# _types.py
from dataclasses import dataclass
from enum import Enum

class FieldType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    DROPDOWN = "dropdown"
    BOOLEAN = "boolean"

@dataclass(frozen=True)
class ProcessField:
    name: str
    unit: str = ""
    field_type: FieldType = FieldType.TEXT
    mandatory: bool = False
    options: tuple = ()
    iodb_aliases: tuple = ()
    subtype_only: tuple = ()

@dataclass(frozen=True)
class InstrumentTypeConfig:
    key: str
    label: str
    category: str
    match_aliases: tuple
    tag_prefixes: tuple = ()
    subtypes: tuple = ()
    subtype_field_name: str = ""
    fields: tuple = ()
    is_custom: bool = False
