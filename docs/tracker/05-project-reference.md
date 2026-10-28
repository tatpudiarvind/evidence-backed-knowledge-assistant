# Project reference

**Last updated:** 2026-10-28 · **Status legend:** see [README.md](README.md#status-legend)

Reference data for the current code. Update it whenever files, dependencies, or configuration change.

## 1. File inventory

| Path | Purpose | Status | Remarks |
|---|---|---|---|
| `README.md` | Project specification (source of truth) and local quickstart | ✅ | Quickstart updated for uv and a License section added on 2026-10-27. The setup without containers (no administrator rights) was added on 2026-10-28 and checked from a fresh clone (P1-33; V-58 – V-60). Updated for Phase 2 on 2026-10-28: code layout, download endpoint, error contract, settings, and what works today (DOC-01) |
| `LICENSE` | MIT License | ✅ | D-23 |
| `.env.example` | Template for local configuration | ✅ | Copy to `.env` at the repository root, which the API, Compose, and Vite all read (D-40); never commit `.env`. Since 2026-10-28 it also lists `POSTGRES_PORT` and `VITE_API_BASE_URL` (I-08) and the Phase 2 settings (section 5) |
| `.gitignore` | Ignores secrets, virtual environments, caches, build output, local data | ✅ | Also keeps `docs/tracker/04-skills-evidence.md` local (D-21). Its `storage/` rule keeps uploaded files in `backend/storage` out of git (D-43) |
| `compose.yaml` | Local stack: `db`, `backend`, `frontend` | ✅ | Built and run in CI (V-36, V-40, V-61); not run on this machine (on hold, D-31). Passes the connect timeout to the backend (I-23). Since 2026-10-28 it also passes the Phase 2 settings and keeps uploads in the `document_storage` volume (D-43) |
| `.github/workflows/ci.yml` | CI: `backend`, `frontend`, and `compose smoke` jobs | ✅ | v7 actions on `ubuntu-24.04` (D-24, D-26); runs pass (V-21, V-36, V-40, V-53, V-55, V-61, V-63, V-68, V-76, V-93, V-94). Since 2026-10-28 the backend job tests against a `pgvector/pgvector:0.8.0-pg16` service database and fails, rather than skips, the database tests (`TEST_DATABASE_REQUIRED=1`); the smoke job also checks sign-up, upload, download, and delete through the API (P2-13, P1-30). Both passed on the Phase 2 runs (V-93, V-94) |
| `docs/tracker/` | This tracker (6 files) | ✅ | `04-skills-evidence.md` is local only and not published (D-21) |
| `backend/pyproject.toml` | Package metadata, pinned direct dependencies, Ruff/mypy/pytest configuration | ✅ | Transitive versions are in `uv.lock`. Registers the `integration` test marker since 2026-10-28 |
| `backend/uv.lock` | Exact versions of every backend package, direct and transitive | ✅ | 51 packages as uv counts them, including the project itself, since 2026-10-28 (46 in V-24). Regenerate with `uv lock`; never edit by hand (D-22) |
| `backend/Dockerfile`, `backend/.dockerignore` | Dev image (Python 3.12; installs from `uv.lock` with uv 0.13.5) | ✅ | Built and run in CI (V-36, V-61); not built on this machine (on hold, D-31). `.dockerignore` leaves out `storage` since 2026-10-28 |
| `backend/alembic.ini` | Alembic configuration | ✅ | The URL is overridden in `env.py` |
| `backend/alembic/env.py` | Migration runner; reads the database URL from app settings | ✅ | Since 2026-10-28 it loads the models, so `alembic check` compares them with the migrations (V-80), and it accepts a connection passed in by the tests |
| `backend/alembic/script.py.mako` | Template for new migrations | ✅ | — |
| `backend/alembic/versions/0001_enable_pgvector.py` | Enables the `vector` extension | ✅ | Applied to a live database in CI (V-36, V-61) and to native PostgreSQL on this machine (V-46, V-60). Not applied through Compose here (P1-19, on hold, D-31) |
| `backend/alembic/versions/0002_users_and_workspaces.py` | Tables `users`, `user_sessions`, `workspaces`, and `workspace_memberships` | ✅ | P2-02. Applied to native PostgreSQL on this machine (V-80); the migration test downgrades and upgrades it (V-77) |
| `backend/alembic/versions/0003_documents.py` | Table `documents` | ✅ | P2-03. Applied and tested the same way (V-80, V-77) |
| `backend/app/main.py` | `create_app`: settings, database engine and sessions, file storage, password hashing, error handlers, middleware (request ID, CORS, error fallback), and routers | ✅ | An app factory since 2026-10-28, so tests can build apps with their own settings |
| `backend/app/api/router.py` | Combines the health and `/api/v1` routers | ✅ | — |
| `backend/app/api/health.py` | `/health/live` and `/health/ready` | ✅ | Uses the app's own engine since 2026-10-28 |
| `backend/app/api/deps.py` | Request dependencies: settings, database session, storage, password hashing, the signed-in user, and the CSRF header check | ✅ | D-32 |
| `backend/app/api/v1/router.py` | Combines the `/api/v1` routers and requires the CSRF header on state-changing requests | ✅ | P2-04, P2-14 |
| `backend/app/api/v1/auth.py` | Register, sign in, sign out, and the current user | ✅ | P2-14 (D-32) |
| `backend/app/api/v1/workspaces.py` | Create and list workspaces | ✅ | P2-04 |
| `backend/app/api/v1/documents.py` | Upload, list, details, download, and delete documents | ✅ | P2-06, P2-08 (D-39) |
| `backend/app/api/v1/uploads.py` | Streaming upload reader: one file, size limit while reading, SHA-256, temporary file | ✅ | D-41 |
| `backend/app/api/v1/schemas.py` | Request and response models, including the error response | ✅ | — |
| `backend/app/core/config.py` | Settings from environment variables and the repository-root `.env` | ✅ | Includes the database connect timeout (D-28) and, since 2026-10-28, the registration, session, upload, and storage settings (section 5; D-40) |
| `backend/app/core/database.py` | SQLAlchemy engine with a bounded connect timeout, session factory, `SELECT 1` check | ✅ | D-28. Since 2026-10-28 the engine keeps SQL parameter values out of errors and logs |
| `backend/app/core/errors.py` | Error contract: JSON with a stable code, a safe message, and the request ID | ✅ | D-42. Validation errors list the fields, never the submitted values |
| `backend/app/core/middleware.py` | Request IDs and the safe fallback for unexpected errors | ✅ | D-42 |
| `backend/app/core/security.py` | Argon2id password hashing (argon2-cffi) and session tokens | ✅ | D-32. Only hashes of passwords and tokens are stored |
| `backend/app/db/base.py` | SQLAlchemy `DeclarativeBase` with fixed constraint and index names | ✅ | The models are in `models.py` since 2026-10-28 |
| `backend/app/db/models.py` | Models `User`, `UserSession`, `Workspace`, `WorkspaceMembership`, and `Document` | ✅ | Match the migrations (V-80) |
| `backend/app/domain/documents.py`, `backend/app/domain/workspaces.py` | Document rules (statuses, file types, content checks, display names) and workspace roles | ✅ | D-33, D-41. Only the `owner` role is used; `member` is reserved for sharing |
| `backend/app/providers/storage.py` | `DocumentStorage` interface, local-disk storage, and random storage keys | ✅ | D-43 |
| `backend/app/repositories/users.py`, `workspaces.py`, `documents.py` | Database queries; workspace and document queries join the caller's membership | ✅ | P2-05 |
| `backend/app/services/auth.py`, `workspaces.py`, `documents.py` | Accounts and sessions, workspaces, and the document lifecycle | ✅ | Access is checked here and in the queries (P2-05) |
| `backend/app/__init__.py` and the `__init__.py` files in `api`, `api/v1`, `core`, `db`, `domain`, `providers`, `repositories`, `services`, and `backend/tests` | Package markers | ✅ | — |
| `backend/tests/test_health.py` | 4 health endpoint tests | ✅ | Database mocked, apart from one test of an unreachable database |
| `backend/tests/test_database.py` | 3 tests: the engine passes the connect timeout to the driver and hides parameter values; a timeout of 0 is rejected; sessions keep objects readable after commit | ✅ | Driver mocked; D-28 |
| `backend/tests/conftest.py`, `backend/tests/support.py` | Fixtures (app factory, test database, temporary storage) and shared helpers (settings, sample files, API calls) | ✅ | The test database's name must end in `_test`; it's created and migrated when missing. Without a reachable server the database tests are skipped, unless `TEST_DATABASE_REQUIRED=1`, as in CI (V-79) |
| `backend/tests/test_auth_api.py` | 14 tests: registration, sign-in, sign-out, session expiry, cookie flags, stored hashes | ✅ | Marked `integration` |
| `backend/tests/test_workspaces_api.py` | 10 tests: create and list, name rules, signed-out requests | ✅ | Marked `integration` |
| `backend/tests/test_documents_api.py` | 27 tests: upload, list, details, download, delete, and limits | ✅ | Marked `integration` |
| `backend/tests/test_isolation_api.py` | 13 tests: another user's workspaces and documents can't be listed, read, downloaded, deleted, or uploaded into; signed-out requests are refused | ✅ | Marked `integration`; P2-12 |
| `backend/tests/test_migrations.py` | 2 tests: a single migration head; downgrade, upgrade, and no difference from the models | ✅ | Marked `integration` |
| `backend/tests/test_config.py`, `test_errors.py`, `test_security.py` | 12, 10, and 6 tests: `.env` location, storage folder, CORS and limit validation; error contract, request IDs, CSRF, CORS; password hashing and session tokens | ✅ | No database needed |
| `backend/tests/test_documents_domain.py`, `test_uploads.py`, `test_storage.py` | 23, 18, and 10 tests: file types, content checks, and display names; the upload reader; storage keys and files | ✅ | No database needed |
| `frontend/package.json`, `frontend/package-lock.json` | Pinned dependencies, scripts, lockfile | ✅ | Build tools are devDependencies since 2026-10-27 (P1-27). The lockfile records no registry URLs (D-19) |
| `frontend/.npmrc` | Keeps registry URLs out of `package-lock.json` (`omit-lockfile-registry-resolved=true`) | ✅ | D-19; installs work from any npm registry |
| `frontend/Dockerfile`, `frontend/.dockerignore` | Dev image (Node 22, Vite dev server) | ✅ | Built and run in CI (V-36, V-61); not built on this machine (on hold, D-31). Starts Vite with `--host 0.0.0.0` itself, so the container doesn't depend on `vite.config.ts` for that (I-24) |
| `frontend/index.html` | HTML entry point | ✅ | Links the favicon (I-21) |
| `frontend/public/favicon.svg` | Favicon: the brand mark, a light "E" on the brand green, drawn as shapes so it needs no font | ✅ | I-21. Vite serves `public/` as is and copies it into the build |
| `frontend/vite.config.ts` | Vite and Vitest (jsdom) configuration | ✅ | No `server.host` since 2026-10-28, so a host run listens on localhost only (I-24; V-60). Reads `.env` from the repository root (`envDir`, D-40) |
| `frontend/tsconfig.json` | Strict TypeScript configuration | ✅ | — |
| `frontend/eslint.config.js` | ESLint flat configuration | ✅ | — |
| `frontend/src/main.tsx` | React entry point | ✅ | — |
| `frontend/src/App.tsx` | Checks the session, then shows sign-in or the workspaces; sign-out | ✅ | The readiness indicator moved to `features/auth/ServiceStatus.tsx` on 2026-10-28 |
| `frontend/src/api/client.ts`, `frontend/src/api/parse.ts` | Shared API client (session cookie, CSRF header, `ApiError` from the error contract, downloads as blobs) and runtime response checks | ✅ | D-44. Replaced `src/lib/api.ts` on 2026-10-28 (DEV-04) |
| `frontend/src/api/auth.ts`, `health.ts`, `workspaces.ts`, `documents.ts` | One module per API area | ✅ | — |
| `frontend/src/components/ErrorNotice.tsx` | Shows an error message and its request ID | ✅ | D-42 |
| `frontend/src/features/auth/AuthCard.tsx`, `ServiceStatus.tsx` | Sign-in and account creation; API and database readiness | ✅ | During a repeat readiness check, "Check again" stays on screen with `aria-disabled`, so it keeps focus; when the services become ready, focus moves to the status message (I-20). Switching forms hides the sign-out message (I-28) |
| `frontend/src/features/workspaces/WorkspaceHome.tsx`, `WorkspaceRail.tsx`, `CreateWorkspaceForm.tsx` | Workspace list, selection, and creation | ✅ | — |
| `frontend/src/features/documents/DocumentLibrary.tsx`, `DocumentRow.tsx`, `UploadQueue.tsx` | Uploads (file picker or drag and drop, one request per file), document list with status, download, and delete | ✅ | D-33 |
| `frontend/src/features/documents/format.ts`, `saveBlob.ts` | File size, date, and type labels; saving a downloaded file through a temporary link | ✅ | The link's object URL is revoked after 60 s (D-44) |
| `frontend/src/styles.css` | Styles (system fonts) | ✅ | Focus outline `#315c48` meets the WCAG contrast minimum (I-19). Extended for the Phase 2 screens on 2026-10-28. Link buttons with `aria-disabled="true"` look disabled (I-20) |
| `frontend/src/App.test.tsx`, `frontend/src/api/client.test.ts`, and the `*.test.ts(x)` files in `src/features/` | 46 Vitest tests: `App` 5, `client` 10, `AuthCard` 6, `ServiceStatus` 2, `WorkspaceHome` 6, `DocumentLibrary` 10, `format` 6, `saveBlob` 1 | ✅ | Pass on Node 22 and Node 24 (V-98) |
| `frontend/src/test/setup.ts` | Test setup: jest-dom matchers; cleanup, real timers, and restored mocks after each test | ✅ | — |
| `frontend/src/test/api.ts` | Test helpers: a fake `fetch` keyed by method and path, sample responses, and `readBlobText` | ✅ | I-27 |
| `backend/.venv/` | Local Python 3.14 virtual environment; also holds uv and pip-audit | Local only | Git-ignored; recreate with the first command in [section 8](#8-commands) |
| `frontend/node_modules/` | Local npm packages | Local only | Git-ignored; recreate with `npm ci` |
| `backend/storage/` | Uploaded files when the API runs on the host | Local only | Git-ignored (D-43). Holds the browser walkthrough's files (V-87 – V-91); set `STORAGE_DIR` to use another folder |
| `frontend/dist/` | Output of `npm run build` | Local only | Git-ignored |

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
| argon2-cffi | 25.1.0 | Runtime | Argon2id password hashing | MIT; brings argon2-cffi-bindings 26.1.0 (MIT), cffi 2.1.1 (MIT-0), and pycparser 3.12 (BSD-3-Clause). Added on 2026-10-28 for local accounts (D-32; P2-01, P2-14) |
| python-multipart | 0.0.32 | Runtime | Streaming multipart parser for uploads | Apache-2.0. `api/v1/uploads.py` uses its `MultipartParser` directly, not FastAPI's form handling, so the size can be checked while reading. Added on 2026-10-28 (D-41; P2-06) |
| httpx2 | 2.16.0 | Dev | Transport for the FastAPI test client | Replaced httpx 0.28.1 on 2026-10-27; Starlette 1.x deprecates httpx for its test client (D-27) |
| pytest | 9.1.1 | Dev | Tests | Upgraded from 8.4.0 on 2026-10-27 (D-27) |
| mypy | 1.16.0 | Dev | Static type checking (strict) | — |
| ruff | 0.11.13 | Dev | Linting and formatting | — |
| setuptools | 80.9.0 | Build | Build backend | — |

Transitive versions (for example starlette 1.10.0) are locked in `backend/uv.lock` (D-22). To change a version, edit `pyproject.toml` and update the lock file (section 8).

### Chosen in Phase 0, not yet added

Versions as checked on PyPI on 2026-10-28 (V-65); check again when adding them.

| Package | Version checked | Scope | Purpose | Remarks |
|---|---|---|---|---|
| pypdf | 6.21.3 | Runtime | PDF text, page by page | BSD-3-Clause. Added in P3-02 (D-35); tried in V-66. Fallback: pypdfium2 5.14.0 (BSD-3-Clause or Apache-2.0) |
| python-docx | 1.2.0 | Runtime | DOCX text | MIT; brings lxml 6.1.3. Added in P3-02 (D-35); tried in V-66 |
| sentence-transformers | 6.2.0 | Runtime | Local embeddings with `BAAI/bge-small-en-v1.5` | Apache-2.0; brings torch, whose Windows wheels on PyPI are CPU-only. Added in P3-05 (D-34); not tried yet. In Linux CI, install torch from PyTorch's CPU-only index to avoid the much larger GPU build |

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
| PostgreSQL with pgvector | `pgvector/pgvector:0.8.0-pg16` | Compose `db` service; CI backend job's test database | PostgreSQL 16 with pgvector 0.8.0. The CI test database since 2026-10-28 (P2-13) |
| Python | `python:3.12-slim` image; 3.12 in CI | Backend Dockerfile; CI backend job | — |
| Node.js | `node:22-alpine` image; 22 in CI | Frontend Dockerfile; CI frontend job | — |
| GitHub Actions | `actions/checkout@v7`, `actions/setup-python@v7`, `actions/setup-node@v7` | CI on `ubuntu-24.04` | Upgraded from v4/v5 and pinned the runner image on 2026-10-27 (D-24) |
| uv | 0.13.5 | CI backend job; backend Dockerfile; `backend\.venv` on this machine | D-22. Not installed globally |
| pip-audit | 2.10.1 | `backend\.venv` on this machine | Not in CI yet (P5-05) |
| Local Python | 3.14.0 (default); 3.12.15 under `D:\DevTools\python` | This machine | `backend\.venv` uses 3.14 (D-22). The 3.12 environment is `D:\DevTools\venvs\eka-backend-py312`, used by the backend checks on 3.12 (D-30, V-50) |
| Local Node.js and npm | v24.18.1 and 11.16.0 (default); 22.23.4 and 10.9.9 under `D:\DevTools\node` | This machine | Node 22 isn't on PATH; the helper scripts in `D:\DevTools` put it first for their own process only (D-30, V-51) |
| Local PostgreSQL with pgvector | PostgreSQL 16.15 with pgvector 0.8.0, under `D:\DevTools` | This machine only; the main database setup here (D-31) | D-29. Installed and checked in V-43 – V-47; the README's setup without containers was also checked with these binaries, on a throwaway cluster (V-59). Not part of the repository |
| Ollama | v0.40.12, the latest release on 2026-10-28 | This machine only; the app uses it from P4-04 | Installed 2026-10-28 in `D:\DevTools\ollama\v0.40.12` from the portable Windows zip (1,601,458,136 bytes) on Ollama's GitHub releases, without the installer (D-38, P4-12). Listens on 127.0.0.1:11434 only (V-71). Not part of the repository |
| Embedding model | `BAAI/bge-small-en-v1.5`; fallback `sentence-transformers/all-MiniLM-L6-v2` | Backend, from P3-05 | Not downloaded yet; that happens in P3-05, most likely through the Windows certificate store (R-16, NV-11). Tests use a fake embedder (D-34) |
| Local LLM | `qwen3:4b-instruct-2507-q4_K_M` (Qwen3-4B-Instruct-2507, 4-bit; ID `0edcdef34593`) | Ollama on this machine; the app uses it from P4-04 | Downloaded 2026-10-28: 2.5 GB, Apache-2.0 license file (D-38, V-72). Without a model, answers are search-only (D-36, P4-11) |

## 5. Environment variables

| Variable | Default | Used by | In `.env.example`? | Remarks |
|---|---|---|---|---|
| `POSTGRES_DB` | `knowledge_assistant` | Compose (`db` and the backend URL) | ✅ | — |
| `POSTGRES_USER` | `knowledge_assistant` | Compose | ✅ | — |
| `POSTGRES_PASSWORD` | `local_dev_only` | Compose | ✅ | Local development only; change it before sharing a host |
| `POSTGRES_PORT` | `5432` | Compose host port for `db` | ✅ | Added on 2026-10-28 (I-08) |
| `API_PORT` | `8000` | Compose host port; frontend API URL | ✅ | — |
| `WEB_PORT` | `5173` | Compose host port; CORS origin | ✅ | — |
| `DATABASE_URL` | `postgresql+psycopg://knowledge_assistant:local_dev_only@127.0.0.1:5432/knowledge_assistant` | Backend on the host; Alembic | ✅ | Compose builds its own URL with host `db`. Uses `127.0.0.1` rather than `localhost` since 2026-10-28, so readiness answers in about 3 s instead of 6 s while the database is down (I-25, V-97) |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | `3` | Backend (host and Compose) | ✅ | Minimum 1; 0 is rejected because PostgreSQL would wait forever (D-28). Compose passes it to the container (I-23) |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Backend | ✅ | JSON list of explicit `http://` or `https://` origins. Wildcards are rejected because the API accepts cookies from these origins (`test_config`) |
| `APP_ENV` | `development` | Backend | ✅ | No effect yet (I-13) |
| `REGISTRATION_ENABLED` | `true` | Backend (host and Compose) | ✅ | Set to `false` once the accounts you need exist; sign-up then answers 403 `registration_disabled` (D-32) |
| `SESSION_LIFETIME_HOURS` | `12` | Backend (host and Compose) | ✅ | 1 to 720 (D-32) |
| `SESSION_COOKIE_SECURE` | `false` | Backend (host and Compose) | ✅ | Set to `true` whenever the app is served over HTTPS; the local setup uses plain HTTP (D-32) |
| `MAX_UPLOAD_BYTES` | `10485760` (10 MiB) | Backend (host and Compose) | ✅ | 1 byte to 100 MiB (D-33, D-41) |
| `MAX_DOCUMENTS_PER_WORKSPACE` | `100` | Backend (host and Compose) | ✅ | 1 to 10,000 (D-33, D-41) |
| `STORAGE_DIR` | `backend/storage` on the host; `/app/storage` in the image | Backend | Commented out | Folder for uploaded files. Compose doesn't set it; it keeps that folder in the `document_storage` volume (D-43) |
| `TEST_DATABASE_URL` | Same as `DATABASE_URL`, but database `knowledge_assistant_test` | Backend tests only | ❌ (tests only) | The database name must end in `_test`; the tests create and migrate it when missing. CI sets its own (P2-13) |
| `TEST_DATABASE_REQUIRED` | Not set | Backend tests only | ❌ (tests only) | `1` makes the database tests fail, instead of being skipped, when the database can't be reached. CI sets it (V-79) |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Frontend; Vite reads it from the root `.env` (D-40) | ✅ | Added on 2026-10-28 (I-08). Compose sets its own value from `API_PORT` |

## 6. Local services and ports

| Service | Source | Host port | Container port | Health check | Remarks |
|---|---|---|---|---|---|
| `db` | `pgvector/pgvector:0.8.0-pg16` | `${POSTGRES_PORT:-5432}` | 5432 | `pg_isready` every 5 s, up to 10 retries | Data in volume `postgres_data`; never expose publicly |
| `backend` | `backend/Dockerfile` | `${API_PORT:-8000}` | 8000 | None in Compose; use `/health/ready` | Starts after `db` is healthy; `uvicorn --reload`; bind-mounts `app/`, `alembic/`, `alembic.ini`. Uploaded files in volume `document_storage` since 2026-10-28 (D-43) |
| `frontend` | `frontend/Dockerfile` | `${WEB_PORT:-5173}` | 5173 | None | Vite dev server; `node_modules` in volume `frontend_node_modules` |
| Native PostgreSQL (this machine only) | `D:\DevTools\postgresql\16` with pgvector 0.8.0 (D-29) | 5432 | — (not a container) | `D:\DevTools\pg-status.cmd` (runs `pg_isready`) | Listens on localhost only; data in `D:\DevTools\pgdata\knowledge-assistant-pg16`. The main database setup on this machine (D-31). Uses the same host port as `db`, so run only one of them (R-14) |
| API on the host | `uv run uvicorn app.main:app --reload` from `backend` (README, without containers) | 8000 | — (not a container) | `/health/ready` | Listens on 127.0.0.1 only, uvicorn's default (V-60). Uses the same host port as `backend`, so run only one of them. Uploaded files go to `backend/storage` unless `STORAGE_DIR` is set (D-43) |
| Web app on the host | `npm run dev` from `frontend` (README, without containers) | 5173 | — (not a container) | None | Listens on localhost only since 2026-10-28 (I-24; V-60). Uses the same host port as `frontend`, so run only one of them |
| Ollama (this machine only) | `D:\DevTools\ollama\v0.40.12`, started by `D:\DevTools\ollama-start.cmd` (D-38) | 11434 | — (not a container) | `D:\DevTools\ollama-status.cmd` (calls `/api/version`) | Listens on 127.0.0.1 only and has no authentication (R-17). While a model is loaded, its model runner listens on another 127.0.0.1 port (V-71). Runs only when started; not part of Compose |

## 7. API endpoints

| Method | Path | Phase | Status | Remarks |
|---|---|---|---|---|
| GET | `/health/live` | P1 | ✅ Implemented | Returns `{"status":"ok"}` |
| GET | `/health/ready` | P1 | ✅ Implemented | 200 `{"status":"ok","database":"ok"}` or 503 `{"status":"unavailable","database":"unavailable"}`. Without a reachable database, 503 arrives in about 3 s on this machine with the default `DATABASE_URL` (V-97); it took about 6 – 7 s while the default used `localhost` (V-32, V-48; I-25, fixed 2026-10-28) |
| GET | `/docs`, `/openapi.json` | P1 | ✅ FastAPI default | Not separately tested; consider disabling outside development |
| POST | `/api/v1/auth/register` | P2 | ✅ Implemented | Creates a local account and signs in: 201 with the user and the session cookie. 403 `registration_disabled` when sign-up is turned off; 409 `email_already_registered` (D-32, P2-14) |
| POST | `/api/v1/auth/login` | P2 | ✅ Implemented | 200 with the user; sets the session cookie and replaces this browser's previous session. A wrong password and an unknown email get the same 401 `invalid_credentials` (D-32, P2-14) |
| POST | `/api/v1/auth/logout` | P2 | ✅ Implemented | 204; ends the session and clears the cookie, also when there's no session (P2-14) |
| GET | `/api/v1/auth/me` | P2 | ✅ Implemented | 200 with the signed-in user; otherwise 401 `not_authenticated` (P2-14) |
| POST | `/api/v1/workspaces` | P2 | ✅ Implemented | 201 with the new workspace; the creator is its owner (P2-04) |
| GET | `/api/v1/workspaces` | P2 | ✅ Implemented | 200; only the workspaces the user is a member of (P2-04, P2-05) |
| POST | `/api/v1/workspaces/{workspace_id}/documents` | P2 | ✅ Implemented | One file per request, in the multipart field `file`; 202 with the document in status `queued` (D-41, P2-06). Processing starts in Phase 3 |
| GET | `/api/v1/workspaces/{workspace_id}/documents` | P2 | ✅ Implemented | 200; newest first, with each document's status (P2-08) |
| GET | `/api/v1/documents/{document_id}` | P2 | ✅ Implemented | 200; details and status, after the membership check (P2-08) |
| GET | `/api/v1/documents/{document_id}/file` | P2 | ✅ Implemented | 200; the original file as an attachment, with `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`. 404 `document_file_missing` if the stored file is gone (D-39, P2-08) |
| DELETE | `/api/v1/documents/{document_id}` | P2–P3 | ✅ Implemented for Phase 2 | 204. Marks the document `deleting`, removes the stored file, then the row. If the file can't be removed: 500 `document_delete_failed`, and deleting again retries; meanwhile downloads get 409 `document_being_deleted`. Phase 3 adds chunks, which must go with the document (P2-08) |
| POST | `/api/v1/workspaces/{workspace_id}/questions` | P4 | ⏳ Planned | Answer, citations, and abstention flag |

All `/api/v1` routes need the session cookie, except sign-up, sign-in, and sign-out. Every POST and DELETE request, including those three, also needs the header `X-CSRF-Protection: 1` (D-32).

### Error contract

Every error response has this shape, except the 503 from `/health/ready`, which keeps its own (D-42, P2-09):

```json
{"error": {"code": "document_not_found", "message": "This document doesn't exist, or you don't have access to it.", "request_id": "<32 hex characters>"}}
```

- `request_id` matches the `X-Request-ID` response header. The API makes a new one for every request and ignores any sent by the client.
- 422 `validation_failed` adds `fields`, a list of `location` and `message` pairs. Submitted values are never echoed.
- Unexpected errors return 500 `internal_error` with a generic message; the details go only to the server log.
- A workspace or document that doesn't exist and one the user can't access get the same 404, so IDs can't be probed (spec §9).

| Status | Codes | Remarks |
|---|---|---|
| 400 | `bad_request`, `upload_interrupted` | `upload_interrupted`: the client disconnected during the upload |
| 401 | `not_authenticated`, `invalid_credentials` | `invalid_credentials` is the same for a wrong password and an unknown email |
| 403 | `forbidden`, `csrf_header_missing`, `registration_disabled` | — |
| 404 | `not_found`, `workspace_not_found`, `document_not_found`, `document_file_missing` | The same answer for items that don't exist and items the user can't access |
| 405 | `method_not_allowed` | Keeps the `Allow` header |
| 409 | `email_already_registered`, `document_limit_reached`, `document_being_deleted` | — |
| 413 | `request_too_large`, `file_too_large` | `file_too_large` names the limit in MiB |
| 415 | `unsupported_media_type`, `unsupported_file_type`, `multipart_required` | `unsupported_file_type`: only PDF, DOCX, and TXT files (D-33) |
| 422 | `validation_failed`, `invalid_file_content`, `invalid_multipart`, `too_many_files`, `file_missing`, `file_empty` | `validation_failed` lists the fields; `invalid_multipart` also covers more than 4 parts |
| 500 | `internal_error`, `document_delete_failed` | `internal_error` details go only to the server log |
| Any other | `http_error` | Fallback for other HTTP errors |

## 8. Commands

Backend commands call the venv interpreter directly, so the venv doesn't need to be activated.

| Purpose | Command | Run from | Status | Remarks |
|---|---|---|---|---|
| Create the venv and install | `python -m venv .venv`, then `.\.venv\Scripts\python.exe -m pip install uv==0.13.5 pip-audit==2.10.1`, then `.\.venv\Scripts\uv.exe sync --locked --extra dev --inexact` | `backend` | ✅ Used 2026-10-27 | Installs uv and pip-audit in the venv only (D-22). Keep `--inexact`: uv and pip-audit aren't in the lock file, so a plain `uv sync` would remove them |
| Backend lint | `.\.venv\Scripts\python.exe -m ruff check .` | `backend` | ✅ Passing | — |
| Backend format check | `.\.venv\Scripts\python.exe -m ruff format --check .` | `backend` | ✅ Passing | Fix with `ruff format .`. In CI since 2026-10-27 (P1-26) |
| Backend type check | `.\.venv\Scripts\python.exe -m mypy app` | `backend` | ✅ Passing | — |
| Backend tests | `.\.venv\Scripts\python.exe -m pytest` | `backend` | ✅ Passing | 152 tests on 2026-10-28 (V-77). The 66 marked `integration` use the PostgreSQL test database `knowledge_assistant_test`, which they create and migrate when missing, so start native PostgreSQL first. Without a reachable server they're skipped, unless `TEST_DATABASE_REQUIRED=1` (V-79). Add `-W error` to fail on warnings (V-28) |
| Update the backend lock file | `.\.venv\Scripts\uv.exe lock` after editing `pyproject.toml`; `.\.venv\Scripts\uv.exe lock --upgrade-package <name>` to upgrade one package; `.\.venv\Scripts\uv.exe lock --check` to confirm the lock is current | `backend` | ✅ Used 2026-10-27 | Commit `uv.lock` together with `pyproject.toml`; CI fails when they don't match (`uv sync --locked`) |
| Audit backend dependencies | See the commands below this table | `backend` | ✅ Used 2026-10-28 | No known vulnerabilities on 2026-10-27 (V-27) or on 2026-10-28, in 50 packages (V-84); CI audits are P5-05 |
| Preview migration SQL | `.\.venv\Scripts\python.exe -m alembic upgrade head --sql` | `backend` | ✅ Works | Offline; no database needed |
| Compare the models with the migrations | `.\.venv\Scripts\python.exe -m alembic check` | `backend` | ✅ Used 2026-10-28 | Needs a database at the latest migration. "No new upgrade operations detected." means they match (V-80); `test_migrations` checks the same against the test database |
| Run the API on the host | `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload` | `backend` | ✅ Used 2026-10-28 | Run without `--reload` and without a database: `/health/live` 200, `/health/ready` 503 (V-31, V-32). With native PostgreSQL, used for the browser walkthrough (V-87 – V-91) |
| Frontend install | `npm ci` | `frontend` | ✅ Used | — |
| Frontend checks | `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` | `frontend` | ✅ Passing | 43 tests on 2026-10-28 (V-83) |
| Audit frontend dependencies | `npm audit --registry=https://registry.npmjs.org/`, then the same with `--omit=dev` | `frontend` | ✅ Used 2026-10-28 | 0 vulnerabilities in both on 2026-10-27 (V-29) and on 2026-10-28 (V-86). Name the public registry: on 2026-10-28 a plain `npm audit` failed with HTTP 401 from the registry this machine's npm is set to use (V-85) |
| Frontend dev server | `npm run dev` | `frontend` | ✅ Used 2026-10-28 | `http://localhost:5173` (V-33, V-60). Listens on localhost only since 2026-10-28 (I-24 fixed). Used for the browser walkthrough (V-87 – V-91) |
| Start, check, or stop native PostgreSQL | `D:\DevTools\pg-start.cmd`, `D:\DevTools\pg-status.cmd`, `D:\DevTools\pg-stop.cmd` | Any folder | ✅ Used 2026-10-27 | This machine only (D-29). Start returns once the server accepts connections and keeps it running in a hidden window; status exits 0 when it accepts connections and 2 when it doesn't respond (V-52) |
| Open psql on native PostgreSQL | `D:\DevTools\pg-psql.cmd`; extra arguments go to psql, for example `D:\DevTools\pg-psql.cmd -c "\dx"` | Any folder | ✅ Used 2026-10-27 | Connects to the `knowledge_assistant` database as `knowledge_assistant` (V-52) |
| Shell with Node.js 22, the PostgreSQL tools, and `ollama` | `D:\DevTools\dev-shell.cmd` | Any folder | ✅ Used 2026-10-28 | Opens PowerShell with all three first on PATH, for that window only (V-52, V-74). Start the Ollama server with `ollama-start.cmd`, not `ollama serve`, so its files stay under `D:\DevTools`. Node 22 is set up only in that interactive window: called inside `cmd /c`, the commands that follow still ran on Node 24 (V-81), so use `frontend-checks-node22.cmd` for scripted Node 22 checks |
| Start, check, or stop Ollama | `D:\DevTools\ollama-start.cmd`, `D:\DevTools\ollama-status.cmd`, `D:\DevTools\ollama-stop.cmd` | Any folder | ✅ Used 2026-10-28 | This machine only (D-38). Start returns once the server answers and keeps it running in a hidden window; status exits 0 when it's running and 1 when it isn't; stop also ends the model runner (V-71, V-74) |
| Ask the local model a question | `ollama run qwen3:4b-instruct-2507-q4_K_M "<question>"` in a `D:\DevTools\dev-shell.cmd` window, with Ollama started | Any folder | ✅ Used 2026-10-28 | A manual check only; the app will call Ollama's API from the backend (P4-04). While loaded, the model uses about 3.2 GB of GPU memory (V-73); `ollama-stop.cmd` also ends the model runner (V-74) |
| Apply migrations to native PostgreSQL | `.\.venv\Scripts\python.exe -m alembic upgrade head` | `backend` | ✅ Used 2026-10-28 | The default `DATABASE_URL` matches the native cluster, so no `.env` is needed (V-46). Then run the API on the host as above; readiness returns 200 (V-48). The database is at `0003_documents` since 2026-10-28 (V-80) |
| Backend checks on Python 3.12 | `D:\DevTools\backend-checks-py312.cmd` | Any folder | ✅ Used 2026-10-28 | Syncs `D:\DevTools\venvs\eka-backend-py312` from `uv.lock`, then runs Ruff, the format check, mypy, and pytest; `backend\.venv` isn't changed (V-50, V-52). Optional argument: another backend folder. From Windows PowerShell 5.1, run it as `cmd /c D:\DevTools\backend-checks-py312.cmd` so the exit code is the script's own (V-78) |
| Frontend checks on Node.js 22 | `D:\DevTools\frontend-checks-node22.cmd` | Any folder | ✅ Used 2026-10-28 | Runs lint, typecheck, tests, and build with the existing `node_modules` (V-51, V-52); run `npm ci` from `dev-shell.cmd` first if `package-lock.json` changed. Optional argument: another frontend folder. On 2026-10-28 it caught a test failure that Node 24 didn't show (V-82, I-27), fixed in V-83 |
| Run the app without containers | Follow "Without containers (no administrator rights)" in the [project README](../../README.md#without-containers-no-administrator-rights): start PostgreSQL with `pg_ctl`; from `backend`, `uv sync --locked --extra dev`, `uv run alembic upgrade head`, and `uv run uvicorn app.main:app --reload`; from `frontend`, `npm ci` and `npm run dev` | Project root | ✅ Used 2026-10-28 | Checked from a fresh clone of `e4ccbf4` with no `.env` file (V-58 – V-60). The main way to run the app on this machine (D-31), where `D:\DevTools\pg-start.cmd` starts the database (V-52). Not repeated from a fresh clone after Phase 2; the Phase 2 walkthrough used this working copy (V-87 – V-91) |
| Start the stack | `Copy-Item .env.example .env`, then `docker compose up --build -d` | Project root | ⏸️ On hold | D-31 (B-01). CI runs the same steps (V-36, V-61). Stop native PostgreSQL first, because both use port 5432 (R-14) |
| Apply migrations | `docker compose run --rm backend alembic upgrade head` | Project root | ⏸️ On hold | D-31 (B-01). CI runs the same command (V-36, V-61) |
| Stop the stack | `docker compose down` | Project root | ⏸️ On hold | D-31 (B-01). Add `-v` only to delete the named volumes too: the database, the uploaded files (since Phase 2, D-43), and the frontend's `node_modules` |
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
| Contents | Specification, Phase 1 foundation and hygiene, the setup without containers, Phase 2 accounts, workspaces, and document lifecycle, and tracker | ✅ Pushed | First commit `f5f4edc` (2026-10-26; D-18, P1-29). Hygiene `d9e50be` and the Compose fix `81262e8` (2026-10-27). The localhost-only Vite setting and the README's setup without containers `e4ccbf4` (2026-10-28; P1-33). Phase 2 `e9fa923` (2026-10-28; P2-01 – P2-14), pushed through branch `phase2-workspaces-documents`, which was deleted once `main` passed CI (V-94). `04-skills-evidence.md` is not published (D-21). Nothing from `D:\DevTools` is in the repository (D-29) |
| Default branch | `main` | ✅ | Matches `git init -b main` above |
| GitHub Actions | Enabled; all actions allowed | ✅ | 3 jobs on every push and pull request; runs pass (V-21, V-36, V-40, V-53, V-55, V-61, V-63, V-68, V-76, V-93, V-94) |
| License | MIT | ✅ Added 2026-10-27 | `LICENSE` (D-23) |
| Description | Marks the project as work in progress and lists only what is built | ✅ Updated 2026-10-27 | Text approved by the owner (D-25). Update it as phases complete ([pre-push checklist](README.md#pre-push-checklist) item 5). It still lists only Phase 1; a Phase 2 update is proposed there and waits for the owner's approval |
