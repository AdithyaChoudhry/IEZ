"""
Cover sheet snapshot for the I/O List generator: the linked cover sheet (centralised Cover Sheet Generator) resolved ONCE per generation request.
The same cover workbook is used to fill the document headers / revision history of the I/O List workbook and is the one inserted as its first
sheet (deliverables.finalize(snapshot=...)), so a cover edited while the request runs can never make the two disagree.
"""
from __future__ import annotations

from typing import Optional

from ..database import SessionLocal
from . import deliverable_covers as DC


def snapshot(project_id: Optional[str], custom_template: Optional[bytes] = None) -> dict:
    """{"resolution": ..., "cover": bytes | None, "warnings": [...], "message": str} - never raises (a cover problem never stops the I/O List)."""
    db = SessionLocal()
    try:
        r = DC.resolve(db, project_id or "", "io_list")
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
