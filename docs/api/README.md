# API

The HTTP API behind the web app, as of Phase 6 (2026-10-31). Everything the web app does goes through it. This guide covers how to call it, what each endpoint returns, the limits, and every error code. The [architecture guide](../architecture/README.md) explains how the backend handles a request, and the [security guide](../security/README.md) explains why the rules below exist.

## Where to find it

| Stack | Base URL | Interactive documentation |
|---|---|---|
| Development: `compose.yaml`, or the API run without containers | `http://localhost:8000` | Swagger UI at `/docs`, ReDoc at `/redoc`, and the OpenAPI document at `/openapi.json` |
| Production-style: `compose.prod.yaml` | `http://localhost:8080`, the web app's own address. nginx passes `/api/` and `/health/` on to the API | Not available. nginx passes nothing else on, so `/docs` shows the web app instead |

FastAPI generates the OpenAPI 3.1.0 document from the code, so the two can't drift apart. Its title is "Evidence-backed Knowledge Assistant API", version 0.1.0.

## Conventions

- Request and response bodies are JSON, apart from uploads (`multipart/form-data`) and downloads (the original file).
- IDs are UUIDs. Times are ISO 8601 strings that include the time zone.
- Lists come wrapped in an object: `{"items": [...]}`.
- Every response has an `X-Request-ID` header with a new random ID. The same ID is in the body of an error, and on every log line written for the request. Request IDs sent by clients are ignored.
- Every endpoint under `/api/v1` apart from registration, sign-in, and sign-out needs a signed-in user. Without one, it answers `401 not_authenticated`.

## Signing in

The API uses a session cookie, so clients never handle a token themselves:

1. Register with `POST /api/v1/auth/register`, or sign in with `POST /api/v1/auth/login`. Both take `{"email": "...", "password": "..."}`. Both answer with the user, `{"id": "...", "email": "..."}`, and set a cookie named `eka_session`.
2. Send the cookie with every later request. Browsers do this by themselves; the web app sends its requests with `credentials: "include"`.
3. Add the header `X-CSRF-Protection: 1` to every POST and DELETE under `/api/v1`, including registration and sign-in. Without it, the API answers `403 csrf_header_missing`.

For example, signing in:

```http
POST /api/v1/auth/login HTTP/1.1
Host: localhost:8000
Content-Type: application/json
X-CSRF-Protection: 1

{"email": "reader@example.com", "password": "…"}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: eka_session=…; HttpOnly; Max-Age=43200; Path=/; SameSite=strict
X-Request-ID: …

{"id": "…", "email": "reader@example.com"}
```

How sessions work:

- **The cookie** holds a random token. The database stores only the token's SHA-256 hash, so a copy of the database can't be used to sign in. The cookie is `HttpOnly`, so page scripts can't read it, and `SameSite=Strict`, so the browser doesn't send it with requests that start on other sites. It's also marked `Secure`, for HTTPS only, when `SESSION_COOKIE_SECURE=true`.
- **A session lasts** 12 hours by default (`SESSION_LIFETIME_HOURS`, 1 to 720). After that, the user signs in again.
- **Signing in** ends the session the request came with, if it had one, and deletes the user's expired sessions.
- **Signing out** deletes the session and clears the cookie. It answers `204` even without a session, so repeating it is harmless.
- **The CSRF header** works because other sites can't add it. A form on another site can't set headers at all. Another site's scripts can, but then the browser first checks with the API (a CORS preflight request), and only the configured origins pass.
- **CORS** allows `http://localhost:5173`, the Vite dev server, in development. The production-style stack allows no other origins, since the web app and the API share one.
- **Registration** can be turned off with `REGISTRATION_ENABLED=false`, and then answers `403 registration_disabled`.

Accounts:

