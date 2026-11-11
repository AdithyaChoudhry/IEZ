"""
gland_reference.py - the cable gland reference database, standards basis and vendor-table import.

What is in the built-in data
----------------------------
Only values that were read from a published manufacturer table: CMP Products "Cable Gland Sizes" page
(armoured T3CDS and unarmoured A2F, both shown there "as examples"). Nothing was estimated or converted from another
thread. The page publishes Metric and NPT entry threads only - no BSP, no ET, no IP rating, no Ex certification, no
material or temperature data - so those fields are empty and every consumer of this database must treat the empty
fields as "not in the database", never as "satisfied".

Priority when several sources exist (project settings > approved vendor/project table > generic reference):
    tier PROJECT  : rows imported from the project's own table (Excel upload)
    tier VENDOR   : rows imported from a vendor table (Excel upload)
    tier REFERENCE: the built-in published example tables below

Everything here is decision support. A selection is final only after it is checked against the datasheet of the
manufacturer product that is actually going to be bought.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import openpyxl

RETRIEVED = "2026-11-12"
CMP_URL = "https://www.cmp-products.com/cable-glands/technical/cable-gland-sizes/"
CMP_DOC = "CMP Products - Cable Gland Sizes (manufacturer selection tables, shown as examples: T3CDS armoured, A2F unarmoured)"

TIER_ORDER = {"PROJECT": 0, "VENDOR": 1, "REFERENCE": 2}


@dataclass
class GlandRef:
    manufacturer: str
    series: str
    gland_type: str
    construction: str                 # UNARMOURED | ARMOURED | BRAIDED | FLEXIBLE | FLAT | OTHER
    size: str                         # manufacturer gland size designation, e.g. "20S", "25"
    od_min: float
    od_max: float
    bed_min: Optional[float] = None
    bed_max: Optional[float] = None
    arm_ranges: list = field(default_factory=list)       # [(min, max), ...] armour ranges as published
    metric: Optional[str] = None                         # "M20"
    npt: list = field(default_factory=list)              # ['1/2" NPT', '3/4" NPT']
    bsp: list = field(default_factory=list)
    et: list = field(default_factory=list)
    ip: str = ""
    ex: str = ""
    material: str = ""
    temp: str = ""
    source_doc: str = ""
    source_url: str = ""
    revision: str = ""
    notes: str = ""
    tier: str = "REFERENCE"

    def threads(self, standard: str) -> list[str]:
        return {"METRIC": [self.metric] if self.metric else [], "NPT": list(self.npt), "BSP": list(self.bsp), "ET": list(self.et)}[standard]

    def to_dict(self) -> dict:
        return {"manufacturer": self.manufacturer, "series": self.series, "gland_type": self.gland_type, "construction": self.construction,
                "size": self.size, "od_min": self.od_min, "od_max": self.od_max, "bed_min": self.bed_min, "bed_max": self.bed_max,
                "armour_ranges": [list(a) for a in self.arm_ranges], "metric": self.metric or "", "npt": self.npt, "bsp": self.bsp,
                "et": self.et, "ip": self.ip, "ex": self.ex, "material": self.material, "temp": self.temp, "source_doc": self.source_doc,
                "source_url": self.source_url, "revision": self.revision, "notes": self.notes, "tier": self.tier}


# ── CMP published tables (values copied from the page; thread lengths, weights, ordering codes are not used) ──
# (size, metric, NPT entry, NPT alternate, cable OD min, cable OD max)
_A2F = [
    ("16", "M16", None, None, 3.2, 8.7), ("20S16", "M20", '1/2"', '3/4"', 3.2, 8.7), ("20S", "M20", '1/2"', '3/4"', 6.1, 11.7),
    ("20", "M20", '1/2"', '3/4"', 6.5, 14.0), ("25", "M25", '3/4"', '1"', 11.1, 20.0), ("32", "M32", '1"', '1-1/4"', 17.0, 26.3),
    ("40", "M40", '1-1/4"', '1-1/2"', 23.5, 32.2), ("50S", "M50", '1-1/2"', '2"', 31.0, 38.2), ("50", "M50", '2"', '2-1/2"', 35.6, 44.0),
    ("63S", "M63", '2"', '2-1/2"', 41.5, 49.9), ("63", "M63", '2-1/2"', '3"', 47.2, 55.9), ("75S", "M75", '2-1/2"', '3"', 54.0, 61.9),
    ("75", "M75", '3"', '3-1/2"', 61.1, 67.9), ("90", "M90", '3-1/2"', '4"', 66.6, 79.9), ("100", "M100", '3-1/2"', '4"', 76.0, 91.0),
    ("115", "M115", '4"', '5"', 86.0, 97.9), ("130", "M130", '5"', None, 97.0, 114.9),
]
# (size, metric, NPT, NPT alt, bedding min, bedding max, overall OD min, overall OD max, armour range 1, armour range 2)
_T3CDS = [
    ("20S16", "M20", '1/2"', '3/4"', 3.1, 8.6, 6.1, 13.1, (0.3, 1.0), (0.8, 1.25)),
    ("20S", "M20", '1/2"', '3/4"', 6.1, 11.6, 9.5, 15.9, (0.3, 1.0), (0.8, 1.25)),
    ("20", "M20", '1/2"', '3/4"', 6.5, 13.9, 12.5, 20.9, (0.4, 1.0), (0.8, 1.25)),
    ("25S", "M25", '3/4"', '1"', 11.1, 19.9, 14.0, 22.0, (0.4, 1.2), (1.25, 1.6)),
    ("25", "M25", '3/4"', '1"', 11.1, 19.9, 18.2, 26.2, (0.4, 1.2), (1.25, 1.6)),
    ("32", "M32", '1"', '1-1/4"', 17.0, 26.2, 23.7, 33.9, (0.4, 1.2), (1.6, 2.0)),
    ("40", "M40", '1-1/4"', '1-1/2"', 22.0, 32.1, 27.9, 40.4, (0.4, 1.6), (1.6, 2.0)),
    ("50S", "M50", '1-1/2"', '2"', 29.5, 38.1, 35.2, 46.7, (0.4, 1.6), (2.0, 2.5)),
    ("50", "M50", '2"', '2-1/2"', 35.6, 44.0, 40.4, 53.0, (0.6, 1.6), (2.0, 2.5)),
    ("63S", "M63", '2"', '2-1/2"', 40.1, 49.9, 45.6, 59.4, (0.6, 1.6), (2.0, 2.5)),
    ("63", "M63", '2-1/2"', '3"', 47.2, 55.9, 54.6, 65.8, (0.6, 1.6), (2.0, 2.5)),
    ("75S", "M75", '2-1/2"', '3"', 52.8, 61.9, 59.0, 72.0, (0.6, 1.6), (2.0, 2.5)),
    ("75", "M75", '3"', '3-1/2"', 59.1, 67.9, 66.7, 78.4, (0.6, 1.6), (2.5, 3.0)),
    ("90", "M90", '3-1/2"', '4"', 66.6, 78.6, 76.2, 90.3, (0.8, 1.6), (3.15, 4.0)),
    ("100", "M100", '3-1/2"', '4"', 76.0, 90.9, 86.1, 101.4, (0.8, 1.6), (3.15, 4.0)),
    ("115", "M115", '4"', '5"', 86.0, 97.9, 101.5, 110.2, (0.8, 1.6), (3.15, 4.0)),
    ("130", "M130", '5"', None, 97.0, 114.9, 110.2, 123.2, (0.8, 1.6), (3.15, 4.0)),
]


def _npt(*vals) -> list:
    return [f'{v} NPT' for v in vals if v]


def builtin() -> list[GlandRef]:
    rows: list[GlandRef] = []
    for size, m, n1, n2, lo, hi in _A2F:
        rows.append(GlandRef("CMP Products", "A2F", "Unarmoured cable gland", "UNARMOURED", size, lo, hi, metric=m, npt=_npt(n1, n2),
                             source_doc=CMP_DOC, source_url=CMP_URL, revision=f"page undated; retrieved {RETRIEVED}",
                             notes="Overall cable diameter range as published. NPT: the entry thread and the alternate entry thread listed for this size "
                                   "(the page does not label which is which). Page gives no IP, Ex, material, temperature, BSP or ET data."))
    for size, m, n1, n2, bl, bh, lo, hi, a1, a2 in _T3CDS:
        rows.append(GlandRef("CMP Products", "T3CDS", "Armoured cable gland", "ARMOURED", size, lo, hi, bed_min=bl, bed_max=bh,
                             arm_ranges=[a1, a2], metric=m, npt=_npt(n1, n2), source_doc=CMP_DOC, source_url=CMP_URL,
                             revision=f"page undated; retrieved {RETRIEVED}",
                             notes="Bedding diameter and overall cable diameter as published. The table lists two armour ranges per size; which armour/cone "
                                   "type each belongs to is not stated in the retrieved text - verify on the manufacturer's page before relying on the armour check. "
                                   "Page gives no IP, Ex, material, temperature, BSP or ET data."))
    return rows


STANDARDS = [
    {"id": "IEC/EN 62444", "title": "Cable glands for electrical installations",
     "use": "General framework: cable gland, entry thread, cable gland size (related to the nominal diameter of the entry thread), cable retention and anchorage. "
            "It is not a universal cable-OD-to-gland-size table; sealing ranges come from the manufacturer's table.",
     "applies_to": "All"},
    {"id": "ASME B1.20.1", "title": "Pipe threads, general purpose (inch)",
     "use": "NPT thread dimensions and terminology. NPT sizes are taken from the gland manufacturer's entry-thread options for the selected body size, "
            "never converted from a metric size.", "applies_to": "NPT"},
    {"id": "BS 31:1940", "title": "Steel conduit and fittings for electrical wiring (historical definition of the ET thread)",
     "use": "ET = Electrical Thread, a legacy English electrical threadform. LEGACY / NON-STANDARD FOR MANY MODERN PRODUCTS. Not interchangeable with Metric, "
            "NPT or BSP. Verify availability with the chosen manufacturer; where an ET entry is required some manufacturers advise an approved adaptor.",
     "applies_to": "ET"},
    {"id": "ISO 228-1 / ISO 7-1 (BSP)", "title": "Pipe threads (BSP parallel / taper)",
     "use": "BSP entry threads. Sizes come from the manufacturer's table for the gland model; the built-in reference tables contain no BSP data.",
     "applies_to": "BSP"},
]

PRINCIPLES = [
    "Cable OD decides whether a particular gland model/size can seal and clamp the cable. The entry thread decides how the gland connects to the "
    "equipment/enclosure. They are related but different selection criteria.",
    "A gland size is not determined by the thread size alone: the cable must lie inside the gland's published cable diameter range "
    "(OD >= minimum and OD <= maximum); armoured cable additionally needs the bedding and armour ranges checked.",
    "The result is an ENGINEERING RECOMMENDATION. A final, certified or procurement-approved selection needs the datasheet of the manufacturer product "
    "that will be purchased.",
    "Priority: project specification > approved vendor/project gland database > generic engineering reference.",
    "Missing data is reported, never assumed: no IP rating, Ex certification, material or temperature is claimed unless the database row states it.",
]


# ── vendor / project table import (Excel) ────────────────────────────────────
TEMPLATE_HEADERS = ["MANUFACTURER", "PRODUCT SERIES", "GLAND TYPE", "CABLE CONSTRUCTION", "GLAND SIZE", "CABLE DIAMETER MIN (MM)",
                    "CABLE DIAMETER MAX (MM)", "BEDDING DIAMETER MIN (MM)", "BEDDING DIAMETER MAX (MM)", "ARMOUR MIN (MM)", "ARMOUR MAX (MM)",
                    "METRIC THREAD", "NPT THREAD", "ET THREAD", "BSP THREAD", "IP RATING", "EX CERTIFICATION", "MATERIAL", "TEMPERATURE RANGE",
                    "SOURCE DOCUMENT", "SOURCE URL", "REVISION / DATE", "NOTES"]
_ALIAS = {
    "manufacturer": ["MANUFACTURER", "VENDOR", "MAKE"], "series": ["PRODUCT SERIES", "SERIES", "MODEL"], "gland_type": ["GLAND TYPE", "TYPE"],
    "construction": ["CABLE CONSTRUCTION", "CONSTRUCTION", "ARMOURED UNARMOURED", "ARMOURED / UNARMOURED"], "size": ["GLAND SIZE", "SIZE"],
    "od_min": ["CABLE DIAMETER MIN MM", "CABLE DIAMETER MIN", "CABLE OD MIN"], "od_max": ["CABLE DIAMETER MAX MM", "CABLE DIAMETER MAX", "CABLE OD MAX"],
    "bed_min": ["BEDDING DIAMETER MIN MM", "BEDDING DIAMETER MIN"], "bed_max": ["BEDDING DIAMETER MAX MM", "BEDDING DIAMETER MAX"],
    "arm_min": ["ARMOUR MIN MM", "ARMOUR DIAMETER MIN", "ARMOUR MIN"], "arm_max": ["ARMOUR MAX MM", "ARMOUR DIAMETER MAX", "ARMOUR MAX"],
    "metric": ["METRIC THREAD", "METRIC"], "npt": ["NPT THREAD", "NPT"], "et": ["ET THREAD", "ET"], "bsp": ["BSP THREAD", "BSPT THREAD", "BSP BSPT", "BSP"],
    "ip": ["IP RATING", "IP"], "ex": ["EX CERTIFICATION", "CERTIFICATION", "EX"], "material": ["MATERIAL"],
    "temp": ["TEMPERATURE RANGE", "TEMPERATURE"], "source_doc": ["SOURCE DOCUMENT"], "source_url": ["SOURCE URL"],
    "revision": ["REVISION DATE", "REVISION", "DATE"], "notes": ["NOTES", "REMARKS"],
}


def _norm(v: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(v or "").upper()).strip()


def _f(v) -> Optional[float]:
    try:
        x = float(str(v).replace(",", "").strip())
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def norm_construction(text: str) -> str:
    t = (text or "").upper()
    if "UNARM" in t or t in ("U", "NO", "NON-ARMOURED", "NON ARMOURED"):
        return "UNARMOURED"
    if "ARM" in t or t in ("SWA", "STA", "AWA"):
        return "ARMOURED"
    for k in ("BRAID", "FLEX", "FLAT"):
        if k in t:
            return {"BRAID": "BRAIDED", "FLEX": "FLEXIBLE", "FLAT": "FLAT"}[k]
    return "OTHER" if t else ""


def _threads(text: Optional[str], std: str) -> list[str]:
    """'1/2" NPT; 3/4" NPT' -> normalised designations (options are separated by ';' or a new line)."""
    from .gland_quantity import parse_gland
    out = []
    for part in (p.strip() for p in re.split(r"[;\n]", str(text or ""))):
        if part:
            g = parse_gland(part if std == "METRIC" or std in part.upper() else f"{part} {std}")
            out.append(g["label"])
    return out


def read_vendor_table(data: bytes, tier: str = "VENDOR") -> tuple[list[GlandRef], list[str]]:
    """Excel table with the TEMPLATE_HEADERS columns -> (rows, problems). Rows with problems are skipped, never repaired."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception as exc:
        raise ValueError("The gland reference table could not be opened as an Excel workbook.") from exc
    problems: list[str] = []
    rows: list[GlandRef] = []
    for ws in wb.worksheets:
        hdr = None
        for r, row in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), 1):
            norm = {_norm(v): c for c, v in enumerate(row, 1) if v not in (None, "")}
            cols = {f: next((norm[_norm(a)] for a in al if _norm(a) in norm), None) for f, al in _ALIAS.items()}
            if cols["size"] and cols["od_min"] and cols["od_max"] and cols["construction"]:
                hdr = (r, cols)
                break
        if not hdr:
            continue
        r0, cols = hdr
        for r in range(r0 + 1, ws.max_row + 1):
            def cell(f):
                c = cols.get(f)
                v = ws.cell(r, c).value if c else None
                return None if v is None or str(v).strip() == "" else v
            if all(cell(f) is None for f in cols):
                continue
            ref = f"{ws.title} row {r}"
            if cell("size") is None and cell("od_min") is None and cell("od_max") is None:
                continue                                      # a note line, not a table row
            size, constr = cell("size"), norm_construction(str(cell("construction") or ""))
            lo, hi = _f(cell("od_min")), _f(cell("od_max"))
            if size is None or lo is None or hi is None or lo <= 0 or hi < lo:
                problems.append(f"{ref}: needs a gland size and a valid cable diameter min/max - skipped.")
                continue
            if not constr:
                problems.append(f"{ref}: cable construction is blank - skipped.")
                continue
            bl, bh = _f(cell("bed_min")), _f(cell("bed_max"))
            am, aM = _f(cell("arm_min")), _f(cell("arm_max"))
            if constr == "ARMOURED" and (bl is None or bh is None):
                problems.append(f"{ref}: armoured gland without a bedding diameter range - used for overall-diameter checks only (bedding cannot be verified).")
            metric = _threads(cell("metric"), "METRIC")
            rows.append(GlandRef(
                manufacturer=str(cell("manufacturer") or ""), series=str(cell("series") or ""), gland_type=str(cell("gland_type") or ""),
                construction=constr, size=str(size), od_min=lo, od_max=hi, bed_min=bl, bed_max=bh,
                arm_ranges=[(am, aM)] if am is not None and aM is not None else [],
                metric=metric[0] if metric else None, npt=_threads(cell("npt"), "NPT"), bsp=_threads(cell("bsp"), "BSP"), et=_threads(cell("et"), "ET"),
                ip=str(cell("ip") or ""), ex=str(cell("ex") or ""), material=str(cell("material") or ""), temp=str(cell("temp") or ""),
                source_doc=str(cell("source_doc") or ""), source_url=str(cell("source_url") or ""), revision=str(cell("revision") or ""),
                notes=str(cell("notes") or ""), tier=tier))
        break
    if not rows and not problems:
        raise ValueError("No gland table was found: a header row with GLAND SIZE, CABLE CONSTRUCTION and CABLE DIAMETER MIN/MAX is required.")
    return rows, problems


def template_workbook() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "GLAND TABLE"
    ws.append(TEMPLATE_HEADERS)
    ws.append(["(enter the rows of your approved manufacturer / project table here - one row per gland size and construction)"])
    ws.append(["Thread columns may list several options separated by ';' e.g. 1/2\" NPT; 3/4\" NPT. Leave a cell empty when the manufacturer does not publish it."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
