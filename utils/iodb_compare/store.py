"""Small on-disk + in-memory store for comparison results (survives restarts / multiple workers)."""
from __future__ import annotations

import gzip
import os
import pickle
import tempfile
import time
from collections import OrderedDict
from pathlib import Path

_TTL_SECONDS = 24 * 3600
_MEM_MAX = 6
_mem: "OrderedDict[str, dict]" = OrderedDict()


def _dir() -> Path:
    d = Path(os.environ.get("IEZ_COMPARE_DIR") or Path(tempfile.gettempdir()) / "iez_compare")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(cid: str, part: str) -> Path:
    if not cid.isalnum():
        raise KeyError(cid)
    return _dir() / f"{cid}.{part}.pkl.gz"


def _cleanup():
    cutoff = time.time() - _TTL_SECONDS
    for p in _dir().glob("*.pkl.gz"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


def _remember(cid: str, result: dict) -> None:
    _mem[cid] = result
    _mem.move_to_end(cid)
    while len(_mem) > _MEM_MAX:
        _mem.popitem(last=False)


def save(result: dict, full: dict) -> None:
    _cleanup()
    for part, obj in (("result", result), ("full", full)):
        with gzip.open(_path(result["id"], part), "wb", compresslevel=3) as fh:
            pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)
    _remember(result["id"], result)


def load_result(cid: str) -> dict:
    if cid in _mem:
        _mem.move_to_end(cid)
        return _mem[cid]
    p = _path(cid, "result")
    if not p.exists():
        raise KeyError(cid)
    with gzip.open(p, "rb") as fh:
        res = pickle.load(fh)
    _remember(cid, res)
    return res


def load_full(cid: str) -> dict:
    p = _path(cid, "full")
    if not p.exists():
        raise KeyError(cid)
    with gzip.open(p, "rb") as fh:
        return pickle.load(fh)
