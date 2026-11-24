"""Cable Schedule: junction boxes are ordered AJB first, then DJB (any other category after), each in ascending JB number
(natural: 01 < 02 < 09 < 10 < 100, prefix-aware), and every instrument stays with its own junction box and engineering data."""
import io
import sys
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_cable_schedule_layout import template  # noqa: E402

from utils.cable_schedule_layout import jb_groups, jb_sort_key, jb_unparsed, parse_jb_tag  # noqa: E402
from utils.template_processor import process_cable_schedule  # noqa: E402


def order(tags):
    return sorted(tags, key=jb_sort_key)


# ── the sorting key ──────────────────────────────────────────────────────────
def test_ajb_numeric_order():
    assert order(["AJB-01", "AJB-03", "AJB-05", "AJB-02"]) == ["AJB-01", "AJB-02", "AJB-03", "AJB-05"]


def test_ajb_before_djb_never_interspersed():
    assert order(["AJB-01", "DJB-01", "AJB-02", "DJB-02"]) == ["AJB-01", "AJB-02", "DJB-01", "DJB-02"]


def test_natural_not_alphabetical_with_leading_zeros_and_different_lengths():
    assert order(["AJB-01", "AJB-10", "AJB-02", "AJB-09"]) == ["AJB-01", "AJB-02", "AJB-09", "AJB-10"]
    assert order(["DJB-100", "DJB-11", "DJB-009", "DJB-1", "DJB-10"]) == ["DJB-1", "DJB-009", "DJB-10", "DJB-11", "DJB-100"]


def test_the_spec_example_with_ajb_and_djb():
    tags = ["AJB-01", "AJB-03", "AJB-05", "AJB-02", "DJB-02", "DJB-01", "AJB-10", "DJB-10", "DJB-04", "AJB-04"]
    assert order(tags) == ["AJB-01", "AJB-02", "AJB-03", "AJB-04", "AJB-05", "AJB-10", "DJB-01", "DJB-02", "DJB-04", "DJB-10"]


def test_naming_variations_keep_the_displayed_tag_and_group_by_category_not_prefix():
    tags = ["30-DJB-01", "20-AJB-02", "20-DJB-01", "30-AJB-01", "20-AJB-01", "AJB 11", "200-AJB-100", "200-AJB-009"]
    got = order(tags)
    assert got == ["AJB 11", "20-AJB-01", "20-AJB-02", "30-AJB-01", "200-AJB-009", "200-AJB-100", "20-DJB-01", "30-DJB-01"]
    assert sorted(got) == sorted(tags)                                                    # nothing renamed or lost
    cat = [parse_jb_tag(t)["category"] for t in got]
    assert cat == ["AJB"] * 6 + ["DJB"] * 2                                               # a prefix never splits the categories
    assert parse_jb_tag("200-DJB-101") == {"category": "DJB", "prefix": "200", "number": 101, "parsed": True}
    assert parse_jb_tag("AJB01")["number"] == 1 and parse_jb_tag("AJB 01")["number"] == 1


def test_other_categories_follow_and_unreadable_tags_are_last_and_reported():
    tags = ["SMB-01", "XYZ", "DJB-01", "AJB-A", "DIJB-2", "AJB-01", "DIJB-1"]
    assert order(tags) == ["AJB-01", "DJB-01", "DIJB-1", "DIJB-2", "SMB-01", "AJB-A", "XYZ"]
    assert jb_unparsed(tags) == ["XYZ", "AJB-A"] or sorted(jb_unparsed(tags)) == ["AJB-A", "XYZ"]
    assert parse_jb_tag("XYZ")["number"] is None                                          # never a guessed number


def test_project_style_tags_with_a_suffix_keep_their_natural_order():
    assert order(["JB-101-10", "JB-101-02", "JB-101-04"]) == ["JB-101-02", "JB-101-04", "JB-101-10"]


# ── the generated workbook ───────────────────────────────────────────────────
def rec(tag, jb, n, io_type="AI"):
    return {"TAG NO": tag, "JUNCTION BOX TAG NO.": jb, "EQUIPMENT DESCRIPTION": "D " + tag, "SIGNAL I/O TYPE": io_type,
            "INSTRUMENT TO JB CABLE TAG NO": f"IC-{n}", "INSTRUMENT TO JB CABLE TYPE": "1PX1.5 Sqmm", "BRANCH CABLE LENGTH": 10 + n,
            "MAIN CABLE TAG NUMBER": f"MC-{jb}", "MAIN CABLE TYPE": "12PX1.5 Sqmm", "MAIN CABLE LENGTH(MTRS)": 200, "REMARKS": None}


