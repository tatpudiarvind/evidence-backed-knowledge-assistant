"""Indexing rules (Phase 3): failure codes, text normalization, and chunking.

A document is split into blocks that each come from one place, such as a PDF page or a Word
section. Chunks never cross blocks, so every chunk can be cited with a single location.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

# Vectors from the embedding model (D-34). The database column has this size, so a model with
# another size needs a new migration and every document indexed again.
EMBEDDING_DIMENSION = 384
MAX_SECTION_LENGTH = 300
MAX_FAILURE_MESSAGE_LENGTH = 500


class IndexingFailure(StrEnum):
    NO_TEXT_FOUND = "no_text_found"
    TOO_MANY_PAGES = "too_many_pages"
    TOO_MUCH_TEXT = "too_much_text"
    PARSE_TIMEOUT = "parse_timeout"
    DOCUMENT_UNREADABLE = "document_unreadable"
    DOCUMENT_ENCRYPTED = "document_encrypted"
    FILE_MISSING = "file_missing"
    EMBEDDING_UNAVAILABLE = "embedding_unavailable"
    EMBEDDING_FAILED = "embedding_failed"
    INGESTION_FAILED = "ingestion_failed"


# Shown to users, so they say what to do next and never include document text or file paths.
FAILURE_MESSAGES: dict[IndexingFailure, str] = {
    IndexingFailure.NO_TEXT_FOUND: (
        "No text was found in this file. Scanned documents need text recognition (OCR), "
        "which isn't supported."
    ),
    IndexingFailure.TOO_MANY_PAGES: "This PDF has more pages than can be indexed.",
    IndexingFailure.TOO_MUCH_TEXT: "This file has more text than can be indexed.",
    IndexingFailure.PARSE_TIMEOUT: "Reading this file took too long, so it was stopped.",
    IndexingFailure.DOCUMENT_UNREADABLE: (
        "This file couldn't be read. It may be damaged; try saving it again and uploading "
        "the new copy."
    ),
    IndexingFailure.DOCUMENT_ENCRYPTED: (
        "This PDF is password-protected. Remove the password, then upload it again."
    ),
    IndexingFailure.FILE_MISSING: (
        "The stored file for this document is missing. Delete the document and upload the "
        "file again."
    ),
    IndexingFailure.EMBEDDING_UNAVAILABLE: (
        "The embedding model isn't available on the server. Download it (see the README), "
        "then retry."
    ),
    IndexingFailure.EMBEDDING_FAILED: "Creating the search index failed. Try again.",
    IndexingFailure.INGESTION_FAILED: "Indexing failed unexpectedly. Try again.",
}


class IndexingError(Exception):
    """An expected indexing failure, with a stable code and a message that is safe to show."""

    def __init__(self, failure: IndexingFailure, message: str | None = None) -> None:
        self.failure = failure
        self.message = (message or FAILURE_MESSAGES[failure])[:MAX_FAILURE_MESSAGE_LENGTH]
        super().__init__(failure.value)


@dataclass(frozen=True)
class TextBlock:
    """Text from one place in a document: a PDF page, a Word section, or a whole text file."""

    text: str
    page_number: int | None = None
    section: str | None = None


@dataclass(frozen=True)
class TextChunk:
    ordinal: int
    text: str
    page_number: int | None
    section: str | None


# Typographic ligatures that PDF text extraction often returns, such as "ﬁ" in "ﬁnance".
_LIGATURES = str.maketrans(
    {
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
        "\ufb05": "st",
        "\ufb06": "st",
    }
)
_LINE_BREAKS = re.compile(r"\r\n?|[\x0b\x0c\x1c-\x1e\x85\u2028\u2029]")
_EXTRA_BLANK_LINES = re.compile(r"\n{3,}")
# Control, invisible formatting (soft hyphens, zero-width and direction marks), and surrogate
# characters. PostgreSQL text can't hold NUL, and lone surrogates can't be stored at all.
_REMOVED_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})
_WHITESPACE = re.compile(r"\s")
# A full stop, question, or exclamation mark (and any closing quotes or brackets) followed by
# whitespace. Chinese and Japanese full-width marks need no following space.
_SENTENCE_END = re.compile(
    r"[.!?][\"'\u2019\u201d)\]]*(?=\s)|[\u3002\uff01\uff1f][\"'\u2019\u201d)\]\u300d\u300f]*"
)


def normalize_text(text: str) -> str:
    """Tidy extracted text for search: one kind of line break and space, no invisible characters.

    Paragraph breaks (blank lines) are kept, because chunking prefers to split there. Words that
    a PDF hyphenated across lines are left as they are.
    """
    text = unicodedata.normalize("NFC", text.translate(_LIGATURES))
    text = _LINE_BREAKS.sub("\n", text)
    kept: list[str] = []
    for char in text:
        if char == "\n":
            kept.append(char)
        elif char.isspace():
            kept.append(" ")
        elif unicodedata.category(char) not in _REMOVED_CATEGORIES:
            kept.append(char)
    lines = (" ".join(line.split()) for line in "".join(kept).split("\n"))
    return _EXTRA_BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def normalize_blocks(blocks: Iterable[TextBlock]) -> list[TextBlock]:
    """Normalize each block's text and section title, dropping blocks left without text."""
    normalized: list[TextBlock] = []
    for block in blocks:
        text = normalize_text(block.text)
        if not text:
            continue
        section = " ".join(normalize_text(block.section).split()) if block.section else ""
        normalized.append(
            TextBlock(text, block.page_number, section[:MAX_SECTION_LENGTH].rstrip() or None)
        )
    return normalized


