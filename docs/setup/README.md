# Installation and setup guide

For a developer who is new to this project and wants to run it, change it, and pick up the unfinished work. It says what to install, how to check each step, what has and hasn't been tried, and where to start.

Everything here is for development on a local machine. Use only public, synthetic, or licensed documents, never real patient or confidential data. The app isn't certified for regulated or clinical use.

## 1. What you are setting up

| Part | What it is | Where it lives |
| --- | --- | --- |
| API | Python 3.12 FastAPI app: accounts, workspaces, uploads, indexing, search, answers | `backend/` |
| Web app | React, TypeScript and Vite single-page app | `frontend/` |
| Database | PostgreSQL 16 with the pgvector 0.8 extension | Compose service `db`, or your own server |
| Embedding model | `sentence-transformers` model, about 135 MB, downloaded once | `backend/models`, or `EMBEDDING_MODEL_DIR` |
| Language model (optional) | Ollama, to write answers. Without it, answers list the closest passages | Your machine |
| End-to-end tests | Playwright | `e2e/` |
| Evaluation | Synthetic documents and questions, plus a scoring command | `evals/` |

You can run it two ways. **Path A** uses Docker Compose and is the shortest. **Path B** runs PostgreSQL, the API and the web app directly on your machine, and needs no Docker or administrator rights.

## 2. What to install

