"""Unit tests for secure authentication email providers and configuration."""

import asyncio
import hashlib
import hmac
import io
import json
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError
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
    assert handler.redirect_request(
        request, None, 302, "Found", {}, "https://script.googleusercontent.com:443/macros/echo?key=one-time"
    ) is not None
    assert handler.redirect_request(
        request, None, 302, "Found", {}, "https://script.googleusercontent.com:444/macros/echo?key=one-time"
    ) is None
    assert handler.redirect_request(
        request, None, 307, "Temporary Redirect", {}, "https://script.googleusercontent.com/macros/echo?key=one-time"
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


@pytest.mark.parametrize(
    "base_url",
    [
        "https://dataset.example ",
        "https://data set.example",
        "https://dataset.example?",
        "https://dataset.example#",
        "https://dataset.example:not-a-port",
        "https://dataset.example:70000",
    ],
)
def test_action_url_builder_rejects_whitespace_delimiters_and_invalid_ports(base_url: str) -> None:
    with pytest.raises(ValueError, match="APPLICATION_BASE_URL"):
        build_action_url(base_url, "verification", "A" * 43)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://dataset.example ",
        "https://data set.example",
        "https://dataset.example?",
        "https://dataset.example#",
        "https://dataset.example:not-a-port",
        "https://dataset.example:70000",
    ],
)
def test_email_configuration_rejects_ambiguous_application_origins(base_url: str) -> None:
    settings = Settings(application_base_url=base_url, _env_file=None)
    with pytest.raises(ValueError, match="APPLICATION_BASE_URL"):
        settings.validate_email_configuration()


@pytest.mark.parametrize("message_type", ["verification", "password_reset"])
def test_python_generated_action_urls_pass_apps_script_validator_offline(message_type: str) -> None:
    service = AppsScriptEmailService(apps_script_settings())
    payload = service._create_payload(message_type, "person@example.com", "A_" + "B" * 40 + "_")
    node_script = r"""
      const fs = require('node:fs')
      const vm = require('node:vm')
      // Apps Script V8 does not expose browser URL or URLSearchParams globals.
      const context = vm.createContext({ Math, Number, Object, Array, String, JSON, RegExp, isFinite })
      vm.runInContext(fs.readFileSync('integrations/apps-script-email-relay/Code.gs', 'utf8'), context)
      let input = ''
      process.stdin.setEncoding('utf8')
      process.stdin.on('data', chunk => { input += chunk })
      process.stdin.on('end', () => {
        const payload = JSON.parse(input)
        const reason = context.actionUrlValidationReason_(
          payload.action_url,
          payload.configured_base,
          payload.message_type,
        )
        process.stdout.write(reason === null ? 'valid' : String(reason))
      })
    """
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["node", "-e", node_script],
        cwd=project_root,
        input=json.dumps(
            {
                "action_url": payload["action_url"],
                "configured_base": "https://dataset.example",
                "message_type": payload["message_type"],
            }
        ),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, "Apps Script URL validator test harness failed"
    assert result.stdout == "valid", "Python-generated action URL was rejected by the Apps Script-compatible parser"


@pytest.mark.parametrize(
    ("reason", "logged_reason"),
    [
        ("origin_mismatch", "origin_mismatch"),
        ("untrusted-provider-value", "unrecognized_reason"),
    ],
)
def test_relay_logs_only_allowlisted_action_url_reason(
    monkeypatch, caplog, reason: str, logged_reason: str
) -> None:
    service = AppsScriptEmailService(apps_script_settings())
    payload = service._create_payload("verification", "person@example.com", "C" * 43)

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size):
            return json.dumps({"status": "invalid_action_url", "reason": reason}).encode()

    monkeypatch.setattr(email_service, "open_relay_request", lambda *_args, **_kwargs: Response())

    assert service._post(payload) == "invalid_action_url"
    expected = f"Apps Script relay validation status=invalid_action_url reason={logged_reason}"
    assert any(record.getMessage() == expected for record in caplog.records)
    if reason != logged_reason:
        assert all(reason not in record.getMessage() for record in caplog.records)


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
    assert service._post(payload) == "sent"
    request = observed["request"]
    assert isinstance(request, Request)
    assert request.get_method() == "POST"
    assert "Authorization" not in request.headers
    assert observed["timeout"] == 12.0
    assert observed["read_size"] == 8193
    observed["status"] = "quota_exhausted"
    assert service._post(payload) == "quota_exhausted"


