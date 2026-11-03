"""
loop_from_assignment.py - feed the Loop Wiring template from the standard I/O Assignment workbook.

    IO_ASSIGNMENT sheet (one row per tag)
        -> columns re-ordered to the loop template's data columns (W18:AR18)   [build_loop_input]
        -> loop type chosen per row                                            [classify]
        -> one sheet per tag copied from the matching sheet of the loop template, row 19 filled   [generate]

One LOOP = all hardwired signals that share a loop name = one sheet. Loop type:
  * motor loop (any signal with an ML / MC tag token, a MOTOR description or SUB SYSTEM MCC / VFD): all its signals go
    to ONE sheet - "MOTOR - VFD" when the loop has a VFD sub system or speed signals, else "MOTOR - STANDARD";
  * single AI signal: WIRE TYPE 2 WIRE -> "2-WIRE INSTRUMENT", 4 WIRE -> "4-WIRE INSTRUMENT";
  * single DI signal that is a level / flow / pressure / temperature switch -> "SWITCH - LEVEL|FLOW|PRESSURE|TEMPERATURE".
Everything else is reported as "not mapped" with the reason - nothing is guessed.
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


LOOP_MOTOR, LOOP_VFD = "MOTOR - STANDARD", "MOTOR - VFD"
SWITCH_TYPES = {"LEVEL": "SWITCH - LEVEL", "FLOW": "SWITCH - FLOW", "PRESSURE": "SWITCH - PRESSURE", "TEMPERATURE": "SWITCH - TEMPERATURE"}
SWITCH_LETTER = {"L": "LEVEL", "F": "FLOW", "P": "PRESSURE", "T": "TEMPERATURE"}
MOTOR_BLOCKS = ["LOCAL/REMOTE", "RUN", "READY", "TRIP", "START", "STOP", "CURRENT", "SPEED CONTROL", "SPEED FEEDBACK"]   # template order
MOTOR_STD_BLOCKS = MOTOR_BLOCKS[:7]


def classify(io_type: Any, wire_type: Any) -> tuple[Optional[str], str]:
    """Single AI signal -> (loop type, '') or (None, reason)."""
    io, wire = _norm(io_type), _norm(wire_type)
    if io != "AI":
        return None, f"I/O TYPE '{io or '-'}' has no loop template yet"
    if wire == "2 WIRE":
        return LOOP_2W, ""
    if wire == "4 WIRE":
        return LOOP_4W, ""
    return None, f"AI with WIRE TYPE '{wire or '-'}' (expected 2 WIRE or 4 WIRE)"


def _tokens(tag: Any) -> list[str]:
    return [t for t in re.split(r"[-\s]+", str(tag or "").upper()) if t]


def _desc(r: dict) -> str:
    return _norm(r.get("SIGNAL DESCRIPTION"))


def is_motor_signal(r: dict) -> bool:
    d = _desc(r)
    toks = _tokens(r.get("TAG NO"))
    return ("ML" in toks or "MC" in toks or (d.startswith("MOTOR") and not d.startswith("MOTORIZED"))
            or _norm(r.get("SUB SYSTEM")) in ("MCC", "VFD"))


def motor_block(r: dict) -> Optional[str]:
    """Which block of the motor sheet this signal belongs to (from its description / I/O type)."""
    d, io = _desc(r), _norm(r.get("I/O TYPE"))
    if "SPEED" in d and ("FEEDBACK" in d or " FB" in d or d.endswith("FB") or io == "AI"):
        return "SPEED FEEDBACK"
    if "SPEED" in d or ("SPD" in d):
        return "SPEED CONTROL"
    if "LOCAL" in d or "REMOTE" in d:
        return "LOCAL/REMOTE"
    if "READY" in d:
        return "READY"
    if "TRIP" in d:
        return "TRIP"
    if "CURRENT" in d:
        return "CURRENT"
    if "RUN" in d.split() or "RUNNING" in d or d.startswith("RUN"):
        return "RUN"
    if "START" in d:
        return "START"                                    # also 'START/STOP COMMAND' (one signal)
    if "STOP" in d:
        return "STOP"
    return None


def switch_kind(r: dict) -> Optional[str]:
    """Level / flow / pressure / temperature switch: ISA function (LS, LSH, LSL, FS, PS, TS ...) or the description."""
    if _norm(r.get("I/O TYPE")) != "DI":
        return None
    for t in _tokens(r.get("TAG NO")):
        m = re.fullmatch(r"([LFPT])S(H|L|HH|LL)?", t)
        if m:
            return SWITCH_LETTER[m.group(1)]
    d = _desc(r)
    for k in SWITCH_TYPES:
        if f"{k} SWITCH" in d:
            return k
    return None


def loop_name_of(r: dict) -> str:
    """LOOP NO when the assignment has one. Otherwise derived from the tag (MODEL INFERENCE): motor tags -> 'ML-<number>'
    (all signals of one motor share it, e.g. ML-11011), others -> '<area>-<first function letter>-<number>'."""
    given = r.get("LOOP NO")
    if given not in (None, "", "-"):
        return str(given).strip()
    return derive_loop_name(r.get("TAG NO"))


# loop-template header (normalised) -> how to obtain it from an IO_ASSIGNMENT row (dict keyed by assignment header)
def derive_loop_name(tag: Any) -> str:
    """'100-YL-ML-10601A' -> 'ML-10601' (motor: all its signals); '100-PIT-10101' -> '100-P-10101'; '6816-LT-3003' -> '6816-L-3003'.
    MODEL INFERENCE - used only when the assignment has no LOOP NO; falls back to the tag."""
    parts = [p for p in re.split(r"-", str(tag).strip()) if p]
    if len(parts) < 2:
        return str(tag).strip()
    m = re.match(r"^(\d{3,})", parts[-1])
    if not m:
        return str(tag).strip()
    toks = [p.upper() for p in parts[:-1]]
    for motor_token in ("ML", "MC"):
        if motor_token in toks:
            return f"{motor_token}-{m.group(1)}"
    letters = next((p for p in parts[1:-1] if re.fullmatch(r"[A-Za-z]{1,5}", p)), "")
    return f"{parts[0]}-{letters[0].upper()}-{m.group(1)}" if parts[0].isdigit() and letters else str(tag).strip()


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
    rows: list[dict] = field(default_factory=list)            # one per placed signal: {header: value, "LOOP", "LOOP TYPE", "BLOCK", "SOURCE ROW"}
    skipped: list[tuple[int, str, str]] = field(default_factory=list)   # (assignment row, tag, reason)
    unfed_headers: list[str] = field(default_factory=list)    # loop headers with no source column

    def loops(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for r in self.rows:
            out.setdefault(r["LOOP"], []).append(r)
        return out


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
    groups: dict[str, list[dict]] = {}
    for r in assignment_rows:
        tag = r.get("TAG NO")
        if tag in (None, "") or _norm(tag) == "SPARE":
            continue
        if _norm(r.get("CHANGE STATUS")) == "DELETED":
            continue
        if _norm(r.get("INTERFACE")) not in ("HARDWIRED", ""):
            feed.skipped.append((r["_row"], str(tag), f"INTERFACE '{r.get('INTERFACE')}' has no field wiring"))
            continue
        groups.setdefault(loop_name_of(r), []).append(r)

    def values(r: dict, loop: str, loop_type: str, block: str) -> dict:
        row = {}
        for h in headers:
            src = FEED_MAP.get(h.strip().upper())
            v = src[0](r) if src else None
            row[h] = None if v in ("", "-") else v
        row["Loop_Name"] = loop
        row.update({"LOOP": loop, "LOOP TYPE": loop_type, "BLOCK": block, "SOURCE ROW": r["_row"]})
        return row

    for loop, rs in groups.items():
        if any(is_motor_signal(r) for r in rs):
            blocks = {r["_row"]: motor_block(r) for r in rs}
            vfd = (any(_norm(r.get("SUB SYSTEM")) == "VFD" for r in rs) or any(b in ("SPEED CONTROL", "SPEED FEEDBACK") for b in blocks.values())
                   or any("VFD" in _desc(r) for r in rs))
            loop_type, allowed, taken = (LOOP_VFD, MOTOR_BLOCKS, set()) if vfd else (LOOP_MOTOR, MOTOR_STD_BLOCKS, set())
            for r in rs:
                b = blocks[r["_row"]]
                if b not in allowed:
                    feed.skipped.append((r["_row"], str(r["TAG NO"]), f"motor loop {loop}: signal '{r.get('SIGNAL DESCRIPTION')}' has no place on the {loop_type} sheet"))
                elif b in taken:
                    feed.skipped.append((r["_row"], str(r["TAG NO"]), f"motor loop {loop}: second '{b}' signal (one per block)"))
                else:
                    taken.add(b)
                    feed.rows.append(values(r, loop, loop_type, b))
            continue
        if len(rs) > 1:
            for r in rs:
                feed.skipped.append((r["_row"], str(r["TAG NO"]), f"loop {loop} has {len(rs)} hardwired signals and is not a motor loop (no template yet)"))
            continue
        r = rs[0]
        kind = switch_kind(r)
        if kind:
            feed.rows.append(values(r, loop, SWITCH_TYPES[kind], ""))
            continue
        loop_type, why = classify(r.get("I/O TYPE"), r.get("WIRE TYPE"))
        if loop_type is None:
            feed.skipped.append((r["_row"], str(r["TAG NO"]), why))
        else:
            feed.rows.append(values(r, loop, loop_type, ""))
    return feed


def feed_to_xlsx(feed: LoopFeed) -> bytes:
    """The loop-template data columns laid side by side (header row, then one row per tag) + LOOP TYPE."""
    df = pd.DataFrame(feed.rows, columns=feed.headers + ["LOOP TYPE", "BLOCK", "SOURCE ROW"])
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
    for loop, rs in feed.loops().items():
        loop_type = rs[0]["LOOP TYPE"]
        src = type_sheets[loop_type]
        ws = wb.copy_worksheet(src)
        ws.title = _safe_title(loop, used)
        if src.print_area:
            ws.print_area = src.print_area.split("!")[-1].replace("$", "")
        by_block = {r["BLOCK"]: r for r in rs} if loop_type in (LOOP_MOTOR, LOOP_VFD) else {}
        order = (MOTOR_BLOCKS if loop_type == LOOP_VFD else MOTOR_STD_BLOCKS) if by_block else [""]
        for k, blk in enumerate(order):                              # motors: one data row per block, in template order
            r = by_block.get(blk) if by_block else rs[0]
            for c in range(COL_START, COL_END + 1):
                head = src.cell(HEADER_ROW, c).value
                if head is None:
                    continue
                cell = ws.cell(DATA_ROW + k, c)
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    continue
                name = str(head).strip()
                v = (r or {}).get(name) if r else (loop if name == "Loop_Name" else None)
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
