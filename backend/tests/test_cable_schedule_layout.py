"""Instrument Cable Schedule layout per the 'Cable_Schedule-12' reference mark-up: red columns removed, Main Cable Length
kept, one 3-row entry per tag (no blank gap rows), TB 1-2-3 per tag numbered within each JB, combined instrument-side
ferrule (+ above -), JB selection with every tag of the JB; and the JB preview API."""
import io
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest

from utils.cable_schedule_layout import jb_groups, rewrite_formula
from utils.template_processor import process_cable_schedule

HEAD = ["SL. No.  ", "TAG NUMBER", "LOOP NUMBER", "EQUIPMENT DESCRIPTION", "SIGNAL I/O TYPE", "P&ID NO.", "SIGNAL TO",
        "INSTRUMENT TO JB CABLE TAG NO", "INSTRUMENT TO JB CABLE", "BRANCH CABLE LENGTH", "INSTRUMENT SIDE GLAND SIZE",
        "INSTRUMENT SIDE GLAND QTY", "FERRULE AT INSTRUMENT SIDE (+)", "FERRULE AT INSTRUMENT SIDE (-)", "JB TAG No.",
        "TB DETAILS AT JB", "JB SIDE GLAND SIZE", "JB SIDE GLAND QTY", "MAIN CABLE TAG NUMBER", "MAIN CABLE TYPE",
        "MAIN CABLE LENGTH(Mtrs)", "JB END GLAND SIZE", "PANEL END GLAND SIZE", "FERRULE AT PLC (+)", "FERRULE AT PLC (-)",
        "IO PANEL", "IO\nTYPE", "RACK / NODE ", "SLOT", "CHANNEL NO", "TERMINAL STRIP NO", "TERMINAL NO(CMN)",
        "TERMINAL NO(Signal)", "TERMINAL NO(Zero)", "Remarks"]
RED = {"LOOP NUMBER", "P&ID NO.", "SIGNAL TO", "IO PANEL", "IO\nTYPE", "RACK / NODE ", "SLOT", "CHANNEL NO",
       "TERMINAL STRIP NO", "TERMINAL NO(CMN)", "TERMINAL NO(Signal)", "TERMINAL NO(Zero)"}


def template() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cable Schedule -INST"
    ws.merge_cells("A1:AI2")
    ws["A3"], ws["E3"] = "PROJECT", "XXXX"
    ws.merge_cells("A3:D3"); ws.merge_cells("E3:AI3")
    ws["A4"], ws["E4"], ws["AF4"], ws["AG4"] = "CLIENT", "XXXX", "WABAG DOC NO.", "XXXX"
    ws.merge_cells("A4:D4"); ws.merge_cells("E4:AE4"); ws.merge_cells("AG4:AI4")
    ws["A6"], ws["AF6"], ws["AG6"] = "INSTRUMENT CABLE SCHEDULE", "DATE", "XXXX"
    ws.merge_cells("A6:AE6"); ws.merge_cells("AG6:AI6")
    for i, h in enumerate(HEAD, start=1):
        ws.cell(7, i, h)
        ws.merge_cells(start_row=7, start_column=i, end_row=8, end_column=i)
    proto = {"J": "=23+2+2", "M": '=CONCATENATE(P9,"-",O9,"/",B9,"(+)")', "N": '=CONCATENATE(P9+1,"-",O9,"/",B9,"(-)")',
             "P": 1, "Q": "=K9", "R": "=L9", "U": "=98+210", "X": '=CONCATENATE(B9,"/",O9,"-",P9,"/",Z9,"-",AE9)',
             "Y": '=CONCATENATE(B9,"/",O9,"-",P9+1,"/",Z9,"-",AE9)', "Z": "TBA", "AE": "TBA", "AI": "TBA"}
    for col, v in proto.items():
        ws[f"{col}9"] = v
    ws.column_dimensions["U"].width = 22
    ws.print_area = "A1:AI40"
    b = io.BytesIO(); wb.save(b)
    return b.getvalue()


