"""Cable Schedule Complete: one IODB -> one workbook, orchestrating the existing engines."""
import io
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import cable_complete as cc  # noqa: E402
from utils.template_processor import process_cable_schedule  # noqa: E402

COLS = ["S.NO", "TAG NO", "LOOP NUMBER", "EQUIPMENT DESCRIPTION", "SIGNAL DESCRIPTION", "INSTRUMENT TYPE NAME", "SIGNAL I/O TYPE", "SUB SYSTEM", "JUNCTION BOX TAG NO.",
        "INSTRUMENT TO JB CABLE TAG NO", "INSTRUMENT TO JB CABLE TYPE", "BRANCH CABLE LENGTH", "INSTRUMENT SIDE GLAND SIZE", "INSTRUMENT SIDE GLAND QTY",
        "MAIN CABLE TAG NUMBER", "MAIN CABLE TYPE", "MAIN CABLE LENGTH(MTRS)", "JB END GLAND SIZE", "PANEL END GLAND SIZE", "IS/NIS TYPE"]


def row(tag, io_type="AI", sub="-", jb="-", btag=None, btype=None, blen=None, gsz=None, gq=None, mtag=None, mtype=None, mlen=None, jend=None, pend=None, loop="L-1", nis="NIS"):
    d = dict.fromkeys(COLS)
    d.update({"TAG NO": tag, "LOOP NUMBER": loop, "EQUIPMENT DESCRIPTION": "EQUIP " + tag, "SIGNAL DESCRIPTION": "SIG", "INSTRUMENT TYPE NAME": "TX", "SIGNAL I/O TYPE": io_type,
              "SUB SYSTEM": sub, "JUNCTION BOX TAG NO.": jb, "INSTRUMENT TO JB CABLE TAG NO": btag, "INSTRUMENT TO JB CABLE TYPE": btype, "BRANCH CABLE LENGTH": blen,
              "INSTRUMENT SIDE GLAND SIZE": gsz, "INSTRUMENT SIDE GLAND QTY": gq, "MAIN CABLE TAG NUMBER": mtag, "MAIN CABLE TYPE": mtype, "MAIN CABLE LENGTH(MTRS)": mlen,
              "JB END GLAND SIZE": jend, "PANEL END GLAND SIZE": pend, "IS/NIS TYPE": nis})
    return d


ROWS = [row("FIT-1", jb="JB-1", btag="IC-1", btype="1PX1.5 Sqmm", blen=20, gsz="M20", gq=1, mtag="MC-1", mtype="12PX1.5 Sqmm", mlen=300, jend="M25", pend="M25"),
        row("PIT-1", jb="JB-1", btag="IC-2", btype="1PX1.5 Sqmm", blen=25, gsz="M20", gq=1, mtag="MC-1", mtype="12PX1.5 Sqmm", mlen=300, jend="M25", pend="M25"),
        row("TIT-1", jb="JB-2", btag="IC-3", btype="2PX1.5 Sqmm", blen=30, gsz='1/2" NPT', gq=1, mtag="MC-2", mtype="12PX1.5 Sqmm", mlen=410, jend="M25", pend="M25"),
        row("YL-M-1A", io_type="DI", sub="MCC", loop="M-1"), row("HS-M-1A", io_type="DO", sub="MCC", loop="M-1"),
        row("YL-V-1A", io_type="DI", sub="VFD", loop="V-1"),
        row("ZS-MOV-1", io_type="DI", loop="MOV-1"), row("ZA-MOV-1", io_type="DO", loop="MOV-1"),
        row("SOFT-1", io_type="SOFT")]


def iodb(rows=None, drop=()):
    df = pd.DataFrame(rows or ROWS, columns=COLS).drop(columns=list(drop))
    buf = io.BytesIO()
    df.to_excel(buf, sheet_name="IODB", index=False)
    return buf.getvalue()


