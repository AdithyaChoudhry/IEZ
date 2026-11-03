"""Loop Wiring fed from the standard I/O Assignment: column layout, loop-type rule, filled sheets."""
import io
import sys
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import loop_from_assignment as L  # noqa: E402

TEMPLATES = {"with": ROOT / "backend" / "app" / "templates" / "loop_wiring" / "WITH_MARSHALLING_CABINET.xlsx",
             "without": ROOT / "backend" / "app" / "templates" / "loop_wiring" / "WITHOUT_MARSHALLING_CABINET.xlsx"}
TEMPLATE = TEMPLATES["with"]
needs_template = pytest.mark.skipif(not all(p.exists() for p in TEMPLATES.values()), reason="loop template workbooks missing")

HEAD = ["S.NO", "TAG NO", "LOOP NO", "I/O TYPE", "INTERFACE", "SIGNAL TYPE", "WIRE TYPE", "JUNCTION BOX NO", "CABLE NO", "CORE / PAIR",
        "MARSHALLING CABINET", "PANEL NO", "RACK NO", "SLOT NO", "MODULE TYPE", "MODULE NO", "CHANNEL NO", "TERMINAL STRIP NO",
        "TERMINAL NO (CMN)", "TERMINAL NO (SIGNAL)", "CHANGE STATUS"]


def assignment(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IO_ASSIGNMENT"
    for _ in range(6):
        ws.append([])
    ws.append(HEAD)
    for r in rows:
        ws.append([r.get(h) for h in HEAD])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def row(tag, io_type="AI", wire="2 WIRE", **kw):
    d = dict(zip(HEAD, [None] * len(HEAD)))
    d.update({"TAG NO": tag, "LOOP NO": "L-" + tag[-3:], "I/O TYPE": io_type, "INTERFACE": "HARDWIRED", "SIGNAL TYPE": "4-20mA", "WIRE TYPE": wire,
              "JUNCTION BOX NO": "JB-1", "PANEL NO": "P1", "RACK NO": 1, "SLOT NO": 2, "MODULE TYPE": "AI 08", "MODULE NO": "M1", "CHANNEL NO": 3,
              "TERMINAL STRIP NO": "X301", "TERMINAL NO (CMN)": 5, "TERMINAL NO (SIGNAL)": 6})
    d.update(kw)
    return d


def test_loop_type_rule():
    assert L.classify("AI", "2 WIRE")[0] == L.LOOP_2W
    assert L.classify("ai", " 4 wire ")[0] == L.LOOP_4W
    for io, wire in (("AI", None), ("AI", "3 WIRE"), ("DI", "2 WIRE"), ("AO", "4 WIRE"), ("DO", "2 WIRE")):
        t, why = L.classify(io, wire)
        assert t is None and why


@needs_template
def test_columns_follow_the_template_and_values_come_from_the_assignment():
    tmpl = TEMPLATE.read_bytes()
    heads = L.template_headers(tmpl)
    assert heads[0] == "Tag_Number" and heads[-1] == "Channel" and len(heads) == 22
    rows, sheet = L.read_assignment(assignment([row("PT-001"), row("FT-002", wire="4 WIRE", **{"CABLE NO": "C-9", "CORE / PAIR": "P3"})]))
    feed = L.build_loop_input(rows, heads)
    a, b = feed.rows
    assert (a["Tag_Number"], a["LOOP TYPE"], a["Term1"], a["Term2"], a["Channel"], a["Slot"], a["Crate"]) == ("PT-001", L.LOOP_2W, 5, 6, 3, 2, 1)
    assert a["JB Cable"] == "PT-001/JB-1" and a["Sys_Cabinet"] == "P1" and a["Module_Tag"] == "M1" and a["Term_Block1"] == "X301"
    assert (b["LOOP TYPE"], b["Cable no."], b["Pair_Num"]) == (L.LOOP_4W, "C-9", "P3")
    assert feed.unfed_headers == ["FTA_model", "FTA_Tag", "FTA_In1", "FTA_Out1", "Sys_Cable"]


@needs_template
def test_spare_deleted_soft_and_other_types_are_not_fed_and_are_explained():
    tmpl = TEMPLATE.read_bytes()
    rows, _ = L.read_assignment(assignment([
        row("PT-001"), row("SPARE"), row("PT-003", **{"CHANGE STATUS": "DELETED"}), row("SOFT-1", INTERFACE="SOFT"),
        row("ZS-1", io_type="DI"), row("PT-005", wire=None)]))
    feed = L.build_loop_input(rows, L.template_headers(tmpl))
    assert [r["Tag_Number"] for r in feed.rows] == ["PT-001"]
    reasons = {t: why for _, t, why in feed.skipped}
    assert set(reasons) == {"SOFT-1", "ZS-1", "PT-005"} and "no loop template" in reasons["ZS-1"] and "WIRE TYPE" in reasons["PT-005"]


@needs_template
def test_generated_workbook_has_one_sheet_per_tag_of_the_right_type_with_row_19_filled():
    tmpl = TEMPLATE.read_bytes()
    rows, _ = L.read_assignment(assignment([row("PT-001"), row("FT-002", wire="4 WIRE")]))
    feed = L.build_loop_input(rows, L.template_headers(tmpl))
    out = L.generate(feed, tmpl)
    wb = openpyxl.load_workbook(io.BytesIO(out))
    assert wb.sheetnames == ["Loop_L-001", "Loop_L-002"]                    # template type sheets are not left behind
    ws2, ws4 = wb["Loop_L-001"], wb["Loop_L-002"]
    assert ws2["W19"].value == "PT-001" and ws2["AF19"].value == 5 and ws2["AG19"].value == 6 and ws2["AR19"].value == 3
    assert ws2["AH19"].value == "TBA"                                          # FTA data has no source column
    assert ws4["W19"].value == "FT-002"
    assert ws2["A2"].value.startswith('="LOOP NAME') and ws2["B16"].value == "=W19"        # template formulas preserved
    # the 4-wire sheet has the extra power block, the 2-wire one does not
    assert ws4["H24"].value == "PDB" or any(c.value == "PDB" for r in ws4.iter_rows() for c in r)
    assert not any(c.value == "PDB" for r in ws2.iter_rows() for c in r)
    import re
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(out))
    drawings = [n for n in z.namelist() if n.startswith("xl/drawings/") and n.endswith(".xml")]
    assert len(drawings) == 2 and len(re.findall(rb"<xdr:sp>", z.read(drawings[0]))) > 0   # wires restored on every sheet


