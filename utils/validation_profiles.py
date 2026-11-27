"""
Configurable IODB validation rules.

The built-in rules stay in utils.generators.generate_iodb_validation. A profile only stores what differs from the built-in
default (enable / disable, severity, message, extra applicability conditions, exceptions and a few rule values), as plain
data: field names, operators from the list below and text values. Nothing in a profile is ever executed as code.
"""
from __future__ import annotations

import fnmatch
import math
import re
from typing import Any, Optional

DEFAULT_PROFILE_NAME = "iEZ Default Validation Rules"
SEVERITIES = ("error", "warning", "information")

OPERATORS = {          # key -> (label, needs a value)
    "equals": ("Equals", True), "not_equals": ("Does not equal", True),
    "contains": ("Contains", True), "not_contains": ("Does not contain", True),
    "starts_with": ("Starts with", True), "ends_with": ("Ends with", True),
    "is_blank": ("Is blank", False), "is_not_blank": ("Is not blank", False),
    "one_of": ("Is one of (comma separated)", True), "not_one_of": ("Is not one of (comma separated)", True),
    "gt": ("Greater than", True), "lt": ("Less than", True),
    "gte": ("Greater than or equal to", True), "lte": ("Less than or equal to", True),
    "matches": ("Matches pattern (* and ?)", True), "equals_field": ("Equals another field", True),
}
_NUMERIC = {"gt", "lt", "gte", "lte"}


def _p(name: str, label: str, kind: str, default: Any) -> dict:
    return {"name": name, "label": label, "type": kind, "default": default}


def _rule(rid, name, category, description, params=(), note=""):
    return {"id": rid, "name": name, "category": category, "description": description, "params": list(params), "note": note,
            "default_severity": "error"}


TAG_NAMES = {   # TAG NO keyword -> expected INSTRUMENT NAME
    "DFIT": "DIFFERENTIAL FLOW INDICATING TRANSMITTER", "DPIT": "DIFFERENTIAL PRESSURE INDICATING TRANSMITTER",
    "DLIT": "DIFFERENTIAL LEVEL INDICATING TRANSMITTER", "FIT": "FLOW INDICATING TRANSMITTER",
    "LIT": "LEVEL INDICATING TRANSMITTER", "TIT": "TEMPERATURE INDICATING TRANSMITTER",
    "PIT": "PRESSURE INDICATING TRANSMITTER", "AIT": "ANALYZER INDICATING TRANSMITTER",
    "DPG": "DIFFERENTIAL PRESSURE GAUGE", "LG": "LEVEL GAUGE", "FG": "FLOW GAUGE", "PG": "PRESSURE GAUGE", "TG": "TEMPERATURE GAUGE",
}

