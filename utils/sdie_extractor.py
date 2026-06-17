"""
Smart Datasheet Intelligence Engine (SDIE) — Phase 1: OCR extraction.

Pipeline:
    file bytes (PDF/JPG/PNG/TIFF)
        -> extract_pages()     : render each page to a PIL Image
        -> ocr_page()           : pytesseract word-level OCR -> lines with confidence
        -> parse_specifications(): regex "label : value" extraction per line
        -> normalize_specifications(): fuzzy-match labels to canonical WABAG fields
"""
from __future__ import annotations

import io
import re
from typing import Any

import os
import shutil

from PIL import Image
import pytesseract
from pytesseract import Output

# Resolve tesseract binary: prefer explicit env var, then common Linux path (Docker/Render),
# then macOS Homebrew path, then whatever is on PATH.
def _find_tesseract() -> str | None:
    if env := os.environ.get("TESSERACT_CMD"):
        return env
    for candidate in (
        "/usr/bin/tesseract",           # apt (Debian/Ubuntu Docker image)
        "/usr/local/bin/tesseract",     # some Linux builds
        "/opt/homebrew/bin/tesseract",  # macOS Homebrew (Apple Silicon)
        "/usr/local/homebrew/bin/tesseract",
    ):
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("tesseract")

_tess = _find_tesseract()
if _tess:
    pytesseract.pytesseract.tesseract_cmd = _tess