@needs_template
def test_sheet_titles_stay_unique_and_valid():
    tmpl = TEMPLATE.read_bytes()
    long = "X" * 40
    rows, _ = L.read_assignment(assignment([row(long + "-1"), row(long + "-2")]))
    out = L.generate(L.build_loop_input(rows, L.template_headers(tmpl)), tmpl)
    names = openpyxl.load_workbook(io.BytesIO(out)).sheetnames
    assert len(names) == 2 and len(set(n.lower() for n in names)) == 2 and all(len(n) <= 31 for n in names)


CYR = __import__("re").compile("[\u0400-\u04FF]")


@needs_template
@pytest.mark.parametrize("variant", ["with", "without"])
def test_templates_are_english_only_have_all_loop_types_and_identical_data_headers(variant):
    wb = openpyxl.load_workbook(TEMPLATES[variant])
    assert wb.sheetnames == ["2-WIRE INSTRUMENT", "4-WIRE INSTRUMENT", "SWITCH - LEVEL", "SWITCH - FLOW", "SWITCH - PRESSURE",
                             "SWITCH - TEMPERATURE", "MOTOR - STANDARD", "MOTOR - VFD"]
    ref = [wb.worksheets[0].cell(18, c).value for c in range(23, 45)]
    for ws in wb.worksheets:
        assert [ws.cell(18, c).value for c in range(23, 45)] == ref                      # same data columns on every sheet
        assert not any(isinstance(c.value, str) and CYR.search(c.value) for r in ws.iter_rows() for c in r), ws.title
        widths = {k: v.width for k, v in ws.column_dimensions.items()}
        assert all(widths.get(c) for c in ("I", "J", "Q", "R", "AA", "AB"))                # grouped columns keep their width
    ws = wb["2-WIRE INSTRUMENT"]
    assert (ws["O5"].value, ws["T5"].value) == (("MARSHALLING CABINET", "SYSTEM CABINET") if variant == "with" else (None, "SYSTEM CABINET"))


