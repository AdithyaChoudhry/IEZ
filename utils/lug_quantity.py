"""
lug_quantity.py - Cable Lug Quantity Generator.

    cable schedule workbook (read only) -> physical cables (unique cable tag) -> construction (pairs / cores / earth)
      -> termination arrangement -> lug requirement -> lugs at the FROM and TO end -> totals, grouping, exceptions

Boundaries (from the specification):
  * Physical cable quantity = unique cable tag. A tag repeated on several signal rows is ONE cable.
  * Cable LENGTH is reported but never used in a lug calculation: lugs follow terminations, not metres.
  * A lug is counted only where the termination uses one. Ferrule / terminal-block terminations (the instrumentation
    default) give 0 lugs. If the arrangement cannot be established the cable is REVIEW and no quantity is invented.
  * Priority: 1 explicit lug data in the schedule, 2 explicit termination data, 3 the project rule table, 4 REVIEW.
  * Lug type / material / part number are never fabricated: "NOT SPECIFIED" unless the schedule or the user says so.
The cable-schedule reading itself reuses the gland module's header/merge/formula handling (utils.gland_quantity).
"""
from __future__ import annotations

import io
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .drum_schedule import cable_key
from .gland_quantity import (GlandError, _Reader, _SUBHEAD, _clean_text, _label_cells, _row_labels, anchor_of, is_blank, is_tba)

NS = "NOT SPECIFIED"


class LugError(GlandError):
    """User-facing problem with the uploaded schedule or the settings."""


# ── construction parsing ─────────────────────────────────────────────────────
def parse_construction(text: Any) -> dict:
    """
    '12P x 1.5 Sq.mm' -> 12 pairs, 24 conductors; '4C x 16' -> 4 cores; '3C x 70 Sq.mm + 35 Sq.mm E' -> 3 cores + earth 35 mm2.
    A pair is two conductors, never one. Anything not recognised: kind UNKNOWN (core count = REVIEW REQUIRED).
    """
    raw = _clean_text(text)
    t = raw.upper().replace("×", "X").replace("²", "2")
    t = re.sub(r"SQ\.?\s*MM|SQMM|MM2|MM\^2", "MM2", t)
    t = re.sub(r"\s+", " ", t)
    out = {"raw": raw, "kind": "UNKNOWN", "pairs": 0, "cores": 0, "conductors": 0, "earth": 0, "size": None, "earth_size": None,
           "runs": None, "note": ""}
    m = re.search(r"\((\d+)\s*RUNS?\)", t)
    if m:
        out["runs"] = int(m.group(1))
        out["note"] = f"'{m.group(0)}' stated in the cable type: cable quantity not multiplied - confirm the number of physical cables."
    num = r"(\d+(?:\.\d+)?)"
    m = re.search(rf"(\d+)\s*P\s*X\s*{num}", t) or re.search(r"\b(\d+)\s*P\b(?!\w)", t)
    if m and not re.search(r"\d\s*C\s*X", t):
        n = int(m.group(1))
        out.update(kind="PAIR", pairs=n, conductors=2 * n, size=float(m.group(2)) if m.lastindex and m.lastindex >= 2 else None)
        return out
    m = re.search(rf"(\d+)\s*T\s*X\s*{num}", t)
    if m:
        n = int(m.group(1))
        out.update(kind="TRIAD", pairs=0, cores=0, conductors=3 * n, size=float(m.group(2)))
        return out
    for pat, has_size, earth_size, has_earth in (
        (rf"(\d+)\s*C\s*X\s*{num}(?:\s*MM2)?\s*\+\s*{num}\s*(?:MM2)?\s*(?:E|EARTH|PE|G)\b", True, True, True),
        (rf"(\d+)\s*C\s*X\s*{num}(?:\s*MM2)?\s*\+\s*(?:E|EARTH|PE|G)\b", True, False, True),
        (r"(\d+)\s*C\s*\+\s*(?:E|EARTH|PE|G)\b", False, False, True),
        (rf"(\d+)\s*C\s*X\s*{num}", True, False, False),
        (r"(\d+)\s*C\b", False, False, False),
    ):
        m = re.search(pat, t)
        if m:
            cores = int(m.group(1))
            earth = 1 if has_earth else 0
            out.update(kind="CORE", cores=cores, conductors=cores + earth, earth=earth,
                       size=float(m.group(2)) if has_size else None, earth_size=float(m.group(3)) if earth_size else None)
            return out
    return out


