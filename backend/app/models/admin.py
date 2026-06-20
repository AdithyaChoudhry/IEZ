from pydantic import BaseModel
from typing import Optional
from datetime import datetime

ROLES = ["Admin", "Reviewer", "Lead Engineer", "Senior Engineer", "Engineer", "GET", "Read Only"]

class AdminUserCreate(BaseModel):
    employee_id: str
    employee_name: str
    designation: str
    department: str
    email_id: str
    password: str
    confirm_password: str
    role: str

class AdminUserUpdate(BaseModel):
    employee_name: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    email_id: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None

class AdminUserResponse(BaseModel):
    id: int
    employee_id: str
    employee_name: str
    designation: str
    department: str
    email_id: str
    role: str
    status: str
    created_date: datetime
    last_login: Optional[datetime] = None
    class Config:
        from_attributes = True

class ResetPasswordRequest(BaseModel):
    new_password: str
    confirm_password: str

class ApprovalRequest(BaseModel):
    employee_id: str
    password: str
    tag_numbers: list[str]
    instrument_type: str

class ApprovalResponse(BaseModel):
    approved_by: str
    employee_id: str
    role: str
    date: str
    time_log: str

class VendorLogRequest(BaseModel):
    tag_number: str
    vendor: str
    model: str
    match_percentage: int
    employee_id: str
    password: str
