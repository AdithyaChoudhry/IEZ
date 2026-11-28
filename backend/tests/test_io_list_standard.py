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
from utils.io_list_pagination import A3_PT, A4_PT, Section, visible_sheets  # noqa: E402

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


def fake_renderer(pages=None, calls=None, wrong_size=()):
    """A stand-in for LibreOffice: blank pages of the right paper size, `pages` = {sheet: count} (default 1)."""
    def render(workbook, sheets=None):
        from pypdf import PdfWriter
        names = [n for n in visible_sheets(workbook) if sheets is None or n in sheets]
        if calls is not None:
            calls.append(names)
        out = {}
        for n in names:
            w, h = (A3_PT[1], A3_PT[0]) if n == "IO List" and n not in wrong_size else A4_PT
            writer = PdfWriter()
            for _ in range((pages or {}).get(n, 1)):
                writer.add_blank_page(w, h)
            buf = io.BytesIO()
            writer.write(buf)
            out[n] = Section(buf.getvalue(), [(w, h)] * (pages or {}).get(n, 1))
        return out
    return render


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
    assert ab["A7"].value == "ABBREVIATIONS" and [ab.cell(8, c).value for c in (1, 2, 4)] == ["S.NO.", "ABBREVIATION", "DESCRIPTION"]
    rows = [(ab.cell(r, 1).value, ab.cell(r, 2).value, ab.cell(r, 4).value) for r in range(9, 27)]
    assert rows[0] == (1, "NA", "NOT APPLICABLE") and rows[-1] == (18, "SOV", "SOLENOID VALVE") and len(rows) == 18
    assert rows[3] == (4, "VFD", "VARIABLE FREQUECY DRIVE")                             # the template's own wording is kept


def _zone_widths(ws, zones):
    return [sum(ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width for c in range(a, b + 1)) for a, b in zones]


def _check_abbreviation_header(wb):
    ab, io_ = wb["ABBREVIATION"], wb["IO_BASIS"]
    zio, zab = [(1, 3), (4, 4), (5, 7), (8, 9), (10, 11)], [(1, 2), (3, 4), (5, 5), (6, 6), (7, 7)]
    assert _zone_widths(ab, zab) == pytest.approx(_zone_widths(io_, zio), abs=0.01)              # same shape and proportions
    assert [ab.row_dimensions[r].height for r in range(1, 7)] == [io_.row_dimensions[r].height for r in range(1, 7)]
    for (a, _), (b, _) in zip(zio, zab):
        for r in range(1, 7):
            x, y = io_.cell(r, a), ab.cell(r, b)
            assert (x.font.name, x.font.sz, x.font.b, x.fill.fill_type, x.alignment.horizontal, x.alignment.vertical) == \
                   (y.font.name, y.font.sz, y.font.b, y.fill.fill_type, y.alignment.horizontal, y.alignment.vertical), (r, b)
            assert (x.border.top.style, x.border.bottom.style, x.border.left.style) == (y.border.top.style, y.border.bottom.style, y.border.left.style), (r, b)
    labels = {c.coordinate: str(c.value).strip() for row in ab.iter_rows(min_row=1, max_row=6) for c in row
              if not isinstance(c, MergedCell) and c.column in (1, 6) and c.value}
    assert labels == {"A1": "PROJECT", "A3": "CLIENT", "A4": "LOCATION", "A5": "Doc. No.", "A6": "Rev. No.",
                      "F1": "Prepared", "F3": "Checked", "F4": "Approved", "F5": "Date", "F6": "Pages"}
    merged = {str(m) for m in ab.merged_cells.ranges}
    assert {"A1:B2", "C1:D2", "E1:E6", "F1:F2", "G1:G2", "A7:G7", "B8:C8", "D8:G8", "B26:C26", "D26:G26"} <= merged
    cells = [(r, c) for m in ab.merged_cells.ranges for r in range(m.min_row, m.max_row + 1) for c in range(m.min_col, m.max_col + 1)]
    assert len(cells) == len(set(cells))                                                          # no overlapping merged ranges
    assert str(ab.print_area).endswith("$A$1:$G$26") and ab.max_row == 26 and ab.max_column == 7  # nothing of the old header remains
    assert len(ab._images) == 1                                                                    # one WABAG logo


def test_abbreviation_header_is_the_six_row_iobasis_header_in_the_template():
    _check_abbreviation_header(D.load_standard_template())


