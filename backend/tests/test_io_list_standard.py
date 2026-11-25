"""Standard I/O List workbook: stored template, linked cover metadata, IO_BASIS from the IODB, merged cells, printed page counts."""
import hashlib
import io
import re
import shutil
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest
from openpyxl.cell.cell import MergedCell

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils import io_list_document as D  # noqa: E402
from utils.io_list_basis import build_basis  # noqa: E402
from utils.io_list_builder import build_io_list_document  # noqa: E402

COLS = ["TAG NO", "LOOP NUMBER", "LOOP TYPE", "SIGNAL DESCRIPTION", "SIGNAL I/O TYPE", "INSTRUMENT TYPE NAME", "SUB SYSTEM"]
M1 = [("DI", "LOCAL/REMOTE INDICATION"), ("DI", "RUN INDICATION"), ("DI", "FAULT INDICATION"), ("DI", "READY FOR START"),
      ("DO", "START/STOP COMMAND"), ("DO", "AUTO/MANUAL COMMAND"), ("AI", "CURRENT INDICATION")]


def rec(tag, loop, ltype, io, desc, inst, sub="-"):
    return dict(zip(COLS, [tag, loop, ltype, desc, io, inst, sub]))


def loops(prefix, n, ltype, sigs, inst, sub="MCC", start=1):
    out = []
    for i in range(n):
        lp = f"{prefix}-{start + i:03d}"
        for k, (io, d) in enumerate(sigs):
            out.append(rec(f"{prefix}{start + i:03d}{chr(65 + k)}", lp, ltype, io, d, inst, sub))
    return out


def df_of(rows):
    return pd.DataFrame(rows, columns=COLS)


def fixture_rows():
    rows = loops("MS", 5, "TYPE-M1", M1, "PUMP")
    rows += loops("VF", 2, "TYPE-M2", [("DI", "RUN INDICATION"), ("DI", "FAULT INDICATION"), ("DO", "START/STOP COMMAND"), ("AI", "SPEED FEEDBACK"),
                                       ("AO", "SPEED CONTROL")], "AIR BLOWER", "VFD")
    rows += loops("XV", 3, "TYPE-1", [("DI", "OPEN INDICATION"), ("DI", "CLOSE INDICATION"), ("DO", "OPEN COMMAND"), ("DO", "CLOSE COMMAND")],
                  "MOTORIZED SLUICE GATE", "-")
    rows += [rec(f"FIT-{i}", f"F-{i}", "", "AI", "FLOW", "ELECTROMAGNETIC FLOWMETER") for i in range(1, 4)]
    rows += [rec(f"PIT-{i}", f"P-{i}", "", "AI", "PRESSURE", "PRESSURE TRANSMITTER") for i in range(1, 3)]
    rows += [rec(f"LSL-{i}", f"L-{i}", "", "DI", "LEVEL", "LEVEL SWITCH") for i in range(1, 3)]
    return rows


# ───────── template ─────────
def test_standard_template_has_three_sheets_and_no_cover():
    wb = D.load_standard_template()
    assert wb.sheetnames == ["TABLE OF CONTENTS", "ABBREVIATION", "IO_BASIS"]


def test_standard_template_is_clean_of_project_data_links_and_address():
    raw = D.STANDARD_TEMPLATE.read_bytes()
    z = zipfile.ZipFile(io.BytesIO(raw))
    assert not [n for n in z.namelist() if "externalLink" in n]                      # no external workbook links
    names = re.findall(rb'<definedName[^>]*name="([^"]+)"', z.read("xl/workbook.xml"))
    assert all(n.startswith(b"_xlnm.") for n in names)                                  # only print areas / print titles, no copied names
    wb = D.load_standard_template()
    bad = re.compile(r"GAIL|PDIL|PC286|10P195|PATA|STORM|STROM|GUARD POND|SWGP|PRUTHI|Kolathur|No\.17|MANISH|RO BASED", re.I)
    for ws in wb:
        hits = [(c.coordinate, c.value) for r in ws.iter_rows() for c in r if isinstance(c.value, str) and bad.search(c.value)]
        assert hits == [], (ws.title, hits)
        assert not any(isinstance(c.value, str) and "COVERSHEET" in c.value.upper() for r in ws.iter_rows() for c in r)


