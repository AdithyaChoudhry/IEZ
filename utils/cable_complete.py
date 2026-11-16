"""
cable_complete.py - CABLE SCHEDULE COMPLETE: one IODB -> one workbook with the Cable Schedule sheets, the I/O Summary,
the Gland Quantity sheets and the Cable Lug Quantity sheets.

This is an ORCHESTRATION layer. It contains no cable, gland, lug or I/O logic of its own; it calls the engines the
individual modules use, in this order, on the same data:

    IODB bytes
      -> utils.file_handler.read_iodb + utils.cable_schedule_extra.normalize      (the one IODB parse; validation)
      -> utils.template_processor.process_cable_schedule (+ extra MCC/VFD/MOV/LCP sheets)   cable schedule workbook
      -> utils.io_summary.build_io_summary / append_io_summary_sheet                 I/O summary
      -> utils.gland_service.analyze   on the GENERATED cable schedule                gland quantities
      -> utils.lug_quantity.analyze    on the GENERATED cable schedule                lug quantities
      -> compile one workbook (+ cover/index + combined exception report) and cross-check the modules

A stage is marked complete only when its engine returned successfully. A failed cable schedule stops the gland and lug
stages; review items in gland/lug never fail the package.
"""
from __future__ import annotations

import io
import re
import time
from copy import copy
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import cable_schedule_extra as cse
from . import gland_quantity as gq
from . import gland_service as gsvc
from . import lug_quantity as lq
from . import workbook_assembly as wa
from .cable_summary import CABLE_SUMMARY_SHEET
from .drum_schedule import extract_demand, fmt
from .file_handler import read_iodb
from .io_summary import append_io_summary_sheet, build_io_summary
from .template_processor import process_cable_schedule

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "backend" / "app" / "templates" / "cable_schedule" / "CABLE_SCHEDULE_TEMPLATE.xlsx"

STAGES = [("validate", "IODB Validation"), ("schedule", "Cable Schedule Generation"), ("io", "I/O Summary"),
          ("gland", "Gland Quantity Extraction"), ("lug", "Lug Quantity Extraction"), ("compile", "Final Workbook Compilation")]


class CompleteError(Exception):
    """User-facing problem that stops the package."""


def builtin_template() -> Optional[bytes]:
    return TEMPLATE_PATH.read_bytes() if TEMPLATE_PATH.exists() else None


