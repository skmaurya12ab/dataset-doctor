"""FastAPI main application entrypoint.

Focuses strictly on:
- Lifecycle management (startup/shutdown)
- Middleware & routing registration
- Global health probe
- Global domain exception handling
- Clean separation from business and analytical logic
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import shutdown_job_runner
from app.api.v1.router import v1_router
from app.core.config import get_settings
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

    # Ensure upload directory exists
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Upload directory confirmed at: %s", settings.upload_dir.resolve())

    yield

    # 2. Shutdown phase
    logger.info("Commencing application graceful shutdown...")
    await shutdown_job_runner()
    await close_database()
    logger.info("Application shutdown completed.")


def create_application() -> FastAPI:
    """Factory creating and configuring the primary FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        description=(
            "Dataset Doctor: AI-assisted data quality & ML-readiness platform. "
            "Deterministic profiling in Python with AI-interpreted remediation strategies."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
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

    # Root health probe
    @application.get("/health", response_model=HealthResponse, tags=["System"])
    async def root_health_check() -> HealthResponse:
        """Global health check endpoint."""
        return HealthResponse(status="ok")

    # Mount API routers
    application.include_router(v1_router, prefix="/api")

    return application


app = create_application()
