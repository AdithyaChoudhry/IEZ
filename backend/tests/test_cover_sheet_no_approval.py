"""Cover Sheet Generator: no software approval workflow. A saved cover sheet is available at once to every generator of its
project, shows exactly the names the engineer entered (nothing fabricated, nothing blanked), earlier approval requests stay
as history without deciding availability, no new request is ever created, other document types keep their approval queue,
and projects / unauthenticated callers stay separated."""
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deliverables import (INFO, MDL_ROWS, OTHER, PID, REVS, client, cover, generate_cable, save)  # noqa: E402,F401
from app.auth.models import ApprovalRequest  # noqa: E402
from app.services import deliverable_covers as DC  # noqa: E402
from app.models.deliverable_cover import DeliverableCover  # noqa: E402


def _history(db, status, cover_id=None, **kw):
    req = ApprovalRequest(request_type="coversheet", status=status, submitted_by_name="Old", submitted_by_id="E0",
                          reviewed_by_name=kw.get("by"), review_notes=kw.get("notes"), payload_json="{}")
    db.add(req)
    db.flush()
    c = db.query(DeliverableCover).filter_by(project_id=PID, doc_type="cable_schedule").one()
    c.approval_request_id, c.approval_fingerprint = req.id, "stale-fingerprint-from-before"
    db.commit()
    return req.id


def test_generate_save_download_link_need_no_approval(client, db):
    save(client, "cable_schedule", project_info=INFO, revisions=REVS)
    assert cover(client, "cable_schedule")["status"] == "AVAILABLE"                     # available as soon as it is saved
    res, xlsx = generate_cable(client)                                                  # linked to the Cable Schedule, Excel
    assert res["cover"]["applied"] and res["cover"]["draft"] is False
    assert openpyxl.load_workbook(io.BytesIO(xlsx)).worksheets[0].title == "COVER SHEET"
    assert db.query(ApprovalRequest).count() == 0                                       # no approval request anywhere


def test_io_list_and_cable_schedule_both_see_the_saved_cover(client, db):
    from app.routers import deliverables
    r = cover(client, "io_list")
    pick = next(x for x in r["candidates"] if x["document_number"].endswith("-102"))
    save(client, "io_list", mdl_record_id=pick["mdl_record_id"], project_info=INFO, revisions=REVS)
    save(client, "cable_schedule", project_info=INFO, revisions=REVS)
    for doc, number in (("io_list", "PC286-10P195-J0001-102"), ("cable_schedule", "PC286-10P195-J0001-105")):
        r = cover(client, doc)
        assert r["status"] == "AVAILABLE" and r["record"]["document_number"] == number and r["revision"] == "R0"
    wb = openpyxl.Workbook(); wb.active.title = "IO LIST"; buf = io.BytesIO(); wb.save(buf)
    data, name, info = deliverables.finalize(5, "io_list", PID, buf.getvalue(), "IO_List.xlsx", db=db)
    assert info["applied"] and info["draft"] is False and name == "PC286-10P195-J0001-102_R0_I_O_List.xlsx"
    assert openpyxl.load_workbook(io.BytesIO(data)).sheetnames[0] == "COVER SHEET"


def test_names_are_printed_exactly_as_entered_and_nothing_is_invented(client, db):
    blank = [{**REVS[0], "checked_by": "", "approved_by": ""}]
    save(client, "cable_schedule", project_info=INFO, revisions=blank)
    r = DC.resolve(db, PID, "cable_schedule")
    data, _ = DC.cover_workbook(db, r)
    ws = openpyxl.load_workbook(io.BytesIO(data)).worksheets[0]
    texts = {str(c.value) for row in ws.iter_rows() for c in row if c.value is not None}
    assert "AB" in texts and "CD" not in texts and "EF" not in texts                    # blank stays blank, no name is added
    save(client, "cable_schedule", revisions=REVS)
    data, _ = DC.cover_workbook(db, DC.resolve(db, PID, "cable_schedule"))
    ws = openpyxl.load_workbook(io.BytesIO(data)).worksheets[0]
    assert {"AB", "CD", "EF"} <= {str(c.value) for row in ws.iter_rows() for c in row if c.value is not None}


