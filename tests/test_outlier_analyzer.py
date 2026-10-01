"""Unit tests for deterministic OutlierAnalyzer."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from app.engine.base import AnalysisContext, Severity
from app.engine.modules.outlier_analyzer import OutlierAnalyzer


def test_outlier_analyzer_normal_distribution(fixtures_dir: Path):
    """Test that a clean normal distribution has no or very low outliers."""
    df = pd.read_csv(fixtures_dir / "normal_distribution.csv")
    analyzer = OutlierAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_norm", df=df)
    result = analyzer.analyze(ctx)

    assert result.metrics["columns_analyzed_count"] == 2  # id and value
    # value column should have 0 outliers due to clipping
    val_metrics = result.metrics["columns"]["value"]
    assert val_metrics["iqr_method"]["outlier_count"] == 0
    assert val_metrics["iqr_method"]["outlier_percentage"] == 0.0
    assert val_metrics["iqr_method"]["iqr"] > 0


def test_outlier_analyzer_single_outlier_severity_and_bounds(fixtures_dir: Path):
    """Test exact bounds, outlier counts, and severity for single_outlier.csv (5% -> LOW)."""
    df = pd.read_csv(fixtures_dir / "single_outlier.csv")
    analyzer = OutlierAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_single", df=df)
    result = analyzer.analyze(ctx)

    val_metrics = result.metrics["columns"]["val"]["iqr_method"]
    assert val_metrics["outlier_count"] == 1
    assert val_metrics["total_non_null"] == 20
    assert val_metrics["outlier_percentage"] == 5.0
    assert val_metrics["upper_bound"] < 500.0

    # Issue must be generated with LOW severity (1 < 5% <= 5%)
    issues = [i for i in result.issues if i.column_name == "val"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.LOW
    assert issue.category == "OUTLIERS"
    assert issue.evidence["method"] == "IQR"
    assert issue.evidence["outlier_count"] == 1
    assert issue.evidence["outlier_percentage"] == 5.0


def test_outlier_analyzer_many_outliers_critical_severity(fixtures_dir: Path):
    """Test many_outliers.csv where >20% outliers trigger CRITICAL severity."""
    df = pd.read_csv(fixtures_dir / "many_outliers.csv")
    analyzer = OutlierAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_many", df=df)
    result = analyzer.analyze(ctx)

    val_metrics = result.metrics["columns"]["val"]["iqr_method"]
    assert val_metrics["outlier_count"] == 7
    assert val_metrics["outlier_percentage"] == pytest.approx(23.33, rel=1e-2)

    issues = [i for i in result.issues if i.column_name == "val"]
    assert len(issues) == 1
    assert issues[0].severity == Severity.CRITICAL


def test_outlier_analyzer_zero_iqr_suppression(fixtures_dir: Path):
    """Test that zero_iqr.csv with IQR==0 does NOT create a spurious outlier issue."""
    df = pd.read_csv(fixtures_dir / "zero_iqr.csv")
    analyzer = OutlierAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_zero_iqr", df=df)
    result = analyzer.analyze(ctx)

    val_metrics = result.metrics["columns"]["val"]["iqr_method"]
    assert val_metrics["iqr"] == 0.0
    assert val_metrics["outlier_count"] == 0

    # No outlier issue should be created for val
    issues = [i for i in result.issues if i.column_name == "val"]
    assert len(issues) == 0


def test_outlier_analyzer_mad_method():
    """Test Median Absolute Deviation (MAD) modified z-score outlier detection."""
    analyzer = OutlierAnalyzer()
    # 20 points around 10, one extreme 200
    vals = [10.0] * 19 + [200.0]
    df = pd.DataFrame({"feat": vals})
    ctx = AnalysisContext(dataset_version_id="ver_mad", df=df)
    result = analyzer.analyze(ctx)

    mad_metrics = result.metrics["columns"]["feat"]["mad_method"]
    assert mad_metrics["median"] == 10.0
    # Since >50% values are identical, MAD is 0.0, so method reports 0 outliers safely without dividing by zero
    assert mad_metrics["mad"] == 0.0
    assert mad_metrics["outlier_count"] == 0


def test_outlier_analyzer_isolation_forest_reproducibility():
    """Test Isolation Forest multivariate advisory runs reproducibly with random_seed."""
    rng = np.random.RandomState(42)
    df = pd.DataFrame({
        "feat_a": rng.normal(10, 2, 60),
        "feat_b": rng.normal(20, 5, 60),
    })
    # Add an extreme anomaly
    df.loc[0, "feat_a"] = 150.0
    df.loc[0, "feat_b"] = 300.0

    analyzer1 = OutlierAnalyzer(parameters={"random_seed": 42})
    ctx1 = AnalysisContext(dataset_version_id="ver_if1", df=df.copy())
    res1 = analyzer1.analyze(ctx1)

    analyzer2 = OutlierAnalyzer(parameters={"random_seed": 42})
    ctx2 = AnalysisContext(dataset_version_id="ver_if2", df=df.copy())
    res2 = analyzer2.analyze(ctx2)

    if_res1 = res1.metrics["multivariate_isolation_forest"]
    if_res2 = res2.metrics["multivariate_isolation_forest"]

    assert if_res1["outlier_count"] == if_res2["outlier_count"]
    assert if_res1["outlier_percentage"] == if_res2["outlier_percentage"]
    assert if_res1["random_seed"] == 42
    assert if_res1["sampling_applied"] is False


def test_outlier_analyzer_deterministic_sampling():
    """Test that large datasets are deterministically sampled for Isolation Forest."""
    df = pd.DataFrame({
        "feat_a": range(100),
        "feat_b": range(100),
    })
    analyzer = OutlierAnalyzer(parameters={"maximum_sample_size": 20, "random_seed": 42})
    ctx = AnalysisContext(dataset_version_id="ver_sampled", df=df)
    result = analyzer.analyze(ctx)

    if_res = result.metrics["multivariate_isolation_forest"]
    assert if_res["sampling_applied"] is True
    assert if_res["sample_size"] == 20
    assert if_res["random_seed"] == 42


def test_outlier_analyzer_skips_non_numeric_and_empty():
    """Test non-numeric columns and empty/all-null columns are handled safely without error."""
    df = pd.DataFrame({
        "text_col": ["a", "b", "c"],
        "all_null": [np.nan, np.nan, np.nan],
    })
    analyzer = OutlierAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_non_num", df=df)
    result = analyzer.analyze(ctx)

    assert result.metrics["columns_analyzed_count"] == 0
    assert len(result.issues) == 0
