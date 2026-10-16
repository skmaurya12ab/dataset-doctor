"""Persistent database-backed limits for low-volume authentication email dispatch."""

from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.email_delivery import EmailDeliveryAttempt, EmailDeliveryCounter


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def reserve_email_delivery(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    message_type: str,
    settings: Settings,
    now: datetime | None = None,
) -> bool:
    """Atomically reserve one daily slot and enforce a per-account cooldown.

    The singleton counter row is locked in PostgreSQL, serializing concurrent sends
    across app workers. Reservations count failures as attempts, so provider errors
    cannot be used to bypass the cap. Production requires this migration before use.
    """
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = current - timedelta(seconds=settings.email_recipient_cooldown_seconds)

    try:
        counter = await db.scalar(
            select(EmailDeliveryCounter)
            .where(EmailDeliveryCounter.id == 1)
            .with_for_update()
        )
        if counter is None:
            counter = EmailDeliveryCounter(id=1, bucket_date=current.date(), attempt_count=0)
            db.add(counter)
            await db.flush()

        if counter.bucket_date != current.date():
            counter.bucket_date = current.date()
            counter.attempt_count = 0

        latest = await db.scalar(
            select(EmailDeliveryAttempt.created_at)
            .where(
                EmailDeliveryAttempt.user_id == user_id,
                EmailDeliveryAttempt.message_type == message_type,
            )
            .order_by(EmailDeliveryAttempt.created_at.desc())
            .limit(1)
        )
        if latest is not None and _as_utc(latest) > cutoff:
            await db.commit()
            return False

        if counter.attempt_count >= settings.email_daily_send_cap:
            await db.commit()
            return False

        counter.attempt_count += 1
        db.add(
            EmailDeliveryAttempt(
                user_id=user_id,
                message_type=message_type,
                created_at=current,
            )
        )
        await db.execute(
            delete(EmailDeliveryAttempt).where(
                EmailDeliveryAttempt.created_at < current - timedelta(days=2)
            )
        )
        await db.commit()
        return True
    except Exception:
        await db.rollback()
        raise
