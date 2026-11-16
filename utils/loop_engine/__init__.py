"""Loop Wiring engine: I/O Assignment -> 42 approved typicals -> formula-driven loop drawings."""
from .registry import build_registry, library_error            # noqa: F401
from .source import read_assignment                            # noqa: F401
from .analysis import analyze, read_matrix, Analysis           # noqa: F401
from .generate import generate_workbook, build_report          # noqa: F401