def test_generated_workbook_has_the_corrected_abbreviation_header_with_the_same_metadata():
    out, _name, err, rep = build_io_list_document(df_of(fixture_rows()), COLS, None, "WITH_SUMMARY", None, renderer=fake_renderer())
    assert err is None
    wb = openpyxl.load_workbook(io.BytesIO(out))
    _check_abbreviation_header(wb)
    meta = {"project": "P", "client": "C", "location": "L", "doc_no": "DOC-1", "rev": "R2", "prepared": "AA", "checked": "BB",
            "approved": "CC", "date": "01.12.2026", "pages": 1}
    D.fill_front(wb, meta, {"toc": 1, "abbr": 1, "basis": 1})
    ab = wb["ABBREVIATION"]
    assert [ab[c].value for c in ("C1", "C3", "C4", "C5", "C6", "G1", "G3", "G4", "G5", "G6")] == \
           ["P", "C", "L", "DOC-1", "R2", "AA", "BB", "CC", "01.12.2026", 1]


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
    build_io_list_document(df_of(fixture_rows()), COLS, None, "WITH_SUMMARY", None, renderer=fake_renderer())
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


def test_a_long_equipment_name_wraps_instead_of_being_cut_off():
    name = "DIFFERENTIAL LEVEL TRANSMITTER (Diaphragm Seal Type with capillary on both side)"
    ws, res, info = basis_ws([rec("LT-1", "L-1", "", "AI", "LEVEL", name)])
    assert ws["C10"].value == name and ws["C10"].alignment.wrap_text and ws.row_dimensions[10].height > 23.4


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
    assert m["location"] == ""                                                            # the iEZ cover has no location: never invented


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
LINES = ("cover", "toc", "abbr", "basis", "iolist", "summary")


def shts(wb):
    toc = wb["TABLE OF CONTENTS"]
    return [toc.cell(r, 15).value for r in range(9, 15)]


def test_assembly_writes_measured_counts_total_pages_and_a_matching_pdf():
    from pypdf import PdfReader
    calls = []
    out, name, err, rep = build_io_list_document(df_of(fixture_rows()), COLS, None, "WITH_SUMMARY", cover(),
                                                 renderer=fake_renderer({"IO_BASIS": 2, "IO List": 7}, calls))
    assert err is None and rep["pages"] == {"cover": 1, "toc": 1, "abbr": 1, "basis": 2, "iolist": 7, "summary": 1} and rep["pages_verified"]
    assert rep["total_pages"] == 13 and len(PdfReader(io.BytesIO(rep["_pdf"])).pages) == 13
    wb = openpyxl.load_workbook(io.BytesIO(out))
    assert wb.sheetnames == ["COVER SHEET", "TABLE OF CONTENTS", "ABBREVIATION", "IO_BASIS", "IO List", "IO Summary"]
    assert shts(wb) == [1, 1, 1, 2, 7, 1] and wb["TABLE OF CONTENTS"]["O16"].value == "=SUM(O9:O14)"
    assert openpyxl.load_workbook(io.BytesIO(out), data_only=True)["TABLE OF CONTENTS"]["O16"].value == 13      # no empty / stale total
    assert wb["COVER SHEET"]["P4"].value == "1 OF 13"
    from utils.io_list_header import field_cells
    assert [field_cells(wb[n])["pages"].value for n in ("TABLE OF CONTENTS", "ABBREVIATION", "IO_BASIS")] == [1, 1, 2]
    assert "IO List" in calls[0] and "COVER SHEET" in calls[0] and all("IO List" not in c for c in calls[1:])   # the heavy sheet is rendered once
    assert not any("normally one" in w for w in rep["warnings"])                          # IO_BASIS and IO List may take several pages


def test_every_generation_counts_its_own_pages():
    for n in (3, 11):
        rep = build_io_list_document(df_of(fixture_rows()), COLS, None, "WITH_SUMMARY", cover(), renderer=fake_renderer({"IO List": n}))[3]
        assert rep["pages"]["iolist"] == n and rep["total_pages"] == n + 5


def test_a_one_page_sheet_that_overflows_is_reported_with_its_actual_count():
    out, _n, err, rep = build_io_list_document(df_of(fixture_rows()), COLS, None, "WITH_SUMMARY", cover(),
                                               renderer=fake_renderer({"ABBREVIATION": 2}))
    assert shts(openpyxl.load_workbook(io.BytesIO(out)))[2] == 2 and any("ABBREVIATION prints on 2 pages" in w for w in rep["warnings"])


