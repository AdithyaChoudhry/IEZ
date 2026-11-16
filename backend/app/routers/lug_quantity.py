"""
Cable Lug Quantity Generator (sub-module of the Cable Schedule Generator).

Upload a cable schedule -> physical cables, termination arrangement, lugs per end, totals, exceptions, Excel report.
The uploaded workbook is only read; the only state is a per-user "last report" cache for the download.
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
from utils import lug_quantity as lq  # noqa: E402

router = APIRouter(prefix="/cable-schedule/lug", tags=["Cable Lug Quantity"])
lug_cache: dict = {}
MAX_BYTES = 25 * 1024 * 1024


def _bad(msg: str, code: int = status.HTTP_400_BAD_REQUEST):
    raise HTTPException(status_code=code, detail=msg)


async def _read(upload: UploadFile) -> bytes:
    data = await upload.read()
    if not data:
        _bad("The cable schedule file is empty.")
    if len(data) > MAX_BYTES:
        _bad("The cable schedule file is larger than 25 MB.")
    if not (upload.filename or "").lower().endswith((".xlsx", ".xlsm")):
        _bad("The cable schedule must be an Excel .xlsx file.")
    return data


def _json(text: Optional[str], what: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        _bad(f"The {what} are not valid JSON.")


@router.post("/detect")
async def detect(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Cable schedule sheets found in the workbook (hidden template sheets are listed but not ticked by default)."""
    data = await _read(file)
    try:
        rd = lq._Reader(data)
    except lq.LugError as e:
        _bad(str(e))
    infos = lq.detect_sheets(rd.wf)
    return {"sheets": infos, "default_sheets": lq.default_sheets(infos)}


@router.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    rules: Optional[str] = Form(None),
    overrides: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    data = await _read(file)
    try:
        out, r = lq.analyze(data, _json(rules, "rules"), _json(overrides, "overrides"))
        xlsx = lq.to_workbook(out, r, file.filename or "uploaded cable schedule")
    except lq.GlandError as e:
        _bad(str(e))
    lug_cache[f"{current_user.id}_lug"] = {"bytes": xlsx, "filename": "Cable_Lug_Quantity_Report.xlsx"}
    out["filename"] = "Cable_Lug_Quantity_Report.xlsx"
    return out


@router.get("/download")
async def download(current_user: User = Depends(get_current_user)):
    cached = lug_cache.get(f"{current_user.id}_lug")
    if not cached:
        _bad("No lug report found. Please generate it first.", status.HTTP_404_NOT_FOUND)
    return StreamingResponse(io.BytesIO(cached["bytes"]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={cached['filename']}"})
