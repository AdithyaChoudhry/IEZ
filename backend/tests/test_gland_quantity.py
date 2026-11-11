"""Cable Gland Quantity Generator: gland quantities from a cable schedule + OD based gland advisor."""
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import gland_advisor as adv  # noqa: E402
from utils import gland_quantity as gq  # noqa: E402
from utils import gland_reference as ref  # noqa: E402
from utils import gland_service as svc  # noqa: E402


# ── a small cable schedule in the iEZ layout (two header rows, one block per cable) ──
def schedule(rows, sheet="Cable Schedule -INST", hidden=()):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    hdr = ["SL. No.", "TAG NUMBER", "INSTRUMENT TO JB CABLE TAG", "INSTRUMENT TO JB CABLE", "INSTRUMENT SIDE GLAND", None, "JB SIDE GLAND", None,
           "MAIN CABLE TAG NUMBER", "MAIN CABLE TYPE", "JB END GLAND SIZE", "PANEL END GLAND SIZE", "Remarks"]
    sub = [None, None, None, None, "GLAND SIZE", "INSTRUMENT GLAND QTY", "GLAND SIZE", "GLAND QTY.", None, None, None, None, None]
    ws.append([None] * 13)
    ws.append(hdr)
    ws.append(sub)
    ws.merge_cells("E2:F2")
    ws.merge_cells("G2:H2")
    for r in rows:
        ws.append(r)
    for n in hidden:
        wb.create_sheet(n).sheet_state = "hidden"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def row(i, tag, btag, btype, isz, iq, jsz, jq, mtag=None, mtype=None, jend=None, pend=None):
    return [i, tag, btag, btype, isz, iq, jsz, jq, mtag, mtype, jend, pend, None]


BASE = [row(1, "FIT-1", "IC-1", "1PX1.5 Sqmm", "M20", 1, "M20", 1, "MC-1", "12PX1.5 Sqmm", "M25", "M25"),
        row(2, "PIT-1", "IC-2", "1PX1.5 Sqmm", "M20", 2, "M20", 1, "MC-1", "12PX1.5 Sqmm", "M25", "M25"),
        row(3, "TIT-1", "IC-3", "2PX1.5 Sqmm", '1/2" NPT', 1, '1/2" NPT', 1)]


def analyze(rows, **kw):
    return svc.analyze(schedule(rows), kw.get("settings"), kw.get("cable_data"), kw.get("project"))


# ── designation parsing ──────────────────────────────────────────────────────
@pytest.mark.parametrize("text,std,label", [("M20", "METRIC", "M20"), ("m 25x1.5", "METRIC", "M25"), ("½” NPT", "NPT", '1/2" NPT'),
                                            ('1 1/4" NPT', "NPT", '1-1/4" NPT'), ("NPT 3/4", "NPT", '3/4" NPT'), ("ET 20", "ET", "ET 20"),
                                            ('3/4"ET', "ET", '3/4" ET'), ("G 1/2", "BSP", '1/2" BSP'), ("20", "", "20")])
def test_gland_designations(text, std, label):
    g = gq.parse_gland(text)
    assert (g["std"], g["label"]) == (std, label)


# ── extraction and aggregation ───────────────────────────────────────────────
def test_quantities_are_used_as_stated_and_shared_main_cable_is_counted_once():
    p = analyze(BASE)
    by = {(r["thread"], r["gland_size"]): r["qty"] for r in p["summary"]["by_gland"]}
    assert by[("Metric", "M20")] == 1 + 1 + 2 + 1          # instrument 1 + JB 1, instrument 2 (explicit quantity 2) + JB 1
    assert by[("Npt", "1/2\" NPT")] == 2
    assert not any(k == ("Metric", "M25") for k in by)     # main-cable glands have no quantity column -> flagged, not assumed
    kinds = {e["kind"] for e in p["exceptions"]}
    assert "MISSING GLAND QUANTITY" in kinds
    miss = [e for e in p["exceptions"] if e["kind"] == "MISSING GLAND QUANTITY"]
    assert len(miss) == 4 and all("not counted" in e["message"].lower() for e in miss)


def test_project_default_quantity_is_used_only_when_configured_and_is_reported():
    p = analyze(BASE, settings={"default_qty": 1})
    by = {(r["thread"], r["gland_size"]): r["qty"] for r in p["summary"]["by_gland"]}
    assert by[("Metric", "M25")] == 4 - 2 + 0 or by[("Metric", "M25")] == 2   # JB end + panel end of MC-1, counted once each
    assert any(e["kind"] == "Default gland quantity used" for e in p["exceptions"])
    assert any(e["kind"] == "Shared cable counted once" and "MC-1" in e["ref"] for e in p["exceptions"])


