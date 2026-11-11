"""
cable_schedule_extra.py - MCC DI, MCC DO, VFD, MOV and LCP cable-schedule sheets.

    Shared IODB -> common normaliser -> per-sheet eligibility + physical grouping -> reference layout

One data engine (this module's `normalize`), sheet specific filtering/grouping, and the layouts of the
approved Digha reference (backend/app/templates/cable_schedule/cable_schedule_reference.xlsx). The existing
Instrument Cable Schedule generator is not touched; it only calls `add_extra_sheets` after its own sheet is done.

Rules (all from the specification):
  * IODB columns are found by header NAME (aliases), never by position; reference columns are found by their
    header text, so a re-laid-out reference keeps working.
  * One IODB record = one schedule row. Physical equipment (loop number) and shared main cables only decide
    which rows are grouped / merged - rows are never collapsed.
  * Nothing technical is invented: missing -> TBA, '-' -> NA. Cable numbers are never generated.
  * The IODB itself is never modified (the filters work on normalised copies).
"""
from __future__ import annotations

import io
import math
import re
from collections import OrderedDict
from copy import copy, deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import openpyxl
from openpyxl.drawing.image import Image as XlImage
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import column_index_from_string, get_column_letter

from .cable_summary import _norm_col, parse_length, resolve_cable_fields

REFERENCE_PATH = Path(__file__).resolve().parent.parent / "backend" / "app" / "templates" / "cable_schedule" / "cable_schedule_reference.xlsx"

# ── sheets ────────────────────────────────────────────────────────────────────
SHEETS: "OrderedDict[str, dict]" = OrderedDict([
    ("mcc_di", dict(label="MCC DI", ref="MCC-DI", hdr=(9, 10), first=11, block_end=21, io=("DI",),
                    block_fields=("sl", "from", "cable_size", "end_gland_size", "end_gland_qty", "panel_gland_size",
                                  "panel_gland_qty", "length", "sigtype"),
                    cable_fields=(), by_device=False, classes=None, from_text="FROM  MCC TO PLC", section="MCC")),
    ("mcc_do", dict(label="MCC DO", ref="MCC-DO", hdr=(9, 10), first=11, block_end=14, io=("DO",),
                    block_fields=("sl", "from", "cable_no", "cable_size", "end_gland_size", "end_gland_qty",
                                  "panel_gland_size", "panel_gland_qty", "length", "sigtype"),
                    cable_fields=(), by_device=False, classes=None, from_text="FROM  MCC TO PLC ", section="MCC")),
    ("vfd", dict(label="VFD", ref="VFD", hdr=(9, 10), first=11, block_end=16, io=("DI", "DO", "AI", "AO"),
                 block_fields=("sl", "from", "panel_gland_size", "panel_gland_qty", "length"),
                 cable_fields=("cable_no", "cable_size", "end_gland_size", "end_gland_qty"),
                 by_device=True, classes={"DI": "DIGITAL", "DO": "DIGITAL", "AI": "AI", "AO": "AO"},
                 from_text="FROM  VFD TO PLC ", section="VFD")),
    ("mov", dict(label="MOV", ref="MOV Cable (2)", hdr=(10, 11), first=12, block_end=18, io=("DI", "DO"),
                 block_fields=("sl", "from", "cable_no", "cable_size", "end_gland_size", "end_gland_qty",
                               "panel_gland_size", "panel_gland_qty", "length"),
                 cable_fields=(), by_device=True, classes=None,
                 from_text="FROM  MOV TO CONTROL DESK", section="MOV")),
    ("lcp", dict(label="LCP", ref="LCP", hdr=(9, 10), first=11, block_end=17, io=("DI", "DO", "AI", "AO", "RTD"),
                 block_fields=("sl", "from", "end_gland_size", "end_gland_qty", "panel_gland_size",
                               "panel_gland_qty", "length"),
                 cable_fields=("cable_no", "cable_size"),
                 by_device=True, classes={"DI": "DI", "DO": "DO", "AI": "AI", "AO": "AO", "RTD": "RTD"},
                 from_text="FROM  LCP TO PLC ", section="LCP")),
])
LABEL_TO_KEY = {v["label"]: k for k, v in SHEETS.items()}


class ExtraSheetError(Exception):
    """User-facing problem with the extra cable-schedule sheets."""


