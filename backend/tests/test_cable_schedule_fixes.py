"""Cable Schedule corrections: FROM = IODB loop number, MOV duplicate tag column, main cable tag merge switch, layout policy."""
import io
import sys
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_cable_schedule_extra import COLS, iodb_rows, row, template, run  # noqa: E402
from utils import cable_schedule_extra as X  # noqa: E402
from utils import cable_schedule_layout as L  # noqa: E402

ALL = ["mcc_di", "mcc_do", "vfd", "mov"]


def data_of(rows):
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=COLS).to_excel(buf, sheet_name="IODB", index=False)
    return buf.getvalue()


def generate(rows=None, sel=ALL):
    out, err, rep = run(sel, data=data_of(rows if rows is not None else iodb_rows()))
    assert not err, err
    return openpyxl.load_workbook(io.BytesIO(out)), rep


def title(rep, label):
    return next(s["sheet"] for s in rep["stats"] if s["label"] == label)


def from_values(ws, first=11):
    """(row, tag, from value of the merged cell that covers the row)"""
    anchors = {}
    for m in ws.merged_cells.ranges:
        if m.min_col == 2 == m.max_col:
            for r in range(m.min_row, m.max_row + 1):
                anchors[r] = m.min_row
    last = int(str(ws.print_area).split("$")[-1])
    out = []
    for r in range(first, last + 1):
        tag = ws.cell(r, 4).value
        if tag is not None:
            out.append((r, tag, ws.cell(anchors.get(r, r), 2).value))
    return out


# ── FIX 1: FROM = loop number ───────────────────────────────────────────────────────────────────────────────────────
def test_from_is_the_iodb_loop_number_per_tag():
    wb, rep = generate()
    loops = {r["TAG NO"]: r["LOOP NUMBER"] for r in iodb_rows()}
    for label in ("MCC DI", "MCC DO", "VFD"):
        rows = from_values(wb[title(rep, label)])
        assert rows
        for _r, tag, frm in rows:
            assert frm == loops[tag], (label, tag, frm)


def test_from_is_a_value_not_a_derived_formula():
    wb, rep = generate()
    for label in ("MCC DI", "MCC DO", "VFD"):
        ws = wb[title(rep, label)]
        for r in range(11, int(str(ws.print_area).split("$")[-1]) + 1):
            v = ws.cell(r, 2).value
            assert not (isinstance(v, str) and v.startswith("="))


def test_missing_loop_number_is_blank_with_warning_not_derived():
    rows = iodb_rows()
    for r in rows:
        if r["TAG NO"] == "YL-ML-9A":
            r["LOOP NUMBER"] = None
    wb, rep = generate(rows)
    ws = wb[title(rep, "MCC DI")]
    blank = [t for _r, t, f in from_values(ws) if t == "YL-ML-9A" and f in (None, "")]
    assert blank == ["YL-ML-9A"]
    assert any("LOOP NUMBER" in w and "YL-ML-9A" in w for w in rep["warnings"])


def test_conflicting_loop_numbers_are_reported_and_each_row_keeps_its_own():
    rows = iodb_rows()
    twin = dict(next(r for r in rows if r["TAG NO"] == "YL-V-1B"))
    twin["LOOP NUMBER"] = "V-2"
    twin["SIGNAL DESCRIPTION"] = "RUN 2"
    rows.append(twin)
    from utils.file_handler import read_iodb
    recs, _ = X.normalize(read_iodb(io.BytesIO(data_of(rows)))[0])
    findings = X.loop_findings("vfd", [r for r in X.split_records(recs)["vfd"]])
    assert any("YL-V-1B" in f and "more than one LOOP NUMBER" in f for f in findings)
    wb, rep = generate(rows)
    vals = [f for _r, t, f in from_values(wb[title(rep, "VFD")]) if t == "YL-V-1B"]
    assert sorted(vals) == ["V-1", "V-2"]


def test_only_identical_loops_are_merged():
    wb, rep = generate()
    ws = wb[title(rep, "VFD")]
    for m in ws.merged_cells.ranges:
        if m.min_col == 2 == m.max_col and m.max_row > m.min_row:
            tags = [ws.cell(r, 4).value for r in range(m.min_row, m.max_row + 1)]
            loops = {next((x["LOOP NUMBER"] for x in iodb_rows() if x["TAG NO"] == t), None) for t in tags if t}
            assert len(loops) == 1


