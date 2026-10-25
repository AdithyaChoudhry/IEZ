"""
list_defaults.py - DEFAULT column selection and DEFAULT filters for the Instrument List
and I/O List generators.

These are only an initial state computed when an IODB is analysed. The user can add or
remove columns and change/clear filters; generation uses the user's final selection.
The IODB itself is never modified.

Matching rules (deliberately narrow - no fuzzy matching):
  * column names: leading/trailing spaces, repeated spaces / line breaks and capitalisation
    are ignored; the ORIGINAL header text is what gets selected and written.
  * filter values: trimmed and compared case-insensitively; the ORIGINAL values stay as they are.
"""
from __future__ import annotations

import re
from typing import Any

# A filter option that stands for empty cells (so blanks can be included/excluded explicitly).
BLANK_TOKEN = "(blank)"

LIST_TYPES = ("instrument_list", "io_list")

DEFAULT_COLUMNS: dict[str, list[str]] = {
    "instrument_list": [
        "S.NO", "REV NUMBER", "LOCATION", "AREA", "AREA CLASSIFICATION", "SCOPE OF SUPPLY",
        "TAG NO", "LOOP NUMBER", "EQUIPMENT DESCRIPTION", "P&ID NO.", "SIGNAL DESCRIPTION",
        "INSTRUMENT TYPE NAME", "INSTRUMENT MEASURING TYPE", "SERVICE", "LINE", "LINE MOC",
        "EQUIPMENT NO", "SYSTEM", "SUB SYSTEM", "SIGNAL I/O TYPE", "POWER SUPPLY",
        "2 WIRE / 4 WIRE", "FIELD POWER LOAD", "VENDOR PACKAGE", "IS/NIS TYPE",
        "PROCESS RANGE", "PROCESS UNIT OF MEASUREMENT", "CALIBRATION RANGE", "CALIBRATION UNIT",
        "INST RANGE", "INST RANGE UNIT", "HART", "REMARKS",
    ],
    "io_list": [
        "S.NO", "REV NUMBER", "LOCATION", "AREA", "AREA CLASSIFICATION", "SCOPE OF SUPPLY",
        "TAG NO", "LOOP NUMBER", "EQUIPMENT DESCRIPTION", "P&ID NO.", "SIGNAL DESCRIPTION",
        "INSTRUMENT TYPE NAME", "INSTRUMENT MEASURING TYPE", "SERVICE", "LINE", "EQUIPMENT NO",
        "SYSTEM", "SUB SYSTEM", "SIGNAL I/O TYPE", "POWER SUPPLY", "PROCESS RANGE",
        "PROCESS UNIT OF MEASUREMENT", "SET POINT FOR ALARM LOW LOW", "SET POINT FOR ALARM LOW",
        "SET POINT FOR ALARM HIGH", "SET POINT FOR ALARM HIGH HIGH", "ALARM UOM", "HART",
        "REDUNDANT I O", "CONTACT DETAILS", "REMARKS",
    ],
}

# mode "include_only": exactly these values are selected (everything else is deselected).
# mode "exclude":      every value is selected EXCEPT these (blank cells stay included).
DEFAULT_FILTERS: dict[str, list[dict[str, Any]]] = {
    "instrument_list": [
        {"column": "SIGNAL I/O TYPE", "mode": "include_only", "values": ["AI", "AO", "DI", "DO"]},
        {"column": "SUB SYSTEM", "mode": "exclude", "values": ["MCC", "VFD", "VENDOR PLC"]},
    ],
    "io_list": [
        {"column": "SIGNAL I/O TYPE", "mode": "exclude", "values": ["-"]},
    ],
}


def norm_key(value: Any) -> str:
    """Safe comparison key: collapse whitespace/line breaks, trim, case-insensitive."""
    return re.sub(r"\s+", " ", str(value).replace(" ", " ")).strip().casefold()


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and value != value) or str(value).strip() == ""


def _column_index(columns: list[str]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for col in columns:
        index.setdefault(norm_key(col), []).append(col)
    return index


def match_columns(wanted: list[str], columns: list[str]) -> tuple[list[str], list[str], list[str]]:
    """(matched actual headers in the wanted order, missing wanted names, warnings)."""
    index = _column_index(columns)
    matched: list[str] = []
    missing: list[str] = []
    warnings: list[str] = []
    for name in wanted:
        hits = index.get(norm_key(name))
        if not hits:
            missing.append(name)
            continue
        if len(hits) > 1:
            warnings.append(f"More than one IODB column matches '{name}'; the first one was used.")
        if hits[0] not in matched:
            matched.append(hits[0])
    return matched, missing, warnings


def unique_values_with_blank(df, max_unique: int = 200) -> dict[str, list[str]]:
    """Per-column option lists for the filter UI; columns with empty cells also offer BLANK_TOKEN."""
    out: dict[str, list[str]] = {}
    for col in df.columns:
        series = df[col]
        text = series.dropna().astype(str)
        values = sorted(text.unique().tolist())[:max_unique]
        if series.isna().any() or (text.str.strip() == "").any():
            values = [v for v in values if v.strip() != ""] + [BLANK_TOKEN]
        out[col] = values
    return out


def build_list_defaults(list_type: str, df) -> dict[str, Any]:
    """
    Defaults for a freshly analysed IODB DataFrame:
      columns         - default columns present in the IODB (actual headers, spec order)
      missing_columns - default names that were not found (never substituted)
      filters         - {actual column: [selected option values]} (inclusion lists, as the UI uses)
      filter_summary  - what each default filter does, for display
      warnings        - anything the user should know
    """
    if list_type not in LIST_TYPES:
        raise ValueError(f"Unknown list type '{list_type}'")
    columns = [str(c) for c in df.columns]
    matched, missing, warnings = match_columns(DEFAULT_COLUMNS[list_type], columns)
    warnings = [f"Default column not found in uploaded IODB: {name}" for name in missing] + warnings

    filters: dict[str, list[str]] = {}
    summary: list[dict[str, Any]] = []
    index = _column_index(columns)
    for spec in DEFAULT_FILTERS[list_type]:
        hits = index.get(norm_key(spec["column"]))
        if not hits:
            warnings.append(f"Default filter column not found in uploaded IODB: {spec['column']}")
            continue
        col = hits[0]
        series = df[col]
        text = series.dropna().astype(str)
        uniques = sorted({v for v in text.tolist() if v.strip() != ""})
        has_blank = bool(series.isna().any() or (text.str.strip() == "").any())
        listed = {norm_key(v) for v in spec["values"]}
        if spec["mode"] == "include_only":
            selected = [v for v in uniques if norm_key(v) in listed]
        else:
            selected = [v for v in uniques if norm_key(v) not in listed]
            if has_blank:
                selected.append(BLANK_TOKEN)              # "all except" keeps blank cells
        deselected = [v for v in uniques if v not in selected]
        if has_blank and BLANK_TOKEN not in selected:
            deselected.append(BLANK_TOKEN)
        if not selected:
            warnings.append(f"Default filter on {col} was not applied: none of its values would remain selected.")
            continue
        filters[col] = selected
        summary.append({"column": col, "mode": spec["mode"], "configured_values": spec["values"],
                        "selected": selected, "deselected": deselected})

    return {"list_type": list_type, "columns": matched, "missing_columns": missing,
            "filters": filters, "filter_summary": summary, "warnings": warnings}