def iodb() -> bytes:
    rows = [("200-PT-101", "200-AJB-002", "PT"), ("200-TT-101", "200-AJB-001", "TT"), ("200-LT-101", "200-AJB-001", "LT"),
            ("200-FT-101", "200-AJB-002", "FT"), ("200-PSH-101", "200-AJB-001", "PSH"), ("200-AT-301", "200-AJB-003", "AT"),
            ("200-SPARE", "-", "X")]
    df = pd.DataFrame([{"TAG NO": t, "JUNCTION BOX TAG NO.": jb, "LOOP NUMBER": f"L-{i}", "EQUIPMENT DESCRIPTION": d,
                        "SIGNAL I/O TYPE": "AI", "MAIN CABLE TAG NUMBER": "IC-" + jb, "MAIN CABLE TYPE": "12PX1.5 Sqmm",
                        "MAIN CABLE LENGTH(Mtrs)": 100 + i} for i, (t, jb, d) in enumerate(rows)])
    b = io.BytesIO(); df.to_excel(b, sheet_name="IODB", index=False)
    return b.getvalue()


def generate(jbs=None):
    rep: dict = {}
    out, _, err = process_cable_schedule(io.BytesIO(iodb()), io.BytesIO(template()), "JUNCTION BOX TAG NO.", "TAG NO",
                                         extra_report=rep, selected_jbs=jbs)
    assert err is None, err
    wb = openpyxl.load_workbook(io.BytesIO(out))
    return wb["Cable Schedule -INST"], rep["layout"]


def cols(ws):
    out = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(7, c).value
        if v:
            out[str(v)] = c
    return out


def entries(ws, tag_col=2):
    return [r for r in range(9, ws.max_row + 1) if ws.cell(r, tag_col).value]


def test_red_columns_removed_main_cable_length_kept():
    ws, lay = generate()
    heads = list(cols(ws))
    assert not RED & set(heads)
    assert "FERRULE AT INSTRUMENT SIDE (-)" not in heads and "FERRULE AT INSTRUMENT SIDE\n(+) / (-)" in heads
    # FERRULE AT PLC (+) / (-) are removed too (Cable_Schedule-13): Remarks follows PANEL END GLAND SIZE
    assert "FERRULE AT PLC (+)" not in heads and "FERRULE AT PLC (-)" not in heads
    assert heads[-1] == "Remarks" and heads[-2] == "PANEL END GLAND SIZE" and len(heads) == len(HEAD) - len(RED) - 1 - 2
    c = cols(ws)
    assert "MAIN CABLE LENGTH(Mtrs)" in c
    assert ws.column_dimensions[openpyxl.utils.get_column_letter(c["MAIN CABLE LENGTH(Mtrs)"])].width == 22
    # the IODB length is written (the template's '=98+210' is sample data); these rows give different lengths for the
    # same main cable tag - a conflict - so every row keeps its own value and a warning is raised
    lengths = [ws.cell(r, c["MAIN CABLE LENGTH(Mtrs)"]).value for r in entries(ws)]
    assert all(isinstance(v, int) for v in lengths) and "=98+210" not in lengths
    assert not any(isinstance(ws.cell(r, k).value, str) and "FERRULE AT PLC" in str(ws.cell(r, k).value) for r in (7, 8) for k in range(1, 30))
    # the title block is re-laid inside the new width
    assert ws["A3"].value == "PROJECT" and any(ws.cell(4, k).value == "WABAG DOC NO." for k in range(1, len(heads) + 1))


