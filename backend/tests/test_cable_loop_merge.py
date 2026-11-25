"""MCC DI / MCC DO: consecutive FROM cells with the same IODB loop number are merged vertically (presentation only)."""
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import openpyxl
import pandas as pd
import pytest
from openpyxl.worksheet.cell_range import CellRange

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_cable_schedule_extra import COLS, row, template  # noqa: E402
from utils import cable_schedule_extra as X  # noqa: E402
from utils.template_processor import process_cable_schedule  # noqa: E402

CAB = {"PANEL END GLAND SIZE": "M25", "TERMINAL STRIP NO.": "X101"}


def sigs(loop, n, io, start="A", cab=None, sub="MCC"):
    out = []
    for i in range(n):
        t = f"YL-{loop}{chr(ord(start) + i)}"
        out.append(row(t, loop, f"EQUIPMENT {loop}", f"SIGNAL {i + 1}", "PUMP", io, sub=sub, ctag=cab or f"IC-{loop}-{io}",
                       ctype="12Cx1.5", clen=100, **CAB))
    return out


def book(rows, merge=True, monkeypatch=None):
    rows = ([row("FIT-001", "F-001", "FEED", "FLOW", "FLOW TRANSMITTER", "AI", jb="JB-1", ctag="IC-JB-1", ctype="12Px1.5", clen=100)] + rows
            + sigs("V-1", 2, "DI", cab="IC-VFD-1", sub="VFD")
            + [row("ZA-MOV-1A", "MOV-1", "INLET GATE", "OPEN COMMAND", "MOTORIZED SLUICE GATE", "DO", ctag="IC-MOV-001", ctype="19Cx1.5", clen=150),
               row("ZS-MOV-1A", "MOV-1", "INLET GATE", "OPEN FEEDBACK", "MOTORIZED SLUICE GATE", "DI", ctag="IC-MOV-001", ctype="19Cx1.5", clen=150)])
    if not any(r["SIGNAL I/O TYPE"] == "DO" and r["SUB SYSTEM"] == "MCC" for r in rows):
        rows = rows + sigs("SC-ZD", 1, "DO")
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=COLS).to_excel(buf, sheet_name="IODB", index=False)
    if not merge and monkeypatch is not None:
        monkeypatch.setattr(X, "merge_consecutive_loops", lambda *a, **k: 0)
    rep = {}
    out, _fn, err = process_cable_schedule(io.BytesIO(buf.getvalue()), io.BytesIO(template()), "JUNCTION BOX TAG NO.", "TAG NO",
                                           output_mode="WITH_SUMMARY", extra_sheets=["mcc_di", "mcc_do", "vfd", "mov"], extra_report=rep)
    assert not err, err
    return out, openpyxl.load_workbook(io.BytesIO(out)), rep


def from_groups(ws, first=11):
    last = int(str(ws.print_area).split("$")[-1])
    groups = {}
    anchors = {}
    for m in ws.merged_cells.ranges:
        if m.min_col == m.max_col == 2 and m.min_row >= first:
            groups[m.min_row] = m.max_row
            for r in range(m.min_row, m.max_row + 1):
                anchors[r] = m.min_row
    return last, groups, anchors


def sheet_name(rep, label):
    return next(s["sheet"] for s in rep["stats"] if s["label"] == label)


def base_rows():
    rows = []
    rows += sigs("SC-1", 3, "DI") + sigs("SC-2", 3, "DI") + sigs("SC-3", 3, "DI")            # three DI per loop
    rows += sigs("SC-1", 2, "DO") + sigs("SC-2", 2, "DO")                                      # two DO per loop (not equal to DI)
    rows += sigs("SC-4", 5, "DI") + sigs("SC-5", 1, "DI")                                      # five / one
    rows += sigs("SC-4", 1, "DO")
    return rows


def test_three_signals_per_loop_are_merged(monkeypatch):
    _o, wb, rep = book(base_rows())
    ws = wb[sheet_name(rep, "MCC DI")]
    last, groups, anchors = from_groups(ws)
    sizes = sorted(e - s + 1 for s, e in groups.items())
    assert sizes.count(3) == 3 and sizes.count(5) == 1 and 1 not in sizes
    s = next(s for s, e in groups.items() if e - s + 1 == 3)
    assert ws.cell(s, 2).value.startswith("SC-") and all(ws.cell(r, 2).value is None for r in range(s + 1, s + 3))


