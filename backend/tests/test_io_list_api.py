"""I/O List API: the stored standard template is used without an upload; the cover snapshot, IO_BASIS review and isolation."""
import hashlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_io_list_standard import COLS, M1, cover, df_of, fake_renderer, fixture_rows, loops  # noqa: E402
from utils.io_list_document import STANDARD_TEMPLATE  # noqa: E402

SHEETS = ["TABLE OF CONTENTS", "ABBREVIATION", "IO_BASIS", "IO List", "IO Summary"]


@pytest.fixture()
def client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import io_list
    # the renderer is a fixed fake here (real rendering is tested in test_io_list_standard.py)
    monkeypatch.setattr(io_list, "render_sections", lambda wb, sheets=None, lock=None: fake_renderer({"IO List": 4})(wb, sheets))
    app = FastAPI()
    app.include_router(io_list.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, username="alice")
    return TestClient(app)


def iodb(rows=None) -> bytes:
    b = io.BytesIO()
    df_of(rows if rows is not None else fixture_rows()).to_excel(b, sheet_name="IODB", index=False)
    return b.getvalue()


def generate(client, rows=None, mode="WITH_SUMMARY", **extra):
    return client.post("/api/io-list/generate", files={"iodb_file": ("I.xlsx", iodb(rows))},
                       data={"selected_columns": json.dumps(COLS), "filters": "{}", "output_mode": mode, **extra})


def test_composition_without_a_template_lists_the_standard_sheets(client):
    r = client.post("/api/io-list/composition", data={"output_mode": "WITH_SUMMARY"})
    assert r.status_code == 200, r.text
    assert [s["name"] for s in r.json()["sheets"]] == SHEETS


def test_generate_without_any_upload_uses_the_stored_template(client):
    before = hashlib.sha256(STANDARD_TEMPLATE.read_bytes()).hexdigest()
    r = generate(client)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["sheets"] == SHEETS and j["basis"]["pages"]["iolist"] == 4
    wb = openpyxl.load_workbook(io.BytesIO(client.get("/api/io-list/download").content))
    assert wb.sheetnames == SHEETS
    ws = wb["IO_BASIS"]
    assert ws["A10"].value == 1 and ws["B10"].value == "TYPE-M1"
    assert hashlib.sha256(STANDARD_TEMPLATE.read_bytes()).hexdigest() == before          # the master is never overwritten


def test_two_requests_do_not_contaminate_each_other(client):
    a = generate(client, loops("MS", 2, "TYPE-M1", M1, "PUMP"))
    wa = openpyxl.load_workbook(io.BytesIO(client.get("/api/io-list/download").content))["IO_BASIS"]
    b = generate(client, loops("PK", 2, "Vendor Package", [("DI", "RUNNING"), ("AI", "SIGNAL")], "UV PACKAGE", "-"))
    wb_ = openpyxl.load_workbook(io.BytesIO(client.get("/api/io-list/download").content))["IO_BASIS"]
    assert a.status_code == b.status_code == 200
    texts = lambda ws: {str(c.value) for r in ws.iter_rows(min_row=10) for c in r if c.value}
    assert "RUN INDICATION" in texts(wa) and "RUN INDICATION" not in texts(wb_)
    assert "RUNNING" in texts(wb_) and "RUNNING" not in texts(wa)


def test_basis_endpoint_and_engineer_choices_reach_the_workbook(client):
    a = [("DI", "RUN INDICATION")]
    b = [("DI", "FAULT INDICATION")]
    rows = loops("MS", 2, "TYPE-M1", a, "PUMP", start=1) + loops("MS", 1, "TYPE-M1", b, "PUMP", start=3)
    r = client.post("/api/io-list/basis", files={"iodb_file": ("I.xlsx", iodb(rows))}, data={"filters": "{}"})
    assert r.status_code == 200, r.text
    c = r.json()["classes"][0]
    assert c["status"] == "Review Required" and c["representative"] == "MS-001" and "MS-003" in c["candidates"]
    g = generate(client, rows, basis_overrides=json.dumps({c["key"]: "MS-003"}), basis_names=json.dumps({c["key"]: "MOTOR (SUBMERSIBLE)"}))
    assert g.status_code == 200, g.text
    ws = openpyxl.load_workbook(io.BytesIO(client.get("/api/io-list/download").content))["IO_BASIS"]
    assert ws["F10"].value == "FAULT INDICATION" and ws["C10"].value == "MOTOR (SUBMERSIBLE)"


def test_filters_apply_to_the_basis_like_the_io_list(client):
    r = client.post("/api/io-list/basis", files={"iodb_file": ("I.xlsx", iodb())}, data={"filters": json.dumps({"SUB SYSTEM": ["VFD"]})})
    assert [c["type"] for c in r.json()["classes"]] == ["TYPE-M2"]


def test_an_empty_or_unusable_iodb_is_reported(client):
    r = client.post("/api/io-list/basis", files={"iodb_file": ("I.xlsx", iodb([]))}, data={"filters": "{}"})
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        assert r.json()["error"]


def test_the_uploaded_template_path_is_unchanged(client):
    from test_cable_schedule_layout import template
    t = openpyxl.Workbook()
    t.active.title = "My Cover Page"
    buf = io.BytesIO()
    t.save(buf)
    r = client.post("/api/io-list/generate", files={"iodb_file": ("I.xlsx", iodb()), "template_file": ("T.xlsx", buf.getvalue())},
                    data={"selected_columns": json.dumps(COLS), "filters": "{}", "output_mode": "WITHOUT_SUMMARY"})
    assert r.status_code == 200, r.text
    assert r.json()["sheets"] == ["My Cover Page", "IO List"] and r.json().get("basis") is None


