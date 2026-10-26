# Task tracker

**Last updated:** 2026-10-26 · **Status legend:** see [README.md](README.md#status-legend) · **Spec:** [project specification](../../README.md) §10

Counts are unweighted: a small task and a large one each count as one. Types: Build, Test, Verify, Security, Ops, Decision, Docs, Setup.

## Phase 0 — Confirm environment and decisions

**Definition of done (spec):** the chosen configuration is written down, and the default path needs no paid account or real sensitive data. **Met:** ❌ No.

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| P0-01 | Check Python, Node.js, npm, and Docker versions | Verify | ✅ Done | — | [02-verification-log.md](02-verification-log.md), environment snapshot | Python 3.14.0, Node v24.18.1, and npm 11.16.0 found; Docker and Podman not found (B-01) |
| P0-02 | Check RAM, free disk, CPU, and GPU to size local models | Verify | ⏳ Not started | — | — | Needed before PD-03 and PD-05. Example: `Get-CimInstance Win32_ComputerSystem`, `Get-PSDrive D`, `Get-CimInstance Win32_VideoController` |
| P0-03 | Choose a small openly licensed or synthetic sample corpus; record source and license | Decision | ⏳ Not started | — | — | PD-02. Never real patient, employer-confidential, or unlicensed copyrighted material |
| P0-04 | Decide the local auth mode | Decision | ⏳ Not started | — | — | PD-01. The spec prefers a mature auth library or a documented single-user local mode over custom password handling |
| P0-05 | Choose the local embedding model and vector dimension | Decision | ⏳ Not started | P0-02 | — | PD-03. The dimension must be configuration, not hard-coded |
| P0-06 | Decide the local LLM runtime (Ollama and model) or a retrieval-only fallback | Decision | ⏳ Not started | P0-02 | — | PD-05. Any hosted provider stays optional and opt-in |
| P0-07 | Write down the chosen configuration (Phase 0 definition of done) | Docs | ⏳ Not started | P0-02 – P0-06 | — | Move the decisions from PD to D in [03-decisions-risks-issues.md](03-decisions-risks-issues.md) |

## Phase 1 — Repository and local foundation

**Definition of done (spec):** a clean checkout starts locally and CI passes without secrets. **Met:** ❌ No — code and local checks pass, but the stack has never run in containers and CI has never run.

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| P1-01 | Create the monorepo layout (`backend/`, `frontend/`, root config, CI) | Build | ✅ Done | — | [05-project-reference.md](05-project-reference.md), file inventory | Minor naming differences from spec §7 (DEV-02 – DEV-07) |
| P1-02 | FastAPI app skeleton with typed settings (pydantic-settings) and a CORS allowlist | Build | ✅ Done | — | `backend/app/main.py`, `backend/app/core/config.py`; mypy strict passes (V-04) | CORS allows GET only for now (I-07) |
| P1-03 | Health endpoints `GET /health/live` and `GET /health/ready` (database `SELECT 1`; generic 503 on failure) | Build | ✅ Done | P1-02 | `backend/app/api/health.py`; 3 pytest tests pass (V-05) | Tests mock the database check; live readiness is P1-20 |
| P1-04 | Pin backend direct dependencies exactly in `pyproject.toml` | Build | ✅ Done | — | `pip check` clean (V-01) | Direct pins only; no transitive lock yet (P1-24) |
| P1-05 | Backend quality tooling: Ruff lint, mypy strict, pytest with HTTPX | Build | ✅ Done | P1-04 | V-02, V-04, and V-05 pass | `ruff format --check` fails on one file (P1-26) |
| P1-06 | Alembic configuration and migration `0001_enable_pgvector` | Build | ✅ Done | P1-04 | Offline SQL generated (V-06) | `env.py` reads the database URL from app settings; live apply is P1-19 |
| P1-07 | React + TypeScript + Vite skeleton: branded landing page with a readiness indicator (checking / ready / unavailable, with retry) | Build | ✅ Done | — | `frontend/src/App.tsx`; test passes (V-11); build passes (V-12) | Not yet viewed in a real browser (P1-21) |
| P1-08 | Typed API client with runtime response validation | Build | ✅ Done | — | `frontend/src/lib/api.ts` | Base URL from `VITE_API_BASE_URL` (default `http://localhost:8000`) |
| P1-09 | Pin frontend dependencies exactly and generate `package-lock.json` | Build | ✅ Done | — | `npm ci` (V-07), `npm ls` (V-08), `npm audit` 0 vulnerabilities (V-13) | Lockfile added after a review found it missing; CI uses `npm ci` |
| P1-10 | Frontend quality tooling: ESLint, strict `tsc --noEmit`, Vitest with React Testing Library, production build | Build | ✅ Done | P1-09 | V-09 – V-12 pass | Playwright comes later (P6-01) |
| P1-11 | `.env.example` and a secret-safe `.gitignore` | Security | ✅ Done | — | `.gitignore` ignores `.env`, `.env.*` (keeps `.env.example`), `.venv/`, `node_modules/`, `dist/`, `data/`, `storage/`, and the local notes file `docs/tracker/04-skills-evidence.md` (D-21) | `.env.example` does not list `POSTGRES_PORT` or `VITE_API_BASE_URL` yet (I-08) |
| P1-12 | Docker Compose: `db` (`pgvector/pgvector:0.8.0-pg16` with `pg_isready` health check), `backend`, `frontend` | Build | 🟡 Built, unverified | — | `compose.yaml`; YAML parses with 3 services and 2 volumes (V-14) | Never run: no container runtime (B-01) |
| P1-13 | Backend Dockerfile (`python:3.12-slim`) and `.dockerignore` | Build | 🟡 Built, unverified | — | `backend/Dockerfile` | Never built. Dev image (installs dev extras); production image is P6-04 |
| P1-14 | Frontend Dockerfile (`node:22-alpine`, Vite dev server) and `.dockerignore` | Build | 🟡 Built, unverified | P1-09 | `frontend/Dockerfile` | Never built. Dev server only; production image is P6-04 |
| P1-15 | GitHub Actions CI: backend job (install, Ruff, mypy, pytest) and frontend job (`npm ci`, lint, typecheck, test, build); `permissions: contents: read` | Build | 🟡 Built, unverified | — | `.github/workflows/ci.yml`; YAML parses with 2 jobs (V-14) | Never run: no repository yet (B-02). No format-check or dependency-audit step yet (P1-26, P5-05) |
| P1-16 | Document startup and teardown ("Phase 1 foundation quickstart" in the spec README) | Docs | 🟡 Built, unverified | — | Last section of the [project specification](../../README.md) | Commands not executed yet (B-01) |
| P1-17 | Install a container runtime that this machine allows | Setup | ⏳ Not started | PD-13 | — | Owner: Arvind. Docker Desktop (check license terms and IT policy), Rancher Desktop, or Podman |
| P1-18 | Start the stack with `docker compose up --build -d`; confirm all services are healthy | Verify | ⛔ Blocked | P1-17 | — | Blocked by B-01 |
| P1-19 | Apply migrations to the live database (`docker compose run --rm backend alembic upgrade head`); confirm the `vector` extension | Verify | ⛔ Blocked | P1-18 | — | Blocked by B-01 |
| P1-20 | Confirm `/health/ready` returns 200 with the database up and 503 with it stopped | Verify | ⛔ Blocked | P1-18 | — | Blocked by B-01 |
| P1-21 | Check the landing page in a real browser (ready and unavailable states, keyboard focus) | Verify | ⏳ Not started | — | — | The unavailable state can be checked now with `npm run dev`; the ready state needs P1-18 |
| P1-22 | Create the GitHub repository | Setup | ✅ Done | — | [tatpudiarvind/evidence-backed-knowledge-assistant](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant): public and empty; checked with `gh api` on 2026-10-26 | Owner: Arvind (D-16). Connecting this folder and pushing are now P1-29 |
| P1-23 | First CI run passes on GitHub Actions | Verify | ⏳ Not started | P1-29 | — | Runs automatically on the first push |
| P1-24 | Add a backend transitive lock file | Build | ⏳ Not started | PD-11 | — | uv is not installed; options are `uv lock` or pip-tools with hashes |
| P1-25 | Baseline backend dependency audit with pip-audit | Security | ⏳ Not started | — | — | pip-audit is not installed; `npm audit` already shows 0 vulnerabilities (V-13) |
| P1-26 | Fix formatting drift and add `ruff format --check` to CI | Build | ⏳ Not started | — | V-03 | Found 2026-10-26: `app/core/config.py` would be reformatted (joins a split string). CI runs only `ruff check`, so it would not catch this |
| P1-27 | Move `vite` and `@vitejs/plugin-react` to `devDependencies` | Build | ⏳ Not started | P1-28 | — | Housekeeping with no functional impact; refresh the lockfile and re-run checks afterwards. Do P1-28 first so the refreshed lockfile stays registry-neutral |
| P1-28 | Make `frontend/package-lock.json` registry-neutral | Security | ✅ Done | — | `frontend/.npmrc`; lockfile regenerated with 0 `resolved` URLs and unchanged versions (V-17); `npm ci` and all frontend checks pass (V-18) | Fixes I-16 (D-19). Integrity hashes are kept, so installs are still verified |
| P1-29 | Initialize git locally, connect to the GitHub repository, and push | Setup | 🔄 In progress | P1-22, P1-28, PD-12, PD-15 | — | Owner asked to push on 2026-10-26 (D-18). [Pre-push checklist](README.md#pre-push-checklist) done; author email D-20; personal notes kept local (D-21) |

## Phase 2 — Workspace and document lifecycle

**Definition of done (spec):** tests prove unauthorized users cannot list, query, download, or delete another workspace's documents, and invalid uploads are rejected. **Met:** ❌ No.

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| P2-01 | Implement the identity/auth guard for the chosen auth mode | Build | ⏳ Not started | P0-04 | — | Authorization must not rely on the UI |
| P2-02 | Migrations for `users`, `workspaces`, and `workspace_memberships` (unique workspace + user) | Build | ⏳ Not started | P1-19 | — | First real tables; verify against a live database |
| P2-03 | Migration for `documents` (workspace ID, display name, opaque storage key, MIME type, size, SHA-256, status, safe failure code and message, timestamps) | Build | ⏳ Not started | P2-02 | — | Spec §9 |
| P2-04 | Workspace endpoints `POST /api/v1/workspaces` and `GET /api/v1/workspaces` | Build | ⏳ Not started | P2-01, P2-02 | — | Introduces `app/api/v1/` routers (DEV-05) |
| P2-05 | Enforce workspace authorization in service and repository queries | Security | ⏳ Not started | P2-01 | — | A guessed document ID must never bypass workspace checks (spec §6.3) |
| P2-06 | Upload endpoint `POST /api/v1/workspaces/{workspace_id}/documents` returning `202` with status; size limit, PDF/DOCX/TXT allowlist, content-signature check, sanitized display name | Build | ⏳ Not started | P2-03, P2-07 | — | Rejected files get a clear 4xx response and are never indexed |
| P2-07 | Local storage adapter with server-generated keys under the git-ignored `storage/` folder; path-traversal protection | Security | ⏳ Not started | — | — | Behind an interface so object storage can be added later |
| P2-08 | Document endpoints: list, status/metadata, delete (`GET …/documents`, `GET /api/v1/documents/{document_id}`, `DELETE /api/v1/documents/{document_id}`) | Build | ⏳ Not started | P2-05 | — | Delete flow per spec §6.3; chunk removal is added in P3-12 |
| P2-09 | Standard error JSON (stable code, message, request ID) and request-ID middleware | Build | ⏳ Not started | — | — | Never echo stack traces, credentials, or uploaded content |
| P2-10 | Extend CORS for POST/DELETE and auth headers; settle where `.env` is read from | Build | ⏳ Not started | P2-01 | — | Resolves I-06 and I-07 |
| P2-11 | Frontend: workspace selection, upload form, document list with status, delete | Build | ⏳ Not started | P2-04, P2-08 | — | Loading, empty, and error states; grow the typed API client (DEV-04) |
| P2-12 | Tests: cross-workspace list/query/download/delete is denied; invalid uploads are rejected | Test | ⏳ Not started | P2-05 – P2-08 | — | This is the Phase 2 definition of done |
| P2-13 | Integration tests against real PostgreSQL (test container or Compose) | Test | ⏳ Not started | P1-17 | — | Spec §11: don't mock away the database behavior being claimed |

## Phase 3 — Ingestion and semantic indexing

**Definition of done (spec):** fixture documents produce the expected text, pages, and chunks; a duplicate retry does not duplicate chunks; parser or provider errors lead to `failed` status and recoverable logs. **Met:** ❌ No.

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| P3-01 | License review and choice of PDF library | Decision | ⏳ Not started | — | — | PD-04: the spec names PyMuPDF (AGPL-3.0 or commercial license); compare permissive options such as pypdf or pdfminer.six |
| P3-02 | Parser interface with PDF, DOCX, and TXT adapters that keep page/section metadata | Build | ⏳ Not started | P3-01 | — | DOCX via python-docx (spec §4) |
| P3-03 | Text normalization that keeps source locations | Build | ⏳ Not started | P3-02 | — | — |
| P3-04 | Configurable chunking (size and overlap) with boundary/overlap unit tests | Build | ⏳ Not started | P3-03 | — | — |
| P3-05 | Embedding provider interface and local sentence-transformers adapter (batched; model and dimension from config) | Build | ⏳ Not started | P0-05 | — | The first run downloads model weights; record size and license |
| P3-06 | Migration for `document_chunks` with a vector column, foreign-key indexes, and a vector index | Build | ⏳ Not started | P2-03, P0-05 | — | Choose the index type for the distance operator and the measured dataset size |
| P3-07 | Background ingestion with status `queued` → `processing` → `ready` / `failed` | Build | ⏳ Not started | P3-02 – P3-06 | — | FastAPI background task or a simple worker; durable queue deferred (PD-08) |
| P3-08 | Idempotent retry (no duplicate chunks) and a retry action | Build | ⏳ Not started | P3-07 | — | — |
| P3-09 | Safe failure codes and messages; logs without secrets or document text | Security | ⏳ Not started | P3-07 | — | — |
| P3-10 | Parsing limits: maximum pages, parse timeout, malformed files, decompression bombs | Security | ⏳ Not started | P3-02 | — | Spec §12 |
| P3-11 | Synthetic or licensed fixture documents with parser, chunker, and ingestion tests | Test | ⏳ Not started | P0-03 | — | This is the Phase 3 definition of done |
| P3-12 | Extend delete to remove chunks, vectors, and the stored file safely | Build | ⏳ Not started | P2-08, P3-06 | — | If storage deletion fails, report it instead of claiming success (spec §6.3) |

## Phase 4 — Grounded question answering

**Definition of done (spec):** integration tests confirm correct citations, no cross-workspace retrieval, and abstention on unsupported questions; model and provider limitations are documented. **Met:** ❌ No.

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| P4-01 | Question embedding and workspace-scoped pgvector retrieval (cosine) | Build | ⏳ Not started | P3-05, P3-06 | — | — |
| P4-02 | Relevance threshold and abstention response (no fabricated citations) | Build | ⏳ Not started | P4-01 | — | Set the threshold from evaluation results, not guesswork (P5-02) |
| P4-03 | Prompt builder with a context budget; retrieved text delimited as untrusted evidence | Security | ⏳ Not started | P4-01 | — | Reduces, but does not eliminate, prompt-injection risk |
| P4-04 | LLM provider interface and local Ollama adapter; optional hosted adapter (opt-in and disclosed) | Build | ⏳ Not started | P0-06 | — | The model must never control authorization or tools |
| P4-05 | Validate citations against the retrieved chunk IDs | Security | ⏳ Not started | P4-04 | — | Model-generated IDs and URLs are untrusted |
| P4-06 | `POST /api/v1/workspaces/{workspace_id}/questions` returning answer, citations, and abstention flag | Build | ⏳ Not started | P4-02 – P4-05 | — | — |
| P4-07 | Decide Q&A persistence and retention (`questions`, `answers`, `citations` tables are optional) | Decision | ⏳ Not started | — | — | Define retention and deletion before storing question text |
| P4-08 | Answer UI: citations linked to document and page; loading, empty, error, and abstention states | Build | ⏳ Not started | P4-06 | — | — |
| P4-09 | Integration tests: correct citations, no cross-workspace retrieval, abstention | Test | ⏳ Not started | P4-06, P2-13 | — | This is the Phase 4 definition of done |
| P4-10 | Document model and provider limitations | Docs | ⏳ Not started | P4-04 | — | — |

## Phase 5 — Evaluation and hardening

**Definition of done (spec):** results are reproducible from a documented command, trade-offs are stated, and no fabricated benchmark claims appear in the README or CV. **Met:** ❌ No.

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| P5-01 | Manually reviewed evaluation set (`evals/questions.jsonl`): question, expected document/page, expected facts | Test | ⏳ Not started | P0-03 | — | Keep it small and honest; record the set size |
| P5-02 | Reproducible evaluation command measuring retrieval hit rate / recall@k and citation correctness; version the data and model/config | Test | ⏳ Not started | P5-01, P4-06 | — | No metrics exist yet. Publish only measured values with their conditions |
| P5-03 | Robustness tests with unsupported questions and prompt-injection-like content | Security | ⏳ Not started | P4-06 | — | Robustness evidence, not proof of security |
| P5-04 | Rate limits and request size limits | Security | ⏳ Not started | P2-06 | — | — |
| P5-05 | Dependency vulnerability checks in CI (pip-audit, npm audit) | Security | ⏳ Not started | P1-23, P1-25 | — | — |
| P5-06 | Structured logs, request/trace IDs, and basic metrics | Ops | ⏳ Not started | P2-09 | — | No secrets or document text in logs |
| P5-07 | Privacy, retention, and deletion notes | Docs | ⏳ Not started | — | — | Include how to clear local data directories |
| P5-08 | Publish results with method, set size, and trade-offs | Docs | ⏳ Not started | P5-02 | — | This is the Phase 5 definition of done |

## Phase 6 — Portfolio polish and optional deployment

**Definition of done (spec):** an external reviewer can understand the architecture, run the app, inspect tests and evaluation, and reproduce the demo. Cloud deployment is optional. **Met:** ❌ No.

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| P6-01 | Accessibility checks and a Playwright end-to-end smoke test (workspace → upload → ready → ask → cite → abstain → delete) | Test | ⏳ Not started | P4-08 | — | Spec §11 end-to-end smoke |
| P6-02 | `docs/`: architecture, API, security, and operations | Docs | ⏳ Not started | — | — | — |
| P6-03 | Screenshots, demo data, and clear limitations in the README | Docs | ⏳ Not started | P6-01 | — | Screenshots only of real, working features |
| P6-04 | Production-oriented images (backend without dev extras; frontend static build served) | Build | ⏳ Not started | P1-18 | — | Current images are dev-only (I-11) |
| P6-05 | Cost estimate and choice of one cloud (optional) | Decision | ⏸️ Deferred | P5-08 | — | PD-07. Don't assume any free tier lasts |
| P6-06 | Optional deployment: least-privilege identity, managed secrets, HTTPS, backups, budget alerts, teardown steps | Ops | ⏸️ Deferred | P6-05 | — | Never expose the database publicly; avoid always-on databases, Kubernetes, NAT gateways, and GPUs |

## Documentation and tracking

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| DOC-01 | Specification README (16 numbered sections, 4 Mermaid diagrams) | Docs | ✅ Done | — | [Project specification](../../README.md) | Source of truth; change it deliberately |
| DOC-02 | Project tracker in `docs/tracker/` | Docs | ✅ Done | — | This folder (6 files; `04-skills-evidence.md` is local only, D-21) | Created 2026-10-26 |
| DOC-03 | Document the host-run workflow (API and web without Docker; `backend/.env` vs root `.env`) | Docs | ⏳ Not started | — | — | Related to I-06 |
| DOC-04 | Optional: short author background and motivation section in the README | Docs | ⏳ Not started | PD-12 | — | The spec mentions prior enterprise knowledge-assistant work only generically; review privacy before publishing |
| DOC-05 | Keep this tracker current after each work session | Docs | 🔄 In progress | — | Change log in [README.md](README.md) | Ongoing |
