"""
Dataset preparation for iEZ SDIE fine-tuning.

Reads all WABAG datasheet .xls files, extracts field-value pairs from
Example sheets and ANNEXURE-I sheets, then generates Alpaca-format
instruction-tuning JSONL for Llama 3.1 8B LoRA training.

Run:
    python ai_training/prepare_dataset.py
Output:
    ai_training/dataset.jsonl   (~train)
    ai_training/dataset_val.jsonl (~val, 10%)
"""

from __future__ import annotations
import json
import random
import re
import os
from pathlib import Path
from typing import Any

import xlrd

DATASHEET_ROOT = Path("/Users/adithyachoudhrym/Downloads/DataSheets")
OUT_DIR = Path(__file__).parent
random.seed(42)

SYSTEM_PROMPT = """You are an Instrumentation Engineering Expert and Datasheet Preparation Assistant for EPC Water, Wastewater, Desalination, ETP, STP, RO and ZLD Projects.

Your task: Given a Tender Specification or instrument description text, extract all technical specifications and return them as a JSON object.

Each field must have:
- "value": the extracted specification value
- "confidence": a percentage (0-100) indicating how certain you are

If a value is not found, set value to null and confidence to 0.
Return ONLY valid JSON. No explanation, no extra text."""

SKIP_FIELDS = {
    "client", "consultant", "project", "plant", "issued for",
    "sheet", "rev", "prepared by", "date", "va tech doc", "client doc",
    "notes", "qty", "spare qty", "stamping", "remarks", "sl.no",
    "xxxxx", "refer annexure", "x"
}

INSTRUMENT_TYPE_MAP = {
    "PT": "Pressure Transmitter",
    "DPT": "Differential Pressure Transmitter",
    "FT-MAGNETIC FULL BORE": "Magnetic Flow Meter - Full Bore",
    "FT-MAGNETIC INSERTION": "Magnetic Flow Meter - Insertion Type",
    "FT-THERMAL MASS": "Thermal Mass Flow Meter",
    "FT-ULT CLAMP ON": "Ultrasonic Flow Meter - Clamp On",
    "FT-DP": "DP Flow Transmitter",
    "FE-ANNUBAR": "Annubar Flow Element",
    "FE-ORIFICE PLATE": "Orifice Plate Flow Element",
    "FLOW SWITCH": "Flow Switch",
    "DIFF.PRESSURE SWITCH": "Differential Pressure Switch",
    "PRESSURE GAUGE-BOURDON TYPE": "Pressure Gauge - Bourdon Type",
    "PRESSURE GAUGE-CAPSULE TYPE": "Pressure Gauge - Capsule Type",
    "PRESSURE GAUGE-DIAPHRAGM SEAL TYPE": "Pressure Gauge - Diaphragm Seal Type",
    "PRESSURE GAUGE-SCHAFFER DIAPHRAGM TYPE": "Pressure Gauge - Schaffer Diaphragm Type",
    "PRESSURE SWITCH": "Pressure Switch",
    "TE-RTD": "Temperature Element - RTD",
    "TE-THERMOCOUPLE": "Temperature Element - Thermocouple",
    "TG": "Temperature Gauge",
    "TT": "Temperature Transmitter",
    "pH ANALYSER": "pH Analyser",
    "CONDUCTIVITY ANALYSER": "Conductivity Analyser",
    "DO ANALYSER": "Dissolved Oxygen Analyser",
    "TURBIDITY ANALYSER": "Turbidity Analyser",
    "TSS ANALYSER": "Total Suspended Solids Analyser",
    "RESIDUAL CHLORINE ANALYSER": "Residual Chlorine Analyser",
    "TOC ANALYSER": "TOC Analyser",
    "ORP ANALYSER": "ORP Analyser",
    "NH3 ANALYSER": "Ammonia Analyser",
    "OIL ANALYSER": "Oil-in-Water Analyser",
    "PHENOL ANALYSER": "Phenol Analyser",
    "FT-ULTRASONIC PARSHALL FLUME": "Ultrasonic Parshall Flume Flow Transmitter",
    "PARSHALL FLUME": "Ultrasonic Parshall Flume Flow Transmitter",
    "pH": "pH Analyser",
    "ROTAMETER": "Rotameter Flow Indicator",
    "BYPASS GLASS": "Rotameter - Bypass Glass Tube",
    "BYPASS METAL": "Rotameter - Bypass Metal Tube",
    "ONLINE GLASS": "Rotameter - Online Glass Tube",
    "ONLINE METAL": "Rotameter - Online Metal Tube",
}


