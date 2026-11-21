"""Datasheet Generator - standard template library (11 instrument templates), type matching, consolidated generation,
validation and the approval gate."""
import hashlib
import re
import io
import json
import time
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

from utils import datasheet_library as DL
from utils import sop_consolidated as SC

LIB = Path(DL.LIB_DIR)
ALL = ["dps", "dpt", "fe_orifice", "fs", "ft_parshall", "ft_dp", "ft_thermal", "ft_clampon", "lg_magnetic", "lg_reflex", "lt_radar",
       "lt_radar_sop", "lt_gwr", "lt_ultrasonic", "lt_dp_open", "fi_glass", "fi_metal", "pg_bourdon",
       "pg_diaphragm", "ps", "pt", "te_rtd", "tg", "tt"]
LEGACY = "lt_radar_sop"                     # the SOP LT workbook: no guide, no annexure (iEZ builds Annexure-I)
HEADER = {"client": "GAIL (INDIA) LTD", "consultant": "PDIL", "project": "NEW WWTP", "plant": "PANIPAT", "client_doc_no": "C-001",
          "vatech_doc_no": "PC286-10P195-I0003-100", "rev": "0", "prepared_by": "AKB", "date": "20.11.2026"}


def blank_iodb() -> bytes:
    wb = openpyxl.Workbook(); ws = wb.active; ws.append(["TAG NO", "INSTRUMENT TYPE"]); ws.append(["X-1", "Y"])
    b = io.BytesIO(); wb.save(b); return b.getvalue()


def iodb_for(tid, n=5, typ=None, blank=(), dup=None):
    """An IODB whose columns are named like the template's annexure headers (so every column maps)."""
    t = DL.entry(tid)
    lc = DL.load_context(tid, blank_iodb())
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "IODB"
    heads, cols = ["TAG NO", "INSTRUMENT TYPE", "SIGNAL I/O TYPE"], []
    for ac in lc.ctx.annexure.columns:
        if ac.kind == "data":
            h = (ac.header + (" " + ac.sub if ac.sub else "")).strip()
            if h not in heads:
                heads.append(h); cols.append(h)
    ws.append(heads)
    for i in range(1, n + 1):
        ws.append([f"{t['code']}-{100 + i}", typ or t["display_name"], "DI"]
                  + [None if (i in blank and j == 0) else f"V{j}-{i}" for j, _ in enumerate(cols)])
    if dup:
        ws.append([f"{t['code']}-{100 + dup}", typ or t["display_name"], "DI"] + ["OTHER"] * len(cols))
    b = io.BytesIO(); wb.save(b); return b.getvalue()


def tags_for(tid, n):
    return [f"{DL.entry(tid)['code']}-{100 + i}" for i in range(1, n + 1)]


def pics(xlsx: bytes) -> int:
    z = zipfile.ZipFile(io.BytesIO(xlsx))
    return sum(1 for n in z.namelist() if n.startswith("xl/media/"))


# ── library + templates ──────────────────────────────────────────────────────
def test_library_has_the_eleven_templates():
    assert sorted(t["id"] for t in DL.library()) == sorted(ALL)
    for t in DL.library():
        assert (LIB / t["file"]).exists()


