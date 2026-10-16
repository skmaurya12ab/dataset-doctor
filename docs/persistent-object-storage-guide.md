# Dataset Doctor — Persistent Object Storage Architecture & Operator Guide

This guide describes the persistent object storage architecture for Dataset Doctor, detailing how to configure, operate, and transition between **Local Filesystem** and **S3-Compatible Object Storage** (such as Backblaze B2, MinIO, or AWS S3).

---

## 1. Storage Modes Overview

Dataset Doctor supports two storage engines via `STORAGE_BACKEND`:

| Storage Backend | Engine Key | Intended Environment | Persistence Model |
| :--- | :--- | :--- | :--- |
| **Local Filesystem** | `local` (default) | Local development, testing, single-node VMs with persistent block storage | Files stored under `UPLOAD_DIR` (`uploads/`) |
| **S3-Compatible Object Storage** | `s3` | Ephemeral containers (Render, Fly, Kubernetes, Koyeb) | Persistent S3 bucket with local ephemeral caching |

In `local` mode, all datasets, original uploads, and canonical Parquet files are stored in the directory defined by `UPLOAD_DIR`.

In `s3` mode, persistent state lives in the configured S3 bucket. Local disk is used strictly as an ephemeral cache and staging workspace (under `UPLOAD_DIR`), meaning container restarts, scale-to-zero sleeping, and deployments will never lose dataset versions or analytical artifacts.

---

## 2. Environment Configuration

### Required Settings

Configure the following variables in your `.env` or cloud service dashboard:

```ini
# Storage Engine Selection ("local" or "s3")
STORAGE_BACKEND="s3"

# Local staging directory (used as local cache on ephemeral disks)
UPLOAD_DIR="uploads"
MAX_UPLOAD_SIZE_MB=100

# S3-Compatible Object Storage Credentials
# Example for Backblaze B2 (US West Region):
S3_ENDPOINT_URL="https://s3.us-west-004.backblazeb2.com"
S3_BUCKET_NAME="dataset-doctor-storage"
S3_REGION="us-west-004"
S3_ACCESS_KEY="<YOUR_B2_KEY_ID>"
S3_SECRET_KEY="<YOUR_B2_APPLICATION_KEY>"
S3_SIGNATURE_VERSION="s3v4"
```

> [!IMPORTANT]
> **Startup Validation**:
> If `STORAGE_BACKEND="s3"` is configured, Dataset Doctor validates that `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY`, and `S3_SECRET_KEY` are non-empty during startup. If any required variable is missing, the application fails to boot with an explicit error. Credential values are never logged.

---

## 3. Creating a Private Bucket & Application Key in Backblaze B2

Backblaze B2 provides 10 GB of free storage with an S3-compatible API and does not require a credit card for private buckets. Follow these manual steps:

