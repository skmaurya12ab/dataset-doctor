"""Deterministic outlier analyzer applying IQR, MAD, and Isolation Forest."""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.core.json_utils import to_json_safe
from app.engine.base import AnalysisContext, BaseAnalyzer, ModuleResult, QualityIssueData, Severity
from app.engine.defaults import DEFAULT_OUTLIER_PARAMETERS


class OutlierAnalyzer(BaseAnalyzer):
    """Detects numerical anomalies using IQR, Median Absolute Deviation (MAD), and Isolation Forest."""

    def __init__(self, parameters: Optional[Dict[str, Any]] = None):
        self.default_params = parameters or {}

    @property
    def name(self) -> str:
        return "outlier_analyzer"

    @property
    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ctx: AnalysisContext) -> ModuleResult:
        start_time = time.perf_counter()
        df: pd.DataFrame = ctx.df if ctx.df is not None else pd.DataFrame()

        params = {
            **DEFAULT_OUTLIER_PARAMETERS,
            **self.default_params,
            **ctx.parameters.get(self.name, {}),
        }
        iqr_mult = float(params.get("iqr_multiplier", 1.5))
        mad_thresh = float(params.get("mad_threshold", 3.5))
        max_samples = int(params.get("maximum_sample_size", 50_000))
        seed = int(params.get("random_seed", 42))
        info_pct = float(params.get("info_threshold_pct", 1.0))
        low_pct = float(params.get("low_threshold_pct", 5.0))
        med_pct = float(params.get("medium_threshold_pct", 10.0))
        high_pct = float(params.get("high_threshold_pct", 20.0))
        enable_iforest = bool(params.get("enable_isolation_forest", True))

        column_metrics: Dict[str, Dict[str, Any]] = {}
        issues: List[QualityIssueData] = []
        now = datetime.now(timezone.utc)

        # Identify numeric columns with at least some valid non-null entries
        numeric_cols: List[str] = []
        for i in range(len(df.columns)):
            col_name = str(df.columns[i])
            series = df.iloc[:, i]
            if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
                s_valid = pd.to_numeric(series, errors="coerce").dropna()
                if len(s_valid) >= 4:
                    numeric_cols.append(col_name)

        # Store in shared cache for downstream analyzers
        ctx.shared_cache["numeric_columns"] = numeric_cols

        # 1. Univariate Analysis per Numeric Column
        for col_name in numeric_cols:
            series = pd.to_numeric(df[col_name], errors="coerce").dropna()
            total_non_null = int(len(series))

            vals = series.to_numpy(dtype=float)
            q1 = float(np.percentile(vals, 25))
            q3 = float(np.percentile(vals, 75))
            iqr = round(q3 - q1, 6)

            # Method B: Median Absolute Deviation (MAD)
            med = float(np.median(vals))
            abs_devs = np.abs(vals - med)
            mad = float(np.median(abs_devs))

            mad_outlier_count = 0
            mad_outlier_pct = 0.0

            if mad > 0.0:
                mod_z_scores = 0.6745 * abs_devs / mad
                mad_mask = mod_z_scores > mad_thresh
                mad_outlier_count = int(np.sum(mad_mask))
                mad_outlier_pct = round((mad_outlier_count / total_non_null) * 100.0, 2)
                mad_evidence = {
                    "median": med,
                    "mad": mad,
                    "outlier_count": mad_outlier_count,
                    "outlier_percentage": mad_outlier_pct,
                    "mad_outlier_count": mad_outlier_count,
                    "mad_outlier_percentage": mad_outlier_pct,
                    "threshold_applied": mad_thresh,
                }
            else:
                mad_evidence = {
                    "median": med,
                    "mad": 0.0,
                    "outlier_count": 0,
                    "outlier_percentage": 0.0,
                    "mad_outlier_count": 0,
                    "mad_outlier_percentage": 0.0,
                    "skipped": "zero_mad",
                }

            # Method A: IQR
            if iqr == 0.0:
                # If IQR is 0, do not create an IQR outlier issue (cardinality analyzer handles constant/near-constant)
                column_metrics[col_name] = {
                    "q1": q1,
                    "q3": q3,
                    "iqr": 0.0,
                    "outlier_count": 0,
                    "outlier_percentage": 0.0,
                    "iqr_method": {
                        "q1": q1,
                        "q3": q3,
                        "iqr": 0.0,
                        "outlier_count": 0,
                        "outlier_percentage": 0.0,
                        "skipped": True,
                        "reason": "zero_iqr",
                    },
                    "mad_method": mad_evidence,
                    "mad_evidence": mad_evidence,
                    "skipped_iqr": True,
                    "reason": "zero_iqr",
                    "total_non_null": total_non_null,
                }
                continue

            lower_bound = round(q1 - iqr_mult * iqr, 6)
            upper_bound = round(q3 + iqr_mult * iqr, 6)

            iqr_outliers_mask = (vals < lower_bound) | (vals > upper_bound)
            iqr_outlier_count = int(np.sum(iqr_outliers_mask))
            iqr_outlier_pct = round((iqr_outlier_count / total_non_null) * 100.0, 2)

            # Method B: Median Absolute Deviation (MAD)
            med = float(np.median(vals))
            abs_devs = np.abs(vals - med)
            mad = float(np.median(abs_devs))

            mad_outlier_count = 0
            mad_outlier_pct = 0.0

            if mad > 0.0:
                # Modified Z-score: 0.6745 * |x - median| / MAD
                mod_z_scores = 0.6745 * abs_devs / mad
                mad_mask = mod_z_scores > mad_thresh
                mad_outlier_count = int(np.sum(mad_mask))
                mad_outlier_pct = round((mad_outlier_count / total_non_null) * 100.0, 2)
                mad_evidence = {
                    "median": med,
                    "mad": mad,
                    "outlier_count": mad_outlier_count,
                    "outlier_percentage": mad_outlier_pct,
                    "mad_outlier_count": mad_outlier_count,
                    "mad_outlier_percentage": mad_outlier_pct,
                    "threshold_applied": mad_thresh,
                }
            else:
                mad_evidence = {
                    "median": med,
                    "mad": 0.0,
                    "outlier_count": 0,
                    "outlier_percentage": 0.0,
                    "mad_outlier_count": 0,
                    "mad_outlier_percentage": 0.0,
                    "skipped": "zero_mad",
                }

            iqr_data = {
                "outlier_count": iqr_outlier_count,
                "outlier_percentage": iqr_outlier_pct,
                "q1": q1,
                "q3": q3,
                "iqr": iqr,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "total_non_null": total_non_null,
            }

            col_metric_entry = {
                "total_non_null": total_non_null,
                "q1": q1,
                "q3": q3,
                "iqr": iqr,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "outlier_count": iqr_outlier_count,
                "outlier_percentage": iqr_outlier_pct,
                "iqr_method": iqr_data,
                "mad_method": mad_evidence,
                "mad_evidence": mad_evidence,
            }
            column_metrics[col_name] = col_metric_entry

            # Determine severity based on affected percentage
            if iqr_outlier_count > 0:
                if iqr_outlier_pct <= info_pct:
                    severity = Severity.INFO
                elif iqr_outlier_pct <= low_pct:
                    severity = Severity.LOW
                elif iqr_outlier_pct <= med_pct:
                    severity = Severity.MEDIUM
                elif iqr_outlier_pct <= high_pct:
                    severity = Severity.HIGH
                else:
                    severity = Severity.CRITICAL

                issues.append(
                    QualityIssueData(
                        module=self.name,
                        analyzer_version=self.version,
                        category="OUTLIERS",
                        severity=severity,
                        title=f"Potential anomalous observations in '{col_name}'",
                        description=(
                            f"Column '{col_name}' contains {iqr_outlier_count} potential outlier(s) "
                            f"({iqr_outlier_pct}% of non-null observations) falling outside IQR boundaries "
                            f"[{lower_bound}, {upper_bound}]."
                        ),
                        column_name=col_name,
                        parameters_used=to_json_safe(params),
                        evidence={
                            "method": "IQR",
                            "column": col_name,
                            "outlier_count": iqr_outlier_count,
                            "total_non_null": total_non_null,
                            "outlier_percentage": iqr_outlier_pct,
                            "q1": q1,
                            "q3": q3,
                            "iqr": iqr,
                            "lower_bound": lower_bound,
                            "upper_bound": upper_bound,
                            "mad_evidence": mad_evidence,
                        },
                        remediation_hint=(
                            "Investigate whether extreme values reflect legitimate domain tails or "
                            "data entry errors before selecting winsorization, trimming, or robust scaling."
                        ),
                        detected_at=now,
                    )
                )

        # 2. Method C: Multivariate Isolation Forest
        iforest_summary: Dict[str, Any] = {"status": "skipped"}
        if enable_iforest and len(numeric_cols) >= 2 and len(df) >= 20:
            try:
                # Prepare numeric matrix with median imputation for fitting
                num_df = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
                non_const_cols = [c for c in numeric_cols if num_df[c].std(skipna=True) > 0]

                if len(non_const_cols) >= 2:
                    imputed = num_df[non_const_cols].fillna(num_df[non_const_cols].median())
                    n_rows = len(imputed)
                    sampled = False
                    sample_size = n_rows

                    if n_rows > max_samples:
                        imputed = imputed.sample(n=max_samples, random_state=seed)
                        sampled = True
                        sample_size = max_samples

                    contamination = params.get("isolation_forest_contamination", "auto")
                    iso = IsolationForest(
                        contamination=contamination,
                        random_state=seed,
                        n_estimators=100,
                    )
                    preds = iso.fit_predict(imputed)
                    anomalies_count = int(np.sum(preds == -1))
                    anomalies_pct = round((anomalies_count / sample_size) * 100.0, 2)

                    iforest_summary = {
                        "status": "completed",
                        "outlier_count": anomalies_count,
                        "outlier_percentage": anomalies_pct,
                        "multivariate_outlier_count": anomalies_count,
                        "multivariate_outlier_percentage": anomalies_pct,
                        "features_used": non_const_cols,
                        "sample_size": sample_size,
                        "sampled": sampled,
                        "sampling_applied": sampled,
                        "random_seed": seed,
                    }
            except Exception as e:
                iforest_summary = {"status": "error", "error": str(e)}

        metrics: Dict[str, Any] = {
            "columns_analyzed_count": len(numeric_cols),
            "columns": column_metrics,
            "columns_with_outliers_count": len([c for c, m in column_metrics.items() if m.get("outlier_count", 0) > 0]),
            "isolation_forest_summary": iforest_summary,
            "multivariate_isolation_forest": iforest_summary,
        }

        exec_time_ms = int((time.perf_counter() - start_time) * 1000)
        return ModuleResult(
            module_name=self.name,
            analyzer_version=self.version,
            execution_time_ms=exec_time_ms,
            metrics=to_json_safe(metrics),
            issues=issues,
        )
