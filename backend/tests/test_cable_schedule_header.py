"""Standard document header (rows 1-6) of the Cable Schedule sheets, driven by the COVERSHEET."""
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import cable_schedule_header as H  # noqa: E402


def cover_ws(wb, rev="0", missing=()):
    ws = wb.create_sheet("COVERSHEET", 0)
    ws["A1"] = "GAIL"
    ws["G2"] = "INSTRUMENT CABLE SCHEDULE - POND"
    ws["A3"] = "SETTING UP OF A POND, ZLD PLANT"
    for c, v in (("G3", "Job No."), ("H3", "Unit No."), ("J3", "Project"), ("K3", "Doc. Code"), ("M3", "Serial No."), ("N3", "Rev."), ("P3", "Page No.")):
        ws[c] = v
    for c, v in (("G4", "PC286"), ("H4", 200), ("J4", "10P195"), ("K4", "I0010"), ("M4", 201), ("N4", rev), ("P4", "1 of 12")):
        if c not in missing:
            ws[c] = v
    for r, (lab, val) in zip((6, 7, 8), (("CLIENT", "GAIL (INDIA) LTD"), ("PMC", "PDIL"), ("CONTRACTOR", "VA TECH WABAG LIMITED"))):
        ws.cell(r, 1, lab)
        ws.cell(r, 4, ":")
        if lab not in missing:
            ws.cell(r, 6, val)
    ws["A10"] = "DOCUMENT TITLE\n\n"
    ws["A11"] = "INSTRUMENT CABLE SCHEDULE - POND"
    ws["A12"] = "STAMPING AREA"
    ws["A13"], ws["E13"] = "DOCUMENT CLASS", "INFORMATION"
    ws["A14"], ws["E14"] = "DISCIPLINE", "INSTRUMENTATION"
    # revision table: newest on top, header below
    for r, (rv, d, p, c, a) in ((19, ("01", "09.03.2026", "AKB", "AG", "VE")), (20, (0, "10.10.2025", "XYZ", "UV", "QR"))):
        ws.cell(r, 1, rv); ws.cell(r, 2, d); ws.cell(r, 10, p); ws.cell(r, 12, c); ws.cell(r, 15, a)
    for col, lab in ((1, "REV"), (2, "DATE"), (3, "DESCRIPTION"), (10, "PREPARED"), (12, "CHECKED"), (15, "APPROVED")):
        ws.cell(22, col, lab)
    return ws


