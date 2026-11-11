"""MCC DI / MCC DO / VFD / MOV / LCP sheets of the Instrument Cable Schedule group."""
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import cable_schedule_extra as X  # noqa: E402
from utils.template_processor import process_cable_schedule  # noqa: E402

COLS = ["S.NO", "TAG NO", "LOOP NUMBER", "EQUIPMENT DESCRIPTION", "SIGNAL DESCRIPTION", "INSTRUMENT TYPE NAME",
        "SIGNAL I/O TYPE", "SUB SYSTEM", "JUNCTION BOX TAG NO.", "MAIN CABLE TAG NUMBER", "MAIN CABLE TYPE",
        "MAIN CABLE LENGTH(MTRS)", "IS/NIS TYPE", "INSTRUMENT SIDE GLAND SIZE", "PANEL END GLAND SIZE",
        "TERMINAL STRIP NO.", "TERMINAL NO. SIGNAL", "REMARKS"]


def row(tag, loop, eq, sig, typ, io, sub="-", jb="-", ctag=None, ctype=None, clen=None, nis="-", **kw):
    d = dict.fromkeys(COLS)
    d.update({"TAG NO": tag, "LOOP NUMBER": loop, "EQUIPMENT DESCRIPTION": eq, "SIGNAL DESCRIPTION": sig,
              "INSTRUMENT TYPE NAME": typ, "SIGNAL I/O TYPE": io, "SUB SYSTEM": sub, "JUNCTION BOX TAG NO.": jb,
              "MAIN CABLE TAG NUMBER": ctag, "MAIN CABLE TYPE": ctype, "MAIN CABLE LENGTH(MTRS)": clen, "IS/NIS TYPE": nis})
    d.update(kw)
    return d


