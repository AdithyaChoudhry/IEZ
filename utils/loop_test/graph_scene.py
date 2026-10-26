"""
Renderer: graph + source data -> SCENE (drawing primitives with coordinates) -> SVG-in-the-browser / PNG-in-Excel.

The scene is built ONLY from the graph (nodes, ports, edges, cables). There is no loop-type logic here: a wire
is drawn if, and only if, there is an edge for it, attached to (node, port). Moving a node moves its ports, so
the wires follow; they can never re-connect to something else.
"""
from __future__ import annotations

import io
from typing import Any, Optional

from .common import clean, is_value
from .graph import LIBRARY, find_node, find_port

NW, ROW, LINE, PAD = 240, 24, 15, 8
ML, ZW, ZH, TOP_H, TITLE_H = 30, 420, 340, 150, 56
SNAP = 10
MISSING = "MISSING"


# ── source values ───────────────────────────────────────────────────────────
def _fv(data: Optional[dict], key: str, override: Optional[dict] = None) -> tuple[str, str]:
    """(value, source). Engineer overrides win and are marked USER; TBA / '-' count as not available."""
    if override and clean(override.get(key, "")):
        return clean(override[key]), "USER"
    f = ((data or {}).get("fields") or {}).get(key) or {}
    v = clean(f.get("value", ""))
    return (v, f.get("source", "")) if is_value(v) else ("", "")


def resolve_cable(cable: dict, graph: dict, datas: dict) -> dict:
    """Effective cable values: IODB branch/main data (by tag) unless the engineer overrides a value."""
    data = datas.get(graph.get("tag", ""))
    ov = cable.get("override") or {}
    src = cable.get("iodb") or ""
    pre = {"branch": "BRANCH_CABLE_", "main": "MAIN_CABLE_"}.get(src, "")
    out = {"id": cable["id"], "iodb": src}
    for name, key in (("tag", "TAG"), ("type", "TYPE"), ("length", "LENGTH")):
        v, s = ("", "")
        if clean(ov.get(name, "")):
            v, s = clean(ov[name]), "USER"
        elif pre:
            v, s = _fv(data, pre + key)
        elif clean(cable.get(name, "")):
            v, s = clean(cable[name]), "USER"
        out[name], out[name + "_src"] = v, s
    route, rs = (clean(ov.get("route", "")), "USER") if clean(ov.get("route", "")) else (_fv(data, "ROUTE_NUMBER") if src == "branch" else (clean(cable.get("route", "")), "USER" if cable.get("route") else ""))
    out["route"], out["route_src"] = route, rs
    out["cores"], out["pairs"] = clean(cable.get("cores", "")), clean(cable.get("pairs", ""))
    out["shield"] = cable.get("shield") or {"type": "", "items": []}
    return out


def io_row(node: dict, datas: dict, graph: dict, idx: Any = "__node__") -> Optional[dict]:
    data = datas.get(node.get("bind_tag") or graph.get("tag", "")) or {}
    rows = data.get("signals", [])
    i = node.get("props", {}).get("io_index") if idx == "__node__" else idx
    if isinstance(i, int) and 0 <= i < len(rows):
        return rows[i]
    return None


