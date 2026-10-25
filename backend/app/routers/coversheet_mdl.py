"""
Coversheet - Master Document List (MDL) endpoints.

Per-project MDL upload and searchable document register. The Coversheet generate
endpoint (routers/coversheet.py) resolves the selected record from here, so the
MDL stays the authoritative source of document number and title.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from ..auth.models import User
from ..deps import get_current_user, get_db
from ..services import document_registry as reg
from ..services import mdl_service as mdl

router = APIRouter(prefix="/projects/{project_id}/coversheet/mdl", tags=["Coversheet MDL"])

MAX_MDL_BYTES = 25 * 1024 * 1024


def _pid(project_id: str) -> str:
    try:
        return reg.normalize_project_id(project_id)
    except reg.RegistryError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/upload")
async def upload_mdl(
    project_id: str,
    file: UploadFile = File(...),
    selected_record_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Upload the project's MDL (replaces the active one). `selected_record_id` is the
    document currently chosen in the Coversheet; the response says whether it still
    exists in the new MDL.
    """
    pid = _pid(project_id)
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty.")
    if len(data) > MAX_MDL_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The MDL file is too large (limit 25 MB).")
    try:
        return mdl.upload(db, pid, file.filename or "MDL.xlsx", data, user.username, selected_record_id)
    except (mdl.MdlError, reg.RegistryError) as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("")
def mdl_status(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return mdl.summary(db, _pid(project_id))


@router.delete("")
def remove_mdl(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Remove the active MDL (manual Coversheet entry becomes available again)."""
    return mdl.remove_active(db, _pid(project_id), user.username)


@router.get("/documents")
def list_documents(
    project_id: str,
    discipline: str = "", category: str = "",
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    return mdl.search(db, _pid(project_id), "", discipline, category, limit, offset)


@router.get("/search")
def search_documents(
    project_id: str,
    q: str = "", discipline: str = "", category: str = "",
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Search by document name, document number or discipline."""
    return mdl.search(db, _pid(project_id), q, discipline, category, limit, offset)


@router.get("/document/{record_id}")
def get_document(project_id: str, record_id: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    rec = mdl.get_record(db, _pid(project_id), record_id)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "This document is not in the project's active MDL.")
    return {**rec, "coversheet": mdl.coversheet_fields(rec)}