### Step 1: Create a Backblaze Account
1. Visit [https://www.backblaze.com/b2/cloud-storage.html](https://www.backblaze.com/b2/cloud-storage.html).
2. Sign up for a free B2 Cloud Storage account.

### Step 2: Create a Private Bucket
1. Log in to the Backblaze B2 console.
2. In the sidebar, navigate to **Buckets** and click **Create a Bucket**.
3. **Bucket Unique Name**: Choose a globally unique name (e.g., `dataset-doctor-storage-<unique-id>`).
4. **Files in Bucket are**: Select **Private** (Never select Public; Dataset Doctor enforces private access control).
5. **Default Encryption**: Enabled (SSE-B2).
6. **Object Lock**: Disabled (or enabled if required by organizational compliance).
7. Click **Create a Bucket**.
8. Note the **Endpoint** displayed on your bucket details (e.g., `s3.us-west-004.backblazeb2.com`).

### Step 3: Generate a Restricted Application Key
1. In the sidebar, navigate to **Application Keys** and click **Add a New Application Key**.
2. **Name of Key**: `dataset-doctor-backend`.
3. **Allow access to Bucket(s)**: Select your newly created bucket only (least-privilege).
4. **Type of Access**: `Read and Write`.
5. **Allow List All Bucket Names**: Unchecked.
6. Click **Create New Key**.
7. Copy the **`keyID`** (this is your `S3_ACCESS_KEY`) and the **`applicationKey`** (this is your `S3_SECRET_KEY`).
   > [!WARNING]
   > The `applicationKey` is shown only once upon creation. Store it securely in your password manager or deployment secrets.

---

## 4. Object Key Structure & Temporary File Lifecycle

### Deterministic Object Keys

Objects in persistent storage follow a strict, collision-proof hierarchy scoped by dataset UUID and version number:

```
s3://<bucket-name>/
    └── datasets/
        └── <dataset_id>/
            └── versions/
                ├── v1/
                │   ├── original/<sanitized_original_filename>
                │   └── data.parquet
                ├── v2/
                │   └── data.parquet
                └── v3/
                    └── data.parquet
```

- **Tenant Isolation**: Every dataset is identified by an immutable `UUIDv4`. Object keys are derived directly from the dataset ID, preventing any accidental cross-tenant access.
- **Provenance Integrity**: Version `v1` contains both the raw uploaded format and the normalized canonical Parquet. Subsequent remediated versions store immutable canonical Parquet files linked via `parent_version_id` in PostgreSQL.

### Ephemeral File Management & Cleanups

When running on ephemeral hosting (such as Render Free Tier):
1. **Upload Staging**: Incoming streams are buffered to a unique temporary file (`.tmp_<uuid>`) in 64 KB chunks while calculating SHA-256 and enforcing file size quotas. The temporary file is atomically moved to the local staging path and immediately uploaded to S3.
2. **Ephemeral Disk Materialization**: When an analytical worker, preview request, or remediation pipeline requires a dataset version, `FileStorageService.ensure_local_parquet()` checks the local disk cache:
   - If present: reads directly with zero network overhead.
   - If missing (e.g., container restarted or spun down): downloads the canonical Parquet file from S3 into a temporary download file (`.tmp_s3_dl_<uuid>`), atomically moves it to the local cache path, and proceeds.
3. **Failure Cleanup**: If an S3 upload fails or a file exceeds storage quotas, all local staging files and incomplete S3 uploads are removed. No partially uploaded files are left behind, and no database records are committed.

---

## 5. Storage Quotas & Deletion Behavior

### Quotas
- Storage quotas (`MAX_CUMULATIVE_STORAGE_MB_PER_USER`) are calculated by summing `file_size_bytes` recorded in the PostgreSQL `dataset_versions` table for the user.
- If an incoming upload or remediation exceeds the quota, the local file is unlinked, any temporary S3 object is deleted, and a `QuotaExceededException` (HTTP 413) is raised before database records are committed.

### Dataset Deletion
- When a user deletes a dataset via `DELETE /api/v1/datasets/{id}`:
  1. The local directory `uploads/datasets/{id}/` is removed.
  2. The storage service issues a prefix deletion (`datasets/{id}/`) in the S3 bucket, deleting all original files and Parquet versions.
  3. The database record is deleted (cascading to analysis runs, issues, and AI reports).

### Account Deletion
- When an account is deleted via `DELETE /api/v1/auth/me`:
  1. All datasets owned by the user are queried from the database.
  2. The storage service deletes the S3 prefix for each owned dataset.
  3. Other users' datasets in the bucket remain completely untouched.

---

## 6. How to Switch Storage Modes Safely

### Switching from Local to S3
1. **Provision Bucket**: Create the private bucket in Backblaze B2 as described in Section 3.
2. **Copy Existing Files (If preserving local data)**:
   Use the AWS CLI or `rclone` to copy existing uploads to the bucket:
   ```bash
   aws s3 sync uploads/ s3://<your-bucket-name>/ \
       --endpoint-url https://s3.<region>.backblazeb2.com
   ```
3. **Update Configuration**:
   Set `STORAGE_BACKEND="s3"` and provide the S3 endpoint, bucket, access key, and secret key in your environment.
4. **Restart Application**:
   The backend will validate the S3 configuration at startup and verify connectivity during the `/ready` probe.

### Switching from S3 to Local
1. Set `STORAGE_BACKEND="local"` in `.env`.
2. Ensure the local volume mounted at `UPLOAD_DIR` has sufficient persistent disk space.
3. If syncing data back to disk:
   ```bash
   aws s3 sync s3://<your-bucket-name>/ uploads/ \
       --endpoint-url https://s3.<region>.backblazeb2.com
   ```

---

## 7. Backup Verification & Integrity Checks

Use `scripts/verify_backup.py` to cryptographically verify database records against stored artifacts:

```bash
# Verify local storage
python3 scripts/verify_backup.py --db "postgresql+asyncpg://..." --storage "uploads"

# Verify with custom database URL
python3 scripts/verify_backup.py
```

The script verifies:
1. Every `DatasetVersion` recorded in the database has an intact canonical `data.parquet` file.
2. Every original uploaded file matches the SHA-256 hash recorded in the database.
