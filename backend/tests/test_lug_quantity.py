"""Cable Lug Quantity Generator: physical cables, termination arrangement, lugs per end."""
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import lug_quantity as L  # noqa: E402

HDR = ["SL. No.", "SIGNAL TAG", "CABLE TAG NO", "CABLE TYPE", "FROM", "TO", "CABLE LENGTH (M)", "IS/NIS"]


def book(rows, header=HDR, sheet="Power Cable Schedule", extra_sheets=()):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(["POWER CABLE SCHEDULE"] + [None] * (len(header) - 1))
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(header))
    ws.append(header)
    for r in rows:
        ws.append(r)
    for n in extra_sheets:
        wb.create_sheet(n)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def run(rows, rules=None, overrides=None, header=HDR):
    out, r = L.analyze(book(rows, header=header), rules, overrides)
    return out


def cab(out, tag):
    return next(c for c in out["cable_wise"] if c["cable_tag"] == tag)


# ── construction ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,kind,pairs,cores,cond,earth,size,esize", [
    ("1P x 1.5 Sq.mm", "PAIR", 1, 0, 2, 0, 1.5, None), ("2PX1.5 Sqmm", "PAIR", 2, 0, 4, 0, 1.5, None), ("12P x 1.5 Sq.mm", "PAIR", 12, 0, 24, 0, 1.5, None),
    ("4C x 16 Sq.mm", "CORE", 0, 4, 4, 0, 16.0, None), ("3C + E", "CORE", 0, 3, 4, 1, None, None),
    ("3C x 35 Sq.mm + E", "CORE", 0, 3, 4, 1, 35.0, None), ("3C x 70 Sq.mm + 35 Sq.mm E", "CORE", 0, 3, 4, 1, 70.0, 35.0),
    ("19C x 1.5", "CORE", 0, 19, 19, 0, 1.5, None), ("2T x 1.0", "TRIAD", 0, 0, 6, 0, 1.0, None)])
def test_construction_parsing(text, kind, pairs, cores, cond, earth, size, esize):
    c = L.parse_construction(text)
    assert (c["kind"], c["pairs"], c["cores"], c["conductors"], c["earth"], c["size"], c["earth_size"]) == (kind, pairs, cores, cond, earth, size, esize)


def test_a_pair_is_never_a_core_and_unknown_is_not_guessed():
    assert L.parse_construction("12P x 1.5")["cores"] == 0 and L.parse_construction("12P x 1.5")["conductors"] == 24
    u = L.parse_construction("RTD cable")
    assert u["kind"] == "UNKNOWN" and u["conductors"] == 0


# ── physical cables / duplicates ─────────────────────────────────────────────
def test_unique_cable_tag_is_one_physical_cable_and_types_are_counted_from_tags():
    rows = [[1, "PT-1", "MC-001", "12P x 1.5 Sq.mm", "JB-1", "PLC", 500, "NIS"], [2, "FT-1", "MC-001", "12P x 1.5 Sq.mm", "JB-1", "PLC", 500, "NIS"],
            [3, "LT-1", "MC-001", "12P x 1.5 Sq.mm", "JB-1", "PLC", 500, "NIS"], [4, "X", "MC-002", "12P x 1.5 Sq.mm", "JB-2", "PLC", 400, "NIS"],
            [5, "Y", "MC-003", "12P x 1.5 Sq.mm", "JB-3", "PLC", 300, "NIS"], [6, "Z", "MC-004", "19P x 1.5 Sq.mm", "JB-4", "PLC", 200, "NIS"]]
    out = run(rows)
    assert out["kpis"]["cables"] == 4
    qty = {t["cable_type"]: t["cable_qty"] for t in out["types"]}
    assert qty == {"12P x 1.5 Sq.mm": 3, "19P x 1.5 Sq.mm": 1}
    assert cab(out, "MC-001")["occurrences"] == 3 and cab(out, "MC-001")["length"] == "500"   # length shown, not used


def test_duplicates_can_be_counted_per_row_when_the_project_says_so():
    rows = [[1, "A", "MC-1", "4C x 16", "MCC", "M-1", 50, None], [2, "B", "MC-1", "4C x 16", "MCC", "M-1", 50, None]]
    assert run(rows, {"count_duplicates_once": False})["kpis"]["cables"] == 2


def test_same_tag_with_different_constructions_is_ambiguous_not_a_conflict_and_both_cables_are_counted():
    rows = [[1, "A", "MC-1", "4C x 16", "MCC", "M-1", 50, None], [2, "B", "MC-1", "4C x 35", "MCC", "M-1", 50, None]]
    out = run(rows)
    assert out["kpis"]["cables"] == 2 and out["kpis"]["errors"] == 0
    amb = [e for e in out["exceptions"] if e["kind"] == "Ambiguous cable tag"]
    assert len(amb) == 1 and amb[0]["severity"] == "REVIEW" and "MC-1" in amb[0]["ref"]
    assert not any(e["kind"] == "Conflicting cable data" for e in out["exceptions"])