# the spec's unsorted IODB, extended: several instruments per JB, AJB / DJB mixed, JB-10 vs JB-2
UNSORTED = [rec("PT-101", "20-AJB-01", 1), rec("FT-103", "20-AJB-03", 2), rec("LT-105", "20-AJB-05", 3), rec("TT-102", "20-AJB-02", 4),
            rec("HS-202", "20-DJB-02", 5, "DI"), rec("LT-101", "20-AJB-01", 6), rec("YL-201", "20-DJB-01", 7, "DO"),
            rec("PT-110", "20-AJB-10", 8), rec("PT-109", "20-AJB-09", 9), rec("HS-210", "20-DJB-10", 10, "DI"), rec("PT-111", "20-AJB-01", 11),
            rec("HS-203", "20-DJB-02", 12, "DI")]


def generate(rows, jbs=None):
    b = io.BytesIO()
    pd.DataFrame(rows).to_excel(b, sheet_name="IODB", index=False)
    rep: dict = {}
    out, _, err = process_cable_schedule(io.BytesIO(b.getvalue()), io.BytesIO(template()), "JUNCTION BOX TAG NO.", "TAG NO",
                                         output_mode="WITH_SUMMARY", extra_report=rep, selected_jbs=jbs)
    assert err is None, err
    return openpyxl.load_workbook(io.BytesIO(out)), rep


def entries(wb):
    """[(tag, jb, branch cable, branch type, terminals, ferrule formulas...)] per instrument block, read from the INST sheet."""
    ws = next(w for w in wb.worksheets if "INST" in w.title.upper())
    h = {str(ws.cell(7, c).value).strip().upper(): c for c in range(1, ws.max_column + 1) if ws.cell(7, c).value}
    col = lambda *names: next(h[k] for k in h if any(k.startswith(n) for n in names))     # noqa: E731
    tag, jb, cab, term = col("TAG NUMBER"), col("JB TAG"), col("INSTRUMENT TO JB CABLE TAG"), col("TB DETAILS")
    ferrule = [c for k, c in h.items() if k.startswith("FERRULE AT INSTRUMENT")]
    out, cur = [], None
    for r in range(9, ws.max_row + 1):
        if ws.cell(r, tag).value:
            cur = {"tag": ws.cell(r, tag).value, "jb": ws.cell(r, jb).value, "cable": ws.cell(r, cab).value, "terms": [],
                   "ferrules": [], "row": r}
            out.append(cur)
        if cur is not None:
            if ws.cell(r, term).value not in (None, ""):
                cur["terms"].append(ws.cell(r, term).value)
            cur["ferrules"] += [ws.cell(r, c).value for c in ferrule if ws.cell(r, c).value]
    return ws, out


def test_generated_schedule_orders_ajb_then_djb_numerically_and_keeps_instruments_with_their_jb():
    wb, _ = generate(UNSORTED)
    _, got = entries(wb)
    jbs = [e["jb"] for e in got]
    assert list(dict.fromkeys(jbs)) == ["20-AJB-01", "20-AJB-02", "20-AJB-03", "20-AJB-05", "20-AJB-09", "20-AJB-10",
                                        "20-DJB-01", "20-DJB-02", "20-DJB-10"]
    # every JB's instruments are consecutive (a JB never reappears later), in their IODB order
    seen = []
    for j in jbs:
        if not seen or seen[-1] != j:
            assert j not in seen
            seen.append(j)
    assert [e["tag"] for e in got if e["jb"] == "20-AJB-01"] == ["PT-101", "LT-101", "PT-111"]
    assert [e["tag"] for e in got if e["jb"] == "20-DJB-02"] == ["HS-202", "HS-203"]
    assert sorted(e["tag"] for e in got) == sorted(r["TAG NO"] for r in UNSORTED)         # none lost, none duplicated
    assert len({e["tag"] for e in got}) == len(UNSORTED)
    jb_of = {r["TAG NO"]: r["JUNCTION BOX TAG NO."] for r in UNSORTED}
    assert all(jb_of[e["tag"]] == e["jb"] for e in got)                                   # no instrument moved to another JB


