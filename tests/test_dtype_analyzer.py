"""Unit tests for deterministic DataTypeAnalyzer."""

import numpy as np
import pandas as pd
import pytest

from app.engine.base import AnalysisContext, Severity
from app.engine.modules.dtype_analyzer import DataTypeAnalyzer


def test_dtype_analyzer_standard_clean_types():
    analyzer = DataTypeAnalyzer()
    df = pd.DataFrame({
        "int_col": [1, 2, 3],
        "float_col": [1.1, 2.2, 3.3],
        "bool_col": [True, False, True],
        "str_col": ["a", "b", "c"],
        "dt_col": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
        "cat_col": pd.Series(["low", "med", "high"], dtype="category"),
    })
    ctx = AnalysisContext(dataset_version_id="ver_types", df=df)
    result = analyzer.analyze(ctx)

    assert result.module_name == "dtype_analyzer"
    assert result.analyzer_version == "1.0.0"
    assert len(result.issues) == 0
    dtypes = result.metrics["column_dtypes"]
    assert dtypes["int_col"]["inferred_type"] == "numeric"
    assert dtypes["float_col"]["inferred_type"] == "numeric"
    assert dtypes["bool_col"]["inferred_type"] == "boolean"
    assert dtypes["str_col"]["inferred_type"] == "object" or dtypes["str_col"]["inferred_type"] == "string"
    assert dtypes["dt_col"]["inferred_type"] == "datetime"
    assert dtypes["cat_col"]["inferred_type"] == "categorical"


def test_dtype_analyzer_mixed_scalar_types():
    analyzer = DataTypeAnalyzer()
    df = pd.DataFrame({
        "mixed_col": ["Alice", 23, "Bob", 42],
    })
    ctx = AnalysisContext(dataset_version_id="ver_mixed", df=df)
    result = analyzer.analyze(ctx)

    mixed_issues = [i for i in result.issues if i.title == "Mixed scalar data types detected"]
    assert len(mixed_issues) == 1
    issue = mixed_issues[0]
    assert issue.category == "DTYPE"
    assert issue.severity == Severity.HIGH
    assert issue.column_name == "mixed_col"
    assert "str" in issue.evidence["observed_python_types"]
    assert "int" in issue.evidence["observed_python_types"]
    assert issue.evidence["type_counts"]["str"] == 2
    assert issue.evidence["type_counts"]["int"] == 2


def test_dtype_analyzer_missing_values_do_not_produce_mixed_findings():
    analyzer = DataTypeAnalyzer()
    df = pd.DataFrame({
        "clean_with_nulls": ["Alpha", None, "Beta", np.nan, "Gamma"],
    })
    ctx = AnalysisContext(dataset_version_id="ver_nulls", df=df)
    result = analyzer.analyze(ctx)

    mixed_issues = [i for i in result.issues if i.title == "Mixed scalar data types detected"]
    assert len(mixed_issues) == 0


def test_dtype_analyzer_nested_data_structures():
    analyzer = DataTypeAnalyzer()
    df = pd.DataFrame({
        "nested_dict": [{"a": 1}, {"b": 2}, {"c": 3}],
        "nested_list": [[1, 2], [3, 4], [5, 6]],
    })
    ctx = AnalysisContext(dataset_version_id="ver_nested", df=df)
    result = analyzer.analyze(ctx)

    nested_issues = [i for i in result.issues if i.title == "Nested data structures detected"]
    assert len(nested_issues) == 2
    for issue in nested_issues:
        assert issue.severity == Severity.HIGH
        assert issue.category == "DTYPE"
        assert len(issue.evidence["detected_nested_types"]) > 0


def test_dtype_analyzer_numeric_like_strings():
    analyzer = DataTypeAnalyzer()
    df = pd.DataFrame({
        "age_text": ["21", "25", "31", "42", "50"],
    })
    ctx = AnalysisContext(dataset_version_id="ver_num_str", df=df)
    result = analyzer.analyze(ctx)

    issues = [i for i in result.issues if i.title == "Numeric-like values stored as text"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.LOW
    assert issue.category == "DTYPE"
    assert issue.evidence["non_null_count"] == 5
    assert issue.evidence["numeric_parseable_count"] == 5
    assert issue.evidence["numeric_parseable_percentage"] == 100.0


def test_dtype_analyzer_datetime_like_strings():
    analyzer = DataTypeAnalyzer()
    df = pd.DataFrame({
        "date_text": [
            "2026-01-01",
            "2026-01-02",
            "2026-01-03",
            "2026-01-04 10:00:00",
            "2026-01-05",
        ],
    })
    ctx = AnalysisContext(dataset_version_id="ver_dt_str", df=df)
    result = analyzer.analyze(ctx)

    issues = [i for i in result.issues if i.title == "Datetime-like values stored as text"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.LOW
    assert issue.category == "DTYPE"
    assert issue.evidence["non_null_count"] == 5
    assert issue.evidence["datetime_parseable_count"] == 5
    assert issue.evidence["datetime_parseable_percentage"] == 100.0
