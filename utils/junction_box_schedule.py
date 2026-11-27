"""
Junction Box Schedule engine (sub-generator of the Cable Schedule module).

Pure functions - no web framework, no database:

    read_schedule(bytes)            the generated Cable Schedule -> one entry per instrument (header-based, merged-cell aware)
    analyze(entries, iodb_info)     one record per unique junction box: instruments, cables, glands, terminals, suggestions
    evaluate(jb, config, design)    the confirmed configuration of one JB -> terminals used / spare / spare %, errors, warnings
    build_workbook(template, rows)  the standard JB_SCHEDULE template filled with the evaluated rows (JB_SCHEDULE only)

Nothing is invented: a value comes from the generated Cable Schedule, from the project's IODB stored with it, from a rule
printed in the standard template, or from the engineer. Anything else stays blank and is reported as missing.
"""
from __future__ import annotations

import io
import math
import re
from collections import Counter, OrderedDict
from copy import copy
from typing import Any, Optional

import openpyxl
from openpyxl.styles import Alignment
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

# ── standard template rules (read from STANDARD_JB_SCHEDULE_TEMPLATE_Ref_Columns_Removed.xlsx) ───────────────────────
CATEGORIES = {   # LOOKUPS L_CAT: category -> its description in the template
    "AJB": "ANALOG SIGNAL JUNCTION BOX",
    "DJB": "DIGITAL JUNCTION BOX (DI + DO)",
    "DIJB": "DIGITAL INPUT JUNCTION BOX",
    "DOJB": "DIGITAL OUTPUT JUNCTION BOX",
    "SMB": "SOLENOID BOX FOR ON-OFF VALVES",
}
LISTS = {  # LOOKUPS - the controlled lists the output keeps as in-cell drop-downs (the LOOKUPS sheet itself is not delivered)
    "category": list(CATEGORIES),
    "isnis": ["IS", "NIS", "ESD"],
    "protection": ["WEATHERPROOF (IP66)", "WEATHERPROOF (IP65)", "Ex e", "Ex d", "Ex ia"],
    "material": ["SS316", "GRP", "ALUMINIUM"],
    "term_type": ["PUSH-FIT CLAMP-ON", "SPRING CLAMP", "SCREW"],
    "entry": ["BOTTOM", "SIDE", "TOP"],
    "gland_size": ['1/2" NPT', '3/4" NPT', '1" NPT', '1 1/4" NPT', '1 1/2" NPT', '2" NPT', "M20", "M25", "M32", "M40", "NA"],
    "cable": ["1P x 1.0 mm2", "1P x 1.5 mm2", "2P x 1.0 mm2", "2P x 1.5 mm2", "1T x 1.5 mm2", "2C x 1.5 mm2", "4C x 1.5 mm2",
              "5C x 1.5 mm2", "12C x 1.5 mm2", "14C x 1.5 mm2", "16C x 1.5 mm2", "24C x 1.5 mm2", "4P x 1.0 mm2", "6P x 1.0 mm2",
              "12P x 1.0 mm2", "12P x 1.5 mm2", "NA"],
}
DESIGN_DEFAULTS = {"max_instruments": 10, "design_spare_pct": 0.20}   # COVER!B29 / B31 of the original template
_SPARE_TAGS = re.compile(r"^(SPARES?|SPARE[\s\-_]*\d*|NA|N/A|-+|TBA|TBD|NIL)$", re.I)
_PLACEHOLDER = re.compile(r"^(TBA|TBD|NA|N/A|-+|NIL)?$", re.I)


class JBError(Exception):
    """A problem the engineer can act on (shown as-is)."""


def _s(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v).replace("\xa0", " ")).strip() if v is not None else ""


def _label(v: Any) -> str:
    return _s(v).upper()


def natural_key(text: str) -> list:
    return [int(t) if t.isdigit() else t.upper() for t in re.split(r"(\d+)", text or "")]


def _unique(values) -> list:
    out, seen = [], set()
    for v in values:
        v = _s(v)
        if v and v.upper() not in seen:
            seen.add(v.upper())
            out.append(v)
    return out


# ── 1. reading the generated Cable Schedule ──────────────────────────────────────────────────────────────────────────
_COLUMN_RULES = [   # (field, regex on the upper-case header label) - first match wins, order matters
    ("branch_gland_inst_size", r"INSTRUMENT SIDE GLAND SIZE"),
    ("branch_gland_inst_qty", r"INSTRUMENT SIDE GLAND (QTY|QUANTITY)"),
    ("jb_gland_size", r"^JB SIDE GLAND SIZE|^JB GLAND SIZE"),
    ("jb_gland_qty", r"^JB SIDE GLAND (QTY|QUANTITY)"),
    ("main_gland_size", r"^JB END GLAND SIZE|^MAIN CABLE GLAND SIZE"),
    ("panel_gland_size", r"^PANEL END GLAND SIZE"),
    ("branch_cable_tag", r"INSTRUMENT TO JB CABLE TAG|BRANCH CABLE (TAG|NO)"),
    ("branch_cable_type", r"^INSTRUMENT TO JB CABLE( TYPE| SIZE)?$|BRANCH CABLE (TYPE|SIZE)"),
    ("main_cable_tag", r"MAIN CABLE (TAG|NO)"),
    ("main_cable_type", r"MAIN CABLE (TYPE|SIZE)"),
    ("jb", r"^(JB|JUNCTION BOX) (TAG|NO)"),
    ("terminal", r"TB DETAILS AT JB|^JB TERMINAL"),
    ("io", r"SIGNAL I/O TYPE|^I/O TYPE|^SIGNAL TYPE"),
    ("desc", r"DESCRIPTION"),
    ("tag", r"^(INSTRUMENT )?TAG( NO| NUMBER)?\.?$"),
]


