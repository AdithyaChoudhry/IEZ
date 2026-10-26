"""Starting configurations for the graph designer. A template creates BLOCKS and PORTS (and seeds values that
exist in the source documents). It never creates wires - the engineer connects the ports."""
from __future__ import annotations

import copy
from typing import Any, Optional

from .common import clean, is_value
from .graph import (DEFAULT_ZONES, LIBRARY, MOTOR_SIGNALS, MOTOR_STARTERS, VALVE_SIGNALS, VALVE_TYPES, _p, find_node,
                    new_graph, new_node, ports_for, signal_ports)
from .graph_scene import ML, NW, TOP_H, ZW, node_height

ZONE_INDEX = {z["id"]: i for i, z in enumerate(DEFAULT_ZONES)}

# id -> definition. field: (component, port profile) ; card: component type of the system block
TEMPLATES: dict[str, dict] = {
    "AI_2WIRE_STANDARD": {"name": "AI 4-20 mA, 2-wire", "field": ("other_instrument", "AI_2WIRE"), "card": ("plc_ai", None)},
    "AI_4WIRE_STANDARD": {"name": "AI 4-20 mA, 4-wire (separate power)", "field": ("other_instrument", "AI_4WIRE"), "card": ("plc_ai", None), "power": True},
    "AI_2WIRE_HART": {"name": "AI 2-wire HART", "field": ("other_instrument", "AI_2WIRE"), "card": ("plc_ai", None), "hart": True},
    "AO_STANDARD": {"name": "AO 4-20 mA", "field": ("control_valve", "AO"), "card": ("plc_ao", None)},
    "DI_DRY_CONTACT": {"name": "DI dry contact", "field": ("other_instrument", "DI_DRY"), "card": ("plc_di", None)},
    "DI_POWERED_CONTACT": {"name": "DI powered contact", "field": ("other_instrument", "DI_POWERED"), "card": ("plc_di", None), "power": True},
    "DO_SOLENOID": {"name": "DO solenoid", "field": ("solenoid", "DO"), "card": ("plc_do", None)},
    "RTD_2WIRE": {"name": "RTD 2-wire", "field": ("rtd", "RTD_2"), "card": ("plc_rtd", None)},
    "RTD_3WIRE": {"name": "RTD 3-wire", "field": ("rtd", "RTD_3"), "card": ("plc_rtd", None)},
    "RTD_4WIRE": {"name": "RTD 4-wire", "field": ("rtd", "RTD_4"), "card": ("plc_rtd", None)},
    "TC_STANDARD": {"name": "Thermocouple", "field": ("thermocouple", "TC"), "card": ("plc_tc", None)},
    "PULSE_INPUT": {"name": "Pulse / frequency input", "field": ("flow_transmitter", "PULSE"), "card": ("plc", "SYS_PULSE")},
    "ANALYZER": {"name": "Analyzer (4-wire)", "field": ("analyzer", "AI_4WIRE"), "card": ("plc_ai", None), "power": True},
    "MOTOR_DOL": {"name": "Motor - DOL", "motor": "DOL"},
    "MOTOR_STAR_DELTA": {"name": "Motor - Star-Delta", "motor": "STAR_DELTA"},
    "MOTOR_SOFT_STARTER": {"name": "Motor - Soft starter", "motor": "SOFT_STARTER"},
    "MOTOR_VFD": {"name": "Motor - VFD", "motor": "VFD"},
    "MOV": {"name": "Motor-operated valve", "valve": "MOV", "device": "mov"},
    "CONTROL_VALVE": {"name": "Modulating control valve", "valve": "MODULATING", "device": "control_valve"},
    "CUSTOM": {"name": "Custom (empty canvas)"},
}


def template_list() -> list[dict]:
    return [{"id": k, "name": v["name"], "kind": "motor" if "motor" in v else ("valve" if "valve" in v else "standard")} for k, v in TEMPLATES.items()]


def _guess_device(itype: str, fallback: str) -> str:
    t = (itype or "").upper()
    if fallback != "other_instrument":
        return fallback
    for key, comp in (("PRESSURE", "pressure_transmitter"), ("LEVEL", "level_transmitter"), ("TEMPERATURE", "temperature_transmitter"),
                      ("FLOW", "flow_transmitter")):
        if key in t:
            return comp
    return fallback


