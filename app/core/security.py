"""Cryptographic security utilities for authentication and session management.

Implements:
- Argon2id password hashing and verification using argon2-cffi.
- Cryptographically secure random token generation.
- SHA-256 token hashing for session identifiers and single-use verification/reset tokens.
- Strict email normalization.
"""

import hashlib
import re
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Argon2id password hasher with standard memory, time, and parallelism parameters
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using Argon2id with random salt."""
    if not plain_password or len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash in constant time."""
    if not plain_password or not hashed_password:
        return False
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def generate_token(nbytes: int = 32) -> str:
    """Generate a cryptographically secure URL-safe random token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Compute deterministic SHA-256 hex digest of a token for database storage.

    Tokens are never stored in plaintext in the database; only their hashes are retained.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    """Normalize an email address (lowercase, whitespace trimmed)."""
    if not email:
        return ""
    normalized = email.strip().lower()
    return normalized


def validate_email_format(email: str) -> bool:
    """Basic structural validation for email addresses."""
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return bool(re.match(pattern, email))
