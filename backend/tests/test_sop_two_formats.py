"""Datasheet generator: INDIVIDUAL (existing) and CONSOLIDATED (main datasheet + tag-wise annexure) formats."""
import io
import json
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
from openpyxl.styles import Border, Side

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import sop_consolidated as SC, sop_datasheet as SD  # noqa: E402

REAL_SOP = Path.home() / "Downloads" / "LT Non contact Radar Type-R0.xls"
REAL_IODB = Path.home() / "Downloads" / "IODB_Test_1000_Rows.xlsx"
THIN = Side(style="thin")
BOX = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)


def sop_xlsx(with_annexure=True) -> bytes:
    from openpyxl.drawing.image import Image as XLImage
    from PIL import Image
    wb = openpyxl.Workbook()
    t = wb.active
    t.title = "LT-RADAR"
    t["A1"] = "INSTRUMENT DATASHEET LEVEL TRANSMITTER - RADAR"
    eg = wb.create_sheet("LT-RADAR-EG")
    eg["A1"] = "INSTRUMENT DATASHEET LEVEL TRANSMITTER - RADAR"
    png = io.BytesIO(); Image.new("RGB", (40, 20), (200, 30, 30)).save(png, "PNG"); png.seek(0)
    eg.add_image(XLImage(png), "J1")
    rows = [  # (row, section, label, subs, values)
        (9, "GENERAL", "Tag No", None, ["REFER ANNEXURE-I"]),
        (10, None, "P&ID No", None, ["REFER ANNEXURE-I"]),
        (11, "PROCESS CONDITIONS", "Pressure", ["Min", "Nor", "Max"], ["REFER ANNEXURE-I"] * 3),
        (12, "TRANSMITTER", "Output", None, ["4-20 mA HART"]),
        (13, None, "Power supply", None, ["24 VDC"]),
        (14, None, "Calibration Range", None, ["REFER ANNEXURE-I"]),
        (15, "PURCHASE", "Make", None, ["EMERSON"]),
        (16, "SENSOR", "Type", None, ["NON CONTACT RADAR"]),
        (17, "OPTIONS", "Type", None, ["2 Wire"]),
    ]
    for r, sec, lab, subs, vals in rows:
        if sec:
            eg.cell(row=r, column=1, value=sec)
        eg.cell(row=r, column=2, value=lab)
        if subs:
            for i, sb in enumerate(subs):
                eg.cell(row=r, column=3 + i, value=sb)
            for i, v in enumerate(vals):
                eg.cell(row=r, column=6 + 2 * i, value=v)
        else:
            eg.cell(row=r, column=6, value=vals[0])
    eg["B18"] = "NOTES"
    eg.print_area = "A1:L18"
    if with_annexure:
        a = wb.create_sheet("ANNEXURE-I")
        a["A1"] = "INSTRUMENT DATASHEET LEVEL TRANSMITTER - ANNEXURE - I"
        a.merge_cells("A1:I1")
        a["A2"] = "PROJECT"; a["C2"] = "XXXXXX"
        for col, head in zip("ABCDHI", ["SL.No.", "TAG NO.", "P & ID NO.", "SERVICE", "CALIBRATION RANGE (mm)", "REMARKS"]):
            a[f"{col}4"] = head
            a.merge_cells(f"{col}4:{col}5")
        a["E4"] = "PRESSURE (bar)"; a.merge_cells("E4:G4")
        a["E5"], a["F5"], a["G5"] = "MIN", "NOR", "MAX"
        for r in (6, 7):
            for c in range(1, 10):
                a.cell(row=r, column=c).border = BOX
        a["B6"], a["B7"] = "LIT-SAMPLE-1", "LIT-SAMPLE-2"
        a["A9"] = "NOTE: 1. PROCESS DATA AS PER PROCESS DATASHEET."
        a.merge_cells("A9:I9")
        a.print_area = "A1:I9"
    b = io.BytesIO(); wb.save(b)
    return b.getvalue()


def iodb_xlsx(n=60, blank_pmax=(), output_values=None) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IODB"
    ws.append(["TAG NO", "INSTRUMENT TYPE", "SIGNAL I/O TYPE", "SUB SYSTEM", "P&ID NO.", "SERVICE", "PRESSURE MIN (bar)", "PRESSURE MAX (bar)",
               "CALIBRATION RANGE", "OUTPUT"])
    for i in range(1, n + 1):
        tag = f"LT-{i:03d}"
        ws.append([tag, "RADAR LT", "AI", "WTP-1", f"PID-{100 + i}", f"TANK {i}", 0.5, None if tag in blank_pmax else 2.5,
                   f"0-{1000 * i}", (output_values or {}).get(tag, "4-20 mA HART")])
    b = io.BytesIO(); wb.save(b)
    return b.getvalue()


