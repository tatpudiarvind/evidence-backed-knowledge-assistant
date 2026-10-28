# Project tracker — Evidence-backed Knowledge Assistant

| Field | Value | Remarks |
|---|---|---|
| Last updated | 2026-10-28 | Update at the end of every work session |
| Current stage | Phase 1 done — next: the Phase 0 decisions, then Phase 2 | A fresh clone starts on this machine without containers: checks, migration, API, web app, and the landing page's ready state all pass, on localhost only (V-58 – V-60). CI passes and also builds and runs the container stack on GitHub's Linux runner (V-36, V-61). Containers on this machine are on hold by choice: everything stays local, without a virtual machine or administrator rights (D-31) |
| Source of truth | [Project specification](../../README.md) | This tracker records progress against the spec; it does not replace it |
| GitHub repository | [tatpudiarvind/evidence-backed-knowledge-assistant](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant) | Created 2026-10-26 (public; MIT license since 2026-10-27, D-23). Pushed: foundation `f5f4edc` (2026-10-26); hygiene `d9e50be` and the Compose fix `81262e8` (2026-10-27); the setup without containers `e4ccbf4` (2026-10-28). CI passes (V-21, V-36, V-40, V-53, V-55, V-61). Personal notes stay local (D-21) |
| AI/RAG features | None yet | By design: Phase 1 is foundation only |
| Checks (2026-10-28) | 57 passed, 5 failed | Every failure has been fixed: V-03 by V-23, V-15 by V-17, V-26 by V-27, V-31 by V-32, V-34 by V-35. CI checks (V-21, V-36, V-40, V-53, V-55, V-61) ran on GitHub's runner, not this machine. V-42 – V-52 cover the tools installed under `D:\DevTools`; V-58 – V-60 cover the setup without containers from a fresh clone. Details in [02-verification-log.md](02-verification-log.md) |
| Measured metrics | None | Evaluation is Phase 5; never publish unmeasured numbers |
| Cloud resources / paid APIs | None | The default path stays local and free. Arvind prefers to keep everything on this machine for now (D-31) |

## Status legend

| Symbol | Meaning | Use when | Remarks |
|---|---|---|---|
| ✅ Done | Implemented and verified | Evidence (file path or logged command and result) exists | Never mark done without evidence |
| 🟡 Built, unverified | Written but never executed in its real environment | Dockerfiles, Compose, CI workflow, untested instructions | Becomes ✅ only after a successful real run |
| 🔄 In progress | Started or ongoing | Work is partially complete | — |
| ⏳ Not started | Planned | Work has not begun | — |
| ⛔ Blocked | Cannot proceed | A named blocker must be cleared first | Name the blocker in Remarks |
| ⏸️ Deferred / On hold | Postponed on purpose, optional, paused by your decision, or superseded | Spec §15 deferred decisions, optional cloud work, decisions replaced by later ones (D-14, D-17) | Revisit at the phase noted, or when you ask |

## Phase summary

Counts come from [01-task-tracker.md](01-task-tracker.md). They are unweighted task counts, not an effort or percent-complete estimate.

| Phase | Focus | Status | Tasks | ✅ | 🟡 | 🔄 | ⏳ | ⛔ | ⏸️ | Definition of done met? | Remarks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P0 | Confirm environment and decisions | 🔄 In progress | 7 | 2 | 0 | 0 | 5 | 0 | 0 | ❌ No | Tool versions and hardware checked; corpus, auth, and model decisions still open (P0-03 – P0-07) |
| P1 | Repository and local foundation | ✅ Done | 33 | 29 | 0 | 0 | 0 | 0 | 4 | ✅ Yes | Met on 2026-10-28: a fresh clone starts on this machine without containers (P1-33; V-58 – V-60), and CI passes without secrets (V-36, V-61). The 4 deferred tasks run Compose on this machine, which is on hold (P1-17 – P1-20, D-31) |
| P2 | Workspace and document lifecycle | ⏳ Not started | 13 | 0 | 0 | 0 | 13 | 0 | 0 | ❌ No | Phase 1 is done; start once the auth mode is decided (PD-01). Runs on this machine with the setup without containers (D-31) |
| P3 | Ingestion and semantic indexing | ⏳ Not started | 12 | 0 | 0 | 0 | 12 | 0 | 0 | ❌ No | Needs corpus, embedding model, and PDF library decisions |
| P4 | Grounded question answering | ⏳ Not started | 10 | 0 | 0 | 0 | 10 | 0 | 0 | ❌ No | Needs the local LLM runtime decision (PD-05) |
| P5 | Evaluation and hardening | ⏳ Not started | 8 | 0 | 0 | 0 | 8 | 0 | 0 | ❌ No | No evaluation results exist yet |
| P6 | Portfolio polish and optional deployment | ⏳ Not started | 6 | 0 | 0 | 0 | 4 | 0 | 2 | ❌ No | Cloud deployment is optional and deferred |
| DOC | Documentation and tracking | 🔄 In progress | 5 | 2 | 0 | 2 | 1 | 0 | 0 | — | Spec and tracker done; upkeep ongoing. The host-run workflow is documented except which `.env` file the backend reads on the host (DOC-03, I-06) |
| **Total** | | | **94** | **33** | **0** | **2** | **53** | **0** | **6** | | |