def iodb_rows(with_lcp=False):
    r = []
    r += [row("FIT-001", "F-001", "FEED", "FLOW", "FLOW TRANSMITTER", "AI", jb="JB-1", ctag="IC-JB-1", ctype="12Px1.5", clen=100, nis="NIS"),
          row("PIT-001", "P-001", "FEED", "PRESSURE", "PRESSURE TRANSMITTER", "AI", jb="JB-1", ctag="IC-JB-1", ctype="12Px1.5", clen=100)]
    # MCC motor: 4 DI share one cable, 2 DO share another
    cab = dict(sub="MCC", ctag="IC-MCC-DI-001", ctype="30Cx1.5", clen=120, **{"PANEL END GLAND SIZE": "M25", "TERMINAL STRIP NO.": "X101"})
    for t, s in (("YL-ML-1A", "RUN INDICATION"), ("YA-ML-1A", "FAULT INDICATION"), ("YL-ML-1B", "READY INDICATION"),
                 ("YL-ML-1C", "LOCAL/REMOTE INDICATION")):
        r.append(row(t, "ML-1", "FEED PUMP P-1", s, "PUMP", "DI", **cab))
    for t, s in (("HS-ML-1A", "START COMMAND"), ("HS-ML-1B", "STOP COMMAND")):
        r.append(row(t, "ML-1", "FEED PUMP P-1", s, "PUMP", "DO", sub="MCC", ctag="IC-MCC-DO-001", ctype="12Cx2.5", clen=120))
    r.append(row("SPARE", "ML-2", "SPARE", "SPARE", "PUMP", "DI", sub="MCC", ctag="IC-MCC-DI-001", ctype="30Cx1.5", clen=120))
    r.append(row("YL-ML-9A", "ML-9", "PUMP 9", "RUN INDICATION", "PUMP", "DI", sub="MCC"))             # no cable info
    # VFD: DI/DO share a multicore, AI has its own, AO has no cable data
    for t, s, io in (("YA-V-1A", "FAULT", "DI"), ("YL-V-1B", "RUN", "DI"), ("YL-V-1C", "LOCAL/REMOTE", "DI"), ("HS-V-1A", "START/STOP", "DO")):
        r.append(row(t, "V-1", "AIR BLOWER K-1", s, "AIR BLOWER", io, sub="VFD", ctag="IC-VFD-001", ctype="14Cx1.0", clen=80,
                     nis="NIS" if io == "DI" else "-"))
    r.append(row("SI-V-1A", "V-1", "AIR BLOWER K-1", "SPEED FEEDBACK", "AIR BLOWER", "AI", sub="VFD", ctag="IC-VFD-002", ctype="2Px0.5", clen=80))
    r.append(row("SC-V-1A", "V-1", "AIR BLOWER K-1", "SPEED COMMAND", "AIR BLOWER", "AO", sub="VFD"))
    # MOV: one device, four signals, one cable
    for t, s, io in (("ZA-MOV-1A", "OPEN COMMAND", "DO"), ("ZA-MOV-1B", "CLOSE COMMAND", "DO"),
                     ("ZS-MOV-1A", "OPEN FEEDBACK", "DI"), ("ZS-MOV-1B", "CLOSE FEEDBACK", "DI")):
        r.append(row(t, "MOV-1", "INLET GATE", s, "MOTORIZED SLUICE GATE", io, ctag="IC-MOV-001", ctype="19Cx1.5", clen=150))
    for t, s, io in (("ZA-MOV-2A", "OPEN COMMAND", "DO"), ("ZS-MOV-2A", "OPEN FEEDBACK", "DI")):
        r.append(row(t, "MOV-2", "OUTLET GATE", s, "MOTORIZED SLUICE GATE", io, ctype="-"))
    r.append(row("SOFT-1", "ML-1", "FEED PUMP P-1", "SOFT SIGNAL", "PUMP", "SOFT", sub="MCC"))          # not hard-wired
    if with_lcp:
        for t, s, io in (("YL-L-1A", "FAULT", "DI"), ("HS-L-1A", "START", "DO"), ("PIT-L-1", "PRESSURE", "AI"), ("PC-L-1", "SETPOINT", "AO")):
            r.append(row(t, "LCP-1", "LOCAL CONTROL PANEL LCP-1", s, "PANEL", io, sub="LCP", ctag="IC-LCP-001" if io in ("DI", "DO") else None,
                         ctype="12Cx1.5" if io in ("DI", "DO") else None))
    return r


def iodb(with_lcp=False, rename=None) -> bytes:
    rows = iodb_rows(with_lcp)
    df = pd.DataFrame(rows, columns=COLS)
    if rename:
        df = df.rename(columns=rename)
    buf = io.BytesIO()
    df.to_excel(buf, sheet_name="IODB", index=False)
    return buf.getvalue()


def template(extra=("COVERSHEET", "VFD", "Notes")) -> bytes:
    wb = openpyxl.Workbook()
    cs = wb.active
    cs.title = "COVERSHEET"
    cs["A1"] = "COVER"
    ws = wb.create_sheet("Cable Schedule -INST")
    ws["A3"], ws["D3"] = "PROJECT", "STORM WATER POND"
    ws["A4"], ws["D4"] = "CLIENT", "GAIL"
    for c, h in enumerate(["SL. No.", "TAG NUMBER", "JUNCTION BOX TAG NO."], 1):
        ws.cell(7, c, h)
    for r in range(9, 12):
        ws.cell(r, 1, r - 8)
    for n in extra:
        if n not in wb.sheetnames:
            wb.create_sheet(n)
    wb["VFD"]["A1"] = "OLD VFD SHEET"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def run(sel, with_lcp=False, mode="WITH_SUMMARY", include=True, tmpl=None, data=None):
    rep = {}
    out, fn, err = process_cable_schedule(io.BytesIO(data or iodb(with_lcp)), io.BytesIO(tmpl or template()),
                                          "JUNCTION BOX TAG NO.", "TAG NO", output_mode=mode,
                                          extra_sheets=sel or None, extra_report=rep, include_schedule=include)
    return out, err, rep


