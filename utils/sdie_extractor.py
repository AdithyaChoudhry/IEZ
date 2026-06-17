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
# Few-shot examples (one per common WABAG instrument type)
# These teach Groq the exact output format and field vocabulary without training.
# ─────────────────────────────────────────────────────────────────────────────
_FEW_SHOT_EXAMPLES = """\
=== EXAMPLE 1: Pressure Transmitter ===
Input: "PT-201 | Pressure Transmitter | Raw Water | Range: 0-10 bar | Output: 4-20mA HART | 24 VDC | Accuracy: ±0.075% | IP67 | Safe Area | SS316 | Yokogawa EJA110E"
Output:
{"_instrument_type":"Pressure Transmitter","Tag Number":{"values":["PT-201"],"confidence":100},"Instrument Type":{"values":["Pressure Transmitter"],"confidence":99},"Fluid":{"values":["Raw Water"],"confidence":98},"Measuring Range":{"values":["0-10 bar"],"confidence":98},"Output Signal":{"values":["4-20mA HART"],"confidence":99},"Supply Voltage":{"values":["24 VDC"],"confidence":99},"Accuracy":{"values":["±0.075%"],"confidence":99},"Enclosure Protection":{"values":["IP67"],"confidence":99},"Area Classification":{"values":["Safe Area"],"confidence":97},"Wetted Material":{"values":["SS316"],"confidence":98},"Make":{"values":["Yokogawa"],"confidence":92},"Model Number":{"values":["EJA110E"],"confidence":90}}

=== EXAMPLE 2: Non-Contact Radar Level Transmitter ===
Input: "LT-101 | Non Contact Radar | Raw Water Tank | FMCW | 80 GHz | Beam 3° | Tank Ht: 6000mm | Max Level: 5500mm | SG: 1.0 | 24 VDC | 4-20mA+HART | ±3mm | IP67 | ATEX | Endress+Hauser FMR60B"
Output:
{"_instrument_type":"Non Contact Radar Level Transmitter","Tag Number":{"values":["LT-101"],"confidence":100},"Instrument Type":{"values":["Non Contact Radar Level Transmitter"],"confidence":99},"Location":{"values":["Raw Water Tank"],"confidence":98},"Fluid":{"values":["Raw Water"],"confidence":98},"Sensor Type":{"values":["FMCW Radar"],"confidence":98},"Frequency":{"values":["80 GHz"],"confidence":99},"Beam Angle":{"values":["3°"],"confidence":96},"Tank Height":{"values":["6000 mm"],"confidence":96},"Maximum Fluid Level":{"values":["5500 mm"],"confidence":95},"Specific Gravity":{"values":["1.0"],"confidence":95},"Supply Voltage":{"values":["24 VDC"],"confidence":99},"Output Signal":{"values":["4-20mA + HART"],"confidence":99},"Accuracy":{"values":["±3 mm"],"confidence":98},"Enclosure Protection":{"values":["IP67"],"confidence":99},"Area Certification":{"values":["ATEX"],"confidence":97},"Make":{"values":["Endress+Hauser"],"confidence":92},"Model Number":{"values":["FMR60B"],"confidence":90}}

=== EXAMPLE 3: Magnetic Flow Meter ===
Input: "FIT-101 | Magnetic Flow Meter | Treated Water | 250 m³/hr | DN300 | Conductivity >20µS/cm | Lining PTFE | Electrodes SS316L | Accuracy ±0.5% | 4-20mA HART | ABB ProcessMaster FEP300"
Output:
{"_instrument_type":"Magnetic Flow Meter","Tag Number":{"values":["FIT-101"],"confidence":100},"Instrument Type":{"values":["Magnetic Flow Meter"],"confidence":99},"Fluid":{"values":["Treated Water"],"confidence":98},"Flow Rate":{"values":["250 m³/hr"],"confidence":97},"Pipe Size":{"values":["DN300"],"confidence":98},"Conductivity":{"values":[">20 µS/cm"],"confidence":95},"Lining Material":{"values":["PTFE"],"confidence":98},"Electrode Material":{"values":["SS316L"],"confidence":98},"Accuracy":{"values":["±0.5%"],"confidence":99},"Output Signal":{"values":["4-20mA HART"],"confidence":99},"Make":{"values":["ABB"],"confidence":92},"Model Number":{"values":["ProcessMaster FEP300"],"confidence":90}}

=== EXAMPLE 4: Differential Pressure Transmitter ===
Input: "PDT-101 | DP Transmitter | Range 0-250 mbar | Accuracy ±0.05% | Rangeability 150:1 | 4-20mA+HART | 24VDC | Process Connection 1/2 NPT(F) | Wetted SS316 | Emerson Rosemount 3051CD"
Output:
{"_instrument_type":"Differential Pressure Transmitter","Tag Number":{"values":["PDT-101"],"confidence":100},"Instrument Type":{"values":["Differential Pressure Transmitter"],"confidence":99},"Pressure Range":{"values":["0-250 mbar"],"confidence":98},"Accuracy":{"values":["±0.05%"],"confidence":99},"Rangeability":{"values":["150:1"],"confidence":97},"Output Signal":{"values":["4-20mA + HART"],"confidence":99},"Supply Voltage":{"values":["24 VDC"],"confidence":99},"Process Connection":{"values":["1/2\" NPT(F)"],"confidence":97},"Wetted Material":{"values":["SS316"],"confidence":98},"Make":{"values":["Emerson"],"confidence":92},"Model Number":{"values":["Rosemount 3051CD"],"confidence":91}}

=== EXAMPLE 5: Ultrasonic Flow Meter ===
Input: "FIT-102 | Ultrasonic | Raw Water | DN500 | Clamp On | Carbon Steel pipe | Accuracy ±1% | Modbus RTU | 24VDC | FLEXIM FLUXUS F721"
Output:
{"_instrument_type":"Ultrasonic Flow Meter","Tag Number":{"values":["FIT-102"],"confidence":100},"Instrument Type":{"values":["Ultrasonic Flow Meter"],"confidence":99},"Fluid":{"values":["Raw Water"],"confidence":98},"Pipe Size":{"values":["DN500"],"confidence":97},"Sensor Type":{"values":["Clamp On"],"confidence":98},"Pipe Material":{"values":["Carbon Steel"],"confidence":96},"Accuracy":{"values":["±1%"],"confidence":97},"Output Signal":{"values":["Modbus RTU"],"confidence":96},"Supply Voltage":{"values":["24 VDC"],"confidence":99},"Make":{"values":["FLEXIM"],"confidence":91},"Model Number":{"values":["FLUXUS F721"],"confidence":89}}
"""

