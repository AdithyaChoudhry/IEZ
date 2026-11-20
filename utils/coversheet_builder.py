"""
coversheet_builder.py - Excel side of the MDL-driven Coversheet Builder (routers/coversheet_builder.py).

It REUSES the existing uploaded-template engine without changing it:
    coversheet_template_analyzer.analyze   label-driven field detection (+ confidence)
    coversheet_excel_fill.fill_template    writes only confirmed cells, keeps styles / merges / images / print setup

and adds what the builder needs on top:
    * separate Document Name (title) and Document Description fields
    * signature locations (detected or assigned) and signature pictures placed into the generated workbook
      at package level, inside the target cell box, aspect ratio kept, never stretched.

Field keys used by the builder (Excel and PDF templates alike):
"""
from __future__ import annotations

import io
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Optional

import openpyxl
from openpyxl.utils import get_column_letter, range_boundaries

from .coversheet_excel_fill import FillError, fill_template
from .coversheet_layout import col_width_px, row_height_px
from .coversheet_template_analyzer import (TemplateError, Sheet, _EXACT, _find_table, _first_line, _rc,
                                           _value_cell_for_label, analyze, norm)
from .workbook_assembly import restore_template_fidelity

# key, label, required mapping, kind, value source
FIELD_DEFS = [
    ("document_number", "Document Number", True, "text", "mdl"),
    ("document_name", "Document Name / Title", True, "text", "mdl"),
    ("document_description", "Document Description", False, "text", "mdl"),
    ("revision", "Revision Number", False, "text", "input"),
    ("revision_date", "Revision Date", False, "text", "input"),
    ("prepared_by", "Prepared By", False, "text", "input"),
    ("checked_by", "Checked By", False, "text", "input"),
    ("approved_by", "Approved By", False, "text", "input"),
    ("sig_prepared", "Prepared By Signature", False, "image", "signature"),
    ("sig_checked", "Checked By Signature", False, "image", "signature"),
    ("sig_approved", "Approved By Signature", False, "image", "signature"),
]
FIELD_KEYS = [k for k, *_ in FIELD_DEFS]
SIGNATURES = {"sig_prepared": "prepared_by", "sig_checked": "checked_by", "sig_approved": "approved_by"}
TEXT_KEYS = [k for k, _l, _r, kind, _s in FIELD_DEFS if kind == "text"]

_DESC_LABELS = {"description", "document description", "doc description", "brief description", "subject",
                "description of document", "scope"}
_ROLE_WORDS = {"prepared": "prepared_by", "drawn": "prepared_by", "originator": "prepared_by", "made": "prepared_by",
               "checked": "checked_by", "reviewed": "checked_by", "approved": "approved_by", "approver": "approved_by"}
_SIGN_WORDS = {"sign", "signature", "signed", "sig", "signatures"}

EMU = 9525
_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
_T_DRAWING = _NS["r"] + "/drawing"
_T_IMAGE = _NS["r"] + "/image"


def empty_field(key: str) -> dict:
    d = next(x for x in FIELD_DEFS if x[0] == key)
    return {"label": d[1], "required": d[2], "kind": d[3], "source": d[4], "confidence": "none",
            "reason": "Not found in the template - assign it or skip it.", "targets": [], "skipped": False}


# ── Excel analysis ────────────────────────────────────────────────────────────
def _with_meta(key: str, f: dict) -> dict:
    base = empty_field(key)
    out = {**base, **{k: v for k, v in f.items() if k not in ("label", "required")}}
    out["label"], out["required"] = base["label"], base["required"]
    out.setdefault("skipped", False)
    return out


