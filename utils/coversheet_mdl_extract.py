"""
coversheet_mdl_extract.py - read a Master Document List (Excel or PDF) for the Coversheet Builder.

Used only by routers/coversheet_builder.py. The project MDL register (utils/mdl_parser.py,
services/mdl_service.py) is not touched.

    Excel (.xlsx / .xlsm / .xls)  header row found by NAME (synonyms + fuzzy matching), never by position
    PDF with a text layer         tables page by page; continued tables and repeated headers handled;
                                  falls back to text lines when no table header is found
    Scanned PDF                   OCR (tesseract) of the page images, then the text-line rules

Every record carries flags:
    error    the record cannot be used yet (document number or name missing)
    warning  check it (duplicate number, value read from text lines / OCR, joined multi-line text ...)
    info     a preferred value is missing (description)
Nothing is invented: a value that is not in the MDL stays empty and is flagged.
"""
from __future__ import annotations

import hashlib
import io
import re
from typing import Any, Optional

FIELDS = ("document_number", "document_name", "document_description", "revision", "document_type", "discipline")

SYNONYMS: dict[str, tuple[str, ...]] = {
    "document_number": ("doc no", "document no", "document number", "doc number", "drawing no", "drawing number", "dwg no",
                        "dwg number", "document ref", "doc ref", "document reference", "document code", "doc code no",
                        "document id", "doc id", "deliverable no", "deliverable number", "client doc no",
                        "client document no", "client document number", "contractor doc no", "vendor doc no",
                        "doc nos", "document nos"),
    "document_name": ("document name", "doc name", "document title", "doc title", "title", "drawing title",
                      "deliverable", "deliverable name", "deliverable title", "name of document", "title of document",
                      "drawing name", "document"),
    "document_description": ("description", "document description", "doc description", "brief description",
                             "details", "scope", "description of document"),
    "revision": ("rev", "revision", "rev no", "revision no", "revision number", "current rev", "current revision",
                 "latest rev", "latest revision", "rev status"),
    "document_type": ("doc type", "document type", "type", "category", "doc category", "document category",
                      "doc class", "document class", "class"),
    "discipline": ("discipline", "dept", "department"),
}
_PRIORITY = ("document_number", "document_name", "document_description", "revision", "document_type", "discipline")
_NUMBERISH = {"no", "number", "nos", "ref", "id", "code"}

DOC_NO_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z0-9]{2,}(?:[-/_.][A-Za-z0-9]{1,}){2,})(?![A-Za-z0-9])")
_REV_TOKEN = re.compile(r"^(?:r(?:ev)?\.?\s*)?([0-9]{1,2}|[a-z])$", re.I)
_ERRORS = {"#ref!", "#n/a", "#value!", "#name?", "#div/0!", "#null!", "#num!"}

MAX_PDF_PAGES = 80
MAX_OCR_PAGES = 15


class MdlExtractError(Exception):
    """User-facing problem with the MDL file (message shown as-is)."""


# ── text helpers ──────────────────────────────────────────────────────────────
def norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    t = re.sub(r"\s+", " ", str(value).replace(" ", " ")).strip()
    return "" if t.lower() in _ERRORS else t


def header_field(text: Any) -> tuple[Optional[str], int]:
    """(field, score) for a header cell. Exact synonym 100; all words of a multi-word synonym present 92; fuzzy >= 88."""
    n = norm(text)
    if not n or len(n) > 60:
        return None, 0
    toks = n.split()
    for f in _PRIORITY:
        if n in SYNONYMS[f]:
            return f, 100
    best: tuple[Optional[str], int] = (None, 0)
    for f in _PRIORITY:
        for s in SYNONYMS[f]:
            st = s.split()
            if len(st) >= 2 and all(t in toks for t in st) and len(toks) <= len(st) + 3:
                if f != "document_number" and _NUMBERISH & set(toks) and not (_NUMBERISH & set(st)):
                    continue
                if 92 > best[1]:
                    best = (f, 92)
            elif len(st) == 1 and st[0] in toks and len(toks) <= 3 and st[0] not in ("document", "type", "class"):
                if f != "document_number" and (_NUMBERISH | {"date"}) & set(toks):
                    continue
                if 90 > best[1]:
                    best = (f, 90)
    if best[0]:
        return best
    try:
        from rapidfuzz import fuzz
        for f in _PRIORITY:
            for s in SYNONYMS[f]:
                if len(s) >= 6:
                    sc = fuzz.token_sort_ratio(n, s)
                    if sc >= 88 and sc > best[1]:
                        best = (f, int(sc))
    except Exception:                                                   # pragma: no cover
        pass
    return best


