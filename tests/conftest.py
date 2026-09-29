"""Pytest test configuration and shared async fixtures."""

from collections.abc import AsyncGenerator
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.main import create_application
from app.models.base import Base


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Fixture returning application settings configured for isolated testing."""
    return Settings(
        app_name="Dataset Doctor Test",
        app_version="0.1.0-test",
        environment="testing",
        database_url="sqlite+aiosqlite:///:memory:",
        log_level="DEBUG",
        max_worker_threads=2,
    )


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
async def async_client(test_settings: Settings, test_db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Asynchronous HTTP test client bound to the FastAPI application instance."""
    app = create_application()

    # Override dependencies
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db] = lambda: test_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
