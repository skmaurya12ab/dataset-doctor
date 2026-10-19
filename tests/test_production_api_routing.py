"""Tests for Phase 3B2: Production API routing, CORS, trusted proxies, cookie security, and CSRF compatibility."""

import logging
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_storage_service
from app.core.config import Settings, get_settings
from app.core.security import extract_client_ip
from app.main import create_application
from app.services.file_storage import FileStorageService


@pytest.mark.asyncio
async def test_production_cors_configuration() -> None:
    """Verify CORS handling in production: exact origins allowed, wildcards rejected."""
    # 1. Exact origins allowed with credentials
    prod_settings = Settings(
        environment="production",
        allowed_origins="https://my-app.vercel.app,https://custom.domain.com",
    )
    assert prod_settings.parsed_allowed_origins == [
        "https://my-app.vercel.app",
        "https://custom.domain.com",
    ]

    # 2. Wildcard '*' with credentials in production is strictly forbidden
    with pytest.raises(ValueError, match="Wildcard origin '\\*' is forbidden in production"):
        bad_settings = Settings(
            environment="production",
            allowed_origins="https://my-app.vercel.app, *",
        )
        _ = bad_settings.parsed_allowed_origins


@pytest.mark.asyncio
async def test_production_cors_response_headers(
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
) -> None:
    """Verify CORS preflight and headers returned to permitted Vercel origin."""
    prod_settings = Settings(
        environment="production",
        database_url="sqlite+aiosqlite:///:memory:",
        allowed_origins="https://dataset-doctor.vercel.app",
        secret_key="production_secret_key_testing_12345",
    )
    app = create_application(settings=prod_settings)
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # OPTIONS preflight request from permitted origin
        preflight = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://dataset-doctor.vercel.app",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type,X-CSRF-Token",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers.get("access-control-allow-origin") == "https://dataset-doctor.vercel.app"
        assert preflight.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_trusted_proxies_security() -> None:
    """Verify that wildcard trusted proxies are rejected and spoofed X-Forwarded-For is ignored."""
    # 1. Wildcard proxy rejection in production
    with pytest.raises(ValueError, match="Insecure trusted proxy configuration"):
        bad_proxy_settings = Settings(
            environment="production",
            trusted_proxies="0.0.0.0/0",
        )
        _ = bad_proxy_settings.parsed_trusted_proxies

    with pytest.raises(ValueError, match="Insecure trusted proxy configuration"):
        bad_proxy_settings2 = Settings(
            environment="production",
            trusted_proxies="*",
        )
        _ = bad_proxy_settings2.parsed_trusted_proxies

    # 2. Client IP extraction ignores X-Forwarded-For when direct peer is untrusted
    class MockRequest:
        def __init__(self, host: str, headers: dict[str, str]):
            self.client = type("Client", (), {"host": host})()
            self.headers = headers

    # Untrusted direct peer connecting directly (e.g. attacker)
    untrusted_req = MockRequest(
        host="198.51.100.55",
        headers={"X-Forwarded-For": "203.0.113.1, 10.0.0.1"},
    )
    # Must return direct host 198.51.100.55, NOT the spoofed 203.0.113.1
    extracted = extract_client_ip(untrusted_req, trusted_proxies=["127.0.0.1", "::1"])
    assert extracted == "198.51.100.55"

    # Trusted proxy networks are matched as IP ranges, and trusted hops are
    # skipped from the right so a client-supplied leftmost value cannot win.
    trusted_req = MockRequest(
        host="10.20.1.5",
        headers={"X-Forwarded-For": "198.51.100.77, 203.0.113.8, 10.20.2.9"},
    )
    extracted_trusted = extract_client_ip(trusted_req, trusted_proxies=["10.20.0.0/16"])
    assert extracted_trusted == "203.0.113.8"

    invalid_forwarded = MockRequest(
        host="10.20.1.5",
        headers={"X-Forwarded-For": "198.51.100.77, not-an-ip", "X-Real-IP": "203.0.113.8"},
    )
    assert extract_client_ip(invalid_forwarded, trusted_proxies=["10.20.0.0/16"]) == "10.20.1.5"

    forged_real_ip = MockRequest(
        host="198.51.100.55",
        headers={"X-Real-IP": "203.0.113.8"},
    )
    assert extract_client_ip(forged_real_ip, trusted_proxies=["127.0.0.1/32"]) == "198.51.100.55"


