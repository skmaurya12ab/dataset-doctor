"""End-to-end API integration tests for dataset upload, versioning, listing, and preview."""

from pathlib import Path
import uuid
import httpx
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_valid_csv(async_client: AsyncClient, fixtures_dir: Path) -> None:
    """Test successful upload and normalization of a CSV dataset."""
    file_path = fixtures_dir / "simple.csv"
    with open(file_path, "rb") as f:
        files = {"file": ("students.csv", f, "text/csv")}
        response = await async_client.post(
            "/api/v1/datasets/upload",
            files=files,
            data={"name": "Student Roster", "description": "Spring Semester Grades"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "READY"
    assert data["version_number"] == 1
    assert data["row_count"] == 5
    assert data["column_count"] == 3
    assert data["storage_format"] == "parquet"
    assert "dataset_id" in data
    assert "version_id" in data


@pytest.mark.asyncio
async def test_upload_all_supported_formats(async_client: AsyncClient, fixtures_dir: Path) -> None:
    """Test upload across all supported formats: XLSX, JSON, Parquet."""
    format_cases = [
        ("sample.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("sample.json", "application/json"),
        ("sample.parquet", "application/octet-stream"),
    ]

    for filename, mime in format_cases:
        file_path = fixtures_dir / filename
        with open(file_path, "rb") as f:
            files = {"file": (filename, f, mime)}
            response = await async_client.post("/api/v1/datasets/upload", files=files)

        assert response.status_code == 201, f"Failed for {filename}: {response.text}"
        data = response.json()
        assert data["status"] == "READY"
        assert data["version_number"] == 1
        assert data["row_count"] == 5


@pytest.mark.asyncio
async def test_upload_unsupported_file_format(async_client: AsyncClient) -> None:
    """Verify 400 Bad Request for unsupported file extension."""
    files = {"file": ("unsupported.txt", b"plain text content", "text/plain")}
    response = await async_client.post("/api/v1/datasets/upload", files=files)

    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_empty_file(async_client: AsyncClient, fixtures_dir: Path) -> None:
    """Verify 422 Unprocessable Entity for an empty file."""
    file_path = fixtures_dir / "empty.csv"
    with open(file_path, "rb") as f:
        files = {"file": ("empty.csv", f, "text/csv")}
        response = await async_client.post("/api/v1/datasets/upload", files=files)

    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_path_traversal_safety(async_client: AsyncClient, fixtures_dir: Path) -> None:
    """Verify that path traversal in filename is sanitized safely."""
    file_path = fixtures_dir / "simple.csv"
    with open(file_path, "rb") as f:
        files = {"file": ("../../etc/shadow.csv", f, "text/csv")}
        response = await async_client.post("/api/v1/datasets/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    assert "/" not in data["file_name"]
    assert "\\" not in data["file_name"]
    assert data["file_name"] == "shadow.csv"


@pytest.mark.asyncio
async def test_versioning_and_duplicate_upload_handling(
    async_client: AsyncClient,
    fixtures_dir: Path,
) -> None:
    """Test duplicate detection (same hash) and incremental versioning (v1 -> v2)."""
    # 1. Upload initial version v1
    file_path_1 = fixtures_dir / "simple.csv"
    with open(file_path_1, "rb") as f:
        res1 = await async_client.post(
            "/api/v1/datasets/upload",
            files={"file": ("simple.csv", f, "text/csv")},
            data={"name": "Versioning Test Dataset"},
        )
    assert res1.status_code == 201
    data1 = res1.json()
    dataset_id = data1["dataset_id"]
    version_1_id = data1["version_id"]
    assert data1["version_number"] == 1

    # 2. Upload the exact same file to the same dataset_id -> should report ALREADY_EXISTS
    with open(file_path_1, "rb") as f:
        res_dup = await async_client.post(
            "/api/v1/datasets/upload",
            files={"file": ("simple.csv", f, "text/csv")},
            data={"dataset_id": dataset_id},
        )
    assert res_dup.status_code == 201
    data_dup = res_dup.json()
    assert data_dup["status"] == "ALREADY_EXISTS"
    assert data_dup["version_number"] == 1
    assert data_dup["version_id"] == version_1_id

    # 3. Upload a different file (dirty.csv) to the same dataset_id -> creates Version 2
    file_path_2 = fixtures_dir / "dirty.csv"
    with open(file_path_2, "rb") as f:
        res2 = await async_client.post(
            "/api/v1/datasets/upload",
            files={"file": ("dirty.csv", f, "text/csv")},
            data={"dataset_id": dataset_id, "change_summary": "Added missing values for test"},
        )
    assert res2.status_code == 201
    data2 = res2.json()
    assert data2["status"] == "READY"
    assert data2["version_number"] == 2
    assert data2["dataset_id"] == dataset_id
    assert data2["row_count"] == 4
    assert data2["column_count"] == 4

    # 4. Check Dataset Detail to verify both versions exist with parent linkage
    res_detail = await async_client.get(f"/api/v1/datasets/{dataset_id}")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert len(detail["versions"]) == 2
    v1 = detail["versions"][0]
    v2 = detail["versions"][1]
    assert v1["version_number"] == 1
    assert v1["parent_version_id"] is None
    assert v2["version_number"] == 2
    assert v2["parent_version_id"] == v1["id"]
    assert v2["change_summary"] == "Added missing values for test"


@pytest.mark.asyncio
async def test_dataset_listing(async_client: AsyncClient, fixtures_dir: Path) -> None:
    """Test GET /api/v1/datasets lists all datasets."""
    # Upload one dataset
    with open(fixtures_dir / "simple.csv", "rb") as f:
        await async_client.post(
            "/api/v1/datasets/upload",
            files={"file": ("simple.csv", f, "text/csv")},
            data={"name": "Listing Test Dataset"},
        )

    res = await async_client.get("/api/v1/datasets")
    assert res.status_code == 200
    datasets = res.json()
    assert len(datasets) >= 1
    item = next(d for d in datasets if d["name"] == "Listing Test Dataset")
    assert item["latest_version_number"] == 1
    assert item["latest_row_count"] == 5
    assert item["latest_column_count"] == 3


@pytest.mark.asyncio
async def test_dataset_preview_endpoint(async_client: AsyncClient, fixtures_dir: Path) -> None:
    """Test GET /api/v1/datasets/{id}/versions/{v}/preview with limits and pagination."""
    # 1. Upload dataset
    with open(fixtures_dir / "simple.csv", "rb") as f:
        upload_res = await async_client.post(
            "/api/v1/datasets/upload",
            files={"file": ("simple.csv", f, "text/csv")},
        )
    dataset_id = upload_res.json()["dataset_id"]

    # 2. Preview default
    preview_res = await async_client.get(f"/api/v1/datasets/{dataset_id}/versions/1/preview")
    assert preview_res.status_code == 200
    preview = preview_res.json()
    assert preview["dataset_id"] == dataset_id
    assert preview["version_number"] == 1
    assert preview["total_rows"] == 5
    assert preview["total_columns"] == 3
    assert len(preview["rows"]) == 5
    assert preview["rows"][0]["name"] == "Alice"
    assert preview["rows"][0]["score"] == 85.5

    # 3. Preview with limit
    bounded_res = await async_client.get(
        f"/api/v1/datasets/{dataset_id}/versions/1/preview?limit=2&offset=1"
    )
    assert bounded_res.status_code == 200
    bounded = bounded_res.json()
    assert len(bounded["rows"]) == 2
    assert bounded["rows"][0]["name"] == "Bob"
    assert bounded["rows"][1]["name"] == "Charlie"

    # 4. Preview non-existent version -> 404
    missing_res = await async_client.get(f"/api/v1/datasets/{dataset_id}/versions/99/preview")
    assert missing_res.status_code == 404
