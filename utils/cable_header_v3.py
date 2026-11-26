"""
cable_header_v3.py - the approved Cable Schedule header (iEZ_Cable_Schedule_Standard_Header_V3) applied to the generated worksheets.

The approved workbook is stored in backend/app/templates/cable_schedule/Cable_Schedule_Standard_Header_V3.xlsx and is a READ-ONLY master: every
generation parses its own copy (load_template), so nothing a request writes can reach the master or another request.

Rows 1-6 of a worksheet are the document header:
    1  logo | company name + address          2  PROJECT          3  CLIENT | DOCUMENT NO.
    4  PMC | DATE                             5  LOCATION | REVISION          6  <schedule title band>
Only those six rows are replaced (the engineering table below them is never touched). When the worksheet's engineering width equals the width of
the approved header (INST T, MCC DI S, MCC DO T, VFD T, MOV Y, CABLE SUMMARY D) the approved cells, merged ranges, row heights and logo are copied
exactly; for any other width (a user's own template, the LCP sheet) the same arrangement is derived from the nearest approved header and reported.
The company name, address, logo and schedule title always come from the approved header - the values come from the resolved metadata only.
"""
from __future__ import annotations

import math
import re
from copy import copy
from dataclasses import dataclass, field
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.drawing.image import Image
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Border, Side
from openpyxl.utils import get_column_letter

from .cable_header_meta import KEYS, LABELS, is_unresolved

TEMPLATE_PATH = (Path(__file__).resolve().parent.parent / "backend" / "app" / "templates" / "cable_schedule"
                 / "Cable_Schedule_Standard_Header_V3.xlsx")
HEADER_ROWS = 6
SHEET_OF = {"INST": "Cable Schedule -INST", "MCC DI": "MCC DI", "MCC DO": "MCC DO", "VFD": "VFD", "MOV": "MOV", "SUMMARY": "CABLE SUMMARY"}
TITLE_OF = {"LCP": "LCP CABLE SCHEDULE"}                         # sheets the approved header has no worksheet for
_LABEL = re.compile(r"^\s*(PROJECT|CLIENT|DOCUMENT NO\.|PMC|DATE|LOCATION|REVISION)\s*:", re.I)
_FIELD_OF = {"PROJECT": "project", "CLIENT": "client", "DOCUMENT NO.": "doc_no", "PMC": "pmc", "DATE": "date", "LOCATION": "location",
             "REVISION": "revision"}
_THIN = Side(style="thin", color="000000")
_TOP_FIXED = (1, 6)                                              # logo / company row and the title band keep their approved height
_PX = 7.0                                                        # one column-width unit in pixels (Calibri 11)


class TemplateError(Exception):
    """The approved header template is missing, unreadable or incomplete (names the worksheet)."""


class HeaderError(Exception):
    """A header could not be applied to a worksheet (names the worksheet and range)."""


# ── the master ───────────────────────────────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _master_bytes() -> bytes:
    try:
        return TEMPLATE_PATH.read_bytes()
    except OSError as exc:
        raise TemplateError(f"The approved Cable Schedule header template is not available ({TEMPLATE_PATH.name}): {exc}")


def load_template():
    """A fresh, private workbook instance of the approved header template (the stored master is never opened for writing)."""
    try:
        wb = openpyxl.load_workbook(BytesIO(_master_bytes()))
    except TemplateError:
        raise
    except Exception as exc:
        raise TemplateError(f"The approved Cable Schedule header template is not a valid workbook: {exc}")
    problems = validate_template(wb)
    if problems:
        raise TemplateError(" ".join(problems))
    return wb


@dataclass
class Layout:
    sheet: str
    last_col: int
    merges: list                       # ["A1:C1", ...] rows 1-6 only
    anchors: dict                      # field key -> (row, col, label text as written on the approved sheet)
    title: str
    heights: dict                      # row -> pt
    logo: Optional[dict]               # {"col","row","colOff","rowOff","cx","cy"}
    company_col: int = 4
    logo_last_col: int = 3


def _label_text(text: str) -> str:
    return re.split(r"\s*:", str(text), 1)[0].strip()