def test_universal_header_is_the_iobasis_header_on_all_three_sheets():
    wb = D.load_standard_template()
    labels = {"PROJECT", "CLIENT", "LOCATION", "DOC. NO.", "REV. NO.", "PREPARED", "CHECKED", "APPROVED", "DATE", "PAGES"}
    for ws in wb:
        found = {str(c.value).strip().upper() for r in ws.iter_rows(min_row=1, max_row=14) for c in r if c.value and str(c.value).strip().upper() in labels}
        assert found == labels, ws.title
        assert len(ws._images) == 1                                                   # the WABAG logo only (no client / PMC logos, no signatures)
    assert not any(c.value for r in wb["TABLE OF CONTENTS"].iter_rows(min_row=1, max_row=6) for c in r
                   if isinstance(c.value, str) and ("VA TECH" in c.value or "Chennai" in c.value))


def test_abbreviation_content_is_unchanged():
    ab = D.load_standard_template()["ABBREVIATION"]
    rows = [(ab.cell(r, 1).value, ab.cell(r, 2).value, ab.cell(r, 4).value) for r in range(15, 33)]
    assert rows[0] == (1, "NA", "NOT APPLICABLE") and rows[-1] == (18, "SOV", "SOLENOID VALVE") and len(rows) == 18
    assert rows[3] == (4, "VFD", "VARIABLE FREQUECY DRIVE")                             # the template's own wording is kept


def test_template_iobasis_has_no_sample_engineering_rows():
    ws = D.load_standard_template()["IO_BASIS"]
    heads = [ws.cell(8, c).value for c in (1, 2, 3, 5, 10)]
    assert heads == ["SI.NO", "TYPE", "EQUIPMENT", "DESCRIPTION", "REMARK"]
    assert all(ws.cell(r, c).value in (None, "", "Note: ") for r in range(10, 15) for c in range(1, 12))
    assert ws.max_row == 14


def test_each_request_gets_an_independent_template_and_the_master_is_unchanged():
    before = hashlib.sha256(D.STANDARD_TEMPLATE.read_bytes()).hexdigest()
    a, b = D.load_standard_template(), D.load_standard_template()
    a["IO_BASIS"]["D1"].value = "PROJECT A"
    assert b["IO_BASIS"]["D1"].value is None
    build_io_list_document(df_of(fixture_rows()), COLS, None, "WITH_SUMMARY", None, pager=lambda wb: {})
    assert hashlib.sha256(D.STANDARD_TEMPLATE.read_bytes()).hexdigest() == before


# ───────── representative loops ─────────
def test_one_entry_per_motor_loop_type_with_the_actual_signals():
    res = build_basis(df_of(fixture_rows()))
    motors = [c for c in res.classes if c.category == "motor"]
    assert [m.type_label for m in motors] == ["TYPE-M1", "TYPE-M2"]
    assert motors[0].rows == [("DI", "LOCAL/REMOTE INDICATION"), ("DI", "RUN INDICATION"), ("DI", "FAULT INDICATION"), ("DI", "READY FOR START"),
                              ("DO", "START/STOP COMMAND"), ("DO", "AUTO/MANUAL COMMAND"), ("AI", "CURRENT INDICATION")]
    assert motors[0].loops == 5 and motors[0].status == "Consistent"


def test_signals_are_grouped_di_do_ai_ao_keeping_source_order():
    rows = loops("MS", 1, "M1", [("DI", "LOCAL/REMOTE"), ("DO", "START/STOP"), ("DI", "RUN"), ("AI", "CURRENT"), ("DI", "FAULT"), ("DO", "AUTO/MANUAL")], "PUMP")
    cls = build_basis(df_of(rows)).classes[0]
    assert cls.rows == [("DI", "LOCAL/REMOTE"), ("DI", "RUN"), ("DI", "FAULT"), ("DO", "START/STOP"), ("DO", "AUTO/MANUAL"), ("AI", "CURRENT")]
    assert cls.type_label == "TYPE-M1"                                                  # M1 -> TYPE-M1, never TYPE-TYPE-M1
    assert build_basis(df_of(loops("MS", 1, "TYPE-M1", M1, "PUMP"))).classes[0].type_label == "TYPE-M1"


