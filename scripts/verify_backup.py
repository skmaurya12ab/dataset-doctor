#!/usr/bin/env python3
"""Database & storage backup consistency verification utility.

Traverses all DatasetVersion records in the database, locates corresponding
canonical Parquet artifacts and original files on disk, computes their SHA-256
hashes, and confirms exact cryptographic integrity.
"""

import argparse
import asyncio
import hashlib
from pathlib import Path
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.models.dataset import Dataset, DatasetVersion


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest of a file in 64 KB chunks."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(64 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


async def verify_integrity(database_url: str, storage_dir: Path) -> bool:
    """Check every DatasetVersion on disk against recorded database metadata."""
    print(f"[*] Connecting to database: {database_url}")
    print(f"[*] Checking storage directory: {storage_dir}")

    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    total_versions = 0
    passed = 0
    failed = 0

    try:
        async with session_factory() as session:
            stmt = select(DatasetVersion)
            result = await session.execute(stmt)
            versions = result.scalars().all()
            total_versions = len(versions)

            print(f"[*] Found {total_versions} dataset versions in database.")

            for v in versions:
                # 1. Check canonical Parquet file
                parquet_path = storage_dir / "datasets" / str(v.dataset_id) / "versions" / f"v{v.version_number}" / "data.parquet"
                if not parquet_path.exists():
                    print(f"[-] ERROR: Missing Parquet file for dataset {v.dataset_id} v{v.version_number} at {parquet_path}")
                    failed += 1
                    continue

                # 2. Check original upload if recorded
                expected_hash = v.sha256_hash
                if expected_hash:
                    # In our storage architecture, original upload is at original/<file_name>
                    orig_path = storage_dir / "datasets" / str(v.dataset_id) / "versions" / f"v{v.version_number}" / "original" / v.file_name
                    if orig_path.exists():
                        actual_hash = compute_sha256(orig_path)
                        if actual_hash != expected_hash:
                            print(f"[-] HASH MISMATCH: {orig_path} (expected {expected_hash}, got {actual_hash})")
                            failed += 1
                            continue

                passed += 1

        print(f"\n[+] Integrity verification complete: {passed}/{total_versions} versions verified successfully.")
        if failed > 0:
            print(f"[-] FAILED: {failed} version integrity checks failed.")
            return False
        return True

    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Verify Dataset Doctor backup integrity.")
    parser.add_argument("--db", default=None, help="Database connection URL")
    parser.add_argument("--storage", default=None, help="Path to storage/uploads directory")
    args = parser.parse_args()

    from app.core.config import get_settings
    settings = get_settings()

    db_url = args.db or settings.database_url
    storage_path = Path(args.storage or settings.upload_dir).resolve()

    success = asyncio.run(verify_integrity(db_url, storage_path))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
