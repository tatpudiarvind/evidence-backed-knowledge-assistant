# Project reference

**Last updated:** 2026-10-28 · **Status legend:** see [README.md](README.md#status-legend)

Reference data for the current code. Update it whenever files, dependencies, or configuration change.

## 1. File inventory

| Path | Purpose | Status | Remarks |
|---|---|---|---|
| `README.md` | Project specification (source of truth) and Phase 1 quickstart | ✅ | Quickstart updated for uv and a License section added on 2026-10-27. The setup without containers (no administrator rights) was added on 2026-10-28 and checked from a fresh clone (P1-33; V-58 – V-60) |
| `LICENSE` | MIT License | ✅ | D-23 |
| `.env.example` | Template for local configuration | ✅ | Copy to `.env`; never commit `.env` |
| `.gitignore` | Ignores secrets, virtual environments, caches, build output, local data | ✅ | Also keeps `docs/tracker/04-skills-evidence.md` local (D-21) |
| `compose.yaml` | Local stack: `db`, `backend`, `frontend` | ✅ | Built and run in CI (V-36, V-40, V-61); not run on this machine (on hold, D-31). Passes the connect timeout to the backend (I-23) |
| `.github/workflows/ci.yml` | CI: `backend`, `frontend`, and `compose smoke` jobs | ✅ | v7 actions on `ubuntu-24.04` (D-24, D-26); runs pass (V-21, V-36, V-40, V-53, V-55, V-61) |
| `docs/tracker/` | This tracker (6 files) | ✅ | `04-skills-evidence.md` is local only and not published (D-21) |
| `backend/pyproject.toml` | Package metadata, pinned direct dependencies, Ruff/mypy/pytest configuration | ✅ | Transitive versions are in `uv.lock` |
| `backend/uv.lock` | Exact versions of every backend package, direct and transitive | ✅ | 46 packages (V-24). Regenerate with `uv lock`; never edit by hand (D-22) |
| `backend/Dockerfile`, `backend/.dockerignore` | Dev image (Python 3.12; installs from `uv.lock` with uv 0.13.5) | ✅ | Built and run in CI (V-36, V-61); not built on this machine (on hold, D-31) |
| `backend/alembic.ini` | Alembic configuration | ✅ | The URL is overridden in `env.py` |
| `backend/alembic/env.py` | Migration runner; reads the database URL from app settings | ✅ | — |
| `backend/alembic/script.py.mako` | Template for new migrations | ✅ | — |
| `backend/alembic/versions/0001_enable_pgvector.py` | Enables the `vector` extension | ✅ | Applied to a live database in CI (V-36, V-61) and to native PostgreSQL on this machine (V-46, V-60). Not applied through Compose here (P1-19, on hold, D-31) |
| `backend/app/main.py` | FastAPI app, CORS middleware, router registration | ✅ | — |
| `backend/app/api/router.py` | Combines API routers | ✅ | — |
| `backend/app/api/health.py` | `/health/live` and `/health/ready` | ✅ | — |
| `backend/app/core/config.py` | Settings from environment variables and `.env` | ✅ | Includes the database connect timeout (D-28) |
| `backend/app/core/database.py` | Cached SQLAlchemy engine with a bounded connect timeout; `SELECT 1` check | ✅ | D-28 |
| `backend/app/db/base.py` | SQLAlchemy `DeclarativeBase` for future models | ✅ | No models yet |
| `backend/app/__init__.py`, `backend/app/api/__init__.py`, `backend/app/core/__init__.py`, `backend/app/db/__init__.py` | Package markers | ✅ | — |
| `backend/tests/test_health.py` | 3 health endpoint tests | ✅ | Database mocked |
| `backend/tests/test_database.py` | 2 tests: the engine passes the connect timeout to the driver; a timeout of 0 is rejected | ✅ | Driver mocked; D-28 |
| `frontend/package.json`, `frontend/package-lock.json` | Pinned dependencies, scripts, lockfile | ✅ | Build tools are devDependencies since 2026-10-27 (P1-27). The lockfile records no registry URLs (D-19) |
| `frontend/.npmrc` | Keeps registry URLs out of `package-lock.json` (`omit-lockfile-registry-resolved=true`) | ✅ | D-19; installs work from any npm registry |
| `frontend/Dockerfile`, `frontend/.dockerignore` | Dev image (Node 22, Vite dev server) | ✅ | Built and run in CI (V-36, V-61); not built on this machine (on hold, D-31). Starts Vite with `--host 0.0.0.0` itself, so the container doesn't depend on `vite.config.ts` for that (I-24) |
| `frontend/index.html` | HTML entry point | ✅ | — |
| `frontend/vite.config.ts` | Vite and Vitest (jsdom) configuration | ✅ | No `server.host` since 2026-10-28, so a host run listens on localhost only (I-24; V-60) |
| `frontend/tsconfig.json` | Strict TypeScript configuration | ✅ | — |
| `frontend/eslint.config.js` | ESLint flat configuration | ✅ | — |
| `frontend/src/main.tsx` | React entry point | ✅ | — |
| `frontend/src/App.tsx` | Landing page and readiness indicator | ✅ | — |
| `frontend/src/lib/api.ts` | Typed API client with runtime validation | ✅ | — |
| `frontend/src/styles.css` | Styles (system fonts) | ✅ | Focus outline `#315c48` meets the WCAG contrast minimum (I-19) |
| `frontend/src/App.test.tsx` | Component test | ✅ | — |
| `frontend/src/test/setup.ts` | Test setup (jest-dom matchers) | ✅ | — |
| `backend/.venv/` | Local Python 3.14 virtual environment; also holds uv and pip-audit | Local only | Git-ignored; recreate with the first command in [section 8](#8-commands) |
| `frontend/node_modules/` | Local npm packages | Local only | Git-ignored; recreate with `npm ci` |

## 2. Backend dependencies (`backend/pyproject.toml`)

| Package | Version | Scope | Purpose | Remarks |
|---|---|---|---|---|
| fastapi | 0.162.0 | Runtime | Web framework | Upgraded from 0.115.12 on 2026-10-27 to clear known vulnerabilities in starlette (D-27); brings starlette 1.10.0 |
| uvicorn[standard] | 0.34.2 | Runtime | ASGI server | Extras include watchfiles (used by `--reload`) |
| pydantic-settings | 2.9.1 | Runtime | Typed settings from environment and `.env` | — |
| sqlalchemy | 2.0.41 | Runtime | Database access and ORM | — |
| alembic | 1.16.1 | Runtime | Migrations | — |
| psycopg[binary] | 3.2.10 | Runtime | PostgreSQL driver | 3.2.9 had no Python 3.14 binary wheel |
| pgvector | 0.4.1 | Runtime | pgvector types for SQLAlchemy | Not used yet; pulls in numpy |
| httpx2 | 2.16.0 | Dev | Transport for the FastAPI test client | Replaced httpx 0.28.1 on 2026-10-27; Starlette 1.x deprecates httpx for its test client (D-27) |
| pytest | 9.1.1 | Dev | Tests | Upgraded from 8.4.0 on 2026-10-27 (D-27) |
| mypy | 1.16.0 | Dev | Static type checking (strict) | — |
| ruff | 0.11.13 | Dev | Linting and formatting | — |
| setuptools | 80.9.0 | Build | Build backend | — |

Transitive versions (for example starlette 1.10.0) are locked in `backend/uv.lock` (D-22). To change a version, edit `pyproject.toml` and update the lock file (section 8).

## 3. Frontend dependencies (`frontend/package.json`)

| Package | Version | Scope | Purpose | Remarks |
|---|---|---|---|---|
| react, react-dom | 19.1.0 | dependencies | UI library | — |
| vite | 6.4.5 | devDependencies | Dev server and bundler | Moved from dependencies on 2026-10-27 (P1-27); upgraded from 6.3.5 |
| @vitejs/plugin-react | 4.5.0 | devDependencies | React support for Vite | Moved from dependencies on 2026-10-27 (P1-27) |
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
| GitHub Actions | `actions/checkout@v7`, `actions/setup-python@v7`, `actions/setup-node@v7` | CI on `ubuntu-24.04` | Upgraded from v4/v5 and pinned the runner image on 2026-10-27 (D-24) |
| uv | 0.13.5 | CI backend job; backend Dockerfile; `backend\.venv` on this machine | D-22. Not installed globally |
| pip-audit | 2.10.1 | `backend\.venv` on this machine | Not in CI yet (P5-05) |
| Local Python | 3.14.0 (default); 3.12.15 under `D:\DevTools\python` | This machine | `backend\.venv` uses 3.14 (D-22). The 3.12 environment is `D:\DevTools\venvs\eka-backend-py312`, used by the backend checks on 3.12 (D-30, V-50) |
| Local Node.js and npm | v24.18.1 and 11.16.0 (default); 22.23.4 and 10.9.9 under `D:\DevTools\node` | This machine | Node 22 isn't on PATH; the helper scripts in `D:\DevTools` put it first for their own process only (D-30, V-51) |
| Local PostgreSQL with pgvector | PostgreSQL 16.15 with pgvector 0.8.0, under `D:\DevTools` | This machine only; the main database setup here (D-31) | D-29. Installed and checked in V-43 – V-47; the README's setup without containers was also checked with these binaries, on a throwaway cluster (V-59). Not part of the repository |

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
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | `3` | Backend (host and Compose) | ✅ | Minimum 1; 0 is rejected because PostgreSQL would wait forever (D-28). Compose passes it to the container (I-23) |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Backend | ✅ | JSON list |
| `APP_ENV` | `development` | Backend | ✅ | No effect yet (I-13) |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Frontend | ❌ | Set by Compose (I-08) |

## 6. Local services and ports

| Service | Source | Host port | Container port | Health check | Remarks |
|---|---|---|---|---|---|
| `db` | `pgvector/pgvector:0.8.0-pg16` | `${POSTGRES_PORT:-5432}` | 5432 | `pg_isready` every 5 s, up to 10 retries | Data in volume `postgres_data`; never expose publicly |
| `backend` | `backend/Dockerfile` | `${API_PORT:-8000}` | 8000 | None in Compose; use `/health/ready` | Starts after `db` is healthy; `uvicorn --reload`; bind-mounts `app/`, `alembic/`, `alembic.ini` |
| `frontend` | `frontend/Dockerfile` | `${WEB_PORT:-5173}` | 5173 | None | Vite dev server; `node_modules` in volume `frontend_node_modules` |
| Native PostgreSQL (this machine only) | `D:\DevTools\postgresql\16` with pgvector 0.8.0 (D-29) | 5432 | — (not a container) | `D:\DevTools\pg-status.cmd` (runs `pg_isready`) | Listens on localhost only; data in `D:\DevTools\pgdata\knowledge-assistant-pg16`. The main database setup on this machine (D-31). Uses the same host port as `db`, so run only one of them (R-14) |
| API on the host | `uv run uvicorn app.main:app --reload` from `backend` (README, without containers) | 8000 | — (not a container) | `/health/ready` | Listens on 127.0.0.1 only, uvicorn's default (V-60). Uses the same host port as `backend`, so run only one of them |
| Web app on the host | `npm run dev` from `frontend` (README, without containers) | 5173 | — (not a container) | None | Listens on localhost only since 2026-10-28 (I-24; V-60). Uses the same host port as `frontend`, so run only one of them |

## 7. API endpoints

| Method | Path | Phase | Status | Remarks |
|---|---|---|---|---|
| GET | `/health/live` | P1 | ✅ Implemented | Returns `{"status":"ok"}` |
| GET | `/health/ready` | P1 | ✅ Implemented | 200 `{"status":"ok","database":"ok"}` or 503 `{"status":"unavailable","database":"unavailable"}`. Without a reachable database, 503 arrives in about 6–7 s on this machine (V-32, D-28), or about 3 s when `DATABASE_URL` uses `127.0.0.1` instead of `localhost` (I-25, V-48) |
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
| Create the venv and install | `python -m venv .venv`, then `.\.venv\Scripts\python.exe -m pip install uv==0.13.5 pip-audit==2.10.1`, then `.\.venv\Scripts\uv.exe sync --locked --extra dev --inexact` | `backend` | ✅ Used 2026-10-27 | Installs uv and pip-audit in the venv only (D-22). Keep `--inexact`: uv and pip-audit aren't in the lock file, so a plain `uv sync` would remove them |
| Backend lint | `.\.venv\Scripts\python.exe -m ruff check .` | `backend` | ✅ Passing | — |
| Backend format check | `.\.venv\Scripts\python.exe -m ruff format --check .` | `backend` | ✅ Passing | Fix with `ruff format .`. In CI since 2026-10-27 (P1-26) |
| Backend type check | `.\.venv\Scripts\python.exe -m mypy app` | `backend` | ✅ Passing | — |
| Backend tests | `.\.venv\Scripts\python.exe -m pytest` | `backend` | ✅ Passing | Add `-W error` to fail on warnings (V-28) |
| Update the backend lock file | `.\.venv\Scripts\uv.exe lock` after editing `pyproject.toml`; `.\.venv\Scripts\uv.exe lock --upgrade-package <name>` to upgrade one package; `.\.venv\Scripts\uv.exe lock --check` to confirm the lock is current | `backend` | ✅ Used 2026-10-27 | Commit `uv.lock` together with `pyproject.toml`; CI fails when they don't match (`uv sync --locked`) |
| Audit backend dependencies | See the commands below this table | `backend` | ✅ Used 2026-10-27 | No known vulnerabilities on 2026-10-27 (V-27); CI audits are P5-05 |
| Preview migration SQL | `.\.venv\Scripts\python.exe -m alembic upgrade head --sql` | `backend` | ✅ Works | Offline; no database needed |
| Run the API on the host | `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload` | `backend` | ✅ Used 2026-10-27 | Run without `--reload` and without a database: `/health/live` 200, `/health/ready` 503 (V-31, V-32) |
| Frontend install | `npm ci` | `frontend` | ✅ Used | — |
| Frontend checks | `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` | `frontend` | ✅ Passing | — |
| Audit frontend dependencies | `npm audit`, then `npm audit --omit=dev` | `frontend` | ✅ Used 2026-10-27 | 0 vulnerabilities in both (V-29) |
| Frontend dev server | `npm run dev` | `frontend` | ✅ Used 2026-10-28 | `http://localhost:5173` (V-33, V-60). Listens on localhost only since 2026-10-28 (I-24 fixed) |
| Start, check, or stop native PostgreSQL | `D:\DevTools\pg-start.cmd`, `D:\DevTools\pg-status.cmd`, `D:\DevTools\pg-stop.cmd` | Any folder | ✅ Used 2026-10-27 | This machine only (D-29). Start returns once the server accepts connections and keeps it running in a hidden window; status exits 0 when it accepts connections and 2 when it doesn't respond (V-52) |
| Open psql on native PostgreSQL | `D:\DevTools\pg-psql.cmd`; extra arguments go to psql, for example `D:\DevTools\pg-psql.cmd -c "\dx"` | Any folder | ✅ Used 2026-10-27 | Connects to the `knowledge_assistant` database as `knowledge_assistant` (V-52) |
| Shell with Node.js 22 and the PostgreSQL tools | `D:\DevTools\dev-shell.cmd` | Any folder | ✅ Used 2026-10-27 | Opens PowerShell with both first on PATH, for that window only (V-52) |
| Apply migrations to native PostgreSQL | `.\.venv\Scripts\python.exe -m alembic upgrade head` | `backend` | ✅ Used 2026-10-27 | The default `DATABASE_URL` matches the native cluster, so no `.env` is needed (V-46). Then run the API on the host as above; readiness returns 200 (V-48) |
| Backend checks on Python 3.12 | `D:\DevTools\backend-checks-py312.cmd` | Any folder | ✅ Used 2026-10-27 | Syncs `D:\DevTools\venvs\eka-backend-py312` from `uv.lock`, then runs Ruff, the format check, mypy, and pytest; `backend\.venv` isn't changed (V-50, V-52). Optional argument: another backend folder |
| Frontend checks on Node.js 22 | `D:\DevTools\frontend-checks-node22.cmd` | Any folder | ✅ Used 2026-10-27 | Runs lint, typecheck, tests, and build with the existing `node_modules` (V-51, V-52); run `npm ci` from `dev-shell.cmd` first if `package-lock.json` changed. Optional argument: another frontend folder |
| Run the app without containers | Follow "Without containers (no administrator rights)" in the [project README](../../README.md#without-containers-no-administrator-rights): start PostgreSQL with `pg_ctl`; from `backend`, `uv sync --locked --extra dev`, `uv run alembic upgrade head`, and `uv run uvicorn app.main:app --reload`; from `frontend`, `npm ci` and `npm run dev` | Project root | ✅ Used 2026-10-28 | Checked from a fresh clone of `e4ccbf4` with no `.env` file (V-58 – V-60). The main way to run the app on this machine (D-31), where `D:\DevTools\pg-start.cmd` starts the database (V-52) |
| Start the stack | `Copy-Item .env.example .env`, then `docker compose up --build -d` | Project root | ⏸️ On hold | D-31 (B-01). CI runs the same steps (V-36, V-61). Stop native PostgreSQL first, because both use port 5432 (R-14) |
| Apply migrations | `docker compose run --rm backend alembic upgrade head` | Project root | ⏸️ On hold | D-31 (B-01). CI runs the same command (V-36, V-61) |
| Stop the stack | `docker compose down` | Project root | ⏸️ On hold | D-31 (B-01). Add `-v` only to delete the local database volume |
| First push | `git init -b main`, `git add .`, review `git status`, `git commit`, `git remote add origin https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant.git`, `git push -u origin main` | Project root | ✅ Done 2026-10-26 | Commit `f5f4edc` (D-18, P1-29). Commits use the no-reply address set for this repository only (D-20) |
| Push later changes | `git status`, `git add <files>`, `git commit -m "<message>"`, `git push` | Project root | ✅ Used 2026-10-26 | Run the [pre-push checklist](README.md#pre-push-checklist) before every push; CI runs on every push |
| Push code changes through a branch | `git switch -c <branch>`, commit, and `git push -u origin <branch>`; wait for CI to pass; then `git switch main`, `git merge --ff-only <branch>`, and `git push`; finally `git push origin --delete <branch>` and `git branch -d <branch>` | Project root | ✅ Used 2026-10-28 | CI checks code changes before they reach `main` (V-36, V-40, V-61). Run the pre-push checklist before each push |

**Audit backend dependencies** (from `backend`). pip-audit checks the exact versions exported from `uv.lock` without installing anything:

```powershell
$req = Join-Path $env:TEMP "eka-requirements.txt"
.\.venv\Scripts\uv.exe export --frozen --extra dev --no-emit-project --no-hashes --format requirements-txt |
  Where-Object { $_ -match '^[A-Za-z0-9]' } |
  ForEach-Object { ($_ -split ';')[0].Trim() } |
  Sort-Object -Unique |
  Set-Content $req
.\.venv\Scripts\pip-audit.exe -r $req --no-deps --disable-pip --progress-spinner off
Remove-Item $req
```

Exit code 0 with "No known vulnerabilities found" means the check passed. The warnings about hash checking are expected with `--no-deps`. The result is only valid for the day you run it.

## 9. Repository

| Item | Value | Status | Remarks |
|---|---|---|---|
| URL | [github.com/tatpudiarvind/evidence-backed-knowledge-assistant](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant) | ✅ Created | Public (D-16) |
| Contents | Specification, Phase 1 foundation and hygiene, the setup without containers, and tracker | ✅ Pushed | First commit `f5f4edc` (2026-10-26; D-18, P1-29). Hygiene `d9e50be` and the Compose fix `81262e8` (2026-10-27). The localhost-only Vite setting and the README's setup without containers `e4ccbf4` (2026-10-28; P1-33). `04-skills-evidence.md` is not published (D-21). Nothing from `D:\DevTools` is in the repository (D-29) |
| Default branch | `main` | ✅ | Matches `git init -b main` above |
| GitHub Actions | Enabled; all actions allowed | ✅ | 3 jobs on every push and pull request; runs pass (V-21, V-36, V-40, V-53, V-55, V-61) |
| License | MIT | ✅ Added 2026-10-27 | `LICENSE` (D-23) |
| Description | Marks the project as work in progress and lists only what is built | ✅ Updated 2026-10-27 | Text approved by the owner (D-25). Update it as phases complete ([pre-push checklist](README.md#pre-push-checklist) item 5) |
