"""Persistence and lifecycle tests for AnalysisRun and QualityIssue models."""

from datetime import datetime, timezone
import uuid
import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisRun, AnalysisStatus, QualityIssue
from app.models.dataset import Dataset, DatasetVersion
from app.services.analysis_service import AnalysisService
from app.services.file_storage import FileStorageService


@pytest.fixture
async def sample_version_with_parquet(
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
) -> DatasetVersion:
    """Fixture creating a Dataset and DatasetVersion with saved canonical Parquet."""
    ds = Dataset(name="Persistence Test Dataset", description="Used for persistence unit tests")
    test_db_session.add(ds)
    await test_db_session.commit()
    await test_db_session.refresh(ds)

    df = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "name": ["Alice", "Bob", None, "Diana"],
        "constant_col": ["VAL", "VAL", "VAL", "VAL"],
    })
    parquet_path = test_storage.save_canonical_parquet(df, ds.id, 1)

    version = DatasetVersion(
        dataset_id=ds.id,
        version_number=1,
        file_name="test.csv",
        storage_path=str(parquet_path),
        file_size_bytes=100,
        sha256_hash="dummy_hash",
        row_count=4,
        column_count=3,
        raw_schema={"columns": [{"name": "id", "dtype": "int64"}, {"name": "name", "dtype": "string"}, {"name": "constant_col", "dtype": "string"}]},
    )
    test_db_session.add(version)
    await test_db_session.commit()
    await test_db_session.refresh(version)
    return version


async def test_completed_analysis_persistence(
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    sample_version_with_parquet: DatasetVersion,
):
    service = AnalysisService()
    version = sample_version_with_parquet

    # Create PENDING AnalysisRun
    run = AnalysisRun(
        dataset_version_id=version.id,
        status=AnalysisStatus.PENDING.value,
        engine_version="1.0.0",
        summary_metrics={},
        analyzer_versions={},
    )
    test_db_session.add(run)
    await test_db_session.commit()
    await test_db_session.refresh(run)

    # Execute directly with current session
    await service.execute_directly(test_db_session, run.id, version.id)

    # Re-fetch run
    refreshed_run = await test_db_session.get(AnalysisRun, run.id)
    assert refreshed_run is not None
    assert refreshed_run.status == AnalysisStatus.COMPLETED.value
    assert refreshed_run.engine_version == "1.0.0"
    assert "schema_analyzer" in refreshed_run.analyzer_versions
    assert refreshed_run.total_issues_count > 0
    assert refreshed_run.execution_time_ms is not None
    assert refreshed_run.completed_at is not None

    # Verify persisted QualityIssues
    stmt = select(QualityIssue).where(QualityIssue.analysis_run_id == run.id)
    res = await test_db_session.execute(stmt)
    issues = list(res.scalars().all())

    assert len(issues) == refreshed_run.total_issues_count
    for qi in issues:
        assert qi.analysis_run_id == run.id
        assert qi.dataset_version_id == version.id
        assert qi.module in ["schema_analyzer", "dtype_analyzer", "missing_analyzer", "duplicate_analyzer", "cardinality_analyzer"]
        assert qi.analyzer_version == "1.0.0"
        assert isinstance(qi.parameters_used, dict)
        assert qi.detected_at is not None
        assert qi.title != ""
        assert qi.description != ""


async def test_failed_analysis_persistence_when_file_missing(
    test_db_session: AsyncSession,
    sample_version_with_parquet: DatasetVersion,
):
    service = AnalysisService()
    version = sample_version_with_parquet

    # Create a non-existent version ID to force failure
    invalid_version_id = uuid.uuid4()
    run = AnalysisRun(
        dataset_version_id=version.id,
        status=AnalysisStatus.PENDING.value,
        engine_version="1.0.0",
        summary_metrics={},
        analyzer_versions={},
    )
    test_db_session.add(run)
    await test_db_session.commit()
    await test_db_session.refresh(run)

    # Execute with invalid version ID
    await service.execute_directly(test_db_session, run.id, invalid_version_id)

    refreshed_run = await test_db_session.get(AnalysisRun, run.id)
    assert refreshed_run is not None
    assert refreshed_run.status == AnalysisStatus.FAILED.value
    assert refreshed_run.error_message is not None
    assert "not found" in refreshed_run.error_message
