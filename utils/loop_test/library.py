"""
Loop type library, component catalog and built-in templates - all DATA.

Nothing here draws anything: the renderer is generic and only reads a LoopConfiguration. Adding a
loop type, a motor starter or a protocol (Modbus, Profibus, Foundation Fieldbus, Ethernet...) means
adding an entry, not writing new drawing code.
"""
from __future__ import annotations

import copy
from typing import Any, Optional

# ── components ──────────────────────────────────────────────────────────────
COMPONENT_KINDS: dict[str, dict[str, str]] = {
    "field_instrument": {"label": "Field instrument", "group": "field"},
    "motor": {"label": "Motor", "group": "field"},
    "valve": {"label": "Valve / actuator", "group": "field"},
    "junction_box": {"label": "Junction box", "group": "field"},
    "local_panel": {"label": "Local panel", "group": "field"},
    "connector": {"label": "Connector / plug", "group": "interface"},
    "terminal_strip": {"label": "Terminal strip", "group": "interface"},
    "marshalling": {"label": "Marshalling panel", "group": "interface"},
    "zener_barrier": {"label": "Zener barrier", "group": "interface"},
    "isolator": {"label": "Isolator", "group": "interface"},
    "signal_conditioner": {"label": "Signal conditioner", "group": "interface"},
    "surge_protection": {"label": "Surge protection", "group": "interface"},
    "relay": {"label": "Relay / interface", "group": "interface"},
    "fuse": {"label": "Fuse", "group": "interface"},
    "mcc": {"label": "MCC / starter panel", "group": "interface"},
    "vfd": {"label": "VFD", "group": "interface"},
    "power_supply": {"label": "Power supply", "group": "interface"},
    "shield_bar": {"label": "Shield bar", "group": "interface"},
    "earth": {"label": "Earth", "group": "interface"},
    "custom_box": {"label": "Custom box", "group": "interface"},
    "remote_io": {"label": "Remote I/O", "group": "system"},
    "plc": {"label": "PLC", "group": "system"},
    "dcs": {"label": "DCS", "group": "system"},
}
FIELD_KINDS = {"field_instrument", "motor", "valve"}
SYSTEM_KINDS = {"plc", "dcs", "remote_io"}

# ── wires and shielding ─────────────────────────────────────────────────────
WIRE_ROLES = {
    "SIGNAL_PLUS": "Signal +", "SIGNAL_MINUS": "Signal -", "COMMON": "Common", "EARTH": "Earth", "SHIELD": "Shield / drain",
    "SPARE": "Spare", "POWER_PLUS": "Power +", "POWER_MINUS": "Power -", "POWER_L": "Power L", "POWER_N": "Power N",
    "CONTACT_NO": "Contact NO", "CONTACT_NC": "Contact NC", "CONTACT_COM": "Contact COM", "CMD_PLUS": "Command +",
    "CMD_MINUS": "Command -", "RTD_1": "RTD 1", "RTD_2": "RTD 2", "RTD_3": "RTD 3 (lead compensation)",
    "EXC_PLUS": "Excitation +", "SENSE_PLUS": "Sense +", "SENSE_MINUS": "Sense -", "EXC_MINUS": "Excitation -",
    "TC_PLUS": "TC +", "TC_MINUS": "TC -", "CUSTOM": "Custom",
}
SHIELD_TYPES = {"none": "No shield", "individual": "Individual shield", "overall": "Overall / common shield",
                "individual_overall": "Individual + overall shield"}
SHIELD_TERMINATIONS = {"field": "Field end", "jb": "JB end", "marshalling": "Marshalling end",
                       "control_room": "Control-room end", "both": "Both ends", "floating_one_end": "Floating one end",
                       "custom": "Custom"}
ORIENTATIONS = ("vertical", "horizontal")
FLOW_DIRECTIONS = {"field_to_system": "Field → PLC/DCS", "system_to_field": "PLC/DCS → Field", "bidirectional": "Bidirectional"}

# ── signal catalogs (nothing is pre-selected: the engineer chooses) ─────────
def _s(id_: str, name: str, stype: str, direction: str) -> dict:
    return {"id": id_, "name": name, "signal_type": stype, "direction": direction}


MOTOR_BASE = ["start", "stop", "run_feedback", "fault", "trip", "local_remote", "ready", "emergency_stop",
              "current_feedback", "other"]
