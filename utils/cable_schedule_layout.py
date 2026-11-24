"""
cable_schedule_layout.py - column layout of the generated Cable Schedule sheets (Instrument, MCC DI, MCC DO, VFD).

Applied to the GENERATED workbook after the existing generators have filled it (the generation logic itself is not
changed). Implements the reference 'Cable_Schedule-12' mark-up:

  Instrument Cable Schedule
    * columns marked red are removed (LOOP NUMBER, P&ID NO., SIGNAL TO, IO PANEL, IO TYPE, RACK / NODE, SLOT,
      CHANNEL NO, TERMINAL STRIP NO, TERMINAL NO (CMN / Signal / Zero)); MAIN CABLE LENGTH is kept
    * FERRULE AT PLC (+) and FERRULE AT PLC (-) are removed (Cable_Schedule-13 mark-up): Remarks follows PANEL END
      GLAND SIZE. Only this sheet - the MCC DI / MCC DO / VFD / MOV / LCP sheets keep their own ferrule columns.
    * every tag is ONE 3-row entry: all columns merged over the 3 rows, except
        - TB DETAILS AT JB: three TB numbers, one per row, numbered 1-2-3, 4-5-6, ... within each junction box
        - FERRULE AT INSTRUMENT SIDE: one column, (+) ferrule on the first row, (-) ferrule on the second
  MCC DI / MCC DO / VFD
    * columns marked red are removed (PLC (To), CONTROL DESK TERMINALS block, Signal Type)
    * Cable Length (M) is moved to just before Remarks; Remarks stays the last column

Removing a column never breaks a formula: a removed cell is dropped from text-joining formulas (& chains and
CONCATENATE) together with its separator, every other reference is re-pointed to the column's new position.
"""
from __future__ import annotations

import math
import re
from copy import copy
from typing import Any, Iterable, Optional

from openpyxl.cell.cell import MergedCell
from openpyxl.worksheet.merge import MergedCellRange
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.worksheet.dimensions import DimensionHolder, ColumnDimension

INST_REMOVE = {"loopnumber", "loopno", "pidno", "pandidno", "signalto", "iopanel", "iotype", "racknode", "rack",
               "slot", "channelno", "terminalstripno", "terminalnocmn", "terminalnosignal", "terminalnozero"}
INST_REMOVE_PREFIX = ("ferruleatplc",)                      # FERRULE AT PLC (+) / (-)
EXTRA_REMOVE = {"plcto", "controldeskterminals", "signaltype"}
EXTRA_SHEETS = ("mcc_di", "mcc_do", "vfd")


def norm(v: Any) -> str:
    return re.sub(r"[^a-z0-9+\-]", "", str(v or "").lower())


def key(v: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower())


def natural(v: Any):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(v))]


# ── junction box order: category (AJB, then DJB, then the rest), project prefix, JB number ──────────────────
_CATEGORY_RANK = {"AJB": 0, "DJB": 1}                   # every other category follows, alphabetically; unparsed tags last
_CAT_TOKEN = re.compile(r"(?<![A-Za-z])([A-Za-z]*JB|SMB)(?![A-Za-z])")


def parse_jb_tag(tag: Any) -> dict:
    """
    Split a junction box tag into its category, project / unit prefix and number WITHOUT changing the displayed tag:
    'AJB-01', 'AJB 01', 'AJB01', '20-AJB-01', '200-DJB-101', 'JB-101-02' ->
    {category: 'AJB', prefix: '20', number: 1, parsed: True}. A tag with no category word, or none followed by a number,
    is not parsed (parsed False) and is sorted after the parsed ones - it is never given a guessed number.
    """
    text = "" if tag is None else re.sub(r"\s+", " ", str(tag)).strip()
    m = _CAT_TOKEN.search(text)
    if not m:
        return {"category": "", "prefix": text, "number": None, "parsed": False}
    num = re.match(r"[\s\-_./]*(\d+)", text[m.end():])
    return {"category": m.group(1).upper(), "prefix": text[:m.start()].strip(" -_./"),
            "number": int(num.group(1)) if num else None, "parsed": num is not None}