@needs_template
@pytest.mark.parametrize("variant", ["with", "without"])
def test_every_wire_in_every_sheet_touches_a_box_a_wire_or_a_cable_end(variant):
    """Geometric check on the drawing XML itself: no wire may end in empty space."""
    import re
    import zipfile
    from utils.workbook_assembly import _sheet_drawings
    z = zipfile.ZipFile(TEMPLATES[variant])
    for sheet, part in _sheet_drawings(z).items():
        x = z.read(part).decode()
        shapes = re.findall(r'<xdr:from><xdr:col>(\d+)</xdr:col><xdr:colOff>(\d+)</xdr:colOff><xdr:row>(\d+)</xdr:row><xdr:rowOff>(\d+)</xdr:rowOff></xdr:from>'
                            r'<xdr:to><xdr:col>(\d+)</xdr:col><xdr:colOff>(\d+)</xdr:colOff><xdr:row>(\d+)</xdr:row><xdr:rowOff>(\d+)</xdr:rowOff></xdr:to>'
                            r'<xdr:sp>.*?prst="(line|ellipse)"', x, re.S)
        assert shapes, sheet
        assert not any(s[8] == "line" and (s[:4] == s[4:8]) for s in shapes), f"{sheet}: zero-length wire"


def test_loop_name_falls_back_to_a_name_derived_from_the_tag():
    assert L.derive_loop_name("100-PIT-10101") == "100-P-10101"
    assert L.derive_loop_name("6816-LT-3003") == "6816-L-3003"          # same style as the reference Loop_Name
    assert L.derive_loop_name("100-YL-ML-10601A") == "ML-10601" == L.derive_loop_name("100-HS-ML-10601B")
    assert L.derive_loop_name("WEIRD") == "WEIRD"


@needs_template
@pytest.mark.parametrize("variant", ["with", "without"])
def test_every_generated_sheet_carries_its_loop_name_at_the_top(variant):
    tmpl = TEMPLATES[variant].read_bytes()
    rows, _ = L.read_assignment(assignment([row("PT-001", **{"LOOP NO": "L-ONE"}), row("100-PIT-10102", **{"LOOP NO": None})]))
    out = L.generate(L.build_loop_input(rows, L.template_headers(tmpl)), tmpl)
    wb = openpyxl.load_workbook(io.BytesIO(out))
    assert wb.worksheets[0]["X19"].value == "L-ONE" and wb.worksheets[1]["X19"].value == "100-P-10102"
    assert wb.worksheets[0]["A2"].value == '="LOOP NAME: "&X19'              # template formula shows row 19's loop name at the top


@needs_template
def test_without_marshalling_template_has_no_marshalling_or_fta_content():
    wb = openpyxl.load_workbook(TEMPLATES["without"])
    for ws in wb.worksheets:
        text = " ".join(str(c.value) for r in ws.iter_rows(max_col=22) for c in r if c.value is not None)
        assert "MARSHALLING" not in text.upper(), ws.title
        for addr in ("N16", "N17", "P15", "P16", "P17", "Q16", "O6"):
            assert ws[addr].value is None, (ws.title, addr)


def mrow(tag, desc, io_type, **kw):
    return row(tag, io_type=io_type, wire="2 WIRE", **{"SIGNAL DESCRIPTION": desc, "CHANNEL NO": kw.pop("ch", 1), **kw})


HEAD2 = HEAD + ["SIGNAL DESCRIPTION", "SUB SYSTEM"]


