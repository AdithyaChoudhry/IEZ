"""
lug_advisor.py - Cable Lug Advisor for the Cable Lug Quantity Generator.

Runs on the result of utils.lug_quantity (which stays the authority for physical cables, conductor counts and the
number of lugged conductors at each end - shared main cables are already one physical cable there). The advisor adds,
per termination END of every physical cable:

    conductor material (from the cable description: Cu / Al / Unknown)
    recommended termination  (lug / ferrule type, material, barrel size) with a confidence status
    the selected termination (user selection > source data > advisor) and its quantity
    compatibility warnings and the items that need engineering input

Engineering principles (general selection guidance, never an unconditional compatibility approval):
  * copper conductor -> copper / tin-plated copper; aluminium -> aluminium or an approved bimetallic connector on a
    copper terminal; unknown material -> manual confirmation
  * the terminal decides the termination: bolted stud -> ring / tubular; screw terminal -> fork, ring, pin or ferrule
    by design; cage clamp -> ferrule or prepared conductor as permitted; PLC / DCS terminal -> ferrule ONLY where the
    terminal manufacturer requires it. Unknown terminal -> advisory only, MANUAL REVIEW.
  * a barrel size follows the conductor size; stud / hole size and palm are never derived -> Manual Verification Required
Nothing is invented: what the sources do not state is reported, not assumed.
"""
from __future__ import annotations

import io
import math
import re
from collections import OrderedDict
from typing import Any, Optional

AUTO = "Auto — Advisor Recommendation"
RING, FORK, PIN = "Ring Type Lug", "Fork / Spade Type Lug", "Pin Type Lug"
FERRULE1, FERRULE2 = "Bootlace Ferrule — Single", "Bootlace Ferrule — Twin"
TUBULAR, BIMETAL, MECH, BLADE = "Tubular Compression Lug", "Bimetallic Lug", "Mechanical Lug", "Blade Type Termination"
OTHER, NONE = "Other / Custom", "No Lug Required"
LUG_TYPES = [AUTO, RING, FORK, PIN, FERRULE1, FERRULE2, TUBULAR, BIMETAL, MECH, BLADE, OTHER, NONE]
BOLTED = {RING, TUBULAR, BIMETAL, MECH}
TERMINALS = {"UNKNOWN": "Not stated", "PLC_DCS": "PLC / DCS terminal", "SCREW": "Screw terminal block",
             "CAGE_CLAMP": "Cage-clamp / spring terminal", "STUD": "Bolted stud / busbar"}
MANUAL = "Manual Verification Required"
CONFIRMED, MANUAL_SEL, ADVISORY, REVIEW = "Confirmed from source data", "Manually selected", "Automatically recommended", "Manual Review"


class AdvisorError(ValueError):
    pass


# ── settings ─────────────────────────────────────────────────────────────────
def settings_from(d: Optional[dict]) -> dict:
    """{'default_type', 'default_scope', 'terminal': {category: key}, 'terminal_material', 'selections': {key: {...}}}"""
    d = d or {}
    out = {"default_type": d.get("default_type") or AUTO, "default_scope": (d.get("default_scope") or "ALL").upper(),
           "terminal": {k: (v or "UNKNOWN").upper() for k, v in (d.get("terminal") or {}).items()},
           "terminal_material": (d.get("terminal_material") or "UNKNOWN").upper(), "selections": d.get("selections") or {},
           # conductor material when the cable description does not state it: an ENGINEER's project input, never assumed
           "default_material": {"COPPER": "Copper", "ALUMINIUM": "Aluminium"}.get((d.get("default_material") or "").upper(), "Unknown")}
    if out["default_type"] not in LUG_TYPES:
        raise AdvisorError(f"Unknown cable lug type '{out['default_type']}'.")
    for k, v in out["terminal"].items():
        if v not in TERMINALS:
            raise AdvisorError(f"Unknown terminal type '{v}' for {k.lower()} cables.")
    for key, sel in out["selections"].items():
        if sel.get("type") and sel["type"] not in LUG_TYPES:
            raise AdvisorError(f"Unknown cable lug type '{sel['type']}' for {key}.")
    return out


