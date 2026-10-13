"""
Tests for the project document registry and its Coversheet links.
Numbered comments map to the acceptance tests in the feature specification.
"""
import json

import pytest

from app.services import document_registry as reg
from conftest import make_iodb, make_xlsx

PID = "10P211"
OTHER = "10P204"
INSTR_PARAMS = {"selected_columns": ["TAG NO", "INSTRUMENT NAME"], "filters": {}}


def register(db, module, project=PID, iodb=None, params=None, **kw):
    kind_loop = module == "loop_wiring"
    if kind_loop:
        kw.setdefault("sheet_count", 4)            # the router supplies the loop count
    return reg.register_generation(
        db, project_id=project, module=module, user="tester",
        source_bytes=iodb if iodb is not None else make_iodb(),
        source_filename="LOOP_INPUT.xlsx" if kind_loop else "IODB.xlsx",
        output_bytes=make_xlsx(4), output_filename=f"{module}.xlsx",
        params=params if params is not None else INSTR_PARAMS, **kw,
    )


def state(db, module, project=PID):
    return reg.module_state(db, project, module)


# ── 1-5: generated documents are detected automatically ─────────────────────
@pytest.mark.parametrize("module", reg.MODULE_ORDER)
def test_each_generator_output_is_detected(db, module):
    doc = register(db, module)
    st = state(db, module)
    assert st["latest"]["id"] == doc.id
    assert st["latest"]["revision_label"] == "R1"
    assert st["latest"]["document_number"] == f"{PID}-INS-{reg.MODULES[module]['serial']:03d}"
    assert st["state"] == "not_connected"      # detected, but not yet linked
    assert st["latest"]["record_count"] == 4   # 4 data rows (header excluded)


def test_all_four_show_correct_revisions(db):
    for m in reg.MODULE_ORDER:
        register(db, m)
    register(db, "io_list")                    # io_list -> R2
    data = reg.overview(db, PID)
    revs = {m["module"]: m["latest"]["revision"] for m in data["modules"]}
    assert revs == {"instrument_list": 1, "io_list": 2, "cable_schedule": 1, "loop_wiring": 1}


def test_document_numbers_are_stable_across_revisions(db):
    a = register(db, "io_list")
    b = register(db, "io_list")
    assert a.document_number == b.document_number and (a.revision, b.revision) == (1, 2)


# ── 6: new IODB revision flags documents generated from the previous one ────
def test_new_iodb_revision_requires_regeneration(db):
    for m in ("instrument_list", "io_list", "cable_schedule"):
        register(db, m)
    reg.connect(db, PID, ["instrument_list", "io_list", "cable_schedule"], "tester")
    assert reg.overview(db, PID)["summary"]["current"] == 3

    sv = reg.ensure_source_version(db, PID, "iodb", "IODB_v2.xlsx", make_iodb(extra_row=True), "tester")
    db.commit()
    assert sv.rev_no == 2
    for m in ("instrument_list", "io_list", "cable_schedule"):
        st = state(db, m)
        assert "regeneration_required" in st["flags"] and st["state"] == "regeneration_required"
    assert reg.overview(db, PID)["summary"]["regeneration_required"] == 3


def test_same_file_does_not_create_a_new_revision(db):
    data = make_iodb()
    a = reg.ensure_source_version(db, PID, "iodb", "a.xlsx", data, "t")
    b = reg.ensure_source_version(db, PID, "iodb", "renamed.xlsx", data, "t")
    assert a.id == b.id and a.rev_no == 1


def test_loop_wiring_compared_against_its_own_source_kind(db):
    register(db, "loop_wiring")
    reg.ensure_source_version(db, PID, "iodb", "IODB_v2.xlsx", make_iodb(extra_row=True), "t")
    db.commit()
    assert "regeneration_required" not in state(db, "loop_wiring")["flags"]


# ── 7: regenerate only one module ───────────────────────────────────────────
def test_regenerate_only_io_list_updates_only_that_revision(db):
    iodb1 = make_iodb()
    register(db, "instrument_list", iodb=iodb1)
    register(db, "io_list", iodb=iodb1)
    reg.connect(db, PID, ["instrument_list", "io_list"], "tester")

    reg.ensure_source_version(db, PID, "iodb", "IODB_v2.xlsx", make_iodb(extra_row=True), "t")
    db.commit()
    io_doc = reg.latest_document(db, PID, "io_list")
    res = reg.regenerate(db, PID, io_doc.id, "tester")

    assert res["ok"] and res["document"]["revision"] == 2
    assert res["document"]["source_rev_no"] == 2
    assert res["document"]["record_count"] == 6          # 5 + the added row
    assert reg.latest_document(db, PID, "instrument_list").revision == 1
    assert state(db, "instrument_list")["state"] == "regeneration_required"
    assert state(db, "io_list")["flags"] == ["new_revision_available"]


