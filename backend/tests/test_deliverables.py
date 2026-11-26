"""Centralised cover sheets + Excel / PDF deliverables: the MDL document is matched by keyword (engineer's pick when
not sure), the cover details are entered once, a saved cover is available at once (no approval step, never a DRAFT), the cover replaces the template's own
cover sheet (never a second one), projects never leak, and the PDF is the same workbook."""
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.database as database
import app.models.deliverable_cover  # noqa: F401  (register the table)
import app.models.mdl  # noqa: F401
from app.auth.models import ApprovalRequest
from app.deps import get_current_user, get_db

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cable_schedule_corrections import ROWS, iodb  # noqa: E402
from test_cable_schedule_layout import template as inst_template  # noqa: E402
from test_mdl import make_mdl  # noqa: E402
from cable_header_helpers import generate as post_generate  # noqa: E402

PID, OTHER = "PRJ-1", "PRJ-2"
MDL_ROWS = [
    (1, "Instrumentation", "PC286-10P195-J0001-105", "Instrument Cable Schedule for New WWTP", "A", ""),
    (2, "Instrumentation", "PC286-10P195-J0001-101", "Instrument List for New WWTP", "A", ""),
    (3, "Instrumentation", "PC286-10P195-J0001-102", "I/O List for New WWTP", "A", ""),
    (4, "Instrumentation", "PC286-10P195-J0001-103", "IO List for Storm Water Guard Pond", "A", ""),
    (5, "Instrumentation", "PC286-10P195-I0003-110", "Instrument Datasheet - Pressure Transmitter", "A", ""),
    (6, "Instrumentation", "PC286-10P195-I0003-111", "Instrument Datasheet - Level Transmitter", "A", ""),
    (7, "Instrumentation", "PC286-10P195-J0002-001", "Loop Wiring Diagrams for New WWTP", "A", ""),
]
REVS = [{"rev_no": "R0", "date": "2026-11-23", "description": "ISSUED FOR REVIEW", "prepared_by": "AB",
         "checked_by": "CD", "approved_by": "EF"}]
INFO = {"client": "GAIL", "pmc": "PMC", "contractor": "WABAG", "project_description": "NEW WWTP"}


@pytest.fixture()
def client(engine, db, monkeypatch):
    from app.routers import cable_schedule, coversheet_mdl, deliverables
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(deliverables, "SessionLocal", sessionmaker(bind=engine))
    deliverables._outputs.clear()
    app = FastAPI()
    for r in (coversheet_mdl.router, deliverables.router, cable_schedule.router):
        app.include_router(r, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=5, username="alice", email="a@x")
    app.dependency_overrides[get_db] = lambda: db
    c = TestClient(app)
    r = c.post(f"/api/projects/{PID}/coversheet/mdl/upload",
               files={"file": ("MDL_R4.xlsx", make_mdl(MDL_ROWS))}, data={"confirm_replace": "true"})
    assert r.status_code == 200, r.text
    return c


def cover(c, doc_type, project=PID, **kw):
    return c.get("/api/deliverables/cover", params={"doc_type": doc_type, "project_id": project, **kw}).json()


def save(c, doc_type, **body):
    r = c.put("/api/deliverables/cover", json={"project_id": PID, "doc_type": doc_type, **body})
    assert r.status_code == 200, r.text


def generate_cable(c, project=PID):
    r = post_generate(c, files={"iodb_file": ("IODB.xlsx", iodb(ROWS[:5])), "template_file": ("t.xlsx", inst_template())},
               data={"jb_column": "JUNCTION BOX TAG NO.", "tag_column": "TAG NO", "output_mode": "WITH_SUMMARY",
                     "include_schedule": "true", **({"project_id": project} if project else {})})
    assert r.status_code == 200, r.text
    return r.json(), c.get("/api/cable-schedule/download").content


# ── matching ─────────────────────────────────────────────────────────────────
def test_no_project_no_cover(client):
    r = cover(client, "cable_schedule", project="")
    assert r["status"] == "NOT_AVAILABLE" and "Select a project" in r["message"]


def test_single_keyword_match_is_used_and_details_are_asked_for(client):
    r = cover(client, "cable_schedule")
    assert r["match"] == "keyword" and r["record"]["document_number"] == "PC286-10P195-J0001-105"
    assert r["status"] == "NOT_AVAILABLE" and "not entered" in r["message"]


def test_ambiguous_match_asks_the_engineer_then_uses_the_pick(client):
    r = cover(client, "io_list")
    assert r["record"] is None and len(r["candidates"]) == 2 and "Choose" in r["message"]
    pick = next(x for x in r["candidates"] if x["document_number"].endswith("-103"))
    save(client, "io_list", mdl_record_id=pick["mdl_record_id"])
    r = cover(client, "io_list")
    assert r["match"] == "selected" and r["record"]["document_number"] == "PC286-10P195-J0001-103"


def test_datasheet_matches_its_instrument_type_only(client):
    r = cover(client, "datasheet", sub_key="pt", sub_label="Pressure Transmitter")
    assert r["record"]["document_number"] == "PC286-10P195-I0003-110"
    r = cover(client, "datasheet", sub_key="tt", sub_label="Temperature Transmitter")
    assert r["record"] is None                                    # never another instrument type's datasheet


def test_other_project_never_sees_this_projects_documents(client):
    save(client, "cable_schedule", project_info=INFO, revisions=REVS)
    r = cover(client, "cable_schedule", project=OTHER)
    assert r["status"] == "NOT_AVAILABLE" and r["record"] is None and "Master Document List" in r["message"]


# ── generation: availability, placement ──────────────────────────────────────
def _cover_sheet(xlsx):
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    return wb, wb.worksheets[0]