# ── reading the cable ────────────────────────────────────────────────────────
def conductor_material(cable_type: str) -> str:
    t = f" {(cable_type or '').upper()} "
    if re.search(r"ALUMIN|[^A-Z]ALU?[^A-Z]|\bAL\b|XLPE/AL|AYFY|A2XFY|A2XWY", t):
        return "Aluminium"
    if re.search(r"COPPER|[^A-Z]CU[^A-Z]", t):
        return "Copper"
    return "Unknown"


def conductor_size(cable_type: str) -> tuple[Optional[float], Optional[float]]:
    from .lug_quantity import parse_construction
    c = parse_construction(cable_type)
    return c.get("size"), c.get("earth_size")


def application(row: dict) -> str:
    return {"INSTRUMENTATION": "Instrument", "CONTROL": "Control", "POWER": "Power"}.get(row.get("category"), "Unknown")


# ── the recommendation ───────────────────────────────────────────────────────
def recommend(row: dict, size: Optional[float], material: str, st: dict) -> dict:
    """Advisor recommendation for one cable (both ends) - type, material, barrel size, status, notes."""
    cat = row.get("category")
    notes: list[str] = []
    if row.get("lug_required") == "NO":
        return {"type": NONE, "material": "-", "status": CONFIRMED if row.get("basis") in ("SCHEDULE", "TERMINATION") else ADVISORY,
                "notes": [row.get("reason") or "No cable lug for this termination."]}
    if row.get("lug_required") != "YES" or cat not in ("INSTRUMENTATION", "CONTROL", "POWER"):
        return {"type": None, "material": MANUAL, "status": REVIEW,
                "notes": ["The termination requirement or the cable category is not known: " + (row.get("reason") or "no rule applies") + "."]}
    if size is None:
        return {"type": None, "material": MANUAL, "status": REVIEW, "notes": ["Conductor size not stated in the cable description."]}
    term = st["terminal"].get(cat, "UNKNOWN")
    if material == "Aluminium":
        tmat = st["terminal_material"]
        if tmat == "ALUMINIUM":
            rec = {"type": TUBULAR, "material": "Aluminium", "status": ADVISORY,
                   "notes": ["Aluminium conductor on an aluminium-compatible connector."]}
        else:
            rec = {"type": BIMETAL, "material": "Bimetallic (Al barrel / Cu palm)", "status": ADVISORY if tmat == "COPPER" else REVIEW,
                   "notes": ["Aluminium conductor: an approved bimetallic connector is needed on a copper terminal."
                             + ("" if tmat == "COPPER" else " The terminal material is not stated - confirm it.")]}
        return rec
    mat = "Tin-plated copper" if material == "Copper" else MANUAL
    if material == "Unknown":
        notes.append("Conductor material is not stated in the cable description - confirm copper / aluminium before ordering.")
    if cat == "POWER" or term == "STUD":
        t = TUBULAR if size >= 16 else RING
        notes.append("Bolted termination: stud diameter, hole size and palm width are not in the sources - " + MANUAL + ".")
        if term == "UNKNOWN":
            notes.append("Terminal type not stated: a bolted stud is assumed for a power cable - confirm.")
        return {"type": t, "material": mat, "status": REVIEW if (material == "Unknown" or term == "UNKNOWN") else ADVISORY, "notes": notes}
    # instrumentation / control conductors on a terminal block
    if term in ("PLC_DCS", "SCREW", "CAGE_CLAMP"):
        notes.append({"PLC_DCS": "Use a bootlace ferrule only where the PLC / DCS terminal manufacturer requires or permits it; "
                                 "some terminals take the stranded conductor directly.",
                      "SCREW": "Screw terminal: ferrule, pin or fork per the terminal design.",
                      "CAGE_CLAMP": "Cage-clamp terminal: ferrule or prepared conductor as the terminal manufacturer permits."}[term])
        return {"type": FERRULE1, "material": mat, "status": REVIEW if material == "Unknown" else ADVISORY, "notes": notes}
    notes.append("Terminal type not stated: a bootlace ferrule is suggested for stranded instrument / control conductors - confirm the "
                 "terminal design (ring lugs cannot be used on terminal blocks that do not accept them).")
    return {"type": FERRULE1, "material": mat, "status": REVIEW, "notes": notes}


