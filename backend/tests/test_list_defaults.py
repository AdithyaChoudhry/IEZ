"""
Default (preselected) columns and default filters for the Instrument List and I/O List
generators. Defaults are an initial state only: the user's final selection is what generates.
"""
import io
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_current_user
from app.routers.instrument_list import router as instrument_router
from app.routers.io_list import router as io_router
from utils.generators import generate_instrument_list, generate_io_list
from utils.list_defaults import (BLANK_TOKEN, DEFAULT_COLUMNS, build_list_defaults, match_columns, norm_key,
                                 unique_values_with_blank)

ROOT = Path(__file__).resolve().parents[2]
DJB = ROOT / "DJB_IODB.xlsx"
OLD = ROOT / "IODB.xlsx"


def frame():
    """IODB-like frame with the awkward header spellings of real IODBs and messy values."""
    return pd.DataFrame({
        "S.NO": range(1, 11),
        "TAG NO": [f"T-{i}" for i in range(1, 11)],
        "AREA\nCLASSIFICATION": ["SAFE"] * 10,
        "INSTRUMENT MEASURING  TYPE": ["LEVEL"] * 10,
        "2 WIRE / \n4 WIRE": ["2 WIRE"] * 10,
        " INST RANGE": ["0-10"] * 10,
        "SIGNAL I/O TYPE": ["AI", "ao ", " DI", "DO", "SOFT ", "soft io", "-", "PI", None, "AI"],
        "SUB SYSTEM": ["-", "MCC", "mcc ", " VFD", "vendor plc", "VENDOR  PLC", "PLC", None, "", "-"],
        "REMARKS": [""] * 10,
    })


# ── column matching ─────────────────────────────────────────────────────────
def test_defaults_match_awkward_headers_and_keep_the_original_header_text():
    d = build_list_defaults("instrument_list", frame())
    assert d["columns"][:3] == ["S.NO", "AREA\nCLASSIFICATION", "TAG NO"]       # spec order; original header text kept
    assert "INSTRUMENT MEASURING  TYPE" in d["columns"] and "2 WIRE / \n4 WIRE" in d["columns"]
    assert " INST RANGE" in d["columns"]


def test_default_column_order_follows_the_specification_not_the_iodb():
    cols = ["REMARKS", "TAG NO", "S.NO", "LOCATION"]
    matched, missing, _ = match_columns(DEFAULT_COLUMNS["instrument_list"], cols)
    assert matched == ["S.NO", "LOCATION", "TAG NO", "REMARKS"]


def test_missing_default_columns_warn_and_nothing_is_substituted():
    d = build_list_defaults("io_list", frame())
    assert "PROCESS RANGE" in d["missing_columns"]
    assert "Default column not found in uploaded IODB: PROCESS RANGE" in d["warnings"]
    assert not any("PROCESS" in c for c in d["columns"])
    assert all(c in frame().columns for c in d["columns"])


def test_no_fuzzy_matching_between_different_columns():
    matched, missing, _ = match_columns(["TAG NO", "AREA"], ["TAG", "AREA CLASSIFICATION", "AREAS"])
    assert matched == [] and missing == ["TAG NO", "AREA"]


def test_default_lists_have_the_specified_sizes_and_endpoints():
    assert len(DEFAULT_COLUMNS["instrument_list"]) == 33 and len(DEFAULT_COLUMNS["io_list"]) == 31
    assert DEFAULT_COLUMNS["instrument_list"][0] == "S.NO" and DEFAULT_COLUMNS["instrument_list"][-1] == "REMARKS"
    assert "LINE MOC" in DEFAULT_COLUMNS["instrument_list"] and "LINE MOC" not in DEFAULT_COLUMNS["io_list"]
    assert DEFAULT_COLUMNS["io_list"][-3:] == ["REDUNDANT I O", "CONTACT DETAILS", "REMARKS"]


# ── default filters ─────────────────────────────────────────────────────────
def test_instrument_signal_type_selects_only_ai_ao_di_do_after_trim_and_case_normalisation():
    f = build_list_defaults("instrument_list", frame())["filters"]["SIGNAL I/O TYPE"]
    assert sorted(f) == sorted(["AI", "ao ", " DI", "DO"])           # raw spellings kept, not rewritten
    summary = next(s for s in build_list_defaults("instrument_list", frame())["filter_summary"]
                   if s["column"] == "SIGNAL I/O TYPE")
    assert {"SOFT ", "soft io", "-", "PI", BLANK_TOKEN} <= set(summary["deselected"])


def test_instrument_sub_system_excludes_mcc_vfd_vendor_plc_variants_but_keeps_everything_else():
    f = build_list_defaults("instrument_list", frame())["filters"]["SUB SYSTEM"]
    assert sorted(f) == sorted(["-", "PLC", BLANK_TOKEN])
    for variant in ("MCC", "mcc ", " VFD", "vendor plc", "VENDOR  PLC"):
        assert variant not in f


