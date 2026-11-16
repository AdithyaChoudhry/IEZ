"""
Loop Wiring engine - analysis.

    I/O Assignment rows -> group by LOOP_NAME -> LOOP TYPE / SPD / TERM -> calculated TYPICAL -> template -> signal slots
    -> FIELD CODE mapping into the DATA BLOCK -> template-specific required fields -> terminal / module / IS checks -> trace

Severity:  ERROR  = the loop is not generated;   REVIEW = generated, engineering review needed;   PASS = all checks passed.
Nothing is ever invented: a missing value stays blank and is reported.
"""
from __future__ import annotations

import io
import re
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import openpyxl

from .registry import Registry, Template, DataField, requirement, library_error, SPD_VALUES, TERM_VALUES
from .source import SourceData, SourceRow

LOOP_LEVEL_CODES = ("LOOP_SERVICE", "DOC_NO", "DWG_REV", "LOOP_TYPE", "SPD_ARR", "TERM_ARR", "TYPICAL")
IO_TYPES = ("AI", "AO", "DI", "DO")
ALLOWED_IO = {"AI-2W": {"AI"}, "AI-4W": {"AI"}, "MOTOR-DOL": {"DI", "DO", "AI"}, "MOTOR-VFD": {"DI", "DO", "AI", "AO"},
              "PNEU-VALVE": {"DI", "DO"}, "MOV": {"DI", "DO"}, "SWITCH": {"DI"}}
WIRE_EXPECT = {"AI-2W": "2 WIRE", "AI-4W": "4 WIRE"}
# DATA BLOCK field whose source FIELD CODE has a different name (explicit contract, still code -> code)
ALIAS = {"REV": "DWG_REV", "INTERFACE_TAG": "ISO_TAG", "INTERFACE_MODEL": "ISO_MODEL", "INTERFACE_T1": "ISO_IN1", "INTERFACE_T2": "ISO_OUT1"}
# source-code groups that stand or fall with one anchor DATA BLOCK field (used to report data the selected template does not use)
GROUPS = [("FSPD_TAG", ("FSPD_",), "FIELD SPD"), ("SPD_TAG", ("SPD_",), "PANEL SPD"), ("MARSH_CAB", ("MARSH_",), "MARSHALLING CABINET"),
          ("TB_STRIP", ("TB_",), "MARSHALLING TB"), ("SYS_CABLE", ("SYS_CABLE", "SYS_CORES"), "SYSTEM CABLE"), ("RLY_TAG", ("RLY_",), "RELAY"),
          ("JB_TAG", ("JB_", "MC_"), "JUNCTION BOX / MULTICORE"), ("PWR_CABLE", ("PWR_", "DB_", "DEV_L", "DEV_N"), "POWER (4-WIRE) PATH")]
# informational source codes that classify the signal (consumed by the engine, not by the DATA BLOCK)
CLASSIFIERS = {"LOOP_NAME", "LOOP_SERVICE", "DOC_NO", "DWG_REV", "LOOP_TYPE", "SPD_ARR", "TERM_ARR", "TYPICAL", "STATUS", "ISNIS", "WIRE", "SIGTYPE", "REV"}
INTERFACE_LOCATION = {"M": "MRC", "D": "SYSTEM CABINET"}       # template INDEX assumptions 1 and 2
TB_NO_MATRIX = {"SNO"}


def msg(sev: str, code: str, detail: str = "") -> str:
    return f"{sev} — {code}" + (f": {detail}" if detail else "")


@dataclass
class Issue:
    severity: str
    code: str
    detail: str
    loop: str = ""
    rows: list[int] = field(default_factory=list)
    field: str = ""
    sig: str = ""

    @property
    def text(self) -> str:
        return msg(self.severity, self.code, self.detail)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["text"] = self.text
        return d


@dataclass
class SignalResult:
    sig: str
    slot_row: int
    source_row: int
    tag: str
    io_type: str
    sig_desc: str
    data_block: dict[str, Any]
    mapping: list[dict]
    trace: dict
    unused: list[dict]
    status: str = "PASS"