# ── what is written inside a block ──────────────────────────────────────────
def node_view(node: dict, graph: dict, datas: dict) -> dict:
    t, props = node["type"], node.get("props", {})
    spec = LIBRARY.get(t, {})
    data = datas.get(node.get("bind_tag") or graph.get("tag", ""))
    ov = props.get("override") or {}
    lines: list[tuple[str, bool]] = []
    title, desc = node.get("tag", ""), node.get("description", "")
    heading = (node.get("label") or spec.get("label", t)).upper()
    group = spec.get("group", "")

    def add(label: str, key: str, required: bool = False) -> None:
        v, _ = _fv(data, key, ov)
        if v:
            lines.append((f"{label}: {v}", False))
        elif required:
            lines.append((f"{label}: {MISSING}", True))

    if spec.get("device"):
        title = title or (node.get("bind_tag") or graph.get("tag", ""))
        itype, _ = _fv(data, "INSTRUMENT_TYPE", ov)
        desc = desc or itype
        add("Signal", "SIGNAL_IO_TYPE", True)
        add("Service", "SIGNAL_DESCRIPTION")
        add("Power", "POWER_SUPPLY")
        add("IS/NIS", "IS_NIS")
        hart = props.get("hart")
        hv, _ = _fv(data, "HART", ov)
        if hart is True or (hart is None and hv.upper() in ("Y", "YES")):
            lines.append(("HART: yes", False))
    elif t == "junction_box":
        jb, _ = _fv(data, "JB_TAG", {"JB_TAG": props.get("jb_tag", "")})
        title = title or jb or MISSING
        add("Gland", "JB_GLAND_SIZE")
    elif t in ("marshalling_cabinet", "terminal_strip", "terminal_block"):
        title = title or MISSING
        if props.get("strip"):
            lines.append((f"Terminal strip: {props['strip']}", False))
        if props.get("terminal_type"):
            lines.append((f"Type: {props['terminal_type']}", False))
    elif spec.get("system") or t.startswith("plc_"):
        row = io_row(node, datas, graph)
        iov = props.get("io_override") or {}
        name = clean(iov.get("plc", "")) or (row or {}).get("plc", "")
        title = title or name or MISSING
        if name and name != title:
            lines.append((f"PLC/DCS: {name}", False))
        multi = any(p.get("signal_id") for p in node["ports"])
        if not multi:
            if row is None and not iov:
                lines.append(("I/O Assignment row: NOT SELECTED", True))
            for lab, key in (("Rack", "rack"), ("Slot", "slot"), ("Module", "module"), ("Channel", "channel"), ("I/O type", "io_type"),
                             ("Address", "address"), ("Terminal strip", "terminal_strip")):
                v = clean(iov.get(key, "")) or (row or {}).get(key, "")
                if v:
                    lines.append((f"{lab}: {v}", False))
                elif key in ("rack", "slot", "channel") and (row is not None or iov):
                    lines.append((f"{lab}: {MISSING}", True))
    elif t == "power_supply":
        title = title or "POWER SUPPLY"
        v, _ = _fv(data, "POWER_SUPPLY", {"POWER_SUPPLY": props.get("voltage", "")})
        lines.append((f"Output: {v or MISSING}", not v))
    elif t in ("zener_barrier", "isolator", "signal_conditioner", "relay", "surge_protection", "fuse"):
        title = title or MISSING
        v, _ = _fv(data, "ZENER_BARRIER") if t == "zener_barrier" else ("", "")
        if v:
            lines.append((f"IODB: {v}", False))
    elif t == "control_function":
        title = title or "CONTROL FUNCTION"
    else:
        title = title or MISSING
    for extra in props.get("lines") or []:
        if clean(extra):
            lines.append((clean(extra), False))
    return {"heading": heading, "title": title or "—", "desc": desc, "lines": lines, "group": group}


def node_height(node: dict, graph: dict, datas: dict) -> int:
    v = node_view(node, graph, datas)
    return 62 + LINE * len(v["lines"]) + 10 + ROW * max(len(node["ports"]), 1) + 8


def port_text(node: dict, port: dict, graph: dict, datas: dict) -> tuple[str, bool]:
    """(text, missing) shown on a port row."""
    term = clean(port.get("terminal", ""))
    props = node.get("props", {})
    if port.get("signal_id") is not None or (node["type"].startswith("plc_") and port["kind"] in ("signal", "common")):
        row = io_row(node, datas, graph, port.get("io_index") if port.get("signal_id") else "__node__")
        iov = props.get("io_override") or {}
        if port.get("signal_id") and row is not None:
            loc = f"R{row['rack'] or '?'}/S{row['slot'] or '?'}/CH{row['channel'] or '?'}"
            return f"{port['label']}  [{loc}]", False
        if port.get("signal_id"):
            return f"{port['label']}  [I/O NOT SELECTED]", True
    if term:
        return (term if term.upper() == port["label"].upper() else f"{term}  {port['label']}"), False
    through = node["type"] in ("junction_box", "marshalling_cabinet", "terminal_strip", "terminal_block", "local_panel",
                               "connector", "custom_block", "package_panel")
    return (f"?  {port['label']}", True) if through else (port["label"], False)


# ── geometry ────────────────────────────────────────────────────────────────
def visible_zones(graph: dict) -> list[dict]:
    return [z for z in graph.get("zones", []) if z.get("visible", True)]


def zone_rect(graph: dict, index: int) -> tuple[float, float, float, float]:
    if graph.get("orientation") == "vertical":
        return (ML, TOP_H + index * ZH, ZW * 2, ZH)
    return (ML + index * ZW, TOP_H, ZW, 560)


