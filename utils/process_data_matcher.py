"""Tag matching + LINE SIZE extraction + optional IODB prefill for Process Data Requisition."""
from __future__ import annotations

import re
from typing import Optional
from .list_defaults import norm_key, match_columns
from .process_data_library import INSTRUMENT_TYPES
from .process_data_profiles import resolve_fields

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


def _unit_key(unit) -> str:
    """A unit reduced to a comparable form: case, spacing, superscripts and a gauge suffix are ignored
    ('Kg/cm2 g' == 'kg/cm2', 'deg C' == '°C'). Nothing is converted - two different units stay different."""
    u = re.sub(r"\s+", "", str(unit or "").lower().replace("²", "2").replace("³", "3").replace("º", "°"))
    u = u.replace("degc", "c").replace("°c", "c").replace("℃", "c").replace("/hr", "/h")
    return re.sub(r"[.(]?g\)?$", "", u) if u.startswith(("kg/cm2", "kg/cm")) else u


def _header_unit(header) -> str:
    m = re.search(r"\(([^)]*)\)\s*$", str(header))
    return m.group(1).strip() if m else ""


def build_prefill_values(df, matched_rows: list[dict], type_key: str, use_iodb_values: bool,
                         subtype=None, notes=None) -> list[dict]:
    """For each matched row, return a dict of {process_field_name: value}.
    If use_iodb_values is False: every value is "" for every field, always - never fabricate.
    If True: for each ProcessField with non-empty iodb_aliases, resolve those alias column names
    against df.columns (case/whitespace-insensitive via list_defaults.match_columns) and copy the
    cell value as-is from df.iloc[row['row_index']] - no computation/derivation, copy only.
    A value is NOT copied when the IODB header states a unit that differs from the unit the datasheet prints for
    that column (e.g. IODB kg/cm2 vs a datasheet column in mmWC): units are never converted, the cell stays blank
    for the process team and the reason is appended to `notes` (a list) when one is given."""
    cfg = INSTRUMENT_TYPES.get(type_key)
    if cfg is None or cfg.is_custom:
        return [{} for _ in matched_rows]
    fields = resolve_fields(cfg, subtype)
    if not use_iodb_values:
        return [{f.name: "" for f in fields} for _ in matched_rows]

    columns = [str(c) for c in df.columns]
    field_column_map: dict[str, str | None] = {}
    for f in fields:
        col = None
        for alias in f.iodb_aliases:
            col = _find_header(columns, alias)
            if col:
                break
        have = _header_unit(col) if col else ""
        if col and have and f.unit and _unit_key(have) != _unit_key(f.unit):
            if notes is not None:
                notes.append(f"IODB column '{col}' was not copied into '{f.name} ({f.unit})': the units differ and no "
                             "conversion is applied - the cell is left blank for the Process team.")
            col = None
        field_column_map[f.name] = col

    results = []
    for row_info in matched_rows:
        row = df.iloc[row_info["row_index"]]
        values = {}
        for f in fields:
            actual_col = field_column_map.get(f.name)
            raw = row.get(actual_col) if actual_col else None
            text = "" if raw is None or (isinstance(raw, float) and raw != raw) else str(raw).strip()
            values[f.name] = "" if norm_key(text) in _PLACEHOLDERS else text
        results.append(values)
    return results


# ── subtype-aware matching + whole-IODB classification (Process Data Requisition only) ───────────────────────────────
from .process_data_subtypes import classify as _classify_subtype, has_rules as _has_subtype_rules, subtype_columns  # noqa: E402

_TYPE_PATTERNS: dict = {}
_ALIAS_PATTERNS: dict = {}


def _alias_re(alias: str):
    p = _ALIAS_PATTERNS.get(alias)
    if p is None:
        p = _ALIAS_PATTERNS[alias] = re.compile(r"(?<![a-z0-9])" + re.escape(norm_key(alias)) + r"(?![a-z0-9])")
    return p


def _type_re(cfg):
    """One compiled expression per type: any of its aliases as whole words (the same rule as _text_matches)."""
    p = _TYPE_PATTERNS.get(cfg.key)
    if p is None:
        aliases = sorted({norm_key(a) for a in cfg.match_aliases if norm_key(a)}, key=len, reverse=True)
        p = _TYPE_PATTERNS[cfg.key] = (re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(a) for a in aliases) + r")(?![a-z0-9])")
                                       if aliases else False)
    return p