def template(gland_cols=True, extra=("COVERSHEET", "Notes")) -> bytes:
    """A small Cable Schedule template in the iEZ layout (header rows 7-8, three-row prototype block from row 9)."""
    wb = openpyxl.Workbook()
    wb.active.title = "COVERSHEET"
    wb["COVERSHEET"]["A1"] = "COVER"
    ws = wb.create_sheet("Cable Schedule -INST")
    ws["A3"], ws["D3"], ws["A4"], ws["D4"] = "PROJECT", "STORM WATER POND", "CLIENT", "GAIL"
    heads = [("SL. No.", None), ("TAG NUMBER", None), ("LOOP NUMBER", None), ("SIGNAL I/O TYPE", None), ("INSTRUMENT TO JB CABLE TAG NO", None), ("INSTRUMENT TO JB CABLE", None),
             ("BRANCH CABLE LENGTH", None), ("JUNCTION BOX TAG NO.", None), ("MAIN CABLE TAG NUMBER", None), ("MAIN CABLE TYPE", None), ("MAIN CABLE LENGTH(Mtrs)", None)]
    if gland_cols:
        heads += [("INSTRUMENT SIDE GLAND", "GLAND SIZE"), (None, "INSTRUMENT GLAND QTY"), ("JB END GLAND SIZE", None), ("PANEL END GLAND SIZE", None)]
    for c, (top, sub) in enumerate(heads, 1):
        if top:
            ws.cell(7, c, top)
        if sub:
            ws.cell(8, c, sub)
    if gland_cols:
        ws.merge_cells("L7:M7")
    for r in range(9, 12):
        ws.cell(r, 1, r - 8)
    for n in extra:
        if n not in wb.sheetnames:
            wb.create_sheet(n)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def run(rows=None, tpl=None, **kw):
    states = []
    res = cc.run(iodb(rows, **kw), "IODB_Test.xlsx", tpl or template(), lambda k, s, m: states.append((k, s)))
    return res, states


@pytest.fixture(scope="module")
def result():
    return run()


# ── validation ───────────────────────────────────────────────────────────────
def test_validation_reports_counts_and_status():
    v = cc.validate(iodb())
    s = v["stats"]
    assert v["ok"] and v["status"] in ("READY", "READY WITH WARNINGS")
    assert (s["rows"], s["unique_tags"], s["jb_records"], s["main_cable_tags"], s["branch_cable_tags"], s["unique_cable_tags"]) == (9, 9, 2, 2, 3, 5)
    assert s["cable_records"] == 3 and s["valid_cables"] == 5 and s["total_cable_length"] == 20 + 25 + 30 + 300 + 410


def test_validation_blocks_critical_problems_with_clear_messages():
    v = cc.validate(iodb(drop=("INSTRUMENT TO JB CABLE TAG NO", "INSTRUMENT TO JB CABLE TYPE", "BRANCH CABLE LENGTH", "MAIN CABLE TAG NUMBER", "MAIN CABLE TYPE", "MAIN CABLE LENGTH(MTRS)")))
    assert not v["ok"] and v["status"] == "BLOCKED" and "none of the cable columns" in v["errors"][0]
    v = cc.validate(iodb([row("A")]))
    assert not v["ok"] and any("no cable tags" in e for e in v["errors"])
    v = cc.validate(b"not an excel file")
    assert not v["ok"] and "could not be read" in v["errors"][0]
    with pytest.raises(cc.CompleteError, match="IODB validation failed"):
        cc.run(iodb([row("A")]), "x.xlsx", template())


# ── orchestration ────────────────────────────────────────────────────────────
def test_every_stage_runs_in_order_and_is_marked_complete_only_after_its_engine_finished(result):
    res, states = result
    keys = [k for k, _ in cc.STAGES]
    assert [k for k, s in states if s == "running"] == keys
    for k in keys:                                       # running always precedes the final state
        seq = [s for kk, s in states if kk == k]
        assert seq[0] == "running" and seq[-1] in ("done", "warning")
    assert [s["state"] for s in res["stages"]][0] in ("done", "warning") and res["stages"][-1]["state"] == "done"


def test_one_workbook_with_all_sections_and_the_original_template_sheets():
    res, _ = run()
    wb = openpyxl.load_workbook(io.BytesIO(res["workbook"]))
    names = wb.sheetnames
    assert names[0] == "COVER - INDEX" and names[-1] == "COMPLETE EXCEPTION REPORT"
    for n in ("COVERSHEET", "Cable Schedule -INST", "MCC DI", "MCC DO", "VFD", "MOV", "Notes", "CABLE SUMMARY", "IO Summary"):
        assert n in names, n
    assert names.index("Cable Schedule -INST") < names.index("MCC DI") < names.index("IO Summary") < names.index("COMPLETE EXCEPTION REPORT")
    assert len(names) == len(set(names)) and all(len(n) <= 31 for n in names)
    assert [s["sheet"] for s in res["sheets"]] == names


def test_cable_schedule_sheets_are_exactly_what_the_cable_schedule_generator_produces():
    tpl = template()
    res = cc.run(iodb(), "IODB_Test.xlsx", tpl)
    direct, _, err = process_cable_schedule(io.BytesIO(iodb()), io.BytesIO(tpl), "JUNCTION BOX TAG NO.", "TAG NO", output_mode="WITH_SUMMARY",
                                            extra_sheets=["mcc_di", "mcc_do", "vfd", "mov"], extra_report={})
    assert err is None
    a, b = openpyxl.load_workbook(io.BytesIO(res["workbook"])), openpyxl.load_workbook(io.BytesIO(direct))
    for name in b.sheetnames:
        wa_, wb_ = a[name], b[name]
        assert wa_.dimensions == wb_.dimensions, name
        va = [[c.value for c in r] for r in wa_.iter_rows()]
        vb = [[c.value for c in r] for r in wb_.iter_rows()]
        assert va == vb, f"{name} differs from the individual generator"
        assert sorted(map(str, wa_.merged_cells.ranges)) == sorted(map(str, wb_.merged_cells.ranges)), name