MOTOR_SIGNALS = {
    "start": _s("start", "Start command", "DO", "system_to_field"),
    "stop": _s("stop", "Stop command", "DO", "system_to_field"),
    "run_feedback": _s("run_feedback", "Run feedback", "DI", "field_to_system"),
    "fault": _s("fault", "Fault", "DI", "field_to_system"),
    "trip": _s("trip", "Trip", "DI", "field_to_system"),
    "local_remote": _s("local_remote", "Local / remote status", "DI", "field_to_system"),
    "ready": _s("ready", "Ready", "DI", "field_to_system"),
    "emergency_stop": _s("emergency_stop", "Emergency stop / trip status", "DI", "field_to_system"),
    "current_feedback": _s("current_feedback", "Current feedback", "AI", "field_to_system"),
    "speed_reference": _s("speed_reference", "Speed reference", "AO", "system_to_field"),
    "speed_feedback": _s("speed_feedback", "Speed feedback", "AI", "field_to_system"),
    "star_command": _s("star_command", "Star command", "DO", "system_to_field"),
    "delta_command": _s("delta_command", "Delta command", "DO", "system_to_field"),
    "star_status": _s("star_status", "Star status", "DI", "field_to_system"),
    "delta_status": _s("delta_status", "Delta status", "DI", "field_to_system"),
    "bypass_status": _s("bypass_status", "Bypass status", "DI", "field_to_system"),
    "other": _s("other", "Other signal", "DI", "field_to_system"),
}
MOTOR_STARTERS = {
    "DOL": {"label": "DOL", "signals": MOTOR_BASE},
    "STAR_DELTA": {"label": "Star-Delta", "signals": MOTOR_BASE[:-1] + ["star_command", "delta_command", "star_status",
                                                                          "delta_status", "other"]},
    "SOFT_STARTER": {"label": "Soft starter", "signals": MOTOR_BASE[:-1] + ["bypass_status", "other"]},
    "VFD": {"label": "VFD", "signals": MOTOR_BASE[:-1] + ["speed_reference", "speed_feedback", "other"]},
}

VALVE_SIGNALS = {
    "open_command": _s("open_command", "Open command", "DO", "system_to_field"),
    "close_command": _s("close_command", "Close command", "DO", "system_to_field"),
    "stop_command": _s("stop_command", "Stop command", "DO", "system_to_field"),
    "open_feedback": _s("open_feedback", "Open feedback", "DI", "field_to_system"),
    "close_feedback": _s("close_feedback", "Close feedback", "DI", "field_to_system"),
    "fault": _s("fault", "Fault / trip", "DI", "field_to_system"),
    "solenoid": _s("solenoid", "Solenoid", "DO", "system_to_field"),
    "ao_command": _s("ao_command", "Position command (AO)", "AO", "system_to_field"),
    "position_feedback": _s("position_feedback", "Position feedback (AI)", "AI", "field_to_system"),
    "limit_open": _s("limit_open", "Limit switch open", "DI", "field_to_system"),
    "limit_close": _s("limit_close", "Limit switch close", "DI", "field_to_system"),
    "running": _s("running", "Running", "DI", "field_to_system"),
    "local_remote": _s("local_remote", "Local / remote", "DI", "field_to_system"),
    "torque_trip": _s("torque_trip", "Torque trip", "DI", "field_to_system"),
}
VALVE_TYPES = {
    "ONOFF": {"label": "ON/OFF valve", "signals": ["open_command", "close_command", "open_feedback", "close_feedback",
                                                     "fault", "solenoid"]},
    "MODULATING": {"label": "Modulating control valve", "signals": ["ao_command", "position_feedback", "limit_open",
                                                                    "limit_close", "fault"]},
    "MOV": {"label": "Motor-operated valve", "signals": ["open_command", "close_command", "stop_command", "open_feedback",
                                                        "close_feedback", "running", "fault", "local_remote", "torque_trip"]},
}

# ── loop types ──────────────────────────────────────────────────────────────
def _lt(label: str, category: str, signal_type: Optional[str], direction: str, wires: list[str],
        components: list[str], params: Optional[dict] = None, status: str = "available") -> dict:
    return {"label": label, "category": category, "signal_type": signal_type, "direction": direction,
            "wires": wires, "components": components, "params": params or {}, "status": status}


