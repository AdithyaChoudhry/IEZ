"""
Cable Lug Quantity Generator (sub-module of the Cable Schedule Generator).

Upload a cable schedule -> physical cables, termination arrangement, lugs per end, totals, exceptions, Excel report.
The uploaded workbook is only read; the only state is a per-user "last report" cache for the download.
"""
import io
import json
import logging
import threading
import time
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from ..auth.models import User
from ..deps import get_current_user

import sys
sys.path.insert(0, '/app')
from utils import lug_quantity as lq  # noqa: E402

router = APIRouter(prefix="/cable-schedule/lug", tags=["Cable Lug Quantity"])
lug_cache: dict = {}
_jobs: dict = {}
_lock = threading.Lock()
_TTL = 3600
logger = logging.getLogger("iez.lug")
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


def _run(data: bytes, name: str, rules, overrides, od_data, gland_cfg, progress=None):
    out, r = lq.analyze(data, rules, overrides, od_data, gland_cfg, progress)
    return out, lq.to_workbook(out, r, name)


@router.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    rules: Optional[str] = Form(None),
    overrides: Optional[str] = Form(None),
    od_data: Optional[str] = Form(None),
    gland: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    """Synchronous analysis (used by the complete package and small schedules). The screen uses /start + /job for the live preview."""
    data = await _read(file)
    try:
        out, xlsx = _run(data, file.filename or "uploaded cable schedule", _json(rules, "rules"), _json(overrides, "overrides"), _json(od_data, "cable OD data"), _json(gland, "gland settings"))
    except lq.GlandError as e:
        _bad(str(e))
    lug_cache[f"{current_user.id}_lug"] = {"bytes": xlsx, "filename": "Cable_Lug_Quantity_Report.xlsx"}
    out["filename"] = "Cable_Lug_Quantity_Report.xlsx"
    return out


def _job_run(job_id: str, user_key: str, data: bytes, name: str, rules, overrides, od_data, gland_cfg):
    def progress(p):
        with _lock:
            _jobs.setdefault(job_id, {}).update(stage=p["stage"], live=p)
    try:
        with _lock:
            _jobs[job_id]["stage"] = "Reading the cable schedule"
        out, xlsx = _run(data, name, rules, overrides, od_data, gland_cfg, progress)
        lug_cache[user_key] = {"bytes": xlsx, "filename": "Cable_Lug_Quantity_Report.xlsx"}
        out["filename"] = "Cable_Lug_Quantity_Report.xlsx"
        with _lock:
            _jobs[job_id].update(status="done", stage="Done", result=out)
    except lq.GlandError as e:
        with _lock:
            _jobs[job_id].update(status="error", error=str(e))
    except Exception as e:                                          # never leave the page waiting
        logger.exception("Lug job %s failed", job_id[:8])
        with _lock:
            _jobs[job_id].update(status="error", error=f"The cable schedule could not be analysed: {e}")


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
async def start(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    rules: Optional[str] = Form(None),
    overrides: Optional[str] = Form(None),
    od_data: Optional[str] = Form(None),
    gland: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    """Starts the analysis and returns at once; poll /job/{id} for the live extraction table, live errors and the final result."""
    data = await _read(file)
    parsed = (_json(rules, "rules"), _json(overrides, "overrides"), _json(od_data, "cable OD data"), _json(gland, "gland settings"))
    try:
        lq.Rules.from_dict(parsed[0])
    except lq.GlandError as e:
        _bad(str(e))
    job_id = uuid.uuid4().hex
    now = time.time()
    with _lock:
        for k in [k for k, v in _jobs.items() if now - v.get("created", now) > _TTL]:
            _jobs.pop(k, None)
        _jobs[job_id] = {"status": "processing", "created": now, "stage": "Queued", "user": current_user.username}
    background_tasks.add_task(_job_run, job_id, f"{current_user.id}_lug", data, file.filename or "uploaded cable schedule", *parsed)
    return {"job_id": job_id, "status": "processing"}


@router.get("/job/{job_id}")
async def job(job_id: str, current_user: User = Depends(get_current_user)):
    with _lock:
        j = dict(_jobs.get(job_id) or {})
    if not j or j.get("user") != current_user.username:
        _bad("This analysis job was not found. Please analyse again.", status.HTTP_404_NOT_FOUND)
    out = {"status": j["status"], "stage": j.get("stage", ""), "live": j.get("live"), "elapsed": round(time.time() - j["created"], 1)}
    if j["status"] == "done":
        out["result"] = j["result"]
    if j["status"] == "error":
        out["error"] = j.get("error", "Analysis failed.")
    return out


@router.get("/download")
async def download(current_user: User = Depends(get_current_user)):
    cached = lug_cache.get(f"{current_user.id}_lug")
    if not cached:
        _bad("No lug report found. Please generate it first.", status.HTTP_404_NOT_FOUND)
    return StreamingResponse(io.BytesIO(cached["bytes"]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={cached['filename']}"})