def test_do_is_processed_independently_of_di():
    _o, wb, rep = book(base_rows())
    di, do = wb[sheet_name(rep, "MCC DI")], wb[sheet_name(rep, "MCC DO")]
    sd = sorted(e - s + 1 for s, e in from_groups(di)[1].items())
    so = sorted(e - s + 1 for s, e in from_groups(do)[1].items())
    assert sd == [3, 3, 3, 5] and so == [2, 2]              # SC-1 / SC-2 have 3 DI but 2 DO; SC-4 has 5 DI and one DO (kept single)
    assert from_groups(do)[0] - 10 == 5                     # five DO rows in all


def test_single_signal_loop_keeps_its_own_cell():
    _o, wb, rep = book(base_rows())
    ws = wb[sheet_name(rep, "MCC DI")]
    last, groups, anchors = from_groups(ws)
    single = [r for r in range(11, last + 1) if r not in anchors]
    assert len(single) == 1 and ws.cell(single[0], 2).value == "SC-5"


def test_every_row_keeps_its_loop_number_through_its_merged_cell():
    _o, wb, rep = book(base_rows())
    ws = wb[sheet_name(rep, "MCC DI")]
    last, groups, anchors = from_groups(ws)
    loops = {r["TAG NO"]: r["LOOP NUMBER"] for r in base_rows()}
    for r in range(11, last + 1):
        assert ws.cell(anchors.get(r, r), 2).value == loops[ws.cell(r, 4).value]


def test_missing_and_placeholder_loops_are_never_merged():
    rows = sigs("SC-1", 2, "DI") + [row("YL-X1", None, "NO LOOP", "S1", "PUMP", "DI", sub="MCC", ctag="IC-X", ctype="12Cx1.5", clen=1, **CAB),
                                    row("YL-X2", None, "NO LOOP", "S2", "PUMP", "DI", sub="MCC", ctag="IC-X", ctype="12Cx1.5", clen=1, **CAB),
                                    row("YL-T1", "TBA", "TBA LOOP", "S1", "PUMP", "DI", sub="MCC", ctag="IC-T", ctype="12Cx1.5", clen=1, **CAB),
                                    row("YL-T2", "TBA", "TBA LOOP", "S2", "PUMP", "DI", sub="MCC", ctag="IC-T", ctype="12Cx1.5", clen=1, **CAB)]
    _o, wb, rep = book(rows)
    ws = wb[sheet_name(rep, "MCC DI")]
    last, groups, anchors = from_groups(ws)
    assert [e - s + 1 for s, e in groups.items()] == [2]                    # only SC-1
    assert ws.cell(11, 2).value == "SC-1" and all(r not in anchors for r in range(13, last + 1))


def merge_ws(values, existing=()):
    wb = openpyxl.Workbook()
    ws = wb.active
    for i, v in enumerate(values):
        ws.cell(11 + i, 2, v)
        ws.cell(11 + i, 4, f"T{i}")
    for m in existing:
        ws.merge_cells(m)
    row_loops = {11 + i: v for i, v in enumerate(values)}
    return ws, row_loops


def test_non_consecutive_identical_loops_are_separate_groups():
    vals = ["L1", "L1", "L2", "L1", "L1", "L1"]
    ws, rl = merge_ws(vals)
    assert X.merge_consecutive_loops(ws, 2, 11, 16, rl) == 2
    assert sorted(str(m) for m in ws.merged_cells.ranges) == ["B11:B12", "B14:B16"]
    assert [ws.cell(r, 4).value for r in range(11, 17)] == [f"T{i}" for i in range(6)]      # rows untouched, order unchanged


def test_last_group_and_overlapping_existing_merge():
    ws, rl = merge_ws(["L1", "L2", "L2", "L2"], existing=["B12:B13"])
    assert X.merge_consecutive_loops(ws, 2, 11, 14, rl) == 1
    ranges = [CellRange(str(m)) for m in ws.merged_cells.ranges]
    assert [str(m) for m in ws.merged_cells.ranges] == ["B12:B14"]
    for i, a in enumerate(ranges):
        for b in ranges[i + 1:]:
            assert a.isdisjoint(b)


