"""SQLAlchemy models for persisting AI reports, remediation plans, and finding explanations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base

# Dialect-adaptive JSON type (JSONB in PostgreSQL, standard JSON in SQLite)
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class AIReport(Base):
    """Persisted AI-synthesized remediation report and risk assessment for an AnalysisRun."""

    __tablename__ = "ai_reports"
    __table_args__ = (
        Index("ix_ai_reports_run_model_version", "analysis_run_id", "provider_model", "prompt_version"),
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
    provider_model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    prompt_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    executive_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    risk_assessment: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        default=list,
        nullable=False,
    )
    remediation_plan: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        default=list,
        nullable=False,
    )
    transformation_specs: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        default=list,
        nullable=False,
    )
    ml_preparation_plan: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        default=list,
        nullable=False,
    )
    generated_python_code: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship to parent analysis run
    analysis_run = relationship("AnalysisRun", backref="ai_reports")

    def __repr__(self) -> str:
        return f"<AIReport id={self.id} run_id={self.analysis_run_id} model={self.provider_model}>"


class FindingExplanationRecord(Base):
    """Persisted grounded explanation for an individual QualityIssue."""

    __tablename__ = "finding_explanations"
    __table_args__ = (
        Index("ix_finding_explanations_issue_model_version", "quality_issue_id", "provider_model", "prompt_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    quality_issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quality_issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    prompt_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    explanation_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    why_it_matters: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    practical_impact: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    recommended_actions: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        default=list,
        nullable=False,
    )
    limitations: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        default=list,
        nullable=False,
    )
    input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship to parent quality issue
    quality_issue = relationship("QualityIssue", backref="explanations")

    def __repr__(self) -> str:
        return f"<FindingExplanationRecord id={self.id} issue_id={self.quality_issue_id} model={self.provider_model}>"