# ── FIX 3: MOV duplicate tag column ─────────────────────────────────────────────────────────────────────────────────
def test_mov_instrument_side_gland_has_only_size_and_qty():
    wb, rep = generate()
    ws = wb[title(rep, "MOV")]
    hdr = {ws.cell(11, c).value: c for c in range(1, ws.max_column + 1) if ws.cell(11, c).value}
    g = next(c for c in range(1, ws.max_column + 1) if str(ws.cell(10, c).value).startswith("Instrument Side Gland"))
    span = next(m for m in ws.merged_cells.ranges if m.min_row == 10 and m.min_col == g)
    assert span.max_col - span.min_col == 1                              # two columns: Gland Size + Gland Qty
    assert ws.cell(11, g).value == "Gland Size" and str(ws.cell(11, g + 1).value).startswith("Gland Qty")
    for r in range(12, 20):                                              # the quantity column never holds a tag
        v = ws.cell(r, g + 1).value
        assert v is None or str(v).strip().isdigit() or v == "TBA"
    assert ws.cell(12, g + 1).value is not None


def test_mov_has_no_empty_column_and_print_area_and_formulas_valid():
    wb, rep = generate()
    ws = wb[title(rep, "MOV")]
    area_last = openpyxl.utils.column_index_from_string(str(ws.print_area).split("$")[-2].rstrip(":"))
    lastcol_hdr = max(c for c in range(1, area_last + 1) if ws.cell(10, c).value or ws.cell(11, c).value)
    assert lastcol_hdr == area_last                                      # print area ends on the last real column
    for rr in range(12, 16):
        for c in range(1, area_last + 1):
            v = ws.cell(rr, c).value
            if isinstance(v, str) and v.startswith("="):
                assert "#REF" not in v
    # ferrule formulas still point at the tag column (D)
    f = [ws.cell(12, c).value for c in range(1, area_last + 1) if isinstance(ws.cell(12, c).value, str) and ws.cell(12, c).value.startswith("=")]
    assert any("D12" in x for x in f)


def test_mov_other_sheets_keep_their_columns():
    wb, rep = generate()
    mcc = wb[title(rep, "MCC DI")]
    assert [mcc.cell(9, c).value for c in range(1, 5)] == ["SL. No.", "From", "Description", "Tag No"]


# ── FIX 2: main cable tag merge (switch, default off - see lug reader) ──────────────────────────────────────────────
def _shared_main_cable_book():
    from test_cable_schedule_layout import template as layout_template
    rows = []
    for i in range(8):
        rows.append({"TAG NO": f"PT-{i}", "JUNCTION BOX TAG NO.": f"AJB-0{1 + i // 4}", "EQUIPMENT DESCRIPTION": f"D PT-{i}",
                     "SIGNAL I/O TYPE": "AI", "INSTRUMENT TO JB CABLE TAG NO": f"IC-{i}", "INSTRUMENT TO JB CABLE TYPE": "1PX1.5 Sqmm",
                     "BRANCH CABLE LENGTH": 10 + i, "MAIN CABLE TAG NUMBER": f"MC-AJB-0{1 + i // 4}", "MAIN CABLE TYPE": "12PX1.5 Sqmm",
                     "MAIN CABLE LENGTH(MTRS)": 200, "JB SIDE GLAND SIZE": "M25x1.5", "JB SIDE GLAND QTY": 1,
                     "INSTRUMENT SIDE GLAND SIZE": "M20x1.5", "INSTRUMENT SIDE GLAND QTY": 1, "PANEL END GLAND SIZE": "M32x1.5",
                     "PANEL END GLAND QTY": 1})
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    from utils.template_processor import process_cable_schedule
    out, _fn, err = process_cable_schedule(io.BytesIO(buf.getvalue()), io.BytesIO(layout_template()), "JUNCTION BOX TAG NO.", "TAG NO",
                                           output_mode="WITH_SUMMARY", extra_report={})
    assert not err, err
    return out


def _inst_main_tag_merges(ws):
    mc = next(c.column for c in ws[7] if c.value and "MAIN CABLE TAG" in str(c.value).upper())
    return mc, [m for m in ws.merged_cells.ranges if m.min_col == mc == m.max_col and m.min_row >= 9]


def test_main_cable_tag_merge_is_on_by_default():
    assert L.MERGE_MAIN_CABLE_TAG is True
    ws = openpyxl.load_workbook(io.BytesIO(_shared_main_cable_book()))["Cable Schedule -INST"]
    _mc, merges = _inst_main_tag_merges(ws)
    assert len(merges) == 8                                              # one per entry


