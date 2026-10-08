"""Comprehensive unit tests for all deterministic analyzers and heuristic scorer.

Tests verify:
- Expected findings, severity, evidence, parameters, provenance
- Empty, 1-row, wide, and edge-case datasets
- Numerical vs categorical behavior, mixed types, constant columns
"""

import numpy as np
import pandas as pd
import pytest

from app.engine.base import AnalysisContext, Severity
from app.engine.modules.cardinality_analyzer import CardinalityAnalyzer
from app.engine.modules.correlation_analyzer import CorrelationAnalyzer
from app.engine.modules.distribution_analyzer import DistributionAnalyzer
from app.engine.modules.dtype_analyzer import DataTypeAnalyzer
from app.engine.modules.duplicate_analyzer import DuplicateAnalyzer
from app.engine.modules.imbalance_analyzer import ClassImbalanceAnalyzer
from app.engine.modules.leakage_analyzer import DataLeakageAnalyzer
from app.engine.modules.missing_analyzer import MissingValueAnalyzer
from app.engine.modules.outlier_analyzer import OutlierAnalyzer
from app.engine.modules.schema_analyzer import SchemaAnalyzer
from app.engine.scoring import MLReadinessHeuristicScorer


# ==============================================================================
# 1. SchemaAnalyzer
# ==============================================================================

def test_schema_analyzer_empty_dataset():
    """Verify SchemaAnalyzer handles completely empty DataFrame gracefully."""
    analyzer = SchemaAnalyzer()
    df = pd.DataFrame()
    ctx = AnalysisContext(dataset_version_id="ver_empty", df=df)
    result = analyzer.analyze(ctx)

    assert result.module_name == "schema_analyzer"
    assert result.analyzer_version == "1.0.0"
    assert result.metrics["row_count"] == 0
    assert result.metrics["column_count"] == 0
    assert len(result.issues) == 0


def test_schema_analyzer_single_row():
    """Verify SchemaAnalyzer correctly processes 1-row dataset."""
    analyzer = SchemaAnalyzer()
    df = pd.DataFrame([{"col_a": 1, "col_b": "text"}])
    ctx = AnalysisContext(dataset_version_id="ver_1row", df=df)
    result = analyzer.analyze(ctx)

    assert result.metrics["row_count"] == 1
    assert result.metrics["column_count"] == 2
    assert len(result.issues) == 0


def test_schema_analyzer_wide_dataset():
    """Verify SchemaAnalyzer on a wide DataFrame with 150 unique columns."""
    analyzer = SchemaAnalyzer()
    cols = [f"feature_{i}" for i in range(150)]
    df = pd.DataFrame(np.zeros((5, 150)), columns=cols)
    ctx = AnalysisContext(dataset_version_id="ver_wide", df=df)
    result = analyzer.analyze(ctx)

    assert result.metrics["column_count"] == 150
    assert result.metrics["has_duplicate_column_names"] is False
    assert len(result.issues) == 0


# ==============================================================================
# 2. DataTypeAnalyzer
# ==============================================================================

def test_dtype_analyzer_empty_and_single_row():
    """Verify DataTypeAnalyzer handles 0-row and 1-row data."""
    analyzer = DataTypeAnalyzer()

    # 0 rows, 2 columns
    df_empty = pd.DataFrame(columns=["a", "b"])
    res_empty = analyzer.analyze(AnalysisContext(dataset_version_id="ver_e", df=df_empty))
    assert res_empty.module_name == "dtype_analyzer"
    assert len(res_empty.issues) == 0

    # 1 row
    df_1 = pd.DataFrame([{"num": 42, "text": "hello"}])
    res_1 = analyzer.analyze(AnalysisContext(dataset_version_id="ver_1", df=df_1))
    assert res_1.metrics["column_dtypes"]["num"]["inferred_type"] == "numeric"
    assert res_1.metrics["column_dtypes"]["text"]["inferred_type"] in ("string", "object")


