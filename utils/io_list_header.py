"""
io_list_header.py - the universal document header of the I/O List workbook (TABLE OF CONTENTS, ABBREVIATION, IO_BASIS).

The header is the one of the original IO_BASIS sheet: PROJECT / CLIENT / LOCATION / Doc. No. / Rev. No. on the left, the WABAG logo in
the middle, Prepared / Checked / Approved / Date / Pages on the right. No company address and no other field is added.

  * build_header(ws, ...)  lays the header out on a sheet from that sheet's PHYSICAL column widths (merged ranges are computed, never copied):
        a wide sheet gets the three-zone arrangement of IO_BASIS, a narrow one (fewer than WIDE_MIN width units) the same fields stacked.
  * restructure_abbreviation(ab, io, logo)  gives the ABBREVIATION sheet the very IO_BASIS header: the sheet takes the IO_BASIS width and
        header zone widths, the visible three-column abbreviation table is widened to it in proportion.
  * fill_header(ws, meta)  writes the values; the fields are found by their labels, so it works on any sheet built by build_header and on the
        original IO_BASIS header alike.
"""
from __future__ import annotations

import re
from copy import copy
from io import BytesIO
from typing import Optional

from openpyxl.cell.cell import MergedCell
from openpyxl.drawing.image import Image
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# label (as written on the sheet) -> meta key
FIELDS = {"project": "project", "client": "client", "location": "location", "doc. no.": "doc_no", "rev. no.": "rev",
          "prepared": "prepared", "checked": "checked", "approved": "approved", "date": "date", "pages": "pages"}
LABELS = {"project": "PROJECT", "client": "CLIENT", "location": "LOCATION", "doc_no": "Doc. No.", "rev": "Rev. No.",
          "prepared": "Prepared", "checked": "Checked", "approved": "Approved", "date": "Date", "pages": "Pages"}
WIDE_MIN = 150.0                   # total printable width (column units) from which the three-zone arrangement is used
_FRACTIONS = (0.144, 0.455, 0.724, 0.853)       # zone boundaries of the original IO_BASIS header (share of its printable width)
LOGO_EMU_W, LOGO_EMU_H = 201 * 9525, 62 * 9525

_MED = Side(style="medium", color="000000")
_THIN = Side(style="thin", color="000000")


def _key(v) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip().lower()


def widths_of(ws, last_col: int) -> list[float]:
    return [float(ws.column_dimensions[get_column_letter(c)].width or 8.43) for c in range(1, last_col + 1)]


def zones(widths: list[float]) -> Optional[list[int]]:
    """[end column of: left labels, left values, logo, right labels] (1-based) for a wide sheet, None for a narrow one."""
    total = sum(widths)
    if total < WIDE_MIN or len(widths) < 6:
        return None
    cum, acc = [], 0.0
    for w in widths:
        acc += w
        cum.append(acc)
    ends, prev = [], 0
    for f in _FRACTIONS:
        target = f * total
        c = min(range(prev, len(widths) - 1), key=lambda i: abs(cum[i] - target)) + 1
        c = max(c, prev + 1)
        ends.append(c)
        prev = c
    n = len(widths)
    if ends[-1] >= n:                      # no room left for the right values: not a wide sheet
        return None
    return ends


def _merge(ws, r1, c1, r2, c2):
    if (r1, c1) != (r2, c2):
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)


def _frame(ws, r1, c1, r2, c2, left_edge, right_edge, top_edge, bottom_edge):
    """Thin lines everywhere, medium on the outer edge of the whole header (as the original IO_BASIS header)."""
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            ws.cell(r, c).border = Border(left=_MED if (left_edge and c == c1) else _THIN, right=_MED if (right_edge and c == c2) else _THIN,
                                          top=_MED if (top_edge and r == r1) else _THIN, bottom=_MED if (bottom_edge and r == r2) else _THIN)


def _cell(ws, r1, c1, r2, c2, text=None, *, label: bool, size: float, left, right, top, bottom, wrap=False, align="left"):
    _merge(ws, r1, c1, r2, c2)
    _frame(ws, r1, c1, r2, c2, left, right, top, bottom)
    a = ws.cell(r1, c1)
    a.value = text
    a.font = Font(name="Calibri", size=size, bold=label)
    a.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)


