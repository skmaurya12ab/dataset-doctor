"""Performance and scalability test on moderately sized synthetic dataset."""

import time
import numpy as np
import pandas as pd
import pytest

from app.engine.base import AnalysisContext
from app.engine.pipeline import AnalysisPipeline


def test_performance_moderately_sized_dataset():
    """Verify that full pipeline completes on 5,000 rows x 20 features within a reasonable bound.

    Confirms correlation limits, sampling safeguards, and records measured execution time.
    """
    n_rows = 5000
    n_cols = 20
    rng = np.random.RandomState(42)

    data = {"id": range(1, n_rows + 1)}
    for i in range(n_cols):
        data[f"feat_{i}"] = rng.normal(10.0 * (i + 1), 5.0, n_rows)

    # Add a binary target column
    data["target"] = [0] * 4000 + [1] * 1000

    df = pd.DataFrame(data)

    params = {
        "outlier_analyzer": {"maximum_sample_size": 1000, "random_seed": 42},
        "correlation_analyzer": {"max_sample_size": 1000, "max_features": 15, "random_seed": 42},
    }

    ctx = AnalysisContext(
        dataset_version_id="ver_perf_5k",
        df=df,
        target_column="target",
        problem_type="classification",
        parameters=params,
    )

    pipeline = AnalysisPipeline()

    start_perf = time.perf_counter()
    result = pipeline.execute(ctx)
    elapsed_seconds = time.perf_counter() - start_perf

    # 1. Execution must complete in under 5.0 seconds
    assert elapsed_seconds < 5.0, f"Execution too slow: {elapsed_seconds:.2f}s"

    # 2. Correlation features guard was applied
    corr_m = result["combined_metrics"]["correlation_analyzer"]
    assert corr_m["analysis_limited"] is True
    assert len(corr_m["columns_analyzed"]) == 15
    assert corr_m["sampling_applied"] is True

    # 3. Outlier sampling was applied
    outlier_m = result["combined_metrics"]["outlier_analyzer"]["multivariate_isolation_forest"]
    assert outlier_m["sampling_applied"] is True
    assert outlier_m["sample_size"] == 1000

    # 4. Pipeline returned all expected result structures
    assert result["total_issues_count"] >= 0
    assert result["ml_readiness_score"] is not None
    assert result["heuristic_breakdown"] is not None

    print(f"\n[PERFORMANCE BENCHMARK] 5,000 rows x 20 features executed in: {elapsed_seconds:.3f} seconds")
