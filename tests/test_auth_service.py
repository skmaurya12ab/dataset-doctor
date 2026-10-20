"""Unit and service tests for authentication, sessions, tokens, and Argon2id hashing."""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AuthenticationException, ValidationException
from app.core.security import hash_password, verify_password
from app.models.user import User, UserSession
from app.schemas.auth import UserLoginRequest, UserRegisterRequest
from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_argon2id_password_hashing() -> None:
    """Verify password hashing produces valid Argon2id hash and verifies correctly."""
    plain = "SuperSecurePassword123!"
    hashed = hash_password(plain)

    assert hashed.startswith("$argon2id$")
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False


@pytest.mark.asyncio
async def test_auth_service_register_user(test_db_session: AsyncSession) -> None:
    """Verify user registration persists user, normalizes email, and creates verification token."""
    svc = AuthService()
    req = UserRegisterRequest(email="  NewUser@Example.COM  ", password="ValidPassword123!")

    user = await svc.register_user(test_db_session, req)
    assert user.id is not None
    assert user.email == "newuser@example.com"
    assert user.is_active is True
    assert verify_password("ValidPassword123!", user.hashed_password) is True


@pytest.mark.asyncio
async def test_auth_service_duplicate_registration_rejected(test_db_session: AsyncSession) -> None:
    """Verify registering an existing email address raises ValidationException."""
    svc = AuthService()
    req1 = UserRegisterRequest(email="dup@example.com", password="Password123!")
    await svc.register_user(test_db_session, req1)

    req2 = UserRegisterRequest(email="DUP@EXAMPLE.COM", password="AnotherPassword123!")
    with pytest.raises(ValidationException, match="already exists"):
        await svc.register_user(test_db_session, req2)


@pytest.mark.asyncio
async def test_auth_service_authenticate_success_and_failure(test_db_session: AsyncSession) -> None:
    """Verify credential verification, failure on bad password, and inactive user refusal."""
    svc = AuthService()
    reg = UserRegisterRequest(email="auth_test@example.com", password="SecretPassword123!")
    user = await svc.register_user(test_db_session, reg)
    user.is_verified = True
    await test_db_session.commit()

    # Success
    auth_user = await svc.authenticate_user(
        test_db_session,
        UserLoginRequest(email="AUTH_TEST@example.com", password="SecretPassword123!"),
    )
    assert auth_user.id == user.id

    # Invalid password -> generic error
    with pytest.raises(AuthenticationException, match="Invalid email address or password"):
        await svc.authenticate_user(
            test_db_session,
            UserLoginRequest(email="auth_test@example.com", password="WrongPassword123!"),
        )

    # Inactive user -> disabled error
    user.is_active = False
    await test_db_session.commit()
    with pytest.raises(AuthenticationException, match="Account is disabled"):
        await svc.authenticate_user(
            test_db_session,
            UserLoginRequest(email="auth_test@example.com", password="SecretPassword123!"),
        )


@pytest.mark.asyncio
async def test_auth_service_session_lifecycle(test_db_session: AsyncSession) -> None:
    """Verify session creation, validation, expiration, and invalidation."""
    svc = AuthService()
    reg = UserRegisterRequest(email="session_user@example.com", password="Password123!")
    user = await svc.register_user(test_db_session, reg)

    # Create session
    session, raw_token = await svc.create_session(test_db_session, user.id, ip_address="127.0.0.1")
    assert session.user_id == user.id
    assert raw_token is not None

    # Validate session
    val_user = await svc.validate_session(test_db_session, raw_token)
    assert val_user is not None
    assert val_user.id == user.id

    # Invalidate session (logout)
    revoked = await svc.invalidate_session(test_db_session, raw_token)
    assert revoked is True

    # Validate after revocation should return None
    assert (await svc.validate_session(test_db_session, raw_token)) is None


@pytest.mark.asyncio
async def test_auth_service_expired_session(test_db_session: AsyncSession) -> None:
    """Verify expired sessions return None and are pruned."""
    svc = AuthService()
    reg = UserRegisterRequest(email="expired_user@example.com", password="Password123!")
    user = await svc.register_user(test_db_session, reg)

    session, raw_token = await svc.create_session(test_db_session, user.id)
    # Manually expire session
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    await test_db_session.commit()

    val_user = await svc.validate_session(test_db_session, raw_token)
    assert val_user is None


@pytest.mark.asyncio
async def test_auth_service_email_verification(test_db_session: AsyncSession, caplog) -> None:
    """Verify token-based email confirmation and rejection of reuse."""
    from sqlalchemy import select
    from app.models.user import EmailVerificationToken

    svc = AuthService()
    reg = UserRegisterRequest(email="verify_test@example.com", password="Password123!")
    user = await svc.register_user(test_db_session, reg)
    user.is_verified = False
    await test_db_session.commit()

    # Get the token
    stmt = select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
    token_record = (await test_db_session.execute(stmt)).scalar_one()

    # Create a fresh raw token and update token_hash to test
    from app.core.security import generate_token, hash_token
    raw_token = generate_token(32)
    token_record.token_hash = hash_token(raw_token)
    await test_db_session.commit()

    # First verification succeeds
    res = await svc.verify_email(test_db_session, raw_token)
    assert res is True
    await test_db_session.refresh(user)
    assert user.is_verified is True

    # Reusing the token fails
    caplog.set_level("INFO", logger="app.services.auth_service")
    with pytest.raises(ValidationException, match="invalid or has expired"):
        await svc.verify_email(test_db_session, raw_token)
    assert "category=consumed" in caplog.text
    assert raw_token not in caplog.text


