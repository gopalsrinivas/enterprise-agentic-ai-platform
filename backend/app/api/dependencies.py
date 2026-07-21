"""Shared FastAPI dependencies."""

from collections.abc import AsyncGenerator
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import DatabaseManager


def get_app_settings(request: Request) -> Settings:
    """Return lifespan-managed settings."""
    return cast(Settings, request.app.state.settings)


def get_database(request: Request) -> DatabaseManager:
    """Return the lifespan-managed database manager."""
    return cast(DatabaseManager, request.app.state.database)


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped async database session."""
    database = get_database(request)
    async for session in database.session():
        yield session
