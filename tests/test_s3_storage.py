"""Isolated unit and integration tests for S3-compatible persistent object storage."""

import hashlib
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncGenerator
import uuid
import boto3
from moto import mock_aws
import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.exceptions import EntityNotFoundException, OversizedFileException, StorageException
from app.models import Base
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.services.account_service import AccountService
from app.services.analysis_service import AnalysisService
from app.services.file_storage import (
    BaseStorageBackend,
    FileStorageService,
    LocalStorageBackend,
    S3StorageBackend,
)


@pytest.fixture
def mock_s3_env():
    """Moto S3 test harness providing an isolated test bucket."""
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        bucket_name = "test-dataset-doctor-bucket"
        client.create_bucket(Bucket=bucket_name)
        yield {
            "client": client,
            "bucket_name": bucket_name,
            "endpoint_url": "https://s3.us-east-1.amazonaws.com",
            "region": "us-east-1",
            "access_key": "mock-access-key",
            "secret_key": "mock-secret-key",
        }


@pytest.fixture
def s3_backend(mock_s3_env) -> S3StorageBackend:
    """S3StorageBackend instance backed by Moto."""
    return S3StorageBackend(
        endpoint_url=mock_s3_env["endpoint_url"],
        bucket_name=mock_s3_env["bucket_name"],
        access_key=mock_s3_env["access_key"],
        secret_key=mock_s3_env["secret_key"],
        region_name=mock_s3_env["region"],
        s3_client=mock_s3_env["client"],
    )


@pytest.fixture
def s3_storage_service(tmp_path: Path, s3_backend: S3StorageBackend) -> FileStorageService:
    """FileStorageService configured with Moto S3 backend and temporary staging directory."""
    return FileStorageService(base_dir=tmp_path / "staging", backend=s3_backend)


@pytest.fixture
async def s3_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides isolated in-memory SQLite session for S3 integration tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ==============================================================================
# 1. Configuration Validation Tests
# ==============================================================================


def test_storage_configuration_local_valid():
    """Verify local storage mode is valid by default without any S3 environment variables."""
    s = Settings(storage_backend="local")
    s.validate_storage_configuration()
    assert s.storage_backend == "local"
    assert s.is_s3_storage is False


def test_storage_configuration_s3_missing_fields_raises_clear_error():
    """Verify S3 mode fails clearly at startup when required S3 variables are missing."""
    s = Settings(storage_backend="s3")
    with pytest.raises(ValueError) as exc_info:
        s.validate_storage_configuration()

    err = str(exc_info.value)
    assert "S3_ENDPOINT_URL" in err
    assert "S3_BUCKET_NAME" in err
    assert "S3_ACCESS_KEY" in err
    assert "S3_SECRET_KEY" in err
    # Ensure no credentials/secrets are leaked in the error
    assert "mock-secret-key" not in err


def test_storage_configuration_s3_complete_valid():
    """Verify S3 mode passes validation when all required options are present."""
    s = Settings(
        storage_backend="s3",
        s3_endpoint_url="https://s3.us-west-004.backblazeb2.com",
        s3_bucket_name="my-dataset-bucket",
        s3_access_key="b2_key_id_123",
        s3_secret_key="b2_app_key_456",
        s3_region="us-west-004",
    )
    s.validate_storage_configuration()
    assert s.is_s3_storage is True
    assert s.s3_endpoint_url == "https://s3.us-west-004.backblazeb2.com"


def test_production_trusted_proxies_rejects_wildcard():
    """Verify that wildcard or 0.0.0.0/0 trusted proxy is rejected in production."""
    s = Settings(
        environment="production",
        trusted_proxies="0.0.0.0/0",
    )
    with pytest.raises(ValueError) as exc_info:
        _ = s.parsed_trusted_proxies

    assert "all-address and unspecified networks are forbidden" in str(exc_info.value)


# ==============================================================================
# 2. S3 Backend Core Operations Tests
# ==============================================================================


