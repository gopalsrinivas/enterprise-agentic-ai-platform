"""Operational liveness and readiness probes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_database
from app.db.session import DatabaseManager
from app.schemas.system import HealthResponse, ReadinessResponse

router = APIRouter(tags=["operations"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report process liveness without touching external dependencies."""
    return HealthResponse(status="healthy")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def ready(
    response: Response,
    database: Annotated[DatabaseManager, Depends(get_database)],
) -> ReadinessResponse:
    """Report required dependency readiness with sanitized detail."""
    if await database.is_ready():
        return ReadinessResponse(status="ready")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="not_ready")
