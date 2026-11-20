"""
coversheet_pdf_template.py - PDF coversheet templates for the Coversheet Builder.

The uploaded PDF is the base document and is never redrawn: values and signatures are drawn on a transparent
overlay that is merged onto the original page, so page size, orientation, graphics, logos, borders, text and
background stay exactly as they are.

Analysis reads the words and the ruled boxes of the page (pdfplumber), finds the field labels and proposes the box
where each value goes. PDF layouts vary a lot, so every detection must be confirmed, and any box can be drawn by
hand on the page image instead (coordinates are PDF points, origin top-left, like pdfplumber).
"""
from __future__ import annotations

import base64
import io
import re
from typing import Optional

import logging

from .coversheet_builder import FIELD_DEFS, SIGNATURES, empty_field

logging.getLogger("pypdf").setLevel(logging.ERROR)

MAX_PAGES = 6

LABELS: dict[str, tuple[str, ...]] = {
    "document_number": ("document no", "document number", "doc no", "doc number", "drawing no", "drawing number", "dwg no",
                        "document ref", "doc ref", "document code"),
    "document_name": ("document title", "doc title", "title", "document name", "drawing title", "name of document"),
    "document_description": ("description", "document description", "doc description", "subject"),
    "revision": ("rev", "revision", "rev no", "revision no", "revision number"),
    "revision_date": ("date", "rev date", "revision date", "issue date", "date of issue"),
    "prepared_by": ("prepared by", "prepared", "drawn by", "originator", "made by"),
    "checked_by": ("checked by", "checked", "reviewed by"),
    "approved_by": ("approved by", "approved"),
}
_LOOKUP = {s: f for f, syns in LABELS.items() for s in syns}
_TABLE = {"revision", "revision_date", "prepared_by", "checked_by", "approved_by"}
_SIGN = {"sign", "signature", "signed", "signatures"}
_ROLE = {"prepared_by", "checked_by", "approved_by"}


class PdfTemplateError(Exception):
    """User-facing problem with the PDF template."""


def norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


def _open(data: bytes):
    if data[:4] != b"%PDF":
        raise PdfTemplateError("The file is not a PDF.")
    try:
        import pdfplumber
        return pdfplumber.open(io.BytesIO(data))
    except Exception as exc:
        raise PdfTemplateError(f"The PDF could not be opened (it may be corrupted or encrypted): {exc}")


def _lines(words: list[dict]) -> list[list[dict]]:
    out: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if out and abs(out[-1][0]["top"] - w["top"]) <= 2.5:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(l, key=lambda w: w["x0"]) for l in out]


def _cells(page) -> list[tuple[float, float, float, float]]:
    boxes = []
    try:
        for t in page.find_tables():
            boxes += [tuple(c) for c in t.cells if c]
    except Exception:
        pass
    W, H = float(page.width), float(page.height)
    for r in page.rects:
        w, h = r["x1"] - r["x0"], r["bottom"] - r["top"]
        if 14 < w < W * 0.98 and 8 < h < H * 0.9:
            boxes.append((r["x0"], r["top"], r["x1"], r["bottom"]))
    return boxes


def _containing(boxes, x, y):
    inside = [b for b in boxes if b[0] - 0.5 <= x <= b[2] + 0.5 and b[1] - 0.5 <= y <= b[3] + 0.5]
    return min(inside, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])) if inside else None


def _neighbour(boxes, cell, side):
    x0, t, x1, b = cell
    for c in sorted(boxes, key=lambda c: (c[2] - c[0]) * (c[3] - c[1])):
        if side == "right" and abs(c[0] - x1) <= 3 and min(b, c[3]) - max(t, c[1]) > 0.6 * (b - t):
            return c
        if side in ("below", "above"):
            touch = abs(c[1] - b) <= 3 if side == "below" else abs(c[3] - t) <= 3
            if touch and min(x1, c[2]) - max(x0, c[0]) > 0.5 * min(x1 - x0, c[2] - c[0]):
                return c
    return None


def _inset(b, d=1.5):
    return [round(b[0] + d, 1), round(b[1] + d, 1), round(b[2] - d, 1), round(b[3] - d, 1)]


