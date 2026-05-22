"""
Async SQLAlchemy engine + session factory for Neon Postgres.
Uses asyncpg driver for non-blocking I/O — critical for FastAPI compatibility.

Usage:
    async with get_session() as session:
        result = await session.execute(select(...))
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
import ssl
from sqlalchemy.pool import NullPool

from backend.src.config import settings
from backend.src.logger import get_logger

log = get_logger(__name__)

# NullPool is mandatory for Neon serverless — connection pooling is handled
# by Neon's own proxy. Using SQLAlchemy's pool causes stale connection errors
# on serverless cold starts.
ssl_context = ssl.create_default_context()
engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
    echo=False,  # set True to log all SQL during debugging
    connect_args={"ssl": ssl_context},
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager that yields an async session and handles cleanup."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    """Health check — verifies the database is reachable."""
    try:
        from sqlalchemy import text
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        log.info("db_connection_healthy")
        return True
    except Exception as exc:
        log.error("db_connection_failed", error=str(exc))
        return False