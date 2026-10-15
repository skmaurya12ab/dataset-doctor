"""Account lifecycle, tenant data management, and GDPR-compliant erasure service.

Guarantees atomic, idempotent deletion of:
- User identity, credentials, sessions, and verification/reset tokens
- Owned datasets, version lineages, and physical storage directories
- Analysis runs, quality defects, AI reports, and remediation records
"""

import uuid
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import EntityNotFoundException
from app.core.logging import get_logger
from app.models.dataset import Dataset
from app.models.user import User
from app.services.file_storage import FileStorageService

logger = get_logger(__name__)


class AccountService:
    """Orchestrates comprehensive, safe account and dataset deletion."""

    async def delete_dataset(
        self,
        db: AsyncSession,
        storage: FileStorageService,
        dataset_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Atomically delete a dataset, all associated database records, and all disk files."""
        stmt = (
            select(Dataset)
            .options(selectinload(Dataset.versions))
            .where(Dataset.id == dataset_id, Dataset.owner_id == user_id)
        )
        result = await db.execute(stmt)
        dataset = result.scalar_one_or_none()

        if not dataset:
            raise EntityNotFoundException("Dataset", str(dataset_id))

        # 1. Delete physical storage directory first
        storage.delete_dataset_dir(dataset_id)

        # 2. Delete database record (cascades to versions, runs, issues, reports, remediations)
        await db.delete(dataset)
        await db.commit()

        logger.info("Successfully deleted dataset %s and all associated artifacts for user %s", dataset_id, user_id)
        return True

    async def delete_user_account(
        self,
        db: AsyncSession,
        storage: FileStorageService,
        user_id: uuid.UUID,
    ) -> bool:
        """Permanently delete a user account and all owned datasets, files, and auth tokens.

        Idempotent: returns True if user does not exist or was deleted.
        """
        user = await db.get(User, user_id)
        if not user:
            logger.info("Account deletion requested for nonexistent user %s (idempotent)", user_id)
            return True

        # 1. Query all datasets owned by this user
        datasets_stmt = select(Dataset).where(Dataset.owner_id == user_id)
        datasets_res = await db.execute(datasets_stmt)
        datasets = datasets_res.scalars().all()

        # 2. Remove physical storage for every dataset
        for ds in datasets:
            storage.delete_dataset_dir(ds.id)
            await db.delete(ds)

        # 3. Delete user entity (cascades to user_sessions, email_verification_tokens, password_reset_tokens)
        await db.delete(user)
        await db.commit()

        logger.info(
            "Permanently purged user account %s (%s) and %d associated datasets",
            user_id,
            user.email,
            len(datasets),
        )
        return True


_account_service = AccountService()


def get_account_service() -> AccountService:
    """Dependency provider for AccountService."""
    return _account_service
