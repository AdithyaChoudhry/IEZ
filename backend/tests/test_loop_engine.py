"""Loop Wiring engine: 42-template selection, FIELD CODE mapping, validation rules, package integrity, API."""
import copy
import io
import sys
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils.loop_engine import analysis as A, fixture as FX, generate as GEN, registry as REG, source as SRC  # noqa: E402

DIR = ROOT / "backend" / "app" / "templates" / "loop_wiring"
TPL = (DIR / "LOOP_TYPICAL_TEMPLATES_FINAL_CORRECTED.xlsx").read_bytes()
IOM = (DIR / "STANDARD_IO_ASSIGNMENT_TEMPLATE_Final.xlsx").read_bytes()


@pytest.fixture(scope="module")
def reg():
    return REG.build_registry(TPL, IOM)


@pytest.fixture(scope="module")
def rows():
    return FX.make_fixture(TPL, IOM)


def run(rows_, reg_):
    return A.analyze(FX.rows_to_source(rows_), reg_, A.read_matrix(IOM))


def loop_rows(rows_, name):
    return [r for r in rows_ if r["LOOP_NAME"] == name]


def issues(an, name):
    return {i.code for l in an.loops if l.name == name for i in l.issues}


# ---- registry / selection ---------------------------------------------------------------------------------------------
def test_library_has_all_42_templates_read_from_the_workbook(reg):
    assert reg.complete and len(reg.templates) == 42 and not reg.missing
    t = reg.templates["6B-M"]
    assert t.sheet_name == "6B-M_MOV_PANEL_SPD" and [s.io_type for s in t.slots] == ["DI"] * 4 + ["DO"] * 3
    assert reg.templates["4A-D"].max_signals == 7 and reg.templates["1A-M"].max_signals == 1
    assert {f.field for f in reg.data_fields} >= {"TAG", "FIELD_CABLE", "JB_TAG", "MC_CABLE", "MARSH_CAB", "MODULE_TAG", "CHANNEL", "PWR_CABLE", "INTERFACE_TAG"}


def test_missing_template_is_reported_as_library_incomplete(reg):
    wb = openpyxl.load_workbook(io.BytesIO(TPL))
    del wb["7C-D_SWITCH_NO_SPD"]
    b = io.BytesIO(); wb.save(b)
    reg2 = REG.build_registry(b.getvalue(), IOM)
    assert reg2.missing == ["7C-D"] and "TEMPLATE LIBRARY INCOMPLETE" in REG.library_error(reg2)
    rows_ = FX.make_loop("SWITCH", "C", "D", FX.example_loops(IOM)["SWITCH"], reg, 1)
    an = run(rows_, reg2)
    assert "TEMPLATE NOT FOUND" in issues(an, rows_[0]["LOOP_NAME"]) and an.loops[0].status == "ERROR"
    assert any(i.code == "TEMPLATE LIBRARY INCOMPLETE" for i in an.global_issues)


def test_all_42_combinations_select_the_right_template(reg):
    out = FX.run_acceptance(TPL, IOM)
    assert [m["result"] for m in out["matrix"]] == ["PASS"] * 42
    assert [t["result"] for t in out["tests"]] == ["PASS"] * 10, out["tests"]
    assert not out["error_loops"] and out["signals"] == 158


@pytest.mark.parametrize("lt,spd,term,expect", [("AI-2W", "A", "M", "1A-M"), ("AI-4W", "B", "M", "2B-M"), ("MOTOR-DOL", "B", "D", "3B-D"), ("MOTOR-VFD", "A", "D", "4A-D"),
                                                 ("PNEU-VALVE", "C", "M", "5C-M"), ("MOV", "A", "M", "6A-M"), ("SWITCH", "B", "D", "7B-D")])
def test_typical_is_loop_type_number_plus_spd_dash_term(reg, lt, spd, term, expect):
    assert reg.typical_code(lt, spd, term) == expect


