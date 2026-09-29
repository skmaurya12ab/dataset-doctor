"""API v1 root router combining modular endpoint sub-routers."""

from fastapi import APIRouter
from app.schemas.health import HealthResponse

v1_router = APIRouter(prefix="/v1")


@v1_router.get("/health", response_model=HealthResponse, tags=["System"])
async def v1_health_check() -> HealthResponse:
    """API v1 health status endpoint."""
    return HealthResponse(status="ok")
