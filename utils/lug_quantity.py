"""
lug_quantity.py - Cable Lug Quantity Generator.

    cable schedule workbook (read only)
      -> data rows only (header / repeated-header / section rows are dropped)
      -> cable occurrences (tag, ROLE, cable type) -> PHYSICAL cables (identity = tag + role + cable group)
      -> normalised cable type -> construction (cores / pairs / triads / earth) -> CORE COUNT
      -> termination arrangement -> LUGGED CONDUCTORS at the FROM and TO end (separate from the core count)
      -> lugs per cable = lugged from + lugged to -> total = physical cable quantity x lugs per cable
      -> grouping, gland recommendation by cable OD (separate calculation), reconciliation, exceptions

Boundaries:
  * Excel row != physical cable. A tag repeated on signal rows is one cable. The same tag text on two cables of different
    ROLE (field vs main, digital vs analog group) or different construction is NOT a conflict: they are separate physical
    cables (a different construction under the same tag and role is flagged AMBIGUOUS CABLE TAG for review). CONFLICTING
    CABLE DATA is reserved for conflicting values of the same field of the same cable group.
  * Cable LENGTH is reported, never used for lugs. Core count and lugged-conductor count are separate fields.
  * Ferrule / terminal-block terminations give 0 lugs (switchable rule). Unknown arrangements are REVIEW, never guessed.
  * Gland size comes from the cable OD and a manufacturer table (utils.gland_advisor), never from the cable type text.
The cable-schedule header/merge/formula handling is shared with the gland module (utils.gland_quantity).
"""
from __future__ import annotations

import io
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .drum_schedule import cable_key
from .gland_quantity import (GlandError, _Reader, _SUBHEAD, _clean_text, _label_cells, _row_labels, is_blank, is_tba, parse_gland)

NS = "NOT SPECIFIED"
HEADER_VOCAB = re.compile(
    r"^(SL\.? ?NO\.?|S\.? ?NO\.?|FROM|TO|DESCRIPTION|(NEW )?TAG( NO\.?| NUMBER)?|CABLE( NO\.?| NUMBER| SIZE| TYPE| TAG( NO\.?)?| LENGTH( \(M\))?)|SIZE|TYPE|"
    r"GLAND( SIZE| QTY\.?( \(NO\))?)?|(POSITIVE|NEGATIVE) CORE|SIGNAL TYPE|REMARKS?|.* SIDE GLAND|FERRULE.*|.*TERMINALS?|RACK|SLOT( NO)?|DROP|MAIN TB NAME|"
    r"TB NO|RIO PANEL|PANEL NO|MCC NO|MTB NO|VFD NO|LCP NO|CARD NO|PLC( \(TO\))?|INSTRUMENT SIDE GLAND|CONTROL DESK.*)$", re.I)


class LugError(GlandError):
    """User-facing problem with the uploaded schedule or the settings."""


def is_header_text(v: Any) -> bool:
    return bool(HEADER_VOCAB.match(_clean_text(v)))


# ── construction parsing / normalisation ─────────────────────────────────────
def _size_txt(s: Optional[float]) -> str:
    if s is None:
        return ""
    return f"{s:.1f}" if (s == int(s) and s < 10) else (f"{int(s)}" if s == int(s) else f"{s:g}")


def parse_construction(text: Any) -> dict:
    """
    '14Cx1.0 Sq. mm' -> 14 cores (14 conductors), size 1.0, normalised '14C x 1.0 Sq.mm';  '12P x 1.5' -> 12 pairs = 24 conductors;
    '3C x 70 Sq.mm + 35 Sq.mm E' -> 3 cores + earth 35 mm2. A pair is two conductors. Not recognised -> kind UNKNOWN (never guessed).
    """
    raw = _clean_text(text)
    t = raw.upper().replace("×", "X").replace("²", "2")
    t = re.sub(r"SQ\.?\s*MM|SQMM|MM2|MM\^2", "MM2", t)
    t = re.sub(r"\s+", " ", t)
    out = {"raw": raw, "kind": "UNKNOWN", "pairs": 0, "cores": 0, "conductors": 0, "earth": 0, "size": None, "earth_size": None,
           "runs": None, "note": "", "normalized": raw, "construction": ""}
    m = re.search(r"\((\d+)\s*RUNS?\)", t)
    if m:
        out["runs"] = int(m.group(1))
        out["note"] = f"'{m.group(0)}' stated in the cable type: cable quantity not multiplied - confirm the number of physical cables."
    num = r"(\d+(?:\.\d+)?)"
    m = re.search(rf"(\d+)\s*P\s*X\s*{num}", t) or re.search(r"\b(\d+)\s*P\b(?!\w)", t)
    if m and not re.search(r"\d\s*C\s*X", t):
        n = int(m.group(1))
        size = float(m.group(2)) if m.lastindex and m.lastindex >= 2 else None
        out.update(kind="PAIR", pairs=n, conductors=2 * n, size=size, construction=f"{n}P")
        out["normalized"] = f"{n}P" + (f" x {_size_txt(size)} Sq.mm" if size is not None else "")
        return out
    m = re.search(rf"(\d+)\s*T\s*X\s*{num}", t)
    if m:
        n = int(m.group(1))
        out.update(kind="TRIAD", conductors=3 * n, size=float(m.group(2)), construction=f"{n}T")
        out["normalized"] = f"{n}T x {_size_txt(out['size'])} Sq.mm"
        return out
    for pat, has_size, earth_size, has_earth in (
        (rf"(\d+)\s*C\s*X\s*{num}(?:\s*MM2)?\s*\+\s*{num}\s*(?:MM2)?\s*(?:E|EARTH|PE|G)\b", True, True, True),
        (rf"(\d+)\s*C\s*X\s*{num}(?:\s*MM2)?\s*\+\s*(?:1\s*)?(?:E|EARTH|PE|G)\b", True, False, True),
        (r"(\d+)\s*C\s*\+\s*(?:1\s*)?(?:E|EARTH|PE|G)\b", False, False, True),
        (rf"(\d+)\s*C\s*X\s*{num}", True, False, False),
        (r"(\d+)\s*C\b", False, False, False),
    ):
        m = re.search(pat, t)
        if m:
            cores = int(m.group(1))
            earth = 1 if has_earth else 0
            size = float(m.group(2)) if has_size else None
            esize = float(m.group(3)) if earth_size else None
            out.update(kind="CORE", cores=cores, conductors=cores + earth, earth=earth, size=size, earth_size=esize, construction=f"{cores}C")
            norm = f"{cores}C" + (f" x {_size_txt(size)} Sq.mm" if size is not None else "")
            if earth:
                norm += f" + {_size_txt(esize)} Sq.mm E" if esize is not None else " + E"
            out["normalized"] = norm
            return out
    return out


def normalize_type_key(text: Any) -> str:
    """Formatting differences collapse (14Cx1.0 Sq. mm = 14C x 1.0 Sq.mm); construction differences do not (5C != 14C)."""
    c = parse_construction(text)
    return re.sub(r"\s+", "", c["normalized"].upper()) if c["kind"] != "UNKNOWN" else cable_key(text)


# ── settings / overrides ─────────────────────────────────────────────────────
@dataclass
class Rules:
    count_duplicates_once: bool = True
    ferrule_evidence: bool = False                 # ferrule / terminal-block columns with values = terminal-block termination (0 lugs)
    instrumentation_use_lugs: bool = True          # pair / triad instrumentation cables: one lug per conductor at each lugged end
    control_use_lugs: bool = True                  # core cables up to control_max_mm2
    power_use_lugs: bool = True
    default_lug_type: str = ""                     # carried to the lug report when the schedule gives none (empty = NOT SPECIFIED)
    default_lug_material: str = ""
    lug_type_by_size: dict = field(default_factory=dict)   # conductor size (mm2) -> lug type, e.g. {"1.0": "Pin lug"}
    lugged_ends: str = "both"                      # both | from | to
    earth_lugged: bool = True
    power_min_mm2: float = 4.0
    control_max_mm2: float = 2.5
    allow_override: bool = True
    sheets: Optional[list] = None

    @staticmethod
    def from_dict(d: Optional[dict]) -> "Rules":
        d = d or {}
        r = Rules()
        for k in ("count_duplicates_once", "ferrule_evidence", "instrumentation_use_lugs", "control_use_lugs", "power_use_lugs", "earth_lugged", "allow_override"):
            if k in d and d[k] is not None:
                setattr(r, k, bool(d[k]))
        if d.get("lugged_ends") is not None:
            if d["lugged_ends"] not in ("both", "from", "to"):
                raise LugError("Lugged ends must be 'both', 'from' or 'to'.")
            r.lugged_ends = d["lugged_ends"]
        for k in ("power_min_mm2", "control_max_mm2"):
            if d.get(k) not in (None, ""):
                try:
                    setattr(r, k, float(d[k]))
                except (TypeError, ValueError):
                    raise LugError(f"{k.replace('_', ' ')} must be a number.")
        if r.control_max_mm2 > r.power_min_mm2:
            raise LugError("The control cable maximum size cannot exceed the power cable minimum size.")
        r.default_lug_type = _clean_text(d.get("default_lug_type"))
        r.default_lug_material = _clean_text(d.get("default_lug_material"))
        by = d.get("lug_type_by_size") or {}
        if isinstance(by, dict):
            for k_, v_ in by.items():
                try:
                    r.lug_type_by_size[f"{float(str(k_).replace('mm2', '').replace('mm²', '').strip()):g}"] = _clean_text(v_)
                except ValueError:
                    raise LugError(f"Lug type by size: '{k_}' is not a conductor size (use e.g. 1.5 = Pin lug).")
        r.sheets = d.get("sheets")
        return r


