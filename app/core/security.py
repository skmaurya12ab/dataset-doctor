"""Cryptographic security utilities for authentication and session management.

Implements:
- Argon2id password hashing and verification using argon2-cffi.
- Cryptographically secure random token generation.
- SHA-256 token hashing for session identifiers and single-use verification/reset tokens.
- Strict email normalization.
"""

import hashlib
import ipaddress
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
    """Extract a client IP only when the immediate peer is a configured proxy.

    Forwarded addresses are parsed as IPs and walked right-to-left, skipping
    configured proxy networks. X-Real-IP is intentionally ignored because an
    incoming client may be able to supply it through an unverified proxy path.
    """
    if not hasattr(request, "client") or not request.client or not request.client.host:
        return "unknown"

    direct_text = request.client.host
    try:
        direct_ip = ipaddress.ip_address(direct_text)
    except ValueError:
        return direct_text

    trusted = trusted_proxies if trusted_proxies is not None else ["127.0.0.1", "::1"]

    def is_trusted(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        for entry in trusted:
            try:
                if address in ipaddress.ip_network(entry, strict=False):
                    return True
            except ValueError:
                # Invalid entries never grant proxy trust.
                continue
        return False

    if not is_trusted(direct_ip):
        return direct_ip.compressed

    forwarded = request.headers.get("X-Forwarded-For")
    if not forwarded:
        return direct_ip.compressed

    try:
        forwarded_ips = [
            ipaddress.ip_address(part.strip())
            for part in forwarded.split(",")
            if part.strip()
        ]
    except ValueError:
        return direct_ip.compressed

    for address in reversed(forwarded_ips):
        if not is_trusted(address):
            return address.compressed
    return direct_ip.compressed
