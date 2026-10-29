"""The evaluation corpus: synthetic documents kept as plain-text sources.

Each source becomes the file a user would upload: `name.pdf.md` a PDF, `name.docx.md` a Word
document, and `name.txt` a text file as it is. Text sources are easy to review and compare.
The files are built from them on every run, and results record the sources' hashes: Word
documents carry the time they were built, so their bytes differ from run to run, but their text
doesn't.

`.pdf.md`: a line of `---` starts a new page. Lines starting with `#` are headings, and lines
starting with `- ` list items; other lines join into paragraphs. Each paragraph and list item
is wrapped at 80 characters, and blank lines separate them.

`.docx.md`: lines starting with `#` or `##` are headings of level 1 or 2, lines starting with
`|` are table rows (a row of dashes is skipped), and other lines join into paragraphs.
"""

import hashlib
import io
import re
import textwrap
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.domain.documents import DOCX, PDF, TXT
from app.domain.indexing import normalize_blocks
from app.evaluation.files import PDF_MAX_LINES_PER_PAGE, Heading, docx_bytes, pdf_bytes
from app.providers.parsers import ParseLimits, parser_for

PDF_LINE_WIDTH = 80
_PAGE_BREAK = "---"
_TABLE_SEPARATOR_ROW = re.compile(r"\|?(\s*:?-{3,}:?\s*\|)*\s*:?-{3,}:?\s*\|?")

DocxItem = str | Heading | list[list[str]]


class CorpusError(ValueError):
    """A corpus source that can't be built."""


@dataclass(frozen=True)
class CorpusDocument:
    # The name it is uploaded with, such as "handbook.pdf".
    name: str
    mime_type: str
    content: bytes
    source_name: str
    source_sha256: str


@dataclass(frozen=True)
class CorpusBlock:
    """The text the app reads from one place in a corpus document: a page or a section."""

    document: str
    page_number: int | None
    section: str | None
    text: str

    def describe(self) -> str:
        page = f" page {self.page_number}" if self.page_number is not None else ""
        section = f' section "{self.section}"' if self.section else ""
        return f"{self.document}{page}{section}"


def read_blocks(documents: Iterable[CorpusDocument], settings: Settings) -> list[CorpusBlock]:
    """The corpus as the app reads it: parsed and normalized the way uploads are indexed."""
    limits = ParseLimits(
        max_pages=settings.max_document_pages,
        max_characters=settings.max_document_characters,
        timeout_seconds=settings.parse_timeout_seconds,
    )
    blocks: list[CorpusBlock] = []
    for document in documents:
        parsed = parser_for(document.mime_type, limits).extract(io.BytesIO(document.content))
        blocks.extend(
            CorpusBlock(document.name, block.page_number, block.section, block.text)
            for block in normalize_blocks(parsed)
        )
    return blocks


def load_corpus(directory: Path) -> list[CorpusDocument]:
    """Build every source in the folder, in name order."""
    sources = sorted(path for path in directory.iterdir() if path.is_file())
    if not sources:
        raise CorpusError(f"There are no corpus sources in {directory.name}.")
    return [build_document(path.name, path.read_bytes()) for path in sources]


def build_document(source_name: str, data: bytes) -> CorpusDocument:
    try:
        source = data.decode("ascii")
    except UnicodeDecodeError:
        raise CorpusError(f"{source_name}: corpus sources must be ASCII text.") from None
    # Line endings depend on how the files were checked out, so they don't count.
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    digest = hashlib.sha256(source.encode()).hexdigest()
    if source_name.endswith(".pdf.md"):
        content = pdf_bytes(*pdf_pages(source, source_name))
        return CorpusDocument(source_name[:-3], PDF.mime_type, content, source_name, digest)
    if source_name.endswith(".docx.md"):
        content = docx_bytes(*docx_content(source, source_name))
        return CorpusDocument(source_name[:-3], DOCX.mime_type, content, source_name, digest)
    if source_name.endswith(".txt"):
        return CorpusDocument(source_name, TXT.mime_type, source.encode(), source_name, digest)
    raise CorpusError(f"{source_name}: corpus sources end in .pdf.md, .docx.md, or .txt.")