def _yn(v: Any) -> Optional[bool]:
    t = _clean_text(v).upper()
    if t in ("YES", "Y", "TRUE", "REQUIRED", "1"):
        return True
    if t in ("NO", "N", "FALSE", "NOT REQUIRED", "0", "NA", "N/A", "-"):
        return False
    return None


def _count(v: Any) -> tuple[Optional[int], str]:
    t = _clean_text(v)
    if t.upper() in ("", "-", "NA", "N/A", "TBA", "TBD"):
        return None, "blank"
    try:
        q = float(t)
    except ValueError:
        return None, "invalid"
    if q < 0 or q != int(q):
        return None, "invalid"
    return int(q), "ok"


# ── reading the schedule ─────────────────────────────────────────────────────
def _collapse(labels: dict[int, str]) -> dict[int, str]:
    """A header merged over both header rows reads twice ('X X'): keep it once."""
    out = {}
    for c, t in labels.items():
        half = len(t) // 2
        out[c] = t[:half] if len(t) % 2 == 1 and t[:half] == t[half + 1:] and t[half] == " " else t
    return out


def find_header(ws) -> Optional[tuple[int, Optional[int], dict[int, str]]]:
    """(top row, sub row or None, {col: 'TOP SUB'}) of a cable schedule: a row with cable tag/type style labels."""
    for r in range(1, min(ws.max_row, 40) + 1):
        row = _row_labels(ws, r)
        filled = list(dict.fromkeys(t for t in row if t))          # a merged title cell counts once
        if len(filled) < 3:
            continue
        hits = sum(1 for t in filled if re.search(r"TAG|CABLE|TYPE|FROM|LENGTH|DESCRIPTION|LUG|FERRULE|SIGNAL", t))
        typed = any(re.search(r"CABLE (TYPE|SIZE|CONSTRUCTION)", t) for t in filled)
        if not ((hits >= 3 and any(re.search(r"TAG|CABLE", t) for t in filled)) or (typed and hits >= 2)):
            continue
        nxt = _row_labels(ws, r + 1) if r < ws.max_row else []
        nxt = list(dict.fromkeys(t for t in nxt if t))
        subs = [t for t in nxt if t and (_SUBHEAD.search(t) or re.search(r"POSITIVE|NEGATIVE|^(MCC|VFD|LCP) NO|MTB|RACK|SLOT|DROP|TB NO|QTY", t))]
        numeric_first = any(re.fullmatch(r"\d+(\.\d+)?", t) for t in nxt if t)
        if len(subs) >= 2 and not numeric_first:
            return r, r + 1, _collapse(_label_cells(ws, r, r + 1))
        return r, None, _label_cells(ws, r, None)
    return None


def classify(labels: dict[int, str]) -> dict:
    """Semantic column map: every field is found by its header text."""
    cols: dict[str, Any] = {}
    ferrule: list[int] = []
    for c, u in labels.items():
        role = "main" if "MAIN" in u else ("branch" if re.search(r"INSTRUMENT TO JB|BRANCH", u) else "gen")
        if "FERRULE" in u:
            ferrule.append(c)
        elif "LUG" in u:
            if re.search(r"REQUIRED|REQ\b", u):
                cols.setdefault("lug_required", c)
            elif re.search(r"\bTYPE\b", u):
                cols.setdefault("lug_type", c)
            elif re.search(r"SIZE|\bMM2\b", u):
                cols.setdefault("lug_size", c)
            elif re.search(r"MATERIAL", u):
                cols.setdefault("lug_material", c)
            elif re.search(r"QTY|QUANTITY|NO\b", u):
                cols.setdefault("lug_qty_from" if "FROM" in u else ("lug_qty_to" if re.search(r"\bTO\b", u) else "lug_qty"), c)
            else:
                cols.setdefault("lug_type", c)
        elif re.search(r"TERMINATION|TERMINAL TYPE", u) and "NO" not in u.split():
            cols.setdefault("termination", c)
        elif "GLAND" in u:
            continue
        elif re.search(r"^SIGNAL (I/O )?TYPE\b|^SIGNAL TYPE", u):
            cols.setdefault("sigtype", c)
        elif re.search(r"CABLE (TAG|NO|NUMBER)|CABLE TAG", u) and "TYPE" not in u and "LENGTH" not in u:
            cols.setdefault(f"cable_tag_{role}", c)
        elif re.search(r"CABLE TYPE|CABLE SIZE|CABLE CONSTRUCTION", u) or re.fullmatch(r"INSTRUMENT TO JB CABLE", u):
            cols.setdefault(f"type_{role}", c)
        elif re.search(r"CABLE LENGTH|LENGTH\s*\(", u) and "LUG" not in u:
            cols.setdefault(f"length_{role}", c)
        elif re.search(r"\bIS\s*/?\s*NIS\b", u):
            cols.setdefault("is_nis", c)
        elif re.search(r"^FROM\b|SOURCE EQUIPMENT", u):
            cols.setdefault("from", c)
        elif re.search(r"SIGNAL TO|^TO\b|\(TO\)|DESTINATION", u):
            cols.setdefault("to", c)
        elif re.search(r"^(SL\.? ?NO\.?|S\.? ?NO\.?)$", u):
            cols.setdefault("sl", c)
        elif re.search(r"^(TAG (NO|NUMBER)|INSTRUMENT TAG|TAG)\b|MOTOR TAG", u) and "CABLE" not in u:
            cols.setdefault("tag_row", c)
        elif re.search(r"DESCRIPTION", u):
            cols.setdefault("desc", c)
        elif re.search(r"CORE (COUNT|NO)|NO\.? OF CORES", u):
            cols.setdefault("core_count", c)
    cols["_ferrule"] = ferrule
    return cols


def detect_sheets(wb) -> list[dict]:
    out = []
    for ws in wb.worksheets:
        info = {"sheet": ws.title, "hidden": ws.sheet_state != "visible", "used": False, "reason": ""}
        try:
            h = find_header(ws)
        except Exception as exc:
            info["reason"] = f"could not be read ({exc})"
            out.append(info)
            continue
        if not h:
            info["reason"] = "no cable schedule header found"
            out.append(info)
            continue
        cols = classify(h[2])
        if not any(k.startswith("type_") for k in cols):
            info["reason"] = "no cable type column"
            out.append(info)
            continue
        info.update(used=True, header_row=h[0], reason="cable schedule", has_cable_tag=any(k.startswith("cable_tag") for k in cols),
                    has_lug_columns=any(k.startswith("lug") for k in cols), has_ferrule=bool(cols["_ferrule"]))
        out.append(info)
    return out


def default_sheets(infos: list[dict]) -> list[str]:
    vis = [i["sheet"] for i in infos if i["used"] and not i["hidden"]]
    return vis or [i["sheet"] for i in infos if i["used"]]


def _sheet_kind(name: str) -> str:
    u = name.upper()
    for k in ("MCC", "VFD", "MOV", "LCP", "DIRECT"):
        if k in u:
            return k
    return "CABLE"


def _incomplete_tag(tag: str) -> bool:
    return bool(re.search(r"[-_/.\s]$", tag)) or not re.search(r"[A-Za-z0-9]", tag.replace("IC", ""))


@dataclass
class Occurrence:
    sheet: str
    row: int
    group_row: int                  # merge anchor of the cable-type cell (the cable group), else the row itself
    tag_block: int                  # merge anchor row of the cable TAG cell when it is a multi-row block (0 = not merged)
    tag: str
    tag_known: bool
    tag_note: str
    role: str                       # FIELD | MAIN | <sheet kind>
    sig_group: str                  # DIGITAL | ANALOG | MIXED | ''
    ctype: str
    con: dict
    sl: str = ""
    description: str = ""
    instrument_tags: list = field(default_factory=list)
    is_nis: str = ""
    frm: str = ""
    to: str = ""
    length: Optional[str] = None
    explicit: dict = field(default_factory=dict)
    ferrule: bool = False
    terminal_text: str = ""

    @property
    def role_class(self) -> str:
        return self.role + (f" - {self.sig_group}" if self.sig_group else "")


@dataclass
class Cable:
    pid: str                        # physical cable id
    tag: str
    tag_known: bool
    role: str
    cable_type: str                 # as written in the schedule (first occurrence)
    con: dict
    sheets: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    occurrences: int = 0
    description: str = ""
    instrument_tags: list = field(default_factory=list)
    is_nis: str = ""
    frm: str = ""
    to: str = ""
    length: Optional[str] = None
    explicit: dict = field(default_factory=dict)
    ferrule: bool = False
    terminal_text: str = ""
    notes: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    type_key: str = ""
    category_hint: str = ""