def test_repeated_rows_can_be_added_instead():
    p = analyze(BASE, settings={"default_qty": 1, "repeated_rows": "sum"})
    by = {(r["thread"], r["gland_size"]): r["qty"] for r in p["summary"]["by_gland"]}
    assert by[("Metric", "M25")] == 4


def test_same_cable_two_locations_is_two_glands_and_locations_are_kept():
    p = analyze(BASE[:1])
    loc = {(r["location"], r["gland_size"]): r["qty"] for r in p["summary"]["by_location"]}
    assert loc[("Instrument Side", "M20")] == 1 and loc[("JB Side", "M20")] == 1
    detail = [c for c in p["cable_wise"] if c["cable_tag"] == "IC-1"]
    assert {c["location"] for c in detail} == {"Instrument Side", "JB Side"}


def test_summaries_by_cable_type_and_gland_type_thread_material_stay_separate():
    p = analyze(BASE)
    bt = {(r["cable_type"], r["gland_size"]): r["qty"] for r in p["summary"]["by_cable_type"]}
    assert bt[("1PX1.5 Sqmm", "M20")] == 5 and bt[("2PX1.5 Sqmm", '1/2" NPT')] == 2
    assert p["summary"]["total_qty"] == 7
    assert all({"gland_type", "thread", "gland_size", "material", "certification", "qty"} <= set(r) for r in p["summary"]["by_gland"])


def test_unrecognised_thread_and_tba_are_flagged_not_hidden():
    rows = [row(1, "A", "IC-1", "1PX1.5 Sqmm", "20", 1, "TBA", 1)]
    p = analyze(rows)
    kinds = {e["kind"] for e in p["exceptions"]}
    assert {"Thread not stated", "Gland size TBA"} <= kinds
    assert p["summary"]["by_gland"][0]["thread"] == "Not stated"


def test_hidden_template_sheets_are_not_counted_by_default():
    wb = openpyxl.load_workbook(io.BytesIO(schedule(BASE)))
    ws = wb.create_sheet("OLD")
    ws.sheet_state = "hidden"
    for r in schedule_rows_copy():
        ws.append(r)
    buf = io.BytesIO(); wb.save(buf)
    infos = gq.detect_sheets(openpyxl.load_workbook(io.BytesIO(buf.getvalue())))
    assert gq.default_sheets(infos) == ["Cable Schedule -INST"]


def schedule_rows_copy():
    return [[None] * 13, ["SL", "TAG NUMBER", "CABLE TAG", "CABLE TYPE", "INSTRUMENT SIDE GLAND", None, None, None, None, None, None, None, None],
            [None, None, None, None, "GLAND SIZE", "GLAND QTY"] + [None] * 7, [1, "X", "IC-9", "1PX1.5", "M16", 99]]


def test_the_uploaded_file_is_never_modified():
    data = schedule(BASE)
    before = bytes(data)
    analyze(BASE)
    svc.analyze(data)
    assert data == before


def test_no_gland_columns_gives_a_clear_error():
    wb = openpyxl.Workbook()
    wb.active.append(["a", "b", "c"])
    buf = io.BytesIO(); wb.save(buf)
    with pytest.raises(gq.GlandError, match="No cable schedule sheet"):
        svc.analyze(buf.getvalue())
    with pytest.raises(gq.GlandError, match="could not be opened"):
        svc.analyze(b"not a zip")


# ── advisor ──────────────────────────────────────────────────────────────────
def advise(**kw):
    d = {"od": 14, "construction": "UNARMOURED", "cable_type": "12P x 1.5"}
    d.update(kw)
    return adv.advise(adv.inputs_from(d), ref.builtin())


def res_for(out, std):
    return next(r for r in out["results"] if r["standard"] == std)


def test_od_validation_messages():
    for bad, msg in (("", "required"), ("abc", "not a valid number"), ("-3", "negative"), ("0", "greater than zero"), ("14.2.3", "not a valid number"),
                     ("400", "reasonable range")):
        with pytest.raises(adv.AdviceError, match=msg):
            adv.parse_od(bad)
    assert adv.parse_od("7.8") == 7.8 and adv.parse_od("27.65 mm") == 27.65 and adv.parse_od("14,2") == 14.2


