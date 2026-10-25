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

# Canonical IODB fields -> accepted header spellings. Headers are compared after normalisation
# (upper case, line breaks / punctuation -> single spaces), so "MAIN CABLE LENGTH(Mtrs)",
# "MAIN CABLE LENGTH (MTRS)" and "Main Cable Length\n(Mtrs)" are the same field. Length headers
# may also carry a trailing unit word (see _UNIT_TOKENS) but nothing else - no fuzzy matching.
CANONICAL_FIELDS: dict[str, dict] = {
    "INSTRUMENT_TO_JB_CABLE_TYPE": {"aliases": ["INSTRUMENT TO JB CABLE TYPE"], "unit_suffix": False},
    "BRANCH_CABLE_LENGTH":         {"aliases": ["BRANCH CABLE LENGTH"],         "unit_suffix": True},
    "MAIN_CABLE_TYPE":             {"aliases": ["MAIN CABLE TYPE"],             "unit_suffix": False},
    "MAIN_CABLE_LENGTH":           {"aliases": ["MAIN CABLE LENGTH"],           "unit_suffix": True},
}
_UNIT_TOKENS = {"M", "MT", "MTR", "MTRS", "MTS", "METER", "METERS", "METRE", "METRES", "IN", "MM"}
# (type field, length field, label) - the two cable runs that contribute quantities
_SOURCES = (
    ("INSTRUMENT_TO_JB_CABLE_TYPE", "BRANCH_CABLE_LENGTH", "branch cable"),
    ("MAIN_CABLE_TYPE", "MAIN_CABLE_LENGTH", "main cable"),
)
_PLACEHOLDERS = {"", "-", "--", "NA", "N/A", "NIL", "NONE", "TBA", "NAN", "NULL"}
_MAX_DETAILS = 25
_HEADER_SCAN_ROWS = 15


@dataclass
class CableSummaryResult:
    rows: list[dict] = field(default_factory=list)            # [{"cable_description", "units", "quantity"}]
    warnings: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)          # per-record problems (capped)
    counts: dict[str, int] = field(default_factory=dict)
    missing_columns: list[str] = field(default_factory=list)
    resolved: dict[str, str] = field(default_factory=dict)    # canonical field -> actual IODB header
    source: dict = field(default_factory=dict)                # {"sheet", "header_row", "columns": {field: letter}}
    typed: dict[str, int] = field(default_factory=dict)       # cable-type entries per run (before length checks)
    formula_hint: str = ""

    def diagnostics(self) -> list[str]:
        """Plain-language account of what the parser found (logged on every generation)."""
        out = []
        if self.source.get("sheet"):
            out.append(f"[Cable Summary] IODB sheet: {self.source['sheet']}; header row: {self.source.get('header_row')}")
        for name in CANONICAL_FIELDS:
            header = self.resolved.get(name)
            letter = self.source.get("columns", {}).get(name)
            out.append(f"[Cable Summary] {name} -> " + (f"'{header}'" + (f" (column {letter})" if letter else "") if header else "NOT FOUND"))
        for _, _, label in _SOURCES:
            out.append(f"[Cable Summary] {label}: {self.typed.get(label, 0)} entries with a cable type, "
                       f"{self.counts.get(label, 0)} with a valid length")
        return out

    def empty_reason(self) -> str:
        """Why there is nothing to total - specific, never a generic 'no data' claim."""
        if self.missing_columns and not any(self.typed.values()):
            return ("Cable columns not found in the IODB: " + ", ".join(self.missing_columns) +
                    ". Required: INSTRUMENT TO JB CABLE TYPE, BRANCH CABLE LENGTH, MAIN CABLE TYPE, MAIN CABLE LENGTH.")
        typed = sum(self.typed.values())
        if typed == 0:
            return ("No cable types found: INSTRUMENT TO JB CABLE TYPE and MAIN CABLE TYPE are blank, '-' or TBA "
                    "for every record.")
        blank, invalid = self.counts.get("blank_length", 0), self.counts.get("invalid_length", 0)
        text = (f"{typed} cable entr{'y' if typed == 1 else 'ies'} have a cable type "
                f"(branch {self.typed.get('branch cable', 0)}, main {self.typed.get('main cable', 0)}) but none has a usable "
                f"numeric length ({blank} blank / TBA / '-', {invalid} non-numeric). "
                "Enter the cable lengths in BRANCH CABLE LENGTH and MAIN CABLE LENGTH(Mtrs) in the IODB.")
        return text + (" " + self.formula_hint if self.formula_hint else "")

    def log_lines(self) -> list[str]:
        return [*self.diagnostics(), *self.warnings, *self.details]


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