def jb_sort_key(tag: Any):
    """Key that orders junction boxes: all AJB, then all DJB, then any other category (by name), then unparsed tags; inside a
    category by prefix and ascending JB number (01 < 02 < 09 < 10 < 100); the full tag breaks ties."""
    p = parse_jb_tag(tag)
    rank = _CATEGORY_RANK.get(p["category"], 2) if p["parsed"] else 3
    return (rank, p["category"] if rank == 2 else "", natural(p["prefix"]) if p["parsed"] else [], p["number"] if p["parsed"] else 0,
            natural(tag))


def jb_unparsed(tags) -> list:
    """Tags whose category / number could not be read (they are sorted last and reported)."""
    return [t for t in tags if not parse_jb_tag(t)["parsed"]]


# ── IODB: tags per junction box (for the JB selection step) ──────────────────
def jb_groups(df, jb_column: str, tag_column: str) -> list[dict]:
    """Junction boxes (AJB first, then DJB, each in numeric order) with ALL their tags in IODB order - the same rows the schedule writes."""
    if jb_column not in df.columns or tag_column not in df.columns:
        raise ValueError(f"Columns '{jb_column}' / '{tag_column}' not found in the IODB.")
    jb = df[jb_column].astype(str).str.strip()
    ok = df[jb_column].notna() & (jb != "") & (jb != "-") & (jb.str.lower() != "nan")
    out: dict[str, list[str]] = {}
    for name, tag in zip(jb[ok], df.loc[ok, tag_column]):
        t = "" if tag is None or str(tag).strip().lower() in ("", "nan") else str(tag).strip()
        out.setdefault(name, []).append(t or "TBA")
    return [{"junction_box": k, "tag_count": len(v), "tags": v} for k, v in sorted(out.items(), key=lambda kv: jb_sort_key(kv[0]))]


# ── formulas ─────────────────────────────────────────────────────────────────
_REF = re.compile(r"(?<![A-Za-z0-9_!.$'])(\$?)([A-Z]{1,3})(\$?)(\d+)(?![A-Za-z0-9_(])")


def _split_top(s: str, sep: str) -> list[str]:
    parts, depth, q, cur = [], 0, False, []
    for ch in s:
        if ch == '"':
            q = not q
        elif not q and ch == "(":
            depth += 1
        elif not q and ch == ")":
            depth -= 1
        if ch == sep and not q and depth == 0:
            parts.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def _outside_quotes(s: str, fn) -> str:
    out = re.split(r'("(?:[^"]|"")*")', s)
    return "".join(p if p.startswith('"') else fn(p) for p in out)


def _refs(s: str) -> list[int]:
    cols: list[int] = []

    def grab(p: str) -> str:
        cols.extend(column_index_from_string(m.group(2)) for m in _REF.finditer(p))
        return p
    _outside_quotes(s, grab)
    return cols


def _drop_terms(terms: list[str], deleted: set[int]) -> list[str]:
    """Remove terms that reference deleted columns, each with the separator next to it (terms alternate value / sep)."""
    keep = [True] * len(terms)
    for i, t in enumerate(terms):
        if any(c in deleted for c in _refs(t)):
            keep[i] = False
            j = i - 1 if i > 0 else i + 1
            if 0 <= j < len(terms):
                keep[j] = False
    out = [t for t, k in zip(terms, keep) if k]
    return out or ['""']


def rewrite_formula(f: str, mapping: dict[int, int], deleted: set[int]) -> str:
    body = f[1:]
    m = re.fullmatch(r"\s*CONCATENATE\((.*)\)\s*", body, flags=re.I | re.S)
    if m and any(c in deleted for c in _refs(body)):
        body = "CONCATENATE(" + ",".join(_drop_terms(_split_top(m.group(1), ","), deleted)) + ")"
    elif "&" in body and any(c in deleted for c in _refs(body)):
        body = "&".join(_drop_terms(_split_top(body, "&"), deleted))

    def sub(p: str) -> str:
        def one(mm):
            c = column_index_from_string(mm.group(2))
            if c in deleted:
                return '""'
            nc = mapping.get(c, c)
            return f"{mm.group(1)}{get_column_letter(nc)}{mm.group(3)}{mm.group(4)}"
        return _REF.sub(one, p)
    return "=" + _outside_quotes(body, sub)


