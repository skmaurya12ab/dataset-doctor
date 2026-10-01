"""Deterministic distribution analyzer profiling central tendency, skewness, kurtosis, and normality."""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List
import numpy as np
import pandas as pd
from scipy import stats

from app.core.json_utils import to_json_safe
from app.engine.base import AnalysisContext, BaseAnalyzer, ModuleResult, QualityIssueData, Severity
from app.engine.defaults import DEFAULT_DISTRIBUTION_PARAMETERS


class DistributionAnalyzer(BaseAnalyzer):
    """Profiles numerical distribution parameters, excess kurtosis, skewness, and normality."""

    @property
    def name(self) -> str:
        return "distribution_analyzer"

    @property
    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ctx: AnalysisContext) -> ModuleResult:
        start_time = time.perf_counter()
        df: pd.DataFrame = ctx.df if ctx.df is not None else pd.DataFrame()

        params = {**DEFAULT_DISTRIBUTION_PARAMETERS, **ctx.parameters.get(self.name, {})}
        skew_low = float(params.get("skew_low_threshold", 1.0))
        skew_med = float(params.get("skew_medium_threshold", 2.0))
        skew_high = float(params.get("skew_high_threshold", 3.0))
        norm_max_sample = int(params.get("normality_test_sample_size", 5_000))
        norm_min_sample = int(params.get("normality_min_sample_size", 20))
        seed = int(params.get("random_seed", 42))

        column_metrics: Dict[str, Dict[str, Any]] = {}
        issues: List[QualityIssueData] = []
        now = datetime.now(timezone.utc)

        # Retrieve numeric columns from shared cache or inspect
        numeric_cols = ctx.shared_cache.get("numeric_columns")
        if numeric_cols is None:
            numeric_cols = []
            for i in range(len(df.columns)):
                series = df.iloc[:, i]
                if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
                    numeric_cols.append(str(df.columns[i]))

        for col_name in numeric_cols:
            series = pd.to_numeric(df[col_name], errors="coerce").dropna()
            non_null_count = int(len(series))

            if non_null_count < 3:
                column_metrics[col_name] = {
                    "skipped": True,
                    "reason": "insufficient_samples",
                    "count": non_null_count,
                }
                continue

            vals = series.to_numpy(dtype=float)
            std_val = float(np.std(vals, ddof=1)) if non_null_count > 1 else 0.0

            # Suppress constant distributions (std == 0) — handled by cardinality analyzer
            if std_val == 0.0:
                column_metrics[col_name] = {
                    "count": non_null_count,
                    "mean": float(vals[0]),
                    "median": float(vals[0]),
                    "std": 0.0,
                    "min": float(vals[0]),
                    "max": float(vals[0]),
                    "skipped_distribution": True,
                    "reason": "constant_feature",
                }
                continue

            mean_val = float(np.mean(vals))
            median_val = float(np.median(vals))
            min_val = float(np.min(vals))
            max_val = float(np.max(vals))
            q1_val = float(np.percentile(vals, 25))
            q3_val = float(np.percentile(vals, 75))

            # Skewness and excess kurtosis (Fisher definition: normal = 0.0)
            skew_val = float(stats.skew(vals, bias=False)) if non_null_count >= 3 else 0.0
            kurt_val = float(stats.kurtosis(vals, fisher=True, bias=False)) if non_null_count >= 4 else 0.0

            # Normality testing using D'Agostino's K-squared test
            normality_test_result: Dict[str, Any] = {
                "eligible": False,
                "test_name": "skipped_insufficient_samples",
                "sample_size": non_null_count,
            }
            if non_null_count >= norm_min_sample:
                test_sample = vals
                if non_null_count > norm_max_sample:
                    rng = np.random.default_rng(seed)
                    test_sample = rng.choice(vals, size=norm_max_sample, replace=False)

                try:
                    k2_stat, p_val = stats.normaltest(test_sample)
                    normality_test_result = {
                        "eligible": True,
                        "test_name": "dagostino_k_squared",
                        "statistic": round(float(k2_stat), 4),
                        "p_value": float(p_val),
                        "sample_size": len(test_sample),
                        "is_normal_p05": bool(p_val >= 0.05),
                    }
                except Exception as e:
                    normality_test_result = {"eligible": True, "error": str(e)}

            col_metric_entry = {
                "count": non_null_count,
                "mean": round(mean_val, 4),
                "median": round(median_val, 4),
                "std": round(std_val, 4),
                "min": round(min_val, 4),
                "max": round(max_val, 4),
                "q1": round(q1_val, 4),
                "q3": round(q3_val, 4),
                "skewness": round(skew_val, 4),
                "kurtosis": round(kurt_val, 4),
                "normality_test": normality_test_result,
            }
            column_metrics[col_name] = col_metric_entry

            # Evaluate Skewness Severity (Advisory finding)
            abs_skew = abs(skew_val)
            if abs_skew >= skew_low:
                if abs_skew >= skew_high:
                    severity = Severity.HIGH
                elif abs_skew >= skew_med:
                    severity = Severity.MEDIUM
                else:
                    severity = Severity.LOW

                direction = "right-skewed (positive)" if skew_val > 0 else "left-skewed (negative)"
                issues.append(
                    QualityIssueData(
                        module=self.name,
                        analyzer_version=self.version,
                        category="DISTRIBUTION",
                        severity=severity,
                        title=f"Skewed distribution detected in '{col_name}'",
                        description=(
                            f"The distribution of '{col_name}' is {direction} (skewness: {round(skew_val, 2)}, "
                            f"kurtosis: {round(kurt_val, 2)}) and may affect models or transformations "
                            "sensitive to scale or normality assumptions."
                        ),
                        column_name=col_name,
                        parameters_used=to_json_safe(params),
                        evidence={
                            "skewness": round(skew_val, 4),
                            "kurtosis": round(kurt_val, 4),
                            "mean": round(mean_val, 4),
                            "median": round(median_val, 4),
                            "std": round(std_val, 4),
                            "normality_test": normality_test_result,
                        },
                        remediation_hint=(
                            "Consider applying power or logarithmic transforms (e.g. log1p, Box-Cox, Yeo-Johnson) "
                            "if downstream estimators assume symmetric feature distributions."
                        ),
                        detected_at=now,
                    )
                )

        metrics: Dict[str, Any] = {
            "columns": column_metrics,
            "skewed_columns_count": len([i for i in issues if i.category == "DISTRIBUTION"]),
        }

        exec_time_ms = int((time.perf_counter() - start_time) * 1000)
        return ModuleResult(
            module_name=self.name,
            analyzer_version=self.version,
            execution_time_ms=exec_time_ms,
            metrics=to_json_safe(metrics),
            issues=issues,
        )
