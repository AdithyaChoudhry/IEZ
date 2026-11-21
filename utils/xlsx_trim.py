"""
xlsx_trim.py - drop the empty formatted rows Excel leaves at the bottom of a sheet.

A sheet that was formatted by whole columns, or where a cell was filled down to the end of the sheet, is saved with
every row down to 1,048,576 written out. openpyxl then builds a million rows of cells: the template takes minutes and
gigabytes to open, and the request times out.

The tail is the run of rows at the bottom that hold nothing but styles and/or the SAME one or two values repeated
(e.g. a header such as "Cable Length (M)" filled down a whole column). Those rows are removed, keeping a small margin
of formatted rows below the last real row. Values, formulas, merges and every row above are untouched; a workbook
without such a tail is returned unchanged (same bytes).
"""
from __future__ import annotations

import io
import re
import zipfile

_DIM = re.compile(rb'<dimension ref="([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?"\s*/>')
_ROW = re.compile(rb"<row\b[^>]*?\br=\"(\d+)\"[^>]*?(?:/>|>(.*?)</row>)", re.S)
_HAS_VALUE = re.compile(rb"<v[ >]|<f[ >/]|<is>")
_MERGE = re.compile(rb'<mergeCell ref="[A-Z]+(\d+):[A-Z]+(\d+)"\s*/>')
_MERGES = re.compile(rb'<mergeCells\b[^>]*>(.*?)</mergeCells>', re.S)


_CELL = re.compile(rb'<c\b[^>]*?\br="([A-Z]+)\d+"[^>]*?(?:/>|>(.*?)</c>)', re.S)


def _row_values(body: bytes) -> frozenset:
    """{(column, cell content)} of the cells of one row that hold a value or formula."""
    return frozenset((m.group(1), m.group(2)) for m in _CELL.finditer(body) if m.group(2) and _HAS_VALUE.search(m.group(2)))


def _trim_sheet(xml: bytes, min_rows: int, margin: int) -> bytes | None:
    """The sheet XML without its filled-down / formatted-only tail, or None when there is nothing to trim."""
    dim = _DIM.search(xml, 0, 4000)
    if not dim or int(dim.group(4) or dim.group(2)) < min_rows:
        return None
    sd_start, sd_end = xml.find(b"<sheetData"), xml.find(b"</sheetData>")
    if sd_start < 0 or sd_end < 0:
        return None
    rows = [(int(m.group(1)), m.start(), m.group(2)) for m in _ROW.finditer(xml, sd_start, sd_end)]
    if len(rows) < min_rows:
        return None
    # The bottom-most row with values gives the fill signature (one or two cells, e.g. a header filled down a column).
    # Every row below the data that holds only those same cells is part of the tail.
    noise: frozenset = frozenset()
    for _, _, body in reversed(rows):
        if body and _HAS_VALUE.search(body):
            noise = _row_values(body)
            break
    if len(noise) > 2:                                            # a full row at the bottom is data, not a fill-down
        noise = frozenset()
    last, repeats = 0, 0
    for r, _, body in reversed(rows):
        if body and _HAS_VALUE.search(body):
            v = _row_values(body)
            if v and not v <= noise:
                last = r
                break
            repeats += 1
    if repeats and repeats < 1000:                               # a few repeated values are data, not a fill-down
        last = next(r for r, _, body in reversed(rows) if body and _HAS_VALUE.search(body))
    for m in _MERGE.finditer(xml, sd_end):                       # a merge that starts in the data keeps its full height
        if int(m.group(1)) <= last:
            last = max(last, int(m.group(2)))
    keep = last + margin
    if keep >= rows[-1][0]:
        return None
    cut = next(pos for r, pos, _ in rows if r > keep)
    tail = xml[sd_end:]
    mc = _MERGES.search(tail)
    if mc:                                                       # merges that start in the removed rows go with them
        kept = [m.group(0) for m in _MERGE.finditer(mc.group(1)) if int(m.group(1)) <= keep]
        block = (b'<mergeCells count="%d">' % len(kept) + b"".join(kept) + b"</mergeCells>") if kept else b""
        tail = tail[:mc.start()] + block + tail[mc.end():]
    out = xml[:cut] + tail
    new_last = keep
    ref = dim.group(1) + str(min(int(dim.group(2)), new_last)).encode() + (b":" + dim.group(3) + str(new_last).encode() if dim.group(3) else b"")
    return out[:dim.start()] + b'<dimension ref="' + ref + b'"/>' + out[dim.end():]


def trim_empty_tail(data: bytes, min_rows: int = 5000, margin: int = 50, min_bytes: int = 2_000_000) -> bytes:
    """Workbook bytes with the empty formatted rows below the last used row of each large sheet removed."""
    try:
        zin = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return data
    with zin:
        sheets = [n for n in zin.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
        trimmed: dict[str, bytes] = {}
        for n in sheets:
            if zin.getinfo(n).file_size < min_bytes:               # a sheet of a few thousand rows is cheap to open as is
                continue
            new = _trim_sheet(zin.read(n), min_rows, margin)
            if new is not None:
                trimmed[n] = new
        if not trimmed:
            return data
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                zout.writestr(info, trimmed.get(info.filename, zin.read(info.filename)), compress_type=zipfile.ZIP_DEFLATED)
        return buf.getvalue()
