# Project tracker — Evidence-backed Knowledge Assistant

| Field | Value | Remarks |
|---|---|---|
| Last updated | 2026-10-26 | Update at the end of every work session |
| Current stage | Phase 1 — repository and local foundation | Code and local checks are in place; the container stack and CI have never been run |
| Source of truth | [Project specification](../../README.md) | This tracker records progress against the spec; it does not replace it |
| GitHub repository | [tatpudiarvind/evidence-backed-knowledge-assistant](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant) | Created 2026-10-26 (public). First push from this folder on 2026-10-26 (D-18, P1-29). Personal notes stay local (D-21) |
| AI/RAG features | None yet | By design: Phase 1 is foundation only |
| Local checks (2026-10-26) | 18 passed, 2 failed | Open failure: `ruff format --check` on one file (I-09). The registry URLs in `package-lock.json` (V-15) were fixed before the push (V-17). Details in [02-verification-log.md](02-verification-log.md) |
| Measured metrics | None | Evaluation is Phase 5; never publish unmeasured numbers |
| Cloud resources / paid APIs | None | The default path stays local and free |

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
| P0 | Confirm environment and decisions | 🔄 In progress | 7 | 1 | 0 | 0 | 6 | 0 | 0 | ❌ No | Tool versions checked; hardware check and corpus/auth/model decisions still open |
| P1 | Repository and local foundation | 🔄 In progress | 29 | 13 | 5 | 1 | 7 | 3 | 0 | ❌ No | Code and local checks pass; first push in progress (P1-29). "Clean checkout starts locally and CI passes" not yet shown (B-01, B-02) |
| P2 | Workspace and document lifecycle | ⏳ Not started | 13 | 0 | 0 | 0 | 13 | 0 | 0 | ❌ No | Start after Phase 1 is done and the auth mode is decided (PD-01) |
| P3 | Ingestion and semantic indexing | ⏳ Not started | 12 | 0 | 0 | 0 | 12 | 0 | 0 | ❌ No | Needs corpus, embedding model, and PDF library decisions |
| P4 | Grounded question answering | ⏳ Not started | 10 | 0 | 0 | 0 | 10 | 0 | 0 | ❌ No | Needs the local LLM runtime decision (PD-05) |
| P5 | Evaluation and hardening | ⏳ Not started | 8 | 0 | 0 | 0 | 8 | 0 | 0 | ❌ No | No evaluation results exist yet |
| P6 | Portfolio polish and optional deployment | ⏳ Not started | 6 | 0 | 0 | 0 | 4 | 0 | 2 | ❌ No | Cloud deployment is optional and deferred |
| DOC | Documentation and tracking | 🔄 In progress | 5 | 2 | 0 | 1 | 2 | 0 | 0 | — | Spec and tracker done; upkeep ongoing |
| **Total** | | | **90** | **16** | **5** | **2** | **62** | **3** | **2** | | |

## Blockers

| ID | Blocker | Blocks | How to unblock | Who | Status | Remarks |
|---|---|---|---|---|---|---|
| B-01 | No container runtime: Docker and Podman were not found | P1-18 – P1-20, P2-13, and all live-database work | Install Docker Desktop, Rancher Desktop, or Podman (PD-13), then run the README quickstart | Arvind | ⛔ Open | Check license terms and IT policy on a managed machine. Native PostgreSQL + pgvector is a harder fallback on Windows |
| B-02 | CI has never run on GitHub: this folder was not a git repository or connected to the repository | P1-23, P5-05 | Push (P1-29), then confirm the first CI run passes (P1-23) | Implementation session | 🔄 In progress | Owner asked to push on 2026-10-26 (D-18) |

## Pre-push checklist

The GitHub repository is public, and anything pushed stays in git history. Run these checks before every push. Status below is for the first push on 2026-10-26.

| # | Check | Status | Related | Remarks |
|---|---|---|---|---|
| 1 | `frontend/package-lock.json` contains no internal registry URLs | ✅ Done | I-16, P1-28, V-17 | No `resolved` URLs; integrity hashes kept (D-19) |
| 2 | Decide whether to publish `04-skills-evidence.md` | ✅ Kept local | PD-12, D-21 | Git-ignored. To publish it, remove its line from `.gitignore` and commit it |
| 3 | Choose the commit author email | ✅ No-reply address | PD-15, D-20 | Set for this repository only; the global git identity is unchanged |
| 4 | Choose a license | ⏳ Open | PD-16 | Not blocking. Without one, others may view the code but have no right to reuse it |
| 5 | Make sure the repository description matches what's built | ⏳ Open | — | Your text, left unchanged. It describes citations and abstention, which aren't built yet; consider marking them as planned |
| 6 | Scan for secrets, internal hostnames, and personal data | ✅ Done | V-16, V-20, R-13 | Staged files scanned right before the first push; repeat before every push |
| 7 | `.env`, virtual environments, `node_modules`, and local data are git-ignored | ✅ Done | P1-11, V-20 | Confirmed with `git status` after `git init` |

## Next actions (in order)

| # | Action | Task IDs | Who | Remarks |
|---|---|---|---|---|
| 1 | Install a permitted container runtime | PD-13, P1-17 | Arvind | Unblocks most remaining Phase 1 checks |
| 2 | Run the quickstart and record the results in [02-verification-log.md](02-verification-log.md) | P1-18 – P1-21 | Arvind or implementation session | Move 🟡 items to ✅ only after a real run |
| 3 | Push to GitHub and confirm the first CI run passes | P1-29, P1-23 | Implementation session | Owner asked to push on 2026-10-26 (D-18) |
| 4 | Phase 1 hygiene: formatting and CI format step, backend lock file, pip-audit, devDependencies | P1-24 – P1-27 | Implementation session | Small changes; re-run all checks afterwards |
| 5 | Make the Phase 0 decisions and write down the configuration | P0-02 – P0-07 | Arvind | Needed before Phases 2–4 |
| 6 | Start Phase 2 | P2-01 onward | Implementation session | Only after the Phase 1 definition of done is met |

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
| 2026-10-26 | Arvind asked to push the project to GitHub; the assistant chose privacy-safe defaults for the open pre-push decisions | ✅ | Author email: GitHub no-reply address for this repository only (D-20); `04-skills-evidence.md` kept local (D-21); license still open (PD-16) |
| 2026-10-26 | Made `frontend/package-lock.json` registry-neutral: added `frontend/.npmrc` and regenerated the lockfile | ✅ | 0 registry URLs and unchanged versions (V-17); `npm ci` and all frontend checks pass (V-18); backend checks re-run (V-19) |
| 2026-10-26 | Initialized git in the project folder and scanned the staged files | ✅ | V-20. First push: P1-29 |
| 2026-10-26 | Updated the tracker: repository status, pre-push checklist, tasks P1-28 and P1-29, decisions D-16 and D-17, pending decisions PD-15 and PD-16, risk R-13, issue I-16 | ✅ | No code or configuration changed |
