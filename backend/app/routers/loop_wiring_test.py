"""
Loop Wiring (TEST) - experimental module, independent of the production Loop Wiring Generator.

IODB + I/O Assignment + user loop configuration -> matching & validation -> generic renderer.
All logic lives in services/loop_test_service.py and utils/loop_test/.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth.models import User
from ..deps import get_current_user, get_db
from ..services import document_registry as reg
from ..services import loop_test_service as svc

router = APIRouter(prefix="/loop-wiring-test", tags=["Loop Wiring (Test)"])
MAX_UPLOAD = 40 * 1024 * 1024


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except (svc.LoopTestError, reg.RegistryError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def _label(user: User) -> str:
    return user.username or user.email


class MappingBody(BaseModel):
    mapping: Dict[str, Optional[str]] = Field(default_factory=dict)
    confirm: bool = False


class DecisionBody(BaseModel):
    kind: str                       # "conflict" | "suggestion"
    tag: str
    field: str = ""
    choice: str = ""
    iodb_tag: str = ""


class DefaultConfigBody(BaseModel):
    tag: str
    loop_type: str
    params: Dict[str, Any] = Field(default_factory=dict)
    signals: List[str] = Field(default_factory=list)
    template_id: str = ""


class FromTemplateBody(BaseModel):
    tag: str
    template_id: str


class ConfigBody(BaseModel):
    config: Dict[str, Any]


class CloneBody(BaseModel):
    config: Dict[str, Any]
    tag: str


class GenerateBody(BaseModel):
    tags: List[str]
    configs: Dict[str, Any] = Field(default_factory=dict)
    allow_warnings: bool = True


class TemplateBody(BaseModel):
    name: str
    description: str = ""
    config: Dict[str, Any]


@router.get("/library")
def library(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc._lt().library.library_payload(svc.list_templates(db))


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(project_id: str = Form(""), iodb_revision: str = Form(""), iodb_file: UploadFile = File(...),
                         user: User = Depends(get_current_user)):
    data = await iodb_file.read()
    if not data or len(data) > MAX_UPLOAD:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a non-empty IODB under 40 MB.")
    return _guard(svc.create_session, user.id, project_id, iodb_file.filename or "IODB.xlsx", data, iodb_revision)


@router.post("/sessions/{sid}/io")
async def upload_io(sid: str, io_revision: str = Form(""), io_file: UploadFile = File(...),
                    user: User = Depends(get_current_user)):
    data = await io_file.read()
    if not data or len(data) > MAX_UPLOAD:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a non-empty I/O Assignment under 40 MB.")
    return _guard(svc.attach_io, sid, user.id, io_file.filename or "IO_Assignment.xlsx", data, io_revision)


@router.put("/sessions/{sid}/io-mapping")
def io_mapping(sid: str, body: MappingBody, user: User = Depends(get_current_user)):
    return _guard(svc.set_io_mapping, sid, user.id, body.mapping, body.confirm)


@router.get("/sessions/{sid}")
def session(sid: str, user: User = Depends(get_current_user)):
    return _guard(svc.session_info, sid, user.id)


@router.post("/sessions/{sid}/match")
def match(sid: str, user: User = Depends(get_current_user)):
    result = _guard(svc.run_match, sid, user.id)
    return {"summary": result["summary"]}


@router.get("/sessions/{sid}/matches")
def matches(sid: str, status_filter: str = "", q: str = "", limit: int = 100, offset: int = 0,
            user: User = Depends(get_current_user)):
    return _guard(svc.list_matches, sid, user.id, status_filter, q, limit, offset)


@router.get("/sessions/{sid}/tags/{tag:path}")
def tag_detail(sid: str, tag: str, user: User = Depends(get_current_user)):
    return _guard(svc.tag_detail, sid, user.id, tag)


@router.post("/sessions/{sid}/decisions")
def decision(sid: str, body: DecisionBody, user: User = Depends(get_current_user)):
    return {"summary": _guard(svc.save_decision, sid, user.id, body.kind, body.tag, body.field, body.choice, body.iodb_tag)}


@router.post("/sessions/{sid}/config/default")
def default_config(sid: str, body: DefaultConfigBody, user: User = Depends(get_current_user)):
    return _guard(svc.default_config, sid, user.id, body.tag, body.loop_type, body.params, body.signals, body.template_id)


@router.post("/sessions/{sid}/config/from-template")
def from_template(sid: str, body: FromTemplateBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _guard(svc.apply_template, db, body.template_id, sid, user.id, body.tag)


@router.post("/sessions/{sid}/config/clone")
def clone_config(sid: str, body: CloneBody, user: User = Depends(get_current_user)):
    return _guard(svc.clone_config, sid, user.id, body.config, body.tag)


@router.put("/sessions/{sid}/config")
def save_config(sid: str, body: ConfigBody, user: User = Depends(get_current_user)):
    return _guard(svc.save_config, sid, user.id, body.config)


@router.post("/sessions/{sid}/preview")
def preview(sid: str, body: ConfigBody, user: User = Depends(get_current_user)):
    return _guard(svc.preview, sid, user.id, _label(user), body.config)


@router.post("/sessions/{sid}/validate")
def validate(sid: str, body: ConfigBody, user: User = Depends(get_current_user)):
    return _guard(svc.validate_only, sid, user.id, body.config)


@router.post("/sessions/{sid}/generate")
def generate(sid: str, body: GenerateBody, user: User = Depends(get_current_user)):
    if not body.tags:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Select at least one tag.")
    return _guard(svc.generate, sid, user.id, _label(user), body.tags, body.configs, body.allow_warnings)


@router.get("/sessions/{sid}/download")
def download(sid: str, user: User = Depends(get_current_user)):
    path, name = _guard(svc.output_file, sid, user.id)
    return FileResponse(path, filename=name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/templates")
def templates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.list_templates(db)


@router.post("/templates", status_code=status.HTTP_201_CREATED)
def save_template(body: TemplateBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _guard(svc.save_template, db, _label(user), body.name, body.description, body.config)


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not svc.delete_template(db, template_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")
    return {"deleted": True}