def compatibility(t: str, size: Optional[float], material: str, cat: str, term: str) -> list[str]:
    """Warnings for a SELECTED termination (never silently changed)."""
    w = []
    if t in (FERRULE1, FERRULE2) and size is not None and size >= 16:
        w.append(f"A bootlace ferrule on a {size:g} mm² conductor is unusual - check the terminal manufacturer.")
    if t == TUBULAR and size is not None and size <= 2.5:
        w.append(f"A tubular compression lug on a {size:g} mm² conductor is unusual - check the lug range.")
    if material == "Aluminium" and t in (RING, FORK, PIN, FERRULE1, FERRULE2, TUBULAR):
        w.append("Aluminium conductor: use an aluminium or approved bimetallic connector, not a copper one.")
    if material == "Copper" and t == BIMETAL:
        w.append("Bimetallic lug selected for a copper conductor - check the selection.")
    if t in BOLTED and term in ("PLC_DCS", "CAGE_CLAMP"):
        w.append(f"{t} selected but the terminal is a {TERMINALS[term].lower()} - it cannot take a bolted lug.")
    return w


def _selection(st: dict, row: dict, end: str) -> tuple[Optional[dict], str]:
    sel = st["selections"]
    for k, level in ((f"tag:{row['cable_tag']}|end:{end}", "end"), (f"tag:{row['cable_tag']}", "cable"), (f"type:{row.get('type_key')}", "group")):
        if sel.get(k) and (sel[k].get("type") or sel[k].get("material") or sel[k].get("size")):
            return sel[k], level
    return None, ""


def _default_applies(st: dict, row: dict) -> bool:
    scope = st["default_scope"]
    return st["default_type"] != AUTO and (scope == "ALL" or scope == (row.get("category") or "").upper())


def _qty(t: Optional[str], conductors: int) -> int:
    if not t or t == NONE:
        return 0
    if t == FERRULE2:
        return math.ceil(conductors / 2)        # two conductors in one ferrule
    return conductors


