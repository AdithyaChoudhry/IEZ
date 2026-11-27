"""
Applying one and the same openpyxl style object to very many cells.

`cell.font = f` looks `f` up in the workbook's style list every time, and that look-up compares the style field by field -
for a generated schedule with hundreds of thousands of assignments it is most of the generation time. `apply` looks each
style object up once per workbook and afterwards only writes its number into the cell; the saved file is the same.
"""
from openpyxl.cell.cell import MergedCell
from openpyxl.styles.borders import Border
from openpyxl.styles.cell_style import StyleArray
from openpyxl.utils import get_column_letter
from openpyxl.worksheet._reader import WorksheetReader
from openpyxl.worksheet.cell_range import MultiCellRange
from openpyxl.worksheet.merge import MergedCellRange

_ATTRS = {"font": ("_fonts", "fontId"), "alignment": ("_alignments", "alignmentId"), "border": ("_borders", "borderId")}


def apply(cell, **styles) -> None:
    """apply(cell, font=F, alignment=A, border=B): same result as assigning each attribute. The objects must not change."""
    wb = cell.parent.parent
    known = wb.__dict__.get("_iez_style_ids")
    if known is None:
        known = wb.__dict__["_iez_style_ids"] = {}
    for name, value in styles.items():
        key = (name, id(value))
        hit = known.get(key)
        if hit is None:
            collection, attr = _ATTRS[name]
            setattr(cell, name, value)                                   # the normal assignment, once
            known[key] = (value, getattr(cell._style, attr))            # keeping `value` keeps its id() unique
        else:
            if cell._style is None:
                cell._style = StyleArray()
            setattr(cell._style, _ATTRS[name][1], hit[1])


class _MergedRange(MergedCellRange):
    """openpyxl's merged range with the same borders and protection, each distinct border combination worked out once."""

    def _add_border(self, cell, other_id: int, names: tuple) -> None:
        """cell.border += Border(<names> of the border `other_id`)"""
        wb = self.ws.parent
        sums = wb.__dict__.setdefault("_iez_border_sums", {})
        if cell._style is None:
            cell._style = StyleArray()
        key = (cell._style.borderId, other_id, names)
        total = sums.get(key)
        if total is None:
            other = wb._borders[other_id]
            total = sums[key] = wb._borders.add(wb._borders[key[0]] + Border(**{n: getattr(other, n) for n in names}))
        cell._style.borderId = total

    def _get_borders(self):
        self.start_cell = self.ws._cells.get((self.min_row, self.min_col))
        if self.start_cell is None:
            self.start_cell = self.ws.cell(row=self.min_row, column=self.min_col)
        end_cell = self.ws._cells.get((self.max_row, self.max_col))
        if end_cell is not None:
            end_id = end_cell._style.borderId if end_cell._style is not None else 0
            self._add_border(self.start_cell, end_id, ("right", "bottom"))

    def _cell_at(self, coord):
        cell = self.ws._cells.get(coord)
        if cell is None:
            cell = self.ws._cells[coord] = MergedCell(self.ws, row=coord[0], column=coord[1])
        if cell._style is None:
            cell._style = StyleArray()
        return cell

    def format(self):
        start = self.start_cell
        if start._style is None:
            start._style = StyleArray()
        start_id = start._style.borderId
        for name in ("top", "left", "right", "bottom"):
            side = getattr(self.ws.parent._borders[start_id], name)
            if side and side.style is None:
                continue
            for coord in getattr(self, name):
                self._add_border(self._cell_at(coord), start_id, (name,))
        protection_id = start._style.protectionId
        for coord in self.cells:
            self._cell_at(coord)._style.protectionId = protection_id


def merge_block(ws, r1: int, c1: int, r2: int, c2: int) -> None:
    """ws.merge_cells for a block known not to overlap any existing merge (openpyxl's own overlap scan makes many merges
    quadratic, and it compares border objects for every cell of every merge). The saved sheet is the same."""
    merged = _MergedRange(ws, f"{get_column_letter(c1)}{r1}:{get_column_letter(c2)}{r2}")
    ws.merged_cells.ranges.add(merged)
    ws._clean_merge_range(merged)


# ── opening workbooks ───────────────────────────────────────────────────────────────────────────────────────────
# openpyxl rebuilds the borders of every merged range while it opens a file, comparing border objects cell by cell: a
# generated schedule with tens of thousands of merges takes many seconds per open (and the cover step opens it four times).
def _bind_merged_cells(self):
    """openpyxl's WorksheetReader.bind_merged_cells with the range class above - the loaded sheet is the same."""
    if not self.parser.merged_cells:
        return
    ranges = []
    for cr in self.parser.merged_cells.mergeCell:
        merged = _MergedRange(self.ws, cr.ref)
        self.ws._clean_merge_range(merged)
        ranges.append(merged)
    self.ws.merged_cells = MultiCellRange(ranges)


if hasattr(WorksheetReader, "bind_merged_cells"):
    WorksheetReader.bind_merged_cells = _bind_merged_cells
