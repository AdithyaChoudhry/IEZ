"""Process Data Requisition: the selected SUBTYPE decides which tags are shown (not just the broad type), unresolved records
are reviewed and never guessed, and the All Instrument Types mode detects, groups and generates every supported type."""
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import process_data_matcher as M  # noqa: E402
from utils.process_data_subtypes import classify, subtype_columns  # noqa: E402


def iodb(rows, extra=None):
    cols = ["TAG NO", "EQUIPMENT DESCRIPTION", "P&ID NO.", "INSTRUMENT TYPE NAME", "INSTRUMENT MEASURING TYPE", "SERVICE", "LINE",
            "EQUIPMENT NO", "DENSITY (kg/m3)", "TEMPERATURE MIN (deg C)", "TEMPERATURE MAX (deg C)", "PRESSURE MIN (kg/cm2)",
            "PRESSURE MAX (kg/cm2)"] + list(extra or [])
    data = []
    for r in rows:
        tag, tname = r[0], r[1]
        rest = list(r[2:])
        data.append([tag, f"{tname} Service Point", f"P-{tag}", tname, "level", "SVC", f"100-W-{tag}", f"E-{tag}", None, None, None, None, None] + rest)
    return pd.DataFrame(data, columns=cols)


def xlsx(df):
    b = io.BytesIO()
    df.to_excel(b, index=False)
    return b.getvalue()


LEVELS = [("LT-001", "Non-Contact Radar Level Transmitter"), ("LT-002", "Ultrasonic Level Transmitter"),
          ("LT-003", "Guided Wave Radar Level Transmitter"), ("LT-004", "Submersible Level Transmitter"),
          ("LT-005", "Non-Contact Radar Level Transmitter"), ("LT-006", "Radar Level Transmitter"),            # generic radar
          ("LT-007", "Level Transmitter")]                                                                      # no technology at all


def tags(rows):
    return [r["tag_no"] for r in rows]


# ── Requirement 1: subtype filtering ─────────────────────────────────────────
def test_non_contact_radar_shows_only_non_contact_radar_tags():
    df = iodb(LEVELS)
    r = M.match_tags_detailed(df, "level_transmitter", "Non-Contact Radar")
    assert tags(r["matched"]) == ["LT-001", "LT-005"]                       # exactly the two verified ones
    assert tags(r["unresolved"]) == ["LT-006", "LT-007"]                    # generic radar / no technology: reviewed, never guessed
    assert r["excluded"] == {"Ultrasonic": 1, "Guided Wave Radar": 1, "Submersible": 1}


@pytest.mark.parametrize("subtype,expected", [("Guided Wave Radar", ["LT-003"]), ("Ultrasonic", ["LT-002"]), ("Non-Contact Radar", ["LT-001", "LT-005"]),
                                              ("DP Type (Open Tank)", []), ("DP Type (Pressurized Tank)", [])])
def test_each_level_subtype_shows_only_its_own_tags(subtype, expected):
    assert tags(M.match_tags_detailed(iodb(LEVELS), "level_transmitter", subtype)["matched"]) == expected


def test_radar_wording_alone_never_decides_between_non_contact_and_guided_wave():
    c = classify("level_transmitter", {"INSTRUMENT TYPE NAME": "Radar Level Transmitter"}, subtype_columns(["INSTRUMENT TYPE NAME"]))
    assert c["subtype"] is None and "non-contact or guided wave" in c["reason"]
    # the tag prefix decides nothing
    df = iodb([("LIT-1", "Level Transmitter")])
    assert tags(M.match_tags_detailed(df, "level_transmitter", "Non-Contact Radar")["matched"]) == []


def test_an_explicit_subtype_column_is_the_first_evidence():
    df = iodb([("LT-1", "Radar Level Transmitter", "Non-Contact Radar"), ("LT-2", "Radar Level Transmitter", "Guided Wave Radar"),
               ("LT-3", "Radar Level Transmitter", "")], extra=["INSTRUMENT SUBTYPE"])
    assert tags(M.match_tags_detailed(df, "level_transmitter", "Non-Contact Radar")["matched"]) == ["LT-1"]
    assert tags(M.match_tags_detailed(df, "level_transmitter", "Guided Wave Radar")["matched"]) == ["LT-2"]
    assert tags(M.match_tags_detailed(df, "level_transmitter", "Guided Wave Radar")["unresolved"]) == ["LT-3"]


