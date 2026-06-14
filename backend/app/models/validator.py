"""
Pydantic models for IODB Validator module.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class ValidationErrorDetail(BaseModel):
    """Individual validation error."""
    row: int
    sno: str
    tag: str
    column: str
    cell: str
    message: str
    rule: int | str
    rule_name: Optional[str] = None
    rule_type: Optional[str] = None
    source: Optional[str] = None


class ValidationRequest(BaseModel):
    """Request to validate an IODB file."""
    auto_correct_spelling: bool = False


class ValidationResponse(BaseModel):
    """Response from validation."""
    errors: List[ValidationErrorDetail]
    error_count: int
    has_error_log: bool
    has_highlighted: bool
    has_tba: bool
    message: Optional[str] = None


class DynamicRuleCondition(BaseModel):
    """Single condition in a dynamic rule."""
    column: str
    operator: str
    value: str
    logical_operator: str = "AND"


class DynamicRuleCreate(BaseModel):
    """Create a new dynamic rule."""
    name: str = Field(..., min_length=1, max_length=200)
    rule_type: str = Field(..., pattern="^(COLUMN|ROW|DUPLICATE)$")
    conditions: List[DynamicRuleCondition]
    target_column: Optional[str] = None
    error_message: str = Field(..., min_length=1, max_length=500)
    case_sensitive: bool = False
    priority: int = Field(default=100, ge=1, le=999)
    is_active: bool = True


class DynamicRuleUpdate(BaseModel):
    """Update an existing dynamic rule."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    rule_type: Optional[str] = Field(None, pattern="^(COLUMN|ROW|DUPLICATE)$")
    conditions: Optional[List[DynamicRuleCondition]] = None
    target_column: Optional[str] = None
    error_message: Optional[str] = Field(None, min_length=1, max_length=500)
    case_sensitive: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=1, le=999)
    is_active: Optional[bool] = None


class DynamicRuleResponse(BaseModel):
    """Dynamic rule response."""
    id: str
    name: str
    rule_type: str
    conditions: List[Dict[str, Any]]
    target_column: Optional[str]
    error_message: str
    case_sensitive: bool
    priority: int
    is_active: bool

    class Config:
        from_attributes = True
