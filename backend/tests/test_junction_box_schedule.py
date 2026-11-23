"""Junction Box Schedule Generator (Cable Schedule sub-generator): the generated Cable Schedule is the only input, junction
boxes / instruments / cables are counted uniquely, terminals come from the termination rows or from the engineer, spare
terminals and spare % are calculated, the standard template is filled, and the delivered workbook is exactly COVERSHEET +
JB_SCHEDULE with no broken formula."""
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.database as database
import app.models.deliverable_cover  # noqa: F401
import app.models.mdl  # noqa: F401
from app.deps import get_current_user, get_db

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_mdl import make_mdl  # noqa: E402
from utils import junction_box_schedule as J  # noqa: E402

PID, OTHER = "PRJ-JB", "PRJ-OTHER"
HEADERS = ["SL. No.  ", "TAG NUMBER", "EQUIPMENT DESCRIPTION", "SIGNAL I/O TYPE", "INSTRUMENT TO JB CABLE TAG NO",
           "INSTRUMENT TO JB CABLE", "BRANCH CABLE LENGTH", "INSTRUMENT SIDE GLAND SIZE", "INSTRUMENT SIDE GLAND QTY",
           "FERRULE AT INSTRUMENT SIDE\n(+) / (-)", "JB TAG No.", "TB DETAILS AT JB", "JB SIDE GLAND SIZE", "JB SIDE GLAND QTY",
           "MAIN CABLE TAG NUMBER", "MAIN CABLE TYPE", "MAIN CABLE LENGTH(Mtrs)", "JB END GLAND SIZE", "PANEL END GLAND SIZE", "Remarks"]

# tag, io, jb, branch cable tag, branch type, main cable tag, main type, terminals
BLOCKS = [
    ("PT-101", "AI", "JB-001", "IC-1", "1PX1.5 Sqmm", "MC-1", "12PX1.5 Sqmm", [1, 2, 3]),
    ("PT-102", "AI", "JB-001", "IC-2", "1PX1.5 Sqmm", "MC-1", "12PX1.5 Sqmm", [4, 5, 6]),
    ("LT-101", "AI", "JB-001", "IC-3", "1PX1.5 Sqmm", "MC-1", "12PX1.5 Sqmm", [7, 8, 9]),
    ("FT-101", "AI", "JB-001", "IC-4", "1PX1.5 Sqmm", "MC-1", "12PX1.5 Sqmm", [10, 11, 12]),
    ("FT-101", "AI", "JB-001", "IC-4B", "1PX1.5 Sqmm", "MC-1", "12PX1.5 Sqmm", [13, 14, 15]),      # 2nd signal of the same instrument
    ("TT-101", "AI", "JB-001", "IC-5", "1PX1.5 Sqmm", "MC-1", "12PX1.5 Sqmm", [16, 17, 18]),
    ("SPARE", "", "JB-001", "", "", "", "", [19, 20, 21]),                                           # spare terminals: not an instrument
    ("PT-201", "AI", "jb-002", "IC-6", "1PX1.5 Sqmm", "MC-2", "8PX1.5 Sqmm", [1, 2, 3]),            # written in lower case
    ("TT-201", "AI", "JB-002", "IC-7", "1PX1.5 Sqmm", "MC-3", "8PX1.5 Sqmm", [4, 5, 6]),            # a second main cable
    ("XV-301", "DO", "JB-003", "IC-8", "1PX1.5 Sqmm", "MC-4", "4PX1.5 Sqmm", [1, 2]),
    ("PS-301", "DI", "JB-003", "IC-9", "1PX1.5 Sqmm", "MC-4", "4PX1.5 Sqmm", [3, 4]),
    ("PS-302", "DI", "JB-004", "IC-10", "1PX1.5 Sqmm", "MC-5", "4PX1.5 Sqmm", ["TBA", "TBA"]),      # terminals not assigned yet
    ("SV-401", "DO", "XXXX-SMB-001", "NA", "NA", "MC-6", "24C x 1.5 mm2", [1]),
    ("SV-402", "DO", "XXXX-SMB-001", "NA", "NA", "MC-6", "24C x 1.5 mm2", [2]),
    ("SV-403", "DO", "XXXX-SMB-001", "NA", "NA", "MC-6", "24C x 1.5 mm2", [3]),
]


