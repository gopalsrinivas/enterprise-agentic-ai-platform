"""Argon2id password hashing with safe verification behavior."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
_dummy_hash = _hasher.hash("not-a-real-user-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    candidate = password_hash or _dummy_hash
    try:
        valid = _hasher.verify(candidate, password)
    except (VerificationError, InvalidHashError):
        return False
    return bool(valid and password_hash is not None)
