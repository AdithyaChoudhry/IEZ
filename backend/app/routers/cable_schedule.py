"""
Cable Schedule Generator router.
"""
from typing import Optional
from utils.xlsx_trim import trim_empty_tail
from fastapi.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
import io
import json
import threading
import uuid
from pathlib import Path
from datetime import datetime

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
from utils.template_processor import get_iodb_columns, process_cable_schedule
from utils import workbook_assembly as wa
from utils.cable_summary import CABLE_SUMMARY_SHEET


router = APIRouter(prefix="/cable-schedule", tags=["Cable Schedule"])

cable_schedule_cache: dict = {}

# The last SUCCESSFULLY generated Cable Schedule per (user, project): the single input of the Gland Quantity, Cable Lug
# Quantity and Drum Schedule generators (they read it here, server side - the bytes never go back to the browser).
# Written only after a generation passed every check, so a failed run never replaces a good schedule. Kept on disk (the
# project document store) as well as in memory, so a restart / deploy or a second server process still finds it.
_generated: dict = {}
_generated_lock = threading.Lock()


def _snapshot_dir(user_id, project_key: str):
    import hashlib
    from ..services.document_registry import _store_dir
    return _store_dir() / "cable_schedule_generated" / hashlib.sha256(f"{user_id}|{project_key}".encode()).hexdigest()[:32]


def _save_snapshot(user_id, project_key: str, g: dict) -> None:
    """meta.json + the two workbooks, written to temporary names and renamed (a reader never sees half a snapshot)."""
    d = _snapshot_dir(user_id, project_key)
    d.mkdir(parents=True, exist_ok=True)
    meta = {k: v for k, v in g.items() if k not in ("bytes", "iodb_bytes")}
    for name, data in ((f"{g['id']}.xlsx", g["bytes"]), (f"{g['id']}.iodb", g["iodb_bytes"])):
        tmp = d / (name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(d / name)
    tmp = d / "meta.json.tmp"
    tmp.write_text(json.dumps(meta))
    tmp.replace(d / "meta.json")
    for old in d.iterdir():                                       # keep only the current snapshot
        if old.suffix in (".xlsx", ".iodb") and not old.name.startswith(g["id"]):
            old.unlink(missing_ok=True)


def _load_snapshot(user_id, project_key: str, known_id: Optional[str]) -> Optional[dict]:
    d = _snapshot_dir(user_id, project_key)
    try:
        meta = json.loads((d / "meta.json").read_text())
        if meta.get("id") == known_id:
            return None                                           # memory is current
        return {**meta, "bytes": (d / f"{meta['id']}.xlsx").read_bytes(), "iodb_bytes": (d / f"{meta['id']}.iodb").read_bytes()}
    except (OSError, ValueError, KeyError):
        return None
NOT_GENERATED = ("No generated Cable Schedule is available. Please generate a Cable Schedule using the Cable Schedule "
                 "Generator first.")


def _project_key(project_id: Optional[str]) -> str:
    return (project_id or "").strip()


def get_generated(user_id, project_id: Optional[str]) -> Optional[dict]:
    """The user's last generated Cable Schedule for exactly this project ("" = no project selected); never another
    user's or another project's. The returned dict is a snapshot: its bytes do not change if a newer schedule is made."""
    key = (user_id, _project_key(project_id))
    with _generated_lock:
        mem = _generated.get(key)
        disk = _load_snapshot(user_id, key[1], mem["id"] if mem else None)
        if disk is not None and (mem is None or disk.get("generated_at", "") >= mem.get("generated_at", "")):
            _generated[key] = mem = disk
        return mem


def require_generated(user_id, project_id: Optional[str], generated_id: Optional[str]) -> dict:
    """The snapshot to calculate from. When the page names the schedule it shows (generated_id) and a newer one has been
    generated since, the request is refused so a result is never labelled with the wrong workbook."""
    g = get_generated(user_id, project_id)
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_GENERATED)
    if generated_id and generated_id != g["id"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"A newer Cable Schedule ({g['filename']}, generated {g['generated_at']}) is now available. "
                                   "The page has been refreshed - run the calculation again.")
    return g