def _clean(v) -> str:
    return "" if v is None or (isinstance(v, float) and v != v) else str(v).strip()


class _Iodb:
    """The IODB prepared once: one record per row with its identification values and its (normalised) matching texts."""

    def __init__(self, df):
        self.columns = [str(c) for c in df.columns]
        res = resolve_match_columns(self.columns)
        self.sub_cols = subtype_columns(self.columns)
        by_norm = {norm_key(c): c for c in df.columns}
        get = lambda n: by_norm.get(norm_key(n))                                       # noqa: E731
        line_col, tag_col, type_col = get("LINE"), res.get("TAG NO"), res.get("INSTRUMENT TYPE NAME")
        id_cols = {k: get(v) for k, v in (("tag_no", "TAG NO"), ("equipment_description", "EQUIPMENT DESCRIPTION"), ("pid_no", "P&ID NO."),
                                          ("service", "SERVICE"), ("equipment_no", "EQUIPMENT NO"))}
        match_cols = [res.get(f) for f in ("INSTRUMENT TYPE NAME", "INSTRUMENT MEASURING TYPE", "SIGNAL DESCRIPTION", "SERVICE")]
        sub_cols = self.sub_cols["explicit"] + self.sub_cols["descriptive"]
        self.warnings = [f"Column not found in IODB for matching: {f}" for f, a in res.items() if a is None]
        self.rows = []
        for idx, rec in zip(df.index, df.to_dict("records")):
            texts = [norm_key(rec.get(c)) if c is not None and _clean(rec.get(c)) else "" for c in match_cols]
            type_text = norm_key(rec.get(type_col)) if type_col is not None and _clean(rec.get(type_col)) else ""
            line = _clean(rec.get(line_col)) if line_col else ""
            row = {k: _clean(rec.get(c)) if c is not None else "" for k, c in id_cols.items()}
            row.update(line=line, line_size=extract_line_size(line), row_index=int(idx) if str(idx).lstrip("-").isdigit() else idx)
            segs = re.split(r"[^A-Z0-9]+", _clean(rec.get(tag_col)).upper()) if tag_col is not None else []
            self.rows.append({"row": row, "texts": [t for t in texts if t and t not in _PLACEHOLDERS],
                              "no_type": type_text in _PLACEHOLDERS | {""}, "segments": segs,
                              "sub_values": {c: rec.get(c) for c in sub_cols}, "type_name": _clean(rec.get(type_col)) if type_col is not None else ""})

    def types_of(self, r, cfgs) -> list:
        """The type configs one row belongs to (alias in a matching text, or the tag prefix when the row has no type wording)."""
        out = []
        for cfg in cfgs:
            pat = _type_re(cfg)
            hit = bool(pat) and any(pat.search(t) for t in r["texts"])
            if not hit and cfg.tag_prefixes and r["no_type"]:
                hit = any(seg == p.upper() for seg in r["segments"] for p in cfg.tag_prefixes)
            if hit:
                out.append(cfg)
        return out


def _most_specific(cfgs, r) -> list:
    """When a row fits several types, keep the one whose matched alias contains the other's ('FLOW ELEMENT - ORIFICE PLATE'
    over 'ORIFICE PLATE'); otherwise keep them all (ambiguous)."""
    if len(cfgs) < 2:
        return cfgs
    best = {}
    for cfg in cfgs:
        found = [norm_key(a) for a in cfg.match_aliases if any(_alias_re(a).search(t) for t in r["texts"])]
        best[cfg.key] = max(found, key=len) if found else ""
    keep = [c for c in cfgs if not any(o.key != c.key and best[c.key] != best[o.key] and best[c.key] in best[o.key] for o in cfgs)]
    return keep or cfgs


