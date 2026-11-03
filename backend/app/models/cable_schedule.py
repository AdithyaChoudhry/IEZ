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
    output_mode: Optional[str] = None
    sheets: Optional[List[str]] = None


class CompositionSheet(BaseModel):
    name: str
    hidden: bool = False
    kind: str                      # "template" | "generated" | "summary"


class CompositionResponse(BaseModel):
    output_mode: str
    sheets: List[CompositionSheet]
