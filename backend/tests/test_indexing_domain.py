"""Text normalization (P3-03) and chunking (P3-04): pure functions, no database needed."""

import random

import pytest

from app.db.models import Document
from app.domain.indexing import (
    FAILURE_MESSAGES,
    MAX_FAILURE_MESSAGE_LENGTH,
    MAX_SECTION_LENGTH,
    IndexingError,
    IndexingFailure,
    TextBlock,
    TextChunk,
    chunk_blocks,
    normalize_blocks,
    normalize_text,
    split_spans,
)


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("one\r\ntwo\rthree\x0cfour\u2028five", "one\ntwo\nthree\nfour\nfive"),
        ("\ufb01nance and \ufb02ow", "finance and flow"),
        ("cafe\u0301", "caf\u00e9"),
        ("tab\there\u00a0and\u2003wide", "tab here and wide"),
        ("  many    spaces  ", "many spaces"),
        (
            "null\x00byte, soft\u00adhyphen, zero\u200bwidth, \u202eflipped\ufeff",
            "nullbyte, softhyphen, zerowidth, flipped",
        ),
        ("lone \ud800 surrogate", "lone surrogate"),
        ("para one\n\n\n\n\npara two", "para one\n\npara two"),
        ("line   \n   \n\t\n next", "line\n\nnext"),
        ("\n\n  edges  \n\n", "edges"),
    ],
    ids=[
        "line-breaks",
        "ligatures",
        "composed-accents",
        "space-characters",
        "repeated-spaces",
        "invisible-characters",
        "lone-surrogate",
        "blank-lines",
        "whitespace-lines",
        "edges",
    ],
)
def test_normalize_text(raw: str, normalized: str) -> None:
    assert normalize_text(raw) == normalized


def test_normalize_blocks_drops_empty_blocks_and_tidies_sections() -> None:
    blocks = [
        TextBlock(" \n\x00\u200b ", page_number=1),
        TextBlock("Page two\x00 text", page_number=2, section="  Results \n and\tmethods "),
        TextBlock("Body", section=" \u200b "),
    ]

    assert normalize_blocks(blocks) == [
        TextBlock("Page two text", page_number=2, section="Results and methods"),
        TextBlock("Body"),
    ]


def test_long_section_titles_are_shortened() -> None:
    [block] = normalize_blocks([TextBlock("Body", section="word " * 100)])

    assert block.section == ("word " * 60).rstrip()
    assert len(block.section) <= MAX_SECTION_LENGTH


def _pieces(text: str, size: int, overlap: int = 0) -> list[str]:
    return [text[start:end] for start, end in split_spans(text, size, overlap)]


def test_short_text_is_one_span_without_surrounding_whitespace() -> None:
    assert split_spans("  short text \n", 100, 0) == [(2, 12)]


