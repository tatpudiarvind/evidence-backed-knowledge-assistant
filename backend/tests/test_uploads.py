"""The streaming multipart reader, tested through a minimal app. No database needed."""

import hashlib
from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.types import Message

from app.api.v1.uploads import MULTIPART_OVERHEAD_BYTES, receive_single_file
from app.core.errors import AppError, register_error_handlers
from app.providers.storage import LocalDocumentStorage
from tests.support import error_code

MAX_FILE_BYTES = 1024
UPLOAD_TIMEOUT_SECONDS = 30
BOUNDARY = "test-boundary-7MA4YWxk"
MULTIPART_HEADERS = {"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    storage = LocalDocumentStorage(tmp_path)
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/upload")
    async def upload(request: Request) -> dict[str, object]:
        received = await receive_single_file(
            request, storage, MAX_FILE_BYTES, timeout_seconds=UPLOAD_TIMEOUT_SECONDS
        )
        try:
            return {
                "filename": received.filename,
                "size_bytes": received.size_bytes,
                "sha256": received.sha256,
                "content": received.path.read_bytes().decode("latin-1"),
            }
        finally:
            received.discard()

    return TestClient(app)


@pytest.fixture
def leftover_files(tmp_path: Path) -> Iterator[list[Path]]:
    """After the test, lists any temporary upload files that were left behind."""
    leftovers: list[Path] = []
    yield leftovers
    temp_dir = tmp_path / "tmp"
    leftovers.extend(temp_dir.iterdir() if temp_dir.exists() else [])
    assert leftovers == [], "temporary upload files were left behind"


def _raw_body(*parts: str, closed: bool = True) -> bytes:
    body = "".join(f"--{BOUNDARY}\r\n{part}\r\n" for part in parts)
    return (body + (f"--{BOUNDARY}--\r\n" if closed else "")).encode()


def _file_part(filename: str, content: str) -> str:
    return (
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n{content}"
    )


def test_receives_the_file_with_size_and_hash(client, leftover_files) -> None:
    content = b"Synthetic notes for testing.\n"

    response = client.post("/upload", files={"file": ("notes.txt", content, "text/plain")})

    assert response.status_code == 200
    assert response.json() == {
        "filename": "notes.txt",
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "content": content.decode(),
    }


def test_keeps_non_ascii_file_names(client, leftover_files) -> None:
    response = client.post(
        "/upload", files={"file": ("R\u00e9sum\u00e9 \u2013 2024.txt", b"x", "text/plain")}
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "R\u00e9sum\u00e9 \u2013 2024.txt"


def test_ignores_other_form_fields(client, leftover_files) -> None:
    response = client.post(
        "/upload",
        data={"note": "ignored"},
        files={"file": ("notes.txt", b"kept", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["content"] == "kept"


def test_file_exactly_at_the_limit_is_accepted(client, leftover_files) -> None:
    response = client.post(
        "/upload", files={"file": ("max.txt", b"x" * MAX_FILE_BYTES, "text/plain")}
    )

    assert response.status_code == 200
    assert response.json()["size_bytes"] == MAX_FILE_BYTES


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"json": {"file": "not a file"}},
        {"content": b"x", "headers": {"Content-Type": "multipart/form-data"}},
        {"content": b"x", "headers": {"Content-Type": "text/plain"}},
    ],
)
def test_requires_multipart_with_a_boundary(client, leftover_files, request_kwargs) -> None:
    response = client.post("/upload", **request_kwargs)

    assert response.status_code == 415
    assert error_code(response) == "multipart_required"


def test_rejects_a_file_over_the_limit_while_reading(client, leftover_files) -> None:
    response = client.post(
        "/upload", files={"file": ("big.txt", b"x" * (MAX_FILE_BYTES + 1), "text/plain")}
    )

    assert response.status_code == 413
    assert error_code(response) == "file_too_large"


def test_rejects_a_declared_oversized_body_before_reading(client, leftover_files) -> None:
    oversized = b"x" * (MAX_FILE_BYTES + MULTIPART_OVERHEAD_BYTES + 1)

    response = client.post("/upload", files={"file": ("big.txt", oversized, "text/plain")})

    assert response.status_code == 413
    assert error_code(response) == "file_too_large"


def test_limits_the_whole_body_even_without_a_declared_length(client, leftover_files) -> None:
    padding = "p" * (MAX_FILE_BYTES + MULTIPART_OVERHEAD_BYTES)
    body = _raw_body('Content-Disposition: form-data; name="padding"\r\n\r\n' + padding)

    def chunks() -> Iterator[bytes]:
        for start in range(0, len(body), 4096):
            yield body[start : start + 4096]

    response = client.post("/upload", content=chunks(), headers=MULTIPART_HEADERS)

    assert response.status_code == 413
    assert error_code(response) == "file_too_large"


def test_rejects_more_than_one_file(client, leftover_files) -> None:
    response = client.post(
        "/upload",
        files=[
            ("file", ("a.txt", b"first", "text/plain")),
            ("file", ("b.txt", b"second", "text/plain")),
        ],
    )

    assert response.status_code == 422
    assert error_code(response) == "too_many_files"


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"files": {"attachment": ("a.txt", b"wrong field", "text/plain")}},
        {"data": {"file": "text, not a file"}, "files": {"other": ("a.txt", b"x", "text/plain")}},
        {"files": {"file": ("", b"no file name", "text/plain")}},
    ],
)
def test_requires_a_file_in_the_file_field(client, leftover_files, request_kwargs) -> None:
    response = client.post("/upload", **request_kwargs)

    assert response.status_code == 422
    assert error_code(response) == "file_missing"


