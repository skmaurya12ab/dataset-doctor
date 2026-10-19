"""Tests for application settings and configuration validation."""

import ssl

import pytest
from pydantic import ValidationError
from app.core.config import Settings
from app.core.database import (
    build_alembic_engine_configuration,
    build_engine_configuration,
)


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


def test_production_requires_email_verification_even_with_configured_relay() -> None:
    settings = Settings(
        environment="production",
        email_provider="apps_script",
        require_email_verification=False,
        application_base_url="https://project.example",
        apps_script_url="https://script.google.com/macros/s/AKfycb_test-123/exec",
        apps_script_hmac_secret="A" * 32,
        _env_file=None,
    )
    with pytest.raises(ValueError, match="REQUIRE_EMAIL_VERIFICATION must be true"):
        settings.validate_email_configuration()


def test_production_rejects_incomplete_real_email_providers() -> None:
    with pytest.raises(ValueError, match="APPS_SCRIPT_URL is required"):
        Settings(
            environment="production",
            email_provider="apps_script",
            require_email_verification=True,
            application_base_url="https://project.example",
            _env_file=None,
        ).validate_email_configuration()

    with pytest.raises(ValueError, match="SMTP_HOST"):
        Settings(
            environment="production",
            email_provider="smtp",
            require_email_verification=True,
            application_base_url="https://project.example",
            email_from="no-reply@example.com",
            _env_file=None,
        ).validate_email_configuration()


def test_production_rejects_apps_script_url_without_deployment_id() -> None:
    settings = Settings(
        environment="production",
        email_provider="apps_script",
        require_email_verification=True,
        application_base_url="https://project.example",
        apps_script_url="https://script.google.com/macros/s//exec",
        apps_script_hmac_secret="A" * 32,
        _env_file=None,
    )
    with pytest.raises(ValueError, match="deployed HTTPS /exec URL"):
        settings.validate_email_configuration()


def test_production_database_requires_async_postgresql() -> None:
    with pytest.raises(ValueError, match=r"DATABASE_URL must use postgresql\+asyncpg"):
        Settings(
            environment="production",
            database_url="sqlite+aiosqlite:///:memory:",
            _env_file=None,
        ).validate_database_configuration()

    with pytest.raises(ValueError, match="database host and name"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://user:password@db.example",
            _env_file=None,
        ).validate_database_configuration()

    valid = Settings(
        environment="production",
        database_url="postgresql+asyncpg://user:password@db.example/test?sslmode=require",
        _env_file=None,
    )
    valid.validate_database_configuration()
    engine_url, engine_kwargs = build_engine_configuration(valid)
    assert "sslmode" not in engine_url.query
    ssl_context = engine_kwargs["connect_args"]["ssl"]
    assert isinstance(ssl_context, ssl.SSLContext)
    assert ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert ssl_context.check_hostname is True


def test_production_alembic_configuration_uses_verified_system_tls() -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql+asyncpg://user:password@db.example/test?sslmode=require",
        _env_file=None,
    )

    migration_config, connect_args = build_alembic_engine_configuration(
        settings, settings.database_url
    )

    assert "sslmode" not in migration_config["sqlalchemy.url"]
    ssl_context = connect_args["ssl"]
    assert isinstance(ssl_context, ssl.SSLContext)
    assert ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert ssl_context.check_hostname is True


def test_local_alembic_configuration_does_not_enable_tls() -> None:
    settings = Settings(
        environment="development",
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )

    migration_config, connect_args = build_alembic_engine_configuration(
        settings, settings.database_url
    )

    assert migration_config["sqlalchemy.url"] == settings.database_url
    assert connect_args == {}


def test_trusted_proxy_config_accepts_cidr_and_rejects_invalid_or_all_addresses() -> None:
    settings = Settings(
        trusted_proxies="127.0.0.1,10.20.0.0/16,2001:db8::/32",
        _env_file=None,
    )
    assert settings.parsed_trusted_proxies == [
        "127.0.0.1/32",
        "10.20.0.0/16",
        "2001:db8::/32",
    ]

    for value in ("*", "0.0.0.0/0", "::/0", "0.0.0.0", "not-an-ip"):
        with pytest.raises(ValueError):
            Settings(trusted_proxies=value, _env_file=None).parsed_trusted_proxies
