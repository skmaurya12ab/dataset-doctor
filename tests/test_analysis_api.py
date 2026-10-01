"""API integration tests for analysis endpoints."""

import io
import time
import uuid
from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisRun, AnalysisStatus, QualityIssue
from app.models.dataset import Dataset, DatasetVersion
from app.services.file_storage import FileStorageService


@pytest.fixture
async def seeded_dataset_version(
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a real dataset and version with Parquet file."""
    import pandas as pd

    ds = Dataset(name="API Test Dataset")
    test_db_session.add(ds)
    await test_db_session.commit()
    await test_db_session.refresh(ds)

    df = pd.DataFrame({
        "target": [0, 1, 0, 1],
        "feature_1": ["A", "B", None, "B"],
        "const_feature": [99, 99, 99, 99],
    })
    parquet_path = test_storage.save_canonical_parquet(df, ds.id, 1)

    version = DatasetVersion(
        dataset_id=ds.id,
        version_number=1,
        file_name="test.csv",
        storage_path=str(parquet_path),
        file_size_bytes=100,
        sha256_hash="hash123",
        row_count=4,
        column_count=3,
        raw_schema={"columns": [{"name": "target", "dtype": "int64"}, {"name": "feature_1", "dtype": "string"}, {"name": "const_feature", "dtype": "int64"}]},
    )
    test_db_session.add(version)
    await test_db_session.commit()
    await test_db_session.refresh(version)

    return ds.id, version.id


async def test_trigger_analysis_202_accepted(
    async_client: AsyncClient,
    seeded_dataset_version: tuple[uuid.UUID, uuid.UUID],
):
    dataset_id, version_id = seeded_dataset_version

    response = await async_client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/analyze",
        json={"target_column": "target", "problem_type": "classification"},
    )
    assert response.status_code == 202
    data = response.json()
    assert "analysis_run_id" in data
    assert data["status"] == "PENDING"
    run_id = data["analysis_run_id"]

    # Verify run status endpoint
    status_resp = await async_client.get(f"/api/v1/analyses/{run_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["id"] == run_id
    assert status_data["target_column"] == "target"
    assert status_data["problem_type"] == "classification"
    assert status_data["engine_version"] == "1.0.0"


async def test_trigger_analysis_nonexistent_dataset(
    async_client: AsyncClient,
    seeded_dataset_version: tuple[uuid.UUID, uuid.UUID],
):
    _, version_id = seeded_dataset_version
    fake_dataset_id = uuid.uuid4()

    response = await async_client.post(
        f"/api/v1/datasets/{fake_dataset_id}/versions/{version_id}/analyze",
        json={},
    )
    assert response.status_code == 404


async def test_trigger_analysis_invalid_target_column(
    async_client: AsyncClient,
    seeded_dataset_version: tuple[uuid.UUID, uuid.UUID],
):
    dataset_id, version_id = seeded_dataset_version

    response = await async_client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/analyze",
        json={"target_column": "non_existent_column_xyz"},
    )
    assert response.status_code == 422
    assert "does not exist in dataset schema" in response.json()["detail"]


async def test_get_analysis_issues_endpoint_and_filters(
    async_client: AsyncClient,
    test_db_session: AsyncSession,
    seeded_dataset_version: tuple[uuid.UUID, uuid.UUID],
):
    _, version_id = seeded_dataset_version

    # Manually create run and issues for predictable API test
    run = AnalysisRun(
        dataset_version_id=version_id,
        status=AnalysisStatus.COMPLETED.value,
        engine_version="1.0.0",
        total_issues_count=2,
        critical_issues_count=1,
        summary_metrics={"row_count": 4},
        analyzer_versions={"missing_analyzer": "1.0.0", "cardinality_analyzer": "1.0.0"},
    )
    test_db_session.add(run)
    await test_db_session.commit()
    await test_db_session.refresh(run)

    qi1 = QualityIssue(
        analysis_run_id=run.id,
        dataset_version_id=version_id,
        module="missing_analyzer",
        analyzer_version="1.0.0",
        parameters_used={},
        category="MISSING_VALUES",
        severity="CRITICAL",
        column_name="feature_1",
        title="Missing values detected",
        description="Missing values present",
        evidence={},
    )
    qi2 = QualityIssue(
        analysis_run_id=run.id,
        dataset_version_id=version_id,
        module="cardinality_analyzer",
        analyzer_version="1.0.0",
        parameters_used={},
        category="CARDINALITY",
        severity="MEDIUM",
        column_name="const_feature",
        title="Constant column detected",
        description="Zero variance",
        evidence={},
    )
    test_db_session.add_all([qi1, qi2])
    await test_db_session.commit()

    # Query all issues
    all_resp = await async_client.get(f"/api/v1/analyses/{run.id}/issues")
    assert all_resp.status_code == 200
    all_data = all_resp.json()
    assert all_data["total"] == 2
    assert len(all_data["items"]) == 2

    # Query filtered by severity=CRITICAL
    crit_resp = await async_client.get(f"/api/v1/analyses/{run.id}/issues?severity=CRITICAL")
    assert crit_resp.status_code == 200
    crit_data = crit_resp.json()
    assert crit_data["total"] == 1
    assert crit_data["items"][0]["severity"] == "CRITICAL"

    # Query filtered by module=cardinality_analyzer
    card_resp = await async_client.get(f"/api/v1/analyses/{run.id}/issues?module=cardinality_analyzer")
    assert card_resp.status_code == 200
    card_data = card_resp.json()
    assert card_data["total"] == 1
    assert card_data["items"][0]["module"] == "cardinality_analyzer"

    # Query filtered by column=feature_1
    col_resp = await async_client.get(f"/api/v1/analyses/{run.id}/issues?column=feature_1")
    assert col_resp.status_code == 200
    col_data = col_resp.json()
    assert col_data["total"] == 1
    assert col_data["items"][0]["column_name"] == "feature_1"


async def test_get_analysis_nonexistent_run_404(async_client: AsyncClient):
    fake_run_id = uuid.uuid4()
    resp = await async_client.get(f"/api/v1/analyses/{fake_run_id}")
    assert resp.status_code == 404

    issues_resp = await async_client.get(f"/api/v1/analyses/{fake_run_id}/issues")
    assert issues_resp.status_code == 404
