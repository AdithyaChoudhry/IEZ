"""
Controlled test fixture + automated acceptance tests (A-J) for the Loop Wiring engine.

The fixture is built from the EXAMPLE sheet of the I/O Assignment master: one example loop per loop type is replicated for each of the
42 SPD x termination combinations, changing only LOOP_TYPE / SPD_ARR / TERM_ARR and the fields that depend on them (field SPD, panel SPD,
marshalling cabinet / TB / system cable). Every loop gets its own cabinets so that physical terminals and channels never collide.
The master workbooks are never modified.
"""
from __future__ import annotations

import copy
import io
import re
from typing import Any, Optional

import openpyxl

from . import analysis as A
from .registry import Registry, build_registry, SPD_VALUES, TERM_VALUES
from .source import SourceData, SourceRow

BASE_LOOPS = {"AI-2W": "XXXX-P-0001", "AI-4W": "XXXX-F-0001", "MOTOR-DOL": "XXXX-PM-0001", "MOTOR-VFD": "XXXX-PM-0002",
              "PNEU-VALVE": "XXXX-XV-0001", "MOV": "XXXX-MOV-0001", "SWITCH": "XXXX-L-0001"}
FSPD = ("FSPD_TAG", "FSPD_MODEL", "FSPD_IN1", "FSPD_IN2", "FSPD_OUT1", "FSPD_OUT2", "FSPD_EARTH")
PSPD = ("SPD_TAG", "SPD_POS", "SPD_MODEL", "SPD_IN1", "SPD_IN2", "SPD_OUT1", "SPD_OUT2", "SPD_EARTH")
MARSH = ("MARSH_AREA", "MARSH_CAB", "TB_STRIP", "TB_T1", "TB_T2", "SYS_CABLE", "SYS_CABLE_TYPE", "SYS_CORES")


def example_loops(io_master: bytes) -> dict[str, list[dict]]:
    wb = openpyxl.load_workbook(io.BytesIO(io_master), data_only=True)
    ws = wb["EXAMPLE"]
    hdr = {c.column: str(c.value) for c in ws[8] if c.value}
    rows = []
    for r in ws.iter_rows(min_row=10, values_only=False):
        d = {hdr[c.column]: c.value for c in r if c.column in hdr and c.value is not None and c.column <= 111}
        if d.get("LOOP_NAME"):
            rows.append(d)
    out: dict[str, list[dict]] = {}
    for lt, name in BASE_LOOPS.items():
        out[lt] = [copy.deepcopy(x) for x in rows if x.get("LOOP_NAME") == name]
    return out


def _prefix(v: Any, p: str) -> Any:
    return v.replace("XXXX", p) if isinstance(v, str) else v


def make_loop(lt: str, spd: str, term: str, base: list[dict], reg: Registry, n: int, prefix: Optional[str] = None) -> list[dict]:
    p = prefix or f"FX{n:02d}"
    typical = reg.typical_code(lt, spd, term)
    rows = []
    counters = {"DI": 0, "DO": 0, "AI": 0, "AO": 0}
    for k, b in enumerate(base, start=1):
        r = {c: _prefix(v, p) for c, v in b.items()}
        io = r["IO_TYPE"]
        counters[io] += 1
        j = counters[io]
        r.update(LOOP_TYPE=lt, SPD_ARR=spd, TERM_ARR=term, TYPICAL=typical, STATUS="USED", ISNIS=r.get("ISNIS", "NIS"))
        for c in list(r):
            if (c.startswith(("FSPD_", "SPD_", "MARSH_", "TB_", "SYS_CABLE")) or c == "SYS_CORES") and c != "SPD_ARR":
                r.pop(c)
        if spd == "A":
            r.update(FSPD_TAG=f"SPD-F{k:02d}", FSPD_MODEL="MAKE / MODEL XXXX", FSPD_IN1="1", FSPD_IN2="2", FSPD_OUT1="3", FSPD_OUT2="4", FSPD_EARTH="LOCAL EARTH BOSS")
        if spd in ("A", "B"):
            r.update(SPD_TAG="SPD1", SPD_POS=f"SPD1-{k:02d}", SPD_MODEL="MAKE / MODEL XXXX", SPD_IN1="4", SPD_IN2="5", SPD_OUT1="1", SPD_OUT2="2", SPD_EARTH="PE BAR PE-01")
        if term == "M":
            t1, t2 = {"AI": (f"{j}+", f"{j}-"), "AO": (f"{j}+", f"{j}-"), "DI": (f"+{j}", f"C{j}"), "DO": (f"{j}A", f"{j}B")}[io]
            r.update(MARSH_AREA="CONTROL ROOM", MARSH_CAB=f"{p}-MRC-01", TB_STRIP=f"TB-{io}", TB_T1=t1, TB_T2=t2, SYS_CABLE=f"{p}-SC-{io}01",
                     SYS_CABLE_TYPE="PREFAB 16P", SYS_CORES=f"CO{2 * j - 1:02d}/CO{2 * j:02d}")
        r["REV"] = r.get("DWG_REV", "A")
        rows.append(r)
    return rows


