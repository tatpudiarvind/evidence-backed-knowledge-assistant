"""The evaluation's data (P5-01): the corpus sources, the reviewed questions, and the checks that
keep the two consistent."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.cli import EVALUATION_DIR
from app.evaluation.corpus import (
    PDF_LINE_WIDTH,
    CorpusBlock,
    CorpusError,
    build_document,
    corpus_sha256,
    docx_content,
    load_corpus,
    pdf_pages,
    read_blocks,
)
from app.evaluation.dataset import (
    Category,
    DatasetError,
    EvalQuestion,
    ExpectedSource,
    MatchText,
    check_consistency,
    load_questions,
    questions_sha256,
)
from app.evaluation.files import PDF_MAX_LINES_PER_PAGE, Heading
from tests.support import DOCX_MIME, PDF_MIME, TXT_MIME, make_settings

ANSWERABLE: dict[str, Any] = {
    "id": "a01",
    "category": "answerable",
    "question": "How long are records kept?",
    "expected_sources": [{"document": "notes.txt"}],
    "expected_facts": [["seven years", "7 years"]],
}
UNANSWERABLE: dict[str, Any] = {
    "id": "u01",
    "category": "unanswerable",
    "question": "Who audits the records?",
}
SOURCE = b"# Rules\n\nTools go back\non the wall.\n"


def question(**fields: Any) -> EvalQuestion:
    return EvalQuestion.model_validate(ANSWERABLE | fields)


def words(word: str, count: int) -> str:
    return " ".join([word] * count)


def write_lines(path: Path, *lines: str, newline: str = "\n") -> Path:
    path.write_bytes(newline.join(lines).encode())
    return path


def test_the_reviewed_questions_match_the_corpus() -> None:
    documents = load_corpus(EVALUATION_DIR / "corpus")
    questions = load_questions(EVALUATION_DIR / "questions.jsonl")

    assert check_consistency(read_blocks(documents, make_settings()), questions) == []
    # Every kind of question, every file type, and every document is covered.
    assert {question.category for question in questions} == set(Category)
    assert {document.mime_type for document in documents} == {PDF_MIME, DOCX_MIME, TXT_MIME}
    assert {source.document for question in questions for source in question.expected_sources} == {
        document.name for document in documents
    }
    # An ID starts with its category's first letter: a01 is answerable, u01 unanswerable.
    assert all(question.id[0] == question.category.value[0] for question in questions)


@pytest.mark.parametrize(
    ("source_name", "name", "mime_type", "signature"),
    [
        ("guide.pdf.md", "guide.pdf", PDF_MIME, b"%PDF-"),
        ("policy.docx.md", "policy.docx", DOCX_MIME, b"PK"),
        ("notes.txt", "notes.txt", TXT_MIME, SOURCE),
    ],
)
def test_each_source_becomes_the_file_a_user_would_upload(
    source_name: str, name: str, mime_type: str, signature: bytes
) -> None:
    document = build_document(source_name, SOURCE)

    assert (document.name, document.mime_type, document.source_name) == (
        name,
        mime_type,
        source_name,
    )
    assert document.source_sha256 == hashlib.sha256(SOURCE).hexdigest()
    assert document.content.startswith(signature)
    blocks = read_blocks([document], make_settings())
    assert {block.document for block in blocks} == {name}
    assert "Tools go back on the wall." in " ".join(
        " ".join(block.text.split()) for block in blocks
    )


@pytest.mark.parametrize("source_name", ["guide.pdf.md", "policy.docx.md", "notes.txt"])
def test_line_endings_do_not_change_a_source(source_name: str) -> None:
    lf = build_document(source_name, SOURCE)
    crlf = build_document(source_name, SOURCE.replace(b"\n", b"\r\n"))

    assert crlf.source_sha256 == lf.source_sha256
    assert corpus_sha256([crlf]) == corpus_sha256([lf])
    settings = make_settings()
    assert read_blocks([crlf], settings) == read_blocks([lf], settings)


@pytest.mark.parametrize(
    ("source_name", "data", "message"),
    [
        ("notes.md", b"Text.", "notes.md: corpus sources end in .pdf.md, .docx.md, or .txt."),
        ("notes.txt", "Caf\u00e9.".encode(), "notes.txt: corpus sources must be ASCII text."),
    ],
)
def test_unusable_sources_are_refused(source_name: str, data: bytes, message: str) -> None:
    with pytest.raises(CorpusError, match=re.escape(message)):
        build_document(source_name, data)


def test_pdf_sources_are_laid_out_in_wrapped_lines_and_pages() -> None:
    source = f"# Heading\n{words('word', 30)}\n\n- {words('item', 30)}\n---\nSecond page.\n"

    pages = pdf_pages(source)

    assert pages == [
        "\n".join(
            [
                "Heading",
                words("word", 16),
                words("word", 14),
                "",
                "- " + words("item", 15),
                "  " + words("item", 15),
            ]
        ),
        "Second page.",
    ]
    assert max(len(line) for line in pages[0].split("\n")) <= PDF_LINE_WIDTH


def test_pdf_lines_never_break_hyphenated_words() -> None:
    # Breaking at hyphens would have fit "state-of-" on the first line.
    assert pdf_pages(f"{'x' * 70} state-of-the-art") == [f"{'x' * 70}\nstate-of-the-art"]


def test_a_pdf_page_with_too_many_lines_is_refused() -> None:
    source = "Short.\n---\n" + "\n\n".join(["Line."] * 30)

    with pytest.raises(
        CorpusError,
        match=re.escape(
            f"long.pdf.md: page 2 has 59 lines, but only {PDF_MAX_LINES_PER_PAGE} fit on a page."
        ),
    ):
        pdf_pages(source, "long.pdf.md")


def test_word_sources_become_headings_paragraphs_and_tables() -> None:
    source = (
        "# Policy\nFirst part\nof a paragraph.\n\n"
        "## Rules\n| Item | Rule |\n| --- | --- |\n| Saw | Guard on |\nAfter the table.\n"
    )

    assert docx_content(source) == [
        Heading("Policy", 1),
        "First part of a paragraph.",
        Heading("Rules", 2),
        [["Item", "Rule"], ["Saw", "Guard on"]],
        "After the table.",
    ]


def test_a_table_with_uneven_rows_is_refused() -> None:
    with pytest.raises(
        CorpusError,
        match=re.escape("policy.docx.md: every row of a table needs the same number of cells."),
    ):
        docx_content("| Item | Rule |\n| Saw |\n", "policy.docx.md")


def test_the_corpus_is_every_file_in_its_folder_in_name_order(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_bytes(b"Second.\n")
    (tmp_path / "a.txt").write_bytes(b"First.\n")
    (tmp_path / "drafts").mkdir()

    documents = load_corpus(tmp_path)

    assert [document.name for document in documents] == ["a.txt", "b.txt"]
    before = corpus_sha256(documents)
    (tmp_path / "b.txt").write_bytes(b"Changed.\n")
    assert corpus_sha256(load_corpus(tmp_path)) != before


def test_an_empty_corpus_folder_is_refused(tmp_path: Path) -> None:
    (tmp_path / "corpus").mkdir()

    with pytest.raises(CorpusError, match=re.escape("There are no corpus sources in corpus.")):
        load_corpus(tmp_path / "corpus")


def test_questions_are_read_one_per_line(tmp_path: Path) -> None:
    path = write_lines(
        tmp_path / "questions.jsonl", json.dumps(UNANSWERABLE), "", json.dumps(ANSWERABLE), ""
    )

    questions = load_questions(path)

    assert [question.id for question in questions] == ["u01", "a01"]
    assert questions[0].expected_sources == []
    assert questions[0].forbidden_text == []
    assert questions[1].expects("notes.txt", None, None)
    assert not questions[1].expects("other.txt", None, None)


def test_line_endings_do_not_change_the_questions_hash(tmp_path: Path) -> None:
    lines = (json.dumps(ANSWERABLE), json.dumps(UNANSWERABLE), "")
    lf = write_lines(tmp_path / "lf.jsonl", *lines)
    crlf = write_lines(tmp_path / "crlf.jsonl", *lines, newline="\r\n")
    edited = write_lines(tmp_path / "edited.jsonl", lines[0], "")

    assert questions_sha256(crlf) == questions_sha256(lf)
    assert questions_sha256(edited) != questions_sha256(lf)


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ('{"id": "a01"', "questions.jsonl line 1: Invalid JSON"),
        (json.dumps(ANSWERABLE | {"id": "A1"}), "line 1: id: String should match pattern"),
        (
            json.dumps(ANSWERABLE | {"expected_facts": []}),
            "expected sources and expected facts go together",
        ),
        (
            json.dumps(ANSWERABLE | {"expected_sources": [], "expected_facts": []}),
            "an answerable question needs expected sources and facts",
        ),
        (
            json.dumps(ANSWERABLE | {"category": "unanswerable"}),
            "an unanswerable question has no expected sources or facts",
        ),
        (
            json.dumps(ANSWERABLE | {"category": "injection"}),
            "an injection question needs forbidden text",
        ),
        (
            json.dumps(ANSWERABLE | {"answer": "Seven years."}),
            "line 1: answer: Extra inputs are not permitted",
        ),
        (
            json.dumps(ANSWERABLE | {"expected_facts": [[]]}),
            "line 1: expected_facts.0: List should have at least 1 item",
        ),
        (
            json.dumps(ANSWERABLE | {"expected_facts": [[" "]]}),
            "line 1: expected_facts.0.0: String should have at least 1 character",
        ),
        (
            json.dumps(ANSWERABLE | {"expected_sources": [{"document": "notes.txt", "page": 0}]}),
            "line 1: expected_sources.0.page: Input should be greater than or equal to 1",
        ),
    ],
)
def test_unusable_questions_are_refused(tmp_path: Path, line: str, message: str) -> None:
    path = write_lines(tmp_path / "questions.jsonl", line)

    with pytest.raises(DatasetError, match=re.escape(message)):
        load_questions(path)


def test_each_question_needs_its_own_id(tmp_path: Path) -> None:
    path = write_lines(tmp_path / "questions.jsonl", json.dumps(ANSWERABLE), json.dumps(ANSWERABLE))

    with pytest.raises(
        DatasetError, match=re.escape("questions.jsonl line 2: the ID a01 is taken.")
    ):
        load_questions(path)


def test_a_file_without_questions_is_refused(tmp_path: Path) -> None:
    path = write_lines(tmp_path / "questions.jsonl", "", "  ", "")

    with pytest.raises(DatasetError, match=re.escape("questions.jsonl has no questions.")):
        load_questions(path)


@pytest.mark.parametrize(
    ("text", "phrase", "expected"),
    [
        ("Membership costs EUR 35 a month.", "eur 35", True),
        ("Membership costs EUR\n   35 a month.", "EUR 35", True),
        ("Membership costs EUR 350 a year.", "EUR 35", False),
        ("Membership costs \u20ac35.", "\u20ac35", True),
        ("Membership costs \u20ac350.", "\u20ac35", False),
        ("Woodworking classes", "wood", False),
        ("Open\u00a0daily", "open daily", True),
        ("The \u201ckeyholder\u201d rule", '"keyholder"', True),
        ("Don\u2019t leave tools out.", "don't", True),
        ("Open 10:00\u201318:00", "10:00-18:00", True),
        ("CO\u2082 detectors", "CO2", True),
    ],
)
def test_phrases_match_whole_words_ignoring_case_spacing_and_typography(
    text: str, phrase: str, expected: bool
) -> None:
    assert MatchText(text).contains(phrase) is expected


def test_a_fact_is_stated_in_any_of_its_phrasings() -> None:
    text = MatchText("Closes at 6 pm.")

    assert text.contains_any(["18:00", "6 pm"])
    assert not text.contains_any(["18:00"])
    assert not text.contains_any([])


def test_expected_sources_can_name_a_page_or_a_section() -> None:
    section = ExpectedSource(document="policy.docx", section="Rules")
    page = ExpectedSource(document="guide.pdf", page=2)

    assert section.describe() == 'policy.docx section "Rules"'
    assert section.matches("policy.docx", None, "Rules")
    assert not section.matches("policy.docx", None, "Scope")
    assert page.describe() == "guide.pdf page 2"
    assert page.matches("guide.pdf", 2, None)
    assert not page.matches("guide.pdf", 1, None)


def test_consistency_problems_are_listed() -> None:
    blocks = [
        CorpusBlock(
            "notes.txt", None, None, "Records are kept for seven years. The office opens at 9:00."
        ),
        CorpusBlock("other.txt", None, None, "Backups are kept for seven years."),
        CorpusBlock("guide.pdf", 1, None, "Opening hours are on the next page."),
        CorpusBlock("guide.pdf", 2, None, "The workshop opens at 10:00."),
    ]
    questions = [
        # "seven years" is also in other.txt, so a passage stating it could come from there.
        question(id="a01"),
        question(id="a02", expected_facts=[["9:00"]]),
        question(
            id="a03", expected_sources=[{"document": "missing.txt"}], expected_facts=[["9:00"]]
        ),
        question(
            id="a04",
            expected_sources=[{"document": "guide.pdf", "page": 1}],
            expected_facts=[["10:00"]],
        ),
        question(
            id="a05",
            expected_sources=[{"document": "guide.pdf", "page": 2}],
            expected_facts=[["10:00"]],
        ),
        question(
            id="u01",
            category="unanswerable",
            expected_sources=[],
            expected_facts=[],
            forbidden_text=["office"],
        ),
    ]

    assert check_consistency(blocks, questions) == [
        "a01: 'seven years' is also in other.txt",
        "a03: the corpus has no missing.txt",
        "a03: no expected source states any of ['9:00']",
        "a03: '9:00' is also in notes.txt",
        "a04: no expected source states any of ['10:00']",
        "a04: '10:00' is also in guide.pdf page 2",
        "u01: the forbidden 'office' is in notes.txt",
    ]