def test_most_frequent_configuration_wins_and_the_class_is_flagged():
    a = [("DI", "RUN INDICATION"), ("DO", "START/STOP COMMAND")]
    b = [("DI", "RUN INDICATION"), ("DI", "FAULT INDICATION"), ("DO", "START/STOP COMMAND")]
    c = [("DI", "RUN INDICATION"), ("DO", "START COMMAND")]
    rows = loops("MS", 1, "TYPE-M1", a, "PUMP", start=1) + loops("MS", 3, "TYPE-M1", b, "PUMP", start=2) + loops("MS", 1, "TYPE-M1", c, "PUMP", start=5)
    cls = build_basis(df_of(rows)).classes[0]
    assert cls.status == "Review Required" and cls.representative == "MS-002" and cls.rows[1] == ("DI", "FAULT INDICATION")
    assert "3 different" in cls.notes[0]


def test_equal_signal_count_but_different_functions_are_different_configurations():
    rows = loops("MS", 1, "TYPE-M1", [("DI", "RUN INDICATION"), ("DO", "START COMMAND")], "PUMP", start=1) + \
        loops("MS", 1, "TYPE-M1", [("DI", "FAULT INDICATION"), ("DO", "START COMMAND")], "PUMP", start=2)
    cls = build_basis(df_of(rows)).classes[0]
    assert len(cls.configs) == 2 and cls.status == "Review Required" and any("equally common" in n for n in cls.notes)


def test_source_order_and_case_do_not_make_configurations_different():
    rows = loops("MS", 1, "TYPE-M1", [("DI", "RUN INDICATION"), ("DO", "START COMMAND")], "PUMP", start=1) + \
        loops("MS", 1, "TYPE-M1", [("DO", "start command"), ("DI", " Run  Indication ")], "PUMP", start=2)
    assert build_basis(df_of(rows)).classes[0].status == "Consistent"


def test_engineer_can_choose_another_real_loop_but_not_an_invented_one():
    a = [("DI", "RUN INDICATION")]
    b = [("DI", "FAULT INDICATION")]
    rows = loops("MS", 2, "TYPE-M1", a, "PUMP", start=1) + loops("MS", 1, "TYPE-M1", b, "PUMP", start=3)
    res = build_basis(df_of(rows), overrides={"motor|TYPE-M1": "MS-003"})
    assert res.classes[0].representative == "MS-003" and res.classes[0].rows == [("DI", "FAULT INDICATION")]
    bad = build_basis(df_of(rows), overrides={"motor|TYPE-M1": "NOPE"})
    assert bad.classes[0].representative == "MS-001" and any(i["severity"] == "error" for i in bad.issues)


def test_additional_motor_types_are_found_dynamically():
    rows = loops("MS", 1, "TYPE-M1", M1, "PUMP") + loops("MX", 1, "TYPE-M7", [("DI", "RUN")], "PUMP", start=1)
    assert [c.type_label for c in build_basis(df_of(rows)).classes if c.category == "motor"] == ["TYPE-M1", "TYPE-M7"]


# ───────── valves / instruments ─────────
def test_valves_keep_their_actual_commands_and_a_valve_without_loop_type_gets_a_dash():
    rows = loops("XV", 2, "TYPE-1", [("DI", "OPEN INDICATION"), ("DO", "OPEN COMMAND"), ("DO", "CLOSE COMMAND")], "MOTORIZED SLUICE GATE", "-") + \
        loops("SV", 2, "", [("DO", "OPEN COMMAND")], "SOLENOID VALVE", "-")
    res = build_basis(df_of(rows))
    v = [c for c in res.classes if c.category == "valve"]
    assert [(x.type_label, x.rows[-1]) for x in v] == [("TYPE-1", ("DO", "CLOSE COMMAND")), ("-", ("DO", "OPEN COMMAND"))]
    assert any(i["category"] == "Valve without Loop Type" for i in res.issues)


