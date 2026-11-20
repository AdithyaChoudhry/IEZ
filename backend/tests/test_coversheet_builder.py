"""Coversheet Builder: MDL extraction (Excel / PDF / scanned), review edits, Excel + PDF templates, signatures, validation."""
import io
import json
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from app.deps import get_current_user
from app.routers import coversheet_builder as CB
from utils import coversheet_mdl_extract as MX
from utils import coversheet_render

ROOT = Path(__file__).resolve().parents[2]
BUNDLED = ROOT / "backend/app/templates/coversheet_template.xlsx"
REAL_MDL = Path("/Users/adithyachoudhrym/Downloads/Input Files/PC286-10P195-A0001-001_R4_MDL.xlsx")
URL = "/api/coversheet/builder"
VALUES = {"revision": "2", "revision_date": "2026-11-20", "prepared_by": "AKB", "checked_by": "AG", "approved_by": "VE"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(CB, "_STORE", tmp_path / "store")
    monkeypatch.setattr(coversheet_render, "soffice_path", lambda: None)
    app = FastAPI()
    app.include_router(CB.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, username="tester")
    return TestClient(app)


# ── inputs ───────────────────────────────────────────────────────────────────
def excel_mdl(rows=None, headers=None) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cover"
    ws["A1"] = "MASTER DOCUMENT LIST"
    ws2 = wb.create_sheet("Document Register")
    ws2["A1"] = "Project XYZ - Deliverables"
    ws2.append([])
    ws2.append(headers or ["Sl.", "Client Document No.", "Title of Document", "Brief Description", "Rev.", "Doc Type"])
    for r in rows or [
        (1, "PC286-10P195-I0003-100", "Instrument Datasheets for New WWTP", "Datasheets of all field instruments", "R1", "DS"),
        (None, None, "INSTRUMENTATION", None, None, None),                              # heading row
        (2, "PC286-10P195-I0003-200", "Instrument Index", "", "R0", "LIST"),            # no description
        (3, "PC286-10P195-I0003-200", "Instrument Index (Storm Water)", "Index", "R0", "LIST"),   # duplicate number
        (4, "PC286-10P195-I0004-001", "", "Loop drawings", "A", "DWG"),                  # no name
    ]:
        ws2.append(list(r))
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def pdf_mdl_tables() -> bytes:
    """Two pages; the table continues on page 2 with its header repeated; header/footer bands on each page."""
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=landscape(A4))
    W, H = landscape(A4)
    cols = [40, 90, 290, 560, 700, 790]
    head = ["S.No", "Document Number", "Document Title", "Description", "Rev"]
    data = [(str(i), f"PC286-10P195-D00{i:02d}-101", f"General arrangement drawing {i}", f"GA of unit {i}", "R0") for i in range(1, 19)]

    def table(rows, y0):
        y = y0
        for row in [head] + rows:
            for j in range(len(cols) - 1):
                c.rect(cols[j], y - 18, cols[j + 1] - cols[j], 18)
                c.setFont("Helvetica", 8)
                c.drawString(cols[j] + 3, y - 12, row[j])
            y -= 18

    for page, rows in ((1, data[:12]), (2, data[12:])):
        c.setFont("Helvetica", 9)
        c.drawString(40, H - 25, "MASTER DOCUMENT LIST  Rev 4  Doc No PC286-10P195-A0001-001")     # page header band
        c.drawString(40, 15, f"Page {page} of 2   Printed 20.11.2026")                         # footer band
        table(rows, H - 60)
        c.showPage()
    c.save()
    return b.getvalue()


def pdf_mdl_text() -> bytes:
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=A4)
    W, H = A4
    c.setFont("Helvetica", 10)
    y = H - 120
    for i in range(1, 6):
        c.drawString(50, y, f"{i}  PC286-10P195-E00{i}-001  Electrical single line diagram {i}  R{i % 2}")
        y -= 20
    c.save()
    return b.getvalue()


def pdf_mdl_scanned() -> bytes:
    img = Image.new("RGB", (1700, 2200), "white")
    d = ImageDraw.Draw(img)
    from PIL import ImageFont
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 34)
    except Exception:
        font = ImageFont.load_default()
    y = 400
    for i in range(1, 5):
        d.text((120, y), f"{i}  PC286-10P195-M00{i}-001  Mechanical layout drawing {i}", fill="black", font=font)
        y += 90
    b = io.BytesIO()
    img.save(b, "PDF", resolution=200)
    return b.getvalue()


