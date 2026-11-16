"""
Template registry - built from the ACTUAL approved template workbook (LOOP_TYPICAL_TEMPLATES_FINAL_CORRECTED.xlsx).

Nothing about a template's layout is hard-coded here: signal slots (rows, IO types), DATA BLOCK columns, loop-field cells,
print area and the DATA_FIELDS destination schema (including the REQUIRED column) are all read from the workbook.
Only the 7 x 3 x 2 naming convention (loop type number, SPD A/B/C, termination M/D) is fixed - that is the contract.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, Optional

import openpyxl
from openpyxl.utils import get_column_letter, column_index_from_string

# Fallback only - the real list is read from the I/O Assignment master (LOOKUPS: LOOP TYPE NO. / LOOP TYPE).
DEFAULT_LOOP_TYPES = [("AI-2W", 1), ("AI-4W", 2), ("MOTOR-DOL", 3), ("MOTOR-VFD", 4), ("PNEU-VALVE", 5), ("MOV", 6), ("SWITCH", 7)]
SPD_VALUES = ("A", "B", "C")
TERM_VALUES = ("M", "D")
SPD_NAMES = {"A": "FIELD + PANEL SPD", "B": "PANEL SPD ONLY", "C": "NO SPD"}
TERM_NAMES = {"M": "WITH MARSHALLING CABINET", "D": "WITHOUT MARSHALLING CABINET / DIRECT SYSTEM TERMINATION"}
LOOP_FIELD_LABELS = ("LOOP_NAME", "LOOP_SERVICE", "DOC_NO", "REV")      # row 2 of every template: label cell, value in the next column
DATA_HEADER_ROW = 4
FIRST_DATA_ROW = 5


@dataclass
class Slot:
    sig: str
    row: int
    io_type: str
    description: str


@dataclass
class Template:
    typical: str
    sheet_name: str
    loop_type: str
    spd: str
    term: str
    slots: list[Slot]
    columns: dict[str, str]            # DATA BLOCK field -> column letter (from the template's own header row)
    loop_cells: dict[str, str]         # LOOP_NAME -> 'AG2' ...
    print_area: str
    part: str                          # xl/worksheets/sheetN.xml
    drawing: Optional[str]             # xl/drawings/drawingN.xml
    dimension: str = ""

    @property
    def max_signals(self) -> int:
        return len(self.slots)

    @property
    def label(self) -> str:
        return self.sheet_name


@dataclass
class DataField:
    field: str
    column: str
    description: str
    required: str                      # 'Yes' / 'No' / 'Conditional - ...'


@dataclass
class Registry:
    templates: dict[str, Template]
    data_fields: list[DataField]
    loop_types: list[tuple[str, int]]
    missing: list[str]
    problems: list[str]
    template_bytes: bytes = b""

    @property
    def complete(self) -> bool:
        return not self.missing and not self.problems

    def typical_code(self, loop_type: str, spd: str, term: str) -> Optional[str]:
        no = dict(self.loop_types).get(loop_type)
        return f"{no}{spd}-{term}" if no else None

    def field_by_name(self) -> dict[str, DataField]:
        return {f.field: f for f in self.data_fields}

    def table(self) -> list[dict]:
        out = []
        for lt, no in self.loop_types:
            for term in TERM_VALUES:
                for spd in SPD_VALUES:
                    code = f"{no}{spd}-{term}"
                    t = self.templates.get(code)
                    out.append({"typical": code, "loop_type": lt, "spd": spd, "term": term, "spd_name": SPD_NAMES[spd], "term_name": TERM_NAMES[term],
                                "template": t.sheet_name if t else None, "found": t is not None, "signals": t.max_signals if t else 0,
                                "slots": [{"sig": s.sig, "io_type": s.io_type, "description": s.description} for s in t.slots] if t else []})
        return out


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def _sheet_parts(z: zipfile.ZipFile) -> dict[str, str]:
    """sheet name -> part path inside the package."""
    wb = z.read("xl/workbook.xml").decode("utf8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf8")
    target = {m.group(1): m.group(2) for m in re.finditer(r'<Relationship\b[^>]*?Id="([^"]+)"[^>]*?Target="([^"]+)"', rels)}
    target.update({m.group(2): m.group(1) for m in re.finditer(r'<Relationship\b[^>]*?Target="([^"]+)"[^>]*?Id="([^"]+)"', rels)})
    out = {}
    for m in re.finditer(r'<sheet\b[^>]*?name="([^"]+)"[^>]*?r:id="([^"]+)"', wb):
        name = m.group(1).replace("&amp;", "&").replace("&apos;", "'").replace("&quot;", '"')
        t = target.get(m.group(2), "")
        out[name] = ("xl/" + t.lstrip("/").removeprefix("xl/")) if not t.startswith("/") else t.lstrip("/")
    return out


def _drawing_of(z: zipfile.ZipFile, part: str) -> Optional[str]:
    rels = part.replace("worksheets/", "worksheets/_rels/") + ".rels"
    if rels not in z.namelist():
        return None
    m = re.search(r'Type="[^"]*/drawing"[^>]*?Target="([^"]+)"', z.read(rels).decode("utf8")) or re.search(r'Target="([^"]+)"[^>]*?Type="[^"]*/drawing"', z.read(rels).decode("utf8"))
    if not m:
        return None
    t = m.group(1)
    return "xl/drawings/" + t.split("/")[-1]


def read_loop_types(io_master: Optional[bytes]) -> list[tuple[str, int]]:
    """LOOKUPS sheet of the I/O Assignment master: K = LOOP TYPE NO., L = LOOP TYPE."""
    if not io_master:
        return list(DEFAULT_LOOP_TYPES)
    try:
        wb = openpyxl.load_workbook(io.BytesIO(io_master), read_only=True, data_only=True)
        ws = wb["LOOKUPS"]
        out = []
        for r in ws.iter_rows(min_row=4, max_row=40, min_col=11, max_col=12, values_only=True):
            no, lt = r
            if lt and no is not None and re.fullmatch(r"\d+", _norm(no)):
                out.append((_norm(lt).upper(), int(_norm(no))))
        return out or list(DEFAULT_LOOP_TYPES)
    except Exception:
        return list(DEFAULT_LOOP_TYPES)


def build_registry(template_bytes: bytes, io_master: Optional[bytes] = None) -> Registry:
    loop_types = read_loop_types(io_master)
    problems: list[str] = []
    wb = openpyxl.load_workbook(io.BytesIO(template_bytes))
    z = zipfile.ZipFile(io.BytesIO(template_bytes))
    parts = _sheet_parts(z)

    data_fields: list[DataField] = []
    if "DATA_FIELDS" in wb.sheetnames:
        ws = wb["DATA_FIELDS"]
        for r in ws.iter_rows(min_row=4, values_only=True):
            col, fld, desc, _ex, req = (list(r) + [None] * 5)[:5]
            if col and fld and re.fullmatch(r"[A-Z]{1,3}", _norm(col)):
                data_fields.append(DataField(_norm(fld), _norm(col), _norm(desc), _norm(req)))
    else:
        problems.append("DATA_FIELDS sheet not found in the template workbook")

    templates: dict[str, Template] = {}
    pat = re.compile(r"^(\d+)([ABC])-([MD])_(.+)$")
    for name in wb.sheetnames:
        m = pat.match(name)
        if not m:
            continue
        no, spd, term, tail = int(m.group(1)), m.group(2), m.group(3), m.group(4)
        lt = next((n for n, k in loop_types if k == no), None)
        if lt is None or not tail.upper().startswith(lt):
            problems.append(f"Template sheet '{name}' does not match a known loop type (number {no}, '{tail}')")
            continue
        ws = wb[name]
        columns: dict[str, str] = {}
        for c in ws[DATA_HEADER_ROW]:
            if c.value and c.column >= 32:                      # AF onwards
                columns[_norm(c.value)] = get_column_letter(c.column)
        loop_cells: dict[str, str] = {}
        for c in ws[2]:
            if c.value and _norm(c.value) in LOOP_FIELD_LABELS:
                loop_cells[_norm(c.value)] = f"{get_column_letter(c.column + 1)}2"
        sig_col, io_col, desc_col = columns.get("SIG"), columns.get("IO_TYPE"), columns.get("SIG_DESC")
        slots: list[Slot] = []
        if sig_col and io_col:
            r = FIRST_DATA_ROW
            while True:
                sv = ws[f"{sig_col}{r}"].value
                if sv is None or not re.fullmatch(r"S\d+", _norm(sv)):
                    break
                slots.append(Slot(_norm(sv), r, _norm(ws[f"{io_col}{r}"].value).upper(), _norm(ws[f"{desc_col}{r}"].value) if desc_col else ""))
                r += 1
        code = f"{no}{spd}-{term}"
        pa = ""
        try:
            pa = str(ws.print_area or "")
        except Exception:
            pass
        part = parts.get(name, "")
        if not part:
            problems.append(f"Template sheet '{name}': worksheet part not found in the package")
            continue
        if code in templates:
            problems.append(f"Typical {code} appears twice ('{templates[code].sheet_name}' and '{name}')")
            continue
        if not slots:
            problems.append(f"Template {name}: no signal rows (S1..) found in the DATA BLOCK")
        if set(LOOP_FIELD_LABELS) - set(loop_cells):
            problems.append(f"Template {name}: loop fields {sorted(set(LOOP_FIELD_LABELS) - set(loop_cells))} not found in row 2")
        templates[code] = Template(code, name, lt, spd, term, slots, columns, loop_cells, pa.split("!")[-1] if pa else "", part,
                                   _drawing_of(z, part), ws.dimensions)

    missing = []
    for lt, no in loop_types:
        for term in TERM_VALUES:
            for spd in SPD_VALUES:
                code = f"{no}{spd}-{term}"
                if code not in templates:
                    missing.append(code)
    # every template must carry the same DATA BLOCK schema as DATA_FIELDS
    if data_fields:
        expected = {f.field: f.column for f in data_fields}
        for code, t in templates.items():
            if t.columns != expected:
                diff = sorted(set(expected.items()) ^ set(t.columns.items()))[:4]
                problems.append(f"Template {t.sheet_name}: DATA BLOCK columns differ from DATA_FIELDS ({diff})")
    return Registry(templates, data_fields, loop_types, missing, problems, template_bytes)


def library_error(reg: Registry) -> Optional[str]:
    if reg.complete:
        return None
    bits = []
    if reg.missing:
        bits.append("missing typical(s): " + ", ".join(reg.missing))
    bits += reg.problems
    return "TEMPLATE LIBRARY INCOMPLETE - " + "; ".join(bits)


# ---- DATA_FIELDS "REQUIRED" column: evaluated against the loop context (never hard-coded per field) -------------------
def requirement(required: str, ctx: dict) -> Optional[bool]:
    """True = required for this loop / signal, False = not applicable or optional, None = text not understood."""
    r = _norm(required)
    if not r or r.lower() == "no":
        return False
    if r.lower() == "yes":
        return True
    if not r.lower().startswith("conditional"):
        return None
    cond = r.split("-", 1)[1].strip() if "-" in r else r
    lt, spd, term, io = ctx.get("loop_type"), ctx.get("spd"), ctx.get("term"), ctx.get("io_type")
    m = re.match(r"(?i)SPD arrangement ([ABC])(?: or ([ABC]))?$", cond)
    if m:
        return spd in {m.group(1), m.group(2)} - {None}
    m = re.match(r"(?i)arrangement ([MD]) only$", cond)
    if m:
        return term == m.group(1).upper()
    m = re.match(r"(?i)loops with JB \(not (.+)\)$", cond)
    if m:
        return lt not in {x.strip().upper() for x in m.group(1).split("/")}
    m = re.match(r"(?i)(DI|DO|AI|AO) of (.+)$", cond)
    if m:
        return io == m.group(1).upper() and lt in {x.strip().upper() for x in m.group(2).split("/")}
    if re.fullmatch(r"[A-Z0-9]+(-[A-Z0-9]+)*", cond.upper()) and cond.upper() in {n for n, _ in DEFAULT_LOOP_TYPES}:
        return lt == cond.upper()
    return None


def column_letter_index(letter: str) -> int:
    return column_index_from_string(letter)
