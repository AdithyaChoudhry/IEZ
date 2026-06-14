"""
Pydantic models shared by the Instrument List and I/O List generators.
"""
from pydantic import BaseModel
from typing import Dict, List, Any, Optional


class ListAnalyzeResponse(BaseModel):
    columns: List[str]
    unique_values: Dict[str, List[str]]
    preview: List[Dict[str, Any]]


class ListGenerateResponse(BaseModel):
    filename: str
    message: str


class ListGenerateRequest(BaseModel):
    selected_columns: List[str]
    filters: Optional[Dict[str, List[str]]] = None
