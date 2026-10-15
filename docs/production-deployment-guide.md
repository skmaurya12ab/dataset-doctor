# Dataset Doctor — Production Deployment Guide

## Overview

This guide details the procedure for packaging, deploying, and maintaining Dataset Doctor in a secure, multi-user production environment.

---

## 1. Architecture & Deployment Topology

```
                  ┌───────────────────────────────────────────────┐
                  │                 Internet                      │
                  └───────────────────────┬───────────────────────┘
                                          │ HTTPS (Port 443)
                                          ▼
                  ┌───────────────────────────────────────────────┐
                  │               Nginx / Ingress                 │
                  │   - TLS Termination                           │
                  │   - SPA Static Asset Serving (/index.html)    │
                  │   - Rate Limiting (30 req/s, burst=50)        │
                  │   - Reverse Proxy with Trusted Headers        │
                  └───────────────┬───────────────────────────────┘
                                  │ HTTP (Port 8000)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      Backend Container (Single Replica)                         │
│   - FastAPI (Uvicorn ASGI)                                                      │
│   - In-Process ThreadPoolJobRunner                                              │
│   - Quota Enforcement & CSRF Validation                                         │
│   - Argon2id & Hashed Session Storage                                           │
└───────────────┬─────────────────────────────────────────┬───────────────────────┘
                │ SQL                                     │ Filesystem
                ▼                                         ▼
┌───────────────────────────────┐         ┌───────────────────────────────────────┐
│     PostgreSQL Database       │         │      Persistent Storage Volume        │
│   - User accounts & sessions  │         │   - Raw uploads                       │
│   - Datasets & version state  │         │   - Canonical Parquet files           │
│   - Analysis & Remediation db │         │   - Mount: /app/uploads               │
└───────────────────────────────┘         └───────────────────────────────────────┘
```

> [!IMPORTANT]
> **Single Backend Replica Constraint**: The application currently executes background analysis and remediation jobs via an in-process worker pool (`ThreadPoolJobRunner`). You **must** run exactly one backend container instance (`replicas: 1`). Do not scale horizontally until a distributed broker (such as Celery/Redis) is introduced.

---

## 2. Environment Configuration

Copy `.env.example` to `.env` and configure every required parameter.

### Required Environment Variables

```bash
# Application & Environment
ENVIRONMENT=production
APP_NAME="Dataset Doctor"
LOG_LEVEL=INFO
ENABLE_API_DOCS=false                # Set to false to disable /docs and /openapi.json in production

# Security & CORS
SECRET_KEY=generate_with_openssl_rand_hex_32   # openssl rand -hex 32
ALLOWED_ORIGINS=https://doctor.yourdomain.com   # Exact origin; NO wildcards with credentials
COOKIE_DOMAIN=yourdomain.com                    # Optional; defaults to same-host
COOKIE_SECURE=true                              # Always true over HTTPS
TRUSTED_PROXIES=127.0.0.1,172.16.0.0/12         # Subnets/IPs of trusted reverse proxies

# Database
DATABASE_URL=postgresql+asyncpg://dd_user:super_secret_db_pass@db:5432/dataset_doctor

# Persistent Storage
UPLOAD_DIR=/app/uploads                         # Absolute path mounted to persistent volume

# Email Delivery (SMTP)
REQUIRE_EMAIL_VERIFICATION=true
SMTP_HOST=smtp.sendgrid.net                     # Or AWS SES / Postmark
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your_real_smtp_api_key
SMTP_FROM_EMAIL=no-reply@yourdomain.com
SMTP_FROM_NAME="Dataset Doctor"
SMTP_USE_TLS=true

# Resource Quotas & Abuse Prevention
MAX_DATASETS_PER_USER=20
MAX_CUMULATIVE_STORAGE_MB_PER_USER=500
MAX_CONCURRENT_ANALYSIS_JOBS_PER_USER=2
RATE_LIMIT_ANALYSIS_TRIGGER=10/minute
RATE_LIMIT_AI_EXPLAIN=20/minute
RATE_LIMIT_AI_PLAN=10/minute
RATE_LIMIT_REMEDIATION_EXEC=5/minute
```

---

## 3. Database Migrations

Never allow application containers to run migrations automatically in parallel. Run migrations as a one-off pre-deployment task:

```bash
# In container or CI/CD deployment pipeline:
alembic upgrade head
```

Verify that the current revision matches `head`:
```bash
alembic current
```

---

## 4. Container Build & Deployment

### 4.1 Production Dockerfile & Compose
Build and package using `docker-compose.prod.yml`:

