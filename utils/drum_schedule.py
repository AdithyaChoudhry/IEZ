"""
drum_schedule.py - Cable Drum Schedule: allocate the cable length demanded by the IODB against the drums of a
Drum Master.

    IODB (shared normaliser) -> cable demand (branch + main, shared main cables once)
    Drum Master Excel        -> drum lots -> physical drum instances
    group by CABLE TYPE + IS/NIS -> sequential allocation with a running balance -> reports

A drum is a finite pool of cable. Many cable tags consume it one after the other (balance 500 -> 380 -> 280 ...)
until the remaining length is at or below the minimum residual, then the next drum of the SAME cable type and the
SAME IS/NIS is opened. Nothing is invented or silently dropped: every metre is either allocated, remaining on a
drum, or reported as shortage.

Nothing here touches the Instrument Cable Schedule generators; the IODB is read through the existing normaliser
(utils.cable_schedule_extra) and its cable-summary helpers.
"""
from __future__ import annotations

import io
import math
import re
from collections import OrderedDict
from copy import copy
from pathlib import Path
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .cable_schedule_extra import clean, is_missing, normalize
from .cable_summary import _norm_col

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "backend" / "app" / "templates" / "drum_schedule" / "drum_schedule_reference.xlsx"
DEFAULT_MIN_RESIDUAL = 10.0
MAX_MIN_RESIDUAL = 15.0
EPS = 1e-9


class DrumError(Exception):
    """User-facing problem (bad input file, bad setting)."""


# ── helpers ──────────────────────────────────────────────────────────────────
def cable_key(text: Optional[str]) -> str:
    """Exact cable type match key: only spelling noise is removed (case, spaces, dots, x/× and Sq.mm variants)."""
    if not text:
        return ""
    t = str(text).upper().replace("×", "X").replace("²", "2")
    t = re.sub(r"SQ\.?\s*MM|MM2|MM\^2", "SQMM", t)
    return re.sub(r"[\s.]+", "", t)


def is_nis_value(text: Optional[str]) -> str:
    """'IS' / 'NIS' / '' (not stated or not recognised)."""
    t = re.sub(r"[^A-Z]", "", (text or "").upper())
    if t in ("IS", "INTRINSICALLYSAFE", "I"):
        return "IS"
    if t in ("NIS", "NONIS", "NONINTRINSICALLYSAFE", "N"):
        return "NIS"
    return ""


def num(value: Any) -> tuple[Optional[float], str]:
    """(number, 'ok' | 'blank' | 'invalid')."""
    text = clean(value)
    if text is None or text.upper() in ("", "-", "--", "NA", "N/A", "TBA", "TBD", "NIL", "NONE", "NAN"):
        return None, "blank"
    try:
        v = float(Decimal(text.replace(",", "")))
    except (InvalidOperation, ValueError):
        return None, "invalid"
    if not math.isfinite(v):
        return None, "invalid"
    return v, "ok"


def fmt(v: float) -> float | int:
    v = round(v, 3)
    return int(v) if v == int(v) else v


def yes_no(value: Any) -> Optional[bool]:
    t = (clean(value) or "").upper()
    if t in ("YES", "Y", "TRUE", "1", "ALLOWED"):
        return True
    if t in ("NO", "N", "FALSE", "0", "NOT ALLOWED"):
        return False
    return None


# ── data model ───────────────────────────────────────────────────────────────
@dataclass
class Issue:
    severity: str                 # ERROR | WARNING | INFO
    source: str                   # IODB | DRUM MASTER | SCHEDULE
    kind: str
    ref: str
    message: str


@dataclass
class Demand:
    tag: str
    category: str                 # BRANCH | MAIN
    cable_type: str
    is_nis: str
    length: float
    row: int                      # first IODB row (Excel numbering, header = 1)
    rows: list[int]
    description: str
    reference: str
    seq: int = 0
    jb: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return cable_key(self.cable_type), self.is_nis


@dataclass
class Lot:                        # one Drum Master record
    master_id: str
    row: int
    cable_type: str
    size: str
    is_nis: str
    unit: str
    length: float                 # standard drum length, metres
    qty: int
    total: Optional[float]
    split: Optional[bool]
    no_splice_default: Optional[bool]
    vendor: str
    drum_type: str
    weight_limit: str
    tolerance: str
    remarks: str
    keys: set[str] = field(default_factory=set)

    @property
    def split_allowed(self) -> bool:
        return bool(self.split)       # blank = not allowed (no splice)


@dataclass
class Drum:                       # one physical drum
    drum_id: str
    lot: Lot
    usable: float
    balance: float = 0.0
    opened: bool = False
    closed: bool = False
    allocated: float = 0.0
    order: int = 0

    def __post_init__(self):
        self.balance = self.usable


@dataclass
class Alloc:
    group: tuple[str, str]
    drum: Optional[Drum]
    demand: Demand
    before: float
    length: float
    after: float
    part: int = 1
    parts: int = 1
    seq: int = 0
    unallocated: float = 0.0
    note: str = ""


# ── Drum Master ──────────────────────────────────────────────────────────────
MASTER_ALIASES = {
    "master_id": ["DRUM MASTER ID", "DRUM ID", "DRUM NO", "DRUM NUMBER", "MASTER ID"],
    "cable_type": ["CABLE TYPE"],
    "size": ["CABLE SIZE CONSTRUCTION", "CABLE SIZE", "CONSTRUCTION", "CABLE CONSTRUCTION"],
    "is_nis": ["IS NIS", "IS NIS TYPE", "IS NIS CLASS"],
    "unit": ["UNIT", "UOM"],
    "length": ["STANDARD DRUM LENGTH M", "STANDARD DRUM LENGTH", "DRUM LENGTH M", "DRUM LENGTH"],
    "qty": ["DRUM QUANTITY", "DRUM QTY", "QUANTITY", "QTY"],
    "total": ["TOTAL CABLE LENGTH", "TOTAL CABLE LENGTH M", "TOTAL LENGTH"],
    "split": ["SPLIT ALLOWED", "SPLIT"],
    "no_splice": ["NO SPLICE DEFAULT", "NO SPLICE"],
    "vendor": ["VENDOR NAME", "VENDOR", "MANUFACTURER", "MAKE"],
    "drum_type": ["DRUM TYPE SIZE", "DRUM TYPE", "DRUM SIZE"],
    "weight": ["DRUM WEIGHT LIMIT KG", "DRUM WEIGHT LIMIT", "WEIGHT LIMIT"],
    "tolerance": ["QUANTITY TOLERANCE", "QUANITY TOLERANCE", "TOLERANCE"],
    "remarks": ["REMARKS", "REMARK"],
}