def signal_catalog(graph: dict) -> list[dict]:
    p = graph.get("params", {})
    if p.get("starter"):
        return [copy.deepcopy(MOTOR_SIGNALS[i]) for i in MOTOR_STARTERS[p["starter"]]["signals"]]
    if p.get("valve_type"):
        return [copy.deepcopy(VALVE_SIGNALS[i]) for i in VALVE_TYPES[p["valve_type"]]["signals"]]
    return []


def apply_signals(graph: dict, selected: list[str]) -> dict:
    """(Re)create the per-signal ports on the blocks that carry signals. Ports keep their terminal / I/O selection
    when the signal stays selected; wires to de-selected signals are removed."""
    cat = {s["id"]: s for s in signal_catalog(graph)}
    chosen = [cat[i] for i in selected if i in cat]
    graph["signals"] = [s["id"] for s in chosen]
    for n in graph["nodes"]:
        mode = n.get("props", {}).get("carries_signals")
        if not mode:
            continue
        side = "left" if mode == "system" else "right"
        old = {p["id"]: p for p in n["ports"] if p.get("signal_id")}
        keep = [p for p in n["ports"] if not p.get("signal_id")]
        new = signal_ports(chosen, side)
        for p in new:
            if p["id"] in old:
                p["terminal"], p["io_index"] = old[p["id"]].get("terminal", ""), old[p["id"]].get("io_index")
        n["ports"] = keep + new
    live = {(n["id"], p["id"]) for n in graph["nodes"] for p in n["ports"]}
    graph["edges"] = [e for e in graph["edges"] if (e["from_node"], e["from_port"]) in live and (e["to_node"], e["to_port"]) in live]
    return graph


def _place(graph: dict, datas: dict) -> None:
    stack: dict[str, float] = {}
    for n in graph["nodes"]:
        zi = ZONE_INDEX.get(n["zone"], 0)
        n["x"] = ML + zi * ZW + (ZW - NW) / 2
        y = stack.get(n["zone"], TOP_H + 40)
        n["y"] = y
        stack[n["zone"]] = y + node_height(n, graph, datas) + 40


def build_template(template_id: str, tag: str, loop: str, datas: dict, params: Optional[dict] = None) -> dict:
    spec = TEMPLATES.get(template_id)
    if spec is None:
        raise ValueError(f"Unknown template '{template_id}'")
    data = datas.get(tag) or {}
    F = data.get("fields", {})
    val = lambda k: (clean(F.get(k, {}).get("value", "")) if is_value(clean(F.get(k, {}).get("value", ""))) else "")
    g = new_graph(tag, loop, template_id)
    g["params"] = {}
    n_io = len(data.get("signals", []))
    counter = [0]

    def add(component: str, zone: str = "", profile: Optional[str] = None, props: Optional[dict] = None, tagtxt: str = "") -> dict:
        counter[0] += 1
        node = new_node(component, f"n{counter[0]}", tagtxt, zone, profile=profile, props=props)
        g["nodes"].append(node)
        return node

    if template_id == "CUSTOM":
        return g
    jb_props = {"jb_tag": val("JB_TAG")}
    if "motor" in spec:
        g["params"]["starter"] = spec["motor"]
        add("motor", "field")
        starter_c = {"DOL": "mcc", "STAR_DELTA": "mcc", "SOFT_STARTER": "soft_starter", "VFD": "vfd"}[spec["motor"]]
        motor = g["nodes"][0]
        motor["ports"] = [_p(f"u{i}", lab, "power", "", "ANY", "right", True) for i, lab in enumerate(("U", "V", "W", "PE"))]
        st = add(starter_c, "marshalling", props={"carries_signals": "starter"})
        st["ports"] = [_p(f"u{i}", lab, "power", "", "ANY", "left", True) for i, lab in enumerate(("U", "V", "W", "PE"))]
        add("plc", "system", props={"carries_signals": "system"})
        add("control_function", "control")
    elif "valve" in spec:
        g["params"]["valve_type"] = spec["valve"]
        add(spec["device"], "field", profile="NONE", props={"carries_signals": "device"})
        add("junction_box", "jb", props=jb_props)
        add("marshalling_cabinet", "marshalling")
        add("plc", "system", props={"carries_signals": "system"})
        add("control_function", "control")
    else:
        comp, prof = spec["field"]
        field = add(_guess_device(val("INSTRUMENT_TYPE"), comp), "field", profile=prof, props={"hart": True} if spec.get("hart") else {})
        jb = add("junction_box", "jb", props=jb_props)
        tp, tm = val("JB_TERMINAL_PLUS"), val("JB_TERMINAL_MINUS")
        for p in jb["ports"]:
            if p["id"] == "t1":
                p["terminal"] = tp
            if p["id"] == "t2":
                p["terminal"] = tm
        add("marshalling_cabinet", "marshalling")
        if spec.get("power"):
            add("power_supply", "marshalling")
        card, cprof = spec["card"]
        sysn = add(card, "system", profile=cprof)
        if n_io == 1:
            sysn["props"]["io_index"] = 0
        add("control_function", "control")
    if len(data.get("signals", [])) == 1:
        for n in g["nodes"]:
            if n["props"].get("carries_signals") == "system":
                n["props"]["io_index"] = 0
    g["signals"] = []
    apply_signals(g, [])
    _place(g, datas)
    return g