def detect_header(row: list[Any]) -> Optional[dict[str, int]]:
    """{field: column index} when the row is a document-list header (needs a number column and a name/description)."""
    cand: list[tuple[int, str, int]] = []
    for i, cell in enumerate(row):
        f, sc = header_field(cell)
        if f:
            cand.append((sc, f, i))
    cols: dict[str, int] = {}
    used: set[int] = set()
    for sc, f, i in sorted(cand, key=lambda x: (-x[0], _PRIORITY.index(x[1]))):
        if f not in cols and i not in used:
            cols[f] = i
            used.add(i)
    if "document_number" in cols and ("document_name" in cols or "document_description" in cols):
        return cols
    return None


def looks_doc_no(text: str) -> bool:
    t = text.strip()
    return bool(t) and len(t) >= 3 and any(ch.isdigit() for ch in t) and len(t) <= 80


def rid_for(doc_no: str, name: str, n: int) -> str:
    h = hashlib.sha1(f"{doc_no.lower()}|{name.lower()}".encode()).hexdigest()[:14]
    return f"r{h}" if n == 1 else f"r{h}-{n}"


# ── record building ───────────────────────────────────────────────────────────
def _record(values: dict[str, str], source: str, method: str, extra_flags: list[dict] | None = None) -> dict:
    rec = {f: clean(values.get(f, "")) for f in FIELDS}
    rec.update(source=source, method=method, edited=False, flags=list(extra_flags or []))
    return rec


def finalize(records: list[dict], name_from_description: bool) -> list[dict]:
    """Ids, duplicate and completeness flags."""
    counts: dict[str, int] = {}
    for r in records:
        k = r["document_number"].strip().lower()
        if k:
            counts[k] = counts.get(k, 0) + 1
    seen: dict[str, int] = {}
    for r in records:
        reflag(r, counts, name_from_description)
        key = f"{r['document_number'].lower()}|{r['document_name'].lower()}"
        seen[key] = seen.get(key, 0) + 1
        r["id"] = rid_for(r["document_number"], r["document_name"], seen[key])
    return records


def reflag(r: dict, counts: Optional[dict[str, int]] = None, name_from_description: bool = False) -> dict:
    """Recompute completeness flags (keeps the extraction-method flags)."""
    keep = [f for f in r.get("flags", []) if f.get("kind") == "method"]
    flags = list(keep)
    if not r["document_number"].strip():
        flags.append({"level": "error", "field": "document_number", "message": "Document number missing"})
    elif not looks_doc_no(r["document_number"]):
        flags.append({"level": "warning", "field": "document_number", "message": "Unusual document number - check it"})
    if not r["document_name"].strip():
        flags.append({"level": "error", "field": "document_name", "message": "Document name missing"})
    if not r["document_description"].strip():
        flags.append({"level": "info", "field": "document_description",
                      "message": "No separate description in the MDL" if name_from_description else "Description missing"})
    n = (counts or {}).get(r["document_number"].strip().lower(), 0)
    if n > 1:
        flags.append({"level": "warning", "field": "document_number", "message": f"Document number appears {n} times in the MDL"})
    if r.get("edited"):
        flags.append({"level": "info", "field": "", "message": "Corrected by the user"})
    r["flags"] = flags
    r["status"] = "error" if any(f["level"] == "error" for f in flags) else (
        "warning" if any(f["level"] == "warning" for f in flags) else "ok")
    return r


