"""
Smart Datasheet Generator - only eligible physical instruments are identified, counted, selectable and generated
(utils/datasheet_eligibility.py). All IODBs here are synthetic fixtures.
"""
import hashlib
import io
import json
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_datasheet_library import HEADER, api, approval, form, run  # noqa: E402,F401
from utils import datasheet_eligibility as DE  # noqa: E402
from utils import datasheet_library as DL  # noqa: E402
from utils.sop_datasheet import _load_iodb_df, get_iodb_instrument_types, get_iodb_tags  # noqa: E402

COLS = ["TAG NO", "INSTRUMENT TYPE", "SIGNAL I/O TYPE", "SERVICE", "STATUS"]
NCR = "LEVEL INDICATING TRANSMITTER - NCR TYPE"


def iodb(rows, cols=COLS) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IODB"
    ws.append(cols)
    for r in rows:
        ws.append(list(r) + [None] * (len(cols) - len(r)))
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def frame(rows, cols=COLS):
    return _load_iodb_df(iodb(rows, cols))[0]


def groups(data: bytes) -> dict:
    return {g["instrument_type"]: g for g in DL.analyze_iodb(data)["groups"]}


LEVEL = [("LIT-101", NCR, "AI", "TANK 1"), ("LI-101", NCR, "SOFT", "TANK 1"), ("LAH-101", NCR, "soft", "TANK 1"),
         ("LAL-101", NCR, "Soft", "TANK 1"), ("LAHH-101", NCR, "  SOFT  ", "TANK 1"), ("LALL-101", NCR, "SOFT", "TANK 1"),
         ("LIT-102", NCR, " ai ", "TANK 2")]


@pytest.mark.parametrize("raw,expected", [("ai", "AI"), ("AI ", "AI"), (" di", "DI"), ("Do", "DO"), ("ao", "AO"), ("Soft", "SOFT"),
                                          ("  SOFT  ", "SOFT"), ("SOFT IO", "SOFT"), ("-", "-"), (" - ", "-"), ("--", "-"), (None, ""),
                                          (float("nan"), ""), ("", ""), ("None", ""), ("null", ""), ("MODBUS TCP/IP AI", "MODBUS TCP/IP AI"),
                                          ("Deleted in Rev 0", "DELETED IN REV 0")])
def test_io_type_normalisation(raw, expected):
    assert DE.normalize_io(raw) == expected


# ───────── the level transmitter example ─────────
def test_seven_records_are_two_physical_transmitters():
    data = iodb(LEVEL)
    res = DL.analyze_iodb(data)
    g = res["groups"][0]
    assert (g["tag_count"], g["tags"]) == (2, ["LIT-101", "LIT-102"])
    assert g["diagnostics"] == {"records": 7, "soft_excluded": 5, "not_applicable_excluded": 0, "no_tag_excluded": 0,
                                "not_applicable_by_io": {}, "duplicates_excluded": 0, "eligible": 2}
    assert res["summary"]["soft_excluded"] == 5 and res["summary"]["eligible"] == 2
    assert get_iodb_tags(data, NCR) == (["LIT-101", "LIT-102"], None)                 # the older tag endpoint obeys the same rule


def test_selection_is_checked_tag_by_tag_with_a_reason():
    df = frame(LEVEL + [("PIT-1", "PRESSURE TRANSMITTER", "AI")])
    assert DE.check_selection(df, ["LIT-101", "lit-102"], NCR) == []
    bad = {p["tag"]: p["reason"] for p in DE.check_selection(df, ["LAH-101", "PIT-1", "GHOST-1"], NCR)}
    assert bad["LAH-101"].startswith("SOFT signal") and "not of the instrument type" in bad["PIT-1"] and "not in the IODB" in bad["GHOST-1"]


def test_the_iodb_and_the_shared_reader_keep_every_soft_record():
    data = iodb(LEVEL)
    before = hashlib.sha256(data).hexdigest()
    df = _load_iodb_df(data)[0]
    snapshot = df.copy(deep=True)
    DL.analyze_iodb(data)
    assert len(DE.eligible_frame(df, NCR)) == 2
    assert df.equals(snapshot) and len(df) == 7 and hashlib.sha256(data).hexdigest() == before
    from utils.file_handler import read_iodb                                              # what the I/O List reads
    from utils.generators import generate_io_list
    full = read_iodb(io.BytesIO(data))[0]
    out = generate_io_list(full, ["TAG NO", "SIGNAL I/O TYPE"], output_mode="WITHOUT_SUMMARY")[0]
    assert openpyxl.load_workbook(io.BytesIO(out)).worksheets[0].max_row == 8