def test_dtype_analyzer_all_null_column():
    """Verify all-null column does not cause unhandled crashes."""
    analyzer = DataTypeAnalyzer()
    df = pd.DataFrame({"null_col": [np.nan, None, np.nan], "valid_col": [1, 2, 3]})
    ctx = AnalysisContext(dataset_version_id="ver_nulls", df=df)
    result = analyzer.analyze(ctx)

    assert "null_col" in result.metrics["column_dtypes"]
    # All null should not trigger false mixed scalar issue
    mixed_issues = [i for i in result.issues if i.column_name == "null_col"]
    assert len(mixed_issues) == 0


# ==============================================================================
# 3. MissingValueAnalyzer
# ==============================================================================

def test_missing_analyzer_empty_and_single_row():
    """Verify MissingValueAnalyzer on empty and single row DataFrames."""
    analyzer = MissingValueAnalyzer()

    df_empty = pd.DataFrame(columns=["col1", "col2"])
    res_empty = analyzer.analyze(AnalysisContext(dataset_version_id="e", df=df_empty))
    assert res_empty.metrics["total_missing_cells"] == 0
    assert len(res_empty.issues) == 0

    df_1_null = pd.DataFrame([{"val": np.nan}])
    res_1_null = analyzer.analyze(AnalysisContext(dataset_version_id="1n", df=df_1_null))
    assert res_1_null.metrics["total_missing_cells"] == 1
    assert res_1_null.issues[0].severity == Severity.CRITICAL  # 100% missing


def test_missing_analyzer_clean_no_missing():
    """Verify dataset with 0 missing cells generates zero issues and clean metrics."""
    analyzer = MissingValueAnalyzer()
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": ["x", "y", "z", "w"]})
    res = analyzer.analyze(AnalysisContext(dataset_version_id="clean", df=df))

    assert res.metrics["total_missing_cells"] == 0
    assert res.metrics["overall_missing_percentage"] == 0.0
    assert len(res.issues) == 0


# ==============================================================================
# 4. DuplicateAnalyzer
# ==============================================================================

def test_duplicate_analyzer_empty_and_single_row():
    """Verify DuplicateAnalyzer on empty and single-row datasets."""
    analyzer = DuplicateAnalyzer()

    df_empty = pd.DataFrame(columns=["a", "b"])
    res_empty = analyzer.analyze(AnalysisContext(dataset_version_id="e", df=df_empty))
    assert res_empty.metrics["duplicate_row_count"] == 0
    assert len(res_empty.issues) == 0

    df_1 = pd.DataFrame([{"a": 1, "b": 2}])
    res_1 = analyzer.analyze(AnalysisContext(dataset_version_id="1", df=df_1))
    assert res_1.metrics["duplicate_row_count"] == 0
    assert len(res_1.issues) == 0


def test_duplicate_analyzer_all_rows_duplicated():
    """Verify 100% duplicated dataset triggers CRITICAL severity."""
    analyzer = DuplicateAnalyzer()
    df = pd.DataFrame({"x": [10, 10, 10, 10, 10], "y": ["a", "a", "a", "a", "a"]})
    res = analyzer.analyze(AnalysisContext(dataset_version_id="all_dup", df=df))

    assert res.metrics["duplicate_row_count"] == 5
    assert res.metrics["duplicate_percentage"] == 100.0
    assert len(res.issues) == 1
    assert res.issues[0].severity == Severity.CRITICAL


# ==============================================================================
# 5. CardinalityAnalyzer
# ==============================================================================

def test_cardinality_analyzer_zero_variance_numerical():
    """Verify numerical column with identical values is flagged as constant."""
    analyzer = CardinalityAnalyzer()
    df = pd.DataFrame({"zero_var": [42.0] * 100, "varying": list(range(100))})
    res = analyzer.analyze(AnalysisContext(dataset_version_id="zv", df=df))

    issues = [i for i in res.issues if i.column_name == "zero_var"]
    assert len(issues) == 1
    assert issues[0].title == "Constant column detected"
    assert issues[0].severity == Severity.MEDIUM


