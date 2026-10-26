"""Validation of the engineer-designed loop graph. Only errors block generation; warnings are reported."""
from __future__ import annotations

from collections import Counter
from typing import Optional

from .common import clean, is_value
from .graph import LIBRARY, can_connect, find_node, find_port
from .graph_scene import _fv, io_row, resolve_cable
from .io_assignment import io_class

THROUGH_TYPES = ("junction_box", "marshalling_cabinet", "terminal_strip", "terminal_block", "local_panel", "connector",
                 "custom_block", "package_panel")
DEST_TYPES = ("power_supply", "earth", "shield_bar", "control_function", "mcc", "vfd", "soft_starter", "motor_starter")
CARD_FAMILY = {"plc_ai": "AI", "plc_ao": "AO", "plc_di": "DI", "plc_do": "DO", "plc_rtd": "RTD", "plc_tc": "TC"}


def edges_at(g: dict, node: str, port: str) -> list[dict]:
    return [e for e in g["edges"] if (e["from_node"], e["from_port"]) == (node, port) or (e["to_node"], e["to_port"]) == (node, port)]


def _other(e: dict, node: str, port: str) -> tuple[str, str]:
    return (e["to_node"], e["to_port"]) if (e["from_node"], e["from_port"]) == (node, port) else (e["from_node"], e["from_port"])


def trace(g: dict, node: str, port: str) -> tuple[list[tuple[str, str]], int]:
    """Follow a wire through terminals / paired devices. Returns (end ports reached, dead ends)."""
    ends, dead, seen = [], 0, set()
    stack = [(node, port, None)]
    while stack:
        n, p, came = stack.pop()
        if (n, p, came) in seen:
            continue
        seen.add((n, p, came))
        es = [e for e in edges_at(g, n, p) if e["id"] != came]
        if not es:
            dead += 1
            continue
        for e in es:
            on, op = _other(e, n, p)
            prt = find_port(find_node(g, on), op)
            if prt is None:
                continue
            if prt["side"] == "both" and prt.get("multi"):
                if [x for x in edges_at(g, on, op) if x["id"] != e["id"]]:
                    stack.append((on, op, e["id"]))
                else:
                    dead += 1
            elif prt.get("pair"):
                stack.append((on, prt["pair"], None))
            else:
                ends.append((on, op))
    return ends, dead


def _chk(cid: str, label: str, status: str, detail: str = "", nodes: Optional[list] = None) -> dict:
    return {"id": cid, "label": label, "status": status, "detail": detail, "nodes": nodes or []}