# ── Revision synchronisation never silently replaces the link ───────────────
def test_new_revision_does_not_silently_move_the_link(db):
    first = register(db, "instrument_list")
    reg.connect(db, PID, ["instrument_list"], "tester")
    second = register(db, "instrument_list")

    st = state(db, "instrument_list")
    assert st["linked"]["id"] == first.id and st["latest"]["id"] == second.id
    assert st["state"] == "new_revision_available"
    db.refresh(first)
    assert first.status == "SUPERSEDED" and first.superseded_by == second.id

    reg.connect(db, PID, ["instrument_list"], "tester")      # explicit engineer action
    assert state(db, "instrument_list")["linked"]["id"] == second.id
    assert state(db, "instrument_list")["state"] == "current"


# ── 8: disconnect keeps the file ────────────────────────────────────────────
def test_disconnect_keeps_the_generated_file(db):
    doc = register(db, "cable_schedule")
    reg.connect(db, PID, ["cable_schedule"], "tester")
    out = reg.disconnect(db, PID, "cable_schedule", "tester")
    assert out["disconnected"] is True
    st = state(db, "cable_schedule")
    assert st["connected"] is False and st["state"] == "not_connected"
    path, name = reg.document_file(db, PID, doc.id)
    assert path.exists() and name == "cable_schedule.xlsx"
    assert reg.disconnect(db, PID, "cable_schedule", "tester")["disconnected"] is False


# ── 9: failures are visible and never mark the project successful ───────────
def test_failure_is_reported_and_earlier_outputs_survive(db):
    for m in ("instrument_list", "io_list", "loop_wiring"):
        register(db, m)
    good = register(db, "cable_schedule")
    reg.connect(db, PID, list(reg.MODULE_ORDER), "tester")
    assert reg.overview(db, PID)["summary"]["coversheet_ready"] is True

    reg.register_failure(db, project_id=PID, module="cable_schedule", user="tester",
                         error="Template sheet missing", params=INSTR_PARAMS)
    st = state(db, "cable_schedule")
    assert st["state"] == "failed" and "Template sheet missing" in st["last_error"]
    assert reg.latest_document(db, PID, "cable_schedule").id == good.id   # output kept
    summary = reg.overview(db, PID)["summary"]
    assert summary["failed"] == 1 and summary["coversheet_ready"] is False
    path, _ = reg.document_file(db, PID, good.id)
    assert path.exists()


def test_first_ever_failure_is_not_generated_state_failed(db):
    reg.register_failure(db, project_id=PID, module="io_list", user="t", error="bad IODB")
    assert state(db, "io_list")["state"] == "failed"
    assert reg.latest_document(db, PID, "io_list") is None


def test_register_safe_never_raises_and_reports_bad_project(db, monkeypatch, engine):
    from sqlalchemy.orm import sessionmaker
    import app.database as database
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    assert reg.register_safe("success", project_id=None) is None
    res = reg.register_safe("success", project_id="../etc", module="io_list", user="t",
                            source_bytes=b"x", source_filename="a.xlsx",
                            output_bytes=b"y", output_filename="o.xlsx")
    assert res["registered"] is False and "Invalid project id" in res["error"]


# ── 10: projects are isolated ───────────────────────────────────────────────
def test_projects_are_isolated(db):
    register(db, "instrument_list", project=PID)
    reg.connect(db, PID, ["instrument_list"], "t")
    register(db, "loop_wiring", project=OTHER)

    a, b = reg.overview(db, PID), reg.overview(db, OTHER)
    by = lambda d: {m["module"]: m for m in d["modules"]}
    assert by(a)["instrument_list"]["connected"] and by(a)["loop_wiring"]["state"] == "not_generated"
    assert by(b)["instrument_list"]["state"] == "not_generated" and not by(b)["instrument_list"]["connected"]
    assert by(b)["loop_wiring"]["latest"]["document_number"].startswith(OTHER)
    doc_id = reg.latest_document(db, PID, "instrument_list").id
    with pytest.raises(reg.RegistryError):
        reg.document_file(db, OTHER, doc_id)                   # cannot reach A's file through B


