"""Indexing: turns queued documents into searchable chunks (Phase 3, spec section 6.1).

A document goes from `queued` to `processing`, then to `ready` with its chunks saved, or to
`failed` with a code and a message that are safe to show. A document deleted part-way through
is left alone. Logs name documents by ID only, never quoting their text.
"""

import io
import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.domain.documents import DocumentStatus
from app.domain.indexing import (
    IndexingError,
    IndexingFailure,
    TextChunk,
    chunk_blocks,
    normalize_blocks,
)
from app.providers.embeddings import EmbeddingProvider, EmbeddingUnavailableError, check_vectors
from app.providers.parsers import ParseLimits, parser_for
from app.providers.storage import DocumentStorage
from app.repositories import chunks as chunk_repository
from app.repositories import documents as document_repository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Job:
    document_id: uuid.UUID
    storage_key: str
    mime_type: str


class DocumentIndexer:
    """Indexes one queued document at a time: read, split into chunks, embed, and save."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: DocumentStorage,
        embeddings: EmbeddingProvider,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._embeddings = embeddings
        self._limits = ParseLimits(
            max_pages=settings.max_document_pages,
            max_characters=settings.max_document_characters,
            timeout_seconds=settings.parse_timeout_seconds,
        )
        self._chunk_size = settings.chunk_size_characters
        self._chunk_overlap = settings.chunk_overlap_characters

    def recover_interrupted(self) -> int:
        """Queue again the documents left `processing`, as when the server stopped mid-way."""
        with self._session_factory() as session:
            count = document_repository.requeue_processing(session)
            session.commit()
        if count:
            logger.info("Queued %d interrupted document(s) to be indexed again", count)
        return count

    def process_next(self) -> bool:
        """Index the oldest queued document. Returns False if none is waiting.

        Errors from the database itself propagate, leaving the document `processing` until
        `recover_interrupted` queues it again.
        """
        with self._session_factory() as session:
            document = document_repository.claim_next_queued(session)
            if document is None:
                return False
            document.status = DocumentStatus.PROCESSING.value
            job = _Job(document.id, document.storage_key, document.mime_type)
            session.commit()
        self._index(job)
        return True

    def _index(self, job: _Job) -> None:
        started = time.perf_counter()
        try:
            chunks = self._read_chunks(job)
            embeddings = self._embed(chunks)
            saved = self._save(job.document_id, chunks, embeddings)
        except IndexingError as error:
            cause = f" ({type(error.__cause__).__name__})" if error.__cause__ else ""
            logger.warning(
                "Indexing document %s failed: %s%s", job.document_id, error.failure.value, cause
            )
            self._mark_failed(job.document_id, error)
            return
        except Exception as error:
            logger.warning(
                "Indexing document %s failed unexpectedly (%s)",
                job.document_id,
                type(error).__name__,
            )
            # Error messages can quote a document, so the details are only logged on request.
            logger.debug("Indexing failure details", exc_info=True)
            self._mark_failed(job.document_id, IndexingError(IndexingFailure.INGESTION_FAILED))
            return
        if saved:
            logger.info(
                "Indexed document %s: %d chunks in %.1f s",
                job.document_id,
                len(chunks),
                time.perf_counter() - started,
            )
        else:
            logger.info("Document %s changed while being indexed; discarded", job.document_id)

    def _read_chunks(self, job: _Job) -> list[TextChunk]:
        try:
            handle = self._storage.open(job.storage_key)
        except FileNotFoundError:
            raise IndexingError(IndexingFailure.FILE_MISSING) from None
        # Copied into memory so the stored file is closed again at once: on Windows, an open
        # file can't be deleted. The upload size limit bounds the copy.
        with handle:
            data = io.BytesIO(handle.read())
        blocks = parser_for(job.mime_type, self._limits).extract(data)
        chunks = chunk_blocks(normalize_blocks(blocks), self._chunk_size, self._chunk_overlap)
        if not chunks:
            raise IndexingError(IndexingFailure.NO_TEXT_FOUND)
        return chunks

    def _embed(self, chunks: Sequence[TextChunk]) -> list[list[float]]:
        try:
            embeddings = self._embeddings.embed_documents([chunk.text for chunk in chunks])
        except EmbeddingUnavailableError:
            raise IndexingError(IndexingFailure.EMBEDDING_UNAVAILABLE) from None
        except Exception as error:
            raise IndexingError(IndexingFailure.EMBEDDING_FAILED) from error
        if not check_vectors(embeddings, len(chunks)):
            raise IndexingError(IndexingFailure.EMBEDDING_FAILED)
        return embeddings

    def _save(
        self,
        document_id: uuid.UUID,
        chunks: Sequence[TextChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> bool:
        with self._session_factory() as session:
            document = document_repository.get_by_id(session, document_id, lock=True)
            # Deleted, or being deleted, while it was indexed.
            if document is None or document.status != DocumentStatus.PROCESSING:
                return False
            chunk_repository.replace_for_document(session, document_id, chunks, embeddings)
            document.status = DocumentStatus.READY.value
            document.failure_code = None
            document.failure_message = None
            session.commit()
        return True

    def _mark_failed(self, document_id: uuid.UUID, error: IndexingError) -> None:
        with self._session_factory() as session:
            document = document_repository.get_by_id(session, document_id, lock=True)
            if document is None or document.status != DocumentStatus.PROCESSING:
                return
            document.status = DocumentStatus.FAILED.value
            document.failure_code = error.failure.value
            document.failure_message = error.message
            session.commit()