def validate_graph(g: dict, datas: dict, tag_conflicts: Optional[list] = None) -> dict:
    checks: list[dict] = []
    nodes = {n["id"]: n for n in g["nodes"]}
    name = lambda nid: (nodes[nid].get("tag") or nodes[nid].get("label") or nid) if nid in nodes else nid
    pname = lambda nid, pid: f"{name(nid)} / {(find_port(nodes.get(nid), pid) or {}).get('label', pid)}"
    data = datas.get(g.get("tag", ""))

    devices = [n for n in g["nodes"] if LIBRARY.get(n["type"], {}).get("device")]
    systems = [n for n in g["nodes"] if LIBRARY.get(n["type"], {}).get("system")]
    if not g["nodes"]:
        checks.append(_chk("blocks", "Loop has blocks", "ERROR", "The canvas is empty - choose a template or add blocks."))
    else:
        miss = []
        if not devices and not any(n["type"] in ("motor", "motor_starter", "mcc", "vfd", "soft_starter") for n in g["nodes"]):
            miss.append("a field device")
        if not systems:
            miss.append("a PLC / DCS block")
        checks.append(_chk("blocks", "Field device and control system present", "ERROR" if miss else "PASS", "Missing: " + ", ".join(miss) if miss else ""))

    # connections valid
    bad = []
    for e in g["edges"]:
        ok, why = can_connect(g, e["from_node"], e["from_port"], e["to_node"], e["to_port"], ignore_edge=e["id"])
        if not ok:
            bad.append((e, why))
    checks.append(_chk("connections", "Every connection is valid (port compatibility)", "ERROR" if bad else "PASS",
                       "; ".join(f"{e['wire_no']}: {w}" for e, w in bad[:4]), [x for e, _ in bad for x in (e["from_node"], e["to_node"])]))
    kinds_mixed = [e for e in g["edges"] if (find_port(nodes.get(e["from_node"]), e["from_port"]) or {}).get("kind") != e["kind"]
                   and not (find_port(nodes.get(e["to_node"]), e["to_port"]) or {}).get("kind") == e["kind"]]
    checks.append(_chk("power_signal", "Power and signal wires are not merged", "ERROR" if kinds_mixed else "PASS",
                       "; ".join(e["wire_no"] for e in kinds_mixed)))

    # required ports
    unconnected = [(n["id"], p) for n in g["nodes"] for p in n["ports"] if p.get("required") and not edges_at(g, n["id"], p["id"])]
    checks.append(_chk("required_ports", "Every required port is connected", "ERROR" if unconnected else "PASS",
                       ", ".join(pname(n, p["id"]) for n, p in unconnected[:6]) + (" …" if len(unconnected) > 6 else ""),
                       [n for n, _ in unconnected]))

    # every signal has a source and a destination
    path_problems, path_nodes = [], []
    for d in g["nodes"]:
        if not (LIBRARY.get(d["type"], {}).get("device") or d["type"] in ("motor_starter", "mcc", "vfd", "soft_starter")):
            continue
        for p in d["ports"]:
            if p["kind"] not in ("signal", "power") or not edges_at(g, d["id"], p["id"]):
                continue
            ends, dead = trace(g, d["id"], p["id"])
            good = [e for e in ends if (nodes[e[0]]["type"] in DEST_TYPES or LIBRARY.get(nodes[e[0]]["type"], {}).get("system"))]
            if not good:
                path_problems.append(f"{pname(d['id'], p['id'])} does not reach a control system / power source")
                path_nodes.append(d["id"])
    checks.append(_chk("paths", "Every signal reaches its destination", "ERROR" if path_problems else "PASS", "; ".join(path_problems[:3]), path_nodes))

    # terminals
    unnum = [(n["id"], p) for n in g["nodes"] if n["type"] in THROUGH_TYPES for p in n["ports"]
             if edges_at(g, n["id"], p["id"]) and not clean(p.get("terminal", ""))]
    checks.append(_chk("terminals", "Every used terminal is assigned", "ERROR" if unnum else "PASS",
                       ", ".join(pname(n, p["id"]) for n, p in unnum[:6]) + (" …" if len(unnum) > 6 else ""), [n for n, _ in unnum]))
    dup_t = []
    for n in g["nodes"]:
        cnt = Counter((clean(p.get("terminal", "")), p["kind"] == "shield") for p in n["ports"] if clean(p.get("terminal", "")))
        dup_t += [(n["id"], t) for (t, _s), c in cnt.items() if c > 1]
    checks.append(_chk("dup_terminals", "No duplicate terminal assignment", "ERROR" if dup_t else "PASS",
                       ", ".join(f"{name(n)} terminal {t}" for n, t in dup_t[:5]), [n for n, _ in dup_t]))

    # cables / cores / wires
    cables = {c["id"]: resolve_cable(c, g, datas) for c in g.get("cables", [])}
    no_cable = [e for e in g["edges"] if e["kind"] in ("signal", "power", "shield") and not e.get("cable_id")
                and nodes[e["from_node"]].get("zone") != nodes[e["to_node"]].get("zone")]
    checks.append(_chk("cables_assigned", "Wires between locations have a cable", "WARNING" if no_cable else "PASS",
                       f"{len(no_cable)} wire(s) without a cable: " + ", ".join(e["wire_no"] for e in no_cable[:6]) if no_cable else ""))
    dangling = [e for e in g["edges"] if e.get("cable_id") and e["cable_id"] not in cables]
    checks.append(_chk("cable_refs", "Every cable reference exists", "ERROR" if dangling else "PASS", ", ".join(e["wire_no"] for e in dangling)))
    no_core = [e for e in g["edges"] if e.get("cable_id") in cables and e["kind"] not in ("soft", "shield") and not clean(e.get("core", ""))]
    checks.append(_chk("cores", "Every wire in a cable has a core / pair number", "ERROR" if no_core else "PASS", ", ".join(e["wire_no"] for e in no_core[:8])))
    use = Counter((e["cable_id"], clean(e["core"])) for e in g["edges"] if e.get("cable_id") in cables and clean(e.get("core", "")))
    dup_core = [k for k, c in use.items() if c > 1]
    checks.append(_chk("dup_cores", "No duplicate core assignment", "ERROR" if dup_core else "PASS",
                       ", ".join(f"{cables[c]['tag'] or c} core {k}" for c, k in dup_core[:5])))
    over = []
    for cid, c in cables.items():
        try:
            cap = int(c["cores"]) if c["cores"] else (int(c["pairs"]) * 2 if c["pairs"] else 0)
        except ValueError:
            cap = 0
        used = len({clean(e["core"]) for e in g["edges"] if e.get("cable_id") == cid and e["kind"] != "shield" and clean(e.get("core", ""))})
        if cap and used > cap:
            over.append(f"{c['tag'] or cid}: {used} cores used, cable has {cap}")
    checks.append(_chk("core_capacity", "Cores used do not exceed the cable", "ERROR" if over else "PASS", "; ".join(over)))
    wc = Counter(clean(e.get("wire_no", "")) for e in g["edges"] if clean(e.get("wire_no", "")))
    dup_w = [w for w, c in wc.items() if c > 1]
    checks.append(_chk("dup_wires", "Wire numbers are unique", "ERROR" if dup_w else "PASS", ", ".join(dup_w[:6])))

    # shielding (the engineer decides; nothing is imposed)
    sh_undef, sh_mismatch = [], []
    for cid, c in cables.items():
        stype = (c["shield"] or {}).get("type") or ""
        used_edges = [e for e in g["edges"] if e.get("cable_id") == cid]
        has_shield_edge = any(e["kind"] == "shield" for e in used_edges)
        if not stype:
            sh_undef.append(c["tag"] or cid)
        elif stype != "none" and not has_shield_edge:
            sh_mismatch.append(f"{c['tag'] or cid}: shield '{stype}' but no shield wire connected")
        elif stype == "none" and has_shield_edge:
            sh_mismatch.append(f"{c['tag'] or cid}: shield wire connected but cable shield is 'None'")
        if stype and stype != "none" and not (c["shield"] or {}).get("items"):
            sh_undef.append(f"{c['tag'] or cid} (termination)")
    checks.append(_chk("shield_defined", "Shielding is defined for every cable", "WARNING" if sh_undef else "PASS",
                       "Not defined: " + ", ".join(sh_undef[:5]) if sh_undef else ""))
    checks.append(_chk("shield_consistent", "Shield wires match the cable shield type", "WARNING" if sh_mismatch else "PASS", "; ".join(sh_mismatch[:4])))

    # source documents
    jb_issue, cab_issue = [], []
    iodb_jb, _ = _fv(data, "JB_TAG")
    for n in g["nodes"]:
        if n["type"] == "junction_box":
            used = (n.get("props", {}).get("jb_tag") or n.get("tag") or "").strip()
            if iodb_jb and used and used.upper() != iodb_jb.upper() and not n.get("props", {}).get("accept_difference"):
                jb_issue.append(f"{used} (IODB: {iodb_jb})")
            if not used and not iodb_jb:
                jb_issue.append("junction box has no tag")
    checks.append(_chk("jb_match", "Junction box matches the IODB", "ERROR" if jb_issue else "PASS", "; ".join(jb_issue)))
    for cid, c in cables.items():
        if c["iodb"]:
            continue
        ends = {e["from_node"] for e in g["edges"] if e.get("cable_id") == cid} | {e["to_node"] for e in g["edges"] if e.get("cable_id") == cid}
        types = {nodes[x]["type"] for x in ends if x in nodes}
        kind = "BRANCH_CABLE_TAG" if any(LIBRARY.get(t, {}).get("device") for t in types) else ("MAIN_CABLE_TAG" if "junction_box" in types else "")
        exp, _ = _fv(data, kind) if kind else ("", "")
        if exp and c["tag"] and c["tag"].upper() != exp.upper() and not next((x for x in g["cables"] if x["id"] == cid), {}).get("accept_difference"):
            cab_issue.append(f"{c['tag']} (IODB: {exp})")
    checks.append(_chk("cable_match", "Cables match the IODB", "ERROR" if cab_issue else "PASS", "; ".join(cab_issue)))

    io_bad, io_missing = [], []
    for n in systems:
        if not any(edges_at(g, n["id"], p["id"]) for p in n["ports"]):
            continue
        fam = CARD_FAMILY.get(n["type"])
        if any(p.get("signal_id") for p in n["ports"]):
            for p in n["ports"]:
                if p.get("signal_id") and edges_at(g, n["id"], p["id"]):
                    row = io_row(n, datas, g, p.get("io_index"))
                    if row is None:
                        io_missing.append(f"{name(n['id'])} / {p['label']}")
                    elif io_class(row["io_type"]) and io_class(row["io_type"]) != (p.get("sig") or "").replace("PULSE", "PI"):
                        io_bad.append(f"{name(n['id'])} / {p['label']}: I/O Assignment says {row['io_type']}")
        else:
            row = io_row(n, datas, g)
            if row is None and not n.get("props", {}).get("io_override"):
                io_missing.append(name(n["id"]))
            elif row is not None and fam and io_class(row["io_type"]) and io_class(row["io_type"]) != fam.replace("PULSE", "PI"):
                io_bad.append(f"{name(n['id'])}: card is {fam}, I/O Assignment channel is {row['io_type']}")
    checks.append(_chk("io_selected", "PLC / DCS channel is taken from the I/O Assignment", "ERROR" if io_missing else "PASS",
                       "Not selected: " + ", ".join(io_missing[:5]) if io_missing else "", [n["id"] for n in systems]))
    checks.append(_chk("io_type", "PLC channel matches the I/O type", "ERROR" if io_bad else "PASS", "; ".join(io_bad[:4])))
    fam_bad = []
    iodb_sig, _ = _fv(data, "SIGNAL_IO_TYPE")
    cls = io_class(iodb_sig) if iodb_sig else ""
    for d in devices:
        fams = {(p.get("sig") or "") for p in d["ports"] if p["kind"] == "signal"} - {"", "ANY"}
        if cls and fams and cls.replace("PI", "PULSE") not in fams and d.get("bind_tag", "") in ("", g.get("tag")):
            fam_bad.append(f"{name(d['id'])}: IODB signal {iodb_sig}, ports {'/'.join(sorted(fams))}")
    checks.append(_chk("iodb_signal", "Device ports match the IODB signal type", "WARNING" if fam_bad else "PASS", "; ".join(fam_bad)))
    unresolved = [c for c in (tag_conflicts or []) if c.get("severity") == "error" and not c.get("decision")]
    checks.append(_chk("conflicts", "IODB and I/O Assignment agree (or the engineer decided)", "ERROR" if unresolved else "PASS",
                       "; ".join(f"{c['label']}: IODB {c['iodb']} vs I/O {c['io']}" for c in unresolved)))

    errors = sum(1 for c in checks if c["status"] == "ERROR")
    warnings = sum(1 for c in checks if c["status"] == "WARNING")
    issues: dict[str, str] = {}
    for c in checks:
        for nid in c["nodes"]:
            if c["status"] == "ERROR" or nid not in issues:
                issues[nid] = c["status"]
    return {"checks": checks, "errors": errors, "warnings": warnings, "passed": sum(1 for c in checks if c["status"] == "PASS"),
            "total": len(checks), "can_generate": errors == 0, "issues": issues}