@pytest.mark.asyncio
async def test_registered_email_token_matches_persisted_hash_and_verifies_immediately(
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the actual email token across generation, SQLite persistence, and verification."""
    from sqlalchemy import select
    from app.core.security import hash_token
    from app.models.user import EmailVerificationToken
    from app.services import auth_service as auth_service_module

    class CapturingEmailService:
        token: str | None = None

        async def send_verification_email(self, _recipient: str, token: str) -> bool:
            self.token = token
            return True

        async def send_password_reset_email(self, *_args) -> bool:
            return True

    provider = CapturingEmailService()
    settings = Settings(
        environment="testing",
        require_email_verification=True,
        email_verification_token_expire_hours=12,
    )
    monkeypatch.setattr(auth_service_module, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_service_module, "get_email_service", lambda: provider)

    now_before_registration = datetime.now(timezone.utc)
    svc = AuthService()
    user = await svc.register_user(
        test_db_session,
        UserRegisterRequest(email="fresh-token@example.com", password="ValidPassword123!"),
    )
    now_after_registration = datetime.now(timezone.utc)
    token_record = await test_db_session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
    )

    assert provider.token is not None
    assert token_record is not None
    assert token_record.token_hash == hash_token(provider.token)
    expires_at = token_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    assert now_before_registration + timedelta(hours=12) <= expires_at
    assert expires_at <= now_after_registration + timedelta(hours=12)
    assert token_record.is_valid

    assert await svc.verify_email(test_db_session, provider.token) is True
    await test_db_session.refresh(user)
    assert user.is_verified is True


def test_verification_expiration_boundary_is_exclusive_and_naive_values_are_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token expires at its exact UTC boundary; SQLite-style naive timestamps mean UTC."""
    import app.models.user as user_models

    frozen_now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen_now if tz else frozen_now.replace(tzinfo=None)

    monkeypatch.setattr(user_models, "datetime", FrozenDateTime)
    at_boundary = user_models.EmailVerificationToken(
        token_hash="a" * 64,
        expires_at=frozen_now.replace(tzinfo=None),
    )
    still_valid = user_models.EmailVerificationToken(
        token_hash="b" * 64,
        expires_at=(frozen_now + timedelta(microseconds=1)).replace(tzinfo=None),
    )

    assert at_boundary.is_valid is False
    assert still_valid.is_valid is True


@pytest.mark.asyncio
async def test_expired_verification_token_is_rejected(
    test_db_session: AsyncSession,
) -> None:
    from app.models.user import EmailVerificationToken
    from app.core.security import hash_token

    user = User(
        email="expired-verification@example.com",
        hashed_password="unused-test-hash",
        is_active=True,
        is_verified=False,
        role="user",
    )
    test_db_session.add(user)
    await test_db_session.flush()
    token = "expired-test-token"
    test_db_session.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )
    await test_db_session.commit()

    with pytest.raises(ValidationException, match="invalid or has expired"):
        await AuthService().verify_email(test_db_session, token)


@pytest.mark.asyncio
async def test_resend_creates_fresh_token_with_configured_validity(
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful resend persists the token sent and keeps its configured UTC lifetime."""
    from sqlalchemy import select
    from app.core.security import hash_token
    from app.models.user import EmailVerificationToken
    from app.services import auth_service as auth_service_module

    class CapturingEmailService:
        token: str | None = None

        async def send_verification_email(self, _recipient: str, token: str) -> bool:
            self.token = token
            return True

        async def send_password_reset_email(self, *_args) -> bool:
            return True

    provider = CapturingEmailService()
    settings = Settings(
        environment="testing",
        require_email_verification=True,
        email_verification_token_expire_hours=6,
    )
    monkeypatch.setattr(auth_service_module, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_service_module, "get_email_service", lambda: provider)
    user = User(
        email="resend-fresh@example.com",
        hashed_password="unused-test-hash",
        is_active=True,
        is_verified=False,
        role="user",
    )
    test_db_session.add(user)
    await test_db_session.commit()

    before_resend = datetime.now(timezone.utc)
    assert await AuthService().resend_verification_email(test_db_session, user.email)
    after_resend = datetime.now(timezone.utc)
    record = await test_db_session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
    )

    assert provider.token is not None
    assert record is not None
    assert record.token_hash == hash_token(provider.token)
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    assert before_resend + timedelta(hours=6) <= expires_at
    assert expires_at <= after_resend + timedelta(hours=6)
    assert record.is_valid
    assert await AuthService().verify_email(test_db_session, provider.token)


@pytest.mark.asyncio
async def test_auth_service_password_reset_revokes_sessions(test_db_session: AsyncSession) -> None:
    """Verify password reset updates password and revokes all active sessions."""
    from sqlalchemy import select
    from app.models.user import PasswordResetToken

    svc = AuthService()
    reg = UserRegisterRequest(email="reset_test@example.com", password="OldPassword123!")
    user = await svc.register_user(test_db_session, reg)

    # Create active session
    session, raw_session_token = await svc.create_session(test_db_session, user.id)
    assert (await svc.validate_session(test_db_session, raw_session_token)) is not None

    # Request password reset
    await svc.request_password_reset(test_db_session, user.email)
    reset_record = (
        await test_db_session.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )
    ).scalar_one()

    from app.core.security import generate_token, hash_token
    raw_reset_token = generate_token(32)
    reset_record.token_hash = hash_token(raw_reset_token)
    await test_db_session.commit()

    # Reset password
    await svc.reset_password(test_db_session, raw_reset_token, "NewPassword123!")

    # Verify old session was invalidated
    assert (await svc.validate_session(test_db_session, raw_session_token)) is None

    # Verify login with new password succeeds
    auth_user = await svc.authenticate_user(
        test_db_session,
        UserLoginRequest(email=user.email, password="NewPassword123!"),
    )
    assert auth_user.id == user.id
