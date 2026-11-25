"""
io_list_document.py - the standard I/O List workbook (TABLE OF CONTENTS, ABBREVIATION, IO_BASIS, IO List, IO Summary + the linked cover sheet).

    load_standard_template()   a fresh in-memory copy of the stored master template (the master file is never written)
    read_cover_meta(bytes)     project / client / document number / revision / date / signatories / revision history of the linked cover sheet
    write_io_basis(ws, result) the IO_BASIS table from utils.io_list_basis (merged equipment and I/O-type cells, five headings only)
    fill_front(wb, meta, counts, ...)  universal headers, TABLE OF CONTENTS rows / total / revision history

The I/O List and I/O Summary sheets are produced by the existing generators and are not touched here.
"""
from __future__ import annotations

import io
import math
import re
from copy import copy
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Alignment, Border, Side
from openpyxl.worksheet.cell_range import CellRange

from utils.io_list_header import fill_header

STANDARD_TEMPLATE = Path(__file__).resolve().parent.parent / "backend" / "app" / "templates" / "io_list" / "IO_List_Standard_Template.xlsx"
TOC_SHEET, ABBR_SHEET, BASIS_SHEET = "TABLE OF CONTENTS", "ABBREVIATION", "IO_BASIS"
_THIN = Side(style="thin", color="000000")
_MED = Side(style="medium", color="000000")


def load_standard_template() -> openpyxl.Workbook:
    """An independent workbook instance per request: the master template bytes are read, never opened for writing."""
    return openpyxl.load_workbook(io.BytesIO(STANDARD_TEMPLATE.read_bytes()))


# ───────────────────────────── the linked cover sheet ─────────────────────────────
def _t(v: Any) -> str:
    if isinstance(v, (datetime, date)):
        return v.strftime("%d.%m.%Y")
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def _k(v: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _t(v).lower())


def _anchor(ws, cell):
    if isinstance(cell, MergedCell):
        for m in ws.merged_cells.ranges:
            if cell.coordinate in m:
                return ws.cell(m.min_row, m.min_col)
    return cell


def _cells(ws):
    for row in ws.iter_rows():
        for c in row:
            if not isinstance(c, MergedCell) and c.value not in (None, ""):
                yield c


