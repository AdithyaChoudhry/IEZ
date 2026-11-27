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

from ..offload import off_main_loop
from ..deps import get_current_user
from ..auth.models import User
from ..services.document_registry import register_safe
from ..services import cable_cover
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
from utils import cable_header_meta as HM
from utils import cable_header_v3 as HV


router = APIRouter(prefix="/cable-schedule", tags=["Cable Schedule"])

cable_schedule_cache: dict = {}
cable_diagnostics: dict = {}          # user id -> the diagnostics of the last generation

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
            "selected_jbs": len(g["selected_jbs"]) if g["selected_jbs"] else None, "scope": g.get("scope")}


@router.post("/columns", response_model=ColumnsResponse)
@off_main_loop
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
@off_main_loop
async def preview_jb_summary(
    file: UploadFile = File(...),
    jb_column: str = Form(...),
    tag_column: str = Form(...),
    scope_filters: str = Form(""),
    current_user: User = Depends(get_current_user),
):
    """Junction boxes with ALL their tags (IODB order) - exactly the rows the Instrument Cable Schedule writes."""
    from utils.file_handler import read_iodb
    from utils.cable_schedule_layout import jb_groups
    file_bytes = trim_empty_tail(await file.read())
    df, err = read_iodb(io.BytesIO(file_bytes))
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    df = _scoped(df, scope_filters)
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


def _scope_selection(value: str) -> dict:
    """The request's AREA / AREA CODE / STATUS selection (JSON); {} = defaults (every area, deleted tags excluded)."""
    from utils.cable_scope import ScopeError, parse
    try:
        raw = json.loads(value) if (value or "").strip() else {}
        if not isinstance(raw, dict):
            raise ValueError
        parse(raw)
    except ScopeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filter selection.")
    return raw


def _scoped(df, scope_filters: str):
    """The eligible rows of an IODB table for the request's selection."""
    from utils.cable_scope import Scope, ScopeError
    selection = _scope_selection(scope_filters)
    try:
        return Scope(df, selection).apply(df)
    except ScopeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/scope")
@off_main_loop
async def engineering_scope(
    iodb_file: UploadFile = File(...),
    scope_filters: str = Form(""),
    current_user: User = Depends(get_current_user),
):
    """The AREA / AREA CODE / STATUS values of this IODB and the record counts of the current selection."""
    from utils.cable_scope import Scope, ScopeError, report
    selection = _scope_selection(scope_filters)
    df = _extra_frame(trim_empty_tail(await iodb_file.read()))
    try:
        chosen = Scope(df, selection)
        return {**chosen.options(), **report(chosen, df)}
    except ScopeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/diagnostics")
async def download_diagnostics(current_user: User = Depends(get_current_user)):
    """Scope, excluded records, shared cables and terminal trace of the user's last generation (not a deliverable)."""
    cached = cable_diagnostics.get(current_user.id)
    if not cached:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generate a Cable Schedule first.")
    from utils.cable_scope import diagnostics_workbook
    data = await run_in_threadpool(diagnostics_workbook, cached["info"])
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={cached['filename']}"})


@router.post("/extra/availability")
@off_main_loop
async def extra_sheet_availability(
    iodb_file: UploadFile = File(...),
    scope_filters: str = Form(""),
    current_user: User = Depends(get_current_user),
):
    """Which of MCC DI / MCC DO / VFD / MOV / LCP can be built from this IODB (counts, warnings, reasons)."""
    from utils.cable_schedule_extra import ExtraSheetError, availability
    df = _scoped(_extra_frame(trim_empty_tail(await iodb_file.read())), scope_filters)
    try:
        return availability(df)
    except ExtraSheetError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


