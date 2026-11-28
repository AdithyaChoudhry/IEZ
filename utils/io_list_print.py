"""
io_list_print.py - print settings of the I/O List workbook: the same settings the Excel file carries and the PDF is rendered with.

    page_setup(ws, ...)          paper size, orientation, fit to page, print area, repeated headings (inherited scale / page breaks removed)
    layout_list_sheet(ws)        IO List: A3 landscape, every column on one page width, as many pages down as needed, heading repeated
    prepare_cover(bytes)         the generated copy of the cover sheet: exactly one A4 page
    set_cover_page_total(ws, n)  "Page No." of that copy: 1 OF n
    store_formula_results(...)   writes the computed value next to a formula so that no viewer shows a stale or empty total

No cell value of the engineering content is changed here.
"""
from __future__ import annotations

import io
import math
import re
import textwrap
import zipfile
from functools import lru_cache
from typing import Optional

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.pagebreak import ColBreak, RowBreak
from openpyxl.worksheet.properties import PageSetupProperties

from utils.fast_style import apply as apply_style
from utils.workbook_assembly import _sheet_paths

PAPER = {"A3": 8, "A4": 9}

# IO List: column widths are chosen from the actual contents so that the whole table is readable on one A3 landscape page width
_LIST_BUDGET = 260.0          # total column width (Excel units) aimed at; about 85 % print scale on A3 landscape
_CHARS_PER_UNIT = 0.72        # Calibri 14 characters per unit of column width (upper-case engineering text)
_LINE_PT, _PAD_PT = 18.75, 3.0
_MIN_COL, _MAX_WORD_COL = 7.0, 28.0
_A3_PRINTABLE_PT = 1190.5 - 2 * 18.0
_THIN = Side(style="thin", color="000000")
_GRID = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def page_setup(ws, paper: str, orientation: str, fit_height: int, area: Optional[str] = None, titles: Optional[str] = None,
               margins: Optional[PageMargins] = None) -> None:
    """One page wide; `fit_height` 1 = one page, 0 = as many pages down as the content needs."""
    ps = ws.page_setup
    ps.paperSize, ps.orientation = PAPER[paper], orientation
    ps.paperWidth = ps.paperHeight = None
    ps.fitToWidth, ps.fitToHeight = 1, fit_height
    ps.scale = None                                       # no explicit scale and no manual breaks that would contradict fit-to-page
    ps.firstPageNumber = None                             # an inherited start page number (the template carried an invalid one)
    ps.useFirstPageNumber = None
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.row_breaks, ws.col_breaks = RowBreak(), ColBreak()
    if margins is not None:
        ws.page_margins = margins
    if area:
        ws.print_area = area
    if titles:
        ws.print_title_rows = titles


def content_bounds(ws) -> tuple[int, int]:
    """(last row, last column) holding a value, widened to the merged blocks of those cells - formatted empty cells do not count."""
    merged = {(m.min_row, m.min_col): m for m in ws.merged_cells.ranges}
    last_r = last_c = 1
    for (r, c), cell in ws._cells.items():
        if isinstance(cell, MergedCell) or cell.value in (None, ""):
            continue
        m = merged.get((r, c))
        last_r = max(last_r, m.max_row if m else r)
        last_c = max(last_c, m.max_col if m else c)
    return last_r, last_c


def content_area(ws) -> str:
    r, c = content_bounds(ws)
    return f"A1:{get_column_letter(c)}{r}"


# ── IO List ─────────────────────────────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=65536)
def _lines(text: str, per_line: int) -> int:
    return sum(max(1, len(textwrap.wrap(part, per_line, break_long_words=True))) if part.strip() else 1 for part in text.split("\n"))


def _list_widths(headers: list[str], columns: list[list[str]]) -> list[float]:
    need, least = [], []
    for head, values in zip(headers, columns):
        lengths = sorted(len(v) for v in values) or [0]
        typical = lengths[int(0.9 * (len(lengths) - 1))]
        words = sorted((max((len(w) for w in v.split()), default=0) for v in values)) or [0]
        word = max(max((len(w) for w in head.split()), default=1) * 1.08, words[int(0.99 * (len(words) - 1))])    # bold heading words a bit wider
        lo = min(_MAX_WORD_COL, max(_MIN_COL, word / _CHARS_PER_UNIT + 1.5))
        least.append(lo)
        need.append(max(lo, typical / _CHARS_PER_UNIT + 1.5))
    spare = max(0.0, _LIST_BUDGET - sum(least))
    extra = sum(n - lo for n, lo in zip(need, least))
    share = min(1.0, spare / extra) if extra else 0.0
    return [round(lo + (n - lo) * share, 1) for n, lo in zip(need, least)]


