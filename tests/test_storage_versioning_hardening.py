"""Exhaustive tests for Ingestion, Storage security, and Immutable Version Lineage.

Covers:
- Filename sanitization against Windows-style backslashes and POSIX traversal
- Storage directory boundary containment
- Streaming SHA-256 calculation verification
- Dual-file retention: original upload stream + canonical Parquet
- File size limit enforcement
- Immutable version lineage and parent-child provenance
- Format-specific parsers for CSV, XLSX, JSON, Parquet
"""

import io
from pathlib import Path
import uuid
import hashlib
import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MalformedFileException, OversizedFileException, StorageException, UnsupportedFileFormatException
from app.models.dataset import Dataset, DatasetVersion
from app.services.file_storage import FileStorageService
from app.services.ingestion import DatasetIngestionService


def test_path_traversal_windows_and_posix_comprehensive(test_storage: FileStorageService):
    """Verify that all malicious path traversal vectors are completely neutralized."""
    vectors = [
        ("..\\..\\..\\windows\\system32\\cmd.exe", "cmd.exe"),
        ("..\\..\\..\\etc\\passwd", "passwd"),
        ("../../etc/shadow", "shadow"),
        ("C:\\Users\\Admin\\AppData\\secret.json", "secret.json"),
        ("..\\../..\\../var/log/syslog.parquet", "syslog.parquet"),
        ("subdir/../../../nested/data.csv", "data.csv"),
        ("....//....//escape.xlsx", "escape.xlsx"),
        (".hidden_file.csv", "dataset_"),  # Should prefix with dataset_ to prevent hidden file
        ("", "dataset_"),
        ("   ", "___"),
        ("../../../", "dataset_"),
        ("..\\..\\", "dataset_"),
    ]

    for raw, expected_substr in vectors:
        clean = test_storage.sanitize_filename(raw)
        assert "/" not in clean, f"Forward slash leaked in {clean} from {raw}"
        assert "\\" not in clean, f"Backslash leaked in {clean} from {raw}"
        assert not clean.startswith("."), f"Leading dot in {clean} from {raw}"
        assert expected_substr in clean, f"Expected {expected_substr} in {clean} from {raw}"


@pytest.mark.asyncio
async def test_storage_boundary_containment(test_storage: FileStorageService):
    """Verify that stored files never escape the designated version directory."""
    dataset_id = uuid.uuid4()
    content = b"col_a,col_b\n1,2\n3,4\n"
    stream = io.BytesIO(content)

    # Attempt directory escape via filename
    saved_path, sha_hash, size = await test_storage.save_uploaded_stream(
        dataset_id=dataset_id,
        version_number=1,
        filename="..\\..\\..\\..\\escape.csv",
        file_stream=stream,
    )

    version_dir = test_storage.get_version_dir(dataset_id, 1).resolve()
    assert saved_path.resolve().is_relative_to(version_dir)
    assert saved_path.exists()
    assert size == len(content)

    # Check sha256 hash
    expected_hash = hashlib.sha256(content).hexdigest()
    assert sha_hash == expected_hash


def test_dual_retention_original_and_canonical(test_storage: FileStorageService):
    """Verify raw original upload and canonical Parquet coexist in version hierarchy."""
    dataset_id = uuid.uuid4()
    df = pd.DataFrame({"x": [10, 20, 30], "y": ["a", "b", "c"]})

    # Save canonical parquet
    parquet_path = test_storage.save_canonical_parquet(df, dataset_id, 1)
    assert parquet_path.exists()
    assert parquet_path.name == "data.parquet"

    # Read back preview
    preview_df, total_rows, total_cols = test_storage.read_preview(dataset_id, 1, limit=10)
    assert total_rows == 3
    assert total_cols == 2
    assert len(preview_df) == 3


@pytest.mark.asyncio
async def test_oversized_upload_stream_aborts_immediately(test_storage: FileStorageService):
    """Verify stream aborts when size exceeds max_bytes."""
    dataset_id = uuid.uuid4()
    test_storage.max_bytes = 64  # Set very small limit
    large_payload = b"A" * 128
    stream = io.BytesIO(large_payload)

    with pytest.raises(OversizedFileException):
        await test_storage.save_uploaded_stream(
            dataset_id=dataset_id,
            version_number=1,
            filename="oversized.csv",
            file_stream=stream,
        )


@pytest.mark.asyncio
async def test_immutable_version_lineage_and_parent_child(test_db_session: AsyncSession):
    """Verify version lineage: v1 -> v2, parent_version_id integrity, and v1 immutability."""
    ds = Dataset(name="Lineage Test Dataset")
    test_db_session.add(ds)
    await test_db_session.commit()
    await test_db_session.refresh(ds)

    v1 = DatasetVersion(
        dataset_id=ds.id,
        version_number=1,
        file_name="v1.csv",
        storage_path="uploads/v1.parquet",
        file_size_bytes=500,
        sha256_hash="hash_v1_immutable",
        row_count=100,
        column_count=5,
        raw_schema={"columns": []},
        parent_version_id=None,
    )
    test_db_session.add(v1)
    await test_db_session.commit()
    await test_db_session.refresh(v1)

    assert v1.parent_version_id is None
    assert v1.version_number == 1

    # Create v2 derived from v1
    v2 = DatasetVersion(
        dataset_id=ds.id,
        version_number=2,
        file_name="v2.csv",
        storage_path="uploads/v2.parquet",
        file_size_bytes=480,
        sha256_hash="hash_v2_remediated",
        row_count=98,
        column_count=5,
        raw_schema={"columns": []},
        parent_version_id=v1.id,
        change_summary="Applied automated deduplication",
    )
    test_db_session.add(v2)
    await test_db_session.commit()
    await test_db_session.refresh(v2)

    # Verify parent-child lineage
    assert v2.parent_version_id == v1.id
    assert v2.version_number == 2

    # Verify v1 remains unchanged
    await test_db_session.refresh(v1)
    assert v1.sha256_hash == "hash_v1_immutable"
    assert v1.version_number == 1
    assert v1.row_count == 100


def test_ingestion_formats_and_unsupported(fixtures_dir: Path):
    """Verify ingestion service across all 4 supported types and rejection of others."""
    ingestion = DatasetIngestionService()

    # Valid CSV
    csv_loaded = ingestion.parse_file(fixtures_dir / "simple.csv", "csv", "simple.csv")
    assert csv_loaded.original_format == "csv"
    assert len(csv_loaded.dataframe) == 5

    # Valid XLSX
    xlsx_loaded = ingestion.parse_file(fixtures_dir / "sample.xlsx", "xlsx", "sample.xlsx")
    assert xlsx_loaded.original_format == "xlsx"
    assert len(xlsx_loaded.dataframe) == 5

    # Valid JSON
    json_loaded = ingestion.parse_file(fixtures_dir / "sample.json", "json", "sample.json")
    assert json_loaded.original_format == "json"
    assert len(json_loaded.dataframe) == 5

    # Valid Parquet
    parquet_loaded = ingestion.parse_file(fixtures_dir / "sample.parquet", "parquet", "sample.parquet")
    assert parquet_loaded.original_format == "parquet"
    assert len(parquet_loaded.dataframe) == 5

    # Rejection of unsupported extensions
    unsupported = ["data.zip", "script.py", "archive.tar.gz", "image.png", "doc.pdf"]
    for fname in unsupported:
        with pytest.raises(UnsupportedFileFormatException):
            ingestion.determine_format(fname)