def build_header(ws, last_col: int, logo: Optional[bytes] = None, row_heights=(18.0, 18.0, 17.6, 17.6, 17.6, 17.6)) -> int:
    """
    Lay the universal header out on `ws` from its column widths and return the number of header rows (the next row is free for the
    sheet's own title bar). Existing cells in the header rows are overwritten, merged ranges there are removed first.
    """
    widths = widths_of(ws, last_col)
    z = zones(widths)
    rows = 6 if z else 12
    for m in [m for m in ws.merged_cells.ranges if m.min_row <= rows]:
        ws.unmerge_cells(str(m))
    for r in range(1, rows + 1):
        for c in range(1, last_col + 1):
            cell = ws.cell(r, c)
            cell.value = None
            cell.style = "Normal"                                  # a named style (e.g. an accent fill) would otherwise show through
            cell.border = Border()
            cell.fill = PatternFill(fill_type=None)
            cell.alignment = Alignment()
            cell.font = Font(name="Calibri", size=11)
    if z:
        lab_l, val_l, logo_end, lab_r = z
        n = last_col
        ws_rows = [(1, 2), (3, 3), (4, 4), (5, 5), (6, 6)]
        left = ["project", "client", "location", "doc_no", "rev"]
        right = ["prepared", "checked", "approved", "date", "pages"]
        for (r1, r2), lk, rk in zip(ws_rows, left, right):
            top, bot = r1 == 1, r2 == 6
            _cell(ws, r1, 1, r2, lab_l, LABELS[lk], label=True, size=11, left=True, right=False, top=top, bottom=bot)
            _cell(ws, r1, lab_l + 1, r2, val_l, None, label=False, size=12, left=False, right=False, top=top, bottom=bot, wrap=True)
            _cell(ws, r1, logo_end + 1, r2, lab_r, LABELS[rk], label=True, size=11, left=False, right=False, top=top, bottom=bot)
            _cell(ws, r1, lab_r + 1, r2, n, None, label=False, size=12, left=False, right=True, top=top, bottom=bot)
        _cell(ws, 1, val_l + 1, 6, logo_end, None, label=False, size=16, left=False, right=False, top=True, bottom=True, align="center")
        logo_box = (val_l + 1, 1, logo_end, 6)
    else:
        n = last_col
        lab_end = max(2, min(3, n - 1))
        _cell(ws, 1, 1, 2, n, None, label=False, size=16, left=True, right=True, top=True, bottom=False, align="center")
        keys = ["project", "client", "location", "doc_no", "rev", "prepared", "checked", "approved", "date", "pages"]
        for i, k in enumerate(keys):
            r = 3 + i
            _cell(ws, r, 1, r, lab_end, LABELS[k], label=True, size=11, left=True, right=False, top=False, bottom=(r == rows))
            _cell(ws, r, lab_end + 1, r, n, None, label=False, size=12 if k == "project" else 11, left=False, right=True, top=False,
                  bottom=(r == rows), wrap=True)
        logo_box = (1, 1, n, 2)
    for i in range(rows):
        ws.row_dimensions[i + 1].hidden = False
        ws.row_dimensions[i + 1].height = row_heights[i] if i < len(row_heights) else 18.0
    if not z:
        ws.row_dimensions[1].height = ws.row_dimensions[2].height = 24.0
        ws.row_dimensions[3].height = 33.0                                   # project name wraps
    if logo:
        place_logo(ws, logo, *logo_box)
    return rows


def _col_px(ws, c: int) -> float:
    return float(ws.column_dimensions[get_column_letter(c)].width or 8.43) * 7 + 5