# ── settings / overrides ─────────────────────────────────────────────────────
@dataclass
class Rules:
    count_duplicates_once: bool = True
    instrumentation_use_lugs: bool = False          # pair / triad instrumentation cables on terminal blocks
    control_use_lugs: bool = False                  # small-core control cables (<= control_max_mm2)
    power_use_lugs: bool = True
    lugged_ends: str = "both"                       # both | from | to
    earth_lugged: bool = True                       # the earth conductor of "nC + E" is lugged (counted as its own line)
    power_min_mm2: float = 4.0
    control_max_mm2: float = 2.5
    allow_override: bool = True
    sheets: Optional[list] = None

    @staticmethod
    def from_dict(d: Optional[dict]) -> "Rules":
        d = d or {}
        r = Rules()
        for k in ("count_duplicates_once", "instrumentation_use_lugs", "control_use_lugs", "power_use_lugs", "earth_lugged", "allow_override"):
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
    cols: dict[str, int] = {}
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
        elif re.search(r"^(TAG (NO|NUMBER)|INSTRUMENT TAG|TAG)\b|MOTOR TAG", u) and "CABLE" not in u:
            cols.setdefault("tag_row", c)
        elif re.search(r"DESCRIPTION", u):
            cols.setdefault("desc", c)
        elif re.search(r"CORE (COUNT|NO)|NO\.? OF CORES", u):
            cols.setdefault("core_count", c)
    cols["_ferrule"] = ferrule          # type: ignore[assignment]
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


@dataclass
class Cable:
    tag: str
    tag_known: bool
    cable_type: str
    category_hint: str
    sheets: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    description: str = ""
    instrument_tags: list = field(default_factory=list)
    is_nis: str = ""
    frm: str = ""
    to: str = ""
    length: Optional[str] = None
    explicit: dict = field(default_factory=dict)         # lug columns of the schedule
    ferrule: bool = False                                # ferrule columns carry values for this cable
    terminal_text: str = ""
    conflicts: list = field(default_factory=list)
    occurrences: int = 1


