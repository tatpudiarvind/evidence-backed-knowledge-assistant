import re
import unicodedata
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.documents import DocumentStatus
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
