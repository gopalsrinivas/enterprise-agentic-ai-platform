"""Shared FastAPI dependencies."""

from typing import cast

from fastapi import Request

from app.core.config import Settings
from app.db.session import DatabaseManager


def get_app_settings(request: Request) -> Settings:
    """Return lifespan-managed settings."""
    return cast(Settings, request.app.state.settings)


def get_database(request: Request) -> DatabaseManager:
    """Return the lifespan-managed database manager."""
    return cast(DatabaseManager, request.app.state.database)
