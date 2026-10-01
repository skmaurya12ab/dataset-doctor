"""Unit tests for deterministic CorrelationAnalyzer."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from app.engine.base import AnalysisContext, Severity
from app.engine.modules.correlation_analyzer import CorrelationAnalyzer


def test_correlation_analyzer_highly_correlated(fixtures_dir: Path):
    """Test highly correlated pair (0.95 <= r < 0.99) generates MEDIUM severity issue."""
    df = pd.read_csv(fixtures_dir / "highly_correlated.csv").drop(columns=["id"])
    analyzer = CorrelationAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_high_corr", df=df)
    result = analyzer.analyze(ctx)

    pairs = result.metrics["high_correlation_pairs"]
    assert len(pairs) == 1
    pair = pairs[0]
    assert {pair["feature_a"], pair["feature_b"]} == {"feat_a", "feat_b"}
    assert 0.95 <= pair["abs_pearson"] < 0.99
    assert "spearman" in pair

    issues = [i for i in result.issues if i.category == "CORRELATION"]
    assert len(issues) == 1
    assert issues[0].severity == Severity.MEDIUM


def test_correlation_analyzer_perfectly_correlated(fixtures_dir: Path):
    """Test perfectly correlated pair (r >= 0.99) generates HIGH severity issue."""
    df = pd.read_csv(fixtures_dir / "perfectly_correlated.csv").drop(columns=["id"])
    analyzer = CorrelationAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_perf_corr", df=df)
    result = analyzer.analyze(ctx)

    pairs = result.metrics["high_correlation_pairs"]
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["abs_pearson"] == pytest.approx(1.0, rel=1e-3)

    issues = [i for i in result.issues if i.category == "CORRELATION"]
    assert len(issues) == 1
    assert issues[0].severity == Severity.HIGH


def test_correlation_analyzer_uncorrelated(fixtures_dir: Path):
    """Test uncorrelated features generate 0 issues."""
    df = pd.read_csv(fixtures_dir / "uncorrelated.csv")
    analyzer = CorrelationAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_uncorr", df=df)
    result = analyzer.analyze(ctx)

    assert len(result.metrics["high_correlation_pairs"]) == 0
    assert len(result.issues) == 0


def test_correlation_analyzer_no_duplicate_or_self_pairs():
    """Test that A<->B is reported only once, and no self-correlations A<->A exist."""
    x = np.linspace(1, 20, 20)
    df = pd.DataFrame({
        "col_a": x,
        "col_b": x * 2.0,
        "col_c": x * 3.0,
    })
    analyzer = CorrelationAnalyzer(parameters={"correlation_threshold": 0.90})
    ctx = AnalysisContext(dataset_version_id="ver_multi_corr", df=df)
    result = analyzer.analyze(ctx)

    pairs = result.metrics["high_correlation_pairs"]
    # 3 features perfectly correlated -> exactly 3 pairs: (a,b), (a,c), (b,c)
    assert len(pairs) == 3

    seen_pairs = set()
    for p in pairs:
        assert p["feature_a"] != p["feature_b"], "Self-correlation found"
        pair_tuple = tuple(sorted([p["feature_a"], p["feature_b"]]))
        assert pair_tuple not in seen_pairs, f"Duplicate pair permutation found: {pair_tuple}"
        seen_pairs.add(pair_tuple)


def test_correlation_analyzer_severity_boundaries():
    """Test exact threshold boundaries: 0.90 -> LOW, 0.95 -> MEDIUM, 0.99 -> HIGH."""
    analyzer = CorrelationAnalyzer()
    # Test boundary logic directly
    assert analyzer._determine_severity(0.8999) is None
    assert analyzer._determine_severity(0.90) == Severity.LOW
    assert analyzer._determine_severity(0.9499) == Severity.LOW
    assert analyzer._determine_severity(0.95) == Severity.MEDIUM
    assert analyzer._determine_severity(0.9899) == Severity.MEDIUM
    assert analyzer._determine_severity(0.99) == Severity.HIGH
    assert analyzer._determine_severity(1.0) == Severity.HIGH

    # Test custom parameter thresholds
    assert analyzer._determine_severity(0.82, low_thresh=0.80, med_thresh=0.90, high_thresh=0.95) == Severity.LOW
    assert analyzer._determine_severity(0.92, low_thresh=0.80, med_thresh=0.90, high_thresh=0.95) == Severity.MEDIUM
    assert analyzer._determine_severity(0.96, low_thresh=0.80, med_thresh=0.90, high_thresh=0.95) == Severity.HIGH



def test_correlation_analyzer_constant_column_exclusion():
    """Test that constant columns are excluded and do not crash correlation calculation."""
    df = pd.DataFrame({
        "const_col": [5.0] * 50,
        "var_a": np.linspace(1, 50, 50),
        "var_b": np.linspace(1, 50, 50) * 1.5,
    })
    analyzer = CorrelationAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_const_prune", df=df)
    result = analyzer.analyze(ctx)

    assert "const_col" in result.metrics["excluded_constant_columns"]
    assert "const_col" not in result.metrics["columns_analyzed"]
    assert len(result.metrics["high_correlation_pairs"]) == 1


def test_correlation_analyzer_target_correlation():
    """Test that target correlations are calculated and stored separately when target is numeric."""
    x = np.linspace(1, 50, 50)
    df = pd.DataFrame({
        "feat_pred": x * 2.0,
        "target": x + np.random.RandomState(42).normal(0, 1, 50),
    })
    analyzer = CorrelationAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_target_corr", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    assert "target_correlations" in result.metrics
    target_corrs = result.metrics["target_correlations"]
    assert "feat_pred" in target_corrs
    assert target_corrs["feat_pred"]["abs_pearson"] > 0.90


def test_correlation_analyzer_wide_dataset_safeguard(fixtures_dir: Path):
    """Test wide dataset protection limits features and marks analysis_limited=True."""
    df = pd.read_csv(fixtures_dir / "wide_dataset.csv")
    # Set limit to 10 features
    analyzer = CorrelationAnalyzer(parameters={"max_features": 10})
    ctx = AnalysisContext(dataset_version_id="ver_wide", df=df)
    result = analyzer.analyze(ctx)

    assert result.metrics["analysis_limited"] is True
    assert len(result.metrics["columns_analyzed"]) == 10
    assert result.metrics["total_eligible_features"] > 10

    # Advisory issue about feature cap should be generated
    cap_issues = [i for i in result.issues if "limited" in i.title.lower()]
    assert len(cap_issues) == 1
    assert cap_issues[0].severity == Severity.INFO


def test_correlation_analyzer_deterministic_sampling():
    """Test deterministic sampling when row count exceeds max_sample_size."""
    df = pd.DataFrame({
        "feat_a": range(100),
        "feat_b": range(100),
    })
    analyzer = CorrelationAnalyzer(parameters={"max_sample_size": 25, "random_seed": 42})
    ctx = AnalysisContext(dataset_version_id="ver_corr_sample", df=df)
    result = analyzer.analyze(ctx)

    assert result.metrics["sampling_applied"] is True
    assert result.metrics["sample_size"] == 25
    assert result.metrics["random_seed"] == 42
