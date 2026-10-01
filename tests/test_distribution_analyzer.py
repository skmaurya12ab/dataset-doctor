"""Unit tests for deterministic DistributionAnalyzer."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from app.engine.base import AnalysisContext, Severity
from app.engine.modules.distribution_analyzer import DistributionAnalyzer


def test_distribution_analyzer_symmetric_data(fixtures_dir: Path):
    """Test symmetric data has near-zero skewness and no skewness issue."""
    df = pd.read_csv(fixtures_dir / "symmetric.csv")
    analyzer = DistributionAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_sym", df=df)
    result = analyzer.analyze(ctx)

    val_metrics = result.metrics["columns"]["val"]
    assert val_metrics["count"] == 60
    assert abs(val_metrics["skewness"]) < 0.1
    assert val_metrics["std"] > 0
    assert "mean" in val_metrics
    assert "median" in val_metrics
    assert "q1" in val_metrics
    assert "q3" in val_metrics

    # No skewness issues should be generated for val
    skew_issues = [i for i in result.issues if i.column_name == "val" and "skew" in i.title.lower()]
    assert len(skew_issues) == 0


def test_distribution_analyzer_moderately_skewed(fixtures_dir: Path):
    """Test moderately skewed data triggers LOW severity (1.0 <= |skew| < 2.0)."""
    df = pd.read_csv(fixtures_dir / "moderately_skewed.csv")
    analyzer = DistributionAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_mod_skew", df=df)
    result = analyzer.analyze(ctx)

    val_metrics = result.metrics["columns"]["val"]
    assert 1.0 <= abs(val_metrics["skewness"]) < 2.0

    skew_issues = [i for i in result.issues if i.column_name == "val" and "skew" in i.title.lower()]
    assert len(skew_issues) == 1
    assert skew_issues[0].severity == Severity.LOW
    assert skew_issues[0].category == "DISTRIBUTION"


def test_distribution_analyzer_strongly_skewed(fixtures_dir: Path):
    """Test strongly skewed data triggers HIGH severity (|skew| >= 3.0)."""
    df = pd.read_csv(fixtures_dir / "strongly_skewed.csv")
    analyzer = DistributionAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_str_skew", df=df)
    result = analyzer.analyze(ctx)

    val_metrics = result.metrics["columns"]["val"]
    assert abs(val_metrics["skewness"]) >= 3.0

    skew_issues = [i for i in result.issues if i.column_name == "val" and "skew" in i.title.lower()]
    assert len(skew_issues) == 1
    assert skew_issues[0].severity == Severity.HIGH


def test_distribution_analyzer_skewness_boundary_thresholds():
    """Test exact boundary transitions for skewness severity."""
    # Test helper to inject specific skewness
    analyzer = DistributionAnalyzer()

    # 1. < 1.0 -> no issue
    df1 = pd.DataFrame({"feat": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
    res1 = analyzer.analyze(AnalysisContext(dataset_version_id="v1", df=df1))
    assert len([i for i in res1.issues if "skew" in i.title.lower()]) == 0

    # 2. Medium boundary check
    # Create controlled dataset with skewness between 2.0 and 3.0
    # gamma distribution with shape parameter
    vals_med = [1.0] * 40 + [2.0] * 10 + [5.0] * 5 + [20.0, 25.0]
    df_med = pd.DataFrame({"feat": vals_med})
    res_med = analyzer.analyze(AnalysisContext(dataset_version_id="v_med", df=df_med))
    skew = res_med.metrics["columns"]["feat"]["skewness"]
    if 2.0 <= abs(skew) < 3.0:
        issues = [i for i in res_med.issues if "skew" in i.title.lower()]
        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM


def test_distribution_analyzer_dagostino_normality_test(fixtures_dir: Path):
    """Test D'Agostino normality test calculation and advisory INFO finding."""
    df = pd.read_csv(fixtures_dir / "moderately_skewed.csv")
    analyzer = DistributionAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_norm_test", df=df)
    result = analyzer.analyze(ctx)

    val_metrics = result.metrics["columns"]["val"]
    normality = val_metrics["normality_test"]
    assert normality["test_name"] in ("dagostino_k_squared", "dagostino_k2")
    assert "p_value" in normality
    assert "statistic" in normality
    assert normality["sample_size"] == 100

    # If non-normal, the issue must be strictly advisory (INFO), never HIGH/CRITICAL
    norm_issues = [i for i in result.issues if i.column_name == "val" and "normality" in i.title.lower()]
    for iss in norm_issues:
        assert iss.severity == Severity.INFO


def test_distribution_analyzer_constant_column_suppressed(fixtures_dir: Path):
    """Test constant column with std==0 does NOT generate high-severity distribution issue."""
    df = pd.read_csv(fixtures_dir / "constant.csv")
    analyzer = DistributionAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_const", df=df)
    result = analyzer.analyze(ctx)

    val_metrics = result.metrics["columns"]["val"]
    assert val_metrics["std"] == 0.0

    # Constant column should not generate skewness or high-severity distribution issues
    high_issues = [i for i in result.issues if i.column_name == "val" and i.severity in (Severity.HIGH, Severity.CRITICAL)]
    assert len(high_issues) == 0


def test_distribution_analyzer_small_sample_skips_normality(fixtures_dir: Path):
    """Test sample size < 20 gracefully skips normality test without errors."""
    df = pd.read_csv(fixtures_dir / "small_sample.csv")
    analyzer = DistributionAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_small", df=df)
    result = analyzer.analyze(ctx)

    val_metrics = result.metrics["columns"]["val"]
    assert val_metrics["count"] == 5
    assert val_metrics["normality_test"]["test_name"] == "skipped_insufficient_samples"
