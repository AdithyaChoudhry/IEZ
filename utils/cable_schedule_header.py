"""
cable_schedule_header.py - one standard document header (rows 1-6) for every Cable Schedule worksheet
(Instrument, MCC DI, MCC DO, VFD, MOV, LCP), filled from the workbook's COVERSHEET.

    Band 1 | logo                 | <SHEET TYPE> CABLE SCHEDULE         | DOC NO  / REV NO  / DATE
           |                      | <document title of the cover>       |
    Band 2 | contractor + address | PROJECT / CLIENT / PMC              | PREPARED BY / CHECKED BY / APPROVED BY

The cover fields are found by their LABELS (Job No., Doc. Code, CLIENT, REV ...), never by a fixed address, and each header
cell is a live formula on the COVERSHEET, so editing the cover updates every sheet. A field the cover does not carry shows
TBA and is reported - nothing is guessed. When the output has no COVERSHEET sheet the same values are written as text.

DOC NO is the cover's Doc. Code + Serial No. (the Job No. / Project code are project specific and are not part of it).
REV is the cover's current Rev. number; DATE / PREPARED / CHECKED / APPROVED are taken from the revision-table row of that REV.
"""
from __future__ import annotations

import re
from copy import copy
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Optional

from openpyxl.cell.cell import MergedCell
from openpyxl.drawing.image import Image
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter, quote_sheetname

HEADER_ROWS = 6
ROW_HEIGHTS = (30.0, 40.0, 30.0, 26.0, 26.0, 26.0)
ADDRESS = "WABAG HOUSE, No.17,200 Feet Thoraipakkam Pallavaram Main Road\nS.Kolathur, Chennai - 600117, India"
LOGO_OFFSET = (231319, 157224)            # EMU from the top-left corner of A1 (as the Instrument template places its logo)
LOGO_HEIGHT_EMU = 709930
_THIN = Side(style="thin", color="000000")
_BOX = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_LABEL_FILL = PatternFill("solid", fgColor="D9D9D9")
_NONE = PatternFill(fill_type=None)