def read_occurrences(data: bytes, rules: Rules, on_sheet: Optional[Callable] = None) -> tuple[list[Occurrence], list[dict], list[dict]]:
    """-> (occurrences, exceptions, sheet info). Only real data rows become occurrences; the workbook is only read."""
    rd = _Reader(data)
    infos = detect_sheets(rd.wf)
    wanted = rules.sheets if rules.sheets is not None else default_sheets(infos)
    used = [i for i in infos if i["used"] and i["sheet"] in wanted]
    if not used:
        raise LugError("No cable schedule sheet was found in the uploaded workbook (a header row with cable tag / cable type style columns is required).")
    exceptions: list[dict] = []
    occs: list[Occurrence] = []

    def exc(sev, kind, ref, msg, sheet="", row=None, **extra):
        exceptions.append({"severity": sev, "kind": kind, "ref": ref, "message": msg, "sheet": sheet, "row": row, **extra})

    for n, info in enumerate(used, 1):
        sheet = info["sheet"]
        ws = rd.wv[sheet]
        h = find_header(ws)
        cols = classify(h[2])
        first = (h[1] or h[0]) + 1
        ferr = cols["_ferrule"]
        probe = [c for c in h[2]][:60]
        kind = _sheet_kind(sheet)
        merged = {}                                           # (col,row) -> (min_row, max_row, anchor col)  for every cell of a merged range
        for m in ws.merged_cells.ranges:
            if m.max_row == m.min_row or m.max_col - m.min_col > 2:
                continue                                  # a one-row or very wide merge is a title bar / section label, not a cable block
            for rr in range(m.min_row, m.max_row + 1):
                for cc in range(m.min_col, m.max_col + 1):
                    merged[(cc, rr)] = (m.min_row, m.max_row, m.min_col)
        skipped_headers = 0
        skipped_labels = 0
        for r in range(first, ws.max_row + 1):
            if all(rd.wv[sheet].cell(r, c).value is None and rd.wf[sheet].cell(r, c).value is None for c in probe):
                continue

            def val(key, rr=None):
                c = cols.get(key)
                if c is None:
                    return None
                rr = rr or r
                a = merged.get((c, rr))                       # a cell inside a merged block carries the value of the block's anchor
                return rd.value(sheet, a[0], a[2]) if a else rd.value(sheet, rr, c)

            def txt(key, rr=None):
                v = val(key, rr)
                return "" if v is None or is_blank(v) or is_tba(v) else _clean_text(v)

            # repeated header / sub-header rows inside the data are not cable records
            texts = [_clean_text(rd.value(sheet, r, c)) for c in probe if rd.value(sheet, r, c) not in (None, "")]
            heads = [t for t in texts if is_header_text(t)]
            if (len(heads) >= 3 and len(heads) >= len(texts) * 0.6) or (len(texts) <= 2 and heads and len(heads) == len(texts)):
                skipped_headers += 1
                continue
            if len(texts) <= 2 and not any(parse_construction(t)["kind"] != "UNKNOWN" for t in texts):
                skipped_labels += 1                           # section label / title row ("DIRECT A", "21AJB02"): not a cable record
                continue
            has_ferrule = any(rd.wf[sheet].cell(r, c).value not in (None, "") for c in ferr)
            for role_key in ("branch", "main", "gen"):
                tcol = cols.get(f"type_{role_key}")
                if tcol is None:
                    continue
                ctype = txt(f"type_{role_key}")
                if not ctype or is_header_text(ctype):
                    continue
                anchor = merged.get((tcol, r), (r, r))[:2]
                group_row = anchor[0]
                tag, tag_col = "", None
                for tk_ in ([f"cable_tag_{role_key}"] + (["cable_tag_main", "cable_tag_branch"] if role_key == "gen" else [])):
                    if tk_ in cols and txt(tk_):
                        tag, tag_col = txt(tk_), cols[tk_]
                        break
                # A merged tag cell makes its block one cable - except a MAIN cable: one main cable is shared by many instrument
                # entries (the Cable Schedule merges its tag per entry), so equal tag + construction stay one physical cable.
                tag_block = merged[(tag_col, r)][0] if (role_key != "main" and tag_col is not None and (tag_col, r) in merged) else 0
                tag_note = ""
                known = bool(tag)
                if known and _incomplete_tag(tag):
                    tag_note = f"incomplete cable tag '{tag}'"
                    tag, known = "", False
                sigs = []
                if "sigtype" in cols:
                    for rr in range(anchor[0], anchor[1] + 1):
                        s = txt("sigtype", rr).upper()
                        if s:
                            sigs.append(s)
                sg = ""
                if sigs:
                    sg = "DIGITAL" if all(s in ("DI", "DO") for s in sigs) else ("ANALOG" if all(s in ("AI", "AO") for s in sigs) else "MIXED")
                role = {"branch": "FIELD", "main": "MAIN"}.get(role_key, kind)
                con = parse_construction(ctype)
                ex = {}
                for k in ("lug_required", "lug_type", "lug_size", "lug_material", "lug_qty", "lug_qty_from", "lug_qty_to"):
                    if k in cols and not is_blank(val(k)):
                        ex[k] = val(k)
                length = txt(f"length_{role_key}") or txt("length_gen")
                sl = _clean_text(rd.value(sheet, anchor[0], cols["sl"])) if "sl" in cols else ""
                occs.append(Occurrence(sheet=sheet, row=r, group_row=group_row, tag_block=tag_block, tag=tag, tag_known=known, tag_note=tag_note, role=role, sig_group=sg if role_key == "gen" else "",
                                       ctype=ctype, con=con, sl=sl, description=txt("desc"), instrument_tags=[txt("tag_row")] if txt("tag_row") else [],
                                       is_nis=txt("is_nis"), frm=txt("from"), to=txt("to"), length=length or None, explicit=ex, ferrule=has_ferrule,
                                       terminal_text=txt("termination")))
        if skipped_labels:
            exc("INFO", "Section label rows ignored", sheet, f"{skipped_labels} section label / title row(s) inside the data were ignored (not cable records).", sheet=sheet)
        if skipped_headers:
            exc("INFO", "Header rows ignored", sheet, f"{skipped_headers} repeated header / sub-header row(s) inside the data were ignored (not cable records).", sheet=sheet)
        if on_sheet:
            on_sheet(sheet, n, len(used), occs, exceptions)
    if rd.unresolved:
        exc("REVIEW", "Formula result unavailable", "workbook",
            f"{rd.unresolved} cell(s) are formulas without a stored result (file written by a tool that does not calculate); they were read as empty. "
            "Open and save the file in Excel, then upload again.")
    return occs, exceptions, infos


def _identity_key(o: Occurrence, rules: Rules) -> tuple:
    tkey = normalize_type_key(o.ctype)
    if o.tag_known:
        if not rules.count_duplicates_once:
            return ("T", o.tag.upper(), o.role_class, tkey, o.sheet, o.row)
        if o.tag_block:                                      # a tag cell that is a merged block: that block is one physical cable
            return ("T", o.tag.upper(), o.role_class, tkey, o.sheet, o.tag_block)
        return ("T", o.tag.upper(), o.role_class, tkey)
    return ("G", o.sheet, o.group_row, o.role_class, tkey)


