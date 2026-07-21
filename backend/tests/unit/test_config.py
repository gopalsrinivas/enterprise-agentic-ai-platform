"""Configuration tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_accept_safe_test_values() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://user:placeholder@db.example/test",
        database_pool_size=3,
    )

    assert settings.app_env == "test"
    assert settings.database_pool_size == 3
    assert settings.sqlalchemy_database_url.startswith("postgresql+asyncpg://")


def test_settings_reject_invalid_pool_size() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_pool_size=0)


def test_settings_repr_hides_database_url() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:do_not_render@db.example/test",
    )

    assert "do_not_render" not in repr(settings)


def test_env_example_contains_placeholders_only() -> None:
    env_example = Path(__file__).parents[2] / ".env.example"
    content = env_example.read_text(encoding="utf-8")

    assert "CHANGE_ME" in content
    assert "sk-" not in content
    private_key_marker = "BEGIN " + "PRIVATE KEY"
    assert private_key_marker not in content