def _resolve(ws, r: int, c: int, depth: int = 0):
    """A cell's value; a plain '=H9' reference (the generator's '=H9' / '=I9' style) is followed."""
    v = ws.cell(r, c).value
    if isinstance(v, str) and v.startswith("="):
        m = re.fullmatch(r"=\s*\$?([A-Z]{1,3})\$?(\d+)\s*", v)
        if m and depth < 5:
            return _resolve(ws, int(m.group(2)), column_index_from_string(m.group(1)), depth + 1)
        return None
    return v


def _find_header(ws) -> Optional[tuple]:
    for r in range(1, min(ws.max_row, 40) + 1):
        labels = {c: _label(ws.cell(r, c).value) for c in range(1, min(ws.max_column, 80) + 1)}
        labels = {c: v for c, v in labels.items() if v}
        if len(labels) < 5:
            continue
        cols: dict = {}
        for c, lab in labels.items():
            for field, rx in _COLUMN_RULES:
                if field not in cols and re.search(rx, lab):
                    cols[field] = c
                    break
        if {"tag", "jb"} <= set(cols):
            return r, cols
    return None


def read_schedule(data: bytes) -> dict:
    """
    -> {"entries": [...], "sheets": [...], "notes": [...]}. One entry per instrument block: its tag, signal type, branch
    cable, JB, the terminal rows it occupies at the JB and its glands. Columns are found by their headings.
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data))
    except Exception as exc:
        raise JBError("The generated Cable Schedule could not be opened.") from exc
    entries, sheets, notes = [], [], []
    for ws in wb.worksheets:
        h = _find_header(ws)
        if not h:
            continue
        hr, cols = h
        used = 0
        cur: Optional[dict] = None

        def cell(r, field):
            return _s(_resolve(ws, r, cols[field])) if field in cols else ""

        for r in range(hr + 1, ws.max_row + 1):
            tag_val = ws.cell(r, cols["tag"]).value
            if _s(tag_val):                                              # first row of an instrument block
                cur = {"sheet": ws.title, "row": r, "tag": _s(tag_val), "terminals": [], "jb": cell(r, "jb")}
                for f in ("desc", "io", "branch_cable_tag", "branch_cable_type", "main_cable_tag", "main_cable_type",
                          "jb_gland_size", "jb_gland_qty", "main_gland_size", "panel_gland_size", "branch_gland_inst_size"):
                    cur[f] = cell(r, f)
                entries.append(cur)
                used += 1
            if cur is not None and "terminal" in cols:
                t = _resolve(ws, r, cols["terminal"])
                raw = ws.cell(r, cols["terminal"]).value
                if _s(t) != "":
                    cur["terminals"].append(_s(t))
                elif _s(raw) != "":                                      # a terminal formula that cannot be followed: still a row
                    cur["terminals"].append(f"#row{r}")
            if cur is not None and not cur["jb"] and r > cur["row"] and "jb" in cols:
                cur["jb"] = cell(r, "jb")                                 # JB tag typed on a later row of the block
        if used:
            sheets.append(ws.title)
    if not entries:
        raise JBError("No instrument cable rows with a JB tag were found in the generated Cable Schedule.")
    return {"entries": entries, "sheets": sheets, "notes": notes}


def is_spare(tag: str) -> bool:
    return bool(_SPARE_TAGS.match(_s(tag)))


# ── 2. the project's IODB (stored with the schedule) - IS/NIS, area class and area name per JB ───────────────────────
def read_iodb_info(iodb_bytes: Optional[bytes]) -> dict:
    """JB tag (upper) -> {"isnis": [...], "area_class": [...], "location": [...], "area": [...]}. Empty when unreadable."""
    if not iodb_bytes:
        return {}
    try:
        from .file_handler import read_iodb
        df, err = read_iodb(io.BytesIO(iodb_bytes))
        if err or df is None:
            return {}
    except Exception:
        return {}
    norm = {re.sub(r"[^A-Z0-9]", "", str(c).upper()): c for c in df.columns}

    def col(*names):
        for n in names:
            k = re.sub(r"[^A-Z0-9]", "", n.upper())
            if k in norm:
                return norm[k]
        return None
    jbc = col("JUNCTION BOX TAG NO.", "JUNCTION BOX TAG NO", "JB TAG NO", "JB TAG")
    if jbc is None:
        return {}
    fields = {"isnis": col("IS/NIS TYPE", "IS/NIS"), "area_class": col("AREA CLASSIFICATION"),
              "location": col("LOCATION"), "area": col("AREA")}
    out: dict = {}
    for _, row in df.iterrows():
        jb = _s(row.get(jbc))
        if not jb or _PLACEHOLDER.match(jb):
            continue
        rec = out.setdefault(jb.upper(), {k: [] for k in fields})
        for k, c in fields.items():
            if c is not None:
                v = _s(row.get(c))
                if v and not _PLACEHOLDER.match(v):
                    rec[k].append(v)
    return {jb: {k: _unique(v) for k, v in rec.items()} for jb, rec in out.items()}


# ── 3. one record per junction box ───────────────────────────────────────────────────────────────────────────────────
def analyze(schedule: dict, iodb_info: Optional[dict] = None) -> dict:
    entries = schedule["entries"]
    iodb_info = iodb_info or {}
    groups: "OrderedDict[str, list]" = OrderedDict()
    spellings: dict = {}
    unassigned = 0
    for e in entries:
        jb = _s(e["jb"])
        if not jb or _PLACEHOLDER.match(jb):
            unassigned += 1
            continue
        groups.setdefault(jb.upper(), []).append(e)
        spellings.setdefault(jb.upper(), []).append(jb)
    tag_jbs: dict = {}
    for key, es in groups.items():
        for e in es:
            if not is_spare(e["tag"]):
                tag_jbs.setdefault(e["tag"].upper(), set()).add(key)
    cable_jbs: dict = {}                                           # main cable (upper) -> the junction boxes it is shown against
    for key, es in groups.items():
        for e in es:
            if not is_spare(e["tag"]) and _cable_tag(e["main_cable_tag"]):
                cable_jbs.setdefault(_cable_tag(e["main_cable_tag"]).upper(), set()).add(key)
    jbs = []
    for key in sorted(groups, key=natural_key):
        es = groups[key]
        real = [e for e in es if not is_spare(e["tag"])]
        spares = [e for e in es if is_spare(e["tag"])]
        warnings: list = []
        counts = Counter(re.sub(r"\s+", " ", x.strip()) for x in spellings[key])
        # shown spelling: the most used one; on a tie the upper-case one (JB tags are written in capitals)
        raw = sorted(counts, key=lambda x: (-counts[x], x != x.upper(), x))
        # the same JB written in different ways in the schedule (case / spacing): merged, and reported
        distinct_raw = {re.sub(r"\s+", " ", x.strip()) for x in spellings[key]}
        if len(distinct_raw) > 1:
            warnings.append(f"The JB tag is written in {len(distinct_raw)} ways in the Cable Schedule ({', '.join(sorted(distinct_raw))}); "
                            "the rows were merged into one junction box. Please review.")
        tags = _unique(e["tag"] for e in real)
        io_types = Counter(_s(e["io"]).upper() for e in real if _s(e["io"]))
        branch = _unique(e["branch_cable_tag"] for e in real)
        if any(not _s(e["branch_cable_tag"]) for e in real):
            warnings.append("Some instruments of this JB have no branch cable tag; the branch cable count covers only the cables that have one.")
        btypes: dict = {}
        for e in real:
            if _s(e["branch_cable_tag"]) and _s(e["branch_cable_type"]):
                btypes.setdefault(e["branch_cable_tag"].upper(), set()).add(_s(e["branch_cable_type"]).upper())
        for t, ts in btypes.items():
            if len(ts) > 1:
                warnings.append(f"Branch cable {t} has conflicting cable types in the Cable Schedule ({', '.join(sorted(ts))}).")
        main_cables = _main_cables(key, real, cable_jbs, warnings)
        for e in real:
            other = tag_jbs.get(e["tag"].upper(), set()) - {key}
            if other and e["tag"] in tags:
                warnings.append(f"Instrument {e['tag']} is also connected to {', '.join(sorted(other, key=natural_key))}.")
        warnings = list(dict.fromkeys(warnings))
        # terminals: the terminal rows of the instrument blocks (spare rows are not used terminals - template rule)
        term_labels = [t for e in real for t in e["terminals"]]
        pending = [e["tag"] for e in real if not e["terminals"] or any(_PLACEHOLDER.match(t) and t for t in e["terminals"])]
        numeric = [int(float(t)) for t in term_labels if re.fullmatch(r"\d+(\.0+)?", t)]
        dup_terms = sorted({t for t, n in Counter(term_labels).items() if n > 1 and not t.startswith("#row")})
        if dup_terms:
            warnings.append(f"Terminal number(s) {', '.join(dup_terms[:8])} are used by more than one instrument row.")
        auto_ok = bool(real) and not pending
        info = iodb_info.get(key, {})
        jbs.append({
            "jb_no": raw[0] if raw else key, "key": key,
            "instrument_count": len(tags), "instruments": tags, "spare_rows": len(spares),
            "io_types": dict(io_types),
            "branch_cable_count": len(branch), "branch_cables": branch,
            "main_cable_count": len(main_cables), "main_cables": main_cables,
            "branch_gland_sizes": _unique(e["jb_gland_size"] for e in real),
            "branch_gland_qty": _qty_sum(e["jb_gland_qty"] for e in real),
            "main_gland_sizes": _unique(e["main_gland_size"] for e in real),
            "terminals": {"auto_available": auto_ok, "count": len(term_labels), "highest": max(numeric) if numeric else None,
                          "pending_instruments": pending[:20], "pending_count": len(pending), "duplicates": dup_terms},
            "iodb": info, "warnings": warnings,
            "suggest": _suggest(key, tags, io_types, info),
        })
    notes = []
    if unassigned:
        notes.append(f"{unassigned} instrument row(s) have no JB tag and are not part of any junction box.")
    return {"jbs": jbs, "instrument_total": len({t.upper() for j in jbs for t in j["instruments"]}),
            "sheets": schedule["sheets"], "notes": notes}


def _cable_tag(value: Any) -> str:
    """The identification of a physical main cable; '' for a blank or a placeholder (TBA, NA, - ...)."""
    v = _s(value)
    return "" if _PLACEHOLDER.match(v) else v


def _type_key(value: str) -> str:
    """Identity of a cable specification: only case, spacing and the way mm2 is written are ignored. Cores and pairs
    ('12X1.5' / '12PX1.5'), sizes and every other word stay significant."""
    v = _s(value).upper().replace("\u00b2", "2")
    v = re.sub(r"SQ\.?\s*MM\.?|MM\s*2", "MM2", v)
    return re.sub(r"\s+", "", v)


def _distinct(values, key) -> list:
    """The values that are not placeholders, one per identity, in order of appearance."""
    out: "OrderedDict[str, str]" = OrderedDict()
    for v in values:
        v = _s(v)
        if v and not _PLACEHOLDER.match(v):
            out.setdefault(key(v), v)
    return list(out.values())


def _main_cables(jb_key: str, real: list, cable_jbs: dict, warnings: list) -> list:
    """
    One record per distinct physical main cable of a junction box: {"tag", "type", "gland_size", "types", "gland_sizes"}.
    A cable named on many instrument rows is one cable; its type and JB-end gland size are taken from its own rows only.
    Different values for one cable are all kept (shown as 'a / b') and reported; nothing is picked arbitrarily.
    """
    rows: "OrderedDict[str, list]" = OrderedDict()
    for e in real:
        tag = _cable_tag(e["main_cable_tag"])
        if tag:
            rows.setdefault(tag.upper(), []).append(e)
    unidentified = sum(1 for e in real if not _cable_tag(e["main_cable_tag"]))
    if unidentified:
        warnings.append(f"{unidentified} instrument row(s) of this JB have no main cable number (blank or TBA); "
                        "the main cable count covers only the identified cables.")
    out = []
    for upper in sorted(rows, key=natural_key):
        es = rows[upper]
        tag = _s(es[0]["main_cable_tag"])
        rec = {"tag": tag}
        for field, plural, source, label, key in (
                ("type", "types", "main_cable_type", "cable type", _type_key),
                ("gland_size", "gland_sizes", "main_gland_size", "JB end gland size",
                 lambda v: _list_spelling(v, LISTS["gland_size"]).upper())):
            found = _distinct((e[source] for e in es), key)
            blank = _unique(e[source] for e in es)                    # what is written when there is no real value (TBA ...)
            rec[plural] = found
            rec[field] = " / ".join(found) if found else " / ".join(blank)
            if len(found) > 1:
                warnings.append(f"Main cable {tag} has conflicting {label}s in the Cable Schedule ({', '.join(found)}). Please review.")
            elif not found:
                warnings.append(f"Main cable {tag} has no {label} in the Cable Schedule.")
        others = cable_jbs.get(upper, set()) - {jb_key}
        if others:
            warnings.append(f"Main cable {tag} is also shown against {', '.join(sorted(others, key=natural_key))}. "
                            "Please verify which junction box it terminates in.")
        out.append(rec)
    return out


def _qty_sum(values) -> Optional[float]:
    total, seen = 0.0, False
    for v in values:
        try:
            total += float(_s(v))
            seen = True
        except ValueError:
            pass
    return (int(total) if total == int(total) else total) if seen else None


def _suggest(key: str, tags: list, io_types: Counter, info: dict) -> dict:
    """Defaults the engineer can change; each carries where it came from."""
    out: dict = {}
    kinds = set(io_types)
    if re.search(r"(^|[^A-Z])SMB([^A-Z]|$)", key):
        out["category"] = {"value": "SMB", "source": "JB tag contains SMB"}
    elif kinds and kinds <= {"AI", "AO"}:
        out["category"] = {"value": "AJB", "source": "signal types of the connected instruments are analog (template rule)"}
    elif kinds == {"DI"}:
        out["category"] = {"value": "DIJB", "source": "signal types of the connected instruments are digital inputs"}
    elif kinds == {"DO"}:
        out["category"] = {"value": "DOJB", "source": "signal types of the connected instruments are digital outputs"}
    elif kinds == {"DI", "DO"}:
        out["category"] = {"value": "DJB", "source": "signal types of the connected instruments are DI and DO"}
    if "category" in out:
        out["jb_desc"] = {"value": CATEGORIES[out["category"]["value"]], "source": "template description of the category"}
    if len(info.get("isnis", [])) == 1:
        out["isnis"] = {"value": info["isnis"][0].upper(), "source": "IODB (IS/NIS TYPE)"}
    if len(info.get("location", [])) == 1:
        out["unit_name"] = {"value": info["location"][0], "source": "IODB (LOCATION)"}
    return out


# ── 4. one confirmed junction box -> results ─────────────────────────────────────────────────────────────────────────
FIELDS_GENERATION = ("category", "terminal_capacity")
FIELDS_SUBMISSION = [("unit_name", "UNIT / AREA NAME"), ("jb_desc", "JB DESCRIPTION"), ("isnis", "IS / NIS"), ("location", "LOCATION"),
                     ("protection", "ENCLOSURE PROTECTION"), ("material", "ENCLOSURE MATERIAL"),
                     ("main_cable_no", "MAIN CABLE NO."), ("main_cable_type", "MAIN CABLE TYPE"),
                     ("main_gland_size", "MAIN CABLE GLAND SIZE")]
FIELDS_SUBMISSION_NON_SMB = [("branch_gland_size", "BRANCH GLAND SIZE")]
EXCEEDED = "Terminal capacity exceeded. Please review the selected junction box capacity."


def _whole(v: Any, minimum: int) -> Optional[int]:
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) and f >= minimum else None


def _join(values) -> str:
    return ", ".join(_unique(values))


def _list_spelling(value: str, options: list) -> str:
    """A value in the template list's spelling when it is the same thing ('M20x1.5' -> 'M20', '4PX1.5 Sqmm' -> '4P x 1.5 mm2')."""
    v = _s(value)
    for o in options:
        if v.upper() == o.upper():
            return o
    m = re.fullmatch(r"(M\d+)\s*[xX]\s*[\d.]+", v)
    if m and m.group(1) in options:
        return m.group(1)
    m = re.fullmatch(r"(\d+)\s*([PCT])\s*[xX]\s*([\d.]+)\s*(?:sq\.?\s?mm|mm2|mm²)", v, re.I)
    if m:
        cand = f"{m.group(1)}{m.group(2).upper()} x {m.group(3)} mm2"
        if cand in options:
            return cand
    return v


