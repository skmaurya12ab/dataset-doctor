"""Email providers for registration verification and password-reset workflows."""

import asyncio
from abc import ABC, abstractmethod
import hashlib
import hmac
import json
from email.message import EmailMessage
import re
import smtplib
import socket
import time
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.security import validate_email_format

logger = get_logger(__name__)

APPS_SCRIPT_RESPONSE_STATUSES = frozenset(
    {
        "sent",
        "duplicate_sent",
        "misconfigured",
        "expired",
        "invalid_request",
        "unauthorized",
        "busy",
        "cooldown",
        "daily_cap",
        "quota_exhausted",
        "relay_error",
        "delivery_unknown",
        "delivery_failed",
        "idempotency_conflict",
        "replay",
    }
)
APPS_SCRIPT_SUCCESS_STATUSES = frozenset({"sent", "duplicate_sent"})
APPS_SCRIPT_CLIENT_OUTCOMES = frozenset(
    {
        "timeout",
        "http_error",
        "url_error",
        "transport_error",
        "non_json_response",
        "unexpected_status",
        "response_too_large",
    }
)


class ContentServiceRedirectHandler(HTTPRedirectHandler):
    """Follow only Apps Script ContentService's documented HTTPS response host."""

    def redirect_request(self, request, fp, code, message, headers, new_url):
        try:
            destination = urlsplit(new_url)
            port = destination.port
        except ValueError:
            return None
        if (
            code not in {301, 302, 303}
            or destination.scheme != "https"
            or destination.hostname != "script.googleusercontent.com"
            or port not in {None, 443}
            or destination.username
            or destination.password
        ):
            return None
        return super().redirect_request(request, fp, code, message, headers, new_url)


def open_relay_request(request: Request, timeout: float):
    """Open the relay request with redirects restricted to Google's content host."""
    return build_opener(ContentServiceRedirectHandler()).open(request, timeout=timeout)


def build_action_url(base_url: str, message_type: str, token: str) -> str:
    """Build links for the frontend routes verified in App.tsx."""
    if message_type not in {"verification", "password_reset"}:
        raise ValueError("Unsupported authentication email type")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not base_url.isascii()
        or "\n" in base_url
        or "\r" in base_url
    ):
        raise ValueError("APPLICATION_BASE_URL must be an origin without credentials, query, or fragment")
    if len(base_url) > 2048:
        raise ValueError("APPLICATION_BASE_URL is too long")
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,256}", token):
        raise ValueError("Authentication email token is malformed")
    route = "/verify-email" if message_type == "verification" else "/reset-password"
    return f"{base_url.rstrip('/')}{route}?{urlencode({'token': token})}"


def canonical_relay_message(
    *,
    schema_version: int,
    timestamp: int,
    nonce: str,
    request_id: str,
    message_type: str,
    recipient: str,
    action_url: str,
) -> bytes:
    """Return the exact v1 UTF-8 bytes signed by both Python and Apps Script.

    Newline-separated fields have strict validation before this function is used;
    the version marker and fixed order prevent ambiguous concatenation.
    """
    fields = (
        "dataset-doctor-email-relay-v1",
        str(schema_version),
        str(timestamp),
        nonce,
        request_id,
        message_type,
        recipient,
        action_url,
    )
    if any("\n" in field or "\r" in field for field in fields):
        raise ValueError("Relay fields cannot contain line breaks")
    return "\n".join(fields).encode("utf-8")


class BaseEmailService(ABC):
    """Stable async interface consumed by authentication services."""

    @abstractmethod
    async def send_verification_email(self, to_email: str, token: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def send_password_reset_email(self, to_email: str, token: str) -> bool:
        raise NotImplementedError


class MockEmailService(BaseEmailService):
    """No-network provider whose in-memory records are reserved for tests."""

    def __init__(self, application_base_url: str):
        self.application_base_url = application_base_url
        # Tests may inspect these records; production configuration rejects mock.
        self.sent_emails: List[Dict[str, Any]] = []

    async def send_verification_email(self, to_email: str, token: str) -> bool:
        return self._record("verification", to_email, token)

    async def send_password_reset_email(self, to_email: str, token: str) -> bool:
        return self._record("password_reset", to_email, token)

    def _record(self, message_type: str, to_email: str, token: str) -> bool:
        self.sent_emails.append(
            {
                "type": message_type,
                "to": to_email,
                "token": token,
                "action_url": build_action_url(self.application_base_url, message_type, token),
            }
        )
        # Deliberately do not log addresses, links, tokens, or message contents.
        logger.info("Mock email provider recorded %s message for test use", message_type)
        return True

    def clear(self) -> None:
        self.sent_emails.clear()


class SMTPEmailService(BaseEmailService):
    """SMTP implementation retained for environments that provide a real relay."""

    def __init__(self, settings: Settings):
        self.host = settings.smtp_host or ""
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.use_tls = settings.smtp_tls
        self.sender = settings.email_from
        self.application_base_url = settings.application_base_url

    async def send_verification_email(self, to_email: str, token: str) -> bool:
        action_url = build_action_url(self.application_base_url, "verification", token)
        return await self._send(
            to_email,
            "Dataset Doctor — Verify Your Email Address",
            f"Hello,\n\nVerify your email address using this link:\n{action_url}\n\n"
            "This single-use link expires automatically.\n\n— The Dataset Doctor Team",
        )

    async def send_password_reset_email(self, to_email: str, token: str) -> bool:
        action_url = build_action_url(self.application_base_url, "password_reset", token)
        return await self._send(
            to_email,
            "Dataset Doctor — Password Reset Request",
            f"Hello,\n\nReset your Dataset Doctor password using this single-use link:\n"
            f"{action_url}\n\nThis single-use link expires automatically. If you did not request this, ignore this email.\n\n"
            "— The Dataset Doctor Team",
        )

    async def _send(self, to_email: str, subject: str, content: str) -> bool:
        return await asyncio.to_thread(self._send_smtp_message, to_email, subject, content)

    def _send_smtp_message(self, to_email: str, subject: str, content: str) -> bool:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.sender
        message["To"] = to_email
        message.set_content(content)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=10.0) as server:
                if self.use_tls:
                    server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.send_message(message)
            logger.info("SMTP accepted an authentication email")
            return True
        except Exception as exc:
            # SMTP exception strings can contain address or server data; keep logs generic.
            logger.warning("SMTP authentication email delivery failed (%s)", type(exc).__name__)
            return False


