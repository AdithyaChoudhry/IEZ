"""
Loop Wiring Generator router.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
import io
import uuid
import pandas as pd

from ..deps import get_current_user
from ..auth.models import User
from ..models.loop_wiring import (
    LoopWiringPreviewResponse,
    LoopWiringGenerateResponse,
    LoopWiringJobResponse,
    LoopWiringStatusResponse,
)

# Import existing business logic
import sys
sys.path.insert(0, '/app')
from utils.file_handler import read_loop_wiring_input, load_workbook_from_upload
from utils.generators import generate_loop_wiring as _generate_loop_wiring


router = APIRouter(prefix="/loop-wiring", tags=["Loop Wiring"])

loop_wiring_cache: dict = {}
loop_wiring_jobs: dict = {}


def _find_tag_column(df: pd.DataFrame) -> str | None:
    cols_lower = {str(c).strip().lower(): c for c in df.columns}
    for key in ("tag number", "tag no", "tag_no", "tag_number", "tag_nummber", "tag"):
        if key in cols_lower:
            return cols_lower[key]
    for c in df.columns:
        if "tag" in str(c).strip().lower():
            return c
    return None


@router.post("/preview", response_model=LoopWiringPreviewResponse)
async def preview_loop_wiring(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Read the Loop Wiring input file and return the unique tags + a row preview."""
    file_bytes = await file.read()
    df, err = read_loop_wiring_input(io.BytesIO(file_bytes))

    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    tag_col = _find_tag_column(df)
    if tag_col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No 'Tag Number' column found in Loop Wiring input.",
        )

    tags = df[tag_col].dropna().astype(str).str.strip().unique().tolist()

    preview_df = df.head(20).astype(object).where(pd.notnull(df.head(20)), None)

    return LoopWiringPreviewResponse(
        tags=tags,
        count=len(tags),
        preview=preview_df.to_dict(orient="records"),
    )


def _run_generate_job(
    job_id: str,
    loop_input_bytes: bytes,
    template_bytes: bytes,
    user_id: int,
):
    """Run loop wiring generation in the background and store the result/status."""
    try:
        df, err = read_loop_wiring_input(io.BytesIO(loop_input_bytes))
        if err:
            loop_wiring_jobs[job_id] = {"status": "error", "error": err}
            return

        tag_col = _find_tag_column(df)
        sheet_count = len(df[tag_col].dropna().astype(str).str.strip().unique()) if tag_col else 0

        wb, tmpl_buf, err = load_workbook_from_upload(io.BytesIO(template_bytes))
        if err:
            loop_wiring_jobs[job_id] = {"status": "error", "error": f"Failed to load Loop Wiring template: {err}"}
            return

        tmpl_buf.seek(0)
        tmpl_bytes = tmpl_buf.read()

        out_bytes, filename, err = _generate_loop_wiring(df, wb, template_bytes=tmpl_bytes)
        if err:
            loop_wiring_jobs[job_id] = {"status": "error", "error": err}
            return

        cache_key = f"{user_id}_loop_wiring"
        loop_wiring_cache[cache_key] = {"bytes": out_bytes, "filename": filename}

        loop_wiring_jobs[job_id] = {
            "status": "done",
            "result": LoopWiringGenerateResponse(
                filename=filename,
                message=f"Loop Wiring generated successfully ({sheet_count} sheet(s))",
                sheet_count=sheet_count,
            ),
        }
    except Exception as exc:
        loop_wiring_jobs[job_id] = {"status": "error", "error": str(exc)}


@router.post("/generate", response_model=LoopWiringJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_loop_wiring(
    background_tasks: BackgroundTasks,
    loop_input_file: UploadFile = File(...),
    template_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Kick off Loop Wiring generation. Generation runs in the background —
    poll GET /loop-wiring/generate/status/{job_id} for the result.
    """
    loop_input_bytes = await loop_input_file.read()
    template_bytes = await template_file.read()

    job_id = str(uuid.uuid4())
    loop_wiring_jobs[job_id] = {"status": "processing"}

    background_tasks.add_task(
        _run_generate_job,
        job_id,
        loop_input_bytes,
        template_bytes,
        current_user.id,
    )

    return LoopWiringJobResponse(job_id=job_id, status="processing")


@router.get("/generate/status/{job_id}", response_model=LoopWiringStatusResponse)
async def get_generate_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Poll the status/result of a loop wiring generation job."""
    job = loop_wiring_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation job not found"
        )

    return LoopWiringStatusResponse(
        job_id=job_id,
        status=job["status"],
        result=job.get("result"),
        error=job.get("error"),
    )


@router.get("/download")
async def download_loop_wiring(current_user: User = Depends(get_current_user)):
    cache_key = f"{current_user.id}_loop_wiring"
    cached = loop_wiring_cache.get(cache_key)

    if not cached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No loop wiring output found. Please generate it first.",
        )

    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={cached['filename']}"},
    )
