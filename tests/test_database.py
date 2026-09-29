"""Tests for SQLAlchemy base models and database session isolation."""

import pytest
from sqlalchemy import Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DummyModel(Base, TimestampMixin):
    """Test model to verify Base and TimestampMixin behavior."""

    __tablename__ = "dummy_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)


@pytest.mark.asyncio
async def test_base_model_and_timestamp_mixin(test_db_session: AsyncSession) -> None:
    """Verify that models inherit timestamps and work with async sessions."""
    # Create test table inside session connection
    conn = await test_db_session.connection()
    await conn.run_sync(Base.metadata.create_all)

    # Insert entity
    entity = DummyModel(name="test_dataset")
    test_db_session.add(entity)
    await test_db_session.flush()

    assert entity.id is not None
    assert entity.name == "test_dataset"
    assert entity.created_at is not None
    assert entity.updated_at is not None

    # Query back
    result = await test_db_session.execute(select(DummyModel).where(DummyModel.name == "test_dataset"))
    retrieved = result.scalar_one_or_none()
    assert retrieved is not None
    assert retrieved.name == "test_dataset"