@pytest.mark.parametrize("text", ["", "   \n\n  "])
def test_blank_text_has_no_spans(text: str) -> None:
    assert split_spans(text, 100, 10) == []


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (1, 0), (100, -1), (100, 26)])
def test_invalid_sizes_are_refused(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        split_spans("Some text", size, overlap)


def test_cuts_prefer_paragraph_breaks() -> None:
    text = "First paragraph here.\n\nSecond one. More words follow on."

    assert _pieces(text, 40) == ["First paragraph here.", "Second one. More words follow on."]


def test_cuts_prefer_line_breaks_to_sentence_ends() -> None:
    text = "Some opening words go\nhere. Then more text follows on"

    assert _pieces(text, 40) == ["Some opening words go", "here. Then more text follows on"]


def test_cuts_prefer_sentence_ends_to_spaces() -> None:
    text = 'One sentence ends here. He said "stop it." Then another keeps going on'

    assert _pieces(text, 50) == [
        'One sentence ends here. He said "stop it."',
        "Then another keeps going on",
    ]


def test_chinese_and_japanese_sentence_ends_need_no_space() -> None:
    text = "\u8fd9\u662f\u4e00\u4e2a\u5f88\u957f\u7684\u53e5\u5b50\u3002" * 10

    pieces = _pieces(text, 25)

    assert "".join(pieces) == text
    assert all(len(piece) == 20 and piece.endswith("\u3002") for piece in pieces)


def test_text_without_spaces_is_cut_at_the_size_limit() -> None:
    assert split_spans("x" * 25, 10, 2) == [(0, 10), (10, 20), (20, 25)]


def test_overlap_starts_at_a_whole_word() -> None:
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"

    assert _pieces(text, 30, 7) == [
        "alpha beta gamma delta",
        "delta epsilon zeta eta theta",
        "theta iota kappa",
    ]


def test_pieces_starting_in_the_overlap_must_add_text() -> None:
    # Only whitespace follows "dd", so a piece starting there would add nothing.
    text = "aaaa bbbb cc dd" + " " * 40 + "ee"

    assert _pieces(text, 16, 4) == ["aaaa bbbb cc dd", "ee"]


_WORDS = [
    "evidence",
    "a",
    "retention",
    "policy",
    "x" * 40,
    "caf\u00e9",
    "\u6570\u636e",
    "(see",
    "p.)",
]
_SEPARATORS = [" ", " ", " ", "\n", "\n\n", ". ", "? ", "\u3002", "\t", "   "]


def _random_text(seed: int) -> str:
    rng = random.Random(seed)
    words = rng.randint(0, 400)
    return "".join(rng.choice(_WORDS) + rng.choice(_SEPARATORS) for _ in range(words))


@pytest.mark.parametrize(("size", "overlap"), [(2, 0), (7, 1), (50, 12), (200, 50), (1000, 150)])
def test_spans_cover_the_text_in_bounded_overlapping_pieces(size: int, overlap: int) -> None:
    for seed in range(30):
        text = _random_text(seed)
        spans = split_spans(text, size, overlap)
        covered = [False] * len(text)
        for index, (start, end) in enumerate(spans):
            assert 0 <= start < end <= len(text)
            assert end - start <= size
            assert not text[start].isspace() and not text[end - 1].isspace()
            covered[start:end] = [True] * (end - start)
            if index:
                previous_start, previous_end = spans[index - 1]
                assert start - previous_start >= size // 2 - overlap
                assert previous_end - start <= overlap
                assert end > previous_end
        assert all(covered[i] or char.isspace() for i, char in enumerate(text)), seed


def test_chunks_follow_blocks_and_are_numbered_in_reading_order() -> None:
    long_page = " ".join(f"Sentence {n} of the first page." for n in range(20))
    blocks = [
        TextBlock(long_page, page_number=1),
        TextBlock("Short page.", page_number=2),
        TextBlock("Section body.", section="Methods"),
    ]

    chunks = chunk_blocks(blocks, 200, 50)

    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    assert chunks[-2:] == [
        TextChunk(len(chunks) - 2, "Short page.", 2, None),
        TextChunk(len(chunks) - 1, "Section body.", None, "Methods"),
    ]
    first_page = chunks[:-2]
    assert len(first_page) > 1
    assert all(chunk.page_number == 1 and chunk.text in long_page for chunk in first_page)
    assert all(chunk.text.endswith(".") for chunk in first_page)


def test_no_blocks_means_no_chunks() -> None:
    assert chunk_blocks([], 1000, 150) == []


def test_every_failure_has_a_message_that_fits_the_database() -> None:
    columns = Document.__table__.c

    assert set(FAILURE_MESSAGES) == set(IndexingFailure)
    for failure, message in FAILURE_MESSAGES.items():
        assert len(failure.value) <= columns.failure_code.type.length
        assert 0 < len(message) <= MAX_FAILURE_MESSAGE_LENGTH
    assert MAX_FAILURE_MESSAGE_LENGTH <= columns.failure_message.type.length


def test_indexing_errors_carry_a_code_and_a_safe_message() -> None:
    error = IndexingError(IndexingFailure.TOO_MANY_PAGES)
    shortened = IndexingError(IndexingFailure.INGESTION_FAILED, "x" * 600)

    assert str(error) == "too_many_pages"
    assert error.message == FAILURE_MESSAGES[IndexingFailure.TOO_MANY_PAGES]
    assert shortened.message == "x" * MAX_FAILURE_MESSAGE_LENGTH
