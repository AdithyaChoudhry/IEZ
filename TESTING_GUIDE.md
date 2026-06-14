# Starting iEZ with Phase 1 Modules

## Prerequisites Check

Before starting, ensure you have:
- [ ] Docker Desktop running
- [ ] Ports 3000, 5432, 8000 available
- [ ] At least 2GB free RAM
- [ ] Sample IODB Excel file ready
- [ ] Datasheet template file ready (optional)

---

## Step-by-Step Startup

### 1. Copy Utils Folder to Backend

The backend needs access to the existing business logic:

```bash
cd /Users/adithyachoudhrym/ProjectIEZ

# Create a symlink (recommended)
ln -s "$(pwd)/utils" "$(pwd)/backend/utils"

# OR copy the folder (alternative)
# cp -r utils backend/utils
```

**Why?** The validator and datasheet routers import from `utils/` to reuse existing functions.

---

### 2. Start Docker Services

```bash
# Start all services in detached mode
docker-compose up -d

# View logs (follow mode)
docker-compose logs -f
```

**Expected output:**
```
iez-postgres  | database system is ready to accept connections
iez-backend   | 🚀 Starting iEZ API...
iez-backend   | ✅ Database initialized
iez-backend   | INFO: Uvicorn running on http://0.0.0.0:8000
iez-frontend  | VITE ready in 1234 ms
```

---

### 3. Verify Services

Open three terminal windows:

**Terminal 1: Check Backend Health**
```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy"}
```

**Terminal 2: Check API Docs**
```bash
open http://localhost:8000/api/docs
# Should show FastAPI Swagger UI with validator/datasheet endpoints
```

**Terminal 3: Check Frontend**
```bash
open http://localhost:3000
# Should show iEZ login page
```

---

### 4. Create Test Account

1. Go to http://localhost:3000/register
2. Fill in:
   - **Email**: test@iez.com
   - **Username**: testuser
   - **Password**: password123
3. Click "Create Account"
4. You'll be auto-redirected to the dashboard

---

## Testing Phase 1 Modules

### A. IODB Validator (5-10 minutes)

#### Basic Validation Flow

1. **Navigate**: Click "IODB Validator" in sidebar
2. **Upload File**: 
   - Click file input
   - Select your IODB Excel file
   - ✓ Check "Auto-correct spelling" if desired
3. **Run Validation**: Click "Run Validation" button
4. **Review Results**:
   - See 6 metric cards (Total, Empty, Logic, Order, Spelling, Dynamic)
   - Expand row sections to see detailed errors
   - Note the color coding and rule types
5. **Download Reports**:
   - Click "Error Log (Excel)" → saves `IODB_Validation_Report.xlsx`
   - Click "Highlighted IODB" → saves `IODB_Highlighted.xlsx` (color-coded cells)
   - Click "TBA Details" → saves `TBA_details.xlsx`

#### Dynamic Rules Testing

6. **Open Rules Manager**: Click "Show Dynamic Rules Manager"
7. **Create a COLUMN Rule**:
   - Click "Add Rule"
   - Name: `Test Hazardous Area Check`
   - Rule Type: `COLUMN`
   - Condition 1:
     - Column: `AREA CLASSIFICATION`
     - Operator: `equals`
     - Value: `HAZARDOUS`
   - Error Message: `Hazardous area requires special handling`
   - Priority: 100
   - Click "Save Rule"
8. **Toggle Rule**: Click the toggle switch to activate
9. **Re-run Validation**: Upload file again and validate
10. **Verify**: Check if new dynamic rule errors appear with blue "Dynamic" badge

#### Advanced Rules Testing

11. **Create a ROW Rule** (multi-column logic):
    - Click "Add Rule"
    - Name: `Power Supply Check for Hazardous`
    - Rule Type: `ROW`
    - Condition 1:
      - Column: `AREA CLASSIFICATION`
      - Operator: `equals`
      - Value: `HAZARDOUS`
    - Click "+ Add Condition"
    - Condition 2:
      - Logic: `AND`
      - Column: `POWER SUPPLY`
      - Operator: `not equals`
      - Value: `24V DC`
    - Target Column: `POWER SUPPLY`
    - Error Message: `Hazardous instruments must use 24V DC`
    - Save
