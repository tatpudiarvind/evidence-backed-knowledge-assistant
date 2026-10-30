"""Indexing queued documents (P3-07 - P3-12) against the PostgreSQL test database.

Most tests run the indexer directly, as the background worker would, with `HashingEmbeddings`
standing in for the model. The last test runs the real background worker.
"""

import logging
import math
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Document, DocumentChunk
from app.domain.indexing import EMBEDDING_DIMENSION, FAILURE_MESSAGES, IndexingFailure
from app.providers.embeddings import EmbeddingUnavailableError
from app.repositories import chunks as chunk_repository
from app.repositories import documents as document_repository
from app.services.ingestion import DocumentIndexer
from tests.conftest import AppFactory
from tests.support import (
    CSRF_HEADERS,
    HashingEmbeddings,
    Heading,
    create_workspace,
    docx_bytes,
    encrypted_pdf_bytes,
    hashed_vector,
    index_queued_documents,
    metric_value,
    pdf_bytes,
    register,
    stored_files,
    upload,
    zip_bytes,
)

pytestmark = pytest.mark.integration

SECRET_TEXT = "Synthetic confidential sentence that must never reach the logs."
WAIT_SECONDS = 10
PROCESSED = "knowledge_assistant_documents_processed_total"


@dataclass
class Library:
    """A signed-in user's workspace, in an app whose background worker is off."""

    app: FastAPI
    client: TestClient
    workspace_id: str

    def upload(self, filename: str, content: bytes) -> str:
        response = upload(self.client, self.workspace_id, filename, content)
        assert response.status_code == 202, response.text
        document_id: str = response.json()["id"]
        return document_id

    def index(self) -> int:
        return index_queued_documents(self.app)

    def document(self, document_id: str) -> dict[str, Any]:
        response = self.client.get(f"/api/v1/documents/{document_id}")
        assert response.status_code == 200, response.text
        document: dict[str, Any] = response.json()
        return document

    def delete(self, document_id: str) -> int:
        return self.client.delete(
            f"/api/v1/documents/{document_id}", headers=CSRF_HEADERS
        ).status_code

    def chunks(self, document_id: str) -> list[DocumentChunk]:
        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == uuid.UUID(document_id))
            .order_by(DocumentChunk.ordinal)
        )
        with self.app.state.session_factory() as session:
            return list(session.scalars(statement))

    def set_status(self, document_id: str, status: str) -> None:
        with self.app.state.session_factory() as session:
            document = session.get(Document, uuid.UUID(document_id))
            assert document is not None
            document.status = status
            session.commit()


@pytest.fixture
def make_library(
    make_db_app: AppFactory, make_client: Callable[[FastAPI], TestClient]
) -> Callable[..., Library]:
    def factory(**overrides: Any) -> Library:
        app = make_db_app(**overrides)
        client = make_client(app)
        assert register(client).status_code == 201
        return Library(app, client, create_workspace(client)["id"])

    return factory


@pytest.fixture
def library(make_library: Callable[..., Library]) -> Library:
    return make_library()


class ControlledEmbeddings(HashingEmbeddings):
    """Hashing embeddings that can run a step first, be unavailable, or return other vectors."""

    def __init__(self) -> None:
        super().__init__()
        self.before: Callable[[], None] | None = None
        self.available = True
        self.result: Callable[[Sequence[str]], list[list[float]]] | None = None

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if self.before is not None:
            self.before()
        if not self.available:
            raise EmbeddingUnavailableError("synthetic-model")
        if self.result is not None:
            return self.result(texts)
        return super().embed_documents(texts)


