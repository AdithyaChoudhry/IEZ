"""
Shared IODB router - one session-scoped IODB reused by the Instrument List, I/O List, Cable Schedule, Process Data
Requisition, Datasheet and Loop Wiring pages. Input management only: no generator logic lives here.
"""
from __future__ import annotations

import io
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel

from ..auth.models import User
from ..config import settings
from ..deps import get_current_user
from ..services.shared_iodb import clean_session_id, store

import sys
sys.path.insert(0, '/app')
from utils.file_handler import read_iodb

router = APIRouter(prefix="/shared-iodb", tags=["Shared IODB"])


class SharedIODBInfo(BaseModel):
    available: bool
    file_name: Optional[str] = None
    uploaded_at: Optional[str] = None
    uploaded_by: Optional[str] = None
    status: Optional[str] = None
    size: Optional[int] = None


def _validate(data: bytes) -> Optional[str]:
    """None when the file is a usable IODB, else the reason. Uses the parsers the generators themselves use."""
    df, err = read_iodb(io.BytesIO(data))
    if err is None and df is not None and len(df.columns) > 0 and len(df) > 0:
        return None
    try:                                              # the Datasheet generator reads IODBs with its own loader
        from utils.datasheet_generator import load_iodb
        df2, cols, err2 = load_iodb(io.BytesIO(data))
        if err2 is None and df2 is not None and len(df2) > 0:
            return None
    except Exception:
        pass
    if err:
        return err
    return "The IODB has no data rows."


@router.get("", response_model=SharedIODBInfo)
def get_shared_iodb(current_user: User = Depends(get_current_user), x_iez_session: Optional[str] = Header(None)):
    e = store.info(current_user.id, clean_session_id(x_iez_session))
    return SharedIODBInfo(**e.public()) if e else SharedIODBInfo(available=False)


@router.post("", response_model=SharedIODBInfo)
async def upload_shared_iodb(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    x_iez_session: Optional[str] = Header(None),
):
    """Validate the file; only a valid IODB replaces the current Shared IODB (an invalid one leaves it untouched)."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > settings.SHARED_IODB_MAX_BYTES:
        raise HTTPException(status_code=413, detail="The IODB file is too large.")
    reason = await run_in_threadpool(_validate, data)
    if reason is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"IODB validation failed: {reason}")
    e = store.put(current_user.id, clean_session_id(x_iez_session), file.filename or "IODB.xlsx", data, current_user.username)
    return SharedIODBInfo(**e.public())


@router.get("/file")
def download_shared_iodb(current_user: User = Depends(get_current_user), x_iez_session: Optional[str] = Header(None)):
    """The stored bytes, exactly as uploaded - the browser hands them to the generator like a fresh upload."""
    got = store.read(current_user.id, clean_session_id(x_iez_session))
    if not got:
        raise HTTPException(status_code=404, detail="No Shared IODB is available for this session.")
    entry, data = got
    return Response(content=data, media_type="application/octet-stream",
                    headers={"X-Shared-IODB-Name": entry.file_name.encode("ascii", "ignore").decode() or "IODB.xlsx",
                             "Cache-Control": "no-store"})


@router.delete("", response_model=SharedIODBInfo)
def clear_shared_iodb(current_user: User = Depends(get_current_user), x_iez_session: Optional[str] = Header(None)):
    store.clear(current_user.id, clean_session_id(x_iez_session))
    return SharedIODBInfo(available=False)
