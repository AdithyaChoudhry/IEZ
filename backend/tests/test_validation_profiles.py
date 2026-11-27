"""IODB Validator: IO TYPE '-' is exempt from AJB/DJB routing, and custom rule profiles really control the validation."""
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import app.models.validation_profile  # noqa: F401,E402
from app.deps import get_current_user, get_db, require_lead  # noqa: E402
from utils import validation_profiles as VP  # noqa: E402
from utils.template_processor import process_iodb_validation  # noqa: E402

HEAD = ["S.NO", "TAG NO", "INSTRUMENT TYPE NAME", "SIGNAL I/O TYPE", "SUB SYSTEM", "JUNCTION BOX TAG NO.", "SERVICE", "FAIL ACTION"]
ROWS = [
    [1, "PG-101", "PRESSURE GAUGE", "-", "-", "-", "x", None],
    [2, "TG-102", "TEMPERATURE GAUGE", "  -  ", "-", None, None, None],      # SERVICE blank: another rule still applies
    [3, "LI-103", "LOCAL INDICATOR", "-", "-", "ANYTHING", "x", None],
    [4, "PIT-104", "PT", "AI", "-", "20-AJB-01", "x", None],
    [5, "PS-105", "PS", "DI", "-", "20-DJB-01", "x", None],
    [6, "PIT-106", "PT", "AI", "-", "20-DJB-01", "x", None],                  # wrong box
    [7, "PS-107", "PS", "DI", "-", None, "x", "XX"],                          # no box, bad fail action
    [8, "XX-108", "X", None, "-", None, "x", None],                           # blank IO type
    [9, "XX-109", "X", "ZZ", "-", None, "x", None],                           # unknown IO type
    [10, "MOV-110", "MOV", "DO", "MCC", None, "x", None],                     # routed through a sub-system
]


def iodb(rows=ROWS) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IODB"
    ws.append(HEAD)
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def run(config=None, empty=False, data=None):
    profile = VP.Profile(config, "P", 1, custom=True) if config is not None else None
    log, _h, _t, errors, err = process_iodb_validation(data or iodb(), validate_empty_cells=empty, profile=profile)
    return log, errors, err


def tags(errors, rid="6"):
    return sorted(e["tag"] for e in errors if e["rule_id"] == rid)


def test_default_routing_exempts_hyphen_only_and_keeps_every_other_check():
    _l, errors, err = run(empty=True)
    assert err is None
    assert tags(errors) == ["PIT-106", "PS-107"]                              # '-' never; blank / unknown / sub-system unchanged
    assert "TG-102" in tags(errors, "1") and "XX-108" in tags(errors, "1")     # other rules still apply to exempt records
    assert tags(errors, "9") == ["PS-107"]
    assert all(e["severity"] == "error" for e in errors)


def test_disable_severity_message_applicability_exception_and_accepted_values():
    assert tags(run({"rules": {"6": {"enabled": False}}})[1]) == []
    e = [x for x in run({"rules": {"6": {"severity": "warning", "message": "Check the box"}}})[1] if x["rule_id"] == "6"]
    assert {(x["severity"], x["message"]) for x in e} == {("warning", "Check the box")}
    only_ai = {"rules": {"6": {"apply_when": {"match": "all", "conditions": [{"field": "SIGNAL I/O TYPE", "operator": "equals", "value": "AI"}]}}}}
    assert tags(run(only_ai)[1]) == ["PIT-106"]
    exc = {"rules": {"6": {"exceptions": [{"field": "TAG NO", "operator": "starts_with", "value": "PS-"}]}}}
    assert tags(run(exc)[1]) == ["PIT-106"]
    own = {"rules": {"6": {"params": {"ai_jb": ["AJB", "*-DJB-*"]}}}}                       # another naming convention
    assert tags(run(own)[1]) == ["PS-107"]
    fail = {"rules": {"9": {"params": {"allowed": ["XX"]}}}}
    assert tags(run(fail)[1], "9") == []
    assert tags(run({"rules": {}})[1]) == tags(run()[1])                       # restoring the default restores the results


def test_bad_configurations_are_rejected_and_unknown_fields_stop_the_run():
    for bad in ({"rules": {"99": {}}}, {"rules": {"6": {"severity": "fatal"}}}, {"rules": {"6": {"code": "import os"}}},
                {"rules": {"6": {"exceptions": [{"field": "TAG NO", "operator": "eval", "value": "1"}]}}},
                {"rules": {"6": {"exceptions": [{"field": "S.NO", "operator": "gt", "value": "abc"}]}}},
                {"rules": {"6": {"params": {"ai_jb": []}}}}):
        with pytest.raises(VP.ProfileError):
            VP.clean_config(bad)
    _l, errors, err = run({"rules": {"6": {"exceptions": [{"field": "NO SUCH COLUMN", "operator": "is_blank"}]}}})
    assert errors == [] and "NO SUCH COLUMN" in err


