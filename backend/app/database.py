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
    from .auth.models import Base, AdminUser, DatasheetApproval, VendorSelectionLog  # noqa: F401
    Base.metadata.create_all(bind=engine)