def test_text_files_become_ready_with_one_chunk(library: Library) -> None:
    document_id = library.upload("notes.txt", b"  Synthetic notes:\r\n\r\n\r\nkept for 7 years.  ")

    assert library.index() == 1
    assert library.index() == 0

    document = library.document(document_id)
    assert document["status"] == "ready"
    assert document["failure_code"] is None
    assert document["failure_message"] is None
    assert metric_value(library.app, PROCESSED, outcome="indexed") == 1
    [chunk] = library.chunks(document_id)
    assert (chunk.ordinal, chunk.text, chunk.page_number, chunk.section) == (
        0,
        "Synthetic notes:\n\nkept for 7 years.",
        None,
        None,
    )
    assert chunk.embedding.tolist() == pytest.approx(hashed_vector(chunk.text), abs=1e-6)


def test_pdf_chunks_keep_their_page_numbers(library: Library) -> None:
    document_id = library.upload("paper.pdf", pdf_bytes("Page one text.", "", "Page three text."))

    library.index()

    assert library.document(document_id)["status"] == "ready"
    chunks = library.chunks(document_id)
    assert [(chunk.ordinal, chunk.text, chunk.page_number) for chunk in chunks] == [
        (0, "Page one text.", 1),
        (1, "Page three text.", 3),
    ]


def test_word_chunks_keep_their_sections(library: Library) -> None:
    content = docx_bytes("Summary first.", Heading("Methods"), "Counted synthetic items.")
    document_id = library.upload("report.docx", content)

    library.index()

    chunks = library.chunks(document_id)
    assert [(chunk.text, chunk.page_number, chunk.section) for chunk in chunks] == [
        ("Summary first.", None, None),
        ("Methods\n\nCounted synthetic items.", None, "Methods"),
    ]


def test_long_documents_become_overlapping_chunks_of_whole_sentences(
    make_library: Callable[..., Library],
) -> None:
    library = make_library(chunk_size_characters=200, chunk_overlap_characters=40)
    sentences = [f"Synthetic sentence {n} describes item number {n}." for n in range(40)]
    document_id = library.upload("long.txt", " ".join(sentences).encode())

    library.index()

    chunks = library.chunks(document_id)
    assert len(chunks) > 5
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    assert all(len(chunk.text) <= 200 for chunk in chunks)
    assert all(any(sentence in chunk.text for chunk in chunks) for sentence in sentences)


def test_indexing_again_replaces_the_chunks(library: Library) -> None:
    document_id = library.upload("notes.txt", b"Synthetic text indexed twice.")
    library.index()
    [first] = library.chunks(document_id)

    library.set_status(document_id, "queued")
    library.index()

    [second] = library.chunks(document_id)
    assert second.id != first.id
    assert second.text == first.text


def test_the_oldest_queued_document_is_indexed_first(library: Library) -> None:
    library.upload("first.txt", b"First document.")
    library.upload("second.txt", b"Second document.")

    library.index()

    assert library.app.state.embeddings.document_batches == [
        ["First document."],
        ["Second document."],
    ]


def test_two_indexers_never_claim_the_same_document(library: Library) -> None:
    uploaded = {library.upload("one.txt", b"One."), library.upload("two.txt", b"Two.")}
    sessions = library.app.state.session_factory

    with sessions() as first, sessions() as second, sessions() as third:
        claimed = [
            document_repository.claim_next_queued(first),
            document_repository.claim_next_queued(second),
        ]
        assert {str(document.id) for document in claimed if document} == uploaded
        assert document_repository.claim_next_queued(third) is None


def _assert_failed(library: Library, document_id: str, failure: IndexingFailure) -> None:
    document = library.document(document_id)
    assert (document["status"], document["failure_code"]) == ("failed", failure.value)
    assert document["failure_message"] == FAILURE_MESSAGES[failure]
    assert library.chunks(document_id) == []
    assert metric_value(library.app, PROCESSED, outcome=failure.value) == 1


