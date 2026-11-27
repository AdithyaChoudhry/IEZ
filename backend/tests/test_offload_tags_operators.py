"""Large uploads do not stall other requests; revised-tag IODBs are read by their revised tags; the operators offered by the
Dynamic Rules Manager fire."""
import asyncio
import io
import sys
import threading
import time
from pathlib import Path

import openpyxl
import pandas as pd
import pytest
from fastapi import FastAPI, File, HTTPException, UploadFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.offload import off_main_loop  # noqa: E402
from utils.dynamic_rules import DynamicRule, run_dynamic_rules  # noqa: E402
from utils.file_handler import read_iodb, revised_tag_column  # noqa: E402


def test_a_slow_upload_leaves_the_server_answering_and_errors_pass_through():
    app = FastAPI()
    release = threading.Event()

    @app.post("/slow")
    @off_main_loop
    async def slow(file: UploadFile = File(...)):
        data = await file.read()
        release.wait(5)                                    # blocking work, like parsing a large workbook
        if data == b"bad":
            raise HTTPException(400, "bad file")
        return {"bytes": len(data)}

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async def scenario():
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            task = asyncio.create_task(c.post("/slow", files={"file": ("a", b"x" * 100)}))
            await asyncio.sleep(0.2)
            started = time.time()
            assert (await c.get("/ping")).json() == {"ok": True}
            assert time.time() - started < 1 and not task.done()
            release.set()
            assert (await task).json() == {"bytes": 100}
            r = await c.post("/slow", files={"file": ("a", b"bad")})
            assert r.status_code == 400 and r.json()["detail"] == "bad file"

    asyncio.run(scenario())


def _book(headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IODB - Format"
    ws.append(headers)
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_the_revised_tag_column_is_the_tag_column_only_when_there_is_no_plain_one():
    data = _book(["TAG NO(REV A)", "REVISEDTAGNO(REVA)", "SERVICE"], [["PT-1", "PT - 101", "a"], ["PT-2", None, "b"]])
    df, err = read_iodb(io.BytesIO(data))
    assert err is None and list(df.columns) == ["TAG NO(REV A)", "REVISEDTAGNO(REVA)", "SERVICE", "TAG NO"]
    assert df["TAG NO"].tolist()[0] == "PT - 101" and pd.isna(df["TAG NO"].tolist()[1])         # nothing borrowed from REV A
    assert "TAG NO" not in read_iodb(io.BytesIO(data), revised_tag=False)[0].columns
    assert revised_tag_column(["TAG NO", "REVISED TAG NO"]) is None
    plain, _ = read_iodb(io.BytesIO(_book(["TAG NO", "SERVICE"], [["PT-1", "a"]])))
    assert list(plain.columns) == ["TAG NO", "SERVICE"]


@pytest.mark.parametrize("operator,value,flagged", [
    ("!contains", "BAD", ["BAD-1"]), ("contains", "OK", ["BAD-1", ""]), ("in", "OK-1,OK-2", ["BAD-1"]),
    ("!in", "BAD-1", ["BAD-1"]), ("!empty", "", [""]), ("empty", "", ["OK-1", "BAD-1"]),
])
def test_screen_operators_fire(operator, value, flagged):
    df = pd.DataFrame({"TAG NO": ["OK-1", "BAD-1", ""]})
    rule = DynamicRule(name="r", conditions=[{"column": "TAG NO", "operator": operator, "value": value}])
    got = [df["TAG NO"].iloc[e["row"] - 2] for e in run_dynamic_rules(df, [rule], tag_col="TAG NO")]
    if operator == "contains":                              # a blank cell is left to the empty-cell rule, as before
        flagged = ["BAD-1"]
    assert got == flagged
