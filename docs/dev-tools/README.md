# Local development tools

The Windows tools for the Evidence-backed Knowledge Assistant, installed on 2026-10-27 in `D:\DevTools` for the project in `D:\Projects\evidence-backed-knowledge-assistant`. Ollama and its model, and the embedding model, were added on 2026-10-28.

This guide was `D:\DevTools\README.txt` until 2026-10-29, when it moved into the project's `docs` folder; that file now only points here. The general steps, for any machine, are in "[Without containers (no administrator rights)](../specification/README.md#without-containers-no-administrator-rights)" in the specification.

Everything in `D:\DevTools` is user-level. Nothing was installed as administrator, no Windows service was created, and the PATH, registry, and PowerShell profile were not changed. The scripts set paths for their own window only. To remove everything: run `pg-stop.cmd` and `ollama-stop.cmd`, then delete `D:\DevTools`. The project's root `.env` points `EMBEDDING_MODEL_DIR` at `D:\DevTools\models\huggingface`, so after deleting `D:\DevTools`, remove that line and download the embedding model again (see [below](#download-the-embedding-model-again)).

## Quick start

1. Start the database: `D:\DevTools\pg-start.cmd`
2. Apply the migrations, from the project's `backend` folder:

   ```powershell
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```

3. Run the API, from `backend`:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

4. Run the web app, from `frontend`: `npm run dev`, then open `http://localhost:5173`.
5. When you are done: `D:\DevTools\pg-stop.cmd`

The project's default `DATABASE_URL` already points at this server (`127.0.0.1:5432`, database `knowledge_assistant`), so the database needs no `.env` setting. With the database stopped, the API's `/health/ready` answers 503 in about 3 s on this machine. It took about 6 s while the default used `localhost`, which is tried as both `::1` and `127.0.0.1`.

Don't run this server and the project's Docker Compose stack at the same time: both use port 5432. Stop this one first, or set `POSTGRES_PORT` in the project's `.env` file.

### Try the local AI model

The app starts using it in Phase 4 of the project.

1. Start Ollama: `D:\DevTools\ollama-start.cmd`
2. Open `D:\DevTools\dev-shell.cmd` and ask the model something:

   ```powershell
   ollama run qwen3:4b-instruct-2507-q4_K_M "Say hello in five words."
   ```

3. When you are done: `D:\DevTools\ollama-stop.cmd`

The very first request took about a minute, because the GPU code was compiled once and saved in `D:\DevTools\ollama\cuda-cache`. After that, loading the model took about 2 s, and short answers came back in under a second once it was loaded. These are single observations on this laptop, not benchmarks.

### Download the embedding model again

The app has used the embedding model since Phase 3 of the project, to index uploaded documents. It is already downloaded into `D:\DevTools\models\huggingface`. To download it again, for example after deleting that folder, run this from the project's `backend` folder:

```powershell
.\.venv\Scripts\python.exe -m app.cli download-embedding-model
```

It downloads about 135 MB once, through the Windows certificate store, then checks that the model loads without a network. Documents that failed because the model was missing can then be retried in the app, without restarting the API.

## Scripts

All in `D:\DevTools`. Double-click them, or run them from any terminal.

