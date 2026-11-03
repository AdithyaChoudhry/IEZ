"""
Populate an uploaded coversheet template.

    MDL            -> document number, description        (what to generate)
    user input     -> revision, date, prepared/checked/approved by
    template       -> everything else: layout, logos, merges, formulas, protection, print setup

Only cells named by a CONFIRMED mapping are written, and only their value: cell styles, merges,
images, print settings and protection stay exactly as the template has them. The uploaded bytes are
never modified (a new workbook is built from a copy).
"""
from __future__ import annotations

import datetime as _dt
import io
import re
from typing import Optional

import openpyxl

from .coversheet_template_analyzer import (FIELDS, FIELD_LABELS, NUMBER_PARTS, PART_LABELS, Sheet, TemplateError,
                                           _find_table, _rc, detect_date_format)
from .workbook_assembly import restore_template_fidelity


class FillError(Exception):
    """User-facing problem while populating the template."""


# ── date handling ────────────────────────────────────────────────────────────
_DATE_INPUTS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y")


def parse_date(text) -> _dt.date:
    if isinstance(text, _dt.datetime):
        return text.date()
    if isinstance(text, _dt.date):
        return text
    s = str(text or "").strip()
    for fmt in _DATE_INPUTS:
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise FillError(f"'{s}' is not a valid date. Use the date picker or DD.MM.YYYY.")


def format_date(d: _dt.date, pattern: str) -> str:
    """Excel-style pattern (dd.mm.yyyy, dd-mmm-yy, ...) -> text."""
    out = pattern
    for tok, rep in (("yyyy", "%Y"), ("mmmm", "%B"), ("mmm", "%b"), ("yy", "%y"), ("mm", "%m"), ("dd", "%d")):
        out = re.sub(tok, rep, out, flags=re.I)
    out = out.replace("m", "%m") if "%" not in out and "m" in out else out
    return d.strftime(out)


def _date_pattern_for(ws, cell, sh: Sheet, table) -> tuple[str, bool]:
    """(pattern, is_native_date_cell). Learns from the target cell, then from sibling entries in its column."""
    pat = detect_date_format(cell)
    if pat:
        return pat, isinstance(cell.value, (_dt.datetime, _dt.date))
    if table:
        c = cell.column
        for rr in table["entry_rows"]:
            sib = ws.cell(*sh.anchor_of(rr, c))
            pat = detect_date_format(sib)
            if pat:
                return pat, isinstance(sib.value, (_dt.datetime, _dt.date))
    return "dd.mm.yyyy", False


# ── writing ──────────────────────────────────────────────────────────────────
def _writable(ws, sh: Sheet, coord: str):
    r, c = _rc(coord)
    ar, ac = sh.anchor_of(r, c)
    cell = ws.cell(ar, ac)
    if isinstance(cell.value, str) and cell.value.startswith("="):
        raise FillError(f"Cell {cell.coordinate} contains a formula and cannot receive a value. "
                        "Choose a different cell in the field mapping.")
    return cell


def _typed(existing, text: str):
    """Keep numeric cells numeric (so number formats keep working); everything else is text."""
    if isinstance(existing, (int, float)) and not isinstance(existing, bool) and re.fullmatch(r"-?[1-9]\d*|0", text or ""):
        return int(text)
    return text


def confirmed_targets(field_map: dict) -> list[dict]:
    return [t for t in (field_map.get("targets") or []) if t.get("confirmed") and t.get("cell")]


def confirmed_parts(field_map: dict) -> dict:
    return {k: v for k, v in (field_map.get("parts") or {}).items() if v.get("confirmed") and v.get("cell")}


def validate_mapping(mapping: dict, values: dict) -> list[str]:
    """Problems that must stop generation (empty list = fine)."""
    problems = []
    for f in FIELDS:
        fm = (mapping or {}).get(f) or {}
        has_target = bool(confirmed_targets(fm)) or bool(confirmed_parts(fm))
        wanted = bool(str(values.get(f, "") or "").strip())
        if f in ("document_number", "document_description") and not has_target:
            problems.append(f"{FIELD_LABELS[f]}: no confirmed template cell. Review the field mapping.")
        elif wanted and not has_target and not fm.get("skipped"):
            problems.append(f"{FIELD_LABELS[f]}: no confirmed template cell. Confirm or skip this field.")
        elif has_target and f in ("revision", "date", "prepared_by", "checked_by", "approved_by") \
                and not wanted and not fm.get("skipped"):
            problems.append(f"{FIELD_LABELS[f]} is empty. Enter a value or skip this field.")
    return problems


