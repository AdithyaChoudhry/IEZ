"""
io_list_builder.py - assembles the standard I/O List document:  cover sheet + TABLE OF CONTENTS + ABBREVIATION + IO_BASIS + IO List + I/O Summary.

IO List and I/O Summary come from the existing generators (utils.generators.generate_io_list). This module adds the standard template, the
linked cover sheet's metadata, the document Location, the IODB-derived IO_BASIS, the print settings, the printed page counts of the TABLE OF
CONTENTS and the combined PDF.

    cover sheet + IODB rows
        pass 1: all sheets written with their print settings (IO List A3 landscape, the rest A4) and rendered sheet by sheet
        pass 2: Shts. / Total / Pages / cover "Page No." written; the sheets that changed are rendered again to confirm the counts
        PDF   : the confirmed sections joined in order - the same pages the counts were read from
"""
from __future__ import annotations

import io
from typing import Callable, Optional

import openpyxl
import pandas as pd

from utils import cable_header_meta as HM
from utils import deliverable_output as DO
from utils.generators import generate_io_list, _apply_column_filters
from utils.file_handler import workbook_to_bytes
from utils.io_list_basis import build_basis
from utils.io_list_document import (ABBR_SHEET, BASIS_SHEET, TOC_SHEET, apply_front_print_setup, fill_front, load_standard_template,
                                    read_cover_meta, toc_rows, write_io_basis)
from utils.io_list_pagination import PaginationUnavailable, combine, page_sizes, render_sections, size_name, visible_sheets
from utils.io_list_print import prepare_cover, set_cover_page_total, store_formula_results
from utils.io_summary import build_io_summary, summary_diagnostics, summary_totals
from utils.workbook_assembly import IO_SUMMARY_SHEET, WITH_SUMMARY, normalize_mode

IO_LIST_SHEET = "IO List"
SECTION_LABELS = {"cover": "Cover Sheet", "toc": "Table of Contents", "abbr": "Abbreviation", "basis": "IO Basis", "iolist": "I/O List",
                  "summary": "I/O Summary"}


def resolve_location(meta: dict, typed: Optional[str]) -> tuple[str, str, list[str]]:
    """
    -> (location, source, warnings). The linked cover sheet's Location is authoritative when it holds one (the same precedence as the Cable
    Schedule header); otherwise the Location typed for this request is used. Nothing else is ever substituted. Raises ValueError for a
    typed placeholder such as TBA.
    """
    from_cover = meta.get("location") or ""
    text = " ".join(str(typed or "").split())
    if text:
        value, why = HM.check_manual("location", text)
        if value is None:
            raise ValueError(f"Location: {why}")
        text = value
    if from_cover:
        warn = []
        if text and text.casefold() != from_cover.casefold():
            warn.append(f"The Location typed ('{text}') was not used: the linked cover sheet states '{from_cover}'. "
                        "Correct the cover sheet if the typed value is the right one.")
        return from_cover, "cover sheet", warn
    if text:
        return text, "entered for this document", []
    return "", "", ["No Location: the linked cover sheet states none and none was entered, so the LOCATION header field is empty."]


def _counts_from(sections: dict) -> dict:
    """Printed pages of each TABLE OF CONTENTS line from the rendered sections (a sheet that is not in the document counts 0)."""
    out = {k: 0 for k in SECTION_LABELS}
    for name, section in sections.items():
        if DO._key(name) in DO.COVER_SHEET_NAMES:
            out["cover"] = section.pages
        elif name == TOC_SHEET:
            out["toc"] = section.pages
        elif name == ABBR_SHEET:
            out["abbr"] = section.pages
        elif name == BASIS_SHEET:
            out["basis"] = section.pages
        elif name == IO_SUMMARY_SHEET:
            out["summary"] = section.pages
        elif name == IO_LIST_SHEET:
            out["iolist"] = section.pages
    return out


def _check_sizes(order: list, sections: dict) -> tuple[list, list]:
    """(per-section page report, problems): the IO List must be A3 landscape, every other sheet A4 portrait."""
    report, problems = [], []
    for name in order:
        found = sorted({size_name(*s) for s in sections[name].sizes})
        want = "A3 landscape" if name == IO_LIST_SHEET else "A4 portrait"
        report.append({"sheet": name, "pages": sections[name].pages, "size": ", ".join(found), "expected": want})
        if found != [want]:
            problems.append(f"{name} was rendered as {', '.join(found) or 'no page'} instead of {want}.")
    return report, problems


