"""Pydantic models for LT Non-Contact Radar Datasheet API."""
from pydantic import BaseModel
from typing import Any


class IódbLookupResponse(BaseModel):
    tag_no: str
    values: dict[str, str]
    missing_fields: list[str]
    error: str | None = None


class TagsResponse(BaseModel):
    tags: list[str]
    count: int


class SpecField(BaseModel):
    id: str
    label: str
    section: str
    color: str           # green | red | grey | violet
    options: list[str] | None = None
    default: str | None = None
    fixed: str | None = None


class SpecsMetaResponse(BaseModel):
    fields: list[SpecField]
    dropdowns: dict[str, list[str]]
    defaults: dict[str, str]


class ValidationResult(BaseModel):
    errors: list[str]
    warnings: list[str]
    passed: bool


class GenerateRequest(BaseModel):
    values: dict[str, Any]


class AiExtractRequest(BaseModel):
    labels: list[str]
    text: str


class AiExtractedField(BaseModel):
    label: str
    field_id: str
    value: str
    confidence: float
    snippet: str


class AiExtractResponse(BaseModel):
    fields: list[AiExtractedField]
    error: str | None = None
