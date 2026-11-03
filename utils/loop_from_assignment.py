"""
loop_from_assignment.py - feed the Loop Wiring template from the standard I/O Assignment workbook.

    IO_ASSIGNMENT sheet (one row per tag)
        -> columns re-ordered to the loop template's data columns (W18:AR18)   [build_loop_input]
        -> loop type chosen per row                                            [classify]
        -> one sheet per tag copied from the matching sheet of the loop template, row 19 filled   [generate]

Loop type rule (as specified):  I/O TYPE = AI and WIRE TYPE = 2 WIRE -> "2-WIRE INSTRUMENT";
                                I/O TYPE = AI and WIRE TYPE = 4 WIRE -> "4-WIRE INSTRUMENT".
Every other signal is reported as "not mapped" with the reason - nothing is guessed.
"""
from __future__ import annotations

import copy
import io
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import openpyxl
import pandas as pd

LOOP_2W = "2-WIRE INSTRUMENT"
LOOP_4W = "4-WIRE INSTRUMENT"
HEADER_ROW, DATA_ROW, COL_START, COL_END = 18, 19, 23, 44          # loop template data block: W18:AR18 / row 19


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip().upper()


def classify(io_type: Any, wire_type: Any) -> tuple[Optional[str], str]:
    """(loop type, reason). reason is empty when mapped."""
    io, wire = _norm(io_type), _norm(wire_type)
    if io != "AI":
        return None, f"I/O TYPE '{io or '-'}' has no loop template yet (only AI is mapped)"
    if wire == "2 WIRE":
        return LOOP_2W, ""
    if wire == "4 WIRE":
        return LOOP_4W, ""
    return None, f"AI with WIRE TYPE '{wire or '-'}' (expected 2 WIRE or 4 WIRE)"


# loop-template header (normalised) -> how to obtain it from an IO_ASSIGNMENT row (dict keyed by assignment header)
def derive_loop_name(tag: Any) -> str:
    """Loop name when the assignment has no LOOP NO (e.g. NEW WWTP): area + loop number of the tag, function letters dropped
    ('100-PIT-10101' -> '100-10101'). MODEL INFERENCE - used so every loop sheet carries a loop name; falls back to the tag."""
    parts = [p for p in re.split(r"-", str(tag).strip()) if p]
    m = re.match(r"^(\d{3,})", parts[-1]) if len(parts) >= 2 else None
    return f"{parts[0]}-{m.group(1)}" if m and parts[0].isdigit() else str(tag).strip()


def _f(name: str) -> Callable[[dict], Any]:
    return lambda r: r.get(name)


def _jb_cable(r: dict) -> Any:
    """Derived like the reference 'JB Cable' text: <tag>/<junction box>."""
    tag, jb = r.get("TAG NO"), r.get("JUNCTION BOX NO")
    return f"{tag}/{jb}" if tag and jb else None


FEED_MAP: dict[str, tuple[Callable[[dict], Any], str]] = {
    "TAG_NUMBER": (_f("TAG NO"), "TAG NO"),
    "LOOP_NAME": (_f("LOOP NO"), "LOOP NO"),
    "SIGNAL TYPE(SIBUR)": (_f("SIGNAL TYPE"), "SIGNAL TYPE"),
    "JB CABLE": (_jb_cable, "derived: TAG NO / JUNCTION BOX NO"),
    "JB TAG NUMBER": (_f("JUNCTION BOX NO"), "JUNCTION BOX NO"),
    "CABLE NO.": (_f("CABLE NO"), "CABLE NO"),
    "PAIR_NUM": (_f("CORE / PAIR"), "CORE / PAIR"),
    "MARSH_CABINET": (_f("MARSHALLING CABINET"), "MARSHALLING CABINET"),
    "TERM_BLOCK1": (_f("TERMINAL STRIP NO"), "TERMINAL STRIP NO"),
    "TERM1": (_f("TERMINAL NO (CMN)"), "TERMINAL NO (CMN)"),
    "TERM2": (_f("TERMINAL NO (SIGNAL)"), "TERMINAL NO (SIGNAL)"),
    "SYS_CABINET": (_f("PANEL NO"), "PANEL NO"),
    "MODULE_TAG": (_f("MODULE NO"), "MODULE NO"),
    "MODULE_TYPE": (_f("MODULE TYPE"), "MODULE TYPE"),
    "CRATE": (_f("RACK NO"), "RACK NO"),
    "SLOT": (_f("SLOT NO"), "SLOT NO"),
    "CHANNEL": (_f("CHANNEL NO"), "CHANNEL NO"),
    # FTA_model, FTA_Tag, FTA_In1, FTA_Out1, Sys_Cable: vendor termination / system-cable data that the standard I/O
    # Assignment deliberately does not carry (project-specific) -> written as TBA until a source column exists.
}


