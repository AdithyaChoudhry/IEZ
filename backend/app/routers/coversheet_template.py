"""
Coversheet Generator - "Use Uploaded Excel Coversheet Template" workflow.

Separate from routers/coversheet.py (the existing iEZ workflow is untouched). Stateless apart from the
last-generated download cache: the browser sends the template with every call and keeps the confirmed
field mapping for the browser session only.

    MDL           -> WHAT to generate   (document number + description, read server-side, never from the browser)
    template      -> HOW it looks       (layout, logos, merges, formulas, protection, print setup)
    user input    -> WHO / WHICH        (revision, date, prepared / checked / approved by)
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth.models import User
from ..deps import get_current_user, get_db
from ..services import document_registry as _registry
from ..services import mdl_service

import sys
sys.path.insert(0, '/app')
from utils.coversheet_template_analyzer import TemplateError, analyze
from utils.coversheet_excel_fill import FillError, fill_template, validate_mapping
from utils.coversheet_render import RenderError, render_pdf, sheet_model

router = APIRouter(prefix="/coversheet/template", tags=["Cover Sheet - Uploaded Template"])

MAX_TEMPLATE_BYTES = 15 * 1024 * 1024
MAX_DOCUMENTS = 200
_cache: dict[int, dict] = {}

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MEDIA = {"xlsx": _XLSX, "pdf": "application/pdf", "zip": "application/zip"}


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(text).strip()).strip("._") or "Coversheet"


async def _read_template(file: UploadFile) -> bytes:
    name = (file.filename or "").lower()
    if name.endswith((".xlsm", ".xls", ".xlsb")):
        raise HTTPException(400, "Please upload the coversheet template as an .xlsx file "
                                 "(in Excel: File > Save As > Excel Workbook).")
    if not name.endswith(".xlsx"):
        raise HTTPException(400, "The coversheet template must be an Excel .xlsx file.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "The uploaded template is empty.")
    if len(data) > MAX_TEMPLATE_BYTES:
        raise HTTPException(413, "The template file is too large (limit 15 MB).")
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise HTTPException(400, "The uploaded file is not a valid Excel workbook (it may be corrupted or password protected).")
    return data


def _json(data: str) -> dict:
    try:
        obj = json.loads(data)
        if not isinstance(obj, dict):
            raise ValueError
        return obj
    except Exception:
        raise HTTPException(400, "Invalid request data.")


@router.post("/analyze")
async def analyze_template(file: UploadFile = File(...), sheet: Optional[str] = Form(None),
                           current_user: User = Depends(get_current_user)):
    """Structure + detected fields (with confidence) of the uploaded template. Nothing is stored."""
    data = await _read_template(file)
    try:
        return await run_in_threadpool(analyze, data, sheet or None)
    except TemplateError as exc:
        raise HTTPException(422, str(exc))


def _values(body: dict, record: Optional[dict]) -> dict:
    v = {k: str(body.get("values", {}).get(k, "") or "").strip()
         for k in ("revision", "date", "prepared_by", "checked_by", "approved_by")}
    if record:
        v["document_number"] = record["document_number"]
        v["document_description"] = record["document_name"]
    return v


@router.post("/preview")
async def preview(file: UploadFile = File(...), data: str = Form(...),
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The populated coversheet as a layout model for on-screen preview (same model the fallback PDF uses)."""
    tb = await _read_template(file)
    body = _json(data)
    record = _resolve_records(db, body, limit=1)[0]
    values = _values(body, record)
    try:
        out, warnings = await run_in_threadpool(fill_template, tb, body.get("sheet", ""), body.get("mapping") or {},
                                                values, bool(body.get("clear_history", True)))
        model = await run_in_threadpool(sheet_model, out, body["sheet"], tb)
    except (FillError, TemplateError, RenderError) as exc:
        raise HTTPException(422, str(exc))
    return {"model": model, "warnings": warnings, "document_number": record["document_number"]}


