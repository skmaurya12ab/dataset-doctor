"""User account resource quota evaluation and enforcement service.

Guarantees fair resource usage across tenants:
- Maximum active stored datasets per user
- Maximum cumulative storage volume across all versions and files per user
- Maximum concurrent background analysis runs per user
"""

import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import QuotaExceededException
from app.core.logging import get_logger
from app.models.analysis import AnalysisRun, AnalysisStatus
from app.models.dataset import Dataset, DatasetVersion

logger = get_logger(__name__)


class QuotaService:
    """Enforces account resource quotas under concurrent requests."""

    async def get_user_dataset_count(self, db: AsyncSession, user_id: uuid.UUID) -> int:
        """Count the number of active datasets owned by the user."""
        stmt = select(func.count(Dataset.id)).where(Dataset.owner_id == user_id)
        result = await db.execute(stmt)
        return result.scalar() or 0

    async def get_user_cumulative_storage_bytes(self, db: AsyncSession, user_id: uuid.UUID) -> int:
        """Sum the total storage in bytes across all dataset versions owned by the user."""
        stmt = (
            select(func.coalesce(func.sum(DatasetVersion.file_size_bytes), 0))
            .join(Dataset, DatasetVersion.dataset_id == Dataset.id)
            .where(Dataset.owner_id == user_id)
        )
        result = await db.execute(stmt)
        return int(result.scalar() or 0)

    async def get_user_active_analysis_runs(self, db: AsyncSession, user_id: uuid.UUID) -> int:
        """Count current pending and running analysis jobs owned by the user."""
        stmt = (
            select(func.count(AnalysisRun.id))
            .join(DatasetVersion, AnalysisRun.dataset_version_id == DatasetVersion.id)
            .join(Dataset, DatasetVersion.dataset_id == Dataset.id)
            .where(
                Dataset.owner_id == user_id,
                AnalysisRun.status.in_([AnalysisStatus.PENDING.value, AnalysisStatus.RUNNING.value]),
            )
        )
        result = await db.execute(stmt)
        return result.scalar() or 0

    async def check_dataset_count_quota(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        max_datasets: int,
    ) -> None:
        """Verify that creating a new dataset will not violate the maximum dataset limit."""
        count = await self.get_user_dataset_count(db, user_id)
        if count >= max_datasets:
            logger.warning("User %s exceeded dataset count quota (%d >= %d)", user_id, count, max_datasets)
            raise QuotaExceededException(
                f"Dataset quota exceeded. You have reached the maximum allowed limit of {max_datasets} datasets."
            )

    async def check_cumulative_storage_quota(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        incoming_bytes: int,
        max_storage_bytes: int,
    ) -> None:
        """Verify that storing an additional artifact will not exceed the cumulative storage quota."""
        current_bytes = await self.get_user_cumulative_storage_bytes(db, user_id)
        if (current_bytes + incoming_bytes) > max_storage_bytes:
            current_mb = round(current_bytes / (1024 * 1024), 2)
            incoming_mb = round(incoming_bytes / (1024 * 1024), 2)
            max_mb = round(max_storage_bytes / (1024 * 1024), 2)
            logger.warning(
                "User %s exceeded cumulative storage quota (%s MB + %s MB > %s MB)",
                user_id,
                current_mb,
                incoming_mb,
                max_mb,
            )
            raise QuotaExceededException(
                f"Cumulative storage quota exceeded. Current: {current_mb} MB, "
                f"Requested: {incoming_mb} MB, Limit: {max_mb} MB."
            )

    async def check_concurrent_analysis_quota(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        max_concurrent_jobs: int,
    ) -> None:
        """Verify that triggering an analysis will not violate concurrent worker constraints."""
        active_jobs = await self.get_user_active_analysis_runs(db, user_id)
        if active_jobs >= max_concurrent_jobs:
            logger.warning(
                "User %s exceeded concurrent analysis quota (%d active >= %d allowed)",
                user_id,
                active_jobs,
                max_concurrent_jobs,
            )
            raise QuotaExceededException(
                f"Concurrent analysis job limit reached ({active_jobs}/{max_concurrent_jobs} active). "
                "Please wait for ongoing analyses to complete."
            )


_quota_service = QuotaService()


def get_quota_service() -> QuotaService:
    """Dependency provider for QuotaService."""
    return _quota_service
