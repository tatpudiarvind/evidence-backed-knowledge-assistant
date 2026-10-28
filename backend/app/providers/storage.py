"""Where uploaded files are kept. Only random, server-generated keys become file names."""

import os
import re
import secrets
import tempfile
from pathlib import Path
from typing import BinaryIO, Protocol

_STORAGE_KEY = re.compile(r"[0-9a-f]{32}")


def new_storage_key() -> str:
    return secrets.token_hex(16)


class DocumentStorage(Protocol):
    def create_temp_file(self) -> tuple[Path, BinaryIO]: ...

    def save(self, key: str, source: Path) -> None: ...

    def open(self, key: str) -> BinaryIO: ...

    def delete(self, key: str) -> None: ...


class LocalDocumentStorage:
    """Keeps stored files in `documents/` and uploads still being received in `tmp/`."""

    def __init__(self, root: Path) -> None:
        self._documents_dir = root / "documents"
        self._temp_dir = root / "tmp"

    def create_temp_file(self) -> tuple[Path, BinaryIO]:
        # On the same disk as `documents/`, so saving is a rename rather than a copy.
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix="upload-", suffix=".part", dir=self._temp_dir)
        return Path(name), os.fdopen(descriptor, "wb")

    def save(self, key: str, source: Path) -> None:
        target = self._path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)

    def open(self, key: str) -> BinaryIO:
        return self._path_for(key).open("rb")

    def delete(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)

    def _path_for(self, key: str) -> Path:
        # A strict key format rules out path traversal, whatever a caller passes in.
        if not _STORAGE_KEY.fullmatch(key):
            raise ValueError("Storage keys are 32 lowercase hexadecimal characters.")
        return self._documents_dir / key
