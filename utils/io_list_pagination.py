"""
io_list_pagination.py - printed pages of the I/O List workbook, measured on the RENDERED output (not estimated).

Every worksheet is rendered on its own by LibreOffice, with the print settings saved in the workbook (the same file the user downloads): the
pages of that PDF are the printed pages of that sheet, and the combined PDF is those very sections joined in workbook order - so the TABLE OF
CONTENTS and the PDF cannot disagree. No PDF bookmarks are needed (LibreOffice before 7.4 cannot export them for a workbook).

The PDFs are read and joined with pypdfium2.

If LibreOffice cannot do it, PaginationUnavailable is raised and the caller reports the limitation - it never substitutes a guess.
"""
from __future__ import annotations

import html
import io
import os
import re
import subprocess
import tempfile
import threading
import zipfile
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Optional

from utils import deliverable_output as DO
from utils.workbook_assembly import _sheet_paths

A4_PT, A3_PT = (595.3, 841.9), (841.9, 1190.5)
_PDFIUM = threading.Lock()           # PDFium must not be used by two threads at once


class PaginationUnavailable(Exception):
    pass


@dataclass
class Section:
    pdf: bytes
    sizes: list                      # [(width, height)] in points, one per page

    @property
    def pages(self) -> int:
        return len(self.sizes)


def visible_sheets(workbook: bytes) -> list[str]:
    xml = zipfile.ZipFile(io.BytesIO(workbook)).read("xl/workbook.xml").decode("utf-8")
    out = []
    for tag in re.findall(r"<sheet\b[^>]*/>", xml):
        if not re.search(r'state="(?:hidden|veryHidden)"', tag):
            out.append(html.unescape(re.search(r'name="([^"]*)"', tag).group(1)))
    return out


def _only(workbook: bytes, target: str) -> bytes:
    """
    A copy of the workbook in which only `target` prints: every other sheet is emptied and hidden and its print ranges are removed
    (LibreOffice still prints a hidden sheet that has a print range). The target sheet and its settings are byte for byte unchanged.
    """
    src = zipfile.ZipFile(io.BytesIO(workbook))
    xml = src.read("xl/workbook.xml").decode("utf-8")
    names = [html.unescape(re.search(r'name="([^"]*)"', t).group(1)) for t in re.findall(r"<sheet\b[^>]*/>", xml)]
    if target not in names:
        raise PaginationUnavailable(f"The workbook has no sheet '{target}'.")
    index = names.index(target)

    def show(m):
        tag = re.sub(r'\s*state="[^"]*"', "", m.group(0))
        if html.unescape(re.search(r'name="([^"]*)"', tag).group(1)) != target:
            tag = tag.replace("<sheet", '<sheet state="hidden"', 1)
        return tag

    xml = re.sub(r"<sheet\b[^>]*/>", show, xml)
    xml = re.sub(r'<definedName\b[^>]*localSheetId="(\d+)"[^>]*>[^<]*</definedName>',
                 lambda m: m.group(0) if int(m.group(1)) == index else "", xml)
    xml = xml.replace("<definedNames></definedNames>", "")
    xml = re.sub(r'\s(?:activeTab|firstSheet)="\d+"', "", xml)
    xml = xml.replace("<workbookView", f'<workbookView activeTab="{index}" firstSheet="{index}"', 1)
    replace = {"xl/workbook.xml": xml.encode("utf-8")}
    for name, path in _sheet_paths(src).items():
        if name != target:
            replace[path] = (b'<?xml version="1.0" encoding="UTF-8"?><worksheet '
                             b'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            out.writestr(item.filename, replace.get(item.filename, src.read(item.filename)))
    return buf.getvalue()


def page_sizes(pdf: bytes) -> list:
    """[(width, height)] in points of every page of a PDF."""
    import pypdfium2
    with _PDFIUM:
        doc = pypdfium2.PdfDocument(pdf)
        try:
            return [tuple(float(v) for v in doc.get_page_size(i)) for i in range(len(doc))]
        finally:
            doc.close()


def render_sections(workbook: bytes, sheets: Optional[list] = None, timeout: int = 280, lock=None) -> dict:
    """{sheet name: Section} for the visible sheets of `workbook` (or only `sheets`), all rendered by one LibreOffice run."""
    exe = DO.soffice()
    if not exe:
        raise PaginationUnavailable("LibreOffice is not installed on this server, so the printed page counts could not be measured.")
    try:
        import pypdfium2  # noqa: F401
    except Exception as e:                                       # pragma: no cover
        raise PaginationUnavailable(f"The PDF reader needed to count pages is not available: {e}")
    names = [n for n in visible_sheets(workbook) if sheets is None or n in sheets]
    with tempfile.TemporaryDirectory(prefix="iez_pages_") as tmp:
        files = []
        for i, name in enumerate(names):
            path = os.path.join(tmp, f"section{i}.xlsx")
            with open(path, "wb") as fh:
                fh.write(_only(workbook, name))
            files.append(path)
        env = dict(os.environ, HOME=tmp)
        try:
            with (lock or nullcontext()):                        # one LibreOffice at a time on a small server
                subprocess.run([exe, "--headless", "--norestore", "--nolockcheck", f"-env:UserInstallation=file://{tmp}/profile",
                                "--convert-to", "pdf", "--outdir", tmp, *files], capture_output=True, timeout=timeout, env=env, check=False)
        except subprocess.TimeoutExpired as e:
            raise PaginationUnavailable("Rendering the workbook to count its printed pages took too long.") from e
        out = {}
        for i, name in enumerate(names):
            pdf = os.path.join(tmp, f"section{i}.pdf")
            if not os.path.exists(pdf) or os.path.getsize(pdf) == 0:
                raise PaginationUnavailable(f"LibreOffice did not produce the pages of the sheet '{name}'.")
            with open(pdf, "rb") as fh:
                data = fh.read()
            out[name] = Section(data, page_sizes(data))
    return out


def count_pages(workbook: bytes, timeout: int = 280) -> dict:
    """{sheet name: printed pages} of every visible sheet."""
    return {n: s.pages for n, s in render_sections(workbook, timeout=timeout).items()}


def combine(sections: list) -> bytes:
    """[(sheet name, Section)] in document order -> one PDF; each page keeps its own size."""
    import pypdfium2
    with _PDFIUM:
        out = pypdfium2.PdfDocument.new()
        sources = []
        try:
            for _name, section in sections:
                sources.append(pypdfium2.PdfDocument(section.pdf))
                out.import_pages(sources[-1])
            buf = io.BytesIO()
            out.save(buf)
            return buf.getvalue()
        finally:
            for doc in sources:
                doc.close()
            out.close()


def size_name(width: float, height: float, tolerance: float = 3.0) -> str:
    for paper, (a, b) in (("A4", A4_PT), ("A3", A3_PT)):
        if abs(width - a) <= tolerance and abs(height - b) <= tolerance:
            return f"{paper} portrait"
        if abs(width - b) <= tolerance and abs(height - a) <= tolerance:
            return f"{paper} landscape"
    return f"{width:.0f} x {height:.0f} pt"