def evaluate(jb: dict, cfg: Optional[dict], design: Optional[dict] = None) -> dict:
    """
    The effective row of one junction box and its checks. `jb` is an analysis record, `cfg` what the engineer confirmed.
    Returns {"row": {...}, "source": {...}, "errors": [...], "warnings": [...], "missing_generation": [...],
             "missing_submission": [...], "status": "Ready"|"Input Required"|"Error", ...}.
    """
    cfg = cfg or {}
    d = {**DESIGN_DEFAULTS, **(design or {})}
    sug = jb["suggest"]
    errors: list = []
    warnings: list = list(jb["warnings"])                 # the analysis notes are review items, not errors
    row: dict = {}
    src: dict = {}

    def pick(field: str, schedule_value: str = "", schedule_src: str = "Cable Schedule", suggest_key: Optional[str] = None):
        v = _s(cfg.get(field))
        if v:
            row[field], src[field] = v, "user"
            return
        if schedule_value:
            row[field], src[field] = schedule_value, schedule_src
            return
        s = sug.get(suggest_key or field)
        if s:
            row[field], src[field] = s["value"], s["source"]
            return
        row[field], src[field] = "", ""

    pick("category")
    category = row["category"]
    if category and category not in CATEGORIES:
        errors.append(f"JB category '{category}' is not one of {', '.join(CATEGORIES)}.")
    pick("jb_desc")
    pick("isnis")
    iod = jb["iodb"]
    if len(iod.get("isnis", [])) > 1 and not _s(cfg.get("isnis")):
        row["isnis"], src["isnis"] = "", ""
        warnings.append(f"IS and NIS signals are both connected to this junction box in the IODB ({', '.join(iod['isnis'])}); "
                        "they never share a box - choose IS / NIS for this JB or correct the IODB.")
    pick("unit_name")
    for f in ("location", "protection", "material", "terminal_type", "cable_entry", "spare_entry_size", "remarks"):
        v = _s(cfg.get(f))
        row[f], src[f] = (v, "user") if v else ("", "")
    # cables and glands: the Cable Schedule, unless the engineer typed a value
    # the main cable columns hold one line per physical cable, in the same order in all three
    cables = jb["main_cables"]
    several = len(cables) > 1
    incomplete = set()
    for field, key, options, label in (("main_cable_no", "tag", None, "MAIN CABLE NO."),
                                       ("main_cable_type", "type", LISTS["cable"], "MAIN CABLE TYPE"),
                                       ("main_gland_size", "gland_size", LISTS["gland_size"], "MAIN CABLE GLAND SIZE")):
        values = [_s(m.get(key)) for m in cables]
        if options:
            values = [_list_spelling(v, options) for v in values]
        typed = [x.strip() for x in re.split(r"[;\n]", str(cfg.get(field) or "")) if x.strip()]
        if typed and several:
            if len(typed) != len(cables):
                errors.append(f"{label}: this junction box has {len(cables)} main cables - enter one value per cable, in the "
                              "order shown, separated by ';' (or leave it blank to use the Cable Schedule).")
            row[field], src[field] = "\n".join(_s(x) for x in typed), "user"
            continue
        if typed:
            row[field], src[field] = _s(cfg.get(field)), "user"
            continue
        if several:
            if any(not v or _PLACEHOLDER.match(v) for v in values):
                incomplete.add(label)
            row[field] = "\n".join(v or "-" for v in values)
        elif cables:
            row[field] = values[0]
        elif field == "main_gland_size":                                   # no identified cable: what the schedule shows
            row[field] = _join(_list_spelling(x, options) for x in jb["main_gland_sizes"])
        else:
            row[field] = ""
        src[field] = "Cable Schedule" if row[field] else ""
    pick("branch_gland_size", _join(_list_spelling(x, LISTS["gland_size"]) for x in jb["branch_gland_sizes"]))
    row["branch_cable_count"], src["branch_cable_count"] = jb["branch_cable_count"], "Cable Schedule"
    row["main_cable_count"], src["main_cable_count"] = jb["main_cable_count"], "Cable Schedule"
    row["spare_entries"] = _whole(cfg.get("spare_entries"), 0)
    # capacity
    cap_raw = cfg.get("terminal_capacity")
    cap = _whole(cap_raw, 1)
    if cap_raw not in (None, "") and cap is None:
        errors.append("Total terminal capacity must be a whole number greater than zero.")
    row["terminal_capacity"], src["terminal_capacity"] = cap, ("user" if cap else "")
    # terminals used
    inst = jb["instrument_count"]
    method = (cfg.get("terminals_method") or "auto").lower()
    t = jb["terminals"]
    used, used_src, auto_used = None, "", None
    if category == "SMB":
        auto_used, auto_src = inst, "template rule: a solenoid box uses one way per instrument"
    elif t["auto_available"]:
        auto_used, auto_src = t["count"], "terminal rows of the generated Cable Schedule"
    else:
        auto_src = ""
    if method == "manual":
        used = _whole(cfg.get("terminals_manual"), 0)
        used_src = "user-confirmed total"
        if used is None:
            errors.append("Enter the total used terminals (a whole number) or choose another calculation method.")
    elif method == "per_instrument":
        n = _whole(cfg.get("terminals_per_instrument"), 1)
        if n is None:
            errors.append("Enter the terminals required per instrument (a whole number greater than zero).")
        else:
            used, used_src = n * inst, f"user-confirmed {n} terminal(s) x {inst} instrument(s)"
    else:
        used, used_src = auto_used, auto_src
    if used is not None and method != "auto" and auto_used is not None and used != auto_used:
        warnings.append(f"The user-provided terminals used ({used}) differ from the termination data of the Cable Schedule ({auto_used}). Please review.")
    row["terminals_used"], src["terminals_used"] = used, used_src
    row["terminals_method"] = method
    # spare
    spare = pct = None
    if cap and used is not None:
        spare = cap - used
        if spare < 0:
            errors.append(EXCEEDED)
            spare = None
        else:
            pct = spare / cap
    hi = t["highest"]
    if cap and hi and category != "SMB" and hi > cap:
        errors.append(f"The highest terminal number in the Cable Schedule ({hi}) is above the terminal capacity ({cap}).")
    row["spare_terminals"], row["spare_pct"] = spare, pct
    row["instrument_count"] = inst
    # template checks (COVER design parameters, editable)
    if inst > d["max_instruments"] and category != "SMB":
        warnings.append(f"{inst} instruments exceed the design maximum of {d['max_instruments']} per junction box.")
    if pct is not None and pct < d["design_spare_pct"]:
        warnings.append(f"Spare terminals ({pct:.0%}) are below the design spare of {d['design_spare_pct']:.0%}.")
    zones = [z for z in iod.get("area_class", []) if z.upper().startswith("ZONE")]
    prot = row["protection"]
    if zones and prot and not prot.upper().startswith("EX"):
        errors.append(f"The area is classified {zones[0]} but the enclosure protection ({prot}) is not Ex.")
    if not zones and iod.get("area_class") and prot.upper().startswith("EX"):
        warnings.append("An Ex enclosure is selected for a safe area - please confirm.")
    if any(_s(v).upper() in ("TBA", "TBD") for v in cfg.values() if isinstance(v, str)):
        warnings.append("An input still holds TBA / TBD.")
    # what is still missing
    miss_gen = []
    if not row["category"]:
        miss_gen.append("JB CATEGORY")
    if not cap and cap_raw in (None, ""):
        miss_gen.append("TERMINAL CAPACITY / WAYS")
    if used is None and not (method == "manual" or method == "per_instrument"):
        miss_gen.append("TERMINALS USED")
    if len(iod.get("isnis", [])) > 1 and not row["isnis"]:
        miss_gen.append("IS / NIS")
    miss_sub = [label for f, label in FIELDS_SUBMISSION + (FIELDS_SUBMISSION_NON_SMB if category != "SMB" else [])
                if not row.get(f) or label in incomplete]
    status = "Error" if errors else ("Input Required" if miss_gen else "Ready")
    return {"jb_no": jb["jb_no"], "row": row, "source": src, "errors": errors, "warnings": list(dict.fromkeys(warnings)),
            "missing_generation": miss_gen, "missing_submission": miss_sub, "status": status,
            "terminals_auto": auto_used, "terminals_auto_source": auto_src}


