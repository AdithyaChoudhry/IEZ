"""Approved V3 Cable Schedule header: the stored master, its application to every worksheet, and that the engineering output is unchanged."""
import hashlib
import io
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import openpyxl
import pytest
from openpyxl.drawing.image import Image
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import cable_header_v3 as HV  # noqa: E402
from utils.cable_schedule_extra import parse_selection  # noqa: E402
from utils.template_processor import process_cable_schedule  # noqa: E402
from app.routers.cable_schedule import DEFAULT_TEMPLATE_PATH  # noqa: E402
from test_cable_schedule_extra import iodb  # noqa: E402

APPROVED_MD5 = "37289b3f80a578c34254ba42ae378592"      # iEZ_Cable_Schedule_Standard_Header_V3.xlsx as approved
VALUES = {"project": "SETTING UP OF A POND, ZLD PLANT", "client": "GAIL (INDIA) LTD", "doc_no": "10P195-I0010-201", "pmc": "PDIL",
          "date": "24-11-2026", "location": "Gujarat, India", "revision": "02"}
EXTRAS = "MCC DI,MCC DO,VFD,MOV,LCP"

# header arrangement of the approved template: (last column, first column of the right-hand block); logo A:C (A:B for the summary)
SPEC = {"Cable Schedule -INST": (20, 13), "MCC DI": (19, 13), "MCC DO": (20, 14), "VFD": (20, 14), "MOV": (25, 16), "CABLE SUMMARY": (4, 3)}
TITLES = {"Cable Schedule -INST": "INSTRUMENT CABLE SCHEDULE", "MCC DI": "MCC DI CABLE SCHEDULE", "MCC DO": "MCC DO CABLE SCHEDULE",
          "VFD": "VFD CABLE SCHEDULE", "MOV": "MOV CABLE SCHEDULE", "CABLE SUMMARY": "CABLE QUANTITY SUMMARY", "LCP": "LCP CABLE SCHEDULE"}


def expected_merges(n, right, logo_last):
    L = get_column_letter
    out = {f"A1:{L(logo_last)}1", f"{L(logo_last + 1)}1:{L(n)}1", f"A2:{L(n)}2", f"A6:{L(n)}6"}
    for r in (3, 4, 5):
        out |= {f"A{r}:{L(right - 1)}{r}", f"{L(right)}{r}:{L(n)}{r}"}
    return out


def build(values=VALUES, extras=EXTRAS, mode="WITH_SUMMARY", jb="JUNCTION BOX TAG NO.", with_header=True, template=None):
    rep = {}
    out, _fn, err = process_cable_schedule(io.BytesIO(iodb(with_lcp=True)), io.BytesIO(template or DEFAULT_TEMPLATE_PATH.read_bytes()), jb, "TAG NO",
                                           output_mode=mode, extra_sheets=parse_selection(extras) if extras else None, extra_report=rep,
                                           header_meta=dict(values) if with_header else None)
    assert err is None, err
    return openpyxl.load_workbook(io.BytesIO(out)), rep


@pytest.fixture(scope="module")
def built():
    return build()


@pytest.fixture(scope="module")
def legacy():
    return build(with_header=False)


# ── 30.1 the stored master ───────────────────────────────────────────────────────────────────────────────────────────
def test_the_approved_template_is_stored_inside_the_application_unchanged():
    assert HV.TEMPLATE_PATH.name == "Cable_Schedule_Standard_Header_V3.xlsx" and HV.TEMPLATE_PATH.parent.name == "cable_schedule"
    assert hashlib.md5(HV.TEMPLATE_PATH.read_bytes()).hexdigest() == APPROVED_MD5
    wb = openpyxl.load_workbook(HV.TEMPLATE_PATH)
    assert wb.sheetnames == ["Cable Schedule -INST", "MCC DI", "MCC DO", "VFD", "MOV", "CABLE SUMMARY"]


