"""
gland_quantity.py - gland quantities from an uploaded Cable Schedule workbook.

    workbook -> cable-schedule sheets (found by their headers) -> gland occurrences (cable tag, location, size, qty ...)
             -> aggregation -> summaries by gland / cable type / location + exceptions

Rules kept from the specification:
  * the schedule's own gland values are the project values and are never changed;
  * a quantity is used exactly as stated; a size without a quantity is flagged (a default applies only when the
    project settings say so);
  * a cable tag is never dropped: it can have several locations. Identical termination rows of a shared cable are
    counted once by default (switchable) and always reported;
  * nothing is read from or written to the uploaded file - it is opened for reading only.
"""
from __future__ import annotations

import io
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

import openpyxl
from openpyxl.utils import get_column_letter

from .drum_schedule import cable_key


class GlandError(Exception):
    """User-facing problem with the uploaded schedule."""


# ── gland designation parsing ────────────────────────────────────────────────
_FRAC = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8"}


def _clean_text(v: Any) -> str:
    t = str(v if v is not None else "").replace("\xa0", " ").strip()
    for k, r in _FRAC.items():
        t = re.sub(rf"(\d)\s*{k}", rf"\1 {r}", t)
        t = t.replace(k, r)
    return re.sub(r"\s+", " ", t.replace("”", '"').replace("“", '"').replace("″", '"').replace("''", '"'))


def parse_gland(value: Any) -> dict:
    """'M20' / '1/2" NPT' / '1 1/4" NPT' / 'ET 20' / 'G 1/2' / '20' -> {std, size, label}. std = METRIC | NPT | BSP | ET | '' (not stated)."""
    t = _clean_text(value)
    u = t.upper()
    m = re.match(r"^M\s*(\d+(?:\.\d+)?)(?:\s*[xX*]\s*[\d.]+)?$", u)
    if m:
        return {"std": "METRIC", "size": f"M{m.group(1)}", "label": f"M{m.group(1)}"}
    m = re.search(r"\bET\s*[-]?\s*(\d+(?:/\d+)?)\b|(\d+(?:[ -]\d+/\d+|/\d+)?)\s*(\")?\s*[-]?\s*ET\b", u)
    if m:
        if m.group(1):
            return {"std": "ET", "size": f"ET{m.group(1)}", "label": f"ET {m.group(1)}"}
        n = re.sub(r"\s+", "-", m.group(2).strip().replace("-", " "))
        return {"std": "ET", "size": f'{n}"' if m.group(3) or "/" in n else n, "label": f'{n}" ET' if m.group(3) or "/" in n else f"ET {n}"}
    frac = r'(\d+(?:[ -]\d+/\d+|/\d+)?)\s*"?'
    for std, words in (("NPT", r"NPT"), ("BSP", r"BSP[PT]?|BSPT|\bG\b|\bR[CP]?\b")):
        m = re.search(rf"{frac}\s*-?\s*(?:{words})\b", u) or re.search(rf"(?:{words})\b\s*{frac}", u)
        if m:
            size = m.group(1).replace("-", " ")
            norm = re.sub(r"\s+", "-", size.strip())
            return {"std": std, "size": f'{norm}"', "label": f'{norm}" {std}'}
    m = re.match(r"^G\s*(\d+(?:/\d+)?)$", u)
    if m:
        return {"std": "BSP", "size": f'{m.group(1)}"', "label": f'{m.group(1)}" BSP'}
    m = re.match(r"^(\d+(?:\.\d+)?)$", u)
    if m:
        return {"std": "", "size": m.group(1), "label": m.group(1)}
    return {"std": "", "size": t, "label": t}


def is_blank(v: Any) -> bool:
    t = _clean_text(v).upper()
    return t in ("", "-", "--", "NA", "N/A", "NIL", "NONE", "NAN")


def is_tba(v: Any) -> bool:
    return _clean_text(v).upper() in ("TBA", "TBD")


def qty_of(v: Any) -> tuple[Optional[float], str]:
    """(quantity, 'ok' | 'blank' | 'invalid')."""
    t = _clean_text(v)
    if t.upper() in ("", "-", "--", "NA", "N/A", "TBA", "TBD", "NAN"):
        return None, "blank"
    try:
        q = float(t)
    except ValueError:
        return None, "invalid"
    return (q, "ok") if q > 0 and q == q else (None, "invalid")


