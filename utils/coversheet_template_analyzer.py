"""
Coversheet template analyser.

Reads an engineer-supplied Excel coversheet and works out, WITHOUT any hard-coded cell
address, where each coversheet field lives:

    document_number, document_description, revision, date,
    prepared_by, checked_by, approved_by

Detection is label driven (text synonyms + the geometry around the label), and every
detected field carries a confidence level:

    high    exact label, unambiguous value cell        -> pre-confirmed
    medium  fuzzy label / structural heuristic          -> must be confirmed by the engineer
    none    nothing found                               -> must be assigned (or skipped) by the engineer

Nothing is ever written to a cell that has not been confirmed (see `coversheet_excel_fill`).

A field may have several targets (e.g. the revision appears both in the ID strip "Rev." box and
in the revision-history table; the title appears in the title block and in the DOCUMENT TITLE box).
"""
from __future__ import annotations

import io
import re
from typing import Optional

import openpyxl
from openpyxl.utils import get_column_letter, range_boundaries

FIELDS = ["document_number", "document_description", "revision", "date",
          "prepared_by", "checked_by", "approved_by"]

FIELD_LABELS = {
    "document_number": "Document Number",
    "document_description": "Document Description / Title",
    "revision": "Revision",
    "date": "Date",
    "prepared_by": "Prepared By",
    "checked_by": "Checked By",
    "approved_by": "Approved By",
}

# Sub-fields of the document number when a template splits it over several boxes.
NUMBER_PARTS = ["job_no", "project_no", "doc_code", "serial_no"]
PART_LABELS = {"job_no": "Job No.", "project_no": "Project", "doc_code": "Doc. Code", "serial_no": "Serial No."}
REQUIRED = ("document_number", "document_description")

# normalised label -> field. Normalisation: lower-case, alphanumerics only, single spaces.
_EXACT = {
    "document number": "document_number", "document no": "document_number", "doc number": "document_number",
    "doc no": "document_number", "drawing number": "document_number", "drawing no": "document_number",
    "dwg no": "document_number", "document no and rev": None,
    "document title": "document_description", "doc title": "document_description",
    "title": "document_description", "document description": "document_description",
    "doc description": "document_description", "description": "document_description",
    "drawing title": "document_description",
    "rev": "revision", "revision": "revision", "rev no": "revision", "revision no": "revision",
    "revision number": "revision",
    "date": "date", "issue date": "date", "date of issue": "date",
    "prepared by": "prepared_by", "prepared": "prepared_by", "prepared by eng": "prepared_by",
    "originator": "prepared_by", "drawn by": "prepared_by", "made by": "prepared_by",
    "checked by": "checked_by", "checked": "checked_by", "reviewed by": "checked_by", "review": "checked_by",
    "approved by": "approved_by", "approved": "approved_by", "approver": "approved_by",
}
_PART_EXACT = {
    "job no": "job_no", "job number": "job_no", "job": "job_no",
    "project": "project_no", "project no": "project_no", "project number": "project_no",
    "doc code": "doc_code", "document code": "doc_code",
    "serial no": "serial_no", "serial number": "serial_no", "serial": "serial_no", "sl no": "serial_no",
}
_FUZZY = [  # (regex on normalised text, field) - used only for medium confidence
    (r"\bdoc(ument)?\b.*\b(no|num|number)\b", "document_number"),
    (r"\b(drawing|dwg)\b.*\b(no|number)\b", "document_number"),
    (r"\btitle\b", "document_description"),
    (r"\bprepared\b", "prepared_by"),
    (r"\bchecked\b", "checked_by"),
    (r"\bapproved\b", "approved_by"),
    (r"^rev\b", "revision"),
    (r"\bdate\b", "date"),
]
_TABLE_FIELDS = {"revision", "date", "prepared_by", "checked_by", "approved_by"}
_DATE_SIGNS = re.compile(r"\d{1,4}[./\-]\d{1,2}[./\-]\d{1,4}")


class TemplateError(Exception):
    """User-facing template problem (message is shown as-is)."""


# ── helpers ──────────────────────────────────────────────────────────────────
def norm(text) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", str(text or "").lower())
    return s.strip()


def _first_line(text) -> str:
    for ln in str(text or "").splitlines():
        if ln.strip():
            return ln.strip()
    return ""


