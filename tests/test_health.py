"""Tests for system health endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_health_endpoint(async_client: AsyncClient) -> None:
    """Verify that root /health returns HTTP 200 with status: ok."""
    response = await async_client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data == {"status": "ok"}


@pytest.mark.asyncio
async def test_v1_health_endpoint(async_client: AsyncClient) -> None:
    """Verify that /api/v1/health returns HTTP 200 with status: ok."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data == {"status": "ok"}