def read_cables(data: bytes, rules: Rules) -> tuple[list[Cable], list[dict], list[dict]]:
    """-> (physical cables, exceptions, sheet info). The workbook is only read."""
    rd = _Reader(data)
    infos = detect_sheets(rd.wf)
    wanted = rules.sheets if rules.sheets is not None else default_sheets(infos)
    used = [i for i in infos if i["used"] and i["sheet"] in wanted]
    if not used:
        raise LugError("No cable schedule sheet was found in the uploaded workbook (a header row with cable tag / cable type style columns is required).")
    exceptions: list[dict] = []
    cables: "OrderedDict[tuple, Cable]" = OrderedDict()

    def exc(sev, kind, ref, msg):
        exceptions.append({"severity": sev, "kind": kind, "ref": ref, "message": msg})

    for info in used:
        sheet = info["sheet"]
        ws = rd.wv[sheet]
        h = find_header(ws)
        cols = classify(h[2])
        first = (h[1] or h[0]) + 1
        ferr = cols["_ferrule"]
        probe = [c for c in h[2]][:60]
        for r in range(first, ws.max_row + 1):
            if all(rd.wv[sheet].cell(r, c).value is None and rd.wf[sheet].cell(r, c).value is None for c in probe):
                continue

            def val(key):
                c = cols.get(key)
                return None if c is None else rd.value(sheet, r, c)

            def txt(key):
                v = val(key)
                return "" if v is None or is_blank(v) or is_tba(v) else _clean_text(v)

            has_ferrule = any(rd.wf[sheet].cell(r, c).value not in (None, "") for c in ferr)
            for role in ("branch", "main", "gen"):
                ctype = txt(f"type_{role}")
                if not ctype:
                    continue
                tag = txt(f"cable_tag_{role}") or (txt("cable_tag_gen") if role != "gen" and False else "")
                if not tag and role == "gen":
                    tag = txt("cable_tag_main") or txt("cable_tag_branch")
                known = bool(tag)
                if not known:
                    tag = f"(no cable tag) {sheet}!row {r}"
                    exc("REVIEW", "Missing cable tag", f"{sheet} row {r}", f"Cable type '{ctype}' has no cable tag; it is counted as one physical cable for this row.")
                key = (tag.upper(),) if (known and rules.count_duplicates_once) else (tag.upper(), sheet, r)
                length = txt(f"length_{role}") or txt("length_gen")
                ex = {}
                for k in ("lug_required", "lug_type", "lug_size", "lug_material", "lug_qty", "lug_qty_from", "lug_qty_to"):
                    if k in cols and not is_blank(val(k)):
                        ex[k] = val(k)
                cb = cables.get(key)
                if cb is None:
                    cb = Cable(tag=tag, tag_known=known, cable_type=ctype, category_hint=sheet, sheets=[sheet], rows=[r],
                               description=txt("desc"), instrument_tags=[txt("tag_row")] if txt("tag_row") else [], is_nis=txt("is_nis"),
                               frm=txt("from"), to=txt("to"), length=length or None, explicit=ex, ferrule=has_ferrule, terminal_text=txt("termination"))
                    cables[key] = cb
                else:
                    cb.occurrences += 1
                    cb.rows.append(r)
                    if sheet not in cb.sheets:
                        cb.sheets.append(sheet)
                    if cb.cable_type and cable_key(ctype) != cable_key(cb.cable_type):
                        cb.conflicts.append(f"cable type '{ctype}' on {sheet} row {r} differs from '{cb.cable_type}'")
                    if txt("tag_row") and txt("tag_row") not in cb.instrument_tags:
                        cb.instrument_tags.append(txt("tag_row"))
                    for k, v in ex.items():
                        if k in cb.explicit and _clean_text(cb.explicit[k]).upper() != _clean_text(v).upper():
                            cb.conflicts.append(f"lug data '{k}' differs between rows ({_clean_text(cb.explicit[k])} / {_clean_text(v)})")
                        cb.explicit.setdefault(k, v)
                    cb.ferrule = cb.ferrule or has_ferrule
                    cb.is_nis = cb.is_nis or txt("is_nis")
                    cb.frm = cb.frm or txt("from")
                    cb.to = cb.to or txt("to")
                    cb.length = cb.length or (length or None)
    if rd.unresolved:
        exc("REVIEW", "Formula result unavailable", "workbook",
            f"{rd.unresolved} cell(s) are formulas without a stored result (file written by a tool that does not calculate); they were read as empty. "
            "Open and save the file in Excel, then upload again.")
    return list(cables.values()), exceptions, infos


# ── lug decision and quantity ────────────────────────────────────────────────
@dataclass
class Result:
    cable: Cable
    construction: dict
    category: str = "UNKNOWN"
    lug_required: Optional[bool] = None
    termination: str = ""
    conductors: Optional[int] = None
    lugged: int = 0                 # lugged conductors (excl. separate earth)
    earth_lugs_per_end: int = 0
    lug_from: int = 0
    lug_to: int = 0
    earth_from: int = 0
    earth_to: int = 0
    lug_type: str = NS
    lug_size: str = NS
    earth_size: str = NS
    material: str = NS
    status: str = "OK"              # OK | REVIEW | ERROR
    source: str = "AUTO"            # AUTO | USER OVERRIDE | REVIEW
    basis: str = ""
    reason: str = ""
    remarks: str = ""
    issues: list = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.lug_from + self.lug_to + self.earth_from + self.earth_to


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
    return NS if s is None else (f"{s:g} mm²")


