"""
Loop Wiring from the standard I/O Assignment (new, separate from the existing Loop Wiring input-file flow).

    I/O Assignment workbook -> loop template columns (W18:AR18) -> loop type per tag (AI + 2/4 WIRE) -> one sheet per tag

Results are stored in the existing Loop Wiring job / download stores, so the page polls and downloads exactly as before.
"""
from __future__ import annotations

import io
import uuid
from collections import Counter
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from ..auth.models import User
from ..deps import get_current_user
from ..models.loop_wiring import LoopWiringGenerateResponse, LoopWiringJobResponse
from ..services.document_registry import register_safe
from .loop_wiring import loop_wiring_cache, loop_wiring_jobs

import sys
sys.path.insert(0, '/app')
from utils import loop_from_assignment as LA

router = APIRouter(prefix="/loop-wiring/assignment", tags=["Loop Wiring"])

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "loop_wiring"
VARIANTS = {
    "WITH": ("WITH_MARSHALLING_CABINET.xlsx", "Junction box -> marshalling cabinet -> system cabinet"),
    "WITHOUT": ("WITHOUT_MARSHALLING_CABINET.xlsx", "Junction box -> system cabinet (no marshalling cabinet)"),
}
MAX_BYTES = 60 * 1024 * 1024


class AssignmentPreview(BaseModel):
    sheet: str
    rows_read: int
    fed: int
    by_type: dict
    skipped: int
    skipped_reasons: list
    unfed_headers: list
    preview: list


def _template(variant: str, upload: Optional[bytes]) -> bytes:
    if upload:
        return upload
    if variant not in VARIANTS:
        raise HTTPException(status_code=400, detail=f"variant must be one of {', '.join(VARIANTS)}")
    return (TEMPLATE_DIR / VARIANTS[variant][0]).read_bytes()


def _feed(data: bytes, template: bytes):
    try:
        rows, sheet = LA.read_assignment(data)
        return LA.build_loop_input(rows, LA.template_headers(template)), sheet, len(rows)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read the I/O Assignment: {e}")


@router.get("/templates")
def list_templates(current_user: User = Depends(get_current_user)):
    return [{"variant": k, "label": v[1]} for k, v in VARIANTS.items()]


@router.get("/template/{variant}")
def download_template(variant: str, current_user: User = Depends(get_current_user)):
    if variant not in VARIANTS:
        raise HTTPException(status_code=404, detail="Unknown template variant")
    return Response(content=(TEMPLATE_DIR / VARIANTS[variant][0]).read_bytes(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="LOOP WIRING_ template - {variant} MARSHALLING CABINET.xlsx"'})


@router.post("/preview", response_model=AssignmentPreview)
async def preview(
    assignment_file: UploadFile = File(...),
    template_file: Optional[UploadFile] = File(None),
    variant: str = Form("WITH"),
    current_user: User = Depends(get_current_user),
):
    data = await assignment_file.read()
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="The I/O Assignment file is empty or too large.")
    tmpl = _template(variant, await template_file.read() if template_file is not None else None)
    feed, sheet, n = _feed(data, tmpl)
    reasons = Counter(why for _, _, why in feed.skipped)
    return AssignmentPreview(
        sheet=sheet, rows_read=n, fed=len(feed.rows), by_type=dict(Counter(r["LOOP TYPE"] for r in feed.rows)),
        skipped=len(feed.skipped), skipped_reasons=[{"reason": k, "count": v} for k, v in reasons.most_common()],
        unfed_headers=feed.unfed_headers,
        preview=[{k: v for k, v in r.items() if v is not None} for r in feed.rows[:20]],
    )


def _run(job_id: str, data: bytes, filename: str, tmpl: bytes, user_id: int, username: str, project_id: Optional[str]):
    try:
        feed, _, _ = _feed(data, tmpl)
        if not feed.rows:
            raise HTTPException(status_code=400, detail="No tags in this I/O Assignment match a loop type (AI with 2 WIRE or 4 WIRE).")
        out = LA.generate(feed, tmpl)
        loop_wiring_cache[f"{user_id}_loop_wiring"] = {"bytes": out, "filename": "Loop_Wiring.xlsx"}
        registry = register_safe("success", project_id=project_id, module="loop_wiring", user=username, source_bytes=data,
                                 source_filename=filename, output_bytes=out, output_filename="Loop_Wiring.xlsx",
                                 sheet_count=len(feed.rows), template_bytes=tmpl, template_filename="Loop_Wiring_Template.xlsx")
        loop_wiring_jobs[job_id] = {"status": "done", "result": LoopWiringGenerateResponse(
            filename="Loop_Wiring.xlsx", sheet_count=len(feed.rows), registry=registry,
            message=f"Loop Wiring generated from the I/O Assignment ({len(feed.rows)} sheet(s); {len(feed.skipped)} row(s) not mapped)")}
    except HTTPException as e:
        loop_wiring_jobs[job_id] = {"status": "error", "error": e.detail}
    except Exception as e:
        loop_wiring_jobs[job_id] = {"status": "error", "error": f"Loop Wiring generation failed: {e}"}


@router.post("/generate", response_model=LoopWiringJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate(
    background_tasks: BackgroundTasks,
    assignment_file: UploadFile = File(...),
    template_file: Optional[UploadFile] = File(None),
    variant: str = Form("WITH"),
    project_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    """Starts the job; poll GET /loop-wiring/generate/status/{job_id}, then GET /loop-wiring/download (existing endpoints)."""
    data = await assignment_file.read()
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="The I/O Assignment file is empty or too large.")
    tmpl = _template(variant, await template_file.read() if template_file is not None else None)
    job_id = str(uuid.uuid4())
    loop_wiring_jobs[job_id] = {"status": "processing"}
    background_tasks.add_task(_run, job_id, data, assignment_file.filename or "IO_Assignment.xlsx", tmpl, current_user.id,
                              current_user.username, project_id)
    return LoopWiringJobResponse(job_id=job_id, status="processing")
