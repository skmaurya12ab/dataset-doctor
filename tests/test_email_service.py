"""Unit tests for secure authentication email providers and configuration."""

import asyncio
import hashlib
import hmac
import json
from urllib.request import Request

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services import email_service
from app.services.email_service import (
    AppsScriptEmailService,
    ContentServiceRedirectHandler,
    MockEmailService,
    SMTPEmailService,
    build_action_url,
    canonical_relay_message,
)


def apps_script_settings(**overrides) -> Settings:
    values = {
        "environment": "testing",
        "email_provider": "apps_script",
        "application_base_url": "https://dataset.example",
        "apps_script_url": "https://script.google.com/macros/s/deployment/exec",
        "apps_script_hmac_secret": SecretStr("s" * 48),
    }
    values.update(overrides)
    return Settings(**values)


def test_hmac_payload_signature_is_valid_and_tampering_is_detected() -> None:
    service = AppsScriptEmailService(apps_script_settings())
    payload = service._create_payload("verification", "Person@Example.com", "A" * 43)
    assert payload["recipient"] == "person@example.com"
    canonical = canonical_relay_message(
        schema_version=payload["schema_version"],
        timestamp=payload["timestamp"],
        nonce=payload["nonce"],
        request_id=payload["request_id"],
        message_type=payload["message_type"],
        recipient=payload["recipient"],
        action_url=payload["action_url"],
    )
    expected = hmac.new(("s" * 48).encode(), canonical, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(payload["signature"], expected)
    tampered = dict(payload, recipient="attacker@example.com")
    tampered_canonical = canonical_relay_message(
        schema_version=tampered["schema_version"],
        timestamp=tampered["timestamp"],
        nonce=tampered["nonce"],
        request_id=tampered["request_id"],
        message_type=tampered["message_type"],
        recipient=tampered["recipient"],
        action_url=tampered["action_url"],
    )
    assert not hmac.compare_digest(
        payload["signature"], hmac.new(("s" * 48).encode(), tampered_canonical, hashlib.sha256).hexdigest()
    )


def test_v1_canonical_representation_and_content_redirect_host_are_fixed() -> None:
    canonical = canonical_relay_message(
        schema_version=1,
        timestamp=123,
        nonce="a" * 32,
        request_id="123e4567-e89b-42d3-a456-426614174000",
        message_type="verification",
        recipient="person@example.com",
        action_url="https://dataset.example/verify-email?token=" + "a" * 43,
    )
    assert canonical == (
        b"dataset-doctor-email-relay-v1\n1\n123\n"
        b"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n123e4567-e89b-42d3-a456-426614174000\n"
        b"verification\nperson@example.com\n"
        b"https://dataset.example/verify-email?token=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )

    handler = ContentServiceRedirectHandler()
    request = Request("https://script.google.com/macros/s/id/exec", data=b"{}", method="POST")
    assert handler.redirect_request(
        request, None, 302, "Found", {}, "https://script.googleusercontent.com/macros/echo?key=one-time"
    ) is not None
    assert handler.redirect_request(
        request, None, 302, "Found", {}, "https://attacker.example/collect"
    ) is None


def test_action_urls_match_existing_frontend_routes_and_encode_token() -> None:
    verify = build_action_url("https://dataset.example", "verification", "A" * 43)
    reset = build_action_url("https://dataset.example", "password_reset", "B" * 43)
    assert verify == "https://dataset.example/verify-email?token=" + "A" * 43
    assert reset == "https://dataset.example/reset-password?token=" + "B" * 43
    with pytest.raises(ValueError):
        build_action_url("https://dataset.example/other", "verification", "A" * 43)
    with pytest.raises(ValueError):
        build_action_url("https://dataset.example", "verification", "short")


def test_relay_post_accepts_confirmed_response_and_rejects_non_sent_status(monkeypatch) -> None:
    service = AppsScriptEmailService(apps_script_settings())
    observed: dict[str, object] = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, size):
            observed["read_size"] = size
            return json.dumps({"status": observed.get("status", "sent")}).encode()

    def fake_urlopen(request: Request, timeout: float):
        observed["request"] = request
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr(email_service, "open_relay_request", fake_urlopen)
    payload = service._create_payload("password_reset", "person@example.com", "C" * 43)
    assert service._post(payload) is True
    request = observed["request"]
    assert isinstance(request, Request)
    assert request.get_method() == "POST"
    assert "Authorization" not in request.headers
    assert observed["timeout"] == 12.0
    assert observed["read_size"] == 8193
    observed["status"] = "quota_exhausted"
    assert service._post(payload) is False


@pytest.mark.asyncio
async def test_relay_timeout_is_failure_and_is_not_retried(monkeypatch) -> None:
    service = AppsScriptEmailService(apps_script_settings())
    calls = 0

    async def direct_call(function, *args):
        return function(*args)

    def timeout(_payload):
        nonlocal calls
        calls += 1
        raise TimeoutError("sensitive URL/token must not be logged")

    monkeypatch.setattr(service, "_post", timeout)
    monkeypatch.setattr(email_service.asyncio, "to_thread", direct_call)
    assert await service.send_verification_email("person@example.com", "D" * 43) is False
    assert calls == 1


@pytest.mark.asyncio
async def test_relay_wait_is_bounded_by_configured_deadline(monkeypatch) -> None:
    service = AppsScriptEmailService(apps_script_settings(apps_script_timeout_seconds=0.01))
    calls = 0

    async def delayed_call(_function, *_args):
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)

    monkeypatch.setattr(email_service.asyncio, "to_thread", delayed_call)
    assert await service.send_verification_email("person@example.com", "H" * 43) is False
    assert calls == 1


