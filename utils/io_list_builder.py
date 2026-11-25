"""
io_list_builder.py - assembles the standard I/O List workbook:  [cover sheet] + TABLE OF CONTENTS + ABBREVIATION + IO_BASIS + IO List + I/O Summary.

IO List and I/O Summary come from the existing generators (utils.generators.generate_io_list), unchanged. This module adds the standard
template, the linked cover sheet's metadata, the IODB-derived IO_BASIS and the measured printed page counts of the TABLE OF CONTENTS.

    cover sheet bytes + IODB rows
        -> header fields + IO_BASIS written into a fresh copy of the stored template
        -> existing I/O List / I/O Summary generation
        -> printed pages measured on the rendered workbook (cover inserted for the measurement)
        -> Shts. / Total / Pages written; the light sheets are re-rendered to confirm the numbers (fixed point, at most 3 rounds)
"""
from __future__ import annotations

import io
from typing import Callable, Optional

import openpyxl
import pandas as pd

from utils import deliverable_output as DO
from utils.generators import generate_io_list, _apply_column_filters
from utils.file_handler import workbook_to_bytes
from utils.io_list_basis import build_basis
from utils.io_list_document import (ABBR_SHEET, BASIS_SHEET, TOC_SHEET, fill_front, load_standard_template, read_cover_meta, write_io_basis)
from utils.io_list_pagination import PaginationUnavailable, count_pages
from utils.workbook_assembly import IO_SUMMARY_SHEET, WITH_SUMMARY, normalize_mode

IO_LIST_SHEET = "IO List"


def _with_cover(workbook: bytes, cover: Optional[bytes]) -> bytes:
    return DO.insert_cover(workbook, cover)[0] if cover else workbook


def _counts_from(pages: dict, cover_present: bool) -> dict:
    """Printed pages of each TABLE OF CONTENTS line from the per-sheet page counts."""
    key = lambda n: DO._key(n)
    out = {"cover": 0, "toc": 0, "abbr": 0, "basis": 0, "iolist": 0, "summary": 0}
    for name, n in pages.items():
        k = key(name)
        if k in DO.COVER_SHEET_NAMES:
            out["cover"] = n
        elif name == TOC_SHEET:
            out["toc"] = n
        elif name == ABBR_SHEET:
            out["abbr"] = n
        elif name == BASIS_SHEET:
            out["basis"] = n
        elif name == IO_SUMMARY_SHEET:
            out["summary"] = n
        elif name.startswith(IO_LIST_SHEET):
            out["iolist"] += n
    return out


def build_io_list_document(df: pd.DataFrame, selected_columns: list, filters: Optional[dict] = None, output_mode: str = "WITHOUT_SUMMARY",
                           cover_bytes: Optional[bytes] = None, overrides: Optional[dict] = None, names: Optional[dict] = None,
                           pager: Callable = count_pages):
    """-> (workbook bytes WITHOUT the cover sheet, file name, error, report). The cover is inserted afterwards by the deliverable step."""
    mode = normalize_mode(output_mode)
    report = {"warnings": [], "issues": [], "classes": [], "pages": {}, "pages_verified": False, "basis_stats": {}}
    meta = read_cover_meta(cover_bytes)
    if cover_bytes is None:
        report["warnings"].append("No linked cover sheet is available: the document fields of the headers and the revision history are empty "
                                  "and the cover sheet is not part of the workbook.")
    report["warnings"] += meta["warnings"] if cover_bytes else []

    filtered = _apply_column_filters(df, filters)
    basis = build_basis(filtered, overrides, names)
    wb = load_standard_template()                              # an independent instance per request; the master file is never written
    if basis.error:
        report["warnings"].append("IO_BASIS was not generated: " + basis.error)
    else:
        write_io_basis(wb[BASIS_SHEET], basis)
    report["classes"], report["issues"], report["basis_stats"] = basis.review_rows(), basis.issues, basis.stats
    io_title = meta["doc_title"].upper() if meta.get("doc_title") else "IO LIST"
    fill_front(wb, meta, {}, io_title)

    out_bytes, filename, err = generate_io_list(df, selected_columns, filters=filters, template_wb=wb, output_mode=mode)
    if err or not out_bytes:
        return None, None, err or "I/O List generation failed.", report

    # printed pages: measured on the rendered workbook (cover inserted, as in the delivered file)
    try:
        counts = _counts_from(pager(_with_cover(out_bytes, cover_bytes)), bool(cover_bytes))
    except PaginationUnavailable as e:
        report["warnings"].append(f"Printed page counts (Shts.) were not filled: {e}")
        return out_bytes, filename, None, report
    base = out_bytes
    for _ in range(3):
        wb = openpyxl.load_workbook(io.BytesIO(base))          # a fresh load per round (a saved openpyxl workbook cannot be saved again with its pictures)
        fill_front(wb, meta, counts, io_title)
        out_bytes = workbook_to_bytes(wb)
        light = openpyxl.load_workbook(io.BytesIO(out_bytes))
        for n in [n for n in light.sheetnames if n.startswith(IO_LIST_SHEET)]:
            del light[n]                                       # the IO List pages do not depend on the TOC: only the front sheets are re-rendered
        try:
            again = _counts_from(pager(_with_cover(workbook_to_bytes(light), cover_bytes)), bool(cover_bytes))
        except PaginationUnavailable as e:
            report["warnings"].append(f"The Shts. counts could not be re-verified: {e}")
            break
        again["iolist"] = counts["iolist"]
        if again == counts:
            report["pages_verified"] = True
            break
        counts = again
    else:
        report["warnings"].append("The printed page counts did not settle after three renders - please check the TABLE OF CONTENTS.")
    report["pages"] = counts
    for key, name in (("toc", "TABLE OF CONTENTS"), ("abbr", "ABBREVIATION"), ("basis", "IO_BASIS")):
        if counts.get(key, 1) > 1:
            report["warnings"].append(f"{name} prints on {counts[key]} pages (normally one): the Shts. value shows the actual count.")
    if cover_bytes and counts.get("cover", 1) != 1:
        report["warnings"].append(f"The cover sheet prints on {counts['cover']} pages (normally one).")
    return out_bytes, filename, None, report