def test_a_wrong_paper_size_is_never_reported_as_a_verified_pdf():
    rep = build_io_list_document(df_of(fixture_rows()), COLS, None, "WITH_SUMMARY", cover(), renderer=fake_renderer(wrong_size=("IO List",)))[3]
    assert rep["_pdf"] is None and any("instead of A3 landscape" in w for w in rep["warnings"])


def test_without_summary_the_summary_line_is_zero_and_no_cover_means_zero():
    out, name, err, rep = build_io_list_document(df_of(fixture_rows()), COLS, None, "WITHOUT_SUMMARY", None, renderer=fake_renderer({"IO List": 3}))
    assert shts(openpyxl.load_workbook(io.BytesIO(out))) == [0, 1, 1, 1, 3, 0] and rep["total_pages"] == 6
    assert any("No linked cover sheet" in w for w in rep["warnings"])


def test_pagination_unavailable_is_reported_and_leaves_the_counts_empty():
    from utils.io_list_pagination import PaginationUnavailable

    def renderer(workbook, sheets=None):
        raise PaginationUnavailable("no renderer")
    out, name, err, rep = build_io_list_document(df_of(fixture_rows()), COLS, None, "WITH_SUMMARY", cover(), renderer=renderer)
    wb = openpyxl.load_workbook(io.BytesIO(out))
    assert err is None and shts(wb) == [None] * 6 and any("no renderer" in w for w in rep["warnings"]) and rep["_pdf"] is None
    assert wb["COVER SHEET"]["P4"].value == "1 of 9" and not rep["pages_verified"]       # the cover's own entry stays: nothing is estimated
    assert wb["IO List"].page_setup.paperSize == 8                                     # the print settings do not depend on the renderer


