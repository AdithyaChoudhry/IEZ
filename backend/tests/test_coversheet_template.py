"""Coversheet Generator - "Use Uploaded Excel Coversheet Template" workflow, plus regression of the existing workflow."""
import datetime as dt
import io
import json
import re
import zipfile
from pathlib import Path

import openpyxl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace
from sqlalchemy.orm import sessionmaker

import app.database as database
from app.deps import get_current_user, get_db
from app.routers.coversheet import router as coversheet_router
from app.routers.coversheet_mdl import router as mdl_router
from app.routers.coversheet_template import router as template_router
from test_mdl import PID, search, upload, generate as old_generate
from utils import coversheet_render
from utils.coversheet_template_analyzer import analyze

ROOT = Path(__file__).resolve().parents[2]
BUNDLED = ROOT / "backend/app/templates/coversheet_template.xlsx"
URL = "/api/coversheet/template"
VALUES = {"revision": "3", "date": "2026-11-04", "prepared_by": "AB", "checked_by": "CD", "approved_by": "EF"}


@pytest.fixture()
def client(engine, db, monkeypatch):
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(coversheet_render, "soffice_path", lambda: None)       # the built-in PDF renderer
    app = FastAPI()
    for r in (mdl_router, coversheet_router, template_router):
        app.include_router(r, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=3, username="alice", email="a@x")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def tpl_bytes() -> bytes:
    return BUNDLED.read_bytes()


