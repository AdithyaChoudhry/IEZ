"""Gland and Lug generators: an IODB can be uploaded instead of a cable schedule (the schedule is generated first)."""
import io
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import cable_complete as cc  # noqa: E402
from tests.test_cable_complete import iodb, template, row, ROWS  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import gland_quantity, lug_quantity
    monkeypatch.setattr(cc, "builtin_template", lambda: template())
    cc.SCHEDULE_CACHE.clear()
    app = FastAPI()
    app.include_router(gland_quantity.router, prefix="/api")
    app.include_router(lug_quantity.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=61, username="bob")
    return TestClient(app)


def wait(client, url, tries=120):
    for _ in range(tries):
        j = client.get(url).json()
        if j["status"] != "processing":
            return j
        time.sleep(0.5)
    raise AssertionError("job did not finish")


def test_lug_quantity_from_an_iodb_generates_the_cable_schedule_first(client):
    r = client.post("/api/cable-schedule/lug/start", files={"iodb_file": ("IODB.xlsx", iodb())})
    assert r.status_code == 202
    j = wait(client, f"/api/cable-schedule/lug/job/{r.json()['job_id']}")
    assert j["status"] == "done", j
    res = j["result"]
    assert res["source"]["type"] == "IODB" and res["source"]["name"] == "IODB.xlsx" and res["source"]["validation"]["status"].startswith("READY")
    assert res["kpis"]["cables"] > 0 and res["kpis"]["total_lugs"] > 0                       # every conductor lugged by default
    tags = {c["tag"] for c in res["cable_wise"]}
    assert {"IC-1", "IC-2", "IC-3", "MC-1", "MC-2"} <= tags
    dl = client.get("/api/cable-schedule/lug/download")
    assert dl.status_code == 200 and openpyxl.load_workbook(io.BytesIO(dl.content)).sheetnames[0] == "LUG SUMMARY"


def test_lug_rerun_reuses_the_generated_schedule_for_new_settings(client):
    r = client.post("/api/cable-schedule/lug/start", files={"iodb_file": ("IODB_A.xlsx", iodb())})
    first = wait(client, f"/api/cable-schedule/lug/job/{r.json()['job_id']}")["result"]
    assert "IODB_A.xlsx" in cc.SCHEDULE_CACHE["61_lug"]["name"]
    r2 = client.post("/api/cable-schedule/lug/start", data={"reuse": "true", "rules": '{"instrumentation_use_lugs": false, "control_use_lugs": false, "ferrule_evidence": true}'})
    assert r2.status_code == 202
    second = wait(client, f"/api/cable-schedule/lug/job/{r2.json()['job_id']}")["result"]
    assert second["source"]["name"] == "IODB_A.xlsx" and second["kpis"]["cables"] == first["kpis"]["cables"]
    assert second["kpis"]["total_lugs"] < first["kpis"]["total_lugs"]


def test_gland_quantity_from_an_iodb_generates_the_cable_schedule_first(client):
    r = client.post("/api/cable-schedule/gland/iodb/start", files={"iodb_file": ("IODB.xlsx", iodb())}, data={"settings": '{"default_qty": 1}'})
    assert r.status_code == 202
    j = wait(client, f"/api/cable-schedule/gland/iodb/job/{r.json()['job_id']}")
    assert j["status"] == "done", j
    res = j["result"]
    assert res["source"]["type"] == "IODB" and res["totals"]["glands"] > 0 and "_lines" not in res
    assert {"IC-1", "MC-1"} <= {c["cable_tag"] for c in res["cable_wise"]}
    dl = client.get("/api/cable-schedule/gland/download")
    assert dl.status_code == 200 and openpyxl.load_workbook(io.BytesIO(dl.content)).sheetnames[0] == "GLAND SUMMARY"
    r2 = client.post("/api/cable-schedule/gland/iodb/start", data={"reuse": "true", "cable_data": '{"1PX15SQMM": {"od": 9}}'})
    assert wait(client, f"/api/cable-schedule/gland/iodb/job/{r2.json()['job_id']}")["status"] == "done"


def test_the_cable_schedule_and_the_existing_endpoints_still_work(client):
    wb = openpyxl.Workbook(); wb.active.append(["x", "y", "z"])
    buf = io.BytesIO(); wb.save(buf)
    r = client.post("/api/cable-schedule/lug/analyze", files={"file": ("a.xlsx", buf.getvalue())})
    assert r.status_code == 400 and "No cable schedule sheet" in r.json()["detail"]


def test_errors_are_clear(client, monkeypatch):
    assert "either a Cable Schedule or an IODB" in client.post("/api/cable-schedule/lug/start").json()["detail"]
    assert "Upload an IODB" in client.post("/api/cable-schedule/gland/iodb/start").json()["detail"]
    both = client.post("/api/cable-schedule/lug/start", files={"file": ("a.xlsx", b"x"), "iodb_file": ("b.xlsx", b"x")})
    assert both.status_code == 400
    bad = client.post("/api/cable-schedule/lug/start", files={"iodb_file": ("IODB.xlsx", iodb([row("A")]))})
    j = wait(client, f"/api/cable-schedule/lug/job/{bad.json()['job_id']}")
    assert j["status"] == "error" and "IODB validation failed" in j["error"]
    badg = client.post("/api/cable-schedule/gland/iodb/start", files={"iodb_file": ("IODB.xlsx", iodb([row("A")]))})
    assert "IODB validation failed" in wait(client, f"/api/cable-schedule/gland/iodb/job/{badg.json()['job_id']}")["error"]
    monkeypatch.setattr(cc, "builtin_template", lambda: None)
    r = client.post("/api/cable-schedule/lug/start", files={"iodb_file": ("IODB.xlsx", iodb())})
    assert r.status_code == 400 and "No Cable Schedule template" in r.json()["detail"]
    r = client.post("/api/cable-schedule/gland/iodb/start", files={"iodb_file": ("IODB.xlsx", iodb())})
    assert r.status_code == 400 and "No Cable Schedule template" in r.json()["detail"]
    up = client.post("/api/cable-schedule/lug/start", files={"iodb_file": ("IODB.xlsx", iodb()), "template_file": ("T.xlsx", template())})
    assert up.status_code == 202 and wait(client, f"/api/cable-schedule/lug/job/{up.json()['job_id']}")["status"] == "done"
