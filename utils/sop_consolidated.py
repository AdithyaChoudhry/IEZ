"""
sop_consolidated.py
===================
Second generation strategy for the SOP datasheet generator:

    CONSOLIDATED  - ONE workbook: the main instrument datasheet (common specifications, tag-specific rows keep their
                    "REFER ANNEXURE-x" reference) + the tag-wise ANNEXURE with one row per selected tag.
    INDIVIDUAL    - the existing engine (one datasheet per tag, zipped) - see sop_datasheet.generate_with_report.

Nothing here is client specific: the annexure sheet is the one the EG sheet itself refers to ("REFER ANNEXURE-I"),
its header is read generically (multi-row headers with MIN/NOR/MAX sub-columns), and its columns are mapped to IODB
columns by name - the engineer confirms or corrects the mapping before approval. Missing data is reported, never invented.
Shared logic (SOP reading, field parsing, IODB loading, value resolution, cell styling) is reused from sop_datasheet.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from copy import copy
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import pandas as pd

from .sop_datasheet import (
    SheetModel, FieldSpec, read_workbook, list_datasheet_sheets, parse_field_spec,
    _load_iodb_df, _find_column, _build_iodb_colmap, _resolve_values_for_tag, _apply_cell_style,
    build_datasheet_xlsx, IODB_TAG_KEYS, _PLACEHOLDER_RE, override_for,
)

INDIVIDUAL = "INDIVIDUAL"
CONSOLIDATED = "CONSOLIDATED"
FORMATS = (INDIVIDUAL, CONSOLIDATED)
FORMAT_LABELS = {CONSOLIDATED: "Consolidated Datasheet with Annexure", INDIVIDUAL: "Individual Datasheet for Each Tag"}

_REF_RE = re.compile(r"refer\s*(annexure[\s\-_]*[ivx0-9]+)", re.IGNORECASE)
_SUB = {"min": "min", "minimum": "min", "nor": "nor", "normal": "nor", "max": "max", "maximum": "max"}
_TAG_HEADERS = {"tag", "tag no", "tag nos", "tag number", "instrument tag", "instrument tag no", "tag no s"}
_SERIAL_HEADERS = {"sl no", "s no", "sr no", "sl", "sno", "slno", "srno", "no", "item", "item no"}


def _n(s: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(s or "").lower())).strip()


_ABBR = {"inst": "instrument", "instr": "instrument", "temp": "temperature", "press": "pressure", "conn": "connection"}


def _clean(s: Any) -> str:
    """Header text for matching: drop units in brackets, '&', '/', punctuation; expand common abbreviations."""
    t = re.sub(r"\([^)]*\)", " ", str(s or ""))
    return " ".join(_ABBR.get(w, w) for w in _n(t.replace("&", " ")).split())


def _sheet_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


# ── annexure structure ───────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class AnnexCol:
    col: int
    header: str              # main header text (merged anchor)
    sub: str                 # sub header (MIN / NOR / MAX ...) or ""
    label: str               # human label: "PRESSURE(Kg/Cm2 g) · MIN"
    kind: str = "data"       # "tag" | "serial" | "data"
    hidden: bool = False     # column width ~0 in the template


@dataclass
class AnnexureSpec:
    sheet: str
    header_top: int          # 0-based
    data_start: int          # first data row (0-based)
    block_end: int           # first row after the template's data block (0-based, exclusive)
    columns: list[AnnexCol]
    tag_col: int
    serial_col: Optional[int]

    @property
    def capacity(self) -> int:
        return self.block_end - self.data_start


def referenced_annexures(fields: list[FieldSpec]) -> Counter:
    refs: Counter = Counter()
    for f in fields:
        for d in f.defaults:
            m = _REF_RE.search(d or "")
            if m:
                refs[m.group(1).upper().replace(" ", "")] += 1
    return refs


def _anchor_map(sm: SheetModel) -> dict[tuple[int, int], tuple[int, int, int, int]]:
    out = {}
    for (rlo, rhi, clo, chi) in sm.merged:
        for r in range(rlo, rhi):
            for c in range(clo, chi):
                out[(r, c)] = (rlo, rhi, clo, chi)
    return out


def parse_annexure(sm: SheetModel) -> Optional[AnnexureSpec]:
    """Read a tag-wise annexure sheet generically: header row with a TAG column, sub-header rows, the data block."""
    header_top = tag_col = None
    for r in range(min(sm.nrows, 40)):
        for c in range(sm.ncols):
            if _n(sm.value(r, c)) in _TAG_HEADERS:
                header_top, tag_col = r, c
                break
        if header_top is not None:
            break
    if header_top is None:
        return None
    anchors = _anchor_map(sm)
    bottom = header_top
    changed = True
    while changed:                                   # the header block is every row covered by a merge that starts in it
        changed = False
        for (rlo, rhi, clo, chi) in sm.merged:
            if header_top <= rlo <= bottom and rhi - 1 > bottom:
                bottom, changed = rhi - 1, True
    data_start = bottom + 1

    def anchor_value(r, c):
        a = anchors.get((r, c))
        return sm.value(a[0], a[2]) if a else sm.value(r, c)

    cols: list[AnnexCol] = []
    serial_col = None
    for c in range(sm.ncols):
        main = anchor_value(header_top, c).strip()
        a_main = anchors.get((header_top, c))
        sub = ""
        for r in range(header_top + 1, data_start):
            a = anchors.get((r, c))
            if a and a_main and a == a_main:
                continue
            v = (sm.value(a[0], a[2]) if a else sm.value(r, c)).strip()
            if v and (not a or a[0] == r):
                sub = v
                break
        if not main and not sub:
            continue
        kind = "tag" if c == tag_col else ("serial" if _n(main) in _SERIAL_HEADERS and serial_col is None else "data")
        if kind == "serial":
            serial_col = c
        label = re.sub(r"\s+", " ", main) + (f" · {sub}" if sub else "")
        cols.append(AnnexCol(c, re.sub(r"\s+", " ", main), sub, label, kind, sm.col_widths.get(c, 9) < 1))
    # the template's data block: rows under the header that carry data or the table's borders
    def bordered(r):
        b = sm.style(r, tag_col).get("border", {})
        return any(b.get(k) for k in ("top", "bottom", "left", "right"))
    block_end = data_start
    while block_end < sm.nrows and (any(sm.value(block_end, c) for c in range(sm.ncols)) or bordered(block_end)):
        if any(_n(sm.value(block_end, c)).startswith("note") for c in range(min(sm.ncols, 3))):
            break
        block_end += 1
    if block_end == data_start:
        block_end = data_start + 1
    return AnnexureSpec(sm.name, header_top, data_start, block_end, cols, tag_col, serial_col)


def find_annexure(sheets: dict[str, SheetModel], fields: list[FieldSpec]) -> tuple[Optional[str], list[str]]:
    """The annexure sheet the EG sheet refers to ('REFER ANNEXURE-I'); returns (sheet name, referenced-but-missing names)."""
    refs = referenced_annexures(fields)
    by_key = {_sheet_key(n): n for n in sheets}
    found, missing = None, []
    for ref, _ in refs.most_common():
        name = by_key.get(_sheet_key(ref))
        if name and parse_annexure(sheets[name]) is not None:
            found = found or name
        elif not name:
            missing.append(ref)
    if found is None:                                                   # no explicit reference: any annexure-like sheet
        for n, sm in sheets.items():
            if "annex" in n.lower() and parse_annexure(sm) is not None:
                found = n
                break
    return found, missing


# ── mapping annexure columns -> IODB columns ──────────────────────────────────────────────────────────────────────────
def _sub_token(text: str) -> Optional[str]:
    for t in _n(text).split():
        if t in _SUB:
            return _SUB[t]
    return None


def auto_map(ann: AnnexureSpec, iodb_columns: list[str], threshold: int = 85) -> dict[int, Optional[str]]:
    """Suggest an IODB column for every data column of the annexure. MIN/NOR/MAX must agree; each IODB column is used once."""
    try:
        from rapidfuzz import fuzz
        score = fuzz.token_sort_ratio
    except Exception:                                          # pragma: no cover
        from difflib import SequenceMatcher
        score = lambda a, b: SequenceMatcher(None, a, b).ratio() * 100  # noqa: E731
    pairs = []
    for ac in ann.columns:
        if ac.kind != "data":
            continue
        sub = _sub_token(ac.sub)
        h = _clean(ac.header) + (f" {sub}" if sub else "")
        for col in iodb_columns:
            csub = _sub_token(col)
            if sub != csub:
                continue
            cc = _clean(col)
            if sub:
                cc = " ".join(t if t not in _SUB else _SUB[t] for t in cc.split())
            s = score(h, cc)
            if s >= threshold:
                pairs.append((s, ac.col, col))
    out: dict[int, Optional[str]] = {ac.col: None for ac in ann.columns if ac.kind == "data"}
    used: set[str] = set()
    for s, c, col in sorted(pairs, key=lambda p: -p[0]):
        if out.get(c) is None and col not in used:
            out[c] = col
            used.add(col)
    return out


def _cell(v: Any) -> Any:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


# ── shared context ────────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Context:
    sheets: dict[str, SheetModel]
    datasheet: str
    target: str
    fields: list[FieldSpec]
    df: pd.DataFrame
    tag_col: str
    annexure: Optional[AnnexureSpec]
    missing_refs: list[str]
    full_df: Optional[pd.DataFrame] = None       # set when `df` holds only the eligible instruments of `instrument_type`
    instrument_type: str = ""

    def why(self, tag: str) -> str:
        """Why a selected tag has no row in `df`."""
        if self.full_df is None:
            return "Tag not found in the IODB"
        from . import datasheet_eligibility as DE
        reason = DE.reason_for(self.full_df, tag, self.instrument_type)
        return "Tag not found in the IODB" if reason == DE.NOT_IN_IODB else reason


def restrict_to_eligible(ctx: "Context", instrument_type: str) -> None:
    """Keep only the eligible physical instruments (utils.datasheet_eligibility) in the context used for validation and generation."""
    from . import datasheet_eligibility as DE
    ctx.full_df, ctx.instrument_type = ctx.df, instrument_type or ""
    ctx.df = DE.eligible_frame(ctx.df, ctx.instrument_type)


def load_context(sop_bytes: bytes, sop_filename: str, datasheet_sheet: str, iodb_bytes: bytes,
                 instrument_type: Optional[str] = None) -> Context:
    sheets = read_workbook(sop_bytes, sop_filename)
    if datasheet_sheet not in sheets:
        raise ValueError(f"Sheet '{datasheet_sheet}' not found in SOP workbook.")
    infos = {d.sheet: d for d in list_datasheet_sheets(sheets)}
    info = infos.get(datasheet_sheet)
    target = info.eg_sheet if (info and info.eg_sheet) else datasheet_sheet
    model = sheets.get(target) or sheets[datasheet_sheet]
    fields = parse_field_spec(model, model)
    df, err = _load_iodb_df(iodb_bytes)
    if err:
        raise ValueError(f"Failed to load IODB: {err}")
    tag_col = _find_column(df, IODB_TAG_KEYS)
    if tag_col is None:
        raise ValueError("No 'TAG NO' column found in IODB.")
    ann_name, missing = find_annexure(sheets, fields)
    ann = parse_annexure(sheets[ann_name]) if ann_name else None
    ctx = Context(sheets, datasheet_sheet, target, fields, df, tag_col, ann, missing)
    if instrument_type is not None:
        restrict_to_eligible(ctx, instrument_type)
    return ctx


def annexure_info(sheets: dict[str, SheetModel], datasheet_sheet: str) -> dict:
    """For /datasheets and /fields: does this datasheet support the consolidated format?"""
    infos = {d.sheet: d for d in list_datasheet_sheets(sheets)}
    info = infos.get(datasheet_sheet)
    target = info.eg_sheet if (info and info.eg_sheet) else datasheet_sheet
    model = sheets.get(target) or sheets.get(datasheet_sheet)
    if model is None:
        return {"annexure_sheet": None, "annexure_capacity": 0, "annexure_columns": 0, "missing_annexures": []}
    fields = parse_field_spec(model, model)
    name, missing = find_annexure(sheets, fields)
    ann = parse_annexure(sheets[name]) if name else None
    return {"annexure_sheet": name, "annexure_capacity": ann.capacity if ann else 0, "annexure_columns": len(ann.columns) if ann else 0,
            "missing_annexures": missing}


def _rows_for(ctx: Context, tags: list[str]) -> tuple[dict[str, pd.Series], list[str], dict[str, int]]:
    keyed = ctx.df[ctx.tag_col].astype(str).str.strip()
    rows, missing, dup = {}, [], {}
    for t in tags:
        m = ctx.df[keyed == str(t).strip()]
        if m.empty:
            missing.append(t)
        else:
            rows[t] = m.iloc[0]
            if len(m) > 1:
                dup[t] = len(m)
    return rows, missing, dup


def _unique(tags: list[str]) -> tuple[list[str], list[str]]:
    seen, out, dups = set(), [], []
    for t in tags:
        k = str(t).strip()
        if k in seen:
            dups.append(k)
            continue
        seen.add(k)
        out.append(k)
    return out, dups


def annexure_records(ctx: Context, tags: list[str], mapping: dict[int, Optional[str]], rows: dict[str, pd.Series]) -> list[dict[int, Any]]:
    out = []
    ann = ctx.annexure
    for i, t in enumerate(tags):
        rec: dict[int, Any] = {}
        r = rows.get(t)
        for ac in ann.columns:
            if ac.kind == "tag":
                rec[ac.col] = t
            elif ac.kind == "serial":
                rec[ac.col] = i + 1
            else:
                col = mapping.get(ac.col)
                rec[ac.col] = _cell(r.get(col)) if (r is not None and col) else None
        out.append(rec)
    return out


def resolve_main(fields: list[FieldSpec], overrides: dict[str, list[str]]) -> dict[tuple[int, int], tuple[str, str]]:
    """Main (common) datasheet: predefined fields take the approved override else the EG default; tag-specific fields keep their
    'REFER ANNEXURE' reference (or stay as the template has them)."""
    resolved = {}
    for f in fields:
        ov = override_for(f, overrides)
        for idx, col in enumerate(f.value_cols):
            default = f.defaults[idx] if idx < len(f.defaults) else ""
            if f.source == "predefined":
                val = ov[idx] if (ov and idx < len(ov) and ov[idx] != "") else default
            else:
                val = default
            resolved[(f.row, col)] = (val, f.source)
    return resolved


def normalize_mapping(ann: AnnexureSpec, iodb_columns: list[str], user: Optional[dict]) -> dict[int, Optional[str]]:
    auto = auto_map(ann, iodb_columns)
    if not user:
        return auto
    out = dict(auto)
    for k, v in user.items():
        try:
            c = int(k)
        except (TypeError, ValueError):
            continue
        if c in out:
            out[c] = v if (v and v in iodb_columns) else None
    return out


# ── validation ───────────────────────────────────────────────────────────────────────────────────────────────────────
def validate(ctx: Context, fmt: str, tags_in: list[str], overrides: dict[str, list[str]], user_mapping: Optional[dict] = None) -> dict:
    issues: list[dict] = []

    def add(sev, code, msg, **kw):
        issues.append({"severity": sev, "code": code, "message": msg, **kw})

    if fmt not in FORMATS:
        add("ERROR", "INVALID_FORMAT", f"Unknown datasheet generation format '{fmt}'. Use {', '.join(FORMATS)}.")
        return {"format": fmt, "issues": issues, "counts": _counts(issues)}
    tags, dups = _unique(tags_in)
    if not tags:
        add("ERROR", "NO_TAGS", "No tags selected.")
    for d in sorted(set(dups)):
        add("ERROR", "DUPLICATE_TAG", f"Tag {d} is selected more than once.", tag=d)
    rows, missing, iodb_dup = _rows_for(ctx, tags)
    for t in missing:
        reason = ctx.why(t)
        if reason == "Tag not found in the IODB":
            add("ERROR", "TAG_NOT_IN_IODB", f"Tag {t} is not in the IODB.", tag=t)
        else:
            add("ERROR", "INELIGIBLE_TAG", f"Tag {t} cannot have a datasheet: {reason}.", tag=t)
    for t, n in iodb_dup.items():
        add("REVIEW", "IODB_DUPLICATE_ROWS", f"Tag {t} appears in {n} IODB rows - the first row is used.", tag=t)
    # mandatory fields (red, no EG default) must have an approved value
    for f in ctx.fields:
        if f.mandatory:
            ov = [v for v in (override_for(f, overrides) or []) if str(v).strip()]
            if not ov:
                add("ERROR", "MISSING_MANDATORY", f"'{f.label}' ({f.section}) is mandatory and has no value.", field=f.label)
    # a common specification that the IODB shows differently per tag
    pre = [f for f in ctx.fields if f.source == "predefined"]
    if pre and rows:
        try:
            from rapidfuzz import fuzz
            same = lambda a, b: fuzz.token_sort_ratio(a, b) >= 90          # noqa: E731  (whole-label match only)
        except Exception:                                                  # pragma: no cover
            same = lambda a, b: a == b                                     # noqa: E731
        cols = [(str(c), _clean(c)) for c in ctx.df.columns]
        for f in pre:
            lab = _clean(f.label)
            col = next((c for c, cc in cols if lab and same(lab, cc)), None)
            if not col:
                continue
            vals = sorted({str(_cell(r.get(col))) for r in rows.values() if _cell(r.get(col)) is not None})
            if len(vals) > 1:
                used = (override_for(f, overrides) or [None])[0] or (f.defaults[0] if f.defaults else "")
                add("REVIEW", "COMMON_SPEC_DIFFERS",
                    f"'{f.label}' is a common specification, but the IODB column '{col}' differs between tags ({', '.join(vals[:5])}). "
                    f"The datasheet will show '{used}' for all tags - confirm or split the package.", field=f.label)

    result: dict[str, Any] = {"format": fmt, "tags": tags}
    iodb_cols = [str(c) for c in ctx.df.columns]
    if fmt == CONSOLIDATED:
        if ctx.annexure is None:
            add("ERROR", "NO_ANNEXURE_TEMPLATE",
                f"The SOP workbook has no tag-wise annexure for '{ctx.datasheet}'. Upload the consolidated SOP workbook whose datasheet refers to "
                f"an annexure sheet (e.g. 'REFER ANNEXURE-I') with a TAG NO column, or choose 'Individual Datasheet for Each Tag'.")
        else:
            ann = ctx.annexure
            mapping = normalize_mapping(ann, iodb_cols, user_mapping)
            recs = annexure_records(ctx, [t for t in tags if t in rows], mapping, rows)
            unmapped = [ac.label for ac in ann.columns if ac.kind == "data" and not mapping.get(ac.col)]
            if unmapped:
                add("REVIEW", "UNMAPPED_COLUMN", f"{len(unmapped)} annexure column(s) have no IODB source and will stay blank: {', '.join(unmapped)}.")
            for ac in ann.columns:
                if ac.kind != "data" or not mapping.get(ac.col):
                    continue
                blank = [t for t, rec in zip([t for t in tags if t in rows], recs) if rec.get(ac.col) is None]
                if blank:
                    add("REVIEW", "MISSING_TAG_DATA", f"'{ac.label}' is blank in the IODB for {len(blank)} tag(s): {', '.join(blank[:8])}{' …' if len(blank) > 8 else ''}.", field=ac.label)
            for ref in ctx.missing_refs:
                add("REVIEW", "MISSING_ANNEXURE_SHEET", f"The datasheet refers to {ref}, which is not in the workbook - those rows keep the reference text.")
            result["annexure"] = {
                "sheet": ann.sheet, "capacity": ann.capacity, "rows": len(recs),
                "columns": [{**asdict(ac), "iodb_column": mapping.get(ac.col) if ac.kind == "data" else None} for ac in ann.columns],
                "preview": [{str(k): v for k, v in r.items()} for r in recs[:10]],
            }
    else:
        # individual: tag-specific fields that will still show their placeholder
        colmap = _build_iodb_colmap(ctx.df, ctx.fields)
        unresolved: dict[str, list[str]] = {}
        for t, r in rows.items():
            res = _resolve_values_for_tag(ctx.fields, overrides, r, colmap, t)
            for f in ctx.fields:
                if f.source != "iodb":
                    continue
                if any(_PLACEHOLDER_RE.search(str(res.get((f.row, c), ("", ""))[0] or "")) for c in f.value_cols):
                    unresolved.setdefault(f.label, []).append(t)
        for lab, ts in unresolved.items():
            add("REVIEW", "UNRESOLVED_PLACEHOLDER", f"'{lab}' keeps its 'REFER ANNEXURE' text in {len(ts)} datasheet(s) - no IODB column or value.", field=lab)
    result["iodb_columns"] = iodb_cols
    result["issues"] = issues
    result["counts"] = _counts(issues)
    return result


def _counts(issues):
    c = Counter(i["severity"] for i in issues)
    return {"ERROR": c.get("ERROR", 0), "REVIEW": c.get("REVIEW", 0)}


# ── generation: consolidated ──────────────────────────────────────────────────────────────────────────────────────────
def _write_annexure_from_model(ws, sm: SheetModel, ann: AnnexureSpec, recs: list[dict[int, Any]]) -> None:
    """Rebuild the annexure (from a parsed .xls model) with len(recs) data rows - header and footer kept, styles copied."""
    from openpyxl.utils import get_column_letter
    n = len(recs)
    rows_out = max(n, ann.capacity)
    extra = rows_out - ann.capacity
    tmpl_last = ann.block_end - 1

    def put(r_out, c, value, r_src):
        cell = ws.cell(row=r_out + 1, column=c + 1)
        cell.value = value
        rgb = sm.fill(r_src, c)
        _apply_cell_style(cell, sm.style(r_src, c), ("%02X%02X%02X" % rgb) if rgb else None)

    for c, w in sm.col_widths.items():
        ws.column_dimensions[get_column_letter(c + 1)].width = w
    # header (and anything above it)
    for (r, c) in set(sm.values) | set(sm.styles):
        if r < ann.data_start:
            put(r, c, sm.value(r, c) or None, r)
        elif r >= ann.block_end:
            put(r + extra, c, sm.value(r, c) or None, r)
    for r, h in sm.row_heights.items():
        if r < ann.data_start:
            ws.row_dimensions[r + 1].height = h
        elif r >= ann.block_end:
            ws.row_dimensions[r + 1 + extra].height = h
    # data rows
    ncols = max([c for (_, c) in sm.styles] + [ac.col for ac in ann.columns] + [0]) + 1
    for i in range(rows_out):
        src = min(ann.data_start + i, tmpl_last)
        rec = recs[i] if i < n else {}
        for c in range(ncols):
            if (src, c) in sm.styles or c in rec:
                put(ann.data_start + i, c, rec.get(c), src)
        if src in sm.row_heights:
            ws.row_dimensions[ann.data_start + i + 1].height = sm.row_heights[src]
    # merges: header as is, single-row data merges per row, footer shifted
    for (rlo, rhi, clo, chi) in sm.merged:
        try:
            if rhi <= ann.data_start:
                ws.merge_cells(start_row=rlo + 1, start_column=clo + 1, end_row=rhi, end_column=chi)
            elif rlo >= ann.block_end:
                ws.merge_cells(start_row=rlo + 1 + extra, start_column=clo + 1, end_row=rhi + extra, end_column=chi)
            elif rhi - rlo == 1 and rlo == ann.data_start:
                for i in range(rows_out):
                    ws.merge_cells(start_row=ann.data_start + i + 1, start_column=clo + 1, end_row=ann.data_start + i + 1, end_column=chi)
        except Exception:
            pass
    _print_setup(ws, ann, rows_out, ncols, keep_existing=False)


def _print_setup(ws, ann: AnnexureSpec, rows_out: int, ncols: int, keep_existing: bool) -> None:
    from openpyxl.utils import get_column_letter
    last_row = max(ws.max_row, ann.data_start + rows_out)
    if not keep_existing or not ws.print_title_rows:
        ws.print_title_rows = f"{ann.header_top + 1}:{ann.data_start}"          # repeat the column header on every page
    area = f"A1:{get_column_letter(max(ncols, 1))}{last_row}"
    if not keep_existing or not ws.print_area:
        ws.print_area = area
    else:
        try:
            cur = ws.print_area if isinstance(ws.print_area, str) else ",".join(ws.print_area)
            m = re.search(r"\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)", cur.split("!")[-1])
            if m and int(m.group(4)) < last_row:
                ws.print_area = f"{m.group(1)}{m.group(2)}:{m.group(3)}{last_row}"
        except Exception:
            ws.print_area = area
    if not keep_existing:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True


def _expand_annexure_inplace(ws, ann: AnnexureSpec, recs: list[dict[int, Any]]) -> None:
    """Fill an .xlsx annexure in place, inserting formatted rows when there are more tags than template rows."""
    from openpyxl.cell.cell import MergedCell
    from openpyxl.utils import get_column_letter
    n = len(recs)
    rows_out = max(n, ann.capacity)
    extra = rows_out - ann.capacity
    first = ann.data_start + 1                     # 1-based
    tmpl_last = ann.block_end                      # 1-based last template data row
    max_col = max(ws.max_column, max(ac.col for ac in ann.columns) + 1)
    if extra:
        footer_start = tmpl_last + 1
        footer_merges = [mr for mr in list(ws.merged_cells.ranges) if mr.min_row >= footer_start]
        for mr in footer_merges:
            ws.unmerge_cells(str(mr))
        if ws.max_row >= footer_start:
            heights = {r: ws.row_dimensions[r].height for r in range(footer_start, ws.max_row + 1)}
            ws.move_range(f"A{footer_start}:{get_column_letter(max_col)}{ws.max_row}", rows=extra, translate=True)
            for r, h in sorted(heights.items(), reverse=True):
                ws.row_dimensions[r + extra].height = h
                ws.row_dimensions[r].height = None
        for mr in footer_merges:
            ws.merge_cells(start_row=mr.min_row + extra, start_column=mr.min_col, end_row=mr.max_row + extra, end_column=mr.max_col)
        row_merges = [mr for mr in ws.merged_cells.ranges if mr.min_row == mr.max_row == tmpl_last]
        for i in range(extra):
            r = tmpl_last + 1 + i
            for c in range(1, max_col + 1):
                src = ws.cell(row=tmpl_last, column=c)
                dst = ws.cell(row=r, column=c)
                if src.has_style:
                    dst._style = copy(src._style)
            ws.row_dimensions[r].height = ws.row_dimensions[tmpl_last].height
            for mr in row_merges:
                ws.merge_cells(start_row=r, start_column=mr.min_col, end_row=r, end_column=mr.max_col)
    for i in range(rows_out):
        rec = recs[i] if i < n else {}
        for ac in ann.columns:
            cell = ws.cell(row=first + i, column=ac.col + 1)
            if isinstance(cell, MergedCell):
                continue
            cell.value = rec.get(ac.col)
    _print_setup(ws, ann, rows_out, max_col, keep_existing=True)


def generate_consolidated(sop_bytes: bytes, sop_filename: str, datasheet_sheet: str, iodb_bytes: bytes, instrument_type: str,
                          selected_tags: list[str], overrides: Optional[dict] = None, user_mapping: Optional[dict] = None
                          ) -> tuple[Optional[bytes], str, Optional[str], list[dict]]:
    """One workbook: main datasheet (common specifications) + tag-wise annexure. Returns (bytes, filename, error, failed)."""
    overrides = overrides or {}
    try:
        ctx = load_context(sop_bytes, sop_filename, datasheet_sheet, iodb_bytes, instrument_type)
    except Exception as exc:
        return None, "", str(exc), []
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", datasheet_sheet).strip("_") or "DATASHEET"
    filename = f"{safe}_CONSOLIDATED_DATASHEET.xlsx"
    if ctx.annexure is None:
        return None, filename, (f"The SOP workbook has no tag-wise annexure for '{datasheet_sheet}'. Upload the consolidated SOP workbook "
                                f"(datasheet + annexure sheet), or use the individual format."), []
    tags, _ = _unique(selected_tags)
    rows, missing, _ = _rows_for(ctx, tags)
    failed = [{"tag": t, "reason": ctx.why(t)} for t in missing]
    present = [t for t in tags if t in rows]
    if not present:
        return None, filename, "No datasheet generated - none of the selected tags is an eligible physical instrument in the IODB.", failed
    mapping = normalize_mapping(ctx.annexure, [str(c) for c in ctx.df.columns], user_mapping)
    recs = annexure_records(ctx, present, mapping, rows)
    main = resolve_main(ctx.fields, overrides)
    is_xlsx = sop_filename.rsplit(".", 1)[-1].lower() in ("xlsx", "xlsm") if "." in sop_filename else False

    if is_xlsx:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(sop_bytes))                       # a copy in memory - the upload is never changed
        keep = {ctx.target, ctx.annexure.sheet}
        for sn in list(wb.sheetnames):
            if sn not in keep:
                del wb[sn]
        ws = wb[ctx.target]
        for (r, c), (value, _src) in main.items():
            try:
                ws.cell(row=r + 1, column=c + 1).value = value
            except (AttributeError, ValueError):
                pass
        _expand_annexure_inplace(wb[ctx.annexure.sheet], ctx.annexure, recs)
        for w in wb.worksheets:
            w.sheet_state = "visible"
        wb.active = wb.sheetnames.index(ctx.target)
    else:
        wb = build_datasheet_xlsx(ctx.sheets[ctx.target], ctx.fields, main)
        ws_a = wb.create_sheet(ctx.annexure.sheet[:31])
        _write_annexure_from_model(ws_a, ctx.sheets[ctx.annexure.sheet], ctx.annexure, recs)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), filename, None, failed


def generate_package(fmt: str, sop_bytes: bytes, sop_filename: str, datasheet_sheet: str, iodb_bytes: bytes, instrument_type: str,
                     selected_tags: list[str], overrides: Optional[dict] = None, user_mapping: Optional[dict] = None
                     ) -> tuple[Optional[bytes], str, Optional[str], list[dict]]:
    """Single entry point: dispatch to the individual (existing) or consolidated strategy."""
    if fmt == INDIVIDUAL:
        from .sop_datasheet import generate_with_report
        return generate_with_report(sop_bytes, sop_filename, datasheet_sheet, iodb_bytes, instrument_type, selected_tags, overrides)
    if fmt == CONSOLIDATED:
        return generate_consolidated(sop_bytes, sop_filename, datasheet_sheet, iodb_bytes, instrument_type, selected_tags, overrides, user_mapping)
    return None, "", f"Unknown datasheet generation format '{fmt}'.", []
