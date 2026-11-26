"""Excel and PDF Master Document Lists in both Cover Sheet workflows: the uploaded-Excel-template workflow (project MDL register)
and the MDL-Driven builder, every MDL x template format combination, with the same documents from either format."""
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_coversheet_template import VALUES, analyze_via_api, client, gen, tpl_bytes  # noqa: E402,F401
from test_mdl import PID, OTHER, search, upload  # noqa: E402
import app.models.deliverable_cover  # noqa: E402,F401
import test_coversheet_builder as B  # noqa: E402

HEAD = ["S.NO", "DISCIPLINE", "DOC NO", "DESCRIPTION", "REV", "REMARKS"]
LONG = ("Instrument Cable Schedule for the New Waste Water Treatment Plant including the Tertiary Treatment, "
        "Sludge Handling and Chemical Dosing Areas")
DOCS = [("PC286-10P195-J0001-105", LONG, "01"), ("PC286-10P195-J0001-101", "Instrument List for New WWTP", "00"),
        ("PC286-10P195-I0003-110", "Instrument Datasheet - Pressure Transmitter", "007"),
        ("PC286-10P195-I0003-110", "Instrument Datasheet - Pressure Transmitter", "008")]
DOCS += [(f"PC286-10P195-I0100-{i:03d}", f"Loop Diagram Sheet Set {i:03d}", f"{i % 3:02d}") for i in range(1, 61)]


def rows(extra=()):
    out = [["", "", "", "INSTRUMENTATION", "", ""]]
    out += [[str(n), "Instrumentation", d, t, r, ""] for n, (d, t, r) in enumerate(DOCS, 1)]
    return out + [list(x) for x in extra]


def xlsx_mdl(extra=()) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MDL"
    ws.append(["MASTER DOCUMENT LIST"]); ws.append([]); ws.append(HEAD)
    for r in rows(extra):
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def pdf_mdl(extra=(), **kw) -> bytes:
    st = getSampleStyleSheet()["BodyText"]
    st.fontSize, st.leading = 8, 10
    data = [HEAD] + [[Paragraph(c, st) if i == 3 else c for i, c in enumerate(r)] for r in rows(extra)]
    t = Table(data, colWidths=[35, 90, 140, 300, 40, 80], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    b = io.BytesIO()
    SimpleDocTemplate(b, pagesize=landscape(A4), **kw).build([Paragraph("MASTER DOCUMENT LIST", getSampleStyleSheet()["Title"]), t])
    return b.getvalue()


def up(c, data, name="MDL_R2.pdf", project=PID, allow=True):
    return c.post(f"/api/projects/{project}/coversheet/mdl/upload", files={"file": (name, data)},
                  data={"allow_pdf": "true"} if allow else {})


def all_records(c, project=PID):
    return search(c, "", project, limit=500)["items"]


# ── workflow 1: uploaded Excel template + project MDL register ───────────────
def test_pdf_and_excel_registers_hold_the_same_documents(client):
    assert upload(client, xlsx_mdl(), name="MDL_R2.xlsx").status_code == 200
    excel = [(r["document_number"], r["document_name"], r["discipline"]) for r in all_records(client)]
    r = up(client, pdf_mdl())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document_count"] == len(DOCS) and body["sheet"] == "PDF table" and body["revision_label"] == "R2" and body["unresolved"] == []
    recs = all_records(client)
    assert [(x["document_number"], x["document_name"], x["discipline"]) for x in recs] == excel
    assert [x["revision"] for x in recs] == [d[2] for d in DOCS]                          # leading zeros kept, in order
    dup = [x for x in recs if x["document_number"].endswith("I0003-110")]
    assert [d["revision"] for d in dup] == ["007", "008"] and len({d["mdl_record_id"] for d in dup}) == 2
    assert all(d["duplicate_document_number"] for d in dup)
    assert next(x for x in recs if x["document_number"].endswith("J0001-105"))["document_name"] == LONG      # wrapped title


@pytest.mark.parametrize("formats", [("xlsx",), ("xlsx", "pdf")])
def test_cover_from_a_pdf_mdl_equals_the_cover_from_the_excel_mdl(client, formats):
    tpl = tpl_bytes()
    a = analyze_via_api(client, tpl)
    books = {}
    for kind, data, name in (("excel", xlsx_mdl(), "MDL.xlsx"), ("pdf", pdf_mdl(), "MDL.pdf")):
        assert up(client, data, name).status_code == 200
        rid = next(x["mdl_record_id"] for x in all_records(client) if x["document_number"].endswith("J0001-105"))
        r = gen(client, tpl, [rid], a["fields"], a["sheet"], formats=formats)
        assert r.status_code == 200, r.text
        out = client.get("/api/coversheet/template/download", params={"kind": "xlsx"} if len(formats) > 1 else {}).content
        ws = openpyxl.load_workbook(io.BytesIO(out))[a["sheet"]]
        books[kind] = ({c.coordinate: (c.value, c.style_id) for row in ws.iter_rows() for c in row}, sorted(map(str, ws.merged_cells.ranges)))
    assert books["excel"] == books["pdf"]
    values = {v for v, _ in books["pdf"][0].values()}
    assert LONG in values and "J0001" in values and VALUES["approved_by"] in values


def test_pdf_is_only_accepted_by_the_template_workflow(client):
    assert upload(client, xlsx_mdl(), name="MDL.xlsx").status_code == 200
    r = up(client, pdf_mdl(), allow=False)                                                  # the existing workflow: unchanged
    assert r.status_code == 422 and "Unsupported MDL file type" in r.json()["detail"]
    assert client.get(f"/api/projects/{PID}/coversheet/mdl").json()["file_name"] == "MDL.xlsx"


def _text_only_pdf():
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=A4)
    for i in range(1, 6):
        c.drawString(50, 700 - 20 * i, f"{i}  PC286-10P195-E00{i}-001  Single line diagram {i}  R0")
    c.save()
    return b.getvalue()