def analyze_excel(data: bytes, sheet: Optional[str] = None) -> dict:
    a = analyze(data, sheet)
    f = a["fields"]
    fields: dict[str, dict] = {
        "document_number": _with_meta("document_number", f["document_number"]),
        "document_name": _with_meta("document_name", f["document_description"]),
        "document_description": empty_field("document_description"),
        "revision": _with_meta("revision", f["revision"]),
        "revision_date": _with_meta("revision_date", f["date"]),
        "prepared_by": _with_meta("prepared_by", f["prepared_by"]),
        "checked_by": _with_meta("checked_by", f["checked_by"]),
        "approved_by": _with_meta("approved_by", f["approved_by"]),
    }
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb[a["sheet"]]
    sh = Sheet(ws)
    table = _find_table(sh)

    # The existing analyser treats 'Title' and 'Description' labels alike. When both exist, the cell next to the
    # description label becomes the Document Description; the title stays the Document Name.
    name = fields["document_name"]
    by_desc = [t for t in name["targets"] if norm(t.get("label", "")) in _DESC_LABELS]
    if by_desc and len(by_desc) < len(name["targets"]):
        name["targets"] = [t for t in name["targets"] if t not in by_desc]
        d = fields["document_description"]
        d["targets"] = [{**t, "confirmed": False} for t in by_desc]
        d["confidence"], d["reason"] = "medium", f"Cell next to the label '{by_desc[0].get('label')}' - confirm it holds the description."
    else:
        taken = {t["cell"] for t in name["targets"]}
        for r, c, v in sh.cells():
            if table and r == table["header_row"]:
                continue
            if norm(_first_line(v)) not in _DESC_LABELS:
                continue
            hit = _value_cell_for_label(sh, r, c)
            if hit and sh.coord(hit[0], hit[1]) not in taken:
                d = fields["document_description"]
                d["targets"] = [{"cell": sh.coord(hit[0], hit[1]), "mode": "replace", "current": sh.text(hit[0], hit[1])[:200],
                                 "confirmed": False, "label": _first_line(v), "where": f"next to '{_first_line(v)}'"}]
                d["confidence"], d["reason"] = "medium", f"Cell next to the label '{_first_line(v)}' - confirm it holds the description."
                break

    fields.update(_detect_excel_signatures(sh))
    for k, fm in fields.items():
        fm["needs_review"] = fm["confidence"] != "high"
    return {"kind": "excel", **{k: v for k, v in a.items() if k != "fields"}, "fields": fields}


def _detect_excel_signatures(sh: Sheet) -> dict[str, dict]:
    out = {k: empty_field(k) for k in SIGNATURES}
    roles: dict[str, list[tuple[int, int]]] = {}
    signs: list[tuple[int, int, str]] = []
    for r, c, v in sh.cells():
        first = _first_line(v)
        n = norm(first)
        toks = set(n.split())
        f = _EXACT.get(n)
        if f in ("prepared_by", "checked_by", "approved_by"):
            roles.setdefault(f, []).append((r, c))
        if toks & _SIGN_WORDS and len(toks) <= 6:
            signs.append((r, c, first))

    def put(role, cell, how):
        key = next(k for k, v in SIGNATURES.items() if v == role)
        if out[key]["targets"]:
            return
        out[key]["targets"] = [{"cell": cell, "mode": "image", "current": "", "confirmed": False, "where": how}]
        out[key]["confidence"], out[key]["reason"] = "medium", f"{how} - confirm the signature box."

    for r, c, text in signs:
        toks = set(norm(text).split())
        role = next((_ROLE_WORDS[t] for t in toks if t in _ROLE_WORDS), None)
        if role:                                                  # "Prepared by (Sign)" - box beside / below it
            hit = _value_cell_for_label(sh, r, c)
            if hit:
                put(role, sh.coord(hit[0], hit[1]), f"Next to '{text}'")
            continue
        for role, cells in roles.items():                         # a "Sign" row label under role column headers
            for (rh, ch) in cells:
                if rh != r and ch > c:
                    put(role, sh.coord(r, ch), f"Row '{text}' under the '{sh.text(rh, ch).strip()}' column")
    return out


# ── Excel generation ──────────────────────────────────────────────────────────
def _legacy(mapping: dict, values: dict) -> tuple[dict, dict]:
    m = {"document_number": mapping.get("document_number") or {}, "document_description": mapping.get("document_name") or {},
         "revision": mapping.get("revision") or {}, "date": mapping.get("revision_date") or {},
         "prepared_by": mapping.get("prepared_by") or {}, "checked_by": mapping.get("checked_by") or {},
         "approved_by": mapping.get("approved_by") or {}}
    for k in m:
        m[k] = {"targets": [], **m[k]}
    v = {"document_number": values.get("document_number", ""), "document_description": values.get("document_name", ""),
         "revision": values.get("revision", ""), "date": values.get("revision_date", ""),
         "prepared_by": values.get("prepared_by", ""), "checked_by": values.get("checked_by", ""),
         "approved_by": values.get("approved_by", "")}
    return m, v