def decide(cb: Cable, rules: Rules, override: Optional[dict] = None) -> Result:
    con = parse_construction(cb.cable_type)
    res = Result(cable=cb, construction=con)
    res.category = _category(con, rules)
    res.lug_size = _fmt_size(con["size"])
    res.earth_size = _fmt_size(con["earth_size"] if con["earth_size"] else None) if con["earth"] else NS
    if con["kind"] == "UNKNOWN":
        res.issues.append(("REVIEW", "Core count cannot be identified", f"Cable type '{cb.cable_type}' is not a recognised pair/core construction. CORE COUNT = REVIEW REQUIRED."))
    else:
        res.conductors = con["conductors"]
        if con["conductors"] <= 0:
            res.issues.append(("ERROR", "Invalid conductor count", f"'{cb.cable_type}' gives {con['conductors']} conductors."))
    if con["note"]:
        res.issues.append(("REVIEW", "Cable runs stated", con["note"]))
    for c in cb.conflicts:
        res.issues.append(("ERROR", "Conflicting cable data", f"Cable {cb.tag}: {c}."))
    ends = {"both": (1, 1), "from": (1, 0), "to": (0, 1)}[rules.lugged_ends]
    n_lug = con["cores"] if con["kind"] == "CORE" else (con["conductors"] or 0)
    ex = cb.explicit

    def apply_lugs(per_end_from: int, per_end_to: int, basis: str, reason: str, earth_from=0, earth_to=0):
        res.lug_required = (per_end_from + per_end_to + earth_from + earth_to) > 0
        res.lug_from, res.lug_to, res.earth_from, res.earth_to = per_end_from, per_end_to, earth_from, earth_to
        res.basis, res.reason = basis, reason

    # ── Priority 1: explicit lug data in the schedule ──
    if ex:
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
            res.issues.append(("ERROR", "Invalid lug quantity", f"Cable {cb.tag}: a lug quantity in the schedule is negative, fractional or not a number."))
        elif req is False and any(q for q in (qf, qt, qa) if q):
            res.issues.append(("ERROR", "Conflicting lug requirement", f"Cable {cb.tag}: the schedule says lugs are not required but also gives a lug quantity."))
        elif req is False:
            apply_lugs(0, 0, "SCHEDULE", "Schedule states a cable lug is not required.")
            res.termination = cb.terminal_text or "Per schedule (no lug)"
        elif qf is not None or qt is not None:
            apply_lugs(qf or 0, qt or 0, "SCHEDULE", "Lug quantities taken from the schedule (From + To).")
            res.termination = "Cable lug (per schedule)"
        elif qa is not None:
            half = qa // 2
            apply_lugs(qa - half, half, "SCHEDULE", f"Total lug quantity {qa} taken from the schedule; the split between the ends is not stated (shown as {qa - half} / {half}).")
            res.termination = "Cable lug (per schedule)"
            res.issues.append(("REVIEW", "Lug split not stated", f"Cable {cb.tag}: only a total lug quantity ({qa}) is given; the From/To split is an even division - confirm."))
        elif req is True:
            if res.conductors and con["kind"] != "UNKNOWN":
                f, t = n_lug * ends[0], n_lug * ends[1]
                ef = con["earth"] * ends[0] if (con["earth"] and rules.earth_lugged) else 0
                et = con["earth"] * ends[1] if (con["earth"] and rules.earth_lugged) else 0
                apply_lugs(f, t, "SCHEDULE + RULE", "Schedule says lugs are required; quantity = lugged conductors x lugged ends (rule table).", ef, et)
                res.termination = "Cable lug (per schedule)"
            else:
                res.issues.append(("REVIEW", "Lug quantity cannot be derived", f"Cable {cb.tag}: lugs are required but the number of conductors is unknown."))
    # ── Priority 2: explicit termination information ──
    if res.lug_required is None and not res.issues and cb.terminal_text:
        t = cb.terminal_text.upper()
        if re.search(r"LUG", t) and not re.search(r"NO LUG|WITHOUT LUG", t):
            if res.conductors and con["kind"] != "UNKNOWN":
                apply_lugs(n_lug * ends[0], n_lug * ends[1], "TERMINATION", f"Schedule termination '{cb.terminal_text}' uses lugs.",
                           con["earth"] * ends[0] if con["earth"] and rules.earth_lugged else 0, con["earth"] * ends[1] if con["earth"] and rules.earth_lugged else 0)
                res.termination = cb.terminal_text
        elif re.search(r"FERRULE|TERMINAL|TB\b|BLOCK|DIRECT|SCREW", t):
            apply_lugs(0, 0, "TERMINATION", f"Termination '{cb.terminal_text}' - cable lug not applicable.")
            res.termination = cb.terminal_text
    if res.lug_required is None and not res.issues and cb.ferrule:
        apply_lugs(0, 0, "TERMINATION", "Ferrule / terminal termination - cable lug not applicable.")
        res.termination = "Ferrule / Terminal"
    # ── Priority 3: project rule table ──
    if res.lug_required is None and not res.issues:
        cat = res.category
        if cat == "INSTRUMENTATION":
            use = rules.instrumentation_use_lugs
        elif cat == "CONTROL":
            use = rules.control_use_lugs
        elif cat == "POWER":
            use = rules.power_use_lugs
        else:
            use = None
        if use is None:
            res.issues.append(("REVIEW", "Lug requirement unknown", f"Cable {cb.tag} ({cb.cable_type}): the termination arrangement is not stated and the rule table cannot classify the cable "
                               "(size missing or between the control and power limits). No lug quantity generated."))
        elif use is False:
            apply_lugs(0, 0, "RULE", "Ferrule / terminal-block termination - cable lug not applicable." if cat != "POWER" else "Project rule: power cables are not lugged.")
            res.termination = "Ferrule / Terminal" if cat != "POWER" else "Per project rule (no lug)"
        elif res.conductors and con["kind"] in ("CORE", "PAIR", "TRIAD"):
            ef = con["earth"] * ends[0] if con["earth"] and rules.earth_lugged else 0
            et = con["earth"] * ends[1] if con["earth"] and rules.earth_lugged else 0
            apply_lugs(n_lug * ends[0], n_lug * ends[1], "RULE", f"Project rule: {cat.lower()} cables use lugs; {n_lug} conductor(s) x {sum(ends)} lugged end(s)"
                       + (f"; earth conductor lugged separately ({con['earth']} x {sum(ends)})." if ef or et else "."), ef, et)
            res.termination = "Cable lug (rule)"
            if con["earth"] and con["earth_size"] is None:
                res.issues.append(("REVIEW", "Earth conductor size not stated", f"Cable {cb.tag}: the earth conductor is lugged separately but its size is not stated."))
        else:
            res.issues.append(("REVIEW", "Lug quantity cannot be derived", f"Cable {cb.tag}: conductor count is unknown."))
    if res.lug_required is None and not res.issues:
        res.issues.append(("REVIEW", "Lug requirement unknown", f"Cable {cb.tag}: no lug, termination or rule information."))
    # ── user override ──
    if override and (override.get("lug_required") or override.get("lug_from") not in (None, "") or override.get("lug_to") not in (None, "")):
        _apply_override(res, override, con)
    res.status = ("ERROR" if any(s == "ERROR" for s, _, _ in res.issues) else "REVIEW" if any(s == "REVIEW" for s, _, _ in res.issues) else "OK")
    if res.source != "USER OVERRIDE":
        res.source = "REVIEW" if res.status != "OK" else "AUTO"
    if res.status != "OK" and res.source != "USER OVERRIDE":
        res.lug_from = res.lug_to = res.earth_from = res.earth_to = 0
        res.lug_required = None
    return res


