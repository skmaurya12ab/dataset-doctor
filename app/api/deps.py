"""FastAPI dependency injection providers."""

from collections.abc import AsyncGenerator
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.services.job_runner import AnalysisJobRunner, ThreadPoolJobRunner

# Singleton job runner managed across the application lifecycle
_job_runner: ThreadPoolJobRunner | None = None


def get_job_runner() -> AnalysisJobRunner:
    """Dependency provider for the background job runner.
    
    In V1, yields the in-process ThreadPoolJobRunner.
    In V2, this can be swapped with a queue-backed runner with zero changes to route handlers.
    """
    global _job_runner
    if _job_runner is None:
        settings = get_settings()
        _job_runner = ThreadPoolJobRunner(max_workers=settings.max_worker_threads)
    return _job_runner


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