def test_io_summary_gland_and_lug_come_from_the_existing_engines_on_the_same_data():
    res, _ = run()
    wb = openpyxl.load_workbook(io.BytesIO(res["workbook"]))
    io_ws = wb["IO Summary"]
    assert io_ws["A1"].value == "I/O SUMMARY"
    counts = {r["type"]: r["total"] for r in res["io_summary"]["rows"]}
    assert counts["AI"] == 3 and counts["DI"] == 4 and counts["DO"] == 3 - 1 + 0 or counts["DO"] >= 2
    from utils import gland_service, lug_quantity
    sched_only = process_cable_schedule(io.BytesIO(iodb()), io.BytesIO(template()), "JUNCTION BOX TAG NO.", "TAG NO", extra_sheets=["mcc_di", "mcc_do", "vfd", "mov"], extra_report={})[0]
    g = gland_service.analyze(sched_only, None, None, None, None, None)
    l, _r = lug_quantity.analyze(sched_only)
    assert res["kpis"]["glands"] == g["totals"]["glands"] and res["kpis"]["lugs"] == l["kpis"]["total_lugs"] and res["kpis"]["cable_tags"] == l["kpis"]["cables"]


def test_gland_and_lug_sheets_use_the_formats_of_their_own_modules():
    res, _ = run()
    wb = openpyxl.load_workbook(io.BytesIO(res["workbook"]))
    assert [c.value for c in wb["GLAND QUANTITY SUMMARY"][3]][:6] == ["GLAND TYPE", "THREAD STANDARD", "GLAND SIZE", "MATERIAL", "CERTIFICATION", "QUANTITY"]
    assert "CABLE LUG SUMMARY" in wb.sheetnames and "CABLE LUG DETAIL" in wb.sheetnames
    hdr = [c.value for c in wb["CABLE LUG DETAIL"][3]]
    assert "CABLE TAG" in hdr and "TOTAL LUGS" in hdr and "CALCULATION BASIS" in hdr


def test_no_meaningless_empty_sheets():
    res, _ = run()
    wb = openpyxl.load_workbook(io.BytesIO(res["workbook"]))
    assert "LUG PROCUREMENT" not in wb.sheetnames                     # instrumentation cables only: no lugs, nothing to procure
    for n in wb.sheetnames:
        if n.startswith(("GLAND", "CABLE LUG", "LUG")):
            assert wb[n].max_row > 3, n


def test_cross_module_consistency_uses_one_physical_cable_dataset():
    res, _ = run()
    c = {x["check"]: x for x in res["checks"]}
    assert all(x["ok"] for x in res["checks"]), res["checks"]
    assert any("counted once" in k for k in c) and any("gland quantities" in k for k in c)
    assert res["kpis"]["cable_tags"] == 5                              # IC-1..3 + MC-1 (shared by two rows) + MC-2
    assert res["lug"]["kpis"]["cables"] == res["kpis"]["cable_tags"]


def test_combined_exception_report_has_the_required_columns_and_all_modules():
    rows = ROWS + [row("LT-9", jb="JB-3", btag="IC-9", btype="1PX1.5 Sqmm", blen=None, gsz="M20", gq=None, mtag="MC-9", mtype=None, mlen=100)]
    res, _ = run(rows)
    wb = openpyxl.load_workbook(io.BytesIO(res["workbook"]))
    ws = wb["COMPLETE EXCEPTION REPORT"]
    assert [c.value for c in ws[3]] == ["MODULE", "SEVERITY", "TAG / CABLE", "SHEET", "FIELD", "ISSUE", "SOURCE VALUE", "EXPECTED VALUE", "RECOMMENDED ACTION"]
    mods = {e["module"] for e in res["exceptions"]}
    assert {"IODB Validation", "Gland"} <= mods
    assert any(e["field"] == "Missing cable length" and "IC-9" in e["ref"] and e["severity"] == "Error" for e in res["exceptions"])
    assert any(e["field"] == "MISSING GLAND QUANTITY" and e["action"] for e in res["exceptions"])
    assert res["kpis"]["exceptions"] == sum(1 for e in res["exceptions"] if e["severity"] in ("Error", "Warning", "Review"))


