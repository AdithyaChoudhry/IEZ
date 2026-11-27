"""
Configurable IODB validation rules.

  GET    /validator/rules-catalogue           built-in rules, condition operators, protected checks, whether you may edit
  GET    /validator/profiles?project_id=      the project's custom profiles
  POST   /validator/profiles                  create (or duplicate) a profile              Lead Engineer / Reviewer / Admin
  PUT    /validator/profiles/{id}             save a new version                           Lead Engineer / Reviewer / Admin
  DELETE /validator/profiles/{id}             remove from use (history is kept)            Lead Engineer / Reviewer / Admin
  GET    /validator/profiles/{id}/history     every saved version
  POST   /validator/preview-rule              one rule against one sample record, nothing saved
"""
import io
import json
import sys
from datetime import datetime
from typing import Optional

import openpyxl
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth.models import User
from ..deps import get_current_user, get_db, require_lead
from ..models.validation_profile import ValidationProfile, ValidationProfileVersion
from ..services import document_registry as reg

sys.path.insert(0, '/app')
from utils import validation_profiles as VP  # noqa: E402
from utils.generators import generate_iodb_validation  # noqa: E402

router = APIRouter(prefix="/validator", tags=["IODB Validation Rules"])


class ProfileBody(BaseModel):
    name: str
    project_id: str = ""
    config: dict = {}
    expected_version: Optional[int] = None


class PreviewBody(BaseModel):
    rule_id: str
    config: dict = {}
    record: dict = {}


def _bad(msg: str, code: int = status.HTTP_400_BAD_REQUEST):
    raise HTTPException(status_code=code, detail=msg)


def _project(project_id: Optional[str]) -> str:
    if not (project_id or "").strip():
        _bad("Select a project first: a custom rule profile belongs to one project.")
    try:
        return reg.normalize_project_id(project_id)
    except reg.RegistryError as exc:
        _bad(str(exc))


def _name(db: Session, project_id: str, name: str, own_id: Optional[int] = None) -> str:
    name = " ".join((name or "").split())
    if not name or len(name) > 100:
        _bad("Enter a profile name (up to 100 characters).")
    taken = [p for p in db.query(ValidationProfile).filter_by(project_id=project_id, is_deleted=False)
             if p.name.lower() == name.lower() and p.id != own_id]
    if taken or name.lower() == VP.DEFAULT_PROFILE_NAME.lower():
        _bad(f"The profile name '{name}' is already used. Choose another name.", status.HTTP_409_CONFLICT)
    return name


def _config(raw: dict) -> dict:
    try:
        return VP.clean_config(raw)
    except VP.ProfileError as exc:
        _bad(str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)


def _public(p: ValidationProfile) -> dict:
    return {"id": p.id, "project_id": p.project_id, "name": p.name, "version": p.version, "config": json.loads(p.config_json),
            "updated_by": p.updated_by, "updated_at": p.updated_at.isoformat() if p.updated_at else None}


def _get(db: Session, profile_id: int) -> ValidationProfile:
    p = db.get(ValidationProfile, profile_id)
    if p is None or p.is_deleted:
        _bad("This rule profile is no longer available. Select another profile.", status.HTTP_404_NOT_FOUND)
    return p


def resolve_profile(db: Session, profile_id: Optional[int], project_id: Optional[str]) -> VP.Profile:
    """The profile a validation run asked for. Never falls back to another one."""
    if not profile_id:
        return VP.Profile()
    p = _get(db, profile_id)
    if p.project_id != _project(project_id):
        _bad(f"The rule profile '{p.name}' belongs to project {p.project_id}. Select a profile of the current project.",
             status.HTTP_409_CONFLICT)
    try:
        return VP.Profile(json.loads(p.config_json), p.name, p.version, custom=True)
    except (ValueError, VP.ProfileError) as exc:
        _bad(f"The saved rule profile '{p.name}' is not valid: {exc}", status.HTTP_422_UNPROCESSABLE_ENTITY)


def _snapshot(db: Session, p: ValidationProfile, who: str) -> None:
    db.add(ValidationProfileVersion(profile_id=p.id, version=p.version, name=p.name, config_json=p.config_json, saved_by=who))