# ── apply to a lug_quantity result ───────────────────────────────────────────
def apply(res: dict, settings: Optional[dict]) -> dict:
    """Adds res['advisor'] = {'ends': [...], 'summary': [...], 'review': [...], 'kpis': {...}} (the lug engine's own
    numbers are not changed)."""
    st = settings_from(settings)
    ends_out, review = [], []
    for row in res.get("cable_wise", []):
        size, esize = conductor_size(row.get("cable_type"))
        material = conductor_material(row.get("cable_type"))
        material_src = "cable description"
        if material == "Unknown" and st["default_material"] != "Unknown":
            material, material_src = st["default_material"], "project setting"
        rec = recommend(row, size, material, st)
        cat = row.get("category") or "UNKNOWN"
        term = st["terminal"].get(cat, "UNKNOWN")
        src_type = row.get("lug_type") if row.get("lug_type") not in (None, "", "NOT SPECIFIED") and row.get("basis") in ("SCHEDULE", "SCHEDULE + RULE") else None
        for end, n_main, place in (("from", row.get("lugged_from"), row.get("from")), ("to", row.get("lugged_to"), row.get("to"))):
            n_main = n_main or 0
            earth = (row.get("lug_from") or 0) - (row.get("lugged_from") or 0) if end == "from" else (row.get("lug_to") or 0) - (row.get("lugged_to") or 0)
            sel, level = _selection(st, row, end)
            if sel and sel.get("type") and sel["type"] != AUTO:
                t, status, how = sel["type"], MANUAL_SEL, f"manual ({level})"
            elif src_type:
                t, status, how = src_type, CONFIRMED, "source data"
            elif _default_applies(st, row) and row.get("lug_required") == "YES":
                t, status, how = st["default_type"], MANUAL_SEL, "project default"
            else:
                t, status, how = rec["type"], rec["status"], "advisor"
            if row.get("status") != "OK" or row.get("lug_required") == "REVIEW":
                status = REVIEW
            lug_material = (sel or {}).get("material") or (rec["material"] if how == "advisor" else (row.get("material") if row.get("material") not in (None, "", "NOT SPECIFIED") else rec["material"]))
            barrel = (sel or {}).get("size") or (f"{size:g} mm²" if size is not None else MANUAL)
            if t in BOLTED and not (sel or {}).get("size"):
                barrel += f" barrel; stud / hole: {MANUAL}"
            # the COUNT of conductor ends is the lug engine's (known when its status is OK); only the TYPE may still need review
            if row.get("lug_required") == "NO":
                qty = 0
            elif row.get("lug_required") == "YES" and row.get("status") == "OK" and t:
                qty = _qty(t, n_main)
            else:
                qty = None
            warnings = compatibility(t, size, material, cat, term) if t and t not in (NONE, AUTO, OTHER) else []
            e = {"cable_tag": row["cable_tag"], "cable_type": row.get("cable_type"), "application": application(row), "category": cat,
                 "conductor_material": material, "material_source": material_src, "conductor_size": f"{size:g} mm²" if size is not None else MANUAL,
                 "end": end.upper(), "location": place or "Not stated", "terminal": TERMINALS.get(term, term),
                 "recommended": rec["type"] or MANUAL, "lug_type": t or MANUAL, "lug_material": lug_material, "lug_size": barrel,
                 "conductors": n_main if row.get("lug_required") == "YES" else None, "quantity": qty, "status": status, "selected_by": how,
                 "warnings": warnings, "notes": rec["notes"], "remarks": "; ".join(warnings + ([] if how != "advisor" else rec["notes"]))}
            ends_out.append(e)
            if earth and row.get("lug_required") == "YES":
                ends_out.append({**e, "end": end.upper() + " (EARTH)", "conductor_size": f"{esize:g} mm²" if esize else MANUAL,
                                 "recommended": RING, "lug_type": RING if how == "advisor" else t, "lug_size": (f"{esize:g} mm² barrel" if esize else MANUAL) + f"; stud / hole: {MANUAL}",
                                 "conductors": earth, "quantity": earth if (row.get("status") == "OK") else None, "warnings": [], "remarks": "Separate earth conductor: ring lug on the earth stud."})
            if status == REVIEW or warnings:
                review.append({"cable_tag": row["cable_tag"], "end": end.upper(), "issue": "; ".join(warnings) or "; ".join(rec["notes"]) or row.get("reason") or "Review required",
                               "kind": "Compatibility warning" if warnings else "Missing engineering information", "status": status})
            if how.startswith("manual") or how == "project default":
                if rec["type"] and t != rec["type"]:
                    review.append({"cable_tag": row["cable_tag"], "end": end.upper(), "kind": "Manual override",
                                   "issue": f"{t} selected ({how}); the advisor recommends {rec['type']}.", "status": status})
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    for e in ends_out:
        if not e["quantity"]:
            continue
        k = (e["lug_type"], e["lug_material"], e["conductor_size"], e["lug_size"])
        g = groups.setdefault(k, {"lug_type": k[0], "lug_material": k[1], "conductor_size": k[2], "specification": k[3], "quantity": 0, "cables": set()})
        g["quantity"] += e["quantity"]
        g["cables"].add(e["cable_tag"])
    summary = [{**{k: v for k, v in g.items() if k != "cables"}, "cables": len(g["cables"])} for g in groups.values()]
    kpis = {"terminations": len(ends_out), "total_quantity": sum(e["quantity"] or 0 for e in ends_out),
            "manual_review": sum(1 for e in ends_out if e["status"] == REVIEW), "manual_selections": sum(1 for e in ends_out if e["status"] == MANUAL_SEL),
            "confirmed": sum(1 for e in ends_out if e["status"] == CONFIRMED), "advisory": sum(1 for e in ends_out if e["status"] == ADVISORY)}
    res["advisor"] = {"ends": ends_out, "summary": summary, "review": review, "kpis": kpis, "lug_types": LUG_TYPES,
                      "terminals": TERMINALS, "settings": {k: v for k, v in st.items() if k != "selections"}}
    return res


