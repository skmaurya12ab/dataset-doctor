# Authentication Email Delivery

Dataset Doctor sends registration-verification and password-reset messages through the existing `BaseEmailService` interface. `EMAIL_PROVIDER` explicitly selects `mock`, `smtp`, or `apps_script`; production rejects `mock` and fails startup if the selected real provider is incomplete. Verification tokens and reset tokens remain random, hashed in PostgreSQL, time-limited, and single-use. Messages contain links to the existing frontend routes: `/verify-email?token=...` and `/reset-password?token=...`.

Production startup also requires REQUIRE_EMAIL_VERIFICATION=true; mock email remains development/testing only.

For SMTP, the backend requires SMTP_HOST, SMTP_TLS=true, a syntactically valid EMAIL_FROM, and SMTP_USER/SMTP_PASSWORD either both present or both absent. Configure a sender accepted by the selected relay; the code cannot prove sender ownership or inbox placement. For Apps Script, the backend requires an HTTPS application origin, a deployed Google /exec URL, and an HMAC secret of at least 32 bytes. Use a randomly generated secret and never expose it to frontend variables. These checks validate local configuration only; provider account authorization and live delivery still need manual verification.

## Provider and request limits

| Setting | Default | Behavior |
| --- | ---: | --- |
| `EMAIL_DAILY_SEND_CAP` | 20 | PostgreSQL-backed cap on reserved delivery attempts per UTC day; failed/uncertain attempts count. Maximum configurable value is 80. |
| `EMAIL_RECIPIENT_COOLDOWN_SECONDS` | 900 | PostgreSQL-backed cooldown per user account and message type. |
| `APPS_SCRIPT_TIMEOUT_SECONDS` | 12 | Maximum time the backend request awaits the relay (maximum 30 seconds). |

The auth endpoints also retain their client-IP rate limits. The PostgreSQL counter row is locked when reserving a send slot; recipient history stores only the account UUID, message category, and timestamp, not the recipient address or action token. This relies on the app's current single-backend deployment model and PostgreSQL row locking. A local SQLite database does not provide equivalent cross-process `SELECT FOR UPDATE` behavior and is for development/testing only. Reservations are committed before the provider call, so failures consume capacity until the UTC counter resets. No distributed queue/outbox is introduced.

The Apps Script relay independently enforces a low daily cap (default 20, maximum 80), `MailApp.getRemainingDailyQuota()`, and a recipient/message-type cooldown under a script lock. Google's current [Apps Script quota table](https://developers.google.com/apps-script/guides/services/quotas) limits a Script Properties value to 9 KB and a property store to 500 KB. The relay stores one small record per nonce and request ID, prunes expired nonce/idempotency/recipient/daily entries, and limits sending to at most 80 attempts per UTC day. Keep the cap low and inspect Apps Script executions and quota before a demonstration.

## Local development and tests

Use `EMAIL_PROVIDER=mock` in development and tests. Mock messages are available only through the in-memory `MockEmailService.sent_emails` test interface; the provider does not log token values, links, message bodies, or recipient addresses. Do not select mock in production.

## Google Apps Script relay setup

No Google project or web app is included or deployed by this change. A maintainer must perform these steps manually before selecting `apps_script`:

