"""
dynamic_rules.py
================
Persistent storage and execution engine for user-defined validation rules.

Storage format  : JSON file at RULES_FILE path.
Rule object     : DynamicRule dataclass.
Execution       : run_dynamic_rules(df) → list[error_dict]

Rule Types
    COLUMN  – Evaluates a single column cell; fires when that cell violates
              the primary condition (+ optional AND/OR extra conditions).
    ROW     – Evaluates multiple columns together (cross-field logic).
              All conditions are evaluated with AND / OR chaining.
              Error is anchored to `target_column` if provided, otherwise
              to the TAG NO column.

Condition schema (each condition dict)
    {
      "column":           str,
      "operator":         str,    # see OPERATORS
      "value":            str,
      "logical_operator": "AND" | "OR"   # how THIS condition chains to
                                          # the previous one (ignored for #0)
    }

Supported operators
    ==  !=  >  <  >=  <=
    CONTAINS   NOT CONTAINS
    IN         NOT IN        (comma-separated list)
    COL==      COL!=         (column-to-column comparison)
    IS EMPTY   IS NOT EMPTY  (presence check; value ignored)

Advanced features
    • rule_type         – "COLUMN" | "ROW"
    • target_column     – error anchor for ROW rules (defaults to TAG NO)
    • conditions        – unified condition list (replaces old primary +
                          multi_conditions; old format auto-converted on load)
    • case_sensitive    – default False
    • is_active         – toggle without deleting
    • priority          – lower = runs first
    • source            – always "dynamic"
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

# Path where rules are persisted between sessions
RULES_FILE = Path(__file__).parent.parent / "dynamic_rules.json"

# ── Predefined rule metadata (read-only display) ─────────────────────────────
PREDEFINED_RULES_META: list[dict] = [
    {"rule": 1,   "name": "Empty Cell Validation",               "description": "All cells must be filled — STATUS and REMARKS columns are excluded."},
    {"rule": 2,   "name": "Area Classification vs IS/NIS Type",  "description": "Hazardous area → IS type; Safe area → NIS type."},
    {"rule": 3,   "name": "Scope of Supply vs Vendor Package",   "description": "Non-WABAG scope must name the Vendor Package."},
    {"rule": 4,   "name": "TAG keyword → Instrument Name",       "description": "TAG NO keyword must match Instrument Name by substring."},
    {"rule": "4B","name": "TAG NO Capitalisation",               "description": "TAG NO must be fully uppercase."},
    {"rule": 5,   "name": "Power Supply vs Wire Type",           "description": "Non-24V-DC power + not 4-wire → mismatch."},
    {"rule": 6,   "name": "Signal Type vs Junction Box",         "description": "AI → AJB; DI/DO → DJB."},
    {"rule": 7,   "name": "Calibration vs Instrument Range",     "description": "Calibration max must not exceed Instrument range max."},
    {"rule": 8,   "name": "Unit Consistency",                    "description": "Calibration unit must match Instrument range unit."},
    {"rule": 9,   "name": "Fail Action Validation",              "description": "Must be FO, FC, or LAST POS."},
    {"rule": 10,  "name": "Alarm Setpoint Order",                "description": "LL < L < H < HH."},
    {"rule": 11,  "name": "S.NO Ascending Order",                "description": "S.NO must be strictly ascending."},
    {"rule": 12,  "name": "Spelling Check",                      "description": "Free-text columns checked for misspellings."},
]

# ── Operator catalogue ────────────────────────────────────────────────────────
OPERATORS: list[str] = [
    "==", "!=", ">", "<", ">=", "<=",
    "CONTAINS", "NOT CONTAINS",
    "IN", "NOT IN",
    "COL==", "COL!=",
    "IS EMPTY", "IS NOT EMPTY",
]

OPERATOR_LABELS: dict[str, str] = {
    "==":           "== (equals)",
    "!=":           "!= (not equals)",
    ">":            ">  (greater than)",
    "<":            "<  (less than)",
    ">=":           ">= (greater or equal)",
    "<=":           "<= (less or equal)",
    "CONTAINS":     "CONTAINS",
    "NOT CONTAINS": "NOT CONTAINS",
    "IN":           "IN  (comma-separated list)",
    "NOT IN":       "NOT IN (comma-separated list)",
    "COL==":        "COL== (equals another column's value)",
    "COL!=":        "COL!= (not equals another column's value)",
    "IS EMPTY":     "IS EMPTY (cell is blank)",
    "IS NOT EMPTY": "IS NOT EMPTY (cell has a value)",
}

RULE_TYPES: list[str]        = ["COLUMN", "ROW", "DUPLICATE"]
LOGICAL_OPERATORS: list[str] = ["AND", "OR"]


# ── Dataclass ─────────────────────────────────────────────────────────────────
@dataclass
class DynamicRule:
    id:             str        = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:           str        = "Unnamed Rule"
    rule_type:      str        = "COLUMN"       # "COLUMN" | "ROW"

    # Unified condition list — each entry:
    #   { column, operator, value, logical_operator }
    conditions:     list[dict] = field(default_factory=list)

    # For ROW rules: column whose cell is used as the error anchor.
    # Empty → use TAG NO column.
    target_column:  str        = ""

    error_message:  str        = "Validation failed"
    case_sensitive: bool       = False
    is_active:      bool       = True
    priority:       int        = 100
    source:         str        = "dynamic"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "DynamicRule":
        """Load from JSON; auto-converts old (column/operator/value) schema."""
        allowed = set(DynamicRule.__dataclass_fields__)
        clean: dict[str, Any] = {k: v for k, v in d.items() if k in allowed}

        # ── Backwards-compat: old format used top-level column/operator/value
        #    plus multi_conditions list.
        if not clean.get("conditions"):
            old_col = d.get("column", "")
            old_op  = d.get("operator", "==")
            old_val = d.get("value", "")
            conds: list[dict] = []
            if old_col:
                conds.append({
                    "column":           old_col,
                    "operator":         old_op,
                    "value":            old_val,
                    "logical_operator": "AND",
                })
            for mc in d.get("multi_conditions", []):
                conds.append({
                    "column":           mc.get("column", ""),
                    "operator":         mc.get("operator", "=="),
                    "value":            mc.get("value", ""),
                    "logical_operator": "AND",
                })
            clean["conditions"] = conds

        if "rule_type" not in clean:
            clean["rule_type"] = "COLUMN"
        if "target_column" not in clean:
            clean["target_column"] = ""

        return DynamicRule(**clean)


# ── Persistence ───────────────────────────────────────────────────────────────
def load_rules() -> list[DynamicRule]:
    """Load user-defined rules from RULES_FILE.  Returns [] if absent/corrupt."""
    if not RULES_FILE.exists():
        return []
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [DynamicRule.from_dict(r) for r in raw]
    except Exception:
        return []


def save_rules(rules: list[DynamicRule]) -> None:
    """Persist user-defined rules to RULES_FILE."""
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump([r.to_dict() for r in rules], f, indent=2, ensure_ascii=False)


def add_rule(rule: DynamicRule) -> list[DynamicRule]:
    rules = load_rules()
    rules.append(rule)
    save_rules(rules)
    return rules


def delete_rule(rule_id: str) -> list[DynamicRule]:
    rules = [r for r in load_rules() if r.id != rule_id]
    save_rules(rules)
    return rules


def update_rule(rule_id: str, **kwargs) -> list[DynamicRule]:
    rules = load_rules()
    for r in rules:
        if r.id == rule_id:
            for k, v in kwargs.items():
                if hasattr(r, k):
                    setattr(r, k, v)
    save_rules(rules)
    return rules


# ── Low-level helpers ─────────────────────────────────────────────────────────
def _norm(val: Any, case_sensitive: bool) -> str:
    s = "" if val is None else str(val).strip()
    return s if case_sensitive else s.upper()


def _to_num(val: Any) -> float | None:
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return None


def _is_truly_empty(val: Any) -> bool:
    if val is None:
        return True
    return str(val).strip() in ("", "nan", "NaN", "none", "None")


def _resolve_col(name: str, col_names: list[str]) -> str | None:
    """Case-insensitive column lookup; returns the actual column name or None."""
    target = name.strip().upper()
    return next((c for c in col_names if c.strip().upper() == target), None)


def _get_cell_address(col_names: list[str], col_name: str, row_idx: int) -> str:
    """Return Excel cell address (e.g. C5) for a column name and 1-based row."""
    from openpyxl.utils import get_column_letter
    match = _resolve_col(col_name, col_names)
    if match:
        ci = col_names.index(match) + 1
        return f"{get_column_letter(ci)}{row_idx}"
    return f"?{row_idx}"


# ── Single-condition evaluator ─────────────────────────────────────────────────
def _evaluate_condition(
    cell_val: Any,
    operator: str,
    target_val: str,
    case_sensitive: bool,
    row_series: pd.Series,
    col_names: list[str],
) -> bool:
    """
    Returns True when the condition is VIOLATED (error should be raised).
    """
    op = operator.strip().upper()

    # Presence checks (value irrelevant)
    if op == "IS EMPTY":
        return not _is_truly_empty(cell_val)   # violated when NOT empty
    if op == "IS NOT EMPTY":
        return _is_truly_empty(cell_val)        # violated when empty

    # Column-to-column comparison
    if op in ("COL==", "COL!="):
        other_col = _resolve_col(target_val, col_names)
        other_val = row_series.get(other_col, "") if other_col else ""
        a = _norm(cell_val, case_sensitive)
        b = _norm(other_val, case_sensitive)
        return (a != b) if op == "COL==" else (a == b)

    cv = _norm(cell_val, case_sensitive)
    tv = _norm(target_val, case_sensitive)

    if op == "==":           return cv != tv
    if op == "!=":           return cv == tv
    if op == "CONTAINS":     return tv not in cv
    if op == "NOT CONTAINS": return tv in cv
    if op == "IN":
        # IN: violated when the cell value is NOT in the allowed list
        allowed = {_norm(x.strip(), case_sensitive) for x in target_val.split(",")}
        return cv not in allowed
    if op == "NOT IN":
        # NOT IN: violated when the cell value IS in the forbidden list
        forbidden = {_norm(x.strip(), case_sensitive) for x in target_val.split(",")}
        return cv in forbidden

    # Numeric comparisons
    cn = _to_num(cell_val)
    tn = _to_num(target_val)
    if cn is None or tn is None:
        return False
    if op == ">":  return not (cn > tn)
    if op == "<":  return not (cn < tn)
    if op == ">=": return not (cn >= tn)
    if op == "<=": return not (cn <= tn)
    return False


# ── Rule evaluator ─────────────────────────────────────────────────────────────
def _evaluate_rule_on_row(
    rule: DynamicRule,
    row_series: pd.Series,
    col_names: list[str],
) -> bool:
    """
    Returns True when the rule is VIOLATED for this row.

    COLUMN rules  (semantics: "this cell is wrong")
        _evaluate_condition returns True when the cell value VIOLATES the
        condition (e.g. == expects X but got Y → violated=True).
        conditions[0] is the primary; the rest are chained with AND/OR.
        Empty cells in the primary column are skipped (Rule 1 covers them).

    ROW rules  (semantics: "all these conditions are true → error")
        Conditions are TRIGGER conditions — the rule fires when they are all
        satisfied.  _evaluate_condition returns True when VIOLATED (i.e. the
        cell does NOT match), so for ROW rules we invert: the condition is
        "satisfied" when _evaluate_condition returns False.
        AND/OR logic operates on the "satisfied" (not violated) result.
    """
    conds = rule.conditions
    if not conds:
        return False

    if rule.rule_type == "COLUMN":
        # Skip if primary column cell is empty (Rule 1 covers that)
        primary = conds[0]
        p_col   = _resolve_col(primary.get("column", ""), col_names)
        if not p_col:
            return False
        if _is_truly_empty(row_series.get(p_col, "")):
            return False

        # Evaluate conditions using AND/OR chain on "violated" semantics
        result: bool | None = None
        for cond in conds:
            col_name = _resolve_col(cond.get("column", ""), col_names)
            violated = False
            if col_name:
                cell_val = row_series.get(col_name, "")
                violated = _evaluate_condition(
                    cell_val,
                    cond.get("operator", "=="),
                    cond.get("value", ""),
                    rule.case_sensitive,
                    row_series,
                    col_names,
                )
            if result is None:
                result = violated
            else:
                logic = cond.get("logical_operator", "AND").upper()
                result = (result or violated) if logic == "OR" else (result and violated)
        return bool(result)

    else:  # ROW rule — fire when all trigger conditions are SATISFIED
        result = None
        for cond in conds:
            col_name = _resolve_col(cond.get("column", ""), col_names)
            if not col_name:
                # Column missing — treat as condition NOT satisfied
                satisfied = False
            else:
                cell_val = row_series.get(col_name, "")
                # For ROW rules, "satisfied" means _evaluate_condition returns
                # False (the cell does NOT violate the condition — it matches).
                satisfied = not _evaluate_condition(
                    cell_val,
                    cond.get("operator", "=="),
                    cond.get("value", ""),
                    rule.case_sensitive,
                    row_series,
                    col_names,
                )

            if result is None:
                result = satisfied
            else:
                logic = cond.get("logical_operator", "AND").upper()
                result = (result or satisfied) if logic == "OR" else (result and satisfied)

        return bool(result)


# ── Public API ────────────────────────────────────────────────────────────────
def run_dynamic_rules(
    df: pd.DataFrame,
    rules: list[DynamicRule],
    sno_col: str | None = None,
    tag_col: str | None = None,
) -> list[dict]:
    """
    Evaluate all active dynamic rules on every row of *df*.

    Returns list of error dicts matching the schema used by
    generate_iodb_validation:
        {row, sno, tag, column, cell, message, rule, rule_name, rule_type, source}
    where source = "dynamic".

    Rule types
        COLUMN   – per-row, single-column violation check
        ROW      – per-row, multi-column cross-field check (AND/OR)
        DUPLICATE– cross-row check; fires for every row where the target
                   column value appears more than once in the dataset
    """
    active = sorted(
        [r for r in rules if r.is_active],
        key=lambda r: r.priority,
    )
    if not active:
        return []

    col_names = list(df.columns)
    errors: list[dict] = []

    # ── Helper: resolve S.NO and TAG values for a row index ───────────────────
    def _row_meta(i: int) -> tuple[str, str]:
        row = df.iloc[i]
        sno_v = "UNKNOWN"
        tag_v = "UNKNOWN"
        if sno_col:
            rc = _resolve_col(sno_col, col_names)
            if rc:
                sv = row.get(rc, "")
                if not _is_truly_empty(sv):
                    try:
                        fsv   = float(sv)
                        sno_v = str(int(fsv)) if fsv.is_integer() else str(fsv)
                    except Exception:
                        sno_v = str(sv).strip()
        if tag_col:
            rc = _resolve_col(tag_col, col_names)
            if rc:
                tv = row.get(rc, "")
                if not _is_truly_empty(tv):
                    tag_v = str(tv).strip()
        return sno_v, tag_v

    # ── DUPLICATE rules — cross-row analysis ──────────────────────────────────
    from collections import Counter
    for rule in active:
        if rule.rule_type != "DUPLICATE" or not rule.conditions:
            continue

        dup_col_name = rule.conditions[0].get("column", "").strip()
        dup_col      = _resolve_col(dup_col_name, col_names)
        if not dup_col:
            continue

        # Count how many times each (normalised) value appears
        value_counts: Counter = Counter()
        for i in range(len(df)):
            val = df.iloc[i].get(dup_col, "")
            if _is_truly_empty(val):
                continue
            key = str(val).strip()
            if not rule.case_sensitive:
                key = key.upper()
            value_counts[key] += 1

        # Emit an error for every row whose value appears more than once
        for i in range(len(df)):
            val = df.iloc[i].get(dup_col, "")
            if _is_truly_empty(val):
                continue
            key = str(val).strip()
            if not rule.case_sensitive:
                key = key.upper()
            if value_counts[key] <= 1:
                continue

            row_idx       = int(df.index[i]) + 2
            sno_v, tag_v  = _row_meta(i)
            cell_addr     = _get_cell_address(col_names, dup_col_name, row_idx)
            errors.append({
                "row":       row_idx,
                "sno":       sno_v,
                "tag":       tag_v,
                "column":    dup_col,
                "cell":      cell_addr,
                "message":   rule.error_message,
                "rule":      f"D:{rule.id}",
                "rule_name": rule.name,
                "rule_type": "DUPLICATE",
                "source":    "dynamic",
            })

    # ── COLUMN and ROW rules — per-row evaluation ──────────────────────────────
    for i in range(len(df)):
        row_series = df.iloc[i]
        row_idx    = int(df.index[i]) + 2
        sno_v, tag_v = _row_meta(i)

        for rule in active:
            if rule.rule_type == "DUPLICATE":
                continue   # already handled above
            if not _evaluate_rule_on_row(rule, row_series, col_names):
                continue

            # Determine error-anchor column
            if rule.rule_type == "ROW":
                anchor_name = (
                    rule.target_column.strip()
                    if rule.target_column.strip()
                    else (tag_col or (col_names[0] if col_names else ""))
                )
            else:
                anchor_name = (
                    rule.conditions[0].get("column", "")
                    if rule.conditions
                    else ""
                )

            resolved_anchor = _resolve_col(anchor_name, col_names)
            display_col     = resolved_anchor or anchor_name
            cell_addr       = _get_cell_address(col_names, anchor_name, row_idx)

            errors.append({
                "row":       row_idx,
                "sno":       sno_v,
                "tag":       tag_v,
                "column":    display_col,
                "cell":      cell_addr,
                "message":   rule.error_message,
                "rule":      f"D:{rule.id}",
                "rule_name": rule.name,
                "rule_type": rule.rule_type,
                "source":    "dynamic",
            })

    return errors
