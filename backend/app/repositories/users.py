import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import User, UserSession


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email))


def add_user(session: Session, email: str, password_hash: str) -> User:
    user = User(email=email, password_hash=password_hash)
    session.add(user)
    return user


def add_session(
    session: Session, user_id: uuid.UUID, token_hash: str, expires_at: datetime
) -> UserSession:
    user_session = UserSession(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    session.add(user_session)
    return user_session


def get_user_by_session(session: Session, token_hash: str, now: datetime) -> User | None:
    return session.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.token_hash == token_hash, UserSession.expires_at > now)
    )


def delete_session(session: Session, token_hash: str) -> None:
    session.execute(delete(UserSession).where(UserSession.token_hash == token_hash))


def delete_expired_sessions(session: Session, user_id: uuid.UUID, now: datetime) -> None:
    session.execute(
        delete(UserSession).where(UserSession.user_id == user_id, UserSession.expires_at <= now)
    )
