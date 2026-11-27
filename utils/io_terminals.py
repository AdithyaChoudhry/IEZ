"""
Terminal details from the Standard I/O Assignment for the MCC DI / MCC DO / VFD / MOV / LCP cable schedule sheets.

Only the IO_ASSIGNMENT worksheet is read, by its column headings. Every signal is matched on its own TAG NUMBER (case and
spaces ignored, nothing else), narrowed by I/O type, signal description and loop only when a tag has several records. A value
is written only for the physical endpoint it describes:

  equipment side  (TB details at MCC / VFD / MOV / LCP)  <- DEVICE TERMINAL BLOCK / DEVICE TERMINAL 1 / 2
  panel side      (MOV control desk terminals)           <- nothing, unless the engineer confirms the field terminal strip

The engineer may confirm that the field terminal strip (TS, TS TERMINAL 1 / 2) is the endpoint instead. Spare channels are
ignored, a value the IODB already holds is never overwritten, and conflicting records are reported, never picked from.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import openpyxl

SHEET = "IOASSIGNMENT"
FIELDS = {    # field -> headings that mean it (compared without case, spaces and punctuation)
    "tag": ["TAG NUMBER", "TAG NO"], "loop": ["LOOP NO", "LOOP NAME", "LOOP NUMBER"], "signal": ["SIGNAL DESCRIPTION"],
    "io": ["IO TYPE", "I/O TYPE"], "status": ["STATUS", "ASSIGNMENT STATUS"],
    "dev_tb": ["DEVICE TERMINAL BLOCK"], "dev_t1": ["DEVICE TERMINAL 1 (+ / SIG)"], "dev_t2": ["DEVICE TERMINAL 2 (- / CMN)"],
    "ts": ["FIELD TERMINAL STRIP (TS)", "TERMINAL STRIP NO", "TERMINAL STRIP NUMBER"],
    "ts1": ["TS TERMINAL 1 (+ / SIG)", "TERMINAL NO (SIGNAL)", "TERMINAL NO. SIGNAL"],
    "ts2": ["TS TERMINAL 2 (- / CMN)", "TERMINAL NO (CMN)", "TERMINAL NO. COMM", "TERMINAL NO CMN"],
    "panel": ["SYSTEM CABINET / IO PANEL", "PANEL NO"], "rack": ["RACK / NODE (CRATE)", "RACK NO"], "slot": ["SLOT", "SLOT NO"],
    "module": ["MODULE NO", "MODULE NO."], "channel": ["CHANNEL NO", "CHANNEL NO."], "remarks": ["REMARKS"],
}
TERMINALS = ("dev_tb", "dev_t1", "dev_t2", "ts", "ts1", "ts2")
SPARE_STATUS = {"SPARE", "SPR", "UNALLOCATED", "NOTUSED", "FREE"}
IO_NAMES = {"DIGITALINPUT": "DI", "DIGITALOUTPUT": "DO", "ANALOGINPUT": "AI", "ANALOGOUTPUT": "AO"}
EQUIPMENT_SOURCES = {"device": ("dev_tb", "dev_t1", "dev_t2"), "ts": ("ts", "ts1", "ts2")}
PANEL_SOURCES = ("none", "ts")
SHEETS_WITH_MTB = {"mcc_di", "mcc_do", "vfd", "lcp"}
SHEETS_WITH_PANEL = {"mov"}                                  # the only sheet with panel-side terminal columns
DESTINATIONS = {"end_mtb": ("MTB No", "equipment-side terminal block"), "end_pos": ("Positive Core", "equipment side (+)"),
                "end_neg": ("Negative Core", "equipment side (-)"),
                "cd_pos": ("Control Desk Positive", "control desk / panel side (+)"),
                "cd_neg": ("Control Desk Negative", "control desk / panel side (-)")}
_MISSING = {"", "TBA", "TBD", "TBC", "-", "--", "NA", "N/A", "NIL", "NONE", "XXXX", "?"}


class AssignmentError(ValueError):
    """A problem with the uploaded I/O Assignment that the user can correct."""


def _norm(v: Any) -> str:
    return re.sub(r"[^A-Z0-9+\-]", "", str(v).upper())


def _head(v: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(v).upper().replace("+", " PLUS ").replace("-", " MINUS "))


def _text(v: Any) -> str:
    """A cell as the identifier it is: leading zeros and letters kept, 12.0 shown as 12."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v).replace("\xa0", " ")).strip()


def tag_key(v: Any) -> str:
    return re.sub(r"\s+", "", _text(v)).upper()


def _io(v: Any) -> str:
    n = re.sub(r"[^A-Z]", "", _text(v).upper())
    return IO_NAMES.get(n, n)


