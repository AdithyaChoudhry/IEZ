"""
Employee profile router — tblemployees CRUD.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user
from ..auth.models import User, AdminUser, Employee

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/employees", tags=["Employees"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class EmployeeCreate(BaseModel):
    employee_id: str
    employee_name: str
    designation: str
    department: str
    email_id: str
    phone: Optional[str] = None
    role: str
    reporting_authority_id: Optional[str] = None


class EmployeeUpdate(BaseModel):
    employee_name: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    email_id: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    reporting_authority_id: Optional[str] = None
    status: Optional[str] = None


class EmployeeResponse(BaseModel):
    id: int
    employee_id: str
    employee_name: str
    designation: str
    department: str
    email_id: str
    phone: Optional[str]
    role: str
    reporting_authority_id: Optional[str]
    status: str
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Helper: resolve employee_id for current JWT user ─────────────────────────

def _employee_id_for_user(user: User, db: Session) -> Optional[str]:
    """Look up the AdminUser/Employee record matching the JWT user's email."""
    admin = db.query(AdminUser).filter(AdminUser.email_id == user.email).first()
    if admin:
        return admin.employee_id
    emp = db.query(Employee).filter(Employee.email_id == user.email).first()
    if emp:
        return emp.employee_id
    return None


# ── GET /employees/me ─────────────────────────────────────────────────────────

@router.get("/me")
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the employee profile matching the current JWT user's email."""
    # Check AdminUser first (primary source)
    admin = db.query(AdminUser).filter(AdminUser.email_id == current_user.email).first()
    if admin:
        return {
            "employee_id": admin.employee_id,
            "employee_name": admin.employee_name,
            "designation": admin.designation,
            "department": admin.department,
            "email_id": admin.email_id,
            "role": admin.role,
            "phone": None,
            "reporting_authority_id": None,
            "status": admin.status,
            "source": "admin_users",
        }
    emp = db.query(Employee).filter(Employee.email_id == current_user.email).first()
    if emp:
        return {
            "employee_id": emp.employee_id,
            "employee_name": emp.employee_name,
            "designation": emp.designation,
            "department": emp.department,
            "email_id": emp.email_id,
            "role": emp.role,
            "phone": emp.phone,
            "reporting_authority_id": emp.reporting_authority_id,
            "status": emp.status,
            "source": "tblemployees",
        }
    # JWT user without an AdminUser record — return minimal profile
    return {
        "employee_id": None,
        "employee_name": current_user.username,
        "designation": None,
        "department": None,
        "email_id": current_user.email,
        "role": "Engineer",
        "phone": None,
        "reporting_authority_id": None,
        "status": "active",
        "source": "users",
    }


# ── GET /employees ────────────────────────────────────────────────────────────

@router.get("", response_model=List[EmployeeResponse])
def list_employees(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(Employee).order_by(Employee.employee_name).all()


# ── POST /employees ───────────────────────────────────────────────────────────

@router.post("", response_model=EmployeeResponse, status_code=201)
def create_employee(
    body: EmployeeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if db.query(Employee).filter(Employee.employee_id == body.employee_id).first():
        raise HTTPException(400, f"Employee ID '{body.employee_id}' already exists")
    emp = Employee(**body.model_dump())
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


# ── PATCH /employees/{employee_id} ───────────────────────────────────────────

@router.patch("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: str,
    body: EmployeeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    emp = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Employee not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(emp, field, value)
    emp.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(emp)
    return emp


# ── GET /employees/reporting-chain/{employee_id} ──────────────────────────────

@router.get("/reporting-chain/{employee_id}")
def reporting_chain(
    employee_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Walk up the reporting chain and return the list of managers."""
    chain = []
    current_id = employee_id
    seen = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        emp = db.query(Employee).filter(Employee.employee_id == current_id).first()
        if not emp:
            break
        chain.append({
            "employee_id": emp.employee_id,
            "employee_name": emp.employee_name,
            "designation": emp.designation,
            "role": emp.role,
        })
        current_id = emp.reporting_authority_id
    return chain