def corpus_sha256(documents: Iterable[CorpusDocument]) -> str:
    """One hash for the whole corpus, from each source's name and hash."""
    listing = "".join(
        f"{document.source_name} {document.source_sha256}\n" for document in documents
    )
    return hashlib.sha256(listing.encode()).hexdigest()


def pdf_pages(source: str, source_name: str = "source") -> list[str]:
    """Each page's lines of text, wrapped, ready for `pdf_bytes`."""
    pages: list[str] = []
    for number, page in enumerate(_split_pages(source), start=1):
        lines: list[str] = []
        for block in _blocks(page):
            if lines:
                lines.append("")
            lines.extend(_pdf_lines(block))
        if len(lines) > PDF_MAX_LINES_PER_PAGE:
            raise CorpusError(
                f"{source_name}: page {number} has {len(lines)} lines, but only "
                f"{PDF_MAX_LINES_PER_PAGE} fit on a page."
            )
        pages.append("\n".join(lines))
    return pages


def docx_content(source: str, source_name: str = "source") -> list[DocxItem]:
    """Headings, paragraphs, and tables, ready for `docx_bytes`."""
    content: list[DocxItem] = []
    for block in _blocks(source):
        paragraph: list[str] = []
        rows: list[list[str]] = []
        for line in block:
            if line.startswith("|"):
                _add_paragraph(content, paragraph)
                if not _TABLE_SEPARATOR_ROW.fullmatch(line.strip()):
                    rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
                continue
            _add_table(content, rows, source_name)
            if line.startswith("#"):
                _add_paragraph(content, paragraph)
                level = len(line) - len(line.lstrip("#"))
                content.append(Heading(line.lstrip("#").strip(), level))
            else:
                paragraph.append(line.strip())
        _add_paragraph(content, paragraph)
        _add_table(content, rows, source_name)
    return content


def _split_pages(source: str) -> list[str]:
    pages: list[str] = []
    current: list[str] = []
    for line in source.split("\n"):
        if line.strip() == _PAGE_BREAK:
            pages.append("\n".join(current))
            current = []
        else:
            current.append(line)
    pages.append("\n".join(current))
    return pages


def _blocks(text: str) -> list[list[str]]:
    """Runs of lines without a blank line between them."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.split("\n"):
        if line.strip():
            current.append(line.rstrip())
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _pdf_lines(block: Sequence[str]) -> list[str]:
    lines: list[str] = []
    paragraph: list[str] = []
    for line in block:
        if line.startswith("#") or line.startswith("- "):
            lines.extend(_wrap(" ".join(paragraph)))
            paragraph = []
        if line.startswith("#"):
            lines.append(line.lstrip("#").strip())
        elif line.startswith("- "):
            lines.extend(_wrap(line[2:].strip(), first="- ", rest="  "))
        else:
            paragraph.append(line.strip())
    lines.extend(_wrap(" ".join(paragraph)))
    return lines


def _wrap(text: str, first: str = "", rest: str = "") -> list[str]:
    # Hyphenated words stay on one line, so text extraction can't split them.
    return textwrap.wrap(
        text,
        PDF_LINE_WIDTH,
        initial_indent=first,
        subsequent_indent=rest,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _add_paragraph(content: list[DocxItem], paragraph: list[str]) -> None:
    if paragraph:
        content.append(" ".join(paragraph))
        paragraph.clear()


def _add_table(content: list[DocxItem], rows: list[list[str]], source_name: str) -> None:
    if not rows:
        return
    if len({len(row) for row in rows}) != 1:
        raise CorpusError(f"{source_name}: every row of a table needs the same number of cells.")
    content.append([list(row) for row in rows])
    rows.clear()
