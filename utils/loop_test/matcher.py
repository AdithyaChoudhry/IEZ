"""
Tag matching, conflict detection and the merged, source-tagged data for one tag.

Matching hierarchy (never fuzzy first):
  1. exact TAG NO   2. normalised TAG NO   3. exact LOOP NUMBER   4. normalised LOOP NUMBER
Loop-number matches and fuzzy look-alikes are only ever SUGGESTIONS: they stay REVIEW REQUIRED
until the engineer accepts them. Conflicting values are never resolved silently.
"""
from __future__ import annotations

import difflib
import re
from collections import defaultdict
from typing import Any, Optional

from .common import IO, IODB, USER, clean, is_value, norm_tag
from .io_assignment import io_class

STATUSES = ("MATCHED", "IO NOT FOUND", "IODB NOT FOUND", "CONFLICT", "DUPLICATE", "REVIEW REQUIRED")
FUZZY_CUTOFF = 0.88


def _wire_count(text: str) -> str:
    m = re.search(r"\b(\d)\s*[- ]?\s*WIRE", clean(text).upper())
    return m.group(1) if m else ""


def detect_conflicts(iodb_rows: list[dict], io_rows: list[dict]) -> list[dict]:
    """Differences between the two documents that need an engineer decision."""
    out: list[dict] = []
    if not iodb_rows or not io_rows:
        return out

    iodb_cls = {io_class(r.get("SIGNAL_IO_TYPE", "")) for r in iodb_rows} - {""}
    io_cls = {io_class(r["fields"].get("IO_TYPE", "")) for r in io_rows} - {""}
    if iodb_cls and io_cls and iodb_cls != io_cls:
        out.append({"field": "SIGNAL_TYPE", "label": "Signal type", "severity": "error",
                    "iodb": "/".join(sorted(iodb_cls)), "io": "/".join(sorted(io_cls))})

    jb_iodb = {norm_tag(r.get("JB_TAG", "")) for r in iodb_rows if is_value(r.get("JB_TAG", ""))}
    jb_io = {norm_tag(r["fields"].get("JB_NO", "")) for r in io_rows if is_value(r["fields"].get("JB_NO", ""))}
    if jb_iodb and jb_io and jb_iodb != jb_io:
        out.append({"field": "JB_TAG", "label": "Junction box", "severity": "error",
                    "iodb": ", ".join(sorted({r.get("JB_TAG", "") for r in iodb_rows if is_value(r.get("JB_TAG", ""))})),
                    "io": ", ".join(sorted({r["fields"].get("JB_NO", "") for r in io_rows if is_value(r["fields"].get("JB_NO", ""))}))})

    w_iodb = {_wire_count(r.get("WIRE_TYPE", "")) for r in iodb_rows} - {""}
    w_io = {_wire_count(r["fields"].get("WIRE_TYPE", "")) for r in io_rows} - {""}
    if w_iodb and w_io and w_iodb != w_io:
        out.append({"field": "WIRE_TYPE", "label": "2-wire / 4-wire", "severity": "warning",
                    "iodb": "/".join(sorted(w_iodb)) + " wire", "io": "/".join(sorted(w_io)) + " wire"})

    l_iodb = {norm_tag(r.get("LOOP_NO", "")) for r in iodb_rows if is_value(r.get("LOOP_NO", ""))}
    l_io = {norm_tag(r.get("loop", "")) for r in io_rows if is_value(r.get("loop", ""))}
    if l_iodb and l_io and l_iodb != l_io:
        out.append({"field": "LOOP_NO", "label": "Loop number", "severity": "warning",
                    "iodb": ", ".join(sorted({r.get("LOOP_NO", "") for r in iodb_rows})),
                    "io": ", ".join(sorted({r.get("loop", "") for r in io_rows}))})
    return out


def _is_true_duplicate(iodb_rows: list[dict], io_rows: list[dict]) -> bool:
    """Same tag more than once with identical key attributes (not a multi-signal loop)."""
    if len(iodb_rows) > 1:
        keys = [(r.get("SIGNAL_IO_TYPE", ""), r.get("SIGNAL_DESCRIPTION", "")) for r in iodb_rows]
        if len(set(keys)) < len(keys):
            return True
    if len(io_rows) > 1:
        keys = [tuple(r["fields"].get(f, "") for f in ("RACK", "SLOT", "CHANNEL", "IO_TYPE", "MODULE")) for r in io_rows]
        if len(set(keys)) < len(keys):
            return True
    return False


