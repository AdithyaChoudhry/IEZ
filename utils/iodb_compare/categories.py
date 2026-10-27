"""Engineering change categories for IODB columns.

Columns are matched by normalized header key (case/space/punctuation-insensitive), so
'MAIN CABLE LENGTH(MTRS)' and 'Main Cable Length (Mtrs)' fall in the same category.
A header that matches no rule goes to UNCATEGORISED - it is still compared and reported.
"""
from __future__ import annotations

import re

CATEGORIES = [
    ("01", "P&ID Information"),
    ("02", "Instrument Identification"),
    ("03", "Piping & Equipment Information"),
    ("04", "Signal / I/O Classification"),
    ("05", "Field Instrument - JB Cable & Termination"),
    ("06", "Main Cable & Panel Termination"),
    ("07", "Process Design Data"),
    ("08", "Alarm & Control Parameters"),
    ("09", "Power & Loop Configuration"),
    ("10", "Range & Calibration"),
    ("11", "Communication, Safety & Control System Integration"),
    ("12", "Engineering Remarks"),
]
UNCATEGORISED = ("99", "Uncategorised Columns")
CATEGORY_NAMES = dict(CATEGORIES + [UNCATEGORISED])


def header_key(name) -> str:
    """Comparison key for a header: unicode/space/case/punctuation-insensitive."""
    s = str(name).replace(" ", " ").replace("\n", " ")
    return re.sub(r"[\s_.\-/&]+", "", s).casefold()


_EXACT = {
    "01": ["revnumber", "rev", "status", "location", "area", "areacode", "areaclassification", "scopeofsupply", "pidno", "pid", "pidnumber"],
    "02": ["tagno", "tag", "tagnumber", "loopnumber", "equipmentdescription", "signaldescription", "instrumenttype",
           "instrumenttypename", "instrumentmeasuringtype"],
    "03": ["service", "line", "linemoc", "linesize", "equipmentno", "system", "subsystem"],
    "04": ["signaliotype", "signalcond", "signaltype"],
    "05": ["livednumber", "fieldcablenumbertoterminalbox", "instrumenttojbcabletagno", "instrumenttojbcable",
           "instrumenttojbcabletype", "signalto", "branchcablelength", "instrumentsideglandsize", "instrumentsideglandqty",
           "instrumentsidegland", "junctionbox", "junctionboxtagno", "jbtagno", "jbsideglandsize", "jbsideglandqty",
           "jbsidegland"],
    "06": ["maincabletagnumber", "maincabletype", "maincablelengthmtrs", "jbendglandsize", "panelendglandsize",
           "panelendglandqty", "corepairdetails"],
    "07": ["density", "viscocity", "viscosity", "specificgravity", "temperaturemin", "temperaturemax", "pressuremin",
           "pressuremax", "flowmin", "flowmax", "velocity", "dielectricconstant", "processconnectionsize", "rating"],
    "08": ["setpoint", "controlaction", "setpointforalarm", "setpointforalarmlowlow", "setpointforalarmlow",
           "setpointforalarmhigh", "setpointforalarmhighhigh", "interlockno", "contactstatus", "alarmuom", "alarmuom%",
           "llpriority", "lpriority", "hpriority", "hhpriority", "alarmprior", "digitalsignallevel", "dipriority",
           "deviationalarm", "deviationcomparision(%)"],
    "09": ["powersupply", "2wire4wire", "fieldpowerload", "vendorpackage", "looptype", "isnistype", "withirp", "soe",
           "looppowerindicator"],
    "10": ["processrange", "processunitofmeasurement", "calibrationrange", "calibrationunit", "calibirationrange",
           "calibirationunit", "instrange", "instrangeunit"],
    "11": ["hart", "harttagname", "sil", "redundantio", "contactdetails", "onsignalstatus", "offsignalstatus", "failaction",
           "iopanel", "racknode", "slot", "channelno", "plcno", "pulserate", "totalisertimedetail", "scantype", "exectime"],
    "12": ["remarks", "ifsprno"],
}
_LOOKUP = {k: code for code, keys in _EXACT.items() for k in keys}

# Fallback substrings for headers not listed above (project-specific variants).
_FALLBACK = [
    ("12", ("remark", "note", "comment")),
    ("08", ("alarm", "setpoint", "priority", "interlock")),
    ("10", ("range", "calib")),
    ("06", ("maincable", "panelend", "corepair")),
    ("05", ("jbside", "instrumentside", "branchcable", "junction", "instrumenttojb")),
    ("07", ("density", "visc", "gravity", "temperature", "pressure", "flow", "dielectric", "velocity")),
    ("09", ("power", "loop", "wire")),
    ("04", ("signal",)),
    ("03", ("line", "equipment", "system")),
    ("11", ("plc", "hart", "sil", "rack", "slot", "channel")),
    ("02", ("tag", "instrument")),
    ("01", ("pid", "area", "scope")),
]


def category_of(header) -> str:
    key = header_key(header)
    if key in _LOOKUP:
        return _LOOKUP[key]
    # strip a trailing "(unit)" and retry (e.g. "DENSITY (kg/m3)")
    base = header_key(re.sub(r"\([^)]*\)", "", str(header)))
    if base in _LOOKUP:
        return _LOOKUP[base]
    for code, needles in _FALLBACK:
        if any(n in base for n in needles):
            return code
    return UNCATEGORISED[0]