def placed(fm: Optional[dict]) -> bool:
    """The field has at least one confirmed location (a cell / box, or the split document-number boxes)."""
    if not fm or fm.get("skipped"):
        return False
    return bool(confirmed(fm)) or any(p.get("confirmed") and str(p.get("cell", "")).strip() for p in (fm.get("parts") or {}).values())


def confirmed(fm: Optional[dict]) -> list[dict]:
    if not fm or fm.get("skipped"):
        return []
    return [t for t in fm.get("targets", []) if t.get("confirmed") and str(t.get("cell", "") or t.get("box", "")).strip()]


def fill_excel(template: bytes, sheet: str, mapping: dict, values: dict, signatures: dict[str, bytes],
               clear_history: bool = True) -> tuple[bytes, list[str]]:
    lm, lv = _legacy(mapping, values)
    out, warnings = fill_template(template, sheet, lm, lv, clear_history)

    desc_targets = confirmed(mapping.get("document_description"))
    desc = str(values.get("document_description", "") or "").strip()
    if desc_targets and desc:
        wb = openpyxl.load_workbook(io.BytesIO(out))
        ws = wb[sheet]
        sh = Sheet(ws)
        for t in desc_targets:
            r, c = _rc(t["cell"])
            cell = ws.cell(*sh.anchor_of(r, c))
            if isinstance(cell.value, str) and cell.value.startswith("="):
                raise FillError(f"Cell {cell.coordinate} contains a formula and cannot receive the description.")
            cell.value = desc
        buf = io.BytesIO()
        wb.save(buf)
        out = restore_template_fidelity(buf.getvalue(), template, [sheet])

    items = []
    for key in SIGNATURES:
        img = signatures.get(key)
        tg = confirmed(mapping.get(key))
        if img and tg:
            items += [(t["cell"], img, key) for t in tg]
    if items:
        out, w = add_images(out, sheet, items)
        warnings += w
    return out, warnings


# ── pictures into an existing workbook (package level, nothing else touched) ─────────────────────────────────
def _col_widths(ws, upto: int) -> list[float]:
    widths = {}
    default = ws.sheet_format.defaultColWidth or (ws.sheet_format.baseColWidth or 8) + 0.43
    for _k, d in ws.column_dimensions.items():
        lo, hi = d.min or 0, d.max or 0
        for col in range(lo, hi + 1):
            widths[col] = 0 if d.hidden else col_width_px(d.width if d.width else default)
    return [widths.get(c, col_width_px(default)) for c in range(1, upto + 1)]


def _row_heights(ws, upto: int) -> list[float]:
    default = ws.sheet_format.defaultRowHeight or 15
    out = []
    for r in range(1, upto + 1):
        d = ws.row_dimensions.get(r)
        out.append(0 if (d is not None and d.hidden) else row_height_px(d.height if d is not None and d.height else default))
    return out


def _locate(pos: float, sizes: list[float]) -> tuple[int, float]:
    acc = 0.0
    for i, s in enumerate(sizes):
        if pos < acc + s or i == len(sizes) - 1:
            return i, max(0.0, pos - acc)
        acc += s
    return len(sizes) - 1, 0.0


def _png(img_bytes: bytes) -> tuple[bytes, int, int]:
    from PIL import Image
    im = Image.open(io.BytesIO(img_bytes))
    im.load()
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA")
    if im.width > 900:
        im = im.resize((900, max(1, round(im.height * 900 / im.width))))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue(), im.width, im.height


def box_of(sh: Sheet, ref: str) -> tuple[int, int, int, int]:
    ref = ref.strip().upper()
    if ":" in ref:
        c1, r1, c2, r2 = range_boundaries(ref)
        return r1, c1, r2, c2
    r, c = _rc(ref)
    return sh.bounds(r, c)


