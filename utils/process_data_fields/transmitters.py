# transmitters.py
"""
Process data field definitions for transmitter-type instruments used by the
Process Data Requisition generator:
    - Level Transmitter
    - Flow Transmitter
    - Temperature Transmitter
    - Pressure Transmitter
"""

from ._types import FieldType, InstrumentTypeConfig, ProcessField

# ---------------------------------------------------------------------------
# LEVEL TRANSMITTER (49 fields, no subtypes)
# ---------------------------------------------------------------------------

LEVEL_TRANSMITTER_FIELDS = (
    ProcessField(
        "Measurement Type",
        field_type=FieldType.DROPDOWN,
        options=("Continuous", "Point Level", "Interface"),
        mandatory=True,
    ),
    ProcessField("Minimum Level", unit="m", field_type=FieldType.NUMBER),
    ProcessField("Normal Operating Level", unit="m", field_type=FieldType.NUMBER),
    ProcessField("Maximum Operating Level", unit="m", field_type=FieldType.NUMBER),
    ProcessField(
        "Level Unit",
        field_type=FieldType.DROPDOWN,
        options=("m", "mm", "cm", "ft", "%"),
    ),
    ProcessField("Tank / Vessel Height", unit="m", field_type=FieldType.NUMBER),
    ProcessField("Tank / Vessel Diameter", unit="m", field_type=FieldType.NUMBER),
    ProcessField("Reference Datum / Zero Elevation", unit="m", field_type=FieldType.NUMBER),
    ProcessField("Nozzle / Instrument Mounting Elevation", unit="m", field_type=FieldType.NUMBER),
    ProcessField("Normal Operating Volume", unit="m3", field_type=FieldType.NUMBER),
    ProcessField("Maximum Operating Volume", unit="m3", field_type=FieldType.NUMBER),
    ProcessField("Minimum Operating Volume", unit="m3", field_type=FieldType.NUMBER),
    ProcessField(
        "Process Fluid",
        field_type=FieldType.DROPDOWN,
        options=("Raw Water", "Clarified Water", "Treated Water", "Sludge", "Chemical", "Effluent", "Other"),
    ),
    ProcessField("Fluid Density Min", unit="kg/m3", field_type=FieldType.NUMBER),
    ProcessField("Fluid Density Normal", unit="kg/m3", field_type=FieldType.NUMBER),
    ProcessField("Fluid Density Max", unit="kg/m3", field_type=FieldType.NUMBER),
    ProcessField("Specific Gravity", field_type=FieldType.NUMBER),
    ProcessField("Process Temperature Min", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Process Temperature Normal", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Process Temperature Max", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Process Pressure Min", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Process Pressure Normal", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Process Pressure Max", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Vacuum Condition", field_type=FieldType.BOOLEAN),
    ProcessField("Dielectric Constant", field_type=FieldType.NUMBER),
    ProcessField("Presence of Fumes", field_type=FieldType.BOOLEAN),
    ProcessField("Presence of Foam", field_type=FieldType.BOOLEAN),
    ProcessField("Foam Characteristics", field_type=FieldType.TEXT),
    ProcessField("Agitation", field_type=FieldType.BOOLEAN),
    ProcessField("Turbulence", field_type=FieldType.BOOLEAN),
    ProcessField("Vapour / Gas Layer", field_type=FieldType.BOOLEAN),
    ProcessField("Presence of Solids", field_type=FieldType.BOOLEAN),
    ProcessField("Suspended Solids", unit="mg/l", field_type=FieldType.NUMBER),
    ProcessField("Interface Measurement Required", field_type=FieldType.BOOLEAN),
    ProcessField("Interface Fluid", field_type=FieldType.TEXT),
    ProcessField("Bottom Shape / Geometry", field_type=FieldType.TEXT),
    ProcessField("Internal Obstructions", field_type=FieldType.TEXT),
    ProcessField("Inlet / Outlet Location", field_type=FieldType.TEXT),
    ProcessField("Nozzle Size", unit="in", field_type=FieldType.NUMBER),
    ProcessField(
        "Nozzle Type",
        field_type=FieldType.DROPDOWN,
        options=("Flanged", "Threaded", "Welded", "Other"),
    ),
    ProcessField("Stilling Well Required", field_type=FieldType.BOOLEAN),
    ProcessField("Overflow Level", unit="m", field_type=FieldType.NUMBER),
    ProcessField("Low Level", unit="m", field_type=FieldType.NUMBER),
    ProcessField("Low-Low Level", unit="m", field_type=FieldType.NUMBER),
    ProcessField("High Level", unit="m", field_type=FieldType.NUMBER),
    ProcessField("High-High Level", unit="m", field_type=FieldType.NUMBER),
    ProcessField("Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField("Corrosive / Aggressive Service", field_type=FieldType.BOOLEAN),
    ProcessField("Remarks", field_type=FieldType.TEXT),
    # --- fields printed on the datasheet ANNEXURE-I of the Guided Wave Radar / Non-Contact Radar / Ultrasonic level
    # transmitters (see process_data_profiles.py) ------------------------------------------------------------------
    ProcessField("Viscosity", unit="cP", field_type=FieldType.NUMBER),
    ProcessField("Tank Tag Number", field_type=FieldType.TEXT),
    ProcessField("Tank Type", field_type=FieldType.TEXT),
    ProcessField("Tank MOC", field_type=FieldType.TEXT),
    ProcessField("Process Connection", field_type=FieldType.TEXT, subtype_only=("Guided Wave Radar",)),
    ProcessField("Nozzle Height", unit="mm", field_type=FieldType.NUMBER, subtype_only=("Non-Contact Radar", "Ultrasonic")),
    ProcessField("Max Fluid Level", unit="mm", field_type=FieldType.NUMBER, subtype_only=("Non-Contact Radar", "Ultrasonic")),
    ProcessField("Process Connection Flange Size", field_type=FieldType.TEXT, subtype_only=("Non-Contact Radar", "Ultrasonic")),
    ProcessField("Calibration Range", unit="mm", field_type=FieldType.TEXT,        # unit per subtype comes from the profile
                 subtype_only=("Guided Wave Radar", "Non-Contact Radar", "Ultrasonic", "DP Type (Open Tank)", "DP Type (Pressurized Tank)")),
    ProcessField("Instrument Range", unit="mm", field_type=FieldType.TEXT,
                 subtype_only=("Guided Wave Radar", "Non-Contact Radar", "Ultrasonic", "DP Type (Open Tank)", "DP Type (Pressurized Tank)")),
    # --- differential-pressure level transmitters (LT-DP Type datasheets) -------------------------------------------
    ProcessField("Level Range Low", field_type=FieldType.NUMBER, subtype_only=("DP Type (Open Tank)", "DP Type (Pressurized Tank)")),
    ProcessField("Level Range High", field_type=FieldType.NUMBER, subtype_only=("DP Type (Open Tank)", "DP Type (Pressurized Tank)")),
    ProcessField("Upper Fluid", field_type=FieldType.TEXT, subtype_only=("DP Type (Pressurized Tank)",)),
    ProcessField("Lower Fluid", field_type=FieldType.TEXT, subtype_only=("DP Type (Pressurized Tank)",)),
    ProcessField("Maximum Pressure", unit="Kg/cm2 G", field_type=FieldType.NUMBER, subtype_only=("DP Type (Pressurized Tank)",)),
    ProcessField("Operating Pressure", unit="Kg/cm2 G", field_type=FieldType.NUMBER, subtype_only=("DP Type (Pressurized Tank)",)),
    ProcessField("Maximum Temperature", unit="DEG C", field_type=FieldType.NUMBER, subtype_only=("DP Type (Pressurized Tank)",)),
    ProcessField("Operating Temperature", unit="DEG C", field_type=FieldType.NUMBER, subtype_only=("DP Type (Pressurized Tank)",)),
    ProcessField("Max DCS Range", unit="MMWC", field_type=FieldType.TEXT, subtype_only=("DP Type (Pressurized Tank)",)),
    ProcessField("Min DCS Range", unit="MMWC", field_type=FieldType.TEXT, subtype_only=("DP Type (Pressurized Tank)",)),
    ProcessField("Display Range", unit="MTRS", field_type=FieldType.TEXT, subtype_only=("DP Type (Pressurized Tank)",)),
    ProcessField("Capillary Size / Length", field_type=FieldType.TEXT, subtype_only=("DP Type (Pressurized Tank)",)),
)

LEVEL_TRANSMITTER = InstrumentTypeConfig(
    key="level_transmitter",
    label="Level Transmitter",
    category="Transmitter",
    match_aliases=(
        "LEVEL TRANSMITTER",
        "RADAR LEVEL TRANSMITTER",
        "ULTRASONIC LEVEL TRANSMITTER",
        "LEVEL INDICATING TRANSMITTER",
        "GUIDED WAVE RADAR LEVEL TRANSMITTER",
        "HYDROSTATIC LEVEL TRANSMITTER",
        "CAPACITANCE LEVEL TRANSMITTER",
    ),
    tag_prefixes=("LIT", "LT"),
    subtypes=("Guided Wave Radar", "Non-Contact Radar", "Ultrasonic", "DP Type (Open Tank)", "DP Type (Pressurized Tank)"),
    subtype_field_name="LEVEL TRANSMITTER TYPE",
    fields=LEVEL_TRANSMITTER_FIELDS,
)

# ---------------------------------------------------------------------------
# FLOW TRANSMITTER (40 generic fields + subtype-gated extras, 7 subtypes)
# ---------------------------------------------------------------------------

FLOW_TRANSMITTER_GENERIC_FIELDS = (
    ProcessField(
        "Measurement Type",
        field_type=FieldType.DROPDOWN,
        options=("Volumetric", "Mass"),
        mandatory=True,
    ),
    ProcessField(
        "Process Fluid",
        field_type=FieldType.DROPDOWN,
        options=("Raw Water", "Clarified Water", "Treated Water", "Sludge", "Chemical", "Effluent", "Gas", "Other"),
    ),
    ProcessField("Flow Minimum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField("Normal Flow", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField("Flow Maximum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField(
        "Flow Unit",
        field_type=FieldType.DROPDOWN,
        options=("m3/hr", "LPS", "LPM", "MLD", "kg/hr", "Nm3/hr"),
    ),
    ProcessField("Design Flow", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField("Density Min", unit="kg/m3", field_type=FieldType.NUMBER),
    ProcessField("Density Normal", unit="kg/m3", field_type=FieldType.NUMBER),
    ProcessField("Density Max", unit="kg/m3", field_type=FieldType.NUMBER),
    ProcessField("Specific Gravity", field_type=FieldType.NUMBER),
    ProcessField("Viscosity Min", unit="cP", field_type=FieldType.NUMBER),
    ProcessField("Viscosity Normal", unit="cP", field_type=FieldType.NUMBER),
    ProcessField("Viscosity Max", unit="cP", field_type=FieldType.NUMBER),
    ProcessField("Temperature Min", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Normal Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Temperature Max", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Pressure Min", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Normal Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Pressure Max", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Line Size", unit="in", field_type=FieldType.NUMBER),
    ProcessField("Line ID", unit="mm", field_type=FieldType.NUMBER),
    ProcessField("Line OD", unit="mm", field_type=FieldType.NUMBER),
    ProcessField(
        "Line MOC",
        field_type=FieldType.DROPDOWN,
        options=("Carbon Steel", "SS304", "SS316", "PVC", "HDPE", "Other"),
    ),
    ProcessField(
        "Process Connection",
        field_type=FieldType.DROPDOWN,
        options=("Flanged", "Threaded", "Welded", "Other"),
    ),
    ProcessField("Process Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Solid Content", unit="%", field_type=FieldType.NUMBER),
    ProcessField("Suspended Solids", unit="mg/l", field_type=FieldType.NUMBER),
    ProcessField("Gas Entrained", field_type=FieldType.BOOLEAN),
    ProcessField("Two-Phase Flow", field_type=FieldType.BOOLEAN),
    ProcessField("Pulsating Flow", field_type=FieldType.BOOLEAN),
    ProcessField(
        "Flow Direction",
        field_type=FieldType.DROPDOWN,
        options=("Horizontal", "Vertical Up", "Vertical Down", "Inclined"),
    ),
    ProcessField("Bidirectional Flow Required", field_type=FieldType.BOOLEAN),
    ProcessField("Required Straight Run Upstream", unit="D", field_type=FieldType.NUMBER),
    ProcessField("Required Straight Run Downstream", unit="D", field_type=FieldType.NUMBER),
    ProcessField("Conductivity", unit="µS/cm", field_type=FieldType.NUMBER),
    ProcessField("Dielectric Constant", field_type=FieldType.NUMBER),
    ProcessField("Corrosive / Aggressive Service", field_type=FieldType.BOOLEAN),
    ProcessField("Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField("Remarks", field_type=FieldType.TEXT),
)

FLOW_TRANSMITTER_SUBTYPE_FIELDS = (
    ProcessField(
        "Minimum Conductivity Required",
        unit="µS/cm",
        field_type=FieldType.NUMBER,
        subtype_only=("Magnetic",),
    ),
    ProcessField(
        "Orifice/Venturi Beta Ratio",
        field_type=FieldType.TEXT,
        subtype_only=("Differential Pressure",),
    ),
    ProcessField(
        "Channel Shape",
        field_type=FieldType.DROPDOWN,
        options=("Rectangular", "Trapezoidal", "V-Notch", "Other"),
        subtype_only=("Open Channel",),
    ),
    # --- fields that exist only on the datasheet ANNEXURE-I of a specific flow transmitter type -------------------
    # (ULTRASONIC PARSHALL FLUME / FT-DP / THERMAL MASS / ULTRASONIC CLAMP ON). Shown only for that subtype.
    ProcessField("Channel Material", field_type=FieldType.TEXT, subtype_only=("Ultrasonic Parshall Flume",)),
    ProcessField("Height at Operating Flow", unit="mm", field_type=FieldType.NUMBER, subtype_only=("Ultrasonic Parshall Flume",)),
    ProcessField("Height at Maximum Flow", unit="mm", field_type=FieldType.NUMBER, subtype_only=("Ultrasonic Parshall Flume",)),
    ProcessField("Throat Width", unit="mm", field_type=FieldType.NUMBER, subtype_only=("Ultrasonic Parshall Flume",)),
    ProcessField("Liquid Depth", unit="mm", field_type=FieldType.NUMBER, subtype_only=("Ultrasonic Parshall Flume",)),
    ProcessField("Calibration Range", unit="Mtrs", field_type=FieldType.TEXT, subtype_only=("Ultrasonic Parshall Flume",)),
    ProcessField("Instrument Range", field_type=FieldType.TEXT,           # unit comes from the profile (mmWC for DP, Mtrs for Parshall flume)
                 subtype_only=("Differential Pressure", "Ultrasonic Parshall Flume")),
    ProcessField("Differential Pressure Range", unit="mmWC", field_type=FieldType.TEXT, subtype_only=("Differential Pressure",)),
    ProcessField("Viscosity", unit="Cp", field_type=FieldType.NUMBER,
                 subtype_only=("Ultrasonic Parshall Flume", "Ultrasonic Clamp-On")),
    ProcessField("Minimum Velocity", unit="m/s", field_type=FieldType.NUMBER, subtype_only=("Ultrasonic Clamp-On",)),
    ProcessField("Normal Velocity", unit="m/s", field_type=FieldType.NUMBER, subtype_only=("Ultrasonic Clamp-On",)),
    ProcessField("Maximum Velocity", unit="m/s", field_type=FieldType.NUMBER, subtype_only=("Ultrasonic Clamp-On",)),
    ProcessField("Line Size / Material", field_type=FieldType.TEXT, subtype_only=("Ultrasonic Clamp-On",)),
    ProcessField("Measuring Range", unit="m3/hr", field_type=FieldType.TEXT, subtype_only=("Ultrasonic Clamp-On",)),
    ProcessField("Meter Range Minimum", unit="Nm3/hr", field_type=FieldType.NUMBER, subtype_only=("Thermal Mass",)),
    ProcessField("Meter Range Maximum", unit="Nm3/hr", field_type=FieldType.NUMBER, subtype_only=("Thermal Mass",)),
)

FLOW_TRANSMITTER_FIELDS = FLOW_TRANSMITTER_GENERIC_FIELDS + FLOW_TRANSMITTER_SUBTYPE_FIELDS

FLOW_TRANSMITTER = InstrumentTypeConfig(
    key="flow_transmitter",
    label="Flow Transmitter",
    category="Transmitter",
    match_aliases=(
        "FLOW TRANSMITTER",
        "MAGNETIC FLOW TRANSMITTER",
        "CORIOLIS FLOW TRANSMITTER",
        "ULTRASONIC FLOW TRANSMITTER",
        "VORTEX FLOW TRANSMITTER",
        "FLOW INDICATING TRANSMITTER",
        "DIFFERENTIAL PRESSURE FLOW TRANSMITTER",
    ),
    tag_prefixes=("FIT", "FT"),
    subtypes=("Magnetic", "Coriolis", "Ultrasonic", "Vortex", "Differential Pressure", "Open Channel",
              "Thermal Mass", "Ultrasonic Clamp-On", "Ultrasonic Parshall Flume", "Other"),
    subtype_field_name="FLOW METER TYPE",
    fields=FLOW_TRANSMITTER_FIELDS,
)

# ---------------------------------------------------------------------------
# TEMPERATURE TRANSMITTER (24 fields + subtype selector, no gated extras)
# ---------------------------------------------------------------------------

TEMPERATURE_TRANSMITTER_FIELDS = (
    ProcessField(
        "Process Fluid",
        field_type=FieldType.DROPDOWN,
        options=("Raw Water", "Clarified Water", "Treated Water", "Sludge", "Chemical", "Effluent", "Gas", "Other"),
    ),
    ProcessField("Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Normal Operating Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Design Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Process Pressure Minimum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Normal Process Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Process Pressure Maximum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Line Size", unit="in", field_type=FieldType.NUMBER),
    ProcessField("Line ID", unit="mm", field_type=FieldType.NUMBER),
    ProcessField("Line OD", unit="mm", field_type=FieldType.NUMBER),
    ProcessField(
        "Line MOC",
        field_type=FieldType.DROPDOWN,
        options=("Carbon Steel", "SS304", "SS316", "PVC", "HDPE", "Other"),
    ),
    ProcessField(
        "Process Connection",
        field_type=FieldType.DROPDOWN,
        options=("Flanged", "Threaded", "Welded", "Other"),
    ),
    ProcessField(
        "Sensor Location",
        field_type=FieldType.DROPDOWN,
        options=("Pipeline", "Tank / Vessel", "Equipment Surface", "Other"),
    ),
    ProcessField("Measurement Point", field_type=FieldType.TEXT),
    ProcessField("Flow Minimum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField("Normal Flow", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField("Flow Maximum", unit="m3/hr", field_type=FieldType.NUMBER),
    ProcessField("Velocity", unit="m/s", field_type=FieldType.NUMBER),
    ProcessField(
        "Process Phase",
        field_type=FieldType.DROPDOWN,
        options=("Liquid", "Gas", "Vapour", "Two-Phase", "Solid/Slurry"),
    ),
    ProcessField("Vibration", field_type=FieldType.BOOLEAN),
    ProcessField("Corrosive / Aggressive Service", field_type=FieldType.BOOLEAN),
    ProcessField("Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField("Remarks", field_type=FieldType.TEXT),
    ProcessField("Instrument Range", unit="°C", field_type=FieldType.TEXT),
    ProcessField("Calibration Range", unit="°C", field_type=FieldType.TEXT),
)

TEMPERATURE_TRANSMITTER = InstrumentTypeConfig(
    key="temperature_transmitter",
    label="Temperature Transmitter",
    category="Transmitter",
    match_aliases=(
        "TEMPERATURE TRANSMITTER",
        "TEMPERATURE INDICATING TRANSMITTER",
        "RTD TEMPERATURE TRANSMITTER",
        "THERMOCOUPLE TEMPERATURE TRANSMITTER",
    ),
    tag_prefixes=("TIT", "TT"),
    subtypes=("RTD", "Thermocouple", "Other"),
    subtype_field_name="SENSOR TYPE",
    fields=TEMPERATURE_TRANSMITTER_FIELDS,
)

# ---------------------------------------------------------------------------
# PRESSURE TRANSMITTER (27 fields + 5 Differential Pressure subtype fields)
# ---------------------------------------------------------------------------

PRESSURE_TRANSMITTER_GENERIC_FIELDS = (
    ProcessField(
        "Process Fluid",
        field_type=FieldType.DROPDOWN,
        options=("Raw Water", "Clarified Water", "Treated Water", "Sludge", "Chemical", "Effluent", "Gas", "Other"),
    ),
    ProcessField("Pressure Minimum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Normal Operating Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Pressure Maximum", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Design Pressure", unit="kg/cm2", field_type=FieldType.NUMBER),
    ProcessField("Vacuum Minimum", unit="mmHg", field_type=FieldType.NUMBER),
    ProcessField("Temperature Minimum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Normal Operating Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Temperature Maximum", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Design Temperature", unit="°C", field_type=FieldType.NUMBER),
    ProcessField("Line Size", unit="in", field_type=FieldType.NUMBER),
    ProcessField("Line ID", unit="mm", field_type=FieldType.NUMBER),
    ProcessField("Line OD", unit="mm", field_type=FieldType.NUMBER),
    ProcessField(
        "Line MOC",
        field_type=FieldType.DROPDOWN,
        options=("Carbon Steel", "SS304", "SS316", "PVC", "HDPE", "Other"),
    ),
    ProcessField(
        "Process Connection",
        field_type=FieldType.DROPDOWN,
        options=("Flanged", "Threaded", "Welded", "Other"),
    ),
    ProcessField(
        "Process Phase",
        field_type=FieldType.DROPDOWN,
        options=("Liquid", "Gas", "Vapour", "Two-Phase", "Solid/Slurry"),
    ),
    ProcessField("Density", unit="kg/m3", field_type=FieldType.NUMBER),
    ProcessField("Specific Gravity", field_type=FieldType.NUMBER),
    ProcessField("Viscosity", unit="cP", field_type=FieldType.NUMBER),
    ProcessField("Pulsation", field_type=FieldType.BOOLEAN),
    ProcessField("Corrosive / Aggressive Service", field_type=FieldType.BOOLEAN),
    ProcessField("Solids", field_type=FieldType.BOOLEAN),
    ProcessField("Hazardous Area", field_type=FieldType.BOOLEAN),
    ProcessField("Diaphragm Seal Required", field_type=FieldType.BOOLEAN),
    ProcessField("Remote Seal Required", field_type=FieldType.BOOLEAN),
    ProcessField("Capillary Requirement / Constraint", field_type=FieldType.TEXT),
    ProcessField("Remarks", field_type=FieldType.TEXT),
    ProcessField("Instrument Range", unit="Kg/cm2 g", field_type=FieldType.TEXT),
    ProcessField("Calibrated Range", unit="Kg/cm2 g", field_type=FieldType.TEXT),
)

PRESSURE_TRANSMITTER_DP_FIELDS = (
    ProcessField(
        "High Side Pressure",
        unit="kg/cm2",
        field_type=FieldType.NUMBER,
        subtype_only=("Differential Pressure",),
    ),
    ProcessField(
        "Low Side Pressure",
        unit="kg/cm2",
        field_type=FieldType.NUMBER,
        subtype_only=("Differential Pressure",),
    ),
    ProcessField(
        "Differential Pressure Minimum",
        unit="kg/cm2",
        field_type=FieldType.NUMBER,
        subtype_only=("Differential Pressure",),
    ),
    ProcessField(
        "Differential Pressure Normal",
        unit="kg/cm2",
        field_type=FieldType.NUMBER,
        subtype_only=("Differential Pressure",),
    ),
    ProcessField(
        "Differential Pressure Maximum",
        unit="kg/cm2",
        field_type=FieldType.NUMBER,
        subtype_only=("Differential Pressure",),
    ),
)

PRESSURE_TRANSMITTER_FIELDS = PRESSURE_TRANSMITTER_GENERIC_FIELDS + PRESSURE_TRANSMITTER_DP_FIELDS

PRESSURE_TRANSMITTER = InstrumentTypeConfig(
    key="pressure_transmitter",
    label="Pressure Transmitter",
    category="Transmitter",
    match_aliases=(
        "PRESSURE TRANSMITTER",
        "DIFFERENTIAL PRESSURE TRANSMITTER",
        "PRESSURE INDICATING TRANSMITTER",
        "GAUGE PRESSURE TRANSMITTER",
        "ABSOLUTE PRESSURE TRANSMITTER",
    ),
    tag_prefixes=("PIT", "PT", "DPIT"),
    subtypes=("Standard", "Differential Pressure"),
    subtype_field_name="SERVICE TYPE",
    fields=PRESSURE_TRANSMITTER_FIELDS,
)

# ---------------------------------------------------------------------------
# Public export
# ---------------------------------------------------------------------------

TRANSMITTER_TYPES: dict = {
    "level_transmitter": LEVEL_TRANSMITTER,
    "flow_transmitter": FLOW_TRANSMITTER,
    "temperature_transmitter": TEMPERATURE_TRANSMITTER,
    "pressure_transmitter": PRESSURE_TRANSMITTER,
}