def test_formatting_differences_normalise_but_construction_differences_do_not():
    keys = {L.normalize_type_key(t) for t in ("14Cx1.0 Sq.mm", "14C x 1.0 Sq.mm", "14C X 1.0 SQ.MM", "14C x1.0 Sq. mm")}
    assert len(keys) == 1
    assert L.parse_construction("14Cx1.0 Sq. mm")["normalized"] == "14C x 1.0 Sq.mm" and L.parse_construction("2Px0.5 Sq.mm")["normalized"] == "2P x 0.5 Sq.mm"
    assert L.normalize_type_key("5C x 1.0 Sq.mm") != L.normalize_type_key("14C x 1.0 Sq.mm")
    rows = [[1, "A", "X-1", "14Cx1.0 Sq. mm", "JB", "PLC", 1, None], [2, "B", "X-2", "14C x 1.0 Sq.mm", "JB", "PLC", 1, None]]
    out = run(rows)
    assert len(out["types"]) == 1 and out["types"][0]["cable_type"] == "14C x 1.0 Sq.mm" and out["types"][0]["cable_qty"] == 2 and out["types"][0]["core_count"] == 14


# ── header / label rows are not cable records ────────────────────────────────
def test_repeated_header_and_section_label_rows_are_ignored():
    h = ["SL. No.", "From", "Description", "Tag No", "Cable No", "Cable Size", "Signal Type"]
    rows = [[1, "MCC-1", "P-1 RUN", "T-1", "IC-1", "14Cx1.0 Sq. mm", "DI"],
            ["SL. No.", "From", "Description", "Tag No", "Cable No", "Cable Size", "Signal Type"],           # repeated header inside the data
            [None, None, None, None, None, "Cable Size", None],                                              # header remnant
            ["SECTION B", None, None, None, None, None, None],                                               # section label
            [2, "MCC-1", "P-2 RUN", "T-2", "IC-2", "5Cx1.0 Sq.mm", "DI"]]
    out = run(rows, header=h)
    assert out["kpis"]["cables"] == 2 and out["kpis"]["errors"] == 0 and out["kpis"]["unrecognized_types"] == 0
    assert not any(e["kind"] in ("Missing cable tag", "UNRECOGNIZED CABLE TYPE", "Core count cannot be identified") for e in out["exceptions"])
    assert any(e["kind"] == "Header rows ignored" for e in out["exceptions"])


def test_section_title_in_a_wide_merged_row_is_not_a_cable_type():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cable List"
    ws.append(["TAG", "CABLE TAG NO", "CABLE TYPE", "FROM", "TO"])
    ws.append(["T-1", "IC-1", "4C x 16 Sq.mm", "MCC", "M"])
    ws.append(["AJB-02 SECTION", None, None, None, None])
    ws.merge_cells("A3:E4")
    ws.append([None] * 5)
    ws.append(["T-2", "IC-2", "4C x 16 Sq.mm", "MCC", "M"])
    buf = io.BytesIO(); wb.save(buf)
    out, _ = L.analyze(buf.getvalue())
    assert out["kpis"]["cables"] == 2 and out["kpis"]["errors"] == 0