# ── IODB normaliser (the common record) ──────────────────────────────────────
ALIASES: dict[str, list[str]] = {
    "tag_no": ["TAG NO", "TAG NUMBER", "TAG", "INSTRUMENT TAG", "TAG_NUMBER NEW", "TAG NUMBER NEW"],
    "loop_number": ["LOOP NUMBER", "LOOP NO", "LOOP NAME", "LOOP"],
    "equipment_description": ["EQUIPMENT DESCRIPTION", "EQUIPMENT DESC", "EQUIP NAME"],
    "signal_description": ["SIGNAL DESCRIPTION", "SERVICE DESCRIPTION", "SIGNAL DESC"],
    "instrument_type": ["INSTRUMENT TYPE NAME", "INSTRUMENT TYPE", "INSTRUMENT TYPE DESC"],
    "io_type": ["SIGNAL I O TYPE", "SIGNAL IO TYPE", "IO TYPE NAME", "IO TYPE", "I O TYPE"],
    "sub_system": ["SUB SYSTEM", "SUBSYSTEM"],
    "system": ["SYSTEM"],
    "vendor_package": ["VENDOR PACKAGE", "VENDOR PKG"],
    "equipment_no": ["EQUIPMENT NO", "EQUIPMENT NUMBER", "EQUIPMENT TAG"],
    "pid": ["P ID NO", "P ID", "P ID NUMBER", "PID NO"],
    "signal_to_from": ["SIGNAL TO FROM", "SIGNAL TO", "SIGNAL FROM"],
    "new_tag_no": ["NEW TAG NO", "NEW TAG NUMBER"],
    "jb_tag": ["JUNCTION BOX TAG NO", "JUNCTION BOX TAG", "JB TAG NO", "JB TAG", "JUNCTION BOX", "JB NO"],
    "branch_cable_tag": ["INSTRUMENT TO JB CABLE TAG NO", "INSTRUMENT TO JB CABLE TAG", "BRANCH CABLE TAG"],
    "main_cable_tag": ["MAIN CABLE TAG NUMBER", "MAIN CABLE TAG NO", "MAIN CABLE TAG", "MAIN CABLE NO"],
    "instrument_gland_size": ["INSTRUMENT SIDE GLAND SIZE", "INSTRUMENT GLAND SIZE", "INSTRUMENT SIDE GLAND",
                              "MCC SIDE GLAND SIZE", "VFD SIDE GLAND SIZE", "LCP SIDE GLAND SIZE"],
    "instrument_gland_qty": ["INSTRUMENT SIDE GLAND QTY", "INSTRUMENT GLAND QTY", "INSTRUMENT SIDE GLAND QUANTITY"],
    "jb_gland_size": ["JB SIDE GLAND SIZE", "JB END GLAND SIZE"],
    "jb_gland_qty": ["JB SIDE GLAND QTY"],
    "panel_gland_size": ["PANEL END GLAND SIZE", "PANEL SIDE GLAND SIZE"],
    "panel_gland_qty": ["PANEL END GLAND QTY", "PANEL SIDE GLAND QTY"],
    "jb_terminal_positive": ["JB TERMINAL POSITIVE", "JB TERMINAL 1", "TERMINAL POSITIVE"],
    "jb_terminal_negative": ["JB TERMINAL NEGATIVE", "JB TERMINAL 2", "TERMINAL NEGATIVE"],
    "jb_terminal_shield": ["JB TERMINAL SHIELD", "TERMINAL SHIELD"],
    "unit_no": ["MCC NO", "VFD NO", "LCP NO", "MCC TAG", "VFD TAG", "LCP TAG"],
    "mtb_no": ["MTB NO", "MARSHALLING TB NO"],
    "panel": ["IO PANEL", "RIO PANEL", "PANEL NO", "PANEL"],
    "drop": ["DROP", "DROP NO"],
    "rack": ["RACK NODE", "RACK", "RACK NO", "NODE"],
    "slot": ["SLOT", "SLOT NO", "PLC DCS MODULE NO", "MODULE NO"],
    "channel": ["CHANNEL NO", "CHANNEL"],
    "terminal_strip": ["TERMINAL STRIP NO", "TERMINAL STRIP", "MAIN TB NAME", "MAIN TB NO"],
    "terminal_common": ["TERMINAL NO COMM", "TERMINAL NO COMMON"],
    "terminal_signal": ["TERMINAL NO SIGNAL", "TERMINAL NO"],
    "terminal_zero": ["TERMINAL NO ZERO"],
    "card_no": ["CARD NO"],
    "is_nis": ["IS NIS TYPE", "IS NIS", "IS NIS CLASS"],
    "power_supply": ["POWER SUPPLY"],
    "remarks": ["REMARKS", "REMARK"],
}
# the four fields the cable summary already resolves (unit suffixes such as (Mtrs) are handled there)
_CABLE_FIELDS = {"INSTRUMENT_TO_JB_CABLE_TYPE": "branch_cable_type", "BRANCH_CABLE_LENGTH": "branch_cable_length",
                 "MAIN_CABLE_TYPE": "main_cable_type", "MAIN_CABLE_LENGTH": "main_cable_length"}
_PLACEHOLDER = {"", "-", "--", "NA", "N/A", "NAN", "NONE", "NULL", "NIL", "TBA", "TBD"}


def clean(value: Any) -> Optional[str]:
    """Stripped text, or None for blank/NaN."""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value == int(value):
            value = int(value)
    text = re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()
    return text or None


def is_missing(text: Optional[str]) -> bool:
    return text is None or text.upper() in _PLACEHOLDER


def show(text: Optional[str]) -> str:
    """Reference convention: blank / TBA -> TBA, '-' / NA -> NA."""
    if text is None or text.upper() in ("", "TBA", "TBD", "NAN", "NONE", "NULL"):
        return "TBA"
    if text.upper() in ("-", "--", "NA", "N/A", "NIL"):
        return "NA"
    return text


@dataclass
class Rec:
    """One normalised IODB record (the shared engineering record; every field is optional text)."""
    row: int                                     # IODB row number (Excel, 1-based, header = 1)
    f: dict[str, Optional[str]] = field(default_factory=dict)

    def __getattr__(self, name):                 # rec.tag_no etc.
        try:
            return self.__dict__["f"].get(name)
        except KeyError:
            raise AttributeError(name)

    @property
    def io(self) -> str:
        v = (self.f.get("io_type") or "").upper().strip()
        return {"DIGITAL INPUT": "DI", "DIGITAL OUTPUT": "DO", "ANALOG INPUT": "AI", "ANALOG OUTPUT": "AO"}.get(v, v)


def resolve_columns(columns) -> dict[str, Optional[str]]:
    """canonical field -> actual IODB header (None when absent). Header text only, never a position."""
    norm: dict[str, str] = {}
    for c in columns:
        norm.setdefault(_norm_col(c), c)
    out: dict[str, Optional[str]] = {}
    for name, aliases in ALIASES.items():
        out[name] = next((norm[_norm_col(a)] for a in aliases if _norm_col(a) in norm), None)
    for cname, actual in resolve_cable_fields(columns).items():
        out[_CABLE_FIELDS[cname]] = actual
    # two-row headers ("INSTRUMENT TO JB CABLE" over "TYPE") leave the first row's text as the only header
    if not out.get("branch_cable_type"):
        out["branch_cable_type"] = norm.get(_norm_col("INSTRUMENT TO JB CABLE"))
    # a terminal pair is written as two columns "JB TERMINAL +" / "JB TERMINAL -": '+' and '-' are stripped by
    # _norm_col, so look at the raw header too
    for c in columns:
        raw = str(c).upper().replace(" ", "")
        if raw.startswith("JBTERMINAL") and raw.endswith("+") and not out.get("jb_terminal_positive"):
            out["jb_terminal_positive"] = c
        if raw.startswith("JBTERMINAL") and raw.endswith("-") and not out.get("jb_terminal_negative"):
            out["jb_terminal_negative"] = c
    return out