def place_logo(ws, data: bytes, c1: int, r1: int, c2: int, r2: int) -> None:
    """The logo at its original size (201 x 62 px) centred in the box c1..c2 x r1..r2 (clipped to the box if it is smaller)."""
    img = Image(BytesIO(data))
    ws._images = []                                           # the sheet's own header pictures are replaced
    box_w = sum(_col_px(ws, c) for c in range(c1, c2 + 1))
    box_h = sum((ws.row_dimensions[r].height or 15.0) * 96 / 72 for r in range(r1, r2 + 1))
    w, h = 201.0, 62.0
    k = min(1.0, box_w * 0.9 / w, box_h * 0.9 / h)
    w, h = w * k, h * k
    # absolute offset inside the first cell of the box
    off_x = max(0.0, (box_w - w) / 2.0)
    off_y = max(0.0, (box_h - h) / 2.0)
    col, x = c1, off_x
    while col < c2 and x >= _col_px(ws, col):
        x -= _col_px(ws, col)
        col += 1
    row, y = r1, off_y
    while row < r2 and y >= (ws.row_dimensions[row].height or 15.0) * 96 / 72:
        y -= (ws.row_dimensions[row].height or 15.0) * 96 / 72
        row += 1
    img.anchor = OneCellAnchor(_from=AnchorMarker(col=col - 1, colOff=int(x * 9525), row=row - 1, rowOff=int(y * 9525)),
                               ext=XDRPositiveSize2D(int(w * 9525), int(h * 9525)))
    ws.add_image(img)


# ───────────────────────────── ABBREVIATION: the IO_BASIS header on a narrow three-column table ─────────────────────────────
def _segment_style(target, anchor, last, *, first_col: bool, last_col: bool):
    """Style of one cell of a (re-divided) merged block: look of the source block, its left / right edge only on the outer columns."""
    font, fill, alignment, number_format, border = anchor
    target.font, target.fill, target.alignment, target.number_format = copy(font), copy(fill), copy(alignment), number_format
    target.border = Border(left=copy(border.left) if first_col else Side(), right=copy(last) if last_col else Side(),
                           top=copy(border.top), bottom=copy(border.bottom))


def _snapshot(cell):
    return (copy(cell.font), copy(cell.fill), copy(cell.alignment), cell.number_format, copy(cell.border))


def mirror_header(src, dst, src_ends: list, src_last: int, dst_ends: list, dst_last: int, logo: Optional[bytes] = None, rows: int = 6) -> None:
    """
    Reproduce the three-zone header of `src` (IO_BASIS) in rows 1..rows of `dst`: same labels, fonts, fills, alignment, borders, row
    heights, vertical merges and logo; only the physical columns of each zone differ (`*_ends` = last column of the first four zones).
    The target rows must be empty and unmerged. Value cells are left blank (fill_header writes them).
    """
    src_zones = list(zip([1] + [e + 1 for e in src_ends], src_ends + [src_last]))
    dst_zones = list(zip([1] + [e + 1 for e in dst_ends], dst_ends + [dst_last]))
    for zi, ((s1, s2), (d1, d2)) in enumerate(zip(src_zones, dst_zones)):
        r = 1
        while r <= rows:
            span = next((m for m in src.merged_cells.ranges if m.min_row == r and m.min_col == s1), None)
            r2 = span.max_row if span else r
            _merge(dst, r, d1, r2, d2)
            for rr in range(r, r2 + 1):
                edge = src.cell(rr, s2).border.right
                if not edge.style:
                    edge = src.cell(rr, s1).border.right
                for c in range(d1, d2 + 1):
                    _segment_style(dst.cell(rr, c), _snapshot(src.cell(rr, s1)), edge, first_col=c == d1, last_col=c == d2)
            if zi in (0, 3):                                   # the two label zones carry text; the value and logo zones stay blank
                dst.cell(r, d1).value = src.cell(r, s1).value
            r = r2 + 1
    for r in range(1, rows + 1):
        dst.row_dimensions[r].height = src.row_dimensions[r].height if r in src.row_dimensions else None
    if logo:
        place_logo(dst, logo, dst_zones[2][0], 1, dst_zones[2][1], rows)