def pdf_template(size=A4) -> bytes:
    """A boxed coversheet: label boxes with the value box to the right, a revision table, signature row, a logo."""
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=size)
    W, H = size
    c.setFillColorRGB(0.1, 0.3, 0.6)
    c.rect(40, H - 80, 60, 40, fill=1, stroke=0)                       # "logo"
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(120, H - 65, "ACME ENGINEERING - DOCUMENT COVER SHEET")
    rows = [("Document No.", H - 130), ("Document Title", H - 160), ("Description", H - 190)]
    for lab, y in rows:
        c.rect(40, y, 140, 26)
        c.rect(180, y, W - 220, 26)
        c.setFont("Helvetica", 9)
        c.drawString(45, y + 9, lab)
    c.drawString(185, H - 121, "OLD-NUMBER-001")                         # an old value in the number box
    # revision table: header row at the bottom, entry row above it
    xs = [40, 90, 170, 330, 420, 500, W - 40]
    hdr = ["Rev", "Date", "Remarks", "Prepared By", "Checked By", "Approved By"]
    y_entry, y_hdr, y_sign = 160, 140, 110
    for j in range(len(hdr)):
        c.rect(xs[j], y_entry, xs[j + 1] - xs[j], 20)
        c.rect(xs[j], y_hdr, xs[j + 1] - xs[j], 20)
        c.drawString(xs[j] + 3, y_hdr + 6, hdr[j])
    c.rect(40, y_sign, 290, 30)
    c.drawString(45, y_sign + 11, "Signature")
    for j in (3, 4, 5):
        c.rect(xs[j], y_sign, xs[j + 1] - xs[j], 30)
    c.showPage()
    c.save()
    return b.getvalue()


def signature(color="navy", w=300, h=100) -> bytes:
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    d.line([(10, h - 20), (w * 0.3, 15), (w * 0.55, h - 25), (w - 10, 20)], fill=color, width=6)
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def second_template() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Front Page"
    ws["B2"], ws["C2"] = "Doc. No.:", "OLD"
    ws["B3"], ws["C3"] = "Title:", "OLD TITLE"
    ws["B4"], ws["C4"] = "Description:", "OLD DESCRIPTION"
    ws["B5"], ws["C5"] = "Revision:", "A"
    ws["B6"], ws["C6"] = "Date:", "01.01.2020"
    ws["B7"], ws["C7"] = "Prepared By:", "x"
    ws["B8"], ws["C8"] = "Checked By:", "x"
    ws["B9"], ws["C9"] = "Approved By:", "x"
    ws["B10"] = "Prepared by Signature"
    ws.merge_cells("C10:E12")
    ws.merge_cells("C3:F3")
    ws.column_dimensions["C"].width = 30
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def extract(client, data, name):
    r = client.post(f"{URL}/mdl/extract", files={"file": (name, data)})
    assert r.status_code == 200, r.text
    return r.json()


def analyze(client, data, name, kind=None):
    r = client.post(f"{URL}/template/analyze", files={"file": (name, data)}, data={"kind": kind} if kind else {})
    assert r.status_code == 200, r.text
    return r.json()


def confirm_all(fields):
    for f in fields.values():
        for t in f["targets"]:
            t["confirmed"] = True
        for p in (f.get("parts") or {}).values():
            p["confirmed"] = True
    return fields


def post(client, ep, tpl, name, body, sigs=None):
    files = {"file": (name, tpl)}
    for k, v in (sigs or {}).items():
        files[k] = (f"{k}.png", v)
    return client.post(f"{URL}/{ep}", files=files, data={"data": json.dumps(body)})


# ── MDL ──────────────────────────────────────────────────────────────────────
def test_excel_mdl_unusual_headers_flags_and_headings(client):
    res = extract(client, excel_mdl(), "mdl.xlsx")
    assert res["sheet"] == "Document Register"                     # the Cover sheet is never used
    cols = {c["field"]: c["header"] for c in res["columns"]}
    assert cols["document_number"] == "Client Document No." and cols["document_name"] == "Title of Document"
    assert cols["document_description"] == "Brief Description" and cols["revision"] == "Rev." and cols["document_type"] == "Doc Type"
    recs = res["records"]
    assert len(recs) == 4 and res["rows_ignored"] == 1               # heading row ignored
    by = {r["document_name"]: r for r in recs}
    assert by["Instrument Datasheets for New WWTP"]["status"] == "ok"
    assert by["Instrument Datasheets for New WWTP"]["revision"] == "R1"
    assert any(f["field"] == "document_description" for f in by["Instrument Index"]["flags"])
    assert by["Instrument Index"]["status"] == "warning"             # duplicate number
    bad = next(r for r in recs if not r["document_name"])
    assert bad["status"] == "error"
    assert res["summary"]["duplicates"] == 1 and res["summary"]["errors"] == 1


