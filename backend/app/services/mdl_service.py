"""
MDL service: stores the parsed Master Document List per project and serves the
searchable document register to the Coversheet Generator.

The MDL is the authoritative source of document number and title. Nothing here
edits engineering data; the Coversheet only reads it.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models.document_registry import DocumentAuditLog
from ..models.mdl import MDLRecord, ProjectMDL
from . import document_registry as reg


def _parser():
    """Import the shared parser from utils/ (same path trick the routers use)."""
    here = Path(__file__).resolve()
    for p in (here.parents[2], here.parents[3], Path("/app")):
        if (p / "utils").is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
    from utils import mdl_parser
    return mdl_parser


class MdlError(Exception):
    """Expected, user-facing MDL problem (invalid file, nothing selected, ...)."""


def _audit(db: Session, project_id: str, action: str, actor: Optional[str], **details: Any) -> None:
    db.add(DocumentAuditLog(project_id=project_id, module="coversheet_mdl", action=action,
                            actor=actor, details=json.dumps(details, default=str)))


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def get_active(db: Session, project_id: str) -> Optional[ProjectMDL]:
    return (db.query(ProjectMDL)
            .filter(ProjectMDL.project_id == project_id, ProjectMDL.active.is_(True))
            .order_by(ProjectMDL.id.desc()).first())


def mdl_to_dict(m: ProjectMDL) -> dict:
    return {
        "mdl_id": m.id, "project_id": m.project_id, "file_name": m.filename, "sheet": m.sheet_name,
        "header_row": m.header_row, "revision": m.revision,
        "revision_label": m.revision or "Not identified", "revision_source": m.revision_source,
        "document_count": m.document_count, "section_rows_ignored": m.section_rows_ignored,
        "duplicate_doc_numbers": m.duplicate_doc_numbers,
        "warnings": json.loads(m.warnings_json) if m.warnings_json else [],
        "uploaded_by": m.uploaded_by, "uploaded_at": _iso(m.uploaded_at), "valid": True,
    }


def record_to_dict(r: MDLRecord, m: ProjectMDL, duplicate: bool = False) -> dict:
    return {
        "mdl_record_id": r.record_id, "s_no": r.s_no or "", "discipline": r.discipline or "",
        "document_number": r.doc_no, "document_name": r.description,
        "document_category": r.category or "", "remarks": r.remarks or "",
        "source_file": m.filename, "source_sheet": m.sheet_name,
        "duplicate_document_number": duplicate,
    }


def _duplicate_numbers(db: Session, mdl_id: int) -> set[str]:
    rows = (db.query(MDLRecord.doc_no).filter(MDLRecord.mdl_id == mdl_id)
            .group_by(MDLRecord.doc_no).having(func.count(MDLRecord.id) > 1).all())
    return {r[0] for r in rows}


def summary(db: Session, project_id: str) -> dict:
    """Status of the project's active MDL (for the Coversheet 'MASTER DOCUMENT LIST' panel)."""
    m = get_active(db, project_id)
    if not m:
        return {"uploaded": False, "project_id": project_id}
    disciplines = (db.query(MDLRecord.discipline, func.count(MDLRecord.id))
                   .filter(MDLRecord.mdl_id == m.id).group_by(MDLRecord.discipline)
                   .order_by(MDLRecord.discipline).all())
    prev = (db.query(ProjectMDL)
            .filter(ProjectMDL.project_id == project_id, ProjectMDL.id != m.id)
            .order_by(ProjectMDL.id.desc()).first())
    return {"uploaded": True, **mdl_to_dict(m),
            "disciplines": [{"name": d or "(none)", "count": c} for d, c in disciplines],
            "previous": ({"file_name": prev.filename, "revision": prev.revision,
                          "revision_label": prev.revision or "Not identified"} if prev else None)}


def upload(db: Session, project_id: str, filename: str, data: bytes, user: Optional[str],
           selected_record_id: Optional[str] = None) -> dict:
    """
    Parse + validate + store an MDL, replacing the project's active MDL.
    An invalid file raises MdlError and leaves the existing active MDL untouched.
    """
    pid = reg.normalize_project_id(project_id)
    mp = _parser()
    try:
        parsed = mp.parse_mdl(data, filename)
    except mp.MdlFormatError as exc:
        raise MdlError(str(exc))

    digest = hashlib.sha256(data).hexdigest()
    previous = get_active(db, pid)
    previous_info = ({"file_name": previous.filename, "revision": previous.revision,
                      "revision_label": previous.revision or "Not identified"} if previous else None)

    if previous and previous.sha256 == digest:           # same file again - nothing to replace
        result = summary(db, pid)
        result.update(unchanged=True, replaced=False, previous=previous_info,
                      selection=_check_selection(db, previous, selected_record_id))
        return result

    reg.get_or_create_project(db, pid, None, user)
    if previous:
        previous.active = False
        previous.replaced_at = datetime.utcnow()

    new = ProjectMDL(
        project_id=pid, filename=filename, sheet_name=parsed.source_sheet, header_row=parsed.header_row,
        revision=parsed.revision, revision_source=parsed.revision_source,
        document_count=len(parsed.records), section_rows_ignored=parsed.section_rows_ignored,
        duplicate_doc_numbers=len(parsed.duplicate_doc_numbers),
        warnings_json=json.dumps(parsed.warnings), sha256=digest, uploaded_by=user, active=True,
    )
    db.add(new)
    db.flush()
    db.bulk_save_objects([
        MDLRecord(mdl_id=new.id, record_id=r.mdl_record_id, ordinal=i, s_no=r.s_no,
                  discipline=r.discipline, doc_no=r.document_number, description=r.document_name,
                  category=r.document_category, remarks=r.remarks)
        for i, r in enumerate(parsed.records)
    ])
    _audit(db, pid, "mdl_uploaded", user, file=filename, revision=parsed.revision,
           documents=len(parsed.records), previous_revision=previous.revision if previous else None)
    db.commit()

    result = summary(db, pid)
    result.update(unchanged=False, replaced=previous is not None, previous=previous_info,
                  selection=_check_selection(db, new, selected_record_id))
    return result