def add_images(xlsx: bytes, sheet: str, items: list[tuple[str, bytes, str]]) -> tuple[bytes, list[str]]:
    """Place pictures inside cell boxes (A1 or A1:C3; a merged cell means its whole merge). Aspect ratio kept."""
    warnings: list[str] = []
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    ws = wb[sheet]
    sh = Sheet(ws)
    anchors = []
    for ref, img, label in items:
        try:
            r1, c1, r2, c2 = box_of(sh, ref)
        except Exception:
            raise FillError(f"'{ref}' is not a valid cell or range for {label.replace('_', ' ')}.")
        widths, heights = _col_widths(ws, c2 + 2), _row_heights(ws, r2 + 2)
        x0, x1 = sum(widths[:c1 - 1]), sum(widths[:c2])
        y0, y1 = sum(heights[:r1 - 1]), sum(heights[:r2])
        bw, bh = x1 - x0, y1 - y0
        if bw < 12 or bh < 8:
            raise FillError(f"The box {ref} is too small for a signature. Assign a larger cell or range.")
        png, iw, ih = _png(img)
        pad = 3
        s = min((bw - 2 * pad) / iw, (bh - 2 * pad) / ih)
        w, h = iw * s, ih * s
        left, top = x0 + (bw - w) / 2, y0 + (bh - h) / 2
        col, coff = _locate(left, widths)
        row, roff = _locate(top, heights)
        anchors.append((col, coff, row, roff, w, h, png, label))
        texts = [sh.text(rr, cc).strip() for rr in range(r1, r2 + 1) for cc in range(c1, c2 + 1) if sh.is_anchor(rr, cc)]
        if any(texts):
            warnings.append(f"The {label.replace('sig_', '').replace('_', ' ')} signature box {ref} also holds text "
                            f"('{next(t for t in texts if t)[:30]}') - the signature is drawn over it.")
    wb.close()
    return _inject(xlsx, sheet, anchors), warnings


def _rel(path: str) -> str:
    return posixpath.join(posixpath.dirname(path), "_rels", posixpath.basename(path) + ".rels")


def _resolve(base: str, target: str) -> str:
    return target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base, target))


