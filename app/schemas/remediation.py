"""Pydantic schemas for remediation approval, execution provenance, and before/after version comparison."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RemediationApplyRequest(BaseModel):
    """Explicit human approval and specification to trigger deterministic remediation."""

    ai_report_id: uuid.UUID = Field(
        description="UUID of the AIReport containing the validated remediation plan",
    )
    approval: bool = Field(
        default=True,
        description="Explicit human approval flag. Must be True to permit execution.",
    )
    approved_by: str = Field(
        default="user",
        description="Identifier of the human reviewer approving execution",
        min_length=1,
        max_length=128,
    )

    @field_validator("approval")
    @classmethod
    def require_explicit_approval(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Remediation execution requires explicit approval (approval=True).")
        return v


class MetricDelta(BaseModel):
    """Comparative metric representing before, after, and arithmetic delta."""

    before: Any = Field(description="Deterministic metric value before remediation")
    after: Any = Field(description="Deterministic metric value after remediation")
    delta: Any = Field(description="Arithmetic delta (after - before) or None if non-numeric")


class IssueComparisonItem(BaseModel):
    """Detailed comparison status for a deterministic quality finding across versions."""

    semantic_key: str = Field(description="Deterministic identity tuple (module:category:column)")
    module: str = Field(description="Detection engine module")
    category: str = Field(description="Defect category")
    column: Optional[str] = Field(default=None, description="Affected column name if column-specific")
    status: Literal["RESOLVED", "CHANGED", "UNCHANGED", "NEW"] = Field(
        description="Comparative defect lifecycle state"
    )
    before_severity: Optional[str] = Field(default=None, description="Severity in source version")
    after_severity: Optional[str] = Field(default=None, description="Severity in remediated version")
    details: Dict[str, Any] = Field(default_factory=dict, description="Metric changes or explanatory note")


class HeuristicComparison(BaseModel):
    """ML readiness score comparison without claiming model performance gains."""

    before_score: Optional[float] = Field(default=None, description="ML readiness score in source version (0-100)")
    after_score: Optional[float] = Field(default=None, description="ML readiness score in remediated version (0-100)")
    delta: Optional[float] = Field(default=None, description="Arithmetic change in ML readiness score")
    before_rating: Optional[str] = Field(default=None, description="Source readiness qualitative rating")
    after_rating: Optional[str] = Field(default=None, description="Remediated readiness qualitative rating")
    note: str = Field(
        default="The heuristic measures data quality/readiness signals, not actual model performance.",
        description="Safety disclaimer ensuring scores are not conflated with model accuracy",
    )


class VersionComparisonResponse(BaseModel):
    """Complete comparative audit report between two DatasetVersions."""

    dataset_id: uuid.UUID = Field(description="Parent dataset UUID")
    before: Dict[str, Any] = Field(description="Source version metadata and analysis run reference")
    after: Dict[str, Any] = Field(description="Remediated version metadata and analysis run reference")
    dataset_metrics: Dict[str, MetricDelta] = Field(
        description="Comparative dataset summary metrics with exact deltas",
    )
    quality: Dict[str, Any] = Field(
        description="Aggregated and granular quality issue comparisons",
    )
    heuristic: HeuristicComparison = Field(
        description="ML readiness score before/after comparison",
    )


class TransformationProvenanceItem(BaseModel):
    """Granular audit record for an individual executed transformation."""

    action: str
    column: Optional[str] = None
    columns: Optional[List[str]] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    source_issue_ids: List[str] = Field(default_factory=list)
    reason: str
    applied_order: int
    rows_changed: int
    columns_changed: int
    before_metrics: Dict[str, Any] = Field(default_factory=dict)
    after_metrics: Dict[str, Any] = Field(default_factory=dict)
    executor_version: str = "1.0.0"
    executed_at: datetime


class RemediationExecutionRead(BaseModel):
    """Full detail of a remediation execution record."""

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    ai_report_id: uuid.UUID
    source_dataset_version_id: uuid.UUID
    approved_by: str
    approved_at: datetime
    status: str
    transformation_plan: List[Dict[str, Any]]
    pre_metrics: Dict[str, Any]
    post_metrics: Dict[str, Any]
    transformation_provenance: List[Dict[str, Any]]
    result_dataset_version_id: Optional[uuid.UUID] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RemediationListResponse(BaseModel):
    """Paginated or listed remediation executions."""

    items: List[RemediationExecutionRead]
    total: int
