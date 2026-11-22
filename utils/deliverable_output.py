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
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from copy import copy
from typing import Optional

import openpyxl
from openpyxl.drawing.image import Image as XLImage

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
        if ws.title == cover or ws.sheet_state != "visible" or ws.max_row <= _LONG_SHEET_ROWS:
            continue
        cols = max((c for c in range(1, ws.max_column + 1) if any(ws.cell(r, c).value is not None for r in range(1, min(ws.max_row, 40) + 1))), default=1)
        if ws.page_setup.paperSize in _SMALL_PAPERS:
            ws.page_setup.paperSize = _PAPER_A3 if cols > 12 else _PAPER_A4
        if cols > 8:
            ws.page_setup.orientation = "landscape"
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        if not ws.print_title_rows:
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
