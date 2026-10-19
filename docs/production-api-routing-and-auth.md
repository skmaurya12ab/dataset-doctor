# Production API Routing and Authentication

## Intended request path

The intended browser path is:

    Browser at Vercel origin
      -> /api/v1/... on the same origin
      -> ordered external rewrite in frontend/vercel.json
      -> FastAPI on the actual Render service URL

The frontend Axios client defaults to /api/v1 and sends credentials. Leave VITE_API_BASE_URL unset for this topology. The first rewrite must match /api/:path* and forward it to the Render origin while retaining /api/.... The current destination is an explicit placeholder. After creating the Render service, replace the destination host with the exact URL shown in its dashboard; no hostname is known or verified yet.

The second rewrite sends other paths to /, the cleanUrls-compatible Vite SPA entrypoint. This supports direct visits and refreshes to /login, /register, /verify-email, /reset-password, and /remediation. The API rule must remain first so API responses are not served as the SPA shell. See Vercel's [rewrite guide](https://vercel.com/docs/routing/rewrites) and [Vite SPA guidance](https://vercel.com/docs/frameworks/frontend/vite).

## Browser authentication

The backend stores only hashed server-side session tokens. In production it sets Secure cookies; the session cookie is HttpOnly and the double-submit CSRF cookie is readable by the frontend API client. SameSite defaults to Lax. No COOKIE_DOMAIN setting exists in current Settings, so the browser receives host-only cookies through the same-origin rewrite.

For cookie-authenticated state-changing methods (POST, PUT, PATCH, DELETE), the CSRF cookie and X-CSRF-Token header must match. Logout is protected by the same dependency. The only exemptions are the initial or token-driven auth flows: login, registration, email verification, forgot password, reset password, and resend verification. CORS does not replace CSRF validation.

Set ALLOWED_ORIGINS to the exact frontend origin. Do not use a wildcard with credentials. Same-origin browser calls do not need a cross-origin API base URL, but the backend still needs the expected origin policy for requests forwarded through the platform.

## Trusted proxies and rate limits

TRUSTED_PROXIES contains comma-separated explicit IP addresses or CIDR ranges. The backend only reads X-Forwarded-For when the effective ASGI peer address matches a configured trusted network. It validates every forwarded address and walks right-to-left past trusted proxy hops. It ignores X-Real-IP.

The effective Render peer address and the Vercel-to-Render path are not established by local tests. Do not add a broad network or assume Vercel's public request header proves that the ASGI peer is Vercel. After deployment, inspect the peer observed by the app and confirm how Render forwards headers; only then consider a narrowly scoped trust configuration. If there is no stable narrow peer range, forwarded client IP remains ignored. Account quotas and ownership checks remain separate; IP-based rate limits may share the peer address.

## Upload and timeout verification

The API allows uploads up to MAX_UPLOAD_SIZE_MB and the application uses backend storage. Vercel/Render request-body handling, timeout behavior, cold starts, and maximum practical upload size must be tested on the actual services. Do not infer these limits from local tests or configure a cross-origin VITE_API_BASE_URL as a workaround without reviewing cookie and CSRF behavior.

## Manual live checks

After account setup and deployment, verify:

- Direct browser loads and refreshes for the client routes above.
- Network requests remain under the Vercel origin at /api/v1 and reach the backend.
- Session and CSRF cookies are Secure; the session cookie is HttpOnly; logout without or with an invalid CSRF token fails while the valid token succeeds.
- Allowed origins, effective peer address, forwarded chain, and rate-limit behavior match the deployed path.
- Actual upload/download/delete and health/readiness behavior work with the configured storage and database.

No Vercel/Render project, deployed URL, browser session, or public endpoint has been configured or tested in this hardening phase.