def schedule_bytes(blocks=BLOCKS, extra_sheet=True):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cable Schedule -INST"
    ws["A3"], ws["D3"] = "PROJECT", "XXXX"
    for c, h in enumerate(HEADERS, 1):
        ws.cell(7, c).value = h
    r = 9
    for i, (tag, io_t, jb, btag, btype, mtag, mtype, terms) in enumerate(blocks, 1):
        top = r
        vals = {1: str(i), 2: tag, 3: "desc " + tag, 4: io_t, 5: btag, 6: btype, 7: "=23+2", 8: "M20x1.5", 9: "1", 11: jb,
                13: f"=H{top}", 14: f"=I{top}", 15: mtag, 16: mtype, 17: "=98+210", 18: '1 1/4" NPT', 19: "M25x1.5"}
        for c, v in vals.items():
            ws.cell(top, c).value = v
        for k, t in enumerate(terms):
            ws.cell(top + k, 12).value = t
        if len(terms) > 1:
            for c in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 13, 14, 15, 16, 17, 18, 19):
                ws.merge_cells(start_row=top, start_column=c, end_row=top + len(terms) - 1, end_column=c)
        r += len(terms) + 1
    if extra_sheet:
        ws2 = wb.create_sheet("CABLE SUMMARY")
        ws2["A1"] = "SUMMARY"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def iodb_bytes():
    df = pd.DataFrame({"TAG NO": ["PT-101", "PT-102", "PT-201", "XV-301", "PS-301"],
                       "JUNCTION BOX TAG NO.": ["JB-001", "JB-001", "JB-002", "JB-003", "JB-003"],
                       "IS/NIS TYPE": ["NIS", "NIS", "IS", "NIS", "IS"],
                       "AREA CLASSIFICATION": ["SAFE", "SAFE", "ZONE 2", "SAFE", "SAFE"],
                       "LOCATION": ["INLET WORKS"] * 5})
    b = io.BytesIO()
    df.to_excel(b, index=False)
    return b.getvalue()


@pytest.fixture()
def client(engine, db, monkeypatch):
    from app.routers import cable_schedule, coversheet_mdl, deliverables, junction_box_schedule
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(deliverables, "SessionLocal", sessionmaker(bind=engine))
    deliverables._outputs.clear()
    cable_schedule._generated.clear()
    junction_box_schedule._cache.clear()
    junction_box_schedule._outputs.clear()
    app = FastAPI()
    for r in (coversheet_mdl.router, deliverables.router, cable_schedule.router, junction_box_schedule.router):
        app.include_router(r, prefix="/api")
    user = SimpleNamespace(id=5, username="alice", email="a@x")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    c = TestClient(app)
    c.user = user
    yield c
    cable_schedule._generated.clear()


def put_schedule(user_id=5, project=PID, gid="g1", blocks=BLOCKS, iodb=True):
    from app.routers import cable_schedule
    cable_schedule._generated[(user_id, project)] = {
        "id": gid, "filename": "Cable_Schedule_R0.xlsx", "generated_at": "2026-11-24T10:00:00", "project_id": project,
        "sheets": ["Cable Schedule -INST"], "iodb_filename": "IODB.xlsx", "selected_jbs": None,
        "bytes": schedule_bytes(blocks), "iodb_bytes": iodb_bytes() if iodb else b""}


def add_cover(c, doc="PC286-10P195-J0007-001", name="Junction Box Schedule for New WWTP", project=PID):
    r = c.post(f"/api/projects/{project}/coversheet/mdl/upload", files={"file": ("MDL.xlsx", make_mdl([(1, "Instrumentation", doc, name, "A", "")]))},
               data={"confirm_replace": "true"})
    assert r.status_code == 200, r.text
    r = c.put("/api/deliverables/cover", json={"project_id": project, "doc_type": "jb_schedule", "sub_key": "",
              "project_info": {"client": "GAIL", "pmc": "PMC", "contractor": "WABAG", "project_description": "NEW WWTP"},
              "revisions": [{"rev_no": "R0", "date": "2026-11-24", "description": "ISSUED FOR REVIEW", "prepared_by": "AB",
                             "checked_by": "CD", "approved_by": "EF"}]})
    assert r.status_code == 200, r.text