@dataclass
class LoopResult:
    name: str
    rows: list[int]
    loop_type: str = ""
    spd: str = ""
    term: str = ""
    typical: str = ""
    manual_typical: str = ""
    template: Optional[str] = None
    status: str = "PASS"
    issues: list[Issue] = field(default_factory=list)
    signals: list[SignalResult] = field(default_factory=list)
    loop_fields: dict[str, Any] = field(default_factory=dict)
    attrs: dict[str, str] = field(default_factory=dict)
    empty_slots: list[str] = field(default_factory=list)
    report: dict = field(default_factory=dict)

    def add(self, sev: str, code: str, detail: str = "", rows: Optional[list[int]] = None, fld: str = "", sig: str = "") -> Issue:
        i = Issue(sev, code, detail, self.name, rows or [], fld, sig)
        if not any((x.code, x.detail, tuple(x.rows), x.field, x.sig) == (i.code, i.detail, tuple(i.rows), i.field, i.sig) for x in self.issues):
            self.issues.append(i)
        return i

    def finish(self) -> None:
        self.status = "ERROR" if any(i.severity == "ERROR" for i in self.issues) else ("REVIEW" if any(i.severity == "REVIEW" for i in self.issues) else "PASS")
        sev = {"ERROR": 2, "REVIEW": 1, "PASS": 0}
        for s in self.signals:
            worst = max([sev[i.severity] for i in self.issues if i.sig == s.sig] + [0])
            s.status = {2: "ERROR", 1: "REVIEW", 0: "PASS"}[worst]

    @property
    def generate(self) -> bool:
        return self.status != "ERROR" and self.template is not None

    def summary(self) -> dict:
        return {"loop": self.name, "loop_type": self.loop_type, "spd": self.spd, "term": self.term, "typical": self.typical, "manual_typical": self.manual_typical,
                "template": self.template, "signals": len(self.signals), "source_rows": len(self.rows), "status": self.status,
                "errors": sum(1 for i in self.issues if i.severity == "ERROR"), "reviews": sum(1 for i in self.issues if i.severity == "REVIEW"), **self.attrs}


@dataclass
class Analysis:
    source: SourceData
    registry: Registry
    loops: list[LoopResult]
    global_issues: list[Issue]
    spares: int
    matrix: dict

    def counts(self) -> dict:
        c = {"PASS": 0, "REVIEW": 0, "ERROR": 0}
        for l in self.loops:
            c[l.status] += 1
        return c


# ---------------------------------------------------------------------------------------------------------------------
_MATRIX_CACHE: dict[bytes, dict] = {}


def read_matrix(io_master: Optional[bytes]) -> dict:
    if io_master is not None and io_master in _MATRIX_CACHE:
        return _MATRIX_CACHE[io_master]
    out = _read_matrix(io_master)
    if io_master is not None and out:
        _MATRIX_CACHE[io_master] = out
    return out


def _read_matrix(io_master: Optional[bytes]) -> dict:
    """TYPICAL_MATRIX of the I/O Assignment master: FIELD CODE -> {loop type: R/C/O/-}."""
    out: dict[str, dict[str, str]] = {}
    if not io_master:
        return out
    try:
        wb = openpyxl.load_workbook(io.BytesIO(io_master), read_only=True, data_only=True)
        ws = wb["TYPICAL_MATRIX"]
        rows = list(ws.iter_rows(min_row=1, max_row=140, values_only=True))
        hdr_i = next(i for i, r in enumerate(rows) if r and r[1] == "FIELD CODE")
        hdr = rows[hdr_i]
        types = {j: str(v).strip() for j, v in enumerate(hdr) if j >= 3 and v and str(v).strip() not in ("CONDITION",)}
        for r in rows[hdr_i + 1:]:
            if not r or not r[1] or not re.fullmatch(r"[A-Z][A-Z0-9_]+", str(r[1])):
                if r and r[0] and str(r[0]).startswith("42 LOOP TYPICALS"):
                    break
                continue
            out[str(r[1])] = {types[j]: str(r[j]).strip() for j in types if j < len(r) and r[j] is not None} | {"_condition": str(r[10] or "") if len(r) > 10 else ""}
    except Exception:
        return {}
    return out


def _txt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


def inst_type(tag: str) -> str:
    for tok in re.split(r"[-\s]+", tag.upper())[1:]:
        if re.fullmatch(r"[A-Z]{1,4}", tok):
            return tok
    return ""


def module_capacity(module_type: str, io: str, density: dict[str, int]) -> Optional[int]:
    m = re.match(r"\s*(AI|AO|DI|DO)\s*(\d+)", module_type.upper())
    if m:
        return int(m.group(2))
    return density.get(io)


def field_state(df: DataField, ctx: dict) -> str:
    r = requirement(df.required, ctx)
    if df.required.strip().lower() == "no":
        return "optional"
    if r is None:
        return "unknown"
    return "required" if r else "na"


# ---------------------------------------------------------------------------------------------------------------------
def analyze(src: SourceData, reg: Registry, matrix: Optional[dict] = None, density: Optional[dict] = None) -> Analysis:
    matrix = matrix or {}
    density = density or {"AI": 16, "AO": 8, "DI": 32, "DO": 16}
    groups: dict[str, list[SourceRow]] = {}
    order: list[str] = []
    orphans: list[SourceRow] = []
    for r in src.rows:
        n = r.text("LOOP_NAME")
        if not n:
            orphans.append(r)
            continue
        if n not in groups:
            groups[n] = []
            order.append(n)
        groups[n].append(r)

    loops = [_analyze_loop(n, groups[n], reg, matrix) for n in order]
    gissues: list[Issue] = []
    if orphans:
        gissues.append(Issue("ERROR", "LOOP NAME MISSING", "I/O rows without a LOOP_NAME cannot be grouped into a loop: rows " + ", ".join(str(o.row) for o in orphans[:30]), "", [o.row for o in orphans]))
    lerr = library_error(reg)
    if lerr:
        gissues.append(Issue("ERROR", "TEMPLATE LIBRARY INCOMPLETE", lerr.replace("TEMPLATE LIBRARY INCOMPLETE - ", "")))

    _system_checks(loops, groups, density)
    _terminal_checks(loops, groups)
    for l in loops:
        _trace_loop(l, groups[l.name], reg)
        l.finish()
        l.report = _mapping_report(l, reg)
    return Analysis(src, reg, loops, gissues, len(src.spare_rows), matrix)