@dataclass
class LoopFeed:
    headers: list[str] = field(default_factory=list)          # loop-template headers, template order (W18:AR18)
    rows: list[dict] = field(default_factory=list)            # {header: value, "LOOP TYPE": ..., "SOURCE ROW": n}
    skipped: list[tuple[int, str, str]] = field(default_factory=list)   # (assignment row, tag, reason)
    unfed_headers: list[str] = field(default_factory=list)    # loop headers with no source column


def template_headers(template_bytes: bytes) -> list[str]:
    wb = openpyxl.load_workbook(io.BytesIO(template_bytes))
    ws = wb.worksheets[0]
    return [str(ws.cell(HEADER_ROW, c).value).strip() for c in range(COL_START, COL_END + 1) if ws.cell(HEADER_ROW, c).value is not None]


def read_assignment(data: bytes) -> tuple[list[dict], str]:
    """Rows of the IO_ASSIGNMENT sheet as dicts keyed by header (formula columns read as their cached values)."""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    sheet = "IO_ASSIGNMENT" if "IO_ASSIGNMENT" in wb.sheetnames else None
    for name in ([sheet] if sheet else wb.sheetnames):
        ws = wb[name]
        rows = list(ws.iter_rows(min_row=1, max_row=15, values_only=True))
        for hi, r in enumerate(rows, 1):
            heads = [_norm(c) for c in r]
            if "TAG NO" in heads and "I/O TYPE" in heads:
                header = [str(c).strip() if c is not None else "" for c in r]
                out = []
                for n, vals in enumerate(ws.iter_rows(min_row=hi + 1, values_only=True), hi + 1):
                    d = {h: v for h, v in zip(header, vals) if h}
                    d["_row"] = n
                    out.append(d)
                return out, name
    raise ValueError("No sheet with 'TAG NO' and 'I/O TYPE' headers was found - is this a standard I/O Assignment workbook?")


def build_loop_input(assignment_rows: list[dict], headers: list[str]) -> LoopFeed:
    feed = LoopFeed(headers=list(headers))
    feed.unfed_headers = [h for h in headers if h.strip().upper() not in FEED_MAP]
    for r in assignment_rows:
        tag = r.get("TAG NO")
        if tag in (None, "") or _norm(tag) == "SPARE":
            continue
        if _norm(r.get("CHANGE STATUS")) == "DELETED":
            continue
        if _norm(r.get("INTERFACE")) not in ("HARDWIRED", ""):
            feed.skipped.append((r["_row"], str(tag), f"INTERFACE '{r.get('INTERFACE')}' has no field wiring"))
            continue
        loop_type, why = classify(r.get("I/O TYPE"), r.get("WIRE TYPE"))
        if loop_type is None:
            feed.skipped.append((r["_row"], str(tag), why))
            continue
        row = {}
        for h in headers:
            src = FEED_MAP.get(h.strip().upper())
            v = src[0](r) if src else None
            row[h] = None if v in ("", "-") else v
        if row.get("Loop_Name") in (None, ""):
            row["Loop_Name"] = derive_loop_name(tag)                  # every loop gets a name; shown at the top of the sheet
        row["LOOP TYPE"] = loop_type
        row["SOURCE ROW"] = r["_row"]
        feed.rows.append(row)
    return feed


