"""The IODB validator reports empty cells (Rule 1) only when 'Validate empty cells' is enabled."""
import io
import time
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.validator as validator
from app.deps import get_current_user
from utils.template_processor import process_iodb_validation

DJB = Path(__file__).resolve().parents[2] / "DJB_IODB.xlsx"


def small_iodb() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IODB"
    ws.append(["S.NO", "TAG NO", "SERVICE", "SIGNAL I/O TYPE", "REMARKS", "UNUSED COLUMN"])
    ws.append([1, "LIT-101", "Wet well level", "AI", None, None])
    ws.append([2, "LIT-102", None, "AI", None, None])            # SERVICE blank
    ws.append([3, "FIT-101", "Outlet flow", None, None, None])   # SIGNAL I/O TYPE blank
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def rule1(errors):
    return [e for e in errors if e["rule"] == 1]


def test_empty_cell_errors_only_when_enabled():
    data = small_iodb()
    _l, _h, _t, on, err = process_iodb_validation(data, validate_empty_cells=True)
    assert err is None
    assert {(e["tag"], e["column"]) for e in rule1(on)} == {("LIT-102", "SERVICE"), ("FIT-101", "SIGNAL I/O TYPE")}

    _l, _h, _t, off, err = process_iodb_validation(data, validate_empty_cells=False)
    assert err is None and rule1(off) == []
    assert len(off) == len(on) - 2                      # nothing else changes


def test_library_default_is_unchanged_for_existing_callers():
    _l, _h, _t, errs, _e = process_iodb_validation(small_iodb())
    assert len(rule1(errs)) == 2


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(validator.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, username="u", email="u@x")
    return TestClient(app)


def run(client, data, **form):
    r = client.post("/api/validator/validate", files={"file": ("IODB.xlsx", data)}, data=form)
    assert r.status_code == 202
    job = r.json()["job_id"]
    for _ in range(300):
        s = client.get(f"/api/validator/validate/status/{job}").json()
        if s["status"] != "processing":
            return s
        time.sleep(0.1)
    raise AssertionError("validation job did not finish")


def test_api_checkbox_is_off_by_default_and_enables_rule1(client):
    data = small_iodb()
    default = run(client, data)
    assert default["status"] == "done"
    assert "empty-cell check off" in default["result"]["message"]
    assert all(e["rule"] != 1 for e in default["result"]["errors"])

    enabled = run(client, data, validate_empty_cells="true")
    assert "empty-cell check off" not in enabled["result"]["message"]
    assert sum(e["rule"] == 1 for e in enabled["result"]["errors"]) == 2
    assert enabled["result"]["error_count"] == default["result"]["error_count"] + 2


@pytest.mark.skipif(not DJB.exists(), reason="DJB_IODB.xlsx not in repo")
def test_real_revised_iodb_off_vs_on():
    data = DJB.read_bytes()
    _l, _h, _t, off, e1 = process_iodb_validation(data, validate_empty_cells=False)
    _l, _h, _t, on, e2 = process_iodb_validation(data, validate_empty_cells=True)
    assert e1 is None and e2 is None
    assert rule1(off) == [] and len(rule1(on)) > 0
    assert len(on) - len(off) == len(rule1(on))         # the checkbox only affects Rule 1