def layout_list_sheet(ws) -> dict:
    """Print layout of the generated IO List sheet (row 1 = column headings). -> {"columns", "rows", "scale", "font_pt"}."""
    rows, ncols = ws.max_row, ws.max_column
    text = [["" if ws.cell(r, c).value is None else str(ws.cell(r, c).value) for c in range(1, ncols + 1)] for r in range(1, rows + 1)]
    widths = _list_widths(text[0], [[text[r][c] for r in range(1, rows)] for c in range(ncols)])
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    per = [max(1, int((w - 1) * _CHARS_PER_UNIT)) for w in widths]
    for r in range(1, rows + 1):
        head = r == 1
        n = max(_lines(text[r - 1][c], max(1, int(per[c] * 0.92)) if head else per[c]) for c in range(ncols))
        ws.row_dimensions[r].height = round(n * _LINE_PT + _PAD_PT, 2)
        for c in range(1, ncols + 1):
            apply_style(ws.cell(r, c), border=_GRID)
    page_setup(ws, "A3", "landscape", 0, area=f"A1:{get_column_letter(ncols)}{rows}", titles="1:1",
               margins=PageMargins(left=0.25, right=0.25, top=0.4, bottom=0.4, header=0.2, footer=0.2))
    ws.print_options.horizontalCentered = True
    scale = min(1.0, _A3_PRINTABLE_PT / (sum(widths) * 5.25 + 3.75 * ncols))
    return {"columns": ncols, "rows": rows, "scale": round(scale, 2), "font_pt": round(14 * scale, 1)}


# ── the cover sheet copy ────────────────────────────────────────────────────────────────────────────────────────
def prepare_cover(cover: bytes) -> bytes:
    """The generated copy of the cover sheet set to exactly one A4 portrait page (the stored cover asset is never touched)."""
    wb = openpyxl.load_workbook(io.BytesIO(cover))
    ws = wb.worksheets[0]
    page_setup(ws, "A4", "portrait", 1, area=content_area(ws))
    ws.print_options.horizontalCentered = True
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def set_cover_page_total(ws, total: int) -> bool:
    """Writes "1 OF <total>" under the cover's "Page No." label (the cover is page 1 of the whole document). False: no such field."""
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c, MergedCell) or not isinstance(c.value, str) or re.sub(r"[^a-z]", "", c.value.lower()) not in ("pageno", "pagenumber"):
                continue
            below = c.row + 1
            for m in ws.merged_cells.ranges:
                if m.min_row == c.row and m.min_col == c.column:
                    below = m.max_row + 1
            target = ws.cell(below, c.column)
            if isinstance(target, MergedCell):
                return False
            if target.value not in (None, "") and not re.fullmatch(r"\s*\d*\s*(of|/)?\s*\d*\s*", str(target.value), re.I):
                return False                                  # something else is written there: left as it is
            target.value = f"1 OF {total}"
            return True
    return False


# ── formula results ─────────────────────────────────────────────────────────────────────────────────────────────
def store_formula_results(workbook: bytes, results: dict) -> bytes:
    """
    {sheet name: {cell: number}} -> the number is stored as the cached result of that cell's formula. openpyxl saves formulas without a
    result, so viewers that do not recalculate would show an empty total. The formula itself is unchanged (Excel recalculates it).
    """
    if not results:
        return workbook
    src = zipfile.ZipFile(io.BytesIO(workbook))
    paths = _sheet_paths(src)
    replace = {}
    for sheet, cells in results.items():
        if sheet not in paths:
            continue
        xml = src.read(paths[sheet]).decode("utf-8")
        for ref, value in cells.items():
            xml = re.sub(rf'(<c r="{ref}"[^>]*?>\s*<f>[^<]*</f>)\s*(?:<v\s*/>|<v>[^<]*</v>)?', rf"\g<1><v>{int(value)}</v>", xml, count=1)
        replace[paths[sheet]] = xml.encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            out.writestr(item, replace.get(item.filename, src.read(item.filename)))
    return buf.getvalue()
