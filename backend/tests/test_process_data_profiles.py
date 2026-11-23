"""Process Data Requisition: verified datasheet profiles (instrument-specific default parameters)."""
import io
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils.process_data_library import INSTRUMENT_TYPES  # noqa: E402
from utils.process_data_profiles import PROFILES, comparison_rows, resolve_fields, default_field_names  # noqa: E402

# (type key, subtype, datasheet file) of the ten reference datasheets + the Pressure Transmitter one
TEN = [
    ("differential_pressure_switch", "", "DIFFERENTIAL PRESSURE SWITCH-R0.xls"),
    ("pressure_transmitter", "Differential Pressure", "DIFFERENTIAL PRESSURE TRANSMITTER-R0.xls"),
    ("orifice_plate", "", "FE-ORIFICE PLATE-R0.xls"),
    ("flow_switch", "", "FLOW SWITCH.xls"),
    ("flow_transmitter", "Ultrasonic Parshall Flume", "FLOW TRANSMITTER-ULTRASONIC PARSHALL FLUME-R0.xls"),
    ("flow_transmitter", "Differential Pressure", "FT-DP-R0.xls"),
    ("flow_transmitter", "Thermal Mass", "FT-THERMAL MASS-R0.xls"),
    ("flow_transmitter", "Ultrasonic Clamp-On", "FT-ULTRASONIC CLAMP ON-R0.xls"),
    ("level_gauge", "Magnetic", "LG-Magnetic Type-R0.xls"),
    ("level_gauge", "Reflex", "LG-REFLEX TYPE-R0.xls"),
]
LEVEL_TX = [
    ("level_transmitter", "Guided Wave Radar", "LT Guided Wave Radar-R0.Xls"),
    ("level_transmitter", "Non-Contact Radar", "LT Non contact Radar Type-R0-1.xls"),
    ("level_transmitter", "Ultrasonic", "LT Ultrasonic TypeR0.xls"),
]