def test_s3_backend_key_construction_and_save_file(
    s3_backend: S3StorageBackend,
    tmp_path: Path,
):
    """Verify key normalization, file upload, existence, and size query."""
    source_file = tmp_path / "sample.csv"
    content = b"col1,col2\nval1,val2\n"
    source_file.write_bytes(content)

    rel_key = "datasets/11111111-1111-1111-1111-111111111111/versions/v1/original/sample.csv"
    size = s3_backend.save_file(rel_key, source_file)
    assert size == len(content)

    assert s3_backend.exists(rel_key) is True
    assert s3_backend.get_size(rel_key) == len(content)
    assert s3_backend.exists("nonexistent/key.parquet") is False


def test_s3_backend_materialize_file(
    s3_backend: S3StorageBackend,
    tmp_path: Path,
):
    """Verify downloading object from S3 to an isolated local file."""
    source_file = tmp_path / "source.parquet"
    source_file.write_bytes(b"PAR1_test_bytes")
    rel_key = "datasets/test/data.parquet"
    s3_backend.save_file(rel_key, source_file)

    target_local = tmp_path / "downloaded" / "target.parquet"
    out = s3_backend.materialize_file(rel_key, target_local)

    assert out.exists()
    assert out.read_bytes() == b"PAR1_test_bytes"


def test_s3_backend_missing_object_behavior(s3_backend: S3StorageBackend, tmp_path: Path):
    """Verify attempting to materialize missing object raises StorageException."""
    target = tmp_path / "missing.parquet"
    with pytest.raises(StorageException) as exc_info:
        s3_backend.materialize_file("datasets/does_not_exist/data.parquet", target)

    assert "S3 object not found" in str(exc_info.value)
    assert not target.exists()


def test_s3_backend_delete_file_and_prefix(s3_backend: S3StorageBackend, tmp_path: Path):
    """Verify single-file deletion and prefix batch deletion in S3."""
    f1 = tmp_path / "f1.txt"
    f2 = tmp_path / "f2.txt"
    f3 = tmp_path / "f3.txt"
    f1.write_bytes(b"1")
    f2.write_bytes(b"2")
    f3.write_bytes(b"3")

    s3_backend.save_file("datasets/ds_a/versions/v1/data.parquet", f1)
    s3_backend.save_file("datasets/ds_a/versions/v2/data.parquet", f2)
    s3_backend.save_file("datasets/ds_b/versions/v1/data.parquet", f3)

    # Delete single file
    assert s3_backend.delete_file("datasets/ds_a/versions/v1/data.parquet") is True
    assert s3_backend.exists("datasets/ds_a/versions/v1/data.parquet") is False
    assert s3_backend.exists("datasets/ds_a/versions/v2/data.parquet") is True

    # Delete prefix for ds_a
    deleted_count = s3_backend.delete_prefix("datasets/ds_a/")
    assert deleted_count == 1
    assert s3_backend.exists("datasets/ds_a/versions/v2/data.parquet") is False
    # ds_b must remain untouched
    assert s3_backend.exists("datasets/ds_b/versions/v1/data.parquet") is True


def test_s3_backend_health_check_repeated_calls_are_read_only(
    s3_backend: S3StorageBackend,
    monkeypatch: pytest.MonkeyPatch,
):
    """Repeated readiness checks list one dataset key and never mutate S3 objects."""
    calls = {"list": 0, "put": 0, "delete": 0}
    list_objects = s3_backend.client.list_objects_v2

    def counted_list(**kwargs):
        calls["list"] += 1
        assert kwargs["Prefix"] == "datasets/"
        assert kwargs["MaxKeys"] == 1
        return list_objects(**kwargs)

    def counted_put(**kwargs):
        calls["put"] += 1

    def counted_delete(**kwargs):
        calls["delete"] += 1

    monkeypatch.setattr(s3_backend.client, "list_objects_v2", counted_list)
    monkeypatch.setattr(s3_backend.client, "put_object", counted_put)
    monkeypatch.setattr(s3_backend.client, "delete_object", counted_delete)

    assert all(s3_backend.check_health() for _ in range(5))
    assert calls == {"list": 5, "put": 0, "delete": 0}