def build_io_list_document(df: pd.DataFrame, selected_columns: list, filters: Optional[dict] = None, output_mode: str = "WITHOUT_SUMMARY",
                           cover_bytes: Optional[bytes] = None, overrides: Optional[dict] = None, names: Optional[dict] = None,
                           renderer: Callable = render_sections, location: Optional[str] = None):
    """
    -> (final workbook bytes INCLUDING the cover sheet, file name, error, report). report["_pdf"] holds the combined PDF when every page
    count was confirmed; the caller removes it before returning the report to the client.
    """
    mode = normalize_mode(output_mode)
    report = {"warnings": [], "issues": [], "classes": [], "pages": {}, "total_pages": None, "pages_verified": False, "sections": [],
              "basis_stats": {}, "location": {"value": "", "source": ""}, "summary": None, "_pdf": None}
    meta = read_cover_meta(cover_bytes)
    try:
        meta["location"], source, location_warnings = resolve_location(meta, location)
    except ValueError as e:
        return None, None, str(e), report
    report["location"] = {"value": meta["location"], "source": source}
    if cover_bytes is None:
        report["warnings"].append("No linked cover sheet is available: the document fields of the headers and the revision history are empty "
                                  "and the cover sheet is not part of the workbook.")
    report["warnings"] += (meta["warnings"] if cover_bytes else []) + location_warnings

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
    apply_front_print_setup(wb)

    layout: dict = {}
    out_bytes, filename, err = generate_io_list(df, selected_columns, filters=filters, template_wb=wb, output_mode=mode, layout_report=layout)
    if err or not out_bytes:
        return None, None, err or "I/O List generation failed.", report
    if layout.get("font_pt") and layout["font_pt"] < 7:
        report["warnings"].append(f"{layout['columns']} columns on one A3 page width print at about {layout['font_pt']} pt: "
                                  "select fewer columns for larger text.")

    summary_result = build_io_summary(filtered) if mode == WITH_SUMMARY else None
    totals = {}
    if summary_result is not None:
        report["summary"] = summary_diagnostics(filtered, summary_result)
        if report["summary"]["excluded"]:
            report["warnings"].append(report["summary"]["message"])
        totals = summary_totals(summary_result)

    if cover_bytes:
        out_bytes = DO.insert_cover(out_bytes, prepare_cover(cover_bytes))[0]
    base = out_bytes
    with_totals = lambda data: store_formula_results(data, {IO_SUMMARY_SHEET: totals} if totals else {})

    try:
        first = renderer(base)                                  # pass 1: every sheet
        order = visible_sheets(base)
        counts = _counts_from(first)
        for _ in range(3):
            wb = openpyxl.load_workbook(io.BytesIO(base))       # a fresh load per round (a saved openpyxl workbook cannot be saved again with its pictures)
            fill_front(wb, meta, counts, io_title)
            total = sum(counts.values())
            cover_name = DO.find_cover_sheet(wb) if cover_bytes else None
            if cover_name and not set_cover_page_total(wb[cover_name], total):
                report["warnings"].append("The cover sheet has no 'Page No.' field that could be set to the total number of sheets.")
            results = {TOC_SHEET: {toc_rows(wb[TOC_SHEET])["total"]: total}}
            if totals:
                results[IO_SUMMARY_SHEET] = totals
            candidate = store_formula_results(workbook_to_bytes(wb), results)
            small = renderer(candidate, [n for n in order if n != IO_LIST_SHEET])        # the IO List does not depend on the counts
            sections = {**first, **small}
            again = _counts_from(sections)
            out_bytes = candidate
            if again == counts:
                report["pages_verified"] = True
                break
            counts = again
        else:
            report["warnings"].append("The printed page counts did not settle after three renders - please check the TABLE OF CONTENTS.")
    except PaginationUnavailable as e:
        report["warnings"].append(f"Printed page counts (Shts.) were not filled: {e}")
        return with_totals(base), filename, None, report

    report["pages"], report["total_pages"] = counts, sum(counts.values())
    report["sections"], problems = _check_sizes(order, sections)
    report["warnings"] += problems
    for key, name in (("cover", "The cover sheet"), ("toc", "TABLE OF CONTENTS"), ("abbr", "ABBREVIATION"), ("summary", "I/O Summary")):
        if counts[key] > 1:
            report["warnings"].append(f"{name} prints on {counts[key]} pages (normally one): the Shts. value shows the actual count.")
    if report["pages_verified"] and not problems:
        pdf = combine([(n, sections[n]) for n in order])
        if len(page_sizes(pdf)) == report["total_pages"]:
            report["_pdf"] = pdf
        else:
            report["pages_verified"] = False
            report["warnings"].append("The combined PDF does not have the number of pages shown in the TABLE OF CONTENTS.")
    return out_bytes, filename, None, report
