"""
deliverable_output.py - the finishing steps shared by the Instrument List, I/O List, Cable Schedule, Loop Wiring and
Datasheet deliverables.

    insert_cover(workbook, cover)  the cover sheet becomes the FIRST sheet; a cover sheet the workbook already has
                                   (e.g. the template's COVERSHEET) is REPLACED at its place, so there is never a second
                                   one. Every other sheet is left as the generator wrote it (drawings / header-footer
                                   that openpyxl cannot round-trip are put back from the generator's own output).
    to_pdf(workbook, draft)        the SAME final workbook converted by LibreOffice (every sheet, its own page setup);
                                   a draft gets a "DRAFT" watermark on every page. Nothing is recalculated.

The engineering content is never changed here.
"""
from __future__ import annotations

import io
import math
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import zipfile
from copy import copy
from typing import Optional

import openpyxl
import openpyxl.worksheet.properties
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter, range_boundaries

COVER_SHEET_NAMES = {"coversheet", "cover", "coverpage", "documentcover", "titlesheet"}
DRAFT_TEXT = "DRAFT - NOT APPROVED FOR SUBMISSION"


class PdfUnavailable(Exception):
    """PDF conversion cannot run on this server (LibreOffice is not installed)."""


class PdfFailed(Exception):
    """LibreOffice ran but produced no PDF."""


def _key(name: str) -> str:
    return re.sub(r"[^a-z]", "", (name or "").lower())


def find_cover_sheet(wb) -> Optional[str]:
    return next((n for n in wb.sheetnames if _key(n) in COVER_SHEET_NAMES), None)


def _copy_sheet(src, dst_wb, title: str, index: int):
    """Cross-workbook copy of one sheet: values, formulas, styles, merges, sizes, page setup, print area, pictures."""
    ws = dst_wb.create_sheet(title=title, index=index)
    for row in src.iter_rows():
        for c in row:
            if isinstance(c, openpyxl.cell.cell.MergedCell):
                continue
            d = ws.cell(row=c.row, column=c.column, value=c.value)
            if c.has_style:
                d.font, d.fill, d.border = copy(c.font), copy(c.fill), copy(c.border)
                d.alignment, d.protection, d.number_format = copy(c.alignment), copy(c.protection), c.number_format
    for m in src.merged_cells.ranges:
        ws.merge_cells(str(m))
    for k, dim in src.column_dimensions.items():
        ws.column_dimensions[k].width = dim.width
        ws.column_dimensions[k].hidden = dim.hidden
    for k, dim in src.row_dimensions.items():
        ws.row_dimensions[k].height = dim.height
        ws.row_dimensions[k].hidden = dim.hidden
    for attr in ("orientation", "paperSize", "fitToWidth", "fitToHeight", "scale"):
        try:
            setattr(ws.page_setup, attr, getattr(src.page_setup, attr))
        except Exception:
            pass
    try:
        ws.sheet_properties.pageSetUpPr = copy(src.sheet_properties.pageSetUpPr)
        ws.page_margins = copy(src.page_margins)
        ws.print_options = copy(src.print_options)
        if src.print_area:
            ws.print_area = src.print_area
    except Exception:
        pass
    ws.sheet_view.showGridLines = src.sheet_view.showGridLines
    for img in getattr(src, "_images", []):
        try:
            new = XLImage(io.BytesIO(img._data()))
            new.anchor = copy(img.anchor)
            new.width, new.height = img.width, img.height
            ws.add_image(new)
        except Exception:
            continue
    return ws


def insert_cover(workbook: bytes, cover: bytes, draft: bool = False) -> tuple[bytes, str]:
    """-> (workbook with the cover sheet first / in place of its own cover, the cover sheet's name)."""
    wb = openpyxl.load_workbook(io.BytesIO(workbook))
    existing = find_cover_sheet(wb)
    index = wb.sheetnames.index(existing) if existing else 0
    title = existing or "COVER SHEET"
    others = [n for n in wb.sheetnames if n != existing]
    if existing:
        del wb[existing]
    cw = openpyxl.load_workbook(io.BytesIO(cover))
    ws = _copy_sheet(cw.worksheets[0], wb, title, index)
    if draft:
        ws.oddHeader.center.text = DRAFT_TEXT
        ws.oddHeader.center.size = 14
        ws.oddHeader.center.color = "C00000"
    try:                                            # the sheets' standard header follows the cover that is now in the workbook
        from .cable_schedule_header import reapply_standard_headers
        reapply_standard_headers(wb)
    except Exception:
        pass
    wb.active = index
    for s in wb.worksheets:
        s.sheet_view.tabSelected = s.title == title
    buf = io.BytesIO()
    wb.save(buf)
    out = buf.getvalue()
    from .workbook_assembly import restore_template_fidelity
    return restore_template_fidelity(out, workbook, others), title