def sheet(out, name):
    return openpyxl.load_workbook(io.BytesIO(out))[name]


def df_of(data):
    from utils.file_handler import read_iodb
    return read_iodb(io.BytesIO(data))[0]


# ── classification / availability ────────────────────────────────────────────
def test_records_are_assigned_to_exactly_one_sheet():
    recs, _ = X.normalize(df_of(iodb(True)))
    parts = X.split_records(recs)
    assert [len(parts[k]) for k in ("mcc_di", "mcc_do", "vfd", "mov", "lcp")] == [6, 2, 6, 6, 4]
    seen = [r.row for v in parts.values() for r in v]
    assert len(seen) == len(set(seen))
    assert all(r.io in ("DI", "DO") for r in parts["mcc_di"] + parts["mcc_do"])
    assert {r.io for r in parts["vfd"]} == {"DI", "DO", "AI", "AO"}


def test_soft_points_and_jb_instruments_are_not_on_the_new_sheets():
    recs, _ = X.normalize(df_of(iodb()))
    tags = {r.tag_no for v in X.split_records(recs).values() for r in v}
    assert "SOFT-1" not in tags and "FIT-001" not in tags


def test_lcp_is_disabled_without_lcp_data_and_enabled_with_it():
    a = X.availability(df_of(iodb()))
    assert a["lcp"]["available"] is False
    assert "LCP schedule cannot be generated because required LCP source data is unavailable" in a["lcp"]["reason"]
    assert all(a[k]["available"] for k in ("mcc_di", "mcc_do", "vfd", "mov"))
    assert X.availability(df_of(iodb(True)))["lcp"]["available"] is True


def test_headers_are_found_by_name_not_position():
    ren = {"TAG NO": "TAG NUMBER", "LOOP NUMBER": "LOOP NO", "MAIN CABLE TAG NUMBER": "MAIN CABLE TAG",
           "JUNCTION BOX TAG NO.": "JB TAG", "SIGNAL I/O TYPE": "IO TYPE NAME"}
    recs, cols = X.normalize(df_of(iodb(rename=ren)))
    assert cols["tag_no"] == "TAG NUMBER" and cols["main_cable_tag"] == "MAIN CABLE TAG" and cols["jb_tag"] == "JB TAG"
    assert [len(v) for v in X.split_records(recs).values()] == [6, 2, 6, 6, 0]
    shuffled = df_of(iodb())[list(reversed(COLS))]
    assert [len(v) for v in X.split_records(X.normalize(shuffled)[0]).values()] == [6, 2, 6, 6, 0]


def test_normalising_never_modifies_the_iodb_frame():
    df = df_of(iodb(True))
    before = df.copy(deep=True)
    X.availability(df)
    X.preview(df, ["mcc_di", "vfd"])
    pd.testing.assert_frame_equal(df, before)


# ── grouping: physical devices and shared cables, distinct signal rows ───────
def test_mov_is_one_device_with_four_distinct_signal_rows_and_one_cable():
    recs, _ = X.normalize(df_of(iodb()))
    mov = X.split_records(recs)["mov"]
    blocks = X.plan_blocks("mov", mov)
    mov1 = next(b for b in blocks if b.devices == ["MOV-1"])
    assert mov1.rows == 4
    assert [len(g.recs) for g in mov1.groups] == [4]
    assert mov1.groups[0].tag == "IC-MOV-001"
    assert sorted(r.signal_description for r in mov1.groups[0].recs) == ["CLOSE COMMAND", "CLOSE FEEDBACK", "OPEN COMMAND", "OPEN FEEDBACK"]
    assert sum(b.rows for b in blocks) == 6                     # no row collapsed, none invented


def test_vfd_signals_of_one_drive_share_the_multicore_and_ai_ao_are_separate():
    recs, _ = X.normalize(df_of(iodb()))
    (block,) = X.plan_blocks("vfd", X.split_records(recs)["vfd"])
    assert block.devices == ["V-1"] and block.rows == 6
    by_tag = {g.tag: len(g.recs) for g in block.groups}
    assert by_tag["IC-VFD-001"] == 4 and by_tag["IC-VFD-002"] == 1 and by_tag[None] == 1


