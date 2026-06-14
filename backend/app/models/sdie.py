"""
Pydantic models for the Smart Datasheet Intelligence Engine (SDIE).
"""
from pydantic import BaseModel


class ExtractedSpec(BaseModel):
    raw_label: str
    value: str
    canonical_field: str | None
    match_score: float
    confidence: float  # OCR confidence 0-100
    page: int


class ExtractionResponse(BaseModel):
    specs: list[ExtractedSpec]
    page_count: int
    message: str


class ExtractionJobResponse(BaseModel):
    """Response when an extraction job is kicked off."""
    job_id: str
    status: str


class ExtractionStatusResponse(BaseModel):
    """Status/result of an in-progress or completed extraction job."""
    job_id: str
    status: str  # "processing" | "done" | "error"
    result: ExtractionResponse | None = None
    error: str | None = None


class MappingLogEntry(BaseModel):
    heading: str
    canonical_field: str | None
    score: float
    value: str
    status: str  # "MATCHED" | "UNMATCHED"


class GenerateResponse(BaseModel):
    specs: list[ExtractedSpec]
    page_count: int
    mapping_log: list[MappingLogEntry]
    filename: str
    message: str


class GenerateJobResponse(BaseModel):
    """Response when a datasheet generation job is kicked off."""
    job_id: str
    status: str


class GenerateStatusResponse(BaseModel):
    """Status/result of an in-progress or completed generation job."""
    job_id: str
    status: str  # "processing" | "done" | "error"
    result: GenerateResponse | None = None
    error: str | None = None
