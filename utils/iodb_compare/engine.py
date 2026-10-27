"""IODB comparison engine.

Read-only: uploaded bytes are parsed into in-memory tables; nothing is written back.
Matching is by TAG NO only (never row number / S.NO). Columns are matched by normalized
header name. The result is a plain, JSON/pickle-friendly dict so other iEZ modules
(e.g. a future impact analysis, or server-side revision compare) can reuse it.
"""
from __future__ import annotations

import io
import re
import unicodedata
import uuid
from collections import Counter, OrderedDict
from datetime import date, datetime, timezone

from .categories import CATEGORY_NAMES, UNCATEGORISED, category_of, header_key

SCHEMA_VERSION = 1

# values treated as "empty" for comparison (original values are still displayed as supplied)
_EMPTY = {"", "nan", "none", "null", "nat", "-", "--", "n/a", "na", "nil"}
_NUM = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")

_TAG_KEYS = ("tagno", "tag", "tagnumber", "tagnummber")
_IGNORED_KEYS = {"sno", "slno", "srno"}          # sorting artefact, not engineering data
_TYPE_KEYS = ("instrumenttypename", "instrumenttype", "instrumenttypedesc", "instrumentmeasuringtype")
_PID_KEYS = ("pidno", "pid", "pidnumber")
_SERVICE_KEYS = ("service",)
_AREA_KEYS = ("area", "areacode", "location")
_STATUS_KEYS = ("status",)


class CompareError(Exception):
    """User-facing validation error (shown as-is in the UI)."""


# ---------------------------------------------------------------- values ----
def display_value(v) -> str:
    """Text shown in the report: the supplied value, tidied only for presentation."""
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v:
            return ""
        return str(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v)
    if isinstance(v, (datetime, date)):
        return v.date().isoformat() if isinstance(v, datetime) else v.isoformat()
    if hasattr(v, "isoformat"):  # pandas Timestamp / NaT
        try:
            return v.date().isoformat()
        except Exception:
            return ""
    s = str(v).replace(" ", " ").strip()
    return "" if s.lower() == "nan" else s


def canon_value(shown: str, ignore_case: bool = True) -> str:
    """Canonical comparison form of a displayed value."""
    s = unicodedata.normalize("NFKC", shown)
    s = re.sub(r"[\s​‌‍﻿]+", " ", s).strip()
    if s.casefold() in _EMPTY:
        return ""
    if _NUM.match(s.replace(",", "")):
        try:
            return "#" + format(float(s.replace(",", "")), ".12g")
        except ValueError:
            pass
    return s.casefold() if ignore_case else s


def clean_header(name) -> str:
    return re.sub(r"\s+", " ", str(name).replace(" ", " ").replace("\n", " ")).strip()


# ----------------------------------------------------------------- table ----
def _has_tag_column(df) -> bool:
    return any(header_key(clean_header(c)) in _TAG_KEYS for c in df.columns)


def _detect_frame(data: bytes):
    """Fallback detection when the standard reader cannot find the IODB: scan every worksheet and
    the first rows of each for a header row that contains a TAG column plus other headers."""
    import pandas as pd

    xls = pd.ExcelFile(io.BytesIO(data))
    best = None  # (score, sheet, header_row)
    for sheet in xls.sheet_names:
        raw = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=40, dtype=object)
        for r in range(len(raw)):
            cells = [display_value(v) for v in raw.iloc[r].tolist()]
            if not any(header_key(c) in _TAG_KEYS for c in cells):
                continue
            score = sum(1 for c in cells if c) + (5 if "iodb" in str(sheet).lower() else 0)
            if best is None or score > best[0]:
                best = (score, sheet, r)
            break
    if best is None or best[0] < 3:
        return None
    df = pd.read_excel(xls, sheet_name=best[1], header=best[2])
    return df.dropna(how="all").reset_index(drop=True)


def load_table(data: bytes, label: str):
    """Parse an IODB workbook: the existing iEZ reader first (sheet + header-row detection),
    then a wider worksheet/header-row scan. Never edits the uploaded bytes."""
    from ..file_handler import read_iodb

    df, err = None, None
    try:
        df, err = read_iodb(io.BytesIO(data))
    except Exception as exc:
        err = str(exc)
        df = None
    if df is None or not _has_tag_column(df):
        try:
            found = _detect_frame(data)
        except Exception as exc:  # unreadable / not an Excel file
            raise CompareError(f"{label} could not be read as an Excel workbook ({exc}). Please upload a valid IODB file.")
        if found is not None:
            df = found
        elif df is None:
            raise CompareError(f'Comparison cannot be completed.\n\nRequired column "TAG NO" was not found in {label} '
                               "(no worksheet with an IODB header row was detected).\nPlease upload a valid IODB file.")
    if len(df) == 0:
        raise CompareError(f"{label} contains no IODB records.")
    return _table_from_frame(df, label)