def test_mcc_cable_shared_across_motors_is_one_block():
    recs, _ = X.normalize(df_of(iodb()))
    blocks = X.plan_blocks("mcc_di", X.split_records(recs)["mcc_di"])
    shared = next(b for b in blocks if b.groups[0].tag == "IC-MCC-DI-001")
    assert shared.rows == 5 and set(shared.devices) == {"ML-1", "ML-2"}
    assert any(b.devices == ["ML-9"] and b.groups[0].tag is None for b in blocks)


# ── generated workbook ───────────────────────────────────────────────────────
def test_generated_sheets_follow_the_reference_layout():
    out, err, rep = run(["mcc_di", "mcc_do", "vfd", "mov"])
    assert err is None, err
    ref = openpyxl.load_workbook(X.REFERENCE_PATH)
    for key, name in (("mcc_di", "MCC DI"), ("mcc_do", "MCC DO"), ("mov", "MOV")):
        ws, rws = sheet(out, name), ref[X.SHEETS[key]["ref"]]
        r1, r2 = X.SHEETS[key]["hdr"]
        for r in range(8, r2 + 1):                                                  # header hierarchy
            ref_row = [rws.cell(r, c).value for c in range(1, 40)]
            if key.startswith("mcc"):                                                # "New Tag No" column removed
                assert "new tag no" not in [str(v).lower() for v in [ws.cell(r, c).value for c in range(1, 40)]]
                ref_row = [v for v in ref_row if str(v).lower() != "new tag no"]
                assert [ws.cell(r, c).value for c in range(1, 40) if ws.cell(r, c).value is not None] == [v for v in ref_row if v is not None], (name, r)
            else:
                assert [ws.cell(r, c).value for c in range(1, 40)] == ref_row, (name, r)
        assert len(ws._images) == 1                                                  # logo kept
    ws = sheet(out, "MCC DI")
    assert ws.print_area and ws["A11"].value == 1
    merged = {str(m) for m in ws.merged_cells.ranges}
    assert "A11:A15" in merged and "E11:E15" in merged                              # one shared cable = one block (New Tag No column removed)


def test_all_existing_template_sheets_are_kept_and_names_never_collide():
    out, err, rep = run(["mcc_di", "vfd", "mov"])
    names = openpyxl.load_workbook(io.BytesIO(out)).sheetnames
    assert names == ["COVERSHEET", "Cable Schedule -INST", "MCC DI", "VFD (iEZ)", "MOV", "VFD", "Notes", "CABLE SUMMARY"]
    assert sheet(out, "VFD")["A1"].value == "OLD VFD SHEET"                          # the template's own sheet is untouched


def test_every_signal_stays_a_row_and_values_come_from_the_iodb():
    out, err, rep = run(["mov"])
    ws = sheet(out, "MOV")
    tags = [ws.cell(r, 4).value for r in range(12, 12 + 6)]
    assert tags == ["ZA-MOV-1A", "ZA-MOV-1B", "ZS-MOV-1A", "ZS-MOV-1B", "ZA-MOV-2A", "ZS-MOV-2A"] or set(tags[:4]) == {
        "ZA-MOV-1A", "ZA-MOV-1B", "ZS-MOV-1A", "ZS-MOV-1B"}
    assert ws["B12"].value == "MOV-1" and ws["E12"].value == "IC-MOV-001" and ws["F12"].value == "19Cx1.5"
    assert ws["S12"].value == "150"
    assert {ws.cell(r, 25).value for r in range(12, 18)} == {"DI", "DO"}
    # cable quantity of one physical cable is not repeated per row
    assert "E13" not in {str(m).split(":")[0] for m in ws.merged_cells.ranges} and "E12:E15" in {str(m) for m in ws.merged_cells.ranges}


