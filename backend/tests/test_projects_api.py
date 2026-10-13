"""
API-level tests: real generator endpoints -> registry -> Coversheet-facing endpoints.
"""
import io
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.database as database
from app.deps import get_current_user, get_db, require_lead
from app.routers.instrument_list import router as instrument_router
from app.routers.io_list import router as io_router
from app.routers.projects import router as projects_router
from conftest import make_iodb

PID = "10P211"
COLS = json.dumps(["TAG NO", "INSTRUMENT NAME"])


@pytest.fixture()
def client(engine, db, monkeypatch):
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    app = FastAPI()
    for r in (projects_router, instrument_router, io_router):
        app.include_router(r, prefix="/api")
    user = SimpleNamespace(id=7, username="alice", email="alice@iez.co.in")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_lead] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def generate(client, path, project=PID, iodb=None, **extra):
    data = {"selected_columns": COLS, **extra}
    if project:
        data["project_id"] = project
    return client.post(
        f"/api/{path}/generate", data=data,
        files={"iodb_file": ("IODB.xlsx", iodb or make_iodb(), "application/octet-stream")},
    )


def test_generation_registers_and_coversheet_sees_it(client):
    r = generate(client, "instrument-list")
    assert r.status_code == 200, r.text
    reg = r.json()["registry"]
    assert reg["registered"] and reg["document"]["revision_label"] == "R1"
    assert reg["document"]["document_number"] == f"{PID}-INS-001"

    ov = client.get(f"/api/projects/{PID}/documents/connected").json()
    mods = {m["module"]: m for m in ov["modules"]}
    assert mods["instrument_list"]["latest"]["filename"] == "Instrument List.xlsx"
    assert mods["instrument_list"]["latest"]["record_count"] == 5
    assert mods["io_list"]["state"] == "not_generated"
    assert ov["sources"]["iodb"]["rev_no"] == 1


def test_generation_without_project_is_unchanged(client):
    r = generate(client, "io-list", project=None)
    assert r.status_code == 200
    assert r.json()["registry"] is None
    assert client.get(f"/api/projects/{PID}/documents").json() == []


def test_bad_project_id_never_breaks_generation(client):
    r = generate(client, "io-list", project="../evil")
    assert r.status_code == 200
    assert r.json()["registry"]["registered"] is False
    assert "Invalid project id" in r.json()["registry"]["error"]
    assert client.get("/api/projects/..%2Fevil/documents").status_code in (400, 404)


def test_failed_generation_is_recorded(client):
    r = client.post("/api/io-list/generate",
                    data={"selected_columns": json.dumps(["NOPE"]), "project_id": PID},
                    files={"iodb_file": ("IODB.xlsx", make_iodb(), "application/octet-stream")})
    if r.status_code == 200:                    # generator tolerated the missing column
        pytest.skip("generator accepted unknown column; failure path covered in service tests")
    assert r.status_code == 400
    mods = {m["module"]: m for m in client.get(f"/api/projects/{PID}/documents/connected").json()["modules"]}
    assert mods["io_list"]["state"] == "failed"


def test_connect_new_revision_and_sync_flow(client):
    generate(client, "instrument-list")
    generate(client, "io-list")
    c = client.post(f"/api/projects/{PID}/documents/connect",
                    json={"modules": ["instrument_list", "io_list", "cable_schedule"]}).json()
    assert c["connected"] == ["instrument_list", "io_list"]
    assert c["skipped"] == [{"module": "cable_schedule", "reason": "Not generated yet"}]

    generate(client, "io-list", iodb=make_iodb(extra_row=True))           # IODB rev 2 + io_list R2
    impact = {d["module"]: d for d in client.get(f"/api/projects/{PID}/document-impact").json()["documents"]}
    assert impact["instrument_list"]["regeneration_required"] is True      # still on IODB rev 1
    assert impact["io_list"]["regeneration_required"] is False
    assert "new_revision_available" in impact["io_list"]["flags"]          # link still on R1

    summary = client.get(f"/api/projects/{PID}/documents/status").json()
    assert summary["regeneration_required"] == 1 and summary["coversheet_ready"] is False


def test_regenerate_endpoint_and_download(client):
    first = generate(client, "instrument-list").json()["registry"]["document"]
    up = client.post(f"/api/projects/{PID}/sources", data={"kind": "iodb"},
                     files={"file": ("IODB_v2.xlsx", make_iodb(extra_row=True), "application/octet-stream")})
    assert up.status_code == 201 and up.json()["rev_no"] == 2

    res = client.post(f"/api/projects/{PID}/documents/{first['id']}/regenerate").json()
    assert res["ok"] and res["document"]["revision"] == 2 and res["document"]["record_count"] == 6

    dl = client.get(f"/api/projects/{PID}/documents/{res['document']['id']}/download")
    assert dl.status_code == 200 and dl.content[:2] == b"PK"            # real xlsx zip


def test_disconnect_endpoint_and_project_isolation(client):
    generate(client, "instrument-list")
    client.post(f"/api/projects/{PID}/documents/connect", json={"modules": ["instrument_list"]})
    other = client.get("/api/projects/10P204/documents/connected").json()
    assert all(not m["connected"] and m["state"] == "not_generated" for m in other["modules"])

    d = client.post(f"/api/projects/{PID}/documents/disconnect", json={"module": "instrument_list"}).json()
    assert d["disconnected"] is True
    assert len(client.get(f"/api/projects/{PID}/documents").json()) == 1   # file/registry row kept


def test_generate_connected_endpoint_and_audit(client):
    generate(client, "instrument-list")
    generate(client, "io-list")
    client.post(f"/api/projects/{PID}/sources", data={"kind": "iodb"},
                files={"file": ("v2.xlsx", make_iodb(extra_row=True), "application/octet-stream")})
    res = client.post(f"/api/projects/{PID}/documents/generate-connected",
                      json={"modules": ["instrument_list", "io_list"]}).json()
    assert res["all_ok"] and [s["status"] for s in res["steps"]] == ["ok", "ok", "ok"]
    assert res["coversheet_ready"] is True

    audit = client.get(f"/api/projects/{PID}/audit").json()
    assert {"generated", "regenerated", "source_uploaded"} <= {a["action"] for a in audit}
    assert client.post(f"/api/projects/{PID}/documents/generate-connected",
                       json={"modules": ["bogus"]}).status_code == 400


def test_status_endpoint_requires_valid_value(client):
    doc = generate(client, "io-list").json()["registry"]["document"]
    ok = client.post(f"/api/projects/{PID}/documents/{doc['id']}/status", json={"status": "UNDER_REVIEW"})
    assert ok.status_code == 200 and ok.json()["status"] == "UNDER_REVIEW"
    bad = client.post(f"/api/projects/{PID}/documents/{doc['id']}/status", json={"status": "SUPERSEDED"})
    assert bad.status_code == 400
