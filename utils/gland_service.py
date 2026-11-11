"""
gland_service.py - the Cable Gland Quantity Generator pipeline and its Excel report.

    upload -> gland_quantity.extract/aggregate (quantities)  +  gland_advisor (OD checks per cable type)  -> payload + workbook

The uploaded workbook is only read. The report is a new workbook; nothing of the schedule is overwritten.
"""
from __future__ import annotations

import io
from collections import OrderedDict
from typing import Any, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import gland_advisor as adv
from . import gland_quantity as gq
from . import gland_reference as ref

HEAD = PatternFill("solid", start_color="163A5F", end_color="163A5F")
THIN = Side(style="thin", color="B7C3D0")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def settings_from(d: Optional[dict]) -> gq.Settings:
    d = d or {}
    dq = d.get("default_qty")
    try:
        dq = float(dq) if dq not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        raise gq.GlandError("The default gland quantity must be a number.")
    rep = d.get("repeated_rows", "once")
    if rep not in ("once", "sum"):
        raise gq.GlandError("Repeated rows must be 'once' or 'sum'.")
    return gq.Settings(default_qty=dq, repeated_rows=rep, sheets=d.get("sheets"))


def reference_rows(extra: Optional[list[ref.GlandRef]] = None) -> list[ref.GlandRef]:
    """Project > vendor tables (uploaded) > built-in published example tables."""
    return list(extra or []) + ref.builtin()


def analyze(data: bytes, settings: Optional[dict] = None, cable_data: Optional[dict] = None, project: Optional[dict] = None,
            extra_rows: Optional[list[ref.GlandRef]] = None, ref_problems: Optional[list[str]] = None) -> dict:
    st = settings_from(settings)
    proj = adv.Project.from_dict(project)
    rows = reference_rows(extra_rows)
    occ, exc, infos, types = gq.extract(data, st)
    lines, exc2 = gq.aggregate(occ, st)
    exceptions = exc + exc2 + [{"severity": "WARNING", "kind": "Reference table", "ref": "gland reference upload", "message": p} for p in (ref_problems or [])]
    cable_data = cable_data or {}

    # ── OD advisory per cable type (the schedule's gland is compared, never replaced) ──
    existing_by_type: "OrderedDict[str, list[str]]" = OrderedDict()
    for l in lines:
        if l["cable_type"] != "Not stated":
            existing_by_type.setdefault(gq.cable_key(l["cable_type"]), [])
            if l["gland_size"] not in existing_by_type[gq.cable_key(l["cable_type"])]:
                existing_by_type[gq.cable_key(l["cable_type"])].append(l["gland_size"])
    advisory = []
    for t in types:
        key = t["key"]
        d = dict(cable_data.get(key) or cable_data.get(t["cable_type"]) or {})
        d.setdefault("od", t["od"])
        d.setdefault("construction", t["construction"])
        if d.get("od") in ("", None):
            d["od"] = None
        else:
            try:
                d["od"] = adv.parse_od(d["od"])
            except adv.AdviceError as e:
                exceptions.append({"severity": "ERROR", "kind": "Invalid cable OD", "ref": t["cable_type"], "message": str(e)})
                d["od"] = None
        if d.get("hazardous") is None and proj.hazardous is not None:
            d["hazardous"] = proj.hazardous
        if not d.get("ip") and proj.ip:
            d["ip"] = proj.ip
        cmp_ = adv.compare_cable_type(t["cable_type"], existing_by_type.get(key, t["existing_glands"]), d, rows, proj)
        cmp_.update(key=key, cables=t["cables"], construction=d.get("construction"), construction_stated=t["construction_stated"],
                    od_source="entered" if cable_data.get(key, {}).get("od") not in (None, "") else ("schedule column" if t["od"] else ""))
        advisory.append(cmp_)
        ref_name = t["cable_type"]
        if cmp_["result"] == "MISSING OD":
            exceptions.append({"severity": "WARNING", "kind": "Missing OD", "ref": ref_name, "message": "No cable OD: the gland cannot be checked against the published ranges."})
        elif cmp_["result"] == "MISSING GLAND DATA":
            exceptions.append({"severity": "WARNING", "kind": "Missing gland", "ref": ref_name, "message": "The schedule has no gland size for this cable type."})
        elif cmp_["result"] == "MISMATCH":
            exceptions.append({"severity": "ERROR", "kind": "Gland mismatch", "ref": ref_name, "message": cmp_["message"]})
        elif cmp_["result"] == "REVIEW":
            exceptions.append({"severity": "WARNING", "kind": "Review gland", "ref": ref_name, "message": cmp_["message"]})
        elif cmp_["result"] == "MANUFACTURER CHECK REQUIRED":
            exceptions.append({"severity": "WARNING", "kind": "Manufacturer check required", "ref": ref_name, "message": cmp_["message"]})
        for f in cmp_["flags"]:
            if f == "CERTIFICATION CHECK REQUIRED":
                exceptions.append({"severity": "WARNING", "kind": "Hazardous-area verification required", "ref": ref_name,
                                   "message": "Hazardous area: certification is not in the reference database; select a certified gland from the manufacturer's Ex documentation."})
        if cmp_.get("recommended_detail") and "BORDERLINE" in (cmp_["recommended_detail"].get("flags") or []):
            exceptions.append({"severity": "WARNING", "kind": "Borderline range", "ref": ref_name, "message": "The OD is at/near the limit of the published range of the advised gland."})
        if not t["construction_stated"] and cmp_["result"] not in ("MISSING OD",):
            exceptions.append({"severity": "INFO", "kind": "Construction assumed", "ref": ref_name,
                               "message": f"The cable type does not say armoured/unarmoured; '{cmp_['construction']}' was assumed. Set the construction in the OD table."})
        if any(parse_ == "ET" for parse_ in [gq.parse_gland(e)["std"] for e in cmp_["existing"]]):
            exceptions.append({"severity": "WARNING", "kind": "ET availability", "ref": ref_name, "message": adv.ET_UNAVAILABLE})

    by_key = {a["key"]: a for a in advisory}
    cable_wise = []
    for l in lines:
        a = by_key.get(gq.cable_key(l["cable_type"])) if l["cable_type"] != "Not stated" else None
        cable_wise.append({**{k: l[k] for k in ("cable_type", "cable_tag", "location", "gland_type", "thread", "gland_size", "qty", "source")},
                           "od": a["od"] if a else None, "existing": l["gland_size"], "recommended": a["recommended"] if a else "",
                           "result": a["result"] if a else "MISSING GLAND DATA"})
    # one preview line per distinct cable-wise combination is enough; the full list goes to Excel
    sums = gq.summaries(lines)
    order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    exceptions.sort(key=lambda e: (order.get(e["severity"], 3), e["kind"]))
    payload = {
        "sheets": infos, "used_sheets": sorted({o.sheet for o in occ}),
        "totals": {"glands": sums["total_qty"], "lines": len(lines), "cable_types": len(types), "cables": len({l["cable_tag"] for l in lines}),
                   "errors": sum(1 for e in exceptions if e["severity"] == "ERROR"), "warnings": sum(1 for e in exceptions if e["severity"] == "WARNING")},
        "summary": sums, "cable_types": types, "advisory": advisory, "cable_wise": cable_wise[:3000], "cable_wise_truncated": len(cable_wise) > 3000,
        "exceptions": exceptions[:3000], "settings": {"default_qty": st.default_qty, "repeated_rows": st.repeated_rows},
        "reference": {"rows": len(rows), "tiers": sorted({r.tier for r in rows}), "disclaimer": adv.NOT_FINAL},
    }
    payload["_lines"] = lines
    payload["_cable_wise"] = cable_wise
    payload["_exceptions"] = exceptions
    payload["_rows"] = rows
    return payload


