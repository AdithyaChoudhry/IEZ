"""Drum Schedule Generator: IODB cable demand + Drum Master -> sequential drum allocation."""
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import drum_schedule as ds  # noqa: E402

IODB_COLS = ["TAG NO", "SIGNAL I/O TYPE", "INSTRUMENT TO JB CABLE TAG NO.", "INSTRUMENT TO JB CABLE TYPE", "BRANCH CABLE LENGTH",
             "JUNCTION BOX TAG NO.", "MAIN CABLE TAG NUMBER", "MAIN CABLE TYPE", "MAIN CABLE LENGTH(MTRS)", "IS/NIS TYPE"]
T1 = "1P x 1.5 Sq.mm"


def rec(tag, btag=None, btype=None, blen=None, mtag=None, mtype=None, mlen=None, nis="NIS", jb="JB-1"):
    d = dict.fromkeys(IODB_COLS)
    d.update({"TAG NO": tag, "SIGNAL I/O TYPE": "AI", "INSTRUMENT TO JB CABLE TAG NO.": btag, "INSTRUMENT TO JB CABLE TYPE": btype,
              "BRANCH CABLE LENGTH": blen, "JUNCTION BOX TAG NO.": jb, "MAIN CABLE TAG NUMBER": mtag, "MAIN CABLE TYPE": mtype,
              "MAIN CABLE LENGTH(MTRS)": mlen, "IS/NIS TYPE": nis})
    return d


def frame(rows):
    df = pd.DataFrame(rows, columns=IODB_COLS)
    df.index = df.index  # keep default numbering (Excel row = index + 2)
    return df


MASTER_HDR = ["DRUM MASTER ID", "CABLE TYPE", "CABLE SIZE / CONSTRUCTION", "IS / NIS", "UNIT", "STANDARD DRUM LENGTH (M)",
              "DRUM QUANTITY", "TOTAL CABLE LENGTH", "SPLIT ALLOWED", "NO-SPLICE DEFAULT", "VENDOR NAME", "DRUM TYPE / SIZE",
              "DRUM WEIGHT LIMIT", "QUANTITY TOLERANCE", "REMARKS"]


def master(rows, header=MASTER_HDR, sheet="Drum Master") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(["DRUM MASTER"])                      # a title row above the header must not matter
    ws.append(header)
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def lot(mid="DM-1", ctype=T1, nis="NIS", length=500, qty=2, split=None, vendor="Polycab"):
    return [mid, ctype, ctype, nis, "M", length, qty, None, split, None, vendor, "W-1", None, None, None]


def run(rows, lots, **kw):
    return ds.run(frame(rows), master(lots), **kw)


def sched(res):
    return [(r["drum_id"], r["cable_tag"], r["before"], r["allocated"], r["after"]) for r in ds.schedule_rows(res)]


# ── the examples of the specification ────────────────────────────────────────
def test_spec_example_four_cables_two_drums():
    res = run([rec(f"FT-{i}", f"IC-00{i}", T1, n) for i, n in ((1, 120), (2, 150), (3, 180), (4, 100))], [lot(length=500, qty=2)])
    assert sched(res) == [("DM-1-001", "IC-001", 500, 120, 380), ("DM-1-001", "IC-002", 380, 150, 230),
                          ("DM-1-001", "IC-003", 230, 180, 50), ("DM-1-002", "IC-004", 500, 100, 400)]
    (g,) = res.groups
    assert (g["required"], g["allocated"], g["shortage"], g["excess"]) == (550, 550, 0, 450)
    assert "EXCESS AVAILABLE" in g["message"] and "450" in g["message"]


def test_running_balance_500_380_280_200():
    res = run([rec(f"FT-{i}", f"IC-{i}", T1, n) for i, n in ((1, 120), (2, 100), (3, 80))], [lot(qty=1)])
    assert [r[2] for r in sched(res)] + [sched(res)[-1][4]] == [500, 380, 280, 200]
    assert {r[0] for r in sched(res)} == {"DM-1"}                      # one drum id on several rows


