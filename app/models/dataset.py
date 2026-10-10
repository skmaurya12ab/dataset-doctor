from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User

# Use JSONB for PostgreSQL when available, fallback to JSON for SQLite/other dialects
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class Dataset(Base, TimestampMixin):
    """Top-level dataset entity representing a data asset and its version lineage."""

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    owner: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="datasets",
        foreign_keys=[owner_id],
    )
    versions: Mapped[List["DatasetVersion"]] = relationship(
        "DatasetVersion",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetVersion.version_number",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Dataset id={self.id} name='{self.name}'>"


class DatasetVersion(Base):
    """Immutable dataset version snapshot with metadata, file references, and schema."""

    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "version_number",
            name="uq_dataset_version_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    change_summary: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        default="Initial upload",
    )
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    row_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    column_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    raw_schema: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    dataset: Mapped["Dataset"] = relationship(
        "Dataset",
        back_populates="versions",
    )
    parent_version: Mapped[Optional["DatasetVersion"]] = relationship(
        "DatasetVersion",
        remote_side=[id],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<DatasetVersion id={self.id} dataset_id={self.dataset_id} v={self.version_number}>"
