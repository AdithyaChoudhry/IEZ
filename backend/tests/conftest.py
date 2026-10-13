"""Shared fixtures for the document registry tests (SQLite + temp file store)."""
import io
import os
import sys
from pathlib import Path

import openpyxl
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Settings reads ".env" from the working directory - run tests from a folder
# without one so they never load real credentials.
os.chdir(Path(__file__).resolve().parent)
os.environ["DATABASE_URL"] = "sqlite://"            # app.database builds an engine at import time

ROOT = Path(__file__).resolve().parents[2]          # repo root (has utils/)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.auth.models import Base                                       # noqa: E402
from app.config import settings                                        # noqa: E402
import app.models.document_registry  # noqa: E402,F401  (register tables)


def make_iodb(tag_prefix: str = "LT", n: int = 5, extra_row: bool = False) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IODB"
    ws.append(["TAG NO", "INSTRUMENT NAME", "SIGNAL I/O TYPE", "JUNCTION BOX"])
    for i in range(1, n + 1):
        ws.append([f"{tag_prefix}-{i:03d}", f"Transmitter {i}", "AI", f"JB-{1 + i % 2}"])
    if extra_row:
        ws.append([f"{tag_prefix}-999", "Added in later revision", "AI", "JB-1"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def make_xlsx(rows: int = 3) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["H1", "H2"])
    for i in range(rows):
        ws.append([i, f"v{i}"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_STORE_DIR", str(tmp_path / "store"), raising=False)
    return tmp_path / "store"


@pytest.fixture()
def engine(store):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db(engine):
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = Session()
    yield s
    s.close()


@pytest.fixture()
def new_session(engine):
    """Factory for a brand-new session over the same database (simulates reopening)."""
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return Session