async def _terminal_matcher(upload: Optional[UploadFile], options: str):
    """The optional I/O Assignment of this request. An invalid file is reported, never ignored."""
    if upload is None:
        return None
    from utils.io_terminals import AssignmentError, Matcher, read_assignment
    name = (upload.filename or "").lower()
    if not name.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload the I/O Assignment as an Excel .xlsx workbook.")
    try:
        chosen = json.loads(options) if options.strip() else {}
        if not isinstance(chosen, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid terminal source selection.")
    try:
        return Matcher(await run_in_threadpool(read_assignment, await upload.read()), chosen)
    except AssignmentError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/extra/preview")
@off_main_loop
async def extra_sheet_preview(
    iodb_file: UploadFile = File(...),
    extra_sheets: str = Form(...),
    io_assignment_file: Optional[UploadFile] = File(None),
    terminal_options: str = Form(""),
    scope_filters: str = Form(""),
    current_user: User = Depends(get_current_user),
):
    """Real preview of the selected extra sheets (rows come from the IODB, nothing is stored)."""
    from utils.cable_schedule_extra import ExtraSheetError, preview
    extras = _parse_extras(extra_sheets)
    terminals = await _terminal_matcher(io_assignment_file, terminal_options)
    df = _scoped(_extra_frame(trim_empty_tail(await iodb_file.read())), scope_filters)
    try:
        return preview(df, extras, terminals=terminals)
    except ExtraSheetError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _parse_overrides(text: str) -> dict:
    """The user's confirmed values for the header fields the cover could not supply: a JSON object {field: value}."""
    if not (text or "").strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid header details (not valid JSON).")
    if not isinstance(data, dict) or any(k not in HM.KEYS for k in data):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid header details: unknown field.")
    return {k: ("" if v is None else str(v)) for k, v in data.items()}


def _fingerprint(cover: "HM.CoverHeader", project_id: Optional[str]) -> str:
    """What the confirmed values belong to: this project's cover as it is right now. A different project or an edited cover changes it."""
    import hashlib
    return hashlib.sha256(f"{_project_key(project_id)}|{cover.fingerprint()}".encode()).hexdigest()[:24]


def _check_header_template() -> None:
    try:
        HV.load_template()
    except HV.TemplateError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _incomplete(res: "HM.Resolution", fingerprint: str) -> HTTPException:
    names = ", ".join(HM.LABELS[f.key] for f in res.unresolved)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                         detail={"code": "HEADER_METADATA_INCOMPLETE", "message": f"The Cable Schedule header needs: {names}. "
                                 "Enter the missing details (they are used for this Cable Schedule only) and generate again.",
                                 "header": {**res.public(), "fingerprint": fingerprint}})