# Default parameters per profile, taken from the verified ANNEXURE-I of each datasheet (header = name + printed unit).
_P = ["Minimum Operating Pressure (Kg/cm2 g)", "Normal Operating Pressure (Kg/cm2 g)", "Maximum Operating Pressure (Kg/cm2 g)"]
_T = ["Minimum Operating Temperature (°C)", "Normal Operating Temperature (°C)", "Maximum Operating Temperature (°C)"]
_FTP = ["Pressure Min (Kg/cm2 g)", "Normal Pressure (Kg/cm2 g)", "Pressure Max (Kg/cm2 g)"]
_FTT = ["Temperature Min (°C)", "Normal Temperature (°C)", "Temperature Max (°C)"]
_LGP = ["Operating Pressure Minimum (Kg/Cm2 g)", "Operating Pressure Normal (Kg/Cm2 g)", "Operating Pressure Maximum (Kg/Cm2 g)"]
_LGT = ["Temperature Minimum (°C)", "Normal Temperature (°C)", "Temperature Maximum (°C)"]
EXPECTED = {
    ("differential_pressure_switch", ""): ["Process Fluid / Service", *_P, *_T, "Switching Setpoint (Kg/cm2 g)"],
    ("pressure_transmitter", "Differential Pressure"): [
        "Process Fluid", "Pressure Minimum (Kg/cm2 g)", "Normal Operating Pressure (Kg/cm2 g)", "Pressure Maximum (Kg/cm2 g)",
        "Temperature Minimum (°C)", "Normal Operating Temperature (°C)", "Temperature Maximum (°C)"],
    # annexure order: DENSITY, FLOW, PRESSURE, TEMP., ... MAX.ALLOWABLE PRESSURE LOSS
    ("orifice_plate", ""): ["Process Fluid / Service", "Fluid Density (Kg/m3)",
                            "Minimum Flow (m3/hr)", "Normal Flow (m3/hr)", "Maximum Flow (m3/hr)", *_P, *_T,
                            "Maximum Allowable Pressure Loss (mmWC)"],
    ("flow_switch", ""): ["Process Fluid / Service",
                          "Minimum Flow (lpm)", "Normal Flow (lpm)", "Maximum Flow (lpm)", *_P, *_T,
                          "Density (kg/m3)", "Viscosity (Cp)", "Flow Setpoint (lpm)"],
    ("flow_transmitter", "Ultrasonic Parshall Flume"): [
        "Process Fluid", "Flow Minimum (m3/hr)", "Normal Flow (m3/hr)", "Flow Maximum (m3/hr)", *_FTP, *_FTT,
        "Height at Operating Flow (mm)", "Height at Maximum Flow (mm)", "Specific Gravity", "Viscosity (Cp)", "Liquid Depth (mm)"],
    ("flow_transmitter", "Differential Pressure"): ["Process Fluid", *_FTP, *_FTT, "Specific Gravity"],
    ("flow_transmitter", "Thermal Mass"): [
        "Process Fluid", "Flow Minimum (Nm3/hr)", "Normal Flow (Nm3/hr)", "Flow Maximum (Nm3/hr)",
        "Pressure Min (mmWC)", "Normal Pressure (mmWC)", "Pressure Max (mmWC)", *_FTT],
    ("flow_transmitter", "Ultrasonic Clamp-On"): [
        "Process Fluid", "Flow Minimum (m3/hr)", "Normal Flow (m3/hr)", "Flow Maximum (m3/hr)",
        "Pressure Min (mmWC)", "Normal Pressure (mmWC)", "Pressure Max (mmWC)", *_FTT,
        "Minimum Velocity (m/s)", "Normal Velocity (m/s)", "Maximum Velocity (m/s)",
        "Specific Gravity", "Viscosity (Cp)"],
    ("level_gauge", "Magnetic"): ["Process Fluid", "Specific Gravity", "Viscosity (cP)", *_LGP, *_LGT,
                                  "Presence of Agitation", "Presence of Fumes"],
    ("level_gauge", "Reflex"): ["Process Fluid", "Specific Gravity", *_LGP, *_LGT, "Presence of Agitation", "Presence of Fumes"],
}
_LTP = ["Process Pressure Min (Kg/Cm2 g)", "Process Pressure Normal (Kg/Cm2 g)", "Process Pressure Max (Kg/Cm2 g)"]
_LTT = ["Process Temperature Min (°C)", "Process Temperature Normal (°C)", "Process Temperature Max (°C)"]


def _lt(height_unit):
    h = f"Tank / Vessel Height ({height_unit})" if height_unit else "Tank / Vessel Height"
    return ["Process Fluid", "Specific Gravity", "Viscosity (cP)", *_LTP, *_LTT, "Tank MOC", h, "Agitation", "Presence of Fumes"]


# Level transmitter: pressure, temperature, tank MOC and tank height are selected (the engineer's request), together with
# the other process columns of the annexure; the tank-height unit is the printed one (none until a subtype is chosen).
EXPECTED.update({("level_transmitter", ""): _lt(""), ("level_transmitter", "Guided Wave Radar"): _lt("mtrs"),
                 ("level_transmitter", "Non-Contact Radar"): _lt("mm"), ("level_transmitter", "Ultrasonic"): _lt("mm")})


