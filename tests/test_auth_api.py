"""API integration tests for authentication, sessions, cookies, CSRF, and rate limiting."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.rate_limit import rate_limiter
from app.models.user import EmailVerificationToken, PasswordResetToken, User


@pytest.mark.asyncio
async def test_register_api_success_and_validation(unauthenticated_async_client: AsyncClient) -> None:
    """Test user self-registration API and validation constraints."""
    client = unauthenticated_async_client

    # 1. Successful registration
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "NewApiUser@Example.com", "password": "StrongPassword123!"},
    )
    assert reg_resp.status_code == 201
    data = reg_resp.json()
    assert data["email"] == "newapiuser@example.com"
    assert data["is_active"] is True
    assert "id" in data

    # 2. Duplicate registration fails cleanly
    dup_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "NEWAPIUSER@EXAMPLE.COM", "password": "StrongPassword123!"},
    )
    assert dup_resp.status_code == 422

    # 3. Short password rejected
    short_pw_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "short"},
    )
    assert short_pw_resp.status_code == 422

    # 4. Invalid email format rejected
    bad_email_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "StrongPassword123!"},
    )
    assert bad_email_resp.status_code == 422


@pytest.mark.asyncio
async def test_login_api_cookie_management(unauthenticated_async_client: AsyncClient) -> None:
    """Test login sets HttpOnly session cookie and csrf cookie."""
    client = unauthenticated_async_client

    # Register user first
    await client.post(
        "/api/v1/auth/register",
        json={"email": "cookieuser@example.com", "password": "ValidPassword123!"},
    )

    # Login
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "cookieuser@example.com", "password": "ValidPassword123!"},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert data["user"]["email"] == "cookieuser@example.com"
    assert "csrf_token" in data

    # Verify cookies
    assert "dd_session" in login_resp.cookies
    assert "dd_csrf" in login_resp.cookies

    # Verify /me endpoint using the cookie
    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "cookieuser@example.com"


@pytest.mark.asyncio
async def test_login_invalid_credentials_generic_response(unauthenticated_async_client: AsyncClient) -> None:
    """Verify login failure provides non-disclosing error response."""
    client = unauthenticated_async_client

    # Nonexistent user
    resp1 = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "SomePassword123!"},
    )
    assert resp1.status_code == 401
    assert "Invalid email address or password" in resp1.json()["detail"]

    # Existent user with bad password
    await client.post(
        "/api/v1/auth/register",
        json={"email": "realuser@example.com", "password": "CorrectPassword123!"},
    )
    resp2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "realuser@example.com", "password": "WrongPassword123!"},
    )
    assert resp2.status_code == 401
    assert "Invalid email address or password" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_logout_invalidates_session_and_clears_cookies(unauthenticated_async_client: AsyncClient) -> None:
    """Verify logout clears session on server and client."""
    client = unauthenticated_async_client

    # Register and login
    await client.post(
        "/api/v1/auth/register",
        json={"email": "logoutuser@example.com", "password": "ValidPassword123!"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": "logoutuser@example.com", "password": "ValidPassword123!"},
    )

    # Validate active
    me_resp1 = await client.get("/api/v1/auth/me")
    assert me_resp1.status_code == 200

    # Logout
    logout_resp = await client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200

    # Validate subsequent request is unauthenticated
    me_resp2 = await client.get("/api/v1/auth/me")
    assert me_resp2.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(unauthenticated_async_client: AsyncClient) -> None:
    """Verify default-deny behavior for anonymous requests on protected endpoints."""
    client = unauthenticated_async_client

    # /auth/me
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    # /datasets
    assert (await client.get("/api/v1/datasets")).status_code == 401

    # /overview/stats
    assert (await client.get("/api/v1/overview/stats")).status_code == 401

    # /analyses/{uuid}
    fake_id = uuid.uuid4()
    assert (await client.get(f"/api/v1/analyses/{fake_id}")).status_code == 401


@pytest.mark.asyncio
async def test_email_verification_flow(
    unauthenticated_async_client: AsyncClient,
    test_db_session: AsyncSession,
) -> None:
    """Test verification token submission via API."""
    client = unauthenticated_async_client
    from sqlalchemy import select
    from app.core.security import generate_token, hash_token

    # Register
    reg_res = await client.post(
        "/api/v1/auth/register",
        json={"email": "verify_api@example.com", "password": "Password123!"},
    )
    user_id = uuid.UUID(reg_res.json()["id"])

    # Overwrite token_hash with known raw token for testing
    raw_token = generate_token(32)
    tok_stmt = select(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id)
    tok = (await test_db_session.execute(tok_stmt)).scalar_one()
    tok.token_hash = hash_token(raw_token)
    await test_db_session.commit()

    # Verify email
    ver_res = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": raw_token},
    )
    assert ver_res.status_code == 200
    assert "verified successfully" in ver_res.json()["message"]


@pytest.mark.asyncio
async def test_forgot_and_reset_password_flow(
    unauthenticated_async_client: AsyncClient,
    test_db_session: AsyncSession,
) -> None:
    """Test forgot password request and completion flow."""
    client = unauthenticated_async_client
    from sqlalchemy import select
    from app.core.security import generate_token, hash_token

    # Register
    await client.post(
        "/api/v1/auth/register",
        json={"email": "reset_api@example.com", "password": "OldPassword123!"},
    )

    # Forgot password request (generic message)
    forgot_res = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "reset_api@example.com"},
    )
    assert forgot_res.status_code == 200
    assert "password reset instructions" in forgot_res.json()["message"]

    # Also returns 200 for nonexistent email (anti-enumeration)
    forgot_fake = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nonexistent_reset@example.com"},
    )
    assert forgot_fake.status_code == 200

    # Overwrite reset token for user to test
    raw_token = generate_token(32)
    user = (await test_db_session.execute(select(User).where(User.email == "reset_api@example.com"))).scalar_one()
    tok = (await test_db_session.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))).scalar_one()
    tok.token_hash = hash_token(raw_token)
    await test_db_session.commit()

    # Reset password
    reset_res = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "BrandNewPassword123!"},
    )
    assert reset_res.status_code == 200

    # Login with new password
    login_new = await client.post(
        "/api/v1/auth/login",
        json={"email": "reset_api@example.com", "password": "BrandNewPassword123!"},
    )
    assert login_new.status_code == 200


@pytest.mark.asyncio
async def test_rate_limiting_enforcement(unauthenticated_async_client: AsyncClient) -> None:
    """Test that abuse prevention rate limiting returns HTTP 429 when threshold exceeded."""
    client = unauthenticated_async_client

    # Login limit is 10 requests per minute
    responses = []
    for _ in range(12):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "ratelimit@example.com", "password": "badpassword"},
        )
        responses.append(resp.status_code)

    assert 429 in responses
    # Confirm Retry-After header
    assert any("Retry-After" in r.headers for r in [resp] if resp.status_code == 429)
