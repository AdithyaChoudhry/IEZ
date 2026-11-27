"""
I/O List Generator router.
"""
from fastapi.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from typing import Optional
import io
import json

from ..offload import off_main_loop
from ..deps import get_current_user
from ..auth.models import User
from ..services.document_registry import register_safe
from ..models.list_generator import (ListAnalyzeResponse, ListGenerateResponse, CompositionResponse, CompositionSheet,
                                     BasisPreviewResponse)
from ..services import io_list_cover

# Import existing business logic
import sys
sys.path.insert(0, '/app')
from utils.template_processor import analyze_iodb_for_list, process_io_list
from utils import workbook_assembly as wa
from utils.file_handler import read_iodb
from utils.io_list_basis import build_basis
from utils.io_list_builder import build_io_list_document
from utils.io_list_document import STANDARD_TEMPLATE
from utils.generators import _apply_column_filters

STANDARD_TEMPLATE_NAME = "IO_List_Standard_Template.xlsx"


router = APIRouter(prefix="/io-list", tags=["I/O List"])

io_list_cache: dict = {}


@router.post("/analyze", response_model=ListAnalyzeResponse)
@off_main_loop
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
@off_main_loop
async def io_list_composition(
    template_file: Optional[UploadFile] = File(None),
    output_mode: str = Form(wa.WITHOUT_SUMMARY),
    current_user: User = Depends(get_current_user),
):
    """Preview of the output workbook: every template sheet + IO List (+ IO Summary when selected)."""
    try:
        mode = wa.normalize_mode(output_mode)
        data = await template_file.read() if template_file is not None else STANDARD_TEMPLATE.read_bytes()
        return CompositionResponse(output_mode=mode, sheets=[CompositionSheet(**s) for s in _composition(data, mode)])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not read the template: {e}")


def _json(text: str, what: str) -> dict:
    try:
        v = json.loads(text) if text and text.strip() else {}
        if not isinstance(v, dict):
            raise ValueError("not an object")
        return v
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {what}: {e}")


@router.post("/basis", response_model=BasisPreviewResponse)
async def preview_io_basis(
    iodb_file: UploadFile = File(...),
    filters: str = Form("{}"),
    basis_overrides: str = Form("{}"),
    basis_names: str = Form("{}"),
    current_user: User = Depends(get_current_user),
):
    """The IO_BASIS classes found in the IODB (same rows as the I/O List: the filters apply) with their representative loops and review status."""
    df, err = read_iodb(io.BytesIO(await iodb_file.read()))
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to read IODB: {err}")
    flt = _json(filters, "filters")
    res = await run_in_threadpool(lambda: build_basis(_apply_column_filters(df, flt or None), _json(basis_overrides, "basis_overrides"),
                                                      _json(basis_names, "basis_names")))
    return BasisPreviewResponse(classes=res.review_rows(), issues=res.issues, stats=res.stats, error=res.error)


@router.post("/generate", response_model=ListGenerateResponse)
async def generate_io_list(
    iodb_file: UploadFile = File(...),
    template_file: Optional[UploadFile] = File(None),
    selected_columns: str = Form(...),  # JSON array of column names
    filters: str = Form("{}"),  # JSON object of {column: [values]}
    project_id: Optional[str] = Form(None),  # optional: register output in the project document registry
    cover_template_file: Optional[UploadFile] = File(None),  # optional custom cover sheet template (default: iEZ cover sheet)
    output_mode: str = Form(wa.WITHOUT_SUMMARY),  # WITHOUT_SUMMARY | WITH_SUMMARY
    basis_overrides: str = Form("{}"),            # {class key: representative loop number} chosen in the IO_BASIS review
    basis_names: str = Form("{}"),                # {class key: EQUIPMENT wording} edited in the IO_BASIS review
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
    standard = template_file is None                      # no template uploaded: the stored iEZ standard I/O List template is used
    cover_tpl = await cover_template_file.read() if cover_template_file is not None else None
    snapshot, basis_report = None, None
    if standard:
        template_bytes = STANDARD_TEMPLATE.read_bytes()
        df, rerr = read_iodb(io.BytesIO(iodb_bytes))
        if rerr:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to read IODB: {rerr}")
        # one consistent snapshot of the linked cover sheet for the whole request (headers, revision history and the inserted cover)
        snapshot = await run_in_threadpool(io_list_cover.snapshot, project_id, cover_tpl)
        out_bytes, filename, err, basis_report = await run_in_threadpool(
            build_io_list_document, df, columns_list, filters_dict if filters_dict else None, output_mode, snapshot["cover"],
            _json(basis_overrides, "basis_overrides"), _json(basis_names, "basis_names"))
    else:
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
                      template_filename=template_file.filename if template_file is not None else STANDARD_TEMPLATE_NAME)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    # The downloaded workbook must be exactly what the preview promised.
    planned = [s["name"] for s in _composition(template_bytes, output_mode)]
    mismatch = wa.check_composition(out_bytes, planned)
    if mismatch:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=mismatch)

    from .deliverables import finalize
    out_bytes, filename, cover = await run_in_threadpool(finalize, current_user.id, "io_list", project_id, out_bytes,
                                                         filename, custom_template=cover_tpl, snapshot=snapshot)
    if cover.get("cover_sheet") and cover["cover_sheet"] not in planned:
        planned = [cover["cover_sheet"]] + planned
    cache_key = f"{current_user.id}_io_list"
    io_list_cache[cache_key] = {"bytes": out_bytes, "filename": filename}      # replaces any earlier run (no stale summary)

    registry = register_safe(
        "success", project_id=project_id, module="io_list", user=current_user.username,
        source_bytes=iodb_bytes, source_filename=iodb_file.filename or "IODB.xlsx",
        output_bytes=out_bytes, output_filename=filename, params=reg_params,
        template_bytes=template_bytes,
        template_filename=template_file.filename if template_file is not None else STANDARD_TEMPLATE_NAME,
    )

    return ListGenerateResponse(filename=filename, message="I/O List generated successfully",
                                 registry=registry, output_mode=output_mode, sheets=planned, cover=cover, basis=basis_report)


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
