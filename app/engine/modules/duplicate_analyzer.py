"""Deterministic duplicate row analyzer detecting identical row groups."""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List
import pandas as pd

from app.core.json_utils import to_json_safe
from app.engine.base import AnalysisContext, BaseAnalyzer, ModuleResult, QualityIssueData, Severity
from app.engine.defaults import DEFAULT_DUPLICATE_PARAMETERS


class DuplicateAnalyzer(BaseAnalyzer):
    """Detects exact duplicate rows across the complete dataset."""

    @property
    def name(self) -> str:
        return "duplicate_analyzer"

    @property
    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ctx: AnalysisContext) -> ModuleResult:
        start_time = time.perf_counter()
        df: pd.DataFrame = ctx.df if ctx.df is not None else pd.DataFrame()

        params = {**DEFAULT_DUPLICATE_PARAMETERS, **ctx.parameters.get(self.name, {})}
        low_thresh = float(params.get("low_threshold_pct", 1.0))
        med_thresh = float(params.get("medium_threshold_pct", 5.0))
        high_thresh = float(params.get("high_threshold_pct", 20.0))

        total_rows = int(len(df))
        duplicate_row_count = 0
        duplicate_percentage = 0.0
        unique_row_count = 0

        issues: List[QualityIssueData] = []
        now = datetime.now(timezone.utc)

        if total_rows > 0 and len(df.columns) > 0:
            try:
                dup_mask = df.duplicated(keep=False)
            except TypeError:
                # Fallback for unhashable objects (lists, dicts, sets in object columns)
                safe_df = df.map(lambda x: str(x) if isinstance(x, (dict, list, set)) else x)
                dup_mask = safe_df.duplicated(keep=False)

            duplicate_row_count = int(dup_mask.sum())
            duplicate_percentage = round((duplicate_row_count / total_rows) * 100.0, 2)
            unique_row_count = total_rows - duplicate_row_count

            if duplicate_row_count > 0:
                if duplicate_percentage <= low_thresh:
                    severity = Severity.LOW
                elif duplicate_percentage <= med_thresh:
                    severity = Severity.MEDIUM
                elif duplicate_percentage <= high_thresh:
                    severity = Severity.HIGH
                else:
                    severity = Severity.CRITICAL

                issues.append(
                    QualityIssueData(
                        module=self.name,
                        analyzer_version=self.version,
                        category="DUPLICATES",
                        severity=severity,
                        title="Duplicate rows detected",
                        description=(
                            f"Detected {duplicate_row_count} duplicate row(s) "
                            f"({duplicate_percentage}% of {total_rows} total rows). All matching rows "
                            "belonging to duplicate clusters are accounted for."
                        ),
                        column_name=None,
                        parameters_used=to_json_safe(params),
                        evidence={
                            "total_rows": total_rows,
                            "duplicate_row_count": duplicate_row_count,
                            "duplicate_percentage": duplicate_percentage,
                            "unique_row_count": unique_row_count,
                        },
                        remediation_hint=(
                            "Review row deduplication criteria to avoid data leakage "
                            "or artificial sample weighting."
                        ),
                        detected_at=now,
                    )
                )

        metrics: Dict[str, Any] = {
            "total_rows": total_rows,
            "duplicate_row_count": duplicate_row_count,
            "duplicate_percentage": duplicate_percentage,
            "unique_row_count": unique_row_count,
        }

        exec_time_ms = int((time.perf_counter() - start_time) * 1000)
        return ModuleResult(
            module_name=self.name,
            analyzer_version=self.version,
            execution_time_ms=exec_time_ms,
            metrics=to_json_safe(metrics),
            issues=issues,
        )
