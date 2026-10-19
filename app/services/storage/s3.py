"""S3-compatible persistent object storage backend."""

from pathlib import Path
from typing import Any, BinaryIO, Optional
import uuid

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.exceptions import StorageException
from app.core.logging import get_logger
from app.services.storage.base import BaseStorageBackend

logger = get_logger(__name__)


class S3StorageBackend(BaseStorageBackend):
    """S3-compatible object storage backend (Backblaze B2, AWS S3, MinIO)."""

    def __init__(
        self,
        endpoint_url: str,
        bucket_name: str,
        access_key: str,
        secret_key: str,
        region_name: Optional[str] = None,
        signature_version: str = "s3v4",
        s3_client: Optional[Any] = None,
    ):
        self.endpoint_url = endpoint_url
        self.bucket_name = bucket_name
        self.region_name = region_name or "us-east-1"
        self.signature_version = signature_version

        if s3_client is not None:
            self.client = s3_client
        else:
            self.client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=self.region_name,
                config=Config(
                    signature_version=self.signature_version,
                    s3={"addressing_style": "virtual" if "backblazeb2.com" not in self.endpoint_url else "path"},
                ),
            )
        logger.info(
            "Initialized S3StorageBackend for bucket '%s' at endpoint '%s'",
            self.bucket_name,
            self.endpoint_url,
        )

    def _clean_key(self, relative_key: str) -> str:
        return relative_key.replace("\\", "/").lstrip("/")

    def save_file(self, relative_key: str, local_source_path: Path) -> int:
        key = self._clean_key(relative_key)
        if not local_source_path.exists():
            raise StorageException(f"Local source file does not exist: {local_source_path}")
        size = local_source_path.stat().st_size

        try:
            self.client.upload_file(
                Filename=str(local_source_path),
                Bucket=self.bucket_name,
                Key=key,
            )
            logger.info("Uploaded S3 object s3://%s/%s (%d bytes)", self.bucket_name, key, size)
            return size
        except Exception as exc:
            logger.exception("Failed to upload file to S3 s3://%s/%s: %s", self.bucket_name, key, exc)
            raise StorageException(f"Failed to persist file to S3: {exc}") from exc

    def save_stream(self, relative_key: str, stream: BinaryIO) -> int:
        key = self._clean_key(relative_key)
        try:
            self.client.upload_fileobj(
                Fileobj=stream,
                Bucket=self.bucket_name,
                Key=key,
            )
            size = self.get_size(key)
            logger.info("Uploaded S3 stream s3://%s/%s (%d bytes)", self.bucket_name, key, size)
            return size
        except Exception as exc:
            logger.exception("Failed to upload stream to S3 s3://%s/%s: %s", self.bucket_name, key, exc)
            raise StorageException(f"Failed to persist stream to S3: {exc}") from exc

    def materialize_file(self, relative_key: str, target_local_path: Path) -> Path:
        key = self._clean_key(relative_key)
        target_local_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dl = target_local_path.parent / f".tmp_s3_dl_{uuid.uuid4().hex}"

        try:
            self.client.download_file(
                Bucket=self.bucket_name,
                Key=key,
                Filename=str(temp_dl),
            )
            temp_dl.replace(target_local_path)
            logger.info("Materialized S3 object s3://%s/%s to local file %s", self.bucket_name, key, target_local_path)
            return target_local_path
        except ClientError as ce:
            error_code = ce.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey", "NotFound"):
                raise StorageException(f"S3 object not found: s3://{self.bucket_name}/{key}") from ce
            logger.exception("Failed to download S3 object s3://%s/%s: %s", self.bucket_name, key, ce)
            raise StorageException(f"S3 download failed: {ce}") from ce
        except Exception as exc:
            logger.exception("Unexpected error downloading S3 object s3://%s/%s: %s", self.bucket_name, key, exc)
            raise StorageException(f"S3 download failed: {exc}") from exc
        finally:
            if temp_dl.exists():
                temp_dl.unlink(missing_ok=True)

    def delete_file(self, relative_key: str) -> bool:
        key = self._clean_key(relative_key)
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.info("Deleted S3 object s3://%s/%s", self.bucket_name, key)
            return True
        except Exception as exc:
            logger.warning("Failed to delete S3 object s3://%s/%s: %s", self.bucket_name, key, exc)
            return False

    def delete_prefix(self, prefix: str) -> int:
        clean_prefix = self._clean_key(prefix)
        if clean_prefix and not clean_prefix.endswith("/"):
            clean_prefix += "/"

        total_deleted = 0
        paginator = self.client.get_paginator("list_objects_v2")

        try:
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=clean_prefix):
                contents = page.get("Contents", [])
                if not contents:
                    continue
                delete_keys = [{"Key": obj["Key"]} for obj in contents]
                self.client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={"Objects": delete_keys, "Quiet": True},
                )
                total_deleted += len(delete_keys)

            logger.info("Deleted %d S3 objects matching prefix s3://%s/%s", total_deleted, self.bucket_name, clean_prefix)
            return total_deleted
        except Exception as exc:
            logger.warning("Error deleting S3 objects for prefix %s: %s", clean_prefix, exc)
            return total_deleted

    def exists(self, relative_key: str) -> bool:
        key = self._clean_key(relative_key)
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as ce:
            error_code = ce.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey", "NotFound"):
                return False
            status = ce.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404:
                return False
            logger.warning("Error checking existence of S3 key %s: %s", key, ce)
            return False
        except Exception:
            return False

    def get_size(self, relative_key: str) -> int:
        key = self._clean_key(relative_key)
        try:
            response = self.client.head_object(Bucket=self.bucket_name, Key=key)
            return response.get("ContentLength", 0)
        except Exception as exc:
            raise StorageException(f"Could not determine size of s3://{self.bucket_name}/{key}: {exc}") from exc

    def check_health(self) -> bool:
        """Check bucket availability and list access without creating or deleting objects."""
        try:
            self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix="datasets/",
                MaxKeys=1,
            )
            return True
        except Exception:
            # Do not log provider exceptions, which may contain request or credential details.
            logger.error("S3 storage availability check failed for bucket '%s'", self.bucket_name)
            return False