def match_tags_detailed(df, type_key: str, subtype: Optional[str] = None, iodb: "Optional[_Iodb]" = None) -> dict:
    """
    The tags of one instrument type, filtered by the selected SUBTYPE when one is given:
      matched    rows whose wording establishes exactly this subtype
      unresolved rows of the type whose subtype is not established (each with the reason) - NOT placed in any subtype
      excluded   {other subtype: count} rows that belong to a different subtype
    Without a subtype every row of the type is matched (the behaviour before subtypes were checked).
    """
    cfg = INSTRUMENT_TYPES.get(type_key)
    if cfg is None:
        raise ValueError(f"Unknown instrument type key: {type_key}")
    broad, warnings = match_tags(df, type_key)
    out = {"matched": broad, "unresolved": [], "excluded": {}, "warnings": warnings, "filtered": False}
    if not subtype or not _has_subtype_rules(type_key):
        return out
    iodb = iodb or _Iodb(df)
    by_index = {r["row"]["row_index"]: r for r in iodb.rows}
    matched = []
    for row in broad:
        src = by_index.get(row["row_index"])
        c = _classify_subtype(type_key, src["sub_values"] if src else {}, iodb.sub_cols)
        if c["subtype"] == subtype:
            matched.append({**row, "subtype": subtype})
        elif c["subtype"] is None:
            out["unresolved"].append({**row, "reason": c["reason"]})
        else:                                                    # another subtype, or a technology that has no subtype of its own
            name = c["subtype"] or c.get("other") or "other"
            out["excluded"][name] = out["excluded"].get(name, 0) + 1
    out.update(matched=matched, filtered=True)
    return out


def detect_groups(df) -> dict:
    """
    Every supported instrument type / subtype present in the IODB, in one pass. A row is assigned to one type only (a row that
    fits several unrelated types is reported as ambiguous), then to a subtype where the type has subtypes; rows whose subtype is
    not established form a review group (not selected by default). Duplicate worksheet rows of one tag count once; the same tag
    with different identification data is reported.
    """
    iodb = _Iodb(df)
    cfgs = [c for c in INSTRUMENT_TYPES.values() if not c.is_custom]
    groups: dict = {}
    unsupported: dict = {}
    ambiguous, conflicts = [], []
    for r in iodb.rows:
        row = r["row"]
        if not row["tag_no"] or norm_key(row["tag_no"]) in _PLACEHOLDERS:
            continue
        hits = _most_specific(iodb.types_of(r, cfgs), r)
        if not hits:
            name = r["type_name"] or row["equipment_description"] or "(no instrument type)"
            unsupported.setdefault(name, set()).add(row["tag_no"])
            continue
        if len(hits) > 1:
            ambiguous.append({"tag_no": row["tag_no"], "types": [h.label for h in hits]})
            continue
        cfg = hits[0]
        sub, reason, other = "", "", ""
        if _has_subtype_rules(cfg.key):
            c = _classify_subtype(cfg.key, r["sub_values"], iodb.sub_cols)
            sub, reason, other = c["subtype"], c["reason"], c.get("other", "")
        review = sub is None
        key = f"{cfg.key}|{'' if review else sub}|{'review' if review else other}"
        g = groups.setdefault(key, {"key": key, "type_key": cfg.key, "type_label": cfg.label, "subtype": "" if review else sub,
                                    "other": other, "needs_review": review, "reason": reason if review else "", "tags": {},
                                    "category": cfg.category})
        seen = g["tags"].get(row["tag_no"])
        if seen is None:
            g["tags"][row["tag_no"]] = {**row, **({"reason": reason} if review else {})}
        elif any(seen[k] != row[k] for k in ("pid_no", "service", "equipment_no", "line")):
            conflicts.append(f"{row['tag_no']} appears more than once with different data ({g['type_label']}); the first record is used.")
    order = {k: i for i, k in enumerate(INSTRUMENT_TYPES)}
    out_groups = []
    for g in sorted(groups.values(), key=lambda g: (order.get(g["type_key"], 999), g["needs_review"], g["subtype"])):
        label = g["type_label"] + (f" - {g['subtype']}" if g["subtype"] else (" - subtype not determined" if g["needs_review"]
                                                                                  else (f" - {g['other']}" if g["other"] else "")))
        out_groups.append({"key": g["key"], "type_key": g["type_key"], "type_label": g["type_label"], "subtype": g["subtype"],
                           "label": label, "needs_review": g["needs_review"], "reason": g["reason"], "category": g["category"],
                           "count": len(g["tags"]), "tags": list(g["tags"].values())})
    eligible = sum(g["count"] for g in out_groups if not g["needs_review"])
    return {"groups": out_groups, "types_found": len({g["type_key"] for g in out_groups if not g["needs_review"]}),
            "eligible_tags": eligible, "review_tags": sum(g["count"] for g in out_groups if g["needs_review"]),
            "unsupported": sorted(({"name": n, "count": len(t), "reason": "No Process Data Requisition configuration for this instrument type."}
                                   for n, t in unsupported.items()), key=lambda x: -x["count"])[:100],
            "ambiguous": ambiguous[:100], "ambiguous_count": len(ambiguous),
            "warnings": iodb.warnings + conflicts[:50]}
