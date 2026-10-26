"""
Loop Wiring (Test) service: disk-backed sessions (survive restarts/deploys), matching, per-tag
merged data, validation, preview, generation and saved templates.

Independent of the production Loop Wiring Generator - nothing here imports or changes it.
"""
from __future__ import annotations

import copy
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models.loop_test import LoopTestTemplate
from . import document_registry as reg


def _lt():
    """Import the loop_test package from utils/ (same path trick the other services use)."""
    here = Path(__file__).resolve()
    for p in (here.parents[2], here.parents[3], Path("/app")):
        if (p / "utils").is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import utils.loop_test.diagram as diagram
    import utils.loop_test.excel_out as excel_out
    import utils.loop_test.io_assignment as io_assignment
    import utils.loop_test.iodb_fields as iodb_fields
    import utils.loop_test.library as library
    import utils.loop_test.matcher as matcher
    import utils.loop_test.validation as validation

    class NS:  # tiny namespace so callers read lt.library.x
        pass
    ns = NS()
    ns.diagram, ns.excel_out, ns.io_assignment, ns.iodb_fields = diagram, excel_out, io_assignment, iodb_fields
    ns.library, ns.matcher, ns.validation = library, matcher, validation
    return ns


class LoopTestError(Exception):
    """Expected, user-facing problem."""


_CACHE: dict[str, dict] = {}