# ---- grouping / multi-signal ------------------------------------------------------------------------------------------
def test_signals_of_one_loop_name_make_one_loop_with_s1_to_sn(reg, rows):
    an = run(rows, reg)
    mov = next(l for l in an.loops if l.loop_type == "MOV" and l.typical == "6A-M")
    assert len(mov.signals) == 7 and [s.sig for s in mov.signals] == [f"S{i}" for i in range(1, 8)]
    assert [s.io_type for s in mov.signals] == ["DI"] * 4 + ["DO"] * 3
    assert len([l for l in an.loops if l.name == mov.name]) == 1


def test_signal_order_follows_the_source_within_each_io_type(reg):
    base = FX.example_loops(IOM)["MOV"]
    rr = FX.make_loop("MOV", "B", "M", base, reg, 3)
    rr[0], rr[1] = rr[1], rr[0]            # swap the first two DI rows
    an = run(rr, reg)
    L = an.loops[0]
    assert [s.tag for s in L.signals][:2] == [rr[0]["TAG"], rr[1]["TAG"]]


# ---- loop-level rules -------------------------------------------------------------------------------------------------
def test_conflicting_configuration_in_one_loop_is_an_error(reg):
    rr = FX.make_loop("MOV", "A", "M", FX.example_loops(IOM)["MOV"], reg, 5)
    rr[2]["SPD_ARR"] = "B"; rr[2]["TYPICAL"] = "6B-M"
    an = run(rr, reg)
    L = an.loops[0]
    assert L.status == "ERROR" and not L.generate and "LOOP CONFIGURATION CONFLICT" in {i.code for i in L.issues} and L.template is None


@pytest.mark.parametrize("field,val,code", [("SPD_ARR", "X", "INVALID SPD ARRANGEMENT"), ("TERM_ARR", "Q", "INVALID TERMINATION ARRANGEMENT"), ("LOOP_TYPE", "AI-3W", "INVALID LOOP TYPE")])
def test_invalid_selectors(reg, field, val, code):
    rr = FX.make_loop("AI-2W", "A", "M", FX.example_loops(IOM)["AI-2W"], reg, 1)
    rr[0][field] = val
    an = run(rr, reg)
    assert code in issues(an, rr[0]["LOOP_NAME"]) and not an.loops[0].generate


def test_manual_typical_that_disagrees_is_an_error_and_calculated_wins(reg):
    rr = FX.make_loop("AI-2W", "A", "M", FX.example_loops(IOM)["AI-2W"], reg, 1)
    rr[0]["TYPICAL"] = "1B-M"
    an = run(rr, reg)
    L = an.loops[0]
    assert "LOOP TYPICAL MISMATCH" in {i.code for i in L.issues} and L.typical == "1A-M" and L.status == "ERROR"


def test_io_type_must_suit_the_loop_type(reg):
    sw = FX.make_loop("SWITCH", "A", "M", FX.example_loops(IOM)["SWITCH"], reg, 1)
    sw[0]["IO_TYPE"] = "DO"
    assert "IO TYPE NOT COMPATIBLE WITH LOOP TYPE" in issues(run(sw, reg), sw[0]["LOOP_NAME"])
    ai = FX.make_loop("AI-2W", "A", "M", FX.example_loops(IOM)["AI-2W"], reg, 2)
    ai[0]["IO_TYPE"] = "DI"
    assert "IO TYPE NOT COMPATIBLE WITH LOOP TYPE" in issues(run(ai, reg), ai[0]["LOOP_NAME"])
    pv = FX.make_loop("PNEU-VALVE", "A", "M", FX.example_loops(IOM)["PNEU-VALVE"], reg, 3)
    pv[1]["IO_TYPE"] = "AI"
    assert "IO TYPE NOT COMPATIBLE WITH LOOP TYPE" in issues(run(pv, reg), pv[0]["LOOP_NAME"])


