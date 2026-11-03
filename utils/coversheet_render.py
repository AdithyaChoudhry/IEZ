"""
Render a populated coversheet for preview and PDF.

One layout model (`sheet_model`) is built from the generated workbook and drives BOTH the browser preview and
the built-in PDF renderer, so what the engineer previews is what the fallback PDF contains. When LibreOffice
(`soffice`) is installed it is preferred for the PDF (it prints the real Excel page setup); the built-in renderer
(reportlab) is the fallback and is also used if LibreOffice fails.
"""
from __future__ import annotations

import base64
import colorsys
import datetime as _dt
import io
import os
import shutil
import subprocess
import tempfile
import threading
from typing import Optional

import openpyxl
from openpyxl.utils import get_column_letter

EMU_PX = 9525
_THEME = ["FFFFFF", "000000", "E7E6E6", "44546A", "4472C4", "ED7D31", "A5A5A5", "FFC000", "5B9BD5", "70AD47"]
_INDEXED = {0: "000000", 1: "FFFFFF", 2: "FF0000", 3: "00FF00", 4: "0000FF", 5: "FFFF00", 6: "FF00FF", 7: "00FFFF",
            8: "000000", 9: "FFFFFF", 64: "000000"}
_SOFFICE_LOCK = threading.Lock()


class RenderError(Exception):
    pass


