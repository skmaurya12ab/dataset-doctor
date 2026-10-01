"""Deterministic schema analyzer inspecting structure, duplicate headers, and blank names."""

from collections import Counter
from datetime import datetime, timezone
import time
from typing import Any, Dict, List
import pandas as pd

from app.core.json_utils import to_json_safe
from app.engine.base import AnalysisContext, BaseAnalyzer, ModuleResult, QualityIssueData, Severity
from app.engine.defaults import DEFAULT_SCHEMA_PARAMETERS


class SchemaAnalyzer(BaseAnalyzer):
    """Inspects structural schema without performing statistical quality analysis."""

    @property
    def name(self) -> str:
        return "schema_analyzer"

    @property
    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ctx: AnalysisContext) -> ModuleResult:
        start_time = time.perf_counter()
        df: pd.DataFrame = ctx.df if ctx.df is not None else pd.DataFrame()

        # Effective parameters
        params = {**DEFAULT_SCHEMA_PARAMETERS, **ctx.parameters.get(self.name, {})}

        raw_columns = [str(c) for c in df.columns]
        row_count = int(len(df))
        column_count = int(len(raw_columns))

        # Check duplicate column names
        col_counts = Counter(raw_columns)
        duplicate_column_names = [name for name, count in col_counts.items() if count > 1]
        has_duplicate_column_names = len(duplicate_column_names) > 0

        # Check blank column names
        strip_ws = params.get("strip_whitespace_for_blank_check", True)
        blank_column_names = []
        for col in raw_columns:
            cleaned = col.strip() if strip_ws else col
            if cleaned == "":
                blank_column_names.append(col)
        has_blank_column_names = len(blank_column_names) > 0

        metrics: Dict[str, Any] = {
            "row_count": row_count,
            "column_count": column_count,
            "column_names": raw_columns,
            "duplicate_column_names": duplicate_column_names,
            "blank_column_names": blank_column_names,
            "column_order": raw_columns,
            "has_duplicate_column_names": has_duplicate_column_names,
            "has_blank_column_names": has_blank_column_names,
        }

        issues: List[QualityIssueData] = []
        now = datetime.now(timezone.utc)

        # 1. Issue for duplicate column names
        if has_duplicate_column_names:
            issues.append(
                QualityIssueData(
                    module=self.name,
                    analyzer_version=self.version,
                    category="SCHEMA",
                    severity=Severity.HIGH,
                    title="Duplicate column names detected",
                    description=(
                        f"The dataset contains duplicate column names: "
                        f"{', '.join(duplicate_column_names)}. Duplicate headers lead to ambiguous "
                        "indexing and pipeline ingestion failures."
                    ),
                    column_name=None,
                    parameters_used=to_json_safe(params),
                    evidence={
                        "duplicate_columns": duplicate_column_names,
                        "duplicate_count": len(duplicate_column_names),
                    },
                    remediation_hint="Rename duplicated column headers uniquely before downstream processing.",
                    detected_at=now,
                )
            )

        # 2. Issue for blank column names
        if has_blank_column_names:
            issues.append(
                QualityIssueData(
                    module=self.name,
                    analyzer_version=self.version,
                    category="SCHEMA",
                    severity=Severity.MEDIUM,
                    title="Blank column name detected",
                    description=(
                        f"Detected {len(blank_column_names)} column(s) with blank or whitespace-only names. "
                        "Unnamed columns prevent reliable feature referencing."
                    ),
                    column_name=None,
                    parameters_used=to_json_safe(params),
                    evidence={
                        "blank_columns": blank_column_names,
                    },
                    remediation_hint="Assign descriptive names to all blank or whitespace-only column headers.",
                    detected_at=now,
                )
            )

        exec_time_ms = int((time.perf_counter() - start_time) * 1000)
        return ModuleResult(
            module_name=self.name,
            analyzer_version=self.version,
            execution_time_ms=exec_time_ms,
            metrics=to_json_safe(metrics),
            issues=issues,
        )