@pytest.mark.parametrize("sheet", list(SPEC))
def test_every_approved_header_has_the_approved_ranges_heights_title_and_logo(sheet):
    ws = HV.load_template()[sheet]
    n, right = SPEC[sheet]
    logo_last = 2 if sheet == "CABLE SUMMARY" else 3
    assert {str(m) for m in ws.merged_cells.ranges if m.max_row <= 6} == expected_merges(n, right, logo_last)
    heights = [ws.row_dimensions[r].height for r in range(1, 7)]
    assert heights[0] == pytest.approx(56.7, abs=0.1) and heights[2:5] == [24.0] * 3 and heights[5] == 28.0
    assert heights[1] == (32.0 if sheet == "CABLE SUMMARY" else 30.0)
    assert ws["A6"].value == TITLES[sheet]
    assert len(ws._images) == 1
    company = ws.cell(1, logo_last + 1).value
    assert company.splitlines() == ["VA TECH WABAG LIMITED", "WABAG House, No.17, 200 Feet Thoraipakkam Pallavaram Main Road",
                                    "S.Kolathur, Chennai - 600117, India"]


def test_the_template_loader_gives_each_request_its_own_instance_and_never_changes_the_master():
    before = hashlib.md5(HV.TEMPLATE_PATH.read_bytes()).hexdigest()
    a, b = HV.load_template(), HV.load_template()
    assert a is not b
    a["MOV"]["A2"] = "CHANGED"
    assert HV.load_template()["MOV"]["A2"].value != "CHANGED" and b["MOV"]["A2"].value != "CHANGED"
    build()
    assert hashlib.md5(HV.TEMPLATE_PATH.read_bytes()).hexdigest() == before == APPROVED_MD5


def test_a_missing_or_broken_template_is_reported_not_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(HV, "TEMPLATE_PATH", tmp_path / "nope.xlsx")
    HV._master_bytes.cache_clear()
    try:
        with pytest.raises(HV.TemplateError, match="not available"):
            HV.load_template()
        bad = tmp_path / "bad.xlsx"
        bad.write_bytes(b"not a workbook")
        monkeypatch.setattr(HV, "TEMPLATE_PATH", bad)
        HV._master_bytes.cache_clear()
        with pytest.raises(HV.TemplateError, match="not a valid workbook"):
            HV.load_template()
        wb = openpyxl.load_workbook(Path(__file__).resolve().parents[2] / "backend/app/templates/cable_schedule/Cable_Schedule_Standard_Header_V3.xlsx")
        del wb["VFD"]
        part = tmp_path / "part.xlsx"
        wb.save(part)
        monkeypatch.setattr(HV, "TEMPLATE_PATH", part)
        HV._master_bytes.cache_clear()
        with pytest.raises(HV.TemplateError, match="'VFD' is missing"):
            HV.load_template()
    finally:
        monkeypatch.undo()
        HV._master_bytes.cache_clear()


# ── 30.7 the headers of the generated workbook ───────────────────────────────────────────────────────────────────────
def test_the_workbook_has_every_applicable_sheet_in_the_planned_order(built):
    wb, _ = built
    assert wb.sheetnames == ["COVERSHEET", "Cable Schedule -INST", "MCC DI", "MCC DO", "VFD", "MOV", "LCP", "CABLE SUMMARY"]


@pytest.mark.parametrize("sheet", list(SPEC))
def test_each_generated_header_is_the_approved_one_filled_with_the_resolved_metadata(built, sheet):
    wb, rep = built
    ws = wb[sheet]
    n, right = SPEC[sheet]
    logo_last = 2 if sheet == "CABLE SUMMARY" else 3
    assert rep["header"][sheet]["mode"] == "approved" and rep["header"][sheet]["last_col"] == n
    assert {str(m) for m in ws.merged_cells.ranges if m.max_row <= 6} == expected_merges(n, right, logo_last)
    left = [ws.cell(r, 1).value for r in (2, 3, 4, 5)]
    rt = [ws.cell(r, right).value for r in (3, 4, 5)]
    assert left == ["PROJECT : SETTING UP OF A POND, ZLD PLANT", "CLIENT : GAIL (INDIA) LTD", "PMC : PDIL", "LOCATION : Gujarat, India"]
    assert rt == ["DOCUMENT NO. : 10P195-I0010-201", "DATE : 24-11-2026", "REVISION : 02"]
    assert ws.cell(6, 1).value == TITLES[sheet]
    assert [ws.row_dimensions[r].height for r in range(1, 7)] == pytest.approx(
        [56.7, 32.0 if sheet == "CABLE SUMMARY" else 30.0, 24.0, 24.0, 24.0, 28.0], abs=0.1)
    assert len([im for im in ws._images if im.anchor._from.row < 6]) == 1
    assert HV.verify_header(ws, VALUES) == []