def test_metric_recommendation_checks_the_published_range_not_the_thread_size():
    out = advise(od=9.0)
    m = res_for(out, "METRIC")
    assert m["status"] == "VALID" and m["preferred"]["od_range"][0] <= 9.0 <= m["preferred"]["od_range"][1]
    assert m["preferred"]["manufacturer"] == "CMP Products" and m["preferred"]["source"]["url"].startswith("https://www.cmp-products.com")
    for c in [m["preferred"]] + m["alternatives"]:                   # every option really covers the OD
        assert c["od_range"][0] <= 9.0 <= c["od_range"][1]
    assert any("MANUFACTURER VERIFICATION REQUIRED" in c["flags"] for c in [m["preferred"]])
    assert "not a final" in out["disclaimer"]


def test_borderline_is_flagged_and_alternatives_are_never_hidden():
    out = advise(od=14.0)                                            # A2F size 20 range 6.5-14.0
    m = res_for(out, "METRIC")
    border = [c for c in [m["preferred"]] + m["alternatives"] if c["gland_size"] == "20"][0]
    assert border["borderline"] and "BORDERLINE" in border["flags"]
    assert m["preferred"]["gland_size"] != "20" and not m["preferred"]["borderline"]
    assert "BORDERLINE" in " ".join(border["checks"]) and len(m["alternatives"]) >= 1


def test_npt_comes_from_the_gland_row_and_is_not_a_metric_conversion():
    out = advise(od=9.0)
    n = res_for(out, "NPT")
    pre = n["preferred"]
    assert pre["standard"] == "NPT" and all("NPT" in o for o in pre["thread_options"]) and len(pre["thread_options"]) >= 1
    # the size-16 gland publishes no NPT thread, so it is never offered for NPT
    assert all(c["gland_size"] != "16" for c in [pre] + n["alternatives"])
    out = advise(od=9.0, entry_thread='3/4" NPT')
    assert all('3/4" NPT' in c["thread_options"] for c in [res_for(out, "NPT")["preferred"]] + res_for(out, "NPT")["alternatives"])


def test_et_and_bsp_are_unavailable_without_a_table_and_never_inferred():
    out = advise(od=9.0)
    et = res_for(out, "ET")
    assert et["status"] == "UNAVAILABLE" and et["message"] == adv.ET_UNAVAILABLE and et["preferred"] is None and et["legacy"]
    assert "BS 31:1940" in et["notice"] and "LEGACY" in et["notice"]
    assert res_for(out, "BSP")["status"] == "UNAVAILABLE"


def test_vendor_table_adds_et_and_bsp_and_takes_priority():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(ref.TEMPLATE_HEADERS)
    ws.append(["Acme", "AX", "Double compression", "Unarmoured", "20", 8.0, 12.0, None, None, None, None, "M20", '1/2" NPT', "ET 20", '1/2" BSP',
               "IP66/IP68", "Ex d IIC", "Nickel plated brass", "-60 to 130 C", "Acme catalogue 2026", "https://example.test", "Rev B", ""])
    buf = io.BytesIO(); wb.save(buf)
    rows, problems = ref.read_vendor_table(buf.getvalue())
    assert len(rows) == 1 and rows[0].et == ["ET 20"] and rows[0].bsp == ['1/2" BSP'] and rows[0].tier == "VENDOR"
    out = adv.advise(adv.inputs_from({"od": 10, "construction": "UNARMOURED", "hazardous": True, "ip": "IP66"}), rows + ref.builtin())
    et = res_for(out, "ET")
    assert et["status"] == "VALID" and et["preferred"]["manufacturer"] == "Acme" and et["preferred"]["ex"] == "Ex d IIC"
    assert "CERTIFICATION CHECK REQUIRED" not in et["preferred"]["flags"]
    m = res_for(out, "METRIC")
    assert m["preferred"]["manufacturer"] == "Acme"                  # vendor table before the built-in reference
    assert "CERTIFICATION CHECK REQUIRED" in res_for(out, "NPT")["preferred"]["flags"] or res_for(out, "NPT")["preferred"]["manufacturer"] == "Acme"