def test_shared_main_cable_is_one_physical_cable():
    rows = [rec(t, mtag="MC-001", mtype="12P x 1.5 Sq.mm", mlen=500) for t in ("FT-001", "PT-001", "LT-001")]
    demands, issues, stats = ds.extract_demand(frame(rows))
    assert [(d.tag, d.category, d.length) for d in demands] == [("MC-001", "MAIN", 500)]
    assert demands[0].rows == [2, 3, 4] and stats["main"] == 1
    assert any(i.kind == "Shared main cable" for i in issues)


def test_branch_and_main_are_both_scheduled_and_grouped_by_type_and_is_nis():
    rows = [rec("FT-1", "IC-1", T1, 75, "MC-1", "12P x 1.5 Sq.mm", 480), rec("FT-2", "IC-2", T1, 120, "MC-1", "12P x 1.5 Sq.mm", 480),
            rec("FT-3", "IC-3", T1, 80, nis="IS")]
    res = run(rows, [lot("A", T1, "NIS", 500, 1), lot("B", T1, "IS", 100, 1), lot("C", "12P x 1.5 Sq.mm", "NIS", 500, 1)])
    by = {(g["cable_type"], g["is_nis"]): g for g in res.groups}
    assert by[(T1, "NIS")]["required"] == 195 and by[(T1, "IS")]["required"] == 80 and by[("12P x 1.5 Sq.mm", "NIS")]["required"] == 480
    drums = {r["cable_tag"]: r["drum_id"] for r in ds.schedule_rows(res)}
    assert drums == {"IC-1": "A", "IC-2": "A", "IC-3": "B", "MC-1": "C"}      # IS never uses NIS drums


# ── splitting follows the Drum Master ────────────────────────────────────────
def test_split_allowed_continues_the_same_tag_on_the_next_drum():
    res = run([rec("A", "IC-1", T1, 120), rec("B", "IC-2", T1, 120)], [lot(length=200, qty=2, split="YES")])
    rows = ds.schedule_rows(res)
    assert [(r["drum_id"], r["cable_tag"], r["allocated"], r["after"]) for r in rows] == [
        ("DM-1-001", "IC-1", 120, 80), ("DM-1-001", "IC-2", 80, 0), ("DM-1-002", "IC-2", 40, 160)]
    assert rows[1]["remarks"].endswith("Split 1/2") and rows[2]["remarks"].endswith("Split 2/2")
    assert res.groups[0]["shortage"] == 0


def test_split_not_allowed_moves_the_whole_tag_to_the_next_drum():
    res = run([rec("A", "IC-1", T1, 120), rec("B", "IC-2", T1, 120)], [lot(length=200, qty=2, split="NO")])
    assert [(r[0], r[1], r[3]) for r in sched(res)] == [("DM-1-001", "IC-1", 120), ("DM-1-002", "IC-2", 120)]


def test_split_rule_can_be_switched_off_for_the_run():
    res = run([rec("A", "IC-1", T1, 120), rec("B", "IC-2", T1, 120)], [lot(length=200, qty=2, split="YES")], use_master_split=False)
    assert [r[0] for r in sched(res)] == ["DM-1-001", "DM-1-002"]


def test_tag_longer_than_any_drum_without_split_is_a_shortage_not_a_partial_allocation():
    res = run([rec("A", "IC-1", T1, 600)], [lot(length=500, qty=2, split="NO")])
    (r,) = ds.schedule_rows(res)
    assert r["status"] == "SHORTAGE" and r["allocated"] == 0 and r["unallocated"] == 600 and r["drum_id"] == ""
    assert res.groups[0]["shortage"] == 600 and all(d.allocated == 0 for d in res.drums)


# ── residual threshold ───────────────────────────────────────────────────────
def test_drum_is_closed_at_the_minimum_residual():
    rows = [rec("A", "IC-1", T1, 490), rec("B", "IC-2", T1, 5)]
    res = run(rows, [lot(length=500, qty=2)], min_residual=10)               # balance 10 -> closed
    assert [r[0] for r in sched(res)] == ["DM-1-001", "DM-1-002"]
    res = run(rows, [lot(length=500, qty=2)], min_residual=5)                # balance 10 > 5 -> still open
    assert [r[0] for r in sched(res)] == ["DM-1-001", "DM-1-001"]
    assert [r["status"] for r in ds.schedule_rows(res)] == ["AVAILABLE", "USED"]