def test_wire_type_must_match_ai_2w_and_4w(reg):
    ai = FX.make_loop("AI-2W", "A", "M", FX.example_loops(IOM)["AI-2W"], reg, 1)
    ai[0]["WIRE"] = "4 WIRE"
    assert "WIRE TYPE / LOOP TYPE MISMATCH" in issues(run(ai, reg), ai[0]["LOOP_NAME"])
    f4 = FX.make_loop("AI-4W", "A", "M", FX.example_loops(IOM)["AI-4W"], reg, 2)
    f4[0]["WIRE"] = "2 WIRE"
    assert "WIRE TYPE / LOOP TYPE MISMATCH" in issues(run(f4, reg), f4[0]["LOOP_NAME"])


def test_more_signals_than_the_typical_has_blocks_is_an_error(reg):
    rr = FX.make_loop("SWITCH", "A", "M", FX.example_loops(IOM)["SWITCH"], reg, 1)
    extra = copy.deepcopy(rr[0]); extra["TAG"] += "B"; extra["CHANNEL"] = 99
    an = run(rr + [extra], reg)
    assert "SIGNAL HAS NO SLOT IN TYPICAL" in issues(an, rr[0]["LOOP_NAME"])


def test_unfilled_typical_signal_is_review_not_error(reg):
    rr = FX.make_loop("MOTOR-DOL", "B", "D", FX.example_loops(IOM)["MOTOR-DOL"], reg, 1)
    rr = [r for r in rr if r["IO_TYPE"] != "AI"]
    an = run(rr, reg)
    L = an.loops[0]
    assert L.status == "REVIEW" and L.generate and L.empty_slots == ["S6"] and "TYPICAL SIGNAL NOT PRESENT" in {i.code for i in L.issues}


# ---- template-specific required fields -------------------------------------------------------------------------------
def test_d_loops_do_not_require_marshalling_and_spd_c_does_not_require_spd(reg):
    rr = FX.make_loop("AI-2W", "C", "D", FX.example_loops(IOM)["AI-2W"], reg, 1)
    assert all("MARSH_CAB" not in r and "SPD_TAG" not in r for r in rr)
    an = run(rr, reg)
    assert an.loops[0].status == "PASS", [i.text for i in an.loops[0].issues]


def test_m_loop_without_marshalling_cabinet_is_an_error_and_motors_need_no_jb(reg):
    rr = FX.make_loop("AI-2W", "B", "M", FX.example_loops(IOM)["AI-2W"], reg, 1)
    rr[0].pop("MARSH_CAB")
    an = run(rr, reg)
    assert any(i.code == "MISSING REQUIRED FIELD" and i.field == "MARSH_CAB" for i in an.loops[0].issues) and not an.loops[0].generate
    dol = FX.make_loop("MOTOR-DOL", "B", "M", FX.example_loops(IOM)["MOTOR-DOL"], reg, 2)
    assert run(dol, reg).loops[0].status == "PASS"
    jb = FX.make_loop("MOV", "B", "M", FX.example_loops(IOM)["MOV"], reg, 3)
    jb[0].pop("JB_TAG")
    assert any(i.field == "JB_TAG" for i in run(jb, reg).loops[0].issues)


def test_spd_data_for_a_no_spd_template_is_review_and_never_silently_dropped(reg):
    rr = FX.make_loop("AI-2W", "C", "M", FX.example_loops(IOM)["AI-2W"], reg, 1)
    rr[0].update(SPD_TAG="SPD1", SPD_POS="SPD1-01")
    an = run(rr, reg)
    L = an.loops[0]
    assert L.status == "REVIEW" and L.generate and "SPD DATA PRESENT FOR NO-SPD TEMPLATE" in {i.code for i in L.issues}
    assert any(u["code"] == "SPD_TAG" for u in L.report["unused_source"])
    assert not L.signals[0].data_block.get("SPD_TAG")