# ---------------------------------------------------------------------------------------------------------------------
def _analyze_loop(name: str, rows: list[SourceRow], reg: Registry, matrix: dict) -> LoopResult:
    L = LoopResult(name, [r.row for r in rows])
    first = rows[0]
    L.attrs = {"area": first.text("DEV_AREA"), "system": first.text("SYSTEM"), "cabinet": first.text("SYS_CAB"), "instrument": inst_type(first.text("TAG")),
               "service": first.text("LOOP_SERVICE"), "doc_no": first.text("DOC_NO"), "rev": first.text("DWG_REV")}
    for r in rows:
        if not r.text("STATUS"):
            L.add("REVIEW", "STATUS BLANK", f"row {r.row}: STATUS is blank; the row is treated as USED", [r.row], "STATUS")

    # ---- loop-level consistency ------------------------------------------------------------------------------------
    vals: dict[str, set[str]] = {}
    conflict = False
    for code in LOOP_LEVEL_CODES:
        norm = (lambda v: v.upper()) if code in ("LOOP_TYPE", "SPD_ARR", "TERM_ARR", "TYPICAL") else (lambda v: v)
        by: dict[str, list[int]] = defaultdict(list)
        for r in rows:
            v = r.text(code)
            if v:
                by[norm(v)].append(r.row)
        vals[code] = set(by)
        if len(by) > 1:
            conflict = True
            L.add("ERROR", "LOOP CONFIGURATION CONFLICT",
                  f"same LOOP_NAME {name} has conflicting {code}: " + "; ".join(f"{v} (rows {', '.join(map(str, rs))})" for v, rs in by.items()) +
                  (" - same LOOP_NAME contains conflicting loop typical configuration." if code in ("LOOP_TYPE", "SPD_ARR", "TERM_ARR", "TYPICAL") else ""), [x for rs in by.values() for x in rs], code)
        elif code != "TYPICAL":
            blank = [r.row for r in rows if not r.text(code)]
            if blank and by:
                L.add("ERROR", "MISSING REQUIRED FIELD", f"{code} is blank in rows {', '.join(map(str, blank))} but filled in the other rows of the loop", blank, code)
            elif blank and not by:
                L.add("ERROR", "MISSING REQUIRED FIELD", f"{code} is blank for the whole loop", blank, code)
    L.loop_fields = {"LOOP_NAME": name, "LOOP_SERVICE": first.text("LOOP_SERVICE"), "DOC_NO": first.text("DOC_NO"), "REV": first.text("DWG_REV")}
    if conflict:
        L.finish()
        return L

    lt = next(iter(vals["LOOP_TYPE"]), "")
    spd = next(iter(vals["SPD_ARR"]), "")
    term = next(iter(vals["TERM_ARR"]), "")
    L.loop_type, L.spd, L.term = lt, spd, term
    L.manual_typical = next(iter(vals["TYPICAL"]), "")
    known = dict(reg.loop_types)
    bad = False
    if lt and lt not in known:
        L.add("ERROR", "INVALID LOOP TYPE", f"'{lt}' is not one of {', '.join(known)}", L.rows, "LOOP_TYPE"); bad = True
    if spd and spd not in SPD_VALUES:
        L.add("ERROR", "INVALID SPD ARRANGEMENT", f"'{spd}' - allowed values are A (field + panel SPD), B (panel SPD only), C (no SPD)", L.rows, "SPD_ARR"); bad = True
    if term and term not in TERM_VALUES:
        L.add("ERROR", "INVALID TERMINATION ARRANGEMENT", f"'{term}' - allowed values are M (with marshalling cabinet) and D (without marshalling cabinet / direct system termination)", L.rows, "TERM_ARR"); bad = True
    for code, v in (("LOOP_TYPE", lt), ("SPD_ARR", spd), ("TERM_ARR", term)):
        if not v:
            bad = True
    if bad:
        L.finish()
        return L

    # ---- calculate the typical ------------------------------------------------------------------------------------
    L.typical = reg.typical_code(lt, spd, term) or ""
    if L.manual_typical and L.manual_typical != L.typical:
        L.add("ERROR", "LOOP TYPICAL MISMATCH", f"TYPICAL '{L.manual_typical}' was entered, but LOOP_TYPE {lt} + SPD_ARR {spd} + TERM_ARR {term} calculates {L.typical}; the calculated typical is authoritative", L.rows, "TYPICAL")
    tpl = reg.templates.get(L.typical)
    if tpl is None:
        L.add("ERROR", "TEMPLATE NOT FOUND", f"no approved template for typical {L.typical}" + (" (" + library_error(reg) + ")" if library_error(reg) else ""), L.rows)
    else:
        L.template = tpl.sheet_name

    # ---- row-level checks -----------------------------------------------------------------------------------------
    for r in rows:
        io = r.upper("IO_TYPE")
        if io not in IO_TYPES:
            L.add("ERROR", "IO TYPE NOT COMPATIBLE WITH LOOP TYPE", f"row {r.row}: IO_TYPE '{io or 'blank'}' is not AI / AO / DI / DO", [r.row], "IO_TYPE")
        elif io not in ALLOWED_IO[lt]:
            L.add("ERROR", "IO TYPE NOT COMPATIBLE WITH LOOP TYPE", f"row {r.row} ({r.text('TAG')}): {io} is not allowed for {lt} (allowed: {' / '.join(sorted(ALLOWED_IO[lt]))})", [r.row], "IO_TYPE")
        exp = WIRE_EXPECT.get(lt)
        w = r.upper("WIRE")
        if exp and w and w != exp:
            L.add("ERROR", "WIRE TYPE / LOOP TYPE MISMATCH", f"row {r.row} ({r.text('TAG')}): WIRE '{w}' but {lt} expects {exp}", [r.row], "WIRE")
        isn = r.upper("ISNIS")
        if isn and isn not in ("IS", "NIS"):
            L.add("ERROR", "MISSING REQUIRED FIELD", f"row {r.row}: ISNIS '{isn}' must be IS or NIS", [r.row], "ISNIS")
        if not r.text("TAG"):
            L.add("ERROR", "MISSING REQUIRED FIELD", f"row {r.row}: TAG is blank", [r.row], "TAG")

    if tpl is None:
        L.finish()
        return L

    # ---- signal slots (template-specific) -------------------------------------------------------------------------
    pool = list(rows)
    assigned: list[tuple[Any, SourceRow]] = []
    for slot in tpl.slots:
        pick = next((r for r in pool if r.upper("IO_TYPE") == slot.io_type), None)
        if pick is not None:
            pool.remove(pick)
            assigned.append((slot, pick))
        else:
            L.empty_slots.append(slot.sig)
            L.add("REVIEW", "TYPICAL SIGNAL NOT PRESENT", f"{slot.sig} ({slot.io_type} - {slot.description or 'typical signal'}) of typical {tpl.typical} has no I/O row in this loop; its drawing block stays blank", [], "", slot.sig)
    for r in pool:
        L.add("ERROR", "SIGNAL HAS NO SLOT IN TYPICAL", f"row {r.row} ({r.text('TAG')}, {r.upper('IO_TYPE')}): typical {tpl.typical} has {tpl.max_signals} signal blocks ({', '.join(s.io_type for s in tpl.slots)}) and none is free for this signal", [r.row], "IO_TYPE")

    for slot, r in assigned:
        _map_signal(L, tpl, slot, r, reg, matrix)
    return L