def test_threshold_is_validated():
    with pytest.raises(ds.DrumError):
        run([rec("A", "IC-1", T1, 10)], [lot()], min_residual=16)
    with pytest.raises(ds.DrumError):
        run([rec("A", "IC-1", T1, 10)], [lot()], min_residual=-1)


# ── shortage / excess / not matched ──────────────────────────────────────────
def test_shortage_is_reported_with_totals():
    rows = [rec(f"T{i}", f"IC-{i}", "12P x 1.5 Sq.mm", 425) for i in range(1, 11)]          # 4,250 m
    res = run(rows, [lot(ctype="12P x 1.5 Sq.mm", length=500, qty=8, split="YES")])        # 4,000 m
    (g,) = res.groups
    assert (g["required"], g["available"], g["allocated"], g["shortage"], g["status"]) == (4250, 4000, 4000, 250, "SHORTAGE")
    assert "SHORTAGE: 12P x 1.5 Sq.mm - NIS - additional 250 m required." in g["message"]
    (s,) = ds.shortage_report(res)
    assert s["shortage"] == 250 and s["drums_consumed"] == 8
    assert sum(r["unallocated"] for r in ds.schedule_rows(res)) == 250


def test_unused_and_partial_drums_stay_visible():
    res = run([rec("A", "IC-1", T1, 100)], [lot(length=500, qty=3)])
    util = {u["drum_id"]: u for u in ds.utilization(res)}
    assert [util[k]["status"] for k in ("DM-1-001", "DM-1-002", "DM-1-003")] == ["PARTIALLY ALLOCATED", "AVAILABLE", "AVAILABLE"]
    ex = ds.excess_report(res)
    assert len(ex["unused_drums"]) == 2 and ex["partial_drums"][0]["remaining"] == 400 and ex["by_type"][0]["excess"] == 1400


def test_cable_type_not_in_master_is_not_substituted():
    res = run([rec("A", "IC-1", "19C x 1.5 Sq.mm", 100)], [lot()])
    (r,) = ds.schedule_rows(res)
    assert r["status"] == "NOT MATCHED" and res.groups[0]["status"] == "NOT MATCHED"
    assert any(e["kind"] == "Not matched" and "No matching drum available for cable type 19C x 1.5 Sq.mm" in e["message"] for e in ds.exceptions(res))


def test_is_nis_is_not_substituted():
    res = run([rec("A", "IC-1", T1, 100, nis="NIS")], [lot(nis="IS")])
    assert res.groups[0]["status"] == "NOT MATCHED"
    assert "only for: IS" in res.groups[0]["message"]


def test_type_spelling_noise_matches_but_different_constructions_do_not():
    assert ds.cable_key("1PX1.5 Sqmm") == ds.cable_key("1P x 1.5 Sq. mm") == ds.cable_key("1p×1.5 sq.mm")
    assert ds.cable_key("2P x 1.5 Sq.mm") != ds.cable_key("1P x 1.5 Sq.mm")
    res = run([rec("A", "IC-1", "1PX1.5 Sqmm", 100)], [lot()])
    assert res.groups[0]["status"] == "ALLOCATED"


# ── validation ───────────────────────────────────────────────────────────────
def test_iodb_validation_flags_and_excludes():
    rows = [rec("A", None, T1, 50),                          # no cable tag
            rec("B", "IC-B", None, 50),                      # no cable type
            rec("C", "IC-C", T1, None),                      # no length
            rec("D", "IC-D", T1, 0),                         # zero
            rec("E", "IC-E", T1, -5),                        # negative
            rec("F", "IC-F", T1, 40, nis="-"),               # no IS/NIS
            rec("G", "IC-G", T1, 30, nis="NIS")]
    demands, issues, _ = ds.extract_demand(frame(rows))
    assert [d.tag for d in demands] == ["IC-F", "IC-G"]
    kinds = {i.kind for i in issues}
    assert {"Missing cable tag", "Missing cable type", "Missing cable length", "Zero/negative cable length", "Missing IS/NIS"} <= kinds
    assert all(i.severity in ("ERROR", "WARNING", "INFO") for i in issues)


