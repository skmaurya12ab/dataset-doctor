"""Authentication and session management business logic service."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import uuid
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import AuthenticationException, EmailDeliveryException, ValidationException
from app.core.logging import get_logger
from app.core.security import generate_token, hash_password, hash_token, normalize_email, verify_password
from app.models.user import EmailVerificationToken, PasswordResetToken, User, UserSession
from app.schemas.auth import UserLoginRequest, UserRegisterRequest
from app.services.email_service import get_email_service
from app.services.email_limits import reserve_email_delivery

logger = get_logger(__name__)


class AuthService:
    """Coordinates user registration, credentials authentication, session security, and token lifecycles."""

    async def register_user(self, db: AsyncSession, req: UserRegisterRequest) -> User:
        """Register a new user account with Argon2id password hashing and issue verification token."""
        clean_email = normalize_email(req.email)

        # 1. Check for existing account
        existing_stmt = select(User).where(User.email == clean_email)
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            raise ValidationException("An account with this email address already exists.")

        # 2. Hash password with Argon2id
        hashed_pw = hash_password(req.password)

        settings = get_settings()
        user = User(
            id=uuid.uuid4(),
            email=clean_email,
            hashed_password=hashed_pw,
            is_active=True,
            # In testing or when verification is explicitly disabled, auto-verify
            is_verified=not settings.require_email_verification,
            role="user",
        )
        db.add(user)
        await db.flush()

        # 3. Create email verification token
        raw_verify_token = generate_token(32)
        verify_token_hash = hash_token(raw_verify_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.email_verification_token_expire_hours)

        token_record = EmailVerificationToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=verify_token_hash,
            expires_at=expires_at,
        )
        db.add(token_record)
        await db.commit()

        # 4. Dispatch verification email
        email_reserved = await self._reserve_email(db, user.id, "verification")
        if email_reserved:
            delivered = await get_email_service().send_verification_email(clean_email, raw_verify_token)
        else:
            delivered = False
        if not delivered:
            if settings.require_email_verification:
                if email_reserved:
                    # Delivery may have succeeded before its acknowledgement was lost.
                    # Keep the hashed token so a message that did arrive remains usable.
                    logger.warning("Registration email delivery was not confirmed; verification token retained")
                else:
                    await db.delete(token_record)
                    await db.commit()
                    logger.warning("Registration email was not attempted; verification token removed")
                raise EmailDeliveryException()
            await db.delete(token_record)
            await db.commit()

        logger.info("Registered new user (id: %s)", user.id)
        return user

    async def authenticate_user(self, db: AsyncSession, req: UserLoginRequest) -> User:
        """Verify user credentials and check active account status."""
        clean_email = normalize_email(req.email)

        stmt = select(User).where(User.email == clean_email)
        user = (await db.execute(stmt)).scalar_one_or_none()

        if not user or not verify_password(req.password, user.hashed_password):
            # Generic non-disclosing error message prevents user enumeration
            raise AuthenticationException("Invalid email address or password.")

        if not user.is_active:
            raise AuthenticationException("Account is disabled. Please contact support.")

        settings = get_settings()
        if settings.require_email_verification and not user.is_verified:
            raise AuthenticationException("Please verify your email address before logging in.")

        return user

    async def create_session(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[UserSession, str]:
        """Create a server-side session, rotate old sessions, and return (session, raw_token)."""
        settings = get_settings()
        raw_token = generate_token(32)
        token_hash = hash_token(raw_token)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=settings.session_max_age_seconds)

        # Clean up already-expired sessions for this user to bound storage
        cleanup_stmt = delete(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.expires_at <= now,
        )
        await db.execute(cleanup_stmt)

        session = UserSession(
            id=uuid.uuid4(),
            user_id=user_id,
            session_token_hash=token_hash,
            ip_address=ip_address[:45] if ip_address else None,
            user_agent=user_agent[:512] if user_agent else None,
            expires_at=expires_at,
            created_at=now,
            last_active_at=now,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

        return session, raw_token

    async def validate_session(self, db: AsyncSession, raw_token: str) -> Optional[User]:
        """Validate raw session token and return the active User entity, or None if invalid/expired."""
        if not raw_token:
            return None

        token_hash = hash_token(raw_token)
        stmt = (
            select(UserSession)
            .options(selectinload(UserSession.user))
            .where(UserSession.session_token_hash == token_hash)
        )
        session = (await db.execute(stmt)).scalar_one_or_none()

        if not session:
            return None

        if session.is_expired:
            await db.delete(session)
            await db.commit()
            return None

        user = session.user
        if not user or not user.is_active:
            return None

        # Update last active timestamp
        session.last_active_at = datetime.now(timezone.utc)
        await db.commit()

        return user

    async def invalidate_session(self, db: AsyncSession, raw_token: str) -> bool:
        """Revoke a session on user logout."""
        if not raw_token:
            return False

        token_hash = hash_token(raw_token)
        stmt = delete(UserSession).where(UserSession.session_token_hash == token_hash)
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0

    async def verify_email(self, db: AsyncSession, token_str: str) -> bool:
        """Validate one-time verification token and mark user account as verified."""
        if not token_str:
            raise ValidationException("Verification token is required.")

        token_hash = hash_token(token_str)
        stmt = (
            select(EmailVerificationToken)
            .options(selectinload(EmailVerificationToken.user))
            .where(EmailVerificationToken.token_hash == token_hash)
            .with_for_update()
        )
        token_record = (await db.execute(stmt)).scalar_one_or_none()

        if not token_record:
            logger.info("Email verification token rejected category=not_found_or_invalidated")
            raise ValidationException("Verification token is invalid or has expired.")
        if token_record.used_at is not None:
            logger.info("Email verification token rejected category=consumed")
            raise ValidationException("Verification token is invalid or has expired.")
        expires_at = token_record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = expires_at.astimezone(timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            logger.info("Email verification token rejected category=expired")
            raise ValidationException("Verification token is invalid or has expired.")
        if token_record.user is None:
            logger.info("Email verification token rejected category=account_missing")
            raise ValidationException("Verification token is invalid or has expired.")

        token_record.used_at = datetime.now(timezone.utc)
        token_record.user.is_verified = True
        await db.commit()

        logger.info("Email verification completed")
        return True

    async def resend_verification_email(self, db: AsyncSession, email: str) -> bool:
        """Issue a fresh verification email token and dispatch email.

        Always returns True to prevent user enumeration.
        """
        clean_email = normalize_email(email)
        stmt = select(User).where(User.email == clean_email)
        user = (await db.execute(stmt)).scalar_one_or_none()

        if not user or not user.is_active or user.is_verified:
            logger.info("Resend verification request ignored for non-verifiable account")
            return True

        settings = get_settings()
        raw_token = generate_token(32)
        token_hash = hash_token(raw_token)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=settings.email_verification_token_expire_hours)

        # Prune expired unused tokens before creating another candidate, while
        # preserving every still-valid link until a new delivery is confirmed.
        await db.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.expires_at <= now,
            )
        )

        record = EmailVerificationToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(record)
        await db.commit()

        if not await self._reserve_email(db, user.id, "verification"):
            await db.delete(record)
            await db.commit()
            logger.info("Verification email resend not sent because delivery limits were reached")
            return False

        delivered = await get_email_service().send_verification_email(clean_email, raw_token)
        if not delivered:
            # The provider may have accepted the message but lost the response.
            # Keep this token alongside prior valid tokens; a later successful
            # resend or verification consumes/invalidates the remaining links.
            logger.warning("Verification email delivery was not confirmed; token retained")
            return False

        await db.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.id != record.id,
            )
        )
        await db.commit()
        return True

    async def request_password_reset(self, db: AsyncSession, email: str) -> bool:
        """Issue password reset token and dispatch email.

        Always returns True to prevent account enumeration.
        """
        clean_email = normalize_email(email)
        stmt = select(User).where(User.email == clean_email)
        user = (await db.execute(stmt)).scalar_one_or_none()

        if not user or not user.is_active:
            # Non-disclosing behavior: pretend email was sent
            logger.info("Password reset requested for nonexistent or inactive user: %s", clean_email)
            return True

        settings = get_settings()
        raw_token = generate_token(32)
        token_hash = hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.password_reset_token_expire_hours)

        reset_token = PasswordResetToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(reset_token)
        await db.commit()

        if not await self._reserve_email(db, user.id, "password_reset"):
            delivered = False
        else:
            delivered = await get_email_service().send_password_reset_email(clean_email, raw_token)
        if not delivered:
            await db.delete(reset_token)
            await db.commit()
            logger.warning("Password-reset email delivery did not complete")
            return False

        await db.execute(
            delete(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.id != reset_token.id,
            )
        )
        await db.commit()
        return True

    async def _reserve_email(self, db: AsyncSession, user_id: uuid.UUID, message_type: str) -> bool:
        """Reserve global and per-account limits before contacting a provider."""
        return await reserve_email_delivery(
            db,
            user_id=user_id,
            message_type=message_type,
            settings=get_settings(),
        )

    async def reset_password(self, db: AsyncSession, token_str: str, new_password: str) -> bool:
        """Validate reset token, update password hash, and revoke all active sessions."""
        if not token_str:
            raise ValidationException("Password reset token is required.")

        token_hash = hash_token(token_str)
        stmt = (
            select(PasswordResetToken)
            .options(selectinload(PasswordResetToken.user))
            .where(PasswordResetToken.token_hash == token_hash)
        )
        token_record = (await db.execute(stmt)).scalar_one_or_none()

        if not token_record or not token_record.is_valid:
            raise ValidationException("Password reset token is invalid, expired, or already used.")

        user = token_record.user
        if not user or not user.is_active:
            raise ValidationException("Account is invalid or disabled.")

        # Update password hash
        user.hashed_password = hash_password(new_password)
        token_record.used_at = datetime.now(timezone.utc)

        # Session invalidation: revoke all active sessions for this user on password change
        await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        await db.commit()

        logger.info("Successfully reset password and revoked all sessions for user %s", user.email)
        return True


_global_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Dependency provider for AuthService."""
    global _global_auth_service
    if _global_auth_service is None:
        _global_auth_service = AuthService()
    return _global_auth_service