@pytest.mark.parametrize(
    ("response_body", "expected"),
    [
        (b'{"status":"duplicate_sent"}', "duplicate_sent"),
        (b'{"status":"unauthorized"}', "unauthorized"),
        (b'{"status":"invalid_envelope"}', "invalid_envelope"),
        (b'{"status":"body_too_large"}', "body_too_large"),
        (b'{"status":"invalid_json"}', "invalid_json"),
        (b'{"status":"invalid_payload"}', "invalid_payload"),
        (b'{"status":"invalid_recipient"}', "invalid_recipient"),
        (b'{"status":"invalid_action_url"}', "invalid_action_url"),
        (b'{"status":"status-from-untrusted-response"}', "unexpected_status"),
        (b'{"unexpected":"shape"}', "unexpected_status"),
        (b'not-json', "non_json_response"),
        (b'{"status":"sent"}' + b" " * 8190, "response_too_large"),
    ],
)
def test_relay_post_classifies_responses_without_preserving_unknown_status(
    monkeypatch, response_body: bytes, expected: str
) -> None:
    service = AppsScriptEmailService(apps_script_settings())
    payload = service._create_payload("verification", "person@example.com", "J" * 43)

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size):
            return response_body

    monkeypatch.setattr(email_service, "open_relay_request", lambda *_args, **_kwargs: Response())

    assert service._post(payload) == expected


@pytest.mark.parametrize(
    ("error_factory", "expected"),
    [
        (lambda: HTTPError("https://relay.example/exec", 503, "private failure", {}, io.BytesIO(b"private body")), "http_error"),
        (lambda: URLError("private URL detail"), "url_error"),
        (lambda: URLError(TimeoutError("private timeout detail")), "timeout"),
        (lambda: TimeoutError("private timeout detail"), "timeout"),
        (lambda: OSError("private transport detail"), "transport_error"),
    ],
)
def test_relay_post_classifies_transport_errors_without_logging_details(
    monkeypatch, error_factory, expected: str
) -> None:
    service = AppsScriptEmailService(apps_script_settings())
    payload = service._create_payload("verification", "person@example.com", "K" * 43)

    def fail_request(*_args, **_kwargs):
        raise error_factory()

    monkeypatch.setattr(email_service, "open_relay_request", fail_request)

    assert service._post(payload) == expected


@pytest.mark.asyncio
async def test_relay_logs_only_whitelisted_status_and_never_response_fields(monkeypatch, caplog) -> None:
    service = AppsScriptEmailService(apps_script_settings())
    sensitive_values = [
        "relay-private-recipient@example.invalid",
        "https://dataset.example/verify-email?token=relay-private-token",
        "relay-private-signature",
        "relay-private-response-body",
    ]
    body = json.dumps(
        {
            "status": "unauthorized",
            "recipient": sensitive_values[0],
            "action_url": sensitive_values[1],
            "signature": sensitive_values[2],
            "message": sensitive_values[3],
        }
    ).encode()

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size):
            return body

    async def direct_call(function, *args):
        return function(*args)

    monkeypatch.setattr(email_service, "open_relay_request", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(email_service.asyncio, "to_thread", direct_call)

    assert await service.send_verification_email("person@example.com", "L" * 43) is False
    assert "status=unauthorized" in caplog.text
    for value in sensitive_values:
        assert value not in caplog.text
    assert body.decode() not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response_body", "expected_outcome", "private_text"),
    [
        (b'{"status":"provider-secret-status"}', "unexpected_status", "provider-secret-status"),
        (b"private non-json recipient body", "non_json_response", "private non-json recipient body"),
    ],
)
async def test_relay_normalizes_unknown_and_non_json_response_logs(
    monkeypatch, caplog, response_body: bytes, expected_outcome: str, private_text: str
) -> None:
    service = AppsScriptEmailService(apps_script_settings())

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size):
            return response_body

    async def direct_call(function, *args):
        return function(*args)

    monkeypatch.setattr(email_service, "open_relay_request", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(email_service.asyncio, "to_thread", direct_call)

    assert await service.send_verification_email("person@example.com", "N" * 43) is False
    assert f"status={expected_outcome}" in caplog.text
    assert private_text not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("relay_status", "expected"),
    [
        ("sent", True),
        ("duplicate_sent", True),
        ("delivery_unknown", False),
        ("unexpected_status", False),
        ("invalid_envelope", False),
        ("body_too_large", False),
        ("invalid_json", False),
        ("invalid_payload", False),
        ("invalid_recipient", False),
        ("invalid_action_url", False),
    ],
)
async def test_relay_reports_success_only_for_confirmed_sent_statuses(
    monkeypatch, relay_status: str, expected: bool
) -> None:
    service = AppsScriptEmailService(apps_script_settings())

    async def direct_call(function, *args):
        return function(*args)

    monkeypatch.setattr(service, "_post", lambda _payload: relay_status)
    monkeypatch.setattr(email_service.asyncio, "to_thread", direct_call)

    assert await service.send_verification_email("person@example.com", "M" * 43) is expected


@pytest.mark.asyncio
async def test_relay_timeout_is_failure_and_is_not_retried(monkeypatch, caplog) -> None:
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
    assert "status=timeout" in caplog.text
    assert "sensitive URL/token must not be logged" not in caplog.text


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