@pytest.mark.asyncio
async def test_smtp_provider_success_and_failure_are_reported(monkeypatch, caplog) -> None:
    settings = Settings(
        environment="testing",
        email_provider="smtp",
        smtp_host="smtp.example.net",
        smtp_user="user",
        smtp_password="secret",
        email_from="no-reply@example.net",
        application_base_url="https://dataset.example",
    )
    service = SMTPEmailService(settings)
    observed = {}

    async def direct_call(function, *args):
        return function(*args)

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            observed.update(host=host, port=port, timeout=timeout)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def starttls(self):
            observed["tls"] = True

        def login(self, user, password):
            observed["login"] = (user, password)

        def send_message(self, message):
            observed["message"] = message

    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_service.asyncio, "to_thread", direct_call)
    assert await service.send_verification_email("person@example.com", "F" * 43)
    assert "https://dataset.example/verify-email?token=" + "F" * 43 in observed["message"].get_content()
    assert observed["login"] == ("user", "secret")

    class FailedSMTP(FakeSMTP):
        def __enter__(self):
            raise OSError("server included recipient/token details")

    monkeypatch.setattr(email_service.smtplib, "SMTP", FailedSMTP)
    assert await service.send_password_reset_email("person@example.com", "G" * 43) is False
    assert "G" * 43 not in caplog.text
    assert "person@example.com" not in caplog.text


@pytest.mark.asyncio
async def test_mock_keeps_tokens_only_in_explicit_test_interface(caplog) -> None:
    service = MockEmailService("http://localhost:5173")
    token = "E" * 43
    assert await service.send_verification_email("person@example.com", token)
    assert service.sent_emails[0]["token"] == token
    assert "http://localhost:5173/verify-email?token=" + token == service.sent_emails[0]["action_url"]
    assert token not in caplog.text
    assert "person@example.com" not in caplog.text


def test_production_email_configuration_fails_closed() -> None:
    # These assertions cover fail-closed defaults, independent of a developer .env.
    with pytest.raises(ValueError, match="EMAIL_PROVIDER=mock"):
        Settings(
            environment="production",
            require_email_verification=True,
            _env_file=None,
        ).validate_email_configuration()
    with pytest.raises(ValueError, match="APPS_SCRIPT_URL"):
        Settings(
            environment="production",
            email_provider="apps_script",
            require_email_verification=True,
            _env_file=None,
        ).validate_email_configuration()
    valid = apps_script_settings(environment="production", require_email_verification=True)
    valid.validate_email_configuration()


def test_provider_factory_does_not_fall_back_to_mock_in_production(monkeypatch) -> None:
    email_service.reset_email_service_for_tests()
    monkeypatch.setattr(
        email_service,
        "get_settings",
        lambda: Settings(environment="production", email_provider="mock"),
    )
    with pytest.raises(RuntimeError, match="cannot select the mock"):
        email_service.get_email_service()
    email_service.reset_email_service_for_tests()
