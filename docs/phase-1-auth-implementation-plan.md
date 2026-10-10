# Implementation Plan — Public Launch Phase 1
## Authentication, Authorization & Multi-User Data Isolation

### 1. Resource & Route Protection Dependency Map

Every API route under `/api/v1` (with the explicit exception of system health probes and auth endpoints) requires an authenticated active user and strict ownership verification:

| Route Path | Method | Resource Type | Ownership Check Rule | Unauthenticated Status | Unauthorized Status |
|---|---|---|---|---|---|
| `/api/v1/auth/register` | POST | Auth | Public endpoint (rate-limited) | 200/201 | N/A |
| `/api/v1/auth/login` | POST | Auth | Public endpoint (rate-limited, session rotation) | 200 | 401 |
| `/api/v1/auth/logout` | POST | Auth | Invalidates active session record & clears cookie | 200 | 200 (idempotent) |
| `/api/v1/auth/me` | GET | User | Current session identity | 401 | N/A |
| `/api/v1/auth/verify-email` | POST | Auth | Validates single-use hash token | 200 | 400 |
| `/api/v1/auth/resend-verification`| POST | Auth | Rate-limited verification email generation | 200 | 401 |
| `/api/v1/auth/forgot-password` | POST | Auth | Generic non-disclosing response, single-use token | 200 | N/A |
| `/api/v1/auth/reset-password` | POST | Auth | Validates token, updates Argon2 hash, revokes sessions | 200 | 400 |
| `/api/v1/datasets/upload` | POST | Dataset | Creates dataset with `owner_id = current_user.id` | 401 | 404 (if target dataset not owned) |
| `/api/v1/datasets` | GET | Dataset | Filters `Dataset.owner_id == current_user.id` | 401 | Empty list |
| `/api/v1/datasets/{id}` | GET | Dataset | Verifies `Dataset.owner_id == current_user.id` | 401 | 404 |
| `/api/v1/datasets/{id}/versions/{v}/preview` | GET | Version | Verifies `Dataset.owner_id == current_user.id` | 401 | 404 |
| `/api/v1/datasets/{id}/versions/{v}/analyze` | POST | Analysis | Verifies `Dataset.owner_id == current_user.id` | 401 | 404 |
| `/api/v1/datasets/{id}/analyses` | GET | Analysis | Verifies `Dataset.owner_id == current_user.id` | 401 | 404 |
| `/api/v1/datasets/{id}/versions/{v}/analyses/latest` | GET | Analysis | Verifies `Dataset.owner_id == current_user.id` | 401 | 404 |
| `/api/v1/analyses/{run_id}` | GET | Analysis | Joins `DatasetVersion` & `Dataset`; checks owner | 401 | 404 |
| `/api/v1/analyses/{run_id}/results`| GET | Analysis | Joins `DatasetVersion` & `Dataset`; checks owner | 401 | 404 |
| `/api/v1/analyses/{run_id}/issues` | GET | Analysis | Joins `DatasetVersion` & `Dataset`; checks owner | 401 | 404 |
| `/api/v1/overview/stats` | GET | Overview | User-scoped metrics for `current_user.id` only | 401 | N/A |
| `/api/v1/findings/{id}/explain` | POST | Finding/AI | Joins finding $\to$ run $\to$ version $\to$ dataset; checks owner | 401 | 404 |
| `/api/v1/analyses/{run_id}/generate-ai-plan` | POST | AI Plan | Joins run $\to$ version $\to$ dataset; checks owner | 401 | 404 |
| `/api/v1/analyses/{run_id}/ai-plan`| GET | AI Plan | Joins run $\to$ version $\to$ dataset; checks owner | 401 | 404 |
| `/api/v1/analyses/{run_id}/remediations/apply` | POST | Remediation | Checks owner; sets `approved_by = current_user.email` | 401 | 404 |
| `/api/v1/remediations/{id}` | GET | Remediation | Joins execution $\to$ run $\to$ dataset; checks owner | 401 | 404 |
| `/api/v1/datasets/{id}/remediations` | GET | Remediation | Verifies `Dataset.owner_id == current_user.id` | 401 | 404 |
| `/api/v1/datasets/{id}/compare-versions` | GET | Comparison | Verifies `Dataset.owner_id == current_user.id` | 401 | 404 |
| `/health` & `/api/v1/health` | GET | System | Unauthenticated liveness probe | 200 | N/A |

---

### 2. Database Schema & Migration Strategy

1. **New Tables:**
   - `users`: `id` (UUID), `email` (string 255, unique, index), `hashed_password` (string 255, Argon2id), `is_active` (bool), `is_verified` (bool), `role` (string 32), `created_at`, `updated_at`.
   - `user_sessions`: `id` (UUID), `user_id` (UUID, FK users.id CASCADE), `session_token_hash` (string 64, unique, index), `expires_at`, `created_at`, `last_active_at`, `ip_address`, `user_agent`.
   - `email_verification_tokens`: `id` (UUID), `user_id` (UUID, FK users.id CASCADE), `token_hash` (string 64, unique, index), `expires_at`, `created_at`, `used_at`.
   - `password_reset_tokens`: `id` (UUID), `user_id` (UUID, FK users.id CASCADE), `token_hash` (string 64, unique, index), `expires_at`, `created_at`, `used_at`.

