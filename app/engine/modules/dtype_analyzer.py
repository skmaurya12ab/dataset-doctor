"""Deterministic data type analyzer identifying inconsistent, mixed, or ML-risky representations."""

from collections import Counter
from datetime import date, datetime, timezone
import math
import re
import time
from typing import Any, Dict, List, Set
import numpy as np
import pandas as pd

from app.core.json_utils import to_json_safe
from app.engine.base import AnalysisContext, BaseAnalyzer, ModuleResult, QualityIssueData, Severity
from app.engine.defaults import DEFAULT_DTYPE_PARAMETERS

DATETIME_REGEX = re.compile(
    r"^(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})"
    r"([ T]\d{1,2}:\d{2}(:\d{2})?(\.\d+)?)?"
    r"(Z|[+-]\d{2}:?\d{2})?$"
)


def normalize_python_type_name(val: Any) -> str:
    """Map concrete Python / NumPy types to standardized family names."""
    if isinstance(val, (bool, np.bool_)):
        return "bool"
    if isinstance(val, (int, np.integer)):
        return "int"
    if isinstance(val, (float, np.floating)):
        return "float"
    if isinstance(val, str):
        return "str"
    if isinstance(val, (datetime, date, pd.Timestamp)):
        return "datetime"
    if isinstance(val, dict):
        return "dict"
    if isinstance(val, list):
        return "list"
    if isinstance(val, set):
        return "set"
    return type(val).__name__


def classify_dtype(series: pd.Series) -> str:
    """Classify a pandas Series into a standardized conceptual category."""
    dtype_str = str(series.dtype).lower()
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_timedelta64_dtype(series):
        return "timedelta"
    if isinstance(series.dtype, pd.CategoricalDtype) or str(series.dtype) == "category":
        return "categorical"
    if pd.api.types.is_string_dtype(series) or dtype_str in ("str", "string") or dtype_str.startswith("string"):
        return "string"
    if pd.api.types.is_object_dtype(series) or dtype_str == "object":
        return "object"
    return "other"



def is_parseable_numeric(val: Any) -> bool:
    """Check if a string represents a valid numeric value without false positive on NaN/inf."""
    if not isinstance(val, str):
        return False
    cleaned = val.strip()
    if not cleaned:
        return False
    # Avoid treating string 'nan', 'inf', '-inf' as ordinary numeric strings
    if cleaned.lower() in ("nan", "inf", "-inf", "+inf", "none", "null"):
        return False
    try:
        parsed = float(cleaned)
        return not (math.isnan(parsed) or math.isinf(parsed))
    except (ValueError, TypeError):
        return False


def is_parseable_datetime(val: Any) -> bool:
    """Check if a string has a structural date/time pattern and parses successfully."""
    if not isinstance(val, str):
        return False
    cleaned = val.strip()
    if not cleaned:
        return False
    if not DATETIME_REGEX.match(cleaned):
        return False
    try:
        pd.to_datetime(cleaned)
        return True
    except Exception:
        return False


