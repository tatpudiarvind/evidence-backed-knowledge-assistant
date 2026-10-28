"""Receives one uploaded file as a stream, enforcing limits while reading (D-33).

Starlette's form parser limits only non-file fields, so this reads the multipart body itself:
the size limit is checked as bytes arrive, and the file is hashed and written to a temporary
file at the same time. Nothing is decompressed or parsed beyond the multipart framing.
"""

import hashlib
from pathlib import Path
from typing import BinaryIO

from fastapi import Request
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.core.errors import AppError
from app.domain.documents import ReceivedFile
from app.providers.storage import DocumentStorage

FILE_FIELD = "file"
# Room for the multipart boundaries and part headers around the file itself.
MULTIPART_OVERHEAD_BYTES = 64 * 1024
# Browsers send one part for the file; a few more are tolerated and ignored.
MAX_PARTS = 4


def _invalid_multipart() -> AppError:
    return AppError(422, "invalid_multipart", "The upload couldn't be read. Try again.")


def _file_too_large(max_file_bytes: int) -> AppError:
    limit_mib = max_file_bytes / (1024 * 1024)
    return AppError(413, "file_too_large", f"Files can be at most {limit_mib:g} MiB.")


class _SingleFileCollector:
    """Multipart parser callbacks that keep the part named "file" and skip any others."""

    def __init__(self, storage: DocumentStorage, max_file_bytes: int) -> None:
        self._storage = storage
        self._max_file_bytes = max_file_bytes
        self._parts = 0
        self._headers: dict[bytes, bytes] = {}
        self._header_field = bytearray()
        self._header_value = bytearray()
        self._sink: BinaryIO | None = None
        self._sha256 = hashlib.sha256()
        self.path: Path | None = None
        self.filename = ""
        self.size_bytes = 0
        self.finished = False

    def on_part_begin(self) -> None:
        self._parts += 1
        if self._parts > MAX_PARTS:
            raise _invalid_multipart()
        self._headers = {}

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_field += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def on_header_end(self) -> None:
        self._headers[bytes(self._header_field).lower()] = bytes(self._header_value)
        self._header_field.clear()
        self._header_value.clear()

    def on_headers_finished(self) -> None:
        _, options = parse_options_header(self._headers.get(b"content-disposition"))
        filename = options.get(b"filename")
        if options.get(b"name") != FILE_FIELD.encode() or not filename:
            return
        if self.path is not None:
            raise AppError(422, "too_many_files", "Upload one file per request.")
        # Browsers send the file name as raw UTF-8.
        self.filename = filename.decode("utf-8", errors="replace")
        self.path, self._sink = self._storage.create_temp_file()

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._sink is None:
            return
        chunk = data[start:end]
        self.size_bytes += len(chunk)
        if self.size_bytes > self._max_file_bytes:
            raise _file_too_large(self._max_file_bytes)
        self._sha256.update(chunk)
        self._sink.write(chunk)

    def on_part_end(self) -> None:
        if self._sink is not None:
            self._sink.close()
            self._sink = None

    def on_end(self) -> None:
        self.finished = True

    def result(self) -> ReceivedFile:
        if not self.finished:
            raise _invalid_multipart()
        if self.path is None:
            raise AppError(
                422, "file_missing", f'Send the file in a form field named "{FILE_FIELD}".'
            )
        if self.size_bytes == 0:
            raise AppError(422, "file_empty", "The file is empty.")
        return ReceivedFile(self.path, self.filename, self.size_bytes, self._sha256.hexdigest())

    def discard(self) -> None:
        if self._sink is not None:
            self._sink.close()
            self._sink = None
        if self.path is not None:
            self.path.unlink(missing_ok=True)


async def receive_single_file(
    request: Request, storage: DocumentStorage, max_file_bytes: int
) -> ReceivedFile:
    """Save the request's one file to a temporary file. The caller must discard it when done."""
    content_type, options = parse_options_header(request.headers.get("content-type"))
    boundary = options.get(b"boundary")
    if content_type.lower() != b"multipart/form-data" or not boundary:
        raise AppError(
            415,
            "multipart_required",
            f'Upload the file as multipart/form-data, in a field named "{FILE_FIELD}".',
        )
    max_body_bytes = max_file_bytes + MULTIPART_OVERHEAD_BYTES
    declared_length = request.headers.get("content-length", "")
    if declared_length.isdigit() and int(declared_length) > max_body_bytes:
        raise _file_too_large(max_file_bytes)

    collector = _SingleFileCollector(storage, max_file_bytes)
    try:
        await _read_body(request, collector, boundary, max_body_bytes, max_file_bytes)
        return collector.result()
    except BaseException:
        collector.discard()
        raise


async def _read_body(
    request: Request,
    collector: _SingleFileCollector,
    boundary: bytes,
    max_body_bytes: int,
    max_file_bytes: int,
) -> None:
    try:
        parser = MultipartParser(
            boundary,
            callbacks={
                "on_part_begin": collector.on_part_begin,
                "on_part_data": collector.on_part_data,
                "on_part_end": collector.on_part_end,
                "on_header_field": collector.on_header_field,
                "on_header_value": collector.on_header_value,
                "on_header_end": collector.on_header_end,
                "on_headers_finished": collector.on_headers_finished,
                "on_end": collector.on_end,
            },
        )
        body_bytes = 0
        async for chunk in request.stream():
            body_bytes += len(chunk)
            if body_bytes > max_body_bytes:
                raise _file_too_large(max_file_bytes)
            # Hashing and disk writes happen in the callbacks, so keep them off the event loop.
            await run_in_threadpool(parser.write, chunk)
    except FormParserError:
        raise _invalid_multipart() from None
    except ClientDisconnect:
        raise AppError(
            400, "upload_interrupted", "The upload was interrupted. Try again."
        ) from None
