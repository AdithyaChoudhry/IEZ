"""
Deliverables: the centralised cover sheet and the Excel / PDF downloads of the Instrument List, I/O List, Cable Schedule,
Loop Wiring and Datasheet generators.

  GET  /deliverables/cover                 the cover sheet a generator will use (status, MDL document, revision)
  GET  /deliverables/cover/details         the entered cover details (Cover Sheet Generator form)
  GET  /deliverables/cover/mdl             search the project MDL for the document (engineer's pick)
  PUT  /deliverables/cover                 save the pick / the cover details (Cover Sheet Generator)
  GET  /deliverables/covers                every cover record of a project
  GET  /deliverables/{module}/info         the user's last generated deliverable of a module (cover state, file name)
  POST /deliverables/{module}/pdf          start converting the SAME workbook to PDF (background - large schedules take minutes)
  GET  /deliverables/{module}/pdf/status   poll it
  GET  /deliverables/{module}/pdf          the PDF (LibreOffice)

Generators call finalize() once, right after generating: the cover sheet goes into the workbook, the result is what
both the Excel and the PDF download serve. A cover problem never stops the engineering output - it is reported.
A cover sheet is not approval-controlled: the output is never marked DRAFT because of the cover.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth.models import User
from ..database import SessionLocal
from ..deps import get_current_user, get_db
from ..services import deliverable_covers as DC
from ..services import mdl_service

import sys
sys.path.insert(0, '/app')
from utils import deliverable_output as DO  # noqa: E402

logger = logging.getLogger("iez.deliverables")
router = APIRouter(prefix="/deliverables", tags=["Deliverables"])
MODULES = tuple(DC.DOC_TYPES)
_outputs: dict[tuple, dict] = {}          # (user id, module) -> last finalised deliverable (bytes are the Excel download)
_pdf_slot = threading.Semaphore(1)          # one LibreOffice conversion at a time (memory on a small server)
PDF_FAILED = "Excel generation completed successfully, but PDF conversion failed. Please review the PDF generation error: "


def _bad(msg: str, code: int = status.HTTP_400_BAD_REQUEST):
    raise HTTPException(status_code=code, detail=msg)


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


# ── used by the generators ───────────────────────────────────────────────────
def finalize(user_id, module: str, project_id: Optional[str], data: bytes, filename: str, *, sub_key: str = "",
             sub_label: str = "", custom_template: Optional[bytes] = None, db: Optional[Session] = None,
             snapshot: Optional[dict] = None, composed: Optional[dict] = None) -> tuple[bytes, str, dict]:
    """
    -> (final bytes, file name, cover info). The cover sheet of the project's MDL document is put first in the workbook
    (or in place of the template's own cover sheet). Without a resolvable cover the workbook is
    returned unchanged with the reason. The result is remembered for the Excel / PDF downloads.
    `snapshot` (optional): a cover resolution + cover workbook taken earlier in the same request ({"resolution", "cover", "warnings",
    "message"}); it is used instead of resolving again, so the document metadata and the inserted cover are one consistent snapshot.
    `composed` (optional, I/O List standard document): {"bytes": the finished workbook, its cover already inserted, "cover_sheet": name or
    None, "pdf": the PDF of exactly that workbook or None, "renderer": workbook -> PDF}; the workbook is then served as it is.
    """
    own = db is None
    db = db or SessionLocal()
    info: dict = {"applied": False}
    try:
        r = snapshot["resolution"] if snapshot is not None else DC.resolve(db, project_id or "", module, sub_key, sub_label)
        info.update(status=r["status"], message=r["message"], doc_label=r["doc_label"], project_id=r["project_id"],
                    revision=r["revision"],
                    document_number=(r["record"] or {}).get("document_number"),
                    document_title=(r["record"] or {}).get("document_name"))
        if r["record"] is not None and r["revision"] is not None:
            if snapshot is not None:
                if snapshot.get("cover") is None:
                    raise DC.CoverError(snapshot.get("message") or "No cover sheet is available for this document.")
                cover, warnings = snapshot["cover"], snapshot.get("warnings") or []
            else:
                cover, warnings = DC.cover_workbook(db, r, custom_template)
            draft = False                                    # a cover sheet has no approval state: nothing is marked DRAFT
            if composed is not None:
                info["cover_sheet"] = composed["cover_sheet"]
            elif filename.lower().endswith(".zip"):
                data = DO.insert_cover_in_zip(data, cover, draft)
            else:
                data, info["cover_sheet"] = DO.insert_cover(data, cover, draft)
            ext = filename.rsplit(".", 1)[-1]
            filename = _safe(f"{r['record']['document_number']}_{r['revision']}_{DC.DOC_TYPES[module]['label']}") + "." + ext
            info.update(applied=True, draft=draft, custom_template=bool(custom_template), warnings=warnings)
    except DC.CoverError as e:
        info.update(applied=False, message=str(e))
    except Exception as e:                                       # the engineering output is never lost to a cover problem
        logger.exception("Cover sheet for %s failed", module)
        info.update(applied=False, message=f"The cover sheet could not be added: {e}")
    finally:
        if own:
            db.close()
    if composed is not None:
        data = composed["bytes"]
    ready = composed.get("pdf") if composed else None
    _outputs[(user_id, module)] = {"bytes": data, "filename": filename, "info": info, "pdf": ready, "pdf_status": "done" if ready else None,
                                   "pdf_error": None, "digest": hashlib.sha256(data).hexdigest(),
                                   "renderer": composed.get("renderer") if composed else None}
    return data, filename, info


# ── cover sheet API ──────────────────────────────────────────────────────────
@router.get("/cover")
def get_cover(doc_type: str, project_id: Optional[str] = None, sub_key: str = "", sub_label: str = "",
              db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return DC.resolve(db, project_id or "", doc_type, sub_key, sub_label)
    except DC.CoverError as e:
        _bad(str(e))


@router.get("/cover/details")
def cover_details(doc_type: str, project_id: str, sub_key: str = "", db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    try:
        DC.check_type(doc_type)
    except DC.CoverError as e:
        _bad(str(e))
    return DC.details(db, project_id, doc_type, sub_key)


@router.get("/cover/mdl")
def cover_mdl(project_id: str, q: str = "", db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return mdl_service.search(db, project_id, q=q, limit=50)


class CoverBody(BaseModel):
    project_id: str
    doc_type: str
    sub_key: str = ""
    mdl_record_id: Optional[str] = None
    clear_record: bool = False
    project_info: Optional[dict] = None
    revisions: Optional[list[dict]] = None


@router.put("/cover")
def put_cover(body: CoverBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        DC.save(db, body.project_id, body.doc_type, body.sub_key, user.username, mdl_record_id=body.mdl_record_id,
                project_info=body.project_info, revisions=body.revisions, clear_record=body.clear_record)
    except DC.CoverError as e:
        _bad(str(e))
    return {"ok": True}


@router.get("/covers")
def covers(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {"covers": DC.list_covers(db, project_id), "types": {k: v["label"] for k, v in DC.DOC_TYPES.items()}}


# ── downloads ────────────────────────────────────────────────────────────────
def _output(user: User, module: str) -> dict:
    if module not in MODULES:
        _bad(f"Unknown deliverable '{module}'.", status.HTTP_404_NOT_FOUND)
    out = _outputs.get((user.id, module))
    if not out:
        _bad("No generated document found. Please generate it first.", status.HTTP_404_NOT_FOUND)
    return out


@router.get("/{module}/info")
def output_info(module: str, user: User = Depends(get_current_user)):
    out = _output(user, module)
    return {"filename": out["filename"], "cover": out["info"], "pdf_available": DO.soffice() is not None}


def _convert(out: dict) -> None:
    """Background: the remembered workbook -> PDF (or a zip of PDFs). The output dict is a snapshot of one generation."""
    draft = bool(out["info"].get("draft"))
    try:
        with _pdf_slot:
            if out["filename"].lower().endswith(".zip"):
                pdf = DO.to_pdf_zip(out["bytes"], draft)
            elif out.get("renderer"):                    # a document that carries its own print settings
                pdf = out["renderer"](out["bytes"])
            else:
                pdf = DO.to_pdf(out["bytes"], draft)
        out.update(pdf=pdf, pdf_status="done")
    except DO.PdfUnavailable as e:
        out.update(pdf_status="error", pdf_error=PDF_FAILED + str(e))
    except DO.PdfFailed as e:
        out.update(pdf_status="error", pdf_error=PDF_FAILED + str(e))
    except Exception:
        logger.exception("PDF conversion failed")
        out.update(pdf_status="error", pdf_error=PDF_FAILED + "the workbook could not be converted.")


def _pdf_state(out: dict) -> dict:
    return {"status": out["pdf_status"] or "not_started", "error": out["pdf_error"], "filename": _pdf_name(out["filename"])}


def _pdf_name(filename: str) -> str:
    zipped = filename.lower().endswith(".zip")
    return re.sub(r"\.(xlsx|zip)$", "", filename, flags=re.I) + ("_PDF.zip" if zipped else ".pdf")


@router.post("/{module}/pdf")
def start_pdf(module: str, user: User = Depends(get_current_user)):
    out = _output(user, module)
    if out["pdf_status"] in (None, "error"):
        if DO.soffice() is None:
            _bad(PDF_FAILED + "PDF conversion is not available on this server: LibreOffice is not installed.",
                 status.HTTP_503_SERVICE_UNAVAILABLE)
        out.update(pdf_status="running", pdf_error=None)
        threading.Thread(target=_convert, args=(out,), daemon=True).start()
    return _pdf_state(out)


@router.get("/{module}/pdf/status")
def pdf_status(module: str, user: User = Depends(get_current_user)):
    return _pdf_state(_output(user, module))


@router.get("/{module}/pdf")
def output_pdf(module: str, user: User = Depends(get_current_user)):
    out = _output(user, module)
    if out["pdf_status"] != "done":
        _bad(out["pdf_error"] or "The PDF is not ready yet. Start it and wait until it is done.", status.HTTP_409_CONFLICT)
    zipped = out["filename"].lower().endswith(".zip")
    return StreamingResponse(io.BytesIO(out["pdf"]), media_type="application/zip" if zipped else "application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{_pdf_name(out["filename"])}"'})