12. **Create a DUPLICATE Rule**:
    - Name: `Duplicate Tag Detector`
    - Rule Type: `DUPLICATE`
    - Column to check: `TAG NO`
    - Error Message: `Duplicate tag number found`
    - Save

13. **Test Rule Management**:
    - Edit a rule (click pencil icon)
    - Toggle a rule off/on (switch)
    - Delete a rule (trash icon)

---

### B. Data Sheet Generator (10-15 minutes)

#### File Preparation Flow

1. **Navigate**: Click "Data Sheet" in sidebar
2. **Upload IODB Source**:
   - Select your IODB Excel file
   - ✓ Check "Two-row combined header" if your IODB has a two-row header
3. **Upload Template**:
   - Select your Datasheet template Excel file
   - Template must have a sheet named "Datasheet"
   - Headings should be in column D

#### Tag Selection Flow

4. **Load Tags**:
   - Click "Load AI Tags" button
   - Wait for processing (~2-5 seconds)
   - Review the count (e.g., "42 AI tags found")
5. **Select Tags**:
   - Option A: Click "Select All" to pick all tags
   - Option B: Manually check individual tags
   - Option C: Check a subset, then "Deselect All" and reselect
6. **Verify Selection**: Bottom text shows "X tag(s) selected → will generate X datasheet(s)"

#### Fuzzy Matching Configuration

7. **Adjust Threshold**:
   - Move slider to 70% (recommended default)
   - Lower = more matches (but less accurate)
   - Higher = fewer matches (but more strict)

#### Generation Flow

8. **Generate**:
   - Click "Generate Datasheets" button
   - Progress indicator shows "Generating X Datasheets..."
   - Wait for completion (5-30 seconds depending on tag count)
9. **Review Success Message**:
   - Green success box appears
   - Shows filename (e.g., `Datasheets_20260522_143022.zip`)
   - Tag count confirmation
10. **Download ZIP**:
    - Click "Download" button in green success box
    - ZIP file contains one Excel per tag

#### Mapping Log Review

11. **Open Mapping Log**:
    - Click "Show Details"
    - See table with all heading matches
12. **Understand Columns**:
    - **Tag**: Instrument tag
    - **Heading**: Template heading from column D
    - **IODB Column**: Matched IODB column name
    - **Score**: Fuzzy match score (0-100)
    - **Value**: Actual value populated
    - **Status**: MATCHED (green) or UNMATCHED (orange)
13. **Analyze Results**:
    - Green rows = successful matches
    - Orange rows = no match found (left blank in datasheet)
    - Low scores (<70) = weak matches (verify manually)

---

## Troubleshooting

### Problem: "Cannot connect to backend"

**Symptoms**: Frontend shows network errors, login fails

**Solutions**:
```bash
# Check if backend is running
docker-compose ps

# View backend logs
docker-compose logs backend

# Restart backend
docker-compose restart backend

# Full restart
docker-compose down && docker-compose up -d
```

---

### Problem: "No AI tags found"

**Symptoms**: Data Sheet Generator shows "0 AI tags found"

**Causes**:
1. IODB doesn't have "SIGNAL I/O TYPE" column
2. No rows have "AI" in the signal type column
3. Wrong two-row header setting

**Solutions**:
- Verify your IODB has the column
- Toggle the "Two-row combined header" checkbox
- Check that at least one row has "AI" signal type

---

### Problem: "Validation failed" or "Generation failed"

**Symptoms**: Error alert after clicking validate/generate

**Solutions**:
```bash
# Check backend logs for detailed error
docker-compose logs backend | tail -50

# Common issues:
# - File too large (>50MB)
# - Missing required columns
# - Corrupted Excel file
# - Template missing "Datasheet" sheet
```

