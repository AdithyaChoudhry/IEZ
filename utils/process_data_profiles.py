"""
Verified default parameter profiles for the Process Data Requisition generator.

A profile records, for one instrument type (and subtype), the ANNEXURE-I of the matching instrument datasheet:
every heading exactly as printed (with its unit and MIN/NOR/MAX sub-column), how it is classified, and what it maps to
in the generator's field configuration:

    Category A  - process data       asked from the process engineering team (selected by default)
    Category B  - additional data    from instrumentation / piping / mechanical / electrical (optional)
    Category C  - reference          already in the IODB / project metadata (never a requisition column)
    Category R  - review             ownership or mapping not settled; kept optional, flagged

Actions (the datasheet-to-generator comparison): EXISTS_DEFAULT, EXISTS_OPTIONAL, ADD_NEW_FIELD, UNIT_REVIEW,
MAPPING_REVIEW, REFERENCE_ONLY, NOT_APPLICABLE.

The headings below were read directly from the ten datasheets (and PRESSURE TRANSMITTER-R0.xls) - nothing here was
inferred. Units are the printed ones; nothing is converted. A type without a profile keeps its legacy behaviour (every
configured field offered, all selected) and is reported as "requires verification".
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Optional

A, B, C, R = "A", "B", "C", "R"
EXISTS_DEFAULT, EXISTS_OPTIONAL, ADD_NEW_FIELD = "EXISTS_DEFAULT", "EXISTS_OPTIONAL", "ADD_NEW_FIELD"
UNIT_REVIEW, MAPPING_REVIEW, REFERENCE_ONLY, NOT_APPLICABLE = "UNIT_REVIEW", "MAPPING_REVIEW", "REFERENCE_ONLY", "NOT_APPLICABLE"


@dataclass(frozen=True)
class Heading:
    label: str                 # the annexure heading exactly as printed (with its MIN/NOR/MAX sub-heading, if any)
    unit: str = ""             # the unit printed in the heading
    cls: str = C               # A / B / C / R
    action: str = REFERENCE_ONLY
    field: str = ""            # generator field it maps to ("" when it is not a requisition column)
    default: bool = False      # selected automatically
    note: str = ""


@dataclass(frozen=True)
class Profile:
    type_key: str
    subtype: str
    template: str              # datasheet file the headings were read from
    sheet: str                 # worksheet name
    headings: tuple
    review_note: str = ""


# ── builders ────────────────────────────────────────────────────────────────
def _ref(label, note="", cls=C, action=REFERENCE_ONLY):
    return Heading(label, cls=cls, action=action, note=note)


def _trio(label, unit, fields, action, cls=A, default=True, note=""):
    """MIN / NOR / MAX sub-columns of one grouped annexure heading -> three separate fields."""
    return tuple(Heading(f"{label} - {sub}", unit, cls, action, fld, default, note)
                 for sub, fld in zip(("MIN", "NOR", "MAX"), fields))


def _one(label, unit, field, cls, action, default=False, note=""):
    return (Heading(label, unit, cls, action, field, default, note),)


SL = _ref("SL.No.", "numbering of the requisition (S.NO)")
TAG = _ref("TAG NO.", "identification column TAG NO")
PID = _ref("P & ID NO.", "identification column P&ID NO.")
SERVICE_ID = _ref("SERVICE", "identification column SERVICE")
LOCATION = _ref("LOCATION", "no identification column carries the datasheet location; the engineer fills it on the datasheet",
                cls=R, action=MAPPING_REVIEW)
LINE = _ref("LINE NO.", "identification column LINE")
AREA = _ref("AREA CLASSIFICATION", "area classification comes from the IODB / project data, not from the process team")
TYPE_REF = _ref("TYPE", "construction type chosen by instrumentation / vendor, not a process input", cls=B, action=NOT_APPLICABLE)
MODEL = _ref("INST MODEL NO", "vendor model, filled after the requisition", cls=B, action=NOT_APPLICABLE)
LINESIZE_ID = _ref("LINE SIZE(NB)", "identification column LINE SIZE (derived from the IODB line number)")


def _remarks():
    return _one("REMARKS", "", "Remarks", B, EXISTS_OPTIONAL)


def _fluid(existing: bool, name="Process Fluid"):
    return _one("FLUID/SERVICE", "", name, A, EXISTS_DEFAULT if existing else ADD_NEW_FIELD, True,
                "free text on the datasheet (e.g. AIR SATURATED WASTE WATER)")


_KGCM2G = "Kg/cm2 g"
_PT_PRESSURE = ("Pressure Minimum", "Normal Operating Pressure", "Pressure Maximum")
_PT_TEMP = ("Temperature Minimum", "Normal Operating Temperature", "Temperature Maximum")
_FT_PRESSURE = ("Pressure Min", "Normal Pressure", "Pressure Max")
_FT_TEMP = ("Temperature Min", "Normal Temperature", "Temperature Max")
_FT_FLOW = ("Flow Minimum", "Normal Flow", "Flow Maximum")
_LG_PRESSURE = ("Operating Pressure Minimum", "Operating Pressure Normal", "Operating Pressure Maximum")
_LG_TEMP = ("Temperature Minimum", "Normal Temperature", "Temperature Maximum")
_NEW_P = ("Minimum Operating Pressure", "Normal Operating Pressure", "Maximum Operating Pressure")
_NEW_T = ("Minimum Operating Temperature", "Normal Operating Temperature", "Maximum Operating Temperature")
_NEW_F = ("Minimum Flow", "Normal Flow", "Maximum Flow")
_UNIT_NOTE = ("existing field is configured in kg/cm2; the datasheet prints this unit - the datasheet unit is used, "
              "no conversion is applied")

PROFILES: dict = {}


def _register(profile: Profile, *subtypes):
    for st in subtypes or (profile.subtype,):
        PROFILES[(profile.type_key, st)] = profile


# ── 1. Differential Pressure Switch ─────────────────────────────────────────
_register(Profile("differential_pressure_switch", "", "DIFFERENTIAL PRESSURE SWITCH-R0.xls", "ANNEXURE-I", (
    SL, TAG, PID, *_fluid(False, "Process Fluid / Service"), LOCATION, LINE, AREA,
    *_trio("PRESSURE (Kg/cm2 g)", _KGCM2G, _NEW_P, ADD_NEW_FIELD),
    *_trio("TEMP. (°C)", "°C", _NEW_T, ADD_NEW_FIELD),
    *_one("INSTRUMENT RANGE (Kg/cm2 g)", _KGCM2G, "Instrument Range", B, ADD_NEW_FIELD,
          note="instrument range is not an operating pressure"),
    *_one("SETPOINT (Kg/cm2 g)", _KGCM2G, "Switching Setpoint", A, ADD_NEW_FIELD, True,
          "the datasheet prints a differential-pressure setpoint in Kg/cm2 g; kept exactly as printed"),
    *_one("SWITCHING DIFFERENTIAL ADJUSTABLE (Kg/cm2 g)", _KGCM2G, "Switching Differential (Adjustable)", B, ADD_NEW_FIELD),
    MODEL, *_remarks())))

# ── 2. Differential Pressure Transmitter / Pressure Transmitter (same annexure columns) ──
_pt_headings = (
    SL, TAG, TYPE_REF, PID, *_fluid(True), SERVICE_ID, LOCATION, LINE, AREA,
    *_trio("PRESSURE (Kg/cm2 g)", _KGCM2G, _PT_PRESSURE, UNIT_REVIEW, note=_UNIT_NOTE),
    *_trio("TEMP. (°C)", "°C", _PT_TEMP, EXISTS_DEFAULT),
    *_one("INSTRUMENT RANGE (Kg/cm2 g)", _KGCM2G, "Instrument Range", B, ADD_NEW_FIELD,
          note="instrument range is not an operating pressure"),
    *_one("CALIBRATED RANGE (Kg/cm2 g)", _KGCM2G, "Calibrated Range", B, ADD_NEW_FIELD,
          note="calibrated range is not an operating pressure"),
    MODEL, *_remarks())
_register(Profile("pressure_transmitter", "Differential Pressure", "DIFFERENTIAL PRESSURE TRANSMITTER-R0.xls", "ANNEXURE-I",
                  _pt_headings,
                  "The annexure has no operating differential-pressure column; the existing Differential Pressure "
                  "Minimum/Normal/Maximum fields stay optional."))
_register(Profile("pressure_transmitter", "Standard", "PRESSURE TRANSMITTER-R0.xls", "ANNEXURE-I", _pt_headings), "Standard", "")

# ── 3. Orifice Plate flow element ───────────────────────────────────────────
_register(Profile("orifice_plate", "", "FE-ORIFICE PLATE-R0.xls", "ANNEXURE-I", (
    SL, TAG, *_one("TYPE", "", "Flange Type", B, ADD_NEW_FIELD, note="flange type of the orifice assembly"),
    PID, *_fluid(False, "Process Fluid / Service"), LOCATION, LINE,
    *_one("GASKET", "", "Gasket", B, ADD_NEW_FIELD), *_one("STUDS & NUTS", "", "Studs & Nuts", B, ADD_NEW_FIELD),
    LINESIZE_ID,
    *_one("PIPE - ID(mm)", "mm", "Pipe Inside Diameter", B, ADD_NEW_FIELD),
    *_one("PIPE - OD(mm)", "mm", "Pipe Outside Diameter", B, ADD_NEW_FIELD),
    *_one("DENSITY(Kg/m3)", "Kg/m3", "Fluid Density", A, ADD_NEW_FIELD, True),
    *_trio("FLOW(m3/hr)", "m3/hr", _NEW_F, ADD_NEW_FIELD),
    *_trio("PRESSURE (Kg/cm2 g)", _KGCM2G, _NEW_P, ADD_NEW_FIELD),
    *_trio("TEMP. (°C)", "°C", _NEW_T, ADD_NEW_FIELD),
    *_one("BORE DIAMETER(mm)", "mm", "Orifice Bore Diameter", B, ADD_NEW_FIELD, note="result of the orifice sizing"),
    *_one("PLATE THICKNESS (mm)", "mm", "Plate Thickness", B, ADD_NEW_FIELD),
    *_one("DP AT MAX.FLOW (mmWC)", "mmWC", "Differential Pressure at Maximum Flow", B, ADD_NEW_FIELD,
          note="result of the orifice sizing"),
    *_one("MAX.ALLOWABLE PRESSURE LOSS(mmWC)", "mmWC", "Maximum Allowable Pressure Loss", A, ADD_NEW_FIELD, True),
    *_one("BETA RATIO", "", "Beta Ratio", B, ADD_NEW_FIELD, note="result of the orifice sizing"),
    MODEL, *_remarks())))

# ── 4. Flow Switch ──────────────────────────────────────────────────────────
_register(Profile("flow_switch", "", "FLOW SWITCH.xls", "ANNEXURE-I", (
    SL, TAG, TYPE_REF, PID, *_fluid(False, "Process Fluid / Service"), SERVICE_ID, LOCATION, LINE, LINESIZE_ID, AREA,
    *_trio("FLOW(lpm)", "lpm", _NEW_F, ADD_NEW_FIELD),
    *_trio("PRESSURE (Kg/cm2 g)", _KGCM2G, _NEW_P, ADD_NEW_FIELD),
    *_trio("TEMP.(°C)", "°C", _NEW_T, ADD_NEW_FIELD),
    *_one("DENSITY (kg/m3)", "kg/m3", "Density", A, ADD_NEW_FIELD, True),
    *_one("VISCOSITY (Cp)", "Cp", "Viscosity", A, ADD_NEW_FIELD, True),
    *_one("SETPOINT(lpm)", "lpm", "Flow Setpoint", A, ADD_NEW_FIELD, True,
          "independent of the normal flow - never filled from a flow range"),
    *_one("SETPOINT RANGE(lpm)", "lpm", "Setpoint Range", B, ADD_NEW_FIELD),
    MODEL, *_remarks())))

# ── 5. Ultrasonic Parshall Flume flow transmitter ───────────────────────────
_register(Profile("flow_transmitter", "Ultrasonic Parshall Flume", "FLOW TRANSMITTER-ULTRASONIC PARSHALL FLUME-R0.xls",
                  "ANNEXURE-I", (
    SL, TAG, TYPE_REF, PID, *_fluid(True), SERVICE_ID, LOCATION, LINE, AREA,
    *_one("CHANNEL MATERIAL", "", "Channel Material", B, ADD_NEW_FIELD),
    *_trio("FLOW(m3/hr)", "m3/hr", _FT_FLOW, EXISTS_DEFAULT),
    *_trio("PRESSURE (Kg/cm2 g)", _KGCM2G, _FT_PRESSURE, UNIT_REVIEW, note=_UNIT_NOTE),
    *_trio("TEMP.(°C)", "°C", _FT_TEMP, EXISTS_DEFAULT),
    *_one("HEIGHT AT OPER.FLOW (mm)", "mm", "Height at Operating Flow", A, ADD_NEW_FIELD, True,
          "liquid head in the flume, not a flow rate"),
    *_one("HEIGHT AT MAX.FLOW (mm)", "mm", "Height at Maximum Flow", A, ADD_NEW_FIELD, True),
    *_one("SPECIFIC GRAVITY", "", "Specific Gravity", A, EXISTS_DEFAULT, True),
    *_one("VISCOSITY (Cp)", "Cp", "Viscosity", A, ADD_NEW_FIELD, True,
          "single value on the datasheet; kept separate from the existing Viscosity Min/Normal/Max"),
    *_one("THROAT WIDTH(mm)", "mm", "Throat Width", B, ADD_NEW_FIELD, note="flume dimension - not known from the IODB"),
    *_one("LIQUID DEPTH(mm)", "mm", "Liquid Depth", A, ADD_NEW_FIELD, True),
    *_one("CALIBRATION RANGE (Mtrs)", "Mtrs", "Calibration Range", B, ADD_NEW_FIELD),
    *_one("INSTRUMENT RANGE (Mtrs)", "Mtrs", "Instrument Range", B, ADD_NEW_FIELD),
    MODEL, *_remarks())))

# ── 6. Differential-pressure flow transmitter ───────────────────────────────
_register(Profile("flow_transmitter", "Differential Pressure", "FT-DP-R0.xls", "ANNEXURE-I", (
    SL, TAG, TYPE_REF, PID, *_fluid(True), LOCATION, LINE, AREA,
    *_trio("PRESSURE (Kg/cm2 g)", _KGCM2G, _FT_PRESSURE, UNIT_REVIEW, note=_UNIT_NOTE),
    *_trio("TEMP.(°C)", "°C", _FT_TEMP, EXISTS_DEFAULT),
    *_one("SPECIFIC GRAVITY", "", "Specific Gravity", A, EXISTS_DEFAULT, True),
    *_one("DP RANGE (mmWC)", "mmWC", "Differential Pressure Range", B, ADD_NEW_FIELD),
    *_one("INSTRUMENT RANGE (mmWC)", "mmWC", "Instrument Range", B, ADD_NEW_FIELD),
    MODEL, *_remarks()),
    "This annexure has no flow MIN/NOR/MAX columns, so none are selected by default; the existing flow fields stay optional."))

# ── 7. Thermal mass flow transmitter ────────────────────────────────────────
_register(Profile("flow_transmitter", "Thermal Mass", "FT-THERMAL MASS-R0.xls", "ANNEXURE-I", (
    SL, TAG, TYPE_REF, PID, *_fluid(True), SERVICE_ID, LOCATION, LINE, AREA,
    *_trio("FLOW(Nm3/hr)", "Nm3/hr", _FT_FLOW, UNIT_REVIEW,
           note="existing field is configured in m3/hr; the datasheet prints normalised flow (Nm3/hr) - no conversion"),
    *_trio("PRESSURE (mmWC)", "mmWC", _FT_PRESSURE, UNIT_REVIEW,
           note="existing field is configured in kg/cm2; this datasheet prints mmWC - no conversion"),
    *_trio("TEMP.(°C)", "°C", _FT_TEMP, EXISTS_DEFAULT),
    Heading("METER RANGE (Nm3/hr) - MIN", "Nm3/hr", B, ADD_NEW_FIELD, "Meter Range Minimum"),
    Heading("METER RANGE (Nm3/hr) - MAX", "Nm3/hr", B, ADD_NEW_FIELD, "Meter Range Maximum"),
    MODEL, *_remarks())))

# ── 8. Ultrasonic clamp-on flow transmitter ─────────────────────────────────
_register(Profile("flow_transmitter", "Ultrasonic Clamp-On", "FT-ULTRASONIC CLAMP ON-R0.xls", "ANNEXURE-I", (
    SL, TAG, TYPE_REF, PID, *_fluid(True), SERVICE_ID, LOCATION, LINE,
    *_one("LINE SIZE/MATERIAL", "", "Line Size / Material", R, MAPPING_REVIEW,
          note="size and pipe material in one heading; the IODB line size is already an identification column"),
    AREA,
    *_trio("FLOW(m3/hr)", "m3/hr", _FT_FLOW, EXISTS_DEFAULT),
    *_trio("PRESSURE (mmWC)", "mmWC", _FT_PRESSURE, UNIT_REVIEW,
           note="existing field is configured in kg/cm2; this datasheet prints mmWC - no conversion"),
    *_trio("TEMP.(°C)", "°C", _FT_TEMP, EXISTS_DEFAULT),
    *_trio("VELOCITY (m/s)", "m/s", ("Minimum Velocity", "Normal Velocity", "Maximum Velocity"), ADD_NEW_FIELD,
           note="flow velocity - not the same as flow rate or the measuring range"),
    *_one("SPECIFIC GRAVITY", "", "Specific Gravity", A, EXISTS_DEFAULT, True),
    *_one("VISCOSITY (Cp)", "Cp", "Viscosity", A, ADD_NEW_FIELD, True),
    *_one("MEASURING RANGE (m3/hr)", "m3/hr", "Measuring Range", B, ADD_NEW_FIELD,
          note="instrument measuring range - not the process flow"),
    MODEL, *_remarks())))

# ── 9. Level gauge - magnetic ───────────────────────────────────────────────
_LG_UNIT = "existing field is configured in bar(g); the datasheet prints Kg/Cm2 g - the datasheet unit is used, no conversion"
_register(Profile("level_gauge", "Magnetic", "LG-Magnetic Type-R0.xls", "ANNEXURE-I", (
    SL, TAG, TYPE_REF, PID, *_fluid(True), SERVICE_ID, LOCATION, AREA,
    *_one("SPECIFIC GRAVITY", "", "Specific Gravity", A, EXISTS_DEFAULT, True),
    *_one("VISCOSITY(cP)", "cP", "Viscosity", A, EXISTS_DEFAULT, True),
    *_trio("PRESSURE(Kg/Cm2 g)", "Kg/Cm2 g", _LG_PRESSURE, UNIT_REVIEW, note=_LG_UNIT),
    *_trio("TEMPERATURE(°C)", "°C", _LG_TEMP, EXISTS_DEFAULT),
    *_one("TANK TAG NO", "", "Tank Tag Number", B, ADD_NEW_FIELD, note="may come from process, mechanical or equipment engineering"),
    *_one("TANK TYPE", "", "Tank Type", B, ADD_NEW_FIELD),
    *_one("TANK MOC", "", "Tank MOC", B, ADD_NEW_FIELD),
    *_one("TANK HEIGHT(mtrs)", "mtrs", "Tank / Vessel Height", B, UNIT_REVIEW, note="existing field is configured in mm; the datasheet prints mtrs"),
    *_one("TANK DIAMETER(mtrs)", "mtrs", "Tank Diameter", B, UNIT_REVIEW, note="existing field is configured in mm; the datasheet prints mtrs"),
    *_one("PRESENCE OF AGITATION", "", "Presence of Agitation", A, ADD_NEW_FIELD, True),
    *_one("PRESENCE OF FUMES", "", "Presence of Fumes", A, ADD_NEW_FIELD, True,
          "yes / no on the datasheet; the existing Vapour / Fumes field is free text and is not reused"),
    *_one("C-C DISTANCE(mm)", "mm", "Centre-to-Centre Distance", B, EXISTS_OPTIONAL),
    MODEL, *_remarks())))

# ── 10. Level gauge - reflex ────────────────────────────────────────────────
_register(Profile("level_gauge", "Reflex", "LG-REFLEX TYPE-R0.xls", "ANNEXURE-I", (
    SL, TAG, TYPE_REF, PID, *_fluid(True), SERVICE_ID, LOCATION, AREA,
    *_one("SPECIFIC GRAVITY", "", "Specific Gravity", A, EXISTS_DEFAULT, True),
    *_trio("PRESSURE(Kg/Cm2 g)", "Kg/Cm2 g", _LG_PRESSURE, UNIT_REVIEW, note=_LG_UNIT),
    *_trio("TEMPERATURE(°C)", "°C", _LG_TEMP, EXISTS_DEFAULT),
    *_one("TANK TAG NO", "", "Tank Tag Number", B, ADD_NEW_FIELD, note="may come from process, mechanical or equipment engineering"),
    *_one("TANK TYPE", "", "Tank Type", B, ADD_NEW_FIELD),
    *_one("TANK MOC", "", "Tank MOC", B, ADD_NEW_FIELD),
    *_one("TANK HEIGHT (mtrs)", "mtrs", "Tank / Vessel Height", B, UNIT_REVIEW, note="existing field is configured in mm; the datasheet prints mtrs"),
    *_one("TANK DIAMETER(mtrs)", "mtrs", "Tank Diameter", B, UNIT_REVIEW, note="existing field is configured in mm; the datasheet prints mtrs"),
    *_one("PRESENCE OF AGITATION", "", "Presence of Agitation", A, ADD_NEW_FIELD, True),
    *_one("PRESENCE OF FUMES", "", "Presence of Fumes", A, ADD_NEW_FIELD, True,
          "yes / no on the datasheet; the existing Vapour / Fumes field is free text and is not reused"),
    *_one("CC DISTANCE(mm)", "mm", "Centre-to-Centre Distance", B, EXISTS_OPTIONAL),
    *_one("OVERALL VISIBLE LENGTH(mm)", "mm", "Overall Visible Length", B, ADD_NEW_FIELD),
    *_one("NO OF GLASS x SIZE(mm)", "mm", "Number of Glasses x Size", B, ADD_NEW_FIELD),
    MODEL, *_remarks()),
    "This annexure has no viscosity column, so viscosity is not part of the Reflex profile."))


# ── lookup / resolution ─────────────────────────────────────────────────────
def get_profile(type_key: str, subtype: Optional[str] = None) -> Optional[Profile]:
    return PROFILES.get((type_key, subtype or "")) or (PROFILES.get((type_key, "")) if not subtype else None)


def _gated(cfg, subtype):
    return [f for f in cfg.fields if not (f.subtype_only and subtype not in f.subtype_only)]


def resolve_fields(cfg, subtype: Optional[str] = None) -> list:
    """The ordered fields for this type/subtype. With a verified profile: annexure order first (units as printed,
    default / category / annexure heading attached), then the type's remaining fields as optional extras.
    Without one: the type's own fields, unchanged."""
    base = _gated(cfg, subtype)
    profile = get_profile(cfg.key, subtype)
    if profile is None:
        return base
    by_name = {f.name: f for f in base}
    out, used = [], set()
    for h in profile.headings:
        f = by_name.get(h.field) if h.field else None
        if f is None or f.name in used:
            continue
        used.add(f.name)
        out.append(dataclasses.replace(f, unit=h.unit or f.unit, category="process" if h.cls == A else "additional",
                                       default_selected=h.default, annexure_label=h.label))
    for f in base:
        if f.name not in used:
            out.append(dataclasses.replace(f, category="additional", default_selected=False))
    return out


