"""Pydantic models for the Process Data Requisition generator."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class InstrumentTypeOption(BaseModel):
    key: str
    label: str
    category: str
    subtypes: List[str] = []


class InstrumentTypesResponse(BaseModel):
    instrument_types: List[InstrumentTypeOption]


class MatchedTag(BaseModel):
    tag_no: str
    equipment_description: str = ""
    pid_no: str = ""
    service: str = ""
    equipment_no: str = ""
    line: str = ""
    line_size: str = ""
    row_index: int


class ProcessDataMatchResponse(BaseModel):
    instrument_type: str
    matched_tags: List[MatchedTag]
    tag_count: int
    identification_columns: List[str]
    process_columns: List[str]
    warnings: List[str] = []


class ProcessDataGenerateResponse(BaseModel):
    filename: str
    message: str
    registry: Optional[Dict[str, Any]] = None
