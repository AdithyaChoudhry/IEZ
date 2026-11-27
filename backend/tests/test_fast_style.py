"""The faster formatting and merging used for large schedules give exactly what openpyxl's own calls give."""
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, Protection, Side

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils.fast_style import apply, merge_block  # noqa: E402

THIN, THICK = Side(style="thin"), Side(style="thick", color="FF0000")
BLOCKS = [(1, 1, 3, 1), (1, 2, 1, 4), (2, 2, 4, 3), (5, 1, 7, 1), (5, 2, 7, 2), (9, 1, 9, 3)]


def sheet():
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in range(1, 9):
        for c in range(1, 5):
            cell = ws.cell(r, c, f"{r}:{c}")
            cell.border = Border(left=THIN if c % 2 else THICK, right=THIN, top=THICK if r % 3 == 0 else None, bottom=THIN if r % 2 else None)
    ws["A5"].protection = Protection(locked=False)
    return wb, ws


def look(ws):
    return {(r, c): (type(x).__name__, getattr(x, "value", None), repr(x.border), repr(x.font), repr(x.alignment), repr(x.protection))
            for r in range(1, 10) for c in range(1, 5) for x in [ws.cell(r, c)]}


def test_merge_block_matches_openpyxl():
    _a, plain = sheet()
    _b, fast = sheet()
    for r1, c1, r2, c2 in BLOCKS:
        plain.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
        merge_block(fast, r1, c1, r2, c2)
    assert look(fast) == look(plain)
    assert sorted(map(str, fast.merged_cells.ranges)) == sorted(map(str, plain.merged_cells.ranges))


def test_apply_matches_plain_assignment():
    font, align, border = Font(name="Arial", size=12), Alignment(horizontal="center", wrap_text=True), Border(left=THIN, right=THIN)
    _a, plain = sheet()
    _b, fast = sheet()
    for r in range(1, 9):
        for c in range(1, 5):
            plain.cell(r, c).font, plain.cell(r, c).alignment, plain.cell(r, c).border = font, align, border
            apply(fast.cell(r, c), font=font, alignment=align, border=border)
    assert look(fast) == look(plain)


def test_opening_a_workbook_with_merges_matches_openpyxls_own_loader(tmp_path):
    import io

    from openpyxl.worksheet._reader import WorksheetReader
    from openpyxl.worksheet.cell_range import MultiCellRange
    from openpyxl.worksheet.merge import MergedCellRange

    def stock(self):
        if not self.parser.merged_cells:
            return
        ranges = []
        for cr in self.parser.merged_cells.mergeCell:
            merged = MergedCellRange(self.ws, cr.ref)
            self.ws._clean_merge_range(merged)
            ranges.append(merged)
        self.ws.merged_cells = MultiCellRange(ranges)

    wb, ws = sheet()
    for r1, c1, r2, c2 in BLOCKS:
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
    buf = io.BytesIO()
    wb.save(buf)
    fast = openpyxl.load_workbook(io.BytesIO(buf.getvalue())).active
    ours = WorksheetReader.bind_merged_cells
    try:
        WorksheetReader.bind_merged_cells = stock
        plain = openpyxl.load_workbook(io.BytesIO(buf.getvalue())).active
    finally:
        WorksheetReader.bind_merged_cells = ours
    assert ours.__module__ == "utils.fast_style" and look(fast) == look(plain)
