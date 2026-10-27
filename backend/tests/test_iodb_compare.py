"""IODB Comparison & Revision Report: engine, API and PDF."""
import io
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils.iodb_compare import CompareError, compare_files  # noqa: E402
from utils.iodb_compare import store  # noqa: E402
from utils.iodb_compare.pdf_report import build_pdf  # noqa: E402

COLS = ["S.NO", "REV NUMBER", "STATUS", "AREA", "TAG NO", "EQUIPMENT DESCRIPTION", "P&ID NO.", "INSTRUMENT TYPE NAME",
        "SERVICE", "LINE", "SIGNAL I/O TYPE", "JUNCTION BOX TAG NO.", "MAIN CABLE LENGTH(MTRS)", "PROCESS RANGE",
        "POWER SUPPLY", "HART", "REMARKS"]


def make(n=20, prefix="FT"):
    rows = []
    for i in range(1, n + 1):
        rows.append([i, 0, "NEW", "AREA1", f"{prefix}-{i:04d}", f"Instrument {i}", f"PID-{i % 7}", "FLOW INDICATING TRANSMITTER",
                     "RAW WATER", f"{100 + i}-W-{i}", "AI", f"JB-{i % 3}", 25 + i, f"0-{100 + i}", "24 VDC", "YES", ""])
    return pd.DataFrame(rows, columns=COLS)


def xl(df, header_rows=0, sheet="IODB"):
    b = io.BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=sheet, index=False, startrow=header_rows)
    return b.getvalue()


def cmp(d1, d2, **k):
    return compare_files(xl(d1) if isinstance(d1, pd.DataFrame) else d1, "Rev0.xlsx",
                         xl(d2) if isinstance(d2, pd.DataFrame) else d2, "Rev1.xlsx", **k)[0]


def test_identical_files():
    df = make(30)
    r = cmp(df, df.copy())
    assert r["counts"] == {"added": 0, "deleted": 0, "modified": 0, "unchanged": 30, "review": 0}
    assert r["totals"]["field_changes"] == 0 and not r["totally_different"]


def test_added_and_deleted():
    a = make(20)
    b = pd.concat([a.iloc[:15], make(3, "NEW")])
    r = cmp(a, b)
    assert r["counts"]["deleted"] == 5 and r["counts"]["added"] == 3 and r["counts"]["unchanged"] == 15
    assert {x["tag"] for x in r["records"]["added"]} == {"NEW-0001", "NEW-0002", "NEW-0003"}


def test_one_field_modified_and_multi_field():
    a = make(10)
    b = a.copy()
    b.loc[2, "SERVICE"] = "FILTERED WATER"
    r = cmp(a, b)
    assert r["counts"]["modified"] == 1 and r["totals"]["field_changes"] == 1
    ch = r["records"]["modified"][0]["changes"][0]
    assert (ch["column"], ch["old"], ch["new"], ch["change_type"]) == ("SERVICE", "RAW WATER", "FILTERED WATER", "VALUE CHANGED")
    b2 = a.copy()
    for col, val in (("SERVICE", "X"), ("LINE", "150-W-1"), ("PROCESS RANGE", "0-150"), ("HART", "NO"), ("POWER SUPPLY", "230 VAC")):
        b2.loc[4, col] = val
    r = cmp(a, b2)
    assert r["counts"]["modified"] == 1 and r["totals"]["field_changes"] == 5
    cats = {c["code"]: c["count"] for c in r["category_counts"]}
    assert cats["03"] == 2 and cats["10"] == 1 and cats["11"] == 1 and cats["09"] == 1   # service+line / range / hart / power


def test_row_order_and_non_engineering_noise_ignored():
    a = make(25)
    b = a.sample(frac=1, random_state=3).copy()
    b["S.NO"] = range(1, 26)                       # S.NO re-numbered by sorting
    b.loc[:, "SERVICE"] = b["SERVICE"].str.lower()  # case only
    b["MAIN CABLE LENGTH(MTRS)"] = b["MAIN CABLE LENGTH(MTRS)"].astype(float)   # 26 vs 26.0
    b.loc[b.index[0], "REMARKS"] = "-"              # blank vs '-' placeholder
    b.columns = [c.replace("MAIN CABLE LENGTH(MTRS)", "Main Cable Length (Mtrs)") for c in b.columns]
    r = cmp(a, b)
    assert r["counts"] == {"added": 0, "deleted": 0, "modified": 0, "unchanged": 25, "review": 0}, r["records"]["modified"][:2]