def test_conflicting_values_for_one_tag_use_the_first_and_warn():
    rows = [rec("A", mtag="MC-1", mtype="12P x 1.5 Sq.mm", mlen=500), rec("B", mtag="MC-1", mtype="12P x 1.5 Sq.mm", mlen=450)]
    demands, issues, _ = ds.extract_demand(frame(rows))
    assert demands[0].length == 500 and any(i.kind == "Conflicting values" for i in issues)


def test_drum_master_validation():
    bad = [lot("OK", length=500, qty=2),
           lot("ZERO", length=0), lot("NEG", length=-10), lot("NOLEN", length=None), lot("NOQTY", qty=None), lot("FRAC", qty=1.5),
           lot("BADNIS", nis="XYZ"), lot("BADSPLIT", split="MAYBE"), [None, None, None, "NIS", "M", 500, 1, None, None, None, None, None, None, None, None]]
    lots, issues, info = ds.read_drum_master(master(bad))
    assert [l.master_id for l in lots] == ["OK", "BADNIS", "BADSPLIT"]
    kinds = {i.kind for i in issues}
    assert {"Zero drum length", "Negative drum length", "Missing drum length", "Missing drum quantity", "Invalid drum quantity",
            "IS/NIS", "Invalid split rule", "Missing cable type"} <= kinds
    assert info["records"] == 3 and info["total_drums"] == 6


def test_master_lots_of_one_type_keep_their_own_lengths_and_quantities():
    lots, _, _ = ds.read_drum_master(master([lot("L1", length=1000, qty=4), lot("L2", length=500, qty=3)]))
    drums = ds.build_drums(lots)
    assert [(d.drum_id, d.usable) for d in drums] == [("L1-001", 1000), ("L1-002", 1000), ("L1-003", 1000), ("L1-004", 1000),
                                                      ("L2-001", 500), ("L2-002", 500), ("L2-003", 500)]
    res = run([rec("A", "IC-1", T1, 900), rec("B", "IC-2", T1, 900)], [lot("L1", length=1000, qty=1), lot("L2", length=500, qty=1)])
    rows = ds.schedule_rows(res)                    # 900 m fits the 1,000 m lot only; the 500 m lot is never merged into it
    assert [(r["drum_id"], r["status"]) for r in rows] == [("L1", "AVAILABLE"), ("", "SHORTAGE")]


def test_master_without_a_recognisable_header_is_rejected():
    wb = openpyxl.Workbook()
    wb.active.append(["a", "b"])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ds.DrumError):
        ds.read_drum_master(buf.getvalue())


def test_no_splice_default_no_means_splitting_is_allowed():
    row = lot(split=None)
    row[9] = "NO"
    lots, _, _ = ds.read_drum_master(master([row]))
    assert lots[0].split_allowed is True


# ── integrity ────────────────────────────────────────────────────────────────
def test_every_metre_is_accounted_for_and_the_result_is_deterministic():
    rows = [rec(f"T{i}", f"IC-{i}", T1, 37 + i * 11) for i in range(1, 30)] + [rec("M", mtag="MC-1", mtype=T1, mlen=410)]
    lots = [lot("A", length=500, qty=3, split="YES"), lot("B", length=300, qty=2, split="NO")]
    r1, r2 = run(rows, lots), run(rows, lots)
    assert sched(r1) == sched(r2)
    g = r1.groups[0]
    assert abs(g["required"] - g["allocated"] - g["shortage"]) < 1e-9
    for d in r1.drums:
        assert abs(d.usable - d.allocated - d.balance) < 1e-9 and d.balance >= 0
    for drum_id in {r[0] for r in sched(r1) if r[0]}:                               # balance chain per drum
        chain = [r for r in sched(r1) if r[0] == drum_id]
        assert chain[0][2] == next(d.usable for d in r1.drums if d.drum_id == drum_id)
        assert all(a[4] == b[2] for a, b in zip(chain, chain[1:])) and all(c[2] - c[3] == c[4] for c in chain)


