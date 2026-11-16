"""Glue: Analysis -> final Loop Wiring workbook + generation / traceability report."""
from __future__ import annotations

import io
from typing import Any, Iterable, Optional

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from .analysis import Analysis, LoopResult
from .package import GenLoop, build_workbook, safe_sheet_name


def build_gen_loops(analysis: Analysis, names: Optional[Iterable[str]] = None) -> tuple[list[GenLoop], list[LoopResult]]:
    reg = analysis.registry
    want = set(names) if names is not None else None
    used: set[str] = {"index"}
    out: list[GenLoop] = []
    skipped: list[LoopResult] = []
    for L in analysis.loops:
        if want is not None and L.name not in want:
            continue
        if not L.generate:
            skipped.append(L)
            continue
        tpl = reg.templates[L.typical]
        rows: dict[int, dict[str, Any]] = {s.row: {f: None for f in tpl.columns} for s in tpl.slots}      # clear every placeholder
        for s in L.signals:
            rows[s.slot_row] = {f: s.data_block.get(f) for f in tpl.columns}
        notes = "; ".join(i.text.replace("REVIEW — ", "") for i in L.issues if i.severity == "REVIEW")[:900]
        out.append(GenLoop(safe_sheet_name(L.name, used), tpl, dict(L.loop_fields), rows,
                           {"loop_type": L.loop_type, "spd": L.spd, "term": L.term, "signals": len(L.signals), "status": L.status, "notes": notes}))
    return out, skipped


def generate_workbook(analysis: Analysis, names: Optional[Iterable[str]] = None, source_name: str = "") -> tuple[bytes, dict]:
    loops, skipped = build_gen_loops(analysis, names)
    if not loops:
        raise ValueError("No loop can be generated: every selected loop has an ERROR (or nothing is selected).")
    data, stats = build_workbook(analysis.registry, loops, {"source": source_name, "library": f"{len(analysis.registry.templates)} templates"})
    stats.update(sheets=len(loops), skipped=[{"loop": s.name, "status": s.status, "errors": [i.text for i in s.issues if i.severity == "ERROR"][:5]} for s in skipped],
                 sheet_names={g.loop_fields["LOOP_NAME"]: g.sheet_name for g in loops})
    return data, stats