# ── workbook ─────────────────────────────────────────────────────────────────
def _sheet(wb, title, headers, rows, note=None, widths=None):
    ws = wb.create_sheet(title)
    n = len(headers)
    ws.cell(1, 1, title).font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    for c in range(1, n + 1):
        ws.cell(1, c).fill = HEAD
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n)
    ws.cell(1, 1).alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 24
    if note:
        ws.cell(2, 1, note).font = Font(name="Calibri", size=10, italic=True)
    for c, h in enumerate(headers, 1):
        cell = ws.cell(3, c, h)
        cell.font, cell.fill, cell.alignment, cell.border = Font(name="Calibri", size=11, bold=True, color="FFFFFF"), HEAD, CENTER, BORDER
    ws.row_dimensions[3].height = 34
    for i, row in enumerate(rows, 4):
        for c, v in enumerate(row, 1):
            cell = ws.cell(i, c, v)
            cell.font, cell.alignment, cell.border = Font(name="Calibri", size=11), CENTER, BORDER
    for c in range(1, n + 1):
        w = (widths or {}).get(c) or min(max(12, max([len(str(headers[c - 1]))] + [len(str(r[c - 1])) for r in rows[:200] if c - 1 < len(r) and r[c - 1] is not None]) + 2), 60)
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A4"
    return ws


