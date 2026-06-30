"""
Admin User Management — CRUD + Engineering Approval + Vendor Log
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user, require_admin
from ..auth.models import User, AdminUser, DatasheetApproval, VendorSelectionLog, LoginLog
from ..auth.utils import get_password_hash, verify_password
from ..config import settings
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


@router.get("/accounts")
def list_all_accounts(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """List all registered login accounts (User table), with their linked AdminUser role if any."""
    users = db.query(User).order_by(User.id.desc()).all()
    result = []
    for u in users:
        admin = db.query(AdminUser).filter(AdminUser.email_id == u.email).first()
        result.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_active": u.is_active,
            "employee_id": admin.employee_id if admin else None,
            "employee_name": admin.employee_name if admin else None,
            "role": admin.role if admin else "No role assigned",
            "in_admin_list": admin is not None,
        })
    return result


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

    # Username = email prefix (e.g. lead@iez.co.in → "lead"), lowercased, spaces→underscore
    username = body.email_id.split('@')[0].lower().replace(' ', '_')

    # Sync: create or update the JWT login User so the employee can log in immediately
    jwt_user = db.query(User).filter(User.email == body.email_id).first()
    if jwt_user:
        # Already signed up manually — adopt their account, update password to match
        jwt_user.username = username
        jwt_user.hashed_password = pw_hash
        jwt_user.is_active = True
    else:
        db.add(User(
            email=body.email_id,
            username=username,
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


# ── Login Activity ───────────────────────────────────────────────────────────

@router.get("/login-activity")
def login_activity(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """
    Total distinct users who have ever logged in, currently active sessions
    (approximated by refresh-token lifetime since logout is client-side only),
    and the most recent login history.
    """
    now = datetime.utcnow()
    session_window = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    logs = db.query(LoginLog).order_by(LoginLog.login_at.desc()).all()

    total_users_logged_in = len({l.employee_id or l.username for l in logs})

    latest_by_user: dict = {}
    for l in logs:
        key = l.employee_id or l.username
        if key not in latest_by_user:
            latest_by_user[key] = l

    active_sessions = [
        {
            "employee_id": l.employee_id,
            "employee_name": l.employee_name,
            "role": l.role,
            "login_at": l.login_at,
            "expires_at": l.login_at + session_window,
        }
        for l in latest_by_user.values()
        if l.login_at + session_window > now
    ]
    active_sessions.sort(key=lambda x: x["login_at"], reverse=True)

    recent_logins = [
        {
            "employee_id": l.employee_id,
            "employee_name": l.employee_name,
            "role": l.role,
            "login_at": l.login_at,
        }
        for l in logs[:200]
    ]

    # Full roster — every created account, including ones that never logged in
    # or whose session has since expired ("logged out").
    all_admin_users = db.query(AdminUser).order_by(AdminUser.employee_name).all()
    all_users = []
    for u in all_admin_users:
        latest = latest_by_user.get(u.employee_id)
        if latest is None:
            session_status = "never_logged_in"
            last_login_at = None
        elif latest.login_at + session_window > now:
            session_status = "active_now"
            last_login_at = latest.login_at
        else:
            session_status = "logged_out"
            last_login_at = latest.login_at

        all_users.append({
            "employee_id": u.employee_id,
            "employee_name": u.employee_name,
            "role": u.role,
            "account_status": u.status,
            "session_status": session_status,
            "last_login_at": last_login_at,
        })

    return {
        "total_users_logged_in": total_users_logged_in,
        "active_session_count": len(active_sessions),
        "active_sessions": active_sessions,
        "recent_logins": recent_logins,
        "all_users": all_users,
    }
