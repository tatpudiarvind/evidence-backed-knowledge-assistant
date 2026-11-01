"""Signing in through an OpenID Connect provider (Phase 10, D-85)."""

import base64
import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import MAX_SESSION_TOKEN_LENGTH, hash_session_token, new_session_token
from app.db.models import User
from app.providers.oidc import OidcError, OidcIdentity, OidcProvider
from app.repositories import oidc as oidc_repository
from app.repositories import users as user_repository
from app.services import auth as auth_service

logger = logging.getLogger(__name__)

LOGIN_LIFETIME = timedelta(minutes=10)
DEFAULT_RETURN_PATH = "/"
MAX_RETURN_PATH_LENGTH = 512
_VERIFIER_BYTES = 48
_RANDOM_BYTES = 32
# Deliberately loose, like the one for local accounts: one "@" with text on both sides.
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")
_MAX_EMAIL_LENGTH = 320
_MAX_PARAMETER_LENGTH = 2048


@dataclass(frozen=True)
class StartedLogin:
    authorization_url: str
    login_token: str
    max_age_seconds: int


@dataclass(frozen=True)
class FinishedLogin:
    signed_in: auth_service.SignedIn
    return_to: str


def check_return_path(value: str | None) -> str:
    """A path inside this app, or an error: sign-in must not send people to another site."""
    if value is None or value == "":
        return DEFAULT_RETURN_PATH
    if (
        len(value) > MAX_RETURN_PATH_LENGTH
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise AppError(400, "invalid_return_path", "The return address must be a path in this app.")
    return value


def start_login(
    session: Session, settings: Settings, provider: OidcProvider, return_to: str | None
) -> StartedLogin:
    return_path = check_return_path(return_to)
    now = datetime.now(UTC)
    state = secrets.token_urlsafe(_RANDOM_BYTES)
    nonce = secrets.token_urlsafe(_RANDOM_BYTES)
    verifier = secrets.token_urlsafe(_VERIFIER_BYTES)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    try:
        url = provider.authorization_url(state=state, nonce=nonce, code_challenge=challenge)
    except OidcError as error:
        logger.warning("Provider sign-in can't start: %s", error)
        raise AppError(
            503, "sign_in_unavailable", "The identity provider can't be reached. Try again later."
        ) from None
    token = new_session_token()
    oidc_repository.delete_expired_login_states(session, now)
    oidc_repository.add_login_state(
        session,
        hash_session_token(token),
        state,
        nonce,
        verifier,
        return_path,
        now + LOGIN_LIFETIME,
    )
    session.commit()
    return StartedLogin(url, token, int(LOGIN_LIFETIME.total_seconds()))


def abandon_login(session: Session, login_token: str | None) -> None:
    """Drops a started sign-in, for a provider that sent the browser back with an error."""
    if login_token and len(login_token) <= MAX_SESSION_TOKEN_LENGTH:
        oidc_repository.take_login_state(
            session, hash_session_token(login_token), datetime.now(UTC)
        )
        session.commit()


def finish_login(
    session: Session,
    settings: Settings,
    provider: OidcProvider,
    login_token: str | None,
    code: str | None,
    state: str | None,
) -> FinishedLogin:
    """Completes a sign-in. Raises OidcError with a code that's safe to show."""
    if not login_token or len(login_token) > MAX_SESSION_TOKEN_LENGTH:
        raise OidcError("sign_in_expired", "No login cookie.")
    # Taken and committed first, so the state works once, whatever happens next.
    stored = oidc_repository.take_login_state(
        session, hash_session_token(login_token), datetime.now(UTC)
    )
    session.commit()
    if stored is None:
        raise OidcError("sign_in_expired", "The login state is unknown or has expired.")
    if (
        not state
        or not code
        or len(state) > _MAX_PARAMETER_LENGTH
        or len(code) > _MAX_PARAMETER_LENGTH
        or not secrets.compare_digest(state.encode(), stored.state.encode())
    ):
        raise OidcError("sign_in_refused", "The state doesn't match.")
    identity = provider.complete(code=code, code_verifier=stored.code_verifier, nonce=stored.nonce)
    user = _find_or_create_user(session, identity)
    user_repository.delete_expired_sessions(session, user.id, datetime.now(UTC))
    signed_in = auth_service.start_session(session, settings, user)
    session.commit()
    return FinishedLogin(signed_in, stored.return_to)


def _find_or_create_user(session: Session, identity: OidcIdentity) -> User:
    user = user_repository.get_user_by_identity(session, identity.issuer, identity.subject)
    if user is not None:
        return user
    # A first sign-in. An account is never linked to an existing one by email, because a
    # provider's email may not be verified, or the local account's never was: that would let
    # someone take over an account by registering its address at a provider.
    email = (identity.email or "").strip().lower()
    if not identity.email_verified or not _EMAIL.fullmatch(email) or len(email) > _MAX_EMAIL_LENGTH:
        raise OidcError("email_not_verified", "The provider gave no verified email address.")
    if user_repository.get_user_by_email(session, email) is not None:
        raise OidcError("email_in_use", "The email belongs to an account that isn't linked.")
    user = user_repository.add_user(session, email, None)
    try:
        session.flush()
        user_repository.add_identity(session, user.id, identity.issuer, identity.subject)
        session.flush()
    except IntegrityError:
        # Another request created the same account in the meantime.
        session.rollback()
        existing = user_repository.get_user_by_identity(session, identity.issuer, identity.subject)
        if existing is None:
            raise OidcError("email_in_use", "The email is already used.") from None
        return existing
    return user