def read_layout(ws) -> Layout:
    """The header arrangement of one approved worksheet, read from the workbook itself (never hard-coded)."""
    merges = [m for m in ws.merged_cells.ranges if m.max_row <= HEADER_ROWS]
    top = {(m.min_row, m.min_col): m for m in merges}
    logo_m, company_m = top.get((1, 1)), None
    if logo_m is not None:
        company_m = top.get((1, logo_m.max_col + 1))
    if logo_m is None or company_m is None:
        raise TemplateError(f"Approved header template: worksheet '{ws.title}' has no logo / company-name range in row 1.")
    anchors = {}
    for r in range(2, 6):
        for c in range(1, company_m.max_col + 1):
            v = ws.cell(r, c).value
            m = _LABEL.match(v) if isinstance(v, str) else None
            if m:
                anchors[_FIELD_OF[m.group(1).upper()]] = (r, c, _label_text(v))
    missing = [k for k in KEYS if k not in anchors]
    if missing:
        raise TemplateError(f"Approved header template: worksheet '{ws.title}' has no {', '.join(LABELS[k] for k in missing)} field.")
    logo = None
    if ws._images:
        a = ws._images[0].anchor
        try:
            logo = {"col": a._from.col, "row": a._from.row, "colOff": a._from.colOff, "rowOff": a._from.rowOff,
                    "cx": a.ext.width, "cy": a.ext.height}
        except AttributeError:
            logo = None
    return Layout(sheet=ws.title, last_col=company_m.max_col, merges=sorted(str(m) for m in merges), anchors=anchors,
                  title=str(ws.cell(6, 1).value or ""), heights={r: ws.row_dimensions[r].height for r in range(1, HEADER_ROWS + 1)},
                  logo=logo, company_col=company_m.min_col, logo_last_col=logo_m.max_col)


def validate_template(wb) -> list[str]:
    out = []
    for key, name in SHEET_OF.items():
        if name not in wb.sheetnames:
            out.append(f"Approved header template: worksheet '{name}' is missing.")
            continue
        try:
            lay = read_layout(wb[name])
        except TemplateError as exc:
            out.append(str(exc))
            continue
        if lay.logo is None:
            out.append(f"Approved header template: worksheet '{name}' has no company logo.")
        if not lay.title:
            out.append(f"Approved header template: worksheet '{name}' has no schedule title.")
    return out


@dataclass
class Master:
    """One request's private copy of the approved template: its worksheets, their header layouts and their logo pictures (bytes)."""
    wb: object
    layouts: dict
    logos: dict


def load_master() -> Master:
    wb = load_template()
    layouts = {s: read_layout(wb[s]) for s in SHEET_OF.values()}
    logos = {}
    for s in SHEET_OF.values():
        data = wb[s]._images[0]._data()                     # read once: the picture's stream is closed by reading it
        logos[s] = data
    return Master(wb=wb, layouts=layouts, logos=logos)


# ── applying ─────────────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class HeaderResult:
    sheet: str
    kind: str
    mode: str                                   # "approved" (exact copy) | "derived"
    template_sheet: str
    last_col: int
    warnings: list = field(default_factory=list)


def _copy_style(dst, src):
    dst.font = copy(src.font)
    dst.fill = copy(src.fill)
    dst.border = copy(src.border)
    dst.alignment = copy(src.alignment)
    dst.number_format = src.number_format
    dst.protection = copy(src.protection)


def _reset(cell):
    cell.value = None
    cell.style = "Normal"


def _px(ws, c1: int, c2: int) -> float:
    return sum((ws.column_dimensions[get_column_letter(c)].width or 8.43) * _PX + 5 for c in range(c1, c2 + 1))


def _need_pt(text: str, size: float, bold: bool, width_px: float) -> float:
    """Height (pt) a wrapped text needs in a cell of this width - a conservative Arial estimate."""
    per_char = size * 96 / 72 * 0.56 * (1.08 if bold else 1.0)
    usable = max(40.0, width_px - 10)
    lines = sum(max(1, math.ceil(len(part) * per_char / usable)) for part in str(text).split("\n"))
    return lines * size * 1.32 + 6


def _outline(ws, r1, c1, r2, c2):
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            ws.cell(r, c).border = Border(left=_THIN if c == c1 else None, right=_THIN if c == c2 else None,
                                          top=_THIN if r == r1 else None, bottom=_THIN if r == r2 else None)