def test_each_instrument_type_appears_once_with_dash_type_and_feedback_description():
    res = build_basis(df_of(fixture_rows()))
    inst = [c for c in res.classes if c.category == "instrument"]
    assert sorted(c.equipment for c in inst) == ["ELECTROMAGNETIC FLOWMETER", "LEVEL SWITCH", "PRESSURE TRANSMITTER"]
    assert all(c.type_label == "-" for c in inst)
    em = next(c for c in inst if c.equipment == "ELECTROMAGNETIC FLOWMETER")
    assert em.rows == [("AI", "ELECTROMAGNETIC FLOWMETER Feedback")] and em.loops == 3                    # 3 records, one entry
    assert next(c for c in inst if c.equipment == "LEVEL SWITCH").rows == [("DI", "LEVEL SWITCH Feedback")]    # DI from the IODB, not assumed


def test_instrument_with_an_output_or_several_classifications_is_flagged_not_called_feedback():
    rows = [rec("X-1", "X-1", "", "DI", "ALARM", "BELT CONVEYOR"), rec("X-2", "X-2", "", "DO", "START CONVEYOR", "BELT CONVEYOR")]
    c = build_basis(df_of(rows)).classes[0]
    assert c.status == "Review Required" and ("DO", "START CONVEYOR") in c.rows and ("DO", "BELT CONVEYOR Feedback") not in c.rows


def test_order_is_motors_valves_instruments_then_other_and_serials_are_continuous():
    rows = fixture_rows() + loops("PK", 2, "Vendor Package", [("DI", "RUNNING"), ("AI", "SIGNAL")], "UV PACKAGE", "-")
    res = build_basis(df_of(rows))
    assert [c.category for c in res.classes] == ["motor", "motor", "valve", "instrument", "instrument", "instrument", "other"]
    wb = D.load_standard_template()
    D.write_io_basis(wb["IO_BASIS"], res)
    ws = wb["IO_BASIS"]
    assert [v for v in (ws.cell(r, 1).value for r in range(10, ws.max_row)) if isinstance(v, int)] == list(range(1, 8))


def test_missing_and_unknown_data_are_reported_and_soft_signals_are_not_hardwired_io():
    rows = [rec("A-1", "", "TYPE-M1", "DI", "RUN", "PUMP", "MCC"), rec("A-2", "L-2", "TYPE-M1", "XX", "RUN", "PUMP", "MCC"),
            rec("A-3", "L-3", "", "SOFT", "COMM", "TRANSMITTER"), rec("A-4", "L-4", "", "AI", "X", ""), rec("A-5", "L-5", "", "DI", "X", "SWITCH", "MCC")]
    cats = {i["category"] for i in build_basis(df_of(rows)).issues}
    assert {"Missing LOOP NUMBER", "Unknown I/O classification", "Non-hardwired signals", "Missing INSTRUMENT TYPE", "Missing LOOP TYPE for motor"} <= cats
    assert build_basis(pd.DataFrame(columns=COLS)).error
    assert "LOOP NUMBER" in build_basis(df_of(rows).drop(columns=["LOOP NUMBER"])).error


def test_the_iodb_is_not_modified_and_valid_repeated_signals_are_kept():
    rows = loops("MS", 1, "TYPE-M1", [("DI", "RUN"), ("DI", "RUN"), ("DO", "START")], "PUMP")
    df = df_of(rows)
    before = df.copy(deep=True)
    res = build_basis(df)
    assert df.equals(before) and res.classes[0].rows.count(("DI", "RUN")) == 2


# ───────── IO_BASIS sheet ─────────
def basis_ws(rows):
    wb = D.load_standard_template()
    res = build_basis(df_of(rows))
    info = D.write_io_basis(wb["IO_BASIS"], res)
    return wb["IO_BASIS"], res, info


def merged(ws):
    return {str(m) for m in ws.merged_cells.ranges}


def test_equipment_and_io_type_cells_are_merged_dynamically():
    ws, res, info = basis_ws(fixture_rows())
    m = merged(ws)
    assert {"A10:A16", "B10:B16", "C10:D16"} <= m                                          # 7 signals of M1
    assert "E10:E13" in m and "E14:E15" in m and "E16" not in " ".join(m)               # 4 DI, 2 DO merged; the single AI stays one cell
    assert ws["E10"].value == "DI" and ws["E14"].value == "DO" and ws["E16"].value == "AI"
    assert ws["F10"].value == "LOCAL/REMOTE INDICATION" and "F10:I10" in m               # one description per row, not merged vertically
    assert not any(re.match(r"^F\d+:F\d+$", x) for x in m)


