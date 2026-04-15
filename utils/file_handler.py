"""
file_handler.py
Handles reading uploaded Excel files into pandas DataFrames or openpyxl Workbooks.
Provides safe wrappers with error feedback.
"""

import io
import re
import zipfile
import pandas as pd
import openpyxl


def read_iodb(uploaded_file) -> tuple[pd.DataFrame | None, str | None]:
    """
    Read the IODB Source Excel file.
    The IODB sheet uses row 1 as the header.

    Returns:
        (DataFrame, None) on success
        (None, error_message) on failure
    """
    try:
        uploaded_file.seek(0)
        # First try a direct (case-sensitive) read for speed
        try:
            df = pd.read_excel(uploaded_file, sheet_name="IODB", header=0)
            uploaded_file.seek(0)
            df = df.dropna(how="all").reset_index(drop=True)
            return df, None
        except Exception:
            uploaded_file.seek(0)

        # Otherwise inspect workbook sheet names and try to find the best match.
        uploaded_file.seek(0)
        xls = pd.ExcelFile(uploaded_file)
        names = xls.sheet_names

        # 1) exact match (case-insensitive)
        match = next((s for s in names if s.strip().lower() == 'iodb'), None)
        # 2) substring match
        if match is None:
            match = next((s for s in names if 'iodb' in s.strip().lower()), None)

        # 3) fallback: look for a sheet that contains a Tag-like column header
        if match is None:
            for s in names:
                try:
                    uploaded_file.seek(0)
                    sample = pd.read_excel(uploaded_file, sheet_name=s, nrows=6)
                    uploaded_file.seek(0)
                except Exception:
                    uploaded_file.seek(0)
                    continue
                cols_lower = [str(c).strip().lower() for c in sample.columns]
                tag_keys = ('tag no', 'tag', 'tag number', 'tag_number')
                if any(k in cols_lower for k in tag_keys):
                    match = s
                    break

        if match is None:
            return None, "Worksheet named 'IODB' not found. Please ensure the IODB sheet is present or contains a 'Tag' column."

        # Read the detected sheet with header detection: sometimes the real
        # header row is not the first row (leading notes/metadata). Try
        # header=0 first, then probe header rows up to 10 to find a sensible
        # header that contains a Tag-like column or has non-empty column names.
        uploaded_file.seek(0)
        df = pd.read_excel(uploaded_file, sheet_name=match, header=0)
        # If columns are mostly unnamed or the standard tag column is missing,
        # attempt to detect header row.
        cols = [str(c) for c in df.columns]
        unnamed_count = sum(1 for c in cols if c.startswith('Unnamed'))
        tag_keys = ('tag no', 'tag', 'tag number', 'tag_number')
        has_tag = any(k in [str(c).strip().lower() for c in cols] for k in tag_keys)

        if unnamed_count > max(1, len(cols) // 2) or not has_tag:
            # probe header rows and pick the best candidate by score.
            # Score = 100 if contains tag-like header + number of non-unnamed columns.
            best_score = -1
            best_df = df
            for hr in range(0, 11):
                try:
                    uploaded_file.seek(0)
                    cand = pd.read_excel(uploaded_file, sheet_name=match, header=hr)
                    uploaded_file.seek(0)
                except Exception:
                    uploaded_file.seek(0)
                    continue
                cand_cols_raw = list(cand.columns)
                cand_cols = [str(c).strip().lower() for c in cand_cols_raw]
                n_non_unnamed = sum(1 for c in cand_cols_raw if not str(c).startswith('Unnamed') and str(c).strip() != '')
                has_tag_cand = any(k in cand_cols for k in tag_keys)
                score = (100 if has_tag_cand else 0) + n_non_unnamed
                if score > best_score:
                    best_score = score
                    best_df = cand
                    # if candidate has tag header, it's the best possible — stop early
                    if has_tag_cand:
                        break
            df = best_df

        df = df.dropna(how="all").reset_index(drop=True)
        return df, None
    except Exception as e:
        return None, str(e)


def read_loop_wiring_input(uploaded_file) -> tuple[pd.DataFrame | None, str | None]:
    """
    Read the Loop Wiring Input Excel file.
    The relevant data sheet has headers in row 7 (0-indexed row 6).
    Returns the sheet that contains 'Tag Number' in its header row.

    Returns:
        (DataFrame, None) on success
        (None, error_message) on failure
    """
    try:
        uploaded_file.seek(0)
        xls = pd.ExcelFile(uploaded_file)
        for sheet_name in xls.sheet_names:
            # Try reading with different header offsets to find 'Tag Number'
            for header_row in range(0, 10):
                try:
                    df = pd.read_excel(
                        uploaded_file, sheet_name=sheet_name, header=header_row
                    )
                    uploaded_file.seek(0)
                    # Check if 'Tag Number' column exists (case-insensitive)
                    cols_lower = [str(c).strip().lower() for c in df.columns]
                    if "tag number" in cols_lower:
                        # Normalise column names
                        df.columns = [str(c).strip() for c in df.columns]
                        df = df.dropna(how="all").reset_index(drop=True)
                        return df, None
                except Exception:
                    uploaded_file.seek(0)
                    continue
        return None, "Could not find a sheet with a 'Tag Number' column in the Loop Wiring Input file."
    except Exception as e:
        return None, str(e)


# Magic bytes that identify file formats
_ZIP_MAGIC = b'PK\x03\x04'       # .xlsx / .xlsm (ZIP-based)
_OLE2_MAGIC = b'\xd0\xcf\x11\xe0'  # .xls (OLE2 / BIFF)

# ── [Content_Types].xml synthesiser ─────────────────────────────────────────
# Used when a ZIP-based .xlsx is missing its [Content_Types].xml entry.
# We map well-known part paths / path patterns to their OOXML content types
# and emit a minimal but valid XML so openpyxl can proceed.
_CT_OVERRIDES: dict[str, str] = {
    'xl/workbook.xml':        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml',
    'xl/workbook.bin':        'application/vnd.ms-excel.sheet.binary.macroEnabled.main',
    'xl/sharedstrings.xml':   'application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml',
    'xl/styles.xml':          'application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml',
    'xl/calcchain.xml':       'application/vnd.openxmlformats-officedocument.spreadsheetml.calcChain+xml',
    'docprops/core.xml':      'application/vnd.openxmlformats-package.core-properties+xml',
    'docprops/app.xml':       'application/vnd.openxmlformats-officedocument.extended-properties+xml',
}
_CT_PATTERNS: list[tuple[str, str]] = [
    (r'^xl/worksheets/sheet\d+\.xml$',   'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'),
    (r'^xl/theme/theme\d*\.xml$',        'application/vnd.openxmlformats-officedocument.theme+xml'),
    (r'^xl/drawings/drawing\d+\.xml$',   'application/vnd.openxmlformats-officedocument.drawing+xml'),
    (r'^xl/charts/chart\d+\.xml$',       'application/vnd.openxmlformats-officedocument.drawingml.chart+xml'),
    (r'^xl/chartsheets/sheet\d+\.xml$',  'application/vnd.openxmlformats-officedocument.spreadsheetml.chartsheet+xml'),
    (r'^xl/macrosheets/sheet\d+\.xml$',  'application/vnd.ms-excel.macrosheet+xml'),
]


def _synthesize_content_types(names: list[str]) -> bytes:
    """Return a minimal valid [Content_Types].xml body derived from the ZIP entry list."""
    defaults = [
        ('rels',  'application/vnd.openxmlformats-package.relationships+xml'),
        ('xml',   'application/xml'),
        ('vml',   'application/vnd.openxmlformats-officedocument.vmlDrawing'),
        ('png',   'image/png'),
        ('jpg',   'image/jpeg'),
        ('jpeg',  'image/jpeg'),
        ('gif',   'image/gif'),
        ('emf',   'image/x-emf'),
        ('wmf',   'image/x-wmf'),
        ('bin',   'application/vnd.openxmlformats-officedocument.spreadsheetml.printerSettings'),
    ]
    overrides: dict[str, str] = {}
    for name in names:
        nl = name.lower().lstrip('/')
        if nl in _CT_OVERRIDES:
            overrides[f'/{name}'] = _CT_OVERRIDES[nl]
            continue
        for pattern, ct in _CT_PATTERNS:
            if re.match(pattern, nl):
                overrides[f'/{name}'] = ct
                break
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
    ]
    for ext, ct in defaults:
        lines.append(f'  <Default Extension="{ext}" ContentType="{ct}"/>')
    for part, ct in overrides.items():
        lines.append(f'  <Override PartName="{part}" ContentType="{ct}"/>')
    lines.append('</Types>')
    return '\n'.join(lines).encode('utf-8')


