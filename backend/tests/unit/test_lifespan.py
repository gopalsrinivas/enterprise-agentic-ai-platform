"""Deterministic application shutdown lifecycle tests."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_lifespan_disposes_database_once_on_shutdown() -> None:
    database = AsyncMock()
    settings = Settings(_env_file=None, app_env="test")

    with patch("app.main.DatabaseManager.from_settings", return_value=database):
        with TestClient(create_app(settings)) as client:
            assert client.get("/health").status_code == 200

    database.dispose.assert_awaited_once_with()