def test_mdl_with_only_description_column_uses_it_as_the_name():
    data = excel_mdl(rows=[(1, "AB-12-CD-001", "Plot plan", "A")], headers=["S.No", "DOC NO", "DESCRIPTION", "REV"])
    res = MX.extract(data, "m.xlsx")
    assert res["name_from_description"] is True
    r = res["records"][0]
    assert r["document_name"] == "Plot plan" and r["document_description"] == ""


def test_pdf_mdl_tables_across_pages_with_repeated_header(client):
    res = extract(client, pdf_mdl_tables(), "mdl.pdf")
    assert res["method"] == "pdf-table" and res["pages"] == 2
    nums = [r["document_number"] for r in res["records"]]
    assert len(nums) == 18 and nums[0] == "PC286-10P195-D0001-101" and nums[-1] == "PC286-10P195-D0018-101"
    assert "PC286-10P195-A0001-001" not in nums                    # the page-header document number is not a record
    r = res["records"][13]
    assert r["document_name"] == "General arrangement drawing 14" and r["document_description"] == "GA of unit 14" and r["revision"] == "R0"


def test_pdf_mdl_text_lines_are_flagged(client):
    res = extract(client, pdf_mdl_text(), "mdl.pdf")
    assert res["method"] == "pdf-text" and len(res["records"]) == 5
    r = res["records"][0]
    assert r["document_number"] == "PC286-10P195-E001-001" and r["document_name"] == "Electrical single line diagram 1"
    assert r["status"] == "warning"


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")
def test_scanned_pdf_mdl_is_read_by_ocr(client):
    res = extract(client, pdf_mdl_scanned(), "scan.pdf")
    assert res["method"] == "ocr"
    nums = {r["document_number"] for r in res["records"]}
    assert "PC286-10P195-M001-001" in nums and len(nums) >= 3
    assert all(r["status"] != "ok" for r in res["records"])          # OCR values are always flagged


def test_bad_mdl_files(client):
    assert client.post(f"{URL}/mdl/extract", files={"file": ("m.txt", b"hello")}).status_code == 422
    assert client.post(f"{URL}/mdl/extract", files={"file": ("m.xlsx", b"")}).status_code == 422
    assert client.post(f"{URL}/mdl/extract", files={"file": ("m.xlsx", b"not a zip")}).status_code == 422
    assert client.post(f"{URL}/mdl/extract", files={"file": ("m.pdf", b"%PDF-1.4 broken")}).status_code == 422
    wb = openpyxl.Workbook(); wb.active.append(["A", "B"]); b = io.BytesIO(); wb.save(b)
    r = client.post(f"{URL}/mdl/extract", files={"file": ("m.xlsx", b.getvalue())})
    assert r.status_code == 422 and "header row" in r.json()["detail"]


def test_review_correction_and_manual_add(client):
    res = extract(client, excel_mdl(), "mdl.xlsx")
    eid = res["extraction_id"]
    bad = next(r for r in res["records"] if r["status"] == "error")
    r = client.put(f"{URL}/mdl/{eid}/records/{bad['id']}", json={"document_name": "Loop Drawings"})
    assert r.status_code == 200
    rec = r.json()["record"]
    assert rec["document_name"] == "Loop Drawings" and rec["edited"] and rec["status"] == "ok"
    assert rec["original"]["document_name"] == ""
    again = client.get(f"{URL}/mdl/{eid}").json()                  # stored on the server
    assert next(x for x in again["records"] if x["id"] == bad["id"])["document_name"] == "Loop Drawings"
    assert client.post(f"{URL}/mdl/{eid}/records", json={"document_number": "X-1"}).status_code == 400
    add = client.post(f"{URL}/mdl/{eid}/records", json={"document_number": "AB-01-02", "document_name": "Extra"}).json()
    assert add["record"]["method"] == "manual" and add["summary"]["records"] == 5