def normalize(df) -> tuple[list[Rec], dict[str, Optional[str]]]:
    """DataFrame (as read by the existing IODB reader) -> normalised records. The frame is not modified."""
    cols = resolve_columns(list(df.columns))
    if not cols.get("tag_no") and not cols.get("io_type"):
        raise ExtraSheetError("The IODB has no TAG NO / SIGNAL I/O TYPE columns, so the MCC / VFD / MOV / LCP "
                              "sheets cannot be built from it.")
    recs: list[Rec] = []
    series = {k: df[v].tolist() for k, v in cols.items() if v}
    index = list(df.index)
    for pos in range(len(df)):
        f = {k: clean(series[k][pos]) for k in series}
        if not f.get("tag_no") and not f.get("io_type"):
            continue                                            # sub-header / blank row
        idx = index[pos]
        recs.append(Rec(row=int(idx) + 2 if isinstance(idx, (int, float)) else pos + 2, f=f))
    return recs, cols


# ── eligibility ──────────────────────────────────────────────────────────────
_VFD = re.compile(r"\b(VFD|VSD|VFDS)\b|VARIABLE\s+(FREQUENCY|SPEED)")
_MOV = re.compile(r"\bMOV\b|MOTOR[\s-]*OPERATED\s+(VALVE|GATE|DAMPER)")
_MOV_TYPE = re.compile(r"MOTORI[SZ]ED\s+\w*\s*(GATE|VALVE|DAMPER)")
_LCP = re.compile(r"\bLCP\b|LOCAL\s+CONTROL\s+PANEL|\bLCS\b")
_MCC = re.compile(r"\bMCC\b")
HARDWIRED = {"DI", "DO", "AI", "AO", "RTD", "TC"}


def classify(rec: Rec) -> Optional[str]:
    """Which extra sheet (if any) a record belongs to. A record belongs to at most one."""
    io = rec.io
    if io not in HARDWIRED:
        return None                                              # SOFT / '-' points have no field cable
    sub = (rec.sub_system or "").upper()
    loop = (rec.loop_number or "").upper()
    names = " ".join(filter(None, [rec.equipment_description, rec.signal_description, rec.instrument_type,
                                   rec.vendor_package, rec.equipment_no])).upper()
    if _LCP.search(sub) or _LCP.search(names):
        return "lcp" if io in SHEETS["lcp"]["io"] else None
    is_mov = bool(re.match(r"MOV\b|MOV-", loop)) or bool(_MOV.search(sub)) or bool(_MOV.search(names)) \
        or (bool(_MOV_TYPE.search((rec.instrument_type or "").upper())) and not (_MCC.search(sub) or _VFD.search(sub)))
    if is_mov:
        return "mov" if io in SHEETS["mov"]["io"] else None
    if _VFD.search(sub) or _VFD.search(names):
        return "vfd" if io in SHEETS["vfd"]["io"] else None
    if _MCC.search(sub) or _MCC.search((rec.signal_to_from or "").upper()):
        return {"DI": "mcc_di", "DO": "mcc_do"}.get(io)
    return None


def split_records(recs: list[Rec]) -> dict[str, list[Rec]]:
    out: dict[str, list[Rec]] = {k: [] for k in SHEETS}
    for r in recs:
        k = classify(r)
        if k:
            out[k].append(r)
    return out


def device_key(rec: Rec) -> str:
    """Physical equipment: the loop number; then equipment no.; then the tag without its signal suffix."""
    if not is_missing(rec.loop_number):
        return rec.loop_number.upper()
    if not is_missing(rec.equipment_no):
        return rec.equipment_no.upper()
    tag = (rec.tag_no or "").upper()
    return re.sub(r"[A-Z]$", "", tag) or f"ROW{rec.row}"


def is_spare(rec: Rec) -> bool:
    return any("SPARE" in (v or "").upper() for v in (rec.tag_no, rec.signal_description, rec.equipment_description))


# ── grouping ─────────────────────────────────────────────────────────────────
@dataclass
class CableGroup:
    key: str
    recs: list[Rec]
    tag: Optional[str] = None
    ctype: Optional[str] = None
    length: Optional[str] = None
    conflicts: list[str] = field(default_factory=list)


@dataclass
class Block:
    devices: list[str]
    groups: list[CableGroup]

    @property
    def rows(self) -> int:
        return sum(len(g.recs) for g in self.groups)


def _first_value(recs: list[Rec], name: str) -> tuple[Optional[str], bool]:
    vals = [r.f.get(name) for r in recs if not is_missing(r.f.get(name))]
    if not vals:
        # nothing usable: '-' / NA in the IODB means "not applicable" and is shown as NA; blank/TBA stays TBA
        na = next((r.f.get(name) for r in recs if (r.f.get(name) or "").upper() in ("-", "--", "NA", "N/A", "NIL")), None)
        return na, False
    distinct = list(OrderedDict.fromkeys(vals))
    return vals[0], len(distinct) > 1


