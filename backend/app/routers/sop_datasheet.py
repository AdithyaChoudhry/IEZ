"""
SOP-driven interactive Datasheet Generator router — Phase 1 (analysis).

Flow:
  POST /sop-datasheet/analyze  (SOP workbook + IODB)  -> available datasheets + IODB instrument types
  POST /sop-datasheet/fields   (SOP workbook + sheet) -> field spec for the interactive form
  POST /sop-datasheet/tags     (IODB + instrument_type) -> matching tags
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from dataclasses import asdict
import io
import json
import uuid
import logging
import threading
import tempfile
from pathlib import Path

from ..offload import off_main_loop
from ..deps import get_current_user, get_db
from ..auth.models import User, ApprovalRequest
from sqlalchemy.orm import Session
from ..models.sop_datasheet import (
    FieldSpecModel,
    DatasheetInfoModel,
    AnalyzeResponse,
    InstrumentTypesResponse,
    DatasheetsResponse,
    FieldsResponse,
    TagsResponse,
    GenerateJobResponse,
    GenerateResult,
    GenerateStatusResponse,
    ExtractSpecResponse,
    VendorMatch,
    VendorRecommendResponse,
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
    generate_with_report as generate_datasheets,
)
from utils import sop_consolidated as SC
from utils import datasheet_library as DL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sop-datasheet", tags=["SOP Datasheet Generator"])

ALLOWED_SOP_EXTENSIONS = {".xls", ".xlsx", ".xlsm"}
ALLOWED_IODB_EXTENSIONS = {".xls", ".xlsx", ".xlsm"}

# In-memory job + download caches (in production, use Redis or a database).
generation_jobs: dict = {}
generation_cache: dict = {}

# Generated ZIPs are also written to disk so a download still works after the
# service restarts (every deploy restarts iez.service and wipes the dicts above).
_OUTPUT_DIR = Path(tempfile.gettempdir()) / "iez_sop_datasheet_output"


def _output_path(user_id) -> Path:
    return _OUTPUT_DIR / f"{user_id}_sop_datasheet.zip"


def _output_meta(user_id) -> tuple[Path, Path]:
    """Format-independent copy of the last output (file + its name), so a download survives a restart."""
    return _OUTPUT_DIR / f"{user_id}_sop_datasheet.bin", _OUTPUT_DIR / f"{user_id}_sop_datasheet.name"


def _media_type(filename: str) -> str:
    return "application/zip" if filename.lower().endswith(".zip") else \
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _check_ext(filename: str, allowed: set[str]) -> None:
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(allowed))}",
        )


@router.post("/analyze", response_model=AnalyzeResponse)
@off_main_loop
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


@router.post("/instrument-types", response_model=InstrumentTypesResponse)
@off_main_loop
async def instrument_types(
    iodb_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Read the IODB and return distinct instrument types (IODB-first workflow)."""
    _check_ext(iodb_file.filename or "", ALLOWED_IODB_EXTENSIONS)
    iodb_bytes = await iodb_file.read()
    types, err = get_iodb_instrument_types(iodb_bytes)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return InstrumentTypesResponse(instrument_types=types, count=len(types))