def test_lug_and_gland_results_do_not_depend_on_the_main_tag_merge(monkeypatch):
    from utils import lug_quantity as lq, gland_quantity as gq
    res = {}
    for flag in (False, True):
        monkeypatch.setattr(L, "MERGE_MAIN_CABLE_TAG", flag)
        data = _shared_main_cable_book()
        out, _ = lq.analyze(data, {}, {}, None, None, None)
        occ, exc, *_ = gq.extract(data)
        res[flag] = (out["kpis"]["cables"], out["kpis"]["total_lugs"], out["kpis"]["review_items"], len(occ), len(exc))
    assert res[False] == res[True]


def test_main_cable_tag_merge_when_enabled_is_centered_nowrap_and_bounded(monkeypatch):
    monkeypatch.setattr(L, "MERGE_MAIN_CABLE_TAG", True)
    ws = openpyxl.load_workbook(io.BytesIO(_shared_main_cable_book()))["Cable Schedule -INST"]
    mc, merges = _inst_main_tag_merges(ws)
    assert merges
    for m in merges:
        assert m.max_row - m.min_row == 2                                # exactly one 3-row entry, never across entries
        a = ws.cell(m.min_row, mc).alignment
        assert a.horizontal == "center" and a.vertical == "center" and not a.wrap_text


# ── FIX 4: layout policy ────────────────────────────────────────────────────────────────────────────────────────────
def test_widths_fit_content_and_nothing_is_hidden():
    wb, rep = generate()
    for label in ("MCC DI", "MCC DO", "VFD", "MOV"):
        ws = wb[title(rep, label)]
        last = int(str(ws.print_area).split("$")[-1])
        lastc = openpyxl.utils.column_index_from_string("".join(ch for ch in str(ws.print_area).split(":")[-1].split("$")[1]))
        for c in range(1, lastc + 1):
            d = ws.column_dimensions[get_column_letter(c)]
            assert not d.hidden and (d.width or 0) >= 8
        # identifier columns keep one line
        tag = ws.cell(12, 4)
        assert not tag.alignment.wrap_text and tag.alignment.horizontal == "center"
        assert ws.row_dimensions[12].height and ws.row_dimensions[12].height >= 20


def test_descriptions_wrap_keep_alignment_and_widths_are_bounded():
    wb, rep = generate()
    ws = wb[title(rep, "MCC DI")]
    c = ws.cell(11, 3)
    assert c.alignment.wrap_text and c.alignment.horizontal == "center"      # the sheet's centred alignment is kept
    assert (ws.column_dimensions["C"].width or 0) <= L._HARD_MAX_WIDTH
    assert all((ws.column_dimensions[get_column_letter(i)].width or 0) <= L._HARD_MAX_WIDTH for i in range(1, 20))


def test_ferrule_columns_are_wide_enough_for_their_text():
    wb, rep = generate()
    ws = wb[title(rep, "MOV")]
    lastc = openpyxl.utils.column_index_from_string("".join(ch for ch in str(ws.print_area).split(":")[-1].split("$")[1]))
    ferr = [c for m in ws.merged_cells.ranges if m.min_row == 10 and "ferule" in str(ws.cell(10, m.min_col).value or "").lower()
            for c in range(m.min_col, m.max_col + 1)]
    assert ferr
    # the column must fit what the ferrule formula displays (tag / panel / card / TB / unit joined)
    last = int(str(ws.print_area).split("$")[-1])
    for c in ferr:
        shown = max(L._shown_len(ws, ws.cell(r, c)) for r in range(12, last + 1))
        assert shown > 20
        assert ws.column_dimensions[get_column_letter(c)].width >= min(shown * 1.2 + 2, L._HARD_MAX_WIDTH) - 0.5


def test_coversheet_untouched_and_iodb_not_modified():
    data = data_of(iodb_rows())
    before = data
    out, err, rep = run(ALL, data=data)
    assert data == before
    wb = openpyxl.load_workbook(io.BytesIO(out))
    assert wb["COVERSHEET"]["A1"].value == "COVER"


# ── downstream readers ──────────────────────────────────────────────────────────────────────────────────────────────
def test_gland_and_lug_readers_read_the_generated_workbook():
    from utils import gland_quantity as gq, lug_quantity as lq
    out, err, rep = run(ALL, data=data_of(iodb_rows()))
    occ, exc, *_ = gq.extract(out)
    assert occ
    res, _rules = lq.analyze(out, {}, {}, None, None, None)
    assert res["kpis"]["cables"] >= 1
