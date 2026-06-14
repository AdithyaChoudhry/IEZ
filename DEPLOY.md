# Deployment Guide — Render (backend) + Netlify (frontend)

This project deploys as two independent services:

- **Backend** (FastAPI + Postgres) → [Render](https://render.com)
- **Frontend** (React/Vite static site) → [Netlify](https://netlify.com)

---

## 1. Backend on Render

### 1.1 Create a Postgres database
1. In the Render dashboard: **New → PostgreSQL**.
2. Name it (e.g. `iez-db`), choose a region, free/starter plan.
3. Once created, copy the **Internal Database URL** (starts with `postgresql://...`).

### 1.2 Create the web service
1. **New → Web Service** → connect this GitHub repo.
2. Settings:
   - **Runtime**: Docker
   - **Dockerfile path**: `backend/Dockerfile`
   - **Docker build context directory**: `.` (repo root — required so the build can `COPY utils/` alongside `backend/`)
   - **Region**: same as the database, for low latency
3. **Environment variables**:
   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the Internal Database URL from step 1.1 |
   | `SECRET_KEY` | generate a new random secret, e.g. `openssl rand -hex 32` |
   | `DEBUG` | `False` |
   | `CORS_ORIGINS` | `https://<your-netlify-site>.netlify.app` (comma-separate if you add a custom domain later) |
4. Deploy. Render will build the image and run `uvicorn app.main:app --host 0.0.0.0 --port 8000` (from the Dockerfile `CMD`).
5. Once live, note the backend URL, e.g. `https://iez-backend.onrender.com`. Confirm it's healthy:
   ```bash
   curl https://iez-backend.onrender.com/health
   ```

### 1.3 Database migrations
If the app uses Alembic migrations, run them once against the new database (via Render's shell/job, or locally with `DATABASE_URL` pointed at the Render Postgres External URL).

---

## 2. Frontend on Netlify

### 2.1 Site setup
1. In Netlify: **Add new site → Import an existing project** → connect this repo.
2. Build settings (also defined in `frontend/netlify.toml`):
   - **Base directory**: `frontend`
   - **Build command**: `npm run build`
   - **Publish directory**: `frontend/dist`

### 2.2 Environment variable
Set in Netlify **Site configuration → Environment variables**:

| Key | Value |
|---|---|
| `VITE_API_URL` | `https://iez-backend.onrender.com/api` (your Render backend URL + `/api`) |

This is read by `frontend/src/services/api.ts` as the axios `baseURL`. If unset, the app falls back to relative `/api` (only correct when frontend and backend share an origin, e.g. local dev via the Vite proxy).

### 2.3 Deploy
Trigger a deploy. Netlify builds with `npm run build` and serves `dist/`. The `[[redirects]]` rule in `netlify.toml` sends all paths to `index.html` so React Router's client-side routes work on refresh/deep-link.

### 2.4 Update backend CORS
Once you know the final Netlify URL (e.g. `https://iez-app.netlify.app`), update the Render backend's `CORS_ORIGINS` env var to include it, then redeploy the backend.

---

## 3. Post-deploy checklist
- [ ] `GET https://<backend>/health` returns `{"status":"healthy"}`
- [ ] Netlify site loads, login/register works
- [ ] Each module (IODB Validator, Instrument List, I/O List, Data Sheet, Cover Sheet, Cable Schedule, Loop Wiring) can upload a file and download a generated `.xlsx`
- [ ] Browser console has no CORS errors
