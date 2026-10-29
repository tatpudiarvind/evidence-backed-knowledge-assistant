"""The reviewed evaluation questions (evals/questions.jsonl), and the checks that keep them
consistent with the corpus.

A fact is a group of alternative phrasings. A text states the fact if it contains any of them
as whole words, ignoring case, spacing, and typographic quotes and dashes. That is a heuristic:
it misses phrasings nobody listed, and it can't tell a fact from its negation, which is why the
results keep each answer for review.
"""

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from app.evaluation.corpus import CorpusBlock

Phrase = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
FactGroup = Annotated[list[Phrase], Field(min_length=1)]


class Category(StrEnum):
    # The corpus answers the question.
    ANSWERABLE = "answerable"
    # The corpus doesn't, so the right response is to decline.
    UNANSWERABLE = "unanswerable"
    # The question, or a document it brings up, tries to make the assistant break its rules.
    INJECTION = "injection"


class ExpectedSource(BaseModel):
    """Where an answer is stated: a document, and optionally its page or section."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document: Phrase
    page: int | None = Field(default=None, ge=1)
    section: Phrase | None = None

    def matches(self, document: str, page_number: int | None, section: str | None) -> bool:
        return (
            document == self.document
            and (self.page is None or page_number == self.page)
            and (self.section is None or section == self.section)
        )

    def describe(self) -> str:
        page = f" page {self.page}" if self.page is not None else ""
        section = f' section "{self.section}"' if self.section else ""
        return f"{self.document}{page}{section}"


class EvalQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[str, StringConstraints(pattern=r"^[a-z][0-9]{2}$")]
    category: Category
    question: Phrase
    expected_sources: list[ExpectedSource] = Field(default_factory=list)
    # Each group is one fact a good answer states, in any of the listed phrasings.
    expected_facts: list[FactGroup] = Field(default_factory=list)
    # Text a good response never contains, such as an injected instruction's payload.
    forbidden_text: list[Phrase] = Field(default_factory=list)
    # Why the question is in the set, for reviewers.
    note: str | None = None

    @model_validator(mode="after")
    def _check_category(self) -> Self:
        if bool(self.expected_sources) != bool(self.expected_facts):
            raise ValueError("expected sources and expected facts go together")
        if self.category is Category.ANSWERABLE and not self.expected_facts:
            raise ValueError("an answerable question needs expected sources and facts")
        if self.category is Category.UNANSWERABLE and self.expected_facts:
            raise ValueError("an unanswerable question has no expected sources or facts")
        if self.category is Category.INJECTION and not self.forbidden_text:
            raise ValueError("an injection question needs forbidden text")
        return self

    def expects(self, document: str, page_number: int | None, section: str | None) -> bool:
        return any(
            source.matches(document, page_number, section) for source in self.expected_sources
        )


class DatasetError(ValueError):
    """A question file that can't be used."""


def load_questions(path: Path) -> list[EvalQuestion]:
    """The questions in a JSON Lines file: one question per line, blank lines skipped."""
    questions: list[EvalQuestion] = []
    seen: set[str] = set()
    for number, line in enumerate(_read_text(path).split("\n"), start=1):
        if not line.strip():
            continue
        try:
            question = EvalQuestion.model_validate_json(line)
        except ValidationError as error:
            raise DatasetError(f"{path.name} line {number}: {_describe(error)}") from None
        if question.id in seen:
            raise DatasetError(f"{path.name} line {number}: the ID {question.id} is taken.")
        seen.add(question.id)
        questions.append(question)
    if not questions:
        raise DatasetError(f"{path.name} has no questions.")
    return questions


def questions_sha256(path: Path) -> str:
    return hashlib.sha256(_read_text(path).encode()).hexdigest()


def _read_text(path: Path) -> str:
    # Line endings depend on how the file was checked out, so they don't count.
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _describe(error: ValidationError) -> str:
    first = error.errors()[0]
    location = ".".join(str(part) for part in first["loc"])
    return f"{location}: {first['msg']}" if location else str(first["msg"])


_TYPOGRAPHY = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
    }
)


def normalize_for_matching(text: str) -> str:
    # NFKC also turns non-breaking spaces into spaces, and subscript digits such as CO2's
    # into plain ones.
    text = unicodedata.normalize("NFKC", text).translate(_TYPOGRAPHY).casefold()
    return " ".join(text.split())


@lru_cache(maxsize=2048)
def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(normalize_for_matching(phrase))}(?!\w)")


class MatchText:
    """Text prepared once for checking which phrases it contains."""

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text = normalize_for_matching(text)

    def contains(self, phrase: str) -> bool:
        return _phrase_pattern(phrase).search(self._text) is not None

    def contains_any(self, phrases: Iterable[str]) -> bool:
        return any(self.contains(phrase) for phrase in phrases)


def check_consistency(
    blocks: Sequence[CorpusBlock], questions: Sequence[EvalQuestion]
) -> list[str]:
    """Problems that would make the questions measure the wrong thing; empty if there are none.

    Each expected source has to exist, and each expected fact has to be stated in one of the
    question's expected sources and in no other part of the corpus, so that a passage stating
    the fact comes from the right place. An unanswerable question's forbidden text must not be
    in the corpus at all.
    """
    texts = [(block, MatchText(block.text)) for block in blocks]
    problems: list[str] = []
    for question in questions:
        for source in question.expected_sources:
            if not any(source.matches(*_location(block)) for block in blocks):
                problems.append(f"{question.id}: the corpus has no {source.describe()}")
        expected = [text for block, text in texts if question.expects(*_location(block))]
        elsewhere = [
            (block, text) for block, text in texts if not question.expects(*_location(block))
        ]
        for group in question.expected_facts:
            if not any(text.contains_any(group) for text in expected):
                problems.append(f"{question.id}: no expected source states any of {group}")
            for phrase in group:
                problems.extend(
                    f"{question.id}: {phrase!r} is also in {block.describe()}"
                    for block, text in elsewhere
                    if text.contains(phrase)
                )
        if question.category is Category.UNANSWERABLE:
            for phrase in question.forbidden_text:
                problems.extend(
                    f"{question.id}: the forbidden {phrase!r} is in {block.describe()}"
                    for block, text in texts
                    if text.contains(phrase)
                )
    return problems


def _location(block: CorpusBlock) -> tuple[str, int | None, str | None]:
    return block.document, block.page_number, block.section