def restructure_abbreviation(ab, io, logo: bytes, title_row: int = 7, old_cols: int = 5) -> None:
    """
    `ab` holds the abbreviation table with its title in `title_row` (rows above are discarded) laid out as S.NO. = A, ABBREVIATION = B:C,
    DESCRIPTION = D:E. Result: the IO_BASIS header in rows 1-6, the title in row 7, headings in row 8, the entries below - on seven
    physical columns A..G (S.NO. = A, ABBREVIATION = B:C, DESCRIPTION = D:G). The sheet is as wide as IO_BASIS, so the header has the
    same zone widths and shape; the three table columns keep their proportions to each other.
    """
    last = max(r for r in range(title_row, ab.max_row + 1) if any(ab.cell(r, c).value not in (None, "") for c in range(1, old_cols + 1)))
    old_w = widths_of(ab, old_cols)
    io_last = 11
    io_w = widths_of(io, io_last)
    io_ends = zones(io_w)
    total = sum(io_w)
    bounds = [sum(io_w[:e]) for e in io_ends]                                       # the IO_BASIS header zone boundaries
    scale = total / sum(old_w)
    sno_end, abbr_end = old_w[0] * scale, sum(old_w[:3]) * scale
    cuts = [sno_end, bounds[0], abbr_end, bounds[1], bounds[2], bounds[3], total]
    if cuts != sorted(cuts):
        raise ValueError("The ABBREVIATION table widths no longer fit the header subdivision.")
    new_w = [b - a for a, b in zip([0.0] + cuts[:-1], cuts)]

    table = []                                                                      # (height, values, styles) of title .. last entry
    for r in range(title_row, last + 1):
        table.append((ab.row_dimensions[r].height, [ab.cell(r, c).value for c in range(1, old_cols + 1)],
                      [_snapshot(ab.cell(r, c)) for c in range(1, old_cols + 1)]))
    for m in list(ab.merged_cells.ranges):
        ab.unmerge_cells(str(m))
    for key in list(ab._cells):
        del ab._cells[key]
    for r in list(ab.row_dimensions):
        del ab.row_dimensions[r]
    ab.column_dimensions.clear()
    for c, w in enumerate(new_w, 1):
        ab.column_dimensions[get_column_letter(c)].width = round(w, 6)
    ab._images = []
    ab.conditional_formatting = type(ab.conditional_formatting)()

    for i, (height, values, styles) in enumerate(table):
        r = 7 + i
        # (first old column, last old column, first new column, last new column)
        blocks = [(1, 5, 1, 7)] if i == 0 else [(1, 1, 1, 1), (2, 3, 2, 3), (4, 5, 4, 7)]
        for o1, o2, n1, n2 in blocks:
            _merge(ab, r, n1, r, n2)
            edge = styles[o2 - 1][4].right if styles[o2 - 1][4].right.style else styles[o1 - 1][4].right
            for c in range(n1, n2 + 1):
                _segment_style(ab.cell(r, c), styles[o1 - 1], edge, first_col=c == n1, last_col=c == n2)
            ab.cell(r, n1).value = values[o1 - 1]
        ab.row_dimensions[r].height = height
    mirror_header(io, ab, io_ends, io_last, [2, 4, 5, 6], 7, logo)
    ab.print_area = f"A1:G{6 + len(table)}"


def field_cells(ws, max_row: int = 14) -> dict:
    """{meta key: value cell} of the header fields, found by their labels (value cell = the cell right of the label's merged range)."""
    out = {}
    for r in range(1, max_row + 1):
        for c in range(1, ws.max_column + 1):
            cell = ws.cell(r, c)
            if isinstance(cell, MergedCell) or cell.value is None:
                continue
            k = FIELDS.get(_key(cell.value))
            if not k or k in out:
                continue
            end = c
            for m in ws.merged_cells.ranges:
                if m.min_row == r and m.min_col == c:
                    end = m.max_col
            out[k] = ws.cell(r, end + 1)
    return out


def fill_header(ws, meta: dict) -> list[str]:
    """Write `meta` ({project, client, location, doc_no, rev, prepared, checked, approved, date, pages}) into the header fields found on
    the sheet. A field with no value is left empty - never guessed. Returns the field keys that could not be found on the sheet."""
    cells = field_cells(ws)
    missing = [k for k in LABELS if k not in cells]
    for k, cell in cells.items():
        v = meta.get(k)
        cell.value = v if v not in (None, "") else None
        if k in ("project",):
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    return missing
