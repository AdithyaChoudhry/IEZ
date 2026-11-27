"""An IODB already read is answered from server memory - same table, own copy, never another file's."""
import io
import sys
import threading
import time
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import file_handler as FH, parsed_cache as PC, sop_datasheet as S  # noqa: E402


def book(tag="PT-1") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IODB"
    ws.append(["TAG NO", "INSTRUMENT TYPE", "SERVICE"])
    ws.append([tag, "PT", "x"])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def counted(monkeypatch, name, module):
    calls = []
    real = getattr(module, name)
    monkeypatch.setattr(module, name, lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    return calls


def test_the_same_file_is_read_once_and_callers_get_their_own_copy(monkeypatch):
    PC.clear()
    calls = counted(monkeypatch, "_parse_iodb", FH)
    data = book()
    first, err = FH.read_iodb(io.BytesIO(data))
    assert err is None
    first.loc[0, "TAG NO"] = "CHANGED"
    first["EXTRA"] = 1
    second, _ = FH.read_iodb(io.BytesIO(data))
    assert len(calls) == 1 and second.loc[0, "TAG NO"] == "PT-1" and "EXTRA" not in second.columns
    pd.testing.assert_frame_equal(second, FH._parse_iodb(io.BytesIO(data))[0])
    other, _ = FH.read_iodb(io.BytesIO(book("PT-2")))                       # a different file is read afresh
    assert other.loc[0, "TAG NO"] == "PT-2" and len(calls) == 3


def test_failures_are_not_remembered_and_the_datasheet_reader_is_cached_too(monkeypatch):
    PC.clear()
    calls = counted(monkeypatch, "_parse_iodb", FH)
    for _ in range(2):
        assert FH.read_iodb(io.BytesIO(b"not a workbook"))[0] is None
    assert len(calls) == 2
    d = counted(monkeypatch, "_parse_iodb_df", S)
    data = book()
    S._load_iodb_df(data)
    S._load_iodb_df(data)
    assert len(d) == 1


def test_simultaneous_uploads_share_one_read_and_old_files_leave(monkeypatch):
    PC.clear()
    reads = []

    def read():
        reads.append(1)
        time.sleep(0.2)
        return pd.DataFrame({"a": [1]}), None

    threads = [threading.Thread(target=PC.cached_table, args=("t", b"same", read)) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(reads) == 1
    for i in range(PC.MAX_FILES + 3):
        PC.cached_table("t", str(i).encode(), lambda: (pd.DataFrame({"a": [i]}), None))
    assert len(PC._entries) == PC.MAX_FILES
    monkeypatch.setattr(PC, "TTL_SECONDS", -1)
    PC.cached_table("t", b"same", read)
    assert len(reads) == 2
