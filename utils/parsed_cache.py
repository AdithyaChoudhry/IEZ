"""
Server-side memory of IODB tables already read, so that one file is not parsed again at every step.

* Keyed by a fingerprint (SHA-256) of the file's own bytes: a file that differs by one cell is read afresh, and only
  someone who uploads the identical file can get its table.
* Memory only, nothing on disk or on the user's computer; a restart clears it. A few recent files, for a limited time.
* Every caller gets its own copy, so nothing a generator does to its table reaches another request.
* While a file is being read, further requests for the same file wait for that read instead of starting their own.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from typing import Callable

MAX_FILES = 5
MAX_BYTES = 300 * 1024 * 1024        # of table memory, all files together
TTL_SECONDS = 3600

_entries: "OrderedDict[tuple, tuple]" = OrderedDict()      # key -> (table, size, last used)
_reading: dict = {}                                        # key -> lock held while that file is being read
_lock = threading.Lock()


def clear() -> None:
    with _lock:
        _entries.clear()


def _lookup(key):
    now = time.time()
    with _lock:
        for k in [k for k, (_, _, used) in _entries.items() if now - used > TTL_SECONDS]:
            del _entries[k]
        hit = _entries.get(key)
        if hit is None:
            return None
        _entries[key] = (hit[0], hit[1], now)
        _entries.move_to_end(key)
        return hit[0]


def _store(key, table) -> None:
    size = int(table.memory_usage(index=True, deep=True).sum())
    if size > MAX_BYTES:
        return
    with _lock:
        _entries[key] = (table, size, time.time())
        _entries.move_to_end(key)
        while len(_entries) > MAX_FILES or sum(s for _, s, _ in _entries.values()) > MAX_BYTES:
            _entries.popitem(last=False)


def cached_table(kind: str, data: bytes, read: Callable):
    """`read()` -> (DataFrame | None, error | None). Only successful reads are remembered."""
    key = (kind, hashlib.sha256(data).hexdigest())
    table = _lookup(key)
    if table is not None:
        return table.copy(), None
    with _lock:
        gate = _reading.setdefault(key, threading.Lock())
    try:
        with gate:
            table = _lookup(key)                           # read by another request while this one waited
            if table is None:
                table, error = read()
                if error is not None or table is None:
                    return table, error
                _store(key, table)
            return table.copy(), None
    finally:
        with _lock:
            _reading.pop(key, None)