def _have(v: Any) -> bool:
    return _text(v).upper() not in _MISSING


@dataclass
class Assignment:
    records: dict[str, list[dict]] = field(default_factory=dict)      # tag key -> used records
    used: int = 0
    spare: int = 0
    columns: dict[str, str] = field(default_factory=dict)             # field -> heading found
    warnings: list[str] = field(default_factory=list)


def read_assignment(data: bytes) -> Assignment:
    try:
        values = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        formulas = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    except Exception as exc:
        raise AssignmentError("The I/O Assignment could not be opened. Upload an Excel .xlsx workbook.") from exc
    try:
        name = next((n for n in values.sheetnames if re.sub(r"[^A-Z]", "", n.upper()) == SHEET), None)
        if name is None:
            raise AssignmentError("The I/O Assignment has no 'IO_ASSIGNMENT' worksheet (the standard template's data sheet). "
                                  f"Sheets found: {', '.join(values.sheetnames[:10])}.")
        wanted = {_head(a): f for f, aliases in FIELDS.items() for a in aliases}
        header_row, columns, headings = 0, {}, {}
        for r, row in enumerate(values[name].iter_rows(min_row=1, max_row=40, values_only=True), start=1):
            found, names = {}, {}
            for c, cell in enumerate(row):
                f = wanted.get(_head(cell)) if cell not in (None, "") else None
                if f and f not in found:
                    found[f], names[f] = c, _text(cell)
            if "tag" in found and len(found) >= 4 and len(found) > len(columns):
                header_row, columns, headings = r, found, names
        if not columns:
            raise AssignmentError("No heading row with 'TAG NUMBER' and the terminal columns was found on IO_ASSIGNMENT.")
        if not any(f in columns for f in TERMINALS):
            raise AssignmentError("IO_ASSIGNMENT has no terminal columns (device terminals or field terminal strip).")
        out = Assignment(columns=headings)
        uncalculated = 0
        raw_rows = formulas[name].iter_rows(min_row=header_row + 1, values_only=True)
        for r, (row, raw) in enumerate(zip(values[name].iter_rows(min_row=header_row + 1, values_only=True), raw_rows),
                                       start=header_row + 1):
            rec = {f: _text(row[c]) if c < len(row) else "" for f, c in columns.items()}
            for f in TERMINALS:
                c = columns.get(f)
                if c is not None and c < len(raw) and isinstance(raw[c], str) and raw[c].startswith("=") and not rec.get(f):
                    uncalculated += 1
            key = tag_key(rec.get("tag"))
            status = re.sub(r"[^A-Z]", "", rec.get("status", "").upper())
            if not key and not status and not any(rec.get(f) for f in TERMINALS):
                continue                                                      # an empty template row
            if status in SPARE_STATUS or not key or key.startswith("SPARE") or key in _MISSING:
                out.spare += 1
                continue
            rec["row"] = r
            out.records.setdefault(key, []).append(rec)
            out.used += 1
    finally:
        values.close()
        formulas.close()
    if not out.used:
        raise AssignmentError("IO_ASSIGNMENT has no used signal rows (every row is spare or has no tag number).")
    if uncalculated:
        out.warnings.append(f"{uncalculated} terminal cell(s) hold formulas without a saved result and read as blank. Open the "
                            "I/O Assignment in Excel, let it calculate, save it and upload it again.")
    return out


def clean_options(raw: Optional[dict]) -> dict:
    o = {"equipment": "device", "panel": "none", **{k: v for k, v in (raw or {}).items() if v}}
    if set(o) != {"equipment", "panel"} or o["equipment"] not in EQUIPMENT_SOURCES or o["panel"] not in PANEL_SOURCES:
        raise AssignmentError("The terminal source selection is not valid.")
    return o