def test_tags_grouped_by_jb_consecutive_in_iodb_order_and_tb_numbers():
    ws, lay = generate()
    c = cols(ws)
    rows = entries(ws)
    assert rows == [9 + 3 * i for i in range(len(rows))]                             # contiguous: no blank gap rows
    got = [(ws.cell(r, 2).value, ws.cell(r, c["JB TAG No."]).value) for r in rows]
    assert got == [("200-TT-101", "200-AJB-001"), ("200-LT-101", "200-AJB-001"), ("200-PSH-101", "200-AJB-001"),
                   ("200-PT-101", "200-AJB-002"), ("200-FT-101", "200-AJB-002"), ("200-AT-301", "200-AJB-003")]
    tb = c["TB DETAILS AT JB"]
    stacks = [[ws.cell(r + i, tb).value for i in range(3)] for r in rows]
    assert stacks == [[1, 2, 3], [4, 5, 6], [7, 8, 9], [1, 2, 3], [4, 5, 6], [1, 2, 3]]   # 3 cells, restart per JB
    assert lay["tb_numbers"] == {"200-AJB-001": 9, "200-AJB-002": 6, "200-AJB-003": 3}


def test_ferrule_combined_plus_above_minus_and_entries_merged():
    ws, _ = generate()
    c = cols(ws)
    f = c["FERRULE AT INSTRUMENT SIDE\n(+) / (-)"]
    tb_letter = openpyxl.utils.get_column_letter(c["TB DETAILS AT JB"])
    jb_letter = openpyxl.utils.get_column_letter(c["JB TAG No."])
    assert ws.cell(9, f).value == f'=CONCATENATE({tb_letter}9,"-",{jb_letter}9,"/",B9,"(+)")'
    assert ws.cell(10, f).value == f'=CONCATENATE({tb_letter}9+1,"-",{jb_letter}9,"/",B9,"(-)")'
    assert ws.cell(11, f).value is None
    merged = {str(m) for m in ws.merged_cells.ranges}
    assert "B9:B11" in merged and f"{jb_letter}9:{jb_letter}11" in merged              # one entry = one 3-row block
    assert not any(m.startswith(openpyxl.utils.get_column_letter(f) + "9:") for m in merged)
    assert not any(m.startswith(tb_letter + "9:") for m in merged)
    mc = openpyxl.utils.get_column_letter(c["MAIN CABLE TAG NUMBER"])
    assert f"{mc}9:{mc}11" not in merged                                             # shared main cable stays one cable


def test_selected_jb_gives_all_its_tags_and_only_them():
    ws, _ = generate(["200-AJB-002"])
    assert [ws.cell(r, 2).value for r in entries(ws)] == ["200-PT-101", "200-FT-101"]
    rep: dict = {}
    _, _, err = process_cable_schedule(io.BytesIO(iodb()), io.BytesIO(template()), "JUNCTION BOX TAG NO.", "TAG NO",
                                       selected_jbs=["NOPE"])
    assert "not found" in err


def test_jb_groups_and_preview_api():
    df = pd.read_excel(io.BytesIO(iodb()))
    g = jb_groups(df, "JUNCTION BOX TAG NO.", "TAG NO")
    assert [x["junction_box"] for x in g] == ["200-AJB-001", "200-AJB-002", "200-AJB-003"]
    assert g[0]["tags"] == ["200-TT-101", "200-LT-101", "200-PSH-101"]
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers.cable_schedule import router
    app = FastAPI(); app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, username="u")
    cli = TestClient(app)
    r = cli.post("/api/cable-schedule/preview", files={"file": ("i.xlsx", iodb())},
                 data={"jb_column": "JUNCTION BOX TAG NO.", "tag_column": "TAG NO"})
    assert r.status_code == 200 and r.json()["rows"][1]["tags"] == ["200-PT-101", "200-FT-101"]


def test_formula_term_removal():
    m = {c: c for c in range(1, 60)}
    assert rewrite_formula('=CONCATENATE(B9,"/",O9,"-",P9,"/",Z9,"-",AE9)', m, {26, 31}) == '=CONCATENATE(B9,"/",O9,"-",P9)'
    assert rewrite_formula("=D11&AJ11&N11&AI11&J11", m, {14}) == "=D11&AI11&J11"
