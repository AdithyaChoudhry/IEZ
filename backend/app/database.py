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


def _seed_notification_routes():
    """Insert default routing rules if the table is empty."""
    from .auth.models import NotificationRoute
    db = SessionLocal()
    try:
        if db.query(NotificationRoute).count() > 0:
            return
        defaults = [
            NotificationRoute(
                trigger_event="approval_submitted",
                notify_type="reporting_authority",
                notify_value=None,
                same_department_only=False,
                priority=1,
                description="Notify the submitter's direct reporting authority",
                is_active=True,
            ),
            NotificationRoute(
                trigger_event="approval_submitted",
                notify_type="role",
                notify_value="Lead Engineer",
                same_department_only=True,
                priority=10,
                description="Fallback: notify Lead Engineers in the same department",
                is_active=True,
            ),
            NotificationRoute(
                trigger_event="approval_submitted",
                notify_type="role",
                notify_value="Admin",
                same_department_only=False,
                priority=20,
                description="Fallback: notify all Admins",
                is_active=False,
            ),
        ]
        for r in defaults:
            db.add(r)
        db.commit()
    finally:
        db.close()


def init_db():
    """
    Initialize database tables.
    Import all models here to ensure they're registered with SQLAlchemy.
    """
    # Import every model so it's registered in Base.metadata before create_all
    from .auth.models import (  # noqa: F401
        Base, User, AdminUser, DatasheetApproval, VendorSelectionLog,
        ApprovalRequest, Employee, Notification, NotificationRoute
    )
    Base.metadata.create_all(bind=engine)
    _seed_notification_routes()