def test_the_cover_snapshot_fills_the_headers_and_is_the_cover_that_is_inserted(client, monkeypatch):
    from app.services import io_list_cover
    cv = cover()
    res = {"doc_type": "io_list", "doc_label": "I/O List", "project_id": "P1", "sub_key": "", "status": "AVAILABLE", "record": {"document_number": "PC999-10P999-I0001-202", "document_name": "I/O LIST - TEST PLANT"},
           "revision": "02", "approved": True, "message": "Approved cover sheet."}
    calls = []
    monkeypatch.setattr(io_list_cover, "snapshot", lambda pid, tpl=None: calls.append(pid) or {"resolution": res, "cover": cv, "warnings": [], "message": ""})
    r = generate(client, project_id="P1")
    assert r.status_code == 200, r.text
    assert calls == ["P1"]                                                                 # resolved once for the whole request
    wb = openpyxl.load_workbook(io.BytesIO(client.get("/api/io-list/download").content))
    assert wb.sheetnames[0].upper().replace(" ", "") == "COVERSHEET" and wb.sheetnames[1:] == SHEETS
    from utils.io_list_header import field_cells
    f = {k: c.value for k, c in field_cells(wb["IO_BASIS"]).items()}
    assert f["doc_no"] == "10P999-I0001-202" and f["rev"] == "02" and f["date"] == "24-11-2026" and f["client"] == "TEST CLIENT LTD"
    assert r.json()["cover"]["applied"] is True


def test_a_missing_cover_is_reported_and_the_workbook_is_still_produced(client):
    r = generate(client)
    assert r.status_code == 200 and r.json()["cover"]["applied"] is False
    assert any("cover" in w.lower() for w in r.json()["basis"]["warnings"])


def test_location_reaches_the_headers_and_the_pdf_download_is_the_verified_document(client):
    from pypdf import PdfReader
    from app.routers import deliverables
    from utils.io_list_header import field_cells
    client.app.include_router(deliverables.router, prefix="/api")
    r = generate(client, location="Test Town")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["basis"]["location"] == {"value": "Test Town", "source": "entered for this document"} and "_pdf" not in j["basis"]
    wb = openpyxl.load_workbook(io.BytesIO(client.get("/api/io-list/download").content))
    assert [field_cells(wb[n])["location"].value for n in SHEETS[:3]] == ["Test Town"] * 3
    assert client.post("/api/deliverables/io_list/pdf").json()["status"] == "done"           # kept from generation, not converted again
    pdf = PdfReader(io.BytesIO(client.get("/api/deliverables/io_list/pdf").content))
    toc = wb["TABLE OF CONTENTS"]
    assert len(pdf.pages) == j["basis"]["total_pages"] == sum(toc.cell(r, 15).value for r in range(9, 15)) == 8     # no cover: its line is 0
    a3 = [p for p in pdf.pages if float(p.mediabox.width) > 1000]
    assert len(a3) == 4


def test_a_placeholder_location_is_refused(client):
    r = generate(client, location="TBD")
    assert r.status_code == 400 and "Location" in r.json()["detail"]


def test_an_uploaded_template_gets_the_corrected_summary_and_reports_what_it_does_not_count(client):
    t = openpyxl.Workbook()
    t.active.title = "My Cover Page"
    buf = io.BytesIO()
    t.save(buf)
    rows = fixture_rows()
    rows[0] = {**rows[0], "SIGNAL I/O TYPE": None}
    r = client.post("/api/io-list/generate", files={"iodb_file": ("I.xlsx", iodb(rows)), "template_file": ("T.xlsx", buf.getvalue())},
                    data={"selected_columns": json.dumps(COLS), "filters": "{}", "output_mode": "WITH_SUMMARY"})
    assert r.status_code == 200, r.text
    assert r.json()["basis"]["summary"]["excluded"] == 1
    wb = openpyxl.load_workbook(io.BytesIO(client.get("/api/io-list/download").content))
    assert "NOT SET" not in [c.value for row in wb["IO Summary"].iter_rows() for c in row]
    assert wb["IO List"].page_setup.paperSize == 8 and wb["IO Summary"].page_setup.paperSize == 9


def test_regenerating_a_standard_io_list_rebuilds_the_whole_document(client, monkeypatch):
    from app.services import document_registry as DR
    from utils import io_list_builder, io_list_pagination
    monkeypatch.setattr(io_list_builder, "build_io_list_document",
                        lambda *a, _f=io_list_builder.build_io_list_document, **k: _f(*a, renderer=fake_renderer(), **k))
    params = {"selected_columns": COLS, "filters": {}, "output_mode": "WITH_SUMMARY", "standard_template": True, "location": "Town"}
    out, name, err, _ = DR._run_generator("io_list", iodb(), STANDARD_TEMPLATE.read_bytes(), params, "")
    assert err is None, err
    wb = openpyxl.load_workbook(io.BytesIO(out))
    assert wb.sheetnames == SHEETS and wb["IO_BASIS"]["B10"].value == "TYPE-M1" and wb["TABLE OF CONTENTS"]["O9"].value is not None
