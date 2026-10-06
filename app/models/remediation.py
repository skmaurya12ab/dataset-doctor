"""SQLAlchemy models for deterministic remediation execution, approval, and version provenance."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base

# Dialect-adaptive JSON type (JSONB in PostgreSQL, standard JSON in SQLite)
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class RemediationExecutionStatus(str, Enum):
    """Lifecycle states of a remediation execution."""

    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    VALIDATING = "VALIDATING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class RemediationExecution(Base):
    """Auditable record of an approved, deterministically executed remediation plan."""

    __tablename__ = "remediation_executions"
    __table_args__ = (
        Index("ix_remediation_executions_run_id", "analysis_run_id"),
        Index("ix_remediation_executions_report_id", "ai_report_id"),
        Index("ix_remediation_executions_source_version", "source_dataset_version_id"),
        Index("ix_remediation_executions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    ai_report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    approved_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="user",
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=RemediationExecutionStatus.PENDING_APPROVAL.value,
        nullable=False,
    )
    transformation_plan: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        default=list,
        nullable=False,
    )
    pre_metrics: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        nullable=False,
    )
    post_metrics: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        nullable=False,
    )
    transformation_provenance: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        default=list,
        nullable=False,
    )
    result_dataset_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    analysis_run = relationship("AnalysisRun", backref="remediation_executions", lazy="selectin")
    ai_report = relationship("AIReport", backref="remediation_executions", lazy="selectin")
    source_version = relationship("DatasetVersion", foreign_keys=[source_dataset_version_id], lazy="selectin")
    result_version = relationship("DatasetVersion", foreign_keys=[result_dataset_version_id], lazy="selectin")

    def __repr__(self) -> str:
        return f"<RemediationExecution id={self.id} run_id={self.analysis_run_id} status={self.status}>"
