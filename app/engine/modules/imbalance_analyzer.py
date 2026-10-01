"""Deterministic class imbalance analyzer evaluating target class distributions and skew."""

from collections import Counter
from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from app.core.json_utils import to_json_safe
from app.engine.base import AnalysisContext, BaseAnalyzer, ModuleResult, QualityIssueData, Severity
from app.engine.defaults import DEFAULT_IMBALANCE_PARAMETERS


class ClassImbalanceAnalyzer(BaseAnalyzer):
    """Profiles target label distribution, calculating imbalance ratios and small class warnings."""

    @property
    def name(self) -> str:
        return "imbalance_analyzer"

    @property
    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ctx: AnalysisContext) -> ModuleResult:
        start_time = time.perf_counter()
        df: pd.DataFrame = ctx.df if ctx.df is not None else pd.DataFrame()

        params = {**DEFAULT_IMBALANCE_PARAMETERS, **ctx.parameters.get(self.name, {})}
        low_pct = float(params.get("binary_low_threshold_pct", 60.0))
        med_pct = float(params.get("binary_medium_threshold_pct", 75.0))
        high_pct = float(params.get("binary_high_threshold_pct", 90.0))
        crit_pct = float(params.get("binary_critical_threshold_pct", 95.0))
        tiny_thresh = int(params.get("tiny_class_sample_threshold", 10))

        issues: List[QualityIssueData] = []
        now = datetime.now(timezone.utc)

        # 1. Precondition Check: Target column must be specified
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

        # 2. Check Problem Type Precondition
        if ctx.problem_type and ctx.problem_type.lower() == "regression":
            metrics = {
                "analysis_skipped": True,
                "reason": "problem_type_is_regression",
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

        target_series = df[target_col].dropna()
        total_samples = int(len(target_series))

        if total_samples < 2:
            metrics = {
                "analysis_skipped": True,
                "reason": "insufficient_target_samples",
                "sample_count": total_samples,
            }
            exec_time_ms = int((time.perf_counter() - start_time) * 1000)
            return ModuleResult(
                module_name=self.name,
                analyzer_version=self.version,
                execution_time_ms=exec_time_ms,
                metrics=to_json_safe(metrics),
                issues=issues,
            )

        # Check for continuous numeric target when problem_type not explicitly classification
        unique_vals_count = int(target_series.nunique())
        is_float = pd.api.types.is_float_dtype(target_series)
        if is_float and unique_vals_count > 20 and ctx.problem_type != "classification":
            metrics = {
                "analysis_skipped": True,
                "reason": "target_appears_continuous_numerical",
                "unique_values_count": unique_vals_count,
            }
            exec_time_ms = int((time.perf_counter() - start_time) * 1000)
            return ModuleResult(
                module_name=self.name,
                analyzer_version=self.version,
                execution_time_ms=exec_time_ms,
                metrics=to_json_safe(metrics),
                issues=issues,
            )

        # 3. Calculate Class Distribution
        raw_counts = target_series.value_counts()
        class_dist: Dict[str, int] = {str(k): int(v) for k, v in raw_counts.items()}
        class_percentages: Dict[str, float] = {
            str(k): round((int(v) / total_samples) * 100.0, 2) for k, v in raw_counts.items()
        }

        class_count = len(class_dist)
        if class_count < 2:
            metrics = {
                "analysis_skipped": True,
                "reason": "single_class_target",
                "class_count": class_count,
                "class_distribution": class_dist,
            }
            exec_time_ms = int((time.perf_counter() - start_time) * 1000)
            return ModuleResult(
                module_name=self.name,
                analyzer_version=self.version,
                execution_time_ms=exec_time_ms,
                metrics=to_json_safe(metrics),
                issues=issues,
            )

        sorted_classes = sorted(class_dist.items(), key=lambda x: x[1], reverse=True)
        majority_class, majority_count = sorted_classes[0]
        minority_class, minority_count = sorted_classes[-1]

        majority_pct = class_percentages[majority_class]
        minority_pct = class_percentages[minority_class]

        imbalance_ratio = (
            round(majority_count / minority_count, 2) if minority_count > 0 else float("inf")
        )

        tiny_classes = [c for c, count in class_dist.items() if count < tiny_thresh]
        has_tiny_classes = len(tiny_classes) > 0

        metrics = {
            "analysis_skipped": False,
            "target_column": target_col,
            "total_samples": total_samples,
            "class_count": class_count,
            "class_distribution": class_dist,
            "class_percentages": class_percentages,
            "majority_class": majority_class,
            "minority_class": minority_class,
            "majority_count": majority_count,
            "minority_count": minority_count,
            "majority_percentage": majority_pct,
            "minority_percentage": minority_pct,
            "imbalance_ratio": imbalance_ratio,
            "has_tiny_classes": has_tiny_classes,
        }

        # 4. Severity Assessment
        if class_count == 2:
            # Binary Classification
            severity = self._determine_binary_severity(majority_pct)
            if severity is not None:
                issues.append(
                    QualityIssueData(
                        module=self.name,
                        analyzer_version=self.version,
                        category="CLASS_IMBALANCE",
                        severity=severity,
                        title=f"Class imbalance detected in target '{target_col}'",
                        description=(
                            f"Target '{target_col}' has a binary class imbalance: majority class '{majority_class}' "
                            f"constitutes {majority_pct}% of samples ({majority_count}/{total_samples}), "
                            f"yielding an imbalance ratio of {imbalance_ratio}:1."
                        ),
                        column_name=target_col,
                        parameters_used=to_json_safe(params),
                        evidence=to_json_safe(metrics),
                        remediation_hint=(
                            "Consider stratified train-test splits, class-weighted objective functions, "
                            "resampling strategies (e.g. SMOTE, random undersampling), or threshold calibration."
                        ),
                        detected_at=now,
                    )
                )
        else:
            # Multiclass Classification
            expected_balanced_pct = 100.0 / class_count
            if minority_pct < expected_balanced_pct * 0.3 or majority_pct > 60.0:
                if minority_pct < 2.0 or majority_pct > 80.0:
                    severity = Severity.HIGH
                elif minority_pct < 5.0 or majority_pct > 70.0:
                    severity = Severity.MEDIUM
                else:
                    severity = Severity.LOW

                issues.append(
                    QualityIssueData(
                        module=self.name,
                        analyzer_version=self.version,
                        category="CLASS_IMBALANCE",
                        severity=severity,
                        title=f"Multiclass imbalance in target '{target_col}'",
                        description=(
                            f"Target '{target_col}' ({class_count} classes) shows uneven class density: "
                            f"majority '{majority_class}' has {majority_pct}%, while minority '{minority_class}' "
                            f"has {minority_pct}% (imbalance ratio: {imbalance_ratio}:1)."
                        ),
                        column_name=target_col,
                        parameters_used=to_json_safe(params),
                        evidence=to_json_safe(metrics),
                        remediation_hint="Use balanced class weighting, focal loss, or macro-averaged evaluation metrics.",
                        detected_at=now,
                    )
                )

        # 5. Check for Tiny Classes (< tiny_thresh samples)
        if tiny_classes:
            tiny_class_details = [{"class": str(c), "count": int(class_dist[c])} for c in tiny_classes]
            issues.append(
                QualityIssueData(
                    module=self.name,
                    analyzer_version=self.version,
                    category="CLASS_IMBALANCE",
                    severity=Severity.LOW,
                    title=f"Critically small class count (tiny class) in target '{target_col}'",
                    description=(
                        f"Target '{target_col}' contains {len(tiny_classes)} class(es) with fewer than "
                        f"{tiny_thresh} samples: {', '.join(tiny_classes)}. Small sample sizes prevent reliable "
                        "cross-validation and evaluation."
                    ),
                    column_name=target_col,
                    parameters_used=to_json_safe(params),
                    evidence={
                        "tiny_classes": tiny_class_details,
                        "tiny_class_names": tiny_classes,
                        "counts": {c: class_dist[c] for c in tiny_classes},
                        "threshold": tiny_thresh,
                    },
                    remediation_hint="Group infrequent labels into an 'Other' category or collect additional observations.",
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

    def _determine_binary_severity(self, majority_pct: float) -> Optional[Severity]:
        """Determine heuristic severity for binary classification majority percentage."""
        if majority_pct > 95.0:
            return Severity.CRITICAL
        elif majority_pct > 90.0:
            return Severity.HIGH
        elif majority_pct > 75.0:
            return Severity.MEDIUM
        elif majority_pct > 60.0:
            return Severity.LOW
        return None
