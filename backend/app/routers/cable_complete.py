"""
Cable Schedule Complete: ONE IODB -> one workbook (Cable Schedule + I/O Summary + Gland Quantity + Cable Lug Quantity).

An orchestration layer over the existing engines (utils.cable_complete). Generation runs as a background job that the
page polls, so the stages shown are the real ones and a slow generation never hits a proxy timeout.
"""
import io
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
from utils import cable_complete as cc  # noqa: E402

logger = logging.getLogger("iez.cable_complete")
router = APIRouter(prefix="/cable-schedule/complete", tags=["Cable Schedule Complete"])
_jobs: dict = {}
_lock = threading.Lock()
_TTL = 3600
complete_cache: dict = {}
MAX_BYTES = 60 * 1024 * 1024


def _bad(msg: str, code: int = status.HTTP_400_BAD_REQUEST):
    raise HTTPException(status_code=code, detail=msg)


async def _read(upload: UploadFile, what: str) -> bytes:
    data = await upload.read()
    if not data:
        _bad(f"The {what} file is empty.")
    if len(data) > MAX_BYTES:
        _bad(f"The {what} file is larger than 60 MB.", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    if not (upload.filename or "").lower().endswith((".xlsx", ".xlsm")):
        _bad(f"The {what} must be an Excel .xlsx file.")
    return data


@router.get("/status")
def info(current_user: User = Depends(get_current_user)):
    """Whether a built-in Cable Schedule template is installed (otherwise the page asks for one)."""
    return {"builtin_template": cc.builtin_template() is not None, "stages": [{"key": k, "label": l} for k, l in cc.STAGES]}


@router.post("/validate")
async def validate(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Immediate IODB validation: counts, mandatory fields, status. Nothing is generated."""
    data = await _read(file, "IODB")
    v = cc.validate(data)
    out = cc._public_validation(v)
    out["ok"] = v["ok"]
    out["file_name"] = file.filename
    return out


def _set(job_id: str, **kw):
    with _lock:
        _jobs.setdefault(job_id, {}).update(kw)


def _run(job_id: str, user_key: str, iodb: bytes, name: str, template: Optional[bytes]):
    stages: dict = {}

    def progress(key, state, message):
        stages[key] = {"state": state, "message": message}
        _set(job_id, stages=dict(stages), stage=key)

    try:
        res = cc.run(iodb, name, template, progress)
        complete_cache[user_key] = {"bytes": res.pop("workbook"), "filename": "Cable_Schedule_Complete.xlsx"}
        _set(job_id, status="done", result=res, stages=dict(stages))
    except cc.CompleteError as exc:
        _set(job_id, status="error", error=str(exc), stages=dict(stages))
    except Exception as exc:                                        # never leave the page waiting
        logger.exception("Cable Schedule Complete job %s failed", job_id[:8])
        _set(job_id, status="error", error=f"The complete package could not be generated: {exc}", stages=dict(stages))


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    template_file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
):
    iodb = await _read(file, "IODB")
    template = await _read(template_file, "Cable Schedule template") if template_file is not None else None
    if template is None and cc.builtin_template() is None:
        _bad("No Cable Schedule template is installed on the server. Upload the project's Cable Schedule template.")
    job_id = uuid.uuid4().hex
    now = time.time()
    with _lock:
        for k in [k for k, v in _jobs.items() if now - v.get("created", now) > _TTL]:
            _jobs.pop(k, None)
        _jobs[job_id] = {"status": "processing", "created": now, "stages": {}, "user": current_user.username}
    background_tasks.add_task(_run, job_id, f"{current_user.id}_complete", iodb, file.filename or "IODB.xlsx", template)
    return {"job_id": job_id, "status": "processing"}


@router.get("/job/{job_id}")
def job(job_id: str, current_user: User = Depends(get_current_user)):
    with _lock:
        j = dict(_jobs.get(job_id) or {})
    if not j or j.get("user") != current_user.username:
        _bad("This generation job was not found. Please generate again.", status.HTTP_404_NOT_FOUND)
    out = {"status": j["status"], "stages": j.get("stages", {}), "elapsed": round(time.time() - j["created"], 1)}
    if j["status"] == "done":
        out["result"] = j["result"]
    if j["status"] == "error":
        out["error"] = j.get("error", "Generation failed.")
    return out


@router.get("/download")
def download(current_user: User = Depends(get_current_user)):
    cached = complete_cache.get(f"{current_user.id}_complete")
    if not cached:
        _bad("No complete package found. Please generate it first.", status.HTTP_404_NOT_FOUND)
    return StreamingResponse(io.BytesIO(cached["bytes"]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={cached['filename']}"})
