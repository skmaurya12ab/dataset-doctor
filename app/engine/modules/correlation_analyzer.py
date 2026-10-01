"""Deterministic correlation analyzer computing pairwise Pearson/Spearman multicollinearity and target signals."""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from app.core.json_utils import to_json_safe
from app.engine.base import AnalysisContext, BaseAnalyzer, ModuleResult, QualityIssueData, Severity
from app.engine.defaults import DEFAULT_CORRELATION_PARAMETERS


class CorrelationAnalyzer(BaseAnalyzer):
    """Calculates pairwise Pearson and Spearman correlations, identifying severe multicollinearity."""

    def __init__(self, parameters: Optional[Dict[str, Any]] = None):
        self.default_params = parameters or {}

    @property
    def name(self) -> str:
        return "correlation_analyzer"

    @property
    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ctx: AnalysisContext) -> ModuleResult:
        start_time = time.perf_counter()
        df: pd.DataFrame = ctx.df if ctx.df is not None else pd.DataFrame()

        params = {
            **DEFAULT_CORRELATION_PARAMETERS,
            **self.default_params,
            **ctx.parameters.get(self.name, {}),
        }
        threshold = float(params.get("correlation_threshold", 0.90))
        med_thresh = float(params.get("medium_threshold", 0.95))
        high_thresh = float(params.get("high_threshold", 0.99))
        max_features = int(params.get("max_features", 100))
        max_samples = int(params.get("max_sample_size", params.get("sample_size", 50_000)))
        seed = int(params.get("random_seed", 42))
        compute_spearman = bool(params.get("compute_spearman", True))

        issues: List[QualityIssueData] = []
        now = datetime.now(timezone.utc)

        # 1. Identify non-constant numeric columns
        numeric_candidates: List[str] = []
        for i in range(len(df.columns)):
            col_name = str(df.columns[i])
            series = df.iloc[:, i]
            if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
                numeric_candidates.append(col_name)

        # Drop constant columns (std == 0)
        eligible_cols: List[str] = []
        for col in numeric_candidates:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(s) > 1 and float(s.std(ddof=1)) > 0.0:
                eligible_cols.append(col)

        if len(eligible_cols) < 2:
            metrics = {
                "analysis_skipped": True,
                "reason": "insufficient_non_constant_numeric_features",
                "eligible_feature_count": len(eligible_cols),
            }
            exec_time_ms = int((time.perf_counter() - start_time) * 1000)
            return ModuleResult(
                module_name=self.name,
                analyzer_version=self.version,
                execution_time_ms=exec_time_ms,
                metrics=to_json_safe(metrics),
                issues=issues,
            )

        # Wide dataset safeguard
        analysis_limited = False
        total_eligible = len(eligible_cols)
        if total_eligible > max_features:
            eligible_cols = eligible_cols[:max_features]
            analysis_limited = True

        # Extract numeric dataframe
        num_df = df[eligible_cols].apply(pd.to_numeric, errors="coerce")

        # Sampling safeguard
        n_rows = len(num_df)
        sampling_applied = False
        sample_size = n_rows
        if n_rows > max_samples:
            num_df = num_df.sample(n=max_samples, random_state=seed)
            sampling_applied = True
            sample_size = max_samples

        # 2. Compute Pearson Correlation Matrix
        pearson_corr = num_df.corr(method="pearson")

        # 3. Optional Spearman Correlation Matrix
        spearman_corr: Optional[pd.DataFrame] = None
        if compute_spearman:
            try:
                spearman_corr = num_df.corr(method="spearman")
            except Exception:
                spearman_corr = None

        # 4. Target Correlation Analysis (if numeric target provided)
        target_correlations: Dict[str, float] = {}
        target_col = ctx.target_column
        if target_col and target_col in eligible_cols:
            for col in eligible_cols:
                if col != target_col:
                    r_val = pearson_corr.loc[target_col, col]
                    if not pd.isna(r_val):
                        target_correlations[col] = round(float(r_val), 4)

        # 5. Extract Upper Triangle Unique Feature Pairs
        high_corr_pairs: List[Dict[str, Any]] = []
        n_features = len(eligible_cols)

        for i in range(n_features):
            feat_a = eligible_cols[i]
            for j in range(i + 1, n_features):
                feat_b = eligible_cols[j]
                r_val = pearson_corr.loc[feat_a, feat_b]

                if pd.isna(r_val):
                    continue

                r_float = float(r_val)
                abs_r = abs(r_float)

                spearman_val = None
                if spearman_corr is not None:
                    sp_val = spearman_corr.loc[feat_a, feat_b]
                    if not pd.isna(sp_val):
                        spearman_val = round(float(sp_val), 4)

                pair_entry = {
                    "feature_a": feat_a,
                    "feature_b": feat_b,
                    "pearson_correlation": round(r_float, 4),
                    "abs_pearson_correlation": round(abs_r, 4),
                    "pearson": round(r_float, 4),
                    "abs_pearson": round(abs_r, 4),
                    "spearman_correlation": spearman_val,
                    "spearman": spearman_val,
                }

                if abs_r >= threshold:
                    high_corr_pairs.append(pair_entry)

                    severity = self._determine_severity(abs_r)
                    if severity is not None:
                        issues.append(
                            QualityIssueData(
                                module=self.name,
                                analyzer_version=self.version,
                                category="CORRELATION",
                                severity=severity,
                                title=f"High feature correlation between '{feat_a}' and '{feat_b}'",
                                description=(
                                    f"Features '{feat_a}' and '{feat_b}' have an absolute Pearson correlation of "
                                    f"{round(abs_r, 3)} (r = {round(r_float, 3)}). Strong multicollinearity can "
                                    "destabilize linear models and inflate feature importance variance."
                                ),
                                column_name=feat_a,
                                parameters_used=to_json_safe(params),
                                evidence=to_json_safe(pair_entry),
                                remediation_hint=(
                                    "Assess whether both features provide unique information. Consider dropping one "
                                    "collinear feature or applying dimensionality reduction (e.g. PCA)."
                                ),
                                detected_at=now,
                            )
                        )

        # Sort high correlation pairs descending by absolute correlation
        high_corr_pairs.sort(key=lambda p: p["abs_pearson_correlation"], reverse=True)

        if analysis_limited:
            issues.append(
                QualityIssueData(
                    module=self.name,
                    analyzer_version=self.version,
                    category="CORRELATION",
                    severity=Severity.INFO,
                    title="Correlation analysis limited by feature cap",
                    description=(
                        f"Dataset contains {total_eligible} numeric features, exceeding the maximum "
                        f"feature threshold of {max_features}. Analysis was restricted to the first {max_features} "
                        "features to preserve computational bounds."
                    ),
                    column_name=None,
                    parameters_used=to_json_safe(params),
                    evidence={"total_features": total_eligible, "max_features": max_features},
                    remediation_hint="Increase 'max_features' in analysis parameters if full matrix computation is required.",
                    detected_at=now,
                )
            )

        excluded_const = [c for c in numeric_candidates if c not in eligible_cols]
        metrics: Dict[str, Any] = {
            "eligible_features": eligible_cols,
            "columns_analyzed": eligible_cols,
            "excluded_constant_columns": excluded_const,
            "total_eligible_features": total_eligible,
            "analysis_limited": analysis_limited,
            "max_features_cap": max_features,
            "sampling_applied": sampling_applied,
            "sample_size": sample_size,
            "random_seed": seed,
            "high_correlation_pairs_count": len(high_corr_pairs),
            "high_correlation_pairs": high_corr_pairs,
            "target_correlations": {
                c: {
                    "pearson": val,
                    "abs_pearson": abs(val),
                    "pearson_correlation": val,
                    "abs_pearson_correlation": abs(val),
                }
                for c, val in target_correlations.items()
            },
        }

        exec_time_ms = int((time.perf_counter() - start_time) * 1000)
        return ModuleResult(
            module_name=self.name,
            analyzer_version=self.version,
            execution_time_ms=exec_time_ms,
            metrics=to_json_safe(metrics),
            issues=issues,
        )

    def _determine_severity(self, abs_r: float) -> Optional[Severity]:
        """Determine heuristic severity for an absolute correlation value."""
        if abs_r >= 0.99:
            return Severity.HIGH
        elif abs_r >= 0.95:
            return Severity.MEDIUM
        elif abs_r >= 0.90:
            return Severity.LOW
        return None
