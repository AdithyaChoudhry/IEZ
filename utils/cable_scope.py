"""
Engineering scope of a Cable Schedule: AREA, AREA CODE and tag STATUS filters on the IODB rows.

The IODB table is filtered before anything is built from it, so every worksheet and the Cable Summary describe the same
records. Nothing in the uploaded file is changed and nothing is assumed about a status beyond its own words:

  deleted   the status says deleted ('DELETED', 'deleted', 'Deleted in Rev 1' ...)      excluded unless selected
  current   one of the plain current-tag words in CURRENT                                 included
  blank     no status written                                                             included, shown for review
  unknown   anything else (including abbreviations such as D, DEL or X)                   included, shown for review

A selection of None means the default; an empty list is a mistake and is reported.
"""
from __future__ import annotations

import io
import math
import re
from typing import Any, Optional

import pandas as pd

BLANK = "(Blank)"
HEADINGS = {"area": ("AREA", "AREA NAME", "PLANT AREA"), "area_code": ("AREA CODE",),
            "status": ("STATUS", "CURRENT STATUS", "TAG STATUS")}
CURRENT = {"ACTIVE", "EXISTING", "NEW", "NEWLY ADDED", "ADDED", "REVISED", "MODIFIED", "APPROVED", "ISSUED"}
CATEGORY_LABELS = {"current": "Current", "deleted": "Deleted", "blank": "Blank / unspecified (review)",
                   "unknown": "Unknown status (review)"}
_NO_VALUE = {"", "-", "TBA", "NA", "N/A", "NIL", "NAN", "NONE", "TBD", "XXXX"}


class ScopeError(ValueError):
    """A filter selection the user has to correct."""


def text(v: Any) -> str:
    """A cell as shown: leading zeros of text codes kept; a number such as 100.0 is shown as 100; blank -> (Blank)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return BLANK
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    t = re.sub(r"\s+", " ", str(v).replace("\xa0", " ")).strip()
    return t or BLANK


def key(v: Any) -> str:
    return text(v).upper()


def category(status_key: str) -> str:
    if status_key == BLANK.upper():
        return "blank"
    if re.match(r"DELETED?\b", status_key):
        return "deleted"
    return "current" if status_key in CURRENT else "unknown"


def find_columns(columns) -> dict[str, Optional[str]]:
    """filter -> the IODB heading it uses (exact heading words only: 'AREA CLASSIFICATION' is not an area)."""
    norm: dict[str, str] = {}
    for c in columns:
        norm.setdefault(re.sub(r"[^A-Z0-9]+", " ", str(c).upper()).strip(), c)
    return {f: next((norm[a] for a in names if a in norm), None) for f, names in HEADINGS.items()}


def parse(raw: Optional[dict]) -> dict[str, Optional[list[str]]]:
    """The request's selection -> {"areas", "area_codes", "statuses"}: None (default) or upper-case keys."""
    raw = raw or {}
    unknown = set(raw) - {"areas", "area_codes", "statuses"}
    if unknown:
        raise ScopeError("Invalid filter selection.")
    out: dict[str, Optional[list[str]]] = {}
    for name, label in (("areas", "area"), ("area_codes", "area code"), ("statuses", "tag status")):
        v = raw.get(name)
        if v is None:
            out[name] = None
            continue
        if not isinstance(v, list) or len(v) > 500 or not all(isinstance(x, (str, int, float)) for x in v):
            raise ScopeError(f"Invalid {label} selection.")
        if not v:
            raise ScopeError(f"No {label} is selected. Select at least one, or reset the filters to include all.")
        out[name] = list(dict.fromkeys(key(x) for x in v))
    return out