def test_the_iodb_frame_is_not_modified():
    df = frame([rec("A", "IC-1", T1, 100)])
    before = df.copy(deep=True)
    ds.extract_demand(df)
    pd.testing.assert_frame_equal(df, before)


# ── workbook: the layout of the reference DRUM SCHEDULE / DRUM MASTER sheets ──
REF_SCHEDULE_HEADERS = ["DRUM ID", "CABLE TYPE", "CABLE DESCRIPTION", "CABLE TAG NUMBER", "IS / NIS", "MANUFACTURER", "DRUM LENGTH (M)",
                        "USABLE DRUM LENGTH (M)", "ALLOCATED LENGTH (M)", "AVAILABLE LENGTH (M)", "STATUS", "REMARKS"]


def example_result():
    return run([rec(f"FT-{i}", f"IC-00{i}", T1, n, jb="200-AJB-003") for i, n in ((1, 120), (2, 150), (3, 180), (4, 100))],
               [lot(length=500, qty=2, vendor="Polycab")])


def test_drum_schedule_sheet_has_the_reference_columns_formulas_and_style():
    wb = openpyxl.load_workbook(io.BytesIO(ds.to_workbook(example_result())))
    assert wb.sheetnames == ["DRUM SCHEDULE", "DRUM SCHEDULE - TRACE", "CABLE TYPE SUMMARY", "DRUM UTILIZATION", "SHORTAGE REPORT",
                             "EXCESS - BALANCE REPORT", "VALIDATION - EXCEPTIONS", "DRUM MASTER"]
    ws = wb["DRUM SCHEDULE"]
    assert ws["A1"].value == "DRUM SCHEDULE" and "A1:L1" in {str(m) for m in ws.merged_cells.ranges}
    assert [ws.cell(3, c).value for c in range(1, 13)] == REF_SCHEDULE_HEADERS and ws.freeze_panes == "A4"
    rows = [[ws.cell(r, c).value for c in range(1, 13)] for r in range(4, 8)]
    assert [r[0] for r in rows] == ["DM-1-001"] * 3 + ["DM-1-002"]
    assert [r[3] for r in rows] == ["IC-001", "IC-002", "IC-003", "IC-004"]
    assert rows[0][1:3] == ["1P x 1.5 Sq.mm", "FIELD TO 200-AJB-003"]
    assert rows[0][4:8] == ["NIS", "Polycab", 500, 500]
    # reference formulas: first row of a drum = usable length, then = previous AVAILABLE; AVAILABLE = MAX(0, H - I)
    assert [r[7] for r in rows] == [500, "=J4", "=J5", 500]
    assert [ws.cell(r, 10).value for r in range(4, 8)] == ["=MAX(0,H4-I4)", "=MAX(0,H5-I5)", "=MAX(0,H6-I6)", "=MAX(0,H7-I7)"]
    assert [r[8] for r in rows] == [120, 150, 180, 100] and [r[10] for r in rows] == ["AVAILABLE", "AVAILABLE", "AVAILABLE", "AVAILABLE"]
    assert "IODB row 2" in rows[0][11] and "DM-1 (Drum Master row 3)" in rows[0][11]
    c = ws["A4"]
    assert (c.font.name, c.font.sz, c.alignment.vertical, c.alignment.wrap_text) == ("Carlito", 10, "center", True)
    assert ws["A3"].fill.fgColor.rgb.endswith("163A5F") and ws["J4"].number_format == "0.0"
    dvs = {str(d.sqref): d.formula1 for d in ws.data_validations.dataValidation}
    assert '"IS,NIS,BOTH,NA"' in dvs.values() and any("AVAILABLE" in v and "EMPTY" in v for v in dvs.values())
    assert any("J4:J302" in str(r.sqref) for r in ws.conditional_formatting)