def test_no_merge_crosses_an_equipment_boundary_and_merges_never_overlap():
    ws, res, info = basis_ws(fixture_rows())
    starts, r = [], 10
    for c in res.classes:
        starts.append((r, r + len(c.rows) - 1))
        r += len(c.rows)
    seen = set()
    for m in ws.merged_cells.ranges:
        for rr in range(m.min_row, m.max_row + 1):
            for cc in range(m.min_col, m.max_col + 1):
                assert (rr, cc) not in seen
                seen.add((rr, cc))
        if 10 <= m.min_row <= info["table_end"] and m.max_row > m.min_row and m.min_col in (1, 2, 3, 5):
            assert any(a <= m.min_row and m.max_row <= b for a, b in starts), str(m)


def test_only_the_five_headings_remain_and_the_table_area_is_exact():
    ws, res, info = basis_ws(fixture_rows())
    assert [ws.cell(8, c).value for c in (1, 2, 3, 5, 10)] == ["SI.NO", "TYPE", "EQUIPMENT", "DESCRIPTION", "REMARK"]
    assert info["rows"] == sum(len(c.rows) for c in res.classes) and ws.print_area.endswith(str(info["last_row"]))
    assert str(ws.cell(info["table_end"] + 2, 1).value).startswith("Note")                # the note box follows the table
    assert ws.cell(info["table_end"] + 1, 1).value is None


def test_merged_cells_are_centred_with_no_inner_lines():
    ws, res, info = basis_ws(fixture_rows())
    for a in ("A10", "B10", "C10", "E10"):
        al = ws[a].alignment
        assert al.vertical == "center" and (al.horizontal == "center" or a == "C10")
    assert ws["E11"].border.top.style is None and ws["E11"].border.bottom.style is None          # inside the merged DI cell
    assert ws["E13"].border.bottom.style == "thin" and ws["E10"].border.top.style == "thin"
    assert ws["F11"].border.top.style == "thin"                                                    # the rows of the descriptions stay separated


def test_long_text_gets_a_taller_row():
    rows = loops("MS", 1, "TYPE-M1", [("DI", "A VERY LONG SIGNAL DESCRIPTION " * 4)], "PUMP")
    ws, res, info = basis_ws(rows)
    assert ws.row_dimensions[10].height > 23.4


# ───────── cover sheet metadata ─────────
def cover(revs=None, project="SETTING UP A TEST PLANT"):
    from utils.coversheet_generator import generate_cover_sheet
    pi = {"doc_title_short": "I/O LIST", "project_description": project, "job_no": "PC999", "unit_no": "1", "project_no": "10P999", "doc_code": "I0001",
          "serial_no": "202", "page_no": "1 of 9", "client": "TEST CLIENT LTD", "pmc": "PMC", "contractor": "VA TECH WABAG LIMITED",
          "doc_title_full": "I/O LIST - TEST PLANT", "doc_class": "INFORMATION", "discipline": "INSTRUMENTATION"}
    revs = revs or [{"rev_no": "00", "date": "10-11-2026", "description": "First", "prepared_by": "AA", "checked_by": "BB", "approved_by": "CC"},
                    {"rev_no": "01", "date": "18-11-2026", "description": "Second", "prepared_by": "AA", "checked_by": "BB", "approved_by": "CC"},
                    {"rev_no": "02", "date": "24-11-2026", "description": "Third", "prepared_by": "DD", "checked_by": "EE", "approved_by": "FF"}]
    data, _n, err = generate_cover_sheet(pi, revs)
    assert err is None, err
    return data


def test_cover_metadata_comes_from_the_linked_cover_and_the_date_is_the_latest_revision():
    m = D.read_cover_meta(cover())
    assert (m["project"], m["client"], m["doc_no"], m["rev"], m["date"]) == ("SETTING UP A TEST PLANT", "TEST CLIENT LTD", "10P999-I0001-202", "02", "24-11-2026")
    assert (m["prepared"], m["checked"], m["approved"]) == ("DD", "EE", "FF")
    assert [r["rev"] for r in m["revisions"]] == ["02", "01", "00"]                      # as on the cover: newest first
    assert m["location"] == "" and any("location" in w for w in m["warnings"])           # the cover has no location: never invented


