"""
SQLAlchemy models for authentication.
"""
from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    """User model for authentication."""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"


class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, unique=True, index=True, nullable=False)
    employee_name = Column(String, nullable=False)
    designation = Column(String, nullable=False)
    department = Column(String, nullable=False)
    email_id = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # Admin, Reviewer, Lead Engineer, Senior Engineer, Engineer, GET, Read Only
    status = Column(String, default="active")  # active, disabled
    created_date = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)


class DatasheetApproval(Base):
    __tablename__ = "datasheet_approval"
    id = Column(Integer, primary_key=True, index=True)
    tag_number = Column(String, nullable=False)
    instrument_type = Column(String, nullable=False)
    approved_by = Column(String, nullable=False)
    employee_id = Column(String, nullable=False)
    role = Column(String, nullable=False)
    date = Column(String, nullable=False)
    time_log = Column(String, nullable=False)


class VendorSelectionLog(Base):
    __tablename__ = "vendor_selection_log"
    id = Column(Integer, primary_key=True, index=True)
    tag_number = Column(String, nullable=False)
    vendor = Column(String, nullable=False)
    model = Column(String, nullable=False)
    match_percentage = Column(Integer, nullable=False)
    selected_by = Column(String, nullable=False)
    employee_id = Column(String, nullable=False)
    date = Column(String, nullable=False)
    time = Column(String, nullable=False)
