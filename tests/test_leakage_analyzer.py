"""Unit tests for deterministic DataLeakageAnalyzer."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from app.engine.base import AnalysisContext, Severity
from app.engine.modules.leakage_analyzer import DataLeakageAnalyzer


def test_leakage_analyzer_no_target_skipped():
    """Test analyzer safely skips when target_column is not provided."""
    df = pd.DataFrame({"feat": [1, 2, 3], "target_name": [0, 1, 0]})
    analyzer = DataLeakageAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_no_tgt", df=df, target_column=None)
    result = analyzer.analyze(ctx)

    assert result.metrics["analysis_skipped"] is True
    assert result.metrics["reason"] == "target_column_not_provided"
    assert len(result.issues) == 0


def test_leakage_analyzer_target_identity(fixtures_dir: Path):
    """Test Signal A: exact target clone generates HIGH severity potential leakage."""
    df = pd.read_csv(fixtures_dir / "target_copy.csv")
    analyzer = DataLeakageAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_tgt_copy", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    issues = [i for i in result.issues if i.column_name == "target_clone"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.HIGH
    assert issue.evidence["method"] == "target_identity"
    assert issue.evidence["match_ratio"] == 1.0


def test_leakage_analyzer_near_target_identity(fixtures_dir: Path):
    """Test Signal A: near target copy (match_ratio >= 0.99) generates HIGH severity."""
    df = pd.read_csv(fixtures_dir / "near_target_copy.csv")
    analyzer = DataLeakageAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_near_tgt", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    issues = [i for i in result.issues if i.column_name == "near_target"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.HIGH
    assert issue.evidence["method"] == "target_identity"
    assert issue.evidence["match_ratio"] >= 0.99


def test_leakage_analyzer_extreme_numerical_correlation():
    """Test Signal B: feature with Pearson r >= 0.99 against continuous target generates HIGH severity."""
    x = np.linspace(10, 100, 50)
    df = pd.DataFrame({
        "target": x,
        "leak_feat": x * 1.0001,  # r = 1.0
    })
    analyzer = DataLeakageAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_corr_leak", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    issues = [i for i in result.issues if i.column_name == "leak_feat"]
    assert len(issues) == 1
    assert issues[0].severity == Severity.HIGH
    assert issues[0].evidence["method"] == "extreme_numerical_correlation"


def test_leakage_analyzer_high_correlation_nonleaky_not_flagged(fixtures_dir: Path):
    """Test predictive feature with r ~ 0.85 does NOT create leakage finding."""
    df = pd.read_csv(fixtures_dir / "high_correlation_nonleaky.csv")
    analyzer = DataLeakageAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_nonleaky", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    leak_issues = [i for i in result.issues if i.column_name == "feature_pred"]
    assert len(leak_issues) == 0


def test_leakage_analyzer_categorical_perfect_mapping(fixtures_dir: Path):
    """Test Signal C: categorical feature with conditional purity >= 0.99 generates HIGH severity."""
    df = pd.read_csv(fixtures_dir / "categorical_perfect_mapping.csv")
    analyzer = DataLeakageAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_cat_map", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    issues = [i for i in result.issues if i.column_name == "status"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.HIGH
    assert issue.evidence["method"] == "conditional_purity"
    assert issue.evidence["conditional_purity"] == 1.0


def test_leakage_analyzer_suspicious_name_only_is_strictly_info(fixtures_dir: Path):
    """Test Signal D: suspicious column name alone MUST NOT generate HIGH/CRITICAL finding, strictly INFO."""
    df = pd.read_csv(fixtures_dir / "suspicious_name_only.csv")
    analyzer = DataLeakageAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver_susp_name", df=df, target_column="target")
    result = analyzer.analyze(ctx)

    issues = [i for i in result.issues if i.column_name == "outcome_cancelled_flag"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.INFO
    assert issue.severity != Severity.HIGH
    assert issue.severity != Severity.CRITICAL
    assert issue.evidence["method"] == "suspicious_naming"