def guess_construction(text: str) -> str:
    u = (text or "").upper()
    if re.search(r"UNARM|NON[- ]?ARM", u):
        return "UNARMOURED"
    if re.search(r"\bARM|SWA|\bSTA\b|\bAWA\b|ARMOUR", u):
        return "ARMOURED"
    if "BRAID" in u:
        return "BRAIDED"
    if "FLEX" in u:
        return "FLEXIBLE"
    if "FLAT" in u:
        return "FLAT"
    return "UNARMOURED"


def construction_is_stated(text: str) -> bool:
    return bool(re.search(r"ARM|SWA|\bSTA\b|AWA|BRAID|FLEX|FLAT", (text or "").upper()))


# ── locations ────────────────────────────────────────────────────────────────
def location_of(label: str) -> str:
    u = label.upper()
    for pat, name in ((r"INSTRUMENT|FIELD|TRANSMITTER", "Instrument Side"), (r"\bJB\b|JUNCTION", "JB Side"), (r"PANEL|PLC|RIO|MARSHALL|CONTROL DESK", "Panel Side"),
                      (r"\bMCC\b", "MCC Side"), (r"\bVFD\b", "VFD Side"), (r"\bLCP\b", "LCP Side"), (r"\bMOV\b", "MOV Side")):
        if re.search(pat, u):
            return name
    return "Other"


LOCATIONS = ["Instrument Side", "JB Side", "Panel Side", "MCC Side", "VFD Side", "LCP Side", "MOV Side", "Other"]


# ── reading the workbook ─────────────────────────────────────────────────────
@dataclass
class SheetMap:
    sheet: str
    header_rows: tuple[int, int]
    first_row: int
    glands: "OrderedDict[tuple[str, str], dict]"           # (location, role) -> {size, qty, label}
    cols: dict                                              # generic columns: tag_row, desc, cable_tag_{branch,main,gen}, type_*, od, gland_type, thread, material, cert, remarks
    notes: list = field(default_factory=list)


def _label_cells(ws, r1: int, r2: Optional[int]) -> dict[int, str]:
    out = {}
    for c in range(1, min(ws.max_column, 150) + 1):
        top = _clean_text(ws.cell(*anchor_of(ws, r1, c)).value)
        sub = _clean_text(ws.cell(*anchor_of(ws, r2, c)).value) if r2 else ""
        lab = f"{top} {sub}".strip()
        if lab:
            out[c] = re.sub(r"\s+", " ", lab).upper()
    return out


def anchor_of(ws, r: int, c: int) -> tuple[int, int]:
    for m in ws.merged_cells.ranges:
        if m.min_row <= r <= m.max_row and m.min_col <= c <= m.max_col:
            return m.min_row, m.min_col
    return r, c


def _row_labels(ws, r: int) -> list[str]:
    return [_clean_text(ws.cell(*anchor_of(ws, r, c)).value).upper() for c in range(1, min(ws.max_column, 150) + 1)]


_SUBHEAD = re.compile(r"^(GLAND\s+)?(SIZE|QTY\.?|QUANTITY|TYPE|THREAD|MATERIAL)\b|\bQTY\b|GLAND (SIZE|QTY)")


def find_header(ws) -> Optional[tuple[int, Optional[int], dict[int, str]]]:
    """(top header row, sub-header row or None, {column: 'TOP SUB' label}). The row that holds the word GLAND anchors it."""
    for r in range(1, min(ws.max_row, 40) + 1):
        row = _row_labels(ws, r)
        if len([t for t in row if t]) < 3 or not any("GLAND" in t for t in row):
            continue
        gl = [t for t in row if "GLAND" in t]
        if r > 1 and all(location_of(t) == "Other" for t in gl):          # 'GLAND SIZE' under a location row above
            above = _row_labels(ws, r - 1)
            if len([t for t in above if t]) >= 2:
                labels = _label_cells(ws, r - 1, r)
                return r - 1, r, labels
        nxt = _row_labels(ws, r + 1) if r < ws.max_row else []
        if len([t for t in nxt if t and _SUBHEAD.search(t)]) >= 2:
            return r, r + 1, _label_cells(ws, r, r + 1)
        return r, None, _label_cells(ws, r, None)
    return None