def read_cover_meta(cover_bytes: Optional[bytes]) -> dict:
    """
    What the header / TOC need from the centralised cover sheet, found by the cover's labels. Nothing is guessed: a missing value stays
    empty and is listed in `warnings`. The cover sheet carries no LOCATION, so location is always empty (reported).
    """
    meta = {"project": "", "client": "", "location": "", "doc_no": "", "rev": "", "date": "", "prepared": "", "checked": "", "approved": "",
            "doc_title": "", "revisions": [], "warnings": []}
    if not cover_bytes:
        return meta
    ws = openpyxl.load_workbook(io.BytesIO(cover_bytes), data_only=True).worksheets[0]
    cells = list(_cells(ws))

    def find(label, row=None):
        return next((c for c in cells if _k(c.value) == label and (row is None or c.row == row)), None)

    def below(c):
        return _t(_anchor(ws, ws.cell(c.row + 1, c.column)).value) if c else ""

    def right(c):
        if not c:
            return ""
        colon = False
        for cc in range(c.column + 1, min(ws.max_column, c.column + 14) + 1):
            cell = ws.cell(c.row, cc)
            if isinstance(cell, MergedCell):
                continue
            if _t(cell.value) in (":", "-"):
                colon = True
                continue
            if cell.value not in (None, ""):
                return _t(cell.value)
        return ""

    job = find("jobno")
    meta["project"] = _t(_anchor(ws, ws.cell(job.row, 1)).value) if job else ""
    meta["client"] = right(find("client"))
    pr = find("project", job.row if job else None)
    project_no, code, serial = below(pr), below(find("doccode", job.row if job else None)), below(find("serialno", job.row if job else None))
    parts = [p for p in (project_no, code, serial) if p]
    meta["doc_no"] = "-".join(parts)
    if len(parts) < 3:
        meta["warnings"].append("The cover sheet's document number is incomplete (Project / Doc. Code / Serial No.): the header shows what it holds.")
    rev_l = next((c for c in cells if _k(c.value) in ("rev", "revno") and (job is None or c.row == job.row)), None)
    meta["rev"] = below(rev_l)
    for c in cells:                                           # document title: text after the label, or the cell under it
        if _k(c.value).startswith("documenttitle"):
            rest = _t(re.sub(r"(?i)document\s*title", "", str(c.value), count=1))
            if not rest:
                for r in range(c.row + 1, c.row + 4):
                    v = _t(_anchor(ws, ws.cell(r, c.column)).value)
                    if v and _k(v) not in ("stampingarea", "documentclass", "discipline"):
                        rest = v
                        break
            meta["doc_title"] = rest
            break
    # revision table: header row (REV / DATE / DESCRIPTION / PREPARED / CHECKED / APPROVED), its rows are above it, newest first
    hdr = None
    for c in cells:
        if _k(c.value) == "rev":
            found = {}
            for x in cells:
                if x.row == c.row:
                    for s in ("date", "description", "prepared", "checked", "approved"):
                        if _k(x.value).startswith(s) and s not in found:
                            found[s] = x.column
            if {"date", "prepared", "checked", "approved"} <= set(found):
                hdr = (c.row, c.column, found)
                break
    if hdr:
        hrow, rcol, cols = hdr
        disc = find("discipline")
        first = (disc.row + 1) if disc and disc.row < hrow else max(1, hrow - 8)
        for r in range(first, hrow):
            rv = _t(ws.cell(r, rcol).value)
            if not rv:
                continue
            g = lambda s: _t(ws.cell(r, cols[s]).value) if s in cols else ""
            meta["revisions"].append({"rev": rv, "date": g("date"), "description": g("description"), "prepared": g("prepared"),
                                      "checked": g("checked"), "approved": g("approved")})
    else:
        meta["warnings"].append("The cover sheet's revision table was not found: date, signatories and revision history are empty.")
    cur = next((x for x in meta["revisions"] if x["rev"] == meta["rev"]), None) or (meta["revisions"][0] if meta["revisions"] else None)
    if cur:
        if not meta["rev"]:
            meta["rev"] = cur["rev"]
        meta["date"], meta["prepared"], meta["checked"], meta["approved"] = cur["date"], cur["prepared"], cur["checked"], cur["approved"]
        if cur["rev"] != meta["rev"]:
            meta["warnings"].append(f"Revision {meta['rev']} is not in the cover's revision table: the date is that of revision {cur['rev']}.")
    for key, label in (("project", "project name"), ("client", "client")):
        if not meta[key]:
            meta["warnings"].append(f"The cover sheet has no {label}: the header field is left empty.")
    meta["warnings"].append("The cover sheet carries no location: the LOCATION header field is left empty.")
    return meta


# ───────────────────────────── IO_BASIS ─────────────────────────────
def _style_of(ws, row: int, cols=range(1, 12)) -> dict:
    return {c: copy(ws.cell(row, c)._style) for c in cols}


def _lines(text: str, width_units: float) -> int:
    per = max(8, int(width_units * 1.05))
    return max(1, sum(max(1, math.ceil(len(p) / per)) for p in str(text).split("\n")))


