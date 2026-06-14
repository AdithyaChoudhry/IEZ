"""
Instrument List Generator router.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from typing import Optional
import io
import json

from ..deps import get_current_user
from ..auth.models import User
from ..models.list_generator import ListAnalyzeResponse, ListGenerateResponse

# Import existing business logic
import sys
sys.path.insert(0, '/app')
from utils.template_processor import get_iodb_preview, process_instrument_list


router = APIRouter(prefix="/instrument-list", tags=["Instrument List"])

instrument_list_cache: dict = {}


@router.post("/analyze", response_model=ListAnalyzeResponse)
async def analyze_iodb(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Read the IODB file and return its columns, unique values, and a preview."""
    file_bytes = await file.read()
    columns, unique_values, preview, err = get_iodb_preview(io.BytesIO(file_bytes))

    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    return ListAnalyzeResponse(columns=columns, unique_values=unique_values, preview=preview)


@router.post("/generate", response_model=ListGenerateResponse)
async def generate_instrument_list(
    iodb_file: UploadFile = File(...),
    template_file: Optional[UploadFile] = File(None),
    selected_columns: str = Form(...),  # JSON array of column names
    filters: str = Form("{}"),  # JSON object of {column: [values]}
    current_user: User = Depends(get_current_user),
):
    try:
        columns_list = json.loads(selected_columns)
        if not columns_list:
            raise ValueError("Empty column selection")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid selected_columns format: {e}",
        )

    try:
        filters_dict = json.loads(filters) if filters else {}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid filters format: {e}",
        )

    iodb_bytes = await iodb_file.read()
    template_buffer = None
    if template_file is not None:
        template_bytes = await template_file.read()
        template_buffer = io.BytesIO(template_bytes)

    out_bytes, filename, err = process_instrument_list(
        io.BytesIO(iodb_bytes),
        columns_list,
        filters=filters_dict if filters_dict else None,
        template_file=template_buffer,
    )

    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    cache_key = f"{current_user.id}_instrument_list"
    instrument_list_cache[cache_key] = {"bytes": out_bytes, "filename": filename}

    return ListGenerateResponse(filename=filename, message="Instrument List generated successfully")


@router.get("/download")
async def download_instrument_list(current_user: User = Depends(get_current_user)):
    cache_key = f"{current_user.id}_instrument_list"
    cached = instrument_list_cache.get(cache_key)

    if not cached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No instrument list found. Please generate it first.",
        )

    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={cached['filename']}"},
    )