def analyze(c, **kw):
    body = {"project_id": PID, **kw}
    r = c.post("/api/cable-schedule/jb/analyze", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def jb_of(data, jb_no):
    return next(j for j in data["analysis"]["jbs"] if j["jb_no"] == jb_no)


def result_of(data, jb_no):
    return next(r for r in data["evaluation"]["results"] if r["jb_no"] == jb_no)


# ── Test 1: retrieval + isolation ────────────────────────────────────────────
def test_uses_the_users_generated_schedule_only(client):
    r = client.post("/api/cable-schedule/jb/analyze", json={"project_id": PID})
    assert r.status_code == 404 and r.json()["detail"] == "No generated Cable Schedule is available. Please generate the Cable Schedule first."
    put_schedule(user_id=99)                                           # another user's schedule
    assert client.post("/api/cable-schedule/jb/analyze", json={"project_id": PID}).status_code == 404
    put_schedule(project=OTHER)                                        # another project's schedule
    assert client.post("/api/cable-schedule/jb/analyze", json={"project_id": PID}).status_code == 404
    put_schedule()
    d = analyze(client)
    assert d["generated"]["filename"] == "Cable_Schedule_R0.xlsx" and d["generated"]["id"] == "g1"
    r = client.post("/api/cable-schedule/jb/analyze", json={"project_id": PID, "generated_id": "old"})
    assert r.status_code == 409 and "newer Cable Schedule" in r.json()["detail"]
    st = client.get("/api/cable-schedule/jb/status", params={"project_id": PID}).json()
    assert st["generated"]["available"] and st["design"] == {"max_instruments": 10, "max_main_cables": 1, "design_spare_pct": 0.2}


# ── Tests 2-5: identification and counting ───────────────────────────────────
def test_unique_junction_boxes_and_instrument_count(client):
    put_schedule()
    d = analyze(client)
    assert [j["jb_no"] for j in d["analysis"]["jbs"]] == ["JB-001", "JB-002", "JB-003", "JB-004", "XXXX-SMB-001"]
    assert len({j["key"] for j in d["analysis"]["jbs"]}) == len(d["analysis"]["jbs"])            # no JB twice
    j1 = jb_of(d, "JB-001")
    assert j1["instrument_count"] == 5 and j1["instruments"] == ["PT-101", "PT-102", "LT-101", "FT-101", "TT-101"]   # FT-101 once, SPARE not counted
    assert j1["spare_rows"] == 1
    assert d["analysis"]["instrument_total"] == 13
    j2 = next(j for j in d["analysis"]["jbs"] if j["key"] == "JB-002")
    assert j2["instrument_count"] == 2


def test_branch_and_main_cables_are_unique_physical_cables(client):
    put_schedule()
    d = analyze(client)
    j1 = jb_of(d, "JB-001")
    assert j1["branch_cable_count"] == 6 and "IC-4B" in j1["branch_cables"]        # FT-101 has two cables; 5 instruments != 6 cables
    assert j1["main_cable_count"] == 1 and j1["main_cables"] == [{"tag": "MC-1", "type": "12PX1.5 Sqmm"}]   # MC-1 repeats on 6 rows
    j2 = next(j for j in d["analysis"]["jbs"] if j["key"] == "JB-002")
    assert j2["main_cable_count"] == 2 and [m["tag"] for m in j2["main_cables"]] == ["MC-2", "MC-3"]
    res = result_of(d, "JB-002")
    assert res["jb_no"] == "JB-002"                                                 # shown in capitals (two spellings in the schedule)
    assert res["row"]["main_cable_no"] == "MC-2, MC-3"                              # every cable number kept, none dropped
    assert res["row"]["main_cable_type"] == "8PX1.5 Sqmm"                          # not in the template list: kept as written
    assert any("main cables exceed" in w for w in res["warnings"])


def test_same_jb_written_two_ways_is_merged_and_reported(client):
    put_schedule()
    d = analyze(client)
    j2 = next(j for j in d["analysis"]["jbs"] if j["key"] == "JB-002")
    assert any("written in 2 ways" in w for w in j2["warnings"])


# ── Tests 6-11: capacity, terminals, spare, missing inputs ───────────────────
def cfg(**kw):
    base = {"category": "AJB", "isnis": "NIS", "terminal_capacity": 40}
    base.update(kw)
    return base


def validate(c, jbs, **kw):
    r = c.post("/api/cable-schedule/jb/validate", json={"project_id": PID, "jbs": jbs, **kw})
    assert r.status_code == 200, r.text
    return r.json()["evaluation"]


def test_terminals_used_from_the_termination_rows_and_spare_calculation(client):
    put_schedule()
    ev = validate(client, {"JB-001": cfg(terminal_capacity=60)})
    r = next(x for x in ev["results"] if x["jb_no"] == "JB-001")
    assert r["row"]["terminals_used"] == 18 and r["source"]["terminals_used"].startswith("terminal rows")   # 6 signal blocks x 3 terminals; spare rows excluded
    assert r["row"]["spare_terminals"] == 42 and r["row"]["spare_pct"] == 42 / 60                          # Spare = Capacity - Used; % = Spare / Capacity
    assert r["status"] == "Ready"


def test_different_capacities_per_junction_box_and_whole_number_rule(client):
    put_schedule()
    ev = validate(client, {"JB-001": cfg(terminal_capacity=60), "JB-002": cfg(terminal_capacity=20), "JB-003": cfg(terminal_capacity=30, category="DJB")})
    cap = {r["jb_no"]: r["row"]["terminal_capacity"] for r in ev["results"]}
    assert cap["JB-001"] == 60 and cap["JB-003"] == 30 and cap[next(k for k in cap if k.lower() == "jb-002")] == 20
    for bad in (0, -5, 12.5, "abc"):
        ev = validate(client, {"JB-001": cfg(terminal_capacity=bad)})
        r = next(x for x in ev["results"] if x["jb_no"] == "JB-001")
        assert r["row"]["terminal_capacity"] is None and r["errors"] and r["status"] == "Error"
    # no capacity assumed: nothing entered -> input required, never a default
    ev = validate(client, {})
    r = next(x for x in ev["results"] if x["jb_no"] == "JB-001")
    assert r["status"] == "Input Required" and "TERMINAL CAPACITY / WAYS" in r["missing_generation"] and r["row"]["terminal_capacity"] is None


def test_capacity_exceeded_is_reported_and_blocks_generation(client):
    put_schedule()
    add_cover(client)
    ev = validate(client, {"JB-001": cfg(terminal_capacity=12)})
    r = next(x for x in ev["results"] if x["jb_no"] == "JB-001")
    assert J.EXCEEDED in r["errors"] and r["row"]["spare_terminals"] is None and r["status"] == "Error"
    g = client.post("/api/cable-schedule/jb/generate", json={"project_id": PID, "jbs": {"JB-001": cfg(terminal_capacity=12)}})
    assert g.status_code == 422 and J.EXCEEDED in str(g.json())


def test_terminals_not_in_the_schedule_are_asked_and_user_values_are_marked(client):
    put_schedule()
    ev = validate(client, {"JB-004": cfg(terminal_capacity=20)})
    r = next(x for x in ev["results"] if x["jb_no"] == "JB-004")
    assert r["row"]["terminals_used"] is None and "TERMINALS USED" in r["missing_generation"] and r["status"] == "Input Required"
    ev = validate(client, {"JB-004": cfg(terminal_capacity=20, terminals_method="per_instrument", terminals_per_instrument=2)})
    r = next(x for x in ev["results"] if x["jb_no"] == "JB-004")
    assert r["row"]["terminals_used"] == 2 and r["row"]["spare_terminals"] == 18 and "user-confirmed" in r["source"]["terminals_used"]
    ev = validate(client, {"JB-004": cfg(terminal_capacity=20, terminals_method="manual", terminals_manual=7)})
    r = next(x for x in ev["results"] if x["jb_no"] == "JB-004")
    assert r["row"]["terminals_used"] == 7 and r["row"]["spare_pct"] == 13 / 20
    # a user value that conflicts with the source termination data is reported, not silently chosen
    ev = validate(client, {"JB-001": cfg(terminal_capacity=60, terminals_method="manual", terminals_manual=10)})
    r = next(x for x in ev["results"] if x["jb_no"] == "JB-001")
    assert r["row"]["terminals_used"] == 10 and any("differ from the termination data" in w for w in r["warnings"])


def test_smb_uses_ways_minus_instruments(client):
    put_schedule()
    d = analyze(client)
    res = result_of(d, "XXXX-SMB-001")
    assert res["row"]["category"] == "SMB"                                                  # from the JB tag, shown as a suggestion source
    ev = validate(client, {"XXXX-SMB-001": {"category": "SMB", "terminal_capacity": 12}})
    r = next(x for x in ev["results"] if x["jb_no"] == "XXXX-SMB-001")
    assert r["row"]["terminals_used"] == 3 and r["row"]["spare_terminals"] == 9 and r["row"]["spare_pct"] == 0.75


def test_category_is_suggested_from_signal_types_but_mixed_signals_are_asked(client):
    put_schedule()
    d = analyze(client)
    assert result_of(d, "JB-001")["row"]["category"] == "AJB" and "analog" in result_of(d, "JB-001")["source"]["category"]
    assert result_of(d, "JB-003")["row"]["category"] == "DJB"                                # DI + DO
    mixed = [("A-1", "AI", "JB-M", "C1", "1P", "M1", "4P", [1, 2, 3]), ("D-1", "DI", "JB-M", "C2", "1P", "M1", "4P", [4, 5])]
    put_schedule(gid="g2", blocks=mixed)
    d = analyze(client)
    r = result_of(d, "JB-M")
    assert r["row"]["category"] == "" and "JB CATEGORY" in r["missing_generation"]


def test_missing_information_is_requested_not_invented(client):
    put_schedule()
    d = analyze(client)
    r = result_of(d, "JB-001")
    for label in ("LOCATION", "DESTINATION PANEL", "ENCLOSURE PROTECTION", "ENCLOSURE MATERIAL", "MAIN CABLE GLAND TYPE", "BRANCH GLAND TYPE"):
        assert label in r["missing_submission"]
    assert r["row"]["location"] == "" and r["row"]["dest_panel"] == "" and r["row"]["branch_gland_type"] == ""       # never TBA / guessed
    assert r["row"]["main_gland_size"] == '1 1/4" NPT' and r["row"]["branch_gland_size"] == "M20"            # from the schedule, template spelling
    assert r["row"]["isnis"] == "" or r["row"]["isnis"] == "NIS"
    assert "IS / NIS" not in r["missing_generation"] or r["row"]["isnis"] == ""


def test_is_and_nis_in_one_box_must_be_resolved_by_the_engineer(client):
    put_schedule()
    d = analyze(client)
    r = result_of(d, "JB-003")                                                              # IODB has IS and NIS on JB-003
    assert r["row"]["isnis"] == "" and "IS / NIS" in r["missing_generation"] and any("never share a box" in w for w in r["warnings"])
    ev = validate(client, {"JB-003": cfg(terminal_capacity=20, isnis="NIS", category="DJB")})
    assert next(x for x in ev["results"] if x["jb_no"] == "JB-003")["status"] == "Ready"


def test_zoned_area_needs_ex_protection(client):
    put_schedule()
    ev = validate(client, {"JB-002": cfg(terminal_capacity=20, protection="WEATHERPROOF (IP66)")})
    r = next(x for x in ev["results"] if x["jb_no"].lower() == "jb-002")
    assert any("not Ex" in e for e in r["errors"]) and r["status"] == "Error"


# ── Tests 12-14: cover sheet, workbook structure, formulas ────────────────────
def ready_configs():
    caps = {"JB-001": 60, "JB-002": 20, "JB-003": 30, "JB-004": 20, "XXXX-SMB-001": 12}
    out = {}
    for jb, cap in caps.items():
        out[jb] = {"terminal_capacity": cap, "category": "SMB" if "SMB" in jb else ("DJB" if jb == "JB-003" else "AJB"), "isnis": "NIS",
                   "location": "NEAR TANK", "dest_panel": "MRC-01", "protection": "WEATHERPROOF (IP66)", "material": "SS316",
                   "branch_gland_type": "SS-316 DOUBLE COMPRESSION", "main_gland_type": "SS-316 DOUBLE COMPRESSION"}
    out["JB-004"].update(terminals_method="per_instrument", terminals_per_instrument=2)
    out["JB-002"]["protection"] = "Ex d"
    return out


def test_cover_sheet_is_optional_the_schedule_downloads_without_it(client):
    put_schedule()
    g = client.post("/api/cable-schedule/jb/generate", json={"project_id": PID, "jbs": ready_configs()})
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["cover"]["applied"] is False and "without a cover sheet" in body["cover"]["message"]
    d = client.get("/api/cable-schedule/jb/download")
    assert d.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(d.content))
    assert wb.sheetnames == ["JB_SCHEDULE"] and J.formula_problems(d.content) == []             # no empty placeholder sheet is left behind
    assert wb["JB_SCHEDULE"]["AD2"].value in (None, "")                                         # no document number is invented
    # another document's cover is never attached: an MDL without a matching document gives the same cover-less schedule
    add_cover(client, name="Instrument Cable Schedule for New WWTP")
    g = client.post("/api/cable-schedule/jb/generate", json={"project_id": PID, "jbs": ready_configs()})
    assert g.status_code == 200 and g.json()["cover"]["applied"] is False
    assert openpyxl.load_workbook(io.BytesIO(client.get("/api/cable-schedule/jb/download").content)).sheetnames == ["JB_SCHEDULE"]
    st = client.get("/api/cable-schedule/jb/status", params={"project_id": PID}).json()
    assert st["cover"]["available"] is False and "cover sheet is not available" in st["cover"]["message"]


