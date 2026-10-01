"""SQLAlchemy models for persistent AnalysisRuns and granular QualityIssues with complete provenance."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base

# Dialect-adaptive JSON type
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class AnalysisStatus(str, Enum):
    """Execution status of an analysis run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AnalysisRun(Base):
    """Record of a deterministic analysis run executed against a specific DatasetVersion."""

    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=AnalysisStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    target_column: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    problem_type: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    engine_version: Mapped[str] = mapped_column(
        String(32),
        default="1.0.0",
        nullable=False,
    )
    analyzer_versions: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        nullable=False,
    )
    ml_readiness_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    heuristic_breakdown: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        nullable=True,
    )
    total_issues_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    critical_issues_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    execution_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    summary_metrics: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        nullable=False,
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
    dataset_version = relationship("DatasetVersion")
    issues: Mapped[List["QualityIssue"]] = relationship(
        "QualityIssue",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        order_by="QualityIssue.detected_at",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<AnalysisRun id={self.id} version_id={self.dataset_version_id} status={self.status}>"


class QualityIssue(Base):
    """Granular data defect detected during deterministic analysis with full provenance."""

    __tablename__ = "quality_issues"
    __table_args__ = (
        Index("ix_quality_issues_run_severity", "analysis_run_id", "severity"),
        Index("ix_quality_issues_run_module", "analysis_run_id", "module"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    analyzer_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    parameters_used: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
    )
    column_name: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    evidence: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        default=dict,
        nullable=False,
    )
    remediation_hint: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    analysis_run: Mapped["AnalysisRun"] = relationship(
        "AnalysisRun",
        back_populates="issues",
    )
    dataset_version = relationship("DatasetVersion")

    def __repr__(self) -> str:
        return f"<QualityIssue id={self.id} module={self.module} severity={self.severity} title='{self.title[:30]}'>"