def _should_skip(text: str) -> bool:
    t = text.lower().strip()
    if not t or len(t) < 2:
        return True
    return any(s in t for s in SKIP_FIELDS)


def _clean_val(v: str) -> str:
    v = v.strip()
    v = re.sub(r'\s+', ' ', v)
    if v.upper() in ("XXXXXX", "XXX", "XX", "X", "XXXX", "NA", "N/A", ""):
        return ""
    return v


def extract_example_sheet(sheet: xlrd.sheet.Sheet) -> dict[str, str]:
    """Extract field→value from an *-Example or similar sheet."""
    specs: dict[str, str] = {}
    current_section = ""
    for r in range(sheet.nrows):
        row_vals = [str(sheet.cell_value(r, c)).strip() for c in range(sheet.ncols)]
        row_vals = [v for v in row_vals if v]

        if not row_vals:
            continue

        # Section header (single cell, all caps, no colon)
        if len(row_vals) == 1 and row_vals[0].isupper():
            current_section = row_vals[0]
            continue

        # Field : Value pattern — first non-skippable cell is field, second is value
        field = row_vals[0]
        if _should_skip(field):
            continue

        # Try to get the value — skip metadata cols like "SOURCE"
        value = ""
        for v in row_vals[1:]:
            cv = _clean_val(v)
            if cv and not _should_skip(cv) and "REFER ANNEXURE" not in cv.upper() and "FETCH FROM" not in cv.upper():
                value = cv
                break

        if value:
            key = field.strip().replace("\n", " ")
            specs[key] = value

    return specs


def extract_annexure_rows(sheet: xlrd.sheet.Sheet) -> list[dict[str, str]]:
    """Extract individual instrument rows from ANNEXURE-I sheets."""
    records = []
    headers: list[str] = []
    header_row = -1

    for r in range(sheet.nrows):
        row_vals = [str(sheet.cell_value(r, c)).strip() for c in range(sheet.ncols)]
        # Detect header row: contains TAG NO.
        if any("TAG NO" in v.upper() for v in row_vals):
            headers = [v.replace("\n", " ").strip() for v in row_vals]
            header_row = r
            continue

        if header_row == -1:
            continue

        # Skip sub-header rows (MIN/NOR/MAX row)
        if all(v in ("MIN", "NOR", "MAX", "") for v in row_vals if v):
            continue

        # Data rows start with a number
        if not row_vals[0] or not re.match(r'^\d+\.?\d*$', row_vals[0]):
            continue

        record: dict[str, str] = {}
        for i, h in enumerate(headers):
            if i < len(row_vals) and h and not _should_skip(h):
                cv = _clean_val(row_vals[i])
                if cv:
                    record[h] = cv
        if record:
            records.append(record)

    return records


def infer_instrument_type(file_path: Path) -> str:
    """Infer instrument type from file path."""
    parts = file_path.parts
    for part in reversed(parts):
        upper = part.upper()
        for key, val in INSTRUMENT_TYPE_MAP.items():
            if key in upper:
                return val
    return "Instrument"


def specs_to_tender_text(instrument_type: str, specs: dict[str, str]) -> str:
    """Convert extracted specs dict into a synthetic tender specification paragraph."""
    lines = [f"Instrument Type: {instrument_type}"]
    for field, value in specs.items():
        if not _should_skip(field) and value:
            lines.append(f"{field}: {value}")
    return "\n".join(lines)


def specs_to_output_json(instrument_type: str, specs: dict[str, str]) -> dict:
    """Convert specs dict to the expected JSON output format with confidence scores."""
    result = {"Instrument Type": {"value": instrument_type, "confidence": 99}}
    confidence_map = {
        "tag no": 100, "p&id": 98, "fluid": 97, "output": 99,
        "power supply": 99, "accuracy": 98, "make": 92, "model": 90,
        "enclosure": 99, "area classification": 97, "certification": 96,
    }
    for field, value in specs.items():
        conf = 95
        for kw, c in confidence_map.items():
            if kw in field.lower():
                conf = c
                break
        result[field] = {"value": value, "confidence": conf}
    return result


def build_training_example(instrument_type: str, specs: dict[str, str]) -> dict | None:
    if len(specs) < 4:
        return None
    tender_text = specs_to_tender_text(instrument_type, specs)
    output = specs_to_output_json(instrument_type, specs)
    return {
        "instruction": SYSTEM_PROMPT,
        "input": tender_text,
        "output": json.dumps(output, indent=2),
    }


