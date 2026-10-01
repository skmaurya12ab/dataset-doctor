"""Deterministic cardinality analyzer detecting constant, near-constant, and identifier columns."""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List
import pandas as pd

from app.core.json_utils import to_json_safe
from app.engine.base import AnalysisContext, BaseAnalyzer, ModuleResult, QualityIssueData, Severity
from app.engine.defaults import DEFAULT_CARDINALITY_PARAMETERS


class CardinalityAnalyzer(BaseAnalyzer):
    """Inspects distinct value distributions, detecting constant, near-constant, and ID columns."""

    @property
    def name(self) -> str:
        return "cardinality_analyzer"

    @property
    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ctx: AnalysisContext) -> ModuleResult:
        start_time = time.perf_counter()
        df: pd.DataFrame = ctx.df if ctx.df is not None else pd.DataFrame()

        params = {**DEFAULT_CARDINALITY_PARAMETERS, **ctx.parameters.get(self.name, {})}
        near_constant_thresh = float(params.get("near_constant_ratio_threshold", 0.01))
        high_card_count = int(params.get("high_cardinality_unique_count", 50))
        id_unique_ratio_thresh = float(params.get("identifier_unique_ratio_threshold", 0.95))
        id_keywords = [k.lower() for k in params.get("identifier_keywords", ["id", "uuid", "email", "key"])]

        total_rows = int(len(df))
        column_metrics: Dict[str, Dict[str, Any]] = {}
        issues: List[QualityIssueData] = []
        now = datetime.now(timezone.utc)

        constant_cols_count = 0
        high_card_cols_count = 0

        for col_idx in range(len(df.columns)):
            col_name = df.columns[col_idx]
            series = df.iloc[:, col_idx]
            non_null_series = series.dropna()
            non_null_count = int(len(non_null_series))


            # Retrieve dtype category from context if available, otherwise deduce
            dtype_cat = ctx.inferred_types.get(str(col_name))
            if not dtype_cat:
                if pd.api.types.is_numeric_dtype(series):
                    dtype_cat = "numeric"
                elif pd.api.types.is_bool_dtype(series):
                    dtype_cat = "boolean"
                elif pd.api.types.is_datetime64_any_dtype(series):
                    dtype_cat = "datetime"
                else:
                    dtype_cat = "categorical" if isinstance(series.dtype, pd.CategoricalDtype) else "string"

            # Calculate unique count handling unhashable objects
            if non_null_count == 0:
                unique_count = 0
                unique_ratio = 0.0
            else:
                try:
                    unique_count = int(non_null_series.nunique())
                except TypeError:
                    safe_series = non_null_series.map(
                        lambda x: str(x) if isinstance(x, (dict, list, set)) else x
                    )
                    unique_count = int(safe_series.nunique())
                unique_ratio = round(unique_count / non_null_count, 4)

            column_metrics[str(col_name)] = {
                "total_count": total_rows,
                "non_null_count": non_null_count,
                "unique_count": unique_count,
                "unique_ratio": unique_ratio,
                "dtype_category": dtype_cat,
            }

            # If column has 0 non-null values, MissingValueAnalyzer handles 100% missing
            if non_null_count == 0:
                continue

            col_str_lower = str(col_name).lower()
            name_looks_id = any(
                kw == col_str_lower
                or col_str_lower.endswith(f"_{kw}")
                or col_str_lower.startswith(f"{kw}_")
                or kw in col_str_lower
                for kw in id_keywords
            )

            # 1. Constant Column (unique_count == 1)
            if unique_count == 1:
                constant_cols_count += 1
                issues.append(
                    QualityIssueData(
                        module=self.name,
                        analyzer_version=self.version,
                        category="CARDINALITY",
                        severity=Severity.MEDIUM,
                        title="Constant column detected",
                        description=(
                            f"Column '{col_name}' has only 1 distinct non-null value across "
                            f"{non_null_count} rows. Zero-variance features carry no predictive signal."
                        ),
                        column_name=str(col_name),
                        parameters_used=to_json_safe(params),
                        evidence={
                            "unique_count": 1,
                            "non_null_count": non_null_count,
                            "unique_ratio": unique_ratio,
                        },
                        remediation_hint="Consider dropping constant zero-variance columns prior to model training.",
                        detected_at=now,
                    )
                )
                continue

            # 2. Identifier-like high-cardinality column (unique_ratio >= 0.95)
            # Checked before high-cardinality categorical to avoid duplicate warnings
            if unique_ratio >= id_unique_ratio_thresh and non_null_count >= 5:
                issues.append(
                    QualityIssueData(
                        module=self.name,
                        analyzer_version=self.version,
                        category="CARDINALITY",
                        severity=Severity.INFO,
                        title="Identifier-like high-cardinality column",
                        description=(
                            f"Column '{col_name}' has a high uniqueness ratio ({round(unique_ratio * 100, 1)}%) "
                            "and may represent an entity identifier. Review recommendation: identifiers typically "
                            "should not be fed directly to ML models."
                        ),
                        column_name=str(col_name),
                        parameters_used=to_json_safe(params),
                        evidence={
                            "unique_count": unique_count,
                            "non_null_count": non_null_count,
                            "unique_ratio": unique_ratio,
                            "name_looks_identifier_like": name_looks_id,
                        },
                        remediation_hint="Exclude primary identifiers from training features to avoid target memorization.",
                        detected_at=now,
                    )
                )
                continue

            # 3. Near-constant column (unique_count > 1 and unique_ratio <= near_constant_thresh)
            if unique_count > 1 and unique_ratio <= near_constant_thresh:
                issues.append(
                    QualityIssueData(
                        module=self.name,
                        analyzer_version=self.version,
                        category="CARDINALITY",
                        severity=Severity.LOW,
                        title="Near-constant column detected",
                        description=(
                            f"Column '{col_name}' has {unique_count} unique values across {non_null_count} rows "
                            f"(uniqueness ratio: {round(unique_ratio * 100, 2)}%), indicating low informational variance."
                        ),
                        column_name=str(col_name),
                        parameters_used=to_json_safe(params),
                        evidence={
                            "unique_count": unique_count,
                            "non_null_count": non_null_count,
                            "unique_ratio": unique_ratio,
                        },
                        remediation_hint="Assess whether this feature provides sufficient variance for predictive modeling.",
                        detected_at=now,
                    )
                )

            # 4. High-cardinality categorical column
            # Only for categorical/string columns that are not already flagged as identifiers
            if dtype_cat in ("categorical", "string", "object"):
                if unique_count >= high_card_count and unique_ratio < id_unique_ratio_thresh:
                    high_card_cols_count += 1
                    issues.append(
                        QualityIssueData(
                            module=self.name,
                            analyzer_version=self.version,
                            category="CARDINALITY",
                            severity=Severity.LOW,
                            title="High cardinality categorical column",
                            description=(
                                f"Column '{col_name}' has {unique_count} distinct categories. "
                                "High categorical cardinality can complicate encoding and increase dimensionality."
                            ),
                            column_name=str(col_name),
                            parameters_used=to_json_safe(params),
                            evidence={
                                "unique_count": unique_count,
                                "non_null_count": non_null_count,
                                "unique_ratio": unique_ratio,
                                "dtype_category": dtype_cat,
                            },
                            remediation_hint=(
                                "Consider target encoding, frequency encoding, or grouping infrequent categories into 'other'."
                            ),
                            detected_at=now,
                        )
                    )

        metrics: Dict[str, Any] = {
            "columns": column_metrics,
            "constant_columns_count": constant_cols_count,
            "high_cardinality_columns_count": high_card_cols_count,
        }

        exec_time_ms = int((time.perf_counter() - start_time) * 1000)
        return ModuleResult(
            module_name=self.name,
            analyzer_version=self.version,
            execution_time_ms=exec_time_ms,
            metrics=to_json_safe(metrics),
            issues=issues,
        )
