"""Excel workbook generation for Process Data Requisition."""
from __future__ import annotations
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from datetime import datetime
from .file_handler import workbook_to_bytes
from .process_data_library import INSTRUMENT_TYPES, IDENTIFICATION_COLUMNS
from .process_data_fields._types import FieldType, ProcessField

_THIN = Side(style="thin", color="999999")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
_ID_FILL = PatternFill("solid", fgColor="EAF1F8")
_SOURCE_FILL = PatternFill("solid", fgColor="E2F0D9")
_INPUT_FILL = PatternFill("solid", fgColor="FFFFFF")
_BODY_FONT = Font(name="Calibri", size=11)
_CENTER_WRAP = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT_WRAP = Alignment(horizontal="left", vertical="center", wrap_text=True)

# Exact order of the 8 identification columns, matching IDENTIFICATION_COLUMNS /
# the keys produced by process_data_matcher.match_tags():
# S.NO, TAG NO, EQUIPMENT DESCRIPTION, P&ID NO., SERVICE, EQUIPMENT NO, LINE, LINE SIZE
_ID_KEYS = ("s_no", "tag_no", "equipment_description", "pid_no", "service",
            "equipment_no", "line", "line_size")
_LEFT_ALIGN_ID_KEYS = {"equipment_description"}


def _make_custom_fields(cf: dict) -> list:
    """One user-defined parameter -> Minimum / Normal / Maximum columns (+ a remarks column
    when the engineer wants one). All blank for the Process team."""
    name = (cf.get("parameter") or "").strip() or "Parameter"
    unit = (cf.get("unit") or "").strip()
    fields = [ProcessField(f"{name} {label}", unit=unit, field_type=FieldType.NUMBER)
              for label in ("Minimum", "Normal", "Maximum")]
    fields.append(ProcessField(f"{name} Remarks", field_type=FieldType.TEXT))
    return fields


def _resolve_fields(cfg, subtype, custom_fields, selected_fields=None):
    """Return the ordered list of ProcessField to actually write for this type/subtype.
    Filters out any field whose subtype_only is non-empty and doesn't include the chosen subtype.
    For is_custom types, builds ProcessField objects on the fly from custom_fields
    (list of dicts: {"parameter": str, "unit": str, ...}) instead of cfg.fields."""
    if cfg.is_custom:
        return [f for cf in (custom_fields or []) for f in _make_custom_fields(cf)]
    result = []
    for f in cfg.fields:
        if f.subtype_only and subtype not in f.subtype_only:
            continue
        if selected_fields is not None and f.name not in selected_fields:
            continue
        result.append(f)
    return result


def column_header(f) -> str:
    """Header text for a process field: name plus unit, e.g. 'Process Temperature Min (°C)'."""
    unit = (getattr(f, "unit", "") or "").strip()
    return f"{f.name} ({unit})" if unit else f.name


def _sanitize(s) -> str:
    return "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in (s or "")).strip("_")


def _build_filename(type_label: str, project_name: str) -> str:
    safe_type = _sanitize(type_label) or "Instrument"
    safe_project = _sanitize(project_name) or "Project"
    return f"Process_Data_Requisition_{safe_type}_{safe_project}.xlsx"


def _autofit_widths(ws, columns: list[str], header_row: int):
    for i, col_name in enumerate(columns, start=1):
        max_len = len(str(col_name))
        for row in ws.iter_rows(min_row=header_row + 1, min_col=i, max_col=i):
            for cell in row:
                if cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[get_column_letter(i)].width = min(max(max_len + 2, 10), 60)


