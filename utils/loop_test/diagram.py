"""
Generic diagram engine: LoopConfiguration + merged source data -> diagram model -> SVG / Excel.

There is no per-loop-type drawing code. The loop type only contributes DEFAULT components, wires
and signals (library.py); this module draws whatever configuration it is given.

Values that are not in the source documents (or entered by the engineer) are drawn as MISSING - never invented.
"""
from __future__ import annotations

import re
from html import escape
from typing import Any

from .common import IO, IODB, USER, clean, is_value
from .library import COMPONENT_KINDS, FIELD_KINDS, LOOP_TYPES, SHIELD_TERMINATIONS, SHIELD_TYPES, SYSTEM_KINDS

MISSING = "MISSING"


def _val(F: dict, key: str) -> tuple[str, str, bool]:
    """(text, source, available) for a merged field; 'TBA', '-' etc. count as not available."""
    f = F.get(key) or {}
    text = clean(f.get("value", ""))
    return text, f.get("source", ""), is_value(text)


def _line(label: str, F: dict, key: str, required: bool = True) -> dict | None:
    text, src, ok = _val(F, key)
    if not ok and not required:
        return None
    return {"text": f"{label}: {text if ok else MISSING}", "missing": not ok, "source": src}


def derive_cable(cable_type: str) -> dict:
    """Pairs / cores / size derived from a type string such as '12PX1.5 Sqmm' (labelled 'derived')."""
    m = re.match(r"^\s*(\d+)\s*P\s*[Xx]\s*([\d.]+)", cable_type or "", re.IGNORECASE)
    if m:
        pairs = int(m.group(1))
        return {"pairs": str(pairs), "cores": str(pairs * 2), "size": m.group(2)}
    m = re.match(r"^\s*(\d+)\s*[Xx]\s*([\d.]+)", cable_type or "", re.IGNORECASE)
    if m:
        return {"pairs": "", "cores": m.group(1), "size": m.group(2)}
    return {}


def _signal_rows(config: dict, data: dict) -> list[dict]:
    rows = []
    io_rows = data.get("signals", [])
    for s in config.get("signals", []):
        idx = s.get("io_index")
        io = io_rows[idx] if isinstance(idx, int) and 0 <= idx < len(io_rows) else None
        rows.append({"name": s["name"], "signal_type": s["signal_type"], "direction": s["direction"], "io": io,
                     "io_index": idx})
    return rows


def _block(c: dict, config: dict, data: dict) -> dict:
    F, kind = data["fields"], c["kind"]
    group = COMPONENT_KINDS.get(kind, {}).get("group", "")
    title = c.get("tag") or ""
    lines: list[dict] = []
    terms: list[dict] = []
    if kind in FIELD_KINDS:
        title = c.get("tag") or F.get("TAG_NO", {}).get("value", "") or config.get("tag_no", "")
        for item in (_line("Type", F, "INSTRUMENT_TYPE", False), _line("Service", F, "SIGNAL_DESCRIPTION", False),
                     _line("Power", F, "POWER_SUPPLY", False), _line("IS/NIS", F, "IS_NIS", False)):
            if item:
                lines.append(item)
        hart = config.get("params", {}).get("hart")
        if hart is True or (hart is None and clean(F.get("HART", {}).get("value", "")).upper() in ("Y", "YES")):
            lines.append({"text": "HART: yes", "missing": False, "source": USER if hart else IODB})
    elif kind == "junction_box":
        text, src, ok = _val(F, "JB_TAG")
        title = c.get("tag") or (text if ok else "")
        if not title:
            lines.append({"text": f"Tag: {MISSING}", "missing": True, "source": ""})
        for key, lab in (("JB_TB1", "TB1"), ("JB_TB2", "TB2"), ("JB_TB3", "TB3"), ("JB_PAIR", "Pair"),
                         ("JB_TERMINAL_PLUS", "Terminal +"), ("JB_TERMINAL_MINUS", "Terminal -")):
            t, s_, ok2 = _val(F, key)
            if ok2:
                terms.append({"label": lab, "value": t, "missing": False, "source": s_})
    elif kind in ("marshalling", "terminal_strip"):
        t, s_, ok = _val(F, "TERMINAL_STRIP")
        title = c.get("tag") or (t if ok else c.get("label", ""))
        for key, lab in (("TERMINAL_CMN", "CMN"), ("TERMINAL_SIGNAL", "SIG"), ("TERMINAL_ZERO", "ZERO"), ("TERMINAL", "Terminal")):
            tv, sv, ok2 = _val(F, key)
            if ok2:
                terms.append({"label": lab, "value": tv, "missing": False, "source": sv})
    elif kind in SYSTEM_KINDS:
        plc, src, ok = _val(F, "PLC")
        title = c.get("tag") or (plc if ok else "")
        rows = _signal_rows(config, data)
        if len(rows) > 1:
            for r in rows:
                io = r["io"]
                loc = (f"R{io['rack'] or '?'}/S{io['slot'] or '?'}/CH{io['channel'] or '?'}" if io else MISSING)
                lines.append({"text": f"{r['name']} ({r['signal_type']}): {loc}", "missing": io is None, "source": IO})
        else:
            for item in (_line("Rack", F, "RACK"), _line("Slot", F, "SLOT"), _line("Module", F, "MODULE", False),
                         _line("Channel", F, "CHANNEL"), _line("I/O type", F, "IO_TYPE", False),
                         _line("Address", F, "ADDRESS", False)):
                if item:
                    lines.append(item)
    for t in c.get("terminals", []):
        terms.append({"label": t.get("number") or "?", "value": " ".join(x for x in (t.get("polarity", ""), t.get("description", "")) if x),
                      "missing": False, "source": USER})
    for note in str(c.get("notes") or "").splitlines():
        if note.strip():
            lines.append({"text": note.strip(), "missing": False, "source": USER})
    return {"id": c["id"], "kind": kind, "group": group, "placement": c.get("placement", "main"),
            "attach_to": c.get("attach_to", ""), "heading": c.get("label") or COMPONENT_KINDS.get(kind, {}).get("label", kind),
            "title": title, "lines": lines, "terminals": terms}


