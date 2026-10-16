"""Persistent, bounded abuse-control counters for authentication email delivery."""

from datetime import date, datetime, timezone
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EmailDeliveryCounter(Base):
    """Singleton UTC-day counter serialized by a row lock before each dispatch attempt."""

    __tablename__ = "email_delivery_counters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class EmailDeliveryAttempt(Base):
    """Recipient-free audit row used to enforce per-account cooldowns."""

    __tablename__ = "email_delivery_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


Index("ix_email_delivery_attempt_user_created", EmailDeliveryAttempt.user_id, EmailDeliveryAttempt.created_at)