def classify_columns(labels: dict[int, str]) -> tuple["OrderedDict", dict]:
    glands: "OrderedDict[tuple[str, str], dict]" = OrderedDict()
    cols: dict = {}
    for c, lab in labels.items():
        u = lab
        if "GLAND" in u:
            if re.search(r"\bQTY\b|QUANTITY|\bNOS?\b\.?\)?$|QTY\.", u):
                kind = "qty"
            elif re.search(r"\bTYPE\b", u):
                kind = "gland_type"
            elif "THREAD" in u:
                kind = "thread"
            elif "MATERIAL" in u:
                kind = "material"
            elif re.search(r"CERT|\bEX\b", u):
                kind = "cert"
            else:
                kind = "size"
            loc = location_of(u)
            if kind in ("gland_type", "thread", "material", "cert") and loc == "Other":
                cols.setdefault(kind, c)
                continue
            role = "branch" if loc == "Instrument Side" else ("main" if (loc == "JB Side" and re.search(r"\bEND\b", u)) else ("branch" if loc == "JB Side" else "gen"))
            if loc == "Panel Side" and re.search(r"\bEND\b", u):
                role = "main"
            key = (loc, role)
            ent = glands.setdefault(key, {"label": lab})
            ent.setdefault(kind, c)
            continue
        if re.search(r"CABLE (TAG|NO|NUMBER)|CABLE TAG", u) and "TYPE" not in u and "LENGTH" not in u:
            role = "main" if "MAIN" in u else ("branch" if re.search(r"INSTRUMENT TO JB|BRANCH", u) else "gen")
            cols.setdefault(f"cable_tag_{role}", c)
        elif re.search(r"CABLE TYPE|CABLE SIZE", u) or re.fullmatch(r"INSTRUMENT TO JB CABLE", u):
            role = "main" if "MAIN" in u else ("branch" if re.search(r"INSTRUMENT TO JB|BRANCH", u) else "gen")
            cols.setdefault(f"type_{role}", c)
        elif re.search(r"CABLE OD|OVERALL (CABLE )?DIA|\bOD\b", u):
            cols.setdefault("od", c)
        elif re.search(r"^(TAG (NO|NUMBER)|INSTRUMENT TAG|TAG)\b|MOTOR TAG|^FROM\b", u) and "CABLE" not in u:
            cols.setdefault("tag_row", c)
        elif re.search(r"DESCRIPTION", u):
            cols.setdefault("desc", c)
        elif re.search(r"^REMARKS?\b", u):
            cols.setdefault("remarks", c)
    return glands, cols


def detect_sheets(wb) -> list[dict]:
    out = []
    for ws in wb.worksheets:
        info = {"sheet": ws.title, "hidden": ws.sheet_state != "visible", "used": False, "reason": ""}
        try:
            h = find_header(ws)
        except Exception as exc:                                      # a sheet that cannot be read is skipped, never fatal
            info["reason"] = f"could not be read ({exc})"
            out.append(info)
            continue
        if not h:
            info["reason"] = "no gland columns found"
            out.append(info)
            continue
        r1, r2, labels = h
        glands, cols = classify_columns(labels)
        sized = [k for k, v in glands.items() if "size" in v]
        if not sized:
            info["reason"] = "no gland size column"
            out.append(info)
            continue
        info.update(used=True, header_row=r1, gland_columns=[f"{k[0]}" for k in sized], has_cable_tag=any(k.startswith("cable_tag") for k in cols),
                    reason="cable schedule with gland columns")
        out.append(info)
    return out


class _Reader:
    """Cell values with formulas resolved: cached value first, then a plain '=K9' style reference."""

    def __init__(self, data: bytes):
        try:
            self.wf = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
            self.wv = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        except Exception as exc:
            raise GlandError("The uploaded file could not be opened as an Excel workbook (.xlsx).") from exc
        self.unresolved = 0

    def value(self, sheet: str, r: int, c: int, depth: int = 0):
        v = self.wv[sheet].cell(r, c).value
        if v is not None:
            return v
        f = self.wf[sheet].cell(r, c).value
        if isinstance(f, str) and f.startswith("="):
            m = re.fullmatch(r"=\s*\$?([A-Z]{1,3})\$?(\d+)\s*", f)
            if m and depth < 5:
                from openpyxl.utils import column_index_from_string
                return self.value(sheet, int(m.group(2)), column_index_from_string(m.group(1)), depth + 1)
            self.unresolved += 1
            return None
        return f


@dataclass
class Settings:
    default_qty: Optional[float] = None          # project rule for a gland size without a quantity (None = flag it)
    repeated_rows: str = "once"                  # identical termination rows of one cable: "once" | "sum"
    sheets: Optional[list] = None                # restrict to these sheets


