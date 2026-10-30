"""Helpers shared by the tests: settings, sample files, API calls, and a stand-in embedder."""

import hashlib
import io
import math
import re
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from prometheus_client.parser import text_string_to_metric_families
from pypdf import PdfReader, PdfWriter

from app.core.config import Settings
from app.domain.grounding import ChatMessage
from app.domain.indexing import EMBEDDING_DIMENSION

# The sample-file builders live with the evaluation, which builds its corpus with them.
from app.evaluation.files import Heading as Heading
from app.evaluation.files import docx_bytes as docx_bytes
from app.evaluation.files import pdf_bytes as pdf_bytes
from app.providers.llm import Generation, LanguageModelUnavailableError
from app.services.ingestion import DocumentIndexer

CSRF_HEADERS = {"X-CSRF-Protection": "1"}
# Port 9 (discard) refuses connections, so unit tests fail fast if they touch the database.
UNREACHABLE_DATABASE_URL = "postgresql+psycopg://nobody:nothing@127.0.0.1:9/unit_tests"
DEFAULT_PASSWORD = "correct horse battery staple"
TXT_MIME = "text/plain"
PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": UNREACHABLE_DATABASE_URL,
        "database_connect_timeout_seconds": 1,
        # Uploads stay queued; tests that need indexing call index_queued_documents.
        "ingestion_worker_enabled": False,
        # Tests give an app a language model when they need one.
        "llm_provider": "none",
        # Tests that need expired questions deleted call the cleanup themselves.
        "question_cleanup_enabled": False,
        # Tests make many requests from one client; the rate limit tests turn the limits on.
        "rate_limits_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def encrypted_pdf_bytes(text: str, *, user_password: str) -> bytes:
    """A PDF encrypted with AES-256. With an empty user password, anyone can still open it."""
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_bytes(text))))
    writer.encrypt(user_password, "synthetic owner password", algorithm="AES-256")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def zip_bytes(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def register(
    client: TestClient, email: str = "reader@example.com", password: str = DEFAULT_PASSWORD
) -> Response:
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
        headers=CSRF_HEADERS,
    )


def login(
    client: TestClient, email: str = "reader@example.com", password: str = DEFAULT_PASSWORD
) -> Response:
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=CSRF_HEADERS,
    )


def create_workspace(client: TestClient, name: str = "Research notes") -> dict[str, Any]:
    response = client.post("/api/v1/workspaces", json={"name": name}, headers=CSRF_HEADERS)
    assert response.status_code == 201, response.text
    workspace: dict[str, Any] = response.json()
    return workspace


def upload(
    client: TestClient,
    workspace_id: str,
    filename: str,
    content: bytes,
    mime_type: str = "application/octet-stream",
) -> Response:
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": (filename, content, mime_type)},
        headers=CSRF_HEADERS,
    )


def error_code(response: Response) -> str:
    code: str = response.json()["error"]["code"]
    return code


def stored_files(storage_dir: Path) -> list[Path]:
    """Every file under the storage folder, including leftover temporary uploads."""
    return sorted(path for path in storage_dir.rglob("*") if path.is_file())


class HashingEmbeddings:
    """A fast, repeatable stand-in for the embedding model, so tests need no download.

    Each word adds 1 or -1 at a position picked by hashing it, so texts sharing words get
    similar vectors. Records the texts it was given.
    """

    def __init__(self) -> None:
        self.document_batches: list[list[str]] = []

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.document_batches.append(list(texts))
        return [hashed_vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return hashed_vector(text)


def hashed_vector(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSION
    for word in re.findall(r"\w+", text.lower()):
        digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
        position = int.from_bytes(digest[:4], "little") % EMBEDDING_DIMENSION
        vector[position] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        # No words, or words that cancel out: any fixed unit vector will do.
        vector[0], norm = 1.0, 1.0
    return [value / norm for value in vector]


def index_queued_documents(app: FastAPI) -> int:
    """Index every queued document now, as the background worker would. Returns how many."""
    state = app.state
    indexer = DocumentIndexer(
        state.session_factory,
        state.storage,
        state.embeddings,
        state.settings,
        metrics=state.metrics,
    )
    count = 0
    while indexer.process_next():
        count += 1
    return count


def sample_value(exposition: str, name: str, **labels: str) -> float | None:
    """A sample's value in metrics in Prometheus's text format, or None if there's none."""
    for family in text_string_to_metric_families(exposition):
        for sample in family.samples:
            if sample.name == name and sample.labels == labels:
                return float(sample.value)
    return None


def metric_value(app: FastAPI, name: str, **labels: str) -> float | None:
    """A sample's value in an app's metrics, whether or not /metrics serves them."""
    body, _ = app.state.metrics.exposition("")
    return sample_value(body.decode(), name, **labels)


class ScriptedLanguageModel:
    """A stand-in language model that gives set replies in turn, and records each prompt.

    With no replies left, or with `fail=True`, it acts like a model that doesn't respond. A
    `before` step runs first, as if it happened while the model was writing.
    """

    def __init__(self, *replies: str, name: str = "scripted-model", fail: bool = False) -> None:
        self.name = name
        self.prompts: list[list[ChatMessage]] = []
        self.before: Callable[[], None] | None = None
        self._replies = list(replies)
        self._fail = fail

    def generate(self, messages: Sequence[ChatMessage]) -> Generation:
        self.prompts.append(list(messages))
        if self.before is not None:
            self.before()
        if self._fail or not self._replies:
            raise LanguageModelUnavailableError(self.name)
        return Generation(self._replies.pop(0), self.name)


def ask(client: TestClient, workspace_id: str, text: str) -> Response:
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/questions", json={"text": text}, headers=CSRF_HEADERS
    )