def _ctx(L: LoopResult, io: str) -> dict:
    return {"loop_type": L.loop_type, "spd": L.spd, "term": L.term, "io_type": io}


def _map_signal(L: LoopResult, tpl: Template, slot, r: SourceRow, reg: Registry, matrix: dict) -> None:
    io = r.upper("IO_TYPE")
    ctx = _ctx(L, io)
    db: dict[str, Any] = {}
    mapping: list[dict] = []
    consumed: set[str] = set()
    missing: list[str] = []
    for df in reg.data_fields:
        col = tpl.columns.get(df.field, df.column)
        cell = f"{col}{slot.row}"
        if df.field == "SIG":
            db["SIG"] = slot.sig
            mapping.append({"field": "SIG", "source": "(auto)", "value": slot.sig, "destination": f"SIG · {cell}", "state": "DERIVED", "note": "signal number generated from the typical's signal block"})
            continue
        if df.field == "INTERFACE_TYPE":
            has = bool(r.text("ISO_TAG"))
            v = "OTHER" if has else "NONE"
            db[df.field] = v
            mapping.append({"field": df.field, "source": "ISO_TAG" if has else "(none)", "value": v, "destination": f"{df.field} · {cell}", "state": "DERIVED",
                            "note": "isolator tag present - type not stated in the I/O Assignment" if has else "no isolator / barrier: nothing drawn"})
            continue
        if df.field == "INTERFACE_LOCATION":
            has = bool(r.text("ISO_TAG"))
            v = INTERFACE_LOCATION.get(L.term) if has else None
            db[df.field] = v
            mapping.append({"field": df.field, "source": "TERM_ARR" if has else "(none)", "value": v, "destination": f"{df.field} · {cell}", "state": "DERIVED" if has else "BLANK",
                            "note": "marshalling cabinet (M) / system cabinet (D) per the template assumptions" if has else ""})
            continue
        code = ALIAS.get(df.field, df.field)
        state = field_state(df, ctx)
        val = r.get(code)
        if df.field == "REV":
            val = r.get("DWG_REV")
        if state == "na":
            db[df.field] = None
            mapping.append({"field": df.field, "source": code, "value": None, "destination": f"{df.field} · {cell}", "state": "NOT APPLICABLE",
                            "note": f"not used by typical {tpl.typical}" + (" - source value present and left unmapped" if val is not None else "")})
            continue
        db[df.field] = val
        consumed.add(code)
        st = "MAPPED" if val is not None else "BLANK"
        mapping.append({"field": df.field, "source": code, "value": val, "destination": f"{df.field} · {cell}", "state": st,
                        "note": ("required" if state == "required" else "optional" if state == "optional" else "")})
        if val is None and state in ("required", "unknown"):
            missing.append(df.field)
            L.add("ERROR", "MISSING REQUIRED FIELD", f"{L.name} {slot.sig} ({r.text('TAG')}, row {r.row}): {code} is blank - required by typical {tpl.typical}", [r.row], code, slot.sig)

    # ---- source data the selected template does not use ---------------------------------------------------------
    unused: list[dict] = []
    for code, v in r.values.items():
        if code in consumed or code in CLASSIFIERS or code in ("SNO",):
            continue
        unused.append({"code": code, "value": v, "reason": ""})
    ctx_loop = ctx
    by_name = reg.field_by_name()
    for anchor, prefixes, label in GROUPS:
        df = by_name.get(anchor)
        if df is None:
            continue
        if field_state(df, ctx_loop) != "na":
            continue
        present = [u for u in unused if u["code"].startswith(prefixes)]
        if not present:
            continue
        for u in present:
            u["reason"] = f"{label} data not used by typical {tpl.typical}"
        if anchor in ("FSPD_TAG", "SPD_TAG") and L.spd == "C":
            L.add("REVIEW", "SPD DATA PRESENT FOR NO-SPD TEMPLATE", f"{L.name} {slot.sig} ({r.text('TAG')}): {', '.join(u['code'] for u in present)} filled although SPD_ARR = C ({tpl.typical}) - data kept in the source, not drawn", [r.row], present[0]["code"], slot.sig)
        elif anchor == "FSPD_TAG":
            L.add("REVIEW", "FIELD SPD DATA PRESENT FOR PANEL-ONLY SPD", f"{L.name} {slot.sig} ({r.text('TAG')}): field SPD data filled although SPD_ARR = {L.spd} ({tpl.typical}) has no field-end SPD", [r.row], present[0]["code"], slot.sig)
        else:
            L.add("REVIEW", "SOURCE DATA NOT USED BY TEMPLATE", f"{L.name} {slot.sig} ({r.text('TAG')}): {label} data ({', '.join(u['code'] for u in present)}) is filled but typical {tpl.typical} has no such element", [r.row], present[0]["code"], slot.sig)
    # IS / NIS
    iso = [c for c in ("ISO_TAG", "ISO_MODEL", "ISO_IN1", "ISO_IN2", "ISO_OUT1", "ISO_OUT2")]
    if r.upper("ISNIS") == "IS":
        lack = [c for c in iso if not r.text(c)]
        if lack:
            L.add("ERROR", "IS LOOP INTERFACE DATA INCOMPLETE", f"{L.name} {slot.sig} ({r.text('TAG')}, row {r.row}): IS signal without {', '.join(lack)}", [r.row], lack[0], slot.sig)
    else:
        present = [u for u in unused if u["code"].startswith("ISO_")]
        if present:
            for u in present:
                u["reason"] = "isolator data on a NIS signal"
            L.add("REVIEW", "SOURCE DATA NOT USED BY TEMPLATE", f"{L.name} {slot.sig} ({r.text('TAG')}): isolator / barrier data on a NIS signal ({', '.join(u['code'] for u in present)})", [r.row], present[0]["code"], slot.sig)
    for u in unused:
        if not u["reason"]:
            u["reason"] = "not part of the DATA BLOCK (kept in the I/O Assignment)" if not u["code"].startswith("ISO_") else "isolator detail (DATA BLOCK carries tag / model / terminals only)"
    # standard fields the I/O Assignment marks required for this loop type (not drawn, so REVIEW only)
    drawn = {ALIAS.get(f.field, f.field) for f in reg.data_fields}
    std = []
    for code, cols in matrix.items():
        if code in drawn or code in CLASSIFIERS or code in ("SNO",):
            continue
        if cols.get(L.loop_type) == "R" and r.get(code) is None and not code.startswith(("FSPD_", "SPD_")):
            cond = cols.get("_condition", "")
            if "Analog" in cond and io not in ("AI", "AO"):
                continue
            std.append(code)
    if std:
        L.add("REVIEW", "STANDARD FIELD BLANK", f"{L.name} {slot.sig} ({r.text('TAG')}, row {r.row}): not drawn but required by the I/O Assignment standard for {L.loop_type}: {', '.join(std)}", [r.row], std[0], slot.sig)

    L.signals.append(SignalResult(slot.sig, slot.row, r.row, r.text("TAG"), io, r.text("SIG_DESC"), db, mapping, {}, unused))