def _marks_in(page, box) -> bool:
    """Pictures or drawn strokes (e.g. a scanned or vector signature) inside the box - the box is not empty."""
    def inside(o):
        return min(box[2], o["x1"]) - max(box[0], o["x0"]) > 2 and min(box[3], o["bottom"]) - max(box[1], o["top"]) > 2
    return any(inside(i) for i in page.images) or any(inside(c) for c in page.curves)


def _text_in(words, box, exclude=()):
    got = [w["text"] for w in words if w not in exclude and box[0] <= (w["x0"] + w["x1"]) / 2 <= box[2]
           and box[1] <= (w["top"] + w["bottom"]) / 2 <= box[3]]
    return " ".join(got)


def analyze_pdf(data: bytes) -> dict:
    pdf = _open(data)
    fields: dict[str, dict] = {k: empty_field(k) for k, *_ in FIELD_DEFS}
    pages_info, notes = [], []
    with pdf:
        if not pdf.pages:
            raise PdfTemplateError("The PDF has no pages.")
        if len(pdf.pages) > MAX_PAGES:
            notes.append(f"Only the first {MAX_PAGES} pages are used as the coversheet.")
        total_words = 0
        for pi, page in enumerate(pdf.pages[:MAX_PAGES]):
            rot = int(page.page_obj.attrs.get("Rotate", 0) or 0) % 360 if hasattr(page, "page_obj") else 0
            pages_info.append({"page": pi + 1, "width": float(page.width), "height": float(page.height), "rotation": rot})
            if rot:
                notes.append(f"Page {pi + 1} is rotated by {rot} degrees - check every position in the preview.")
            words = page.extract_words(keep_blank_chars=False) or []
            total_words += len(words)
            boxes = _cells(page)
            lines = _lines(words)
            found: list[dict] = []                               # label hits on this page
            for line in lines:
                used = set()
                for n in (4, 3, 2, 1):
                    for i in range(0, len(line) - n + 1):
                        if any(j in used for j in range(i, i + n)):
                            continue
                        span = line[i:i + n]
                        if any(span[j + 1]["x0"] - span[j]["x1"] > max(6.0, 0.9 * (span[j]["bottom"] - span[j]["top"]))
                               for j in range(n - 1)):
                            continue                                # words in separate boxes / columns
                        key = norm(" ".join(w["text"] for w in span))
                        if key in _LOOKUP or (n <= 2 and set(key.split()) & _SIGN and len(key.split()) == n):
                            nxt = line[i + n] if i + n < len(line) else None
                            sign_after = nxt is not None and norm(nxt["text"]) in _SIGN and key in _LOOKUP and _LOOKUP[key] in _ROLE
                            hit = {"field": _LOOKUP.get(key), "sign": bool(set(key.split()) & _SIGN) and key not in _LOOKUP,
                                   "words": span + ([nxt] if sign_after else []), "text": " ".join(w["text"] for w in span),
                                   "x0": span[0]["x0"], "x1": (nxt or span[-1])["x1"] if sign_after else span[-1]["x1"],
                                   "top": min(w["top"] for w in span), "bottom": max(w["bottom"] for w in span),
                                   "multi": n > 1, "line": line}
                            if sign_after:
                                hit["sign"], hit["role"] = True, _LOOKUP[key]
                                used.add(i + n)
                            found.append(hit)
                            used.update(range(i, i + n))
            # revision-table header: >= 3 table labels on one line
            table_tops = []
            table_row: dict[float, tuple] = {}                     # header line top -> (entry row y-range, side) or None
            H = float(page.height)
            for line in lines:
                heads = [h for h in found if h["line"] is line and h["field"] in _TABLE and not h["sign"]]
                if len({h["field"] for h in heads}) < 3:
                    continue
                top = line[0]["top"]
                table_tops.append(top)
                first = min(heads, key=lambda h: h["x0"])
                hc = _containing(boxes, (first["x0"] + first["x1"]) / 2, (first["top"] + first["bottom"]) / 2)
                if not hc:
                    table_row[top] = None
                    continue
                above, below = _neighbour(boxes, hc, "above"), _neighbour(boxes, hc, "below")
                side = "above" if (above and (first["top"] > H / 2 or not below)) else "below"
                nxt, steps, chosen, nearest = (above if side == "above" else below), 0, None, None
                while nxt is not None and steps < 15:             # the first row EMPTY in every column - never an old revision
                    yc = (nxt[1] + nxt[3]) / 2
                    nearest = nearest or (nxt[1], nxt[3])
                    cols = [_containing(boxes, (x["x0"] + x["x1"]) / 2, yc) for x in heads]
                    if all(c and not _text_in(words, c).strip() and not _marks_in(page, c) for c in cols):
                        chosen = (nxt[1], nxt[3])
                        break
                    nxt, steps = _neighbour(boxes, nxt, side), steps + 1
                if chosen is None and nearest:
                    notes.append(f"The revision table on page {pi + 1} has no empty entry row - its fields point at a "
                                 "filled row; check them.")
                table_row[top] = (chosen or nearest, side) if (chosen or nearest) else None
            # a "Signature" row label: its boxes sit under the Prepared / Checked / Approved column headers
            role_heads = [x for x in found if x["field"] in _ROLE and not x["sign"]]
            for h in found:
                if not h["sign"] or h.get("role"):
                    continue
                if any(norm(w["text"]) in _LOOKUP and _LOOKUP[norm(w["text"])] in _ROLE for w in h["line"]):
                    continue                                        # the role is on the same line - handled below
                scell = _containing(boxes, (h["x0"] + h["x1"]) / 2, (h["top"] + h["bottom"]) / 2)
                if not scell:
                    continue
                h["handled"] = True
                for rh in role_heads:
                    rx = (rh["x0"] + rh["x1"]) / 2
                    b = next((b for b in sorted(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
                              if abs(b[1] - scell[1]) <= 3 and b[0] <= rx <= b[2] and b != scell), None)
                    key = next(k for k, v in SIGNATURES.items() if v == rh["field"])
                    if b and not fields[key]["targets"]:
                        fields[key]["targets"] = [{"page": pi + 1, "box": _inset(b), "clear": False, "current": "",
                                                   "confirmed": False, "label": h["text"],
                                                   "where": f"'{h['text']}' row under '{rh['text']}'"}]
                        fields[key]["confidence"] = "medium"
                        fields[key]["reason"] = (f"'{h['text']}' row on page {pi + 1}, under the '{rh['text']}' column - "
                                                 "confirm the box.")
            for h in found:
                if h.get("handled"):
                    continue
                in_table = any(abs(h["top"] - t) <= 2.5 for t in table_tops)
                cx, cy = (h["x0"] + h["x1"]) / 2, (h["top"] + h["bottom"]) / 2
                cell = _containing(boxes, cx, cy)
                box, how = None, ""
                if in_table:
                    if h["field"] == "document_description":
                        continue                                  # the description column of the revision table
                    row = next((v for t, v in table_row.items() if abs(h["top"] - t) <= 2.5), None)
                    if row:
                        (rt, rb), side = row
                        pick = _containing(boxes, cx, (rt + rb) / 2)
                        if pick:
                            box, how = _inset(pick), f"revision table, first empty row {side} the '{h['text']}' header"
                elif cell:
                    right = _neighbour(boxes, cell, "right")
                    below = _neighbour(boxes, cell, "below")
                    row_labels = [b for b in boxes if abs(b[1] - cell[1]) <= 3 and b != cell
                                  and 0 < len(_text_in(words, b)) <= 14]
                    if below and len(row_labels) >= 3 and _text_in(words, below).strip() != "" or \
                            (below and len(row_labels) >= 3 and right and not _text_in(words, right).strip()):
                        box, how = _inset(below), f"box below '{h['text']}' (labels in a row, values underneath)"
                    elif right and right[2] - right[0] >= 30:
                        box, how = _inset(right), f"box to the right of '{h['text']}'"
                    elif cell[2] - h["x1"] > 40:
                        box, how = _inset((h["x1"] + 2, cell[1], cell[2], cell[3])), f"same box after '{h['text']}'"
                    else:
                        nb = right or _neighbour(boxes, cell, "below")
                        if nb:
                            box, how = _inset(nb), f"box next to '{h['text']}'"
                else:
                    others = [w for w in h["line"] if w["x0"] > h["x1"] + 6 and w not in h["words"]]
                    x1 = min(others[0]["x0"] - 6, h["x1"] + 220) if others else min(h["x1"] + 220, float(page.width) - 20)
                    if x1 - h["x1"] > 30:
                        box, how = [round(h["x1"] + 4, 1), round(h["top"] - 2, 1), round(x1, 1), round(h["bottom"] + 2, 1)], f"space after '{h['text']}'"
                if not box:
                    continue
                current = _text_in(words, box, h["words"])
                tgt = {"page": pi + 1, "box": box, "clear": bool(current.strip()), "current": current[:200],
                       "confirmed": False, "where": how, "label": h["text"],
                       "align": "center" if (in_table or box[2] - box[0] < 140) else "left",
                       "font_size": round(min(11.0, max(6.0, (h["bottom"] - h["top"]) * 1.05)), 1)}
                if h["sign"]:
                    role = h.get("role") or next((_LOOKUP[norm(w["text"])] for w in h["line"]
                                                  if norm(w["text"]) in _LOOKUP and _LOOKUP[norm(w["text"])] in _ROLE
                                                  and w["x1"] <= h["x0"] and h["x0"] - w["x1"] < 160), None)
                    if not role:
                        continue
                    key = next(k for k, v in SIGNATURES.items() if v == role)
                    tgt["clear"] = False
                else:
                    key = h["field"]
                fd = fields[key]
                conf = "high" if (h["multi"] and cell is not None and not current.strip() and not h["sign"]) else "medium"
                rank = {"none": 0, "medium": 1, "high": 2}
                if key == "revision" and fd["targets"] and len(fd["targets"]) < 2 and \
                        ("revision table" in tgt["where"]) != ("revision table" in fd["targets"][0]["where"]):
                    fd["targets"].append(tgt)                       # the ID-strip Rev box AND the table's REV column
                    fd["reason"] += f" Also the REV column of the revision table (page {pi + 1})."
                    continue
                if fd["targets"] and rank[conf] <= rank[fd["confidence"]]:
                    continue
                fd["targets"] = [tgt]
                fd["confidence"] = conf
                fd["reason"] = (f"Label '{h['text']}' on page {pi + 1}, {how}." if conf == "high" else
                                f"Label '{h['text']}' on page {pi + 1}, {how} - confirm the box (PDF layouts are read heuristically).")
        if total_words == 0:
            notes.append("This PDF has no text layer (scanned image), so no labels could be detected. "
                         "Draw each field's box on the page image.")
    for k, fd in fields.items():
        fd["needs_review"] = fd["confidence"] != "high"
        if fd["confidence"] == "high":
            for t in fd["targets"]:
                t["confirmed"] = True
    return {"kind": "pdf", "pages": pages_info, "fields": fields, "notes": notes,
            "page_images": render_pages(data, scale=1.5)}


def render_pages(data: bytes, scale: float = 1.5, max_pages: int = MAX_PAGES) -> list[dict]:
    try:
        import pypdfium2 as pdfium
    except Exception as exc:                                              # pragma: no cover
        raise PdfTemplateError(f"PDF rendering is not available on the server: {exc}")
    out = []
    doc = pdfium.PdfDocument(data)
    try:
        for i in range(min(len(doc), max_pages)):
            page = doc[i]
            img = page.render(scale=scale).to_pil()
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "PNG", optimize=True)
            out.append({"page": i + 1, "width_pt": page.get_width(), "height_pt": page.get_height(),
                        "scale": scale, "png": base64.b64encode(buf.getvalue()).decode()})
    finally:
        doc.close()
    return out