def match_all(iodb_rows: list[dict], io_rows: list[dict], decisions: Optional[dict] = None) -> dict:
    """
    Returns {"entries": [...], "summary": {...}}. `decisions` = {"suggestions": {io_tag: {"iodb_tag", "action"}},
    "conflicts": {tag: {field: "iodb" | "io"}}}.
    """
    decisions = decisions or {}
    sugg_dec: dict = decisions.get("suggestions", {})
    conf_dec: dict = decisions.get("conflicts", {})

    iodb_by_tag: dict[str, list[int]] = defaultdict(list)
    iodb_by_norm: dict[str, list[int]] = defaultdict(list)
    iodb_by_loop: dict[str, list[int]] = defaultdict(list)
    iodb_by_nloop: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(iodb_rows):
        iodb_by_tag[r["TAG_NO"]].append(i)
        iodb_by_norm[norm_tag(r["TAG_NO"])].append(i)
        if is_value(r.get("LOOP_NO", "")):
            iodb_by_loop[r["LOOP_NO"]].append(i)
            iodb_by_nloop[norm_tag(r["LOOP_NO"])].append(i)

    io_groups: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(io_rows):
        if not r["is_spare"]:
            io_groups[r["tag"]].append(i)

    entries: list[dict] = []
    used_iodb_tags: set[str] = set()

    for io_tag, io_idx in io_groups.items():
        rows_io = [io_rows[i] for i in io_idx]
        loop = next((r["loop"] for r in rows_io if r["loop"]), "")
        method, iodb_idx, suggestion = "", [], None

        if io_tag in iodb_by_tag:
            method, iodb_idx = "exact tag", iodb_by_tag[io_tag]
        elif norm_tag(io_tag) in iodb_by_norm:
            method, iodb_idx = "normalised tag", iodb_by_norm[norm_tag(io_tag)]
        else:
            # weaker evidence -> suggestion only
            cand = iodb_by_loop.get(loop) or iodb_by_nloop.get(norm_tag(loop)) if loop else None
            tags = sorted({iodb_rows[i]["TAG_NO"] for i in cand}) if cand else []
            if len(tags) == 1:
                suggestion = {"iodb_tag": tags[0], "method": "loop number", "score": 1.0}
            else:
                near = difflib.get_close_matches(norm_tag(io_tag), list(iodb_by_norm), n=1, cutoff=FUZZY_CUTOFF)
                if near:
                    suggestion = {"iodb_tag": iodb_rows[iodb_by_norm[near[0]][0]]["TAG_NO"], "method": "similar tag",
                                  "score": round(difflib.SequenceMatcher(None, norm_tag(io_tag), near[0]).ratio(), 3)}
            dec = sugg_dec.get(io_tag)
            if suggestion and dec and dec.get("action") == "accept" and dec.get("iodb_tag") == suggestion["iodb_tag"]:
                method, iodb_idx = f"{suggestion['method']} (engineer-approved)", iodb_by_tag[suggestion["iodb_tag"]]
                suggestion = None
            elif suggestion and dec and dec.get("action") == "reject" and dec.get("iodb_tag") == suggestion["iodb_tag"]:
                suggestion = None

        if iodb_idx:
            rows_iodb = [iodb_rows[i] for i in iodb_idx]
            tag = rows_iodb[0]["TAG_NO"]
            used_iodb_tags.add(tag)
            conflicts = detect_conflicts(rows_iodb, rows_io)
            decided = conf_dec.get(tag, {})
            for c in conflicts:
                c["decision"] = decided.get(c["field"])
            open_errors = [c for c in conflicts if c["severity"] == "error" and not c["decision"]]
            if _is_true_duplicate(rows_iodb, rows_io):
                status = "DUPLICATE"
            elif open_errors:
                status = "CONFLICT"
            else:
                status = "MATCHED"
            entries.append({"tag": tag, "loop": rows_iodb[0].get("LOOP_NO") or loop, "status": status, "method": method,
                            "in_iodb": True, "in_io": True, "iodb_idx": iodb_idx, "io_idx": io_idx,
                            "io_tag": io_tag, "conflicts": conflicts, "suggestions": [],
                            "signals": max(len(rows_io), 1)})
        else:
            entries.append({"tag": io_tag, "loop": loop, "status": "REVIEW REQUIRED" if suggestion else "IODB NOT FOUND",
                            "method": "", "in_iodb": False, "in_io": True, "iodb_idx": [], "io_idx": io_idx,
                            "io_tag": io_tag, "conflicts": [], "suggestions": [suggestion] if suggestion else [],
                            "signals": len(rows_io)})

    # IODB tags nobody assigned
    seen_iodb: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(iodb_rows):
        if r["TAG_NO"] not in used_iodb_tags:
            seen_iodb[r["TAG_NO"]].append(i)
    for tag, idx in seen_iodb.items():
        first = iodb_rows[idx[0]]
        entries.append({"tag": tag, "loop": first.get("LOOP_NO", ""), "status": "IO NOT FOUND", "method": "",
                        "in_iodb": True, "in_io": False, "iodb_idx": idx, "io_idx": [], "io_tag": "",
                        "conflicts": [], "suggestions": [], "signals": len(idx)})

    counts = {s: sum(1 for e in entries if e["status"] == s) for s in STATUSES}
    summary = {
        "iodb_tags": len({r["TAG_NO"] for r in iodb_rows}),
        "io_assignment_tags": len(io_groups),
        "matched": counts["MATCHED"],
        "not_matched": counts["IO NOT FOUND"] + counts["IODB NOT FOUND"],
        "conflicts": counts["CONFLICT"],
        "duplicates": counts["DUPLICATE"],
        "review_required": counts["REVIEW REQUIRED"],
        "warnings": sum(1 for e in entries for c in e["conflicts"] if c["severity"] == "warning"),
        "by_status": counts,
    }
    # tags that exist in BOTH documents (and need attention) first; IODB-only tags last
    priority = {"CONFLICT": 0, "REVIEW REQUIRED": 1, "DUPLICATE": 2, "MATCHED": 3, "IODB NOT FOUND": 4, "IO NOT FOUND": 5}
    entries.sort(key=lambda e: (priority.get(e["status"], 9), e["tag"]))
    return {"entries": entries, "summary": summary}