def duplicate_for_tag(graph: dict, target_tag: str, target_loop: str, datas: dict) -> tuple[dict, list[str]]:
    """Copy a designed loop onto another tag. Source-derived values are re-read for the target tag; values that are
    specific to the old loop (terminals, cable tags/lengths, I/O channel) are cleared and reported, never copied."""
    g = copy.deepcopy(graph)
    old = g.get("tag", "")
    report: list[str] = []
    g["tag"], g["loop"] = target_tag, target_loop
    data = datas.get(target_tag) or {}
    F = data.get("fields", {})
    val = lambda k: clean(F.get(k, {}).get("value", "")) if is_value(clean(F.get(k, {}).get("value", ""))) else ""
    for n in g["nodes"]:
        if n.get("tag") == old:
            n["tag"] = ""
        if n["type"] == "junction_box":
            jb = val("JB_TAG")
            n["props"]["jb_tag"] = jb
            n["tag"] = ""
            report.append(f"Junction box: {jb or 'not in IODB for ' + target_tag} (from IODB)")
            n["props"].pop("accept_difference", None)
        if n["type"] in ("junction_box", "marshalling_cabinet", "terminal_strip", "terminal_block", "local_panel", "connector", "custom_block", "package_panel"):
            for p in n["ports"]:
                p["terminal"] = ""
            if n["type"] == "junction_box":
                for p in n["ports"]:
                    if p["id"] == "t1":
                        p["terminal"] = val("JB_TERMINAL_PLUS")
                    if p["id"] == "t2":
                        p["terminal"] = val("JB_TERMINAL_MINUS")
            report.append(f"{n.get('tag') or n['label']}: terminal numbers cleared - enter the terminals for {target_tag}")
        if LIBRARY.get(n["type"], {}).get("system"):
            n["props"].pop("io_override", None)
            n_io = len(data.get("signals", []))
            n["props"]["io_index"] = 0 if n_io == 1 else None
            for p in n["ports"]:
                p["io_index"] = 0 if (n_io == 1 and p.get("signal_id")) else None
            report.append(f"{n.get('tag') or n['label']}: I/O channel re-read from the I/O Assignment "
                          f"({'1 row' if n_io == 1 else 'select the row' if n_io else 'no row found'})")
    for c in g["cables"]:
        if c.get("iodb"):
            report.append(f"Cable {c['id']}: re-read from IODB ({c['iodb']})")
        else:
            c["tag"], c["length"] = "", ""
            c.setdefault("override", {}).pop("tag", None)
            c["accept_difference"] = False
            report.append(f"Cable {c['id']}: manual tag / length cleared (they belonged to {old})")
    return g, report
