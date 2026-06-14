"""
Cover Sheet Generator router - smart document control / revision cover sheets
with interactive preview and image/format editing.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
import io
import json

from ..deps import get_current_user
from ..auth.models import User
from ..models.coversheet import (
    CoverSheetRequest,
    CoverSheetPreviewRequest,
    CoverSheetResponse,
    CoverSheetPreviewResponse,
)

import sys
sys.path.insert(0, '/app')
from utils.coversheet_generator import build_preview, generate_cover_sheet


router = APIRouter(prefix="/coversheet", tags=["Cover Sheet"])

# Store generated files temporarily (in production, use S3 or similar)
coversheet_cache: dict = {}

_IMAGE_KEYS = [
    "client_logo",
    "pmc_logo",
    "wabag_logo",
    "prepared_signature",
    "checked_signature",
    "approved_signature",
]


async def _read_images(
    client_logo, pmc_logo, wabag_logo,
    prepared_signature, checked_signature, approved_signature,
) -> dict:
    files = {
        "client_logo": client_logo,
        "pmc_logo": pmc_logo,
        "wabag_logo": wabag_logo,
        "prepared_signature": prepared_signature,
        "checked_signature": checked_signature,
        "approved_signature": approved_signature,
    }
    result = {}
    for key, f in files.items():
        if f is not None:
            result[key] = await f.read()
    return result


@router.post("/preview", response_model=CoverSheetPreviewResponse)
async def preview(
    data: str = Form(...),  # JSON-encoded CoverSheetPreviewRequest
    client_logo: UploadFile | None = File(None),
    pmc_logo: UploadFile | None = File(None),
    wabag_logo: UploadFile | None = File(None),
    prepared_signature: UploadFile | None = File(None),
    checked_signature: UploadFile | None = File(None),
    approved_signature: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
):
    """
    Build a preview of the cover sheet: filled-in grid (cells, styles,
    merges, sizing) plus image overlay positions, before final generation.
    """
    try:
        payload = CoverSheetPreviewRequest(**json.loads(data))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request data: {str(e)}"
        )

    uploaded_images = await _read_images(
        client_logo, pmc_logo, wabag_logo,
        prepared_signature, checked_signature, approved_signature,
    )

    result, err = build_preview(
        project_info=payload.project_info.model_dump(),
        revisions=[r.model_dump() for r in payload.revisions],
        uploaded_images=uploaded_images,
    )

    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    return CoverSheetPreviewResponse(**result)


@router.post("/generate", response_model=CoverSheetResponse)
async def generate(
    data: str = Form(...),  # JSON-encoded CoverSheetRequest
    client_logo: UploadFile | None = File(None),
    pmc_logo: UploadFile | None = File(None),
    wabag_logo: UploadFile | None = File(None),
    prepared_signature: UploadFile | None = File(None),
    checked_signature: UploadFile | None = File(None),
    approved_signature: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
):
    """
    Generate the final cover sheet from project information, revision
    history, image placements, and cell formatting overrides.
    """
    try:
        payload = CoverSheetRequest(**json.loads(data))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request data: {str(e)}"
        )

    uploaded_images = await _read_images(
        client_logo, pmc_logo, wabag_logo,
        prepared_signature, checked_signature, approved_signature,
    )

    images = {}
    for key in _IMAGE_KEYS:
        entry = {}
        if key in uploaded_images:
            entry["bytes"] = uploaded_images[key]
        if key in payload.image_placements:
            entry["placement"] = payload.image_placements[key].model_dump()
        if entry:
            images[key] = entry

    out_bytes, filename, err = generate_cover_sheet(
        project_info=payload.project_info.model_dump(),
        revisions=[r.model_dump() for r in payload.revisions],
        images=images,
        cell_overrides=payload.cell_overrides,
    )

    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    cache_key = f"{current_user.id}_coversheet"
    coversheet_cache[cache_key] = {"bytes": out_bytes, "filename": filename}

    return CoverSheetResponse(filename=filename, message="Cover sheet generated successfully")


@router.get("/download")
async def download(current_user: User = Depends(get_current_user)):
    """Download the generated cover sheet."""
    cache_key = f"{current_user.id}_coversheet"
    cached = coversheet_cache.get(cache_key)

    if not cached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No cover sheet found. Please generate one first."
        )

    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={cached['filename']}"}
    )