@pytest.mark.asyncio
async def test_cookie_security_attributes_in_production(
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
) -> None:
    """Verify that login sets HttpOnly session cookie, readable CSRF cookie, SameSite=Lax, and Secure=True in production."""
    prod_settings = Settings(
        environment="production",
        database_url="sqlite+aiosqlite:///:memory:",
        allowed_origins="https://dataset-doctor.vercel.app",
        secret_key="production_secret_key_testing_12345",
        _env_file=None,  # Keep local development settings out of this production-default test.
    )
    assert prod_settings.is_cookie_secure is True
    assert prod_settings.cookie_samesite == "lax"

    app = create_application(settings=prod_settings)
    app.dependency_overrides[get_settings] = lambda: prod_settings
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "produser@example.com", "password": "SecurePassword123!"},
        )
        assert reg_resp.status_code == 201

        # Login
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "produser@example.com", "password": "SecurePassword123!"},
        )
        assert login_resp.status_code == 200

        # Verify Set-Cookie headers
        raw_set_cookie_headers = login_resp.headers.get_list("set-cookie")
        assert len(raw_set_cookie_headers) >= 2

        session_cookie_header = next(h for h in raw_set_cookie_headers if "dd_session=" in h)
        csrf_cookie_header = next(h for h in raw_set_cookie_headers if "dd_csrf=" in h)

        # dd_session must be HttpOnly, Secure, SameSite=lax
        assert "httponly" in session_cookie_header.lower()
        assert "secure" in session_cookie_header.lower()
        assert "samesite=lax" in session_cookie_header.lower()

        # dd_csrf must be Secure, SameSite=lax, but NOT HttpOnly (so JavaScript can read and double-submit it)
        assert "httponly" not in csrf_cookie_header.lower()
        assert "secure" in csrf_cookie_header.lower()
        assert "samesite=lax" in csrf_cookie_header.lower()


@pytest.mark.asyncio
async def test_csrf_validation_on_all_state_changing_cookie_routes(
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
) -> None:
    """Verify CSRF enforcement on state-changing endpoints while safe GET routes are exempt."""
    app = create_application()
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register and login
        await client.post(
            "/api/v1/auth/register",
            json={"email": "csrf_guard@example.com", "password": "SecurePassword123!"},
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "csrf_guard@example.com", "password": "SecurePassword123!"},
        )
        assert login_resp.status_code == 200
        csrf_token = login_resp.json()["csrf_token"]
        session_cookie = login_resp.cookies.get("dd_session")

        # 2. Safe GET request (GET /api/v1/auth/me) passes with cookie without X-CSRF-Token header
        me_resp = await client.get(
            "/api/v1/auth/me",
            cookies={"dd_session": session_cookie, "dd_csrf": csrf_token},
        )
        assert me_resp.status_code == 200

        # 3. State-changing POST /api/v1/datasets/upload without CSRF header is rejected (403)
        upload_bad = await client.post(
            "/api/v1/datasets/upload",
            cookies={"dd_session": session_cookie, "dd_csrf": csrf_token},
            files={"file": ("test.csv", b"a,b\n1,2\n", "text/csv")},
            data={"name": "Bad CSRF Dataset"},
        )
        assert upload_bad.status_code == 403
        assert "CSRF token" in upload_bad.json()["detail"]

        # 4. State-changing POST /api/v1/datasets/upload with matching CSRF header succeeds
        upload_good = await client.post(
            "/api/v1/datasets/upload",
            cookies={"dd_session": session_cookie, "dd_csrf": csrf_token},
            headers={"X-CSRF-Token": csrf_token},
            files={"file": ("test.csv", b"a,b\n1,2\n", "text/csv")},
            data={"name": "Good CSRF Dataset"},
        )
        assert upload_good.status_code == 201


