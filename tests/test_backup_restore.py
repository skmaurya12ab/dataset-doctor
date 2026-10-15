"""Tests for backup verification utility and restore integrity checks."""

import hashlib
from pathlib import Path
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset, DatasetVersion
from scripts.verify_backup import compute_sha256, verify_integrity


@pytest.mark.asyncio
async def test_backup_verification_script_detects_intact_and_corrupt_files(
    test_db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Verify that verify_backup.py confirms intact backups and catches modified/missing Parquet files."""
    db_file = tmp_path / "test_backup.sqlite3"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    storage_dir = tmp_path / "uploads"
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Setup database with a dataset version
    from app.models import Base
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    ds_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    # Create dummy storage files
    v_dir = storage_dir / "datasets" / str(ds_id) / "versions" / "v1"
    orig_dir = v_dir / "original"
    orig_dir.mkdir(parents=True, exist_ok=True)

    test_content = b"sample,tabular,data\n1,2,3\n4,5,6\n"
    orig_file = orig_dir / "test.csv"
    orig_file.write_bytes(test_content)
    file_hash = hashlib.sha256(test_content).hexdigest()

    parquet_file = v_dir / "data.parquet"
    parquet_file.write_bytes(b"PAR1_dummy_parquet_content_bytes")

    # Record in database
    from sqlalchemy.ext.asyncio import async_sessionmaker
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        ds = Dataset(id=ds_id, name="Backup Verification DS")
        session.add(ds)
        ver = DatasetVersion(
            id=ver_id,
            dataset_id=ds_id,
            version_number=1,
            file_name="test.csv",
            storage_path=str(parquet_file.relative_to(storage_dir)),
            file_size_bytes=len(test_content),
            sha256_hash=file_hash,
            row_count=2,
            column_count=3,
            raw_schema={"columns": []},
        )
        session.add(ver)
        await session.commit()

    # 1. Run verification on intact files (must succeed)
    is_valid = await verify_integrity(database_url=db_url, storage_dir=storage_dir)
    assert is_valid is True

    # 2. Corrupt original file content (hash mismatch)
    orig_file.write_bytes(b"tampered_data_bytes")
    is_corrupt_valid = await verify_integrity(database_url=db_url, storage_dir=storage_dir)
    assert is_corrupt_valid is False

    # 3. Remove Parquet file (missing artifact)
    orig_file.write_bytes(test_content)  # restore original
    parquet_file.unlink()
    is_missing_valid = await verify_integrity(database_url=db_url, storage_dir=storage_dir)
    assert is_missing_valid is False

    await engine.dispose()
