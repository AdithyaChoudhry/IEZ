"""
generators.py
Core generation functions for each of the 5 modules.
All functions return (output_bytes, filename, error_message).
  - output_bytes: bytes of the generated Excel file (or None on error)
  - filename:     suggested download filename  (or None on error)
  - error_message: None on success, string description on failure
"""

import io
import copy
import re
import zipfile
import pandas as pd
import openpyxl
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.styles import Alignment, Font, PatternFill, Border

from utils.file_handler import workbook_to_bytes, dataframe_to_bytes

# Shared cell style applied to all output cells in list generators
_LIST_ALIGNMENT = Alignment(horizontal='center', vertical='center', wrap_text=True)
_LIST_FONT = Font(name='Calibri', size=14)
_HEADER_FONT = Font(name='Calibri', size=14, bold=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Instrument List Generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_instrument_list(
    df: pd.DataFrame,
    selected_columns: list[str],
) -> tuple[bytes | None, str | None, str | None]:
    """
    Extract selected columns from the IODB DataFrame and produce a formatted Excel file.
    Applies Calibri 14pt, center+wrap alignment to all cells, and auto-fits column widths.
    """
    try:
        available = [c for c in selected_columns if c in df.columns]
        if not available:
            return None, None, "None of the selected columns were found in the IODB file."
        result = df[available].copy()
        out_bytes = _build_formatted_list(result, "Sheet1")
        return out_bytes, "Instrument_List.xlsx", None
    except Exception as e:
        return None, None, f"Instrument List generation failed: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. I/O List Generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_io_list(
    df: pd.DataFrame,
    selected_columns: list[str],
) -> tuple[bytes | None, str | None, str | None]:
    """
    Same logic as Instrument List but outputs IO_List.xlsx.
    Applies Calibri 14pt, center+wrap alignment to all cells, and auto-fits column widths.
    """
    try:
        available = [c for c in selected_columns if c in df.columns]
        if not available:
            return None, None, "None of the selected columns were found in the IODB file."
        result = df[available].copy()
        out_bytes = _build_formatted_list(result, "Sheet1")
        return out_bytes, "IO_List.xlsx", None
    except Exception as e:
        return None, None, f"I/O List generation failed: {e}"


