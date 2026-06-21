"""
Approval Request Queue — junior engineers raise spec/coversheet review requests;
Lead Engineers approve or reject via their AdminUser credentials.
"""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from ..deps import get_db, get_current_user
from ..auth.models import User, AdminUser, ApprovalRequest, Notification
from ..auth.utils import verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["Approval Queue"])

LEAD_ROLES = ("Lead Engineer", "Admin", "Reviewer")


def _notify(db, recipient_employee_id: str, title: str, body: str,
             notif_type: str, related_request_id: int | None = None):
    """Insert a notification row — call before db.commit()."""
    if not recipient_employee_id:
        return
    db.add(Notification(
        recipient_employee_id=recipient_employee_id,
        title=title,
        body=body,
        notif_type=notif_type,
        related_request_id=related_request_id,
    ))


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class SubmitRequest(BaseModel):
    request_type: str               # "spec" | "coversheet"
    submitted_by_name: str
    submitted_by_id: str            # informational employee ID
    submitter_notes: Optional[str] = None
    tag_numbers: Optional[List[str]] = None
    instrument_type: Optional[str] = None
    payload: Optional[dict] = None  # full specs dict or coversheet summary


class ReviewRequest(BaseModel):
    employee_id: str
    password: str
    review_notes: Optional[str] = None


class ApprovalRequestResponse(BaseModel):
    id: int
    request_type: str
    tag_numbers: Optional[str]
    instrument_type: Optional[str]
    payload_json: Optional[str]
    submitted_by_name: str
    submitted_by_id: str
    submitter_notes: Optional[str]
    status: str
    reviewed_by_name: Optional[str]
    reviewed_by_id: Optional[str]
    reviewed_role: Optional[str]
    review_notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Submit a new approval request ─────────────────────────────────────────────

@router.post("", status_code=201, response_model=ApprovalRequestResponse)
def submit_approval(
    body: SubmitRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    req = ApprovalRequest(
        request_type=body.request_type,
        tag_numbers=json.dumps(body.tag_numbers) if body.tag_numbers else None,
        instrument_type=body.instrument_type,
        payload_json=json.dumps(body.payload) if body.payload else None,
        submitted_by_name=body.submitted_by_name,
        submitted_by_id=body.submitted_by_id,
        submitter_notes=body.submitter_notes,
        status="pending",
    )
    db.add(req)
    db.flush()  # get req.id before notifications

    # Notify all Lead Engineers / Admins / Reviewers
    leads = db.query(AdminUser).filter(
        AdminUser.role.in_(LEAD_ROLES),
        AdminUser.status == "active",
    ).all()
    label = "spec extraction" if body.request_type == "spec" else "cover sheet"
    for lead in leads:
        _notify(
            db, lead.employee_id,
            title=f"New {label} approval request",
            body=f"{body.submitted_by_name} has raised a {label} approval request (#{req.id}). Please review.",
            notif_type="approval_submitted",
            related_request_id=req.id,
        )

    db.commit()
    db.refresh(req)
    return req


# ── List pending (for notification badge + Lead queue) ────────────────────────

@router.get("/pending", response_model=List[ApprovalRequestResponse])
def list_pending(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.status == "pending")
        .order_by(ApprovalRequest.created_at.desc())
        .all()
    )


@router.get("/pending/count")
def pending_count(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    n = db.query(ApprovalRequest).filter(ApprovalRequest.status == "pending").count()
    return {"count": n}


# ── List my submitted requests ─────────────────────────────────────────────────

@router.get("/my/{submitted_by_id}", response_model=List[ApprovalRequestResponse])
def my_requests(
    submitted_by_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.submitted_by_id == submitted_by_id)
        .order_by(ApprovalRequest.created_at.desc())
        .all()
    )


# ── Get single request status (used for polling) ──────────────────────────────

@router.get("/{req_id}", response_model=ApprovalRequestResponse)
def get_request(
    req_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == req_id).first()
    if not req:
        raise HTTPException(404, "Request not found")
    return req


# ── Lead Engineer: Approve ─────────────────────────────────────────────────────

@router.post("/{req_id}/approve", response_model=ApprovalRequestResponse)
def approve_request(
    req_id: int,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == req_id).first()
    if not req:
        raise HTTPException(404, "Request not found")
    if req.status != "pending":
        raise HTTPException(400, f"Request is already {req.status}")

    # Validate Lead Engineer credentials
    lead = db.query(AdminUser).filter(
        AdminUser.employee_id == body.employee_id,
        AdminUser.status == "active",
    ).first()
    if not lead or not verify_password(body.password, lead.password_hash):
        raise HTTPException(401, "Invalid Employee ID or Password")
    if lead.role not in LEAD_ROLES:
        raise HTTPException(403, f"Role '{lead.role}' is not authorized to approve requests")

    now = datetime.now(timezone.utc)
    req.status = "approved"
    req.reviewed_by_name = lead.employee_name
    req.reviewed_by_id = lead.employee_id
    req.reviewed_role = lead.role
    req.review_notes = body.review_notes
    req.updated_at = now
    lead.last_login = now

    label = "spec extraction" if req.request_type == "spec" else "cover sheet"
    _notify(
        db, req.submitted_by_id,
        title=f"Your {label} request was approved",
        body=f"{lead.employee_name} ({lead.role}) has approved your {label} request (#{req.id}). You may now proceed.",
        notif_type="approved",
        related_request_id=req.id,
    )

    db.commit()
    db.refresh(req)
    return req


# ── Lead Engineer: Reject ──────────────────────────────────────────────────────

@router.post("/{req_id}/reject", response_model=ApprovalRequestResponse)
def reject_request(
    req_id: int,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == req_id).first()
    if not req:
        raise HTTPException(404, "Request not found")
    if req.status != "pending":
        raise HTTPException(400, f"Request is already {req.status}")

    lead = db.query(AdminUser).filter(
        AdminUser.employee_id == body.employee_id,
        AdminUser.status == "active",
    ).first()
    if not lead or not verify_password(body.password, lead.password_hash):
        raise HTTPException(401, "Invalid Employee ID or Password")
    if lead.role not in LEAD_ROLES:
        raise HTTPException(403, f"Role '{lead.role}' is not authorized to reject requests")

    now = datetime.now(timezone.utc)
    req.status = "rejected"
    req.reviewed_by_name = lead.employee_name
    req.reviewed_by_id = lead.employee_id
    req.reviewed_role = lead.role
    req.review_notes = body.review_notes
    req.updated_at = now

    label = "spec extraction" if req.request_type == "spec" else "cover sheet"
    note_suffix = f" Reason: {body.review_notes}" if body.review_notes else ""
    _notify(
        db, req.submitted_by_id,
        title=f"Your {label} request was rejected",
        body=f"{lead.employee_name} ({lead.role}) has rejected your {label} request (#{req.id}).{note_suffix}",
        notif_type="rejected",
        related_request_id=req.id,
    )

    db.commit()
    db.refresh(req)
    return req