# ── filling ───────────────────────────────────────────────────────────────────
def _fit(text: str, w: float, h: float, font: str = "Helvetica", start: float = 11.0) -> tuple[float, list[str], bool]:
    from reportlab.lib.utils import simpleSplit
    size = min(start, max(5.0, h * 0.62))
    while size >= 5.0:
        lines = simpleSplit(text, font, size, w)
        if len(lines) * size * 1.15 <= h + 0.5 and all(True for _ in lines):
            return size, lines, True
        size -= 0.5
    return 5.0, simpleSplit(text, font, 5.0, w), False


def _latin(text: str) -> tuple[str, bool]:
    out = text.encode("latin-1", "replace").decode("latin-1")
    return out, out != text


def fill_pdf(data: bytes, mapping: dict, values: dict, signatures: dict[str, bytes]) -> tuple[bytes, list[str]]:
    """Overlay the confirmed fields onto the original pages. Returns (pdf bytes, warnings)."""
    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except Exception as exc:                                              # pragma: no cover
        raise PdfTemplateError(f"PDF writing is not available on the server: {exc}")
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            reader.decrypt("")
    except Exception as exc:
        raise PdfTemplateError(f"The PDF template could not be read: {exc}")
    warnings: list[str] = []
    per_page: dict[int, list[tuple]] = {}
    for key, *_ in FIELD_DEFS:
        fm = mapping.get(key) or {}
        if fm.get("skipped"):
            continue
        for t in fm.get("targets", []):
            if not t.get("confirmed") or not t.get("box"):
                continue
            if key in SIGNATURES:
                if signatures.get(key):
                    per_page.setdefault(int(t["page"]), []).append(("img", key, t, signatures[key]))
            else:
                val = str(values.get(key, "") or "").strip()
                if val:
                    per_page.setdefault(int(t["page"]), []).append(("txt", key, t, val))
    writer = PdfWriter(clone_from=reader)
    label = {k: l for k, l, *_ in FIELD_DEFS}
    for pno, page in enumerate(writer.pages, start=1):
        ops = per_page.get(pno)
        if ops:
            mb = page.mediabox
            llx, lly, W, H = float(mb.left), float(mb.bottom), float(mb.width), float(mb.height)
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(W, H))
            for kind, key, t, payload in ops:
                x0, top, x1, bottom = [float(v) for v in t["box"]]
                bw, bh = x1 - x0, bottom - top
                if bw <= 4 or bh <= 4:
                    warnings.append(f"{label[key]}: the box is too small.")
                    continue
                X, Y = x0, H - bottom                             # reportlab origin bottom-left (overlay page space)
                if kind == "txt":
                    if t.get("clear"):
                        c.setFillColorRGB(1, 1, 1)
                        c.rect(X + 0.6, Y + 0.6, bw - 1.2, bh - 1.2, stroke=0, fill=1)
                    text, lost = _latin(payload)
                    if lost:
                        warnings.append(f"{label[key]}: characters outside the PDF font were replaced by '?'.")
                    size, lines, ok = _fit(text, bw - 4, bh - 2, start=float(t.get("font_size") or 10.0))
                    if not ok:
                        warnings.append(f"{label[key]}: the text is too long for its box on page {pno} - enlarge the box.")
                        lines = lines[:max(1, int((bh - 2) // (size * 1.15)))]
                    c.setFillColorRGB(0, 0, 0)
                    c.setFont("Helvetica", size)
                    block = len(lines) * size * 1.15
                    y = Y + (bh + block) / 2 - size
                    for ln in lines:
                        if t.get("align") == "center":
                            c.drawCentredString(X + bw / 2, y + size * 0.15, ln)
                        else:
                            c.drawString(X + 2, y + size * 0.15, ln)
                        y -= size * 1.15
                else:
                    from PIL import Image
                    im = Image.open(io.BytesIO(payload))
                    im.load()
                    iw, ih = im.size
                    s = min((bw - 4) / iw, (bh - 4) / ih)
                    w, h = iw * s, ih * s
                    c.drawImage(ImageReader(im.convert("RGBA")), X + (bw - w) / 2, Y + (bh - h) / 2, w, h, mask="auto")
            c.showPage()
            c.save()
            overlay = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
            if llx or lly:
                from pypdf import Transformation
                overlay.add_transformation(Transformation().translate(llx, lly))
            page.merge_page(overlay)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), warnings