# ---------------------------------------------------------------------------------------------------------------------
def _sysrows(loops, groups):
    for L in loops:
        if L.loop_type and L.signals is not None:
            for r in groups[L.name]:
                yield L, r


def _system_checks(loops: list[LoopResult], groups: dict, density: dict) -> None:
    """Module / channel / slot / rack consistency across ALL loops (a module is shared between loops)."""
    chan: dict[str, list[tuple[LoopResult, SourceRow]]] = defaultdict(list)
    slotmap: dict[tuple, dict[tuple, list]] = defaultdict(lambda: defaultdict(list))
    tagmap: dict[tuple, dict[tuple, list]] = defaultdict(lambda: defaultdict(list))
    for L in loops:
        for r in groups[L.name]:
            io = r.upper("IO_TYPE")
            cab, crate, slot, mtag, mtype, ch = r.text("SYS_CAB"), r.text("CRATE"), r.text("SLOT"), r.text("MODULE_TAG"), r.text("MODULE_TYPE"), r.text("CHANNEL")
            sig = ""
            s = next((x for x in L.signals if x.source_row == r.row), None)
            sig = s.sig if s else ""
            m = re.match(r"\s*(AI|AO|DI|DO)\b", mtype.upper())
            if io in IO_TYPES and m and m.group(1) != io:
                L.add("ERROR", "SYSTEM I/O ASSIGNMENT INVALID", f"row {r.row} ({r.text('TAG')}): {io} signal on a {mtype} module", [r.row], "MODULE_TYPE", sig)
            mt = re.match(r"(AI|AO|DI|DO)", mtag.upper())
            if io in IO_TYPES and mt and mt.group(1) != io:
                L.add("ERROR", "SYSTEM I/O ASSIGNMENT INVALID", f"row {r.row} ({r.text('TAG')}): {io} signal on module {mtag}", [r.row], "MODULE_TAG", sig)
            if ch:
                if not re.fullmatch(r"\d+", ch) or int(ch) < 1:
                    L.add("ERROR", "SYSTEM I/O ASSIGNMENT INVALID", f"row {r.row}: CHANNEL '{ch}' is not a positive channel number", [r.row], "CHANNEL", sig)
                else:
                    cap = module_capacity(mtype, io, density)
                    if cap and int(ch) > cap:
                        L.add("ERROR", "SYSTEM I/O ASSIGNMENT INVALID", f"row {r.row} ({r.text('TAG')}): channel {ch} exceeds the {cap} channels of module {mtag or mtype}", [r.row], "CHANNEL", sig)
            if cab and crate and slot and ch:
                chan[f"{cab}|{crate}|{slot}|{ch}"].append((L, r))
            if cab and crate and slot and mtag:
                slotmap[(cab, crate, slot)][(mtag, mtype)].append((L, r))
                tagmap[(cab, mtag)][(crate, slot)].append((L, r))
    for key, lst in chan.items():
        if len(lst) > 1:
            cab, crate, slot, ch = key.split("|")
            for L, r in lst:
                L.add("ERROR", "SYSTEM I/O ASSIGNMENT INVALID", f"duplicate channel: {cab} rack {crate} slot {slot} channel {ch} is assigned to {', '.join(x[1].text('TAG') + ' (row ' + str(x[1].row) + ')' for x in lst)}", [x[1].row for x in lst], "CHANNEL")
    for key, d in slotmap.items():
        if len(d) > 1:
            for lst in d.values():
                for L, r in lst:
                    L.add("ERROR", "SYSTEM I/O ASSIGNMENT INVALID", f"{key[0]} rack {key[1]} slot {key[2]} holds more than one module ({', '.join(m[0] + ' ' + m[1] for m in d)})", [r.row], "SLOT")
    for key, d in tagmap.items():
        if len(d) > 1:
            for lst in d.values():
                for L, r in lst:
                    L.add("ERROR", "SYSTEM I/O ASSIGNMENT INVALID", f"module {key[1]} in {key[0]} is placed in more than one rack / slot ({', '.join('rack ' + a + ' slot ' + b for a, b in d)})", [r.row], "SLOT")


