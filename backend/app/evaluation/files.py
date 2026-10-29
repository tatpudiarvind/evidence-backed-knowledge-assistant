"""Small, repeatable PDF and Word files, built without office software (Phase 5).

The evaluation corpus is built with these, and so are the tests' sample files.
"""

import io
from dataclasses import dataclass

import docx

# Points between lines, and where the first line starts; a page is 792 points high.
PDF_LINE_SPACING = 14
PDF_FIRST_LINE_Y = 720
# As many lines as stay above the bottom margin.
PDF_MAX_LINES_PER_PAGE = 48


def pdf_bytes(*pages: str) -> bytes:
    """A real PDF with one page per argument, showing its lines of text in Helvetica.

    An empty string makes a page without any text. Text must fit the Windows-1252 code page.
    """
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", font]
    page_numbers: list[int] = []
    for text in pages or ("Synthetic test PDF",):
        shown = b" T* ".join(_pdf_string(line) + b" Tj" for line in text.split("\n"))
        start = b"BT /F1 12 Tf %d TL 72 %d Td " % (PDF_LINE_SPACING, PDF_FIRST_LINE_Y)
        stream = start + shown + b" ET" if text else b""
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % len(objects)
        )
        page_numbers.append(len(objects))
    kids = b" ".join(b"%d 0 R" % number for number in page_numbers)
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_numbers))
    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref_offset = len(output)
    output += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    output += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    output += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    output += b"startxref\n%d\n%%%%EOF\n" % xref_offset
    return bytes(output)


def _pdf_string(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return b"(" + escaped.encode("cp1252") + b")"


@dataclass(frozen=True)
class Heading:
    text: str
    level: int = 1


def docx_bytes(*content: str | Heading | list[list[str]]) -> bytes:
    """A real Word document: strings are paragraphs, `Heading`s headings, lists of rows tables."""
    document = docx.Document()
    for item in content or ("Synthetic test document",):
        if isinstance(item, Heading):
            document.add_heading(item.text, item.level)
        elif isinstance(item, str):
            document.add_paragraph(item)
        else:
            table = document.add_table(rows=len(item), cols=len(item[0]))
            for row, values in zip(table.rows, item, strict=True):
                for cell, value in zip(row.cells, values, strict=True):
                    cell.text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