- Emails are trimmed and lower-cased. They can be up to 320 characters long, and need one `@` with text on both sides and no spaces. Addresses aren't verified by sending an email.
- Passwords need 12 to 128 characters to register. Sign-in accepts up to 128, which bounds the work of checking one.
- Passwords are hashed with Argon2id. A wrong password and an unknown email get the same answer, `401 invalid_credentials`. Both check a password hash, so they also take about as long.

## Endpoints

| Method | Path | Success | What it does |
|---|---|---|---|
| GET | `/health/live` | 200 | Reports that the process is running |
| GET | `/health/ready` | 200, or 503 | Reports whether the API can reach the database |
| POST | `/api/v1/auth/register` | 201 | Creates an account and signs in |
| POST | `/api/v1/auth/login` | 200 | Signs in |
| POST | `/api/v1/auth/logout` | 204 | Signs out |
| GET | `/api/v1/auth/me` | 200 | Returns the signed-in user |
| GET | `/api/v1/workspaces` | 200 | Lists your workspaces, oldest first |
| POST | `/api/v1/workspaces` | 201 | Creates a workspace |
| POST | `/api/v1/workspaces/{workspace_id}/documents` | 202 | Uploads one PDF, Word (.docx), or text file |
| GET | `/api/v1/workspaces/{workspace_id}/documents` | 200 | Lists a workspace's documents, newest first |
| GET | `/api/v1/documents/{document_id}` | 200 | Returns a document's details and status |
| DELETE | `/api/v1/documents/{document_id}` | 204 | Deletes a document, its file, and the questions that cite it |
| GET | `/api/v1/documents/{document_id}/file` | 200 | Downloads the original file |
| POST | `/api/v1/documents/{document_id}/retry` | 202 | Indexes a failed document again |
| POST | `/api/v1/workspaces/{workspace_id}/questions` | 201 | Asks a question about a workspace's documents |
| GET | `/api/v1/workspaces/{workspace_id}/questions` | 200 | Lists your recent questions in a workspace, newest first |
| GET | `/metrics` | 200 | Prometheus metrics, only when `METRICS_ENABLED=true` |

## Workspaces

A workspace holds documents and the questions asked about them.

- **Creating one:** `POST /api/v1/workspaces` with `{"name": "..."}`. Spaces, tabs, and line breaks in the name are collapsed to single spaces, and the ends are trimmed. Other control characters and invisible formatting characters are refused. What's left must be 1 to 100 characters long.
- **The response:** `{"id", "name", "role", "created_at"}`. The role is always `owner` for now, because workspaces can't be shared yet.
- **Access:** a workspace that doesn't exist and one you're not a member of get the same answer, `404 workspace_not_found`. Guessing IDs can't confirm that another user's workspace exists.

## Documents

### Uploading

`POST /api/v1/workspaces/{workspace_id}/documents` with a `multipart/form-data` body, with the file in a field named `file`:

```http
POST /api/v1/workspaces/…/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=example-boundary
X-CSRF-Protection: 1

--example-boundary
Content-Disposition: form-data; name="file"; filename="volunteer-faq.txt"
Content-Type: text/plain

…the file's bytes…
--example-boundary--
```

The API checks, in this order:

1. **Membership**, before it reads the body, so non-members can't make the server store anything.
2. **The body's type and declared size.** It must be `multipart/form-data` (otherwise `415 multipart_required`). If its `Content-Length` already exceeds the limit, the API refuses at once (`413 file_too_large`).
3. **The body, as it arrives.** At most 4 parts in all (otherwise `422 invalid_multipart`), and one file in the `file` field (`422 too_many_files`, `422 file_missing`, `422 file_empty`). The file can be at most 10 MiB (`MAX_UPLOAD_BYTES`, `413 file_too_large`), and the whole upload must arrive within 120 seconds (`UPLOAD_TIMEOUT_SECONDS`, `408 upload_timed_out`). Other fields are skipped.
4. **The type,** from the file name's extension: `.pdf`, `.docx`, or `.txt` (otherwise `415 unsupported_file_type`). The MIME type the client sends is ignored.
5. **The content,** which must match the type (otherwise `422 invalid_file_content`):
   - PDF: `%PDF-` within the first 1,024 bytes.
   - Word: a ZIP file containing `[Content_Types].xml` and `word/document.xml`, with at most 10,000 entries and at most 256 MiB uncompressed, according to its own directory.
   - Text: valid UTF-8 throughout, with no NUL bytes.
