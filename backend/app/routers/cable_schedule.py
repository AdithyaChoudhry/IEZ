"""
Cable Schedule Generator router.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
import io

from ..deps import get_current_user
from ..auth.models import User
from ..services.document_registry import register_safe
from ..models.cable_schedule import (
    ColumnsResponse,
    CompositionResponse,
    CompositionSheet,
    JBSummaryResponse,
    CableScheduleGenerateResponse,
)

# Import existing business logic
import sys
sys.path.insert(0, '/app')
from utils.template_processor import get_iodb_columns, get_jb_summary, process_cable_schedule
from utils import workbook_assembly as wa
from utils.cable_summary import CABLE_SUMMARY_SHEET


router = APIRouter(prefix="/cable-schedule", tags=["Cable Schedule"])

cable_schedule_cache: dict = {}


@router.post("/columns", response_model=ColumnsResponse)
async def get_columns(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Read the IODB file and return its column names for JB/Tag column mapping."""
    file_bytes = await file.read()
    columns, err = get_iodb_columns(io.BytesIO(file_bytes))

    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    return ColumnsResponse(columns=columns)


@router.post("/preview", response_model=JBSummaryResponse)
async def preview_jb_summary(
    file: UploadFile = File(...),
    jb_column: str = Form(...),
    tag_column: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """Return a junction box → tag count summary for the IODB file."""
    file_bytes = await file.read()
    rows, err = get_jb_summary(io.BytesIO(file_bytes), jb_column, tag_column)

    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    return JBSummaryResponse(rows=rows)


def _composition(template_bytes: bytes, mode: str, extras: Optional[list] = None, include_schedule: bool = True) -> list[dict]:
    """Output sheets for this template + mode. The template's own Cable Schedule sheet is populated in place.
    `extras`: keys of the MCC DI / MCC DO / VFD / MOV / LCP sheets, inserted right after the schedule sheet.
    `include_schedule=False` (extras only): the schedule sheet is not generated and not part of the output."""
    from utils.file_handler import load_workbook_from_upload
    from utils.generators import _find_cs_sheet
    tmpl = wa.template_sheets(template_bytes)
    wb, _, err = load_workbook_from_upload(io.BytesIO(template_bytes), read_only=True)
    if err:
        raise ValueError(err)
    schedule = _find_cs_sheet(wb)
    hidden = {t["name"]: t["hidden"] for t in tmpl}
    names = wa.plan_sheets([t["name"] for t in tmpl], schedule or "", CABLE_SUMMARY_SHEET, mode, True)
    out = [{"name": n, "hidden": hidden.get(n, False),
            "kind": "summary" if wa._key(n) == wa._key(CABLE_SUMMARY_SHEET) else ("generated" if n == schedule else "template")}
           for n in names]
    if extras:
        from utils.cable_schedule_extra import sheet_titles
        titles = sheet_titles([t["name"] for t in tmpl], extras)
        at = next((i for i, s in enumerate(out) if s["name"] == schedule), len(out)) + 1
        out[at:at] = [{"name": titles[k], "hidden": False, "kind": "extra"} for k in extras]
        if not include_schedule:
            out = [s for s in out if s["name"] != schedule]
    return out


def _parse_extras(value: str) -> list:
    from utils.cable_schedule_extra import ExtraSheetError, parse_selection
    try:
        return parse_selection(value)
    except ExtraSheetError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _extra_frame(iodb_bytes: bytes):
    from utils.file_handler import read_iodb
    df, err = read_iodb(io.BytesIO(iodb_bytes))
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to read IODB: {err}")
    return df


@router.post("/extra/availability")
async def extra_sheet_availability(
    iodb_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Which of MCC DI / MCC DO / VFD / MOV / LCP can be built from this IODB (counts, warnings, reasons)."""
    from utils.cable_schedule_extra import ExtraSheetError, availability
    df = _extra_frame(await iodb_file.read())
    try:
        return availability(df)
    except ExtraSheetError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/extra/preview")
async def extra_sheet_preview(
    iodb_file: UploadFile = File(...),
    extra_sheets: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """Real preview of the selected extra sheets (rows come from the IODB, nothing is stored)."""
    from utils.cable_schedule_extra import ExtraSheetError, preview
    extras = _parse_extras(extra_sheets)
    df = _extra_frame(await iodb_file.read())
    try:
        return preview(df, extras)
    except ExtraSheetError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/composition", response_model=CompositionResponse)
async def cable_schedule_composition(
    template_file: UploadFile = File(...),
    output_mode: str = Form(wa.WITH_SUMMARY),
    extra_sheets: str = Form(""),
    include_schedule: bool = Form(True),
    current_user: User = Depends(get_current_user),
):
    """Preview of the output workbook: every template sheet (Cable Schedule populated in place) + Cable Summary when selected."""
    try:
        mode = wa.normalize_mode(output_mode)
        extras = _parse_extras(extra_sheets)
        data = await template_file.read()
        return CompositionResponse(output_mode=mode, sheets=[CompositionSheet(**s)
                                   for s in _composition(data, mode, extras, include_schedule or not extras)])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not read the template: {e}")


@router.post("/generate", response_model=CableScheduleGenerateResponse)
async def generate_cable_schedule(
    iodb_file: UploadFile = File(...),
    template_file: UploadFile = File(...),
    jb_column: str = Form(""),                 # not needed when only the extra sheets are generated
    tag_column: str = Form(""),
    project_id: Optional[str] = Form(None),  # optional: register output in the project document registry
    output_mode: str = Form(wa.WITH_SUMMARY),  # WITHOUT_SUMMARY | WITH_SUMMARY
    extra_sheets: str = Form(""),              # optional: "MCC DI,MCC DO,VFD,MOV,LCP"
    include_schedule: bool = Form(True),       # False: only the extra sheets (needs extra_sheets)
    current_user: User = Depends(get_current_user),
):
    try:
        output_mode = wa.normalize_mode(output_mode)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    extras = _parse_extras(extra_sheets)
    if include_schedule and not (jb_column and tag_column):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Select the Junction Box and Tag Number columns for the Instrument Cable Schedule.")
    if not include_schedule and not extras:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Select the Instrument Cable Schedule or at least one of MCC DI / MCC DO / VFD / MOV / LCP.")
    iodb_bytes = await iodb_file.read()
    template_bytes = await template_file.read()

    extra_report: dict = {}
    out_bytes, filename, err = process_cable_schedule(
        io.BytesIO(iodb_bytes),
        io.BytesIO(template_bytes),
        jb_column,
        tag_column,
        output_mode=output_mode,
        extra_sheets=extras or None,
        extra_report=extra_report,
        include_schedule=include_schedule,
    )

    reg_params = {"jb_column": jb_column, "tag_column": tag_column, "output_mode": output_mode}
    if extras:
        reg_params["extra_sheets"] = extras
        reg_params["include_schedule"] = include_schedule
    if err:
        register_safe("failure", project_id=project_id, module="cable_schedule", user=current_user.username,
                      error=err, source_bytes=iodb_bytes, source_filename=iodb_file.filename or "IODB.xlsx",
                      params=reg_params, template_bytes=template_bytes,
                      template_filename=template_file.filename)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    # The downloaded workbook must be exactly what the preview promised.
    planned = [s["name"] for s in _composition(template_bytes, output_mode, extras, include_schedule)]
    mismatch = wa.check_composition(out_bytes, planned)
    if mismatch:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=mismatch)

    cache_key = f"{current_user.id}_cable_schedule"
    cable_schedule_cache[cache_key] = {"bytes": out_bytes, "filename": filename}

    registry = register_safe(
        "success", project_id=project_id, module="cable_schedule", user=current_user.username,
        source_bytes=iodb_bytes, source_filename=iodb_file.filename or "IODB.xlsx",
        output_bytes=out_bytes, output_filename=filename, params=reg_params,
        template_bytes=template_bytes, template_filename=template_file.filename,
    )

    return CableScheduleGenerateResponse(filename=filename, message="Cable Schedule generated successfully",
                                         registry=registry, output_mode=output_mode, sheets=planned,
                                         extra_sheets=extra_report.get("sheets") or None,
                                         extra_stats=extra_report.get("stats") or None,
                                         extra_warnings=extra_report.get("warnings") or None)


@router.get("/download")
async def download_cable_schedule(current_user: User = Depends(get_current_user)):
    cache_key = f"{current_user.id}_cable_schedule"
    cached = cable_schedule_cache.get(cache_key)

    if not cached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No cable schedule found. Please generate it first.",
        )

    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={cached['filename']}"},
    )
