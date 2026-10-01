"""Unit tests for deterministic MissingValueAnalyzer."""

import numpy as np
import pandas as pd
import pytest

from app.engine.base import AnalysisContext, Severity
from app.engine.modules.missing_analyzer import MissingValueAnalyzer


def test_missing_analyzer_exact_boundaries():
    analyzer = MissingValueAnalyzer()
    n = 1000

    def make_series(missing_count: int):
        data = [np.nan] * missing_count + [1.0] * (n - missing_count)
        return data

    df = pd.DataFrame({
        "col_0": make_series(0),       # 0% -> no issue
        "col_5": make_series(50),      # 5.0% -> LOW
        "col_5_1": make_series(51),    # 5.1% -> MEDIUM
        "col_20": make_series(200),    # 20.0% -> MEDIUM
        "col_20_1": make_series(201),  # 20.1% -> HIGH
        "col_40": make_series(400),    # 40.0% -> HIGH
        "col_40_1": make_series(401),  # 40.1% -> CRITICAL
        "col_100": make_series(1000),  # 100.0% -> CRITICAL
    })

    ctx = AnalysisContext(dataset_version_id="ver_boundaries", df=df)
    result = analyzer.analyze(ctx)

    issues_by_col = {i.column_name: i for i in result.issues}

    # 0% must not produce issue
    assert "col_0" not in issues_by_col
    assert result.metrics["columns"]["col_0"]["missing_count"] == 0

    # 5.0% -> LOW
    assert issues_by_col["col_5"].severity == Severity.LOW
    assert issues_by_col["col_5"].evidence["missing_count"] == 50
    assert issues_by_col["col_5"].evidence["missing_percentage"] == 5.0

    # 5.1% -> MEDIUM
    assert issues_by_col["col_5_1"].severity == Severity.MEDIUM
    assert issues_by_col["col_5_1"].evidence["missing_count"] == 51
    assert issues_by_col["col_5_1"].evidence["missing_percentage"] == 5.1

    # 20.0% -> MEDIUM
    assert issues_by_col["col_20"].severity == Severity.MEDIUM
    assert issues_by_col["col_20"].evidence["missing_count"] == 200

    # 20.1% -> HIGH
    assert issues_by_col["col_20_1"].severity == Severity.HIGH
    assert issues_by_col["col_20_1"].evidence["missing_count"] == 201

    # 40.0% -> HIGH
    assert issues_by_col["col_40"].severity == Severity.HIGH
    assert issues_by_col["col_40"].evidence["missing_count"] == 400

    # 40.1% -> CRITICAL
    assert issues_by_col["col_40_1"].severity == Severity.CRITICAL
    assert issues_by_col["col_40_1"].evidence["missing_count"] == 401

    # 100% -> CRITICAL
    assert issues_by_col["col_100"].severity == Severity.CRITICAL
    assert issues_by_col["col_100"].evidence["missing_count"] == 1000
    assert issues_by_col["col_100"].evidence["missing_percentage"] == 100.0


def test_missing_analyzer_blank_strings_and_nullables():
    analyzer = MissingValueAnalyzer()
    df = pd.DataFrame({
        "text_col": ["Alice", "", "   ", None, "Bob"],
        "nullable_col": pd.Series([1, pd.NA, 3, pd.NA, 5], dtype="Int64"),
    })
    ctx = AnalysisContext(dataset_version_id="ver_blanks", df=df)
    result = analyzer.analyze(ctx)

    issues_by_col = {i.column_name: i for i in result.issues}

    # In text_col: "", "   ", None are missing -> 3 out of 5 = 60.0% (CRITICAL)
    assert issues_by_col["text_col"].evidence["missing_count"] == 3
    assert issues_by_col["text_col"].evidence["missing_percentage"] == 60.0
    assert issues_by_col["text_col"].severity == Severity.CRITICAL

    # In nullable_col: 2 pd.NA out of 5 = 40.0% (HIGH)
    assert issues_by_col["nullable_col"].evidence["missing_count"] == 2
    assert issues_by_col["nullable_col"].evidence["missing_percentage"] == 40.0
    assert issues_by_col["nullable_col"].severity == Severity.HIGH


def test_missing_analyzer_preserves_arbitrary_string_na():
    analyzer = MissingValueAnalyzer()
    df = pd.DataFrame({
        "country_code": ["NA", "US", "CA", "NA", "MX"],  # Namibia or abbreviation
    })
    ctx = AnalysisContext(dataset_version_id="ver_na_str", df=df)
    result = analyzer.analyze(ctx)

    # By default, "NA" string must NOT be treated as missing
    assert len(result.issues) == 0
    assert result.metrics["columns"]["country_code"]["missing_count"] == 0

    # If explicitly configured in parameters, then it is treated as missing
    ctx_custom = AnalysisContext(
        dataset_version_id="ver_na_str",
        df=df,
        parameters={"missing_analyzer": {"custom_missing_strings": ["NA"]}},
    )
    result_custom = analyzer.analyze(ctx_custom)
    assert len(result_custom.issues) == 1
    assert result_custom.issues[0].evidence["missing_count"] == 2