# ── column reorder / removal ─────────────────────────────────────────────────
def _col_dims(ws) -> dict[int, ColumnDimension]:
    dims: dict[int, ColumnDimension] = {}
    for _k, d in ws.column_dimensions.items():
        lo, hi = d.min or column_index_from_string(_k), d.max or column_index_from_string(_k)
        for c in range(lo, hi + 1):
            dims[c] = d
    return dims


def reorder_columns(ws, keep: list[int], hdr_row: int, last_col: int, keep_tail: bool = True) -> dict[int, int]:
    """Rebuild the sheet with columns `keep` (old indices, in their new order) as the table, everything else in
    1..last_col removed, helper columns after last_col appended unchanged in order. Rows above `hdr_row` (the title
    block) are re-laid proportionally to the new width. Returns old -> new column mapping (table + helpers)."""
    old_max = max(ws.max_column, last_col)
    new_last = len(keep)
    mapping = {c: i + 1 for i, c in enumerate(keep)}
    if keep_tail:
        for c in range(last_col + 1, old_max + 1):
            mapping[c] = new_last + (c - last_col)
    deleted = {c for c in range(1, old_max + 1) if c not in mapping}
    k = new_last / last_col

    merges = [(r.min_row, r.min_col, r.max_row, r.max_col) for r in ws.merged_cells.ranges]
    for r in list(ws.merged_cells.ranges):
        ws.merged_cells.remove(r)
    cells = dict(ws._cells)
    dims = _col_dims(ws)
    ws._cells = {}

    def put(r, nc, src):
        cell = ws.cell(row=r, column=nc)
        v = None if isinstance(src, MergedCell) else src.value
        if isinstance(v, str) and v.startswith("="):
            v = rewrite_formula(v, mapping, deleted)
        cell.value = v
        if src.has_style:
            cell._style = copy(src._style)
        if getattr(src, "hyperlink", None):
            cell.hyperlink = copy(src.hyperlink)

    # table + helper columns
    for (r, c), src in cells.items():
        if r >= hdr_row and c in mapping:
            put(r, mapping[c], src)
        elif r < hdr_row and c > last_col and c in mapping:
            put(r, mapping[c], src)
    # title block: proportional segments, order kept, no overlap
    title_merges = [m for m in merges if m[2] < hdr_row and m[1] <= last_col]
    in_merge = {(r, c) for (r1, c1, r2, c2) in title_merges for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)}
    segs = list(title_merges) + [(r, c, r, c) for (r, c), s in cells.items()
                                 if r < hdr_row and c <= last_col and (r, c) not in in_merge
                                 and not isinstance(s, MergedCell) and (s.value not in (None, "") or s.has_style)]
    placed: dict[tuple, tuple] = {}
    occupied: dict[int, list[tuple[int, int]]] = {}
    for (r1, c1, r2, c2) in sorted(segs, key=lambda s: (s[1], s[0])):
        n1 = 1 + math.floor((c1 - 1) * k)
        n2 = max(n1, math.ceil(c2 * k))
        for r in range(r1, r2 + 1):
            for (a, b) in occupied.get(r, []):
                if n1 <= b:
                    n1 = b + 1
        n2 = min(max(n2, n1), new_last)
        n1 = min(n1, new_last)
        for r in range(r1, r2 + 1):
            occupied.setdefault(r, []).append((n1, n2))
        placed[(r1, c1, r2, c2)] = (n1, n2)
        for r in range(r1, r2 + 1):
            for nc in range(n1, n2 + 1):
                frac = 0 if n2 == n1 else (nc - n1) / (n2 - n1)
                oc = c1 if nc == n1 else (c2 if nc == n2 else min(c2, c1 + max(1, round(frac * (c2 - c1)))))
                src = cells.get((r, oc))
                if src is not None and src.has_style:
                    ws.cell(row=r, column=nc)._style = copy(src._style)
        a = cells.get((r1, c1))
        if a is not None and not isinstance(a, MergedCell) and a.value is not None:
            v = a.value
            ws.cell(row=r1, column=n1).value = rewrite_formula(v, mapping, deleted) if isinstance(v, str) and v.startswith("=") else v
    # merges
    for (r1, c1, r2, c2) in merges:
        if (r1, c1, r2, c2) in placed:
            n1, n2 = placed[(r1, c1, r2, c2)]
        else:
            ks = sorted(mapping[c] for c in range(c1, c2 + 1) if c in mapping)
            if not ks or ks != list(range(ks[0], ks[-1] + 1)):
                continue
            n1, n2 = ks[0], ks[-1]
        if n2 > n1 or r2 > r1:
            try:
                ws.merge_cells(start_row=r1, start_column=n1, end_row=r2, end_column=n2)
            except Exception:
                pass
    # column widths
    holder = DimensionHolder(worksheet=ws, default_factory=ws._add_column)
    for c, nc in mapping.items():
        d = dims.get(c)
        if d is not None and (d.width or d.hidden):
            nd = ColumnDimension(ws, index=get_column_letter(nc), width=d.width, hidden=d.hidden)
            holder[get_column_letter(nc)] = nd
    ws.column_dimensions = holder
    # print area
    try:
        pa = ws.print_area
        if pa:
            pa = pa if isinstance(pa, str) else ",".join(pa)
            m = re.search(r"\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)", pa.split("!")[-1])
            if m:
                end = column_index_from_string(m.group(3))
                ends = [mapping[c] for c in range(1, min(end, last_col) + 1) if c in mapping]
                ws.print_area = f"{m.group(1)}{m.group(2)}:{get_column_letter(max(ends) if ends else new_last)}{m.group(4)}"
    except Exception:
        pass
    return mapping