def _build_formatted_list(df: pd.DataFrame, sheet_name: str) -> bytes:
    """
    Write a DataFrame to an Excel workbook with:
      - Calibri 14 font on every cell (bold for header row)
      - Center + center + wrap_text alignment on every cell
      - Auto-adjust column width to the longest value in each column
    Returns raw bytes of the xlsx file.
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        wb = writer.book
        ws = wb[sheet_name]

        # Track max width per column for auto-fit
        col_widths: dict[int, int] = {}

        for row_idx, row in enumerate(ws.iter_rows(), start=1):
            is_header = row_idx == 1
            for cell in row:
                cell.alignment = _LIST_ALIGNMENT
                cell.font = _HEADER_FONT if is_header else _LIST_FONT

                # Measure display length (handle multi-line cell values)
                if cell.value is not None:
                    val_str = str(cell.value)
                    # For wrapped text, use longest line
                    line_len = max((len(line) for line in val_str.split('\n')), default=0)
                else:
                    line_len = 0
                col_widths[cell.column] = max(col_widths.get(cell.column, 0), line_len)

        # Apply column widths (cap between 10 and 60 chars)
        for col_idx, width in col_widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max(width + 4, 10), 60)

    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Data Sheet Generator
# ─────────────────────────────────────────────────────────────────────────────

# Values in datasheet value cells that are considered "empty placeholders".
# ONLY these are replaced; anything else ("NA", "VTS", numbers, etc.) is preserved.
_PLACEHOLDER_VALUES = {"refer annexure 1", "refer annexure1", "annexure 1", "", None}


def generate_datasheets(
    df: pd.DataFrame,
    template_wb: openpyxl.Workbook,
    tag_column: str,
    selected_tags: list[str],
    progress_callback=None,
) -> tuple[list[tuple[bytes, str]] | None, str | None]:
    """
    For each selected tag, copy the entire template workbook, then perform
    layout-aware field mapping on the 'Annexure' sheet:

      1. Scan EVERY cell in the sheet.
      2. If the cell text matches an IODB column name (case-insensitive, with
         fuzzy fallback), look rightward in the same row (up to 5 cells).
      3. Write the IODB value into the first rightward cell whose current value
         is a placeholder (None, empty, or "Refer Annexure 1").
      4. Never overwrite formulas, "NA", "VTS", or any other meaningful text.
      5. Write "TBA" when the IODB value is empty/NaN.

    Preserves all formatting, merged cells, and structure — only placeholder
    cells are touched.
    """
    try:
        # ───────────────────────────────────────────────────────────────────────
        # Locate Annexure sheet (case-insensitive, then partial match)
        # ───────────────────────────────────────────────────────────────────────
        ANNEXURE_SHEET = next(
            (s for s in template_wb.sheetnames if s.strip().lower() == "annexure"),
            None,
        )
        # Also accept "Annexure 1- NEW WWTP", "Annexure 1", etc.
        if ANNEXURE_SHEET is None:
            ANNEXURE_SHEET = next(
                (s for s in template_wb.sheetnames if "annexure" in s.strip().lower()),
                None,
            )
        if ANNEXURE_SHEET is None:
            return None, (
                f"Template does not contain a sheet named 'Annexure'. "
                f"Found sheets: {template_wb.sheetnames}"
            )

        if tag_column not in df.columns:
            return None, f"Tag column '{tag_column}' not found in IODB."

        # ───────────────────────────────────────────────────────────────────────
        # Build normalised IODB column index for fast lookup
        # ───────────────────────────────────────────────────────────────────────
        # Map: normalised_col_name -> original column name (preserves case for df access)
        iodb_col_norm: dict[str, str] = {
            str(c).strip().lower(): str(c) for c in df.columns
        }
        iodb_col_names_norm = list(iodb_col_norm.keys())

        # ───────────────────────────────────────────────────────────────────────
        # Pre-scan template sheet ONCE to build a label-position map.
        # For each cell that contains text matching an IODB column:
        #   label_map[norm_label] = (row, col_of_label_cell)
        # We defer finding the target write-cell to fill-time so we can
        # respect per-tag placeholder state.
        # ───────────────────────────────────────────────────────────────────────
        tmpl_ws = template_wb[ANNEXURE_SHEET]
        # label_map: norm_label -> (row, label_col)
        label_map: dict[str, tuple[int, int]] = {}
        for t_row in tmpl_ws.iter_rows():
            for t_cell in t_row:
                if t_cell.value is None:
                    continue
                norm = str(t_cell.value).strip().lower()
                if not norm:
                    continue
                # Exact match
                if norm in iodb_col_norm:
                    label_map[norm] = (t_cell.row, t_cell.column)
                else:
                    # Fuzzy: check if template label contains or is contained
                    # by an IODB column name (handles "Line Size (NB)" vs "Line size")
                    for iodb_norm in iodb_col_names_norm:
                        if (iodb_norm in norm or norm in iodb_norm) and len(norm) >= 3:
                            if norm not in label_map:
                                label_map[norm] = (t_cell.row, t_cell.column)
                            break

        results: list[tuple[bytes, str]] = []
        total = len(selected_tags)

        for idx, tag in enumerate(selected_tags):
            if progress_callback:
                progress_callback(idx, total)

            # Find IODB row for this tag
            mask = df[tag_column].astype(str).str.strip() == str(tag).strip()
            if not mask.any():
                continue
            row_data = df[mask].iloc[0].to_dict()

            # Build normalised lookup {norm_col -> value}
            iodb_values: dict[str, object] = {}
            for col, val in row_data.items():
                norm_key = str(col).strip().lower()
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    iodb_values[norm_key] = "TBA"
                else:
                    iodb_values[norm_key] = val

            # Deep-copy workbook so every tag gets pristine formatting
            new_wb = _copy_workbook(template_wb)
            ws = new_wb[ANNEXURE_SHEET]

            # ────────────────────────────────────────────────
            # Spatial fill: for each matched label cell,
            # scan rightward for a placeholder and write the IODB value.
            # ────────────────────────────────────────────────
            _spatial_fill(ws, label_map, iodb_values, iodb_col_norm)

            out_bytes = workbook_to_bytes(new_wb)
            safe_tag = re.sub(r'[\\/*?:\[\]]', '_', str(tag))
            filename = f"Datasheet_{safe_tag}.xlsx"
            results.append((out_bytes, filename))

        if progress_callback:
            progress_callback(total, total)

        return results, None

    except Exception as e:
        return None, f"Datasheet generation failed: {e}"


def _is_placeholder(value) -> bool:
    """
    Return True if a cell value is a placeholder that may be overwritten.
    Placeholders: None, empty string, or any string that contains
    'refer annexure' (case-insensitive).
    Any other value — 'NA', 'VTS', a number, a formula — is preserved.
    """
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return True
        if "refer annexure" in stripped.lower() or stripped.lower() == "annexure 1":
            return True
    return False


def _spatial_fill(
    ws,
    label_map: dict[str, tuple[int, int]],
    iodb_values: dict[str, object],
    iodb_col_norm: dict[str, str],
    max_right_search: int = 5,
):
    """
    Fill worksheet by spatial label-to-value mapping.

    For each (norm_label -> (row, label_col)) in label_map:
      1. Resolve which IODB column this label corresponds to.
      2. Get the IODB value for this tag.
      3. Scan cells to the RIGHT (same row) for the first placeholder.
      4. Write the value there.  Never overwrite formulas or meaningful content.
    """
    for norm_label, (r, label_col) in label_map.items():
        # Resolve IODB value for this label
        iodb_value = None
        if norm_label in iodb_values:
            iodb_value = iodb_values[norm_label]
        else:
            # Try fuzzy resolution: find the best-matching IODB column
            for iodb_norm, orig_col in iodb_col_norm.items():
                if (iodb_norm in norm_label or norm_label in iodb_norm) and len(norm_label) >= 3:
                    raw = iodb_values.get(iodb_norm)
                    if raw is not None:
                        iodb_value = raw
                    break

        if iodb_value is None:
            # No IODB column matched this label at all — do nothing
            continue

        # Search rightward for a placeholder cell to write into
        for offset in range(1, max_right_search + 1):
            target = ws.cell(row=r, column=label_col + offset)
            # Skip read-only merged-cell slaves (non-top-left cells in a merge)
            if target.__class__.__name__ == "MergedCell":
                continue
            # Never touch formula cells
            if isinstance(target.value, str) and target.value.startswith("="):
                break  # formula encountered — stop scanning right
            if _is_placeholder(target.value):
                target.value = iodb_value
                break  # wrote successfully — move on to next label


# ─────────────────────────────────────────────────────────────────────────────
# 4. Cable Schedule Generator
# ─────────────────────────────────────────────────────────────────────────────

# Mapping from IODB column → Cable Schedule template column header text
# (based on analysis of the reference Cable_schedule.xlsx)
CABLE_SCHEDULE_COL_MAP = {
    "TAG NO": "TAG NUMBER",
    "LOOP NUMBER": "LOOP NUMBER",
    "EQUIPMENT DESCRIPTION": "EQUIPMENT DESCRIPTION",
    "SIGNAL I/O TYPE": "SIGNAL I/O TYPE",
    "P&ID NO.": "P&ID NO.",
    "SIGNAL TO": "SIGNAL TO",
    "INSTRUMENT TO JB CABLE TAG NO": "INSTRUMENT TO JB CABLE TAG NO",
    "INSTRUMENT TO JB CABLE": "INSTRUMENT TO JB CABLE",
    "BRANCH CABLE LENGTH": "BRANCH CABLE LENGTH",
    "INSTRUMENT SIDE GLAND": "INSTRUMENT SIDE GLAND",
    "JB TAG No.": "JB TAG No.",
    "MAIN CABLE TAG NUMBER": "MAIN CABLE TAG NUMBER",
    "MAIN CABLE TYPE": "MAIN CABLE TYPE",
}

# The target sheet inside the cable schedule template
CABLE_SCHEDULE_SHEET = "Cable Schedule -INST"

# Header row index (1-based) inside the cable schedule template
CABLE_SCHEDULE_HEADER_ROW = 7
# First data row (1-based)
CABLE_SCHEDULE_FIRST_DATA_ROW = 9
# Rows per tag in the template (the reference shows 3 rows per tag entry)
ROWS_PER_TAG = 3
# Max tags per JB section
MAX_TAGS_PER_JB = 12


def generate_cable_schedule(
    df: pd.DataFrame,
    template_wb: openpyxl.Workbook,
    jb_column: str = "JUNCTION BOX",
    tag_column: str = "TAG NO",
    progress_callback=None,
) -> tuple[bytes | None, str | None, str | None]:
    """
    Group IODB rows by JB Number, sort ascending, pad to 12 tags with SPARE,
    and populate into the Cable Schedule template sheet.

    NOTE: Some cable schedule templates contain corrupt style/hyperlink structures
    that cause openpyxl to loop infinitely when saving.  The generator therefore
    reads the header map from the template's read-only view and writes all data
    rows into a fresh openpyxl Workbook (same column layout, no styles copied).
    This avoids the bug while still producing a correct, downloadable output.

    Args:
        df: IODB DataFrame
        template_wb: openpyxl Workbook loaded from the cable schedule template
        jb_column: Column in df containing Junction Box numbers
        tag_column: Column in df containing tag numbers
        progress_callback: optional callable(current, total)

    Returns:
        (bytes, "Cable_Schedule.xlsx", None) on success
        (None, None, error_string) on failure
    """
    try:
        if CABLE_SCHEDULE_SHEET not in template_wb.sheetnames:
            # Fuzzy match
            match = next(
                (s for s in template_wb.sheetnames
                 if "cable schedule" in s.lower() and "inst" in s.lower()),
                None,
            )
            if not match:
                return None, None, (
                    f"Could not find Cable Schedule instrument sheet. "
                    f"Available: {template_wb.sheetnames}"
                )
            target_sheet = match
        else:
            target_sheet = CABLE_SCHEDULE_SHEET

        # ── Read template structure (read-only mode to avoid corrupt-style bugs) ──
        tmpl_ws = template_wb[target_sheet]
        header_map = _build_header_map(tmpl_ws, CABLE_SCHEDULE_HEADER_ROW)
        sub_header_map = _build_header_map(tmpl_ws, CABLE_SCHEDULE_HEADER_ROW + 1)

        # Snapshot the full ferrule block from template rows 9-11.
        # Read ALL columns from AK to max_column — covers TB markers, ferrule
        # codes and anything else in the ferrule section — and copy them
        # exactly (without modification) into every tag block in the output.
        _ferrule_start = column_index_from_string("AK")
        _ferrule_end = max(tmpl_ws.max_column, _ferrule_start)
        ferrule_col_letters = tuple(
            get_column_letter(c) for c in range(_ferrule_start, _ferrule_end + 1)
        )
        formula_block = _read_formula_block(
            tmpl_ws,
            start_row=CABLE_SCHEDULE_FIRST_DATA_ROW,
            num_rows=ROWS_PER_TAG,
            cols=ferrule_col_letters,
        )

        # Also read ferrule column headers (template rows 7 and 8) so they
        # appear in the output header rows as well.
        ferrule_header_rows: dict[tuple[int, int], object] = {}
        for _hoff in range(2):
            _tmpl_hrow = CABLE_SCHEDULE_HEADER_ROW + _hoff
            for _ci in range(_ferrule_start, _ferrule_end + 1):
                _val = None
                for _r in tmpl_ws.iter_rows(
                    min_row=_tmpl_hrow, max_row=_tmpl_hrow,
                    min_col=_ci, max_col=_ci, values_only=True,
                ):
                    _val = _r[0]
                if _val is not None:
                    ferrule_header_rows[(_hoff, _ci)] = _val

        # ── Filter & sort IODB rows ──
        work_df = df[df[jb_column].notna() & (df[jb_column].astype(str).str.strip() != "")].copy()
        work_df[jb_column] = work_df[jb_column].astype(str).str.strip()

        # Natural sort by JB number
        try:
            work_df["_jb_sort"] = work_df[jb_column].apply(
                lambda x: [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', x)]
            )
            work_df = work_df.sort_values("_jb_sort")
            work_df = work_df.drop(columns=["_jb_sort"])
        except Exception:
            work_df = work_df.sort_values(jb_column)

        # ── Group by JB, pad to MAX_TAGS_PER_JB with SPARE ──
        groups = {}
        for jb, grp in work_df.groupby(jb_column, sort=False):
            groups[jb] = grp.to_dict("records")

        all_entries = []
        for jb, rows in groups.items():
            tag_rows = rows[:MAX_TAGS_PER_JB]
            while len(tag_rows) < MAX_TAGS_PER_JB:
                tag_rows.append({tag_column: "SPARE", jb_column: jb})
            all_entries.append((jb, tag_rows))

        # ── Build a fresh output workbook ──
        new_wb = openpyxl.Workbook()
        ws = new_wb.active
        ws.title = target_sheet

        # Write regular column headers from template
        for col_name, col_idx in header_map.items():
            hcell = ws.cell(row=1, column=col_idx, value=col_name.title())
            hcell.alignment = _LIST_ALIGNMENT
            hcell.font = _HEADER_FONT
        for col_name, col_idx in sub_header_map.items():
            if col_name:
                hcell = ws.cell(row=2, column=col_idx, value=col_name)
                hcell.alignment = _LIST_ALIGNMENT
                hcell.font = _HEADER_FONT
        # Write ferrule column headers — exact copy from template
        for (row_off, col_idx), val in ferrule_header_rows.items():
            hcell = ws.cell(row=row_off + 1, column=col_idx, value=val)
            hcell.alignment = _LIST_ALIGNMENT
            hcell.font = _HEADER_FONT

        current_row = 3
        sl_no = 1
        total_jbs = len(all_entries)

        for jb_idx, (jb_name, tag_rows) in enumerate(all_entries):
            if progress_callback:
                progress_callback(jb_idx, total_jbs)

            for tag_entry in tag_rows:
                is_spare = str(tag_entry.get(tag_column, "")).strip().upper() == "SPARE"

                # ── Row A (main data row) ──
                _write_cable_row(
                    ws, current_row, tag_entry, header_map,
                    tag_column, jb_column, sl_no=sl_no,
                )

                # ── Paste full ferrule block for all 3 sub-rows ──
                # Values are copied EXACTLY from the template (no overrides) so
                # the ferrule side looks identical to the reference template.
                for row_offset in range(ROWS_PER_TAG):
                    target_r = current_row + row_offset
                    for (tmpl_col_letter, tmpl_row_off_key), cell_val in formula_block.items():
                        if tmpl_row_off_key == row_offset:
                            col_idx = column_index_from_string(tmpl_col_letter)
                            ws.cell(row=target_r, column=col_idx).value = cell_val

                # Apply formatting to all 3 rows
                for row_offset in range(ROWS_PER_TAG):
                    for cell in ws[current_row + row_offset]:
                        cell.alignment = _LIST_ALIGNMENT
                        cell.font = _LIST_FONT

                if not is_spare:
                    sl_no += 1
                current_row += ROWS_PER_TAG

        if progress_callback:
            progress_callback(total_jbs, total_jbs)

        out_bytes = workbook_to_bytes(new_wb)
        return out_bytes, "Cable_Schedule.xlsx", None

    except Exception as e:
        return None, None, f"Cable Schedule generation failed: {e}"


def _read_formula_block(
    ws,
    start_row: int,
    num_rows: int,
    cols: tuple[str, ...] = ("AK", "AL", "AM", "AN"),
) -> dict[tuple[str, int], object]:
    """
    Read a rectangular block of cells from the template worksheet.
    Returns {(col_letter, row_offset): cell_value} for the given columns
    across `num_rows` rows starting at `start_row`.
    """
    result: dict[tuple[str, int], object] = {}
    for row_offset in range(num_rows):
        row_idx = start_row + row_offset
        for col_letter in cols:
            col_idx = column_index_from_string(col_letter)
            # iter_rows works in read-only mode; use direct cell access
            val = None
            for row in ws.iter_rows(
                min_row=row_idx, max_row=row_idx,
                min_col=col_idx, max_col=col_idx,
                values_only=True,
            ):
                val = row[0]
            result[(col_letter, row_offset)] = val
    return result


def _build_header_map(ws, header_row: int) -> dict[str, int]:
    """
    Read a header row and return {normalised_header_text: column_index (1-based)}.
    """
    result = {}
    for cell in ws[header_row]:
        if cell.value is not None:
            key = str(cell.value).strip().upper()
            result[key] = cell.column
    return result


def _write_cable_row(
    ws,
    row_idx: int,
    tag_entry: dict,
    header_map: dict,
    tag_col: str,
    jb_col: str,
    sl_no: int = 0,
):
    """
    Write one tag's data into the cable schedule worksheet at row_idx.
    Maps IODB column names → template header names using CABLE_SCHEDULE_COL_MAP.
    For SPARE entries, writes SPARE in the TAG NUMBER column and the JB in JB TAG No.
    """
    tag_value = tag_entry.get(tag_col, "")
    is_spare = str(tag_value).strip().upper() == "SPARE"

    if is_spare:
        for template_hdr, col_idx in header_map.items():
            if "TAG" in template_hdr and "NUMBER" in template_hdr:
                ws.cell(row=row_idx, column=col_idx).value = "SPARE"
            elif "JB TAG" in template_hdr or ("JB" in template_hdr and "NO" in template_hdr):
                ws.cell(row=row_idx, column=col_idx).value = tag_entry.get(jb_col, "")
        # Write serial number
        sl_col = header_map.get("SL. NO.  ") or header_map.get("SL. NO.") or 1
        if sl_no:
            ws.cell(row=row_idx, column=sl_col if isinstance(sl_col, int) else 1).value = ""
        return

    # Write serial number in column A
    ws.cell(row=row_idx, column=1).value = sl_no

    for iodb_col, template_col in CABLE_SCHEDULE_COL_MAP.items():
        value = tag_entry.get(iodb_col)
        template_key = template_col.strip().upper()
        col_idx = header_map.get(template_key)
        if col_idx is None:
            col_idx = next(
                (v for k, v in header_map.items() if template_key in k or k in template_key),
                None,
            )
        if col_idx is not None:
            cell = ws.cell(row=row_idx, column=col_idx)
            if isinstance(cell.value, str) and cell.value.startswith("="):
                continue
            if value is None or (isinstance(value, float) and pd.isna(value)):
                cell.value = "TBA"
            else:
                cell.value = value


# ─────────────────────────────────────────────────────────────────────────────
# 5. Loop Wiring Generator
# ─────────────────────────────────────────────────────────────────────────────

# The template sheet to use in the Loop Wiring template
LOOP_WIRING_TEMPLATE_SHEET = "AI - INST"

# Row 7 (1-based) in the AI-INST sheet contains input column headers:
# Tag Number | Loop number | IO TYPE | JB No.  (columns Q-T, i.e. col 17-20)
LOOP_WIRING_HEADER_ROW = 7
# Row 8 is the first data row where values are filled in
LOOP_WIRING_DATA_ROW = 8


def generate_loop_wiring(
    lw_df: pd.DataFrame,
    template_wb: openpyxl.Workbook,
    progress_callback=None,
    template_bytes: bytes = None,
) -> tuple[bytes | None, str | None, str | None]:
    """
    For each tag in the Loop Wiring Input file, duplicate the AI - INST template
    sheet and fill data under the matching column headers in row 8.

    Shapes/lines are preserved by injecting the template drawing XML at ZIP level
    (openpyxl does not round-trip complex drawings).

    Args:
        lw_df: DataFrame from the Loop Wiring Input file (has 'Tag Number' etc.)
        template_wb: openpyxl Workbook loaded from the Loop Wiring template
        progress_callback: optional callable(current, total)
        template_bytes: raw bytes of the template file, used for drawing injection

    Returns:
        (bytes, "Loop_Wiring.xlsx", None) on success
        (None, None, error_string) on failure
    """
    try:
        # Find template sheet (case-insensitive)
        template_sheet_name = next(
            (s for s in template_wb.sheetnames
             if s.strip().lower() == LOOP_WIRING_TEMPLATE_SHEET.lower()),
            None,
        )
        if not template_sheet_name:
            return None, None, (
                f"Loop Wiring template does not contain sheet '{LOOP_WIRING_TEMPLATE_SHEET}'. "
                f"Found: {template_wb.sheetnames}"
            )

        # Find 'Tag Number' column in the input DataFrame
        tag_col = next(
            (c for c in lw_df.columns if c.strip().lower() == "tag number"),
            None,
        )
        if not tag_col:
            return None, None, "Loop Wiring Input file does not have a 'Tag Number' column."

        # Get the header row from the template sheet to know which columns map to what
        tmpl_ws = template_wb[template_sheet_name]
        header_col_map = _get_loop_wiring_header_map(tmpl_ws, LOOP_WIRING_HEADER_ROW)

        # Deep-copy the full template workbook into the output workbook.
        # copy_worksheet() is used (not _copy_workbook + re-load) so that
        # openpyxl's internal drawing/shape references stay intact within the
        # SAME workbook object — shapes are preserved when copying within a wb.
        out_wb = _copy_workbook(template_wb)

        # Remove every sheet except the AI-INST template from the output wb
        for sname in list(out_wb.sheetnames):
            if sname != template_sheet_name:
                del out_wb[sname]

        # Rename the template so we can copy_worksheet from it repeatedly
        out_wb[template_sheet_name].title = "_TEMPLATE_"
        template_in_out = out_wb["_TEMPLATE_"]

        tags = lw_df[tag_col].dropna().astype(str).str.strip().unique().tolist()
        total = len(tags)

        for idx, tag in enumerate(tags):
            if progress_callback:
                progress_callback(idx, total)

            # copy_worksheet preserves cell values, formulas, styles AND drawings.
            # openpyxl's copy_worksheet does a SHALLOW copy of the drawing, so every
            # sheet ends up sharing the same drawing object — that causes missing shapes
            # when saving.  deepcopy gives each sheet its own independent drawing tree.
            new_ws = out_wb.copy_worksheet(template_in_out)
            safe_tag = re.sub(r'[\\/*?:\[\]]', '_', tag)
            new_ws.title = safe_tag[:31]
            try:
                if getattr(template_in_out, '_drawing', None) is not None:
                    new_ws._drawing = copy.deepcopy(template_in_out._drawing)
            except Exception:
                pass  # prefer partial output over a crash

            # Locate this tag's row in the input DataFrame
            tag_rows = lw_df[lw_df[tag_col].astype(str).str.strip() == tag]
            if tag_rows.empty:
                continue
            row_data = tag_rows.iloc[0].to_dict()

            # Fill data row — never touch the drawing layer
            _fill_loop_wiring_row(new_ws, LOOP_WIRING_DATA_ROW, row_data, header_col_map)

        # Remove the placeholder template sheet from the output
        del out_wb["_TEMPLATE_"]

        if not out_wb.sheetnames:
            return None, None, "No sheets were generated. Check that tags exist in the input file."

        if progress_callback:
            progress_callback(total, total)

        out_bytes = workbook_to_bytes(out_wb)

        # Inject drawing shapes/lines from the template at ZIP level.
        # openpyxl does not expose complex drawings (connectors, ovals, text-boxes)
        # through its Python API; we must copy the raw drawing XML into the output
        # zip so Excel/Numbers can render the same lines and shapes on every sheet.
        if template_bytes is not None:
            out_bytes = _inject_drawings_from_template(
                out_bytes, template_bytes, template_sheet_name
            )

        return out_bytes, "Loop_Wiring.xlsx", None

    except Exception as e:
        return None, None, f"Loop Wiring generation failed: {e}"


def _get_loop_wiring_header_map(ws, header_row: int) -> dict[str, int]:
    """
    Read the header row of the loop wiring template to map column names → column indices.
    The template keeps input headers (Tag Number, Loop number, IO TYPE, JB No., etc.)
    in specific columns of the header row.
    Returns {normalised_col_name: col_index (1-based)}.
    """
    result = {}
    for cell in ws[header_row]:
        if cell.value is not None:
            key = str(cell.value).strip().lower()
            result[key] = cell.column
    return result


def _fill_loop_wiring_row(ws, data_row: int, row_data: dict, header_col_map: dict):
    """
    Fill data_row in the loop wiring sheet using header_col_map to find target columns.
    - Only writes to cells that do NOT already contain a formula.
    - Writes "TBA" for None / NaN values.
    - Does not touch any drawing or shape objects.
    """
    # Normalise input row keys to lowercase for case-insensitive matching
    norm_row = {str(k).strip().lower(): v for k, v in row_data.items()}

    for header_key, col_idx in header_col_map.items():
        value = norm_row.get(header_key)
        # Also try partial / alias matches for common column name variations
        if value is None:
            for rk, rv in norm_row.items():
                if header_key in rk or rk in header_key:
                    value = rv
                    break
        cell = ws.cell(row=data_row, column=col_idx)
        if isinstance(cell.value, str) and cell.value.startswith("="):
            continue  # never overwrite formulas
        if value is None or (isinstance(value, float) and pd.isna(value)):
            # Only write TBA if the cell is currently empty
            if cell.value is None:
                cell.value = "TBA"
        else:
            cell.value = value


# ─────────────────────────────────────────────────────────────────────────────
# Utility: deep-copy a workbook
# ─────────────────────────────────────────────────────────────────────────────

def _inject_drawings_from_template(
    out_bytes: bytes,
    tmpl_bytes: bytes,
    template_sheet_name: str,
) -> bytes:
    """
    Post-process the output xlsx (bytes) to inject the drawing XML from the
    matching template sheet into EVERY sheet of the output workbook.

    Works entirely at the ZIP/XML level, bypassing openpyxl's incomplete
    drawing support.  If anything goes wrong the original bytes are returned
    unchanged so the caller always gets a valid file.
    """
    NS_R_TYPE_DRAWING = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"
    )
    try:
        from xml.etree import ElementTree as ET

        # ── 1. Locate and extract drawing XML from the template zip ──────────
        drawing_xml_bytes = None
        with zipfile.ZipFile(io.BytesIO(tmpl_bytes)) as tz:
            tz_names = tz.namelist()
            NS_SS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            NS_R  = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

            # Find the rId for the target sheet in workbook.xml
            wb_root = ET.fromstring(tz.read('xl/workbook.xml'))
            sheet_rid = None
            for el in wb_root.iter(f'{{{NS_SS}}}sheet'):
                if el.get('name', '').strip().lower() == template_sheet_name.strip().lower():
                    sheet_rid = el.get(f'{{{NS_R}}}id')
                    break
            if sheet_rid is None:
                return out_bytes

            # Resolve rId → worksheet filename through workbook.xml.rels
            wb_rels = ET.fromstring(tz.read('xl/_rels/workbook.xml.rels'))
            sheet_file = None
            for rel in wb_rels:
                if rel.get('Id') == sheet_rid:
                    sheet_file = rel.get('Target')  # e.g. "worksheets/sheet1.xml"
                    break
            if sheet_file is None:
                return out_bytes

            # Find drawing reference in the sheet's rels file
            sheet_basename = sheet_file.split('/')[-1]     # "sheet1.xml"
            rels_path = f'xl/worksheets/_rels/{sheet_basename}.rels'
            if rels_path not in tz_names:
                return out_bytes
            sheet_rels = ET.fromstring(tz.read(rels_path))
            drawing_filename = None
            for rel in sheet_rels:
                if rel.get('Type') == NS_R_TYPE_DRAWING:
                    drawing_filename = rel.get('Target').split('/')[-1]  # "drawing1.xml"
                    break
            if drawing_filename is None:
                return out_bytes

            drawing_zip_path = f'xl/drawings/{drawing_filename}'
            if drawing_zip_path not in tz_names:
                return out_bytes
            drawing_xml_bytes = tz.read(drawing_zip_path)

        if drawing_xml_bytes is None:
            return out_bytes

        # ── 2. Read output zip into memory ───────────────────────────────────
        with zipfile.ZipFile(io.BytesIO(out_bytes)) as oz:
            entries: dict[str, bytes] = {n: oz.read(n) for n in oz.namelist()}

        # Collect sheet files sorted numerically
        sheet_paths = sorted(
            (n for n in entries
             if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')),
            key=lambda x: int(re.search(r'(\d+)', x.split('/')[-1]).group(1))
            if re.search(r'(\d+)', x.split('/')[-1]) else 0,
        )
        if not sheet_paths:
            return out_bytes

        # ── 3. Inject drawing into each sheet ────────────────────────────────
        ct_text = entries.get('[Content_Types].xml', b'').decode('utf-8')
        DRAWING_CT = 'application/vnd.openxmlformats-officedocument.drawing+xml'

        for i, sheet_path in enumerate(sheet_paths, start=1):
            drw_name  = f'drawing_lw{i}.xml'
            drw_zip   = f'xl/drawings/{drw_name}'
            drw_rel   = f'../drawings/{drw_name}'
            ct_part   = f'/xl/drawings/{drw_name}'
            rel_id    = 'rIdLwDrw'

            # Store the drawing XML bytes
            entries[drw_zip] = drawing_xml_bytes

            # Update or create the sheet's rels file
            sht_base  = sheet_path.split('/')[-1]           # "sheet1.xml"
            rels_path = f'xl/worksheets/_rels/{sht_base}.rels'
            if rels_path in entries:
                rels_text = entries[rels_path].decode('utf-8')
                if NS_R_TYPE_DRAWING not in rels_text:
                    new_rel = (
                        f'<Relationship Id="{rel_id}" '
                        f'Type="{NS_R_TYPE_DRAWING}" '
                        f'Target="{drw_rel}"/>'
                    )
                    rels_text = rels_text.replace(
                        '</Relationships>', new_rel + '</Relationships>'
                    )
                    entries[rels_path] = rels_text.encode('utf-8')
                else:
                    rel_id = None  # drawing rel already present; extract its id
            else:
                rels_content = (
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    f'<Relationship Id="{rel_id}" '
                    f'Type="{NS_R_TYPE_DRAWING}" '
                    f'Target="{drw_rel}"/>'
                    '</Relationships>'
                )
                entries[rels_path] = rels_content.encode('utf-8')

            # Add <drawing r:id="..."/> to the sheet XML if not already there
            sht_xml = entries[sheet_path].decode('utf-8')
            if '<drawing' not in sht_xml and rel_id is not None:
                ns_r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
                if 'xmlns:r=' not in sht_xml:
                    sht_xml = sht_xml.replace(
                        '<worksheet ', f'<worksheet xmlns:r="{ns_r}" ', 1
                    )
                sht_xml = sht_xml.replace(
                    '</worksheet>',
                    f'<drawing r:id="{rel_id}"/></worksheet>',
                )
                entries[sheet_path] = sht_xml.encode('utf-8')

            # Register in [Content_Types].xml
            if ct_part not in ct_text:
                ct_text = ct_text.replace(
                    '</Types>',
                    f'<Override PartName="{ct_part}" ContentType="{DRAWING_CT}"/></Types>',
                )

        entries['[Content_Types].xml'] = ct_text.encode('utf-8')

        # ── 4. Rebuild the zip ────────────────────────────────────────────────
        out_buf = io.BytesIO()
        with zipfile.ZipFile(out_buf, 'w', zipfile.ZIP_DEFLATED) as zout:
            for name, data in entries.items():
                zout.writestr(name, data)
        out_buf.seek(0)
        return out_buf.read()

    except Exception:
        return out_bytes  # always return a valid file even if injection fails


def _copy_workbook(wb: openpyxl.Workbook) -> openpyxl.Workbook:
    """
    Serialize a workbook to bytes and reload it, achieving a deep copy.

    Image-ref fix: openpyxl's Image._data() closes img.ref (a BytesIO) after
    reading image bytes during wb.save().  That means a second call to
    _copy_workbook on the same wb would fail with "I/O operation on closed file".
    After each save we therefore restore wb's image refs from the freshly-loaded
    copy's independent BytesIO objects so every subsequent call works correctly.
    """
    buf = io.BytesIO()
    wb.save(buf)           # NOTE: closes every img.ref on wb
    raw = buf.getvalue()   # full bytes before seeking
    buf.seek(0)
    new_wb = load_workbook(buf)
    new_wb._copybuf = buf  # keep buf alive for new_wb's own save()

    # Restore img.refs on original wb (and give new_wb fresh independent refs)
    # so that (a) the next _copy_workbook call on wb works and (b) new_wb.save()
    # can write its images without a closed-file error.
    for ws_orig, ws_new in zip(wb.worksheets, new_wb.worksheets):
        orig_imgs = getattr(ws_orig, '_images', [])
        new_imgs  = getattr(ws_new,  '_images', [])
        for o_img, n_img in zip(orig_imgs, new_imgs):
            try:
                # getvalue() returns all bytes regardless of current stream pos
                img_bytes = (n_img.ref.getvalue()
                             if hasattr(n_img.ref, 'getvalue')
                             else (n_img.ref.seek(0) or n_img.ref.read()))
                o_img.ref = io.BytesIO(img_bytes)   # fresh ref for next copy
                n_img.ref = io.BytesIO(img_bytes)   # fresh ref for this copy's save
            except Exception:
                pass

    return new_wb