def plan_blocks(key: str, recs: list[Rec]) -> list[Block]:
    """Physical grouping: devices -> shared main cables -> blocks of the reference layout."""
    spec = SHEETS[key]
    n = len(recs)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    by_tag: dict[str, int] = {}
    by_dev: dict[str, int] = {}
    for i, r in enumerate(recs):
        tag = None if is_missing(r.main_cable_tag) else r.main_cable_tag.upper()
        if tag:
            union(i, by_tag.setdefault(tag, i))          # a cable shared by several devices keeps them in one block
        union(i, by_dev.setdefault(device_key(r), i))    # all signals of one pump / drive / MOV are one block
    comp: "OrderedDict[int, list[int]]" = OrderedDict()
    for i in range(n):
        comp.setdefault(find(i), []).append(i)

    blocks: list[Block] = []
    for members in comp.values():
        rs = [recs[i] for i in members]
        groups: "OrderedDict[str, list[Rec]]" = OrderedDict()
        for r in rs:
            # rows of the same cable type in one block are ONE cable laid to the equipment (Digha reference), whatever
            # their individual tag cells say; the cable is shown once and the cells are merged
            if not is_missing(r.main_cable_type):
                gk = "Y:" + re.sub(r"\s+", "", r.main_cable_type.upper())
            elif not is_missing(r.main_cable_tag):
                gk = "T:" + r.main_cable_tag.upper()
            elif spec["classes"]:
                gk = "C:" + device_key(r) + "|" + spec["classes"].get(r.io, r.io)
            else:
                gk = "D:" + device_key(r)
            groups.setdefault(gk, []).append(r)
        cgs = []
        for gk, grs in groups.items():
            cg = CableGroup(key=gk, recs=grs)
            for attr, name in (("tag", "main_cable_tag"), ("ctype", "main_cable_type"), ("length", "main_cable_length")):
                val, conflict = _first_value(grs, name)
                setattr(cg, attr, val)
                if conflict:
                    cg.conflicts.append(name)
            cgs.append(cg)
        blocks.append(Block(devices=list(OrderedDict.fromkeys(device_key(r) for r in rs)), groups=cgs))
    return blocks


# ── availability / validation (messages for the screen and the generator) ────
def sheet_stats(key: str, recs: list[Rec], blocks: Optional[list[Block]] = None) -> dict:
    blocks = blocks if blocks is not None else plan_blocks(key, recs)
    label = SHEETS[key]["label"]
    cables = {g.tag.upper() for b in blocks for g in b.groups if g.tag}
    no_tag = sum(1 for r in recs if is_missing(r.main_cable_tag))
    no_type = sum(1 for r in recs if is_missing(r.main_cable_type))
    no_len = sum(1 for r in recs if is_missing(r.main_cable_length))
    warnings: list[str] = []
    if recs and (no_tag or no_type or no_len):
        warnings.append(f"{len(recs)} {label} signals were found, but {max(no_tag, no_type)} are missing main cable "
                        f"information and {no_len} a cable length. Those rows will be generated with TBA.")
    for b in blocks:
        for g in b.groups:
            if g.conflicts:
                warnings.append(f"Cable {g.tag or g.key}: different {', '.join(c.replace('_', ' ') for c in g.conflicts)} "
                                "values in the IODB for the same cable; the first one is used.")
    return {"key": key, "label": label, "records": len(recs), "devices": len({device_key(r) for r in recs}),
            "cables": len(cables) if cables else 0, "blocks": len(blocks), "spare": sum(1 for r in recs if is_spare(r)),
            "warnings": warnings[:12]}


def availability(df) -> dict:
    """Per sheet: can it be generated from this IODB, and why not."""
    recs, cols = normalize(df)
    parts = split_records(recs)
    out = {}
    ref_ok = REFERENCE_PATH.exists()
    skipped_ios = sum(1 for r in recs if r.io in HARDWIRED and classify(r) is None)
    for key, spec in SHEETS.items():
        rs = parts[key]
        st = sheet_stats(key, rs) if rs else {"key": key, "label": spec["label"], "records": 0, "devices": 0,
                                               "cables": 0, "blocks": 0, "spare": 0, "warnings": []}
        reason = None
        if not ref_ok:
            reason = f"The {spec['label']} reference layout is not installed on the server."
        elif not rs:
            what = {"mcc_di": "DI signals from an MCC (SUB SYSTEM = MCC)", "mcc_do": "DO signals to an MCC (SUB SYSTEM = MCC)",
                    "vfd": "signals of VFD-driven equipment (SUB SYSTEM = VFD)", "mov": "MOV signals (LOOP NUMBER MOV-...)",
                    "lcp": "LCP signals"}[key]
            reason = (f"LCP schedule cannot be generated because required LCP source data is unavailable: "
                      f"the IODB has no {what}." if key == "lcp" else f"The IODB has no {what}.")
        elif not cols.get("io_type"):
            reason = "The IODB has no SIGNAL I/O TYPE column."
        out[key] = {**st, "available": reason is None, "reason": reason}
    out["_summary"] = {"records": len(recs), "hardwired_unassigned": skipped_ios}
    return out


# ── reference sheet access (header text -> column) ───────────────────────────
FIELD_HEADERS: dict[str, tuple[Optional[str], Optional[str]]] = {
    # field: (regex on the group header (row 9), regex on the sub header (row 10))
    "sl": (r"^sl", None), "from": (r"^from", None), "desc": (r"^description", None),
    "tag": (r"^tag no", None), "new_tag": (r"^new tag", None),
    "cable_no": (r"^cable no", None), "cable_size": (r"^cable size", None),
    "end_gland_size": (r"(mcc|vfd|lcp|instrument) side gland", r"^gland size"),
    "end_gland_qty": (r"(mcc|vfd|lcp|instrument) side gland", r"^gland qty"),
    "end_unit": (r"^tb details at", r"^(mcc|vfd|lcp) no"),
    "end_mtb": (r"^tb details at", r"^mtb no"),
    "end_pos": (r"^tb details at", r"^positive"), "end_neg": (r"^tb details at", r"^negative"),
    "to_jb": (r"^to \(jb\)", None),
    "panel_gland_size": (r"^panel side gland", r"^gland size"),
    "panel_gland_qty": (r"^panel side gland", r"^gland qty"),
    "length": (r"^cable length", None),
    "cd_panel": (r"^(control desk terminals|plc$)", r"^(rio panel|panel no)"),
    "cd_drop": (r"^control desk terminals", r"^drop"), "cd_rack": (r"^control desk terminals", r"^rack"),
    "cd_slot": (r"^control desk terminals", r"^slot"),
    "cd_main_tb": (r"^(control desk terminals|plc$)", r"^main tb"),
    "cd_tb": (r"^(control desk terminals|plc$)", r"^tb no"),
    "cd_card": (r"^control desk terminals", r"^card no"),
    "cd_pos": (r"^control desk terminals", r"^positive"), "cd_neg": (r"^control desk terminals", r"^negative"),
    "sigtype": (r"^signal type", None), "remarks": (r"^remarks", None),
}