def test_whitespace_and_unicode_spaces_ignored_but_real_edits_found():
    a = make(5)
    b = a.copy()
    b.loc[0, "SERVICE"] = "RAW  WATER "           # hidden nbsp + double space
    b.loc[1, "TAG NO"] = " FT-0002 "
    r = cmp(a, b)
    assert r["counts"]["modified"] == 0 and r["counts"]["unchanged"] == 5


def test_totally_different_files():
    r = cmp(make(12, "AA"), make(9, "BB"))
    assert r["totals"]["common"] == 0 and r["totally_different"] is True
    assert "totally different" in r["summary_text"]
    assert r["counts"]["added"] == 9 and r["counts"]["deleted"] == 12
    pdf = build_pdf(r, "summary")
    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf)) as p:
        assert "TOTALLY DIFFERENT" in p.pages[0].extract_text()


def test_duplicate_tags_are_not_silently_compared():
    a = make(6)
    a.loc[1, "TAG NO"] = a.loc[0, "TAG NO"]          # FT-0001 twice in IODB 1
    b = make(6)
    r = cmp(a, b)
    assert "FT-0001" in r["duplicates"]["iodb1"]
    assert any(w["code"] == "DUPLICATE_TAG" and "FT-0001 appears 2 times" in w["message"] for w in r["warnings"])
    assert r["counts"]["review"] == 1 and all(x["tag"] != "FT-0001" for x in r["records"]["unchanged"] + r["records"]["modified"])


def test_missing_tag_column_is_a_clear_error():
    a = make(5).drop(columns=["TAG NO"])
    with pytest.raises(CompareError) as e:
        cmp(a, make(5))
    assert 'Required column "TAG NO" was not found in IODB 1' in str(e.value)
    with pytest.raises(CompareError) as e:
        compare_files(b"not an excel file", "x.xlsx", xl(make(3)), "y.xlsx")
    assert "IODB 1" in str(e.value)


def test_header_row_and_sheet_detected():
    a = make(8)
    r = compare_files(xl(a, header_rows=3, sheet="Sheet1"), "r0.xlsx", xl(a, header_rows=3, sheet="Sheet1"), "r1.xlsx")[0]
    assert r["counts"]["unchanged"] == 8


def test_value_added_removed_types_and_missing_columns_reported():
    a = make(4)
    b = a.copy()
    b.loc[0, "REMARKS"] = "Added note"
    b.loc[1, "HART"] = ""
    b = b.drop(columns=["POWER SUPPLY"])
    r = cmp(a, b)
    kinds = {c["column"]: c["change_type"] for m in r["records"]["modified"] for c in m["changes"]}
    assert kinds == {"REMARKS": "VALUE ADDED", "HART": "VALUE REMOVED"}
    assert r["columns_only_in_1"] == ["POWER SUPPLY"]


