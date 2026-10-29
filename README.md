# Evidence-backed Knowledge Assistant

A local-first web app, being built as a portfolio project, for asking questions about documents you upload. The goal is answers that use only those documents, cite the document and page or section behind each statement, and say so when the documents don't hold enough evidence, rather than guess.

It is a retrieval and summarization demo, not professional, medical, legal, or financial advice. Upload only public, synthetic, or licensed documents that you are allowed to use, and never real patient or confidential data.

## Status

Work in progress. As of 2026-10-29, Phases 0 to 4 of the [roadmap](docs/specification/README.md#10-implementation-roadmap-and-definition-of-done) are done:

- **Foundation:** a FastAPI backend, a React and TypeScript web app built with Vite, PostgreSQL with pgvector, Alembic migrations, health endpoints, Docker Compose, and GitHub Actions CI.
- **Accounts and documents:** local accounts, and workspaces that other users can't access; upload, list, download, and delete for PDF, Word (.docx), and plain-text files.
- **Indexing:** each uploaded document is split into chunks that keep their page or section, embedded on the CPU by a local model, and stored in pgvector. The web app shows each document's status as it changes, and a document that can't be indexed shows what to do and can be retried.
- **Questions and answers:** questions about a workspace's documents are matched to their closest passages. A local model, run by Ollama, writes an answer that cites the document and page or section of each passage it uses; without the model, the closest passages are the answer. When the documents don't cover a question, the app says so instead of guessing. Questions and answers are kept for 3 days.

Next is Phase 5: evaluation and hardening. Answer quality hasn't been measured yet, so there are no quality measurements; Phase 5 measures retrieval and citations on a small reviewed set of questions. Progress is recorded in the [project tracker](docs/tracker/README.md).

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

Answers written by a model are optional. Without containers, the API uses [Ollama](https://ollama.com/download) on your machine when it's running and its model is pulled (`ollama pull qwen3:4b-instruct-2507-q4_K_M`, about 2.5 GB); otherwise, and by default under Docker Compose, answers list the closest passages. The quickstart explains the settings.

## License

Released under the [MIT License](LICENSE).
