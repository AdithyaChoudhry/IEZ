"""Process Data Requirement Library.

One InstrumentTypeConfig per instrument type (aliases, fields, units, data types,
mandatory flags). Adding a new instrument type normally means adding one config to a
module in process_data_fields/ and listing it in _SOURCES below - no generator change.
"""
from __future__ import annotations

import dataclasses

from .process_data_fields._types import FieldType, InstrumentTypeConfig, ProcessField
from .process_data_fields.transmitters import TRANSMITTER_TYPES
from .process_data_fields.analyzers_a import ANALYZER_TYPES_A
from .process_data_fields.analyzers_b import ANALYZER_TYPES_B
from .process_data_fields.gauges_gas_custom import GAUGE_GAS_CUSTOM_TYPES

# Always the first 8 columns of the requisition, in this order.
IDENTIFICATION_COLUMNS = (
    ProcessField("S.NO", mandatory=True),
    ProcessField("TAG NO", mandatory=True),
    ProcessField("EQUIPMENT DESCRIPTION", mandatory=True),
    ProcessField("P&ID NO.", mandatory=True),
    ProcessField("SERVICE", mandatory=True),
    ProcessField("EQUIPMENT NO", mandatory=True),
    ProcessField("LINE", mandatory=True),
    ProcessField("LINE SIZE", mandatory=True),
)

# Order shown in the type dropdown (follows the requisition spec).
_ORDER = (
    "level_transmitter", "flow_transmitter", "temperature_transmitter", "pressure_transmitter",
    "level_gauge", "pressure_gauge", "temperature_gauge",
    "ph_analyzer", "orp_analyzer", "conductivity_analyzer", "turbidity_analyzer",
    "dissolved_oxygen_analyzer", "chlorine_analyzer", "ozone_analyzer", "ammonia_analyzer",
    "nitrate_analyzer", "phosphate_analyzer", "cod_analyzer", "toc_analyzer", "tss_mlss_analyzer",
    "fluoride_analyzer", "silica_analyzer", "oil_in_water_analyzer", "h2s_analyzer",
    "o2_analyzer", "co2_analyzer", "ch4_analyzer", "biogas_analyzer", "other_gas_analyzer",
    "custom_analyzer", "custom_instrument",
)

# Extra aliases seen in real IODBs (e.g. "ANALYZER INDICATING TRANSMITTER - DO").
# Only wording that unambiguously names the measured parameter is listed here;
# "NITROGEN" / "PHOSPHORUS" / "BOD" are NOT mapped to nitrate / phosphate / anything -
# they are different parameters and are never classified silently.
_EXTRA_ALIASES = {
    "ph_analyzer": ("ANALYZER INDICATING TRANSMITTER - PH", "PH ANALYZER INDICATING TRANSMITTER"),
    "dissolved_oxygen_analyzer": ("ANALYZER INDICATING TRANSMITTER - DO",),
    "cod_analyzer": ("ANALYZER INDICATING TRANSMITTER - COD",),
    "toc_analyzer": ("ANALYZER INDICATING TRANSMITTER - TOC",),
    "tss_mlss_analyzer": ("ANALYZER INDICATING TRANSMITTER - TSS", "ANALYZER INDICATING TRANSMITTER - MLSS",
                          "TSS ANALYZER", "MLSS ANALYZER", "SUSPENDED SOLIDS ANALYZER"),
    "orp_analyzer": ("ANALYZER INDICATING TRANSMITTER - ORP",),
    "conductivity_analyzer": ("ANALYZER INDICATING TRANSMITTER - CONDUCTIVITY",),
    "turbidity_analyzer": ("ANALYZER INDICATING TRANSMITTER - TURBIDITY",),
    "chlorine_analyzer": ("ANALYZER INDICATING TRANSMITTER - CHLORINE",),
    "ammonia_analyzer": ("ANALYZER INDICATING TRANSMITTER - AMMONIA",),
    "nitrate_analyzer": ("ANALYZER INDICATING TRANSMITTER - NITRATE",),
    "phosphate_analyzer": ("PHOSPHATE ANALYZER", "ANALYZER INDICATING TRANSMITTER - PHOSPHATE"),
}

# Process-data field -> IODB column that may seed it (prefill option only; copy, never compute).
# Single-valued IODB columns only seed the plain / "Normal" field - never Min and Max too.
# Header comparison ignores case, spacing and a trailing "(unit)" in the IODB header.
IODB_PREFILL = {
    "density": "DENSITY", "fluid density normal": "DENSITY", "density normal": "DENSITY",
    "specific gravity": "SPECIFIC GRAVITY",
    "viscosity": "VISCOCITY", "viscosity normal": "VISCOCITY",
    "dielectric constant": "DIELECTRIC CONSTANT",
    "velocity": "VELOCITY",
    "line moc": "LINE MOC",
    "process connection size": "PROCESS CONNECTION SIZE",
}
for _p, _col in (("process temperature", "TEMPERATURE"), ("temperature", "TEMPERATURE"),
                 ("process pressure", "PRESSURE"), ("pressure", "PRESSURE"),
                 ("operating pressure", "PRESSURE"), ("gas temperature", "TEMPERATURE"),
                 ("gas pressure", "PRESSURE"), ("flow", "FLOW"), ("gas flow", "FLOW")):
    for _lo in ("min", "minimum"):
        IODB_PREFILL[f"{_p} {_lo}"] = f"{_col} MIN"
    for _hi in ("max", "maximum"):
        IODB_PREFILL[f"{_p} {_hi}"] = f"{_col} MAX"


def iodb_aliases_for(field_name: str) -> tuple:
    col = IODB_PREFILL.get(" ".join(str(field_name).lower().split()))
    return (col,) if col else ()


def _finalize(cfg: InstrumentTypeConfig) -> InstrumentTypeConfig:
    changes = {}
    extra = _EXTRA_ALIASES.get(cfg.key)
    if extra:
        changes["match_aliases"] = tuple(cfg.match_aliases) + tuple(extra)
    # "AIT" is the generic analyzer tag prefix - it would classify every analyzer as every
    # analyzer type, so analyzers are matched on wording only.
    if cfg.category == "Analyzer" and cfg.tag_prefixes:
        changes["tag_prefixes"] = ()
    fields = tuple(f if f.iodb_aliases else dataclasses.replace(f, iodb_aliases=iodb_aliases_for(f.name))
                   for f in cfg.fields)
    if fields != tuple(cfg.fields):
        changes["fields"] = fields
    return dataclasses.replace(cfg, **changes) if changes else cfg


def _build() -> dict:
    merged: dict = {}
    for src in (TRANSMITTER_TYPES, ANALYZER_TYPES_A, ANALYZER_TYPES_B, GAUGE_GAS_CUSTOM_TYPES):
        merged.update(src)
    out = {k: _finalize(merged[k]) for k in _ORDER if k in merged}
    for k, v in merged.items():  # any config not in _ORDER is still available (extensibility)
        out.setdefault(k, _finalize(v))
    return out


INSTRUMENT_TYPES: dict = _build()


def get_type(key: str) -> InstrumentTypeConfig:
    return INSTRUMENT_TYPES[key]
