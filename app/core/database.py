"""Async SQLAlchemy 2.0 database engine and session factory.

IMPORTANT ARCHITECTURAL RULE:
AsyncSession instances are tied to asyncio event loops and are NOT thread-safe.
They must NEVER be shared across worker threads or between concurrent background tasks.
Background analysis jobs running in worker threads must create their own dedicated
sessions or use thread-isolated execution patterns.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import ssl
from typing import Optional
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Global singletons initialized lazily
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def build_database_connection_configuration(
    settings, database_url: str | None = None
) -> tuple[object, dict]:
    """Build the database URL and driver options shared by app and migrations."""
    configured_url = database_url or settings.database_url
    engine_url: object = configured_url
    connect_args: dict = {}

    if settings.is_production:
        settings.validate_database_configuration(configured_url)
        parsed_url = make_url(configured_url)
        query = dict(parsed_url.query)
        # Avoid asyncpg's verify-full shorthand, which can rely on a per-user
        # ~/.postgresql/root.crt rather than Python's system trust store.
        query.pop("sslmode", None)
        query.pop("ssl", None)
        engine_url = parsed_url.set(query=query)
        connect_args["ssl"] = build_postgresql_ssl_context()

    return engine_url, connect_args


def build_postgresql_ssl_context() -> ssl.SSLContext:
    """Create hostname-verified TLS using Python's system trusted CA bundle."""
    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    return context


def build_alembic_engine_configuration(
    settings, database_url: str
) -> tuple[dict[str, str], dict]:
    """Return Alembic's URL and connect args using application DB policy."""
    engine_url, connect_args = build_database_connection_configuration(settings, database_url)
    return {"sqlalchemy.url": str(engine_url)}, connect_args


def build_engine_configuration(settings) -> tuple[object, dict]:
    """Build SQLAlchemy options, enforcing verified TLS for production PostgreSQL."""
    engine_url, connect_args = build_database_connection_configuration(settings)
    is_sqlite = "sqlite" in settings.database_url.lower()
    engine_kwargs: dict = {
        "echo": settings.debug,
        "future": True,
    }

    if not is_sqlite:
        engine_kwargs.update(
            {
                "pool_size": 10,
                "max_overflow": 20,
                "pool_pre_ping": True,
                "pool_recycle": 3600,
            }
        )

    if connect_args:
        engine_kwargs["connect_args"] = connect_args

    return engine_url, engine_kwargs


def get_engine() -> AsyncEngine:
    """Retrieve or create the global async engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        engine_url, engine_kwargs = build_engine_configuration(settings)
        _engine = create_async_engine(engine_url, **engine_kwargs)
        logger.info("Initialized async database engine.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Retrieve or create the async session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI request-scoped database dependency.
    
    Yields an independent AsyncSession per HTTP request. Commits on success,
    rolls back on exception, and guarantees session closure.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_async_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Isolated session context manager for background tasks and maintenance scripts.
    
    Allows background jobs executing on the asyncio event loop to acquire a dedicated,
    isolated session without relying on request scopes.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_database() -> None:
    """Gracefully terminate engine connection pool on application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        logger.info("Disposing database connection pool...")
        await _engine.dispose()
        _engine = None
        _session_factory = None