RULES: list[dict] = [
    _rule("1", "Empty Cell Validation", "Data Completeness", "All cells must be filled; STATUS and REMARKS are excluded.",
          note="Runs only when 'Validate empty cells' is ticked."),
    _rule("2", "Area Classification vs IS/NIS Type", "Electrical Information", "Hazardous area requires IS; safe area requires NIS.",
          [_p("hazardous_area", "Hazardous area value", "text", "HAZARDOUS"), _p("hazardous_type", "Type required in it", "text", "IS"),
           _p("safe_area", "Safe area value", "text", "SAFE AREA"), _p("safe_type", "Type required in it", "text", "NIS")]),
    _rule("3", "Scope of Supply vs Vendor Package", "Document Information", "Scope other than the own scope must name the Vendor Package.",
          [_p("own_scope", "Scope values needing no vendor package", "list", ["WABAG"])]),
    _rule("4", "TAG keyword vs Instrument Name", "Instrument Identification", "TAG NO keyword must match the Instrument Name.",
          [_p("tag_names", "TAG keyword = Instrument name (one per line)", "map", TAG_NAMES)]),
    _rule("4B", "TAG NO Capitalisation", "Instrument Identification", "TAG NO must be fully uppercase."),
    _rule("5", "Power Supply vs Wire Type", "Electrical Information", "A power supply other than 24V DC must be 4-wire.",
          [_p("loop_power", "Power supply values that need no check ('-' allowed)", "list", ["24V DC", "-"]),
           _p("external_wire", "Wire type required otherwise", "list", ["4 WIRE - EXT POWER"])]),
    _rule("6", "AJB/DJB Signal Routing", "Junction Box",
          "Applicable I/O signals shall comply with the AJB/DJB routing requirements: AI to AJB; DI and DO to DJB. Records with IO "
          "TYPE marked as '-' are exempt from this signal-routing validation.",
          [_p("exempt_io", "IO TYPE values exempt from routing", "list", ["-"]),
           _p("ai_jb", "Junction box text / pattern for AI", "list", ["AJB"]),
           _p("ao_jb", "Junction box text / pattern for AO (empty = not checked)", "list", []),
           _p("di_jb", "Junction box text / pattern for DI", "list", ["DJB"]),
           _p("do_jb", "Junction box text / pattern for DO", "list", ["DJB"]),
           _p("direct_subsystems", "SUB SYSTEM values that are routed through a junction box ('-' and blank)", "list", ["-"])],
          note="Records whose SUB SYSTEM is any other value are routed through that sub-system and are not checked."),
    _rule("7", "Calibration vs Instrument Range", "Process Information", "Calibration maximum must not exceed the instrument range maximum."),
    _rule("8", "Unit Consistency", "Engineering Units", "Calibration unit must match the instrument range unit."),
    _rule("9", "Fail Action", "I/O Signals", "Fail action must be one of the allowed values.",
          [_p("allowed", "Allowed fail actions", "list", ["FO", "FC", "LAST POS", "-", "NA", "N/A", "FAIL OPEN", "FAIL CLOSE"])]),
    _rule("10", "Alarm Setpoint Order", "Process Information", "LL < L < H < HH."),
    _rule("11", "S.NO Ascending Order", "Data Completeness", "S.NO must be strictly ascending."),
    _rule("12", "Spelling Check", "Document Information", "Free-text columns are checked for misspellings.",
          note="Runs only when 'Auto-correct spelling' is ticked."),
]
BY_ID = {r["id"]: r for r in RULES}

PROTECTED_CHECKS = [
    "The file must be a readable Excel workbook (.xlsx / .xls).",
    "The first worksheet must have a header row that can be parsed.",
    "Only signed-in users can run validation; only Lead Engineer, Reviewer or Admin can change profiles.",
    "A profile applies only to its own project, and an invalid or unavailable profile stops the validation.",
]


class ProfileError(ValueError):
    """A problem with a rule configuration that the user can correct."""


def _text(v: Any) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return str(v).strip()


# ── checking a configuration ─────────────────────────────────────────────────
def _condition(c: Any, where: str) -> dict:
    if not isinstance(c, dict):
        raise ProfileError(f"{where}: a condition must have a field, an operator and a value.")
    field, op, value = _text(c.get("field")), _text(c.get("operator")), _text(c.get("value"))
    if not field:
        raise ProfileError(f"{where}: choose the IODB field of the condition.")
    if op not in OPERATORS:
        raise ProfileError(f"{where}: '{op}' is not a supported condition.")
    if OPERATORS[op][1] and not value:
        raise ProfileError(f"{where}: '{OPERATORS[op][0]}' needs a value.")
    if op in _NUMERIC:
        try:
            float(value)
        except ValueError:
            raise ProfileError(f"{where}: '{OPERATORS[op][0]}' needs a number, not '{value}'.")
    if max(len(field), len(value)) > 300:
        raise ProfileError(f"{where}: the condition text is too long.")
    return {"field": field, "operator": op, "value": value if OPERATORS[op][1] else ""}


