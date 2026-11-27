"""Process Data Requisition Generator router."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from typing import Optional
import io
import json

from ..offload import off_main_loop
from ..deps import get_current_user
from ..auth.models import User
from ..models.process_data import (
    InstrumentTypeOption, InstrumentTypesResponse, MatchedTag, ProcessFieldOption,
    ProcessDataMatchResponse, ProcessDataGenerateResponse, ProcessProfileResponse, DetectResponse,
)

# Import existing business logic
import sys
sys.path.insert(0, '/app')
from utils.file_handler import read_iodb
from utils.process_data_library import INSTRUMENT_TYPES
from utils.process_data_matcher import match_tags, match_tags_detailed, detect_groups, build_prefill_values, all_tags
from utils.process_data_generator import generate_process_data_requisition, generate_combined_requisition, column_header
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


def _subtype_messages(cfg, subtype, res) -> list:
    msgs = []
    if not res["matched"]:
        msgs.append(f"No {cfg.label} tag is established as '{subtype}' by the IODB wording.")
    if res["excluded"]:
        msgs.append("Not included (another subtype): " + ", ".join(f"{n} {k}" for k, n in sorted(res["excluded"].items())) + ".")
    if res["unresolved"]:
        msgs.append(f"{len(res['unresolved'])} {cfg.label} record(s) have no stated subtype, so they are not placed in '{subtype}'. "
                    "They are listed for review below; add them only if you know they are this subtype.")
    return msgs


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
@off_main_loop
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

    _check_subtype(cfg, subtype)
    res = match_tags_detailed(df, instrument_type, subtype or None)
    matched_rows, unresolved, warnings = res["matched"], res["unresolved"], list(res["warnings"])
    if not matched_rows and not unresolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No matching {cfg.label} tags were found in the IODB.",
        )
    if res["filtered"]:
        warnings += _subtype_messages(cfg, subtype, res)
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
        subtype=subtype or "",
        unresolved_tags=[MatchedTag(**row) for row in unresolved],
        excluded_counts=res["excluded"],
    )


@router.post("/generate", response_model=ProcessDataGenerateResponse)
@off_main_loop
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
    if cfg.is_custom:
        all_matched = all_tags(df)
    else:
        res = match_tags_detailed(df, instrument_type, subtype or None)
        # the tags of the selected subtype, plus the unresolved ones the engineer chose to add explicitly
        all_matched = res["matched"] + [{k: v for k, v in r.items() if k != "reason"} for r in res["unresolved"]]
    if not all_matched:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No matching {cfg.label} tags were found in the IODB.",
        )
    selected_set = set(selected_tags_parsed)
    outside = sorted(selected_set - {r["tag_no"] for r in all_matched})
    if outside and not cfg.is_custom:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"{len(outside)} selected tag(s) do not belong to {cfg.label}"
                                    f"{' / ' + subtype if subtype else ''}: {', '.join(outside[:5])}. Find the matching tags again.")
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


# ── All Instrument Types ─────────────────────────────────────────────────────────────────────────────────────────────
import hashlib                                                          # noqa: E402
import threading                                                        # noqa: E402

_detect_cache: dict = {}                      # user id -> {"digest", "df", "result"}: the IODB is parsed and classified once
_detect_lock = threading.Lock()


def _detected(user_id, file_bytes: bytes):
    digest = hashlib.sha256(file_bytes).hexdigest()
    with _detect_lock:
        hit = _detect_cache.get(user_id)
    if hit and hit["digest"] == digest:
        return hit["df"], hit["result"]
    df, err = read_iodb(io.BytesIO(file_bytes))
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    result = detect_groups(df)
    with _detect_lock:
        _detect_cache[user_id] = {"digest": digest, "df": df, "result": result}
    return df, result


@router.post("/detect-types", response_model=DetectResponse)
async def detect_types(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Every supported instrument type / subtype in the IODB with its tags; unsupported, ambiguous and unresolved records are
    reported, never forced into a type."""
    from fastapi.concurrency import run_in_threadpool
    data = await file.read()
    _df, result = await run_in_threadpool(_detected, current_user.id, data)
    if not result["groups"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No supported instrument types were found in the IODB.")
    return DetectResponse(**result)


@router.post("/generate-all", response_model=ProcessDataGenerateResponse)
async def generate_all(
    iodb_file: UploadFile = File(...),
    selections: str = Form(...),
    use_iodb_values: bool = Form(False),
    project_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    """One workbook with a requisition sheet per selected instrument type / subtype. selections = JSON list of
    {key, tags: [TAG NO], selected_fields: [names] | null}; each group is re-derived from the IODB here, so a tag or a
    column that does not belong to its group is refused."""
    from fastapi.concurrency import run_in_threadpool
    try:
        picks = json.loads(selections)
        if not isinstance(picks, list) or not picks:
            raise ValueError("no instrument type selected")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid selections: {e}")
    data = await iodb_file.read()
    df, detected = await run_in_threadpool(_detected, current_user.id, data)
    by_key = {g["key"]: g for g in detected["groups"]}
    notes: list = []
    groups = []
    seen = set()
    for p in picks:
        g = by_key.get(p.get("key") if isinstance(p, dict) else None)
        if g is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown instrument group: {p.get('key') if isinstance(p, dict) else p}")
        if g["key"] in seen:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{g['label']} was selected twice.")
        seen.add(g["key"])
        cfg = INSTRUMENT_TYPES[g["type_key"]]
        sub = g["subtype"] or None
        tags = p.get("tags")
        if not isinstance(tags, list) or not tags or not all(isinstance(t, str) for t in tags):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Select at least one tag of {g['label']}.")
        outside = sorted(set(tags) - {t["tag_no"] for t in g["tags"]})
        if outside:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"{len(outside)} selected tag(s) do not belong to {g['label']}: {', '.join(outside[:5])}.")
        chosen = set(tags)
        rows = [{k: v for k, v in t.items() if k != "reason"} for t in g["tags"] if t["tag_no"] in chosen]
        names = p.get("selected_fields")
        valid = {f.name for f in resolve_fields(cfg, sub)}
        if names is None:
            names = default_field_names(cfg, sub)
        else:
            unknown = [n for n in names if n not in valid]
            if not isinstance(names, list) or unknown:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"Unknown process data column(s) for {g['label']}: {', '.join(map(str, unknown[:5]))}")
            names = list(dict.fromkeys(names))
        if not names:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Select at least one process data column for {g['label']}.")
        prefill = build_prefill_values(df, rows, g["type_key"], use_iodb_values, subtype=sub, notes=notes)
        groups.append({"type_key": g["type_key"], "subtype": sub, "label": g["label"], "rows": rows, "prefill": prefill,
                       "selected_fields": names})
    out_bytes, filename = await run_in_threadpool(generate_combined_requisition, groups, project_id or "Project",
                                                  iodb_file.filename or "IODB.xlsx")
    process_data_cache[f"{current_user.id}_process_data"] = {"bytes": out_bytes, "filename": filename}
    total = sum(len(g["rows"]) for g in groups)
    return ProcessDataGenerateResponse(filename=filename, message=f"Process Data Requisition generated: {total} tag(s) in {len(groups)} instrument type sheet(s).",
                                       warnings=list(dict.fromkeys(notes)))


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