def _cell_text(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def header_columns(ws, hdr: tuple[int, int]) -> dict[str, list[int]]:
    """field -> columns (left to right) whose header text matches; read from the sheet, never assumed."""
    top_r, sub_r = hdr
    spans = [(m.min_col, m.max_col) for m in ws.merged_cells.ranges if m.min_row <= top_r <= m.max_row]
    tops: list[tuple[int, int, str]] = []
    for c in range(1, min(ws.max_column, 60) + 1):
        t = _cell_text(ws.cell(top_r, c).value)
        if t:
            end = next((e for (s, e) in spans if s == c), c)
            tops.append((c, end, t))
    out: dict[str, list[int]] = {}
    for c in range(1, min(ws.max_column, 60) + 1):
        sub = _cell_text(ws.cell(sub_r, c).value)
        top_own = _cell_text(ws.cell(top_r, c).value)
        top = top_own or next((t for (s, e, t) in reversed(tops) if s <= c <= e), "")
        if not top:
            top = next((t for (s, e, t) in reversed(tops) if s <= c), "")
        for fld, (tp, sp) in FIELD_HEADERS.items():
            if sp is None:
                if top_own and re.search(tp, top_own) and not sub:
                    out.setdefault(fld, []).append(c)
            elif sub and re.search(sp, sub) and top and re.search(tp, top):
                out.setdefault(fld, []).append(c)
    return out


def _separator_cols(ws, row: int) -> tuple[Optional[int], Optional[int]]:
    """(dash column, slash column): the helper cells the ferrule formulas concatenate."""
    dash = slash = None
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row, c).value
        if v in ("−", "-") and dash is None and c > 25:
            dash = c
        elif v == "/" and slash is None and c > 25:
            slash = c
    return dash, slash


# ── writing ──────────────────────────────────────────────────────────────────
_THIN = Side(style="thin", color="000000")


def _adjust(formula: str, src: int, dst: int) -> str:
    if dst == src or not (isinstance(formula, str) and formula.startswith("=")):
        return formula
    off = dst - src
    return re.sub(r"(\$?[A-Za-z]{1,3})(\$?)(\d+)",
                  lambda m: m.group(0) if m.group(2) else f"{m.group(1)}{int(m.group(3)) + off}", formula)


def _style_from(dst, src):
    dst._style = copy(src._style)


def _outline(ws, rng: str):
    from openpyxl.worksheet.cell_range import CellRange
    cr = CellRange(rng)
    for r in range(cr.min_row, cr.max_row + 1):
        for c in range(cr.min_col, cr.max_col + 1):
            cell = ws.cell(r, c)
            b = cell.border
            cell.border = Border(left=_THIN if c == cr.min_col else b.left, right=_THIN if c == cr.max_col else b.right,
                                 top=_THIN if r == cr.min_row else b.top, bottom=_THIN if r == cr.max_row else b.bottom)


def _description(rec: Rec) -> str:
    eq, sig = rec.equipment_description, rec.signal_description
    parts = [p for p in (eq, sig) if not is_missing(p)]
    if len(parts) == 2 and sig.upper() in eq.upper():
        parts = [eq]
    return " ".join(parts) if parts else "TBA"


def _remarks(rec: Rec) -> Optional[str]:
    """IS / NIS classification (as the IODB states it) followed by the IODB remarks."""
    cls = rec.is_nis.upper() if not is_missing(rec.is_nis) and rec.is_nis.upper() in ("IS", "NIS") else None
    parts = [p for p in (cls, rec.remarks if not is_missing(rec.remarks) else None) if p]
    return " - ".join(parts) if parts else None


def _row_values(key: str, rec: Rec, group: CableGroup) -> dict[str, Any]:
    """Cell values of one signal row, by reference field. Everything comes from the IODB; absent -> TBA."""
    sig = show(rec.terminal_signal)
    common = rec.terminal_common if not is_missing(rec.terminal_common) else rec.terminal_zero
    v = {
        "desc": _description(rec), "tag": show(rec.tag_no), "new_tag": show(rec.new_tag_no),
        "end_unit": show(rec.unit_no), "end_mtb": show(rec.mtb_no),
        "end_pos": show(rec.jb_terminal_positive), "end_neg": show(rec.jb_terminal_negative),
        "to_jb": show(rec.jb_tag),
        "cd_panel": show(rec.panel), "cd_drop": show(rec.drop), "cd_rack": show(rec.rack), "cd_slot": show(rec.slot),
        "cd_main_tb": show(rec.terminal_strip), "cd_tb": sig, "cd_card": show(rec.card_no or rec.slot),
        "cd_pos": sig, "cd_neg": show(common),
        "sigtype": rec.io or "TBA", "remarks": None,
        "cd_tb2": show(common),
    }
    return v


def _block_values(key: str, block: Block, serial: int) -> dict[str, Any]:
    first = block.groups[0].recs[0]
    allrecs = [r for g in block.groups for r in g.recs]
    gs, _ = _first_value(allrecs, "instrument_gland_size")
    gq, _ = _first_value(allrecs, "instrument_gland_qty")
    ps, _ = _first_value(allrecs, "panel_gland_size")
    pq, _ = _first_value(allrecs, "panel_gland_qty")
    ln = next((g.length for g in block.groups if g.length and parse_length(g.length)[1] == "ok"), None)
    if ln is None:
        ln = next((g.length for g in block.groups if g.length), None)
    d = {"sl": serial, "end_gland_size": show(gs), "end_gland_qty": show(gq),
         "panel_gland_size": show(ps), "panel_gland_qty": show(pq), "length": show(ln)}
    if key == "mov":
        d["from"] = block.devices[0]
    g0 = block.groups[0]
    d["cable_no"] = show(g0.tag)
    d["cable_size"] = show(g0.ctype)
    return d