## Blockers

| ID | Blocker | Blocks | How to unblock | Who | Status | Remarks |
|---|---|---|---|---|---|---|
| B-01 | No container engine: Docker and the Podman engine are not installed | P1-18 – P1-20 (the Compose stack on this machine) | Only if containers are wanted here: ask IT to enable WSL 2 or Hyper-V, or to install a permitted runtime (PD-13), then run the README quickstart | Arvind | ⏸️ On hold (D-31) | Podman Desktop 1.30.5 was installed on 2026-10-28, but it's only the GUI; the Podman engine needs WSL 2 or Hyper-V, and turning either on needs administrator rights (V-42, V-56). Arvind chose to keep everything local without a virtual machine (D-31). The app runs here without containers (V-58 – V-60), and CI runs the stack on every push (V-36, V-61) |
| B-02 | CI has never run on GitHub: this folder was not a git repository or connected to the repository | P1-23, P5-05 | Push (P1-29), then confirm the first CI run passes (P1-23) | Implementation session | ✅ Resolved 2026-10-26 | Pushed commit `f5f4edc`; the first CI run passed (V-21) |

## Pre-push checklist

The GitHub repository is public, and anything pushed stays in git history. Run these checks before every push. Status below is for the latest pushes on 2026-10-28.

| # | Check | Status | Related | Remarks |
|---|---|---|---|---|
| 1 | `frontend/package-lock.json` contains no internal registry URLs | ✅ Done | I-16, P1-28, V-17, V-29 | No `resolved` URLs; integrity hashes kept (D-19). Still true after the lockfile was regenerated on 2026-10-27 (V-29) |
| 2 | Decide whether to publish `04-skills-evidence.md` | ✅ Kept local | PD-12, D-21 | Git-ignored. To publish it, remove its line from `.gitignore` and commit it |
| 3 | Choose the commit author email | ✅ No-reply address | PD-15, D-20 | Set for this repository only; the global git identity is unchanged |
| 4 | Choose a license | ✅ MIT | PD-16, D-23 | Chosen by Arvind on 2026-10-27 |
| 5 | Make sure the repository description matches what's built | ✅ Done | D-25 | Updated 2026-10-27 with owner-approved text that marks the project as work in progress. Reviewed on 2026-10-28, when Phase 1 was done: it still matches what's built. Review it whenever a phase completes |
| 6 | Scan for secrets, internal hostnames, and personal data | ✅ Done | V-16, V-20, V-37, V-39, V-41, V-54, V-57, V-62, R-13 | Staged files scanned before every push so far; repeat before every push |
| 7 | `.env`, virtual environments, `node_modules`, and local data are git-ignored | ✅ Done | P1-11, V-20 | Confirmed with `git status` after `git init` |

## Next actions (in order)

