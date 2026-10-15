"""Tests for per-user resource quotas, cumulative storage limits, concurrent analysis caps, and proxy IP spoof prevention."""

import io
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_storage_service
from app.core.config import Settings, get_settings
from app.core.exceptions import QuotaExceededException
from app.core.security import extract_client_ip
from app.main import create_application
from app.models.analysis import AnalysisRun, AnalysisStatus
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.services.file_storage import FileStorageService
from app.services.quota_service import QuotaService, get_quota_service


@pytest.mark.asyncio
async def test_dataset_count_quota_enforcement(
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    default_test_user: User,
    tmp_path,
) -> None:
    """Verify that uploading exceeds dataset count quota when limit is reached."""
    # Configure custom quota settings: max 2 datasets
    custom_settings = Settings(
        environment="testing",
        database_url="sqlite+aiosqlite:///:memory:",
        upload_dir=tmp_path,
        max_datasets_per_user=2,
        max_cumulative_storage_mb_per_user=100,
    )

    app = create_application()
    app.dependency_overrides[get_settings] = lambda: custom_settings
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage
    app.dependency_overrides[get_current_user] = lambda: default_test_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Upload 1
        r1 = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("file1.csv", b"a,b\n1,2\n", "text/csv")},
            data={"name": "Dataset 1"},
        )
        assert r1.status_code == 201

        # Upload 2
        r2 = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("file2.csv", b"c,d\n3,4\n", "text/csv")},
            data={"name": "Dataset 2"},
        )
        assert r2.status_code == 201

        # Upload 3: exceeds limit of 2
        r3 = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("file3.csv", b"e,f\n5,6\n", "text/csv")},
            data={"name": "Dataset 3"},
        )
        assert r3.status_code == 429
        assert "Dataset quota exceeded" in r3.json()["detail"]


@pytest.mark.asyncio
async def test_cumulative_storage_quota_and_partial_file_cleanup(
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    default_test_user: User,
    tmp_path,
) -> None:
    """Verify that cumulative storage limits reject oversized uploads and clean up temporary files."""
    # Configure custom quota settings: 1 MB cumulative limit
    custom_settings = Settings(
        environment="testing",
        database_url="sqlite+aiosqlite:///:memory:",
        upload_dir=tmp_path,
        max_datasets_per_user=10,
        max_cumulative_storage_mb_per_user=1,  # 1 MB limit
    )

    app = create_application()
    app.dependency_overrides[get_settings] = lambda: custom_settings
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage
    app.dependency_overrides[get_current_user] = lambda: default_test_user

    # Generate a payload > 1 MB (e.g. 1.2 MB)
    large_csv = b"col1,col2\n" + (b"val1,val2\n" * 120000)
    assert len(large_csv) > 1024 * 1024

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("large_quota.csv", large_csv, "text/csv")},
            data={"name": "Oversized Storage"},
        )
        assert resp.status_code == 429
        assert "Cumulative storage quota exceeded" in resp.json()["detail"]

        # Ensure no orphaned files remain in storage directory
        dataset_files = list(tmp_path.rglob("large_quota.csv"))
        assert len(dataset_files) == 0


@pytest.mark.asyncio
async def test_concurrent_analysis_quota_enforcement(
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    default_test_user: User,
    tmp_path,
) -> None:
    """Verify that triggering an analysis fails when active concurrent analysis cap is reached."""
    custom_settings = Settings(
        environment="testing",
        database_url="sqlite+aiosqlite:///:memory:",
        upload_dir=tmp_path,
        max_concurrent_analysis_jobs_per_user=1,  # Max 1 active job
    )

    app = create_application()
    app.dependency_overrides[get_settings] = lambda: custom_settings
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage
    app.dependency_overrides[get_current_user] = lambda: default_test_user

    # Create dataset and version
    ds = Dataset(id=uuid.uuid4(), name="Test Dataset", owner_id=default_test_user.id)
    test_db_session.add(ds)
    await test_db_session.flush()

    ver = DatasetVersion(
        id=uuid.uuid4(),
        dataset_id=ds.id,
        version_number=1,
        file_name="test.csv",
        storage_path="datasets/dummy/data.parquet",
        file_size_bytes=100,
        sha256_hash="hash1",
        row_count=10,
        column_count=2,
        raw_schema={"columns": []},
    )
    test_db_session.add(ver)

    # Insert an existing RUNNING analysis run for this user
    active_run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=ver.id,
        status=AnalysisStatus.RUNNING.value,
        engine_version="1.0.0",
        analyzer_versions={},
    )
    test_db_session.add(active_run)
    await test_db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Attempt to trigger a second analysis
        resp = await client.post(
            f"/api/v1/datasets/{ds.id}/versions/{ver.id}/analyze",
            json={"target_column": None, "problem_type": None},
        )
        assert resp.status_code == 429
        assert "Concurrent analysis job limit reached" in resp.json()["detail"]


def test_trusted_proxy_ip_extraction_prevents_spoofing():
    """Verify extract_client_ip ignores X-Forwarded-For when the immediate caller is not a trusted proxy."""
    class DummyClient:
        def __init__(self, host):
            self.host = host

    class DummyRequest:
        def __init__(self, host, headers):
            self.client = DummyClient(host)
            self.headers = headers

    trusted_proxies = ["127.0.0.1", "10.0.0.1"]

    # 1. Untrusted caller trying to spoof IP via X-Forwarded-For
    untrusted_req = DummyRequest(
        host="203.0.113.50",
        headers={"X-Forwarded-For": "198.51.100.1"},
    )
    assert extract_client_ip(untrusted_req, trusted_proxies) == "203.0.113.50"

    # 2. Trusted proxy caller forwards the real client IP
    trusted_req = DummyRequest(
        host="127.0.0.1",
        headers={"X-Forwarded-For": "198.51.100.1, 10.0.0.1"},
    )
    assert extract_client_ip(trusted_req, trusted_proxies) == "198.51.100.1"
