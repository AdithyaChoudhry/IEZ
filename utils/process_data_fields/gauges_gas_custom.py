# gauges_gas_custom.py
"""
Gauge, gas-analyzer, and custom instrument type definitions for the
Process Data Requisition generator.

Covers:
  - 3 gauge types: Level Gauge, Pressure Gauge, Temperature Gauge
  - 5 gas analyzer types: O2, CO2, CH4, Biogas, Other Gas
  - 2 custom types: Custom Instrument, Custom Analyzer
"""

from ._types import FieldType, ProcessField, InstrumentTypeConfig

# ---------------------------------------------------------------------------
# LEVEL GAUGE
# ---------------------------------------------------------------------------

LEVEL_GAUGE_FIELDS = (
    ProcessField(
        name="Measurement Type",
        field_type=FieldType.DROPDOWN,
        options=("Reflex", "Transparent", "Magnetic", "Float", "Other"),
    ),
    ProcessField(name="Process Fluid", field_type=FieldType.TEXT),
    ProcessField(name="Minimum Level", unit="mm", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Level", unit="mm", field_type=FieldType.NUMBER),
    ProcessField(name="Maximum Level", unit="mm", field_type=FieldType.NUMBER),
    ProcessField(
        name="Level Unit",
        field_type=FieldType.DROPDOWN,
        options=("mm", "m", "cm", "%"),
    ),
    ProcessField(name="Tank / Vessel Height", unit="mm", field_type=FieldType.NUMBER),
    ProcessField(name="Tank Diameter", unit="mm", field_type=FieldType.NUMBER),
    ProcessField(name="Operating Pressure Minimum", unit="bar(g)", field_type=FieldType.NUMBER),
    ProcessField(name="Operating Pressure Normal", unit="bar(g)", field_type=FieldType.NUMBER),
    ProcessField(name="Operating Pressure Maximum", unit="bar(g)", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Density", unit="kg/m³", field_type=FieldType.NUMBER),
    ProcessField(name="Specific Gravity", field_type=FieldType.NUMBER),
    ProcessField(name="Viscosity", unit="cP", field_type=FieldType.NUMBER),
    ProcessField(name="Vapour / Fumes", field_type=FieldType.TEXT),
    ProcessField(name="Foam", field_type=FieldType.BOOLEAN),
    ProcessField(name="Solids", field_type=FieldType.BOOLEAN),
    ProcessField(name="Corrosive Service", field_type=FieldType.BOOLEAN),
    ProcessField(name="Tank Connection Size", unit="in", field_type=FieldType.TEXT),
    ProcessField(name="Top Connection", field_type=FieldType.TEXT),
    ProcessField(name="Bottom Connection", field_type=FieldType.TEXT),
    ProcessField(name="Centre-to-Centre Distance", unit="mm", field_type=FieldType.NUMBER),
    ProcessField(name="Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

# ---------------------------------------------------------------------------
# PRESSURE GAUGE
# ---------------------------------------------------------------------------

PRESSURE_GAUGE_FIELDS = (
    ProcessField(name="Process Fluid", field_type=FieldType.TEXT),
    ProcessField(name="Pressure Minimum", unit="bar(g)", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Operating Pressure", unit="bar(g)", field_type=FieldType.NUMBER),
    ProcessField(name="Pressure Maximum", unit="bar(g)", field_type=FieldType.NUMBER),
    ProcessField(name="Design Pressure", unit="bar(g)", field_type=FieldType.NUMBER),
    ProcessField(name="Vacuum Condition", field_type=FieldType.BOOLEAN),
    ProcessField(name="Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Line Size", unit="in", field_type=FieldType.TEXT),
    ProcessField(name="Line MOC", field_type=FieldType.TEXT),
    ProcessField(name="Process Connection Size", unit="in", field_type=FieldType.TEXT),
    ProcessField(
        name="Process Connection Type",
        field_type=FieldType.DROPDOWN,
        options=("Threaded", "Flanged", "Welded", "Other"),
    ),
    ProcessField(name="Pressure Pulsation", field_type=FieldType.BOOLEAN),
    ProcessField(name="Vibration", field_type=FieldType.BOOLEAN),
    ProcessField(name="Corrosive Service", field_type=FieldType.BOOLEAN),
    ProcessField(name="Density", unit="kg/m³", field_type=FieldType.NUMBER),
    ProcessField(name="Specific Gravity", field_type=FieldType.NUMBER),
    ProcessField(name="Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

# ---------------------------------------------------------------------------
# TEMPERATURE GAUGE
# ---------------------------------------------------------------------------

TEMPERATURE_GAUGE_FIELDS = (
    ProcessField(name="Process Fluid", field_type=FieldType.TEXT),
    ProcessField(name="Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal Operating Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Design Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Process Pressure", unit="bar(g)", field_type=FieldType.NUMBER),
    ProcessField(name="Line Size", unit="in", field_type=FieldType.TEXT),
    ProcessField(name="Line MOC", field_type=FieldType.TEXT),
    ProcessField(
        name="Process Connection",
        field_type=FieldType.DROPDOWN,
        options=("Thermowell", "Direct Insertion", "Surface Mount", "Other"),
    ),
    ProcessField(name="Measurement Point", field_type=FieldType.TEXT),
    ProcessField(name="Flow Rate", unit="m³/h", field_type=FieldType.NUMBER),
    ProcessField(name="Velocity", unit="m/s", field_type=FieldType.NUMBER),
    ProcessField(name="Vibration", field_type=FieldType.BOOLEAN),
    ProcessField(name="Corrosive Service", field_type=FieldType.BOOLEAN),
    ProcessField(name="Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

# ---------------------------------------------------------------------------
# GAS ANALYZERS — shared generic field template (23 fields)
# ---------------------------------------------------------------------------

GAS_ANALYZER_GENERIC_FIELDS = (
    ProcessField(name="Component to be measured", field_type=FieldType.TEXT),
    ProcessField(name="Minimum concentration", field_type=FieldType.NUMBER),
    ProcessField(name="Normal concentration", field_type=FieldType.NUMBER),
    ProcessField(name="Maximum concentration", field_type=FieldType.NUMBER),
    ProcessField(
        name="Unit",
        field_type=FieldType.DROPDOWN,
        options=("%vol", "ppm", "ppb", "mg/m³", "%LEL"),
    ),
    ProcessField(name="Gas composition", field_type=FieldType.TEXT),
    ProcessField(name="Carrier gas", field_type=FieldType.TEXT),
    ProcessField(name="Interfering components", field_type=FieldType.TEXT),
    ProcessField(name="Gas temperature minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Normal gas temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Gas temperature maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField(name="Gas pressure minimum", unit="bar(g)", field_type=FieldType.NUMBER),
    ProcessField(name="Normal gas pressure", unit="bar(g)", field_type=FieldType.NUMBER),
    ProcessField(name="Gas pressure maximum", unit="bar(g)", field_type=FieldType.NUMBER),
    ProcessField(name="Gas flow minimum", unit="Nm³/h", field_type=FieldType.NUMBER),
    ProcessField(name="Normal gas flow", unit="Nm³/h", field_type=FieldType.NUMBER),
    ProcessField(name="Gas flow maximum", unit="Nm³/h", field_type=FieldType.NUMBER),
    ProcessField(name="Moisture", field_type=FieldType.BOOLEAN),
    ProcessField(name="Condensation", field_type=FieldType.BOOLEAN),
    ProcessField(name="Dust / particulates", field_type=FieldType.BOOLEAN),
    ProcessField(name="Sample conditioning required", field_type=FieldType.BOOLEAN),
    ProcessField(name="Hazardous area", field_type=FieldType.BOOLEAN),
    ProcessField(name="Remarks", field_type=FieldType.TEXT),
)

# Biogas-specific extra fields, appended on top of the 23 generic fields.
BIOGAS_EXTRA_FIELDS = (
    ProcessField(name="CH4 Concentration", unit="%vol", field_type=FieldType.NUMBER),
    ProcessField(name="CO2 Concentration", unit="%vol", field_type=FieldType.NUMBER),
    ProcessField(name="H2S Concentration", unit="ppm", field_type=FieldType.NUMBER),
    ProcessField(name="O2 Concentration", unit="%vol", field_type=FieldType.NUMBER),
    ProcessField(name="Moisture Content", unit="%", field_type=FieldType.NUMBER),
    ProcessField(name="Other Gas Components", field_type=FieldType.TEXT),
)

# ---------------------------------------------------------------------------
# InstrumentTypeConfig entries
# ---------------------------------------------------------------------------

LEVEL_GAUGE = InstrumentTypeConfig(
    key="level_gauge",
    label="Level Gauge",
    category="Gauge",
    match_aliases=(
        "LEVEL GAUGE",
        "REFLEX LEVEL GAUGE",
        "TRANSPARENT LEVEL GAUGE",
        "MAGNETIC LEVEL GAUGE",
    ),
    tag_prefixes=("LG",),
    fields=LEVEL_GAUGE_FIELDS,
)

PRESSURE_GAUGE = InstrumentTypeConfig(
    key="pressure_gauge",
    label="Pressure Gauge",
    category="Gauge",
    match_aliases=(
        "PRESSURE GAUGE",
        "DIAL PRESSURE GAUGE",
        "DIAPHRAGM SEAL PRESSURE GAUGE",
    ),
    tag_prefixes=("PG", "PI"),
    fields=PRESSURE_GAUGE_FIELDS,
)

TEMPERATURE_GAUGE = InstrumentTypeConfig(
    key="temperature_gauge",
    label="Temperature Gauge",
    category="Gauge",
    match_aliases=(
        "TEMPERATURE GAUGE",
        "BIMETALLIC TEMPERATURE GAUGE",
        "DIAL THERMOMETER",
    ),
    tag_prefixes=("TG", "TI"),
    fields=TEMPERATURE_GAUGE_FIELDS,
)

O2_ANALYZER = InstrumentTypeConfig(
    key="o2_analyzer",
    label="Oxygen Analyzer",
    category="Analyzer",
    match_aliases=(
        "OXYGEN ANALYZER",
        "O2 ANALYZER",
        "DISSOLVED OXYGEN GAS ANALYZER",
    ),
    tag_prefixes=("AIT",),
    fields=GAS_ANALYZER_GENERIC_FIELDS,
)

CO2_ANALYZER = InstrumentTypeConfig(
    key="co2_analyzer",
    label="Carbon Dioxide Analyzer",
    category="Analyzer",
    match_aliases=(
        "CARBON DIOXIDE ANALYZER",
        "CO2 ANALYZER",
    ),
    tag_prefixes=("AIT",),
    fields=GAS_ANALYZER_GENERIC_FIELDS,
)

CH4_ANALYZER = InstrumentTypeConfig(
    key="ch4_analyzer",
    label="Methane / CH4 Analyzer",
    category="Analyzer",
    match_aliases=(
        "METHANE ANALYZER",
        "CH4 ANALYZER",
    ),
    tag_prefixes=("AIT",),
    fields=GAS_ANALYZER_GENERIC_FIELDS,
)

BIOGAS_ANALYZER = InstrumentTypeConfig(
    key="biogas_analyzer",
    label="Biogas Analyzer",
    category="Analyzer",
    match_aliases=(
        "BIOGAS ANALYZER",
        "BIOGAS COMPOSITION ANALYZER",
    ),
    tag_prefixes=("AIT",),
    fields=GAS_ANALYZER_GENERIC_FIELDS + BIOGAS_EXTRA_FIELDS,
)

OTHER_GAS_ANALYZER = InstrumentTypeConfig(
    key="other_gas_analyzer",
    label="Other / Custom Gas Analyzer",
    category="Analyzer",
    match_aliases=(
        "GAS ANALYZER",
        "OTHER GAS ANALYZER",
    ),
    tag_prefixes=("AIT",),
    fields=GAS_ANALYZER_GENERIC_FIELDS,
)

CUSTOM_INSTRUMENT = InstrumentTypeConfig(
    key="custom_instrument",
    label="Custom Instrument",
    category="Custom",
    match_aliases=(),
    fields=(),
    is_custom=True,
)

CUSTOM_ANALYZER = InstrumentTypeConfig(
    key="custom_analyzer",
    label="Other / Custom Analyzer",
    category="Custom",
    match_aliases=(),
    fields=(),
    is_custom=True,
)

# ---------------------------------------------------------------------------
# Exported registry
# ---------------------------------------------------------------------------

GAUGE_GAS_CUSTOM_TYPES: dict = {
    "level_gauge": LEVEL_GAUGE,
    "pressure_gauge": PRESSURE_GAUGE,
    "temperature_gauge": TEMPERATURE_GAUGE,
    "o2_analyzer": O2_ANALYZER,
    "co2_analyzer": CO2_ANALYZER,
    "ch4_analyzer": CH4_ANALYZER,
    "biogas_analyzer": BIOGAS_ANALYZER,
    "other_gas_analyzer": OTHER_GAS_ANALYZER,
    "custom_instrument": CUSTOM_INSTRUMENT,
    "custom_analyzer": CUSTOM_ANALYZER,
}
