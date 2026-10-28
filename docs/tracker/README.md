# Project tracker — Evidence-backed Knowledge Assistant

| Field | Value | Remarks |
|---|---|---|
| Last updated | 2026-10-28 | Update at the end of every work session |
| Current stage | Phases 0 – 2 done — next: Phase 3 | Phase 2 was built and checked on 2026-10-28: local accounts, workspaces, and upload, list, download, and delete for PDF, DOCX, and TXT files, with each user's workspaces kept apart (P2-01 – P2-14). 152 backend tests pass on Python 3.14 and 3.12, including 66 integration tests run with the PostgreSQL test database (V-77, V-78); 43 frontend tests pass on Node 24 and 22 (V-83), 46 since the small fixes below (V-98); a browser walkthrough on this machine covered sign-up, uploads, download, delete, sign-out, and a second account (V-87 – V-91). Uploaded files are stored but not read until Phase 3. A fresh clone starts on this machine without containers (V-58 – V-60). CI passes, including the Phase 2 database tests against its own PostgreSQL (V-93, V-94), and also builds and runs the container stack on GitHub's Linux runner (V-36, V-61). Containers on this machine are on hold by choice: everything stays local, without a virtual machine or administrator rights (D-31). Ollama and the chosen LLM are installed under `D:\DevTools` and gave a first cited answer on the GPU (P4-12; V-70 – V-74); the embedding model comes with Phase 3 (P3-05). Four small issues found in the Phase 1 and 2 checks were fixed on 2026-10-28 (I-20, I-21, I-25, I-28; V-97 – V-100) |
| Source of truth | [Project specification](../../README.md) | This tracker records progress against the spec; it does not replace it |
| GitHub repository | [tatpudiarvind/evidence-backed-knowledge-assistant](https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant) | Created 2026-10-26 (public; MIT license since 2026-10-27, D-23). Pushed: foundation `f5f4edc` (2026-10-26); hygiene `d9e50be` and the Compose fix `81262e8` (2026-10-27); the setup without containers `e4ccbf4` (2026-10-28); Phase 2 `e9fa923` (2026-10-28), through branch `phase2-workspaces-documents`, deleted once `main` passed CI. CI passes (V-21, V-36, V-40, V-53, V-55, V-61, V-63, V-68, V-76, V-93, V-94, V-96). Personal notes stay local (D-21) |
| AI/RAG features | None yet | The tools are chosen (D-32 – D-36), and the local LLM is installed on this machine (P4-12), but the app doesn't use it yet. Uploaded documents are stored but not read yet. Building starts in Phase 3 (ingestion) and Phase 4 (answers) |
| Checks (2026-10-28) | 94 passed, 7 failed | Every failure has been fixed: V-03 by V-23, V-15 by V-17, V-26 by V-27, V-31 by V-32, V-34 by V-35, V-82 by V-83, V-85 by V-86. CI checks (V-21, V-36, V-40, V-53, V-55, V-61, V-63, V-68, V-76, V-93, V-94, V-96) ran on GitHub's runner, not this machine. V-42 – V-52 cover the tools installed under `D:\DevTools`; V-58 – V-60 cover the setup without containers from a fresh clone; V-64 – V-66 cover the Phase 0 research and library checks; V-69 – V-74 cover Ollama and its model; V-77 – V-91 cover Phase 2: checks on both Python and both Node versions, migrations, audits, and a browser walkthrough; V-92 is its staged-file review, and V-93 and V-94 its CI runs; V-95 reviews the follow-up tracker update, and V-96 is its CI run; V-97 – V-100 cover the small fixes (timings, checks on both Python and both Node versions, and a browser check), and V-101 reviews this update. Details in [02-verification-log.md](02-verification-log.md) |
| Measured metrics | None | Evaluation is Phase 5; never publish unmeasured numbers. The Ollama timings in V-71 – V-74 are single observations, not benchmarks |
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
| P0 | Confirm environment and decisions | ✅ Done | 7 | 7 | 0 | 0 | 0 | 0 | 0 | ✅ Yes | Met on 2026-10-28: tools and hardware checked; sample documents, login, embedding model, PDF library, LLM, and layout chosen (D-32 – D-37) |
| P1 | Repository and local foundation | ✅ Done | 33 | 29 | 0 | 0 | 0 | 0 | 4 | ✅ Yes | Met on 2026-10-28: a fresh clone starts on this machine without containers (P1-33; V-58 – V-60), and CI passes without secrets (V-36, V-61). The 4 deferred tasks run Compose on this machine, which is on hold (P1-17 – P1-20, D-31) |
| P2 | Workspace and document lifecycle | ✅ Done | 14 | 14 | 0 | 0 | 0 | 0 | 0 | ✅ Yes | Met on 2026-10-28: integration tests against PostgreSQL show that another user can't list, read, download, or delete a workspace's documents, or upload to it, and invalid uploads are rejected and leave no stored file (P2-12; V-77, V-78). A browser walkthrough with a second account showed the same (V-91). CI passes with the test database (P2-13; V-93, V-94) |
| P3 | Ingestion and semantic indexing | ⏳ Not started | 12 | 1 | 0 | 0 | 11 | 0 | 0 | ❌ No | Only the PDF library choice is done, decided early (P3-01, D-35). The embedding model's download will most likely need the Windows certificate store (R-16); tests use a fake embedder |
| P4 | Grounded question answering | ⏳ Not started | 12 | 1 | 0 | 0 | 11 | 0 | 0 | ❌ No | Only the Ollama install is done, early, after Arvind asked for it (P4-12, D-38). Search-only answers (P4-11) work without a model |
| P5 | Evaluation and hardening | ⏳ Not started | 8 | 0 | 0 | 0 | 8 | 0 | 0 | ❌ No | No evaluation results exist yet |
| P6 | Portfolio polish and optional deployment | ⏳ Not started | 6 | 0 | 0 | 0 | 4 | 0 | 2 | ❌ No | Cloud deployment is optional and deferred |
| DOC | Documentation and tracking | 🔄 In progress | 5 | 3 | 0 | 1 | 1 | 0 | 0 | — | Spec, tracker, and the host-run workflow are done, including which `.env` file the backend reads (DOC-01 – DOC-03; D-40). The spec was updated for Phase 2 on 2026-10-28. Upkeep is ongoing (DOC-05) |
| **Total** | | | **97** | **55** | **0** | **1** | **35** | **0** | **6** | | |

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
| 5 | Make sure the repository description matches what's built | 🔄 Update proposed | D-25 | Updated 2026-10-27 with owner-approved text that marks the project as work in progress; reviewed after Phases 0 and 1 on 2026-10-28. It ends "Done so far: the Phase 1 foundation.", so after Phase 2 it understates what's built but claims nothing that isn't. Proposed new ending: "Done so far: the foundation (Phase 1) and local accounts, workspaces, and document upload (Phase 2)." Waiting for Arvind's approval; review it whenever a phase completes |
| 6 | Scan for secrets, internal hostnames, and personal data | ✅ Done | V-16, V-20, V-37, V-39, V-41, V-54, V-57, V-62, V-67, V-75, V-92, V-95, V-101, R-13 | Staged files scanned before every push so far; repeat before every push. Since Phase 2, the email and password patterns match test code, so review those matches by hand (V-92) |
| 7 | `.env`, virtual environments, `node_modules`, and local data are git-ignored | ✅ Done | P1-11, V-20 | Confirmed with `git status` after `git init` |