def _param(spec: dict, value: Any, where: str) -> Any:
    kind = spec["type"]
    if kind == "text":
        v = _text(value)
        if not v or len(v) > 200:
            raise ProfileError(f"{where}: enter a value for '{spec['label']}'.")
        return v
    if kind == "list":
        if not isinstance(value, list) or len(value) > 100:
            raise ProfileError(f"{where}: '{spec['label']}' must be a list of values.")
        out = [_text(x) for x in value if _text(x)]
        if any(len(x) > 100 for x in out):
            raise ProfileError(f"{where}: a value in '{spec['label']}' is too long.")
        if not out and spec["default"]:
            raise ProfileError(f"{where}: '{spec['label']}' needs at least one value (disable the rule instead).")
        return out
    if not isinstance(value, dict) or not value or len(value) > 200:
        raise ProfileError(f"{where}: '{spec['label']}' needs 'keyword = name' lines.")
    out = {_text(k).upper(): _text(v).upper() for k, v in value.items() if _text(k) and _text(v)}
    if not out or any(len(k) > 40 or len(v) > 200 for k, v in out.items()):
        raise ProfileError(f"{where}: '{spec['label']}' needs 'keyword = name' lines.")
    return out


def clean_config(raw: Any) -> dict:
    """The validated configuration, holding only what differs from the default rules. Raises ProfileError."""
    if raw in (None, ""):
        return {"rules": {}}
    if not isinstance(raw, dict) or not isinstance(raw.get("rules", {}), dict):
        raise ProfileError("The rule configuration is not in the expected form.")
    out: dict = {}
    for rid, o in raw.get("rules", {}).items():
        rule = BY_ID.get(str(rid))
        if rule is None:
            raise ProfileError(f"Unknown validation rule '{rid}'.")
        if not isinstance(o, dict):
            raise ProfileError(f"{rule['name']}: the rule settings are not in the expected form.")
        unknown = set(o) - {"enabled", "severity", "message", "apply_when", "exceptions", "params"}
        if unknown:
            raise ProfileError(f"{rule['name']}: unknown setting(s) {', '.join(sorted(unknown))}.")
        keep: dict = {}
        if "enabled" in o:
            if not isinstance(o["enabled"], bool):
                raise ProfileError(f"{rule['name']}: 'enabled' must be on or off.")
            if not o["enabled"]:
                keep["enabled"] = False
        sev = _text(o.get("severity")).lower()
        if sev:
            if sev not in SEVERITIES:
                raise ProfileError(f"{rule['name']}: severity must be Error, Warning or Information.")
            if sev != rule["default_severity"]:
                keep["severity"] = sev
        msg = _text(o.get("message"))
        if msg:
            if len(msg) > 500:
                raise ProfileError(f"{rule['name']}: the message is longer than 500 characters.")
            keep["message"] = msg
        group = o.get("apply_when") or {}
        if not isinstance(group, dict):
            raise ProfileError(f"{rule['name']}: the applicability is not in the expected form.")
        conds = group.get("conditions") or []
        if conds:
            match = _text(group.get("match")).lower() or "all"
            if match not in ("all", "any") or not isinstance(conds, list) or len(conds) > 20:
                raise ProfileError(f"{rule['name']}: combine up to 20 applicability conditions with AND or OR.")
            keep["apply_when"] = {"match": match, "conditions": [_condition(c, f"{rule['name']} applicability") for c in conds]}
        exc = o.get("exceptions") or []
        if exc:
            if not isinstance(exc, list) or len(exc) > 20:
                raise ProfileError(f"{rule['name']}: up to 20 exceptions are supported.")
            keep["exceptions"] = [_condition(c, f"{rule['name']} exception") for c in exc]
        params = o.get("params") or {}
        if not isinstance(params, dict):
            raise ProfileError(f"{rule['name']}: the rule values are not in the expected form.")
        specs = {s["name"]: s for s in rule["params"]}
        changed = {}
        for name, value in params.items():
            if name not in specs:
                raise ProfileError(f"{rule['name']}: unknown rule value '{name}'.")
            v = _param(specs[name], value, rule["name"])
            if v != specs[name]["default"]:
                changed[name] = v
        if changed:
            keep["params"] = changed
        if keep:
            out[rule["id"]] = keep
    return {"rules": out}