def test_io_list_excludes_only_dash_and_keeps_other_values_and_blanks():
    f = build_list_defaults("io_list", frame())["filters"]["SIGNAL I/O TYPE"]
    assert "-" not in f and BLANK_TOKEN in f
    assert {"AI", "ao ", " DI", "DO", "SOFT ", "soft io", "PI"} <= set(f)       # nothing hard-coded: PI kept
    df = frame(); df["SIGNAL I/O TYPE"] = ["AI", " - ", "-"] + ["DI"] * 7
    assert " - " not in build_list_defaults("io_list", df)["filters"]["SIGNAL I/O TYPE"]


def test_filter_options_offer_a_blank_choice_only_where_blanks_exist():
    u = unique_values_with_blank(frame())
    assert BLANK_TOKEN in u["SUB SYSTEM"] and BLANK_TOKEN in u["SIGNAL I/O TYPE"]
    assert BLANK_TOKEN not in u["TAG NO"]


def test_missing_filter_column_is_a_warning_not_a_crash():
    d = build_list_defaults("instrument_list", frame().drop(columns=["SUB SYSTEM"]))
    assert "SUB SYSTEM" not in d["filters"] and "SIGNAL I/O TYPE" in d["filters"]
    assert any("Default filter column not found" in w and "SUB SYSTEM" in w for w in d["warnings"])


def test_filter_that_would_deselect_everything_is_not_applied():
    df = frame(); df["SIGNAL I/O TYPE"] = ["SOFT"] * 10
    d = build_list_defaults("instrument_list", df)
    assert "SIGNAL I/O TYPE" not in d["filters"] and any("not applied" in w for w in d["warnings"])


# ── generation honours the user's final selection ───────────────────────────
def output_rows(out_bytes):
    ws = openpyxl.load_workbook(io.BytesIO(out_bytes)).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    return rows[0], rows[1:]


def test_generation_with_defaults_filters_rows_and_keeps_order():
    df = frame()
    d = build_list_defaults("instrument_list", df)
    out, _, err = generate_instrument_list(df, ["TAG NO", "S.NO", "SIGNAL I/O TYPE", "SUB SYSTEM"], d["filters"])
    header, rows = output_rows(out)
    assert err is None and header == ["TAG NO", "S.NO", "SIGNAL I/O TYPE", "SUB SYSTEM"]      # selected order kept
    assert [r[0] for r in rows] == ["T-1", "T-10"]                                             # AI + sub system '-'


def test_user_can_include_soft_and_everything_else_follows_the_users_choice():
    df = frame()
    f = dict(build_list_defaults("instrument_list", df)["filters"])
    f["SIGNAL I/O TYPE"] = f["SIGNAL I/O TYPE"] + ["SOFT "]                    # user ticks SOFT
    f["SUB SYSTEM"] = f["SUB SYSTEM"] + ["MCC", "mcc ", " VFD"]                # and MCC / VFD
    out, _, _ = generate_instrument_list(df, ["TAG NO"], f)
    tags = [r[0] for r in output_rows(out)[1]]
    assert tags == ["T-1", "T-2", "T-3", "T-4", "T-10"]                         # T-5 is SOFT but its sub system (vendor plc) is still off
    f["SIGNAL I/O TYPE"] = f["SIGNAL I/O TYPE"]
    f["SUB SYSTEM"] = f["SUB SYSTEM"] + ["vendor plc"]
    tags = [r[0] for r in output_rows(generate_instrument_list(df, ["TAG NO"], f)[0])[1]]
    assert tags == ["T-1", "T-2", "T-3", "T-4", "T-5", "T-10"]                  # SOFT row now included


def test_clearing_filters_returns_every_row():
    df = frame()
    out, _, _ = generate_instrument_list(df, ["TAG NO"], {})
    assert len(output_rows(out)[1]) == 10
    out, _, _ = generate_io_list(df, ["TAG NO"], None)
    assert len(output_rows(out)[1]) == 10


def test_blank_rows_are_kept_for_all_except_rules_and_never_dropped_silently():
    df = frame()
    f = build_list_defaults("io_list", df)["filters"]                            # excludes only '-'
    tags = [r[0] for r in output_rows(generate_io_list(df, ["TAG NO"], f)[0])[1]]
    assert "T-7" not in tags and "T-9" in tags                                   # '-' out, blank row (None) stays
    assert len(tags) == 9


def test_io_list_user_can_include_dash_or_drop_soft():
    df = frame()
    f = dict(build_list_defaults("io_list", df)["filters"])
    f["SIGNAL I/O TYPE"] = f["SIGNAL I/O TYPE"] + ["-"]
    assert len(output_rows(generate_io_list(df, ["TAG NO"], f)[0])[1]) == 10
    f["SIGNAL I/O TYPE"] = [v for v in f["SIGNAL I/O TYPE"] if norm_key(v) != "soft"]
    assert "T-5" not in [r[0] for r in output_rows(generate_io_list(df, ["TAG NO"], f)[0])[1]]


def test_filter_on_a_column_that_is_not_in_the_output_still_applies():
    df = frame()
    f = build_list_defaults("instrument_list", df)["filters"]
    tags = [r[0] for r in output_rows(generate_instrument_list(df, ["TAG NO"], f)[0])[1]]
    assert tags == ["T-1", "T-10"]                                               # SUB SYSTEM not output, rule still honoured