def test_without_a_cover_nothing_is_invented():
    m = D.read_cover_meta(None)
    assert m["project"] == m["doc_no"] == m["date"] == "" and m["revisions"] == []


# ───────── headers, TOC, revision history ─────────
def filled(revs=None, counts=None):
    wb = D.load_standard_template()
    meta = D.read_cover_meta(cover(revs))
    D.fill_front(wb, meta, counts if counts is not None else {"cover": 1, "toc": 1, "abbr": 1, "basis": 1, "iolist": 25, "summary": 1}, "I/O LIST - TEST PLANT")
    return wb, meta


def test_headers_of_all_three_sheets_carry_the_same_metadata():
    wb, meta = filled()
    for name, pages in (("TABLE OF CONTENTS", 1), ("ABBREVIATION", 1), ("IO_BASIS", 1)):
        cells = D.field_cells if False else None
        from utils.io_list_header import field_cells
        f = {k: c.value for k, c in field_cells(wb[name]).items()}
        assert f["project"] == "SETTING UP A TEST PLANT" and f["client"] == "TEST CLIENT LTD" and f["doc_no"] == "10P999-I0001-202"
        assert f["rev"] == "02" and f["date"] == "24-11-2026" and f["pages"] == pages and f["location"] is None
        assert (f["prepared"], f["checked"], f["approved"]) == ("DD", "EE", "FF")


def test_toc_shts_column_total_formula_and_description():
    wb, _ = filled()
    toc = wb["TABLE OF CONTENTS"]
    assert [toc.cell(r, 15).value for r in range(9, 15)] == [1, 1, 1, 1, 25, 1]
    assert toc["O16"].value == "=SUM(O9:O14)"                                             # a real SUM over the Shts. column, no SHEET() formula
    assert toc["B13"].value == "I/O LIST - TEST PLANT"
    assert not any(isinstance(c.value, str) and "SHEET()" in c.value.upper() for r in toc.iter_rows() for c in r)


def test_revision_history_from_the_cover_newest_first_and_no_old_values():
    wb, _ = filled()
    toc = wb["TABLE OF CONTENTS"]
    assert [[toc.cell(r, c).value for c in (1, 2, 10, 12, 14, 15)] for r in (22, 23, 24)] == [
        ["02", "Third", "24-11-2026", "DD", "EE", "FF"], ["01", "Second", "18-11-2026", "AA", "BB", "CC"], ["00", "First", "10-11-2026", "AA", "BB", "CC"]]
    assert toc["A25"].value == "REV." and toc["A21"].value is None
    assert not any(c.value in ("AKB", "AG", "VE", "06.10.2025") for r in toc.iter_rows() for c in r)


def test_revision_table_grows_safely_when_the_cover_has_more_revisions():
    revs = [{"rev_no": f"{i:02d}", "date": f"0{i}-01-2026", "description": f"R{i}", "prepared_by": "A", "checked_by": "B", "approved_by": "C"} for i in range(6)]
    wb, _ = filled(revs)
    toc = wb["TABLE OF CONTENTS"]
    head = next(r for r in range(1, toc.max_row + 1) if toc.cell(r, 1).value == "REV.")
    assert [toc.cell(r, 1).value for r in range(head - 6, head)] == ["05", "04", "03", "02", "01", "00"]
    assert toc.print_area.endswith(str(head))
    assert any(str(m).startswith("J") and m.min_row == head - 6 for m in toc.merged_cells.ranges)       # the new rows keep the table's merges


def test_missing_counts_stay_empty_not_estimated():
    wb, _ = filled(counts={})
    toc = wb["TABLE OF CONTENTS"]
    assert all(toc.cell(r, 15).value is None for r in range(9, 15))


