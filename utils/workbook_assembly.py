"""
workbook_assembly.py - output-mode handling shared by the I/O List and Cable Schedule generators.

The company template is the base of the output workbook; its sheets are never removed or
re-created. The only optional sheet is the generated summary (I/O Summary / Cable Summary):

    WITHOUT_SUMMARY = template sheets + generated list/schedule
    WITH_SUMMARY    = template sheets + generated list/schedule + summary (always last)

`plan_sheets` is the single source of truth for the sheet list: the preview endpoint, the
generator and the post-generation check all use it, so the downloaded workbook always
matches the preview.
"""
from __future__ import annotations

import io
import re

import openpyxl

WITHOUT_SUMMARY = "WITHOUT_SUMMARY"
WITH_SUMMARY = "WITH_SUMMARY"
OUTPUT_MODES = (WITHOUT_SUMMARY, WITH_SUMMARY)

IO_LIST_SHEET = "IO List"
IO_SUMMARY_SHEET = "IO Summary"        # Excel sheet names cannot contain "/"


def normalize_mode(value) -> str:
    """Explicit state only: anything but the two known modes is an error (no silent default)."""
    mode = str(value or "").strip().upper()
    if mode not in OUTPUT_MODES:
        raise ValueError(f"Invalid output mode '{value}'. Use {WITHOUT_SUMMARY} or {WITH_SUMMARY}.")
    return mode


def _key(name: str) -> str:
    return re.sub(r"[^0-9a-z]", "", str(name).lower())


def template_sheets(template_bytes: bytes) -> list[dict]:
    """[{"name", "hidden"}] for every sheet of the template, in workbook order."""
    wb = openpyxl.load_workbook(io.BytesIO(template_bytes), read_only=True, keep_links=False)
    try:
        return [{"name": ws.title, "hidden": ws.sheet_state != "visible"} for ws in wb.worksheets]
    finally:
        wb.close()


def plan_sheets(template_names: list[str], generated: str, summary: str, mode: str, generated_in_place: bool) -> list[str]:
    """
    Sheet names of the output workbook, in order.

    generated_in_place=False (I/O List): template sheets, then the generated sheet at the end.
    generated_in_place=True  (Cable Schedule): the template's own schedule sheet is populated where it is.
    A template sheet that has the summary's name is the designated optional sheet: it is dropped
    from its place and, only in WITH_SUMMARY, re-created as the last sheet.
    """
    mode = normalize_mode(mode)
    skip = {_key(summary)} | (set() if generated_in_place else {_key(generated)})
    names = [n for n in template_names if _key(n) not in skip]
    if not generated_in_place:
        names.append(generated)
    if mode == WITH_SUMMARY:
        names.append(summary)
    return names


def composition_of(xlsx_bytes: bytes) -> list[str]:
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, keep_links=False)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def check_composition(xlsx_bytes: bytes, planned: list[str]) -> str | None:
    """None when the workbook has exactly the planned sheets (same names, same order)."""
    actual = composition_of(xlsx_bytes)
    if actual != planned:
        return f"Output workbook sheets {actual} do not match the planned sheets {planned}."
    return None


def drop_sheet(wb, name: str) -> None:
    """Remove every sheet whose normalised name equals `name` (stale generated sheet from the template)."""
    for ws in list(wb.worksheets):
        if _key(ws.title) == _key(name) and len(wb.worksheets) > 1:
            del wb[ws.title]


# ─────────────────────────────────────────────────────────────────────────────
# Drawing restore: openpyxl drops some template drawing content when it re-saves a workbook
# (e.g. a logo inside a grouped shape on a cover sheet). Instead of trying to rebuild it, the
# template's own drawing part (and the images it references) is copied back, sheet by sheet.
# ─────────────────────────────────────────────────────────────────────────────
import posixpath
import zipfile
from xml.etree import ElementTree as ET

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_T_DRAWING = _NS_R + "/drawing"
_T_IMAGE = _NS_R + "/image"
ET.register_namespace("", _NS_REL)          # write <Relationships> with the default namespace like Excel does


def _resolve(base_dir: str, target: str) -> str:
    return target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base_dir, target))


def _sheet_drawings(z: zipfile.ZipFile) -> dict[str, str]:
    """sheet name -> drawing part path (only sheets that have a drawing)."""
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for sh in wb.iter(f"{{{_NS_MAIN}}}sheet"):
        target = rels.get(sh.get(f"{{{_NS_R}}}id"))
        if not target:
            continue
        sheet_path = _resolve("xl", target)
        rel_path = posixpath.join(posixpath.dirname(sheet_path), "_rels", posixpath.basename(sheet_path) + ".rels")
        if rel_path not in z.namelist():
            continue
        for r in ET.fromstring(z.read(rel_path)):
            if r.get("Type") == _T_DRAWING:
                out[sh.get("name")] = _resolve(posixpath.dirname(sheet_path), r.get("Target"))
    return out