def test_legacy_filters_without_the_blank_token_behave_as_before():
    df = frame()
    out, _, _ = generate_instrument_list(df, ["TAG NO"], {"SUB SYSTEM": ["-"]})
    assert [r[0] for r in output_rows(out)[1]] == ["T-1", "T-10"]                 # blanks not matched, as originally


def test_generation_does_not_modify_the_source_frame():
    df = frame()
    before = df.copy(deep=True)
    generate_instrument_list(df, ["TAG NO"], build_list_defaults("instrument_list", df)["filters"])
    pd.testing.assert_frame_equal(df, before)


# ── API ─────────────────────────────────────────────────────────────────────
def xlsx(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="IODB", index=False)
    return buf.getvalue()


@pytest.fixture()
def client():
    app = FastAPI()
    for r in (instrument_router, io_router):
        app.include_router(r, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, username="u", email="e")
    return TestClient(app)


def test_analyze_endpoints_return_defaults_for_their_own_list(client):
    data = xlsx(frame())
    for url, expected_cols in (("instrument-list", 33), ("io-list", 31)):
        r = client.post(f"/api/{url}/analyze", files={"file": ("IODB.xlsx", data)})
        assert r.status_code == 200
        body = r.json()
        assert body["defaults"]["list_type"] == url.replace("-", "_")
        assert BLANK_TOKEN in body["unique_values"]["SUB SYSTEM"]
        assert len(DEFAULT_COLUMNS[body["defaults"]["list_type"]]) == expected_cols
    inst = client.post("/api/instrument-list/analyze", files={"file": ("IODB.xlsx", data)}).json()["defaults"]
    io_ = client.post("/api/io-list/analyze", files={"file": ("IODB.xlsx", data)}).json()["defaults"]
    assert "SUB SYSTEM" in inst["filters"] and "SUB SYSTEM" not in io_["filters"]


def test_generate_endpoint_uses_the_users_filters(client):
    data = xlsx(frame())
    import json
    r = client.post("/api/instrument-list/generate", files={"iodb_file": ("IODB.xlsx", data)},
                    data={"selected_columns": json.dumps(["TAG NO"]),
                          "filters": json.dumps({"SIGNAL I/O TYPE": ["SOFT "], "SUB SYSTEM": [BLANK_TOKEN, "vendor plc"]})})
    assert r.status_code == 200
    d = client.get("/api/instrument-list/download")
    assert [x[0] for x in output_rows(d.content)[1]] == ["T-5"]


# ── real IODBs ──────────────────────────────────────────────────────────────
@pytest.mark.skipif(not DJB.exists(), reason="DJB_IODB.xlsx not in repo")
def test_real_revised_iodb_defaults_and_row_counts(client):
    from utils.file_handler import read_iodb
    raw, _ = read_iodb(io.BytesIO(DJB.read_bytes()))
    for url, n_cols in (("instrument-list", 33), ("io-list", 31)):
        body = client.post(f"/api/{url}/analyze", files={"file": ("DJB_IODB.xlsx", DJB.read_bytes())}).json()
        assert len(body["defaults"]["columns"]) == n_cols and body["defaults"]["missing_columns"] == []
        assert body["defaults"]["columns"][0] == "S.NO"

    sig = raw["SIGNAL I/O TYPE"].astype(str).str.strip().str.upper()
    sub = raw["SUB SYSTEM"].astype(str).str.strip().str.upper().replace({"NAN": ""})
    expected_instr = int(sig.isin(["AI", "AO", "DI", "DO"]).__and__(~sub.isin(["MCC", "VFD", "VENDOR PLC"])).sum())
    expected_io = int((sig != "-").sum())
    import json
    for url, cols_key, expected in (("instrument-list", "instrument_list", expected_instr), ("io-list", "io_list", expected_io)):
        d = client.post(f"/api/{url}/analyze", files={"file": ("DJB_IODB.xlsx", DJB.read_bytes())}).json()["defaults"]
        r = client.post(f"/api/{url}/generate", files={"iodb_file": ("DJB_IODB.xlsx", DJB.read_bytes())},
                        data={"selected_columns": json.dumps(d["columns"]), "filters": json.dumps(d["filters"])})
        assert r.status_code == 200, r.text
        header, rows = output_rows(client.get(f"/api/{url}/download").content)
        assert header == d["columns"] and len(rows) == expected, (url, len(rows), expected)


@pytest.mark.skipif(not OLD.exists(), reason="IODB.xlsx not in repo")
def test_older_iodb_format_warns_about_missing_defaults_without_crashing(client):
    r = client.post("/api/instrument-list/analyze", files={"file": ("IODB.xlsx", OLD.read_bytes())})
    assert r.status_code == 200
    d = r.json()["defaults"]
    assert 0 < len(d["columns"]) < 33 and d["missing_columns"]
    assert any(w.startswith("Default column not found in uploaded IODB:") for w in d["warnings"])