def test_armoured_cable_checks_bedding_and_armour_and_flags_missing_inputs():
    out = adv.advise(adv.inputs_from({"od": 20, "construction": "ARMOURED"}), ref.builtin())
    pre = res_for(out, "METRIC")["preferred"]
    assert "BEDDING NOT ENTERED" in pre["flags"] and "ARMOUR NOT ENTERED" in pre["flags"] and pre["bedding_range"]
    ok = adv.advise(adv.inputs_from({"od": 20, "construction": "ARMOURED", "bedding": 15, "armour_min": 1.25, "armour_max": 1.6}), ref.builtin())
    assert res_for(ok, "METRIC")["status"] in ("VALID", "BORDERLINE")
    bad = adv.advise(adv.inputs_from({"od": 20, "construction": "ARMOURED", "bedding": 3.0}), ref.builtin())
    assert res_for(bad, "METRIC")["status"] == "NO COMPATIBLE GLAND"


def test_construction_changes_the_family_and_unsupported_families_say_so():
    un = res_for(advise(od=20), "METRIC")["preferred"]
    ar = res_for(advise(od=20, construction="ARMOURED", bedding=15), "METRIC")["preferred"]
    assert un["series"] == "A2F" and ar["series"] == "T3CDS"
    br = res_for(advise(od=10, construction="BRAIDED"), "METRIC")
    assert br["status"] == "NO COMPATIBLE GLAND" and "braided" in br["message"].lower()


def test_hazardous_area_never_claims_certification():
    out = advise(od=9, hazardous=True, zone="Zone 1", protection="Ex e")
    pre = res_for(out, "METRIC")["preferred"]
    assert "CERTIFICATION CHECK REQUIRED" in pre["flags"] and pre["ex"] == "not in database"
    assert any("CERTIFICATION CHECK REQUIRED" in a for a in out["advice"])


def test_ip_and_material_not_in_database_are_flagged_not_assumed():
    pre = res_for(advise(od=9, ip="IP66", material="Stainless steel"), "METRIC")["preferred"]
    assert {"IP RATING NOT IN DATABASE", "MATERIAL NOT IN DATABASE"} <= set(pre["flags"])


def test_cable_type_advice_texts():
    assert any("EMC" in a for a in advise(cable_type="VFD cable 4C x 2.5")["advice"])
    assert any("armoured or unarmoured" in a for a in advise(cable_type="MOV cable 19C")["advice"])
    assert any("core count" in a for a in advise(cable_type="RTD cable")["advice"])
    assert advise()["advice"][-1] == adv.RULE_OD_VS_THREAD


# ── existing vs recommended ──────────────────────────────────────────────────
def test_existing_gland_is_compared_and_never_replaced():
    rows = [row(1, "A", "IC-1", "1PX1.5 Sqmm", "M20", 1, "M20", 1), row(2, "B", "IC-2", "19CX1.5 Sqmm", "M20", 1, "M20", 1),
            row(3, "C", "IC-3", "4PX1.5 Sqmm", "M25", 1, "M25", 1), row(4, "D", "IC-4", "9PX1.5 Sqmm", "M20", 1, "M20", 1),
            row(5, "E", "IC-5", "7PX1.5 Sqmm", None, None, None, None)]
    cd = {"1PX15SQMM": {"od": 7.0}, "19CX15SQMM": {"od": 24.0}, "9PX15SQMM": {}}
    p = analyze(rows, cable_data=cd)
    res = {a["cable_type"]: a for a in p["advisory"]}
    assert res["1PX1.5 Sqmm"]["result"] in ("MATCH", "REVIEW") and res["1PX1.5 Sqmm"]["existing"] == ["M20"]
    assert res["19CX1.5 Sqmm"]["result"] in ("MISMATCH", "REVIEW") and res["19CX1.5 Sqmm"]["existing"] == ["M20"]
    assert res["4PX1.5 Sqmm"]["result"] == "MISSING OD" and res["9PX1.5 Sqmm"]["result"] == "MISSING OD"
    assert res["7PX1.5 Sqmm"]["result"] == "MISSING GLAND DATA" or res["7PX1.5 Sqmm"]["result"] == "MISSING OD"
    sizes = {r["gland_size"] for r in p["summary"]["by_gland"]}
    assert "M20" in sizes and all(l["existing"] in ("M20", "M25") for l in p["_cable_wise"])       # schedule values untouched
    kinds = {e["kind"] for e in p["exceptions"]}
    assert {"Missing OD"} <= kinds


def test_project_mapping_takes_priority_over_the_reference_tables():
    p = analyze(BASE[:1], cable_data={"1PX15SQMM": {"od": 7.0}}, project={"mapping": {"1PX1.5 Sqmm": "M20"}})
    a = next(x for x in p["advisory"] if x["cable_type"] == "1PX1.5 Sqmm")
    assert a["result"] == "MATCH" and a["source"]["manufacturer"] == "Project specification"


