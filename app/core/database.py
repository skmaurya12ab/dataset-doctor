"""Async SQLAlchemy 2.0 database engine and session factory.

IMPORTANT ARCHITECTURAL RULE:
AsyncSession instances are tied to asyncio event loops and are NOT thread-safe.
They must NEVER be shared across worker threads or between concurrent background tasks.
Background analysis jobs running in worker threads must create their own dedicated
sessions or use thread-isolated execution patterns.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional
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


def get_engine() -> AsyncEngine:
    """Retrieve or create the global async engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        is_sqlite = "sqlite" in settings.database_url.lower()

        engine_kwargs = {
            "echo": settings.debug,
            "future": True,
        }

        # Postgres-specific connection pooling configuration
        if not is_sqlite:
            engine_kwargs.update(
                {
                    "pool_size": 10,
                    "max_overflow": 20,
                    "pool_pre_ping": True,
                    "pool_recycle": 3600,
                }
            )

        _engine = create_async_engine(settings.database_url, **engine_kwargs)
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
