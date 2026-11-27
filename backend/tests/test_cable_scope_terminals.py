"""Cable Schedule: AREA / AREA CODE / STATUS scope filters and terminal details from the Standard I/O Assignment."""
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import app.database as database  # noqa: E402
from app.deps import get_current_user, get_db  # noqa: E402
from cable_header_helpers import generate as post_generate  # noqa: E402
from utils import cable_scope as CS  # noqa: E402
from utils.io_terminals import AssignmentError, Matcher, read_assignment  # noqa: E402

COLS = ["TAG NO", "LOOP NUMBER", "SIGNAL DESCRIPTION", "INSTRUMENT TYPE NAME", "SIGNAL I/O TYPE", "SUB SYSTEM", "AREA", "AREA CODE",
        "STATUS", "JUNCTION BOX TAG NO.", "INSTRUMENT TO JB CABLE TYPE", "BRANCH CABLE LENGTH", "MAIN CABLE TAG NUMBER",
        "MAIN CABLE TYPE", "MAIN CABLE LENGTH(MTRS)"]


def r(tag, io_t="AI", sub="-", area="Intake", code="001", status=None, jb="JB-1", btype="1P", blen=10, mtag="MC-1", mtype="12P",
      mlen=100, loop=None, sig="SIGNAL"):
    return [tag, loop or "L-" + tag, sig, "PUMP", io_t, sub, area, code, status, jb, btype, blen, mtag, mtype, mlen]


ROWS = [
    r("PT-101"), r("PT-102", status="Deleted in Rev 1", blen=999), r("PT-103", status="Newly added"),
    r("PT-201", area="RO", code="002", jb="JB-2", mtag="MC-2", mlen=50), r("PT-202", area="RO", code="002", jb="JB-1", status="D"),
    r("PT-301", area="RO", code="003", jb="JB-3", mtag="MC-3", status=" deleted "),
    r("MS-101A", "DO", "MCC", loop="ML-101", sig="START", jb="-", mtag="MC-9"),
    r("MS-101B", "DO", "MCC", loop="ML-101", sig="STOP", jb="-", mtag="MC-9", status="DELETED"),
    r("MS-101C", "DI", "MCC", loop="ML-101", sig="RUN", jb="-", mtag="MC-8"),
]


def iodb(rows=ROWS, cols=COLS) -> bytes:
    b = io.BytesIO()
    pd.DataFrame(rows, columns=cols).to_excel(b, sheet_name="IODB", index=False)
    return b.getvalue()


def frame():
    from utils.file_handler import read_iodb
    return read_iodb(io.BytesIO(iodb()))[0]


def tags(selection):
    df = frame()
    return CS.Scope(df, selection).apply(df)["TAG NO"].tolist()


# ── filters ──────────────────────────────────────────────────────────────────
def test_default_excludes_every_deleted_spelling_only_and_rows_individually():
    assert tags({}) == ["PT-101", "PT-103", "PT-201", "PT-202", "MS-101A", "MS-101C"]      # 'D' is not assumed to mean deleted
    options = CS.Scope(frame()).options()
    cats = {s["value"]: s["category"] for s in options["statuses"]}
    assert cats == {"NEWLY ADDED": "current", "(Blank)": "blank", "D": "unknown", "DELETED": "deleted", "DELETED IN REV 1": "deleted"}
    assert [c["value"] for c in options["area_codes"]] == ["001", "002", "003"]                    # leading zeros kept
    assert {c["value"]: c["areas"] for c in options["area_codes"]} == {"001": ["Intake"], "002": ["RO"], "003": ["RO"]}


def test_area_and_code_combine_and_bad_or_empty_selections_are_refused():
    assert tags({"areas": ["RO"]}) == ["PT-201", "PT-202"]
    assert tags({"area_codes": ["001"]}) == ["PT-101", "PT-103", "MS-101A", "MS-101C"]
    assert tags({"areas": ["RO", "Intake"], "area_codes": ["002"]}) == ["PT-201", "PT-202"]
    assert tags({"areas": ["Intake"], "area_codes": ["002"]}) == []
    assert "PT-102" in tags({"statuses": ["DELETED IN REV 1", "(Blank)"]})
    for bad in ({"areas": []}, {"statuses": []}, {"area_codes": ["1"]}, {"areas": ["Nowhere"]}, {"x": 1}):
        with pytest.raises(CS.ScopeError):
            CS.Scope(frame(), bad)
    with pytest.raises(CS.ScopeError):
        CS.Scope(frame().drop(columns=["AREA"]), {"areas": ["RO"]})


