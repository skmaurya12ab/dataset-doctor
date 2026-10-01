"""Unit tests for deterministic DuplicateAnalyzer."""

import pandas as pd
import pytest

from app.engine.base import AnalysisContext, Severity
from app.engine.modules.duplicate_analyzer import DuplicateAnalyzer


def test_duplicate_analyzer_exact_boundaries():
    analyzer = DuplicateAnalyzer()
    n = 1000

    def make_df(dup_rows: int):
        # dup_rows rows will be identical to row 0, remaining n - dup_rows will be unique
        if dup_rows == 0:
            return pd.DataFrame({"val": list(range(n))})
        if dup_rows == n:
            return pd.DataFrame({"val": [999] * n})
        # For dup_rows > 0: create a duplicate cluster of size dup_rows, rest unique
        dup_cluster = [1000000] * dup_rows
        unique_rest = list(range(n - dup_rows))
        return pd.DataFrame({"val": dup_cluster + unique_rest})

    # 0% -> no issue
    res_0 = analyzer.analyze(AnalysisContext(dataset_version_id="d0", df=make_df(0)))
    assert len(res_0.issues) == 0
    assert res_0.metrics["duplicate_row_count"] == 0

    # 1.0% (10 rows) -> LOW
    res_1 = analyzer.analyze(AnalysisContext(dataset_version_id="d1", df=make_df(10)))
    assert res_1.issues[0].severity == Severity.LOW
    assert res_1.issues[0].evidence["duplicate_row_count"] == 10
    assert res_1.issues[0].evidence["duplicate_percentage"] == 1.0

    # 1.1% (11 rows) -> MEDIUM
    res_1_1 = analyzer.analyze(AnalysisContext(dataset_version_id="d11", df=make_df(11)))
    assert res_1_1.issues[0].severity == Severity.MEDIUM
    assert res_1_1.issues[0].evidence["duplicate_row_count"] == 11
    assert res_1_1.issues[0].evidence["duplicate_percentage"] == 1.1

    # 5.0% (50 rows) -> MEDIUM
    res_5 = analyzer.analyze(AnalysisContext(dataset_version_id="d5", df=make_df(50)))
    assert res_5.issues[0].severity == Severity.MEDIUM
    assert res_5.issues[0].evidence["duplicate_row_count"] == 50

    # 5.1% (51 rows) -> HIGH
    res_5_1 = analyzer.analyze(AnalysisContext(dataset_version_id="d51", df=make_df(51)))
    assert res_5_1.issues[0].severity == Severity.HIGH
    assert res_5_1.issues[0].evidence["duplicate_row_count"] == 51

    # 20.0% (200 rows) -> HIGH
    res_20 = analyzer.analyze(AnalysisContext(dataset_version_id="d20", df=make_df(200)))
    assert res_20.issues[0].severity == Severity.HIGH
    assert res_20.issues[0].evidence["duplicate_row_count"] == 200

    # 20.1% (201 rows) -> CRITICAL
    res_20_1 = analyzer.analyze(AnalysisContext(dataset_version_id="d201", df=make_df(201)))
    assert res_20_1.issues[0].severity == Severity.CRITICAL
    assert res_20_1.issues[0].evidence["duplicate_row_count"] == 201

    # 100% (1000 rows) -> CRITICAL
    res_100 = analyzer.analyze(AnalysisContext(dataset_version_id="d100", df=make_df(1000)))
    assert res_100.issues[0].severity == Severity.CRITICAL
    assert res_100.issues[0].evidence["duplicate_row_count"] == 1000
    assert res_100.issues[0].evidence["duplicate_percentage"] == 100.0


def test_duplicate_analyzer_all_rows_in_duplicate_groups_counted():
    analyzer = DuplicateAnalyzer()
    # A, A, A, B: 3 out of 4 rows belong to duplicate cluster A
    df = pd.DataFrame({
        "letter": ["A", "A", "A", "B"],
    })
    ctx = AnalysisContext(dataset_version_id="ver_aaa_b", df=df)
    result = analyzer.analyze(ctx)

    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.evidence["total_rows"] == 4
    assert issue.evidence["duplicate_row_count"] == 3
    assert issue.evidence["duplicate_percentage"] == 75.0
    assert issue.evidence["unique_row_count"] == 1
    assert issue.severity == Severity.CRITICAL
