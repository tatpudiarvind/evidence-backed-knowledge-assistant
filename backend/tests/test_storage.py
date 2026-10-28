from pathlib import Path

import pytest

from app.providers.storage import LocalDocumentStorage, new_storage_key


def test_files_move_from_temporary_to_permanent_storage(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    temp_path, sink = storage.create_temp_file()
    with sink:
        sink.write(b"stored bytes")
    key = new_storage_key()

    storage.save(key, temp_path)

    assert temp_path.parent == tmp_path / "tmp"
    assert not temp_path.exists()
    with storage.open(key) as handle:
        assert handle.read() == b"stored bytes"
    assert (tmp_path / "documents" / key).is_file()


def test_delete_removes_the_file_and_tolerates_missing_files(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    temp_path, sink = storage.create_temp_file()
    sink.close()
    key = new_storage_key()
    storage.save(key, temp_path)

    storage.delete(key)
    storage.delete(key)

    assert not (tmp_path / "documents" / key).exists()


def test_storage_keys_are_random_hex() -> None:
    keys = {new_storage_key() for _ in range(100)}

    assert len(keys) == 100
    assert all(len(key) == 32 and int(key, 16) >= 0 for key in keys)


@pytest.mark.parametrize(
    "key",
    ["../" + "a" * 29, "A" * 32, "a" * 31, "a" * 33, "..", "", "a" * 31 + "/"],
)
def test_keys_that_are_not_server_generated_are_refused(tmp_path: Path, key: str) -> None:
    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.open(key)
    with pytest.raises(ValueError):
        storage.delete(key)
