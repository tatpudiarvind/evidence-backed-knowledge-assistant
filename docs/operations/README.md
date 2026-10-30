# Operations

How to run the production-style stack on one computer: start it, check it, read its logs, back it up, upgrade it, and remove it, and how to run the end-to-end tests against it. This page describes the project as of Phase 6 (2026-10-31). The development stack, and running the app without containers, are in the [quickstart](../specification/README.md#local-quickstart). The [architecture guide](../architecture/README.md) explains what each part does, and the [security guide](../security/README.md) explains why the stack is built the way it is.

CI builds this stack on every push, starts it, downloads the embedding model into it, and runs the end-to-end tests against it ([what CI checks](#what-ci-checks)). It hasn't been run outside CI yet. Steps that CI doesn't cover are marked **Not tried yet**: try them on a spare copy before you rely on them.

Commands are for PowerShell, as in the quickstart, and run from the project root. Most are the same in other shells; where one differs, the bash version follows it.

## The two stacks

| | Development: `compose.yaml` | Production-style: `compose.prod.yaml` |
|---|---|---|
| For | Changing the code and seeing the result | Running the app as it would be deployed, and testing it end to end |
| Web app | Vite's dev server at `http://localhost:5173`, updating as the code changes | The built app, served by nginx at `http://localhost:8080` (`PROD_WEB_PORT`) |
| API | Published at `http://localhost:8000`, with its interactive documentation at `/docs`. Restarts when its code changes | Not published: nginx passes `/api/` and `/health/` to it. Its image has no test tools, and runs as a user without root rights |
| PostgreSQL | Published at `127.0.0.1:5432` | Not published |
| Migrations | Run by the `migrate` service before the API starts | The same |
| Logs | Text by default, with no limit on how much Docker keeps | One JSON object per line; Docker keeps up to three files of 10 MB per container |
| Containers' own files | Writable, with the backend's code mounted from `backend/app` | Read-only apart from the volumes and `/tmp`, with every Linux capability dropped, in the migration, API, and web containers. The database's container is set up as in development |

Both read their settings from the same `.env` file, and both publish their ports on `127.0.0.1` only, so other computers can't reach them. Their data lives in separate volumes, so they can run at the same time without sharing anything; each API then loads its own copy of the embedding model.

## Running the production-style stack

You need Docker with Compose v2, the `docker compose` command: Docker Desktop on Windows or macOS, or Docker Engine with the Compose plugin on Linux. The first build downloads the Python packages, including PyTorch's CPU-only build, and the web app's npm packages, so it takes a while; later builds reuse what Docker has cached. No GPU is needed.

### First start

1. If there's no `.env` in the project root yet, copy the example: `Copy-Item .env.example .env` (bash: `cp .env.example .env`).
2. In `.env`, set `POSTGRES_PASSWORD` to a long random value. Use only letters, digits, `-`, and `_`: Compose puts the password into the database URL as it is, and other characters can break the URL. This prints one: `python -c "import secrets; print(secrets.token_urlsafe(24))"`. The stack won't start without a password, but the example's password is public, and CI uses it.

   PostgreSQL stores the password when it creates the database, the first time the stack starts. Changing it in `.env` later doesn't change it in the database, and the API can no longer connect ([troubleshooting](#troubleshooting)). The development stack reads the same `.env`, so the same goes for its database if you've already started it.
3. Build and start the stack, then download the embedding model (about 135 MB) into the stack's own volume. The development stack's copy is in a volume of its own, so this stack needs its own download.

   ```powershell
   docker compose -f compose.prod.yaml up --build --detach --wait
   docker compose -f compose.prod.yaml run --rm backend python -m app.cli download-embedding-model
   ```

   `up` starts the database, runs the migrations once it's healthy, starts the API once they have succeeded, and starts nginx once the API is healthy. `--wait` returns when all of them are up and healthy, and fails if one of them doesn't get there.
4. Open `http://localhost:8080`. Below the sign-in form, the page should say "API and database are ready". Create your account, then turn registration off ([changing settings](#changing-settings)) unless other people need to sign up.

Documents uploaded before the model was downloaded fail with "The embedding model isn't available on the server"; select **Retry** on them once it's there.

To leave out `-f compose.prod.yaml`, set `$env:COMPOSE_FILE = "compose.prod.yaml"` for the session (bash: `export COMPOSE_FILE=compose.prod.yaml`), as CI does. Remove it before you work with the development stack again.

### Trying it out

Upload documents you're allowed to use, or the evaluation's synthetic ones. `evals/corpus/volunteer-faq.txt` can be uploaded as it is. The other three are kept as text that describes a PDF or a Word file. This writes all four as real files to `demo-files/` in the project root, which Git ignores. It runs on the computer, not in a container, with uv installed as in the quickstart:

```powershell
cd backend
uv run python -m app.cli write-demo-files
cd ..
```

Then ask something the documents answer, such as "How long is a front desk shift?", and something they don't, such as "What is the capital of Australia?". With only `volunteer-faq.txt` uploaded, the end-to-end test checks that the first is matched to the FAQ and the second is declined. Without a language model, the assistant declines only when no passage is similar enough to the question, so it declines fewer unanswerable questions than with one; the [evaluation](../evaluation/README.md) measured both.

### Changing settings

The stack takes its settings from `.env`, through the list in `compose.prod.yaml`. A few are set by that file instead:

- `APP_ENV=production` and `LOG_FORMAT=json`.
- `CORS_ORIGINS=[]`: the browser reaches the API through nginx, on the app's own origin, so no other origin needs access.
- The database URL, built from `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`.
- `FORWARDED_ALLOW_IPS="*"`, so Uvicorn takes the client's address from nginx ([security](../security/README.md#the-production-stack)).
- `LLM_PROVIDER` and `OLLAMA_BASE_URL`, taken from `COMPOSE_LLM_PROVIDER` and `COMPOSE_OLLAMA_BASE_URL`, because the plain names in `.env` are for an API running directly on the computer.

After editing `.env`, apply the change. Compose recreates the containers whose settings changed:

```powershell
docker compose -f compose.prod.yaml up --detach --wait
```

Two settings must stay in step with nginx's limits in `frontend/nginx.conf`, which change only when the web image is rebuilt (`up --build`):

- `MAX_UPLOAD_BYTES` must stay below about 11.9 MiB, under nginx's 12 MiB `client_max_body_size`. Otherwise nginx refuses large uploads before the API sees them.
- `LLM_TIMEOUT_SECONDS` should stay well below the 180 seconds nginx waits for the API (`proxy_read_timeout`). Otherwise a slow model gets nginx's timeout instead of the passages.

CI checks that the two stacks give the API the same list of settings.

## What runs

| Service | Image | What it does | What can reach it |
|---|---|---|---|
| `db` | `pgvector/pgvector:0.8.0-pg16`: PostgreSQL 16 with pgvector | Holds everything apart from the uploaded files | The other containers in the stack |
| `migrate` | The API's production image | Runs `alembic upgrade head`, then exits | Nothing; it only connects to `db` |
| `backend` | The API's production image (`backend/Dockerfile`): Python 3.12, run as the user `app` (uid 10001) | The API, the indexing thread, and the cleanup thread that deletes questions after 3 days | The other containers in the stack; only `web` uses it |
| `web` | The built web app on nginx's unprivileged image, `nginxinc/nginx-unprivileged:1.30-alpine` (`frontend/Dockerfile`) | Serves the app, and passes `/api/` and `/health/` to the API | This computer, at `127.0.0.1:8080` |

`db` starts first. `migrate` runs once `db` is healthy; `backend` starts once `migrate` has succeeded; `web` starts once `backend` is healthy. The health checks are `pg_isready` for `db`, every 5 seconds; `GET /health/live` for `backend`, every 10 seconds after a 30-second start period; and `GET /nginx-health` for `web`, every 10 seconds.

No service has a restart policy. A container that stops stays stopped, and after the computer restarts, the stack stays down until you run `up` again.

The data lives in three volumes, whose full names start with `evidence-backed-knowledge-assistant-production_`:

| Volume | Holds | Back it up |
|---|---|---|
| `postgres_data` | The database: accounts, sessions, workspaces, the documents' details, their chunks and embeddings, and questions with their answers | Yes |
| `document_storage` | The uploaded files, under random names | Yes, together with the database |
| `embedding_models` | The embedding model | No: download it again |

### One API process

The API runs as one Uvicorn process, on purpose. Its rate limits are counted in the process's memory, so several processes would each keep their own counts, and each would also start its own indexing and cleanup threads and load its own copy of the embedding model. One process still handles several requests at once. Running more than one needs the changes in [what a real deployment adds](#what-a-real-deployment-adds).

### nginx

- **Serves the built app.** Files under `/assets/` have a hash of their content in their names, so browsers may keep them for a year. Every other path is checked for changes on each visit, and a path that isn't a file gets `index.html`, because it's a page of the app.
- **Passes `/api/` and `/health/` to the API, and nothing else**, so the API's `/docs`, `/openapi.json`, and `/metrics` can't be reached through it.
- **Streams uploads** to the API as they arrive, so the API applies its own size and time limits.
- **Limits requests.** It accepts bodies of up to 12 MiB, allows 30 seconds to send a request's headers, and drops a request whose body stops arriving for 30 seconds. It waits up to 180 seconds for the API's answer, longer than the API waits for a language model (120 seconds by default).
- **Finds the API again** after its container is recreated. It looks up the API's address with Docker's DNS server every 10 seconds, instead of only when it starts.
- **Answers in the API's error format** when the API isn't running (`502 api_unreachable`), takes longer than 180 seconds (`504 api_timeout`), or is sent a body over 12 MiB (`413 request_too_large`). See [errors from nginx](../api/README.md#errors-from-nginx).
- **Adds security headers** to every response, errors included ([security](../security/README.md#the-production-stack)).
- **Answers `ok` at `/nginx-health`** for its container's health check, without logging it.

## Checking health

```powershell
docker compose -f compose.prod.yaml ps --all
```

This lists each service with its state. `migrate` should show `Exited (0)`, and the other three `Up` and `(healthy)`. Without `--all`, `migrate` isn't listed, because it has exited.

Through nginx, as the browser sees them:

- `http://localhost:8080/health/live` answers `{"status": "ok"}` while the API is running.
- `http://localhost:8080/health/ready` answers `{"status": "ok", "database": "ok"}` when the API can query the database, and `503` with `"unavailable"` when it can't. The sign-in page shows the same, and checks again when asked.

In PowerShell, `Invoke-RestMethod http://localhost:8080/health/ready` (a 503 shows as an error); in bash, `curl http://localhost:8080/health/ready`. In Windows PowerShell, `curl` stands for `Invoke-WebRequest`; `curl.exe` is the real one.

## Logs

```powershell
docker compose -f compose.prod.yaml logs --follow backend
```

Use `web`, `db`, or `migrate` for the others, or no name for all of them. Docker puts the container's name in front of each line; `--no-log-prefix` leaves it out.

**The API** writes one JSON object per line, timed in UTC. This line, from a CI run, logged a request:

```json
{"time": "2026-10-30T18:59:12.411Z", "level": "INFO", "logger": "app.access", "message": "GET /api/v1/auth/me 401 5.5 ms", "request_id": "a4c1bb38e6f34def8254a04259a83d4a", "method": "GET", "route": "/api/v1/auth/me", "status": 401, "duration_ms": 5.5}
```

Every line has `time`, `level`, `logger`, `message`, and `request_id`, which is `null` outside a request. Some lines add fields of their own, as this one does, and an error adds `exception`, with its traceback. A request's lines carry the ID the API returned in the `X-Request-ID` header and in any error body, so a reported request ID leads to its lines. With the ID above:

```powershell
docker compose -f compose.prod.yaml logs backend | Select-String a4c1bb38e6f34def8254a04259a83d4a
```

In bash, use `grep` instead of `Select-String`.

The API's lines name routes, IDs, and counts. They never contain document text, questions, answers, file names, or email addresses, apart from two exceptions listed in [privacy](../privacy/README.md#logs). One of them, `LOG_LEVEL=DEBUG`, can quote documents, so keep `INFO`.

**nginx** logs each request it serves, apart from its health check, in its standard format. From the same CI run:

```text
172.18.0.1 - - [30/Oct/2026:18:59:12 +0000] "GET /api/v1/auth/me HTTP/1.1" 401 119 "-" "curl/8.5.0" "-"
```

That is the client's address, the time, the method and the full path, the status, the size of the response, the referrer, the user agent, and any forwarded address. Unlike the API's lines, these record the client's address and the full path, with any IDs in it. When the browser runs on the same computer, the address is usually one of Docker's own, as here; behind a real deployment, it would be each user's.

Docker keeps up to three files of 10 MB for each container, and deletes the oldest lines beyond that. `docker compose down` removes the containers, and their logs with them.

## Metrics

Metrics are off by default (`METRICS_ENABLED=false`). Turned on, the API serves request, answer, and indexing counts at `/metrics`, in Prometheus's format ([API](../api/README.md#health-and-metrics)). nginx doesn't pass `/metrics` on, and the API isn't published, so only containers on the stack's network can read them, such as a Prometheus added to the stack. The counts live in the API's memory and start again from zero when it restarts.

**Not tried yet.** To read them once, from inside the API's container:

```powershell
docker compose -f compose.prod.yaml exec backend python -c "import urllib.request as r; print(r.urlopen('http://127.0.0.1:8000/metrics').read().decode())"
```

## Using a language model

By default the stack runs without one: `COMPOSE_LLM_PROVIDER` isn't set, so `LLM_PROVIDER` is `none`, and answers list the closest passages under "No language model is set up". To have a model write answers from those passages and cite them:

1. Run [Ollama](https://ollama.com/download) where the API's container can reach it, and pull the model there once: `ollama pull qwen3:4b-instruct-2507-q4_K_M` (about 2.5 GB).
2. In `.env`, set `COMPOSE_LLM_PROVIDER=ollama`, and set `COMPOSE_OLLAMA_BASE_URL` to Ollama's address as the container sees it. The default, `http://host.docker.internal:11434`, names the host computer under Docker Desktop. On Linux, Docker doesn't define that name unless it's added, which this stack doesn't do.
3. Apply it: `docker compose -f compose.prod.yaml up --detach --wait`.

**Not tried yet** (risk R-25). Ollama listens on the host's `127.0.0.1` by default, and whether a container can reach it there depends on how Docker runs on the computer. Don't make Ollama listen on every network interface to get around that: it has no authentication, so anything that can reach it can use it (R-17).

If the model can't be reached, or doesn't answer within `LLM_TIMEOUT_SECONDS` (120 by default), the answer falls back to the closest passages, under "qwen3:4b-instruct-2507-q4_K_M didn't reply". Without a GPU that suits it, the model can be much slower. To give it more time, raise `LLM_TIMEOUT_SECONDS`, and nginx's `proxy_read_timeout` too if the new value gets near 180 seconds.

## Backing up and restoring

Back up the database (`postgres_data`) and the uploaded files (`document_storage`) together, while nothing changes them. The database lists each file by its storage name, so a database restored without its files lists documents that can't be downloaded or indexed again, and files restored without the database are orphans. The embedding model needn't be backed up; download it again.

A backup is a copy of every uploaded document and every recent question, so keep it where only you can read it, and encrypt it if it leaves the computer. Restoring a backup brings back whatever was deleted after it was made. History hides questions older than 3 days at once, and the cleanup deletes them when the API starts; delete documents again if they were deleted for a reason.

**Not tried yet.** These steps use the standard Docker and PostgreSQL tools, but they haven't been run against this stack. Restore a backup on a spare copy before you rely on it.

To back up into a folder outside the project, where Git can't pick it up:

```powershell
$backups = "$HOME\knowledge-assistant-backups"
New-Item -ItemType Directory -Force $backups | Out-Null

# Stop the web app and the API, so nothing changes while you copy. The app is offline meanwhile.
docker compose -f compose.prod.yaml stop web backend

# The database, dumped inside its container and copied out.
docker compose -f compose.prod.yaml exec db sh -c 'pg_dump --username $POSTGRES_USER --dbname $POSTGRES_DB --format=custom --file /tmp/database.dump'
docker compose -f compose.prod.yaml cp db:/tmp/database.dump "${backups}/database.dump"
docker compose -f compose.prod.yaml exec db rm /tmp/database.dump

# The uploaded files, archived by a throwaway container.
docker run --rm --volume evidence-backed-knowledge-assistant-production_document_storage:/data:ro --volume "${backups}:/backups" pgvector/pgvector:0.8.0-pg16 tar --create --file /backups/document_storage.tar --directory /data .

docker compose -f compose.prod.yaml up --detach --wait
```

In bash, the first two lines are `backups="$HOME/knowledge-assistant-backups"` and `mkdir -p "$backups"`; the rest is the same.

- The dump is written inside the container and copied out, rather than redirected with `>`: Windows PowerShell's `>` writes text as UTF-16, which would ruin a binary dump.
- `--format=custom` is pg_dump's compressed format, which `pg_restore` reads.
- The throwaway container borrows the database's image, already on the computer, for its `tar`. It runs as root, so it can read every file in the volume.

To restore into an empty stack, with the code at the version that made the backup or a later one:

```powershell
$backups = "$HOME\knowledge-assistant-backups"

# On the computer the backup came from, this deletes the stack's current data. Skip it on a new one.
docker compose -f compose.prod.yaml down --volumes

# Create the containers and volumes, then start only the database.
docker compose -f compose.prod.yaml up --build --no-start
docker compose -f compose.prod.yaml up --detach --wait db

docker compose -f compose.prod.yaml cp "${backups}/database.dump" db:/tmp/database.dump
docker compose -f compose.prod.yaml exec db sh -c 'pg_restore --username $POSTGRES_USER --dbname $POSTGRES_DB --no-owner --single-transaction /tmp/database.dump'
docker compose -f compose.prod.yaml exec db rm /tmp/database.dump

# The files go back with the API's user as their owner.
docker run --rm --volume evidence-backed-knowledge-assistant-production_document_storage:/data --volume "${backups}:/backups" pgvector/pgvector:0.8.0-pg16 sh -c 'tar --extract --file /backups/document_storage.tar --directory /data && chown -R 10001:10001 /data'

# Start the rest. The migrations bring the restored database up to date first.
docker compose -f compose.prod.yaml up --detach --wait
docker compose -f compose.prod.yaml run --rm backend python -m app.cli download-embedding-model
```

- `--single-transaction` makes a failed restore leave the database empty, so it can simply be run again.
- The dump holds no database password. The new database takes the one in `.env`.
- Afterward, sign in, download an old document, ask a question, and upload a new file. The upload shows that the API can write to the restored folder.

## Upgrading

**Not tried yet** with data in the stack: CI always starts from empty volumes.

1. Back up, as above.
2. Get the new code, for example with `git pull`.
3. Rebuild and restart. `migrate` brings the database up to date before the new API starts.

   ```powershell
   docker compose -f compose.prod.yaml up --build --detach --wait
   ```

To take fixes in the base images too, build with `--pull`, and fetch the database's image again, before `up`:

```powershell
docker compose -f compose.prod.yaml build --pull
docker compose -f compose.prod.yaml pull db
docker compose -f compose.prod.yaml up --detach --wait
```

Python and npm packages stay at the versions in the lock files, whatever you pull; they change only when the lock files do. The database image's tag pins PostgreSQL 16. Moving to another major version needs a dump and a restore, not just a new image.

## Stopping and removing

| To | Run |
|---|---|
| Stop the stack, keeping everything | `docker compose -f compose.prod.yaml stop` |
| Start it again | `docker compose -f compose.prod.yaml up --detach --wait` |
| Remove the containers, their logs, and the network, keeping the data | `docker compose -f compose.prod.yaml down` |
| Also delete the database, the uploaded files, and the model | `docker compose -f compose.prod.yaml down --volumes` |
| Also remove the images the stack built | Add `--rmi local` to `down` |

`--volumes` can't be undone, and it doesn't touch backups you made.

## Running the end-to-end tests

The tests in `e2e/` use Playwright to drive Chromium through the production-style stack:

- `journey.spec.ts` uses the app as a reader would. It signs up, creates a workspace, adds `evals/corpus/volunteer-faq.txt`, and waits for it to be Ready. It asks a question the file answers and one it doesn't, checks that Shift+Enter starts a new line, downloads the file and compares it with the original, deletes it, which also deletes the answer citing it, and signs out. Along the way, axe checks six screens against WCAG 2.2 A and AA, and the test saves the [screenshots](../screenshots/README.md).
- `headers.spec.ts` checks that nginx sends the security headers, and that the app works within its Content Security Policy, with no violations reported.
- `service-status.spec.ts` checks that the sign-in page reports unavailable services and checks again when asked. It fakes the readiness answers in the browser, so the stack stays up.

Without a language model, the journey's answer shows "Passages only". With one, it shows "Answered", and the test checks that the answer doesn't follow the instruction planted in `volunteer-faq.txt`, which asks for "PINEAPPLE".

To run them, with the stack up, the embedding model downloaded, and registration on, using Node.js 22 as CI does:

```powershell
cd e2e
npm ci
npx playwright install chromium
$env:E2E_BASE_URL = "http://localhost:8080"
npx playwright test
npx playwright show-report
```

- `E2E_BASE_URL` defaults to `http://localhost:8080`; set it only if `PROD_WEB_PORT` is different. In bash: `E2E_BASE_URL=http://localhost:8080 npx playwright test`.
- On Linux, `npx playwright install --with-deps chromium` also installs the system libraries Chromium needs, as CI does.
- `npm run typecheck` checks the tests' TypeScript.
- The tests run one at a time, because they share the API's rate limits, and each may take up to 3 minutes; the first upload also loads the embedding model. A failed test isn't retried.
- Each journey creates an account. Registration allows 10 an hour from one address, so an eleventh run within the hour fails at sign-up with `429 rate_limited`; `docker compose -f compose.prod.yaml restart backend` resets the counts. The accounts and workspaces stay, because the app can't delete them yet; the declined question is deleted after 3 days.
- The HTML report goes to `e2e/playwright-report/`, the traces of failed tests to `e2e/test-results/`, and the screenshots to `e2e/screenshots/`. Git ignores all three.
- axe's findings for each screen are attached to the report as `axe-<screen>.json`. The checks are soft: the journey carries on, so one run reports the problems on every screen, and the test still fails. They run after the page's animations finish: text caught mid-fade is paler than it ends up, and axe would report its contrast as too low. Automated checks find only some kinds of accessibility problems, so passing them doesn't show that the app meets WCAG 2.2.

CI runs these tests on every push and pull request, against freshly built images and without a language model. It keeps the report, the traces, and the screenshots as the run's `e2e-results` artifact.

## What CI checks

The CI workflow (`.github/workflows/ci.yml`) runs both stacks on every push and pull request, on GitHub's Ubuntu runners.

The `compose smoke` job checks that, on the development stack:

- the stack starts, with the migrations run by `migrate`, and the embedding model downloads;
- the pgvector extension is installed, and the health endpoints and the web app answer;
- through the API, a new account can create a workspace and upload a file, which is indexed into stored chunks; a question gets the file's passages; the download matches the upload; and deleting the document removes it, its chunks, and the answer that cited it;
- the API never reached the database before the migrations;
- readiness reports `503` once the database stops.

The `production images and end-to-end tests` job checks that, on this stack:

- both stacks give the API the same list of settings;
- the API and web containers don't run as root, and the API's image has no pytest or uv;
- the API can't write to its code or its user's home folder, and nginx can't write to the app's files or its own settings;
- the API's and the database's ports can't be reached from the computer, only nginx's;
- nginx sends the security headers, serves the app for any page's path, passes readiness through with an `X-Request-ID`, and answers `/api/v1/auth/me` with `401` without a session;
- a 13 MiB body gets nginx's `413 request_too_large`, and an 11 MiB file gets the API's `413 file_too_large`;
- a download through nginx matches the upload, keeps the API's headers, and sends `nosniff` once;
- the end-to-end tests pass;
- with the API stopped, nginx answers `502 api_unreachable`, in the API's format;
- the API never reached the database before the migrations.

Both jobs show every service's status and logs at the end, and remove their stack with its volumes, whether they passed or not. The `Dependency audit` workflow checks the locked Python and npm packages ([security](../security/README.md#dependencies)).

## Troubleshooting

| What you see | Likely cause | What to do |
|---|---|---|
| `up` stops with "Set POSTGRES_PASSWORD in .env" | No `.env`, or no password in it | Steps 1 and 2 of [first start](#first-start) |
| `up` says port 8080 is already allocated | Another program uses the port | Set `PROD_WEB_PORT` in `.env`, and use that port |
| `migrate` fails, and its log says `password authentication failed` | `POSTGRES_PASSWORD` changed after the database was created | Put the old password back in `.env`, or delete all the stack's data with `down --volumes` and start again |
| The sign-in page says "API or database is unavailable" | A service has stopped, or isn't healthy | `ps --all`, then the logs of the service that isn't healthy |
| Documents fail with "The embedding model isn't available on the server", and questions get `503 embedding_unavailable` | The model isn't in this stack's volume | Download it, then select **Retry** on the failed documents |
| Answers are passages, under "No language model is set up" | The default: no model is set up | [Using a language model](#using-a-language-model) |
| Answers are passages, under "… didn't reply" | Ollama can't be reached, or took longer than `LLM_TIMEOUT_SECONDS` | Check that Ollama is running and that `COMPOSE_OLLAMA_BASE_URL` reaches it, or allow more time |
| `502 api_unreachable` | The API isn't running, or nginx hasn't found a recreated API yet | `ps --all` and the API's logs. nginx finds a recreated API within about 10 seconds |
| `504 api_timeout` | The API took more than 180 seconds, for example with `LLM_TIMEOUT_SECONDS` raised above that | Lower `LLM_TIMEOUT_SECONDS`, or raise nginx's `proxy_read_timeout` and rebuild |
| `413 request_too_large` for a file under `MAX_UPLOAD_BYTES` | `MAX_UPLOAD_BYTES` is above nginx's 12 MiB limit | Lower it, or raise `client_max_body_size` in `frontend/nginx.conf` and rebuild |
| `429 rate_limited` at sign-up, after many end-to-end runs | Registration allows 10 an hour from one address | `docker compose -f compose.prod.yaml restart backend` resets the counts |

## What a real deployment adds

The production-style stack rehearses a deployment on one computer: plain HTTP to that computer only, one API process, secrets in a file, and no automatic backups, monitoring, or restarts. The project hasn't been deployed. Choosing a cloud (task P6-05) and deploying to it (P6-06) are optional and deferred, and would come only after a cost estimate. Serving anyone else would need at least:

- **HTTPS**, from a proxy or load balancer that handles TLS, with `SESSION_COOKIE_SECURE=true` and HSTS. With that proxy in front of nginx, nginx must take the client's address from it (its `real_ip` module); otherwise every user shares one set of rate limits, and the logs show only the proxy.
- **Limits at the edge** on connections and request rates, for every path. Here, nginx limits only body sizes and slow clients, and the API limits only sign-ins, registrations, and questions.
- **Managed secrets**: the database password in the platform's secret store rather than a `.env` file, and nothing left at an example value.
- **Accounts fit for others**: registration off once the accounts exist, or an identity provider with verified emails, password resets, and second factors (spec §15).
- **Shared state before a second API process**: rate limits in a shared store such as Redis, and indexing through a durable queue, a choice spec §15 defers.
- **A database run with care**: managed PostgreSQL with pgvector, or one run just as carefully, never reachable from the internet, and encrypted at rest.
- **Backups**: automated, encrypted, kept somewhere else, and restored on a schedule to prove they work.
- **Monitoring and alerts**: health, error rates, disk space, and the metrics, collected privately.
- **Restarts and updates**: restart policies, or a platform that restarts failed services; images pinned by digest, rebuilt regularly, and scanned. The weekly audit covers the Python and npm packages, not the images' system packages.
- **Privacy that fits**: a privacy notice and retention periods for where it runs, and a review of any hosted model provider's data handling before user content goes to it ([privacy](../privacy/README.md), spec §12).
- **One cloud, chosen after a cost estimate**, with least-privilege identity, a budget and billing alerts, short-lived resources, and teardown steps written before anything is created (spec §13). Avoid always-on databases, Kubernetes clusters, NAT gateways, and GPU instances for a demo, and don't assume any free tier lasts.

Even then, the app isn't certified for regulated or clinical use, and it must not hold real patient, personal, or confidential data.