class Sheet:
    """Merge-aware accessor over a worksheet."""

    def __init__(self, ws):
        self.ws = ws
        self.anchor: dict[tuple[int, int], tuple[int, int]] = {}     # any merged cell -> its anchor (r, c)
        self.span: dict[tuple[int, int], tuple[int, int, int, int]] = {}  # anchor -> (r1, c1, r2, c2)
        for rng in ws.merged_cells.ranges:
            c1, r1, c2, r2 = range_boundaries(str(rng))
            self.span[(r1, c1)] = (r1, c1, r2, c2)
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    self.anchor[(r, c)] = (r1, c1)
        self.max_row = min(ws.max_row, 400)
        self.max_col = min(ws.max_column, 60)

    def anchor_of(self, r, c):
        return self.anchor.get((r, c), (r, c))

    def value(self, r, c):
        ar, ac = self.anchor_of(r, c)
        return self.ws.cell(ar, ac).value

    def text(self, r, c) -> str:
        v = self.value(r, c)
        return "" if v is None else str(v)

    def bounds(self, r, c):
        ar, ac = self.anchor_of(r, c)
        return self.span.get((ar, ac), (ar, ac, ar, ac))

    def coord(self, r, c) -> str:
        ar, ac = self.anchor_of(r, c)
        return f"{get_column_letter(ac)}{ar}"

    def is_anchor(self, r, c) -> bool:
        return self.anchor_of(r, c) == (r, c)

    def cells(self):
        """Anchor cells with a text value, in reading order."""
        for r in range(1, self.max_row + 1):
            for c in range(1, self.max_col + 1):
                if not self.is_anchor(r, c):
                    continue
                v = self.ws.cell(r, c).value
                if v not in (None, "") and str(v).strip():
                    yield r, c, v


def pick_sheet(wb, requested: Optional[str] = None):
    """The coversheet sheet: requested name, else the visible sheet with the most field labels."""
    if requested:
        if requested not in wb.sheetnames:
            raise TemplateError(f"Sheet '{requested}' was not found in the uploaded template.")
        return wb[requested]
    visible = [ws for ws in wb.worksheets if ws.sheet_state == "visible"]
    if not visible:
        raise TemplateError("The uploaded template has no visible sheet.")
    best, best_score = visible[0], -1
    for ws in visible:
        sh = Sheet(ws)
        score = 0
        for _, _, v in sh.cells():
            n = norm(_first_line(v))
            if n in _EXACT and _EXACT[n] or n in _PART_EXACT:
                score += 1
        if "cover" in ws.title.lower():
            score += 3
        if score > best_score:
            best, best_score = ws, score
    return best


# ── revision-history table ───────────────────────────────────────────────────
def _find_table(sh: Sheet):
    """
    A header row holding >= 3 of REV / DATE / PREPARED / CHECKED / APPROVED (+ optional DESCRIPTION).
    Returns dict(header_row, columns{field: col}, desc_col, direction, entry_rows[]) or None.
    """
    best = None
    for r in range(1, sh.max_row + 1):
        cols, desc = {}, None
        for c in range(1, sh.max_col + 1):
            if not sh.is_anchor(r, c):
                continue
            n = norm(_first_line(sh.text(r, c)))
            f = _EXACT.get(n)
            if f in _TABLE_FIELDS and f not in cols:
                cols[f] = c
            elif n in ("description", "revision description", "remarks"):
                desc = c
        if len(cols) >= 3 and (best is None or len(cols) > len(best[1])):
            best = (r, cols, desc)
    if not best:
        return None
    hr, cols, desc = best
    anchor_col = cols.get("revision") or min(cols.values())

    def entry_rows(direction):
        rows, r = [], hr + direction
        while 1 <= r <= sh.max_row:
            if not sh.is_anchor(r, anchor_col) and sh.anchor_of(r, anchor_col)[0] != r:
                r += direction            # continuation row of a merged entry
                continue
            # an entry row: its cells in the table columns are empty or look like data (not labels)
            texts = [sh.text(r, c).strip() for c in cols.values()]
            if any(norm(_first_line(t)) in _EXACT and _EXACT[norm(_first_line(t))] for t in texts if t):
                break
            if r != hr + direction and not any(texts) and not _row_inside_table(sh, r, cols):
                break
            rows.append(r)
            r = sh.bounds(r, anchor_col)[0] - 1 if direction == -1 else sh.bounds(r, anchor_col)[2] + 1
            if len(rows) > 40:
                break
        return rows

    up, down = entry_rows(-1), entry_rows(1)
    filled = lambda rows: sum(1 for r in rows if any(sh.text(r, c).strip() for c in cols.values()))
    direction = -1 if (filled(up) >= filled(down) and up) else (1 if down else -1)
    rows = up if direction == -1 else down
    return {"header_row": hr, "columns": cols, "desc_col": desc, "direction": direction, "entry_rows": rows}


