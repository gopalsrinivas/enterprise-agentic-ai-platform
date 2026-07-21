"""Typed environment-based application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and local .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: PostgresDsn = Field(
        default=PostgresDsn(
            "postgresql+asyncpg://app_user:CHANGE_ME@localhost:5432/enterprise_agentic_ai"
        ),
        repr=False,
    )
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return a SQLAlchemy-compatible URL without exposing it in repr output."""
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    """Load and cache process settings."""
    return Settings()
