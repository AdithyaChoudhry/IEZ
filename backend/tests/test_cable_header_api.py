"""Cable Schedule header through the API: linked-cover metadata, asking only for what is missing, validation, one consistent output workbook."""
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cable_header_helpers import fake_snapshot, make_cover, no_cover_snapshot  # noqa: E402
from test_cable_schedule_extra import iodb  # noqa: E402

ALL = {"jb_column": "JUNCTION BOX TAG NO.", "tag_column": "TAG NO", "output_mode": "WITH_SUMMARY"}
STATE = {}


@pytest.fixture()
def client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import cable_schedule
    app = FastAPI()
    app.include_router(cable_schedule.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, username="alice")
    STATE.clear()
    STATE["snap"] = fake_snapshot(make_cover())
    monkeypatch.setattr(cable_schedule.cable_cover, "snapshot", lambda project_id, tpl=None: STATE["snap"])
    cable_schedule._generated.clear()
    cable_schedule.cable_schedule_cache.clear()                    # a module-level cache: no earlier test's output may answer /download
    return TestClient(app)


def meta(c, **data):
    r = c.post("/api/cable-schedule/header-metadata", data={"project_id": "PRJ-1", **data})
    assert r.status_code == 200, r.text
    return r.json()


def gen(c, overrides=None, fingerprint=None, **data):
    d = {**ALL, "project_id": "PRJ-1", **data}
    if overrides is not None:
        d["header_overrides"] = json.dumps(overrides)
        d["header_fingerprint"] = fingerprint if fingerprint is not None else meta(c)["fingerprint"]
    return c.post("/api/cable-schedule/generate", files={"iodb_file": ("I.xlsx", iodb())}, data=d)


def output(c):
    return openpyxl.load_workbook(io.BytesIO(c.get("/api/cable-schedule/download").content))


def by_key(m):
    return {f["key"]: f for f in m["fields"]}


# ── 30.2 / 30.3 ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_cover_supplies_everything_but_the_location_and_only_the_location_is_requested(client):
    m = meta(client)
    f = by_key(m)
    assert [k for k, v in f.items() if v["status"] != "ok"] == ["location"] and not m["complete"]
    assert f["project"]["value"] == "SETTING UP OF A POND, ZLD PLANT" and f["doc_no"]["value"] == "10P195-I0010-201"
    assert (f["revision"]["value"], f["date"]["value"], f["pmc"]["value"], f["client"]["value"]) == ("02", "24-11-2026", "PDIL", "GAIL (INDIA) LTD")
    assert m["cover"]["available"] and m["cover"]["document_number"] == "PC286-10P195-I0010-201"


def test_generating_without_the_missing_details_is_refused_and_names_them(client):
    r = gen(client)
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["code"] == "HEADER_METADATA_INCOMPLETE" and "LOCATION" in d["message"] and "PROJECT" not in d["message"]
    assert [f["key"] for f in d["header"]["fields"] if f["status"] != "ok"] == ["location"]
    assert client.get("/api/cable-schedule/download").status_code == 404                  # nothing was produced


def test_confirmed_details_produce_one_workbook_with_the_cover_first_and_consistent_headers(client):
    r = gen(client, {"location": "Gujarat, India"}, extra_sheets="MCC DI,VFD")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["header"]["sources"]["location"] == "manual" and body["header"]["sources"]["client"] == "cover"
    wb = output(client)
    assert wb.sheetnames == ["COVERSHEET", "Cable Schedule -INST", "MCC DI", "VFD", "CABLE SUMMARY"] == body["sheets"]
    for name in wb.sheetnames[1:]:
        ws = wb[name]
        col = 13 if name in ("Cable Schedule -INST", "MCC DI") else (14 if name == "VFD" else 3)
        assert ws["A5"].value == "LOCATION : Gujarat, India" and ws["A3"].value == "CLIENT : GAIL (INDIA) LTD"
        assert [ws.cell(r_, col).value for r_ in (3, 4, 5)] == ["DOCUMENT NO. : 10P195-I0010-201", "DATE : 24-11-2026", "REVISION : 02"]
    assert body["filename"] == "PC286-10P195-I0010-201_02_Cable_Schedule.xlsx"            # the existing naming convention, from the resolved document


def test_the_linked_cover_sheet_itself_is_not_changed(client):
    before = openpyxl.load_workbook(io.BytesIO(STATE["snap"]["cover"])).worksheets[0]
    expected = {c.coordinate: c.value for row in before.iter_rows() for c in row if c.value is not None}
    assert gen(client, {"location": "Gujarat, India"}).status_code == 200
    ws = output(client)["COVERSHEET"]
    got = {c.coordinate: c.value for row in ws.iter_rows() for c in row if c.value is not None}
    assert got == expected
    assert "Gujarat" not in " ".join(str(v) for v in got.values())


# ── 30.4 / 30.5 ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_missing_revision_date_is_asked_for_and_the_clock_is_never_used(client):
    revs = [{"rev_no": "00", "date": "", "description": "x", "prepared_by": "a", "checked_by": "b", "approved_by": "c"}]
    STATE["snap"] = fake_snapshot(make_cover(revs=revs), revision="00")
    f = by_key(meta(client))
    assert f["date"]["status"] == "missing" and f["revision"]["status"] == "ok" and f["revision"]["value"] == "00"
    assert gen(client, {"location": "L"}).status_code == 422
    r = gen(client, {"location": "L", "date": "2026-11-24"})
    assert r.status_code == 200, r.text
    ws = output(client)["Cable Schedule -INST"]
    assert ws["M4"].value == "DATE : 24-11-2026" and ws["M5"].value == "REVISION : 00"            # the leading zero is kept