@pytest.mark.parametrize("data, name, message", [
    (b"%PDF-1.7\nnot really a pdf" + b"\0" * 100, "m.pdf", "Invalid PDF file"),
    (b"hello", "m.pdf", "does not contain a PDF"),
    (pdf_mdl(encrypt=StandardEncryption("secret")), "m.pdf", "password-protected"),
    (B.pdf_mdl_scanned(), "m.pdf", "scanned|No document records"),
    (_text_only_pdf(), "m.pdf", "No document table"),
    (pdf_mdl(), "m.xlsx", "Rename it to .pdf"),
    (b"not a zip", "m.xlsx", "could not be opened"),
    (b"abc", "m.docx", "Unsupported MDL file type"),
])
def test_bad_files_are_explained_and_the_active_mdl_is_kept(client, data, name, message):
    import re
    assert upload(client, xlsx_mdl(), name="good.xlsx").status_code == 200
    r = up(client, data, name)
    assert r.status_code == 422 and re.search(message, r.json()["detail"]), r.json()
    assert client.get(f"/api/projects/{PID}/coversheet/mdl").json()["file_name"] == "good.xlsx"


def test_rows_with_gaps_are_flagged_and_completed_by_hand_only(client):
    extra = [["65", "Instrumentation", "", "Hook Up Drawing without a number", "00", ""]]
    r = up(client, pdf_mdl(extra))
    assert r.status_code == 200, r.text
    u = r.json()["unresolved"]
    assert len(u) == 1 and u[0]["missing"] == ["document number"] and u[0]["document_name"].startswith("Hook Up") and u[0]["revision"] == "00"
    assert r.json()["document_count"] == len(DOCS) and any("were not imported" in w for w in r.json()["warnings"])
    assert not any("Hook Up" in x["document_name"] for x in all_records(client))             # never completed by guessing
    url = f"/api/projects/{PID}/coversheet/mdl/records"
    assert client.post(url, json={"document_number": "  ", "document_name": "x"}).status_code == 422
    ok = {"document_number": "PC286-10P195-J0009-001", "document_name": u[0]["document_name"], "revision": "00"}
    r = client.post(url, json=ok)
    assert r.status_code == 201 and r.json()["document_count"] == len(DOCS) + 1 and r.json()["record"]["revision"] == "00"
    assert client.post(url, json=ok).status_code == 422                                     # not twice
    assert any(x["document_number"] == "PC286-10P195-J0009-001" for x in all_records(client))
    upload(client, xlsx_mdl(), name="MDL.xlsx")
    assert client.post(url, json=ok).status_code == 422                                     # an Excel register is corrected in Excel