def test_a_saved_cover_is_available_at_once_and_carries_the_entered_names_without_a_draft_mark(client, db):
    save(client, "cable_schedule", project_info=INFO, revisions=REVS)
    r = cover(client, "cable_schedule")
    assert r["status"] == "AVAILABLE" and "approved" not in r and r["legacy_approval"] is None     # no approval step, none invented
    res, xlsx = generate_cable(client)
    assert res["cover"]["applied"] and res["cover"]["draft"] is False and "approved" not in res["cover"]
    assert res["filename"] == "PC286-10P195-J0001-105_R0_Cable_Schedule.xlsx"
    wb, ws = _cover_sheet(xlsx)
    assert ws.title == "COVER SHEET" and wb.sheetnames[1] == "Cable Schedule -INST"   # cover first, schedule kept
    assert ws["K4"].value == "J0001" and ws["M4"].value == "105" and "Instrument Cable Schedule" in ws["G2"].value
    assert not ws.oddHeader.center.text                                                  # no DRAFT mark
    texts = {str(c.value) for row in ws.iter_rows() for c in row if c.value is not None}
    assert {"AB", "CD", "EF"} <= texts                                                   # exactly what the engineer typed
    assert db.query(ApprovalRequest).count() == 0                                        # nothing was sent to the approval queue
    save(client, "cable_schedule", revisions=REVS + [{**REVS[0], "rev_no": "R1"}])       # a later edit needs no approval either
    assert cover(client, "cable_schedule")["status"] == "AVAILABLE" and cover(client, "cable_schedule")["revision"] == "R1"


def test_the_approval_request_endpoint_is_gone(client):
    save(client, "cable_schedule", project_info=INFO, revisions=REVS)
    r = client.post("/api/deliverables/cover/request-approval", json={
        "project_id": PID, "doc_type": "cable_schedule", "submitted_by_name": "Alice", "submitted_by_id": "E1"})
    assert r.status_code in (404, 405)


def test_template_cover_sheet_is_replaced_not_duplicated(client):
    save(client, "cable_schedule", project_info=INFO, revisions=REVS)
    wb = openpyxl.load_workbook(io.BytesIO(inst_template()))
    wb.create_sheet("COVERSHEET", 0)["A1"] = "TEMPLATE COVER"
    buf = io.BytesIO(); wb.save(buf)
    r = post_generate(client, files={"iodb_file": ("IODB.xlsx", iodb(ROWS[:5])), "template_file": ("t.xlsx", buf.getvalue())},
                    data={"jb_column": "JUNCTION BOX TAG NO.", "tag_column": "TAG NO", "output_mode": "WITH_SUMMARY",
                          "include_schedule": "true", "project_id": PID})
    assert r.status_code == 200, r.text
    out = openpyxl.load_workbook(io.BytesIO(client.get("/api/cable-schedule/download").content))
    assert [n for n in out.sheetnames if "COVER" in n.upper()] == ["COVERSHEET"]
    assert out.sheetnames[0] == "COVERSHEET" and out["COVERSHEET"]["A1"].value != "TEMPLATE COVER"


def test_without_a_cover_the_engineering_output_is_unchanged_and_the_reason_is_given(client):
    res, xlsx = generate_cable(client, project=None)
    assert res["cover"]["applied"] is False and "Select a project" in res["cover"]["message"]
    assert res["filename"] == "Cable_Schedule.xlsx" and openpyxl.load_workbook(io.BytesIO(xlsx)).sheetnames[0] == "Cable Schedule -INST"


def test_a_cover_problem_never_blocks_generation(client):
    save(client, "cable_schedule", project_info=INFO, revisions=REVS)
    r = post_generate(client, files={"iodb_file": ("IODB.xlsx", iodb(ROWS[:5])), "template_file": ("t.xlsx", inst_template()),
                                                          "cover_template_file": ("bad.xlsx", b"not a workbook")},
                    data={"jb_column": "JUNCTION BOX TAG NO.", "tag_column": "TAG NO", "output_mode": "WITH_SUMMARY",
                          "include_schedule": "true", "project_id": PID})
    assert r.status_code == 200 and r.json()["cover"]["applied"] is False and "custom cover" in r.json()["cover"]["message"].lower()


# ── downloads ────────────────────────────────────────────────────────────────
def test_info_and_pdf_are_the_same_deliverable(client):
    from utils import deliverable_output as DO
    save(client, "cable_schedule", project_info=INFO, revisions=REVS)
    res, xlsx = generate_cable(client)
    info = client.get("/api/deliverables/cable_schedule/info").json()
    assert info["filename"] == res["filename"] and info["cover"]["draft"] is False
    if DO.soffice() is None:
        r = client.post("/api/deliverables/cable_schedule/pdf")
        assert r.status_code == 503 and "Excel generation completed successfully" in r.json()["detail"]
        return
    assert client.get("/api/deliverables/cable_schedule/pdf").status_code == 409          # not started yet
    st = client.post("/api/deliverables/cable_schedule/pdf").json()
    import time
    for _ in range(240):
        if st["status"] != "running":
            break
        time.sleep(0.5)
        st = client.get("/api/deliverables/cable_schedule/pdf/status").json()
    assert st["status"] == "done", st
    r = client.get("/api/deliverables/cable_schedule/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert 'PC286-10P195-J0001-105_R0_Cable_Schedule.pdf' in r.headers["content-disposition"]
    from pypdf import PdfReader
    pages = PdfReader(io.BytesIO(r.content)).pages
    text = " ".join(p.extract_text() or "" for p in pages)
    assert "DRAFT" not in text and "PT-001" in text and "Instrument Cable Schedule" in text


def test_pdf_before_generation_is_refused(client):
    assert client.get("/api/deliverables/io_list/pdf").status_code == 404
    assert client.post("/api/deliverables/io_list/pdf").status_code == 404
