"""Declarative Base and common model mixins using modern SQLAlchemy 2.0 conventions."""

from datetime import datetime, timezone
from typing import Any
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Default table name derived from lowercase class name pluralized."""
        name = cls.__name__.lower()
        if name.endswith("s"):
            return name
        return f"{name}s"


class TimestampMixin:
    """Mixin providing created_at and updated_at UTC timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
