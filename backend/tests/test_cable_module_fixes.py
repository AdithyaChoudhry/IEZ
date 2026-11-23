"""Cable Schedule module fixes: main cable identity in the MCC / VFD / MOV sheets (tag first, no false conflicts, no
silent first value), safe formula lengths, uniform entry row heights, the Cable Lug Advisor, the lug job lifecycle
(never an endless 'processing') and the gland generate path."""
import io
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cable_schedule_extra import COLS, row  # noqa: E402

from utils import cable_schedule_extra as X  # noqa: E402
from utils import lug_advisor as LA  # noqa: E402
from utils.cable_summary import parse_length  # noqa: E402
from utils.file_handler import read_iodb  # noqa: E402


def recs_of(rows):
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=COLS).to_excel(buf, sheet_name="IODB", index=False)
    df, _ = read_iodb(io.BytesIO(buf.getvalue()))
    recs, _ = X.normalize(df)
    return X.split_records(recs)


def mcc(tag, ctag, clen, io_="DI", dev="FINE SCREEN 01", ctype="12PX1.5 Sqmm"):
    return row(tag, "ML-1", dev, "SIG " + tag, "SCREEN", io_, sub="MCC", jb="JB-101-02", ctag=ctag, ctype=ctype, clen=clen)


# ── main cable identity (the 12 reported 'conflicts') ────────────────────────
def test_distinct_main_cable_tags_of_one_device_are_separate_cables_not_a_conflict():
    parts = recs_of([mcc("MS-1C", "MC-101-0201-03", 73), mcc("MS-1D", "MC-101-0201-04", 90), mcc("MS-1E", "MC-101-0201-05", 107)])
    blocks = X.plan_blocks("mcc_di", parts["mcc_di"])
    cables = [(g.tag, g.length) for b in blocks for g in b.groups]
    assert sorted(cables) == [("MC-101-0201-03", "73"), ("MC-101-0201-04", "90"), ("MC-101-0201-05", "107")]
    assert all(not g.conflicts for b in blocks for g in b.groups)
    assert X.sheet_stats("mcc_di", parts["mcc_di"])["warnings"] == []


def test_same_tag_on_several_rows_is_one_cable_and_formatting_differences_are_equal():
    parts = recs_of([mcc("A", "MC-001", 300), mcc("B", "MC-001", "300.0"), mcc("C", "mc-001 ", "=100+200"), mcc("D", "MC-001", None)])
    blocks = X.plan_blocks("mcc_di", parts["mcc_di"])
    groups = [g for b in blocks for g in b.groups]
    assert len(groups) == 1 and not groups[0].conflicts                     # blank = missing data, not a conflict
    assert not any("Conflict" in w for w in X.sheet_stats("mcc_di", parts["mcc_di"])["warnings"])
    # a formula and its value are the same length (compared as numbers, not text)
    n = X._norm_value
    assert n("main_cable_length", "=100+200") == n("main_cable_length", "300.0") == n("main_cable_length", "300")
    assert n("main_cable_length", "=98+210") == n("main_cable_length", "308")
    assert n("main_cable_tag", " mc-001 ") == n("main_cable_tag", "MC-001")


def test_genuine_conflict_is_reported_with_rows_and_values_and_never_resolved_silently():
    parts = recs_of([mcc("A", "MC-001", 300), mcc("B", "MC-001", 350)])
    blocks = X.plan_blocks("mcc_di", parts["mcc_di"])
    g = blocks[0].groups[0]
    assert g.conflicts == ["main_cable_length"] and [v for _, v in g.conflict_rows["main_cable_length"]] == ["300", "350"]
    msg = X.sheet_stats("mcc_di", parts["mcc_di"])["warnings"][0]
    for part in ("Main Cable Conflict Detected", "Cable Tag: MC-001", "Junction Box: JB-101-02", "IODB row 2", "= 300 m", "IODB row 3",
                 "= 350 m", "Action required", "not counted"):
        assert part in msg, part
    assert "first one is used" not in msg
    assert X._block_values("mcc_di", blocks[0], 1)["length"] == "CONFLICT: 300 / 350"


def test_untagged_signals_of_one_motor_still_share_the_reference_block():
    parts = recs_of([mcc("A", None, 120), mcc("B", None, 120), mcc("C", None, 120)])
    assert len(X.plan_blocks("mcc_di", parts["mcc_di"])) == 1


def test_safe_formula_lengths():
    assert parse_length("=98+210")[0] == 308 and parse_length("=2*(10+5)")[0] == 30
    for bad in ("=A1+2", "=SUM(1,2)", '__import__("os")', "=1/0", "=-5"):
        assert parse_length(bad)[1] == "invalid", bad


