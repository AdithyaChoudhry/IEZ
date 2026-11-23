"""Pydantic models for the Process Data Requisition generator."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class InstrumentTypeOption(BaseModel):
    key: str
    label: str
    category: str
    subtypes: List[str] = []
    verified_subtypes: List[str] = []      # subtypes ("" = no subtype) that have a verified datasheet profile


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
    subtype: str = ""            # the subtype this record was classified as (when a subtype was selected)
    reason: str = ""             # why a record is unresolved (subtype not established)


class ProcessFieldOption(BaseModel):
    name: str
    header: str
    mandatory: bool = False
    # Added with the verified datasheet profiles - all optional, so existing clients keep working.
    unit: str = ""
    category: str = "process"          # process | additional
    default_selected: bool = False
    source_annexure_label: str = ""
    field_type: str = "text"
    options: List[str] = []


class ProcessProfileResponse(BaseModel):
    instrument_type: str
    subtype: str = ""
    verified: bool = False
    template: str = ""
    sheet: str = ""
    note: str = ""
    fields: List[ProcessFieldOption] = []
    default_fields: List[str] = []


class ProcessDataMatchResponse(BaseModel):
    instrument_type: str
    matched_tags: List[MatchedTag]
    tag_count: int
    identification_columns: List[str]
    process_columns: List[str]
    process_fields: List[ProcessFieldOption] = []
    default_fields: List[str] = []
    warnings: List[str] = []
    # subtype filtering: records of the type whose subtype is not established (NOT in matched_tags) and what was left out
    subtype: str = ""
    unresolved_tags: List[MatchedTag] = []
    excluded_counts: Dict[str, int] = {}


class ProcessDataGenerateResponse(BaseModel):
    filename: str
    message: str
    registry: Optional[Dict[str, Any]] = None
    warnings: List[str] = []


class DetectGroup(BaseModel):
    key: str
    type_key: str
    type_label: str
    subtype: str = ""
    label: str
    needs_review: bool = False
    reason: str = ""
    category: str = ""
    count: int
    tags: List[MatchedTag]


class DetectResponse(BaseModel):
    """All Instrument Types mode: every supported type / subtype found in the IODB."""
    groups: List[DetectGroup]
    types_found: int
    eligible_tags: int
    review_tags: int
    unsupported: List[Dict[str, Any]] = []
    ambiguous: List[Dict[str, Any]] = []
    ambiguous_count: int = 0
    warnings: List[str] = []