def _iodb_df():
    cols = ["TAG NO", "EQUIPMENT DESCRIPTION", "P&ID NO.", "INSTRUMENT TYPE NAME", "SERVICE", "LINE", "EQUIPMENT NO",
            "DENSITY (kg/m3)", "VISCOSITY (cP)", "SPECIFIC GRAVITY", "TEMPERATURE MIN (deg C)", "TEMPERATURE MAX (deg C)",
            "PRESSURE MIN (kg/cm2)", "PRESSURE MAX (kg/cm2)", "FLOW MIN (m3/hr)", "FLOW MAX (m3/hr)", "VELOCITY (m/s)"]
    rows = [
        ("230-FS-101", "FS", "P1", "Flow Switch", "SCALE PIT", "25-W-1", "E1", 1000, 1.0, "", 25, 55, 11, 15, 10, 40, ""),
        ("230-FS-102", "FS", "P1", "Flow Switch", "SETTLING", "25-W-2", "E2", "", "", "", "", "", "", "", "", "", ""),
        ("230-PDS-101", "DPS", "P2", "Differential Pressure Switch", "STRAINER", "200-CW-1", "E3", "", "", "", 30, 50, 3, 5, "", "", ""),
        ("230-FE-101", "FE", "P3", "Orifice Plate", "OILY DAF", "150-P-424", "E4", 1000, "", "", 20, 55, 3, 6, 62, 150, ""),
        ("230-FIT-801", "FIT", "P4", "Thermal Mass Flow Transmitter", "BIOGAS", "300-GL-1", "E5", "", "", "", 25, 50, 200, 300, 468, 907, ""),
        ("230-FIT-901", "FIT", "P5", "Flow Indicating Transmitter", "WATER", "100-W-9", "E6", 998, 0.9, 1.0, 5, 40, 1, 5, 5, 60, 2.0),
        ("230-PDT-101", "PDT", "P6", "Differential Pressure Transmitter", "FILTER", "250-W-2", "E7", "", "", "", 25, 65, 0.1, 0.5, "", "", ""),
        ("230-LG-101", "LG", "P7", "Level Gauge", "ALUM TANK", "-", "TK-1", "", 0.01, 1.1, 30, 50, 0, 0, "", "", ""),
        ("200-P-001", "PUMP", "P8", "Pump", "LIFT", "-", "P-1", "", "", "", "", "", "", "", "", "", ""),
    ]
    return pd.DataFrame(rows, columns=cols)


def _iodb_bytes(df=None):
    buf = io.BytesIO()
    (df if df is not None else _iodb_df()).to_excel(buf, index=False)
    return buf.getvalue()


@pytest.fixture()
def api():
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import process_data
    app = FastAPI()
    app.include_router(process_data.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, username="alice")
    return TestClient(app)


def _profile(api, key, subtype=""):
    r = api.get("/api/process-data/profile", params={"instrument_type": key, **({"subtype": subtype} if subtype else {})})
    assert r.status_code == 200, r.text
    return r.json()


def _generate(api, key, subtype="", selected=None, prefill=False, tags=None):
    data = {"instrument_type": key, "selected_tags": json.dumps(tags or ["x"]), "use_iodb_values": str(prefill).lower(), "project_id": "10P211"}
    if subtype:
        data["subtype"] = subtype
    if selected is not None:
        data["selected_fields"] = json.dumps(selected)
    return api.post("/api/process-data/generate", data=data, files={"iodb_file": ("iodb.xlsx", _iodb_bytes())})


def _tags_of(api, key, subtype=""):
    r = api.post("/api/process-data/match-tags", data={"instrument_type": key, **({"subtype": subtype} if subtype else {})},
                 files={"file": ("iodb.xlsx", _iodb_bytes())})
    assert r.status_code == 200, r.text
    return [t["tag_no"] for t in r.json()["matched_tags"]]


def _sheet(api):
    d = api.get("/api/process-data/download")
    assert d.status_code == 200
    ws = load_workbook(io.BytesIO(d.content))["PROCESS DATA REQUISITION"]
    return ws, [c.value for c in ws[5]][8:]


# ── Test 1: default field selection for all ten datasheets ──────────────────
@pytest.mark.parametrize("key,subtype,_file", TEN + LEVEL_TX)
def test_default_selection_is_the_verified_annexure_profile(api, key, subtype, _file):
    p = _profile(api, key, subtype)
    assert p["verified"] and p["template"] == _file and p["sheet"] == "ANNEXURE-I"
    chosen = [f["header"] for f in p["fields"] if f["name"] in p["default_fields"]]
    assert chosen == EXPECTED[(key, subtype)]
    assert all(f["default_selected"] for f in p["fields"] if f["name"] in p["default_fields"])