def _from_rows(rows: list[list[Any]], cols: dict[str, int], source: str, method: str,
               method_flag: Optional[dict] = None) -> tuple[list[dict], int]:
    """Records from data rows under a header. Rows without a document number are headings / notes."""
    out, skipped = [], 0
    width = max(cols.values()) + 1
    for row in rows:
        row = list(row) + [None] * max(0, width - len(row))
        vals = {f: clean(row[i]) for f, i in cols.items()}
        if detect_header(row):
            continue                                            # a repeated header (continued table)
        dn = vals.get("document_number", "")
        if not dn:
            if any(clean(v) for v in row):
                skipped += 1
            continue
        if not looks_doc_no(dn) and not (vals.get("document_name") or vals.get("document_description")):
            skipped += 1
            continue
        out.append(_record(vals, source, method, [method_flag] if method_flag else None))
    return out, skipped


def _apply_name_rule(records: list[dict], cols: dict[str, int]) -> bool:
    """An MDL with only a DESCRIPTION column uses it for the document name (the title); description stays empty."""
    if "document_name" in cols or "document_description" not in cols:
        return False
    for r in records:
        r["document_name"], r["document_description"] = r["document_description"], ""
    return True


def _column_report(cols: dict[str, int], headers: list[Any], name_from_description: bool) -> list[dict]:
    rep = []
    for f in FIELDS:
        if f in cols:
            h = clean(headers[cols[f]]) if cols[f] < len(headers) else ""
            rep.append({"field": f, "header": h, "column": cols[f] + 1})
        else:
            rep.append({"field": f, "header": "", "column": None})
    if name_from_description:
        for r in rep:
            if r["field"] == "document_name":
                r["header"] = next((x["header"] for x in rep if x["field"] == "document_description"), "") + " (used as name)"
                r["column"] = cols["document_description"] + 1
            if r["field"] == "document_description":
                r["header"], r["column"] = "", None
    return rep


# ── Excel ─────────────────────────────────────────────────────────────────────
def _excel_sheets(data: bytes, ext: str) -> list[tuple[str, list[list[Any]]]]:
    if ext == "xls":
        try:
            import xlrd
            book = xlrd.open_workbook(file_contents=data)
        except Exception as exc:
            raise MdlExtractError(f"The .xls file could not be opened: {exc}")
        return [(sh.name, [sh.row_values(r) for r in range(min(sh.nrows, 20000))]) for sh in book.sheets()]
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise MdlExtractError(f"The Excel file could not be opened (it may be corrupted or password protected): {exc}")
    out = []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(max_row=20000, max_col=60, values_only=True)]
        out.append((ws.title, rows))
    wb.close()
    return out


def extract_excel(data: bytes, filename: str) -> dict:
    ext = filename.rsplit(".", 1)[-1].lower()
    sheets = _excel_sheets(data, ext)
    ordered = sorted(sheets, key=lambda s: (s[0].strip().lower() == "cover", "mdl" not in s[0].lower()))
    best = None
    for name, rows in ordered:
        if name.strip().lower() == "cover":
            continue
        for i, row in enumerate(rows[:40]):
            cols = detect_header(row)
            if cols:
                score = len(cols) + (5 if "mdl" in name.lower() else 0)
                if best is None or score > best[0]:
                    best = (score, name, i, cols, rows)
                break
    if best is None:
        raise MdlExtractError("No document list was found: no sheet has a header row with a document-number column and a "
                              "document name / title / description column. Check the file, or add the documents manually.")
    _, sheet, hi, cols, rows = best
    records, skipped = _from_rows(rows[hi + 1:], cols, f"{sheet}", "excel")
    if not records:
        raise MdlExtractError(f"Sheet '{sheet}' has the document-list columns but no rows with a document number.")
    nfd = _apply_name_rule(records, cols)
    finalize(records, nfd)
    return {"source_type": "excel", "file_name": filename, "sheet": sheet, "header_row": hi + 1, "pages": None,
            "method": "excel", "columns": _column_report(cols, rows[hi], nfd), "name_from_description": nfd,
            "records": records, "rows_ignored": skipped, "notes": []}


