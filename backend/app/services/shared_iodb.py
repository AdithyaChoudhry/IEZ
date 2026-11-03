"""
Shared IODB - ONE session-scoped IODB per authenticated user session, reused by every supported generator.

    Authenticated user (JWT) + browser session id  ->  one current IODB file

* The entry is keyed by (user id from the verified JWT, session id sent by the browser). A different user can never
  reach it; a new login gets a new session id, so an old entry is unreachable even if its logout call was lost.
* The file lives in a private temporary directory under a random name (never a user-supplied path, never a project
  document). Replacing, logging out, idling out and a server restart all delete the file.
* Nothing here parses or changes the IODB: generators receive the stored bytes exactly as uploaded.
"""
from __future__ import annotations

import os
import re
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import settings

_SID_OK = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_ENTRIES_PER_USER = 5          # several browser sessions of one user; oldest is evicted


def clean_session_id(value: Optional[str]) -> str:
    return value if value and _SID_OK.match(value) else "default"


@dataclass
class SharedIODB:
    file_name: str
    path: Path
    size: int
    uploaded_at: float
    uploaded_by: str
    validation_status: str
    last_used: float

    def public(self) -> dict:
        """What the frontend may see - no paths, no storage internals."""
        return {
            "available": True,
            "file_name": self.file_name,
            "uploaded_at": datetime.fromtimestamp(self.uploaded_at, tz=timezone.utc).isoformat(),
            "uploaded_by": self.uploaded_by,
            "status": self.validation_status,
            "size": self.size,
        }


class SharedIODBStore:
    def __init__(self, directory: Optional[str] = None, idle_seconds: Optional[int] = None):
        self.dir = Path(directory or settings.SHARED_IODB_DIR or Path(tempfile.gettempdir()) / "iez_shared_iodb")
        self.idle = idle_seconds if idle_seconds is not None else settings.SHARED_IODB_IDLE_MINUTES * 60
        self._entries: dict[tuple[int, str], SharedIODB] = {}
        self._lock = threading.Lock()
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for f in self.dir.glob("*.iodb"):      # the registry is in memory: files left by a previous process are unreachable
            self._unlink(f)

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def _sweep_locked(self, now: float) -> None:
        for key in [k for k, e in self._entries.items() if now - e.last_used > self.idle]:
            self._unlink(self._entries.pop(key).path)

    def info(self, user_id: int, sid: str) -> Optional[SharedIODB]:
        now = time.time()
        with self._lock:
            self._sweep_locked(now)
            e = self._entries.get((user_id, sid))
            if e and not e.path.exists():
                self._entries.pop((user_id, sid), None)
                return None
            return e

    def read(self, user_id: int, sid: str) -> Optional[tuple[SharedIODB, bytes]]:
        with self._lock:
            self._sweep_locked(time.time())
            e = self._entries.get((user_id, sid))
            if not e:
                return None
            try:
                data = e.path.read_bytes()
            except OSError:
                self._entries.pop((user_id, sid), None)
                return None
            e.last_used = time.time()
            return e, data

    def put(self, user_id: int, sid: str, file_name: str, data: bytes, uploaded_by: str, status: str = "Validated") -> SharedIODB:
        """Atomically make `data` the current Shared IODB (call only after the file passed validation)."""
        now = time.time()
        path = self.dir / f"{uuid.uuid4().hex}.iodb"
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        entry = SharedIODB(file_name=(file_name or "IODB.xlsx")[:200], path=path, size=len(data), uploaded_at=now,
                           uploaded_by=uploaded_by, validation_status=status, last_used=now)
        with self._lock:
            self._sweep_locked(now)
            old = self._entries.get((user_id, sid))
            self._entries[(user_id, sid)] = entry
            if old:
                self._unlink(old.path)
            mine = sorted(((k, e) for k, e in self._entries.items() if k[0] == user_id), key=lambda kv: kv[1].last_used)
            while len(mine) > MAX_ENTRIES_PER_USER:
                k, e = mine.pop(0)
                self._entries.pop(k, None)
                self._unlink(e.path)
        return entry

    def clear(self, user_id: int, sid: str) -> bool:
        with self._lock:
            e = self._entries.pop((user_id, sid), None)
        if e:
            self._unlink(e.path)
        return e is not None


store = SharedIODBStore()
