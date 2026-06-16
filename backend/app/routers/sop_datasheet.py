"""
SOP-driven interactive Datasheet Generator router — Phase 1 (analysis).

Flow:
  POST /sop-datasheet/analyze  (SOP workbook + IODB)  -> available datasheets + IODB instrument types
  POST /sop-datasheet/fields   (SOP workbook + sheet) -> field spec for the interactive form
  POST /sop-datasheet/tags     (IODB + instrument_type) -> matching tags
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from dataclasses import asdict
import io
import json
import uuid
import logging
import threading

from ..deps import get_current_user
from ..auth.models import User
from ..models.sop_datasheet import (
    FieldSpecModel,
    DatasheetInfoModel,
    AnalyzeResponse,
    FieldsResponse,
    TagsResponse,
    GenerateJobResponse,
    GenerateResult,
    GenerateStatusResponse,
)

# Import existing business logic
import sys
sys.path.insert(0, '/app')
from utils.sop_datasheet import (
    read_workbook,
    list_datasheet_sheets,
    parse_field_spec,
    get_iodb_instrument_types,
    get_iodb_tags,
    generate as generate_datasheets,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sop-datasheet", tags=["SOP Datasheet Generator"])

ALLOWED_SOP_EXTENSIONS = {".xls", ".xlsx", ".xlsm"}
ALLOWED_IODB_EXTENSIONS = {".xls", ".xlsx", ".xlsm"}

# In-memory job + download caches (in production, use Redis or a database).
generation_jobs: dict = {}
generation_cache: dict = {}


def _check_ext(filename: str, allowed: set[str]) -> None:
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(allowed))}",
        )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    sop_file: UploadFile = File(...),
    iodb_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Read the SOP workbook + IODB; return available datasheets and instrument types."""
    _check_ext(sop_file.filename or "", ALLOWED_SOP_EXTENSIONS)
    _check_ext(iodb_file.filename or "", ALLOWED_IODB_EXTENSIONS)

    sop_bytes = await sop_file.read()
    iodb_bytes = await iodb_file.read()

    try:
        sheets = read_workbook(sop_bytes, sop_file.filename or "")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to read SOP workbook: {exc}")

    datasheets = [DatasheetInfoModel(**asdict(d)) for d in list_datasheet_sheets(sheets)]

    types, err = get_iodb_instrument_types(iodb_bytes)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    return AnalyzeResponse(
        datasheets=datasheets,
        instrument_types=types,
        message=f"Found {len(datasheets)} datasheet(s) and {len(types)} instrument type(s)",
    )


@router.post("/fields", response_model=FieldsResponse)
async def fields(
    sop_file: UploadFile = File(...),
    datasheet_sheet: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """Return the ordered field spec (iodb vs predefined + defaults) for a datasheet."""
    _check_ext(sop_file.filename or "", ALLOWED_SOP_EXTENSIONS)
    sop_bytes = await sop_file.read()

    try:
        sheets = read_workbook(sop_bytes, sop_file.filename or "")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to read SOP workbook: {exc}")

    if datasheet_sheet not in sheets:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sheet '{datasheet_sheet}' not found in SOP workbook.")

    infos = {d.sheet: d for d in list_datasheet_sheets(sheets)}
    info = infos.get(datasheet_sheet)
    eg_model = sheets.get(info.eg_sheet) if (info and info.eg_sheet) else None

    specs = parse_field_spec(sheets[datasheet_sheet], eg_model)
    return FieldsResponse(
        datasheet=datasheet_sheet,
        title=info.title if info else datasheet_sheet,
        fields=[FieldSpecModel(**asdict(s)) for s in specs],
    )


@router.post("/tags", response_model=TagsResponse)
async def tags(
    iodb_file: UploadFile = File(...),
    instrument_type: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """Return the IODB tags whose INSTRUMENT TYPE matches the selection."""
    _check_ext(iodb_file.filename or "", ALLOWED_IODB_EXTENSIONS)
    iodb_bytes = await iodb_file.read()

    tag_list, err = get_iodb_tags(iodb_bytes, instrument_type)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    return TagsResponse(instrument_type=instrument_type, tags=tag_list, count=len(tag_list))


def _run_generate_job(job_id, sop_bytes, sop_filename, datasheet_sheet,
                      iodb_bytes, instrument_type, selected_tags, overrides, user_id):
    """Generate one datasheet per tag in a background thread."""
    try:
        zip_bytes, filename, err = generate_datasheets(
            sop_bytes, sop_filename, datasheet_sheet,
            iodb_bytes, instrument_type, selected_tags, overrides,
        )
        if err:
            generation_jobs[job_id] = {"status": "error", "error": err}
            return
        generation_cache[f"{user_id}_sop_datasheet"] = {"bytes": zip_bytes, "filename": filename}
        generation_jobs[job_id] = {
            "status": "done",
            "result": GenerateResult(
                filename=filename,
                tag_count=len(selected_tags),
                message=f"Generated {len(selected_tags)} datasheet(s) for {instrument_type}",
            ),
        }
        logger.info("SOP datasheet job %s done: %d tags", job_id, len(selected_tags))
    except Exception as exc:
        logger.exception("SOP datasheet job %s failed", job_id)
        generation_jobs[job_id] = {"status": "error", "error": str(exc)}


@router.post("/generate", response_model=GenerateJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate(
    sop_file: UploadFile = File(...),
    iodb_file: UploadFile = File(...),
    datasheet_sheet: str = Form(...),
    instrument_type: str = Form(...),
    selected_tags: str = Form(...),   # JSON array
    overrides: str = Form("{}"),      # JSON object: {label: [values]}
    current_user: User = Depends(get_current_user),
):
    """Kick off datasheet generation (one file per tag); poll the status endpoint."""
    _check_ext(sop_file.filename or "", ALLOWED_SOP_EXTENSIONS)
    _check_ext(iodb_file.filename or "", ALLOWED_IODB_EXTENSIONS)

    try:
        tags_list = json.loads(selected_tags)
        overrides_dict = json.loads(overrides) if overrides else {}
        if not tags_list:
            raise ValueError("No tags selected")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid request data: {exc}")

    sop_bytes = await sop_file.read()
    iodb_bytes = await iodb_file.read()

    job_id = str(uuid.uuid4())
    generation_jobs[job_id] = {"status": "processing"}

    threading.Thread(
        target=_run_generate_job,
        args=(job_id, sop_bytes, sop_file.filename or "", datasheet_sheet,
              iodb_bytes, instrument_type, tags_list, overrides_dict, current_user.id),
        daemon=True,
    ).start()

    return GenerateJobResponse(job_id=job_id, status="processing")


@router.get("/generate/status/{job_id}", response_model=GenerateStatusResponse)
async def get_generate_status(job_id: str, current_user: User = Depends(get_current_user)):
    """Poll the status/result of a datasheet generation job."""
    job = generation_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation job not found")
    return GenerateStatusResponse(
        job_id=job_id, status=job["status"],
        result=job.get("result"), error=job.get("error"),
    )


@router.get("/download")
async def download(current_user: User = Depends(get_current_user)):
    """Download the generated datasheets ZIP."""
    cached = generation_cache.get(f"{current_user.id}_sop_datasheet")
    if not cached:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No generated datasheets found. Please generate first.")
    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={cached['filename']}"},
    )