def test_pmc_can_be_confirmed_as_not_applicable_once(client):
    STATE["snap"] = fake_snapshot(make_cover(pmc=""))
    m = meta(client)
    assert [k for k, v in by_key(m).items() if v["status"] != "ok"] == ["pmc", "location"] and by_key(m)["pmc"]["allow_na"]
    assert gen(client, {"pmc": "N/A", "location": "L"}).status_code == 200
    assert output(client)["Cable Schedule -INST"]["A4"].value == "PMC : N/A"
    again = meta(client, header_overrides=json.dumps({"pmc": "N/A", "location": "L"}))
    assert again["complete"]                                                                          # not asked again


def test_conflicting_revision_information_is_sent_for_review_not_guessed(client):
    def edit(ws):
        ws["N4"] = "07"
    STATE["snap"] = fake_snapshot(make_cover(edit=edit), revision="07")
    f = by_key(meta(client))
    assert f["revision"]["status"] == "conflict" and f["date"]["status"] == "conflict"
    r = gen(client, {"location": "L"})
    assert r.status_code == 422
    assert gen(client, {"location": "L", "revision": "02", "date": "24-11-2026"}).status_code == 200


# ── 16 backend validation ────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["TBD", "XXXX", "[Confirm location]", "   "])
def test_placeholder_input_is_refused_by_the_backend(client, bad):
    r = gen(client, {"location": bad})
    assert r.status_code == 422 and by_key(r.json()["detail"]["header"])["location"]["status"] in ("invalid", "missing")


def test_an_invalid_date_is_refused(client):
    revs = [{"rev_no": "00", "date": "", "description": "x", "prepared_by": "a", "checked_by": "b", "approved_by": "c"}]
    STATE["snap"] = fake_snapshot(make_cover(revs=revs), revision="00")
    r = gen(client, {"location": "L", "date": "2026-13-45"})
    assert r.status_code == 422 and by_key(r.json()["detail"]["header"])["date"]["status"] == "invalid"


def test_input_for_a_field_the_cover_holds_is_ignored(client):
    r = gen(client, {"location": "L", "client": "SOMEONE ELSE"})
    assert r.status_code == 200
    assert output(client)["Cable Schedule -INST"]["A3"].value == "CLIENT : GAIL (INDIA) LTD"


def test_details_confirmed_for_another_cover_or_project_are_refused(client):
    fp = meta(client)["fingerprint"]
    STATE["snap"] = fake_snapshot(make_cover(client="ANOTHER CLIENT"))                     # the cover changed after the user confirmed
    r = gen(client, {"location": "L"}, fingerprint=fp)
    assert r.status_code == 409 and "changed" in r.json()["detail"]
    STATE["snap"] = fake_snapshot(make_cover())
    r = client.post("/api/cable-schedule/generate", files={"iodb_file": ("I.xlsx", iodb())},
                    data={**ALL, "project_id": "PRJ-OTHER", "header_overrides": json.dumps({"location": "L"}), "header_fingerprint": fp})
    assert r.status_code == 409                                                           # same cover values, other project: still not reusable


def test_confirmed_details_without_a_fingerprint_and_unknown_fields_are_rejected(client):
    r = client.post("/api/cable-schedule/generate", files={"iodb_file": ("I.xlsx", iodb())},
                    data={**ALL, "project_id": "PRJ-1", "header_overrides": json.dumps({"location": "L"})})
    assert r.status_code == 400
    r = client.post("/api/cable-schedule/header-metadata", data={"project_id": "PRJ-1", "header_overrides": json.dumps({"colour": "red"})})
    assert r.status_code == 400
    r = client.post("/api/cable-schedule/header-metadata", data={"project_id": "PRJ-1", "header_overrides": "not json"})
    assert r.status_code == 400


def test_without_a_linked_cover_every_detail_is_requested_and_nothing_is_invented(client):
    STATE["snap"] = no_cover_snapshot()
    m = meta(client)
    assert not m["cover"]["available"] and [f["status"] for f in m["fields"]] == ["missing"] * 7 and not m["complete"]
    assert "Select a project" in m["cover"]["message"]
    assert gen(client).status_code == 422
    full = {"project": "P", "client": "C", "doc_no": "10P1-I1-001", "pmc": "N/A", "date": "01-02-2026", "location": "L", "revision": "A"}
    assert gen(client, full).status_code == 200
    assert output(client)["Cable Schedule -INST"]["M5"].value == "REVISION : A"


def test_manual_values_never_leak_between_projects_or_requests(client):
    assert gen(client, {"location": "ALPHA TOWN"}).status_code == 200
    STATE["snap"] = fake_snapshot(make_cover(client="BRAVO CLIENT", project="BRAVO PROJECT"), project_id="PRJ-2")
    f = by_key(meta(client, project_id="PRJ-2"))
    assert f["location"]["status"] == "missing" and f["client"]["value"] == "BRAVO CLIENT"           # nothing carried over
    assert gen(client).status_code == 422


def test_the_header_template_error_is_reported(client, monkeypatch):
    from utils import cable_header_v3 as HV
    def boom():
        raise HV.TemplateError("The approved Cable Schedule header template is not available (x).")
    monkeypatch.setattr(HV, "load_template", boom)
    r = client.post("/api/cable-schedule/header-metadata", data={"project_id": "PRJ-1"})
    assert r.status_code == 500 and "header template" in r.json()["detail"]
    r = client.post("/api/cable-schedule/generate", files={"iodb_file": ("I.xlsx", iodb())}, data={**ALL, "project_id": "PRJ-1"})
    assert r.status_code == 500 and "header template" in r.json()["detail"]
