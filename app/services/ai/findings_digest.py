"""Compact, token-bounded deterministic findings digest generator for LLM interpretation.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. Strict Grounding: Contains ONLY deterministically computed metrics and defects.
2. Zero Raw Data: Never includes Parquet files, raw DataFrames, or arbitrary raw dataset rows.
3. Token Bounded: Explicitly budgets token allocation (2,000–3,500 tokens configurable).
4. Transparent Truncation: Prioritizes CRITICAL > HIGH > MEDIUM > LOW > INFO issues;
   if budgeting truncates issues, explicitly flags truncation and reports counts.
"""

import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.analysis import AnalysisRun, QualityIssue

# Severity priority order (lower number = higher priority)
SEVERITY_ORDER = {
    "CRITICAL": 1,
    "HIGH": 2,
    "MEDIUM": 3,
    "LOW": 4,
    "INFO": 5,
}


class CompactQualityIssue(BaseModel):
    """Token-efficient summary of an individual deterministic defect."""

    id: str = Field(description="Defect unique identifier")
    category: str = Field(description="Issue category (e.g. MISSING_VALUES, HIGH_CORRELATION)")
    severity: str = Field(description="Defect severity: CRITICAL, HIGH, MEDIUM, LOW, INFO")
    module: str = Field(description="Deterministic analyzer module that flagged the defect")
    column_name: Optional[str] = Field(default=None, description="Impacted column name, if applicable")
    title: str = Field(description="Short human-readable defect title")
    description: str = Field(description="Factual description grounded in deterministic findings")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Deterministic statistical proof")
    remediation_hint: Optional[str] = Field(default=None, description="Deterministic engine hint")


class FindingsDigest(BaseModel):
    """Compact structured payload supplied to the AI interpretation provider."""

    dataset_metadata: Dict[str, Any] = Field(
        description="Dataset high-level attributes (name, dimensions, format, version)",
    )
    target_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Target variable specification and problem type (classification/regression)",
    )
    summary_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Authoritative deterministic metrics (row_count, column_count, null_rate, etc.)",
    )
    ml_readiness_score: Optional[float] = Field(
        default=None,
        description="Deterministic heuristic ML readiness score (0-100)",
    )
    heuristic_breakdown: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Transparent penalty itemization",
    )
    total_issues: int = Field(ge=0, description="Total number of deterministic issues found")
    included_issues: int = Field(ge=0, description="Number of issues included in this digest")
    findings_truncated: bool = Field(
        default=False,
        description="True if token budgeting truncated lower-priority findings",
    )
    omitted_by_severity: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of omitted issues broken down by severity level",
    )
    priority_issues: List[CompactQualityIssue] = Field(
        default_factory=list,
        description="Ordered list of high-priority quality defects",
    )


class FindingsDigestGenerator:
    """Produces token-bounded, prioritized findings digests from AnalysisRun records."""

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough, conservative token estimation (~4 characters per token)."""
        return max(1, len(text) // 4)

    @staticmethod
    def _compact_evidence(evidence: Dict[str, Any], max_items: int = 10) -> Dict[str, Any]:
        """Prune unnecessarily large nested collections in evidence to preserve token budget."""
        compacted: Dict[str, Any] = {}
        for k, v in evidence.items():
            if isinstance(v, list) and len(v) > max_items:
                compacted[k] = v[:max_items] + [f"...({len(v) - max_items} more items truncated)"]
            elif isinstance(v, dict) and len(v) > max_items:
                pruned_dict = {sub_k: v[sub_k] for sub_k in list(v.keys())[:max_items]}
                pruned_dict["_truncated_keys_count"] = len(v) - max_items
                compacted[k] = pruned_dict
            else:
                compacted[k] = v
        return compacted

    def create_digest(
        self,
        analysis_run: AnalysisRun,
        issues: List[QualityIssue],
        max_tokens: int = 3500,
    ) -> FindingsDigest:
        """Construct a token-bounded, grounded findings digest from an AnalysisRun."""
        # 1. Base dataset metadata
        version = analysis_run.dataset_version
        dataset_meta: Dict[str, Any] = {
            "analysis_run_id": str(analysis_run.id),
            "engine_version": analysis_run.engine_version,
            "created_at": analysis_run.created_at.isoformat() if analysis_run.created_at else None,
        }
        if version:
            dataset_meta.update({
                "dataset_id": str(version.dataset_id),
                "version_number": version.version_number,
                "file_name": version.file_name,
                "storage_format": (
                    getattr(version, "storage_format", None)
                    or (version.storage_path.split(".")[-1] if getattr(version, "storage_path", None) else "parquet")
                ),
                "row_count": version.row_count,
                "column_count": version.column_count,
            })

        # 2. Target metadata
        target_meta: Optional[Dict[str, Any]] = None
        if analysis_run.target_column or analysis_run.problem_type:
            target_meta = {
                "target_column": analysis_run.target_column,
                "problem_type": analysis_run.problem_type,
            }

        # 3. Base digest skeleton
        base_digest = FindingsDigest(
            dataset_metadata=dataset_meta,
            target_metadata=target_meta,
            summary_metrics=analysis_run.summary_metrics or {},
            ml_readiness_score=analysis_run.ml_readiness_score,
            heuristic_breakdown=analysis_run.heuristic_breakdown or {},
            total_issues=len(issues),
            included_issues=0,
            findings_truncated=False,
            omitted_by_severity={s: 0 for s in SEVERITY_ORDER},
            priority_issues=[],
        )

        base_tokens = self._estimate_tokens(base_digest.model_dump_json())
        remaining_budget = max(200, max_tokens - base_tokens)

        # 4. Sort issues strictly by severity priority, then by module/title for determinism
        sorted_issues = sorted(
            issues,
            key=lambda x: (
                SEVERITY_ORDER.get(x.severity.upper(), 99),
                x.module,
                x.title,
                str(x.id),
            ),
        )

        included: List[CompactQualityIssue] = []
        truncated = False
        current_consumed = 0

        for issue in sorted_issues:
            compact_iss = CompactQualityIssue(
                id=str(issue.id),
                category=issue.category,
                severity=issue.severity,
                module=issue.module,
                column_name=issue.column_name,
                title=issue.title,
                description=issue.description,
                evidence=self._compact_evidence(issue.evidence or {}),
                remediation_hint=issue.remediation_hint,
            )

            issue_tokens = self._estimate_tokens(compact_iss.model_dump_json())

            if current_consumed + issue_tokens <= remaining_budget:
                included.append(compact_iss)
                current_consumed += issue_tokens
            else:
                truncated = True
                sev_key = issue.severity.upper()
                base_digest.omitted_by_severity[sev_key] = (
                    base_digest.omitted_by_severity.get(sev_key, 0) + 1
                )

        base_digest.priority_issues = included
        base_digest.included_issues = len(included)
        base_digest.findings_truncated = truncated

        # Clean up empty omitted counts
        base_digest.omitted_by_severity = {
            k: v for k, v in base_digest.omitted_by_severity.items() if v > 0
        }

        return base_digest
