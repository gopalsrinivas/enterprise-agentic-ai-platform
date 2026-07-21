"""Typed environment-based application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, model_validator
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
    jwt_secret: SecretStr = Field(
        default=SecretStr("CHANGE_ME_USE_AT_LEAST_32_RANDOM_CHARACTERS"), repr=False
    )
    jwt_issuer: str = "enterprise-agentic-ai-platform"
    jwt_audience: str = "enterprise-agentic-ai-platform-api"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_ttl_days: int = Field(default=7, ge=1, le=30)
    registration_enabled: bool = False

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        """Reject unsafe token configuration outside tests."""
        secret = self.jwt_secret.get_secret_value()
        if len(secret) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        if self.app_env == "production" and secret.startswith("CHANGE_ME"):
            raise ValueError("JWT_SECRET must be configured in production")
        if self.app_env == "production" and self.registration_enabled:
            raise ValueError("Registration cannot be enabled in production")
        return self

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return a SQLAlchemy-compatible URL without exposing it in repr output."""
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    """Load and cache process settings."""
    return Settings()
