"""
datasheet_eligibility.py - which IODB records are physical instruments that get a datasheet (Smart Datasheet Generator only).

The one rule used by instrument-type discovery, the counts, the tag list, validation, generation and the tag-wise annexure:

    SIGNAL I/O TYPE contains SOFT                         never (a software signal is not a device), whatever its type or tag
    transmitter / switch / other field instrument         AI, DI, DO
    control valve / actuator                              AI, AO, DI, DO
    mechanical gauge                                      "-" or blank (no electrical signal)
    local indicator                                       "-" or blank, or a hardwired AI, DI, DO (e.g. loop powered)
    primary element (orifice, RTD element ...)            "-", blank, AI, DI, DO
    anything else (unknown signal text)                   never
    a record without a real tag number ("_", "-", TBA)    never

The category comes from the INSTRUMENT TYPE in the IODB, never from the tag number (a physical level alarm switch tagged LAH with a DI
is a switch). A MEASURING TYPE column, when the IODB has one, is part of the instrument type, so different technologies are never mixed.
One physical instrument = one tag number (prefixes, suffixes, hyphens and leading zeros are kept). The IODB is only read: its rows are
never changed, and the shared IODB reader and the other generators are not affected.
"""
from __future__ import annotations

import re
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from .datasheet_library import _clean, is_instrument_type, match_type, norm_type, type_tokens
from .sop_datasheet import IODB_NAME_KEYS, IODB_SIGNAL_KEYS, IODB_TAG_KEYS, IODB_TYPE_KEYS, _find_column

_DESC_KEYS = ("instrument description", "instrument_description", "description", "instr description")
_SIGNALS = frozenset({"AI", "DI", "DO"})
_NO_SIGNAL = frozenset({"-", ""})
ALLOWED: dict[str, frozenset] = {
    "transmitter": _SIGNALS, "switch": _SIGNALS, "instrument": _SIGNALS, "actuator": _SIGNALS | {"AO"},
    "gauge": _NO_SIGNAL, "local indicator": _NO_SIGNAL | _SIGNALS, "primary element": _NO_SIGNAL | _SIGNALS,
}
_ACTUATOR_WORDS = {"valve", "valves", "actuator", "mov", "damper", "gate"}
_SIGNAL_POINT_WORDS = {"command", "cmd", "feedback", "status", "alarm", "alarms", "indication", "fault", "permissive", "trip", "ready", "running"}
_GAUGE_WORDS = {"gauge", "glass", "manometer", "thermometer"}
_INDICATOR_WORDS = {"indicator", "indicatoe", "rotameter", "rota"}
_ELEMENT_WORDS = {"element", "orifice", "thermocouple", "rtd", "thermowell", "venturi", "flume"}
_TEMPLATE_CATEGORY = (("pg_", "gauge"), ("tg", "gauge"), ("lg_", "gauge"), ("fi_", "local indicator"), ("ps", "switch"),
                      ("dps", "switch"), ("fs", "switch"), ("fe_", "primary element"), ("te_", "primary element"))
_NOT_A_MEASURING_TYPE = {"", "-", "--", "na", "n/a", "tba", "tbd"}
NOT_IN_IODB = "the tag is not in the IODB"