import logging

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from .datasheet_generator import (
    normalize,
    fuzzy_match,
    _get_datasheet_ws,
    _is_explicit_placeholder,
    FUZZY_THRESHOLD,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Limits (keep memory/CPU bounded on Render's free tier — 512MB RAM, throttled CPU)
# ─────────────────────────────────────────────────────────────────────────────
MAX_PAGES = 5
PDF_DPI = 120

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

# ─────────────────────────────────────────────────────────────────────────────
# Canonical WABAG datasheet fields + synonym dictionary
# ─────────────────────────────────────────────────────────────────────────────
CANONICAL_FIELDS = [
    "INSTRUMENT TYPE",
    "MODEL NUMBER",
    "MEASURING RANGE",
    "ACCURACY",
    "OUTPUT SIGNAL",
    "SUPPLY VOLTAGE",
    "PROCESS TEMPERATURE",
    "PROCESS PRESSURE",
    "WETTED MATERIAL",
    "ENCLOSURE PROTECTION",
    "HAZARDOUS AREA CERTIFICATION",
    "COMMUNICATION PROTOCOL",
    "MOUNTING TYPE",
    "PROCESS CONNECTION",
]

SYNONYMS: dict[str, list[str]] = {
    "INSTRUMENT TYPE": ["instrument type", "type", "device type", "transmitter type"],
    "MODEL NUMBER": ["model number", "model no", "model", "part number", "part no", "type number"],
    "MEASURING RANGE": [
        "measuring range", "range", "measurement range", "operating range",
        "span", "calibration range",
    ],
    "ACCURACY": ["accuracy", "accuracy class", "precision", "measurement accuracy"],
    "OUTPUT SIGNAL": [
        "output signal", "output", "signal output", "electrical output",
        "output type",
    ],
    "SUPPLY VOLTAGE": [
        "supply voltage", "power supply", "power", "voltage supply",
        "operating voltage", "input voltage",
    ],
    "PROCESS TEMPERATURE": [
        "process temperature", "operating temperature", "temperature range",
        "ambient temperature", "temperature",
    ],
    "PROCESS PRESSURE": [
        "process pressure", "operating pressure", "pressure rating",
        "pressure range", "pressure",
    ],
    "WETTED MATERIAL": [
        "wetted material", "wetted parts", "material of construction",
        "wetted parts material", "body material",
    ],
    "ENCLOSURE PROTECTION": [
        "enclosure protection", "ingress protection", "protection class",
        "ip rating", "enclosure rating", "housing protection",
    ],
    "HAZARDOUS AREA CERTIFICATION": [
        "hazardous area certification", "hazardous area approval",
        "explosion protection", "ex certification", "area classification",
        "certification",
    ],
    "COMMUNICATION PROTOCOL": [
        "communication protocol", "communication", "protocol",
        "digital communication", "fieldbus",
    ],
    "MOUNTING TYPE": ["mounting type", "mounting", "mounting style", "installation type"],
    "PROCESS CONNECTION": [
        "process connection", "connection type", "process connection size",
        "fitting", "connection",
    ],
}

# Build a flat list of (synonym, canonical_field) for fuzzy matching.
_SYNONYM_CHOICES: list[str] = []
_SYNONYM_TO_CANONICAL: dict[str, str] = {}
for _canonical, _terms in SYNONYMS.items():
    for _term in [_canonical] + _terms:
        norm_term = normalize(_term)
        _SYNONYM_CHOICES.append(norm_term)
        _SYNONYM_TO_CANONICAL[norm_term] = _canonical

MATCH_THRESHOLD = 80


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — page extraction
# ─────────────────────────────────────────────────────────────────────────────
def extract_pages(file_bytes: bytes, filename: str) -> list[Image.Image]:
    """Render an uploaded PDF/image into a list of PIL Images (one per page)."""
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    if ext == ".pdf":
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(file_bytes, dpi=PDF_DPI, fmt="png")
        return pages[:MAX_PAGES]

    # Treat everything else as a single-page image (JPG/PNG/TIFF/BMP/...)
    img = Image.open(io.BytesIO(file_bytes))
    # TIFF files may contain multiple frames/pages
    pages: list[Image.Image] = []
    try:
        while True:
            pages.append(img.convert("RGB"))
            img.seek(img.tell() + 1)
    except EOFError:
        pass
    if not pages:
        pages = [img.convert("RGB")]
    return pages[:MAX_PAGES]


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — OCR a single page into lines with per-line confidence
# ─────────────────────────────────────────────────────────────────────────────
def ocr_page(image: Image.Image) -> list[dict[str, Any]]:
    """
    Run OCR on a page image and group words into lines.

    Returns a list of {"text": str, "confidence": float} — confidence is the
    average of the OCR word-level confidences (0-100) for that line.
    """
    if not _tess:
        raise RuntimeError(
            "Tesseract OCR binary not found. "
            "Install it with: apt-get install tesseract-ocr (Linux) or brew install tesseract (macOS)."
        )
    data = pytesseract.image_to_data(image, output_type=Output.DICT)

    lines: dict[tuple[int, int, int], dict[str, Any]] = {}
    n = len(data.get("text", []))
    for i in range(n):
        word = data["text"][i].strip()
        if not word:
            continue
        conf_raw = data["conf"][i]
        try:
            conf = float(conf_raw)
        except (TypeError, ValueError):
            conf = -1.0
        if conf < 0:
            continue

        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        entry = lines.setdefault(key, {"words": [], "confs": []})
        entry["words"].append(word)
        entry["confs"].append(conf)

    result = []
    for entry in lines.values():
        text = " ".join(entry["words"]).strip()
        if not text:
            continue
        avg_conf = sum(entry["confs"]) / len(entry["confs"])
        result.append({"text": text, "confidence": round(avg_conf, 1)})

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — parse "label : value" style specifications from OCR'd lines
# ─────────────────────────────────────────────────────────────────────────────
# Matches "Label : Value", "Label - Value", "Label = Value", or a label
# followed by 2+ spaces and a value (common in tabular vendor datasheets).
_SPEC_LINE_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9/().,\- ]{1,60}?)\s*(?:[:=]|-{1,2}|\s{2,})\s*(\S.*)$"
)


