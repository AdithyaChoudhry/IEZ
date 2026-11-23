"""
Deliverable cover sheets: the Cover Sheet Generator is the single source of the cover sheet of the Instrument List,
I/O List, Cable Schedule, Loop Wiring and Datasheet deliverables.

    project MDL  --keyword match / engineer's pick-->  MDL record (document number + title: the MDL is the authority)
    Cover Sheet Generator  --entered once per document-->  DeliverableCover (client, PMC, revisions, signatories ...)
    Approval Queue (request_type "coversheet")  -->  approved / pending: an unapproved cover is a DRAFT
    generator output  -->  cover sheet built with the existing cover sheet engine and put first in the workbook

Nothing is invented: without a resolved MDL record or entered cover details there is no cover (the generator says what
is missing); a draft never shows Checked / Approved names.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..auth.models import ApprovalRequest
from ..models.deliverable_cover import DeliverableCover
from . import mdl_service

DOC_TYPES: dict[str, dict] = {
    "instrument_list": {"label": "Instrument List", "keywords": ["INSTRUMENT LIST", "INSTRUMENT INDEX"]},
    "io_list": {"label": "I/O List", "keywords": ["I/O LIST", "IO LIST", "I-O LIST", "INPUT OUTPUT LIST", "INPUT/OUTPUT LIST"]},
    "cable_schedule": {"label": "Cable Schedule", "keywords": ["CABLE SCHEDULE"]},
    "loop_wiring": {"label": "Loop Wiring", "keywords": ["LOOP WIRING", "LOOP DIAGRAM", "LOOP DRAWING"]},
    "datasheet": {"label": "Datasheet", "keywords": ["DATASHEET", "DATA SHEET"]},
    "gland_quantity": {"label": "Cable Gland Quantity", "keywords": ["GLAND QUANTITY", "CABLE GLAND", "GLAND SCHEDULE"]},
    "lug_quantity": {"label": "Cable Lug Quantity", "keywords": ["LUG QUANTITY", "CABLE LUG", "LUG SCHEDULE"]},
}
PROJECT_FIELDS = ("project_description", "client", "pmc", "contractor", "unit_no", "doc_class", "discipline", "page_no")
DRAFT_TEXT = "DRAFT - NOT APPROVED FOR SUBMISSION"
_STOP = {"TYPE", "R0", "THE", "AND", "OF", "FOR", "WITH"}


class CoverError(Exception):
    """User-facing problem."""


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-]+", " ", re.sub(r"[^A-Z0-9/ \-_]", " ", (text or "").upper())).strip()


def check_type(doc_type: str) -> dict:
    if doc_type not in DOC_TYPES:
        raise CoverError(f"Unknown document type '{doc_type}'.")
    return DOC_TYPES[doc_type]


# ── MDL matching ─────────────────────────────────────────────────────────────
def candidates(db: Session, project_id: str, doc_type: str, sub_label: str = "") -> list[dict]:
    """MDL records whose title names this kind of document (and, for a datasheet, the instrument type), best first."""
    spec = check_type(doc_type)
    found: dict[str, tuple[int, dict]] = {}
    for kw in spec["keywords"]:
        res = mdl_service.search(db, project_id, q=kw.replace("/", " "), limit=200)
        for item in res.get("items", []):
            title = _norm(item["document_name"])
            if _norm(kw) not in title and _norm(kw).replace(" ", "") not in title.replace(" ", ""):
                continue
            score, full = 10, True
            if sub_label:
                words = [w for w in _norm(sub_label).split() if len(w) > 1 and w not in _STOP]
                hits = sum(1 for w in words if w in title.split())
                if words and hits == 0:
                    continue                       # a datasheet of another instrument type
                full = hits == len(words)
                score += 5 * hits + (20 if full else 0)
            found.setdefault(item["mdl_record_id"], (score, {**item, "full_match": full}))
    return [it for _, it in sorted(found.values(), key=lambda x: -x[0])]


def _record(db: Session, project_id: str, record_id: str) -> Optional[dict]:
    return mdl_service.get_record(db, project_id, record_id)


def _get(db: Session, project_id: str, doc_type: str, sub_key: str) -> Optional[DeliverableCover]:
    return (db.query(DeliverableCover)
            .filter_by(project_id=project_id, doc_type=doc_type, sub_key=sub_key or "").first())


def _loads(text: Optional[str], default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def fingerprint(record: dict, info: dict, revisions: list) -> str:
    """What an approval covers: the MDL number / title and every entered cover value."""
    blob = json.dumps({"doc": record.get("document_number"), "title": record.get("document_name"),
                       "info": info, "revisions": revisions}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def resolve(db: Session, project_id: str, doc_type: str, sub_key: str = "", sub_label: str = "") -> dict:
    """
    The cover sheet a generator will use, and its state:
      status  NOT_AVAILABLE      - no project / no MDL / no single matching MDL record / cover details not entered
              APPROVAL_REQUIRED  - complete, not (or no longer) approved: the output is marked DRAFT
              AVAILABLE          - complete and approved
    """
    spec = check_type(doc_type)
    out: dict = {"doc_type": doc_type, "doc_label": spec["label"] + (f" - {sub_label}" if sub_label else ""),
                 "project_id": project_id or None, "sub_key": sub_key or "", "status": "NOT_AVAILABLE",
                 "record": None, "match": None, "candidates": [], "revision": None, "approved": False,
                 "approval": None, "message": ""}
    if not project_id:
        out["message"] = "Select a project first: the cover sheet is resolved from the project's Master Document List."
        return out
    if not mdl_service.get_active(db, project_id):
        out["message"] = ("No Master Document List is uploaded for this project. Upload it in the Cover Sheet Generator "
                          "to resolve the document number and title.")
        return out
    cover = _get(db, project_id, doc_type, sub_key)
    record = None
    if cover and cover.mdl_record_id:
        record = _record(db, project_id, cover.mdl_record_id)
        out["match"] = "selected"
        if record is None:
            out["message"] = "The MDL record chosen for this document is no longer in the active MDL. Choose it again."
    if record is None:
        cands = candidates(db, project_id, doc_type, sub_label)
        out["candidates"] = cands[:25]
        sure = [c for c in cands if c.get("full_match")]
        if len(sure) == 1:                         # exactly one clear match: used; otherwise the engineer picks
            record, out["match"] = {k: v for k, v in sure[0].items() if k != "full_match"}, "keyword"
        elif not out["message"]:
            out["message"] = (f"No MDL document matches '{out['doc_label']}'. Choose the document from the MDL."
                              if not cands else
                              f"{len(cands)} MDL documents could be the {out['doc_label']}. Choose the right one.")
    out["record"] = record
    if record is None:
        return out
    info = _loads(cover.project_info_json, {}) if cover else {}
    revisions = _loads(cover.revisions_json, []) if cover else []
    if not revisions:
        out["message"] = ("Cover sheet details (revision, date, prepared / checked / approved by) are not entered yet. "
                          "Complete them once in the Cover Sheet Generator.")
        return out
    out["revision"] = revisions[-1].get("rev_no") or None
    req = db.query(ApprovalRequest).filter_by(id=cover.approval_request_id).first() if cover.approval_request_id else None
    fp = fingerprint(record, info, revisions)
    if req:
        out["approval"] = {"id": req.id, "status": req.status, "reviewed_by": req.reviewed_by_name,
                           "current": cover.approval_fingerprint == fp}
    if req and req.status == "approved" and cover.approval_fingerprint == fp:
        out.update(status="AVAILABLE", approved=True, message="Approved cover sheet.")
    else:
        out["status"] = "APPROVAL_REQUIRED"
        out["message"] = ("The document is pending the required engineering approval and cannot yet be issued as an "
                          "approved client-submission document. It is generated as a DRAFT.")
        if req and req.status == "approved":
            out["message"] = "The cover details changed after approval - approval is required again. It is generated as a DRAFT."
        elif req and req.status == "rejected":
            out["message"] = "The cover sheet was rejected" + (f" ({req.review_notes})" if req.review_notes else "") + ". It is generated as a DRAFT."
    return out


def details(db: Session, project_id: str, doc_type: str, sub_key: str = "") -> dict:
    cover = _get(db, project_id, doc_type, sub_key)
    return {"project_info": _loads(cover.project_info_json, {}) if cover else {},
            "revisions": _loads(cover.revisions_json, []) if cover else [],
            "mdl_record_id": cover.mdl_record_id if cover else None,
            "updated_by": cover.updated_by if cover else None,
            "updated_at": cover.updated_at.isoformat() if cover and cover.updated_at else None}


def save(db: Session, project_id: str, doc_type: str, sub_key: str, user: str, *, mdl_record_id: Optional[str] = None,
         project_info: Optional[dict] = None, revisions: Optional[list] = None, clear_record: bool = False) -> None:
    check_type(doc_type)
    if not project_id:
        raise CoverError("Select a project first.")
    if mdl_record_id and _record(db, project_id, mdl_record_id) is None:
        raise CoverError("That document is not in the project's active MDL.")
    if revisions is not None:
        if not revisions:
            raise CoverError("At least one revision entry is required.")
        for r in revisions:
            if not str(r.get("rev_no") or "").strip():
                raise CoverError("Every revision needs a revision number.")
    cover = _get(db, project_id, doc_type, sub_key)
    if cover is None:
        cover = DeliverableCover(project_id=project_id, doc_type=doc_type, sub_key=sub_key or "")
        db.add(cover)
    if mdl_record_id or clear_record:
        cover.mdl_record_id = mdl_record_id or None
    if project_info is not None:
        cover.project_info_json = json.dumps({k: str(project_info.get(k) or "").strip() for k in PROJECT_FIELDS})
    if revisions is not None:
        keys = ("rev_no", "date", "description", "prepared_by", "checked_by", "approved_by")
        cover.revisions_json = json.dumps([{k: str(r.get(k) or "").strip() for k in keys} for r in revisions])
    cover.updated_by, cover.updated_at = user, datetime.utcnow()
    db.commit()


def request_approval(db: Session, project_id: str, doc_type: str, sub_key: str, sub_label: str,
                     submitter_name: str, submitter_id: str, notes: Optional[str] = None) -> dict:
    r = resolve(db, project_id, doc_type, sub_key, sub_label)
    if r["record"] is None or r["revision"] is None:
        raise CoverError(r["message"] or "The cover sheet is not complete.")
    if r["approved"]:
        raise CoverError("This cover sheet is already approved.")
    cover = _get(db, project_id, doc_type, sub_key)
    info, revisions = _loads(cover.project_info_json, {}), _loads(cover.revisions_json, [])
    fp = fingerprint(r["record"], info, revisions)
    req = ApprovalRequest(request_type="coversheet", instrument_type=sub_label or None, status="pending",
                          submitted_by_name=submitter_name, submitted_by_id=submitter_id, submitter_notes=notes,
                          payload_json=json.dumps({"kind": "deliverable_cover", "project_id": project_id,
                                                   "doc_type": doc_type, "doc_label": r["doc_label"],
                                                   "document_number": r["record"]["document_number"],
                                                   "document_title": r["record"]["document_name"],
                                                   "revision": r["revision"], "project_info": info,
                                                   "revisions": revisions, "fingerprint": fp}))
    db.add(req)
    db.flush()
    try:
        from ..routers.approvals import _notify_via_routes
        _notify_via_routes(db, submitter_id, req.id, "cover sheet", submitter_name)
    except Exception:
        pass                                            # a notification problem never blocks the request
    cover.approval_request_id, cover.approval_fingerprint = req.id, fp
    db.commit()
    return {"approval_request_id": req.id}


def list_covers(db: Session, project_id: str) -> list[dict]:
    rows = db.query(DeliverableCover).filter_by(project_id=project_id).all()
    return [{"doc_type": c.doc_type, "sub_key": c.sub_key, "mdl_record_id": c.mdl_record_id,
             "revisions": len(_loads(c.revisions_json, [])), "updated_by": c.updated_by,
             "updated_at": c.updated_at.isoformat() if c.updated_at else None} for c in rows]


# ── the cover sheet workbook ─────────────────────────────────────────────────
def cover_workbook(db: Session, resolution: dict, custom_template: Optional[bytes] = None) -> tuple[bytes, list[str]]:
    """The filled cover sheet (.xlsx) for a resolved document. A draft keeps Checked / Approved empty."""
    from utils.coversheet_generator import generate_cover_sheet
    if resolution["record"] is None or resolution["revision"] is None:
        raise CoverError(resolution["message"] or "No cover sheet is available for this document.")
    cover = _get(db, resolution["project_id"], resolution["doc_type"], resolution["sub_key"])
    info = _loads(cover.project_info_json, {})
    revisions = [dict(r) for r in _loads(cover.revisions_json, [])]
    if not resolution["approved"]:
        for r in revisions:
            r["checked_by"] = r["approved_by"] = ""
    mapped = mdl_service.coversheet_fields(resolution["record"])
    project_info = {**info, **mapped["fields"]}
    if custom_template:
        return _custom_cover(custom_template, resolution, project_info, revisions), mapped["warnings"]
    data, _name, err = generate_cover_sheet(project_info, revisions,
                                            document_number=resolution["record"]["document_number"],
                                            document_title=resolution["record"]["document_name"])
    if err:
        raise CoverError(f"The cover sheet could not be built: {err}")
    return data, mapped["warnings"]


def _custom_cover(template: bytes, resolution: dict, project_info: dict, revisions: list) -> bytes:
    """An engineer's own cover template, filled from the same MDL + cover data (fields found by their labels)."""
    from utils import coversheet_excel_fill as fill
    from utils import coversheet_template_analyzer as an
    try:
        a = an.analyze(template)
    except an.TemplateError as e:
        raise CoverError(f"The custom cover sheet template could not be read: {e}")
    latest = revisions[-1]
    values = {"document_number": resolution["record"]["document_number"],
              "document_description": resolution["record"]["document_name"],
              "revision": latest.get("rev_no", ""), "date": latest.get("date", ""),
              "prepared_by": latest.get("prepared_by", ""), "checked_by": latest.get("checked_by", ""),
              "approved_by": latest.get("approved_by", "")}
    # only cells the analyser found with HIGH confidence (it pre-confirms those); anything uncertain is skipped, never guessed
    mapping = {}
    for k, v in (a.get("fields") or {}).items():
        sure = fill.confirmed_targets(v) or fill.confirmed_parts(v)
        mapping[k] = v if sure and str(values.get(k) or "").strip() else {**v, "targets": [], "parts": {}, "skipped": True}
    missing = [k for k in an.REQUIRED if not (fill.confirmed_targets(mapping.get(k) or {}) or fill.confirmed_parts(mapping.get(k) or {}))]
    if missing:
        raise CoverError("The custom cover sheet template has no recognisable "
                         + " / ".join(an.FIELD_LABELS.get(k, k) for k in missing) + " field. Use the iEZ cover sheet instead.")
    try:
        out, _warn = fill.fill_template(template, a["sheet"], mapping, values)
    except Exception as e:
        raise CoverError(f"The custom cover sheet template could not be filled: {e}")
    return out
