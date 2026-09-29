"""Tests for FileStorageService: path security, streaming hashes, and preview reads."""

import io
import uuid
import pandas as pd
import pytest
from app.core.exceptions import OversizedFileException, StorageException
from app.services.file_storage import FileStorageService


def test_path_traversal_sanitization(test_storage: FileStorageService) -> None:
    """Verify that path traversal attempts (../../) are stripped to safe basenames."""
    malicious_inputs = [
        ("../../etc/passwd.csv", "passwd.csv"),
        ("..\\..\\windows\\system32\\cmd.exe.parquet", "cmd.exe.parquet"),
        ("subdir/nested/data.xlsx", "data.xlsx"),
        ("normal_file.json", "normal_file.json"),
    ]

    for raw, expected in malicious_inputs:
        cleaned = test_storage.sanitize_filename(raw)
        assert cleaned == expected
        assert "/" not in cleaned
        assert "\\" not in cleaned


@pytest.mark.asyncio
async def test_save_uploaded_stream_and_hashing(test_storage: FileStorageService) -> None:
    """Verify that streaming uploads calculate exact SHA-256 and enforce storage paths."""
    dataset_id = uuid.uuid4()
    content = b"col1,col2\n10,20\n30,40\n"
    stream = io.BytesIO(content)

    saved_path, sha256_hash, size = await test_storage.save_uploaded_stream(
        dataset_id=dataset_id,
        version_number=1,
        filename="../../test_file.csv",
        file_stream=stream,
    )

    assert saved_path.exists()
    assert saved_path.name == "test_file.csv"
    assert size == len(content)
    # Check that file is inside version 1 original directory
    assert "v1" in str(saved_path)
    assert "original" in str(saved_path)
    assert len(sha256_hash) == 64


@pytest.mark.asyncio
async def test_oversized_upload_rejection(test_storage: FileStorageService) -> None:
    """Verify that files exceeding the configured size limit are rejected immediately."""
    dataset_id = uuid.uuid4()
    # Force tiny limit for test
    test_storage.max_bytes = 100
    oversized_content = b"X" * 150
    stream = io.BytesIO(oversized_content)

    with pytest.raises(OversizedFileException):
        await test_storage.save_uploaded_stream(
            dataset_id=dataset_id,
            version_number=1,
            filename="large.csv",
            file_stream=stream,
        )


def test_parquet_serialization_and_preview(test_storage: FileStorageService) -> None:
    """Verify writing canonical Parquet and reading bounded previews."""
    dataset_id = uuid.uuid4()
    df = pd.DataFrame({
        "id": range(1, 51),
        "score": [float(i * 1.5) for i in range(1, 51)],
    })

    parquet_path = test_storage.save_canonical_parquet(df, dataset_id, 1)
    assert parquet_path.exists()
    assert parquet_path.name == "data.parquet"

    # Preview default 20 rows
    preview_df, total_rows, total_cols = test_storage.read_preview(
        dataset_id=dataset_id,
        version_number=1,
        limit=20,
        offset=0,
    )
    assert total_rows == 50
    assert total_cols == 2
    assert len(preview_df) == 20
    assert list(preview_df.columns) == ["id", "score"]
    assert preview_df.iloc[0]["id"] == 1

    # Preview with offset
    preview_slice, _, _ = test_storage.read_preview(
        dataset_id=dataset_id,
        version_number=1,
        limit=5,
        offset=10,
    )
    assert len(preview_slice) == 5
    assert preview_slice.iloc[0]["id"] == 11
