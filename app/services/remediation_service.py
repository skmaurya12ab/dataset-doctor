"""Orchestration service for safe, deterministic remediation execution and version creation."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid
import pandas as pd
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import EntityNotFoundException, InvalidTransformationException, ValidationException
from app.core.logging import get_logger
from app.models.ai import AIReport
from app.models.analysis import AnalysisRun, AnalysisStatus
from app.models.dataset import Dataset, DatasetVersion
from app.models.remediation import RemediationExecution, RemediationExecutionStatus
from app.schemas.analysis import AnalysisRequest
from app.schemas.ai import TransformationSpec
from app.schemas.remediation import RemediationApplyRequest
from app.services.analysis_service import AnalysisService
from app.services.file_storage import FileStorageService
from app.services.ingestion import DatasetIngestionService
from app.services.remediation_executor import RemediationExecutor, compute_snapshot_metrics

logger = get_logger(__name__)


class RemediationService:
    """Manages the full lifecycle of human-approved, deterministic remediation execution."""

    def __init__(
        self,
        storage: Optional[FileStorageService] = None,
        ingestion: Optional[DatasetIngestionService] = None,
        executor: Optional[RemediationExecutor] = None,
        analysis_service: Optional[AnalysisService] = None,
    ):
        self.storage = storage or FileStorageService()
        self.ingestion = ingestion or DatasetIngestionService()
        self.executor = executor or RemediationExecutor()
        self.analysis_service = analysis_service or AnalysisService()

    async def apply_remediation(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
        request: RemediationApplyRequest,
    ) -> RemediationExecution:
        """Execute an approved remediation plan deterministically, creating a new immutable DatasetVersion."""
        # 1. Enforce explicit human approval
        if not request.approval:
            raise ValidationException("Remediation execution requires explicit human approval (approval=True).")

        # 2. Retrieve AnalysisRun
        run_stmt = (
            select(AnalysisRun)
            .where(AnalysisRun.id == run_id)
            .options(selectinload(AnalysisRun.dataset_version))
        )
        run_res = await db.execute(run_stmt)
        run = run_res.scalar_one_or_none()
        if not run:
            raise EntityNotFoundException("AnalysisRun", str(run_id))

        if run.status != AnalysisStatus.COMPLETED.value:
            raise ValidationException(
                f"Cannot execute remediation on AnalysisRun '{run_id}' with status '{run.status}'. Must be COMPLETED."
            )

        # 3. Retrieve AIReport
        report_stmt = select(AIReport).where(AIReport.id == request.ai_report_id)
        report_res = await db.execute(report_stmt)
        report = report_res.scalar_one_or_none()
        if not report:
            raise EntityNotFoundException("AIReport", str(request.ai_report_id))

        if report.analysis_run_id != run_id:
            raise ValidationException(
                f"AIReport '{request.ai_report_id}' belongs to AnalysisRun '{report.analysis_run_id}', not '{run_id}'."
            )

        # 4. Check for existing completed execution (Idempotency Protection)
        existing_stmt = select(RemediationExecution).where(
            RemediationExecution.analysis_run_id == run_id,
            RemediationExecution.ai_report_id == request.ai_report_id,
        ).order_by(desc(RemediationExecution.created_at))
        existing_res = await db.execute(existing_stmt)
        existing_exec = existing_res.scalars().first()

        if existing_exec:
            if existing_exec.status == RemediationExecutionStatus.COMPLETED.value:
                logger.info(
                    "Idempotency hit: Returning existing completed RemediationExecution %s for run %s",
                    existing_exec.id,
                    run_id,
                )
                return existing_exec
            elif existing_exec.status in (
                RemediationExecutionStatus.RUNNING.value,
                RemediationExecutionStatus.VALIDATING.value,
            ):
                raise ValidationException(
                    f"RemediationExecution '{existing_exec.id}' is currently in progress (status: {existing_exec.status})."
                )

        # 5. Extract and parse transformation specs
        raw_specs = report.transformation_specs
        if not raw_specs or len(raw_specs) == 0:
            raise ValidationException(
                f"AIReport '{report.id}' does not contain any transformation specifications to execute."
            )

        try:
            parsed_specs = [TransformationSpec(**s) for s in raw_specs]
        except Exception as exc:
            raise InvalidTransformationException(f"Failed to validate transformation specifications: {exc}") from exc

        # 6. Retrieve source DatasetVersion
        source_version = run.dataset_version
        if not source_version:
            v_stmt = select(DatasetVersion).where(DatasetVersion.id == run.dataset_version_id)
            v_res = await db.execute(v_stmt)
            source_version = v_res.scalar_one_or_none()

        if not source_version:
            raise EntityNotFoundException("DatasetVersion", str(run.dataset_version_id))

        dataset_id = source_version.dataset_id

        # 7. Create RemediationExecution record in APPROVED state
        now_utc = datetime.now(timezone.utc)
        execution = RemediationExecution(
            id=uuid.uuid4(),
            analysis_run_id=run.id,
            ai_report_id=report.id,
            source_dataset_version_id=source_version.id,
            approved_by=request.approved_by,
            approved_at=now_utc,
            status=RemediationExecutionStatus.APPROVED.value,
            transformation_plan=raw_specs,
            pre_metrics={},
            post_metrics={},
            transformation_provenance=[],
        )
        db.add(execution)
        await db.flush()

        logger.info(
            "Remediation execution %s created in APPROVED state for run %s (source version v%d)",
            execution.id,
            run.id,
            source_version.version_number,
        )

        # 8. Load source canonical Parquet (Read-Only)
        parquet_path = self.storage.get_parquet_path(dataset_id, source_version.version_number)
        if not parquet_path.exists():
            execution.status = RemediationExecutionStatus.FAILED.value
            execution.error_message = f"Source canonical Parquet file not found at {parquet_path}"
            await db.commit()
            raise EntityNotFoundException("Source Parquet file", str(parquet_path))

        try:
            source_df = pd.read_parquet(parquet_path, engine="pyarrow")
        except Exception as exc:
            execution.status = RemediationExecutionStatus.FAILED.value
            execution.error_message = f"Failed to load source Parquet file: {exc}"
            await db.commit()
            raise ValidationException(f"Failed to read source Parquet file: {exc}") from exc

        # 9. Compute pre-execution snapshot metrics
        pre_metrics = compute_snapshot_metrics(source_df)
        execution.pre_metrics = pre_metrics
        execution.status = RemediationExecutionStatus.VALIDATING.value
        await db.flush()

        # 10. Execute transformations deterministically
        temp_parquet_path: Optional[Path] = None
        try:
            execution.status = RemediationExecutionStatus.RUNNING.value
            await db.flush()

            remediated_df, provenance_records = self.executor.execute_plan(
                source_df,
                parsed_specs,
                target_column=run.target_column,
            )

            # 11. Compute post-execution snapshot metrics
            post_metrics = compute_snapshot_metrics(remediated_df)
            execution.post_metrics = post_metrics
            execution.transformation_provenance = provenance_records

            # 12. Determine next version number
            max_v_stmt = select(func.max(DatasetVersion.version_number)).where(
                DatasetVersion.dataset_id == dataset_id
            )
            max_v_res = await db.execute(max_v_stmt)
            max_v = max_v_res.scalar_one_or_none() or source_version.version_number
            new_version_number = max_v + 1

            # 13. Save new canonical Parquet file
            new_version_dir = self.storage.get_version_dir(dataset_id, new_version_number)
            target_parquet_path = self.storage.get_parquet_path(dataset_id, new_version_number)

            temp_parquet_path = new_version_dir / f".tmp_rem_{uuid.uuid4().hex}.parquet"
            remediated_df.to_parquet(
                temp_parquet_path,
                engine="pyarrow",
                index=False,
                compression="snappy",
            )

            # Calculate SHA-256 and size of the newly generated file
            with open(temp_parquet_path, "rb") as f_in:
                hasher = hashlib.sha256()
                total_bytes = 0
                while chunk := f_in.read(64 * 1024):
                    hasher.update(chunk)
                    total_bytes += len(chunk)
                new_sha256 = hasher.hexdigest()

            # Verify hash condition: if output is byte-identical, document; otherwise confirm divergence
            if new_sha256 == source_version.sha256_hash:
                logger.warning(
                    "Remediated Parquet SHA-256 matches source version SHA-256 for dataset %s v%d",
                    dataset_id,
                    new_version_number,
                )

            # Atomic move into final canonical location
            temp_parquet_path.replace(target_parquet_path)
            temp_parquet_path = None  # moved successfully

            # 14. Build structured change summary and raw schema
            change_summary_dict = {
                "derived_from_version": source_version.version_number,
                "remediation_execution_id": str(execution.id),
                "transformations_applied": len(provenance_records),
                "rows_before": pre_metrics["row_count"],
                "rows_after": post_metrics["row_count"],
                "columns_before": pre_metrics["column_count"],
                "columns_after": post_metrics["column_count"],
            }
            change_summary_json = json.dumps(change_summary_dict)

            raw_schema = self.ingestion.extract_raw_schema(remediated_df)
            raw_schema["remediation_metadata"] = change_summary_dict

            # 15. Create new immutable DatasetVersion record
            new_version = DatasetVersion(
                id=uuid.uuid4(),
                dataset_id=dataset_id,
                parent_version_id=source_version.id,
                version_number=new_version_number,
                change_summary=change_summary_json,
                file_name=f"remediated_v{new_version_number}.parquet",
                storage_path=str(target_parquet_path.relative_to(self.storage.base_dir)),
                file_size_bytes=total_bytes,
                sha256_hash=new_sha256,
                row_count=post_metrics["row_count"],
                column_count=post_metrics["column_count"],
                raw_schema=raw_schema,
            )
            db.add(new_version)
            await db.flush()

            # 16. Update execution record to COMPLETED
            execution.result_dataset_version_id = new_version.id
            execution.status = RemediationExecutionStatus.COMPLETED.value
            execution.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(execution)

            logger.info(
                "Remediation execution %s COMPLETED: DatasetVersion v%d (%s) created",
                execution.id,
                new_version.version_number,
                new_version.id,
            )

        except Exception as exc:
            logger.exception("Remediation execution %s FAILED: %s", execution.id, str(exc))
            # Clean up temp file if present
            if temp_parquet_path and temp_parquet_path.exists():
                temp_parquet_path.unlink(missing_ok=True)

            execution.status = RemediationExecutionStatus.FAILED.value
            execution.error_message = str(exc)
            execution.completed_at = datetime.now(timezone.utc)
            try:
                await db.commit()
            except Exception as commit_exc:
                logger.error("Failed to commit FAILED status for execution %s: %s", execution.id, commit_exc)
            raise

        # 17. Automatically trigger deterministic re-analysis on the new version
        try:
            target_col = run.target_column if (run.target_column and run.target_column in remediated_df.columns) else None
            reanalysis_request = AnalysisRequest(
                target_column=target_col,
                problem_type=run.problem_type,
                parameters={},
            )
            new_run = await self.analysis_service.trigger_analysis(
                db=db,
                dataset_id=dataset_id,
                version_id=new_version.id,
                request_data=reanalysis_request,
            )
            logger.info(
                "Automatic re-analysis run %s triggered for remediated version v%d (%s)",
                new_run.id,
                new_version.version_number,
                new_version.id,
            )
        except Exception as analysis_exc:
            logger.error(
                "Automatic re-analysis trigger failed for version %s: %s (version was committed successfully)",
                new_version.id,
                str(analysis_exc),
            )

        return execution

    async def get_execution(self, db: AsyncSession, execution_id: uuid.UUID) -> RemediationExecution:
        """Retrieve a specific RemediationExecution record by UUID."""
        stmt = select(RemediationExecution).where(RemediationExecution.id == execution_id)
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            raise EntityNotFoundException("RemediationExecution", str(execution_id))
        return record

    async def list_dataset_remediations(
        self,
        db: AsyncSession,
        dataset_id: uuid.UUID,
    ) -> List[RemediationExecution]:
        """List all remediation executions associated with versions of a dataset."""
        # Find all version IDs for this dataset
        versions_stmt = select(DatasetVersion.id).where(DatasetVersion.dataset_id == dataset_id)
        v_res = await db.execute(versions_stmt)
        version_ids = v_res.scalars().all()

        if not version_ids:
            return []

        stmt = (
            select(RemediationExecution)
            .where(RemediationExecution.source_dataset_version_id.in_(version_ids))
            .order_by(desc(RemediationExecution.created_at))
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())
