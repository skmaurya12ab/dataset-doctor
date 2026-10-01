"""Deterministic data leakage analyzer detecting target identity, extreme correlation, and predictive purity."""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from app.core.json_utils import to_json_safe
from app.engine.base import AnalysisContext, BaseAnalyzer, ModuleResult, QualityIssueData, Severity
from app.engine.defaults import DEFAULT_LEAKAGE_PARAMETERS


class DataLeakageAnalyzer(BaseAnalyzer):
    """Detects potential target-derived features, extreme correlations, and post-outcome signals."""

    @property
    def name(self) -> str:
        return "leakage_analyzer"

    @property
    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ctx: AnalysisContext) -> ModuleResult:
        start_time = time.perf_counter()
        df: pd.DataFrame = ctx.df if ctx.df is not None else pd.DataFrame()

        params = {**DEFAULT_LEAKAGE_PARAMETERS, **ctx.parameters.get(self.name, {})}
        identity_thresh = float(params.get("identity_threshold", 0.99))
        corr_thresh = float(params.get("correlation_threshold", 0.99))
        purity_thresh = float(params.get("categorical_purity_threshold", 0.99))
        suspicious_keywords = [
            k.lower()
            for k in params.get(
                "suspicious_keywords",
                ["target", "label", "outcome", "result", "final", "approved", "churned", "future_"],
            )
        ]

        issues: List[QualityIssueData] = []
        now = datetime.now(timezone.utc)

        # Precondition: Target column must be provided and exist in dataframe
        target_col = ctx.target_column
        if not target_col:
            metrics = {
                "analysis_skipped": True,
                "reason": "target_column_not_provided",
            }
            exec_time_ms = int((time.perf_counter() - start_time) * 1000)
            return ModuleResult(
                module_name=self.name,
                analyzer_version=self.version,
                execution_time_ms=exec_time_ms,
                metrics=to_json_safe(metrics),
                issues=issues,
            )

        if target_col not in df.columns:
            metrics = {
                "analysis_skipped": True,
                "reason": "target_column_not_found",
                "target_column": target_col,
            }
            exec_time_ms = int((time.perf_counter() - start_time) * 1000)
            return ModuleResult(
                module_name=self.name,
                analyzer_version=self.version,
                execution_time_ms=exec_time_ms,
                metrics=to_json_safe(metrics),
                issues=issues,
            )

        target_series = df[target_col]
        total_rows = len(df)
        if total_rows < 10:
            metrics = {
                "analysis_skipped": True,
                "reason": "insufficient_rows_for_leakage_detection",
                "total_rows": total_rows,
            }
            exec_time_ms = int((time.perf_counter() - start_time) * 1000)
            return ModuleResult(
                module_name=self.name,
                analyzer_version=self.version,
                execution_time_ms=exec_time_ms,
                metrics=to_json_safe(metrics),
                issues=issues,
            )

        leakage_findings: List[Dict[str, Any]] = []
        target_is_numeric = (
            pd.api.types.is_numeric_dtype(target_series)
            and not pd.api.types.is_bool_dtype(target_series)
        )

        for col_idx in range(len(df.columns)):
            col_name = str(df.columns[col_idx])
            if col_name == target_col:
                continue

            feature_series = df.iloc[:, col_idx]

            # Signal A: Exact or Near-Exact Target Identity
            # Compare non-null aligned values
            aligned = pd.DataFrame({"target": target_series, "feature": feature_series}).dropna()
            if len(aligned) >= 10:
                match_count = int((aligned["target"] == aligned["feature"]).sum())
                match_ratio = round(match_count / len(aligned), 4)

                if match_ratio >= identity_thresh:
                    finding = {
                        "method": "target_identity",
                        "target_column": target_col,
                        "feature_column": col_name,
                        "match_ratio": match_ratio,
                        "threshold": identity_thresh,
                    }
                    leakage_findings.append(finding)
                    issues.append(
                        QualityIssueData(
                            module=self.name,
                            analyzer_version=self.version,
                            category="LEAKAGE",
                            severity=Severity.HIGH,
                            title=f"Potential target-derived feature: near identity with '{target_col}'",
                            description=(
                                f"Feature '{col_name}' exactly matches target '{target_col}' in "
                                f"{round(match_ratio * 100, 1)}% of rows. Potential leakage signal detected: "
                                "this feature may be a direct duplicate or derivative of the target variable."
                            ),
                            column_name=col_name,
                            parameters_used=to_json_safe(params),
                            evidence=to_json_safe(finding),
                            remediation_hint=(
                                "Verify data collection timing. Features that duplicate the target must be "
                                "excluded from the training matrix to prevent data leakage."
                            ),
                            detected_at=now,
                        )
                    )
                    continue

            # Signal B: Extreme Numerical Correlation with Target (|r| >= corr_thresh)
            feature_is_numeric = (
                pd.api.types.is_numeric_dtype(feature_series)
                and not pd.api.types.is_bool_dtype(feature_series)
            )

            if target_is_numeric and feature_is_numeric and len(aligned) >= 10:
                s_feat = pd.to_numeric(aligned["feature"], errors="coerce")
                s_targ = pd.to_numeric(aligned["target"], errors="coerce")
                if s_feat.std() > 0 and s_targ.std() > 0:
                    r_val = float(s_feat.corr(s_targ))
                    abs_r = abs(r_val)
                    if abs_r >= corr_thresh:
                        finding = {
                            "method": "extreme_numerical_correlation",
                            "target_column": target_col,
                            "feature_column": col_name,
                            "pearson_correlation": round(r_val, 4),
                            "abs_correlation": round(abs_r, 4),
                            "threshold": corr_thresh,
                        }
                        leakage_findings.append(finding)
                        issues.append(
                            QualityIssueData(
                                module=self.name,
                                analyzer_version=self.version,
                                category="LEAKAGE",
                                severity=Severity.HIGH,
                                title=f"Potential target leakage: near-perfect correlation with '{target_col}'",
                                description=(
                                    f"Feature '{col_name}' exhibits an extreme absolute correlation of {round(abs_r, 4)} "
                                    f"with target '{target_col}'. Potential leakage signal detected: verify whether this "
                                    "feature is available prior to the prediction event."
                                ),
                                column_name=col_name,
                                parameters_used=to_json_safe(params),
                                evidence=to_json_safe(finding),
                                remediation_hint=(
                                    "Review the temporal lineage of this feature. Ensure it is not calculated using "
                                    "information that only becomes available after the target event occurs."
                                ),
                                detected_at=now,
                            )
                        )
                        continue

            # Signal C: Perfect or Near-Perfect Categorical Correspondence (Conditional Purity)
            # Evaluate whether feature categories deterministically predict target classes
            target_is_discrete = (
                not target_is_numeric
                or target_series.nunique() <= 20
                or (ctx.problem_type and ctx.problem_type.lower() == "classification")
            )
            if target_is_discrete and len(aligned) >= 20 and feature_series.nunique() > 1:
                # Group by feature and calculate maximum target class count per group
                crosstab = pd.crosstab(aligned["feature"], aligned["target"])
                max_per_group = crosstab.max(axis=1).sum()
                conditional_purity = round(max_per_group / len(aligned), 4)

                if conditional_purity >= purity_thresh and crosstab.shape[0] < (len(aligned) * 0.5):
                    finding = {
                        "method": "conditional_purity",
                        "target_column": target_col,
                        "feature_column": col_name,
                        "conditional_purity": conditional_purity,
                        "threshold": purity_thresh,
                    }
                    leakage_findings.append(finding)
                    issues.append(
                        QualityIssueData(
                            module=self.name,
                            analyzer_version=self.version,
                            category="LEAKAGE",
                            severity=Severity.HIGH,
                            title=f"Potential target-derived feature: near-perfect mapping to '{target_col}'",
                            description=(
                                f"Feature '{col_name}' displays {round(conditional_purity * 100, 1)}% deterministic "
                                f"conditional purity relative to target '{target_col}'. Potential leakage signal detected: "
                                "this feature may represent an encoded or re-labeled version of the target outcome."
                            ),
                            column_name=col_name,
                            parameters_used=to_json_safe(params),
                            evidence=to_json_safe(finding),
                            remediation_hint=(
                                "Confirm whether this categorical attribute is determined concurrently with or "
                                "after the target label."
                            ),
                            detected_at=now,
                        )
                    )
                    continue

            # Signal D: Suspicious Feature Name (Contextual Signal - Strictly INFO Severity)
            col_lower = col_name.lower()
            matching_keywords = [
                kw for kw in suspicious_keywords
                if kw in col_lower or col_lower.startswith(kw) or col_lower.endswith(kw)
            ]
            if matching_keywords:
                finding = {
                    "method": "suspicious_naming",
                    "target_column": target_col,
                    "feature_column": col_name,
                    "matched_keywords": matching_keywords,
                }
                leakage_findings.append(finding)
                issues.append(
                    QualityIssueData(
                        module=self.name,
                        analyzer_version=self.version,
                        category="LEAKAGE",
                        severity=Severity.INFO,
                        title=f"Suspicious column name resembles outcome in '{col_name}'",
                        description=(
                            f"Column name '{col_name}' matches outcome keywords ({', '.join(matching_keywords)}). "
                            "Contextual review recommendation: verify that this feature does not capture post-outcome data."
                        ),
                        column_name=col_name,
                        parameters_used=to_json_safe(params),
                        evidence=to_json_safe(finding),
                        remediation_hint=(
                            "Column names alone do not constitute proof of leakage. Review feature dictionary documentation."
                        ),
                        detected_at=now,
                    )
                )

        metrics = {
            "target_column": target_col,
            "features_screened_count": len(df.columns) - 1,
            "leakage_findings_count": len(leakage_findings),
            "findings": leakage_findings,
        }

        exec_time_ms = int((time.perf_counter() - start_time) * 1000)
        return ModuleResult(
            module_name=self.name,
            analyzer_version=self.version,
            execution_time_ms=exec_time_ms,
            metrics=to_json_safe(metrics),
            issues=issues,
        )