def test_final_workbook_is_coversheet_and_jb_schedule_only_without_broken_formulas(client):
    put_schedule()
    add_cover(client)
    g = client.post("/api/cable-schedule/jb/generate", json={"project_id": PID, "jbs": ready_configs()})
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["filename"].startswith("PC286-10P195-J0007-001_R0_Junction_Box_Schedule") and body["cover"]["applied"] and body["cover"]["draft"] is True
    d = client.get("/api/cable-schedule/jb/download")
    assert d.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(d.content))
    assert wb.sheetnames == ["COVERSHEET", "JB_SCHEDULE"]                                    # nothing else, nothing hidden
    assert all(ws.sheet_state == "visible" for ws in wb.worksheets)
    assert J.formula_problems(d.content) == [] and not list(wb.defined_names)
    ws = wb["JB_SCHEDULE"]
    for row in ws.iter_rows():                                                                # no formula depends on a deleted sheet
        for c in row:
            assert not (isinstance(c.value, str) and c.value.startswith("=")), c.coordinate
    headers = [ws.cell(9, c).value for c in range(1, 32)]
    assert headers[0] == "S.NO" and headers[13] == "TERMINAL CAPACITY / WAYS" and headers[26] == "TERMINALS USED" and headers[-1] == "REMARKS"
    assert ws.max_column == 31 and ws.cell(8, 3).value == "JB_NO"                              # helper / check columns AF:AR are gone
    assert ws.max_row == 9 + 5                                                                 # unused template rows removed
    by_jb = {ws.cell(r, 3).value: r for r in range(10, 15)}
    r1 = by_jb["JB-001"]
    assert [ws.cell(r1, c).value for c in (14, 17, 22, 27, 28)] == [60, 6, 1, 18, 42]          # N capacity, Q branch, V main, AA used, AB spare
    assert ws.cell(r1, 29).value == pytest.approx(0.7) and "%" in ws.cell(r1, 29).number_format   # AC stored as a fraction -> 70%, not 7000%
    assert ws.cell(r1, 20).value == "MC-1" and ws.cell(r1, 18).value == "M20"
    smb = by_jb["XXXX-SMB-001"]
    assert ws.cell(smb, 27).value is None and ws.cell(smb, 28).value == 9 and ws.cell(smb, 29).value == 0.75
    assert ws.cell(by_jb["JB-004"], 27).value == 2                                              # user-confirmed terminals per instrument
    assert ws.cell(9, 31).value == "REMARKS" and all(ws.cell(r, 31).value is None for r in range(10, 15))   # heading kept, rows empty
    assert ws.print_area and "$AE$14" in str(ws.print_area) and ws.page_setup.orientation == "landscape"
    assert ws["C1"].value == "NEW WWTP" and ws["AD2"].value == "PC286-10P195-J0007-001" and ws["AD3"].value == "R0"
    assert len(ws.data_validations.dataValidation) >= 5                                        # the lists survive as in-cell drop-downs