def _cable_values(group: CableGroup) -> dict[str, Any]:
    recs = group.recs
    gs, _ = _first_value(recs, "instrument_gland_size")
    gq, _ = _first_value(recs, "instrument_gland_qty")
    return {"cable_no": show(group.tag), "cable_size": show(group.ctype),
            "end_gland_size": show(gs), "end_gland_qty": show(gq)}


def build_sheet(ref_wb, key: str, recs: list[Rec], info: dict) -> tuple[Any, dict]:
    """Populate the reference sheet for `key` inside `ref_wb` (a fresh copy of the reference) -> (ws, stats)."""
    spec = SHEETS[key]
    ws = ref_wb[spec["ref"]]
    cols = header_columns(ws, spec["hdr"])
    first, proto_end = spec["first"], spec["block_end"]
    max_col = min(ws.max_column, 70)
    sep_dash, sep_slash = _separator_cols(ws, first + 1)

    def col(fld, nth=0):
        c = cols.get(fld)
        return c[nth] if c and len(c) > nth else None

    # signal rows: field -> column (cd_tb2 is the second 'TB NO' of the control desk group)
    fcol = {f: col(f) for f in FIELD_HEADERS if col(f)}
    if col("cd_tb", 1):
        fcol["cd_tb2"] = col("cd_tb", 1)

    # ── snapshot of the prototype block (formulas + styles), then clear it ──
    proto_first, proto_mid, proto_last = first, min(first + 1, proto_end), proto_end
    snap: dict[str, dict[int, tuple]] = {}
    for tag, r in (("first", proto_first), ("mid", proto_mid), ("last", proto_last)):
        snap[tag] = {c: (ws.cell(r, c).value if type(ws.cell(r, c)).__name__ != "MergedCell" else None,
                         copy(ws.cell(r, c)._style), r) for c in range(1, max_col + 1)}
    row_h = {t: ws.row_dimensions[r].height for t, r in (("first", proto_first), ("mid", proto_mid), ("last", proto_last))}
    for rng in [str(m) for m in ws.merged_cells.ranges if m.min_row >= first]:
        ws.unmerge_cells(rng)
    for r in range(first, proto_end + 1):
        for c in range(1, max_col + 1):
            ws.cell(r, c).value = None

    # title block
    _fill_title(ws, spec, info)

    stats = sheet_stats(key, recs)
    blocks = plan_blocks(key, recs)
    r = first
    serial = 0
    resolved_fields = set(fcol)

    def style_row(row: int, pos: str):
        src = snap[pos]
        for c in range(1, max_col + 1):
            ws.cell(row, c)._style = copy(src[c][1])
        if row_h.get(pos):
            ws.row_dimensions[row].height = row_h[pos]

    for block in blocks:
        serial += 1
        n = block.rows
        bv = _block_values(key, block, serial)
        r0, r1 = r, r + n - 1
        # every signal row: prototype cells, formulas moved to the row, then the IODB values
        i = 0
        for g in block.groups:
            gv = _cable_values(g)
            g0 = r + i
            for rec in g.recs:
                rr = r + i
                pos = "last" if (i == n - 1) else ("first" if i == 0 else "mid")
                style_row(rr, pos)
                src_tag = "first" if i == 0 else "mid"
                for c in range(1, max_col + 1):
                    val, _st, src_row = snap[src_tag][c]
                    mid_val = snap["mid"][c][0]
                    if isinstance(mid_val, str) and mid_val.startswith("="):
                        val, src_row = mid_val, snap["mid"][c][2]      # row formulas: same in every row
                    if val is None:
                        continue
                    if isinstance(val, str) and val.startswith("="):
                        if "#REF" in val:
                            val = "TBA"
                        else:
                            val = _adjust(val, src_row, rr)
                    ws.cell(rr, c).value = val
                vals = _row_values(key, rec, g)
                for fld, c in fcol.items():
                    if fld in vals and vals[fld] is not None:
                        ws.cell(rr, c).value = vals[fld]
                    elif fld in vals and vals[fld] is None and fld == "remarks":
                        ws.cell(rr, c).value = None
                    if fld == "cd_tb2" and ws.cell(rr, c).value in (None, "TBA"):
                        ws.cell(rr, c).value = vals["cd_tb2"]
                if key == "mov":
                    for fld in ("desc", "tag"):
                        pass
                    ws.cell(rr, fcol["from"]).value = None           # set at block level below
                i += 1
            gend = r + i - 1
            # cable-level cells (VFD/LCP): value in the first row of the cable group, merged over its rows
            for fld in spec["cable_fields"]:
                c = fcol.get(fld)
                if c:
                    ws.cell(g0, c).value = gv[fld]
                    if gend > g0:
                        ws.merge_cells(start_row=g0, start_column=c, end_row=gend, end_column=c)
                    _outline(ws, f"{get_column_letter(c)}{g0}:{get_column_letter(c)}{gend}")
        # block-level cells (merged over the whole block)
        for fld in spec["block_fields"]:
            c = fcol.get(fld)
            if not c:
                continue
            if fld == "from":
                if key == "mov":
                    ws.cell(r0, c).value = bv["from"]
                else:
                    unit, mtb = fcol.get("end_unit"), fcol.get("end_mtb")
                    if unit and mtb and sep_dash:
                        ws.cell(r0, c).value = (f"={get_column_letter(unit)}{r0}&{get_column_letter(sep_dash)}{r0}"
                                                f"&{get_column_letter(mtb)}{r0}")
                    else:
                        ws.cell(r0, c).value = "TBA"
            elif fld == "sigtype":
                ws.cell(r0, c).value = block.groups[0].recs[0].io
            else:
                ws.cell(r0, c).value = bv[fld]
            for rr in range(r0 + 1, r1 + 1):
                ws.cell(rr, c).value = None
            if r1 > r0:
                ws.merge_cells(start_row=r0, start_column=c, end_row=r1, end_column=c)
            _outline(ws, f"{get_column_letter(c)}{r0}:{get_column_letter(c)}{r1}")
        r += n

    last = max(r - 1, first)
    # leftover reference formatting below the data
    for rr in range(r, max(ws.max_row, proto_end) + 1):
        for c in range(1, max_col + 1):
            ws.cell(rr, c).value = None
    ws.print_area = f"A1:{get_column_letter(_print_last_col(ws, spec))}{last}"
    stats["rows"] = r - first
    stats["drop_col"] = col("new_tag") if key in ("mcc_di", "mcc_do") else None
    return ws, stats


