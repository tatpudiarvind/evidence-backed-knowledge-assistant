import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk
from app.domain.indexing import TextChunk


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