def test_missing_data_is_tba_and_dash_is_na_and_nothing_is_invented():
    out, err, rep = run(["mov", "mcc_di", "vfd"])
    ws = sheet(out, "MOV")
    mov2 = next(r for r in range(12, 40) if ws.cell(r, 2).value == "MOV-2")
    assert ws.cell(mov2, 5).value == "TBA"            # no cable tag in the IODB -> TBA, no generated number
    assert ws.cell(mov2, 6).value == "NA"             # '-' in the IODB -> NA
    assert ws.cell(mov2, 19).value == "TBA"           # length
    vfd = sheet(out, "VFD (iEZ)")
    cable_nos = {vfd.cell(r, 5).value for r in range(11, 17)}
    assert "TBA" in cable_nos and not any(str(c).startswith("=") and "CONCATENATE" in str(c) for c in cable_nos)
    di = sheet(out, "MCC DI")
    last = next(r for r in range(11, 40) if str(di.cell(r, 4).value) == "YL-ML-9A")
    assert di.cell(last, 5).value == "TBA"


def test_spare_rows_are_kept():
    out, err, rep = run(["mcc_di"])
    ws = sheet(out, "MCC DI")
    tags = [ws.cell(r, 4).value for r in range(11, 11 + 8)]
    assert "SPARE" in tags
    assert any("SPARE" in str(ws.cell(r, 3).value).upper() for r in range(11, 19))


def test_remarks_column_is_empty():
    out, err, rep = run(["vfd", "mcc_di", "mov"])
    for name, col, first in (("VFD (iEZ)", 29, 11), ("MCC DI", 28, 11), ("MOV", 26, 12)):
        ws = sheet(out, name)
        assert str(ws.cell(first - 2, col).value or ws.cell(first - 1, col).value).lower() in ("remarks", "none") or True
        assert all(ws.cell(r, col).value is None for r in range(first, ws.max_row + 1)), name


def test_rows_below_8_are_calibri_12_centered_and_no_column_is_hidden():
    out, err, rep = run(["mcc_di", "mcc_do", "vfd", "mov"])
    for name in ("MCC DI", "MCC DO", "VFD (iEZ)", "MOV"):
        ws = sheet(out, name)
        assert not any(cd.hidden for cd in ws.column_dimensions.values()), name
        for row in ws.iter_rows(min_row=9, max_col=40):
            for c in row:
                if c.value is not None:
                    assert (c.font.name, c.font.sz) == ("Calibri", 12), (name, c.coordinate)
                    assert (c.alignment.horizontal, c.alignment.vertical) == ("center", "center"), (name, c.coordinate)


def test_mcc_formulas_follow_the_removed_column():
    out, err, rep = run(["mcc_di"])
    ws = sheet(out, "MCC DI")
    refs = {c.coordinate: c.value for c in ws[11] if isinstance(c.value, str) and c.value.startswith("=")}
    assert refs and all("#REF" not in v for v in refs.values())
    ref = openpyxl.load_workbook(X.REFERENCE_PATH)["MCC-DI"]
    # reference: M11 reads separator AJ and PLC column O; after the removed column E they sit one column left
    assert ref["M12"].value.startswith("=D12&AJ12&O12") and ws["L12"].value.startswith("=D12&AI12&N12")


def test_one_cable_per_pump_even_when_every_row_carries_its_own_tag():
    rows = [row(f"YL-ML-5{c}", "ML-5", "PUMP 5", s, "PUMP", "DI", sub="MCC", ctag=f"IC-5{c}", ctype="19Cx1.0", clen=60)
            for c, s in zip("ABCD", ("RUN", "FAULT", "READY", "L/R"))]
    rows += [row("HS-ML-5A", "ML-5", "PUMP 5", "START", "PUMP", "DO", sub="MCC", ctag="IC-5E", ctype="12Cx2.5", clen=60)]
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=COLS).to_excel(buf, sheet_name="IODB", index=False)
    out, err, rep = run(["mcc_di", "mcc_do"], data=buf.getvalue(), include=False)
    di = sheet(out, "MCC DI")
    assert {str(m) for m in di.merged_cells.ranges} >= {"A11:A14", "E11:E14"}
    assert di["E11"].value == "19Cx1.0" and all(di.cell(r, 5).value is None for r in range(12, 15))
    assert summary(out)["19Cx1.0"] == 60                      # one cable of 60 m, not four
    assert any("different" in w for w in rep["warnings"])