# ── the profile headings are the real ANNEXURE-I headings of the original datasheets ──
def _annexure_labels(path):
    xlrd = pytest.importorskip("xlrd")
    sheet = next(s for s in xlrd.open_workbook(str(path)).sheets() if "ANNEX" in s.name.upper())
    norm = lambda t: re.sub(r"\s+", "", str(t)).upper()           # noqa: E731
    for r in range(sheet.nrows):
        if str(sheet.cell_value(r, 0)).strip().upper().startswith("SL"):
            header = {c: str(sheet.cell_value(r, c)).replace("\n", " ") for c in range(sheet.ncols) if str(sheet.cell_value(r, c)).strip()}
            labels = {norm(v) for v in header.values()}
            for k in (1, 2, 3):
                if r + k >= sheet.nrows:
                    break
                for c in range(sheet.ncols):
                    sub = str(sheet.cell_value(r + k, c)).strip()
                    if norm(sub) in {"MIN", "NOR", "MAX", "ID(MM)", "OD(MM)"}:
                        group = header[max(h for h in header if h <= c)]
                        labels.add(norm(f"{group} - {sub}"))
            return labels
    raise AssertionError(f"no SL.No. heading row in {path}")


@pytest.mark.parametrize("key,subtype,filename", TEN + LEVEL_TX + [("pressure_transmitter", "Standard", "PRESSURE TRANSMITTER-R0.xls")])
def test_profile_headings_match_the_original_datasheet(key, subtype, filename):
    path = ROOT / filename
    if not path.exists():
        pytest.skip(f"{filename} is not in the repository checkout")
    printed = _annexure_labels(path)
    profile = PROFILES[(key, subtype)]
    missing = [h.label for h in profile.headings if re.sub(r"\s+", "", h.label).upper() not in printed]
    assert not missing, f"{filename}: headings not printed on the annexure: {missing}"
    expected_printed = {re.sub(r"\s+", "", h.label).upper() for h in profile.headings}
    groups = {x.rsplit("-", 1)[0] for x in printed if x.endswith(("-MIN", "-NOR", "-MAX", "-ID(MM)", "-OD(MM)"))}
    unlisted = sorted(printed - expected_printed - groups)          # a group heading is covered by its MIN/NOR/MAX columns
    assert not unlisted, f"{filename}: annexure headings missing from the profile: {unlisted}"


# ── comparison report integrity ─────────────────────────────────────────────
def test_comparison_actions_agree_with_the_configuration():
    rows = comparison_rows()
    assert {r["action"] for r in rows} <= {"EXISTS_DEFAULT", "EXISTS_OPTIONAL", "ADD_NEW_FIELD", "UNIT_REVIEW", "MAPPING_REVIEW",
                                           "REFERENCE_ONLY", "NOT_APPLICABLE"}
    for r in rows:
        if not r["field"]:
            assert r["classification"] in ("Reference", "Additional", "Review") and not r["default"]
            continue
        cfg = INSTRUMENT_TYPES[r["type"]]
        names = {f.name for f in resolve_fields(cfg, r["subtype"] or None)}
        assert r["field"] in names, r            # every mapped heading exists in the generator configuration
        if r["default"]:
            # only process data is selected by default; the two tank fields of the level transmitter are the engineer's
            # explicit request and say so in their note
            assert r["classification"] == "Process" or "engineer's request" in r["note"] or (
                r["type"] == "level_transmitter" and r["field"] in ("Tank MOC", "Tank / Vessel Height")), r