@router.post("/datasheets", response_model=DatasheetsResponse)
@off_main_loop
async def datasheets(
    sop_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Read the SOP workbook and return available instrument datasheet sheets."""
    _check_ext(sop_file.filename or "", ALLOWED_SOP_EXTENSIONS)
    sop_bytes = await sop_file.read()
    try:
        sheets = read_workbook(sop_bytes, sop_file.filename or "")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to read SOP workbook: {exc}")
    return DatasheetsResponse(datasheets=[DatasheetInfoModel(**asdict(d), **SC.annexure_info(sheets, d.sheet))
                                          for d in list_datasheet_sheets(sheets)])


@router.post("/fields", response_model=FieldsResponse)
@off_main_loop
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
    # Parse the EG example sheet (rows 9–60) so the popup fields + defaults match
    # exactly what generation will fill.
    target_name = info.eg_sheet if (info and info.eg_sheet) else datasheet_sheet
    target_model = sheets.get(target_name) or sheets[datasheet_sheet]

    specs = parse_field_spec(target_model, target_model)
    ann = SC.annexure_info(sheets, datasheet_sheet)
    return FieldsResponse(
        datasheet=datasheet_sheet,
        title=info.title if info else datasheet_sheet,
        fields=[FieldSpecModel(**asdict(s)) for s in specs],
        annexure_sheet=ann["annexure_sheet"],
        annexure_capacity=ann["annexure_capacity"],
    )


@router.post("/tags", response_model=TagsResponse)
@off_main_loop
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


def _warm_library():
    """Parse the 11 library workbooks once in the background so the first wizard call is fast."""
    try:
        for t in DL.library():
            DL.template_info(t)
    except Exception:
        logger.warning("Datasheet template library warm-up failed", exc_info=True)


threading.Thread(target=_warm_library, daemon=True).start()


@router.get("/library")
async def library_list(current_user: User = Depends(get_current_user)):
    """The standard datasheet template library."""
    try:
        return {"templates": [await run_in_threadpool(DL.template_info, t) for t in DL.library()]}
    except DL.LibraryError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/library/analyze-iodb")
async def library_analyze_iodb(iodb_file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Instrument types in the IODB, their tags and the matching library template (with how sure the match is)."""
    _check_ext(iodb_file.filename or "", ALLOWED_IODB_EXTENSIONS)
    data = await iodb_file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The IODB file is empty.")
    try:
        return await run_in_threadpool(DL.analyze_iodb, data)
    except DL.LibraryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/library/{template_id}")
async def library_template(template_id: str, field_scope: str = "", current_user: User = Depends(get_current_user)):
    """Template details: sheet roles, field rules from the Engineering Guide, annexure columns."""
    try:
        t = DL.entry(template_id)
        scope = _json_obj(field_scope, "field scope") if field_scope else None
        fields, info = await run_in_threadpool(DL.fields_for, t, scope)
        tinfo = await run_in_threadpool(DL.template_info, t)
    except DL.LibraryError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {"template": tinfo, "fields": [f.to_dict() for f in fields], "notes": info["notes"],
            "header_fields": DL.HEADER_FIELDS}


def _run_generate_job(job_id, sop_bytes, sop_filename, datasheet_sheet,
                      iodb_bytes, instrument_type, selected_tags, overrides, user_id,
                      generation_format=SC.INDIVIDUAL, annexure_mapping=None, approval_id=None,
                      template_id=None, header=None, field_scope=None, annexure_values=None,
                      project_id=None, cover_template=None):
    """Generate the datasheet package in a background thread (individual: one file per tag; consolidated: one workbook;
    library template: one consolidated workbook from the standard template library)."""
    try:
        if template_id:
            zip_bytes, filename, err, failed = DL.generate(template_id, iodb_bytes, selected_tags, overrides,
                                                           annexure_mapping, header, field_scope, annexure_values)
        elif generation_format == SC.INDIVIDUAL:
            zip_bytes, filename, err, failed = generate_datasheets(
                sop_bytes, sop_filename, datasheet_sheet,
                iodb_bytes, instrument_type, selected_tags, overrides,
            )
        else:
            zip_bytes, filename, err, failed = SC.generate_package(
                generation_format, sop_bytes, sop_filename, datasheet_sheet,
                iodb_bytes, instrument_type, selected_tags, overrides, annexure_mapping,
            )
        if err:
            generation_jobs[job_id] = {"status": "error", "error": err}
            return
        generated = len(set(map(str, selected_tags))) - len(failed)
        # centralised cover sheet: one per datasheet document (library template = instrument type), Excel and PDF alike
        from .deliverables import finalize
        try:
            label = DL.entry(template_id)["display_name"] if template_id else instrument_type
        except Exception:
            label = instrument_type
        zip_bytes, filename, cover = finalize(user_id, "datasheet", project_id, zip_bytes, filename,
                                              sub_key=template_id or str(instrument_type or ""), sub_label=label,
                                              custom_template=cover_template)
        generation_cache[f"{user_id}_sop_datasheet"] = {"bytes": zip_bytes, "filename": filename}
        try:
            _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            if filename.lower().endswith(".zip"):
                _output_path(user_id).write_bytes(zip_bytes)
            data_p, name_p = _output_meta(user_id)
            data_p.write_bytes(zip_bytes)
            name_p.write_text(filename)
        except OSError:
            logger.warning("Could not persist datasheet ZIP to disk", exc_info=True)
        generation_jobs[job_id] = {
            "status": "done",
            "result": GenerateResult(
                filename=filename,
                cover=cover,
                tag_count=generated,
                requested_count=len(set(map(str, selected_tags))),
                failed_tags=failed,
                format=generation_format,
                approval_id=approval_id,
                message=(
                    (f"Consolidated datasheet generated for {instrument_type}: main datasheet + annexure with {generated} tag(s)"
                     if generation_format == SC.CONSOLIDATED else f"Generated {generated} datasheet(s) for {instrument_type}")
                    if not failed else
                    f"{generated} of {generated + len(failed)} tags generated for {instrument_type}. {len(failed)} failed."
                ),
            ),
        }
        logger.info("SOP datasheet job %s done: %d generated, %d failed, zip=%d bytes",
                    job_id, generated, len(failed), len(zip_bytes))
    except Exception as exc:
        logger.exception("SOP datasheet job %s failed", job_id)
        generation_jobs[job_id] = {"status": "error", "error": str(exc)}


def _approved_package(db: Session, approval_id: int, fmt: str, tags: list, datasheet_sheet: str,
                      template_id: str | None = None, meta_out: dict | None = None) -> tuple[dict, dict | None]:
    """The approved request must cover exactly this package; returns (approved overrides + approval stamps, approved mapping)."""
    req = db.get(ApprovalRequest, approval_id)
    if req is None or req.request_type != "spec":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Approval request #{approval_id} not found.")
    if req.status != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Approval request #{approval_id} is {req.status} - datasheets are generated only after Lead Engineer approval.")
    try:
        payload = json.loads(req.payload_json or "{}")
        approved_tags = json.loads(req.tag_numbers or "[]")
    except ValueError:
        payload, approved_tags = {}, []
    meta = payload.get("__iez") or {}
    approved_fmt = meta.get("format", SC.INDIVIDUAL)
    if approved_fmt != fmt:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Request #{approval_id} was approved for '{SC.FORMAT_LABELS.get(approved_fmt, approved_fmt)}', not "
                                   f"'{SC.FORMAT_LABELS.get(fmt, fmt)}'. Changing the format needs a new approval.")
    if sorted({str(t).strip() for t in approved_tags}) != sorted({str(t).strip() for t in tags}):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"The selected tags differ from the tags approved in request #{approval_id}. Raise a new approval.")
    if (meta.get("template_id") or None) != (template_id or None):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Request #{approval_id} was approved for a different datasheet template. "
                                   "Changing the template needs a new approval.")
    if meta_out is not None:
        meta_out.update(header=meta.get("header") if isinstance(meta.get("header"), dict) else {},
                        field_scope=meta.get("field_scope") if isinstance(meta.get("field_scope"), dict) else {},
                        annexure_values=meta.get("annexure_values") if isinstance(meta.get("annexure_values"), dict) else {})
    if meta.get("datasheet") and meta["datasheet"] != datasheet_sheet:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Request #{approval_id} was approved for datasheet '{meta['datasheet']}', not '{datasheet_sheet}'.")
    overrides = {str(k): [str(x) for x in (v if isinstance(v, list) else [v])] for k, v in (meta.get("overrides") or {}).items()}
    if req.reviewed_by_name:
        overrides["Approved By"] = [req.reviewed_by_name]
    if req.reviewed_by_id:
        overrides["Employee ID"] = [req.reviewed_by_id]
    if req.updated_at:
        overrides["Approval Date"] = [req.updated_at.strftime("%Y-%m-%d %H:%M")]
    mapping = meta.get("annexure_mapping")
    return overrides, (mapping if isinstance(mapping, dict) else None)