2. **Dataset Table Modification:**
   - Add `owner_id`: UUID nullable foreign key to `users.id` (ondelete="SET NULL").
   - Existing datasets remain with `owner_id = NULL`.
   - Default-deny ownership filter ensures legacy unowned datasets are hidden from ordinary users.

3. **Alembic Migration:**
   - `0005_create_auth_and_user_tables.py` chaining from `0004_create_remediation_tables`.

---

### 3. Session Security & Cookie Handling

- **Cookie name:** `dd_session`.
- **Attributes:** `HttpOnly=True`, `SameSite="lax"`, `Secure` (based on `settings.environment == "production"` or `COOKIE_SECURE`).
- **Path:** `/`.
- **Max-Age:** 7 days (configurable via `SESSION_MAX_AGE_SECONDS`).
- **CSRF Defense:** Cookie `dd_csrf` issued on session creation with `HttpOnly=False, SameSite="lax"`; state-changing API requests check matching `X-CSRF-Token` header, or verify Origin/Referer headers.
- **Session Lifecycle:**
  - Token generated with `secrets.token_urlsafe(32)`.
  - Database stores only SHA-256 hash `hashlib.sha256(token.encode()).hexdigest()`.
  - On login: session rotated (new token generated, old sessions cleaned up).
  - On logout: session deleted from database and cookie cleared with `Max-Age=0`.
  - On password reset: all active sessions for the user revoked.

---

### 4. Email Delivery Abstraction

- Abstract `EmailService` with methods: `send_verification_email(email, token, user)` and `send_password_reset_email(email, token, user)`.
- `MockEmailService`: records sent emails in memory for tests and logs tokens to console in dev mode.
- `SMTPEmailService`: configurable via standard SMTP environment variables (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS`, `EMAIL_FROM`).

---

### 5. Rate Limiting & Abuse Prevention

- In-memory sliding-window limiter `app/core/rate_limit.py`:
  - `auth_login`: 5 attempts per 5 minutes per IP.
  - `auth_register`: 5 registrations per hour per IP.
  - `auth_forgot_password`: 3 requests per 15 minutes per IP.
  - `dataset_upload`: 10 uploads per hour per user.
  - `analysis_trigger`: maximum 2 concurrent running analyses per user.

---

### 6. Frontend Authentication Architecture

1. `AuthContext.tsx`:
   - State: `user: User | null`, `isAuthenticated: boolean`, `isLoading: boolean`.
   - Methods: `login()`, `register()`, `logout()`, `verifyEmail()`, `forgotPassword()`, `resetPassword()`.
   - On app mount: calls `GET /api/v1/auth/me`. If successful, sets `user` and `isAuthenticated = true`. If 401, sets `user = null`.
2. `api.ts`:
   - Axios instance configured with `withCredentials: true`.
   - Interceptor: catches 401 on protected requests and triggers logout/redirect.
3. Auth Pages:
   - `LoginPage.tsx` (`/login`): Email/password form, links to register/forgot password.
   - `RegisterPage.tsx` (`/register`): Name/email/password with strength check.
   - `VerifyEmailPage.tsx` (`/verify-email`): Accepts token from query parameter and shows success/failure.
   - `ForgotPasswordPage.tsx` (`/forgot-password`): Request reset link.
   - `ResetPasswordPage.tsx` (`/reset-password`): Set new password with token.
4. Protected Route:
   - `ProtectedRoute.tsx`: checks `isAuthenticated`. While `isLoading`, displays `LoadingSpinner`. If not authenticated, redirects to `/login` with return URL.
5. Navigation & Shell:
   - `Header.tsx` & `Sidebar.tsx`: display user email, verified status, and logout button.

---

### 7. Regression & Security Test Strategy

1. **Authentication Tests (`tests/test_auth_service.py` & `tests/test_auth_api.py`):**
   - User registration (valid, duplicate, weak password, invalid email).
   - Login (valid, invalid password, nonexistent user, unverified/inactive accounts).
   - Logout (revocation in DB, cookie clear).
   - Current user (`/me`).
   - Email verification (valid token, expired token, token reuse).
   - Password reset (request, valid reset, invalid token, token reuse, session revocation).
   - Argon2id hash verification.
2. **Multi-User Isolation Tests (`tests/test_multi_user_isolation.py`):**
   - User A uploads dataset, runs analysis, generates AI plan, applies remediation.
   - User B attempts to access:
     - `GET /datasets` -> User A's dataset omitted.
     - `GET /datasets/{id}` -> 404.
     - `GET /datasets/{id}/versions/{v}/preview` -> 404.
     - `POST /datasets/{id}/versions/{v}/analyze` -> 404.
     - `GET /analyses/{run_id}` -> 404.
     - `GET /analyses/{run_id}/issues` -> 404.
     - `GET /analyses/{run_id}/ai-plan` -> 404.
     - `POST /analyses/{run_id}/remediations/apply` -> 404.
     - `GET /remediations/{exec_id}` -> 404.
     - `GET /datasets/{id}/compare-versions` -> 404.
     - `GET /overview/stats` -> User B sees only their own statistics (0 datasets/issues).
3. **Frontend Regression Tests:**
   - Auth pages render, login form submits, logout redirects.
   - Protected routes enforce authentication.
   - All existing 44 frontend tests pass.