def test_lcp_gets_the_approved_arrangement_of_the_same_width_and_is_reported(built):
    wb, rep = built
    ws = wb["LCP"]
    assert rep["header"]["LCP"]["mode"] == "derived" and rep["header"]["LCP"]["template_sheet"] == "MOV"
    assert ws["A6"].value == "LCP CABLE SCHEDULE" and ws["A3"].value == "CLIENT : GAIL (INDIA) LTD" and ws["P5"].value == "REVISION : 02"
    assert any("LCP" in w and "no LCP worksheet" in w for w in rep["warnings"])


def test_the_logo_is_the_approved_picture_with_its_approved_position_and_size(built):
    wb, _ = built
    tpl = HV.load_template()
    for sheet in SPEC:
        a, t = wb[sheet]._images[0].anchor, tpl[sheet]._images[0].anchor
        assert (a._from.col, a._from.row, a._from.colOff, a._from.rowOff) == (t._from.col, t._from.row, t._from.colOff, t._from.rowOff)
        assert (a.ext.width, a.ext.height) == (t.ext.width, t.ext.height)


def test_no_prepared_checked_approved_fields_and_no_template_sample_values(built):
    wb, _ = built
    import re
    for ws in wb.worksheets[1:]:
        text = " ".join(str(ws.cell(r, c).value) for r in range(1, 7) for c in range(1, ws.max_column + 1) if ws.cell(r, c).value)
        assert not re.search(r"(?i)prepared|checked|approved", text), ws.title
        assert not re.search(r"(?i)confirm|\bDJB\b|\bTTI\b|10P211|\[|XXXX|\bTBD\b", text), (ws.title, text)


# ── 30.9 engineering regression ──────────────────────────────────────────────────────────────────────────────────────
def style_of(c):
    return (c.font.name, c.font.sz, c.font.b, c.fill.fill_type, c.fill.fgColor.rgb if c.fill.fill_type else None,
            c.alignment.horizontal, c.alignment.wrap_text, c.border.left.style if c.border.left else None)


@pytest.mark.parametrize("sheet", ["Cable Schedule -INST", "MCC DI", "MCC DO", "VFD", "MOV", "LCP"])
def test_the_engineering_tables_are_identical_to_the_earlier_output(built, legacy, sheet):
    new, old = built[0][sheet], legacy[0][sheet]
    assert new.max_row == old.max_row
    width = {"Cable Schedule -INST": 20, "MCC DI": 19, "MCC DO": 20, "VFD": 20, "MOV": 25, "LCP": 25}[sheet]
    for r in range(7, old.max_row + 1):
        for c in range(1, width + 1):
            assert new.cell(r, c).value == old.cell(r, c).value, (sheet, r, c)
            assert style_of(new.cell(r, c)) == style_of(old.cell(r, c)), (sheet, r, c)
    assert {str(m) for m in new.merged_cells.ranges if m.min_row >= 7} == {str(m) for m in old.merged_cells.ranges if m.min_row >= 7}
    for r in range(7, old.max_row + 1):
        assert new.row_dimensions[r].height == old.row_dimensions[r].height, (sheet, r)
    for c in range(1, width + 1):
        letter = get_column_letter(c)
        assert new.column_dimensions[letter].width == old.column_dimensions[letter].width, (sheet, letter)
    assert (new.print_area, new.print_title_rows) == (old.print_area, old.print_title_rows)


def test_the_cable_summary_quantities_are_the_generated_ones_not_the_samples(built, legacy):
    def table(ws, first):
        return [(ws.cell(r, 2).value, ws.cell(r, 3).value, ws.cell(r, 4).value) for r in range(first, ws.max_row + 1) if ws.cell(r, 2).value
                and not str(ws.cell(r, 2).value).startswith("NOTE")]
    new, old = built[0]["CABLE SUMMARY"], legacy[0]["CABLE SUMMARY"]
    assert [new.cell(7, c).value for c in range(1, 5)] == ["SL.NO", "CABLE DESCRIPTION", "UNITS", "QUANTITY"]
    assert table(new, 8) == table(old, 4) != []
    assert ("1PX1.5 Sqmm", "METERS", 109185) not in table(new, 8)                  # the template's sample row
    assert [new.cell(r, 1).value for r in range(8, 8 + len(table(new, 8)))] == list(range(1, len(table(new, 8)) + 1))


