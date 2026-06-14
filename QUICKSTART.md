# 🚀 Quick Start Guide - iEZ Migration

## What We Built (Phase 0: Foundation)

✅ Complete **React + TypeScript + Tailwind** frontend  
✅ Complete **FastAPI + PostgreSQL** backend with JWT authentication  
✅ **Docker Compose** orchestration for easy development  
✅ Protected routes and auth flow  
✅ Responsive layout with Header + Sidebar  
✅ Module placeholders ready for implementation

---

## Start the Application (3 Steps)

### 1. Navigate to Project
```bash
cd /Users/adithyachoudhrym/ProjectIEZ
```

### 2. Start All Services
```bash
docker-compose up -d
```

This starts:
- 🐘 PostgreSQL database (port 5432)
- 🐍 FastAPI backend (port 8000)
- ⚛️  React frontend (port 3000)

### 3. Open Browser
```
http://localhost:3000
```

---

## First Time Setup

### Create Your Account

1. Click **"Sign up"** on the login page
2. Fill in:
   - Email: your.email@example.com
   - Username: your_username
   - Password: (min 8 characters)
3. Click **"Create Account"**
4. You'll be auto-logged in and see the dashboard

### Test the API

Backend API docs:
```
http://localhost:8000/api/docs
```

Health check:
```
http://localhost:8000/health
```

---

## Development Workflow

### View Logs
```bash
# All services
docker-compose logs -f

# Just backend
docker-compose logs -f backend

# Just frontend
docker-compose logs -f frontend
```

### Restart After Code Changes

Backend changes (Python files):
```bash
docker-compose restart backend
```

Frontend changes (React files):
- Hot reload is automatic! Just save the file.

### Stop Services
```bash
docker-compose down
```

### Reset Database
```bash
docker-compose down -v
docker-compose up -d
```

---

## Project Structure

```
ProjectIEZ/
├── backend/                 # FastAPI application
│   ├── app/
│   │   ├── auth/           # JWT authentication
│   │   ├── main.py         # FastAPI entry point
│   │   ├── database.py     # PostgreSQL connection
│   │   └── deps.py         # Auth dependencies
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                # React application
│   ├── src/
│   │   ├── pages/          # Login, Register, Dashboard
│   │   ├── components/     # Header, Sidebar, Layout
│   │   ├── services/       # API client
│   │   └── context/        # Auth context
│   ├── package.json
│   └── Dockerfile
│
├── utils/                   # Existing business logic (PRESERVED)
├── docker-compose.yml
└── README.md
```

---

## What's Working Right Now

### ✅ Authentication System
- Register new users
- Login with username/password
- JWT access + refresh tokens
- Protected routes
- Auto token refresh
- Logout

### ✅ UI Components
- Responsive header with user menu
- Collapsible sidebar navigation
- Dashboard with module cards
- Login/Register pages
- Protected route handling

### ✅ Infrastructure
- PostgreSQL database with users table
- FastAPI REST API with OpenAPI docs
- Docker Compose orchestration
- CORS configured
- Hot reload for development

### ✅ IODB Validator Module (Phase 1)
- **File Upload**: Upload IODB Excel files
- **Validation Engine2)

### Module Implementation Priority

1. **Instrument List Generator**
   - Column selection
   - Per-column filters
   - Template support
   
2. **I/O List Generator**
   - Signal-focused columns
   - Multi-filter logic
   - Excel export

**Phase 3**: Cable Schedule + Loop Wiring modules

---

## Testing Phase 1 Modules

### Test IODB Validator

1. Navigate to **IODB Validator** from the sidebar
2. Click "Show Dynamic Rules Manager" to explore rule management
3. Upload an IODB Excel file
4. (Optional) Enable "Auto-correct spelling"
5. Click "Run Validation"
6. Review error metrics and grouped errors
7. Download the three report files:
   - Error Log (Excel)
   - Highlighted IODB (Excel with color-coded errors)
   - TBA Details (Excel)

**Test Dynamic Rules:**
1. Click "Add Rule" in the Dynamic Rules Manager
2. Create a COLUMN rule:
   - Name: "Test Power Supply"
   - Rule Type: COLUMN
   - Condition: `POWER SUPPLY` == `24V DC`
   - Error Message: "Must be 24V DC"
