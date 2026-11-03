"""I/O List and Cable Schedule output modes: template sheets + list/schedule (+ summary when selected)."""
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import workbook_assembly as wa  # noqa: E402
from utils.template_processor import process_cable_schedule, process_io_list  # noqa: E402

WITHOUT, WITH = wa.WITHOUT_SUMMARY, wa.WITH_SUMMARY
CABLE_TEMPLATE = ROOT / "Cable_schedule.xlsx"
CABLE_IODB = ROOT / "IODB Source File.xlsx"


# ── helpers ────────────────────────────────────────────────────────────────────────────────────
def png() -> io.BytesIO:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (200, 30, 30)).save(buf, "PNG")
    buf.seek(0)
    return buf


def template(extra_sheets=(), io_list_pos=None) -> bytes:
    """Cover Sheet / Document Control / Revision History with logo, merged cells, formulas, header/footer, page set-up."""
    wb = openpyxl.Workbook()
    cover = wb.active
    cover.title = "Cover Sheet"
    cover.merge_cells("A1:D3")
    cover["A1"] = "COMPANY X - DOCUMENT COVER"
    cover["A1"].font = Font(name="Arial", size=16, bold=True, color="FF0000")
    cover["A1"].fill = PatternFill("solid", fgColor="DDEBF7")
    cover["A1"].alignment = Alignment(horizontal="center", vertical="center")
    cover["B5"], cover["C5"], cover["D5"] = 7, 5, "=B5*C5"
    cover["B5"].border = Border(left=Side("thin"), bottom=Side("medium"))
    cover.add_image(XLImage(png()), "F1")
    cover.column_dimensions["A"].width = 31
    cover.column_dimensions["E"].hidden = True
    cover.row_dimensions[2].height = 33
    cover.freeze_panes = "A4"
    cover.print_area = "A1:H20"
    cover.page_setup.orientation = "landscape"
    cover.page_setup.paperSize = 9
    cover.oddHeader.center.text = "CLIENT LOGO HEADER"
    cover.oddFooter.right.text = "Page &P of &N"
    dc = wb.create_sheet("Document Control")
    dc.append(["Doc No", "PC286-10P195-J0001-105"])
    dc.append(["Rev", "='Cover Sheet'!D5"])
    dc.sheet_properties.tabColor = "FFC000"
    rh = wb.create_sheet("Revision History")
    rh.append(["REV", "DATE", "DESCRIPTION"])
    rh.append([0, "29.01.2026", "ISSUED FOR INFORMATION"])
    rh.protection.sheet = False
    for name in extra_sheets:
        s = wb.create_sheet(name)
        s["A1"] = f"STALE CONTENT IN {name}"
    if io_list_pos is not None:
        s = wb.create_sheet("IO List", io_list_pos)
        s["A1"] = "OLD TEMPLATE IO LIST"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def iodb(n=12) -> bytes:
    rows = []
    kinds = ["AI", "AI", "AO", "DI", "DI", "DI", "DO", "DO", "-", "AI", "DI", "AI"]
    for i in range(n):
        rows.append([i + 1, f"PT-{i + 1:03d}", f"Pressure {i + 1}", kinds[i % len(kinds)], "IS" if i % 3 == 0 else "NIS", f"JB-{1 + i % 2}"])
    df = pd.DataFrame(rows, columns=["S.NO", "TAG NO", "INSTRUMENT TYPE NAME", "SIGNAL I/O TYPE", "IS/NIS TYPE", "JUNCTION BOX"])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


COLS = ["S.NO", "TAG NO", "SIGNAL I/O TYPE"]


def run(tmpl, mode, filters=None):
    out, fn, err = process_io_list(io.BytesIO(iodb()), COLS, filters=filters, template_file=io.BytesIO(tmpl) if tmpl else None,
                                   output_mode=mode)
    assert err is None, err
    return out


def names(out):
    return wa.composition_of(out)


def fingerprint(ws):
    """Everything visible/functional about a sheet that the generators must not change."""
    cells = {}
    for row in ws.iter_rows():
        for c in row:
            if c.value is not None or c.has_style:
                cells[c.coordinate] = (c.value, c.font.name, c.font.sz, c.font.b, c.font.color.rgb if c.font.color else None,
                                       c.fill.fgColor.rgb, c.border.left.style, c.border.bottom.style, c.alignment.horizontal,
                                       c.number_format)
    return dict(
        cells=cells, merged=sorted(str(r) for r in ws.merged_cells.ranges),
        widths={k: (round(v.width or 0, 2), v.hidden) for k, v in ws.column_dimensions.items()},
        heights={k: v.height for k, v in ws.row_dimensions.items() if v.height},
        freeze=ws.freeze_panes, print_area=str(ws.print_area), orient=ws.page_setup.orientation, paper=ws.page_setup.paperSize,
        header=ws.oddHeader.center.text or "", footer=ws.oddFooter.right.text or "", state=ws.sheet_state, tab=str(ws.sheet_properties.tabColor),
        images=len(ws._images), dims=ws.dimensions)