def test_explicit_subtype_column_outranks_the_description_and_two_names_in_one_cell_are_unresolved():
    df = iodb([("LT-1", "Ultrasonic Level Transmitter", "Guided Wave Radar")], extra=["INSTRUMENT SUBTYPE"])
    assert tags(M.match_tags_detailed(df, "level_transmitter", "Guided Wave Radar")["matched"]) == ["LT-1"]       # the explicit column wins
    assert tags(M.match_tags_detailed(df, "level_transmitter", "Ultrasonic")["matched"]) == []                     # never in two subtypes
    both = iodb([("LT-2", "Non-Contact Radar and Guided Wave Radar Level Transmitter")])
    r = M.match_tags_detailed(both, "level_transmitter", "Non-Contact Radar")
    assert tags(r["matched"]) == [] and tags(r["unresolved"]) == ["LT-2"] and "more than one subtype" in r["unresolved"][0]["reason"]


def test_the_same_rule_works_for_every_family_with_subtypes():
    flow = iodb([("F-1", "Magnetic Flow Transmitter"), ("F-2", "Coriolis Flow Transmitter"), ("F-3", "Flow Indicating Transmitter"),
                 ("F-4", "Ultrasonic Clamp On Flow Transmitter"), ("F-5", "Thermal Mass Flow Transmitter"), ("F-6", "Vortex Flow Transmitter")])
    assert tags(M.match_tags_detailed(flow, "flow_transmitter", "Magnetic")["matched"]) == ["F-1"]
    assert tags(M.match_tags_detailed(flow, "flow_transmitter", "Ultrasonic Clamp-On")["matched"]) == ["F-4"]
    assert tags(M.match_tags_detailed(flow, "flow_transmitter", "Thermal Mass")["matched"]) == ["F-5"]
    assert tags(M.match_tags_detailed(flow, "flow_transmitter", "Magnetic")["unresolved"]) == ["F-3"]            # generic: reviewed
    pt = iodb([("P-1", "Pressure Indicating Transmitter"), ("P-2", "Differential Pressure Transmitter")])
    assert tags(M.match_tags_detailed(pt, "pressure_transmitter", "Differential Pressure")["matched"]) == ["P-2"]    # not also "Standard"
    assert tags(M.match_tags_detailed(pt, "pressure_transmitter", "Standard")["matched"]) == ["P-1"]
    lg = iodb([("G-1", "Magnetic Level Gauge"), ("G-2", "Reflex Level Gauge"), ("G-3", "Level Gauge")])
    assert tags(M.match_tags_detailed(lg, "level_gauge", "Reflex")["matched"]) == ["G-2"]
    assert tags(M.match_tags_detailed(lg, "level_gauge", "Reflex")["unresolved"]) == ["G-3"]
    tt = iodb([("T-1", "RTD Temperature Transmitter"), ("T-2", "Thermocouple Temperature Transmitter"), ("T-3", "Temperature Indicating Transmitter")])
    assert tags(M.match_tags_detailed(tt, "temperature_transmitter", "RTD")["matched"]) == ["T-1"]


def test_without_a_subtype_the_behaviour_is_unchanged():
    r = M.match_tags_detailed(iodb(LEVELS), "level_transmitter", None)
    assert len(r["matched"]) == 7 and not r["unresolved"] and not r["filtered"]


# ── API ──────────────────────────────────────────────────────────────────────
@pytest.fixture()
def api():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import process_data
    process_data._detect_cache.clear()
    app = FastAPI()
    app.include_router(process_data.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, username="alice")
    return TestClient(app)


def match(api, df, type_key, subtype=None):
    data = {"instrument_type": type_key, **({"subtype": subtype} if subtype else {})}
    return api.post("/api/process-data/match-tags", data=data, files={"file": ("i.xlsx", xlsx(df))})


def test_match_tags_endpoint_returns_only_the_selected_subtype_and_the_review_list(api):
    r = match(api, iodb(LEVELS), "level_transmitter", "Non-Contact Radar")
    assert r.status_code == 200, r.text
    b = r.json()
    assert [t["tag_no"] for t in b["matched_tags"]] == ["LT-001", "LT-005"] and b["tag_count"] == 2 and b["subtype"] == "Non-Contact Radar"
    assert [t["tag_no"] for t in b["unresolved_tags"]] == ["LT-006", "LT-007"] and all(t["reason"] for t in b["unresolved_tags"])
    assert b["excluded_counts"]["Ultrasonic"] == 1
    assert any("not placed in" in w for w in b["warnings"])
    # a subtype with nothing established still answers (200) - the records are offered for review
    r = match(api, iodb(LEVELS), "level_transmitter", "DP Type (Open Tank)")
    assert r.status_code == 200 and r.json()["tag_count"] == 0 and r.json()["unresolved_tags"]
    # identification columns are the IODB's own values
    t = match(api, iodb(LEVELS), "level_transmitter", "Ultrasonic").json()["matched_tags"][0]
    assert (t["tag_no"], t["equipment_description"], t["pid_no"], t["line"], t["line_size"]) == (
        "LT-002", "Ultrasonic Level Transmitter Service Point", "P-LT-002", "100-W-LT-002", "100 mm")