def evaluate_all(analysis: dict, configs: dict, design: Optional[dict] = None) -> dict:
    results = [evaluate(j, configs.get(j["jb_no"]) or configs.get(j["key"]), design) for j in analysis["jbs"]]
    keys = Counter(j["key"] for j in analysis["jbs"])
    dups = [k for k, n in keys.items() if n > 1]
    summary = Counter(r["status"] for r in results)
    return {"results": results, "duplicates": dups, "summary": dict(summary),
            "ready": bool(results) and not dups and all(r["status"] == "Ready" for r in results),
            "submission_ready": bool(results) and all(not r["missing_submission"] for r in results)}


# ── 5. the output workbook ───────────────────────────────────────────────────────────────────────────────────────────
# The stored template IS the delivered layout: one sheet (JB_SCHEDULE), document header rows 1-5, title band row 6, the 22
# column headings in row 7 and pre-formatted junction box rows from row 8.
HEADER_ROW, FIRST_DATA_ROW, TITLE_ROW = 7, 8, 6
HEADINGS = ("S.NO", "UNIT / AREA NAME", "JB NO.", "JB CATEGORY", "JB DESCRIPTION", "IS / NIS", "LOCATION", "ENCLOSURE PROTECTION",
            "ENCLOSURE MATERIAL", "TERMINAL CAPACITY / WAYS", "TERMINAL TYPE", "CABLE ENTRY", "BRANCH CABLES (FROM TERMINATION)",
            "BRANCH GLAND SIZE", "MAIN CABLE NO.", "MAIN CABLE TYPE", "MAIN CABLES (FROM TERMINATION)", "MAIN CABLE GLAND SIZE",
            "SPARE ENTRIES (QTY)", "SPARE ENTRY SIZE", "TERMINALS USED", "REMARKS")