def _print_last_col(ws, spec) -> int:
    """Last printed column of the reference (before the helper columns)."""
    cols = header_columns(ws, spec["hdr"])
    return max(cols.get("remarks", [29]) + [cols.get("sigtype", [28])[-1]])


def _fill_title(ws, spec, info: dict):
    """Title block: project/client from the workbook's own schedule header; the rest TBA (never guessed)."""
    labels = {"document title", "client", "project", "doc no.", "rev no.", "date", "prepared by", "checked by", "approved by"}
    for row in (4, 5, 6):
        for c in range(1, 30):
            t = _cell_text(ws.cell(row, c).value)
            if t not in labels:
                continue
            m = next((m for m in ws.merged_cells.ranges if m.min_row <= row <= m.max_row and m.min_col == c), None)
            start = (m.max_col + 1) if m else c + 1
            target = None
            for nc in range(start, 31):
                cell = ws.cell(row, nc)
                if type(cell).__name__ == "MergedCell":
                    continue
                if _cell_text(cell.value) in labels:
                    break
                target = cell
                break
            if target is None:
                continue
            val = {"document title": f"{spec['label']} CABLE SCHEDULE", "client": info.get("client"),
                   "project": info.get("project")}.get(t, "TBA")
            if val is not None:
                target.value = val


# ── copying the finished sheet into the output workbook ──────────────────────
UNIFORM_FROM_ROW = 9
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _shift_formula(f: str, drop: int) -> str:
    def sub(m):
        c = column_index_from_string(m.group(2))
        return m.group(0) if c <= drop else f"{m.group(1)}{get_column_letter(c - 1)}{m.group(3)}{m.group(4)}"
    return re.sub(r"(\$?)([A-Z]{1,3})(\$?)(\d+)", sub, f)


def copy_sheet(src, dst_wb, title: str, index: Optional[int] = None, drop_col: Optional[int] = None):
    """Copy `src` into `dst_wb`. drop_col: a column removed from the copy (cells, merges, widths, formulas, picture and
    print area move left). Rows from UNIFORM_FROM_ROW down are Calibri 12, centred horizontally and vertically; no
    column is hidden."""
    def mc(c):                                    # source column -> copy column
        return c - 1 if drop_col and c > drop_col else c

    dst = dst_wb.create_sheet(title=title, index=index)
    for row in src.iter_rows():
        for c in row:
            if type(c).__name__ == "MergedCell" or (drop_col and c.column == drop_col):
                continue
            d = dst.cell(c.row, mc(c.column))
            v = c.value
            d.value = _shift_formula(v, drop_col) if drop_col and isinstance(v, str) and v.startswith("=") else v
            if c.has_style:
                d.font, d.fill, d.border = copy(c.font), copy(c.fill), copy(c.border)
                d.alignment, d.number_format, d.protection = copy(c.alignment), c.number_format, copy(c.protection)
            if c.row >= UNIFORM_FROM_ROW:
                f = c.font
                d.font = Font(name="Calibri", size=12, bold=f.b, italic=f.i, color=copy(f.color) if f.color else None)
                d.alignment = _CENTER
    for rng in src.merged_cells.ranges:
        c1, c2 = rng.min_col, rng.max_col
        if drop_col:
            if c1 == c2 == drop_col:
                continue
            n1, n2 = (c1 - 1 if c1 > drop_col else c1), (c2 - 1 if c2 >= drop_col else c2)
            if n1 == n2 and rng.min_row == rng.max_row:
                continue
        else:
            n1, n2 = c1, c2
        dst.merge_cells(start_row=rng.min_row, start_column=n1, end_row=rng.max_row, end_column=n2)
    for k, cd in src.column_dimensions.items():
        lo, hi = cd.min or column_index_from_string(k), cd.max or column_index_from_string(k)
        if drop_col:
            if lo == hi == drop_col:
                continue
            lo, hi = (lo - 1 if lo > drop_col else lo), (hi - 1 if hi >= drop_col else hi)
        d = dst.column_dimensions[get_column_letter(lo)]
        d.min, d.max, d.width, d.hidden = lo, hi, cd.width, False          # nothing stays hidden
    for r, rd in src.row_dimensions.items():
        if rd.height is not None:
            dst.row_dimensions[r].height = rd.height
    dst.sheet_view.zoomScale = src.sheet_view.zoomScale
    dst.sheet_view.showGridLines = src.sheet_view.showGridLines
    ps, pd_ = src.page_setup, dst.page_setup
    pd_.orientation, pd_.paperSize, pd_.scale = ps.orientation, ps.paperSize, ps.scale
    pd_.fitToWidth, pd_.fitToHeight = ps.fitToWidth, ps.fitToHeight
    if src.sheet_properties.pageSetUpPr is not None:
        dst.sheet_properties.pageSetUpPr = copy(src.sheet_properties.pageSetUpPr)
    dst.page_margins = copy(src.page_margins)
    dst.print_options = copy(src.print_options)
    if src.print_title_rows:
        dst.print_title_rows = src.print_title_rows
    if src.print_area:
        pa = src.print_area if isinstance(src.print_area, str) else str(src.print_area)
        if drop_col:
            m = re.match(r"^(.*!)?\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)$", pa)
            if m:
                end = column_index_from_string(m.group(4))
                end = end - 1 if end >= drop_col else end
                pa = f"A1:{get_column_letter(end)}{m.group(5)}"
        dst.print_area = pa.split("!")[-1].replace("$", "")
    try:
        dst.oddHeader, dst.oddFooter = copy(src.oddHeader), copy(src.oddFooter)
    except Exception:
        pass
    for img in src._images:
        try:
            data = img._data()
            new = XlImage(io.BytesIO(data))
            new.width, new.height = img.width, img.height
            new.anchor = deepcopy(img.anchor)
            if drop_col:
                a = new.anchor
                for pt in (getattr(a, "_from", None), getattr(a, "to", None)):
                    if pt is not None and pt.col >= drop_col:
                        pt.col -= 1
            dst.add_image(new)
        except Exception:
            continue
    return dst