TAGS5 = [f"LT-{i:03d}" for i in range(1, 6)]
OV = {"Make": ["KROHNE"], "Output": ["4-20 mA HART"]}


def ann_ws(data: bytes):
    wb = openpyxl.load_workbook(io.BytesIO(data))
    return wb, wb["ANNEXURE-I"], wb["LT-RADAR-EG"]


# ── structure ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_annexure_is_found_and_parsed_generically():
    sheets = SD.read_workbook(sop_xlsx(), "sop.xlsx")
    info = SC.annexure_info(sheets, "LT-RADAR")
    assert info["annexure_sheet"] == "ANNEXURE-I" and info["annexure_capacity"] == 2
    ann = SC.parse_annexure(sheets["ANNEXURE-I"])
    assert (ann.header_top, ann.data_start, ann.block_end) == (3, 5, 7)
    labels = [c.label for c in ann.columns]
    assert labels == ["SL.No.", "TAG NO.", "P & ID NO.", "SERVICE", "PRESSURE (bar) · MIN", "PRESSURE (bar) · NOR", "PRESSURE (bar) · MAX",
                      "CALIBRATION RANGE (mm)", "REMARKS"]
    assert SC.annexure_info(SD.read_workbook(sop_xlsx(False), "s.xlsx"), "LT-RADAR")["annexure_sheet"] is None


def test_mapping_respects_min_nor_max_and_never_guesses():
    sheets = SD.read_workbook(sop_xlsx(), "sop.xlsx")
    ann = SC.parse_annexure(sheets["ANNEXURE-I"])
    import pandas as pd
    cols = list(pd.read_excel(io.BytesIO(iodb_xlsx(1))).columns)
    m = {next(c.label for c in ann.columns if c.col == k): v for k, v in SC.auto_map(ann, cols).items()}
    assert m["P & ID NO."] == "P&ID NO." and m["SERVICE"] == "SERVICE" and m["CALIBRATION RANGE (mm)"] == "CALIBRATION RANGE"
    assert m["PRESSURE (bar) · MIN"] == "PRESSURE MIN (bar)" and m["PRESSURE (bar) · MAX"] == "PRESSURE MAX (bar)"
    assert m["PRESSURE (bar) · NOR"] is None and m["REMARKS"] is None


# ── Test A: individual (existing engine, unchanged) ─────────────────────────────────────────────────────────────────
def test_A_individual_five_tags():
    data, name, err, failed = SC.generate_package(SC.INDIVIDUAL, sop_xlsx(), "sop.xlsx", "LT-RADAR", iodb_xlsx(), "RADAR LT", TAGS5, OV)
    assert err is None and not failed and name == "Datasheets.zip"
    z = zipfile.ZipFile(io.BytesIO(data))
    assert sorted(z.namelist()) == [f"{t} Datasheet.xlsx" for t in TAGS5]
    for t in TAGS5:
        ws = openpyxl.load_workbook(io.BytesIO(z.read(f"{t} Datasheet.xlsx")))["LT-RADAR-EG"]
        assert ws["F9"].value == t and ws["F15"].value == "KROHNE"
    # identical to calling the existing engine directly
    d2, n2, e2, f2 = SD.generate_with_report(sop_xlsx(), "sop.xlsx", "LT-RADAR", iodb_xlsx(), "RADAR LT", TAGS5, OV)
    assert n2 == name and sorted(zipfile.ZipFile(io.BytesIO(d2)).namelist()) == sorted(z.namelist())


