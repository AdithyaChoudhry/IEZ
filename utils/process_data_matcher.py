"""Tag matching + LINE SIZE extraction + optional IODB prefill for Process Data Requisition."""
from __future__ import annotations

import re
from .list_defaults import norm_key, match_columns
from .process_data_library import INSTRUMENT_TYPES

MATCH_FIELDS = ("INSTRUMENT TYPE NAME", "INSTRUMENT MEASURING TYPE",
                "SIGNAL DESCRIPTION", "SERVICE", "TAG NO")

IDENTIFICATION_IODB_COLUMNS = {
    "TAG NO": "TAG NO",
    "EQUIPMENT DESCRIPTION": "EQUIPMENT DESCRIPTION",
    "P&ID NO.": "P&ID NO.",
    "SERVICE": "SERVICE",
    "EQUIPMENT NO": "EQUIPMENT NO",
    "LINE": "LINE",
}


def extract_line_size(line_value) -> str:
    """Extract pipe size from a LINE tag string.
    '600-SEW-MS-10109' -> '600 mm'
    '2"-SW-20101-B24-NI' -> '2"'
    Blank/unparseable -> ''.
    Rule: take the substring before the first '-'. If it contains '"', return as-is
    (already has an inch mark). Else if it's a plain number (int or decimal), append ' mm'.
    Otherwise return the raw first segment unchanged (unrecognized format, don't guess further)."""
    if line_value is None:
        return ""
    s = str(line_value).strip()
    if not s:
        return ""
    first_segment = s.split("-")[0].strip()
    if not first_segment:
        return ""
    if '"' in first_segment:
        return first_segment
    if re.match(r"^\d+(\.\d+)?$", first_segment):
        return f"{first_segment} mm"
    return first_segment


def resolve_match_columns(columns: list[str]) -> dict[str, str | None]:
    """Resolve MATCH_FIELDS against actual IODB headers using list_defaults.match_columns
    (case/whitespace-insensitive). Returns {wanted_field_name: actual_header_or_None}."""
    _matched, missing, _warnings = match_columns(list(MATCH_FIELDS), columns)
    result: dict[str, str | None] = {}
    for wanted in MATCH_FIELDS:
        if wanted in missing:
            result[wanted] = None
            continue
        # find the actual header whose normalized form equals this wanted name's normalized form
        found = None
        for actual in columns:
            if norm_key(actual) == norm_key(wanted):
                found = actual
                break
        result[wanted] = found
    return result


def _text_matches(cell_value, alias: str) -> bool:
    """Whole-word match of the alias inside the normalized cell value (case/space-insensitive).
    'LEVEL TRANSMITTER' catches 'RADAR LEVEL TRANSMITTER'. A cell can never match just because
    it is short (e.g. '-' or 'LT' inside another word) - no reverse/partial matching."""
    if cell_value is None:
        return False
    cell_norm = norm_key(cell_value)
    alias_norm = norm_key(alias)
    if not cell_norm or not alias_norm or cell_norm in _PLACEHOLDERS:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(alias_norm) + r"(?![a-z0-9])", cell_norm) is not None


_PLACEHOLDERS = {"-", "--", "nan", "none", "n/a", "na", "tba", "tbd", "nil"}


def _strip_units(header) -> str:
    return norm_key(re.sub(r"\([^)]*\)", "", str(header)))


def _find_header(columns: list[str], wanted: str):
    """Exact normalized match first; then match ignoring a '(unit)' suffix in the IODB header."""
    key = norm_key(wanted)
    for c in columns:
        if norm_key(c) == key:
            return c
    for c in columns:
        if _strip_units(c) == key:
            return c
    return None


def all_tags(df) -> list[dict]:
    """Every IODB row as an identification record - used by custom types, which have no
    automatic matching: the engineer picks the tags by hand."""
    columns = [str(c) for c in df.columns]

    def col(row, name):
        for c in columns:
            if norm_key(c) == norm_key(name):
                v = row.get(c, "")
                return "" if v is None or (isinstance(v, float) and v != v) else str(v).strip()
        return ""

    out = []
    for idx, row in df.iterrows():
        tag = col(row, "TAG NO")
        if not tag or norm_key(tag) in _PLACEHOLDERS:
            continue
        line = col(row, "LINE")
        out.append({"tag_no": tag, "equipment_description": col(row, "EQUIPMENT DESCRIPTION"),
                    "pid_no": col(row, "P&ID NO."), "service": col(row, "SERVICE"),
                    "equipment_no": col(row, "EQUIPMENT NO"), "line": line,
                    "line_size": extract_line_size(line), "row_index": int(idx)})
    return out