# ── row heights ──────────────────────────────────────────────────────────────
def test_every_entry_has_one_height_on_all_its_rows_and_long_text_is_not_clipped():
    from test_cable_schedule_corrections import generate, heads, by_tag
    wb, rep, _ = generate()
    ws = wb["Cable Schedule -INST"]
    starts = sorted(by_tag(ws).values())
    for s in starts:
        hs = {ws.row_dimensions[s + i].height for i in range(3)}
        assert len(hs) == 1 and min(hs) >= 18.0
    assert rep["layout"]["row_height"]["entries"] == len(starts)
    assert [ws.row_dimensions[r].height for r in range(1, 9)] == [openpyxl.load_workbook(io.BytesIO(__import__("test_cable_schedule_layout").template()))["Cable Schedule -INST"].row_dimensions[r].height for r in range(1, 9)]


# ── lug advisor ──────────────────────────────────────────────────────────────
def lrow(tag, ctype, cat, req="YES", lf=2, lt=2, status="OK", basis="RULE", lug_type="NOT SPECIFIED", earth=0):
    return {"cable_tag": tag, "cable_type": ctype, "category": cat, "lug_required": req, "lugged_from": lf, "lugged_to": lt,
            "lug_from": (lf or 0) + earth, "lug_to": (lt or 0) + earth, "basis": basis, "status": status, "from": "A", "to": "B",
            "type_key": ctype, "lug_type": lug_type, "material": "NOT SPECIFIED", "reason": ""}


def ends(rows, st=None):
    return {(e["cable_tag"], e["end"]): e for e in LA.apply({"cable_wise": rows}, st)["advisor"]["ends"]}


def test_power_copper_aluminium_and_unknown_material():
    e = ends([lrow("CU6", "3C x 6 Sq.mm Cu", "POWER", lf=3, lt=3), lrow("CU95", "3C x 95 Sq.mm Cu", "POWER", lf=3, lt=3),
              lrow("AL95", "3.5C x 95 Sq.mm AL", "POWER", lf=3, lt=3), lrow("UNK", "4C x 25 Sq.mm", "POWER", lf=4, lt=4)],
             {"terminal": {"POWER": "STUD"}, "terminal_material": "COPPER"})
    assert e[("CU6", "FROM")]["lug_type"] == LA.RING and e[("CU95", "FROM")]["lug_type"] == LA.TUBULAR
    assert e[("CU6", "FROM")]["lug_material"] == "Tin-plated copper" and e[("CU6", "FROM")]["status"] == LA.ADVISORY
    assert LA.MANUAL in e[("CU95", "FROM")]["lug_size"]                    # stud / hole never derived
    assert e[("AL95", "FROM")]["lug_type"] == LA.BIMETAL
    assert e[("UNK", "FROM")]["status"] == LA.REVIEW and e[("UNK", "FROM")]["lug_material"] == LA.MANUAL
    assert e[("CU6", "FROM")]["quantity"] == 3


def test_instrument_cable_on_unknown_terminal_is_advisory_only_and_count_is_kept():
    e = ends([lrow("I-1", "1P x 1.5 Sq.mm", "INSTRUMENTATION")])
    f = e[("I-1", "FROM")]
    assert f["lug_type"] == LA.FERRULE1 and f["status"] == LA.REVIEW and f["quantity"] == 2   # the count is known, the type is not confirmed


def test_missing_size_unknown_category_and_no_lug():
    e = ends([lrow("X", "Special", "UNKNOWN", req="REVIEW", status="REVIEW", lf=None, lt=None), lrow("N", "1P x 1.5", "INSTRUMENTATION", req="NO", lf=0, lt=0, basis="TERMINATION")])
    assert e[("X", "FROM")]["status"] == LA.REVIEW and e[("X", "FROM")]["quantity"] is None
    assert e[("N", "FROM")]["lug_type"] == LA.NONE and e[("N", "FROM")]["quantity"] == 0 and e[("N", "FROM")]["status"] == LA.CONFIRMED


def test_selection_precedence_and_overrides_are_kept_and_flagged():
    st = {"default_type": LA.PIN, "default_scope": "CONTROL", "terminal": {"CONTROL": "PLC_DCS"},
          "selections": {"tag:C2|end:to": {"type": LA.RING}, "tag:I1": {"type": LA.FERRULE2}}}
    e = ends([lrow("C1", "4C x 1.5 Cu", "CONTROL", lf=4, lt=4), lrow("C2", "4C x 1.5 Cu", "CONTROL", lf=4, lt=4),
              lrow("I1", "1P x 1.5 Cu", "INSTRUMENTATION"), lrow("S", "4C x 1.5 Cu", "CONTROL", lf=4, lt=4, basis="SCHEDULE", lug_type="Pin lug 1.5")], st)
    assert e[("C1", "FROM")]["lug_type"] == LA.PIN and e[("C1", "FROM")]["status"] == LA.MANUAL_SEL       # project default, scope CONTROL
    assert e[("C2", "TO")]["lug_type"] == LA.RING and any("cannot take a bolted lug" in w for w in e[("C2", "TO")]["warnings"])
    assert e[("I1", "FROM")]["lug_type"] == LA.FERRULE2 and e[("I1", "FROM")]["quantity"] == 1             # twin: 2 conductors, 1 ferrule
    assert e[("S", "FROM")]["lug_type"] == "Pin lug 1.5" and e[("S", "FROM")]["status"] == LA.CONFIRMED     # source data beats the default


