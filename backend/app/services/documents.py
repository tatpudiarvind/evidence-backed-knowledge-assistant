"""Document lifecycle: upload, list, read, download, retry indexing, and delete (D-33)."""

import logging
import uuid
from collections.abc import Sequence
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import Document, User
from app.domain.documents import (
    DocumentStatus,
    ReceivedFile,
    content_matches,
    file_type_for_name,
    sanitize_display_name,
)
from app.providers.storage import DocumentStorage, new_storage_key
from app.repositories import documents as document_repository
from app.services.workspaces import require_workspace

logger = logging.getLogger(__name__)


def list_documents(session: Session, user: User, workspace_id: uuid.UUID) -> Sequence[Document]:
    require_workspace(session, user, workspace_id)
    return document_repository.list_for_member(session, workspace_id, user.id)


def get_document(session: Session, user: User, document_id: uuid.UUID) -> Document:
    document = document_repository.get_for_member(session, document_id, user.id)
    if document is None:
        raise _document_not_found()
    return document


def check_can_upload(session: Session, user: User, workspace_id: uuid.UUID) -> None:
    """Checked before the file is received, so non-members can't make the server store data."""
    require_workspace(session, user, workspace_id)
    # End the read transaction: no connection or transaction stays open while the file arrives.
    session.rollback()


def store_upload(
    session: Session,
    storage: DocumentStorage,
    settings: Settings,
    user: User,
    workspace_id: uuid.UUID,
    received: ReceivedFile,
) -> Document:
    display_name = sanitize_display_name(received.filename)
    file_type = file_type_for_name(display_name)
    if file_type is None:
        raise AppError(
            415,
            "unsupported_file_type",
            "Only PDF, Word (.docx), and plain-text (.txt) files can be uploaded.",
        )
    if not content_matches(received.path, file_type):
        raise AppError(422, "invalid_file_content", file_type.invalid_content_message)

    # Locking the workspace row makes concurrent uploads take turns, so the limit holds.
    require_workspace(session, user, workspace_id, lock=True)
    limit = settings.max_documents_per_workspace
    if document_repository.count_in_workspace(session, workspace_id) >= limit:
        raise AppError(
            409,
            "document_limit_reached",
            f"This workspace already has the maximum of {limit} documents. "
            "Delete one to upload another.",
        )

    storage_key = new_storage_key()
    storage.save(storage_key, received.path)
    try:
        document = Document(
            workspace_id=workspace_id,
            display_name=display_name,
            storage_key=storage_key,
            mime_type=file_type.mime_type,
            size_bytes=received.size_bytes,
            sha256=received.sha256,
            # The ingestion worker indexes queued documents in upload order.
            status=DocumentStatus.QUEUED.value,
        )
        document_repository.add(session, document)
        session.commit()
    except BaseException:
        session.rollback()
        _delete_stored_file_quietly(storage, storage_key)
        raise
    return document


def open_document_file(
    session: Session, storage: DocumentStorage, user: User, document_id: uuid.UUID
) -> tuple[Document, BinaryIO]:
    document = get_document(session, user, document_id)
    if document.status == DocumentStatus.DELETING:
        raise _being_deleted()
    try:
        handle = storage.open(document.storage_key)
    except FileNotFoundError:
        logger.error("Stored file missing for document %s", document.id)
        raise AppError(
            404, "document_file_missing", "The stored file for this document is missing."
        ) from None
    return document, handle


def retry_document(session: Session, user: User, document_id: uuid.UUID) -> Document:
    """Queue a document whose indexing failed. Queued or processing documents stay as they are."""
    document = document_repository.get_for_member(session, document_id, user.id, lock=True)
    if document is None:
        raise _document_not_found()
    if document.status == DocumentStatus.DELETING:
        raise _being_deleted()
    if document.status == DocumentStatus.READY:
        raise AppError(409, "document_already_indexed", "This document is already indexed.")
    if document.status == DocumentStatus.FAILED:
        document.status = DocumentStatus.QUEUED.value
        document.failure_code = None
        document.failure_message = None
    # Saves the change, if any, and releases the row lock.
    session.commit()
    return document


def delete_document(
    session: Session, storage: DocumentStorage, user: User, document_id: uuid.UUID
) -> None:
    document = document_repository.get_for_member(session, document_id, user.id, lock=True)
    if document is None:
        raise _document_not_found()
    # Marked first, so a failure part-way leaves a visible "deleting" document to retry.
    document.status = DocumentStatus.DELETING.value
    session.commit()
    try:
        storage.delete(document.storage_key)
    except OSError:
        logger.exception("Could not delete the stored file of document %s", document.id)
        raise AppError(
            500,
            "document_delete_failed",
            "The document couldn't be deleted completely. Try deleting it again.",
        ) from None
    document_repository.delete_by_id(session, document.id)
    session.commit()


def _delete_stored_file_quietly(storage: DocumentStorage, storage_key: str) -> None:
    try:
        storage.delete(storage_key)
    except OSError:
        logger.exception("Could not remove an unsaved upload's stored file")


def _document_not_found() -> AppError:
    return AppError(
        404, "document_not_found", "This document doesn't exist, or you don't have access to it."
    )


def _being_deleted() -> AppError:
    return AppError(409, "document_being_deleted", "This document is being deleted.")