def match_tags(df, type_key: str) -> tuple[list[dict], list[str]]:
    """Find IODB rows matching the given instrument type's aliases/tag-prefixes.
    Returns (matched_rows, warnings). Each matched_row dict has keys:
    tag_no, equipment_description, pid_no, service, equipment_no, line, line_size, row_index.
    No fuzzy/Levenshtein matching - deliberate. Matching rule per row: normalized substring
    match (both directions) against cfg.match_aliases on any of INSTRUMENT TYPE NAME /
    INSTRUMENT MEASURING TYPE / SIGNAL DESCRIPTION / SERVICE, OR TAG NO's alnum-prefix
    (split on non-alnum chars) matches any cfg.tag_prefixes as a standalone segment.
    If a MATCH_FIELD column isn't present in this IODB, skip that field for matching (don't error) -
    still try the others and TAG NO prefix matching."""
    cfg = INSTRUMENT_TYPES.get(type_key)
    if cfg is None:
        raise ValueError(f"Unknown instrument type key: {type_key}")
    if cfg.is_custom:
        return [], []  # custom types never auto-match, this function shouldn't be called for them - caller's responsibility

    columns = [str(c) for c in df.columns]
    resolved = resolve_match_columns(columns)
    warnings: list[str] = []
    for field, actual in resolved.items():
        if actual is None:
            warnings.append(f"Column not found in IODB for matching: {field}")

    # LINE isn't in MATCH_FIELDS (it's an identification field, not a match field) -
    # resolve its actual header once, up front.
    line_col = None
    for c in columns:
        if norm_key(c) == norm_key("LINE"):
            line_col = c
            break

    def _id_col(row, name):
        for c in columns:
            if norm_key(c) == norm_key(name):
                return row.get(c, "")
        return ""

    matched_rows: list[dict] = []
    for idx, row in df.iterrows():
        is_match = False
        for field in ("INSTRUMENT TYPE NAME", "INSTRUMENT MEASURING TYPE", "SIGNAL DESCRIPTION", "SERVICE"):
            actual = resolved.get(field)
            if actual is None:
                continue
            cell = row.get(actual)
            if any(_text_matches(cell, alias) for alias in cfg.match_aliases):
                is_match = True
                break
        # Tag prefix is only a fallback for rows with NO instrument type wording at all: a tag
        # like PI-10101 whose type name says PRESSURE INDICATING TRANSMITTER is not a gauge.
        type_actual = resolved.get("INSTRUMENT TYPE NAME")
        type_text = norm_key(row.get(type_actual)) if type_actual is not None and row.get(type_actual) is not None else ""
        if not is_match and cfg.tag_prefixes and type_text in _PLACEHOLDERS | {""}:
            tag_actual = resolved.get("TAG NO")
            if tag_actual is not None:
                tag_val = str(row.get(tag_actual) or "").strip().upper()
                # real tags look like "200-LT-001" - check if any tag_prefix appears as a
                # standalone segment when split on non-alphanumeric characters
                segments = re.split(r"[^A-Z0-9]+", tag_val)
                if any(seg == prefix.upper() for seg in segments for prefix in cfg.tag_prefixes):
                    is_match = True
        if not is_match:
            continue

        line_value = row.get(line_col, "") if line_col else ""

        matched_rows.append({
            "tag_no": str(_id_col(row, "TAG NO") or "").strip(),
            "equipment_description": str(_id_col(row, "EQUIPMENT DESCRIPTION") or "").strip(),
            "pid_no": str(_id_col(row, "P&ID NO.") or "").strip(),
            "service": str(_id_col(row, "SERVICE") or "").strip(),
            "equipment_no": str(_id_col(row, "EQUIPMENT NO") or "").strip(),
            "line": str(line_value or "").strip(),
            "line_size": extract_line_size(line_value),
            "row_index": int(idx),
        })
    return matched_rows, warnings


def build_prefill_values(df, matched_rows: list[dict], type_key: str, use_iodb_values: bool) -> list[dict]:
    """For each matched row, return a dict of {process_field_name: value}.
    If use_iodb_values is False: every value is "" for every field, always - never fabricate.
    If True: for each ProcessField with non-empty iodb_aliases, resolve those alias column names
    against df.columns (case/whitespace-insensitive via list_defaults.match_columns) and copy the
    cell value as-is from df.iloc[row['row_index']] - no computation/derivation, copy only."""
    cfg = INSTRUMENT_TYPES.get(type_key)
    if cfg is None or cfg.is_custom:
        return [{} for _ in matched_rows]
    if not use_iodb_values:
        return [{f.name: "" for f in cfg.fields} for _ in matched_rows]

    columns = [str(c) for c in df.columns]
    field_column_map: dict[str, str | None] = {}
    for f in cfg.fields:
        col = None
        for alias in f.iodb_aliases:
            col = _find_header(columns, alias)
            if col:
                break
        field_column_map[f.name] = col

    results = []
    for row_info in matched_rows:
        row = df.iloc[row_info["row_index"]]
        values = {}
        for f in cfg.fields:
            actual_col = field_column_map.get(f.name)
            raw = row.get(actual_col) if actual_col else None
            text = "" if raw is None or (isinstance(raw, float) and raw != raw) else str(raw).strip()
            values[f.name] = "" if norm_key(text) in _PLACEHOLDERS else text
        results.append(values)
    return results