def test_spare_conductors_follow_the_engine_count():
    e = ends([lrow("C", "12C x 1.5 Cu", "CONTROL", lf=10, lt=10)], {"terminal": {"CONTROL": "SCREW"}})
    assert e[("C", "FROM")]["quantity"] == 10                                # 2 spare cores not terminated -> not counted


def test_unknown_lug_type_is_rejected():
    with pytest.raises(LA.AdvisorError):
        LA.settings_from({"default_type": "Gold plated lug"})


# ── lug job lifecycle ────────────────────────────────────────────────────────
@pytest.fixture()
def lug_client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import lug_quantity
    from utils import cable_complete as cc
    from test_cable_complete import template
    monkeypatch.setattr(cc, "builtin_template", lambda: template())
    app = FastAPI()
    app.include_router(lug_quantity.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=81, username="lugger")
    return TestClient(app), lug_quantity


def wait(c, job_id, limit=120):
    for _ in range(limit * 4):
        j = c.get(f"/api/cable-schedule/lug/job/{job_id}").json()
        if j["status"] != "processing":
            return j
        time.sleep(0.25)
    raise AssertionError("job never finished")


def test_iodb_upload_generates_the_lug_report_with_advisor_sheets(lug_client):
    from test_cable_complete import iodb
    c, _ = lug_client
    r = c.post("/api/cable-schedule/lug/start", files={"iodb_file": ("IODB_Test.xlsx", iodb())},
               data={"advisor": json.dumps({"terminal": {"INSTRUMENTATION": "PLC_DCS"}, "default_material": "COPPER"})})
    assert r.status_code == 202, r.text
    j = wait(c, r.json()["job_id"])
    assert j["status"] == "done", j
    adv = j["result"]["advisor"]
    assert adv["ends"] and adv["summary"] and j["result"]["source"]["type"] == "IODB"
    wb = openpyxl.load_workbook(io.BytesIO(c.get("/api/cable-schedule/lug/download").content))
    assert {"CABLE LUG DETAILS", "LUG QUANTITY SUMMARY", "ADVISOR REVIEW", "LUG SUMMARY"} <= set(wb.sheetnames)
    # re-run with a selection on the same IODB (reuse) keeps the selection
    key = f"tag:{adv['ends'][0]['cable_tag']}|end:from"
    r = c.post("/api/cable-schedule/lug/start", data={"reuse": "true", "advisor": json.dumps({"selections": {key: {"type": LA.PIN}}})})
    j2 = wait(c, r.json()["job_id"])
    e = next(x for x in j2["result"]["advisor"]["ends"] if x["cable_tag"] == adv["ends"][0]["cable_tag"] and x["end"] == "FROM")
    assert e["lug_type"] == LA.PIN and e["status"] == LA.MANUAL_SEL


def test_job_status_survives_memory_loss_and_a_dead_job_is_an_error_not_processing(lug_client):
    c, lq = lug_client
    from test_cable_complete import iodb
    job_id = c.post("/api/cable-schedule/lug/start", files={"iodb_file": ("IODB.xlsx", iodb())}).json()["job_id"]
    assert wait(c, job_id)["status"] == "done"
    lq._jobs.clear()                                                        # another process / a restart: read from disk
    assert c.get(f"/api/cable-schedule/lug/job/{job_id}").json()["status"] == "done"
    # a job whose process is gone never stays 'processing'
    lq._jobs["deadjob"] = {"status": "processing", "created": time.time(), "updated": time.time(), "stage": "Reading", "user": "lugger", "pid": 999999}
    lq._save_job("deadjob")
    lq._jobs.clear()
    d = c.get("/api/cable-schedule/lug/job/deadjob").json()
    assert d["status"] == "error" and "run it again" in d["error"]
    assert c.get("/api/cable-schedule/lug/job/nosuchjob").status_code == 404


def test_bad_advisor_settings_are_refused_before_a_job_starts(lug_client):
    c, _ = lug_client
    from test_cable_complete import iodb
    r = c.post("/api/cable-schedule/lug/start", files={"iodb_file": ("IODB.xlsx", iodb())}, data={"advisor": json.dumps({"default_type": "Gold lug"})})
    assert r.status_code == 400 and "Unknown cable lug type" in r.json()["detail"]
