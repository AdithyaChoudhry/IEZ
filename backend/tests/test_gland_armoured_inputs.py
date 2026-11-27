"""Gland Quantity Step 2 no longer asks for bedding / armour dimensions: an armoured cable is then checked on its overall
diameter only and is never reported as a confirmed match."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils import gland_advisor as A  # noqa: E402
from utils import gland_reference as R  # noqa: E402

ROWS = R.builtin()


def _matching(construction):
    """An OD and the preferred gland designation the tables give for it."""
    for od in (8, 10, 12, 14, 16, 18, 20, 24, 28):
        adv = A.advise(A.inputs_from({"od": od, "construction": construction, "standards": ["METRIC"]}), ROWS, A.Project())
        pre = next((r["preferred"] for r in adv["results"] if r["preferred"]), None)
        if pre and not pre["borderline"]:
            return od, pre["thread_options"][0]
    raise AssertionError("no preferred gland found")


def test_armoured_without_dimensions_is_a_preliminary_check_only():
    od, gland = _matching("ARMOURED")
    out = A.compare_cable_type("12PX1.5", [gland], {"od": od, "construction": "ARMOURED"}, ROWS, A.Project())
    assert out["result"] != "MATCH" and "DETAILED COMPATIBILITY INCOMPLETE" in out["flags"]
    assert "incomplete" in out["message"] and out["recommended"]


def test_unarmoured_result_is_unchanged():
    od, gland = _matching("UNARMOURED")
    out = A.compare_cable_type("12PX1.5", [gland], {"od": od, "construction": "UNARMOURED"}, ROWS, A.Project())
    assert out["result"] == "MATCH" and "DETAILED COMPATIBILITY INCOMPLETE" not in out["flags"]
