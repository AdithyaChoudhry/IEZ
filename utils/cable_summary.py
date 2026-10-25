"""
cable_summary.py - CABLE QUANTITIES summary for the Cable Schedule workbook.

For every IODB record two cable runs contribute quantities:

    INSTRUMENT TO JB CABLE TYPE  + BRANCH CABLE LENGTH
    MAIN CABLE TYPE              + MAIN CABLE LENGTH(MTRS)

Identical cable descriptions (across both sources and across rows) are grouped into
one row with the summed length in METERS. The result is written to the LAST worksheet,
named "CABLE SUMMARY", reusing the template's own summary sheet when it has one.

Matching is EXACT after safe whitespace normalisation only - no fuzzy matching.
Look-alike descriptions that are not identical are reported, never merged.
"""
from __future__ import annotations

import math
import re
from copy import copy
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

CABLE_SUMMARY_SHEET = "CABLE SUMMARY"
SUMMARY_TITLE = "CABLE QUANTITIES"
UNITS = "METERS"

# Source columns: (cable-type column, cable-length column) pairs, in the order they are read.
_SOURCES = (
    ("INSTRUMENT TO JB CABLE TYPE", "BRANCH CABLE LENGTH", "branch cable"),
    ("MAIN CABLE TYPE", "MAIN CABLE LENGTH", "main cable"),
)
_PLACEHOLDERS = {"", "-", "--", "NA", "N/A", "NIL", "NONE", "TBA", "NAN", "NULL"}
_MAX_DETAILS = 25


@dataclass
class CableSummaryResult:
    rows: list[dict] = field(default_factory=list)            # [{"cable_description", "units", "quantity"}]
    warnings: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)          # per-record problems (capped)
    counts: dict[str, int] = field(default_factory=dict)
    missing_columns: list[str] = field(default_factory=list)

    def log_lines(self) -> list[str]:
        return [*self.warnings, *self.details]


# ── helpers ──────────────────────────────────────────────────────────────────
def _norm_col(name: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(name).upper()).strip()


