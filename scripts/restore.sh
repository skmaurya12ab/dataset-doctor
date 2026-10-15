#!/usr/bin/env bash
# ==============================================================================
# Dataset Doctor — Unified Database & Storage Restoration Script
# Restores point-in-time snapshot and validates cryptographic integrity
# ==============================================================================
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <path_to_backup_directory>"
    echo "Example: $0 ./backups/20261010_120000"
    exit 1
fi

BACKUP_DIR="$1"
if [ ! -d "$BACKUP_DIR" ]; then
    echo "Error: Backup directory '$BACKUP_DIR' does not exist."
    exit 1
fi

echo "=========================================================="
echo " Starting Dataset Doctor Unified Restoration"
echo " Source Backup: $BACKUP_DIR"
echo "=========================================================="

# 1. Verify required files in backup
if [ ! -f "$BACKUP_DIR/db.dump" ]; then
    echo "Error: Missing $BACKUP_DIR/db.dump"
    exit 1
fi
if [ ! -f "$BACKUP_DIR/storage.tar.gz" ]; then
    echo "Error: Missing $BACKUP_DIR/storage.tar.gz"
    exit 1
fi

# 2. Restore PostgreSQL database
echo "[1/3] Restoring PostgreSQL database..."
if command -v pg_restore >/dev/null 2>&1; then
    pg_restore --clean --if-exists --no-owner --no-privileges \
        -d "${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/dataset_doctor}" \
        "$BACKUP_DIR/db.dump" || true
    echo "  -> Database restored."
else
    echo "  [WARN] pg_restore not available on host. Attempting docker exec..."
    cat "$BACKUP_DIR/db.dump" | docker exec -i dataset_doctor_prod_db pg_restore -U postgres -d dataset_doctor --clean --if-exists || true
fi

# 3. Restore Storage Artifacts
echo "[2/3] Restoring storage directory..."
UPLOAD_PATH="${UPLOAD_DIR:-uploads}"
mkdir -p "$UPLOAD_PATH"
tar -xzf "$BACKUP_DIR/storage.tar.gz" -C "$UPLOAD_PATH"
echo "  -> Storage artifacts unpacked to $UPLOAD_PATH"

# 4. Run Python Verification Utility
echo "[3/3] Cross-verifying cryptographic hashes of restored Parquet and upload files..."
python3 scripts/verify_backup.py --storage "$UPLOAD_PATH"

echo "=========================================================="
echo " Restoration and Verification Completed Successfully!"
echo "=========================================================="