def test_is_signal_needs_its_interface_data_and_nis_forces_none(reg):
    rr = FX.make_loop("AI-2W", "B", "M", FX.example_loops(IOM)["AI-2W"], reg, 1)
    rr[0]["ISNIS"] = "IS"
    an = run(rr, reg)
    assert "IS LOOP INTERFACE DATA INCOMPLETE" in issues(an, rr[0]["LOOP_NAME"]) and not an.loops[0].generate
    rr[0].update(ISO_TAG="ISB-1", ISO_MODEL="M", ISO_IN1="1", ISO_IN2="2", ISO_OUT1="3", ISO_OUT2="4")
    ok = run(rr, reg).loops[0]
    assert ok.status == "PASS" and ok.signals[0].data_block["INTERFACE_TAG"] == "ISB-1" and ok.signals[0].data_block["INTERFACE_TYPE"] == "OTHER"
    nis = FX.make_loop("AI-2W", "B", "M", FX.example_loops(IOM)["AI-2W"], reg, 2)
    assert run(nis, reg).loops[0].signals[0].data_block["INTERFACE_TYPE"] == "NONE"


def test_missing_values_are_never_invented(reg):
    rr = FX.make_loop("AI-4W", "B", "M", FX.example_loops(IOM)["AI-4W"], reg, 1)
    rr[0].pop("DB_TAG"); rr[0].pop("TB_T1")
    L = run(rr, reg).loops[0]
    assert {i.field for i in L.issues if i.code == "MISSING REQUIRED FIELD"} >= {"DB_TAG", "TB_T1"} and L.status == "ERROR"
    assert L.signals[0].data_block["DB_TAG"] is None and "BROKEN SIGNAL TRACE" in {i.code for i in L.issues}


# ---- module / channel / terminals ------------------------------------------------------------------------------------
def test_module_and_channel_validation(reg):
    base = FX.example_loops(IOM)["AI-2W"]
    a = FX.make_loop("AI-2W", "A", "M", base, reg, 1)
    a[0]["MODULE_TYPE"] = "DI 32 012"
    assert "SYSTEM I/O ASSIGNMENT INVALID" in issues(run(a, reg), a[0]["LOOP_NAME"])
    b = FX.make_loop("AI-2W", "A", "M", base, reg, 2)
    b[0]["CHANNEL"] = 9                        # AI 08 022 has 8 channels
    assert "SYSTEM I/O ASSIGNMENT INVALID" in issues(run(b, reg), b[0]["LOOP_NAME"])
    c1, c2 = FX.make_loop("AI-2W", "A", "M", base, reg, 3), FX.make_loop("AI-2W", "A", "M", base, reg, 4)
    for r in c2:
        r["SYS_CAB"] = c1[0]["SYS_CAB"]
    both = run(c1 + c2, reg)
    assert "SYSTEM I/O ASSIGNMENT INVALID" in issues(both, c1[0]["LOOP_NAME"]) and "SYSTEM I/O ASSIGNMENT INVALID" in issues(both, c2[0]["LOOP_NAME"])
    d = FX.make_loop("AI-2W", "A", "M", base, reg, 5)
    d[0]["SLOT"] = 7                           # module tag AI101d1 now claims a second slot
    d2 = FX.make_loop("AI-2W", "A", "M", base, reg, 6)
    for r in d2:
        r["SYS_CAB"] = d[0]["SYS_CAB"]; r["CHANNEL"] = 2
    assert "SYSTEM I/O ASSIGNMENT INVALID" in issues(run(d + d2, reg), d[0]["LOOP_NAME"])


