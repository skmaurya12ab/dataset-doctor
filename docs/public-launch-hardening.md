# Dataset Doctor — Public Launch Hardening (Phase 2)

## Overview

Dataset Doctor Phase 2 establishes production hardening, resource abuse prevention, secure authentication, data lifecycle management, and deployment packaging ahead of public multi-user deployment.

---

## 1. Security Review & Authentication Hardening

A comprehensive audit of the authentication system was conducted against production deployment standards:

### 1.1 Session Token Storage
- **Finding**: Raw session tokens must never be persisted in plain text in the database.
- **Resolution**: Session tokens are generated as 32-byte cryptographic random hex strings. Only their SHA-256 hashes (`session_token_hash`) are stored in PostgreSQL (`user_sessions` table).
- **Lookup & Invalidation**: Incoming `dd_session` cookies are hashed with SHA-256 before database lookup. Logouts and account deletions purge matching hashes immediately.

### 1.2 Password Hashing
- Handled with **Argon2id** (`argon2-cffi`), employing modern memory-hard and computation-hard parameters (time cost, memory cost, parallelism) with individual salt per password.

### 1.3 Cookie Attributes & CSRF Enforcement
- Session and CSRF cookies are set with:
  - `HttpOnly=True` for session cookie (`dd_session`)
  - `SameSite="lax"`
  - `Secure=True` in production environments
  - `Path="/"`
- **Double-Submit CSRF**: State-changing API requests (`POST`, `PUT`, `PATCH`, `DELETE`) authenticated via session cookies must supply a matching `X-CSRF-Token` header corresponding to the `dd_csrf` cookie. Constant-time comparison prevents timing attacks.

### 1.4 Email Verification Gating
- When `REQUIRE_EMAIL_VERIFICATION=True`, unverified users are strictly blocked (HTTP 403 Forbidden) from:
  - Dataset uploads and listings
  - Analysis triggers and results
  - AI explanations and remediation plans
  - Remediation executions
- Unverified users retain access only to session management (`/auth/me`, `/auth/logout`) and the resend verification endpoint (`/auth/resend-verification`).

### 1.5 Reverse Proxy IP Trust & Rate Limiting
- Client IP addresses are resolved using `extract_client_ip()`.
- `X-Forwarded-For` headers are only trusted if the direct connection originates from an IP address listed in `TRUSTED_PROXIES` (e.g. Nginx reverse proxy `127.0.0.1`). Spoofed headers from untrusted clients are discarded.
- In-memory rate limiters protect auth endpoints (`/register`, `/login`, `/resend-verification`) from credential stuffing and token harvesting.

---

## 2. Account Quotas and Resource Abuse Controls

To prevent system exhaustion in a public multi-user deployment without introducing complex distributed queues, PostgreSQL-backed quotas were implemented:

| Quota | Setting | Default | Action on Violation |
|---|---|---|---|
| Max Datasets | `MAX_DATASETS_PER_USER` | 20 | HTTP 429; blocks new dataset creation |
| Cumulative Storage | `MAX_CUMULATIVE_STORAGE_MB_PER_USER` | 500 MB | HTTP 429; rejects upload and cleans up partial disk files |
| Concurrent Analyses | `MAX_CONCURRENT_ANALYSIS_JOBS_PER_USER` | 2 | HTTP 429; rejects triggering additional concurrent jobs |
| Analysis Trigger Rate | `RATE_LIMIT_ANALYSIS_TRIGGER` | 10/min | HTTP 429 |
| AI Explanation Rate | `RATE_LIMIT_AI_EXPLAIN` | 20/min | HTTP 429 |
| AI Remediation Plan Rate | `RATE_LIMIT_AI_PLAN` | 10/min | HTTP 429 |
| Remediation Execution Rate | `RATE_LIMIT_REMEDIATION_EXEC` | 5/min | HTTP 429 |

### Atomic Partial File Cleanup
When a user upload or remediation execution exceeds the storage quota:
1. The transaction is aborted.
2. Any temporary Parquet or raw files written to disk are immediately deleted (`delete_file`).
3. No orphaned files, versions, or database rows remain.

---

## 3. Email Delivery & Production Validation

- **Fail-Fast Startup**: In production (`ENVIRONMENT=production`), startup validates the explicitly selected `EMAIL_PROVIDER` (`smtp` or `apps_script`) and rejects `mock` or incomplete provider configuration.
- **Mock Provider for Testing**: In testing and local development, `MockEmailService` keeps messages in an explicit in-memory test interface and does not log tokens, links, bodies, or recipient addresses.
- **Abuse Limits**: PostgreSQL-backed daily delivery caps and per-account cooldowns reserve capacity before provider calls; the Apps Script relay applies independent daily, cooldown, nonce-replay, and request-idempotency controls.
- **Non-disclosing Requests**: Password-reset and verification-resend responses do not claim that a message was delivered and do not reveal whether an account exists. Duplicate registration remains an explicit validation error in the current UX.
- **Manual Setup**: The Apps Script relay has not been deployed or tested against a live inbox. See [Authentication Email Delivery](email-delivery.md) for the manual account, sender-consent, secret, and inbox-smoke-test steps.

---

## 4. GDPR-Compliant Account & Data Deletion

The `AccountService` provides complete, idempotent data purging:

### 4.1 Dataset Deletion (`DELETE /api/v1/datasets/{dataset_id}`)
- Verifies dataset ownership by authenticated user.
- Recursively deletes physical storage directory (`uploads/datasets/<dataset_id>`).
- Database cascade deletes:
  - Dataset versions
  - Analysis runs and quality issues
  - Version comparisons
  - Remediation plans and executions

### 4.2 Account Deletion (`DELETE /api/v1/auth/me`)
- Iterates over all datasets owned by the user and purges their physical directories.
- Deletes user database entity, cascading:
  - All owned datasets and versions
  - All active sessions
  - All verification and password-reset tokens
- Clears session and CSRF cookies in the response.

### 4.3 Backup Retention Implications
- Point-in-time database and storage backups will retain data until backup snapshots age out per backup retention policies. Real-time instant backup modification is neither safe nor possible in standard snapshot architectures.

---

## 5. Background Job Recovery & Health Probes

### 5.1 Interrupted Job Startup Recovery
- On application startup (`lifespan`), `AnalysisService.recover_interrupted_jobs` queries for runs left in `PENDING` or `RUNNING` status from previous process crashes.
- Interrupted jobs are marked `FAILED` with an explicit error: `"Analysis was interrupted by server restart or process termination"`.
- Job history and timestamps are preserved; active running tasks in the current process are not affected.

### 5.2 Liveness Probe (`/health` & `/api/v1/health`)
- Lightweight check returning `{"status": "ok"}`.
- Does not query PostgreSQL or storage, preventing container restart loops during temporary database network blips.

### 5.3 Deep Readiness Probe (`/ready` & `/api/v1/ready`)
- Deep check verifying:
  1. PostgreSQL database connectivity (`SELECT 1`).
  2. Storage directory read/write capability (creating and unlinking a temporary test file).
- Returns HTTP 200 `{"status": "ready"}` or HTTP 503 `{"status": "unready"}`.

---

## 6. Architecture Constraint: Single Backend Replica

The current application uses an in-process `ThreadPoolJobRunner` for background analysis and remediation jobs.

**Important Deployment Rule**:
The backend must run as a **single replica** (`replicas: 1`). Multiple container replicas cannot coordinate in-process job runners without an external distributed queue (e.g. Celery/Redis). Single-replica deployment supports concurrent requests via async I/O and worker threads safely.
