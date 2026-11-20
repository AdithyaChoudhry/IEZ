"""
Coversheet Builder - MDL-driven coversheets on an uploaded Excel or PDF template.

A separate router: the existing Coversheet workflows (routers/coversheet.py, coversheet_mdl.py,
coversheet_template.py) and the project MDL register are not changed.

    Stage 1  POST /mdl/extract              Excel or PDF MDL -> document records (+ flags); kept on the server
    Stage 2  GET  /mdl/{id}                 the extracted list
             PUT  /mdl/{id}/records/{rid}   correct a record (marked as corrected)
             POST /mdl/{id}/records         add a record the extraction missed
    Stage 3  POST /template/analyze         Excel or PDF template -> detected fields (+ confidence)
    Stage 7  POST /preview                  populated coversheet (Excel layout model / PDF page images)
    Stage 8  POST /generate, GET /download

The selected MDL record is resolved on the server from the stored extraction (including the user's corrections),
so document number, name and description always come from the MDL record, never from free browser input.
"""
from __future__ import annotations

import io
import json
import re
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from ..auth.models import User
from ..deps import get_current_user

import sys
sys.path.insert(0, '/app')
from utils import coversheet_mdl_extract as MX
from utils.coversheet_builder import FIELD_DEFS, SIGNATURES, TEXT_KEYS, analyze_excel, confirmed, fill_excel, placed
from utils.coversheet_excel_fill import FillError, parse_date
from utils.coversheet_pdf_template import PdfTemplateError, analyze_pdf, fill_pdf, render_pages
from utils.coversheet_render import RenderError, render_pdf, sheet_model
from utils.coversheet_template_analyzer import TemplateError

router = APIRouter(prefix="/coversheet/builder", tags=["Cover Sheet - Builder (MDL + Excel/PDF template)"])

MAX_MDL = 25 * 1024 * 1024
MAX_TEMPLATE = 15 * 1024 * 1024
MAX_SIGNATURE = 5 * 1024 * 1024
_STORE = Path(tempfile.gettempdir()) / "iez_coversheet_builder"
_cache: dict[int, dict] = {}
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MEDIA = {"xlsx": _XLSX, "pdf": "application/pdf", "zip": "application/zip"}


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(text).strip()).strip("._") or "Coversheet"


# ── extraction store (per user, on disk so a restart does not lose the reviewed list) ─────────────────────────
def _path(user_id, eid: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", eid or ""):
        raise HTTPException(404, "MDL extraction not found. Upload the MDL again.")
    return _STORE / str(user_id) / f"{eid}.json"


def _load(user_id, eid: str) -> dict:
    p = _path(user_id, eid)
    if not p.exists():
        raise HTTPException(404, "MDL extraction not found (it may have expired). Upload the MDL again.")
    return json.loads(p.read_text())


def _save(user_id, eid: str, data: dict) -> None:
    p = _path(user_id, eid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))
    olds = sorted(p.parent.glob("*.json"), key=lambda x: x.stat().st_mtime)[:-8]       # keep the 8 latest
    for o in olds:
        o.unlink(missing_ok=True)


def _counts(records: list[dict]) -> dict[str, int]:
    c: dict[str, int] = {}
    for r in records:
        k = r["document_number"].strip().lower()
        if k:
            c[k] = c.get(k, 0) + 1
    return c


def _refresh(data: dict) -> dict:
    counts = _counts(data["records"])
    for r in data["records"]:
        MX.reflag(r, counts, data.get("name_from_description", False))
    recs = data["records"]
    data["summary"] = {
        "records": len(recs),
        "errors": sum(1 for r in recs if r["status"] == "error"),
        "warnings": sum(1 for r in recs if r["status"] == "warning"),
        "duplicates": sum(1 for k, n in counts.items() if n > 1),
        "missing_description": sum(1 for r in recs if not r["document_description"]),
    }
    return data