# ── Test B: consolidated ─────────────────────────────────────────────────────────────────────────────────────────────
def test_B_consolidated_five_tags_one_workbook():
    data, name, err, failed = SC.generate_package(SC.CONSOLIDATED, sop_xlsx(), "sop.xlsx", "LT-RADAR", iodb_xlsx(), "RADAR LT", TAGS5, OV)
    assert err is None and not failed and name == "LT-RADAR_CONSOLIDATED_DATASHEET.xlsx"
    wb, a, eg = ann_ws(data)
    assert wb.sheetnames == ["LT-RADAR-EG", "ANNEXURE-I"]
    assert eg["F9"].value == "REFER ANNEXURE-I" and eg["F15"].value == "KROHNE" and eg["F13"].value == "24 VDC"   # common specs on the main sheet
    assert len(eg._images) == 1                                                                                  # logo kept
    tags = [a.cell(row=r, column=2).value for r in range(6, 11)]
    assert tags == TAGS5 and [a.cell(row=r, column=1).value for r in range(6, 11)] == [1, 2, 3, 4, 5]
    assert [a.cell(row=r, column=3).value for r in range(6, 11)] == [f"PID-{100 + i}" for i in range(1, 6)]
    assert a["E6"].value == 0.5 and a["G6"].value == 2.5 and a["F6"].value is None and a["H8"].value == "0-3000"
    assert a["A12"].value == "NOTE: 1. PROCESS DATA AS PER PROCESS DATASHEET." and "A12:I12" in {str(m) for m in a.merged_cells.ranges}   # note moved down, spacer kept
    assert "LIT-SAMPLE-1" not in [c.value for row in a.iter_rows() for c in row]                                  # template samples replaced


# ── Test C: 50 tags ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_C_annexure_expands_to_fifty_rows_with_formatting():
    tags = [f"LT-{i:03d}" for i in range(1, 51)]
    data, _, err, failed = SC.generate_package(SC.CONSOLIDATED, sop_xlsx(), "sop.xlsx", "LT-RADAR", iodb_xlsx(), "RADAR LT", tags, OV)
    assert err is None and not failed
    _, a, _ = ann_ws(data)
    got = [a.cell(row=r, column=2).value for r in range(6, 56)]
    assert got == tags and len(set(got)) == 50
    assert a.cell(row=55, column=9).border.bottom.style == "thin" and a.cell(row=40, column=1).border.left.style == "thin"
    assert a["A56"].value is None and a["A57"].value == "NOTE: 1. PROCESS DATA AS PER PROCESS DATASHEET."
    assert "A57:I57" in {str(m) for m in a.merged_cells.ranges} and "E4:G4" in {str(m) for m in a.merged_cells.ranges}
    assert a.print_title_rows == "$4:$5" and str(a.print_area).endswith("$I$57")


# ── Test D: missing data ─────────────────────────────────────────────────────────────────────────────────────────────
def test_D_missing_data_is_reported_never_invented():
    iodb = iodb_xlsx(blank_pmax={"LT-002", "LT-004"})
    ctx = SC.load_context(sop_xlsx(), "sop.xlsx", "LT-RADAR", iodb)
    v = SC.validate(ctx, SC.CONSOLIDATED, TAGS5 + ["LT-999"], OV)
    codes = {i["code"]: i for i in v["issues"]}
    assert codes["TAG_NOT_IN_IODB"]["tag"] == "LT-999" and v["counts"]["ERROR"] >= 1
    miss = [i for i in v["issues"] if i["code"] == "MISSING_TAG_DATA" and "MAX" in i["field"]]
    assert miss and "LT-002" in miss[0]["message"] and "LT-004" in miss[0]["message"]
    assert any(i["code"] == "UNMAPPED_COLUMN" and "REMARKS" in i["message"] for i in v["issues"])
    data, _, err, failed = SC.generate_package(SC.CONSOLIDATED, sop_xlsx(), "sop.xlsx", "LT-RADAR", iodb, "RADAR LT", TAGS5 + ["LT-999"], OV)
    _, a, _ = ann_ws(data)
    assert a["G7"].value is None and a["G9"].value is None and a["G6"].value == 2.5                     # blank stays blank
    assert failed == [{"tag": "LT-999", "reason": "Tag not found in the IODB"}]


def test_validation_rules():
    ctx = SC.load_context(sop_xlsx(), "sop.xlsx", "LT-RADAR", iodb_xlsx(output_values={"LT-003": "FOUNDATION FIELDBUS"}))
    v = SC.validate(ctx, SC.INDIVIDUAL, TAGS5 + ["LT-001"], OV)
    codes = [i["code"] for i in v["issues"]]
    assert "DUPLICATE_TAG" in codes and "COMMON_SPEC_DIFFERS" in codes
    assert SC.validate(ctx, "BOTH", TAGS5, OV)["issues"][0]["code"] == "INVALID_FORMAT"
    no_ann = SC.load_context(sop_xlsx(False), "s.xlsx", "LT-RADAR", iodb_xlsx())
    assert any(i["code"] == "NO_ANNEXURE_TEMPLATE" for i in SC.validate(no_ann, SC.CONSOLIDATED, TAGS5, OV)["issues"])
    _, _, err, _ = SC.generate_package(SC.CONSOLIDATED, sop_xlsx(False), "s.xlsx", "LT-RADAR", iodb_xlsx(), "RADAR LT", TAGS5, OV)
    assert err and "annexure" in err.lower()


