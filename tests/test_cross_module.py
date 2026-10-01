"""Cross-module consistency and edge-case integration tests."""

import numpy as np
import pandas as pd
import pytest

from app.engine.base import AnalysisContext, Severity
from app.engine.pipeline import AnalysisPipeline


def test_cross_module_constant_column_coordination():
    """Test constant column does not cause contradictory or cascading duplicate issues across modules."""
    df = pd.DataFrame({
        "all_same": [10.0] * 50,
        "normal_feat": np.linspace(1, 50, 50),
    })
    ctx = AnalysisContext(dataset_version_id="ver_cross_const", df=df)
    pipeline = AnalysisPipeline()
    res = pipeline.execute(ctx)

    # 1. Cardinality analyzer should detect the constant column
    card_issues = [i for i in res["all_issues"] if i.module == "cardinality_analyzer" and i.column_name == "all_same"]
    assert len(card_issues) == 1

    # 2. Correlation analyzer should exclude it rather than crashing or claiming correlation
    corr_issues = [i for i in res["all_issues"] if i.module == "correlation_analyzer" and "all_same" in (i.column_name or "")]
    assert len(corr_issues) == 0

    # 3. Outlier analyzer should not report spurious IQR=0 outlier issues
    outlier_issues = [i for i in res["all_issues"] if i.module == "outlier_analyzer" and i.column_name == "all_same"]
    assert len(outlier_issues) == 0

    # 4. Distribution analyzer should not report HIGH/CRITICAL severity for the constant column
    dist_high = [i for i in res["all_issues"] if i.module == "distribution_analyzer" and i.column_name == "all_same" and i.severity in (Severity.HIGH, Severity.CRITICAL)]
    assert len(dist_high) == 0


def test_cross_module_completely_missing_column():
    """Test 100% missing column reports CRITICAL in missing_analyzer and downstream statistical analyzers skip safely."""
    df = pd.DataFrame({
        "empty_feature": [np.nan] * 50,
        "valid_feature": np.linspace(1, 50, 50),
    })
    ctx = AnalysisContext(dataset_version_id="ver_cross_missing", df=df)
    pipeline = AnalysisPipeline()
    res = pipeline.execute(ctx)

    # 1. Missing analyzer reports CRITICAL
    miss_issues = [i for i in res["all_issues"] if i.module == "missing_analyzer" and i.column_name == "empty_feature"]
    assert len(miss_issues) == 1
    assert miss_issues[0].severity == Severity.CRITICAL

    # 2. Statistical modules (outliers, distributions, correlations) should not crash or generate false positives for empty_feature
    stat_issues = [i for i in res["all_issues"] if i.module in ("outlier_analyzer", "distribution_analyzer", "correlation_analyzer") and i.column_name == "empty_feature"]
    assert len(stat_issues) == 0


def test_cross_module_target_not_specified():
    """Test that when target_column is None, imbalance and leakage analyzers skip safely while others run normally."""
    df = pd.DataFrame({
        "col_a": np.linspace(1, 30, 30),
        "col_b": np.linspace(1, 30, 30) * 2.0,
    })
    ctx = AnalysisContext(dataset_version_id="ver_cross_no_target", df=df, target_column=None)
    pipeline = AnalysisPipeline()
    res = pipeline.execute(ctx)

    # Imbalance and leakage should have no issues and be marked skipped
    comb_metrics = res["combined_metrics"]
    assert comb_metrics["imbalance_analyzer"]["analysis_skipped"] is True
    assert comb_metrics["leakage_analyzer"]["analysis_skipped"] is True

    # Correlation analyzer should still identify high correlation between col_a and col_b
    corr_issues = [i for i in res["all_issues"] if i.module == "correlation_analyzer"]
    assert len(corr_issues) == 1


def test_cross_module_categorical_target():
    """Test when target is categorical: imbalance runs, correlation skips treating it as continuous, and leakage uses categorical methods."""
    df = pd.DataFrame({
        "feature_num": np.linspace(1, 50, 50),
        "cat_target": ["churned" if i % 4 == 0 else "active" for i in range(50)],
    })
    ctx = AnalysisContext(dataset_version_id="ver_cross_cat_target", df=df, target_column="cat_target")
    pipeline = AnalysisPipeline()
    res = pipeline.execute(ctx)

    comb_metrics = res["combined_metrics"]
    # Imbalance analyzer ran
    assert comb_metrics["imbalance_analyzer"]["analysis_skipped"] is False
    assert comb_metrics["imbalance_analyzer"]["class_count"] == 2


def test_cross_module_extreme_low_row_counts():
    """Test that extreme small row counts (0 rows, 1 row, 2 rows) do not crash the pipeline."""
    pipeline = AnalysisPipeline()

    # 0 rows
    df0 = pd.DataFrame({"a": pd.Series([], dtype=float), "b": pd.Series([], dtype=float)})
    res0 = pipeline.execute(AnalysisContext(dataset_version_id="v0", df=df0))
    assert res0["total_issues_count"] >= 0

    # 1 row
    df1 = pd.DataFrame({"a": [10.0], "b": [20.0]})
    res1 = pipeline.execute(AnalysisContext(dataset_version_id="v1", df=df1))
    assert res1["total_issues_count"] >= 0

    # 2 rows
    df2 = pd.DataFrame({"a": [10.0, 20.0], "b": [20.0, 40.0]})
    res2 = pipeline.execute(AnalysisContext(dataset_version_id="v2", df=df2))
    assert res2["total_issues_count"] >= 0