def _row_inside_table(sh: Sheet, r, cols) -> bool:
    """A blank row still belongs to the table if its cells are merged/bordered like the table columns."""
    c = min(cols.values())
    cell = sh.ws.cell(*sh.anchor_of(r, c))
    b = cell.border
    return bool(b and (b.left.style or b.top.style or b.bottom.style))


# ── detection ────────────────────────────────────────────────────────────────
def _target(sh: Sheet, r, c, mode="replace", **extra):
    return {"cell": sh.coord(r, c), "mode": mode, "current": sh.text(r, c)[:400], "confirmed": True, **extra}


def _value_cell_for_label(sh: Sheet, r, c):
    """The value cell belonging to a label at (r, c): beside it (skipping ':'), else below. -> (r, c, how) | None."""
    r1, c1, r2, c2 = sh.bounds(r, c)
    cc = c2 + 1
    while cc <= sh.max_col and sh.text(r1, cc).strip() == ":":
        cc = sh.bounds(r1, cc)[3] + 1
    right = sh.anchor_of(r1, cc) if cc <= sh.max_col else None
    below = sh.anchor_of(r2 + 1, c1) if r2 + 1 <= sh.max_row else None
    right_t = sh.text(*right).strip() if right else None
    below_t = sh.text(*below).strip() if below else None
    # "strip" layout: labels in one row, their values directly underneath (ID strip: Job No. | Project | ...)
    if right_t and below_t and _looks_label(right_t) and not _looks_label(below_t):
        return below + ("below",)
    if right and (right_t == "" or not _is_label(right_t)) and not (right_t and below_t == "" and _looks_label(right_t)):
        return right + ("right",)
    if below and (below_t == "" or not _is_label(below_t)):
        return below + ("below",)
    return None


def _looks_label(text) -> bool:
    t = text.strip()
    return len(t) <= 14 and t.endswith((".", ":")) or _is_label(t)


def _is_label(text) -> bool:
    n = norm(_first_line(text))
    return bool(_EXACT.get(n) or n in _PART_EXACT)


