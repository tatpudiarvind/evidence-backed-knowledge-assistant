# Project documents

Every document for the Evidence-backed Knowledge Assistant, with a folder for each kind. The [front page](../README.md) has the project summary and status.

| Folder | What it holds | Update when | Remarks |
|---|---|---|---|
| [specification](specification/README.md) | The project specification: goals, user stories, architecture and diagrams, code layout, data model and API, roadmap, testing, security, costs, and the local quickstart | A decision or a phase changes what is built or how to run it | The source of truth. Moved here from the root `README.md` on 2026-10-29 |
| [architecture](architecture/README.md) | How the code is built: the runtime view, the backend's layers, how a request is handled, background work, answering a question, the data model, the web app, and the main design choices and their limits | The code's structure, its background work, or its data model changes | Added in Phase 6 on 2026-10-31. Describes the code as it is; the specification records the design and its reasons |
| [api](api/README.md) | The HTTP API: conventions, signing in, every endpoint, errors and their codes, health and metrics, and limits | An endpoint, an error code, or a limit changes | Added in Phase 6 on 2026-10-31 |
| [security](security/README.md) | How accounts, workspaces, uploads, documents, and answers are protected; the production stack; dependencies; and the known gaps | A control, a limit, or a known gap changes | Added in Phase 6 on 2026-10-31. Not certified for regulated use |
| [operations](operations/README.md) | Running the production-style stack: starting it, settings, health, logs, metrics, a language model, backups, upgrades, removal, the end-to-end tests, what CI checks, troubleshooting, and what a real deployment adds | `compose.prod.yaml`, `frontend/nginx.conf`, the images, or CI changes | Added in Phase 6 on 2026-10-31. Steps CI doesn't cover are marked "Not tried yet" |
| [screenshots](screenshots/README.md) | Screenshots of the web app, taken by the end-to-end test in CI, with the conditions they were taken under | The web app's screens change | Added in Phase 6 on 2026-10-31. Synthetic data, no language model |
| [evaluation](evaluation/README.md) | How well the assistant finds passages and answers questions about a small synthetic set: the questions and documents, the scoring, the measured results and their conditions, trade-offs, and how to run it again | The questions, the test documents, the scoring, or the default retrieval settings change, or the evaluation is run again | Added in Phase 5 on 2026-10-30. Read every number with its conditions |
| [privacy](privacy/README.md) | What the app stores, logs, and sends, for how long, how to delete it, and what the network can reach | What the app stores, logs, sends, or keeps changes | Added in Phase 5 on 2026-10-30. Covers running on one computer, with or without containers; hosting isn't covered |
| [dev-tools](dev-tools/README.md) | The Windows development tools installed in `D:\DevTools` without administrator rights: what is there, how each was checked, and how to keep them up to date | A tool in `D:\DevTools` is added, updated, or removed | Specific to the owner's machine. Moved here from `D:\DevTools\README.txt` on 2026-10-29 |
| [tracker](tracker/README.md) | Progress against the specification: tasks, checks, decisions, risks, issues, and reference data | At the end of every work session | Start at its dashboard |

New kinds of documents get a folder of their own here.