@pytest.mark.skipif(not REAL_MDL.exists(), reason="real MDL not available")
def test_real_mdl_excel():
    res = MX.extract(REAL_MDL.read_bytes(), REAL_MDL.name)
    assert res["summary"]["records"] > 100
    assert all(r["document_number"] for r in res["records"])


# ── Excel template ───────────────────────────────────────────────────────────
def _mdl_pick(client, name="Instrument Datasheets for New WWTP"):
    res = extract(client, excel_mdl(), "mdl.xlsx")
    rec = next(r for r in res["records"] if r["document_name"] == name)
    return res["extraction_id"], rec


def _pics(xlsx: bytes, sheet_index=0) -> int:
    z = zipfile.ZipFile(io.BytesIO(xlsx))
    return sum(z.read(n).decode("utf-8", "ignore").count("<xdr:pic>") + z.read(n).decode("utf-8", "ignore").count("<xdr:pic ")
               for n in z.namelist() if n.startswith("xl/drawings/drawing") and n.endswith(".xml"))


def test_excel_template_all_fields_and_signatures(client):
    eid, rec = _mdl_pick(client)
    tpl = BUNDLED.read_bytes()
    a = analyze(client, tpl, "cs.xlsx", "excel")
    assert a["kind"] == "excel" and a["sheet"] == "Coversheet"
    f = a["fields"]
    assert f["document_number"]["parts"] and f["document_name"]["targets"]
    assert f["revision"]["confidence"] == "high"
    fields = confirm_all(f)
    fields["document_description"]["skipped"] = True
    fields["sig_prepared"]["targets"] = [{"cell": "I21", "mode": "image", "confirmed": True}]
    fields["sig_checked"]["targets"] = [{"cell": "L21", "mode": "image", "confirmed": True}]
    fields["sig_approved"]["targets"] = [{"cell": "O21", "mode": "image", "confirmed": True}]
    body = {"extraction_id": eid, "record_id": rec["id"], "sheet": a["sheet"], "mapping": fields, "values": VALUES,
            "formats": ["xlsx", "pdf"]}

    base_pics = _pics(tpl)
    for sigs, extra in (({}, 0), ({"sig_prepared": signature()}, 1),
                        ({"sig_prepared": signature(), "sig_checked": signature("black"), "sig_approved": signature("green", 200, 200)}, 3)):
        r = post(client, "generate", tpl, "cs.xlsx", body, sigs)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["files"] == [f"{rec['document_number']}_Coversheet.pdf", f"{rec['document_number']}_Coversheet.xlsx"]
        x = client.get(f"{URL}/download", params={"kind": "xlsx"})
        assert x.status_code == 200 and x.headers["content-type"].startswith("application/vnd.openxml")
        assert _pics(x.content) == base_pics + extra                  # the template logo is kept, signatures added
        ws = openpyxl.load_workbook(io.BytesIO(x.content))["Coversheet"]
        assert ws["G4"].value == "PC286" and ws["K4"].value == "I0003" and str(ws["M4"].value) == "100"   # number box keeps its numeric type
        assert "Instrument Datasheets for New WWTP" in ws["A10"].value
        cell = {k: fields[k]["targets"][0]["cell"] for k in ("prepared_by", "checked_by", "approved_by", "revision_date")}
        assert (ws[cell["prepared_by"]].value, ws[cell["checked_by"]].value, ws[cell["approved_by"]].value) == ("AKB", "AG", "VE")
        assert ws[cell["revision_date"]].value == "20.11.2026"     # written in the template's own date format
        p = client.get(f"{URL}/download", params={"kind": "pdf"})
        assert p.status_code == 200 and p.content[:4] == b"%PDF"


def test_signature_keeps_aspect_ratio_inside_box(client):
    from utils.coversheet_builder import add_images
    tpl = second_template()
    out, warn = add_images(tpl, "Front Page", [("C10", signature(w=400, h=100), "sig_prepared")])
    z = zipfile.ZipFile(io.BytesIO(out))
    xml = next(z.read(n).decode() for n in z.namelist() if n.startswith("xl/drawings/drawing"))
    import re
    cx, cy = map(int, re.search(r'<xdr:ext cx="(\d+)" cy="(\d+)"', xml).groups())
    assert abs(cx / cy - 4.0) < 0.02                                 # 400 x 100 stays 4:1
    # the merged box C10:E12 is (30+8.43+8.43 chars) x 3 rows; the picture fits inside it
    ws = openpyxl.load_workbook(io.BytesIO(tpl))["Front Page"]
    from utils.coversheet_layout import col_width_px
    box_w = (col_width_px(30) + 2 * col_width_px(8.43)) * 9525
    assert cx <= box_w and cy <= 3 * 20 * 9525


