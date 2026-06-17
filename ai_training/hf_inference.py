"""
iEZ SDIE — Groq inference client.

Calls Llama 3.1 70B via Groq's free API for spec extraction.

Usage:
    from ai_training.hf_inference import extract_specifications
    result = extract_specifications(tender_text)

Environment:
    GROQ_API_KEY — your Groq API key (gsk_...)
"""

from __future__ import annotations

import json
import os
import re
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """You are an Instrumentation Engineering Expert and Datasheet Preparation Assistant for EPC Water, Wastewater, Desalination, ETP, STP, RO and ZLD Projects (WABAG standard).

Your task: Extract all technical specifications from the given text and return a JSON object.

Rules:
- Each field must have: {"value": "extracted value", "confidence": <0-100>}
- Confidence 95-100: explicitly stated. 80-94: clearly implied. 60-79: inferred. Below 60: uncertain.
- Always extract: Instrument Type, Tag Number, Fluid, Measuring Range, Output Signal, Power Supply, Accuracy, Enclosure Protection, Area Classification, Make, Model
- Map synonyms: e.g. "4-20mA HART" = Output Signal, "IP66" = Enclosure Protection, "ATEX" = Area Certification
- Return ONLY valid JSON. No explanation, no extra text.

Instrument types include: Pressure Transmitter, Differential Pressure Transmitter, Magnetic Flow Meter, Ultrasonic Flow Meter, Thermal Mass Flow Meter, Non Contact Radar Level Transmitter, Guided Wave Radar Level Transmitter, Ultrasonic Level Transmitter, DP Level Transmitter, Pressure Gauge, Level Switch, Flow Switch, Temperature Transmitter, pH Analyser, Conductivity Analyser, Dissolved Oxygen Analyser, Turbidity Analyser.

Example output:
{
  "Instrument Type": {"value": "Pressure Transmitter", "confidence": 99},
  "Tag Number": {"value": "PT-201", "confidence": 100},
  "Fluid": {"value": "Raw Water", "confidence": 97},
  "Output Signal": {"value": "4-20mA HART", "confidence": 99},
  "Power Supply": {"value": "24 VDC", "confidence": 99},
  "Accuracy": {"value": "±0.075%", "confidence": 98},
  "Enclosure Protection": {"value": "IP66", "confidence": 99},
  "Area Classification": {"value": "Safe Area", "confidence": 97}
}"""


def _call_groq(text: str) -> str:
    key = os.environ.get("GROQ_API_KEY", GROQ_API_KEY)
    if not key:
        raise ValueError("GROQ_API_KEY not set")

    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 1024,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _parse_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    logger.warning("Could not parse JSON from model response: %s", raw[:200])
    return {}


def extract_specifications(
    tender_text: str,
    instrument_hint: str | None = None,
) -> dict[str, Any]:
    if instrument_hint:
        tender_text = f"Instrument Type: {instrument_hint}\n{tender_text}"
    try:
        raw = _call_groq(tender_text)
        return _parse_json(raw)
    except Exception as e:
        logger.error("Groq inference failed: %s", e)
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test = """
    Pressure Transmitter required for water treatment plant.
    Tag No: PT-301, Fluid: Treated Water, Pressure Range: 0 to 16 bar,
    Output Signal: 4-20mA with HART, Power Supply: 24V DC Loop Powered,
    Accuracy: ±0.075%, Enclosure: IP66, Area: Safe Area,
    Process Connection: 1/2 inch NPT Female, Make: Emerson
    """
    print(json.dumps(extract_specifications(test), indent=2))
