"""
Smart Datasheet Intelligence Engine (SDIE) router.

Phase 1: upload a vendor datasheet (PDF/image), OCR it, extract label/value
specifications with confidence scores, and normalize labels to canonical
WABAG field names.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
import io
import uuid
import logging
import threading

from ..deps import get_current_user
from ..auth.models import User
from ..models.sdie import (
    ExtractedSpec,
    ExtractionResponse,
    ExtractionJobResponse,
    ExtractionStatusResponse,
    MappingLogEntry,
    GenerateResponse,
    GenerateJobResponse,
    GenerateStatusResponse,
)

# Import existing business logic
import sys
sys.path.insert(0, '/app')
from utils.sdie_extractor import (
    extract_specifications,
    generate_populated_datasheet,
    specs_to_excel_bytes,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sdie", tags=["Smart Datasheet Intelligence"])

# Store extraction job status/results temporarily (in production, use Redis or database)
extraction_jobs: dict = {}

# Store generation job status/results temporarily (in production, use Redis or database)
generation_jobs: dict = {}

# Store downloadable output bytes per user (in production, use Redis or database)
extraction_cache: dict = {}
generation_cache: dict = {}

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
ALLOWED_TEMPLATE_EXTENSIONS = {".xlsx", ".xlsm"}


def _run_extraction_job(job_id: str, file_bytes: bytes, filename: str, user_id: int, template_bytes: bytes | None = None):
    """Run OCR extraction in a background thread and store the result/status."""
    try:
        specs, page_count, instrument_type = extract_specifications(file_bytes, filename, template_bytes)

        extraction_cache[f"{user_id}_sdie_extract"] = {
            "bytes": specs_to_excel_bytes(specs),
            "filename": "Extracted_Specifications.xlsx",
        }

        extraction_jobs[job_id] = {
            "status": "done",
            "result": ExtractionResponse(
                specs=[ExtractedSpec(**s) for s in specs],
                page_count=page_count,
                message=f"Extracted {len(specs)} specification(s) from {page_count} page(s)",
                instrument_type=instrument_type,
            ),
        }
        logger.info("SDIE extract job %s done: %d specs, type=%r", job_id, len(specs), instrument_type)
    except Exception as exc:
        logger.exception("SDIE extract job %s failed", job_id)
        extraction_jobs[job_id] = {"status": "error", "error": str(exc)}


@router.post("/extract", response_model=ExtractionJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def extract_datasheet(
    file: UploadFile = File(...),
    template_file: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_user),
):
    """
    Kick off AI extraction of a tender document.
    Optionally upload a WABAG template alongside for template-aware field targeting.
    Poll GET /sdie/extract/status/{job_id} for the result.
    """
    filename = file.filename or ""
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    file_bytes = await file.read()
    template_bytes = await template_file.read() if template_file else None

    job_id = str(uuid.uuid4())
    extraction_jobs[job_id] = {"status": "processing"}

    threading.Thread(
        target=_run_extraction_job,
        args=(job_id, file_bytes, filename, current_user.id, template_bytes),
        daemon=True,
    ).start()

    return ExtractionJobResponse(job_id=job_id, status="processing")


@router.get("/extract/status/{job_id}", response_model=ExtractionStatusResponse)
async def get_extraction_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Poll the status/result of a datasheet extraction job."""
    job = extraction_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Extraction job not found",
        )

    return ExtractionStatusResponse(
        job_id=job_id,
        status=job["status"],
        result=job.get("result"),
        error=job.get("error"),
    )


@router.get("/extract/download")
async def download_extracted_specs(current_user: User = Depends(get_current_user)):
    """Download the most recently extracted specifications as an Excel file."""
    cached = extraction_cache.get(f"{current_user.id}_sdie_extract")
    if not cached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No extracted specifications found. Please extract first.",
        )

    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={cached['filename']}"},
    )


def _run_generation_job(job_id: str, file_bytes: bytes, filename: str, template_bytes: bytes, user_id: int):
    """Run OCR extraction + WABAG template population in a background thread."""
    try:
        specs, page_count, instrument_type = extract_specifications(file_bytes, filename, template_bytes)

        out_bytes, mapping_log, err = generate_populated_datasheet(template_bytes, specs)
        if err:
            generation_jobs[job_id] = {"status": "error", "error": err}
            return

        out_filename = "Datasheet_Populated.xlsx"
        generation_cache[f"{user_id}_sdie_generate"] = {"bytes": out_bytes, "filename": out_filename}
        extraction_cache[f"{user_id}_sdie_extract"] = {
            "bytes": specs_to_excel_bytes(specs),
            "filename": "Extracted_Specifications.xlsx",
        }

        matched = sum(1 for e in mapping_log if e["status"] == "MATCHED")
        generation_jobs[job_id] = {
            "status": "done",
            "result": GenerateResponse(
                specs=[ExtractedSpec(**s) for s in specs],
                page_count=page_count,
                mapping_log=[MappingLogEntry(**e) for e in mapping_log],
                filename=out_filename,
                message=f"Mapped {matched}/{len(mapping_log)} template field(s) from {len(specs)} extracted specification(s)",
                instrument_type=instrument_type,
            ),
        }
        logger.info("SDIE generate job %s done: %d specs, %d matched", job_id, len(specs), matched)
    except Exception as exc:
        logger.exception("SDIE generate job %s failed", job_id)
        generation_jobs[job_id] = {"status": "error", "error": str(exc)}


@router.post("/generate", response_model=GenerateJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_datasheet(
    file: UploadFile = File(...),
    template_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Kick off OCR extraction of a vendor datasheet AND population of a WABAG
    datasheet template with the extracted specs. Runs in the background —
    poll GET /sdie/generate/status/{job_id} for the result, then
    GET /sdie/download to retrieve the populated workbook.
    """
    filename = file.filename or ""
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    template_filename = template_file.filename or ""
    template_ext = ""
    if "." in template_filename:
        template_ext = "." + template_filename.rsplit(".", 1)[-1].lower()
    if template_ext not in ALLOWED_TEMPLATE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported template file type '{template_ext}'. Allowed: {', '.join(sorted(ALLOWED_TEMPLATE_EXTENSIONS))}",
        )

    file_bytes = await file.read()
    template_bytes = await template_file.read()

    job_id = str(uuid.uuid4())
    generation_jobs[job_id] = {"status": "processing"}

    threading.Thread(
        target=_run_generation_job,
        args=(job_id, file_bytes, filename, template_bytes, current_user.id),
        daemon=True,
    ).start()

    return GenerateJobResponse(job_id=job_id, status="processing")


@router.get("/generate/status/{job_id}", response_model=GenerateStatusResponse)
async def get_generation_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Poll the status/result of a datasheet generation job."""
    job = generation_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation job not found",
        )

    return GenerateStatusResponse(
        job_id=job_id,
        status=job["status"],
        result=job.get("result"),
        error=job.get("error"),
    )


@router.get("/download")
async def download_populated_datasheet(current_user: User = Depends(get_current_user)):
    """Download the most recently populated WABAG datasheet for this user."""
    cached = generation_cache.get(f"{current_user.id}_sdie_generate")
    if not cached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No populated datasheet found. Please generate it first.",
        )

    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={cached['filename']}"},
    )