def augment_tender_text(tender_text: str) -> list[str]:
    """Generate text variations to increase training diversity."""
    variants = [tender_text]

    # Variant 1: shuffle order slightly
    lines = tender_text.split("\n")
    if len(lines) > 4:
        header = lines[:1]
        body = lines[1:]
        random.shuffle(body)
        variants.append("\n".join(header + body))

    # Variant 2: add noise/context sentences
    contexts = [
        "As per client specification and project requirements:",
        "The following instrument is required for the plant:",
        "Tender technical requirement for instrumentation:",
        "Vendor to supply instrument with below specifications:",
    ]
    variants.append(random.choice(contexts) + "\n" + tender_text)

    return variants


def process_all_datasheets() -> list[dict]:
    examples = []

    xls_files = list(DATASHEET_ROOT.rglob("*.xls")) + list(DATASHEET_ROOT.rglob("*.xlsx"))
    print(f"Found {len(xls_files)} datasheet files")

    for xls_path in xls_files:
        try:
            wb = xlrd.open_workbook(str(xls_path), formatting_info=False)
        except Exception as e:
            print(f"  SKIP {xls_path.name}: {e}")
            continue

        instrument_type = infer_instrument_type(xls_path)
        print(f"  Processing: {xls_path.name} → {instrument_type}")

        for sheet in wb.sheets():
            sname = sheet.name.lower()

            # Example sheets
            if "example" in sname:
                specs = extract_example_sheet(sheet)
                if specs:
                    for variant in augment_tender_text(specs_to_tender_text(instrument_type, specs)):
                        ex = build_training_example(instrument_type, specs)
                        if ex:
                            ex_copy = ex.copy()
                            ex_copy["input"] = variant
                            examples.append(ex_copy)

            # ANNEXURE-I: real project instrument rows
            elif "annexure" in sname:
                rows = extract_annexure_rows(sheet)
                for row in rows:
                    # Map ANNEXURE columns to human-readable fields
                    specs = {}
                    col_map = {
                        "TAG NO.": "Tag Number",
                        "P & ID NO.": "P&ID Number",
                        "FLUID/SERVICE": "Fluid / Service",
                        "SERVICE": "Service Description",
                        "LOCATION": "Location",
                        "LINE NO.": "Line Number",
                        "AREA CLASSIFICATION": "Area Classification",
                        "INST MODEL NO": "Model",
                        "CALIBRATION RANGE\n(M3/Hr)": "Calibration Range",
                        "INSTRUMENT RANGE\n(M3/Hr)": "Instrument Range",
                        "METER SIZE(inch)": "Meter Size",
                        "PIPELINE MOC": "Pipeline MOC",
                        "CONDUCTIVITY\n(Micro Siemens/cm)": "Conductivity",
                        "LINE SIZE(mm)": "Line Size",
                        "SPECIFIC GRAVITY": "Specific Gravity",
                        "INSTRUMENT RANGE\n(Kg/cm2 g)": "Instrument Range",
                        "CALIBRATED RANGE\n(Kg/cm2 g)": "Calibration Range",
                        "TYPE": "Type",
                    }
                    for raw_col, mapped_col in col_map.items():
                        if raw_col in row and row[raw_col]:
                            specs[mapped_col] = row[raw_col]
                    # Also add remaining unmapped keys
                    for k, v in row.items():
                        if k not in col_map and not _should_skip(k) and v:
                            specs[k] = v

                    ex = build_training_example(instrument_type, specs)
                    if ex:
                        examples.append(ex)

    return examples


def main():
    print("=== iEZ SDIE Dataset Preparation ===\n")
    examples = process_all_datasheets()

    # Deduplicate
    seen = set()
    unique = []
    for ex in examples:
        key = ex["input"][:100]
        if key not in seen:
            seen.add(key)
            unique.append(ex)

    random.shuffle(unique)

    split = int(len(unique) * 0.9)
    train = unique[:split]
    val = unique[split:]

    train_path = OUT_DIR / "dataset.jsonl"
    val_path = OUT_DIR / "dataset_val.jsonl"

    with open(train_path, "w") as f:
        for ex in train:
            f.write(json.dumps(ex) + "\n")

    with open(val_path, "w") as f:
        for ex in val:
            f.write(json.dumps(ex) + "\n")

    print(f"\n✓ Train examples : {len(train)} → {train_path}")
    print(f"✓ Val   examples : {len(val)}   → {val_path}")
    print("\nSample example:")
    if train:
        ex = train[0]
        print("INPUT:", ex["input"][:300])
        print("OUTPUT:", ex["output"][:300])


if __name__ == "__main__":
    main()