@dataclass
class Occurrence:
    sheet: str
    row: int
    cable_tag: str
    tag_known: bool
    role: str
    cable_type: str
    location: str
    raw: str
    std: str
    size: str
    label: str
    qty: Optional[float]
    qty_status: str
    gland_type: str
    material: str
    cert: str
    instrument_tag: str
    description: str
    od: Optional[float]
    flags: list = field(default_factory=list)


def default_sheets(infos: list[dict]) -> list[str]:
    """Visible cable-schedule sheets; hidden template sheets (old project data) only when nothing else exists."""
    vis = [i["sheet"] for i in infos if i["used"] and not i["hidden"]]
    return vis or [i["sheet"] for i in infos if i["used"]]


def extract(data: bytes, settings: Optional[Settings] = None) -> tuple[list[Occurrence], list[dict], list[dict], list[dict]]:
    """-> (occurrences, exceptions, sheet info, cable-type info). Exceptions: {severity, kind, ref, message}."""
    settings = settings or Settings()
    rd = _Reader(data)
    infos = detect_sheets(rd.wf)
    exceptions: list[dict] = []
    occ: list[Occurrence] = []
    type_rows: list[tuple] = []

    def exc(sev, kind, ref, msg):
        exceptions.append({"severity": sev, "kind": kind, "ref": ref, "message": msg})

    wanted = settings.sheets if settings.sheets is not None else default_sheets(infos)
    used = [i for i in infos if i["used"] and i["sheet"] in wanted]
    if not used:
        raise GlandError("No cable schedule sheet with gland columns was found in the uploaded workbook "
                         "(a header row with columns such as 'INSTRUMENT SIDE GLAND' / 'GLAND SIZE' / 'GLAND QTY' is needed).")
    for info in used:
        ws = rd.wv[info["sheet"]]
        r1, r2, labels = find_header(ws)
        glands, cols = classify_columns(labels)
        first = (r2 or r1) + 1

        def val(r, key):
            c = cols.get(key)
            return None if c is None else rd.value(info["sheet"], r, c)

        for r in range(first, ws.max_row + 1):
            if all(rd.wv[info["sheet"]].cell(r, c).value is None and rd.wf[info["sheet"]].cell(r, c).value is None for c in list(labels)[:40]):
                continue
            row_tag = _clean_text(val(r, "tag_row"))
            desc = _clean_text(val(r, "desc"))
            od_raw = val(r, "od")
            od = None
            try:
                od = float(od_raw) if od_raw not in (None, "") and not is_blank(od_raw) else None
            except (TypeError, ValueError):
                od = None
            for trole in ("branch", "main", "gen"):
                if f"type_{trole}" in cols and not is_blank(val(r, f"type_{trole}")) and not is_tba(val(r, f"type_{trole}")):
                    tg = _clean_text(val(r, f"cable_tag_{trole}")) if f"cable_tag_{trole}" in cols else ""
                    type_rows.append((_clean_text(val(r, f"type_{trole}")), tg, od, info["sheet"]))
            for (loc, role), g in glands.items():
                if "size" not in g:
                    continue
                size_raw = rd.value(info["sheet"], r, g["size"])
                if size_raw is None or is_blank(size_raw):
                    continue
                ref = f"{info['sheet']} row {r}"
                if is_tba(size_raw):
                    exc("WARNING", "Gland size TBA", f"{ref} ({loc})", "The gland size is TBA - not counted.")
                    continue
                tag_cols = [f"cable_tag_{role}", "cable_tag_gen", "cable_tag_main", "cable_tag_branch"]
                type_cols = [f"type_{role}", "type_gen", "type_main", "type_branch"]
                tag = next((_clean_text(val(r, k)) for k in tag_cols if k in cols and not is_blank(val(r, k)) and not is_tba(val(r, k))), "")
                ctype = next((_clean_text(val(r, k)) for k in type_cols if k in cols and not is_blank(val(r, k)) and not is_tba(val(r, k))), "")
                known = bool(tag)
                if not known:
                    tag = f"(no cable tag) {info['sheet']}!{row_tag or 'row ' + str(r)}"
                    exc("WARNING", "Missing cable tag", ref, f"{loc} gland '{_clean_text(size_raw)}' has no cable tag number; listed under the row tag.")
                pg = parse_gland(size_raw)
                flags = []
                q, qs = (None, "blank")
                if "qty" in g:
                    q, qs = qty_of(rd.value(info["sheet"], r, g["qty"]))
                if qs != "ok":
                    if settings.default_qty:
                        q, qs = settings.default_qty, "default"
                        flags.append("DEFAULT QUANTITY")
                        exc("INFO", "Default gland quantity used", f"{ref} ({loc})", f"No quantity stated; the project default of {settings.default_qty:g} was used.")
                    else:
                        exc("ERROR", "MISSING GLAND QUANTITY", f"{ref} ({loc})",
                            f"Gland '{pg['label']}' for cable {tag} has "
                            + ("no quantity column." if "qty" not in g else f"an invalid quantity ('{_clean_text(rd.value(info['sheet'], r, g['qty']))}')." if qs == "invalid" else "no quantity.")
                            + " It is not counted.")
                        flags.append("MISSING GLAND QUANTITY")
                if not pg["std"]:
                    exc("WARNING", "Thread not stated", f"{ref} ({loc})", f"Gland '{pg['label']}' does not say Metric / NPT / BSP / ET; it is kept as 'Not stated'.")
                    flags.append("THREAD NOT STATED")
                gt = _clean_text(rd.value(info["sheet"], r, g["gland_type"])) if "gland_type" in g else (_clean_text(val(r, "gland_type")) if "gland_type" in cols else "")
                mat = _clean_text(val(r, "material")) if "material" in cols else ""
                cert = _clean_text(val(r, "cert")) if "cert" in cols else ""
                occ.append(Occurrence(sheet=info["sheet"], row=r, cable_tag=tag, tag_known=known, role=role, cable_type=ctype, location=loc, raw=_clean_text(size_raw),
                                      std=pg["std"], size=pg["size"], label=pg["label"], qty=q, qty_status=qs,
                                      gland_type=gt if not is_blank(gt) else "Not stated", material=mat if not is_blank(mat) else "Not stated",
                                      cert=cert if not is_blank(cert) else "Not stated", instrument_tag=row_tag, description=desc, od=od, flags=flags))
    if rd.unresolved:
        exc("WARNING", "Formula result unavailable", "workbook",
            f"{rd.unresolved} gland/tag cell(s) are formulas without a stored result (the file was written by a tool that does not calculate). "
            "Open and save it in Excel, then upload again; those cells were not counted.")
    return occ, exceptions, infos, _cable_types(occ, type_rows)


