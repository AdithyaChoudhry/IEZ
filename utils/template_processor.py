"""
template_processor.py
Higher-level helpers that combine file_handler + generators,
providing simple single-call interfaces for each module
that Streamlit main.py can use directly.
"""

import io
import zipfile
import openpyxl
import pandas as pd

from utils.file_handler import (
    read_iodb,
    read_loop_wiring_input,
    load_workbook_from_upload,
    dataframe_to_bytes,
)
from utils.generators import (
    generate_instrument_list,
    generate_io_list,
    generate_datasheets,
    generate_cable_schedule,
    generate_loop_wiring,
)


# ─────────────────────────────────────────────────────────────────────────────
# Instrument List
# ─────────────────────────────────────────────────────────────────────────────

def process_instrument_list(
    iodb_file,
    selected_columns: list[str],
) -> tuple[bytes | None, str | None, str | None]:
    """
    Full pipeline: read IODB → generate instrument list.

    Returns (bytes, filename, error)
    """
    df, err = read_iodb(iodb_file)
    if err:
        return None, None, f"Failed to read IODB: {err}"
    return generate_instrument_list(df, selected_columns)


# ─────────────────────────────────────────────────────────────────────────────
# I/O List
# ─────────────────────────────────────────────────────────────────────────────

def process_io_list(
    iodb_file,
    selected_columns: list[str],
) -> tuple[bytes | None, str | None, str | None]:
    """
    Full pipeline: read IODB → generate I/O list.

    Returns (bytes, filename, error)
    """
    df, err = read_iodb(iodb_file)
    if err:
        return None, None, f"Failed to read IODB: {err}"
    return generate_io_list(df, selected_columns)


# ─────────────────────────────────────────────────────────────────────────────
# Data Sheet
# ─────────────────────────────────────────────────────────────────────────────

def process_datasheets(
    iodb_file,
    template_file,
    tag_column: str,
    selected_tags: list[str],
    progress_callback=None,
) -> tuple[bytes | None, str | None, str | None]:
    """
    Full pipeline: read IODB + template → generate datasheets → zip all files.

    Returns (zip_bytes, "Datasheets.zip", error)
    """
    df, err = read_iodb(iodb_file)
    if err:
        return None, None, f"Failed to read IODB: {err}"

    wb, _, err = load_workbook_from_upload(template_file)
    if err:
        return None, None, f"Failed to load template: {err}"

    results, err = generate_datasheets(df, wb, tag_column, selected_tags, progress_callback)
    if err:
        return None, None, err
    if not results:
        return None, None, "No datasheets were generated. Check that the selected tags exist in the IODB."

    # Package all individual Excel files into a ZIP
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_bytes, filename in results:
            zf.writestr(filename, file_bytes)
    zip_buf.seek(0)
    return zip_buf.read(), "Datasheets.zip", None


# ─────────────────────────────────────────────────────────────────────────────
# Cable Schedule
# ─────────────────────────────────────────────────────────────────────────────

def process_cable_schedule(
    iodb_file,
    template_file,
    jb_column: str = "JUNCTION BOX",
    tag_column: str = "TAG NO",
    progress_callback=None,
) -> tuple[bytes | None, str | None, str | None]:
    """
    Full pipeline: read IODB + template → generate cable schedule.
    Template is opened in read-only mode to avoid corrupt-style openpyxl bugs
    present in some reference cable schedule files.

    Returns (bytes, "Cable_Schedule.xlsx", error)
    """
    df, err = read_iodb(iodb_file)
    if err:
        return None, None, f"Failed to read IODB: {err}"

    # Use read_only=True to safely load templates that have corrupt style tables
    wb, _, err = load_workbook_from_upload(template_file, read_only=True)
    if err:
        return None, None, f"Failed to load template: {err}"

    return generate_cable_schedule(df, wb, jb_column, tag_column, progress_callback)


# ─────────────────────────────────────────────────────────────────────────────
# Loop Wiring
# ─────────────────────────────────────────────────────────────────────────────

def process_loop_wiring(
    loop_input_file,
    template_file,
    progress_callback=None,
) -> tuple[bytes | None, str | None, str | None]:
    """
    Full pipeline: read Loop Wiring input + template → generate loop wiring sheets.

    Returns (bytes, "Loop_Wiring.xlsx", error)
    """
    df, err = read_loop_wiring_input(loop_input_file)
    if err:
        return None, None, f"Failed to read Loop Wiring Input: {err}"

    wb, tmpl_buf, err = load_workbook_from_upload(template_file)
    if err:
        return None, None, f"Failed to load Loop Wiring template: {err}"

    tmpl_buf.seek(0)
    tmpl_bytes = tmpl_buf.read()
    return generate_loop_wiring(df, wb, progress_callback, template_bytes=tmpl_bytes)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: get IODB columns for UI dropdowns
# ─────────────────────────────────────────────────────────────────────────────

def get_iodb_columns(iodb_file) -> tuple[list[str] | None, str | None]:
    """
    Load IODB and return the list of column names for UI multiselect.

    Returns (columns_list, None) or (None, error_string)
    """
    df, err = read_iodb(iodb_file)
    if err:
        return None, err
    return list(df.columns), None


def get_iodb_tags(iodb_file, tag_column: str = "TAG NO") -> tuple[list[str] | None, str | None]:
    """
    Load IODB and return a list of unique, non-null tag numbers for UI selection.

    Returns (tags_list, None) or (None, error_string)
    """
    df, err = read_iodb(iodb_file)
    if err:
        return None, err
    if tag_column not in df.columns:
        return None, f"Column '{tag_column}' not found in IODB. Available: {list(df.columns)}"
    tags = df[tag_column].dropna().astype(str).str.strip()
    tags = sorted(tags[tags != ""].unique().tolist())
    return tags, None


def get_iodb_dataframe(iodb_file) -> tuple[pd.DataFrame | None, str | None]:
    """Return the full IODB dataframe for preview purposes."""
    return read_iodb(iodb_file)
