"""
IODB Validator router - validation and dynamic rules management.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from typing import List, Optional
import io
import json
import uuid

from ..deps import get_current_user
from ..auth.models import User
from ..models.validator import (
    ValidationRequest,
    ValidationResponse,
    ValidationErrorDetail,
    ValidationJobResponse,
    ValidationStatusResponse,
    DynamicRuleCreate,
    DynamicRuleUpdate,
    DynamicRuleResponse,
)

# Import existing business logic
import sys
sys.path.insert(0, '/app')
from utils.template_processor import process_iodb_validation
from utils.dynamic_rules import (
    DynamicRule,
    load_rules,
    add_rule,
    update_rule,
    delete_rule,
)


router = APIRouter(prefix="/validator", tags=["IODB Validator"])


# Store validation results temporarily (in production, use Redis or database)
validation_cache: dict = {}

# Store validation job status/results temporarily (in production, use Redis or database)
validation_jobs: dict = {}

# Cap the number of error details sent back in the JSON response — with
# wide/sparse IODB files this can reach 100K+ entries, which is far too
# large to serialize and render in the browser. The full list is still
# available in the downloadable error-log workbook.
MAX_ERRORS_IN_RESPONSE = 2000


def _run_validation_job(
    job_id: str,
    file_bytes: bytes,
    auto_correct_spelling: bool,
    dynamic_rules,
    user_id: int,
):
    """Run validation in the background and store the result/status."""
    try:
        log_bytes, hl_bytes, tba_bytes, errors, err_msg = process_iodb_validation(
            file_bytes,
            auto_correct_spelling=auto_correct_spelling,
            dynamic_rules=dynamic_rules if dynamic_rules else None,
        )

        if err_msg:
            validation_jobs[job_id] = {"status": "error", "error": err_msg}
            return

        # Store results in cache (keyed by user ID) for the download endpoints
        cache_key = f"{user_id}_validation"
        validation_cache[cache_key] = {
            "log_bytes": log_bytes,
            "highlighted_bytes": hl_bytes,
            "tba_bytes": tba_bytes,
        }

        error_details = [
            ValidationErrorDetail(**error) for error in errors[:MAX_ERRORS_IN_RESPONSE]
        ]

        validation_jobs[job_id] = {
            "status": "done",
            "result": ValidationResponse(
                errors=error_details,
                error_count=len(errors),
                errors_truncated=len(errors) > MAX_ERRORS_IN_RESPONSE,
                has_error_log=log_bytes is not None,
                has_highlighted=hl_bytes is not None,
                has_tba=tba_bytes is not None,
                message=f"Validation complete: {len(errors)} error(s) found" if errors else "No errors found",
            ),
        }
    except Exception as exc:
        validation_jobs[job_id] = {"status": "error", "error": str(exc)}


@router.post("/validate", response_model=ValidationJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def validate_iodb(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    auto_correct_spelling: bool = Form(False),
    current_user: User = Depends(get_current_user),
):
    """
    Kick off validation of an IODB Excel file with predefined and dynamic
    rules. Validation runs in the background — poll
    GET /validator/validate/status/{job_id} for the result.
    """
    file_bytes = await file.read()
    dynamic_rules = load_rules()

    job_id = str(uuid.uuid4())
    validation_jobs[job_id] = {"status": "processing"}

    background_tasks.add_task(
        _run_validation_job,
        job_id,
        file_bytes,
        auto_correct_spelling,
        dynamic_rules,
        current_user.id,
    )

    return ValidationJobResponse(job_id=job_id, status="processing")


@router.get("/validate/status/{job_id}", response_model=ValidationStatusResponse)
async def get_validation_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Poll the status/result of a validation job."""
    job = validation_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Validation job not found"
        )

    return ValidationStatusResponse(
        job_id=job_id,
        status=job["status"],
        result=job.get("result"),
        error=job.get("error"),
    )


