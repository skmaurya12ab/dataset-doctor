"""Local filesystem storage backend implementation."""

from pathlib import Path
import shutil
from typing import BinaryIO
import uuid

from app.core.exceptions import StorageException
from app.core.logging import get_logger
from app.services.storage.base import BaseStorageBackend

logger = get_logger(__name__)


class LocalStorageBackend(BaseStorageBackend):
    """Stores files on the local filesystem rooted at base_dir."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_key(self, relative_key: str) -> Path:
        clean_key = relative_key.replace("\\", "/").lstrip("/")
        target = (self.base_dir / clean_key).resolve()
        if not target.is_relative_to(self.base_dir):
            raise StorageException(f"Path traversal detected in key: {relative_key}")
        return target

    def save_file(self, relative_key: str, local_source_path: Path) -> int:
        target = self._resolve_key(relative_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.resolve() != local_source_path.resolve():
            shutil.copy2(local_source_path, target)
        return target.stat().st_size

    def save_stream(self, relative_key: str, stream: BinaryIO) -> int:
        target = self._resolve_key(relative_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.parent / f".tmp_{uuid.uuid4().hex}"
        total = 0
        try:
            with open(temp_target, "wb") as f_out:
                while chunk := stream.read(64 * 1024):
                    f_out.write(chunk)
                    total += len(chunk)
            temp_target.replace(target)
            return total
        finally:
            if temp_target.exists():
                temp_target.unlink(missing_ok=True)

    def materialize_file(self, relative_key: str, target_local_path: Path) -> Path:
        source = self._resolve_key(relative_key)
        if not source.exists():
            raise StorageException(f"Local file not found: {relative_key}")
        if source.resolve() == target_local_path.resolve():
            return source
        target_local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target_local_path)
        return target_local_path

    def delete_file(self, relative_key: str) -> bool:
        try:
            target = self._resolve_key(relative_key)
            if target.exists() and target.is_file():
                target.unlink()
                return True
        except Exception as exc:
            logger.warning("Failed to delete local file %s: %s", relative_key, exc)
        return False

    def delete_prefix(self, prefix: str) -> int:
        clean_prefix = prefix.replace("\\", "/").lstrip("/")
        target_dir = self.base_dir / clean_prefix
        if target_dir.exists() and target_dir.is_dir():
            count = sum(1 for p in target_dir.rglob("*") if p.is_file())
            shutil.rmtree(target_dir, ignore_errors=True)
            return count
        return 0

    def exists(self, relative_key: str) -> bool:
        try:
            target = self._resolve_key(relative_key)
            return target.is_file()
        except Exception:
            return False

    def get_size(self, relative_key: str) -> int:
        target = self._resolve_key(relative_key)
        if not target.exists():
            raise StorageException(f"File not found: {relative_key}")
        return target.stat().st_size

    def check_health(self) -> bool:
        try:
            if self.base_dir.exists() and self.base_dir.is_dir():
                test_file = self.base_dir / f".ready_test_{uuid.uuid4().hex}"
                test_file.touch()
                test_file.unlink()
                return True
        except Exception as exc:
            logger.error("Local storage health check failed: %s", exc)
        return False
