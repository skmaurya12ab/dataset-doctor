"""API integration tests for AI explanation and remediation plan endpoints."""

import uuid
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_llm_provider
from app.main import app
from app.models.analysis import AnalysisRun, AnalysisStatus, QualityIssue
from app.models.dataset import Dataset, DatasetVersion
from app.services.ai.mock_provider import MockLLMProvider


@pytest.fixture
async def api_test_data(test_db_session: AsyncSession) -> tuple[AnalysisRun, QualityIssue]:
    """Create test dataset and completed analysis run with a quality issue."""
    dataset = Dataset(
        id=uuid.uuid4(),
        name="API Test Dataset",
        owner_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    )
    test_db_session.add(dataset)

    version = DatasetVersion(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        version_number=1,
        file_name="data.csv",
        storage_path="uploads/data.parquet",
        file_size_bytes=2048,
        sha256_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        row_count=500,
        column_count=4,
        raw_schema={"target": "int64"},
    )
    test_db_session.add(version)

    run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=version.id,
        status=AnalysisStatus.COMPLETED.value,
        target_column="target",
        problem_type="classification",
        summary_metrics={"null_percentage": 1.5},
        completed_at=datetime.now(timezone.utc),
    )
    test_db_session.add(run)

    issue = QualityIssue(
        id=uuid.uuid4(),
        analysis_run_id=run.id,
        dataset_version_id=version.id,
        module="missing_analyzer",
        analyzer_version="1.0.0",
        category="MISSING_VALUES",
        severity="MEDIUM",
        column_name="feature_x",
        title="Missing values in feature_x",
        description="Feature x is missing 10% of values",
        evidence={"missing_percentage": 10.0},
        remediation_hint="Impute with mean",
        detected_at=datetime.now(timezone.utc),
    )
    test_db_session.add(issue)

    await test_db_session.commit()
    await test_db_session.refresh(run)
    await test_db_session.refresh(issue)

    return run, issue


@pytest.mark.asyncio
async def test_api_explain_finding_lifecycle(
    async_client: AsyncClient,
    api_test_data: tuple[AnalysisRun, QualityIssue],
):
    """Test POST /api/v1/analyses/{run_id}/issues/{issue_id}/explain endpoint."""
    run, issue = api_test_data

    # 1. Successful first call
    resp = await async_client.post(f"/api/v1/analyses/{run.id}/issues/{issue.id}/explain")
    assert resp.status_code == 200
    data = resp.json()
    assert data["issue_id"] == str(issue.id)
    assert data["cached"] is False
    assert "explanation" in data
    assert "why_it_matters" in data
    assert "practical_impact" in data
    assert isinstance(data["recommended_actions"], list)

    # 2. Idempotent second call returns cached result
    resp2 = await async_client.post(f"/api/v1/analyses/{run.id}/issues/{issue.id}/explain")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cached"] is True
    assert data2["explanation"] == data["explanation"]


@pytest.mark.asyncio
async def test_api_explain_finding_not_found(
    async_client: AsyncClient,
    api_test_data: tuple[AnalysisRun, QualityIssue],
):
    """Test 404 error when run or issue does not exist."""
    run, _ = api_test_data
    fake_id = uuid.uuid4()

    resp = await async_client.post(f"/api/v1/analyses/{fake_id}/issues/{fake_id}/explain")
    assert resp.status_code == 404

    resp2 = await async_client.post(f"/api/v1/analyses/{run.id}/issues/{fake_id}/explain")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_api_generate_and_get_ai_plan(
    async_client: AsyncClient,
    api_test_data: tuple[AnalysisRun, QualityIssue],
):
    """Test POST /generate-ai-plan and GET /ai-plan endpoints."""
    run, _ = api_test_data

    # 1. Initial GET before generation returns 404
    resp_get_init = await async_client.get(f"/api/v1/analyses/{run.id}/ai-plan")
    assert resp_get_init.status_code == 404

    # 2. POST /generate-ai-plan generates plan
    resp_post = await async_client.post(f"/api/v1/analyses/{run.id}/generate-ai-plan")
    assert resp_post.status_code == 200
    post_data = resp_post.json()
    assert post_data["analysis_run_id"] == str(run.id)
    assert post_data["cached"] is False
    assert len(post_data["transformation_specs"]) > 0

    # 3. GET /ai-plan now returns stored plan
    resp_get = await async_client.get(f"/api/v1/analyses/{run.id}/ai-plan")
    assert resp_get.status_code == 200
    get_data = resp_get.json()
    assert get_data["id"] == post_data["id"]
    assert get_data["cached"] is True

    # 4. POST with force_regenerate=true creates fresh plan
    resp_regen = await async_client.post(f"/api/v1/analyses/{run.id}/generate-ai-plan?force_regenerate=true")
    assert resp_regen.status_code == 200
    regen_data = resp_regen.json()
    assert regen_data["cached"] is False
    assert regen_data["id"] != post_data["id"]


@pytest.mark.asyncio
async def test_api_provider_refusal_returns_502(
    async_client: AsyncClient,
    test_db_session: AsyncSession,
    api_test_data: tuple[AnalysisRun, QualityIssue],
):
    """Verify that an AI provider refusal returns HTTP 502 Bad Gateway."""
    run, _ = api_test_data

    # Create a fresh issue that does not have a cached explanation
    fresh_issue = QualityIssue(
        id=uuid.uuid4(),
        analysis_run_id=run.id,
        dataset_version_id=run.dataset_version_id,
        module="outlier_analyzer",
        analyzer_version="1.0.0",
        category="OUTLIER",
        severity="HIGH",
        column_name="extreme_col",
        title="Outliers in extreme_col",
        description="Extreme values found",
        evidence={"count": 5},
    )
    test_db_session.add(fresh_issue)
    await test_db_session.commit()

    # Override provider dependency on the active client application instance
    target_app = getattr(async_client._transport, "app", app)
    refusal_provider = MockLLMProvider(simulate_refusal="Content policy violation")
    target_app.dependency_overrides[get_llm_provider] = lambda: refusal_provider

    try:
        resp = await async_client.post(f"/api/v1/analyses/{run.id}/issues/{fresh_issue.id}/explain")
        assert resp.status_code == 502
        assert "Content policy violation" in resp.json()["detail"]
    finally:
        target_app.dependency_overrides.pop(get_llm_provider, None)