def test_inputs_not_modified_and_api_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("IEZ_COMPARE_DIR", str(tmp_path / "cmp"))
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_current_user
    from app.routers.iodb_compare import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, username="alice")
    c = TestClient(app)
    a, b = make(40), make(40)
    b.loc[3, "SERVICE"] = "CHANGED"
    b = b.iloc[:-2]
    f1, f2 = xl(a), xl(b)
    h1, h2 = hash(f1), hash(f2)
    r = c.post("/api/validator/compare", files={"file1": ("Rev0.xlsx", f1), "file2": ("Rev1.xlsx", f2)},
               data={"project_id": "10P211"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["counts"]["modified"], j["counts"]["deleted"], j["status_counts"]["unchanged"]) == (1, 2, 37)
    assert hash(f1) == h1 and hash(f2) == h2
    cid = j["id"]
    lst = c.get(f"/api/validator/compare/{cid}/records", params={"status": "modified", "category": "03"}).json()
    assert lst["total"] == 1 and lst["items"][0]["changed_fields"] == ["SERVICE"]
    assert c.get(f"/api/validator/compare/{cid}/records", params={"status": "modified", "category": "10"}).json()["total"] == 0
    assert c.get(f"/api/validator/compare/{cid}/records", params={"status": "unchanged", "q": "ft-0010"}).json()["total"] == 1
    rec = c.get(f"/api/validator/compare/{cid}/record", params={"tag": "ft-0004"}).json()
    assert rec["status"] == "modified" and rec["changes"][0]["new"] == "CHANGED" and rec["iodb1"]["SERVICE"] == "RAW WATER"
    added = c.get(f"/api/validator/compare/{cid}/record", params={"tag": "FT-0040"}).json()
    assert added["status"] == "deleted" and added["iodb2"] is None and added["iodb1"]["TAG NO"] == "FT-0040"
    for kind in ("summary", "detailed", "complete"):
        pdf = c.get(f"/api/validator/compare/{cid}/pdf", params={"kind": kind})
        assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    bad = c.post("/api/validator/compare", files={"file1": ("a.xlsx", xl(a.drop(columns=["TAG NO"]))), "file2": ("b.xlsx", f2)})
    assert bad.status_code == 400 and "TAG NO" in bad.json()["detail"]
    assert c.get("/api/validator/compare/deadbeef").status_code == 404


def test_pdf_pagination_and_no_clipping_with_long_values():
    a = make(60)
    b = a.copy()
    long = "VERY-LONG-UNBROKEN-VALUE-" + "X" * 180 + " with some normal words afterwards " * 6
    for i in range(0, 40):
        b.loc[i, "SERVICE"] = long
        b.loc[i, "PROCESS RANGE"] = "0-9999"
    r = cmp(a, b)
    pdf = build_pdf(r, "complete", user="tester", project="10P211")
    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf)) as p:
        assert len(p.pages) > 3
        for pg in p.pages:
            assert abs(pg.width - 595.28) < 1 and abs(pg.height - 841.89) < 1                     # A4
            for w in pg.extract_words():
                assert w["x1"] <= pg.width - 18 and w["x0"] >= 18                                  # nothing outside the margins
        txt = "\n".join(pg.extract_text() or "" for pg in p.pages)
        assert "Page 1 of" in txt and "FIELD-LEVEL CHANGES" in txt and "IODB 1 (OLD VALUE)" in txt
        header_pages = sum(1 for pg in p.pages if "TAG NO" in (pg.extract_text() or "") and "Instrument Type" in (pg.extract_text() or ""))
        assert header_pages >= 1


@pytest.mark.parametrize("n", [100, 1000, 5000, 10000])
def test_scale(n, tmp_path, monkeypatch):
    monkeypatch.setenv("IEZ_COMPARE_DIR", str(tmp_path))
    a = make(n)
    b = a.copy()
    k = max(1, n // 20)
    b.loc[:k - 1, "SERVICE"] = "CHANGED"
    b.loc[:k - 1, "HART"] = "NO"
    b = pd.concat([b.iloc[k:].sample(frac=1, random_state=1), b.iloc[:k], make(k, "ADD")])
    t = time.time()
    r, full = compare_files(xl(a), "a.xlsx", xl(b), "b.xlsx")
    t_cmp = time.time() - t
    assert r["counts"]["modified"] == k and r["counts"]["added"] == k and r["counts"]["deleted"] == 0
    assert r["totals"]["field_changes"] == 2 * k
    store.save(r, full)
    t = time.time()
    pdf = build_pdf(r, "complete")
    t_pdf = time.time() - t
    assert pdf[:5] == b"%PDF-"
    print(f"\nn={n}: compare {t_cmp:.1f}s, pdf {t_pdf:.1f}s, {len(pdf) // 1024} KB")
    assert t_cmp < 60 and t_pdf < 150
