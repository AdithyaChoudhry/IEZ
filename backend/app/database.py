"""
Database configuration and session management.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings


# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    echo=settings.DEBUG,  # Log SQL queries in debug mode
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """
    Initialize database tables.
    Import all models here to ensure they're registered with SQLAlchemy.
    """
    # Import every model so it's registered in Base.metadata before create_all
    from .auth.models import (  # noqa: F401
        Base, User, AdminUser, DatasheetApproval, VendorSelectionLog,
        ApprovalRequest, Employee, Notification
    )
    Base.metadata.create_all(bind=engine)