def second_template() -> bytes:
    """A differently laid out coversheet: labels with the value beside them, a real date cell, no revision table."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Front Page"
    ws["B2"], ws["C2"] = "Doc. No.:", "OLD-NUMBER"
    ws["B3"], ws["C3"] = "Title:", "OLD TITLE"
    ws["B4"], ws["C4"] = "Revision:", "A"
    ws["B5"], ws["C5"] = "Date:", dt.datetime(2020, 1, 1)
    ws["C5"].number_format = "dd-mmm-yy"
    ws["B6"], ws["C6"] = "Prepared By:", "x"
    ws["B7"], ws["C7"] = "Checked By:", "x"
    ws["B8"], ws["C8"] = "Approved By:", "x"
    ws.merge_cells("C3:F3")
    ws.column_dimensions["C"].width = 30
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def analyze_via_api(client, data):
    r = client.post(f"{URL}/analyze", files={"file": ("t.xlsx", data)})
    assert r.status_code == 200, r.text
    return r.json()


def gen(client, data, record_ids, mapping, sheet, formats=("xlsx",), project=PID, values=VALUES):
    body = {"project_id": project, "record_ids": record_ids, "sheet": sheet, "mapping": mapping,
            "values": values, "formats": list(formats)}
    return client.post(f"{URL}/generate", files={"file": ("t.xlsx", data)}, data={"data": json.dumps(body)})


def download(client, kind=None):
    return client.get(f"{URL}/download", params={"kind": kind} if kind else {})


def record_ids(client, q="I0003"):
    upload(client)
    return [i["mdl_record_id"] for i in search(client, q)["items"]]


# ── 1. basic Excel coversheet ────────────────────────────────────────────────
def test_analysis_detects_fields_with_confidence(client):
    a = analyze_via_api(client, tpl_bytes())
    f = a["fields"]
    assert a["sheet"] == "Coversheet" and a["images"] == 1
    assert f["document_number"]["confidence"] == "high" and set(f["document_number"]["parts"]) == {
        "job_no", "project_no", "doc_code", "serial_no"}
    assert [t["cell"] for t in f["document_description"]["targets"] if t["confirmed"]] == ["A10", "G2"]
    assert {t["cell"] for t in f["revision"]["targets"]} == {"A22", "N4"}
    assert f["date"]["targets"][0]["cell"] == "B22" and f["prepared_by"]["targets"][0]["cell"] == "I22"
    assert all(d["confidence"] == "high" for d in f.values())


def test_basic_generation_fills_values_and_keeps_template(client):
    ids = record_ids(client, "I0003-100")
    master = tpl_bytes()
    a = analyze_via_api(client, master)
    r = gen(client, master, ids, a["fields"], a["sheet"])
    assert r.status_code == 200, r.text
    assert r.json()["filename"] == "PC286-10P195-I0003-100_Coversheet.xlsx"
    resp = download(client)
    assert 'filename="PC286-10P195-I0003-100_Coversheet.xlsx"' in resp.headers["content-disposition"]
    out = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws, src = out["Coversheet"], openpyxl.load_workbook(io.BytesIO(master))["Coversheet"]
    assert (ws["G4"].value, ws["J4"].value, ws["K4"].value) == ("PC286", "10P195", "I0003")
    assert str(ws["M4"].value) == "100" and ws["N4"].value == "3"
    assert ws["G2"].value == "Instrument Datasheets for New WWTP"
    assert ws["A10"].value.startswith("DOCUMENT TITLE") and ws["A10"].value.endswith("Instrument Datasheets for New WWTP")
    assert (ws["A22"].value, ws["B22"].value) == (3, "04.11.2026")                 # template's own date format
    assert (ws["I22"].value, ws["L22"].value, ws["O22"].value) == ("AB", "CD", "EF")
    assert ws["A20"].value is None                                                   # old history cleared
    # formatting / structure preserved
    assert {str(m) for m in ws.merged_cells.ranges} == {str(m) for m in src.merged_cells.ranges}
    assert len(ws._images) == 1 and ws["F6"].value == "GAIL (INDIA) LTD" and ws["H4"].value == src["H4"].value
    assert ws["A1"].font.name == src["A1"].font.name and ws["A22"].border.top.style == src["A22"].border.top.style
    assert ws.page_setup.orientation == src.page_setup.orientation
    assert master == tpl_bytes()                                                     # master never modified


# ── 2. PDF ───────────────────────────────────────────────────────────────────
def pdf_pages(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", data))


def test_pdf_is_a4_single_page_and_named(client):
    ids = record_ids(client, "I0003-100")
    a = analyze_via_api(client, tpl_bytes())
    r = gen(client, tpl_bytes(), ids, a["fields"], a["sheet"], formats=("pdf",))
    assert r.status_code == 200, r.text
    assert r.json()["filename"] == "PC286-10P195-I0003-100_Coversheet.pdf" and r.json()["pdf_engine"] == "builtin"
    pdf = download(client).content
    assert pdf.startswith(b"%PDF") and pdf_pages(pdf) == 1
    assert re.search(rb"/MediaBox\s*\[\s*0\s+0\s+595\.27\d*\s+841\.88", pdf)         # A4 portrait


def test_both_formats_single_document_download_each(client):
    ids = record_ids(client, "I0003-100")
    a = analyze_via_api(client, tpl_bytes())
    assert gen(client, tpl_bytes(), ids, a["fields"], a["sheet"], formats=("xlsx", "pdf")).status_code == 200
    assert download(client, "xlsx").headers["content-disposition"].endswith('_Coversheet.xlsx"')
    assert download(client, "pdf").content.startswith(b"%PDF")


def test_preview_model_matches_generated_values(client):
    ids = record_ids(client, "I0003-100")
    a = analyze_via_api(client, tpl_bytes())
    body = {"project_id": PID, "record_ids": ids, "sheet": a["sheet"], "mapping": a["fields"], "values": VALUES}
    r = client.post(f"{URL}/preview", files={"file": ("t.xlsx", tpl_bytes())}, data={"data": json.dumps(body)})
    assert r.status_code == 200, r.text
    texts = {c["t"] for c in r.json()["model"]["cells"]}
    assert "Instrument Datasheets for New WWTP" in texts and "04.11.2026" in texts and r.json()["model"]["images"]


# ── 3. multiple documents ────────────────────────────────────────────────────
def test_multiple_documents_zip(client):
    ids = record_ids(client, "I0003")
    assert len(ids) == 3
    a = analyze_via_api(client, tpl_bytes())
    r = gen(client, tpl_bytes(), ids, a["fields"], a["sheet"], formats=("xlsx", "pdf"))
    assert r.status_code == 200 and r.json()["kind"] == "zip" and r.json()["count"] == 3
    z = zipfile.ZipFile(io.BytesIO(download(client).content))
    assert sorted(z.namelist()) == sorted(f"PC286-10P195-I0003-{n}_Coversheet.{e}" for n in (100, 200, 300) for e in ("xlsx", "pdf"))
    titles = {}
    for n in z.namelist():
        if n.endswith(".xlsx"):
            titles[n] = openpyxl.load_workbook(io.BytesIO(z.read(n)))["Coversheet"]["G2"].value
    assert titles["PC286-10P195-I0003-300_Coversheet.xlsx"] == "Instrument Datasheets for ZLD Unit"


def test_document_values_come_from_the_mdl_not_the_browser(client):
    ids = record_ids(client, "I0003-100")
    a = analyze_via_api(client, tpl_bytes())
    body = {"project_id": PID, "record_ids": ids, "sheet": a["sheet"], "mapping": a["fields"],
            "values": {**VALUES, "document_number": "HACKED", "document_description": "HACKED"}}
    assert client.post(f"{URL}/generate", files={"file": ("t.xlsx", tpl_bytes())}, data={"data": json.dumps(body)}).status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(download(client).content))["Coversheet"]
    assert "HACKED" not in (ws["G2"].value or "") and ws["K4"].value == "I0003"


def test_requires_selection_mdl_and_known_record(client):
    a = analyze_via_api(client, tpl_bytes())
    assert gen(client, tpl_bytes(), [], a["fields"], a["sheet"]).status_code == 400
    assert gen(client, tpl_bytes(), ["x"], a["fields"], a["sheet"], project="10P555").status_code == 400   # no MDL
    upload(client)
    assert gen(client, tpl_bytes(), ["no-such-record"], a["fields"], a["sheet"]).status_code == 409


# ── 4. second, different template ────────────────────────────────────────────
def test_second_template_layout_and_date_format(client):
    ids = record_ids(client, "I0003-100")
    tb = second_template()
    a = analyze_via_api(client, tb)
    f = a["fields"]
    assert a["sheet"] == "Front Page"
    assert [t["cell"] for t in f["document_number"]["targets"]] == ["C2"] and f["document_number"]["confidence"] == "high"
    assert f["document_description"]["targets"][0]["cell"] == "C3"
    assert f["date"]["targets"][0]["cell"] == "C5" and f["approved_by"]["targets"][0]["cell"] == "C8"
    assert gen(client, tb, ids, f, a["sheet"]).status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(download(client).content))["Front Page"]
    assert ws["C2"].value == "PC286-10P195-I0003-100"                               # whole number in one cell
    assert ws["C3"].value == "Instrument Datasheets for New WWTP" and ws["C4"].value == "3"
    assert ws["C5"].value == dt.datetime(2026, 11, 4) and ws["C5"].number_format == "dd-mmm-yy"
    assert ws["C3"].coordinate in {str(m).split(":")[0] for m in ws.merged_cells.ranges}
    assert (ws["C6"].value, ws["C7"].value, ws["C8"].value) == ("AB", "CD", "EF")


# ── 5. low confidence: nothing is written to a guessed cell ──────────────────
def ambiguous_template() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cover"
    ws["A1"], ws["B1"] = "Document Reference Ref", "?"
    ws["A2"], ws["B2"] = "Subject Matter Title", "?"
    ws["A3"], ws["B3"] = "Rev No", "0"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_low_confidence_fields_must_be_confirmed(client):
    ids = record_ids(client, "I0003-100")
    tb = ambiguous_template()
    a = analyze_via_api(client, tb)
    f = a["fields"]
    assert f["document_number"]["confidence"] != "high" and not any(t["confirmed"] for t in f["document_number"]["targets"])
    assert f["document_description"]["confidence"] != "high"
    r = gen(client, tb, ids, f, a["sheet"])
    assert r.status_code == 422 and "Document Number" in r.json()["detail"]         # blocked, nothing guessed
    f["document_number"]["targets"] = [{"cell": "B1", "mode": "replace", "confirmed": True}]    # engineer's correction
    f["document_description"]["targets"] = [{"cell": "B2", "mode": "replace", "confirmed": True}]
    for k in ("date", "prepared_by", "checked_by", "approved_by"):
        f[k]["skipped"] = True
    assert gen(client, tb, ids, f, a["sheet"], values={"revision": "5"}).status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(download(client).content))["Cover"]
    assert (ws["B1"].value, ws["B2"].value, ws["A1"].value) == ("PC286-10P195-I0003-100", "Instrument Datasheets for New WWTP", "Document Reference Ref")


def test_unconfirmed_target_is_never_written(client):
    ids = record_ids(client, "I0003-100")
    a = analyze_via_api(client, tpl_bytes())
    for t in a["fields"]["document_description"]["targets"]:
        if t["cell"] == "G2":
            t["confirmed"] = False
    assert gen(client, tpl_bytes(), ids, a["fields"], a["sheet"]).status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(download(client).content))["Coversheet"]
    assert ws["G2"].value.startswith("INSTRUMENT DATASHEET FOR STORM WATER")          # untouched


def test_error_messages(client):
    ids = record_ids(client, "I0003-100")
    assert client.post(f"{URL}/analyze", files={"file": ("t.xls", b"x")}).status_code == 400
    assert client.post(f"{URL}/analyze", files={"file": ("t.xlsx", b"not a zip")}).status_code == 400
    assert client.post(f"{URL}/analyze", files={"file": ("t.xlsx", b"")}).status_code == 400
    wb = openpyxl.Workbook(); buf = io.BytesIO(); wb.save(buf)
    assert client.post(f"{URL}/analyze", files={"file": ("t.xlsx", buf.getvalue())}).status_code == 422   # empty sheet
    a = analyze_via_api(client, tpl_bytes())
    bad = gen(client, tpl_bytes(), ids, a["fields"], a["sheet"], values={**VALUES, "date": "31/31/2026"})
    assert bad.status_code == 422 and "valid date" in bad.json()["detail"]
    empty = gen(client, tpl_bytes(), ids, a["fields"], a["sheet"], values={**VALUES, "prepared_by": ""})
    assert empty.status_code == 422 and "Prepared By" in empty.json()["detail"]
    a["fields"]["revision"]["targets"][0]["cell"] = "G2"                              # not a formula cell, fine
    wb = openpyxl.load_workbook(BUNDLED); wb["Coversheet"]["A22"] = "=1+1"; buf = io.BytesIO(); wb.save(buf)
    f = gen(client, buf.getvalue(), ids, analyze_via_api(client, tpl_bytes())["fields"], "Coversheet")
    assert f.status_code == 422 and "formula" in f.json()["detail"]


# ── 6. old workflow unchanged ────────────────────────────────────────────────
def test_existing_workflow_still_works(client):
    upload(client)
    rec = search(client, "I0003-100")["items"][0]
    assert old_generate(client, PID, rec["mdl_record_id"]).status_code == 200
    r = client.get("/api/coversheet/download")
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    assert ws["G2"].value == "Instrument Datasheets for New WWTP" and "_CoverSheet.xlsx" in r.headers["content-disposition"]
    assert old_generate(client).status_code == 200                                    # manual (no MDL) mode


def test_libreoffice_is_preferred_when_present_and_fallback_on_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(coversheet_render, "soffice_path", lambda: "/fake/soffice")

    def boom(*a, **k):
        calls.append(1)
        raise coversheet_render.RenderError("no")
    monkeypatch.setattr(coversheet_render, "render_pdf_libreoffice", boom)
    from utils.coversheet_excel_fill import fill_template
    tb = tpl_bytes()
    a = analyze(tb)
    out, _ = fill_template(tb, a["sheet"], a["fields"], {**VALUES, "document_number": "PC286-10P195-I0003-100",
                                                          "document_description": "T"})
    pdf, engine = coversheet_render.render_pdf(out, a["sheet"], tb)
    assert calls and engine == "builtin" and pdf.startswith(b"%PDF")
