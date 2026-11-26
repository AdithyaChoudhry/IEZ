"""Test helper: generate a Cable Schedule through the API the way the page does - ask /header-metadata what the cover cannot supply, then send
the user's confirmed values for exactly those fields (the values below are test values, never project data)."""
import json

TEST_VALUES = {"project": "TEST PROJECT NAME", "client": "TEST CLIENT", "doc_no": "10P000-I0010-001", "pmc": "TEST PMC", "date": "01-01-2026",
               "location": "TEST LOCATION", "revision": "0"}


def header_fields(client, data=None, files=None):
    """What /header-metadata says for the same project / cover template as a generate call."""
    d = {k: v for k, v in (data or {}).items() if k == "project_id"}
    f = {k: v for k, v in (files or {}).items() if k == "cover_template_file"}
    r = client.post("/api/cable-schedule/header-metadata", data=d, files=f or None)
    assert r.status_code == 200, r.text
    return r.json()


def generate(client, files, data=None, values=None):
    data = dict(data or {})
    meta = header_fields(client, data, files)
    vals = {**TEST_VALUES, **(values or {})}
    overrides = {f["key"]: vals[f["key"]] for f in meta["fields"] if f["status"] != "ok"}
    if overrides:
        data["header_overrides"] = json.dumps(overrides)
        data["header_fingerprint"] = meta["fingerprint"]
    return client.post("/api/cable-schedule/generate", files=files, data=data)


# ── covers built by the real Cover Sheet engine ──────────────────────────────────────────────────────────────────────
def make_cover(pmc="PDIL", client="GAIL (INDIA) LTD", project="SETTING UP OF A POND, ZLD PLANT", revs=None, parts=None, edit=None, raw=False) -> bytes:
    """A cover sheet workbook (bytes) from utils.coversheet_generator - the same engine the Cover Sheet Generator uses. `edit(ws)` may change it.
    The engine leaves the template's own sample revision rows (20 and 22) where no revision is written to them; unless `raw`, those leftovers
    are cleared here so the cover is the one a clean engine would produce."""
    import io
    import openpyxl
    from utils.coversheet_generator import generate_cover_sheet
    info = {"project_description": project, "client": client, "pmc": pmc, "contractor": "VA TECH WABAG LIMITED", "unit_no": "200",
            "doc_class": "INFORMATION", "discipline": "INSTRUMENTATION", "page_no": "1 of 12",
            **(parts or {"job_no": "PC286", "project_no": "10P195", "doc_code": "I0010", "serial_no": "201"})}
    revs = revs if revs is not None else [
        {"rev_no": "00", "date": "10-11-2026", "description": "Issued for Review", "prepared_by": "AKB", "checked_by": "AG", "approved_by": "VE"},
        {"rev_no": "01", "date": "18-11-2026", "description": "Issued for Approval", "prepared_by": "AKB", "checked_by": "AG", "approved_by": "VE"},
        {"rev_no": "02", "date": "24-11-2026", "description": "Revised as per Comments", "prepared_by": "AKB", "checked_by": "AG", "approved_by": "VE"}]
    data, _n, err = generate_cover_sheet(info, revs, document_number="PC286-10P195-I0010-201", document_title="INSTRUMENT CABLE SCHEDULE")
    assert err is None, err
    if edit or not raw:
        from utils.coversheet_generator import _REVISION_ROWS
        wb = openpyxl.load_workbook(io.BytesIO(data))
        if not raw:
            ws0 = wb.worksheets[0]
            for row in (r for r in _REVISION_ROWS if r not in _REVISION_ROWS[:len(revs)]):
                for col in "ABCIJKLMNO":
                    cell = ws0[f"{col}{row}"]
                    if type(cell).__name__ != "MergedCell":
                        cell.value = None
        if edit:
            edit(wb.worksheets[0])
        out = io.BytesIO()
        wb.save(out)
        data = out.getvalue()
    return data


def fake_snapshot(cover_bytes, revision="02", project_id="PRJ-1", doc="PC286-10P195-I0010-201"):
    """What cable_cover.snapshot returns for a resolved project cover (the cover workbook is inserted by finalize(snapshot=...))."""
    return {"resolution": {"doc_type": "cable_schedule", "doc_label": "Cable Schedule", "project_id": project_id, "sub_key": "", "status": "AVAILABLE",
                           "record": {"document_number": doc, "document_name": "INSTRUMENT CABLE SCHEDULE"}, "match": "selected", "candidates": [],
                           "revision": revision, "approved": True, "approval": None, "message": "Approved cover sheet."},
            "cover": cover_bytes, "warnings": [], "message": "Approved cover sheet."}


def no_cover_snapshot(project_id=None):
    return {"resolution": {"doc_type": "cable_schedule", "doc_label": "Cable Schedule", "project_id": project_id, "sub_key": "", "status": "NOT_AVAILABLE",
                           "record": None, "match": None, "candidates": [], "revision": None, "approved": False, "approval": None,
                           "message": "Select a project first."}, "cover": None, "warnings": [], "message": "Select a project first."}