def test_formula_balance_chain_equals_the_engine_balances():
    res = example_result()
    ws = openpyxl.load_workbook(io.BytesIO(ds.to_workbook(res)))["DRUM SCHEDULE"]
    bal = {}
    for r in range(4, 8):
        h = ws.cell(r, 8).value
        h = bal[r - 1] if isinstance(h, str) else h
        bal[r] = max(0, h - ws.cell(r, 9).value)
    assert [bal[r] for r in range(4, 8)] == [x["after"] for x in ds.schedule_rows(res)] == [380, 230, 50, 400]


def test_shortage_rows_are_visible_in_the_drum_schedule_sheet():
    res = run([rec("A", "IC-1", T1, 600), rec("B", "IC-2", "19C x 1.5 Sq.mm", 50)], [lot(length=500, qty=1, split="NO")])
    ws = openpyxl.load_workbook(io.BytesIO(ds.to_workbook(res)))["DRUM SCHEDULE"]
    assert [(ws.cell(r, 1).value, ws.cell(r, 4).value, ws.cell(r, 9).value, ws.cell(r, 11).value, ws.cell(r, 10).value) for r in (4, 5)] == [
        ("NO DRUM", "IC-1", 0, "SHORTAGE", None), ("NO DRUM", "IC-2", 0, "NOT MATCHED", None)]
    assert "SHORTAGE 600 m" in ws["L4"].value


def test_drum_master_sheet_keeps_the_input_columns_and_traceability_sheet_exists():
    wb = openpyxl.load_workbook(io.BytesIO(ds.to_workbook(example_result())))
    wm = wb["DRUM MASTER"]
    assert [wm.cell(3, c).value for c in range(1, 4)] == ["DRUM MASTER ID", "CABLE TYPE", "CABLE SIZE / CONSTRUCTION"]
    assert [wm.cell(4, c).value for c in (1, 6, 7, 8, 9, 11)] == ["DM-1", 500, 2, 1000, "NO", "Polycab"]
    tr = wb["DRUM SCHEDULE - TRACE"]
    hdr = [c.value for c in tr[3]]
    for h in ("DRUM MASTER ID", "DRUM MASTER ROW", "CABLE CATEGORY", "AVAILABLE BEFORE ALLOCATION (M)", "SOURCE IODB REFERENCE"):
        assert h in hdr
    assert [tr.cell(r, 10).value for r in range(4, 8)] == [500, 380, 230, 500]


# ── the real input workbook layout ───────────────────────────────────────────
INPUT_HEADERS = ["DRUM MASTER ID", "CABLE TYPE", "CABLE SIZE / CONSTRUCTION", "IS / NIS", "UNIT", "STANDARD DRUM LENGTH (M)", "DRUM QUANTITY",
                 "TOTAL CABLE LENGTH ", "SPLIT ALLOWED", "NO-SPLICE DEFAULT", "VENDOR NAME", "DRUM TYPE / SIZE", "DRUM WEIGHT LIMIT (KG)",
                 "QUANITY TOLERANCE", "REMARKS"]


def test_input_workbook_layout_is_read_and_matched_to_iodb_spelling():
    rows = [["DM-001", "1P X 1.5 SQ.MM", "1 Pair x 1.5 sq.mm", "NIS", "M", 1000, 21, None, "NO", "YES", "Vendor A", "STD", None, None, "Example - replace"],
            ["DM-002", "12P X 1.5 SQ.MM", "12 Pair x 1.5 sq.mm", "NIS", "M", 500, 2, None, "NO", "YES", "Vendor A", "STD", 150, 5, "Example."],
            ["DM-003", "14C X 1.0 SQ.MM", "14 Core x 1.0 sq.mm", "NIS", "M", 500, 3, None, "NO", "YES", "Vendor A", "STD", None, None, None]]
    lots, issues, info = ds.read_drum_master(master(rows, header=INPUT_HEADERS))
    assert info["records"] == 3 and info["total_drums"] == 26 and info["header_row"] == 2
    assert all(not l.split_allowed for l in lots) and lots[1].weight_limit == "150" and lots[1].tolerance == "5"
    assert any(i.kind == "Example record" for i in issues)
    demands, d_issues, _ = ds.extract_demand(frame([rec("A", "IC-1", "1PX1.5 Sqmm", 75), rec("B", "IC-2", "12PX1.5 Sqmm", 100),
                                                    rec("C", "IC-3", "14Cx1.0 Sq. mm", 60)]))
    res = ds.build_schedule(demands, lots, d_issues + issues, 10)
    assert [r["drum_id"] for r in ds.schedule_rows(res)] == ["DM-001-001", "DM-002-001", "DM-003-001"]
    assert [r["cable_type"] for r in ds.schedule_rows(res)] == ["1P X 1.5 SQ.MM", "12P X 1.5 SQ.MM", "14C X 1.0 SQ.MM"]