_GROQ_SYSTEM = f"""You are an Instrumentation Engineering Expert for EPC Water/Wastewater/Desalination projects (WABAG standard).

TASK:
1. Identify the instrument type from the document.
2. Extract ALL technical specifications found anywhere in the text.

Return ONLY valid JSON — no explanation, no markdown, no prefix text:
{{
  "_instrument_type": "detected instrument type name",
  "Field Name": {{"values": ["primary value", "alternate value if found elsewhere"], "confidence": 95}},
  ...
}}

RULES:
- "_instrument_type" is always the first key.
- If the same field appears multiple times in the document with DIFFERENT values, list ALL values in the array.
- If only one value found, the array has one element.
- Confidence: 95-100 = explicitly stated, 80-94 = clearly implied, 60-79 = inferred.
- Extract EVERY field present: tag number, service description, fluid, measuring range, set point,
  output signal, supply voltage, accuracy, repeatability, response time, IP rating, area classification,
  certifications, make, model, materials (body/wetted/diaphragm/electrode/lining/probe), process connection,
  pipe size, flow rate, frequency, beam angle, sensor type, communication protocol, cable entry,
  mounting type, rangeability, turndown ratio, tank height, specific gravity — and everything else found.
- Omit fields where value is N/A, empty, unknown, or not mentioned.

FEW-SHOT EXAMPLES (follow this exact format):
{_FEW_SHOT_EXAMPLES}"""


