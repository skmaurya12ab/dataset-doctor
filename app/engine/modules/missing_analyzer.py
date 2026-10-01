"""Deterministic missing value analyzer inspecting nulls, empty strings, and missingness rates."""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List
import pandas as pd

from app.core.json_utils import to_json_safe
from app.engine.base import AnalysisContext, BaseAnalyzer, ModuleResult, QualityIssueData, Severity
from app.engine.defaults import DEFAULT_MISSING_PARAMETERS


class MissingValueAnalyzer(BaseAnalyzer):
    """Detects standard missing values and blank strings across dataset columns."""

    @property
    def name(self) -> str:
        return "missing_analyzer"

    @property
    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ctx: AnalysisContext) -> ModuleResult:
        start_time = time.perf_counter()
        df: pd.DataFrame = ctx.df if ctx.df is not None else pd.DataFrame()

        params = {**DEFAULT_MISSING_PARAMETERS, **ctx.parameters.get(self.name, {})}
        treat_blanks = bool(params.get("treat_blank_strings_as_missing", True))
        custom_missing_strings = set(params.get("custom_missing_strings", []))
        low_thresh = float(params.get("low_threshold_pct", 5.0))
        med_thresh = float(params.get("medium_threshold_pct", 20.0))
        high_thresh = float(params.get("high_threshold_pct", 40.0))

        total_rows = int(len(df))
        total_cells = total_rows * int(len(df.columns))
        total_missing_cells = 0

        columns_metrics: Dict[str, Dict[str, Any]] = {}
        issues: List[QualityIssueData] = []
        now = datetime.now(timezone.utc)

        definition_str = (
            "null_values_and_blank_strings" if treat_blanks else "null_values_only"
        )
        if custom_missing_strings:
            definition_str += "_and_custom_tokens"

        for col_idx in range(len(df.columns)):
            col_name = df.columns[col_idx]
            series = df.iloc[:, col_idx]
            na_mask = series.isna()

            blank_mask = pd.Series(False, index=series.index)
            is_string_like = (
                pd.api.types.is_string_dtype(series)
                or pd.api.types.is_object_dtype(series)
                or str(series.dtype).lower() in ("str", "string", "object")
                or str(series.dtype).startswith("string")
            )
            if treat_blanks and is_string_like:
                blank_mask = series.map(lambda x: isinstance(x, str) and x.strip() == "")


            custom_mask = pd.Series(False, index=series.index)
            if custom_missing_strings:
                custom_mask = series.isin(custom_missing_strings)

            missing_mask = na_mask | blank_mask | custom_mask
            missing_count = int(missing_mask.sum())
            non_missing_count = total_rows - missing_count
            missing_pct = round((missing_count / total_rows) * 100.0, 2) if total_rows > 0 else 0.0

            total_missing_cells += missing_count

            columns_metrics[str(col_name)] = {
                "total_count": total_rows,
                "missing_count": missing_count,
                "missing_percentage": missing_pct,
                "non_missing_count": non_missing_count,
            }

            # Generate issue based on thresholds
            if missing_count > 0:
                if missing_pct <= low_thresh:
                    severity = Severity.LOW
                elif missing_pct <= med_thresh:
                    severity = Severity.MEDIUM
                elif missing_pct <= high_thresh:
                    severity = Severity.HIGH
                else:
                    severity = Severity.CRITICAL

                issues.append(
                    QualityIssueData(
                        module=self.name,
                        analyzer_version=self.version,
                        category="MISSING_VALUES",
                        severity=severity,
                        title=f"Missing values detected in '{col_name}'",
                        description=(
                            f"Column '{col_name}' has {missing_count} missing value(s) "
                            f"({missing_pct}% of {total_rows} total rows)."
                        ),
                        column_name=str(col_name),
                        parameters_used=to_json_safe(params),
                        evidence={
                            "missing_count": missing_count,
                            "total_count": total_rows,
                            "missing_percentage": missing_pct,
                            "non_missing_count": non_missing_count,
                            "definition": definition_str,
                        },
                        remediation_hint=(
                            "Investigate missingness mechanism (MCAR, MAR, MNAR) before "
                            "selecting an imputation strategy or row filtering."
                        ),
                        detected_at=now,
                    )
                )

        overall_missing_pct = (
            round((total_missing_cells / total_cells) * 100.0, 2) if total_cells > 0 else 0.0
        )
        missing_columns_count = len([c for c, m in columns_metrics.items() if m["missing_count"] > 0])

        metrics: Dict[str, Any] = {
            "columns": columns_metrics,
            "total_cells": total_cells,
            "total_missing_cells": total_missing_cells,
            "missing_columns_count": missing_columns_count,
            "overall_missing_percentage": overall_missing_pct,
        }

        # Shared cache for downstream analyzers
        ctx.shared_cache["missing_counts"] = {
            c: m["missing_count"] for c, m in columns_metrics.items()
        }
        ctx.shared_cache["non_null_counts"] = {
            c: m["non_missing_count"] for c, m in columns_metrics.items()
        }

        exec_time_ms = int((time.perf_counter() - start_time) * 1000)
        return ModuleResult(
            module_name=self.name,
            analyzer_version=self.version,
            execution_time_ms=exec_time_ms,
            metrics=to_json_safe(metrics),
            issues=issues,
        )