@router.get("/download/error-log")
async def download_error_log(current_user: User = Depends(get_current_user)):
    """Download the error log Excel file."""
    cache_key = f"{current_user.id}_validation"
    cached = validation_cache.get(cache_key)
    
    if not cached or not cached.get("log_bytes"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No validation results found. Please run validation first."
        )
    
    return StreamingResponse(
        io.BytesIO(cached["log_bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=IODB_Validation_Report.xlsx"
        }
    )


@router.get("/download/highlighted")
async def download_highlighted(current_user: User = Depends(get_current_user)):
    """Download the highlighted IODB Excel file."""
    cache_key = f"{current_user.id}_validation"
    cached = validation_cache.get(cache_key)
    
    if not cached or not cached.get("highlighted_bytes"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No validation results found. Please run validation first."
        )
    
    return StreamingResponse(
        io.BytesIO(cached["highlighted_bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=IODB_Highlighted.xlsx"
        }
    )


@router.get("/download/tba")
async def download_tba(current_user: User = Depends(get_current_user)):
    """Download the TBA details Excel file."""
    cache_key = f"{current_user.id}_validation"
    cached = validation_cache.get(cache_key)
    
    if not cached or not cached.get("tba_bytes"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No validation results found. Please run validation first."
        )
    
    return StreamingResponse(
        io.BytesIO(cached["tba_bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=TBA_details.xlsx"
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Predefined Rules metadata (read-only)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/predefined-rules")
async def list_predefined_rules(current_user: User = Depends(get_current_user)):
    """Return the 12 built-in validation rules (metadata only — always active)."""
    from utils.dynamic_rules import PREDEFINED_RULES_META
    return PREDEFINED_RULES_META


# Dynamic Rules CRUD
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/rules", response_model=List[DynamicRuleResponse])
async def list_rules(current_user: User = Depends(get_current_user)):
    """Get all dynamic validation rules."""
    rules = load_rules()
    return [
        DynamicRuleResponse(
            id=rule.id,
            name=rule.name,
            rule_type=rule.rule_type,
            conditions=rule.conditions,
            target_column=rule.target_column,
            error_message=rule.error_message,
            case_sensitive=rule.case_sensitive,
            priority=rule.priority,
            is_active=rule.is_active,
        )
        for rule in rules
    ]


@router.post("/rules", response_model=DynamicRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    rule_data: DynamicRuleCreate,
    current_user: User = Depends(get_current_user),
):
    """Create a new dynamic validation rule."""
    # Convert Pydantic model to DynamicRule
    new_rule = DynamicRule(
        name=rule_data.name,
        rule_type=rule_data.rule_type,
        conditions=[cond.dict() for cond in rule_data.conditions],
        target_column=rule_data.target_column,
        error_message=rule_data.error_message,
        case_sensitive=rule_data.case_sensitive,
        priority=rule_data.priority,
        is_active=rule_data.is_active,
    )
    
    # Save rule
    add_rule(new_rule)
    
    return DynamicRuleResponse(
        id=new_rule.id,
        name=new_rule.name,
        rule_type=new_rule.rule_type,
        conditions=new_rule.conditions,
        target_column=new_rule.target_column,
        error_message=new_rule.error_message,
        case_sensitive=new_rule.case_sensitive,
        priority=new_rule.priority,
        is_active=new_rule.is_active,
    )


@router.put("/rules/{rule_id}", response_model=DynamicRuleResponse)
async def update_rule_endpoint(
    rule_id: str,
    rule_data: DynamicRuleUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update an existing dynamic validation rule."""
    # Get current rule
    rules = load_rules()
    current_rule = next((r for r in rules if r.id == rule_id), None)
    
    if not current_rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule with ID {rule_id} not found"
        )
    
    # Update fields
    update_dict = rule_data.dict(exclude_unset=True)
    if "conditions" in update_dict:
        update_dict["conditions"] = [cond.dict() for cond in rule_data.conditions]
    
    update_rule(rule_id, **update_dict)
    
    # Reload to get updated rule
    rules = load_rules()
    updated_rule = next((r for r in rules if r.id == rule_id), None)
    
    return DynamicRuleResponse(
        id=updated_rule.id,
        name=updated_rule.name,
        rule_type=updated_rule.rule_type,
        conditions=updated_rule.conditions,
        target_column=updated_rule.target_column,
        error_message=updated_rule.error_message,
        case_sensitive=updated_rule.case_sensitive,
        priority=updated_rule.priority,
        is_active=updated_rule.is_active,
    )


@router.patch("/rules/{rule_id}/toggle")
async def toggle_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
):
    """Toggle a rule's active status."""
    rules = load_rules()
    rule = next((r for r in rules if r.id == rule_id), None)
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule with ID {rule_id} not found"
        )
    
    update_rule(rule_id, is_active=not rule.is_active)
    
    return {"message": "Rule status toggled", "is_active": not rule.is_active}


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule_endpoint(
    rule_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a dynamic validation rule."""
    rules = load_rules()
    rule = next((r for r in rules if r.id == rule_id), None)
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule with ID {rule_id} not found"
        )
    
    delete_rule(rule_id)
    return None
