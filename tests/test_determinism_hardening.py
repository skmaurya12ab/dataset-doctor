"""Comprehensive determinism and reproducibility verification suite.

Verifies:
- 100% stable outputs across all 10 analyzers and scoring heuristic over multiple runs
- OutlierAnalyzer Isolation Forest deterministic sampling stability
- CorrelationAnalyzer deterministic row sampling stability
- RemediationExecutor transformation order and resulting DataFrame byte-level determinism
- Explicit distinction between deterministic facts (findings, evidence, scores)
  and intentional non-deterministic metadata (UUIDs, timestamps)
"""

import numpy as np
import pandas as pd
import pytest

from app.engine.base import AnalysisContext
from app.engine.modules.correlation_analyzer import CorrelationAnalyzer
from app.engine.modules.outlier_analyzer import OutlierAnalyzer
from app.engine.pipeline import AnalysisPipeline
from app.schemas.ai import TransformationSpec
from app.services.remediation_executor import RemediationExecutor


def test_full_pipeline_multi_run_determinism():
    """Execute the full 10-module pipeline 5 times on the same input and verify 100% stability."""
    rng = np.random.RandomState(42)
    n = 200
    df = pd.DataFrame({
        "id": range(1, n + 1),
        "feat_norm": rng.normal(50, 10, n),
        "feat_outlier": [20.0] * (n - 2) + [1000.0, -1000.0],
        "feat_missing": [None if i % 10 == 0 else float(i) for i in range(n)],
        "feat_const": ["CONSTANT"] * n,
        "feat_dup": [i % 50 for i in range(n)],
        "target": [0] * 160 + [1] * 40,
    })

    runs = []
    pipeline = AnalysisPipeline()

    for run_idx in range(5):
        ctx = AnalysisContext(
            dataset_version_id=f"ver_det_{run_idx}",
            df=df.copy(),
            target_column="target",
            problem_type="classification",
            parameters={
                "outlier_analyzer": {"random_seed": 42},
                "correlation_analyzer": {"random_seed": 42},
            },
        )
        res = pipeline.execute(ctx)
        runs.append(res)

    base = runs[0]

    for run_idx, res in enumerate(runs[1:], start=2):
        # 1. Total and critical issue counts must match
        assert res["total_issues_count"] == base["total_issues_count"]
        assert res["critical_issues_count"] == base["critical_issues_count"]

        # 2. Heuristic ML readiness score must match exactly
        assert res["ml_readiness_score"] == base["ml_readiness_score"]
        assert res["heuristic_breakdown"].heuristic_score == base["heuristic_breakdown"].heuristic_score
        assert res["heuristic_breakdown"].total_penalties == base["heuristic_breakdown"].total_penalties
        assert res["heuristic_breakdown"].rating == base["heuristic_breakdown"].rating

        # 3. Itemized deductions must match in order and value
        base_penalties = base["heuristic_breakdown"].itemized_penalties
        run_penalties = res["heuristic_breakdown"].itemized_penalties
        assert len(base_penalties) == len(run_penalties)
        for p1, p2 in zip(base_penalties, run_penalties):
            assert p1.module == p2.module
            assert p1.severity == p2.severity
            assert p1.penalty == p2.penalty
            assert p1.column_name == p2.column_name

        # 4. Summary metrics match
        assert res["summary_metrics"] == base["summary_metrics"]

        # 5. Granular QualityIssues match on all analytical properties
        issues_base = base["all_issues"]
        issues_run = res["all_issues"]
        assert len(issues_base) == len(issues_run)

        for i1, i2 in zip(issues_base, issues_run):
            assert i1.module == i2.module
            assert i1.category == i2.category
            assert i1.severity == i2.severity
            assert i1.column_name == i2.column_name
            assert i1.title == i2.title
            assert i1.evidence == i2.evidence
            # Note: QualityIssue.id is intentionally a fresh UUID4, but analytical properties are identical


def test_outlier_analyzer_sampling_reproducibility():
    """Verify Isolation Forest sampling reproduces exact same outliers when random_seed is fixed."""
    rng = np.random.RandomState(42)
    n = 500
    df = pd.DataFrame({
        "feat_a": rng.normal(0, 1, n),
        "feat_b": rng.normal(5, 2, n),
    })

    results = []
    for _ in range(3):
        analyzer = OutlierAnalyzer(parameters={"maximum_sample_size": 100, "random_seed": 12345})
        ctx = AnalysisContext(dataset_version_id="seed_test", df=df.copy())
        res = analyzer.analyze(ctx)
        results.append(res)

    for res in results[1:]:
        if_base = results[0].metrics["multivariate_isolation_forest"]
        if_curr = res.metrics["multivariate_isolation_forest"]
        assert if_curr["outlier_count"] == if_base["outlier_count"]
        assert if_curr["outlier_percentage"] == if_base["outlier_percentage"]
        assert if_curr["sample_size"] == 100
        assert if_curr["random_seed"] == 12345


def test_correlation_analyzer_sampling_reproducibility():
    """Verify CorrelationAnalyzer row sampling reproduces exact matrix with fixed seed."""
    rng = np.random.RandomState(42)
    n = 300
    df = pd.DataFrame({
        "x": rng.normal(10, 2, n),
        "y": rng.normal(20, 3, n),
    })

    results = []
    for _ in range(3):
        analyzer = CorrelationAnalyzer(parameters={"max_sample_size": 100, "random_seed": 999})
        ctx = AnalysisContext(dataset_version_id="corr_seed", df=df.copy())
        res = analyzer.analyze(ctx)
        results.append(res)

    for res in results[1:]:
        assert res.metrics["sampling_applied"] is True
        assert res.metrics["sample_size"] == 100
        assert res.metrics["random_seed"] == 999
        assert res.metrics["high_correlation_pairs"] == results[0].metrics["high_correlation_pairs"]


def test_remediation_executor_deterministic_execution_and_metrics():
    """Verify RemediationExecutor applies transformations in identical sequence and produces identical data."""
    df_raw = pd.DataFrame({
        "id": [1, 2, 2, 3, 4],
        "drop_me": [10, 20, 20, 30, 40],
        "age": [25.0, 30.0, 30.0, None, 45.0],
    })

    plan = [
        TransformationSpec(action="DROP_COLUMN", column="drop_me", parameters={}, rationale="Drop", source_issue_ids=[]),
        TransformationSpec(action="REMOVE_DUPLICATES", column=None, parameters={"keep": "first"}, rationale="Dedup", source_issue_ids=[]),
        TransformationSpec(action="IMPUTE", column="age", parameters={"strategy": "mean"}, rationale="Impute", source_issue_ids=[]),
    ]

    runs = []
    executor = RemediationExecutor()

    for _ in range(3):
        df_res, prov = executor.execute_plan(df_raw.copy(), plan)
        runs.append((df_res, prov))

    base_df, base_prov = runs[0]

    for curr_df, curr_prov in runs[1:]:
        # Exact dataframe equality
        pd.testing.assert_frame_equal(curr_df, base_df)

        # Exact provenance records equality
        assert len(curr_prov) == len(base_prov)
        for p1, p2 in zip(base_prov, curr_prov):
            assert p1["action"] == p2["action"]
            assert p1["applied_order"] == p2["applied_order"]
            assert p1["rows_changed"] == p2["rows_changed"]
            assert p1["executor_version"] == "1.0.0"