def header_texts(ws, rows: Iterable[int], last_col: int) -> dict[int, str]:
    """Column -> header text (first non-empty of the header rows; merged headers give every spanned column the text)."""
    anchor = {}
    for mr in ws.merged_cells.ranges:
        for r in range(mr.min_row, mr.max_row + 1):
            for c in range(mr.min_col, mr.max_col + 1):
                anchor[(r, c)] = (mr.min_row, mr.min_col)
    out: dict[int, str] = {}
    for c in range(1, last_col + 1):
        for r in rows:
            ar, ac = anchor.get((r, c), (r, c))
            v = ws.cell(ar, ac).value
            if v not in (None, "") and str(v).strip():
                out.setdefault(c, str(v).strip())
    return out


def _merge_block(ws, r1: int, c1: int, r2: int, c2: int) -> None:
    """ws.merge_cells for a block known not to overlap any existing merge.

    openpyxl's merge_cells first scans every existing merge (MultiCellRange.__contains__), so N merges cost N^2:
    18,000 entry merges of a 1,000-tag schedule took minutes. The entry blocks are disjoint by construction (the data
    area's merges were removed by reorder_columns), so the scan is skipped; the merge and its borders are the same.
    """
    mcr = MergedCellRange(ws, f"{get_column_letter(c1)}{r1}:{get_column_letter(c2)}{r2}")
    ws.merged_cells.ranges.add(mcr)
    ws._clean_merge_range(mcr)


