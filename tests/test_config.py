"""Tests for application settings and configuration validation."""

import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_default_settings_instantiation() -> None:
    """Verify that default settings instantiate with expected fallback values."""
    settings = Settings()
    assert settings.app_name == "Dataset Doctor"
    assert settings.environment == "development"
    assert settings.is_development is True
    assert settings.is_testing is False
    assert settings.is_production is False
    assert settings.max_upload_size_mb == 100
    assert settings.max_upload_size_bytes == 100 * 1024 * 1024
    assert settings.log_level == "INFO"
    assert settings.max_worker_threads == 4


def test_log_level_validation() -> None:
    """Verify that valid log levels pass and invalid ones raise ValidationError."""
    s = Settings(log_level="debug")
    assert s.log_level == "DEBUG"

    with pytest.raises(ValidationError):
        Settings(log_level="VERBOSE_INVALID")


def test_environment_flags() -> None:
    """Verify environment helper properties."""
    prod = Settings(environment="production")
    assert prod.is_production is True
    assert prod.is_development is False

    testing = Settings(environment="testing")
    assert testing.is_testing is True
    assert testing.is_production is False