def insert_cover_in_zip(package: bytes, cover: bytes, draft: bool = False) -> bytes:
    """A .zip of workbooks (datasheets generated one per tag): every .xlsx member gets the cover sheet."""
    src = zipfile.ZipFile(io.BytesIO(package))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.lower().endswith(".xlsx"):
                data, _ = insert_cover(data, cover, draft)
            out.writestr(info, data)
    return buf.getvalue()


# ── PDF ──────────────────────────────────────────────────────────────────────
def soffice() -> Optional[str]:
    return shutil.which("soffice") or shutil.which("libreoffice") or next(
        (p for p in ("/usr/bin/soffice", "/usr/lib64/libreoffice/program/soffice", "/usr/lib/libreoffice/program/soffice",
                     "/opt/libreoffice/program/soffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice")
         if os.path.exists(p)), None)


_LONG_SHEET_ROWS = 80          # a sheet taller than this is printed over as many pages as it needs
_PAPER_A3, _PAPER_A4, _SMALL_PAPERS = 8, 9, {None, 1, 5}   # Letter / Legal / unset -> A3 or A4


_MIN_SCALE = 0.5


def _print_columns(ws) -> tuple:
    """First and last printed column: the print area if the sheet has one, else the columns that hold data."""
    area = str(ws.print_area or "")
    if area:
        try:
            lo, _, hi, _ = range_boundaries(area.split("!")[-1].split(",")[0].replace("$", ""))
            return lo, hi
        except Exception:
            pass
    used = [c for c in range(1, ws.max_column + 1)
            if any(ws.cell(r, c).value is not None for r in range(1, min(ws.max_row, 40) + 1))]
    return (1, max(used)) if used else (1, 1)


_MIN_COL_WIDTH = 10            # no column is printed cramped; wider ones keep their width
_LINE_PT, _PAD_PT = 14.5, 8    # one wrapped text line / the space above and below it, in points
_MIN_ROW_PT = 18


def _polish_table(ws, first: int, last: int, borders: bool = True) -> None:
    """
    PDF copy only: every cell of the table gets a thin border, wrapped text, vertical centering, a minimum column
    width, and rows tall enough for their wrapped lines (a cell that wraps to two lines gets room for two lines plus
    padding). Row heights are only ever increased, so the template's own spacing is kept.
    """
    from openpyxl.styles import Alignment, Border, Side
    side = Side(style="thin", color="000000")
    top = 1
    hdr = _header_rows(ws) if borders else None
    if hdr:
        top = max(1, int(hdr.split(":")[0]))
    bottom = ws.max_row
    while bottom > top and not any(ws.cell(bottom, c).value is not None for c in range(first, last + 1)):
        bottom -= 1
    for c in range(first, last + 1):
        letter = get_column_letter(c)
        dim = ws.column_dimensions[letter]
        if borders and (dim.width or 8.43) < _MIN_COL_WIDTH and not dim.hidden:
            dim.width = _MIN_COL_WIDTH
    merged = {}
    for m in ws.merged_cells.ranges:
        for r in range(m.min_row, m.max_row + 1):
            for c in range(m.min_col, m.max_col + 1):
                merged[(r, c)] = m
    need = {}                                                  # row -> height needed by its own (unmerged) cells
    for r in range(top, bottom + 1):
        if ws.row_dimensions[r].hidden:
            continue
        for c in range(first, last + 1):
            cell = ws.cell(r, c)
            al = cell.alignment
            if borders:
                try:
                    cell.border = Border(left=side, right=side, top=side, bottom=side)
                except Exception:
                    pass
            if (r, c) in merged and (r, c) != (merged[(r, c)].min_row, merged[(r, c)].min_col):
                continue
            if borders:
                try:
                    cell.alignment = Alignment(horizontal=al.horizontal, vertical="center", wrap_text=True, indent=al.indent, text_rotation=al.text_rotation)
                except Exception:
                    pass
            v = cell.value
            if not isinstance(v, str) or v.startswith("=") or al.text_rotation:
                continue
            m = merged.get((r, c))
            span_w = sum((ws.column_dimensions[get_column_letter(k)].width or 8.43) for k in range(m.min_col, m.max_col + 1)) if m else (ws.column_dimensions[get_column_letter(c)].width or 8.43)
            size = (cell.font.sz or 11) if cell.font else 11
            bold = bool(cell.font and cell.font.b)
            per_line = max(1, int(span_w * (0.80 if bold else 0.88) * (11 / size)))
            wraps = borders or bool(al.wrap_text)
            if not wraps:                                       # a one-line cell that is wider than its column: shrink it
                spills = m is None and (c >= ws.max_column or ws.cell(r, c + 1).value is None)   # text may run into an empty neighbour
                if not spills and len(v) > per_line * 0.8:
                    try:
                        cell.alignment = Alignment(horizontal=al.horizontal, vertical=al.vertical, shrink_to_fit=True, indent=al.indent)
                    except Exception:
                        pass
                continue
            lines = sum(max(1, len(textwrap.wrap(part, per_line, break_long_words=True)) if part.strip() else 1) for part in v.split("\n"))
            h = lines * _LINE_PT * (size / 11) + _PAD_PT
            rows = (m.max_row - m.min_row + 1) if m else 1
            for k in range(rows):
                need[(m.min_row if m else r) + k] = max(need.get((m.min_row if m else r) + k, 0), h / rows)
    for r in range(top, bottom + 1) if borders else ():       # no table row is printed cramped
        if not ws.row_dimensions[r].hidden:
            need[r] = max(need.get(r, 0), _MIN_ROW_PT)
    if borders and hdr:                                       # plain tables: every data row the same height (equal spacing)
        body0 = int(hdr.split(":")[1]) + 1
        if not any(m.max_row >= body0 for m in ws.merged_cells.ranges):
            body = [r for r in range(body0, bottom + 1) if not ws.row_dimensions[r].hidden]
            if body:
                uniform = max(need.get(r, 0) for r in body)
                for r in body:
                    need[r] = uniform
                    ws.row_dimensions[r].height = None        # the uniform height replaces the template's own
    for r, h in need.items():
        cur = ws.row_dimensions[r].height
        if cur is None or cur < h:
            ws.row_dimensions[r].height = h


