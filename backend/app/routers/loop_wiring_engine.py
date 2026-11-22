"""
Loop Wiring Generator - engine API (replaces the previous Loop Wiring flows behind the same page).

    I/O Assignment -> validate (group by LOOP_NAME, calculate typical, select 1 of 42 templates, map FIELD CODES, trace)
                   -> loop selection preview -> per-loop 7-step preview -> GENERATE LOOP WIRING -> LOOP_WIRING_GENERATED.xlsx

The two master workbooks are the authority and are read-only assets:
    backend/app/templates/loop_wiring/STANDARD_IO_ASSIGNMENT_TEMPLATE_Final.xlsx
    backend/app/templates/loop_wiring/LOOP_TYPICAL_TEMPLATES_FINAL_CORRECTED.xlsx
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from ..auth.models import User
from ..deps import get_current_user
from ..services.document_registry import register_safe
from .loop_wiring import loop_wiring_cache

import sys
sys.path.insert(0, '/app')
from utils.loop_engine import analysis as A, fixture as FX, generate as GEN, registry as REG, source as SRC

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/loop-wiring/engine", tags=["Loop Wiring"])

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "loop_wiring"
TEMPLATES_FILE = "LOOP_TYPICAL_TEMPLATES_FINAL_CORRECTED.xlsx"
IO_MASTER_FILE = "STANDARD_IO_ASSIGNMENT_TEMPLATE_Final.xlsx"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_BYTES = 60 * 1024 * 1024
SESSION_TTL, MAX_SESSIONS_PER_USER = 7200, 6

_lock = threading.Lock()
_assets: dict = {}
_sessions: dict[str, dict] = {}
_jobs: dict[str, dict] = {}
_outputs: dict[str, dict] = {}          # user id -> {"workbook": bytes, "report": bytes, "filename": str}
_selftest: dict = {}


def _load_assets() -> dict:
    with _lock:
        if not _assets:
            tpl = (TEMPLATE_DIR / TEMPLATES_FILE).read_bytes()
            io_master = (TEMPLATE_DIR / IO_MASTER_FILE).read_bytes()
            reg = REG.build_registry(tpl, io_master)
            _assets.update(tpl=tpl, io=io_master, reg=reg, matrix=A.read_matrix(io_master))
        return _assets


def _gc() -> None:
    now = time.time()
    for k in [k for k, v in _sessions.items() if now - v["ts"] > SESSION_TTL]:
        _sessions.pop(k, None)
    for k in [k for k, v in _jobs.items() if now - v.get("ts", now) > SESSION_TTL]:
        _jobs.pop(k, None)


def _session(analysis_id: str, user: User) -> dict:
    s = _sessions.get(analysis_id)
    if not s or s["user"] != user.id:
        raise HTTPException(status_code=404, detail="This validation is no longer available - upload and validate the I/O Assignment again.")
    return s


# ---------------------------------------------------------------------------------------------------------------------
@router.get("/library")
def library(current_user: User = Depends(get_current_user)):
    a = _load_assets()
    reg = a["reg"]
    return {"complete": reg.complete, "count": len(reg.templates), "expected": len(reg.loop_types) * 6, "missing": reg.missing, "problems": reg.problems,
            "error": REG.library_error(reg), "loop_types": [{"name": n, "no": k} for n, k in reg.loop_types], "templates": reg.table(),
            "fields": [{"field": f.field, "column": f.column, "description": f.description, "required": f.required} for f in reg.data_fields],
            "masters": {"io_assignment": IO_MASTER_FILE, "templates": TEMPLATES_FILE}}


@router.get("/master/{which}")
def master(which: str, current_user: User = Depends(get_current_user)):
    name = {"io": IO_MASTER_FILE, "templates": TEMPLATES_FILE}.get(which)
    if not name:
        raise HTTPException(status_code=404, detail="Unknown master")
    return Response(content=(TEMPLATE_DIR / name).read_bytes(), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/validate")
def validate(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    data = file.file.read()
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="The I/O Assignment file is empty or too large.")
    a = _load_assets()
    try:
        known = {r[0] for r in [(f.field,) for f in a["reg"].data_fields]}
        src = SRC.read_assignment(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read the I/O Assignment: {e}")
    an = A.analyze(src, a["reg"], a["matrix"])
    with _lock:
        _gc()
        mine = sorted([k for k, v in _sessions.items() if v["user"] == current_user.id], key=lambda k: _sessions[k]["ts"])
        for k in mine[:max(0, len(mine) - MAX_SESSIONS_PER_USER + 1)]:
            _sessions.pop(k, None)
        aid = str(uuid.uuid4())
        _sessions[aid] = {"user": current_user.id, "ts": time.time(), "analysis": an, "name": file.filename or "IO_Assignment.xlsx", "bytes": data}
    return {"analysis_id": aid, "filename": file.filename, "sheet": src.sheet, "header_row": src.header_row, "rows": len(src.rows), "spares": len(src.spare_rows),
            "warnings": src.warnings, "counts": an.counts(), "loops": [l.summary() for l in an.loops], "global_issues": [i.to_dict() for i in an.global_issues],
            "library_ok": a["reg"].complete}


@router.get("/analysis/{analysis_id}/loop/{loop_name:path}")
def loop_detail(analysis_id: str, loop_name: str, current_user: User = Depends(get_current_user)):
    s = _session(analysis_id, current_user)
    an: A.Analysis = s["analysis"]
    L = next((l for l in an.loops if l.name == loop_name), None)
    if L is None:
        raise HTTPException(status_code=404, detail="Loop not found")
    reg = an.registry
    tpl = reg.templates.get(L.typical)
    rows = {r.row: r for r in an.source.rows}
    src_keys = ["TAG", "SIG_DESC", "IO_TYPE", "ISNIS", "WIRE", "LOOP_TYPE", "SPD_ARR", "TERM_ARR", "TYPICAL", "STATUS", "JB_TAG", "MARSH_CAB", "SYS_CAB", "MODULE_TAG", "CHANNEL"]
    no = dict(reg.loop_types).get(L.loop_type)
    return {
        "loop": L.summary(), "issues": [i.to_dict() for i in L.issues],
        "step1": [{"row": r, "values": rows[r].values, "key": {k: rows[r].values.get(k) for k in src_keys}} for r in L.rows if r in rows],
        "step2": {"loop_type": L.loop_type, "loop_type_no": no, "spd": L.spd, "term": L.term, "calculated": L.typical, "manual": L.manual_typical,
                  "template": L.template, "formula": f"{no}{L.spd}-{L.term}" if no else "", "spd_name": REG.SPD_NAMES.get(L.spd, ""), "term_name": REG.TERM_NAMES.get(L.term, ""),
                  "slots": [{"sig": x.sig, "row": x.row, "io_type": x.io_type, "description": x.description} for x in tpl.slots] if tpl else [], "empty_slots": L.empty_slots},
        "step3": [{"sig": x.sig, "tag": x.tag, "source_row": x.source_row, "mapping": x.mapping} for x in L.signals],
        "step4": {"loop_fields": L.loop_fields, "columns": [f.field for f in reg.data_fields], "rows": [{"sig": x.sig, "row": x.slot_row, "values": x.data_block, "status": x.status} for x in L.signals]},
        "step5": [{"sig": x.sig, "tag": x.tag, "io_type": x.io_type, "nodes": [n for n in x.trace.get("nodes", []) + x.trace.get("power", []) if n["side"] == "field"]} for x in L.signals],
        "step6": [{"sig": x.sig, "tag": x.tag, "io_type": x.io_type, "nodes": [n for n in x.trace.get("nodes", []) if n["side"] == "control"]} for x in L.signals],
        "step7": [{"sig": x.sig, "tag": x.tag, "status": x.status, "topology": x.trace.get("topology"), "complete": x.trace.get("complete"), "broken": x.trace.get("broken"),
                   "conductors": x.trace.get("conductors")} for x in L.signals],
        "report": L.report,
    }


class GenerateIn(BaseModel):
    analysis_id: str
    loops: Optional[list[str]] = None
    project_id: Optional[str] = None


def _run(job_id: str, analysis_id: str, names: Optional[list[str]], user: User, project_id: Optional[str]) -> None:
    try:
        s = _sessions[analysis_id]
        an: A.Analysis = s["analysis"]
        data, stats = GEN.generate_workbook(an, names, s["name"])
        report = GEN.build_report(an, set(stats["sheet_names"]), s["name"])
        from .deliverables import finalize          # centralised cover sheet first; Excel and PDF serve this same workbook
        data, fname, cover = finalize(user.id, "loop_wiring", project_id, data, "LOOP_WIRING_GENERATED.xlsx")
        _outputs[str(user.id)] = {"workbook": data, "report": report, "filename": fname}
        loop_wiring_cache[f"{user.id}_loop_wiring"] = {"bytes": data, "filename": fname}
        registry = register_safe("success", project_id=project_id, module="loop_wiring", user=user.username, source_bytes=s["bytes"], source_filename=s["name"],
                                 output_bytes=data, output_filename=fname, sheet_count=stats["sheets"],
                                 template_bytes=an.registry.template_bytes, template_filename=TEMPLATES_FILE)
        _jobs[job_id].update(status="done", ts=time.time(), result={
            "filename": fname, "cover": cover, "sheet_count": stats["sheets"], "skipped": stats["skipped"], "sheet_names": stats["sheet_names"], "registry": registry,
            "message": f"Loop Wiring generated: {stats['sheets']} loop sheet(s)" + (f"; {len(stats['skipped'])} loop(s) with ERROR not generated" if stats["skipped"] else "")})
    except Exception as e:                                           # noqa: BLE001
        logger.exception("loop wiring generation failed")
        _jobs[job_id].update(status="error", ts=time.time(), error=str(e) if isinstance(e, ValueError) else f"Loop Wiring generation failed: {e}")


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
def generate(body: GenerateIn, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    _session(body.analysis_id, current_user)
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "processing", "ts": time.time(), "user": current_user.id}
    background_tasks.add_task(_run, job_id, body.analysis_id, body.loops, current_user, body.project_id)
    return {"job_id": job_id, "status": "processing"}


@router.get("/job/{job_id}")
def job(job_id: str, current_user: User = Depends(get_current_user)):
    j = _jobs.get(job_id)
    if not j or j.get("user") != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return {k: v for k, v in j.items() if k not in ("user", "ts")}


def _output(user: User) -> dict:
    o = _outputs.get(str(user.id))
    if not o:
        raise HTTPException(status_code=404, detail="Nothing generated yet - run GENERATE LOOP WIRING first.")
    return o


@router.get("/download")
def download(current_user: User = Depends(get_current_user)):
    o = _output(current_user)
    return Response(content=o["workbook"], media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{o["filename"]}"'})


@router.get("/report")
def report(current_user: User = Depends(get_current_user)):
    o = _output(current_user)
    return Response(content=o["report"], media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="LOOP_WIRING_GENERATION_REPORT.xlsx"'})


@router.get("/selftest")
def selftest(current_user: User = Depends(get_current_user)):
    a = _load_assets()
    with _lock:
        if not _selftest:
            _selftest.update(FX.run_acceptance(a["tpl"], a["io"]))
    return _selftest


@router.get("/fixture")
def fixture(current_user: User = Depends(get_current_user)):
    a = _load_assets()
    rows = FX.make_fixture(a["tpl"], a["io"])
    return Response(content=FX.fixture_workbook(rows, a["io"]), media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="LOOP_WIRING_TEST_FIXTURE_IO_ASSIGNMENT.xlsx"'})
