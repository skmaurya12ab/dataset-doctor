"""Service for deterministic before/after DatasetVersion comparisons and defect lifecycle tracking."""

from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import EntityNotFoundException, ValidationException
from app.core.logging import get_logger
from app.models.analysis import AnalysisRun, AnalysisStatus, QualityIssue
from app.models.dataset import DatasetVersion
from app.schemas.remediation import (
    HeuristicComparison,
    IssueComparisonItem,
    MetricDelta,
    VersionComparisonResponse,
)

logger = get_logger(__name__)


def calculate_rating(score: Optional[float]) -> Optional[str]:
    """Map numeric readiness score to standardized qualitative rating."""
    if score is None:
        return None
    if score >= 80.0:
        return "EXCELLENT"
    if score >= 65.0:
        return "GOOD"
    if score >= 50.0:
        return "MODERATE"
    return "POOR"


def make_semantic_issue_key(issue: QualityIssue) -> str:
    """Deterministic defect identity tuple string: (module:category:column)."""
    col = issue.column_name or ""
    return f"{issue.module}:{issue.category}:{col}"


class ComparisonService:
    """Generates structured comparisons between two dataset versions based on deterministic analysis."""

    async def compare_versions(
        self,
        db: AsyncSession,
        dataset_id: uuid.UUID,
        v1_id: uuid.UUID,
        v2_id: uuid.UUID,
    ) -> VersionComparisonResponse:
        """Compare two DatasetVersions and their latest completed AnalysisRuns."""
        # 1. Fetch both versions
        v1_stmt = select(DatasetVersion).where(
            DatasetVersion.id == v1_id,
            DatasetVersion.dataset_id == dataset_id,
        )
        v2_stmt = select(DatasetVersion).where(
            DatasetVersion.id == v2_id,
            DatasetVersion.dataset_id == dataset_id,
        )
        res1 = await db.execute(v1_stmt)
        v1 = res1.scalar_one_or_none()
        if not v1:
            raise EntityNotFoundException("DatasetVersion", f"v1 '{v1_id}' for dataset '{dataset_id}'")

        res2 = await db.execute(v2_stmt)
        v2 = res2.scalar_one_or_none()
        if not v2:
            raise EntityNotFoundException("DatasetVersion", f"v2 '{v2_id}' for dataset '{dataset_id}'")

        # 2. Fetch latest completed AnalysisRun for each version
        run1 = await self._get_latest_completed_run(db, v1.id)
        run2 = await self._get_latest_completed_run(db, v2.id)

        # 3. Compute Dataset-level metric deltas
        # Use run summary_metrics if available, otherwise version metadata
        v1_rows = run1.summary_metrics.get("row_count", v1.row_count) if run1 else v1.row_count
        v2_rows = run2.summary_metrics.get("row_count", v2.row_count) if run2 else v2.row_count
        v1_cols = run1.summary_metrics.get("column_count", v1.column_count) if run1 else v1.column_count
        v2_cols = run2.summary_metrics.get("column_count", v2.column_count) if run2 else v2.column_count

        v1_missing = run1.summary_metrics.get("missing_cells", 0) if run1 else 0
        v2_missing = run2.summary_metrics.get("missing_cells", 0) if run2 else 0

        v1_missing_pct = run1.summary_metrics.get("missing_percentage", 0.0) if run1 else 0.0
        v2_missing_pct = run2.summary_metrics.get("missing_percentage", 0.0) if run2 else 0.0

        v1_dups = run1.summary_metrics.get("duplicate_rows", 0) if run1 else 0
        v2_dups = run2.summary_metrics.get("duplicate_rows", 0) if run2 else 0

        v1_total_issues = run1.total_issues_count if run1 else 0
        v2_total_issues = run2.total_issues_count if run2 else 0

        v1_crit_issues = run1.critical_issues_count if run1 else 0
        v2_crit_issues = run2.critical_issues_count if run2 else 0

        dataset_metrics: Dict[str, MetricDelta] = {
            "rows": MetricDelta(before=v1_rows, after=v2_rows, delta=v2_rows - v1_rows),
            "columns": MetricDelta(before=v1_cols, after=v2_cols, delta=v2_cols - v1_cols),
            "missing_cells": MetricDelta(before=v1_missing, after=v2_missing, delta=v2_missing - v1_missing),
            "missing_percentage": MetricDelta(
                before=round(v1_missing_pct, 4),
                after=round(v2_missing_pct, 4),
                delta=round(v2_missing_pct - v1_missing_pct, 4),
            ),
            "duplicate_rows": MetricDelta(before=v1_dups, after=v2_dups, delta=v2_dups - v1_dups),
            "total_issues": MetricDelta(before=v1_total_issues, after=v2_total_issues, delta=v2_total_issues - v1_total_issues),
            "critical_issues": MetricDelta(before=v1_crit_issues, after=v2_crit_issues, delta=v2_crit_issues - v1_crit_issues),
        }

        # 4. Compare QualityIssues deterministically
        issues1 = run1.issues if run1 else []
        issues2 = run2.issues if run2 else []

        quality_comparison = self._compare_issues(issues1, issues2)

        # 5. Heuristic score comparison
        score1 = run1.ml_readiness_score if run1 else None
        score2 = run2.ml_readiness_score if run2 else None
        score_delta = round(score2 - score1, 2) if (score1 is not None and score2 is not None) else None

        heuristic_comp = HeuristicComparison(
            before_score=score1,
            after_score=score2,
            delta=score_delta,
            before_rating=calculate_rating(score1),
            after_rating=calculate_rating(score2),
        )

        return VersionComparisonResponse(
            dataset_id=dataset_id,
            before={
                "version_id": v1.id,
                "version_number": v1.version_number,
                "file_name": v1.file_name,
                "created_at": v1.created_at,
                "analysis_run_id": run1.id if run1 else None,
            },
            after={
                "version_id": v2.id,
                "version_number": v2.version_number,
                "file_name": v2.file_name,
                "created_at": v2.created_at,
                "analysis_run_id": run2.id if run2 else None,
            },
            dataset_metrics=dataset_metrics,
            quality=quality_comparison,
            heuristic=heuristic_comp,
        )

    async def _get_latest_completed_run(self, db: AsyncSession, version_id: uuid.UUID) -> Optional[AnalysisRun]:
        stmt = (
            select(AnalysisRun)
            .where(
                AnalysisRun.dataset_version_id == version_id,
                AnalysisRun.status == AnalysisStatus.COMPLETED.value,
            )
            .options(selectinload(AnalysisRun.issues))
            .order_by(desc(AnalysisRun.completed_at), desc(AnalysisRun.created_at))
        )
        res = await db.execute(stmt)
        return res.scalars().first()

    def _compare_issues(
        self,
        issues1: List[QualityIssue],
        issues2: List[QualityIssue],
    ) -> Dict[str, Any]:
        """Compare issues between two runs using semantic identity keys."""
        map1: Dict[str, QualityIssue] = {make_semantic_issue_key(iss): iss for iss in issues1}
        map2: Dict[str, QualityIssue] = {make_semantic_issue_key(iss): iss for iss in issues2}

        all_keys = set(map1.keys()) | set(map2.keys())

        resolved_count = 0
        changed_count = 0
        unchanged_count = 0
        new_count = 0

        items: List[Dict[str, Any]] = []

        for key in sorted(all_keys):
            iss1 = map1.get(key)
            iss2 = map2.get(key)

            if iss1 and not iss2:
                # Issue existed in before, absent in after -> RESOLVED
                resolved_count += 1
                items.append({
                    "semantic_key": key,
                    "module": iss1.module,
                    "category": iss1.category,
                    "column": iss1.column_name,
                    "status": "RESOLVED",
                    "before_severity": iss1.severity,
                    "after_severity": None,
                    "details": {"resolution": "Defect successfully resolved in remediated version"},
                })
            elif not iss1 and iss2:
                # Issue absent in before, present in after -> NEW
                new_count += 1
                items.append({
                    "semantic_key": key,
                    "module": iss2.module,
                    "category": iss2.category,
                    "column": iss2.column_name,
                    "status": "NEW",
                    "before_severity": None,
                    "after_severity": iss2.severity,
                    "details": {"issue": "Defect introduced in remediated version"},
                })
            elif iss1 and iss2:
                if iss1.severity != iss2.severity:
                    # Severity changed -> CHANGED
                    changed_count += 1
                    items.append({
                        "semantic_key": key,
                        "module": iss1.module,
                        "category": iss1.category,
                        "column": iss1.column_name,
                        "status": "CHANGED",
                        "before_severity": iss1.severity,
                        "after_severity": iss2.severity,
                        "details": {"change": f"Severity transitioned from {iss1.severity} to {iss2.severity}"},
                    })
                else:
                    # Identical severity -> UNCHANGED
                    unchanged_count += 1
                    items.append({
                        "semantic_key": key,
                        "module": iss1.module,
                        "category": iss1.category,
                        "column": iss1.column_name,
                        "status": "UNCHANGED",
                        "before_severity": iss1.severity,
                        "after_severity": iss2.severity,
                        "details": {"note": "Defect remains present with unchanged severity"},
                    })

        return {
            "issues_resolved": resolved_count,
            "issues_changed": changed_count,
            "issues_unchanged": unchanged_count,
            "new_issues": new_count,
            "items": items,
        }
