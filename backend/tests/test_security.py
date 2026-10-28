import hashlib

from argon2 import PasswordHasher, profiles

from app.core.security import (
    PasswordHashing,
    hash_session_token,
    new_session_token,
)

CHEAP = PasswordHasher.from_parameters(profiles.CHEAPEST)


def test_hashes_verify_only_the_original_password() -> None:
    passwords = PasswordHashing(CHEAP)
    password_hash = passwords.hash("correct horse battery staple")

    assert password_hash.startswith("$argon2id$")
    assert "correct horse" not in password_hash
    assert passwords.verify(password_hash, "correct horse battery staple")
    assert not passwords.verify(password_hash, "wrong password entirely")


def test_invalid_stored_hash_fails_verification_instead_of_raising() -> None:
    assert not PasswordHashing(CHEAP).verify("not-a-hash", "anything")


def test_default_parameters_are_argon2id_low_memory_profile() -> None:
    password_hash = PasswordHashing().hash("correct horse battery staple")

    assert password_hash.startswith("$argon2id$v=19$m=65536,t=3,p=4$")


def test_hashes_with_old_parameters_need_rehashing() -> None:
    old_hash = PasswordHashing(CHEAP).hash("correct horse battery staple")

    assert PasswordHashing().needs_rehash(old_hash)
    assert not PasswordHashing(CHEAP).needs_rehash(old_hash)


def test_spending_verification_time_never_succeeds() -> None:
    passwords = PasswordHashing(CHEAP)

    passwords.spend_verification_time("anything")
    passwords.spend_verification_time("anything")


def test_session_tokens_are_random_and_stored_only_as_hashes() -> None:
    first, second = new_session_token(), new_session_token()

    assert first != second
    assert len(first) == 43
    assert hash_session_token(first) == hashlib.sha256(first.encode()).hexdigest()
    assert hash_session_token(first) != first