def test_page_counting_and_the_combined_pdf_do_not_need_pypdf(monkeypatch):
    """The production server has pypdfium2 but not pypdf."""
    from utils.io_list_pagination import combine, page_sizes
    sections = fake_renderer({"IO List": 3})(build_io_list_document(df_of(fixture_rows()), COLS, None, "WITH_SUMMARY", None,
                                                                    renderer=fake_renderer())[0])
    for name in [n for n in sys.modules if n == "pypdf" or n.startswith("pypdf.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "pypdf", None)                                       # any "import pypdf" now fails
    pdf = combine(list(sections.items()))
    assert len(page_sizes(pdf)) == 7 and [s for s in page_sizes(pdf) if s[0] > 1000] == [s for s in page_sizes(sections["IO List"].pdf)]


# ───────── Location ─────────
def location_of(out):
    from utils.io_list_header import field_cells
    wb = openpyxl.load_workbook(io.BytesIO(out))
    return [field_cells(wb[n])["location"].value for n in ("TABLE OF CONTENTS", "ABBREVIATION", "IO_BASIS")]


def cover_with_location(value):
    wb = openpyxl.load_workbook(io.BytesIO(cover()))
    ws = wb.worksheets[0]
    r = ws.max_row + 2
    ws.cell(r, 1).value, ws.cell(r, 3).value = "LOCATION", value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build(cover_bytes, location, rows=None):
    return build_io_list_document(df_of(rows or fixture_rows()), COLS, None, "WITH_SUMMARY", cover_bytes, renderer=fake_renderer(), location=location)


def test_the_entered_location_reaches_all_three_headers_and_never_the_next_request():
    for value in ("Kolkata  STP", "Delhi Works"):
        out, _n, err, rep = build(cover(), value)
        assert err is None and location_of(out) == [" ".join(value.split())] * 3
        assert rep["location"]["source"] == "entered for this document"
    out, _n, _e, rep = build(cover(), "")
    assert location_of(out) == [None] * 3 and any("No Location" in w for w in rep["warnings"])


def test_a_location_on_the_cover_wins_and_a_different_typed_one_is_reported():
    out, _n, _e, rep = build(cover_with_location("Cover Town"), "Typed Town")
    assert location_of(out) == ["Cover Town"] * 3 and any("Typed Town" in w and "not used" in w for w in rep["warnings"])
    out, _n, _e, rep = build(cover_with_location("Cover Town"), "")
    assert location_of(out) == ["Cover Town"] * 3 and rep["location"]["source"] == "cover sheet"


def test_an_empty_cover_location_never_overwrites_the_typed_one_and_placeholders_are_refused():
    out, _n, err, _r = build(cover_with_location(""), "Typed Town")
    assert err is None and location_of(out) == ["Typed Town"] * 3
    out, _n, err, _r = build(cover(), "TBA")
    assert out is None and "placeholder" in err


def test_a_long_location_wraps_in_a_taller_row():
    out = build(cover(), "A VERY LONG PROJECT LOCATION " * 5)[0]
    wb = openpyxl.load_workbook(io.BytesIO(out))
    for name in ("TABLE OF CONTENTS", "ABBREVIATION", "IO_BASIS"):
        assert wb[name].row_dimensions[4].height > 17.6
        from utils.io_list_header import field_cells
        assert field_cells(wb[name])["location"].alignment.wrap_text


def test_the_instrument_location_column_of_the_io_list_is_untouched():
    cols = COLS + ["LOCATION"]
    df = df_of(fixture_rows())
    df["LOCATION"] = "FIELD AREA"
    out = build_io_list_document(df, cols, None, "WITH_SUMMARY", None, renderer=fake_renderer(), location="Project Town")[0]
    ws = openpyxl.load_workbook(io.BytesIO(out))["IO List"]
    assert {ws.cell(r, len(cols)).value for r in range(2, ws.max_row + 1)} == {"FIELD AREA"}


# ───────── print settings ─────────
def settings(ws):
    ps = ws.page_setup
    return (ps.paperSize, ps.orientation, ps.fitToWidth, ps.fitToHeight, ws.sheet_properties.pageSetUpPr.fitToPage, ps.scale, ps.firstPageNumber,
            str(ws.print_area).replace("'", "").split("!")[-1], len(ws.row_breaks.brk))


def test_every_sheet_has_its_own_paper_size_and_a_print_area_of_its_actual_content():
    out = build(cover(), "Town")[0]
    wb = openpyxl.load_workbook(io.BytesIO(out))
    n = len(fixture_rows()) + 1
    s = wb["IO Summary"]
    assert settings(wb["COVER SHEET"]) == (9, "portrait", 1, 1, True, None, None, "$A$1:$P$24", 0)
    assert settings(wb["TABLE OF CONTENTS"]) == (9, "portrait", 1, 1, True, None, None, "$A$1:$O$25", 0)
    assert settings(wb["ABBREVIATION"]) == (9, "portrait", 1, 1, True, None, None, "$A$1:$G$26", 0)
    basis = settings(wb["IO_BASIS"])
    assert basis[:7] == (9, "portrait", 1, 0, True, None, None) and wb["IO_BASIS"].print_title_rows == "$8:$9"
    assert settings(wb["IO List"]) == (8, "landscape", 1, 0, True, None, None, f"$A$1:$G${n}", 0) and wb["IO List"].print_title_rows == "$1:$1"
    assert settings(s) == (9, "portrait", 1, 1, True, None, None, f"$A$1:$C${s.max_row}", 0)       # no IS/NIS column in this IODB


def test_the_print_area_follows_the_data_size_and_selected_columns():
    for rows, cols in ((fixture_rows()[:5], COLS[:3]), (fixture_rows() * 4, COLS)):
        out = build_io_list_document(df_of(rows), cols, None, "WITH_SUMMARY", None, renderer=fake_renderer())[0]
        ws = openpyxl.load_workbook(io.BytesIO(out))["IO List"]
        assert str(ws.print_area).endswith(f"$A$1:${openpyxl.utils.get_column_letter(len(cols))}${len(rows) + 1}")
        assert ws.max_row == len(rows) + 1 and all(ws.row_dimensions[r].height for r in (1, ws.max_row))


# ───────── I/O Summary ─────────
def summary_rows():
    cols = COLS + ["IS/NIS TYPE"]
    data = [("AI", "IS"), ("AI", "NIS"), ("AO", "IS"), ("DI", "NIS"), ("DO", "NIS"), ("SOFT", ""), ("SOFT", None), ("", "IS"), ("TBA", ""), (None, "")]
    rows = [{**rec(f"T-{i}", f"L-{i}", "", t, "X", "SWITCH"), "IS/NIS TYPE": k} for i, (t, k) in enumerate(data)]
    return pd.DataFrame(rows, columns=cols), cols


def test_summary_has_five_columns_no_not_set_and_totals_over_the_shown_rows():
    df, cols = summary_rows()
    out, _n, err, rep = build_io_list_document(df, cols, None, "WITH_SUMMARY", None, renderer=fake_renderer())
    wb = openpyxl.load_workbook(io.BytesIO(out))
    ws = wb["IO Summary"]
    table = [list(r) for r in ws.iter_rows(min_row=4, values_only=True)]
    assert table == [["SL.NO", "SIGNAL I/O TYPE", "NO. OF SIGNALS", "IS", "NIS"], [1, "AI", 2, 1, 1], [2, "AO", 1, 1, 0], [3, "DI", 1, 0, 1],
                     [4, "DO", 1, 0, 1], [5, "SOFT", 2, 0, 0], [None, "TOTAL", "=SUM(C5:C9)", "=SUM(D5:D9)", "=SUM(E5:E9)"]]
    assert ws.max_column == 5 and sorted(map(str, ws.merged_cells.ranges)) == ["A1:E1", "A2:E2"] and str(ws.print_area).endswith("$A$1:$E$10")
    values = openpyxl.load_workbook(io.BytesIO(out), data_only=True)["IO Summary"]
    assert [values.cell(10, c).value for c in (3, 4, 5)] == [7, 2, 3]
    assert "10 I/O List rows" in ws["A2"].value and "7 with a stated" in ws["A2"].value
    assert wb["IO List"].max_row == 11                                                    # no record was removed from the I/O List
    s = rep["summary"]
    assert (s["source_records"], s["counted"], s["excluded"]) == (10, 7, 3)
    assert [x["tag"] for x in s["excluded_records"]] == ["T-7", "T-8", "T-9"] and any("3 of 10" in w and "T-7" in w for w in rep["warnings"])


def test_the_summary_shared_with_the_cable_schedule_is_unchanged():
    from utils.io_summary import append_io_summary_sheet, build_io_summary
    wb = openpyxl.Workbook()
    ws = append_io_summary_sheet(wb, build_io_summary(summary_rows()[0]))
    assert [c.value for c in ws[4]] == ["SL.NO", "SIGNAL I/O TYPE", "NO. OF SIGNALS", "IS", "NIS", "IS/NIS NOT SET"]
    assert "NOT SET" in [ws.cell(r, 2).value for r in range(5, ws.max_row)] and not ws.print_area


# ───────── real rendering ─────────
@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_real_rendering_matches_the_toc_total_and_the_page_sizes():
    from pypdf import PdfReader
    from utils.io_list_pagination import count_pages, size_name
    cv = cover()
    rows = fixture_rows() * 8
    out, name, err, rep = build_io_list_document(df_of(rows), COLS, None, "WITH_SUMMARY", cv, location="Town")
    assert err is None and rep["pages_verified"], rep["warnings"]
    pages = count_pages(out)                                                              # an independent render of the delivered workbook
    assert [pages[n] for n in ("COVER SHEET", "TABLE OF CONTENTS", "ABBREVIATION", "IO_BASIS", "IO List", "IO Summary")] == [rep["pages"][k] for k in LINES]
    assert rep["pages"]["cover"] == rep["pages"]["toc"] == rep["pages"]["abbr"] == rep["pages"]["summary"] == 1 and rep["pages"]["iolist"] > 1
    assert shts(openpyxl.load_workbook(io.BytesIO(out))) == [rep["pages"][k] for k in LINES]
    pdf = PdfReader(io.BytesIO(rep["_pdf"]))
    sizes = [size_name(float(p.mediabox.width), float(p.mediabox.height)) for p in pdf.pages]
    n = rep["pages"]["iolist"]
    first = sum(rep["pages"][k] for k in LINES[:4])
    assert len(sizes) == rep["total_pages"] and set(sizes[first:first + n]) == {"A3 landscape"}
    assert set(sizes[:first] + sizes[first + n:]) == {"A4 portrait"}
    assert all((p.extract_text() or "").strip() for p in pdf.pages)                        # no blank page
    assert "SIGNAL" in pdf.pages[first + 1].extract_text() and rows[-1]["TAG NO"] in pdf.pages[first + n - 1].extract_text()


# ───────── existing I/O List data is untouched ─────────
def test_io_list_values_are_identical_to_the_existing_generator():
    from utils.generators import generate_io_list
    df = df_of(fixture_rows())
    old, _n, e1 = generate_io_list(df, COLS, None, template_wb=None, output_mode="WITH_SUMMARY")
    new, _n2, e2, rep = build_io_list_document(df, COLS, None, "WITH_SUMMARY", None, renderer=fake_renderer())
    assert e1 is None and e2 is None
    a = openpyxl.load_workbook(io.BytesIO(old))
    b = openpyxl.load_workbook(io.BytesIO(new))
    assert [[c.value for c in r] for r in a.worksheets[0].iter_rows()] == [[c.value for c in r] for r in b["IO List"].iter_rows()]
    summary = {r[1].value: r[2].value for r in b["IO Summary"].iter_rows() if r[1].value in ("AI", "AO", "DI", "DO")}
    assert sum(summary.values()) == len(df) == 64                                       # all signals, not the representative ones (IO_BASIS lists 7 loops)