def matches_pattern(text: str, patterns: list[str]) -> bool:
    """A pattern with * or ? is a wildcard for the whole value; any other text must be contained in the value."""
    t = text.upper()
    return any(fnmatch.fnmatchcase(t, p.upper()) if ("*" in p or "?" in p) else p.upper() in t for p in patterns)


# ── applying a profile while validating ──────────────────────────────────────
class Profile:
    def __init__(self, config: Optional[dict] = None, name: str = DEFAULT_PROFILE_NAME, version: Any = "default",
                 custom: bool = False):
        self.config = clean_config(config)
        self.name, self.version, self.custom = name, version, custom

    def _o(self, rid) -> dict:
        return self.config["rules"].get(str(rid), {})

    def enabled(self, rid) -> bool:
        return self._o(rid).get("enabled", True)

    def param(self, rid, name):
        over = self._o(rid).get("params", {})
        if name in over:
            return over[name]
        return next(s["default"] for s in BY_ID[str(rid)]["params"] if s["name"] == name)

    @property
    def modified(self) -> list[str]:
        return [r["id"] for r in RULES if r["id"] in self.config["rules"]]

    @property
    def disabled(self) -> list[str]:
        return [r["id"] for r in RULES if not self.enabled(r["id"])]

    def check_fields(self, columns: list[str]) -> None:
        """Every field named by a condition must exist in this IODB; nothing falls back silently."""
        known = {str(c).strip().upper() for c in columns}
        for rid, o in self.config["rules"].items():
            conds = list(o.get("apply_when", {}).get("conditions", [])) + list(o.get("exceptions", []))
            for c in conds:
                names = [c["field"]] + ([c["value"]] if c["operator"] == "equals_field" else [])
                for n in names:
                    if n.upper() not in known:
                        raise ProfileError(f"Rule '{BY_ID[rid]['name']}' uses the field '{n}', which this IODB does not have.")

    def applies(self, rid, record: dict) -> bool:
        """`record`: upper-case column name -> cell value. False when the profile's own conditions exempt the record."""
        o = self._o(rid)
        group = o.get("apply_when")
        if group:
            hits = [evaluate(c, record) for c in group["conditions"]]
            if not (all(hits) if group["match"] == "all" else any(hits)):
                return False
        return not any(evaluate(c, record) for c in o.get("exceptions", []))

    def severity(self, rid) -> str:
        return self._o(rid).get("severity") or "error"

    def message(self, rid, default: str) -> str:
        return self._o(rid).get("message") or default

    def info(self) -> dict:
        return {"name": self.name, "version": str(self.version), "custom": self.custom,
                "enabled_rules": len(RULES) - len(self.disabled), "disabled_rules": len(self.disabled),
                "modified_rules": len(self.modified),
                "disabled": [BY_ID[r]["name"] for r in self.disabled], "modified": [BY_ID[r]["name"] for r in self.modified]}


def evaluate(c: dict, record: dict) -> bool:
    actual = _text(record.get(c["field"].upper()))
    op, value = c["operator"], c["value"]
    a, v = actual.upper(), value.upper()
    if op == "is_blank":
        return a == ""
    if op == "is_not_blank":
        return a != ""
    if op == "equals":
        return a == v
    if op == "not_equals":
        return a != v
    if op == "contains":
        return v in a
    if op == "not_contains":
        return v not in a
    if op == "starts_with":
        return a.startswith(v)
    if op == "ends_with":
        return a.endswith(v)
    if op in ("one_of", "not_one_of"):
        found = a in {x.strip() for x in v.split(",")}
        return found if op == "one_of" else not found
    if op == "matches":
        return fnmatch.fnmatchcase(a, v)
    if op == "equals_field":
        return a == _text(record.get(v)).upper()
    try:
        x, y = float(re.sub(r",", "", actual)), float(value)
    except ValueError:
        return False                                   # a blank or non-numeric cell satisfies no numeric comparison
    return {"gt": x > y, "lt": x < y, "gte": x >= y, "lte": x <= y}[op]
