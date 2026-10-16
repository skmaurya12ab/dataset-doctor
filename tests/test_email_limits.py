"""Persistent application-level email cap and account cooldown tests."""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.email_delivery import EmailDeliveryAttempt, EmailDeliveryCounter
from app.models.user import User
from app.services.email_limits import reserve_email_delivery


async def make_user(db: AsyncSession, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password="unused-test-hash",
        is_active=True,
        is_verified=False,
        role="user",
    )
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_per_account_cooldown_and_persistent_daily_cap(test_db_session: AsyncSession) -> None:
    settings = Settings(
        environment="testing",
        email_provider="mock",
        email_daily_send_cap=2,
        email_recipient_cooldown_seconds=900,
    )
    first_user = await make_user(test_db_session, "limits1@example.com")
    second_user = await make_user(test_db_session, "limits2@example.com")
    now = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)

    assert await reserve_email_delivery(
        test_db_session, user_id=first_user.id, message_type="verification", settings=settings, now=now
    )
    assert not await reserve_email_delivery(
        test_db_session, user_id=first_user.id, message_type="verification", settings=settings, now=now + timedelta(minutes=1)
    )
    assert await reserve_email_delivery(
        test_db_session, user_id=second_user.id, message_type="password_reset", settings=settings, now=now + timedelta(minutes=1)
    )
    assert not await reserve_email_delivery(
        test_db_session, user_id=first_user.id, message_type="verification", settings=settings, now=now + timedelta(minutes=16)
    )

    counter = await test_db_session.scalar(select(EmailDeliveryCounter).where(EmailDeliveryCounter.id == 1))
    assert counter is not None
    assert counter.attempt_count == 2
    attempts = (await test_db_session.execute(select(EmailDeliveryAttempt))).scalars().all()
    assert len(attempts) == 2
    assert all(not hasattr(attempt, "email") for attempt in attempts)


@pytest.mark.asyncio
async def test_daily_cap_resets_on_utc_date(test_db_session: AsyncSession) -> None:
    settings = Settings(
        environment="testing",
        email_provider="mock",
        email_daily_send_cap=1,
        email_recipient_cooldown_seconds=60,
    )
    user = await make_user(test_db_session, "limits3@example.com")
    day_one = datetime(2026, 10, 16, 23, 59, tzinfo=timezone.utc)
    day_two = day_one + timedelta(minutes=2)

    assert await reserve_email_delivery(
        test_db_session, user_id=user.id, message_type="verification", settings=settings, now=day_one
    )
    assert await reserve_email_delivery(
        test_db_session, user_id=user.id, message_type="password_reset", settings=settings, now=day_two
    )
    counter = await test_db_session.scalar(select(EmailDeliveryCounter).where(EmailDeliveryCounter.id == 1))
    assert counter is not None
    assert counter.bucket_date == day_two.date()
    assert counter.attempt_count == 1