def test_duplicate_physical_terminations(reg):
    base = FX.example_loops(IOM)["MOV"]
    rr = FX.make_loop("MOV", "B", "M", base, reg, 1)
    rr[1]["TS_T1"] = rr[0]["TS_T1"]
    assert "DUPLICATE PHYSICAL TERMINATION" in issues(run(rr, reg), rr[0]["LOOP_NAME"])
    jb = FX.make_loop("MOV", "B", "M", base, reg, 2)
    jb[1]["JB_T1"], jb[1]["JB_T2"] = jb[0]["JB_T1"], jb[0]["JB_T2"]
    assert "DUPLICATE PHYSICAL TERMINATION" in issues(run(jb, reg), jb[0]["LOOP_NAME"])
    spd = FX.make_loop("MOV", "B", "M", base, reg, 3)
    spd[1]["SPD_POS"] = spd[0]["SPD_POS"]
    assert "DUPLICATE PHYSICAL TERMINATION" in issues(run(spd, reg), spd[0]["LOOP_NAME"])
    tb = FX.make_loop("MOV", "B", "M", base, reg, 4)
    tb[4]["TB_T1"], tb[5]["TB_T1"] = "9A", "9A"
    assert "DUPLICATE PHYSICAL TERMINATION" in issues(run(tb, reg), tb[0]["LOOP_NAME"])
    ok = FX.make_loop("PNEU-VALVE", "B", "M", FX.example_loops(IOM)["PNEU-VALVE"], reg, 5)       # solenoid and limit switches have their own device strips
    assert "DUPLICATE PHYSICAL TERMINATION" not in issues(run(ok, reg), ok[0]["LOOP_NAME"])


# ---- FIELD CODE mapping / data block ---------------------------------------------------------------------------------
def test_mapping_is_by_field_code_not_position(reg, rows):
    """Same I/O Assignment with the columns in a different order gives the same result."""
    fx = FX.fixture_workbook(rows[:30], IOM)
    wb = openpyxl.load_workbook(io.BytesIO(fx))
    ws = wb["IO_ASSIGNMENT"]
    a = SRC.read_assignment(fx)
    # move the SERVICE / TAG block: swap two columns' values AND their code cells, keep everything else
    col = {str(c.value): c.column for c in ws[8] if c.value}
    c1, c2 = col["FIELD_CABLE"], col["JB_TAG"]
    for r in range(8, 8 + 40):
        v1, v2 = ws.cell(r, c1).value, ws.cell(r, c2).value
        ws.cell(r, c1).value, ws.cell(r, c2).value = v2, v1
    b = io.BytesIO(); wb.save(b)
    swapped = SRC.read_assignment(b.getvalue())
    k1 = A.analyze(a, reg, {}); k2 = A.analyze(swapped, reg, {})
    assert [l.summary() for l in k1.loops] == [l.summary() for l in k2.loops]
    assert [[s.data_block for s in l.signals] for l in k1.loops] == [[s.data_block for s in l.signals] for l in k2.loops]


def test_mapping_log_and_report(reg, rows):
    an = run(rows, reg)
    L = next(l for l in an.loops if l.typical == "2B-M")
    s = L.signals[0]
    m = {x["field"]: x for x in s.mapping}
    assert m["TAG"]["source"] == "TAG" and m["TAG"]["value"] == s.tag and m["TAG"]["state"] == "MAPPED"
    assert m["FSPD_TAG"]["state"] == "NOT APPLICABLE" and m["MARSH_CAB"]["state"] == "MAPPED" and m["SIG"]["state"] == "DERIVED"
    assert L.report["mapped"] >= 35 and not L.report["missing_required"]
    assert any(u["code"] == "FIELD_CABLE_TYPE" for u in L.report["unused_source"])         # informational, not an error
    assert L.status == "PASS"


def test_source_without_the_io_assignment_sheet_is_refused():
    wb = openpyxl.Workbook(); wb.active["A1"] = "nothing"
    b = io.BytesIO(); wb.save(b)
    with pytest.raises(ValueError):
        SRC.read_assignment(b.getvalue())