def test_formulas_in_the_engineering_tables_are_still_formulas(built, legacy):
    for sheet in ("Cable Schedule -INST", "MCC DI", "VFD"):
        f_new = sum(1 for row in built[0][sheet].iter_rows(min_row=7) for c in row if isinstance(c.value, str) and c.value.startswith("="))
        f_old = sum(1 for row in legacy[0][sheet].iter_rows(min_row=7) for c in row if isinstance(c.value, str) and c.value.startswith("="))
        assert f_new == f_old


def test_the_earlier_loop_number_merging_and_main_cable_corrections_survive(built, legacy):
    ws = built[0]["MCC DI"]
    assert [str(m) for m in ws.merged_cells.ranges if m.min_row >= 7 and m.min_col == 2 and m.max_row > m.min_row] == \
           [str(m) for m in legacy[0]["MCC DI"].merged_cells.ranges if m.min_row >= 7 and m.min_col == 2 and m.max_row > m.min_row]
    heads = [built[0]["MOV"].cell(r, c).value for r in (9, 10, 11) for c in range(1, 26)]
    assert heads == [legacy[0]["MOV"].cell(r, c).value for r in (9, 10, 11) for c in range(1, 26)]


# ── 30.8 long metadata, 30.6 placeholders ────────────────────────────────────────────────────────────────────────────
def test_long_metadata_wraps_and_only_the_rows_that_need_it_grow(legacy):
    long_values = {**VALUES, "project": "SETTING UP OF A 2 x 40 MLD INTEGRATED SEWAGE TREATMENT PLANT WITH TERTIARY TREATMENT AND ZERO LIQUID "
                                         "DISCHARGE FACILITY, INCLUDING ALL ASSOCIATED CIVIL, MECHANICAL, ELECTRICAL AND INSTRUMENTATION WORKS ON "
                                         "A TURNKEY BASIS FOR THE METROPOLITAN DEVELOPMENT AUTHORITY, PHASE 2 EXTENSION PACKAGE 3",
                   "client": "THE MUNICIPAL CORPORATION OF GREATER METROPOLITAN CITY DEVELOPMENT AUTHORITY AND ALLIED SERVICES LTD",
                   "pmc": "PROJECT MANAGEMENT CONSULTANTS INTERNATIONAL PRIVATE LIMITED, INFRASTRUCTURE AND ENVIRONMENT DIVISION (SOUTH ASIA)"}
    wb, _ = build(long_values, extras="MCC DI")
    ws, summary = wb["MCC DI"], wb["CABLE SUMMARY"]
    assert ws.row_dimensions[1].height == pytest.approx(56.7, abs=0.1) and ws.row_dimensions[6].height == 28.0
    assert ws.row_dimensions[2].height >= 30.0 and ws["A2"].value.endswith("PACKAGE 3")
    assert summary.row_dimensions[2].height > 32.0 and summary.row_dimensions[4].height > 24.0                 # the compact header wraps taller
    assert summary.row_dimensions[1].height == pytest.approx(56.7, abs=0.1)
    old = legacy[0]["MCC DI"]
    assert [ws.column_dimensions[get_column_letter(c)].width for c in range(1, 20)] == [old.column_dimensions[get_column_letter(c)].width for c in range(1, 20)]
    assert HV.verify_header(ws, long_values) == [] and HV.verify_header(summary, long_values) == []


@pytest.mark.parametrize("bad", ["[Confirm project name]", "(Confirm Client)", "XXXX", "TBA", "", "   "])
def test_placeholders_never_reach_a_header(bad):
    with pytest.raises(HV.HeaderError, match="unresolved"):
        HV.apply_headers(openpyxl.load_workbook(DEFAULT_TEMPLATE_PATH), {"Cable Schedule -INST": ("INST", 20)}, {**VALUES, "client": bad})


