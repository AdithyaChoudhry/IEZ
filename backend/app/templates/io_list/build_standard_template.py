"""
Builds IO_List_Standard_Template.xlsx from an engineering I/O List template workbook (COVERSHEET, TABLE OF CONTENTS, ABBREVIATION, IO_BASIS).

    python build_standard_template.py "<source template>.xlsx" IO_List_Standard_Template.xlsx

The source workbook is only read. The standard template
  * has no COVERSHEET (the centralised Cover Sheet Generator provides it),
  * has the universal header (the IO_BASIS header: project / client / location / doc no. / rev. / prepared / checked / approved / date /
    pages + the WABAG logo, no company address) on TABLE OF CONTENTS, ABBREVIATION and IO_BASIS, with no project data in it,
  * keeps the TABLE OF CONTENTS and ABBREVIATION layouts and the ABBREVIATION text, with the project values, the stale formulas, the client logos
    and the signature pictures removed,
  * keeps the IO_BASIS headings and cell formats as ONE blank prototype row (row 10) and the Note box (rows 12-14); every motor / valve /
    instrument row is generated from the IODB.
"""
import sys
from copy import copy
from pathlib import Path

import openpyxl
from openpyxl.worksheet.cell_range import CellRange

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from utils.io_list_header import build_header, fill_header, restructure_abbreviation  # noqa: E402

SRC, OUT = sys.argv[1], sys.argv[2]
wb = openpyxl.load_workbook(SRC)
del wb["COVERSHEET"]
io, toc, ab = wb["IO_BASIS"], wb["TABLE OF CONTENTS"], wb["ABBREVIATION"]
logo = io._images[0]._data()
io._images[0].ref = __import__("io").BytesIO(logo)             # _data() closes the stream: give the picture a fresh one


def shift_rows(ws, first: int, delta: int, last: int):
    """Move rows first..last by delta rows (values, styles, merged ranges, row heights); pictures are dropped by the caller."""
    heights = {r: ws.row_dimensions[r].height for r in range(first, last + 1)}
    merges = [CellRange(str(m)) for m in ws.merged_cells.ranges if m.min_row >= first]
    for m in merges:
        ws.unmerge_cells(str(m))
    maxc = max(ws.max_column, 17)
    order = range(first, last + 1) if delta < 0 else range(last, first - 1, -1)
    for r in order:
        for c in range(1, maxc + 1):
            src, dst = ws.cell(r, c), ws.cell(r + delta, c)
            dst.value, dst._style = src.value, copy(src._style)
            src.value = None
    for r in range(first, last + 1):
        ws.row_dimensions[r + delta].height = heights[r]
    for m in merges:
        ws.merge_cells(start_row=m.min_row + delta, start_column=m.min_col, end_row=m.max_row + delta, end_column=m.max_col)


# ── IO_BASIS: blank prototype row + note box, no sample engineering rows ──────────────────────────────────────────────
note = {(r, c): (io.cell(r, c).value, copy(io.cell(r, c)._style)) for r in range(66, 69) for c in range(1, 12)}
for m in [m for m in io.merged_cells.ranges if m.min_row >= 10]:
    io.unmerge_cells(str(m))
proto = {c: copy(io.cell(10, c)._style) for c in range(1, 12)}
for r in range(10, 70):
    for c in range(1, 14):
        cell = io.cell(r, c)
        cell.value = None
        cell._style = copy(io.cell(200, c)._style)           # default style
    io.row_dimensions[r].height = None
for c in range(1, 12):
    io.cell(10, c)._style = proto[c]
io.row_dimensions[10].height = 23.4
for (r, c), (v, st) in note.items():
    cell = io.cell(r - 54, c)                                # rows 66-68 -> 12-14
    cell.value, cell._style = v, st
io.merge_cells("B12:K14")
io["A7"].value = "IO BASIS"
fill_header(io, {})                                          # the old project values and the stale COVERSHEET formulas
io.print_area = "A1:K14"
io.page_setup.scale = None
io.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
io.page_setup.fitToWidth, io.page_setup.fitToHeight = 1, 0
io.print_title_rows = "8:9"

# ── TABLE OF CONTENTS ────────────────────────────────────────────────────────────────────────────────────────────────
toc._images = []
for m in [m for m in toc.merged_cells.ranges if m.min_row <= 9]:
    toc.unmerge_cells(str(m))
shift_rows(toc, 10, -3, 84)                                  # the title bar (row 10) moves under the 6 header rows
build_header(toc, 15, logo)
for r in range(1, 7):
    toc.row_dimensions[r].height = io.row_dimensions[r].height or 17.6
toc.row_dimensions[1].height = toc.row_dimensions[2].height = 18.0
for addr in ("O13", "O14"):
    pass
# description rows (old 12-17 -> 9-14), total (old 19 -> 16), revision table (old 24-28 -> 21-25)
toc["B13"].value = "IO LIST"                                 # project suffix is added at generation from the document title
toc["O13"].value = 1
toc["O16"].value = "=SUM(O9:O14)"
for r in (23, 24):                                           # old revision rows 26-27: hard-coded revisions and the COVERSHEET links
    for c in range(1, 16):
        cell = toc.cell(r, c)
        if not hasattr(cell, "column") or cell.__class__.__name__ == "MergedCell":
            continue
        cell.value = None
toc.print_area = "A1:O25"

# ── ABBREVIATION ─────────────────────────────────────────────────────────────────────────────────────────────────────
restructure_abbreviation(ab, io, logo)                       # the IO_BASIS header; title row 7, headings row 8, abbreviations 9-26

for ws in (toc, ab, io):
    for r in range(1, 14):
        pass
for ws, end in ((toc, 25), (ab, 26), (io, 14)):                # empty formatted rows below the print area (the source sheets carry rows to 84)
    if ws.max_row > end:
        ws.delete_rows(end + 1, ws.max_row - end)
    for r in [r for r in ws.row_dimensions if r > end]:
        del ws.row_dimensions[r]
    for key in [k for k in ws._cells if k[0] > end]:
        del ws._cells[key]
for ws, (fw, fh) in ((toc, (1, 1)), (ab, (1, 1)), (io, (1, 0))):      # one page each (IO_BASIS: one page wide, as many high as needed), A4 portrait
    ws.page_setup.paperSize, ws.page_setup.orientation, ws.page_setup.scale = 9, "portrait", None
    ws.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = fw, fh
for ws in (toc, ab, io):                                     # column formats out to column XFD make LibreOffice / Excel crawl: keep A..Z
    for key in list(ws.column_dimensions):
        d = ws.column_dimensions[key]
        if (d.min or 1) > 26:
            del ws.column_dimensions[key]
        elif (d.max or 1) > 26:
            d.max = 26
# the source workbook carries 216 external-workbook links and the defined names that point into them (copy-paste leftovers of other projects):
# they make Excel ask to update links and LibreOffice crawl, and nothing in the three sheets uses them
wb._external_links = []
for name in list(wb.defined_names):
    del wb.defined_names[name]
for ws in wb:
    for name in list(ws.defined_names):
        del ws.defined_names[name]
wb.calculation.fullCalcOnLoad = True
wb.active = 0
wb.save(OUT)
print("saved", OUT, wb.sheetnames)