def _txt(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def _key(v: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _txt(v).lower())


def find_cover(wb) -> Optional[str]:
    names = list(wb.sheetnames)
    for n in names:
        if _key(n) == "coversheet":
            return n
    for n in names:
        if "cover" in _key(n):
            return n
    return None


# ── reading the cover ────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Field:
    value: str = "TBA"                    # what the cover holds now (used when no live formula is possible)
    expr: Optional[str] = None            # formula body (no '=') on the cover sheet
    found: bool = False
    is_date: bool = False


@dataclass
class Cover:
    sheet: str
    fields: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


def _cells(ws):
    for row in ws.iter_rows():
        for c in row:
            if not isinstance(c, MergedCell) and c.value not in (None, ""):
                yield c


def _find(ws, labels: set, row: Optional[int] = None):
    for c in _cells(ws):
        if (row is None or c.row == row) and _key(c.value) in labels:
            return c
    return None


def _anchor(ws, cell):
    """The top-left cell of the merged range a cell belongs to (the cell itself when it is not merged)."""
    if isinstance(cell, MergedCell):
        for m in ws.merged_cells.ranges:
            if cell.coordinate in m:
                return ws.cell(m.min_row, m.min_col)
    return cell


def _right_value(ws, c):
    """The value cell of a 'LABEL : value' row - the first non-empty cell after the colon, or (still empty) the first unmerged cell
    after it, so a header formula can follow later edits of the cover."""
    colon, first_empty = False, None
    for cc in range(c.column + 1, min(ws.max_column, c.column + 14) + 1):
        cell = ws.cell(c.row, cc)
        if isinstance(cell, MergedCell):
            continue
        if _txt(cell.value) in (":", "-"):
            colon = True
            continue
        if cell.value not in (None, ""):
            return cell
        if colon and first_empty is None:
            first_empty = cell
    return first_empty


def _below_value(ws, c):
    return _anchor(ws, ws.cell(c.row + 1, c.column))


def read_cover(wb, sheet: str) -> Cover:
    ws = wb[sheet]
    q = quote_sheetname(sheet)
    cover = Cover(sheet=sheet)

    def ref(cell, absolute_col_row=True) -> str:
        return f"{q}!${get_column_letter(cell.column)}${cell.row}"

    def put(name: str, cell, label: str, is_date: bool = False):
        if cell is None:
            cover.fields[name] = Field()
            cover.warnings.append(f"COVERSHEET: {label} not found - the header shows TBA.")
            return
        empty = _txt(cell.value) == ""
        cover.fields[name] = Field(value="TBA" if empty else (cell.value if hasattr(cell.value, "strftime") else _txt(cell.value)),
                                   expr=f'IF({ref(cell)}="","TBA",{ref(cell)})', found=not empty, is_date=is_date)
        if empty:
            cover.warnings.append(f"COVERSHEET: {label} is empty - the header shows TBA.")

    # document title: the text that follows the DOCUMENT TITLE label inside its own cell (the cover generator's layout) or, when
    # the cell holds the label only, the first cell under it that is not another label (the older layout)
    title_cell, title_expr, title_val = None, None, ""
    other_labels = {"stampingarea", "documentclass", "discipline"}
    for c in _cells(ws):
        if _key(c.value).startswith("documenttitle"):
            rest = _txt(re.sub(r"(?i)document\s*title", "", str(c.value), count=1))
            if not rest:
                for r in range(c.row + 1, c.row + 4):
                    cell = ws.cell(r, c.column)
                    if isinstance(cell, MergedCell) or not _txt(cell.value):
                        continue
                    if _key(cell.value) in other_labels:
                        break
                    title_cell = cell
                    break
            if title_cell is None:
                title_val = rest
                inner = f'TRIM(SUBSTITUTE(SUBSTITUTE({ref(c)},"DOCUMENT TITLE",""),CHAR(10),""))'
                title_expr = f'IF({inner}="","TBA",{inner})'
            break
    if title_expr:
        cover.fields["title"] = Field(value=title_val or "TBA", expr=title_expr, found=bool(title_val))
        if not title_val:
            cover.warnings.append("COVERSHEET: DOCUMENT TITLE not found or empty - the header shows TBA.")
    else:
        put("title", title_cell, "DOCUMENT TITLE")

    # job-number strip: PROJECT description is the large cell at the left of the 'Job No.' row; Doc code / serial / rev sit under their labels
    job = _find(ws, {"jobno"})
    put("project", _anchor(ws, ws.cell(job.row, 1)) if job else None, "PROJECT (project description)")
    code_l = _find(ws, {"doccode"}, job.row if job else None) or _find(ws, {"doccode"})
    ser_l = _find(ws, {"serialno"}, job.row if job else None) or _find(ws, {"serialno"})
    rev_l = _find(ws, {"rev", "revno", "revision"}, job.row if job else None)
    code, ser = (_below_value(ws, code_l) if code_l else None), (_below_value(ws, ser_l) if ser_l else None)
    rev = _below_value(ws, rev_l) if rev_l else None
    if code is None:
        cover.fields["doc_no"] = Field()
        cover.warnings.append("COVERSHEET: Doc. Code not found - DOC NO shows TBA.")
    else:
        cs = ref(code)
        ctxt = _txt(code.value)
        if ser is not None:
            ss = ref(ser)
            stxt = _txt(ser.value)
            cover.fields["doc_no"] = Field(value=f"{ctxt}-{stxt}" if ctxt and stxt else (ctxt or "TBA"),
                                           expr=f'IF({cs}="","TBA",{cs}&IF({ss}="","","-"&{ss}))', found=bool(ctxt))
        else:
            cover.fields["doc_no"] = Field(value=ctxt or "TBA", expr=f'IF({cs}="","TBA",{cs})', found=bool(ctxt))
            cover.warnings.append("COVERSHEET: Serial No. not found - DOC NO shows the Doc. Code only.")
        if not ctxt:
            cover.warnings.append("COVERSHEET: Doc. Code is empty - DOC NO shows TBA.")
    put("rev", rev, "Rev.")

    for name, labels, label in (("client", {"client"}, "CLIENT"), ("pmc", {"pmc"}, "PMC"), ("contractor", {"contractor"}, "CONTRACTOR")):
        lab = _find(ws, labels)
        put(name, _right_value(ws, lab) if lab else None, label)

    # revision table: header row REV / DATE / ... ; its data rows are the rows above it (below DISCIPLINE)
    hdr_row, cols = None, {}
    for c in _cells(ws):
        if _key(c.value) == "rev":
            found = {}
            for x in _cells_in_row(ws, c.row):          # 'PREPARED' / 'PREPARED BY', 'CHECKED' / 'CHECKED BY' ... both spellings exist
                k = _key(x.value)
                for stem in ("date", "prepared", "checked", "approved"):
                    if k.startswith(stem) and stem not in found:
                        found[stem] = x
            if len(found) == 4:
                hdr_row = c.row
                cols = {"rev": c.column, **{stem: found[stem].column for stem in found}}
                break
    if hdr_row is None:
        for n in ("date", "prepared_by", "checked_by", "approved_by"):
            cover.fields[n] = Field()
        cover.warnings.append("COVERSHEET: revision table not found - DATE / PREPARED / CHECKED / APPROVED show TBA.")
        return cover
    disc = _find(ws, {"discipline"})
    first = (disc.row + 1) if disc and disc.row < hdr_row else max(1, hdr_row - 8)
    last = hdr_row - 1
    rev_txt = _txt(rev.value) if rev is not None else ""
    match_row = None
    for r in range(first, last + 1):
        v = ws.cell(r, cols["rev"]).value
        if v not in (None, "") and _txt(v) == rev_txt and rev_txt != "":
            match_row = r
            break
    rng = lambda col: f"{q}!${get_column_letter(col)}${first}:${get_column_letter(col)}${last}"
    key_rng = f'INDEX({rng(cols["rev"])}&"",0)'
    revref = ref(rev) if rev is not None else '""'
    for name, col in (("date", cols["date"]), ("prepared_by", cols["prepared"]), ("checked_by", cols["checked"]),
                      ("approved_by", cols["approved"])):
        val = ws.cell(match_row, col).value if match_row else None
        ok = match_row is not None and val not in (None, "")
        cover.fields[name] = Field(value=(val if hasattr(val, "strftime") else _txt(val)) if ok else "TBA",
                                   expr=f'IFERROR(IF(INDEX({rng(col)},MATCH({revref}&"",{key_rng},0))="","TBA",INDEX({rng(col)},MATCH({revref}&"",{key_rng},0))),"TBA")',
                                   found=ok, is_date=(name == "date"))
        if not ok:
            cover.warnings.append(f"COVERSHEET: {name.replace('_', ' ').upper()} of revision {rev_txt or '?'} not found in the revision table - TBA.")
    return cover


def _cells_in_row(ws, r):
    for c in ws[r]:
        if not isinstance(c, MergedCell) and c.value not in (None, ""):
            yield c


# ── writing the header ───────────────────────────────────────────────────────────────────────────────────────────────
def _zones(widths: list[float]) -> tuple[int, int]:
    """(last column of the left zone, last column of the right zone) from the column widths (1-based list index = column)."""
    n = len(widths) - 1
    total = sum(widths[1:])
    left, acc = 1, 0.0
    for c in range(1, n + 1):
        acc += widths[c]
        left = c
        if acc >= max(0.20 * total, 56.0):
            break
    right_start, acc = n, 0.0
    for c in range(n, left + 1, -1):
        acc += widths[c]
        right_start = c
        if acc >= max(0.27 * total, 44.0):
            break
    right_start = max(right_start, left + 2)
    return left, right_start - 1


def _split(widths, c1, c2, share=0.42, minimum=15.0) -> int:
    """Last column of the label part of a zone c1..c2 (>= c1, < c2 when the zone has more than one column)."""
    if c1 >= c2:
        return c1
    total = sum(widths[c1:c2 + 1])
    acc, end = 0.0, c1
    for c in range(c1, c2):
        acc += widths[c]
        end = c
        if acc >= max(share * total, minimum):
            break
    return end


def _clear(ws, last_col: int):
    for m in [m for m in ws.merged_cells.ranges if m.max_row <= HEADER_ROWS]:
        ws.unmerge_cells(str(m))
    for r in range(1, HEADER_ROWS + 1):
        for c in range(1, max(last_col, ws.max_column) + 1):
            cell = ws.cell(r, c)
            cell.value = None
            cell.fill = _NONE
            cell.border = Border()
        ws.row_dimensions[r].height = ROW_HEIGHTS[r - 1]


def _block(ws, r1, c1, r2, c2, value=None, *, bold=False, size=10, fill=None, align="center", wrap=True, number_format=None):
    if (r2, c2) != (r1, c1):
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            cell = ws.cell(r, c)
            cell.border = _BOX
            if fill is not None:
                cell.fill = fill
    a = ws.cell(r1, c1)
    if value is not None:
        a.value = value
    a.font = Font(name="Calibri", size=size, bold=bold)
    a.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
    if number_format:
        a.number_format = number_format


def _val(cover: Cover, name: str, live: bool):
    f = cover.fields.get(name) or Field()
    if live and f.expr:
        return "=" + f.expr
    v = f.value
    return v


def apply_header(ws, cover: Cover, last_col: int, sheet_title: str, live: bool = True) -> bool:
    """Write the standard header. False (sheet untouched) when the sheet has too few columns for the three zones."""
    widths = [0.0] + [float(ws.column_dimensions[get_column_letter(c)].width or 8.43) for c in range(1, last_col + 1)]
    left, right = _zones(widths)
    c0, c1 = left + 1, right                      # centre zone
    r0 = right + 1                                # right zone
    n = last_col
    if last_col < 7 or not (c0 < c1 and r0 <= n):
        return False
    _clear(ws, last_col)

    def pairs(zone_c1, zone_c2, items, first_row, share=0.42):
        """items: [(label, field)] one per row, rows first_row..; label cell | value cell (stacked into one cell if no room)."""
        end = _split(widths, zone_c1, zone_c2, share)
        for i, (label, name) in enumerate(items):
            r = first_row + i
            v = _val(cover, name, live)
            fld = cover.fields.get(name) or Field()
            fmt = "DD.MM.YYYY" if fld.is_date else None
            if zone_c1 >= zone_c2:
                text = f'="{label}: "&{v[1:]}' if isinstance(v, str) and v.startswith("=") else f"{label}: {v}"
                _block(ws, r, zone_c1, r, zone_c2, text, number_format=fmt)
            else:
                _block(ws, r, zone_c1, r, end, label, bold=True, fill=_LABEL_FILL)
                _block(ws, r, end + 1, r, zone_c2, v, number_format=fmt)

    # band 1
    _block(ws, 1, 1, 3, left, None)                                                       # logo area
    _block(ws, 1, c0, 1, c1, sheet_title, bold=True, size=12, fill=_LABEL_FILL)
    _block(ws, 2, c0, 3, c1, _val(cover, "title", live), bold=True, size=14)
    pairs(r0, n, [("DOC NO", "doc_no"), ("REV NO", "rev"), ("DATE", "date")], 1)
    # band 2
    contractor = _val(cover, "contractor", live)
    if isinstance(contractor, str) and contractor.startswith("="):
        contractor = f'={contractor[1:]}&CHAR(10)&"{ADDRESS.splitlines()[0]}"&CHAR(10)&"{ADDRESS.splitlines()[1]}"'
    else:
        contractor = f"{contractor}\n{ADDRESS}"
    _block(ws, 4, 1, 6, left, contractor, size=9)
    pairs(c0, c1, [("PROJECT", "project"), ("CLIENT", "client"), ("PMC", "pmc")], 4, share=0.16)
    pairs(r0, n, [("PREPARED BY", "prepared_by"), ("CHECKED BY", "checked_by"), ("APPROVED BY", "approved_by")], 4)
    return True


# ── logo ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def place_logo(ws, data: bytes) -> bool:
    """Put `data` at the standard logo position (A1) at the standard height, keeping its proportions. False when it fails."""
    try:
        img = Image(BytesIO(data))
        ws._images = []
        w, h = float(img.width or 1), float(img.height or 1)
        cx = int(LOGO_HEIGHT_EMU * w / h)
        img.anchor = OneCellAnchor(_from=AnchorMarker(col=0, colOff=LOGO_OFFSET[0], row=0, rowOff=LOGO_OFFSET[1]),
                                   ext=XDRPositiveSize2D(cx, LOGO_HEIGHT_EMU))
        ws.add_image(img)
        return True
    except Exception:
        return False


def logo_bytes(ws) -> Optional[bytes]:
    try:
        for im in ws._images:
            data = im._data()
            im.ref = BytesIO(data)              # _data() closes the stream: give the picture a fresh one so it can still be saved
            return data
    except Exception:
        pass
    return None


def apply_standard_headers(wb, sheets: dict, cover_sheet: Optional[str] = None, fill_from: Optional[tuple] = None) -> dict:
    """
    `sheets`: {sheet name: (section title, last column, table header rows or None)}. Returns
    {"applied": [names], "warnings": [...], "logo_sheets": [names]}.
    The Instrument sheet's logo (or the first sheet's) is reused on all of them. `fill_from` = (sheet, cell): the table-header
    fill of that cell is copied to the table headers of the sheets that name header rows (one look on every sheet).
    """
    cover_name = cover_sheet or find_cover(wb)
    if not cover_name:
        return {"applied": [], "warnings": ["No COVERSHEET sheet in the workbook - the sheet headers were left as they are."], "logo_sheets": []}
    cover = read_cover(wb, cover_name)
    out = {"applied": [], "warnings": list(cover.warnings), "logo_sheets": []}
    logo = None
    for name in sheets:
        logo = logo or logo_bytes(wb[name])
    hdr_fill = None
    if fill_from and fill_from[0] in wb.sheetnames:
        f = wb[fill_from[0]][fill_from[1]].fill
        hdr_fill = copy(f) if f is not None and f.fill_type else None
    for name, (title, last_col, hdr_rows) in sheets.items():
        ws = wb[name]
        if not apply_header(ws, cover, last_col, title, live=True):
            out["warnings"].append(f"{name}: too few columns for the standard header - its header was left as it is.")
            continue
        if hdr_fill is not None and hdr_rows:
            for r in hdr_rows:
                for c in range(1, last_col + 1):
                    ws.cell(r, c).fill = copy(hdr_fill)
        own = logo or logo_bytes(ws)
        if own and place_logo(ws, own):
            out["logo_sheets"].append(name)
        out["applied"].append(name)
    return out


# ── keep the header in step with the cover that finally ends up in the workbook ─────────────────────────────────────
def is_standard_header(ws) -> bool:
    v = ws.cell(4, 1).value
    return isinstance(v, str) and ADDRESS.splitlines()[0] in v


def reapply_standard_headers(wb) -> list[str]:
    """
    Rebuild the standard header of every sheet that has one, against the workbook's CURRENT cover sheet. Used after a
    project cover replaced the template's cover (the revision table / label cells may sit on other rows). Never raises.
    """
    done: list[str] = []
    try:
        cover_name = find_cover(wb)
        if not cover_name:
            return done
        cover = read_cover(wb, cover_name)
        for ws in wb.worksheets:
            if ws.title == cover_name or not is_standard_header(ws):
                continue
            title = next((str(c.value) for c in ws[1] if isinstance(c.value, str) and c.value and not c.value.startswith("=")
                          and c.value not in ("DOC NO",)), "")
            last = max((m.max_col for m in ws.merged_cells.ranges if m.max_row <= HEADER_ROWS), default=0)
            if title and last and apply_header(ws, cover, last, title, live=True):
                done.append(ws.title)
    except Exception:
        pass
    return done
