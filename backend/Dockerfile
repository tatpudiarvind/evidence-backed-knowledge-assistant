# Two images from one file:
# - development: the Compose development stack's image, with the test tools (compose.yaml).
# - production, the default: runtime packages only, run by a user without root rights
#   (compose.prod.yaml).

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN python -m pip install --no-cache-dir uv==0.13.5

# Install locked dependencies before copying source so code edits keep this layer cached.
COPY pyproject.toml uv.lock ./


FROM base AS development

RUN uv sync --locked --extra dev --no-install-project --no-cache

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM base AS production-dependencies

# Without the dev extras. The packages are compiled here because the app user can't write
# compiled files into the image, so Python would otherwise compile them on every start.
RUN UV_COMPILE_BYTECODE=1 uv sync --locked --no-install-project --no-cache


# A fresh base, so neither uv nor anything else used to build the environment is shipped.
FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-log-init --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=production-dependencies /app/.venv ./.venv
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

# Uploads (STORAGE_DIR) and the embedding model (EMBEDDING_MODEL_DIR) are written here. A new
# named volume mounted on either starts with this owner, so the app user can write to it.
RUN mkdir -p /app/storage /app/models \
    && chown app:app /app/storage /app/models

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4)"]

# One process on purpose: the rate limits count requests in its memory, so more processes would
# each keep separate counts, and each would start its own indexing and cleanup threads and load
# its own copy of the embedding model.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
