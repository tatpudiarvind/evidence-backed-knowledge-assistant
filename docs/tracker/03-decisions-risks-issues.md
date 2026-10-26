# Decisions, risks, and issues

**Last updated:** 2026-10-26 · **Status legend:** see [README.md](README.md#status-legend)

## 1. Decisions made

| ID | Decision | Rationale | Date | Status | Remarks |
|---|---|---|---|---|---|
| D-01 | Modular monolith: one FastAPI service, one React app, one PostgreSQL database; no microservices, Kafka, or Kubernetes in the MVP | Spec §1 and §4; avoid premature complexity | 2026-10-26 | ✅ Adopted | Revisit only with a measured need |
| D-02 | Python 3.12 baseline (`requires-python >=3.12`; Ruff and mypy target 3.12; CI and Docker use 3.12) | Spec stack; broad library support | 2026-10-26 | ✅ Adopted | This machine runs 3.14 (I-03) |
| D-03 | Exact pins for direct dependencies; frontend `package-lock.json` | Reproducible installs; `npm ci` in CI | 2026-10-26 | ✅ Adopted | Backend transitive lock still pending (PD-11) |
| D-04 | PostgreSQL image `pgvector/pgvector:0.8.0-pg16` | One database for relational data and vectors (spec §4) | 2026-10-26 | ✅ Adopted | Not yet run (B-01) |
| D-05 | Alembic migrations in `backend/alembic/`; the database URL comes from app settings | One source of configuration | 2026-10-26 | ✅ Adopted | Spec §7 proposes `migrations/` (DEV-02) |
| D-06 | Health checks: `/health/live` checks the process only; `/health/ready` runs `SELECT 1`; failures return a generic 503 body | Spec §9: don't leak credentials or configuration | 2026-10-26 | ✅ Adopted | Covered by 3 tests |
| D-07 | CORS allowlist from `CORS_ORIGINS`; Phase 1 allows GET and `Content-Type` only | Least privilege until write endpoints exist | 2026-10-26 | ✅ Adopted | Extend in P2-10 |
| D-08 | Local-first UI: system fonts, no third-party font or CDN requests | Privacy and offline development | 2026-10-26 | ✅ Adopted | — |
| D-09 | The frontend API client validates responses at runtime | Treat API responses as untrusted at the boundary | 2026-10-26 | ✅ Adopted | Keep this pattern in Phase 2 and later |
| D-10 | CI with two jobs, `permissions: contents: read`, and `npm ci` from the lockfile | Least privilege; reproducible installs | 2026-10-26 | ✅ Adopted | Not yet run (B-02) |
| D-11 | Dev-oriented containers: backend runs `uvicorn --reload` with bind mounts; frontend runs the Vite dev server | Fast local iteration | 2026-10-26 | ✅ Adopted | Production images later (P6-04) |
| D-12 | Default ports: PostgreSQL 5432, API 8000, web 5173, all overridable through environment variables | Common defaults | 2026-10-26 | ✅ Adopted | — |
| D-13 | Upgraded vite to 6.4.5, vitest to 4.1.12, eslint to 10.13.0, and psycopg to 3.2.10 | Clear audit findings and deprecations; Python 3.14 wheel availability | 2026-10-26 | ✅ Adopted | Details in the [change log](README.md#change-log) |
| D-14 | The assistant does not initialize git; creating the repository is the owner's action | Explicit instruction | 2026-10-26 | ⏸️ Superseded | Replaced by D-18 (the owner asked to push) |
| D-15 | The tracker lives in `docs/tracker/` | Spec §7 reserves `docs/` for project documentation | 2026-10-26 | ✅ Adopted | — |
| D-16 | The GitHub repository [tatpudiarvind/evidence-backed-knowledge-assistant](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant) is public | Owner's choice; created by Arvind | 2026-10-26 | ✅ Adopted | Empty; not connected to this folder yet (D-17) |
| D-17 | Keep the work local: don't connect this folder to GitHub or push until the owner asks | Explicit instruction | 2026-10-26 | ⏸️ Superseded | Replaced by D-18 on 2026-10-26 |
| D-18 | Push this project to the public GitHub repository | Owner's request on 2026-10-26 | 2026-10-26 | ✅ Adopted | Supersedes D-14 and D-17. First push: P1-29 |
| D-19 | Keep registry URLs out of `frontend/package-lock.json` with `omit-lockfile-registry-resolved=true` in `frontend/.npmrc` | Installs work from any npm registry (CI uses the public one), no internal hostname is published, and integrity hashes are still checked | 2026-10-26 | ✅ Adopted | Fixes I-16 (P1-28). npm looks up each package's download URL at install time, so installs can be slightly slower |
| D-20 | Commit author email: the GitHub no-reply address, set for this repository only | Keeps personal and work emails out of public history and still links commits to the GitHub profile; global git settings unchanged | 2026-10-26 | ✅ Adopted | Resolves PD-15. A privacy-safe default chosen by the assistant; change it with `git config user.email` (affects future commits only) |
| D-21 | Keep `docs/tracker/04-skills-evidence.md` out of the public repository (git-ignored) | Personal career notes; anything pushed stays in git history | 2026-10-26 | ✅ Adopted | Resolves PD-12. A privacy-safe default chosen by the assistant; to publish the file later, remove its line from `.gitignore` and commit it |

## 2. Pending and deferred decisions

| ID | Decision needed | Options to compare | Needed before | Status | Remarks |
|---|---|---|---|---|---|
| PD-01 | Local auth mode | Documented single-user local mode; mature auth library; external OIDC provider | P2-01 | ⏳ Open | The spec discourages custom password handling |
| PD-02 | Sample corpus | Synthetic documents you write; public-domain or openly licensed documents | P3-11, P5-01 | ⏳ Open | Record source and license; no patient or confidential data |
| PD-03 | Local embedding model and vector dimension | Small sentence-transformers models, for example all-MiniLM-L6-v2 (384 dimensions) | P3-05, P3-06 | ⏳ Open | Check license, download size, and RAM (P0-02); the dimension must be configuration |
| PD-04 | PDF parsing library | PyMuPDF (AGPL-3.0 or commercial); permissive alternatives such as pypdf or pdfminer.six | P3-02 | ⏳ Open | Spec §4 names PyMuPDF; check the license fits how you publish the repository |
| PD-05 | Local LLM runtime | Ollama with a small model; retrieval-only or extractive answers as a fallback | P4-04 | ⏳ Open | Depends on the hardware check (P0-02) |
| PD-06 | Hosted model vendor and model (optional) | Decide after the local baseline | After Phase 4 | ⏸️ Deferred | Spec §15: privacy, cost, availability, evaluation |
| PD-07 | Cloud provider and service (optional, one only) | Decide after a cost estimate | Phase 6 | ⏸️ Deferred | Spec §13 and §15; no permanent free tier assumed |
| PD-08 | Durable queue for ingestion | Background task or simple worker vs a durable queue | After Phase 3 | ⏸️ Deferred | Only with an observed reliability need |
| PD-09 | Hybrid search, reranking, and index tuning | Decide from evaluation results | After the Phase 5 baseline | ⏸️ Deferred | Only with evaluation evidence |
| PD-10 | Full authentication provider | Decide if the app is used beyond a portfolio demo | Not planned | ⏸️ Deferred | Spec §15 |
| PD-11 | Backend lock tool | uv (`uv lock`); pip-tools (`pip-compile --generate-hashes`) | P1-24 | ⏳ Open | Installing a new tool needs your approval |
| PD-12 | What to publish in the public repository | Publish everything; or keep personal notes such as `04-skills-evidence.md` out of the repository (move the file or exclude it in `.gitignore`) | P1-29 | ✅ Decided (D-21) | Visibility: public (D-16). The notes file stays local; everything else is published |
| PD-13 | Container runtime | Docker Desktop; Rancher Desktop; Podman | P1-17 | ⏳ Open | Check license terms and IT policy |
| PD-14 | Align the layout with spec §7, or update the spec | Rename (`migrations/`, `src/api/`, `docker-compose.yml`) or document the actual layout | Start of Phase 2 | ⏳ Open | See the spec deviations below |
| PD-15 | Commit author email for this repository | GitHub no-reply address; a personal email; the existing global identity (a work email) | P1-29 | ✅ Decided (D-20) | GitHub no-reply address, set for this repository only; global settings unchanged |
| PD-16 | License | MIT or Apache-2.0; no license (others may view the code but have no right to reuse it) | P1-29 | ⏳ Open | Must be compatible with the PDF library's license (PD-04, R-09) |

## 3. Risks

Likelihood and impact are qualitative judgments, not measurements.

| ID | Risk | Likelihood | Impact | Mitigation | Status | Remarks |
|---|---|---|---|---|---|---|
| R-01 | A container runtime can't be installed on this machine (policy or license) | Medium | High | Rancher Desktop or Podman; a personal machine; native PostgreSQL + pgvector as a last resort | Open | Drives B-01 |
| R-02 | Hardware too small for local embeddings or LLM (RAM, CPU, no GPU) | Medium | Medium | Small models; retrieval-only fallback; optional opt-in hosted adapter | Open | Check in P0-02 |
| R-03 | Local Python 3.14 behaves differently from Python 3.12 in CI and Docker | Medium | Low | Install 3.12 locally, or add a 3.14 CI job | Open | — |
| R-04 | Scope creep (microservices, Kubernetes, Kafka, cloud) before the MVP | Medium | High | Follow the phases; use the definition-of-done gates | Open | Spec §1 |
| R-05 | Unverified skills or metrics appear in the README or CV | Low | High | Evidence column and rules in this tracker; measured-only metrics | Open (controlled) | Spec §14 |
| R-06 | Real patient, confidential, or unlicensed data enters the corpus | Low | High | Synthetic or public licensed corpus; record the license (PD-02) | Open (controlled) | Spec §12 |
| R-07 | Prompt injection through document text | Medium | Medium | Delimit evidence as untrusted; keep authorization independent of the model; validate citations; robustness tests | Open | P4-03, P4-05, P5-03 |
| R-08 | Cross-workspace data leakage | Medium | High | Authorization in service and repository queries; isolation tests in Phases 2 and 4 | Open | P2-05, P2-12, P4-09 |
| R-09 | PDF library license conflicts with how the repository is published (AGPL) | Low | Medium | License review before adoption | Open | PD-04 |
| R-10 | Dependency vulnerabilities and fast-moving toolchains | Medium | Medium | Lock files; audits in CI; scheduled updates | Open | Major upgrades were already needed during setup; P1-24, P1-25, P5-05 |
| R-11 | The AI-assisted scaffold is presented before it is fully understood | Medium | High | Walk through every file until you can explain or rebuild it; record this in `04-skills-evidence.md` (local only, D-21) | Open | Interview readiness |
| R-12 | Unexpected cloud cost if deployed | Low | Medium | Budget alerts, short-lived resources, teardown steps; avoid always-on databases, NAT gateways, and GPUs | ⏸️ Deferred | Only relevant if PD-07 goes ahead |
| R-13 | Internal company details (such as the npm registry hostname or a work email) become public through the repository | Medium | High | [Pre-push checklist](README.md#pre-push-checklist); registry-neutral lockfile (D-19); no-reply author email (D-20); scan the staged files before every push (V-20) | Open (controlled) | Checked before the first push: the lockfile was fixed (V-17) and the staged files were clean (V-20). Anything pushed stays in git history |

## 4. Issues

| ID | Issue | Severity | Impact | Action | Status | Remarks |
|---|---|---|---|---|---|---|
| I-01 | Docker and Podman are not installed | High | The stack, live migrations, readiness, and integration tests can't run | P1-17 (PD-13) | ⛔ Open — blocker B-01 | — |
| I-02 | The folder is not a git repository; CI has never run | High | No CI evidence or history | P1-29, P1-23 | 🔄 In progress — first push (P1-29) | Owner asked to push on 2026-10-26 (D-18) |
| I-03 | Python 3.12 is not installed locally; the venv uses 3.14 | Low | Possible version-specific differences from CI | Install 3.12, or accept the gap with CI on 3.12 | Open | R-03 |
| I-04 | 7 pytest deprecation warnings on Python 3.14 (Starlette `TestClient` anyio alias; FastAPI `asyncio.iscoroutinefunction`) | Low | Noise now; possible breakage on future Python versions | Revisit when upgrading FastAPI and Starlette | Open (monitor) | Third-party code, not project code |
| I-05 | npm prints an install-script warning for esbuild | Low | Noise only | None; re-check after npm upgrades | Open (monitor) | The build works |
| I-06 | The backend reads `.env` from the current folder (`backend/.env` when run on the host), while Compose reads the root `.env` | Low | Confusing host-run setup | Document it (DOC-03) or point settings at the root file (P2-10) | Open | Defaults match `.env.example`, so no file is required today |
| I-07 | CORS allows only GET and `Content-Type` | Medium for Phase 2 | Browser uploads and deletes will fail until extended | P2-10 | Open | Intended for Phase 1 |
| I-08 | `.env.example` doesn't list `POSTGRES_PORT` or `VITE_API_BASE_URL` | Low | Hidden settings | Add them with comments | Open | Both have safe defaults |
| I-09 | `ruff format --check` fails on `app/core/config.py`; CI has no format step | Low | Style drift that CI won't catch | P1-26 | Open | Found 2026-10-26 (V-03) |
| I-10 | `vite` and `@vitejs/plugin-react` are in `dependencies`, not `devDependencies` | Low | Cosmetic for a single-page app | P1-27 | Open | — |
| I-11 | Container images are dev-only (backend installs dev extras; frontend runs the Vite dev server) | Low for now | Not suitable for deployment | P6-04 | Open (by design) | — |
| I-12 | No backend transitive lock file | Medium | Transitive versions can drift between installs | P1-24 (PD-11) | Open | Spec Phase 1 mentions lock files |
| I-13 | `APP_ENV` is read but has no effect yet | Low | None today | Use it for log level and error detail later | Open | — |
| I-14 | The spec README doesn't describe the author's background explicitly | Low | Less personal context for reviewers | DOC-04 (optional) | Open | Review privacy first |
| I-15 | Stray files were created outside the project folder during setup (`D:\Projects\.venv`, `D:\Projects\package-lock.json`) | Low | Folder hygiene | Both removed | ✅ Resolved 2026-10-26 | Commands ran from the wrong folder |
| I-16 | All 294 `resolved` URLs in `frontend/package-lock.json` pointed to this machine's internal company npm registry | High before publishing | GitHub CI's `npm ci` would most likely fail, and the internal hostname would become public | P1-28 | ✅ Resolved 2026-10-26 | Found by V-15; fixed by P1-28 (V-17, V-18) before the first push |

## 5. Spec deviations (spec §7 proposed layout vs actual)

| ID | Spec proposes | Actual | Reason | Action | Status | Remarks |
|---|---|---|---|---|---|---|
| DEV-01 | Root folder `knowledge-assistant/` | `evidence-backed-knowledge-assistant/` | Requested project folder name | None | ✅ Accepted | — |
| DEV-02 | `backend/migrations/` | `backend/alembic/` and `backend/alembic.ini` | Alembic default layout | PD-14 | ⏳ Open | Either works; keep the docs consistent |
| DEV-03 | `docker-compose.yml` | `compose.yaml` | The file name Docker Compose prefers | PD-14 | ⏳ Open | Docker Compose accepts both |
| DEV-04 | `frontend/src/api/` | `frontend/src/lib/api.ts` | One module is enough for Phase 1 | Move it when the client grows (P2-11) | ⏳ Open | — |
| DEV-05 | `backend/app/api/v1/` | `backend/app/api/health.py` (unversioned) | The spec keeps `/health/*` unversioned | Add `api/v1/` routers in P2-04 | ⏳ Open | — |
| DEV-06 | `infra/docker/` | Dockerfiles in `backend/` and `frontend/` | Kept beside each build context | PD-14 | ⏳ Open | — |
| DEV-07 | `domain/`, `services/`, `repositories/`, `providers/`, `workers/`, `evals/`, `docs/` | Not created yet, apart from `docs/tracker/` | Created when first needed (Phase 2 onward) | Create them per phase | ⏳ Planned | Avoids empty folders |
