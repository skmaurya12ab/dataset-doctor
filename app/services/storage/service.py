"""Unified storage service coordinating local caching and persistent object storage."""

import hashlib
from pathlib import Path
import re
from typing import BinaryIO, Optional, Tuple
import uuid
import pandas as pd
import pyarrow.parquet as pq

from app.core.config import get_settings
from app.core.exceptions import OversizedFileException, StorageException
from app.core.logging import get_logger
from app.services.storage.base import BaseStorageBackend
from app.services.storage.local import LocalStorageBackend
from app.services.storage.s3 import S3StorageBackend

logger = get_logger(__name__)


class FileStorageService:
    """Manages dataset storage across local filesystem and S3-compatible persistent object storage."""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        backend: Optional[BaseStorageBackend] = None,
    ):
        settings = get_settings()
        self.base_dir = (base_dir or settings.upload_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = settings.max_upload_size_bytes

        if backend is not None:
            self.backend = backend
        elif settings.storage_backend == "s3":
            self.backend = S3StorageBackend(
                endpoint_url=settings.s3_endpoint_url or "",
                bucket_name=settings.s3_bucket_name or "",
                access_key=settings.s3_access_key or "",
                secret_key=settings.s3_secret_key or "",
                region_name=settings.s3_region,
                signature_version=settings.s3_signature_version,
            )
        else:
            self.backend = LocalStorageBackend(base_dir=self.base_dir)

    def sanitize_filename(self, raw_filename: str) -> str:
        """Strip directory components, null bytes, and non-printable characters."""
        basename = Path(raw_filename.replace("\\", "/")).name
        clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", basename)
        if not clean or clean.startswith("."):
            clean = f"dataset_{uuid.uuid4().hex[:8]}" + Path(basename).suffix
        return clean

    def get_version_dir(self, dataset_id: uuid.UUID, version_number: int) -> Path:
        """Get or create the local staging/cache directory for a specific dataset version."""
        version_dir = self.base_dir / "datasets" / str(dataset_id) / "versions" / f"v{version_number}"
        version_dir.mkdir(parents=True, exist_ok=True)
        return version_dir

    def get_original_dir(self, dataset_id: uuid.UUID, version_number: int) -> Path:
        """Get or create the local original upload directory within a version."""
        original_dir = self.get_version_dir(dataset_id, version_number) / "original"
        original_dir.mkdir(parents=True, exist_ok=True)
        return original_dir

    def get_parquet_path(self, dataset_id: uuid.UUID, version_number: int) -> Path:
        """Get local canonical Parquet file path for a version."""
        return self.get_version_dir(dataset_id, version_number) / "data.parquet"

    def get_relative_parquet_key(self, dataset_id: uuid.UUID, version_number: int) -> str:
        """Stable persistent object key for the canonical Parquet artifact."""
        return f"datasets/{dataset_id}/versions/v{version_number}/data.parquet"

    def get_relative_original_key(self, dataset_id: uuid.UUID, version_number: int, filename: str) -> str:
        """Stable persistent object key for the original uploaded dataset artifact."""
        clean_name = self.sanitize_filename(filename)
        return f"datasets/{dataset_id}/versions/v{version_number}/original/{clean_name}"

    def ensure_local_parquet(self, dataset_id: uuid.UUID, version_number: int) -> Path:
        """Ensure canonical Parquet file exists in the local filesystem/cache.

        If missing locally (e.g. after container restart), materializes it from persistent storage.
        """
        local_path = self.get_parquet_path(dataset_id, version_number)
        if local_path.exists() and local_path.is_file():
            return local_path

        key = self.get_relative_parquet_key(dataset_id, version_number)
        if not self.backend.exists(key):
            raise StorageException(f"Canonical Parquet file missing at {local_path} and in persistent storage ({key})")

        return self.backend.materialize_file(key, local_path)

    async def a_ensure_local_parquet(self, dataset_id: uuid.UUID, version_number: int) -> Path:
        """Async version of ensure_local_parquet."""
        local_path = self.get_parquet_path(dataset_id, version_number)
        if local_path.exists() and local_path.is_file():
            return local_path

        key = self.get_relative_parquet_key(dataset_id, version_number)
        if not await self.backend.a_exists(key):
            raise StorageException(f"Canonical Parquet file missing at {local_path} and in persistent storage ({key})")

        return await self.backend.a_materialize_file(key, local_path)

    async def save_uploaded_stream(
        self,
        dataset_id: uuid.UUID,
        version_number: int,
        filename: str,
        file_stream: BinaryIO,
    ) -> Tuple[Path, str, int]:
        """Stream uploaded file, compute SHA-256, verify size limits, and persist to storage.

        Returns:
            Tuple of (saved_local_path, sha256_hex_digest, total_file_size_bytes)
        """
        clean_name = self.sanitize_filename(filename)
        original_dir = self.get_original_dir(dataset_id, version_number)
        target_path = original_dir / clean_name
        temp_path = original_dir / f".tmp_{uuid.uuid4().hex}"

        hasher = hashlib.sha256()
        total_bytes = 0
        chunk_size = 64 * 1024  # 64 KB chunks

        try:
            with open(temp_path, "wb") as f_out:
                while True:
                    chunk = file_stream.read(chunk_size)
                    if not chunk:
                        break
                    total_bytes += len(chunk)

                    if total_bytes > self.max_bytes:
                        settings = get_settings()
                        raise OversizedFileException(
                            max_mb=settings.max_upload_size_mb,
                            actual_bytes=total_bytes,
                        )

                    hasher.update(chunk)
                    f_out.write(chunk)

            # Atomic replace into local target
            temp_path.replace(target_path)
            sha256_hash = hasher.hexdigest()

            # If persistent object storage backend is configured, upload to persistent storage
            relative_key = self.get_relative_original_key(dataset_id, version_number, clean_name)
            try:
                await self.backend.a_save_file(relative_key, target_path)
            except Exception as exc:
                if target_path.exists():
                    target_path.unlink(missing_ok=True)
                raise StorageException(f"Failed to persist uploaded stream to storage: {exc}") from exc

            logger.info(
                "Saved upload for dataset %s v%d: %s (%d bytes, sha256=%s)",
                dataset_id,
                version_number,
                clean_name,
                total_bytes,
                sha256_hash[:12],
            )
            return target_path, sha256_hash, total_bytes

        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            if not isinstance(exc, (OversizedFileException, StorageException)):
                logger.exception("Failed to write upload stream to storage: %s", str(exc))
                raise StorageException(str(exc)) from exc
            raise

    def save_canonical_parquet(
        self,
        df: pd.DataFrame,
        dataset_id: uuid.UUID,
        version_number: int,
    ) -> Path:
        """Write normalized dataset dataframe to the canonical Parquet file and persist to storage."""
        target_path = self.get_parquet_path(dataset_id, version_number)
        temp_path = target_path.parent / f".tmp_parquet_{uuid.uuid4().hex}"

        try:
            df.to_parquet(
                temp_path,
                engine="pyarrow",
                index=False,
                compression="snappy",
            )
            temp_path.replace(target_path)

            # Persist to active storage backend
            relative_key = self.get_relative_parquet_key(dataset_id, version_number)
            try:
                self.backend.save_file(relative_key, target_path)
            except Exception as exc:
                if target_path.exists():
                    target_path.unlink(missing_ok=True)
                raise StorageException(f"Failed to persist canonical Parquet to backend: {exc}") from exc

            logger.info("Normalized canonical Parquet created and persisted at: %s", target_path)
            return target_path
        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            if not isinstance(exc, StorageException):
                logger.exception("Failed to serialize canonical Parquet: %s", str(exc))
                raise StorageException(f"Parquet serialization failed: {exc}") from exc
            raise

    def persist_canonical_parquet_file(
        self,
        dataset_id: uuid.UUID,
        version_number: int,
        local_parquet_path: Path,
    ) -> str:
        """Persist an existing local Parquet file (e.g. from remediation) to the persistent storage backend.

        Returns:
            The relative storage key.
        """
        relative_key = self.get_relative_parquet_key(dataset_id, version_number)
        try:
            self.backend.save_file(relative_key, local_parquet_path)
            return relative_key
        except Exception as exc:
            logger.exception("Failed to persist canonical Parquet file %s: %s", local_parquet_path, exc)
            raise StorageException(f"Failed to persist canonical Parquet file: {exc}") from exc

    def read_preview(
        self,
        dataset_id: uuid.UUID,
        version_number: int,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[pd.DataFrame, int, int]:
        """Read a slice of the canonical Parquet file for preview without loading the full file into memory."""
        parquet_path = self.ensure_local_parquet(dataset_id, version_number)

        try:
            parquet_file = pq.ParquetFile(parquet_path)
            total_rows = parquet_file.metadata.num_rows
            total_columns = parquet_file.metadata.num_columns

            df_full = pd.read_parquet(parquet_path, engine="pyarrow")
            preview_slice = df_full.iloc[offset : offset + limit]
            preview_clean = preview_slice.replace({float("nan"): None})

            return preview_clean, total_rows, total_columns
        except Exception as exc:
            logger.exception("Failed to read Parquet preview for dataset %s v%d: %s", dataset_id, version_number, str(exc))
            raise StorageException(f"Failed to read Parquet preview: {exc}") from exc

    def delete_dataset_dir(self, dataset_id: uuid.UUID) -> bool:
        """Safely remove the entire storage tree for a dataset locally and from persistent storage."""
        import shutil
        dataset_dir = self.base_dir / "datasets" / str(dataset_id)
        if dataset_dir.exists() and dataset_dir.is_dir():
            shutil.rmtree(dataset_dir, ignore_errors=True)

        # Remove all objects under this dataset's prefix in the persistent backend
        prefix = f"datasets/{dataset_id}/"
        self.backend.delete_prefix(prefix)
        logger.info("Deleted storage tree for dataset %s (prefix: %s)", dataset_id, prefix)
        return True

    async def a_delete_dataset_dir(self, dataset_id: uuid.UUID) -> bool:
        """Async version of delete_dataset_dir."""
        import shutil
        dataset_dir = self.base_dir / "datasets" / str(dataset_id)
        if dataset_dir.exists() and dataset_dir.is_dir():
            shutil.rmtree(dataset_dir, ignore_errors=True)

        prefix = f"datasets/{dataset_id}/"
        await self.backend.a_delete_prefix(prefix)
        logger.info("Async deleted storage tree for dataset %s (prefix: %s)", dataset_id, prefix)
        return True

    def delete_file(self, file_path: Path) -> bool:
        """Safely remove an individual file locally and from persistent storage."""
        try:
            # If path is relative to base_dir, compute key and delete from backend
            try:
                resolved_file = file_path.resolve()
                if resolved_file.is_relative_to(self.base_dir):
                    rel_key = str(resolved_file.relative_to(self.base_dir)).replace("\\", "/")
                    self.backend.delete_file(rel_key)
            except Exception as backend_exc:
                logger.warning("Could not delete persistent object for %s: %s", file_path, backend_exc)

            if file_path.exists():
                file_path.unlink()
                return True
        except Exception as exc:
            logger.warning("Could not delete file %s: %s", file_path, exc)
        return False

    async def check_health(self) -> bool:
        """Run the backend-specific storage availability check."""
        return await self.backend.a_check_health()
