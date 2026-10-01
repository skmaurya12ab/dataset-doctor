"""Unit tests for deterministic SchemaAnalyzer."""

import pandas as pd
import pytest

from app.engine.base import AnalysisContext, Severity
from app.engine.modules.schema_analyzer import SchemaAnalyzer


def test_schema_analyzer_clean_dataset():
    analyzer = SchemaAnalyzer()
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Charlie"],
        "age": [25, 30, 35],
    })
    ctx = AnalysisContext(dataset_version_id="ver_1", df=df)
    result = analyzer.analyze(ctx)

    assert result.module_name == "schema_analyzer"
    assert result.analyzer_version == "1.0.0"
    assert len(result.issues) == 0
    assert result.metrics["row_count"] == 3
    assert result.metrics["column_count"] == 3
    assert result.metrics["duplicate_column_names"] == []
    assert result.metrics["blank_column_names"] == []
    assert not result.metrics["has_duplicate_column_names"]
    assert not result.metrics["has_blank_column_names"]


def test_schema_analyzer_duplicate_columns():
    analyzer = SchemaAnalyzer()
    df = pd.DataFrame(
        [[25, 50000, 25]],
        columns=["age", "income", "age"],
    )
    ctx = AnalysisContext(dataset_version_id="ver_2", df=df)
    result = analyzer.analyze(ctx)

    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.category == "SCHEMA"
    assert issue.severity == Severity.HIGH
    assert issue.title == "Duplicate column names detected"
    assert issue.evidence["duplicate_columns"] == ["age"]
    assert issue.evidence["duplicate_count"] == 1
    assert "strip_whitespace_for_blank_check" in issue.parameters_used
    assert result.metrics["has_duplicate_column_names"] is True


def test_schema_analyzer_blank_and_whitespace_columns():
    analyzer = SchemaAnalyzer()
    df = pd.DataFrame(
        [[1, 2, 3]],
        columns=["", "   ", "valid_col"],
    )
    ctx = AnalysisContext(dataset_version_id="ver_3", df=df)
    result = analyzer.analyze(ctx)

    blank_issues = [i for i in result.issues if i.title == "Blank column name detected"]
    assert len(blank_issues) == 1
    issue = blank_issues[0]
    assert issue.category == "SCHEMA"
    assert issue.severity == Severity.MEDIUM
    assert issue.evidence["blank_columns"] == ["", "   "]
    assert result.metrics["has_blank_column_names"] is True


def test_schema_analyzer_valid_unusual_and_unicode_names():
    analyzer = SchemaAnalyzer()
    df = pd.DataFrame(
        [[1, 2, 3, 4]],
        columns=["user age", "customer.address", "₹income", "नाम"],
    )
    ctx = AnalysisContext(dataset_version_id="ver_4", df=df)
    result = analyzer.analyze(ctx)

    assert len(result.issues) == 0
    assert result.metrics["column_count"] == 4
    assert result.metrics["duplicate_column_names"] == []
    assert result.metrics["blank_column_names"] == []