def analyze(template_bytes: bytes, sheet_name: Optional[str] = None) -> dict:
    """Structure + field detection for the uploaded template."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(template_bytes))
    except Exception as exc:
        raise TemplateError("The uploaded file is not a readable Excel workbook (.xlsx/.xlsm).") from exc
    ws = pick_sheet(wb, sheet_name)
    sh = Sheet(ws)
    if not any(True for _ in sh.cells()):
        raise TemplateError("The selected sheet is empty - no coversheet content was found.")

    fields: dict[str, dict] = {f: {"targets": [], "confidence": "none", "reason": "No matching label found."}
                               for f in FIELDS}
    parts: dict[str, dict] = {}
    used: set[tuple[int, int]] = set()

    def add(field, tgt, conf, reason):
        d = fields[field]
        if any(t["cell"] == tgt["cell"] for t in d["targets"]):
            return
        d["targets"].append(tgt)
        rank = {"none": 0, "medium": 1, "high": 2}
        if not d["reason"] or d["confidence"] == "none":
            d["reason"] = reason
            d["confidence"] = conf
        elif rank[conf] < rank[d["confidence"]]:
            d["confidence"] = conf
            d["reason"] = reason
        used.add(tuple(sh.anchor_of(*_rc(tgt["cell"]))))

    # 1. revision-history table
    table = _find_table(sh)
    table_cells = set()
    if table:
        hr = table["header_row"]
        for f, col in table["columns"].items():
            table_cells.add(sh.anchor_of(hr, col))
        if table["desc_col"]:
            table_cells.add(sh.anchor_of(hr, table["desc_col"]))
        rows = table["entry_rows"]
        if rows:
            r_new = rows[0]                           # entry nearest the header = newest slot
            for f, col in table["columns"].items():
                add(f, _target(sh, r_new, col, "replace", where="revision table"), "high",
                    f"Column '{sh.text(hr, col).strip().splitlines()[0]}' of the revision table "
                    f"(row {sh.anchor_of(r_new, col)[0]}).")
        else:
            for f, col in table["columns"].items():
                fields[f]["reason"] = "Revision table found but it has no entry row."

    # 2. label cells (outside the table header)
    for r, c, v in sh.cells():
        if (r, c) in table_cells:
            continue
        first = _first_line(v)
        n = norm(first)
        multi = "\n" in str(v).strip()
        field = _EXACT.get(n)
        part = _PART_EXACT.get(n)
        if field:
            rest = str(v).strip()[len(str(v).strip().splitlines()[0]):].strip() if multi else ""
            if field == "document_description" and multi:
                # "DOCUMENT TITLE\n\n...title..." - label and value share a cell; keep the label line
                add(field, _target(sh, r, c, "after_label", label=first), "high",
                    "Label and title share one cell; the label line is kept, the title replaces the rest.")
                continue
            hit = _value_cell_for_label(sh, r, c)
            if not hit:
                continue
            vr, vc, how = hit
            if field == "revision" and vr == r + 1 and part is None:
                pass
            add(field, _target(sh, vr, vc, "replace", label=first, where=f"next to '{first}'"), "high",
                f"Value cell {sh.coord(vr, vc)} is {'beside' if how == 'right' else 'below'} the label '{first}'.")
        elif part:
            hit = _value_cell_for_label(sh, r, c)
            if hit:
                vr, vc, how = hit
                parts[part] = {"cell": sh.coord(vr, vc), "label": first, "current": sh.text(vr, vc)[:80]}
        else:
            for pat, f in _FUZZY:
                if re.search(pat, n):
                    hit = _value_cell_for_label(sh, r, c)
                    if hit and fields[f]["confidence"] != "high":
                        vr, vc, how = hit
                        add(f, _target(sh, vr, vc, "replace", label=first, where=f"next to '{first}'"), "medium",
                            f"Label '{first}' only loosely matches {FIELD_LABELS[f]}.")
                    break

    # 3. document number built from the Job No | Project | Doc. Code | Serial No boxes
    if parts and len(parts) >= 2 and fields["document_number"]["confidence"] == "none":
        fields["document_number"]["confidence"] = "high" if len(parts) == 4 else "medium"
        fields["document_number"]["reason"] = (
            "The document number is composed of separate boxes ("
            + " | ".join(PART_LABELS[p] for p in NUMBER_PARTS if p in parts) + ").")
        fields["document_number"]["parts"] = {p: parts[p] for p in NUMBER_PARTS if p in parts}
        fields["document_number"]["targets"] = []
        if len(parts) != 4:
            fields["document_number"]["reason"] += " Not all four boxes were found - please review."
    elif parts and fields["document_number"]["targets"]:
        fields["document_number"]["parts"] = {p: parts[p] for p in NUMBER_PARTS if p in parts}

    # 4. title block heuristic: biggest text in the top banner that is not a label
    if fields["document_description"]["confidence"] in ("none",) or not _has_banner(fields["document_description"]):
        cand = _banner_title(sh, used, table_cells)
        if cand:
            r, c = cand
            conf = "medium" if fields["document_description"]["confidence"] == "none" else None
            if conf:
                add("document_description", _target(sh, r, c, "replace", where="title banner", confirmed=False), "medium",
                    "Large heading text in the title banner - confirm this is where the title belongs.")
            else:
                d = fields["document_description"]
                d["targets"].append(_target(sh, r, c, "replace", where="title banner", optional=True, confirmed=False))

    # a banner that repeats the title already mapped is the same title shown twice: pre-confirm it
    d = fields["document_description"]
    if d["confidence"] == "high":
        ref = {norm(t["current"]) for t in d["targets"] if t.get("confirmed") and t["current"]}
        for t in d["targets"]:
            if t.get("optional") and t["current"] and (
                    norm(t["current"]) in ref or any(norm(t["current"]) in r or r in norm(t["current"]) for r in ref if len(r) > 8)):
                t["confirmed"] = True
                t["note"] = "Repeats the document title shown elsewhere on the sheet."

    # 5. date format hints
    for f in ("date",):
        for t in fields[f]["targets"]:
            t["date_hint"] = describe_date_format(sh, t["cell"], table)

    # normalise outputs
    for f, d in fields.items():
        d["label"] = FIELD_LABELS[f]
        d["required"] = f in REQUIRED
        d["needs_review"] = d["confidence"] != "high"
        d["confirmed"] = d["confidence"] == "high"
        if d.get("parts"):
            for p in d["parts"].values():
                p["confirmed"] = d["confidence"] == "high"
        if d["confidence"] != "high":
            for t in d["targets"]:
                t["confirmed"] = False

    return {
        "sheet": ws.title,
        "sheets": [s.title for s in wb.worksheets if s.sheet_state == "visible"],
        "dimensions": ws.dimensions,
        "merged_ranges": len(ws.merged_cells.ranges),
        "images": len(getattr(ws, "_images", [])),
        "print_area": ws.print_area or "",
        "orientation": ws.page_setup.orientation or "portrait",
        "paper_size": ws.page_setup.paperSize,
        "protected": bool(ws.protection and ws.protection.sheet),
        "formulas": sum(1 for row in ws.iter_rows() for cl in row if isinstance(cl.value, str) and cl.value.startswith("=")),
        "table": ({"header_row": table["header_row"], "direction": "up" if table["direction"] == -1 else "down",
                   "entry_rows": table["entry_rows"][:6]} if table else None),
        "fields": fields,
    }


def _rc(coord: str) -> tuple[int, int]:
    from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
    col, row = coordinate_from_string(coord)
    return row, column_index_from_string(col)


def _has_banner(d) -> bool:
    return any(t.get("where") == "title banner" for t in d["targets"])


def _banner_title(sh: Sheet, used, table_cells):
    """A wide text-bearing merged cell in the top rows that no label claims."""
    best, best_w = None, 0
    for r in range(1, min(sh.max_row, 3) + 1):
        for c in range(1, sh.max_col + 1):
            if not sh.is_anchor(r, c) or (r, c) in used or (r, c) in table_cells:
                continue
            t = sh.text(r, c).strip()
            if not t or _is_label(_first_line(t)) or len(t) < 8:
                continue
            r1, c1, r2, c2 = sh.bounds(r, c)
            w = c2 - c1 + 1
            if w >= 4 and w > best_w:
                best, best_w = (r, c), w
    return best


def describe_date_format(sh: Sheet, coord: str, table) -> str:
    r, c = _rc(coord)
    cell = sh.ws.cell(*sh.anchor_of(r, c))
    samples = [cell]
    if table:
        col = c
        samples += [sh.ws.cell(*sh.anchor_of(rr, col)) for rr in table["entry_rows"][1:4]]
    for s in samples:
        fmt = detect_date_format(s)
        if fmt:
            return fmt
    return "dd.mm.yyyy"


def detect_date_format(cell) -> Optional[str]:
    """Excel-style pattern of an existing date cell (or text date); None when nothing to learn from."""
    import datetime as _dt
    v = cell.value
    if isinstance(v, (_dt.datetime, _dt.date)):
        return cell.number_format if cell.number_format and cell.number_format != "General" else "dd.mm.yyyy"
    if isinstance(v, str) and _DATE_SIGNS.fullmatch(v.strip()):
        m = re.fullmatch(r"(\d{1,4})([./\-])(\d{1,2})[./\-](\d{1,4})", v.strip())
        a, sep, b, c = m.groups()
        if len(a) == 4:
            return f"yyyy{sep}mm{sep}dd"
        if len(c) == 4 or len(c) == 2:
            return f"dd{sep}mm{sep}{'yyyy' if len(c) == 4 else 'yy'}"
    if cell.number_format and re.search(r"[dmy]", cell.number_format.replace("General", "")) and cell.number_format not in ("@",):
        return cell.number_format
    return None
