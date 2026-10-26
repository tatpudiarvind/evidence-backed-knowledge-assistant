# Verification log

**Last updated:** 2026-10-26 · **Machine:** local Windows development machine · **Status legend:** see [README.md](README.md#status-legend)

Results below are from this machine. CI and containers use Python 3.12 and Node 22, so results there may differ. When you run a check, add a row with the date, command, and result instead of editing old rows.

## 1. Environment snapshot (2026-10-26)

| Component | Project expects | Found on this machine | Status | Remarks |
|---|---|---|---|---|
| Operating system | Windows, macOS, or Linux | Windows | ✅ | Check IT policy before installing tools on a managed machine |
| Python | 3.12 or newer (CI and Docker use 3.12) | 3.14.0 at `C:\Python314`; `py -0p` lists no 3.12 | ✅ Meets ≥ 3.12 | Local and CI versions differ (I-03, R-03) |
| Backend virtual environment | `backend\.venv` | Python 3.14.0; all pinned packages installed; `pip check` clean | ✅ | Git-ignored; recreate at any time |
| Node.js | 22 in Docker and CI | v24.18.1 | ✅ | Local is newer than CI |
| npm | Bundled with Node.js | 11.16.0 | ✅ | Prints a harmless install-script warning for esbuild (I-05) |
| npm registry | Public npm registry in CI | This machine's npm is configured for an internal company registry | ✅ Works locally | The lockfile no longer records registry URLs, so CI can install from the public registry (D-19, V-17) |
| Frontend packages | `frontend\node_modules` | 16 direct packages match the pins (`npm ls`) | ✅ | Git-ignored |
| Docker / Docker Compose | Required to run the stack | Not found | ⛔ | Blocker B-01 |
| Podman | Alternative container runtime | Not found | — | Option for PD-13 |
| git | Required for the repository and CI | 2.56.0 available | ✅ | Bundled with the Copilot app, so it may not be on your normal PATH. The project folder is a git repository from 2026-10-26: branch `main`, remote `origin` = the GitHub repository. Commits use the GitHub no-reply address, set for this repository only (D-20); the global identity is unchanged |
| GitHub CLI (`gh`) | Optional | 2.102.1 available; github.com login `tatpudiarvind` stored | ✅ | Bundled with the Copilot app. In this app's environment, `gh` defaults to a different account, so github.com commands must use the stored `tatpudiarvind` login |
| GitHub repository | Public repository for the portfolio | `tatpudiarvind/evidence-backed-knowledge-assistant`: public, default branch `main`, Actions enabled, no license | ✅ | Checked with `gh api` on 2026-10-26. First push from this folder: P1-29 (D-18); license pending (PD-16) |
| uv | Optional (backend lock file) | Not found | ⏳ | PD-11 |
| pip-audit | Optional (vulnerability check) | Not installed | ⏳ | P1-25 |
| RAM, disk, CPU, GPU | Needed to size local models | Not checked yet | ⏳ | P0-02 |

## 2. Check log

| ID | Date | Area | Check | Command (run from) | Result | Remarks |
|---|---|---|---|---|---|---|
| V-01 | 2026-10-26 | Backend | Dependency consistency | `python -m pip check` (`backend`) | ✅ No broken requirements | Run with the `.venv` interpreter |
| V-02 | 2026-10-26 | Backend | Lint | `ruff check .` (`backend`) | ✅ All checks passed | Rule sets E, F, I, UP, B |
| V-03 | 2026-10-26 | Backend | Formatting | `ruff format --check .` (`backend`) | ❌ 1 file would be reformatted (`app/core/config.py`); 12 already formatted | Cosmetic: joins a split string. Not checked in CI (P1-26, I-09) |
| V-04 | 2026-10-26 | Backend | Type check | `mypy app` (`backend`) | ✅ No issues in 10 source files | Strict mode |
| V-05 | 2026-10-26 | Backend | Tests | `pytest -q` (`backend`) | ✅ 3 passed, 7 warnings, 1.71 s | Warnings are third-party deprecations on Python 3.14 (I-04); the database is mocked |
| V-06 | 2026-10-26 | Backend | Migration, offline | `alembic upgrade head --sql` (`backend`) | ✅ Emits `CREATE EXTENSION IF NOT EXISTS vector` and the `alembic_version` table | Offline SQL only; live apply is P1-19 |
| V-07 | 2026-10-26 | Frontend | Clean install from lockfile | `npm ci` (`frontend`) | ✅ 244 packages, 0 vulnerabilities | Run during foundation setup; dependencies unchanged since |
| V-08 | 2026-10-26 | Frontend | Installed tree matches pins | `npm ls --depth=0` (`frontend`) | ✅ 16 direct packages, no errors | — |
| V-09 | 2026-10-26 | Frontend | Lint | `npm run lint` (`frontend`) | ✅ Passed | ESLint 10 flat config |
| V-10 | 2026-10-26 | Frontend | Type check | `npm run typecheck` (`frontend`) | ✅ Passed | `tsc --noEmit`, strict |
| V-11 | 2026-10-26 | Frontend | Component tests | `npm test` (`frontend`) | ✅ 1 file, 1 test passed | 48.5 s total on this machine, mostly jsdom environment setup (31.1 s) |
| V-12 | 2026-10-26 | Frontend | Production build | `npm run build` (`frontend`) | ✅ JS 190.73 kB (60.27 kB gzip); CSS 4.31 kB (1.66 kB gzip); HTML 0.61 kB | `dist/` deleted after the check |
| V-13 | 2026-10-26 | Frontend | Dependency audit | `npm audit` (`frontend`) | ✅ 0 vulnerabilities | Point-in-time result; re-run regularly |
| V-14 | 2026-10-26 | Infra | YAML syntax | Parse `compose.yaml` and `.github/workflows/ci.yml` with PyYAML (project root) | ✅ Compose: services `db`, `backend`, `frontend`; volumes `postgres_data`, `frontend_node_modules`. CI: jobs `backend`, `frontend` | Syntax only; `docker compose config` not run (NV-09) |
| V-15 | 2026-10-26 | Frontend | Lockfile registry check (before publishing) | Node script that groups the `resolved` URL hosts in `package-lock.json` (`frontend`) | ❌ All 294 entries resolve from this machine's internal company npm registry | GitHub CI most likely can't download from it, and the hostname would become public (I-16, P1-28) |
| V-16 | 2026-10-26 | Repo | Secret pattern scan | Search for GitHub tokens, `sk-` API keys, AWS access key IDs, and private-key headers, excluding `.venv` and `node_modules` (project root) | ✅ No matches | A pattern scan, not a full audit; repeat right before every push |
| V-17 | 2026-10-26 | Frontend | Lockfile registry check after P1-28 | `npm install --package-lock-only --ignore-scripts` with `omit-lockfile-registry-resolved=true` in `frontend/.npmrc`, then compare the old and new lockfiles with a Python script (`frontend`) | ✅ 0 `resolved` URLs (was 294); 294 integrity hashes kept; every package and version unchanged; no internal hostnames | The remaining URLs are public funding links (opencollective.com, github.com, tidelift.com, eslint.org). Fixes I-16 |
| V-18 | 2026-10-26 | Frontend | Clean install and all checks with the regenerated lockfile | `npm ci`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` (`frontend`) | ✅ All passed; 1 test passed in 3.97 s; JS 190.73 kB (60.27 kB gzip) | Installed through this machine's registry; GitHub CI installs from the public registry (NV-05). `dist/` deleted after the check |
| V-19 | 2026-10-26 | Backend | Lint, type check, and tests before the first push | `ruff check .`, `mypy app`, `pytest -q` (`backend`) | ✅ All checks passed; no issues in 10 source files; 3 passed, 7 warnings, 1.83 s | Same third-party warnings as V-05 (I-04) |
| V-20 | 2026-10-26 | Repo | Staged-file review before the first push | `git init -b main`, `git add -A`, then `git status --short --ignored`, `git ls-files --eol`, and `git grep --cached` for internal hostnames, this machine's username, email addresses, and token and private-key patterns (project root) | ✅ 43 files staged, all with LF line endings in the index; `.venv`, `node_modules`, tool caches, and `04-skills-evidence.md` not staged; no matches for hostnames, username, emails, tokens, or keys | The only password value is the documented local-development placeholder in `.env.example` and `compose.yaml`. A pattern scan, not a full audit (R-13) |

## 3. Not yet verified

| ID | What | Why not yet | How to verify (run from) | Unblocked by | Remarks |
|---|---|---|---|---|---|
| NV-01 | Docker images build | No container runtime | `docker compose build` (project root) | B-01, P1-17 | — |
| NV-02 | Stack starts and the database becomes healthy | No container runtime | `docker compose up --build -d`, then `docker compose ps` (project root) | B-01 | P1-18 |
| NV-03 | Migration applies to live PostgreSQL | No container runtime | `docker compose run --rm backend alembic upgrade head`, then `docker compose exec db psql -U knowledge_assistant -d knowledge_assistant -c "\dx"` (project root) | B-01 | P1-19; `\dx` should list `vector` |
| NV-04 | Readiness against a real database | No container runtime | `curl.exe -i http://localhost:8000/health/ready` → 200; after `docker compose stop db` → 503 | B-01 | P1-20 |
| NV-05 | CI workflow on GitHub | First push in progress (P1-29, D-18) | Check the Actions tab, or run `gh run list` for the repository | P1-29 | P1-23 |
| NV-06 | Landing page in a real browser | Not done yet | `npm run dev` (`frontend`), then open `http://localhost:5173` | — | P1-21; the ready state needs the API and database |
| NV-07 | API runs on the host outside tests | Not done yet | `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload` (`backend`); expect `/health/live` 200 and `/health/ready` 503 without a database | — | Also confirms settings and `.env` loading on the host (I-06) |
| NV-08 | Backend dependency vulnerabilities | pip-audit not installed | `.\.venv\Scripts\python.exe -m pip install pip-audit`, then `.\.venv\Scripts\python.exe -m pip_audit` (`backend`) | — | P1-25; installing a tool needs your approval |
| NV-09 | Compose file validated by Docker | No container runtime | `docker compose config` (project root) | B-01 | Stronger than the YAML parse in V-14 |
