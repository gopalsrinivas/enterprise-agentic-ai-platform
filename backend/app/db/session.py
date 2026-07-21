"""Async SQLAlchemy engine and session lifecycle."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """Own an async engine and sessions for one application lifecycle."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> DatabaseManager:
        engine = create_async_engine(
            settings.sqlalchemy_database_url,
            pool_pre_ping=True,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            connect_args={"timeout": settings.database_connect_timeout_seconds},
        )
        return cls(engine)

    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a session and roll back unfinished or failed transactions."""
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def is_ready(self) -> bool:
        """Run a bounded connectivity probe and hide dependency details."""
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:
            logger.warning("database_readiness_failed")
            return False
        return True

    async def dispose(self) -> None:
        """Release pooled connections during graceful shutdown."""
        await self.engine.dispose()