# ── 11/12: state persists across sessions ───────────────────────────────────
def test_registry_persists_across_sessions(db, new_session):
    register(db, "io_list")
    register(db, "io_list")
    reg.connect(db, PID, ["io_list"], "tester")
    db.close()

    fresh = new_session()
    try:
        st = reg.module_state(fresh, PID, "io_list")
        assert st["connected"] and st["linked"]["revision"] == 2 and st["state"] == "current"
        assert len(reg.list_documents(fresh, PID, "io_list")) == 2
    finally:
        fresh.close()


# ── Status model & audit ────────────────────────────────────────────────────
def test_status_rules(db):
    old = register(db, "io_list")
    new = register(db, "io_list")
    assert reg.set_status(db, PID, new.id, "under review", "lead")["status"] == "UNDER_REVIEW"
    assert reg.set_status(db, PID, new.id, "APPROVED", "lead")["status"] == "APPROVED"
    with pytest.raises(reg.RegistryError):
        reg.set_status(db, PID, old.id, "APPROVED", "lead")      # superseded
    with pytest.raises(reg.RegistryError):
        reg.set_status(db, PID, new.id, "SUPERSEDED", "lead")    # not a manual status


def test_audit_trail_records_who_what_which_revision(db):
    doc = register(db, "instrument_list")
    reg.connect(db, PID, ["instrument_list"], "alice")
    reg.disconnect(db, PID, "instrument_list", "bob")
    actions = [(a["action"], a["actor"]) for a in reg.audit_trail(db, PID)]
    assert ("generated", "tester") in actions
    assert ("connected", "alice") in actions and ("disconnected", "bob") in actions
    gen = next(a for a in reg.audit_trail(db, PID) if a["action"] == "generated")
    assert gen["document_id"] == doc.id and gen["details"]["source_rev"] == 1


def test_invalid_project_id_rejected(db):
    for bad in ("", "../x", "a b", "x" * 41, "-lead"):
        with pytest.raises(reg.RegistryError):
            reg.normalize_project_id(bad)


# ── Generate connected documents (re-runs the real generators) ──────────────
def test_generate_connected_runs_generators_and_reports_missing_ones(db):
    iodb = make_iodb()
    register(db, "instrument_list", iodb=iodb)
    register(db, "io_list", iodb=iodb)
    reg.ensure_source_version(db, PID, "iodb", "IODB_v2.xlsx", make_iodb(extra_row=True), "t")
    db.commit()

    res = reg.generate_connected(db, PID, ["instrument_list", "io_list", "cable_schedule"], "tester")
    by = {s["step"]: s for s in res["steps"]}
    assert by["iodb_check"]["status"] == "ok"
    assert by["instrument_list"]["status"] == "ok" and by["io_list"]["status"] == "ok"
    assert by["cable_schedule"]["status"] == "needs_input"       # never generated -> no settings
    assert res["all_ok"] is False and res["coversheet_ready"] is False
    assert reg.latest_document(db, PID, "instrument_list").source_rev_no == 2


def test_generate_connected_without_iodb_fails_cleanly(db):
    res = reg.generate_connected(db, PID, ["io_list"], "tester")
    assert res["all_ok"] is False and res["steps"][0]["status"] == "failed"


def test_regenerate_without_stored_settings_is_refused(db):
    doc = register(db, "io_list", params={})
    with pytest.raises(reg.RegistryError):
        reg.regenerate(db, PID, doc.id, "t")


# ── Regressions found while checking against the real sample files ──────────
def test_loop_wiring_needs_only_a_template_to_be_regenerable(db):
    doc = register(db, "loop_wiring", params={}, template_bytes=make_xlsx(), template_filename="LW.xlsx")
    assert reg.doc_to_dict(doc)["can_regenerate"] is True
    bare = register(db, "loop_wiring", params={})
    assert reg.doc_to_dict(bare)["can_regenerate"] is False


def test_failed_run_keeps_template_so_it_can_be_retried(db):
    fail = reg.register_failure(db, project_id=PID, module="cable_schedule", user="t", error="boom",
                                params={"jb_column": "New JB", "tag_column": "TAG NO"},
                                template_bytes=make_xlsx(), template_filename="cable.xlsx")
    assert fail.template_path and reg.has_stored_settings(fail)
