"""End-to-end multi-user data isolation and authorization tests."""

import io
from pathlib import Path
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_storage_service
from app.core.config import Settings, get_settings
from app.main import create_application
from app.models.analysis import AnalysisRun, AnalysisStatus, QualityIssue
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.services.file_storage import FileStorageService


@pytest.fixture
async def user_a(test_db_session: AsyncSession) -> User:
    """User A entity."""
    user = User(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        email="usera@example.com",
        hashed_password="hashed_a",
        is_active=True,
        is_verified=True,
        role="user",
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    return user


@pytest.fixture
async def user_b(test_db_session: AsyncSession) -> User:
    """User B entity."""
    user = User(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        email="userb@example.com",
        hashed_password="hashed_b",
        is_active=True,
        is_verified=True,
        role="user",
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    return user


def create_user_client(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    user: User,
) -> AsyncClient:
    """Create an authenticated AsyncClient for a specific User with isolated dependency overrides."""
    app = create_application()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_cross_user_dataset_isolation(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    user_a: User,
    user_b: User,
) -> None:
    """Verify that User B cannot list, view, or preview User A's datasets."""
    client_a = create_user_client(test_settings, test_db_session, test_storage, user_a)
    client_b = create_user_client(test_settings, test_db_session, test_storage, user_b)

    # 1. User A uploads a dataset
    csv_content = b"col_a,col_b,target\n1,2,0\n3,4,1\n5,6,0\n"
    upload_resp = await client_a.post(
        "/api/v1/datasets/upload",
        files={"file": ("usera_data.csv", csv_content, "text/csv")},
        data={"name": "User A Private Dataset"},
    )
    assert upload_resp.status_code == 201
    dataset_a_id = upload_resp.json()["dataset_id"]
    version_a_id = upload_resp.json()["version_id"]

    # 2. User A can list and view their dataset
    list_a = await client_a.get("/api/v1/datasets")
    assert list_a.status_code == 200
    assert any(d["dataset_id"] == dataset_a_id for d in list_a.json())

    detail_a = await client_a.get(f"/api/v1/datasets/{dataset_a_id}")
    assert detail_a.status_code == 200

    preview_a = await client_a.get(f"/api/v1/datasets/{dataset_a_id}/versions/1/preview")
    assert preview_a.status_code == 200

    # 3. User B lists datasets -> must NOT see User A's dataset
    list_b = await client_b.get("/api/v1/datasets")
    assert list_b.status_code == 200
    assert not any(d["dataset_id"] == dataset_a_id for d in list_b.json())

    # 4. User B attempts direct lookup of User A's dataset -> 404 (non-disclosing)
    detail_b = await client_b.get(f"/api/v1/datasets/{dataset_a_id}")
    assert detail_b.status_code == 404

    # 5. User B attempts preview of User A's dataset -> 404
    preview_b = await client_b.get(f"/api/v1/datasets/{dataset_a_id}/versions/1/preview")
    assert preview_b.status_code == 404

    # 6. User B attempts to upload a new version to User A's dataset -> 404
    upload_b_to_a = await client_b.post(
        "/api/v1/datasets/upload",
        files={"file": ("attacker.csv", csv_content, "text/csv")},
        data={"dataset_id": dataset_a_id},
    )
    assert upload_b_to_a.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_analysis_and_remediation_isolation(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    user_a: User,
    user_b: User,
) -> None:
    """Verify that User B cannot access or trigger analysis, findings, AI plans, or remediations on User A's data."""
    client_a = create_user_client(test_settings, test_db_session, test_storage, user_a)
    client_b = create_user_client(test_settings, test_db_session, test_storage, user_b)

    # 1. User A uploads dataset
    csv_content = b"x,y,target\n1,10,0\n2,20,1\n3,30,0\n"
    upload_resp = await client_a.post(
        "/api/v1/datasets/upload",
        files={"file": ("dataset_for_analysis.csv", csv_content, "text/csv")},
        data={"name": "Analysis Isolation Dataset"},
    )
    assert upload_resp.status_code == 201
    dataset_id = upload_resp.json()["dataset_id"]
    version_id = upload_resp.json()["version_id"]

    # 2. User B tries to trigger analysis on User A's version -> 404
    trig_b = await client_b.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/analyze",
        json={"target_column": "target"},
    )
    assert trig_b.status_code == 404

    # 3. User A triggers analysis
    trig_a = await client_a.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/analyze",
        json={"target_column": "target"},
    )
    assert trig_a.status_code == 202
    run_id = trig_a.json()["analysis_run_id"]

    # Seed analysis run as COMPLETED with a quality issue
    run_record = await test_db_session.get(AnalysisRun, uuid.UUID(run_id))
    run_record.status = AnalysisStatus.COMPLETED.value
    run_record.ml_readiness_score = 80.0

    issue = QualityIssue(
        analysis_run_id=run_record.id,
        dataset_version_id=uuid.UUID(version_id),
        module="missing_analyzer",
        analyzer_version="1.0.0",
        parameters_used={},
        category="MISSING_VALUES",
        severity="MEDIUM",
        column_name="y",
        title="Missing values detected",
        description="Detailed private finding",
        evidence={"count": 0},
    )
    test_db_session.add(issue)
    await test_db_session.commit()
    await test_db_session.refresh(issue)

    # 4. User A can view run details and issues
    assert (await client_a.get(f"/api/v1/analyses/{run_id}")).status_code == 200
    assert (await client_a.get(f"/api/v1/analyses/{run_id}/issues")).status_code == 200
    assert (await client_a.get(f"/api/v1/analyses/{run_id}/visualizations")).status_code == 200

    # 5. User B CANNOT view run details, issues, or visualizations -> 404
    assert (await client_b.get(f"/api/v1/analyses/{run_id}")).status_code == 404
    assert (await client_b.get(f"/api/v1/analyses/{run_id}/issues")).status_code == 404
    assert (await client_b.get(f"/api/v1/analyses/{run_id}/visualizations")).status_code == 404

    # 6. User B cannot call AI explain or generate AI plan -> 404
    assert (await client_b.post(f"/api/v1/analyses/{run_id}/issues/{issue.id}/explain")).status_code == 404
    assert (await client_b.post(f"/api/v1/analyses/{run_id}/generate-ai-plan")).status_code == 404
    assert (await client_b.get(f"/api/v1/analyses/{run_id}/ai-plan")).status_code == 404

    # 7. User B cannot apply remediation or list dataset remediations -> 404
    assert (
        await client_b.post(
            f"/api/v1/analyses/{run_id}/remediations/apply",
            json={"ai_report_id": str(uuid.uuid4()), "approval": True},
        )
    ).status_code == 404
    assert (await client_b.get(f"/api/v1/datasets/{dataset_id}/remediations")).status_code == 404
    assert (
        await client_b.get(
            f"/api/v1/datasets/{dataset_id}/compare-versions?v1={version_id}&v2={version_id}"
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_legacy_unowned_datasets_inaccessible(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    user_a: User,
) -> None:
    """Verify that unowned/legacy datasets are completely hidden from regular users."""
    client = create_user_client(test_settings, test_db_session, test_storage, user_a)

    # Insert a legacy dataset with owner_id = None
    legacy_ds = Dataset(
        id=uuid.uuid4(),
        name="Legacy Unowned Dataset",
        owner_id=None,
    )
    test_db_session.add(legacy_ds)
    await test_db_session.commit()

    # User A listing must NOT include legacy unowned dataset
    list_resp = await client.get("/api/v1/datasets")
    assert list_resp.status_code == 200
    assert not any(d["dataset_id"] == str(legacy_ds.id) for d in list_resp.json())

    # User A direct access to legacy unowned dataset -> 404
    detail_resp = await client.get(f"/api/v1/datasets/{legacy_ds.id}")
    assert detail_resp.status_code == 404


@pytest.mark.asyncio
async def test_overview_stats_isolated_per_user(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    user_a: User,
    user_b: User,
) -> None:
    """Verify overview statistics are strictly scoped to the requesting user."""
    client_a = create_user_client(test_settings, test_db_session, test_storage, user_a)
    client_b = create_user_client(test_settings, test_db_session, test_storage, user_b)

    # Initial stats for both: 0 datasets
    stats_b_initial = (await client_b.get("/api/v1/overview/stats")).json()
    assert stats_b_initial["total_datasets"] == 0

    # User A uploads 1 dataset
    csv_bytes = b"a,b\n1,2\n"
    await client_a.post(
        "/api/v1/datasets/upload",
        files={"file": ("data_a.csv", csv_bytes, "text/csv")},
        data={"name": "Dataset For Stats"},
    )

    # User A overview stats shows 1 dataset
    stats_a = (await client_a.get("/api/v1/overview/stats")).json()
    assert stats_a["total_datasets"] == 1

    # User B overview stats STILL shows 0 datasets
    stats_b = (await client_b.get("/api/v1/overview/stats")).json()
    assert stats_b["total_datasets"] == 0
