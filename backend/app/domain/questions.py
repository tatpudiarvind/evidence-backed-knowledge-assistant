"""Question rules (Phase 4): what is kept, for how long, and how an answer can turn out."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domain.indexing import normalize_text

# Questions are deleted with their answers and citations three days after being asked (D-55).
QUESTION_RETENTION = timedelta(days=3)
MAX_QUESTION_LENGTH = 1000
# The history lists at most this many of the caller's most recent questions.
HISTORY_LIMIT = 50


class AnswerMode(StrEnum):
    # A language model is configured to write answers from the matching passages.
    GENERATED = "generated"
    # No model wrote the answer: the matching passages are the answer.
    SEARCH_ONLY = "search_only"


class AbstentionReason(StrEnum):
    # No document in the workspace was indexed when the question was asked.
    NO_INDEXED_DOCUMENTS = "no_indexed_documents"
    # No passage was similar enough to the question to count as evidence.
    WEAK_EVIDENCE = "weak_evidence"
    # The model replied that the passages don't answer the question.
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    # The model's reply cited none of the passages it was given, so it wasn't kept.
    UNCITED_ANSWER = "uncited_answer"


@dataclass(frozen=True)
class Passage:
    """A chunk found for a question: its text, where it comes from, and its cosine similarity."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    text: str
    page_number: int | None
    section: str | None
    similarity: float


@dataclass(frozen=True)
class CitationRecord:
    # The [n] marker in the answer's text, from 1.
    number: int
    passage: Passage


@dataclass(frozen=True)
class AnswerRecord:
    mode: AnswerMode
    # Only generated answers that don't abstain have text.
    text: str | None
    abstention_reason: AbstentionReason | None
    # The model that was asked, if one was.
    model_name: str | None
    citations: tuple[CitationRecord, ...]

    @property
    def abstained(self) -> bool:
        return self.abstention_reason is not None


@dataclass(frozen=True)
class QuestionRecord:
    id: uuid.UUID
    workspace_id: uuid.UUID
    text: str
    created_at: datetime
    answer: AnswerRecord

    @property
    def expires_at(self) -> datetime:
        return self.created_at + QUESTION_RETENTION


def clean_question(text: str) -> str:
    """A question as it is searched for and stored: normalized, on one line, nothing invisible."""
    return " ".join(normalize_text(text).split())