# ── physical cable identity: merged blocks, roles, repeated tag text ─────────
def block_book(rows, merges, header=("SL. No.", "Description", "Tag No", "Cable No", "Cable Size", "Signal Type"), sheet="VFD"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(["VFD"] + [None] * 5)
    ws.append(list(header))
    for r in rows:
        ws.append(r)
    for m in merges:
        ws.merge_cells(m)
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


def test_vfd_block_digital_and_analog_cables_under_one_tag_text_are_two_cables_not_a_conflict():
    rows = [[1, "K-1 FAULT", "T-A", "IC-VFD-1", "14Cx1.0 Sq. mm", "DI"], [None, "K-1 RUN", "T-B", None, None, "DI"], [None, "K-1 START", "T-C", None, None, "DO"],
            [None, "K-1 SPEED FB", "T-D", "IC-VFD-1", "2Px0.5 Sq. mm", "AI"], [None, "K-1 SPEED CMD", "T-E", None, None, "AO"]]
    out, _ = L.analyze(block_book(rows, ["D3:D5", "E3:E5", "D6:D7", "E6:E7"]))
    assert out["kpis"]["cables"] == 2 and out["kpis"]["errors"] == 0
    cw = {c["role"]: c for c in out["cable_wise"]}
    assert set(cw) == {"VFD - DIGITAL", "VFD - ANALOG"} and cw["VFD - DIGITAL"]["core_count"] == 14 and cw["VFD - ANALOG"]["core_count"] == 4
    assert not any(e["kind"] in ("Conflicting cable data", "Ambiguous cable tag") for e in out["exceptions"])
    assert any(e["kind"] == "Tag shared by different cable roles" and e["severity"] == "INFO" for e in out["exceptions"])


def test_the_same_tag_text_in_two_separate_cable_blocks_is_two_cables_flagged_for_review():
    rows = [[1, "K-1 FAULT", "T-A", "IC-VFD-1", "14Cx1.0 Sq. mm", "DI"], [None, "K-1 RUN", "T-B", None, None, "DI"],
            [1, "P-9 FAULT", "T-X", "IC-VFD-1", "14Cx1.0 Sq. mm", "DI"], [None, "P-9 RUN", "T-Y", None, None, "DI"]]
    out, _ = L.analyze(block_book(rows, ["D3:D4", "E3:E4", "D5:D6", "E5:E6"]))
    assert out["kpis"]["cables"] == 2
    amb = [e for e in out["exceptions"] if e["kind"] == "Ambiguous cable tag"]
    assert len(amb) == 1 and "2 separate cable blocks" in amb[0]["message"] and amb[0]["severity"] == "REVIEW"
    assert out["types"][0]["cable_qty"] == 2


def test_cell_inside_a_merged_tag_block_belongs_to_the_block_cable():
    # row 4 carries its own cable-size cell inside the merged tag block (as in the VFD sheet): same cable, not a new one
    rows = [[1, "K-1 FAULT", "T-A", "IC-VFD-1", "14Cx1.0 Sq. mm", "DI"], [None, "K-1 RUN", "T-B", None, "14Cx1.0 Sq. mm", "DI"]]
    out, _ = L.analyze(block_book(rows, ["D3:D4"]))
    assert out["kpis"]["cables"] == 1 and out["cable_wise"][0]["occurrences"] == 2 and not any(e["kind"] == "Missing cable tag" for e in out["exceptions"])


def test_mcc_di_blocks_without_a_cable_tag_column_derive_one_cable_per_merged_block():
    rows = [[1, "SIG 1", "T-1", "19Cx1.0 Sq. mm", "DI"], [None, "SIG 2", "T-2", None, "DI"], [None, "SIG 3", "T-3", None, "DI"],
            [2, "SIG 4", "T-4", "19Cx1.0 Sq. mm", "DI"], [None, "SIG 5", "T-5", None, "DI"]]
    out, _ = L.analyze(block_book(rows, ["D3:D5", "D6:D7", "A3:A5", "A6:A7"], header=("SL. No.", "Description", "Tag No", "Cable Size", "Signal Type"), sheet="MCC-DI"))
    assert out["kpis"]["cables"] == 2 and not any(e["kind"] == "Missing cable tag" for e in out["exceptions"])
    assert out["types"][0]["cable_qty"] == 2 and {c["cable_tag"] for c in out["cable_wise"]} == {"MCC-DI cable 1", "MCC-DI cable 2"}
    assert any(e["kind"] == "Cable identity derived from cable block" and e["severity"] == "INFO" for e in out["exceptions"])


def test_incomplete_tag_and_untraceable_rows_are_reported_not_silently_counted():
    h = ["SL", "Tag No", "Cable No", "Cable Size"]
    out = run([[1, "T-1", "IC-LCP-", "12Cx2.5 Sq. mm"], [2, "T-2", None, "6Px1.0 Sq. mm"]], header=h)
    kinds = [e["kind"] for e in out["exceptions"]]
    assert kinds.count("Missing cable tag") == 2 and all(e["severity"] == "REVIEW" for e in out["exceptions"] if e["kind"] == "Missing cable tag")


def test_unrecognized_cable_type_is_an_error_with_sheet_row_and_original_value():
    out = run([[1, "A", "MC-101", "XYZ-123", "JB", "PLC", 5, None], [2, "B", "MC-102", "4C x 16", "MCC", "M", 5, None]])
    e = next(x for x in out["exceptions"] if x["kind"] == "UNRECOGNIZED CABLE TYPE")
    assert e["severity"] == "ERROR" and e["sheet"] == "Power Cable Schedule" and e["row"] == 3 and e["original"] == "XYZ-123" and "MC-101" in e["message"]
    assert out["kpis"]["unrecognized_types"] == 1 and out["kpis"]["recognized_types"] == 1
    assert cab(out, "MC-101")["cores"] == "REVIEW REQUIRED" and cab(out, "MC-101")["total"] is None


def test_physical_cable_reconciliation_lists_every_source_row():
    rows = [[1, "PT-1", "MC-001", "12P x 1.5", "JB", "PLC", 1, None], [2, "FT-1", "MC-001", "12P x 1.5", "JB", "PLC", 1, None]]
    out = run(rows)
    assert [(r["sheet"], r["row"], r["pid"], r["status"]) for r in out["reconciliation"]] == [("Power Cable Schedule", 3, "MC-001", "Valid"), ("Power Cable Schedule", 4, "MC-001", "Valid")]


# ── core count vs lugged conductors ──────────────────────────────────────────
def test_14c_core_count_is_14_and_all_conductors_lugged_at_both_ends_is_28_per_cable():
    rows = [[i, f"S{i}", f"IC-{i}", "14Cx1.0 Sq. mm", "VFD", "PLC", 10, None] for i in range(1, 6)]
    out = run(rows, {"control_use_lugs": True, "ferrule_evidence": False})
    c = cab(out, "IC-1")
    assert (c["core_count"], c["lugged_from"], c["lugged_to"], c["lugs_per_cable"], c["total"]) == (14, 14, 14, 28, 28)
    assert out["kpis"]["total_lugs"] == 5 * 28
    t = out["types"][0]
    assert (t["cable_qty"], t["core_count"], t["lugged_from"], t["lugged_to"], t["per_cable"], t["total"]) == (5, 14, 14, 14, 28, 140)


def test_14c_with_12_lugged_conductors_keeps_core_count_14_and_gives_24():
    rows = [[1, "S", "IC-1", "14Cx1.0 Sq. mm", "VFD", "PLC", 10, None]]
    ov = {"tag:IC-1": {"lug_required": "YES", "lugged_from": 12, "lugged_to": 12, "remarks": "2 spare conductors not lugged"}}
    out = run(rows, {"control_use_lugs": True, "ferrule_evidence": False}, overrides=ov)
    c = cab(out, "IC-1")
    assert (c["core_count"], c["lugged_from"], c["lugged_to"], c["lugs_per_cable"], c["total"], c["source"]) == (14, 12, 12, 24, 24, "USER OVERRIDE")
    assert c["auto"]["lugs_per_cable"] == 28 and c["remarks"] == "2 spare conductors not lugged"             # the automatic value stays visible
    bad = run(rows, overrides={"tag:IC-1": {"lug_required": "YES", "lugged_from": 15, "lugged_to": 14}})
    assert cab(bad, "IC-1")["status"] == "ERROR" and any(e["kind"] == "Invalid lugged conductor count" for e in bad["exceptions"])


def test_ferrule_columns_can_be_ignored_by_a_project_rule():
    h = ["SL", "TAG", "CABLE TAG NO", "CABLE TYPE", "FERRULE AT PANEL SIDE"]
    rows = [[1, "A", "IC-1", "5C x 1.0 Sq.mm", "=D3&E3"]]
    assert run(rows, header=h)["kpis"]["total_lugs"] == 0
    assert run(rows, {"ferrule_evidence": False, "control_use_lugs": True}, header=h)["kpis"]["total_lugs"] == 10


# ── live preview ─────────────────────────────────────────────────────────────
def test_progress_callback_gives_a_growing_live_extraction_after_every_sheet():
    wb = openpyxl.load_workbook(io.BytesIO(book([[1, "A", "P-1", "4C x 16", "MCC", "M", 1, None]])))
    ws = wb.create_sheet("Second Schedule")
    ws.append(["SL", "TAG", "CABLE TAG NO", "CABLE TYPE"])
    ws.append([1, "B", "P-2", "XYZ-1"])
    ws.append([2, "C", "P-3", "5C x 1.0 Sq.mm"])
    buf = io.BytesIO(); wb.save(buf)
    snaps = []
    L.analyze(buf.getvalue(), progress=snaps.append)
    assert [s["sheets_done"] for s in snaps] == [1, 2] and snaps[0]["kpis"]["cables"] == 1 and snaps[1]["kpis"]["cables"] == 3
    assert snaps[1]["kpis"]["errors"] == 1 and any(e["kind"] == "UNRECOGNIZED CABLE TYPE" for e in snaps[1]["errors"])
    assert {"cable_tag", "cable_type", "normalized_type", "core_count", "lugged_from", "lugged_to", "lugs_per_cable", "status"} <= set(snaps[1]["rows"][0])


# ── gland recommendation (separate calculation, from the cable OD) ───────────
def test_gland_recommendation_needs_the_cable_od_and_never_invents_one():
    rows = [[1, "A", "IC-1", "14Cx1.0 Sq. mm", "JB", "PLC", 1, None]]
    out = run(rows)
    g = out["gland"][0]
    assert (g["metric"], g["npt"], g["status"]) == ("OD Required", "OD Required", "REVIEW - OD REQUIRED") and "Manufacturer Verification" in g["et"]
    assert g["od"] is None and "Enter cable OD" in g["advice"]


def test_gland_recommendation_from_od_uses_a_manufacturer_table_with_source():
    rows = [[1, "A", "IC-1", "14Cx1.0 Sq. mm", "JB", "PLC", 1, None]]
    key = L.normalize_type_key("14C x 1.0 Sq.mm")
    out, _ = L.analyze(book(rows), None, None, {key: {"od": "11.0"}})
    g = out["gland"][0]
    assert g["od"] == 11.0 and g["status"] == "ADVISORY"
    assert g["metric"].startswith("M") and "NPT" in g["npt"] and "ET" in g["et"] and "verify" in g["et"].lower()
    assert "CMP" in g["basis"] and "cable OD range" in g["basis"] and "retrieved" in g["source"]
    ov, _ = L.analyze(book(rows), None, None, {key: {"od": "11.0", "metric_gland": "M25"}})
    assert ov["gland"][0]["metric"] == "M25" and ov["gland"][0]["status"] == "USER OVERRIDE" and ov["gland"][0]["auto"]["metric"] == g["metric"]
    bad, _ = L.analyze(book(rows), None, None, {key: {"od": "abc"}})
    assert bad["gland"][0]["status"] == "REVIEW - INVALID OD"


def test_gland_lug_and_core_calculations_stay_independent():
    rows = [[1, "A", "IC-1", "14Cx1.0 Sq. mm", "JB", "PLC", 1, None]]
    key = L.normalize_type_key("14C x 1.0 Sq.mm")
    a, _ = L.analyze(book(rows), {"control_use_lugs": True, "ferrule_evidence": False}, None, {key: {"od": "11.0"}})
    b, _ = L.analyze(book(rows), {"control_use_lugs": True, "ferrule_evidence": False}, None, {key: {"od": "30.0"}})
    assert a["kpis"]["total_lugs"] == b["kpis"]["total_lugs"] == 28 and a["gland"][0]["metric"] != b["gland"][0]["metric"]


# ── the specification's calculation examples ────────────────────────────────
def test_example_power_cable_10_x_4_x_2_is_80():
    rows = [[i, f"M{i}", f"PC-{i:03d}", "4C x 16 Sq.mm", "MCC", f"M-{i}", 60, None] for i in range(1, 11)]
    out = run(rows)
    assert out["kpis"]["total_lugs"] == 80 and out["kpis"]["with_lugs"] == 10
    (t,) = out["types"]
    assert (t["cable_qty"], t["lug_from"], t["lug_to"], t["per_cable"], t["total"], t["lug_size"], t["lug_type"], t["material"]) == (10, 4, 4, 8, 80, "16 mm²", "NOT SPECIFIED", "NOT SPECIFIED")
    assert out["procurement"][0]["qty"] == 80 and out["by_size"] == [{"size": "16 mm²", "qty": 80}]


def test_example_instrument_multicore_is_zero_lugs_with_the_reason():
    rows = [[i, f"P{i}", f"MC-{i:03d}", "12P x 1.5 Sq.mm", "JB", "PLC", 100, "NIS"] for i in range(1, 21)]
    out = run(rows)
    assert out["kpis"]["total_lugs"] == 0 and out["kpis"]["without_lugs"] == 20 and out["procurement"] == []
    c = cab(out, "MC-001")
    assert c["lug_required"] == "NO" and "cable lug not applicable" in c["reason"] and c["termination"] == "Ferrule / Terminal Block"


def test_example_one_sided_lug_and_partial_lugging():
    rows = [[i, "A", f"PC-{i}", "4C x 16 Sq.mm", "MCC", "M", 10, None] for i in range(1, 6)]
    out = run(rows, {"lugged_ends": "from"})
    assert out["kpis"]["total_lugs"] == 5 * (4 + 0)                              # 5 x (4 + 0) = 20
    explicit = ["SL", "TAG", "CABLE TAG NO", "CABLE TYPE", "LUG QTY FROM", "LUG QTY TO"]
    rows = [[i, "A", f"PC-{i}", "3C + E", 4, 3] for i in range(1, 6)]
    out = run(rows, header=explicit)
    assert out["kpis"]["total_lugs"] == 35 and cab(out, "PC-1")["total"] == 7     # 5 x (4 + 3) = 35


def test_earth_conductor_is_counted_on_its_own_line_and_can_be_switched_off():
    rows = [[1, "A", "PC-1", "3C x 70 Sq.mm + 35 Sq.mm E", "MCC", "M", 30, None]]
    out = run(rows)
    c = cab(out, "PC-1")
    assert c["total"] == 8 and c["earth_lugs"] == 2 and c["earth_size"] == "35 mm²" and c["lug_size"] == "70 mm²"
    sizes = {p["conductor_size"]: p["qty"] for p in out["procurement"]}
    assert sizes == {"70 mm²": 6, "35 mm²": 2}
    assert run(rows, {"earth_lugged": False})["kpis"]["total_lugs"] == 6
    nosize = run([[1, "A", "PC-2", "3C x 70 Sq.mm + E", "MCC", "M", 30, None]])
    assert any(e["kind"] == "Earth conductor size not stated" for e in nosize["exceptions"])


# ── priorities ───────────────────────────────────────────────────────────────
def test_explicit_schedule_lug_data_beats_the_rule_table():
    h = ["SL", "TAG", "CABLE TAG NO", "CABLE TYPE", "LUG REQUIRED", "LUG TYPE", "LUG SIZE", "LUG MATERIAL", "LUG QTY FROM", "LUG QTY TO"]
    out = run([[1, "A", "PC-1", "4C x 16 Sq.mm", "YES", "Compression", "16 mm2", "Cu", 4, 4], [2, "B", "MC-1", "4C x 16 Sq.mm", "NO", None, None, None, None, None],
               [3, "C", "PC-3", "12P x 1.5", "YES", "Mechanical", "1.5", "Cu", 12, 12]], header=h)
    a, b, c = cab(out, "PC-1"), cab(out, "MC-1"), cab(out, "PC-3")
    assert (a["total"], a["lug_type"], a["material"], a["basis"]) == (8, "Compression", "Cu", "SCHEDULE")
    assert b["total"] == 0 and b["lug_required"] == "NO" and "not required" in b["reason"]
    assert c["total"] == 24                                                       # the schedule explicitly says lugs: used, not overridden by the instrument default


def test_conflicting_schedule_lug_data_is_an_error():
    h = ["SL", "TAG", "CABLE TAG NO", "CABLE TYPE", "LUG REQUIRED", "LUG QTY"]
    out = run([[1, "A", "PC-1", "4C x 16", "NO", 8]], header=h)
    assert cab(out, "PC-1")["status"] == "ERROR" and any(e["kind"] == "Conflicting lug requirement" for e in out["exceptions"])
    assert out["kpis"]["total_lugs"] == 0


def test_explicit_termination_text_and_ferrule_columns_are_used_before_the_rules():
    h = ["SL", "TAG", "CABLE TAG NO", "CABLE TYPE", "TERMINATION TYPE"]
    out = run([[1, "A", "PC-1", "4C x 16", "Terminal block"], [2, "B", "PC-2", "4C x 16", "Compression lug"]], header=h)
    assert cab(out, "PC-1")["total"] == 0 and cab(out, "PC-1")["basis"] == "TERMINATION"
    assert cab(out, "PC-2")["total"] == 8
    hf = ["SL", "TAG", "CABLE TAG NO", "CABLE TYPE", "FERRULE AT PANEL SIDE"]
    out = run([[1, "A", "PC-9", "4C x 16", "=D3&E3"]], header=hf)
    assert cab(out, "PC-9")["total"] == 0 and cab(out, "PC-9")["termination"] == "Ferrule / Terminal Block"


# ── review: nothing is invented ──────────────────────────────────────────────
def test_unknown_construction_and_unclassifiable_cables_are_review_with_no_quantity():
    rows = [[1, "A", "X-1", "RTD cable", "JB", "PLC", 10, None], [2, "B", "X-2", "4C x 3.0 Sq.mm", "MCC", "M", 10, None], [3, "C", "X-3", "3C", "MCC", "M", 10, None]]
    out = run(rows)
    assert [cab(out, t)["status"] for t in ("X-1", "X-2", "X-3")] == ["ERROR", "REVIEW", "REVIEW"]               # X-1 is not a recognised construction
    assert all(cab(out, t)["total"] is None and cab(out, t)["lug_required"] == "REVIEW" for t in ("X-1", "X-2", "X-3"))
    kinds = {e["kind"] for e in out["exceptions"]}
    assert {"UNRECOGNIZED CABLE TYPE", "Lug requirement unknown"} <= kinds
    assert out["kpis"]["review"] == 2 and out["kpis"]["errors"] == 1 and out["kpis"]["total_lugs"] == 0
    assert cab(out, "X-1")["cores"] == "REVIEW REQUIRED"


def test_runs_are_flagged_not_multiplied():
    out = run([[1, "A", "P-1", "3CX2.5mm2 IOS Armored Type (2 Runs)", "MCC", "M", 10, None]])
    assert out["kpis"]["cables"] == 1 and any(e["kind"] == "Cable runs stated" for e in out["exceptions"])


# ── rules, overrides, grouping ───────────────────────────────────────────────
def test_project_rules_are_configurable():
    rows = [[1, "A", "I-1", "2P x 1.5", "JB", "PLC", 10, None], [2, "B", "P-1", "4C x 16", "MCC", "M", 10, None]]
    out = run(rows, {"instrumentation_use_lugs": True, "power_use_lugs": False})
    assert cab(out, "I-1")["total"] == 8 and cab(out, "P-1")["total"] == 0                   # 4 conductors x 2 ends
    with pytest.raises(L.LugError):
        run(rows, {"lugged_ends": "middle"})
    with pytest.raises(L.LugError):
        run(rows, {"power_min_mm2": 1, "control_max_mm2": 5})


def test_user_override_resolves_a_review_cable_and_is_marked():
    rows = [[1, "A", "X-1", "4C x 3.0 Sq.mm", "JB", "PLC", 10, None], [2, "B", "P-1", "4C x 16", "MCC", "M", 10, None]]
    out = run(rows, overrides={"tag:X-1": {"lug_required": "YES", "lug_from": 4, "lug_to": 4, "lug_type": "Compression", "lug_size": "3 mm2", "lug_material": "Cu", "remarks": "per vendor"}})
    c = cab(out, "X-1")
    assert (c["status"], c["source"], c["total"], c["lug_type"], c["material"], c["remarks"]) == ("OK", "USER OVERRIDE", 8, "Compression", "Cu", "per vendor")
    assert cab(out, "P-1")["source"] == "AUTO"
    assert out["kpis"]["overrides"] == 1
    out = run(rows, overrides={"tag:P-1": {"lug_required": "NO"}})
    assert cab(out, "P-1")["total"] == 0 and cab(out, "P-1")["source"] == "USER OVERRIDE"
    out = run(rows, {"allow_override": False}, overrides={"tag:P-1": {"lug_required": "NO"}})
    assert cab(out, "P-1")["source"] == "AUTO"
    out = run(rows, overrides={"type:" + L.normalize_type_key("4C x 16"): {"lug_required": "REVIEW"}})
    assert cab(out, "P-1")["source"] == "REVIEW"


def test_same_cable_text_with_different_lug_characteristics_stays_separate():
    h = ["SL", "TAG", "CABLE TAG NO", "CABLE TYPE", "LUG REQUIRED", "LUG TYPE", "LUG MATERIAL", "LUG QTY FROM", "LUG QTY TO"]
    out = run([[1, "A", "P-1", "4C x 16 Sq.mm", "YES", "Compression", "Cu", 4, 4], [2, "B", "P-2", "4C x 16 Sq.mm", "YES", "Compression", "Al", 4, 4],
               [3, "C", "P-3", "4C x 16 Sq.mm", "YES", "Compression", "Cu", 4, 4]], header=h)
    assert len(out["types"]) == 2
    assert {(p["material"], p["qty"]) for p in out["procurement"]} == {("Cu", 16), ("Al", 8)}


def test_asymmetric_from_to_in_the_procurement_view():
    h = ["SL", "TAG", "CABLE TAG NO", "CABLE TYPE", "LUG REQUIRED", "LUG QTY FROM", "LUG QTY TO"]
    out = run([[1, "A", "P-1", "4C x 16", "YES", 4, 3]], header=h)
    p = out["procurement"][0]
    assert (p["from_qty"], p["to_qty"], p["qty"]) == (4, 3, 7)


def test_invalid_explicit_quantity_is_an_error():
    h = ["SL", "TAG", "CABLE TAG NO", "CABLE TYPE", "LUG REQUIRED", "LUG QTY FROM", "LUG QTY TO"]
    out = run([[1, "A", "P-1", "4C x 16", "YES", -2, 3]], header=h)
    assert cab(out, "P-1")["status"] == "ERROR" and any(e["kind"] == "Invalid lug quantity" for e in out["exceptions"])


def test_missing_cable_tag_is_reported_and_counts_one_cable_per_row():
    h = ["SL", "SIGNAL TAG", "CABLE TYPE"]
    out = run([[1, "A", "4C x 16"], [2, "B", "4C x 16"]], header=h)
    assert out["kpis"]["cables"] == 2 and any(e["kind"] == "Missing cable tag" for e in out["exceptions"])


# ── sheets / safety / workbook ───────────────────────────────────────────────
def test_sheets_are_found_by_headers_and_hidden_ones_are_not_default():
    wb = openpyxl.load_workbook(io.BytesIO(book([[1, "A", "P-1", "4C x 16", "MCC", "M", 1, None]], extra_sheets=("Cover",))))
    ws = wb.create_sheet("Old")
    ws.sheet_state = "hidden"
    ws.append(["SL", "TAG", "CABLE TAG NO", "CABLE TYPE"])
    ws.append([1, "A", "OLD-1", "4C x 16"])
    buf = io.BytesIO(); wb.save(buf)
    infos = L.detect_sheets(openpyxl.load_workbook(io.BytesIO(buf.getvalue())))
    assert [i["sheet"] for i in infos if i["used"]] == ["Power Cable Schedule", "Old"]
    assert L.default_sheets(infos) == ["Power Cable Schedule"]


def test_the_uploaded_file_is_never_modified_and_bad_files_give_clear_errors():
    data = book([[1, "A", "P-1", "4C x 16", "MCC", "M", 1, None]])
    before = bytes(data)
    L.analyze(data)
    assert data == before
    with pytest.raises(L.GlandError, match="could not be opened"):
        L.analyze(b"nope")
    wb = openpyxl.Workbook(); wb.active.append(["x", "y", "z"])
    buf = io.BytesIO(); wb.save(buf)
    with pytest.raises(L.LugError, match="No cable schedule sheet"):
        L.analyze(buf.getvalue())


def test_real_iez_schedule_layout_dedupes_main_cables_and_uses_ferrule_termination():
    from tests.test_gland_quantity import schedule, BASE
    out, _ = L.analyze(schedule(BASE))
    tags = [c["cable_tag"] for c in out["cable_wise"]]
    assert sorted(tags) == ["IC-1", "IC-2", "IC-3", "MC-1"]                       # MC-1 appears on two rows -> one cable
    assert out["kpis"]["total_lugs"] == 0 and {c["category"] for c in out["cable_wise"]} == {"INSTRUMENTATION"}


def test_report_workbook_and_traceability():
    rows = [[i, f"M{i}", f"PC-{i:03d}", "4C x 16 Sq.mm", "MCC", f"M-{i}", 60, None] for i in range(1, 4)] + [[9, "Z", "MC-9", "12P x 1.5", "JB", "PLC", 5, "NIS"]]
    out, rules = L.analyze(book(rows))
    wb = openpyxl.load_workbook(io.BytesIO(L.to_workbook(out, rules, "S.xlsx")))
    assert wb.sheetnames == ["LUG SUMMARY", "CABLE TYPE SUMMARY", "CABLE-WISE DETAIL", "GLAND RECOMMENDATION", "EXTRACTION LOG", "LUG PROCUREMENT", "REVIEW - EXCEPTIONS", "RULES - ASSUMPTIONS"]
    ws = wb["CABLE-WISE DETAIL"]
    hdr = [c.value for c in ws[3]]
    for h in ("CABLE TAG", "CABLE TYPE", "FROM", "TO", "LUGGED FROM", "LUGGED TO", "TOTAL LUGS", "SHEET", "ROW(S)", "CALCULATION BASIS", "SOURCE"):
        assert h in hdr
    first = {h: ws.cell(4, i + 1).value for i, h in enumerate(hdr)}
    assert first["CABLE TAG"] == "PC-001" and first["TOTAL LUGS"] == 8 and first["SHEET"] == "Power Cable Schedule" and first["ROW(S)"] == "3" and first["SOURCE"] == "AUTO"
    assert wb["LUG SUMMARY"]["B4"].value == 24
    text = " ".join(str(c.value) for row in wb["RULES - ASSUMPTIONS"].iter_rows() for c in row if c.value)
    assert "never used" in text and "Physical cable" in text and "Core count vs lugged conductors" in text


# ── API ──────────────────────────────────────────────────────────────────────
@pytest.fixture()
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import lug_quantity
    app = FastAPI()
    app.include_router(lug_quantity.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=41, username="alice")
    return TestClient(app)


def test_api_detect_analyze_override_download(client):
    f = ("S.xlsx", book([[1, "A", "X-1", "4C x 3.0 Sq.mm", "JB", "PLC", 5, None], [2, "B", "P-1", "4C x 16", "MCC", "M", 5, None]]))
    d = client.post("/api/cable-schedule/lug/detect", files={"file": f}).json()
    assert d["default_sheets"] == ["Power Cable Schedule"]
    a = client.post("/api/cable-schedule/lug/analyze", files={"file": f}).json()
    assert a["kpis"]["review"] == 1 and a["kpis"]["total_lugs"] == 8
    ov = '{"tag:X-1": {"lug_required": "NO"}}'
    b = client.post("/api/cable-schedule/lug/analyze", files={"file": f}, data={"overrides": ov, "rules": '{"lugged_ends": "both"}'}).json()
    st = client.post("/api/cable-schedule/lug/start", files={"file": f}, data={"od_data": "{}"})
    assert st.status_code == 202
    jid = st.json()["job_id"]
    for _ in range(40):
        j = client.get(f"/api/cable-schedule/lug/job/{jid}").json()
        if j["status"] != "processing":
            break
        import time as _t; _t.sleep(0.1)
    assert j["status"] == "done" and j["result"]["kpis"]["total_lugs"] == 8 and j["live"]["kpis"]["cables"] >= 1 and client.get("/api/cable-schedule/lug/job/nope").status_code == 404
    assert b["kpis"]["review"] == 0 and b["kpis"]["overrides"] == 1
    dl = client.get("/api/cable-schedule/lug/download")
    assert dl.status_code == 200 and openpyxl.load_workbook(io.BytesIO(dl.content)).sheetnames[0] == "LUG SUMMARY"


def test_api_errors_are_clear(client):
    assert ".xlsx" in client.post("/api/cable-schedule/lug/analyze", files={"file": ("a.txt", b"x")}).json()["detail"]
    r = client.post("/api/cable-schedule/lug/analyze", files={"file": ("a.xlsx", b"nope")})
    assert r.status_code == 400 and "could not be opened" in r.json()["detail"]
    r = client.post("/api/cable-schedule/lug/analyze", files={"file": ("a.xlsx", book([[1, "A", "P", "4C x 16", "M", "M", 1, None]]))}, data={"rules": "{bad"})
    assert r.status_code == 400 and "not valid JSON" in r.json()["detail"]
