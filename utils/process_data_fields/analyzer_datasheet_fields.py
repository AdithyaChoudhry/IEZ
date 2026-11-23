# analyzer_datasheet_fields.py
"""
Fields printed on the ANNEXURE-I of the analyser datasheets (pH / ORP / Conductivity / Turbidity / DO / Residual Chlorine /
NH3 / TOC / TSS / Oil / Phenol ANALYSER-R0.xls) that the analyser configurations did not have. They are appended to the
existing configurations by process_data_library.py - the analyser files themselves are untouched. Which fields are selected
by default is decided by the verified profiles in process_data_profiles.py.
"""
from ._types import FieldType, InstrumentTypeConfig, ProcessField

_N, _T = FieldType.NUMBER, FieldType.TEXT


def _pressure_trio():
    return (ProcessField("Pressure Minimum", unit="Kg/Cm2.g", field_type=_N),
            ProcessField("Pressure Normal", unit="Kg/Cm2.g", field_type=_N),
            ProcessField("Pressure Maximum", unit="Kg/Cm2.g", field_type=_N))


_SG = ProcessField("Specific Gravity", field_type=_N)
_VISC = ProcessField("Viscosity", unit="Cp", field_type=_N)
_COND = ProcessField("Conductivity", unit="µs/cm", field_type=_N)


def _ranges(unit=""):
    return (ProcessField("Operating Range", unit=unit, field_type=_T), ProcessField("Instrument Range", unit=unit, field_type=_T))


# Analyser types that already have a single-valued Pressure get the MIN / NOR / MAX columns of the annexure.
EXTRA_FIELDS = {
    "ph_analyzer": (_SG, _VISC, *_ranges()),
    "orp_analyzer": (_SG, _VISC, *_ranges()),
    "conductivity_analyzer": (_SG, _VISC, _COND, *_ranges()),
    "turbidity_analyzer": (_SG, _VISC, _COND, *_ranges()),
    "dissolved_oxygen_analyzer": (ProcessField("Instrument Range", field_type=_T),),
    "chlorine_analyzer": (ProcessField("Process Fluid", field_type=_T), *_ranges()),
    "ammonia_analyzer": (*_pressure_trio(), *_ranges()),
    "toc_analyzer": (*_pressure_trio(), _SG, _VISC, _COND, *_ranges("Mg/L")),
    "tss_mlss_analyzer": (*_pressure_trio(), *_ranges("PPM")),
    "oil_in_water_analyzer": (*_pressure_trio(), *_ranges()),
}

PHENOL_ANALYZER = InstrumentTypeConfig(
    key="phenol_analyzer",
    label="Phenol Analyzer",
    category="Analyzer",
    match_aliases=("PHENOL ANALYZER", "PHENOL ANALYSER", "ONLINE PHENOL ANALYZER"),
    fields=(
        ProcessField("Process Fluid", field_type=_T),
        *_pressure_trio(),
        ProcessField("Temperature Minimum", unit="°C", field_type=_N),
        ProcessField("Normal Temperature", unit="°C", field_type=_N),
        ProcessField("Temperature Maximum", unit="°C", field_type=_N),
        *_ranges(),
        ProcessField("Remarks", field_type=_T),
    ),
)

ANALYZER_DATASHEET_TYPES = {"phenol_analyzer": PHENOL_ANALYZER}