# ───────── categories ─────────
@pytest.mark.parametrize("itype,tag,io_type,ok", [
    ("PRESSURE GAUGE", "PG-101", "-", True), ("TEMPERATURE GAUGE", "TG-101", None, True), ("LEVEL GAUGE", "LG-101", "-", True),
    ("LOCAL PRESSURE INDICATOR", "PI-101", None, True), ("LOCAL TEMPERATURE INDICATOR", "TI-101", "-", True),
    ("PRESSURE INDICATOR", "PI-102", "SOFT", False), ("LEVEL INDICATOR", "LI-102", "SOFT", False),
    ("PRESSURE TRANSMITTER", "PT-1", None, False), ("PRESSURE TRANSMITTER", "PT-2", "-", False),
    ("FLOW INDICATING TRANSMITTER", "FIT-1", "", False), ("PRESSURE GAUGE", "PG-102", "AI", False),
    ("LOOP POWERED INDICATOR", "LPI-1", "AI", True),                                 # a hardwired physical indicator
    ("PRESSURE TRANSMITTER", "PT-3", "AI", True), ("PRESSURE TRANSMITTER", "PT-4", "DI", True), ("PRESSURE TRANSMITTER", "PT-5", "DO", True),
    ("PRESSURE TRANSMITTER", "PT-6", "AO", False), ("PRESSURE TRANSMITTER", "PT-7", "MODBUS TCP/IP AI", False),
    ("PRESSURE TRANSMITTER", "PT-8", "TBA", False), ("LEVEL SWITCH", "LAH-201", "DI", True), ("PRESSURE SWITCH", "PSH-301", "DI", True),
    ("PRESSURE SWITCH", "PSH-302", "-", False), ("LEVEL ALARM", "LAH-202", "SOFT", False), ("PRESSURE HIGH ALARM", "PAH-301", "SOFT", False),
    ("PRESSURE HIGH ALARM", "PAH-302", "DI", False),                                  # an alarm point, not a device
    ("ORIFICE PLATE", "FE-1", "-", True), ("TEMPERATURE ELEMENT", "TE-1", "AI", True),
    ("CONTROL VALVE", "FCV-1", "AO", True), ("CONTROL VALVE", "FCV-2", "SOFT", False), ("VALVE OPEN STATUS", "ZSO-1", "DI", False),
    ("CONTROL VALVE POSTIONER XMTR", "PZI-1", "AI", True), ("MOTOR RUNNING STATUS", "M-1", "DI", False), ("PUMP", "P-1", "DI", False),
])
def test_eligibility_by_category(itype, tag, io_type, ok):
    df = frame([(tag, itype, io_type)])
    assert (DE.check_selection(df, [tag], itype) == []) is ok
    assert len(DE.eligible_frame(df, itype)) == (1 if ok else 0)


def test_a_physical_switch_stays_while_its_software_alarm_goes():
    data = iodb([("LAH-201", "LEVEL SWITCH", "DI"), ("LAH-202", "LEVEL SWITCH", "SOFT"), ("PSH-301", "PRESSURE SWITCH", "DI"),
                 ("PAH-301", "PRESSURE SWITCH", "SOFT")])
    by = groups(data)
    assert by["LEVEL SWITCH"]["tags"] == ["LAH-201"] and by["PRESSURE SWITCH"]["tags"] == ["PSH-301"]


def test_gauges_without_signals_are_offered_in_the_library():
    by = groups(iodb([("PG-101", "PRESSURE GAUGE", "-"), ("TG-101", "TEMPERATURE GAUGE", None), ("LG-101", "LEVEL GAUGE", "-"),
                      ("PI-101", "LOCAL PRESSURE INDICATOR", None), ("PI-102", "LOCAL PRESSURE INDICATOR", "SOFT")]))
    assert [by[k]["tags"] for k in ("PRESSURE GAUGE", "TEMPERATURE GAUGE", "LEVEL GAUGE", "LOCAL PRESSURE INDICATOR")] == \
           [["PG-101"], ["TG-101"], ["LG-101"], ["PI-101"]]


def test_a_missing_signal_column_never_confirms_a_transmitter():
    res = DL.analyze_iodb(iodb([("PT-1", "PRESSURE TRANSMITTER"), ("PG-1", "PRESSURE GAUGE")], ["TAG NO", "INSTRUMENT TYPE"]))
    assert [g["instrument_type"] for g in res["groups"]] == ["PRESSURE GAUGE"] and "no SIGNAL I/O TYPE column" in res["warnings"][0]


# ───────── subtypes ─────────
MCOLS = ["TAG NO", "INSTRUMENT TYPE NAME", "INSTRUMENT MEASURING  TYPE", "SIGNAL I/O TYPE"]
LT = "LEVEL INDICATING TRANSMITTER"