@router.post("/header-metadata")
async def cable_header_metadata(
    project_id: Optional[str] = Form(None),
    cover_template_file: Optional[UploadFile] = File(None),
    header_overrides: str = Form(""),
    current_user: User = Depends(get_current_user),
):
    """
    The document header details of the Cable Schedule worksheets (PROJECT, CLIENT, DOCUMENT NO., PMC, DATE, LOCATION, REVISION), read from the linked
    Cover Sheet of this project. Each field is `ok` (verified from the cover) or missing / invalid / conflict - the page asks the user for exactly
    those. `complete` = true: generation needs no further input. Nothing is stored; `fingerprint` ties confirmed values to this cover.
    """
    _check_header_template()
    overrides = _parse_overrides(header_overrides)
    tpl = await cover_template_file.read() if cover_template_file is not None else None
    snap = await run_in_threadpool(cable_cover.snapshot, project_id, tpl or None)
    cover = HM.read_cover_header(snap["cover"])
    res = HM.resolve(cover, overrides)
    r = snap["resolution"]
    return {**res.public(), "fingerprint": _fingerprint(cover, project_id),
            "cover": {"available": snap["cover"] is not None, "status": r.get("status"), "message": snap["message"],
                      "document_number": (r.get("record") or {}).get("document_number"), "revision": r.get("revision"),
                      "revisions": cover.revisions}}


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
@off_main_loop
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
    header_overrides: str = Form(""),          # JSON {field: value}: only the header fields the cover could not supply, confirmed by the user
    header_fingerprint: str = Form(""),        # from /header-metadata: ties header_overrides to this project's cover as the user saw it
    io_assignment_file: Optional[UploadFile] = File(None),   # optional: terminal details for MCC / VFD / MOV / LCP
    terminal_options: str = Form(""),          # JSON {"equipment": "device"|"ts", "panel": "none"|"ts"}
    scope_filters: str = Form(""),             # JSON {"areas", "area_codes", "statuses"}; empty: all areas, deleted excluded
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

    # ── the document header: linked cover sheet (one snapshot for the whole request) -> resolved metadata; the user's confirmed values only for
    #    what the cover cannot supply. Unresolved metadata never produces a deliverable. ──
    _check_header_template()
    overrides = _parse_overrides(header_overrides)
    cover_tpl = await cover_template_file.read() if cover_template_file is not None else None
    cover_snap = await run_in_threadpool(cable_cover.snapshot, project_id, cover_tpl or None)
    cover_hdr = HM.read_cover_header(cover_snap["cover"])
    fingerprint = _fingerprint(cover_hdr, project_id)
    if any(v.strip() for v in overrides.values()):
        if not header_fingerprint:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="header_fingerprint is required with header_overrides.")
        if header_fingerprint != fingerprint:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="The project or its cover sheet changed since the header details were confirmed. "
                                       "Check the header details again.")
    resolution = HM.resolve(cover_hdr, overrides)
    if not resolution.complete:
        raise _incomplete(resolution, fingerprint)

    extra_report: dict = {}
    terminals = await _terminal_matcher(io_assignment_file, terminal_options)
    selection = _scope_selection(scope_filters)
    scoped: dict = {}
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
        header_meta=resolution.values,
        terminals=terminals,
        scope=selection,
        scope_report=scoped,
    )

    reg_params = {"jb_column": jb_column, "tag_column": tag_column, "output_mode": output_mode, "scope": selection}
    if jbs:
        reg_params["selected_jbs"] = jbs
    if extras:
        reg_params["extra_sheets"] = extras
        reg_params["include_schedule"] = include_schedule
    if terminals is not None and not extras:
        extra_report["warnings"] = list(extra_report.get("warnings") or []) + [
            "I/O Assignment: terminal details apply only to the MCC DI, MCC DO, VFD, MOV and LCP sheets; none was selected."]
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
    out_bytes, filename, cover = await run_in_threadpool(finalize, current_user.id, "cable_schedule", project_id, out_bytes,
                                                         filename, custom_template=cover_tpl, snapshot=cover_snap)
    if cover.get("cover_sheet") and cover["cover_sheet"] not in planned:
        planned = [cover["cover_sheet"]] + planned
    if cover.get("applied") and extra_report.get("warnings"):          # the project cover replaced the template's cover: the header follows it
        extra_report["warnings"] = [w for w in extra_report["warnings"] if not str(w).startswith("COVERSHEET:")]
    scope_info, snapshot_iodb = None, iodb_bytes
    if scoped:
        from utils.cable_scope import excluded_rows, report, row_scope, scoped_iodb
        chosen, full = scoped["scope"], scoped["full"]
        scope_info = report(chosen, full)
        suffix = chosen.file_suffix()
        if suffix:                                    # area / historical downloads stay apart; the document number is the cover's
            stem, dot, ext = filename.rpartition(".")
            filename = f"{stem}_{suffix}{dot}{ext}" if dot else f"{filename}_{suffix}"
        if chosen.active:                             # Gland / Lug / Drum / JB generators then work on the same records
            snapshot_iodb = await run_in_threadpool(scoped_iodb, scoped["eligible"])
        where = row_scope(chosen, full)
        trace = []
        for t in (terminals.trace if terminals is not None else []):
            area, code, state = where.get(t["iodb_row"], ("", "", ""))
            trace.append([t["tag"], t["iodb_row"], area, code, state, t["sheet"], t["field"], t["endpoint"], "IO_ASSIGNMENT",
                          t["source_row"], t["source_column"], t["value"], t["result"]])
        cable_diagnostics[current_user.id] = {
            "filename": filename.rsplit(".", 1)[0] + "_Diagnostics.xlsx",
            "info": {**scope_info, "excluded": excluded_rows(chosen, full), "trace": trace,
                     "notes": scope_info["notes"] + list((extra_report.get("terminals") or {}).get("warnings") or [])}}
        extra_report["warnings"] = list(extra_report.get("warnings") or []) + scope_info["notes"]
    cache_key = f"{current_user.id}_cable_schedule"
    cable_schedule_cache[cache_key] = {"bytes": out_bytes, "filename": filename}
    snap = {"id": uuid.uuid4().hex, "bytes": out_bytes, "filename": filename, "project_id": _project_key(project_id),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "sheets": planned,
            "iodb_bytes": snapshot_iodb, "iodb_filename": iodb_file.filename or "IODB.xlsx", "selected_jbs": jbs,
            "scope": (scope_info or {}).get("selection")}
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
                                         extra_warnings=extra_report.get("warnings") or None, cover=cover,
                                         terminals=extra_report.get("terminals"),
                                         scope=scope_info,
                                         header={"values": resolution.values, "sources": {f.key: f.source for f in resolution.fields},
                                                 "sheets": extra_report.get("header") or {}, "fingerprint": fingerprint})


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