@router.post("/mdl/extract")
async def mdl_extract(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    data = await file.read()
    if len(data) > MAX_MDL:
        raise HTTPException(413, "The MDL file is too large (limit 25 MB).")
    try:
        res = await run_in_threadpool(MX.extract, data, file.filename or "MDL")
    except MX.MdlExtractError as exc:
        raise HTTPException(422, str(exc))
    eid = uuid.uuid4().hex
    res["extraction_id"] = eid
    res["created"] = time.time()
    _save(user.id, eid, res)
    return res


@router.get("/mdl/{eid}")
def mdl_get(eid: str, user: User = Depends(get_current_user)):
    return _load(user.id, eid)


_EDITABLE = ("document_number", "document_name", "document_description", "revision", "document_type", "discipline")


@router.put("/mdl/{eid}/records/{rid}")
def mdl_update(eid: str, rid: str, body: dict, user: User = Depends(get_current_user)):
    data = _load(user.id, eid)
    rec = next((r for r in data["records"] if r["id"] == rid), None)
    if rec is None:
        raise HTTPException(404, "This document is not in the extracted MDL.")
    changed = False
    for k in _EDITABLE:
        if k in body:
            v = MX.clean(body[k])
            if v != rec[k]:
                rec.setdefault("original", {}).setdefault(k, rec[k])
                rec[k] = v
                changed = True
    if changed:
        rec["edited"] = True
    _save(user.id, eid, _refresh(data))
    return {"record": rec, "summary": data["summary"]}


@router.post("/mdl/{eid}/records")
def mdl_add(eid: str, body: dict, user: User = Depends(get_current_user)):
    data = _load(user.id, eid)
    rec = {k: MX.clean(body.get(k, "")) for k in MX.FIELDS}
    if not rec["document_number"] or not rec["document_name"]:
        raise HTTPException(400, "A manually added document needs a document number and a document name.")
    rec.update(source="added manually", method="manual", edited=True, flags=[], id="m" + uuid.uuid4().hex[:14])
    data["records"].append(rec)
    _save(user.id, eid, _refresh(data))
    return {"record": rec, "summary": data["summary"]}


# ── template ──────────────────────────────────────────────────────────────────
def _kind(name: str, data: bytes) -> str:
    n = (name or "").lower()
    if n.endswith(".pdf") or data[:4] == b"%PDF":
        if data[:4] != b"%PDF":
            raise HTTPException(400, "The file has a .pdf name but is not a valid PDF.")
        return "pdf"
    if n.endswith((".xls", ".xlsb")):
        raise HTTPException(400, "Excel templates must be .xlsx or .xlsm: the existing template engine keeps formatting, "
                                 "logos and print setup only for these (in Excel: File > Save As > Excel Workbook).")
    if n.endswith((".xlsx", ".xlsm")):
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise HTTPException(400, "The uploaded file is not a valid Excel workbook (corrupted or password protected).")
        return "excel"
    raise HTTPException(400, "Unsupported template type. Upload an Excel (.xlsx, .xlsm) or PDF coversheet template.")


async def _template(file: UploadFile, expected: Optional[str] = None) -> tuple[bytes, str]:
    data = await file.read()
    if not data:
        raise HTTPException(400, "The uploaded template is empty.")
    if len(data) > MAX_TEMPLATE:
        raise HTTPException(413, "The template file is too large (limit 15 MB).")
    kind = _kind(file.filename or "", data)
    if expected and expected != kind:
        raise HTTPException(400, f"An {'Excel' if expected == 'excel' else 'PDF'} template was selected, but this file is "
                                 f"{'a PDF' if kind == 'pdf' else 'an Excel workbook'}.")
    return data, kind


@router.post("/template/analyze")
async def template_analyze(file: UploadFile = File(...), kind: Optional[str] = Form(None), sheet: Optional[str] = Form(None),
                           user: User = Depends(get_current_user)):
    data, k = await _template(file, kind)
    try:
        if k == "excel":
            return await run_in_threadpool(analyze_excel, data, sheet or None)
        return await run_in_threadpool(analyze_pdf, data)
    except (TemplateError, PdfTemplateError) as exc:
        raise HTTPException(422, str(exc))


# ── preview / generate ───────────────────────────────────────────────────────
async def _signatures(files: dict[str, Optional[UploadFile]]) -> dict[str, bytes]:
    from PIL import Image
    out = {}
    for key, f in files.items():
        if f is None:
            continue
        data = await f.read()
        if not data:
            continue
        name = (f.filename or "").lower()
        if not name.endswith((".png", ".jpg", ".jpeg")):
            raise HTTPException(400, f"{dict((k, l) for k, l, *_ in FIELD_DEFS)[key]}: use a PNG or JPG image.")
        if len(data) > MAX_SIGNATURE:
            raise HTTPException(413, f"{dict((k, l) for k, l, *_ in FIELD_DEFS)[key]}: the image is larger than 5 MB.")
        try:
            im = Image.open(io.BytesIO(data))
            im.verify()
        except Exception:
            raise HTTPException(400, f"{dict((k, l) for k, l, *_ in FIELD_DEFS)[key]}: the file is not a readable image.")
        out[key] = data
    return out


def _resolve(user_id, body: dict) -> tuple[dict, dict]:
    eid, rid = str(body.get("extraction_id") or ""), str(body.get("record_id") or "")
    if not eid:
        raise HTTPException(400, "Upload and analyse the MDL first.")
    if not rid:
        raise HTTPException(400, "Select a document from the MDL.")
    data = _load(user_id, eid)
    rec = next((r for r in data["records"] if r["id"] == rid), None)
    if rec is None:
        raise HTTPException(409, "The selected document is no longer in the extracted MDL. Select it again.")
    if rec.get("status") == "error":
        raise HTTPException(409, "The selected document is incomplete (" + "; ".join(
            f["message"] for f in rec["flags"] if f["level"] == "error") + "). Correct it in the review table first.")
    counts = _counts(data["records"])
    return rec, {"duplicate": counts.get(rec["document_number"].strip().lower(), 0) > 1}


def _check(kind: str, mapping: dict, values: dict, sigs: dict[str, bytes]) -> list[str]:
    """Problems that stop generation (nothing is generated silently with missing or unplaced information)."""
    label = {k: l for k, l, *_ in FIELD_DEFS}
    p = []
    for k in ("document_number", "document_name"):
        if not placed(mapping.get(k)):
            p.append(f"{label[k]}: no confirmed location in the template.")
    if not values.get("revision"):
        p.append("Revision Number is required.")
    if not values.get("revision_date"):
        p.append("Revision Date is required.")
    else:
        try:
            parse_date(values["revision_date"])
        except FillError as exc:
            p.append(str(exc))
    for k in TEXT_KEYS:
        fm = mapping.get(k) or {}
        if k in ("document_number", "document_name") or fm.get("skipped"):
            continue
        if placed(fm) and not str(values.get(k, "")).strip():
            if k == "document_description":
                p.append("Document Description: the selected MDL record has no description - correct the record or skip the field.")
            else:
                p.append(f"{label[k]}: enter a value or skip the field.")
    for k in SIGNATURES:
        if k in sigs and not confirmed(mapping.get(k)):
            p.append(f"{label[k]}: a signature was uploaded but its location is not confirmed - assign it or remove the signature.")
    return p


def _values(rec: dict, body: dict) -> dict:
    v = {k: str((body.get("values") or {}).get(k, "") or "").strip()
         for k in ("revision", "revision_date", "prepared_by", "checked_by", "approved_by")}
    v.update(document_number=rec["document_number"], document_name=rec["document_name"],
             document_description=rec["document_description"])
    if v["revision_date"]:
        try:
            v["revision_date"] = parse_date(v["revision_date"]).isoformat()
        except FillError:
            pass
    return v


def _pdf_date(values: dict) -> dict:
    """PDF templates have no cell format to learn from: the date is written as DD.MM.YYYY unless a format is given."""
    v = dict(values)
    if v.get("revision_date"):
        d = parse_date(v["revision_date"])
        v["revision_date"] = d.strftime("%d.%m.%Y")
    return v


async def _build(user, file, data, sig_p, sig_c, sig_a, for_preview: bool):
    template, kind = await _template(file)
    try:
        body = json.loads(data)
        assert isinstance(body, dict)
    except Exception:
        raise HTTPException(400, "Invalid request data.")
    rec, info = _resolve(user.id, body)
    sigs = await _signatures({"sig_prepared": sig_p, "sig_checked": sig_c, "sig_approved": sig_a})
    mapping = body.get("mapping") or {}
    values = _values(rec, body)
    problems = _check(kind, mapping, values, sigs)
    if problems:
        raise HTTPException(422, " ".join(problems))
    warnings = []
    if info["duplicate"]:
        warnings.append(f"Document number {rec['document_number']} appears more than once in the MDL - "
                        f"this coversheet uses '{rec['document_name']}'.")
    if rec.get("edited"):
        warnings.append("The selected MDL record was corrected by the user before generation.")
    try:
        if kind == "excel":
            sheet = body.get("sheet") or ""
            out, w = await run_in_threadpool(fill_excel, template, sheet, mapping, values, sigs, bool(body.get("clear_history", True)))
            return kind, rec, out, sheet, template, warnings + w
        out, w = await run_in_threadpool(fill_pdf, template, mapping, _pdf_date(values), sigs)
        return kind, rec, out, None, template, warnings + w
    except (FillError, TemplateError, PdfTemplateError, RenderError) as exc:
        raise HTTPException(422, str(exc))


@router.post("/preview")
async def preview(file: UploadFile = File(...), data: str = Form(...),
                  sig_prepared: Optional[UploadFile] = File(None), sig_checked: Optional[UploadFile] = File(None),
                  sig_approved: Optional[UploadFile] = File(None), user: User = Depends(get_current_user)):
    kind, rec, out, sheet, template, warnings = await _build(user, file, data, sig_prepared, sig_checked, sig_approved, True)
    try:
        if kind == "excel":
            model = await run_in_threadpool(sheet_model, out, sheet, template)
            return {"kind": kind, "model": model, "warnings": warnings, "document_number": rec["document_number"]}
        pages = await run_in_threadpool(render_pages, out, 1.5)
        return {"kind": kind, "pages": pages, "warnings": warnings, "document_number": rec["document_number"]}
    except (RenderError, PdfTemplateError) as exc:
        raise HTTPException(422, str(exc))


@router.post("/generate")
async def generate(file: UploadFile = File(...), data: str = Form(...),
                   sig_prepared: Optional[UploadFile] = File(None), sig_checked: Optional[UploadFile] = File(None),
                   sig_approved: Optional[UploadFile] = File(None), user: User = Depends(get_current_user)):
    kind, rec, out, sheet, template, warnings = await _build(user, file, data, sig_prepared, sig_checked, sig_approved, False)
    body = json.loads(data)
    base = f"{safe_name(rec['document_number'])}_Coversheet"
    files: dict[str, bytes] = {}
    engine = None
    if kind == "excel":
        formats = [f for f in (body.get("formats") or ["xlsx"]) if f in ("xlsx", "pdf")] or ["xlsx"]
        if "xlsx" in formats:
            files[f"{base}.xlsx"] = out
        if "pdf" in formats:
            try:
                pdf, engine = await run_in_threadpool(render_pdf, out, sheet, template)
            except RenderError as exc:
                raise HTTPException(422, str(exc))
            files[f"{base}.pdf"] = pdf
    else:
        files[f"{base}.pdf"] = out
    _cache[user.id] = {"files": files, "base": base}
    return {"filename": next(iter(files)) if len(files) == 1 else f"{base}.zip", "files": sorted(files),
            "kind": kind, "pdf_engine": engine, "warnings": warnings, "document_number": rec["document_number"],
            "message": f"Coversheet generated for {rec['document_number']}."}


@router.get("/download")
async def download(kind: Optional[str] = None, user: User = Depends(get_current_user)):
    e = _cache.get(user.id)
    if not e:
        raise HTTPException(404, "No coversheet found. Generate it first.")
    files = e["files"]
    pick = [n for n in files if kind and n.endswith("." + kind)]
    if pick or len(files) == 1:
        name = pick[0] if pick else next(iter(files))
        return StreamingResponse(io.BytesIO(files[name]), media_type=_MEDIA[name.rsplit(".", 1)[1]],
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in files.items():
            z.writestr(n, b)
    name = f"{e['base']}.zip"
    return StreamingResponse(io.BytesIO(buf.getvalue()), media_type=_MEDIA["zip"],
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})
