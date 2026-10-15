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
from typing import Any, Optional
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


def constant_time_compare(val1: str, val2: str) -> bool:
    """Compare two strings in constant time to prevent timing side channels."""
    if not val1 or not val2:
        return False
    return secrets.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))


def extract_client_ip(request: Any, trusted_proxies: Optional[list[str]] = None) -> str:
    """Safely extract remote client IP address respecting trusted reverse proxies.

    If request.client.host is not in trusted_proxies, X-Forwarded-For is ignored to
    prevent client IP spoofing attacks against the rate limiter.
    """
    if not hasattr(request, "client") or not request.client or not request.client.host:
        return "unknown"

    direct_ip = request.client.host
    trusted = trusted_proxies if trusted_proxies is not None else ["127.0.0.1", "::1"]

    if direct_ip in trusted:
        # Inspect X-Forwarded-For header added by trusted reverse proxy
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if parts:
                return parts[0]
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
    return direct_ip
