"""Shared Session IODB: one authoritative IODB per authenticated session; replace / invalid / clear / isolation / expiry."""
import io
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SID_A, SID_B = "sessionAAAA1111", "sessionBBBB2222"


def iodb(prefix="PT", n=5) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IODB"
    ws.append(["TAG NO", "INSTRUMENT TYPE NAME", "SIGNAL I/O TYPE", "JUNCTION BOX"])
    for i in range(1, n + 1):
        ws.append([f"{prefix}-{i:03d}", f"Transmitter {i}", "AI", f"JB-{i % 2}"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def not_an_iodb() -> bytes:
    return b"this is not an excel workbook"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import shared_iodb as router_mod
    from app.services.shared_iodb import SharedIODBStore
    store = SharedIODBStore(directory=str(tmp_path / "shared"), idle_seconds=3600)
    monkeypatch.setattr(router_mod, "store", store)
    app = FastAPI()
    app.include_router(router_mod.router, prefix="/api")
    current = {"user": SimpleNamespace(id=1, username="alice")}
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    c = TestClient(app)
    return SimpleNamespace(c=c, store=store, current=current, dir=tmp_path / "shared")


def up(env, data, name="IODB.xlsx", sid=SID_A):
    return env.c.post("/api/shared-iodb", files={"file": (name, data)}, headers={"X-IEZ-Session": sid})


def info(env, sid=SID_A):
    return env.c.get("/api/shared-iodb", headers={"X-IEZ-Session": sid}).json()


def test_nothing_available_right_after_login(env):
    assert info(env) == {"available": False, "file_name": None, "uploaded_at": None, "uploaded_by": None, "status": None, "size": None}
    assert env.c.get("/api/shared-iodb/file", headers={"X-IEZ-Session": SID_A}).status_code == 404


def test_upload_becomes_shared_and_bytes_are_returned_unchanged(env):
    data = iodb()
    r = up(env, data, "Project_A_Rev01.xlsx")
    assert r.status_code == 200, r.text
    i = info(env)
    assert i["available"] and i["file_name"] == "Project_A_Rev01.xlsx" and i["status"] == "Validated" and i["uploaded_by"] == "alice"
    assert "path" not in i and "/" not in str(i["file_name"])                 # no storage internals exposed
    got = env.c.get("/api/shared-iodb/file", headers={"X-IEZ-Session": SID_A})
    assert got.status_code == 200 and got.content == data                    # exactly what was uploaded


def test_valid_new_upload_replaces_and_old_file_is_deleted(env):
    up(env, iodb("A"), "Rev01.xlsx")
    assert len(list(env.dir.glob("*.iodb"))) == 1
    up(env, iodb("B"), "Rev02.xlsx")
    assert info(env)["file_name"] == "Rev02.xlsx"
    assert len(list(env.dir.glob("*.iodb"))) == 1                             # no second copy kept
    assert env.c.get("/api/shared-iodb/file", headers={"X-IEZ-Session": SID_A}).content == iodb("B")


def test_invalid_upload_does_not_replace_the_shared_iodb(env):
    good = iodb("A")
    up(env, good, "Rev02.xlsx")
    r = up(env, not_an_iodb(), "Invalid_IO_DB.xlsx")
    assert r.status_code == 400 and "validation failed" in r.json()["detail"].lower()
    assert info(env)["file_name"] == "Rev02.xlsx"
    assert env.c.get("/api/shared-iodb/file", headers={"X-IEZ-Session": SID_A}).content == good
    assert len(list(env.dir.glob("*.iodb"))) == 1


def test_empty_workbook_is_rejected(env):
    wb = openpyxl.Workbook(); wb.active.title = "IODB"; wb.active.append(["TAG NO"])
    buf = io.BytesIO(); wb.save(buf)
    assert up(env, buf.getvalue()).status_code == 400
    assert not info(env)["available"]


def test_logout_clears_and_removes_the_file(env):
    up(env, iodb())
    assert env.c.delete("/api/shared-iodb", headers={"X-IEZ-Session": SID_A}).json()["available"] is False
    assert not info(env)["available"]
    assert list(env.dir.glob("*.iodb")) == []


def test_new_login_session_sees_no_shared_iodb(env):
    up(env, iodb(), sid=SID_A)
    assert not info(env, sid=SID_B)["available"]            # a new login = a new session id
    assert env.c.get("/api/shared-iodb/file", headers={"X-IEZ-Session": SID_B}).status_code == 404


def test_users_are_isolated_even_with_the_same_session_id(env):
    up(env, iodb("A"), "Project_A.xlsx")
    env.current["user"] = SimpleNamespace(id=2, username="bob")
    assert not info(env)["available"]
    assert env.c.get("/api/shared-iodb/file", headers={"X-IEZ-Session": SID_A}).status_code == 404
    up(env, iodb("B"), "Project_B.xlsx")
    assert info(env)["file_name"] == "Project_B.xlsx"
    env.current["user"] = SimpleNamespace(id=1, username="alice")
    assert info(env)["file_name"] == "Project_A.xlsx"
    assert env.c.get("/api/shared-iodb/file", headers={"X-IEZ-Session": SID_A}).content == iodb("A")
    env.c.delete("/api/shared-iodb", headers={"X-IEZ-Session": SID_A})       # alice logs out ...
    env.current["user"] = SimpleNamespace(id=2, username="bob")
    assert info(env)["file_name"] == "Project_B.xlsx"                         # ... bob is unaffected


def test_idle_expiry_removes_the_iodb_and_its_file(env):
    env.store.idle = 0.05
    up(env, iodb())
    time.sleep(0.1)
    assert not info(env)["available"]
    assert list(env.dir.glob("*.iodb")) == []


def test_restart_purges_orphan_files(tmp_path):
    from app.services.shared_iodb import SharedIODBStore
    d = tmp_path / "s"; d.mkdir()
    (d / "left_over.iodb").write_bytes(b"x")
    SharedIODBStore(directory=str(d), idle_seconds=60)
    assert list(d.glob("*.iodb")) == []


def test_requires_authentication():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers.shared_iodb import router
    app = FastAPI(); app.include_router(router, prefix="/api")
    c = TestClient(app)
    assert c.get("/api/shared-iodb").status_code in (401, 403)
    assert c.post("/api/shared-iodb", files={"file": ("a.xlsx", iodb())}).status_code in (401, 403)
    assert c.get("/api/shared-iodb/file").status_code in (401, 403)
    assert c.delete("/api/shared-iodb").status_code in (401, 403)


def test_missing_or_bad_session_header_is_a_safe_default_not_a_crash(env):
    assert env.c.post("/api/shared-iodb", files={"file": ("a.xlsx", iodb())}).status_code == 200
    assert env.c.get("/api/shared-iodb").json()["available"]
    assert env.c.get("/api/shared-iodb", headers={"X-IEZ-Session": "../../etc/passwd"}).json()["available"]   # sanitised to "default"
    assert list(env.dir.glob("*.iodb")) and all(p.parent == env.dir for p in env.dir.glob("*"))


def test_generators_get_the_same_bytes_as_a_direct_upload(env):
    """The stored file, handed to an existing generator, gives the same result as uploading it directly."""
    from utils.template_processor import analyze_iodb_for_list
    data = iodb(n=8)
    up(env, data)
    stored = env.c.get("/api/shared-iodb/file", headers={"X-IEZ-Session": SID_A}).content
    a, err_a = analyze_iodb_for_list(io.BytesIO(data), "io_list")
    b, err_b = analyze_iodb_for_list(io.BytesIO(stored), "io_list")
    assert err_a is None and err_b is None and a == b
