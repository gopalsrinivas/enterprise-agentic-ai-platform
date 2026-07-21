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
    document_storage_path: str = ".data/documents"
    document_max_bytes: int = Field(default=10_000_000, ge=1, le=100_000_000)
    document_max_pages: int = Field(default=500, ge=1, le=5000)
    document_max_extracted_chars: int = Field(default=2_000_000, ge=1)
    document_chunk_chars: int = Field(default=1200, ge=100, le=10000)
    document_chunk_overlap_chars: int = Field(default=200, ge=0, le=2000)
    embedding_provider: Literal["fake", "openai"] = "fake"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: Literal[1536] = 1536
    openai_api_key: SecretStr | None = Field(default=None, repr=False)

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
        if self.document_chunk_overlap_chars >= self.document_chunk_chars:
            raise ValueError("DOCUMENT_CHUNK_OVERLAP_CHARS must be smaller than chunk size")
        if self.embedding_provider == "openai" and self.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI embedding provider")
        return self

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return a SQLAlchemy-compatible URL without exposing it in repr output."""
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    """Load and cache process settings."""
    return Settings()