def test_second_excel_layout_with_description_and_signature(client):
    eid, rec = _mdl_pick(client)
    tpl = second_template()
    a = analyze(client, tpl, "front.xlsx")
    f = a["fields"]
    assert f["document_name"]["targets"][0]["cell"] == "C3"
    assert f["document_description"]["targets"][0]["cell"] == "C4"
    assert f["sig_prepared"]["targets"][0]["cell"] == "C10"
    body = {"extraction_id": eid, "record_id": rec["id"], "sheet": a["sheet"], "mapping": confirm_all(f), "values": VALUES}
    r = post(client, "generate", tpl, "front.xlsx", body, {"sig_prepared": signature()})
    assert r.status_code == 200, r.text
    ws = openpyxl.load_workbook(io.BytesIO(client.get(f"{URL}/download").content))["Front Page"]
    assert ws["C2"].value == rec["document_number"] and ws["C3"].value == rec["document_name"]
    assert ws["C4"].value == "Datasheets of all field instruments"
    assert ws["C5"].value == "2" and ws["C7"].value == "AKB"
    assert "C3:F3" in {str(m) for m in ws.merged_cells.ranges}        # merges kept
    assert ws.column_dimensions["C"].width == 30


def test_excel_preview_includes_signature(client):
    eid, rec = _mdl_pick(client)
    tpl = second_template()
    f = confirm_all(analyze(client, tpl, "front.xlsx")["fields"])
    body = {"extraction_id": eid, "record_id": rec["id"], "sheet": "Front Page", "mapping": f, "values": VALUES}
    r = post(client, "preview", tpl, "front.xlsx", body, {"sig_prepared": signature()})
    assert r.status_code == 200, r.text
    m = r.json()["model"]
    assert len(m["images"]) == 1
    assert any(c["t"] == rec["document_name"] for c in m["cells"])


# ── PDF template ─────────────────────────────────────────────────────────────
def test_pdf_template_detect_fill_preserve(client):
    import pdfplumber
    from pypdf import PdfReader
    eid, rec = _mdl_pick(client)
    tpl = pdf_template()
    a = analyze(client, tpl, "cs.pdf", "pdf")
    assert a["kind"] == "pdf" and a["pages"][0]["width"] == pytest.approx(A4[0]) and a["page_images"]
    f = a["fields"]
    for k in ("document_number", "document_name", "document_description", "revision", "revision_date",
              "prepared_by", "checked_by", "approved_by", "sig_prepared", "sig_checked", "sig_approved"):
        assert f[k]["targets"], k
    num = f["document_number"]["targets"][0]
    assert num["clear"] is True and "OLD-NUMBER" in num["current"]      # an old value is whited out
    rev_box = f["revision"]["targets"][0]["box"]
    assert rev_box[1] < A4[1] - 160 - 20 + 2                          # the entry row ABOVE the bottom header row
    body = {"extraction_id": eid, "record_id": rec["id"], "mapping": confirm_all(f), "values": VALUES}
    sigs = {"sig_prepared": signature(), "sig_checked": signature("black"), "sig_approved": signature("green", 150, 150)}
    r = post(client, "generate", tpl, "cs.pdf", body, sigs)
    assert r.status_code == 200, r.text
    assert r.json()["files"] == [f"{rec['document_number']}_Coversheet.pdf"]
    out = client.get(f"{URL}/download").content
    page = PdfReader(io.BytesIO(out)).pages[0]
    assert (float(page.mediabox.width), float(page.mediabox.height)) == pytest.approx(A4)
    with pdfplumber.open(io.BytesIO(out)) as pdf:
        p = pdf.pages[0]
        text = p.extract_text()
        assert "ACME ENGINEERING - DOCUMENT COVER SHEET" in text           # original text kept
        bx = num["box"]                                                    # drawn last in the whited-out number box
        drawn = "".join(ch["text"] for ch in p.chars if bx[0] <= ch["x0"] <= bx[2] and bx[1] <= ch["top"] <= bx[3])
        assert drawn.endswith(rec["document_number"])
        white = [r for r in p.rects if r.get("non_stroking_color") in ((1, 1, 1), [1, 1, 1], (1.0, 1.0, 1.0))
                 and r["x0"] <= bx[0] + 2 and r["x1"] >= bx[2] - 2]
        assert white, "the old value is covered"
        assert "Instrument Datasheets for New WWTP" in text
        assert "Datasheets of all field instruments" in text and "20.11.2026" in text and "AKB" in text
        assert len(p.images) == 3                                          # three signatures
        assert any(abs(r["x0"] - 40) < 1 and r["width"] == pytest.approx(60) for r in p.rects)   # logo block kept
    pv = post(client, "preview", tpl, "cs.pdf", body, sigs)
    assert pv.status_code == 200 and pv.json()["pages"][0]["png"]


