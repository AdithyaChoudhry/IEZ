"""
Instrument subtype classification for the Process Data Requisition generator.

The type matcher (process_data_matcher.match_tags) answers "is this row a Level Transmitter?". The subtype decides WHICH kind
of level transmitter (Non-Contact Radar, Guided Wave Radar, Ultrasonic ...). It is decided only from words the IODB actually
contains - an explicit subtype / technology column first, then the instrument type name and description - never from a tag
prefix (LT / LIT fit every technology) and never from a loose keyword ("radar" alone does not tell non-contact from guided wave).

A row whose wording does not establish its subtype is UNRESOLVED: it is not placed in any subtype. The engineer reviews it and
adds it explicitly.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# type key -> subtype -> aliases (whole-word, punctuation-insensitive). A subtype without aliases is never matched automatically.
SUBTYPE_RULES: dict = {
    "level_transmitter": {
        "Guided Wave Radar": ["GUIDED WAVE RADAR", "GUIDED RADAR", "GWR"],
        "Non-Contact Radar": ["NON CONTACT RADAR", "NONCONTACT RADAR", "CONTACTLESS RADAR", "NON CONTACTING RADAR"],
        "Ultrasonic": ["ULTRASONIC LEVEL", "ULTRASONIC LEVEL TRANSMITTER"],
        "DP Type (Open Tank)": ["DP LEVEL OPEN TANK", "DIFFERENTIAL PRESSURE LEVEL OPEN TANK", "DP TYPE OPEN TANK"],
        "DP Type (Pressurized Tank)": ["DP LEVEL PRESSURIZED TANK", "DIFFERENTIAL PRESSURE LEVEL PRESSURIZED TANK",
                                       "DP TYPE PRESSURIZED TANK", "DP LEVEL CLOSED TANK"],
    },
    "flow_transmitter": {
        "Magnetic": ["MAGNETIC FLOW", "ELECTROMAGNETIC", "ELECTRO MAGNETIC", "MAGNETIC FLOW METER"],
        "Coriolis": ["CORIOLIS"],
        "Vortex": ["VORTEX"],
        "Differential Pressure": ["DIFFERENTIAL PRESSURE FLOW", "DP TYPE FLOW", "DP FLOW"],
        "Thermal Mass": ["THERMAL MASS"],
        "Ultrasonic Clamp-On": ["ULTRASONIC CLAMP ON", "CLAMP ON ULTRASONIC", "ULTRASONIC CLAMPON"],
        "Ultrasonic Parshall Flume": ["PARSHALL FLUME", "PARSHALL"],
        "Open Channel": ["OPEN CHANNEL"],
        "Ultrasonic": ["ULTRASONIC FLOW"],
    },
    "pressure_transmitter": {
        "Differential Pressure": ["DIFFERENTIAL PRESSURE TRANSMITTER", "DIFFERENTIAL PRESSURE INDICATING TRANSMITTER", "DP TRANSMITTER"],
        "Standard": ["PRESSURE TRANSMITTER", "PRESSURE INDICATING TRANSMITTER", "GAUGE PRESSURE TRANSMITTER",
                     "ABSOLUTE PRESSURE TRANSMITTER"],
    },
    "temperature_transmitter": {
        "RTD": ["RTD", "PT100", "PT 100"],
        "Thermocouple": ["THERMOCOUPLE"],
    },
    "level_gauge": {
        "Magnetic": ["MAGNETIC LEVEL GAUGE", "MAGNETIC TYPE LEVEL GAUGE", "MAGNETIC TYPE"],
        "Reflex": ["REFLEX LEVEL GAUGE", "REFLEX TYPE LEVEL GAUGE", "REFLEX TYPE", "REFLEX"],
    },
    "pressure_gauge": {
        "Bourdon": ["BOURDON"],
        "Diaphragm Seal": ["DIAPHRAGM SEAL", "DIAPHRAGM"],
    },
}

# Technologies that are named in the IODB but have no subtype of their own in the Process Data configuration. Such a record is a
# known technology (not unresolved), it simply belongs to no listed subtype.
OTHER_TECH: dict = {
    "level_transmitter": {"Submersible": ["SUBMERSIBLE", "HYDROSTATIC"], "Capacitance": ["CAPACITANCE"]},
}

# Why a record of this family stays unresolved (shown to the engineer).
_HINTS = {
    "level_transmitter": [(r"\bRADAR\b", "Radar level transmitter: the wording does not say non-contact or guided wave radar."),
                          (r"\bDP\b|\bDIFFERENTIAL PRESSURE\b", "DP level transmitter: open or pressurized tank is not stated."),
                          (r".", "The level measurement technology is not stated.")],
    "flow_transmitter": [(r"\bULTRASONIC\b", "Ultrasonic flow transmitter: insertion, clamp-on or Parshall flume is not stated."),
                         (r".", "The flow measurement technology is not stated.")],
    "pressure_transmitter": [(r".", "Gauge or differential pressure is not stated.")],
    "temperature_transmitter": [(r".", "The sensor type (RTD / thermocouple) is not stated.")],
    "level_gauge": [(r".", "Magnetic or reflex type is not stated.")],
    "pressure_gauge": [(r".", "Bourdon or diaphragm-seal type is not stated.")],
}

# IODB columns that can state the subtype explicitly (highest priority), then the descriptive ones. Compared without spaces / case.
_EXPLICIT_COLUMNS = ("INSTRUMENT SUBTYPE", "SUBTYPE", "SUB TYPE", "INSTRUMENT SUB TYPE", "TECHNOLOGY", "MEASURING PRINCIPLE",
                     "SENSOR TYPE", "FLOW METER TYPE", "LEVEL TRANSMITTER TYPE", "GAUGE TYPE", "SERVICE TYPE")
_DESCRIPTIVE_COLUMNS = ("INSTRUMENT MEASURING TYPE", "INSTRUMENT TYPE NAME", "EQUIPMENT DESCRIPTION", "SIGNAL DESCRIPTION")


def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text if text is not None else "").lower()).strip()


_COMPILED: dict = {}


def _pattern(alias: str):
    p = _COMPILED.get(alias)
    if p is None:
        p = _COMPILED[alias] = re.compile(r"(?<![a-z0-9])" + re.escape(_norm(alias)) + r"(?![a-z0-9])")
    return p


def has_rules(type_key: str) -> bool:
    return type_key in SUBTYPE_RULES


def subtype_columns(columns) -> dict:
    """Which IODB columns hold subtype evidence: {'explicit': [actual headers], 'descriptive': [actual headers]} in priority order."""
    key = {re.sub(r"[^A-Z0-9]", "", str(c).upper()): c for c in columns}

    def find(names):
        out = []
        for n in names:
            actual = key.get(re.sub(r"[^A-Z0-9]", "", n))
            if actual is not None and actual not in out:
                out.append(actual)
        return out
    return {"explicit": find(_EXPLICIT_COLUMNS), "descriptive": find(_DESCRIPTIVE_COLUMNS)}


def _matches(text: str, rules: dict) -> list:
    """[(subtype, alias)] of the aliases found in a normalised text."""
    return [(sub, a) for sub, aliases in rules.items() for a in aliases if _pattern(a).search(text)]


def _dominant(found: list) -> set:
    """Subtypes left after dropping the matches that are only part of a longer alias of another subtype
    ('PRESSURE TRANSMITTER' inside 'DIFFERENTIAL PRESSURE TRANSMITTER')."""
    keep = set()
    for sub, a in found:
        na = _norm(a)
        if not any(sub2 != sub and na != _norm(a2) and na in _norm(a2) for sub2, a2 in found):
            keep.add(sub)
    return keep


def classify(type_key: str, values: dict, cols: dict) -> dict:
    """
    -> {"subtype": str | None, "reason": str, "evidence": str}.  `values` maps IODB column -> cell value for one row,
    `cols` is subtype_columns() of the IODB. subtype None = unresolved (reason says why).
    """
    rules = SUBTYPE_RULES.get(type_key)
    if not rules:
        return {"subtype": "", "reason": "", "evidence": ""}
    for column in cols["explicit"] + cols["descriptive"]:
        text = _norm(values.get(column))
        if not text:
            continue
        for sub in rules:                                   # a subtype column holding exactly the subtype's name
            if text == _norm(sub):
                return {"subtype": sub, "reason": "", "evidence": f"{column}: {values.get(column)}"}
        subs = _dominant(_matches(text, rules))
        if not subs:
            for other, aliases in OTHER_TECH.get(type_key, {}).items():
                if any(_pattern(a).search(text) for a in aliases):
                    return {"subtype": "", "other": other, "reason": "", "evidence": f"{column}: {values.get(column)}"}
        if len(subs) == 1:
            return {"subtype": next(iter(subs)), "reason": "", "evidence": f"{column}: {values.get(column)}"}
        if len(subs) > 1:
            return {"subtype": None, "reason": f"{column} names more than one subtype ({', '.join(sorted(subs))}).", "evidence": ""}
    joined = " ".join(_norm(values.get(c)) for c in cols["explicit"] + cols["descriptive"]).upper()
    for rx, why in _HINTS.get(type_key, [(r".", "The subtype is not stated.")]):
        if re.search(rx, joined):
            return {"subtype": None, "reason": why, "evidence": ""}
    return {"subtype": None, "reason": "The subtype is not stated.", "evidence": ""}
