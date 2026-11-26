"""Built-in universal Cable Schedule template: used when no template is uploaded."""
import io
import re
import sys
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.routers.cable_schedule import DEFAULT_TEMPLATE_PATH  # noqa: E402
from utils.template_processor import process_cable_schedule  # noqa: E402
from cable_header_helpers import generate as post_generate  # noqa: E402

PROJECT_WORDS = re.compile(r"GAIL|PC286|STORM|10P195|JB-101|MC-101|IC-101|PDIL|PROJECT AND DEVELOPMENT|Test data|RADAR|I0003|I0010", re.I)


@pytest.fixture()
def client():
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import cable_schedule
    app = FastAPI()
    app.include_router(cable_schedule.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, username="alice")
    return TestClient(app)


def wb():
    return openpyxl.load_workbook(DEFAULT_TEMPLATE_PATH)


def iodb(rows=6):
    data = []
    for i in range(rows):
        data.append({"TAG NO": f"PT-{i}", "JUNCTION BOX TAG NO.": f"AJB-0{1 + i // 3}", "EQUIPMENT DESCRIPTION": f"D {i}", "SIGNAL I/O TYPE": "AI",
                     "INSTRUMENT TO JB CABLE TAG NO": f"IC-{i}", "INSTRUMENT TO JB CABLE TYPE": "1PX1.5 Sqmm", "BRANCH CABLE LENGTH": 10 + i,
                     "MAIN CABLE TAG NUMBER": f"MC-{1 + i // 3}", "MAIN CABLE TYPE": "12PX1.5 Sqmm", "MAIN CABLE LENGTH(MTRS)": 200})
    b = io.BytesIO()
    pd.DataFrame(data).to_excel(b, index=False)
    return b.getvalue()


def test_default_template_has_a_blank_cover_and_the_schedule_sheet_only():
    w = wb()
    assert w.sheetnames == ["COVERSHEET", "Cable Schedule -INST"]


def test_default_template_holds_no_project_data():
    for ws in wb():
        hits = [(c.coordinate, c.value) for r in ws.iter_rows() for c in r if isinstance(c.value, str) and PROJECT_WORDS.search(c.value)]
        assert hits == [], (ws.title, hits)
    cover = wb()["COVERSHEET"]
    for a in ("A3", "G4", "H4", "J4", "K4", "M4", "N4", "F6", "F7", "G2", "E13"):
        assert cover[a].value in (None, ""), a
    assert all(cover.cell(r, 1).value in (None, "") for r in range(15, 24))      # revision table empty


def test_default_template_schedule_sheet_matches_the_current_output_header():
    ws = wb()["Cable Schedule -INST"]
    heads = [ws.cell(7, c).value for c in range(1, 25) if ws.cell(7, c).value]
    assert "FERRULE AT PLC (+)" not in heads and "FERRULE AT PLC (-)" not in heads
    assert heads[0].strip() == "SL. No." and heads[-1] == "Remarks" and "MAIN CABLE TAG NUMBER" in heads
    assert ws.max_row == 11                                                        # header + one 3-row prototype entry, no test data
    # the standard header: formulas on the cover
    assert str(ws["R3"].value).startswith("=") and "COVERSHEET" in str(ws["R3"].value)
    assert {"DOC NO", "REV NO", "DATE", "PROJECT", "CLIENT", "PMC"} <= {str(c.value) for r in ws.iter_rows(min_row=1, max_row=6) for c in r}
    # prototype keeps formulas, never sample constants
    consts = [c.coordinate for r in ws.iter_rows(min_row=9, max_row=11) for c in r
              if c.value is not None and not str(c.value).startswith("=") and c.coordinate not in ("A9", "L9", "L10", "L11")]
    assert consts == []
    assert not any(ws.cell(r, c).fill.fill_type and ws.cell(r, c).fill.fgColor.rgb == "00FFFF00" for r in range(9, 12) for c in range(1, 21))


def test_generating_with_the_default_template_works_and_keeps_the_layout():
    out, _fn, err = process_cable_schedule(io.BytesIO(iodb()), io.BytesIO(DEFAULT_TEMPLATE_PATH.read_bytes()), "JUNCTION BOX TAG NO.", "TAG NO",
                                           output_mode="WITH_SUMMARY", extra_report={})
    assert err is None, err
    book = openpyxl.load_workbook(io.BytesIO(out))
    assert book.sheetnames == ["COVERSHEET", "Cable Schedule -INST", "CABLE SUMMARY"]
    ws = book["Cable Schedule -INST"]
    assert [ws.cell(r, 2).value for r in (9, 12, 15)] == ["PT-0", "PT-1", "PT-2"]
    assert ws["K9"].value == "AJB-01"
    assert str(ws["A4"].value).startswith("=")                                       # standard header present
    # nothing of any project is left behind
    for s in book:
        for row in s.iter_rows():
            for c in row:
                assert not (isinstance(c.value, str) and PROJECT_WORDS.search(c.value)), (s.title, c.coordinate, c.value)


def test_extra_sheets_come_without_the_iez_suffix_and_with_the_same_header():
    from utils.cable_schedule_extra import parse_selection
    from test_cable_schedule_extra import COLS, iodb_rows
    b = io.BytesIO()
    pd.DataFrame(iodb_rows(), columns=COLS).to_excel(b, sheet_name="IODB", index=False)
    out, _fn, err = process_cable_schedule(io.BytesIO(b.getvalue()), io.BytesIO(DEFAULT_TEMPLATE_PATH.read_bytes()), "JUNCTION BOX TAG NO.", "TAG NO",
                                           output_mode="WITHOUT_SUMMARY", extra_sheets=parse_selection("MCC DI,VFD"), extra_report={})
    assert err is None, err
    book = openpyxl.load_workbook(io.BytesIO(out))
    assert book.sheetnames == ["COVERSHEET", "Cable Schedule -INST", "MCC DI", "VFD"]
    for n in ("Cable Schedule -INST", "MCC DI", "VFD"):
        assert str(book[n]["A4"].value).startswith("=") and book[n].row_dimensions[2].height == 40.0


def test_api_generates_without_an_uploaded_template(client):
    r = client.post("/api/cable-schedule/composition", data={"output_mode": "WITH_SUMMARY"})
    assert r.status_code == 200, r.text
    planned = [s["name"] for s in r.json()["sheets"]]
    assert planned[:2] == ["COVERSHEET", "Cable Schedule -INST"] and "CABLE SUMMARY" in planned
    g = post_generate(client, files={"iodb_file": ("I.xlsx", iodb())},
                    data={"jb_column": "JUNCTION BOX TAG NO.", "tag_column": "TAG NO", "output_mode": "WITH_SUMMARY"})
    assert g.status_code == 200, g.text
    assert g.json()["sheets"] == planned


def test_an_uploaded_template_still_wins(client):
    from test_cable_schedule_layout import template
    g = post_generate(client, files={"iodb_file": ("I.xlsx", iodb()), "template_file": ("T.xlsx", template())},
                    data={"jb_column": "JUNCTION BOX TAG NO.", "tag_column": "TAG NO", "output_mode": "WITHOUT_SUMMARY"})
    assert g.status_code == 200, g.text
    assert g.json()["sheets"] == ["Cable Schedule -INST"]
