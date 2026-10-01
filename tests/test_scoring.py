"""Unit tests for MLReadinessHeuristicScorer."""

import pytest
from app.engine.base import QualityIssue, Severity
from app.engine.scoring import MLReadinessHeuristicScorer


def _make_issue(module: str, severity: Severity, title: str, column: str = None) -> QualityIssue:
    return QualityIssue(
        module=module,
        analyzer_version="1.0.0",
        parameters_used={},
        category="TEST",
        severity=severity,
        column_name=column,
        title=title,
        description=f"Description for {title}",
        evidence={},
    )


def test_scoring_clean_dataset_perfect_score():
    """Test 0 issues results in 100.0 score and Production-oriented readiness."""
    breakdown = MLReadinessHeuristicScorer.calculate([])
    assert breakdown.heuristic_score == 100.0
    assert breakdown.base_score == 100.0
    assert breakdown.total_penalties == 0.0
    assert breakdown.rating == "Production-oriented readiness"
    assert len(breakdown.itemized_penalties) == 0
    assert "heuristic reflecting structural" in breakdown.disclaimer


def test_scoring_penalty_weights_and_itemization():
    """Test exact penalty deductions: CRITICAL=25, HIGH=10, MEDIUM=4, LOW=1, INFO=0."""
    issues = [
        _make_issue("missing_analyzer", Severity.CRITICAL, "Column all missing", column="c1"),
        _make_issue("correlation_analyzer", Severity.HIGH, "Extreme correlation", column="c2"),
        _make_issue("outlier_analyzer", Severity.MEDIUM, "Outliers detected", column="c3"),
        _make_issue("dtype_analyzer", Severity.LOW, "Type mismatch", column="c4"),
        _make_issue("distribution_analyzer", Severity.INFO, "Non-normal distribution", column="c5"),
    ]
    # Total penalties: 25 + 10 + 4 + 1 + 0 = 40.0 -> Score = 60.0
    breakdown = MLReadinessHeuristicScorer.calculate(issues)
    assert breakdown.heuristic_score == 60.0
    assert breakdown.total_penalties == 40.0
    assert breakdown.rating == "Significant preprocessing"

    # INFO issue should not generate a penalty deduction item
    penalties = breakdown.itemized_penalties
    assert len(penalties) == 4
    assert penalties[0].penalty == 25.0
    assert penalties[1].penalty == 10.0
    assert penalties[2].penalty == 4.0
    assert penalties[3].penalty == 1.0


def test_scoring_floor_at_zero():
    """Test heuristic score cannot go below 0.0 despite excessive penalties."""
    issues = [
        _make_issue("missing_analyzer", Severity.CRITICAL, f"Critical issue {i}", column=f"col_{i}")
        for i in range(10)  # 10 * 25 = 250 penalty
    ]
    breakdown = MLReadinessHeuristicScorer.calculate(issues)
    assert breakdown.heuristic_score == 0.0
    assert breakdown.total_penalties == 250.0
    assert breakdown.rating == "High risk / substantial remediation"


def test_scoring_rating_label_boundaries():
    """Test rating label transitions across 90, 75, 50, and below 50."""
    # Score 90.0 (10 penalty -> 1 HIGH)
    res_90 = MLReadinessHeuristicScorer.calculate([_make_issue("m", Severity.HIGH, "H1", "c1")])
    assert res_90.heuristic_score == 90.0
    assert res_90.rating == "Production-oriented readiness"

    # Score 89.0 (11 penalty -> 1 HIGH + 1 LOW)
    res_89 = MLReadinessHeuristicScorer.calculate([
        _make_issue("m", Severity.HIGH, "H1", "c1"),
        _make_issue("m", Severity.LOW, "L1", "c2"),
    ])
    assert res_89.heuristic_score == 89.0
    assert res_89.rating == "Minor remediation"

    # Score 75.0 (25 penalty -> 1 CRITICAL)
    res_75 = MLReadinessHeuristicScorer.calculate([_make_issue("m", Severity.CRITICAL, "C1", "c1")])
    assert res_75.heuristic_score == 75.0
    assert res_75.rating == "Minor remediation"

    # Score 50.0 (50 penalty -> 2 CRITICAL)
    res_50 = MLReadinessHeuristicScorer.calculate([
        _make_issue("m", Severity.CRITICAL, "C1", "c1"),
        _make_issue("m", Severity.CRITICAL, "C2", "c2"),
    ])
    assert res_50.heuristic_score == 50.0
    assert res_50.rating == "Significant preprocessing"

    # Score 49.0 (51 penalty -> 2 CRITICAL + 1 LOW)
    res_49 = MLReadinessHeuristicScorer.calculate([
        _make_issue("m", Severity.CRITICAL, "C1", "c1"),
        _make_issue("m", Severity.CRITICAL, "C2", "c2"),
        _make_issue("m", Severity.LOW, "L1", "c3"),
    ])
    assert res_49.heuristic_score == 49.0
    assert res_49.rating == "High risk / substantial remediation"


def test_scoring_per_column_penalty_deduplication():
    """Test that multiple analyzers flagging the same column are capped at 25.0 to avoid pathological over-penalization."""
    same_col_issues = [
        _make_issue("missing_analyzer", Severity.HIGH, "Missing values", column="salary"),  # 10
        _make_issue("outlier_analyzer", Severity.HIGH, "Extreme outliers", column="salary"),  # 10
        _make_issue("distribution_analyzer", Severity.HIGH, "Severe skewness", column="salary"),  # 10 -> capped to 5
        _make_issue("cardinality_analyzer", Severity.HIGH, "Near constant", column="salary"),  # should be 0 (cap reached)
    ]
    # Without de-duplication: 4 * 10 = 40. With de-duplication cap of 25.0: total penalty = 25.0
    breakdown = MLReadinessHeuristicScorer.calculate(same_col_issues, max_penalty_per_column=25.0)
    assert breakdown.total_penalties == 25.0
    assert breakdown.heuristic_score == 75.0

    # Verify itemized penalties reflect the capped amounts
    penalties = breakdown.itemized_penalties
    assert len(penalties) == 3
    assert penalties[0].penalty == 10.0
    assert penalties[1].penalty == 10.0
    assert penalties[2].penalty == 5.0