def feed_to_xlsx(feed: LoopFeed) -> bytes:
    """The loop-template data columns laid side by side (header row, then one row per tag) + LOOP TYPE."""
    df = pd.DataFrame(feed.rows, columns=feed.headers + ["LOOP TYPE", "SOURCE ROW"])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="LOOP WIRING INPUT")
        ws = w.sheets["LOOP WIRING INPUT"]
        for i, col in enumerate(df.columns, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = max(12, min(40, len(str(col)) + 4))
        ws.freeze_panes = "B2"
    return buf.getvalue()


def _safe_title(tag: str, used: set) -> str:
    base = re.sub(r"[\\/*?:\[\]]", "_", f"Loop_{tag}")[:31]
    t, n = base, 2
    while t.lower() in used:
        suffix = f"_{n}"
        t, n = base[:31 - len(suffix)] + suffix, n + 1
    used.add(t.lower())
    return t


def generate(feed: LoopFeed, template_bytes: bytes) -> bytes:
    """One sheet per fed tag, copied from the loop template's sheet for its loop type; row 19 filled; drawings restored."""
    from utils.workbook_assembly import _sheet_drawings, _resolve  # noqa: F401  (drawing lookup helpers)
    wb = openpyxl.load_workbook(io.BytesIO(template_bytes))
    type_sheets = {ws.title: ws for ws in wb.worksheets}
    missing = {r["LOOP TYPE"] for r in feed.rows} - set(type_sheets)
    if missing:
        raise ValueError(f"The loop template has no sheet for: {', '.join(sorted(missing))}")
    used: set = set()
    made: list[tuple[str, str]] = []                                 # (new sheet title, template sheet title)
    for r in feed.rows:
        src = type_sheets[r["LOOP TYPE"]]
        ws = wb.copy_worksheet(src)
        ws.title = _safe_title(str(r[feed.headers[0]]), used)
        if src.print_area:
            ws.print_area = src.print_area.split("!")[-1].replace("$", "")
        for c in range(COL_START, COL_END + 1):
            head = src.cell(HEADER_ROW, c).value
            if head is None:
                continue
            cell = ws.cell(DATA_ROW, c)
            if isinstance(cell.value, str) and cell.value.startswith("="):
                continue
            v = r.get(str(head).strip())
            cell.value = "TBA" if v in (None, "") else v
        made.append((ws.title, src.title))
    for name in list(type_sheets):
        del wb[name]
    buf = io.BytesIO()
    wb.save(buf)
    return _inject_type_drawings(buf.getvalue(), template_bytes, made)


def _inject_type_drawings(out_bytes: bytes, template_bytes: bytes, made: list[tuple[str, str]]) -> bytes:
    """Each generated sheet gets the drawing (wires, terminals, shields) of ITS loop type's template sheet."""
    from utils.workbook_assembly import _sheet_drawings, _sheet_paths, ET, _resolve
    try:
        zt = zipfile.ZipFile(io.BytesIO(template_bytes))
        zo = zipfile.ZipFile(io.BytesIO(out_bytes))
        t_dr = _sheet_drawings(zt)
        o_paths = _sheet_paths(zo)
        names = zo.namelist()
        ct = zo.read("[Content_Types].xml").decode()
        replace: dict[str, bytes] = {}
        for i, (new_title, type_title) in enumerate(made, 1):
            if type_title not in t_dr or new_title not in o_paths:
                continue
            dn = f"xl/drawings/loopdrw{i}.xml"
            replace[dn] = zt.read(t_dr[type_title])
            sp = o_paths[new_title]
            relp = sp.replace("worksheets/", "worksheets/_rels/") + ".rels"
            rel = f'<Relationship Id="rIdLoopDrw" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="/{dn}"/>'
            if relp in names:
                replace[relp] = zo.read(relp).decode().replace("</Relationships>", rel + "</Relationships>").encode()
            else:
                replace[relp] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                 + rel + "</Relationships>").encode()
            sx = zo.read(sp).decode()
            if "xmlns:r=" not in sx[:700]:
                sx = sx.replace("<worksheet ", '<worksheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ', 1)
            for anchor in ("<legacyDrawing", "<tableParts", "</worksheet>"):
                if anchor in sx:
                    sx = sx.replace(anchor, '<drawing r:id="rIdLoopDrw"/>' + anchor, 1)
                    break
            replace[sp] = sx.encode()
            ct = ct.replace("</Types>", f'<Override PartName="/{dn}" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/></Types>')
        replace["[Content_Types].xml"] = ct.encode()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n in names:
                z.writestr(n, replace.pop(n, None) if n in replace else zo.read(n))
            for n, data in replace.items():
                z.writestr(n, data)
        result = buf.getvalue()
        openpyxl.load_workbook(io.BytesIO(result), read_only=True).close()
        return result
    except Exception:
        return out_bytes