@pytest.mark.parametrize(
    ("filename", "content", "settings", "failure"),
    [
        ("blank.txt", b" \n\t\r\n ", {}, IndexingFailure.NO_TEXT_FOUND),
        ("scan.pdf", pdf_bytes(""), {}, IndexingFailure.NO_TEXT_FOUND),
        (
            "locked.pdf",
            encrypted_pdf_bytes("Secret", user_password="synthetic password"),
            {},
            IndexingFailure.DOCUMENT_ENCRYPTED,
        ),
        ("damaged.pdf", b"%PDF-1.7\nnot really a PDF", {}, IndexingFailure.DOCUMENT_UNREADABLE),
        (
            "damaged.docx",
            zip_bytes({"[Content_Types].xml": "<Types/>", "word/document.xml": "<document/>"}),
            {},
            IndexingFailure.DOCUMENT_UNREADABLE,
        ),
        (
            "long.pdf",
            pdf_bytes("one", "two"),
            {"max_document_pages": 1},
            IndexingFailure.TOO_MANY_PAGES,
        ),
        (
            "long.txt",
            b"x" * 1001,
            {"max_document_characters": 1000},
            IndexingFailure.TOO_MUCH_TEXT,
        ),
    ],
    ids=[
        "blank-text",
        "pdf-without-text",
        "locked-pdf",
        "damaged-pdf",
        "damaged-docx",
        "pages",
        "characters",
    ],
)
def test_documents_that_cannot_be_indexed_fail_with_a_reason(
    make_library: Callable[..., Library],
    filename: str,
    content: bytes,
    settings: dict[str, Any],
    failure: IndexingFailure,
) -> None:
    library = make_library(**settings)
    document_id = library.upload(filename, content)

    assert library.index() == 1

    _assert_failed(library, document_id, failure)


def test_a_missing_stored_file_fails_indexing(library: Library, storage_dir: Path) -> None:
    document_id = library.upload("notes.txt", b"Synthetic text.")
    for path in stored_files(storage_dir):
        path.unlink()

    library.index()

    _assert_failed(library, document_id, IndexingFailure.FILE_MISSING)


def test_documents_can_be_retried_once_the_model_is_available(
    make_library: Callable[..., Library],
) -> None:
    embeddings = ControlledEmbeddings()
    embeddings.available = False
    library = make_library(embeddings=embeddings)
    document_id = library.upload("notes.txt", b"Synthetic text.")
    library.index()
    _assert_failed(library, document_id, IndexingFailure.EMBEDDING_UNAVAILABLE)

    embeddings.available = True
    retried = library.client.post(f"/api/v1/documents/{document_id}/retry", headers=CSRF_HEADERS)

    assert retried.status_code == 202
    assert retried.json()["status"] == "queued"
    assert library.index() == 1
    assert library.document(document_id)["status"] == "ready"
    assert len(library.chunks(document_id)) == 1


def _raise_secret(texts: Sequence[str]) -> list[list[float]]:
    raise RuntimeError(SECRET_TEXT)


@pytest.mark.parametrize(
    "result",
    [
        lambda texts: [],
        lambda texts: [[0.5] * 10 for _ in texts],
        lambda texts: [[math.nan] * EMBEDDING_DIMENSION for _ in texts],
        _raise_secret,
    ],
    ids=["too-few-vectors", "wrong-size", "not-a-number", "error"],
)
def test_bad_embeddings_fail_the_document_without_logging_its_text(
    make_library: Callable[..., Library],
    caplog: pytest.LogCaptureFixture,
    result: Callable[[Sequence[str]], list[list[float]]],
) -> None:
    caplog.set_level(logging.INFO)
    embeddings = ControlledEmbeddings()
    embeddings.result = result
    library = make_library(embeddings=embeddings)
    document_id = library.upload("secret.txt", SECRET_TEXT.encode())

    library.index()

    _assert_failed(library, document_id, IndexingFailure.EMBEDDING_FAILED)
    assert f"Indexing document {document_id} failed: embedding_failed" in caplog.text
    assert SECRET_TEXT not in caplog.text