def resolve_cables(occs: list[Occurrence], rules: Rules) -> tuple[list[Cable], list[dict], list[dict]]:
    """
    Physical cable identity. Tagged: (tag, role class, construction). Untagged: the cable group (merged block) of its sheet.
    Returns (cables, exceptions, reconciliation rows).
    """
    exceptions: list[dict] = []

    def exc(sev, kind, ref, msg, sheet="", row=None, **extra):
        exceptions.append({"severity": sev, "kind": kind, "ref": ref, "message": msg, "sheet": sheet, "row": row, **extra})

    cables: "OrderedDict[tuple, Cable]" = OrderedDict()
    by_tagrole: dict[tuple, dict] = {}
    keys_of: list[tuple] = []
    for o in occs:
        key = _identity_key(o, rules)
        keys_of.append(key)
        tkey = normalize_type_key(o.ctype)
        if o.tag_known:
            by_tagrole.setdefault(("T", o.tag.upper(), o.role_class), {}).setdefault(tkey, []).append(o)
        cb = cables.get(key)
        if cb is None:
            cb = Cable(pid="", tag=o.tag, tag_known=o.tag_known, role=o.role_class, cable_type=o.ctype, con=o.con, type_key=tkey, category_hint=o.sheet)
            cb.description, cb.is_nis, cb.frm, cb.to, cb.length = o.description, o.is_nis, o.frm, o.to, o.length
            cb.explicit, cb.ferrule, cb.terminal_text = dict(o.explicit), o.ferrule, o.terminal_text
            if o.sl:
                cb.notes.append(f"SL {o.sl}")
            if o.tag_note:
                cb.notes.append(o.tag_note)
            cables[key] = cb
        cb.occurrences += 1
        cb.rows.append(o.row)
        if o.sheet not in cb.sheets:
            cb.sheets.append(o.sheet)
        for t in o.instrument_tags:
            if t and t not in cb.instrument_tags:
                cb.instrument_tags.append(t)
        cb.frm, cb.to, cb.length, cb.is_nis = cb.frm or o.frm, cb.to or o.to, cb.length or o.length, cb.is_nis or o.is_nis
        cb.ferrule = cb.ferrule or o.ferrule
        for k, v in o.explicit.items():
            if k in cb.explicit and _clean_text(cb.explicit[k]).upper() != _clean_text(v).upper():
                cb.conflicts.append(f"lug data '{k}' differs between rows ({_clean_text(cb.explicit[k])} / {_clean_text(v)})")
            cb.explicit.setdefault(k, v)
    # same tag + same role: different constructions or several separate cable blocks -> separate cables, AMBIGUOUS CABLE TAG (review);
    # the same cable group with two types -> real conflict
    per_tr: dict[tuple, list] = {}
    for cb_key, cb in cables.items():
        if cb.tag_known:
            per_tr.setdefault((cb.tag.upper(), cb.role), []).append(cb)
    for (tag, role), cbs in per_tr.items():
        if len(cbs) < 2:
            continue
        types = {c.type_key for c in cbs}
        first_o = by_tagrole[("T", tag, role)][next(iter(by_tagrole[("T", tag, role)]))][0]
        shown = "; ".join(f"{c.con['normalized'] if c.con['kind'] != 'UNKNOWN' else c.cable_type} ({c.sheets[0]} row {c.rows[0]})" for c in cbs[:4])
        same_group: dict[tuple, set] = {}
        for tk, os_ in by_tagrole[("T", tag, role)].items():
            for o in os_:
                same_group.setdefault((o.sheet, o.group_row), set()).add(tk)
        if any(len(v) > 1 for v in same_group.values()):
            exc("ERROR", "Conflicting cable data", cbs[0].tag, f"Cable {cbs[0].tag} ({role}) has different cable types in the same cable group: {shown}.", sheet=first_o.sheet, row=first_o.row)
        else:
            why = f"{len(types)} different constructions" if len(types) > 1 else f"{len(cbs)} separate cable blocks"
            exc("REVIEW", "Ambiguous cable tag", cbs[0].tag, f"Cable tag {cbs[0].tag} ({role}) is used for {why}: {shown}. Counted as {len(cbs)} physical cables - "
                "confirm the tag is unique to one cable.", sheet=first_o.sheet, row=first_o.row, action="Give each physical cable its own tag, or confirm the cables are different.")
    roles_per_tag: dict[str, set] = {}
    for cb in cables.values():
        if cb.tag_known:
            roles_per_tag.setdefault(cb.tag.upper(), set()).add(cb.role)
    for tag, roles in roles_per_tag.items():
        if len(roles) > 1:
            exc("INFO", "Tag shared by different cable roles", tag, f"Tag text {tag} is used by cables of different roles ({', '.join(sorted(roles))}); they are separate physical cables.")
    # physical ids
    tag_count: dict[str, int] = {}
    for cb in cables.values():
        if cb.tag_known:
            tag_count[cb.tag.upper()] = tag_count.get(cb.tag.upper(), 0) + 1
    derived: dict[str, list] = {}
    for cb in cables.values():
        if cb.tag_known:
            cb.pid = cb.tag if tag_count[cb.tag.upper()] == 1 else f"{cb.tag} [{cb.role}; {cb.con['normalized'] if cb.con['kind'] != 'UNKNOWN' else cb.cable_type}]"
        else:
            sl = next((n[3:] for n in cb.notes if n.startswith("SL ")), "")
            sheet = cb.sheets[0]
            cb.pid = f"{sheet} cable {sl}" if sl else f"{sheet} row {cb.rows[0]}"
            if cb.occurrences > 1 or sl:
                derived.setdefault(sheet, []).append(cb)
            else:
                exc("REVIEW", "Missing cable tag", cb.pid, f"{sheet} row {cb.rows[0]}: cable type '{cb.cable_type}' has no cable tag and no cable block to derive an identity from "
                    "- MISSING CABLE TAG - REVIEW REQUIRED.", sheet=sheet, row=cb.rows[0], original=cb.cable_type, action="Assign a cable tag number in the schedule.")
                cb.notes.append("tag missing")
    for sheet, lst in derived.items():
        exc("INFO", "Cable identity derived from cable block", sheet, f"{len(lst)} cable(s) on {sheet} have no usable cable tag; each merged cable block (SL / row group) is one physical cable "
            "(several signal rows share it).", sheet=sheet)
    recon = []
    for o, key in zip(occs, keys_of):
        cb = cables[key]
        recon.append({"sheet": o.sheet, "row": o.row, "pid": cb.pid, "role": o.role_class, "original_type": o.ctype,
                      "normalized_type": o.con["normalized"] if o.con["kind"] != "UNKNOWN" else "UNRECOGNIZED", "status": "Valid" if o.con["kind"] != "UNKNOWN" else "UNRECOGNIZED"})
    return list(cables.values()), exceptions, recon


def read_cables(data: bytes, rules: Rules) -> tuple[list[Cable], list[dict], list[dict]]:
    """Compatibility wrapper: occurrences -> physical cables. -> (cables, exceptions, sheet info)."""
    occs, exc1, infos = read_occurrences(data, rules)
    cables, exc2, _ = resolve_cables(occs, rules)
    return cables, exc1 + exc2, infos


# ── lug decision and quantity ────────────────────────────────────────────────
@dataclass
class Result:
    cable: Cable
    construction: dict
    category: str = "UNKNOWN"
    lug_required: Optional[bool] = None
    termination: str = ""
    core_count: Optional[int] = None         # total conductors of the cable (incl. a separate earth conductor)
    lugged_from: int = 0                     # lugged conductors at the FROM end (excl. separate earth)
    lugged_to: int = 0
    earth_from: int = 0
    earth_to: int = 0
    lug_type: str = NS
    lug_size: str = NS
    earth_size: str = NS
    material: str = NS
    status: str = "OK"
    source: str = "AUTO"
    basis: str = ""
    reason: str = ""
    remarks: str = ""
    issues: list = field(default_factory=list)
    auto: Optional[dict] = None              # the automatic values, kept when a user override replaces them

    @property
    def lugs_per_cable(self) -> int:
        return self.lugged_from + self.lugged_to + self.earth_from + self.earth_to

    @property
    def total(self) -> int:                  # one record = one physical cable
        return self.lugs_per_cable

    @property
    def lug_from(self) -> int:
        return self.lugged_from

    @property
    def lug_to(self) -> int:
        return self.lugged_to


def _category(con: dict, rules: Rules) -> str:
    if con["kind"] in ("PAIR", "TRIAD"):
        return "INSTRUMENTATION"
    if con["kind"] == "CORE":
        s = con["size"]
        if s is None:
            return "UNKNOWN"
        if s <= rules.control_max_mm2:
            return "CONTROL"
        if s >= rules.power_min_mm2:
            return "POWER"
        return "UNKNOWN"
    return "UNKNOWN"


def _fmt_size(s: Optional[float]) -> str:
    return NS if s is None else f"{_size_txt(s)} mm²"