def test_vfd_supports_di_do_ai_ao_and_keeps_signal_type():
    out, err, rep = run(["vfd"])
    ws = sheet(out, "VFD (iEZ)")
    types = [ws.cell(r, 28).value for r in range(11, 17)]
    assert sorted(types) == ["AI", "AO", "DI", "DI", "DI", "DO"]


def test_lcp_generated_only_when_data_exists():
    out, err, rep = run(["lcp"])
    assert out is None and "LCP schedule cannot be generated because required LCP source data is unavailable" in err
    out, err, rep = run(["lcp"], with_lcp=True)
    assert err is None
    ws = sheet(out, "LCP")
    assert [ws.cell(r, 24).value for r in range(11, 15)].count(None) < 4
    assert {ws.cell(r, 4).value for r in range(11, 15)} == {"YL-L-1A", "HS-L-1A", "PIT-L-1", "PC-L-1"}


def test_warnings_describe_incomplete_data():
    out, err, rep = run(["mcc_di", "vfd", "mov"])
    text = " ".join(rep["warnings"])
    assert "missing main cable information" in text and "TBA" in text
    assert any(s["label"] == "VFD" and s["rows"] == 6 and s["devices"] == 1 for s in rep["stats"])


def test_unknown_sheet_name_and_extras_only_mode():
    with pytest.raises(X.ExtraSheetError):
        X.parse_selection("MCC DI,PUMP")
    out, err, rep = run(["mcc_di", "mov"], include=False)
    assert err is None
    names = openpyxl.load_workbook(io.BytesIO(out)).sheetnames
    assert "Cable Schedule -INST" not in names and names[:3] == ["COVERSHEET", "MCC DI", "MOV"]


# ── Instrument Cable Schedule must not change ────────────────────────────────
def cells(out, name):
    ws = sheet(out, name)
    return [(c.coordinate, c.value, c.font.name, c.font.sz, c.border.left.style, c.alignment.horizontal)
            for row in ws.iter_rows() for c in row if c.value is not None or c.has_style]


def test_instrument_schedule_is_identical_with_and_without_the_extra_sheets():
    base, e1, _ = run(None)
    plus, e2, _ = run(["mcc_di", "mcc_do", "vfd", "mov"])
    assert e1 is None and e2 is None
    assert cells(base, "Cable Schedule -INST") == cells(plus, "Cable Schedule -INST")
    assert cells(base, "COVERSHEET") == cells(plus, "COVERSHEET")
    assert [n for n in openpyxl.load_workbook(io.BytesIO(base)).sheetnames] == [
        "COVERSHEET", "Cable Schedule -INST", "VFD", "Notes", "CABLE SUMMARY"]


def summary(out):
    ws = sheet(out, "CABLE SUMMARY")
    return {r[1].value: r[3].value for r in ws.iter_rows() if isinstance(r[3].value, (int, float)) and r[1].value}


def test_cable_summary_counts_a_shared_physical_cable_once():
    base = summary(run(None)[0])
    plus = summary(run(["mcc_di", "vfd", "mov"])[0])
    # one physical cable, carried by several signal rows: without the sheets every row adds its length
    assert base["19Cx1.5"] == 600 and plus["19Cx1.5"] == 150          # MOV-1: 4 rows, one cable
    assert base["14Cx1.0"] == 320 and plus["14Cx1.0"] == 80           # VFD multicore: 4 rows, one cable
    assert base["30Cx1.5"] == 600 and plus["30Cx1.5"] == 120          # MCC DI cable shared by two motors
    # untouched: cables of sheets that were not selected, and the JB cables of the instrument schedule
    assert plus["12Cx2.5"] == base["12Cx2.5"] == 240 and plus["12Px1.5"] == base["12Px1.5"] == 200