def _header_rows(ws) -> Optional[str]:
    """The table's column-heading rows (repeated on every printed page): the most text-filled row of the first 20."""
    best, best_n = None, 0
    for r in range(1, min(ws.max_row, 20) + 1):
        n = sum(1 for c in range(1, min(ws.max_column, 80) + 1)
                if isinstance(ws.cell(r, c).value, str) and ws.cell(r, c).value.strip() and not ws.cell(r, c).value.startswith("="))
        if n > best_n:
            best, best_n = r, n
    if not best or best_n < 3:
        return None
    nxt = best + 1
    sub = sum(1 for c in range(1, min(ws.max_column, 80) + 1) if isinstance(ws.cell(nxt, c).value, str) and ws.cell(nxt, c).value.strip())
    merged_down = any(m.min_row == best and m.max_row >= nxt for m in ws.merged_cells.ranges)
    return f"{best}:{nxt if (sub or merged_down) else best}"


def prepare_for_print(workbook: bytes) -> bytes:
    """
    Page setup for the PDF copy only (the Excel deliverable keeps its own): long tables print one page wide over as
    many pages as needed with the column headings repeated - never squeezed onto one unreadable page - and wide tables
    use A3 landscape instead of Letter. Short sheets (cover sheet, a loop drawing) keep their own fit-to-page setup.
    """
    wb = openpyxl.load_workbook(io.BytesIO(workbook))
    cover = find_cover_sheet(wb)
    changed = False
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        ps, props = ws.page_setup, ws.sheet_properties
        if props.pageSetUpPr is None:
            props.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties()
        if ws.title == cover:                                 # a cover sheet is exactly one page
            if ps.paperSize in _SMALL_PAPERS:
                ps.paperSize = _PAPER_A4
            ps.orientation = "portrait"
            props.pageSetUpPr.fitToPage = True
            ps.fitToWidth, ps.fitToHeight = 1, 1
            changed = True
            continue
        if ws.max_row <= _LONG_SHEET_ROWS and ps.fitToWidth == 1 and ps.fitToHeight == 1:
            continue                                          # a form made for exactly one page (datasheet): untouched
        if ws.max_row <= _LONG_SHEET_ROWS and props.pageSetUpPr.fitToPage:
            f0, l0 = _print_columns(ws)                       # a short sheet that already fits its page (loop drawing):
            _polish_table(ws, f0, l0, borders=False)          # keep its layout and borders, only make its text fit
            changed = True
            continue
        first, last = _print_columns(ws)
        cols = last - first + 1
        _polish_table(ws, first, last)
        if ps.paperSize in _SMALL_PAPERS:
            ps.paperSize = _PAPER_A3 if cols > 12 else _PAPER_A4
        landscape = cols > 8
        if landscape:
            ps.orientation = "landscape"
        # Readable text: never shrink below about half size - a very wide table prints 2-4 pages wide instead, with the
        # identifying columns repeated on each page, rather than one page of unreadably small text.
        usable = (1100 if ps.paperSize == _PAPER_A3 else 760) if landscape else 520
        width = sum((ws.column_dimensions[get_column_letter(c)].width or 8.43) for c in range(first, last + 1)) * 5.5
        wide = min(4, max(1, math.ceil(width * _MIN_SCALE / usable)))
        props.pageSetUpPr.fitToPage = True
        ps.fitToWidth, ps.fitToHeight = wide, 0
        if wide > 1 and cols > 6 and not ws.print_title_cols:
            ws.print_title_cols = "A:C"
        if ws.max_row > _LONG_SHEET_ROWS and not ws.print_title_rows:
            rows = _header_rows(ws)
            if rows:
                ws.print_title_rows = rows
        changed = True
    if not changed:
        return workbook
    buf = io.BytesIO()
    wb.save(buf)
    from .workbook_assembly import restore_template_fidelity
    return restore_template_fidelity(buf.getvalue(), workbook, wb.sheetnames)