def test_summary_counts_each_exclusion_once_and_shared_cables_are_disclosed():
    df = frame()
    rep = CS.report(CS.Scope(df, {"areas": ["Intake"]}), df)
    s = rep["summary"]
    assert s["total"] == s["eligible"] + s["excluded_status"] + s["excluded_area"] + s["excluded_area_code"]
    assert (s["eligible"], s["excluded_status"], s["deleted_excluded"]) == (4, 3, 3)
    assert any("junction boxes also serve records outside" in n and "JB-1" in n for n in rep["notes"])
    hist = CS.report(CS.Scope(df, {"statuses": ["DELETED"]}), df)
    assert hist["notes"][0].startswith("WARNING") and CS.Scope(df, {"statuses": ["DELETED"]}).file_suffix() == "with_deleted"


# ── I/O Assignment ───────────────────────────────────────────────────────────
HEAD = ["LOOP NO.", "TAG NUMBER", "SIGNAL DESCRIPTION", "IO TYPE", "STATUS", "DEVICE TERMINAL BLOCK", "DEVICE TERMINAL 1 (+ / SIG)",
        "DEVICE TERMINAL 2 (- / CMN)", "FIELD TERMINAL STRIP (TS)", "TS TERMINAL 1 (+ / SIG)", "TS TERMINAL 2 (- / CMN)", "CHANNEL NO."]


def assignment(rows, sheet="IO_ASSIGNMENT", head=HEAD) -> bytes:
    wb = openpyxl.Workbook()
    wb.active.title = "EXAMPLE"
    wb.active.append(head)
    wb.active.append(["x", "MS-101A", "START", "DO", "USED", "NO", "NO", "NO"])
    ws = wb.create_sheet(sheet)
    ws.append(["I/O ASSIGNMENT"])
    ws.append(head)
    for row in rows:
        ws.append(row)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


IOA = [["ML-101", "ms-101a ", "START", "DO", "USED", "X1", "02", "01", "TS1", "7", "8", 1],
       ["ML-101", "MS-101A", "START", "DO", "SPARE", "ZZ", "99", "99", "", "", "", 2],
       ["ML-101", "MS-101C", "RUN", "DI", "USED", "", "", "", "TS1", "9", "10", 3]]


def rec(tag, io_t, signal="", loop="ML-101"):
    return SimpleNamespace(tag_no=tag, io=io_t, signal_description=signal, loop_number=loop, row=2)


def run(matcher, record, sheet="mcc_do"):
    values = {"end_mtb": "TBA", "end_pos": "TBA", "end_neg": "TBA", "cd_pos": "TBA", "cd_neg": "TBA"}
    matcher.apply(sheet, record, values)
    return values


def test_only_the_assignment_sheet_is_read_spares_ignored_and_terminal_order_kept():
    a = read_assignment(assignment(IOA))
    assert (a.used, a.spare) == (2, 1)
    m = Matcher(a)
    assert run(m, rec("MS-101A", "DO", "START"))["end_pos"] == "02" and run(m, rec("MS-101A", "DO"))["end_neg"] == "01"
    panel_only = run(m, rec("MS-101C", "DI", "RUN"), "mcc_di")                  # the TS is a panel-side terminal: not used
    assert (panel_only["end_pos"], panel_only["end_mtb"]) == ("TBA", "TBA")
    assert run(Matcher(a, {"equipment": "ts"}), rec("MS-101C", "DI"), "mcc_di")["end_pos"] == "9"      # confirmed by the engineer
    assert run(m, rec("MS-101A", "DO"), "mov")["cd_pos"] == "TBA"
    assert run(Matcher(a, {"panel": "ts"}), rec("MS-101A", "DO"), "mov")["cd_pos"] == "7"
    assert run(m, rec("MS-101", "DO"))["end_pos"] == "TBA" and run(m, rec("101A", "DO"))["end_pos"] == "TBA"
    total = m.report({})["total"]
    assert total["resolved"] >= 1 and total["partial"] >= 1 and total["unmatched"] >= 2


def test_conflicts_are_reported_and_nothing_is_picked_or_overwritten():
    rows = IOA + [["ML-101", "MS-101A", "START", "DO", "USED", "X2", "5", "6", "", "", "", 9]]
    m = Matcher(read_assignment(assignment(rows)))
    assert run(m, rec("MS-101A", "DO", "START"))["end_pos"] == "TBA"
    assert m.report({})["total"]["conflicts"] == 1
    m = Matcher(read_assignment(assignment(IOA)))
    assert run(m, rec("MS-101A", "DI"))["end_pos"] == "TBA"                                     # IO type differs
    values = {"end_pos": "55", "end_neg": "TBA", "end_mtb": "TBA"}
    m.apply("mcc_do", rec("MS-101A", "DO"), values)
    assert values["end_pos"] == "55" and values["end_neg"] == "01" and m.report({})["total"]["conflicts"] == 2