FIELD_CHAIN = ["field_instrument", "junction_box", "marshalling", "plc"]
RTD_WIRES = {
    "2": ["RTD_1", "RTD_2"],
    "3": ["RTD_1", "RTD_2", "RTD_3"],
    "4": ["EXC_PLUS", "SENSE_PLUS", "SENSE_MINUS", "EXC_MINUS"],
}
LOOP_TYPES: dict[str, dict] = {
    "AI_2WIRE": _lt("AI 4–20 mA, 2-wire", "Standard Instrument", "AI", "field_to_system",
                    ["SIGNAL_PLUS", "SIGNAL_MINUS"], FIELD_CHAIN, {"hart": "bool"}),
    "AI_4WIRE": _lt("AI 4–20 mA, 4-wire (separate power)", "Standard Instrument", "AI", "field_to_system",
                    ["SIGNAL_PLUS", "SIGNAL_MINUS"], FIELD_CHAIN, {"hart": "bool", "power_wires": "int"}),
    "AO": _lt("AO 4–20 mA", "Standard Instrument", "AO", "system_to_field", ["SIGNAL_PLUS", "SIGNAL_MINUS"],
              ["plc", "marshalling", "junction_box", "field_instrument"], {"hart": "bool", "wires_mode": "2|4"}),
    "DI": _lt("DI (contact / status)", "Standard Instrument", "DI", "field_to_system", ["SIGNAL_PLUS", "SIGNAL_MINUS"],
              FIELD_CHAIN, {"contact": "NO|NC|dry|powered"}),
    "DO": _lt("DO (command)", "Standard Instrument", "DO", "system_to_field", ["CMD_PLUS", "CMD_MINUS"],
              ["plc", "marshalling", "junction_box", "field_instrument"], {"load": "solenoid|relay|contactor|actuator|other"}),
    "RTD": _lt("RTD", "Standard Instrument", "RTD", "field_to_system", RTD_WIRES["3"], FIELD_CHAIN,
               {"rtd_wires": "2|3|4 (required)"}),
    "TC": _lt("Thermocouple", "Standard Instrument", "TC", "field_to_system", ["TC_PLUS", "TC_MINUS"], FIELD_CHAIN,
              {"tc_type": "required", "extension_cable": "bool"}),
    "PULSE": _lt("Pulse / frequency", "Standard Instrument", "PI", "field_to_system", ["SIGNAL_PLUS", "SIGNAL_MINUS"],
                 FIELD_CHAIN, {"supply": "bool", "common": "bool"}),
    "MOTOR": _lt("Motor loop", "Motor", None, "bidirectional", ["SIGNAL_PLUS", "SIGNAL_MINUS"],
                 ["plc", "marshalling", "mcc", "motor"], {"starter": "DOL|STAR_DELTA|SOFT_STARTER|VFD (required)"}),
    "VALVE": _lt("Valve / actuator loop", "Valve", None, "bidirectional", ["SIGNAL_PLUS", "SIGNAL_MINUS"],
                 ["plc", "marshalling", "junction_box", "valve"], {"valve_type": "ONOFF|MODULATING|MOV (required)"}),
    "ANALYZER": _lt("Analyzer loop", "Analyzer", "AI", "field_to_system", ["SIGNAL_PLUS", "SIGNAL_MINUS"], FIELD_CHAIN,
                    {"hart": "bool"}),
    "PACKAGE": _lt("Package interface", "Package Interface", None, "bidirectional", ["SIGNAL_PLUS", "SIGNAL_MINUS"],
                   ["plc", "marshalling", "local_panel"]),
    "REMOTE_IO": _lt("Remote I/O channel", "Remote I/O", None, "bidirectional", ["SIGNAL_PLUS", "SIGNAL_MINUS"],
                     ["field_instrument", "junction_box", "remote_io"]),
    "CUSTOM": _lt("Custom loop", "Custom", None, "bidirectional", ["SIGNAL_PLUS", "SIGNAL_MINUS"], ["field_instrument", "plc"]),
    # architecture hooks for later phases - listed, not selectable yet
    "COMM_MODBUS": _lt("Modbus device (planned)", "Fieldbus", None, "bidirectional", [], [], status="planned"),
    "COMM_PROFIBUS": _lt("Profibus device (planned)", "Fieldbus", None, "bidirectional", [], [], status="planned"),
    "COMM_FF": _lt("Foundation Fieldbus device (planned)", "Fieldbus", None, "bidirectional", [], [], status="planned"),
    "COMM_ETHERNET": _lt("Ethernet field device (planned)", "Fieldbus", None, "bidirectional", [], [], status="planned"),
}

