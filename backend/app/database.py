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


def _seed_default_admin():
    """Ensure the system admin account always exists."""
    from .auth.models import AdminUser, User
    from .auth.utils import get_password_hash
    db = SessionLocal()
    try:
        if db.query(AdminUser).filter(AdminUser.employee_id == "ADMIN001").first():
            return  # already seeded
        pw_hash = get_password_hash("Admin@iez2024")
        admin = AdminUser(
            employee_id="ADMIN001",
            employee_name="System Admin",
            designation="System Administrator",
            department="IT",
            email_id="admin@iez.co.in",
            password_hash=pw_hash,
            role="Admin",
            status="active",
        )
        db.add(admin)
        # JWT login account
        if not db.query(User).filter(User.email == "admin@iez.co.in").first():
            db.add(User(
                email="admin@iez.co.in",
                username="admin",
                hashed_password=pw_hash,
                is_active=True,
            ))
        db.commit()
    finally:
        db.close()


def _seed_tbe_vendors():
    """Populate tbe_vendors from VENDOR_DB. Re-seeds if count < expected total."""
    from .auth.models import TBEVendor
    from .data.tbe_vendors import VENDOR_DB
    expected = sum(len(v) for v in VENDOR_DB.values())
    db = SessionLocal()
    try:
        current = db.query(TBEVendor).count()
        if current >= expected:
            return  # already up to date
        # Clear and reseed (preserves any user-added extras beyond expected count)
        db.query(TBEVendor).delete()
        for instrument_type, vendors in VENDOR_DB.items():
            for v in vendors:
                db.add(TBEVendor(
                    instrument_type=instrument_type,
                    vendor_name=v["vendor"],
                    abbr=v["abbr"],
                    model=v["model"],
                    specs=v["specs"],
                ))
        db.commit()
    finally:
        db.close()


def init_db():
    """
    Initialize database tables.
    Import all models here to ensure they're registered with SQLAlchemy.
    """
    from .auth.models import (  # noqa: F401
        Base, User, AdminUser, DatasheetApproval, VendorSelectionLog,
        ApprovalRequest, Employee, Notification, NotificationRoute,
        TBEApprovalLog, TBEVendor
    )
    from .models.idc import (  # noqa: F401
        IDCSession, IDCDocument, IDCDiscipline, IDCAnnotation,
        IDCComment, IDCCommentReply, IDCApproval,
    )
    Base.metadata.create_all(bind=engine)
    _seed_notification_routes()
    _seed_default_admin()
    _seed_tbe_vendors()