def load_workbook_from_upload(uploaded_file, keep_vba: bool = False, read_only: bool = False):
    """
    Load an openpyxl Workbook from a Streamlit UploadedFile or BytesIO.

    Robustness features:
      - Detects and rejects old-format .xls (OLE2) files with a clear message.
      - Falls back to keep_vba=True for macro-enabled workbooks disguised as .xlsx.
      - Falls back to read_only mode if normal load fails (avoids corrupt-style bugs).

    Returns:
        (Workbook, BytesIO_buffer, None) on success
        (None, None, error_message) on failure
    """
    try:
        uploaded_file.seek(0)
        data = uploaded_file.read()
    except Exception as e:
        return None, None, f"Could not read file data: {e}"

    if not data:
        return None, None, (
            "The uploaded file is empty. Please upload a valid .xlsx file."
        )

    # Detect old .xls binary format — openpyxl cannot open these
    if data[:4] == _OLE2_MAGIC:
        return None, None, (
            "The uploaded file appears to be an old-format Excel file (.xls / Excel 97-2003). "
            "Please re-save it as .xlsx (Excel Workbook) and upload again."
        )

    # Verify ZIP magic so we give a clear error before openpyxl tries
    if data[:4] != _ZIP_MAGIC:
        return None, None, (
            "The uploaded file is not a valid Excel .xlsx file. "
            "Please upload an Excel Workbook (.xlsx)."
        )

    # ── ZIP-level repair ──────────────────────────────────────────────────────
    # Some files (created by LibreOffice, Google Sheets, or non-standard exporters)
    # store [Content_Types].xml with incorrect casing or entry ordering that
    # confuses openpyxl's case-sensitive ZipFile lookup.
    # We rebuild the archive with the canonical entry name so openpyxl can find it.
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            ct_entry = next(
                (n for n in names if n.lower() == '[content_types].xml'), None
            )
            if ct_entry is None:
                # Auto-repair: synthesize a valid [Content_Types].xml from the archive contents
                ct_content = _synthesize_content_types(names)
                clean = io.BytesIO()
                with zipfile.ZipFile(clean, 'w', zipfile.ZIP_DEFLATED) as zout:
                    zout.writestr('[Content_Types].xml', ct_content)
                    for name in names:
                        zout.writestr(name, z.read(name))
                clean.seek(0)
                data = clean.read()
            elif ct_entry != '[Content_Types].xml':
                # Rebuild the ZIP with the correct canonical entry name
                clean = io.BytesIO()
                with zipfile.ZipFile(clean, 'w', zipfile.ZIP_DEFLATED) as zout:
                    for name in names:
                        content = z.read(name)
                        out_name = '[Content_Types].xml' if name == ct_entry else name
                        zout.writestr(out_name, content)
                clean.seek(0)
                data = clean.read()
    except zipfile.BadZipFile as e:
        return None, None, f"The file is not a valid ZIP/Excel archive: {e}"
    except Exception:
        pass  # ZIP repair failed; fall through and let openpyxl try anyway

    # Progressive loading strategies
    strategies = [
        dict(keep_vba=keep_vba,  read_only=read_only, keep_links=False),
        dict(keep_vba=True,      read_only=read_only, keep_links=False),  # .xlsm disguised as .xlsx
        dict(keep_vba=False,     read_only=True,      keep_links=False),  # skip corrupt style tables
        dict(keep_vba=True,      read_only=True,      keep_links=False),  # last resort
    ]
    last_err = None
    for opts in strategies:
        try:
            buf = io.BytesIO(data)
            wb = openpyxl.load_workbook(buf, **opts)
            buf.seek(0)
            return wb, buf, None
        except Exception as e:
            last_err = e
            continue

    return None, None, str(last_err)


def workbook_to_bytes(wb: openpyxl.Workbook) -> bytes:
    """Serialise an openpyxl Workbook to bytes for Streamlit download."""
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def dataframe_to_bytes(df: pd.DataFrame) -> bytes:
    """Serialise a pandas DataFrame to an xlsx bytes object."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buf.seek(0)
    return buf.read()