def decide(cb: Cable, rules: Rules, override: Optional[dict] = None) -> Result:
    con = cb.con
    res = Result(cable=cb, construction=con)
    res.category = _category(con, rules)
    res.lug_size = _fmt_size(con["size"])
    res.earth_size = _fmt_size(con["earth_size"]) if con["earth"] else NS
    if rules.default_lug_material:
        res.material = rules.default_lug_material
    if con["size"] is not None and rules.lug_type_by_size.get(f"{con['size']:g}"):
        res.lug_type = rules.lug_type_by_size[f"{con['size']:g}"]
    elif rules.default_lug_type:
        res.lug_type = rules.default_lug_type
    if con["kind"] == "UNKNOWN":
        res.issues.append(("ERROR", "UNRECOGNIZED CABLE TYPE", f"Cable {cb.pid} has cable type '{cb.cable_type}', which does not match a recognised cable construction "
                           "(nC x size, nP x size, nT x size, nC + E). CORE COUNT = REVIEW REQUIRED."))
    else:
        res.core_count = con["conductors"]
        if con["conductors"] <= 0:
            res.issues.append(("ERROR", "Invalid conductor count", f"'{cb.cable_type}' gives {con['conductors']} conductors."))
    if con["note"]:
        res.issues.append(("REVIEW", "Cable runs stated", con["note"]))
    for c in cb.conflicts:
        res.issues.append(("ERROR", "Conflicting cable data", f"Cable {cb.pid}: {c}."))
    if "tag missing" in cb.notes:
        res.issues.append(("REVIEW", "Missing cable tag", f"Cable on {cb.sheets[0]} row {cb.rows[0]} has no cable tag and no cable block: MISSING CABLE TAG - REVIEW REQUIRED."))
    ends = {"both": (1, 1), "from": (1, 0), "to": (0, 1)}[rules.lugged_ends]
    n_lug = con["cores"] if con["kind"] == "CORE" else (con["conductors"] or 0)
    ex = cb.explicit

    def apply(f: int, t: int, basis: str, reason: str, ef=0, et=0):
        res.lug_required = (f + t + ef + et) > 0
        res.lugged_from, res.lugged_to, res.earth_from, res.earth_to = f, t, ef, et
        res.basis, res.reason = basis, reason

    def by_rule(basis: str, reason: str):
        ef = con["earth"] * ends[0] if con["earth"] and rules.earth_lugged else 0
        et = con["earth"] * ends[1] if con["earth"] and rules.earth_lugged else 0
        apply(n_lug * ends[0], n_lug * ends[1], basis, reason + (f" Earth conductor lugged separately ({con['earth']} x {sum(ends)})." if ef or et else ""), ef, et)
        if con["earth"] and con["earth_size"] is None and (ef or et):
            res.issues.append(("REVIEW", "Earth conductor size not stated", f"Cable {cb.pid}: the earth conductor is lugged separately but its size is not stated."))

    can_derive = con["kind"] != "UNKNOWN" and bool(res.core_count)
    # Priority 1: explicit lug data in the schedule
    if ex and con["kind"] != "UNKNOWN":
        if "lug_type" in ex:
            res.lug_type = _clean_text(ex["lug_type"]) or NS
        if "lug_size" in ex:
            res.lug_size = _clean_text(ex["lug_size"]) or res.lug_size
        if "lug_material" in ex:
            res.material = _clean_text(ex["lug_material"]) or NS
        req = _yn(ex.get("lug_required")) if "lug_required" in ex else None
        qf, sf = _count(ex.get("lug_qty_from")) if "lug_qty_from" in ex else (None, "blank")
        qt, st = _count(ex.get("lug_qty_to")) if "lug_qty_to" in ex else (None, "blank")
        qa, sa = _count(ex.get("lug_qty")) if "lug_qty" in ex else (None, "blank")
        if "invalid" in (sf, st, sa):
            res.issues.append(("ERROR", "Invalid lug quantity", f"Cable {cb.pid}: a lug quantity in the schedule is negative, fractional or not a number."))
        elif req is False and any(q for q in (qf, qt, qa) if q):
            res.issues.append(("ERROR", "Conflicting lug requirement", f"Cable {cb.pid}: the schedule says lugs are not required but also gives a lug quantity."))
        elif req is False:
            apply(0, 0, "SCHEDULE", "Schedule states a cable lug is not required.")
            res.termination = cb.terminal_text or "Per schedule (no lug)"
        elif qf is not None or qt is not None:
            apply(qf or 0, qt or 0, "SCHEDULE", "Lugged conductors per end taken from the schedule (From + To).")
            res.termination = "Cable lug (per schedule)"
        elif qa is not None:
            half = qa // 2
            apply(qa - half, half, "SCHEDULE", f"Total lug quantity {qa} taken from the schedule; the split between the ends is not stated (shown as {qa - half} / {half}).")
            res.termination = "Cable lug (per schedule)"
            res.issues.append(("REVIEW", "Lug split not stated", f"Cable {cb.pid}: only a total lug quantity ({qa}) is given; the From/To split is an even division - confirm."))
        elif req is True:
            if can_derive:
                by_rule("SCHEDULE + RULE", "Schedule says lugs are required; every conductor is lugged at each lugged end (rule table).")
                res.termination = "Cable lug (per schedule)"
            else:
                res.issues.append(("REVIEW", "Lug quantity cannot be derived", f"Cable {cb.pid}: lugs are required but the number of conductors is unknown."))
    # Priority 2: explicit termination information
    if res.lug_required is None and not res.issues and cb.terminal_text:
        t = cb.terminal_text.upper()
        if re.search(r"LUG", t) and not re.search(r"NO LUG|WITHOUT LUG", t):
            if can_derive:
                by_rule("TERMINATION", f"Schedule termination '{cb.terminal_text}' uses lugs.")
                res.termination = cb.terminal_text
        elif re.search(r"FERRULE|TERMINAL|TB\b|BLOCK|DIRECT|SCREW", t):
            apply(0, 0, "TERMINATION", f"Termination '{cb.terminal_text}' - cable lug not applicable.")
            res.termination = cb.terminal_text
    if res.lug_required is None and not res.issues and cb.ferrule and rules.ferrule_evidence:
        apply(0, 0, "TERMINATION", "Ferrule / terminal-block termination - cable lug not applicable.")
        res.termination = "Ferrule / Terminal Block"
    # Priority 3: project rule table
    if res.lug_required is None and not res.issues:
        cat = res.category
        use = {"INSTRUMENTATION": rules.instrumentation_use_lugs, "CONTROL": rules.control_use_lugs, "POWER": rules.power_use_lugs}.get(cat)
        if use is None:
            res.issues.append(("REVIEW", "Lug requirement unknown", f"Cable {cb.pid} ({cb.cable_type}): the termination arrangement is not stated and the rule table cannot classify the cable "
                               "(size missing or between the control and power limits). No lug quantity generated."))
        elif use is False:
            apply(0, 0, "RULE", "Ferrule / terminal-block termination - cable lug not applicable." if cat != "POWER" else "Project rule: power cables are not lugged.")
            res.termination = "Ferrule / Terminal Block" if cat != "POWER" else "Per project rule (no lug)"
        elif can_derive:
            by_rule("RULE", f"Project rule: {cat.lower()} cables use lugs; {n_lug} conductor(s) lugged at each lugged end.")
            res.termination = "Cable lug (rule)"
        else:
            res.issues.append(("REVIEW", "Lug quantity cannot be derived", f"Cable {cb.pid}: conductor count is unknown."))
    if res.lug_required is None and not res.issues:
        res.issues.append(("REVIEW", "Lug requirement unknown", f"Cable {cb.pid}: no lug, termination or rule information."))
    res.status = ("ERROR" if any(s == "ERROR" for s, _, _ in res.issues) else "REVIEW" if any(s == "REVIEW" for s, _, _ in res.issues) else "OK")
    res.source = "REVIEW" if res.status != "OK" else "AUTO"
    if res.status != "OK":
        res.lugged_from = res.lugged_to = res.earth_from = res.earth_to = 0
        res.lug_required = None
    res.auto = {"lug_required": res.lug_required, "lugged_from": res.lugged_from, "lugged_to": res.lugged_to, "lugs_per_cable": res.lugs_per_cable}
    if override and (override.get("lug_required") or override.get("lugged_from") not in (None, "") or override.get("lugged_to") not in (None, "")
                     or override.get("lug_from") not in (None, "") or override.get("lug_to") not in (None, "")):
        _apply_override(res, override, con)
        res.status = ("ERROR" if any(s == "ERROR" for s, _, _ in res.issues) else "REVIEW" if any(s == "REVIEW" for s, _, _ in res.issues) else "OK")
    return res


def _apply_override(res: Result, o: dict, con: dict) -> None:
    req = (o.get("lug_required") or "").upper()
    res.issues = [(s, k, m) for s, k, m in res.issues if s == "ERROR"]            # an override resolves REVIEW cases; genuine ERRORs stay visible
    res.source = "USER OVERRIDE"
    res.remarks = _clean_text(o.get("remarks"))
    for src, attr in (("lug_type", "lug_type"), ("lug_size", "lug_size"), ("lug_material", "material")):
        if o.get(src):
            setattr(res, attr, _clean_text(o[src]))
    if req == "REVIEW":
        res.issues.append(("REVIEW", "Marked for review by the user", "The engineer set this cable to REVIEW."))
        res.source = "REVIEW"
        res.lugged_from = res.lugged_to = res.earth_from = res.earth_to = 0
        res.lug_required, res.basis, res.reason = None, "USER OVERRIDE", "Engineer marked this cable for review."
        return
    if req == "NO":
        res.lugged_from = res.lugged_to = res.earth_from = res.earth_to = 0
        res.lug_required, res.basis, res.reason = False, "USER OVERRIDE", "Engineer states a cable lug is not required."
        res.termination = "No lug (user override)"
        return
    f, t = _count(o.get("lugged_from", o.get("lug_from"))), _count(o.get("lugged_to", o.get("lug_to")))
    if "invalid" in (f[1], t[1]):
        res.issues.append(("ERROR", "Invalid lug quantity", "The override lugged-conductor count must be a whole number, 0 or more."))
        return
    if f[0] is None and t[0] is None:
        n = con["cores"] if con["kind"] == "CORE" else (con["conductors"] or 0)
        if not n:
            res.issues.append(("REVIEW", "Lug quantity cannot be derived", "Enter the lugged conductors at the From / To end: the conductor count is unknown."))
            return
        f, t = (n, "ok"), (n, "ok")
    cores = res.core_count
    if cores is not None and ((f[0] or 0) > cores or (t[0] or 0) > cores):
        res.issues.append(("ERROR", "Invalid lugged conductor count", f"Lugged conductors ({f[0]}/{t[0]}) exceed the core count ({cores}) of {res.cable.cable_type}."))
        return
    res.lugged_from, res.lugged_to = f[0] or 0, t[0] or 0
    res.earth_from = res.earth_to = 0
    res.lug_required = (res.lugged_from + res.lugged_to) > 0
    res.basis, res.reason = "USER OVERRIDE", "Lugged conductors at the From / To end entered by the engineer (core count unchanged)."
    res.termination = "Cable lug (user override)" if res.lug_required else "No lug (user override)"