class Scope:
    """A validated selection against one IODB table; `apply` filters that table or any table with the same headings."""

    def __init__(self, df: pd.DataFrame, selection: Optional[dict] = None):
        self.selection = parse(selection)
        self.columns = find_columns(df.columns)
        self.values = {f: [text(v) for v in df[c]] if c else None for f, c in self.columns.items()}
        for name, f, label in (("areas", "area", "AREA"), ("area_codes", "area_code", "AREA CODE"), ("statuses", "status", "STATUS")):
            chosen = self.selection[name]
            if chosen is None:
                continue
            if not self.columns[f]:
                raise ScopeError(f"This IODB has no {label} column, so it cannot be filtered by it.")
            present = {v.upper() for v in self.values[f]}
            missing = [c for c in chosen if c not in present]
            if missing:
                raise ScopeError(f"Not in this IODB's {label} column: {', '.join(missing[:6])}. Reset the filters and select again.")
        self.masks = self._masks(df)

    def _masks(self, df: pd.DataFrame) -> dict[str, list[bool]]:
        """filter -> per row: does the row pass this filter on its own."""
        n = len(df)
        cols = find_columns(df.columns)
        out = {}
        for name, f in (("statuses", "status"), ("areas", "area"), ("area_codes", "area_code")):
            c = self.columns[f]
            chosen = self.selection[name]
            if not c:
                out[f] = [True] * n
                continue
            if c not in df.columns:
                c = cols[f]
            if c is None:
                raise ScopeError(f"The cable data sheet has no {f.replace('_', ' ').upper()} column, so the Cable Summary "
                                 "cannot be filtered to the selected scope.")
            keys = [key(v) for v in df[c]]
            if chosen is None:
                out[f] = [category(k) != "deleted" for k in keys] if f == "status" else [True] * n
            else:
                wanted = set(chosen)
                out[f] = [k in wanted for k in keys]
        return out

    @property
    def active(self) -> bool:
        """True when at least one row is left out."""
        return not all(all(m) for m in self.masks.values())

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """The eligible rows, with the table's own index (IODB row numbers stay traceable)."""
        m = self._masks(df)
        keep = [a and b and c for a, b, c in zip(m["status"], m["area"], m["area_code"])]
        return df.loc[keep]

    @property
    def needed_columns(self) -> list[str]:
        return [c for c in self.columns.values() if c]

    # ── what the page shows ─────────────────────────────────────────────────
    def options(self) -> dict:
        out: dict = {"columns": self.columns}
        for f, name in (("area", "areas"), ("area_code", "area_codes")):
            seen: dict[str, dict] = {}
            for i, v in enumerate(self.values[f] or []):
                item = seen.setdefault(v.upper(), {"value": v, "count": 0, "areas": set()})
                item["count"] += 1
                if f == "area_code" and self.values["area"]:
                    item["areas"].add(self.values["area"][i])
            out[name] = [{**x, "areas": sorted(x["areas"])} for _, x in sorted(seen.items(), key=lambda kv: _natural(kv[0]))]
        statuses: dict[str, dict] = {}
        for v in self.values["status"] or []:
            k = v.upper()
            item = statuses.setdefault(k, {"value": k if k != BLANK.upper() else BLANK, "count": 0, "category": category(k)})
            item["count"] += 1
        order = {"current": 0, "blank": 1, "unknown": 2, "deleted": 3}
        out["statuses"] = [{**x, "label": CATEGORY_LABELS[x["category"]], "default": x["category"] != "deleted"}
                           for x in sorted(statuses.values(), key=lambda s: (order[s["category"]], _natural(s["value"])))]
        return out

    def summary(self, df: pd.DataFrame, loop_column: Optional[str] = None, jb_column: Optional[str] = None) -> dict:
        """Counts for the selected scope. Exclusions are counted in the order status, area, area code, so no row is counted
        twice and the figures add up to the total."""
        m = self.masks
        status_out = [not x for x in m["status"]]
        area_out = [not a and not s for a, s in zip(m["area"], status_out)]
        code_out = [not c and not s and a for c, s, a in zip(m["area_code"], status_out, m["area"])]
        eligible = [a and b and c for a, b, c in zip(m["status"], m["area"], m["area_code"])]
        cats = [category(v.upper()) for v in self.values["status"]] if self.values["status"] else []

        def distinct(column):
            if not column or column not in df.columns:
                return None
            return len({key(v) for v, ok in zip(df[column], eligible) if ok and key(v) not in _NO_VALUE and key(v) != BLANK.upper()})

        return {"total": len(df), "excluded_status": sum(status_out), "excluded_area": sum(area_out),
                "excluded_area_code": sum(code_out), "eligible": sum(eligible),
                "deleted_excluded": sum(1 for c, ok in zip(cats, m["status"]) if c == "deleted" and not ok),
                "deleted_included": sum(1 for c, ok in zip(cats, eligible) if c == "deleted" and ok),
                "review": sum(1 for c, ok in zip(cats, eligible) if c in ("blank", "unknown") and ok),
                "loops": distinct(loop_column), "junction_boxes": distinct(jb_column)}

    def shared(self, df: pd.DataFrame, columns: dict[str, Optional[str]], lengths: dict[str, Optional[str]]) -> list[str]:
        """Cables / junction boxes of the selected rows that also serve rows outside the selected area or area code
        (deleted and other status-excluded rows do not count). `columns`: label -> heading."""
        m = self.masks
        inside = [s and a and c for s, a, c in zip(m["status"], m["area"], m["area_code"])]
        outside = [s and not (a and c) for s, a, c in zip(m["status"], m["area"], m["area_code"])]
        notes = []
        if not any(outside):
            return notes
        for label, column in columns.items():
            if not column or column not in df.columns:
                continue
            keys = [key(v) for v in df[column]]
            a = {k for k, ok in zip(keys, inside) if ok and k not in _NO_VALUE and k != BLANK.upper()}
            b = {k for k, ok in zip(keys, outside) if ok}
            both = sorted(a & b, key=_natural)
            if both:
                notes.append(f"{len(both)} {label} also serve records outside the selected area scope and are kept in full here "
                             f"({', '.join(both[:8])}{' ...' if len(both) > 8 else ''}). Do not add the Cable Summaries of "
                             "separate area schedules together without removing these repeats.")
            length = lengths.get(label)
            if length and length in df.columns:
                has_in = {k for k, v, ok in zip(keys, df[length], inside) if ok and key(v) not in _NO_VALUE and key(v) != BLANK.upper()}
                only_out = sorted({k for k, v, ok in zip(keys, df[length], outside)
                                   if ok and k in a and key(v) not in _NO_VALUE and key(v) != BLANK.upper()} - has_in, key=_natural)
                if only_out:
                    notes.append(f"Length of {', '.join(only_out[:8])} is written only on rows outside the selected scope; "
                                 "this schedule shows it as not available. Review the IODB.")
        return notes

    def describe(self) -> dict:
        """What was selected, in words, for the file name, the stored result and the diagnostics."""
        shown = {}
        for name, f in (("areas", "area"), ("area_codes", "area_code"), ("statuses", "status")):
            chosen = self.selection[name]
            if chosen is None:
                shown[name] = None
                continue
            original = {v.upper(): v for v in self.values[f]}
            shown[name] = [original[k] for k in chosen]
        return shown

    def file_suffix(self) -> str:
        """'' for the complete project; otherwise what tells separate area downloads apart."""
        d, parts = self.describe(), []
        for name, label in (("areas", "Area"), ("area_codes", "Code")):
            values = d[name]
            if values and len(values) < len({v.upper() for v in self.values["area" if name == "areas" else "area_code"]}):
                joined = "_".join(values[:4]) + (f"_and_{len(values) - 4}_more" if len(values) > 4 else "")
                parts.append(f"{label}_{joined}")
        if self.values["status"] and any(category(v.upper()) == "deleted" and ok
                                         for v, ok in zip(self.values["status"], self.masks["status"])):
            parts.append("with_deleted")
        return re.sub(r"[^A-Za-z0-9._-]+", "_", "_".join(parts)).strip("_")[:90]


