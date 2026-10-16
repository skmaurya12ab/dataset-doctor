# Dataset Doctor — Phase 3B2: Production API Routing & Authentication Compatibility

## Overview

This guide defines the production API routing, authentication mechanics, reverse-proxy behavior, cookie security, CSRF protection, and environment configurations for running **Dataset Doctor** across the zero-cost architecture:
- **Vercel Hobby**: React 19 / Vite Single-Page Application (Frontend)
- **Render Free**: FastAPI / Python ASGI Service (Backend)
- **Neon Free**: Serverless PostgreSQL Database
- **Backblaze B2**: S3-Compatible Persistent Object Storage

---

## 1. Same-Origin API Routing Architecture

```
 Browser Request (https://dataset-doctor.vercel.app/api/v1/datasets)
                           │
                           ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                      Vercel Edge Proxy                       │
 │  - Matches /api/:path* rewrite rule in frontend/vercel.json │
 │  - Rewrites to: https://<RENDER_SERVICE>.onrender.com/api/.. │
 │  - Serves /(.*) as /index.html for client-side routing       │
 └──────────────────────────────┬───────────────────────────────┘
                                │ HTTPS Reverse Proxy Request
                                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                 Render Free (FastAPI Backend)                │
 │  - Origin: https://dataset-doctor.vercel.app                 │
 │  - Cookie: dd_session=...; dd_csrf=...                       │
 │  - Header: X-CSRF-Token: ...                                 │
 │  - Validates session, double-submit CSRF, and user quotas    │
 └──────────────────────────────────────────────────────────────┘
```

