"""
Drum Schedule Generator (a sub-module of the Cable Schedule Generator).

IODB (the same bytes the Cable Schedule uses) + Drum Master Excel -> sequential drum allocation.
Stateless apart from a per-user "last generated workbook" cache for the download.
"""
import io
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from ..auth.models import User
from ..deps import get_current_user

import sys
sys.path.insert(0, '/app')
from utils import drum_schedule as ds  # noqa: E402
from utils.cable_schedule_extra import ExtraSheetError  # noqa: E402

router = APIRouter(prefix="/cable-schedule/drum", tags=["Drum Schedule"])
drum_cache: dict = {}
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


def _iodb_frame(data: bytes):
    from utils.file_handler import read_iodb
    df, err = read_iodb(io.BytesIO(data))
    if err:
        _bad(f"Failed to read IODB: {err}")
    return df


def _issues(issues, limit=40):
    return [dict(severity=i.severity, kind=i.kind, ref=i.ref, message=i.message)
            for i in sorted(issues, key=lambda i: {"ERROR": 0, "WARNING": 1, "INFO": 2}[i.severity])][:limit]


@router.post("/demand")
async def drum_demand(iodb_file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Step 1: how many cable requirements the IODB gives (branch + main, shared main cables once) and its problems."""
    df = _iodb_frame(await _read(iodb_file, "IODB"))
    try:
        demands, issues, stats = ds.extract_demand(df)
    except (ds.DrumError, ExtraSheetError) as e:
        _bad(str(e))
    counts: dict = {}
    for i in issues:
        counts[i.severity] = counts.get(i.severity, 0) + 1
    types = {}
    for d in demands:
        k = (d.cable_type, d.is_nis or "-")
        types[k] = types.get(k, 0) + d.length
    return {"stats": stats, "issues": _issues(issues), "issue_counts": counts,
            "cable_types": [dict(cable_type=k[0], is_nis=k[1], required=ds.fmt(v)) for k, v in sorted(types.items())]}


@router.post("/master")
async def drum_master(drum_master_file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Step 2: read and validate the Drum Master."""
    data = await _read(drum_master_file, "Drum Master")
    try:
        lots, issues, info = ds.read_drum_master(data)
    except ds.DrumError as e:
        _bad(str(e))
    return {"info": info, "issues": _issues(issues),
            "lots": [dict(master_id=l.master_id, cable_type=l.size or l.cable_type, is_nis=l.is_nis or "-", length=ds.fmt(l.length),
                          qty=l.qty, split="YES" if l.split else "NO", vendor=l.vendor) for l in lots][:200]}


@router.post("/generate")
async def drum_generate(
    iodb_file: UploadFile = File(...),
    drum_master_file: UploadFile = File(...),
    min_residual: float = Form(ds.DEFAULT_MIN_RESIDUAL),
    use_master_split: bool = Form(True),
    current_user: User = Depends(get_current_user),
):
    iodb = await _read(iodb_file, "IODB")
    master = await _read(drum_master_file, "Drum Master")
    df = _iodb_frame(iodb)
    try:
        res = ds.run(df, master, min_residual=min_residual, use_master_split=use_master_split)
        xlsx = ds.to_workbook(res)
    except (ds.DrumError, ExtraSheetError) as e:
        _bad(str(e))
    drum_cache[f"{current_user.id}_drum"] = {"bytes": xlsx, "filename": "Drum_Schedule.xlsx"}
    out = ds.payload(res)
    out["filename"] = "Drum_Schedule.xlsx"
    return out


@router.get("/download")
async def drum_download(current_user: User = Depends(get_current_user)):
    cached = drum_cache.get(f"{current_user.id}_drum")
    if not cached:
        _bad("No drum schedule found. Please generate it first.", status.HTTP_404_NOT_FOUND)
    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={cached['filename']}"})