def _root() -> Path:
    base = reg._store_dir() / "loop_test"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _dir(session_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", session_id or ""):
        raise LoopTestError("Unknown session.")
    return _root() / session_id


def _load_state(session_id: str, user_id: int) -> dict:
    path = _dir(session_id) / "state.json"
    if not path.exists():
        raise LoopTestError("Session not found (it may have expired). Upload the files again.")
    state = json.loads(path.read_text())
    if state.get("user_id") != user_id:
        raise LoopTestError("This session belongs to another user.")
    return state


def _save_state(session_id: str, state: dict) -> None:
    (_dir(session_id) / "state.json").write_text(json.dumps(state, indent=1))


# ── sessions & uploads ──────────────────────────────────────────────────────
def create_session(user_id: int, project_id: str, iodb_name: str, iodb_bytes: bytes, iodb_revision: str = "") -> dict:
    lt = _lt()
    try:
        data = lt.iodb_fields.parse_iodb(iodb_bytes, iodb_name)
    except ValueError as exc:
        raise LoopTestError(str(exc))
    pid = reg.normalize_project_id(project_id) if project_id else ""
    sid = uuid.uuid4().hex
    folder = _dir(sid)
    folder.mkdir(parents=True)
    (folder / "iodb.xlsx").write_bytes(iodb_bytes)
    state = {"session_id": sid, "user_id": user_id, "project_id": pid, "created_at": datetime.utcnow().isoformat() + "Z",
             "iodb": {"file": iodb_name, "revision": iodb_revision}, "io": None,
             "decisions": {"suggestions": {}, "conflicts": {}}, "configs": {}, "output": None}
    _save_state(sid, state)
    _CACHE[sid] = {"iodb": data}
    return {"session_id": sid, "iodb": data.summary()}


def attach_io(session_id: str, user_id: int, name: str, data: bytes, revision: str = "",
              mapping_override: Optional[dict] = None) -> dict:
    lt = _lt()
    state = _load_state(session_id, user_id)
    try:
        parsed = lt.io_assignment.parse_io_assignment(data, name, mapping_override)
    except ValueError as exc:
        raise LoopTestError(str(exc))
    (_dir(session_id) / "io.xlsx").write_bytes(data)
    state["io"] = {"file": name, "revision": revision, "mapping_override": mapping_override or {}, "confirmed": False}
    state["decisions"] = {"suggestions": {}, "conflicts": {}}          # decisions belong to the previous match
    _save_state(session_id, state)
    _CACHE.setdefault(session_id, {})["io"] = parsed
    return parsed.summary()


def set_io_mapping(session_id: str, user_id: int, mapping: dict, confirm: bool) -> dict:
    """mapping: {field: column letter | None}. Re-parses the stored file with the engineer's corrections."""
    lt = _lt()
    state = _load_state(session_id, user_id)
    if not state.get("io"):
        raise LoopTestError("Upload the I/O Assignment first.")
    data = (_dir(session_id) / "io.xlsx").read_bytes()
    try:
        parsed = lt.io_assignment.parse_io_assignment(data, state["io"]["file"], mapping)
    except ValueError as exc:
        raise LoopTestError(str(exc))
    state["io"]["mapping_override"] = mapping
    state["io"]["confirmed"] = bool(confirm)
    _save_state(session_id, state)
    _CACHE.setdefault(session_id, {})["io"] = parsed
    return parsed.summary()


def _parsed(session_id: str, state: dict) -> tuple[Any, Any]:
    lt = _lt()
    cache = _CACHE.setdefault(session_id, {})
    if "iodb" not in cache:
        cache["iodb"] = lt.iodb_fields.parse_iodb((_dir(session_id) / "iodb.xlsx").read_bytes(), state["iodb"]["file"])
    if state.get("io") and "io" not in cache:
        cache["io"] = lt.io_assignment.parse_io_assignment((_dir(session_id) / "io.xlsx").read_bytes(), state["io"]["file"],
                                                           state["io"].get("mapping_override") or None)
    return cache["iodb"], cache.get("io")


def session_info(session_id: str, user_id: int) -> dict:
    state = _load_state(session_id, user_id)
    iodb, io = _parsed(session_id, state)
    return {"session_id": session_id, "project_id": state["project_id"], "iodb": {**iodb.summary(), **state["iodb"]},
            "io": ({**io.summary(), **state["io"]} if io else None),
            "decisions": state["decisions"], "saved_configs": sorted(state["configs"]),
            "output": state.get("output")}


# ── matching ────────────────────────────────────────────────────────────────
def run_match(session_id: str, user_id: int) -> dict:
    lt = _lt()
    state = _load_state(session_id, user_id)
    iodb, io = _parsed(session_id, state)
    if io is None:
        raise LoopTestError("Upload the I/O Assignment before matching.")
    result = lt.matcher.match_all(iodb.rows, io.rows, state["decisions"])
    _CACHE[session_id]["match"] = result
    return result


def _match(session_id: str, state: dict) -> dict:
    cached = _CACHE.get(session_id, {}).get("match")
    return cached if cached else run_match(session_id, state["user_id"])


def list_matches(session_id: str, user_id: int, status: str = "", q: str = "", limit: int = 100, offset: int = 0) -> dict:
    state = _load_state(session_id, user_id)
    result = _match(session_id, state)
    items = result["entries"]
    if status:
        items = [e for e in items if e["status"] == status]
    if q:
        needle = q.lower()
        items = [e for e in items if needle in e["tag"].lower() or needle in (e["loop"] or "").lower()]
    page = items[offset: offset + max(1, min(limit, 500))]
    return {"summary": result["summary"], "total": len(items), "offset": offset,
            "items": [{k: e[k] for k in ("tag", "loop", "status", "method", "in_iodb", "in_io", "signals", "io_tag")} |
                      {"conflicts": [{k: c[k] for k in ("field", "label", "severity", "iodb", "io", "decision")} for c in e["conflicts"]],
                       "suggestions": e["suggestions"]} for e in page]}


def _entry(session_id: str, state: dict, tag: str) -> dict:
    entry = next((e for e in _match(session_id, state)["entries"] if e["tag"] == tag), None)
    if entry is None:
        raise LoopTestError(f"Tag '{tag}' is not in the match results.")
    return entry


def tag_detail(session_id: str, user_id: int, tag: str, overrides: Optional[dict] = None) -> dict:
    lt = _lt()
    state = _load_state(session_id, user_id)
    iodb, io = _parsed(session_id, state)
    entry = _entry(session_id, state, tag)
    data = lt.matcher.merged_tag_data(entry, iodb.rows, io.rows if io else [], state["decisions"], overrides)
    sig_class = next((lt.io_assignment.io_class(s["io_type"]) for s in data["signals"] if s["io_type"]), "")
    return {"tag": tag, "status": entry["status"], "method": entry["method"], "loop": entry["loop"],
            "fields": {k: v for k, v in data["fields"].items()}, "signals": data["signals"], "conflicts": data["conflicts"],
            "suggestions": entry["suggestions"], "saved_config": state["configs"].get(tag),
            "suggested_loop_type": {"AI": "AI_2WIRE", "AO": "AO", "DI": "DI", "DO": "DO", "RTD": "RTD", "TC": "TC",
                                    "PI": "PULSE"}.get(sig_class or "", "")}


def save_decision(session_id: str, user_id: int, kind: str, tag: str, field: str = "", choice: str = "",
                  iodb_tag: str = "") -> dict:
    state = _load_state(session_id, user_id)
    dec = state["decisions"]
    if kind == "conflict":
        if choice not in ("iodb", "io", ""):
            raise LoopTestError("Choose 'iodb' or 'io'.")
        entry_tags = dec["conflicts"].setdefault(tag, {})
        if choice:
            entry_tags[field] = choice
        else:
            entry_tags.pop(field, None)
    elif kind == "suggestion":
        if choice not in ("accept", "reject", ""):
            raise LoopTestError("Choose 'accept' or 'reject'.")
        if choice:
            dec["suggestions"][tag] = {"iodb_tag": iodb_tag, "action": choice}
        else:
            dec["suggestions"].pop(tag, None)
    else:
        raise LoopTestError("Unknown decision kind.")
    _save_state(session_id, state)
    _CACHE.get(session_id, {}).pop("match", None)
    return run_match(session_id, user_id)["summary"]


# ── configuration, preview, validation ──────────────────────────────────────
def default_config(session_id: str, user_id: int, tag: str, loop_type: str, params: dict, signals: list[str],
                   template_id: str = "") -> dict:
    lt = _lt()
    state = _load_state(session_id, user_id)
    entry = _entry(session_id, state, tag)
    try:
        cfg = lt.library.new_config(loop_type, params, signals, template_id, tag, entry["loop"], state["project_id"])
    except ValueError as exc:
        raise LoopTestError(str(exc))
    n_io = len(entry["io_idx"])
    if n_io == 1:                                                   # unambiguous: one signal <-> the one I/O row
        for s in cfg["signals"]:
            s["io_index"] = 0
    return cfg


def _merged(session_id: str, state: dict, config: dict) -> tuple[dict, dict]:
    lt = _lt()
    iodb, io = _parsed(session_id, state)
    entry = _entry(session_id, state, config["tag_no"])
    return entry, lt.matcher.merged_tag_data(entry, iodb.rows, io.rows if io else [], state["decisions"],
                                             config.get("overrides"))


def _meta(state: dict, user: str) -> dict:
    return {"project": state["project_id"] or "—", "iodb_file": state["iodb"]["file"],
            "iodb_revision": state["iodb"].get("revision", ""), "io_file": (state.get("io") or {}).get("file", ""),
            "io_revision": (state.get("io") or {}).get("revision", ""), "generated_by": user,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M")}


def _prepare(config: dict) -> dict:
    lt = _lt()
    cfg = copy.deepcopy(config)
    if not cfg.get("tag_no"):
        raise LoopTestError("The configuration has no tag.")
    cfg.setdefault("links", [])
    return lt.library.reconcile_links(cfg)


def preview(session_id: str, user_id: int, user_label: str, config: dict) -> dict:
    lt = _lt()
    state = _load_state(session_id, user_id)
    cfg = _prepare(config)
    entry, data = _merged(session_id, state, cfg)
    model = lt.diagram.build_diagram(cfg, data, _meta(state, user_label))
    return {"svg": lt.diagram.render_svg(model), "validation": lt.validation.validate_config(cfg, entry, data),
            "config": cfg, "model": {"signals": model["signals"]}}


def validate_only(session_id: str, user_id: int, config: dict) -> dict:
    lt = _lt()
    state = _load_state(session_id, user_id)
    cfg = _prepare(config)
    entry, data = _merged(session_id, state, cfg)
    return lt.validation.validate_config(cfg, entry, data)


def save_config(session_id: str, user_id: int, config: dict) -> dict:
    state = _load_state(session_id, user_id)
    cfg = _prepare(config)
    state["configs"][cfg["tag_no"]] = cfg
    _save_state(session_id, state)
    return {"saved": cfg["tag_no"], "count": len(state["configs"])}


# ── generation ──────────────────────────────────────────────────────────────
def generate(session_id: str, user_id: int, user_label: str, tags: list[str], configs: Optional[dict] = None,
             allow_warnings: bool = True) -> dict:
    lt = _lt()
    state = _load_state(session_id, user_id)
    configs = configs or {}
    items, results = [], []
    for tag in tags:
        raw = configs.get(tag) or state["configs"].get(tag)
        if raw is None:
            results.append({"tag": tag, "status": "SKIPPED", "reason": "No loop configuration for this tag."})
            continue
        try:
            cfg = _prepare(raw)
            entry, data = _merged(session_id, state, cfg)
            check = lt.validation.validate_config(cfg, entry, data)
        except LoopTestError as exc:
            results.append({"tag": tag, "status": "SKIPPED", "reason": str(exc)})
            continue
        if not check["can_generate"]:
            bad = [c["label"] + (": " + c["detail"] if c["detail"] else "") for c in check["checks"] if c["status"] == "ERROR"]
            results.append({"tag": tag, "status": "BLOCKED", "reason": "; ".join(bad), "errors": check["errors"]})
            continue
        if check["warnings"] and not allow_warnings:
            results.append({"tag": tag, "status": "BLOCKED", "reason": f"{check['warnings']} warning(s) not accepted.",
                            "warnings": check["warnings"]})
            continue
        model = lt.diagram.build_diagram(cfg, data, _meta(state, user_label))
        items.append({"tag": tag, "model": model})
        results.append({"tag": tag, "status": "GENERATED", "warnings": check["warnings"]})
    if not items:
        return {"generated": 0, "results": results, "filename": None}
    out = lt.excel_out.build_workbook(items)
    project = re.sub(r"[^A-Za-z0-9._-]+", "_", state["project_id"] or "Project")
    rev = re.sub(r"[^A-Za-z0-9._-]+", "_", state["iodb"].get("revision") or "R0")
    filename = f"Loop_Wiring_Test_{project}_{rev}.xlsx"
    (_dir(session_id) / "output.xlsx").write_bytes(out)
    state["output"] = {"filename": filename, "tags": [i["tag"] for i in items], "at": datetime.utcnow().isoformat() + "Z"}
    _save_state(session_id, state)
    return {"generated": len(items), "results": results, "filename": filename}


def output_file(session_id: str, user_id: int) -> tuple[Path, str]:
    state = _load_state(session_id, user_id)
    if not state.get("output") or not (_dir(session_id) / "output.xlsx").exists():
        raise LoopTestError("Nothing has been generated in this session yet.")
    return _dir(session_id) / "output.xlsx", state["output"]["filename"]


# ── templates ───────────────────────────────────────────────────────────────
def list_templates(db: Session) -> list[dict]:
    rows = db.query(LoopTestTemplate).order_by(LoopTestTemplate.name).all()
    return [{"id": f"saved:{r.id}", "db_id": r.id, "name": r.name, "description": r.description or "",
             "loop_type": r.loop_type, "builtin": False, "created_by": r.created_by,
             "config": json.loads(r.config_json)} for r in rows]


def save_template(db: Session, user: str, name: str, description: str, config: dict) -> dict:
    lt = _lt()
    name = (name or "").strip()
    if not name:
        raise LoopTestError("Give the template a name.")
    cfg = copy.deepcopy(config)
    if cfg.get("loop_type") not in lt.library.LOOP_TYPES:
        raise LoopTestError("The configuration has no valid loop type.")
    for key in ("tag_no", "loop_number", "project_id", "overrides"):      # a template carries structure, not one tag's data
        cfg[key] = "" if key != "overrides" else {}
    for s in cfg.get("signals", []):
        s["io_index"] = None if len(cfg["signals"]) > 1 else s.get("io_index")
    existing = db.query(LoopTestTemplate).filter(LoopTestTemplate.name == name).first()
    row = existing or LoopTestTemplate(name=name, loop_type=cfg["loop_type"], created_by=user, config_json="{}")
    row.description, row.loop_type, row.config_json = description, cfg["loop_type"], json.dumps(cfg)
    db.add(row)
    db.commit()
    return {"id": f"saved:{row.id}", "name": row.name, "updated": existing is not None}


def delete_template(db: Session, template_id: int) -> bool:
    row = db.get(LoopTestTemplate, template_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def apply_template(db: Session, template_id: str, session_id: str, user_id: int, tag: str) -> dict:
    """A copy of a template's structure bound to one tag. Template defaults are suggestions the engineer edits."""
    lt = _lt()
    state = _load_state(session_id, user_id)
    entry = _entry(session_id, state, tag)
    if template_id in lt.library.BUILTIN_TEMPLATES:
        t = lt.library.BUILTIN_TEMPLATES[template_id]
        cfg = default_config(session_id, user_id, tag, t["loop_type"], t["params"], [], template_id)
        return cfg
    if template_id.startswith("saved:"):
        row = db.get(LoopTestTemplate, int(template_id.split(":", 1)[1]))
        if not row:
            raise LoopTestError("Template not found.")
        cfg = json.loads(row.config_json)
        cfg.update(tag_no=tag, loop_number=entry["loop"], project_id=state["project_id"], template_id=template_id)
        if len(entry["io_idx"]) == 1:
            for s in cfg.get("signals", []):
                s["io_index"] = 0
        return lt.library.reconcile_links(cfg)
    raise LoopTestError("Unknown template.")


def clone_config(session_id: str, user_id: int, config: dict, tag: str) -> dict:
    """The structure of one loop design bound to another tag (own loop number, own I/O rows, no carried-over overrides)."""
    lt = _lt()
    state = _load_state(session_id, user_id)
    entry = _entry(session_id, state, tag)
    cfg = copy.deepcopy(config)
    cfg.update(tag_no=tag, loop_number=entry["loop"], project_id=state["project_id"], overrides={})
    n_io = len(entry["io_idx"])
    signals = cfg.get("signals", [])
    for i, sig in enumerate(signals):
        if len(signals) == 1 and n_io == 1:
            sig["io_index"] = 0
        elif n_io == len(signals):                   # same number of I/O rows as signals: keep the engineer's order
            sig["io_index"] = i
        else:
            sig["io_index"] = None                   # never guess a channel allocation - validation will flag it
    return lt.library.reconcile_links(cfg)
