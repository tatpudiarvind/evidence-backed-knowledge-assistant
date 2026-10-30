# Privacy and data handling

What the Evidence-backed Knowledge Assistant keeps, where it keeps it, for how long, and how to remove it. This page describes the code as of Phase 5 (2026-10-30). The requirements it follows are in the [specification](../specification/README.md#12-security-privacy-and-operational-requirements).

The assistant is a local demo of document retrieval and summarization. It isn't certified for regulated or clinical use, and its answers aren't professional, medical, legal, or financial advice. Upload only public, synthetic, or licensed documents you're allowed to use, and never real patient or confidential data.

## At a glance

| What | Where | Kept until |
|---|---|---|
| Accounts: email address and password hash | PostgreSQL: `users` | Local data is cleared; accounts can't be deleted yet |
| Sign-in sessions: a hash of each session's token | PostgreSQL: `user_sessions` | Sign-out. An expired session stays until its user signs in again, but can't be used |
| Workspaces: name and owner | PostgreSQL: `workspaces`, `workspace_memberships` | Local data is cleared; workspaces can't be deleted yet |
| Uploaded files | The storage folder | The document is deleted |
| Document details, and its text and embeddings in chunks | PostgreSQL: `documents`, `document_chunks` | The document is deleted |
| Questions, answers, and citations | PostgreSQL: `questions`, `answers`, `citations` | 3 days after the question was asked, or sooner when a document an answer cites is deleted |
| The session cookie | The browser | Sign-out, or 12 hours by default |
| Logs | Standard error: a terminal, or Docker's container logs | As long as you keep them |
| Metrics and rate-limit counters | The API's memory | The API restarts |
| The embedding model | `backend/models`, or the `embedding_models` volume | You delete it |

## What is stored

### Accounts and sessions

- Registering stores an email address, trimmed and lower-cased, and an Argon2 hash of the password. The password itself is never stored or logged.
- Signing in creates a session. The browser gets a random token in the `eka_session` cookie, and the database keeps only the token's SHA-256 hash, with the times the session started and expires.
- The cookie is `HttpOnly`, so page scripts can't read it, and `SameSite=Strict`. It is marked `Secure` only when `SESSION_COOKIE_SECURE=true`: set that whenever the app is served over HTTPS. Sessions last `SESSION_LIFETIME_HOURS`, 12 by default.
- Signing out deletes the session. Signing in replaces the browser's previous session and deletes the user's expired ones.
- Registration is open by default. Set `REGISTRATION_ENABLED=false` once your accounts exist.

### Workspaces and documents

- A workspace has a name and an owner. Its only member is the user who created it, because workspaces can't be shared yet. Every database query that returns workspace data checks membership itself.
- Uploading a document stores:
  - **the file**, under a random 32-character name in the storage folder's `documents` folder. The original file name is never used on disk. While a file arrives, it is written to the storage folder's `tmp` folder. A rejected, interrupted, or timed-out upload is deleted from there, so a partial file is left only if the API process itself stops mid-upload.
  - **its details**, in `documents`: the file name as shown (the original name, without folders or invisible characters), the file type, its size, its SHA-256 hash, the indexing status, and why indexing failed, if it did.
  - **its text**, once indexed, in `document_chunks`: the document's text in chunks, each with its page number or section heading and its embedding, 384 numbers computed from the text. Embeddings are derived from the text, so treat them as just as sensitive.
- Downloads are sent with `Cache-Control: no-store`, so the browser shouldn't keep a cached copy. A copy you save is yours to look after.

### Questions and answers

- Asking a question stores its text, who asked it, the workspace, and when. The answer stores its text, or why the assistant declined, and the model that wrote it, or that search-only mode did. Each citation stores the document, the chunk, the citation's number, and the passage's similarity to the question.
- The model's raw reply isn't stored: only the answer that passed the citation check.
- Only the user who asked a question sees it in the history.

### In the browser

- The session cookie is all the web app keeps in the browser. It uses no local storage, session storage, or IndexedDB.
- The web app loads nothing from other sites: no fonts, scripts, or analytics. It talks only to the API.

## Retention and deletion

- **Questions and answers: 3 days.** The history hides a question once it is 3 days old. A cleanup thread in the API deletes it, with its answer and citations, when the API starts and then every hour (decisions D-55 and D-62). While the API isn't running, or with `QUESTION_CLEANUP_ENABLED=false`, expired questions stay in the database, hidden, until the cleanup runs.
- **Documents: until you delete them.** Deleting a document first marks it `deleting` and deletes every question whose answer cites it, in one transaction. It then deletes the stored file, and finally the document's row, which takes its chunks with it. If the file can't be deleted, the API answers `500 document_delete_failed` and the document stays visible, so you can delete it again.
- **Accounts and workspaces: no deletion yet.** There is no endpoint or button for either. Deleting their database rows by hand would leave their documents' files in the storage folder, so [clear all local data](#clearing-all-local-data) instead.
- **Deleting isn't erasing.** PostgreSQL leaves deleted rows in its files until it vacuums them, and its write-ahead log can keep copies for a while. A deleted file's bytes stay on the disk until they are overwritten. The app doesn't encrypt its database or files, so use disk encryption on a computer that others use or that could be lost.
- **No backups.** The app makes none. Backups you make keep what the app later deletes.

## Clearing all local data

Without containers:

1. Stop the API (Ctrl+C).
2. With PostgreSQL's `bin` folder on `PATH`, drop the database: `dropdb -U knowledge_assistant knowledge_assistant`. Drop `knowledge_assistant_eval` and `knowledge_assistant_test` too if they exist; the evaluation and the tests made them, and they hold only synthetic data.
3. Delete the storage folder: `backend/storage`, or the folder `STORAGE_DIR` names.
4. Delete logs you saved.
5. Optionally, delete the embedding model: `backend/models`, or the folder `EMBEDDING_MODEL_DIR` names. It holds no user data, and you'll have to download it again.

To start again, create the database (`createdb -U knowledge_assistant knowledge_assistant`) and apply the migrations from `backend` (`uv run alembic upgrade head`).

With Docker Compose, `docker compose down -v` removes the containers, with their logs, and the volumes: the database (`postgres_data`), the uploaded files (`document_storage`), the embedding model (`embedding_models`), and the web app's packages (`frontend_node_modules`).

Ollama keeps its models in its own folder. The app asks it to keep nothing; see [what leaves your computer](#what-leaves-your-computer).

## Logs

The API logs to standard error, as text or, with `LOG_FORMAT=json`, as one JSON object per line. Under Compose, Docker keeps each container's log until the container is removed, which `docker compose down` does.

- **Requests.** Each request is logged once, by its method, its route's template (such as `GET /api/v1/documents/{document_id}`), its status, and its duration. Client addresses, query strings, and the IDs in paths are left out; Uvicorn's own access log, which records them, is turned off.
- **Events.** Other lines name things by their random IDs and count them: a document indexed into a number of chunks, or failed with an error code; a question answered or declined, with how many passages and citations; how long the model took; how many expired questions the cleanup deleted.
- **Request IDs.** Each line logged while a request is handled carries the request's ID. The API returns the same ID in the `X-Request-ID` header and in error bodies, so a reported error can be found in the log. Every request gets a new ID; IDs sent by clients are ignored.
- **What lines leave out.** The app's log lines don't contain passwords, session tokens, email addresses, file names, document text, prompts, model replies, or the text of questions and answers. There are two exceptions, and logs from either should be treated like the documents themselves:
  - `LOG_LEVEL=DEBUG` adds the details of unexpected indexing errors, which can quote a document.
  - An unexpected server error is logged with its traceback, and an exception's message can quote the data it failed on.

## Metrics

With `METRICS_ENABLED=true`, the API serves counts at `/metrics`, in Prometheus's text format: requests by method, route template, and status; request durations; answers by mode and outcome; and documents processed, by outcome. They hold no IDs, names, or text, and stay in the API's memory until it restarts. Anyone who can reach the API can read `/metrics`, so it is off by default.

## Rate limits

Sign-in attempts (10 a minute) and registrations (10 an hour) are counted per network address, and questions (10 a minute) per account. The counters are kept only in the API's memory and reset when it restarts. Requests turned away are logged like any other request, without the address.

## What leaves your computer

| When | What is sent | To |
|---|---|---|
| `python -m app.cli download-embedding-model`, once | Requests for the model's files: BAAI/bge-small-en-v1.5, at a pinned revision. No documents or questions | Hugging Face |
| Each question, with `LLM_PROVIDER=ollama` | The question and the passages found for it, labeled S1, S2, and so on. No document names, IDs, or account details | The Ollama server at `OLLAMA_BASE_URL` |

- **Nothing else.** The API loads the embedding model from local files only, with Hugging Face's offline mode and telemetry turned off. The code has no hosted model provider: `LLM_PROVIDER` is `ollama` or `none`.
- **Ollama.** By default it runs on your own computer, at `http://127.0.0.1:11434`. What Ollama logs or keeps is up to Ollama and its settings, not this app. If `OLLAMA_BASE_URL` names another computer, prompts travel there, unencrypted unless the address starts with `https://`.
- **Setting up.** Installing dependencies (`uv sync`, `npm ci`) and pulling the Ollama model contact their registries. That is part of setting up, not of running the app.
- **CI.** The project's CI runs on GitHub with synthetic test data only.
- **Later.** If a hosted model provider or a hosted demo is ever added, this page must first say what is sent where, and how long it is kept there (spec §12).

## Network exposure

- **Without containers**, PostgreSQL, the API, and the Vite dev server listen on localhost only.
- **Under Docker Compose**, the database, API, and web app ports are published on `127.0.0.1` only, so other computers can't reach them. Until Phase 5 they were published on every network interface, which could expose the database, with its default password, to the network (issue I-38).
- **The database password** in `.env.example`, `local_dev_only`, is for local use. Change it before sharing a computer.
- **Before opening the app to other computers**, serve it over HTTPS with `SESSION_COOKIE_SECURE=true`, behind a reverse proxy that limits how long headers and bodies may take to arrive and how many connections are open, which the API doesn't. Uvicorn should trust forwarded addresses from that proxy only (its `--forwarded-allow-ips` option, `127.0.0.1` by default), so rate limits count clients rather than the proxy. Turn registration off, and keep `/metrics` unreachable. None of this has been tried yet; deployment is Phase 6 (spec §10).

## How this is checked

Tests in `backend/tests` check the claims on this page that code can check, including:

- `test_auth_api.py` and `test_security.py`: only hashes of passwords and session tokens are stored; the cookie is protected, and marked `Secure` when configured; expired sessions are refused and cleaned up.
- `test_storage.py`: storage keys are random.
- `test_questions_api.py`: the history lists only your own recent questions; questions are deleted once they are 3 days old, and when the API starts; deleting a document deletes the answers that cite it; question and answer text never reach the logs.
- `test_llm.py`: logs never include the prompt or the model's reply.
- `test_ingestion.py`: failed indexing doesn't log the document's text at the default log level.
- `test_logs.py` and `test_metrics.py`: requests are named by their route templates, never their paths; Uvicorn's access log is off; metrics aren't served unless enabled.
- `test_robustness.py`: a model that follows planted instructions still sees only the workspace asked about.

The [evaluation](../evaluation/README.md) measures how the assistant answers; this page only describes what it keeps.
