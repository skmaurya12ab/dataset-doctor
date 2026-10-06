"""Unit tests for ComparisonService testing metrics, issue transitions, and heuristic score deltas."""

from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException
from app.models.analysis import AnalysisRun, AnalysisStatus, QualityIssue
from app.models.dataset import Dataset, DatasetVersion
from app.services.comparison_service import ComparisonService, calculate_rating, make_semantic_issue_key


@pytest.fixture
async def comparison_fixture(test_db_session: AsyncSession):
    """Fixture creating dataset with two versions and analysis runs with known differences."""
    dataset = Dataset(id=uuid.uuid4(), name="Comparison Test Dataset")
    test_db_session.add(dataset)

    # Version 1 (Before)
    v1 = DatasetVersion(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        version_number=1,
        file_name="data_v1.parquet",
        storage_path="uploads/v1.parquet",
        file_size_bytes=10000,
        sha256_hash="hash_v1",
        row_count=1000,
        column_count=10,
        raw_schema={"columns": []},
    )
    test_db_session.add(v1)

    # Version 2 (After remediation)
    v2 = DatasetVersion(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        parent_version_id=v1.id,
        version_number=2,
        file_name="data_v2.parquet",
        storage_path="uploads/v2.parquet",
        file_size_bytes=9000,
        sha256_hash="hash_v2",
        row_count=950,
        column_count=9,
        raw_schema={"columns": []},
    )
    test_db_session.add(v2)

    # Analysis Run 1 (Before)
    run1 = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=v1.id,
        status=AnalysisStatus.COMPLETED.value,
        target_column="target",
        ml_readiness_score=55.0,
        total_issues_count=3,
        critical_issues_count=1,
        summary_metrics={
            "row_count": 1000,
            "column_count": 10,
            "missing_cells": 100,
            "missing_percentage": 10.0,
            "duplicate_rows": 50,
        },
        completed_at=datetime.now(timezone.utc),
    )
    test_db_session.add(run1)

    # Issue 1: Will be RESOLVED in v2 (missing values in income)
    iss1 = QualityIssue(
        id=uuid.uuid4(),
        analysis_run_id=run1.id,
        dataset_version_id=v1.id,
        module="missing_analyzer",
        analyzer_version="1.0.0",
        category="MISSING_VALUES",
        severity="HIGH",
        column_name="income",
        title="High missingness in income",
        description="income is 20% missing",
        evidence={},
    )
    # Issue 2: Will be CHANGED in v2 (outliers in age: HIGH -> LOW)
    iss2 = QualityIssue(
        id=uuid.uuid4(),
        analysis_run_id=run1.id,
        dataset_version_id=v1.id,
        module="outlier_analyzer",
        analyzer_version="1.0.0",
        category="OUTLIERS",
        severity="HIGH",
        column_name="age",
        title="Severe outliers in age",
        description="age has extreme values",
        evidence={},
    )
    # Issue 3: Will be UNCHANGED in v2 (imbalance in target)
    iss3 = QualityIssue(
        id=uuid.uuid4(),
        analysis_run_id=run1.id,
        dataset_version_id=v1.id,
        module="imbalance_analyzer",
        analyzer_version="1.0.0",
        category="CLASS_IMBALANCE",
        severity="MEDIUM",
        column_name="target",
        title="Moderate imbalance",
        description="target ratio 80:20",
        evidence={},
    )
    test_db_session.add_all([iss1, iss2, iss3])

    # Analysis Run 2 (After)
    run2 = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=v2.id,
        status=AnalysisStatus.COMPLETED.value,
        target_column="target",
        ml_readiness_score=85.0,
        total_issues_count=3,
        critical_issues_count=0,
        summary_metrics={
            "row_count": 950,
            "column_count": 9,
            "missing_cells": 0,
            "missing_percentage": 0.0,
            "duplicate_rows": 0,
        },
        completed_at=datetime.now(timezone.utc),
    )
    test_db_session.add(run2)

    # Issue 2 in run 2 (CHANGED: severity is now LOW)
    iss2_after = QualityIssue(
        id=uuid.uuid4(),
        analysis_run_id=run2.id,
        dataset_version_id=v2.id,
        module="outlier_analyzer",
        analyzer_version="1.0.0",
        category="OUTLIERS",
        severity="LOW",
        column_name="age",
        title="Minor outliers in age",
        description="age outliers clipped",
        evidence={},
    )
    # Issue 3 in run 2 (UNCHANGED: severity is still MEDIUM)
    iss3_after = QualityIssue(
        id=uuid.uuid4(),
        analysis_run_id=run2.id,
        dataset_version_id=v2.id,
        module="imbalance_analyzer",
        analyzer_version="1.0.0",
        category="CLASS_IMBALANCE",
        severity="MEDIUM",
        column_name="target",
        title="Moderate imbalance",
        description="target ratio 80:20",
        evidence={},
    )
    # Issue 4 in run 2 (NEW: newly detected issue in category)
    iss4_new = QualityIssue(
        id=uuid.uuid4(),
        analysis_run_id=run2.id,
        dataset_version_id=v2.id,
        module="cardinality_analyzer",
        analyzer_version="1.0.0",
        category="HIGH_CARDINALITY",
        severity="LOW",
        column_name="category",
        title="Slight cardinality shift",
        description="new categories detected",
        evidence={},
    )
    test_db_session.add_all([iss2_after, iss3_after, iss4_new])
    await test_db_session.commit()

    return {"dataset": dataset, "v1": v1, "v2": v2, "run1": run1, "run2": run2}


