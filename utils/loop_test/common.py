"""Shared helpers: header/tag normalisation and the source-provenance vocabulary."""
from __future__ import annotations

import re
from typing import Any

IODB, IO, USER = "IODB", "I/O ASSIGNMENT", "USER CONFIGURATION"
PLACEHOLDERS = {"", "-", "--", "NA", "N/A", "NIL", "NONE", "TBA", "NAN", "NULL"}


def norm_header(value: Any) -> str:
    """Header comparison key: upper case, any punctuation/line break -> single space."""
    text = str(value).upper().replace("+", " PLUS ")
    text = re.sub(r"(?<=\s)-(?=\s|$)", " MINUS ", text)
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def clean(value: Any) -> str:
    """Cell -> trimmed single-line text; '' for blanks and spreadsheet error values."""
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:
            return ""
        if value.is_integer():
            value = int(value)
    text = re.sub(r"\s+", " ", str(value).replace(" ", " ")).strip()
    return "" if text.upper() in {"#REF!", "#N/A", "#VALUE!", "#NAME?", "#DIV/0!"} else text


def is_value(text: str) -> bool:
    """True when the text is real data (not blank / '-' / TBA / NA ...)."""
    return clean(text).upper() not in PLACEHOLDERS


def norm_tag(tag: Any) -> str:
    """
    Safe tag normalisation for the 'normalised' match step: case, whitespace, dash look-alikes and
    spaces around dashes. Letters/digits (e.g. a trailing 'A') are never altered or dropped.
    """
    t = clean(tag).upper()
    t = re.sub(r"[‐-―−]", "-", t)
    t = re.sub(r"\s*-\s*", "-", t)
    return re.sub(r"\s+", "", t)


def field(value: Any, source: str) -> dict:
    return {"value": clean(value), "source": source}
