# ProjectIEZ (iEZ – Instrumentation Engineering EZ)

Engineering document generation app. FastAPI backend + React/Vite/TS/Tailwind frontend. See README.md, DEPLOY.md, QUICKSTART.md, TESTING_GUIDE.md.

## Layout
- `backend/app/routers/` – one router per module (datasheet, coversheet, io_list, instrument_list, loop_wiring, cable_schedule, lt_radar, sdie, tbe, validator, approvals, idc/idc_ws, admin_users, deploy, ...)
- `backend/app/models/` – Pydantic schemas; `backend/app/auth/` – JWT auth
- `utils/` – shared business logic (datasheet/coversheet generators, sdie_extractor, template_processor, dynamic_rules, datasheet_kb.json)
- `frontend/src/components/modules/` – one component per module
- Root `generate_*.py` / `*.pptx` – one-off presentation scripts and outputs, not part of the app
- Root `*.xlsx` – sample input/template files; `_test_*.py`, `_debug_*.py` – ad hoc scripts

## Notes (from git history)
- Vendor DB lives in SQLite with CRUD UI (228 vendors, 15 instrument types); Vendor TBE has Mode 2 (technical offer compliance).
- IDC (Inter Discipline Check) module is hidden from sidebar/dashboard but the component is kept.
- Deployed via a deploy webhook (`routers/deploy.py`) to a server running `iez.service`; deploy does git pull, npm install, pip install.
- Login Activity admin screen lists the full user roster (Twilio SMS alerts were added then reverted).
- Wizard/cover-sheet state is persisted to sessionStorage.

## Uncommitted work at 2026-10-08
IO List / Instrument List generators (backend routers, `list_generator.py`, frontend components), `utils/sdie_extractor.py`, `utils/template_processor.py`, requirements.txt.
