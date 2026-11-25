"""
io_list_basis.py - the IO_BASIS of the I/O List workbook, derived from the IODB (rule based, no AI / OCR).

For every kind of equipment found in the IODB one REPRESENTATIVE configuration is listed - the signals (I/O type + description) of one real loop:

    Motors            LOOP TYPE of a motor (TYPE-M1, M2 ... / 'Motor DOL' ...)   one entry per motor loop type
    Valves            LOOP TYPE of a valve (TYPE-1, TYPE-K1 ...) or a valve type with no loop type (TYPE shown as '-')
    Field instruments one entry per INSTRUMENT TYPE:  TYPE '-', EQUIPMENT = instrument type, '<instrument type> Feedback'
    Other equipment   any other LOOP TYPE whose loops carry several signals (packages, screens ...)

Representative loop: the loops of one class are compared by their complete signal configuration (I/O type + signal description with its
multiplicity, source order ignored; only case and spaces are normalised). The most frequent configuration wins and an actual loop with it is
the representative. When the loops of a class disagree the class is flagged "Review Required" (an engineer confirms or picks another real
loop - never a mixture of loops). Nothing here changes the IODB, the I/O List or the I/O Summary: this only decides what IO_BASIS shows.
"""
from __future__ import annotations

import re
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

IO_ORDER = ("DI", "DO", "AI", "AO")
_PLACEHOLDER = {"", "-", "--", "NA", "N/A", "NAN", "NONE", "NIL", "TBA", "TBD"}
_HEADERS = {
    "loop": ("LOOP NUMBER", "LOOP NO", "LOOP NO.", "LOOP"),
    "loop_type": ("LOOP TYPE",),
    "signal": ("SIGNAL DESCRIPTION", "SIGNAL DESC"),
    "io": ("SIGNAL I/O TYPE", "SIGNAL IO TYPE", "I/O TYPE", "IO TYPE", "SIGNAL TYPE"),
    "inst": ("INSTRUMENT TYPE NAME", "INSTRUMENT TYPE", "INSTRUMENT NAME"),
    "tag": ("TAG NO", "TAG NUMBER", "TAG NO.", "TAG"),
    "sub": ("SUB SYSTEM", "SUBSYSTEM"),
}
_MOTOR_TYPE = re.compile(r"^(TYPE[\s\-_]*)?M\d+[A-Z]?$")
_VALVE_TYPE = re.compile(r"^(TYPE[\s\-_]*)?K?\d+[A-Z]?$")
_VALVE_WORDS = ("VALVE", "GATE", "BUTTERFLY", "DAMPER")
_NON_HARDWIRED = ("SOFT", "COMM", "SERIAL", "MODBUS", "PROFI", "ETHERNET", "OPC")


def _norm(v: Any) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    return re.sub(r"\s+", " ", str(v).replace("\n", " ")).strip()


def _up(v: Any) -> str:
    return _norm(v).upper()


def _empty(v: Any) -> bool:
    return _up(v) in _PLACEHOLDER


def _find(df: pd.DataFrame, names) -> Optional[str]:
    cols = {_up(c): c for c in df.columns}
    for n in names:
        if n in cols:
            return cols[n]
    return None