def generate_process_data_requisition(
    matched_rows: list[dict],
    prefill: list[dict],
    type_key: str,
    subtype,
    project_name: str,
    source_filename: str,
    custom_fields=None,
    custom_name: str = "",
    selected_fields=None,
) -> tuple[bytes, str]:
    """Build the full workbook. matched_rows and prefill are parallel lists (same length/order).
    matched_rows[i] has the 8 identification values (keys: tag_no, equipment_description, pid_no,
    service, equipment_no, line, line_size). prefill[i] is {process_field_name: value}.
    Returns (xlsx_bytes, filename)."""
    cfg = INSTRUMENT_TYPES[type_key]
    fields = _resolve_fields(cfg, subtype, custom_fields, selected_fields)
    id_names = [f.name for f in IDENTIFICATION_COLUMNS]
    all_column_names = id_names + [column_header(f) for f in fields]

    wb = Workbook()
    ws = wb.active
    ws.title = "PROCESS DATA REQUISITION"

    # info block, rows 1-3
    ws.cell(row=1, column=1, value="PROCESS DATA REQUISITION").font = Font(bold=True, size=14)
    ws.cell(row=2, column=1, value=f"Instrument Type: {cfg.label}" + (f" ({subtype})" if subtype else "") + (f" - {custom_name}" if custom_name else ""))
    ws.cell(row=2, column=4, value=f"Project: {project_name or ''}")
    ws.cell(row=3, column=1, value=f"Generated from: {source_filename or 'IODB'}")
    ws.cell(row=3, column=4, value=f"Generated on: {datetime.now().strftime('%Y-%m-%d')}")

    header_row = 5
    for col_idx, name in enumerate(all_column_names, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=name)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _CENTER_WRAP
        cell.border = _BORDER

    for r, (row_data, row_prefill) in enumerate(zip(matched_rows, prefill), start=1):
        excel_row = header_row + r
        values = {"s_no": r, **row_data}
        for col_idx, key in enumerate(_ID_KEYS, start=1):
            cell = ws.cell(row=excel_row, column=col_idx, value=values.get(key, ""))
            cell.font = _BODY_FONT
            cell.alignment = _LEFT_WRAP if key in _LEFT_ALIGN_ID_KEYS else _CENTER_WRAP
            cell.border = _BORDER
            cell.fill = _ID_FILL
        for f_idx, f in enumerate(fields, start=1):
            col_idx = len(_ID_KEYS) + f_idx
            val = row_prefill.get(f.name, "") if row_prefill else ""
            cell = ws.cell(row=excel_row, column=col_idx, value=val)
            cell.font = _BODY_FONT
            cell.alignment = _LEFT_WRAP
            cell.border = _BORDER
            cell.fill = _SOURCE_FILL if val else _INPUT_FILL

    last_data_row = header_row + len(matched_rows)
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    if last_data_row > header_row:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(all_column_names))}{last_data_row}"

    for f_idx, f in enumerate(fields, start=1):
        if f.field_type not in (FieldType.DROPDOWN, FieldType.BOOLEAN):
            continue
        options = list(f.options) if f.field_type == FieldType.DROPDOWN else ["Yes", "No"]
        if not options:
            continue
        col_idx = len(_ID_KEYS) + f_idx
        col_letter = get_column_letter(col_idx)
        formula = '"' + ",".join(options) + '"'
        dv = DataValidation(type="list", formula1=formula, allow_blank=True)
        ws.add_data_validation(dv)
        if last_data_row > header_row:
            dv.add(f"{col_letter}{header_row + 1}:{col_letter}{last_data_row}")

    _autofit_widths(ws, all_column_names, header_row)

    _write_instructions_sheet(wb, cfg, subtype)
    _write_field_definitions_sheet(wb, IDENTIFICATION_COLUMNS, fields)

    filename = _build_filename(cfg.label, project_name)
    return workbook_to_bytes(wb), filename


def _write_instructions_sheet(wb, cfg, subtype):
    ws = wb.create_sheet("INSTRUCTIONS")
    lines = [
        "PROCESS DATA REQUISITION - INSTRUCTIONS",
        "",
        f"Instrument Type: {cfg.label}" + (f" (Subtype: {subtype})" if subtype else ""),
        "",
        "1. The identification columns (S.NO, TAG NO, EQUIPMENT DESCRIPTION, P&ID NO., SERVICE,",
        "   EQUIPMENT NO, LINE, LINE SIZE) are derived automatically from the IODB.",
        "2. The process-data columns are intentionally left blank for the Process Engineering",
        "   team to fill in or confirm.",
        "3. Do not alter the identification columns.",
        "4. Fill all mandatory fields where known; leave fields blank only if the information",
        "   genuinely does not apply or is not yet available.",
        "5. Return the completed file to the Instrumentation Engineering team.",
    ]
    for i, line in enumerate(lines, start=1):
        ws.cell(row=i, column=1, value=line)
    ws.column_dimensions["A"].width = 90


def _write_field_definitions_sheet(wb, identification_columns, fields):
    ws = wb.create_sheet("FIELD DEFINITIONS")
    headers = ["Field Name", "Unit", "Data Type", "Mandatory", "Source"]
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
    r = 2
    for f in identification_columns:
        ws.cell(row=r, column=1, value=f.name)
        ws.cell(row=r, column=2, value=f.unit)
        ws.cell(row=r, column=3, value="Text")
        ws.cell(row=r, column=4, value="Yes" if f.mandatory else "No")
        ws.cell(row=r, column=5, value="IODB")
        r += 1
    for f in fields:
        ws.cell(row=r, column=1, value=f.name)
        ws.cell(row=r, column=2, value=getattr(f, "unit", ""))
        field_type = getattr(f, "field_type", "")
        ws.cell(row=r, column=3, value=field_type.value if hasattr(field_type, "value") else str(field_type))
        ws.cell(row=r, column=4, value="Yes" if getattr(f, "mandatory", False) else "No")
        ws.cell(row=r, column=5, value="Process Engineering")
        r += 1
    for col_letter, width in zip("ABCDE", (40, 12, 14, 12, 20)):
        ws.column_dimensions[col_letter].width = width