def assert_template_sheets_intact(tmpl_bytes, out_bytes, only=None):
    a = openpyxl.load_workbook(io.BytesIO(tmpl_bytes))
    b = openpyxl.load_workbook(io.BytesIO(out_bytes))
    for ws in a.worksheets:
        if only is not None and ws.title not in only:
            continue
        assert ws.title in b.sheetnames, f"template sheet {ws.title} missing"
        assert fingerprint(ws) == fingerprint(b[ws.title]), f"template sheet {ws.title} changed"


# ── I/O List ───────────────────────────────────────────────────────────────────────────────────
def test_without_summary_is_template_plus_io_list():
    t = template()
    out = run(t, WITHOUT)
    assert names(out) == ["Cover Sheet", "Document Control", "Revision History", "IO List"]
    assert_template_sheets_intact(t, out)


def test_with_summary_is_template_plus_io_list_plus_summary():
    t = template()
    out = run(t, WITH)
    assert names(out) == ["Cover Sheet", "Document Control", "Revision History", "IO List", "IO Summary"]
    assert_template_sheets_intact(t, out)


def test_io_list_sheet_is_identical_in_both_modes():
    t = template()
    a, b = (openpyxl.load_workbook(io.BytesIO(run(t, m)))["IO List"] for m in (WITHOUT, WITH))
    assert fingerprint(a) == fingerprint(b)
    assert [c.value for c in a[1]] == COLS and a.max_row == 13


def test_template_with_any_number_of_sheets_is_preserved_dynamically():
    t = template(extra_sheets=("Notes A", "Notes B", "Notes C"))
    for mode, tail in ((WITHOUT, ["IO List"]), (WITH, ["IO List", "IO Summary"])):
        out = run(t, mode)
        assert names(out) == ["Cover Sheet", "Document Control", "Revision History", "Notes A", "Notes B", "Notes C"] + tail
        assert_template_sheets_intact(t, out)


def test_stale_io_summary_in_template_never_reaches_without_mode():
    t = template(extra_sheets=("IO Summary",))
    out = run(t, WITHOUT)
    assert names(out) == ["Cover Sheet", "Document Control", "Revision History", "IO List"]
    wb = openpyxl.load_workbook(io.BytesIO(out))
    assert "IO Summary" not in wb.sheetnames


def test_stale_io_summary_in_template_is_replaced_not_duplicated_in_with_mode():
    t = template(extra_sheets=("IO Summary",))
    out = run(t, WITH)
    assert names(out) == ["Cover Sheet", "Document Control", "Revision History", "IO List", "IO Summary"]
    ws = openpyxl.load_workbook(io.BytesIO(out))["IO Summary"]
    assert "STALE" not in str(ws["A1"].value) and ws["A1"].value == "I/O SUMMARY"


def test_io_list_already_in_template_is_not_duplicated():
    t = template(io_list_pos=1)
    for mode, tail in ((WITHOUT, []), (WITH, ["IO Summary"])):
        out = run(t, mode)
        assert names(out) == ["Cover Sheet", "Document Control", "Revision History", "IO List"] + tail
        assert openpyxl.load_workbook(io.BytesIO(out))["IO List"]["A1"].value == "S.NO"
        assert not any(n.startswith(("IO List (", "IO Summary (")) for n in names(out))


def test_no_template_without_and_with_summary():
    assert names(run(None, WITHOUT)) == ["Sheet1"]
    assert names(run(None, WITH)) == ["Sheet1", "IO Summary"]


def test_summary_counts_the_filtered_rows_only():
    t = template()
    out = run(t, WITH, filters={"SIGNAL I/O TYPE": ["AI", "DI"]})
    ws = openpyxl.load_workbook(io.BytesIO(out))["IO Summary"]
    rows = {r[1].value: [c.value for c in r] for r in ws.iter_rows(min_row=5) if r[1].value}
    assert rows["AI"][2] == 4 and rows["DI"][2] == 4
    assert rows["AO"][2] == 0 and rows["DO"][2] == 0               # filtered out
    assert rows["TOTAL"][2] == "=SUM(C5:C8)"
    assert "8 I/O List rows" in ws["A2"].value
    # IS/NIS split present because the IODB has the column
    assert ws["D4"].value == "IS" and rows["AI"][3] + rows["AI"][4] + rows["AI"][5] == 4


