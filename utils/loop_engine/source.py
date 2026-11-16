"""
I/O Assignment reader. Every column is identified by its FIELD CODE (the code row of the IO_ASSIGNMENT sheet) - never by position.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import openpyxl

# Codes that are computed by the I/O Assignment workbook itself (not engineering inputs).
COMPUTED_CODES = {"SNO", "RESULT"}
COMPUTED_PREFIXES = ("DUP_", "MISS_")
CORE_CODES = {"LOOP_NAME", "TAG", "IO_TYPE", "LOOP_TYPE", "SPD_ARR", "TERM_ARR"}
SHEET_NAME = "IO_ASSIGNMENT"
SPARE_WORDS = {"SPARE", "SPR", "RESERVED"}


@dataclass
class SourceRow:
    row: int                                # worksheet row number
    values: dict[str, Any]                  # FIELD CODE -> value (non-blank only)

    def get(self, code: str, default: Any = None) -> Any:
        v = self.values.get(code)
        return default if v is None else v

    def text(self, code: str) -> str:
        v = self.values.get(code)
        if v is None:
            return ""
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return re.sub(r"\s+", " ", str(v)).strip()

    def upper(self, code: str) -> str:
        return self.text(code).upper()

    @property
    def is_spare(self) -> bool:
        return self.upper("STATUS") in SPARE_WORDS or self.upper("TAG") in SPARE_WORDS


@dataclass
class SourceData:
    sheet: str
    header_row: int
    codes: list[str]
    rows: list[SourceRow]
    spare_rows: list[SourceRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _clean(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        return v if v else None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _is_code(v: Any) -> bool:
    return isinstance(v, str) and bool(re.fullmatch(r"[A-Z][A-Z0-9_]{1,24}", v.strip()))


def read_assignment(data: bytes, known_codes: Optional[set[str]] = None) -> SourceData:
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    names = [SHEET_NAME] + [n for n in wb.sheetnames if n != SHEET_NAME]
    for name in names:
        if name not in wb.sheetnames:
            continue
        ws = wb[name]
        header_row, codes_by_col = 0, {}
        for r_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=30, values_only=True), start=1):
            hit = {i: str(v).strip() for i, v in enumerate(row) if _is_code(v)}
            if CORE_CODES <= set(hit.values()):
                header_row, codes_by_col = r_idx, hit
                break
        if not header_row:
            continue
        # data starts after the code row and the human heading row(s): first row where a core field holds a non-heading value
        codes = [codes_by_col.get(i) for i in range(max(codes_by_col) + 1)]
        input_cols = {i: c for i, c in codes_by_col.items() if c not in COMPUTED_CODES and not c.startswith(COMPUTED_PREFIXES)}
        rows: list[SourceRow] = []
        spares: list[SourceRow] = []
        heading_skipped = False
        for r_idx, row in enumerate(ws.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
            vals = {c: _clean(row[i]) for i, c in input_cols.items() if i < len(row)}
            vals = {c: v for c, v in vals.items() if v is not None}
            if not vals:
                continue
            if not heading_skipped:
                # the line under the code row is the human column heading (e.g. TAG -> 'TAG NUMBER'): skip it once
                heading_skipped = True
                if vals.get("LOOP_NAME") in ("LOOP NO.", "LOOP NAME") or vals.get("TAG") in ("TAG NUMBER", "TAG NO."):
                    continue
            sr = SourceRow(r_idx, vals)
            key = {c for c in ("TAG", "LOOP_NAME", "IO_TYPE", "MODULE_TAG", "CHANNEL", "STATUS", "SYS_CAB") if c in vals}
            if not key:
                continue
            (spares if sr.is_spare and not sr.text("LOOP_NAME") else rows).append(sr)
        warn = []
        if known_codes:
            unknown = sorted({c for c in codes_by_col.values() if c not in known_codes and c not in COMPUTED_CODES and not c.startswith(COMPUTED_PREFIXES)})
            if unknown:
                warn.append(f"Field codes not defined in the I/O Assignment standard (read as-is): {', '.join(unknown)}")
        return SourceData(name, header_row, [c for c in codes if c], rows, spares, warn)
    raise ValueError("No I/O Assignment found: the workbook needs an IO_ASSIGNMENT sheet whose header row carries the FIELD CODES (LOOP_NAME, TAG, IO_TYPE, LOOP_TYPE, SPD_ARR, TERM_ARR ...).")