# ── merged, source-tagged view of one tag ───────────────────────────────────
IODB_FIELDS_SHOWN = [
    ("TAG_NO", "Tag"), ("LOOP_NO", "Loop"), ("INSTRUMENT_TYPE", "Instrument type"), ("MEASURING_TYPE", "Measuring type"),
    ("SIGNAL_IO_TYPE", "Signal (I/O type)"), ("POWER_SUPPLY", "Power supply"), ("WIRE_TYPE", "2/4 wire"),
    ("JB_TAG", "Junction box"), ("JB_TERMINAL_PLUS", "JB terminal +"), ("JB_TERMINAL_MINUS", "JB terminal -"),
    ("BRANCH_CABLE_TAG", "Branch cable tag"), ("BRANCH_CABLE_TYPE", "Branch cable type"),
    ("BRANCH_CABLE_LENGTH", "Branch cable length"), ("BRANCH_FERRULE", "Branch ferrule"), ("ROUTE_NUMBER", "Route"),
    ("JB_GLAND_SIZE", "JB-side gland"), ("MAIN_CABLE_TAG", "Main cable tag"), ("MAIN_CABLE_TYPE", "Main cable type"),
    ("MAIN_CABLE_LENGTH", "Main cable length"), ("MAIN_CABLE_FERRULE", "Main cable ferrule"),
    ("IS_NIS", "IS / NIS"), ("HART", "HART"), ("FIELD_POWER_LOAD", "Field power load"), ("ZENER_BARRIER", "Zener barrier"),
    ("REDUNDANT_IO", "Redundant I/O"), ("FAIL_ACTION", "Fail action"), ("REMARKS", "Remarks"),
]
IO_FIELDS_SHOWN = [
    ("PLC", "PLC / DCS"), ("RACK", "Rack / node"), ("SLOT", "Slot"), ("MODULE", "Module"), ("CHANNEL", "Channel"),
    ("IO_TYPE", "I/O type"), ("TERMINAL_STRIP", "Terminal strip"), ("TERMINAL", "Terminal"), ("TERMINAL_CMN", "Terminal CMN"),
    ("TERMINAL_SIGNAL", "Terminal signal"), ("TERMINAL_ZERO", "Terminal zero"), ("ADDRESS", "Address"),
    ("JB_TB1", "JB TB1"), ("JB_TB2", "JB TB2"), ("JB_TB3", "JB TB3"), ("JB_PAIR", "JB pair"),
]


