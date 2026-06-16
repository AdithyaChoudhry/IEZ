"""
Pydantic models for the SOP-driven interactive Datasheet Generator.
"""
from pydantic import BaseModel


class FieldSpecModel(BaseModel):
    section: str
    label: str
    row: int
    value_cols: list[int]
    sub_labels: list[str]
    source: str            # "iodb" | "predefined"
    defaults: list[str]
    source_note: str
    color: str             # yellow | red | green | none | other


class DatasheetInfoModel(BaseModel):
    sheet: str
    eg_sheet: str | None
    title: str


class AnalyzeResponse(BaseModel):
    datasheets: list[DatasheetInfoModel]
    instrument_types: list[str]
    message: str


class FieldsResponse(BaseModel):
    datasheet: str
    title: str
    fields: list[FieldSpecModel]


class TagsResponse(BaseModel):
    instrument_type: str
    tags: list[str]
    count: int