def restore_template_drawings(out_bytes: bytes, template_bytes: bytes, sheet_names: list[str]) -> bytes:
    """
    For each sheet in `sheet_names` that has a drawing in BOTH the template and the output, replace the
    output's drawing XML by the template's and copy the pictures it references. Anything unexpected
    (charts/other relationships, missing parts, a result that does not load) leaves that sheet - or the whole
    workbook - exactly as openpyxl wrote it, so this step can never make the output worse.
    """
    try:
        zt = zipfile.ZipFile(io.BytesIO(template_bytes))
        zo = zipfile.ZipFile(io.BytesIO(out_bytes))
        t_dr, o_dr = _sheet_drawings(zt), _sheet_drawings(zo)
        replace: dict[str, bytes] = {}
        add: dict[str, bytes] = {}
        n_media = 0
        for name in sheet_names:
            if name not in t_dr or name not in o_dr:
                continue
            t_part, o_part = t_dr[name], o_dr[name]
            t_rels_path = posixpath.join(posixpath.dirname(t_part), "_rels", posixpath.basename(t_part) + ".rels")
            rel_xml = ET.fromstring(zt.read(t_rels_path)) if t_rels_path in zt.namelist() else ET.Element(f"{{{_NS_REL}}}Relationships")
            if any(r.get("Type") != _T_IMAGE for r in rel_xml):
                continue                                  # charts / other parts: keep openpyxl's version
            new_rels = ET.Element(f"{{{_NS_REL}}}Relationships")
            ok = True
            for r in rel_xml:
                src = _resolve(posixpath.dirname(t_part), r.get("Target"))
                if src not in zt.namelist():
                    ok = False
                    break
                n_media += 1
                ext = posixpath.splitext(src)[1]
                dst = f"xl/media/restored_{n_media}{ext}"
                add[dst] = zt.read(src)
                ET.SubElement(new_rels, f"{{{_NS_REL}}}Relationship", {"Id": r.get("Id"), "Type": _T_IMAGE, "Target": "/" + dst})
            if not ok:
                continue
            replace[o_part] = zt.read(t_part)
            o_rels_path = posixpath.join(posixpath.dirname(o_part), "_rels", posixpath.basename(o_part) + ".rels")
            replace[o_rels_path] = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(new_rels)
        if not replace:
            return out_bytes
        exts = {posixpath.splitext(p)[1].lstrip(".").lower() for p in add}
        ct = zo.read("[Content_Types].xml").decode("utf-8")
        have = {e.lower() for e in re.findall(r'<Default[^>]*Extension="([^"]+)"', ct)}
        t_ct = zt.read("[Content_Types].xml").decode("utf-8")
        defaults = dict((e.lower(), c) for e, c in re.findall(r'<Default[^>]*Extension="([^"]+)"[^>]*ContentType="([^"]+)"', t_ct))
        defaults.update((e.lower(), c) for c, e in re.findall(r'<Default[^>]*ContentType="([^"]+)"[^>]*Extension="([^"]+)"', t_ct))
        extra = ""
        for e in sorted(exts - have):
            if e not in defaults:
                return out_bytes
            extra += f'<Default Extension="{e}" ContentType="{defaults[e]}"/>'
        if extra:
            ct = ct.replace("<Override", extra + "<Override", 1) if "<Override" in ct else ct.replace("</Types>", extra + "</Types>")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zo.infolist():
                if item.filename == "[Content_Types].xml":
                    zout.writestr(item, ct)
                elif item.filename in replace:
                    zout.writestr(item, replace.pop(item.filename))
                else:
                    zout.writestr(item, zo.read(item.filename))
            for path, data in replace.items():            # rels files that did not exist yet
                zout.writestr(path, data)
            for path, data in add.items():
                zout.writestr(path, data)
        result = buf.getvalue()
        wb = openpyxl.load_workbook(io.BytesIO(result), read_only=True)      # must still open
        wb.close()
        return result
    except Exception:
        return out_bytes


def _sheet_paths(z: zipfile.ZipFile) -> dict[str, str]:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    return {sh.get("name"): _resolve("xl", rels[sh.get(f"{{{_NS_R}}}id")]) for sh in wb.iter(f"{{{_NS_MAIN}}}sheet")
            if sh.get(f"{{{_NS_R}}}id") in rels}


_HF = re.compile(r"<headerFooter\b[^>]*?(?:/>|>.*?</headerFooter>)", re.S)


def restore_template_header_footer(out_bytes: bytes, template_bytes: bytes, sheet_names: list[str]) -> bytes:
    """openpyxl silently drops header/footer text it cannot parse (e.g. a bare 'Page &P'). Copy the template's
    <headerFooter> element back for each named sheet when the output's differs. Never raises."""
    try:
        zt, zo = zipfile.ZipFile(io.BytesIO(template_bytes)), zipfile.ZipFile(io.BytesIO(out_bytes))
        tp, op = _sheet_paths(zt), _sheet_paths(zo)
        replace: dict[str, bytes] = {}
        for name in sheet_names:
            if name not in tp or name not in op:
                continue
            t_xml = zt.read(tp[name]).decode("utf-8")
            o_xml = zo.read(op[name]).decode("utf-8")
            t_hf = _HF.search(t_xml)
            if not t_hf:
                continue
            o_hf = _HF.search(o_xml)
            if o_hf and o_hf.group(0) == t_hf.group(0):
                continue
            if o_hf:
                new = o_xml[:o_hf.start()] + t_hf.group(0) + o_xml[o_hf.end():]
            else:
                anchor = re.search(r"<pageSetup\b[^>]*?/>", o_xml) or re.search(r"<pageMargins\b[^>]*?/>", o_xml)
                if not anchor:
                    continue
                new = o_xml[:anchor.end()] + t_hf.group(0) + o_xml[anchor.end():]
            replace[op[name]] = new.encode("utf-8")
        if not replace:
            return out_bytes
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zo.infolist():
                zout.writestr(item, replace.get(item.filename, zo.read(item.filename)))
        result = buf.getvalue()
        openpyxl.load_workbook(io.BytesIO(result), read_only=True).close()
        return result
    except Exception:
        return out_bytes


def restore_template_fidelity(out_bytes: bytes, template_bytes: bytes, sheet_names: list[str]) -> bytes:
    """Everything openpyxl cannot round-trip for the untouched template sheets: drawings, then header/footer."""
    out_bytes = restore_template_drawings(out_bytes, template_bytes, sheet_names)
    return restore_template_header_footer(out_bytes, template_bytes, sheet_names)
