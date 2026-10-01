"""Determinism and reproducibility test for Phase 2 analysis engine."""

import pandas as pd
import pytest

from app.engine.base import AnalysisContext
from app.engine.pipeline import AnalysisPipeline


def test_pipeline_strict_determinism():
    """Verify that identical inputs produce 100% identical analytical outputs and evidence."""
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 1],
        "name": ["Alice", "Bob", None, "Diana", "Alice"],
        "age_text": ["25", "30", "35", "40", "25"],
        "status": ["active", "active", "active", "active", "active"],
        "mixed_feature": ["val", 123, "val", 456, "val"],
    })

    ctx1 = AnalysisContext(
        dataset_version_id="fixed_ver_1",
        df=df.copy(),
        parameters={"schema_analyzer": {}, "missing_analyzer": {}},
    )
    ctx2 = AnalysisContext(
        dataset_version_id="fixed_ver_1",
        df=df.copy(),
        parameters={"schema_analyzer": {}, "missing_analyzer": {}},
    )

    pipeline1 = AnalysisPipeline()
    pipeline2 = AnalysisPipeline()

    res1 = pipeline1.execute(ctx1)
    res2 = pipeline2.execute(ctx2)

    # 1. Summary metrics must match exactly
    assert res1["summary_metrics"] == res2["summary_metrics"]

    # 2. Combined module metrics must match exactly
    assert res1["combined_metrics"] == res2["combined_metrics"]

    # 3. Total and critical issue counts must match exactly
    assert res1["total_issues_count"] == res2["total_issues_count"]
    assert res1["critical_issues_count"] == res2["critical_issues_count"]

    # 4. Analyzer versions must match
    assert res1["analyzer_versions"] == res2["analyzer_versions"]

    # 5. Granular QualityIssues must match on all deterministic properties
    issues1 = res1["all_issues"]
    issues2 = res2["all_issues"]
    assert len(issues1) == len(issues2)

    for i1, i2 in zip(issues1, issues2):
        assert i1.module == i2.module
        assert i1.analyzer_version == i2.analyzer_version
        assert i1.category == i2.category
        assert i1.severity == i2.severity
        assert i1.column_name == i2.column_name
        assert i1.title == i2.title
        assert i1.description == i2.description
        assert i1.evidence == i2.evidence
    # 6. Heuristic score and breakdown must match exactly
    assert res1["ml_readiness_score"] == res2["ml_readiness_score"]
    assert res1["heuristic_breakdown"].heuristic_score == res2["heuristic_breakdown"].heuristic_score
    assert res1["heuristic_breakdown"].total_penalties == res2["heuristic_breakdown"].total_penalties
    assert res1["heuristic_breakdown"].rating == res2["heuristic_breakdown"].rating


def test_pipeline_phase3_advanced_determinism():
    """Verify that Phase 3 statistical analyzers and ML readiness heuristics are 100% deterministic."""
    import numpy as np

    rng = np.random.RandomState(42)
    n = 120
    x = np.linspace(10, 100, n)
    df = pd.DataFrame({
        "id": range(1, n + 1),
        "feat_norm": rng.normal(50, 5, n),
        "feat_skew": np.exp(rng.normal(0, 1.2, n)),
        "feat_corr1": x,
        "feat_corr2": x * 1.5,
        "target": [0] * 100 + [1] * 20,
    })

    params = {
        "outlier_analyzer": {"maximum_sample_size": 50, "random_seed": 42},
        "correlation_analyzer": {"max_sample_size": 60, "random_seed": 42},
    }

    ctx1 = AnalysisContext(
        dataset_version_id="fixed_ver_p3",
        df=df.copy(),
        target_column="target",
        problem_type="classification",
        parameters=params,
    )
    ctx2 = AnalysisContext(
        dataset_version_id="fixed_ver_p3",
        df=df.copy(),
        target_column="target",
        problem_type="classification",
        parameters=params,
    )

    p1 = AnalysisPipeline()
    p2 = AnalysisPipeline()

    res1 = p1.execute(ctx1)
    res2 = p2.execute(ctx2)

    assert res1["summary_metrics"] == res2["summary_metrics"]
    assert res1["combined_metrics"] == res2["combined_metrics"]
    assert res1["ml_readiness_score"] == res2["ml_readiness_score"]
    assert res1["heuristic_breakdown"].heuristic_score == res2["heuristic_breakdown"].heuristic_score
    assert res1["heuristic_breakdown"].total_penalties == res2["heuristic_breakdown"].total_penalties
    assert len(res1["all_issues"]) == len(res2["all_issues"])