def make_fixture(template_bytes: bytes, io_master: bytes) -> list[dict]:
    reg = build_registry(template_bytes, io_master)
    base = example_loops(io_master)
    out: list[dict] = []
    n = 0
    for lt, no in reg.loop_types:
        for term in TERM_VALUES:
            for spd in SPD_VALUES:
                n += 1
                out += make_loop(lt, spd, term, base[lt], reg, n)
    # IS / NIS: the standard loops above are NIS; add two IS loops carrying isolator data
    for i, (lt, spd, term) in enumerate((("AI-2W", "B", "M"), ("SWITCH", "C", "D")), start=1):
        rows = make_loop(lt, spd, term, base[lt], reg, 90 + i, f"FXIS{i}")
        for r in rows:
            r.update(ISNIS="IS", ISO_TAG=f"ISB-00{i}", ISO_MODEL="MAKE / MODEL XXXX", ISO_IN1="1", ISO_IN2="2", ISO_OUT1="3", ISO_OUT2="4")
            r["LOOP_NAME"] = r["LOOP_NAME"] + "-IS"
        out += rows
    return out


def rows_to_source(rows: list[dict], first_row: int = 10) -> SourceData:
    sr = []
    for i, r in enumerate(rows):
        sr.append(SourceRow(first_row + i, {c: v for c, v in r.items() if v is not None and v != ""}))
    return SourceData("IO_ASSIGNMENT", 8, sorted({c for r in rows for c in r}), sr)


def fixture_workbook(rows: list[dict], io_master: bytes) -> bytes:
    """A COPY of the I/O Assignment master with the fixture rows written into IO_ASSIGNMENT (by FIELD CODE, never by column number)."""
    wb = openpyxl.load_workbook(io.BytesIO(io_master))
    ws = wb["IO_ASSIGNMENT"]
    col = {str(c.value): c.column for c in ws[8] if c.value}
    for i, r in enumerate(rows):
        for code, v in r.items():
            if code in col and code not in ("SNO", "RESULT"):
                ws.cell(row=10 + i, column=col[code], value=v)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ---------------------------------------------------------------------------------------------------------------------
def selection_matrix(an: A.Analysis, reg: Registry) -> list[dict]:
    """T01..T42: expected typical from the loop type / SPD / term, actual typical + template chosen by the engine."""
    by_loop = {l.name: l for l in an.loops}
    out = []
    n = 0
    for lt, no in reg.loop_types:
        for term in TERM_VALUES:
            for spd in SPD_VALUES:
                n += 1
                exp = f"{no}{spd}-{term}"
                L = next((l for l in an.loops if l.loop_type == lt and l.spd == spd and l.term == term and not l.name.endswith("-IS")), None)
                tpl = reg.templates.get(exp)
                ok = bool(L and L.typical == exp and tpl and L.template == tpl.sheet_name and L.generate)
                out.append({"test": f"T{n:02d}", "loop_type": lt, "spd": spd, "term": term, "expected": exp, "actual": L.typical if L else "", "template": L.template if L else "",
                            "loop": L.name if L else "", "loop_status": L.status if L else "", "result": "PASS" if ok else "FAIL"})
    return out