def test_pdf_template_landscape_and_manual_box(client):
    from pypdf import PdfReader
    eid, rec = _mdl_pick(client)
    size = landscape(A4)
    tpl = pdf_template(size)
    f = confirm_all(analyze(client, tpl, "cs.pdf")["fields"])
    f["document_description"] = {"targets": [{"page": 1, "box": [400, 300, 700, 330], "confirmed": True, "clear": False}]}
    body = {"extraction_id": eid, "record_id": rec["id"], "mapping": f, "values": VALUES}
    r = post(client, "generate", tpl, "cs.pdf", body)
    assert r.status_code == 200, r.text
    page = PdfReader(io.BytesIO(client.get(f"{URL}/download").content)).pages[0]
    assert (float(page.mediabox.width), float(page.mediabox.height)) == pytest.approx(size)


# ── validation ───────────────────────────────────────────────────────────────
def test_validation_errors(client):
    eid, rec = _mdl_pick(client)
    tpl = second_template()
    f = confirm_all(analyze(client, tpl, "front.xlsx")["fields"])
    good = {"extraction_id": eid, "record_id": rec["id"], "sheet": "Front Page", "mapping": f, "values": VALUES}

    def gen(body, sigs=None, name="front.xlsx", data=tpl):
        return post(client, "generate", data, name, body, sigs)

    assert gen({**good, "values": {**VALUES, "revision": ""}}).status_code == 422          # missing revision
    r = gen({**good, "values": {**VALUES, "revision_date": "31.02.2026"}})
    assert r.status_code == 422 and "not a valid date" in r.json()["detail"]
    assert gen({**good, "record_id": ""}).status_code == 400                                 # no document selected
    assert gen({**good, "record_id": "nope"}).status_code == 409
    bad = next(x for x in client.get(f"{URL}/mdl/{eid}").json()["records"] if x["status"] == "error")
    assert gen({**good, "record_id": bad["id"]}).status_code == 409                          # incomplete record
    r = client.post(f"{URL}/generate", files={"file": ("front.xlsx", tpl), "sig_prepared": ("s.gif", b"GIF89a")},
                    data={"data": json.dumps(good)})
    assert r.status_code == 400                                                              # signature type
    r = client.post(f"{URL}/generate", files={"file": ("front.xlsx", tpl), "sig_prepared": ("s.png", b"not an image")},
                    data={"data": json.dumps(good)})
    assert r.status_code == 400
    nosig = json.loads(json.dumps(good)); nosig["mapping"]["sig_prepared"]["targets"] = []
    r = gen(nosig, {"sig_prepared": signature()})
    assert r.status_code == 422 and "location is not confirmed" in r.json()["detail"]
    nodesc_rec = next(x for x in client.get(f"{URL}/mdl/{eid}").json()["records"] if x["document_name"] == "Instrument Index")
    r = gen({**good, "record_id": nodesc_rec["id"]})
    assert r.status_code == 422 and "no description" in r.json()["detail"]
    assert client.post(f"{URL}/template/analyze", files={"file": ("t.xls", b"x")}).status_code == 400
    assert client.post(f"{URL}/template/analyze", files={"file": ("t.docx", b"x")}).status_code == 400
    assert client.post(f"{URL}/template/analyze", files={"file": ("t.pdf", b"%PDF-broken")}).status_code == 422
    r = client.post(f"{URL}/template/analyze", files={"file": ("t.xlsx", tpl)}, data={"kind": "pdf"})
    assert r.status_code == 400 and "PDF template was selected" in r.json()["detail"]