def test_s3_backend_health_check_concurrent_calls_are_read_only(
    s3_backend: S3StorageBackend,
    monkeypatch: pytest.MonkeyPatch,
):
    """Concurrent readiness checks use independent read-only listing requests."""
    calls = {"list": 0, "put": 0, "delete": 0}
    calls_lock = threading.Lock()
    concurrent_calls = threading.Barrier(4, timeout=5)

    def counted_list(**kwargs):
        with calls_lock:
            calls["list"] += 1
        assert kwargs["Bucket"] == s3_backend.bucket_name
        assert kwargs["Prefix"] == "datasets/"
        assert kwargs["MaxKeys"] == 1
        concurrent_calls.wait()
        return {"KeyCount": 0}

    def counted_put(**kwargs):
        with calls_lock:
            calls["put"] += 1

    def counted_delete(**kwargs):
        with calls_lock:
            calls["delete"] += 1

    monkeypatch.setattr(s3_backend.client, "list_objects_v2", counted_list)
    monkeypatch.setattr(s3_backend.client, "put_object", counted_put)
    monkeypatch.setattr(s3_backend.client, "delete_object", counted_delete)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: s3_backend.check_health(), range(4)))
    assert results == [True] * 4
    assert calls == {"list": 4, "put": 0, "delete": 0}


def test_s3_backend_health_check_fails_when_listing_is_denied(
    s3_backend: S3StorageBackend,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    from botocore.exceptions import ClientError

    def deny_listing(**kwargs):
        raise ClientError(
            {
                "Error": {"Code": "AccessDenied", "Message": "provider detail mock-secret-key"},
                "ResponseMetadata": {"HTTPStatusCode": 403},
            },
            "ListObjectsV2",
        )

    monkeypatch.setattr(s3_backend.client, "list_objects_v2", deny_listing)
    assert s3_backend.check_health() is False
    assert "mock-secret-key" not in caplog.text


# ==============================================================================
# 3. FileStorageService with S3 Integration Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_save_uploaded_stream_persists_to_s3_and_verifies_hash(
    s3_storage_service: FileStorageService,
    s3_backend: S3StorageBackend,
):
    """Verify streaming upload computes SHA-256 and persists both locally and in S3."""
    dataset_id = uuid.uuid4()
    content = b"feature_a,feature_b\n1.5,2.5\n3.5,4.5\n"
    stream = io.BytesIO(content)

    saved_path, sha_hash, size = await s3_storage_service.save_uploaded_stream(
        dataset_id=dataset_id,
        version_number=1,
        filename="train_data.csv",
        file_stream=stream,
    )

    assert saved_path.exists()
    assert size == len(content)
    assert sha_hash == hashlib.sha256(content).hexdigest()

    # Verify S3 persistence under structured key
    expected_key = f"datasets/{dataset_id}/versions/v1/original/train_data.csv"
    assert s3_backend.exists(expected_key) is True
    assert s3_backend.get_size(expected_key) == len(content)


@pytest.mark.asyncio
async def test_save_canonical_parquet_persists_to_s3(
    s3_storage_service: FileStorageService,
    s3_backend: S3StorageBackend,
):
    """Verify DataFrame is saved as canonical Parquet locally and persisted to S3."""
    dataset_id = uuid.uuid4()
    df = pd.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]})

    parquet_path = s3_storage_service.save_canonical_parquet(df, dataset_id, 1)
    assert parquet_path.exists()

    expected_key = f"datasets/{dataset_id}/versions/v1/data.parquet"
    assert s3_backend.exists(expected_key) is True


