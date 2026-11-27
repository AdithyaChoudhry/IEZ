"""
Custom IODB validation rule profiles (per project). The iEZ default rules are built in and are never stored.

Only adds new tables - touches no existing ones. Versions are append-only, so the configuration named in an old validation
report can still be looked up after the profile has been edited or deleted.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from ..auth.models import Base


class ValidationProfile(Base):
    __tablename__ = "validation_profiles"
    id          = Column(Integer, primary_key=True, index=True)
    project_id  = Column(String, index=True, nullable=False)
    name        = Column(String, nullable=False)
    version     = Column(Integer, nullable=False, default=1)
    config_json = Column(Text, nullable=False)
    is_deleted  = Column(Boolean, nullable=False, default=False)
    created_by  = Column(String, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_by  = Column(String, nullable=True)
    updated_at  = Column(DateTime, default=datetime.utcnow)


class ValidationProfileVersion(Base):
    __tablename__ = "validation_profile_versions"
    __table_args__ = (UniqueConstraint("profile_id", "version", name="uq_validation_profile_version"),)
    id          = Column(Integer, primary_key=True, index=True)
    profile_id  = Column(Integer, ForeignKey("validation_profiles.id"), index=True, nullable=False)
    version     = Column(Integer, nullable=False)
    name        = Column(String, nullable=False)
    config_json = Column(Text, nullable=False)
    saved_by    = Column(String, nullable=True)
    saved_at    = Column(DateTime, default=datetime.utcnow)
