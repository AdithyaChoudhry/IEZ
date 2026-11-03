"""
io_summary.py - I/O SUMMARY sheet for the I/O List workbook (new; iEZ had no I/O summary before).

Counts the SAME filtered IODB rows that go into the I/O List, by SIGNAL I/O TYPE (AI / AO / DI / DO,
any other value as found, empty / "-" as NOT SET). When the IODB has an IS/NIS column the counts are also
split IS / NIS. Nothing is inferred: a missing signal-type column gives an explicit reason on the sheet.
Layout follows the Cable Summary sheet (Arial 12, thin borders, same header fill).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from utils.workbook_assembly import IO_SUMMARY_SHEET, drop_sheet

SUMMARY_TITLE = "I/O SUMMARY"
_TYPE_HEADERS = ("SIGNAL I/O TYPE", "SIGNAL IO TYPE", "SIGNAL TYPE", "I/O TYPE", "IO TYPE")
_ISNIS_HEADERS = ("IS/NIS TYPE", "IS/NIS", "IS NIS")
_STANDARD = ("AI", "AO", "DI", "DO")
_NOT_SET = "NOT SET"
_PLACEHOLDERS = {"", "-", "--", "NA", "N/A", "NAN", "NONE", "NIL", "TBA"}


def _norm(name) -> str:
    return re.sub(r"\s+", " ", str(name).replace("\n", " ")).strip().upper()


def _find(df: pd.DataFrame, headers) -> str | None:
    cols = {_norm(c): c for c in df.columns}
    for h in headers:
        if h in cols:
            return cols[h]
    return None


@dataclass
class IOSummaryResult:
    rows: list[dict] = field(default_factory=list)      # {"type", "total", "IS", "NIS", "NOT SET"}
    has_isnis: bool = False
    total_rows: int = 0
    type_column: str | None = None
    isnis_column: str | None = None
    reason: str = ""                                    # set when nothing could be counted


def _clean(v) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return _NOT_SET
    t = _norm(v)
    return _NOT_SET if t in _PLACEHOLDERS else t


def build_io_summary(df: pd.DataFrame) -> IOSummaryResult:
    """df = the filtered IODB rows (all columns), i.e. exactly the rows behind the I/O List."""
    res = IOSummaryResult(total_rows=len(df))
    type_col = _find(df, _TYPE_HEADERS)
    if type_col is None:
        res.reason = ("No SIGNAL I/O TYPE column was found in the IODB, so the signals could not be counted. "
                      f"Looked for: {', '.join(_TYPE_HEADERS)}.")
        return res
    res.type_column = str(type_col)
    isnis_col = _find(df, _ISNIS_HEADERS)
    res.has_isnis = isnis_col is not None
    res.isnis_column = str(isnis_col) if isnis_col is not None else None
    types = df[type_col].map(_clean)
    isnis = df[isnis_col].map(_clean) if isnis_col is not None else None
    others = sorted({t for t in types if t not in _STANDARD and t != _NOT_SET})
    for t in (*_STANDARD, *others, _NOT_SET):
        mask = types == t
        n = int(mask.sum())
        if n == 0 and t not in _STANDARD:
            continue
        row = {"type": t, "total": n, "IS": 0, "NIS": 0, "NOT SET": 0}
        if isnis is not None:
            sub = isnis[mask]
            row["IS"] = int((sub == "IS").sum())
            row["NIS"] = int((sub == "NIS").sum())
            row["NOT SET"] = n - row["IS"] - row["NIS"]
        res.rows.append(row)
    return res


def append_io_summary_sheet(wb, result: IOSummaryResult):
    """Add the I/O SUMMARY as the LAST sheet. A stale sheet of the same name in the template is replaced."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    drop_sheet(wb, IO_SUMMARY_SHEET)
    ws = wb.create_sheet(IO_SUMMARY_SHEET)              # create_sheet appends -> last
    thin = Side(border_style="thin", color="000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    font = Font(name="Arial", size=12)
    bold = Font(name="Arial", size=12, bold=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    heads = ["SL.NO", "SIGNAL I/O TYPE", "NO. OF SIGNALS"] + (["IS", "NIS", "IS/NIS NOT SET"] if result.has_isnis else [])
    last_col = len(heads)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws["A1"] = SUMMARY_TITLE
    ws["A1"].font, ws["A1"].alignment = Font(name="Arial", size=14, bold=True), center
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws["A2"] = f"Source: {result.total_rows} I/O List rows (after the selected filters)"
    ws["A2"].font, ws["A2"].alignment = Font(name="Arial", size=10, italic=True), center
    for col, head in enumerate(heads, 1):
        c = ws.cell(4, col, head)
        c.font, c.alignment, c.border = bold, center, border
        c.fill = PatternFill("solid", fgColor="CCFFFF")
    row = 5
    if result.rows:
        first = row
        for n, item in enumerate(result.rows, 1):
            values = [n, item["type"], item["total"]] + ([item["IS"], item["NIS"], item["NOT SET"]] if result.has_isnis else [])
            for col, value in enumerate(values, 1):
                c = ws.cell(row, col, value)
                c.font, c.alignment, c.border = font, center, border
            row += 1
        last = row - 1
        for col in range(1, last_col + 1):
            c = ws.cell(row, col)
            c.font, c.alignment, c.border = bold, center, border
        ws.cell(row, 2, "TOTAL")
        for col in range(3, last_col + 1):
            letter = ws.cell(row, col).column_letter
            ws.cell(row, col, f"=SUM({letter}{first}:{letter}{last})")
    else:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
        c = ws.cell(row, 1, result.reason or "No signals to count.")
        c.font, c.alignment = Font(name="Arial", size=12, italic=True), Alignment(horizontal="left", vertical="center", wrap_text=True)
        ws.row_dimensions[row].height = 48
    for col, width in zip("ABCDEF", (10, 24, 18, 12, 12, 18)):
        ws.column_dimensions[col].width = width
    ws.page_setup.paperSize = 9
    return ws
