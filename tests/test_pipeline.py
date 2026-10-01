"""Unit tests for deterministic AnalysisPipeline."""

import pandas as pd
import pytest

from app.engine.base import AnalysisContext
from app.engine.pipeline import AnalysisPipeline, get_default_analyzers


def test_pipeline_executes_all_ten_analyzers_in_order():
    pipeline = AnalysisPipeline()
    expected_order = [
        "schema_analyzer",
        "dtype_analyzer",
        "missing_analyzer",
        "duplicate_analyzer",
        "cardinality_analyzer",
        "outlier_analyzer",
        "distribution_analyzer",
        "correlation_analyzer",
        "imbalance_analyzer",
        "leakage_analyzer",
    ]
    actual_order = [a.name for a in pipeline.analyzers]
    assert actual_order == expected_order

    df = pd.DataFrame({
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Charlie"],
        "score": [95.0, 80.5, 88.0],
    })
    ctx = AnalysisContext(dataset_version_id="ver_pipeline", df=df)
    output = pipeline.execute(ctx)

    assert "module_results" in output
    assert len(output["module_results"]) == 10
    result_names = [m.module_name for m in output["module_results"]]
    assert result_names == expected_order

    # Verify all analyzer versions present
    assert len(output["analyzer_versions"]) == 10
    for mod_name in expected_order:
        assert output["analyzer_versions"][mod_name] == "1.0.0"

    # Verify timings
    assert output["total_execution_time_ms"] >= 0
    for mod_res in output["module_results"]:
        assert mod_res.execution_time_ms >= 0

    # Verify summary metrics
    summary = output["summary_metrics"]
    assert summary["row_count"] == 3
    assert summary["column_count"] == 3
    assert summary["missing_columns"] == 0
    assert summary["duplicate_row_count"] == 0


def test_pipeline_aggregates_issues_from_multiple_modules():
    pipeline = AnalysisPipeline()
    # Create dataset with multiple issues:
    # 1. Duplicate column header ("dup", "dup")
    # 2. Duplicate rows (2 identical rows)
    # 3. Missing values (1 null in col3)
    # 4. Constant column
    df = pd.DataFrame(
        [
            ["A", "A", None, "SAME"],
            ["A", "A", 10.0, "SAME"],
            ["B", "B", 20.0, "SAME"],
        ],
        columns=["col_dup", "col_dup", "col_miss", "col_const"],
    )
    ctx = AnalysisContext(dataset_version_id="ver_multi_issues", df=df)
    output = pipeline.execute(ctx)

    all_issues = output["all_issues"]
    modules_detected = {i.module for i in all_issues}

    # Should detect schema issue (duplicate columns), missing issue, and cardinality issue (constant col)
    assert "schema_analyzer" in modules_detected
    assert "missing_analyzer" in modules_detected
    assert "cardinality_analyzer" in modules_detected
    assert output["total_issues_count"] == len(all_issues)