def normalize_io(value: Any) -> str:
    """AI / AO / DI / DO / SOFT / "-" / "" (blank cell); any other text is returned upper-cased and is eligible nowhere."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip().upper()
    if text in ("", "NAN", "NONE", "NULL"):
        return ""
    if re.fullmatch(r"[-–—]+", text):
        return "-"
    if re.search(r"\bSOFT\b", text):                      # SOFT, "SOFT IO", "SOFT AI": a software signal
        return "SOFT"
    return text


def category(instrument_type: str) -> str:
    words = type_tokens(instrument_type) | set(norm_type(instrument_type).replace("/", " ").split())
    if "transmitter" in words:
        return "transmitter"
    if words & {"switch", "swtich"}:
        return "switch"
    if words & _ACTUATOR_WORDS:
        return "actuator"
    if words & _GAUGE_WORDS:
        return "gauge"
    if words & _INDICATOR_WORDS:
        return "local indicator"
    if words & _ELEMENT_WORDS:
        return "primary element"
    template = match_type(instrument_type).get("template_id") or ""          # a bare code such as "PG" or "TI"
    for prefix, cat in _TEMPLATE_CATEGORY:
        if template == prefix or (prefix.endswith("_") and template.startswith(prefix)):
            return cat
    return "instrument"


def type_key(label: str) -> str:
    """Spelling-insensitive identity of an instrument type: capitals, spaces and hyphens do not make a new type."""
    return norm_type(label)


def tag_key(tag: Any) -> str:
    return _clean(tag).casefold()


def is_real_tag(tag: str) -> bool:
    """False for an empty or placeholder tag ("_", "-", "TBA", "NA", "SPARE"): it identifies no instrument."""
    return bool(re.search(r"[A-Za-z0-9]", tag)) and not re.fullmatch(r"(?i)\s*(tba|tbd|na|n/a|nil|none|spare)\s*", tag)


def columns_of(df: pd.DataFrame) -> dict:
    cols = {"tag": _find_column(df, IODB_TAG_KEYS), "type": _find_column(df, IODB_TYPE_KEYS), "name": _find_column(df, IODB_NAME_KEYS),
            "description": _find_column(df, _DESC_KEYS), "signal": _find_column(df, IODB_SIGNAL_KEYS), "measuring": None, "status": None}
    for c in df.columns:
        n = re.sub(r"[^a-z]+", " ", str(c).lower()).strip()
        if cols["measuring"] is None and ("measuring type" in n or "measuring principle" in n):
            cols["measuring"] = c
        if cols["status"] is None and n in ("status", "tag status"):
            cols["status"] = c
    return cols


@dataclass
class Row:
    position: int
    tag: str
    io: str
    deleted: bool


@dataclass
class Group:
    key: str
    field_instrument: bool                   # offered in the library (motors, valves, commands and soft types are not)
    category: str
    spellings: Counter = field(default_factory=Counter)
    descriptions: Counter = field(default_factory=Counter)
    matched_on_description: bool = False
    records: int = 0
    soft: int = 0
    no_tag: int = 0                                                                # records with a placeholder instead of a tag
    not_applicable: Counter = field(default_factory=Counter)                       # I/O value -> records
    eligible: "OrderedDict[str, list]" = field(default_factory=OrderedDict)        # tag key -> eligible rows, preferred first
    all_tags: set = field(default_factory=set)

    @property
    def label(self) -> str:
        return self.spellings.most_common(1)[0][0]

    @property
    def eligible_tags(self) -> list:
        return sorted(rows[0].tag for rows in self.eligible.values())

    @property
    def can_have_datasheet(self) -> bool:
        """A field instrument, or physical valve / actuator equipment (incl. its positioner); never a command, status or alarm point."""
        if self.field_instrument:
            return True
        words = set(self.key.replace("/", " ").split())
        return bool(words & _ACTUATOR_WORDS) and not words & _SIGNAL_POINT_WORDS

    def diagnostics(self) -> dict:
        eligible_records = sum(len(r) for r in self.eligible.values())
        return {"records": self.records, "soft_excluded": self.soft, "not_applicable_excluded": sum(self.not_applicable.values()),
                "no_tag_excluded": self.no_tag,
                "not_applicable_by_io": {k or "(blank)": v for k, v in sorted(self.not_applicable.items())},
                "duplicates_excluded": eligible_records - len(self.eligible), "eligible": len(self.eligible)}


@dataclass
class Index:
    columns: dict
    groups: "OrderedDict[str, Group]"
    tags: dict                                # tag key -> [(group key | "", io)] of every row of that tag

    def other_types(self, tag: str, group_key: str) -> list:
        return [g.label for k, g in self.groups.items() if k != group_key and tag in g.eligible and g.can_have_datasheet]


def build_index(df: pd.DataFrame) -> Index:
    cols = columns_of(df)
    groups: "OrderedDict[str, Group]" = OrderedDict()
    tags: dict = {}
    if not cols["tag"]:
        return Index(cols, groups, tags)
    values = {k: (df[c].tolist() if c is not None else None) for k, c in cols.items()}
    pick = lambda k, i: _clean(values[k][i]) if values[k] is not None and not _blank(values[k][i]) else ""
    for i in range(len(df)):
        tag = pick("tag", i)
        if not tag:
            continue
        io = normalize_io(values["signal"][i]) if values["signal"] is not None else ""
        base = pick("type", i)
        desc = " ".join(x for x in (pick("name", i), pick("description", i)) if x)
        if not (base or desc):
            tags.setdefault(tag_key(tag), []).append(("", io))
            continue
        label = base or desc
        measuring = pick("measuring", i)
        if base and measuring.lower() not in _NOT_A_MEASURING_TYPE and norm_type(measuring) not in norm_type(base):
            label = f"{base} - {measuring}"
        key = type_key(label)
        g = groups.get(key)
        if g is None:
            g = groups[key] = Group(key, is_instrument_type(base or desc), category(base or desc))
        g.spellings[label] += 1
        g.matched_on_description = g.matched_on_description or not base
        if desc:
            g.descriptions[desc] += 1
        g.records += 1
        k = tag_key(tag)
        g.all_tags.add(k)
        tags.setdefault(k, []).append((key, io))
        if io == "SOFT":
            g.soft += 1
        elif not is_real_tag(tag):
            g.no_tag += 1
        elif io not in ALLOWED[g.category]:
            g.not_applicable[io] += 1
        else:
            deleted = pick("status", i).upper().startswith("DELETE")
            rows = g.eligible.setdefault(k, [])
            rows.append(Row(i, tag, io, deleted))
            rows.sort(key=lambda r: (r.deleted, r.position))                  # a live row is preferred to a deleted one
    return Index(cols, groups, tags)


def _blank(value: Any) -> bool:
    return value is None or (not isinstance(value, str) and pd.isna(value))


def _selected_groups(index: Index, instrument_type: str) -> list:
    if instrument_type:
        g = index.groups.get(type_key(instrument_type))
        return [g] if g is not None and g.can_have_datasheet else []
    return [g for g in index.groups.values() if g.can_have_datasheet]


def eligible_frame(df: pd.DataFrame, instrument_type: str = "") -> pd.DataFrame:
    """
    A COPY of the IODB holding only the eligible rows of `instrument_type` ("" = of any instrument type), the preferred row of each tag
    first, with the tag written exactly as it is listed. Everything built from it (validation, datasheet, annexure) sees eligible
    instruments only.
    """
    index = build_index(df)
    positions, spelled = [], []
    for g in _selected_groups(index, instrument_type):
        for rows in g.eligible.values():
            for r in rows:
                positions.append(r.position)
                spelled.append(rows[0].tag)
    out = df.iloc[positions].copy()
    if index.columns["tag"] is not None:
        out[index.columns["tag"]] = pd.Series(spelled, index=out.index, dtype=object)
    return out.reset_index(drop=True)


def check_selection(df: pd.DataFrame, selected_tags: list, instrument_type: str = "") -> list:
    """[{"tag", "reason"}] for every selected tag that may NOT have a datasheet of `instrument_type`; empty = the selection is valid."""
    index = build_index(df)
    wanted = _selected_groups(index, instrument_type)
    allowed = set().union(*(g.eligible.keys() for g in wanted)) if wanted else set()
    out = []
    for tag in selected_tags:
        if tag_key(tag) not in allowed:
            out.append({"tag": str(tag), "reason": _why(index, tag_key(tag), instrument_type)})
    return out


def reason_for(df: pd.DataFrame, tag: str, instrument_type: str = "") -> str:
    return _why(build_index(df), tag_key(tag), instrument_type)


def _why(index: Index, tag: str, instrument_type: str) -> str:
    rows = index.tags.get(tag)
    if not rows:
        return NOT_IN_IODB
    if not is_real_tag(tag):
        return "it is a placeholder, not a tag number"
    if all(io == "SOFT" for _, io in rows):
        return "SOFT signal - a software signal is not a physical instrument"
    wanted = type_key(instrument_type) if instrument_type else ""
    if wanted and not any(k == wanted for k, _ in rows):
        other = next((index.groups[k].label for k, _ in rows if k in index.groups), "")
        return f"it is not of the instrument type '{instrument_type}'" + (f" (the IODB type is '{other}')" if other else "")
    for k, io in rows:
        g = index.groups.get(k)
        if g is None or (wanted and k != wanted) or io == "SOFT":
            continue
        if not g.can_have_datasheet:
            return f"'{g.label}' is not a field instrument"
        if io not in ALLOWED[g.category]:
            return f"I/O type '{io or '(blank)'}' is not applicable to a {g.category}"
    return "it is not an eligible physical instrument of the selected type"


def ineligible_message(problems: list, limit: int = 8) -> str:
    shown = "; ".join(f"{p['tag']}: {p['reason']}" for p in problems[:limit])
    more = f"; and {len(problems) - limit} more" if len(problems) > limit else ""
    return (f"{len(problems)} selected tag(s) cannot have a datasheet for this instrument type - {shown}{more}. "
            "Analyse the IODB again and select the tags from the list.")
