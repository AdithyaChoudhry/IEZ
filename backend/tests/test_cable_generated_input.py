"""The generated Cable Schedule is the only Cable Schedule input of the Gland Quantity, Cable Lug Quantity and Drum
Schedule generators: shared server side per (user, project), same results as the old upload routes, refreshed on
regeneration, never another user's or project's workbook."""
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_cable_complete import iodb, template  # noqa: E402
from test_drum_schedule import lot, master  # noqa: E402

USER = {"u": SimpleNamespace(id=71, username="alice")}


@pytest.fixture()
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import cable_schedule, drum_schedule, gland_quantity, lug_quantity
    cable_schedule._generated.clear()
    USER["u"] = SimpleNamespace(id=71, username="alice")
    app = FastAPI()
    for r in (cable_schedule, gland_quantity, lug_quantity, drum_schedule):
        app.include_router(r.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: USER["u"]
    yield TestClient(app)
    cable_schedule._generated.clear()


IODB = iodb()
TPL = template()
MASTER = master([lot("DM-1", "1PX1.5 Sqmm", "NIS", 500, 2, "YES"), lot("DM-2", "2PX1.5 Sqmm", "NIS", 500, 1, "NO"),
                 lot("DM-3", "12PX1.5 Sqmm", "NIS", 1000, 1, "YES")])


def generate(c, project=None, jbs=None, jb_column="JUNCTION BOX TAG NO."):
    data = {"jb_column": jb_column, "tag_column": "TAG NO", "output_mode": "WITH_SUMMARY", "include_schedule": "true"}
    if project:
        data["project_id"] = project
    if jbs:
        data["selected_jbs"] = json.dumps(jbs)
    return c.post("/api/cable-schedule/generate", files={"iodb_file": ("IODB_Test.xlsx", IODB), "template_file": ("tpl.xlsx", TPL)}, data=data)


def meta(c, project=None):
    return c.get("/api/cable-schedule/generated", params={"project_id": project} if project else {}).json()


def lug_result(c, resp):
    job = resp.json()["job_id"]
    for _ in range(300):
        j = c.get(f"/api/cable-schedule/lug/job/{job}").json()
        if j["status"] != "processing":
            return j
        time.sleep(0.1)
    raise AssertionError("lug job did not finish")


def test_nothing_generated_blocks_all_three_with_a_clear_message(client):
    m = meta(client)
    assert m["available"] is False and "generate a Cable Schedule" in m["message"]
    for url in ("/api/cable-schedule/gland/generated/detect", "/api/cable-schedule/lug/generated/detect",
                "/api/cable-schedule/drum/generated/demand"):
        r = client.post(url, data={})
        assert r.status_code == 404 and "No generated Cable Schedule" in r.json()["detail"]
    r = client.post("/api/cable-schedule/drum/generated/generate", files={"drum_master_file": ("m.xlsx", MASTER)}, data={})
    assert r.status_code == 404


def test_generation_publishes_metadata_only_and_keeps_the_download(client):
    assert generate(client).status_code == 200
    m = meta(client)
    assert m["available"] and m["filename"] == "Cable_Schedule.xlsx" and m["iodb_filename"] == "IODB_Test.xlsx"
    assert "Cable Schedule -INST" in m["sheets"] and len(m["id"]) == 32
    assert not any(isinstance(v, (bytes, bytearray)) for v in m.values()) and "bytes" not in m and "iodb_bytes" not in m
    dl = client.get("/api/cable-schedule/download")
    assert dl.status_code == 200 and dl.content[:2] == b"PK"


def test_gland_from_the_generated_schedule_equals_the_upload_route(client):
    generate(client)
    gid = meta(client)["id"]
    sched = client.get("/api/cable-schedule/download").content
    new = client.post("/api/cable-schedule/gland/generated/detect", data={"generated_id": gid}).json()
    old = client.post("/api/cable-schedule/gland/detect", files={"file": ("Cable_Schedule.xlsx", sched)}).json()
    assert {k: v for k, v in new.items() if k != "source"} == old
    settings = json.dumps({"sheets": old["default_sheets"], "default_qty": "", "repeated_rows": "once"})
    a = client.post("/api/cable-schedule/gland/generated/analyze", data={"generated_id": gid, "settings": settings}).json()
    b = client.post("/api/cable-schedule/gland/analyze", files={"file": ("Cable_Schedule.xlsx", sched)}, data={"settings": settings}).json()
    assert a["totals"] == b["totals"] and a["summary"] == b["summary"] and a["cable_wise"] == b["cable_wise"]
    assert a["source"]["name"] == "Cable_Schedule.xlsx" and a["source"]["id"] == gid


def test_lug_from_the_generated_schedule_equals_the_upload_route(client):
    generate(client)
    gid = meta(client)["id"]
    sched = client.get("/api/cable-schedule/download").content
    new = client.post("/api/cable-schedule/lug/generated/detect", data={"generated_id": gid}).json()
    old = client.post("/api/cable-schedule/lug/detect", files={"file": ("Cable_Schedule.xlsx", sched)}).json()
    assert {k: v for k, v in new.items() if k != "source"} == old
    a = lug_result(client, client.post("/api/cable-schedule/lug/generated/start", data={"generated_id": gid}))
    b = lug_result(client, client.post("/api/cable-schedule/lug/start", files={"file": ("Cable_Schedule.xlsx", sched)}))
    assert a["status"] == b["status"] == "done"
    assert a["result"]["kpis"] == b["result"]["kpis"] and a["result"]["cable_wise"] == b["result"]["cable_wise"]
    assert a["result"]["source"]["id"] == gid


def test_drum_from_the_generated_schedule_equals_the_iodb_route(client):
    generate(client)
    gid = meta(client)["id"]
    dn = client.post("/api/cable-schedule/drum/generated/demand", data={"generated_id": gid}).json()
    do = client.post("/api/cable-schedule/drum/demand", files={"iodb_file": ("IODB.xlsx", IODB)}).json()
    assert dn["stats"]["demand"] == do["stats"]["demand"] > 0 and dn["cable_types"] == do["cable_types"]
    assert dn["stats"]["not_in_schedule"] == 0
    a = client.post("/api/cable-schedule/drum/generated/generate", files={"drum_master_file": ("m.xlsx", MASTER)},
                    data={"generated_id": gid, "min_residual": "10", "use_master_split": "true"}).json()
    b = client.post("/api/cable-schedule/drum/generate", files={"iodb_file": ("IODB.xlsx", IODB), "drum_master_file": ("m.xlsx", MASTER)},
                    data={"min_residual": "10", "use_master_split": "true"}).json()
    for k in ("totals", "schedule", "summary", "utilization", "shortage", "excess"):
        assert a[k] == b[k], k
    assert a["source"]["name"] == "Cable_Schedule.xlsx"


def test_drum_schedules_only_the_cables_of_the_generated_schedule(client):
    generate(client, jbs=["JB-1"])
    d = client.post("/api/cable-schedule/drum/generated/demand", data={}).json()
    assert d["stats"]["not_in_schedule"] == 2                           # IC-3 and MC-2 belong to JB-2
    assert d["stats"]["demand"] == 3                                    # IC-1, IC-2, shared MC-1
    assert any("Not in the generated Cable Schedule" in i["kind"] for i in d["issues"])


def test_regeneration_replaces_the_input_and_refuses_the_old_id(client):
    generate(client)
    first = meta(client)["id"]
    generate(client, jbs=["JB-1"])
    second = meta(client)
    assert second["id"] != first and second["selected_jbs"] == 1
    r = client.post("/api/cable-schedule/gland/generated/detect", data={"generated_id": first})
    assert r.status_code == 409 and "newer Cable Schedule" in r.json()["detail"]
    r = client.post("/api/cable-schedule/lug/generated/start", data={"generated_id": first})
    assert r.status_code == 409


def test_failed_generation_keeps_the_last_good_schedule(client):
    generate(client)
    good = meta(client)["id"]
    bad = generate(client, jb_column="NO SUCH COLUMN")
    assert bad.status_code >= 400
    assert meta(client)["id"] == good


def test_projects_are_separate_and_never_fall_back(client):
    generate(client, project="PRJ-A")
    assert meta(client, "PRJ-A")["available"] and meta(client, "PRJ-A")["project_id"] == "PRJ-A"
    assert meta(client)["available"] is False and meta(client, "PRJ-B")["available"] is False
    assert client.post("/api/cable-schedule/drum/generated/demand", data={"project_id": "PRJ-B"}).status_code == 404
    assert client.post("/api/cable-schedule/drum/generated/demand", data={"project_id": "PRJ-A"}).status_code == 200


def test_users_never_see_each_others_schedule(client):
    generate(client, project="PRJ-A")
    gid = meta(client, "PRJ-A")["id"]
    USER["u"] = SimpleNamespace(id=72, username="bob")
    assert meta(client, "PRJ-A")["available"] is False
    r = client.post("/api/cable-schedule/gland/generated/analyze", data={"project_id": "PRJ-A", "generated_id": gid})
    assert r.status_code == 404
