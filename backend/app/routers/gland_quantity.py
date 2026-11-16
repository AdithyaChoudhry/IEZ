"""
Cable Gland Quantity Generator (sub-module of the Cable Schedule Generator).

  /analyze  - gland quantities + OD advisory for an uploaded cable schedule
  /advise   - manual cable OD -> gland advice
  /reference - the reference database (built-in published tables + standards), vendor table check and template
Stateless apart from a per-user "last report" cache for the download. The uploaded schedule is only read.
"""
import io
import json
import logging
import threading
import time
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from ..auth.models import User
from ..deps import get_current_user

import sys
sys.path.insert(0, '/app')
from utils import gland_advisor as adv  # noqa: E402
from utils import gland_quantity as gq  # noqa: E402
from utils import gland_reference as ref  # noqa: E402
from utils import gland_service as svc  # noqa: E402
from utils import cable_complete as cc  # noqa: E402

router = APIRouter(prefix="/cable-schedule/gland", tags=["Cable Gland Quantity"])
gland_cache: dict = {}
_jobs: dict = {}
_lock = threading.Lock()
_TTL = 3600
logger = logging.getLogger("iez.gland")
MAX_BYTES = 25 * 1024 * 1024


def _bad(msg: str, code: int = status.HTTP_400_BAD_REQUEST):
    raise HTTPException(status_code=code, detail=msg)


async def _read(upload: UploadFile, what: str) -> bytes:
    data = await upload.read()
    if not data:
        _bad(f"The {what} file is empty.")
    if len(data) > MAX_BYTES:
        _bad(f"The {what} file is larger than 25 MB.")
    if not (upload.filename or "").lower().endswith((".xlsx", ".xlsm")):
        _bad(f"The {what} must be an Excel .xlsx file.")
    return data