# ── report sheets ────────────────────────────────────────────────────────────
def add_sheets(xlsx: bytes, res: dict) -> bytes:
    """CABLE LUG DETAILS, LUG QUANTITY SUMMARY and ADVISOR REVIEW added after the existing lug report sheets."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    adv = res.get("advisor")
    if not adv:
        return xlsx
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    head = PatternFill("solid", start_color="163A5F", end_color="163A5F")
    thin = Side(style="thin", color="B7C3D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(vertical="center", wrap_text=True)

    def sheet(title, headers, rows, widths):
        ws = wb.create_sheet(title)
        ws.cell(1, 1, title).font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
        ws.cell(1, 1).fill = head
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        for c, h in enumerate(headers, 1):
            cell = ws.cell(3, c, h)
            cell.font, cell.fill, cell.border, cell.alignment = Font(bold=True, color="FFFFFF"), head, border, Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.column_dimensions[get_column_letter(c)].width = widths.get(c, 18)
        for r, row in enumerate(rows, 4):
            for c, v in enumerate(row, 1):
                cell = ws.cell(r, c, v)
                cell.border, cell.alignment = border, wrap
        ws.freeze_panes = "A4"
        ws.print_title_rows = "3:3"

    sheet("CABLE LUG DETAILS", ["SL. NO.", "CABLE TAG", "CABLE TYPE", "CABLE APPLICATION", "CONDUCTOR MATERIAL", "CONDUCTOR SIZE",
                                "TERMINATION END", "LOCATION", "LUG TYPE", "LUG MATERIAL", "LUG SIZE", "REQUIRED QUANTITY", "SELECTION STATUS", "REMARKS"],
          [[i, e["cable_tag"], e["cable_type"], e["application"], e["conductor_material"], e["conductor_size"], e["end"], e["location"],
            e["lug_type"], e["lug_material"], e["lug_size"], e["quantity"] if e["quantity"] is not None else "REVIEW", e["status"], e["remarks"]]
           for i, e in enumerate(adv["ends"], 1)], {2: 22, 3: 22, 9: 26, 10: 24, 11: 34, 13: 26, 14: 60})
    sheet("LUG QUANTITY SUMMARY", ["LUG TYPE", "LUG MATERIAL", "CONDUCTOR SIZE", "SPECIFICATION", "TOTAL QUANTITY", "CABLES"],
          [[g["lug_type"], g["lug_material"], g["conductor_size"], g["specification"], g["quantity"], g["cables"]] for g in adv["summary"]]
          + [["TOTAL", "", "", "", sum(g["quantity"] for g in adv["summary"]), ""]], {1: 28, 2: 28, 4: 44})
    sheet("ADVISOR REVIEW", ["CABLE TAG", "END", "KIND", "STATUS", "ISSUE / ACTION"],
          [[r["cable_tag"], r["end"], r["kind"], r["status"], r["issue"]] for r in adv["review"]] or [["-", "-", "-", "-", "No item needs review."]],
          {1: 22, 3: 30, 4: 26, 5: 100})
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
