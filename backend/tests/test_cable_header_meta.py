"""Cable Schedule header metadata: what the linked cover holds, what is unresolved, and how the user's confirmed values are accepted."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import cable_header_meta as M  # noqa: E402
from cable_header_helpers import make_cover  # noqa: E402


def read(**kw):
    return M.read_cover_header(make_cover(**kw))


def test_complete_cover_gives_every_field_but_the_location():
    c = read()
    assert c.available
    assert c.values == {"project": "SETTING UP OF A POND, ZLD PLANT", "client": "GAIL (INDIA) LTD", "doc_no": "10P195-I0010-201", "pmc": "PDIL",
                        "date": "24-11-2026", "location": "", "revision": "02"}
    assert list(c.problems) == ["location"] and c.problems["location"][0] == "missing"


def test_document_number_is_project_code_serial_without_the_job_number():
    assert read().values["doc_no"] == "10P195-I0010-201"
    assert "PC286" not in read().values["doc_no"]


def test_date_and_revision_come_from_the_latest_revision_not_from_the_clock():
    c = read()
    assert (c.values["revision"], c.values["date"]) == ("02", "24-11-2026")
    assert [r["rev"] for r in c.revisions] == ["02", "01", "00"]


@pytest.mark.parametrize("rev", ["00", "01", "A", "B2"])
def test_revision_identifiers_are_kept_exactly(rev):
    revs = [{"rev_no": rev, "date": "05-06-2026", "description": "x", "prepared_by": "a", "checked_by": "b", "approved_by": "c"}]
    c = read(revs=revs)
    assert c.values["revision"] == rev and c.values["date"] == "05-06-2026" and "revision" not in c.problems


def test_missing_pmc_is_reported_and_nothing_else():
    c = read(pmc="")
    assert c.problems["pmc"][0] == "missing" and "client" not in c.problems and "project" not in c.problems


def test_missing_revision_date_is_reported_for_the_date_only():
    revs = [{"rev_no": "01", "date": "", "description": "x", "prepared_by": "a", "checked_by": "b", "approved_by": "c"}]
    c = read(revs=revs)
    assert c.problems["date"][0] == "missing" and "revision" not in c.problems and c.values["revision"] == "01"


def test_an_invalid_revision_date_is_reported_as_invalid():
    revs = [{"rev_no": "01", "date": "31-02-2026", "description": "x", "prepared_by": "a", "checked_by": "b", "approved_by": "c"}]
    assert read(revs=revs).problems["date"][0] == "invalid"


def test_revision_missing_from_the_table_is_a_conflict_for_review():
    def edit(ws):
        ws["N4"] = "07"                                        # the cover strip says Rev. 07, the revision table has 00-02
    c = M.read_cover_header(make_cover(edit=edit))
    assert c.problems["revision"][0] == "conflict" and c.problems["date"][0] == "conflict"
    assert "07" in c.problems["revision"][1]


def test_a_stale_current_revision_against_a_newer_table_entry_is_a_conflict():
    def edit(ws):
        ws["N4"] = "01"                                        # table lists 02 as the newest
    c = M.read_cover_header(make_cover(edit=edit))
    assert c.problems["revision"][0] == "conflict" and "02" in c.problems["revision"][1]


def test_without_a_cover_every_field_is_missing():
    c = M.read_cover_header(None)
    assert not c.available and set(c.problems) == set(M.KEYS) and all(k == "missing" for k, _ in c.problems.values())


@pytest.mark.parametrize("value", ["", "   ", "XXXX", "xxx", "TBA", "TBD", "tbc", "-", "?", "[Confirm project name]", "(Confirm Client)",
                                   "(confirm document No.)", "[confirm Revision ]", "To be confirmed", "10P195-XXXX-201", "<project>", "Enter name"])
def test_placeholders_are_unresolved(value):
    assert M.is_unresolved(value)


@pytest.mark.parametrize("value", ["N/A", "n/a", "NA", "Not applicable", "GAIL (INDIA) LTD", "00", "A", "10P195-I0010-201", "24-11-2026", "Gujarat, India"])
def test_real_values_and_a_confirmed_na_are_not_unresolved(value):
    assert not M.is_unresolved(value)


def test_unresolved_cover_values_become_missing_fields():
    c = read(client="XXXX", pmc="TBA")
    assert c.problems["client"][0] == "missing" and c.problems["pmc"][0] == "missing"


# ── resolution ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_only_the_missing_fields_are_requested():
    res = M.resolve(read(pmc="", ), None)
    assert not res.complete
    assert [f.key for f in res.unresolved] == ["pmc", "location"]
    assert all(f.source == "cover" for f in res.fields if f.status == "ok")


def test_confirmed_input_completes_the_header_and_is_tagged_manual():
    res = M.resolve(read(), {"location": "Gujarat, India"})
    assert res.complete and res.values["location"] == "Gujarat, India"
    assert {f.key: f.source for f in res.fields}["location"] == "manual"
    assert res.values["date"] == "24-11-2026" and res.values["revision"] == "02"


def test_pmc_can_be_confirmed_as_not_applicable_but_nothing_else_can():
    res = M.resolve(read(pmc=""), {"pmc": "na", "location": "X Site"})
    assert res.complete and res.values["pmc"] == "N/A"
    res = M.resolve(read(client=""), {"client": "N/A", "location": "X Site"})
    assert not res.complete and [f for f in res.fields if f.key == "client"][0].status == "invalid"


def test_placeholder_and_blank_input_is_refused():
    res = M.resolve(read(), {"location": "TBD"})
    f = [f for f in res.fields if f.key == "location"][0]
    assert f.status == "invalid" and not res.complete
    assert M.resolve(read(), {"location": "   "}).unresolved[0].status == "missing"


def test_manual_date_is_validated_and_written_day_first():
    revs = [{"rev_no": "01", "date": "", "description": "x", "prepared_by": "a", "checked_by": "b", "approved_by": "c"}]
    c = read(revs=revs)
    assert M.resolve(c, {"date": "2026-11-24", "location": "L"}).values["date"] == "24-11-2026"
    assert M.resolve(c, {"date": "24.11.2026", "location": "L"}).values["date"] == "24-11-2026"
    bad = M.resolve(c, {"date": "2026-13-45", "location": "L"})
    assert not bad.complete and [f for f in bad.fields if f.key == "date"][0].status == "invalid"


def test_the_cover_is_authoritative_for_a_field_it_holds_validly():
    res = M.resolve(read(), {"client": "SOMEONE ELSE", "location": "L"})
    assert res.values["client"] == "GAIL (INDIA) LTD" and res.ignored == ["client"]


def test_a_conflict_needs_an_explicit_confirmation():
    def edit(ws):
        ws["N4"] = "07"
    c = M.read_cover_header(make_cover(edit=edit))
    assert not M.resolve(c, {"location": "L"}).complete
    ok = M.resolve(c, {"location": "L", "revision": "02", "date": "24-11-2026"})
    assert ok.complete and ok.values["revision"] == "02"


def test_the_fingerprint_follows_the_cover_not_the_input():
    a, b = read(), read(client="OTHER CLIENT")
    assert a.fingerprint() != b.fingerprint() and a.fingerprint() == read().fingerprint()
    assert M.resolve(a, {"location": "L"}).fingerprint == a.fingerprint()


def test_too_long_input_is_refused():
    assert M.resolve(read(), {"location": "x" * 500}).unresolved[0].status == "invalid"


def test_a_single_revision_cover_with_the_engines_leftover_sample_row_is_reported_not_guessed():
    """The Cover Sheet engine leaves its template's sample revision row (1 / 04.02.2026) when only one revision is written."""
    revs = [{"rev_no": "01", "date": "05-06-2026", "description": "x", "prepared_by": "a", "checked_by": "b", "approved_by": "c"}]
    c = M.read_cover_header(make_cover(revs=revs, raw=True))
    assert c.problems["date"][0] == "conflict" and c.values["date"] == ""
    assert "04.02.2026" in c.suggestions["date"] and "05-06-2026" in c.suggestions["date"]
    blank = [{"rev_no": "01", "date": "", "description": "x", "prepared_by": "a", "checked_by": "b", "approved_by": "c"}]
    assert M.read_cover_header(make_cover(revs=blank, raw=True)).problems["date"][0] == "conflict"      # the stale date is never used silently