def _table_from_frame(df, label: str) -> dict:
    # Build unique, named columns. Header-less columns that sit beside a named one
    # (e.g. the extra alarm set-point columns) are kept as "<previous header> (+n)".
    cols: list[dict] = []
    prev, extra = "", 0
    seen: Counter = Counter()
    for i, raw in enumerate(df.columns):
        text = clean_header(raw)
        unnamed = (not text) or text.lower().startswith("unnamed")
        if unnamed:
            if not prev:
                continue
            extra += 1
            name = f"{prev} (+{extra})"
            base_cat = category_of(prev)
        else:
            prev, extra = text, 0
            name, base_cat = text, category_of(text)
        key = header_key(name)
        if key in _IGNORED_KEYS:
            continue
        seen[key] += 1
        if seen[key] > 1:
            n = seen[key]
            key, name = f"{key}#{n}", f"{name} ({n})"
        cols.append({"idx": i, "key": key, "name": name, "category": base_cat, "unnamed": unnamed})

    tag_col = next((c for c in cols if c["key"] in _TAG_KEYS and not c["unnamed"]), None)
    if tag_col is None:
        raise CompareError(
            f'Comparison cannot be completed.\n\nRequired column "TAG NO" was not found in {label}.\n'
            "Please upload a valid IODB file.")

    matrix = df.to_numpy(dtype=object)
    rows = []
    for r in range(matrix.shape[0]):
        rows.append([display_value(matrix[r, c["idx"]]) for c in cols])

    # drop header-less columns that are completely empty
    keep = [j for j, c in enumerate(cols) if not c["unnamed"] or any(row[j] for row in rows)]
    cols = [cols[j] for j in keep]
    rows = [[row[j] for j in keep] for row in rows]
    tag_idx = next(j for j, c in enumerate(cols) if c is tag_col or c["key"] == tag_col["key"])
    return {"label": label, "columns": cols, "rows": rows, "tag_idx": tag_idx}


def _first_idx(cols, keys):
    for k in keys:
        for j, c in enumerate(cols):
            if c["key"] == k:
                return j
    return None


def _brief(cols, row) -> dict:
    def pick(keys):
        j = _first_idx(cols, keys)
        return row[j] if j is not None else ""
    return {"type": pick(_TYPE_KEYS), "pid": pick(_PID_KEYS), "service": pick(_SERVICE_KEYS),
            "area": pick(_AREA_KEYS), "status": pick(_STATUS_KEYS)}


def _index(table: dict):
    """tag -> list of row indices (original order); also missing-tag record positions."""
    idx: "OrderedDict[str, list[int]]" = OrderedDict()
    missing = []
    tj = table["tag_idx"]
    for n, row in enumerate(table["rows"]):
        tag = canon_tag(row[tj])
        if not tag:
            missing.append(n + 1)
            continue
        idx.setdefault(tag, []).append(n)
    return idx, missing


def canon_tag(shown: str) -> str:
    s = unicodedata.normalize("NFKC", shown)
    s = re.sub(r"[\s​‌‍﻿]+", " ", s).strip().upper()
    return "" if s.casefold() in _EMPTY else s


def _numeric_share(table, j):
    vals = [r[j] for r in table["rows"] if canon_value(r[j])]
    if not vals:
        return None
    return sum(1 for v in vals if _NUM.match(v.replace(",", ""))) / len(vals)


# -------------------------------------------------------------- compare ----
def compare_files(data1: bytes, name1: str, data2: bytes, name2: str, *, ignore_case: bool = True,
                  project: str = "", user: str = "") -> tuple[dict, dict]:
    t1 = load_table(data1, "IODB 1")
    t2 = load_table(data2, "IODB 2")
    return compare_tables(t1, t2, name1, name2, ignore_case=ignore_case, project=project, user=user)


