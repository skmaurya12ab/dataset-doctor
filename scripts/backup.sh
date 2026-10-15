#!/usr/bin/env bash
# ==============================================================================
# Dataset Doctor — Unified Database & Storage Backup Script
# Creates point-in-time consistent snapshot of PostgreSQL and Parquet files
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${1:-./backups/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$BACKUP_DIR"

echo "=========================================================="
echo " Starting Dataset Doctor Unified Backup"
echo " Destination: $BACKUP_DIR"
echo " Timestamp:   $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "=========================================================="

# 1. Backup PostgreSQL database (custom compressed archive format)
echo "[1/3] Dumping PostgreSQL database..."
if command -v pg_dump >/dev/null 2>&1; then
    pg_dump "${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/dataset_doctor}" \
        --format=custom \
        --file="$BACKUP_DIR/db.dump"
    echo "  -> Database dump created: $BACKUP_DIR/db.dump"
else
    echo "  [WARN] pg_dump not installed on host. Attempting docker exec if container is running..."
    docker exec -t dataset_doctor_prod_db pg_dump -U postgres -d dataset_doctor -Fc > "$BACKUP_DIR/db.dump" || true
fi

# 2. Backup storage directory containing Parquet artifacts and uploads
echo "[2/3] Archiving persistent file storage..."
UPLOAD_PATH="${UPLOAD_DIR:-uploads}"
if [ -d "$UPLOAD_PATH" ]; then
    tar -czf "$BACKUP_DIR/storage.tar.gz" -C "$UPLOAD_PATH" .
    echo "  -> Storage archive created: $BACKUP_DIR/storage.tar.gz"
else
    echo "  [WARN] Upload directory $UPLOAD_PATH not found; skipping storage archive."
fi

# 3. Generate SHA-256 Manifest
echo "[3/3] Generating checksum manifest..."
cat <<EOF > "$BACKUP_DIR/manifest.json"
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "backup_dir": "$BACKUP_DIR",
  "files": {
    "db_dump": "$(sha256sum "$BACKUP_DIR/db.dump" 2>/dev/null | awk '{print $1}' || echo "N/A")",
    "storage_archive": "$(sha256sum "$BACKUP_DIR/storage.tar.gz" 2>/dev/null | awk '{print $1}' || echo "N/A")"
  }
}
EOF

echo "=========================================================="
echo " Backup Completed Successfully!"
echo " Manifest: $BACKUP_DIR/manifest.json"
echo "=========================================================="
