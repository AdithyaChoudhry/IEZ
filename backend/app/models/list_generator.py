"""
Pydantic models shared by the Instrument List and I/O List generators.
"""
from pydantic import BaseModel
from typing import Dict, List, Any, Optional


class ListAnalyzeResponse(BaseModel):
    columns: List[str]
    unique_values: Dict[str, List[str]]
    preview: List[Dict[str, Any]]
    total_rows: int = 0
    # Default column selection / filters for this list (an initial state, never locked).
    defaults: Optional[Dict[str, Any]] = None


class ListGenerateResponse(BaseModel):
    filename: str
    message: str
    # Set when a project_id was supplied: result of registering the output.
    registry: Optional[Dict[str, Any]] = None
    # I/O List output option and the sheets the generated workbook actually contains (read from the output file).
    output_mode: Optional[str] = None
    sheets: Optional[List[str]] = None
    # Centralised cover sheet applied to the deliverable (status, MDL document, revision, draft) - see routers/deliverables.py
    cover: Optional[Dict[str, Any]] = None
    # Standard I/O List document: IO_BASIS classes / review items, printed pages per section, warnings (see utils/io_list_builder.py)
    basis: Optional[Dict[str, Any]] = None


class BasisPreviewResponse(BaseModel):
    classes: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {}
    error: str = ""


class CompositionSheet(BaseModel):
    name: str
    hidden: bool = False
    kind: str                      # "template" | "generated" | "summary"


class CompositionResponse(BaseModel):
    output_mode: str
    sheets: List[CompositionSheet]


class ListGenerateRequest(BaseModel):
    selected_columns: List[str]
    filters: Optional[Dict[str, List[str]]] = None