def natural(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


@dataclass
class Config:
    sig: tuple                           # ((io, DESC), count) sorted - the comparison key
    loops: list = field(default_factory=list)
    signals: list = field(default_factory=list)       # [(io, description)] of the first loop of this configuration, source order


@dataclass
class BasisClass:
    key: str                             # stable id used by the review step ("motor|TYPE-M1")
    category: str                        # motor | valve | other | instrument
    type_label: str                      # TYPE column
    equipment: str                       # EQUIPMENT column
    equipment_default: str = ""          # the derived name (the user may rename it in the review step)
    loops: int = 0                       # loops (or, for instruments, records) found
    representative: str = ""             # loop number
    rows: list = field(default_factory=list)          # [(io, description)] grouped DI, DO, AI, AO
    status: str = "Consistent"           # Consistent | Review Required
    configs: list = field(default_factory=list)       # the available configurations (most frequent first)
    notes: list = field(default_factory=list)
    candidates: list = field(default_factory=list)    # loop numbers an engineer may choose instead


@dataclass
class BasisResult:
    classes: list = field(default_factory=list)
    issues: list = field(default_factory=list)       # {"severity", "category", "message"}
    stats: dict = field(default_factory=dict)
    error: str = ""

    def review_rows(self) -> list[dict]:
        return [{"key": c.key, "category": c.category, "type": c.type_label, "equipment": c.equipment, "loops": c.loops,
                 "representative": c.representative, "status": c.status, "candidates": c.candidates,
                 "configs": [{"count": len(k.loops), "loops": k.loops[:6], "signals": k.signals} for k in c.configs[:6]],
                 "notes": c.notes} for c in self.classes]


def _canon_type(raw: str) -> str:
    """TYPE column text: M1 -> TYPE-M1, 'TYPE M1' / 'type-m1' -> TYPE-M1, an existing TYPE-1 stays, anything else as written (upper case)."""
    t = _up(raw)
    m = re.match(r"^(?:TYPE[\s\-_]*)?(M\d+[A-Z]?|K?\d+[A-Z]?)$", t)
    return f"TYPE-{m.group(1)}" if m else t


def _group_rows(sig_list: list) -> list:
    out = []
    for io in IO_ORDER:
        out += [(io, d) for i, d in sig_list if i == io]
    return out


def _io_class(v: Any) -> str:
    t = _up(v).replace(" ", "")
    if t in IO_ORDER:
        return t
    if _up(v) in _PLACEHOLDER:
        return "NONE"
    if any(w in _up(v) for w in _NON_HARDWIRED):
        return "SOFT"
    return "UNKNOWN"


def build_basis(df: pd.DataFrame, overrides: Optional[dict] = None, names: Optional[dict] = None) -> BasisResult:
    """
    df        the IODB rows behind the I/O List (all columns).
    overrides {class key: loop number} - the representative loop an engineer chose (must be a loop of that class).
    names     {class key: EQUIPMENT text} - an engineer's own equipment wording.
    """
    res = BasisResult()
    overrides, names = overrides or {}, names or {}
    if df is None or len(df) == 0:
        res.error = "The IODB has no rows, so IO_BASIS cannot be generated."
        return res
    c = {k: _find(df, v) for k, v in _HEADERS.items()}
    need = [("loop", "LOOP NUMBER"), ("io", "SIGNAL I/O TYPE"), ("signal", "SIGNAL DESCRIPTION"), ("inst", "INSTRUMENT TYPE NAME")]
    absent = [label for k, label in need if not c[k]]
    if absent:
        res.error = "IO_BASIS needs these IODB columns, which were not found: " + ", ".join(absent) + "."
        return res

    def issue(sev, cat, msg):
        res.issues.append({"severity": sev, "category": cat, "message": msg})

    recs = []
    for i, row in enumerate(df.to_dict("records")):
        recs.append({"row": i + 2, "loop": _norm(row.get(c["loop"])), "ltype": _up(row.get(c["loop_type"])) if c["loop_type"] else "",
                     "io": _io_class(row.get(c["io"])), "io_raw": _norm(row.get(c["io"])), "desc": _norm(row.get(c["signal"])),
                     "inst": _norm(row.get(c["inst"])), "tag": _norm(row.get(c["tag"])) if c["tag"] else "",
                     "sub": _up(row.get(c["sub"])) if c["sub"] else ""})
    for r in recs:
        if r["ltype"] in _PLACEHOLDER:
            r["ltype"] = ""
        if r["loop"].upper() in _PLACEHOLDER:
            r["loop"] = ""
    loop_rows = Counter((r["ltype"], r["loop"]) for r in recs if r["loop"])

    def kind(r):
        lt, inst = r["ltype"], r["inst"].upper()
        if lt and (_MOTOR_TYPE.match(lt) or re.match(r"^MOTOR\b", lt)):
            return "motor"
        if lt and (_VALVE_TYPE.match(lt) or any(w in lt for w in _VALVE_WORDS)):
            return "valve"
        if not lt and any(w in inst for w in _VALVE_WORDS):
            return "valve"
        if not lt and r["sub"] in ("MCC", "VFD"):
            return "motor?"                                         # a motor starter with no loop type
        if lt and loop_rows.get((lt, r["loop"]), 0) > 1:
            return "other"
        return "instrument"

    hard = Counter()
    groups: "OrderedDict[tuple, list]" = OrderedDict()
    inst_recs: "OrderedDict[str, list]" = OrderedDict()
    missing = {"loop": [], "ltype": [], "io": [], "desc": [], "inst": []}
    soft, unknown, nosig = [], [], 0
    for r in recs:
        k = kind(r)
        if r["io"] == "SOFT":
            soft.append(r)
            continue
        if r["io"] == "UNKNOWN":
            unknown.append(r)
            continue
        if r["io"] == "NONE":
            nosig += 1
            continue
        hard[r["io"]] += 1
        if k == "motor?":
            missing["ltype"].append(r)
            continue
        if k == "instrument":
            if not r["inst"]:
                missing["inst"].append(r)
                continue
            inst_recs.setdefault(r["inst"].upper(), []).append(r)
            continue
        if not r["loop"]:
            missing["loop"].append(r)
            continue
        if k in ("motor", "valve", "other") and not r["desc"]:
            missing["desc"].append(r)
        gk = (k, r["ltype"], "" if r["ltype"] else r["inst"].upper())
        groups.setdefault(gk, []).append(r)

    classes: list[BasisClass] = []
    for (k, lt, valve_name), rs in groups.items():
        key = f"{k}|{lt or valve_name}"
        by_loop: "OrderedDict[str, list]" = OrderedDict()
        for r in rs:
            by_loop.setdefault(r["loop"], []).append(r)
        cfgs: "OrderedDict[tuple, Config]" = OrderedDict()
        for lp, lrs in by_loop.items():
            sig = tuple(sorted(Counter((r["io"], r["desc"].upper()) for r in lrs).items()))
            cf = cfgs.get(sig)
            if cf is None:
                cf = cfgs[sig] = Config(sig=sig, signals=[(r["io"], r["desc"]) for r in lrs])
            cf.loops.append(lp)
        ordered = sorted(cfgs.values(), key=lambda x: -len(x.loops))          # stable: ties keep source order
        top = ordered[0]
        status, notes = "Consistent", []
        if len(ordered) > 1:
            status = "Review Required"
            tie = [x for x in ordered if len(x.loops) == len(top.loops)]
            notes.append(f"{len(ordered)} different signal configurations among {len(by_loop)} loops; the most frequent ({len(top.loops)} loops) "
                         "is recommended.")
            if len(tie) > 1:
                notes.append(f"{len(tie)} configurations are equally common - none is silently treated as the approved basis.")
        rep, chosen = top.loops[0], top
        if key in overrides:
            want = str(overrides[key]).strip()
            hit = next((lp for lp in by_loop if lp.upper() == want.upper()), None)
            if hit is None:
                issue("error", "Representative loop", f"{key}: '{want}' is not a loop of this equipment class - the recommended loop is used.")
            else:
                rep = hit
                chosen = next(x for x in ordered if hit in x.loops)
                if chosen is not top:
                    notes.append(f"Representative loop {hit} chosen by the engineer.")
        sig_list = [(r["io"], r["desc"]) for r in by_loop[rep]]
        types = Counter(r["inst"] for r in rs if r["inst"])
        subs = Counter(r["sub"] for r in by_loop[rep] if r["sub"])
        if k == "motor":
            type_label = _canon_type(lt)
            default = "MOTOR STATUS" + (f" - {subs.most_common(1)[0][0]}" if subs else "")
        elif k == "valve":
            type_label = _canon_type(lt) if lt else "-"
            default = " / ".join(n for n, _ in types.most_common(3)) or (lt or valve_name)
        else:
            type_label = _canon_type(lt) if (lt and _VALVE_TYPE.match(lt) or lt and _MOTOR_TYPE.match(lt)) else "-"
            default = lt if lt and not (_VALVE_TYPE.match(lt) or _MOTOR_TYPE.match(lt)) else (types.most_common(1)[0][0] if types else lt)
        equip = names.get(key) or default
        classes.append(BasisClass(key=key, category=k, type_label=type_label, equipment=equip, equipment_default=default, loops=len(by_loop),
                                  representative=rep, rows=_group_rows(sig_list), status=status, configs=ordered, notes=notes,
                                  candidates=list(by_loop)))
        if status != "Consistent":
            issue("review", "Same Loop Type, different configurations", f"{key}: " + " ".join(notes))
        if k == "valve" and not lt:
            issue("review", "Valve without Loop Type", f"{valve_name}: no LOOP TYPE in the IODB - TYPE is shown as '-'.")

    # individual field instruments: one entry per INSTRUMENT TYPE
    for name_up, rs in inst_recs.items():
        key = f"instrument|{name_up}"
        shown = Counter(r["inst"] for r in rs).most_common(1)[0][0]
        ios = Counter(r["io"] for r in rs)
        rows, notes, status = [], [], "Consistent"
        for io in IO_ORDER:
            if io not in ios:
                continue
            if io in ("DO", "AO"):
                dd = Counter(r["desc"] for r in rs if r["io"] == io and r["desc"])
                rows.append((io, dd.most_common(1)[0][0] if dd else ""))
                status = "Review Required"
                notes.append(f"{io} signal on an instrument: it is an output, not a Feedback - the IODB description is shown; please review.")
            else:
                rows.append((io, f"{shown} Feedback"))
        if len([i for i in ios if i in IO_ORDER]) > 1:
            status = "Review Required"
            notes.append("Several I/O classifications (" + ", ".join(i for i in IO_ORDER if i in ios) + ") - all are kept; please review.")
        equip = names.get(key) or shown
        classes.append(BasisClass(key=key, category="instrument", type_label="-", equipment=equip, equipment_default=shown, loops=len(rs),
                                  representative="", rows=rows, status=status, notes=notes))
        if status != "Consistent":
            issue("review", "Same Instrument Type, different configurations" if len(ios) > 1 else "Output on a field instrument",
                  f"{shown}: " + " ".join(notes))

    order = {"motor": 0, "valve": 1, "instrument": 2, "other": 3}
    classes.sort(key=lambda x: (order[x.category], x.type_label == "-", natural(x.key)))        # a valve with a loop type before one without
    res.classes = classes

    if missing["ltype"]:
        issue("review", "Missing LOOP TYPE for motor", f"{len(missing['ltype'])} signal(s) of MCC / VFD equipment have no LOOP TYPE and are not in IO_BASIS "
              f"(e.g. {', '.join(sorted({r['tag'] or r['loop'] for r in missing['ltype']})[:5])}).")
    if missing["loop"]:
        issue("review", "Missing LOOP NUMBER", f"{len(missing['loop'])} motor / valve / equipment signal(s) have no LOOP NUMBER and are not in IO_BASIS "
              f"(e.g. {', '.join(sorted({r['tag'] for r in missing['loop'] if r['tag']})[:5])}).")
    if missing["inst"]:
        issue("review", "Missing INSTRUMENT TYPE", f"{len(missing['inst'])} signal(s) have no INSTRUMENT TYPE and are not in IO_BASIS.")
    if missing["desc"]:
        issue("review", "Missing SIGNAL DESCRIPTION", f"{len(missing['desc'])} signal(s) of multi-signal equipment have no SIGNAL DESCRIPTION.")
    if unknown:
        issue("review", "Unknown I/O classification", "Not DI / DO / AI / AO and not classified: " + ", ".join(sorted({r["io_raw"] for r in unknown})) +
              f" ({len(unknown)} signal(s)).")
    if soft:
        issue("info", "Non-hardwired signals", f"{len(soft)} communication / soft signal(s) ({', '.join(sorted({r['io_raw'] for r in soft}))}) are not hardwired "
              "I/O and are not listed in IO_BASIS.")
    if nosig:
        issue("info", "Records without a signal", f"{nosig} record(s) have no I/O type ('-') - local indicators / gauges - and are not listed.")
    seen = Counter((r["loop"], r["io"], r["desc"].upper()) for r in recs if r["loop"] and r["io"] in IO_ORDER)
    dup = sum(1 for v in seen.values() if v > 1)
    if dup:
        issue("info", "Repeated signal records", f"{dup} signal(s) appear more than once in the same loop; they are kept (distinct channels are legitimate).")

    res.stats = {"records": len(recs), "hardwired": sum(hard.values()), "classes": len(classes),
                 "review": sum(1 for x in classes if x.status != "Consistent")}
    return res