# ---- generated workbook ----------------------------------------------------------------------------------------------
def test_generated_workbook_preserves_template_drawings_and_formulas(reg, rows):
    an = run(rows, reg)
    data, stats = GEN.generate_workbook(an, None, "fixture.xlsx")
    assert stats["sheets"] == 44 and stats["unsupported_formulas"] == 0 and not stats["skipped"]
    z = zipfile.ZipFile(io.BytesIO(data))
    assert z.testzip() is None
    zt = zipfile.ZipFile(io.BytesIO(TPL))
    for i, g in enumerate(GEN.build_gen_loops(an)[0], start=1):
        assert z.read(f"xl/drawings/drawing{i}.xml") == zt.read(g.template.drawing)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames[0] == "INDEX" and len(wb.sheetnames) == 45 and len(set(wb.sheetnames)) == 45
    name = stats["sheet_names"]["FX07-F-0001"]
    ws = wb[name]
    assert ws["A1"].value == '="LOOP NAME: "&$AG$2' and ws["AG2"].value == "FX07-F-0001" and ws["AG5"].value == "FX07-FT-0001"
    wbv = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    wv = wbv[name]
    assert wv["A1"].value == "LOOP NAME: FX07-F-0001" and wv["B5"].value == "TAG: FX07-FT-0001" and wv["AB7"].value == "Channel:  2"
    # no template placeholder survives in any data block
    for w in wbv.worksheets[1:]:
        for row in w.iter_rows(min_row=2, min_col=32, max_col=78):
            for c in row:
                assert not (isinstance(c.value, str) and "XXXX-" in c.value), (w.title, c.coordinate)
    # 7 signals of a MOV share one sheet; unused blocks are cleared
    mov = wbv[stats["sheet_names"]["FX31-MOV-0001"]]
    assert [mov.cell(r, 32).value for r in range(5, 12)] == [f"S{i}" for i in range(1, 8)]


def test_unfilled_signal_block_is_cleared_in_the_drawing(reg):
    rr = [r for r in FX.make_loop("MOTOR-DOL", "B", "D", FX.example_loops(IOM)["MOTOR-DOL"], reg, 1) if r["IO_TYPE"] != "AI"]
    an = run(rr, reg)
    data, stats = GEN.generate_workbook(an, None, "x")
    ws = openpyxl.load_workbook(io.BytesIO(data), data_only=True)[stats["sheet_names"][rr[0]["LOOP_NAME"]]]
    assert ws["AG10"].value is None and ws["AF10"].value is None
    assert ws["AG5"].value == rr[0]["TAG"]


def test_error_loops_are_not_generated_and_selection_is_honoured(reg, rows):
    bad = copy.deepcopy(rows)
    for r in loop_rows(bad, "FX01-P-0001"):
        r["SPD_ARR"] = "Z"
    an = run(bad, reg)
    data, stats = GEN.generate_workbook(an, ["FX01-P-0001", "FX02-P-0001", "FX03-P-0001"], "x")
    assert stats["sheets"] == 2 and [s["loop"] for s in stats["skipped"]] == ["FX01-P-0001"]
    with pytest.raises(ValueError):
        GEN.generate_workbook(an, ["FX01-P-0001"], "x")


def test_sheet_names_are_excel_safe_and_unique(reg):
    base = FX.example_loops(IOM)["SWITCH"]
    r1 = FX.make_loop("SWITCH", "A", "M", base, reg, 1); r2 = FX.make_loop("SWITCH", "A", "M", base, reg, 2)
    for r in r1: r["LOOP_NAME"] = "A/B:C*D?[1]" + "X" * 40
    for r in r2: r["LOOP_NAME"] = "A/B:C*D?[1]" + "X" * 40 + "2"
    an = run(r1 + r2, reg)
    data, stats = GEN.generate_workbook(an, None, "x")
    names = list(stats["sheet_names"].values())
    assert len(set(n.lower() for n in names)) == 2 and all(len(n) <= 31 and not any(ch in n for ch in "[]:*?/\\") for n in names)