3. Save and toggle the rule active
4. Re-run validation to see the rule in action

### Test Data Sheet Generator

1. Navigate to **Data Sheet** from the sidebar
2. Upload your IODB source file
3. Upload your Datasheet template (must have "Datasheet" sheet with headings in column D)
4. Check/uncheck "Two-row combined header" based on your IODB format
5. Adjust "Fuzzy Match Threshold" (70% recommended)
6. Click "Load AI Tags" button
7. Select tags you want to generate datasheets for
8. Click "Generate Datasheets"
9. Wait for completion (progress shown)
10. Click "Download" to get the ZIP file
11. Click "Show Details" in Mapping Log to see which columns matched

**Expected Output**: ZIP file containing one Excel file per selected tag, with data populated from IODB using fuzzy matching.
### ✅ Data Sheet Generator Module (Phase 1)
- **File Upload**: IODB source + Datasheet template
- **AI Tag Extraction**: Automatically detect AI signal type tags
- **Tag Selection**: Multi-select with Select All / Deselect All
- **Fuzzy Matching**: Configurable threshold (30-100%) for column name matching
- **Batch Generation**: Generate multiple datasheets as single ZIP file
- **Mapping Log**: View matched/unmatched columns with scores
- **Progress Tracking**: Visual feedback during generation
- **Two-Row Header Support**: Handle complex IODB header formats

---

## Next Steps (Phase 1)

### Module Implementation Priority

1. **IODB Validator** (highest value)
   - Backend: `/api/validator/validate` endpoint
   - Frontend: File upload + error display
   - Dynamic rules CRUD

2. **Data Sheet Generator**
   - Backend: `/api/datasheet/generate` endpoint
   - Frontend: Tag selection + fuzzy matching UI
   - WebSocket for progress

---

## Troubleshooting

### Ports Already in Use
```bash
# Check what's using port 8000
lsof -ti:8000 | xargs kill -9

# Check what's using port 3000
lsof -ti:3000 | xargs kill -9
```

### Can't Connect to Database
```bash
# Reset everything
docker-compose down -v
docker-compose up -d
```

### Frontend Not Loading
```bash
# Rebuild frontend
docker-compose up -d --build frontend
```

### Backend Errors
```bash
# View backend logs
docker-compose logs backend

# Restart backend
docker-compose restart backend
```

---

## Testing the Setup

### 1. Test Backend Health
```bash
curl http://localhost:8000/health
```

Expected: `{"status":"healthy"}`

### 2. Test Registration
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "password": "password123"
  }'
```

### 3. Test Login
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "password123"
  }'
```

Expected: JSON with `access_token` and `refresh_token`

---

## Development Tips

### Backend Development
- API auto-reloads on file save
- View API docs: http://localhost:8000/api/docs
- Query database:
  ```bash
  docker exec -it iez-postgres psql -U iez_user -d iez_db
  ```

### Frontend Development
- Hot reload enabled (automatic)
- Access from: http://localhost:3000
- React DevTools supported

### Adding New API Endpoints
1. Create router in `backend/app/routers/`
2. Add Pydantic models in `backend/app/models/`
3. Register router in `backend/app/main.py`

### Adding New React Pages
1. Create component in `frontend/src/pages/`
2. Add route in `frontend/src/App.tsx`
3. Add nav item in `frontend/src/components/layout/Sidebar.tsx`

---

## Common Commands

```bash
# Start everything
docker-compose up -d

# Stop everything
docker-compose down

# View logs
docker-compose logs -f

# Rebuild after changes
docker-compose up -d --build

# Reset database
docker-compose down -v && docker-compose up -d

# Install new Python package
docker-compose exec backend pip install <package>

# Install new npm package
docker-compose exec frontend npm install <package>

# Run tests
docker-compose exec backend pytest
docker-compose exec frontend npm test
```

---

## Ready to Start Development!

Your migration foundation is complete. The existing Streamlit app in `main.py` is **still working** while you build the new React frontend module by module.

**Start here**: 
```bash
docker-compose up -d
```

Then open: http://localhost:3000

Happy coding! 🎉