## Next actions (in order)

| # | Action | Task IDs | Who | Remarks |
|---|---|---|---|---|
| 1 | Start Phase 3: read the uploaded PDF, DOCX, and TXT files into chunks that keep their page locations, embed the chunks, and index them in pgvector, so documents move from `queued` to `ready` or `failed` | P3-02 – P3-12 | Implementation session | Phase 2 is done. The parsers and chunking (P3-02 – P3-04) come first and don't need the embedding model |
| 2 | When P3-05 starts: download the embedding model into a folder under `D:\DevTools`, through the Windows certificate store | P3-05, NV-11, R-16 | Implementation session | Hugging Face is reachable again (V-69). It's reached through TLS inspection, so Python's own certificate bundle will most likely be rejected; never turn certificate checks off. The LLM is already installed (P4-12) |
| 3 | Approve or change the proposed repository description ([pre-push checklist](#pre-push-checklist) item 5) | D-25 | Arvind | It still lists only Phase 1 |
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
| 2026-10-28 | Researched the Phase 0 options: licenses, versions, and download sites; tried the parsing and password-hashing libraries on Python 3.12 and 3.14 | ✅ | V-64 – V-66. The model sites (Hugging Face and Ollama's model library) are blocked by the network policy on this machine (I-26); not bypassed |
| 2026-10-28 | Arvind answered the Phase 0 decisions and left the details to the assistant; recorded the choices and updated the spec (§4, §7, §9, §15) | ✅ | D-32 – D-37. Phase 0 definition of done met. P3-01 done early; new tasks P2-14 and P4-11 |
| 2026-10-28 | Recorded this work in the tracker and pushed it to `main` | ✅ | Staged files scanned first (V-67). CI for the previous push passed (V-63), and branch `native-local-path` was deleted |
| 2026-10-28 | Arvind sent Ollama's one-line install command; installed the same Ollama release from its portable zip under `D:\DevTools` instead, downloaded the pinned model, and checked both | ✅ | D-38, P4-12; V-69 – V-74. The command's script was read but not run: by default it installs on C: and changes the user PATH and registry. The model sites answer again (I-26 resolved). Helper scripts and `D:\DevTools\README.txt` updated; not part of the repository |
| 2026-10-28 | Recorded this work in the tracker, named the pinned model tag in spec §4 and §15, and pushed it to `main` | ✅ | Staged files scanned first (V-75). CI for the previous push passed (V-68) |
| 2026-10-28 | Built Phase 2 on branch `phase2-workspaces-documents`: local accounts with sign-in, workspaces, and upload, list, download, and delete for PDF, DOCX, and TXT files, in the API and the web app | ✅ | P2-01 – P2-14; D-39 – D-44. Backend checks on Python 3.14 and 3.12 with the PostgreSQL test database (V-77 – V-80), frontend checks (V-81 – V-83), dependency audits (V-84 – V-86), and a browser walkthrough (V-87 – V-91). I-06, I-07, I-08, and DEV-04, DEV-05 resolved; new risk R-18 and minor issue I-28 |
| 2026-10-28 | Fixed two frontend tests that failed only on Node 22, the version CI uses | ✅ | I-27; V-82 → V-83. Only the test helper changed; the app itself was unaffected |
| 2026-10-28 | `npm audit` on this machine now names the public registry, because the registry this machine's npm uses asks for a sign-in | ✅ | V-85 → V-86. The command is in [05-project-reference.md](05-project-reference.md#8-commands) |
| 2026-10-28 | Updated the spec for Phase 2: §6 upload path, §7 code layout, §9 data model, endpoints, and error contract, and a "Local quickstart" with the root `.env` and the test database | ✅ | D-39 – D-44; DOC-03 done (D-40) |
| 2026-10-28 | Phase 2 definition of done met | ✅ | Integration tests against PostgreSQL show that another user can't list, read, download, or delete a workspace's documents, and invalid uploads are rejected and leave no stored file (P2-12; V-77, V-78). The repository description now understates what's built; a new ending is proposed and waits for Arvind's approval (D-25) |
| 2026-10-28 | Recorded this work in the tracker and pushed it on branch `phase2-workspaces-documents` | ✅ | Staged files scanned first (V-92). CI for the previous push passed (V-76). The branch's CI and the merge to `main` are recorded in a follow-up update |
| 2026-10-28 | CI passed on the branch; `main` fast-forwarded to `e9fa923` and pushed; CI passed on `main`; the branch was deleted on GitHub and locally | ✅ | V-93, V-94: the first CI runs with the PostgreSQL test service and the smoke job's document step (P2-13, P1-30) |
| 2026-10-28 | Recorded the CI results in the tracker and pushed it to `main` | ✅ | Staged files scanned first (V-95). CI for the previous push passed (V-94) |
| 2026-10-28 | Fixed four small issues from the Phase 1 and 2 checks on branch `small-fixes`: "Check again" keeps focus during a repeat readiness check, and focus moves to the status once the services are ready; a favicon; readiness answers 503 in about 3 s instead of 6 s while the database is down, because the default database URLs use `127.0.0.1`; switching between the sign-in forms hides the sign-out message | ✅ | I-20, I-21, I-25, and I-28 resolved. Timings (V-97), checks on both Node and both Python versions with 3 new frontend tests (V-98, V-99), and a browser check (V-100) |
| 2026-10-28 | Recorded this work in the tracker and pushed it on branch `small-fixes` | ✅ | Staged files scanned first (V-101). CI for the previous push passed (V-96). The branch's CI and the merge to `main` are recorded in the next update |