def test_invalid_assignments_are_explained():
    for data, text in ((b"junk", "could not be opened"), (assignment(IOA, sheet="OTHER"), "no 'IO_ASSIGNMENT' worksheet"),
                       (assignment([IOA[1]]), "no used signal rows"), (assignment(IOA, head=["A"] * 12), "TAG NUMBER")):
        with pytest.raises(AssignmentError, match=text):
            read_assignment(data)


# ── through the API ──────────────────────────────────────────────────────────
@pytest.fixture()
def client(engine, db, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app.routers import cable_schedule, deliverables
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(deliverables, "SessionLocal", sessionmaker(bind=engine))
    appx = FastAPI()
    appx.include_router(cable_schedule.router, prefix="/api")
    appx.include_router(deliverables.router, prefix="/api")
    appx.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=31, username="u", email="u@x")
    appx.dependency_overrides[get_db] = lambda: db
    cable_schedule._generated.clear()
    return TestClient(appx)


def generate(c, selection=None, io_file=None):
    files = {"iodb_file": ("IODB.xlsx", iodb())}
    if io_file is not None:
        files["io_assignment_file"] = ("ioa.xlsx", io_file)
    data = {"jb_column": "JUNCTION BOX TAG NO.", "tag_column": "TAG NO", "output_mode": "WITH_SUMMARY", "extra_sheets": "MCC DI,MCC DO"}
    if selection is not None:
        data["scope_filters"] = json.dumps(selection)
    return post_generate(c, files=files, data=data)


def texts(content):
    wb = openpyxl.load_workbook(io.BytesIO(content))
    return wb, {str(v).strip() for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for v in row if v is not None}


def test_generation_uses_one_scope_for_every_sheet_and_the_following_modules(client):
    from app.routers import cable_schedule
    from utils.file_handler import read_iodb
    g = generate(client)
    assert g.status_code == 200, g.text
    _wb, values = texts(client.get("/api/cable-schedule/download").content)
    assert {"PT-101", "PT-201", "MS-101A"} <= values and not {"PT-102", "PT-301", "MS-101B"} & values
    assert g.json()["scope"]["summary"]["eligible"] == 6
    full_name = g.json()["filename"]
    g = generate(client, {"areas": ["RO"]})
    assert g.status_code == 400 and "no DI signals from an MCC" in g.json()["detail"]      # a sheet without data, as before
    g = generate(client, {"area_codes": ["001"]}, assignment(IOA))
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["filename"] != full_name and "Code_001" in body["filename"]
    wb, values = texts(client.get("/api/cable-schedule/download").content)
    assert not {"PT-201", "PT-102"} & values and {"02", "01", "X1"} <= values
    assert body["terminals"]["total"]["resolved"] == 1 and body["terminals"]["total"]["eligible"] == 2
    summary = [row for row in wb["CABLE SUMMARY"].iter_rows(values_only=True)]
    quantities = {row[1]: row[3] for row in summary if row and len(row) > 3 and isinstance(row[3], (int, float))}
    assert quantities == {"1P": 4 * 10, "12P": 3 * 100}                # four live branch rows; MC-1, MC-9, MC-8 once each
    snap = cable_schedule.get_generated(31, None)
    stored = read_iodb(io.BytesIO(snap["iodb_bytes"]))[0]
    assert stored["TAG NO"].tolist() == ["PT-101", "PT-103", "MS-101A", "MS-101C"] and snap["scope"]["area_codes"] == ["001"]
    d = client.get("/api/cable-schedule/diagnostics")
    book = openpyxl.load_workbook(io.BytesIO(d.content))
    assert book.sheetnames == ["Scope", "Excluded Records", "Terminal Trace"] and book["Terminal Trace"].max_row > 1


def test_bad_requests_and_the_scope_endpoint(client):
    assert generate(client, {"areas": ["Nowhere"]}).status_code == 400
    assert generate(client, {"statuses": []}).status_code == 400
    r_ = generate(client, {"areas": ["Intake"], "area_codes": ["002"]})
    assert r_.status_code == 400 and "No IODB records match" in r_.json()["detail"]
    assert generate(client, io_file=b"junk").status_code == 400
    s = client.post("/api/cable-schedule/scope", files={"iodb_file": ("i.xlsx", iodb())}).json()
    assert s["summary"]["eligible"] == 6 and [a["value"] for a in s["areas"]] == ["Intake", "RO"]
    p = client.post("/api/cable-schedule/preview", files={"file": ("i.xlsx", iodb())},
                    data={"jb_column": "JUNCTION BOX TAG NO.", "tag_column": "TAG NO", "scope_filters": json.dumps({"areas": ["RO"]})})
    assert [x["junction_box"] for x in p.json()["rows"]] == ["JB-1", "JB-2"]