@pytest.mark.asyncio
async def test_compare_versions_metrics_and_deltas(test_db_session: AsyncSession, comparison_fixture):
    fix = comparison_fixture
    service = ComparisonService()

    resp = await service.compare_versions(
        db=test_db_session,
        dataset_id=fix["dataset"].id,
        v1_id=fix["v1"].id,
        v2_id=fix["v2"].id,
    )

    # Check metric deltas
    metrics = resp.dataset_metrics
    assert metrics["rows"].before == 1000
    assert metrics["rows"].after == 950
    assert metrics["rows"].delta == -50

    assert metrics["columns"].before == 10
    assert metrics["columns"].after == 9
    assert metrics["columns"].delta == -1

    assert metrics["missing_cells"].before == 100
    assert metrics["missing_cells"].after == 0
    assert metrics["missing_cells"].delta == -100

    assert metrics["duplicate_rows"].before == 50
    assert metrics["duplicate_rows"].after == 0
    assert metrics["duplicate_rows"].delta == -50


@pytest.mark.asyncio
async def test_compare_versions_quality_issues(test_db_session: AsyncSession, comparison_fixture):
    fix = comparison_fixture
    service = ComparisonService()

    resp = await service.compare_versions(
        db=test_db_session,
        dataset_id=fix["dataset"].id,
        v1_id=fix["v1"].id,
        v2_id=fix["v2"].id,
    )

    quality = resp.quality
    assert quality["issues_resolved"] == 1  # missing_analyzer on income
    assert quality["issues_changed"] == 1   # outlier_analyzer on age (HIGH -> LOW)
    assert quality["issues_unchanged"] == 1 # imbalance_analyzer on target (MEDIUM)
    assert quality["new_issues"] == 1       # cardinality_analyzer on category

    # Verify granular items
    items = {item["semantic_key"]: item for item in quality["items"]}
    assert items["missing_analyzer:MISSING_VALUES:income"]["status"] == "RESOLVED"
    assert items["outlier_analyzer:OUTLIERS:age"]["status"] == "CHANGED"
    assert items["outlier_analyzer:OUTLIERS:age"]["before_severity"] == "HIGH"
    assert items["outlier_analyzer:OUTLIERS:age"]["after_severity"] == "LOW"
    assert items["imbalance_analyzer:CLASS_IMBALANCE:target"]["status"] == "UNCHANGED"
    assert items["cardinality_analyzer:HIGH_CARDINALITY:category"]["status"] == "NEW"


@pytest.mark.asyncio
async def test_compare_versions_heuristic_scores(test_db_session: AsyncSession, comparison_fixture):
    fix = comparison_fixture
    service = ComparisonService()

    resp = await service.compare_versions(
        db=test_db_session,
        dataset_id=fix["dataset"].id,
        v1_id=fix["v1"].id,
        v2_id=fix["v2"].id,
    )

    heuristic = resp.heuristic
    assert heuristic.before_score == 55.0
    assert heuristic.after_score == 85.0
    assert heuristic.delta == 30.0
    assert heuristic.before_rating == "MODERATE"
    assert heuristic.after_rating == "EXCELLENT"
    assert "signals, not actual model performance" in heuristic.note


@pytest.mark.asyncio
async def test_compare_versions_nonexistent_version(test_db_session: AsyncSession, comparison_fixture):
    fix = comparison_fixture
    service = ComparisonService()

    fake_id = uuid.uuid4()
    with pytest.raises(EntityNotFoundException):
        await service.compare_versions(
            db=test_db_session,
            dataset_id=fix["dataset"].id,
            v1_id=fake_id,
            v2_id=fix["v2"].id,
        )


def test_calculate_rating():
    assert calculate_rating(90.0) == "EXCELLENT"
    assert calculate_rating(80.0) == "EXCELLENT"
    assert calculate_rating(70.0) == "GOOD"
    assert calculate_rating(55.0) == "MODERATE"
    assert calculate_rating(40.0) == "POOR"
    assert calculate_rating(None) is None