# ── Instrument Cable Schedule ────────────────────────────────────────────────
def instrument_layout(ws, hdr_row: int = 7, first_row: int = 9, rows_per_tag: int = 3,
                      block_jbs: Optional[list[str]] = None) -> dict:
    """`block_jbs`: junction box of every entry in output order (from the generator); TB numbering restarts per JB."""
    report: dict[str, Any] = {"removed": [], "tags": 0, "warnings": []}
    last_col = ws.max_column
    hdr = header_texts(ws, (hdr_row, hdr_row + 1), last_col)
    remarks = next((c for c, t in hdr.items() if key(t) == "remarks"), None)
    last_col = max(remarks or 0, max(hdr) if hdr else 1)
    ks = {c: key(t) for c, t in hdr.items()}
    ns = {c: norm(t) for c, t in hdr.items()}
    tag_col = next((c for c, t in ks.items() if t in ("tagnumber", "tagno")), None) or \
        next((c for c, t in ks.items() if "tag" in t and ("number" in t or t.endswith("no")) and "cable" not in t and "jb" not in t), 2)
    jb_col = next((c for c, t in ks.items() if t in ("jbtagno", "jbtagnumber", "junctionboxno", "junctionbox", "jbno")), None)
    tb_col = next((c for c, t in ks.items() if t.startswith("tbdetails") or t in ("tbno", "tb")), None)
    f_plus = next((c for c, t in ns.items() if "ferruleatinstrumentside" in t and "+" in t), None)
    f_minus = next((c for c, t in ns.items() if "ferruleatinstrumentside" in t and "-" in t and "+" not in t), None)
    remove = {c for c, t in ks.items() if (t in INST_REMOVE or t.startswith(INST_REMOVE_PREFIX)) and c != tag_col}
    if not tb_col:
        report["warnings"].append("The template has no 'TB DETAILS AT JB' column - TB numbers were not written.")

    # entries (block start rows) in order
    starts, r = [], first_row
    while r <= ws.max_row:
        v = ws.cell(r, tag_col).value
        if v is not None and str(v).strip():
            starts.append(r)
            r += rows_per_tag
        else:
            r += 1
    report["tags"] = len(starts)
    counters: dict[str, int] = {}
    if block_jbs is not None and len(block_jbs) != len(starts):
        report["warnings"].append("Entry count differs from the generator's - TB numbering uses the JB column of the sheet.")
        block_jbs = None
    for i_blk, s in enumerate(starts):
        jb = block_jbs[i_blk] if block_jbs is not None else (str(ws.cell(s, jb_col).value or "").strip() if jb_col else "")
        n = counters.get(jb, 0)
        counters[jb] = n + 1
        if tb_col:
            for i in range(rows_per_tag):
                cell = ws.cell(s + i, tb_col)
                cell.value = n * rows_per_tag + i + 1
                if i:
                    cell._style = copy(ws.cell(s, tb_col)._style)
        if f_plus and f_minus:
            minus = ws.cell(s, f_minus).value
            dst = ws.cell(s + 1, f_plus)
            dst.value = minus
            dst._style = copy(ws.cell(s, f_plus)._style)
            ws.cell(s, f_minus).value = None
    report["tb_numbers"] = {jb: n * rows_per_tag for jb, n in counters.items()}
    if f_plus and f_minus:
        top = hdr_row
        ws.cell(top, f_plus).value = "FERRULE AT INSTRUMENT SIDE\n(+) / (-)"
        remove.add(f_minus)
        report["ferrule"] = "combined"
    report["removed"] = [hdr[c] for c in sorted(remove)]
    keep = [c for c in range(1, last_col + 1) if c not in remove]
    mapping = reorder_columns(ws, keep, hdr_row, last_col)
    # one entry = one 3-row block: merge every column except TB and the instrument-side ferrule
    nb = {mapping[c] for c in (tb_col, f_plus) if c in mapping}
    # a MAIN cable is shared by every tag of its JB: its tag cell is not merged per entry, so the cable / gland / lug
    # readers keep seeing one physical cable (a merged cable-tag cell means "one cable per block" to them)
    nb |= {mapping[c] for c, t in ks.items() if "main" in t and "cable" in t and ("tag" in t or t.endswith("no")) and c in mapping}
    new_last = len(keep)
    for s in starts:
        for c in range(1, new_last + 1):
            if c in nb:
                continue
            below = [ws.cell(s + i, c).value for i in range(1, rows_per_tag)]
            if any(v not in (None, "") for v in below):
                continue
            _merge_block(ws, s, c, s + rows_per_tag - 1, c)
    report["columns"] = [header_texts(ws, (hdr_row, hdr_row + 1), new_last).get(c, "") for c in range(1, new_last + 1)]
    report["row_height"] = uniform_entry_heights(ws, starts, rows_per_tag, new_last)
    return report


# ── row heights ──────────────────────────────────────────────────────────────
ENTRY_ROW_MIN = 18.0          # points: one line of Arial 12 plus padding - every row of an entry is at least this
LINE_PT = 15.0                # points per wrapped line of Arial 12
CHARS_PER_WIDTH = 1 / 1.3     # Arial 12 characters per Excel column-width unit (width is in Calibri 11 characters)


def _text_len(ws, cell):
    """What the cell shows (text, for word wrapping); a CONCATENATE / & formula is estimated from the cells and
    literals it joins (an int length is returned for those)."""
    v = cell.value
    if v is None:
        return 0
    if not (isinstance(v, str) and v.startswith("=")):
        return str(v)
    if isinstance(v, str) and v.startswith("="):
        lits = sum(len(x) for x in re.findall(r'"([^"]*)"', v))
        refs = 0
        for col, row in re.findall(r"(?<![A-Z\"])\$?([A-Z]{1,3})\$?(\d+)", v.upper()):
            try:
                rv = ws[f"{col}{row}"].value
            except Exception:
                rv = None
            refs += len(str(rv)) if rv is not None and not (isinstance(rv, str) and rv.startswith("=")) else 4
        return lits + refs
    return len(str(v))


