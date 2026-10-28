"""Document rules: supported file types, content checks, and safe display names (D-33)."""

import codecs
import unicodedata
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"


@dataclass(frozen=True)
class FileType:
    extension: str
    mime_type: str
    invalid_content_message: str


PDF = FileType(".pdf", "application/pdf", "This file doesn't look like a PDF.")
DOCX = FileType(
    ".docx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "This file doesn't look like a Word (.docx) document.",
)
TXT = FileType(".txt", "text/plain", "Text files must contain UTF-8 encoded text.")
SUPPORTED_FILE_TYPES: dict[str, FileType] = {
    file_type.extension: file_type for file_type in (PDF, DOCX, TXT)
}

MAX_DISPLAY_NAME_LENGTH = 255
FALLBACK_STEM = "document"
# PDF readers accept the "%PDF-" header anywhere in the first 1024 bytes.
PDF_HEADER_WINDOW = 1024
# Read from the ZIP directory alone, without decompressing anything. Parsing (Phase 3) must
# still limit what it decompresses, because a ZIP directory can understate sizes.
DOCX_MAX_ENTRIES = 10_000
DOCX_MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
_TEXT_CHUNK_BYTES = 64 * 1024
# Control, invisible formatting (such as right-to-left overrides), and surrogate characters.
# Whitespace characters among them, such as tabs and line breaks, become spaces instead.
_REMOVED_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})


@dataclass(frozen=True)
class ReceivedFile:
    """An uploaded file, saved to a temporary path and not yet validated."""

    path: Path
    filename: str
    size_bytes: int
    sha256: str

    def discard(self) -> None:
        self.path.unlink(missing_ok=True)


def split_extension(name: str) -> tuple[str, str]:
    stem, dot, extension = name.rpartition(".")
    if not dot:
        return name, ""
    return stem, f".{extension}"


def sanitize_display_name(raw_name: str) -> str:
    """Make an uploaded file name safe to show: no folders, control, or invisible characters."""
    name = raw_name.replace("\\", "/").rsplit("/", 1)[-1]
    name = unicodedata.normalize("NFC", name)
    kept: list[str] = []
    for char in name:
        if char.isspace():
            kept.append(" ")
        elif unicodedata.category(char) not in _REMOVED_CATEGORIES:
            kept.append(char)
    name = " ".join("".join(kept).split())
    stem, extension = split_extension(name)
    if not stem.strip(" ."):
        stem = FALLBACK_STEM
    room_for_stem = MAX_DISPLAY_NAME_LENGTH - len(extension)
    if room_for_stem < len(FALLBACK_STEM):
        return (stem + extension)[:MAX_DISPLAY_NAME_LENGTH]
    return stem[:room_for_stem].rstrip() + extension


def file_type_for_name(name: str) -> FileType | None:
    return SUPPORTED_FILE_TYPES.get(split_extension(name)[1].lower())


def content_matches(path: Path, file_type: FileType) -> bool:
    """Check the file's actual bytes, rather than trusting its name or the browser's MIME type."""
    if file_type == PDF:
        return _looks_like_pdf(path)
    if file_type == DOCX:
        return _looks_like_docx(path)
    return _is_utf8_text(path)


def _looks_like_pdf(path: Path) -> bool:
    with path.open("rb") as handle:
        return b"%PDF-" in handle.read(PDF_HEADER_WINDOW)


def _looks_like_docx(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, EOFError, ValueError):
        return False
    if len(entries) > DOCX_MAX_ENTRIES:
        return False
    if sum(entry.file_size for entry in entries) > DOCX_MAX_UNCOMPRESSED_BYTES:
        return False
    names = {entry.filename for entry in entries}
    return "[Content_Types].xml" in names and "word/document.xml" in names


def _is_utf8_text(path: Path) -> bool:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_TEXT_CHUNK_BYTES):
                if b"\x00" in chunk:
                    return False
                decoder.decode(chunk)
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return False
    return True
