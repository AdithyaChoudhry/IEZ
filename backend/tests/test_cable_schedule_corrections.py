"""Cable_Schedule-13 corrections: FERRULE AT PLC (+)/(-) removed from the Instrument Cable Schedule, Remarks exactly as in
the IODB (never a TBA placeholder), the IODB cable lengths written (not the template's sample formulas), one length per
physical main cable, and a Cable Summary that counts every physical cable once."""
import io
import sys
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cable_schedule_layout import template  # noqa: E402  (the reference INST layout incl. FERRULE AT PLC + Remarks)

from utils.template_processor import process_cable_schedule  # noqa: E402

B1, M12 = "1PX1.5 Sqmm", "12PX1.5 Sqmm"


def rec(tag, jb, btag, blen, mtag, mlen, remark=None, mtype=M12, btype=B1):
    return {"TAG NO": tag, "JUNCTION BOX TAG NO.": jb, "EQUIPMENT DESCRIPTION": "D " + tag, "SIGNAL I/O TYPE": "AI",
            "INSTRUMENT TO JB CABLE TAG NO": btag, "INSTRUMENT TO JB CABLE TYPE": btype, "BRANCH CABLE LENGTH": blen,
            "MAIN CABLE TAG NUMBER": mtag, "MAIN CABLE TYPE": mtype, "MAIN CABLE LENGTH(MTRS)": mlen, "REMARKS": remark}


# JB-001: the spec example - five instruments, one 300 m main cable (branch 25 + 30 + 20 + 35 + 40 = 150 m)
# JB-002: two DISTINCT main cables (MC-2A 250 m, MC-2B 120 m) - both must count
# JB-003: the same main cable MC-3 with two different lengths - a conflict: reported, not counted
ROWS = [rec("PT-001", "JB-001", "IC-1", 25, "MC-JB-001", 300, "NEWLY ADDED IN REV 3"),
        rec("PT-002", "JB-001", "IC-2", 30, "MC-JB-001", 300, None),
        rec("LT-003", "JB-001", "IC-3", 20, "MC-JB-001", 300, 42),
        rec("FT-004", "JB-001", "IC-4", 35, "MC-JB-001", 300, "TBA"),
        rec("TT-005", "JB-001", "IC-5", 40, "MC-JB-001", 300, "LINE 1\nLINE 2"),
        rec("PT-201", "JB-002", "IC-21", 10, "MC-2A", 250, "SPARE"),
        rec("PT-202", "JB-002", "IC-22", 12, "MC-2B", 120, None, mtype="24PX1.5 Sqmm"),
        rec("PT-301", "JB-003", "IC-31", 15, "MC-3", 200, None),
        rec("PT-302", "JB-003", "IC-32", 16, "MC-3", 210, None)]


def iodb(rows=ROWS, drop=()) -> bytes:
    b = io.BytesIO()
    pd.DataFrame(rows).drop(columns=list(drop)).to_excel(b, sheet_name="IODB", index=False)
    return b.getvalue()


def generate(data=None, jbs=None):
    rep: dict = {}
    out, _, err = process_cable_schedule(io.BytesIO(data or iodb()), io.BytesIO(template()), "JUNCTION BOX TAG NO.", "TAG NO",
                                         output_mode="WITH_SUMMARY", extra_report=rep, selected_jbs=jbs)
    assert err is None, err
    return openpyxl.load_workbook(io.BytesIO(out)), rep, out


@pytest.fixture(scope="module")
def result():
    return generate()


def heads(ws):
    return {str(ws.cell(7, c).value): c for c in range(1, ws.max_column + 1) if ws.cell(7, c).value}


def by_tag(ws):
    h = heads(ws)
    return {ws.cell(r, h["TAG NUMBER"]).value: r for r in range(9, ws.max_row + 1) if ws.cell(r, h["TAG NUMBER"]).value}


def summary(wb):
    ws = wb["CABLE SUMMARY"]
    out = {}
    for r in ws.iter_rows(values_only=True):
        if r[1] and r[2] == "METERS":
            out[r[1]] = r[3]
    return out


# ── A: columns ───────────────────────────────────────────────────────────────
def test_plc_ferrule_columns_are_removed_and_remarks_follows_panel_end_gland(result):
    ws = result[0]["Cable Schedule -INST"]
    names = list(heads(ws))
    assert "FERRULE AT PLC (+)" not in names and "FERRULE AT PLC (-)" not in names
    assert names[-2:] == ["PANEL END GLAND SIZE", "Remarks"] and len(names) == 20
    assert ws.max_column == 20 or all(ws.cell(7, c).value is None for c in range(21, ws.max_column + 1))
    # nothing in the sheet still refers to a removed column
    for row in ws.iter_rows(min_row=9):
        for c in row:
            assert not (isinstance(c.value, str) and "#REF" in c.value)


