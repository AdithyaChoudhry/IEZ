"""
Admin User Management — CRUD + Engineering Approval + Vendor Log
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user, require_admin
from ..auth.models import User, AdminUser, DatasheetApproval, VendorSelectionLog
from ..auth.utils import get_password_hash, verify_password
from ..models.admin import (
    AdminUserCreate, AdminUserUpdate, AdminUserResponse,
    ResetPasswordRequest, ApprovalRequest, ApprovalResponse, VendorLogRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin Management"])


# ── Admin User CRUD ────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[AdminUserResponse])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(AdminUser).all()


@router.post("/users", response_model=AdminUserResponse, status_code=201)
def create_user(body: AdminUserCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if body.password != body.confirm_password:
        raise HTTPException(400, "Passwords do not match")
    if db.query(AdminUser).filter(AdminUser.employee_id == body.employee_id).first():
        raise HTTPException(400, "Employee ID already exists")
    if db.query(AdminUser).filter(AdminUser.email_id == body.email_id).first():
        raise HTTPException(400, "Email already exists")

    pw_hash = get_password_hash(body.password)

    admin = AdminUser(
        employee_id=body.employee_id,
        employee_name=body.employee_name,
        designation=body.designation,
        department=body.department,
        email_id=body.email_id,
        password_hash=pw_hash,
        role=body.role,
        status="active",
    )
    db.add(admin)

    # Sync: create or update the JWT login User so the employee can log in immediately
    jwt_user = db.query(User).filter(User.email == body.email_id).first()
    if jwt_user:
        # Already signed up manually — adopt their account, update password to match
        jwt_user.username = body.employee_name
        jwt_user.hashed_password = pw_hash
        jwt_user.is_active = True
    else:
        db.add(User(
            email=body.email_id,
            username=body.employee_name,
            hashed_password=pw_hash,
            is_active=True,
        ))

    db.commit(); db.refresh(admin)
    return admin


@router.get("/users/{employee_id}", response_model=AdminUserResponse)
def get_user(employee_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    u = db.query(AdminUser).filter(AdminUser.employee_id == employee_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    return u


@router.put("/users/{employee_id}", response_model=AdminUserResponse)
def update_user(employee_id: str, body: AdminUserUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    u = db.query(AdminUser).filter(AdminUser.employee_id == employee_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(u, k, v)
    db.commit(); db.refresh(u)
    return u


@router.delete("/users/{employee_id}", status_code=204)
def delete_user(employee_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    u = db.query(AdminUser).filter(AdminUser.employee_id == employee_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    # Remove linked JWT login account
    jwt_user = db.query(User).filter(User.email == u.email_id).first()
    if jwt_user:
        db.delete(jwt_user)
    db.delete(u); db.commit()


@router.post("/users/{employee_id}/disable", response_model=AdminUserResponse)
def disable_user(employee_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    u = db.query(AdminUser).filter(AdminUser.employee_id == employee_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    u.status = "disabled"
    # Revoke JWT login access
    jwt_user = db.query(User).filter(User.email == u.email_id).first()
    if jwt_user:
        jwt_user.is_active = False
    db.commit(); db.refresh(u)
    return u


@router.post("/users/{employee_id}/enable", response_model=AdminUserResponse)
def enable_user(employee_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    u = db.query(AdminUser).filter(AdminUser.employee_id == employee_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    u.status = "active"
    # Restore JWT login access
    jwt_user = db.query(User).filter(User.email == u.email_id).first()
    if jwt_user:
        jwt_user.is_active = True
    db.commit(); db.refresh(u)
    return u


@router.post("/users/{employee_id}/reset-password", response_model=AdminUserResponse)
def reset_password(employee_id: str, body: ResetPasswordRequest, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if body.new_password != body.confirm_password:
        raise HTTPException(400, "Passwords do not match")
    u = db.query(AdminUser).filter(AdminUser.employee_id == employee_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    pw_hash = get_password_hash(body.new_password)
    u.password_hash = pw_hash
    # Keep JWT login password in sync
    jwt_user = db.query(User).filter(User.email == u.email_id).first()
    if jwt_user:
        jwt_user.hashed_password = pw_hash
    db.commit(); db.refresh(u)
    return u


# ── Verify credentials (no log — used for cover sheet auth gate) ───────────────

@router.post("/verify")
def verify_credentials(body: dict, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Check Employee ID + Password without creating any audit entry."""
    emp_id = body.get("employee_id", "")
    password = body.get("password", "")
    if not emp_id or not password:
        raise HTTPException(400, "employee_id and password are required")
    admin = db.query(AdminUser).filter(
        AdminUser.employee_id == emp_id,
        AdminUser.status == "active",
    ).first()
    if not admin or not verify_password(password, admin.password_hash):
        raise HTTPException(401, "Invalid Employee ID or Password")
    return {"verified": True, "employee_name": admin.employee_name, "role": admin.role}


# ── Engineering Approval ───────────────────────────────────────────────────────

@router.post("/approve", response_model=ApprovalResponse)
def engineering_approve(body: ApprovalRequest, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    admin = db.query(AdminUser).filter(
        AdminUser.employee_id == body.employee_id,
        AdminUser.status == "active",
    ).first()
    if not admin or not verify_password(body.password, admin.password_hash):
        raise HTTPException(401, "Invalid Employee ID or Password")

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    for tag in body.tag_numbers:
        db.add(DatasheetApproval(
            tag_number=tag,
            instrument_type=body.instrument_type,
            approved_by=admin.employee_name,
            employee_id=admin.employee_id,
            role=admin.role,
            date=date_str,
            time_log=time_str,
        ))

    admin.last_login = now
    db.commit()

    return ApprovalResponse(
        approved_by=admin.employee_name,
        employee_id=admin.employee_id,
        role=admin.role,
        date=date_str,
        time_log=time_str,
    )


# ── Vendor Selection Log ───────────────────────────────────────────────────────

@router.post("/vendor-log", status_code=201)
def log_vendor_selection(body: VendorLogRequest, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    admin = db.query(AdminUser).filter(
        AdminUser.employee_id == body.employee_id,
        AdminUser.status == "active",
    ).first()
    if not admin or not verify_password(body.password, admin.password_hash):
        raise HTTPException(401, "Invalid Employee ID or Password")

    now = datetime.now(timezone.utc)
    db.add(VendorSelectionLog(
        tag_number=body.tag_number,
        vendor=body.vendor,
        model=body.model,
        match_percentage=body.match_percentage,
        selected_by=admin.employee_name,
        employee_id=admin.employee_id,
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M:%S"),
    ))
    db.commit()
    return {"status": "logged"}


# ── Audit Logs ─────────────────────────────────────────────────────────────────

@router.get("/approvals")
def list_approvals(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(DatasheetApproval).order_by(DatasheetApproval.id.desc()).all()

@router.get("/vendor-logs")
def list_vendor_logs(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(VendorSelectionLog).order_by(VendorSelectionLog.id.desc()).all()
