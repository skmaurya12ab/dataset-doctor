"""Pytest test configuration and shared async fixtures."""

from collections.abc import AsyncGenerator
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db, get_storage_service
from app.core.config import Settings, get_settings
from app.main import create_application
from app.models import Base
from app.services.file_storage import FileStorageService


@pytest.fixture(scope="session")
def test_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Fixture returning application settings configured for isolated testing."""
    temp_dir = tmp_path_factory.mktemp("test_uploads")
    return Settings(
        app_name="Dataset Doctor Test",
        app_version="0.1.0-test",
        environment="testing",
        database_url="sqlite+aiosqlite:///:memory:",
        upload_dir=temp_dir,
        max_upload_size_mb=10,  # 10 MB for tests
        log_level="DEBUG",
        max_worker_threads=2,
    )


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the test fixtures directory."""
    return Path("tests/fixtures")


@pytest.fixture
def test_storage(test_settings: Settings) -> FileStorageService:
    """File storage service bound to the test upload directory."""
    return FileStorageService(base_dir=test_settings.upload_dir)


@pytest.fixture
async def test_db_session(test_settings: Settings) -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated in-memory SQLite async session for testing database components."""
    engine = create_async_engine(test_settings.database_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def async_client(
    test_settings: Settings,
    test_db_session: AsyncSession,
    test_storage: FileStorageService,
) -> AsyncGenerator[AsyncClient, None]:
    """Asynchronous HTTP test client bound to the FastAPI application instance."""
    app = create_application()

    # Override dependencies
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_storage_service] = lambda: test_storage

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