def _cable_types(occ: list[Occurrence], type_rows: Optional[list] = None) -> list[dict]:
    types: "OrderedDict[str, dict]" = OrderedDict()
    for ctype, tag, od, sheet in (type_rows or []):
        t = types.setdefault(cable_key(ctype), {"cable_type": ctype, "tags": set(), "glands": OrderedDict(), "od": od, "roles": set(), "sheets": set()})
        if tag:
            t["tags"].add(tag)
        t["sheets"].add(sheet)
        if od and not t["od"]:
            t["od"] = od
    for o in occ:
        if not o.cable_type:
            continue
        k = cable_key(o.cable_type)
        t = types.setdefault(k, {"cable_type": o.cable_type, "tags": set(), "glands": OrderedDict(), "od": o.od, "roles": set(), "sheets": set()})
        t["tags"].add(o.cable_tag)
        t["roles"].add(o.role)
        t["sheets"].add(o.sheet)
        if o.od and not t["od"]:
            t["od"] = o.od
        if o.label and o.qty_status in ("ok", "default"):
            t["glands"][o.label] = t["glands"].get(o.label, 0) + (o.qty or 0)
    out = []
    for k, t in types.items():
        out.append({"key": k, "cable_type": t["cable_type"], "cables": len(t["tags"]), "existing_glands": list(t["glands"]),
                    "od": t["od"], "construction": guess_construction(t["cable_type"]), "construction_stated": construction_is_stated(t["cable_type"]),
                    "sheets": sorted(t["sheets"])})
    return out


