# Dataset Doctor — Production Deployment Guide

## Deployment status

This guide describes the intended deployment; no hosting project, cloud resource, relay, or public deployment has been created or verified. Local tests do not prove external delivery, storage, database, or deployment behavior.

## Legacy Docker Compose path

The retained docker-compose.prod.yml is a legacy reference and is unsupported for the current public production architecture. Use the Vercel + Render + hosted PostgreSQL + Backblaze B2 + Google Apps Script topology in this guide. The legacy file conflicts with current production validation: it trusts the non-IP name proxy, defaults email verification off and omits EMAIL_PROVIDER (which defaults to mock), and connects to a stock PostgreSQL container without TLS while production connections require hostname-verified TLS. It also probes /ready every 15 seconds, although /ready is intended for deeper readiness checks rather than frequent liveness probes. Do not use that Compose file for production without a separately reviewed configuration update. The root docker-compose.yml quickstart is for local development only.

## Recommended topology

    Browser
      └── Vercel static React/Vite frontend
            └── same-origin /api/v1 rewrite
                  └── Render FastAPI service (one instance)
                        ├── hosted PostgreSQL over verified TLS
                        ├── private Backblaze B2 bucket through S3 API
                        └── Google Apps Script HTTPS email relay

The backend uses an in-process analysis worker pool. Run one backend instance unless the job runner is moved to a distributed worker system. Render's ephemeral filesystem is staging/cache only; use B2 for persistent dataset objects.

### Vercel frontend

Set the Vercel project root to frontend. Build with npm run build and publish dist. Keep VITE_API_BASE_URL unset so the browser uses the same-origin /api/v1 client path. The API rewrite in frontend/vercel.json currently contains a conspicuous placeholder host. After a Render service exists, replace only that destination's host with the exact HTTPS service URL shown by Render, retaining /api/:path*. Do not deploy while the placeholder remains.

The ordered SPA rewrite sends remaining paths to /, which is Vercel's clean-URL form of the Vite SPA entrypoint. This supports direct navigation and refresh on /login, /register, /verify-email, /reset-password, and /remediation. Vercel documents the external rewrite and cleanUrls behavior in its [rewrite documentation](https://vercel.com/docs/routing/rewrites) and [Vite SPA guide](https://vercel.com/docs/frameworks/frontend/vite).

### Render backend

Use the repository Dockerfile. It binds to 0.0.0.0 and honors Render's PORT environment variable; local Docker use falls back to port 8000. The image exposes 8000 as metadata to match that local fallback; Render's supplied PORT controls the runtime listener and health check. Render currently defaults PORT to 10000, but verify the effective value in the service configuration. Set the recurring platform health check path to `/health`; it is a lightweight liveness response and does not contact dependencies. Configure one instance because analysis jobs run in-process. `/ready` is a deeper availability check for PostgreSQL and storage. For S3, each `/ready` request performs a read-only `ListObjectsV2` request limited to one result under `datasets/`; it checks bucket/list access only, not object reads, writes, or deletes, and creates no probe object. Use `/ready` for readiness/manual diagnosis rather than a frequent liveness probe.

### Hosted PostgreSQL

Use a PostgreSQL service reachable from Render and supply the SQLAlchemy async URL using postgresql+asyncpg. Production startup rejects another driver or a missing host. The database engine forces asyncpg TLS mode verify-full and removes sslmode/ssl URL query parameters before engine creation; do not assume a pasted libpq sslmode parameter configures SQLAlchemy's asyncpg connection. The asyncpg TLS behavior is documented in the [asyncpg API reference](https://magicstack.github.io/asyncpg/current/api/index.html).

Run Alembic migrations as a one-off command from the same application release and with the hosted database environment variable supplied explicitly by the hosting job. The command is alembic upgrade head. Do not rely on a developer's local .env file, run migrations automatically during application startup, or point a deployment migration command at the development database. Confirm the resulting revision with alembic current from that same hosted environment.

### Backblaze B2