def test_registers_stay_separate_per_project_and_replacing_drops_old_documents(client):
    assert up(client, pdf_mdl()).status_code == 200
    rid = all_records(client)[0]["mdl_record_id"]
    assert client.get(f"/api/projects/{OTHER}/coversheet/mdl").json()["uploaded"] is False
    assert client.get(f"/api/projects/{OTHER}/coversheet/mdl/document/{rid}").status_code == 404
    assert upload(client, B.excel_mdl(), name="other.xlsx").status_code in (200, 422)
    assert up(client, xlsx_mdl([["99", "Instrumentation", "NEW-1-X-1", "Newer doc", "0", ""]]), "newer.xlsx").status_code == 200
    r = up(client, pdf_mdl([["99", "Instrumentation", "NEW-2-X-2", "Newest doc", "0", ""]]), "newest.pdf")
    nums = [x["document_number"] for x in all_records(client)]
    assert r.status_code == 200 and "NEW-2-X-2" in nums and "NEW-1-X-1" not in nums


def test_a_pdf_register_serves_the_downstream_deliverable_cover(client, db):
    from app.services import deliverable_covers as DC
    assert up(client, pdf_mdl()).status_code == 200
    r = DC.resolve(db, PID, "cable_schedule")
    assert r["record"]["document_number"] == "PC286-10P195-J0001-105"
    DC.save(db, PID, "cable_schedule", "", "alice", project_info={"client": "C"},
            revisions=[{"rev_no": "01", "date": "2026-11-27", "prepared_by": "AB"}])
    r = DC.resolve(db, PID, "cable_schedule")
    data, _ = DC.cover_workbook(db, r)
    assert r["status"] == "AVAILABLE" and r["revision"] == "01" and openpyxl.load_workbook(io.BytesIO(data)).worksheets


# ── workflow 2: MDL-Driven builder, every combination ────────────────────────
@pytest.fixture()
def builder(tmp_path, monkeypatch):
    from app.deps import get_current_user
    from app.routers import coversheet_builder as CB
    from utils import coversheet_render
    monkeypatch.setattr(CB, "_STORE", tmp_path / "store")
    monkeypatch.setattr(coversheet_render, "soffice_path", lambda: None)
    app = FastAPI()
    app.include_router(CB.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, username="tester")
    return TestClient(app)


@pytest.mark.parametrize("mdl_kind", ["excel", "pdf"])
@pytest.mark.parametrize("tpl_kind", ["excel", "pdf"])
def test_builder_every_mdl_and_template_format(builder, mdl_kind, tpl_kind):
    data, name = (xlsx_mdl(), "MDL.xlsx") if mdl_kind == "excel" else (pdf_mdl(), "MDL.pdf")
    m = B.extract(builder, data, name)
    assert [(r["document_number"], r["document_name"], r["revision"]) for r in m["records"]] == DOCS
    rec = m["records"][0]
    tpl, tname = (B.BUNDLED.read_bytes(), "cs.xlsx") if tpl_kind == "excel" else (B.pdf_template(), "cs.pdf")
    a = B.analyze(builder, tpl, tname, tpl_kind)
    fields = B.confirm_all(a["fields"])
    fields["document_description"]["skipped"] = True
    body = {"extraction_id": m["extraction_id"], "record_id": rec["id"], "sheet": a.get("sheet"), "mapping": fields,
            "values": B.VALUES, "formats": ["xlsx"]}
    r = B.post(builder, "generate", tpl, tname, body)
    assert r.status_code == 200, r.text
    out = builder.get(f"{B.URL}/download").content
    if tpl_kind == "excel":
        text = " ".join(str(c.value) for ws in openpyxl.load_workbook(io.BytesIO(out)) for row in ws.iter_rows() for c in row if c.value)
        assert "J0001" in text and LONG in text
    else:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(out)) as pdf:
            text = " ".join((p.extract_text() or "") for p in pdf.pages)
        # the template's old number stays in the text layer under the white-out, so its letters interleave with the new ones
        line = next(ln for ln in text.splitlines() if ln.startswith("Document No."))
        letters = iter(line)
        assert all(ch in letters for ch in "PC286-10P195-J0001-105") and "Instrument Cable Schedule" in text


def test_builder_flags_a_row_without_a_number_and_reports_protected_pdfs(builder):
    m = B.extract(builder, pdf_mdl([["65", "Instrumentation", "", "Hook Up Drawing without a number", "00", ""]]), "m.pdf")
    bad = [r for r in m["records"] if r["status"] == "error"]
    assert len(bad) == 1 and not bad[0]["document_number"] and m["summary"]["records"] == len(DOCS) + 1
    r = builder.post(f"{B.URL}/mdl/extract", files={"file": ("p.pdf", pdf_mdl(encrypt=StandardEncryption("secret")))})
    assert r.status_code == 422 and "password-protected" in r.json()["detail"]
