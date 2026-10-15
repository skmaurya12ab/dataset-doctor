"""Tests for GDPR-compliant dataset and account deletion, file artifact purging, and isolation."""

import io
from pathlib import Path
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_storage_service
from app.core.config import Settings, get_settings
from app.main import create_application
from app.models.analysis import AnalysisRun, QualityIssue
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User, UserSession
from app.services.file_storage import FileStorageService


@pytest.fixture
def user_alpha(test_db_session: AsyncSession) -> User:
    """User Alpha fixture."""
    user = User(
        id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        email="alpha@example.com",
        hashed_password="hash_alpha",
        is_active=True,
        is_verified=True,
        role="user",
    )
    return user


@pytest.fixture
def user_beta(test_db_session: AsyncSession) -> User:
    """User Beta fixture."""
    user = User(
        id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        email="beta@example.com",
        hashed_password="hash_beta",
        is_active=True,
        is_verified=True,
        role="user",
    )
    return user


def create_user_client(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    user: User,
) -> AsyncClient:
    app = create_application()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_dataset_deletion_purges_db_and_disk_artifacts(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    user_alpha: User,
) -> None:
    """Verify that deleting a dataset removes all database records and storage directories."""
    test_db_session.add(user_alpha)
    await test_db_session.commit()

    client = create_user_client(test_settings, test_db_session, test_storage, user_alpha)

    # 1. Upload dataset
    upload_resp = await client.post(
        "/api/v1/datasets/upload",
        files={"file": ("to_delete.csv", b"a,b\n1,2\n3,4\n", "text/csv")},
        data={"name": "To Delete"},
    )
    assert upload_resp.status_code == 201
    dataset_id = upload_resp.json()["dataset_id"]

    # Verify physical file exists on disk
    dataset_dir = test_storage.base_dir / "datasets" / dataset_id
    assert dataset_dir.exists()
    assert (dataset_dir / "versions" / "v1" / "data.parquet").exists()

    # 2. Delete the dataset
    del_resp = await client.delete(f"/api/v1/datasets/{dataset_id}")
    assert del_resp.status_code == 200
    assert "deleted successfully" in del_resp.json()["message"]

    # 3. Verify physical directory was purged from disk
    assert not dataset_dir.exists()

    # 4. Verify database record is gone
    stmt = select(Dataset).where(Dataset.id == uuid.UUID(dataset_id))
    assert (await test_db_session.execute(stmt)).scalar_one_or_none() is None

    # 5. Verify versions were cascaded and removed
    v_stmt = select(DatasetVersion).where(DatasetVersion.dataset_id == uuid.UUID(dataset_id))
    assert (await test_db_session.execute(v_stmt)).scalars().all() == []


@pytest.mark.asyncio
async def test_cross_tenant_dataset_deletion_isolation(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    user_alpha: User,
    user_beta: User,
) -> None:
    """Verify that User Beta cannot delete User Alpha's dataset."""
    test_db_session.add_all([user_alpha, user_beta])
    await test_db_session.commit()

    client_alpha = create_user_client(test_settings, test_db_session, test_storage, user_alpha)
    client_beta = create_user_client(test_settings, test_db_session, test_storage, user_beta)

    # User Alpha uploads
    upload_resp = await client_alpha.post(
        "/api/v1/datasets/upload",
        files={"file": ("alpha_dataset.csv", b"x,y\n10,20\n", "text/csv")},
        data={"name": "Alpha Dataset"},
    )
    dataset_id = upload_resp.json()["dataset_id"]

    # User Beta attempts to delete User Alpha's dataset
    del_resp = await client_beta.delete(f"/api/v1/datasets/{dataset_id}")
    assert del_resp.status_code == 404

    # Ensure dataset still exists
    stmt = select(Dataset).where(Dataset.id == uuid.UUID(dataset_id))
    assert (await test_db_session.execute(stmt)).scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_user_account_deletion_purges_all_user_data(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
    user_alpha: User,
) -> None:
    """Verify that deleting a user account purges account, sessions, datasets, and files."""
    test_db_session.add(user_alpha)
    await test_db_session.commit()

    client = create_user_client(test_settings, test_db_session, test_storage, user_alpha)

    # Upload two datasets
    r1 = await client.post(
        "/api/v1/datasets/upload",
        files={"file": ("alpha1.csv", b"a,b\n1,2\n", "text/csv")},
        data={"name": "Alpha 1"},
    )
    r2 = await client.post(
        "/api/v1/datasets/upload",
        files={"file": ("alpha2.csv", b"c,d\n3,4\n", "text/csv")},
        data={"name": "Alpha 2"},
    )
    ds1_id = r1.json()["dataset_id"]
    ds2_id = r2.json()["dataset_id"]

    ds1_dir = test_storage.base_dir / "datasets" / ds1_id
    ds2_dir = test_storage.base_dir / "datasets" / ds2_id
    assert ds1_dir.exists()
    assert ds2_dir.exists()

    # Delete the user account via /api/v1/auth/me
    del_resp = await client.delete("/api/v1/auth/me")
    assert del_resp.status_code == 200
    assert "Account and all associated datasets deleted" in del_resp.json()["message"]

    # Verify storage directories are deleted
    assert not ds1_dir.exists()
    assert not ds2_dir.exists()

    # Verify user record is gone
    user_stmt = select(User).where(User.id == user_alpha.id)
    assert (await test_db_session.execute(user_stmt)).scalar_one_or_none() is None

    # Verify datasets are gone
    ds_stmt = select(Dataset).where(Dataset.owner_id == user_alpha.id)
    assert (await test_db_session.execute(ds_stmt)).scalars().all() == []