6. **The workspace's document count,** which must be under 100 (`MAX_DOCUMENTS_PER_WORKSPACE`, otherwise `409 document_limit_reached`). Concurrent uploads to one workspace take turns, so the limit holds.

The API then stores the file under a random name, records the document as `queued`, and answers `202 Accepted` with the document:

| Field | Meaning |
|---|---|
| `id`, `workspace_id` | The document, and the workspace it belongs to |
| `display_name` | The uploaded file's name, cleaned for display (below) |
| `mime_type` | The standard MIME type for the file's type, such as `application/pdf` |
| `size_bytes`, `sha256` | The file's size, and its SHA-256 hash in hex |
| `status` | `queued`, `processing`, `ready`, `failed`, or `deleting` |
| `failure_code`, `failure_message` | Why indexing failed, when the status is `failed`; otherwise `null` |
| `created_at`, `updated_at` | When it was uploaded, and when it last changed |

- **The display name** comes from the uploaded file's name. Folders are dropped, control and invisible characters removed, whitespace collapsed, and the result shortened to 255 characters, keeping the extension. A name with nothing left becomes `document`, plus the extension. The name is only ever displayed: the stored file has a random name.
- **The same file twice** makes two documents. The SHA-256 is recorded, but not used to refuse duplicates.

### Following indexing

Indexing runs in the background. Get the document (`GET /api/v1/documents/{document_id}`), or the list, until its status is `ready` or `failed`. The web app reloads the list every 2.5 seconds while any document is `queued` or `processing`.

| Status | Meaning |
|---|---|
| `queued` | Waiting to be indexed |
| `processing` | Being read, split into chunks, and embedded |
| `ready` | Searchable |
| `failed` | Indexing stopped. `failure_code` and `failure_message` say why |
| `deleting` | Being deleted |

The failure messages are written for users, and say what to do next. They never include document text or file paths.

| `failure_code` | What happened | What to do |
|---|---|---|
| `no_text_found` | The file has no text layer, as with a scanned document. Text recognition (OCR) isn't supported | Upload a version with real text |
| `too_many_pages` | A PDF has more pages than `MAX_DOCUMENT_PAGES` allows (500 by default) | Split it |
| `too_much_text` | The file has more text than `MAX_DOCUMENT_CHARACTERS` allows (2,000,000 characters by default) | Split it |
| `parse_timeout` | Reading the file took longer than `PARSE_TIMEOUT_SECONDS` (120 by default) | Simplify or split it |
| `document_unreadable` | The file is damaged, or not really of its type | Save it again and upload the new copy |
| `document_encrypted` | The PDF is password-protected | Remove the password and upload it again |
| `file_missing` | The stored file has gone | Delete the document and upload the file again |
| `embedding_unavailable` | The embedding model isn't on the server | Download it ([operations guide](../operations/README.md)), then retry |
| `embedding_failed` | Creating the embeddings failed | Retry |
| `ingestion_failed` | Something unexpected went wrong | Retry |

### Downloading

`GET /api/v1/documents/{document_id}/file` returns the original bytes, with these headers:

- `Content-Type`: the document's `mime_type`.
- `Content-Disposition: attachment; filename="…"; filename*=UTF-8''…`, so browsers save the file rather than open it, under its display name. `filename` is an ASCII copy of the name, with `_` in place of other characters and quotes, for older clients.
- `Cache-Control: no-store`, so no copy stays in caches, and `X-Content-Type-Options: nosniff`, so browsers trust the declared type.

The API answers `404 document_file_missing` if the stored file has gone, and `409 document_being_deleted` while the document is being deleted.

