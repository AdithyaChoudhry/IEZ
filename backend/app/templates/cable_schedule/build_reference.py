"""
One-off builder for cable_schedule_reference.xlsx - the engineering reference layouts used by the
extra cable-schedule sheets (MCC DI, MCC DO, VFD, MOV, LCP).

    python build_reference.py "<path to 10P155-I0010-2101(DIGHA).xlsx>"

Keeps, per reference sheet, only the header block and the FIRST data block (the style/formula prototype);
every project value in that block is blanked. Formulas, separators and fixed texts stay.
"""
import re
import sys

import openpyxl

KEEP = {            # sheet -> (last header row, last row of the first data block)
    "MCC-DI": (10, 21),
    "MCC-DO": (10, 14),
    "VFD": (10, 16),
    "LCP": (10, 17),
    "MOV Cable (2)": (11, 18),
}
# literal cells that are project data in the Digha file (everything else literal in the prototype is a fixed text)
DATA_COLS_NOTE = "values below the header that are not formulas and not in FIXED are blanked"
TITLE_LABELS = {"DOCUMENT TITLE", "CLIENT", "PROJECT", "DOC NO.", "REV NO.", "DATE", "PREPARED BY", "CHECKED BY", "APPROVED BY"}
FIXED = re.compile(r"^(PLC ?|CCD|[−/\-]|\(\+\)|\(-\)|TB|IC-|MOV|sh|1\" ?(NPT|ET))$")


def main(src, dst):
    wb = openpyxl.load_workbook(src, keep_links=False)
    for name in list(wb.sheetnames):
        if name not in KEEP:
            del wb[name]
    for name, (hdr_end, blk_end) in KEEP.items():
        ws = wb[name]
        for rng in list(ws.merged_cells.ranges):
            if rng.min_row > blk_end:
                ws.unmerge_cells(str(rng))
        for row in ws.iter_rows(min_row=blk_end + 1, max_row=ws.max_row):
            for c in row:
                c.value = None
                c.style = "Normal"
        for r in list(ws.row_dimensions):
            if r > blk_end:
                del ws.row_dimensions[r]
        for row in ws.iter_rows(min_row=1, max_row=blk_end):
            for c in row:
                v = c.value
                if v is None or type(c).__name__ == "MergedCell":
                    continue
                if c.row <= hdr_end:
                    if c.row in (4, 5, 6) and not (isinstance(v, str) and v.strip().upper() in TITLE_LABELS):
                        c.value = None                      # title block values: filled per project at generation
                    continue
                if isinstance(v, str) and v.startswith("="):
                    continue
                if isinstance(v, str) and FIXED.match(v.strip()):
                    continue
                c.value = None
        ws.print_area = None
    wb.save(dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "cable_schedule_reference.xlsx")