# ── PDF ───────────────────────────────────────────────────────────────────────
def _clean_table(tbl: list[list[Any]]) -> list[list[str]]:
    return [[clean(c) for c in row] for row in tbl if row and any(clean(c) for c in row)]


def _text_line_records(lines: list[tuple[int, str]], method: str, flag_msg: str) -> list[dict]:
    """Document records from free text lines: a document-number token, the rest of the line is the name."""
    out = []
    for page, line in lines:
        m = DOC_NO_RE.search(line)
        if not m or not any(ch.isdigit() for ch in m.group(1)):
            continue
        dn = m.group(1)
        if re.fullmatch(r"[0-9./\-]+", dn):                    # dates / plain numbers
            continue
        rest = (line[:m.start()] + " " + line[m.end():]).strip()
        rest = re.sub(r"^\d{1,4}[.)]?\s+", "", rest)            # leading serial number
        toks = rest.split()
        rev = ""
        if toks and _REV_TOKEN.match(toks[-1]) and len(toks) > 2:
            rev = toks.pop()
        name = " ".join(toks).strip(" -:|")
        if len(name) < 3:
            continue
        out.append(_record({"document_number": dn, "document_name": name, "revision": rev}, f"page {page}", method,
                           [{"level": "warning", "field": "", "message": flag_msg, "kind": "method"}]))
    return out


def _ocr_lines(data: bytes, npages: int) -> list[tuple[int, str]]:
    try:
        import pypdfium2 as pdfium
        import pytesseract
    except Exception as exc:
        raise MdlExtractError(f"This PDF has no text layer and OCR is not available on the server ({exc}). "
                              "Upload the MDL as Excel, or add the documents manually.")
    lines: list[tuple[int, str]] = []
    pdf = pdfium.PdfDocument(data)
    try:
        for i in range(min(len(pdf), MAX_OCR_PAGES)):
            img = pdf[i].render(scale=300 / 72).to_pil()
            try:
                d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            except Exception as exc:
                raise MdlExtractError(f"OCR failed on page {i + 1}: {exc}")
            groups: dict[tuple, list[tuple[int, int, str]]] = {}
            for k, word in enumerate(d["text"]):
                if word and word.strip():
                    key = (d["block_num"][k], d["par_num"][k], d["line_num"][k])
                    groups.setdefault(key, []).append((d["top"][k], d["left"][k], word.strip()))
            H = img.height
            for words in sorted(groups.values(), key=lambda ws: min(w[0] for w in ws)):
                top = min(w[0] for w in words)
                if 0.05 * H <= top <= 0.95 * H:                    # page header / footer bands are not records
                    lines.append((i + 1, " ".join(w[2] for w in sorted(words, key=lambda w: w[1]))))
    finally:
        pdf.close()
    return lines