# ── step 1: validation (the single IODB parse) ───────────────────────────────
def validate(iodb: bytes) -> dict:
    """Parse once with the existing reader/normaliser and report what the package can be built from."""
    df, err = read_iodb(io.BytesIO(iodb))
    if err:
        return {"ok": False, "status": "BLOCKED", "errors": [f"The IODB could not be read: {err}"], "warnings": [], "df": None}
    try:
        recs, cols = cse.normalize(df)
    except cse.ExtraSheetError as e:
        return {"ok": False, "status": "BLOCKED", "errors": [str(e)], "warnings": [], "df": df}
    errors, warnings = [], []
    present = lambda v: not cse.is_missing(v)
    tags = {r.tag_no.upper() for r in recs if present(r.tag_no)}
    branch = {r.branch_cable_tag.upper() for r in recs if present(r.branch_cable_tag)}
    main = {r.main_cable_tag.upper() for r in recs if present(r.main_cable_tag)}
    jbs = {r.jb_tag.upper() for r in recs if present(r.jb_tag)}
    cable_rows = sum(1 for r in recs if present(r.branch_cable_tag) or present(r.main_cable_tag))
    jb_rows = sum(1 for r in recs if present(r.jb_tag))
    missing = []
    for f, label in (("tag_no", "TAG NO"), ("jb_tag", "JUNCTION BOX TAG NO."), ("branch_cable_tag", "INSTRUMENT TO JB CABLE TAG"), ("branch_cable_type", "INSTRUMENT TO JB CABLE TYPE"),
                     ("branch_cable_length", "BRANCH CABLE LENGTH"), ("main_cable_tag", "MAIN CABLE TAG NUMBER"), ("main_cable_type", "MAIN CABLE TYPE"),
                     ("main_cable_length", "MAIN CABLE LENGTH(MTRS)"), ("io_type", "SIGNAL I/O TYPE")):
        if not cols.get(f):
            missing.append(label)
    cable_cols = [m for m in missing if "CABLE" in m]
    if not cols.get("tag_no"):
        errors.append("The IODB has no TAG NO column.")
    if len(cable_cols) == 6:
        errors.append("The IODB has none of the cable columns (INSTRUMENT TO JB CABLE TAG / TYPE, BRANCH CABLE LENGTH, MAIN CABLE TAG NUMBER / TYPE / LENGTH), so no cable schedule can be built.")
    elif cable_cols:
        warnings.append("Cable fields not found: " + ", ".join(cable_cols) + ".")
    if not cols.get("jb_tag") or jb_rows == 0:
        warnings.append("No junction box data in the IODB: the Instrument Cable Schedule cannot be built; the MCC / VFD / MOV / LCP sheets are still generated where the IODB has such signals.")
    if not cols.get("io_type"):
        warnings.append("No SIGNAL I/O TYPE column: the I/O Summary cannot count signals.")
    if not errors and cable_rows == 0:
        errors.append("The IODB contains no cable tags (no INSTRUMENT TO JB CABLE TAG or MAIN CABLE TAG NUMBER values).")
    demand, d_issues, d_stats = ([], [], {}) if errors else extract_demand(df)
    stats = {"rows": len(df), "unique_tags": len(tags), "cable_records": cable_rows, "jb_records": len(jbs), "jb_rows": jb_rows,
             "unique_cable_tags": len(branch | main), "main_cable_tags": len(main), "branch_cable_tags": len(branch),
             "valid_cables": len(demand), "total_cable_length": d_stats.get("total_length", 0) if d_stats else 0}
    status = "BLOCKED" if errors else ("READY WITH WARNINGS" if (warnings or d_issues) else "READY")
    return {"ok": not errors, "status": status, "errors": errors, "warnings": warnings, "stats": stats, "missing_fields": missing,
            "issues": [{"severity": i.severity, "kind": i.kind, "ref": i.ref, "message": i.message} for i in d_issues],
            "df": df, "recs": recs, "cols": cols, "demand": demand, "branch": branch, "main": main}