def analyze_cables(cables: list[Cable], rules: Rules, overrides: Optional[dict] = None) -> list[Result]:
    overrides = overrides or {}
    out = []
    for cb in cables:
        ov = None
        if rules.allow_override:
            ov = overrides.get(f"tag:{cb.pid}") or overrides.get(f"tag:{cb.tag}") or overrides.get(f"type:{cb.type_key}")
        out.append(decide(cb, rules, ov))
    return out


# ── summaries ────────────────────────────────────────────────────────────────
def _cores_text(r: Result) -> str:
    con = r.construction
    if r.core_count is None:
        return "REVIEW REQUIRED"
    if con["kind"] == "PAIR":
        return f"{con['pairs']} pair = {con['conductors']} conductors"
    if con["kind"] == "TRIAD":
        return f"{con['conductors'] // 3} triad = {con['conductors']} conductors"
    return f"{con['cores']} core" + (" + earth" if con["earth"] else "") + f" = {con['conductors']} conductors"


def _row(r: Result) -> dict:
    cb = r.cable
    known = r.lug_required is not None
    return {"cable_tag": cb.pid, "tag": cb.tag, "tag_known": cb.tag_known, "cable_type": cb.cable_type, "normalized_type": r.construction["normalized"] if r.construction["kind"] != "UNKNOWN" else "UNRECOGNIZED",
            "category": r.category, "role": cb.role, "is_nis": cb.is_nis or "Not stated", "cores": _cores_text(r), "conductors": r.core_count, "core_count": r.core_count,
            "cable_qty": 1, "from": cb.frm, "to": cb.to, "length": cb.length,
            "lug_required": {True: "YES", False: "NO", None: "REVIEW"}[r.lug_required], "termination": r.termination or "Not determined",
            "lugged_from": (r.lugged_from if known else None), "lugged_to": (r.lugged_to if known else None), "lug_from": (r.lugged_from + r.earth_from if known else None),
            "lug_to": (r.lugged_to + r.earth_to if known else None), "earth_lugs": r.earth_from + r.earth_to, "lugs_per_cable": r.lugs_per_cable if known else None,
            "total": r.total if known else None, "lug_type": r.lug_type, "lug_size": r.lug_size, "earth_size": r.earth_size, "material": r.material,
            "status": r.status, "source": r.source, "basis": r.basis, "reason": r.reason or "; ".join(m for _, _, m in r.issues),
            "sheets": ", ".join(cb.sheets), "rows": ", ".join(str(x) for x in cb.rows[:6]) + ("…" if len(cb.rows) > 6 else ""), "first_row": cb.rows[0] if cb.rows else None,
            "occurrences": cb.occurrences, "remarks": r.remarks, "auto": r.auto if r.source == "USER OVERRIDE" else None, "type_key": cb.type_key}


def build(results: list[Result], rules: Rules) -> dict:
    rows = [_row(r) for r in results]
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    for r, row in zip(results, rows):
        key = (r.cable.type_key, r.cable.is_nis, row["lug_required"], r.lug_type, r.lug_size, r.material, row["lug_from"], row["lug_to"],
               r.termination if r.lug_required is not True else "", r.status)
        g = groups.setdefault(key, {"cable_type": r.construction["normalized"] if r.construction["kind"] != "UNKNOWN" else r.cable.cable_type, "original_types": [], "is_nis": r.cable.is_nis or "Not stated",
                                    "cable_qty": 0, "cores": row["cores"], "core_count": r.core_count, "category": r.category, "lug_required": row["lug_required"],
                                    "lugged_from": row["lugged_from"], "lugged_to": row["lugged_to"], "lug_from": row["lug_from"], "lug_to": row["lug_to"],
                                    "per_cable": row["lugs_per_cable"], "total": 0, "lug_type": r.lug_type, "lug_size": r.lug_size, "material": r.material,
                                    "termination": row["termination"], "status": r.status, "source": r.source, "reason": row["reason"], "tags": [], "type_key": r.cable.type_key,
                                    "recognized": r.construction["kind"] != "UNKNOWN"})
        g["cable_qty"] += 1
        g["total"] += row["total"] or 0
        g["tags"].append(r.cable.pid)
        if r.cable.cable_type not in g["original_types"]:
            g["original_types"].append(r.cable.cable_type)
        if r.source == "USER OVERRIDE":
            g["source"] = "USER OVERRIDE"
    types = []
    for g in groups.values():
        g["tags"] = g["tags"][:12]
        types.append(g)
    types.sort(key=lambda g: (g["cable_type"], g["lug_required"]))
    proc: "OrderedDict[tuple, dict]" = OrderedDict()
    for r in results:
        if not r.lug_required:
            continue
        for label, f, t, size in (("lugged conductors", r.lugged_from, r.lugged_to, r.lug_size), ("earth conductor", r.earth_from, r.earth_to, r.earth_size)):
            if f + t <= 0:
                continue
            k = (r.lug_type, size, r.material, label)
            p = proc.setdefault(k, {"lug_type": r.lug_type, "conductor_size": size, "material": r.material, "use": label, "spec": NS, "from_qty": 0, "to_qty": 0, "qty": 0, "cables": 0})
            p["from_qty"] += f
            p["to_qty"] += t
            p["qty"] += f + t
            p["cables"] += 1
    procurement = sorted(proc.values(), key=lambda p: (p["lug_type"], p["conductor_size"], p["material"]))
    by_size: "OrderedDict[str, int]" = OrderedDict()
    by_mat: "OrderedDict[str, int]" = OrderedDict()
    for p in procurement:
        by_size[p["conductor_size"]] = by_size.get(p["conductor_size"], 0) + p["qty"]
        by_mat[p["material"]] = by_mat.get(p["material"], 0) + p["qty"]
    exceptions = []
    for r in results:
        for sev, kind, msg in r.issues:
            if kind == "Missing cable tag":
                continue                                     # already reported with sheet / row when the identity was resolved
            exceptions.append({"severity": sev, "kind": kind, "ref": r.cable.pid, "message": msg, "sheet": ", ".join(r.cable.sheets), "row": r.cable.rows[0] if r.cable.rows else None,
                               "original": r.cable.cable_type})
    ferr: dict[str, int] = {}
    for g in types:
        if g["lug_required"] == "NO" and "Ferrule" in (g["termination"] or ""):
            ferr[g["cable_type"]] = ferr.get(g["cable_type"], 0) + g["cable_qty"]
    for t, n in ferr.items():
        exceptions.append({"severity": "INFO", "kind": "Ferrule / terminal termination", "ref": t, "message": f"{n} cable(s) of type {t} use ferrule / terminal-block termination - cable lug not applicable.", "sheet": "", "row": None})
    recognized = {g["type_key"] for g in types if g["recognized"]}
    all_types = {g["type_key"] for g in types}
    kpis = {"total_lugs": sum(r.total for r in results if r.lug_required), "cables": len(results), "cable_types": len(all_types), "recognized_types": len(recognized),
            "unrecognized_types": len(all_types - recognized), "with_lugs": sum(1 for r in results if r.lug_required), "without_lugs": sum(1 for r in results if r.lug_required is False),
            "review": sum(1 for r in results if r.status == "REVIEW" or (r.lug_required is None and r.status != "ERROR")), "errors": sum(1 for r in results if r.status == "ERROR"),
            "overrides": sum(1 for r in results if r.source == "USER OVERRIDE")}
    return {"kpis": kpis, "cable_wise": rows, "types": types, "procurement": procurement,
            "by_size": [{"size": k, "qty": v} for k, v in by_size.items()], "by_material": [{"material": k, "qty": v} for k, v in by_mat.items()], "exceptions": exceptions}


RULE_TEXT = [
    ("Physical cable", "Excel row != physical cable. Identity = cable tag + cable role (field / main / sheet kind, digital / analog group) + construction. A tag repeated on signal rows is one cable; "
                       "untagged merged blocks are one cable each; header and repeated-header rows are ignored."),
    ("Conflicts", "CONFLICTING CABLE DATA only when the same cable group carries different types. The same tag on cables of different role is a separate cable (INFO); the same tag and role with "
                  "different constructions is AMBIGUOUS CABLE TAG (REVIEW) and counted as separate cables."),
    ("Cable length", "Reported for information only. It is never used to calculate lugs."),
    ("Core count vs lugged conductors", "Core count (e.g. 14C = 14) is a property of the cable. Lugged conductors at the From / To end are separate: lugs per cable = lugged From + lugged To; "
                                        "total = physical cables x lugs per cable. 14C with all conductors lugged at both ends = 28 lugs; with 12 lugged at each end = 24, core count stays 14."),
    ("Default lugging", "Each conductor of a lugged cable carries one lug at the From end and one at the To end (2 lugs per conductor): 14C = 14 From + 14 To = 28 lugs. "
                        "Instrumentation, control and power cables are lugged by default; switch a class off, or tick 'ferrule columns mean terminal block', to change that."),
    ("Priority", "1 explicit lug data in the schedule; 2 explicit termination data (ferrule / terminal / lug); 3 the project rule table; 4 REVIEW - no quantity is generated when the arrangement is unknown."),
    ("Pairs", "A pair is two conductors (12P = 24 conductors, never 12 cores)."),
    ("Earth conductor", "A separate earth conductor ('+ E') is counted on its own line with its own size; it is not assumed identical to the other conductors."),
    ("Gland recommendation", "From the cable OD and a manufacturer table (never from the cable type text or core count). Missing OD -> OD REQUIRED. ET only where the reference data supports it - otherwise verify with the manufacturer."),
    ("Lug type / material / part number", "Carried from the schedule or the user; otherwise NOT SPECIFIED. No lug model is invented."),
]


