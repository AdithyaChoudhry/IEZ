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
    input_type: str = "text"          # "iodb" | "dropdown" | "text"
    options: list[str] = []
    mandatory: bool = False


class DatasheetInfoModel(BaseModel):
    sheet: str
    eg_sheet: str | None
    title: str
    annexure_sheet: str | None = None      # tag-wise annexure referenced by the datasheet (consolidated format)
    annexure_capacity: int = 0
    annexure_columns: int = 0
    missing_annexures: list[str] = []


class AnalyzeResponse(BaseModel):
    datasheets: list[DatasheetInfoModel]
    instrument_types: list[str]
    message: str


class InstrumentTypesResponse(BaseModel):
    instrument_types: list[str]
    count: int


class DatasheetsResponse(BaseModel):
    datasheets: list[DatasheetInfoModel]


class FieldsResponse(BaseModel):
    datasheet: str
    title: str
    fields: list[FieldSpecModel]
    annexure_sheet: str | None = None
    annexure_capacity: int = 0


class TagsResponse(BaseModel):
    instrument_type: str
    tags: list[str]
    count: int


class GenerateJobResponse(BaseModel):
    job_id: str
    status: str


class FailedTag(BaseModel):
    tag: str
    reason: str


class GenerateResult(BaseModel):
    filename: str
    tag_count: int                 # datasheets actually generated
    message: str
    requested_count: int = 0       # tags the user selected
    failed_tags: list[FailedTag] = []
    format: str = "INDIVIDUAL"     # INDIVIDUAL | CONSOLIDATED
    approval_id: int | None = None


class GenerateStatusResponse(BaseModel):
    job_id: str
    status: str  # "processing" | "done" | "error"
    result: GenerateResult | None = None
    error: str | None = None


class ExtractedField(BaseModel):
    label: str
    value: str
    confidence: float
    snippet: str = ""


class ExtractSpecResponse(BaseModel):
    label: str
    extracted_value: str
    confidence: float  # 0.0 – 1.0
    raw_snippet: str
    error: str | None = None
    fields: list[ExtractedField] = []      # per-field results when several labels are requested
    text_chars: int = 0                    # how much tender text was read


class VendorMatch(BaseModel):
    vendor: str
    model: str
    match_pct: float
    strengths: list[str]
    gaps: list[str]


class VendorRecommendResponse(BaseModel):
    instrument_type: str
    vendors: list[VendorMatch]
    recommended: str  # vendor name of top match
