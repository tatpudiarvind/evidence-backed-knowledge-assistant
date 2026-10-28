"""Password hashing and session tokens (D-32). Uses argon2-cffi; no custom cryptography."""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

SESSION_TOKEN_BYTES = 32
# token_urlsafe(32) is 43 characters; anything much longer is not a token this server issued.
MAX_SESSION_TOKEN_LENGTH = 128


class PasswordHashing:
    """Argon2id hashing with argon2-cffi's default parameters (RFC 9106, low-memory profile)."""

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or PasswordHasher()
        self._dummy_hash: str | None = None

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)

    def spend_verification_time(self, password: str) -> None:
        """Check a throwaway hash, so an unknown email takes as long as a wrong password."""
        if self._dummy_hash is None:
            self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(16))
        self.verify(self._dummy_hash, password)


def new_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """Sessions are stored by this hash; the token itself exists only in the user's cookie."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
