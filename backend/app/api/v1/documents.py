import uuid
from collections.abc import Iterator
from typing import BinaryIO
from urllib.parse import quote

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, DbSession, IngestionWorkerDep, SettingsDep, StorageDep
from app.api.v1.schemas import DocumentList, DocumentOut
from app.api.v1.uploads import FILE_FIELD, receive_single_file
from app.services import documents as document_service

router = APIRouter(tags=["documents"])

DOWNLOAD_CHUNK_BYTES = 64 * 1024
_UPLOAD_REQUEST_BODY = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": [FILE_FIELD],
                "properties": {FILE_FIELD: {"type": "string", "format": "binary"}},
            }
        }
    },
}


@router.post(
    "/workspaces/{workspace_id}/documents",
    status_code=202,
    summary="Upload one PDF, DOCX, or TXT file",
    description=(
        "Stores the file and queues it for indexing. Send one file per request, in a "
        "multipart/form-data field named `file`."
    ),
    openapi_extra={"requestBody": _UPLOAD_REQUEST_BODY},
)
async def upload_document(
    workspace_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    storage: StorageDep,
    settings: SettingsDep,
    worker: IngestionWorkerDep,
) -> DocumentOut:
    # Membership is checked before the body is read.
    await run_in_threadpool(document_service.check_can_upload, session, user, workspace_id)
    received = await receive_single_file(request, storage, settings.max_upload_bytes)
    try:
        document = await run_in_threadpool(
            document_service.store_upload, session, storage, settings, user, workspace_id, received
        )
    finally:
        received.discard()
    response = DocumentOut.model_validate(document)
    worker.notify()
    return response


@router.get("/workspaces/{workspace_id}/documents", summary="List a workspace's documents")
def list_documents(workspace_id: uuid.UUID, user: CurrentUser, session: DbSession) -> DocumentList:
    documents = document_service.list_documents(session, user, workspace_id)
    return DocumentList(items=[DocumentOut.model_validate(document) for document in documents])


@router.get("/documents/{document_id}", summary="Get a document's details and status")
def get_document(document_id: uuid.UUID, user: CurrentUser, session: DbSession) -> DocumentOut:
    return DocumentOut.model_validate(document_service.get_document(session, user, document_id))


@router.get(
    "/documents/{document_id}/file",
    summary="Download the original file",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
def download_document(
    document_id: uuid.UUID, user: CurrentUser, session: DbSession, storage: StorageDep
) -> StreamingResponse:
    document, handle = document_service.open_document_file(session, storage, user, document_id)
    return StreamingResponse(
        _read_chunks(handle),
        media_type=document.mime_type,
        headers={
            "Content-Disposition": _attachment(document.display_name),
            "Content-Length": str(document.size_bytes),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/documents/{document_id}/retry",
    status_code=202,
    summary="Index a failed document again",
    description=(
        "Queues a document whose indexing failed. A queued or processing document is returned "
        "unchanged; an indexed one is a conflict."
    ),
)
def retry_document(
    document_id: uuid.UUID, user: CurrentUser, session: DbSession, worker: IngestionWorkerDep
) -> DocumentOut:
    document = document_service.retry_document(session, user, document_id)
    response = DocumentOut.model_validate(document)
    worker.notify()
    return response


@router.delete(
    "/documents/{document_id}",
    status_code=204,
    summary="Delete a document and its stored file",
    response_class=Response,
)
def delete_document(
    document_id: uuid.UUID, user: CurrentUser, session: DbSession, storage: StorageDep
) -> Response:
    document_service.delete_document(session, storage, user, document_id)
    return Response(status_code=204)


def _read_chunks(handle: BinaryIO) -> Iterator[bytes]:
    with handle:
        while chunk := handle.read(DOWNLOAD_CHUNK_BYTES):
            yield chunk


def _attachment(display_name: str) -> str:
    """Always a download, never shown inline. The name is ASCII-safe plus an RFC 6266 UTF-8 copy."""
    fallback = "".join(
        char if char.isascii() and char.isprintable() and char not in '"\\' else "_"
        for char in display_name
    )
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(display_name, safe='')}"
