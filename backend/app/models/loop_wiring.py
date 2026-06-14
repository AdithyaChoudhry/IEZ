"""
Pydantic models for the Loop Wiring generator.
"""
from pydantic import BaseModel
from typing import List, Dict, Any


class LoopWiringPreviewResponse(BaseModel):
    tags: List[str]
    count: int
    preview: List[Dict[str, Any]]


class LoopWiringGenerateResponse(BaseModel):
    filename: str
    message: str
    sheet_count: int


class LoopWiringJobResponse(BaseModel):
    """Response when a loop wiring generation job is kicked off."""
    job_id: str
    status: str


class LoopWiringStatusResponse(BaseModel):
    """Status/result of an in-progress or completed generation job."""
    job_id: str
    status: str  # "processing" | "done" | "error"
    result: LoopWiringGenerateResponse | None = None
    error: str | None = None
