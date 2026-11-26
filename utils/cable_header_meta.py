"""
cable_header_meta.py - the document metadata of the Cable Schedule header (PROJECT, CLIENT, DOCUMENT NO., PMC, DATE, LOCATION, REVISION).

  read_cover_header(cover_bytes)   what the linked Cover Sheet workbook (the one the Cover Sheet Generator built for this request) holds,
                                   found by the cover's LABELS (never by a fixed address) - nothing is guessed, a value that is empty,
                                   a placeholder, invalid or contradictory is reported as such.
  resolve(cover, overrides)        cover value if valid, else the user's confirmed value, else still unresolved. Returns the per-field state
                                   the confirmation form shows and, when complete, the values every worksheet header is filled with.

Sources, in priority order: linked Cover Sheet -> the user's confirmed input for that one request. Nothing else is ever used (no sample values,
no previous workbook, no current date, no file name). The user's input is never stored anywhere: it exists for the request that carries it.

DOCUMENT NO. is the cover's Project - Doc. Code - Serial No. (the Job No. is project specific and is not part of it).
REVISION is the cover's current Rev.; DATE is the revision-table date of that same revision (not the current date, not the maximum date).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

import openpyxl

from .cable_schedule_header import _anchor, _below_value, _cells, _find, _key, _right_value, _txt

KEYS = ("project", "client", "doc_no", "pmc", "date", "location", "revision")
LABELS = {"project": "PROJECT", "client": "CLIENT", "doc_no": "DOCUMENT NO.", "pmc": "PMC", "date": "DATE", "location": "LOCATION",
          "revision": "REVISION"}
INPUT_TYPE = {"date": "date"}                                  # every other field is a text input
MAX_LEN = {"project": 300, "client": 200, "doc_no": 80, "pmc": 200, "date": 20, "location": 200, "revision": 20}
NA = "N/A"
NA_ALLOWED = ("pmc",)                                          # a project may genuinely have no PMC

# ── unresolved / placeholder values ──────────────────────────────────────────────────────────────────────────────────
_UNRESOLVED = re.compile(
    r"(?ix) ^\s*$ | ^\s*(?:tba|tbd|tbc|tbf|x+|\?+|[-–—_.]+|n\.?a\.?\s*\?|<.*>|enter\b.*|select\b.*)\s*$"
    r" | \bconfirm | \bto\s+be\s+(?:confirmed|decided|advised|announced|finalised|finalized|filled) | \bX{3,}\b | \bTB[ADCF]\b"
    r" | \[\s*\] | \(\s*\)")
_NA = re.compile(r"(?i)^\s*(?:n\s*/\s*a|n\.a\.?|na|not\s+applicable)\s*$")


def is_unresolved(value: Any) -> bool:
    """Empty, whitespace, XXXX, TBA / TBD, 'Confirm ...' text and similar placeholders. A confirmed N/A is NOT unresolved."""
    text = _txt(value)
    return bool(_UNRESOLVED.search(text)) and not _NA.match(text)


def is_na(value: Any) -> bool:
    return bool(_NA.match(_txt(value)))


# ── dates ────────────────────────────────────────────────────────────────────────────────────────────────────────────
_DATE_FORMATS = ("%d-%m-%Y", "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y", "%d.%m.%y", "%d/%m/%y", "%d-%b-%Y", "%d-%B-%Y",
                 "%d %b %Y", "%d %B %Y", "%d-%b-%y", "%b %d, %Y", "%B %d, %Y", "%Y/%m/%d", "%Y.%m.%d")


def parse_date(value: Any) -> Optional[date]:
    """A calendar date from a date object or common written forms (day first for dd-mm-yyyy); None when it is not a valid date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _txt(value)
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            d = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if 1990 <= d.year <= 2100:
            return d
    return None


