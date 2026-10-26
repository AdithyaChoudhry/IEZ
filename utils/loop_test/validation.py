"""
Pre-generation validation. Each check is PASS / WARNING / ERROR; only ERRORS block generation.

ERROR  = the diagram would have to invent or silently choose engineering data
         (unmatched tag, unresolved source conflict, loop type incomplete, PLC channel missing, JB tag missing
         while a JB is drawn, signal not linked to an I/O row ...).
WARNING = details that make the drawing less complete but are not fabricated (cable length, ferrule, shield not set).
"""
from __future__ import annotations

from typing import Any

from .common import clean, is_value
from .io_assignment import io_class
from .library import FIELD_KINDS, LOOP_TYPES, SYSTEM_KINDS, signal_catalog

PASS, WARN, ERROR = "PASS", "WARNING", "ERROR"


def _check(cid: str, label: str, status: str, detail: str = "") -> dict:
    return {"id": cid, "label": label, "status": status, "detail": detail}


def validate_config(config: dict, entry: dict, data: dict) -> dict:
    F = data["fields"]
    checks: list[dict] = []
    add = checks.append

    def has(key: str) -> bool:
        return is_value((F.get(key) or {}).get("value", ""))

    # 1. tag matched in both documents
    if entry["in_iodb"] and entry["in_io"]:
        add(_check("tag", "Tag matched", PASS, f"matched by {entry.get('method') or 'tag'}"))
    else:
        missing = "I/O Assignment" if entry["in_iodb"] else "IODB"
        add(_check("tag", "Tag matched", ERROR, f"Tag is not present in the {missing}. Nothing is drawn from a guess."))

    # 2. loop
    c_loop = next((c for c in data["conflicts"] if c["field"] == "LOOP_NO"), None)
    if not has("LOOP_NO"):
        add(_check("loop", "Loop number", WARN, "No loop number in either document."))
    elif c_loop and not c_loop.get("decision"):
        add(_check("loop", "Loop number", WARN, f"IODB '{c_loop['iodb']}' ≠ I/O Assignment '{c_loop['io']}' – review."))
    else:
        add(_check("loop", "Loop number", PASS, F["LOOP_NO"]["value"]))

    # 3. loop type
    spec = LOOP_TYPES.get(config.get("loop_type", ""))
    if not spec or spec["status"] != "available":
        add(_check("loop_type", "Loop type selected", ERROR, "Choose a loop type or template."))
    else:
        add(_check("loop_type", "Loop type selected", PASS, spec["label"]))

    # 4. signal consistency (source conflict, the engineer's decision, loop type vs the assigned channel)
    unresolved = [c for c in data["conflicts"] if c["severity"] == "error" and not c.get("decision")]
    sig_conf = next((c for c in data["conflicts"] if c["field"] == "SIGNAL_TYPE"), None)
    skip_loop_types = ("MOTOR", "VALVE", "CUSTOM", "PACKAGE", "REMOTE_IO")
    want = spec["signal_type"] if spec else None
    if sig_conf and not sig_conf.get("decision"):
        add(_check("signal", "Signal type consistent", ERROR,
                   f"IODB says {sig_conf['iodb']}, I/O Assignment says {sig_conf['io']}. Decide which is correct."))
    elif sig_conf:                                      # engineer decided: the chosen document defines the signal class
        chosen = sig_conf["iodb"] if sig_conf["decision"] == "iodb" else sig_conf["io"]
        if want and config["loop_type"] not in skip_loop_types and want not in chosen.split("/"):
            add(_check("signal", "Signal type consistent", ERROR,
                       f"You accepted {chosen} ({'IODB' if sig_conf['decision'] == 'iodb' else 'I/O Assignment'}) "
                       f"but the loop type is {want}. Choose a matching loop type."))
        else:
            other = sig_conf["io"] if sig_conf["decision"] == "iodb" else sig_conf["iodb"]
            add(_check("signal", "Signal type consistent", WARN,
                       f"Engineer accepted {chosen}; the other document says {other}. Fix the source document when possible."))
    else:
        classes = {io_class(s.get("io_type", "")) for s in data["signals"]} - {""}
        if want and classes and want not in classes and config["loop_type"] not in skip_loop_types:
            add(_check("signal", "Signal type consistent", ERROR,
                       f"Loop type is {want} but the assigned I/O channel is {'/'.join(sorted(classes))}."))
        else:
            add(_check("signal", "Signal type consistent", PASS))

    # 5. JB
    kinds = [c["kind"] for c in config["components"]]
    jb_conf = next((c for c in data["conflicts"] if c["field"] == "JB_TAG"), None)
    if "junction_box" in kinds:
        if jb_conf and not jb_conf.get("decision"):
            add(_check("jb", "Junction box available", ERROR,
                       f"IODB '{jb_conf['iodb']}' ≠ I/O Assignment '{jb_conf['io']}'. Decide which is correct."))
        elif has("JB_TAG") or any(c.get("tag") for c in config["components"] if c["kind"] == "junction_box"):
            add(_check("jb", "Junction box available", PASS, F["JB_TAG"]["value"]))
        else:
            add(_check("jb", "Junction box available", ERROR, "A junction box is in the loop but no JB tag exists in the "
                                                             "documents. Provide it explicitly or remove the JB from the loop."))
        terms = any(has(k) for k in ("JB_TB1", "JB_TB2", "JB_TB3", "JB_TERMINAL_PLUS", "JB_TERMINAL_MINUS")) or \
            any(c.get("terminals") for c in config["components"] if c["kind"] == "junction_box")
        add(_check("jb_terminals", "JB terminals available", PASS if terms else WARN, "" if terms else "No JB terminal numbers in the source documents."))
    else:
        add(_check("jb", "Junction box", PASS, "not used in this loop"))

    # 6. cable
    cable_links = [l for l in config["links"] if l["cable"]["source"] in ("branch", "main")]
    for src, pre in (("branch", "BRANCH"), ("main", "MAIN")):
        if any(l["cable"]["source"] == src for l in cable_links):
            for fld, lab in (("CABLE_TAG", "tag"), ("CABLE_TYPE", "type"), ("CABLE_LENGTH", "length")):
                ok = has(f"{pre}_{fld}")
                add(_check(f"{src}_{lab}", f"{src.capitalize()} cable {lab} available", PASS if ok else WARN,
                           "" if ok else f"{src.capitalize()} cable {lab} is not available in the IODB."))
    # 7. PLC / DCS card
    systems = [c for c in config["components"] if c["kind"] in SYSTEM_KINDS]
    if systems:
        sigs = data["signals"]
        linked = [s for s in config.get("signals", []) if isinstance(s.get("io_index"), int) and 0 <= s["io_index"] < len(sigs)]
        if config.get("signals") and len(linked) != len(config["signals"]):
            names = ", ".join(s["name"] for s in config["signals"] if s not in linked)
            add(_check("signal_link", "Every signal linked to an I/O row", ERROR,
                       f"Not linked: {names}. PLC channels are never allocated automatically."))
        for key, lab, level in (("RACK", "Rack", ERROR), ("SLOT", "Slot", ERROR), ("CHANNEL", "Channel", ERROR),
                                ("MODULE", "Module", WARN), ("PLC", "PLC / DCS name", WARN)):
            if len(config.get("signals", [])) > 1 and key in ("RACK", "SLOT", "CHANNEL"):
                ok = bool(linked) and all(clean(sigs[s["io_index"]].get(key.lower(), "")) for s in linked)
            else:
                ok = has(key) or any(clean(sigs[s["io_index"]].get(key.lower(), "")) for s in linked)
            add(_check(key.lower(), f"{lab} available", PASS if ok else level,
                       "" if ok else f"{lab} is missing in the I/O Assignment – nothing is invented."))
        term = has("TERMINAL_STRIP") or has("TERMINAL") or has("TERMINAL_SIGNAL") or \
            any(c.get("terminals") for c in config["components"])
        add(_check("terminal", "Terminals available", PASS if term else WARN, "" if term else "No terminal details found."))
    else:
        add(_check("plc", "PLC / DCS in loop", WARN, "No PLC / DCS / remote I/O component – the loop ends at the panel."))

    # 8. wires and shielding
    bad = [l for l in config["links"] if not l.get("wires")]
    add(_check("wires", "Wire count defined", ERROR if bad else PASS, "A segment has no wires." if bad else ""))
    no_shield = [l for l in config["links"] if l["cable"]["source"] != "none" and l["cable"].get("shield_type") is None]
    add(_check("shield", "Shielding defined", WARN if no_shield else PASS,
               "Shield type is not set on a cable – choose it (including 'No shield')." if no_shield else ""))
    open_term = [l for l in config["links"] if l["cable"].get("shield_type") not in (None, "none")
                 and not l["cable"].get("shield_termination")]
    if open_term:
        add(_check("shield_term", "Shield termination defined", WARN, "Shield termination is not set."))

    # 9. special-case parameters
    p, lt = config.get("params", {}), config.get("loop_type")
    problems = []
    if lt == "RTD" and str(p.get("rtd_wires", "")) not in ("2", "3", "4"):
        problems.append("RTD wiring (2/3/4-wire) not chosen")
    if lt == "TC" and not p.get("tc_type"):
        problems.append("Thermocouple type not chosen")
    if lt == "MOTOR":
        if not p.get("starter"):
            problems.append("Motor starter type not chosen")
        if not config.get("signals"):
            problems.append("No motor signals selected")
    if lt == "VALVE":
        if not p.get("valve_type"):
            problems.append("Valve type not chosen")
        if not config.get("signals"):
            problems.append("No valve signals selected")
    if lt in ("MOTOR", "VALVE"):
        allowed = {s["id"] for s in signal_catalog(lt, p)}
        stray = [s["id"] for s in config.get("signals", []) if s["id"] not in allowed]
        if stray:
            problems.append("Signals not valid for the chosen type: " + ", ".join(stray))
    add(_check("special", "Special-case parameters complete", ERROR if problems else PASS, "; ".join(problems)))

    # 10. a field device and a system end
    kinds_set = set(kinds)
    if not (kinds_set & FIELD_KINDS) and lt not in ("PACKAGE", "CUSTOM"):
        add(_check("field", "Field device in loop", WARN, "No field device component."))

    errors = sum(1 for c in checks if c["status"] == ERROR)
    warnings = sum(1 for c in checks if c["status"] == WARN)
    return {"checks": checks, "errors": errors, "warnings": warnings,
            "passed": sum(1 for c in checks if c["status"] == PASS), "total": len(checks),
            "can_generate": errors == 0, "unresolved_conflicts": len(unresolved)}
