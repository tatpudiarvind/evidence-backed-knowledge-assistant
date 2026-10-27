# Task tracker

**Last updated:** 2026-10-27 · **Status legend:** see [README.md](README.md#status-legend) · **Spec:** [project specification](../../README.md) §10

Counts are unweighted: a small task and a large one each count as one. Types: Build, Test, Verify, Security, Ops, Decision, Docs, Setup.

## Phase 0 — Confirm environment and decisions

**Definition of done (spec):** the chosen configuration is written down, and the default path needs no paid account or real sensitive data. **Met:** ❌ No.

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| P0-01 | Check Python, Node.js, npm, and Docker versions | Verify | ✅ Done | — | [02-verification-log.md](02-verification-log.md), environment snapshot | Python 3.14.0, Node v24.18.1, and npm 11.16.0 found; Docker and Podman not found (B-01). Since 2026-10-27 this machine also has Python 3.12.15, Node 22.23.4, and PostgreSQL 16.15 with pgvector 0.8.0 under `D:\DevTools` (P1-31, P1-32) |
| P0-02 | Check RAM, free disk, CPU, and GPU to size local models | Verify | ✅ Done | — | [02-verification-log.md](02-verification-log.md), environment snapshot and V-22 | About 32 GB RAM, 16 cores / 24 threads, an NVIDIA GPU with 8 GB VRAM, and more than 300 GB free on D:. Input for PD-03 and PD-05; no model has been run or measured yet |
| P0-03 | Choose a small openly licensed or synthetic sample corpus; record source and license | Decision | ⏳ Not started | — | — | PD-02. Never real patient, employer-confidential, or unlicensed copyrighted material |
| P0-04 | Decide the local auth mode | Decision | ⏳ Not started | — | — | PD-01. The spec prefers a mature auth library or a documented single-user local mode over custom password handling |
| P0-05 | Choose the local embedding model and vector dimension | Decision | ⏳ Not started | P0-02 | — | PD-03. The dimension must be configuration, not hard-coded |
| P0-06 | Decide the local LLM runtime (Ollama and model) or a retrieval-only fallback | Decision | ⏳ Not started | P0-02 | — | PD-05. Any hosted provider stays optional and opt-in |
| P0-07 | Write down the chosen configuration (Phase 0 definition of done) | Docs | ⏳ Not started | P0-02 – P0-06 | — | Move the decisions from PD to D in [03-decisions-risks-issues.md](03-decisions-risks-issues.md) |

## Phase 1 — Repository and local foundation

**Definition of done (spec):** a clean checkout starts locally and CI passes without secrets. **Met:** ❌ No — CI passes without secrets and also builds and starts the full Compose stack on a GitHub-hosted Linux runner (P1-30, V-36), but the stack hasn't started on this machine yet (B-01). Since 2026-10-27 the app does run here against a native PostgreSQL: migrations, readiness, and the landing page's ready state pass (P1-31; V-46, V-48, V-49).

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| P1-01 | Create the monorepo layout (`backend/`, `frontend/`, root config, CI) | Build | ✅ Done | — | [05-project-reference.md](05-project-reference.md), file inventory | Minor naming differences from spec §7 (DEV-02 – DEV-07) |
| P1-02 | FastAPI app skeleton with typed settings (pydantic-settings) and a CORS allowlist | Build | ✅ Done | — | `backend/app/main.py`, `backend/app/core/config.py`; mypy strict passes (V-04) | CORS allows GET only for now (I-07) |
| P1-03 | Health endpoints `GET /health/live` and `GET /health/ready` (database `SELECT 1`; generic 503 on failure) | Build | ✅ Done | P1-02 | `backend/app/api/health.py`; 3 pytest tests pass (V-05); on the host without a database, readiness returns 503 in about 6–7 s (V-32) | Tests mock the database check; live readiness is P1-20. Since 2026-10-27, connection attempts time out (default 3 s), so readiness no longer hangs (D-28, I-18); Compose passes the setting to the container (I-23) |
| P1-04 | Pin backend direct dependencies exactly in `pyproject.toml` | Build | ✅ Done | — | `pip check` clean (V-01); `uv lock --check` passes (V-24) | Transitive versions are locked in `backend/uv.lock` (P1-24, D-22). fastapi, pytest, and the test transport were upgraded on 2026-10-27 (D-27) |
| P1-05 | Backend quality tooling: Ruff lint, mypy strict, pytest with HTTPX | Build | ✅ Done | P1-04 | V-02, V-04, and V-05 pass; format check passes (V-23); 5 tests pass with warnings treated as errors (V-28) | CI runs lint, format check, type check, and tests through uv (P1-15). The HTTPX test transport is now `httpx2` (D-27) |
| P1-06 | Alembic configuration and migration `0001_enable_pgvector` | Build | ✅ Done | P1-04 | Offline SQL generated (V-06) | `env.py` reads the database URL from app settings; live apply is P1-19 |
| P1-07 | React + TypeScript + Vite skeleton: branded landing page with a readiness indicator (checking / ready / unavailable, with retry) | Build | ✅ Done | — | `frontend/src/App.tsx`; test passes (V-11); build passes (V-12, V-30) | Unavailable state checked in a real browser (P1-21, V-33); focus outline contrast fixed (I-19) |
| P1-08 | Typed API client with runtime response validation | Build | ✅ Done | — | `frontend/src/lib/api.ts` | Base URL from `VITE_API_BASE_URL` (default `http://localhost:8000`) |
| P1-09 | Pin frontend dependencies exactly and generate `package-lock.json` | Build | ✅ Done | — | `npm ci` (V-07), `npm ls` (V-08), `npm audit` 0 vulnerabilities (V-13) | Lockfile added after a review found it missing; CI uses `npm ci` |
| P1-10 | Frontend quality tooling: ESLint, strict `tsc --noEmit`, Vitest with React Testing Library, production build | Build | ✅ Done | P1-09 | V-09 – V-12 pass | Playwright comes later (P6-01) |
| P1-11 | `.env.example` and a secret-safe `.gitignore` | Security | ✅ Done | — | `.gitignore` ignores `.env`, `.env.*` (keeps `.env.example`), `.venv/`, `node_modules/`, `dist/`, `data/`, `storage/`, and the local notes file `docs/tracker/04-skills-evidence.md` (D-21) | `.env.example` does not list `POSTGRES_PORT` or `VITE_API_BASE_URL` yet (I-08) |
| P1-12 | Docker Compose: `db` (`pgvector/pgvector:0.8.0-pg16` with `pg_isready` health check), `backend`, `frontend` | Build | ✅ Done | — | `compose.yaml`; YAML parses (V-14); in CI, `docker compose config` passes and `docker compose up --build --wait` reports every service healthy or running (V-36, V-40) | Verified on a GitHub-hosted Ubuntu 24.04 runner (P1-30), not yet on this machine (B-01). Passes the database connect timeout to the backend since 2026-10-27 (I-23) |
| P1-13 | Backend Dockerfile (`python:3.12-slim`) and `.dockerignore` | Build | ✅ Done | — | `backend/Dockerfile`; built and started in CI (V-36) | Installs from `uv.lock` with uv 0.13.5 (D-22). Dev image (installs dev extras); production image is P6-04. Not yet built on this machine (B-01) |
| P1-14 | Frontend Dockerfile (`node:22-alpine`, Vite dev server) and `.dockerignore` | Build | ✅ Done | P1-09 | `frontend/Dockerfile`; built in CI, and the web app responded (V-36) | Dev server only; production image is P6-04. Not yet built on this machine (B-01) |
| P1-15 | GitHub Actions CI: backend job (install, Ruff, mypy, pytest) and frontend job (`npm ci`, lint, typecheck, test, build); `permissions: contents: read` | Build | ✅ Done | — | `.github/workflows/ci.yml`; the first run passed (V-21); all 3 jobs passed on [run 40384992198](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant/actions/runs/40384992198) (V-36) and [run 40456942024](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant/actions/runs/40456942024) (V-40) | Since 2026-10-27: v7 actions on `ubuntu-24.04` (D-24, fixes I-17); the backend installs from `uv.lock` and checks formatting (P1-26); a third job runs the Compose stack (P1-30). No dependency audit in CI yet (P5-05) |
| P1-16 | Document startup and teardown ("Phase 1 foundation quickstart" in the spec README) | Docs | 🟡 Built, unverified | — | Last section of the [project specification](../../README.md) | Updated 2026-10-27 for uv. The Compose commands pass in CI (V-36), but the documented steps haven't been run on this machine (B-01) |
| P1-17 | Install a container runtime that this machine allows | Setup | ⏳ Not started | PD-13 | — | Owner: Arvind. Docker Desktop (check license terms and IT policy), Rancher Desktop, or Podman. Each needs WSL 2 or Hyper-V, which are off here, and turning them on needs administrator rights, so ask IT (V-42) |
| P1-18 | Start the stack with `docker compose up --build -d`; confirm all services are healthy | Verify | ⛔ Blocked | P1-17 | — | Blocked by B-01. The same step (with `--wait`) passes in CI (V-36) |
| P1-19 | Apply migrations to the live database (`docker compose run --rm backend alembic upgrade head`); confirm the `vector` extension | Verify | ⛔ Blocked | P1-18 | — | Blocked by B-01. Passes in CI: pgvector 0.8.0 (V-36). The same migration applies, reverts, and re-applies against native PostgreSQL on this machine (P1-31, V-46); this task stays open for the Compose command |
| P1-20 | Confirm `/health/ready` returns 200 with the database up and 503 with it stopped | Verify | ⛔ Blocked | P1-18 | — | Blocked by B-01. Passes in CI: 200 with the database up, 503 after `docker compose stop db` (V-36). Also shown on this machine with native PostgreSQL: 200, then 503 when stopped, then 200 after a restart (P1-31, V-48); this task stays open for the Compose stack |
| P1-21 | Check the landing page in a real browser (ready and unavailable states, keyboard focus) | Verify | ✅ Done | — | V-33, V-35, V-49 | Unavailable state, retry, and keyboard focus checked on 2026-10-27; focus contrast fixed (I-19). Ready state checked the same day against native PostgreSQL (P1-31). Minor issues logged: I-20, I-21, I-24 |
| P1-22 | Create the GitHub repository | Setup | ✅ Done | — | [tatpudiarvind/evidence-backed-knowledge-assistant](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant): public and empty; checked with `gh api` on 2026-10-26 | Owner: Arvind (D-16). Connecting this folder and pushing are now P1-29 |
| P1-23 | First CI run passes on GitHub Actions | Verify | ✅ Done | P1-29 | [Run 40378438728](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant/actions/runs/40378438728): `backend` and `frontend` jobs passed (V-21) | Triggered by the first push. Non-blocking annotations logged as I-17 |
| P1-24 | Add a backend transitive lock file | Build | ✅ Done | PD-11 | `backend/uv.lock` (46 packages, all from PyPI); `uv lock --check` passes (V-24); a fresh environment installed from the lock passes all checks (V-25) | uv 0.13.5 (D-22). CI and the backend Dockerfile install with `uv sync --locked` |
| P1-25 | Baseline backend dependency audit with pip-audit | Security | ✅ Done | — | Baseline: 8 known vulnerabilities in 2 packages (V-26); after the upgrades: none found (V-27) | pip-audit 2.10.1, installed in `backend/.venv` only. Fixed by D-27 (I-22). A point-in-time result; CI audits are P5-05 |
| P1-26 | Fix formatting drift and add `ruff format --check` to CI | Build | ✅ Done | — | `ruff format --check` passes locally (V-23) and in CI (V-36) | Fixes I-09 (found in V-03) |
| P1-27 | Move `vite` and `@vitejs/plugin-react` to `devDependencies` | Build | ✅ Done | P1-28 | `frontend/package.json`; lockfile refreshed with no package changes and 0 registry URLs; `npm ci`, all checks, and both audits pass (V-29) | Fixes I-10 |
| P1-28 | Make `frontend/package-lock.json` registry-neutral | Security | ✅ Done | — | `frontend/.npmrc`; lockfile regenerated with 0 `resolved` URLs and unchanged versions (V-17); `npm ci` and all frontend checks pass (V-18) | Fixes I-16 (D-19). Integrity hashes are kept, so installs are still verified |
| P1-29 | Initialize git locally, connect to the GitHub repository, and push | Setup | ✅ Done | P1-22, P1-28, PD-12, PD-15 | Commit `f5f4edc` (43 files) on `main`; remote `main` matches local (V-20, V-21) | Pushed 2026-10-26 at the owner's request (D-18) after the [pre-push checklist](README.md#pre-push-checklist). Author email D-20; personal notes kept local (D-21) |
| P1-30 | CI `compose smoke` job: validate the Compose file, build and start the stack, apply migrations, check pgvector, the health endpoints, and the web app, and confirm readiness returns 503 when the database stops | Test | ✅ Done | P1-12 – P1-15 | `compose-smoke` job in `.github/workflows/ci.yml`; passed on [run 40384992198](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant/actions/runs/40384992198) in 56 s (V-36) and [run 40456942024](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant/actions/runs/40456942024) in 42 s (V-40) | Added 2026-10-27 (D-26). Runs on GitHub's Linux runner, so it doesn't replace a run on this machine (P1-18 – P1-20) |
| P1-31 | Native PostgreSQL 16 with pgvector 0.8.0 on this machine, without administrator rights, while no container runtime is available | Setup | ✅ Done | — | Under `D:\DevTools` (outside the repository): PostgreSQL 16.15 from EDB's zip (V-43), pgvector built from source (V-44), a cluster on localhost port 5432 (V-45); migrations, pgvector's tests, and readiness pass against it (V-46 – V-48) | D-29. Added 2026-10-27 after Arvind asked to install what's possible on D:. A stopgap: it doesn't replace the Compose checks (P1-18 – P1-20) |
| P1-32 | Python 3.12 and Node.js 22 on this machine, matching CI | Setup | ✅ Done | — | Python 3.12.15 and Node.js 22.23.4 under `D:\DevTools`; the backend checks (V-50) and frontend checks (V-51) pass on them | D-30. Not on PATH; the default Python 3.14 and Node 24 are unchanged. Resolves I-03 |

## Phase 2 — Workspace and document lifecycle

**Definition of done (spec):** tests prove unauthorized users cannot list, query, download, or delete another workspace's documents, and invalid uploads are rejected. **Met:** ❌ No.

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| P2-01 | Implement the identity/auth guard for the chosen auth mode | Build | ⏳ Not started | P0-04 | — | Authorization must not rely on the UI |
| P2-02 | Migrations for `users`, `workspaces`, and `workspace_memberships` (unique workspace + user) | Build | ⏳ Not started | P1-19 or P1-31 | — | First real tables; verify against a live database. Native PostgreSQL (P1-31) makes that possible on this machine before B-01 clears |
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
| P2-13 | Integration tests against real PostgreSQL (test container or Compose) | Test | ⏳ Not started | P1-17 or P1-31 | — | Spec §11: don't mock away the database behavior being claimed. On this machine they can run against native PostgreSQL (P1-31); CI would need a PostgreSQL service container |

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
| P5-05 | Dependency vulnerability checks in CI (pip-audit, npm audit) | Security | ⏳ Not started | P1-23, P1-25 | — | Local baselines exist: pip-audit (V-27) and `npm audit` (V-29). The audit commands are in [05-project-reference.md](05-project-reference.md#8-commands) |
| P5-06 | Structured logs, request/trace IDs, and basic metrics | Ops | ⏳ Not started | P2-09 | — | No secrets or document text in logs |
| P5-07 | Privacy, retention, and deletion notes | Docs | ⏳ Not started | — | — | Include how to clear local data directories |
| P5-08 | Publish results with method, set size, and trade-offs | Docs | ⏳ Not started | P5-02 | — | This is the Phase 5 definition of done |

## Phase 6 — Portfolio polish and optional deployment

**Definition of done (spec):** an external reviewer can understand the architecture, run the app, inspect tests and evaluation, and reproduce the demo. Cloud deployment is optional. **Met:** ❌ No.

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| P6-01 | Accessibility checks and a Playwright end-to-end smoke test (workspace → upload → ready → ask → cite → abstain → delete) | Test | ⏳ Not started | P4-08 | — | Spec §11 end-to-end smoke. Include keeping focus on the retry button (I-20) |
| P6-02 | `docs/`: architecture, API, security, and operations | Docs | ⏳ Not started | — | — | — |
| P6-03 | Screenshots, demo data, and clear limitations in the README | Docs | ⏳ Not started | P6-01 | — | Screenshots only of real, working features. Add a favicon (I-21) |
| P6-04 | Production-oriented images (backend without dev extras; frontend static build served) | Build | ⏳ Not started | P1-18 | — | Current images are dev-only (I-11) |
| P6-05 | Cost estimate and choice of one cloud (optional) | Decision | ⏸️ Deferred | P5-08 | — | PD-07. Don't assume any free tier lasts |
| P6-06 | Optional deployment: least-privilege identity, managed secrets, HTTPS, backups, budget alerts, teardown steps | Ops | ⏸️ Deferred | P6-05 | — | Never expose the database publicly; avoid always-on databases, Kubernetes, NAT gateways, and GPUs |

## Documentation and tracking

| ID | Task | Type | Status | Depends on | Evidence / output | Remarks |
|---|---|---|---|---|---|---|
| DOC-01 | Specification README (16 numbered sections, 4 Mermaid diagrams) | Docs | ✅ Done | — | [Project specification](../../README.md) | Source of truth; change it deliberately |
| DOC-02 | Project tracker in `docs/tracker/` | Docs | ✅ Done | — | This folder (6 files; `04-skills-evidence.md` is local only, D-21) | Created 2026-10-26 |
| DOC-03 | Document the host-run workflow (API and web without Docker; `backend/.env` vs root `.env`) | Docs | ⏳ Not started | — | — | Related to I-06. The API and the Vite dev server both ran on the host on 2026-10-27 (V-31 – V-33), without any `.env` file. Host runs against native PostgreSQL on this machine are listed in [05-project-reference.md](05-project-reference.md#8-commands) (V-48) |
| DOC-04 | Optional: short author background and motivation section in the README | Docs | ⏳ Not started | PD-12 | — | The spec mentions prior enterprise knowledge-assistant work only generically; review privacy before publishing |
| DOC-05 | Keep this tracker current after each work session | Docs | 🔄 In progress | — | Change log in [README.md](README.md) | Ongoing |