def split_spans(text: str, size: int, overlap: int) -> list[tuple[int, int]]:
    """Where to cut `text` into pieces of at most `size` characters.

    Each cut prefers, in order: a paragraph break, a line break, the end of a sentence, and a
    space, in the second half of the piece; failing all of those, a word is cut. The next piece
    starts up to `overlap` characters earlier, at the start of a word, so a sentence cut in two
    still appears whole in one of the pieces. With an overlap of at most a quarter of `size`,
    each piece starts at least about a quarter of `size` after the previous one, and ends after
    it. Returns (start, end) offsets without surrounding whitespace.
    """
    if size < 2 or not 0 <= overlap * 4 <= size:
        raise ValueError("chunk size must be at least 2, and overlap at most a quarter of it")
    spans: list[tuple[int, int]] = []
    length = len(text)
    start = _skip_whitespace(text, 0)
    while start < length:
        cut = length if length - start <= size else _cut_point(text, start, start + size)
        end = _trim_end(text, start, cut)
        # A piece starting in the overlap adds nothing if only whitespace follows it there.
        if not spans or end > spans[-1][1]:
            spans.append((start, end))
        if cut == length:
            break
        start = _skip_whitespace(text, _next_start(text, start, cut, overlap))
    return spans


def chunk_blocks(blocks: Iterable[TextBlock], size: int, overlap: int) -> list[TextChunk]:
    """Split every block into chunks, numbered in reading order across the whole document."""
    chunks: list[TextChunk] = []
    for block in blocks:
        for start, end in split_spans(block.text, size, overlap):
            chunks.append(
                TextChunk(len(chunks), block.text[start:end], block.page_number, block.section)
            )
    return chunks


def _cut_point(text: str, start: int, limit: int) -> int:
    earliest = start + (limit - start) // 2
    for separator in ("\n\n", "\n"):
        position = text.rfind(separator, earliest, limit)
        if position != -1:
            return position
    sentence_ends = [
        match.end()
        for match in _SENTENCE_END.finditer(text, earliest, min(limit + 1, len(text)))
        if match.end() <= limit
    ]
    if sentence_ends:
        return sentence_ends[-1]
    position = text.rfind(" ", earliest, limit)
    return position if position != -1 else limit


def _next_start(text: str, start: int, end: int, overlap: int) -> int:
    if overlap == 0:
        return end
    candidate = max(end - overlap, start + 1)
    if text[candidate - 1].isspace():
        return candidate
    # Start at the next word rather than part-way through one; no overlap if there is none.
    match = _WHITESPACE.search(text, candidate, end)
    return match.end() if match else end


def _skip_whitespace(text: str, position: int) -> int:
    while position < len(text) and text[position].isspace():
        position += 1
    return position


def _trim_end(text: str, start: int, end: int) -> int:
    while end > start and text[end - 1].isspace():
        end -= 1
    return end
