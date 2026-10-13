"""
Pydantic models for the Cable Schedule generator.
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class ColumnsResponse(BaseModel):
    columns: List[str]


class JBSummaryResponse(BaseModel):
    rows: List[Dict[str, Any]]


class CableScheduleGenerateResponse(BaseModel):
    filename: str
    message: str
    # Set when a project_id was supplied: result of registering the output.
    registry: Optional[Dict[str, Any]] = None