- `pg-start.cmd`: starts PostgreSQL in a hidden window. It keeps running when you close your terminal, and Ctrl+C there doesn't stop it. Stop it with `pg-stop.cmd` before you sign out or shut down Windows. If it was stopped some other way, the next start replays its log and recovers automatically; the log then says "automatic recovery in progress".
- `pg-stop.cmd`: stops PostgreSQL (fast shutdown: open connections are closed).
- `pg-status.cmd`: shows whether PostgreSQL is running and accepting connections.
- `pg-psql.cmd`: opens psql on the `knowledge_assistant` database. Extra arguments go to psql, for example `pg-psql.cmd -c "\dx"`.
- `ollama-start.cmd`: starts Ollama in a hidden window, listening on this computer only (`127.0.0.1:11434`), with its cloud features turned off. Its models, key pair, temporary files, compiled GPU code, and log stay in `D:\DevTools`. It keeps running when you close your terminal. A loaded model uses about 3.2 GB of GPU memory until 5 minutes after the last request.
- `ollama-stop.cmd`: stops Ollama and its model runner (`llama-server.exe`): every program running from `D:\DevTools\ollama`. The models are kept.
- `ollama-status.cmd`: shows whether Ollama is running, its version, and the downloaded and loaded models.
- `dev-shell.cmd`: opens PowerShell with Node.js 22, the PostgreSQL tools, and the `ollama` command first on PATH, for that window only. Start the Ollama server with `ollama-start.cmd`, not with `ollama serve`, so that all its files stay in `D:\DevTools`.
- `backend-checks-py312.cmd`: runs the backend checks (ruff, ruff format, mypy, pytest) on Python 3.12, the version CI uses. Optional argument: the path to the backend folder.
- `frontend-checks-node22.cmd`: runs the frontend checks (lint, typecheck, test, build) on Node.js 22, the version CI uses. Uses the existing `node_modules`; run `npm ci` first if `package-lock.json` changed. Optional argument: the path to the frontend folder.

## What is installed

Folders in `D:\DevTools`:

