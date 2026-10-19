"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod
import asyncio
from pathlib import Path
from typing import BinaryIO


class BaseStorageBackend(ABC):
    """Abstract interface defining required persistent storage operations."""

    @abstractmethod
    def save_file(self, relative_key: str, local_source_path: Path) -> int:
        """Persist a local file to the storage backend under relative_key.

        Returns:
            Total bytes persisted.
        """
        pass

    @abstractmethod
    def save_stream(self, relative_key: str, stream: BinaryIO) -> int:
        """Persist a stream to the storage backend under relative_key.

        Returns:
            Total bytes persisted.
        """
        pass

    @abstractmethod
    def materialize_file(self, relative_key: str, target_local_path: Path) -> Path:
        """Ensure the object at relative_key is available as a local file at target_local_path.

        Returns:
            Path to the verified local file.
        """
        pass

    @abstractmethod
    def delete_file(self, relative_key: str) -> bool:
        """Delete an individual object at relative_key."""
        pass

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int:
        """Delete all objects matching prefix.

        Returns:
            Number of objects deleted.
        """
        pass

    @abstractmethod
    def exists(self, relative_key: str) -> bool:
        """Check if relative_key exists in storage."""
        pass

    @abstractmethod
    def get_size(self, relative_key: str) -> int:
        """Get size in bytes of object at relative_key."""
        pass

    @abstractmethod
    def check_health(self) -> bool:
        """Check backend-specific storage availability and required access."""
        pass

    # Async wrappers using asyncio.to_thread for non-blocking I/O in async routes
    async def a_save_file(self, relative_key: str, local_source_path: Path) -> int:
        return await asyncio.to_thread(self.save_file, relative_key, local_source_path)

    async def a_save_stream(self, relative_key: str, stream: BinaryIO) -> int:
        return await asyncio.to_thread(self.save_stream, relative_key, stream)

    async def a_materialize_file(self, relative_key: str, target_local_path: Path) -> Path:
        return await asyncio.to_thread(self.materialize_file, relative_key, target_local_path)

    async def a_delete_file(self, relative_key: str) -> bool:
        return await asyncio.to_thread(self.delete_file, relative_key)

    async def a_delete_prefix(self, prefix: str) -> int:
        return await asyncio.to_thread(self.delete_prefix, prefix)

    async def a_exists(self, relative_key: str) -> bool:
        return await asyncio.to_thread(self.exists, relative_key)

    async def a_get_size(self, relative_key: str) -> int:
        return await asyncio.to_thread(self.get_size, relative_key)

    async def a_check_health(self) -> bool:
        return await asyncio.to_thread(self.check_health)