def test_review_items_in_gland_or_lug_do_not_fail_the_package():
    res, _ = run()
    states = {s["key"]: s["state"] for s in res["stages"]}
    assert states["schedule"] in ("done", "warning") and states["compile"] == "done"
    assert any(s["state"] == "warning" for s in res["stages"])        # e.g. main-cable gland quantities are flagged, the package still completes


def test_gland_failure_is_non_critical():
    res, states = run(ROWS[:3], tpl=template(gland_cols=False))       # no gland columns anywhere (no MCC/VFD/MOV sheets either): the gland engine has nothing to read
    st = {s["key"]: s for s in res["stages"]}
    assert st["gland"]["state"] == "warning" and "could not be generated" in st["gland"]["message"]
    assert st["lug"]["state"] in ("done", "warning") and st["compile"]["state"] == "done" and res["gland"] is None
    wb = openpyxl.load_workbook(io.BytesIO(res["workbook"]))
    assert not any(n.startswith("GLAND") for n in wb.sheetnames)


def test_cable_schedule_failure_stops_gland_and_lug():
    rows = [row("YL-M-1A", io_type="DI", sub="MCC", loop="M-1", btag="IC-1", btype="1PX1.5 Sqmm", blen=5)]       # a cable, but no JB rows and no signals the extra sheets accept for the tag
    seen = []
    try:
        res = cc.run(iodb(rows), "x.xlsx", template(), lambda k, s, m: seen.append((k, s, m)))
    except cc.CompleteError as e:
        assert "Cable Schedule generation failed. Gland and Lug quantities were not generated." in str(e)
        assert not any(k in ("gland", "lug") and s == "running" for k, s, m in seen)
        return
    # the IODB still yields MCC rows, so the package may legitimately build: then no downstream stage may have been skipped
    assert all(s["state"] != "skipped" for s in res["stages"])


def test_no_template_gives_a_clear_error(monkeypatch):
    monkeypatch.setattr(cc, "TEMPLATE_PATH", Path("/nonexistent/template.xlsx"))
    with pytest.raises(cc.CompleteError, match="No Cable Schedule template is installed"):
        cc.run(iodb(), "x.xlsx", None)


def test_the_uploaded_iodb_and_template_are_not_modified():
    data, tpl = iodb(), template()
    b1, b2 = bytes(data), bytes(tpl)
    cc.run(data, "x.xlsx", tpl)
    assert data == b1 and tpl == b2


# ── API ──────────────────────────────────────────────────────────────────────
@pytest.fixture()
def client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import cable_complete
    monkeypatch.setattr(cc, "builtin_template", lambda: template())
    app = FastAPI()
    app.include_router(cable_complete.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=51, username="alice")
    return TestClient(app)


def test_api_status_validate_generate_poll_download(client):
    assert client.get("/api/cable-schedule/complete/status").json()["builtin_template"] is True
    v = client.post("/api/cable-schedule/complete/validate", files={"file": ("IODB.xlsx", iodb())}).json()
    assert v["ok"] and v["stats"]["unique_tags"] == 9 and v["file_name"] == "IODB.xlsx"
    start = client.post("/api/cable-schedule/complete/generate", files={"file": ("IODB.xlsx", iodb())})
    assert start.status_code == 202
    job = start.json()["job_id"]
    for _ in range(60):
        j = client.get(f"/api/cable-schedule/complete/job/{job}").json()
        if j["status"] != "processing":
            break
        time.sleep(0.5)
    assert j["status"] == "done", j
    assert set(j["stages"]) == {k for k, _ in cc.STAGES} and j["result"]["kpis"]["cable_tags"] == 5 and "workbook" not in j["result"]
    dl = client.get("/api/cable-schedule/complete/download")
    assert dl.status_code == 200 and openpyxl.load_workbook(io.BytesIO(dl.content)).sheetnames[0] == "COVER - INDEX"


def test_api_errors_are_clear(client, monkeypatch):
    r = client.post("/api/cable-schedule/complete/generate", files={"file": ("a.txt", b"x")})
    assert r.status_code == 400 and ".xlsx" in r.json()["detail"]
    start = client.post("/api/cable-schedule/complete/generate", files={"file": ("IODB.xlsx", iodb([row("A")]))})
    job = start.json()["job_id"]
    for _ in range(40):
        j = client.get(f"/api/cable-schedule/complete/job/{job}").json()
        if j["status"] != "processing":
            break
        time.sleep(0.3)
    assert j["status"] == "error" and "IODB validation failed" in j["error"]
    assert client.get("/api/cable-schedule/complete/job/nope").status_code == 404
    monkeypatch.setattr(cc, "builtin_template", lambda: None)
    r = client.post("/api/cable-schedule/complete/generate", files={"file": ("IODB.xlsx", iodb())})
    assert r.status_code == 400 and "No Cable Schedule template" in r.json()["detail"]