def test_switching_modes_repeatedly_leaves_no_stale_summary():
    t = template()
    for mode, expect in ((WITHOUT, 4), (WITH, 5), (WITHOUT, 4), (WITH, 5), (WITHOUT, 4)):
        out = run(t, mode)
        assert len(names(out)) == expect
        assert ("IO Summary" in names(out)) == (mode == WITH)


def test_invalid_mode_is_rejected():
    with pytest.raises(ValueError):
        wa.normalize_mode("MAYBE")
    out, fn, err = process_io_list(io.BytesIO(iodb()), COLS, template_file=io.BytesIO(template()), output_mode="MAYBE")
    assert out is None and "Invalid output mode" in err


def test_plan_sheets_matches_the_rule():
    tn = ["A", "B", "C"]
    assert wa.plan_sheets(tn, "IO List", "IO Summary", WITHOUT, False) == ["A", "B", "C", "IO List"]
    assert wa.plan_sheets(tn, "IO List", "IO Summary", WITH, False) == ["A", "B", "C", "IO List", "IO Summary"]
    assert wa.plan_sheets(["A", "io summary", "IO LIST", "B"], "IO List", "IO Summary", WITH, False) == ["A", "B", "IO List", "IO Summary"]


def test_missing_signal_type_column_gives_a_clear_reason_not_a_fake_summary():
    df = pd.DataFrame({"TAG NO": ["A", "B"], "SERVICE": ["x", "y"]})
    buf = io.BytesIO(); df.to_excel(buf, index=False)
    out, _, err = process_io_list(io.BytesIO(buf.getvalue()), ["TAG NO"], template_file=io.BytesIO(template()), output_mode=WITH)
    assert err is None
    ws = openpyxl.load_workbook(io.BytesIO(out))["IO Summary"]
    assert "No SIGNAL I/O TYPE column" in str(ws["A5"].value)


# ── API: preview == download, switching without restarting ────────────────────────────────────
@pytest.fixture()
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import cable_schedule, io_list
    app = FastAPI()
    app.include_router(io_list.router, prefix="/api")
    app.include_router(cable_schedule.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, username="alice")
    return TestClient(app)


def generate_api(c, tmpl, mode):
    files = {"iodb_file": ("IODB.xlsx", iodb()), "template_file": ("T.xlsx", tmpl)}
    data = {"selected_columns": '["S.NO","TAG NO","SIGNAL I/O TYPE"]', "filters": "{}", "output_mode": mode}
    r = c.post("/api/io-list/generate", files=files, data=data)
    assert r.status_code == 200, r.text
    d = c.get("/api/io-list/download")
    assert d.status_code == 200
    return r.json(), d.content


def test_api_preview_equals_downloaded_workbook_across_three_runs(client):
    t = template()
    for mode, expect in ((WITHOUT, ["Cover Sheet", "Document Control", "Revision History", "IO List"]),
                         (WITH, ["Cover Sheet", "Document Control", "Revision History", "IO List", "IO Summary"]),
                         (WITHOUT, ["Cover Sheet", "Document Control", "Revision History", "IO List"])):
        prev = client.post("/api/io-list/composition", files={"template_file": ("T.xlsx", t)}, data={"output_mode": mode})
        assert prev.status_code == 200, prev.text
        assert [s["name"] for s in prev.json()["sheets"]] == expect
        kinds = {s["name"]: s["kind"] for s in prev.json()["sheets"]}
        assert kinds["IO List"] == "generated" and kinds["Cover Sheet"] == "template"
        resp, content = generate_api(client, t, mode)
        assert resp["output_mode"] == mode and resp["sheets"] == expect
        assert names(content) == expect == [s["name"] for s in prev.json()["sheets"]]


def test_api_rejects_unknown_mode(client):
    r = client.post("/api/io-list/composition", data={"output_mode": "nope"})
    assert r.status_code == 400
    r = client.post("/api/io-list/generate", files={"iodb_file": ("I.xlsx", iodb())},
                    data={"selected_columns": '["TAG NO"]', "output_mode": "nope"})
    assert r.status_code == 400