# ── gland recommendation per cable type (separate calculation) ───────────────
def _smallest(options: list[str]) -> str:
    def key(o):
        g = parse_gland(o)
        m = re.search(r"(\d+(?:\.\d+)?)(?:[ -](\d+)/(\d+)|/(\d+))?", g["size"])
        if not m:
            return 0
        v = float(m.group(1))
        if m.group(2):
            v += int(m.group(2)) / int(m.group(3))
        elif m.group(4):
            v = v / int(m.group(4))
        return v
    return sorted(options, key=key)[0] if options else ""


def gland_for_types(types: list[dict], od_data: Optional[dict], cfg: Optional[dict]) -> list[dict]:
    """Metric / NPT / ET preferred gland per recognised cable type from the cable OD. Missing OD is reported, never invented."""
    from . import gland_advisor as adv
    from . import gland_reference as ref
    od_data = od_data or {}
    cfg = cfg or {}
    project = adv.Project.from_dict({"manufacturer": cfg.get("manufacturer"), "series": cfg.get("series"), "ip": cfg.get("ip"), "hazardous": cfg.get("hazardous")})
    rows = ref.builtin()
    out = []
    seen = set()
    for g in types:
        if g["type_key"] in seen or not g["recognized"]:
            continue
        seen.add(g["type_key"])
        qty = sum(t["cable_qty"] for t in types if t["type_key"] == g["type_key"])
        d = dict(od_data.get(g["type_key"]) or {})
        con_guess = "ARMOURED" if re.search(r"ARM|SWA", " ".join(g["original_types"]).upper()) else "UNARMOURED"
        row = {"cable_type": g["cable_type"], "type_key": g["type_key"], "cable_qty": qty, "od": None, "construction": d.get("construction") or con_guess,
               "metric": "OD Required", "npt": "OD Required", "et": "OD Required / Manufacturer Verification", "basis": "", "status": "REVIEW - OD REQUIRED",
               "source": "", "flags": [], "advice": "Enter cable OD to obtain gland recommendation.", "override": False, "auto": None}
        od_raw = d.get("od")
        if od_raw not in (None, ""):
            try:
                od = adv.parse_od(od_raw)
                row["od"] = od
                inp = adv.inputs_from({"od": od, "construction": row["construction"], "cable_type": g["cable_type"], "bedding": d.get("bedding"), "armour_min": d.get("armour_min"),
                                       "armour_max": d.get("armour_max"), "hazardous": cfg.get("hazardous"), "ip": cfg.get("ip")}, project)
                res = adv.advise(inp, rows, project)
                bits = []
                for e in res["results"]:
                    p = e["preferred"]
                    if e["standard"] == "METRIC":
                        row["metric"] = p["thread"] if p else "NOT AVAILABLE - VERIFY"
                    elif e["standard"] == "NPT":
                        row["npt"] = _smallest(p["thread_options"]) if p else "NOT AVAILABLE - VERIFY"
                    elif e["standard"] == "ET":
                        row["et"] = (_smallest(p["thread_options"]) + " - verify (legacy thread)") if p else "NOT AVAILABLE / VERIFY MANUFACTURER"
                    if p and e["standard"] == "METRIC":
                        bits.append(f"{p['manufacturer']} {p['series']} size {p['gland_size']}: cable OD range {p['od_range'][0]:g}-{p['od_range'][1]:g} mm")
                        row["source"] = f"{p['source']['document']} ({p['source']['revision']})"
                        row["flags"] = p["flags"]
                row["basis"] = "; ".join(bits)
                ok = any(e["preferred"] for e in res["results"] if e["standard"] == "METRIC")
                row["status"] = "ADVISORY" if ok else "REVIEW - NO COMPATIBLE GLAND"
                row["advice"] = "Gland recommendation is advisory - confirm against the manufacturer datasheet." if ok else next((e["message"] for e in res["results"] if e["standard"] == "METRIC"), "")
                if row["construction"] == "ARMOURED" and d.get("bedding") in (None, ""):
                    row["flags"] = list(row["flags"]) + ["BEDDING DIAMETER NOT ENTERED"]
                if not any(re.search(r"ARM|SWA", t.upper()) for t in g["original_types"]) and not d.get("construction"):
                    row["flags"] = list(row["flags"]) + ["CONSTRUCTION ASSUMED UNARMOURED"]
            except adv.AdviceError as e:
                row["status"], row["advice"] = "REVIEW - INVALID OD", str(e)
        ov = {k: d.get(k) for k in ("metric_gland", "npt_gland", "et_gland") if d.get(k)}
        if ov:                                                      # manual gland overrides are shown next to the automatic value
            row["auto"] = {"metric": row["metric"], "npt": row["npt"], "et": row["et"]}
            for k, name in (("metric_gland", "metric"), ("npt_gland", "npt"), ("et_gland", "et")):
                if d.get(k):
                    row[name] = str(d[k])
            row["override"], row["status"] = True, "USER OVERRIDE"
        out.append(row)
    return out