# ── helpers for the combined workbook ────────────────────────────────────────
_HEAD = PatternFill("solid", start_color="163A5F", end_color="163A5F")
_THIN = Side(style="thin", color="B7C3D0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _copy_plain(src, dst_wb, title: str):
    """Copy a report sheet as it was generated by its own module (values, styles, merges, widths, freeze panes)."""
    dst = dst_wb.create_sheet(title=title)
    for row in src.iter_rows():
        for c in row:
            if type(c).__name__ == "MergedCell":
                continue
            d = dst.cell(c.row, c.column, c.value)
            if c.has_style:
                d.font, d.fill, d.border = copy(c.font), copy(c.fill), copy(c.border)
                d.alignment, d.number_format = copy(c.alignment), c.number_format
    for rng in src.merged_cells.ranges:
        dst.merge_cells(str(rng))
    for k, cd in src.column_dimensions.items():
        dst.column_dimensions[k].width = cd.width
        dst.column_dimensions[k].min, dst.column_dimensions[k].max = cd.min, cd.max
    for r, rd in src.row_dimensions.items():
        if rd.height:
            dst.row_dimensions[r].height = rd.height
    dst.freeze_panes = src.freeze_panes
    return dst


def _has_data(ws, first_row: int = 4) -> bool:
    for row in ws.iter_rows(min_row=first_row, values_only=True):
        vals = [v for v in row if v not in (None, "")]
        placeholder = str(vals[0]).strip().upper().startswith(("OK", "NO SHORTAGE", "NO EXCEPTIONS", "NO LUGS", "NOTHING LEFT")) if vals else False
        if vals and not placeholder:
            return True
    return False


def _sev(s: str) -> str:
    return {"ERROR": "Error", "WARNING": "Warning", "REVIEW": "Review", "INFO": "Info"}.get(s, s.title())


_ACTION = {
    "Missing cable length": "Enter the cable length in the IODB and regenerate.", "Missing cable type": "Enter the cable type in the IODB and regenerate.",
    "Missing cable tag": "Assign a cable tag number in the IODB / cable schedule.", "MISSING GLAND QUANTITY": "State the gland quantity in the schedule or set a project default quantity in the Gland module.",
    "Thread not stated": "State the thread standard (Metric / NPT / BSP / ET) with the gland size.", "Gland size TBA": "Replace TBA with the actual gland size.",
    "Core count cannot be identified": "Correct the cable type text (e.g. 12P x 1.5 Sq.mm) or override in the Lug module.", "Lug requirement unknown": "Confirm the termination arrangement or override in the Lug module.",
    "Conflicting cable data": "Resolve the conflicting cable data for this tag in the IODB.", "Conflicting values": "Resolve the conflicting values for this cable tag in the IODB.",
    "Missing IS/NIS": "State IS or NIS for the cable in the IODB.", "Cable runs stated": "Confirm the number of physical cables for this tag.",
}


def _action(kind: str) -> str:
    return _ACTION.get(kind, "Review the item in the source IODB / cable schedule.")


def _exception_rows(v: dict, sched: dict, gl: Optional[dict], lg: Optional[dict], io_reason: str, checks: Optional[list] = None) -> list[dict]:
    rows = []

    def add(module, sev, ref, sheet, field, issue, src="", exp=""):
        rows.append({"module": module, "severity": _sev(sev), "ref": ref, "sheet": sheet, "field": field, "issue": issue, "source_value": src,
                     "expected_value": exp, "action": _action(field)})

    for e in v.get("errors", []):
        add("IODB Validation", "ERROR", "IODB", "", "IODB", e)
    for w in v.get("warnings", []):
        add("IODB Validation", "WARNING", "IODB", "", "IODB", w)
    for i in v.get("issues", []):
        if i["severity"] != "INFO":
            add("IODB Validation", i["severity"], i["ref"], "IODB", i["kind"], i["message"])
    for w in sched.get("warnings", []):
        add("Cable Schedule", "WARNING", "", "", "Cable schedule", w)
    if io_reason:
        add("I/O Summary", "WARNING", "", "I/O SUMMARY", "I/O Summary", io_reason)
    if gl:
        for e in gl["_exceptions"]:
            add("Gland", e["severity"], e["ref"], "", e["kind"], e["message"])
    if lg:
        for e in lg["exceptions"]:
            add("Lug", e["severity"], e["ref"], e.get("sheet", ""), e["kind"], e["message"])
    for c in checks or []:
        for tag in c.get("only_in_iodb", [])[:30]:
            add("Consistency", "WARNING", tag, "", "Cable tag not in schedule", f"Cable tag {tag} is in the IODB (junction-box rows) but was not written to the generated Instrument Cable Schedule.")
        for tag in c.get("only_in_schedule", [])[:30]:
            add("Consistency", "WARNING", tag, "", "Cable tag not in IODB", f"Cable tag {tag} is in the generated Instrument Cable Schedule but not in the IODB (leftover template value?).")
    return rows


def _consistency(v: dict, sched: dict, gl: Optional[dict], lg: Optional[dict], sheet_name: str, include_schedule: bool) -> list[dict]:
    """The modules must agree on the physical cables they process (one normalised cable dataset)."""
    checks = []
    if not lg:
        return checks
    known = [c["cable_tag"] for c in lg["cable_wise"] if c["tag_known"]]
    lug_tags = set(known)
    checks.append({"check": "Each physical cable tag is counted once in the lug dataset", "ok": len(known) == len(lug_tags),
                   "detail": f"{len(known)} cable records, {len(lug_tags)} unique tags"})
    if gl:
        g_tags = {l["cable_tag"] for l in gl["_lines"] if not l["cable_tag"].startswith("(no cable tag)")}
        extra = g_tags - lug_tags
        checks.append({"check": "Every cable tag in the gland quantities is a physical cable in the lug dataset", "ok": not extra,
                       "detail": f"{len(g_tags)} gland cable tags; {len(extra)} not in the lug dataset" + (f" (e.g. {sorted(extra)[:3]})" if extra else "")})
    if include_schedule:
        inst = {c["cable_tag"].upper() for c in lg["cable_wise"] if c["tag_known"] and sheet_name in c["sheets"].split(", ")}
        present = lambda x: not cse.is_missing(x)
        expected = set()
        for r in v["recs"]:
            if present(r.jb_tag):
                if present(r.branch_cable_tag) and present(r.branch_cable_type):
                    expected.add(r.branch_cable_tag.upper())
                if present(r.main_cable_tag) and present(r.main_cable_type):
                    expected.add(r.main_cable_tag.upper())
        only_iodb, only_sched = sorted(expected - inst), sorted(inst - expected)
        diff = only_iodb + only_sched
        checks.append({"check": "Unique cable tags of the IODB (junction-box rows) = physical cables of the generated Instrument Cable Schedule", "ok": not diff,
                       "detail": f"IODB {len(expected)} unique cable tags, schedule {len(inst)}" + (f"; {len(only_iodb)} only in the IODB, {len(only_sched)} only in the schedule (e.g. {diff[:3]})" if diff else ""),
                       "only_in_iodb": only_iodb[:50], "only_in_schedule": only_sched[:50]})
    return checks


# ── the orchestrator ─────────────────────────────────────────────────────────
Progress = Callable[[str, str, str], None]


def run(iodb: bytes, iodb_name: str, template: Optional[bytes] = None, progress: Optional[Progress] = None) -> dict:
    """-> {"stages", "kpis", "workbook" (bytes), previews..., "exceptions"}. Raises CompleteError when nothing can be produced."""
    stages: dict[str, dict] = {k: {"label": l, "state": "pending", "message": "", "seconds": None} for k, l in STAGES}

    def mark(key, state, message="", t0=None):
        stages[key].update(state=state, message=message, seconds=round(time.time() - t0, 1) if t0 else None)
        if progress:
            progress(key, state, message)

    def begin(key):
        stages[key]["state"] = "running"
        if progress:
            progress(key, "running", "")
        return time.time()

    used_builtin = template is None
    template = template or builtin_template()
    if template is None:
        raise CompleteError("No Cable Schedule template is installed on the server. Upload the project's Cable Schedule template (the same one the Cable Schedule Generator uses).")

    # 1. validation
    t0 = begin("validate")
    v = validate(iodb)
    if not v["ok"]:
        mark("validate", "failed", " ".join(v["errors"]), t0)
        raise CompleteError("IODB validation failed: " + " ".join(v["errors"]))
    mark("validate", "warning" if v["status"] != "READY" else "done",
         "Ready for Cable Schedule generation" if v["status"] == "READY" else "; ".join(v["warnings"][:2]) or f"{len(v['issues'])} IODB data issue(s) reported", t0)
    df, recs, cols = v["df"], v["recs"], v["cols"]

    # 2. cable schedule (existing generator)
    t0 = begin("schedule")
    avail = cse.availability(df)
    extras = [k for k in cse.SHEETS if avail[k]["available"]]
    include_schedule = v["stats"]["jb_rows"] > 0
    jb_col, tag_col = cols.get("jb_tag"), cols.get("tag_no")
    if not include_schedule and not extras:
        mark("schedule", "failed", "No junction box rows and no MCC / VFD / MOV / LCP signals.", t0)
        for k in ("gland", "lug"):
            mark(k, "skipped", "Cable Schedule generation failed. Gland and Lug quantities were not generated.")
        raise CompleteError("Cable Schedule generation failed. Gland and Lug quantities were not generated. The IODB has no junction box rows and no MCC / VFD / MOV / LCP signals.")
    report: dict = {}
    sched_bytes, fname, err = process_cable_schedule(io.BytesIO(iodb), io.BytesIO(template), jb_col or "", tag_col or "TAG NO", output_mode=wa.WITH_SUMMARY,
                                                     extra_sheets=extras or None, extra_report=report, include_schedule=include_schedule)
    if err:
        mark("schedule", "failed", err, t0)
        mark("gland", "skipped", "Cable Schedule generation failed. Gland and Lug quantities were not generated.")
        mark("lug", "skipped", "Cable Schedule generation failed. Gland and Lug quantities were not generated.")
        mark("io", "skipped", "Not run: the Cable Schedule stage failed.")
        mark("compile", "skipped", "Not run.")
        raise CompleteError(f"Cable Schedule generation failed. Gland and Lug quantities were not generated. ({err})")
    sched_warn = list(report.get("warnings", []))
    mark("schedule", "warning" if sched_warn else "done", f"{len(report.get('sheets', []))} extra sheet(s) + schedule" if report.get("sheets") else "Instrument Cable Schedule generated", t0)
    schedule_sheet = _schedule_sheet_name(template)

    # 3. I/O summary (existing engine)
    io_res, io_reason = _io_stage(df, stages, mark, begin)

    # 4. gland (existing engine, on the GENERATED cable schedule)
    gl = gl_wb = None
    t0 = begin("gland")
    try:
        gl = gsvc.analyze(sched_bytes, None, None, None, None, None)
        gl_wb = openpyxl.load_workbook(io.BytesIO(gsvc.to_workbook(gl, "generated Cable Schedule")))
        n_rev = sum(1 for e in gl["_exceptions"] if e["severity"] in ("ERROR", "WARNING"))
        mark("gland", "warning" if n_rev else "done", f"Cable Schedule generated. Gland quantity contains {n_rev} review item(s)." if n_rev else "Gland quantities generated", t0)
    except Exception as exc:                                    # non-critical: the schedule stays valid
        mark("gland", "warning", f"Gland quantity could not be generated: {exc}", t0)
        sched_warn.append(f"Gland quantity could not be generated: {exc}")

    # 5. lug (existing engine, on the GENERATED cable schedule)
    lg = lg_wb = None
    t0 = begin("lug")
    try:
        lg, lrules = lq.analyze(sched_bytes)
        lg_wb = openpyxl.load_workbook(io.BytesIO(lq.to_workbook(lg, lrules, "generated Cable Schedule")))
        n_rev = lg["kpis"]["review"] + lg["kpis"]["errors"]
        mark("lug", "warning" if n_rev else "done", f"Cable Schedule generated. Lug quantity contains {n_rev} review item(s)." if n_rev else "Lug quantities generated", t0)
    except Exception as exc:
        mark("lug", "warning", f"Lug quantity could not be generated: {exc}", t0)
        sched_warn.append(f"Lug quantity could not be generated: {exc}")

    # 6. compile
    t0 = begin("compile")
    sched = {"warnings": sched_warn, "sheets": report.get("sheets", []), "stats": report.get("stats", [])}
    checks = _consistency(v, sched, gl, lg, schedule_sheet, include_schedule)
    exc_rows = _exception_rows(v, sched, gl, lg, io_reason, checks)
    kpis = _kpis(v, io_res, gl, lg, exc_rows)
    workbook, sheet_index = _compile(sched_bytes, template, iodb_name, v, kpis, stages, checks, io_res, gl_wb, lg_wb, exc_rows,
                                     [schedule_sheet] + list(report.get("sheets", []) or []) + [CABLE_SUMMARY_SHEET])
    mark("compile", "done", f"{len(sheet_index)} sheets", t0)

    return {"stages": [dict(key=k, **stages[k]) for k, _ in STAGES], "kpis": kpis, "validation": _public_validation(v), "checks": checks,
            "sheets": sheet_index, "workbook": workbook, "iodb_name": iodb_name,
            "io_summary": {"rows": io_res.rows, "has_isnis": io_res.has_isnis, "reason": io_res.reason, "total_rows": io_res.total_rows},
            "gland": {"totals": gl["totals"], "by_gland": gl["summary"]["by_gland"], "by_location": gl["summary"]["location_totals"]} if gl else None,
            "lug": {"kpis": lg["kpis"], "types": lg["types"], "procurement": lg["procurement"]} if lg else None,
            "cables": lg["cable_wise"][:3000] if lg else [], "exceptions": exc_rows[:5000],
            "schedule": {"sheets": report.get("sheets", []), "stats": report.get("stats", []), "instrument_schedule": include_schedule, "template": "built-in" if used_builtin else "uploaded"}}


def _io_stage(df, stages, mark, begin):
    t0 = begin("io")
    res = build_io_summary(df)
    if res.rows:
        mark("io", "done", f"{sum(r['total'] for r in res.rows)} signals counted", t0)
    else:
        mark("io", "warning", res.reason or "No signals to count.", t0)
    return res, res.reason


def _schedule_sheet_name(template: bytes) -> str:
    from .generators import _find_cs_sheet
    wb = openpyxl.load_workbook(io.BytesIO(template), read_only=True)
    try:
        return _find_cs_sheet(wb) or "Cable Schedule -INST"
    finally:
        wb.close()


def _public_validation(v: dict) -> dict:
    return {k: v[k] for k in ("status", "errors", "warnings", "stats", "missing_fields", "issues") if k in v}


def _kpis(v, io_res, gl, lg, exc_rows) -> dict:
    s = v["stats"]
    counted = sum(r["total"] for r in io_res.rows if r["type"] in ("AI", "AO", "DI", "DO")) if io_res.rows else 0
    return {"tags": s["unique_tags"], "cable_tags": lg["kpis"]["cables"] if lg else s["unique_cable_tags"], "cable_types": lg["kpis"]["cable_types"] if lg else None,
            "cable_length": s["total_cable_length"], "io": counted, "glands": gl["totals"]["glands"] if gl else None, "lugs": lg["kpis"]["total_lugs"] if lg else None,
            "exceptions": sum(1 for e in exc_rows if e["severity"] in ("Error", "Warning", "Review")),
            "errors": sum(1 for e in exc_rows if e["severity"] == "Error")}


def _compile(sched_bytes, template, iodb_name, v, kpis, stages, checks, io_res, gl_wb, lg_wb, exc_rows, sched_generated=()):
    """ONE workbook: cover/index + the generated cable schedule workbook (unchanged) + I/O summary + gland + lug + exceptions."""
    wb = openpyxl.load_workbook(io.BytesIO(sched_bytes))
    original_names = list(wb.sheetnames)
    generated = set(sched_generated)
    index: list[dict] = [{"section": "Cable Schedule", "sheet": n, "note": "generated by the Cable Schedule Generator" if n in generated else "template sheet (unchanged)"} for n in original_names]
    # I/O summary: the existing sheet writer, added after the cable schedule sheets
    append_io_summary_sheet(wb, io_res)
    index.append({"section": "Summary", "sheet": wa.IO_SUMMARY_SHEET, "note": "existing I/O Summary engine"})
    sections = [("Glands", gl_wb, [("GLAND SUMMARY", "GLAND QUANTITY SUMMARY"), ("CABLE TYPE SUMMARY", "GLAND BY CABLE TYPE"), ("CABLE GLAND DETAIL", "GLAND DETAIL"),
                                   ("LOCATION SUMMARY", "GLAND BY LOCATION"), ("EXCEPTIONS", "GLAND REVIEW - EXCEPTIONS")]),
                ("Lugs", lg_wb, [("LUG SUMMARY", "CABLE LUG SUMMARY"), ("CABLE TYPE SUMMARY", "CABLE LUG BY TYPE"), ("CABLE-WISE DETAIL", "CABLE LUG DETAIL"),
                                 ("LUG PROCUREMENT", "LUG PROCUREMENT"), ("REVIEW - EXCEPTIONS", "LUG REVIEW - EXCEPTIONS")])]
    for section, src, names in sections:
        if src is None:
            continue
        for old, new in names:
            if old not in src.sheetnames:
                continue
            ws = src[old]
            if not _has_data(ws):
                continue                                           # no meaningless empty sheets
            _copy_plain(ws, wb, new[:31])
            index.append({"section": section, "sheet": new[:31], "note": "same layout as the " + ("Gland" if section == "Glands" else "Cable Lug") + " Quantity Generator"})
    # combined exception report
    ws = wb.create_sheet("COMPLETE EXCEPTION REPORT")
    heads = ["MODULE", "SEVERITY", "TAG / CABLE", "SHEET", "FIELD", "ISSUE", "SOURCE VALUE", "EXPECTED VALUE", "RECOMMENDED ACTION"]
    ws.cell(1, 1, "COMPLETE EXCEPTION REPORT").font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    for c in range(1, len(heads) + 1):
        ws.cell(1, c).fill = _HEAD
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(heads))
    for c, h in enumerate(heads, 1):
        cell = ws.cell(3, c, h)
        cell.font, cell.fill, cell.alignment, cell.border = Font(name="Calibri", size=11, bold=True, color="FFFFFF"), _HEAD, _CENTER, _BORDER
    rows = exc_rows or [{"module": "All", "severity": "OK", "ref": "", "sheet": "", "field": "", "issue": "No exceptions", "source_value": "", "expected_value": "", "action": ""}]
    for i, r in enumerate(rows, 4):
        for c, key in enumerate(["module", "severity", "ref", "sheet", "field", "issue", "source_value", "expected_value", "action"], 1):
            cell = ws.cell(i, c, r[key])
            cell.font, cell.alignment, cell.border = Font(name="Calibri", size=11), _CENTER, _BORDER
    for c, w in enumerate([18, 11, 26, 22, 28, 80, 18, 18, 50], 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A4"
    index.append({"section": "Exceptions", "sheet": "COMPLETE EXCEPTION REPORT", "note": f"{len(exc_rows)} item(s)"})
    # cover / index (first sheet)
    cv = wb.create_sheet("COVER - INDEX", 0)
    cv.column_dimensions["A"].width = 34
    cv.column_dimensions["B"].width = 34
    cv.column_dimensions["C"].width = 70
    cv["A1"] = "CABLE SCHEDULE COMPLETE"
    cv["A1"].font = Font(name="Calibri", size=16, bold=True)
    cv["A2"] = f"IODB: {iodb_name}   |   Generated: {datetime.now().strftime('%d.%m.%Y %H:%M')}   |   Status: {v['status']}"
    cv["A2"].font = Font(name="Calibri", size=11, italic=True)
    r = 4
    for label, val in (("Instrument tags", kpis["tags"]), ("Physical cable tags", kpis["cable_tags"]), ("Cable types", kpis["cable_types"]), ("Total cable length (m)", kpis["cable_length"]),
                       ("Total I/O (AI/AO/DI/DO)", kpis["io"]), ("Total glands", kpis["glands"]), ("Total lugs", kpis["lugs"]), ("Exceptions (error/warning/review)", kpis["exceptions"])):
        cv.cell(r, 1, label).font = Font(name="Calibri", size=11, bold=True)
        cv.cell(r, 2, val if val is not None else "n/a").font = Font(name="Calibri", size=11)
        r += 1
    r += 1
    cv.cell(r, 1, "Generation stages").font = Font(name="Calibri", size=12, bold=True)
    r += 1
    for k, _ in STAGES:
        st = stages[k]
        cv.cell(r, 1, st["label"]).font = Font(name="Calibri", size=11)
        cv.cell(r, 2, {"done": "COMPLETE", "warning": "COMPLETE - REVIEW", "failed": "FAILED", "skipped": "SKIPPED"}.get(st["state"], "COMPLETE" if k == "compile" else st["state"].upper()))
        cv.cell(r, 3, st["message"])
        r += 1
    if checks:
        r += 1
        cv.cell(r, 1, "Cross-module consistency").font = Font(name="Calibri", size=12, bold=True)
        r += 1
        for c in checks:
            cv.cell(r, 1, "OK" if c["ok"] else "CHECK")
            cv.cell(r, 2, c["check"])
            cv.cell(r, 3, c["detail"])
            r += 1
    r += 1
    cv.cell(r, 1, "Sheet index").font = Font(name="Calibri", size=12, bold=True)
    r += 1
    for item in index:
        cv.cell(r, 1, item["section"])
        cv.cell(r, 2, item["sheet"])
        cv.cell(r, 3, item["note"])
        r += 1
    for row in cv.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    index.insert(0, {"section": "Cover", "sheet": "COVER - INDEX", "note": ""})
    wb.active = 0
    for w in wb.worksheets:
        w.sheet_view.tabSelected = w.title == "COVER - INDEX"
    buf = io.BytesIO()
    wb.save(buf)
    out = wa.restore_template_fidelity(buf.getvalue(), template, [n for n in wb.sheetnames if n in original_names])
    return out, index