def test_existing_et_gland_asks_for_manufacturer_check():
    rows = [row(1, "A", "IC-1", "1PX1.5 Sqmm", '3/4"ET', 1, '3/4"ET', 1)]
    p = analyze(rows, cable_data={"1PX15SQMM": {"od": 9.0}})
    a = p["advisory"][0]
    assert a["result"] == "MANUFACTURER CHECK REQUIRED"
    assert any(e["kind"] == "ET availability" for e in p["exceptions"])


# ── workbook ─────────────────────────────────────────────────────────────────
def test_report_workbook_sheets_and_assumptions():
    p = analyze(BASE, settings={"default_qty": 1}, cable_data={"1PX15SQMM": {"od": 7.0}})
    wb = openpyxl.load_workbook(io.BytesIO(svc.to_workbook(p, "Schedule.xlsx")))
    assert wb.sheetnames == ["GLAND SUMMARY", "CABLE TYPE SUMMARY", "CABLE GLAND DETAIL", "LOCATION SUMMARY", "OD ADVISORY", "EXCEPTIONS", "REFERENCE - ASSUMPTIONS"]
    ws = wb["GLAND SUMMARY"]
    assert [c.value for c in ws[3]] == ["GLAND TYPE", "THREAD STANDARD", "GLAND SIZE", "MATERIAL", "CERTIFICATION", "QUANTITY"]
    assert ws.cell(ws.max_row, 1).value == "TOTAL"
    text = " ".join(str(c.value) for row in wb["REFERENCE - ASSUMPTIONS"].iter_rows() for c in row if c.value)
    for needle in ("IEC/EN 62444", "ASME B1.20.1", "BS 31:1940", "cmp-products.com", "not a final", "Metric and NPT"):
        assert needle.lower() in text.lower() or needle in text


# ── API ──────────────────────────────────────────────────────────────────────
@pytest.fixture()
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import gland_quantity
    app = FastAPI()
    app.include_router(gland_quantity.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=31, username="alice")
    return TestClient(app)


def test_api_detect_analyze_download_advise_reference(client):
    f = ("Schedule.xlsx", schedule(BASE))
    d = client.post("/api/cable-schedule/gland/detect", files={"file": f}).json()
    assert d["default_sheets"] == ["Cable Schedule -INST"] and {t["cable_type"] for t in d["cable_types"]} == {"1PX1.5 Sqmm", "2PX1.5 Sqmm", "12PX1.5 Sqmm"}
    a = client.post("/api/cable-schedule/gland/analyze", files={"file": f}, data={"settings": '{"default_qty": 1}', "cable_data": '{"1PX15SQMM": {"od": 7}}'})
    assert a.status_code == 200, a.text
    body = a.json()
    assert body["totals"]["glands"] > 0 and "_lines" not in body and body["summary"]["by_gland"]
    dl = client.get("/api/cable-schedule/gland/download")
    assert dl.status_code == 200 and openpyxl.load_workbook(io.BytesIO(dl.content)).sheetnames[0] == "GLAND SUMMARY"
    adv_r = client.post("/api/cable-schedule/gland/advise", data={"inputs": '{"od": "9.5", "construction": "UNARMOURED"}'})
    assert adv_r.status_code == 200 and {r["standard"] for r in adv_r.json()["results"]} == {"METRIC", "NPT", "BSP", "ET"}
    assert client.post("/api/cable-schedule/gland/advise", data={"inputs": '{"od": "abc"}'}).status_code == 400
    r = client.get("/api/cable-schedule/gland/reference").json()
    assert r["rows"] and {s["id"] for s in r["standards"]} >= {"IEC/EN 62444", "ASME B1.20.1", "BS 31:1940"} and "disclaimer" in r
    t = client.get("/api/cable-schedule/gland/reference/template")
    assert t.status_code == 200


def test_api_errors_are_clear(client):
    r = client.post("/api/cable-schedule/gland/analyze", files={"file": ("a.txt", b"x")})
    assert r.status_code == 400 and ".xlsx" in r.json()["detail"]
    r = client.post("/api/cable-schedule/gland/analyze", files={"file": ("a.xlsx", b"not a zip")})
    assert r.status_code == 400 and "could not be opened" in r.json()["detail"]
    r = client.post("/api/cable-schedule/gland/analyze", files={"file": ("a.xlsx", schedule(BASE))}, data={"settings": "{bad"})
    assert r.status_code == 400 and "not valid JSON" in r.json()["detail"]