def test_ephemeral_recovery_materializes_parquet_from_s3(
    s3_storage_service: FileStorageService,
    s3_backend: S3StorageBackend,
):
    """Simulate container restart / ephemeral disk wipe: preview must materialize from S3."""
    dataset_id = uuid.uuid4()
    df = pd.DataFrame({"id": range(1, 26), "val": [f"item_{i}" for i in range(1, 26)]})

    # Save initially
    parquet_path = s3_storage_service.save_canonical_parquet(df, dataset_id, 1)
    assert parquet_path.exists()

    # Simulate ephemeral container restart: wipe local staging directory completely
    import shutil
    shutil.rmtree(s3_storage_service.base_dir)
    assert not parquet_path.exists()

    # Calling read_preview must transparently re-materialize from S3
    preview_df, total_rows, total_cols = s3_storage_service.read_preview(
        dataset_id=dataset_id,
        version_number=1,
        limit=10,
        offset=0,
    )

    assert total_rows == 25
    assert total_cols == 2
    assert len(preview_df) == 10
    assert parquet_path.exists()  # local cache restored


@pytest.mark.asyncio
async def test_partial_upload_cleanup_on_error(
    s3_storage_service: FileStorageService,
    s3_backend: S3StorageBackend,
):
    """Verify that if an upload exceeds quota or errors out, temporary files and S3 objects are cleaned up."""
    dataset_id = uuid.uuid4()
    s3_storage_service.max_bytes = 50
    oversized = b"A" * 100
    stream = io.BytesIO(oversized)

    with pytest.raises(OversizedFileException):
        await s3_storage_service.save_uploaded_stream(
            dataset_id=dataset_id,
            version_number=1,
            filename="large.csv",
            file_stream=stream,
        )

    expected_key = f"datasets/{dataset_id}/versions/v1/original/large.csv"
    assert s3_backend.exists(expected_key) is False


# ==============================================================================
# 4. End-to-End Workflows & Tenant Isolation in S3 Mode
# ==============================================================================


@pytest.mark.asyncio
async def test_tenant_isolated_dataset_deletion(
    s3_storage_service: FileStorageService,
    s3_backend: S3StorageBackend,
    s3_db_session: AsyncSession,
):
    """Verify deleting a dataset removes only its S3 objects and leaves other datasets untouched."""
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()
    ds1_id = uuid.uuid4()
    ds2_id = uuid.uuid4()

    # Create dummy Parquet files for ds1 and ds2
    df = pd.DataFrame({"a": [1, 2]})
    s3_storage_service.save_canonical_parquet(df, ds1_id, 1)
    s3_storage_service.save_canonical_parquet(df, ds2_id, 1)

    key_ds1 = f"datasets/{ds1_id}/versions/v1/data.parquet"
    key_ds2 = f"datasets/{ds2_id}/versions/v1/data.parquet"
    assert s3_backend.exists(key_ds1) is True
    assert s3_backend.exists(key_ds2) is True

    # Record in database
    ds1 = Dataset(id=ds1_id, name="DS1", owner_id=user1_id)
    ds2 = Dataset(id=ds2_id, name="DS2", owner_id=user2_id)
    s3_db_session.add_all([ds1, ds2])
    await s3_db_session.commit()

    # Delete ds1 using AccountService
    account_svc = AccountService()
    await account_svc.delete_dataset(
        db=s3_db_session,
        storage=s3_storage_service,
        dataset_id=ds1_id,
        user_id=user1_id,
    )

    # ds1 objects must be gone from S3
    assert s3_backend.exists(key_ds1) is False
    # ds2 objects must remain completely intact
    assert s3_backend.exists(key_ds2) is True