def _link(l: dict, F: dict) -> dict:
    cab = l.get("cable", {})
    src = cab.get("source", "none")
    lines: list[dict] = []
    cable_type = ""
    if src in ("branch", "main"):
        pre = "BRANCH" if src == "branch" else "MAIN"
        for lab, key in (("Cable", f"{pre}_CABLE_TAG"), ("Type", f"{pre}_CABLE_TYPE"), ("Length", f"{pre}_CABLE_LENGTH")):
            t, s_, ok = _val(F, key)
            lines.append({"text": f"{lab}: {t if ok else MISSING}", "missing": not ok, "source": s_})
            if key.endswith("TYPE") and ok:
                cable_type = t
        if src == "branch":
            for lab, key in (("Ferrule", "BRANCH_FERRULE"), ("Route", "ROUTE_NUMBER")):
                t, s_, ok = _val(F, key)
                if ok:
                    lines.append({"text": f"{lab}: {t}", "missing": False, "source": s_})
        else:
            t, s_, ok = _val(F, "MAIN_CABLE_FERRULE")
            if ok:
                lines.append({"text": f"Ferrule: {t}", "missing": False, "source": s_})
    elif src == "custom":
        for lab, key in (("Cable", "tag"), ("Type", "type"), ("Length", "length")):
            if cab.get(key):
                lines.append({"text": f"{lab}: {cab[key]}", "missing": False, "source": USER})
        cable_type = cab.get("type", "")
    derived = derive_cable(cable_type)
    pairs = cab.get("pairs") or derived.get("pairs", "")
    cores = cab.get("cores") or derived.get("cores", "")
    if pairs or cores:
        tag = "" if (cab.get("pairs") or cab.get("cores")) else " (derived)"
        lines.append({"text": f"Cores: {cores or '?'} / Pairs: {pairs or '?'}{tag}", "missing": False,
                      "source": USER if tag == "" else IODB})
    stype = cab.get("shield_type")
    sterm = cab.get("shield_termination")
    shield = {"defined": stype is not None, "type": SHIELD_TYPES.get(stype, "") if stype else "",
              "termination": SHIELD_TERMINATIONS.get(sterm, "") if sterm else "",
              "note": cab.get("termination_note", "")}
    wires = [{"label": w.get("label") or w.get("role", ""), "colour": w.get("colour", ""), "number": w.get("number", ""),
              "terminal_from": w.get("terminal_from", ""), "terminal_to": w.get("terminal_to", "")} for w in l.get("wires", [])]
    def _cf(prefix: str) -> str:
        for ln in lines:
            if ln["text"].startswith(prefix + ":"):
                return ln["text"].split(":", 1)[1].strip()
        return ""

    return {"from_id": l["from_id"], "to_id": l["to_id"], "lines": lines, "wires": wires, "shield": shield,
            "has_cable": src != "none",
            "cable_fields": {"tag": _cf("Cable"), "type": _cf("Type"), "length": _cf("Length")}}


