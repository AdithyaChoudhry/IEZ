"""
IODB reader for Loop Wiring (Test).

Reading the workbook reuses the existing shared reader (utils.file_handler.read_iodb - sheet and
header-row detection). Columns are then resolved SEMANTICALLY (normalised header aliases), never
by position. Columns that an IODB revision does not have are reported as unavailable - they never
fail the module.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any, Optional

from .common import clean, norm_header

# canonical field -> (aliases, allow trailing unit words)
_UNIT_WORDS = {"M", "MT", "MTR", "MTRS", "MTS", "METER", "METERS", "METRE", "METRES", "IN"}
IODB_FIELDS: dict[str, tuple[list[str], bool]] = {
    "TAG_NO": (["TAG NO", "TAG NUMBER", "TAG"], False),
    "LOOP_NO": (["LOOP NUMBER", "LOOP NO"], False),
    "INSTRUMENT_TYPE": (["INSTRUMENT TYPE NAME", "INSTRUMENT NAME", "INSTRUMENT TYPE"], False),
    "MEASURING_TYPE": (["INSTRUMENT MEASURING TYPE"], False),
    "SIGNAL_DESCRIPTION": (["SIGNAL DESCRIPTION"], False),
    "SIGNAL_IO_TYPE": (["SIGNAL I O TYPE", "SIGNAL IO TYPE"], False),
    "JB_TAG": (["JUNCTION BOX TAG NO", "JUNCTION BOX", "JB TAG NO", "JB TAG"], False),
    "JB_TERMINAL_PLUS": (["JB TERMINAL PLUS"], False),
    "JB_TERMINAL_MINUS": (["JB TERMINAL MINUS"], False),
    "BRANCH_CABLE_TAG": (["INSTRUMENT TO JB CABLE TAG NO"], False),
    "BRANCH_CABLE_TYPE": (["INSTRUMENT TO JB CABLE TYPE"], False),
    "BRANCH_CABLE_LENGTH": (["BRANCH CABLE LENGTH"], True),
    "ROUTE_NUMBER": (["ROUTE NUMBER", "ROUTE NO"], False),
    "BRANCH_FERRULE": (["BRANCH FERRULE"], False),
    "JB_GLAND_SIZE": (["JB SIDE GLAND SIZE"], False),
    "MAIN_CABLE_TAG": (["MAIN CABLE TAG NUMBER", "MAIN CABLE TAG NO"], False),
    "MAIN_CABLE_TYPE": (["MAIN CABLE TYPE"], False),
    "MAIN_CABLE_FERRULE": (["MAIN CABLE FERRULE"], False),
    "MAIN_CABLE_LENGTH": (["MAIN CABLE LENGTH"], True),
    "IS_NIS": (["IS NIS TYPE", "IS NIS"], False),
    "HART": (["HART"], False),
    "POWER_SUPPLY": (["POWER SUPPLY"], False),
    "FIELD_POWER_LOAD": (["FIELD POWER LOAD"], False),
    "ZENER_BARRIER": (["ZENER BARRIER"], False),
    "REDUNDANT_IO": (["REDUNDANT I O", "REDUNDANT IO"], False),
    "FAIL_ACTION": (["FAIL ACTION"], False),
    "WIRE_TYPE": (["2 WIRE 4 WIRE"], False),
    "REMARKS": (["REMARKS"], False),
}


@dataclass
class IodbData:
    file_name: str
    rows: list[dict[str, str]] = field(default_factory=list)       # canonical field -> text, plus "_row"
    resolved: dict[str, str] = field(default_factory=dict)          # canonical -> actual header
    missing: list[str] = field(default_factory=list)                # canonical fields this IODB lacks

    def summary(self) -> dict:
        return {"file_name": self.file_name, "rows": len(self.rows), "fields_resolved": self.resolved,
                "fields_unavailable": self.missing}


def resolve_iodb_fields(columns) -> dict[str, Optional[str]]:
    keyed: dict[str, str] = {}
    for col in columns:
        keyed.setdefault(norm_header(col), col)
    out: dict[str, Optional[str]] = {}
    for name, (aliases, unit_suffix) in IODB_FIELDS.items():
        found = None
        for alias in aliases:
            if alias in keyed:
                found = keyed[alias]
                break
            if unit_suffix:
                for key, actual in keyed.items():
                    if key.startswith(alias + " ") and all(t in _UNIT_WORDS for t in key[len(alias):].split()):
                        found = actual
                        break
            if found:
                break
        out[name] = found
    return out


def parse_iodb(file_bytes: bytes, file_name: str = "IODB.xlsx") -> IodbData:
    """Raises ValueError (user-facing message) when the file cannot be used."""
    from utils.file_handler import read_iodb

    df, err = read_iodb(io.BytesIO(file_bytes))
    if err or df is None:
        raise ValueError(f"The IODB could not be read: {err}")
    resolved_all = resolve_iodb_fields(df.columns)
    if not resolved_all["TAG_NO"]:
        raise ValueError("The IODB has no TAG NO column, so loops cannot be matched.")
    data = IodbData(file_name=file_name,
                    resolved={k: v for k, v in resolved_all.items() if v},
                    missing=[k for k, v in resolved_all.items() if not v])
    cols = {k: v for k, v in resolved_all.items() if v}
    series = {k: df[v].tolist() for k, v in cols.items()}
    for i in range(len(df)):
        row = {k: clean(series[k][i]) for k in cols}
        if not row.get("TAG_NO"):
            continue
        row["_row"] = str(int(df.index[i]) + 2)
        data.rows.append(row)
    return data