BUILTIN_TEMPLATES: dict[str, dict] = {
    "AI_2WIRE_STANDARD": {"name": "AI 2-wire standard", "loop_type": "AI_2WIRE", "params": {}},
    "AI_4WIRE_STANDARD": {"name": "AI 4-wire standard", "loop_type": "AI_4WIRE", "params": {}},
    "AO_4_20MA": {"name": "AO 4–20 mA", "loop_type": "AO", "params": {}},
    "DI_DRY_CONTACT": {"name": "DI dry contact", "loop_type": "DI", "params": {"contact": "dry"}},
    "DO_SOLENOID": {"name": "DO solenoid", "loop_type": "DO", "params": {"load": "solenoid"}},
    "RTD_3WIRE": {"name": "RTD 3-wire", "loop_type": "RTD", "params": {"rtd_wires": "3"}},
    "RTD_4WIRE": {"name": "RTD 4-wire", "loop_type": "RTD", "params": {"rtd_wires": "4"}},
    "TC_STANDARD": {"name": "Thermocouple", "loop_type": "TC", "params": {}},
    "HART_AI": {"name": "HART AI", "loop_type": "AI_2WIRE", "params": {"hart": True}},
    "MOTOR_DOL": {"name": "Motor – DOL", "loop_type": "MOTOR", "params": {"starter": "DOL"}},
    "MOTOR_STAR_DELTA": {"name": "Motor – Star-Delta", "loop_type": "MOTOR", "params": {"starter": "STAR_DELTA"}},
    "MOTOR_SOFT_STARTER": {"name": "Motor – Soft starter", "loop_type": "MOTOR", "params": {"starter": "SOFT_STARTER"}},
    "MOTOR_VFD": {"name": "Motor – VFD", "loop_type": "MOTOR", "params": {"starter": "VFD"}},
    "MOV": {"name": "Motor-operated valve", "loop_type": "VALVE", "params": {"valve_type": "MOV"}},
    "CONTROL_VALVE": {"name": "Modulating control valve", "loop_type": "VALVE", "params": {"valve_type": "MODULATING"}},
    "CUSTOM": {"name": "Custom loop", "loop_type": "CUSTOM", "params": {}},
}


def signal_catalog(loop_type: str, params: dict) -> list[dict]:
    """Signals the engineer may SELECT for this loop (never pre-selected for motor / valve)."""
    if loop_type == "MOTOR":
        starter = params.get("starter")
        return [copy.deepcopy(MOTOR_SIGNALS[i]) for i in MOTOR_STARTERS.get(starter, {}).get("signals", [])]
    if loop_type == "VALVE":
        vt = params.get("valve_type")
        return [copy.deepcopy(VALVE_SIGNALS[i]) for i in VALVE_TYPES.get(vt, {}).get("signals", [])]
    return []


def wires_for(loop_type: str, params: dict) -> list[str]:
    """DEFAULT conductor roles for the loop type; the engineer may add / remove / rename them."""
    if loop_type == "RTD":
        return list(RTD_WIRES.get(str(params.get("rtd_wires", "")), []))
    roles = list(LOOP_TYPES.get(loop_type, {}).get("wires", []))
    if loop_type == "AI_4WIRE":
        n = int(params.get("power_wires", 2) or 2)
        roles = (["POWER_PLUS", "POWER_MINUS"] if n == 2 else ["POWER_L", "POWER_N", "EARTH"][:n]) + roles
    if loop_type == "DI" and params.get("contact") in ("NO", "NC", "dry"):
        roles = ["CONTACT_COM", "CONTACT_NO" if params.get("contact") != "NC" else "CONTACT_NC"]
    if loop_type == "PULSE" and params.get("common"):
        roles = roles + ["COMMON"]
    return roles


def _wire(role: str, idx: int) -> dict:
    return {"role": role, "label": WIRE_ROLES.get(role, role), "colour": "", "number": "", "terminal_from": "", "terminal_to": ""}


def default_link(from_id: str, to_id: str, roles: list[str], cable_source: str = "none") -> dict:
    return {"from_id": from_id, "to_id": to_id, "wires": [_wire(r, i) for i, r in enumerate(roles)],
            "cable": {"source": cable_source, "tag": "", "type": "", "length": "", "cores": "", "pairs": "",
                      "shield_type": None, "shield_termination": None, "termination_note": ""}}


MULTI_SIGNAL_TYPES = ("MOTOR", "VALVE")


def signal_wires(signals: list[dict]) -> list[dict]:
    """Default conductors of a multi-signal loop: one pair per selected signal (editable by the engineer)."""
    out = []
    for s in signals:
        out.append({**_wire("SIGNAL_PLUS", 0), "label": f"{s['name']} +"})
        out.append({**_wire("SIGNAL_MINUS", 1), "label": f"{s['name']} -"})
    return out