| Tool | Version | Needed for | Required? |
| --- | --- | --- | --- |
| Git | any recent | Cloning the repository | Yes |
| Docker Desktop, or Docker Engine with the Compose plugin | Compose v2 | Path A, the production-style stack, the end-to-end tests | Path A only |
| Python | 3.12 (CI uses 3.12; the code requires 3.12 or newer) | Path B, backend checks | Path B only |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | 0.13.5 (the version CI uses) | Installing the locked backend dependencies | Path B only |
| Node.js | 22 (CI uses 22) | Web app, end-to-end tests | Path B, and for any frontend or e2e work |
| PostgreSQL and pgvector | PostgreSQL 16, pgvector 0.8.0 | Path B database | Path B only |
| [Ollama](https://ollama.com/download) and the model `qwen3:4b-instruct-2507-q4_K_M` | any recent; the model is about 2.5 GB | Written answers | No |
| A GPU | any | Faster written answers | No |
| Visual Studio C++ build tools | any recent | Building pgvector from source on Windows | Only if you build pgvector yourself |

Disk and memory: expect several GB. The first backend install downloads PyTorch, and the embedding model is another 135 MB. This guide gives no memory or speed figures, because none were measured across machines.

## 3. Get the code and the settings

```powershell
git clone https://github.com/tatpudiarvind/evidence-backed-knowledge-assistant.git
cd evidence-backed-knowledge-assistant
cp .env.example .env
```

One root `.env` file feeds Compose, the API and the Vite dev server. `.env` is git-ignored: never commit it. The defaults work for local development. The password in `.env.example` (`local_dev_only`) is for local use only; change it before sharing a host. Every setting is explained in a comment in `.env.example`.

## 4. Path A: Docker Compose

From the project root:

```powershell
docker compose up --build -d
docker compose run --rm backend python -m app.cli download-embedding-model
```

Open `http://localhost:5173`. The page should report the API and database as ready. Create an account, then a workspace, and upload a document.

- Migrations run by themselves each time the stack starts.
- Documents uploaded before the model download fail with a message asking for it. Select **Retry** after the download.
- Under Compose, answers list the closest passages, because `LLM_PROVIDER=none` there. To use Ollama, see [section 7](#7-optional-ollama-for-written-answers).
- Stop with `docker compose down`. `docker compose down -v` also deletes the database, uploads and model, so use it only on purpose.

### The production-style stack

nginx serves the built web app on `http://localhost:8080`, and only nginx is reachable. It needs a `POSTGRES_PASSWORD` in `.env`. The steps are in the [operations guide](../operations/README.md#running-the-production-style-stack).

## 5. Path B: without containers

### 5.1 PostgreSQL 16 with pgvector 0.8.0

Put both in a folder you own. On Windows, EDB's [binaries zip](https://www.enterprisedb.com/download-postgresql-binaries) needs no installer, and pgvector is built from source with `nmake` ([instructions](https://github.com/pgvector/pgvector/tree/v0.8.0#windows)). On Linux or macOS, use your package manager's PostgreSQL 16 and pgvector packages. Then:

```powershell
initdb -D <data-folder> -U knowledge_assistant -A scram-sha-256 -E UTF8 --locale=C --pwprompt
pg_ctl -D <data-folder> -l <log-file> start
createdb -U knowledge_assistant knowledge_assistant
```

Enter the password from `.env.example` when prompted. The `knowledge_assistant` user must be the cluster's superuser: the first migration runs `CREATE EXTENSION vector`, and the backend tests create their own database. Don't run this server and the Compose database together, because both use port 5432. Stop one, or set `POSTGRES_PORT` in `.env`.

### 5.2 The API

From `backend`:

```powershell
uv sync --locked --extra dev
uv run alembic upgrade head
uv run python -m app.cli download-embedding-model
uv run uvicorn app.main:app --reload
```

The first `uv sync` is slow because it downloads PyTorch. If `uv` fails with a certificate error behind a corporate proxy, add `--system-certs`. The API listens on `http://localhost:8000`; check `/health/live` and `/health/ready` there.

### 5.3 The web app

In a second terminal, from `frontend`:

```powershell
npm ci
npm run dev
```

Open `http://localhost:5173`.

## 6. Check your setup

Run these before you change anything, so you know the starting point is good.

| Check | Command | Directory |
| --- | --- | --- |
| Lint | `uv run ruff check .` | `backend` |
| Format | `uv run ruff format --check .` | `backend` |
| Types | `uv run mypy app` | `backend` |
| Tests | `uv run pytest` | `backend` |
| Web lint, types, tests, build | `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` | `frontend` |
| Evaluation agrees with the committed results | `uv run python -m app.cli evaluate --output <temp file>`, then `uv run python -m app.cli compare-results ../evals/results/retrieval-only.json <temp file>` | `backend` |

Notes:

- The API tests need PostgreSQL. They use their own database, `knowledge_assistant_test`, on `127.0.0.1:5432` with the development credentials. Without a reachable server they are skipped; `TEST_DATABASE_REQUIRED=1` makes them fail instead, as CI does.
- One test loads the real embedding model. It is skipped when the model is missing; `TEST_MODEL_REQUIRED=1` makes it fail. A second real-model test, for the reranker, is skipped unless that model is downloaded (see [section 9](#9-whats-lacking-or-untried)).
- Tests never call Ollama or any hosted model.
- End-to-end tests need the production-style stack and Docker; see the [operations guide](../operations/README.md). They also run in CI.
- A `dist/` folder appears in `frontend` after a build; it is git-ignored.

CI (`.github/workflows/ci.yml`) runs the same checks on Python 3.12 and Node 22, plus a Compose smoke test, the production images with the end-to-end tests, and a Keycloak sign-in job. A separate `Dependency audit` workflow audits the locked dependencies.

## 7. Optional: Ollama for written answers

1. Install Ollama as your own user and start it: `ollama serve`.
2. Pull the model once: `ollama pull qwen3:4b-instruct-2507-q4_K_M` (about 2.5 GB).
3. With Path B the defaults (`LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://127.0.0.1:11434`) use it at once. While it isn't running, answers list the closest passages.
4. Under Compose, run Ollama where the API container can reach it and set `COMPOSE_LLM_PROVIDER=ollama` and `COMPOSE_OLLAMA_BASE_URL` in `.env`. **This Compose setup has not been tried.**
5. Without a suitable GPU the model can be much slower; raise `LLM_TIMEOUT_SECONDS` (at most 600) if answers time out. Set `LLM_PROVIDER=none` to stop asking it.

## 8. Other optional pieces

- **Try it with sample files.** From `backend`: `uv run python -m app.cli write-demo-files` writes synthetic documents to `demo-files/`. See [trying it out](../operations/README.md#trying-it-out).
- **Retrieval modes.** `RETRIEVAL_MODE=vector` is the default. `hybrid` adds keyword matching. `hybrid_rerank` also needs `uv run python -m app.cli download-reranker-model`. Read the [evaluation](../evaluation/README.md) before changing the default.
- **Background worker.** `INDEXING_RUNNER=embedded` (default) indexes inside the API. `worker` runs `python -m app.worker`, or the optional Compose worker profile.
- **Sign-in through an OpenID Connect provider.** `AUTH_MODE=local` is the default. See the [operations guide](../operations/README.md) for the `OIDC_` settings. Switching an existing install to `oidc` locks out password accounts; `both` allows either.
- **A hosted language model.** `LLM_PROVIDER=openai_compatible` with `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`. No vendor has been chosen. Sending document text to a vendor needs your approval of the vendor, its terms and its cost first.
- **Metrics and logs.** `METRICS_ENABLED=true` serves `/metrics`; `LOG_FORMAT=json` gives one JSON object per line.

## 9. What's lacking or untried

Be clear about these before you rely on them. The [tracker](../tracker/README.md) has the full record, with IDs.

| Item | State | What to do |
| --- | --- | --- |
| Docker Compose on the original author's machine | The stack has only been run in CI (GitHub's runners); Docker wasn't installed on that machine | Run Path A or the production-style stack yourself and note any surprise |
| Compose with Ollama | Not tried | Follow step 4 in [section 7](#7-optional-ollama-for-written-answers) and record the result |
| `hybrid_rerank` retrieval | Implemented but **not measured**: the reranker model couldn't be downloaded on the author's machine (B-03), so its real-model test is skipped | Download the reranker, run the evaluation, and publish numbers only after measuring. The chosen model has an MS MARCO non-commercial limitation; an MIT-licensed alternative is recorded in the tracker |
| A hosted language model | The adapter is built and tested against a stub server. **No vendor was chosen or called** | Pick a vendor deliberately, check its terms and cost, then try it |
| Hosted sign-in provider | Keycloak is tested in CI. No hosted provider was tried | Try one and record the result |
| Keycloak by hand | Not tried outside CI | Optional |
| Linking a provider to an existing account, and provider logout | Not built | Design and build if needed |
| Cloud deployment | Not started; no cloud was chosen | Only after a local cost check (see the [operations guide](../operations/README.md) and the [roadmap](../roadmap/README.md)). Don't assume a free tier persists; set a billing alert and plan teardown |
| Evaluation sets | Small, synthetic, and reviewed by one person | Have someone independent review the questions before treating results as more than a demo |
| Rate limits | Counted in the API's memory, so they reset on restart and don't span several API processes | Move them to shared storage if you run more than one process |
| Windows issue R-19 | Partly open | See the tracker's risk register |
| Resume claims | The skills evidence file is git-ignored on purpose and holds placeholders | Claim a skill only once you've done the work |

## 10. Pick up the work

1. Read the project's front page (`README.md` in the repository root), then the [architecture](../architecture/README.md), [API reference](../api/README.md) and [security guide](../security/README.md).
2. Read the [tracker](../tracker/README.md). Its "next actions" table lists what remains, and the [roadmap](../roadmap/README.md) has the design for each later phase.
3. Work on a branch, one concern per branch. Run the section 6 checks before pushing.
4. When you add a dependency, run a dependency audit locally first. A past audit failure (I-46) came from pushing an unaudited pin.
5. Record what you verified in the tracker's verification log, and don't write numbers or claims for runs you didn't make.
6. Keep `.env` files out of commits, and leave the git-ignored `docs/project-guide` and `docs/tracker/04-skills-evidence.md` alone unless you own them.

## 11. Common problems

| Symptom | Likely cause and fix |
| --- | --- |
| `/health/ready` answers 503 | PostgreSQL isn't running or `DATABASE_URL` is wrong. Start the database and check port 5432 |
| Port 5432 already in use | Two PostgreSQL servers. Stop one, or set `POSTGRES_PORT` |
| Migration fails on `CREATE EXTENSION vector` | pgvector isn't installed, or the user isn't a superuser |
| Documents show **Failed** with a message about the model | The embedding model isn't downloaded. Run `download-embedding-model`, then select **Retry** |
| API tests are skipped | No PostgreSQL reachable. Start it, or set `TEST_DATABASE_REQUIRED=1` to make this an error |
| `uv` or `npm` certificate errors behind a proxy | `uv ... --system-certs`; for npm, configure your registry and certificates |
| Answers only list passages | Ollama isn't running, the model isn't pulled, or `LLM_PROVIDER=none` (the Compose default) |
| Answers time out | Raise `LLM_TIMEOUT_SECONDS` (at most 600), or use a smaller model |
| Sign-in fails after switching `AUTH_MODE` | `oidc` mode refuses password accounts. Use `both`, or check all the `OIDC_` settings |

## 12. Removing everything

`docker compose down -v` removes the Compose database, uploads and model. For Path B, stop PostgreSQL (`pg_ctl -D <data-folder> stop`) and delete your data folder, `backend/models`, `backend/storage` and `node_modules`.