---

### Problem: "Dynamic rules not working"

**Symptoms**: Created rules don't appear in validation results

**Checklist**:
- [ ] Rule is toggled ON (green switch)
- [ ] Column name exactly matches IODB (case-sensitive if checked)
- [ ] Operator matches data type (e.g., don't use "contains" on numeric columns)
- [ ] Rule priority is set
- [ ] Re-upload file after creating rule

**Debug**:
```bash
# Check if rules are saved
ls -la dynamic_rules.json

# View rules JSON
cat dynamic_rules.json | python -m json.tool
```

---

### Problem: Port conflicts

**Symptoms**: "Port 3000 is already in use"

**Solutions**:
```bash
# Find and kill process using port 3000
lsof -ti:3000 | xargs kill -9

# Or use different ports in docker-compose.yml
ports:
  - "3001:3000"  # Change external port
```

---

### Problem: Database connection error

**Symptoms**: Backend shows "could not connect to PostgreSQL"

**Solutions**:
```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Restart database
docker-compose restart postgres

# Wait 10 seconds, then restart backend
sleep 10
docker-compose restart backend

# Nuclear option: reset everything
docker-compose down -v
docker-compose up -d
```

---

## Performance Tips

### For Large IODB Files (1000+ rows)

1. **Increase timeout** in `backend/app/config.py`:
   ```python
   MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB
   ```

2. **Use fewer dynamic rules** (each rule adds processing time)

3. **Disable auto-correct** if not needed (spelling check is slow)

### For Many Datasheets (50+ tags)

1. **Select in batches** (e.g., 25 tags at a time)

2. **Lower fuzzy threshold** to 60-65% for faster matching

3. **Use simpler templates** (fewer formulas = faster generation)

---

## Quick Reference: API Endpoints

### Validator
```bash
# Validate IODB
curl -X POST http://localhost:8000/api/validator/validate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@path/to/iodb.xlsx" \
  -F "auto_correct_spelling=false"

# List rules
curl http://localhost:8000/api/validator/rules \
  -H "Authorization: Bearer YOUR_TOKEN"

# Create rule
curl -X POST http://localhost:8000/api/validator/rules \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Rule",
    "rule_type": "COLUMN",
    "conditions": [{"column": "TAG NO", "operator": "!=", "value": "", "logical_operator": "AND"}],
    "error_message": "TAG NO cannot be empty",
    "priority": 100
  }'
```

### Datasheet
```bash
# Get AI tags
curl -X POST http://localhost:8000/api/datasheet/tags \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@path/to/iodb.xlsx" \
  -F "two_row_header=true"

# Generate datasheets
curl -X POST http://localhost:8000/api/datasheet/generate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "iodb_file=@path/to/iodb.xlsx" \
  -F "template_file=@path/to/template.xlsx" \
  -F 'selected_tags=["TAG001", "TAG002"]' \
  -F "two_row_header=true" \
  -F "fuzzy_threshold=70"
```

---

## Logs & Monitoring

### View All Logs
```bash
docker-compose logs -f
```

### Filter Specific Service
```bash
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f postgres
```

### Search Logs for Errors
```bash
docker-compose logs backend | grep ERROR
docker-compose logs backend | grep CRITICAL
```

### Check Resource Usage
```bash
docker stats
```

---

## Clean Shutdown

```bash
# Stop all services
docker-compose down

# Remove volumes (resets database)
docker-compose down -v

# Remove images
docker-compose down --rmi all
```

---

## Success Indicators

You'll know everything is working when:

✅ All 3 containers show "healthy" status  
✅ http://localhost:3000 loads the login page  
✅ http://localhost:8000/api/docs shows 15+ endpoints  
✅ You can register, login, and see the dashboard  
✅ IODB Validator shows metric cards after validation  
✅ Data Sheet Generator loads AI tags successfully  
✅ Downloaded files open correctly in Excel  

**Ready to test!** 🚀