_COLS = {"unit_name": "B", "jb_no": "C", "category": "D", "jb_desc": "E", "isnis": "F", "location": "G", "protection": "H",
         "material": "I", "terminal_capacity": "J", "terminal_type": "K", "cable_entry": "L", "branch_cable_count": "M",
         "branch_gland_size": "N", "main_cable_no": "O", "main_cable_type": "P", "main_cable_count": "Q", "main_gland_size": "R",
         "spare_entries": "S", "spare_entry_size": "T", "terminals_used": "U", "remarks": "V"}
_CABLE_COLUMNS = ("O", "P", "R")      # one line per physical main cable
_LIST_COLUMNS = {"D": "category", "F": "isnis", "H": "protection", "I": "material", "K": "term_type", "L": "entry",
                 "N": "gland_size", "R": "gland_size", "T": "gland_size", "P": "cable"}
_HEADER_LABEL_COL, _HEADER_VALUE_COL = "S", "U"
_LINE_PT, _MAX_ROW_PT = 11.0, 400.0    # Excel stops at 409.5 pt


def build_workbook(template: bytes, results: list, meta: dict) -> bytes:
    """
    Fill the standard JB_SCHEDULE template: one row per junction box, nothing but this sheet, no formulas and no cover sheet.
    The main cable number, type and gland size cells hold one line per physical cable; their columns are widened so a line is
    never wrapped (which would break the line-to-line correspondence). meta: project_info (dict), document_number, revision, date.
    """
    wb = openpyxl.load_workbook(io.BytesIO(template))
    if wb.sheetnames != ["JB_SCHEDULE"]:
        raise JBError("The Junction Box Schedule template is not the expected single JB_SCHEDULE sheet.")
    ws = wb["JB_SCHEDULE"]
    if [ws.cell(HEADER_ROW, c).value for c in range(1, ws.max_column + 1)] != list(HEADINGS):
        raise JBError("The column headings of the Junction Box Schedule template are not the expected 22 headings.")
    rows = list(results)
    n = len(rows)
    if n == 0:
        raise JBError("There are no junction boxes to write.")
    last_col = len(HEADINGS)
    last_letter = get_column_letter(last_col)
    # unused template rows (new rows beyond the formatted ones copy the first data row)
    last_template = ws.max_row
    if FIRST_DATA_ROW + n <= last_template:
        ws.delete_rows(FIRST_DATA_ROW + n, last_template - (FIRST_DATA_ROW + n) + 1)
    for r in range(last_template + 1, FIRST_DATA_ROW + n):
        for c in range(1, last_col + 1):
            ws.cell(r, c)._style = copy(ws.cell(FIRST_DATA_ROW, c)._style)
    # title block - plain values (blank stays blank)
    info = meta.get("project_info") or {}
    units = meta.get("unit_names") or _unique(r["row"].get("unit_name") for r in rows)
    ws["C1"], ws["C2"], ws["C3"], ws["C4"] = (info.get("project_description") or "", info.get("client") or "",
                                              info.get("pmc") or "", info.get("contractor") or "")
    ws["C5"] = info.get("unit_no") or ", ".join(units)
    for r, value in zip((2, 3, 4), (meta.get("document_number"), meta.get("revision"), meta.get("date"))):
        ws[f"{_HEADER_VALUE_COL}{r}"].value = value or ""
    # data rows
    centre = Alignment(horizontal="center", vertical="center", wrap_text=True)
    top = Alignment(horizontal="center", vertical="top", wrap_text=True)
    widths = {c: ws.column_dimensions[c].width or 10 for c in _COLS.values()}
    for col in _CABLE_COLUMNS:                                   # a cable line must fit on one printed line
        field = next(f for f, c in _COLS.items() if c == col)
        longest = max((len(line) for r in rows for line in str(r["row"].get(field) or "").split("\n")), default=0)
        widths[col] = max(widths[col], min(longest * 1.05 + 2, 60))
        ws.column_dimensions[col].width = widths[col]
    for i, res in enumerate(rows):
        r = FIRST_DATA_ROW + i
        row = res["row"]
        values = dict(row)
        values["jb_no"] = res["jb_no"]
        values["remarks"] = None                                 # the REMARKS column stays in the template, its rows stay empty
        ws.cell(r, 1).value = i + 1
        ws.cell(r, 1).alignment = centre
        lines = 1
        multi = any("\n" in str(values.get(f) or "") for f, c in _COLS.items() if c in _CABLE_COLUMNS)
        for field, col in _COLS.items():
            v = values.get(field)
            if field == "terminals_used" and row.get("category") == "SMB":
                v = None                                         # an SMB counts ways = instruments (template example leaves it blank)
            cell = ws[f"{col}{r}"]
            cell.value = v if v not in ("", None) else None
            cell.alignment = top if multi and col in _CABLE_COLUMNS else centre
            if isinstance(v, str):
                lines = max(lines, sum(max(1, math.ceil(len(p) / max(1.0, widths[col] * 1.05))) for p in v.split("\n")))
        ws.row_dimensions[r].height = min(max(15.0, _LINE_PT * lines + 4), _MAX_ROW_PT)
    # controlled lists as in-cell drop-downs
    ws.data_validations.dataValidation = []
    for col, key in _LIST_COLUMNS.items():
        literal = ",".join(x.replace('"', '""') for x in LISTS[key])
        if len(literal) > 250:
            continue
        dv = DataValidation(type="list", formula1=f'"{literal}"', allow_blank=True, showErrorMessage=False)
        dv.add(f"{col}{FIRST_DATA_ROW}:{col}{FIRST_DATA_ROW + n - 1}")
        ws.add_data_validation(dv)
    # print setup and view
    ws.print_area = f"A1:{last_letter}{FIRST_DATA_ROW + n - 1}"
    ws.print_title_rows = f"{HEADER_ROW}:{HEADER_ROW}"
    ws.freeze_panes = f"E{FIRST_DATA_ROW}"
    wb.active = 0
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def formula_problems(data: bytes) -> list:
    """Any formula error / broken reference / defined name left in a workbook (the output must have none)."""
    wb = openpyxl.load_workbook(io.BytesIO(data))
    bad = []
    for name, dn in wb.defined_names.items():
        if "#REF!" in str(dn.attr_text):
            bad.append(f"defined name {name}")
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, str) and (re.search(r"#(REF|VALUE|NAME|DIV/0|N/A)[!?]?", v) or (v.startswith("=") and "!" in v)):
                    bad.append(f"{ws.title}!{c.coordinate}: {v[:40]}")
    return bad