def test_report_names_the_profile_used():
    log, _e, _x = run({"rules": {"6": {"enabled": False}, "9": {"severity": "information"}}})
    wb = openpyxl.load_workbook(io.BytesIO(log))
    info = {r[0].value: r[1].value for r in wb["Rule Profile"].iter_rows() if r[0].value}
    assert "CUSTOM" in info["Validation Profile"] and info["Disabled Rules"] == 1 and info["Modified Rules"] == 2
    assert info["Information"] == 1 and wb["Validation Report"]["G1"].value == "Severity"
    default = openpyxl.load_workbook(io.BytesIO(run()[0]))["Rule Profile"]
    assert default["B1"].value == VP.DEFAULT_PROFILE_NAME


@pytest.fixture()
def client(engine, db):
    from app.routers import validation_profiles, validator
    appx = FastAPI()
    appx.include_router(validator.router, prefix="/api")
    appx.include_router(validation_profiles.router, prefix="/api")
    user = SimpleNamespace(id=7, username="lead", email="l@x")
    appx.dependency_overrides[get_current_user] = lambda: user
    appx.dependency_overrides[require_lead] = lambda: user
    appx.dependency_overrides[get_db] = lambda: db
    c = TestClient(appx)
    c.appx = appx
    return c


def validate(c, **data):
    r = c.post("/api/validator/validate", files={"file": ("i.xlsx", iodb())}, data=data)
    if r.status_code != 202:
        return r
    return c.get(f"/api/validator/validate/status/{r.json()['job_id']}").json()


def test_profiles_are_saved_versioned_and_kept_to_their_project(client):
    cfg = {"rules": {"6": {"enabled": False}}}
    r = client.post("/api/validator/profiles", json={"name": "Preliminary", "project_id": "PRJ-A", "config": cfg})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert client.post("/api/validator/profiles", json={"name": "preliminary", "project_id": "PRJ-A", "config": {}}).status_code == 409
    assert client.post("/api/validator/profiles", json={"name": VP.DEFAULT_PROFILE_NAME, "project_id": "PRJ-A"}).status_code == 409
    assert [p["name"] for p in client.get("/api/validator/profiles", params={"project_id": "PRJ-A"}).json()] == ["Preliminary"]
    assert client.get("/api/validator/profiles", params={"project_id": "PRJ-B"}).json() == []
    done = validate(client, profile_id=pid, project_id="PRJ-A")["result"]
    assert done["profile"]["custom"] and done["profile"]["disabled_rules"] == 1 and not [e for e in done["errors"] if e["rule"] == 6]
    assert validate(client, profile_id=pid, project_id="PRJ-B").status_code == 409
    assert validate(client, profile_id=999, project_id="PRJ-A").status_code == 404
    default = validate(client)["result"]                                       # the default is untouched by the custom profile
    assert not default["profile"]["custom"] and [e for e in default["errors"] if e["rule"] == 6]
    body = {"name": "Preliminary", "project_id": "PRJ-A", "config": {}, "expected_version": 1}
    assert client.put(f"/api/validator/profiles/{pid}", json=body).json()["version"] == 2
    assert client.put(f"/api/validator/profiles/{pid}", json=body).status_code == 409          # stale version
    assert client.delete(f"/api/validator/profiles/{pid}", params={"project_id": "PRJ-A"}).status_code == 204
    assert validate(client, profile_id=pid, project_id="PRJ-A").status_code == 404
    assert [v["version"] for v in client.get(f"/api/validator/profiles/{pid}/history").json()] == [2, 1]


def test_only_lead_roles_may_change_profiles(client):
    client.appx.dependency_overrides.pop(require_lead)
    r = client.post("/api/validator/profiles", json={"name": "N", "project_id": "PRJ-A", "config": {}})
    assert r.status_code == 403
    assert client.get("/api/validator/rules-catalogue").json()["can_edit"] is False


def test_preview(client):
    def preview(record, config=None):
        return client.post("/api/validator/preview-rule", json={"rule_id": "6", "config": config or {}, "record": record}).json()
    base = {"TAG NO": "PI-101", "SUB SYSTEM": "-", "JUNCTION BOX TAG NO.": ""}
    assert preview({**base, "SIGNAL I/O TYPE": "-"})["result"] == "NOT APPLICABLE"
    assert preview({**base, "SIGNAL I/O TYPE": "AI"})["result"] == "ERROR"
    assert preview({**base, "SIGNAL I/O TYPE": "AI"}, {"rules": {"6": {"severity": "warning"}}})["result"] == "WARNING"
