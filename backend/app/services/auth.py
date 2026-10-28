"""Local accounts and server-side sessions (D-32)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    MAX_SESSION_TOKEN_LENGTH,
    PasswordHashing,
    hash_session_token,
    new_session_token,
)
from app.db.models import User
from app.repositories import users as user_repository


@dataclass(frozen=True)
class SignedIn:
    user: User
    session_token: str
    max_age_seconds: int


def register(
    session: Session, passwords: PasswordHashing, settings: Settings, email: str, password: str
) -> SignedIn:
    if not settings.registration_enabled:
        raise AppError(403, "registration_disabled", "Registration is turned off on this server.")
    if user_repository.get_user_by_email(session, email) is not None:
        raise _email_taken()
    user = user_repository.add_user(session, email, passwords.hash(password))
    try:
        session.flush()
    except IntegrityError:
        # Another request registered the same email in the meantime.
        session.rollback()
        raise _email_taken() from None
    signed_in = _start_session(session, settings, user)
    session.commit()
    return signed_in


def login(
    session: Session,
    passwords: PasswordHashing,
    settings: Settings,
    email: str,
    password: str,
    previous_token: str | None,
) -> SignedIn:
    user = user_repository.get_user_by_email(session, email)
    if user is None:
        passwords.spend_verification_time(password)
        raise _invalid_credentials()
    if not passwords.verify(user.password_hash, password):
        raise _invalid_credentials()
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash(password)
    if token_hash := _hash_if_plausible(previous_token):
        # Signing in replaces whatever session this browser had before.
        user_repository.delete_session(session, token_hash)
    user_repository.delete_expired_sessions(session, user.id, datetime.now(UTC))
    signed_in = _start_session(session, settings, user)
    session.commit()
    return signed_in


def logout(session: Session, token: str | None) -> None:
    if token_hash := _hash_if_plausible(token):
        user_repository.delete_session(session, token_hash)
        session.commit()


def user_for_session_token(session: Session, token: str | None) -> User | None:
    token_hash = _hash_if_plausible(token)
    if token_hash is None:
        return None
    return user_repository.get_user_by_session(session, token_hash, datetime.now(UTC))


def _start_session(session: Session, settings: Settings, user: User) -> SignedIn:
    token = new_session_token()
    lifetime = timedelta(hours=settings.session_lifetime_hours)
    user_repository.add_session(
        session, user.id, hash_session_token(token), datetime.now(UTC) + lifetime
    )
    return SignedIn(user, token, int(lifetime.total_seconds()))


def _hash_if_plausible(token: str | None) -> str | None:
    if not token or len(token) > MAX_SESSION_TOKEN_LENGTH:
        return None
    return hash_session_token(token)


def _email_taken() -> AppError:
    return AppError(409, "email_already_registered", "An account with this email already exists.")


def _invalid_credentials() -> AppError:
    # The same answer for an unknown email and a wrong password.
    return AppError(401, "invalid_credentials", "The email or password is incorrect.")
