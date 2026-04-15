"""Direct test: call generate_datasheets directly without catching exceptions."""
import sys, io
sys.path.insert(0, '/Users/adithyachoudhrym/ProjectIEZ')

import pandas as pd
from utils.file_handler import load_workbook_from_upload
from utils.generators import generate_datasheets

TMPL = 'Pressure Transmitter.xlsx'
IODB = 'IODB Source File.xlsx'

with open(IODB, 'rb') as f:
    iodb_data = f.read()
with open(TMPL, 'rb') as f:
    tmpl_data = f.read()

df = pd.read_excel(io.BytesIO(iodb_data), sheet_name='IODB', header=0).dropna(how='all')
tags = df['TAG NO'].dropna().astype(str).str.strip().unique()[:2].tolist()
print(f"Tags: {tags}")

wb, buf_ref, err = load_workbook_from_upload(io.BytesIO(tmpl_data))
assert err is None and wb is not None, f"load failed: {err}"
print(f"Template loaded. Sheets: {wb.sheetnames}")

# Call WITHOUT the try/except wrapper so we see the real traceback
import traceback
try:
    results, err = generate_datasheets(df, wb, 'TAG NO', tags)
    if err:
        print(f"returned error: {err}")
    else:
        print(f"OK: {len(results)} datasheets generated")
        print(f"  first: {results[0][1]} ({len(results[0][0])} bytes)")
except Exception:
    print("EXCEPTION:")
    traceback.print_exc()