def source_rows(data: dict) -> list[dict]:
    return [{"label": f.get("label", k), "value": f.get("value", "") or "—", "source": f.get("source", "")}
            for k, f in data["fields"].items() if f.get("available") and is_value(f.get("value", ""))]


def build_diagram(config: dict, data: dict, meta: dict) -> dict:
    blocks = [_block(c, config, data) for c in config["components"]]
    links = [_link(l, data["fields"]) for l in config["links"]]
    spec = LOOP_TYPES.get(config["loop_type"], {})
    sig_rows = []
    for r in _signal_rows(config, data):
        io = r["io"] or {}
        sig_rows.append({"name": r["name"], "type": r["signal_type"], "direction": r["direction"],
                         "io_type": io.get("io_type", ""), "rack": io.get("rack", ""), "slot": io.get("slot", ""),
                         "module": io.get("module", ""), "channel": io.get("channel", ""),
                         "terminal": " / ".join(x for x in (io.get("terminal_strip", ""), io.get("terminal_cmn", ""),
                                                            io.get("terminal_signal", ""), io.get("terminal_zero", "")) if x),
                         "status": "linked" if r["io"] else "NOT LINKED"})
    return {
        "tag": config.get("tag_no", ""), "loop": config.get("loop_number", ""),
        "loop_type": spec.get("label", config["loop_type"]), "template": config.get("template_id", ""),
        "orientation": config.get("layout", {}).get("orientation", "vertical"),
        "flow": config.get("layout", {}).get("flow_direction", ""),
        "positions": config.get("layout", {}).get("positions", {}),
        "blocks": blocks, "links": links, "signals": sig_rows, "sources": source_rows(data),
        "title_block": meta, "params": config.get("params", {}),
    }


# ── SVG ─────────────────────────────────────────────────────────────────────
def _esc(s: Any) -> str:
    return escape(str(s), quote=True)


