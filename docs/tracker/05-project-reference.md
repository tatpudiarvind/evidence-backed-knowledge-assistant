# Project reference

**Last updated:** 2026-10-26 · **Status legend:** see [README.md](README.md#status-legend)

Reference data for the current code. Update it whenever files, dependencies, or configuration change.

## 1. File inventory

| Path | Purpose | Status | Remarks |
|---|---|---|---|
| `README.md` | Project specification (source of truth) and Phase 1 quickstart | ✅ | — |
| `.env.example` | Template for local configuration | ✅ | Copy to `.env`; never commit `.env` |
| `.gitignore` | Ignores secrets, virtual environments, caches, build output, local data | ✅ | Also keeps `docs/tracker/04-skills-evidence.md` local (D-21) |
| `compose.yaml` | Local stack: `db`, `backend`, `frontend` | 🟡 | Never run (B-01) |
| `.github/workflows/ci.yml` | CI for backend and frontend | ✅ | The first run on GitHub passed (V-21); action-version warnings (I-17) |
| `docs/tracker/` | This tracker (6 files) | ✅ | `04-skills-evidence.md` is local only and not published (D-21) |
| `backend/pyproject.toml` | Package metadata, pinned dependencies, Ruff/mypy/pytest configuration | ✅ | — |
| `backend/Dockerfile`, `backend/.dockerignore` | Dev image (Python 3.12) | 🟡 | Never built |
| `backend/alembic.ini` | Alembic configuration | ✅ | The URL is overridden in `env.py` |
| `backend/alembic/env.py` | Migration runner; reads the database URL from app settings | ✅ | — |
| `backend/alembic/script.py.mako` | Template for new migrations | ✅ | — |
| `backend/alembic/versions/0001_enable_pgvector.py` | Enables the `vector` extension | ✅ Offline only | Live apply pending (P1-19) |
| `backend/app/main.py` | FastAPI app, CORS middleware, router registration | ✅ | — |
| `backend/app/api/router.py` | Combines API routers | ✅ | — |
| `backend/app/api/health.py` | `/health/live` and `/health/ready` | ✅ | — |
| `backend/app/core/config.py` | Settings from environment variables and `.env` | ✅ | Formatting drift (I-09) |
| `backend/app/core/database.py` | Cached SQLAlchemy engine; `SELECT 1` check | ✅ | — |
| `backend/app/db/base.py` | SQLAlchemy `DeclarativeBase` for future models | ✅ | No models yet |
| `backend/app/__init__.py`, `backend/app/api/__init__.py`, `backend/app/core/__init__.py`, `backend/app/db/__init__.py` | Package markers | ✅ | — |
| `backend/tests/test_health.py` | 3 health endpoint tests | ✅ | Database mocked |
| `frontend/package.json`, `frontend/package-lock.json` | Pinned dependencies, scripts, lockfile | ✅ | I-10. The lockfile records no registry URLs (D-19) |
| `frontend/.npmrc` | Keeps registry URLs out of `package-lock.json` (`omit-lockfile-registry-resolved=true`) | ✅ | D-19; installs work from any npm registry |
| `frontend/Dockerfile`, `frontend/.dockerignore` | Dev image (Node 22, Vite dev server) | 🟡 | Never built |
| `frontend/index.html` | HTML entry point | ✅ | — |
| `frontend/vite.config.ts` | Vite and Vitest (jsdom) configuration | ✅ | — |
| `frontend/tsconfig.json` | Strict TypeScript configuration | ✅ | — |
| `frontend/eslint.config.js` | ESLint flat configuration | ✅ | — |
| `frontend/src/main.tsx` | React entry point | ✅ | — |
| `frontend/src/App.tsx` | Landing page and readiness indicator | ✅ | — |
| `frontend/src/lib/api.ts` | Typed API client with runtime validation | ✅ | — |
| `frontend/src/styles.css` | Styles (system fonts) | ✅ | — |
| `frontend/src/App.test.tsx` | Component test | ✅ | — |
| `frontend/src/test/setup.ts` | Test setup (jest-dom matchers) | ✅ | — |
| `backend/.venv/` | Local Python 3.14 virtual environment | Local only | Git-ignored; recreate at any time |
| `frontend/node_modules/` | Local npm packages | Local only | Git-ignored; recreate with `npm ci` |

## 2. Backend dependencies (`backend/pyproject.toml`)

| Package | Version | Scope | Purpose | Remarks |
|---|---|---|---|---|
| fastapi | 0.115.12 | Runtime | Web framework | Deprecation warnings on Python 3.14 (I-04) |
| uvicorn[standard] | 0.34.2 | Runtime | ASGI server | Extras include watchfiles (used by `--reload`) |
| pydantic-settings | 2.9.1 | Runtime | Typed settings from environment and `.env` | — |
| sqlalchemy | 2.0.41 | Runtime | Database access and ORM | — |
| alembic | 1.16.1 | Runtime | Migrations | — |
| psycopg[binary] | 3.2.10 | Runtime | PostgreSQL driver | 3.2.9 had no Python 3.14 binary wheel |
| pgvector | 0.4.1 | Runtime | pgvector types for SQLAlchemy | Not used yet; pulls in numpy |
| httpx | 0.28.1 | Dev | Transport for the FastAPI test client | — |
| pytest | 8.4.0 | Dev | Tests | — |
| mypy | 1.16.0 | Dev | Static type checking (strict) | — |
| ruff | 0.11.13 | Dev | Linting and formatting | — |
| setuptools | 80.9.0 | Build | Build backend | — |

## 3. Frontend dependencies (`frontend/package.json`)

| Package | Version | Scope | Purpose | Remarks |
|---|---|---|---|---|
| react, react-dom | 19.1.0 | dependencies | UI library | — |
| vite | 6.4.5 | dependencies | Dev server and bundler | Should be a devDependency (I-10); upgraded from 6.3.5 |
| @vitejs/plugin-react | 4.5.0 | dependencies | React support for Vite | Should be a devDependency (I-10) |
| typescript | 5.8.3 | devDependencies | Type checking | — |
| eslint | 10.13.0 | devDependencies | Linting | Upgraded from 9.28.0 |
| @eslint/js | 10.0.1 | devDependencies | Recommended ESLint rules | — |
| typescript-eslint | 8.72.0 | devDependencies | TypeScript lint rules | — |
| globals | 16.2.0 | devDependencies | Browser globals for ESLint | — |
| vitest | 4.1.12 | devDependencies | Test runner | Upgraded from 3.2.4 to clear audit findings |
| jsdom | 26.1.0 | devDependencies | DOM for tests | — |
| @testing-library/react | 16.3.0 | devDependencies | Component testing | — |
| @testing-library/jest-dom | 6.6.4 | devDependencies | DOM matchers | — |
| @types/react, @types/react-dom | 19.1.6 | devDependencies | Type definitions | — |
| @types/node | 22.15.30 | devDependencies | Node.js types for config files | — |

## 4. Runtime images and toolchain

| Component | Version | Where used | Remarks |
|---|---|---|---|
| PostgreSQL with pgvector | `pgvector/pgvector:0.8.0-pg16` | Compose `db` service | PostgreSQL 16 with pgvector 0.8.0 |
| Python | `python:3.12-slim` image; 3.12 in CI | Backend Dockerfile; CI backend job | — |
| Node.js | `node:22-alpine` image; 22 in CI | Frontend Dockerfile; CI frontend job | — |
| GitHub Actions | `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4` | CI on `ubuntu-latest` | — |
| Local Python | 3.14.0 | This machine | I-03 |
| Local Node.js and npm | v24.18.1 and 11.16.0 | This machine | — |

## 5. Environment variables

| Variable | Default | Used by | In `.env.example`? | Remarks |
|---|---|---|---|---|
| `POSTGRES_DB` | `knowledge_assistant` | Compose (`db` and the backend URL) | ✅ | — |
| `POSTGRES_USER` | `knowledge_assistant` | Compose | ✅ | — |
| `POSTGRES_PASSWORD` | `local_dev_only` | Compose | ✅ | Local development only; change it before sharing a host |
| `POSTGRES_PORT` | `5432` | Compose host port for `db` | ❌ | I-08 |
| `API_PORT` | `8000` | Compose host port; frontend API URL | ✅ | — |
| `WEB_PORT` | `5173` | Compose host port; CORS origin | ✅ | — |
| `DATABASE_URL` | `postgresql+psycopg://knowledge_assistant:local_dev_only@localhost:5432/knowledge_assistant` | Backend on the host; Alembic | ✅ | Compose builds its own URL with host `db` |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Backend | ✅ | JSON list |
| `APP_ENV` | `development` | Backend | ✅ | No effect yet (I-13) |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Frontend | ❌ | Set by Compose (I-08) |

## 6. Local services and ports

| Service | Source | Host port | Container port | Health check | Remarks |
|---|---|---|---|---|---|
| `db` | `pgvector/pgvector:0.8.0-pg16` | `${POSTGRES_PORT:-5432}` | 5432 | `pg_isready` every 5 s, up to 10 retries | Data in volume `postgres_data`; never expose publicly |
| `backend` | `backend/Dockerfile` | `${API_PORT:-8000}` | 8000 | None in Compose; use `/health/ready` | Starts after `db` is healthy; `uvicorn --reload`; bind-mounts `app/`, `alembic/`, `alembic.ini` |
| `frontend` | `frontend/Dockerfile` | `${WEB_PORT:-5173}` | 5173 | None | Vite dev server; `node_modules` in volume `frontend_node_modules` |

## 7. API endpoints

| Method | Path | Phase | Status | Remarks |
|---|---|---|---|---|
| GET | `/health/live` | P1 | ✅ Implemented | Returns `{"status":"ok"}` |
| GET | `/health/ready` | P1 | ✅ Implemented | 200 `{"status":"ok","database":"ok"}` or 503 `{"status":"unavailable","database":"unavailable"}` |
| GET | `/docs`, `/openapi.json` | P1 | ✅ FastAPI default | Not separately tested; consider disabling outside development |
| POST | `/api/v1/workspaces` | P2 | ⏳ Planned | Create a workspace |
| GET | `/api/v1/workspaces` | P2 | ⏳ Planned | List accessible workspaces |
| POST | `/api/v1/workspaces/{workspace_id}/documents` | P2 | ⏳ Planned | Upload; returns `202` with status |
| GET | `/api/v1/workspaces/{workspace_id}/documents` | P2 | ⏳ Planned | List documents with ingestion status |
| GET | `/api/v1/documents/{document_id}` | P2 | ⏳ Planned | Status and metadata, after authorization |
| DELETE | `/api/v1/documents/{document_id}` | P2–P3 | ⏳ Planned | Deletes the document and its chunks |
| POST | `/api/v1/workspaces/{workspace_id}/questions` | P4 | ⏳ Planned | Answer, citations, and abstention flag |

All `/api/v1` errors will use one JSON shape with a stable code, a message, and a request ID (P2-09).

## 8. Commands

Backend commands call the venv interpreter directly, so the venv doesn't need to be activated.

| Purpose | Command | Run from | Status | Remarks |
|---|---|---|---|---|
| Create the venv and install | `python -m venv .venv`, then `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` | `backend` | ✅ Used | — |
| Backend lint | `.\.venv\Scripts\python.exe -m ruff check .` | `backend` | ✅ Passing | — |
| Backend format check | `.\.venv\Scripts\python.exe -m ruff format --check .` | `backend` | ❌ 1 file | Fix with `ruff format .` (P1-26) |
| Backend type check | `.\.venv\Scripts\python.exe -m mypy app` | `backend` | ✅ Passing | — |
| Backend tests | `.\.venv\Scripts\python.exe -m pytest` | `backend` | ✅ Passing | — |
| Preview migration SQL | `.\.venv\Scripts\python.exe -m alembic upgrade head --sql` | `backend` | ✅ Works | Offline; no database needed |
| Run the API on the host | `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload` | `backend` | ⏳ Not run | NV-07 |
| Frontend install | `npm ci` | `frontend` | ✅ Used | — |
| Frontend checks | `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` | `frontend` | ✅ Passing | — |
| Frontend dev server | `npm run dev` | `frontend` | ⏳ Not run | `http://localhost:5173` |
| Start the stack | `Copy-Item .env.example .env`, then `docker compose up --build -d` | Project root | ⛔ Blocked | B-01 |
| Apply migrations | `docker compose run --rm backend alembic upgrade head` | Project root | ⛔ Blocked | B-01 |
| Stop the stack | `docker compose down` | Project root | ⛔ Blocked | Add `-v` only to delete the local database volume |
| First push | `git init -b main`, `git add .`, review `git status`, `git commit`, `git remote add origin https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant.git`, `git push -u origin main` | Project root | ✅ Done 2026-10-26 | Commit `f5f4edc` (D-18, P1-29). Commits use the no-reply address set for this repository only (D-20) |
| Push later changes | `git status`, `git add <files>`, `git commit -m "<message>"`, `git push` | Project root | ✅ Used 2026-10-26 | Run the [pre-push checklist](README.md#pre-push-checklist) before every push; CI runs on every push |

## 9. Repository

| Item | Value | Status | Remarks |
|---|---|---|---|
| URL | [github.com/tatpudiarvind/evidence-backed-knowledge-assistant](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant) | ✅ Created | Public (D-16) |
| Contents | Specification, Phase 1 foundation, and tracker | ✅ Pushed 2026-10-26 | First commit `f5f4edc` (D-18, P1-29). `04-skills-evidence.md` is not published (D-21) |
| Default branch | `main` | ✅ | Matches `git init -b main` above |
| GitHub Actions | Enabled; all actions allowed | ✅ | CI runs on every push and pull request; the first run passed (V-21) |
| License | None | ⏳ Open | PD-16 |
| Description | Set on GitHub; describes citations and abstention in the present tense | ⏳ Review | Your text, left unchanged. Those features aren't built yet (Phase 4); consider rewording it, for example as "in progress" (pre-push checklist item 5) |