def _find_master_sheet(wb) -> tuple[Any, int, dict[str, int]]:
    best = None
    for ws in wb.worksheets:
        for r_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=30, values_only=True), start=1):
            norm = {_norm_col(v): c for c, v in enumerate(row, start=1) if v not in (None, "")}
            cols = {f: next((norm[_norm_col(a)] for a in al if _norm_col(a) in norm), None) for f, al in MASTER_ALIASES.items()}
            score = sum(1 for f in ("cable_type", "length", "qty") if cols[f]) + (1 if cols["size"] else 0)
            if cols["length"] and (cols["cable_type"] or cols["size"]) and (best is None or score > best[0]):
                best = (score, ws, r_idx, {f: c for f, c in cols.items() if c})
    if not best:
        raise DrumError("The Drum Master was not recognised: no sheet has a header row with CABLE TYPE (or CABLE SIZE) "
                        "and STANDARD DRUM LENGTH.")
    return best[1], best[2], best[3]


def read_drum_master(data: bytes) -> tuple[list[Lot], list[Issue], dict]:
    """Drum Master Excel -> lots (validated). Invalid records are reported and excluded."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    except Exception as exc:
        raise DrumError("The Drum Master could not be opened as an Excel workbook.") from exc
    ws, hdr, cols = _find_master_sheet(wb)
    issues: list[Issue] = []
    lots: list[Lot] = []
    seen_ids: dict[str, int] = {}
    for r in range(hdr + 1, ws.max_row + 1):
        def cell(f):
            return clean(ws.cell(r, cols[f]).value) if f in cols else None
        if all(cell(f) is None for f in cols):
            continue
        ref = f"Drum Master row {r}"
        ctype, size = cell("cable_type"), cell("size")
        if is_missing(ctype) and is_missing(size):
            issues.append(Issue("ERROR", "DRUM MASTER", "Missing cable type", ref, "No cable type - record excluded."))
            continue
        length, st = num(cell("length"))
        if st == "blank":
            issues.append(Issue("ERROR", "DRUM MASTER", "Missing drum length", ref, f"{ctype or size}: no standard drum length - excluded."))
            continue
        if st == "invalid" or length is None or length <= 0:
            kind = "Zero drum length" if length == 0 else ("Negative drum length" if length is not None and length < 0 else "Invalid drum length")
            issues.append(Issue("ERROR", "DRUM MASTER", kind, ref, f"{ctype or size}: drum length '{cell('length')}' is not usable - excluded."))
            continue
        unit = (cell("unit") or "M").upper().strip()
        if unit in ("KM", "KMS"):
            length *= 1000
        elif unit not in ("M", "MTR", "MTRS", "METER", "METERS", "METRE", "METRES", "MT"):
            issues.append(Issue("ERROR", "DRUM MASTER", "Unsupported unit", ref, f"Unit '{unit}' is not metres - excluded."))
            continue
        qv, qst = num(cell("qty"))
        if qst != "ok" or qv is None or qv <= 0 or qv != int(qv):
            kind = "Missing drum quantity" if qst == "blank" else "Invalid drum quantity"
            issues.append(Issue("ERROR", "DRUM MASTER", kind, ref, f"{ctype or size}: drum quantity '{cell('qty')}' is not a whole number above 0 - excluded."))
            continue
        isn_raw = cell("is_nis")
        isn = is_nis_value(isn_raw)
        if not isn:
            issues.append(Issue("WARNING", "DRUM MASTER", "IS/NIS" if isn_raw else "Missing IS/NIS", ref,
                                f"{ctype or size}: IS/NIS {'value ' + repr(isn_raw) + ' is not IS or NIS' if isn_raw else 'is blank'}; "
                                "it only matches IODB cables with no IS/NIS."))
        split_raw = cell("split")
        split = yes_no(split_raw)
        nosplice = yes_no(cell("no_splice"))
        if split_raw and split is None:
            issues.append(Issue("WARNING", "DRUM MASTER", "Invalid split rule", ref,
                                f"SPLIT ALLOWED '{split_raw}' is not YES or NO; treated as NO (no split)."))
        if split is None and nosplice is False:
            split = True                       # NO-SPLICE DEFAULT = NO: splicing/splitting is allowed
        total, tst = num(cell("total"))
        if total is not None and abs(total - length * qv) > 0.5:
            issues.append(Issue("WARNING", "DRUM MASTER", "Inconsistent total", ref,
                                f"TOTAL CABLE LENGTH {fmt(total)} m differs from drum length x quantity = {fmt(length * qv)} m; "
                                "the drum length and quantity are used."))
        if re.match(r"^\s*example\b", cell("remarks") or "", re.I):
            issues.append(Issue("WARNING", "DRUM MASTER", "Example record", ref,
                                f"{ctype or size}: REMARKS says '{cell('remarks')}' - the row is used as given; remove it if it is only a template example."))
        mid = cell("master_id") or f"DM-{r}"
        if mid in seen_ids:
            issues.append(Issue("WARNING", "DRUM MASTER", "Duplicate master id", ref,
                                f"DRUM MASTER ID '{mid}' also appears in row {seen_ids[mid]}; both are kept as separate lots."))
        seen_ids.setdefault(mid, r)
        lot = Lot(master_id=mid, row=r, cable_type=ctype or "", size=size or "", is_nis=isn, unit="M", length=length,
                  qty=int(qv), total=total, split=split, no_splice_default=nosplice, vendor=cell("vendor") or "",
                  drum_type=cell("drum_type") or "", weight_limit=cell("weight") or "", tolerance=cell("tolerance") or "",
                  remarks=cell("remarks") or "")
        # the IODB cable type may be written as the type column, the size/construction column or both together
        for text in (ctype, size, f"{ctype or ''} {size or ''}".strip()):
            if text and not is_missing(text):
                lot.keys.add(cable_key(text))
        lots.append(lot)
    if not lots and not issues:
        raise DrumError("The Drum Master has a header row but no drum records.")
    types = {cable_key(l.size or l.cable_type) for l in lots}
    info = {"sheet": ws.title, "header_row": hdr, "records": len(lots), "cable_types": len(types),
            "total_drums": sum(l.qty for l in lots), "total_length": fmt(sum(l.length * l.qty for l in lots)),
            "columns_found": sorted(cols)}
    return lots, issues, info


def build_drums(lots: list[Lot]) -> list[Drum]:
    """One Drum per unit of DRUM QUANTITY (ids generated when the master has one id per lot)."""
    drums: list[Drum] = []
    for lot in lots:
        for n in range(1, lot.qty + 1):
            did = lot.master_id if lot.qty == 1 else f"{lot.master_id}-{n:03d}"
            drums.append(Drum(drum_id=did, lot=lot, usable=lot.length, order=len(drums)))
    return drums


# ── demand from the IODB ─────────────────────────────────────────────────────
def extract_demand(df) -> tuple[list[Demand], list[Issue], dict]:
    """Branch cable (unique tag) + main cable (unique tag, counted once) requirements from the IODB frame."""
    recs, cols = normalize(df)
    issues: list[Issue] = []
    missing = [n for n in ("branch_cable_tag", "branch_cable_type", "branch_cable_length", "main_cable_tag",
                           "main_cable_type", "main_cable_length") if not cols.get(n)]
    if len(missing) == 6:
        raise DrumError("The IODB has none of the cable columns (INSTRUMENT TO JB CABLE TAG / TYPE, BRANCH CABLE LENGTH, "
                        "MAIN CABLE TAG NUMBER / TYPE / LENGTH).")
    for n in missing:
        issues.append(Issue("WARNING", "IODB", "Column not found", "IODB header", f"No '{n.replace('_', ' ').upper()}' column was found."))

    groups: dict[tuple[str, str], "OrderedDict[str, list]"] = {("BRANCH", "t"): OrderedDict(), ("MAIN", "t"): OrderedDict()}
    stats = {"rows": len(recs), "branch_rows": 0, "main_rows": 0}
    for rec in recs:
        for cat, tag_f, type_f, len_f in (("BRANCH", "branch_cable_tag", "branch_cable_type", "branch_cable_length"),
                                          ("MAIN", "main_cable_tag", "main_cable_type", "main_cable_length")):
            tag, ctype, length = rec.f.get(tag_f), rec.f.get(type_f), rec.f.get(len_f)
            has_type, has_len, has_tag = not is_missing(ctype), not is_missing(length), not is_missing(tag)
            if not (has_tag or has_type or has_len):
                continue                                    # this record has no such cable
            if not has_tag:
                if has_type and has_len:
                    issues.append(Issue("ERROR", "IODB", "Missing cable tag", f"IODB row {rec.row}",
                                        f"{cat.title()} cable {ctype} {length} m has no cable tag number ({rec.tag_no or 'no instrument tag'}) - not scheduled."))
                continue
            stats["branch_rows" if cat == "BRANCH" else "main_rows"] += 1
            groups[(cat, "t")].setdefault(tag.upper(), []).append((rec, tag))

    demands: list[Demand] = []
    seq = 0
    for (cat, _), bytag in groups.items():
        tag_f, type_f, len_f = (("branch_cable_tag", "branch_cable_type", "branch_cable_length") if cat == "BRANCH"
                                else ("main_cable_tag", "main_cable_type", "main_cable_length"))
        for key, items in bytag.items():
            first_rec, tag = items[0]
            rows = [r.row for r, _ in items]
            ref = f"IODB row {rows[0]}" + (f" (+{len(rows) - 1} more)" if len(rows) > 1 else "")

            def pick(field_name, ok=lambda v: not is_missing(v)):
                vals = [r.f.get(field_name) for r, _ in items if ok(r.f.get(field_name))]
                return (vals[0] if vals else None), len(set(v.upper() for v in vals)) > 1

            ctype, c_conf = pick(type_f)
            length_raw, l_conf = pick(len_f)
            isn_raw, i_conf = pick("is_nis", lambda v: bool(is_nis_value(v)))
            for conflict, what in ((c_conf, "cable type"), (l_conf, "length"), (i_conf, "IS/NIS")):
                if conflict:
                    issues.append(Issue("WARNING", "IODB", "Conflicting values", f"{cat.title()} cable {tag}",
                                        f"{len(rows)} IODB rows give different {what} values for this cable tag; the first is used (rows {', '.join(map(str, rows[:6]))})."))
            if ctype is None:
                issues.append(Issue("ERROR", "IODB", "Missing cable type", f"{cat.title()} cable {tag}",
                                    f"{ref}: no cable type - excluded from automatic scheduling."))
                continue
            length, st = num(length_raw)
            if st == "blank":
                issues.append(Issue("ERROR", "IODB", "Missing cable length", f"{cat.title()} cable {tag}", f"{ref}: no cable length - not scheduled."))
                continue
            if st == "invalid" or length is None or length <= 0:
                kind = "Zero/negative cable length" if length is not None else "Invalid cable length"
                issues.append(Issue("ERROR", "IODB", kind, f"{cat.title()} cable {tag}", f"{ref}: length '{length_raw}' is not valid - not scheduled."))
                continue
            isn = is_nis_value(isn_raw)
            if not isn:
                issues.append(Issue("WARNING", "IODB", "Missing IS/NIS", f"{cat.title()} cable {tag}",
                                    f"{ref}: IS/NIS is not stated; it can only use drums with no IS/NIS."))
            if len(rows) > 1 and cat == "MAIN":
                issues.append(Issue("INFO", "IODB", "Shared main cable", f"Main cable {tag}",
                                    f"Used by {len(rows)} IODB rows; counted once ({fmt(length)} m)."))
            elif len(rows) > 1:
                issues.append(Issue("INFO", "IODB", "Repeated branch cable tag", f"Branch cable {tag}",
                                    f"Appears on {len(rows)} IODB rows; counted once ({fmt(length)} m)."))
            tags = [r.tag_no for r, _ in items if r.tag_no]
            if cat == "MAIN":
                jb = first_rec.jb_tag if not is_missing(first_rec.jb_tag) else None
                reference = (f"{jb}: " if jb else "") + ", ".join(tags[:4]) + (f" +{len(tags) - 4} more" if len(tags) > 4 else "")
                desc = first_rec.equipment_description or jb or first_rec.tag_no or ""
            else:
                reference = first_rec.tag_no or ""
                desc = " ".join(p for p in (first_rec.equipment_description, first_rec.signal_description) if p) or reference
            seq += 1
            demands.append(Demand(tag=tag, category=cat, cable_type=ctype, is_nis=isn, length=length, row=rows[0], rows=rows,
                                  description=desc, reference=reference, seq=seq,
                                  jb=first_rec.jb_tag if not is_missing(first_rec.jb_tag) else ""))
    stats.update({"demand": len(demands), "branch": sum(1 for d in demands if d.category == "BRANCH"),
                  "main": sum(1 for d in demands if d.category == "MAIN"),
                  "total_length": fmt(sum(d.length for d in demands)), "iodb_columns": {k: v for k, v in cols.items() if v and "cable" in k}})
    return demands, issues, stats


# ── scheduling ───────────────────────────────────────────────────────────────
def check_settings(min_residual: float) -> float:
    try:
        v = float(min_residual)
    except (TypeError, ValueError):
        raise DrumError("The minimum residual drum length must be a number.")
    if not (0 <= v <= MAX_MIN_RESIDUAL):
        raise DrumError(f"The minimum residual drum length must be between 0 and {fmt(MAX_MIN_RESIDUAL)} m.")
    return v


def _allocate_group(group, demands: list[Demand], drums: list[Drum], min_residual: float, use_split: bool, seq0: int):
    """
    Sequential allocation for one cable type + IS/NIS. Deterministic: cable tags in IODB order, drums in master order.

    For every cable tag the length is taken from the drum that is already open and has enough cable left; if the Drum
    Master allows splitting, a tag longer than the open drum's balance takes what is left and continues on the next
    drum; otherwise a new drum is opened. A drum is closed once its balance is at or below the minimum residual.
    """
    allocs: list[Alloc] = []
    seq = seq0

    def take(drum: Drum, d: Demand, length: float, part: int) -> Alloc:
        nonlocal seq
        before = drum.balance
        drum.opened = True
        drum.balance = max(before - length, 0.0)
        drum.allocated += length
        if drum.balance <= min_residual + EPS:
            drum.closed = True
        seq += 1
        a = Alloc(group=group, drum=drum, demand=d, before=before, length=length, after=drum.balance, part=part, seq=seq)
        allocs.append(a)
        return a

    can_split = lambda x: use_split and x.lot.split_allowed
    for d in demands:
        remaining = d.length
        mine: list[Alloc] = []
        while remaining > EPS:
            open_drums = [x for x in drums if x.opened and not x.closed]
            fresh = [x for x in drums if not x.opened]
            whole = next((x for x in open_drums if x.balance + EPS >= remaining), None)
            if whole is not None:
                mine.append(take(whole, d, remaining, len(mine) + 1))
                remaining = 0
                continue
            part = next((x for x in open_drums if can_split(x) and x.balance > EPS), None)
            if part is not None:
                mine.append(take(part, d, part.balance, len(mine) + 1))
                remaining -= mine[-1].length
                continue
            new = next((x for x in fresh if x.usable + EPS >= remaining), None)
            if new is not None:
                mine.append(take(new, d, remaining, len(mine) + 1))
                remaining = 0
                continue
            new = next((x for x in fresh if can_split(x)), None)
            if new is not None:
                mine.append(take(new, d, min(new.balance, remaining), len(mine) + 1))
                remaining -= mine[-1].length
                continue
            if not mine and not any(can_split(x) for x in drums):
                reason = "no drum of this type is long enough and splitting is not allowed"
            elif mine:
                reason = "the drums of this type are used up"
            else:
                reason = "no drum of this type has enough length left"
            seq += 1
            allocs.append(Alloc(group=group, drum=None, demand=d, before=0, length=0, after=0, part=len(mine) + 1, seq=seq,
                                unallocated=remaining, note=f"SHORTAGE {fmt(remaining)} m - {reason}"))
            mine.append(allocs[-1])
            remaining = 0
        for a in mine:
            a.parts = len(mine)
    return allocs, seq


@dataclass
class Result:
    settings: dict
    allocations: list[Alloc]
    drums: list[Drum]
    demands: list[Demand]
    lots: list[Lot]
    groups: list[dict]
    issues: list[Issue]
    info: dict
    unrequested: list = field(default_factory=list)       # Drum Master lots no IODB cable asked for


def build_schedule(demands: list[Demand], lots: list[Lot], issues: list[Issue], min_residual: float = DEFAULT_MIN_RESIDUAL,
                   use_master_split: bool = True, info: Optional[dict] = None) -> Result:
    min_residual = check_settings(min_residual)
    issues = list(issues)
    drums = build_drums(lots)
    by_group: "OrderedDict[tuple[str, str], list[Demand]]" = OrderedDict()
    for d in demands:
        by_group.setdefault(d.key, []).append(d)
    lot_groups: dict[tuple[str, str], list[Drum]] = {}
    for dr in drums:
        for k in dr.lot.keys:
            lot_groups.setdefault((k, dr.lot.is_nis), []).append(dr)
    # a drum belongs to one group (one lot may be listed under type and size spellings - de-duplicated by identity)
    allocs: list[Alloc] = []
    groups: list[dict] = []
    seq = 0
    used_group_drums: set[int] = set()
    all_keys = list(by_group.keys())
    for key in all_keys:
        ds = by_group[key]
        gdrums = [x for x in lot_groups.get(key, []) if id(x) not in used_group_drums]
        label = ds[0].cable_type + (f" - {key[1]}" if key[1] else "")
        required = sum(d.length for d in ds)
        if not gdrums:
            others = sorted({dr.lot.is_nis or "no IS/NIS" for k, v in lot_groups.items() if k[0] == key[0] for dr in v})
            why = (f"No matching drum available for cable type {ds[0].cable_type}" + (f" with IS/NIS '{key[1]}'" if key[1] else "") + ".")
            if others and key[1] not in others:
                why += f" The Drum Master has this cable type only for: {', '.join(others)} (not substituted)."
            issues.append(Issue("ERROR", "SCHEDULE", "Not matched", label, why))
            for d in ds:
                seq += 1
                allocs.append(Alloc(group=key, drum=None, demand=d, before=0, length=0, after=0, seq=seq, unallocated=d.length,
                                    note="NOT MATCHED - " + why))
            groups.append(dict(key=key, label=label, cable_type=ds[0].cable_type, is_nis=key[1], required=required, available=0.0,
                               allocated=0.0, shortage=required, excess=0.0, drums=0, drums_used=0, status="NOT MATCHED",
                               tags=len(ds), message=why))
            continue
        for x in gdrums:
            used_group_drums.add(id(x))
        a, seq = _allocate_group(key, ds, gdrums, min_residual, use_master_split, seq)
        allocs += a
        allocated = sum(x.length for x in a)
        available = sum(x.usable for x in gdrums)
        shortage = sum(x.unallocated for x in a)
        remaining = sum(x.balance for x in gdrums)
        used = sum(1 for x in gdrums if x.opened)
        status = "SHORTAGE" if shortage > EPS else "ALLOCATED"
        msg = ""
        if shortage > EPS:
            msg = f"SHORTAGE: {label} - additional {fmt(shortage)} m required."
            issues.append(Issue("ERROR", "SCHEDULE", "Shortage", label, msg))
        elif remaining > EPS:
            msg = f"EXCESS AVAILABLE: {label} - {fmt(remaining)} m remaining after scheduling."
        groups.append(dict(key=key, label=label, cable_type=ds[0].cable_type, is_nis=key[1], required=required, available=available,
                           allocated=allocated, shortage=shortage, excess=remaining, drums=len(gdrums), drums_used=used,
                           status=status, tags=len(ds), message=msg))
    unrequested = [lot for lot in lots if not any(id(dr) in used_group_drums for dr in drums if dr.lot is lot)]
    for lot in unrequested:
        issues.append(Issue("INFO", "SCHEDULE", "Drum type not required", lot.master_id,
                            f"{lot.size or lot.cable_type} {lot.is_nis or ''}: {lot.qty} x {fmt(lot.length)} m available, no IODB demand."))
    _verify(groups, allocs, drums)
    # keep each drum's rows together in allocation order (running balance reads top to bottom)
    order = {k: i for i, k in enumerate(all_keys)}
    allocs.sort(key=lambda a: (order[a.group], 1 if a.drum is None else 0, a.drum.order if a.drum else 0, a.seq))
    return Result(settings={"min_residual": min_residual, "use_master_split": use_master_split, "exact_is_nis": True},
                  allocations=allocs, drums=drums, demands=demands, lots=lots, groups=groups, issues=issues, info=info or {},
                  unrequested=unrequested)


def _verify(groups, allocs, drums):
    """Engineering safety: every metre is accounted for."""
    for g in groups:
        if abs(g["required"] - g["allocated"] - g["shortage"]) > 1e-6:
            raise DrumError(f"Internal check failed for {g['label']}: required != allocated + shortage.")
    for dr in drums:
        if abs(dr.usable - dr.allocated - dr.balance) > 1e-6 or dr.balance < -1e-9:
            raise DrumError(f"Internal check failed for drum {dr.drum_id}: usable != allocated + remaining.")


def run(df, drum_master_bytes: bytes, min_residual: float = DEFAULT_MIN_RESIDUAL, use_master_split: bool = True) -> Result:
    min_residual = check_settings(min_residual)
    demands, d_issues, d_stats = extract_demand(df)
    lots, m_issues, m_info = read_drum_master(drum_master_bytes)
    res = build_schedule(demands, lots, d_issues + m_issues, min_residual, use_master_split, {"demand": d_stats, "master": m_info})
    return res


# ── report tables (JSON friendly; also feed the workbook) ───────────────────
STATUS_ORDER = ("EXHAUSTED", "ALLOCATED", "PARTIALLY ALLOCATED", "AVAILABLE")


def drum_status(dr: Drum) -> str:
    if not dr.opened:
        return "AVAILABLE"
    if dr.balance <= EPS:
        return "EXHAUSTED"
    return "ALLOCATED" if dr.closed else "PARTIALLY ALLOCATED"


def row_description(d: Demand) -> str:
    """Same wording as the reference sheet: 'FIELD TO AJB' (branch) / 'JB TO PLC' (main)."""
    jb = d.jb or "JB"
    return f"FIELD TO {jb}" if d.category == "BRANCH" else f"{jb} TO PLC"


def schedule_rows(res: Result) -> list[dict]:
    """One row per allocation. Status words are those of the reference sheet (AVAILABLE / USED / EMPTY) plus
    SHORTAGE / NOT MATCHED for cable that no drum could take."""
    rows = []
    for i, a in enumerate(res.allocations, 1):
        d, dr = a.demand, a.drum
        remarks = []
        if dr is None:
            status = "NOT MATCHED" if a.note.startswith("NOT MATCHED") else "SHORTAGE"
        elif a.after <= EPS:
            status = "EMPTY"
        elif a.after <= res.settings["min_residual"] + EPS:
            status = "USED"
            remarks.append(f"Drum closed at {fmt(a.after)} m residual")
        else:
            status = "AVAILABLE"
        if a.parts > 1 and dr is not None:
            remarks.append(f"Split {a.part}/{a.parts}")
        if a.note:
            remarks.append(a.note)
        trace = f"IODB row {d.row}" + (f" (+{len(d.rows) - 1} more)" if len(d.rows) > 1 else "")
        if dr is not None:
            trace += f"; {dr.lot.master_id} (Drum Master row {dr.lot.row})"
        rows.append({
            "sl": i, "drum_id": dr.drum_id if dr else "", "master_id": dr.lot.master_id if dr else "",
            "master_row": dr.lot.row if dr else None, "cable_type": (dr.lot.cable_type or dr.lot.size) if dr else d.cable_type,
            "description": row_description(d), "cable_tag": d.tag, "category": d.category, "is_nis": d.is_nis or "-",
            "manufacturer": dr.lot.vendor if dr else "", "drum_length": fmt(dr.lot.length) if dr else None,
            "usable": fmt(dr.usable) if dr else None, "before": fmt(a.before) if dr else None, "allocated": fmt(a.length),
            "after": fmt(a.after) if dr else None, "unallocated": fmt(a.unallocated) if a.unallocated else 0,
            "required": fmt(d.length), "status": status,
            "source": trace.split(";")[0], "reference": d.reference, "remarks": "; ".join([trace] + remarks),
        })
    return rows


def type_summary(res: Result) -> list[dict]:
    out = [dict(cable_type=g["cable_type"], is_nis=g["is_nis"] or "-", tags=g["tags"], required=fmt(g["required"]),
                available=fmt(g["available"]), allocated=fmt(g["allocated"]), balance=fmt(g["excess"]),
                shortage=fmt(g["shortage"]), excess=fmt(g["excess"]), drums=g["drums"], drums_used=g["drums_used"],
                status=g["status"], message=g["message"]) for g in res.groups]
    seen: dict[tuple[str, str], dict] = {}
    for lot in res.unrequested:                             # master types nobody needs
        k = (cable_key(lot.size or lot.cable_type), lot.is_nis)
        t = seen.setdefault(k, dict(cable_type=lot.size or lot.cable_type, is_nis=lot.is_nis or "-", tags=0, required=0, available=0,
                                    allocated=0, balance=0, shortage=0, excess=0, drums=0, drums_used=0, status="NOT REQUIRED",
                                    message="No IODB demand for this cable type."))
        t["available"] = t["balance"] = t["excess"] = fmt(t["available"] + lot.length * lot.qty)
        t["drums"] += lot.qty
    return out + list(seen.values())


def utilization(res: Result) -> list[dict]:
    return [dict(drum_id=d.drum_id, master_id=d.lot.master_id, cable_type=d.lot.size or d.lot.cable_type, is_nis=d.lot.is_nis or "-",
                 vendor=d.lot.vendor, original=fmt(d.lot.length), usable=fmt(d.usable), allocated=fmt(d.allocated),
                 remaining=fmt(d.balance), status=drum_status(d), cables=len({a.demand.tag for a in res.allocations if a.drum is d}))
            for d in res.drums]


def shortage_report(res: Result) -> list[dict]:
    return [dict(cable_type=g["cable_type"], is_nis=g["is_nis"] or "-", required=fmt(g["required"]), available=fmt(g["available"]),
                 allocated=fmt(g["allocated"]), shortage=fmt(g["shortage"]), drums_consumed=g["drums_used"],
                 remaining_balance=fmt(g["excess"]), status=g["status"], message=g["message"])
            for g in res.groups if g["shortage"] > EPS]


def excess_report(res: Result) -> dict:
    util = utilization(res)
    unused = [u for u in util if u["status"] == "AVAILABLE"]
    partial = [u for u in util if u["status"] in ("PARTIALLY ALLOCATED", "ALLOCATED") and u["remaining"] > 0]
    by_type = [dict(cable_type=s["cable_type"], is_nis=s["is_nis"], excess=s["excess"], message=s["message"])
               for s in type_summary(res) if s["excess"] > 0]
    return {"unused_drums": unused, "partial_drums": partial, "by_type": by_type}


def exceptions(res: Result) -> list[dict]:
    order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    return [dict(severity=i.severity, source=i.source, kind=i.kind, ref=i.ref, message=i.message)
            for i in sorted(res.issues, key=lambda i: (order[i.severity], i.source, i.kind))]


def progress(res: Result) -> list[dict]:
    return [dict(label=g["label"], status="Completed" if g["status"] == "ALLOCATED" else ("Not matched" if g["status"] == "NOT MATCHED" else "Shortage"),
                 detail=g["message"]) for g in res.groups]


def payload(res: Result, max_rows: int = 5000) -> dict:
    rows = schedule_rows(res)
    exc = exceptions(res)
    return {
        "settings": res.settings, "info": res.info,
        "totals": {"required": fmt(sum(g["required"] for g in res.groups)), "allocated": fmt(sum(g["allocated"] for g in res.groups)),
                   "shortage": fmt(sum(g["shortage"] for g in res.groups)),
                   "remaining": fmt(sum(d.balance for d in res.drums)), "drums": len(res.drums),
                   "drums_used": sum(1 for d in res.drums if d.opened), "rows": len(rows),
                   "errors": sum(1 for e in exc if e["severity"] == "ERROR"), "warnings": sum(1 for e in exc if e["severity"] == "WARNING")},
        "progress": progress(res), "schedule": rows[:max_rows], "schedule_truncated": len(rows) > max_rows,
        "summary": type_summary(res), "utilization": utilization(res), "shortage": shortage_report(res),
        "excess": excess_report(res), "exceptions": exc,
    }


# ── workbook (layout of the reference DRUM SCHEDULE / DRUM MASTER sheets) ───
_HEAD_FILL = PatternFill("solid", start_color="163A5F", end_color="163A5F")
_THIN = Side(style="thin", color="B7C3D0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
STATUS_LIST = "AVAILABLE,RESERVED,HOLD,USED,DAMAGED,EMPTY,SHORTAGE,NOT MATCHED"


def _report_sheet(wb, title, headers, rows, widths=None, note=None):
    """Report sheets share the look of the reference sheets: dark title bar, white bold header, Carlito 10 body."""
    ws = wb.create_sheet(title)
    n = len(headers)
    ws.cell(1, 1, title).font = Font(name="Carlito", size=15, bold=True, color="FFFFFF")
    for c in range(1, n + 1):
        ws.cell(1, c).fill = _HEAD_FILL
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n)
    ws.cell(1, 1).alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 26.1
    if note:
        ws.cell(2, 1, note).font = Font(name="Carlito", size=10, italic=True, color="1F2937")
    for c, h in enumerate(headers, 1):
        cell = ws.cell(3, c, h)
        cell.font, cell.fill, cell.alignment = Font(name="Carlito", size=11, bold=True, color="FFFFFF"), _HEAD_FILL, _CENTER
    ws.row_dimensions[3].height = 36
    for i, row in enumerate(rows, 4):
        for c, v in enumerate(row, 1):
            cell = ws.cell(i, c, v)
            cell.font, cell.alignment, cell.border = Font(name="Carlito", size=10, color="1F2937"), _CENTER, _BORDER
    for c in range(1, n + 1):
        w = (widths or {}).get(c)
        if w is None:
            longest = max([len(str(headers[c - 1]))] + [len(str(r[c - 1])) for r in rows[:200] if c - 1 < len(r) and r[c - 1] is not None])
            w = min(max(12, longest + 2), 60)
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A4"
    return ws


def _fill_reference_sheet(ws, rows: list[list], ncols: int, first_row: int = 4):
    """Write rows below the header of a reference sheet, row styles copied from its first data row."""
    proto = {c: copy(ws.cell(first_row, c)._style) for c in range(1, ncols + 1)}
    height = ws.row_dimensions[first_row].height
    for i, row in enumerate(rows):
        r = first_row + i
        for c in range(1, ncols + 1):
            cell = ws.cell(r, c)
            cell._style = copy(proto[c])
            cell.value = row[c - 1] if c - 1 < len(row) else None
        if height:
            ws.row_dimensions[r].height = height
    return first_row + max(len(rows), 1) - 1


def to_workbook(res: Result) -> bytes:
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.worksheet.datavalidation import DataValidation
    if not TEMPLATE_PATH.exists():
        raise DrumError("The Drum Schedule layout (reference workbook) is missing on the server.")
    wb = openpyxl.load_workbook(TEMPLATE_PATH)
    note = settings_note(res)
    rows = schedule_rows(res)

    # ── DRUM SCHEDULE: the reference columns, running balance as the reference formulas ──
    ws = wb["DRUM SCHEDULE"]
    body, prev = [], None
    for k, r in enumerate(rows):
        excel_row = 4 + k
        first_of_drum = r["drum_id"] != prev
        if r["drum_id"]:
            usable = r["usable"] if first_of_drum else f"=J{excel_row - 1}"
            avail = f"=MAX(0,H{excel_row}-I{excel_row})"
        else:
            usable = avail = None
        body.append([r["drum_id"] or "NO DRUM", r["cable_type"], r["description"], r["cable_tag"],
                     r["is_nis"] if r["is_nis"] in ("IS", "NIS") else "NA", r["manufacturer"] or None,
                     r["drum_length"], usable, r["allocated"], avail, r["status"], r["remarks"]])
        prev = r["drum_id"] or None
    last = _fill_reference_sheet(ws, body, 12)
    last = max(last, 302)
    for rr in range(4 + len(body), last + 1):                      # the reference sheet keeps styled blank rows
        for c in range(1, 13):
            ws.cell(rr, c)._style = copy(ws.cell(4, c)._style)
    ws.data_validations.dataValidation = []
    for col, formula in (("E", '"IS,NIS,BOTH,NA"'), ("K", f'"{STATUS_LIST}"')):
        dv = DataValidation(type="list", formula1=formula, allow_blank=False)
        dv.add(f"{col}4:{col}{last}")
        ws.add_data_validation(dv)
    from openpyxl.formatting.formatting import ConditionalFormattingList
    ws.conditional_formatting = ConditionalFormattingList()
    ws.conditional_formatting.add(f"J4:J{last}", CellIsRule(operator="lessThanOrEqual", formula=["20"],
                                                            fill=PatternFill(bgColor="FFF4CC", fill_type="solid")))
    ws.cell(2, 1, note).font = Font(name="Carlito", size=10, italic=True, color="1F2937")
    wb.calculation.fullCalcOnLoad = True

    # ── DRUM MASTER (same columns as the input) ──
    wm = wb["DRUM MASTER"]
    _fill_reference_sheet(wm, [[l.master_id, l.cable_type, l.size, l.is_nis or "NA", l.unit, fmt(l.length), l.qty, fmt(l.length * l.qty),
                                "YES" if l.split else "NO", {True: "YES", False: "NO", None: None}[l.no_splice_default], l.vendor or None,
                                l.drum_type or None, l.weight_limit or None, l.tolerance or None, l.remarks or None]
                               for l in res.lots], 15)
    wm.cell(2, 1, f"Drum Master records used for this schedule ({len(res.lots)} records, {sum(l.qty for l in res.lots)} drums).").font = \
        Font(name="Carlito", size=10, italic=True, color="1F2937")

    # ── traceability + reports ──
    _report_sheet(wb, "DRUM SCHEDULE - TRACE",
                  ["SL. No.", "DRUM ID", "DRUM MASTER ID", "DRUM MASTER ROW", "CABLE TYPE", "CABLE TAG NUMBER", "CABLE CATEGORY",
                   "IS / NIS", "REQUIRED (M)", "AVAILABLE BEFORE ALLOCATION (M)", "ALLOCATED LENGTH (M)",
                   "AVAILABLE AFTER ALLOCATION (M)", "UNALLOCATED (M)", "STATUS", "SOURCE IODB REFERENCE",
                   "INSTRUMENT / EQUIPMENT REFERENCE", "REMARKS"],
                  [[r["sl"], r["drum_id"] or "NO DRUM", r["master_id"] or "-", r["master_row"], r["cable_type"], r["cable_tag"],
                    r["category"], r["is_nis"], r["required"], r["before"], r["allocated"], r["after"], r["unallocated"], r["status"],
                    r["source"], r["reference"], r["remarks"]] for r in rows], widths={16: 36, 17: 50}, note=note)
    ts = type_summary(res)
    _report_sheet(wb, "CABLE TYPE SUMMARY", ["CABLE TYPE", "IS / NIS", "CABLE TAGS", "REQUIRED (M)", "AVAILABLE (M)", "ALLOCATED (M)",
                                             "BALANCE (M)", "SHORTAGE (M)", "EXCESS (M)", "DRUMS", "DRUMS USED", "STATUS", "MESSAGE"],
                  [[t["cable_type"], t["is_nis"], t["tags"], t["required"], t["available"], t["allocated"], t["balance"], t["shortage"],
                    t["excess"], t["drums"], t["drums_used"], t["status"], t["message"]] for t in ts], widths={13: 60}, note=note)
    ut = utilization(res)
    _report_sheet(wb, "DRUM UTILIZATION", ["DRUM ID", "DRUM MASTER ID", "CABLE TYPE", "IS / NIS", "MANUFACTURER", "ORIGINAL LENGTH (M)",
                                           "USABLE LENGTH (M)", "ALLOCATED (M)", "REMAINING (M)", "CABLE TAGS", "STATUS"],
                  [[u["drum_id"], u["master_id"], u["cable_type"], u["is_nis"], u["vendor"] or "-", u["original"], u["usable"],
                    u["allocated"], u["remaining"], u["cables"], u["status"]] for u in ut], note=note)
    sh = shortage_report(res)
    _report_sheet(wb, "SHORTAGE REPORT", ["CABLE TYPE", "IS / NIS", "TOTAL REQUIRED (M)", "TOTAL AVAILABLE (M)", "TOTAL ALLOCATED (M)",
                                          "SHORTAGE (M)", "DRUMS CONSUMED", "REMAINING USABLE BALANCE (M)", "STATUS", "MESSAGE"],
                  [[x["cable_type"], x["is_nis"], x["required"], x["available"], x["allocated"], x["shortage"], x["drums_consumed"],
                    x["remaining_balance"], x["status"], x["message"]] for x in sh] or [["No shortage", "", "", "", "", "", "", "", "", ""]],
                  widths={10: 60}, note=note)
    ex = excess_report(res)
    ex_rows = ([["EXCESS BY TYPE", e["cable_type"], e["is_nis"], "", "", e["excess"], e["message"]] for e in ex["by_type"]]
               + [["UNUSED DRUM", u["cable_type"], u["is_nis"], u["drum_id"], u["usable"], u["remaining"], u["status"]] for u in ex["unused_drums"]]
               + [["PARTLY USED DRUM", u["cable_type"], u["is_nis"], u["drum_id"], u["usable"], u["remaining"], u["status"]] for u in ex["partial_drums"]])
    _report_sheet(wb, "EXCESS - BALANCE REPORT", ["KIND", "CABLE TYPE", "IS / NIS", "DRUM ID", "USABLE (M)", "REMAINING / EXCESS (M)", "STATUS / MESSAGE"],
                  ex_rows or [["Nothing left over", "", "", "", "", "", ""]], widths={7: 60}, note=note)
    exc = exceptions(res)
    _report_sheet(wb, "VALIDATION - EXCEPTIONS", ["SEVERITY", "SOURCE", "KIND", "REFERENCE", "MESSAGE"],
                  [[e["severity"], e["source"], e["kind"], e["ref"], e["message"]] for e in exc] or [["OK", "", "", "", "No exceptions"]],
                  widths={5: 90}, note=note)
    order = ["DRUM SCHEDULE", "DRUM SCHEDULE - TRACE", "CABLE TYPE SUMMARY", "DRUM UTILIZATION", "SHORTAGE REPORT",
             "EXCESS - BALANCE REPORT", "VALIDATION - EXCEPTIONS", "DRUM MASTER"]
    wb._sheets = [wb[n] for n in order]
    wb.active = 0
    for w in wb.worksheets:
        w.sheet_view.tabSelected = w.title == "DRUM SCHEDULE"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def settings_note(res: Result) -> str:
    st = res.settings
    return (f"Minimum residual {fmt(st['min_residual'])} m | Drum Master split rule {'used' if st['use_master_split'] else 'off (no splitting)'} | "
            "Exact cable type + IS/NIS matching | Shared main cables counted once")