def _resolve_records(db: Session, body: dict, limit: int = MAX_DOCUMENTS) -> list[dict]:
    """Selected MDL records, resolved server-side from the project's active MDL (exact values)."""
    ids = [str(i) for i in (body.get("record_ids") or []) if str(i).strip()]
    if not ids:
        raise HTTPException(400, "Select at least one document from the MDL.")
    if len(set(ids)) > limit:
        raise HTTPException(400, f"Select at most {limit} documents at a time.")
    try:
        pid = _registry.normalize_project_id(body.get("project_id") or "")
    except _registry.RegistryError as exc:
        raise HTTPException(400, str(exc))
    if not mdl_service.get_active(db, pid):
        raise HTTPException(400, "No Master Document List is uploaded for this project. Upload the MDL first.")
    out, seen = [], set()
    for rid in ids:
        if rid in seen:
            continue
        seen.add(rid)
        rec = mdl_service.get_record(db, pid, rid)
        if rec is None:
            raise HTTPException(409, "A selected document is not in this project's active MDL. Select the documents again.")
        out.append(rec)
    body["_pid"] = pid
    return out


@router.post("/generate")
async def generate(file: UploadFile = File(...), data: str = Form(...),
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Build the coversheet(s). One selected document -> <DOCNO>_Coversheet.xlsx / .pdf; several -> one ZIP.
    The master template is only read; every output is a fresh workbook.
    """
    tb = await _read_template(file)
    body = _json(data)
    formats = [f for f in (body.get("formats") or ["xlsx"]) if f in ("xlsx", "pdf")] or ["xlsx"]
    records = _resolve_records(db, body)
    sheet = body.get("sheet", "")
    mapping = body.get("mapping") or {}
    clear = bool(body.get("clear_history", True))

    files: dict[str, bytes] = {}
    warnings: list[str] = []
    engine = None
    for rec in records:
        values = _values(body, rec)
        base = f"{safe_name(rec['document_number'])}_Coversheet"
        try:
            out, w = await run_in_threadpool(fill_template, tb, sheet, mapping, values, clear)
            if "xlsx" in formats:
                files[f"{base}.xlsx"] = out
            if "pdf" in formats:
                pdf, engine = await run_in_threadpool(render_pdf, out, sheet, tb)
                files[f"{base}.pdf"] = pdf
        except (FillError, TemplateError, RenderError) as exc:
            raise HTTPException(422, f"{rec['document_number']}: {exc}")
        warnings += [f"{rec['document_number']}: {m}" for m in w] if len(records) > 1 else w
    if len(files) != len({*files}) or not files:
        raise HTTPException(500, "Nothing was generated.")

    if len(files) == 1:
        (name, payload), = files.items()
        kind = name.rsplit(".", 1)[1]
    else:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n, b in files.items():
                z.writestr(n, b)
        payload = buf.getvalue()
        name = "Coversheets.zip" if len(records) > 1 else f"{safe_name(records[0]['document_number'])}_Coversheet.zip"
        kind = "zip"
    entry = {"name": name, "bytes": payload, "kind": kind, "single": {}}
    if len(records) == 1:
        entry["single"] = {n.rsplit(".", 1)[1]: (n, b) for n, b in files.items()}
    _cache[current_user.id] = entry
    for rec in records:
        mdl_service.audit_generation(db, body["_pid"], current_user.username, rec, name)
    return {"filename": name, "kind": kind, "count": len(records), "files": sorted(files),
            "pdf_engine": engine, "warnings": warnings,
            "message": f"Generated {len(records)} coversheet{'s' if len(records) != 1 else ''}."}


@router.get("/download")
async def download(kind: Optional[str] = None, current_user: User = Depends(get_current_user)):
    """The last generated output. For a single document with both formats, `kind=xlsx|pdf` picks one."""
    e = _cache.get(current_user.id)
    if not e:
        raise HTTPException(404, "No coversheet found. Generate one first.")
    name, payload, k = e["name"], e["bytes"], e["kind"]
    if kind in ("xlsx", "pdf") and kind in e["single"]:
        name, payload = e["single"][kind]
        k = kind
    return StreamingResponse(io.BytesIO(payload), media_type=_MEDIA.get(k, "application/octet-stream"),
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})
