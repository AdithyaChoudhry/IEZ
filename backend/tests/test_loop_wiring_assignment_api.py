"""Loop Wiring from the I/O Assignment: preview, generate (job + download), templates, validation."""
import io
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from test_loop_from_assignment import assignment, row  # noqa: E402


@pytest.fixture()
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import loop_wiring, loop_wiring_assignment
    app = FastAPI()
    app.include_router(loop_wiring.router, prefix="/api")
    app.include_router(loop_wiring_assignment.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=5, username="alice")
    return TestClient(app)


DATA = lambda: assignment([row("PT-001"), row("FT-002", wire="4 WIRE"), row("ZS-1", io_type="DI"), row("SPARE"), row("S-1", INTERFACE="SOFT")])


def test_preview_counts_types_and_explains_what_is_not_mapped(client):
    r = client.post("/api/loop-wiring/assignment/preview", files={"assignment_file": ("A.xlsx", DATA())}, data={"variant": "WITH"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["fed"] == 2 and j["by_type"] == {"2-WIRE INSTRUMENT": 1, "4-WIRE INSTRUMENT": 1} and j["skipped"] == 2
    assert {x["reason"][:12] for x in j["skipped_reasons"]} == {"I/O TYPE 'DI", "INTERFACE 'S"}
    assert j["preview"][0]["Tag_Number"] == "PT-001" and j["preview"][0]["Loop_Name"] == "L-001"


@pytest.mark.parametrize("variant", ["WITH", "WITHOUT"])
def test_generate_job_then_existing_status_and_download_endpoints(client, variant):
    r = client.post("/api/loop-wiring/assignment/generate", files={"assignment_file": ("A.xlsx", DATA())}, data={"variant": variant})
    assert r.status_code == 202, r.text
    job = r.json()["job_id"]
    for _ in range(100):
        s = client.get(f"/api/loop-wiring/generate/status/{job}").json()
        if s["status"] != "processing":
            break
        time.sleep(0.1)
    assert s["status"] == "done", s
    assert s["result"]["sheet_count"] == 2 and "2 sheet" in s["result"]["message"]
    d = client.get("/api/loop-wiring/download")
    assert d.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(d.content))
    assert wb.sheetnames == ["Loop_PT-001", "Loop_FT-002"]
    assert wb["Loop_PT-001"]["X19"].value == "L-001" and wb["Loop_PT-001"]["W19"].value == "PT-001"
    assert (wb["Loop_PT-001"]["O5"].value is None) == (variant == "WITHOUT")        # marshalling title only in the WITH template


def test_uploaded_template_is_used_instead_of_the_bundled_one(client):
    from app.routers.loop_wiring_assignment import TEMPLATE_DIR
    tmpl = (TEMPLATE_DIR / "WITHOUT_MARSHALLING_CABINET.xlsx").read_bytes()
    r = client.post("/api/loop-wiring/assignment/preview", files={"assignment_file": ("A.xlsx", DATA()), "template_file": ("T.xlsx", tmpl)},
                    data={"variant": "WITH"})
    assert r.status_code == 200 and r.json()["fed"] == 2


def test_templates_are_listed_and_downloadable(client):
    assert [t["variant"] for t in client.get("/api/loop-wiring/assignment/templates").json()] == ["WITH", "WITHOUT"]
    for v in ("WITH", "WITHOUT"):
        r = client.get(f"/api/loop-wiring/assignment/template/{v}")
        assert r.status_code == 200 and len(openpyxl.load_workbook(io.BytesIO(r.content)).sheetnames) == 8
    assert client.get("/api/loop-wiring/assignment/template/NOPE").status_code == 404


def test_bad_inputs_are_rejected_clearly(client):
    r = client.post("/api/loop-wiring/assignment/preview", files={"assignment_file": ("A.xlsx", b"not excel")})
    assert r.status_code == 400
    r = client.post("/api/loop-wiring/assignment/preview", files={"assignment_file": ("A.xlsx", DATA())}, data={"variant": "MAYBE"})
    assert r.status_code == 400 and "variant" in r.json()["detail"]
    wb = openpyxl.Workbook(); wb.active.append(["foo"]); buf = io.BytesIO(); wb.save(buf)
    r = client.post("/api/loop-wiring/assignment/preview", files={"assignment_file": ("A.xlsx", buf.getvalue())})
    assert r.status_code == 400 and "TAG NO" in r.json()["detail"]


def test_job_with_nothing_to_map_ends_in_a_clear_error(client):
    only_di = assignment([row("ZS-1", io_type="DI")])
    job = client.post("/api/loop-wiring/assignment/generate", files={"assignment_file": ("A.xlsx", only_di)}).json()["job_id"]
    for _ in range(100):
        s = client.get(f"/api/loop-wiring/generate/status/{job}").json()
        if s["status"] != "processing":
            break
        time.sleep(0.1)
    assert s["status"] == "error" and "AI with 2 WIRE or 4 WIRE" in s["error"]


def test_requires_authentication():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers.loop_wiring_assignment import router
    app = FastAPI(); app.include_router(router, prefix="/api")
    c = TestClient(app)
    assert c.get("/api/loop-wiring/assignment/templates").status_code in (401, 403)
    assert c.post("/api/loop-wiring/assignment/preview", files={"assignment_file": ("A.xlsx", b"x")}).status_code in (401, 403)