# ── colours ──────────────────────────────────────────────────────────────────
def _tint(hex6: str, tint: float) -> str:
    r, g, b = (int(hex6[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = l * (1 + tint) if tint < 0 else l * (1 - tint) + tint
    r, g, b = colorsys.hls_to_rgb(h, max(0, min(1, l)), s)
    return "%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def color_hex(col, default: Optional[str] = None) -> Optional[str]:
    if col is None:
        return default
    try:
        if col.type == "rgb" and isinstance(col.rgb, str) and len(col.rgb) in (6, 8):
            return "#" + col.rgb[-6:]
        if col.type == "theme" and col.theme is not None and col.theme < len(_THEME):
            return "#" + _tint(_THEME[col.theme], col.tint or 0)
        if col.type == "indexed" and col.indexed in _INDEXED:
            return "#" + _INDEXED[col.indexed]
    except Exception:
        pass
    return default


# ── geometry ─────────────────────────────────────────────────────────────────
def _col_px(w) -> float:
    return 0.0 if w is None else max(0.0, w * 7 + 5)


def _dims(ws, max_row, max_col):
    dcw = ws.sheet_format.defaultColWidth or ws.sheet_format.baseColWidth and ws.sheet_format.baseColWidth + 0.71 or 8.43
    widths = [_col_px(dcw)] * max_col
    for key, dim in ws.column_dimensions.items():
        lo, hi = (dim.min or 0), (dim.max or 0)
        if not lo:
            from openpyxl.utils import column_index_from_string
            lo = hi = column_index_from_string(key)
        for c in range(lo, min(hi, max_col) + 1):
            widths[c - 1] = 0.0 if dim.hidden else (_col_px(dim.width) if dim.width else widths[c - 1])
    drh = ws.sheet_format.defaultRowHeight or 15
    heights = []
    for r in range(1, max_row + 1):
        d = ws.row_dimensions.get(r)
        heights.append(0.0 if d is not None and d.hidden else ((d.height if d is not None and d.height else drh) * 96 / 72))
    return widths, heights


def _used_range(ws):
    """(min_row, min_col, max_row, max_col) of the print area, else of everything that has content or borders."""
    pa = ws.print_area
    if pa:
        from openpyxl.utils import range_boundaries
        rng = pa.split(",")[0].split("!")[-1].replace("$", "")
        c1, r1, c2, r2 = range_boundaries(rng)
        return r1, c1, r2, c2
    max_r = max_c = 0
    for row in ws.iter_rows(max_row=min(ws.max_row, 400), max_col=min(ws.max_column, 60)):
        for cl in row:
            b = cl.border
            if cl.value not in (None, "") or (b and (b.left.style or b.right.style or b.top.style or b.bottom.style)):
                max_r, max_c = max(max_r, cl.row), max(max_c, cl.column)
    for rng in ws.merged_cells.ranges:
        max_r, max_c = max(max_r, rng.max_row), max(max_c, rng.max_col)
    return 1, 1, max(max_r, 1), max(max_c, 1)


def _display(v, fmt: str) -> str:
    if v is None:
        return ""
    if isinstance(v, (_dt.datetime, _dt.date)):
        f = (fmt or "").lower()
        d = v if isinstance(v, _dt.datetime) else _dt.datetime(v.year, v.month, v.day)
        if f in ("", "general", "mm-dd-yy"):
            return d.strftime("%d.%m.%Y")
        for tok, rep in (("yyyy", "%Y"), ("mmmm", "%B"), ("mmm", "%b"), ("yy", "%y"), ("mm", "%m"), ("dd", "%d")):
            f = f.replace(tok, rep)
        return d.strftime(f) if "%" in f else d.strftime("%d.%m.%Y")
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def sheet_model(xlsx_bytes: bytes, sheet_name: str, fallback_bytes: Optional[bytes] = None) -> dict:
    """Layout model of one sheet in pixel units (96 dpi). `fallback_bytes` supplies cached formula results."""
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    if sheet_name not in wb.sheetnames:
        raise RenderError(f"Sheet '{sheet_name}' is missing from the generated workbook.")
    ws = wb[sheet_name]
    cached = {}
    for src in (fallback_bytes, xlsx_bytes):
        if src:
            try:
                wsv = openpyxl.load_workbook(io.BytesIO(src), data_only=True)[sheet_name]
                for row in wsv.iter_rows():
                    for cl in row:
                        if cl.value is not None:
                            cached[cl.coordinate] = cl.value
            except Exception:
                pass
    r1, c1, r2, c2 = _used_range(ws)
    widths, heights = _dims(ws, r2, c2)
    xs = [0.0]
    for w in widths[c1 - 1:c2]:
        xs.append(xs[-1] + w)
    ys = [0.0]
    for h in heights[r1 - 1:r2]:
        ys.append(ys[-1] + h)

    merged = {}
    covered = set()
    for rng in ws.merged_cells.ranges:
        if rng.max_row < r1 or rng.min_row > r2 or rng.max_col < c1 or rng.min_col > c2:
            continue
        merged[(rng.min_row, rng.min_col)] = (rng.max_row, rng.max_col)
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                if (r, c) != (rng.min_row, rng.min_col):
                    covered.add((r, c))

    cells = []
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            cl = ws.cell(r, c)
            val = cl.value
            if isinstance(val, str) and val.startswith("="):
                val = cached.get(cl.coordinate, "")
            b = cl.border
            fill = cl.fill.fgColor if cl.fill and cl.fill.fill_type == "solid" else None
            sides = {}
            for side in ("left", "right", "top", "bottom"):
                sd = getattr(b, side)
                if sd and sd.style:
                    sides[side[0]] = [sd.style, color_hex(sd.color, "#000000")]
            text = "" if (r, c) in covered else _display(val, cl.number_format)
            if not (text or sides or fill):
                continue
            ar2, ac2 = merged.get((r, c), (r, c))
            f = cl.font
            al = cl.alignment
            cells.append({
                "r": r - r1, "c": c - c1, "rs": ar2 - r + 1, "cs": ac2 - c + 1,
                "t": text, "b": sides,
                "bg": color_hex(fill) if fill is not None else None,
                "f": {"n": f.name or "Calibri", "s": float(f.sz or 11), "b": bool(f.b), "i": bool(f.i),
                      "u": bool(f.u), "c": color_hex(f.color, "#000000")},
                "h": al.horizontal or ("right" if isinstance(val, (int, float)) else "left"),
                "v": al.vertical or "bottom", "w": bool(al.wrap_text), "rot": al.textRotation or 0,
            })

    images = []
    for im in getattr(ws, "_images", []):
        try:
            a = im.anchor
            fr = a._from
            x = xs[min(max(fr.col - (c1 - 1), 0), len(xs) - 1)] + fr.colOff / EMU_PX
            y = ys[min(max(fr.row - (r1 - 1), 0), len(ys) - 1)] + fr.rowOff / EMU_PX
            to = getattr(a, "to", None)
            if to is not None:
                x2 = xs[min(max(to.col - (c1 - 1), 0), len(xs) - 1)] + to.colOff / EMU_PX
                y2 = ys[min(max(to.row - (r1 - 1), 0), len(ys) - 1)] + to.rowOff / EMU_PX
                w, h = x2 - x, y2 - y
            else:
                ext = getattr(a, "ext", None)
                w = (ext.width if ext is not None else im.width * EMU_PX) / EMU_PX
                h = (ext.height if ext is not None else im.height * EMU_PX) / EMU_PX
            data = im._data()
            fmt = (im.format or "png").lower()
            images.append({"x": x, "y": y, "w": w, "h": h, "mime": f"image/{'jpeg' if fmt == 'jpg' else fmt}",
                           "b64": base64.b64encode(data).decode()})
        except Exception:
            continue

    pm = ws.page_margins
    return {
        "sheet": ws.title, "width": xs[-1], "height": ys[-1], "xs": xs, "ys": ys, "cells": cells, "images": images,
        "orientation": ws.page_setup.orientation or ("landscape" if xs[-1] > ys[-1] else "portrait"),
        "orientation_set": bool(ws.page_setup.orientation),
        "margins_in": [pm.left, pm.right, pm.top, pm.bottom],
        "h_centered": bool(ws.print_options.horizontalCentered),
        "v_centered": bool(ws.print_options.verticalCentered),
    }


# ── PDF: built-in renderer ───────────────────────────────────────────────────
def _font_name(name: str, bold: bool, italic: bool) -> str:
    n = (name or "").lower()
    fam = "Times" if "times" in n or "serif" in n or "cambria" in n else "Courier" if "cour" in n or "mono" in n else "Helvetica"
    if fam == "Times":
        return {(0, 0): "Times-Roman", (1, 0): "Times-Bold", (0, 1): "Times-Italic", (1, 1): "Times-BoldItalic"}[(int(bold), int(italic))]
    if fam == "Courier":
        return {(0, 0): "Courier", (1, 0): "Courier-Bold", (0, 1): "Courier-Oblique", (1, 1): "Courier-BoldOblique"}[(int(bold), int(italic))]
    return {(0, 0): "Helvetica", (1, 0): "Helvetica-Bold", (0, 1): "Helvetica-Oblique", (1, 1): "Helvetica-BoldOblique"}[(int(bold), int(italic))]


def _latin(s: str) -> str:
    return s.encode("cp1252", "replace").decode("cp1252")


_LINE_W = {"hair": 0.25, "thin": 0.6, "dotted": 0.6, "dashed": 0.6, "medium": 1.4, "mediumDashed": 1.4,
           "double": 1.2, "thick": 2.2}


def render_pdf_builtin(model: dict) -> bytes:
    try:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader, simpleSplit
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RenderError("PDF generation is unavailable: neither LibreOffice nor the built-in renderer "
                          "(reportlab) is installed on the server.") from exc
    landscape = model["orientation"] == "landscape"
    pw, ph = (A4[1], A4[0]) if landscape else A4
    ml, mr, mt, mb = (m * 72 for m in model["margins_in"])
    avail_w, avail_h = pw - ml - mr, ph - mt - mb
    wpt, hpt = model["width"] * 0.75, model["height"] * 0.75
    if wpt <= 0 or hpt <= 0:
        raise RenderError("The coversheet is empty - nothing to print.")
    scale = min(avail_w / wpt, avail_h / hpt, 1.0)
    ox = ml + ((avail_w - wpt * scale) / 2 if model["h_centered"] else 0)
    oy_top = ph - mt - ((avail_h - hpt * scale) / 2 if model["v_centered"] else 0)

    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=(pw, ph))
    cv.setTitle(model["sheet"])
    xs, ys = model["xs"], model["ys"]

    def X(px):
        return ox + px * 0.75 * scale

    def Y(px):
        return oy_top - px * 0.75 * scale

    def rect(c, r, rs, cs):
        x0, x1 = xs[c], xs[min(c + cs, len(xs) - 1)]
        y0, y1 = ys[r], ys[min(r + rs, len(ys) - 1)]
        return x0, y0, x1, y1

    # fills first, then text, images, borders on top
    for cell in model["cells"]:
        if cell["bg"]:
            x0, y0, x1, y1 = rect(cell["c"], cell["r"], cell["rs"], cell["cs"])
            cv.setFillColor(HexColor(cell["bg"]))
            cv.rect(X(x0), Y(y1), (x1 - x0) * 0.75 * scale, (y1 - y0) * 0.75 * scale, stroke=0, fill=1)
    for cell in model["cells"]:
        if not cell["t"]:
            continue
        x0, y0, x1, y1 = rect(cell["c"], cell["r"], cell["rs"], cell["cs"])
        f = cell["f"]
        size = f["s"] * scale
        fn = _font_name(f["n"], f["b"], f["i"])
        bw, bh = (x1 - x0) * 0.75 * scale, (y1 - y0) * 0.75 * scale
        pad = 2 * scale
        text = _latin(cell["t"])
        lines = []
        for para in text.split("\n"):
            lines += simpleSplit(para, fn, size, max(bw - 2 * pad, 1)) if cell["w"] or "\n" in text else [para]
            if not para:
                lines = lines  # blank line already kept by split
        if not cell["w"]:
            lines = text.split("\n")
        lead = size * 1.15
        total = lead * len(lines)
        cv.saveState()
        p = cv.beginPath()
        p.rect(X(x0), Y(y1), bw, bh)
        cv.clipPath(p, stroke=0, fill=0)
        cv.setFillColor(HexColor(f["c"]))
        cv.setFont(fn, size)
        if cell["rot"] in (90, 180):
            cv.translate(X(x0) + bw / 2, Y(y1) + bh / 2)
            cv.rotate(90)
            tw = stringWidth(lines[0], fn, size) if lines else 0
            cv.drawString(-tw / 2, -size / 3, lines[0] if lines else "")
            cv.restoreState()
            continue
        top = Y(y0)
        if cell["v"] in ("center", "centre"):
            ty = top - (bh - total) / 2 - size * 0.9
        elif cell["v"] == "top":
            ty = top - pad - size * 0.9
        else:
            ty = Y(y1) + pad + total - size * 0.9 - 0.0
        for ln in lines:
            tw = stringWidth(ln, fn, size)
            if cell["h"] in ("center", "centerContinuous"):
                tx = X(x0) + (bw - tw) / 2
            elif cell["h"] == "right":
                tx = X(x1) - pad - tw
            else:
                tx = X(x0) + pad
            cv.drawString(tx, ty, ln)
            if f["u"]:
                cv.line(tx, ty - 1, tx + tw, ty - 1)
            ty -= lead
        cv.restoreState()
    for im in model["images"]:
        try:
            raw = base64.b64decode(im["b64"])
            cv.drawImage(ImageReader(io.BytesIO(raw)), X(im["x"]), Y(im["y"] + im["h"]),
                         im["w"] * 0.75 * scale, im["h"] * 0.75 * scale, mask="auto", preserveAspectRatio=False)
        except Exception:
            continue
    for cell in model["cells"]:
        if not cell["b"]:
            continue
        x0, y0, x1, y1 = rect(cell["c"], cell["r"], cell["rs"], cell["cs"])
        segs = {"l": (x0, y0, x0, y1), "r": (x1, y0, x1, y1), "t": (x0, y0, x1, y0), "b": (x0, y1, x1, y1)}
        for side, (style, col) in cell["b"].items():
            a, b_, c_, d = segs[side]
            cv.setStrokeColor(HexColor(col))
            cv.setLineWidth(_LINE_W.get(style, 0.6) * scale)
            cv.line(X(a), Y(b_), X(c_), Y(d))
    # border sides of merged-range edge cells that are not the anchor
    cv.showPage()
    cv.save()
    return buf.getvalue()


# ── PDF: LibreOffice ─────────────────────────────────────────────────────────
def soffice_path() -> Optional[str]:
    return shutil.which("soffice") or shutil.which("libreoffice") or next(
        (p for p in ("/Applications/LibreOffice.app/Contents/MacOS/soffice", "/usr/bin/soffice", "/opt/libreoffice/program/soffice")
         if os.path.exists(p)), None)


def render_pdf_libreoffice(xlsx_bytes: bytes, sheet_name: str, timeout: int = 90) -> bytes:
    exe = soffice_path()
    if not exe:
        raise RenderError("LibreOffice is not installed.")
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    for ws in wb.worksheets:
        if ws.title != sheet_name:
            ws.sheet_state = "hidden"
    ws = wb[sheet_name]
    wb.active = wb.worksheets.index(ws)
    ws.page_setup.paperSize = 9                       # A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
    with tempfile.TemporaryDirectory(prefix="iez_cs_") as tmp:
        src = os.path.join(tmp, "coversheet.xlsx")
        from .workbook_assembly import restore_template_fidelity
        buf = io.BytesIO()
        wb.save(buf)
        with open(src, "wb") as fh:
            fh.write(restore_template_fidelity(buf.getvalue(), xlsx_bytes, [sheet_name]))
        profile = "file://" + os.path.join(tmp, "profile")
        with _SOFFICE_LOCK:
            try:
                subprocess.run([exe, f"-env:UserInstallation={profile}", "--headless", "--norestore",
                                "--convert-to", "pdf", "--outdir", tmp, src],
                               check=True, capture_output=True, timeout=timeout)
            except (subprocess.SubprocessError, OSError) as exc:
                raise RenderError(f"LibreOffice could not convert the coversheet: {exc}") from exc
        out = os.path.join(tmp, "coversheet.pdf")
        if not os.path.exists(out):
            raise RenderError("LibreOffice did not produce a PDF.")
        with open(out, "rb") as fh:
            return fh.read()


def render_pdf(xlsx_bytes: bytes, sheet_name: str, fallback_bytes: Optional[bytes] = None) -> tuple[bytes, str]:
    """-> (pdf bytes, engine name: 'libreoffice' | 'builtin'). LibreOffice first when present, else the built-in renderer."""
    if soffice_path():
        try:
            return render_pdf_libreoffice(xlsx_bytes, sheet_name), "libreoffice"
        except RenderError:
            pass
    return render_pdf_builtin(sheet_model(xlsx_bytes, sheet_name, fallback_bytes)), "builtin"