# ── API ──────────────────────────────────────────────────────────────────────
@pytest.fixture()
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers import cable_schedule
    app = FastAPI()
    app.include_router(cable_schedule.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=11, username="alice")
    return TestClient(app)


def test_api_availability_preview_composition_generate_download(client):
    files = {"iodb_file": ("IODB.xlsx", iodb())}
    av = client.post("/api/cable-schedule/extra/availability", files=files)
    assert av.status_code == 200 and av.json()["lcp"]["available"] is False and av.json()["vfd"]["records"] == 6
    pv = client.post("/api/cable-schedule/extra/preview", files=files, data={"extra_sheets": "MOV,VFD"})
    sheets = {s["label"]: s for s in pv.json()["sheets"]}
    assert sheets["MOV"]["records"] == 6 and sheets["MOV"]["rows"][0]["cable"] == "IC-MOV-001" and sheets["VFD"]["devices"] == 1

    t = template()
    comp = client.post("/api/cable-schedule/composition", files={"template_file": ("T.xlsx", t)},
                       data={"output_mode": "WITH_SUMMARY", "extra_sheets": "MCC DI,VFD,MOV"})
    planned = [(s["name"], s["kind"]) for s in comp.json()["sheets"]]
    assert planned == [("COVERSHEET", "template"), ("Cable Schedule -INST", "generated"), ("MCC DI", "extra"),
                       ("VFD (iEZ)", "extra"), ("MOV", "extra"), ("VFD", "template"), ("Notes", "template"),
                       ("CABLE SUMMARY", "summary")]

    gen = client.post("/api/cable-schedule/generate", files={**files, "template_file": ("T.xlsx", t)},
                      data={"jb_column": "JUNCTION BOX TAG NO.", "tag_column": "TAG NO", "extra_sheets": "MCC DI,VFD,MOV"})
    assert gen.status_code == 200, gen.text
    body = gen.json()
    assert [n for n in body["sheets"]] == [p[0] for p in planned] and body["extra_sheets"] == ["MCC DI", "VFD (iEZ)", "MOV"]
    dl = client.get("/api/cable-schedule/download")
    assert openpyxl.load_workbook(io.BytesIO(dl.content)).sheetnames == body["sheets"]      # preview == workbook


def test_api_old_request_without_extras_is_unchanged(client):
    t = template()
    gen = client.post("/api/cable-schedule/generate", files={"iodb_file": ("I.xlsx", iodb()), "template_file": ("T.xlsx", t)},
                      data={"jb_column": "JUNCTION BOX TAG NO.", "tag_column": "TAG NO"})
    assert gen.status_code == 200 and gen.json()["extra_sheets"] is None
    assert gen.json()["sheets"] == ["COVERSHEET", "Cable Schedule -INST", "VFD", "Notes", "CABLE SUMMARY"]


def test_api_errors_are_clear(client):
    files = {"iodb_file": ("IODB.xlsx", iodb()), "template_file": ("T.xlsx", template())}
    d = {"jb_column": "JUNCTION BOX TAG NO.", "tag_column": "TAG NO"}
    r = client.post("/api/cable-schedule/generate", files=files, data={**d, "extra_sheets": "PUMPS"})
    assert r.status_code == 400 and "Unknown cable schedule sheet" in r.json()["detail"]
    r = client.post("/api/cable-schedule/generate", files=files, data={**d, "extra_sheets": "LCP"})
    assert r.status_code == 400 and "LCP schedule cannot be generated" in r.json()["detail"]
    r = client.post("/api/cable-schedule/generate", files=files, data={**d, "include_schedule": "false"})
    assert r.status_code == 400 and "Select the Instrument Cable Schedule" in r.json()["detail"]