def to_pdf(workbook: bytes, draft: bool = False, timeout: int = 240) -> bytes:
    """The final workbook as a PDF: every visible sheet in order, printed readably (see prepare_for_print)."""
    workbook = prepare_for_print(workbook)
    exe = soffice()
    if not exe:
        raise PdfUnavailable("PDF conversion is not available on this server: LibreOffice is not installed.")
    with tempfile.TemporaryDirectory(prefix="iez_pdf_") as tmp:
        src = os.path.join(tmp, "deliverable.xlsx")
        with open(src, "wb") as fh:
            fh.write(workbook)
        env = dict(os.environ, HOME=tmp)                      # a private LibreOffice profile per conversion
        try:
            subprocess.run([exe, "--headless", "--norestore", "--nolockcheck", f"-env:UserInstallation=file://{tmp}/profile",
                            "--convert-to", "pdf", "--outdir", tmp, src],
                           capture_output=True, timeout=timeout, env=env, check=False)
        except subprocess.TimeoutExpired as e:
            raise PdfFailed("PDF conversion took too long.") from e
        pdf = os.path.join(tmp, "deliverable.pdf")
        if not os.path.exists(pdf) or os.path.getsize(pdf) == 0:
            raise PdfFailed("LibreOffice did not produce a PDF.")
        with open(pdf, "rb") as fh:
            data = fh.read()
    return watermark(data, DRAFT_TEXT) if draft else data


def to_pdf_zip(package: bytes, draft: bool = False) -> bytes:
    """A .zip of workbooks -> a .zip of the matching PDFs."""
    src = zipfile.ZipFile(io.BytesIO(package))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for info in src.infolist():
            if info.filename.lower().endswith(".xlsx"):
                out.writestr(re.sub(r"\.xlsx$", ".pdf", info.filename, flags=re.I), to_pdf(src.read(info.filename), draft))
    return buf.getvalue()


def watermark(pdf: bytes, text: str) -> bytes:
    """Diagonal semi-transparent text on every page (the page content is not touched)."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.colors import Color
    from reportlab.pdfgen import canvas
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    stamps: dict[tuple[float, float], object] = {}
    for page in writer.pages:
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        if (w, h) not in stamps:
            b = io.BytesIO()
            c = canvas.Canvas(b, pagesize=(w, h))
            from reportlab.pdfbase.pdfmetrics import stringWidth
            import math
            c.setFillColor(Color(0.8, 0, 0, alpha=0.16))
            angle = math.degrees(math.atan2(h, w))
            size = 0.8 * math.hypot(w, h) / stringWidth(text, "Helvetica-Bold", 1)    # fits the page diagonal
            c.setFont("Helvetica-Bold", size)
            c.translate(w / 2, h / 2)
            c.rotate(angle)
            c.drawCentredString(0, -size / 3, text)
            c.save()
            stamps[(w, h)] = PdfReader(io.BytesIO(b.getvalue())).pages[0]
        page.merge_page(stamps[(w, h)])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
