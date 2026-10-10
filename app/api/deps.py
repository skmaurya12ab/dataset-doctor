"""FastAPI dependency injection providers."""

from collections.abc import AsyncGenerator
from typing import Annotated
from fastapi import Depends, Request
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


def get_remediation_executor() -> "RemediationExecutor":
    """Dependency provider for deterministic RemediationExecutor."""
    from app.services.remediation_executor import RemediationExecutor
    return RemediationExecutor()


def get_remediation_service(
    storage: Annotated[FileStorageService, Depends(get_storage_service)],
    ingestion: Annotated[DatasetIngestionService, Depends(get_ingestion_service)],
    executor: Annotated["RemediationExecutor", Depends(get_remediation_executor)],
    analysis_service: Annotated["AnalysisService", Depends(get_analysis_service)],
) -> "RemediationService":
    """Dependency provider for RemediationService orchestration."""
    from app.services.remediation_service import RemediationService
    return RemediationService(
        storage=storage,
        ingestion=ingestion,
        executor=executor,
        analysis_service=analysis_service,
    )


def get_comparison_service() -> "ComparisonService":
    """Dependency provider for ComparisonService."""
    from app.services.comparison_service import ComparisonService
    return ComparisonService()


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
RemediationExecutorDep = Annotated["RemediationExecutor", Depends(get_remediation_executor)]
RemediationServiceDep = Annotated["RemediationService", Depends(get_remediation_service)]
ComparisonServiceDep = Annotated["ComparisonService", Depends(get_comparison_service)]


async def get_current_user(
    request: Request,
    db: DBSessionDep,
    settings: SettingsDep,
) -> "User":
    """Extract, validate, and resolve the authenticated User entity from server-side session."""
    from app.core.exceptions import AuthenticationException
    from app.models.user import User
    from app.services.auth_service import get_auth_service

    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        # Fallback to Authorization: Bearer token (for automated testing & scripts)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()

    if not raw_token:
        raise AuthenticationException("Authentication required. Please log in.")

    auth_service = get_auth_service()
    user = await auth_service.validate_session(db, raw_token)
    if not user:
        raise AuthenticationException("Session is invalid or has expired. Please log in again.")

    if not user.is_active:
        raise AuthenticationException("User account is inactive. Please contact support.")

    return user


async def get_current_active_user(
    user: Annotated["User", Depends(get_current_user)],
) -> "User":
    """Ensure user is active."""
    return user


CurrentUserDep = Annotated["User", Depends(get_current_active_user)]


async def verify_dataset_owner(
    db: AsyncSession,
    dataset_id: "uuid.UUID",
    user_id: "uuid.UUID",
) -> "Dataset":
    """Verify that the dataset exists and is owned by user_id. Fail closed with 404."""
    import uuid
    from sqlalchemy import select
    from app.core.exceptions import EntityNotFoundException
    from app.models.dataset import Dataset

    stmt = select(Dataset).where(Dataset.id == dataset_id, Dataset.owner_id == user_id)
    dataset = (await db.execute(stmt)).scalar_one_or_none()
    if not dataset:
        raise EntityNotFoundException("Dataset", str(dataset_id))
    return dataset


async def verify_version_owner(
    db: AsyncSession,
    version_id: "uuid.UUID",
    user_id: "uuid.UUID",
) -> "DatasetVersion":
    """Verify that the dataset version exists and belongs to a dataset owned by user_id."""
    import uuid
    from sqlalchemy import select
    from app.core.exceptions import EntityNotFoundException
    from app.models.dataset import Dataset, DatasetVersion

    stmt = (
        select(DatasetVersion)
        .join(Dataset, DatasetVersion.dataset_id == Dataset.id)
        .where(DatasetVersion.id == version_id, Dataset.owner_id == user_id)
    )
    version = (await db.execute(stmt)).scalar_one_or_none()
    if not version:
        raise EntityNotFoundException("DatasetVersion", str(version_id))
    return version


async def verify_analysis_owner(
    db: AsyncSession,
    run_id: "uuid.UUID",
    user_id: "uuid.UUID",
) -> "AnalysisRun":
    """Verify that the analysis run exists and belongs to a dataset owned by user_id."""
    import uuid
    from sqlalchemy import select
    from app.core.exceptions import EntityNotFoundException
    from app.models.analysis import AnalysisRun
    from app.models.dataset import Dataset, DatasetVersion

    stmt = (
        select(AnalysisRun)
        .join(DatasetVersion, AnalysisRun.dataset_version_id == DatasetVersion.id)
        .join(Dataset, DatasetVersion.dataset_id == Dataset.id)
        .where(AnalysisRun.id == run_id, Dataset.owner_id == user_id)
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    if not run:
        raise EntityNotFoundException("AnalysisRun", str(run_id))
    return run


async def verify_remediation_owner(
    db: AsyncSession,
    execution_id: "uuid.UUID",
    user_id: "uuid.UUID",
) -> "RemediationExecution":
    """Verify that the remediation execution belongs to a dataset owned by user_id."""
    import uuid
    from sqlalchemy import select
    from app.core.exceptions import EntityNotFoundException
    from app.models.analysis import AnalysisRun
    from app.models.dataset import Dataset, DatasetVersion
    from app.models.remediation import RemediationExecution

    stmt = (
        select(RemediationExecution)
        .join(AnalysisRun, RemediationExecution.analysis_run_id == AnalysisRun.id)
        .join(DatasetVersion, AnalysisRun.dataset_version_id == DatasetVersion.id)
        .join(Dataset, DatasetVersion.dataset_id == Dataset.id)
        .where(RemediationExecution.id == execution_id, Dataset.owner_id == user_id)
    )
    execution = (await db.execute(stmt)).scalar_one_or_none()
    if not execution:
        raise EntityNotFoundException("RemediationExecution", str(execution_id))
    return execution