### Retrying and deleting

- **Retrying:** `POST /api/v1/documents/{document_id}/retry` queues a `failed` document again and clears its failure. A document that's `queued` or `processing` is returned unchanged. A `ready` one gets `409 document_already_indexed`, and one being deleted gets `409 document_being_deleted`. Success is `202`, with the document.
- **Deleting:** `DELETE /api/v1/documents/{document_id}` works in any status, and answers `204`. It also deletes the questions whose answers cite the document, so no answer refers to a document that's gone. If the stored file can't be removed, the API answers `500 document_delete_failed`, and the document stays listed as `deleting`. Deleting it again finishes the job.

## Questions

### Asking

`POST /api/v1/workspaces/{workspace_id}/questions` with `{"text": "..."}`:

- The text is tidied first: Unicode normalized, invisible characters removed, and all whitespace collapsed onto one line. It must then be 1 to 1,000 characters long.
- Each account can ask 10 questions a minute (`QUESTIONS_PER_MINUTE`). More get `429 rate_limited`.
- With a language model configured, answering can take much longer than searching. The API waits up to `LLM_TIMEOUT_SECONDS` (120 by default) for the model, and then answers with the passages alone.

The API answers `201 Created` with the question and its answer. This example is the end-to-end test's first question, without a language model. The IDs, times, and other passages are left out, the excerpt is shortened, and the similarity is rounded:

```json
{
  "id": "…",
  "workspace_id": "…",
  "text": "How long is a front desk shift?",
  "created_at": "…",
  "expires_at": "…",
  "answer": {
    "mode": "search_only",
    "text": null,
    "abstained": false,
    "abstention_reason": null,
    "model_name": null,
    "citations": [
      {
        "number": 1,
        "document_id": "…",
        "document_name": "volunteer-faq.txt",
        "chunk_id": "…",
        "page_number": null,
        "section": null,
        "excerpt": "… A: A front desk shift lasts three hours. Hosts welcome visitors, check guests in, and answer questions. …",
        "similarity": 0.65
      }
    ]
  }
}
```

### Answers

Only passages with a cosine similarity to the question of at least 0.5 (`RETRIEVAL_MIN_SIMILARITY`) count as evidence, from the 4 closest (`RETRIEVAL_TOP_K`). The answer then takes one of six forms:

| `mode` | `abstention_reason` | `text` | `citations` | When |
|---|---|---|---|---|
| `generated` | `null` | The answer, with `[n]` markers | The passages it cites, numbered from 1 in the order cited | A language model answered from the passages, and cited them |
| `generated` | `insufficient_evidence` | `null` | None | The model replied that the passages don't answer the question |
| `generated` | `uncited_answer` | `null` | None | The model's reply cited none of the passages it was given, so it was dropped |
| `search_only` | `null` | `null` | The evidence passages, closest first | No language model is configured, or it didn't reply. In that case, `model_name` names it |
| `search_only` | `weak_evidence` | `null` | None | No passage was similar enough to count as evidence |
| `search_only` | `no_indexed_documents` | `null` | None | The workspace had no `ready` documents |

`abstained` is `true` exactly when there's an `abstention_reason`. A generated answer always names its `model_name`.

Each citation has:

| Field | Meaning |
|---|---|
| `number` | The `[n]` marker in a written answer, from 1 |
| `document_id`, `document_name` | The document, and its display name |
| `chunk_id` | The passage |
| `page_number` | The PDF page, from 1. Word and text files have none |
| `section` | The Word heading the passage falls under, if any |
| `excerpt` | The passage's text |
| `similarity` | Cosine similarity between the passage and the question, from -1 to 1. Higher is closer |

Asking can also fail:

- `503 embedding_unavailable`: the embedding model isn't on the server, so nothing can be searched.
- `409 answer_sources_changed`: a document the answer relies on was deleted while the answer was being prepared. Ask again.

### History

