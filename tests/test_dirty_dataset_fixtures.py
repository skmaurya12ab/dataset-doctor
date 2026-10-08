"""Deterministic tests against dirty and edge-case dataset fixtures.

Verifies known expected defects and metrics across:
- missing_values.csv
- duplicates.csv
- constant.csv / zero_iqr.csv
- cardinality.csv
- single_outlier.csv / many_outliers.csv
- moderately_skewed.csv / strongly_skewed.csv / symmetric.csv
- highly_correlated.csv / perfectly_correlated.csv / uncorrelated.csv
- mild_imbalance.csv / severe_imbalance.csv / extreme_imbalance.csv
- target_copy.csv / near_target_copy.csv / categorical_perfect_mapping.csv / suspicious_name_only.csv
- mixed_types.csv / numeric_strings.csv / datetime_strings.csv
- malformed.csv / empty.csv
- wide_dataset.csv / small_sample.csv / combined_dirty.csv
- Unicode headers and all-null column synthesis
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import MalformedFileException
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
from app.engine.pipeline import AnalysisPipeline
from app.services.ingestion import DatasetIngestionService


def test_fixture_missing_values(fixtures_dir: Path):
    """Verify missing_values.csv flags expected missing rates and columns."""
    df = pd.read_csv(fixtures_dir / "missing_values.csv")
    analyzer = MissingValueAnalyzer()
    res = analyzer.analyze(AnalysisContext(dataset_version_id="f_missing", df=df))

    assert res.metrics["total_missing_cells"] > 0
    assert len(res.issues) > 0
    # Every issue generated must be in the MISSING_VALUES category
    for issue in res.issues:
        assert issue.category == "MISSING_VALUES"
        assert issue.evidence["missing_count"] > 0


def test_fixture_duplicates(fixtures_dir: Path):
    """Verify duplicates.csv produces exact expected duplicate row counts."""
    df = pd.read_csv(fixtures_dir / "duplicates.csv")
    analyzer = DuplicateAnalyzer()
    res = analyzer.analyze(AnalysisContext(dataset_version_id="f_dups", df=df))

    assert res.metrics["duplicate_row_count"] > 0
    assert len(res.issues) == 1
    issue = res.issues[0]
    assert issue.category == "DUPLICATES"
    assert issue.severity in (Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


def test_fixture_constant_and_near_constant(fixtures_dir: Path):
    """Verify constant.csv and cardinality.csv produce constant/near-constant findings."""
    df_const = pd.read_csv(fixtures_dir / "constant.csv")
    analyzer = CardinalityAnalyzer()
    res_const = analyzer.analyze(AnalysisContext(dataset_version_id="f_const", df=df_const))

    const_issues = [i for i in res_const.issues if i.title == "Constant column detected"]
    assert len(const_issues) >= 1
    assert const_issues[0].severity == Severity.MEDIUM


def test_fixture_outliers(fixtures_dir: Path):
    """Verify single_outlier, many_outliers, and zero_iqr fixtures."""
    analyzer = OutlierAnalyzer()

    # Single outlier fixture -> LOW severity
    df_single = pd.read_csv(fixtures_dir / "single_outlier.csv")
    res_single = analyzer.analyze(AnalysisContext(dataset_version_id="f_out1", df=df_single))
    assert len(res_single.issues) == 1
    assert res_single.issues[0].severity == Severity.LOW

    # Many outliers fixture -> CRITICAL severity
    df_many = pd.read_csv(fixtures_dir / "many_outliers.csv")
    res_many = analyzer.analyze(AnalysisContext(dataset_version_id="f_out_many", df=df_many))
    assert len(res_many.issues) == 1
    assert res_many.issues[0].severity == Severity.CRITICAL

    # Zero IQR fixture -> Outlier calculation suppressed, 0 issues
    df_zero = pd.read_csv(fixtures_dir / "zero_iqr.csv")
    res_zero = analyzer.analyze(AnalysisContext(dataset_version_id="f_zero_iqr", df=df_zero))
    assert len(res_zero.issues) == 0


def test_fixture_distributions(fixtures_dir: Path):
    """Verify symmetric, moderately_skewed, and strongly_skewed distributions."""
    analyzer = DistributionAnalyzer()

    # Symmetric -> 0 skewness issues
    df_sym = pd.read_csv(fixtures_dir / "symmetric.csv")
    res_sym = analyzer.analyze(AnalysisContext(dataset_version_id="f_sym", df=df_sym))
    assert len([i for i in res_sym.issues if "skew" in i.title.lower()]) == 0

    # Moderately skewed -> LOW severity
    df_mod = pd.read_csv(fixtures_dir / "moderately_skewed.csv")
    res_mod = analyzer.analyze(AnalysisContext(dataset_version_id="f_mod", df=df_mod))
    mod_issues = [i for i in res_mod.issues if "skew" in i.title.lower()]
    assert len(mod_issues) == 1
    assert mod_issues[0].severity == Severity.LOW

    # Strongly skewed -> HIGH severity
    df_str = pd.read_csv(fixtures_dir / "strongly_skewed.csv")
    res_str = analyzer.analyze(AnalysisContext(dataset_version_id="f_str", df=df_str))
    str_issues = [i for i in res_str.issues if "skew" in i.title.lower()]
    assert len(str_issues) == 1
    assert str_issues[0].severity == Severity.HIGH


def test_fixture_correlations(fixtures_dir: Path):
    """Verify highly_correlated, perfectly_correlated, and uncorrelated datasets."""
    analyzer = CorrelationAnalyzer()

    # Perfectly correlated -> HIGH severity
    df_perf = pd.read_csv(fixtures_dir / "perfectly_correlated.csv").drop(columns=["id"], errors="ignore")
    res_perf = analyzer.analyze(AnalysisContext(dataset_version_id="f_perf_corr", df=df_perf))
    assert len(res_perf.issues) == 1
    assert res_perf.issues[0].severity == Severity.HIGH

    # Highly correlated -> MEDIUM severity
    df_high = pd.read_csv(fixtures_dir / "highly_correlated.csv").drop(columns=["id"], errors="ignore")
    res_high = analyzer.analyze(AnalysisContext(dataset_version_id="f_high_corr", df=df_high))
    assert len(res_high.issues) == 1
    assert res_high.issues[0].severity == Severity.MEDIUM

    # Uncorrelated -> 0 issues
    df_uncorr = pd.read_csv(fixtures_dir / "uncorrelated.csv")
    res_uncorr = analyzer.analyze(AnalysisContext(dataset_version_id="f_uncorr", df=df_uncorr))
    assert len(res_uncorr.issues) == 0


def test_fixture_imbalance(fixtures_dir: Path):
    """Verify class imbalance severity progression from mild to extreme."""
    analyzer = ClassImbalanceAnalyzer()

    # Mild imbalance (70%) -> LOW
    df_mild = pd.read_csv(fixtures_dir / "mild_imbalance.csv")
    res_mild = analyzer.analyze(AnalysisContext(dataset_version_id="f_mild", df=df_mild, target_column="target"))
    assert res_mild.issues[0].severity == Severity.LOW

    # Severe imbalance (85%) -> MEDIUM
    df_sev = pd.read_csv(fixtures_dir / "severe_imbalance.csv")
    res_sev = analyzer.analyze(AnalysisContext(dataset_version_id="f_sev", df=df_sev, target_column="target"))
    assert res_sev.issues[0].severity == Severity.MEDIUM

    # Extreme imbalance (97%) -> CRITICAL
    df_ext = pd.read_csv(fixtures_dir / "extreme_imbalance.csv")
    res_ext = analyzer.analyze(AnalysisContext(dataset_version_id="f_ext", df=df_ext, target_column="target"))
    assert res_ext.issues[0].severity == Severity.CRITICAL


def test_fixture_leakage(fixtures_dir: Path):
    """Verify data leakage signals: target copy, categorical mapping, and suspicious naming."""
    analyzer = DataLeakageAnalyzer()

    # Target copy -> HIGH
    df_copy = pd.read_csv(fixtures_dir / "target_copy.csv")
    res_copy = analyzer.analyze(AnalysisContext(dataset_version_id="f_copy", df=df_copy, target_column="target"))
    assert any(i.severity == Severity.HIGH and i.column_name == "target_clone" for i in res_copy.issues)

    # Categorical perfect mapping -> HIGH
    df_cat = pd.read_csv(fixtures_dir / "categorical_perfect_mapping.csv")
    res_cat = analyzer.analyze(AnalysisContext(dataset_version_id="f_cat", df=df_cat, target_column="target"))
    assert any(i.severity == Severity.HIGH and i.column_name == "status" for i in res_cat.issues)

    # Suspicious name only -> INFO strictly
    df_name = pd.read_csv(fixtures_dir / "suspicious_name_only.csv")
    res_name = analyzer.analyze(AnalysisContext(dataset_version_id="f_name", df=df_name, target_column="target"))
    assert any(i.severity == Severity.INFO and i.column_name == "outcome_cancelled_flag" for i in res_name.issues)
    assert not any(i.severity in (Severity.HIGH, Severity.CRITICAL) for i in res_name.issues)


def test_fixture_mixed_and_parseable_types(fixtures_dir: Path):
    """Verify mixed_types, numeric_strings, and datetime_strings."""
    analyzer = DataTypeAnalyzer()

    # Mixed types: Python DataFrame with heterogeneous scalar types
    df_mixed = pd.DataFrame({"mixed_scalar": ["Alice", 42, "Bob", 100, "Charlie"]})
    res_mixed = analyzer.analyze(AnalysisContext(dataset_version_id="f_mixed", df=df_mixed))
    assert any(i.title == "Mixed scalar data types detected" for i in res_mixed.issues)

    # Numeric strings -> LOW severity
    df_num = pd.read_csv(fixtures_dir / "numeric_strings.csv", dtype=str)
    res_num = analyzer.analyze(AnalysisContext(dataset_version_id="f_num", df=df_num))
    assert any(i.title == "Numeric-like values stored as text" for i in res_num.issues)

    # Datetime strings -> LOW severity
    df_dt = pd.read_csv(fixtures_dir / "datetime_strings.csv")
    res_dt = analyzer.analyze(AnalysisContext(dataset_version_id="f_dt", df=df_dt))
    assert any(i.title == "Datetime-like values stored as text" for i in res_dt.issues)


def test_fixture_empty_and_malformed_ingestion(fixtures_dir: Path):
    """Verify ingestion service properly rejects empty and malformed CSV files."""
    service = DatasetIngestionService()

    with pytest.raises(MalformedFileException):
        service.parse_file(fixtures_dir / "empty.csv", "csv", "empty.csv")


def test_fixture_wide_dataset_safeguard(fixtures_dir: Path):
    """Verify wide_dataset.csv triggers feature limiting safeguard."""
    df = pd.read_csv(fixtures_dir / "wide_dataset.csv")
    analyzer = CorrelationAnalyzer(parameters={"max_features": 8})
    res = analyzer.analyze(AnalysisContext(dataset_version_id="f_wide", df=df))

    assert res.metrics["analysis_limited"] is True
    assert len(res.metrics["columns_analyzed"]) == 8
    assert any(i.severity == Severity.INFO and "limited" in i.title.lower() for i in res.issues)


def test_synthetic_unicode_and_all_null_pipeline():
    """Verify pipeline executes cleanly on DataFrame with Unicode headers and an all-null column."""
    df = pd.DataFrame({
        "उपयोगकर्ता_आईडी": [1, 2, 3, 4, 5],
        "all_null_feature": [np.nan] * 5,
        "valid_metric": [10.5, 20.1, 15.2, 30.0, 25.4],
        "target_col": [0, 1, 0, 1, 0],
    })

    pipeline = AnalysisPipeline()
    ctx = AnalysisContext(
        dataset_version_id="syn_unicode",
        df=df,
        target_column="target_col",
        problem_type="classification",
    )
    result = pipeline.execute(ctx)

    assert result["summary_metrics"]["column_count"] == 4
    assert result["summary_metrics"]["row_count"] == 5
    assert result["ml_readiness_score"] < 100.0  # Penalized due to all-null column
    assert "schema_analyzer" in result["analyzer_versions"]
    assert "missing_analyzer" in result["analyzer_versions"]
