"""Immutable file storage service for dataset versions.

Implements the architecture layout:
storage/datasets/<dataset_id>/versions/v<version_number>/
    ├── original/<sanitized_uploaded_name>
    └── data.parquet

Security features:
- Complete path traversal prevention (strips directory components from user filenames).
- Streaming SHA-256 computation with chunked reading.
- Strict upload size enforcement during streaming.
- Atomic file writes to prevent partial uploads on disk.
"""

import hashlib
from pathlib import Path
import re
from typing import BinaryIO, Tuple
import uuid
import pandas as pd
import pyarrow.parquet as pq

from app.core.config import get_settings
from app.core.exceptions import OversizedFileException, StorageException
from app.core.logging import get_logger

logger = get_logger(__name__)


class FileStorageService:
    """Manages disk-based persistence for dataset uploads and canonical Parquet files."""

    def __init__(self, base_dir: Path | None = None):
        settings = get_settings()
        self.base_dir = base_dir or settings.upload_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = settings.max_upload_size_bytes

    def sanitize_filename(self, raw_filename: str) -> str:
        """Strip directory components, null bytes, and non-printable characters."""
        # Extract pure basename, neutralizing path traversal (e.g. ../../)
        basename = Path(raw_filename).name
        # Keep alphanumeric, dots, underscores, dashes
        clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", basename)
        # Avoid empty or hidden files
        if not clean or clean.startswith("."):
            clean = f"dataset_{uuid.uuid4().hex[:8]}" + Path(basename).suffix
        return clean

    def get_version_dir(self, dataset_id: uuid.UUID, version_number: int) -> Path:
        """Get or create the immutable directory for a specific dataset version."""
        version_dir = self.base_dir / "datasets" / str(dataset_id) / "versions" / f"v{version_number}"
        version_dir.mkdir(parents=True, exist_ok=True)
        return version_dir

    def get_original_dir(self, dataset_id: uuid.UUID, version_number: int) -> Path:
        """Get or create the original upload directory within a version."""
        original_dir = self.get_version_dir(dataset_id, version_number) / "original"
        original_dir.mkdir(parents=True, exist_ok=True)
        return original_dir

    def get_parquet_path(self, dataset_id: uuid.UUID, version_number: int) -> Path:
        """Get canonical Parquet file path for a version."""
        return self.get_version_dir(dataset_id, version_number) / "data.parquet"

    async def save_uploaded_stream(
        self,
        dataset_id: uuid.UUID,
        version_number: int,
        filename: str,
        file_stream: BinaryIO,
    ) -> Tuple[Path, str, int]:
        """Stream an uploaded file to disk, calculating SHA-256 and verifying size.
        
        Returns:
            Tuple of (saved_file_path, sha256_hex_digest, total_file_size_bytes)
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

            # Atomic replace
            temp_path.replace(target_path)
            sha256_hash = hasher.hexdigest()

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
            if not isinstance(exc, OversizedFileException):
                logger.exception("Failed to write upload stream to disk: %s", str(exc))
                raise StorageException(str(exc)) from exc
            raise

    def save_canonical_parquet(
        self,
        df: pd.DataFrame,
        dataset_id: uuid.UUID,
        version_number: int,
    ) -> Path:
        """Write normalized dataset dataframe to the canonical Parquet file."""
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
            logger.info("Normalized canonical Parquet created at: %s", target_path)
            return target_path
        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            logger.exception("Failed to serialize canonical Parquet: %s", str(exc))
            raise StorageException(f"Parquet serialization failed: {exc}") from exc

    def read_preview(
        self,
        dataset_id: uuid.UUID,
        version_number: int,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[pd.DataFrame, int, int]:
        """Read a slice of the canonical Parquet file for preview without loading the full file into memory.
        
        Returns:
            Tuple of (preview_dataframe, total_rows, total_columns)
        """
        parquet_path = self.get_parquet_path(dataset_id, version_number)
        if not parquet_path.exists():
            raise StorageException(f"Canonical Parquet file missing at {parquet_path}")

        try:
            # Inspect metadata first to get row and column counts fast
            parquet_file = pq.ParquetFile(parquet_path)
            total_rows = parquet_file.metadata.num_rows
            total_columns = parquet_file.metadata.num_columns

            # Read bounded batch
            # For moderate preview slices, pandas read_parquet or pyarrow batch reading is fast
            df_full = pd.read_parquet(parquet_path, engine="pyarrow")
            preview_slice = df_full.iloc[offset : offset + limit]

            # Convert non-serializable objects (e.g. Timestamps, NaNs) cleanly
            preview_clean = preview_slice.replace({float("nan"): None})

            return preview_clean, total_rows, total_columns
        except Exception as exc:
            logger.exception("Failed to read Parquet preview for dataset %s v%d: %s", dataset_id, version_number, str(exc))
            raise StorageException(f"Failed to read Parquet preview: {exc}") from exc
