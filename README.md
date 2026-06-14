# iEZ - Instrumentation Engineering EZ

Modern React + FastAPI application for automated engineering document generation.

## 🏗️ Architecture

- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS
- **Backend**: FastAPI + SQLAlchemy + PostgreSQL
- **Auth**: JWT (access + refresh tokens)
- **Deployment**: Docker Compose

## 📦 Project Structure

```
iez/
├── backend/              # FastAPI application
│   ├── app/
│   │   ├── auth/        # Authentication (JWT, models, routes)
│   │   ├── models/      # Pydantic schemas
│   │   ├── routers/     # API endpoints (6 modules)
│   │   ├── main.py      # FastAPI app entry point
│   │   ├── config.py    # Settings
│   │   ├── database.py  # SQLAlchemy setup
│   │   └── deps.py      # Dependencies
│   ├── utils/           # Business logic (preserved from Streamlit)
│   └── requirements.txt
├── frontend/            # React application
│   ├── src/
│   │   ├── components/  # React components
│   │   ├── pages/       # Page components
│   │   ├── services/    # API client
│   │   ├── context/     # Auth context
│   │   └── types/       # TypeScript types
│   └── package.json
├── nginx/               # Reverse proxy config
└── docker-compose.yml   # Orchestration
```

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ (for local development)
- Python 3.11+ (for local development)

### Development Setup

1. **Clone and navigate to project**
   ```bash
   cd ProjectIEZ
   ```

2. **Start services with Docker Compose**
   ```bash
   docker-compose up -d
   ```

   This starts:
   - PostgreSQL (port 5432)
   - Backend API (port 8000)
   - Frontend dev server (port 3000)

3. **Access the application**
   - Frontend: http://localhost:3000
   - Backend API docs: http://localhost:8000/api/docs
   - Backend health: http://localhost:8000/health

4. **Create your first account**
   - Navigate to http://localhost:3000/register
   - Create an account
   - Login and access the dashboard

### Local Development (without Docker)

#### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Start PostgreSQL (via Docker)
docker run -d \
  --name iez-postgres \
  -e POSTGRES_USER=iez_user \
  -e POSTGRES_PASSWORD=iez_password \
  -e POSTGRES_DB=iez_db \
  -p 5432:5432 \
  postgres:16-alpine

# Run migrations (creates tables)
python -c "from app.database import init_db; init_db()"

# Start development server
uvicorn app.main:app --reload --port 8000
```

#### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

## 📚 API Documentation

### Authentication Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Create new user account |
| POST | `/api/auth/login` | Login and get tokens |
| POST | `/api/auth/refresh` | Refresh access token |
| GET | `/api/auth/me` | Get current user info |
| POST | `/api/auth/logout` | Logout (client-side) |

### Module Endpoints (Coming in Phases 1-3)

#### Phase 1 Modules (✅ Available Now)

**IODB Validator:**
- `POST /api/validator/validate` - Upload and validate IODB file
- `GET /api/validator/download/error-log` - Download validation report
- `GET /api/validator/download/highlighted` - Download highlighted IODB
- `GET /api/validator/download/tba` - Download TBA details
- `GET /api/validator/rules` - List dynamic validation rules
- `POST /api/validator/rules` - Create new dynamic rule
- `PUT /api/validator/rules/{rule_id}` - Update dynamic rule
- `PATCH /api/validator/rules/{rule_id}/toggle` - Toggle rule active status
- `DELETE /api/validator/rules/{rule_id}` - Delete dynamic rule

**Data Sheet Generator:**
- `POST /api/datasheet/tags` - Extract AI tags from IODB
- `POST /api/datasheet/generate` - Generate datasheets for selected tags
- `GET /api/datasheet/download` - Download generated datasheets ZIP

#### Phase 2-3 Modules (Coming Soon)

- `/api/instrument-list/*` - Instrument list
- `/api/io-list/*` - I/O list
- `/api/cable-schedule/*` - Cable schedule
- `/api/loop-wiring/*` - Loop wiring

Full API documentation available at: http://localhost:8000/api/docs

## 🔧 Configuration

### Environment Variables

Backend (`.env`):
```env
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql://iez_user:iez_password@postgres:5432/iez_db
DEBUG=True
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### Database Migrations

```bash
cd backend

# Generate migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## 🐳 Docker Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# Rebuild after code changes
docker-compose up -d --build

# Reset database
docker-compose down -v
docker-compose up -d
```

## 🧪 Testing

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm run test
```

## 📦 Production Deployment

1. **Build production images**
   ```bash
   docker-compose -f docker-compose.prod.yml build
   ```

2. **Set production environment variables**
   ```bash
   export SECRET_KEY=$(openssl rand -hex 32)
   export DATABASE_URL=postgresql://user:pass@prod-db:5432/iez
   export DEBUG=False
   ```

3. **Start production stack**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

## 🗺️ Migration Roadmap

### ✅ Phase 0: Foundation (COMPLETED)
- Backend: FastAPI + JWT auth + PostgreSQL
- Frontend: React + TypeScript + Tailwind + Auth flow
- Docker: Compose orchestration

### ✅ Phase 1: High-Value Modules (COMPLETED)
- **IODB Validator**: Full validation with dynamic rules CRUD, error metrics, download reports
- **Data Sheet Generator**: AI tag selection, fuzzy matching, batch generation with ZIP export

### 📋 Phase 2: List Generators (PLANNED)
- Instrument List
- I/O List

### 📋 Phase 3: Advanced Generators (PLANNED)
- Cable Schedule
- Loop Wiring

### 📋 Phase 4: Polish & Deploy (PLANNED)
- Production hardening
- CI/CD pipeline
- Documentation

## 🤝 Contributing

1. Create a feature branch
2. Make your changes
3. Write tests
4. Submit a pull request

## 📄 License

Proprietary - built by Akash B

## 🆘 Troubleshooting

### Port already in use
```bash
# Find and kill process using port 8000
lsof -ti:8000 | xargs kill -9

# Or change port in docker-compose.yml
```

### Database connection error
```bash
# Reset database
docker-compose down -v
docker-compose up -d postgres
sleep 5
docker-compose up -d backend
```

### Frontend not connecting to backend
- Check CORS origins in `backend/app/config.py`
- Verify proxy settings in `frontend/vite.config.ts`

## 📞 Support

For issues and questions, contact: Akash B

---

**Version**: iEz 1.0  
**Built by**: Akash B
