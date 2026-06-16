"""
iEZ SDIE — Hugging Face Inference API client.

After the Kaggle training completes and the model is pushed to HF,
call extract_specifications() from anywhere in the app.

Usage:
    from ai_training.hf_inference import extract_specifications

    result = extract_specifications(
        tender_text="Pressure Transmitter, Tag: PT-201, Range: 0-10 bar, Output: 4-20mA HART...",
        instrument_hint="Pressure Transmitter"   # optional
    )
    # result is a dict: { "Instrument Type": {"value": ..., "confidence": ...}, ... }

Environment:
    HF_TOKEN   — your Hugging Face token (hf_...)
    HF_MODEL   — optional override, default: AdithyaChoudhry/iez-sdie-llama3-lora
"""

from __future__ import annotations

import json
import os
import re
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

HF_MODEL = os.environ.get("HF_MODEL", "AdithyaChoudhry/iez-sdie-qwen3-lora")
HF_TOKEN = os.environ.get("HF_TOKEN", "")

SYSTEM_PROMPT = (
    "You are an Instrumentation Engineering Expert and Datasheet Preparation Assistant "
    "for EPC Water, Wastewater, Desalination, ETP, STP, RO and ZLD Projects.\n\n"
    "Your task: Given a Tender Specification or instrument description text, extract all "
    "technical specifications and return them as a JSON object.\n\n"
    "Each field must have:\n"
    "- \"value\": the extracted specification value\n"
    "- \"confidence\": a percentage (0-100) indicating how certain you are\n\n"
    "If a value is not found, set value to null and confidence to 0.\n"
    "Return ONLY valid JSON. No explanation, no extra text."
)


def _build_prompt(tender_text: str) -> str:
    return (
        f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n"
        f"{SYSTEM_PROMPT}<|eot_id|>"
        f"<|start_header_id|>user<|end_header_id|>\n"
        f"{tender_text}<|eot_id|>"
        f"<|start_header_id|>assistant<|end_header_id|>\n"
    )


def _call_hf_api(prompt: str, max_tokens: int = 1024) -> str:
    """Call HF Inference API (serverless) and return raw text response."""
    if not HF_TOKEN:
        raise ValueError(
            "HF_TOKEN environment variable not set. "
            "Add it to your .env or export HF_TOKEN=hf_..."
        )

    url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": max_tokens,
            "temperature": 0.1,
            "do_sample": True,
            "return_full_text": False,
        },
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list) and data:
        return data[0].get("generated_text", "")
    if isinstance(data, dict):
        return data.get("generated_text", "")
    return str(data)


def _parse_json_from_response(raw: str) -> dict[str, Any]:
    """Extract JSON from model output — handles extra text/markdown."""
    raw = raw.strip()

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences
    raw_stripped = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(raw_stripped)
    except json.JSONDecodeError:
        pass

    # Find first { ... } block
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
    """
    Extract instrument specifications from tender text using the fine-tuned model.

    Args:
        tender_text: Raw text from tender spec, datasheet, or OCR output.
        instrument_hint: Optional instrument type hint to prepend (improves accuracy).

    Returns:
        Dict mapping field names to {"value": ..., "confidence": ...}
    """
    if instrument_hint:
        tender_text = f"Instrument Type: {instrument_hint}\n{tender_text}"

    prompt = _build_prompt(tender_text)

    try:
        raw = _call_hf_api(prompt)
        result = _parse_json_from_response(raw)
        return result
    except requests.HTTPError as e:
        if e.response.status_code == 503:
            logger.warning("HF model is loading (cold start). Retry in ~20 seconds.")
        raise
    except Exception as e:
        logger.error("HF inference failed: %s", e)
        raise


def extract_specifications_batch(
    texts: list[str],
    instrument_hints: list[str | None] | None = None,
) -> list[dict[str, Any]]:
    """Extract specifications for multiple texts."""
    hints = instrument_hints or [None] * len(texts)
    return [extract_specifications(t, h) for t, h in zip(texts, hints)]


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)

    test_text = """
    Pressure Transmitter required for water treatment plant.
    Tag No: PT-301
    Fluid: Treated Water
    Pressure Range: 0 to 16 bar
    Output Signal: 4-20mA with HART Protocol
    Power Supply: 24V DC Loop Powered
    Accuracy: better than 0.075% of calibrated span
    Enclosure Protection: IP66
    Area Classification: Safe Area
    Process Connection: 1/2 inch NPT Female
    Make: Emerson or equivalent
    """

    print("Testing HF inference...")
    result = extract_specifications(test_text, "Pressure Transmitter")
    print(json.dumps(result, indent=2))