def compare_tables(t1: dict, t2: dict, name1: str, name2: str, *, ignore_case: bool = True,
                   project: str = "", user: str = "") -> tuple[dict, dict]:
    """Returns (result, full_rows). `result` is light (no full records); `full_rows`
    holds every record's complete values for the detail view."""
    c1, c2 = t1["columns"], t2["columns"]
    map2 = {c["key"]: j for j, c in enumerate(c2)}
    common = [(j1, map2[c["key"]], c) for j1, c in enumerate(c1) if c["key"] in map2 and c["key"] not in _TAG_KEYS]
    only1 = [c["name"] for c in c1 if c["key"] not in map2]
    only2 = [c["name"] for c in c2 if c["key"] not in {x["key"] for x in c1}]

    idx1, missing1 = _index(t1)
    idx2, missing2 = _index(t2)
    dup1 = {t: len(v) for t, v in idx1.items() if len(v) > 1}
    dup2 = {t: len(v) for t, v in idx2.items() if len(v) > 1}
    dups = set(dup1) | set(dup2)

    warnings: list[dict] = []
    for label, dup in (("IODB 1", dup1), ("IODB 2", dup2)):
        if dup:
            lines = ", ".join(f"{t} appears {n} times" for t, n in list(dup.items())[:15])
            more = f" (and {len(dup) - 15} more)" if len(dup) > 15 else ""
            warnings.append({"level": "warning", "code": "DUPLICATE_TAG",
                             "message": f"Duplicate TAG NO detected in {label}: {lines}{more}. Duplicate tags require review; "
                                        "they were NOT compared and are listed under 'Needs review'."})
    for label, miss in (("IODB 1", missing1), ("IODB 2", missing2)):
        if miss:
            warnings.append({"level": "warning", "code": "EMPTY_TAG",
                             "message": f"{label}: {len(miss)} record(s) have an empty TAG NO and were skipped "
                                        f"(record positions: {', '.join(map(str, miss[:10]))}{'...' if len(miss) > 10 else ''})."})
    if only1:
        warnings.append({"level": "info", "code": "COLUMNS_ONLY_IN_1",
                         "message": f"Columns present only in IODB 1 (not compared): {', '.join(only1[:12])}"
                                    f"{'...' if len(only1) > 12 else ''}."})
    if only2:
        warnings.append({"level": "info", "code": "COLUMNS_ONLY_IN_2",
                         "message": f"Columns present only in IODB 2 (not compared): {', '.join(only2[:12])}"
                                    f"{'...' if len(only2) > 12 else ''}."})
    for j1, j2, c in common:  # data type inconsistencies
        s1, s2 = _numeric_share(t1, j1), _numeric_share(t2, j2)
        if s1 is not None and s2 is not None and ((s1 >= 0.9 and s2 <= 0.1) or (s2 >= 0.9 and s1 <= 0.1)):
            warnings.append({"level": "info", "code": "TYPE_MISMATCH",
                             "message": f"Column '{c['name']}' holds numeric values in one IODB and text in the other."})

    tags1, tags2 = set(idx1) - dups, set(idx2) - dups
    common_tags = [t for t in idx1 if t in tags2]
    added_tags = [t for t in idx2 if t in tags2 and t not in tags1]
    deleted_tags = [t for t in idx1 if t in tags1 and t not in tags2]

    records = {"added": [], "deleted": [], "modified": [], "unchanged": [], "review": []}
    category_counts: Counter = Counter()
    field_counts: Counter = Counter()
    field_total = 0

    for t in added_tags:
        row = t2["rows"][idx2[t][0]]
        records["added"].append({"tag": t, "shown_tag": row[t2["tag_idx"]], **_brief(c2, row), "n_changes": 0, "changes": []})
    for t in deleted_tags:
        row = t1["rows"][idx1[t][0]]
        records["deleted"].append({"tag": t, "shown_tag": row[t1["tag_idx"]], **_brief(c1, row), "n_changes": 0, "changes": []})

    for t in common_tags:
        r1, r2 = t1["rows"][idx1[t][0]], t2["rows"][idx2[t][0]]
        changes = []
        for j1, j2, c in common:
            old, new = r1[j1], r2[j2]
            if canon_value(old, ignore_case) == canon_value(new, ignore_case):
                continue
            o_empty, n_empty = not canon_value(old), not canon_value(new)
            ctype = "VALUE ADDED" if o_empty else ("VALUE REMOVED" if n_empty else "VALUE CHANGED")
            changes.append({"column": c["name"], "column_key": c["key"], "category": c["category"],
                            "old": old, "new": new, "change_type": ctype})
        brief = _brief(c2, r2)
        if not brief["type"]:
            brief = _brief(c1, r1)
        rec = {"tag": t, "shown_tag": r2[t2["tag_idx"]], **brief, "n_changes": len(changes), "changes": changes}
        if changes:
            records["modified"].append(rec)
            field_total += len(changes)
            for ch in changes:
                category_counts[ch["category"]] += 1
                field_counts[ch["column"]] += 1
        else:
            records["unchanged"].append(rec)

    for t in sorted(dups):
        src, tb, ix = (t1, c1, idx1) if t in idx1 else (t2, c2, idx2)
        row = src["rows"][ix[t][0]]
        records["review"].append({"tag": t, "shown_tag": row[src["tag_idx"]], **_brief(tb, row),
                                  "count_1": len(idx1.get(t, [])), "count_2": len(idx2.get(t, [])),
                                  "n_changes": 0, "changes": []})

    n1, n2 = sum(len(v) for v in idx1.values()), sum(len(v) for v in idx2.values())
    n_common = len(common_tags)
    totally_different = n_common == 0 and bool(tags1) and bool(tags2)
    counts = {"added": len(added_tags), "deleted": len(deleted_tags), "modified": len(records["modified"]),
              "unchanged": len(records["unchanged"]), "review": len(records["review"])}

    category_rows = [{"code": code, "name": CATEGORY_NAMES[code], "count": category_counts.get(code, 0)}
                     for code in [c for c, _ in sorted(CATEGORY_NAMES.items())] if code != UNCATEGORISED[0]]
    if category_counts.get(UNCATEGORISED[0]):
        category_rows.append({"code": UNCATEGORISED[0], "name": UNCATEGORISED[1], "count": category_counts[UNCATEGORISED[0]]})

    result = {
        "schema_version": SCHEMA_VERSION,
        "id": uuid.uuid4().hex,
        "created": datetime.now(timezone.utc).isoformat(),
        "user": user, "project": project,
        "file1": {"name": name1, "instruments": n1, "records": len(t1["rows"]), "columns": len(c1)},
        "file2": {"name": name2, "instruments": n2, "records": len(t2["rows"]), "columns": len(c2)},
        "options": {"ignore_case": ignore_case, "empty_equivalents": sorted(_EMPTY - {""}), "ignored_columns": ["S.NO"]},
        "compared_columns": [{"name": c["name"], "category": c["category"]} for _, _, c in common],
        "columns_only_in_1": only1, "columns_only_in_2": only2,
        "counts": counts,
        "totals": {"iodb1": n1, "iodb2": n2, "common": n_common, "changed_instruments": counts["modified"],
                   "field_changes": field_total},
        "totally_different": totally_different,
        "category_counts": category_rows,
        "field_counts": [{"column": k, "count": v} for k, v in field_counts.most_common()],
        "duplicates": {"iodb1": dup1, "iodb2": dup2},
        "missing_tag": {"iodb1": len(missing1), "iodb2": len(missing2)},
        "warnings": warnings,
        "records": records,
    }
    result["summary_text"] = summary_text(result)

    full = {"columns1": [c["name"] for c in c1], "columns2": [c["name"] for c in c2],
            "rows1": {t: t1["rows"][i[0]] for t, i in idx1.items() if t not in dups},
            "rows2": {t: t2["rows"][i[0]] for t, i in idx2.items() if t not in dups},
            "dups1": {t: [t1["rows"][k] for k in idx1[t]] for t in dup1},
            "dups2": {t: [t2["rows"][k] for k in idx2[t]] for t in dup2}}
    return result, full