REAL_INPUT = ROOT / "IO_Assignment_Standard" / "iEZ_Cable_Drum_Schedule_Input-2.xlsx"


@pytest.mark.skipif(not REAL_INPUT.exists(), reason="sample input workbook missing")
def test_the_supplied_input_workbook_is_accepted_as_is():
    lots, issues, info = ds.read_drum_master(REAL_INPUT.read_bytes())
    assert info["sheet"] == "DRUM MASTER" and info["records"] >= 3 and info["header_row"] == 3


# ── API ──────────────────────────────────────────────────────────────────────
@pytest.fixture()
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import drum_schedule
    app = FastAPI()
    app.include_router(drum_schedule.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=21, username="alice")
    return TestClient(app)


def iodb_bytes(rows):
    buf = io.BytesIO()
    frame(rows).to_excel(buf, sheet_name="IODB", index=False)
    return buf.getvalue()


def test_api_demand_master_generate_download(client):
    rows = [rec(f"FT-{i}", f"IC-00{i}", T1, n, "MC-1", "12P x 1.5 Sq.mm", 480) for i, n in ((1, 120), (2, 150), (3, 180), (4, 100))]
    iodb = ("IODB.xlsx", iodb_bytes(rows))
    m = ("Drum Master.xlsx", master([lot("A", T1, "NIS", 500, 2), lot("B", "12P x 1.5 Sq.mm", "NIS", 500, 1)]))
    d = client.post("/api/cable-schedule/drum/demand", files={"iodb_file": iodb}).json()
    assert d["stats"]["demand"] == 5 and d["stats"]["main"] == 1 and d["stats"]["branch"] == 4 and d["stats"]["total_length"] == 1030
    mm = client.post("/api/cable-schedule/drum/master", files={"drum_master_file": m}).json()
    assert mm["info"]["records"] == 2 and mm["info"]["total_drums"] == 3 and mm["info"]["cable_types"] == 2
    g = client.post("/api/cable-schedule/drum/generate", files={"iodb_file": iodb, "drum_master_file": m}, data={"min_residual": "10"})
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["totals"]["required"] == 1030 and body["totals"]["shortage"] == 0 and body["totals"]["rows"] == 5
    assert [p["status"] for p in body["progress"]] == ["Completed", "Completed"]
    assert body["schedule"][0]["drum_id"] == "A-001" and body["summary"][0]["excess"] == 450
    dl = client.get("/api/cable-schedule/drum/download")
    assert dl.status_code == 200 and openpyxl.load_workbook(io.BytesIO(dl.content)).sheetnames[0] == "DRUM SCHEDULE"


def test_api_errors_are_clear(client):
    iodb = ("IODB.xlsx", iodb_bytes([rec("A", "IC-1", T1, 10)]))
    r = client.post("/api/cable-schedule/drum/generate", files={"iodb_file": iodb, "drum_master_file": ("m.xlsx", master([lot()]))},
                    data={"min_residual": "20"})
    assert r.status_code == 400 and "between 0 and 15" in r.json()["detail"]
    r = client.post("/api/cable-schedule/drum/master", files={"drum_master_file": ("m.txt", b"x")})
    assert r.status_code == 400 and ".xlsx" in r.json()["detail"]
    r = client.post("/api/cable-schedule/drum/master", files={"drum_master_file": ("m.xlsx", b"not a zip")})
    assert r.status_code == 400 and "could not be opened" in r.json()["detail"]
    r = client.get("/api/cable-schedule/drum/download")
    assert r.status_code in (200, 404)