def _inject(xlsx: bytes, sheet: str, anchors: list) -> bytes:
    z = zipfile.ZipFile(io.BytesIO(xlsx))
    names = set(z.namelist())
    files: dict[str, bytes] = {n: z.read(n) for n in z.namelist()}
    wbx = ET.fromstring(files["xl/workbook.xml"])
    wrels = {r.get("Id"): r.get("Target") for r in ET.fromstring(files["xl/_rels/workbook.xml.rels"])}
    sheet_path = None
    for s in wbx.iter(f"{{{_NS['main']}}}sheet"):
        if s.get("name") == sheet:
            sheet_path = _resolve("xl", wrels[s.get(f"{{{_NS['r']}}}id")])
    if not sheet_path:
        raise FillError(f"Sheet '{sheet}' is missing from the generated workbook.")
    srel_path = _rel(sheet_path)
    srels = ET.fromstring(files[srel_path]) if srel_path in files else ET.Element(f"{{{_NS['rel']}}}Relationships")
    drawing_path = None
    for r in srels:
        if r.get("Type") == _T_DRAWING:
            drawing_path = _resolve(posixpath.dirname(sheet_path), r.get("Target"))
    ct = files["[Content_Types].xml"].decode("utf-8")
    if drawing_path is None:
        n = 1
        while f"xl/drawings/drawing{n}.xml" in names:
            n += 1
        drawing_path = f"xl/drawings/drawing{n}.xml"
        files[drawing_path] = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                               f'<xdr:wsDr xmlns:xdr="{_NS["xdr"]}" xmlns:a="{_NS["a"]}"></xdr:wsDr>').encode()
        rid = _next_id(srels)
        ET.SubElement(srels, f"{{{_NS['rel']}}}Relationship", {"Id": rid, "Type": _T_DRAWING, "Target": "/" + drawing_path})
        sx = files[sheet_path].decode("utf-8")
        tag = f'<drawing xmlns:r="{_NS["r"]}" r:id="{rid}"/>' if 'xmlns:r=' not in sx[:2000] else f'<drawing r:id="{rid}"/>'
        m = re.search(r"<(legacyDrawing|legacyDrawingHF|drawingHF|picture|oleObjects|controls|webPublishItems|tableParts|extLst)\b", sx)
        sx = sx[:m.start()] + tag + sx[m.start():] if m else sx.replace("</worksheet>", tag + "</worksheet>")
        files[sheet_path] = sx.encode("utf-8")
        ct = ct.replace("</Types>", f'<Override PartName="/{drawing_path}" '
                                    f'ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/></Types>')
    if not re.search(r'Extension="png"', ct, re.I):
        ct = ct.replace("<Override", '<Default Extension="png" ContentType="image/png"/><Override', 1)
    files["[Content_Types].xml"] = ct.encode("utf-8")
    files[srel_path] = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(srels, default_namespace=None)

    drel_path = _rel(drawing_path)
    drels = ET.fromstring(files[drel_path]) if drel_path in files else ET.Element(f"{{{_NS['rel']}}}Relationships")
    dxml = files[drawing_path].decode("utf-8")
    ids = [int(x) for x in re.findall(r'<xdr:cNvPr[^>]*\bid="(\d+)"', dxml)] or [1]
    next_pic = max(ids) + 1
    snippets = []
    for (col, coff, row, roff, w, h, png, label) in anchors:
        k = 1
        while f"xl/media/iez_signature_{k}.png" in files:
            k += 1
        media = f"xl/media/iez_signature_{k}.png"
        files[media] = png
        rid = _next_id(drels)
        ET.SubElement(drels, f"{{{_NS['rel']}}}Relationship", {"Id": rid, "Type": _T_IMAGE, "Target": "/" + media})
        cx, cy = int(w * EMU), int(h * EMU)
        snippets.append(
            f'<xdr:oneCellAnchor xmlns:xdr="{_NS["xdr"]}" xmlns:a="{_NS["a"]}"><xdr:from><xdr:col>{col}</xdr:col><xdr:colOff>{int(coff * EMU)}</xdr:colOff>'
            f'<xdr:row>{row}</xdr:row><xdr:rowOff>{int(roff * EMU)}</xdr:rowOff></xdr:from><xdr:ext cx="{cx}" cy="{cy}"/>'
            f'<xdr:pic><xdr:nvPicPr><xdr:cNvPr id="{next_pic}" name="{label}"/><xdr:cNvPicPr><a:picLocks noChangeAspect="1"/>'
            f'</xdr:cNvPicPr></xdr:nvPicPr><xdr:blipFill><a:blip xmlns:r="{_NS["r"]}" r:embed="{rid}"/><a:stretch><a:fillRect/>'
            f'</a:stretch></xdr:blipFill><xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/></xdr:oneCellAnchor>')
        next_pic += 1
    dxml = re.sub(r"<((?:\w+:)?wsDr)([^>]*)/>", r"<\1\2></\1>", dxml)
    ends = list(re.finditer(r"</(?:\w+:)?wsDr>", dxml))
    if not ends:
        raise FillError("The template's drawing part could not be read; signatures were not added.")
    e = ends[-1]
    dxml = dxml[:e.start()] + "".join(snippets) + dxml[e.start():]
    files[drawing_path] = dxml.encode("utf-8")
    files[drel_path] = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(drels)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zo:
        order = [i.filename for i in z.infolist()] + [n for n in files if n not in names]
        for n in order:
            zo.writestr(n, files[n])
    result = buf.getvalue()
    try:
        openpyxl.load_workbook(io.BytesIO(result)).close()
    except Exception as exc:
        raise FillError(f"The signatures could not be added to the workbook: {exc}")
    return result


def _next_id(rels) -> str:
    used = {r.get("Id") for r in rels}
    i = 1
    while f"rId{i}" in used:
        i += 1
    return f"rId{i}"


ET.register_namespace("", _NS["rel"])