def merged_tag_data(entry: dict, iodb_rows: list[dict], io_rows: list[dict], decisions: Optional[dict] = None,
                    overrides: Optional[dict] = None) -> dict:
    """
    {"fields": {name: {"value","source","label"}}, "signals": [per I/O row details], "conflicts": [...]}.
    A value is never silently replaced by another source: conflicts follow the engineer's decision;
    USER overrides only apply to fields the engineer explicitly set.
    """
    decisions = decisions or {}
    overrides = overrides or {}
    tag = entry["tag"]
    first_iodb = iodb_rows[entry["iodb_idx"][0]] if entry["iodb_idx"] else {}
    rows_io = [io_rows[i] for i in entry["io_idx"]]
    first_io = rows_io[0]["fields"] if rows_io else {}
    decided = decisions.get("conflicts", {}).get(tag, {})

    fields: dict[str, dict] = {}
    for key, label in IODB_FIELDS_SHOWN:
        v = first_iodb.get(key, "")
        if key in ("TAG_NO",):
            v = v or entry["tag"]
        fields[key] = {"value": v, "source": IODB, "label": label, "available": key in first_iodb}
    for key, label in IO_FIELDS_SHOWN:
        fields[key] = {"value": first_io.get(key, ""), "source": IO, "label": label,
                       "available": bool(rows_io) and key in first_io}

    # fields that exist in both documents: JB tag, wire type, loop number
    for key, io_key, io_label in (("JB_TAG", "JB_NO", "Junction box"), ("WIRE_TYPE", "WIRE_TYPE", "2/4 wire"),
                                  ("LOOP_NO", "LOOP_NO", "Loop")):
        iodb_v = first_iodb.get(key, "")
        io_v = first_io.get(io_key, "") if io_key != "LOOP_NO" else (rows_io[0]["loop"] if rows_io else "")
        c = next((c for c in entry["conflicts"] if c["field"] == key), None)
        choice = decided.get(key)
        if c and choice == "io":
            fields[key] = {"value": io_v, "source": IO, "label": io_label, "available": True, "resolved_by": "engineer"}
        elif c and choice == "iodb":
            fields[key] = {"value": iodb_v, "source": IODB, "label": io_label, "available": True, "resolved_by": "engineer"}
        elif not is_value(iodb_v) and is_value(io_v):
            fields[key] = {"value": io_v, "source": IO, "label": io_label, "available": True}
        # else IODB value stays (identical, or IODB-owned)

    for key, value in overrides.items():
        if key in fields and clean(value):
            fields[key] = {"value": clean(value), "source": USER, "label": fields[key]["label"], "available": True}

    signals = []
    for r in rows_io:
        f = r["fields"]
        signals.append({"io_type": f.get("IO_TYPE", ""), "rack": f.get("RACK", ""), "slot": f.get("SLOT", ""),
                        "module": f.get("MODULE", ""), "channel": f.get("CHANNEL", ""), "plc": f.get("PLC", ""),
                        "terminal_strip": f.get("TERMINAL_STRIP", ""), "terminal": f.get("TERMINAL", ""),
                        "terminal_cmn": f.get("TERMINAL_CMN", ""), "terminal_signal": f.get("TERMINAL_SIGNAL", ""),
                        "terminal_zero": f.get("TERMINAL_ZERO", ""), "address": f.get("ADDRESS", ""),
                        "description": f.get("DESCRIPTION", "") or f.get("SERVICE", ""), "source": IO,
                        "sheet": r["sheet"], "row": r["row"]})
    return {"fields": fields, "signals": signals, "conflicts": entry["conflicts"]}
