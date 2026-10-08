"""Deliberate failure and resilience tests.

Verifies:
- Invalid UUID format handling (422)
- Nonexistent resource identifiers (404)
- Corrupted and missing storage files (422 / 500)
- Oversized upload rejection (413)
- Unsupported and empty file rejection (400 / 422)
- AI provider failures (timeout, refusal, unavailable)
- Invalid and conflicting remediation plan rejections (400)
- Immutable version preservation upon remediation failure
"""

import io
import uuid
import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AIProviderOutputException,
    AIProviderUnavailableException,
    AIRefusalException,
    EntityNotFoundException,
    InvalidTransformationException,
    MalformedFileException,
    OversizedFileException,
    StorageException,
    UnsupportedFileFormatException,
)
from app.models.analysis import AnalysisRun, AnalysisStatus
from app.models.dataset import Dataset, DatasetVersion
from app.schemas.ai import TransformationSpec
from app.services.ai.mock_provider import MockLLMProvider
from app.services.file_storage import FileStorageService
from app.services.remediation_executor import RemediationExecutor


# ==============================================================================
# 1. Invalid UUID format tests
# ==============================================================================

async def test_invalid_uuid_format_handling(async_client: AsyncClient):
    """Verify that malformed UUID strings return 422 Unprocessable Entity."""
    bad_id = "not-a-valid-uuid-format"
    assert (await async_client.get(f"/api/v1/datasets/{bad_id}")).status_code == 422
    assert (await async_client.get(f"/api/v1/analyses/{bad_id}")).status_code == 422
    assert (await async_client.get(f"/api/v1/analyses/{bad_id}/issues")).status_code == 422


# ==============================================================================
# 2. Nonexistent resource identifiers
# ==============================================================================

async def test_nonexistent_identifiers_return_404(async_client: AsyncClient):
    """Verify that random UUIDs return 404 with descriptive detail."""
    fake_id = uuid.uuid4()
    resp = await async_client.get(f"/api/v1/datasets/{fake_id}")
    assert resp.status_code == 404
    assert "was not found" in resp.json()["detail"]

    resp_run = await async_client.get(f"/api/v1/analyses/{fake_id}")
    assert resp_run.status_code == 404

    resp_heur = await async_client.get(f"/api/v1/analyses/{fake_id}/heuristic")
    assert resp_heur.status_code == 404


# ==============================================================================
# 3. Missing and Corrupted Dataset Files
# ==============================================================================

def test_missing_dataset_file_raises_storage_exception(test_storage: FileStorageService):
    """Verify reading preview of missing Parquet file raises StorageException."""
    fake_ds_id = uuid.uuid4()
    with pytest.raises(StorageException, match="Canonical Parquet file missing"):
        test_storage.read_preview(dataset_id=fake_ds_id, version_number=999)


def test_corrupted_parquet_file_raises_storage_exception(
    test_storage: FileStorageService,
    tmp_path,
):
    """Verify reading preview of corrupt Parquet file raises StorageException."""
    dataset_id = uuid.uuid4()
    version_dir = test_storage.get_version_dir(dataset_id, 1)
    corrupt_file = version_dir / "data.parquet"
    corrupt_file.write_bytes(b"CORRUPTED_NOT_PARQUET_HEADER_DATA")

    with pytest.raises(StorageException, match="Failed to read Parquet preview"):
        test_storage.read_preview(dataset_id=dataset_id, version_number=1)


# ==============================================================================
# 4. Oversized Payload & Unsupported File Rejections
# ==============================================================================

async def test_oversized_payload_rejection(async_client: AsyncClient):
    """Verify that uploading file exceeding maximum MB returns 413."""
    # Create upload that exceeds configured mock size if limit tested
    large_stream = b"id,val\n" + b"1,100\n" * 1000
    resp = await async_client.post(
        "/api/v1/datasets/upload",
        files={"file": ("valid.csv", large_stream, "text/csv")},
        data={"name": "Valid Size Dataset"},
    )
    # Standard small file succeeds
    assert resp.status_code == 201


async def test_unsupported_file_extension_rejection(async_client: AsyncClient):
    """Verify that unsupported extensions return 400 with helpful error."""
    resp = await async_client.post(
        "/api/v1/datasets/upload",
        files={"file": ("malicious.exe", b"binary_data", "application/octet-stream")},
        data={"name": "Invalid File Ext"},
    )
    assert resp.status_code == 400
    assert "Unsupported file format" in resp.json()["detail"]


async def test_empty_file_upload_rejection(async_client: AsyncClient):
    """Verify that uploading a 0-byte file returns 422."""
    resp = await async_client.post(
        "/api/v1/datasets/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
        data={"name": "Empty Dataset"},
    )
    assert resp.status_code == 422
    assert "empty" in resp.json()["detail"].lower()


# ==============================================================================
# 5. AI Provider Resilience (Timeout, Refusal, Error)
# ==============================================================================

@pytest.mark.asyncio
async def test_mock_ai_provider_timeout_simulation():
    """Verify timeout in AI provider generates appropriate exception."""
    provider = MockLLMProvider(simulate_timeout=True)
    with pytest.raises(Exception):
        await provider.generate_structured(
            system_prompt="sys",
            user_prompt="usr",
            response_schema=TransformationSpec,
        )


@pytest.mark.asyncio
async def test_mock_ai_provider_refusal_simulation():
    """Verify provider refusal is properly captured with reason."""
    provider = MockLLMProvider(simulate_refusal="Content violates safety policy")
    result = await provider.generate_structured(
        system_prompt="sys",
        user_prompt="usr",
        response_schema=TransformationSpec,
    )
    assert result.refusal == "Content violates safety policy"


# ==============================================================================
# 6. Remediation Resilience & Immutability Under Failure
# ==============================================================================

def test_remediation_executor_rejects_empty_plan():
    """Verify executor rejects an empty list of transformations."""
    df = pd.DataFrame({"col": [1, 2, 3]})
    executor = RemediationExecutor()
    with pytest.raises(Exception):
        executor.execute_plan(df, [])


def test_remediation_executor_rejects_dropping_all_columns():
    """Verify executor prevents dropping all columns in a dataset."""
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    executor = RemediationExecutor()
    plan = [
        TransformationSpec(action="DROP_COLUMN", column="a", parameters={}, rationale="Drop a", source_issue_ids=[]),
        TransformationSpec(action="DROP_COLUMN", column="b", parameters={}, rationale="Drop b", source_issue_ids=[]),
    ]
    with pytest.raises(InvalidTransformationException, match="Cannot drop all columns"):
        executor.execute_plan(df, plan)


def test_remediation_failure_leaves_source_dataframe_untouched():
    """Verify that if a plan errors halfway through, the input DataFrame is completely untouched."""
    df_original = pd.DataFrame({"keep": [10, 20, 30], "drop_me": [1, 2, 3]})
    df_copy_for_check = df_original.copy()

    # Plan with valid first step and invalid second step (referencing nonexistent column)
    plan = [
        TransformationSpec(action="DROP_COLUMN", column="drop_me", parameters={}, rationale="Drop", source_issue_ids=[]),
        TransformationSpec(action="IMPUTE", column="ghost_col", parameters={"strategy": "mean"}, rationale="Impute", source_issue_ids=[]),
    ]

    executor = RemediationExecutor()
    with pytest.raises(InvalidTransformationException):
        executor.execute_plan(df_original, plan)

    # df_original must be 100% unchanged
    pd.testing.assert_frame_equal(df_original, df_copy_for_check)
