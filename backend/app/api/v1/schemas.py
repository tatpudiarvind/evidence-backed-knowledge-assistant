import re
import unicodedata
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.documents import DocumentStatus
from app.domain.questions import (
    MAX_QUESTION_LENGTH,
    AbstentionReason,
    AnswerMode,
    clean_question,
)
from app.domain.workspaces import WorkspaceRole

MIN_PASSWORD_LENGTH = 12
# Bounds the work of hashing a password.
MAX_PASSWORD_LENGTH = 128
MAX_WORKSPACE_NAME_LENGTH = 100
# Deliberately loose: one "@" with text on both sides. Accounts aren't verified by email.
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")


class _Credentials(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not _EMAIL.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        return email


class RegisterRequest(_Credentials):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class LoginRequest(_Credentials):
    pass


class UserOut(BaseModel):
    id: uuid.UUID
    email: str


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(max_length=1000)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        name = " ".join(value.split())
        if any(unicodedata.category(char) in {"Cc", "Cf"} for char in name):
            raise ValueError("Workspace names can't contain control or invisible characters.")
        if not 1 <= len(name) <= MAX_WORKSPACE_NAME_LENGTH:
            raise ValueError(
                f"Workspace names must be 1 to {MAX_WORKSPACE_NAME_LENGTH} characters long."
            )
        return name


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    role: WorkspaceRole
    created_at: datetime


class WorkspaceList(BaseModel):
    items: list[WorkspaceOut]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    display_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    status: DocumentStatus
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentList(BaseModel):
    items: list[DocumentOut]


class QuestionCreateRequest(BaseModel):
    # Generous, so the length that counts is checked after cleaning.
    text: str = Field(max_length=4 * MAX_QUESTION_LENGTH)

    @field_validator("text")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        text = clean_question(value)
        if not 1 <= len(text) <= MAX_QUESTION_LENGTH:
            raise ValueError(f"Questions must be 1 to {MAX_QUESTION_LENGTH} characters long.")
        return text


class CitationOut(BaseModel):
    # The [n] marker in a generated answer's text.
    number: int
    document_id: uuid.UUID
    document_name: str
    chunk_id: uuid.UUID
    # PDF pages, from 1; Word and text files have none.
    page_number: int | None
    # The Word heading the passage falls under, if any.
    section: str | None
    # The passage's text.
    excerpt: str
    # Cosine similarity to the question, from -1 to 1; higher is closer.
    similarity: float


class AnswerOut(BaseModel):
    # "generated": a language model wrote the answer, or declined to. "search_only": the
    # citations are the passages that best match the question.
    mode: AnswerMode
    # Only a generated answer that doesn't abstain has text.
    text: str | None
    abstained: bool
    abstention_reason: AbstentionReason | None
    # The model that was asked, if one was; a search-only answer names it if it didn't reply.
    model_name: str | None
    citations: list[CitationOut]


class QuestionOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    text: str
    created_at: datetime
    # When the question and its answer are deleted.
    expires_at: datetime
    answer: AnswerOut


class QuestionList(BaseModel):
    items: list[QuestionOut]


class ErrorField(BaseModel):
    location: str
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None
    fields: list[ErrorField] | None = None


class ErrorResponse(BaseModel):
    """The shape of every error the API returns."""

    error: ErrorDetail