def test_user_mapping_overrides_auto_mapping():
    data, *_ = SC.generate_package(SC.CONSOLIDATED, sop_xlsx(), "sop.xlsx", "LT-RADAR", iodb_xlsx(), "RADAR LT", TAGS5, OV,
                                   {"3": "SERVICE", "8": "OUTPUT"})       # REMARKS <- OUTPUT, SERVICE column cleared? no: col 3 = SERVICE
    _, a, _ = ann_ws(data)
    assert a["D6"].value == "TANK 1" and a["I6"].value == "4-20 mA HART"


# ── real SOP (.xls) - run where the files exist ─────────────────────────────────────────────────────────────────────
@pytest.mark.skipif(not (REAL_SOP.exists() and REAL_IODB.exists()), reason="real SOP / IODB not on this machine")
def test_F_real_sop_both_formats():
    import pandas as pd
    sop = REAL_SOP.read_bytes()
    iodb = REAL_IODB.read_bytes()
    df = pd.read_excel(io.BytesIO(iodb))
    tags = df[df["INSTRUMENT TYPE NAME"].astype(str).str.contains("radar", case=False)]["TAG NO"].astype(str).tolist()[:5]
    assert len(tags) == 5
    d1, n1, e1, f1 = SC.generate_package(SC.INDIVIDUAL, sop, "x.xls", "LT-RADAR", iodb, "", tags, {})
    d0, n0, e0, f0 = SD.generate_with_report(sop, "x.xls", "LT-RADAR", iodb, "", tags, {})
    assert e1 is None and n1 == n0 and sorted(zipfile.ZipFile(io.BytesIO(d1)).namelist()) == sorted(zipfile.ZipFile(io.BytesIO(d0)).namelist())
    d2, n2, e2, f2 = SC.generate_package(SC.CONSOLIDATED, sop, "x.xls", "LT-RADAR", iodb, "", tags, {"Make": ["KROHNE"]})
    assert e2 is None and not f2
    wb = openpyxl.load_workbook(io.BytesIO(d2))
    a = wb["ANNEXURE-I"]
    assert [a.cell(row=r, column=2).value for r in range(12, 17)] == tags
    assert a.cell(row=12, column=1).value == 1 and a.print_title_rows == "$7:$11"
    eg = wb["LT-RADAR-EG"]
    assert eg.cell(row=9, column=6).value == "REFER ANNEXURE-I"
    assert any(c.value == "KROHNE" for row in eg.iter_rows() for c in row)


