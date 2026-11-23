# switches_elements.py
"""
Process data field definitions for instruments that had no entry in the Process Data Requisition library and whose
datasheet ANNEXURE-I defines the process inputs:
    - Differential Pressure Switch   (DIFFERENTIAL PRESSURE SWITCH-R0.xls)
    - Flow Switch                    (FLOW SWITCH.xls)
    - Flow Element - Orifice Plate   (FE-ORIFICE PLATE-R0.xls)

Field names and units follow the annexure headings exactly (units are the ones printed on the datasheet; nothing is
converted). Which of these fields are selected by default is decided by the verified profile in
process_data_profiles.py.
"""
from ._types import FieldType, InstrumentTypeConfig, ProcessField

_N, _T = FieldType.NUMBER, FieldType.TEXT


def _trio(prefix: str, unit: str, ft=_N):
    return (ProcessField(f"Minimum {prefix}", unit=unit, field_type=ft),
            ProcessField(f"Normal {prefix}", unit=unit, field_type=ft),
            ProcessField(f"Maximum {prefix}", unit=unit, field_type=ft))


# ── Differential Pressure Switch ────────────────────────────────────────────
DPS_FIELDS = (
    ProcessField("Process Fluid / Service", field_type=_T),
    *_trio("Operating Pressure", "Kg/cm2 g"),
    *_trio("Operating Temperature", "°C"),
    ProcessField("Switching Setpoint", unit="Kg/cm2 g", field_type=_N),
    ProcessField("Instrument Range", unit="Kg/cm2 g", field_type=_T),
    ProcessField("Switching Differential (Adjustable)", unit="Kg/cm2 g", field_type=_N),
    ProcessField("Remarks", field_type=_T),
)

DIFFERENTIAL_PRESSURE_SWITCH = InstrumentTypeConfig(
    key="differential_pressure_switch",
    label="Differential Pressure Switch",
    category="Switch",
    match_aliases=("DIFFERENTIAL PRESSURE SWITCH", "DP SWITCH", "DIFFERENTIAL PRESSURE SWITCH - DPS"),
    tag_prefixes=("PDS", "DPS"),
    fields=DPS_FIELDS,
)

# ── Flow Switch ─────────────────────────────────────────────────────────────
FS_FIELDS = (
    ProcessField("Process Fluid / Service", field_type=_T),
    *_trio("Flow", "lpm"),
    *_trio("Operating Pressure", "Kg/cm2 g"),
    *_trio("Operating Temperature", "°C"),
    ProcessField("Density", unit="kg/m3", field_type=_N),
    ProcessField("Viscosity", unit="Cp", field_type=_N),
    ProcessField("Flow Setpoint", unit="lpm", field_type=_N),
    ProcessField("Setpoint Range", unit="lpm", field_type=_T),
    ProcessField("Remarks", field_type=_T),
)

FLOW_SWITCH = InstrumentTypeConfig(
    key="flow_switch",
    label="Flow Switch",
    category="Switch",
    match_aliases=("FLOW SWITCH",),
    tag_prefixes=("FS", "FSL", "FSH"),
    fields=FS_FIELDS,
)

# ── Flow Element - Orifice Plate ────────────────────────────────────────────
FE_FIELDS = (
    ProcessField("Process Fluid / Service", field_type=_T),
    *_trio("Flow", "m3/hr"),
    *_trio("Operating Pressure", "Kg/cm2 g"),
    *_trio("Operating Temperature", "°C"),
    ProcessField("Fluid Density", unit="Kg/m3", field_type=_N),
    ProcessField("Maximum Allowable Pressure Loss", unit="mmWC", field_type=_N),
    ProcessField("Pipe Inside Diameter", unit="mm", field_type=_N),
    ProcessField("Pipe Outside Diameter", unit="mm", field_type=_N),
    ProcessField("Orifice Bore Diameter", unit="mm", field_type=_N),
    ProcessField("Plate Thickness", unit="mm", field_type=_N),
    ProcessField("Differential Pressure at Maximum Flow", unit="mmWC", field_type=_N),
    ProcessField("Beta Ratio", field_type=_N),
    ProcessField("Flange Type", field_type=_T),
    ProcessField("Gasket", field_type=_T),
    ProcessField("Studs & Nuts", field_type=_T),
    ProcessField("Remarks", field_type=_T),
)

ORIFICE_PLATE = InstrumentTypeConfig(
    key="orifice_plate",
    label="Flow Element - Orifice Plate",
    category="Flow Element",
    match_aliases=("ORIFICE PLATE", "ORIFICE FLOW ELEMENT", "FLOW ELEMENT - ORIFICE PLATE", "FLOW ELEMENT ORIFICE PLATE"),
    tag_prefixes=("FE",),
    fields=FE_FIELDS,
)

SWITCH_ELEMENT_TYPES = {
    "differential_pressure_switch": DIFFERENTIAL_PRESSURE_SWITCH,
    "flow_switch": FLOW_SWITCH,
    "orifice_plate": ORIFICE_PLATE,
}