def _terminal_checks(loops: list[LoopResult], groups: dict) -> None:
    seen: dict[tuple, list[tuple[LoopResult, SourceRow, str]]] = defaultdict(list)

    def reg_key(L, r, family, key, label):
        seen[(family,) + key].append((L, r, label))

    for L in loops:
        for r in groups[L.name]:
            if r.is_spare:
                continue
            cab = r.text("MARSH_CAB") or r.text("SYS_CAB")
            for fam, strip, t1, t2, owner in (("JB", "JB_TB", "JB_T1", "JB_T2", r.text("JB_TAG")), ("TS", "TS_STRIP", "TS_T1", "TS_T2", cab),
                                              ("TB", "TB_STRIP", "TB_T1", "TB_T2", r.text("MARSH_CAB")), ("DEV", "DEV_TB", "DEV_T1", "DEV_T2", L.name + "|" + r.text("FIELD_CABLE"))):
                a, b = r.text(t1), r.text(t2)
                if fam in ("JB", "TS", "TB") and not owner and fam != "TS":
                    continue
                if a and b and a == b:
                    L.add("ERROR", "DUPLICATE PHYSICAL TERMINATION", f"row {r.row} ({r.text('TAG')}): {t1} and {t2} are both '{a}' on {fam} strip {r.text(strip)}", [r.row], t1)
                for t in (a, b):
                    if t and (r.text(strip) or fam == "DEV") and owner:
                        reg_key(L, r, fam, (owner, r.text(strip), t), f"{fam} {owner} {r.text(strip)} terminal {t}")
            if r.text("SPD_TAG") and r.text("SPD_POS"):
                reg_key(L, r, "SPD", (cab, r.text("SPD_TAG"), r.text("SPD_POS")), f"SPD {r.text('SPD_TAG')} position {r.text('SPD_POS')}")
            if r.text("FSPD_TAG"):
                reg_key(L, r, "FSPD", (r.text("FIELD_CABLE"), r.text("FSPD_TAG")), f"field SPD {r.text('FSPD_TAG')}")
            if r.text("RLY_TAG"):
                reg_key(L, r, "RLY", (cab, r.text("RLY_TAG")), f"relay {r.text('RLY_TAG')}")
            if r.text("IE_BAR") and r.text("IE_TERM"):
                reg_key(L, r, "IE", (cab, r.text("IE_BAR"), r.text("IE_TERM")), f"IE bar {r.text('IE_BAR')} terminal {r.text('IE_TERM')}")
    for key, lst in seen.items():
        rows = {id(r): (L, r, lab) for L, r, lab in lst}
        if len(rows) > 1:
            lab = lst[0][2]
            for L, r, _ in rows.values():
                L.add("ERROR", "DUPLICATE PHYSICAL TERMINATION", f"{lab} is used by {', '.join(x[1].text('TAG') + ' (row ' + str(x[1].row) + ')' for x in rows.values())}", [x[1].row for x in rows.values()], "")