def _apply_override(res: Result, o: dict, con: dict) -> None:
    req = (o.get("lug_required") or "").upper()
    res.issues = [(s, k, m) for s, k, m in res.issues if s == "ERROR" and k.startswith("Conflicting cable")]    # an override resolves REVIEW cases only
    res.source = "USER OVERRIDE"
    res.remarks = _clean_text(o.get("remarks"))
    if o.get("lug_type"):
        res.lug_type = _clean_text(o["lug_type"])
    if o.get("lug_size"):
        res.lug_size = _clean_text(o["lug_size"])
    if o.get("lug_material"):
        res.material = _clean_text(o["lug_material"])
    if req == "REVIEW":
        res.issues.append(("REVIEW", "Marked for review by the user", "The engineer set this cable to REVIEW."))
        res.source = "REVIEW"
        res.lug_from = res.lug_to = res.earth_from = res.earth_to = 0
        res.lug_required = None
        res.basis, res.reason = "USER OVERRIDE", "Engineer marked this cable for review."
        return
    if req == "NO":
        res.lug_from = res.lug_to = res.earth_from = res.earth_to = 0
        res.lug_required, res.basis, res.reason = False, "USER OVERRIDE", "Engineer states a cable lug is not required."
        return
    f, t = _count(o.get("lug_from")), _count(o.get("lug_to"))
    if "invalid" in (f[1], t[1]):
        res.issues.append(("ERROR", "Invalid lug quantity", "The override lug quantity must be a whole number, 0 or more."))
        return
    if f[0] is None and t[0] is None:
        n = con["cores"] if con["kind"] == "CORE" else (con["conductors"] or 0)
        if not n:
            res.issues.append(("REVIEW", "Lug quantity cannot be derived", "Enter the From / To lug quantities: the conductor count is unknown."))
            return
        f, t = (n, "ok"), (n, "ok")
    res.lug_from, res.lug_to = f[0] or 0, t[0] or 0
    res.earth_from = res.earth_to = 0
    res.lug_required = (res.lug_from + res.lug_to) > 0
    res.basis, res.reason = "USER OVERRIDE", "Lug quantities entered by the engineer (From + To)."
    res.termination = "Cable lug (user override)" if res.lug_required else "No lug (user override)"