```bash
# 1. Build images
docker compose -f docker-compose.prod.yml build

# 2. Run pre-deployment migrations
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head

# 3. Start services
docker compose -f docker-compose.prod.yml up -d
```

### 4.2 Non-Root User & Permissions
The backend container runs as a non-privileged user `appuser` (UID 10001). The host directory mounted to `/app/uploads` must have matching ownership:
```bash
sudo chown -R 10001:10001 /opt/dataset-doctor/uploads
```

---

## 5. Reverse Proxy & HTTPS Configuration

The provided `nginx/nginx.conf` handles:
1. **Client Body Size**: `client_max_body_size 100M;` for tabular file uploads.
2. **Rate Limiting**: `limit_req_zone $binary_remote_addr zone=api_limit:10m rate=30r/s;`
3. **Forwarded Headers**: Pass `X-Forwarded-For`, `X-Forwarded-Proto`, and `Host`.
4. **SPA Fallback**:
   ```nginx
   location / {
       try_files $uri $uri/ /index.html;
   }
   ```
5. **TLS Termination**: Place SSL certificates (e.g. from Let's Encrypt / Certbot) on the proxy:
   ```nginx
   ssl_certificate /etc/letsencrypt/live/doctor.yourdomain.com/fullchain.pem;
   ssl_certificate_key /etc/letsencrypt/live/doctor.yourdomain.com/privkey.pem;
   ```

---

## 6. Health & Readiness Probes

Configure load balancer and container orchestrator health checks:

- **Liveness Probe** (Every 10s):
  - URL: `/health`
  - Expected Response: `200 OK`
  - Payload: `{"status": "ok"}`
  - Note: Does not query external dependencies; avoids restart cascades.

- **Readiness Probe** (Every 15s):
  - URL: `/ready`
  - Expected Response: `200 OK`
  - Payload: `{"status": "ready", "checks": {"database": "connected", "storage": "available"}}`
  - Returns `503 Service Unavailable` if PostgreSQL connection or storage directory fails.

---

## 7. Backups and Disaster Recovery

### 7.1 Running a Backup
The backup script captures both PostgreSQL data and disk storage:
```bash
./scripts/backup.sh /var/backups/dataset-doctor
```
This generates:
- `db_<TIMESTAMP>.sql.gz`
- `storage_<TIMESTAMP>.tar.gz`

### 7.2 Verifying Backup Integrity
After restoring or downloading a backup snapshot:
```bash
python scripts/verify_backup.py \
  --db-url "postgresql+asyncpg://..." \
  --storage-dir "/var/dataset-doctor/uploads"
```
The script verifies that every Parquet file recorded in the database exists and that SHA-256 hashes match.

### 7.3 Restoring from Backup
```bash
./scripts/restore.sh \
  /var/backups/dataset-doctor/db_20261015_120000.sql.gz \
  /var/backups/dataset-doctor/storage_20261015_120000.tar.gz
```

---

## 8. Log Monitoring & Rollback

### 8.1 Log Monitoring
- Filter logs for warnings and errors:
  ```bash
  docker compose -f docker-compose.prod.yml logs -f --tail=100 backend | grep -E "ERROR|WARNING"
  ```
- Startup recovery events are logged as:
  `Recovered X interrupted analysis runs from previous process termination`

### 8.2 Rollback Procedure
If a deployment fails:
1. Stop the application:
   ```bash
   docker compose -f docker-compose.prod.yml down
   ```
2. Rollback the database migration:
   ```bash
   docker compose -f docker-compose.prod.yml run --rm backend alembic downgrade -1
   ```
3. Revert image tags to the previous stable release:
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

---

## 9. Verification Matrix

| Area | Verified in Automated Test Suite | Requires Hosting Environment Setup |
|---|---|---|
| Hashed Session Storage | Yes (`test_security_hardening.py`) | Database provisioning |
| CSRF Header Double-Submit | Yes (`test_security_hardening.py`) | HTTPS certificate |
| Email Verification Gating | Yes (`test_security_hardening.py`) | DNS & MX/SPF/DKIM records |
| Quotas & Concurrency Caps | Yes (`test_quotas_and_abuse.py`) | Persistent volume mount |
| Startup Job Recovery | Yes (`test_startup_recovery_and_health.py`) | Container orchestrator restart |
| Health & Readiness Probes | Yes (`test_startup_recovery_and_health.py`) | Load balancer probe configuration |
| Account & Dataset Deletion | Yes (`test_account_deletion.py`) | Backup rotation policy |
| Backup Hash Verification | Yes (`test_backup_restore.py`) | Offsite S3/GCS sync cron |
| Frontend Assets & SPA Fallback | Yes (Vitest & Nginx config) | Public DNS pointing to proxy |