def test_rejects_an_empty_file(client, leftover_files) -> None:
    response = client.post("/upload", files={"file": ("empty.txt", b"", "text/plain")})

    assert response.status_code == 422
    assert error_code(response) == "file_empty"


def test_rejects_a_truncated_upload(client, leftover_files) -> None:
    body = _raw_body(_file_part("cut.txt", "partial content"), closed=False)

    response = client.post("/upload", content=body, headers=MULTIPART_HEADERS)

    assert response.status_code == 422
    assert error_code(response) == "invalid_multipart"


def test_rejects_malformed_multipart(client, leftover_files) -> None:
    response = client.post(
        "/upload", content=b"this is not multipart at all", headers=MULTIPART_HEADERS
    )

    assert response.status_code == 422
    assert error_code(response) == "invalid_multipart"


def test_rejects_too_many_parts(client, leftover_files) -> None:
    response = client.post(
        "/upload",
        data={"a": "1", "b": "2", "c": "3", "d": "4"},
        files={"file": ("notes.txt", b"x", "text/plain")},
    )

    assert response.status_code == 422
    assert error_code(response) == "invalid_multipart"


def test_gives_up_on_an_upload_that_stops_arriving(tmp_path, leftover_files) -> None:
    # The test client sends whole bodies at once, so this calls the reader directly with a
    # client that sends the start of a file and then nothing more.
    storage = LocalDocumentStorage(tmp_path)
    start = _raw_body(_file_part("slow.txt", "The start of a file, then nothing."), closed=False)
    messages: list[Message] = [{"type": "http.request", "body": start, "more_body": True}]
    files_while_waiting: list[Path] = []

    async def receive() -> Message:
        if messages:
            return messages.pop(0)
        files_while_waiting.extend((tmp_path / "tmp").iterdir())
        await anyio.sleep_forever()
        raise AssertionError("unreachable")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/upload",
        "headers": [(b"content-type", MULTIPART_HEADERS["Content-Type"].encode())],
    }

    async def upload() -> None:
        request = Request(scope, receive)
        # A backstop, so the test fails rather than hangs if the reader stops timing out.
        with anyio.fail_after(10):
            await receive_single_file(request, storage, MAX_FILE_BYTES, timeout_seconds=0.5)

    with pytest.raises(AppError) as raised:
        anyio.run(upload)

    assert raised.value.status_code == 408
    assert raised.value.code == "upload_timed_out"
    assert raised.value.headers == {"Connection": "close"}
    # The partly written file existed while the reader waited; `leftover_files` checks that
    # it was removed.
    assert len(files_while_waiting) == 1