def _natural(s: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def diagnostics_workbook(info: dict) -> bytes:
    """A separate report (never part of the engineering deliverable): scope, exclusions, shared cables, terminal trace."""
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()

    def sheet(title, head, rows, widths):
        ws = wb.create_sheet(title)
        ws.append(head)
        for c in ws[1]:
            c.font = Font(bold=True)
        for row in rows:
            ws.append([str(v) if isinstance(v, str) and v.startswith("=") else v for v in row])
            for cell in ws[ws.max_row]:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    cell.data_type = "s"
        for i, w in enumerate(widths):
            ws.column_dimensions[chr(65 + i)].width = w
        return ws

    del wb[wb.sheetnames[0]]
    sel, summary = info.get("selection") or {}, info.get("summary") or {}
    names = {"areas": "Selected areas", "area_codes": "Selected area codes", "statuses": "Selected tag statuses"}
    rows = [[label, ", ".join(sel.get(k) or []) or ("All except deleted" if k == "statuses" else "All")] for k, label in names.items()]
    rows += [[k.replace("_", " ").capitalize(), v] for k, v in summary.items() if v is not None]
    rows += [["Note", n] for n in info.get("notes") or []]
    sheet("Scope", ["Item", "Value"], rows, [28, 110])
    sheet("Excluded Records", ["IODB row", "Tag number", "Area", "Area code", "Status", "Excluded by"],
          info.get("excluded") or [], [10, 26, 22, 12, 22, 20])
    trace_head = ["IODB tag", "IODB row", "Area", "Area code", "Status", "Destination sheet", "Destination field",
                  "Physical endpoint", "I/O Assignment sheet", "I/O Assignment row", "Source column", "Source value", "Result"]
    sheet("Terminal Trace", trace_head, info.get("trace") or [], [24, 10, 16, 10, 16, 16, 18, 20, 18, 12, 32, 14, 52])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def report(scope: Scope, df: pd.DataFrame) -> dict:
    """Options, counts and notes of a selection against the full IODB table."""
    from .cable_schedule_extra import resolve_columns

    cols = resolve_columns(list(df.columns))
    notes = scope.shared(df, {"main cables": cols.get("main_cable_tag"), "junction boxes": cols.get("jb_tag")},
                         {"main cables": cols.get("main_cable_length")})
    summary = scope.summary(df, cols.get("loop_number"), cols.get("jb_tag"))
    if summary["deleted_included"]:
        notes.insert(0, f"WARNING: {summary['deleted_included']} record(s) with a deleted status are included. This is a "
                        "historical schedule, not a current one.")
    if summary["review"]:
        notes.append(f"{summary['review']} included record(s) have a blank or unrecognised tag status. No approved status "
                     "definition covers them; review them or untick those statuses.")
    missing = [label for f, label in (("area", "AREA"), ("area_code", "AREA CODE"), ("status", "STATUS")) if not scope.columns[f]]
    if missing:
        notes.append(f"The IODB has no {', '.join(missing)} column; that filter is not available.")
    return {"selection": scope.describe(), "summary": summary, "notes": notes}


def excluded_rows(scope: Scope, df: pd.DataFrame, limit: int = 20000) -> list[list]:
    from .cable_schedule_extra import resolve_columns

    tag = resolve_columns(list(df.columns)).get("tag_no")
    tags = df[tag].tolist() if tag else [""] * len(df)
    out = []
    values = scope.values
    for i, index in enumerate(df.index):
        why = next((label for f, label in (("status", "Tag status"), ("area", "Area"), ("area_code", "Area code"))
                    if not scope.masks[f][i]), None)
        if why:
            out.append([int(index) + 2, "" if text(tags[i]) == BLANK else text(tags[i]),
                        *(values[f][i] if values[f] else "" for f in ("area", "area_code", "status")), why])
            if len(out) >= limit:
                break
    return out


def row_scope(scope: Scope, df: pd.DataFrame) -> dict[int, tuple]:
    """IODB row number -> (area, area code, status), for the traceability of terminal assignments."""
    v = scope.values
    return {int(index) + 2: tuple(v[f][i] if v[f] else "" for f in ("area", "area_code", "status"))
            for i, index in enumerate(df.index)}


def scoped_iodb(df: pd.DataFrame) -> bytes:
    """The eligible rows as an IODB workbook: stored with the generated schedule, so the generators that follow it work on
    the same scope."""
    import openpyxl
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("IODB")

    def cell(v):
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            return None
        if isinstance(v, str):
            c = WriteOnlyCell(ws, value=ILLEGAL_CHARACTERS_RE.sub("", v))
            c.data_type = "s"
            return c
        return v

    ws.append([cell(str(c)) for c in df.columns])
    for row in df.itertuples(index=False, name=None):
        ws.append([cell(v) for v in row])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