def format_date(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def date_text(value: Any) -> str:
    """The date as the cover shows it: written text is kept as typed (when it is a valid date), a real date becomes dd-mm-yyyy."""
    if isinstance(value, (datetime, date)):
        return format_date(parse_date(value))               # type: ignore[arg-type]
    return _txt(value)


# ── what the cover holds ─────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class CoverHeader:
    available: bool = False
    values: dict = field(default_factory=lambda: {k: "" for k in KEYS})      # the cover's own candidate for each field (may be unresolved)
    problems: dict = field(default_factory=dict)                              # key -> (kind, message), kind in {"missing", "invalid", "conflict"}
    revisions: list = field(default_factory=list)                             # [{"rev", "date"}] as on the cover, newest first
    suggestions: dict = field(default_factory=dict)                           # key -> values the cover offers for a conflict (the user picks / types)
    notes: list = field(default_factory=list)

    def fingerprint(self) -> str:
        blob = json.dumps({"a": self.available, "v": self.values, "p": {k: list(v) for k, v in sorted(self.problems.items())}}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:24]


def _rev_text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return _txt(value)


def _same_rev(a: str, b: str) -> bool:
    a, b = _txt(a), _txt(b)
    if a == b:
        return bool(a)
    return a.isdigit() and b.isdigit() and int(a) == int(b)


def _revision_table(ws):
    """(rows, rev column, date column): rows = [(rev text, date value)] top to bottom, found from the header row REV / DATE / PREPARED ..."""
    for c in _cells(ws):
        if _key(c.value) != "rev":
            continue
        found = {}
        for x in ws[c.row]:
            k = _key(x.value) if x.value is not None else ""
            for stem in ("date", "prepared", "checked", "approved"):
                if k.startswith(stem) and stem not in found:
                    found[stem] = x
        if len(found) == 4:
            disc = _find(ws, {"discipline"})
            first = (disc.row + 1) if disc and disc.row < c.row else max(1, c.row - 8)
            rows = []
            for r in range(first, c.row):
                rv = ws.cell(r, c.column).value
                if rv not in (None, "") and _txt(rv):
                    rows.append((_rev_text(rv), ws.cell(r, found["date"].column).value))
            return rows
    return None


def read_cover_header(cover: Optional[bytes]) -> CoverHeader:
    """The header metadata of a Cover Sheet workbook (bytes). `available` is False without one (every field is then missing)."""
    out = CoverHeader()
    if not cover:
        for k in KEYS:
            out.problems[k] = ("missing", "No linked Cover Sheet is available for this request.")
        return out
    try:
        wb = openpyxl.load_workbook(io.BytesIO(cover), data_only=True)
    except Exception as exc:
        for k in KEYS:
            out.problems[k] = ("missing", "The linked Cover Sheet could not be read.")
        out.notes.append(f"The linked Cover Sheet could not be read: {exc}")
        return out
    ws = wb.worksheets[0]
    out.available = True
    v = out.values

    def miss(key: str, what: str):
        out.problems.setdefault(key, ("missing", f"The linked Cover Sheet has no {what}."))

    job = _find(ws, {"jobno"})
    # PROJECT: the project description - the large cell at the left of the 'Job No.' row (or a labelled PROJECT NAME cell)
    proj = _anchor(ws, ws.cell(job.row, 1)) if job else None
    if proj is None or not _txt(proj.value):
        lab = _find(ws, {"projectname", "projecttitle", "nameofproject"})
        proj = _right_value(ws, lab) if lab else None
    v["project"] = _txt(proj.value) if proj is not None else ""
    if not v["project"]:
        miss("project", "project name")

    cl = _find(ws, {"client"})
    v["client"] = _txt(_right_value(ws, cl).value) if cl and _right_value(ws, cl) is not None else ""
    if not v["client"]:
        miss("client", "client name")

    pm = _find(ws, {"pmc"})
    v["pmc"] = _txt(_right_value(ws, pm).value) if pm and _right_value(ws, pm) is not None else ""
    if not v["pmc"]:
        miss("pmc", "PMC name")

    lo = _find(ws, {"location", "projectlocation", "sitelocation"})
    lc = (_right_value(ws, lo) if lo else None) or (_below_value(ws, lo) if lo else None)
    v["location"] = _txt(lc.value) if lc is not None and _key(lc.value) not in ("", "location") else ""
    if not v["location"]:
        miss("location", "project location")

    # DOCUMENT NO. = Project - Doc. Code - Serial No. (the Job No. is not part of it)
    scope = job.row if job else None
    parts = []
    for labels in ({"project"}, {"doccode"}, {"serialno"}):
        lab = _find(ws, labels, scope)
        cell = _below_value(ws, lab) if lab else None
        parts.append(_txt(cell.value) if cell is not None else "")
    project_no, code, serial = parts
    if project_no or serial:
        v["doc_no"] = "-".join(p for p in parts if p)
        if not (project_no and code and serial):
            out.problems["doc_no"] = ("invalid", f"The cover's document number is incomplete (Project '{project_no}', Doc. Code '{code}', "
                                                 f"Serial No. '{serial}').")
    elif code:                                               # a number that could not be split is kept whole in Doc. Code by the cover
        v["doc_no"] = code
    else:
        miss("doc_no", "document number")

    # REVISION and DATE: the cover's current Rev. and the revision-table date of that same revision
    rev_l = _find(ws, {"rev", "revno", "revision"}, scope) if job else None
    rev_cell = _below_value(ws, rev_l) if rev_l else None
    current = _rev_text(rev_cell.value) if rev_cell is not None else ""
    v["revision"] = current
    table = _revision_table(ws)
    out.revisions = [{"rev": r, "date": date_text(d)} for r, d in (table or [])]
    if not current:
        miss("revision", "current revision number")
    if table is None:
        out.notes.append("The cover's revision table was not found.")
        miss("date", "revision table")
    else:
        rows = [(r, d) for r, d in table]
        match = [(r, d) for r, d in rows if current and _same_rev(r, current)]
        if current and not match:
            msg = f"Revision {current} is shown on the cover but is not listed in its revision table."
            out.problems["revision"] = ("conflict", msg)
            out.problems["date"] = ("conflict", msg)
        elif match:
            dates = {date_text(d) for _r, d in match if _txt(d)}
            first = match[0][1]
            v["date"] = date_text(first)
            if len(match) > 1 and (len(dates) != 1 or any(not _txt(d) for _r, d in match)):
                shown = ", ".join(sorted(dates)) or "none"
                out.problems["date"] = ("conflict", f"Revision {current} is listed more than once on the cover with different or missing dates "
                                                    f"({shown}). Enter the correct date.")
                out.suggestions["date"] = sorted(dates)
                v["date"] = ""                                   # no guess: the user confirms the right one
            elif not _txt(first):
                miss("date", f"date for revision {current}")
            elif rows and not _same_rev(rows[0][0], current):
                msg = (f"The cover's current revision is {current}, but its revision table lists {rows[0][0]} as the newest revision.")
                out.problems["revision"] = out.problems["date"] = ("conflict", msg)
            else:
                d0 = parse_date(first)
                later = [r for r, d in rows if parse_date(d) and d0 and parse_date(d) > d0 and not _same_rev(r, current)]
                if later:
                    out.problems["date"] = ("conflict", f"Revision {current} is dated earlier than revision {', '.join(later)} on the cover.")
    # an unresolved value is a missing one (a field the user must supply), unless a problem was already recorded
    for k in KEYS:
        if k not in out.problems and is_unresolved(v[k]):
            out.problems[k] = ("missing", f"The linked Cover Sheet holds no valid {LABELS[k].title().rstrip('.')} (found '{v[k]}').")
        elif k not in out.problems and k == "date" and parse_date(v[k]) is None:
            out.problems[k] = ("invalid", f"The cover's revision date '{v[k]}' is not a valid date.")
        elif k not in out.problems and k == "pmc" and is_na(v[k]):
            v[k] = NA
    return out


# ── resolution ───────────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class FieldState:
    key: str
    label: str
    value: str                    # what the header will show (cover value or confirmed input); "" while unresolved
    candidate: str                # the cover's own value (prefill for a conflict / the invalid value found)
    source: str                   # "cover" | "manual" | ""
    status: str                   # "ok" | "missing" | "invalid" | "conflict"
    message: str
    input: str                    # "text" | "date"
    allow_na: bool = False
    suggestions: list = field(default_factory=list)   # values the cover offers when it contradicts itself

    def public(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Resolution:
    fields: list
    complete: bool
    fingerprint: str
    cover_available: bool
    ignored: list = field(default_factory=list)          # overrides for fields the cover already holds validly
    notes: list = field(default_factory=list)

    @property
    def values(self) -> dict:
        return {f.key: f.value for f in self.fields}

    @property
    def unresolved(self) -> list:
        return [f for f in self.fields if f.status != "ok"]

    def public(self) -> dict:
        return {"complete": self.complete, "fingerprint": self.fingerprint, "cover_available": self.cover_available,
                "fields": [f.public() for f in self.fields], "ignored": self.ignored, "notes": self.notes}


def check_manual(key: str, raw: Any) -> tuple[Optional[str], str]:
    """(normalised value, '') for an acceptable user input, else (None, why not)."""
    text = _txt(raw)
    if not text:
        return None, f"{LABELS[key].title().rstrip('.')} is required."
    if is_na(text):
        if key in NA_ALLOWED:
            return NA, ""
        return None, f"{LABELS[key].title().rstrip('.')} cannot be N/A."
    if is_unresolved(text):
        return None, f"'{text}' is a placeholder, not a value."
    if len(text) > MAX_LEN[key]:
        return None, f"{LABELS[key].title().rstrip('.')} is too long (maximum {MAX_LEN[key]} characters)."
    if key == "date":
        d = parse_date(text)
        if d is None:
            return None, f"'{text}' is not a valid date (use dd-mm-yyyy)."
        return format_date(d), ""
    return text, ""


def resolve(cover: CoverHeader, overrides: Optional[dict] = None) -> Resolution:
    """Every field: the cover's value when valid, else the user's confirmed value for it, else unresolved (with the reason)."""
    overrides = {k: v for k, v in (overrides or {}).items() if k in KEYS}
    fields, ignored = [], []
    for k in KEYS:
        cand = cover.values.get(k, "")
        problem = cover.problems.get(k)
        base = dict(key=k, label=LABELS[k], candidate=cand, input=INPUT_TYPE.get(k, "text"), allow_na=k in NA_ALLOWED,
                    suggestions=list(cover.suggestions.get(k, [])))
        if problem is None:
            if k in overrides and _txt(overrides[k]) and _txt(overrides[k]) != cand:
                ignored.append(k)                           # the cover is authoritative for a field it holds validly
            fields.append(FieldState(value=cand, source="cover", status="ok", message="", **base))
            continue
        kind, message = problem
        raw = overrides.get(k)
        if raw is not None and _txt(raw):
            value, why = check_manual(k, raw)
            if value is not None:
                fields.append(FieldState(value=value, source="manual", status="ok", message="", **base))
            else:
                fields.append(FieldState(value="", source="", status="invalid", message=why, **base))
            continue
        fields.append(FieldState(value="", source="", status=kind, message=message, **base))
    return Resolution(fields=fields, complete=all(f.status == "ok" for f in fields), fingerprint=cover.fingerprint(),
                      cover_available=cover.available, ignored=ignored, notes=list(cover.notes))