def test_outline_alignment_and_neighbour_columns_unchanged():
    ws, rl = merge_ws(["L1", "L1", "L1"])
    X.merge_consecutive_loops(ws, 2, 11, 13, rl)
    c = ws["B11"]
    assert (c.alignment.horizontal, c.alignment.vertical) == ("center", "center") and not c.alignment.wrap_text
    assert ws["B11"].border.top.style == "thin" and ws["B13"].border.bottom.style == "thin"
    assert ws["B12"].border.top.style is None and ws["B12"].border.bottom.style is None      # no line inside the merged cell
    assert ws["D12"].border.top.style is None                                                  # the neighbour column is untouched


def test_only_the_from_column_of_mcc_di_and_do_changes(monkeypatch):
    rows = base_rows()
    _o1, before, rep1 = book(rows, merge=False, monkeypatch=monkeypatch)
    monkeypatch.undo()
    _o2, after, rep2 = book(rows)
    assert before.sheetnames == after.sheetnames
    for n in before.sheetnames:
        A, B = after[n], before[n]
        for r in range(1, max(A.max_row, B.max_row) + 1):
            for c in range(1, max(A.max_column, B.max_column) + 1):
                if n in (sheet_name(rep1, "MCC DI"), sheet_name(rep1, "MCC DO")) and c == 2 and r >= 11:
                    continue
                assert A.cell(r, c).value == B.cell(r, c).value, (n, A.cell(r, c).coordinate)
        ma = {str(m) for m in A.merged_cells.ranges}
        mb = {str(m) for m in B.merged_cells.ranges}
        if n in (sheet_name(rep1, "MCC DI"), sheet_name(rep1, "MCC DO")):
            assert all(m.startswith("B") for m in ma ^ mb)
        else:
            assert ma == mb, n
        assert [A.row_dimensions[r].height for r in range(1, 30)] == [B.row_dimensions[r].height for r in range(1, 30)]
        assert {k: d.width for k, d in A.column_dimensions.items()} == {k: d.width for k, d in B.column_dimensions.items()}
    for n in (sheet_name(rep1, "MCC DI"), sheet_name(rep1, "MCC DO")):          # headers (rows 1-10) identical
        assert [str(m) for m in after[n].merged_cells.ranges if m.max_row <= 10 and m.min_col != 2] == \
               [str(m) for m in before[n].merged_cells.ranges if m.max_row <= 10 and m.min_col != 2]


def test_no_overlapping_merges_in_any_generated_sheet():
    _o, wb, _rep = book(base_rows())
    for ws in wb:
        ranges = [CellRange(str(m)) for m in ws.merged_cells.ranges]
        cells = set()
        for m in ranges:
            for r in range(m.min_row, m.max_row + 1):
                for c in range(m.min_col, m.max_col + 1):
                    assert (r, c) not in cells, (ws.title, str(m))
                    cells.add((r, c))


def test_formulas_that_use_the_from_column_still_resolve():
    _o, wb, rep = book(base_rows())
    for lab in ("MCC DI", "MCC DO"):
        ws = wb[sheet_name(rep, lab)]
        last = int(str(ws.print_area).split("$")[-1])
        import re
        for r in range(11, last + 1):
            for c in range(1, 22):
                v = ws.cell(r, c).value
                if isinstance(v, str) and v.startswith("="):
                    assert not re.search(r"(?<![A-Z$!'])\$?B\$?\d+", v), (ws.title, ws.cell(r, c).coordinate, v)   # nothing reads From


def test_downstream_readers_give_the_same_result(monkeypatch):
    from utils import gland_quantity as gq, lug_quantity as lq
    rows = base_rows()
    o1, _w1, _ = book(rows, merge=False, monkeypatch=monkeypatch)
    monkeypatch.undo()
    o2, _w2, _ = book(rows)
    res = []
    for data in (o1, o2):
        out, _r = lq.analyze(data, {}, {}, None, None, None)
        occ, exc, *_ = gq.extract(data)
        res.append((out["kpis"]["cables"], out["kpis"]["total_lugs"], len(occ), sum(o.qty or 0 for o in occ), len(exc)))
    assert res[0] == res[1]


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_workbook_opens_and_converts():
    o, _wb, _rep = book(base_rows())
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "w.xlsx"
        src.write_bytes(o)
        r = subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(Path(d) / "o"), str(src)], capture_output=True, timeout=170)
        assert (Path(d) / "o" / "w.pdf").exists(), r.stderr