def run_acceptance(template_bytes: bytes, io_master: bytes) -> dict:
    """Tests A-J of the specification, run on the controlled fixture. Returns {tests:[...], matrix:[...], passed:bool}."""
    from .generate import build_gen_loops
    reg = build_registry(template_bytes, io_master)
    rows = make_fixture(template_bytes, io_master)
    an = A.analyze(rows_to_source(rows), reg, A.read_matrix(io_master))
    matrix = selection_matrix(an, reg)
    loops = {l.name: l for l in an.loops}
    gl, _ = build_gen_loops(an)
    by_sheet = {g.loop_fields["LOOP_NAME"]: g for g in gl}
    tests = []

    def add(code: str, name: str, ok: bool, detail: str):
        tests.append({"test": code, "name": name, "result": "PASS" if ok else "FAIL", "detail": detail})

    npass = sum(1 for m in matrix if m["result"] == "PASS")
    add("A", "Template selection - 42 combinations", npass == 42 and reg.complete, f"{npass} / 42 PASS; library {'complete' if reg.complete else 'INCOMPLETE'}")
    multi = {lt: [l for l in an.loops if l.loop_type == lt and not l.name.endswith("-IS")] for lt in ("MOTOR-DOL", "MOTOR-VFD", "PNEU-VALVE", "MOV")}
    want = {"MOTOR-DOL": 6, "MOTOR-VFD": 7, "PNEU-VALVE": 3, "MOV": 7}
    ok = all(len(v) == 6 and all(len(l.signals) == want[lt] and l.name in by_sheet for l in v) for lt, v in multi.items())
    add("B", "Multi-signal loops - one drawing per loop", ok, ", ".join(f"{lt}: {want[lt]} signals in one sheet x{len(v)}" for lt, v in multi.items()))
    m_ok = d_ok = True
    for l in an.loops:
        if l.name.endswith("-IS") or l.name not in by_sheet:
            continue
        for s in l.signals:
            db = s.data_block
            if l.term == "M":
                m_ok &= bool(db.get("MARSH_CAB") and db.get("TB_STRIP") and db.get("SYS_CABLE"))
            else:
                d_ok &= not any(db.get(f) for f in ("MARSH_CAB", "TB_STRIP", "TB_T1", "TB_T2", "SYS_CABLE", "SYS_CORES"))
    add("C", "M / D topology (marshalling cabinet filled for M, blank for D)", m_ok and d_ok, f"M ok={m_ok}, D ok={d_ok}")
    spd_ok = True
    for l in an.loops:
        if l.name.endswith("-IS") or not l.signals:
            continue
        for s in l.signals:
            db = s.data_block
            spd_ok &= {"A": bool(db.get("FSPD_TAG") and db.get("SPD_TAG")), "B": bool(not db.get("FSPD_TAG") and db.get("SPD_TAG")), "C": not db.get("FSPD_TAG") and not db.get("SPD_TAG")}[l.spd]
    add("D", "SPD arrangement A / B / C", spd_ok, "field + panel / panel only / none")
    f4 = [l for l in an.loops if l.loop_type == "AI-4W" and not l.name.endswith("-IS")]
    e_ok = len(f4) == 6 and all(all(s.data_block.get(f) for f in ("PWR_CABLE", "PWR_CORES", "DB_TAG", "DB_CCT", "DB_T1", "DB_T2", "DEV_TB")) for l in f4 for s in l.signals)
    f2 = [l for l in an.loops if l.loop_type == "AI-2W" and not l.name.endswith("-IS")]
    e_ok &= all(not any(s.data_block.get(f) for f in ("PWR_CABLE", "DB_TAG")) for l in f2 for s in l.signals)
    add("E", "AI-4W signal and power path (and none on AI-2W)", e_ok, "PWR_CABLE / PWR_CORES / DB_* populated for AI-4W only")
    rl = [s for l in an.loops if l.loop_type in ("MOTOR-DOL", "MOTOR-VFD", "MOV") and not l.name.endswith("-IS") for s in l.signals]
    f_ok = all(bool(s.data_block.get("RLY_TAG")) == (s.io_type == "DO") for s in rl)
    add("F", "Relay data on DO signals of motor / VFD / MOV loops only", f_ok, f"{sum(1 for s in rl if s.io_type == 'DO')} relay signals")
    isl = [l for l in an.loops if l.name.endswith("-IS")]
    g_ok = len(isl) == 2 and all(l.generate and all(s.data_block.get("INTERFACE_TAG") and s.data_block.get("INTERFACE_TYPE") != "NONE" for s in l.signals) for l in isl)
    nis = [l for l in an.loops if not l.name.endswith("-IS") and l.signals]
    g_ok &= all(all(not s.data_block.get("INTERFACE_TAG") and s.data_block.get("INTERFACE_TYPE") == "NONE" for s in l.signals) for l in nis)
    bad = copy.deepcopy(rows)
    for r in bad:
        if r["LOOP_NAME"].endswith("-IS") and r["LOOP_NAME"].startswith("FXIS1"):
            r.pop("ISO_TAG", None)
    an2 = A.analyze(rows_to_source(bad), reg, {})
    g_ok &= any(i.code == "IS LOOP INTERFACE DATA INCOMPLETE" for l in an2.loops for i in l.issues)
    add("G", "IS / NIS logic", g_ok, "IS loops carry isolator data, NIS loops draw none, IS without isolator tag = ERROR")
    h_ok = all(all(s.data_block.get(f) not in (None, "") for f in ("SYS_CAB", "MODULE_TAG", "MODULE_TYPE", "CHANNEL", "SLOT", "CRATE")) for l in an.loops for s in l.signals)
    add("H", "Module / channel hardware shown", h_ok, "SYS_CAB, MODULE_TAG, MODULE_TYPE, CHANNEL, SLOT, CRATE on every signal")
    i_ok = all(s.trace.get("complete") for l in an.loops for s in l.signals)
    add("I", "Connectivity trace complete on every signal", i_ok, f"{sum(len(l.signals) for l in an.loops)} signal traces")
    j_ok = True
    for l in an.loops:
        for s in l.signals:
            for m in s.mapping:
                if m["state"] == "MAPPED" and m["source"] != "(auto)":
                    src_row = next(r for r in an.source.rows if r.row == s.source_row)
                    j_ok &= src_row.get(m["source"]) == s.data_block.get(m["field"])
    add("J", "Field Code mapping - every DATA BLOCK value equals its source FIELD CODE value", j_ok, "FIELD CODE -> FIELD CODE, no positional mapping")
    nerr = [l.name for l in an.loops if l.status == "ERROR"]
    return {"tests": tests, "matrix": matrix, "passed": all(t["result"] == "PASS" for t in tests), "loops": len(an.loops), "signals": sum(len(l.signals) for l in an.loops),
            "error_loops": nerr, "review_loops": [l.name for l in an.loops if l.status == "REVIEW"]}