def test_generate_refuses_tags_of_another_subtype_but_accepts_explicit_review_picks(api):
    df = iodb(LEVELS)
    def gen(selected, subtype="Non-Contact Radar"):
        return api.post("/api/process-data/generate", data={"instrument_type": "level_transmitter", "subtype": subtype,
                        "selected_tags": json.dumps(selected), "project_id": "P1"}, files={"iodb_file": ("i.xlsx", xlsx(df))})
    r = gen(["LT-001", "LT-002"])                                    # LT-002 is ultrasonic
    assert r.status_code == 400 and "LT-002" in r.json()["detail"]
    assert gen(["LT-001", "LT-005"]).status_code == 200
    ws = load_workbook(io.BytesIO(api.get("/api/process-data/download").content))["PROCESS DATA REQUISITION"]
    assert [row[1].value for row in ws.iter_rows(min_row=6, max_row=ws.max_row)] == ["LT-001", "LT-005"]
    assert gen(["LT-001", "LT-006"]).status_code == 200              # LT-006 (generic radar) added explicitly by the engineer


# ── Requirement 2: All Instrument Types ──────────────────────────────────────
MIX = [("LT-001", "Non-Contact Radar Level Transmitter"), ("LT-002", "Ultrasonic Level Transmitter"), ("LT-003", "Radar Level Transmitter"),
       ("PT-001", "Pressure Indicating Transmitter"), ("PT-002", "Pressure Indicating Transmitter"), ("PDT-001", "Differential Pressure Transmitter"),
       ("FS-001", "Flow Switch"), ("FS-002", "Flow Switch"), ("TT-001", "Temperature Indicating Transmitter"),
       ("M-001", "Motor - DOL"), ("M-002", "Motor - DOL"), ("XV-001", "Pneumatic On/Off Valve"), ("PT-001", "Pressure Indicating Transmitter")]   # PT-001 twice


def detect(api, df):
    r = api.post("/api/process-data/detect-types", files={"file": ("i.xlsx", xlsx(df))})
    assert r.status_code == 200, r.text
    return r.json()


def test_all_types_detects_groups_counts_and_reports_what_it_cannot_classify(api):
    d = detect(api, iodb(MIX))
    groups = {g["label"]: g for g in d["groups"]}
    assert groups["Level Transmitter - Non-Contact Radar"]["count"] == 1 and groups["Level Transmitter - Ultrasonic"]["count"] == 1
    assert groups["Pressure Transmitter - Standard"]["count"] == 2                          # PT-001 listed twice counts once
    assert groups["Pressure Transmitter - Differential Pressure"]["count"] == 1 and groups["Flow Switch"]["count"] == 2
    review = [g for g in d["groups"] if g["needs_review"]]
    assert {g["type_key"] for g in review} == {"level_transmitter", "temperature_transmitter"} and all(g["reason"] or g["tags"][0]["reason"] for g in review)
    assert d["eligible_tags"] == 1 + 1 + 2 + 1 + 2 and d["review_tags"] == 2 and d["types_found"] == 3
    assert {u["name"]: u["count"] for u in d["unsupported"]} == {"Motor - DOL": 2, "Pneumatic On/Off Valve": 1}      # never forced into a type
    assert all(u["reason"] for u in d["unsupported"])
    assert not any(t["tag_no"] in ("M-001", "XV-001") for g in d["groups"] for t in g["tags"])