def analyze_cables(cables: list[Cable], rules: Rules, overrides: Optional[dict] = None) -> list[Result]:
    overrides = overrides or {}
    out = []
    for cb in cables:
        ov = None
        if rules.allow_override:
            ov = overrides.get(f"tag:{cb.tag}") or overrides.get(f"type:{cable_key(cb.cable_type)}")
        out.append(decide(cb, rules, ov))
    return out


# ── summaries ────────────────────────────────────────────────────────────────
def _row(r: Result) -> dict:
    cb = r.cable
    con = r.construction
    cores = "REVIEW REQUIRED" if r.conductors is None else (
        f"{con['pairs']} pair = {con['conductors']} conductors" if con["kind"] == "PAIR" else
        f"{con['cores']} core" + (f" + earth" if con["earth"] else "") + f" = {con['conductors']} conductors" if con["kind"] == "CORE" else f"{con['conductors']} conductors")
    return {"cable_tag": cb.tag, "tag_known": cb.tag_known, "cable_type": cb.cable_type, "category": r.category, "is_nis": cb.is_nis or "Not stated",
            "cores": cores, "conductors": r.conductors, "cable_qty": 1, "from": cb.frm, "to": cb.to, "length": cb.length,
            "lug_required": {True: "YES", False: "NO", None: "REVIEW"}[r.lug_required], "termination": r.termination or "Not determined",
            "lug_from": r.lug_from + r.earth_from if r.lug_required is not None else None, "lug_to": r.lug_to + r.earth_to if r.lug_required is not None else None,
            "earth_lugs": r.earth_from + r.earth_to, "total": r.total if r.lug_required is not None else None,
            "lug_type": r.lug_type, "lug_size": r.lug_size, "earth_size": r.earth_size, "material": r.material,
            "status": r.status, "source": r.source, "basis": r.basis, "reason": r.reason or "; ".join(m for _, _, m in r.issues),
            "sheets": ", ".join(cb.sheets), "rows": ", ".join(str(x) for x in cb.rows[:6]) + ("…" if len(cb.rows) > 6 else ""),
            "occurrences": cb.occurrences, "remarks": r.remarks}


def build(results: list[Result], rules: Rules) -> dict:
    rows = [_row(r) for r in results]
    # cable type summary: same text but different termination/lug characteristics stay separate
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    for r, row in zip(results, rows):
        key = (cable_key(r.cable.cable_type), r.cable.is_nis, row["lug_required"], r.lug_type, r.lug_size, r.material, r.lug_from + r.earth_from if r.lug_required is not None else None,
               r.lug_to + r.earth_to if r.lug_required is not None else None, r.termination if r.lug_required is not True else "", r.status)
        g = groups.setdefault(key, {"cable_type": r.cable.cable_type, "is_nis": r.cable.is_nis or "Not stated", "cable_qty": 0, "cores": row["cores"], "category": r.category,
                                    "lug_required": row["lug_required"], "lug_from": row["lug_from"], "lug_to": row["lug_to"],
                                    "per_cable": row["total"], "total": 0, "lug_type": r.lug_type, "lug_size": r.lug_size, "material": r.material,
                                    "termination": row["termination"], "status": r.status, "source": r.source, "reason": row["reason"], "length": 0.0, "tags": []})
        g["cable_qty"] += 1
        g["total"] += row["total"] or 0
        g["tags"].append(r.cable.tag)
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
        for label, f, t, size in (("power / main conductors", r.lug_from, r.lug_to, r.lug_size), ("earth conductor", r.earth_from, r.earth_to, r.earth_size)):
            if f + t <= 0:
                continue
            k = (r.lug_type, size, r.material, label)
            p = proc.setdefault(k, {"lug_type": r.lug_type, "conductor_size": size, "material": r.material, "use": label, "spec": NS, "from_qty": 0, "to_qty": 0, "qty": 0, "cables": 0})
            p["from_qty"] += f
            p["to_qty"] += t
            p["qty"] += f + t
            p["cables"] += 1
    procurement = sorted(proc.values(), key=lambda p: (p["lug_type"], p["conductor_size"], p["material"]))
    by_size, by_mat = OrderedDict(), OrderedDict()
    for p in procurement:
        by_size[p["conductor_size"]] = by_size.get(p["conductor_size"], 0) + p["qty"]
        by_mat[p["material"]] = by_mat.get(p["material"], 0) + p["qty"]
    review = [r for r in results if r.status != "OK"]
    exceptions = []
    for r in results:
        for sev, kind, msg in r.issues:
            exceptions.append({"severity": sev, "kind": kind, "ref": r.cable.tag, "message": msg, "sheet": ", ".join(r.cable.sheets), "row": r.cable.rows[0] if r.cable.rows else None})
    kpis = {"total_lugs": sum(r.total for r in results if r.lug_required), "cables": len(results), "cable_types": len({cable_key(r.cable.cable_type) for r in results}),
            "with_lugs": sum(1 for r in results if r.lug_required), "without_lugs": sum(1 for r in results if r.lug_required is False),
            "review": sum(1 for r in results if r.status == "REVIEW" or (r.lug_required is None and r.status != "ERROR")), "errors": sum(1 for r in results if r.status == "ERROR"),
            "overrides": sum(1 for r in results if r.source == "USER OVERRIDE")}
    return {"kpis": kpis, "cable_wise": rows, "types": types, "procurement": procurement,
            "by_size": [{"size": k, "qty": v} for k, v in by_size.items()], "by_material": [{"material": k, "qty": v} for k, v in by_mat.items()],
            "exceptions": exceptions}


