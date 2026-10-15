"""FastAPI main application entrypoint.

Focuses strictly on:
- Lifecycle management (startup/shutdown)
- Middleware & routing registration
- Global health probe
- Global domain exception handling
- Clean separation from business and analytical logic
"""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, shutdown_job_runner
from app.api.v1.router import v1_router
from app.core.config import Settings, get_settings
from app.core.database import close_database
from app.core.exceptions import DatasetDoctorException
from app.core.logging import configure_logging, get_logger
from app.schemas.health import HealthResponse

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager handling startup and shutdown events."""
    settings = get_settings()

    # 1. Startup phase
    configure_logging(level=settings.log_level)
    logger.info("Starting %s in [%s] mode", settings.app_name, settings.environment)

    # Validate production SMTP configuration
    try:
        settings.validate_production_smtp()
    except ValueError as val_err:
        logger.critical("Fatal production configuration error: %s", val_err)
        raise

    # Ensure upload directory exists
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Upload directory confirmed at: %s", settings.upload_dir.resolve())

    # Recover interrupted in-flight jobs left after previous server termination
    try:
        from app.core.database import async_session_factory
        from app.services.analysis_service import AnalysisService
        async with async_session_factory() as startup_session:
            analysis_svc = AnalysisService()
            await analysis_svc.recover_interrupted_jobs(startup_session)
    except Exception as exc:
        logger.warning("Could not execute startup job recovery (database may be uninitialized): %s", exc)

    yield

    # 2. Shutdown phase
    logger.info("Commencing application graceful shutdown...")
    await shutdown_job_runner()
    await close_database()
    logger.info("Application shutdown completed.")


def create_application() -> FastAPI:
    """Factory creating and configuring the primary FastAPI application."""
    settings = get_settings()

    show_docs = (not settings.is_production) or settings.enable_api_docs

    application = FastAPI(
        title=settings.app_name,
        description=(
            "Dataset Doctor: AI-assisted data quality & ML-readiness platform. "
            "Deterministic profiling in Python with AI-interpreted remediation strategies."
        ),
        docs_url="/docs" if show_docs else None,
        redoc_url="/redoc" if show_docs else None,
        openapi_url="/openapi.json" if show_docs else None,
        lifespan=lifespan,
    )

    # CORS configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Domain exception handler
    @application.exception_handler(DatasetDoctorException)
    async def domain_exception_handler(request: Request, exc: DatasetDoctorException) -> JSONResponse:
        logger.warning("Domain exception caught on %s: %s (status %d)", request.url.path, exc.message, exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    # Catch-all production exception handler preventing traceback leakage
    @application.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception on %s: %s", request.url.path, str(exc))
        detail = "An internal server error occurred." if settings.is_production else str(exc)
        return JSONResponse(
            status_code=500,
            content={"detail": detail},
        )

    # Liveness probe (Lightweight: does not fail during temporary external DB network blips)
    @application.get("/health", response_model=HealthResponse, tags=["System"])
    async def root_health_check() -> HealthResponse:
        """Lightweight container liveness check."""
        return HealthResponse(status="ok")

    # Readiness probe (Deep check: verifies DB connectivity and storage availability)
    @application.get("/ready", tags=["System"])
    async def readiness_check(
        db: AsyncSession = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ) -> JSONResponse:
        """Deep readiness probe verifying database connectivity and storage health."""
        checks = {"database": "unknown", "storage": "unknown"}
        status_code = 200

        # 1. Database check
        try:
            from sqlalchemy import text
            await db.execute(text("SELECT 1"))
            checks["database"] = "connected"
        except Exception as exc:
            logger.error("Readiness check database failure: %s", exc)
            checks["database"] = "unavailable"
            status_code = 503

        # 2. Storage writeability check
        try:
            if settings.upload_dir.exists() and settings.upload_dir.is_dir():
                test_file = settings.upload_dir / f".ready_test_{uuid.uuid4().hex}"
                test_file.touch()
                test_file.unlink()
                checks["storage"] = "available"
            else:
                checks["storage"] = "missing_directory"
                status_code = 503
        except Exception as exc:
            logger.error("Readiness check storage failure: %s", exc)
            checks["storage"] = "inaccessible"
            status_code = 503

        overall_status = "ready" if status_code == 200 else "unready"
        return JSONResponse(
            status_code=status_code,
            content={"status": overall_status, "checks": checks},
        )

    # Mount API routers
    application.include_router(v1_router, prefix="/api")

    return application



app = create_application()