# ── API: format, approval gate, approved values, download ───────────────────────────────────────────────────────────
@pytest.fixture()
def api(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user, get_db
    from app.routers import sop_datasheet as R
    R.generation_cache.clear()
    app = FastAPI()
    app.include_router(R.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=4242, username="u")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def approval(db, status="approved", fmt=SC.CONSOLIDATED, tags=TAGS5, overrides=None, mapping=None):
    from app.auth.models import ApprovalRequest
    payload = {"Datasheet Format": SC.FORMAT_LABELS[fmt], "Make": "KROHNE",
               "__iez": {"format": fmt, "datasheet": "LT-RADAR", "overrides": overrides or {"Make": ["KROHNE"]}, "annexure_mapping": mapping}}
    req = ApprovalRequest(request_type="spec", tag_numbers=json.dumps(tags), instrument_type="RADAR LT", payload_json=json.dumps(payload),
                          submitted_by_name="Eng", submitted_by_id="E1", status=status, reviewed_by_name="Lead A", reviewed_by_id="L9",
                          reviewed_role="Lead Engineer", updated_at=datetime(2026, 11, 18, 10, 30))
    db.add(req); db.commit(); db.refresh(req)
    return req.id


def files(fmt, approval_id=None, tags=TAGS5, overrides=None):
    data = {"datasheet_sheet": "LT-RADAR", "instrument_type": "RADAR LT", "selected_tags": json.dumps(tags),
            "overrides": json.dumps(overrides or {"Make": ["SOMETHING ELSE"]}), "generation_format": fmt}
    if approval_id is not None:
        data["approval_id"] = str(approval_id)
    return {"files": {"sop_file": ("sop.xlsx", sop_xlsx()), "iodb_file": ("iodb.xlsx", iodb_xlsx())}, "data": data}


def run(api, **kw):
    r = api.post("/api/sop-datasheet/generate", **kw)
    if r.status_code != 202:
        return r, None
    for _ in range(100):
        j = api.get(f"/api/sop-datasheet/generate/status/{r.json()['job_id']}").json()
        if j["status"] != "processing":
            return r, j
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_E_consolidated_needs_an_approval_and_uses_the_approved_values(api, db):
    assert api.post("/api/sop-datasheet/generate", **files(SC.CONSOLIDATED)).status_code == 409                 # no approval
    pending = approval(db, status="pending")
    assert api.post("/api/sop-datasheet/generate", **files(SC.CONSOLIDATED, pending)).status_code == 409
    rejected = approval(db, status="rejected")
    assert api.post("/api/sop-datasheet/generate", **files(SC.CONSOLIDATED, rejected)).status_code == 409
    wrong_fmt = approval(db, fmt=SC.INDIVIDUAL)
    r = api.post("/api/sop-datasheet/generate", **files(SC.CONSOLIDATED, wrong_fmt))
    assert r.status_code == 409 and "new approval" in r.json()["detail"]
    ok = approval(db)
    assert api.post("/api/sop-datasheet/generate", **files(SC.CONSOLIDATED, ok, tags=TAGS5[:4])).status_code == 409   # tags changed
    _, job = run(api, **files(SC.CONSOLIDATED, ok))
    assert job["status"] == "done" and job["result"]["format"] == SC.CONSOLIDATED and job["result"]["tag_count"] == 5
    d = api.get("/api/sop-datasheet/download")
    assert d.status_code == 200 and "CONSOLIDATED_DATASHEET.xlsx" in d.headers["content-disposition"]
    assert d.headers["content-type"].startswith("application/vnd.openxmlformats")
    eg = openpyxl.load_workbook(io.BytesIO(d.content))["LT-RADAR-EG"]
    assert eg["F15"].value == "KROHNE"                                   # the approved value, not the one the browser sent


def test_E_individual_with_approval_and_legacy_without(api, db):
    ok = approval(db, fmt=SC.INDIVIDUAL)
    _, job = run(api, **files(SC.INDIVIDUAL, ok))
    assert job["status"] == "done" and job["result"]["tag_count"] == 5
    d = api.get("/api/sop-datasheet/download")
    assert d.headers["content-type"] == "application/zip"
    ws = openpyxl.load_workbook(io.BytesIO(zipfile.ZipFile(io.BytesIO(d.content)).read("LT-001 Datasheet.xlsx")))["LT-RADAR-EG"]
    assert ws["F15"].value == "KROHNE"
    _, job2 = run(api, **files(SC.INDIVIDUAL))                           # legacy call (no approval id) still works
    assert job2["status"] == "done"
    assert api.post("/api/sop-datasheet/generate", **{**files("BOTH")}).status_code == 400


def test_validate_and_datasheets_endpoints(api):
    r = api.post("/api/sop-datasheet/datasheets", files={"sop_file": ("sop.xlsx", sop_xlsx())})
    ds = r.json()["datasheets"][0]
    assert ds["annexure_sheet"] == "ANNEXURE-I" and ds["annexure_capacity"] == 2
    v = api.post("/api/sop-datasheet/validate", files={"sop_file": ("sop.xlsx", sop_xlsx()), "iodb_file": ("i.xlsx", iodb_xlsx())},
                 data={"datasheet_sheet": "LT-RADAR", "selected_tags": json.dumps(TAGS5), "generation_format": "CONSOLIDATED", "overrides": json.dumps(OV)})
    j = v.json()
    assert v.status_code == 200 and j["counts"]["ERROR"] == 0 and j["annexure"]["rows"] == 5 and len(j["annexure"]["preview"]) == 5
    assert any(c["iodb_column"] == "P&ID NO." for c in j["annexure"]["columns"])


def test_ai_extracts_each_field_separately(api, monkeypatch):
    from app.routers import sop_datasheet as R
    seen = {}

    async def fake(prompt, max_tokens, json_mode=False):
        seen["prompt"] = prompt
        return json.dumps({"fields": [{"label": "Output", "value": "4-20 mA HART", "confidence": 0.9, "snippet": "output 4-20 mA HART"},
                                      {"label": "Make", "value": "", "confidence": 0.7, "snippet": ""}]})
    monkeypatch.setattr(R, "_groq", fake)
    r = api.post("/api/sop-datasheet/extract-spec", data={"labels": json.dumps(["Output", "Make", "Power supply"])},
                 files=[("tender_file", ("t.txt", b"Transmitter output 4-20 mA HART, IP66.")), ("tender_file", ("u.txt", b"Supply 24 VDC"))])
    j = r.json()
    f = {x["label"]: x for x in j["fields"]}
    assert f["Output"]["value"] == "4-20 mA HART" and f["Output"]["confidence"] == 0.9
    assert f["Make"]["value"] == "" and f["Make"]["confidence"] == 0.0 and f["Power supply"]["value"] == ""
    assert "Supply 24 VDC" in seen["prompt"] and j["text_chars"] > 0


def test_repeated_labels_in_different_sections_keep_their_own_values():
    """'Type' exists under SENSOR and OPTIONS: a keyed override changes only its own row (both formats)."""
    ov = {"SENSOR::Type": ["GUIDED WAVE RADAR"], "PURCHASE::Make": ["KROHNE"], "OPTIONS::Type": ["2 Wire"]}
    data, *_ = SC.generate_package(SC.INDIVIDUAL, sop_xlsx(), "sop.xlsx", "LT-RADAR", iodb_xlsx(), "RADAR LT", TAGS5[:1], ov)
    ws = openpyxl.load_workbook(io.BytesIO(zipfile.ZipFile(io.BytesIO(data)).read("LT-001 Datasheet.xlsx")))["LT-RADAR-EG"]
    assert (ws["F16"].value, ws["F17"].value, ws["F15"].value) == ("GUIDED WAVE RADAR", "2 Wire", "KROHNE")
    data, *_ = SC.generate_package(SC.CONSOLIDATED, sop_xlsx(), "sop.xlsx", "LT-RADAR", iodb_xlsx(), "RADAR LT", TAGS5, ov)
    _, _, eg = ann_ws(data)
    assert (eg["F16"].value, eg["F17"].value) == ("GUIDED WAVE RADAR", "2 Wire")
    # older clients that send a plain label keep the old behaviour (the label applies wherever it appears)
    data, *_ = SC.generate_package(SC.INDIVIDUAL, sop_xlsx(), "sop.xlsx", "LT-RADAR", iodb_xlsx(), "RADAR LT", TAGS5[:1], {"Type": ["X"]})
    ws = openpyxl.load_workbook(io.BytesIO(zipfile.ZipFile(io.BytesIO(data)).read("LT-001 Datasheet.xlsx")))["LT-RADAR-EG"]
    assert ws["F16"].value == ws["F17"].value == "X"


@pytest.mark.skipif(not (REAL_SOP.exists() and REAL_IODB.exists()), reason="real SOP / IODB not on this machine")
def test_real_sop_sensor_type_is_not_overwritten_by_transmitter_type():
    import pandas as pd
    sop, iodb = REAL_SOP.read_bytes(), REAL_IODB.read_bytes()
    sheets = SD.read_workbook(sop, "x.xls")
    fields = SD.parse_field_spec(sheets["LT-RADAR-EG"], sheets["LT-RADAR-EG"])
    ov = {SD.field_key(f): list(f.defaults) for f in fields}                    # exactly what the page now sends
    df = pd.read_excel(io.BytesIO(iodb))
    tag = df[df["INSTRUMENT TYPE NAME"].astype(str).str.contains("radar", case=False)]["TAG NO"].astype(str).iloc[0]
    data, *_ = SC.generate_package(SC.INDIVIDUAL, sop, "x.xls", "LT-RADAR", iodb, "", [tag], ov)
    ws = openpyxl.load_workbook(io.BytesIO(zipfile.ZipFile(io.BytesIO(data)).read(f"{tag} Datasheet.xlsx"))).active
    assert ws.cell(row=26, column=6).value == "NON CONTACT RADAR" and ws.cell(row=39, column=6).value == "2 Wire"
