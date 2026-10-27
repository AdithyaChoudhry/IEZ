"""IODB Comparison & Revision engine (read-only; works on parsed copies, never on the uploaded files)."""
from .engine import CompareError, compare_files, compare_tables, load_table  # noqa: F401
