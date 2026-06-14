"""
Data Sheet Generator router - datasheet generation with fuzzy matching.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from typing import List, Optional
import io
import json

from ..deps import get_current_user
from ..auth.models import User
from ..models.datasheet import (
    DataSheetRequest,
    DataSheetResponse,
    MappingLogEntry,
    TagsResponse,
)

# Import existing business logic
import sys
sys.path.insert(0, '/app')
from utils.template_processor import (
    get_ai_tags_from_iodb,
    process_datasheets_v2,
)


router = APIRouter(prefix="/datasheet", tags=["Data Sheet"])


# Store generated files temporarily (in production, use S3 or similar)
datasheet_cache: dict = {}


@router.post("/tags", response_model=TagsResponse)
async def get_available_tags(
    file: UploadFile = File(...),
    two_row_header: bool = Form(True),
    current_user: User = Depends(get_current_user),
):
    """
    Extract AI signal tags from IODB file.
    
    Args:
        file: IODB Excel file
        two_row_header: Whether to use two-row combined header
        current_user: Authenticated user
        
    Returns:
        List of AI tags found in the IODB
    """
    file_bytes = await file.read()
    iodb_buffer = io.BytesIO(file_bytes)
    
    tags, err = get_ai_tags_from_iodb(iodb_buffer, two_row_header=two_row_header)
    
    if err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err
        )
    
    if not tags:
        return TagsResponse(
            tags=[],
            count=0,
            message="No AI-type tags found in the IODB. Check the 'SIGNAL I/O TYPE' column."
        )
    
    return TagsResponse(
        tags=tags,
        count=len(tags),
        message=f"Found {len(tags)} AI signal tags"
    )


@router.post("/generate", response_model=DataSheetResponse)
async def generate_datasheets(
    iodb_file: UploadFile = File(...),
    template_file: UploadFile = File(...),
    selected_tags: str = Form(...),  # JSON string of tag list
    two_row_header: bool = Form(True),
    fuzzy_threshold: int = Form(70),
    current_user: User = Depends(get_current_user),
):
    """
    Generate datasheets for selected tags.
    
    Args:
        iodb_file: IODB Excel file
        template_file: Datasheet template Excel file
        selected_tags: JSON array of tag names
        two_row_header: Whether to use two-row combined header
        fuzzy_threshold: Fuzzy matching threshold (30-100)
        current_user: Authenticated user
        
    Returns:
        Success message with filename and mapping logs
    """
    # Parse selected tags
    try:
        tags_list = json.loads(selected_tags)
        if not tags_list:
            raise ValueError("Empty tags list")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid selected_tags format: {str(e)}"
        )
    
    # Read file bytes
    iodb_bytes = await iodb_file.read()
    template_bytes = await template_file.read()
    
    iodb_buffer = io.BytesIO(iodb_bytes)
    template_buffer = io.BytesIO(template_bytes)
    
    # Progress tracking
    progress_data = {"current": 0, "total": len(tags_list)}
    
    def progress_callback(current: int, total: int):
        progress_data["current"] = current
        progress_data["total"] = total
        # In production, emit WebSocket event here
    
    # Process datasheets
    out_bytes, filename, err, mapping_logs = process_datasheets_v2(
        iodb_file=iodb_buffer,
        template_file=template_buffer,
        selected_tags=tags_list,
        two_row_header=two_row_header,
        fuzzy_threshold=fuzzy_threshold,
        progress_callback=progress_callback,
    )
    
    if err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err
        )
    
    # Store result in cache
    cache_key = f"{current_user.id}_datasheet"
    datasheet_cache[cache_key] = {
        "bytes": out_bytes,
        "filename": filename,
    }
    
    # Convert mapping logs to response format
    log_entries = [
        MappingLogEntry(**log) for log in mapping_logs
    ]
    
    return DataSheetResponse(
        filename=filename,
        tag_count=len(tags_list),
        mapping_logs=log_entries,
        message=f"Successfully generated {len(tags_list)} datasheets"
    )


@router.get("/download")
async def download_datasheets(current_user: User = Depends(get_current_user)):
    """Download the generated datasheets ZIP file."""
    cache_key = f"{current_user.id}_datasheet"
    cached = datasheet_cache.get(cache_key)
    
    if not cached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No datasheet results found. Please generate datasheets first."
        )
    
    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={cached['filename']}"
        }
    )