# ── Cable Schedule (real company template: 11 sheets, 8 hidden, pictures, own CABLE SUMMARY sheet) ──
needs_cable_files = pytest.mark.skipif(not (CABLE_TEMPLATE.exists() and CABLE_IODB.exists()), reason="sample cable files missing")


def cable_run(mode):
    from utils.template_processor import get_iodb_columns
    data = CABLE_IODB.read_bytes()
    cols, _ = get_iodb_columns(io.BytesIO(data))
    jb = next(c for c in cols if "JUNCTION" in str(c).upper())
    out, fn, err = process_cable_schedule(io.BytesIO(data), io.BytesIO(CABLE_TEMPLATE.read_bytes()), jb, "TAG NO", output_mode=mode)
    assert err is None, err
    return out


@needs_cable_files
def test_cable_without_summary_keeps_every_template_sheet_except_its_own_summary():
    out = cable_run(WITHOUT)
    tmpl_names = openpyxl.load_workbook(CABLE_TEMPLATE, read_only=True).sheetnames
    assert names(out) == [n for n in tmpl_names if n.strip().upper() != "CABLE SUMMARY"]
    wb = openpyxl.load_workbook(io.BytesIO(out))
    hidden_t = {ws.title: ws.sheet_state for ws in openpyxl.load_workbook(CABLE_TEMPLATE).worksheets}
    assert all(wb[n].sheet_state == hidden_t[n] for n in names(out))
    assert "CABLE SUMMARY" not in wb.sheetnames


@needs_cable_files
def test_cable_with_summary_adds_cable_summary_last():
    out = cable_run(WITH)
    tmpl_names = openpyxl.load_workbook(CABLE_TEMPLATE, read_only=True).sheetnames
    assert names(out) == [n for n in tmpl_names if n.strip().upper() != "CABLE SUMMARY"] + ["CABLE SUMMARY"]
    assert names(out).count("CABLE SUMMARY") == 1


@needs_cable_files
def test_cable_template_sheets_other_than_the_schedule_are_untouched_and_drawings_restored():
    out = cable_run(WITH)
    a = openpyxl.load_workbook(CABLE_TEMPLATE)
    b = openpyxl.load_workbook(io.BytesIO(out))
    for ws in a.worksheets:
        if ws.title.strip().upper() in ("CABLE SUMMARY", "CABLE SCHEDULE -INST"):
            continue
        assert fingerprint(ws) == fingerprint(b[ws.title]), ws.title
    import re
    import zipfile

    def pics(data):
        z = zipfile.ZipFile(io.BytesIO(data))
        return sum(len(re.findall(r"<(?:\w+:)?pic[ >]", z.read(n).decode())) for n in z.namelist()
                   if n.startswith("xl/drawings/drawing") and n.endswith(".xml"))
    assert pics(out) == pics(CABLE_TEMPLATE.read_bytes())            # including the logo inside the grouped shape

    def header_footers(data):                                         # raw XML: also catches text openpyxl cannot parse
        import re
        import zipfile
        z = zipfile.ZipFile(io.BytesIO(data))
        paths = wa._sheet_paths(z)
        return {n: re.findall(r"<headerFooter\b.*?</headerFooter>", z.read(p).decode(), re.S) for n, p in paths.items()}
    ht, ho = header_footers(CABLE_TEMPLATE.read_bytes()), header_footers(out)
    for n in ht:
        if n.strip().upper() != "CABLE SUMMARY":
            assert ht[n] == ho[n], f"header/footer of {n} changed"


@needs_cable_files
def test_cable_api_preview_equals_download(client):
    t, data = CABLE_TEMPLATE.read_bytes(), CABLE_IODB.read_bytes()
    from utils.template_processor import get_iodb_columns
    cols, _ = get_iodb_columns(io.BytesIO(data))
    jb = next(c for c in cols if "JUNCTION" in str(c).upper())
    for mode in (WITHOUT, WITH, WITHOUT):
        prev = client.post("/api/cable-schedule/composition", files={"template_file": ("T.xlsx", t)}, data={"output_mode": mode})
        assert prev.status_code == 200, prev.text
        planned = [s["name"] for s in prev.json()["sheets"]]
        r = client.post("/api/cable-schedule/generate", files={"iodb_file": ("I.xlsx", data), "template_file": ("T.xlsx", t)},
                        data={"jb_column": jb, "tag_column": "TAG NO", "output_mode": mode})
        assert r.status_code == 200, r.text
        content = client.get("/api/cable-schedule/download").content
        assert names(content) == planned == r.json()["sheets"]
        assert ("CABLE SUMMARY" in planned) == (mode == WITH)