# ── aggregation ──────────────────────────────────────────────────────────────
def aggregate(occ: list[Occurrence], settings: Optional[Settings] = None) -> tuple[list[dict], list[dict]]:
    """
    One line per (cable tag, location, gland size, gland type, thread). Identical termination rows of a shared cable are
    counted once (or summed when the project says so) and reported. Returns (lines, exceptions).
    """
    settings = settings or Settings()
    exceptions: list[dict] = []
    groups: "OrderedDict[tuple, list[Occurrence]]" = OrderedDict()
    for o in occ:
        if o.qty_status not in ("ok", "default"):
            continue
        groups.setdefault((o.cable_tag, o.location, o.label, o.gland_type, o.std, o.material, o.cert), []).append(o)
    lines = []
    for key, items in groups.items():
        qtys = [i.qty for i in items]
        if len(items) == 1:
            qty = qtys[0]
        elif settings.repeated_rows == "sum":
            qty = sum(qtys)
            exceptions.append({"severity": "INFO", "kind": "Repeated rows added", "ref": f"{key[0]} / {key[1]}",
                               "message": f"{len(items)} rows give the same {key[2]} gland at this location; their quantities were added ({qty:g})."})
        else:
            qty = qtys[0]
            if len(set(qtys)) > 1:
                qty = max(qtys)
                exceptions.append({"severity": "WARNING", "kind": "Conflicting gland quantity", "ref": f"{key[0]} / {key[1]}",
                                   "message": f"{len(items)} rows give different quantities ({', '.join(f'{q:g}' for q in qtys)}) for the same gland; the largest ({qty:g}) is used."})
            else:
                exceptions.append({"severity": "INFO", "kind": "Shared cable counted once", "ref": f"{key[0]} / {key[1]}",
                                   "message": f"{len(items)} schedule rows carry the same {key[2]} gland at this location of cable {key[0]}; counted once ({qty:g})."})
        first = items[0]
        lines.append({"cable_tag": first.cable_tag, "cable_type": first.cable_type or "Not stated", "location": first.location, "gland_size": first.label,
                      "thread": first.std.title() if first.std else "Not stated", "std": first.std, "gland_type": first.gland_type,
                      "material": first.material, "certification": first.cert, "qty": qty, "role": first.role,
                      "source": f"{first.sheet} row {first.row}" + (f" (+{len(items) - 1} more)" if len(items) > 1 else ""),
                      "instrument_tag": first.instrument_tag, "od": first.od})
    return lines, exceptions


def _tot(lines, keyf):
    out: "OrderedDict[tuple, float]" = OrderedDict()
    for l in lines:
        k = keyf(l)
        out[k] = out.get(k, 0) + l["qty"]
    return out


def _fmtq(q):
    return int(q) if float(q) == int(q) else round(q, 3)


def _size_sort(label: str):
    m = re.search(r"(\d+(?:\.\d+)?)(?:\s+(\d+)/(\d+)|/(\d+))?", label)
    if not m:
        return (9, 0)
    base = float(m.group(1))
    if m.group(2):
        base += int(m.group(2)) / int(m.group(3))
    elif m.group(4):
        base = base / int(m.group(4))
    return ({"M": 0}.get(label[:1], 1), base)


def summaries(lines: list[dict]) -> dict:
    by_gland = _tot(lines, lambda l: (l["gland_type"], l["thread"], l["gland_size"], l["material"], l["certification"]))
    by_type = _tot(lines, lambda l: (l["cable_type"], l["gland_type"], l["thread"], l["gland_size"]))
    cables_by_type = {}
    for l in lines:
        cables_by_type.setdefault((l["cable_type"], l["gland_type"], l["thread"], l["gland_size"]), set()).add(l["cable_tag"])
    by_loc = _tot(lines, lambda l: (l["location"], l["thread"], l["gland_size"]))
    loc_totals = _tot(lines, lambda l: (l["location"],))
    return {
        "by_gland": sorted([dict(gland_type=k[0], thread=k[1], gland_size=k[2], material=k[3], certification=k[4], qty=_fmtq(v)) for k, v in by_gland.items()],
                           key=lambda r: (r["thread"], _size_sort(r["gland_size"]), r["gland_type"])),
        "by_cable_type": sorted([dict(cable_type=k[0], gland_type=k[1], thread=k[2], gland_size=k[3], qty=_fmtq(v), cables=len(cables_by_type[k]))
                                 for k, v in by_type.items()], key=lambda r: (r["cable_type"], _size_sort(r["gland_size"]))),
        "by_location": sorted([dict(location=k[0], thread=k[1], gland_size=k[2], qty=_fmtq(v)) for k, v in by_loc.items()],
                              key=lambda r: (LOCATIONS.index(r["location"]) if r["location"] in LOCATIONS else 99, r["thread"], _size_sort(r["gland_size"]))),
        "location_totals": sorted([dict(location=k[0], qty=_fmtq(v)) for k, v in loc_totals.items()],
                                  key=lambda r: LOCATIONS.index(r["location"]) if r["location"] in LOCATIONS else 99),
        "total_qty": _fmtq(sum(l["qty"] for l in lines)),
    }
