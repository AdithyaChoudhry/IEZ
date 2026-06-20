"""
Cover Sheet Generator router — fully customizable cover sheet builder.
Supports:
  - Custom template upload (or falls back to default WABAG template)
  - 6 fixed named image slots + unlimited extra images (extra_images[])
  - Cell value overrides via cell_overrides JSON ("value" key)
  - Image placement / resize overrides
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from typing import List, Optional
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

coversheet_cache: dict = {}

_FIXED_IMAGE_KEYS = [
    "client_logo", "pmc_logo", "wabag_logo",
    "prepared_signature", "checked_signature", "approved_signature",
]


async def _read_fixed_images(
    client_logo, pmc_logo, wabag_logo,
    prepared_signature, checked_signature, approved_signature,
) -> dict:
    files = {
        "client_logo": client_logo, "pmc_logo": pmc_logo, "wabag_logo": wabag_logo,
        "prepared_signature": prepared_signature, "checked_signature": checked_signature,
        "approved_signature": approved_signature,
    }
    return {k: await f.read() for k, f in files.items() if f is not None}


@router.post("/preview", response_model=CoverSheetPreviewResponse)
async def preview(
    data: str = Form(...),
    template_file: Optional[UploadFile] = File(None),
    client_logo: Optional[UploadFile] = File(None),
    pmc_logo: Optional[UploadFile] = File(None),
    wabag_logo: Optional[UploadFile] = File(None),
    prepared_signature: Optional[UploadFile] = File(None),
    checked_signature: Optional[UploadFile] = File(None),
    approved_signature: Optional[UploadFile] = File(None),
    extra_images: List[UploadFile] = File(default=[]),
    extra_image_meta: str = Form(default="[]"),
    current_user: User = Depends(get_current_user),
):
    """Build an interactive preview: cell grid + image overlay positions."""
    try:
        payload = CoverSheetPreviewRequest(**json.loads(data))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request data: {e}")

    template_bytes = await template_file.read() if template_file else None

    uploaded_images = await _read_fixed_images(
        client_logo, pmc_logo, wabag_logo,
        prepared_signature, checked_signature, approved_signature,
    )

    # Attach extra images keyed by their metadata id
    try:
        meta_list = json.loads(extra_image_meta)
    except Exception:
        meta_list = []
    for idx, uf in enumerate(extra_images):
        img_id = meta_list[idx]["id"] if idx < len(meta_list) else f"extra_{idx}"
        uploaded_images[img_id] = await uf.read()

    result, err = build_preview(
        project_info=payload.project_info.model_dump(),
        revisions=[r.model_dump() for r in payload.revisions],
        uploaded_images=uploaded_images,
        template_bytes=template_bytes,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    return CoverSheetPreviewResponse(**result)


@router.post("/generate", response_model=CoverSheetResponse)
async def generate(
    data: str = Form(...),
    template_file: Optional[UploadFile] = File(None),
    client_logo: Optional[UploadFile] = File(None),
    pmc_logo: Optional[UploadFile] = File(None),
    wabag_logo: Optional[UploadFile] = File(None),
    prepared_signature: Optional[UploadFile] = File(None),
    checked_signature: Optional[UploadFile] = File(None),
    approved_signature: Optional[UploadFile] = File(None),
    extra_images: List[UploadFile] = File(default=[]),
    extra_image_meta: str = Form(default="[]"),
    current_user: User = Depends(get_current_user),
):
    """Generate the final cover sheet with all overrides applied."""
    try:
        payload = CoverSheetRequest(**json.loads(data))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request data: {e}")

    template_bytes = await template_file.read() if template_file else None

    uploaded_images = await _read_fixed_images(
        client_logo, pmc_logo, wabag_logo,
        prepared_signature, checked_signature, approved_signature,
    )

    # Build fixed image entries with placement data
    images = {}
    for key in _FIXED_IMAGE_KEYS:
        entry = {}
        if key in uploaded_images:
            entry["bytes"] = uploaded_images[key]
        if key in payload.image_placements:
            entry["placement"] = payload.image_placements[key].model_dump()
        if entry:
            images[key] = entry

    # Extra custom images
    try:
        meta_list = json.loads(extra_image_meta)
    except Exception:
        meta_list = []
    custom_placements = getattr(payload, "custom_image_placements", {}) or {}
    for idx, uf in enumerate(extra_images):
        img_id = meta_list[idx]["id"] if idx < len(meta_list) else f"extra_{idx}"
        img_bytes = await uf.read()
        entry = {"bytes": img_bytes}
        if img_id in custom_placements:
            p = custom_placements[img_id]
            entry["placement"] = p if isinstance(p, dict) else p.model_dump()
        images[img_id] = entry

    out_bytes, filename, err = generate_cover_sheet(
        project_info=payload.project_info.model_dump(),
        revisions=[r.model_dump() for r in payload.revisions],
        images=images,
        cell_overrides=payload.cell_overrides,
        template_bytes=template_bytes,
        merge_ranges=getattr(payload, "merge_ranges", []) or [],
        unmerge_coords=getattr(payload, "unmerge_coords", []) or [],
        blank_mode=getattr(payload, "blank_mode", False),
        paper_size=getattr(payload, "paper_size", "9"),
        orientation=getattr(payload, "orientation", "portrait"),
        col_width_overrides=getattr(payload, "col_width_overrides", {}) or {},
        row_height_overrides=getattr(payload, "row_height_overrides", {}) or {},
    )
    if err:
        raise HTTPException(status_code=400, detail=err)

    cache_key = f"{current_user.id}_coversheet"
    coversheet_cache[cache_key] = {"bytes": out_bytes, "filename": filename}
    return CoverSheetResponse(filename=filename, message="Cover sheet generated successfully")


@router.get("/download")
async def download(current_user: User = Depends(get_current_user)):
    """Download the last-generated cover sheet for this user."""
    cache_key = f"{current_user.id}_coversheet"
    cached = coversheet_cache.get(cache_key)
    if not cached:
        raise HTTPException(status_code=404, detail="No cover sheet found. Generate one first.")
    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={cached['filename']}"},
    )