def test_submission_readiness_is_reported_without_blocking(client):
    put_schedule()
    add_cover(client)
    jbs = ready_configs()
    jbs["JB-001"].pop("dest_panel")
    g = client.post("/api/cable-schedule/jb/generate", json={"project_id": PID, "jbs": jbs})
    assert g.status_code == 200
    assert g.json()["submission_ready"] is False and "DESTINATION PANEL" in g.json()["missing_for_submission"]["JB-001"]


def test_template_is_the_standard_one_and_loses_nothing_it_needs():
    tpl = (ROOT / "backend/app/templates/junction_box_schedule/JB_SCHEDULE_TEMPLATE.xlsx").read_bytes()
    wb = openpyxl.load_workbook(io.BytesIO(tpl))
    ws = wb["JB_SCHEDULE"]
    assert [ws.cell(9, c).value for c in (1, 3, 14, 27, 28, 29)] == ["S.NO", "JB NO.", "TERMINAL CAPACITY / WAYS", "TERMINALS USED",
                                                                      "SPARE TERMINALS / WAYS", "SPARE %"]
    out = J.build_workbook(tpl, [{"jb_no": "JB-1", "row": {"terminal_capacity": 10, "terminals_used": 4, "spare_terminals": 6, "spare_pct": 0.6,
                                                           "category": "AJB", "terminals_method": "auto"}}], {})
    assert openpyxl.load_workbook(io.BytesIO(out)).sheetnames == ["COVERSHEET", "JB_SCHEDULE"]
    assert J.formula_problems(out) == []