@pytest.mark.asyncio
async def test_proxied_authenticated_multi_user_isolation(
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
) -> None:
    """Verify tenant isolation: User 1 cannot access or preview User 2's dataset."""
    app = create_application()
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register User 1 and User 2
        await client.post(
            "/api/v1/auth/register",
            json={"email": "user1_iso@example.com", "password": "Password123!"},
        )
        l1 = await client.post(
            "/api/v1/auth/login",
            json={"email": "user1_iso@example.com", "password": "Password123!"},
        )
        s1 = l1.cookies.get("dd_session")
        c1 = l1.json()["csrf_token"]

        await client.post(
            "/api/v1/auth/register",
            json={"email": "user2_iso@example.com", "password": "Password123!"},
        )
        l2 = await client.post(
            "/api/v1/auth/login",
            json={"email": "user2_iso@example.com", "password": "Password123!"},
        )
        s2 = l2.cookies.get("dd_session")
        c2 = l2.json()["csrf_token"]

        # User 1 uploads a dataset
        csv_data = b"col1,col2\n10,20\n30,40\n"
        up_resp = await client.post(
            "/api/v1/datasets/upload",
            cookies={"dd_session": s1, "dd_csrf": c1},
            headers={"X-CSRF-Token": c1},
            files={"file": ("data.csv", csv_data, "text/csv")},
            data={"name": "User 1 Dataset"},
        )
        assert up_resp.status_code == 201
        dataset_id = up_resp.json()["dataset_id"]

        # User 2 attempts to get User 1's dataset detail -> must return 404
        bad_get = await client.get(
            f"/api/v1/datasets/{dataset_id}",
            cookies={"dd_session": s2, "dd_csrf": c2},
        )
        assert bad_get.status_code == 404

        # User 2 attempts to get User 1's preview -> must return 404
        bad_prev = await client.get(
            f"/api/v1/datasets/{dataset_id}/versions/1/preview",
            cookies={"dd_session": s2, "dd_csrf": c2},
        )
        assert bad_prev.status_code == 404

        # User 1 can preview their own dataset
        good_prev = await client.get(
            f"/api/v1/datasets/{dataset_id}/versions/1/preview",
            cookies={"dd_session": s1, "dd_csrf": c1},
        )
        assert good_prev.status_code == 200
        data = good_prev.json()
        assert data["total_rows"] == 2
        assert data["columns"] == ["col1", "col2"]


@pytest.mark.asyncio
async def test_health_and_readiness_probes(
    test_settings: Settings,
    test_storage: FileStorageService,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Both readiness paths report storage failures; liveness does not probe storage."""
    app = create_application()

    class ReadinessDatabase:
        async def execute(self, _statement):
            return None

    async def get_readiness_database() -> ReadinessDatabase:
        return ReadinessDatabase()

    async def get_readiness_settings() -> Settings:
        return test_settings

    app.dependency_overrides[get_db] = get_readiness_database
    app.dependency_overrides[get_settings] = get_readiness_settings

    storage_checks = []

    async def storage_available() -> bool:
        storage_checks.append(True)
        return True

    monkeypatch.setattr("app.api.deps.get_storage_service", lambda: test_storage)
    monkeypatch.setattr(test_storage, "check_health", storage_available)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for health_path in ("/health", "/api/v1/health"):
            health_resp = await client.get(health_path)
            assert health_resp.status_code == 200
            assert health_resp.json()["status"] == "ok"
        assert storage_checks == []

        for _ in range(3):
            for ready_path in ("/ready", "/api/v1/ready"):
                ready_resp = await client.get(ready_path)
                assert ready_resp.status_code == 200
                ready_data = ready_resp.json()
                assert ready_data["status"] == "ready"
                assert ready_data["checks"]["database"] == "connected"
                assert ready_data["checks"]["storage"] == "available"
        assert len(storage_checks) == 6

        async def storage_unavailable() -> bool:
            return False

        monkeypatch.setattr(test_storage, "check_health", storage_unavailable)
        for ready_path in ("/ready", "/api/v1/ready"):
            failed_ready = await client.get(ready_path)
            assert failed_ready.status_code == 503
            assert failed_ready.json()["status"] == "unready"
            assert failed_ready.json()["checks"]["storage"] == "inaccessible"

        async def storage_error() -> bool:
            raise RuntimeError("provider response included mock-secret-key")

        monkeypatch.setattr(test_storage, "check_health", storage_error)
        with caplog.at_level(logging.ERROR):
            for ready_path in ("/ready", "/api/v1/ready"):
                failed_ready = await client.get(ready_path)
                assert failed_ready.status_code == 503
                assert failed_ready.json()["status"] == "unready"
                assert failed_ready.json()["checks"]["storage"] == "inaccessible"
        assert "mock-secret-key" not in caplog.text


@pytest.mark.asyncio
async def test_production_error_masking(
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
) -> None:
    """Verify that unhandled exceptions in production return generic error messages without stack traces."""
    prod_settings = Settings(
        environment="production",
        database_url="sqlite+aiosqlite:///:memory:",
        secret_key="production_secret_key_testing_12345",
    )
    app = create_application(settings=prod_settings)
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage

    # Add a temporary test route that raises an unhandled exception
    @app.get("/api/v1/test-unhandled-error")
    async def crash_endpoint():
        raise RuntimeError("Database connection string leaked: postgres://user:secret@host/db")

    # ASGITransport with raise_app_exceptions=False tests the HTTP 500 response returned to client
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/test-unhandled-error")
        assert resp.status_code == 500
        assert resp.json() == {"detail": "An internal server error occurred."}
        # Verify secret message was masked
        assert "Database connection string leaked" not in resp.text