def _check_selection(db: Session, mdl: ProjectMDL, selected_record_id: Optional[str]) -> dict:
    """After a (re)upload: is the previously selected document still in the active MDL?"""
    if not selected_record_id:
        return {"status": "none"}
    rec = _get_record(db, mdl, selected_record_id)
    if rec:
        return {"status": "preserved", "record": record_to_dict(rec, mdl)}
    return {"status": "missing",
            "message": "Previously selected document is not available in the newly uploaded MDL."}


def remove_active(db: Session, project_id: str, user: Optional[str]) -> dict:
    pid = reg.normalize_project_id(project_id)
    m = get_active(db, pid)
    if not m:
        return {"removed": False}
    m.active = False
    m.replaced_at = datetime.utcnow()
    _audit(db, pid, "mdl_removed", user, file=m.filename, revision=m.revision)
    db.commit()
    return {"removed": True, "file_name": m.filename}


def _get_record(db: Session, mdl: ProjectMDL, record_id: str) -> Optional[MDLRecord]:
    return (db.query(MDLRecord)
            .filter(MDLRecord.mdl_id == mdl.id, MDLRecord.record_id == record_id).first())


def get_record(db: Session, project_id: str, record_id: str) -> Optional[dict]:
    """A record from THIS project's active MDL only (never another project's)."""
    m = get_active(db, project_id)
    if not m:
        return None
    rec = _get_record(db, m, record_id)
    if not rec:
        return None
    dup = db.query(func.count(MDLRecord.id)).filter(
        MDLRecord.mdl_id == m.id, MDLRecord.doc_no == rec.doc_no).scalar() > 1
    return record_to_dict(rec, m, dup)


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(db: Session, project_id: str, q: str = "", discipline: str = "", category: str = "",
           limit: int = 50, offset: int = 0) -> dict:
    """
    Search the active MDL by document name, document number and discipline.
    Every whitespace-separated term must match at least one of those fields.
    """
    m = get_active(db, project_id)
    if not m:
        return {"uploaded": False, "total": 0, "items": []}
    query = db.query(MDLRecord).filter(MDLRecord.mdl_id == m.id)
    for term in (q or "").split():
        # Plural-tolerant: "datasheets" must also find "Datasheet" (substring match covers the reverse).
        if len(term) > 3 and term.lower().endswith("s"):
            term = term[:-1]
        like = f"%{_escape_like(term)}%"
        query = query.filter(or_(MDLRecord.description.ilike(like, escape="\\"),
                                 MDLRecord.doc_no.ilike(like, escape="\\"),
                                 MDLRecord.discipline.ilike(like, escape="\\")))
    if discipline:
        query = query.filter(MDLRecord.discipline == discipline)
    if category:
        query = query.filter(MDLRecord.category == category)
    total = query.count()
    rows = (query.order_by(MDLRecord.ordinal)
            .offset(max(offset, 0)).limit(max(1, min(limit, 500))).all())
    dups = _duplicate_numbers(db, m.id)
    return {"uploaded": True, "total": total, "limit": limit, "offset": offset,
            "items": [record_to_dict(r, m, r.doc_no in dups) for r in rows]}


# ── Coversheet mapping ───────────────────────────────────────────────────────
MDL_CONTROLLED_CELLS = ("G2", "G4", "J4", "K4", "M4", "A10")


def coversheet_fields(record: dict) -> dict:
    """
    MDL record -> Coversheet fields.

        DESCRIPTION -> document title   (title block G2 + 'DOCUMENT TITLE' A10)
        DOC NO      -> document number  (ID strip: Job No. | Project | Doc. Code | Serial No.)

    The sheet has no single 'document number' cell: the number is composed in the ID
    strip. A WABAG number JOB-PROJECT-CODE-SERIAL is split into those boxes. Unit No.
    is not part of the MDL number and is left as entered. A number that does not have
    four parts is not guessed at - it is placed whole in Doc. Code with a warning.
    """
    mp = _parser()
    parts = mp.split_document_number(record["document_number"])
    fields = {"doc_title_short": record["document_name"], "doc_title_full": record["document_name"]}
    warnings: list[str] = []
    if parts:
        fields.update(parts)
    else:
        fields.update(doc_code=record["document_number"], job_no="", project_no="", serial_no="")
        warnings.append("The document number does not follow JOB-PROJECT-CODE-SERIAL; "
                        "the whole number was placed in the Doc. Code field.")
    if record.get("duplicate_document_number"):
        warnings.append("Multiple MDL entries use this document number. "
                        "The selected document description will be used.")
    return {"fields": fields, "warnings": warnings}


def audit_generation(db: Session, project_id: str, user: Optional[str], record: dict, filename: str) -> None:
    _audit(db, project_id, "coversheet_generated_from_mdl", user,
           document_number=record["document_number"], document_name=record["document_name"],
           mdl_file=record["source_file"], output=filename)
    db.commit()
