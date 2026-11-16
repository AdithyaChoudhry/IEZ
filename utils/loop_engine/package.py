"""
Final Loop Wiring workbook - built at the OOXML package level.

The approved templates carry real drawing objects (lines / boxes / connectors in xl/drawings/drawingN.xml). Loading them with
openpyxl would drop that geometry, so each loop sheet is a byte-for-byte clone of the template's worksheet part and drawing part:
only the DATA BLOCK cells (row 2 loop fields, one row per signal) are written, the cached results of the template's own label
formulas are refreshed (Excel recalculates on open anyway), everything else - formulas, styles, merges, print setup, page
footer, row heights, column widths, drawing geometry - is untouched.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, Optional
from xml.sax.saxutils import escape

from openpyxl.utils import column_index_from_string, get_column_letter

from .registry import Registry, Template

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DATA_FIRST_COL = column_index_from_string("AF")
INVALID_SHEET_CHARS = re.compile(r"[\[\]\:\*\?\/\\]")


@dataclass
class GenLoop:
    sheet_name: str
    template: Template
    loop_fields: dict[str, Any]                    # LOOP_NAME / LOOP_SERVICE / DOC_NO / REV
    rows: dict[int, dict[str, Any]]                # worksheet row -> {DATA BLOCK field: value}   (every slot row of the template)
    cover: dict[str, Any] = field(default_factory=dict)


def safe_sheet_name(name: str, used: set[str]) -> str:
    base = INVALID_SHEET_CHARS.sub("_", name).strip().strip("'") or "LOOP"
    base = base[:31]
    cand, i = base, 1
    while cand.lower() in used:
        i += 1
        suf = f"_{i}"
        cand = base[:31 - len(suf)] + suf
    used.add(cand.lower())
    return cand


# ---- formula evaluation (the template labels are concatenations of literals and absolute cell references) ------------
_TOKEN = re.compile(r'\s*(?:"((?:[^"]|"")*)"|\$?([A-Z]{1,3})\$?(\d+)|(\d+(?:\.\d+)?))\s*')


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def eval_label(formula: str, values: dict[str, Any]) -> Optional[str]:
    f = formula.strip().lstrip("=")
    pos, out = 0, []
    expect_operand = True
    while pos < len(f):
        if expect_operand:
            m = _TOKEN.match(f, pos)
            if not m:
                return None
            if m.group(1) is not None:
                out.append(m.group(1).replace('""', '"'))
            elif m.group(2) is not None:
                out.append(_fmt(values.get(f"{m.group(2)}{m.group(3)}")))
            else:
                out.append(m.group(4))
            pos = m.end()
            expect_operand = False
        else:
            if f[pos] != "&":
                return None
            pos += 1
            expect_operand = True
    return None if expect_operand else "".join(out)


# ---- worksheet cell surgery --------------------------------------------------------------------------------------------
_ROW = re.compile(r'<row r="(\d+)"([^>]*?)(?:/>|>(.*?)</row>)', re.S)
_CELL = re.compile(r'<c r="([A-Z]{1,3})(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.S)


def _attr(attrs: str, name: str) -> Optional[str]:
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return m.group(1) if m else None


def _cell_xml(ref: str, style: Optional[str], value: Any) -> str:
    s = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}"{s} t="b"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{s}><v>{_fmt(value) if isinstance(value, float) else value}</v></c>'
    t = str(value)
    sp = ' xml:space="preserve"' if t != t.strip() or "  " in t else ""
    return f'<c r="{ref}"{s} t="inlineStr"><is><t{sp}>{escape(t)}</t></is></c>'


def _fill_data_cells(xml: str, edits: dict[int, dict[str, Any]], formulas_values: dict[str, Any]) -> tuple[str, int]:
    """Write DATA BLOCK cells (edits: row -> {col letter: value}) and refresh the cached value of every formula cell."""
    unsupported = 0

    def row_sub(m: re.Match) -> str:
        nonlocal unsupported
        rno, attrs, inner = int(m.group(1)), m.group(2), m.group(3) or ""
        cells: dict[int, str] = {}
        styles: dict[int, Optional[str]] = {}
        for cm in _CELL.finditer(inner):
            col = column_index_from_string(cm.group(1))
            cells[col] = cm.group(0)
            styles[col] = _attr(cm.group(3), "s")
        for col_letter, val in edits.get(rno, {}).items():
            col = column_index_from_string(col_letter)
            cells[col] = _cell_xml(f"{col_letter}{rno}", styles.get(col), val)
        # refresh formula caches
        for col, cx in list(cells.items()):
            if "<f>" not in cx and "<f " not in cx:
                continue
            fm = re.search(r"<f[^>]*>(.*?)</f>", cx, re.S)
            if not fm:
                continue
            formula = fm.group(1).replace("&amp;", "&").replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")
            res = eval_label(formula, formulas_values)
            if res is None:
                unsupported += 1
                continue
            ref = f"{get_column_letter(col)}{rno}"
            s = styles.get(col)
            cells[col] = f'<c r="{ref}"' + (f' s="{s}"' if s else "") + f' t="str"><f>{fm.group(1)}</f><v>{escape(res)}</v></c>'
        body = "".join(cells[c] for c in sorted(cells))
        return f'<row r="{rno}"{attrs}>{body}</row>'

    return _ROW.sub(row_sub, xml), unsupported


def fill_sheet(xml: str, tpl: Template, loop_fields: dict[str, Any], rows: dict[int, dict[str, Any]]) -> tuple[str, int]:
    edits: dict[int, dict[str, Any]] = defaultdict_dict()
    values: dict[str, Any] = {}
    for label, ref in tpl.loop_cells.items():
        col, rno = re.match(r"([A-Z]+)(\d+)", ref).groups()
        edits[int(rno)][col] = loop_fields.get(label)
        values[ref] = loop_fields.get(label)
    for rno, fields in rows.items():
        for fld, val in fields.items():
            col = tpl.columns.get(fld)
            if not col:
                continue
            edits[rno][col] = val
            values[f"{col}{rno}"] = val
    return _fill_data_cells(xml, edits, values)


class defaultdict_dict(dict):
    def __missing__(self, k):
        self[k] = {}
        return self[k]


# ---- package assembly -------------------------------------------------------------------------------------------------
def _style_patch(styles: str) -> tuple[str, dict[str, int]]:
    """Append fonts / fills / borders / cellXfs for the INDEX sheet; returns the new style ids."""
    def bump(tag: str, items: str, s: str) -> tuple[str, int]:
        m = re.search(rf'<{tag} count="(\d+)"([^>]*)>', s)
        n = int(m.group(1))
        s = s.replace(m.group(0), f'<{tag} count="{n + items.count("<" + tag[:-1] + ">") + items.count("<" + tag[:-1] + " ")}"{m.group(2)}>', 1)
        s = s.replace(f"</{tag}>", items + f"</{tag}>", 1)
        return s, n
    ids: dict[str, int] = {}
    fonts = ('<font><b/><sz val="14"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font>'
             '<font><sz val="10"/><name val="Arial"/></font><font><u/><sz val="10"/><color rgb="FF0563C1"/><name val="Arial"/></font><font><b/><sz val="10"/><name val="Arial"/></font>')
    styles, f0 = bump("fonts", fonts, styles)
    ids.update(f_title=f0, f_head=f0 + 1, f_norm=f0 + 2, f_link=f0 + 3, f_bold=f0 + 4)
    fills = ('<fill><patternFill patternType="solid"><fgColor rgb="FF2F5597"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFC6EFCE"/></patternFill></fill>'
             '<fill><patternFill patternType="solid"><fgColor rgb="FFFFEB9C"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFC7CE"/></patternFill></fill>')
    styles, l0 = bump("fills", fills, styles)
    ids.update(l_head=l0, l_pass=l0 + 1, l_rev=l0 + 2, l_err=l0 + 3)
    borders = '<border><left style="thin"><color rgb="FF808080"/></left><right style="thin"><color rgb="FF808080"/></right><top style="thin"><color rgb="FF808080"/></top><bottom style="thin"><color rgb="FF808080"/></bottom><diagonal/></border>'
    styles, b0 = bump("borders", borders, styles)
    ids["b_thin"] = b0
    xfs = []
    def xf(font, fill=0, border=0, wrap=False, bold_center=False):
        a = '<alignment vertical="center"' + (' wrapText="1"' if wrap else "") + (' horizontal="center"' if bold_center else "") + "/>"
        xfs.append(f'<xf numFmtId="0" fontId="{font}" fillId="{fill}" borderId="{border}" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">{a}</xf>')
        return len(xfs) - 1
    keys = {"title": xf(ids["f_title"]), "head": xf(ids["f_head"], ids["l_head"], ids["b_thin"], True, True), "cell": xf(ids["f_norm"], 0, ids["b_thin"], True),
            "link": xf(ids["f_link"], 0, ids["b_thin"]), "bold": xf(ids["f_bold"]), "norm": xf(ids["f_norm"], 0, 0, True),
            "pass": xf(ids["f_bold"], ids["l_pass"], ids["b_thin"], False, True), "review": xf(ids["f_bold"], ids["l_rev"], ids["b_thin"], False, True),
            "error": xf(ids["f_bold"], ids["l_err"], ids["b_thin"], False, True)}
    m = re.search(r'<cellXfs count="(\d+)">', styles)
    base = int(m.group(1))
    styles = styles.replace(m.group(0), f'<cellXfs count="{base + len(xfs)}">', 1).replace("</cellXfs>", "".join(xfs) + "</cellXfs>", 1)
    return styles, {k: base + v for k, v in keys.items()}


def _cover_sheet(loops: list[GenLoop], info: dict, st: dict[str, int]) -> str:
    cols = [("NO.", 5), ("SHEET", 22), ("LOOP NAME", 20), ("LOOP SERVICE", 34), ("LOOP TYPE", 14), ("SPD", 6), ("TERM", 6), ("TYPICAL", 9), ("TEMPLATE", 34), ("SIGNALS", 9), ("STATUS", 10), ("REVIEW NOTES", 60)]
    rows: list[str] = []

    def c(ref: str, v: Any, style: str, link: Optional[str] = None) -> str:
        return _cell_xml(ref, str(st[style]), v)

    def r(n: int, cells: list[str], ht: Optional[float] = None) -> str:
        return f'<row r="{n}"' + (f' ht="{ht}" customHeight="1"' if ht else "") + ">" + "".join(cells) + "</row>"

    rows.append(r(1, [c("A1", "LOOP WIRING - INDEX", "title")], 22))
    meta = [("Generated by", "iEZ Loop Wiring Generator"), ("Source I/O Assignment", info.get("source", "")), ("Loop sheets", str(len(loops))),
            ("Signals", str(sum(len(l.rows) for l in loops))), ("Template library", info.get("library", "")),
            ("Method", "I/O Assignment → group by LOOP_NAME → LOOP TYPE + SPD + TERM → TYPICAL → template → FIELD CODE mapping → DATA BLOCK → formula-driven drawing")]
    n = 2
    for k, v in meta:
        rows.append(r(n, [c(f"A{n}", k, "bold"), c(f"C{n}", v, "norm")])); n += 1
    n += 1
    head_row = n
    rows.append(r(n, [c(f"{get_column_letter(i + 1)}{n}", h, "head") for i, (h, _) in enumerate(cols)], 22)); n += 1
    links = []
    for i, l in enumerate(loops, start=1):
        cv = l.cover
        stat = cv.get("status", "PASS")
        cells = [c(f"A{n}", i, "cell"), _cell_xml(f"B{n}", str(st["link"]), l.sheet_name), c(f"C{n}", l.loop_fields.get("LOOP_NAME"), "cell"), c(f"D{n}", l.loop_fields.get("LOOP_SERVICE"), "cell"),
                 c(f"E{n}", cv.get("loop_type"), "cell"), c(f"F{n}", cv.get("spd"), "cell"), c(f"G{n}", cv.get("term"), "cell"), c(f"H{n}", l.template.typical, "cell"),
                 c(f"I{n}", l.template.sheet_name, "cell"), c(f"J{n}", cv.get("signals"), "cell"),
                 c(f"K{n}", stat, {"PASS": "pass", "REVIEW": "review", "ERROR": "error"}.get(stat, "cell")), c(f"L{n}", cv.get("notes", ""), "cell")]
        rows.append(r(n, cells))
        q = l.sheet_name.replace("'", "''")
        links.append(f'<hyperlink ref="B{n}" location="\'{escape(q)}\'!A1" display="{escape(l.sheet_name)}"/>')
        n += 1
    colxml = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, (_, w) in enumerate(cols))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<worksheet xmlns="{MAIN_NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><sheetViews><sheetView showGridLines="0" workbookViewId="0" tabSelected="1"><pane ySplit="{head_row}" topLeftCell="A{head_row + 1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            f'<sheetFormatPr defaultRowHeight="15"/><cols>{colxml}</cols><sheetData>{"".join(rows)}</sheetData>'
            + (f'<hyperlinks>{"".join(links)}</hyperlinks>' if links else "") +
            '<pageMargins left="0.4" right="0.4" top="0.5" bottom="0.5" header="0.3" footer="0.3"/><pageSetup paperSize="8" orientation="landscape" fitToHeight="0"/></worksheet>')


def build_workbook(reg: Registry, loops: list[GenLoop], info: Optional[dict] = None) -> tuple[bytes, dict]:
    info = info or {}
    zin = zipfile.ZipFile(io.BytesIO(reg.template_bytes))
    names = set(zin.namelist())
    styles, st = _style_patch(zin.read("xl/styles.xml").decode("utf8"))
    stats = {"unsupported_formulas": 0}

    out = io.BytesIO()
    z = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    sheet_entries, def_names, overrides, wb_rels = [], [], [], []

    # INDEX / COVER = sheet1
    z.writestr("xl/worksheets/sheet1.xml", _cover_sheet(loops, info, st))
    sheet_entries.append(("INDEX", 1, "rIdSheet1"))
    overrides.append('<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    wb_rels.append('<Relationship Id="rIdSheet1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>')

    for i, gl in enumerate(loops, start=1):
        n = i + 1
        tpl = gl.template
        sx = zin.read(tpl.part).decode("utf8")
        sx, uns = fill_sheet(sx, tpl, gl.loop_fields, gl.rows)
        stats["unsupported_formulas"] += uns
        sx = sx.replace('tabSelected="1"', "")
        has_drawing = tpl.drawing is not None and tpl.drawing in names
        z.writestr(f"xl/worksheets/sheet{n}.xml", sx)
        overrides.append(f'<Override PartName="/xl/worksheets/sheet{n}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        if has_drawing:
            z.writestr(f"xl/drawings/drawing{i}.xml", zin.read(tpl.drawing))
            z.writestr(f"xl/worksheets/_rels/sheet{n}.xml.rels",
                       f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{REL_NS}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing{i}.xml"/></Relationships>')
            overrides.append(f'<Override PartName="/xl/drawings/drawing{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>')
        sheet_entries.append((gl.sheet_name, n, f"rIdSheet{n}"))
        wb_rels.append(f'<Relationship Id="rIdSheet{n}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{n}.xml"/>')
        area = tpl.print_area or "$A$1:$AD$51"
        q = gl.sheet_name.replace("'", "''")
        def_names.append(f'<definedName name="_xlnm.Print_Area" localSheetId="{i}">\'{escape(q)}\'!{area}</definedName>')

    # shared parts
    z.writestr("xl/styles.xml", styles)
    overrides.append('<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>')
    wb_rels.append('<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
    if "xl/sharedStrings.xml" in names:
        z.writestr("xl/sharedStrings.xml", zin.read("xl/sharedStrings.xml"))
        overrides.append('<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>')
        wb_rels.append('<Relationship Id="rIdSS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>')
    if "xl/theme/theme1.xml" in names:
        z.writestr("xl/theme/theme1.xml", zin.read("xl/theme/theme1.xml"))
        overrides.append('<Override PartName="/xl/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>')
        wb_rels.append('<Relationship Id="rIdTheme" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>')

    sheets_xml = "".join(f'<sheet name="{escape(nm, {chr(34): "&quot;"})}" sheetId="{sid}" r:id="{rid}"/>' for nm, sid, rid in sheet_entries)
    z.writestr("xl/workbook.xml",
               '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               f'<workbook xmlns="{MAIN_NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><workbookPr/>'
               '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="28800" windowHeight="12210" activeTab="0"/></bookViews>'
               f'<sheets>{sheets_xml}</sheets>' + (f'<definedNames>{"".join(def_names)}</definedNames>' if def_names else "") + '<calcPr calcId="162913" fullCalcOnLoad="1"/></workbook>')
    z.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{REL_NS}">{"".join(wb_rels)}</Relationships>')
    z.writestr("_rels/.rels", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{REL_NS}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    z.writestr("[Content_Types].xml",
               '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
               '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' + "".join(overrides) + "</Types>")
    z.close()
    return out.getvalue(), stats