### 1.1 Vercel External Rewrite Configuration
Under the frontend project root ([frontend/vercel.json](file:///run/media/saurabh-kumar-maurya/D43C3FD33C3FAEFC/Agentic%20AI/Antigravity/frontend/vercel.json)):
```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "cleanUrls": true,
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://YOUR_BACKEND_SERVICE.onrender.com/api/:path*"
    },
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ]
}
```

### 1.2 Frontend Base URL & Relative Routing
The Axios API client in [frontend/src/services/api.ts](file:///run/media/saurabh-kumar-maurya/D43C3FD33C3FAEFC/Agentic%20AI/Antigravity/frontend/src/services/api.ts) defaults to:
```typescript
baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1'
```
- **Same-Origin Benefit**: All browser requests target the frontend origin itself (`https://<frontend>.vercel.app/api/v1/...`).
- **No Third-Party Cookie Blocking**: Because requests are same-origin from the browser's vantage point, modern browsers (Safari ITP, Chrome third-party cookie restrictions) do not block or isolate session cookies.
- **Configurable Override**: In staging or multi-domain environments, `VITE_API_BASE_URL` can override the relative path without modifying source code.

---

## 2. Authentication & Cookie Security Model

Dataset Doctor uses server-side hashed session cookies rather than raw client tokens.

| Cookie | Purpose | HttpOnly | Secure | SameSite | Client JavaScript Access |
|---|---|:---:|:---:|:---:|:---:|
| `dd_session` | Authenticated session token | **True** | **True** (in production) | **Lax** | **Forbidden** (XSS protection) |
| `dd_csrf` | Double-submit CSRF token | **False** | **True** (in production) | **Lax** | **Allowed** (read by Axios for headers) |

### 2.1 Why `SameSite=Lax` is Safe and Optimal
1. **First-Party Context**: All AJAX and API requests initiated by the frontend application share the same site and origin via the Vercel rewrite. Cookies are sent reliably on all same-origin operations.
2. **Top-Level Navigation Compatibility**: When users click an email verification link or password reset link from webmail or an external application, `SameSite=Lax` allows cookies on safe top-level `GET` requests, preserving a smooth user onboarding flow.
3. **Cross-Site Mutation Rejection**: `SameSite=Lax` blocks cookies on cross-site `POST`, `PUT`, `DELETE`, and form submissions.

### 2.2 Double-Submit CSRF Defense
State-changing API endpoints (`POST`, `PUT`, `PATCH`, `DELETE`) require two matching tokens:
1. The `dd_csrf` cookie sent by the browser.
2. The `X-CSRF-Token` header attached by Axios.
The backend ([app/api/deps.py](file:///run/media/saurabh-kumar-maurya/D43C3FD33C3FAEFC/Agentic%20AI/Antigravity/app/api/deps.py)) validates both tokens using constant-time comparison (`secrets.compare_digest`). If either token is missing or mismatched, the request fails immediately with **HTTP 403 Forbidden**.

Safe `GET` endpoints (`/auth/me`, `/datasets`, `/health`, `/ready`) and initial authentication endpoints (`/auth/login`, `/auth/register`) are exempt from CSRF header requirements.

---

## 3. CORS and Trusted Proxy Security

### 3.1 Production CORS
- In production (`ENVIRONMENT="production"`), `ALLOWED_ORIGINS` must list the exact frontend origin(s), e.g.:
  `ALLOWED_ORIGINS="https://dataset-doctor.vercel.app"`
- **Strict Prohibition**: Wildcard `*` in `ALLOWED_ORIGINS` is strictly prohibited in production when credentials are enabled. Setting `ALLOWED_ORIGINS="*"` causes startup validation to raise a fatal `ValueError`.

### 3.2 Trusted Proxy Hardening
- Setting `TRUSTED_PROXIES="0.0.0.0/0"` or `"*"` is **strictly forbidden in production** and rejected during configuration parsing.
- On Render Free, reverse proxies connect using dynamic container network IPs. Because a static CIDR block is not published, blanket trust is unsafe.
- Client IP resolution ([app/core/security.py](file:///run/media/saurabh-kumar-maurya/D43C3FD33C3FAEFC/Agentic%20AI/Antigravity/app/core/security.py)) only extracts `X-Forwarded-For` if the direct peer is listed in `TRUSTED_PROXIES`. Untrusted direct peers have their `X-Forwarded-For` headers ignored, preventing rate-limit bypass.
- **Account-Based Security Priority**: Dataset Doctor does not rely on IP addresses for critical security. Resource limits, quota enforcement (20 datasets, 500 MB cumulative storage, 2 concurrent jobs), and dataset ownership are strictly tied to the authenticated `user.id`.

---

## 4. Large Upload & Download Considerations

### 4.1 File Size & Quotas
- Maximum single upload: `100 MB` (`MAX_UPLOAD_SIZE_MB=100`).
- Maximum cumulative storage per user: `500 MB` (`MAX_CUMULATIVE_STORAGE_MB_PER_USER=500`).
- If an upload exceeds the user's remaining cumulative storage quota, the backend aborts the transaction, returns **HTTP 429**, and atomically deletes any temporary files written to disk.

### 4.2 Vercel Edge Proxy Limitations & Cold Starts
- **Vercel Hobby Timeout**: Vercel Edge rewrites have execution timeouts (typically 10-30 seconds on Hobby). On very slow client connections, uploading a 100 MB file may hit the proxy timeout.
- **Render Cold Starts**: On Render Free, containers spin down after 15 minutes of inactivity. When a request arrives, Render takes 30-50 seconds to boot the backend.
- **Preview Deployment Testing**: Testing actual 50-100 MB uploads and cold-start latency must be validated during staging preview on Vercel and Render before opening to high-traffic production.

---

## 5. Environment Variables & Deployment Checklist

### Render Backend Environment Variables
```bash
# Environment & App
ENVIRONMENT="production"
APP_NAME="Dataset Doctor"
LOG_LEVEL="INFO"
SECRET_KEY="<generate-with-openssl-rand-hex-32>"
ENABLE_API_DOCS="false"

# Database (Neon PostgreSQL Async via asyncpg)
DATABASE_URL="postgresql+asyncpg://<neon_user>:<neon_password>@<neon_host>.neon.tech/dataset_doctor?sslmode=require"

# Storage Backend (Backblaze B2 S3 API)
STORAGE_BACKEND="s3"
S3_ENDPOINT_URL="https://s3.us-west-004.backblazeb2.com"
S3_BUCKET_NAME="dataset-doctor-prod"
S3_REGION="us-west-004"
S3_ACCESS_KEY="<backblaze_key_id>"
S3_SECRET_KEY="<backblaze_application_key>"
S3_SIGNATURE_VERSION="s3v4"

# CORS & Ingress
ALLOWED_ORIGINS="https://YOUR_FRONTEND_SUBDOMAIN.vercel.app"
COOKIE_SECURE="true"
COOKIE_SAMESITE="lax"
TRUSTED_PROXIES="127.0.0.1,::1"

# Abuse Quotas
MAX_DATASETS_PER_USER="20"
MAX_CUMULATIVE_STORAGE_MB_PER_USER="500"
MAX_CONCURRENT_ANALYSIS_JOBS_PER_USER="2"

# Email Verification
REQUIRE_EMAIL_VERIFICATION="true"
EMAIL_PROVIDER="apps_script"
APPLICATION_BASE_URL="https://YOUR_FRONTEND_SUBDOMAIN.vercel.app"
APPS_SCRIPT_URL="https://script.google.com/macros/s/DEPLOYMENT_ID/exec"
APPS_SCRIPT_HMAC_SECRET="STORE_A_32_BYTE_RANDOM_SECRET_SERVER_SIDE"
```

> [!NOTE]
> **Email Delivery Notice**: Configure and manually smoke-test the Apps Script relay before deploying these values. Production rejects `EMAIL_PROVIDER=mock`; if no real provider is configured, keep verification required and do not start the deployment. See [Authentication Email Delivery](email-delivery.md) for the setup and operational limits.

### Vercel Frontend Configuration
1. Connect repository to Vercel.
2. In **Project Settings**:
   - Set **Root Directory** to `frontend`.
   - Framework preset: `Vite`.
   - Build Command: `npm run build`.
   - Output Directory: `dist`.
3. In [frontend/vercel.json](file:///run/media/saurabh-kumar-maurya/D43C3FD33C3FAEFC/Agentic%20AI/Antigravity/frontend/vercel.json), replace `YOUR_BACKEND_SERVICE.onrender.com` with your active Render web service URL.

---

## 6. Probes & Health Checks
- **Liveness Probe**: `GET /health` (Render Health Check Path). Returns 200 `{"status": "ok"}` quickly without database or storage overhead.
- **Readiness Probe**: `GET /ready`. Performs deep verification of PostgreSQL connectivity and Backblaze B2 bucket access.