def _pick_template_sheet(kind: str, n: int, layouts: dict) -> str:
    """The approved worksheet of this kind, else the one whose width is nearest to the engineering width (an exact width wins)."""
    own = SHEET_OF.get(kind)
    if own and layouts[own].last_col == n:
        return own
    exact = [s for s, lay in layouts.items() if lay.last_col == n and s != SHEET_OF["SUMMARY"]]
    if exact:
        return exact[0]
    pool = [s for s in layouts if s != SHEET_OF["SUMMARY"]] if n > 6 else [SHEET_OF["SUMMARY"]]
    return min(pool, key=lambda s: (abs(layouts[s].last_col - n), s != own))


def _clear_header(ws, last_col: int):
    for m in list(ws.merged_cells.ranges):
        if m.min_row <= HEADER_ROWS < m.max_row:
            raise HeaderError(f"{ws.title}: the merged range {m} spans the header and the table; the approved header cannot be placed "
                              f"without moving engineering cells.")
    for m in [m for m in ws.merged_cells.ranges if m.max_row <= HEADER_ROWS]:
        ws.unmerge_cells(str(m))
    for (r, c), cell in list(ws._cells.items()):
        if r <= HEADER_ROWS:
            _reset(cell)


def _remove_header_images(ws):
    def top_row(im) -> int:
        a = im.anchor
        if isinstance(a, str):                                   # an anchor given as a cell reference ("B20")
            from openpyxl.utils.cell import coordinate_to_tuple
            return coordinate_to_tuple(a)[0] - 1
        try:
            return a._from.row
        except AttributeError:
            return 0
    ws._images = [im for im in ws._images if top_row(im) >= HEADER_ROWS]      # only pictures anchored in the header band


def _place_logo(ws, data: bytes, logo: dict, last_logo_col: int, warnings: list):
    img = Image(BytesIO(data))
    cx, cy = logo["cx"], logo["cy"]
    avail = _px(ws, 1, last_logo_col) * 9525 - logo["colOff"] - 4 * 9525        # EMU left in the logo cells right of the offset
    if cx > avail > 0:
        k = avail / cx
        cx, cy = int(cx * k), int(cy * k)
        warnings.append(f"{ws.title}: the logo was scaled to {round(k * 100)}% to stay inside its header cells.")
    img.anchor = OneCellAnchor(_from=AnchorMarker(col=logo["col"], colOff=logo["colOff"], row=logo["row"], rowOff=logo["rowOff"]),
                               ext=XDRPositiveSize2D(int(cx), int(cy)))
    ws.add_image(img)


def _text(label: str, value: str) -> str:
    return f"{label} : {value}"