def assignment2(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IO_ASSIGNMENT"
    for _ in range(6):
        ws.append([])
    ws.append(HEAD2)
    for r in rows:
        ws.append([r.get(h) for h in HEAD2])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


MOTOR_SIGNALS = [("YL-ML-11011A", "LOCAL/REMOTE FEEDBACK", "DI"), ("YL-ML-11011B", "RUN FEEDBACK", "DI"), ("YL-ML-11011C", "READY FOR START", "DI"),
                 ("YA-ML-11011", "TRIP FEEDBACK", "DI"), ("HS-ML-11011A", "START COMMAND", "DO"), ("HS-ML-11011B", "STOP COMMAND", "DO"),
                 ("CI-ML-11011", "CURRENT INDICATION", "AI")]


@needs_template
@pytest.mark.parametrize("variant", ["with", "without"])
def test_all_signals_of_one_motor_loop_go_on_one_sheet_named_after_the_loop(variant):
    tmpl = TEMPLATES[variant].read_bytes()
    sigs = [mrow(f"100-{t}", d, io, ch=i + 1, **{"LOOP NO": None}) for i, (t, d, io) in enumerate(MOTOR_SIGNALS)]
    rows, _ = L.read_assignment(assignment2(sigs))
    feed = L.build_loop_input(rows, L.template_headers(tmpl))
    loops = feed.loops()
    assert list(loops) == ["ML-11011"] and loops["ML-11011"][0]["LOOP TYPE"] == L.LOOP_MOTOR and len(loops["ML-11011"]) == 7
    wb = openpyxl.load_workbook(io.BytesIO(L.generate(feed, tmpl)))
    assert wb.sheetnames == ["Loop_ML-11011"]
    ws = wb.worksheets[0]
    assert [ws.cell(19 + k, 23).value for k in range(7)] == [f"100-{t}" for t, _, _ in MOTOR_SIGNALS]      # tag per block row, template order
    assert {ws.cell(19 + k, 24).value for k in range(7)} == {"ML-11011"}                                     # one loop name on every row
    assert ws["A2"].value == '="LOOP NAME: "&X19' and ws.cell(19, 24).value == "ML-11011"


@needs_template
def test_vfd_motor_gets_the_vfd_sheet_with_speed_blocks_and_switches_get_their_own_types():
    tmpl = TEMPLATES["with"].read_bytes()
    sigs = [mrow(f"100-{t}", d, io, ch=i + 1) for i, (t, d, io) in enumerate(MOTOR_SIGNALS)]
    sigs += [mrow("100-SC-ML-11011", "SPEED CONTROL", "AO", ch=1), mrow("100-SI-ML-11011", "SPEED FEEDBACK", "AI", ch=2)]
    for s_ in sigs:
        s_["LOOP NO"] = "ML-11011"
    nl = {"LOOP NO": None}
    sigs += [mrow("100-LSH-20001", "HIGH LEVEL SWITCH", "DI", ch=9, **nl), mrow("100-FSL-20002", "LOW FLOW", "DI", ch=10, **nl),
             mrow("100-PS-20003", "X", "DI", ch=11, **nl), mrow("100-TSH-20004", "X", "DI", ch=12, **nl),
             mrow("100-ZSO-30001", "OPEN FEEDBACK", "DI", ch=13, **nl)]
    rows, _ = L.read_assignment(assignment2(sigs))
    feed = L.build_loop_input(rows, L.template_headers(tmpl))
    types = {k: v[0]["LOOP TYPE"] for k, v in feed.loops().items()}
    assert types["ML-11011"] == L.LOOP_VFD and len(feed.loops()["ML-11011"]) == 9
    assert sorted(t for k, t in types.items() if k != "ML-11011") == ["SWITCH - FLOW", "SWITCH - LEVEL", "SWITCH - PRESSURE", "SWITCH - TEMPERATURE"]
    assert any("100-ZSO-30001" == t for _, t, _ in feed.skipped)                   # a valve limit switch is not a switch loop
    out = L.generate(feed, tmpl)
    assert len(openpyxl.load_workbook(io.BytesIO(out)).sheetnames) == 5
