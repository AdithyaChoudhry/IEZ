"""Templates whose sheets run to row 1,048,576 (formatted rows / a header filled down a column) are trimmed before
openpyxl opens them, without touching the real content."""
import io
import zipfile

import openpyxl

from utils.xlsx_trim import trim_empty_tail


def _book(fill_rows: int, fill_value: bool = True, extra_tail_values: int = 0) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MCC DI"
    ws["A1"] = "TITLE"
    for r in range(3, 20):
        ws.cell(r, 1, r - 2); ws.cell(r, 2, f"TAG-{r}"); ws.cell(r, 3, f"=A{r}&B{r}")
    ws.merge_cells("A1:D1")
    for r in range(20, fill_rows, 2):                                   # header filled down column T, 2-row merges
        if fill_value:
            ws.cell(r, 20, "Cable Length (M)")
        ws.cell(r + 1, 20).border = openpyxl.styles.Border(left=openpyxl.styles.Side(style="thin"))
        ws.merge_cells(start_row=r, start_column=20, end_row=r + 1, end_column=20)
    for i in range(extra_tail_values):
        ws.cell(fill_rows - 5 + i, 5, f"REAL-{i}")
    wb.create_sheet("Small")["A1"] = "x"
    b = io.BytesIO(); wb.save(b)
    return b.getvalue()


def test_filled_down_tail_is_removed_and_data_kept():
    src = _book(12000)
    out = trim_empty_tail(src, min_rows=5000, min_bytes=0)
    assert len(out) < len(src) / 5
    ws = openpyxl.load_workbook(io.BytesIO(out))["MCC DI"]
    assert ws.max_row <= 19 + 50 + 2
    assert [ws.cell(r, 2).value for r in range(3, 20)] == [f"TAG-{r}" for r in range(3, 20)]
    assert ws["C5"].value == "=A5&B5" and "A1:D1" in {str(m) for m in ws.merged_cells.ranges}
    assert all(m.min_row <= ws.max_row for m in ws.merged_cells.ranges)


def test_formatted_only_tail_is_removed():
    out = trim_empty_tail(_book(12000, fill_value=False), min_rows=5000, min_bytes=0)
    assert openpyxl.load_workbook(io.BytesIO(out))["MCC DI"].max_row < 100


def test_real_data_at_the_bottom_is_left_alone():
    src = _book(12000, extra_tail_values=3)
    assert trim_empty_tail(src, min_rows=5000, min_bytes=0) == src


def test_small_or_non_excel_files_are_unchanged():
    small = _book(200)
    assert trim_empty_tail(small) == small
    assert trim_empty_tail(b"not a zip") == b"not a zip"
    with zipfile.ZipFile(io.BytesIO(small)) as z:
        assert "xl/workbook.xml" in z.namelist()