1. Use a Google account whose owner consents to send the project's authentication emails. Create a standalone Apps Script project and copy `integrations/apps-script-email-relay/Code.gs` and `appsscript.json` into it.
2. Run a harmless authorization path in the Apps Script editor and grant the requested `script.send_mail` scope. Deploy a **Web app** with **Execute as: Me** (the account that will send) and access for **Anyone**, including anonymous visitors. Google documents the execute-as identity and the `doPost` web-app model in its [web app guide](https://developers.google.com/apps-script/guides/web). The manifest names `ANYONE_ANONYMOUS` as a supported access value, but account, organization, or administrator policies can hide or prohibit anonymous access. Treat availability of this deployment setting as a hard prerequisite; do not replace it with a publicly accessible unauthenticated sender if the account will not allow it.
3. In **Project Settings → Script Properties**, set `HMAC_SECRET` to a newly generated high-entropy random string of at least 32 bytes, `ACTION_BASE_URL` to the application's HTTPS origin (for example, `https://project.example`), and optionally `DAILY_SEND_CAP`, `RECIPIENT_COOLDOWN_SECONDS`, `TIMESTAMP_TOLERANCE_SECONDS`, `NONCE_TTL_SECONDS`, and `IDEMPOTENCY_TTL_SECONDS`. Do not put these values in code, a URL, a checked-in file, or logs.
4. Put the *same* `HMAC_SECRET` in the backend's secret environment as `APPS_SCRIPT_HMAC_SECRET`. Set `EMAIL_PROVIDER=apps_script`, `APPS_SCRIPT_URL` to the deployed URL ending in `/exec`, `APPLICATION_BASE_URL` to the same HTTPS origin as `ACTION_BASE_URL`, and `REQUIRE_EMAIL_VERIFICATION=true`. Keep the backend secret server-side; do not use a `VITE_` prefix or expose it through frontend configuration.
5. Keep the backend and relay caps aligned. `EMAIL_DAILY_SEND_CAP` is capped at 80 in the backend; set the script property to the same or a lower value. Google currently documents a MailApp recipient quota of 100 per day for consumer Gmail accounts and 1,500 for Workspace accounts, per user, with quotas subject to change; the project cap of 20 is intentionally conservative. Check the current [Apps Script quotas](https://developers.google.com/apps-script/guides/services/quotas) before any live use.
6. Send a manual smoke-test registration to an address you control, open the received link, verify the account, request a password reset, and complete it. Confirm the visible sender identity is the account that deployed the script. Check the Apps Script execution history and mail quota without copying token-bearing request data into logs.

For an already deployed relay, update `Code.gs` in the same Apps Script project, save it, then use **Deploy → Manage deployments → Edit** and deploy a new version of the existing web app. Keep the deployment URL and Script Properties unchanged. Updating the tracked source does not update a live deployment by itself.

`MailApp` uses the deployer's sending authority. The script accepts only a validated recipient, the two fixed message types, and an HTTPS action link on the configured application origin; caller-controlled HTML and sender identity are not accepted. A display name may be set to “Dataset Doctor,” but the actual sending account remains Google-controlled. The official [MailApp reference](https://developers.google.com/apps-script/reference/mail/mail-app) describes this sender behavior and quota query.

## Backend-to-relay protocol

The web-app event object exposes POST body data, not a documented arbitrary request-header map, so the backend signs the JSON body rather than relying on an Authorization header. The signed v1 UTF-8 representation is exactly these newline-separated values, in this order: the literal `dataset-doctor-email-relay-v1`, schema version, integer timestamp, random 32-hex nonce, unique request UUID, message type, normalized recipient, and complete action URL. Both implementations validate CR/LF-free fields and use HMAC-SHA-256 hex. The script compares signatures without early character exit and accepts timestamps only within the configured window (default five minutes).

The nonce is reserved under `LockService`; the request UUID stores a hash of the business payload and a state. Same UUID/same payload returns the stored sent result or an uncertain/failure result without sending again. Same UUID/different payload is rejected. A timeout after `MailApp.sendEmail` may leave state as `processing`; retries fail closed rather than risking a second sensitive email. The backend stops awaiting at its configured deadline, though an already-running worker request may finish in the background. A new user-initiated request after the cooldown can create a new action token. The backend does not automatically retry a timeout.

The request body is bounded to 8 KiB. The relay rejects unsupported types, malformed addresses, links to other origins/routes, bad signatures, stale timestamps, nonce replay, recipient cooldowns, and quota exhaustion. The standard Apps Script Content Service redirects its response to a one-time `script.googleusercontent.com` URL; the Python HTTP client follows this redirect as Google documents in its [Content Service guide](https://developers.google.com/apps-script/guides/content).

The planned Render Free backend cannot send outbound SMTP traffic on ports 25, 465, or 587; this provider uses HTTPS instead. Render documents external API calls as service-initiated traffic, but the particular Apps Script web-app route is not live-tested by this repository change and must pass the manual smoke test before it is considered operational. See [Render's free-service limits](https://render.com/docs/free).

This HMAC scheme protects sending against forged requests while the shared key remains secret. It cannot prevent denial-of-service attempts against an anonymously reachable Apps Script URL: invalid requests still consume some web-app execution capacity. Google account policy may also prevent anonymous web-app deployment. Keep the endpoint secret out of logs, use the modest cap, monitor executions, and disable the provider if abuse occurs. A separate relay URL is not treated as authentication.

Relay diagnostics are deliberately value-free. The backend logs only a fixed relay outcome category such as `sent`, `unauthorized`, `quota_exhausted`, `timeout`, `http_error`, `non_json_response`, or `unexpected_status`; it never logs the response body. Apps Script execution logs emit `DD_RELAY_STAGE` records containing only a fixed stage name, elapsed milliseconds, and, on the response stage, a whitelisted status category. Use the last stage and backend outcome to narrow failures without copying request data or Script Properties. `sent` means MailApp returned successfully and the relay persisted its sent state; it does not confirm inbox placement. `delivery_unknown` remains non-success and is not automatically retried.

## Delivery failure, privacy, and retry behavior

Email and database writes cannot form one atomic transaction. The user and token are committed first, then a bounded delivery reservation is committed, then the provider is called. For a failed verification or reset send, the newly created token record is removed and any prior unused token is kept. A registration account remains stored; when verification is required, the API returns a temporary service error and the user can request a new verification message after the cooldown. Resend and password-reset responses remain non-disclosing and do not say that delivery succeeded. Password-reset responses are generic for known and unknown accounts.

Duplicate registration currently intentionally returns a validation error stating that an account already exists; this is an account-enumeration tradeoff retained for the existing UX. Do not reuse that behavior for password-reset requests. Provider logs omit email addresses, action links, tokens, message bodies, HMAC keys, and provider response bodies. Email quota errors and uncertain delivery count against the cooldown and daily cap to prevent retry storms.

For SMTP, server timeouts can leave delivery uncertain because SMTP has no idempotency key; the app makes one dispatch attempt and never retries it automatically. Apps Script additionally records a request ID so a repeated relay call cannot trigger a second send for that ID, but an execution can stop between sending and recording the final status. In either provider, inbox placement, spam filtering, and actual receipt are not confirmed by automated tests.

## Rotation and safe disablement

To rotate the Apps Script key, set a new `HMAC_SECRET` in Script Properties and update `APPS_SCRIPT_HMAC_SECRET` in the backend environment as one coordinated operation; requests fail closed while keys differ. For an overlap-free cutover, briefly disable email actions, update both sides, then re-enable. Revoke the old key by replacing it in Script Properties and removing it from the backend secret store. To disable the relay, stop selecting `apps_script`; select another fully configured provider or leave local/testing explicitly on `mock`. Production startup will reject mock. If no real provider is available, keep `REQUIRE_EMAIL_VERIFICATION=true` deployments stopped rather than silently bypassing verification.

## Future implementation verification

Automated tests cover Python request signing, provider response/timeout handling, URL construction, token failure cleanup, generic reset responses, and database-backed cooldown/cap behavior. The Node test harness exercises the Apps Script source with local service stubs for signature rejection, timestamp expiry, nonce replay, duplicate IDs, changed payloads, quotas, and fixed-template rules. Run `pytest`, `node integrations/apps-script-email-relay/Code.test.mjs`, and the frontend commands recorded in the handoff. These checks are mocked/local only. Before relying on delivery, perform the manual smoke test above; this repository change has not deployed or exercised a real Google account or live inbox.