def zone_for_position(graph: dict, cx: float, cy: float) -> Optional[str]:
    zs = visible_zones(graph)
    if not zs or graph.get("orientation") == "custom":
        return None
    if graph.get("orientation") == "vertical":
        i = int((cy - TOP_H) // ZH)
    else:
        i = int((cx - ML) // ZW)
    return zs[min(max(i, 0), len(zs) - 1)]["id"]


def normalize_positions(graph: dict, datas: dict) -> dict:
    """Derive each node's zone from where the engineer placed it; snap to grid. Does not touch edges."""
    g = graph
    grid = g.get("grid", SNAP) or SNAP
    for n in g["nodes"]:
        n["x"] = round(float(n.get("x", 0)) / grid) * grid
        n["y"] = round(float(n.get("y", 0)) / grid) * grid
        z = zone_for_position(g, n["x"] + NW / 2, n["y"] + node_height(n, g, datas) / 2)
        if z:
            n["zone"] = z
    return g


def _port_pos(node: dict, port: dict, nview: dict, side: str) -> tuple[float, float]:
    idx = node["ports"].index(port)
    y = node["y"] + 62 + LINE * len(nview["lines"]) + 10 + ROW * idx + ROW / 2
    x = node["x"] if side == "left" else node["x"] + NW
    return x, y


def route(p1: tuple[float, float], d1: int, p2: tuple[float, float], d2: int, lane: int = 0) -> list[tuple[float, float]]:
    """Orthogonal polyline from p1 (leaving in direction d1) to p2 (entered from direction d2). Cosmetic only."""
    (x1, y1), (x2, y2) = p1, p2
    if abs(y1 - y2) < 0.5 and (x2 - x1) * d1 > 0:
        return [p1, p2]
    if d1 == 1 and d2 == -1 and x2 - x1 > 40:
        xm = (x1 + x2) / 2 + lane * 8
        return [p1, (xm, y1), (xm, y2), p2]
    if d1 == -1 and d2 == 1 and x1 - x2 > 40:
        xm = (x1 + x2) / 2 + lane * 8
        return [p1, (xm, y1), (xm, y2), p2]
    xo1 = x1 + d1 * (24 + lane * 8)
    xo2 = x2 + d2 * (24 + lane * 8)
    ym = (y1 + y2) / 2 + (30 + lane * 8 if abs(y1 - y2) < 30 else 0)
    return [p1, (xo1, y1), (xo1, ym), (xo2, ym), (xo2, y2), p2]


def build_scene(graph: dict, datas: dict, meta: Optional[dict] = None, issues: Optional[dict] = None) -> dict:
    meta = meta or {}
    issues = issues or {}
    g = graph
    items: list[dict] = []
    views = {n["id"]: node_view(n, g, datas) for n in g["nodes"]}
    heights = {n["id"]: node_height(n, g, datas) for n in g["nodes"]}
    nodes_out: dict[str, dict] = {}
    for n in g["nodes"]:
        nodes_out[n["id"]] = {"x": n["x"], "y": n["y"], "w": NW, "h": heights[n["id"]], "zone": n.get("zone", ""),
                              "tag": views[n["id"]]["title"], "label": n.get("label", ""), "type": n["type"]}
    zs = visible_zones(g)
    custom = g.get("orientation") == "custom" or not zs
    # canvas size
    max_x = max([v["x"] + v["w"] for v in nodes_out.values()] + [ML + max(len(zs), 1) * ZW])
    max_y = max([v["y"] + v["h"] for v in nodes_out.values()] + [TOP_H + (len(zs) * ZH if g.get("orientation") == "vertical" else 560)])
    W, H = int(max_x + 60), int(max_y + 220)
    field = next((n for n in g["nodes"] if LIBRARY.get(n["type"], {}).get("device")), None)
    ftype = clean(views[field["id"]]["desc"]).upper() if field else ""
    ftag = (field.get("tag") or g.get("tag", "")) if field else g.get("tag", "")
    title = f"INSTRUMENT LOOP DIAGRAM FOR {ftype + ' ' if ftype else ''}{ftag}".strip()
    items.append({"t": "rect", "x": 6, "y": 6, "w": W - 12, "h": H - 12, "fill": "#fff", "stroke": "#000", "sw": 2})
    items.append({"t": "text", "x": W / 2, "y": 38, "s": title, "size": 22, "bold": True, "anchor": "middle"})
    bands = []
    if not custom:
        vertical = g.get("orientation") == "vertical"
        for i, z in enumerate(zs):
            x, y, w, h = zone_rect(g, i)
            bands.append({"id": z["id"], "x": x, "y": y, "w": w, "h": h})
            items.append({"t": "rect", "x": x, "y": y, "w": w, "h": h, "fill": "none", "stroke": "#000", "sw": 1.2})
            hy = y - 56 if not vertical else y
            if not vertical:
                items.append({"t": "rect", "x": x, "y": y - 56, "w": w, "h": 56, "fill": "#f3f3f3", "stroke": "#000", "sw": 1.2})
                items.append({"t": "text", "x": x + w / 2, "y": y - 32, "s": z["name"], "size": 14, "bold": True, "anchor": "middle"})
                if z.get("sub"):
                    items.append({"t": "text", "x": x + w / 2, "y": y - 12, "s": z["sub"], "size": 11, "anchor": "middle"})
            else:
                items.append({"t": "text", "x": x + 10, "y": y + 18, "s": z["name"] + (f"  —  {z['sub']}" if z.get("sub") else ""),
                              "size": 13, "bold": True})
    # blocks
    ports_out: dict[str, dict] = {}
    for n in g["nodes"]:
        v, h = views[n["id"]], heights[n["id"]]
        x, y = n["x"], n["y"]
        bad = issues.get(n["id"])
        items.append({"t": "rect", "x": x, "y": y, "w": NW, "h": h, "fill": "#fff", "stroke": "#c00000" if bad == "ERROR" else ("#d97706" if bad else "#000"),
                      "sw": 2.5 if bad else 1.6, "n": n["id"]})
        items.append({"t": "text", "x": x + PAD + 14, "y": y + 15, "s": v["heading"], "size": 10, "fill": "#555", "n": n["id"]})
        items.append({"t": "text", "x": x + PAD + 14, "y": y + 34, "s": v["title"], "size": 15, "bold": True,
                      "fill": "#c00000" if v["title"] == MISSING else "#000", "n": n["id"]})
        if v["desc"]:
            items.append({"t": "text", "x": x + PAD + 14, "y": y + 50, "s": v["desc"][:34], "size": 10, "fill": "#333", "n": n["id"]})
        ty = y + 62
        for text, miss in v["lines"]:
            items.append({"t": "text", "x": x + PAD + 14, "y": ty + 11, "s": text[:36], "size": 11, "fill": "#c00000" if miss else "#000",
                          "italic": miss, "n": n["id"]})
            ty += LINE
        items.append({"t": "line", "x1": x, "y1": ty + 4, "x2": x + NW, "y2": ty + 4, "stroke": "#999", "sw": 0.8, "n": n["id"]})
        for i, p in enumerate(n["ports"]):
            text, miss = port_text(n, p, g, datas)
            py = y + 62 + LINE * len(v["lines"]) + 10 + ROW * i + ROW / 2
            left_x, right_x = x, x + NW
            side = p["side"]
            if side == "right":
                items.append({"t": "text", "x": right_x - 12, "y": py + 4, "s": text[:34], "size": 11, "anchor": "end", "fill": "#c00000" if miss else "#000", "n": n["id"]})
            else:
                items.append({"t": "text", "x": left_x + 12, "y": py + 4, "s": text[:34], "size": 11, "fill": "#c00000" if miss else "#000", "n": n["id"]})
            for sd in (("left", "right") if side == "both" else (side,)):
                px = left_x if sd == "left" else right_x
                ports_out[f"{n['id']}:{p['id']}:{sd}"] = {"node": n["id"], "port": p["id"], "side": sd, "x": px, "y": py}
                items.append({"t": "circle", "cx": px, "cy": py, "r": 5, "fill": "#fff" if p["kind"] != "shield" else "#eee",
                              "stroke": {"power": "#b91c1c", "shield": "#6b7280"}.get(p["kind"], "#000"), "sw": 1.6,
                              "port": {"node": n["id"], "port": p["id"], "side": sd}, "n": n["id"]})
    # wires (only those that exist as edges)
    edges_out: dict[str, dict] = {}
    cables = {c["id"]: resolve_cable(c, g, datas) for c in g.get("cables", [])}
    lanes: dict[tuple, int] = {}
    labelled_cables: set = set()
    wire_items: list[dict] = []
    for e in g["edges"]:
        na, nb = find_node(g, e["from_node"]), find_node(g, e["to_node"])
        pa, pb = find_port(na, e["from_port"]), find_port(nb, e["to_port"])
        if not (pa and pb):
            continue
        ca, cb = na["x"] + NW / 2, nb["x"] + NW / 2
        def pick(n, p, other_cx):
            if p["side"] == "both":
                return "right" if other_cx >= n["x"] + NW / 2 else "left"
            return p["side"]
        sa, sb = pick(na, pa, cb), pick(nb, pb, ca)
        p1 = _port_pos(na, pa, views[na["id"]], sa)
        p2 = _port_pos(nb, pb, views[nb["id"]], sb)
        key = tuple(sorted((na["id"], nb["id"])))
        lane = lanes.get(key, 0)
        lanes[key] = lane + 1
        pts = route(p1, 1 if sa == "right" else -1, p2, 1 if sb == "right" else -1, lane)
        dash = "6 4" if e["kind"] == "shield" else None
        colour = {"power": "#b91c1c", "shield": "#6b7280", "soft": "#2563eb"}.get(e["kind"], "#000")
        wire_items.append({"t": "poly", "pts": [[round(a, 1), round(b, 1)] for a, b in pts], "stroke": colour, "sw": 1.6, "dash": dash, "e": e["id"]})
        cab = cables.get(e.get("cable_id", ""))
        label = " · ".join(x for x in (e.get("wire_no", ""), f"core {e['core']}" if e.get("core") else "") if x)
        # label on the longest horizontal run
        best = max(range(len(pts) - 1), key=lambda i: abs(pts[i + 1][0] - pts[i][0]) if abs(pts[i + 1][1] - pts[i][1]) < 1 else -1)
        (ax, ay), (bx, by) = pts[best], pts[best + 1]
        lx, ly = (ax + bx) / 2, ay - 4 - 0
        if label:
            wire_items.append({"t": "text", "x": round(lx, 1), "y": round(ly, 1), "s": label, "size": 10, "anchor": "middle", "e": e["id"],
                               "fill": "#c00000" if (cab and not e.get("core") and e["kind"] not in ("shield", "soft")) else "#222"})
        if cab and cab["id"] not in labelled_cables:
            labelled_cables.add(cab["id"])
            sh = cab["shield"].get("type") or ""
            sh_txt = f"shield: {sh}" if sh and sh != "none" else ("no shield" if sh == "none" else "shield: NOT DEFINED")
            lines3 = [(cab["tag"] or "CABLE TAG: " + MISSING, not cab["tag"]),
                      (" · ".join(x for x in (cab["type"], f"{cab['length']} m" if cab["length"] else "") if x) or "", False),
                      (sh_txt, sh == "")]
            for k, (txt, bad) in enumerate([x for x in lines3 if x[0]][::-1]):
                wire_items.append({"t": "text", "x": round(lx, 1), "y": round(ly - 14 - k * 12, 1), "s": txt[:30], "size": 10, "anchor": "middle",
                                   "bold": k == len([x for x in lines3 if x[0]]) - 1, "e": e["id"], "fill": "#c00000" if bad else "#1f2937"})
        edges_out[e["id"]] = {"from": {"node": na["id"], "port": pa["id"], "side": sa}, "to": {"node": nb["id"], "port": pb["id"], "side": sb},
                              "pts": [[round(a, 1), round(b, 1)] for a, b in pts], "kind": e["kind"]}
    # wires are drawn above band lines, below port dots: insert before the first circle
    first_circle = next((i for i, it in enumerate(items) if it["t"] == "circle"), len(items))
    items[first_circle:first_circle] = wire_items
    # title block + legend
    bx, by = W - 440, H - 160
    items.append({"t": "rect", "x": bx, "y": by, "w": 410, "h": 130, "fill": "#fff", "stroke": "#000", "sw": 1.2})
    rows = [("Project", meta.get("project", "")), ("Tag / Loop", f"{g.get('tag', '')} / {g.get('loop', '') or '—'}"),
            ("IODB", f"{meta.get('iodb_file', '')} {meta.get('iodb_revision', '')}".strip()),
            ("I/O Assignment", f"{meta.get('io_file', '')} {meta.get('io_revision', '')}".strip()),
            ("Generated", f"{meta.get('generated_by', '')}  {meta.get('generated_at', '')}".strip()), ("Sheet", "1 of 1")]
    for i, (k, val) in enumerate(rows):
        yy = by + 18 + i * 20
        items.append({"t": "text", "x": bx + 8, "y": yy, "s": k, "size": 10, "fill": "#555"})
        items.append({"t": "text", "x": bx + 110, "y": yy, "s": str(val)[:46], "size": 11, "bold": k == "Tag / Loop"})
    items.append({"t": "line", "x1": 30, "y1": H - 90, "x2": 80, "y2": H - 90, "stroke": "#000", "sw": 1.6})
    items.append({"t": "text", "x": 88, "y": H - 86, "s": "signal", "size": 10})
    items.append({"t": "line", "x1": 140, "y1": H - 90, "x2": 190, "y2": H - 90, "stroke": "#b91c1c", "sw": 1.6})
    items.append({"t": "text", "x": 198, "y": H - 86, "s": "power", "size": 10})
    items.append({"t": "line", "x1": 250, "y1": H - 90, "x2": 300, "y2": H - 90, "stroke": "#6b7280", "sw": 1.6, "dash": "6 4"})
    items.append({"t": "text", "x": 308, "y": H - 86, "s": "shield", "size": 10})
    return {"w": W, "h": H, "items": items, "nodes": nodes_out, "ports": ports_out, "edges": edges_out, "bands": bands,
            "zone_geometry": {"ML": ML, "ZW": ZW, "ZH": ZH, "TOP": TOP_H, "orientation": g.get("orientation", "horizontal")}}


# ── PNG (same scene) ────────────────────────────────────────────────────────
def _font(size: int, bold: bool):
    from PIL import ImageFont
    names = (["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf", "Helvetica.ttc"] if bold else
             ["DejaVuSans.ttf", "Arial.ttf", "arial.ttf", "Helvetica.ttc"])
    dirs = ["", "/usr/share/fonts/truetype/dejavu/", "/Library/Fonts/", "/System/Library/Fonts/Supplemental/", "/System/Library/Fonts/"]
    for d in dirs:
        for nme in names:
            try:
                return ImageFont.truetype(d + nme, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def render_png(scene: dict, scale: float = 1.5) -> bytes:
    from PIL import Image, ImageDraw
    W, H = int(scene["w"] * scale), int(scene["h"] * scale)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    S = scale

    def dashed(pts, fill, width, dash=(6, 4)):
        import math
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            L = math.hypot(x2 - x1, y2 - y1) or 1
            pos, on = 0.0, True
            while pos < L:
                seg = (dash[0] if on else dash[1]) * S
                end = min(L, pos + seg)
                if on:
                    d.line([(x1 + (x2 - x1) * pos / L, y1 + (y2 - y1) * pos / L), (x1 + (x2 - x1) * end / L, y1 + (y2 - y1) * end / L)], fill=fill, width=width)
                pos, on = end, not on

    for it in scene["items"]:
        t = it["t"]
        if t == "rect":
            fill = None if it.get("fill") in (None, "none") else it["fill"]
            d.rectangle([it["x"] * S, it["y"] * S, (it["x"] + it["w"]) * S, (it["y"] + it["h"]) * S], fill=fill,
                        outline=it.get("stroke"), width=max(1, round(it.get("sw", 1) * S * 0.7)))
        elif t == "line":
            pts = [(it["x1"] * S, it["y1"] * S), (it["x2"] * S, it["y2"] * S)]
            (dashed(pts, it["stroke"], max(1, round(it.get("sw", 1) * S * 0.7))) if it.get("dash") else
             d.line(pts, fill=it["stroke"], width=max(1, round(it.get("sw", 1) * S * 0.7))))
        elif t == "poly":
            pts = [(x * S, y * S) for x, y in it["pts"]]
            w = max(1, round(it.get("sw", 1) * S * 0.7))
            (dashed(pts, it["stroke"], w) if it.get("dash") else d.line(pts, fill=it["stroke"], width=w, joint="curve"))
        elif t == "circle":
            r = it["r"] * S
            d.ellipse([it["cx"] * S - r, it["cy"] * S - r, it["cx"] * S + r, it["cy"] * S + r], fill=it.get("fill") or "white",
                      outline=it.get("stroke", "#000"), width=max(1, round(it.get("sw", 1) * S * 0.7)))
        elif t == "text":
            f = _font(max(8, round(it.get("size", 11) * S * 0.9)), bool(it.get("bold")))
            anchor = {"middle": "ms", "end": "rs"}.get(it.get("anchor", "start"), "ls")
            d.text((it["x"] * S, it["y"] * S), str(it["s"]), font=f, fill=it.get("fill", "#000"), anchor=anchor)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
