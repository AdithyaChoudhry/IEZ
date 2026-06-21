"""
Notifications router — per-employee notification feed.
Notifications are keyed by employee_id (from AdminUser or tblemployees).
"""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user
from ..auth.models import User, AdminUser, Employee, Notification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ── Helper ────────────────────────────────────────────────────────────────────

def _resolve_employee_id(user: User, db: Session) -> Optional[str]:
    admin = db.query(AdminUser).filter(AdminUser.email_id == user.email).first()
    if admin:
        return admin.employee_id
    emp = db.query(Employee).filter(Employee.email_id == user.email).first()
    if emp:
        return emp.employee_id
    return None


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    id: int
    recipient_employee_id: str
    title: str
    body: str
    notif_type: str
    related_request_id: Optional[int]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── GET /notifications/unread/count ──────────────────────────────────────────

@router.get("/unread/count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp_id = _resolve_employee_id(current_user, db)
    if not emp_id:
        return {"count": 0}
    n = (
        db.query(Notification)
        .filter(Notification.recipient_employee_id == emp_id, Notification.is_read == False)  # noqa: E712
        .count()
    )
    return {"count": n}


# ── GET /notifications ────────────────────────────────────────────────────────

@router.get("", response_model=List[NotificationResponse])
def list_notifications(
    limit: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp_id = _resolve_employee_id(current_user, db)
    if not emp_id:
        return []
    return (
        db.query(Notification)
        .filter(Notification.recipient_employee_id == emp_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )


# ── POST /notifications/{id}/read ─────────────────────────────────────────────

@router.post("/{notif_id}/read")
def mark_read(
    notif_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp_id = _resolve_employee_id(current_user, db)
    n = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.recipient_employee_id == emp_id,
    ).first()
    if not n:
        raise HTTPException(404, "Notification not found")
    n.is_read = True
    db.commit()
    return {"ok": True}


# ── POST /notifications/mark-all-read ────────────────────────────────────────

@router.post("/mark-all-read")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp_id = _resolve_employee_id(current_user, db)
    if not emp_id:
        return {"updated": 0}
    result = (
        db.query(Notification)
        .filter(Notification.recipient_employee_id == emp_id, Notification.is_read == False)  # noqa: E712
        .all()
    )
    for n in result:
        n.is_read = True
    db.commit()
    return {"updated": len(result)}