def test_unexpected_errors_fail_the_document_without_logging_details(
    library: Library, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    def failing_replace(*args: object) -> None:
        raise RuntimeError(SECRET_TEXT)

    monkeypatch.setattr(chunk_repository, "replace_for_document", failing_replace)
    document_id = library.upload("secret.txt", SECRET_TEXT.encode())

    library.index()

    _assert_failed(library, document_id, IndexingFailure.INGESTION_FAILED)
    assert "failed unexpectedly (RuntimeError)" in caplog.text
    assert SECRET_TEXT not in caplog.text


@pytest.mark.parametrize("delete_completes", [True, False], ids=["deleted", "still-deleting"])
def test_documents_deleted_while_being_indexed_are_left_alone(
    make_library: Callable[..., Library],
    storage_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    delete_completes: bool,
) -> None:
    embeddings = ControlledEmbeddings()
    library = make_library(embeddings=embeddings)
    document_id = library.upload("notes.txt", b"Synthetic text.")

    def delete_document() -> None:
        if delete_completes:
            assert library.delete(document_id) == 204
            return

        def locked_file(key: str) -> None:
            raise PermissionError("the file is locked by another program")

        with monkeypatch.context() as patch:
            patch.setattr(library.app.state.storage, "delete", locked_file)
            assert library.delete(document_id) == 500

    embeddings.before = delete_document
    library.index()

    assert library.chunks(document_id) == []
    assert metric_value(library.app, PROCESSED, outcome="discarded") == 1
    if delete_completes:
        assert library.client.get(f"/api/v1/documents/{document_id}").status_code == 404
        assert stored_files(storage_dir) == []
    else:
        assert library.document(document_id)["status"] == "deleting"
        assert library.delete(document_id) == 204


def test_documents_deleted_while_their_indexing_fails_count_as_discarded(
    make_library: Callable[..., Library],
) -> None:
    embeddings = ControlledEmbeddings()
    embeddings.available = False
    library = make_library(embeddings=embeddings)
    document_id = library.upload("notes.txt", b"Synthetic text.")

    def delete_document() -> None:
        assert library.delete(document_id) == 204

    embeddings.before = delete_document
    library.index()

    assert library.client.get(f"/api/v1/documents/{document_id}").status_code == 404
    assert metric_value(library.app, PROCESSED, outcome="discarded") == 1
    assert metric_value(library.app, PROCESSED, outcome="embedding_unavailable") is None


def test_deleting_an_indexed_document_deletes_its_chunks(library: Library) -> None:
    document_id = library.upload("notes.txt", b"Synthetic text.")
    library.index()
    assert len(library.chunks(document_id)) == 1

    assert library.delete(document_id) == 204

    with library.app.state.session_factory() as session:
        assert chunk_repository.count_for_document(session, uuid.UUID(document_id)) == 0


def test_documents_left_processing_are_queued_again(library: Library) -> None:
    document_id = library.upload("notes.txt", b"Synthetic text.")
    library.set_status(document_id, "processing")
    state = library.app.state
    indexer = DocumentIndexer(
        state.session_factory, state.storage, state.embeddings, state.settings
    )

    assert indexer.recover_interrupted() == 1
    assert library.document(document_id)["status"] == "queued"
    assert indexer.recover_interrupted() == 0


def test_the_background_worker_indexes_uploads(make_library: Callable[..., Library]) -> None:
    library = make_library(ingestion_worker_enabled=True)
    worker = library.app.state.ingestion_worker

    # Entering the client runs the app's startup, which starts the worker, and leaving stops it.
    with library.client:
        assert worker.running
        document_id = library.upload("notes.txt", b"Synthetic text for the worker.")
        deadline = time.monotonic() + WAIT_SECONDS
        while library.document(document_id)["status"] in ("queued", "processing"):
            assert time.monotonic() < deadline, "the worker didn't index the upload in time"
            time.sleep(0.05)
        assert library.document(document_id)["status"] == "ready"

    assert not worker.running
