"""Operational endpoint response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Liveness response."""

    model_config = ConfigDict(extra="forbid")
    status: Literal["healthy"]


class ReadinessResponse(BaseModel):
    """Sanitized readiness response."""

    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "not_ready"]