| # | Action | Task IDs | Who | Remarks |
|---|---|---|---|---|
| 1 | Make the Phase 0 decisions and write down the configuration | P0-03 – P0-07 (PD-01, PD-02, PD-03, PD-05) | Arvind | Needed before Phases 2–4. Hardware is checked (P0-02). Prefer options that run on this machine without administrator rights (D-31) |
| 2 | Optional small fixes | I-08, I-20, I-21, I-25, DOC-03 (I-06) | Implementation session | Not blocking; push code changes through a branch so CI checks them first ([commands](05-project-reference.md#8-commands)) |
| 3 | Start Phase 2 | P2-01 onward | Implementation session | Phase 1 is done (2026-10-28); start once the auth mode is decided (PD-01). The first tables and integration tests run on this machine against native PostgreSQL (P2-02, P2-13; D-31) |
| 4 | Optional: ask IT to enable WSL 2 or Hyper-V, only if you want containers on this machine | PD-13, P1-17 – P1-20 | Arvind | Not needed for development (D-31). CI runs the container stack on every push (V-61) |

## Tracker files

| File | Contents | Update when | Remarks |
|---|---|---|---|
| [README.md](README.md) | Dashboard: stage, phase summary, blockers, next actions, change log | End of every work session | Start here |
| [01-task-tracker.md](01-task-tracker.md) | Every task by phase with status, dependencies, and evidence | A task changes status | IDs are stable; never renumber |
| [02-verification-log.md](02-verification-log.md) | Environment snapshot, check results, items not yet verified | After running any check | Record date, command, and result |
| [03-decisions-risks-issues.md](03-decisions-risks-issues.md) | Decisions, pending decisions, risks, issues, spec deviations | A decision is made or a problem is found | Move a pending decision (PD) to the decisions table (D) once made |
| `04-skills-evidence.md` (local only) | Skill evidence and resume readiness | A phase completes | Personal notes; git-ignored and not published (D-21) |
| [05-project-reference.md](05-project-reference.md) | Files, dependency pins, environment variables, ports, endpoints, commands | Configuration or dependencies change | Reference data, not status |

## Rules for keeping this tracker honest

| Rule | Why | Remarks |
|---|---|---|
| Mark ✅ only with evidence (file path, or a logged command and result) | Prevents "done on paper" | Use 🟡 for built-but-never-run items |
| Never record a metric that was not measured | Spec §10 Phase 5 and §14 | Always state method, set size, and conditions |
| Mark a skill resume-ready only when it is implemented, verified, and you can explain it unaided | Interview credibility | Track this in `04-skills-evidence.md` (local only) |
| Keep IDs stable; add new tasks at the end of their phase | Cross-references stay valid | Retire a task by marking it ⏸️ with a remark instead of deleting it |
| Update the phase counts and change log at the end of each session | The dashboard stays accurate | Recount from [01-task-tracker.md](01-task-tracker.md) |
| Run the [pre-push checklist](#pre-push-checklist) before every push | The repository is public, and git history is permanent | Covers registry URLs, author email, secrets, and personal notes |

## Change log

| Date | Change | Result | Remarks |
|---|---|---|---|
| 2026-10-26 | Created the project folder and saved the specification `README.md` | ✅ | 16 numbered sections and 4 Mermaid diagrams (system flowchart, ingestion sequence, Q&A sequence, class diagram) |
| 2026-10-26 | Built the Phase 1 foundation: FastAPI backend, React/Vite frontend, Compose, Dockerfiles, CI, env and ignore files | ✅ code / 🟡 runtime | No AI/RAG features, by design |
| 2026-10-26 | Adjusted dependency pins during setup: psycopg 3.2.9 → 3.2.10; vite 6.3.5 → 6.4.5; vitest 3.2.4 → 4.1.12; eslint 9.28.0 → 10.13.0 (with @eslint/js 10.0.1 and typescript-eslint 8.72.0) | ✅ | psycopg 3.2.9 had no binary wheel for Python 3.14; the vite/vitest upgrades cleared the `npm audit` findings; eslint 9.28.0 was flagged as deprecated |
| 2026-10-26 | Removed the Google Fonts import; the UI uses system fonts | ✅ | Local-first: the page makes no third-party requests |
| 2026-10-26 | Appended "Phase 1 foundation quickstart" to the specification README | ✅ | Commands not yet executed (B-01) |
| 2026-10-26 | Generated `frontend/package-lock.json` and verified `npm ci` | ✅ | CI installs with `npm ci` |
| 2026-10-26 | Removed a stray `D:\Projects\.venv` created by a command run from the wrong folder | ✅ | Outside the project folder; confirmed absent |
| 2026-10-26 | Removed a stray empty `D:\Projects\package-lock.json` (87 bytes, no packages) | ✅ | Created at 20:16 during foundation setup, most likely by an npm command run from the wrong folder; found while preparing this tracker |
| 2026-10-26 | Re-ran all local checks for this tracker | ✅ 13 / ❌ 1 | Only `ruff format --check` failed (I-09, P1-26) |
| 2026-10-26 | Created this tracker in `docs/tracker/` | ✅ | 6 files |
| 2026-10-26 | Arvind created the GitHub repository `tatpudiarvind/evidence-backed-knowledge-assistant` (public, empty, Actions enabled) | ✅ | Checked with `gh api`. This folder was intentionally not connected or pushed (D-17) |
| 2026-10-26 | Pre-push review: `package-lock.json` resolves every package from this machine's internal company npm registry; secret pattern scan found nothing | ❌ 1 / ✅ 1 | Fix the lockfile before the first push (I-16, P1-28) |
| 2026-10-26 | Updated the tracker: repository status, pre-push checklist, tasks P1-28 and P1-29, decisions D-16 and D-17, pending decisions PD-15 and PD-16, risk R-13, issue I-16 | ✅ | No code or configuration changed |
| 2026-10-26 | Arvind asked to push the project to GitHub; the assistant chose privacy-safe defaults for the open pre-push decisions | ✅ | Author email: GitHub no-reply address for this repository only (D-20); `04-skills-evidence.md` kept local (D-21); license still open (PD-16) |
| 2026-10-26 | Made `frontend/package-lock.json` registry-neutral: added `frontend/.npmrc` and regenerated the lockfile | ✅ | 0 registry URLs and unchanged versions (V-17); `npm ci` and all frontend checks pass (V-18); backend checks re-run (V-19) |
| 2026-10-26 | Initialized git in the project folder and scanned the staged files | ✅ | V-20. First push: P1-29 |
| 2026-10-26 | Pushed the Phase 1 foundation to GitHub: commit `f5f4edc`, 43 files | ✅ | The first CI run passed (V-21); non-blocking annotations logged as I-17 |
| 2026-10-26 | Updated the tracker after the push: tasks P1-15, P1-23, and P1-29; blocker B-02; issues I-02 and I-17; check V-21 | ✅ | Committed and pushed as a follow-up commit |
| 2026-10-27 | Checked the hardware for sizing local models (P0-02) | ✅ | Generic summary in V-22; no model has been run or measured |
| 2026-10-27 | Arvind chose: uv and pip-audit inside `backend\.venv` only, the MIT license, and a work-in-progress repository description | ✅ | D-22, D-23, D-25 |
| 2026-10-27 | Phase 1 hygiene: formatting fix and CI format check, backend lock file `uv.lock`, dependency audit, and build tools moved to devDependencies | ✅ | P1-24 – P1-27. The audit found 8 known vulnerabilities, cleared by upgrades (I-22, D-27; V-26 → V-27) |
| 2026-10-27 | Ran the API on the host for the first time; found and fixed a readiness hang when no database is reachable | ✅ | V-31 → V-32 (I-18, D-28) |
| 2026-10-27 | Checked the landing page in a browser; fixed the focus outline contrast | ✅ | V-33 – V-35 (I-19). Two minor issues logged (I-20, I-21) |
| 2026-10-27 | CI: v7 actions on `ubuntu-24.04`, backend installs with uv, and a new compose smoke job. Added `LICENSE` and updated the quickstart for uv | ✅ | D-24, D-26, P1-30 |
| 2026-10-27 | Pushed branch `phase1-hygiene` (commit `d9e50be`) | ✅ | Scanned first (V-37); all 3 CI jobs passed (V-36) |
| 2026-10-27 | Updated the repository description on GitHub | ✅ | Owner-approved text (D-25) |
| 2026-10-27 | Compose now passes the database connect timeout to the backend (commit `81262e8`) | ✅ | I-23; V-38 – V-40 |
| 2026-10-27 | Recorded this work in the tracker; `main` fast-forwarded to the branch commits and pushed with this update | ✅ | Staged files scanned first (V-41). The branch is deleted once `main` passes CI |
| 2026-10-27 | Arvind asked to download and install on D: whatever is possible; checked what this account can install | ✅ | No administrator rights, and WSL and Hyper-V are off, so a container runtime needs IT (V-42). conda-forge is blocked by this machine's network policy |
| 2026-10-27 | Installed under `D:\DevTools`, outside the repository: PostgreSQL 16.15 with pgvector 0.8.0 (built from source), Python 3.12.15, and Node.js 22.23.4 | ✅ | P1-31, P1-32; D-29, D-30. No administrator rights used; no PATH, registry, or Windows service changes (V-43 – V-45, V-50, V-51) |
| 2026-10-27 | Ran the app against the native database: migrations, pgvector's own tests, readiness, and the landing page's ready state | ✅ | V-46 – V-49. P1-21 done; I-03 resolved; new minor issues I-24 and I-25 |
| 2026-10-27 | Added helper scripts and a `README.txt` in `D:\DevTools` to start and stop the database and to run the checks on Python 3.12 and Node 22 | ✅ | V-52. Not part of the repository |
| 2026-10-27 | Recorded this work in the tracker and pushed it to `main` | ✅ | Staged files scanned first (V-54). CI for the previous push passed (V-53) |
| 2026-10-28 | Arvind installed Podman Desktop and asked to keep everything local, without a virtual machine of his own or administrator rights; checked what Podman Desktop provides | ✅ | It's only the GUI: the Podman engine needs WSL 2 or Hyper-V, which need administrator rights (V-56). Decided to develop without containers on this machine; Compose stays supported and tested in CI (D-31). B-01 and P1-17 – P1-20 on hold |
| 2026-10-28 | Vite listens on localhost only, and the README documents a setup without containers (commit `e4ccbf4`, pushed on branch `native-local-path`) | ✅ | I-24 resolved; P1-33. Scanned first (V-57); checked from a fresh clone (V-58 – V-60); all 3 CI jobs passed (V-61) |
| 2026-10-28 | Phase 1 definition of done met | ✅ | A fresh clone starts on this machine without containers, and CI passes without secrets (P1-16, P1-33). The repository description still matches what's built (D-25) |
| 2026-10-28 | Recorded this work in the tracker; `main` fast-forwarded to the branch commit and pushed with this update | ✅ | Staged files scanned first (V-62). CI for the previous push passed (V-55). The branch is deleted once `main` passes CI |