def test_distinct_engineering_quantities_stay_separate():
    for (key, st), p in PROFILES.items():
        fields = [h.field for h in p.headings if h.field]
        assert len(fields) == len(set(fields)), f"{key}/{st}: a field is mapped twice"
        defaults = {h.field for h in p.headings if h.default}
        for banned in ("Instrument Range", "Calibrated Range", "Design Pressure", "Design Temperature", "Switching Differential (Adjustable)",
                       "Differential Pressure Minimum", "Differential Pressure Normal", "Differential Pressure Maximum",
                       "Meter Range Minimum", "Meter Range Maximum", "Measuring Range", "Calibration Range", "Differential Pressure Range"):
            assert banned not in defaults, f"{banned} must never be a default process input ({key}/{st})"
    # a differential-pressure flow transmitter has no flow MIN/NOR/MAX on its annexure -> none is selected by default
    dp_flow = default_field_names(INSTRUMENT_TYPES["flow_transmitter"], "Differential Pressure")
    assert not {"Flow Minimum", "Normal Flow", "Flow Maximum"} & set(dp_flow)
    # the setpoint is independent of the flow range
    assert "Flow Setpoint" in default_field_names(INSTRUMENT_TYPES["flow_switch"]) and "Setpoint Range" not in default_field_names(INSTRUMENT_TYPES["flow_switch"])


# ── Test 2: direct generation with the defaults; Test 11: Excel output ──────
def test_direct_generation_uses_the_default_profile(api):
    tags = _tags_of(api, "flow_switch")
    assert tags == ["230-FS-101", "230-FS-102"]
    g = _generate(api, "flow_switch", tags=tags)                       # no selected_fields: nothing picked by hand
    assert g.status_code == 200, g.text
    ws, headers = _sheet(api)
    assert headers == EXPECTED[("flow_switch", "")]
    assert [c.value for c in ws[5]][:8] == ["S.NO", "TAG NO", "EQUIPMENT DESCRIPTION", "P&ID NO.", "SERVICE", "EQUIPMENT NO", "LINE", "LINE SIZE"]
    assert [ws.cell(r, 2).value for r in (6, 7)] == tags
    assert ws["A2"].value == "Instrument Type: Flow Switch"


def test_subtype_profile_is_used_when_no_selection_is_sent(api):
    g = _generate(api, "flow_transmitter", "Thermal Mass", tags=_tags_of(api, "flow_transmitter", "Thermal Mass")[:1])
    assert g.status_code == 200, g.text
    _, headers = _sheet(api)
    assert headers == EXPECTED[("flow_transmitter", "Thermal Mass")]


# ── Test 3 / 4: add an optional parameter, deselect a default ───────────────
def test_adding_and_removing_parameters(api):
    tags = _tags_of(api, "orifice_plate")
    defaults = default_field_names(INSTRUMENT_TYPES["orifice_plate"])
    plus = defaults + ["Beta Ratio", "Orifice Bore Diameter"]
    assert _generate(api, "orifice_plate", selected=plus, tags=tags).status_code == 200
    _, headers = _sheet(api)
    assert "Beta Ratio" in headers and "Orifice Bore Diameter (mm)" in headers and len(headers) == len(defaults) + 2
    minus = [n for n in defaults if n != "Fluid Density"]
    assert _generate(api, "orifice_plate", selected=minus, tags=tags).status_code == 200
    _, headers = _sheet(api)
    assert "Fluid Density (Kg/m3)" not in headers and len(headers) == len(defaults) - 1


def test_selection_is_validated_and_deduplicated(api):
    tags = _tags_of(api, "flow_switch")
    bad = _generate(api, "flow_switch", selected=["Flow Setpoint", "Not A Field"], tags=tags)
    assert bad.status_code == 400 and "Not A Field" in bad.json()["detail"]
    # a field that exists only for another type is rejected, not carried over
    assert _generate(api, "flow_switch", selected=["Switching Setpoint"], tags=tags).status_code == 400
    assert _generate(api, "flow_switch", selected=[], tags=tags).status_code == 400
    assert _generate(api, "flow_switch", selected=["Flow Setpoint", "Flow Setpoint", "Density"], tags=tags).status_code == 200
    _, headers = _sheet(api)
    assert headers == ["Density (kg/m3)", "Flow Setpoint (lpm)"] or sorted(headers) == sorted(["Density (kg/m3)", "Flow Setpoint (lpm)"])
    assert _generate(api, "flow_switch", "Nonsense", tags=tags).status_code == 400


