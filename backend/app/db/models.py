import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.documents import DocumentStatus
from app.domain.indexing import EMBEDDING_DIMENSION, MAX_SECTION_LENGTH
from app.domain.workspaces import WorkspaceRole


def _allowed_values(column: str, values: list[str]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Stored trimmed and lower-cased, so each address can register only once.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # SHA-256 of the session token; the token itself is only in the user's cookie.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceMembership(Base):
    """Who may use a workspace. Every workspace query joins this table on the current user."""

    __tablename__ = "workspace_memberships"
    __table_args__ = (
        CheckConstraint(_allowed_values("role", [role.value for role in WorkspaceRole]), "role"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            _allowed_values("status", [status.value for status in DocumentStatus]), "status"
        ),
        CheckConstraint("size_bytes > 0", "size_bytes_positive"),
        Index("ix_documents_workspace_id_created_at", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    # Sanitized original file name, for display only; never used to build a file path.
    display_name: Mapped[str] = mapped_column(String(255))
    # Random, server-generated name of the stored file.
    storage_key: Mapped[str] = mapped_column(String(32), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    failure_code: Mapped[str | None] = mapped_column(String(50))
    failure_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentChunk(Base):
    """A searchable piece of a document's text, its location, and its embedding (Phase 3)."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        # Its first column also serves finding and deleting a document's chunks.
        UniqueConstraint("document_id", "ordinal"),
        CheckConstraint("ordinal >= 0", "ordinal_not_negative"),
        CheckConstraint("page_number IS NULL OR page_number >= 1", "page_number_positive"),
        # Approximate nearest-neighbour search by cosine distance; it works on any number of
        # rows, unlike IVFFlat, which needs data before it is built.
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    # Reading order within the document, from 0.
    ordinal: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    # PDF pages, from 1; Word and text files have none.
    page_number: Mapped[int | None]
    # The Word heading the chunk falls under, if any.
    section: Mapped[str | None] = mapped_column(String(MAX_SECTION_LENGTH))
    # Read back as a NumPy array.
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIMENSION))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