def fill_template(template_bytes: bytes, sheet_name: str, mapping: dict, values: dict,
                  clear_history: bool = True) -> tuple[bytes, list[str]]:
    """-> (xlsx bytes containing the populated coversheet sheet, warnings)."""
    problems = validate_mapping(mapping, values)
    if problems:
        raise FillError(" ".join(problems))
    try:
        wb = openpyxl.load_workbook(io.BytesIO(template_bytes))
    except Exception as exc:
        raise FillError("The uploaded template could not be opened as an Excel workbook.") from exc
    if sheet_name not in wb.sheetnames:
        raise FillError(f"Sheet '{sheet_name}' was not found in the template.")
    ws = wb[sheet_name]
    sh = Sheet(ws)
    table = _find_table(sh)
    warnings: list[str] = []
    written: set[tuple[int, int]] = set()

    def put(cell, value):
        cell.value = value
        written.add((cell.row, cell.column))

    # document number: single cell(s) and/or the Job | Project | Code | Serial boxes
    fm = mapping["document_number"]
    number = str(values.get("document_number", "")).strip()
    if not number:
        raise FillError("The document number is missing - select a document from the MDL.")
    for t in confirmed_targets(fm):
        cell = _writable(ws, sh, t["cell"])
        put(cell, number)
    parts = confirmed_parts(fm)
    if parts:
        from .mdl_parser import split_document_number
        split = split_document_number(number)
        if not split:
            raise FillError(
                f"The document number '{number}' does not follow JOB-PROJECT-CODE-SERIAL, but the template "
                "splits the number over separate boxes. Map the document number to a single cell instead.")
        for key in NUMBER_PARTS:
            if key in parts:
                put(_writable(ws, sh, parts[key]["cell"]), _typed(ws[parts[key]["cell"]].value, split[key]))
        missing = [PART_LABELS[k] for k in NUMBER_PARTS if k not in parts]
        if missing:
            warnings.append("Not written (no confirmed box): " + ", ".join(missing))

    # description
    title = str(values.get("document_description", "")).strip()
    if not title:
        raise FillError("The document description is missing - select a document from the MDL.")
    for t in confirmed_targets(mapping["document_description"]):
        cell = _writable(ws, sh, t["cell"])
        if t.get("mode") == "after_label" and isinstance(cell.value, str):
            lines = cell.value.split("\n")
            keep = [lines[0]]
            for ln in lines[1:]:
                if ln.strip():
                    break
                keep.append(ln)
            put(cell, "\n".join(keep) + title if len(keep) > 1 else lines[0] + "\n" + title)
        else:
            put(cell, title)

    # user-entered fields
    for f in ("revision", "prepared_by", "checked_by", "approved_by"):
        fmap = mapping.get(f) or {}
        val = str(values.get(f, "") or "").strip()
        if fmap.get("skipped") or not val:
            continue
        for t in confirmed_targets(fmap):
            cell = _writable(ws, sh, t["cell"])
            put(cell, _typed(cell.value, val) if f == "revision" else val)

    fmap = mapping.get("date") or {}
    if values.get("date") and not fmap.get("skipped"):
        d = parse_date(values["date"])
        for t in confirmed_targets(fmap):
            cell = _writable(ws, sh, t["cell"])
            pattern, native = _date_pattern_for(ws, cell, sh, table)
            if native:
                cell.value = _dt.datetime(d.year, d.month, d.day)
                if cell.number_format in ("General", "@"):
                    cell.number_format = pattern
                written.add((cell.row, cell.column))
            else:
                put(cell, format_date(d, pattern))

    # the revision history of the template belongs to the template's own document: clear it
    if clear_history and table and table["entry_rows"]:
        target_rows = {r for (r, _c) in written}
        cols = list(table["columns"].values()) + ([table["desc_col"]] if table["desc_col"] else [])
        for rr in table["entry_rows"]:
            if rr in target_rows:
                continue
            for c in cols:
                ar, ac = sh.anchor_of(rr, c)
                cell = ws.cell(ar, ac)
                if cell.value not in (None, "") and not (isinstance(cell.value, str) and cell.value.startswith("=")):
                    cell.value = None
        # description of the new (written) row would still show the old document's text: leave it, it is
        # not one of the fields iEZ fills, but tell the engineer.
        if table["desc_col"]:
            r_new = table["entry_rows"][0]
            old = ws.cell(*sh.anchor_of(r_new, table["desc_col"])).value
            if old:
                warnings.append(f"The revision description '{old}' is a template value and was kept - edit it in the Excel file if needed.")

    # formulas that read cells we changed can only be recalculated by Excel
    changed = {openpyxl.utils.get_column_letter(c) + str(r) for (r, c) in written}
    deps = _formulas_reading(ws, changed)
    if deps:
        warnings.append("Formulas in " + ", ".join(sorted(deps)[:6]) + " depend on filled cells; Excel recalculates them when the file is opened.")

    keep_all = _references_other_sheets(ws)
    if not keep_all:
        for other in list(wb.worksheets):
            if other.title != ws.title:
                wb.remove(other)
        for name in list(wb.defined_names.keys()):
            dn = wb.defined_names[name]
            if dn.attr_text and "!" in dn.attr_text and ws.title not in dn.attr_text:
                del wb.defined_names[name]
    else:
        warnings.append("The coversheet formulas use other sheets, so the whole workbook was kept.")
    wb.active = wb.worksheets.index(ws)
    for s in wb.worksheets:
        s.sheet_view.tabSelected = s.title == ws.title
    wb.calculation.fullCalcOnLoad = True

    buf = io.BytesIO()
    wb.save(buf)
    out = restore_template_fidelity(buf.getvalue(), template_bytes, [ws.title])
    return out, warnings


def _formulas_reading(ws, changed: set[str]) -> set[str]:
    hits = set()
    for row in ws.iter_rows():
        for cl in row:
            v = cl.value
            if isinstance(v, str) and v.startswith("="):
                refs = set(re.findall(r"\$?([A-Z]{1,3})\$?(\d+)", v))
                if any(f"{a}{b}" in changed for a, b in refs):
                    hits.add(cl.coordinate)
    return hits


def _references_other_sheets(ws) -> bool:
    for row in ws.iter_rows():
        for cl in row:
            v = cl.value
            if isinstance(v, str) and v.startswith("=") and "!" in v:
                return True
    return False