RULE_TEXT = [
    ("Physical cable quantity", "Unique cable tag number = one physical cable. A tag repeated on several signal rows is counted once (switchable)."),
    ("Cable length", "Reported for information only. It is never used to calculate lugs: one cable = one termination set, whatever its length."),
    ("Priority", "1 explicit lug data in the schedule; 2 explicit termination data (ferrule / terminal / lug); 3 the project rule table; 4 REVIEW - no quantity is generated when the arrangement is unknown."),
    ("Pair / triad instrumentation cables", "Ferrule / terminal-block termination by default: lugs = 0 (rule 'instrumentation cables use lugs' = NO)."),
    ("Power cables", "Lugs per conductor at each lugged end when the rule 'power cables use lugs' = YES: lugs = lugged conductors x lugged ends x cable quantity."),
    ("Asymmetric ends", "Lug quantity From and To are calculated separately: total per cable = From + To."),
    ("Earth conductor", "A separate earth conductor ('+ E') is counted on its own line and its size is shown separately; it is not assumed identical to the phase conductors."),
    ("Pairs", "A pair is two conductors (12P = 24 conductors, never 12 cores)."),
    ("Lug type / material / part number", "Carried from the schedule or the user; otherwise NOT SPECIFIED. No lug model is invented; conductor size is not a part number."),
]