# ---------------------------------------------------------------------------------------------------------------------
def _node(name: str, ident: Any, terms: dict[str, Any], required: bool, side: str, cond_note: str = "") -> dict:
    present = bool(_txt(ident))
    incomplete = [k for k, v in terms.items() if not _txt(v)] if present else []
    return {"node": name, "id": _txt(ident), "terminals": {k: _txt(v) for k, v in terms.items()}, "required": required, "present": present,
            "broken": (required and not present) or bool(incomplete and required), "missing": ([name] if required and not present else []) + incomplete, "side": side, "note": cond_note}


def _trace_loop(L: LoopResult, rows: list[SourceRow], reg: Registry) -> None:
    if L.template is None:
        return
    by_row = {r.row: r for r in rows}
    tpl = reg.templates[L.typical]
    for s in L.signals:
        r = by_row[s.source_row]
        io = s.io_type
        d = lambda f: _txt(s.data_block.get(f))
        has_jb = L.loop_type not in ("MOTOR-DOL", "MOTOR-VFD")
        spd_field, spd_panel = L.spd == "A", L.spd in ("A", "B")
        relay = io == "DO" and L.loop_type in ("MOTOR-DOL", "MOTOR-VFD", "MOV")
        nodes = [_node("DEVICE", s.tag, {"DEV_TB": d("DEV_TB"), "DEV_T1": d("DEV_T1"), "DEV_T2": d("DEV_T2")}, True, "field")]
        if spd_field:
            nodes.append(_node("FIELD SPD", d("FSPD_TAG"), {}, True, "field"))
        nodes.append(_node("FIELD CABLE", d("FIELD_CABLE"), {"FIELD_PAIR": d("FIELD_PAIR")}, True, "field"))
        if has_jb:
            nodes.append(_node("JUNCTION BOX", d("JB_TAG"), {"JB_TB": d("JB_TB"), "JB_T1": d("JB_T1"), "JB_T2": d("JB_T2")}, True, "field"))
            nodes.append(_node("MAIN CABLE", d("MC_CABLE"), {"MC_PAIR": d("MC_PAIR")}, True, "field"))
        if L.term == "M":
            nodes.append(_node("MARSHALLING CABINET", d("MARSH_CAB"), {}, True, "control"))
        nodes.append(_node("TS", d("TS_STRIP"), {"TS_T1": d("TS_T1"), "TS_T2": d("TS_T2")}, True, "control"))
        if spd_panel:
            nodes.append(_node("PANEL SPD", d("SPD_TAG"), {"SPD_POS": d("SPD_POS")}, True, "control"))
        if relay:
            nodes.append(_node("RELAY", d("RLY_TAG"), {}, True, "control"))
        if r.upper("ISNIS") == "IS":
            nodes.append(_node("ISOLATOR / BARRIER", r.text("ISO_TAG"), {"ISO_IN1": r.text("ISO_IN1"), "ISO_OUT1": r.text("ISO_OUT1")}, True, "control"))
        if L.term == "M":
            nodes.append(_node("TB", d("TB_STRIP"), {"TB_T1": d("TB_T1"), "TB_T2": d("TB_T2")}, True, "control"))
            nodes.append(_node("SYSTEM CABLE", d("SYS_CABLE"), {"SYS_CORES": d("SYS_CORES")}, True, "control"))
        nodes.append(_node("SYSTEM CABINET", d("SYS_CAB"), {}, True, "control"))
        nodes.append(_node("MODULE", d("MODULE_TAG"), {"MODULE_TYPE": d("MODULE_TYPE"), "SLOT": d("SLOT"), "CRATE": d("CRATE")}, True, "control"))
        nodes.append(_node("CHANNEL", d("CHANNEL"), {}, True, "control"))
        power = []
        if L.loop_type == "AI-4W":
            power = [_node("DISTRIBUTION BOARD", d("DB_TAG"), {"DB_CCT": d("DB_CCT"), "DB_T1": d("DB_T1"), "DB_T2": d("DB_T2")}, True, "field"),
                     _node("POWER CABLE", d("PWR_CABLE"), {"PWR_CORES": d("PWR_CORES")}, True, "field")]
        cond = [{"role": "Signal + / contact 1", "path": [r.text(c) for c in ("DEV_T1", "FSPD_IN1", "FSPD_OUT1", "JB_T1", "TS_T1", "SPD_IN1", "SPD_OUT1", "TB_T1") if r.text(c)]},
                {"role": "Signal - / contact 2", "path": [r.text(c) for c in ("DEV_T2", "FSPD_IN2", "FSPD_OUT2", "JB_T2", "TS_T2", "SPD_IN2", "SPD_OUT2", "TB_T2") if r.text(c)]}]
        if r.text("JB_SH") or r.text("TS_SH") or r.text("IE_BAR"):
            cond.append({"role": "Shield (S) → IE bar", "path": [x for x in (r.text("JB_SH"), r.text("TS_SH"), (r.text("IE_BAR") + " " + r.text("IE_TERM")).strip()) if x]})
        if r.text("JB_OS"):
            cond.append({"role": "Overall shield (OS)", "path": [r.text("JB_OS")]})
        if L.loop_type == "AI-4W":
            cond.append({"role": "Power L", "path": [x for x in (r.text("DEV_L"), r.text("DB_T1")) if x]})
            cond.append({"role": "Power N", "path": [x for x in (r.text("DEV_N"), r.text("DB_T2")) if x]})
            if r.text("DEV_PE"):
                cond.append({"role": "PE", "path": [r.text("DEV_PE")]})
        if io == "DO":
            cond[0]["role"], cond[1]["role"] = "DO command +", "DO command -"
        elif io == "AO":
            cond[0]["role"], cond[1]["role"] = "AO +", "AO -"
        elif io == "DI":
            cond[0]["role"], cond[1]["role"] = "DI contact 1", "DI contact 2"
        broken = [m for n in nodes + power if n["broken"] for m in n["missing"]]
        s.trace = {"typical": L.typical, "template": tpl.sheet_name, "topology": ("M: field → JB → marshalling cabinet (TS · SPD · relay · TB) → system cable → system cabinet" if L.term == "M"
                                                                                  else "D: field → JB → system cabinet (TS · SPD · relay wired straight to the I/O channel)") if has_jb else
                   ("M: MCC / VFD panel → marshalling cabinet → system cabinet" if L.term == "M" else "D: MCC / VFD panel → system cabinet"),
                   "nodes": nodes, "power": power, "conductors": cond, "complete": not broken, "broken": broken}
        if broken:
            L.add("ERROR", "BROKEN SIGNAL TRACE", f"{L.name} {s.sig} ({s.tag}): trace field → system is broken at " + ", ".join(broken), [s.source_row], "", s.sig)


def _mapping_report(L: LoopResult, reg: Registry) -> dict:
    if not L.signals:
        return {"mapped": 0, "missing_required": [], "unused_source": [], "template_without_source": []}
    mapped = sum(1 for s in L.signals for m in s.mapping if m["state"] in ("MAPPED", "DERIVED"))
    missing = [{"sig": s.sig, "field": m["source"], "tag": s.tag} for s in L.signals for m in s.mapping if m["state"] == "BLANK" and m["note"] == "required"]
    unused = [{"sig": s.sig, "tag": s.tag, **u} for s in L.signals for u in s.unused]
    nosrc = sorted({m["field"] for s in L.signals for m in s.mapping if m["state"] == "BLANK" and m["note"] != "required"})
    return {"mapped": mapped, "missing_required": missing, "unused_source": unused, "template_without_source": nosrc}
