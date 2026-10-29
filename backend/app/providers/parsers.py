"""Text extraction from stored PDF, Word (.docx), and plain-text files (Phase 3, D-35).

Each parser returns blocks of raw text with their location: one per PDF page, one per Word
section (a heading and what follows it), or one for a whole text file. Every failure becomes an
`IndexingError` with a safe message; nothing here logs or returns document text.
"""

import time
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import BinaryIO, Protocol

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PasswordType, PdfReader
from pypdf.errors import DependencyError

from app.domain.documents import DOCX, PDF, TXT
from app.domain.indexing import IndexingError, IndexingFailure, TextBlock

# The XML parts of a Word file are parsed into memory, which takes several times their size.
DOCX_MAX_XML_BYTES = 64 * 1024 * 1024
_DOCX_XML_SUFFIXES = (".xml", ".rels")
_HEADING_STYLE_PREFIXES = ("Heading", "Title")
_TABLE_CELL_SEPARATOR = " | "


@dataclass(frozen=True)
class ParseLimits:
    max_pages: int
    max_characters: int
    # Checked between pages and paragraphs, so one slow page can run past it.
    timeout_seconds: float


class Parser(Protocol):
    def extract(self, file: BinaryIO) -> list[TextBlock]: ...


class _Budget:
    """Tracks the time and amount of text a parser has used against the limits."""

    def __init__(self, limits: ParseLimits) -> None:
        self._deadline = time.perf_counter() + limits.timeout_seconds
        self._characters_left = limits.max_characters

    def check_time(self) -> None:
        if time.perf_counter() >= self._deadline:
            raise IndexingError(IndexingFailure.PARSE_TIMEOUT)

    def take(self, text: str) -> str:
        self._characters_left -= len(text)
        if self._characters_left < 0:
            raise IndexingError(IndexingFailure.TOO_MUCH_TEXT)
        return text


class PdfParser:
    """One block per page, numbered from 1. Pages without a text layer give empty blocks."""

    def __init__(self, limits: ParseLimits) -> None:
        self._limits = limits

    def extract(self, file: BinaryIO) -> list[TextBlock]:
        budget = _Budget(self._limits)
        return _unreadable_on_error(lambda: self._extract(file, budget))

    def _extract(self, file: BinaryIO, budget: _Budget) -> list[TextBlock]:
        reader = PdfReader(file)
        if reader.is_encrypted:
            _decrypt_without_password(reader)
        if len(reader.pages) > self._limits.max_pages:
            raise IndexingError(IndexingFailure.TOO_MANY_PAGES)
        blocks: list[TextBlock] = []
        for number, page in enumerate(reader.pages, start=1):
            budget.check_time()
            blocks.append(TextBlock(budget.take(page.extract_text()), page_number=number))
        return blocks


class DocxParser:
    """One block per section: the text before the first heading, then each heading onwards.

    Covers the main body's paragraphs and tables. Headers, footers, footnotes, comments, text
    boxes, and content controls are not read.
    """

    def __init__(self, limits: ParseLimits) -> None:
        self._limits = limits

    def extract(self, file: BinaryIO) -> list[TextBlock]:
        budget = _Budget(self._limits)
        return _unreadable_on_error(lambda: self._extract(file, budget))

    def _extract(self, file: BinaryIO, budget: _Budget) -> list[TextBlock]:
        _check_docx_xml_size(file)
        document = docx.Document(file)
        blocks: list[TextBlock] = []
        section: str | None = None
        paragraphs: list[str] = []
        for item in document.iter_inner_content():
            budget.check_time()
            if isinstance(item, Paragraph):
                text = budget.take(item.text)
                if _is_heading(item) and text.strip():
                    blocks.append(TextBlock("\n\n".join(paragraphs), section=section))
                    section, paragraphs = text, []
                paragraphs.append(text)
            else:
                paragraphs.append("\n".join(budget.take(row) for row in _table_rows(item)))
        blocks.append(TextBlock("\n\n".join(paragraphs), section=section))
        return blocks


class TextParser:
    """The whole file as one block. Uploads were already checked to be UTF-8."""

    def __init__(self, limits: ParseLimits) -> None:
        self._limits = limits

    def extract(self, file: BinaryIO) -> list[TextBlock]:
        budget = _Budget(self._limits)
        # UTF-8 takes at most 4 bytes per character, so a longer file has too many characters.
        byte_limit = self._limits.max_characters * 4
        data = file.read(byte_limit + 1)
        if len(data) > byte_limit:
            raise IndexingError(IndexingFailure.TOO_MUCH_TEXT)
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise IndexingError(IndexingFailure.DOCUMENT_UNREADABLE) from None
        return [TextBlock(budget.take(text))]


_PARSERS: dict[str, Callable[[ParseLimits], Parser]] = {
    PDF.mime_type: PdfParser,
    DOCX.mime_type: DocxParser,
    TXT.mime_type: TextParser,
}


def parser_for(mime_type: str, limits: ParseLimits) -> Parser:
    """The parser for a stored document's type. Uploads only accept these types."""
    try:
        return _PARSERS[mime_type](limits)
    except KeyError:
        raise IndexingError(IndexingFailure.DOCUMENT_UNREADABLE) from None


def _unreadable_on_error(extract: Callable[[], list[TextBlock]]) -> list[TextBlock]:
    """Damaged files make parsing libraries raise all kinds of errors; report them all alike."""
    try:
        return extract()
    except IndexingError:
        raise
    except Exception as error:
        raise IndexingError(IndexingFailure.DOCUMENT_UNREADABLE) from error


def _decrypt_without_password(reader: PdfReader) -> None:
    # Many PDFs are encrypted only to restrict printing or editing, with an empty password
    # for reading. Anything that needs a real password can't be indexed.
    try:
        result = reader.decrypt("")
    except (DependencyError, NotImplementedError):
        result = PasswordType.NOT_DECRYPTED
    if result == PasswordType.NOT_DECRYPTED:
        raise IndexingError(IndexingFailure.DOCUMENT_ENCRYPTED)


def _check_docx_xml_size(file: BinaryIO) -> None:
    # Python's zipfile stops at each entry's declared size, so declared sizes bound the work.
    with zipfile.ZipFile(file) as archive:
        xml_bytes = sum(
            entry.file_size
            for entry in archive.infolist()
            if entry.filename.lower().endswith(_DOCX_XML_SUFFIXES)
        )
    if xml_bytes > DOCX_MAX_XML_BYTES:
        raise IndexingError(IndexingFailure.TOO_MUCH_TEXT)
    file.seek(0)


def _is_heading(paragraph: Paragraph) -> bool:
    name = paragraph.style.name if paragraph.style is not None else None
    return bool(name) and str(name).startswith(_HEADING_STYLE_PREFIXES)


def _table_rows(table: Table) -> Iterator[str]:
    """Each row as one line, its cells separated by " | ". Nested tables join their cell."""
    for row in table.rows:
        texts: list[str] = []
        previous = None
        for cell in row.cells:
            # A cell spanning several columns appears once for each of them.
            if cell is previous:
                continue
            previous = cell
            parts = [
                item.text if isinstance(item, Paragraph) else " ".join(_table_rows(item))
                for item in cell.iter_inner_content()
            ]
            text = " ".join(part for part in parts if part.strip())
            if text:
                texts.append(text)
        if texts:
            yield _TABLE_CELL_SEPARATOR.join(texts)
