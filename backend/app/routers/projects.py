"""
Project document registry router.

Gives the Coversheet Generator (and any other module) a project-level view of the
deliverables produced by the Instrument List, I/O List, Cable Schedule and Loop
Wiring generators. Business logic lives in services/document_registry.py.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth.models import User
from ..deps import get_current_user, get_db, require_lead
from ..models.document_registry import Project
from ..services import document_registry as reg

router = APIRouter(prefix="/projects", tags=["Project Documents"])


def _actor(user: User) -> str:
    return user.username or user.email


def _pid(project_id: str) -> str:
    try:
        return reg.normalize_project_id(project_id)
    except reg.RegistryError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def _fail(exc: reg.RegistryError, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(code, str(exc))


class ProjectCreate(BaseModel):
    project_id: str
    name: Optional[str] = None


class ModulesBody(BaseModel):
    modules: List[str] = Field(default_factory=list)


class DisconnectBody(BaseModel):
    module: str


class StatusBody(BaseModel):
    status: str


# ── Projects ─────────────────────────────────────────────────────────────────
@router.get("")
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Project).order_by(Project.created_at.desc()).all()
    return [{"project_id": p.project_id, "name": p.name, "created_by": p.created_by} for p in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    try:
        proj = reg.get_or_create_project(db, body.project_id, body.name, _actor(user))
        db.commit()
    except reg.RegistryError as exc:
        raise _fail(exc)
    return {"project_id": proj.project_id, "name": proj.name}


# ── Registry views ───────────────────────────────────────────────────────────
@router.get("/{project_id}/documents")
def documents(project_id: str, module: Optional[str] = None,
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Every registered revision for the project (history included)."""
    return reg.list_documents(db, _pid(project_id), module)


@router.get("/{project_id}/documents/connected")
def connected_documents(project_id: str, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Per-module latest/linked revision and synchronisation state."""
    return reg.overview(db, _pid(project_id))


@router.get("/{project_id}/documents/status")
def documents_status(project_id: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    return reg.overview(db, _pid(project_id))["summary"]


@router.get("/{project_id}/document-impact")
def document_impact(project_id: str, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Source (IODB) revision and which documents were generated from an older one."""
    data = reg.overview(db, _pid(project_id))
    return {
        "project_id": data["project_id"],
        "sources": data["sources"],
        "documents": [{
            "module": m["module"], "module_name": m["module_name"],
            "source_kind": m["source_kind"],
            "document_source_rev": m["latest"]["source_rev_no"] if m["latest"] else None,
            "latest_source_rev": m["latest_source_rev"],
            "state": m["state"], "flags": m["flags"],
            "regeneration_required": "regeneration_required" in m["flags"],
        } for m in data["modules"]],
    }


@router.get("/{project_id}/audit")
def audit(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return reg.audit_trail(db, _pid(project_id))


# ── Link management ──────────────────────────────────────────────────────────
@router.post("/{project_id}/documents/connect")
def connect_documents(project_id: str, body: ModulesBody, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    try:
        result = reg.connect(db, _pid(project_id), body.modules, _actor(user))
    except reg.RegistryError as exc:
        raise _fail(exc)
    return {**result, "overview": reg.overview(db, _pid(project_id))}


@router.post("/{project_id}/documents/disconnect")
def disconnect_document(project_id: str, body: DisconnectBody, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    try:
        result = reg.disconnect(db, _pid(project_id), body.module, _actor(user))
    except reg.RegistryError as exc:
        raise _fail(exc)
    return {**result, "overview": reg.overview(db, _pid(project_id))}


@router.post("/{project_id}/documents/{document_id}/status")
def change_status(project_id: str, document_id: int, body: StatusBody,
                  db: Session = Depends(get_db), user: User = Depends(require_lead)):
    """Review/approval status. Lead Engineer / Admin only - engineering judgement stays human."""
    try:
        return reg.set_status(db, _pid(project_id), document_id, body.status, _actor(user))
    except reg.RegistryError as exc:
        raise _fail(exc)


# ── Files ────────────────────────────────────────────────────────────────────
@router.get("/{project_id}/documents/{document_id}/download")
def download_document(project_id: str, document_id: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    try:
        path, name = reg.document_file(db, _pid(project_id), document_id)
    except reg.RegistryError as exc:
        raise _fail(exc, status.HTTP_404_NOT_FOUND)
    return FileResponse(
        path, filename=name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/{project_id}/sources", status_code=status.HTTP_201_CREATED)
async def upload_source(project_id: str, kind: str = Form("iodb"), file: UploadFile = File(...),
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Register a new IODB (or Loop Wiring input) revision for the project without
    generating anything. A file with new content becomes the next revision;
    documents generated from an older revision are then flagged for regeneration.
    """
    pid = _pid(project_id)
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    try:
        reg.get_or_create_project(db, pid, None, _actor(user))
        sv = reg.ensure_source_version(db, pid, kind, file.filename or "source.xlsx", data, _actor(user))
        db.commit()
    except reg.RegistryError as exc:
        raise _fail(exc)
    return {"kind": sv.kind, "rev_no": sv.rev_no, "filename": sv.filename,
            "overview": reg.overview(db, pid)}


# ── Regeneration ─────────────────────────────────────────────────────────────
@router.post("/{project_id}/documents/{document_id}/regenerate")
def regenerate_document(project_id: str, document_id: int, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    try:
        result = reg.regenerate(db, _pid(project_id), document_id, _actor(user))
    except reg.RegistryError as exc:
        raise _fail(exc)
    return {**result, "overview": reg.overview(db, _pid(project_id))}


@router.post("/{project_id}/documents/generate-connected")
def generate_connected_documents(project_id: str, body: ModulesBody, db: Session = Depends(get_db),
                                 user: User = Depends(get_current_user)):
    """
    Regenerate the selected modules in order from the project's latest source files.
    Does not generate the Coversheet itself - the UI does that once `coversheet_ready`
    is true, using the existing Coversheet flow and its approval gate.
    """
    modules = body.modules or list(reg.MODULE_ORDER)
    unknown = [m for m in modules if m not in reg.MODULES]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown module(s): {', '.join(unknown)}")
    result = reg.generate_connected(db, _pid(project_id), modules, _actor(user))
    return {**result, "overview": reg.overview(db, _pid(project_id))}