`GET /api/v1/workspaces/{workspace_id}/questions` returns your own questions in the workspace with their answers, newest first. It returns at most 50, none older than 3 days, and never another member's questions. Each question is deleted 3 days after it was asked, at its `expires_at`, together with its answer and citations ([privacy notes](../privacy/README.md)).

## Errors

### Format

Every error has the same shape:

```json
{
  "error": {
    "code": "workspace_not_found",
    "message": "This workspace doesn't exist, or you don't have access to it.",
    "request_id": "…"
  }
}
```

- **`code`** is stable. Clients should act on it, not on the message.
- **`message`** is safe to show to users. Errors never include stack traces, settings, file paths, or the values that were sent.
- **`request_id`** matches the `X-Request-ID` header and the server's log lines, so a user can report it.
- **`fields`** is added to `422 validation_failed` errors: a list of `{"location", "message"}`, such as `{"location": "body.password", "message": "String should have at least 12 characters"}`. The value that failed is never echoed.
- **`429 rate_limited`** comes with a `Retry-After` header, in seconds, and a message that says how long to wait, such as "Too many sign-in attempts. Try again in 42 seconds."

### Codes

Any endpoint:

| Status | Code | When |
|---|---|---|
| 401 | `not_authenticated` | The request has no valid session |
| 403 | `csrf_header_missing` | A POST or DELETE under `/api/v1` lacks `X-CSRF-Protection: 1` |
| 404 | `not_found` | No endpoint has this path |
| 405 | `method_not_allowed` | The endpoint doesn't accept this method |
| 413 | `request_too_large` | A body over 64 KiB, apart from uploads |
| 422 | `validation_failed` | Fields are missing or invalid. See `fields` |
| 429 | `rate_limited` | Too many requests. See `Retry-After` |
| 500 | `internal_error` | Something unexpected went wrong. The message asks the user to report the request ID |

Errors raised by the framework itself get a generic code from their status: `400 bad_request`, `403 forbidden`, and `415 unsupported_media_type`, as well as those above. Any other status gets `http_error`.

Accounts:

| Status | Code | When |
|---|---|---|
| 401 | `invalid_credentials` | The email or the password is wrong |
| 403 | `registration_disabled` | Registration is turned off |
| 409 | `email_already_registered` | An account with this email already exists |

Workspaces:

| Status | Code | When |
|---|---|---|
| 404 | `workspace_not_found` | The workspace doesn't exist, or you're not a member |

Documents:

| Status | Code | When |
|---|---|---|
| 400 | `upload_interrupted` | The client stopped sending the upload part-way |
| 404 | `document_not_found` | The document doesn't exist, or you're not a member of its workspace |
| 404 | `document_file_missing` | A download, when the stored file has gone |
| 408 | `upload_timed_out` | The upload took longer than `UPLOAD_TIMEOUT_SECONDS`. The connection is closed |
| 409 | `document_limit_reached` | The workspace already has `MAX_DOCUMENTS_PER_WORKSPACE` documents |
| 409 | `document_already_indexed` | A retry of a `ready` document |
| 409 | `document_being_deleted` | A download or retry while the document is being deleted |
| 413 | `file_too_large` | The file is over `MAX_UPLOAD_BYTES` |
| 415 | `multipart_required` | The upload isn't `multipart/form-data` |
| 415 | `unsupported_file_type` | The file name doesn't end in `.pdf`, `.docx`, or `.txt` |
| 422 | `invalid_multipart` | The body isn't valid multipart, or has more than 4 parts |
| 422 | `file_missing` | No file in a field named `file` |
| 422 | `too_many_files` | More than one file in the `file` field |
| 422 | `file_empty` | The file is empty |
| 422 | `invalid_file_content` | The content doesn't match the file's type |
| 500 | `document_delete_failed` | The stored file couldn't be deleted. Delete the document again |

Questions:

| Status | Code | When |
|---|---|---|
| 409 | `answer_sources_changed` | A cited document was deleted while the answer was being prepared |
| 503 | `embedding_unavailable` | The embedding model isn't available |