def default_field_names(cfg, subtype: Optional[str] = None) -> list:
    """Names selected automatically: the verified profile's defaults, or every field for a type without a profile."""
    fields = resolve_fields(cfg, subtype)
    if get_profile(cfg.key, subtype) is None:
        return [f.name for f in fields]
    return [f.name for f in fields if f.default_selected]


def profile_info(cfg, subtype: Optional[str] = None) -> dict:
    p = get_profile(cfg.key, subtype)
    if p is None:
        return {"verified": False, "template": "", "sheet": "", "note": "No verified datasheet profile for this type - "
                "all configured parameters are offered and selected (existing behaviour); requires verification."}
    return {"verified": True, "template": p.template, "sheet": p.sheet, "note": p.review_note}


def comparison_rows() -> list:
    """The datasheet-to-generator comparison: one row per annexure heading of every profile."""
    rows, seen = [], set()
    for (t, st), p in PROFILES.items():
        if id(p) in seen:
            continue
        seen.add(id(p))
        for h in p.headings:
            rows.append({"type": t, "subtype": p.subtype, "template": p.template, "heading": h.label, "unit": h.unit,
                         "classification": {"A": "Process", "B": "Additional", "C": "Reference", "R": "Review"}[h.cls],
                         "field": h.field, "action": h.action, "default": h.default, "note": h.note})
    return rows