def test_a_confirmed_not_applicable_pmc_is_written(legacy):
    wb, _ = build({**VALUES, "pmc": "N/A"}, extras="VFD")
    assert wb["VFD"]["A4"].value == "PMC : N/A" and wb["CABLE SUMMARY"]["A4"].value == "PMC : N/A"


# ── 30.10 / 18 the picture, the merges, the width ────────────────────────────────────────────────────────────────────
def sheet_20(title="S", n=20, widths=14):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for c in range(1, n + 1):
        ws.column_dimensions[get_column_letter(c)].width = widths
        ws.cell(7, c, f"H{c}")
        ws.cell(9, c, f"D{c}")
    ws["A1"] = "OLD"
    ws.merge_cells("A1:D3")
    return wb, ws


def test_only_header_pictures_are_replaced_and_the_logo_is_never_duplicated():
    wb, ws = sheet_20()
    old = Image(io.BytesIO(HV.load_master().logos["MOV"]))
    old.anchor = "A1"
    ws.add_image(old)
    keep = Image(io.BytesIO(HV.load_master().logos["MOV"]))
    keep.anchor = "B20"                                                    # an engineering picture below the header
    ws.add_image(keep)
    for _ in range(2):                                                     # applying twice must not add a second logo
        HV.apply_headers(wb, {"S": ("INST", 20)}, VALUES)
    rows = sorted(im.anchor._from.row if hasattr(im.anchor, "_from") else 19 for im in ws._images)
    assert rows == [0, 19]                                                 # the new logo at the top, the engineering picture kept


def test_a_merge_that_spans_the_header_and_the_table_is_reported_with_its_range():
    wb, ws = sheet_20()
    ws.merge_cells("B5:B9")
    with pytest.raises(HV.HeaderError, match="B5:B9"):
        HV.apply_headers(wb, {"S": ("INST", 20)}, VALUES)


def test_a_different_width_is_reported_and_proportioned_not_silently_forced():
    wb, ws = sheet_20(n=12)
    res = HV.apply_headers(wb, {"S": ("INST", 12)}, VALUES)["S"]
    assert res.mode == "derived" and any("12 columns" in w and "20" in w for w in res.warnings)
    assert {str(m) for m in ws.merged_cells.ranges if m.max_row <= 6} >= {"A1:C1", "A2:L2", "A6:L6"}
    assert ws["A3"].value == "CLIENT : GAIL (INDIA) LTD" and HV.verify_header(ws, VALUES) == []
    assert [ws.cell(7, c).value for c in range(1, 13)] == [f"H{c}" for c in range(1, 13)]          # the table is untouched


def test_engineering_rows_below_the_header_are_never_touched():
    wb, ws = sheet_20()
    before = [[ws.cell(r, c).value for c in range(1, 21)] for r in range(7, 12)]
    HV.apply_headers(wb, {"S": ("INST", 20)}, VALUES)
    assert [[ws.cell(r, c).value for c in range(1, 21)] for r in range(7, 12)] == before


# ── 30.11 concurrent requests ────────────────────────────────────────────────────────────────────────────────────────
def test_simultaneous_generations_never_mix_their_metadata():
    a = {**VALUES, "project": "PROJECT ALPHA", "client": "CLIENT ALPHA", "doc_no": "10PAAA-I0010-001", "location": "ALPHA TOWN"}
    b = {**VALUES, "project": "PROJECT BRAVO", "client": "CLIENT BRAVO", "doc_no": "10PBBB-I0010-002", "location": "BRAVO CITY"}
    barrier = threading.Barrier(2)

    def run(v):
        barrier.wait()
        return build(v, extras="MCC DI,VFD")[0]
    with ThreadPoolExecutor(2) as pool:
        wa, wb_ = pool.map(run, [a, b])
    for wb, v, other in ((wa, a, b), (wb_, b, a)):
        for ws in wb.worksheets[1:]:
            text = " ".join(str(ws.cell(r, c).value) for r in range(1, 7) for c in range(1, ws.max_column + 1) if ws.cell(r, c).value)
            assert v["project"] in text and v["doc_no"] in text and v["location"] in text
            assert other["project"] not in text and other["doc_no"] not in text
    assert hashlib.md5(HV.TEMPLATE_PATH.read_bytes()).hexdigest() == APPROVED_MD5