def normalize_cable_description(value: Any) -> str:
    """Safe normalisation only: trim and collapse whitespace. Case and characters are kept."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = re.sub(r"\s+", " ", str(value).replace(" ", " ")).strip()
    return "" if text.upper() in _PLACEHOLDERS else text


def parse_length(value: Any) -> tuple[Optional[Decimal], str]:
    """
    Returns (length, status); status is "ok", "blank" or "invalid".
    Numbers and numeric strings are accepted. Text such as "27 m" is flagged, not guessed.
    """
    if value is None:
        return None, "blank"
    if isinstance(value, bool):
        return None, "invalid"
    if isinstance(value, float) and math.isnan(value):
        return None, "blank"
    if isinstance(value, str):
        text = value.replace(" ", " ").strip()
        if text.upper() in _PLACEHOLDERS:
            return None, "blank"
        try:
            number = Decimal(text)
        except InvalidOperation:
            return None, "invalid"
    else:
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            return None, "invalid"
    if not number.is_finite() or number < 0:
        return None, "invalid"
    return number, "ok"


def _natural_key(text: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def _find_columns(df) -> dict[str, Optional[str]]:
    """Locate the four source columns by normalised header name (tolerates spacing/punctuation)."""
    by_norm = {_norm_col(c): c for c in df.columns}
    found: dict[str, Optional[str]] = {}
    for type_col, len_col, _ in _SOURCES:
        found[type_col] = by_norm.get(_norm_col(type_col))
        found[len_col] = by_norm.get(_norm_col(len_col)) or next(
            (orig for norm, orig in by_norm.items() if norm.startswith(_norm_col(len_col))), None)
    return found


def _quantity(total: Decimal) -> int | float:
    return int(total) if total == total.to_integral_value() else float(total)


# ── calculation ──────────────────────────────────────────────────────────────
def build_cable_summary(df, tag_column: str | None = None) -> CableSummaryResult:
    """
    Cable quantity per cable description from an IODB DataFrame (all rows of that IODB).

    Each source field is counted once: branch type uses only the branch length and main
    type uses only the main length. Blank cable types or lengths are skipped (never
    treated as 0); non-numeric lengths are skipped and reported.
    """
    result = CableSummaryResult()
    cols = _find_columns(df)
    totals: dict[str, Decimal] = {}
    spelled: dict[str, str] = {}
    counts = {"branch cable": 0, "main cable": 0, "blank_length": 0, "invalid_length": 0, "zero_length": 0}
    index_to_row = {pos: int(idx) + 2 if isinstance(idx, (int, float)) else pos + 2
                    for pos, idx in enumerate(df.index)}
    tag_values = df[tag_column].tolist() if tag_column and tag_column in df.columns else None

    for type_col, len_col, label in _SOURCES:
        t_name, l_name = cols[type_col], cols[len_col]
        if t_name is None or l_name is None:
            missing = [c for c, n in ((type_col, t_name), (len_col, l_name)) if n is None]
            result.missing_columns += missing
            result.warnings.append(
                f"[Cable Summary] {label} skipped - column(s) not found in the IODB: {', '.join(missing)}.")
            continue
        types = df[t_name].tolist()
        lengths = df[l_name].tolist()
        for pos, (raw_type, raw_len) in enumerate(zip(types, lengths)):
            description = normalize_cable_description(raw_type)
            if not description:
                continue                                   # no cable of this kind on this record
            length, status = parse_length(raw_len)
            where = f"IODB row {index_to_row[pos]}" + (f", tag {tag_values[pos]}" if tag_values else "")
            if status == "blank":
                counts["blank_length"] += 1
                if len(result.details) < _MAX_DETAILS:
                    result.details.append(f"[Cable Summary] {where}: {label} '{description}' has no length - not counted.")
                continue
            if status == "invalid":
                counts["invalid_length"] += 1
                if len(result.details) < _MAX_DETAILS:
                    result.details.append(
                        f"[Cable Summary] {where}: {label} '{description}' has a non-numeric length "
                        f"'{raw_len}' - not counted.")
                continue
            if length == 0:
                counts["zero_length"] += 1
                continue
            key = description
            spelled.setdefault(key, description)
            totals[key] = totals.get(key, Decimal(0)) + length
            counts[label] += 1

    # Look-alike descriptions are NOT merged - only reported.
    looks_alike: dict[str, list[str]] = {}
    for key in totals:
        looks_alike.setdefault(re.sub(r"[\s]+", "", key).lower(), []).append(key)
    for group in looks_alike.values():
        if len(group) > 1:
            result.warnings.append("[Cable Summary] These descriptions look alike but are not identical, "
                                   f"so they were kept separate: {' | '.join(sorted(group))}.")
    if counts["blank_length"]:
        n = counts["blank_length"]
        result.warnings.append(f"[Cable Summary] {n} cable entr{'y' if n == 1 else 'ies'} "
                               f"had a cable type but no length (not counted).")
    if counts["invalid_length"]:
        n = counts["invalid_length"]
        result.warnings.append(f"[Cable Summary] {n} cable entr{'y' if n == 1 else 'ies'} "
                               f"had a non-numeric length (not counted).")

    result.rows = [{"cable_description": spelled[k], "units": UNITS, "quantity": _quantity(totals[k])}
                   for k in sorted(totals, key=_natural_key)]
    result.counts = counts
    return result


# ── worksheet ────────────────────────────────────────────────────────────────
def _find_sheet(wb):
    for ws in wb.worksheets:
        if ws.title.strip().upper() == CABLE_SUMMARY_SHEET:
            return ws
    return None


def _style_of(cell) -> dict:
    return {"font": copy(cell.font), "border": copy(cell.border), "fill": copy(cell.fill),
            "alignment": copy(cell.alignment), "number_format": cell.number_format,
            "protection": copy(cell.protection)}


def _apply(cell, style: dict) -> None:
    cell.font, cell.border, cell.fill = copy(style["font"]), copy(style["border"]), copy(style["fill"])
    cell.alignment, cell.number_format = copy(style["alignment"]), style["number_format"]
    cell.protection = copy(style["protection"])


def append_cable_summary_sheet(wb, result: CableSummaryResult):
    """
    Put the summary on the workbook's LAST sheet, named "CABLE SUMMARY".

    If the template already contains a CABLE SUMMARY sheet it is reused (banner, project
    block, headers, fonts, borders, its TOTAL row) and moved to the end; otherwise a new
    sheet with the same layout is appended. No other sheet is modified or reordered.
    """
    ws = _find_sheet(wb)
    first_data = 8
    if ws is None:
        return _append_new_sheet(wb, result)

    ws.sheet_state = "visible"
    # Capture the template's own row styles BEFORE clearing.
    first_styles = [_style_of(ws.cell(first_data, c)) for c in range(1, 5)]
    next_styles = [_style_of(ws.cell(first_data + 1, c)) for c in range(1, 5)]
    total_styles = [_style_of(ws.cell(14, c)) for c in range(1, 5)]
    total_font_bold = copy(ws.cell(14, 3).font)
    total_formula_style = _style_of(ws.cell(14, 4))
    row_height = ws.row_dimensions[first_data + 1].height or 15.75

    ws["A6"].value = SUMMARY_TITLE                      # template title is project-specific / stale
    ws.delete_rows(first_data, max(ws.max_row - first_data + 1, 1))
    for r in [k for k in ws.row_dimensions if k >= first_data]:
        del ws.row_dimensions[r]

    row = first_data
    for n, item in enumerate(result.rows, 1):
        styles = first_styles if n == 1 else next_styles
        values = (n, item["cable_description"], item["units"], item["quantity"])
        for col, (value, style) in enumerate(zip(values, styles), 1):
            cell = ws.cell(row, col, value)
            _apply(cell, style)
        ws.row_dimensions[row].height = row_height
        row += 1

    last_data = row - 1
    if result.rows:
        for col, style in enumerate(total_styles, 1):
            _apply(ws.cell(row, col), style)
        ws.cell(row, 3, "TOTAL").font = total_font_bold
        total = ws.cell(row, 4, f"=ROUNDUP(SUM(D{first_data}:D{last_data}),0)")
        _apply(total, total_formula_style)
        ws.row_dimensions[row].height = row_height
        row += 1
    else:
        ws.cell(row, 2, "No cable type / length data found in the IODB "
                        "(INSTRUMENT TO JB CABLE TYPE, MAIN CABLE TYPE).")
        _apply(ws.cell(row, 2), next_styles[1])
        row += 1

    last_used = row - 1                                   # last row of the table (TOTAL or the empty-data line)
    if _write_note(ws, row + 1, result, next_styles[1]):
        last_used = row + 1
    ws.print_area = f"A1:D{max(last_used, first_data)}"
    _move_to_end(wb, ws)
    return ws


def _write_note(ws, row: int, result: CableSummaryResult, style: dict) -> bool:
    from openpyxl.styles import Alignment, Font

    issues = [w for w in result.warnings if "not counted" in w or "not found" in w or "look alike" in w]
    if not issues:
        return False
    cell = ws.cell(row, 2, "NOTE: " + " ".join(i.replace("[Cable Summary] ", "") for i in issues))
    base = style["font"]
    cell.font = Font(name=base.name, size=base.sz, italic=True)
    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=False)
    return True


def _move_to_end(wb, ws) -> None:
    offset = len(wb.sheetnames) - 1 - wb.sheetnames.index(ws.title)
    if offset:
        wb.move_sheet(ws, offset=offset)


def _append_new_sheet(wb, result: CableSummaryResult):
    """No summary sheet in the template: create one at the end using the schedule's look."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    ws = wb.create_sheet(CABLE_SUMMARY_SHEET)          # create_sheet appends -> last
    thin = Side(border_style="thin", color="000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    font = Font(name="Arial", size=12)
    bold = Font(name="Arial", size=12, bold=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.merge_cells("A1:D1")
    ws["A1"] = SUMMARY_TITLE
    ws["A1"].font, ws["A1"].alignment = Font(name="Arial", size=14, bold=True), center
    for col, head in enumerate(("SL.NO", "CABLE DESCRIPTION", "UNITS", "QUANTITY"), 1):
        c = ws.cell(3, col, head)
        c.font, c.alignment, c.border = bold, center, border
        c.fill = PatternFill("solid", fgColor="CCFFFF")
    row = 4
    for n, item in enumerate(result.rows, 1):
        for col, value in enumerate((n, item["cable_description"], item["units"], item["quantity"]), 1):
            c = ws.cell(row, col, value)
            c.font, c.alignment, c.border = font, center, border
        row += 1
    if not result.rows:
        ws.cell(row, 2, "No cable type / length data found in the IODB.").font = font
        row += 1
    for col, width in zip("ABCD", (10, 48, 14, 16)):
        ws.column_dimensions[col].width = width
    ws.page_setup.paperSize = 9
    _write_note(ws, row + 1, result, {"font": font, "alignment": center})
    return ws