def _n(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def summary_text(r: dict) -> str:
    """Written summary generated only from the actual comparison numbers."""
    c, t = r["counts"], r["totals"]
    l1, l2 = r["file1"]["name"], r["file2"]["name"]
    if r["totally_different"]:
        return (f"No common TAG NOs were found between {l1} ({_n(t['iodb1'], 'instrument')}) and {l2} "
                f"({_n(t['iodb2'], 'instrument')}). The uploaded files are totally different IODB datasets and cannot be "
                "treated as revisions of the same IODB.")
    if t["iodb1"] == 0 or t["iodb2"] == 0:
        return "One of the uploaded files contains no usable instrument records."
    parts = [f"Comparison of {l1} and {l2} identified {_n(c['added'], 'newly added instrument')}, "
             f"{_n(c['deleted'], 'deleted instrument')}, and {_n(c['modified'], 'existing instrument')} with engineering data "
             f"modifications. A total of {_n(c['unchanged'], 'instrument')} remain unchanged."]
    if c["modified"]:
        fc = t["field_changes"]
        parts.append(f"Across the modified instruments, {_n(fc, 'field-level change')} {'was' if fc == 1 else 'were'} identified.")
    else:
        parts.append("No field-level changes were identified in the instruments common to both files.")
    if c["review"]:
        parts.append(f"{_n(c['review'], 'tag')} with duplicate TAG NO entries were excluded and need review.")
    return " ".join(parts)