def render_svg(model: dict) -> str:
    """Black-on-white engineering style preview of the SAME model that is written to Excel."""
    vertical = model["orientation"] != "horizontal"
    main = [b for b in model["blocks"] if b["placement"] == "main"]
    side = [b for b in model["blocks"] if b["placement"] == "side"]
    W, LH, PAD = 300, 16, 8

    def height(b: dict) -> int:
        return 34 + LH * (len(b["lines"]) + (1 if b["terminals"] else 0)) + 2 * PAD

    pos: dict[str, tuple[float, float, float, float]] = {}
    gap = 110
    x0, y0 = 260 if side else 40, 70
    if vertical:
        y = y0
        for b in main:
            h = height(b)
            pos[b["id"]] = (x0, y, W, h)
            y += h + gap
        total_w, total_h = x0 + W + 330, y - gap + 40
    else:
        x = 40
        for b in main:
            h = height(b)
            pos[b["id"]] = (x, y0 + 40, W, h)
            x += W + gap + 60
        total_w, total_h = x - gap + 20, y0 + 40 + max((height(b) for b in main), default=100) + 60
    for b in side:
        target = pos.get(b["attach_to"])
        h = height(b)
        pos[b["id"]] = (30, (target[1] if target else y0) + 10, 200, h) if vertical else (40, y0 + 40 + 180, 200, h)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {max(total_w, 760)} {max(total_h, 300) + 130 + 18 * (len(model["signals"]) + 1)}" '
           f'width="100%" font-family="Arial, Helvetica, sans-serif" font-size="12">',
           '<rect width="100%" height="100%" fill="#ffffff"/>',
           f'<text x="30" y="30" font-size="16" font-weight="bold">LOOP WIRING (TEST) — {_esc(model["tag"])}</text>',
           f'<text x="30" y="48" fill="#444">{_esc(model["loop_type"])} · loop {_esc(model["loop"] or "—")} · '
           f'flow: {_esc(model["flow"].replace("_", " "))}</text>']

    for b in model["blocks"]:
        if b["id"] not in pos:
            continue
        x, y, w, h = pos[b["id"]]
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fff" stroke="#000" stroke-width="1.5"/>')
        out.append(f'<text x="{x + PAD}" y="{y + 15}" font-size="10" fill="#555">{_esc(b["heading"].upper())}</text>')
        out.append(f'<text x="{x + PAD}" y="{y + 33}" font-size="14" font-weight="bold">{_esc(b["title"] or "—")}</text>')
        ty = y + 34 + PAD + 4
        for ln in b["lines"]:
            col = "#c00000" if ln["missing"] else "#000"
            out.append(f'<text x="{x + PAD}" y="{ty + 8}" fill="{col}" font-style="{"italic" if ln["missing"] else "normal"}">{_esc(ln["text"])}</text>')
            ty += LH
        if b["terminals"]:
            cells = "   ".join(f'{t["label"]}:{t["value"]}' for t in b["terminals"])
            out.append(f'<text x="{x + PAD}" y="{ty + 8}" font-family="monospace" font-size="11">▸ {_esc(cells[:46])}</text>')

    for l in model["links"]:
        a, c = pos.get(l["from_id"]), pos.get(l["to_id"])
        if not a or not c:
            continue
        if vertical and a[0] == c[0]:
            x = a[0] + a[2] / 2
            y1, y2 = a[1] + a[3], c[1]
            mid = (y1 + y2) / 2
            out.append(f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="#000" stroke-width="1.5"/>')
            out.append(f'<polygon points="{x - 5},{y2 - 8} {x + 5},{y2 - 8} {x},{y2}" fill="#000"/>')
            ty = mid - 8 * len(l["lines"]) / 1.5
            for ln in l["lines"]:
                col = "#c00000" if ln["missing"] else "#000"
                out.append(f'<text x="{x + 12}" y="{ty}" fill="{col}" font-size="11">{_esc(ln["text"])}</text>')
                ty += 14
            if l["wires"]:
                out.append(f'<text x="{x + 12}" y="{ty}" font-size="11" fill="#333">{len(l["wires"])} wires: {_esc(", ".join(w["label"] for w in l["wires"])[:60])}</text>')
                ty += 14
            sh = l["shield"]
            out.append(f'<text x="{x + 12}" y="{ty}" font-size="11" fill="{"#333" if sh["defined"] else "#c00000"}">'
                       f'Shield: {_esc(sh["type"] or "not defined")}{(" · " + _esc(sh["termination"])) if sh["termination"] else ""}</text>')
        elif not vertical:
            y = a[1] + a[3] / 2
            x1, x2 = a[0] + a[2], c[0]
            out.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="#000" stroke-width="1.5"/>')
            out.append(f'<polygon points="{x2 - 8},{y - 5} {x2 - 8},{y + 5} {x2},{y}" fill="#000"/>')
            ty = y - 30
            for ln in l["lines"][:3]:
                out.append(f'<text x="{x1 + 4}" y="{ty}" font-size="10" fill="{"#c00000" if ln["missing"] else "#000"}">{_esc(ln["text"][:24])}</text>')
                ty += 12
        else:                                   # side component (power supply ...) -> its target
            out.append(f'<line x1="{a[0] + a[2]}" y1="{a[1] + 30}" x2="{c[0]}" y2="{a[1] + 30}" stroke="#000" stroke-width="1.5"/>')
            out.append(f'<text x="{a[0] + a[2] + 6}" y="{a[1] + 24}" font-size="10">{len(l["wires"])} wires</text>')

    ty = (max((p[1] + p[3] for p in pos.values()), default=100) + 36) if vertical else y0 + 40 + 230
    if model["signals"]:
        out.append(f'<text x="30" y="{ty}" font-weight="bold">SIGNALS</text>')
        ty += 16
        for s in model["signals"]:
            col = "#c00000" if s["status"] != "linked" else "#000"
            where = f'R{s["rack"] or "?"}/S{s["slot"] or "?"}/CH{s["channel"] or "?"}' if s["status"] == "linked" else "NOT LINKED"
            out.append(f'<text x="40" y="{ty}" fill="{col}" font-size="11">{_esc(s["name"])} [{_esc(s["type"])}]  →  {_esc(where)}'
                       f'  {_esc(s["terminal"])}</text>')
            ty += 16
    out.append("</svg>")
    return "".join(out)
