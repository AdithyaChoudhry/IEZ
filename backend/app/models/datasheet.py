"""
Pydantic models for Data Sheet Generator module.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class DataSheetRequest(BaseModel):
    """Request to generate datasheets."""
    selected_tags: List[str] = Field(..., min_items=1)
    two_row_header: bool = True
    fuzzy_threshold: int = Field(default=70, ge=30, le=100)


class MappingLogEntry(BaseModel):
    """Single entry in the mapping log."""
    tag: str
    heading: str
    iodb_col: Optional[str]
    score: Optional[float]
    value: Optional[str]
    status: str  # "MATCHED" or "UNMATCHED"


class DataSheetResponse(BaseModel):
    """Response from datasheet generation."""
    filename: str
    tag_count: int
    mapping_logs: List[MappingLogEntry]
    message: str


class TagsResponse(BaseModel):
    """Response with available AI tags."""
    tags: List[str]
    count: int
    message: Optional[str] = None
