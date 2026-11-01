from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import OidcLoginState


@dataclass(frozen=True)
class LoginState:
    state: str
    nonce: str
    code_verifier: str
    return_to: str
    expires_at: datetime


def add_login_state(
    session: Session,
    token_hash: str,
    state: str,
    nonce: str,
    code_verifier: str,
    return_to: str,
    expires_at: datetime,
) -> None:
    session.add(
        OidcLoginState(
            token_hash=token_hash,
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            return_to=return_to,
            expires_at=expires_at,
        )
    )


def take_login_state(session: Session, token_hash: str, now: datetime) -> LoginState | None:
    """Deletes the state and returns it, so it can be used once; None if unknown or expired."""
    row = session.execute(
        delete(OidcLoginState)
        .where(OidcLoginState.token_hash == token_hash)
        .returning(
            OidcLoginState.state,
            OidcLoginState.nonce,
            OidcLoginState.code_verifier,
            OidcLoginState.return_to,
            OidcLoginState.expires_at,
        )
    ).one_or_none()
    if row is None or row.expires_at <= now:
        return None
    return LoginState(row.state, row.nonce, row.code_verifier, row.return_to, row.expires_at)


def delete_expired_login_states(session: Session, now: datetime) -> None:
    session.execute(delete(OidcLoginState).where(OidcLoginState.expires_at <= now))


__all__ = ["LoginState", "add_login_state", "delete_expired_login_states", "take_login_state"]
