import uuid
from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import Select, delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, WorkspaceMembership
from app.domain.documents import DocumentStatus
from app.domain.indexing import TextChunk
from app.domain.questions import Passage

_Row = TypeVar("_Row", bound=tuple[Any, ...])


def replace_for_document(
    session: Session,
    document_id: uuid.UUID,
    chunks: Sequence[TextChunk],
    embeddings: Sequence[Sequence[float]],
) -> None:
    """Swap a document's chunks for new ones, so indexing again never leaves duplicates."""
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
    if not chunks:
        return
    session.execute(
        insert(DocumentChunk),
        [
            {
                "id": uuid.uuid4(),
                "document_id": document_id,
                "ordinal": chunk.ordinal,
                "text": chunk.text,
                "page_number": chunk.page_number,
                "section": chunk.section,
                "embedding": list(embedding),
            }
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ],
    )


def count_for_document(session: Session, document_id: uuid.UUID) -> int:
    statement = select(func.count()).select_from(DocumentChunk)
    return session.scalar(statement.where(DocumentChunk.document_id == document_id)) or 0


def _ready_for_member(
    statement: Select[_Row], workspace_id: uuid.UUID, user_id: uuid.UUID
) -> Select[_Row]:
    """Limit a chunk query to a workspace's ready documents, and to the workspace's members."""
    return (
        statement.join(Document, Document.id == DocumentChunk.document_id)
        .join(
            WorkspaceMembership,
            (WorkspaceMembership.workspace_id == Document.workspace_id)
            & (WorkspaceMembership.user_id == user_id),
        )
        .where(
            Document.workspace_id == workspace_id,
            Document.status == DocumentStatus.READY.value,
        )
    )


def search_statement(
    workspace_id: uuid.UUID, user_id: uuid.UUID, vector: Sequence[float], limit: int
) -> Select[Any]:
    """The query behind `search_workspace`. The evaluation also inspects its query plan."""
    distance = DocumentChunk.embedding.cosine_distance(list(vector))
    statement = _ready_for_member(
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.display_name,
            DocumentChunk.text,
            DocumentChunk.page_number,
            DocumentChunk.section,
            distance.label("distance"),
        ),
        workspace_id,
        user_id,
    )
    return statement.order_by(distance).limit(limit)


def search_workspace(
    session: Session,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    vector: Sequence[float],
    limit: int,
) -> list[Passage]:
    """The chunks of a workspace's ready documents closest to `vector`, closest first.

    Only a member's search finds anything. The HNSW index is approximate, so a close chunk can
    occasionally be missed. Its strict-order iterative scan keeps searching past chunks from
    other workspaces, so the filter doesn't leave fewer than `limit` results while enough
    exist, up to pgvector's scan limit.
    """
    session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    rows = session.execute(search_statement(workspace_id, user_id, vector, limit))
    return [
        Passage(
            chunk_id=row.id,
            document_id=row.document_id,
            document_name=row.display_name,
            text=row.text,
            page_number=row.page_number,
            section=row.section,
            similarity=1.0 - float(row.distance),
        )
        for row in rows
    ]


def workspace_has_indexed_chunks(
    session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    statement = _ready_for_member(select(DocumentChunk.id), workspace_id, user_id)
    return session.scalar(statement.limit(1)) is not None