@router.get("/rules-catalogue")
def catalogue(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        require_lead(user, db)
        can_edit = True
    except HTTPException:
        can_edit = False
    return {"default_name": VP.DEFAULT_PROFILE_NAME, "rules": VP.RULES, "severities": list(VP.SEVERITIES),
            "operators": [{"key": k, "label": v[0], "needs_value": v[1]} for k, v in VP.OPERATORS.items()],
            "protected": VP.PROTECTED_CHECKS, "can_edit": can_edit}


def _headings(data: bytes) -> list[str]:
    df = pd.read_excel(io.BytesIO(data), sheet_name=0, header=0, nrows=0)
    return [str(c).strip() for c in df.columns if not str(c).startswith("Unnamed")]


@router.post("/columns")
async def columns(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """Column headings of the IODB (the sheet the validator reads), offered in the condition builder."""
    data = await file.read()
    try:
        return {"columns": await run_in_threadpool(_headings, data)}
    except Exception:
        _bad("The column headings of this file could not be read.")


@router.get("/profiles")
def list_profiles(project_id: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not project_id.strip():
        return []
    rows = db.query(ValidationProfile).filter_by(project_id=_project(project_id), is_deleted=False).order_by(ValidationProfile.name)
    return [_public(p) for p in rows]


@router.post("/profiles", status_code=status.HTTP_201_CREATED)
def create_profile(body: ProfileBody, user: User = Depends(require_lead), db: Session = Depends(get_db)):
    pid = _project(body.project_id)
    p = ValidationProfile(project_id=pid, name=_name(db, pid, body.name), version=1,
                          config_json=json.dumps(_config(body.config)), created_by=user.username, updated_by=user.username)
    db.add(p)
    db.flush()
    _snapshot(db, p, user.username)
    db.commit()
    return _public(p)


@router.put("/profiles/{profile_id}")
def save_profile(profile_id: int, body: ProfileBody, user: User = Depends(require_lead), db: Session = Depends(get_db)):
    p = _get(db, profile_id)
    if p.project_id != _project(body.project_id):
        _bad("This profile belongs to another project.", status.HTTP_409_CONFLICT)
    if body.expected_version is not None and body.expected_version != p.version:
        _bad(f"The profile was changed by {p.updated_by} (version {p.version}). Reload it before saving.", status.HTTP_409_CONFLICT)
    p.name = _name(db, p.project_id, body.name, p.id)
    p.config_json = json.dumps(_config(body.config))
    p.version += 1
    p.updated_by, p.updated_at = user.username, datetime.utcnow()
    _snapshot(db, p, user.username)
    db.commit()
    return _public(p)


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: int, project_id: str = "", user: User = Depends(require_lead), db: Session = Depends(get_db)):
    p = _get(db, profile_id)
    if p.project_id != _project(project_id):
        _bad("This profile belongs to another project.", status.HTTP_409_CONFLICT)
    p.is_deleted, p.updated_by, p.updated_at = True, user.username, datetime.utcnow()
    db.commit()


@router.get("/profiles/{profile_id}/history")
def history(profile_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(ValidationProfileVersion).filter_by(profile_id=profile_id).order_by(ValidationProfileVersion.version.desc())
    return [{"version": v.version, "name": v.name, "saved_by": v.saved_by, "saved_at": v.saved_at.isoformat(),
             "config": json.loads(v.config_json)} for v in rows]


@router.post("/preview-rule")
def preview_rule(body: PreviewBody, user: User = Depends(get_current_user)):
    """Run the one rule on the one sample record with the unsaved settings. Not a validation of any IODB."""
    rule = VP.BY_ID.get(body.rule_id)
    if rule is None:
        _bad("Unknown validation rule.")
    own = (body.config or {}).get("rules", {}).get(body.rule_id, {})
    config = {"rules": {r["id"]: ({**own} if r["id"] == body.rule_id else {"enabled": False}) for r in VP.RULES}}
    record = {str(k).strip(): ("" if v is None else str(v))[:500] for k, v in list(body.record.items())[:60] if str(k).strip()}
    if not record:
        _bad("Enter at least one field and value of the sample record.")
    try:
        profile = VP.Profile(_config(config), "preview", custom=True)
        df = pd.DataFrame([{k: (v if v != "" else float("nan")) for k, v in record.items()}], dtype=object)
        *_, errors, problem = generate_iodb_validation(df, openpyxl.Workbook(), auto_correct_spelling=body.rule_id == "12",
                                                       validate_empty_cells=body.rule_id == "1", profile=profile)
    except VP.ProfileError as exc:
        _bad(str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
    if problem:
        _bad(problem.split("\n")[0], status.HTTP_422_UNPROCESSABLE_ENTITY)
    findings = [{"severity": e["severity"], "message": e["message"], "column": e["column"]} for e in errors]
    upper = {k.upper(): v for k, v in record.items()}
    if findings:
        result = findings[0]["severity"].upper()
    elif not profile.enabled(body.rule_id):
        result = "DISABLED"
    elif not profile.applies(body.rule_id, upper) or (
            body.rule_id == "6" and any(upper.get(c, "").strip().upper() in {x.upper() for x in profile.param("6", "exempt_io")}
                                        for c in ("SIGNAL I/O TYPE", "SIGNAL TYPE", "I/O TYPE", "IO TYPE", "SIGNAL IO TYPE") if c in upper)):
        result = "NOT APPLICABLE"
    else:
        result = "NO FINDING"
    return {"rule": rule["name"], "result": result, "findings": findings,
            "note": "Preview of one sample record. A rule also reports nothing when the record lacks the columns it reads."}
