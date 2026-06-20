"""
Pydantic models for Smart Cover Sheet Generator module.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any


class RevisionEntry(BaseModel):
    """Single revision history row, ordered oldest-first in the request."""
    rev_no: str
    date: str
    description: str
    prepared_by: str = ""
    checked_by: str = ""
    approved_by: str = ""


class ProjectInfo(BaseModel):
    """Document control / project information fields."""
    client: str = ""
    pmc: str = ""
    contractor: str = ""
    project_description: str = ""
    doc_title_short: str = ""
    doc_title_full: str = ""
    job_no: str = ""
    unit_no: str = ""
    project_no: str = ""
    doc_code: str = ""
    serial_no: str = ""
    page_no: str = ""
    doc_class: str = ""
    discipline: str = ""


class ImagePlacement(BaseModel):
    """Pixel position/size of an image overlay on the cover sheet canvas."""
    x: float
    y: float
    width: float
    height: float


class CoverSheetRequest(BaseModel):
    """Request body for cover sheet generation (sent as JSON form field)."""
    project_info: ProjectInfo
    revisions: List[RevisionEntry] = Field(..., min_items=1, max_items=7)
    image_placements: Dict[str, ImagePlacement] = Field(default_factory=dict)
    cell_overrides: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    # custom image placements keyed by image id
    custom_image_placements: Dict[str, Dict[str, float]] = Field(default_factory=dict)


class CoverSheetPreviewRequest(BaseModel):
    """Request body for cover sheet preview generation."""
    project_info: ProjectInfo
    revisions: List[RevisionEntry] = Field(..., min_items=1, max_items=7)


class CoverSheetResponse(BaseModel):
    """Response from cover sheet generation."""
    filename: str
    message: str


class CoverSheetPreviewResponse(BaseModel):
    """Response from cover sheet preview generation."""
    layout: Dict[str, Any]
    images: Dict[str, Any]