def write_io_basis(ws, result) -> dict:
    """Write the IO_BASIS data area (from row 10) and the note box below it. Returns {"rows": n, "last_row": r, "merged": n}."""
    proto = _style_of(ws, 10)
    note = {(r, c): (ws.cell(r, c).value, copy(ws.cell(r, c)._style)) for r in range(12, 15) for c in range(1, 12)}
    for m in [m for m in ws.merged_cells.ranges if m.min_row >= 10]:
        ws.unmerge_cells(str(m))
    for r in range(10, ws.max_row + 1):
        for c in range(1, 12):
            cell = ws.cell(r, c)
            cell.value = None
            cell._style = copy(ws.cell(500, c)._style)
        ws.row_dimensions[r].height = None
    widths = {c: float(ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width or 8.43) for c in range(1, 12)}
    w_equip, w_desc = widths[3] + widths[4], sum(widths[c] for c in (6, 7, 8, 9))
    r, n_merge = 10, 0
    for si, cls in enumerate(result.classes, 1):
        rows = cls.rows or [("", "")]
        r0 = r
        for idx, (io_t, desc) in enumerate(rows):
            for c in range(1, 12):
                ws.cell(r, c)._style = copy(proto[c])
            ws.cell(r, 2).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.cell(r, 5).value = io_t or None
            ws.cell(r, 6).value = desc or None
            ws.merge_cells(start_row=r, start_column=6, end_row=r, end_column=9)           # description
            ws.merge_cells(start_row=r, start_column=10, end_row=r, end_column=11)         # remark (blank unless a verified remark exists)
            n_merge += 2
            ws.row_dimensions[r].height = max(23.4, 14.5 * _lines(desc, w_desc) + 8)
            r += 1
        r1 = r - 1
        ws.cell(r0, 1).value, ws.cell(r0, 2).value, ws.cell(r0, 3).value = si, cls.type_label, cls.equipment
        ws.merge_cells(start_row=r0, start_column=3, end_row=r1, end_column=4)             # equipment (also horizontal for a single row)
        n_merge += 1
        if r1 > r0:
            ws.merge_cells(start_row=r0, start_column=1, end_row=r1, end_column=1)
            ws.merge_cells(start_row=r0, start_column=2, end_row=r1, end_column=2)
            n_merge += 2
        need = 14.5 * _lines(cls.equipment, w_equip) + 8                                    # the equipment text must fit its merged cell
        have = sum(ws.row_dimensions[x].height or 23.4 for x in range(r0, r1 + 1))
        if need > have:
            ws.row_dimensions[r1].height = (ws.row_dimensions[r1].height or 23.4) + (need - have)
        # I/O type: one merged cell per run of the same type inside this equipment
        runs, a = [], r0
        while a <= r1:
            b = a
            while b < r1 and ws.cell(b + 1, 5).value == ws.cell(a, 5).value:
                b += 1
            runs.append((a, b))
            if b > a:
                ws.merge_cells(start_row=a, start_column=5, end_row=b, end_column=5)
                n_merge += 1
            a = b + 1
        _frame_group(ws, r0, r1, runs)
    last = r - 1
    # the note box under the table
    nr = last + 2
    for (rr, cc), (v, st) in note.items():
        cell = ws.cell(nr + rr - 12, cc)
        cell.value, cell._style = v, copy(st)
    ws.merge_cells(start_row=nr, start_column=2, end_row=nr + 2, end_column=11)
    ws.print_area = f"A1:K{nr + 2}"
    return {"rows": last - 9, "last_row": nr + 2, "merged": n_merge, "table_end": last}


def _frame_group(ws, r0: int, r1: int, io_runs: list) -> None:
    """Row lines between signal rows stay; inside a merged cell (equipment level: SI.NO / TYPE / EQUIPMENT, and each I/O-type run) there are
    no lines - only the outline of the merged cell is drawn."""
    def outline(c, a, b):
        for rr in range(a, b + 1):
            bd = ws.cell(rr, c).border
            ws.cell(rr, c).border = Border(left=bd.left, right=bd.right, top=_THIN if rr == a else Side(style=None),
                                           bottom=_THIN if rr == b else Side(style=None))
    for c in (1, 2, 3, 4):
        outline(c, r0, r1)
    for a, b in io_runs:
        outline(5, a, b)


# ───────────────────────────── front sheets ─────────────────────────────
def _find_row(ws, col: int, pred) -> Optional[int]:
    for r in range(1, ws.max_row + 1):
        v = ws.cell(r, col).value
        if v is not None and pred(_t(v).upper()):
            return r
    return None


