"""
Notification routing rules — admin configures who gets notified for which events.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user
from ..auth.models import User, NotificationRoute

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notification-routes", tags=["Notification Routes"])

TRIGGER_EVENTS = ("approval_submitted", "approved", "rejected")
NOTIFY_TYPES = ("reporting_authority", "role", "employee")


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RouteCreate(BaseModel):
    trigger_event: str
    notify_type: str
    notify_value: Optional[str] = None
    same_department_only: bool = False
    description: Optional[str] = None
    priority: int = 10
    is_active: bool = True


class RouteUpdate(BaseModel):
    notify_value: Optional[str] = None
    same_department_only: Optional[bool] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class RouteResponse(BaseModel):
    id: int
    trigger_event: str
    notify_type: str
    notify_value: Optional[str]
    same_department_only: bool
    description: Optional[str]
    priority: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── GET /notification-routes ─────────────────────────────────────────────────

@router.get("", response_model=List[RouteResponse])
def list_routes(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return (
        db.query(NotificationRoute)
        .order_by(NotificationRoute.priority, NotificationRoute.id)
        .all()
    )


# ── POST /notification-routes ─────────────────────────────────────────────────

@router.post("", response_model=RouteResponse, status_code=201)
def create_route(
    body: RouteCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if body.trigger_event not in TRIGGER_EVENTS:
        raise HTTPException(400, f"trigger_event must be one of {TRIGGER_EVENTS}")
    if body.notify_type not in NOTIFY_TYPES:
        raise HTTPException(400, f"notify_type must be one of {NOTIFY_TYPES}")
    if body.notify_type in ("role", "employee") and not body.notify_value:
        raise HTTPException(400, "notify_value is required for type 'role' and 'employee'")

    route = NotificationRoute(**body.model_dump())
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


# ── PATCH /notification-routes/{id} ──────────────────────────────────────────

@router.patch("/{route_id}", response_model=RouteResponse)
def update_route(
    route_id: int,
    body: RouteUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    route = db.query(NotificationRoute).filter(NotificationRoute.id == route_id).first()
    if not route:
        raise HTTPException(404, "Route not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(route, field, value)
    db.commit()
    db.refresh(route)
    return route


# ── DELETE /notification-routes/{id} ─────────────────────────────────────────

@router.delete("/{route_id}", status_code=204)
def delete_route(
    route_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    route = db.query(NotificationRoute).filter(NotificationRoute.id == route_id).first()
    if not route:
        raise HTTPException(404, "Route not found")
    db.delete(route)
    db.commit()
