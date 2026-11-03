"""
I/O List Generator router.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from typing import Optional
import io
import json

from ..deps import get_current_user
from ..auth.models import User
from ..services.document_registry import register_safe
from ..models.list_generator import ListAnalyzeResponse, ListGenerateResponse, CompositionResponse, CompositionSheet

# Import existing business logic
import sys
sys.path.insert(0, '/app')
from utils.template_processor import analyze_iodb_for_list, process_io_list
from utils import workbook_assembly as wa


router = APIRouter(prefix="/io-list", tags=["I/O List"])

io_list_cache: dict = {}


@router.post("/analyze", response_model=ListAnalyzeResponse)
async def analyze_iodb(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Read the IODB file and return its columns, unique values, and a preview."""
    file_bytes = await file.read()
    analysis, err = analyze_iodb_for_list(io.BytesIO(file_bytes), "io_list")

    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    return ListAnalyzeResponse(**analysis)


def _composition(template_bytes: Optional[bytes], mode: str) -> list[dict]:
    """Sheets of the output workbook for this template + mode (same plan the generator is checked against)."""
    tmpl = wa.template_sheets(template_bytes) if template_bytes else []
    hidden = {t["name"]: t["hidden"] for t in tmpl}
    names = wa.plan_sheets([t["name"] for t in tmpl], "IO List" if template_bytes else "Sheet1", wa.IO_SUMMARY_SHEET, mode, False)
    out = []
    for n in names:
        kind = "summary" if n == wa.IO_SUMMARY_SHEET else ("generated" if n == ("IO List" if template_bytes else "Sheet1") else "template")
        out.append({"name": n, "hidden": hidden.get(n, False), "kind": kind})
    return out


@router.post("/composition", response_model=CompositionResponse)
async def io_list_composition(
    template_file: Optional[UploadFile] = File(None),
    output_mode: str = Form(wa.WITHOUT_SUMMARY),
    current_user: User = Depends(get_current_user),
):
    """Preview of the output workbook: every template sheet + IO List (+ IO Summary when selected)."""
    try:
        mode = wa.normalize_mode(output_mode)
        data = await template_file.read() if template_file is not None else None
        return CompositionResponse(output_mode=mode, sheets=[CompositionSheet(**s) for s in _composition(data, mode)])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not read the template: {e}")


@router.post("/generate", response_model=ListGenerateResponse)
async def generate_io_list(
    iodb_file: UploadFile = File(...),
    template_file: Optional[UploadFile] = File(None),
    selected_columns: str = Form(...),  # JSON array of column names
    filters: str = Form("{}"),  # JSON object of {column: [values]}
    project_id: Optional[str] = Form(None),  # optional: register output in the project document registry
    output_mode: str = Form(wa.WITHOUT_SUMMARY),  # WITHOUT_SUMMARY | WITH_SUMMARY
    current_user: User = Depends(get_current_user),
):
    try:
        output_mode = wa.normalize_mode(output_mode)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    try:
        columns_list = json.loads(selected_columns)
        if not columns_list:
            raise ValueError("Empty column selection")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid selected_columns format: {e}",
        )

    try:
        filters_dict = json.loads(filters) if filters else {}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid filters format: {e}",
        )

    iodb_bytes = await iodb_file.read()
    template_buffer = None
    template_bytes = None
    if template_file is not None:
        template_bytes = await template_file.read()
        template_buffer = io.BytesIO(template_bytes)

    out_bytes, filename, err = process_io_list(
        io.BytesIO(iodb_bytes),
        columns_list,
        filters=filters_dict if filters_dict else None,
        template_file=template_buffer,
        output_mode=output_mode,
    )

    reg_params = {"selected_columns": columns_list, "filters": filters_dict, "output_mode": output_mode}
    if err:
        register_safe("failure", project_id=project_id, module="io_list", user=current_user.username,
                      error=err, source_bytes=iodb_bytes, source_filename=iodb_file.filename or "IODB.xlsx",
                      params=reg_params, template_bytes=template_bytes,
                      template_filename=template_file.filename if template_file is not None else None)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    # The downloaded workbook must be exactly what the preview promised.
    planned = [s["name"] for s in _composition(template_bytes, output_mode)]
    mismatch = wa.check_composition(out_bytes, planned)
    if mismatch:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=mismatch)

    cache_key = f"{current_user.id}_io_list"
    io_list_cache[cache_key] = {"bytes": out_bytes, "filename": filename}      # replaces any earlier run (no stale summary)

    registry = register_safe(
        "success", project_id=project_id, module="io_list", user=current_user.username,
        source_bytes=iodb_bytes, source_filename=iodb_file.filename or "IODB.xlsx",
        output_bytes=out_bytes, output_filename=filename, params=reg_params,
        template_bytes=template_bytes,
        template_filename=template_file.filename if template_file is not None else None,
    )

    return ListGenerateResponse(filename=filename, message="I/O List generated successfully",
                                 registry=registry, output_mode=output_mode, sheets=planned)


@router.get("/download")
async def download_io_list(current_user: User = Depends(get_current_user)):
    cache_key = f"{current_user.id}_io_list"
    cached = io_list_cache.get(cache_key)

    if not cached:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No I/O list found. Please generate it first.",
        )

    return StreamingResponse(
        io.BytesIO(cached["bytes"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={cached['filename']}"},
    )
