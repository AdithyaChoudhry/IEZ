"""
FastAPI router for LT Non-Contact Radar Datasheet module.

Endpoints:
  GET  /lt-radar/specs-meta          → field definitions + dropdown options
  POST /lt-radar/tags                → tag list from IODB
  POST /lt-radar/iodb-lookup         → field values for a selected tag
  POST /lt-radar/validate            → run rule engine
  POST /lt-radar/ai-extract          → AI extraction from tender text/file
  POST /lt-radar/generate            → produce clean xlsx datasheet
"""
import io
import json
import logging
import os

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from ..deps import get_current_user
from ..auth.models import User
from ..models.lt_radar import (
    AiExtractedField, AiExtractResponse, IódbLookupResponse,
    SpecField, SpecsMetaResponse, TagsResponse, ValidationResult,
)

import sys
sys.path.insert(0, "/app")
from utils.lt_radar_datasheet import (
    SPEC_FIELDS, DROPDOWN_OPTIONS, DEFAULTS,
    get_iodb_tags, iodb_lookup, generate, validate_specs,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lt-radar", tags=["LT Non-Contact Radar Datasheet"])

ALLOWED_IODB = {".xls", ".xlsx", ".xlsm"}
ALLOWED_DOC  = {".pdf", ".docx", ".xlsx", ".txt"}


def _check_ext(filename: str, allowed: set[str]) -> None:
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in allowed:
        raise HTTPException(status_code=400,
            detail=f"Unsupported file '{ext}'. Allowed: {', '.join(sorted(allowed))}")


# ---------------------------------------------------------------------------
@router.get("/specs-meta", response_model=SpecsMetaResponse)
async def specs_meta(current_user: User = Depends(get_current_user)):
    """Return all field definitions, dropdown options, and defaults."""
    fields_out: list[SpecField] = []
    for f in SPEC_FIELDS:
        opts_key = f.get("options")
        opts = DROPDOWN_OPTIONS.get(opts_key, []) if opts_key else None
        # Dynamic beam angle options come from the frontend logic
        if f.get("options_dynamic") == "beam_angle":
            opts = DROPDOWN_OPTIONS["beam_angle_80"] + DROPDOWN_OPTIONS["beam_angle_26"]
        fields_out.append(SpecField(
            id=f["id"], label=f["label"], section=f["section"],
            color=f["color"], options=opts,
            default=DEFAULTS.get(f["id"]),
            fixed=f.get("fixed"),
        ))
    return SpecsMetaResponse(
        fields=fields_out, dropdowns=DROPDOWN_OPTIONS, defaults=DEFAULTS)


# ---------------------------------------------------------------------------
@router.post("/tags", response_model=TagsResponse)
async def tags(
    iodb_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Return list of tag numbers from the uploaded IODB."""
    _check_ext(iodb_file.filename or "", ALLOWED_IODB)
    raw = await iodb_file.read()
    tag_list, err = get_iodb_tags(raw)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return TagsResponse(tags=tag_list, count=len(tag_list))


# ---------------------------------------------------------------------------
@router.post("/iodb-lookup", response_model=IódbLookupResponse)
async def iodb_lookup_endpoint(
    iodb_file: UploadFile = File(...),
    tag_no: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """Fetch all GREEN field values for the selected tag from IODB."""
    _check_ext(iodb_file.filename or "", ALLOWED_IODB)
    raw = await iodb_file.read()
    found, err = iodb_lookup(raw, tag_no)

    green_fields = [f["id"] for f in SPEC_FIELDS if f["color"] == "green"]
    missing = [fid for fid in green_fields if not found.get(fid)]

    return IódbLookupResponse(
        tag_no=tag_no, values=found, missing_fields=missing,
        error=err if err and not found else None,
    )


# ---------------------------------------------------------------------------
@router.post("/validate", response_model=ValidationResult)
async def validate(
    spec_json: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """Run rule engine on the current spec values."""
    try:
        values: dict = json.loads(spec_json)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in spec_json")
    errors = validate_specs(values)
    warnings = [e for e in errors if e.startswith("Warning")]
    errors    = [e for e in errors if not e.startswith("Warning")]
    return ValidationResult(errors=errors, warnings=warnings, passed=len(errors) == 0)


# ---------------------------------------------------------------------------
@router.post("/ai-extract", response_model=AiExtractResponse)
async def ai_extract(
    spec_labels: str = Form(...),           # JSON list of {id, label}
    tender_text: str = Form(""),
    tender_file: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
):
    """Use Groq AI to extract RED field values from a tender/spec document."""
    text = tender_text.strip()
    if tender_file is not None:
        raw_bytes = await tender_file.read()
        ext = (tender_file.filename or "").rsplit(".", 1)[-1].lower()
        if ext == "pdf":
            try:
                import pdfminer.high_level as pm
                text = pm.extract_text(io.BytesIO(raw_bytes))[:10000]
            except Exception:
                text = raw_bytes.decode("utf-8", errors="ignore")[:10000]
        else:
            text = raw_bytes.decode("utf-8", errors="ignore")[:10000]

    if not text:
        return AiExtractResponse(fields=[], error="No text provided for extraction.")

    try:
        label_list: list[dict] = json.loads(spec_labels)
    except Exception:
        raise HTTPException(status_code=400, detail="spec_labels must be JSON array of {id, label}")

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        return AiExtractResponse(fields=[], error="GROQ_API_KEY not configured.")

    labels_text = "\n".join(f'  - "{item["label"]}"' for item in label_list)
    prompt = (
        "You are an expert instrument specification extractor for water treatment plant projects.\n"
        "Given the following tender / technical specification text, extract values for each specification below.\n\n"
        f"SPECIFICATION FIELDS TO EXTRACT:\n{labels_text}\n\n"
        f"TEXT:\n{text[:7000]}\n\n"
        "Respond with ONLY a JSON array (no markdown):\n"
        '[\n  {"label": "<field label>", "value": "<extracted value or empty>", "confidence": <0.0-1.0>, "snippet": "<short excerpt>"},\n  ...\n]\n'
        "If a field is not found in the text, set value to \"\" and confidence to 0.0."
    )

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile",
                      "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.1, "max_tokens": 1024},
            )
        raw_content = resp.json()["choices"][0]["message"]["content"].strip()
        if raw_content.startswith("```"):
            raw_content = raw_content.split("```")[1]
            if raw_content.startswith("json"):
                raw_content = raw_content[4:]
        parsed: list[dict] = json.loads(raw_content)

        # Build id→label lookup
        id_map = {item["label"]: item["id"] for item in label_list}
        out_fields: list[AiExtractedField] = []
        for item in parsed:
            lbl = item.get("label", "")
            out_fields.append(AiExtractedField(
                label=lbl,
                field_id=id_map.get(lbl, lbl),
                value=str(item.get("value", "")),
                confidence=float(item.get("confidence", 0.0)),
                snippet=str(item.get("snippet", "")),
            ))
        return AiExtractResponse(fields=out_fields)

    except Exception as exc:
        logger.exception("AI extract failed")
        return AiExtractResponse(fields=[], error=str(exc))


# ---------------------------------------------------------------------------
@router.post("/generate")
async def generate_datasheet(
    values_json: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a clean LT Non-Contact Radar datasheet xlsx.
    values_json: JSON dict of field_id → value.
    Returns the xlsx file as a download.
    """
    try:
        values: dict = json.loads(values_json)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in values_json")

    # Final validation
    errors = validate_specs(values)
    hard_errors = [e for e in errors if not e.startswith("Warning")]
    if hard_errors:
        raise HTTPException(status_code=422, detail={"validation_errors": hard_errors})

    try:
        xlsx_bytes = generate(values)
    except Exception as exc:
        logger.exception("LT radar datasheet generation failed")
        raise HTTPException(status_code=500, detail=f"Generation failed: {exc}")

    tag_no = values.get("tag_no", "LT_RADAR").replace("/", "-").replace(" ", "_")
    filename = f"LT_Radar_Datasheet_{tag_no}.xlsx"

    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
