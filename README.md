# Evidence-backed Knowledge Assistant

A local-first web app, being built as a portfolio project, for asking questions about documents you upload. The goal is answers that use only those documents, cite the document and page or section behind each statement, and say so when the documents don't hold enough evidence, rather than guess.

It is a retrieval and summarization demo, not professional, medical, legal, or financial advice. Upload only public, synthetic, or licensed documents that you are allowed to use, and never real patient or confidential data.

## Status

Work in progress. As of 2026-10-29, Phases 0 to 3 of the [roadmap](docs/specification/README.md#10-implementation-roadmap-and-definition-of-done) are done:

- **Foundation:** a FastAPI backend, a React and TypeScript web app built with Vite, PostgreSQL with pgvector, Alembic migrations, health endpoints, Docker Compose, and GitHub Actions CI.
- **Accounts and documents:** local accounts, and workspaces that other users can't access; upload, list, download, and delete for PDF, Word (.docx), and plain-text files.
- **Indexing:** each uploaded document is split into chunks that keep their page or section, embedded on the CPU by a local model, and stored in pgvector. The web app shows each document's status as it changes, and a document that can't be indexed shows what to do and can be retried.

Next is Phase 4: questions, answers with citations, and abstaining when the evidence is weak. Nothing searches the documents or answers questions yet. Evaluation is Phase 5, so there are no quality measurements yet. Progress is recorded in the [project tracker](docs/tracker/README.md).

## Documentation

Every project document is in [`docs`](docs/README.md), with a folder for each kind of document.

| Document | What it covers | Remarks |
|---|---|---|
| [Documents index](docs/README.md) | The folders in `docs` and what each one holds | Start here to browse |
| [Specification](docs/specification/README.md) | Goals, user stories, architecture and diagrams, code layout, data model and API, roadmap, testing, security, costs, and the local quickstart | The source of truth. It was this README until 2026-10-29 |
| [Development tools](docs/dev-tools/README.md) | The Windows tools installed in `D:\DevTools` on the owner's machine without administrator rights: PostgreSQL with pgvector, Python 3.12, Node.js 22, Ollama and its model, and the embedding model | Specific to one machine; the general steps are in the specification's quickstart |
| [Project tracker](docs/tracker/README.md) | Dashboard: stage, phase summary, blockers, next actions, and change log | Updated at the end of every work session |
| [Task tracker](docs/tracker/01-task-tracker.md) | Every task by phase, with status, dependencies, and evidence | Done only with evidence |
| [Verification log](docs/tracker/02-verification-log.md) | The environment, and every check with its command and result | Failed checks stay listed next to their fixes |
| [Decisions, risks, and issues](docs/tracker/03-decisions-risks-issues.md) | Decisions and their reasons, pending decisions, risks, issues, and differences from the specification | Licenses and alternatives for each technology choice |
| [Project reference](docs/tracker/05-project-reference.md) | Files, dependency versions, environment variables, ports, API endpoints, and commands | Reference data, not status |

## Run it locally

Follow the [local quickstart](docs/specification/README.md#local-quickstart), which uses Docker Compose, or the steps [without containers (no administrator rights)](docs/specification/README.md#without-containers-no-administrator-rights). Either way, indexing needs the embedding model (about 135 MB), downloaded once:

```powershell
# With Docker Compose, from the project root
docker compose run --rm backend python -m app.cli download-embedding-model

# Without containers, from the backend folder
uv run python -m app.cli download-embedding-model
```

Documents that failed because the model was missing can then be retried in the web app.

## License

Released under the [MIT License](LICENSE).
