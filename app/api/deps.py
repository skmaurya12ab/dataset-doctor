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


def get_analysis_service(
    job_runner: Annotated[AnalysisJobRunner, Depends(get_job_runner)],
) -> "AnalysisService":
    """Dependency provider for deterministic analysis orchestration."""
    from app.services.analysis_service import AnalysisService
    return AnalysisService(job_runner=job_runner)


def get_llm_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> "BaseLLMProvider":
    """Dependency provider for the abstract BaseLLMProvider."""
    from app.services.ai.mock_provider import MockLLMProvider
    from app.services.ai.openai_provider import OpenAIResponsesProvider

    if settings.openai_api_key:
        return OpenAIResponsesProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
            retry_backoff=settings.openai_retry_backoff,
            max_output_tokens=settings.openai_max_output_tokens,
        )
    return MockLLMProvider(model_name=settings.openai_model)


def get_ai_service(
    provider: Annotated["BaseLLMProvider", Depends(get_llm_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> "AIService":
    """Dependency provider for AIService orchestration."""
    from app.services.ai.ai_service import AIService
    return AIService(provider=provider, settings=settings)


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
AnalysisServiceDep = Annotated["AnalysisService", Depends(get_analysis_service)]
LLMProviderDep = Annotated["BaseLLMProvider", Depends(get_llm_provider)]
AIServiceDep = Annotated["AIService", Depends(get_ai_service)]


