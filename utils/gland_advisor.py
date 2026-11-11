"""
gland_advisor.py - cable OD -> gland size decision support (Metric / NPT / BSP / ET), and the comparison of the
schedule's existing glands with the advice.

The advice is an ENGINEERING RECOMMENDATION taken from the reference tables in utils.gland_reference. It is never
a certified or procurement-approved selection: the result always says the manufacturer datasheet must confirm it.
Nothing is converted between threads (M20 is not "1/2 NPT"): a thread is offered only when a table row lists it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from . import gland_reference as ref
from .gland_quantity import parse_gland

STANDARDS = ("METRIC", "NPT", "BSP", "ET")
OD_MIN_REASONABLE, OD_MAX_REASONABLE = 1.0, 150.0
BORDERLINE_MM = 0.25                  # at or within this distance of a published limit: BORDERLINE
CONSTRUCTIONS = ("UNARMOURED", "ARMOURED", "BRAIDED", "FLEXIBLE", "FLAT", "OTHER")

NOT_FINAL = ("ENGINEERING RECOMMENDATION - not a final, certified or procurement-approved selection. Confirm the gland against the datasheet "
             "of the manufacturer product that will be purchased, the enclosure entry thread and the project's hazardous-area requirements.")
ET_UNAVAILABLE = ("ET gland selection unavailable in the selected reference database. ET is a legacy electrical threadform and manufacturer verification is "
                  "required. Consider Metric or another project-specified thread only after checking the equipment/enclosure entry requirement.")
RULE_OD_VS_THREAD = ("Cable OD -> sealing/clamping compatibility of the gland. Thread standard -> connection to the equipment/enclosure. "
                     "These are related but different selection criteria.")


class AdviceError(Exception):
    """Invalid input (message is shown to the user)."""


def parse_od(value: Any) -> float:
    """Cable OD in mm: numeric, > 0, within a reasonable range. Raises AdviceError with a clear message."""
    if value is None or str(value).strip() == "":
        raise AdviceError("Cable OD is required.")
    t = str(value).strip().lower().replace("mm", "").strip()
    if t.count(",") == 1 and "." not in t:
        t = t.replace(",", ".")
    if not re.fullmatch(r"[+-]?\d+(\.\d+)?", t):
        raise AdviceError(f"Cable OD '{value}' is not a valid number. Enter millimetres, e.g. 14.2.")
    v = float(t)
    if v < 0:
        raise AdviceError("Cable OD cannot be negative.")
    if v == 0:
        raise AdviceError("Cable OD must be greater than zero.")
    if v < OD_MIN_REASONABLE or v > OD_MAX_REASONABLE:
        raise AdviceError(f"Cable OD {v:g} mm is outside the reasonable range for cable glands ({OD_MIN_REASONABLE:g}-{OD_MAX_REASONABLE:g} mm). Check the value.")
    return v


def _opt(v: Any) -> Optional[float]:
    if v is None or str(v).strip() == "":
        return None
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        raise AdviceError(f"'{v}' is not a valid number.")
    if x <= 0:
        raise AdviceError("Dimensions must be greater than zero.")
    return x


@dataclass
class Inputs:
    cable_type: str = ""
    od: float = 0.0
    construction: str = "UNARMOURED"
    bedding: Optional[float] = None
    armour_min: Optional[float] = None
    armour_max: Optional[float] = None
    armour_type: str = ""
    cores: str = ""
    csa: str = ""
    voltage: str = ""
    is_nis: str = ""
    hazardous: bool = False
    zone: str = ""
    gas_group: str = ""
    temp_class: str = ""
    protection: str = ""
    certification: str = ""
    barrier: bool = False
    ip: str = ""
    entry_thread: str = ""
    material: str = ""
    temperature: str = ""
    standards: tuple = STANDARDS


@dataclass
class Project:
    manufacturer: str = ""
    series: str = ""
    material: str = ""
    thread: str = ""                  # preferred standard
    hazardous: Optional[bool] = None
    ip: str = ""
    gland_type: str = ""
    mapping: dict = field(default_factory=dict)       # cable type -> gland designation (project / client specification)

    @staticmethod
    def from_dict(d: Optional[dict]) -> "Project":
        d = d or {}
        return Project(manufacturer=d.get("manufacturer", "") or "", series=d.get("series", "") or "", material=d.get("material", "") or "",
                       thread=(d.get("thread", "") or "").upper(), hazardous=d.get("hazardous"), ip=d.get("ip", "") or "",
                       gland_type=d.get("gland_type", "") or "", mapping=d.get("mapping") or {})


def inputs_from(d: dict, project: Optional[Project] = None) -> Inputs:
    project = project or Project()
    od = parse_od(d.get("od"))
    constr = (d.get("construction") or "UNARMOURED").upper()
    if constr not in CONSTRUCTIONS:
        raise AdviceError(f"Unknown cable construction '{d.get('construction')}'.")
    std = d.get("standards")
    if isinstance(std, str):
        std = [s for s in re.split(r"[,; ]+", std.upper()) if s]
    std = tuple(s for s in (std or STANDARDS) if s in STANDARDS) or STANDARDS
    haz = d.get("hazardous")
    if haz is None:
        haz = bool(project.hazardous)
    return Inputs(cable_type=str(d.get("cable_type") or "").strip(), od=od, construction=constr, bedding=_opt(d.get("bedding")),
                  armour_min=_opt(d.get("armour_min")), armour_max=_opt(d.get("armour_max")), armour_type=str(d.get("armour_type") or ""),
                  cores=str(d.get("cores") or ""), csa=str(d.get("csa") or ""), voltage=str(d.get("voltage") or ""), is_nis=str(d.get("is_nis") or ""),
                  hazardous=bool(haz), zone=str(d.get("zone") or ""), gas_group=str(d.get("gas_group") or ""), temp_class=str(d.get("temp_class") or ""),
                  protection=str(d.get("protection") or ""), certification=str(d.get("certification") or ""), barrier=bool(d.get("barrier")),
                  ip=str(d.get("ip") or project.ip or ""), entry_thread=str(d.get("entry_thread") or ""),
                  material=str(d.get("material") or project.material or ""), temperature=str(d.get("temperature") or ""), standards=std)


# ── advice texts ─────────────────────────────────────────────────────────────
def cable_advice(inp: Inputs) -> list[str]:
    t = f"{inp.cable_type} {inp.construction}".upper()
    out = []
    c = inp.construction
    if c == "UNARMOURED":
        out.append("Suitable unarmoured cable gland family required. Select the gland from the actual overall cable diameter and the required entry thread.")
    elif c == "ARMOURED":
        out.append("Armoured cable gland required. Overall cable diameter alone may not be sufficient; verify the bedding diameter and the armour range before final selection.")
    elif c == "BRAIDED":
        out.append("Use a gland family specifically approved for braided cable construction and verify the manufacturer's braid / overall diameter range.")
    elif c == "FLEXIBLE":
        out.append("Use a gland family intended for flexible cable and verify the manufacturer's strain-relief / overall diameter range.")
    elif c == "FLAT":
        out.append("Flat cable needs a gland family designed for flat cable; a round-cable gland cannot be assumed to seal on a flat profile.")
    else:
        out.append("Cable construction is 'other': identify the construction and select a gland family approved for it.")
    if re.search(r"\bVFD\b", t):
        out.append("VFD cable: verify whether the selected gland must accommodate the specific EMC / shield termination arrangement. Gland selection must follow the "
                   "project EMC requirement and the manufacturer's instructions.")
    if re.search(r"\bMOV\b", t):
        out.append("MOV cable: identify whether the cable is armoured or unarmoured and determine the gland from the actual cable OD and gland family, not from the term 'MOV cable'.")
    if re.search(r"RTD|THERMOCOUPLE|\bTC\b|INSTRUMENT|\d+\s*[PC]\s*X", t):
        out.append("RTD / thermocouple / instrumentation cable: cable OD and construction control the gland selection. Do not use core count alone to determine gland size.")
    if re.search(r"\bMCC\b|POWER", t):
        out.append("Power / MCC cable: check the cable construction (armoured or not) and the actual OD; the cable type name alone does not determine the gland.")
    return out


def hazardous_notes(inp: Inputs, cert_known: bool) -> list[str]:
    if not inp.hazardous:
        return []
    out = ["Hazardous area: only a gland certified for the area (zone/EPL, gas or dust group, temperature class and protection concept) may be used. "
           "An ordinary non-certified gland must not be selected."]
    asked = [f"Zone/EPL {inp.zone}" if inp.zone else "", f"group {inp.gas_group}" if inp.gas_group else "", f"T-class {inp.temp_class}" if inp.temp_class else "",
             inp.protection, f"certification {inp.certification}" if inp.certification else "", "barrier gland required" if inp.barrier else ""]
    asked = [a for a in asked if a]
    if asked:
        out.append("Requirement entered: " + ", ".join(asked) + ".")
    if not cert_known:
        out.append("CERTIFICATION CHECK REQUIRED: the reference database does not contain certification data for the listed glands. "
                   "Select a certified gland from the manufacturer's Ex documentation.")
    return out


# ── candidate search ─────────────────────────────────────────────────────────
def _size_key(r: ref.GlandRef):
    m = re.search(r"\d+", r.metric or r.size)
    s = 0 if "S" in r.size.upper() else 1
    return (int(m.group()) if m else 999, s, r.od_max)


def _in(v: float, lo: Optional[float], hi: Optional[float]) -> bool:
    return (lo is None or v >= lo - 1e-9) and (hi is None or v <= hi + 1e-9)


def _border(v: float, lo: float, hi: float) -> Optional[str]:
    if abs(v - lo) <= BORDERLINE_MM:
        return "minimum"
    if abs(v - hi) <= BORDERLINE_MM:
        return "maximum"
    return None


def _norm_thread(t: str) -> str:
    return parse_gland(t)["label"].upper().replace(" ", "")


def _ip_ok(have: str, need: str) -> Optional[bool]:
    m1, m2 = re.search(r"IP\s*(\d)(\d)", (have or "").upper()), re.search(r"IP\s*(\d)(\d)", (need or "").upper())
    if not m2:
        return True
    if not m1:
        return None
    return int(m1.group(1)) >= int(m2.group(1)) and int(m1.group(2)) >= int(m2.group(2))


def _check_row(r: ref.GlandRef, inp: Inputs, std: str, project: Project) -> Optional[dict]:
    """A candidate dict, or None when the row cannot take this cable / thread. All reasons are kept in `checks`."""
    if r.construction != inp.construction:
        return None
    opts = r.threads(std)
    if not opts:
        return None
    if inp.entry_thread:
        want = parse_gland(inp.entry_thread)
        if want["std"] == std:
            opts = [o for o in opts if _norm_thread(o) == _norm_thread(inp.entry_thread)]
            if not opts:
                return None
    if not _in(inp.od, r.od_min, r.od_max):
        return None
    flags, checks = [], []
    side = _border(inp.od, r.od_min, r.od_max)
    checks.append(f"Cable OD {inp.od:g} mm is within the published range {r.od_min:g}-{r.od_max:g} mm.")
    if side:
        flags.append("BORDERLINE")
        checks.append(f"BORDERLINE SELECTION: the OD is at/near the {side} of the published range - verify manufacturer tolerance / installation condition.")
    if r.construction == "ARMOURED":
        if r.bed_min is not None and r.bed_max is not None:
            if inp.bedding is None:
                flags.append("BEDDING NOT ENTERED")
                checks.append(f"Bedding diameter not entered: the gland needs {r.bed_min:g}-{r.bed_max:g} mm - verify before final selection.")
            elif not _in(inp.bedding, r.bed_min, r.bed_max):
                return None
            else:
                checks.append(f"Bedding diameter {inp.bedding:g} mm is within {r.bed_min:g}-{r.bed_max:g} mm.")
                b = _border(inp.bedding, r.bed_min, r.bed_max)
                if b:
                    flags.append("BORDERLINE")
                    checks.append(f"BORDERLINE: bedding diameter is at/near the {b} of the published range.")
        else:
            flags.append("BEDDING RANGE NOT IN DATABASE")
        if r.arm_ranges:
            lo, hi = inp.armour_min, inp.armour_max
            if lo is None and hi is None:
                flags.append("ARMOUR NOT ENTERED")
                checks.append("Armour dimension not entered: verify the armour range of the cable against the manufacturer's table.")
            else:
                lo, hi = lo if lo is not None else hi, hi if hi is not None else lo
                if not any(a <= lo + 1e-9 and hi <= b + 1e-9 for a, b in r.arm_ranges):
                    return None
                checks.append(f"Armour {lo:g}-{hi:g} mm lies within a published armour range ("
                              + " / ".join(f"{a:g}-{b:g}" for a, b in r.arm_ranges) + " mm).")
            if len(r.arm_ranges) > 1:
                flags.append("ARMOUR RANGE MAPPING TO BE VERIFIED")
    if inp.material:
        if not r.material:
            flags.append("MATERIAL NOT IN DATABASE")
            checks.append(f"Required material '{inp.material}': the database row does not state the material - verify.")
        elif inp.material.lower() not in r.material.lower():
            return None
    ipc = _ip_ok(r.ip, inp.ip) if inp.ip else True
    if ipc is None:
        flags.append("IP RATING NOT IN DATABASE")
        checks.append(f"Required {inp.ip}: the database row does not state an IP rating - verify with the manufacturer.")
    elif ipc is False:
        return None
    elif inp.ip:
        checks.append(f"{r.ip} stated for this gland meets the required {inp.ip} (per the table; installation conditions apply).")
    if inp.temperature and not r.temp:
        flags.append("TEMPERATURE NOT IN DATABASE")
    if inp.hazardous and not r.ex:
        flags.append("CERTIFICATION CHECK REQUIRED")
    flags.append("MANUFACTURER VERIFICATION REQUIRED")
    if project.gland_type and r.gland_type and project.gland_type.lower() not in r.gland_type.lower():
        flags.append("GLAND TYPE DIFFERS FROM PROJECT PREFERENCE")
    return {"manufacturer": r.manufacturer, "series": r.series, "gland_type": r.gland_type, "construction": r.construction, "gland_size": r.size,
            "standard": std, "thread_options": opts, "thread": opts[0] if len(opts) == 1 else " / ".join(opts),
            "od_range": [r.od_min, r.od_max], "bedding_range": [r.bed_min, r.bed_max] if r.bed_min is not None else None,
            "armour_ranges": [list(a) for a in r.arm_ranges], "ip": r.ip or "not in database", "ex": r.ex or "not in database",
            "material": r.material or "not in database", "temperature": r.temp or "not in database", "tier": r.tier,
            "flags": list(dict.fromkeys(flags)), "checks": checks, "borderline": "BORDERLINE" in flags,
            "source": {"manufacturer": r.manufacturer, "series": r.series, "document": r.source_doc, "url": r.source_url, "revision": r.revision, "notes": r.notes, "tier": r.tier},
            "_key": (TIER_RANK(r), _pref(r, project), "BORDERLINE" in flags, _size_key(r))}


def TIER_RANK(r: ref.GlandRef) -> int:
    return ref.TIER_ORDER.get(r.tier, 9)


def _pref(r: ref.GlandRef, p: Project) -> int:
    return (0 if (not p.manufacturer or p.manufacturer.lower() in r.manufacturer.lower()) else 1) + (0 if (not p.series or p.series.lower() == r.series.lower()) else 1)


def advise(inp: Inputs, rows: list[ref.GlandRef], project: Optional[Project] = None) -> dict:
    project = project or Project()
    family = [r for r in rows if r.construction == inp.construction]
    result_std = []
    cert_known = False
    for std in inp.standards:
        cands = [c for c in (_check_row(r, inp, std, project) for r in rows) if c]
        cands.sort(key=lambda c: c["_key"])
        for c in cands:
            c.pop("_key")
            cert_known = cert_known or c["ex"] != "not in database"
        entry = {"standard": std, "legacy": std == "ET"}
        std_rows = [r for r in rows if r.threads(std)]
        if std == "ET":
            entry["notice"] = ("ET = Electrical Thread, a legacy English electrical threadform (BS 31:1940). LEGACY / NON-STANDARD FOR MANY MODERN PRODUCTS; "
                               "not interchangeable with Metric, NPT or BSP. Verify availability with the chosen manufacturer.")
        if not cands:
            if not std_rows:
                entry.update(status="UNAVAILABLE", message=ET_UNAVAILABLE if std == "ET" else
                             f"{std} gland selection unavailable in the selected reference database: no table row lists {std} entry threads. "
                             "Upload the manufacturer's table that does, or verify with the manufacturer.")
            elif not family:
                entry.update(status="NO COMPATIBLE GLAND", message=f"The reference database has no {inp.construction.lower()} gland family. "
                             "Use a gland family specifically approved for this construction and verify the manufacturer's ranges.")
            else:
                entry.update(status="NO COMPATIBLE GLAND", message=_why_none(inp, family, std))
            entry.update(preferred=None, alternatives=[])
        else:
            pre, alts = cands[0], cands[1:]
            st = "BORDERLINE" if pre["borderline"] else "VALID"
            reason = (f"{pre['manufacturer']} {pre['series']} size {pre['gland_size']} is the smallest compatible gland that has the cable inside its published range "
                      f"({pre['od_range'][0]:g}-{pre['od_range'][1]:g} mm)" + (", and it is not at the limit of that range" if not pre["borderline"] else
                      " - but the OD sits at the limit of the range, so this is flagged as borderline") + ".")
            if any(a["borderline"] for a in cands) and not pre["borderline"]:
                reason += " A smaller size was set aside because the OD sits at the limit of its range (listed under alternatives, flagged BORDERLINE)."
            entry.update(status=st, preferred=pre, alternatives=alts, reason=reason,
                         message=(f"BORDERLINE - VERIFY MANUFACTURER TOLERANCE / INSTALLATION CONDITION. " if st == "BORDERLINE" else "") +
                         f"Preferred: size {pre['gland_size']} ({pre['thread']}); {len(alts)} alternative(s) also technically valid.")
        result_std.append(entry)
    advice = cable_advice(inp) + hazardous_notes(inp, cert_known)
    if inp.is_nis.upper() == "IS":
        advice.append("Intrinsically safe circuit: the gland itself does not make a circuit IS; follow the IS installation rules and keep IS cables separated/identified as the project specifies.")
    advice.append(RULE_OD_VS_THREAD)
    if inp.entry_thread:
        advice.append(f"Enclosure entry thread specified: {inp.entry_thread}. Only glands that list that thread were considered; verify the exact manufacturer gland variant.")
    return {"inputs": {"cable_type": inp.cable_type, "od": inp.od, "construction": inp.construction, "hazardous": inp.hazardous, "ip": inp.ip, "entry_thread": inp.entry_thread},
            "results": result_std, "advice": advice, "disclaimer": NOT_FINAL, "standards": ref.STANDARDS,
            "sources": sorted({(r.manufacturer, r.series, r.source_doc, r.source_url, r.revision) for r in rows if r.construction == inp.construction})}


def _why_none(inp: Inputs, family: list[ref.GlandRef], std: str) -> str:
    cover = [r for r in family if r.threads(std)]
    lo, hi = min(r.od_min for r in cover), max(r.od_max for r in cover)
    if inp.od < lo or inp.od > hi:
        return (f"No {std} gland in the database covers a {inp.od:g} mm cable: the published {inp.construction.lower()} ranges run {lo:g}-{hi:g} mm. "
                "Check the OD or use a manufacturer table with a suitable range.")
    if inp.entry_thread:
        return f"No gland covering {inp.od:g} mm lists the entry thread {inp.entry_thread}. Check the enclosure entry thread or the manufacturer's alternate thread options."
    return ("The cable OD is covered by the table, but the bedding / armour / material / IP requirements entered exclude every gland. "
            "Re-check those inputs against the cable datasheet.")


# ── existing vs recommended (schedule cable types) ───────────────────────────
STATUSES = ("MATCH", "REVIEW", "MISMATCH", "MISSING OD", "MISSING GLAND DATA", "MANUFACTURER CHECK REQUIRED")


def compare_cable_type(cable_type: str, existing: list[str], data: dict, rows: list[ref.GlandRef], project: Project) -> dict:
    """One schedule cable type: its existing gland designations vs the advice. The schedule value is never changed."""
    out = {"cable_type": cable_type, "existing": existing, "od": data.get("od"), "construction": data.get("construction"),
           "recommended": "", "recommended_detail": None, "result": "", "message": "", "alternatives": [], "flags": [], "source": None, "advice": []}
    mapped = project.mapping.get(cable_type) if project.mapping else None
    if mapped:
        out["recommended"], out["source"] = mapped, {"manufacturer": "Project specification", "series": "project gland mapping", "document": "Project / client specification (user-entered)", "url": "", "revision": ""}
        out["result"] = "MATCH" if any(_norm_thread(mapped) == _norm_thread(e) or mapped.strip().upper() == e.strip().upper() for e in existing) else ("MISMATCH" if existing else "MISSING GLAND DATA")
        out["message"] = f"Project gland mapping gives {mapped}; the schedule has {', '.join(existing) or 'no gland'}. Project specification takes priority over the reference tables."
        return out
    if not existing:
        out["result"], out["message"] = "MISSING GLAND DATA", "The schedule has no gland size for this cable type."
    od = data.get("od")
    if od in (None, ""):
        out["result"] = out["result"] or "MISSING OD"
        out["message"] = (out["message"] + " " if out["message"] else "") + "Enter the cable OD (or import it from the cable datasheet) to run the check."
        if out["result"] == "MISSING GLAND DATA":
            out["message"] += " (Cable OD is also missing.)"
        return out
    try:
        inp_d = {"od": od, "construction": data.get("construction") or "UNARMOURED", "cable_type": cable_type, "bedding": data.get("bedding"),
                 "armour_min": data.get("armour_min"), "armour_max": data.get("armour_max"), "hazardous": data.get("hazardous"),
                 "ip": data.get("ip"), "entry_thread": ""}
        parsed = [parse_gland(e) for e in existing]
        stds = []
        for p in parsed:
            if p["std"] and p["std"] not in stds:
                stds.append(p["std"])
        if not stds:
            stds = [project.thread] if project.thread in STANDARDS else ["METRIC"]
            out["flags"].append("THREAD OF EXISTING GLAND NOT STATED")
        inp_d["standards"] = stds
        inp = inputs_from(inp_d, project)
    except AdviceError as e:
        out["result"], out["message"] = "MISSING OD", str(e)
        return out
    adv = advise(inp, rows, project)
    out["advice"] = adv["advice"]
    out["flags"] += ["MANUFACTURER VERIFICATION REQUIRED"]
    if inp.hazardous:
        out["flags"].append("CERTIFICATION CHECK REQUIRED")
    best = None
    for res in adv["results"]:
        if res["preferred"] and (best is None or res["standard"] == (parsed[0]["std"] if parsed and parsed[0]["std"] else res["standard"])):
            best = res
    if best is None:
        res0 = adv["results"][0]
        out["result"] = "MANUFACTURER CHECK REQUIRED" if res0["status"] in ("UNAVAILABLE",) or res0["standard"] == "ET" else (out["result"] or "MANUFACTURER CHECK REQUIRED")
        out["message"] = res0["message"]
        return out
    pre = best["preferred"]
    out["recommended"] = f"{pre['gland_size']} - {pre['thread']}" + (f" ({pre['manufacturer']} {pre['series']})" if pre["manufacturer"] else "")
    out["recommended_detail"] = {k: pre[k] for k in ("manufacturer", "series", "gland_type", "gland_size", "thread", "od_range", "bedding_range", "flags")}
    out["alternatives"] = [f"{a['gland_size']} - {a['thread']}" for a in best["alternatives"]]
    out["source"] = pre["source"]
    if out["result"] == "MISSING GLAND DATA":
        return out
    valid_labels = {_norm_thread(o) for c in [pre] + best["alternatives"] for o in c["thread_options"]}
    ex_norm = [_norm_thread(e) for e in existing]
    pre_labels = {_norm_thread(o) for o in pre["thread_options"]}
    if any(e in pre_labels for e in ex_norm):
        out["result"] = "REVIEW" if pre["borderline"] else "MATCH"
        out["message"] = ("Existing gland is the preferred option." if not pre["borderline"] else "Existing gland is the preferred option but the OD is borderline for it - verify.")
    elif any(e in valid_labels for e in ex_norm):
        out["result"] = "REVIEW"
        out["message"] = "Existing gland is technically valid but is not the smallest compatible option; alternatives are listed."
    else:
        out["result"] = "MISMATCH"
        out["message"] = (f"Existing {', '.join(existing)} is not among the glands whose published range covers a {od:g} mm cable. "
                          f"The reference tables point to {pre['gland_size']} ({pre['thread']}). Review - the project gland is not changed automatically.")
        if _adjacent(ex_norm, pre_labels, rows, best["standard"]):
            out["result"] = "REVIEW"
            out["message"] = (f"Existing {', '.join(existing)} is one size step from the advised {pre['gland_size']} ({pre['thread']}); "
                              "check the cable OD and the manufacturer range. The project gland is not changed automatically.")
    return out


def _adjacent(existing: list[str], preferred: set, rows: list[ref.GlandRef], std: str) -> bool:
    """True when an existing designation is the neighbour (one step up or down) of the advised one in the table order."""
    order = []
    for r in sorted(rows, key=_size_key):
        for o in r.threads(std):
            n = _norm_thread(o)
            if n not in order:
                order.append(n)
    idx = {n: i for i, n in enumerate(order)}
    return any(e in idx and any(p in idx and abs(idx[e] - idx[p]) <= 1 for p in preferred) for e in existing)