def test_latest_revision_date_is_still_extracted_from_the_cover(client, db):
    from utils import cable_header_meta as M
    revs = [{**REVS[0]}, {**REVS[0], "rev_no": "R1", "date": "2026-12-05", "description": "UPDATED"}]
    save(client, "cable_schedule", project_info=INFO, revisions=revs)
    data, _ = DC.cover_workbook(db, DC.resolve(db, PID, "cable_schedule"))
    h = M.read_cover_header(data)
    assert str(h.values.get("revision") or "") == "R1" and "05" in str(h.values.get("date") or "")


@pytest.mark.parametrize("status", ["pending", "rejected", "approved"])
def test_legacy_approval_records_stay_usable_and_untouched(client, db, status):
    save(client, "cable_schedule", project_info=INFO, revisions=REVS)
    rid = _history(db, status, by="Lead", notes="old note")
    r = cover(client, "cable_schedule")
    assert r["status"] == "AVAILABLE" and r["revision"] == "R0"                        # a valid cover stays usable
    assert r["legacy_approval"]["id"] == rid and r["legacy_approval"]["status"] == status   # history reported as recorded ...
    assert "approved" not in r                                                         # ... never turned into an approval
    row = db.query(ApprovalRequest).get(rid)
    assert (row.status, row.review_notes, row.reviewed_by_name) == (status, "old note", "Lead")  # record not modified or deleted
    save(client, "cable_schedule", revisions=REVS + [{**REVS[0], "rev_no": "R1"}])      # changed after an old approval: still available
    assert cover(client, "cable_schedule")["status"] == "AVAILABLE"
    assert db.query(ApprovalRequest).get(rid).status == status
    res, _ = generate_cable(client)
    assert res["cover"]["applied"] is True and res["cover"]["draft"] is False


def test_projects_stay_separate(client, db):
    save(client, "cable_schedule", project_info=INFO, revisions=REVS)
    r = cover(client, "cable_schedule", project=OTHER)
    assert r["status"] == "NOT_AVAILABLE" and r["record"] is None
    assert client.get("/api/deliverables/covers", params={"project_id": OTHER}).json()["covers"] == []
    assert client.get("/api/deliverables/cover/details", params={"doc_type": "cable_schedule", "project_id": OTHER}).json()["revisions"] == []
    assert len(client.get("/api/deliverables/covers", params={"project_id": PID}).json()["covers"]) == 1


def test_unauthenticated_callers_are_refused(db):
    from app.routers import deliverables
    from app.deps import get_db
    app = FastAPI()
    app.include_router(deliverables.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    c = TestClient(app)
    assert c.get("/api/deliverables/cover", params={"doc_type": "cable_schedule", "project_id": PID}).status_code in (401, 403)
    assert c.put("/api/deliverables/cover", json={"project_id": PID, "doc_type": "cable_schedule"}).status_code in (401, 403)


def test_other_document_types_keep_their_approval_queue_and_cover_requests_are_refused(db):
    from app.deps import get_current_user, get_db
    from app.routers import approvals
    app = FastAPI()
    app.include_router(approvals.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=5, username="alice", email="a@x")
    app.dependency_overrides[get_db] = lambda: db
    c = TestClient(app)
    body = {"submitted_by_name": "Alice", "submitted_by_id": "E1"}
    r = c.post("/api/approvals", json={"request_type": "coversheet", **body})
    assert r.status_code == 410 and "no longer need approval" in r.json()["detail"]
    assert db.query(ApprovalRequest).count() == 0
    for kind in ("spec", "tbe"):                                                         # unchanged for everything else
        r = c.post("/api/approvals", json={"request_type": kind, **body})
        assert r.status_code == 201 and r.json()["status"] == "pending"
    assert db.query(ApprovalRequest).filter_by(request_type="spec").count() == 1
