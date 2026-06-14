"""
Cable Schedule Generator router.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
import io

from ..deps import get_current_user
from ..auth.models import User
from ..models.cable_schedule import (
    ColumnsResponse,
    JBSummaryResponse,
    CableScheduleGenerateResponse,
)

# Import existing business logic
import sys
sys.path.insert(0, '/app')
from utils.template_processor import get_iodb_columns, get_jb_summary, process_cable_schedule


router = APIRouter(prefix="/cable-schedule", tags=["Cable Schedule"])

cable_schedule_cache: dict = {}


@router.post("/columns", response_model=ColumnsResponse)
async def get_columns(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Read the IODB file and return its column names for JB/Tag column mapping."""
    file_bytes = await file.read()
    columns, err = get_iodb_columns(io.BytesIO(file_bytes))

    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    return ColumnsResponse(columns=columns)


@router.post("/preview", response_model=JBSummaryResponse)
async def preview_jb_summary(
    file: UploadFile = File(...),
    jb_column: str = Form(...),
    tag_column: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """Return a junction box → tag count summary for the IODB file."""
    file_bytes = await file.read()
    rows, err = get_jb_summary(io.BytesIO(file_bytes), jb_column, tag_column)

    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    return JBSummaryResponse(rows=rows)


@router.post("/generate", response_model=CableScheduleGenerateResponse)
async def generate_cable_schedule(
    iodb_file: UploadFile = File(...),
    template_file: UploadFile = File(...),
    jb_column: str = Form(...),
    tag_column: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    iodb_bytes = await iodb_file.read()
    template_bytes = await template_file.read()

    out_bytes, filename, err = process_cable_schedule(
        io.BytesIO(iodb_bytes),
        io.BytesIO(template_bytes),
        jb_column,
        tag_column,
    )

    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    cache_key = f"{current_user.id}_cable_schedule"
    cable_schedule_cache[cache_key] = {"bytes": out_bytes, "filename": filename}

    return CableScheduleGenerateResponse(filename=filename, message="Cable Schedule generated successfully")


@router.get("/download")
async def download_cable_schedule(current_user: User = Depends(get_current_user)):
    cache_key = f"{current_user.id}_cable_schedule"
    cached = cable_schedule_cache.get(cache_key)

    if not cached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No cable schedule found. Please generate it first.",
        )

    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={cached['filename']}"},
    )