def to_workbook(res: dict, rules: Rules, source_name: str = "uploaded cable schedule") -> bytes:
    head = PatternFill("solid", start_color="163A5F", end_color="163A5F")
    thin = Side(style="thin", color="B7C3D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    note = f"Source: {source_name} (read only - original values not changed). Lug quantities follow terminations, never cable length."

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
    sheet("LUG SUMMARY", ["ITEM", "VALUE"], [["TOTAL LUGS REQUIRED", k["total_lugs"]], ["Physical cables analysed", k["cables"]], ["Cable types", k["cable_types"]],
                                             ["Cables requiring lugs", k["with_lugs"]], ["Cables not requiring lugs", k["without_lugs"]],
                                             ["Cables requiring review", k["review"]], ["Cables with errors", k["errors"]], ["User overrides", k["overrides"]]] +
          [["Lugs of size " + s["size"], s["qty"]] for s in res["by_size"]] + [["Lugs of material " + m["material"], m["qty"]] for m in res["by_material"]], {1: 40})
    sheet("CABLE TYPE SUMMARY", ["CABLE TYPE", "IS/NIS", "CABLE QTY", "CORES / CONDUCTORS", "LUG REQUIRED", "LUGS FROM / CABLE", "LUGS TO / CABLE", "LUGS / CABLE", "TOTAL LUGS",
                                 "LUG TYPE", "CONDUCTOR SIZE", "MATERIAL", "TERMINATION", "SOURCE", "REASON"],
          [[t["cable_type"], t["is_nis"], t["cable_qty"], t["cores"], t["lug_required"], t["lug_from"], t["lug_to"], t["per_cable"], t["total"], t["lug_type"], t["lug_size"],
            t["material"], t["termination"], t["source"], t["reason"]] for t in res["types"]], {15: 60, 4: 30})
    sheet("CABLE-WISE DETAIL", ["CABLE TAG", "CABLE TYPE", "CATEGORY", "IS/NIS", "CABLE QTY", "CORES / CONDUCTORS", "FROM", "TO", "CABLE LENGTH (info only)", "LUG REQUIRED", "TERMINATION",
                                "LUG FROM", "LUG TO", "TOTAL LUGS", "LUG TYPE", "LUG SIZE", "MATERIAL", "STATUS", "SOURCE", "CALCULATION BASIS", "SHEET", "ROW(S)", "SCHEDULE ROWS WITH THIS TAG", "REMARKS"],
          [[c["cable_tag"], c["cable_type"], c["category"], c["is_nis"], c["cable_qty"], c["cores"], c["from"], c["to"], c["length"], c["lug_required"], c["termination"], c["lug_from"],
            c["lug_to"], c["total"], c["lug_type"], c["lug_size"], c["material"], c["status"], c["source"], f"{c['basis']}: {c['reason']}", c["sheets"], c["rows"], c["occurrences"], c["remarks"]]
           for c in res["cable_wise"]], {20: 70, 6: 30})
    sheet("LUG PROCUREMENT", ["LUG TYPE", "CONDUCTOR SIZE", "MATERIAL", "LUG SPECIFICATION / PART NO.", "USE", "FROM-END QTY", "TO-END QTY", "TOTAL QTY", "CABLES"],
          [[p["lug_type"], p["conductor_size"], p["material"], p["spec"], p["use"], p["from_qty"], p["to_qty"], p["qty"], p["cables"]] for p in res["procurement"]] +
          [["TOTAL", "", "", "", "", sum(p["from_qty"] for p in res["procurement"]), sum(p["to_qty"] for p in res["procurement"]), sum(p["qty"] for p in res["procurement"]), ""]] if res["procurement"]
          else [["No lugs required by the analysed cables", "", "", "", "", "", "", 0, ""]])
    sheet("REVIEW - EXCEPTIONS", ["SEVERITY", "KIND", "CABLE / REFERENCE", "SHEET", "ROW", "MESSAGE"],
          [[e["severity"], e["kind"], e["ref"], e.get("sheet", ""), e.get("row"), e["message"]] for e in res["exceptions"]] or [["OK", "", "", "", "", "No exceptions"]], {6: 100})
    rule_rows = [["Rule", a, b] for a, b in RULE_TEXT] + [
        ["Setting", "Count duplicate cable tags once", "YES" if rules.count_duplicates_once else "NO"],
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


def analyze(data: bytes, rules_d: Optional[dict] = None, overrides: Optional[dict] = None) -> tuple[dict, Rules]:
    rules = Rules.from_dict(rules_d)
    cables, exc, infos = read_cables(data, rules)
    results = analyze_cables(cables, rules, overrides)
    out = build(results, rules)
    out["exceptions"] = exc + out["exceptions"]
    order = {"ERROR": 0, "REVIEW": 1, "WARNING": 1, "INFO": 2}
    out["exceptions"].sort(key=lambda e: order.get(e["severity"], 3))
    out["sheets"] = infos
    out["used_sheets"] = sorted({s for c in cables for s in c.sheets})
    out["rules"] = {"count_duplicates_once": rules.count_duplicates_once, "instrumentation_use_lugs": rules.instrumentation_use_lugs, "control_use_lugs": rules.control_use_lugs,
                    "power_use_lugs": rules.power_use_lugs, "lugged_ends": rules.lugged_ends, "earth_lugged": rules.earth_lugged, "power_min_mm2": rules.power_min_mm2,
                    "control_max_mm2": rules.control_max_mm2, "allow_override": rules.allow_override}
    out["rule_text"] = [{"rule": a, "text": b} for a, b in RULE_TEXT]
    return out, rules
