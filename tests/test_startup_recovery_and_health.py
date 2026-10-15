"""Tests for background job startup recovery, liveness probe, and deep readiness probe."""

import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_storage_service
from app.core.config import Settings, get_settings
from app.main import create_application
from app.models.analysis import AnalysisRun, AnalysisStatus
from app.models.dataset import Dataset, DatasetVersion
from app.models.remediation import RemediationExecution, RemediationExecutionStatus
from app.models.user import User
from app.services.analysis_service import AnalysisService
from app.services.file_storage import FileStorageService


@pytest.mark.asyncio
async def test_startup_recovery_marks_interrupted_runs_failed(
    test_db_session: AsyncSession,
    default_test_user: User,
) -> None:
    """Verify that jobs left in PENDING or RUNNING during process termination are marked FAILED on startup."""
    # Setup dataset & version
    ds = Dataset(id=uuid.uuid4(), name="Recovery Test Dataset", owner_id=default_test_user.id)
    test_db_session.add(ds)
    await test_db_session.flush()

    ver = DatasetVersion(
        id=uuid.uuid4(),
        dataset_id=ds.id,
        version_number=1,
        file_name="test.csv",
        storage_path="datasets/dummy/data.parquet",
        file_size_bytes=100,
        sha256_hash="dummy_hash",
        row_count=10,
        column_count=2,
        raw_schema={"columns": []},
    )
    test_db_session.add(ver)

    # 1. Orphaned RUNNING analysis run
    run_running = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=ver.id,
        status=AnalysisStatus.RUNNING.value,
        engine_version="1.0.0",
        analyzer_versions={},
    )
    # 2. Orphaned PENDING analysis run
    run_pending = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=ver.id,
        status=AnalysisStatus.PENDING.value,
        engine_version="1.0.0",
        analyzer_versions={},
    )
    # 3. Already COMPLETED analysis run (should NOT be modified)
    run_completed = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=ver.id,
        status=AnalysisStatus.COMPLETED.value,
        engine_version="1.0.0",
        analyzer_versions={},
    )

    test_db_session.add_all([run_running, run_pending, run_completed])
    await test_db_session.commit()

    # Execute recovery routine
    svc = AnalysisService()
    recovered = await svc.recover_interrupted_jobs(test_db_session)
    assert recovered == 2

    # Refresh entities
    await test_db_session.refresh(run_running)
    await test_db_session.refresh(run_pending)
    await test_db_session.refresh(run_completed)

    assert run_running.status == AnalysisStatus.FAILED.value
    assert "interrupted by server restart" in run_running.error_message
    assert run_running.completed_at is not None

    assert run_pending.status == AnalysisStatus.FAILED.value
    assert "interrupted by server restart" in run_pending.error_message

    assert run_completed.status == AnalysisStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_health_and_readiness_probes(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
) -> None:
    """Verify lightweight /health liveness probe and deep /ready readiness probe."""
    app = create_application()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Liveness probe
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json() == {"status": "ok"}

        # 2. Root readiness probe
        ready_resp = await client.get("/ready")
        assert ready_resp.status_code == 200
        ready_data = ready_resp.json()
        assert ready_data["status"] == "ready"
        assert ready_data["checks"]["database"] == "connected"
        assert ready_data["checks"]["storage"] == "available"

        # 3. API v1 readiness probe
        v1_ready_resp = await client.get("/api/v1/ready")
        assert v1_ready_resp.status_code == 200
        assert v1_ready_resp.json()["status"] == "ready"