def resolve_cable_fields(columns) -> dict[str, Optional[str]]:
    """Canonical field -> actual header (None if absent). Order/position of columns is irrelevant."""
    norm_to_actual: dict[str, str] = {}
    for col in columns:
        norm_to_actual.setdefault(_norm_col(col), col)
    out: dict[str, Optional[str]] = {}
    for name, spec in CANONICAL_FIELDS.items():
        found = None
        for alias in spec["aliases"]:
            key = _norm_col(alias)
            if key in norm_to_actual:
                found = norm_to_actual[key]
                break
            if spec["unit_suffix"]:
                for norm, actual in norm_to_actual.items():
                    if norm.startswith(key + " ") and all(t in _UNIT_TOKENS for t in norm[len(key):].split()):
                        found = actual
                        break
            if found:
                break
        out[name] = found
    return out


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
    cols = resolve_cable_fields(df.columns)
    result.resolved = {k: v for k, v in cols.items() if v}
    totals: dict[str, Decimal] = {}
    spelled: dict[str, str] = {}
    counts = {"branch cable": 0, "main cable": 0, "blank_length": 0, "invalid_length": 0, "zero_length": 0}
    index_to_row = {pos: int(idx) + 2 if isinstance(idx, (int, float)) else pos + 2
                    for pos, idx in enumerate(df.index)}
    tag_values = df[tag_column].tolist() if tag_column and tag_column in df.columns else None

    for type_col, len_col, label in _SOURCES:
        t_name, l_name = cols[type_col], cols[len_col]
        if t_name is None or l_name is None:
            missing = [c.replace("_", " ") for c, n in ((type_col, t_name), (len_col, l_name)) if n is None]
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
            result.typed[label] = result.typed.get(label, 0) + 1
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


# ── locating the data in the uploaded workbook ───────────────────────────────
def inspect_workbook(iodb_bytes: bytes) -> list[dict]:
    """
    Every sheet that has a header row (within the first rows) containing a cable-type field,
    found by header NAME - independent of sheet name, header row number or column position.
    [{"sheet", "header_row" (1-based), "headers": {field: actual header}, "columns": {field: letter}}]
    """
    import io
    import openpyxl
    from openpyxl.utils import get_column_letter

    wb = openpyxl.load_workbook(io.BytesIO(iodb_bytes), read_only=True, data_only=True)
    found = []
    try:
        for ws in wb.worksheets:
            for i, row in enumerate(ws.iter_rows(min_row=1, max_row=_HEADER_SCAN_ROWS, max_col=300, values_only=True)):
                headers = [h for h in row if h not in (None, "")]
                res = resolve_cable_fields(headers)
                if res["INSTRUMENT_TO_JB_CABLE_TYPE"] or res["MAIN_CABLE_TYPE"]:
                    letters = {}
                    for name, actual in res.items():
                        if actual is not None:
                            letters[name] = get_column_letter(next(j for j, h in enumerate(row) if h == actual) + 1)
                    by_header = {str(h): get_column_letter(j + 1) for j, h in enumerate(row) if h not in (None, "")}
                    found.append({"sheet": ws.title, "header_row": i + 1, "headers": res, "columns": letters,
                                  "letters_by_header": by_header})
                    break
    finally:
        wb.close()
    return found