# ── public entry points ──────────────────────────────────────────────────────
def sheet_titles(template_names: list[str], selected: list[str]) -> dict[str, str]:
    """Output sheet name per selected key. Never replaces a template sheet: a clash gets ' (iEZ)'."""
    taken = {re.sub(r"\s+", " ", n).strip().lower() for n in template_names}
    out = {}
    for key in selected:
        name = SHEETS[key]["label"]
        if re.sub(r"\s+", " ", name).strip().lower() in taken:
            name = f"{name} (iEZ)"
        taken.add(name.lower())
        out[key] = name
    return out


def parse_selection(value) -> list[str]:
    """'MCC DI,VFD' / ['mcc_di'] -> ordered, validated keys (reference order)."""
    if not value:
        return []
    items = value if isinstance(value, (list, tuple)) else re.split(r"[,;|]", str(value))
    wanted = set()
    for it in items:
        t = str(it).strip()
        if not t:
            continue
        k = LABEL_TO_KEY.get(t.upper()) or (t.lower() if t.lower() in SHEETS else None) \
            or LABEL_TO_KEY.get(re.sub(r"[-_]", " ", t).upper())
        if not k:
            raise ExtraSheetError(f"Unknown cable schedule sheet '{t}'. Choose from: " + ", ".join(v["label"] for v in SHEETS.values()) + ".")
        wanted.add(k)
    return [k for k in SHEETS if k in wanted]


def project_info(wb, schedule_sheet: Optional[str]) -> dict:
    """PROJECT / CLIENT labels in the first rows of the workbook's own schedule sheet."""
    info = {}
    if schedule_sheet and schedule_sheet in wb.sheetnames:
        ws = wb[schedule_sheet]
        for row in ws.iter_rows(min_row=1, max_row=8, max_col=8):
            label = None
            for c in row:
                v = c.value
                if isinstance(v, str) and v.strip().lower() in ("project", "client", "location"):
                    label = v.strip().lower()
                elif label and v not in (None, "") and type(c).__name__ != "MergedCell":
                    info.setdefault(label, str(v).strip())
                    label = None
    return info


def add_extra_sheets(out_wb, df, selected: list[str], schedule_sheet: Optional[str], template_names: list[str]) -> dict:
    """
    Append the selected sheets to `out_wb`, right after the schedule sheet (before any CABLE SUMMARY).
    Raises ExtraSheetError when a selected sheet cannot be built. Returns {"sheets": [names], "stats": [...],
    "warnings": [...]}.
    """
    if not selected:
        return {"sheets": [], "stats": [], "warnings": []}
    if not REFERENCE_PATH.exists():
        raise ExtraSheetError("The MCC / VFD / MOV / LCP reference layouts are missing on the server.")
    recs, _cols = normalize(df)
    parts = split_records(recs)
    avail = availability(df)
    titles = sheet_titles(template_names, selected)
    info = project_info(out_wb, schedule_sheet)
    names: list[str] = []
    stats: list[dict] = []
    warnings: list[str] = []
    at = (out_wb.sheetnames.index(schedule_sheet) + 1) if schedule_sheet in out_wb.sheetnames else len(out_wb.sheetnames)
    for key in selected:
        if not avail[key]["available"]:
            raise ExtraSheetError(avail[key]["reason"])
        ref_wb = openpyxl.load_workbook(REFERENCE_PATH)
        ws, st = build_sheet(ref_wb, key, parts[key], info)
        copy_sheet(ws, out_wb, titles[key], index=at, drop_col=st.pop("drop_col", None))
        at += 1
        names.append(titles[key])
        st["sheet"] = titles[key]
        stats.append(st)
        warnings += [f"{SHEETS[key]['label']}: {w}" for w in st["warnings"]]
    return {"sheets": names, "stats": stats, "warnings": warnings}


def preview(df, selected: list[str], max_rows: int = 40) -> dict:
    """What would be generated, from the real data: counts, warnings and the first rows of each sheet."""
    recs, _ = normalize(df)
    parts = split_records(recs)
    avail = availability(df)
    out = []
    for key in selected:
        a = avail[key]
        entry = {"key": key, "label": SHEETS[key]["label"], "available": a["available"], "reason": a["reason"],
                 "records": a["records"], "devices": a["devices"], "cables": a["cables"], "warnings": a["warnings"],
                 "rows": []}
        if a["available"]:
            serial = 0
            for block in plan_blocks(key, parts[key]):
                serial += 1
                for g in block.groups:
                    for rec in g.recs:
                        if len(entry["rows"]) < max_rows:
                            entry["rows"].append({"sl": serial, "tag": show(rec.tag_no), "description": _description(rec),
                                                  "cable": show(g.tag), "cable_size": show(g.ctype),
                                                  "signal": rec.io, "device": device_key(rec)})
        out.append(entry)
    return {"sheets": out}


def redundant_main_cable_rows(df, selected: list[str]) -> set[int]:
    """IODB (Excel) rows that repeat a cable already carried by an earlier row of the same physical cable group.
    The cable summary counts a physical cable once: it drops the cable type/length of these rows."""
    recs, _ = normalize(df)
    parts = split_records(recs)
    redundant: set[int] = set()
    for key in selected:
        for block in plan_blocks(key, parts[key]):
            for g in block.groups:
                counted = False
                for r in g.recs:
                    if is_missing(r.main_cable_type):
                        continue
                    if counted:
                        redundant.add(r.row)
                    counted = True
    return redundant
