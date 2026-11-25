"""
io_list_pagination.py - printed page counts of the I/O List workbook, measured on the RENDERED output (not estimated).

The workbook is prepared exactly as for the PDF download (utils.deliverable_output.prepare_for_print: long tables one page wide over as many
pages as needed, headings repeated) and rendered by LibreOffice with one PDF bookmark per worksheet; a sheet's pages are the pages from its
bookmark to the next one. If LibreOffice (or the bookmark export) is not available, PaginationUnavailable is raised and the caller reports the
limitation - it never substitutes a guess.
"""
from __future__ import annotations

import io
import os
import subprocess
import tempfile

from utils import deliverable_output as DO


class PaginationUnavailable(Exception):
    pass


_FILTER = 'pdf:calc_pdf_Export:{"ExportBookmarks":{"type":"boolean","value":"true"}}'


def count_pages(workbook: bytes, timeout: int = 280) -> dict:
    """{sheet name: printed pages} of every visible sheet of `workbook`, in the supported (PDF download) rendering configuration."""
    exe = DO.soffice()
    if not exe:
        raise PaginationUnavailable("LibreOffice is not installed on this server, so the printed page counts could not be measured.")
    try:
        from pypdf import PdfReader
    except Exception as e:                                       # pragma: no cover
        raise PaginationUnavailable(f"The PDF reader needed to count pages is not available: {e}")
    prepared = DO.prepare_for_print(workbook)
    with tempfile.TemporaryDirectory(prefix="iez_pages_") as tmp:
        src = os.path.join(tmp, "doc.xlsx")
        with open(src, "wb") as fh:
            fh.write(prepared)
        env = dict(os.environ, HOME=tmp)
        try:
            subprocess.run([exe, "--headless", "--norestore", "--nolockcheck", f"-env:UserInstallation=file://{tmp}/profile",
                            "--convert-to", _FILTER, "--outdir", tmp, src], capture_output=True, timeout=timeout, env=env, check=False)
        except subprocess.TimeoutExpired as e:
            raise PaginationUnavailable("Rendering the workbook to count its printed pages took too long.") from e
        pdf = os.path.join(tmp, "doc.pdf")
        if not os.path.exists(pdf) or os.path.getsize(pdf) == 0:
            raise PaginationUnavailable("LibreOffice did not produce the PDF used to count the printed pages.")
        reader = PdfReader(pdf)
        total = len(reader.pages)
        marks = []
        for o in reader.outline:
            if isinstance(o, list):
                continue
            try:
                marks.append((str(o.title), reader.get_destination_page_number(o)))
            except Exception:
                continue
    if not marks:
        raise PaginationUnavailable("The rendered PDF has no sheet bookmarks, so the pages of each sheet could not be told apart.")
    out = {}
    for i, (name, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else total
        out[name] = max(0, end - start)
    return out
