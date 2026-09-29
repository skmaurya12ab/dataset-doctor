"""FastAPI dependency injection providers."""

from collections.abc import AsyncGenerator
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.services.file_storage import FileStorageService
from app.services.ingestion import DatasetIngestionService
from app.services.job_runner import AnalysisJobRunner, ThreadPoolJobRunner

# Singleton job runner managed across the application lifecycle
_job_runner: ThreadPoolJobRunner | None = None
_storage_service: FileStorageService | None = None
_ingestion_service: DatasetIngestionService | None = None


def get_job_runner() -> AnalysisJobRunner:
    """Dependency provider for the background job runner."""
    global _job_runner
    if _job_runner is None:
        settings = get_settings()
        _job_runner = ThreadPoolJobRunner(max_workers=settings.max_worker_threads)
    return _job_runner


def get_storage_service() -> FileStorageService:
    """Dependency provider for file storage operations."""
    global _storage_service
    if _storage_service is None:
        _storage_service = FileStorageService()
    return _storage_service


def get_ingestion_service() -> DatasetIngestionService:
    """Dependency provider for dataset parsing and normalization."""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = DatasetIngestionService()
    return _ingestion_service


async def shutdown_job_runner() -> None:
    """Shutdown job runner on application stop."""
    global _job_runner
    if _job_runner is not None:
        await _job_runner.shutdown(wait=True)
        _job_runner = None


# Type aliases for clean FastAPI dependency declarations
DBSessionDep = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
JobRunnerDep = Annotated[AnalysisJobRunner, Depends(get_job_runner)]
StorageServiceDep = Annotated[FileStorageService, Depends(get_storage_service)]
IngestionServiceDep = Annotated[DatasetIngestionService, Depends(get_ingestion_service)]