# ── engine details ───────────────────────────────────────────────────────────
def test_template_spellings_and_spare_tag_rules():
    assert J._list_spelling("M20x1.5", J.LISTS["gland_size"]) == "M20"
    assert J._list_spelling("4PX1.0 Sqmm", J.LISTS["cable"]) == "4P x 1.0 mm2"
    assert J._list_spelling("1PX2.5 Sqmm", J.LISTS["cable"]) == "1PX2.5 Sqmm"                # not in the template list: kept as written
    for t in ("SPARE", "spare 2", "NA", "-", "TBA"):
        assert J.is_spare(t)
    assert not J.is_spare("PT-101")
    jb = {"jb_no": "X", "key": "X", "instrument_count": 5, "instruments": [], "branch_cable_count": 0, "branch_cables": [], "main_cable_count": 0,
          "main_cables": [], "branch_gland_sizes": [], "main_gland_sizes": [], "iodb": {}, "warnings": [], "suggest": {},
          "terminals": {"auto_available": True, "count": 10, "highest": 10, "pending_instruments": [], "duplicates": []}}
    r = J.evaluate(jb, {"category": "AJB", "terminal_capacity": 40})
    assert (r["row"]["terminals_used"], r["row"]["spare_terminals"], r["row"]["spare_pct"]) == (10, 30, 0.75)    # the worked example
    r = J.evaluate(jb, {"category": "AJB", "terminal_capacity": 8})
    assert J.EXCEEDED in r["errors"]