@pytest.mark.parametrize("tid", ALL)
def test_each_template_loads_and_generates(tid):
    master = (LIB / DL.entry(tid)["file"]).read_bytes()
    digest = hashlib.sha256(master).hexdigest()
    info = DL.template_info(DL.entry(tid))
    roles = {s["role"]: s["sheet"] for s in info["sheets"]}
    assert roles["main"]
    if tid != LEGACY:
        for r in ("example", "annexure", "annexure2", "checklist", "cover", "index"):
            assert roles.get(r), f"{tid}: {r} not identified"
    fields, notes = DL.fields_for(DL.entry(tid))
    assert len(fields) >= 15
    assert any(f.scope == "tag" for f in fields) and any(f.scope == "common" for f in fields)
    lc = DL.load_context(tid, blank_iodb())
    main = lc.ctx.sheets[roles["main"]]
    for f in fields:                                                      # every field sits on its own main-sheet row
        assert re.sub(r"\s", "", main.value(f.spec.row, 1)).lower() == re.sub(r"\s", "", f.spec.label).lower()

    n = 3
    out, name, err, failed = DL.generate(tid, iodb_for(tid, n), tags_for(tid, n), {}, None, HEADER)
    assert err is None and not failed and name.endswith("_CONSOLIDATED_DATASHEET.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(out))
    expected = [roles[r] for r in ("cover", "index", "main", "annexure", "annexure2") if roles.get(r)]
    if tid == LEGACY:
        expected = [roles["main"], "ANNEXURE-I"]
    assert wb.sheetnames == expected                                    # guide + checklist are not part of the document
    ws = wb[roles["main"]]
    tag_row = next(f.spec for f in fields if f.scope == "tag")
    assert ws.cell(tag_row.row + 1, tag_row.value_cols[0] + 1).value == "REFER ANNEXURE-I"
    ann = wb[roles.get("annexure") or "ANNEXURE-I"]
    found = {c.value for row in ann.iter_rows() for c in row}
    assert set(tags_for(tid, n)) <= found
    assert pics(out) >= pics(master)                                      # logos kept
    assert hashlib.sha256((LIB / DL.entry(tid)["file"]).read_bytes()).hexdigest() == digest   # master untouched


def test_engineering_guide_rules_dpt():
    fields, _ = DL.fields_for(DL.entry("dpt"))
    by = {(f.spec.section, f.spec.label): f for f in fields}
    assert by[("GENERAL", "Tag No")].scope == "tag"
    assert by[("PROCESS CONDITIONS", "Pressure (Kg/cm2 g)")].spec.sub_labels == ["Min", "Nor", "Max"]
    assert by[("TRANSMITTER", "Output")].scope == "common" and by[("TRANSMITTER", "Output")].spec.defaults[0] == "FOUNDATION FIELD BUS"
    make = by[("PURCHASE", "Make")]
    assert make.origin == "vendor" and make.spec.defaults == [""] and make.example == ["EMERSON"]   # example not used as a value
    assert by[("PURCHASE", "Spare Qty")].scope == "annexure2"
    assert by[("PURCHASE", "Qty")].origin == "computed"


def test_guide_rows_paired_by_label_when_layout_shifts():
    fields, notes = DL.fields_for(DL.entry("ft_dp"))
    main = DL.sheets_of(DL.entry("ft_dp"))["FT(DP)"]
    fluid = next(f for f in fields if f.spec.label == "Fluid")
    assert main.value(fluid.spec.row, 1) == "Fluid" and fluid.scope == "tag"


# ── instrument type matching ─────────────────────────────────────────────────
@pytest.mark.parametrize("text,tid,status", [
    ("Differential Pressure Transmitter", "dpt", "exact"),
    ("DP Transmitter", "dpt", "alias"),
    ("D.P. TRANSMITTER", "dpt", "keyword"),
    ("DP Switch", "dps", "alias"),
    ("Orifice Flow Element", "fe_orifice", "alias"),
    ("FLOW ELEMENT - ORIFICE", "fe_orifice", "keyword"),
    ("Flow Switch", "fs", "exact"),
    ("Ultrasonic Parshall Flume Flow Transmitter", "ft_parshall", "alias"),
    ("DP Flow Transmitter", "ft_dp", "exact"),
    ("FLOW TRANSMITTER (DP TYPE)", "ft_dp", "alias"),
    ("DIFF. PRESSURE FLOW TRANSMITTER (D/P)", "ft_dp", "keyword"),
    ("Thermal Mass Flow Meter", "ft_thermal", "alias"),
    ("Clamp-On Ultrasonic Flowmeter", "ft_clampon", "alias"),
    ("Magnetic Level Indicator", "lg_magnetic", "alias"),
    ("Reflex Level Gauge", "lg_reflex", "exact"),
    ("Radar Level Transmitter", "lt_radar", "exact"),
    ("LT - NON CONTACT RADAR", "lt_radar", "keyword"),
    ("LEVEL INDICATING TRANSMITTER - NCR TYPE", "lt_radar", "alias"),
    ("Guided Wave Radar Level Transmitter", "lt_gwr", "exact"),
    ("LEVEL TRANSMITTER - GWR", "lt_gwr", "keyword"),
    ("Ultrasonic Level Transmitter", "lt_ultrasonic", "exact"),
    ("LEVEL INDICATING TRANSMITTER-DP OPEN TANK", "lt_dp_open", "keyword"),
    ("LEVEL INDICATING TRANSMITTER-DP", "lt_dp_open", "keyword"),
    ("FLOW INDICATOR GLASS TUBE ROTAMETER", "fi_glass", "keyword"),
    ("ROTAMETER METAL TUBE TYPE", "fi_metal", "keyword"),
    ("PRESSURE GAUGE", "pg_bourdon", "alias"),
    ("PRESSURE GAUGE- BOURDON TYPE", "pg_bourdon", "alias"),
    ("PRESSURE GAUGE- DIAPHRAGM SEAL TYPE", "pg_diaphragm", "alias"),
    ("PRESSURE SWITCH", "ps", "exact"),
    ("PRESSURE INDICATING TRANSMITTER", "pt", "alias"),
    ("PRESSURE INDICATING TRANSMITTER-BOURDON", "pt", "keyword"),
    ("TEMPERATURE ELEMENT", "te_rtd", "alias"),
    ("TEMPERATURE GAUGE", "tg", "exact"),
    ("TEMPERATURE INDIDATING TRANSMITTER-RTD", "tt", "keyword"),
    ("TEMPERATURE INDICATING TRANSMITTER", "tt", "alias"),
])
def test_type_matching(text, tid, status):
    m = DL.match_type(text)
    assert (m["template_id"], m["status"]) == (tid, status)


def test_inactive_template_is_not_offered():
    assert "lt_dp_closed" not in {t["id"] for t in DL.library()}
    with pytest.raises(DL.LibraryError):
        DL.entry("lt_dp_closed")


@pytest.mark.parametrize("text", ["Magnetic Flow Meter", "Level Transmitter", "Ultrasonic Flow Transmitter", "Coriolis Flow Transmitter",
                                  "Flow Element", "Level Switch", "Conductivity Analyzer", "LEVEL TRANSMITTER DP TYPE CLOSED TANK",
                                  "Rotameter", ""])
def test_similar_or_unknown_types_are_never_assigned(text):
    assert DL.match_type(text)["template_id"] is None


def test_ultrasonic_flow_suggests_both_ultrasonic_templates():
    m = DL.match_type("Ultrasonic Flow Transmitter")
    assert m["status"] == "unmatched" and {"ft_clampon", "ft_parshall"} <= set(m["candidates"])


def test_iodb_analysis_groups_all_signal_types():
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "IODB"
    ws.append(["TAG NO", "INSTRUMENT TYPE", "INSTRUMENT DESCRIPTION", "SIGNAL I/O TYPE", "SUB SYSTEM"])
    rows = [("PDT-1", "DP TRANSMITTER", "", "AI", "A-1"), ("PDT-2", "DP TRANSMITTER", "", "AI", "A-1"),
            ("PDT-2", "DP TRANSMITTER", "", "AI", "A-1"),                                   # duplicate row
            ("LG-1", "MAGNETIC LEVEL GAUGE", "", "", ""),                                     # local - no signal
            ("FS-1", "FLOW SWITCH", "", "DI", "B"), ("VT-1", "VIBRATION TRANSMITTER", "", "AI", "A-1"),
            ("X-1", "", "Reflex level gauge for tank T-1", "", "")]                          # blank type, description only
    for r in rows:
        ws.append(list(r))
    b = io.BytesIO(); wb.save(b)
    res = DL.analyze_iodb(b.getvalue())
    by = {g["instrument_type"]: g for g in res["groups"]}
    assert by["DP TRANSMITTER"]["template_id"] == "dpt" and by["DP TRANSMITTER"]["tag_count"] == 2
    assert by["DP TRANSMITTER"]["duplicates"] == ["PDT-2"]
    assert by["MAGNETIC LEVEL GAUGE"]["template_id"] == "lg_magnetic"
    assert by["FLOW SWITCH"]["template_id"] == "fs"
    assert by["VIBRATION TRANSMITTER"]["template_id"] is None and "VIBRATION TRANSMITTER" in res["unsupported"]
    reflex = next(g for g in res["groups"] if g["matched_on"] == "description")
    assert reflex["template_id"] == "lg_reflex" and reflex["status"] == "description"


# ── annexure ─────────────────────────────────────────────────────────────────
def test_annexure_one_tag_clears_template_sample_rows():
    out, *_ = DL.generate("dpt", iodb_for("dpt", 1), tags_for("dpt", 1), {}, None, HEADER)
    ws = openpyxl.load_workbook(io.BytesIO(out))["ANNEXURE-I"]
    vals = {c.value for row in ws.iter_rows() for c in row if c.value}
    assert "DPT-101" in vals and "235-PDT-2001" not in vals and "235-PDT-4001" not in vals     # template examples removed


def test_annexure_expands_with_formatting_footer_and_print_area():
    master = openpyxl.load_workbook(LIB / "fe_orifice.xlsx")["ANNEXURE-I"]
    ann = DL.load_context("fe_orifice", blank_iodb()).ctx.annexure
    n = 60
    out, *_ = DL.generate("fe_orifice", iodb_for("fe_orifice", n), tags_for("fe_orifice", n), {}, None, HEADER)
    ws = openpyxl.load_workbook(io.BytesIO(out))["ANNEXURE-I"]
    first = ann.data_start + 1
    tag_c = ann.tag_col + 1
    assert [ws.cell(first + i, tag_c).value for i in range(n)] == tags_for("fe_orifice", n)
    last = first + n - 1
    src = master.cell(ann.block_end, tag_c)
    assert ws.cell(last, tag_c).border.left.style == src.border.left.style
    assert ws.cell(last, tag_c).font.name == src.font.name
    assert ws.cell(first + n - 1, 1).value == n                          # serial numbers continue
    end_row = int(str(ws.print_area).split("$")[-1])
    assert end_row >= last
    assert ws.print_title_rows                                           # header repeats on every printed page
    # MIN / NOR / MAX columns keep their own values
    p = [ac for ac in ann.columns if ac.header.startswith("PRESSURE")]
    assert [ws.cell(first, ac.col + 1).value for ac in p] != [None] * len(p)
    assert len({ws.cell(first, ac.col + 1).value for ac in p}) == len(p)


def test_missing_iodb_values_stay_blank_and_are_reported():
    io_b = iodb_for("dpt", 3, blank=(2,))
    res = DL.validate("dpt", io_b, tags_for("dpt", 3), {}, None, "Differential Pressure Transmitter", HEADER)
    assert any(i["code"] == "MISSING_TAG_DATA" for i in res["issues"])
    out, *_ = DL.generate("dpt", io_b, tags_for("dpt", 3), {}, None, HEADER)
    ann = DL.load_context("dpt", io_b).ctx.annexure
    ws = openpyxl.load_workbook(io.BytesIO(out))["ANNEXURE-I"]
    first_data = next(ac for ac in ann.columns if ac.kind == "data")
    assert ws.cell(ann.data_start + 2, first_data.col + 1).value is None


def test_missing_annexure_data_is_asked_and_entered_values_fill_only_blanks():
    io_b = iodb_for("dpt", 3, blank=(2,))
    tags = tags_for("dpt", 3)
    ann = DL.load_context("dpt", io_b).ctx.annexure
    first_data = next(ac for ac in ann.columns if ac.kind == "data")
    res = DL.validate("dpt", io_b, tags, {}, None, "Differential Pressure Transmitter", HEADER)
    gaps = res["annexure"]["missing"]
    assert {"tag": tags[1], "col": first_data.col, "label": first_data.label} in gaps and res["annexure"]["missing_total"] == len(gaps)
    assert all(g["tag"] == tags[1] for g in gaps)                                        # only the blank cell is asked
    entered = {tags[1]: {str(first_data.col): "ENTERED"}, tags[0]: {str(first_data.col): "MUST NOT REPLACE IODB"}}
    res2 = DL.validate("dpt", io_b, tags, {}, None, "Differential Pressure Transmitter", HEADER, annexure_values=entered)
    assert not res2["annexure"]["missing"] and res2["annexure"]["manual_filled"] == 1
    assert not any(i["code"] == "MISSING_TAG_DATA" for i in res2["issues"])
    assert res2["annexure"]["preview"][1][str(first_data.col)] == "ENTERED"
    out, *_ = DL.generate("dpt", io_b, tags, {}, None, HEADER, annexure_values=entered)
    ws = openpyxl.load_workbook(io.BytesIO(out))["ANNEXURE-I"]
    assert ws.cell(ann.data_start + 2, first_data.col + 1).value == "ENTERED"
    assert ws.cell(ann.data_start + 1, first_data.col + 1).value == "V0-1"


@pytest.mark.parametrize("text", ["MOTOR COMMAND START", "MOTOR RUNNING STATUS", "ON/OFF VALVE PNEUMATIC", "CONTROL VALVE POSTIONER",
                                  "LEVEL HIGH ALARM", "FLOW TRANSMITTER FAULT ALARM", "PRESSURE INDICATION", "VALVE OPEN STATUS",
                                  "PUMP", "AGITATOR", "AIR BLOWER", "SPARE", "POWER SUPPLY FAILURE", "FLOW TOTALISER IND",
                                  "Belt conveyor pos.1, electric motor 1-M1, forward", "MOTORIZED SLUICE GATE"])
def test_non_instrument_types_are_not_offered(text):
    assert not DL.is_instrument_type(text)


@pytest.mark.parametrize("text", ["DIFFERENTIAL PRESSURE TRANSMITTER", "FLOW ELEMENT", "LEVEL SWITCH-TUNING FORK", "PRESSURE GUAGE",
                                  "TEMPERATURE ELEMENT", "FLOW INDICATING ROTAMETER", "ANALYZER INDICATING TRANSMITTER - PH",
                                  "MAGNETIC LEVEL GAUGE", "ORIFICE PLATE", "FT-THERMAL MASS", "LEVEL INDICATING TRANSMITTER-RADAR"])
def test_instrument_types_are_offered(text):
    assert DL.is_instrument_type(text)


def test_iodb_analysis_hides_motors_valves_and_soft_points():
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "IODB"
    ws.append(["TAG NO", "INSTRUMENT TYPE"])
    for r in [("PDT-1", "DP TRANSMITTER"), ("M-1A", "MOTOR COMMAND START"), ("M-1B", "MOTOR RUNNING STATUS"),
              ("XV-1", "ON/OFF VALVE PNEUMATIC"), ("PAH-1", "PRESSURE ALARM HIGH"), ("PI-1", "PRESSURE INDICATION"), ("P-1", "PUMP")]:
        ws.append(list(r))
    b = io.BytesIO(); wb.save(b)
    res = DL.analyze_iodb(b.getvalue())
    assert [g["instrument_type"] for g in res["groups"]] == ["DP TRANSMITTER"]
    assert len(res["hidden"]) == 6 and res["hidden_tags"] == 6


def test_manual_entry_dropdown_options_are_engineering_values():
    fields, _ = DL.fields_for(DL.entry("dpt"))
    by = {(f.spec.section, f.spec.label): f for f in fields}
    typ = by[("TRANSMITTER", "Type")].spec
    assert typ.input_type == "dropdown" and typ.options[0] == "2 WIRE" and typ.options[-1] == "Custom Value"
    assert not any("radar" in o.lower() for o in typ.options)                          # radar list only on radar templates
    ip = by[("TRANSMITTER", "Enclosure Protection Class")].spec.options
    assert ip[0] == "IP 66" and "IP 67" in ip
    radar, _ = DL.fields_for(DL.entry("lt_radar"))
    assert any("Radar" in o for f in radar if f.spec.label == "Type" for o in f.spec.options)
    for f in fields:                                                                    # tag-wise rows are never dropdowns
        if f.scope != "common":
            assert not f.spec.options


def test_generated_annexure_for_template_without_one():
    lc = DL.load_context(LEGACY, blank_iodb())
    assert lc.derived_annexure
    heads = [c.label for c in lc.ctx.annexure.columns]
    assert heads[:2] == ["SL.No.", "TAG NO."] and "PRESSURE (KG/CM2 G) · MIN" in heads and "TANK MOC" in heads
    scope = {f"{f.spec.section}::{f.spec.label}": "common" for f in lc.lib_fields if f.spec.label == "Nozzle Size"}
    scoped = DL.load_context(LEGACY, blank_iodb(), {"SENSOR::Nozzle Size": "tag"})
    assert any("NOZZLE SIZE" in c.label for c in scoped.ctx.annexure.columns)


def test_worked_example_guide_takes_tag_rows_from_the_annexure():
    # the RTD guide is filled for one real tag (no 'REFER ANNEXURE-I'): Annexure-I columns decide what is tag-wise
    fields, _ = DL.fields_for(DL.entry("te_rtd"))
    tag = {f.spec.label for f in fields if f.scope == "tag"}
    assert {"Tag No", "Location", "P&ID No", "Fluid", "Immersion Length (U) MM"} <= tag
    assert "RTD Material" not in tag
    out, *_ = DL.generate("te_rtd", iodb_for("te_rtd", 2), tags_for("te_rtd", 2), {}, None, HEADER)
    vals = {c.value for row in openpyxl.load_workbook(io.BytesIO(out))["TEMP ELEMENT"].iter_rows() for c in row}
    assert "TE 0102" not in vals and "REFER ANNEXURE-I" in vals                # the example tag is not copied


def test_guide_with_different_section_names_still_pairs_every_row():
    fields, notes = DL.fields_for(DL.entry("fi_glass"))
    assert len(fields) == 30 and not notes["notes"]
    assert next(f for f in fields if f.spec.label == "Tube Material").example == ["GLASS BOROSILICATE"]


def test_header_placeholders_filled_and_reported():
    out, *_ = DL.generate("dps", iodb_for("dps", 2), tags_for("dps", 2), {}, None, HEADER)
    wb = openpyxl.load_workbook(io.BytesIO(out))
    vals = {c.value for ws in wb.worksheets for row in ws.iter_rows() for c in row if isinstance(c.value, str)}
    assert {"GAIL (INDIA) LTD", "PDIL", "NEW WWTP", "PC286-10P195-I0003-100"} <= vals
    res = DL.validate("dps", iodb_for("dps", 2), tags_for("dps", 2), {}, None, "DP Switch", {})
    assert any(i["code"] == "HEADER_PLACEHOLDERS" for i in res["issues"])


def test_values_common_vendor_and_quantity():
    out, *_ = DL.generate("dpt", iodb_for("dpt", 4), tags_for("dpt", 4), {"TRANSMITTER::Output": ["4-20 mA HART"]}, None, HEADER)
    ws = openpyxl.load_workbook(io.BytesIO(out))["DPT"]
    fields, _ = DL.fields_for(DL.entry("dpt"))
    cell = {f.spec.label: ws.cell(f.spec.row + 1, f.spec.value_cols[0] + 1).value for f in fields}
    assert cell["Output"] == "4-20 mA HART" and cell["Power supply"] == "9 - 32 V DC"
    assert cell["Make"] is None and cell["Qty"] == "4 NOS" and cell["Spare Qty"] == "REFER ANNEXURE-II"


# ── validation ───────────────────────────────────────────────────────────────
def test_validation_rules():
    io_b = iodb_for("dpt", 3, dup=1)
    res = DL.validate("dpt", io_b, tags_for("dpt", 3) + ["DPT-101", "NOPE-1"], {}, None, "D.P. TRANSMITTER", {},
                      ai_confidence={"TRANSMITTER::Accuracy": 0.3})
    codes = {i["code"]: i["severity"] for i in res["issues"]}
    assert codes["DUPLICATE_TAG"] == "ERROR" and codes["TAG_NOT_IN_IODB"] == "ERROR"
    assert codes["UNCERTAIN_CLASSIFICATION"] == "REVIEW" and codes["CONFLICTING_TAG_DATA"] == "REVIEW"
    assert codes["LOW_CONFIDENCE_AI"] == "REVIEW" and codes["VENDOR_DATA_PENDING"] == "INFO"
    assert codes["ANNEXURE_II_TEMPLATE"] == "INFO"
    assert res["counts"]["ERROR"] == 2 and res["counts"]["INFO"] >= 2
    manual = DL.validate("dpt", iodb_for("dpt", 2), tags_for("dpt", 2), {}, None, "Pressure Transmitter", HEADER)
    assert any(i["code"] == "TEMPLATE_CHOSEN_MANUALLY" for i in manual["issues"])
    ok = DL.validate("dpt", iodb_for("dpt", 2), tags_for("dpt", 2), {}, None, "Differential Pressure Transmitter", HEADER)
    assert ok["counts"]["ERROR"] == 0
    assert not any(i["code"] in ("UNCERTAIN_CLASSIFICATION", "HEADER_PLACEHOLDERS") for i in ok["issues"])


def test_bad_template_ids():
    for bad in ("../etc/passwd", "nope", "", "DPS"):
        with pytest.raises(DL.LibraryError):
            DL.entry(bad)


# ── API + approval gate ──────────────────────────────────────────────────────
@pytest.fixture()
def api(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user, get_db
    from app.routers import sop_datasheet as R
    R.generation_cache.clear()
    app = FastAPI()
    app.include_router(R.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=5151, username="u")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


TAGS = ["DPT-101", "DPT-102", "DPT-103"]


def approval(db, status="approved", template_id="dpt", tags=TAGS, overrides=None, mapping=None, header=None, annexure_values=None):
    from app.auth.models import ApprovalRequest
    meta = {"format": SC.CONSOLIDATED, "datasheet": "DPT", "template_id": template_id,
            "overrides": overrides or {"TRANSMITTER::Output": ["APPROVED OUTPUT"]}, "annexure_mapping": mapping,
            "header": header or HEADER, "field_scope": {}, "annexure_values": annexure_values or {}}
    req = ApprovalRequest(request_type="spec", tag_numbers=json.dumps(tags), instrument_type="DP TRANSMITTER",
                          payload_json=json.dumps({"Output": "APPROVED OUTPUT", "__iez": meta}), submitted_by_name="Eng",
                          submitted_by_id="E1", status=status, reviewed_by_name="Lead A", reviewed_by_id="L9",
                          reviewed_role="Lead Engineer", updated_at=datetime(2026, 11, 21, 9, 0))
    db.add(req); db.commit(); db.refresh(req)
    return req.id


def form(approval_id=None, tags=TAGS, template_id="dpt", overrides=None, mapping=None):
    data = {"template_id": template_id, "datasheet_sheet": "DPT", "instrument_type": "DP TRANSMITTER",
            "selected_tags": json.dumps(tags), "overrides": json.dumps(overrides or {"TRANSMITTER::Output": ["BROWSER VALUE"]}),
            "annexure_mapping": json.dumps(mapping or {}), "generation_format": "CONSOLIDATED"}
    if approval_id is not None:
        data["approval_id"] = str(approval_id)
    return {"files": {"iodb_file": ("iodb.xlsx", iodb_for("dpt", 3))}, "data": data}


def run(api, **kw):
    r = api.post("/api/sop-datasheet/generate", **kw)
    if r.status_code != 202:
        return r, None
    for _ in range(150):
        j = api.get(f"/api/sop-datasheet/generate/status/{r.json()['job_id']}").json()
        if j["status"] != "processing":
            return r, j
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_api_library_and_iodb_analysis(api):
    lib = api.get("/api/sop-datasheet/library").json()["templates"]
    assert len(lib) == len(ALL) and all(t["output_filename"].endswith(".xlsx") for t in lib)
    t = api.get("/api/sop-datasheet/library/dpt").json()
    assert t["template"]["has_guide"] and len(t["fields"]) == 34 and "client" in t["header_fields"]
    assert api.get("/api/sop-datasheet/library/..%2Fsecret").status_code == 404
    r = api.post("/api/sop-datasheet/library/analyze-iodb", files={"iodb_file": ("i.xlsx", iodb_for("dpt", 3))})
    assert r.status_code == 200 and r.json()["groups"][0]["template_id"] == "dpt"
    assert api.post("/api/sop-datasheet/library/analyze-iodb", files={"iodb_file": ("i.txt", b"x")}).status_code == 400
    assert api.post("/api/sop-datasheet/library/analyze-iodb", files={"iodb_file": ("i.xlsx", b"garbage")}).status_code == 400
    v = api.post("/api/sop-datasheet/validate", **{**form(), "data": {**form()["data"], "header": json.dumps(HEADER)}})
    assert v.status_code == 200 and v.json()["counts"]["ERROR"] == 0 and v.json()["template"]["id"] == "dpt"


def test_api_approval_gate_for_library_templates(api, db):
    assert api.post("/api/sop-datasheet/generate", **form()).status_code == 409                        # approval required
    assert api.post("/api/sop-datasheet/generate", **form(approval(db, "pending"))).status_code == 409
    assert api.post("/api/sop-datasheet/generate", **form(approval(db, "rejected"))).status_code == 409
    ok = approval(db)
    assert api.post("/api/sop-datasheet/generate", **form(ok, tags=TAGS[:2])).status_code == 409        # tags changed
    r = api.post("/api/sop-datasheet/generate", **form(ok, template_id="dps"))                        # template changed
    assert r.status_code == 409 and "template" in r.json()["detail"]
    legacy = approval(db, template_id=None)                                                            # approved for an upload
    assert api.post("/api/sop-datasheet/generate", **form(legacy)).status_code == 409
    _, job = run(api, **form(ok, mapping={"99": "SOMETHING"}))
    assert job["status"] == "done", job
    assert job["result"]["filename"] == "DPT_CONSOLIDATED_DATASHEET.xlsx" and job["result"]["tag_count"] == 3
    d = api.get("/api/sop-datasheet/download")
    assert d.status_code == 200 and "DPT_CONSOLIDATED_DATASHEET.xlsx" in d.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(d.content))
    fields, _ = DL.fields_for(DL.entry("dpt"))
    out = next(f for f in fields if f.spec.label == "Output")
    assert wb["DPT"].cell(out.spec.row + 1, out.spec.value_cols[0] + 1).value == "APPROVED OUTPUT"     # not the browser value
    assert "GAIL (INDIA) LTD" in {c.value for row in wb["COVER SHEET"].iter_rows() for c in row}       # approved header
    assert str(wb["DPT"]["B5"].value).startswith("='COVER SHEET'!")                                     # main header reads it
    ap = next(f for f in fields if f.spec.label == "Make")
    assert wb["DPT"].cell(ap.spec.row + 1, ap.spec.value_cols[0] + 1).value is None


def test_api_approved_annexure_entries_are_generated(api, db):
    io_b = iodb_for("dpt", 3, blank=(2,))
    ann = DL.load_context("dpt", io_b).ctx.annexure
    col = next(ac for ac in ann.columns if ac.kind == "data").col
    f = form(approval(db, annexure_values={"DPT-102": {str(col): "APPROVED ENTRY"}}))
    f["files"] = {"iodb_file": ("iodb.xlsx", io_b)}
    v = api.post("/api/sop-datasheet/validate", files={"iodb_file": ("iodb.xlsx", io_b)},
                 data={**f["data"], "annexure_values": json.dumps({"DPT-102": {str(col): "X"}})})
    assert v.status_code == 200 and v.json()["annexure"]["manual_filled"] == 1
    _, job = run(api, **f)
    assert job["status"] == "done", job
    ws = openpyxl.load_workbook(io.BytesIO(api.get("/api/sop-datasheet/download").content))["ANNEXURE-I"]
    assert ws.cell(ann.data_start + 2, col + 1).value == "APPROVED ENTRY"


def test_api_other_users_cannot_download(api, db):
    _, job = run(api, **form(approval(db)))
    assert job["status"] == "done"
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user, get_db
    from app.routers import sop_datasheet as R
    app = FastAPI(); app.include_router(R.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=999999, username="other")
    app.dependency_overrides[get_db] = lambda: db
    other = TestClient(app).get("/api/sop-datasheet/download")
    assert other.status_code == 404