def generated_meta(g: Optional[dict]) -> dict:
    if g is None:
        return {"available": False, "message": NOT_GENERATED}
    return {"available": True, "id": g["id"], "filename": g["filename"], "generated_at": g["generated_at"],
            "project_id": g["project_id"] or None, "sheets": g["sheets"], "iodb_filename": g["iodb_filename"],
            "selected_jbs": len(g["selected_jbs"]) if g["selected_jbs"] else None}


@router.post("/columns", response_model=ColumnsResponse)
async def get_columns(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Read the IODB file and return its column names for JB/Tag column mapping."""
    file_bytes = trim_empty_tail(await file.read())
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
    """Junction boxes with ALL their tags (IODB order) - exactly the rows the Instrument Cable Schedule writes."""
    from utils.file_handler import read_iodb
    from utils.cable_schedule_layout import jb_groups
    file_bytes = trim_empty_tail(await file.read())
    df, err = read_iodb(io.BytesIO(file_bytes))
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    try:
        rows = jb_groups(df, jb_column, tag_column)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
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
    df = _extra_frame(trim_empty_tail(await iodb_file.read()))
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
    df = _extra_frame(trim_empty_tail(await iodb_file.read()))
    try:
        return preview(df, extras)
    except ExtraSheetError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "cable_schedule" / "cable_schedule_default_template.xlsx"
DEFAULT_TEMPLATE_NAME = "iEZ default Cable Schedule template.xlsx"


async def _template_bytes(upload: Optional[UploadFile]) -> tuple[bytes, str]:
    """The uploaded template, or the built-in universal iEZ template (blank cover + standard header, no project data)."""
    if upload is not None and (upload.filename or ""):
        data = await upload.read()
        if data:
            return trim_empty_tail(data), upload.filename
    return DEFAULT_TEMPLATE_PATH.read_bytes(), DEFAULT_TEMPLATE_NAME


@router.post("/composition", response_model=CompositionResponse)
async def cable_schedule_composition(
    template_file: Optional[UploadFile] = File(None),
    output_mode: str = Form(wa.WITH_SUMMARY),
    extra_sheets: str = Form(""),
    include_schedule: bool = Form(True),
    current_user: User = Depends(get_current_user),
):
    """Preview of the output workbook: every template sheet (Cable Schedule populated in place) + Cable Summary when selected."""
    try:
        mode = wa.normalize_mode(output_mode)
        extras = _parse_extras(extra_sheets)
        data, _tname = await _template_bytes(template_file)
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
    template_file: Optional[UploadFile] = File(None),    # optional: the built-in iEZ default template is used without it
    jb_column: str = Form(""),                 # not needed when only the extra sheets are generated
    tag_column: str = Form(""),
    project_id: Optional[str] = Form(None),  # optional: register output in the project document registry
    output_mode: str = Form(wa.WITH_SUMMARY),  # WITHOUT_SUMMARY | WITH_SUMMARY
    extra_sheets: str = Form(""),              # optional: "MCC DI,MCC DO,VFD,MOV,LCP"
    include_schedule: bool = Form(True),       # False: only the extra sheets (needs extra_sheets)
    selected_jbs: str = Form(""),              # optional JSON list / comma list of junction boxes (default: all)
    cover_template_file: Optional[UploadFile] = File(None),  # optional custom cover sheet template (default: iEZ cover sheet)
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
    jbs = None
    if selected_jbs.strip():
        try:
            jbs = json.loads(selected_jbs) if selected_jbs.strip().startswith("[") else [x for x in selected_jbs.split(",")]
            jbs = [str(x).strip() for x in jbs if str(x).strip()]
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid junction box selection.")
        if not jbs:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one junction box.")
    iodb_bytes = trim_empty_tail(await iodb_file.read())
    template_bytes, template_name = await _template_bytes(template_file)

    extra_report: dict = {}
    # CPU-bound: run in the worker pool so one long generation does not freeze the server for every other request
    out_bytes, filename, err = await run_in_threadpool(
        process_cable_schedule,
        io.BytesIO(iodb_bytes),
        io.BytesIO(template_bytes),
        jb_column,
        tag_column,
        output_mode=output_mode,
        extra_sheets=extras or None,
        extra_report=extra_report,
        include_schedule=include_schedule,
        selected_jbs=jbs,
    )

    reg_params = {"jb_column": jb_column, "tag_column": tag_column, "output_mode": output_mode}
    if jbs:
        reg_params["selected_jbs"] = jbs
    if extras:
        reg_params["extra_sheets"] = extras
        reg_params["include_schedule"] = include_schedule
    if err:
        register_safe("failure", project_id=project_id, module="cable_schedule", user=current_user.username,
                      error=err, source_bytes=iodb_bytes, source_filename=iodb_file.filename or "IODB.xlsx",
                      params=reg_params, template_bytes=template_bytes,
                      template_filename=template_name)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    # The downloaded workbook must be exactly what the preview promised.
    planned = [s["name"] for s in _composition(template_bytes, output_mode, extras, include_schedule)]
    mismatch = wa.check_composition(out_bytes, planned)
    if mismatch:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=mismatch)

    from .deliverables import finalize
    cover_tpl = await cover_template_file.read() if cover_template_file is not None else None
    out_bytes, filename, cover = await run_in_threadpool(finalize, current_user.id, "cable_schedule", project_id, out_bytes,
                                                         filename, custom_template=cover_tpl)
    if cover.get("cover_sheet") and cover["cover_sheet"] not in planned:
        planned = [cover["cover_sheet"]] + planned
    if cover.get("applied") and extra_report.get("warnings"):          # the project cover replaced the template's cover: the header follows it
        extra_report["warnings"] = [w for w in extra_report["warnings"] if not str(w).startswith("COVERSHEET:")]
    cache_key = f"{current_user.id}_cable_schedule"
    cable_schedule_cache[cache_key] = {"bytes": out_bytes, "filename": filename}
    snap = {"id": uuid.uuid4().hex, "bytes": out_bytes, "filename": filename, "project_id": _project_key(project_id),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "sheets": planned,
            "iodb_bytes": iodb_bytes, "iodb_filename": iodb_file.filename or "IODB.xlsx", "selected_jbs": jbs}
    with _generated_lock:
        _generated[(current_user.id, _project_key(project_id))] = snap
        try:
            _save_snapshot(current_user.id, _project_key(project_id), snap)
        except OSError:
            import logging
            logging.getLogger("iez.cable").warning("Generated Cable Schedule kept in memory only (disk write failed)", exc_info=True)

    registry = register_safe(
        "success", project_id=project_id, module="cable_schedule", user=current_user.username,
        source_bytes=iodb_bytes, source_filename=iodb_file.filename or "IODB.xlsx",
        output_bytes=out_bytes, output_filename=filename, params=reg_params,
        template_bytes=template_bytes, template_filename=template_name,
    )

    return CableScheduleGenerateResponse(filename=filename, message="Cable Schedule generated successfully",
                                         registry=registry, output_mode=output_mode, sheets=planned,
                                         extra_sheets=extra_report.get("sheets") or None,
                                         extra_stats=extra_report.get("stats") or None,
                                         extra_warnings=extra_report.get("warnings") or None, cover=cover)


@router.get("/generated")
async def generated_cable_schedule(
    project_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Metadata of the Cable Schedule the Gland / Lug / Drum generators will use (no file content)."""
    return generated_meta(get_generated(current_user.id, project_id))


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