def test_cable_tb_and_ferrule_data_stay_with_each_tag():
    wb, _ = generate(UNSORTED)
    _, got = entries(wb)
    by = {e["tag"]: e for e in got}
    cables = {r["TAG NO"]: f"IC-{i}" for i, r in enumerate(UNSORTED, 0)}
    expected = {r["TAG NO"]: r["INSTRUMENT TO JB CABLE TAG NO"] for r in UNSORTED}
    assert {t: e["cable"] for t, e in by.items()} == expected
    assert all(e["terms"] and e["ferrules"] for e in got)
    # the same IODB already in sorted order gives an identical schedule: sorting moved whole blocks, nothing else
    pre = sorted(range(len(UNSORTED)), key=lambda i: (jb_sort_key(UNSORTED[i]["JUNCTION BOX TAG NO."]), i))
    wb2, _ = generate([UNSORTED[i] for i in pre])
    ws1, ws2 = entries(wb)[0], entries(wb2)[0]
    assert ws1.max_row == ws2.max_row
    assert [[c.value for c in row] for row in ws1.iter_rows(min_row=9)] == [[c.value for c in row] for row in ws2.iter_rows(min_row=9)]
    assert sorted(str(m) for m in ws1.merged_cells.ranges) == sorted(str(m) for m in ws2.merged_cells.ranges)


def test_selected_jbs_and_the_preview_use_the_same_order_and_other_sheets_are_unchanged():
    wb, rep = generate(UNSORTED, jbs=["20-DJB-01", "20-AJB-02", "20-AJB-01"])
    assert list(dict.fromkeys(e["jb"] for e in entries(wb)[1])) == ["20-AJB-01", "20-AJB-02", "20-DJB-01"]
    b = io.BytesIO()
    pd.DataFrame(UNSORTED).to_excel(b, index=False)
    df = pd.read_excel(io.BytesIO(b.getvalue()))
    assert [g["junction_box"] for g in jb_groups(df, "JUNCTION BOX TAG NO.", "TAG NO")] == [
        "20-AJB-01", "20-AJB-02", "20-AJB-03", "20-AJB-05", "20-AJB-09", "20-AJB-10", "20-DJB-01", "20-DJB-02", "20-DJB-10"]
    assert [g["tags"] for g in jb_groups(df, "JUNCTION BOX TAG NO.", "TAG NO")][0] == ["PT-101", "LT-101", "PT-111"]
    full, _ = generate(UNSORTED)
    assert full.sheetnames == wb.sheetnames


def test_unreadable_jb_tags_are_kept_after_the_sorted_boxes_and_reported():
    rows = [rec("A-1", "XYZ", 1), rec("A-2", "AJB-02", 2), rec("A-3", "AJB-01", 3)]
    wb, rep = generate(rows)
    assert list(dict.fromkeys(e["jb"] for e in entries(wb)[1])) == ["AJB-01", "AJB-02", "XYZ"]
    assert any("XYZ" in w and "could not be read" in w for w in (rep.get("warnings") or []))


def test_mixed_project_prefixes_do_not_intersperse_ajb_and_djb_in_the_workbook():
    """The case the old whole-string sort got wrong: 20-DJB-01 sorted before 30-AJB-01 because the prefix led."""
    rows = [rec("D-1", "20-DJB-01", 1, "DI"), rec("A-1", "30-AJB-01", 2), rec("A-2", "20-AJB-02", 3), rec("D-2", "30-DJB-01", 4, "DI"),
            rec("A-3", "20-AJB-01", 5)]
    wb, _ = generate(rows)
    got = list(dict.fromkeys(e["jb"] for e in entries(wb)[1]))
    assert got == ["20-AJB-01", "20-AJB-02", "30-AJB-01", "20-DJB-01", "30-DJB-01"]
    import re
    old = sorted({r["JUNCTION BOX TAG NO."] for r in rows}, key=lambda v: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", v)])
    assert old != got and old.index("20-DJB-01") < old.index("30-AJB-01")                 # the previous order interleaved them