def reconcile_links(config: dict) -> dict:
    """Make sure every consecutive pair of MAIN components has a link (keeps existing links by endpoints)."""
    if config.get("manual_links"):
        # the engineer drew the connections: keep exactly those (dropping any whose end was deleted)
        ids = {c["id"] for c in config["components"]}
        seen, kept = set(), []
        for l in config.get("links", []):
            key = (l["from_id"], l["to_id"])
            if l["from_id"] in ids and l["to_id"] in ids and l["from_id"] != l["to_id"] and key not in seen:
                seen.add(key)
                kept.append(l)
        config["links"] = kept
        return config
    main = [c for c in config["components"] if c.get("placement", "main") == "main"]
    existing = {(l["from_id"], l["to_id"]): l for l in config.get("links", [])}
    roles = wires_for(config["loop_type"], config.get("params", {}))
    links = []
    for a, b in zip(main, main[1:]):
        link = existing.get((a["id"], b["id"]))
        if link is None:
            kinds = {a["kind"], b["kind"]}
            if kinds & FIELD_KINDS and "junction_box" in kinds:
                src = "branch"                    # field device <-> junction box
            elif "junction_box" in kinds:
                src = "main"                      # junction box <-> panel side
            else:
                src = "none"                      # the engineer chooses where cable data comes from
            link = default_link(a["id"], b["id"], roles, src)
        links.append(link)
    if config["loop_type"] in MULTI_SIGNAL_TYPES:          # wires follow the selected signals until the engineer edits them
        for link in links:
            if link.get("auto_wires", True):
                link["wires"] = signal_wires(config.get("signals", []))
                link["auto_wires"] = True
    for c in config["components"]:                        # side components (e.g. power supply) link to their target
        if c.get("placement") == "side" and c.get("attach_to"):
            key = (c["id"], c["attach_to"])
            links.append(existing.get(key) or default_link(c["id"], c["attach_to"], ["POWER_PLUS", "POWER_MINUS"]))
    config["links"] = links
    return config


def new_component(kind: str, idx: int, label: str = "", placement: str = "main", attach_to: str = "") -> dict:
    return {"id": f"c{idx}", "kind": kind, "label": label or COMPONENT_KINDS.get(kind, {}).get("label", kind),
            "tag": "", "placement": placement, "attach_to": attach_to, "terminals": [], "notes": ""}


def new_config(loop_type: str, params: Optional[dict] = None, selected_signals: Optional[list[str]] = None,
               template_id: str = "", tag_no: str = "", loop_number: str = "", project_id: str = "") -> dict:
    """A fresh, editable LoopConfiguration for a loop type (template defaults, not engineering decisions)."""
    if loop_type not in LOOP_TYPES or LOOP_TYPES[loop_type]["status"] != "available":
        raise ValueError(f"Unknown or unavailable loop type '{loop_type}'")
    params = dict(params or {})
    spec = LOOP_TYPES[loop_type]
    comps = [new_component(k, i + 1) for i, k in enumerate(spec["components"])]
    if loop_type == "AI_4WIRE":
        comps.append(new_component("power_supply", len(comps) + 1, "Power supply", "side", comps[0]["id"]))
    catalog = {s["id"]: s for s in signal_catalog(loop_type, params)}
    if catalog:
        signals = [dict(catalog[i], io_index=None) for i in (selected_signals or []) if i in catalog]
    elif spec["signal_type"]:
        signals = [{"id": "s1", "name": spec["label"], "signal_type": spec["signal_type"],
                    "direction": spec["direction"], "io_index": 0}]
    else:
        signals = []
    config = {
        "project_id": project_id, "tag_no": tag_no, "loop_number": loop_number, "loop_type": loop_type,
        "template_id": template_id, "category": spec["category"], "params": params, "signals": signals,
        "components": comps, "links": [],
        "layout": {"orientation": "vertical", "flow_direction": spec["direction"]},
        "options": {"show_wire_table": True, "show_source_table": True},
        "overrides": {}, "notes": "",
    }
    return reconcile_links(config)


def library_payload(saved_templates: list[dict]) -> dict:
    return {
        "loop_types": {k: {**v, "id": k} for k, v in LOOP_TYPES.items()},
        "components": COMPONENT_KINDS, "wire_roles": WIRE_ROLES, "shield_types": SHIELD_TYPES,
        "shield_terminations": SHIELD_TERMINATIONS, "flow_directions": FLOW_DIRECTIONS,
        "motor_starters": {k: {"label": v["label"], "signals": [MOTOR_SIGNALS[i] for i in v["signals"]]}
                           for k, v in MOTOR_STARTERS.items()},
        "valve_types": {k: {"label": v["label"], "signals": [VALVE_SIGNALS[i] for i in v["signals"]]}
                        for k, v in VALVE_TYPES.items()},
        "builtin_templates": {k: {**v, "id": k, "builtin": True} for k, v in BUILTIN_TEMPLATES.items()},
        "saved_templates": saved_templates,
        "rtd_wires": RTD_WIRES,
    }