def extract_pdf(data: bytes, filename: str) -> dict:
    try:
        import pdfplumber
    except Exception as exc:                                            # pragma: no cover
        raise MdlExtractError(f"PDF support is not installed on the server: {exc}")
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:
        raise MdlExtractError(f"The PDF could not be opened (it may be corrupted or encrypted): {exc}")
    notes: list[str] = []
    records: list[dict] = []
    skipped = 0
    header_cols: Optional[dict[str, int]] = None
    header_row: list[str] = []
    header_width = 0
    chars = 0
    text_lines: list[tuple[int, str]] = []
    with pdf:
        npages = len(pdf.pages)
        if npages > MAX_PDF_PAGES:
            notes.append(f"Only the first {MAX_PDF_PAGES} of {npages} pages were read.")
        for pno, page in enumerate(pdf.pages[:MAX_PDF_PAGES], start=1):
            chars += len(page.chars)
            h = float(page.height)
            try:
                words_lines = page.extract_text_lines()
            except Exception:
                words_lines = []
            for ln in words_lines:
                if 0.05 * h <= ln["top"] <= 0.95 * h:             # page header / footer bands are not records
                    text_lines.append((pno, ln["text"]))
            tables = []
            try:
                tables = page.extract_tables() or []
                if not tables:
                    tables = page.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text"}) or []
            except Exception:
                tables = []
            for tbl in tables:
                rows = _clean_table(tbl)
                if not rows:
                    continue
                start = 0
                for i, row in enumerate(rows[:8]):
                    cols = detect_header(row)
                    if cols:
                        header_cols, header_row, header_width, start = cols, row, len(row), i + 1
                        break
                else:
                    if header_cols is None or abs(len(rows[0]) - header_width) > 1:
                        continue                                    # a table that is not the document list
                prev = None
                for row in rows[start:]:
                    width = max(header_cols.values()) + 1
                    row = row + [""] * max(0, width - len(row))
                    vals = {f: row[i] for f, i in header_cols.items()}
                    if detect_header(row):
                        continue
                    if not vals.get("document_number"):
                        txt = [v for v in (vals.get("document_name"), vals.get("document_description")) if v]
                        other = [c for j, c in enumerate(row) if c and j not in header_cols.values()]
                        if prev is not None and txt and not other and prev["source"] == f"page {pno}":
                            for f in ("document_name", "document_description"):
                                if vals.get(f):
                                    prev[f] = (prev[f] + " " + vals[f]).strip()
                            if not any(x.get("message", "").startswith("Text continued") for x in prev["flags"]):
                                prev["flags"].append({"level": "warning", "field": "", "kind": "method",
                                                      "message": "Text continued on the next line was joined - check it"})
                        elif any(row):
                            skipped += 1
                        continue
                    if not looks_doc_no(vals["document_number"]):
                        skipped += 1
                        continue
                    prev = _record(vals, f"page {pno}", "pdf-table")
                    records.append(prev)
    method = "pdf-table"
    nfd = False
    columns = []
    if records:
        nfd = _apply_name_rule(records, header_cols)
        columns = _column_report(header_cols, header_row, nfd)
    elif chars >= 40:
        method = "pdf-text"
        records = _text_line_records(text_lines, method, "Read from text lines (no table header found) - check it")
        notes.append("No document table with recognisable headers was found; documents were read from text lines.")
    else:
        method = "ocr"
        records = _text_line_records(_ocr_lines(data, npages), method, "Read by OCR from a scanned page - check every value")
        notes.append("The PDF has no text layer (scanned); documents were read by OCR.")
    if not records:
        raise MdlExtractError("No document records could be read from this PDF. "
                              + ("It looks scanned and OCR found no document numbers. " if method == "ocr" else "")
                              + "Upload the MDL as Excel, or add the documents manually in the review table.")
    finalize(records, nfd)
    return {"source_type": "pdf", "file_name": filename, "sheet": None, "header_row": None, "pages": npages,
            "method": method, "columns": columns, "name_from_description": nfd, "records": records,
            "rows_ignored": skipped, "notes": notes}


# ── entry point ───────────────────────────────────────────────────────────────
def extract(data: bytes, filename: str) -> dict:
    if not data:
        raise MdlExtractError("The uploaded MDL file is empty.")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("xlsx", "xlsm", "xls"):
        res = extract_excel(data, filename)
    elif ext == "pdf" or data[:4] == b"%PDF":
        if data[:4] != b"%PDF":
            raise MdlExtractError("The file has a .pdf name but is not a PDF.")
        res = extract_pdf(data, filename)
    else:
        raise MdlExtractError("Unsupported MDL file type. Upload an Excel (.xlsx, .xlsm, .xls) or PDF file.")
    recs = res["records"]
    res["summary"] = {
        "records": len(recs),
        "errors": sum(1 for r in recs if r["status"] == "error"),
        "warnings": sum(1 for r in recs if r["status"] == "warning"),
        "duplicates": len({r["document_number"].lower() for r in recs
                           if any("appears" in f["message"] for f in r["flags"])}),
        "missing_description": sum(1 for r in recs if not r["document_description"]),
    }
    return res
