"""
Cable Gland Quantity Generator (sub-module of the Cable Schedule Generator).

  /analyze  - gland quantities + OD advisory for an uploaded cable schedule
  /advise   - manual cable OD -> gland advice
  /reference - the reference database (built-in published tables + standards), vendor table check and template
Stateless apart from a per-user "last report" cache for the download. The uploaded schedule is only read.
"""
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from ..auth.models import User
from ..deps import get_current_user

import sys
sys.path.insert(0, '/app')
from utils import gland_advisor as adv  # noqa: E402
from utils import gland_quantity as gq  # noqa: E402
from utils import gland_reference as ref  # noqa: E402
from utils import gland_service as svc  # noqa: E402

router = APIRouter(prefix="/cable-schedule/gland", tags=["Cable Gland Quantity"])
gland_cache: dict = {}
MAX_BYTES = 25 * 1024 * 1024


def _bad(msg: str, code: int = status.HTTP_400_BAD_REQUEST):
    raise HTTPException(status_code=code, detail=msg)


async def _read(upload: UploadFile, what: str) -> bytes:
    data = await upload.read()
    if not data:
        _bad(f"The {what} file is empty.")
    if len(data) > MAX_BYTES:
        _bad(f"The {what} file is larger than 25 MB.")
    if not (upload.filename or "").lower().endswith((".xlsx", ".xlsm")):
        _bad(f"The {what} must be an Excel .xlsx file.")
    return data


def _json(text: Optional[str], what: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        _bad(f"The {what} are not valid JSON.")


async def _extra_rows(upload: Optional[UploadFile]):
    if upload is None:
        return None, []
    try:
        rows, problems = ref.read_vendor_table(await _read(upload, "gland reference table"), tier="VENDOR")
    except ValueError as e:
        _bad(str(e))
    return rows, problems


def _public(p: dict) -> dict:
    return {k: v for k, v in p.items() if not k.startswith("_")}


@router.post("/detect")
async def detect(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Cable schedule sheets found in the workbook and the cable types (for the OD table)."""
    data = await _read(file, "cable schedule")
    try:
        occ, exc, infos, types = gq.extract(data, gq.Settings())
    except gq.GlandError as e:
        _bad(str(e))
    return {"sheets": infos, "default_sheets": gq.default_sheets(infos), "cable_types": types, "occurrences": len(occ),
            "exceptions": len(exc)}


@router.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    settings: Optional[str] = Form(None),
    cable_data: Optional[str] = Form(None),
    project: Optional[str] = Form(None),
    reference_file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
):
    data = await _read(file, "cable schedule")
    extra, problems = await _extra_rows(reference_file)
    try:
        p = svc.analyze(data, _json(settings, "settings"), _json(cable_data, "cable OD data"), _json(project, "project settings"), extra, problems)
        xlsx = svc.to_workbook(p, file.filename or "uploaded cable schedule")
    except (gq.GlandError, adv.AdviceError) as e:
        _bad(str(e))
    gland_cache[f"{current_user.id}_gland"] = {"bytes": xlsx, "filename": "Gland_Quantity_Report.xlsx"}
    out = _public(p)
    out["filename"] = "Gland_Quantity_Report.xlsx"
    return out


@router.post("/advise")
async def advise(
    inputs: str = Form(...),
    project: Optional[str] = Form(None),
    reference_file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
):
    form = _json(inputs, "inputs") or {}
    extra, problems = await _extra_rows(reference_file)
    try:
        out = svc.advise_payload(form, _json(project, "project settings"), extra)
    except adv.AdviceError as e:
        _bad(str(e))
    out["reference_problems"] = problems
    return out


@router.get("/reference")
async def reference(current_user: User = Depends(get_current_user)):
    rows = ref.builtin()
    return {"standards": ref.STANDARDS, "principles": ref.PRINCIPLES, "disclaimer": adv.NOT_FINAL, "rule": adv.RULE_OD_VS_THREAD,
            "rows": [r.to_dict() for r in rows], "priority": "Project specification > approved vendor/project gland database > generic engineering reference",
            "limits": ["The built-in tables hold Metric and NPT entry threads only (CMP Products published example tables).",
                       "No IP rating, Ex certification, material or temperature data is in the built-in tables: those checks stay 'verify with the manufacturer'.",
                       "ET and BSP need a manufacturer table (upload it below); nothing is inferred from Metric or NPT.",
                       "Live retrieval from the internet is not performed; the tables were read from the manufacturer's page on " + ref.RETRIEVED + "."],
            "template_headers": ref.TEMPLATE_HEADERS}


@router.post("/reference/check")
async def reference_check(reference_file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    rows, problems = await _extra_rows(reference_file)
    return {"rows": len(rows), "problems": problems, "preview": [r.to_dict() for r in rows[:50]],
            "standards_offered": sorted({s for s in ("METRIC", "NPT", "BSP", "ET") if any(r.threads(s) for r in rows)})}


@router.get("/reference/template")
async def reference_template(current_user: User = Depends(get_current_user)):
    return StreamingResponse(io.BytesIO(ref.template_workbook()),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=Gland_Reference_Table_Template.xlsx"})


@router.get("/download")
async def download(current_user: User = Depends(get_current_user)):
    cached = gland_cache.get(f"{current_user.id}_gland")
    if not cached:
        _bad("No gland report found. Please generate it first.", status.HTTP_404_NOT_FOUND)
    return StreamingResponse(io.BytesIO(cached["bytes"]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={cached['filename']}"})
