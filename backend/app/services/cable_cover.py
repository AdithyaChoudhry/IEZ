"""
Cover sheet snapshot for the Cable Schedule generator: the linked cover sheet (centralised Cover Sheet Generator, document type "cable_schedule")
resolved ONCE per generation request. The same cover workbook fills the header metadata of every Cable Schedule worksheet and is the one inserted
as the first sheet of the output (deliverables.finalize(snapshot=...)), so a cover edited while the request runs can never make the two disagree.
Read-only use of the Cover Sheet Generator's own resolution - nothing is stored or changed.
"""
from __future__ import annotations

from typing import Optional

from .. import database
from . import deliverable_covers as DC


def snapshot(project_id: Optional[str], custom_template: Optional[bytes] = None) -> dict:
    """{"resolution": ..., "cover": bytes | None, "warnings": [...], "message": str} - never raises (the caller decides what a missing cover means)."""
    db = database.SessionLocal()                  # looked up at call time (the module attribute), like every other service
    try:
        try:
            r = DC.resolve(db, project_id or "", "cable_schedule")
        except Exception as e:                                       # a cover lookup problem never stops the engineering output
            msg = str(e) if isinstance(e, DC.CoverError) else "The cover sheet could not be looked up."
            r = {"doc_type": "cable_schedule", "doc_label": DC.DOC_TYPES["cable_schedule"]["label"], "project_id": project_id or None,
                 "sub_key": "", "status": "NOT_AVAILABLE", "record": None, "match": None, "candidates": [], "revision": None,
                 "legacy_approval": None, "message": msg}
        out = {"resolution": r, "cover": None, "warnings": [], "message": r.get("message") or ""}
        if r["record"] is not None and r["revision"] is not None:
            try:
                out["cover"], out["warnings"] = DC.cover_workbook(db, r, custom_template)
            except DC.CoverError as e:
                out["message"] = str(e)
            except Exception as e:                                   # pragma: no cover
                out["message"] = f"The cover sheet could not be built: {e}"
        return out
    finally:
        db.close()
