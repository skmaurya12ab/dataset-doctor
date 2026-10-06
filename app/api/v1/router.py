"""API v1 root router combining modular endpoint sub-routers."""

from fastapi import APIRouter
from app.api.v1.ai import router as ai_router
from app.api.v1.analyses import router as analyses_router
from app.api.v1.datasets import router as datasets_router
from app.schemas.health import HealthResponse

v1_router = APIRouter(prefix="/v1")

# System health probe
@v1_router.get("/health", response_model=HealthResponse, tags=["System"])
async def v1_health_check() -> HealthResponse:
    """API v1 health status endpoint."""
    return HealthResponse(status="ok")


# Datasets management endpoints
v1_router.include_router(datasets_router)

# Deterministic analysis endpoints
v1_router.include_router(analyses_router)

# Grounded AI interpretation and remediation endpoints
v1_router.include_router(ai_router)

# Deterministic remediation execution and before/after comparison endpoints
from app.api.v1.remediations import router as remediations_router
v1_router.include_router(remediations_router)


