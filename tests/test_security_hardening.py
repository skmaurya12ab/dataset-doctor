"""Tests for security hardening: CSRF enforcement, email verification gating, and hashed session storage."""

import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_storage_service
from app.core.config import Settings, get_settings
from app.core.security import hash_token
from app.main import create_application
from app.models.user import User, UserSession
from app.services.file_storage import FileStorageService


@pytest.mark.asyncio
async def test_session_token_storage_security(
    test_settings: Settings,
    test_db_session: AsyncSession,
) -> None:
    """Verify that user sessions store only SHA-256 hashes and never plaintext tokens."""
    from app.services.auth_service import AuthService
    auth_service = AuthService()

    # Create user
    user = User(
        id=uuid.uuid4(),
        email="session_sec@example.com",
        hashed_password="hash",
        is_active=True,
        is_verified=True,
        role="user",
    )
    test_db_session.add(user)
    await test_db_session.commit()

    # Create session
    session_obj, raw_token = await auth_service.create_session(
        db=test_db_session,
        user_id=user.id,
        ip_address="127.0.0.1",
        user_agent="TestAgent",
    )

    # Inspect persisted record in database
    stmt = select(UserSession).where(UserSession.id == session_obj.id)
    persisted = (await test_db_session.execute(stmt)).scalar_one()

    # The persisted value must be the SHA-256 hash
    expected_hash = hash_token(raw_token)
    assert persisted.session_token_hash == expected_hash
    # The raw token must NOT equal the stored hash
    assert raw_token != persisted.session_token_hash
    assert len(persisted.session_token_hash) == 64


@pytest.mark.asyncio
async def test_email_verification_enforcement_policy(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
) -> None:
    """Verify that unverified users are blocked from accessing dataset endpoints when verification is enforced."""
    verification_required_settings = Settings(
        environment="testing",
        database_url="sqlite+aiosqlite:///:memory:",
        upload_dir=test_settings.upload_dir,
        require_email_verification=True,  # Enforcement active
    )

    unverified_user = User(
        id=uuid.uuid4(),
        email="unverified@example.com",
        hashed_password="hash",
        is_active=True,
        is_verified=False,  # Unverified
        role="user",
    )
    test_db_session.add(unverified_user)
    await test_db_session.commit()

    app = create_application()
    app.dependency_overrides[get_settings] = lambda: verification_required_settings
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage
    app.dependency_overrides[get_current_user] = lambda: unverified_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. /auth/me should succeed so user can view status and is_verified: false
        me_resp = await client.get("/api/v1/auth/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["is_verified"] is False

        # 2. Accessing datasets list must be forbidden (403)
        ds_resp = await client.get("/api/v1/datasets")
        assert ds_resp.status_code == 403
        assert "Email verification required" in ds_resp.json()["detail"]

        # 3. Accessing upload must be forbidden (403)
        up_resp = await client.post(
            "/api/v1/datasets/upload",
            files={"file": ("test.csv", b"a,b\n1,2\n", "text/csv")},
        )
        assert up_resp.status_code == 403
        assert "Email verification required" in up_resp.json()["detail"]


@pytest.mark.asyncio
async def test_csrf_protection_on_cookie_authenticated_requests(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
) -> None:
    """Verify that state-changing requests using session cookies require valid double-submit CSRF tokens."""
    app = create_application()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register and login to obtain cookies
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "csrf_test@example.com", "password": "Password123!"},
        )
        assert reg_resp.status_code == 201

        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "csrf_test@example.com", "password": "Password123!"},
        )
        assert login_resp.status_code == 200
        csrf_token = login_resp.json()["csrf_token"]
        session_cookie = login_resp.cookies.get("dd_session")

        # 2. Make state-changing POST without CSRF header (must be rejected with 403)
        bad_req = await client.post(
            "/api/v1/datasets/upload",
            cookies={"dd_session": session_cookie, "dd_csrf": csrf_token},
            files={"file": ("test.csv", b"a,b\n1,2\n", "text/csv")},
            data={"name": "CSRF Attack"},
        )
        assert bad_req.status_code == 403
        assert "CSRF token" in bad_req.json()["detail"]

        # 3. Make state-changing POST with correct CSRF header (must succeed)
        good_req = await client.post(
            "/api/v1/datasets/upload",
            cookies={"dd_session": session_cookie, "dd_csrf": csrf_token},
            headers={"X-CSRF-Token": csrf_token},
            files={"file": ("test.csv", b"a,b\n1,2\n", "text/csv")},
            data={"name": "CSRF Protected"},
        )
        assert good_req.status_code == 201


@pytest.mark.asyncio
async def test_resend_verification_endpoint(
    test_settings: Settings,
    test_db_session: AsyncSession,
) -> None:
    """Verify that requesting resend verification responds gracefully and dispatches token."""
    app = create_application()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db] = lambda: test_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "nonexistent@example.com"},
        )
        assert resp.status_code == 200
        assert "fresh link has been sent" in resp.json()["message"]