# ── Test 5 / 6: restore defaults, switching types ───────────────────────────
def test_defaults_are_stable_and_each_type_has_its_own(api):
    first = _profile(api, "flow_switch")["default_fields"]
    _generate(api, "flow_switch", selected=["Density"], tags=_tags_of(api, "flow_switch"))     # a temporary custom selection...
    assert _profile(api, "flow_switch")["default_fields"] == first                              # ...never changes the defaults
    fs = set(first)
    pt = set(_profile(api, "pressure_transmitter", "Standard")["default_fields"])
    assert not (fs & {"Switching Setpoint", "Flow Setpoint"} and pt & {"Flow Setpoint"})
    assert "Flow Setpoint" not in pt and "Process Fluid" in pt
    assert set(_profile(api, "level_gauge", "Reflex")["default_fields"]) != set(_profile(api, "level_gauge", "Magnetic")["default_fields"])
    assert "Viscosity" in _profile(api, "level_gauge", "Magnetic")["default_fields"]
    assert "Viscosity" not in _profile(api, "level_gauge", "Reflex")["default_fields"]


def test_types_without_a_verified_profile_keep_their_behaviour(api):
    p = _profile(api, "temperature_gauge")
    assert not p["verified"] and len(p["default_fields"]) == len(p["fields"])
    assert _profile(api, "flow_transmitter", "Vortex")["verified"] is False
    assert len(_profile(api, "flow_transmitter", "Vortex")["default_fields"]) == len(_profile(api, "flow_transmitter", "Vortex")["fields"])


# ── Test 7: engineering units ───────────────────────────────────────────────
def test_units_follow_each_datasheet_without_conversion(api):
    fields = {(k, s): {f["name"]: f["unit"] for f in _profile(api, k, s)["fields"]} for k, s, _ in TEN}
    assert fields[("flow_transmitter", "Thermal Mass")]["Flow Minimum"] == "Nm3/hr"           # normalised flow, not m3/hr
    assert fields[("flow_transmitter", "Thermal Mass")]["Pressure Min"] == "mmWC"
    assert fields[("flow_transmitter", "Ultrasonic Clamp-On")]["Pressure Min"] == "mmWC"
    assert fields[("flow_transmitter", "Ultrasonic Clamp-On")]["Flow Minimum"] == "m3/hr"
    assert fields[("flow_switch", "")]["Minimum Flow"] == "lpm"
    assert fields[("flow_transmitter", "Ultrasonic Parshall Flume")]["Pressure Min"] == "Kg/cm2 g"
    assert fields[("flow_transmitter", "Differential Pressure")]["Instrument Range"] == "mmWC"
    assert fields[("flow_transmitter", "Ultrasonic Parshall Flume")]["Instrument Range"] == "Mtrs"
    assert fields[("level_gauge", "Magnetic")]["Tank / Vessel Height"] == "mtrs"
    assert fields[("level_gauge", "Magnetic")]["Operating Pressure Minimum"] == "Kg/Cm2 g"      # not the config's bar(g)
    assert fields[("level_gauge", "Magnetic")]["Viscosity"] == "cP"
    assert fields[("flow_switch", "")]["Viscosity"] == "Cp"
    # the type's own configuration is not changed by a subtype's units
    assert {f.name: f.unit for f in INSTRUMENT_TYPES["flow_transmitter"].fields}["Pressure Min"] == "kg/cm2"
    assert {f.name: f.unit for f in resolve_fields(INSTRUMENT_TYPES["flow_transmitter"], "Magnetic")}["Pressure Min"] == "kg/cm2"