# ── B: remarks ───────────────────────────────────────────────────────────────
def test_remarks_are_the_iodb_values_and_never_a_placeholder(result):
    ws = result[0]["Cable Schedule -INST"]
    h, rows = heads(ws), by_tag(ws)
    got = {t: ws.cell(r, h["Remarks"]).value for t, r in rows.items()}
    assert got["PT-001"] == "NEWLY ADDED IN REV 3" and got["PT-201"] == "SPARE"
    assert got["LT-003"] == 42                                    # a number stays a number
    assert got["FT-004"] == "TBA"                                 # a real source TBA is kept
    assert got["TT-005"] == "LINE 1\nLINE 2"                      # multi-line kept
    assert got["PT-002"] is None and got["PT-202"] is None        # empty stays empty - no TBA inserted


def test_no_remarks_column_in_the_iodb_leaves_remarks_blank_with_a_warning():
    wb, rep, _ = generate(iodb(drop=("REMARKS",)))
    ws = wb["Cable Schedule -INST"]
    h = heads(ws)
    assert all(ws.cell(r, h["Remarks"]).value is None for r in by_tag(ws).values())
    assert any("no Remarks column" in w for w in rep.get("warnings") or [])


# ── C: lengths / main cable ──────────────────────────────────────────────────
def test_branch_lengths_are_the_iodb_values_not_the_template_sample(result):
    ws = result[0]["Cable Schedule -INST"]
    h, rows = heads(ws), by_tag(ws)
    want = {r["TAG NO"]: r["BRANCH CABLE LENGTH"] for r in ROWS}
    assert {t: ws.cell(r, h["BRANCH CABLE LENGTH"]).value for t, r in rows.items()} == want


def test_main_cable_length_is_shown_once_per_physical_main_cable(result):
    ws = result[0]["Cable Schedule -INST"]
    h, rows = heads(ws), by_tag(ws)
    ml = {t: ws.cell(r, h["MAIN CABLE LENGTH(Mtrs)"]).value for t, r in rows.items()}
    assert ml["PT-001"] == 300 and [ml[t] for t in ("PT-002", "LT-003", "FT-004", "TT-005")] == [None] * 4
    assert ml["PT-201"] == 250 and ml["PT-202"] == 120            # two distinct main cables of one JB: both shown
    # every row keeps its main cable tag (instrument -> JB -> main cable relationship preserved)
    assert all(ws.cell(r, h["MAIN CABLE TAG NUMBER"]).value for r in rows.values())


def test_conflicting_main_cable_keeps_each_value_and_is_reported(result):
    wb, rep, _ = result
    ws = wb["Cable Schedule -INST"]
    h, rows = heads(ws), by_tag(ws)
    assert ws.cell(rows["PT-301"], h["MAIN CABLE LENGTH(Mtrs)"]).value == 200
    assert ws.cell(rows["PT-302"], h["MAIN CABLE LENGTH(Mtrs)"]).value == 210
    assert any("Conflicting lengths" in w and "MC-3" in w for w in rep["warnings"])


# ── D: cable summary ─────────────────────────────────────────────────────────
def test_summary_counts_every_physical_cable_once(result):
    s = summary(result[0])
    # branch: 150 (JB-001) + 22 (JB-002) + 31 (JB-003) = 203; main 12P: 300 (MC-JB-001 once) + 250 (MC-2A);
    # MC-3 conflicts (200 vs 210) -> not counted; 24P: 120 (MC-2B)
    assert s == {B1: 203, M12: 550, "24PX1.5 Sqmm": 120}
    assert s[M12] != 300 * 5 + 250                                # the shared main cable is not multiplied


def test_spec_example_branch_150_plus_main_300_is_450():
    wb, _, _ = generate(iodb(ROWS[:5]))
    s = summary(wb)
    assert s == {B1: 150, M12: 300} and sum(s.values()) == 450


def test_repeated_branch_cable_tag_counts_once():
    rows = [rec("PT-1", "JB-1", "IC-1", 25, "MC-1", 100), rec("PT-1B", "JB-1", "IC-1", 25, "MC-1", 100)]
    s = summary(generate(iodb(rows))[0])
    assert s == {B1: 25, M12: 100}


def test_summary_equals_drum_demand_reconciliation():
    """Same physical-cable rule as the Drum Schedule (one length per cable tag)."""
    from utils import drum_schedule as ds
    from utils.file_handler import read_iodb
    rows = ROWS[:7]                                               # no conflict
    df, _ = read_iodb(io.BytesIO(iodb(rows)))
    demands, _, _ = ds.extract_demand(df)
    total = sum(summary(generate(iodb(rows))[0]).values())
    assert total == sum(d.length for d in demands) == 150 + 22 + 300 + 250 + 120


# ── E: downstream generators read the corrected schedule ─────────────────────
def test_gland_and_lug_engines_read_the_corrected_schedule(result):
    from utils import gland_quantity as gq
    from utils import lug_quantity as lq
    out = result[2]
    occ, exc, infos, types = gq.extract(out, gq.Settings())
    assert any(i.get("used") for i in infos)
    res, _ = lq.analyze(out, None, None, None, None)
    assert res["kpis"]["cables"] > 0