class Matcher:
    """Applies the assignment to the rows of the extra sheets and keeps the counts of what happened."""

    def __init__(self, assignment: Assignment, options: Optional[dict] = None):
        self.a = assignment
        self.options = clean_options(options)
        self.sheets: dict[str, dict] = {}
        self.trace: list[dict] = []                      # one entry per destination field (or per signal not filled)

    def _stats(self, key: str) -> dict:
        return self.sheets.setdefault(key, {"eligible": 0, "resolved": 0, "partial": 0, "unmatched": 0, "conflicts": 0,
                                            "equipment_available": 0, "panel_available": 0, "issues": []})

    def find(self, tag: Any, io_type: str, signal: Any, loop: Any) -> tuple[Optional[dict], str]:
        """-> (record, '') | (None, '') unmatched | (None, reason) conflicting."""
        found = self.a.records.get(tag_key(tag), [])
        if not found:
            return None, ""
        for value, of in ((_io(io_type), lambda r: _io(r.get("io"))), (_norm(signal or ""), lambda r: _norm(r.get("signal", ""))),
                          (_norm(loop or ""), lambda r: _norm(r.get("loop", "")))):
            if len(found) > 1 and value:
                narrowed = [r for r in found if of(r) == value]
                found = narrowed or found
        io_a, io_b = _io(io_type), {_io(r.get("io")) for r in found} - {""}
        if io_a and io_b and io_a not in io_b:
            return None, f"IO type differs (IODB {io_a}, I/O Assignment {'/'.join(sorted(io_b))})"
        if len({tuple(r.get(f, "") for f in TERMINALS) for r in found}) > 1:
            return None, "the I/O Assignment has different terminals for this signal (rows " + \
                         ", ".join(str(r["row"]) for r in found[:4]) + ")"
        return found[0], ""

    def apply(self, sheet: str, rec, values: dict) -> None:
        """Fill the terminal values of one signal row (`values`: the cell values about to be written)."""
        tag = rec.tag_no
        if not tag_key(tag) or tag_key(tag) in _MISSING or tag_key(tag).startswith("SPARE"):
            return
        st = self._stats(sheet)
        st["eligible"] += 1
        found, conflict = self.find(tag, rec.io, rec.signal_description, rec.loop_number)

        def issue(text):
            if len(st["issues"]) < 200:
                st["issues"].append(f"{tag}: {text}")

        def note(result, target=None, source=None, value="", row=None):
            field_name, endpoint = DESTINATIONS.get(target, ("", ""))
            self.trace.append({"tag": tag, "iodb_row": rec.row, "sheet": sheet, "field": field_name, "endpoint": endpoint,
                               "source_row": row, "source_column": self.a.columns.get(source, source or ""), "value": value,
                               "result": result})

        if conflict:
            st["conflicts"] += 1
            issue(conflict)
            note(f"Conflict - not filled: {conflict}")
            return
        if found is None:
            st["unmatched"] += 1
            note("Unmatched - no I/O Assignment record for this tag")
            return
        block, t1, t2 = EQUIPMENT_SOURCES[self.options["equipment"]]
        targets = [("end_pos", t1), ("end_neg", t2)] + ([("end_mtb", block)] if sheet in SHEETS_WITH_MTB else [])
        if sheet in SHEETS_WITH_PANEL and self.options["panel"] == "ts":
            targets += [("cd_pos", "ts1"), ("cd_neg", "ts2")]
        st["equipment_available"] += bool(_have(found.get(t1)) and _have(found.get(t2)))
        st["panel_available"] += bool(_have(found.get("ts1")) and _have(found.get("ts2")))
        clash = False
        for target, source in targets:
            new = found.get(source, "")
            if not _have(new):
                note("Not filled - the I/O Assignment has no value", target, source, new, found["row"])
                continue
            old = _text(values.get(target))
            if _have(old) and old.upper() != new.upper():
                clash = True
                issue(f"the IODB has '{old}' and the I/O Assignment '{new}' ({self.a.columns.get(source, source)}); "
                      "the IODB value is kept")
                note(f"Conflict - IODB value '{old}' kept", target, source, new, found["row"])
            else:
                note("Same as the IODB value" if _have(old) else "Filled", target, source, new, found["row"])
                values[target] = new
        cores = _have(values.get("end_pos")) and _have(values.get("end_neg"))
        if clash:
            st["conflicts"] += 1
        elif cores and (sheet not in SHEETS_WITH_MTB or _have(values.get("end_mtb"))):
            st["resolved"] += 1
        else:
            st["partial"] += 1

    def report(self, labels: dict[str, str]) -> dict:
        keys = ("eligible", "resolved", "partial", "unmatched", "conflicts", "equipment_available", "panel_available")
        sheets = [{"sheet": labels.get(k, k), **v} for k, v in self.sheets.items()]
        total = {k: sum(s[k] for s in sheets) for k in keys}
        warnings = list(self.a.warnings)
        if total["eligible"] and not total["equipment_available"] and self.options["equipment"] == "device":
            warnings.append("The I/O Assignment gives no equipment-side (device) terminals for these signals, so the TB details "
                            "at the equipment stay unresolved. Its field terminal strip is a panel-side terminal; select it only "
                            "if you have confirmed that those are the equipment's terminals.")
        for s in sheets:
            if s["conflicts"]:
                warnings.append(f"{s['sheet']}: {s['conflicts']} signal(s) have conflicting terminal information - review "
                                f"(for example {s['issues'][0]}).")
        return {"assignment": {"used": self.a.used, "spare_ignored": self.a.spare, "columns": self.a.columns},
                "options": self.options, "total": total, "sheets": sheets, "warnings": warnings}