def schedule_ws(wb, title="Sched", ncols=12):
    ws = wb.create_sheet(title)
    for c in range(1, ncols + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = 14
        ws.cell(9, c, f"H{c}")
    ws["A1"] = "OLD HEADER"
    return ws


def build(**kw):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    cover_ws(wb, **kw)
    return wb


def test_cover_fields_are_found_by_label():
    wb = build()
    cv = H.read_cover(wb, "COVERSHEET")
    f = cv.fields
    assert f["title"].value == "INSTRUMENT CABLE SCHEDULE - POND"
    assert f["project"].value.startswith("SETTING UP")
    assert f["client"].value == "GAIL (INDIA) LTD" and f["pmc"].value == "PDIL" and f["contractor"].value == "VA TECH WABAG LIMITED"
    assert f["rev"].value == "0"
    assert not cv.warnings


def test_doc_no_is_doc_code_and_serial_only_never_the_job_code():
    cv = H.read_cover(build(), "COVERSHEET")
    assert cv.fields["doc_no"].value == "I0010-201"
    expr = cv.fields["doc_no"].expr
    assert "$K$4" in expr and "$M$4" in expr and "$G$4" not in expr and "$J$4" not in expr


def test_current_rev_selects_its_own_revision_row():
    cv = H.read_cover(build(rev="0"), "COVERSHEET")
    assert [cv.fields[k].value for k in ("date", "prepared_by", "checked_by", "approved_by")] == ["10.10.2025", "XYZ", "UV", "QR"]
    cv = H.read_cover(build(rev="01"), "COVERSHEET")
    assert [cv.fields[k].value for k in ("date", "prepared_by", "checked_by", "approved_by")] == ["09.03.2026", "AKB", "AG", "VE"]


def test_unknown_current_rev_shows_tba_with_a_warning():
    cv = H.read_cover(build(rev="7"), "COVERSHEET")
    assert cv.fields["date"].value == "TBA" and any("revision 7" in w for w in cv.warnings)


def test_missing_cover_fields_show_tba_and_are_reported_never_guessed():
    cv = H.read_cover(build(missing=("CLIENT", "K4")), "COVERSHEET")
    assert cv.fields["client"].value == "TBA" and cv.fields["doc_no"].value == "TBA"
    assert any("CLIENT" in w for w in cv.warnings) and any("Doc. Code" in w for w in cv.warnings)


def test_every_header_cell_is_a_live_formula_on_the_cover():
    wb = build()
    ws = schedule_ws(wb)
    assert H.apply_standard_headers(wb, {"Sched": ("INSTRUMENT CABLE SCHEDULE", 12, None)})["applied"] == ["Sched"]
    formulas = [c.value for r in ws.iter_rows(min_row=1, max_row=6) for c in r if isinstance(c.value, str) and c.value.startswith("=")]
    assert len(formulas) == 11                                      # title, doc no, rev, date, project, client, pmc, 3 signatures, contractor block
    assert all("COVERSHEET" in f for f in formulas)
    texts = {str(c.value) for r in ws.iter_rows(min_row=1, max_row=6) for c in r if c.value}
    assert {"DOC NO", "REV NO", "DATE", "PROJECT", "CLIENT", "PMC", "PREPARED BY", "CHECKED BY", "APPROVED BY", "INSTRUMENT CABLE SCHEDULE"} <= texts
    assert "OLD HEADER" not in texts


def test_same_header_structure_on_every_sheet():
    wb = build()
    a, b = schedule_ws(wb, "A", 12), schedule_ws(wb, "B", 20)
    H.apply_standard_headers(wb, {"A": ("X", 12, None), "B": ("Y", 20, None)})
    assert [a.row_dimensions[r].height for r in range(1, 7)] == [b.row_dimensions[r].height for r in range(1, 7)] == list(H.ROW_HEIGHTS)
    labels = lambda ws: sorted(str(c.value) for r in ws.iter_rows(min_row=1, max_row=6) for c in r if c.value and not str(c.value).startswith("="))
    assert [x for x in labels(a) if x not in "X"] == [x for x in labels(b) if x not in "Y"]
    for ws in (a, b):
        assert ws.cell(9, 1).value == "H1"                           # the table below is untouched


def test_static_values_when_the_workbook_has_no_cover_sheet_formulas():
    wb = build()
    cv = H.read_cover(wb, "COVERSHEET")
    ws = schedule_ws(wb)
    assert H.apply_header(ws, cv, 12, "T", live=False)
    vals = {str(c.value) for r in ws.iter_rows(min_row=1, max_row=6) for c in r if c.value}
    assert {"I0010-201", "GAIL (INDIA) LTD", "PDIL", "10.10.2025", "XYZ"} <= vals
    assert not any(v.startswith("=") for v in vals)


def test_workbook_without_a_cover_is_left_alone():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "KEEP"
    res = H.apply_standard_headers(wb, {wb.active.title: ("T", 12, None)})
    assert res["applied"] == [] and ws["A1"].value == "KEEP" and res["warnings"]


def test_sheet_with_too_few_columns_is_skipped_untouched():
    wb = build()
    ws = schedule_ws(wb, "Tiny", 3)
    res = H.apply_standard_headers(wb, {"Tiny": ("T", 3, None)})
    assert res["applied"] == [] and ws["A1"].value == "OLD HEADER" and any("too few columns" in w for w in res["warnings"])


def test_logo_is_reused_at_one_position_and_height():
    from PIL import Image as PIL
    buf = io.BytesIO()
    PIL.new("RGB", (400, 100), "blue").save(buf, "PNG")
    wb = build()
    a, b = schedule_ws(wb, "A"), schedule_ws(wb, "B")
    assert H.place_logo(a, buf.getvalue())
    res = H.apply_standard_headers(wb, {"A": ("X", 12, None), "B": ("Y", 12, None)})
    assert res["logo_sheets"] == ["A", "B"]
    anchors = [ws._images[0].anchor for ws in (a, b)]
    assert [(x._from.col, x._from.row, x._from.colOff, x._from.rowOff, x.ext.height) for x in anchors][0] == \
           [(x._from.col, x._from.row, x._from.colOff, x._from.rowOff, x.ext.height) for x in anchors][1]
    assert H.logo_bytes(a) and not a._images[0].ref.closed


def test_generation_applies_the_header_to_instrument_and_extra_sheets():
    from test_cable_schedule_extra import run, template, iodb
    # the helper template already has a COVERSHEET sheet: replace it with the full cover
    wb2 = openpyxl.load_workbook(io.BytesIO(template()))
    del wb2["COVERSHEET"]
    cover_ws(wb2)
    for ws in wb2:
        if ws.title == "Cable Schedule -INST":
            for c, h in enumerate(["SL. No.", "TAG NUMBER", "JUNCTION BOX TAG NO.", "D", "E", "F", "G", "H"], 1):
                ws.cell(7, c, h)
    b2 = io.BytesIO()
    wb2.save(b2)
    out, err, rep = run(["mcc_di", "vfd", "mov"], tmpl=b2.getvalue())
    assert err is None, err
    book = openpyxl.load_workbook(io.BytesIO(out))
    names = ["Cable Schedule -INST"] + [s for s in book.sheetnames if "(iEZ)" in s or s in ("MCC DI", "MOV")]
    done = [n for n in names if isinstance(book[n]["A4"].value, str) and "COVERSHEET" in str(book[n]["A4"].value)]
    assert "MOV" in done or any("MOV" in n for n in done)
    for n in done:
        ws = book[n]
        assert [ws.row_dimensions[r].height for r in range(1, 7)] == list(H.ROW_HEIGHTS)


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_formulas_evaluate_to_the_cover_values():
    wb = build(rev="0")
    ws = schedule_ws(wb)
    H.apply_standard_headers(wb, {"Sched": ("T", 12, None)})
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "h.xlsx"
        wb.save(src)
        subprocess.run(["soffice", "--headless", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(Path(d) / "o"), str(src)],
                       capture_output=True, timeout=170)
        res = openpyxl.load_workbook(Path(d) / "o" / "h.xlsx", data_only=True)["Sched"]
    vals = {str(c.value) for r in res.iter_rows(min_row=1, max_row=6) for c in r if c.value is not None}
    assert {"I0010-201", "0", "10.10.2025", "XYZ", "UV", "QR", "GAIL (INDIA) LTD", "PDIL", "INSTRUMENT CABLE SCHEDULE - POND"} <= vals
    assert not any("Err" in v or "#" in v for v in vals)


# ── the cover the app really produces (coversheet generator, 'PREPARED BY' labels, revision rows 15-23) ───────────────
def real_cover(revs=None):
    from utils.coversheet_generator import generate_cover_sheet
    pi = {"doc_title_short": "X", "project_description": "MY PROJECT", "job_no": "J1", "unit_no": "U", "project_no": "P9", "doc_code": "I0010",
          "serial_no": "201", "page_no": "1 of 2", "client": "CLI", "pmc": "PMC", "contractor": "VA TECH WABAG LIMITED",
          "doc_title_full": "INSTRUMENT CABLE SCHEDULE - MY PROJECT", "doc_class": "INFORMATION", "discipline": "INSTRUMENTATION"}
    revs = revs or [{"rev_no": "0", "date": "01.01.2025", "description": "A", "prepared_by": "P0", "checked_by": "C0", "approved_by": "A0"},
                    {"rev_no": "1", "date": "02.02.2026", "description": "B", "prepared_by": "P1", "checked_by": "C1", "approved_by": "A1"}]
    data, _fn, err = generate_cover_sheet(pi, revs)
    assert err is None, err
    return data


def test_generated_cover_is_read_including_prepared_by_labels():
    cv = H.read_cover(openpyxl.load_workbook(io.BytesIO(real_cover())), "Coversheet")
    f = cv.fields
    assert (f["doc_no"].value, f["rev"].value, f["date"].value, f["prepared_by"].value, f["checked_by"].value, f["approved_by"].value) == \
           ("I0010-201", "1", "02.02.2026", "P1", "C1", "A1")
    assert not cv.warnings


def test_header_follows_a_project_cover_that_replaces_the_template_cover():
    from utils import deliverable_output as DO
    wb = build(rev="0")                                         # a template cover with another layout (revision table at rows 19-22)
    schedule_ws(wb)
    H.apply_standard_headers(wb, {"Sched": ("INSTRUMENT CABLE SCHEDULE", 12, None)})
    buf = io.BytesIO()
    wb.save(buf)
    out, name = DO.insert_cover(buf.getvalue(), real_cover())
    book = openpyxl.load_workbook(io.BytesIO(out))
    assert name == "COVERSHEET"
    ws = book["Sched"]
    date = next(str(c.value) for c in ws[3] if isinstance(c.value, str) and c.value.startswith("=") and "INDEX" in c.value)
    assert "$B$15:$B$23" in date                               # ranges now follow the replacing cover's revision table


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_replaced_cover_values_show_in_the_header():
    from utils import deliverable_output as DO
    wb = build(rev="0")
    schedule_ws(wb)
    H.apply_standard_headers(wb, {"Sched": ("INSTRUMENT CABLE SCHEDULE", 12, None)})
    buf = io.BytesIO()
    wb.save(buf)
    out, _ = DO.insert_cover(buf.getvalue(), real_cover())
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "h.xlsx"
        src.write_bytes(out)
        subprocess.run(["soffice", "--headless", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(Path(d) / "o"), str(src)],
                       capture_output=True, timeout=170)
        res = openpyxl.load_workbook(Path(d) / "o" / "h.xlsx", data_only=True)["Sched"]
    vals = {str(c.value) for r in res.iter_rows(min_row=1, max_row=6) for c in r if c.value is not None}
    assert {"I0010-201", "1", "02.02.2026", "P1", "C1", "A1", "CLI", "PMC", "MY PROJECT"} <= vals


def test_blank_cover_title_is_tba_not_the_next_label():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("COVERSHEET")
    ws["A10"] = "DOCUMENT TITLE\n\n\n\n\n\n"
    ws["A12"] = "STAMPING AREA"
    ws["A13"] = "DOCUMENT CLASS"
    cv = H.read_cover(wb, "COVERSHEET")
    assert cv.fields["title"].value == "TBA" and "DOCUMENT CLASS" not in str(cv.fields["title"].expr) and "$A$13" not in cv.fields["title"].expr
    assert any("DOCUMENT TITLE" in w for w in cv.warnings)