def to_workbook(p: dict, source_name: str = "uploaded cable schedule") -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    S = p["summary"]
    note = f"Source: {source_name} (read only - original values not changed). ENGINEERING RECOMMENDATION - final selection to be confirmed against the manufacturer datasheet."
    _sheet(wb, "GLAND SUMMARY", ["GLAND TYPE", "THREAD STANDARD", "GLAND SIZE", "MATERIAL", "CERTIFICATION", "QUANTITY"],
           [[r["gland_type"], r["thread"], r["gland_size"], r["material"], r["certification"], r["qty"]] for r in S["by_gland"]] +
           [["TOTAL", "", "", "", "", S["total_qty"]]], note=note)
    _sheet(wb, "CABLE TYPE SUMMARY", ["CABLE TYPE", "GLAND TYPE", "THREAD", "GLAND SIZE", "QUANTITY", "CABLES"],
           [[r["cable_type"], r["gland_type"], r["thread"], r["gland_size"], r["qty"], r["cables"]] for r in S["by_cable_type"]], note=note)
    _sheet(wb, "CABLE GLAND DETAIL", ["CABLE TYPE", "CABLE TAG NUMBER", "LOCATION", "GLAND TYPE", "THREAD", "GLAND SIZE", "QTY", "CABLE OD (MM)",
                                      "EXISTING GLAND", "RECOMMENDED GLAND", "RESULT", "SOURCE (SHEET / ROW)"],
           [[r["cable_type"], r["cable_tag"], r["location"], r["gland_type"], r["thread"], r["gland_size"], r["qty"], r["od"], r["existing"],
             r["recommended"], r["result"], r["source"]] for r in p["_cable_wise"]], note=note, widths={11: 26, 10: 34})
    _sheet(wb, "LOCATION SUMMARY", ["LOCATION", "THREAD", "GLAND SIZE", "QUANTITY"],
           [[r["location"], r["thread"], r["gland_size"], r["qty"]] for r in S["by_location"]] +
           [["TOTAL " + r["location"].upper(), "", "", r["qty"]] for r in S["location_totals"]], note=note)
    _sheet(wb, "OD ADVISORY", ["CABLE TYPE", "CABLES", "CONSTRUCTION", "CABLE OD (MM)", "OD SOURCE", "EXISTING GLAND (SCHEDULE)", "RECOMMENDED GLAND", "ALTERNATIVES",
                               "RESULT", "MESSAGE", "SOURCE (MANUFACTURER / SERIES / DOCUMENT)"],
           [[a["cable_type"], a["cables"], a["construction"], a["od"], a.get("od_source", ""), ", ".join(a["existing"]), a["recommended"],
             ", ".join(a["alternatives"]), a["result"], a["message"],
             ((a["source"] or {}).get("manufacturer", "") + " " + (a["source"] or {}).get("series", "") + " - " + (a["source"] or {}).get("document", "")).strip(" -")
             if a["source"] else ""] for a in p["advisory"]], note=note, widths={10: 60, 11: 50, 8: 30})
    _sheet(wb, "EXCEPTIONS", ["SEVERITY", "KIND", "REFERENCE", "MESSAGE"],
           [[e["severity"], e["kind"], e["ref"], e["message"]] for e in p["_exceptions"]] or [["OK", "", "", "No exceptions"]], note=note, widths={4: 100})
    refs = [["Disclaimer", "", "", adv.NOT_FINAL]] + [["Basis", s["id"], s["title"], s["use"]] for s in ref.STANDARDS] + [["Principle", "", "", t] for t in ref.PRINCIPLES]
    srcs = sorted({(r.manufacturer, r.series, r.source_doc, r.source_url, r.revision, r.tier) for r in p["_rows"]})
    refs += [["Reference data", f"{m} {s}".strip(), d, f"{u}  |  {rev}  |  tier: {t}"] for m, s, d, u, rev, t in srcs]
    refs += [["Assumption", "", "", f"Repeated identical termination rows of one cable counted: {p['settings']['repeated_rows']}."],
             ["Assumption", "", "", f"Default gland quantity for a size without a quantity: {p['settings']['default_qty'] or 'none (flagged as MISSING GLAND QUANTITY)'}."],
             ["Assumption", "", "", "A cable type that does not state armoured/unarmoured is treated as unarmoured until set in the OD table."],
             ["Limit", "", "", "The built-in tables contain Metric and NPT entry threads only; BSP and ET are unavailable unless a manufacturer table is uploaded. No IP, Ex, material or temperature data is claimed."]]
    _sheet(wb, "REFERENCE - ASSUMPTIONS", ["TYPE", "ID / SOURCE", "TITLE / DOCUMENT", "USE / DETAIL"], refs, note=note, widths={3: 50, 4: 110})
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def advise_payload(form: dict, project: Optional[dict] = None, extra_rows: Optional[list[ref.GlandRef]] = None) -> dict:
    proj = adv.Project.from_dict(project)
    inp = adv.inputs_from(form, proj)
    out = adv.advise(inp, reference_rows(extra_rows), proj)
    out["sources"] = [dict(manufacturer=a, series=b, document=c, url=d, revision=e) for a, b, c, d, e in out["sources"]]
    out["standards"] = ref.STANDARDS
    return out
