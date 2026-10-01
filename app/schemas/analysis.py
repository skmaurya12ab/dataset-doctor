"""Pydantic schemas for analysis requests, run statuses, and quality issues."""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class AnalysisRequest(BaseModel):
    """Payload to trigger an asynchronous analysis run on a dataset version."""

    target_column: Optional[str] = Field(
        default=None,
        description="Optional target column name for downstream ML analysis",
    )
    problem_type: Optional[str] = Field(
        default=None,
        description="Optional problem type: 'classification', 'regression', etc.",
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional custom configuration parameters overriding defaults",
    )


class AnalysisResponse(BaseModel):
    """Immediate response confirming analysis submission."""

    analysis_run_id: uuid.UUID = Field(description="UUID of the initiated analysis run")
    status: str = Field(description="Initial status, usually PENDING")


class QualityIssueRead(BaseModel):
    """Detailed quality defect finding with complete provenance."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    dataset_version_id: uuid.UUID
    module: str
    analyzer_version: str
    parameters_used: Dict[str, Any]
    category: str
    severity: str
    column_name: Optional[str] = None
    title: str
    description: str
    evidence: Dict[str, Any]
    remediation_hint: Optional[str] = None
    detected_at: datetime


class AnalysisRunRead(BaseModel):
    """Complete summary and status of an analysis execution run."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    dataset_version_id: uuid.UUID
    status: str
    target_column: Optional[str] = None
    problem_type: Optional[str] = None
    engine_version: str
    analyzer_versions: Dict[str, Any]
    ml_readiness_score: Optional[float] = None
    heuristic_breakdown: Optional[Dict[str, Any]] = None
    total_issues_count: int
    critical_issues_count: int
    execution_time_ms: Optional[int] = None
    summary_metrics: Dict[str, Any]
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class QualityIssueListResponse(BaseModel):
    """Paginated collection of quality issues."""

    total: int
    limit: int
    offset: int
    items: List[QualityIssueRead]


class ItemizedPenaltyRead(BaseModel):
    """Itemized penalty deduction in the ML Readiness Heuristic breakdown."""

    module: str
    severity: str
    reason: str
    penalty: float
    column_name: Optional[str] = None


class HeuristicBreakdownRead(BaseModel):
    """Transparent explainable breakdown of the ML Readiness Heuristic."""

    heuristic_score: float
    rating: str
    base_score: float = 100.0
    total_penalties: float = 0.0
    disclaimer: str
    itemized_penalties: List[ItemizedPenaltyRead] = Field(default_factory=list)