class DataTypeAnalyzer(BaseAnalyzer):
    """Analyzes column dtypes, detects mixed scalar types, nested structures, and miscast strings."""

    @property
    def name(self) -> str:
        return "dtype_analyzer"

    @property
    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ctx: AnalysisContext) -> ModuleResult:
        start_time = time.perf_counter()
        df: pd.DataFrame = ctx.df if ctx.df is not None else pd.DataFrame()

        params = {**DEFAULT_DTYPE_PARAMETERS, **ctx.parameters.get(self.name, {})}
        num_threshold = float(params.get("numeric_parseable_threshold_pct", 95.0))
        dt_threshold = float(params.get("datetime_parseable_threshold_pct", 95.0))

        column_dtypes: Dict[str, Dict[str, str]] = {}
        type_distribution: Dict[str, int] = {}
        issues: List[QualityIssueData] = []
        now = datetime.now(timezone.utc)

        # Inferred type registry for downstream modules
        inferred_types: Dict[str, str] = {}

        for col_idx in range(len(df.columns)):
            col_name = df.columns[col_idx]
            series = df.iloc[:, col_idx]
            pandas_dtype = str(series.dtype)
            inferred_category = classify_dtype(series)
            inferred_types[str(col_name)] = inferred_category


            column_dtypes[str(col_name)] = {
                "pandas_dtype": pandas_dtype,
                "inferred_type": inferred_category,
            }
            type_distribution[inferred_category] = type_distribution.get(inferred_category, 0) + 1

            # Only inspect values for object / string / other columns
            if inferred_category in ("object", "string", "other"):
                # Extract non-null scalar values (ignore None, NaN, NaT, pd.NA)
                non_null_mask = series.notna()
                non_null_series = series[non_null_mask]
                non_null_count = len(non_null_series)

                if non_null_count == 0:
                    continue

                # Inspect Python value types
                type_counts: Counter[str] = Counter()
                for val in non_null_series:
                    t_name = normalize_python_type_name(val)
                    type_counts[t_name] += 1

                observed_types = sorted(list(type_counts.keys()))
                nested_types = [t for t in observed_types if t in ("dict", "list", "set")]
                scalar_types = [t for t in observed_types if t not in ("dict", "list", "set")]

                # 1. Check for nested objects (dict, list, set)
                if nested_types:
                    issues.append(
                        QualityIssueData(
                            module=self.name,
                            analyzer_version=self.version,
                            category="DTYPE",
                            severity=Severity.HIGH,
                            title="Nested data structures detected",
                            description=(
                                f"Column '{col_name}' contains nested structures ({', '.join(nested_types)}). "
                                "Standard machine learning algorithms and estimators cannot consume non-scalar "
                                "nested structures without serialization or feature flattening."
                            ),
                            column_name=str(col_name),
                            parameters_used=to_json_safe(params),
                            evidence={
                                "pandas_dtype": pandas_dtype,
                                "detected_nested_types": nested_types,
                                "type_counts": dict(type_counts),
                            },
                            remediation_hint=(
                                "Flatten nested structures into tabular columns or serialize them to JSON strings."
                            ),
                            detected_at=now,
                        )
                    )

                # 2. Check for mixed scalar types (e.g. str + int, str + float, str + datetime)
                # Meaningful scalar mixture: str mixed with int/float/datetime/bool
                has_str = "str" in scalar_types
                has_number = ("int" in scalar_types) or ("float" in scalar_types)
                has_datetime = "datetime" in scalar_types
                has_bool = "bool" in scalar_types

                is_mixed_scalar = (
                    (has_str and has_number)
                    or (has_str and has_datetime)
                    or (has_str and has_bool)
                    or (len(nested_types) > 0 and len(scalar_types) > 0)
                )

                if is_mixed_scalar and len(observed_types) > 1:
                    issues.append(
                        QualityIssueData(
                            module=self.name,
                            analyzer_version=self.version,
                            category="DTYPE",
                            severity=Severity.HIGH,
                            title="Mixed scalar data types detected",
                            description=(
                                f"Column '{col_name}' contains mixed Python data types ({', '.join(observed_types)}). "
                                "Inconsistent types in a single column prevent vectorization and cause training crashes."
                            ),
                            column_name=str(col_name),
                            parameters_used=to_json_safe(params),
                            evidence={
                                "pandas_dtype": pandas_dtype,
                                "observed_python_types": observed_types,
                                "type_counts": dict(type_counts),
                            },
                            remediation_hint=(
                                "Clean and coerce values to a uniform target type or isolate non-conforming rows."
                            ),
                            detected_at=now,
                        )
                    )

                # 3. Check for numeric-like strings (advisory LOW)
                # Only evaluate if column is predominantly string/text and not already flagged as mixed
                if all(t == "str" for t in observed_types):
                    numeric_parseable = sum(1 for v in non_null_series if is_parseable_numeric(v))
                    numeric_pct = round((numeric_parseable / non_null_count) * 100.0, 2)

                    if numeric_pct >= num_threshold:
                        issues.append(
                            QualityIssueData(
                                module=self.name,
                                analyzer_version=self.version,
                                category="DTYPE",
                                severity=Severity.LOW,
                                title="Numeric-like values stored as text",
                                description=(
                                    f"Column '{col_name}' appears to be represented as text/string, but {numeric_pct}% "
                                    "of values are parseable as numbers and may require validation or conversion."
                                ),
                                column_name=str(col_name),
                                parameters_used=to_json_safe(params),
                                evidence={
                                    "non_null_count": non_null_count,
                                    "numeric_parseable_count": numeric_parseable,
                                    "numeric_parseable_percentage": numeric_pct,
                                },
                                remediation_hint="Verify if this field represents a numeric feature and convert it to int/float.",
                                detected_at=now,
                            )
                        )
                    else:
                        # 4. Check for datetime-like strings (advisory LOW)
                        dt_parseable = sum(1 for v in non_null_series if is_parseable_datetime(v))
                        dt_pct = round((dt_parseable / non_null_count) * 100.0, 2)

                        if dt_pct >= dt_threshold:
                            issues.append(
                                QualityIssueData(
                                    module=self.name,
                                    analyzer_version=self.version,
                                    category="DTYPE",
                                    severity=Severity.LOW,
                                    title="Datetime-like values stored as text",
                                    description=(
                                        f"Column '{col_name}' appears to be represented as text/string, but {dt_pct}% "
                                        "of values appear parseable as dates/times and may require validation or conversion."
                                    ),
                                    column_name=str(col_name),
                                    parameters_used=to_json_safe(params),
                                    evidence={
                                        "non_null_count": non_null_count,
                                        "datetime_parseable_count": dt_parseable,
                                        "datetime_parseable_percentage": dt_pct,
                                    },
                                    remediation_hint="Verify if this field represents a temporal feature and parse to datetime64.",
                                    detected_at=now,
                                )
                            )

        # Update context shared inferred types
        ctx.inferred_types.update(inferred_types)

        metrics: Dict[str, Any] = {
            "column_dtypes": column_dtypes,
            "type_distribution": type_distribution,
            "columns_with_type_warnings": len({iss.column_name for iss in issues if iss.column_name}),
        }

        exec_time_ms = int((time.perf_counter() - start_time) * 1000)
        return ModuleResult(
            module_name=self.name,
            analyzer_version=self.version,
            execution_time_ms=exec_time_ms,
            metrics=to_json_safe(metrics),
            issues=issues,
        )
