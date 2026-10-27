"""IODB Comparison & Revision Report router (part of the IODB Validator area)."""
from typing import Optional
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from ..deps import get_current_user
from ..auth.models import User

import sys
sys.path.insert(0, '/app')
from utils.iodb_compare import CompareError, compare_files
from utils.iodb_compare import store
from utils.iodb_compare.categories import CATEGORY_NAMES
from utils.iodb_compare.pdf_report import KINDS, build_pdf

router = APIRouter(prefix="/validator/compare", tags=["IODB Comparison"])

STATUSES = ("added", "deleted", "modified", "unchanged", "review")
MAX_PAGE_SIZE = 200
MAX_UPLOAD_BYTES = 60 * 1024 * 1024


def _get(cid: str) -> dict:
    try:
        return store.load_result(cid)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="This comparison is no longer available. Please run the comparison again.")


def _light(r: dict) -> dict:
    """Everything except the (large) record lists - the UI pages those separately."""
    out = {k: v for k, v in r.items() if k != "records"}
    out["status_counts"] = {k: len(v) for k, v in r["records"].items()}
    out["categories"] = [{"code": c, "name": n} for c, n in sorted(CATEGORY_NAMES.items())]
    return out


@router.post("")
def run_comparison(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
    ignore_case: bool = Form(True),
    project_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    data1, data2 = file1.file.read(), file2.file.read()
    if not data1 or not data2:
        raise HTTPException(status_code=400, detail="Both IODB files are required.")
    if len(data1) > MAX_UPLOAD_BYTES or len(data2) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="An uploaded file is too large (limit 60 MB).")
    try:
        result, full = compare_files(data1, file1.filename or "IODB 1", data2, file2.filename or "IODB 2",
                                     ignore_case=ignore_case, project=project_id or "", user=current_user.username)
    except CompareError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # never a bare 500 for a malformed workbook
        raise HTTPException(status_code=400, detail=f"The IODB files could not be compared: {exc}")
    store.save(result, full)
    return _light(result)


@router.get("/{cid}")
def get_comparison(cid: str, current_user: User = Depends(get_current_user)):
    return _light(_get(cid))


@router.get("/{cid}/records")
def list_records(
    cid: str,
    status_: str = Query("modified", alias="status"),
    q: str = "",
    category: str = "",
    field: str = "",
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
):
    r = _get(cid)
    if status_ not in STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {', '.join(STATUSES)}")
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    items = r["records"][status_]
    ql = q.strip().casefold()
    if ql:
        items = [i for i in items if any(ql in (i.get(k) or "").casefold()
                                         for k in ("tag", "shown_tag", "pid", "type", "service", "area"))]
    if status_ == "modified" and (category or field):
        items = [i for i in items if any((not category or c["category"] == category) and (not field or c["column"] == field)
                                         for c in i["changes"])]
    total = len(items)
    start = (max(page, 1) - 1) * page_size
    rows = [{k: v for k, v in i.items() if k != "changes"} | {
        "changed_fields": list(dict.fromkeys(c["column"] for c in i["changes"]))[:6]} for i in items[start:start + page_size]]
    return {"status": status_, "total": total, "page": max(page, 1), "page_size": page_size, "items": rows}


@router.get("/{cid}/record")
def get_record(cid: str, tag: str, current_user: User = Depends(get_current_user)):
    r = _get(cid)
    key = re.sub(r"\s+", " ", tag).strip().upper()
    full = store.load_full(cid)
    rec, st_name = None, None
    for name in STATUSES:
        for i in r["records"][name]:
            if i["tag"] == key:
                rec, st_name = i, name
                break
        if rec:
            break
    if rec is None:
        raise HTTPException(status_code=404, detail=f"TAG NO {tag} was not found in this comparison.")
    cols1, cols2 = full["columns1"], full["columns2"]
    row1 = full["rows1"].get(key)
    row2 = full["rows2"].get(key)
    return {
        "tag": rec["shown_tag"] or rec["tag"], "status": st_name, "n_changes": rec["n_changes"], "changes": rec["changes"],
        "iodb1": dict(zip(cols1, row1)) if row1 else None,
        "iodb2": dict(zip(cols2, row2)) if row2 else None,
        "duplicates1": [dict(zip(cols1, x)) for x in full["dups1"].get(key, [])],
        "duplicates2": [dict(zip(cols2, x)) for x in full["dups2"].get(key, [])],
    }


@router.get("/{cid}/pdf")
def download_pdf(cid: str, kind: str = "complete", current_user: User = Depends(get_current_user)):
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {', '.join(KINDS)}")
    r = _get(cid)
    pdf = build_pdf(r, kind, user=current_user.username, project=r.get("project") or "")
    name = {"summary": "Summary", "detailed": "Detailed", "complete": "Complete"}[kind]
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="IODB_Comparison_{name}_Report.pdf"'})
