"""Database lifecycle tests that do not require PostgreSQL."""

from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.db.session import DatabaseManager


class FailingConnectionContext:
    """Deterministic async connection context that simulates an outage."""

    async def __aenter__(self) -> None:
        raise OSError("simulated connection failure")

    async def __aexit__(self, *args: object) -> None:
        return None


class FailingEngine:
    """Small engine double used only for the readiness failure branch."""

    def connect(self) -> FailingConnectionContext:
        return FailingConnectionContext()

    async def dispose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_session_executes_and_closes_with_local_sqlite() -> None:
    manager = DatabaseManager(create_async_engine("sqlite+aiosqlite:///:memory:"))
    try:
        sessions = manager.session()
        session = await anext(sessions)
        result = await session.execute(text("SELECT 1"))
        await sessions.aclose()

        assert result.scalar_one() == 1
    finally:
        await manager.dispose()


@pytest.mark.asyncio
async def test_readiness_uses_real_async_connection_contract() -> None:
    manager = DatabaseManager(create_async_engine("sqlite+aiosqlite:///:memory:"))
    try:
        assert await manager.is_ready() is True
    finally:
        await manager.dispose()


@pytest.mark.asyncio
async def test_unreachable_database_reports_not_ready() -> None:
    failing_engine = cast(Any, FailingEngine())
    manager = DatabaseManager(cast(AsyncEngine, failing_engine))
    try:
        assert await manager.is_ready() is False
    finally:
        await manager.dispose()