def test_all_types_generates_one_workbook_with_a_sheet_and_its_own_parameters_per_type(api):
    df = iodb(MIX)
    d = detect(api, df)
    picks = [{"key": g["key"], "tags": [t["tag_no"] for t in g["tags"]], "selected_fields": None} for g in d["groups"] if not g["needs_review"]]
    r = api.post("/api/process-data/generate-all", data={"selections": json.dumps(picks), "project_id": "P1"}, files={"iodb_file": ("i.xlsx", xlsx(df))})
    assert r.status_code == 200, r.text
    wb = load_workbook(io.BytesIO(api.get("/api/process-data/download").content))
    sheets = wb.sheetnames
    assert sheets[-2:] == ["INSTRUCTIONS", "FIELD DEFINITIONS"] and len(sheets) == len(picks) + 2
    assert all(len(s) <= 31 for s in sheets) and len(set(s.lower() for s in sheets)) == len(sheets)
    by_label = {}
    for ws in wb.worksheets[:-2]:
        hdr = [c.value for c in ws[5]][8:]
        by_label[ws["A2"].value] = (ws.title, hdr, [row[1].value for row in ws.iter_rows(min_row=6, max_row=ws.max_row)])
    fs = next(v for k, v in by_label.items() if k.startswith("Instrument Type: Flow Switch"))
    pt = next(v for k, v in by_label.items() if "Pressure Transmitter (Standard)" in k)
    assert fs[2] == ["FS-001", "FS-002"] and "Flow Setpoint (lpm)" in fs[1] and "Flow Setpoint (lpm)" not in pt[1]    # each type keeps its own columns
    assert pt[2] == ["PT-001", "PT-002"] and "Normal Operating Pressure (Kg/cm2 g)" in pt[1] and "Viscosity (Cp)" not in pt[1]
    assert not any(t in ("M-001", "XV-001", "LT-003", "TT-001") for _t, _h, tg in by_label.values() for t in tg)       # only the selected groups / tags
    defs = wb["FIELD DEFINITIONS"]
    assert defs["A1"].value == "Instrument Type" and {defs.cell(r, 1).value for r in range(2, defs.max_row + 1)} >= {"Flow Switch", "Level Transmitter - Ultrasonic"}


def test_all_types_deselecting_a_type_or_a_tag_and_changing_one_types_parameters(api):
    df = iodb(MIX)
    d = detect(api, df)
    g = {x["label"]: x for x in d["groups"]}
    picks = [{"key": g["Flow Switch"]["key"], "tags": ["FS-002"], "selected_fields": ["Density", "Viscosity"]},        # one tag, own columns
             {"key": g["Pressure Transmitter - Standard"]["key"], "tags": ["PT-001", "PT-002"], "selected_fields": None}]
    r = api.post("/api/process-data/generate-all", data={"selections": json.dumps(picks)}, files={"iodb_file": ("i.xlsx", xlsx(df))})
    assert r.status_code == 200, r.text
    wb = load_workbook(io.BytesIO(api.get("/api/process-data/download").content))
    assert len(wb.sheetnames) == 4                                                                                      # 2 sheets + 2 info sheets
    ws = {s.title: s for s in wb.worksheets}
    fs = next(s for s in wb.worksheets if "Flow Switch" in s["A2"].value)
    pt = next(s for s in wb.worksheets[:-2] if "Pressure Transmitter" in s["A2"].value)
    assert [c.value for c in fs[5]][8:] == ["Density (kg/m3)", "Viscosity (Cp)"] and [row[1].value for row in fs.iter_rows(min_row=6, max_row=fs.max_row)] == ["FS-002"]
    assert "Viscosity (Cp)" not in [c.value for c in pt[5]]                                                              # adding it to one type adds it to no other


def test_all_types_refuses_foreign_tags_unknown_groups_and_unknown_columns(api):
    df = iodb(MIX)
    d = detect(api, df)
    g = {x["label"]: x for x in d["groups"]}
    def go(picks):
        return api.post("/api/process-data/generate-all", data={"selections": json.dumps(picks)}, files={"iodb_file": ("i.xlsx", xlsx(df))})
    assert go([{"key": g["Flow Switch"]["key"], "tags": ["PT-001"]}]).status_code == 400                                 # PT-001 is not a flow switch
    assert go([{"key": "nope|x|", "tags": ["FS-001"]}]).status_code == 400
    assert go([{"key": g["Flow Switch"]["key"], "tags": ["FS-001"], "selected_fields": ["Switching Setpoint"]}]).status_code == 400
    assert go([]).status_code == 400
    assert go([{"key": g["Flow Switch"]["key"], "tags": ["FS-001"]}, {"key": g["Flow Switch"]["key"], "tags": ["FS-002"]}]).status_code == 400


def test_all_types_is_fast_on_a_large_iodb(api):
    import time
    big = iodb([(f"PT-{i:04d}", "Pressure Indicating Transmitter") for i in range(3000)] + [(f"FS-{i:04d}", "Flow Switch") for i in range(1000)])
    t = time.time()
    d = detect(api, big)
    assert time.time() - t < 8 and d["eligible_tags"] == 4000


def test_sheet_names_stay_unique_and_valid():
    from utils.process_data_generator import _sheet_title
    used = set()
    names = [_sheet_title(x, used) for x in ["Level Transmitter - Non-Contact Radar", "Level Transmitter - Non-Contact Radar",
                                             "Pressure Transmitter - Differential Pressure", "A/B:C*D?[E]"]]
    assert all(len(n) <= 31 for n in names) and len({n.lower() for n in names}) == 4 and not any(ch in n for n in names for ch in "[]:*?/\\")