Select STORAGE_BACKEND=s3, provide the B2 S3 endpoint, bucket, region, and a standard application key restricted to the intended bucket and datasets/ prefix. The minimum capabilities used by this implementation are listFiles, readFiles, writeFiles, and deleteFiles. It does not require listAllBucketNames because readiness no longer calls HeadBucket/ListBuckets. See the [B2 S3-compatible key capabilities](https://www.backblaze.com/docs/cloud-storage-s3-compatible-app-keys) and the detailed [persistent storage guide](persistent-object-storage-guide.md).

### Authentication email

Production requires REQUIRE_EMAIL_VERIFICATION=true, rejects EMAIL_PROVIDER=mock, and validates the selected provider during startup. Configure either Apps Script or SMTP fully. Apps Script requires an HTTPS APPLICATION_BASE_URL, an exact deployed Google /exec URL, and a random HMAC secret of at least 32 bytes. SMTP requires a host, STARTTLS, a syntactically valid sender, and paired username/password if the relay authenticates. Provider-side sender authorization and actual inbox delivery remain manual checks. See [Authentication Email Delivery](email-delivery.md).

## Environment variables

These names come from app/core/config.py and the provider implementations. They are configuration names, not values to copy into source control.

### Render non-secret configuration

- APP_NAME, ENVIRONMENT=production, DEBUG=false, LOG_LEVEL, ENABLE_API_DOCS=false
- DATABASE_URL (the connection string itself is secret)
- PORT is supplied by Render, not by application Settings; the Dockerfile honors it.
- STORAGE_BACKEND=s3, UPLOAD_DIR, MAX_UPLOAD_SIZE_MB
- S3_ENDPOINT_URL, S3_BUCKET_NAME, S3_REGION, S3_SIGNATURE_VERSION
- OPENAI_MODEL, OPENAI_TIMEOUT_SECONDS, OPENAI_MAX_RETRIES, OPENAI_RETRY_BACKOFF, OPENAI_MAX_INPUT_TOKENS, OPENAI_MAX_OUTPUT_TOKENS
- SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS, COOKIE_SECURE=true, COOKIE_SAMESITE=lax
- REQUIRE_EMAIL_VERIFICATION=true, EMAIL_PROVIDER, APPLICATION_BASE_URL, ALLOWED_ORIGINS, TRUSTED_PROXIES
- APPS_SCRIPT_URL when Apps Script is selected
- SMTP_HOST, SMTP_PORT, SMTP_TLS, EMAIL_FROM when SMTP is selected
- EMAIL_DAILY_SEND_CAP, EMAIL_RECIPIENT_COOLDOWN_SECONDS, APPS_SCRIPT_TIMEOUT_SECONDS
- MAX_WORKER_THREADS, MAX_DATASETS_PER_USER, MAX_CUMULATIVE_STORAGE_MB_PER_USER, MAX_CONCURRENT_ANALYSIS_JOBS_PER_USER
- RATE_LIMIT_ANALYSIS_TRIGGERS_PER_MINUTE, RATE_LIMIT_AI_EXPLANATIONS_PER_MINUTE, RATE_LIMIT_AI_PLANS_PER_MINUTE, RATE_LIMIT_REMEDIATIONS_PER_MINUTE

### Render secrets

- DATABASE_URL
- S3_ACCESS_KEY and S3_SECRET_KEY (the settings also accept the documented AWS-compatible aliases)
- APPS_SCRIPT_HMAC_SECRET, or SMTP_PASSWORD and SMTP_USER when SMTP authentication is selected
- OPENAI_API_KEY only when genuine OpenAI-generated advice is intended

When EMAIL_PROVIDER=apps_script, also set APPS_SCRIPT_URL. When EMAIL_PROVIDER=smtp, configure SMTP_HOST, SMTP_PORT, SMTP_USER and SMTP_PASSWORD together when authentication is needed, SMTP_TLS=true, and EMAIL_FROM to a sender authorized by that SMTP service. The application has no SECRET_KEY or COOKIE_DOMAIN setting; do not configure those as though the code consumes them. EMAIL_PROVIDER=mock only belongs in development/testing. If OPENAI_API_KEY is absent, the AI factory uses a clearly labeled mock sample provider; this is not genuine AI output.

### Vercel configuration

No VITE_API_BASE_URL is needed for the same-origin design. The only pending routing change is the explicit Render hostname replacement in frontend/vercel.json after Render supplies the real URL. Do not put backend-only keys in Vercel frontend environment variables.

## Cookie, CSRF, CORS, and proxy settings

Production session and CSRF cookies use Secure and SameSite=Lax by default; the session cookie is HttpOnly and the double-submit CSRF cookie is readable by the frontend client. Cookie-authenticated state-changing routes require matching CSRF cookie/header values, including logout. Login, registration, email verification, password-reset, and verification-resend flows retain their narrow initial-authentication exemptions.

Set ALLOWED_ORIGINS to the exact frontend origin even with a same-origin rewrite. Do not use a wildcard with credentials. TRUSTED_PROXIES accepts explicit IP addresses or CIDR ranges and rejects all-address networks. The app trusts forwarded client IPs only when the direct peer matches that list, validates forwarded values, and walks the chain from the right. Vercel documents X-Forwarded-For and X-Real-IP forwarding, but the actual peer seen inside Render and any intermediate proxy behavior have not been verified. Do not guess a proxy range or trust all proxies. Verify the deployed request path first; if no narrow trustworthy peer range is available, leave forwarded headers untrusted and understand that IP rate limits may group traffic by the observed peer.

## Health checks and manual deployment sequence

1. Create/configure the Vercel, Render, hosted PostgreSQL, B2, and email accounts manually; obtain consent and authorize the sender.
2. Set production variables and secrets in the correct service. Keep the Render service single-instance.
3. Confirm the actual Render PORT and public HTTPS service URL. Update the Vercel rewrite placeholder to that exact URL, set the Vercel project root/build settings, and leave VITE_API_BASE_URL unset.
4. Run alembic upgrade head once against the intended hosted database using that release's runtime configuration.
5. Deploy the backend and frontend.
6. Check /health and /ready. Then test authenticated registration/login, CSRF-protected logout, upload/download/delete, direct SPA routes, and both verification and password-reset messages using controlled accounts and data.
7. Verify proxy peer/forwarded headers, TLS, cookie attributes, B2 permissions, inbox delivery, and sender identity from live service logs and browser/network behavior.

These steps have not been run. Free-plan eligibility, quotas, sleeping behavior, provider approval, and charges depend on current account terms and usage and are not guaranteed here.

## Retained self-hosted alternative

A separately operated single-host deployment can terminate TLS at Nginx and run one FastAPI instance with a persistent UPLOAD_DIR and PostgreSQL. That is an alternative topology, not the recommended Vercel/Render/B2 arrangement. The Nginx host, certificate automation, persistent disk, backups, SMTP relay, and proxy trust configuration must be supplied and verified by its operator.
