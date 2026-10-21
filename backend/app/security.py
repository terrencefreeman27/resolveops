"""Password hashing and opaque session tokens."""
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerificationError:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """Only hashes of session tokens are stored, so a DB leak does not leak live sessions."""
    return hashlib.sha256(token.encode()).hexdigest()
