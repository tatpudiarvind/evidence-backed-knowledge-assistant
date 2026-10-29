"""Request dependencies: settings, database session, storage, indexing, and the signed-in user."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import PasswordHashing
from app.db.models import User
from app.providers.storage import DocumentStorage
from app.services import auth as auth_service
from app.workers.ingestion import IngestionWorker

SESSION_COOKIE_NAME = "eka_session"
# Browsers only send custom headers cross-site after a CORS preflight that the API allows, and
# HTML forms can't send them at all. Requiring one blocks cross-site request forgery (D-32).
CSRF_HEADER_NAME = "X-CSRF-Protection"
_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

session_cookie = APIKeyCookie(
    name=SESSION_COOKIE_NAME,
    auto_error=False,
    description="Session cookie that sign-in sets (HttpOnly, SameSite=Strict).",
)


async def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_storage(request: Request) -> DocumentStorage:
    storage: DocumentStorage = request.app.state.storage
    return storage


async def get_passwords(request: Request) -> PasswordHashing:
    passwords: PasswordHashing = request.app.state.passwords
    return passwords


async def get_ingestion_worker(request: Request) -> IngestionWorker:
    worker: IngestionWorker = request.app.state.ingestion_worker
    return worker


def get_db(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
StorageDep = Annotated[DocumentStorage, Depends(get_storage)]
PasswordsDep = Annotated[PasswordHashing, Depends(get_passwords)]
IngestionWorkerDep = Annotated[IngestionWorker, Depends(get_ingestion_worker)]
DbSession = Annotated[Session, Depends(get_db)]
SessionToken = Annotated[str | None, Depends(session_cookie)]


async def require_csrf_header(request: Request) -> None:
    if request.method in _STATE_CHANGING_METHODS and request.headers.get(CSRF_HEADER_NAME) != "1":
        raise AppError(
            403,
            "csrf_header_missing",
            f"State-changing requests need the header {CSRF_HEADER_NAME}: 1.",
        )


def get_current_user(session: DbSession, token: SessionToken) -> User:
    user = auth_service.user_for_session_token(session, token)
    if user is None:
        raise AppError(401, "not_authenticated", "Sign in to continue.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