# ───────── page counts / assembly ─────────
def test_assembly_writes_measured_counts_and_verifies_them():
    calls = []

    def pager(wb_bytes):
        calls.append(openpyxl.load_workbook(io.BytesIO(wb_bytes)).sheetnames)
        return {"COVER SHEET": 1, "TABLE OF CONTENTS": 1, "ABBREVIATION": 1, "IO_BASIS": 2, "IO List": 7, "IO Summary": 1}
    out, name, err, rep = build_io_list_document(df_of(fixture_rows()), COLS, None, "WITH_SUMMARY", cover(), pager=pager)
    assert err is None and rep["pages"] == {"cover": 1, "toc": 1, "abbr": 1, "basis": 2, "iolist": 7, "summary": 1} and rep["pages_verified"]
    wb = openpyxl.load_workbook(io.BytesIO(out))
    assert wb.sheetnames == ["TABLE OF CONTENTS", "ABBREVIATION", "IO_BASIS", "IO List", "IO Summary"]
    assert [wb["TABLE OF CONTENTS"].cell(r, 15).value for r in range(9, 15)] == [1, 1, 1, 2, 7, 1]
    assert any("IO_BASIS prints on 2 pages" in w for w in rep["warnings"])               # an overflow is reported, never hidden
    assert "IO List" in calls[0] and "COVER SHEET" in calls[0] and all("IO List" not in c for c in calls[1:])   # the heavy sheet is rendered once


def test_without_summary_the_summary_line_is_zero_and_no_cover_means_zero():
    def pager(b):
        return {"TABLE OF CONTENTS": 1, "ABBREVIATION": 1, "IO_BASIS": 1, "IO List": 3}
    out, name, err, rep = build_io_list_document(df_of(fixture_rows()), COLS, None, "WITHOUT_SUMMARY", None, pager=pager)
    toc = openpyxl.load_workbook(io.BytesIO(out))["TABLE OF CONTENTS"]
    assert [toc.cell(r, 15).value for r in range(9, 15)] == [0, 1, 1, 1, 3, 0]
    assert any("No linked cover sheet" in w for w in rep["warnings"])


def test_pagination_unavailable_is_reported_and_leaves_the_counts_empty():
    from utils.io_list_pagination import PaginationUnavailable

    def pager(b):
        raise PaginationUnavailable("no renderer")
    out, name, err, rep = build_io_list_document(df_of(fixture_rows()), COLS, None, "WITH_SUMMARY", cover(), pager=pager)
    toc = openpyxl.load_workbook(io.BytesIO(out))["TABLE OF CONTENTS"]
    assert err is None and all(toc.cell(r, 15).value is None for r in range(9, 15)) and any("no renderer" in w for w in rep["warnings"])


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_real_rendering_matches_the_toc_total():
    from utils import deliverable_output as DO
    from utils.io_list_pagination import count_pages
    cv = cover()
    out, name, err, rep = build_io_list_document(df_of(fixture_rows() * 3), COLS, None, "WITH_SUMMARY", cv)
    assert err is None and rep["pages_verified"], rep["warnings"]
    final = DO.insert_cover(out, cv)[0]
    pages = count_pages(final)
    assert sum(pages.values()) == sum(rep["pages"].values())
    toc = openpyxl.load_workbook(io.BytesIO(final))["TABLE OF CONTENTS"]
    assert [toc.cell(r, 15).value for r in range(9, 15)] == [rep["pages"][k] for k in ("cover", "toc", "abbr", "basis", "iolist", "summary")]
    assert rep["pages"]["toc"] == rep["pages"]["abbr"] == rep["pages"]["basis"] == 1


# ───────── existing I/O List and Summary are untouched ─────────
def test_io_list_and_summary_are_identical_to_the_existing_generator():
    from utils.generators import generate_io_list
    df = df_of(fixture_rows())
    old, _n, e1 = generate_io_list(df, COLS, None, template_wb=None, output_mode="WITH_SUMMARY")
    new, _n2, e2, rep = build_io_list_document(df, COLS, None, "WITH_SUMMARY", None, pager=lambda b: {})
    assert e1 is None and e2 is None
    a = openpyxl.load_workbook(io.BytesIO(old))
    b = openpyxl.load_workbook(io.BytesIO(new))
    for src, dst in ((a.worksheets[0], b["IO List"]), (a["IO Summary"], b["IO Summary"])):
        va = [[c.value for c in r] for r in src.iter_rows()]
        vb = [[c.value for c in r] for r in dst.iter_rows()]
        assert va == vb
    summary = {r[1].value: r[2].value for r in b["IO Summary"].iter_rows() if r[1].value in ("AI", "AO", "DI", "DO")}
    assert sum(summary.values()) == len(df) == 64                                       # all signals, not the representative ones (IO_BASIS lists 7 loops)