class AppsScriptEmailService(BaseEmailService):
    """Signed HTTPS client for the fixed-template Google Apps Script relay."""

    def __init__(self, settings: Settings):
        if not settings.apps_script_url or not settings.apps_script_hmac_secret:
            raise ValueError("Apps Script email configuration is incomplete")
        self.endpoint = settings.apps_script_url
        self.secret = settings.apps_script_hmac_secret.get_secret_value().encode("utf-8")
        self.timeout = settings.apps_script_timeout_seconds
        self.application_base_url = settings.application_base_url

    async def send_verification_email(self, to_email: str, token: str) -> bool:
        return await self._send("verification", to_email, token)

    async def send_password_reset_email(self, to_email: str, token: str) -> bool:
        return await self._send("password_reset", to_email, token)

    async def _send(self, message_type: str, to_email: str, token: str) -> bool:
        try:
            payload = self._create_payload(message_type, to_email, token)
            outcome = await asyncio.wait_for(
                asyncio.to_thread(self._post, payload),
                timeout=self.timeout,
            )
        except TimeoutError:
            outcome = "timeout"
        except Exception:
            outcome = "relay_error"

        if not isinstance(outcome, str) or outcome not in (
            APPS_SCRIPT_RESPONSE_STATUSES | APPS_SCRIPT_CLIENT_OUTCOMES
        ):
            outcome = "unexpected_status"
        if outcome in APPS_SCRIPT_SUCCESS_STATUSES:
            logger.info("Apps Script relay delivery status=%s", outcome)
            return True
        logger.warning("Apps Script relay delivery status=%s", outcome)
        return False

    def _create_payload(self, message_type: str, to_email: str, token: str) -> Dict[str, Any]:
        if message_type not in {"verification", "password_reset"}:
            raise ValueError("Unsupported authentication email type")
        recipient = to_email.strip().lower()
        if len(recipient) > 254 or not recipient.isascii() or not validate_email_format(recipient):
            raise ValueError("Invalid email recipient")
        action_url = build_action_url(self.application_base_url, message_type, token)
        if len(action_url.encode("utf-8")) > 2048:
            raise ValueError("Authentication action URL is too long")
        timestamp = int(time.time())
        nonce = uuid.uuid4().hex
        request_id = str(uuid.uuid4())
        canonical = canonical_relay_message(
            schema_version=1,
            timestamp=timestamp,
            nonce=nonce,
            request_id=request_id,
            message_type=message_type,
            recipient=recipient,
            action_url=action_url,
        )
        signature = hmac.new(self.secret, canonical, hashlib.sha256).hexdigest()
        return {
            "schema_version": 1,
            "timestamp": timestamp,
            "nonce": nonce,
            "request_id": request_id,
            "message_type": message_type,
            "recipient": recipient,
            "action_url": action_url,
            "signature": signature,
        }

    def _post(self, payload: Dict[str, Any]) -> str:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(body) > 8192:
            return "invalid_request"
        request = Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            # urllib follows the documented ContentService one-time googleusercontent redirect.
            with open_relay_request(request, timeout=self.timeout) as response:
                status_code = getattr(response, "status", None)
                if not isinstance(status_code, int) or not 200 <= status_code < 300:
                    return "http_error"
                response_bytes = response.read(8193)
        except HTTPError:
            return "http_error"
        except (TimeoutError, socket.timeout):
            return "timeout"
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                return "timeout"
            return "url_error"
        except OSError:
            return "transport_error"
        if len(response_bytes) > 8192:
            return "response_too_large"
        try:
            result = json.loads(response_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "non_json_response"
        if not isinstance(result, dict):
            return "unexpected_status"
        relay_status = result.get("status")
        if not isinstance(relay_status, str) or relay_status not in APPS_SCRIPT_RESPONSE_STATUSES:
            return "unexpected_status"
        return relay_status


_global_email_service: Optional[BaseEmailService] = None


def get_email_service() -> BaseEmailService:
    """Resolve the explicitly configured email provider as a process singleton."""
    global _global_email_service
    if _global_email_service is None:
        settings = get_settings()
        if settings.email_provider == "mock":
            if settings.is_production:
                raise RuntimeError("Production cannot select the mock email provider")
            _global_email_service = MockEmailService(settings.application_base_url)
        elif settings.email_provider == "smtp":
            _global_email_service = SMTPEmailService(settings)
        elif settings.email_provider == "apps_script":
            _global_email_service = AppsScriptEmailService(settings)
        else:  # Guard future enum changes; never silently use mock.
            raise RuntimeError("No supported email provider is configured")
    return _global_email_service


def reset_email_service_for_tests() -> None:
    """Clear provider singleton for tests that change settings or inject providers."""
    global _global_email_service
    _global_email_service = None