def _json(text: Optional[str], what: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        _bad(f"The {what} are not valid JSON.")


async def _extra_rows(upload: Optional[UploadFile]):
    if upload is None:
        return None, []
    try:
        rows, problems = ref.read_vendor_table(await _read(upload, "gland reference table"), tier="VENDOR")
    except ValueError as e:
        _bad(str(e))
    return rows, problems


def _public(p: dict) -> dict:
    return {k: v for k, v in p.items() if not k.startswith("_")}


@router.post("/detect")
async def detect(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Cable schedule sheets found in the workbook and the cable types (for the OD table)."""
    data = await _read(file, "cable schedule")
    try:
        occ, exc, infos, types = gq.extract(data, gq.Settings())
    except gq.GlandError as e:
        _bad(str(e))
    return {"sheets": infos, "default_sheets": gq.default_sheets(infos), "cable_types": types, "occurrences": len(occ),
            "exceptions": len(exc)}


@router.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    settings: Optional[str] = Form(None),
    cable_data: Optional[str] = Form(None),
    project: Optional[str] = Form(None),
    reference_file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
):
    data = await _read(file, "cable schedule")
    extra, problems = await _extra_rows(reference_file)
    try:
        p = svc.analyze(data, _json(settings, "settings"), _json(cable_data, "cable OD data"), _json(project, "project settings"), extra, problems)
        xlsx = svc.to_workbook(p, file.filename or "uploaded cable schedule")
    except (gq.GlandError, adv.AdviceError) as e:
        _bad(str(e))
    gland_cache[f"{current_user.id}_gland"] = {"bytes": xlsx, "filename": "Gland_Quantity_Report.xlsx"}
    out = _public(p)
    out["filename"] = "Gland_Quantity_Report.xlsx"
    return out


def _job_run(job_id: str, user_key: str, iodb, template, reuse: bool, name: str, settings, cable_data, project, extra, problems):
    def stage(text):
        with _lock:
            _jobs[job_id]["stage"] = text
    try:
        if reuse and user_key in cc.SCHEDULE_CACHE:
            data, info, name = cc.SCHEDULE_CACHE[user_key]["bytes"], cc.SCHEDULE_CACHE[user_key]["info"], cc.SCHEDULE_CACHE[user_key]["name"]
        else:
            stage("Generating the Cable Schedule from the IODB (existing Cable Schedule generator)")
            data, info = cc.schedule_from_iodb(iodb, template)
            cc.SCHEDULE_CACHE[user_key] = {"bytes": data, "info": info, "name": name}
        stage("Extracting glands from the generated Cable Schedule")
        p = svc.analyze(data, settings, cable_data, project, extra, problems)
        xlsx = svc.to_workbook(p, f"Cable Schedule generated from {name}")
        gland_cache[user_key] = {"bytes": xlsx, "filename": "Gland_Quantity_Report.xlsx"}
        out = _public(p)
        out["filename"] = "Gland_Quantity_Report.xlsx"
        out["source"] = {"type": "IODB", "name": name, **info}
        with _lock:
            _jobs[job_id].update(status="done", stage="Done", result=out)
    except (gq.GlandError, adv.AdviceError, cc.CompleteError) as e:
        with _lock:
            _jobs[job_id].update(status="error", error=str(e))
    except Exception as e:                                          # never leave the page waiting
        logger.exception("Gland job %s failed", job_id[:8])
        with _lock:
            _jobs[job_id].update(status="error", error=f"The gland quantities could not be generated: {e}")


@router.post("/iodb/start", status_code=status.HTTP_202_ACCEPTED)
async def iodb_start(
    background_tasks: BackgroundTasks,
    iodb_file: Optional[UploadFile] = File(None),
    template_file: Optional[UploadFile] = File(None),
    reuse: bool = Form(False),
    settings: Optional[str] = Form(None),
    cable_data: Optional[str] = Form(None),
    project: Optional[str] = Form(None),
    reference_file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
):
    """Gland quantities straight from an IODB: the Cable Schedule is generated first (existing generator), then the gland engine reads it. Poll /iodb/job/{id}."""
    key = f"{current_user.id}_gland"
    if iodb_file is None and not (reuse and key in cc.SCHEDULE_CACHE):
        _bad("Upload an IODB.")
    iodb = await _read(iodb_file, "IODB") if iodb_file is not None else None
    template = await _read(template_file, "Cable Schedule template") if template_file is not None else None
    if iodb is not None and template is None and cc.builtin_template() is None:
        _bad("No Cable Schedule template is installed on the server. Upload the project's Cable Schedule template.")
    extra, problems = await _extra_rows(reference_file)
    parsed = (_json(settings, "settings"), _json(cable_data, "cable OD data"), _json(project, "project settings"))
    job_id = uuid.uuid4().hex
    now = time.time()
    with _lock:
        for k in [k for k, v in _jobs.items() if now - v.get("created", now) > _TTL]:
            _jobs.pop(k, None)
        _jobs[job_id] = {"status": "processing", "created": now, "stage": "Queued", "user": current_user.username}
    background_tasks.add_task(_job_run, job_id, key, iodb, template, reuse and iodb is None, (iodb_file.filename if iodb_file else "IODB") or "IODB", *parsed, extra, problems)
    return {"job_id": job_id, "status": "processing"}


@router.get("/iodb/job/{job_id}")
async def iodb_job(job_id: str, current_user: User = Depends(get_current_user)):
    with _lock:
        j = dict(_jobs.get(job_id) or {})
    if not j or j.get("user") != current_user.username:
        _bad("This job was not found. Please generate again.", status.HTTP_404_NOT_FOUND)
    out = {"status": j["status"], "stage": j.get("stage", ""), "elapsed": round(time.time() - j["created"], 1)}
    if j["status"] == "done":
        out["result"] = j["result"]
    if j["status"] == "error":
        out["error"] = j.get("error", "Generation failed.")
    return out


@router.post("/advise")
async def advise(
    inputs: str = Form(...),
    project: Optional[str] = Form(None),
    reference_file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
):
    form = _json(inputs, "inputs") or {}
    extra, problems = await _extra_rows(reference_file)
    try:
        out = svc.advise_payload(form, _json(project, "project settings"), extra)
    except adv.AdviceError as e:
        _bad(str(e))
    out["reference_problems"] = problems
    return out


@router.get("/reference")
async def reference(current_user: User = Depends(get_current_user)):
    rows = ref.builtin()
    return {"standards": ref.STANDARDS, "principles": ref.PRINCIPLES, "disclaimer": adv.NOT_FINAL, "rule": adv.RULE_OD_VS_THREAD,
            "rows": [r.to_dict() for r in rows], "priority": "Project specification > approved vendor/project gland database > generic engineering reference",
            "limits": ["Basis: manufacturers' published selection tables (CMP Products A2F / T3CDS and Hawke 501/453 UNIVERSAL), not an industry standard - no standard publishes cable-OD-to-gland-size ranges.",
                       "Metric and NPT entry threads are as printed in the manufacturer tables. ET (Imperial Electrical Thread) and BSP options of the CMP rows come from CMP's HOW TO ORDER thread-size code table through the NPT codes - they are not printed per gland size and are flagged 'derived - confirm availability'. The Hawke sheet lists no ET or BSP.",
                       "IP rating, Ex certification, material and temperature are present only for the Hawke rows (as printed on its datasheet); CMP rows carry none, so those checks stay 'verify with the manufacturer'. The certificate scope must always be verified.",
                       "Live retrieval from the internet is not performed; the tables were read from the manufacturer's page on " + ref.RETRIEVED + "."],
            "template_headers": ref.TEMPLATE_HEADERS}


@router.post("/reference/check")
async def reference_check(reference_file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    rows, problems = await _extra_rows(reference_file)
    return {"rows": len(rows), "problems": problems, "preview": [r.to_dict() for r in rows[:50]],
            "standards_offered": sorted({s for s in ("METRIC", "NPT", "BSP", "ET") if any(r.threads(s) for r in rows)})}


@router.get("/reference/template")
async def reference_template(current_user: User = Depends(get_current_user)):
    return StreamingResponse(io.BytesIO(ref.template_workbook()),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=Gland_Reference_Table_Template.xlsx"})


@router.get("/download")
async def download(current_user: User = Depends(get_current_user)):
    cached = gland_cache.get(f"{current_user.id}_gland")
    if not cached:
        _bad("No gland report found. Please generate it first.", status.HTTP_404_NOT_FOUND)
    return StreamingResponse(io.BytesIO(cached["bytes"]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={cached['filename']}"})