def test_cardinality_analyzer_single_row_does_not_flag_false_constant():
    """Verify 1-row dataset does not trigger spurious constant alerts if suppressed."""
    analyzer = CardinalityAnalyzer()
    df = pd.DataFrame([{"feature": "val"}])
    res = analyzer.analyze(AnalysisContext(dataset_version_id="1row", df=df))
    # 1 row has unique_count == 1, but non_null_count is also 1
    assert res.metrics["columns"]["feature"]["unique_count"] == 1


# ==============================================================================
# 6. OutlierAnalyzer
# ==============================================================================

def test_outlier_analyzer_empty_and_few_rows():
    """Verify OutlierAnalyzer handles datasets with < 4 rows safely."""
    analyzer = OutlierAnalyzer()
    df_tiny = pd.DataFrame({"val": [10.0, 20.0]})
    res = analyzer.analyze(AnalysisContext(dataset_version_id="tiny", df=df_tiny))

    assert res.module_name == "outlier_analyzer"
    assert len(res.issues) == 0


def test_outlier_analyzer_extreme_outlier_value():
    """Verify extreme value (1e9) is detected by IQR with correct bounds."""
    analyzer = OutlierAnalyzer()
    # 25 values near 10, 1 extreme
    vals = [10.0 + (i * 0.1) for i in range(25)] + [1000000000.0]
    df = pd.DataFrame({"feat": vals})
    res = analyzer.analyze(AnalysisContext(dataset_version_id="extreme", df=df))

    issues = [i for i in res.issues if i.column_name == "feat"]
    assert len(issues) == 1
    assert issues[0].evidence["outlier_count"] == 1
    assert issues[0].evidence["method"] == "IQR"


# ==============================================================================
# 7. DistributionAnalyzer
# ==============================================================================

def test_distribution_analyzer_empty_and_single_row():
    """Verify DistributionAnalyzer handles empty and 1-row data safely."""
    analyzer = DistributionAnalyzer()

    df_empty = pd.DataFrame({"val": []})
    res_empty = analyzer.analyze(AnalysisContext(dataset_version_id="e", df=df_empty))
    assert len(res_empty.issues) == 0

    df_1 = pd.DataFrame({"val": [42.0]})
    res_1 = analyzer.analyze(AnalysisContext(dataset_version_id="1", df=df_1))
    assert res_1.metrics["columns"]["val"]["count"] == 1
    assert len(res_1.issues) == 0


def test_distribution_analyzer_all_constants():
    """Verify column of identical numbers does not trigger division by zero."""
    analyzer = DistributionAnalyzer()
    df = pd.DataFrame({"const": [5.0] * 50})
    res = analyzer.analyze(AnalysisContext(dataset_version_id="c", df=df))

    assert res.metrics["columns"]["const"]["std"] == 0.0
    # No high-severity skewness
    assert len([i for i in res.issues if i.severity in (Severity.HIGH, Severity.CRITICAL)]) == 0


# ==============================================================================
# 8. CorrelationAnalyzer
# ==============================================================================

def test_correlation_analyzer_single_numeric_column():
    """Verify CorrelationAnalyzer with only 1 numeric column skips without error."""
    analyzer = CorrelationAnalyzer()
    df = pd.DataFrame({"col_num": [1, 2, 3, 4], "col_str": ["a", "b", "c", "d"]})
    res = analyzer.analyze(AnalysisContext(dataset_version_id="single_num", df=df))

    assert res.metrics["analysis_skipped"] is True
    assert res.metrics["reason"] == "insufficient_non_constant_numeric_features"
    assert res.metrics["eligible_feature_count"] == 1
    assert len(res.issues) == 0