def test_measuring_technologies_are_never_mixed():
    data = iodb([("LIT-1", LT, "NON CONTACT RADAR", "AI"), ("LIT-2", LT, "ULTRASONIC", "AI"), ("LIT-3", LT, "SUBMERSIBLE", "AI"),
                 ("LIT-4", LT, "GUIDED WAVE RADAR", "AI"), ("LAH-1", LT, "NON CONTACT RADAR", "SOFT"), ("LIT-5", LT, "RADAR", "AI"),
                 ("LIT-6", LT, "HYDROSTATIC", "AI"), ("LIT-7", LT, "CAPACITANCE", "AI")], MCOLS)
    by = groups(data)
    ncr, us = f"{LT} - NON CONTACT RADAR", f"{LT} - ULTRASONIC"
    assert by[ncr]["tags"] == ["LIT-1"] and by[ncr]["template_id"] == "lt_radar"
    assert by[us]["tags"] == ["LIT-2"] and by[us]["template_id"] == "lt_ultrasonic"
    assert by[f"{LT} - GUIDED WAVE RADAR"]["template_id"] == "lt_gwr" and by[f"{LT} - RADAR"]["tags"] == ["LIT-5"]
    assert all(by[f"{LT} - {m}"]["template_id"] is None for m in ("SUBMERSIBLE", "HYDROSTATIC", "CAPACITANCE"))
    df = _load_iodb_df(data)[0]
    for other in ("LIT-2", "LIT-3", "LIT-4", "LIT-5", "LAH-1"):
        assert DE.check_selection(df, [other], ncr), other
    assert DE.check_selection(df, ["LIT-1"], us)


def test_spelling_differences_do_not_split_a_type_but_different_types_stay_apart():
    by = groups(iodb([("AIT-1", "ANALYSER TRANSMITTER - pH", "AI"), ("AIT-2", "ANALYSER TRANSMITTER -PH", "AI"),
                      ("AIT-3", "ANALYSER TRANSMITTER - PH", "AI"), ("AIT-4", "ANALYSER TRANSMITTER - PH/TEMP", "AI")]))
    assert len(by) == 2 and sorted(g["tag_count"] for g in by.values()) == [1, 3]


# ───────── unique physical instruments ─────────
def test_one_instrument_per_tag_and_prefixes_are_significant():
    data = iodb([("100-LIT-010", NCR, "AI"), ("100-LIT-010", NCR, "AI"), ("100-lit-010", NCR, "AI"), ("200-LIT-010", NCR, "AI"),
                 ("100-LIT-10", NCR, "AI"), ("100-LIT-010A", NCR, "AI"), ("_", NCR, "AI"), ("TBA", NCR, "AI")])
    g = groups(data)[NCR]
    assert g["tags"] == ["100-LIT-010", "100-LIT-010A", "100-LIT-10", "200-LIT-010"]
    assert g["diagnostics"]["duplicates_excluded"] == 2 and g["diagnostics"]["no_tag_excluded"] == 2 and g["duplicates"] == ["100-LIT-010"]


def test_conflicting_types_and_deleted_rows_are_reported_not_chosen_silently():
    data = iodb([("FIT-1", "FLOW TRANSMITTER - MAGNETIC", "AI"), ("FIT-1", "FLOW TRANSMITTER - ULTRASONIC", "AI"),
                 ("LIT-1", NCR, "AI", "OLD TANK", "DELETED IN REV 1"), ("LIT-1", NCR, "AI", "NEW TANK", ""),
                 ("LIT-2", NCR, "AI", "T2", "deleted")])
    by = groups(data)
    assert any("also listed" in c["reason"] for c in by["FLOW TRANSMITTER - MAGNETIC"]["conflicts"])
    assert by[NCR]["deleted_tags"] == ["LIT-2"] and any("DELETED row and a current row" in c["reason"] for c in by[NCR]["conflicts"])
    used = DE.eligible_frame(_load_iodb_df(data)[0], NCR)
    assert used[used["TAG NO"] == "LIT-1"]["SERVICE"].tolist()[0] == "NEW TANK"                  # the current row feeds the annexure


def test_a_type_with_only_soft_records_is_not_offered():
    data = iodb([("AI-1", "ANALYSER TRANSMITTER - PH/TEMP", "SOFT"), ("PT-1", "PRESSURE TRANSMITTER", "AI")])
    res = DL.analyze_iodb(data)
    assert [g["instrument_type"] for g in res["groups"]] == ["PRESSURE TRANSMITTER"]
    assert [x["instrument_type"] for x in res["excluded_types"]] == ["ANALYSER TRANSMITTER - PH/TEMP"]
    assert get_iodb_instrument_types(data) == (["PRESSURE TRANSMITTER"], None)
    assert get_iodb_tags(data, "ANALYSER TRANSMITTER - PH/TEMP") == ([], None)


