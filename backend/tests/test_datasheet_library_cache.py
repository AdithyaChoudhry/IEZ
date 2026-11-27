"""The standard template library is read once per workbook. Re-reading it (a cache smaller than the library, or a new
format descriptor for every cell) made the first Datasheet Generator request run past the proxy's 120-second limit."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import datasheet_library as DL  # noqa: E402


def test_every_library_workbook_is_read_once_and_formats_are_shared():
    DL._sheets_cached.cache_clear()
    DL._learned_tag_labels.cache_clear()
    DL._guide_values.cache_clear()
    templates = DL.library()
    for _ in range(2):
        for t in templates:
            DL.template_info(t)
    info = DL._sheets_cached.cache_info()
    assert info.misses == len(templates) == info.currsize
    sm = next(iter(DL.sheets_of(templates[0]).values()))
    assert len({id(s) for s in sm.styles.values()}) < len(sm.styles)