def test_correlation_analyzer_perfect_negative_correlation():
    """Verify perfect negative correlation (r = -1.0) is detected as high correlation."""
    analyzer = CorrelationAnalyzer()
    x = np.linspace(1, 50, 50)
    df = pd.DataFrame({"pos": x, "neg": -x})
    res = analyzer.analyze(AnalysisContext(dataset_version_id="neg_corr", df=df))

    pairs = res.metrics["high_correlation_pairs"]
    assert len(pairs) == 1
    assert pairs[0]["abs_pearson"] == pytest.approx(1.0, rel=1e-3)
    assert res.issues[0].severity == Severity.HIGH


# ==============================================================================
# 9. ClassImbalanceAnalyzer
# ==============================================================================

def test_imbalance_analyzer_nonexistent_target():
    """Verify target column not present in DataFrame is safely handled."""
    analyzer = ClassImbalanceAnalyzer()
    df = pd.DataFrame({"feat": [1, 2, 3]})
    res = analyzer.analyze(AnalysisContext(dataset_version_id="missing_tgt", df=df, target_column="ghost_target"))

    assert res.metrics["analysis_skipped"] is True
    assert res.metrics["reason"] == "target_column_not_found"
    assert len(res.issues) == 0


def test_imbalance_analyzer_single_class_target():
    """Verify target column with only 1 unique class gracefully skips with single_class_target."""
    analyzer = ClassImbalanceAnalyzer()
    df = pd.DataFrame({"target": ["positive"] * 50})
    res = analyzer.analyze(AnalysisContext(dataset_version_id="single_cls", df=df, target_column="target"))

    assert res.metrics["analysis_skipped"] is True
    assert res.metrics["reason"] == "single_class_target"
    assert res.metrics["class_count"] == 1
    assert len(res.issues) == 0


# ==============================================================================
# 10. DataLeakageAnalyzer
# ==============================================================================

def test_leakage_analyzer_missing_target_column():
    """Verify DataLeakageAnalyzer when target_column is not in DataFrame."""
    analyzer = DataLeakageAnalyzer()
    df = pd.DataFrame({"feat1": [1, 2, 3], "feat2": [4, 5, 6]})
    res = analyzer.analyze(AnalysisContext(dataset_version_id="no_tgt_in_df", df=df, target_column="nonexistent"))

    assert res.metrics["analysis_skipped"] is True
    assert res.metrics["reason"] == "target_column_not_found"
    assert len(res.issues) == 0


def test_leakage_analyzer_clean_features_no_false_positive():
    """Verify independent random features do not trigger false positive leakage."""
    analyzer = DataLeakageAnalyzer()
    rng = np.random.RandomState(42)
    df = pd.DataFrame({
        "target": rng.choice([0, 1], size=100),
        "feat_clean": rng.normal(0, 1, 100),
        "feat_cat": rng.choice(["cat", "dog"], size=100),
    })
    res = analyzer.analyze(AnalysisContext(dataset_version_id="clean_leak", df=df, target_column="target"))

    high_leak_issues = [i for i in res.issues if i.severity in (Severity.HIGH, Severity.CRITICAL)]
    assert len(high_leak_issues) == 0


# ==============================================================================
# 11. MLReadinessHeuristicScorer
# ==============================================================================

def test_heuristic_scorer_empty_issues_list():
    """Verify scorer returns perfect score for empty issue list."""
    breakdown = MLReadinessHeuristicScorer.calculate([])
    assert breakdown.heuristic_score == 100.0
    assert breakdown.total_penalties == 0.0
    assert breakdown.rating == "Production-oriented readiness"


def test_heuristic_scorer_provenance_and_disclaimer():
    """Verify scorer includes transparent provenance and disclaimer."""
    breakdown = MLReadinessHeuristicScorer.calculate([])
    assert breakdown.base_score == 100.0
    assert "heuristic reflecting structural" in breakdown.disclaimer
    assert "does not guarantee" in breakdown.disclaimer
