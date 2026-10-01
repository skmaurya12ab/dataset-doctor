"""Unit tests for deterministic CardinalityAnalyzer."""

import uuid
import numpy as np
import pandas as pd
import pytest

from app.engine.base import AnalysisContext, Severity
from app.engine.modules.cardinality_analyzer import CardinalityAnalyzer


def test_cardinality_analyzer_constant_column():
    analyzer = CardinalityAnalyzer()
    df = pd.DataFrame({
        "constant_col": ["STATIC_VAL"] * 500,
        "normal_col": list(range(500)),
    })
    ctx = AnalysisContext(dataset_version_id="ver_const", df=df)
    result = analyzer.analyze(ctx)

    issues = [i for i in result.issues if i.column_name == "constant_col"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.title == "Constant column detected"
    assert issue.severity == Severity.MEDIUM
    assert issue.category == "CARDINALITY"
    assert issue.evidence["unique_count"] == 1
    assert issue.evidence["non_null_count"] == 500


def test_cardinality_analyzer_near_constant_column():
    analyzer = CardinalityAnalyzer()
    # 1000 rows, 5 unique values -> unique_ratio = 5 / 1000 = 0.005 <= 0.01
    vals = ["A"] * 996 + ["B", "C", "D", "E"]
    df = pd.DataFrame({"low_variance_feature": vals})
    ctx = AnalysisContext(dataset_version_id="ver_near_const", df=df)
    result = analyzer.analyze(ctx)

    issues = [i for i in result.issues if i.title == "Near-constant column detected"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.LOW
    assert issue.evidence["unique_count"] == 5
    assert issue.evidence["unique_ratio"] == 0.005


def test_cardinality_analyzer_high_cardinality_categorical():
    analyzer = CardinalityAnalyzer()
    # 200 rows with 60 distinct categories -> unique_count >= 50, unique_ratio = 60/200 = 0.30 (< 0.95)
    cats = [f"cat_{i % 60}" for i in range(200)]
    df = pd.DataFrame({"category_field": pd.Series(cats, dtype="category")})
    ctx = AnalysisContext(
        dataset_version_id="ver_high_card",
        df=df,
        inferred_types={"category_field": "categorical"},
    )
    result = analyzer.analyze(ctx)

    issues = [i for i in result.issues if i.title == "High cardinality categorical column"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.LOW
    assert issue.evidence["unique_count"] == 60


def test_cardinality_analyzer_identifier_columns():
    analyzer = CardinalityAnalyzer()
    n = 100
    df = pd.DataFrame({
        "user_id": [f"user_{i}" for i in range(n)],
        "email": [f"user{i}@example.com" for i in range(n)],
        "uuid_val": [str(uuid.uuid4()) for _ in range(n)],
    })
    ctx = AnalysisContext(dataset_version_id="ver_ids", df=df)
    result = analyzer.analyze(ctx)

    id_issues = [i for i in result.issues if i.title == "Identifier-like high-cardinality column"]
    assert len(id_issues) == 3
    for issue in id_issues:
        # Must be advisory INFO
        assert issue.severity == Severity.INFO
        assert issue.category == "CARDINALITY"
        assert issue.evidence["unique_ratio"] == 1.0
        assert issue.evidence["name_looks_identifier_like"] is True


def test_cardinality_analyzer_all_missing_column_skipped():
    analyzer = CardinalityAnalyzer()
    df = pd.DataFrame({
        "empty_col": [np.nan] * 50,
        "valid_col": list(range(50)),
    })
    ctx = AnalysisContext(dataset_version_id="ver_all_missing", df=df)
    result = analyzer.analyze(ctx)

    # All-missing column should not create a false constant or identifier issue
    empty_issues = [i for i in result.issues if i.column_name == "empty_col"]
    assert len(empty_issues) == 0
    assert result.metrics["columns"]["empty_col"]["non_null_count"] == 0
    assert result.metrics["columns"]["empty_col"]["unique_count"] == 0
