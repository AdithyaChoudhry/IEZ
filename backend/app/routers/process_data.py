"""Process Data Requisition Generator router."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from typing import Optional
import io
import json

from ..deps import get_current_user
from ..auth.models import User
from ..models.process_data import (
    InstrumentTypeOption, InstrumentTypesResponse, MatchedTag, ProcessFieldOption,
    ProcessDataMatchResponse, ProcessDataGenerateResponse, ProcessProfileResponse,
)

# Import existing business logic
import sys
sys.path.insert(0, '/app')
from utils.file_handler import read_iodb
from utils.process_data_library import INSTRUMENT_TYPES
from utils.process_data_matcher import match_tags, build_prefill_values, all_tags
from utils.process_data_generator import generate_process_data_requisition, column_header
from utils.process_data_profiles import PROFILES, resolve_fields, default_field_names, profile_info


router = APIRouter(prefix="/process-data", tags=["Process Data Requisition"])

process_data_cache: dict = {}

IDENTIFICATION_COLUMNS = ["S.NO", "TAG NO", "EQUIPMENT DESCRIPTION", "P&ID NO.",
                          "SERVICE", "EQUIPMENT NO", "LINE", "LINE SIZE"]


def _field_options(cfg, subtype):
    return [ProcessFieldOption(
        name=f.name, header=column_header(f), mandatory=f.mandatory, unit=f.unit, category=f.category,
        default_selected=f.default_selected, source_annexure_label=f.annexure_label,
        field_type=f.field_type.value, options=list(f.options))
        for f in resolve_fields(cfg, subtype)]


def _check_subtype(cfg, subtype):
    if subtype and subtype not in cfg.subtypes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"Unknown subtype '{subtype}' for {cfg.label}.")


@router.get("/instrument-types", response_model=InstrumentTypesResponse)
async def list_instrument_types(current_user: User = Depends(get_current_user)):
    options = [
        InstrumentTypeOption(
            key=cfg.key, label=cfg.label, category=cfg.category,
            subtypes=list(cfg.subtypes),
            verified_subtypes=sorted(st for (t, st) in PROFILES if t == cfg.key),
        )
        for cfg in INSTRUMENT_TYPES.values()
    ]
    return InstrumentTypesResponse(instrument_types=options)


@router.get("/profile", response_model=ProcessProfileResponse)
async def get_profile_endpoint(instrument_type: str, subtype: Optional[str] = None,
                               current_user: User = Depends(get_current_user)):
    """The parameters of one instrument type / subtype: every available field with its unit and category, and
    which of them the verified datasheet profile selects by default. The backend configuration is authoritative."""
    cfg = INSTRUMENT_TYPES.get(instrument_type)
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown instrument type: {instrument_type}")
    _check_subtype(cfg, subtype)
    if cfg.is_custom:
        return ProcessProfileResponse(instrument_type=instrument_type, subtype=subtype or "")
    return ProcessProfileResponse(instrument_type=instrument_type, subtype=subtype or "",
                                  fields=_field_options(cfg, subtype),
                                  default_fields=default_field_names(cfg, subtype), **profile_info(cfg, subtype))


@router.post("/match-tags", response_model=ProcessDataMatchResponse)
async def match_tags_endpoint(
    file: UploadFile = File(...),
    instrument_type: str = Form(...),
    subtype: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    cfg = INSTRUMENT_TYPES.get(instrument_type)
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"Unknown instrument type: {instrument_type}")

    file_bytes = await file.read()
    df, err = read_iodb(io.BytesIO(file_bytes))
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    if cfg.is_custom:
        # No automatic matching for custom types: list every IODB tag, the engineer picks.
        rows = all_tags(df)
        if not rows:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                 detail="No tags were found in the IODB.")
        return ProcessDataMatchResponse(
            instrument_type=instrument_type, matched_tags=[MatchedTag(**r) for r in rows],
            tag_count=len(rows), identification_columns=IDENTIFICATION_COLUMNS,
            process_columns=[],
            warnings=["Custom type: all IODB tags are listed - select the ones that need process data."],
        )

    matched_rows, warnings = match_tags(df, instrument_type)
    if not matched_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No matching {cfg.label} tags were found in the IODB.",
        )

    _check_subtype(cfg, subtype)
    options = _field_options(cfg, subtype)
    process_columns = [o.header for o in options]

    return ProcessDataMatchResponse(
        instrument_type=instrument_type,
        matched_tags=[MatchedTag(**row) for row in matched_rows],
        tag_count=len(matched_rows),
        identification_columns=IDENTIFICATION_COLUMNS,
        process_columns=process_columns,
        process_fields=options,
        default_fields=default_field_names(cfg, subtype),
        warnings=warnings,
    )


@router.post("/generate", response_model=ProcessDataGenerateResponse)
async def generate_process_data(
    iodb_file: UploadFile = File(...),
    instrument_type: str = Form(...),
    subtype: Optional[str] = Form(None),
    selected_tags: str = Form(...),
    use_iodb_values: bool = Form(False),
    custom_fields: Optional[str] = Form(None),
    custom_name: Optional[str] = Form(None),
    selected_fields: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    cfg = INSTRUMENT_TYPES.get(instrument_type)
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"Unknown instrument type: {instrument_type}")

    try:
        selected_tags_parsed = json.loads(selected_tags)
        if not selected_tags_parsed:
            raise ValueError("Empty tag selection")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"Invalid selected_tags format: {e}")

    custom_fields_list = None
    if custom_fields:
        try:
            custom_fields_list = json.loads(custom_fields)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                 detail=f"Invalid custom_fields format: {e}")

    if cfg.is_custom and not custom_fields_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one custom process-data field must be defined before generating.",
        )

    _check_subtype(cfg, subtype)
    selected_fields_list = None
    if selected_fields and not cfg.is_custom:
        try:
            selected_fields_list = json.loads(selected_fields)
            if not isinstance(selected_fields_list, list) or not all(isinstance(x, str) for x in selected_fields_list):
                raise ValueError("expected a list of field names")
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                 detail=f"Invalid selected_fields format: {e}")
        valid = {f.name for f in resolve_fields(cfg, subtype)}
        unknown = [x for x in selected_fields_list if x not in valid]
        if unknown:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                 detail=f"Unknown process data column(s) for {cfg.label}"
                                        f"{' / ' + subtype if subtype else ''}: {', '.join(unknown[:5])}")
        selected_fields_list = list(dict.fromkeys(selected_fields_list))        # no duplicate columns
        if not selected_fields_list:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                 detail="Select at least one process data column to request.")
    elif not cfg.is_custom:
        # No selection sent: the verified profile's defaults (all fields for a type without a verified profile).
        selected_fields_list = default_field_names(cfg, subtype)

    iodb_bytes = await iodb_file.read()
    df, err = read_iodb(io.BytesIO(iodb_bytes))
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    if not isinstance(selected_tags_parsed, list) or not all(isinstance(t, str) for t in selected_tags_parsed):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="selected_tags must be a JSON list of TAG NO strings.")
    all_matched = all_tags(df) if cfg.is_custom else match_tags(df, instrument_type)[0]
    if not all_matched:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No matching {cfg.label} tags were found in the IODB.",
        )
    selected_set = set(selected_tags_parsed)
    matched_rows = [r for r in all_matched if r["tag_no"] in selected_set]
    if not matched_rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="None of the selected tags matched the IODB.")
    notes: list = []
    prefill = ([{} for _ in matched_rows] if cfg.is_custom
               else build_prefill_values(df, matched_rows, instrument_type, use_iodb_values, subtype=subtype, notes=notes))

    project_name = project_id or "Project"
    out_bytes, filename = generate_process_data_requisition(
        matched_rows=matched_rows, prefill=prefill, type_key=instrument_type,
        subtype=subtype, project_name=project_name,
        source_filename=iodb_file.filename or "IODB.xlsx",
        custom_fields=custom_fields_list, custom_name=(custom_name or "").strip(),
        selected_fields=selected_fields_list,
    )

    cache_key = f"{current_user.id}_process_data"
    process_data_cache[cache_key] = {"bytes": out_bytes, "filename": filename}

    return ProcessDataGenerateResponse(
        filename=filename,
        message=f"Process Data Requisition generated: {len(matched_rows)} {cfg.label} tag(s).",
        warnings=list(dict.fromkeys(notes)),
    )


@router.get("/download")
async def download_process_data(current_user: User = Depends(get_current_user)):
    cache_key = f"{current_user.id}_process_data"
    cached = process_data_cache.get(cache_key)
    if not cached:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail="No Process Data Requisition found. Please generate it first.")
    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={cached['filename']}"},
    )
