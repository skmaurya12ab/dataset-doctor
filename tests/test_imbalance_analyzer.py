"""Unit tests for deterministic ClassImbalanceAnalyzer."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from app.engine.base import AnalysisContext, Severity
from app.engine.modules.imbalance_analyzer import ClassImbalanceAnalyzer


def test_imbalance_analyzer_no_target_provided():
    """Test analyzer safely skips when target_column is None."""
    df = pd.DataFrame({"feat": [1, 2, 3], "col": ["a", "b", "c"]})
    analyzer = ClassImbalanceAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_no_target", df=df, target_column=None)
    result = analyzer.analyze(ctx)

    assert result.metrics["analysis_skipped"] is True
    assert result.metrics["reason"] == "target_column_not_provided"
    assert len(result.issues) == 0


def test_imbalance_analyzer_continuous_target_skipped():
    """Test analyzer skips continuous numerical targets (e.g., regression)."""
    df = pd.DataFrame({
        "feat": range(100),
        "target_reg": np.random.RandomState(42).normal(50, 10, 100),
    })
    analyzer = ClassImbalanceAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_continuous", df=df, target_column="target_reg")
    result = analyzer.analyze(ctx)

    assert result.metrics["analysis_skipped"] is True
    assert result.metrics["reason"] == "target_appears_continuous_numerical"
    assert len(result.issues) == 0


def test_imbalance_analyzer_balanced_binary(fixtures_dir: Path):
    """Test balanced binary target (50/50) produces no imbalance issues."""
    df = pd.read_csv(fixtures_dir / "balanced_binary.csv")
    analyzer = ClassImbalanceAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_bal", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    assert result.metrics["class_count"] == 2
    assert result.metrics["imbalance_ratio"] == 1.0
    assert result.metrics["majority_percentage"] == 50.0
    assert len(result.issues) == 0


def test_imbalance_analyzer_mild_imbalance(fixtures_dir: Path):
    """Test mild imbalance (70% majority) triggers LOW severity."""
    df = pd.read_csv(fixtures_dir / "mild_imbalance.csv")
    analyzer = ClassImbalanceAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_mild", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    assert result.metrics["majority_percentage"] == 70.0
    issues = [i for i in result.issues if "imbalance" in i.title.lower()]
    assert len(issues) == 1
    assert issues[0].severity == Severity.LOW


def test_imbalance_analyzer_severe_imbalance(fixtures_dir: Path):
    """Test severe imbalance (85% majority) triggers MEDIUM severity."""
    df = pd.read_csv(fixtures_dir / "severe_imbalance.csv")
    analyzer = ClassImbalanceAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_sev", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    assert result.metrics["majority_percentage"] == 85.0
    issues = [i for i in result.issues if "imbalance" in i.title.lower()]
    assert len(issues) == 1
    assert issues[0].severity == Severity.MEDIUM


def test_imbalance_analyzer_extreme_imbalance_critical(fixtures_dir: Path):
    """Test extreme imbalance (>95% majority) triggers CRITICAL severity."""
    df = pd.read_csv(fixtures_dir / "extreme_imbalance.csv")
    analyzer = ClassImbalanceAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_ext", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    assert result.metrics["majority_percentage"] == 97.0
    issues = [i for i in result.issues if "imbalance" in i.title.lower()]
    assert len(issues) == 1
    assert issues[0].severity == Severity.CRITICAL


def test_imbalance_analyzer_binary_exact_boundaries():
    """Test exact binary boundary transitions for both majority policy and equivalent minority percentages."""
    analyzer = ClassImbalanceAnalyzer()

    # Majority <= 60.0% (Minority >= 40.0%) -> no issue
    assert analyzer._determine_binary_severity(60.0) is None
    # Majority 60.1% (Minority 39.9%) -> LOW
    assert analyzer._determine_binary_severity(60.1) == Severity.LOW
    # Majority 75.0% (Minority 25.0%) -> LOW
    assert analyzer._determine_binary_severity(75.0) == Severity.LOW
    # Majority 75.1% (Minority 24.9%) -> MEDIUM
    assert analyzer._determine_binary_severity(75.1) == Severity.MEDIUM
    # Majority 90.0% (Minority 10.0%) -> MEDIUM
    assert analyzer._determine_binary_severity(90.0) == Severity.MEDIUM
    # Majority 90.1% (Minority 9.9%) -> HIGH
    assert analyzer._determine_binary_severity(90.1) == Severity.HIGH
    # Majority 95.0% (Minority 5.0%) -> HIGH
    assert analyzer._determine_binary_severity(95.0) == Severity.HIGH
    # Majority 95.1% (Minority 4.9%) -> CRITICAL
    assert analyzer._determine_binary_severity(95.1) == Severity.CRITICAL

    # Verify custom parameter overrides
    custom_severity = analyzer._determine_binary_severity(
        majority_pct=80.0,
        low_pct=55.0,
        med_pct=70.0,
        high_pct=85.0,
        crit_pct=95.0,
    )
    assert custom_severity == Severity.MEDIUM


def test_imbalance_analyzer_evaluation_basis_in_metrics():
    """Test that metrics explicitly document evaluation_basis as majority_percentage."""
    df = pd.DataFrame({"target": [0] * 70 + [1] * 30})
    analyzer = ClassImbalanceAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_basis", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    assert result.metrics["evaluation_basis"] == "majority_percentage"
    assert result.metrics["majority_percentage"] == 70.0
    assert result.metrics["minority_percentage"] == 30.0
    assert result.issues[0].severity == Severity.LOW



def test_imbalance_analyzer_multiclass(fixtures_dir: Path):
    """Test multiclass distribution calculation and metrics."""
    df = pd.read_csv(fixtures_dir / "multiclass.csv")
    analyzer = ClassImbalanceAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_multi", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    assert result.metrics["class_count"] == 3
    assert result.metrics["majority_class"] == "A"
    assert result.metrics["majority_percentage"] == 70.0
    assert result.metrics["minority_percentage"] == 10.0
    assert result.metrics["imbalance_ratio"] == 7.0


def test_imbalance_analyzer_tiny_class_warning(fixtures_dir: Path):
    """Test that a class with < 10 samples generates an advisory warning."""
    df = pd.read_csv(fixtures_dir / "tiny_class.csv")
    analyzer = ClassImbalanceAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_tiny", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    assert result.metrics["has_tiny_classes"] is True
    tiny_issues = [i for i in result.issues if "tiny" in i.title.lower() or "few" in i.title.lower()]
    assert len(tiny_issues) == 1
    assert tiny_issues[0].severity == Severity.LOW
    assert tiny_issues[0].evidence["tiny_classes"][0]["count"] == 4