def _lines(text, width: Optional[float]) -> int:
    """Wrapped lines Excel needs: words wrapped at the column's character capacity (explicit line breaks kept)."""
    import textwrap
    cap = max(1, int((width or 8.43) * CHARS_PER_WIDTH))
    if not text:
        return 1
    if isinstance(text, int):
        return max(1, math.ceil(text / cap))
    return max(1, sum(max(1, len(textwrap.wrap(part, cap, break_long_words=True))) for part in str(text).split("\n")))


def uniform_entry_heights(ws, starts: list[int], rows_per_tag: int, ncols: int) -> dict:
    """
    One height for every row of an entry (main row + terminal continuation rows), the same for every entry:
    ENTRY_ROW_MIN, raised only when wrapped text needs more room - text merged over the entry is spread over its rows,
    per-row text (TB number, ferrule) must fit its own row. Header / title rows are not touched. -> summary for the report.
    """
    widths = {c: ws.column_dimensions[get_column_letter(c)].width for c in range(1, ncols + 1)}
    merged_top = {(m.min_row, m.min_col): m.max_row - m.min_row + 1 for m in ws.merged_cells.ranges if m.min_row in set(starts)}
    raised = 0
    for s in starts:
        need = ENTRY_ROW_MIN
        for c in range(1, ncols + 1):
            span = merged_top.get((s, c))
            if span:                                            # merged over the entry: its lines share the rows
                lines = _lines(_text_len(ws, ws.cell(s, c)), widths[c])
                need = max(need, (lines * LINE_PT + 4) / span)
            else:
                for i in range(rows_per_tag):
                    cell = ws.cell(s + i, c)
                    if not isinstance(cell, MergedCell) and cell.value is not None:
                        need = max(need, _lines(_text_len(ws, cell), widths[c]) * LINE_PT + 3)
        need = math.ceil(need * 4) / 4
        if need > ENTRY_ROW_MIN:
            raised += 1
        for i in range(rows_per_tag):
            ws.row_dimensions[s + i].height = need
    return {"entries": len(starts), "base_pt": ENTRY_ROW_MIN, "raised_for_wrapped_text": raised}


# ── MCC DI / MCC DO / VFD ────────────────────────────────────────────────────
def extra_layout(ws, hdr_row: int = 9) -> dict:
    last_guess = ws.max_column
    hdr = header_texts(ws, (hdr_row,), last_guess)
    remarks = next((c for c, t in sorted(hdr.items()) if key(t) == "remarks"), None)
    if remarks is None:
        return {"warnings": [f"{ws.title}: no Remarks column - layout unchanged."]}
    ks = {c: key(t) for c, t in hdr.items() if c <= remarks}
    remove = {c for c, t in ks.items() if t in EXTRA_REMOVE}
    lengths = [c for c, t in ks.items() if t.startswith("cablelength")]
    keep = [c for c in range(1, remarks) if c not in remove and c not in lengths]
    keep += lengths[:1] + [remarks]
    # helper cells after Remarks only hold the ferrule separators ('/', '−'): write them into the formulas as text,
    # then the helper columns go - Remarks is the last column and nothing is hidden
    for row in ws.iter_rows(min_row=hdr_row + 1, max_col=remarks):
        for cell in row:
            v = cell.value
            if isinstance(v, str) and v.startswith("="):
                def lit(m, r=cell.row):
                    c = column_index_from_string(m.group(2))
                    if c <= remarks:
                        return m.group(0)
                    t = ws.cell(int(m.group(4)), c).value
                    return '"' + str(t if t is not None else "").replace('"', '""') + '"'
                cell.value = "=" + _outside_quotes(v[1:], lambda p: _REF.sub(lit, p))
    mapping = reorder_columns(ws, keep, hdr_row, remarks, keep_tail=False)
    new = header_texts(ws, (hdr_row,), len(keep))
    return {"removed": [hdr[c] for c in sorted(remove)], "columns": [new.get(c, "") for c in range(1, len(keep) + 1)],
            "cable_length_col": mapping.get(lengths[0]) if lengths else None, "warnings": []}