def extract_template_fields(template_bytes: bytes) -> list[str]:
    """
    Read the target field names from a WABAG datasheet template (sheet 2 or 3).
    Scans for 'Refer Annexure' placeholder cells and collects the heading text
    to their left — these are the fields the template expects to be filled.
    Returns an empty list if template cannot be parsed.
    """
    try:
        wb = load_workbook(io.BytesIO(template_bytes), data_only=True)
        # Try the standard datasheet worksheet first, then fall back to sheets 2/3
        ws, err = _get_datasheet_ws(wb)
        if err:
            sheets = wb.sheetnames
            candidates = [wb[s] for s in sheets[1:3]]  # sheets 2 and 3
            ws = candidates[0] if candidates else None
        if ws is None:
            return []

        fields: list[str] = []
        seen: set[str] = set()
        for row in ws.iter_rows():
            for cell in row:
                if not _is_explicit_placeholder(cell.value):
                    continue
                # Walk left to find the heading
                for col in range(cell.column - 1, 0, -1):
                    c = ws.cell(row=cell.row, column=col)
                    cv = c.value
                    if cv and str(cv).strip() and not _is_explicit_placeholder(str(cv)):
                        label = str(cv).strip()
                        if label not in seen:
                            fields.append(label)
                            seen.add(label)
                        break
        logger.info("SDIE: extracted %d template fields", len(fields))
        return fields
    except Exception as exc:
        logger.warning("SDIE: template field extraction failed: %s", exc)
        return []


def _run_ai_extraction(
    ocr_text: str,
    template_fields: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Call Groq API — primary extraction pipeline.
    Returns (specs, instrument_type).
    """
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        logger.warning("SDIE: GROQ_API_KEY not set — AI extraction skipped")
        return [], ""

    import json as _json
    import requests as _requests

    # Build user message: OCR text + template field hints if available
    user_content = ocr_text[:8000]
    if template_fields:
        field_list = ", ".join(template_fields[:40])  # cap at 40 fields to avoid token overflow
        user_content = (
            f"TARGET FIELDS TO EXTRACT (from the datasheet template):\n{field_list}\n\n"
            f"DOCUMENT TEXT:\n{ocr_text[:7500]}"
        )

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
                    {"role": "user", "content": user_content},
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
        return [], ""

    try:
        ai_result = _json.loads(raw)
    except _json.JSONDecodeError:
        import re as _re
        m = _re.search(r"\{.*\}", raw, _re.DOTALL)
        if not m:
            logger.error("SDIE: Could not parse JSON from Groq response")
            return [], ""
        try:
            ai_result = _json.loads(m.group())
        except _json.JSONDecodeError as e:
            logger.error("SDIE: JSON decode failed: %s", e)
            return [], ""

    _SKIP_VALUES = {"", "n/a", "na", "none", "null", "not specified", "unknown", "-", "—"}
    instrument_type = str(ai_result.pop("_instrument_type", "")).strip()

    specs = []
    for field, data in ai_result.items():
        if isinstance(data, dict):
            raw_vals = data.get("values") or [data.get("value", "")]
            conf = int(data.get("confidence", 90))
        elif isinstance(data, list):
            raw_vals = data
            conf = 85
        else:
            raw_vals = [str(data)]
            conf = 85

        # Clean and deduplicate values
        values = []
        seen_vals: set[str] = set()
        for v in raw_vals:
            s = str(v).strip()
            if s.lower() not in _SKIP_VALUES and s not in seen_vals:
                values.append(s)
                seen_vals.add(s)

        if not values:
            continue

        specs.append({
            "raw_label": field,
            "values": values,
            "value": values[0],
            "confidence": min(100, max(0, conf)),
            "page": 1,
            "canonical_field": field,
            "match_score": conf,
            "source": "ai",
        })

    logger.info("SDIE: AI extracted %d spec(s), instrument_type=%r", len(specs), instrument_type)
    return specs, instrument_type


def extract_specifications(
    file_bytes: bytes,
    filename: str,
    template_bytes: bytes | None = None,
) -> tuple[list[dict[str, Any]], int, str]:
    """
    Run the full extraction pipeline on an uploaded vendor datasheet.

    Renders pages → OCR text → (optional template field targeting) → Groq AI.
    Returns (specs, page_count, instrument_type).
    Each spec: {raw_label, values[], value, confidence, page, canonical_field, match_score, source}
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

    # Read template target fields if a template was supplied
    template_fields: list[str] = []
    if template_bytes:
        template_fields = extract_template_fields(template_bytes)

    specs, instrument_type = _run_ai_extraction(ocr_text, template_fields or None)
    logger.info("SDIE: final %d specification(s), type=%r", len(specs), instrument_type)
    return specs, len(pages), instrument_type


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
