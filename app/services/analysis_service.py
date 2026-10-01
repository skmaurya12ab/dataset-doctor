"""Service coordinating deterministic analysis execution, lifecycle transitions, and persistence."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import EntityNotFoundException, ValidationException
from app.core.logging import get_logger
from app.engine.base import AnalysisContext
from app.engine.pipeline import AnalysisPipeline
from app.models.analysis import AnalysisRun, AnalysisStatus, QualityIssue
from app.models.dataset import DatasetVersion
from app.schemas.analysis import AnalysisRequest
from app.services.file_storage import FileStorageService
from app.services.job_runner import AnalysisJobRunner, get_job_runner

logger = get_logger(__name__)


async def _execute_analysis_coro(
    run_id: uuid.UUID,
    version_id: uuid.UUID,
    request_params: Dict[str, Any],
    session: Optional[AsyncSession] = None,
) -> None:
    """Core coroutine that loads Parquet, executes deterministic pipeline, and persists findings."""
    settings = get_settings()
    own_engine = None

    if session is None:
        # Create thread-isolated engine and session with NullPool
        own_engine = create_async_engine(settings.database_url, poolclass=NullPool)
        session_factory = async_sessionmaker(own_engine, expire_on_commit=False)
        active_session = session_factory()
    else:
        active_session = session

    try:
        async with active_session:
            # 1. Retrieve AnalysisRun and DatasetVersion
            run = await active_session.get(AnalysisRun, run_id)
            if not run:
                logger.error("AnalysisRun %s not found for background execution", run_id)
                return

            version = await active_session.get(DatasetVersion, version_id)
            if not version:
                logger.error("DatasetVersion %s not found for analysis run %s", version_id, run_id)
                run.status = AnalysisStatus.FAILED.value
                run.error_message = f"Dataset version '{version_id}' not found."
                run.completed_at = datetime.now(timezone.utc)
                await active_session.commit()
                return

            # 2. Mark RUNNING
            run.status = AnalysisStatus.RUNNING.value
            await active_session.commit()
            logger.info("Analysis run %s marked as RUNNING", run_id)

            # 3. Locate and load canonical Parquet file
            parquet_path = None
            if version.storage_path:
                stored_p = Path(version.storage_path)
                if stored_p.exists():
                    parquet_path = stored_p

            if parquet_path is None or not parquet_path.exists():
                storage = FileStorageService()
                parquet_path = storage.get_parquet_path(version.dataset_id, version.version_number)

            if not parquet_path.exists():
                err_msg = f"Canonical Parquet file missing for version {version.version_number} at {parquet_path}"
                logger.error(err_msg)
                run.status = AnalysisStatus.FAILED.value
                run.error_message = "Canonical dataset file could not be located."
                run.completed_at = datetime.now(timezone.utc)
                await active_session.commit()
                return

            df = pd.read_parquet(parquet_path, engine="pyarrow")


            # 4. Construct AnalysisContext
            ctx = AnalysisContext(
                dataset_version_id=str(version.id),
                file_path=parquet_path,
                df=df,
                file_format="parquet",
                target_column=run.target_column,
                problem_type=run.problem_type,
                parameters=request_params.get("parameters", {}),
            )

            # 5. Run Deterministic Analysis Pipeline
            pipeline = AnalysisPipeline()
            pipeline_result = pipeline.execute(ctx)

            # 6. Persist Quality Issues
            issues_to_create: List[QualityIssue] = []
            for issue_data in pipeline_result["all_issues"]:
                qi = QualityIssue(
                    analysis_run_id=run.id,
                    dataset_version_id=version.id,
                    module=issue_data.module,
                    analyzer_version=issue_data.analyzer_version,
                    parameters_used=issue_data.parameters_used,
                    category=issue_data.category,
                    severity=issue_data.severity.value,
                    column_name=issue_data.column_name,
                    title=issue_data.title,
                    description=issue_data.description,
                    evidence=issue_data.evidence,
                    remediation_hint=issue_data.remediation_hint,
                    detected_at=issue_data.detected_at,
                )
                issues_to_create.append(qi)

            if issues_to_create:
                active_session.add_all(issues_to_create)

            # 7. Update AnalysisRun to COMPLETED
            run.status = AnalysisStatus.COMPLETED.value
            run.engine_version = "1.0.0"
            run.analyzer_versions = pipeline_result["analyzer_versions"]
            run.total_issues_count = pipeline_result["total_issues_count"]
            run.critical_issues_count = pipeline_result["critical_issues_count"]
            run.execution_time_ms = pipeline_result["total_execution_time_ms"]
            run.summary_metrics = pipeline_result["summary_metrics"]
            run.completed_at = datetime.now(timezone.utc)

            await active_session.commit()
            logger.info("Analysis run %s completed successfully with %d issues", run_id, len(issues_to_create))

    except Exception as exc:
        logger.exception("Unhandled error executing analysis run %s: %s", run_id, str(exc))
        try:
            if own_engine is not None:
                # Open fresh session to persist failure state
                session_factory = async_sessionmaker(own_engine, expire_on_commit=False)
                async with session_factory() as err_session:
                    err_run = await err_session.get(AnalysisRun, run_id)
                    if err_run:
                        err_run.status = AnalysisStatus.FAILED.value
                        err_run.error_message = f"Deterministic analysis failed: {str(exc)}"
                        err_run.completed_at = datetime.now(timezone.utc)
                        await err_session.commit()
            else:
                run = await active_session.get(AnalysisRun, run_id)
                if run:
                    run.status = AnalysisStatus.FAILED.value
                    run.error_message = f"Deterministic analysis failed: {str(exc)}"
                    run.completed_at = datetime.now(timezone.utc)
                    await active_session.commit()
        except Exception as persist_err:
            logger.exception("Failed to persist FAILED status for run %s: %s", run_id, str(persist_err))
        raise
    finally:
        if own_engine is not None:
            await own_engine.dispose()


def _background_worker_target(run_id_str: str, version_id_str: str, request_params: Dict[str, Any]) -> None:
    """Synchronous worker thread entrypoint running asyncio loop."""
    run_uuid = uuid.UUID(run_id_str)
    version_uuid = uuid.UUID(version_id_str)
    asyncio.run(_execute_analysis_coro(run_uuid, version_uuid, request_params))


class AnalysisService:
    """Manages the full lifecycle of deterministic analysis runs and defect retrieval."""

    def __init__(self, job_runner: Optional[AnalysisJobRunner] = None):
        self.job_runner = job_runner or get_job_runner()

    async def trigger_analysis(
        self,
        db: AsyncSession,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        request_data: AnalysisRequest,
    ) -> AnalysisRun:
        """Validate dataset version, create PENDING run, and submit background task."""
        # 1. Verify DatasetVersion exists and belongs to dataset
        version_stmt = select(DatasetVersion).where(
            DatasetVersion.id == version_id,
            DatasetVersion.dataset_id == dataset_id,
        )
        version_res = await db.execute(version_stmt)
        version = version_res.scalar_one_or_none()
        if not version:
            raise EntityNotFoundException(
                "DatasetVersion",
                f"Version '{version_id}' for Dataset '{dataset_id}'",
            )

        # 2. Validate target column if supplied
        if request_data.target_column:
            schema_cols = [c.get("name") for c in version.raw_schema.get("columns", [])]
            if request_data.target_column not in schema_cols:
                raise ValidationException(
                    f"Target column '{request_data.target_column}' does not exist in dataset schema."
                )

        # 3. Create AnalysisRun record with PENDING status
        analysis_run = AnalysisRun(
            dataset_version_id=version_id,
            status=AnalysisStatus.PENDING.value,
            target_column=request_data.target_column,
            problem_type=request_data.problem_type,
            engine_version="1.0.0",
            summary_metrics={},
            analyzer_versions={},
        )
        db.add(analysis_run)
        await db.commit()
        await db.refresh(analysis_run)

        # 4. Dispatch to background runner
        run_id_str = str(analysis_run.id)
        version_id_str = str(version_id)
        req_params_dict = request_data.model_dump()

        await self.job_runner.submit_job(
            run_id_str,
            _background_worker_target,
            run_id_str,
            version_id_str,
            req_params_dict,
        )

        logger.info("Dispatched analysis run %s to background job runner", run_id_str)
        return analysis_run

    async def execute_directly(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
        version_id: uuid.UUID,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Execute analysis synchronously in the provided session (primarily for unit/integration tests)."""
        await _execute_analysis_coro(run_id, version_id, params or {}, session=db)

    async def get_analysis(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
    ) -> Optional[AnalysisRun]:
        """Fetch AnalysisRun by ID."""
        stmt = select(AnalysisRun).where(AnalysisRun.id == run_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_analysis_issues(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
        severity: Optional[str] = None,
        module: Optional[str] = None,
        column_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[QualityIssue], int]:
        """Fetch paginated, filtered quality issues with total count."""
        # Base query filters
        filters = [QualityIssue.analysis_run_id == run_id]

        if severity:
            filters.append(QualityIssue.severity == severity.upper())
        if module:
            filters.append(QualityIssue.module == module.lower())
        if column_name:
            filters.append(QualityIssue.column_name == column_name)

        # Total count query
        count_stmt = select(func.count()).select_from(QualityIssue).where(*filters)
        total_res = await db.execute(count_stmt)
        total = total_res.scalar() or 0

        # Paginated items query
        items_stmt = (
            select(QualityIssue)
            .where(*filters)
            .order_by(QualityIssue.detected_at.asc(), QualityIssue.id.asc())
            .limit(limit)
            .offset(offset)
        )
        items_res = await db.execute(items_stmt)
        items = list(items_res.scalars().all())

        return items, total
