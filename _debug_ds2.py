"""Minimal reproducer: calls generate_datasheets without catching exceptions,
so we see the full traceback."""
import sys, io, traceback
sys.path.insert(0, '/Users/adithyachoudhrym/ProjectIEZ')

import pandas as pd, openpyxl
from utils.file_handler import load_workbook_from_upload, workbook_to_bytes
from utils.generators import _copy_workbook

TMPL = 'Pressure Transmitter.xlsx'
IODB = 'IODB Source File.xlsx'

with open(IODB, 'rb') as f:
    iodb_buf = io.BytesIO(f.read())
with open(TMPL, 'rb') as f:
    tmpl_buf = io.BytesIO(f.read())

df = pd.read_excel(io.BytesIO(open(IODB,'rb').read()), sheet_name='IODB', header=0).dropna(how='all')
tags = df['TAG NO'].dropna().astype(str).str.strip().unique()[:2].tolist()

wb, buf_ref, err = load_workbook_from_upload(tmpl_buf)
print(f"Template loaded OK. buf_ref closed={buf_ref.closed if buf_ref else 'N/A'}")

# Simulate what generate_datasheets does
ANNEXURE_SHEET = next((s for s in wb.sheetnames if 'annexure' in s.lower()), None)
print(f"Annexure sheet: {ANNEXURE_SHEET}")

tmpl_ws = wb[ANNEXURE_SHEET]
print("Iterating template sheet (label scan)...")
count = 0
for row in tmpl_ws.iter_rows():
    for cell in row:
        count += 1
print(f"  Scanned {count} cells. buf_ref closed after scan: {buf_ref.closed if buf_ref else 'N/A'}")

print(f"\nNow copying workbook for tag 1 ({tags[0]})...")
try:
    new_wb = _copy_workbook(wb)
    print("  _copy_workbook OK")
except Exception as e:
    print(f"  _copy_workbook FAILED: {e}")
    traceback.print_exc()

print(f"\nbuf_ref closed after _copy_workbook: {buf_ref.closed if buf_ref else 'N/A'}")

print("\nNow calling workbook_to_bytes on copied wb...")
try:
    data = workbook_to_bytes(new_wb)
    print(f"  workbook_to_bytes OK: {len(data)} bytes")
except Exception as e:
    print(f"  workbook_to_bytes FAILED: {e}")
    traceback.print_exc()