def test_report_workbook_has_the_traceability_sheets(reg, rows):
    an = run(rows, reg)
    wb = openpyxl.load_workbook(io.BytesIO(GEN.build_report(an, None, "x")))
    assert {"SUMMARY", "GENERATION LOG", "FIELD CODE MAPPING", "MAPPING REPORT", "VALIDATION", "TRACE", "CONDUCTORS"} <= set(wb.sheetnames)
    log = wb["GENERATION LOG"]
    assert log.max_row == 1 + 158 and log["I2"].value == "1A-M"


def test_fixture_workbook_round_trips_and_leaves_the_master_untouched(reg, rows):
    before = IOM
    fx = FX.fixture_workbook(rows, IOM)
    src = SRC.read_assignment(fx)
    assert len(src.rows) == len(rows) and {r.text("LOOP_NAME") for r in src.rows} == {r["LOOP_NAME"] for r in rows}
    assert (DIR / "STANDARD_IO_ASSIGNMENT_TEMPLATE_Final.xlsx").read_bytes() == before


# ---- API --------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import loop_wiring_engine
    app = FastAPI()
    app.include_router(loop_wiring_engine.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=77, username="eve")
    return TestClient(app)


def test_api_validate_preview_generate_download(client, rows):
    lib = client.get("/api/loop-wiring/engine/library").json()
    assert lib["complete"] and lib["count"] == 42 and len(lib["templates"]) == 42
    fx = FX.fixture_workbook(rows, IOM)
    v = client.post("/api/loop-wiring/engine/validate", files={"file": ("IO.xlsx", fx)})
    assert v.status_code == 200, v.text
    j = v.json()
    assert j["counts"] == {"PASS": 44, "REVIEW": 0, "ERROR": 0} and len(j["loops"]) == 44 and j["loops"][0]["typical"] == "1A-M"
    d = client.get(f"/api/loop-wiring/engine/analysis/{j['analysis_id']}/loop/FX33-MOV-0001").json()
    assert d["step2"]["calculated"] == "6C-M" and d["step2"]["formula"] == "6C-M" and len(d["step3"]) == 7 and len(d["step4"]["rows"]) == 7
    assert d["step5"][0]["nodes"] and d["step6"][0]["nodes"] and all(x["complete"] for x in d["step7"])
    g = client.post("/api/loop-wiring/engine/generate", json={"analysis_id": j["analysis_id"], "loops": ["FX01-P-0001", "FX33-MOV-0001"]})
    assert g.status_code == 202
    for _ in range(60):
        job = client.get(f"/api/loop-wiring/engine/job/{g.json()['job_id']}").json()
        if job["status"] != "processing":
            break
        time.sleep(0.5)
    assert job["status"] == "done", job
    assert job["result"]["sheet_count"] == 2 and job["result"]["filename"] == "LOOP_WIRING_GENERATED.xlsx"
    out = client.get("/api/loop-wiring/engine/download")
    assert out.status_code == 200 and openpyxl.load_workbook(io.BytesIO(out.content)).sheetnames[0] == "INDEX"
    assert client.get("/api/loop-wiring/engine/report").status_code == 200


def test_api_rejects_non_assignment_and_unknown_analysis(client):
    wb = openpyxl.Workbook(); wb.active["A1"] = "x"
    b = io.BytesIO(); wb.save(b)
    assert client.post("/api/loop-wiring/engine/validate", files={"file": ("x.xlsx", b.getvalue())}).status_code == 400
    assert client.get("/api/loop-wiring/engine/analysis/nope/loop/x").status_code == 404
    assert client.post("/api/loop-wiring/engine/generate", json={"analysis_id": "nope"}).status_code == 404


def test_api_selftest_and_fixture(client):
    st = client.get("/api/loop-wiring/engine/selftest").json()
    assert st["passed"] and sum(m["result"] == "PASS" for m in st["matrix"]) == 42
    assert client.get("/api/loop-wiring/engine/fixture").status_code == 200
