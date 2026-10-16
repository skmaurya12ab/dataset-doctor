"""API v1 root router combining modular endpoint sub-routers."""

import uuid
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.ai import router as ai_router
from app.api.v1.analyses import router as analyses_router
from app.api.v1.datasets import router as datasets_router
from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse

v1_router = APIRouter(prefix="/v1")

# System health probe
@v1_router.get("/health", response_model=HealthResponse, tags=["System"])
async def v1_health_check() -> HealthResponse:
    """API v1 health status endpoint."""
    return HealthResponse(status="ok")


@v1_router.get("/ready", tags=["System"])
async def v1_readiness_check(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """API v1 readiness probe."""
    checks = {"database": "unknown", "storage": "unknown"}
    status_code = 200

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception:
        checks["database"] = "unavailable"
        status_code = 503

    try:
        from app.api.deps import get_storage_service
        storage = get_storage_service()
        if await storage.check_health():
            checks["storage"] = "available"
        else:
            checks["storage"] = "inaccessible"
            status_code = 503
    except Exception:
        checks["storage"] = "inaccessible"
        status_code = 503

    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if status_code == 200 else "unready", "checks": checks},
    )



# Authentication and identity management endpoints
from app.api.v1.auth import router as auth_router
v1_router.include_router(auth_router)

# Datasets management endpoints
v1_router.include_router(datasets_router)

# Deterministic analysis endpoints
v1_router.include_router(analyses_router)

# Grounded AI interpretation and remediation endpoints
v1_router.include_router(ai_router)

# Deterministic remediation execution and before/after comparison endpoints
from app.api.v1.remediations import router as remediations_router
v1_router.include_router(remediations_router)


