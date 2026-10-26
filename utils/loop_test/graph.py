"""
Graph model for Loop Wiring (Test): the engineer-designed loop is a graph of NODES (components) that expose
explicit PORTS, joined by EDGES (wires). The graph is the single source of truth: validation, preview and
the Excel / PNG output are all produced from it, and nothing is ever connected because two blocks are "next
to each other" or because of the loop type.

A template only creates a starting set of nodes and ports (never wires). Wires exist only when the engineer
creates them (drag port -> port) or presses an explicit "connect +/- between these two blocks" helper, which
creates ordinary, editable edges.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Optional

from .library import MOTOR_SIGNALS, MOTOR_STARTERS, VALVE_SIGNALS, VALVE_TYPES

# ── zones (drawing columns) ─────────────────────────────────────────────────
DEFAULT_ZONES = [
    {"id": "field", "name": "FIELD INSTRUMENT", "sub": "Field process area", "visible": True},
    {"id": "jb", "name": "JUNCTION BOX", "sub": "", "visible": True},
    {"id": "marshalling", "name": "MARSHALLING CABINET", "sub": "", "visible": True},
    {"id": "system", "name": "SYSTEM CABINET", "sub": "", "visible": True},
    {"id": "control", "name": "CONTROL FUNCTION", "sub": "", "visible": True},
]
ORIENTATIONS = ("horizontal", "vertical", "custom")
SHIELD_TYPES = {"none": "None", "individual": "Individual", "overall": "Overall / common",
                "individual_overall": "Individual + overall"}
SHIELD_TERMINATIONS = {"": "Not defined", "field": "Field end", "jb": "JB end", "marshalling": "Marshalling end",
                       "control": "Control end", "both": "Both ends", "floating": "Floating", "custom": "Custom"}

# ── ports ───────────────────────────────────────────────────────────────────
KINDS = ("signal", "power", "shield", "earth", "common", "soft")
FAMILIES = ("AI", "AO", "DI", "DO", "RTD", "TC", "PULSE", "SOFT", "CUSTOM", "ANY")
FAMILY_ALIAS = {"HART": "AI", "FREQUENCY": "PULSE", "FREQ": "PULSE", "PI": "PULSE", "FI": "PULSE"}


def _p(pid: str, label: str, kind: str = "signal", pol: str = "", sig: str = "ANY", side: str = "right",
       required: bool = False, **kw: Any) -> dict:
    return {"id": pid, "label": label, "terminal": "", "kind": kind, "pol": pol, "sig": sig, "side": side,
            "required": required, "multi": False, "pair": "", "io_index": None, **kw}


def _sig(fam: str, side: str, req: bool = True, plus: str = "+", minus: str = "-", prefix: Optional[str] = None) -> list[dict]:
    pre = prefix if prefix is not None else fam
    return [_p("sp", f"{pre}{plus}", "signal", "+", fam, side, req), _p("sn", f"{pre}{minus}", "signal", "-", fam, side, req)]


def _shield(side: str, multi: bool = False) -> dict:
    return _p("sh", "SHIELD", "shield", "", "ANY", side, False, multi=multi)


# field-side device profiles -> ports (device drives the right-hand side of its box)
FIELD_PROFILES: dict[str, list[dict]] = {
    "AI_2WIRE": _sig("AI", "right", prefix="SIG") + [_shield("right")],
    "AI_4WIRE": [_p("pp", "P+", "power", "+", "ANY", "right", True), _p("pn", "P-", "power", "-", "ANY", "right", True)]
                + _sig("AI", "right", prefix="SIG") + [_shield("right")],
    "AO": _sig("AO", "right", prefix="AO") + [_shield("right")],
    "DI_DRY": [_p("sp", "DI+", "signal", "", "DI", "right", True), _p("sn", "DI-", "signal", "", "DI", "right", True), _shield("right")],
    "DI_POWERED": [_p("pp", "P+", "power", "+", "ANY", "right", True), _p("pn", "P-", "power", "-", "ANY", "right", True),
                   _p("sp", "DI+", "signal", "+", "DI", "right", True), _p("sn", "DI-", "signal", "-", "DI", "right", True),
                   _shield("right")],
    "DO": _sig("DO", "right", prefix="DO") + [_shield("right")],
    "RTD_2": _sig("RTD", "right", prefix="RTD") + [_shield("right")],
    "RTD_3": _sig("RTD", "right", prefix="RTD") + [_p("s3", "SENSE-", "signal", "-", "RTD", "right", True), _shield("right")],
    "RTD_4": _sig("RTD", "right", prefix="RTD")
             + [_p("s3", "SENSE+", "signal", "+", "RTD", "right", True), _p("s4", "SENSE-", "signal", "-", "RTD", "right", True), _shield("right")],
    "TC": _sig("TC", "right", prefix="TC") + [_shield("right")],
    "PULSE": _sig("PULSE", "right", prefix="PUL") + [_shield("right")],
    "NONE": [],
}
# system-side cards -> ports (card receives on the left-hand side of its box)
SYSTEM_PROFILES: dict[str, list[dict]] = {
    "AI": _sig("AI", "left", prefix="AI") + [_shield("left")],
    "AO": _sig("AO", "left", prefix="AO") + [_shield("left")],
    "DI": _sig("DI", "left", prefix="DI") + [_p("cm", "COM", "common", "", "DI", "left", False), _shield("left")],
    "DO": _sig("DO", "left", prefix="DO") + [_p("cm", "COM", "common", "", "DO", "left", False), _shield("left")],
    "RTD": _sig("RTD", "left", prefix="RTD") + [_p("s3", "SENSE+", "signal", "+", "RTD", "left", False),
                                                 _p("s4", "SENSE-", "signal", "-", "RTD", "left", False), _shield("left")],
    "TC": _sig("TC", "left", prefix="TC") + [_shield("left")],
    "PULSE": _sig("PULSE", "left", prefix="PUL") + [_shield("left")],
}


def through_ports() -> list[dict]:
    """A terminal block: each terminal accepts one wire from each side (field side / system side)."""
    return [_p("t1", "+", "signal", "+", "ANY", "both", True, multi=True),
            _p("t2", "-", "signal", "-", "ANY", "both", True, multi=True),
            _p("sh", "S", "shield", "", "ANY", "both", False, multi=True)]


def pair_ports() -> list[dict]:
    """A device with an input and an output side (barrier, isolator, conditioner, relay ...)."""
    return [_p("i1", "IN+", "signal", "+", "ANY", "left", True, pair="o1"), _p("i2", "IN-", "signal", "-", "ANY", "left", True, pair="o2"),
            _p("o1", "OUT+", "signal", "+", "ANY", "right", True, pair="i1"), _p("o2", "OUT-", "signal", "-", "ANY", "right", True, pair="i2")]


# ── component library ───────────────────────────────────────────────────────
# id -> (label, palette group, zone, default ports factory name)
LIBRARY: dict[str, dict] = {}


def _reg(cid: str, label: str, group: str, zone: str, ports: str = "none", **extra: Any) -> None:
    LIBRARY[cid] = {"id": cid, "label": label, "group": group, "zone": zone, "ports": ports, **extra}


for cid, label, ports in (
        ("pressure_transmitter", "Pressure Transmitter", "AI_2WIRE"), ("pressure_gauge", "Pressure Gauge", "NONE"),
        ("pressure_switch", "Pressure Switch", "DI_DRY"), ("level_transmitter", "Level Transmitter", "AI_2WIRE"),
        ("level_gauge", "Level Gauge", "NONE"), ("level_switch", "Level Switch", "DI_DRY"),
        ("temperature_transmitter", "Temperature Transmitter", "AI_2WIRE"), ("rtd", "RTD", "RTD_3"),
        ("thermocouple", "Thermocouple", "TC"), ("flow_transmitter", "Flow Transmitter", "AI_2WIRE"),
        ("analyzer", "Analyzer", "AI_4WIRE"), ("control_valve", "Control Valve", "AO"), ("mov", "MOV", "NONE"),
        ("solenoid", "Solenoid", "DO"), ("motor", "Motor", "NONE"), ("other_instrument", "Other Instrument", "AI_2WIRE")):
    _reg(cid, label, "FIELD DEVICES", "field", ports, device=True)
for cid, label, zone in (
        ("junction_box", "Junction Box", "jb"), ("marshalling_cabinet", "Marshalling Cabinet", "marshalling"),
        ("terminal_strip", "Terminal Strip", "marshalling"), ("terminal_block", "Terminal Block", "jb"),
        ("local_panel", "Local Panel", "jb"), ("connector", "Connector", "jb"), ("surge_protection", "Surge Protection", "marshalling"),
        ("fuse", "Fuse", "marshalling")):
    _reg(cid, label, "FIELD / INTERMEDIATE", zone, "THROUGH")
for cid, label, zone in (("zener_barrier", "Zener Barrier", "marshalling"), ("isolator", "Isolator", "marshalling"),
                         ("signal_conditioner", "Signal Conditioner", "marshalling"), ("relay", "Relay", "marshalling")):
    _reg(cid, label, "FIELD / INTERMEDIATE", zone, "PAIR")
_reg("power_supply", "Power Supply", "FIELD / INTERMEDIATE", "marshalling", "POWER")
_reg("shield_bar", "Shield Bar", "FIELD / INTERMEDIATE", "marshalling", "SHIELD_BAR")
_reg("earth", "Earth", "FIELD / INTERMEDIATE", "marshalling", "EARTH")
for cid, label, ports in (("plc_ai", "PLC AI Card", "AI"), ("plc_ao", "PLC AO Card", "AO"), ("plc_di", "PLC DI Card", "DI"),
                          ("plc_do", "PLC DO Card", "DO"), ("plc_rtd", "PLC RTD Card", "RTD"), ("plc_tc", "PLC TC Card", "TC")):
    _reg(cid, label, "CONTROL SYSTEM", "system", f"SYS_{ports}", system=True)
for cid, label in (("plc", "PLC"), ("dcs", "DCS"), ("remote_io", "Remote I/O"), ("vendor_plc", "Vendor PLC"), ("controller", "Controller")):
    _reg(cid, label, "CONTROL SYSTEM", "system", "NONE", system=True)
_reg("control_function", "Control Function", "CONTROL SYSTEM", "control", "SOFT")
for cid, label, zone in (("motor_starter", "Motor Starter", "marshalling"), ("mcc", "MCC", "marshalling"), ("vfd", "VFD", "marshalling"),
                         ("soft_starter", "Soft Starter", "marshalling"), ("package_panel", "Package Panel", "jb")):
    _reg(cid, label, "SPECIAL", zone, "NONE")
_reg("custom_block", "Custom Block", "SPECIAL", "jb", "THROUGH")

PALETTE_ORDER = ["FIELD DEVICES", "FIELD / INTERMEDIATE", "CONTROL SYSTEM", "SPECIAL"]


def ports_for(component: str, profile: Optional[str] = None) -> list[dict]:
    spec = LIBRARY.get(component)
    if spec is None:
        raise ValueError(f"Unknown component '{component}'")
    kind = profile or spec["ports"]
    if kind == "THROUGH":
        return through_ports()
    if kind == "PAIR":
        return pair_ports()
    if kind == "POWER":
        return [_p("pp", "+24V", "power", "+", "ANY", "right", True, multi=True), _p("pn", "0V", "power", "-", "ANY", "right", True, multi=True)]
    if kind == "SHIELD_BAR":
        return [_p("sh", "SHIELD", "shield", "", "ANY", "both", False, multi=True)]
    if kind == "EARTH":
        return [_p("e", "EARTH", "earth", "", "ANY", "both", False, multi=True)]
    if kind == "SOFT":
        return [_p("in", "IN", "soft", "", "ANY", "left", False, multi=True)]
    if kind.startswith("SYS_"):
        return copy.deepcopy(SYSTEM_PROFILES[kind[4:]]) + [_p("out", "TO LOGIC", "soft", "", "ANY", "right", False, multi=True)]
    if kind in FIELD_PROFILES:
        return copy.deepcopy(FIELD_PROFILES[kind])
    return []


def signal_ports(signals: list[dict], side: str, io: bool = False) -> list[dict]:
    """Two ports per selected signal (motor / valve / VFD): every signal is its own connection path."""
    out = []
    for i, s in enumerate(signals):
        fam = FAMILY_ALIAS.get(s["signal_type"], s["signal_type"])
        sid = re.sub(r"[^a-z0-9_]", "", s["id"].lower()) or f"s{i}"
        pol_p, pol_n = ("", "") if fam in ("DI", "DO") else ("+", "-")
        out.append(_p(f"{sid}_p", f"{s['name']} +", "signal", pol_p, fam, side, True, group=s["name"], signal_id=s["id"]))
        out.append(_p(f"{sid}_n", f"{s['name']} -", "signal", pol_n, fam, side, True, group=s["name"], signal_id=s["id"]))
    return out


# ── nodes / graph helpers ───────────────────────────────────────────────────
def new_node(component: str, node_id: str, tag: str = "", zone: str = "", x: float = 0, y: float = 0,
             ports: Optional[list[dict]] = None, props: Optional[dict] = None, profile: Optional[str] = None) -> dict:
    spec = LIBRARY[component]
    return {"id": node_id, "type": component, "label": spec["label"], "tag": tag, "description": "",
            "zone": zone or spec["zone"], "x": x, "y": y, "bind_tag": "", "props": props or {},
            "ports": ports if ports is not None else ports_for(component, profile)}


def next_id(graph: dict, key: str, prefix: str) -> str:
    used = {str(i["id"]) for i in graph.get(key, [])}
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def find_node(graph: dict, node_id: str) -> Optional[dict]:
    return next((n for n in graph.get("nodes", []) if n["id"] == node_id), None)


def find_port(node: Optional[dict], port_id: str) -> Optional[dict]:
    return next((p for p in (node or {}).get("ports", []) if p["id"] == port_id), None)


def new_graph(tag: str, loop: str = "", template: str = "") -> dict:
    return {"version": 1, "tag": tag, "loop": loop, "template": template, "orientation": "horizontal",
            "zones": copy.deepcopy(DEFAULT_ZONES), "nodes": [], "edges": [], "cables": [], "notes": "",
            "grid": 10}


# ── connection rules ────────────────────────────────────────────────────────
_KIND_OK = {("signal", "signal"), ("power", "power"), ("shield", "shield"), ("shield", "earth"), ("earth", "shield"),
            ("earth", "earth"), ("common", "common"), ("common", "power"), ("power", "common"), ("common", "signal"),
            ("signal", "common"), ("soft", "soft")}


def _fam(p: dict) -> str:
    f = (p.get("sig") or "ANY").upper()
    return FAMILY_ALIAS.get(f, f)


def can_connect(graph: dict, a_node: str, a_port: str, b_node: str, b_port: str, ignore_edge: str = "") -> tuple[bool, str]:
    """(ok, reason). Hard rules only - what is physically impossible to wire is refused."""
    na, nb = find_node(graph, a_node), find_node(graph, b_node)
    pa, pb = find_port(na, a_port), find_port(nb, b_port)
    if not (na and nb and pa and pb):
        return False, "Both ends of a connection must be existing ports."
    if a_node == b_node:
        return False, "A wire cannot connect a block to itself."
    ka, kb = pa["kind"], pb["kind"]
    if (ka, kb) not in _KIND_OK:
        names = {"signal": "signal", "power": "power", "shield": "shield", "earth": "earth", "common": "common", "soft": "logic"}
        if "shield" in (ka, kb) and "earth" not in (ka, kb):
            other = pb if ka == "shield" else pa
            return False, f"A shield cannot be connected to a {names[other['kind']]} port ({other['label']}) - use a shield terminal or earth."
        return False, f"A {names[ka]} port ({pa['label']}) cannot be connected to a {names[kb]} port ({pb['label']})."
    if ka == "signal" and kb == "signal":
        fa, fb = _fam(pa), _fam(pb)
        if fa not in ("ANY", "CUSTOM") and fb not in ("ANY", "CUSTOM") and fa != fb:
            return False, f"{fa} signal port ({pa['label']}) cannot be connected to a {fb} port ({pb['label']})."
    if pa["pol"] and pb["pol"] and pa["pol"] != pb["pol"] and "common" not in (ka, kb):
        return False, f"Polarity mismatch: {pa['label']} ({pa['pol']}) to {pb['label']} ({pb['pol']})."
    for node, port, nid in ((na, pa, a_node), (nb, pb, b_node)):
        used = [e for e in graph.get("edges", []) if e["id"] != ignore_edge and
                ((e["from_node"] == nid and e["from_port"] == port["id"]) or (e["to_node"] == nid and e["to_port"] == port["id"]))]
        limit = 2 if port["side"] == "both" and port.get("multi") else (99 if port.get("multi") else 1)
        if len(used) >= limit:
            return False, f"{node['tag'] or node['label']} / {port['label']} already has {'its wire' if limit == 1 else 'the maximum number of wires'}."
    for e in graph.get("edges", []):
        if e["id"] != ignore_edge and {(e["from_node"], e["from_port"]), (e["to_node"], e["to_port"])} == {(a_node, a_port), (b_node, b_port)}:
            return False, "These two ports are already connected."
    return True, ""


def add_edge(graph: dict, a_node: str, a_port: str, b_node: str, b_port: str, kind: str = "", **extra: Any) -> tuple[Optional[dict], str]:
    ok, reason = can_connect(graph, a_node, a_port, b_node, b_port)
    if not ok:
        return None, reason
    pa = find_port(find_node(graph, a_node), a_port)
    eid = next_id(graph, "edges", "e")
    used_w = [int(m.group(1)) for e in graph["edges"] if (m := re.fullmatch(r"W(\d+)", str(e.get("wire_no", ""))))]
    edge = {"id": eid, "from_node": a_node, "from_port": a_port, "to_node": b_node, "to_port": b_port,
            "kind": kind or pa["kind"], "cable_id": "", "core": "", "wire_no": f"W{max(used_w, default=0) + 1:02d}",
            "signal": pa["label"], "remarks": ""}
    edge.update(extra)
    graph["edges"].append(edge)
    return edge, ""


def connect_blocks(graph: dict, a_node: str, b_node: str) -> dict:
    """Explicit helper (user-triggered): wire matching ports of two blocks pairwise (+ to +, - to -, shield to shield,
    power to power ...), creating ordinary edges. Pass-through / paired ports are matched in port order."""
    na, nb = find_node(graph, a_node), find_node(graph, b_node)
    created, skipped = [], []
    if not (na and nb):
        return {"created": created, "skipped": ["Unknown block."]}
    taken = set()
    for pa in na["ports"]:
        for pb in nb["ports"]:
            if pb["id"] in taken or pa["kind"] != pb["kind"]:
                continue
            if pa["pol"] != pb["pol"] and (pa["pol"] or pb["pol"]):
                continue
            if pa["kind"] == "signal" and pa["pol"] == "" and pb["pol"] == "":
                continue                                    # unpolarised contacts: ambiguous, never guessed
            ok, _ = can_connect(graph, a_node, pa["id"], b_node, pb["id"])
            if not ok:
                continue
            ports_a_used = [e for e in graph["edges"] if (e["from_node"], e["from_port"]) == (a_node, pa["id"]) or (e["to_node"], e["to_port"]) == (a_node, pa["id"])]
            if ports_a_used and not (pa["side"] == "both"):
                continue
            edge, _ = add_edge(graph, a_node, pa["id"], b_node, pb["id"])
            if edge:
                created.append(edge["id"])
                taken.add(pb["id"])
                break
        else:
            skipped.append(pa["label"])
    return {"created": created, "skipped": skipped}


def remove_node(graph: dict, node_id: str) -> None:
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] != node_id]
    graph["edges"] = [e for e in graph["edges"] if node_id not in (e["from_node"], e["to_node"])]


def clean_graph(graph: dict) -> dict:
    """Drop anything dangling (edges to removed ports, cables nobody uses are kept) and derive node zones from
    their position - never changes which port an edge is attached to."""
    g = copy.deepcopy(graph)
    g.setdefault("zones", copy.deepcopy(DEFAULT_ZONES))
    g.setdefault("cables", [])
    g.setdefault("edges", [])
    g.setdefault("orientation", "horizontal")
    keep = []
    for e in g["edges"]:
        if find_port(find_node(g, e["from_node"]), e["from_port"]) and find_port(find_node(g, e["to_node"]), e["to_port"]):
            keep.append(e)
    g["edges"] = keep
    return g