def apply_header(ws, kind: str, values: dict, master: Master, last_col: int) -> HeaderResult:
    """
    Replace rows 1-6 of `ws` with the approved header and fill it from `values` ({project, client, doc_no, pmc, date, location, revision}).
    `kind`: INST | MCC DI | MCC DO | VFD | MOV | SUMMARY | LCP.   `last_col`: the last column of the engineering table.
    """
    layouts, tpl_wb = master.layouts, master.wb
    unresolved = [LABELS[k] for k in KEYS if is_unresolved(values.get(k))]
    if unresolved:
        raise HeaderError(f"{ws.title}: the header cannot be written - unresolved: {', '.join(unresolved)}.")
    tname = _pick_template_sheet(kind, last_col, layouts)
    lay, tws = layouts[tname], tpl_wb[tname]
    exact = lay.last_col == last_col                                    # the approved cells / merges fit the table width: copy them verbatim
    # a worksheet whose table is deliberately narrower than its approved header: MOV is delivered without the column that only
    # repeated "To (JB)", so the approved arrangement, one column narrower, is its expected header
    narrower = not exact and kind == "MOV" and last_col == layouts[SHEET_OF["MOV"]].last_col - 1
    if narrower:
        tname = SHEET_OF["MOV"]
        lay, tws = layouts[tname], tpl_wb[tname]
    approved = narrower or (exact and kind in SHEET_OF and tname == SHEET_OF[kind])  # this worksheet's own approved header
    res = HeaderResult(sheet=ws.title, kind=kind, mode="approved" if approved else "derived", template_sheet=tname, last_col=last_col)
    if kind not in SHEET_OF:
        res.warnings.append(f"{ws.title}: the approved header template has no {kind} worksheet; the approved arrangement of '{tname}' "
                            f"was applied with the title {TITLE_OF.get(kind, kind + ' CABLE SCHEDULE')}.")
    elif not approved:
        res.warnings.append(f"{ws.title}: the engineering table is {last_col} columns wide but the approved {kind} header is "
                            f"{layouts[SHEET_OF[kind]].last_col} columns wide; the approved arrangement ({tname}) was "
                            f"{'applied as it is' if exact else 'proportioned to the table width'}. Review the template-to-schema difference.")
    _clear_header(ws, last_col)
    _remove_header_images(ws)

    if exact:
        merges = list(lay.merges)
        for r in range(1, HEADER_ROWS + 1):
            for c in range(1, last_col + 1):
                _copy_style(ws.cell(r, c), tws.cell(r, c))
        for rng in merges:
            ws.merge_cells(rng)
        anchors = dict(lay.anchors)
        company = (1, lay.company_col)
        logo_last = lay.logo_last_col
    else:
        n = last_col
        logo_last = 3 if n >= 8 else 2
        company = (1, logo_last + 1)
        if n >= 8:
            tot = sum((ws.column_dimensions[get_column_letter(c)].width or 8.43) for c in range(1, n + 1))
            base_total = sum((tws.column_dimensions[get_column_letter(c)].width or 8.43) for c in range(1, lay.last_col + 1))
            right_first = lay.anchors["doc_no"][1]
            frac = sum((tws.column_dimensions[get_column_letter(c)].width or 8.43) for c in range(1, right_first)) / base_total
            acc, split = 0.0, 4
            for c in range(1, n + 1):
                acc += ws.column_dimensions[get_column_letter(c)].width or 8.43
                if acc >= frac * tot:
                    split = c
                    break
            split = max(4, min(split, n - 3))
        else:
            split = max(1, n // 2)
        merges = [f"A1:{get_column_letter(logo_last)}1", f"{get_column_letter(logo_last + 1)}1:{get_column_letter(n)}1",
                  f"A2:{get_column_letter(n)}2", f"A6:{get_column_letter(n)}6"]
        for r in (3, 4, 5):
            merges += [f"A{r}:{get_column_letter(split)}{r}", f"{get_column_letter(split + 1)}{r}:{get_column_letter(n)}{r}"]
        anchors = {"project": (2, 1, lay.anchors["project"][2])}
        for (k, r, side) in (("client", 3, 0), ("doc_no", 3, 1), ("pmc", 4, 0), ("date", 4, 1), ("location", 5, 0), ("revision", 5, 1)):
            anchors[k] = (r, 1 if side == 0 else split + 1, lay.anchors[k][2])
        for rng in merges:
            ws.merge_cells(rng)
        base = {(1, 1): (1, 1), (1, company[1]): (1, lay.company_col), (6, 1): (6, 1)}
        for k, (r, c, _l) in anchors.items():
            base[(r, c)] = (lay.anchors[k][0], lay.anchors[k][1])
        for (r, c), (br, bc) in base.items():
            _copy_style(ws.cell(r, c), tws.cell(br, bc))
        for rng in merges:
            a, b = rng.split(":")
            ca, cb = ws[a], ws[b]
            _outline(ws, ca.row, ca.column, cb.row, cb.column)

    # values: label wording, company, address and title come from the approved header; the values from the resolved metadata
    for k, (r, c, label) in anchors.items():
        ws.cell(r, c).value = _text(label, str(values[k]).strip())
    ws.cell(*company).value = tws.cell(1, lay.company_col).value
    ws.cell(6, 1).value = (layouts[SHEET_OF[kind]].title if kind in SHEET_OF else TITLE_OF.get(kind, f"{kind} CABLE SCHEDULE"))

    # summary: its four columns keep the approved widths (the address and the document number must fit)
    if kind == "SUMMARY":
        for c in range(1, 5):
            w = tws.column_dimensions[get_column_letter(c)].width
            if w:
                ws.column_dimensions[get_column_letter(c)].width = w
    # row heights: the approved ones; only a metadata row whose wrapped text does not fit grows
    for r in range(1, HEADER_ROWS + 1):
        ws.row_dimensions[r].height = lay.heights[r]
    spans = {}
    for rng in merges:
        a, b = rng.split(":")
        spans[(ws[a].row, ws[a].column)] = ws[b].column
    for k, (r, c, _l) in anchors.items():
        if r in _TOP_FIXED:
            continue
        cell = ws.cell(r, c)
        size = float(cell.font.sz or 10)
        need = _need_pt(str(cell.value), size, bool(cell.font.b), _px(ws, c, spans.get((r, c), c)))
        if need > (ws.row_dimensions[r].height or 15):
            ws.row_dimensions[r].height = round(need, 1)

    # the approved logo: copied from the approved worksheet, scaled only if its cells are narrower than the logo
    if lay.logo:
        _place_logo(ws, master.logos[tname], lay.logo, logo_last, res.warnings)
    return res


def apply_headers(wb, targets: dict, values: dict) -> dict:
    """
    `targets`: {sheet name: (kind, last column)}. One private copy of the approved template is read for the whole call; returns
    {sheet name: HeaderResult}. Raises TemplateError / HeaderError (the caller must not deliver a workbook then).
    """
    master = load_master()
    out = {}
    for name, (kind, last_col) in targets.items():
        out[name] = apply_header(wb[name], kind, values, master, last_col)
    return out


# ── verification ─────────────────────────────────────────────────────────────────────────────────────────────────────
_SIGNATORY = re.compile(r"(?i)\b(prepared|checked|approved)\b\s*(by)?\s*:")


def verify_header(ws, values: dict, expect: Optional[HeaderResult] = None) -> list[str]:
    """Problems of the header on `ws` ([] = fine): every field shows its resolved value, no placeholder / signatory field, one logo."""
    problems = []
    seen = {}
    for r in range(2, 6):
        for c in range(1, (ws.max_column or 1) + 1):
            v = ws.cell(r, c).value
            m = _LABEL.match(v) if isinstance(v, str) else None
            if m:
                seen[_FIELD_OF[m.group(1).upper()]] = (r, c, v)
    for k in KEYS:
        want = str(values.get(k) or "").strip()
        if k not in seen:
            problems.append(f"{ws.title}: the {LABELS[k]} field is missing from the header.")
        elif not seen[k][2].split(":", 1)[1].strip() == want:
            problems.append(f"{ws.title}: {LABELS[k]} shows '{seen[k][2].split(':', 1)[1].strip()}' instead of '{want}'.")
    for r in range(1, HEADER_ROWS + 1):
        for c in range(1, (ws.max_column or 1) + 1):
            v = ws.cell(r, c).value
            if isinstance(v, str):
                if _SIGNATORY.search(v):
                    problems.append(f"{ws.title}: {ws.cell(r, c).coordinate} carries a signatory field ('{v[:30]}'); the Cable Schedule header has none.")
                tail = v.split(":", 1)[1] if _LABEL.match(v) else ""
                if tail and is_unresolved(tail) and tail.strip().upper() != "N/A":
                    problems.append(f"{ws.title}: {ws.cell(r, c).coordinate} still holds a placeholder ('{v[:40]}').")
    n_logo = sum(1 for im in ws._images if getattr(getattr(im.anchor, "_from", None), "row", 99) < HEADER_ROWS)
    if n_logo != 1:
        problems.append(f"{ws.title}: the header has {n_logo} logo pictures (expected 1).")
    for m in ws.merged_cells.ranges:
        if m.min_row <= HEADER_ROWS < m.max_row:
            problems.append(f"{ws.title}: merged range {m} spans the header and the table.")
    return problems


def has_v3_header(ws) -> bool:
    """True when rows 1-6 of `ws` are the approved V3 header: the company line, the seven labelled fields and a schedule title band."""
    try:
        company = any(isinstance(ws.cell(1, c).value, str) and "VA TECH WABAG LIMITED" in ws.cell(1, c).value
                      for c in range(1, min(ws.max_column or 1, 40) + 1))
        fields = set()
        for r in range(2, 6):
            for c in range(1, min(ws.max_column or 1, 40) + 1):
                v = ws.cell(r, c).value
                m = _LABEL.match(v) if isinstance(v, str) else None
                if m:
                    fields.add(_FIELD_OF[m.group(1).upper()])
        title = ws.cell(6, 1).value
        return company and fields == set(KEYS) and isinstance(title, str) and bool(re.search(r"(?i)\b(SCHEDULE|SUMMARY)\s*$", title.strip()))
    except Exception:
        return False
