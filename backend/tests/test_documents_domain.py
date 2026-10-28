from pathlib import Path

import pytest

from app.domain.documents import (
    DOCX,
    PDF,
    TXT,
    content_matches,
    file_type_for_name,
    sanitize_display_name,
)
from tests.support import docx_bytes, pdf_bytes, zip_bytes


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("../../etc/passwd.txt", "passwd.txt"),
        ("C:\\Users\\someone\\notes.txt", "notes.txt"),
        ("  spaced \t  out   name .txt", "spaced out name.txt"),
        ("evil\u202egnp.txt", "evilgnp.txt"),
        ("line\r\nbreak\x00.txt", "line break.txt"),
        ("cafe\u0301.txt", "caf\u00e9.txt"),
        (".txt", "document.txt"),
        ("...txt", "document.txt"),
        ("", "document"),
        ("no_extension", "no_extension"),
    ],
)
def test_display_names_are_sanitized(raw: str, expected: str) -> None:
    assert sanitize_display_name(raw) == expected


def test_long_display_names_keep_their_extension() -> None:
    name = sanitize_display_name("a" * 400 + ".docx")

    assert len(name) == 255
    assert name.endswith(".docx")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a.pdf", PDF),
        ("a.PDF", PDF),
        ("a.docx", DOCX),
        ("a.txt", TXT),
        ("a.doc", None),
        ("a.pdf.exe", None),
        ("pdf", None),
    ],
)
def test_file_type_comes_from_the_extension(name: str, expected: object) -> None:
    assert file_type_for_name(name) == expected


def _write(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "upload.part"
    path.write_bytes(content)
    return path


def test_pdf_signature_is_checked(tmp_path: Path) -> None:
    assert content_matches(_write(tmp_path, pdf_bytes()), PDF)
    assert content_matches(_write(tmp_path, b"\xef\xbb\xbf" + pdf_bytes()), PDF)
    assert not content_matches(_write(tmp_path, b"MZ\x90\x00 not a pdf"), PDF)
    assert not content_matches(_write(tmp_path, b" " * 1024 + pdf_bytes()), PDF)


def test_docx_must_be_a_word_zip_package(tmp_path: Path) -> None:
    assert content_matches(_write(tmp_path, docx_bytes()), DOCX)
    assert not content_matches(_write(tmp_path, zip_bytes({"[Content_Types].xml": ""})), DOCX)
    assert not content_matches(_write(tmp_path, pdf_bytes()), DOCX)
    assert not content_matches(_write(tmp_path, b"PK\x03\x04 truncated"), DOCX)


def test_text_must_be_utf8_without_nul_bytes(tmp_path: Path) -> None:
    assert content_matches(_write(tmp_path, "Plain text, caf\u00e9.\n".encode()), TXT)
    assert content_matches(_write(tmp_path, b"\xef\xbb\xbfWith a byte order mark"), TXT)
    assert not content_matches(_write(tmp_path, b"Latin-1 caf\xe9"), TXT)
    assert not content_matches(_write(tmp_path, b"binary\x00data"), TXT)
    assert not content_matches(_write(tmp_path, b"cut off \xe2\x82"), TXT)


def test_text_characters_split_across_read_chunks_are_accepted(tmp_path: Path) -> None:
    # The euro sign's three bytes straddle the 64 KiB read boundary.
    content = b"a" * (64 * 1024 - 1) + "\u20ac".encode() + b"end"

    assert content_matches(_write(tmp_path, content), TXT)