def parse_specifications(pages: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """
    Extract {raw_label, value, confidence, page} dicts from OCR'd page lines.

    `pages` is a list of per-page line lists, as returned by ocr_page().
    """
    specs: list[dict[str, Any]] = []
    for page_idx, lines in enumerate(pages, start=1):
        for line in lines:
            text = line["text"]
            m = _SPEC_LINE_RE.match(text)
            if not m:
                continue
            raw_label = m.group(1).strip(" :-=")
            value = m.group(2).strip()
            if not raw_label or not value:
                continue
            # Skip labels that are themselves just numbers/symbols (false positives)
            if not re.search(r"[A-Za-z]", raw_label):
                continue
            specs.append({
                "raw_label": raw_label,
                "value": value,
                "confidence": line["confidence"],
                "page": page_idx,
            })
    return specs


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — normalize extracted labels to canonical WABAG fields
# ─────────────────────────────────────────────────────────────────────────────
def normalize_specifications(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Attach `canonical_field` (or None) and `match_score` to each extracted spec
    by fuzzy-matching the raw label against the synonym dictionary.
    """
    normalized = []
    for spec in specs:
        norm_label = normalize(spec["raw_label"])
        canonical_field: str | None = None
        match_score = 0.0

        if norm_label in _SYNONYM_TO_CANONICAL:
            canonical_field = _SYNONYM_TO_CANONICAL[norm_label]
            match_score = 100.0
        else:
            best, score = fuzzy_match(norm_label, _SYNONYM_CHOICES, MATCH_THRESHOLD)
            if best is not None:
                canonical_field = _SYNONYM_TO_CANONICAL[best]
                match_score = float(score)

        normalized.append({
            **spec,
            "canonical_field": canonical_field,
            "match_score": round(match_score, 1),
        })
    return normalized


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — map normalized specs onto a WABAG template
# ─────────────────────────────────────────────────────────────────────────────
def _best_specs_by_canonical_field(specs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """For each canonical field, keep the spec with the highest OCR confidence."""
    best: dict[str, dict[str, Any]] = {}
    for spec in specs:
        field = spec.get("canonical_field")
        if not field:
            continue
        current = best.get(field)
        if current is None or spec["confidence"] > current["confidence"]:
            best[field] = spec
    return best


def map_specs_to_template(
    ws,
    specs: list[dict[str, Any]],
    threshold: int = FUZZY_THRESHOLD,
    log: list[dict] | None = None,
) -> None:
    """
    Populate a WABAG "Datasheet" worksheet in-place using extracted vendor specs.

    Mirrors the inverted-scan strategy of
    `datasheet_generator.map_data_to_template`: scans the sheet for explicit
    "Refer Annexure …" placeholder cells, walks leftward along the row to find
    the heading text, fuzzy-matches that heading against the SDIE synonym
    dictionary to resolve a canonical field, and fills the placeholder with the
    matching extracted spec's value (if any).
    """
    specs_by_field = _best_specs_by_canonical_field(specs)

    for row in ws.iter_rows():
        for cell in row:
            if not _is_explicit_placeholder(cell.value):
                continue
            if isinstance(cell.value, str) and cell.value.strip().startswith("="):
                continue
            if cell.__class__.__name__ == "MergedCell":
                continue

            # Collect non-empty, non-placeholder labels to the left (left-to-right order)
            left_labels: list[str] = []
            for check_col in range(cell.column - 1, 0, -1):
                check_cell = ws.cell(row=cell.row, column=check_col)
                if check_cell.__class__.__name__ == "MergedCell":
                    continue
                cv = check_cell.value
                if cv is None or not str(cv).strip():
                    continue
                cv_str = str(cv).strip()
                if cv_str.startswith("=") or _is_explicit_placeholder(cv_str):
                    continue
                left_labels.insert(0, cv_str)

            if not left_labels:
                logger.debug(
                    "map_specs_to_template: no heading found left of %s%d — skipping",
                    get_column_letter(cell.column), cell.row,
                )
                continue

            heading_candidates = [" ".join(left_labels[start:]) for start in range(len(left_labels))]
            heading_text = heading_candidates[0]

            # ── Resolve canonical field — try each heading candidate ───────────
            canonical_field: str | None = None
            match_score = 0.0
            for candidate in heading_candidates:
                nc = normalize(candidate)
                if nc in _SYNONYM_TO_CANONICAL:
                    canonical_field = _SYNONYM_TO_CANONICAL[nc]
                    match_score = 100.0
                    break
                best, score = fuzzy_match(nc, _SYNONYM_CHOICES, threshold)
                if best is not None and score > match_score:
                    canonical_field = _SYNONYM_TO_CANONICAL[best]
                    match_score = float(score)

            spec = specs_by_field.get(canonical_field) if canonical_field else None

            if spec is None:
                if log is not None:
                    log.append({
                        "heading": heading_text,
                        "canonical_field": canonical_field,
                        "score": match_score,
                        "value": "N/A",
                        "status": "UNMATCHED",
                    })
                continue

            cell.value = spec["value"]
            if log is not None:
                log.append({
                    "heading": heading_text,
                    "canonical_field": canonical_field,
                    "score": match_score,
                    "value": spec["value"],
                    "status": "MATCHED",
                })


def generate_populated_datasheet(
    template_bytes: bytes,
    specs: list[dict[str, Any]],
    threshold: int = FUZZY_THRESHOLD,
) -> tuple[bytes, list[dict], str | None]:
    """
    Populate a WABAG datasheet template with extracted vendor specs.

    Returns (excel_bytes, mapping_log, error). On error, excel_bytes is b"".
    """
    wb = load_workbook(io.BytesIO(template_bytes))

    ws, err = _get_datasheet_ws(wb)
    if err:
        return b"", [], err

    mapping_log: list[dict] = []
    map_specs_to_template(ws, specs, threshold, mapping_log)

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out.read(), mapping_log, None


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────
_GROQ_SYSTEM = """You are an Instrumentation Engineering Expert for EPC Water/Wastewater/Desalination projects (WABAG standard).

Extract ALL technical specifications from the text and return ONLY a JSON object.
Format: {"Field Name": {"value": "extracted value", "confidence": <0-100>}}
Confidence: 95-100 explicitly stated, 80-94 clearly implied, 60-79 inferred.

Extract EVERY field you find — including but not limited to:
Instrument Type, Tag Number, Service Description, Fluid/Medium, Line Size, Nominal Pipe Bore,
Measuring Range, Full Scale Range, Calibration Range, Turndown Ratio, Set Point,
Output Signal, Loop Power, Supply Voltage, Power Consumption,
Accuracy, Repeatability, Linearity, Hysteresis, Resolution, Response Time,
Process Temperature, Ambient Temperature, Process Pressure, Design Pressure, Design Temperature,
Enclosure Protection (IP Rating), Area Classification, Zone, Group, Ex Protection Standard,
Certificate Number, Approvals, SIL Rating,
Manufacturer, Make, Model Number, Series, Part Number,
Material of Construction, Body Material, Wetted Parts Material, Diaphragm Material,
Float Material, Electrode Material, Tube Material, Housing Material,
Process Connection, Connection Size, Flange Rating, Connection Standard (ASME/DIN/BS),
Cable Entry Size, Number of Cable Entries, Conduit Entry,
Communication Protocol, Digital Output, Fieldbus Type, HART Revision,
Mounting Type, Installation Type, Position, Orientation,
Sensor Type, Sensing Element, Detector Type, Probe Length, Insertion Depth,
Display Type, Local Indicator, LCD/LED, Scale Units,
Wiring Terminals, Terminal Block, Cable Gland,
Any other specification present in the document.

Return ONLY valid JSON. No explanation, no markdown, no prefix."""


def _run_ai_extraction(ocr_text: str) -> list[dict[str, Any]]:
    """Call Groq API — primary extraction pipeline."""
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        logger.warning("SDIE: GROQ_API_KEY not set — AI extraction skipped")
        return []

    import json as _json
    import requests as _requests

    try:
        resp = _requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": _GROQ_SYSTEM},
                    {"role": "user", "content": ocr_text[:8000]},
                ],
                "temperature": 0.1,
                "max_tokens": 2048,
            },
            timeout=45,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.error("SDIE: Groq API call failed: %s", exc)
        return []

    try:
        ai_result = _json.loads(raw)
    except _json.JSONDecodeError:
        import re as _re
        m = _re.search(r"\{.*\}", raw, _re.DOTALL)
        if not m:
            logger.error("SDIE: Could not parse JSON from Groq response")
            return []
        try:
            ai_result = _json.loads(m.group())
        except _json.JSONDecodeError as e:
            logger.error("SDIE: JSON decode failed: %s", e)
            return []

    specs = []
    for field, data in ai_result.items():
        val = data.get("value") if isinstance(data, dict) else data
        conf = data.get("confidence", 90) if isinstance(data, dict) else 90
        if not val or str(val).strip() in ("", "N/A", "n/a", "None", "null"):
            continue
        specs.append({
            "raw_label": field,
            "value": str(val).strip(),
            "confidence": int(conf),
            "page": 1,
            "canonical_field": field,
            "match_score": int(conf),
            "source": "ai",
        })
    logger.info("SDIE: AI extracted %d spec(s)", len(specs))
    return specs


def _merge_ocr_into_ai(ai_specs: list[dict[str, Any]], ocr_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add OCR specs that AI missed."""
    ai_fields = {(s.get("canonical_field") or "").lower() for s in ai_specs}
    for spec in ocr_specs:
        if (spec.get("canonical_field") or "").lower() not in ai_fields:
            spec["source"] = "ocr"
            ai_specs.append(spec)
    return ai_specs


def extract_specifications(file_bytes: bytes, filename: str) -> tuple[list[dict[str, Any]], int]:
    """
    Run the full extraction pipeline on an uploaded vendor datasheet.

    Renders pages → OCR text → Groq AI extraction.
    Returns (specs, page_count) where each spec is:
        {raw_label, value, confidence, page, canonical_field, match_score, source}
    """
    logger.info("SDIE: extracting from '%s' (%d bytes)", filename, len(file_bytes))
    pages = extract_pages(file_bytes, filename)
    logger.info("SDIE: rendered %d page(s)", len(pages))

    # Build plain text from all pages to feed the AI
    ocr_text_parts = []
    for idx, page in enumerate(pages, start=1):
        lines = ocr_page(page)
        logger.info("SDIE: OCR text page %d/%d -> %d line(s)", idx, len(pages), len(lines))
        for line in lines:
            ocr_text_parts.append(line.get("text", ""))

    ocr_text = "\n".join(line for line in ocr_text_parts if len(line.strip()) > 3)
    logger.info("SDIE: sending %d chars to Groq AI", len(ocr_text))

    specs = _run_ai_extraction(ocr_text)
    logger.info("SDIE: final %d specification(s)", len(specs))
    return specs, len(pages)


def specs_to_excel_bytes(specs: list[dict[str, Any]]) -> bytes:
    """Export extracted specifications to a single-sheet .xlsx workbook."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Extracted Specs"

    headers = ["Raw Label", "Value", "Mapped Field", "Match Score (%)", "OCR Confidence (%)", "Page"]
    ws.append(headers)
    for spec in specs:
        ws.append([
            spec.get("raw_label", ""),
            spec.get("value", ""),
            spec.get("canonical_field") or "Other technical specification",
            round(float(spec.get("match_score", 0)), 1),
            round(float(spec.get("confidence", 0)), 1),
            spec.get("page", ""),
        ])

    # Reasonable column widths
    widths = [32, 40, 30, 16, 18, 6]
    for col_idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out.read()