# ── Test 8 / 9: IODB prefill and missing values ─────────────────────────────
def test_iodb_values_are_prefilled_and_missing_values_stay_blank(api):
    tags = _tags_of(api, "flow_switch")
    g = _generate(api, "flow_switch", prefill=True, tags=tags)
    assert g.status_code == 200, g.text
    ws, headers = _sheet(api)
    col = {h: i + 9 for i, h in enumerate(headers)}
    row1 = {h: ws.cell(6, c).value for h, c in col.items()}
    row2 = {h: ws.cell(7, c).value for h, c in col.items()}
    assert row1["Minimum Flow (lpm)"] is None or row1["Minimum Flow (lpm)"] == "" or True      # flow unit differs (m3/hr vs lpm): not copied
    assert row1["Minimum Flow (lpm)"] in (None, "")
    assert str(row1["Minimum Operating Pressure (Kg/cm2 g)"]).startswith("11")                  # kg/cm2 == Kg/cm2 g: copied as-is
    assert str(row1["Maximum Operating Temperature (°C)"]).startswith("55")
    assert str(row1["Density (kg/m3)"]).startswith("1000") and str(row1["Viscosity (Cp)"]).startswith("1")
    assert row1["Normal Operating Pressure (Kg/cm2 g)"] in (None, "")                           # the IODB has no normal value
    assert row1["Flow Setpoint (lpm)"] in (None, "")                                           # never invented
    assert all(v in (None, "") for v in row2.values())                                         # second tag has no data: all blank
    assert any("Flow Min" in w or "FLOW MIN" in w for w in g.json()["warnings"])


def test_unit_mismatch_is_reported_and_not_converted(api):
    tags = _tags_of(api, "flow_transmitter", "Thermal Mass")
    g = _generate(api, "flow_transmitter", "Thermal Mass", prefill=True, tags=tags)
    assert g.status_code == 200, g.text
    ws, headers = _sheet(api)
    col = {h: i + 9 for i, h in enumerate(headers)}
    assert ws.cell(6, col["Pressure Min (mmWC)"]).value in (None, "")                           # IODB kg/cm2 is not an mmWC value
    assert ws.cell(6, col["Flow Minimum (Nm3/hr)"]).value in (None, "")                         # IODB m3/hr is not Nm3/hr
    assert str(ws.cell(6, col["Temperature Min (°C)"]).value).startswith("25")                    # same unit: copied
    assert any("not copied" in w for w in g.json()["warnings"])
    # a type whose unit matches the IODB does get the values
    tags = _tags_of(api, "flow_transmitter", "Ultrasonic Clamp-On")
    _generate(api, "flow_transmitter", "Ultrasonic Clamp-On", prefill=True, tags=["230-FIT-901"])
    ws, headers = _sheet(api)
    col = {h: i + 9 for i, h in enumerate(headers)}
    assert str(ws.cell(6, col["Flow Minimum (m3/hr)"]).value).startswith("5")
    assert str(ws.cell(6, col["Normal Velocity (m/s)"]).value).startswith("2")
    assert ws.cell(6, col["Minimum Velocity (m/s)"]).value in (None, "")                      # a single IODB value seeds Normal only


def test_no_iodb_values_means_every_process_cell_is_blank(api):
    assert _generate(api, "orifice_plate", prefill=False, tags=_tags_of(api, "orifice_plate")).status_code == 200
    ws, headers = _sheet(api)
    assert all(ws.cell(6, 9 + i).value in (None, "") for i in range(len(headers)))


# ── Test 10: several instrument types in one IODB are handled independently ─
def test_each_type_matches_its_own_tags_and_columns(api):
    seen = {}
    for key, subtype in (("flow_switch", ""), ("differential_pressure_switch", ""), ("orifice_plate", ""),
                         ("pressure_transmitter", "Differential Pressure"), ("level_gauge", "Magnetic"), ("flow_transmitter", "Thermal Mass")):
        seen[key] = (_tags_of(api, key, subtype), [h for h in EXPECTED[(key, subtype)]])
    assert seen["flow_switch"][0] == ["230-FS-101", "230-FS-102"]
    assert seen["differential_pressure_switch"][0] == ["230-PDS-101"]
    assert seen["orifice_plate"][0] == ["230-FE-101"]
    assert seen["level_gauge"][0] == ["230-LG-101"]
    assert "230-PDS-101" not in seen["pressure_transmitter"][0] and "230-PDT-101" in seen["pressure_transmitter"][0]
    assert len({tuple(v[1]) for v in seen.values()}) == len(seen)                                # no two types share one profile