def locate_cable_source(df, iodb_bytes: bytes | None = None, tag_column: str | None = None):
    """
    (DataFrame holding the cable columns, info about where it came from).

    The cable fields are located in the workbook by header NAME (any sheet, any header row) and
    only those columns (+ the tag column) are read, keeping real Excel row numbers so log lines
    can point at the right row. Falls back to the frame the Cable Schedule already read.
    Never raises.
    """
    if not iodb_bytes:
        return df, None
    try:
        candidates = inspect_workbook(iodb_bytes)
    except Exception:
        return df, None

    def complete(res):
        return any(res[t] and res[ln] for t, ln, _ in _SOURCES)

    own = resolve_cable_fields(df.columns)
    if complete(own):                              # prefer the sheet the schedule itself used
        ordered = sorted(candidates, key=lambda c: 0 if all(v in set(df.columns) for v in c["headers"].values() if v) else 1)
    else:
        ordered = candidates
    for cand in ordered:
        if not complete(cand["headers"]):
            continue
        letters = [cand["columns"][f] for f in cand["columns"]]
        if tag_column:
            tag_letter = next((letter for h, letter in cand["letters_by_header"].items()
                               if _norm_col(h) == _norm_col(tag_column)), None)
            if tag_letter and tag_letter not in letters:
                letters.append(tag_letter)
        try:
            import io
            import pandas as pd
            frame = pd.read_excel(io.BytesIO(iodb_bytes), sheet_name=cand["sheet"], header=cand["header_row"] - 1,
                                  usecols=",".join(letters))
            frame = frame.dropna(how="all")
            frame.index = frame.index + (cand["header_row"] - 1)     # index + 2 == Excel row number
            return frame, cand
        except Exception:
            continue
    return df, (ordered[0] if ordered else None)


def formula_hint_for(iodb_bytes: bytes, info: dict) -> str:
    """If the cable-length cells are formulas with no stored result, say so (they read as empty)."""
    import io
    import openpyxl

    letters = [info["columns"].get(f) for f in ("BRANCH_CABLE_LENGTH", "MAIN_CABLE_LENGTH")]
    letters = [x for x in letters if x]
    if not letters:
        return ""
    try:
        formulas = openpyxl.load_workbook(io.BytesIO(iodb_bytes), read_only=True, data_only=False)[info["sheet"]]
        values = openpyxl.load_workbook(io.BytesIO(iodb_bytes), read_only=True, data_only=True)[info["sheet"]]
        lost = 0
        for letter in letters:
            f_cells = [c[0].value for c in formulas.iter_rows(min_row=info["header_row"] + 1, min_col=openpyxl.utils.column_index_from_string(letter), max_col=openpyxl.utils.column_index_from_string(letter))]
            v_cells = [c[0].value for c in values.iter_rows(min_row=info["header_row"] + 1, min_col=openpyxl.utils.column_index_from_string(letter), max_col=openpyxl.utils.column_index_from_string(letter))]
            lost += sum(1 for f, v in zip(f_cells, v_cells) if isinstance(f, str) and f.startswith("=") and v is None)
        if lost:
            return (f"{lost} length cell(s) contain formulas with no stored result, so they read as empty. "
                    "Open the IODB in Excel, save it, and upload it again.")
    except Exception:
        pass
    return ""


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
        _write_empty_reason(ws, row, result, next_styles[1], row_height)
        row += 1

    last_used = row - 1                                   # last row of the table (TOTAL or the empty-data line)
    if result.rows and _write_note(ws, row + 1, result, next_styles[1]):
        last_used = row + 1
    ws.print_area = f"A1:D{max(last_used, first_data)}"
    _move_to_end(wb, ws)
    return ws


def _write_empty_reason(ws, row: int, result: CableSummaryResult, style: dict, row_height: float) -> None:
    """Explain WHY there is nothing to total (merged, wrapped across the table width)."""
    from openpyxl.styles import Alignment, Font

    text = result.empty_reason()
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    cell = ws.cell(row, 2, text)
    if "border" in style:
        _apply(cell, style)
    base = style["font"]
    cell.font = Font(name=base.name, size=base.sz, italic=True)
    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = max(row_height, 15.75 * (1 + len(text) // 85))


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
        _write_empty_reason(ws, row, result, {"font": font, "alignment": center}, 15.75)
        row += 1
    for col, width in zip("ABCD", (10, 48, 14, 16)):
        ws.column_dimensions[col].width = width
    ws.page_setup.paperSize = 9
    if result.rows:
        _write_note(ws, row + 1, result, {"font": font, "alignment": center})
    return ws
