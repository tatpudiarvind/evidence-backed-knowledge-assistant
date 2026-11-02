# Security

How the Evidence-backed Knowledge Assistant protects accounts, workspaces, uploaded files, and answers, and what it doesn't protect against yet. This page describes the code as of Phase 10 (2026-11-02). The requirements it follows are in the [specification](../specification/README.md#12-security-privacy-and-operational-requirements). What is stored, logged, and sent, and for how long, is in [privacy and data handling](../privacy/README.md).

The assistant is a portfolio demo of document retrieval, built to run on one computer. It isn't certified for regulated or clinical use, it hasn't been penetration-tested or reviewed by anyone independent, and its answers aren't professional, medical, legal, or financial advice. Upload only public, synthetic, or licensed documents you're allowed to use, and never real patient or confidential data.

## At a glance

| Risk | Main controls | Checked by |
|---|---|---|
| Someone guesses a password | Argon2id hashes; 10 sign-in attempts a minute per network address; the same answer, after the same work, for an unknown email as for a wrong password | `test_security`, `test_auth_api`, `test_rate_limits` |
| A forged or replayed provider sign-in | The API checks each ID token's signature, issuer, audience, expiry, and nonce; a one-use `state` and a PKCE verifier bound to the browser; only literal `email_verified: true` counts | `test_oidc_sign_in`, `test_config` |
| Someone steals or forges a session | Random 256-bit tokens, stored only as SHA-256 hashes, in an `HttpOnly`, `SameSite=Strict` cookie | `test_security`, `test_auth_api` |
| Another site sends requests as the user | The `SameSite=Strict` cookie; a custom header on every state-changing request; explicit CORS origins | `test_errors`, `test_config`, `test_documents_api`, `test_questions_api` |
| A user reads another user's workspace | Membership checked inside each database query; `404` for other users' items, as for missing ones | `test_isolation_api`, `test_robustness` |
| An upload is harmful or mislabeled | Size, time, and type limits; the file's bytes checked; random storage names; downloads never shown inline | `test_uploads`, `test_documents_api`, `test_storage` |
| A file is built to be expensive to read | Page, character, time, and XML-size limits; parser child process with a hard timeout and Linux memory limit | `test_parsers`, `test_ingestion` |
| A document tries to instruct the model | Passages framed as untrusted evidence between random markers; no tools; citations checked | `test_grounding`, `test_robustness`, and the [evaluation](../evaluation/README.md#planted-instructions) |
| Someone overloads the API | Rate limits; request size and upload time limits; a time limit on the model | `test_rate_limits`, `test_request_body_limit`, `test_uploads`, `test_llm` |
| Logs or errors give data away | Logs name routes and IDs, not text or names; errors show a plain message and a request ID | `test_logs`, `test_errors`, `test_llm`, `test_questions_api` |
| A dependency has a known vulnerability | Locked versions; audits in CI on every push and every week | The `Dependency audit` workflow |

The tests are in `backend/tests`. The [known gaps](#known-gaps) are at the end.

## Accounts and signing in

- Accounts are local: an email address and a password of 12 to 128 characters. Email addresses aren't verified, and there is no password reset or second factor.
- Passwords are hashed with Argon2id by argon2-cffi, with its default parameters: RFC 9106's low-memory profile of 64 MiB of memory, 3 passes, and 4 lanes. If the defaults change, the next successful sign-in stores a new hash (D-32). No cryptography is written by hand.
- An unknown email is checked against a throwaway hash, so it takes about as long as a wrong password, and both get the same `401 invalid_credentials`: "The email or password is incorrect."
- Registration does say whether an email has an account (`409 email_already_registered`). It is limited to 10 attempts an hour per network address, and `REGISTRATION_ENABLED=false` turns it off once your accounts exist.
- Sign-in attempts are limited to 10 a minute per network address (D-69).
- `AUTH_MODE` chooses how people sign in: `local` (the default), `oidc`, or `both`. When passwords are off, registering and signing in with a password answer `403 password_sign_in_disabled`. An account made through a provider has no password, and a password sign-in to it gets the same `401 invalid_credentials` as a wrong password, after the same hashing work.

## Signing in through an identity provider

With `AUTH_MODE=oidc` or `both`, the API is the client of one OpenID Connect provider and runs the authorization code flow itself (D-85). The browser only follows redirects. The ID token and the provider's other tokens never reach it, and the API keeps neither: only the provider's issuer address and the person's subject are stored, in `user_identities`.

- **Start.** `GET /api/v1/auth/oidc/login` makes a random `state`, a random `nonce`, and a PKCE verifier (RFC 7636, method `S256`), stores them in `oidc_login_states` under the SHA-256 hash of a random token, and sends the browser to the provider. The token goes in the `eka_oidc_login` cookie, which is `HttpOnly`, `SameSite=Lax`, limited to the path `/api/v1/auth/oidc`, and lasts 10 minutes. It is `Lax` because the provider sends the browser back with a cross-site navigation, which doesn't carry `Strict` cookies.
- **Finish.** `GET /api/v1/auth/oidc/callback` deletes the stored state in the same statement that reads it, so a state works once, and refuses it when it has expired. The `state` in the address must equal the stored one, and the cookie must be the browser's own: a callback from another browser finds no state.
- **Token exchange.** The code goes to the provider's token endpoint with the PKCE verifier and the client secret in an `Authorization` header (RFC 6749 §2.3.1). Redirects are never followed, so the secret can't be sent elsewhere. Replies are capped at 1 MiB, and every request has a timeout (`OIDC_TIMEOUT_SECONDS`).
- **The ID token** is checked by PyJWT, a maintained library, as OpenID Connect Core §3.1.3.7 lists: the signature, against the provider's published keys, with only `RS256`, `PS256`, and `ES256` allowed, so `none` and shared-secret algorithms are refused; `iss` equal to the configured issuer; `aud` containing the client ID, and `azp` equal to it when present or needed; `exp`, `iat`, `sub`, and `iss` present, with 60 seconds of clock leeway; and the `nonce` equal to the stored one, compared in constant time.
- **Keys and discovery.** The provider's discovery document must name the configured issuer exactly (OpenID Connect Discovery §4.3). Its endpoints must be `https://`, or `http://` only on this computer. Keys are cached, and a token with an unknown key ID makes the API fetch them again at most every 30 seconds, so made-up key IDs can't make it fetch on every request.
- **Accounts.** A person is known by issuer and subject, never by email. A first sign-in creates an account only when the provider says the email is verified, as the literal `true`, and no other account has that email. Otherwise it is refused (`email_not_verified`, `email_in_use`). Accounts are never linked by email: that is how one person's account is taken over by another who can claim the same address at a weaker provider.
- **After sign-in** the API starts the same session as for a password: the `eka_session` cookie, `HttpOnly` and `SameSite=Strict`, with only its hash stored.
- **Where the browser lands.** The return path is checked when sign-in starts (it must begin with one `/`, and have no `//`, backslash, or control character, and be at most 512 characters), and kept on the server, so the callback never redirects to an address taken from the request. Failures send the browser to `/?sign_in_error=<code>`, with the code only, never a message from the provider.
- **Errors and logs** name a short code. The provider's messages, tokens, codes, and the client secret aren't logged or shown.

### Review against the standards (P10-06)

This is the project's own review of the code against the parts of [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700) (OAuth 2.0 security best current practice) and OpenID Connect Core that apply. It is not an independent one.

| Requirement | How it's met | Checked by |
|---|---|---|
| Authorization code flow with PKCE `S256` (RFC 9700 §2.1.1) | Every sign-in sends a challenge and the token request sends the verifier | `test_oidc_sign_in` |
| `state` ties the callback to the browser that started it (RFC 9700 §2.1) | A one-use state, kept under the hash of a cookie token | `test_oidc_sign_in` |
| The ID token's `nonce` is checked (OIDC Core §3.1.3.7) | Compared with the stored nonce, in constant time | `test_oidc_sign_in` |
| Signature, `iss`, `aud`, `azp`, `exp` are checked (OIDC Core §3.1.3.7) | PyJWT, with a fixed list of algorithms | `test_oidc_sign_in` |
| The redirect URI is exact (RFC 9700 §2.1) | One configured address, sent unchanged; the provider must hold it as registered | `test_config` |
| No open redirect after sign-in | The return path is checked, kept on the server, and always relative | `test_oidc_sign_in` |
| Endpoints use TLS (RFC 9700 §4) | Settings and discovery refuse `http://` except on this computer | `test_config`, `test_oidc_sign_in` |
| Tokens aren't exposed to the browser | The browser sees only redirects; no token is stored | `test_oidc_sign_in` |
| A confused provider can't impersonate another | The discovery issuer must equal the configured one | `test_oidc_sign_in` |

Gaps in this review, also under [known gaps](#known-gaps):

- It was tested against a stand-in provider that the tests run on this computer, by reading the code, and in CI against Keycloak through a real browser, which showed the `Strict` session cookie is sent after the redirect back. It was not run against a hosted provider, so a provider-specific behavior could still surprise it.
- Whether a browser sends the `Strict` session cookie on the first request after coming back from the provider is untested; the web app's own request to `/auth/me` is same-site, which should carry it.
- Signing out ends only this app's session, not the one at the provider. The provider's session can sign the person straight back in.
- There's no refresh token, back-channel logout, or ID token encryption, and the API doesn't ask for or use access tokens.
- A signed-in user can't link a provider to an existing password account (see the known gaps).
- The sign-in rate limit counts both the start and the callback, so one sign-in uses two of the 10 attempts a minute.

## Sessions and cookies

- Signing in creates a session with a random token from `secrets.token_urlsafe(32)`, which is 32 random bytes. The browser gets the token in the `eka_session` cookie. The database keeps only its SHA-256 hash, so a copy of the database can't be used to sign in.
- The cookie is `HttpOnly`, so page scripts can't read it, and `SameSite=Strict`. It lasts 12 hours by default (`SESSION_LIFETIME_HOURS`, 1 to 720). It is marked `Secure` only with `SESSION_COOKIE_SECURE=true`, which any HTTPS deployment needs.
- A cookie value longer than 128 characters is refused without a database lookup. Expired sessions are refused, and deleted when their user next signs in.
- Signing in replaces the browser's previous session. Signing out deletes the session and the cookie.

## Requests from other sites

- `SameSite=Strict` keeps browsers from sending the cookie with requests that start on other sites.
- Every `POST`, `PUT`, `PATCH`, and `DELETE` under `/api/v1` must carry the header `X-CSRF-Protection: 1`, or it gets `403 csrf_header_missing`. That includes registering and signing in. A form on another site can't add a header, and a script on another site can't send one without the browser asking the API first (a CORS preflight), which only allowed origins pass.
- CORS allows only the origins in `CORS_ORIGINS`. Settings refuse wildcards and anything but `http://` and `https://` origins, because the API accepts cookies from them. It allows credentials, the methods `GET`, `POST`, and `DELETE`, and the headers `Content-Type` and `X-CSRF-Protection`.
- In development, the one allowed origin is the Vite dev server, `http://localhost:5173`. In the production stack the list is empty: the browser reaches the API through nginx, on the web app's own origin.

## Workspace isolation

Authorization is enforced by the API's database queries, not by the web app hiding things (spec §12).

- Every query that returns workspace data, whether workspaces, documents, files, passages, or questions, joins the signed-in user's membership of the workspace in SQL.
- A workspace or document that isn't yours gets the same `404` as one that doesn't exist, such as "This document doesn't exist, or you don't have access to it.", so IDs can't be probed. IDs are random UUIDs, but isolation doesn't depend on keeping them secret.
- The passage searches, by meaning and, in the hybrid search modes, by the question's words, join the asker's membership too, and keep only `ready` documents in the workspace asked about. The model and the reranker are only ever shown passages the asker may read.
- The keyword search passes PostgreSQL only the question's words, joined with `or`, as a query parameter, so a question can't add search operators.
- An upload checks membership before the API reads the request body, so a non-member can't make the API store anything.
- The question history lists only the signed-in user's own questions.
- Workspaces can't be shared yet. The `member` role exists in the database for sharing later, but nothing grants it.

`test_isolation_api` has a second user try to list, read, download, delete, upload, retry, ask, and read the history in the first user's workspace, and checks signed-out requests. `test_robustness` checks that a model following planted instructions still sees only the workspace asked about.

## Uploaded files

Uploads are checked in this order; the [API guide](../api/README.md#uploading) lists the error for each step.

1. The user must be signed in and a member of the workspace.
2. The request must be a multipart form with one file, in the `file` field, and at most 4 parts.
3. The file may be at most `MAX_UPLOAD_BYTES`, 10 MiB by default, counted as its bytes arrive, so a false `Content-Length` doesn't help. It must arrive within `UPLOAD_TIMEOUT_SECONDS`, 120 seconds by default.
4. Its type comes from its extension, `.pdf`, `.docx`, or `.txt`. The type the browser sends isn't trusted.
5. Its bytes must match that type:
   - a PDF must contain `%PDF-` in its first 1,024 bytes;
   - a Word file must be a ZIP archive whose directory lists `[Content_Types].xml` and `word/document.xml`, with at most 10,000 entries and 256 MiB uncompressed. Only the directory is read; nothing is decompressed;
   - a text file must be UTF-8, without NUL bytes.
6. A workspace may hold at most 100 documents (`MAX_DOCUMENTS_PER_WORKSPACE`). The count is taken with the workspace's row locked, so two uploads can't both take the last place.

How files are kept:

- While a file arrives, it is written to a new temporary file in the storage folder's `tmp` folder. A rejected, interrupted, or timed-out upload is deleted from there. An accepted one is moved into place in one step.
- Files are stored under a random 32-character name from `secrets.token_hex(16)`. Storage refuses any name that isn't exactly 32 hexadecimal characters, so no name or path chosen by a user ever reaches the file system.
- The name shown in the app is cleaned: folders, control characters, and invisible formatting characters such as right-to-left overrides are removed, and it is cut to 255 characters.
- Downloads are always sent as attachments (`Content-Disposition: attachment`), with `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`, so the browser saves the file instead of showing it on the app's own origin.

Files aren't scanned for malware. Each file's SHA-256 hash is recorded, but duplicate files are accepted.

## Reading documents

Text is extracted by a short-lived parser child process, one document at a time, with these limits (D-48, D-83):

- at most 500 pages (`MAX_DOCUMENT_PAGES`), 2,000,000 characters (`MAX_DOCUMENT_CHARACTERS`), and 120 seconds (`PARSE_TIMEOUT_SECONDS`). The parent process kills a child that exceeds the wall-clock timeout. On Linux the child has a 1.5 GiB address-space limit; Python's standard library has no equivalent on Windows, so the residual memory risk remains there (R-19);
- a Word file's XML parts may declare at most 64 MiB in total, checked before parsing. Python's `zipfile` stops reading each part at its declared size, so this bounds the work. python-docx parses the XML without resolving entities;
- a PDF that needs a password is refused (`document_encrypted`). One encrypted only to restrict printing or editing is read with the empty password. pypdf applies its own decompression limits;
- a text file is read only up to 4 bytes per allowed character.

The child environment contains only the executable search path, required Windows system/temp variables where present, and no `DATABASE_URL` or application secrets. It receives a local storage path and parse limits, and returns bounded extracted text to the worker. Any error from a parsing library is reported as `document_unreadable`, without its details. The details are not sent back to the API logs. There is no OCR: a PDF of scanned pages fails with `no_text_found`.

## Documents that try to instruct the model

A document can contain text written to steer a language model, such as "Ignore your previous instructions and…". This is called prompt injection. The assistant treats document text, and the question, as untrusted:

1. **Evidence, not instructions.** The system prompt says the sources are untrusted text from documents, to use them only as evidence, and never to follow instructions, requests, or role changes inside them.
2. **Random markers.** Each passage sits between `<<<BEGIN SOURCE S1 …>>>` and `<<<END SOURCE S1 …>>>` markers that end with a random 16-character value chosen for each question. A document can't guess the value, so it can't close its passage early and continue as if it were outside the sources.
3. **Labels, not names.** Passages are labeled S1, S2, and so on. Document names, which users choose, and IDs or links never reach the model.
4. **No tools.** The model is offered no tools or functions, runs at temperature 0, and can only return text. It has no say in who sees what: the search has kept to the asker's workspace before the model is called.
5. **Checked citations.** The reply is cut to 8,000 characters, and any reasoning between think tags is removed. Citations of labels the model wasn't given are dropped. A reply with no valid citation is declined (`uncited_answer`), and so is the reply `INSUFFICIENT_EVIDENCE`. Invisible characters are removed before an answer is stored.
6. **The question can't add sources.** The question is put on one line after every passage. Text in it shaped like a source has no valid marker, and a citation of it is dropped (`test_a_question_cannot_add_passages_of_its_own`).
7. **Plain text in the browser.** The web app shows answers as text, never as HTML, and the production stack's Content Security Policy allows no inline scripts. A reply can't add markup to the page or run code in it.

This reduces the risk; it doesn't remove it. A model can still follow an instruction phrased as a fact. The answer then has to cite the passage it came from, where a reader can see the instruction (`test_an_answer_that_follows_a_planted_instruction_cites_the_passage_holding_it`). That is why nothing the model writes decides access, and why the web app shows every answer's passages.

The evaluation planted instructions in its documents and questions. In its one run with the local model, the model followed the instruction written in a question, and the citation check declined the reply. It ignored both planted instructions that reached its prompt. One run of one model shows what happened there, not that the model can't be misled; the [evaluation](../evaluation/README.md#planted-instructions) has the details.

## The language model

- Only the API calls the model. The browser never does, and in the production stack the Content Security Policy only lets the page connect to its own origin.
- `LLM_PROVIDER` is `ollama` (the default), `openai_compatible` or `none`. `OLLAMA_BASE_URL` must be an `http://` or `https://` URL, and is on this computer by default.
- `openai_compatible` reaches any server that speaks the OpenAI chat completions API through `LLM_BASE_URL`, `LLM_MODEL` and, for a hosted one, `LLM_API_KEY`. The settings are refused at startup unless the URL is `http://` or `https://` with no login in it, and a host that isn't this computer uses `https://` and has a key. The key is a secret setting: it is sent only in the `Authorization` header, never logged, and left out of any printout of the settings. Redirects are not followed, so the key can't be carried to another host. The reply is only ever text: no tools or functions are offered to the model.
- A busy or failing hosted provider (429, 500, 502, 503, 504, or no connection) is tried again up to `LLM_MAX_RETRIES` times, waiting as long as `Retry-After` says (at most 30 seconds) or else backing off from a second. Other errors aren't retried. At most `LLM_DAILY_CALL_LIMIT` hosted calls are made per UTC day, counted in PostgreSQL, so a loop or a stolen account can't run up an unbounded bill. Past it, nothing is sent and answers list the matching passages. The limit caps calls, not what each one costs, and it is not a billing alert (R-28).
- Each call has a time limit (`LLM_TIMEOUT_SECONDS`, 120 seconds by default), the answer is limited to 768 tokens, and a response over 1 MiB is refused. If the model can't be reached, takes too long, or replies with something unexpected, the question is answered with passages only.
- Prompts, replies, and the key are never logged (`test_llm`, `test_llm_openai_compatible`). Only a status code or an error type is.
- No hosted provider has been called by this project's tests or by the owner, and none is chosen: that needs the owner's approval of a vendor and its cost, and a review of its data handling ([privacy](../privacy/README.md#what-leaves-your-computer)).
- Ollama has no authentication of its own (R-17). Keep it listening on `127.0.0.1`, and stop it when you don't need it.

## Limits on requests

- **Rate limits (D-69).** 10 sign-in attempts a minute and 10 registrations an hour per network address, and 10 questions a minute per account. A request over a limit gets `429 rate_limited` with a `Retry-After` header. The counts are kept in the API's memory, for at most 10,000 addresses and accounts, and reset when it restarts.
- **Request size.** Request bodies other than uploads may be at most 64 KiB (`413 request_too_large`). The bytes are counted as they arrive, not taken from `Content-Length`.
- **Uploads.** 10 MiB within 120 seconds, as described [above](#uploaded-files).
- **In the production stack**, nginx also refuses request bodies over 12 MiB. It gives a client 30 seconds to send a request's headers, and drops a request whose body stops arriving for 30 seconds.

The [API guide](../api/README.md#limits) lists every limit and its setting.

## Errors and logs

- Every error has the same JSON shape: a code, a message, and the request's ID ([API guide](../api/README.md#errors)). An unexpected error returns only "Something went wrong on the server. Try again; if it keeps happening, report the request ID."; the details go to the log. Validation errors name the field that failed, never the value that was sent.
- Each request gets a new random ID, returned in the `X-Request-ID` header. IDs sent by clients are ignored, so they can't put text into the log.
- Log lines name requests by their route templates, such as `GET /api/v1/documents/{document_id}`, not by their paths. They leave out client addresses, query strings, passwords, session tokens, email addresses, file names, document text, prompts, replies, and the text of questions and answers. The two exceptions, `DEBUG` logging and tracebacks, are in [privacy](../privacy/README.md#logs).
- Questions and answers are deleted 3 days after the question was asked (D-55); [privacy](../privacy/README.md#retention-and-deletion) has the details.
- Metrics are off by default (`METRICS_ENABLED`). When they are on, anyone who can reach the API can read `/metrics`, including durable job status counts and queued age; nginx doesn't forward it. The job payload contains document IDs only, never file contents, extracted text, or secrets.

## The production stack

`compose.prod.yaml` runs the app as it would be deployed, on one computer; [operations](../operations/README.md) explains how to run it.

- **One way in.** Only nginx is published, on `127.0.0.1:8080`. The API and PostgreSQL have no published ports, so only the other containers in the stack can reach them. nginx passes on only `/api/` and `/health/`, so the API's `/docs`, `/redoc`, `/openapi.json`, and `/metrics` can't be reached through it.
- **Client addresses.** nginx replaces any `X-Forwarded-For` header the browser sent with the address it received the request from. Uvicorn trusts that header from any address (`FORWARDED_ALLOW_IPS="*"`), so the rate limits count browsers rather than nginx. That is safe only because nothing but nginx can reach the API.
- **Headers.** nginx adds these to every response, errors included:
  - a Content Security Policy that allows only the app's own scripts, styles, images, and connections, no plugins, and no forms or base URLs that point elsewhere, and doesn't let any page put the app in a frame;
  - `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`;
  - a `Permissions-Policy` that turns off the camera, microphone, and location;
  - `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy`, both `same-origin`.

  `server_tokens off` keeps nginx's version out of responses.
- **Containers.** The migration, API, and web containers can't change their own files, apart from their volumes and a temporary `/tmp`. They run with every Linux capability dropped and can't gain privileges (`no-new-privileges`). The API runs as an unprivileged user (uid 10001), from an image without test tools or uv; nginx runs from nginx's unprivileged image. The database uses the standard pgvector image.
- **Secrets.** Compose refuses to start without `POSTGRES_PASSWORD`, set in `.env`, which Git ignores. The production stack has no default password.
- **Logs** rotate at 10 MB, keeping 3 files per container.

CI starts this stack on every push and checks that the API and web containers don't run as root, that the API image has no pytest or uv, that their files are read-only, that only nginx can be reached, that the headers are sent (`e2e/tests/headers.spec.ts`), and that oversized requests get the right errors.

The stack serves plain HTTP to this computer only. [Operations](../operations/README.md#what-a-real-deployment-adds) lists what a real deployment would add, starting with HTTPS.

## Dependencies

- Versions are locked in `backend/uv.lock`, `frontend/package-lock.json`, and `e2e/package-lock.json`. CI installs exactly those versions, with `uv sync --locked` and `npm ci`.
- The `Dependency audit` workflow (`.github/workflows/audit.yml`) checks the locked Python packages, development tools included, with pip-audit 2.10.1, and the web app's and the end-to-end tests' npm packages with `npm audit`. It runs on every push and pull request, every Monday at 06:37 UTC, and on demand. Its runs during Phase 6 found no known vulnerabilities.
- `frontend/package.json` overrides minimatch, which only ESLint and typescript-eslint use, to 11.0.3. Every version below 11.0.1 has a moderate advisory (CVE-2026-118764), and those tools still ask for 10.x. Remove the override once they ask for 11.
- The container images are pinned by tag: `python:3.12-slim`, `pgvector/pgvector:0.8.0-pg16`, and `nginxinc/nginx-unprivileged:1.30-alpine`.
- The embedding model, and the reranker of `hybrid_rerank`, are each pinned to a revision, downloaded once, and loaded from local files, with Hugging Face's offline mode and telemetry turned off.
- Updates are made by hand. Nothing opens update pull requests automatically.

## Known gaps

None of these matter much while the app runs on one computer for one person. Each matters before it serves anyone else.

| Gap | Why it matters | What would close it |
|---|---|---|
| No HTTPS, and the `Secure` cookie flag is off by default | On a network, sessions and documents would travel unencrypted | A TLS-terminating proxy and `SESSION_COOKIE_SECURE=true` |
| Rate limits live in one process's memory | They reset on restart and can't be shared by several API processes. Sign-in attempts aren't limited per account, and nothing limits how many questions run at once across accounts (R-24) | A shared store such as Redis, or limits in the proxy |
| Registration says whether an email has an account | It lets someone check which emails are registered, 10 times an hour per address | Turn registration off, or answer every registration the same way and send an email |
| Local accounts have no email verification, password reset, or second factor | Anyone can register with an address they don't own, if registration is open | `AUTH_MODE=oidc`, which leaves those to the provider |
| The sign-in through a provider hasn't met a hosted provider | CI shows it working against Keycloak in a browser. A hosted provider's quirks aren't shown | A run against a hosted provider |
| Provider accounts and password accounts can't be linked, and signing out doesn't sign out of the provider | Someone with a password account who moves to a provider gets a new account, or is refused when the email is taken | An explicit, signed-in linking step, and the provider's logout |
| No account or workspace deletion | Removing a user means clearing all local data | Endpoints that delete them with their files |
| No malware scanning or OCR | Uploaded files are stored as they are; scanned PDFs can't be indexed | A scanner before storage; OCR as an indexing step |
| Parser resource exhaustion | A crafted file could use substantial CPU or memory. A child process and hard timeout limit the exposure, but Windows has no equivalent parser memory limit (R-19) | Linux applies a child address-space limit; keep the parser child isolated and retain the upload and parse limits |
| Prompt injection is reduced, not removed | A model can still be steered by a passage that reaches it | The current checks, plus measuring with more planted documents |
| `/metrics` has no authentication | Anyone who can reach the API could read the counts | Keep it off, or behind the proxy's access control |
| Nothing is encrypted at rest by the app, and there are no backups | A copy of the disk exposes the documents | Disk encryption, and encrypted backups ([operations](../operations/README.md#backing-up-and-restoring)) |
| Images are pinned by tag, not digest, and updates are by hand | A tag can move, and a fix can wait for someone to notice it | Digests, and automated update pull requests |
| Ollama has no authentication (R-17) | Any local program can use it while it runs | Keep it on `127.0.0.1`, and stop it when not needed |
| No independent review or penetration test | These controls have only been checked by this project's own tests | An external review before any real use |

## Not for regulated use

This project is not certified for regulated or clinical use. It hasn't been assessed against any security, privacy, or medical-device standard, and it must not be used with real patient, personal, or confidential data. Use public, synthetic, or licensed documents only.