# ── Test 12: regression - the original behaviour is intact ──────────────────
def test_existing_selected_fields_flow_still_works(api):
    tags = _tags_of(api, "flow_switch")
    assert _generate(api, "flow_switch", selected=["Density"], tags=tags).status_code == 200
    ws, headers = _sheet(api)
    assert headers == ["Density (kg/m3)"]
    r = api.get("/api/process-data/instrument-types").json()["instrument_types"]
    keys = [t["key"] for t in r]
    for k in ("level_transmitter", "flow_transmitter", "pressure_gauge", "custom_instrument", "flow_switch", "differential_pressure_switch", "orifice_plate"):
        assert k in keys
    ft = next(t for t in r if t["key"] == "flow_transmitter")
    assert set(ft["verified_subtypes"]) == {"Differential Pressure", "Thermal Mass", "Ultrasonic Clamp-On", "Ultrasonic Parshall Flume"}
    assert api.get("/api/process-data/profile", params={"instrument_type": "nope"}).status_code == 400
    assert api.get("/api/process-data/profile", params={"instrument_type": "flow_switch", "subtype": "x"}).status_code == 400


def test_level_transmitter_selects_only_the_important_parameters_by_default(api):
    """Reported case: every one of the 49 Level Transmitter parameters came up selected."""
    for st in ("", "Guided Wave Radar", "Non-Contact Radar", "Ultrasonic"):
        p = _profile(api, "level_transmitter", st)
        assert p["verified"] and len(p["default_fields"]) == 13 and len(p["fields"]) > 13
        d = set(p["default_fields"])
        assert {"Process Pressure Min", "Process Pressure Max", "Process Temperature Min", "Tank / Vessel Height", "Tank MOC"} <= d
        assert not {"Tank Tag Number", "Tank Type", "Tank / Vessel Diameter", "Instrument Range", "Calibration Range", "Design Flow",
                    "Minimum Level", "Remarks", "Hazardous Area"} & d
    # generate with no selection sent -> only the 13 defaults
    df = _iodb_df()
    g = api.post("/api/process-data/generate", data={"instrument_type": "level_transmitter", "selected_tags": '["x"]'},
                 files={"iodb_file": ("i.xlsx", _iodb_bytes(pd.DataFrame({"TAG NO": ["200-LIT-1"], "EQUIPMENT DESCRIPTION": ["LT"], "P&ID NO.": ["P"],
                                                                         "INSTRUMENT TYPE NAME": ["Level Transmitter"]})))})
    assert g.status_code == 400                                   # 'x' is not a tag
    g = api.post("/api/process-data/generate", data={"instrument_type": "level_transmitter", "selected_tags": '["200-LIT-1"]'},
                 files={"iodb_file": ("i.xlsx", _iodb_bytes(pd.DataFrame({"TAG NO": ["200-LIT-1"], "EQUIPMENT DESCRIPTION": ["LT"], "P&ID NO.": ["P"],
                                                                         "INSTRUMENT TYPE NAME": ["Level Transmitter"]})))})
    assert g.status_code == 200, g.text
    _, headers = _sheet(api)
    assert headers == EXPECTED[("level_transmitter", "")] and len(headers) == 13


def test_iodb_without_type_name_columns_still_matches_by_tag_prefix(api):
    """The 'Column not found ... INSTRUMENT TYPE NAME' warning: tags are then matched on the TAG NO prefix (LIT / LT)."""
    iodb = pd.DataFrame({"TAG NO": ["200-LIT-1", "200-FIT-1"], "EQUIPMENT DESCRIPTION": ["a", "b"], "P&ID NO.": ["P", "P"]})
    r = api.post("/api/process-data/match-tags", data={"instrument_type": "level_transmitter"}, files={"file": ("i.xlsx", _iodb_bytes(iodb))})
    assert r.status_code == 200
    assert [t["tag_no"] for t in r.json()["matched_tags"]] == ["200-LIT-1"]
    assert any("INSTRUMENT TYPE NAME" in w for w in r.json()["warnings"])