# ── workbook ─────────────────────────────────────────────────────────────────
def to_workbook(res: dict, rules: Rules, source_name: str = "uploaded cable schedule") -> bytes:
    head = PatternFill("solid", start_color="163A5F", end_color="163A5F")
    thin = Side(style="thin", color="B7C3D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    note = f"Source: {source_name} (read only - original values not changed). Lug quantities follow terminations, never cable length; core count and lugged conductors are separate."

    def sheet(title, headers, rows, widths=None):
        ws = wb.create_sheet(title)
        n = len(headers)
        ws.cell(1, 1, title).font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
        for c in range(1, n + 1):
            ws.cell(1, c).fill = head
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n)
        ws.cell(1, 1).alignment = Alignment(horizontal="left", vertical="center")
        ws.cell(2, 1, note).font = Font(name="Calibri", size=10, italic=True)
        for c, h in enumerate(headers, 1):
            cell = ws.cell(3, c, h)
            cell.font, cell.fill, cell.alignment, cell.border = Font(name="Calibri", size=11, bold=True, color="FFFFFF"), head, center, border
        ws.row_dimensions[3].height = 34
        for i, row in enumerate(rows, 4):
            for c, v in enumerate(row, 1):
                cell = ws.cell(i, c, v)
                cell.font, cell.alignment, cell.border = Font(name="Calibri", size=11), center, border
        for c in range(1, n + 1):
            w = (widths or {}).get(c) or min(max(12, max([len(str(headers[c - 1]))] + [len(str(r[c - 1])) for r in rows[:200] if c - 1 < len(r) and r[c - 1] is not None]) + 2), 55)
            ws.column_dimensions[get_column_letter(c)].width = w
        ws.freeze_panes = "A4"

    k = res["kpis"]
    sheet("LUG SUMMARY", ["ITEM", "VALUE"], [["TOTAL LUGS REQUIRED", k["total_lugs"]], ["Physical cables identified", k["cables"]], ["Cable types identified", k["cable_types"]],
                                             ["Recognized cable types", k.get("recognized_types")], ["Unrecognized cable types", k.get("unrecognized_types")],
                                             ["Cables requiring lugs", k["with_lugs"]], ["Cables not requiring lugs", k["without_lugs"]],
                                             ["Cables requiring review", k["review"]], ["Cables with errors", k["errors"]], ["User overrides", k["overrides"]]] +
          [["Lugs of size " + s["size"], s["qty"]] for s in res["by_size"]] + [["Lugs of material " + m["material"], m["qty"]] for m in res["by_material"]], {1: 40})
    gl = {g["type_key"]: g for g in res.get("gland", [])}
    sheet("CABLE TYPE SUMMARY", ["CABLE TYPE (NORMALIZED)", "ORIGINAL TYPE(S)", "IS/NIS", "PHYSICAL CABLE QTY", "CORE COUNT", "LUG REQUIRED", "LUGGED FROM", "LUGGED TO", "LUGS / CABLE",
                                 "TOTAL LUGS", "CABLE OD (MM)", "METRIC GLAND", "NPT GLAND", "ET GLAND", "LUG TYPE", "CONDUCTOR SIZE", "MATERIAL", "TERMINATION", "STATUS", "SOURCE", "REASON"],
          [[t["cable_type"], "; ".join(t["original_types"]), t["is_nis"], t["cable_qty"], t["core_count"] if t["core_count"] is not None else "REVIEW REQUIRED", t["lug_required"],
            t["lugged_from"], t["lugged_to"], t["per_cable"], t["total"], (gl.get(t["type_key"]) or {}).get("od") or "OD Required", (gl.get(t["type_key"]) or {}).get("metric", ""),
            (gl.get(t["type_key"]) or {}).get("npt", ""), (gl.get(t["type_key"]) or {}).get("et", ""), t["lug_type"], t["lug_size"], t["material"], t["termination"], t["status"], t["source"], t["reason"]]
           for t in res["types"]], {21: 60, 2: 28})
    sheet("CABLE-WISE DETAIL", ["CABLE TAG", "CABLE TYPE", "NORMALIZED TYPE", "ROLE", "CATEGORY", "IS/NIS", "CABLE QTY", "CORES / CONDUCTORS", "CORE COUNT", "FROM", "TO", "CABLE LENGTH (info only)",
                                "LUG REQUIRED", "TERMINATION", "LUGGED FROM", "LUGGED TO", "LUGS / CABLE", "TOTAL LUGS", "LUG TYPE", "LUG SIZE", "MATERIAL", "STATUS", "SOURCE", "CALCULATION BASIS", "SHEET",
                                "ROW(S)", "SCHEDULE ROWS WITH THIS CABLE", "REMARKS"],
          [[c["cable_tag"], c["cable_type"], c["normalized_type"], c["role"], c["category"], c["is_nis"], c["cable_qty"], c["cores"], c["core_count"], c["from"], c["to"], c["length"], c["lug_required"],
            c["termination"], c["lugged_from"], c["lugged_to"], c["lugs_per_cable"], c["total"], c["lug_type"], c["lug_size"], c["material"], c["status"], c["source"], f"{c['basis']}: {c['reason']}",
            c["sheets"], c["rows"], c["occurrences"], c["remarks"]] for c in res["cable_wise"]], {24: 70, 8: 30})
    sheet("GLAND RECOMMENDATION", ["CABLE TYPE", "CABLE QTY", "CONSTRUCTION", "CABLE OD (MM)", "METRIC PREFERRED GLAND", "NPT PREFERRED GLAND", "ET PREFERRED GLAND", "BASIS (MANUFACTURER / SERIES / OD RANGE)",
                                   "STATUS", "FLAGS", "SOURCE", "ADVICE"],
          [[g["cable_type"], g["cable_qty"], g["construction"], g["od"] or "OD Required", g["metric"], g["npt"], g["et"], g["basis"], g["status"], "; ".join(g["flags"]), g["source"], g["advice"]]
           for g in res.get("gland", [])] or [["No recognised cable types", "", "", "", "", "", "", "", "", "", "", ""]], {8: 60, 11: 60, 12: 60})
    sheet("EXTRACTION LOG", ["SOURCE SHEET", "SOURCE ROW", "PHYSICAL CABLE ID", "CABLE ROLE", "ORIGINAL CABLE TYPE", "NORMALIZED TYPE", "STATUS"],
          [[x["sheet"], x["row"], x["pid"], x["role"], x["original_type"], x["normalized_type"], x["status"]] for x in res.get("reconciliation", [])] or [["", "", "", "", "", "", ""]], {3: 40})
    sheet("LUG PROCUREMENT", ["LUG TYPE", "CONDUCTOR SIZE", "MATERIAL", "LUG SPECIFICATION / PART NO.", "USE", "FROM-END QTY", "TO-END QTY", "TOTAL QTY", "CABLES"],
          [[p["lug_type"], p["conductor_size"], p["material"], p["spec"], p["use"], p["from_qty"], p["to_qty"], p["qty"], p["cables"]] for p in res["procurement"]] +
          [["TOTAL", "", "", "", "", sum(p["from_qty"] for p in res["procurement"]), sum(p["to_qty"] for p in res["procurement"]), sum(p["qty"] for p in res["procurement"]), ""]] if res["procurement"]
          else [["No lugs required by the analysed cables", "", "", "", "", "", "", 0, ""]])
    sheet("REVIEW - EXCEPTIONS", ["SEVERITY", "KIND", "CABLE / REFERENCE", "SHEET", "ROW", "ORIGINAL VALUE", "MESSAGE", "RECOMMENDED ACTION"],
          [[e["severity"], e["kind"], e["ref"], e.get("sheet", ""), e.get("row"), e.get("original", ""), e["message"], e.get("action", "")] for e in res["exceptions"]] or [["OK", "", "", "", "", "", "No exceptions", ""]],
          {7: 100, 8: 50})
    rule_rows = [["Rule", a, b] for a, b in RULE_TEXT] + [
        ["Setting", "Count duplicate cable tags once", "YES" if rules.count_duplicates_once else "NO"],
        ["Setting", "Ferrule / terminal-block columns mean terminal-block termination (0 lugs)", "YES" if rules.ferrule_evidence else "NO"],
        ["Setting", "Default lug type / material (when the schedule gives none)", f"{rules.default_lug_type or NS} / {rules.default_lug_material or NS}"],
        ["Setting", "Lug type by conductor size", "; ".join(f"{k_} mm² = {v_}" for k_, v_ in rules.lug_type_by_size.items()) or NS],
        ["Setting", "Instrumentation (pair/triad) cables use cable lugs", "YES" if rules.instrumentation_use_lugs else "NO"],
        ["Setting", f"Control cables (core size <= {rules.control_max_mm2:g} mm²) use cable lugs", "YES" if rules.control_use_lugs else "NO"],
        ["Setting", f"Power cables (core size >= {rules.power_min_mm2:g} mm²) use cable lugs", "YES" if rules.power_use_lugs else "NO"],
        ["Setting", "Lugged ends by default", rules.lugged_ends.upper()],
        ["Setting", "Earth conductor of 'nC + E' is lugged (own line)", "YES" if rules.earth_lugged else "NO"],
        ["Setting", "Manual override allowed", "YES" if rules.allow_override else "NO"]]
    sheet("RULES - ASSUMPTIONS", ["TYPE", "RULE / SETTING", "VALUE / DESCRIPTION"], rule_rows, {2: 55, 3: 110})
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── pipeline ─────────────────────────────────────────────────────────────────
def _assemble(occs, exc_read, infos, rules, overrides, od_data, gland_cfg):
    cables, exc_res, recon = resolve_cables(occs, rules)
    results = analyze_cables(cables, rules, overrides)
    out = build(results, rules)
    out["exceptions"] = exc_read + exc_res + out["exceptions"]
    order = {"ERROR": 0, "REVIEW": 1, "WARNING": 1, "INFO": 2}
    out["exceptions"].sort(key=lambda e: order.get(e["severity"], 3))
    out["gland"] = gland_for_types(out["types"], od_data, gland_cfg)
    out["reconciliation"] = recon[:6000]
    out["sheets"] = infos
    out["used_sheets"] = sorted({s for c in cables for s in c.sheets})
    out["kpis"]["error_items"] = sum(1 for e in out["exceptions"] if e["severity"] == "ERROR")
    out["kpis"]["review_items"] = sum(1 for e in out["exceptions"] if e["severity"] == "REVIEW")
    out["extraction"] = out["cable_wise"]
    return out, results


def snapshot(occs, exc_read, rules, overrides, max_rows: int = 250) -> dict:
    """Cheap partial result for the live preview (after each sheet)."""
    cables, exc_res, _ = resolve_cables(occs, rules)
    results = analyze_cables(cables, rules, overrides)
    rows = [_row(r) for r in results]
    ex = exc_read + exc_res + [{"severity": s, "kind": k, "ref": r.cable.pid, "message": m, "sheet": ", ".join(r.cable.sheets), "row": r.cable.rows[0]} for r in results for s, k, m in r.issues]
    order = {"ERROR": 0, "REVIEW": 1}
    ex = [e for e in ex if e["severity"] in order]
    ex.sort(key=lambda e: order[e["severity"]])
    types = {r.cable.type_key for r in results}
    rec = {r.cable.type_key for r in results if r.construction["kind"] != "UNKNOWN"}
    return {"kpis": {"cables": len(results), "cable_types": len(types), "recognized_types": len(rec), "unrecognized_types": len(types - rec),
                     "total_lugs": sum(r.total for r in results if r.lug_required), "errors": sum(1 for e in ex if e["severity"] == "ERROR"), "review": sum(1 for e in ex if e["severity"] == "REVIEW")},
            "rows": rows[-max_rows:], "errors": ex[:60]}


def analyze(data: bytes, rules_d: Optional[dict] = None, overrides: Optional[dict] = None, od_data: Optional[dict] = None, gland_cfg: Optional[dict] = None,
            progress: Optional[Callable] = None) -> tuple[dict, Rules]:
    rules = Rules.from_dict(rules_d)

    def on_sheet(sheet, n, total, occs, excs):
        if progress:
            progress({"stage": f"Read {sheet} ({n}/{total})", "sheet": sheet, "sheets_done": n, "sheets_total": total, **snapshot(occs, excs, rules, overrides)})

    occs, exc_read, infos = read_occurrences(data, rules, on_sheet)
    out, _ = _assemble(occs, exc_read, infos, rules, overrides, od_data, gland_cfg)
    out["rules"] = {"count_duplicates_once": rules.count_duplicates_once, "ferrule_evidence": rules.ferrule_evidence, "instrumentation_use_lugs": rules.instrumentation_use_lugs,
                    "control_use_lugs": rules.control_use_lugs, "power_use_lugs": rules.power_use_lugs, "lugged_ends": rules.lugged_ends, "earth_lugged": rules.earth_lugged,
                    "power_min_mm2": rules.power_min_mm2, "control_max_mm2": rules.control_max_mm2, "allow_override": rules.allow_override}
    out["rule_text"] = [{"rule": a, "text": b} for a, b in RULE_TEXT]
    return out, rules