def _json_obj(raw: str, what: str) -> dict:
    try:
        v = json.loads(raw) if raw else {}
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {what}.")
    if not isinstance(v, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {what}.")
    return v


@router.post("/validate")
async def validate_package(
    sop_file: UploadFile | None = File(None),
    iodb_file: UploadFile = File(...),
    datasheet_sheet: str = Form(""),
    instrument_type: str = Form(""),
    selected_tags: str = Form(...),
    generation_format: str = Form(SC.INDIVIDUAL),
    overrides: str = Form("{}"),
    annexure_mapping: str = Form("{}"),
    template_id: str = Form(""),                     # standard template library (no SOP upload)
    header: str = Form("{}"),
    field_scope: str = Form("{}"),
    ai_confidence: str = Form("{}"),
    annexure_values: str = Form("{}"),               # library: {tag: {annexure column: value}} for cells the IODB leaves blank
    current_user: User = Depends(get_current_user),
):
    """Engineering checks before approval: tags in the IODB, duplicates, mandatory values, common specs that differ per tag,
    unresolved placeholders (individual), annexure mapping / blank tag data (consolidated). Nothing is corrected."""
    _check_ext(iodb_file.filename or "", ALLOWED_IODB_EXTENSIONS)
    try:
        tags_list = json.loads(selected_tags)
        overrides_dict = json.loads(overrides) if overrides else {}
        mapping_dict = json.loads(annexure_mapping) if annexure_mapping else {}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid request data: {exc}")
    if template_id:
        try:
            return await run_in_threadpool(DL.validate, template_id, await iodb_file.read(), tags_list, overrides_dict,
                                           mapping_dict, instrument_type, _json_obj(header, "document header"),
                                           _json_obj(field_scope, "field scope"), _json_obj(ai_confidence, "AI confidence"),
                                           _json_obj(annexure_values, "annexure values"))
        except DL.LibraryError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if sop_file is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a datasheet template.")
    _check_ext(sop_file.filename or "", ALLOWED_SOP_EXTENSIONS)
    try:
        ctx = SC.load_context(await sop_file.read(), sop_file.filename or "", datasheet_sheet, await iodb_file.read())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return SC.validate(ctx, (generation_format or "").strip().upper(), tags_list, overrides_dict, mapping_dict)


@router.post("/generate", response_model=GenerateJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate(
    sop_file: UploadFile | None = File(None),
    iodb_file: UploadFile = File(...),
    datasheet_sheet: str = Form(""),
    instrument_type: str = Form(...),
    selected_tags: str = Form(...),   # JSON array
    overrides: str = Form("{}"),      # JSON object: {label: [values]}
    generation_format: str = Form(SC.INDIVIDUAL),   # INDIVIDUAL | CONSOLIDATED
    approval_id: int | None = Form(None),           # Lead Engineer approval of exactly this package
    annexure_mapping: str = Form("{}"),             # consolidated: {annexure column: IODB column}
    template_id: str = Form(""),                    # standard template library: consolidated only, approval required
    project_id: str | None = Form(None),            # selected project: resolves the datasheet's cover sheet (MDL)
    cover_template_file: UploadFile | None = File(None),   # optional custom cover sheet template
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Kick off datasheet generation; poll the status endpoint.

    INDIVIDUAL   - one datasheet per tag, zipped (existing behaviour).
    CONSOLIDATED - one workbook: main datasheet + tag-wise annexure. Requires an approved request; the approved values are used.
    When an approval_id is given, the package must match what was approved (format, tags, datasheet) and the approved
    specification values are used instead of the ones sent by the browser."""
    if template_id:
        try:
            DL.entry(template_id)
        except DL.LibraryError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        generation_format = SC.CONSOLIDATED                       # the library always produces the consolidated document
    elif sop_file is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a datasheet template.")
    else:
        _check_ext(sop_file.filename or "", ALLOWED_SOP_EXTENSIONS)
    _check_ext(iodb_file.filename or "", ALLOWED_IODB_EXTENSIONS)

    try:
        tags_list = json.loads(selected_tags)
        overrides_dict = json.loads(overrides) if overrides else {}
        mapping_dict = json.loads(annexure_mapping) if annexure_mapping else {}
        if not tags_list:
            raise ValueError("No tags selected")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid request data: {exc}")
    fmt = (generation_format or SC.INDIVIDUAL).strip().upper()
    if fmt not in SC.FORMATS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unknown generation_format '{generation_format}'. Use {' or '.join(SC.FORMATS)}.")
    if fmt == SC.CONSOLIDATED and approval_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="The consolidated datasheet needs an approved request - raise it for Lead Engineer approval first.")
    approved_meta: dict = {}
    if approval_id is not None:
        overrides_dict, approved_mapping = _approved_package(db, approval_id, fmt, tags_list, datasheet_sheet,
                                                             template_id or None, approved_meta)
        if approved_mapping is not None:
            mapping_dict = approved_mapping

    sop_bytes = await sop_file.read() if sop_file is not None else b""
    iodb_bytes = await iodb_file.read()
    cover_tpl = await cover_template_file.read() if cover_template_file is not None else None

    job_id = str(uuid.uuid4())
    generation_jobs[job_id] = {"status": "processing"}

    threading.Thread(
        target=_run_generate_job,
        args=(job_id, sop_bytes, (sop_file.filename if sop_file else "") or "", datasheet_sheet,
              iodb_bytes, instrument_type, tags_list, overrides_dict, current_user.id,
              fmt, mapping_dict, approval_id, template_id or None,
              approved_meta.get("header") or {}, approved_meta.get("field_scope") or {},
              approved_meta.get("annexure_values") or {}, project_id, cover_tpl),
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
    if cached:
        data, filename = cached["bytes"], cached["filename"]
    else:
        data_p, name_p = _output_meta(current_user.id)
        if data_p.exists() and name_p.exists():
            data, filename = data_p.read_bytes(), name_p.read_text().strip() or "Datasheets.zip"
        else:
            path = _output_path(current_user.id)
            if not path.exists():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="No generated datasheets found. Please generate first.")
            data, filename = path.read_bytes(), "Datasheets.zip"
    logger.info("SOP datasheet download: user=%s file=%s bytes=%d source=%s",
                current_user.id, filename, len(data), "memory" if cached else "disk")
    return StreamingResponse(
        io.BytesIO(data),
        media_type=_media_type(filename),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(data)),
        },
    )


def _tender_text(raw: bytes, filename: str) -> str:
    """Readable text of a tender document: PDF text layer, OCR for scanned pages / images, plain text otherwise."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    text = ""
    if ext == "pdf" or raw[:4] == b"%PDF":
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                text = "\n".join((p.extract_text() or "") for p in pdf.pages[:40])
        except Exception:
            text = ""
        if len(text.strip()) < 40:                               # scanned PDF: OCR the first pages
            try:
                from utils.sdie_extractor import extract_pages, ocr_page
                text = "\n".join(l["text"] for img in extract_pages(raw, filename)[:6] for l in ocr_page(img))
            except Exception:
                pass
        return text
    if ext in ("png", "jpg", "jpeg", "tif", "tiff", "bmp"):
        try:
            from utils.sdie_extractor import extract_pages, ocr_page
            return "\n".join(l["text"] for img in extract_pages(raw, filename)[:6] for l in ocr_page(img))
        except Exception:
            return ""
    return raw.decode("utf-8", errors="ignore")


async def _groq(prompt: str, max_tokens: int, json_mode: bool = False) -> str:
    import os, httpx
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        raise RuntimeError("GROQ_API_KEY not configured.")
    body = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post("https://api.groq.com/openai/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}, json=body)
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


@router.post("/extract-spec", response_model=ExtractSpecResponse)
@off_main_loop
async def extract_spec(
    label: str = Form("All specifications"),
    tender_text: str = Form(""),
    labels: str = Form(""),                                   # JSON list: extract every field separately
    tender_file: list[UploadFile] | None = File(None),
    current_user: User = Depends(get_current_user),
):
    """
    Extract specification values from tender text or uploaded documents (PDF text / OCR / text) with Groq AI.
    With `labels`, every field gets its own value, confidence and supporting snippet (nothing is copied between fields);
    without it the single-label behaviour is unchanged.
    """
    parts = [tender_text.strip()] if tender_text.strip() else []
    for f in tender_file or []:
        raw = await f.read()
        t = _tender_text(raw, f.filename or "")
        if t.strip():
            parts.append(t)
    text = "\n\n".join(parts)
    if not text.strip():
        return ExtractSpecResponse(label=label, extracted_value="", confidence=0.0, raw_snippet="",
                                   error="No readable text found in the tender documents.")
    try:
        wanted = [str(x) for x in json.loads(labels)] if labels else []
    except ValueError:
        wanted = []

    if wanted:
        prompt = (
            "You are an instrument specification extractor for water treatment plant projects.\n"
            "Extract the value of EACH of the specification fields below from the tender text. Treat every field on its own: "
            "use only text that states that field, never reuse a value for a different field, keep units exactly as written, "
            "and leave value empty with confidence 0 when the text does not state it.\n\n"
            f"FIELDS: {json.dumps(wanted)}\n\nTEXT:\n{text[:14000]}\n\n"
            'Respond with JSON only: {"fields": [{"label": "<field>", "value": "<value or empty>", "confidence": <0.0-1.0>, '
            '"snippet": "<the exact supporting text>"}]}'
        )
        try:
            parsed = json.loads(await _groq(prompt, 3000, json_mode=True))
            got = {str(x.get("label", "")).strip().lower(): x for x in parsed.get("fields", []) if isinstance(x, dict)}
            fields_out = []
            for lab in wanted:
                x = got.get(lab.strip().lower(), {})
                val = str(x.get("value", "") or "").strip()
                fields_out.append({"label": lab, "value": val, "confidence": float(x.get("confidence", 0.0) or 0.0) if val else 0.0,
                                   "snippet": str(x.get("snippet", "") or "")[:400]})
            return ExtractSpecResponse(label=label, extracted_value="", confidence=0.0, raw_snippet="", fields=fields_out, text_chars=len(text))
        except Exception as exc:
            logger.exception("extract-spec (multi) Groq call failed")
            return ExtractSpecResponse(label=label, extracted_value="", confidence=0.0, raw_snippet="", error=str(exc), text_chars=len(text))

    prompt = (
        f"You are an instrument specification extractor for water treatment plant projects.\n"
        f"Given the following tender/datasheet text, extract the value for the specification field: \"{label}\".\n\n"
        f"TEXT:\n{text[:6000]}\n\n"
        f"Respond with a JSON object ONLY:\n"
        f"{{\"value\": \"<extracted value or empty string>\", \"confidence\": <0.0-1.0>, \"snippet\": \"<relevant excerpt>\"}}\n"
        f"If the field is not mentioned, set value to \"\" and confidence to 0.0."
    )
    try:
        parsed = json.loads(await _groq(prompt, 256))
        return ExtractSpecResponse(
            label=label,
            extracted_value=str(parsed.get("value", "")),
            confidence=float(parsed.get("confidence", 0.0)),
            raw_snippet=str(parsed.get("snippet", "")),
            text_chars=len(text),
        )
    except Exception as exc:
        logger.exception("extract-spec Groq call failed")
        return ExtractSpecResponse(label=label, extracted_value="", confidence=0.0,
                                   raw_snippet="", error=str(exc))


@router.post("/vendor-recommend", response_model=VendorRecommendResponse)
async def vendor_recommend(
    instrument_type: str = Form(...),
    spec_json: str = Form("{}"),   # JSON: {label: value, ...}
    current_user: User = Depends(get_current_user),
):
    """
    Use Groq AI to generate a vendor comparison table for the given instrument
    type and collected spec profile. Returns match % per vendor/model.
    """
    import os, httpx

    specs: dict = {}
    try:
        specs = json.loads(spec_json) if spec_json else {}
    except Exception:
        pass

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured.")

    spec_lines = "\n".join(f"  - {k}: {v}" for k, v in specs.items()) or "  (no specs provided)"
    prompt = (
        f"You are a senior instrumentation engineer for a water treatment plant project.\n"
        f"Instrument type: {instrument_type}\n"
        f"Collected technical specifications:\n{spec_lines}\n\n"
        f"Compare the following vendors for this instrument: Endress+Hauser, Emerson, VEGA, ABB, Yokogawa.\n"
        f"For each vendor provide:\n"
        f"  - Their best-fit model name\n"
        f"  - match_pct: integer 0-100 showing how well their product line matches the specs\n"
        f"  - strengths: list of 2-3 short bullet points\n"
        f"  - gaps: list of 0-2 short bullet points (limitations or missing features)\n\n"
        f"Respond with ONLY a JSON array:\n"
        f"[{{\"vendor\":\"...\",\"model\":\"...\",\"match_pct\":...,\"strengths\":[...],\"gaps\":[...]}}, ...]\n"
        f"Sort by match_pct descending."
    )
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.2, "max_tokens": 1024},
            )
        data = resp.json()
        raw = data["choices"][0]["message"]["content"].strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        vendors_raw: list[dict] = json.loads(raw)
        vendors = [VendorMatch(
            vendor=v.get("vendor", ""),
            model=v.get("model", ""),
            match_pct=float(v.get("match_pct", 0)),
            strengths=v.get("strengths", []),
            gaps=v.get("gaps", []),
        ) for v in vendors_raw]
        top = vendors[0].vendor if vendors else ""
        return VendorRecommendResponse(instrument_type=instrument_type, vendors=vendors, recommended=top)
    except Exception as exc:
        logger.exception("vendor-recommend Groq call failed")
        raise HTTPException(status_code=500, detail=f"Vendor recommendation failed: {exc}")