def _shift_down(ws, at: int, k: int) -> None:
    """Insert k rows at row `at` copying the formats of the row that was there (values, styles, merges, heights)."""
    last = ws.max_row
    heights = {r: ws.row_dimensions[r].height for r in range(at, last + 1)}
    merges = [CellRange(str(m)) for m in ws.merged_cells.ranges if m.min_row >= at]
    for m in merges:
        ws.unmerge_cells(str(m))
    maxc = max(ws.max_column, 15)
    for r in range(last, at - 1, -1):
        for c in range(1, maxc + 1):
            s, d = ws.cell(r, c), ws.cell(r + k, c)
            d.value, d._style = s.value, copy(s._style)
    for r in range(at, last + 1):
        ws.row_dimensions[r + k].height = heights[r]
    for m in merges:
        ws.merge_cells(start_row=m.min_row + k, start_column=m.min_col, end_row=m.max_row + k, end_column=m.max_col)
    for i in range(k):                                        # the new rows look like the first old data row
        for c in range(1, maxc + 1):
            ws.cell(at + i, c)._style = copy(ws.cell(at + k, c)._style)
            ws.cell(at + i, c).value = None
        ws.row_dimensions[at + i].height = heights[at]
        for m in merges:
            if m.min_row == at:
                ws.merge_cells(start_row=at + i, start_column=m.min_col, end_row=at + i, end_column=m.max_col)


def fill_front(wb, meta: dict, counts: dict, io_list_title: str = "") -> dict:
    """
    Header fields of the three front sheets, the TABLE OF CONTENTS rows (Shts.), the total (a real SUM) and the revision history.
    `counts`: {"cover": n, "toc": n, "abbr": n, "basis": n, "iolist": n, "summary": n} - printed pages measured from the rendered
    workbook; a missing key leaves that Shts. cell empty (never an estimate). Returns {"missing_fields": {...}}.
    """
    out = {"missing_fields": {}}
    for name, key in ((TOC_SHEET, "toc"), (ABBR_SHEET, "abbr"), (BASIS_SHEET, "basis")):
        ws = wb[name]
        m = dict(meta)
        m["pages"] = counts.get(key)
        miss = fill_header(ws, m)
        if miss:
            out["missing_fields"][name] = miss
    toc = wb[TOC_SHEET]
    head = _find_row(toc, 1, lambda s: s.startswith("S. NO")) or 8
    rows = dict(zip(("cover", "toc", "abbr", "basis", "iolist", "summary"), range(head + 1, head + 7)))   # the six lines of the template, in order
    if io_list_title and rows["iolist"]:
        toc.cell(rows["iolist"], 2).value = io_list_title
    for key, r in rows.items():
        if r:
            v = counts.get(key)
            toc.cell(r, 15).value = int(v) if v is not None else None
    first, last = min(x for x in rows.values() if x), max(x for x in rows.values() if x)
    tot = _find_row(toc, 2, lambda s: s.startswith("TOTAL"))
    if tot:
        toc.cell(tot, 15).value = f"=SUM(O{first}:O{last})"                 # replaces the worksheet-position formula of the old template
    _fill_revisions(toc, meta.get("revisions") or [])
    return out


def _fill_revisions(toc, revs: list) -> None:
    head = _find_row(toc, 1, lambda s: s == "REV.")
    if not head:
        return
    cap = 4                                                    # data rows of the template table (above its heading row)
    if len(revs) > cap:
        k = len(revs) - cap
        _shift_down(toc, head - cap, k)
        filler = head - cap - 1
        if toc.row_dimensions[filler].height:                  # the blank space above the table gives way: the TOC stays one page
            toc.row_dimensions[filler].height = max(10.0, toc.row_dimensions[filler].height - k * 32.25)
        head += k
        cap = len(revs)
    rows = list(range(head - 1, head - 1 - cap, -1))           # nearest to the heading first = oldest revision
    for r in rows:
        for c in range(1, 16):
            cell = toc.cell(r, c)
            if isinstance(cell, MergedCell):
                continue
            cell.value = None
            if r != rows[0]:
                cell._style = copy(toc.cell(rows[0], c)._style)       # every revision row looks like the one next to the heading
    for r, rev in zip(rows, reversed(revs)):                   # revs are newest-first as on the cover: the oldest goes next to the heading
        for c, key in ((1, "rev"), (2, "description"), (10, "date"), (12, "prepared"), (14, "checked"), (15, "approved")):
            toc.cell(r, c).value = rev.get(key) or None
    area = str(toc.print_area or "")
    m = re.match(r"^'?[^!]*'?!?\$?A\$?1:\$?([A-Z]+)\$?(\d+)$", area.replace("'", ""))
    if m:
        toc.print_area = f"A1:{m.group(1)}{head}"