- `postgresql\16\`: PostgreSQL 16.15 for Windows x64, from EDB's binaries zip (`postgresql-16.15-5-windows-x64-binaries.zip`): server, client tools, libraries, and headers. pgAdmin, StackBuilder, and the documentation were not extracted. Includes pgvector 0.8.0, built here from source.
- `pgdata\knowledge-assistant-pg16\`: the database cluster. UTF8 encoding, locale C, scram-sha-256 passwords, listens on localhost only (`127.0.0.1` and `::1`), port 5432. Superuser `knowledge_assistant`, password `local_dev_only`; database `knowledge_assistant` (the project's migration enables pgvector). The password is the project's local-development default from `.env.example`. Don't reuse it for anything reachable from other machines.
- `python\`: Python 3.12.15, installed by uv without registry entries or shims. Interpreter: `D:\DevTools\python\cpython-3.12.15-windows-x86_64-none\python.exe`.
- `venvs\eka-backend-py312\`: backend environment on Python 3.12, synced from `backend\uv.lock`. The project's own `backend\.venv` (Python 3.14) is separate. Since Phase 3 of the project, both hold PyTorch 2.14.1 (the CPU-only build) and sentence-transformers 6.2.0.
- `node\node-v22.23.4-win-x64\`: Node.js 22.23.4 LTS with npm 10.9.9. Your usual Node.js 24 is unchanged.
- `ollama\v0.40.12\`: Ollama 0.40.12 for Windows x64, from `ollama-windows-amd64.zip` on Ollama's GitHub releases page: the ollama program and its GPU libraries. No installer was run.
- `ollama\models\`: the local AI model `qwen3:4b-instruct-2507-q4_K_M` (Qwen3-4B-Instruct-2507, 4-bit, 2.5 GB, Apache-2.0), the project's choice (D-36 in the [decision log](../tracker/03-decisions-risks-issues.md)).
- `ollama\home\`: the key pair Ollama created on its first start (`.ollama\id_ed25519` and `id_ed25519.pub`). Not used by the project. Keep the private key private: don't share it or copy it into the project.
- `ollama\cuda-cache\`: GPU code compiled on the first request. Safe to delete; it is rebuilt.
- `ollama\tmp\`: Ollama's temporary files. Safe to empty while Ollama is stopped.
- `models\huggingface\`: the embedding model `BAAI/bge-small-en-v1.5` (MIT license), the project's choice (D-34 and D-46 in the decision log), at the pinned revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`: 13 files, 134,508,296 bytes, in Hugging Face's cache layout. The project's root `.env` points `EMBEDDING_MODEL_DIR` here, so both Python environments use this copy. The app loads it without a network and runs it on the CPU.
- `cache\uv\`: uv's download cache. Safe to delete.
- `src\pgvector-0.8.0\`: pgvector source and build files. Keep them to rebuild pgvector or re-run its tests; otherwise safe to delete.
- `downloads\`: the original zip files, Node.js's `SHASUMS256.txt`, and Ollama's `sha256sum.txt` and `install.ps1` (kept for reference; it was not run). Safe to delete.
- `logs\`: `postgres-16.log` and `ollama.log` (server logs; every start appends to them), and the pgvector build and test logs. `ollama.log` lists requests, but not the questions or the answers.

## How it was checked (2026-10-27)

- PostgreSQL zip: 373,254,386 bytes; SHA-256 `43BB45F173A6F08CF1D29A97A6D8DEB119E8E8093A24C00D2D1001A0CCAA8281`, computed after the download. EDB publishes no checksum for it, and its .exe files are not code-signed.
- pgvector: git tag v0.8.0 (commit `2627c5ff775ae6d7aef0c430121ccf857842d2f2`), built with Visual Studio 2026 (MSVC 19.51) using `nmake /F Makefile.win`: 0 warnings, 0 errors. Its regression tests (`installcheck`) passed: 14 of 14.
- Node.js zip: SHA-256 matches nodejs.org's `SHASUMS256.txt`; `node.exe` is signed by the OpenJS Foundation.
- With the project: the migration upgrades, downgrades, and upgrades again; `/health/ready` returns 200 with the database running and 503 with it stopped; the landing page shows "API and database are ready"; the backend checks pass on Python 3.12.15 and the frontend checks pass on Node.js 22.23.4.
- Details: the [verification log](../tracker/02-verification-log.md), V-42 onward.

## How Ollama was checked (2026-10-28)

- Ollama zip: 1,601,458,136 bytes; SHA-256 `21814944F3E50D3F07B6BB3AF75BADDB96F59E91353C332AC9C5063B3BFD1041`, the same as in Ollama's `sha256sum.txt` for v0.40.12 and in GitHub's record of the file. `ollama.exe` is signed by Ollama Inc., but Windows reports the signature as UnknownError here, because this machine doesn't trust the certificate's root (DigiCert CS ECC P384 Root G5). Which roots the machine trusts is a security setting, so it was left alone; the checksum shows the file is the one Ollama published.
- Server: listens on `127.0.0.1:11434` only, and the model runner it starts listens on another `127.0.0.1` port. Its log says "Ollama cloud disabled: true" and that it found the NVIDIA GPU. It can still contact ollama.com, to download models and to refresh its list of recommended models.
- Model: downloaded through the local server in about 2 minutes. Each of its 6 files matches the SHA-256 in its name, and `ollama show --license` prints the Apache License 2.0.
- Answers: given a short made-up text (temperature 0), it answered a question about the text with a citation, and replied `INSUFFICIENT_EVIDENCE` to a question the text didn't cover. `ollama ps` showed 3.2 GB, 100% GPU, context 4096.
- Start, stop, and status were each run twice; stop also ends the model runner.
- Nothing was written to the usual places on C: (the `.ollama` folder in the user profile, `AppData\Local\Ollama`, `AppData\Local\Programs\Ollama`, `ollama*` folders in the temporary folder, and NVIDIA's compiled-code cache in `AppData\Roaming`).
- Details: the [verification log](../tracker/02-verification-log.md), V-69 to V-74.

## How the embedding model was checked (2026-10-28)

- The project's download command fetched the pinned revision through the Windows certificate store, with certificate checks left on, then loaded the model without a network and reported 384-dimensional vectors.
- The model card at that revision says license: mit, and that the released models can be used for commercial purposes free of charge.
- On this laptop's CPU, with Python 3.14 and PyTorch 2.14.1: loading the model and answering the first query took 6.5 s; single queries then took 9 to 12 ms; batches of 100 chunks of 1,000 characters took 1.8 to 1.9 s; the process's working set peaked at 751 MiB. These are single observations, not benchmarks.
- Details: the [verification log](../tracker/02-verification-log.md), V-104 and V-105.

## Keeping it up to date

Nothing in `D:\DevTools` updates itself. Check for security releases now and then.

- PostgreSQL 16.x: run `pg-stop.cmd`; replace `bin`, `lib`, `include`, and `share` in `D:\DevTools\postgresql\16` with those from the new zip (this removes pgvector); then rebuild and reinstall pgvector in an "x64 Native Tools Command Prompt": `set PGROOT=D:\DevTools\postgresql\16`, then in `D:\DevTools\src\pgvector-0.8.0` run `nmake /F Makefile.win clean`, `nmake /F Makefile.win`, and `nmake /F Makefile.win install`. The data in `D:\DevTools\pgdata` is kept.
- Node.js 22.x: download the new zip and `SHASUMS256.txt` from nodejs.org, compare the checksum, extract it next to the current folder, and update the folder name in `dev-shell.cmd` and `frontend-checks-node22.cmd`.
- Python 3.12.x: from the project's `backend` folder, run:

  ```powershell
  .\.venv\Scripts\uv.exe python install 3.12 --install-dir D:\DevTools\python --no-bin --no-registry
  ```

- Ollama: run `ollama-stop.cmd`; download the new `ollama-windows-amd64.zip` and `sha256sum.txt` from Ollama's GitHub releases and compare the checksum; extract it into a new folder next to `D:\DevTools\ollama\v0.40.12` (Ollama's documentation says to remove an older version's folders rather than extract over them); update the folder name in `ollama-start.cmd`, `ollama-status.cmd`, and `dev-shell.cmd`; then delete the old folder. The models are kept.
- The model: the project pins it (D-36). Record a change in the [project tracker](../tracker/README.md) first; then, with Ollama running, pull the new model in `dev-shell.cmd` (`ollama pull <name>`) and remove the old one (`ollama rm <name>`).
- The embedding model: the project pins its name and revision (D-34, D-46). Record a change in the project tracker first. Another model means indexing every document again, and a new database migration if its vectors don't have 384 values.

## Not installed, and why

- Docker Desktop, Podman, or Rancher Desktop: each needs WSL2 or Hyper-V, which are turned off on this machine, and turning them on needs administrator rights. Ask IT, or look in the company software portal (Software Center). Docker Desktop needs a paid subscription at larger companies; Rancher Desktop and Podman are free and open source. Podman Desktop 1.30.5 was installed on 2026-10-28, but it is only the GUI: the Podman engine it offers to install still needs WSL2 or Hyper-V, so it cannot run here. By the owner's choice (D-31), development stays on this machine without containers: follow "[Without containers (no administrator rights)](../specification/README.md#without-containers-no-administrator-rights)" in the specification, using the scripts above for the database.
- conda / micromamba packages: conda-forge (anaconda.org) is blocked by this machine's network policy, so they were not used.
- Ollama's installer (`OllamaSetup.exe`), and the one-line command that runs it (`irm https://ollama.com/install.ps1 | iex`): not used. The command's script was read but not run. By default the installer puts Ollama in `AppData\Local\Programs\Ollama` on C:, adds that folder to your user PATH, registers an `ollama://` link handler, adds Start menu shortcuts, and starts the Ollama app in the background; models go to the `.ollama` folder in your user profile on C: unless `OLLAMA_MODELS` is set for your account. The script also stops unless Windows reports the installer's signature as valid, which most likely fails here (see [How Ollama was checked](#how-ollama-was-checked-2026-10-28)). The zip above is the same Ollama release without the desktop app and without those changes.
- Playwright browsers, pgAdmin: not needed yet.
