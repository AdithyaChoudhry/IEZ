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