### Errors from nginx

In the production-style stack, nginx answers some errors itself, in the same format. Their `request_id` is `null`, because the request never reached the API.

| Status | Code | When |
|---|---|---|
| 413 | `request_too_large` | A body over 12 MiB |
| 502 | `api_unreachable` | The API isn't running |
| 504 | `api_timeout` | The API took longer than 180 seconds to answer |

nginx's 12 MiB limit is above the API's 10 MiB upload limit, so a file a little over 10 MiB still gets the API's clearer `413 file_too_large`. Only bodies over 12 MiB get nginx's answer.

The web app adds one code of its own, `network_error`, when a request fails without any response, as when the API isn't running in development.

## Health and metrics

- **`GET /health/live`** answers `{"status": "ok"}` whenever the process is running. It doesn't touch the database, so container health checks use it.
- **`GET /health/ready`** answers `{"status": "ok", "database": "ok"}` when the API can query the database, and `503` with `{"status": "unavailable", "database": "unavailable"}` when it can't. The web app's sign-in page shows the result.
- **`GET /metrics`** exists only when `METRICS_ENABLED=true`. It answers in Prometheus's text format, or in OpenMetrics when the `Accept` header asks for it:
  - `http_requests_total`, by method, route, and status.
  - `http_request_duration_seconds`, a histogram by method and route.
  - `knowledge_assistant_answers_total`, by answer mode and outcome: `answered`, or the abstention reason.
  - `knowledge_assistant_documents_processed_total`, by outcome: `indexed`, `discarded` (deleted or changed while it was being indexed), or the failure code.

  Routes are recorded as templates, such as `/api/v1/documents/{document_id}`, so no ID ever becomes a label. `/metrics` has no authentication, so leave it off, or let only your monitoring reach it. In the production-style stack, nginx doesn't pass it on, so only containers on the stack's own network can reach it.

Requests to these three endpoints are logged at debug level only, so frequent checks don't flood the logs.

## Limits

| Limit | Default | Setting |
|---|---|---|
| Request body, apart from uploads | 64 KiB | Fixed |
| Uploaded file | 10 MiB | `MAX_UPLOAD_BYTES`, up to 100 MiB. Behind nginx, keep it below about 11.9 MiB |
| Time to upload a file | 120 seconds | `UPLOAD_TIMEOUT_SECONDS` |
| Parts in an upload body | 4 | Fixed |
| Documents in a workspace | 100 | `MAX_DOCUMENTS_PER_WORKSPACE` |
| Pages in a PDF | 500 | `MAX_DOCUMENT_PAGES` |
| Text in a document | 2,000,000 characters | `MAX_DOCUMENT_CHARACTERS` |
| Time to read a document | 120 seconds | `PARSE_TIMEOUT_SECONDS` |
| Question | 1 to 1,000 characters, after tidying | Fixed |
| Workspace name | 1 to 100 characters, after tidying | Fixed |
| Email | 320 characters | Fixed |
| Password | 12 to 128 characters | Fixed |
| Question history | The 50 most recent, up to 3 days old | Fixed |
| Session | 12 hours | `SESSION_LIFETIME_HOURS` |
| Sign-in attempts | 10 a minute for each client address | `SIGN_IN_ATTEMPTS_PER_MINUTE` |
| Registrations | 10 an hour for each client address | `REGISTRATION_ATTEMPTS_PER_HOUR` |
| Questions | 10 a minute for each account | `QUESTIONS_PER_MINUTE` |
| Waiting for the language model | 120 seconds | `LLM_TIMEOUT_SECONDS` |

The rate limits count requests over a sliding window, in the API process's memory, so they reset when it restarts. `RATE_LIMITS_ENABLED=false` turns them off. Behind nginx, the client address is the one nginx received the request from. nginx replaces any `X-Forwarded-For` header the client sent, and the API trusts that header because only nginx can reach it.
