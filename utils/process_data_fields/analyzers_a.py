# analyzers_a.py
"""
Process Data Requisition field definitions for Analyzer instrument types (batch A):
pH, ORP, Conductivity, Turbidity, Dissolved Oxygen, Chlorine, Ozone, Ammonia, and
Nitrate analyzers.
"""

from ._types import FieldType, ProcessField, InstrumentTypeConfig


# ---------------------------------------------------------------------------
# pH Analyzer
# ---------------------------------------------------------------------------
PH_ANALYZER_FIELDS = (
    ProcessField(name="Process Fluid", field_type=FieldType.TEXT),
    ProcessField(name="Expected pH Minimum", field_type=FieldType.NUMBER),
    ProcessField(name="Normal pH", field_type=FieldType.NUMBER),
    ProcessField(name="Expected pH Maximum", field_type=FieldType.NUMBER),
    ProcessField(name="pH Unit", field_type=FieldType.TEXT),
    ProcessField(name="Process Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Process Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Process Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Process Pressure Minimum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Process Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Process Pressure Maximum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Minimum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Flow", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Maximum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Conductivity", unit="µS/cm", field_type=FieldType.NUMBER),
    ProcessField(name="Suspended Solids / TSS", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Turbidity", unit="NTU", field_type=FieldType.NUMBER),
    ProcessField(name="Colour / Optical Characteristics", field_type=FieldType.TEXT),
    ProcessField(name="Chemical Composition", field_type=FieldType.TEXT),
    ProcessField(name="Cleaning Requirement / Fouling Tendency", field_type=FieldType.TEXT),
    ProcessField(name="Chemical Dosing Present", field_type=FieldType.BOOLEAN),
    ProcessField(name="Expected Interference / Contamination", field_type=FieldType.TEXT),
    ProcessField(name="Sample Point / Installation Location", field_type=FieldType.TEXT),
    ProcessField(name="Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

PH_ANALYZER = InstrumentTypeConfig(
    key="ph_analyzer",
    label="pH Analyzer",
    category="Analyzer",
    match_aliases=("pH ANALYZER", "pH TRANSMITTER", "pH METER"),
    tag_prefixes=("AIT",),
    subtypes=(),
    fields=PH_ANALYZER_FIELDS,
)


# ---------------------------------------------------------------------------
# ORP Analyzer
# ---------------------------------------------------------------------------
ORP_ANALYZER_FIELDS = (
    ProcessField(name="Process Fluid", field_type=FieldType.TEXT),
    ProcessField(name="ORP Minimum", unit="mV", field_type=FieldType.NUMBER),
    ProcessField(name="Normal ORP", unit="mV", field_type=FieldType.NUMBER),
    ProcessField(name="ORP Maximum", unit="mV", field_type=FieldType.NUMBER),
    ProcessField(name="ORP Unit", field_type=FieldType.TEXT),
    ProcessField(name="Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Minimum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Maximum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Minimum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Flow", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Maximum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="pH", field_type=FieldType.NUMBER),
    ProcessField(name="Conductivity", unit="µS/cm", field_type=FieldType.NUMBER),
    ProcessField(name="Oxidizing / Reducing Chemicals", field_type=FieldType.TEXT),
    ProcessField(name="Chemical Dosing", field_type=FieldType.BOOLEAN),
    ProcessField(name="Suspended Solids", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Fouling Tendency", field_type=FieldType.TEXT),
    ProcessField(name="Sample / Installation Point", field_type=FieldType.TEXT),
    ProcessField(name="Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

ORP_ANALYZER = InstrumentTypeConfig(
    key="orp_analyzer",
    label="ORP Analyzer",
    category="Analyzer",
    match_aliases=("ORP ANALYZER", "REDOX ANALYZER", "ORP TRANSMITTER"),
    tag_prefixes=("AIT",),
    subtypes=(),
    fields=ORP_ANALYZER_FIELDS,
)


# ---------------------------------------------------------------------------
# Conductivity Analyzer
# ---------------------------------------------------------------------------
CONDUCTIVITY_ANALYZER_FIELDS = (
    ProcessField(name="Process Fluid", field_type=FieldType.TEXT),
    ProcessField(name="Conductivity Minimum", unit="µS/cm", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Conductivity", unit="µS/cm", field_type=FieldType.NUMBER),
    ProcessField(name="Conductivity Maximum", unit="µS/cm", field_type=FieldType.NUMBER),
    ProcessField(name="Conductivity Unit", field_type=FieldType.TEXT),
    ProcessField(name="Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Minimum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Maximum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Minimum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Flow", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Maximum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="TDS", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Ionic Composition", field_type=FieldType.TEXT),
    ProcessField(name="Chemical Composition", field_type=FieldType.TEXT),
    ProcessField(name="Suspended Solids", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Scaling / Fouling Tendency", field_type=FieldType.TEXT),
    ProcessField(name="Temperature Compensation Required", field_type=FieldType.BOOLEAN),
    ProcessField(name="Sample / Installation Point", field_type=FieldType.TEXT),
    ProcessField(name="Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

CONDUCTIVITY_ANALYZER = InstrumentTypeConfig(
    key="conductivity_analyzer",
    label="Conductivity Analyzer",
    category="Analyzer",
    match_aliases=("CONDUCTIVITY ANALYZER", "CONDUCTIVITY TRANSMITTER", "CONDUCTIVITY METER"),
    tag_prefixes=("AIT",),
    subtypes=(),
    fields=CONDUCTIVITY_ANALYZER_FIELDS,
)


# ---------------------------------------------------------------------------
# Turbidity Analyzer
# ---------------------------------------------------------------------------
TURBIDITY_ANALYZER_FIELDS = (
    ProcessField(name="Process Fluid", field_type=FieldType.TEXT),
    ProcessField(name="Turbidity Minimum", unit="NTU", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Turbidity", unit="NTU", field_type=FieldType.NUMBER),
    ProcessField(name="Turbidity Maximum", unit="NTU", field_type=FieldType.NUMBER),
    ProcessField(name="Turbidity Unit", field_type=FieldType.TEXT),
    ProcessField(name="Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Minimum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Maximum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Minimum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Flow", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Maximum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="TSS", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Particle Characteristics", field_type=FieldType.TEXT),
    ProcessField(name="Particle Size / Distribution", field_type=FieldType.TEXT),
    ProcessField(name="Colour", field_type=FieldType.TEXT),
    ProcessField(name="Suspended Solids Type", field_type=FieldType.TEXT),
    ProcessField(name="Fouling / Coating Tendency", field_type=FieldType.TEXT),
    ProcessField(name="Sample / Installation Point", field_type=FieldType.TEXT),
    ProcessField(name="Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

TURBIDITY_ANALYZER = InstrumentTypeConfig(
    key="turbidity_analyzer",
    label="Turbidity Analyzer",
    category="Analyzer",
    match_aliases=("TURBIDITY ANALYZER", "TURBIDITY TRANSMITTER", "TURBIDIMETER"),
    tag_prefixes=("AIT",),
    subtypes=(),
    fields=TURBIDITY_ANALYZER_FIELDS,
)


# ---------------------------------------------------------------------------
# Dissolved Oxygen Analyzer
# ---------------------------------------------------------------------------
DISSOLVED_OXYGEN_ANALYZER_FIELDS = (
    ProcessField(name="Process Fluid", field_type=FieldType.TEXT),
    ProcessField(name="DO Minimum", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Normal DO", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="DO Maximum", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="DO Unit", field_type=FieldType.TEXT),
    ProcessField(name="Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Minimum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Maximum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Minimum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Flow", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Maximum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Atmospheric / Gas Exposure", field_type=FieldType.TEXT),
    ProcessField(name="Salinity", unit="ppt", field_type=FieldType.NUMBER),
    ProcessField(name="Conductivity", unit="µS/cm", field_type=FieldType.NUMBER),
    ProcessField(name="Suspended Solids", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Biological Activity", field_type=FieldType.TEXT),
    ProcessField(name="Aeration Condition", field_type=FieldType.TEXT),
    ProcessField(name="Fouling Tendency", field_type=FieldType.TEXT),
    ProcessField(name="Sample / Installation Point", field_type=FieldType.TEXT),
    ProcessField(name="Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

DISSOLVED_OXYGEN_ANALYZER = InstrumentTypeConfig(
    key="dissolved_oxygen_analyzer",
    label="Dissolved Oxygen Analyzer",
    category="Analyzer",
    match_aliases=("DISSOLVED OXYGEN ANALYZER", "DO ANALYZER", "DO TRANSMITTER"),
    tag_prefixes=("AIT",),
    subtypes=(),
    fields=DISSOLVED_OXYGEN_ANALYZER_FIELDS,
)


# ---------------------------------------------------------------------------
# Chlorine Analyzer
# ---------------------------------------------------------------------------
CHLORINE_ANALYZER_FIELDS = (
    ProcessField(
        name="Chlorine Type",
        field_type=FieldType.DROPDOWN,
        options=("Free Chlorine", "Total Chlorine", "Combined Chlorine"),
    ),
    ProcessField(name="Free Chlorine Minimum", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Free Chlorine", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Free Chlorine Maximum", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Total Chlorine Minimum", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Total Chlorine", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Total Chlorine Maximum", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Chlorine Unit", field_type=FieldType.TEXT),
    ProcessField(name="pH", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Minimum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Maximum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Minimum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Flow", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Maximum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Conductivity", unit="µS/cm", field_type=FieldType.NUMBER),
    ProcessField(name="Ammonia", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Chemical Dosing", field_type=FieldType.BOOLEAN),
    ProcessField(name="Sample Conditioning", field_type=FieldType.TEXT),
    ProcessField(name="Fouling Tendency", field_type=FieldType.TEXT),
    ProcessField(name="Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

CHLORINE_ANALYZER = InstrumentTypeConfig(
    key="chlorine_analyzer",
    label="Chlorine Analyzer",
    category="Analyzer",
    match_aliases=("CHLORINE ANALYZER", "RESIDUAL CHLORINE ANALYZER", "FREE CHLORINE ANALYZER"),
    tag_prefixes=("AIT",),
    subtypes=(),
    fields=CHLORINE_ANALYZER_FIELDS,
)


# ---------------------------------------------------------------------------
# Ozone Analyzer
# ---------------------------------------------------------------------------
OZONE_ANALYZER_FIELDS = (
    ProcessField(name="Ozone Minimum", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Ozone", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Ozone Maximum", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Ozone Unit", field_type=FieldType.TEXT),
    ProcessField(name="Process Fluid", field_type=FieldType.TEXT),
    ProcessField(name="Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Minimum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Maximum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Minimum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Flow", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Maximum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="pH", field_type=FieldType.NUMBER),
    ProcessField(name="Conductivity", unit="µS/cm", field_type=FieldType.NUMBER),
    ProcessField(name="Residual Chlorine", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Chemical Dosing", field_type=FieldType.BOOLEAN),
    ProcessField(name="Sample Conditioning", field_type=FieldType.TEXT),
    ProcessField(name="Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

OZONE_ANALYZER = InstrumentTypeConfig(
    key="ozone_analyzer",
    label="Ozone Analyzer",
    category="Analyzer",
    match_aliases=("OZONE ANALYZER", "O3 ANALYZER"),
    tag_prefixes=("AIT",),
    subtypes=(),
    fields=OZONE_ANALYZER_FIELDS,
)


# ---------------------------------------------------------------------------
# Ammonia Analyzer
# ---------------------------------------------------------------------------
AMMONIA_ANALYZER_FIELDS = (
    ProcessField(name="Ammonia Minimum", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Ammonia", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Ammonia Maximum", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Ammonia Unit", field_type=FieldType.TEXT),
    ProcessField(name="Process Fluid", field_type=FieldType.TEXT),
    ProcessField(name="pH Minimum", field_type=FieldType.NUMBER),
    ProcessField(name="Normal pH", field_type=FieldType.NUMBER),
    ProcessField(name="pH Maximum", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Minimum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Flow", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Maximum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="TSS", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Conductivity", unit="µS/cm", field_type=FieldType.NUMBER),
    ProcessField(name="Interfering Species", field_type=FieldType.TEXT),
    ProcessField(name="Chemical Dosing", field_type=FieldType.BOOLEAN),
    ProcessField(name="Sample Conditioning", field_type=FieldType.TEXT),
    ProcessField(name="Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

AMMONIA_ANALYZER = InstrumentTypeConfig(
    key="ammonia_analyzer",
    label="Ammonia Analyzer",
    category="Analyzer",
    match_aliases=("AMMONIA ANALYZER", "NH3 ANALYZER"),
    tag_prefixes=("AIT",),
    subtypes=(),
    fields=AMMONIA_ANALYZER_FIELDS,
)


# ---------------------------------------------------------------------------
# Nitrate Analyzer
# ---------------------------------------------------------------------------
NITRATE_ANALYZER_FIELDS = (
    ProcessField(name="Nitrate Minimum", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Nitrate", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Nitrate Maximum", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Nitrate Unit", field_type=FieldType.TEXT),
    ProcessField(name="Process Fluid", field_type=FieldType.TEXT),
    ProcessField(name="Nitrite", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Ammonia", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="pH", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Minimum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Flow", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="Flow Maximum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(name="TSS / Suspended Solids", unit="mg/L", field_type=FieldType.NUMBER),
    ProcessField(name="Turbidity", unit="NTU", field_type=FieldType.NUMBER),
    ProcessField(name="Colour", field_type=FieldType.TEXT),
    ProcessField(name="Chemical Interference", field_type=FieldType.TEXT),
    ProcessField(name="Sample Conditioning", field_type=FieldType.TEXT),
    ProcessField(name="Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

NITRATE_ANALYZER = InstrumentTypeConfig(
    key="nitrate_analyzer",
    label="Nitrate Analyzer",
    category="Analyzer",
    match_aliases=("NITRATE ANALYZER", "NO3 ANALYZER"),
    tag_prefixes=("AIT",),
    subtypes=(),
    fields=NITRATE_ANALYZER_FIELDS,
)


ANALYZER_TYPES_A: dict = {
    "ph_analyzer": PH_ANALYZER,
    "orp_analyzer": ORP_ANALYZER,
    "conductivity_analyzer": CONDUCTIVITY_ANALYZER,
    "turbidity_analyzer": TURBIDITY_ANALYZER,
    "dissolved_oxygen_analyzer": DISSOLVED_OXYGEN_ANALYZER,
    "chlorine_analyzer": CHLORINE_ANALYZER,
    "ozone_analyzer": OZONE_ANALYZER,
    "ammonia_analyzer": AMMONIA_ANALYZER,
    "nitrate_analyzer": NITRATE_ANALYZER,
}