# ---------------------------------------------------------------------------------------------------------------------
def build_report(analysis: Analysis, generated: Optional[set[str]] = None, source_name: str = "") -> bytes:
    wb = openpyxl.Workbook()
    head = PatternFill("solid", fgColor="2F5597")
    fills = {"PASS": PatternFill("solid", fgColor="C6EFCE"), "REVIEW": PatternFill("solid", fgColor="FFEB9C"), "ERROR": PatternFill("solid", fgColor="FFC7CE")}
    thin = Side(style="thin", color="999999")
    body_font, body_align, body_border = Font(name="Arial", size=10), Alignment(wrap_text=True, vertical="top"), Border(left=thin, right=thin, top=thin, bottom=thin)

    def sheet(title: str, headers: list[str], rows: list[list[Any]], widths: list[int], status_col: Optional[int] = None):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF", name="Arial", size=10)
            c.fill = head
            c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        for r in rows:
            ws.append(r)
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.font, c.alignment, c.border = body_font, body_align, body_border
            if status_col is not None and row[status_col].value in fills:
                row[status_col].fill = fills[row[status_col].value]
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        return ws

    wb.remove(wb.active)
    counts = analysis.counts()
    sheet("SUMMARY", ["ITEM", "VALUE"],
          [["Source I/O Assignment", source_name], ["Sheet read", analysis.source.sheet], ["I/O rows (active)", len(analysis.source.rows)], ["Spare rows (not looped)", analysis.spares],
           ["Loops", len(analysis.loops)], ["PASS", counts["PASS"]], ["REVIEW", counts["REVIEW"]], ["ERROR (not generated)", counts["ERROR"]],
           ["Generated", len(generated) if generated is not None else sum(1 for l in analysis.loops if l.generate)],
           ["Template library", "complete - 42 / 42" if analysis.registry.complete else "INCOMPLETE: " + ", ".join(analysis.registry.missing + analysis.registry.problems)]],
          [34, 60])
    sheet("GENERATION LOG", ["LOOP", "SIGNAL", "TAG", "IO TYPE", "SOURCE ROW", "LOOP TYPE", "SPD", "TERM", "CALCULATED TYPICAL", "TEMPLATE", "MAPPED FIELDS", "STATUS", "WHY THIS TEMPLATE"],
          [[L.name, s.sig, s.tag, s.io_type, s.source_row, L.loop_type, L.spd, L.term, L.typical, L.template, sum(1 for m in s.mapping if m["state"] in ("MAPPED", "DERIVED")), s.status,
            f"LOOP_TYPE {L.loop_type} (no. {dict(analysis.registry.loop_types).get(L.loop_type)}) + SPD_ARR {L.spd} + '-' + TERM_ARR {L.term} = {L.typical}"]
           for L in analysis.loops for s in L.signals] +
          [[L.name, "", "", "", ", ".join(map(str, L.rows)), L.loop_type, L.spd, L.term, L.typical, L.template or "", 0, L.status, "loop not generated: " + "; ".join(i.code for i in L.issues if i.severity == "ERROR")[:300]]
           for L in analysis.loops if not L.signals],
          [18, 8, 18, 8, 10, 12, 6, 6, 12, 34, 10, 10, 60], 11)
    sheet("FIELD CODE MAPPING", ["LOOP", "SIGNAL", "TAG", "FIELD CODE (DESTINATION)", "SOURCE FIELD CODE", "SOURCE VALUE", "DESTINATION CELL", "STATE", "NOTE"],
          [[L.name, s.sig, s.tag, m["field"], m["source"], m["value"], m["destination"].split("· ")[-1], m["state"], m["note"]] for L in analysis.loops for s in L.signals for m in s.mapping],
          [18, 8, 18, 22, 18, 26, 12, 16, 50])
    sheet("MAPPING REPORT", ["LOOP", "MAPPED FIELDS", "MISSING REQUIRED", "UNUSED SOURCE FIELDS", "TEMPLATE FIELDS WITHOUT SOURCE"],
          [[L.name, L.report.get("mapped", 0), "; ".join(f"{x['sig']} {x['field']}" for x in L.report.get("missing_required", [])),
            "; ".join(sorted({x["code"] for x in L.report.get("unused_source", [])})), ", ".join(L.report.get("template_without_source", []))] for L in analysis.loops],
          [18, 12, 40, 60, 50])
    sheet("VALIDATION", ["LOOP", "SEVERITY", "CODE", "DETAIL", "ROWS", "FIELD CODE", "SIGNAL"],
          [[i.loop, i.severity, i.code, i.detail, ", ".join(map(str, i.rows)), i.field, i.sig] for L in analysis.loops for i in L.issues] +
          [[i.loop, i.severity, i.code, i.detail, ", ".join(map(str, i.rows)), i.field, i.sig] for i in analysis.global_issues],
          [18, 10, 36, 90, 16, 16, 8], 1)
    sheet("TRACE", ["LOOP", "SIGNAL", "TAG", "SIDE", "NODE", "ID", "TERMINALS", "PRESENT", "BROKEN"],
          [[L.name, s.sig, s.tag, n["side"], n["node"], n["id"], ", ".join(f"{k}={v}" for k, v in n["terminals"].items()), "yes" if n["present"] else "no", "BROKEN" if n["broken"] else ""]
           for L in analysis.loops for s in L.signals for n in (s.trace.get("nodes", []) + s.trace.get("power", []))],
          [18, 8, 18, 9, 22, 22, 50, 9, 9])
    sheet("CONDUCTORS", ["LOOP", "SIGNAL", "TAG", "CONDUCTOR", "PATH (device → system)"],
          [[L.name, s.sig, s.tag, c["role"], " → ".join(c["path"])] for L in analysis.loops for s in L.signals for c in s.trace.get("conductors", [])], [18, 8, 18, 26, 80])
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()