@pytest.mark.asyncio
async def test_user_account_deletion_cleans_all_owned_s3_datasets(
    s3_storage_service: FileStorageService,
    s3_backend: S3StorageBackend,
    s3_db_session: AsyncSession,
):
    """Verify deleting a user account purges all of that user's datasets from S3 without collateral damage."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    user_a = User(
        id=user_a_id,
        email="usera@example.com",
        hashed_password="pw",
        is_active=True,
        is_verified=True,
    )
    user_b = User(
        id=user_b_id,
        email="userb@example.com",
        hashed_password="pw",
        is_active=True,
        is_verified=True,
    )
    s3_db_session.add_all([user_a, user_b])

    ds_a1 = uuid.uuid4()
    ds_a2 = uuid.uuid4()
    ds_b1 = uuid.uuid4()

    df = pd.DataFrame({"x": [10]})
    s3_storage_service.save_canonical_parquet(df, ds_a1, 1)
    s3_storage_service.save_canonical_parquet(df, ds_a2, 1)
    s3_storage_service.save_canonical_parquet(df, ds_b1, 1)

    s3_db_session.add(Dataset(id=ds_a1, name="A1", owner_id=user_a_id))
    s3_db_session.add(Dataset(id=ds_a2, name="A2", owner_id=user_a_id))
    s3_db_session.add(Dataset(id=ds_b1, name="B1", owner_id=user_b_id))
    await s3_db_session.commit()

    # Delete User A
    account_svc = AccountService()
    await account_svc.delete_user_account(
        db=s3_db_session,
        storage=s3_storage_service,
        user_id=user_a_id,
    )

    # All of User A's datasets must be removed from S3
    assert s3_backend.exists(f"datasets/{ds_a1}/versions/v1/data.parquet") is False
    assert s3_backend.exists(f"datasets/{ds_a2}/versions/v1/data.parquet") is False
    # User B's dataset must remain intact
    assert s3_backend.exists(f"datasets/{ds_b1}/versions/v1/data.parquet") is True


@pytest.mark.asyncio
async def test_analysis_and_remediation_workflow_with_s3_backend(
    s3_storage_service: FileStorageService,
    s3_backend: S3StorageBackend,
    s3_db_session: AsyncSession,
):
    """Verify that analysis and remediation workflows persist new versions to S3 correctly."""
    user_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    version_id = uuid.uuid4()

    df_initial = pd.DataFrame({
        "age": [25, None, 45, 120],  # missing value + outlier
        "salary": [50000, 60000, 70000, 80000],
    })

    # Save initial version into S3
    parquet_path = s3_storage_service.save_canonical_parquet(df_initial, dataset_id, 1)
    rel_path = s3_storage_service.get_relative_parquet_key(dataset_id, 1)
    assert s3_backend.exists(rel_path) is True

    ds = Dataset(id=dataset_id, name="Analysis S3 Test", owner_id=user_id)
    v1 = DatasetVersion(
        id=version_id,
        dataset_id=dataset_id,
        version_number=1,
        file_name="initial.parquet",
        storage_path=rel_path,
        file_size_bytes=parquet_path.stat().st_size,
        sha256_hash="dummy_hash_v1",
        row_count=4,
        column_count=2,
        raw_schema={"columns": ["age", "salary"]},
    )
    s3_db_session.add_all([ds, v1])
    await s3_db_session.commit()

    # 1. Wipe local cache to simulate restart
    import shutil
    shutil.rmtree(s3_storage_service.base_dir)

    # 2. Materialization check via ensure_local_parquet
    restored_path = s3_storage_service.ensure_local_parquet(dataset_id, 1)
    assert restored_path.exists()
    restored_df = pd.read_parquet(restored_path)
    assert len(restored_df) == 4

    # 3. Simulate remediation generating version 2
    df_remediated = restored_df.dropna()
    v2_number = 2
    v2_target_path = s3_storage_service.get_parquet_path(dataset_id, v2_number)
    df_remediated.to_parquet(v2_target_path, engine="pyarrow", index=False)

    # Persist remediated file to S3
    saved_rel_key = s3_storage_service.persist_canonical_parquet_file(dataset_id, v2_number, v2_target_path)
    assert saved_rel_key == f"datasets/{dataset_id}/versions/v2/data.parquet"
    assert s3_backend.exists(saved_rel_key) is True