def test_valves_with_ao_signals_remain_for_valve_datasheets_but_are_not_added_to_the_library():
    data = iodb([("FCV-1", "FLOW CONTROL VALVE", "AO"), ("FCV-1", "FLOW CONTROL VALVE", "AI"), ("FCV-1", "FLOW CONTROL VALVE", "SOFT")])
    assert get_iodb_tags(data, "FLOW CONTROL VALVE") == (["FCV-1"], None)                       # one valve, however many signals
    res = DL.analyze_iodb(data)
    assert res["groups"] == [] and res["hidden"][0]["instrument_type"] == "FLOW CONTROL VALVE"   # the library has no valve template


# ───────── generation and annexure ─────────
def dpt_iodb() -> bytes:
    t = "DP TRANSMITTER"
    return iodb([("PDI-101", t, "SOFT", "SOFT SERVICE"), ("DPT-101", t, "SOFT", "SOFT ROW FIRST"), ("DPT-101", t, "AI", "REAL SERVICE 1"),
                 ("DPT-102", t, "AI", "REAL SERVICE 2"), ("PDAH-101", t, "SOFT", "SOFT SERVICE"), ("DPT-103", t, "AI", "REAL SERVICE 3")])


def cells(data: bytes, sheet: str) -> list:
    return [str(c.value) for row in openpyxl.load_workbook(io.BytesIO(data))[sheet].iter_rows() for c in row if c.value is not None]


def test_the_annexure_holds_only_the_selected_physical_instruments_and_their_own_rows():
    tags = ["DPT-101", "DPT-102", "DPT-103"]
    out, _n, err, failed = DL.generate("dpt", dpt_iodb(), tags + ["PDI-101", "PDAH-101"], {}, None, HEADER, instrument_type="DP TRANSMITTER")
    assert err is None
    assert [f["tag"] for f in failed] == ["PDI-101", "PDAH-101"] and all("SOFT" in f["reason"] for f in failed)
    text = " | ".join(cells(out, "ANNEXURE-I"))
    assert all(t in text for t in tags) and "PDI-101" not in text and "PDAH-101" not in text
    assert "REAL SERVICE 1" in text and "SOFT ROW FIRST" not in text and "SOFT SERVICE" not in text


def test_generation_with_only_excluded_tags_is_refused():
    out, _n, err, failed = DL.generate("dpt", dpt_iodb(), ["PDI-101"], {}, None, HEADER, instrument_type="DP TRANSMITTER")
    assert out is None and "eligible physical instrument" in err and len(failed) == 1


def test_validation_names_ineligible_tags():
    res = DL.validate("dpt", dpt_iodb(), ["DPT-101", "PDI-101", "NOPE"], {}, None, "DP TRANSMITTER", HEADER)
    codes = {(i["code"], i.get("tag")) for i in res["issues"] if i["severity"] == "ERROR"}
    assert ("INELIGIBLE_TAG", "PDI-101") in codes and ("TAG_NOT_IN_IODB", "NOPE") in codes and ("INELIGIBLE_TAG", "DPT-101") not in codes


def request(tags, approval_id, instrument_type="DP TRANSMITTER"):
    f = form(approval_id, tags=tags)
    f["files"] = {"iodb_file": ("iodb.xlsx", dpt_iodb())}
    f["data"]["instrument_type"] = instrument_type
    return f


def test_api_refuses_a_hand_made_request_for_a_soft_record_even_when_approved(api, db):
    tags = ["DPT-101", "PDI-101"]
    r = api.post("/api/sop-datasheet/generate", **request(tags, approval(db, tags=tags)))
    assert r.status_code == 422 and "PDI-101: SOFT signal" in r.json()["detail"] and "DPT-101:" not in r.json()["detail"]
    ok = ["DPT-101"]
    r = api.post("/api/sop-datasheet/generate", **request(ok, approval(db, tags=ok), instrument_type="PRESSURE TRANSMITTER"))
    assert r.status_code == 422 and "not of the instrument type" in r.json()["detail"]
    assert api.post("/api/sop-datasheet/generate", **request(ok, approval(db, tags=ok), instrument_type=" ")).status_code in (400, 422)


def test_api_generates_the_eligible_selection(api, db):
    tags = ["DPT-101", "DPT-102"]
    _, job = run(api, **request(tags, approval(db, tags=tags)))
    assert job["status"] == "done" and job["result"]["tag_count"] == 2 and not job["result"]["failed_tags"], job
    text = " | ".join(cells(api.get("/api/sop-datasheet/download").content, "ANNEXURE-I"))
    assert "DPT-102" in text and "DPT-103" not in text and "SOFT" not in text


def test_api_validation_reports_ineligible_tags(api):
    f = request(["DPT-101", "PDI-101"], None)
    r = api.post("/api/sop-datasheet/validate", **f)
    assert r.status_code == 200 and any(i["code"] == "INELIGIBLE_TAG" and i["tag"] == "PDI-101" for i in r.json()["issues"])
