"""Centralized structured logging configuration for Dataset Doctor.

Follows production best practices:
- Standardized formatting: timestamp, level, logger name, message.
- Sanitizes sensitive credentials and suppresses verbose external logs.
- Safe for production and container environments (stdout/stderr).
"""

import logging
import re
import sys
from typing import Optional


class SensitiveDataFilter(logging.Filter):
    """Filter that masks potential API keys and secrets from log records."""

    PATTERNS = [
        (re.compile(r"(sk-[a-zA-Z0-9_-]{20,})"), "[REDACTED_API_KEY]"),
        (re.compile(r"(password[=:]\s*['\"]?)([^'\"\s&]+)(['\"]?)", re.IGNORECASE), r"\1[REDACTED_PASSWORD]\3"),
        (re.compile(r"(api[-_]?key[=:]\s*['\"]?)([^'\"\s&]+)(['\"]?)", re.IGNORECASE), r"\1[REDACTED_API_KEY]\3"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern, replacement in self.PATTERNS:
                msg = pattern.sub(replacement, msg)
            record.msg = msg
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure root and application loggers with structured formatting."""
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    )
    date_format = "%Y-%m-%d %H:%M:%S"

    # Reset any existing handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Console stream handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(fmt=log_format, datefmt=date_format))
    console_handler.addFilter(SensitiveDataFilter())
    root_logger.addHandler(console_handler)

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Convenience helper to retrieve an application logger."""
    return logging.getLogger(name or "dataset_doctor")
