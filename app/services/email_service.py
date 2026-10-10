"""Email delivery abstraction and implementations for authentication workflows."""

from abc import ABC, abstractmethod
from email.message import EmailMessage
import smtplib
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class BaseEmailService(ABC):
    """Abstract interface defining required email delivery contracts."""

    @abstractmethod
    async def send_verification_email(self, to_email: str, token: str) -> bool:
        """Send account email address verification link with one-time token."""
        pass

    @abstractmethod
    async def send_password_reset_email(self, to_email: str, token: str) -> bool:
        """Send password reset link with single-use expiring token."""
        pass


class MockEmailService(BaseEmailService):
    """In-memory test and local development email delivery implementation.

    Records outgoing emails in memory for test assertions and logs tokens to console.
    """

    def __init__(self):
        self.sent_emails: List[Dict[str, Any]] = []

    async def send_verification_email(self, to_email: str, token: str) -> bool:
        record = {
            "type": "verification",
            "to": to_email,
            "token": token,
        }
        self.sent_emails.append(record)
        logger.info("[MockEmailService] Verification email sent to %s with token: %s", to_email, token)
        return True

    async def send_password_reset_email(self, to_email: str, token: str) -> bool:
        record = {
            "type": "password_reset",
            "to": to_email,
            "token": token,
        }
        self.sent_emails.append(record)
        logger.info("[MockEmailService] Password reset email sent to %s with token: %s", to_email, token)
        return True

    def clear(self) -> None:
        self.sent_emails.clear()


class SMTPEmailService(BaseEmailService):
    """Standard SMTP email delivery implementation for production environments."""

    def __init__(
        self,
        host: str,
        port: int = 587,
        user: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = True,
        sender: str = "noreply@datasetdoctor.local",
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_tls = use_tls
        self.sender = sender

    async def send_verification_email(self, to_email: str, token: str) -> bool:
        subject = "Dataset Doctor — Verify Your Email Address"
        body = (
            f"Hello,\n\n"
            f"Please verify your email address for Dataset Doctor using the following verification token:\n\n"
            f"{token}\n\n"
            f"This token is valid for 24 hours.\n\n"
            f"— The Dataset Doctor Team"
        )
        return self._send_smtp_message(to_email, subject, body)

    async def send_password_reset_email(self, to_email: str, token: str) -> bool:
        subject = "Dataset Doctor — Password Reset Request"
        body = (
            f"Hello,\n\n"
            f"A password reset was requested for your Dataset Doctor account. "
            f"Use the following single-use token to reset your password:\n\n"
            f"{token}\n\n"
            f"This token expires in 1 hour. If you did not request this, please ignore this email.\n\n"
            f"— The Dataset Doctor Team"
        )
        return self._send_smtp_message(to_email, subject, body)

    def _send_smtp_message(self, to_email: str, subject: str, content: str) -> bool:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = to_email
        msg.set_content(content)

        try:
            with smtplib.SMTP(self.host, self.port, timeout=10.0) as server:
                if self.use_tls:
                    server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.send_message(msg)
            logger.info("Successfully dispatched email to %s via SMTP %s", to_email, self.host)
            return True
        except Exception as exc:
            logger.error("Failed to deliver email to %s via SMTP: %s", to_email, str(exc))
            return False


_global_email_service: Optional[BaseEmailService] = None


def get_email_service() -> BaseEmailService:
    """Dependency provider resolving active email delivery service singleton."""
    global _global_email_service
    if _global_email_service is None:
        settings = get_settings()
        if settings.smtp_host:
            _global_email_service = SMTPEmailService(
                host=settings.smtp_host,
                port=settings.smtp_port,
                user=settings.smtp_user,
                password=settings.smtp_password,
                use_tls=settings.smtp_tls,
                sender=settings.email_from,
            )
        else:
            _global_email_service = MockEmailService()
    return _global_email_service
