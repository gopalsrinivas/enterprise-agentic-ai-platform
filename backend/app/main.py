"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import CorrelationIdMiddleware
from app.db.session import DatabaseManager

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an application with explicit, testable dependencies."""
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = DatabaseManager.from_settings(app_settings)
        app.state.settings = app_settings
        app.state.database = database
        logger.info("application_started", extra={"environment": app_settings.app_env})
        try:
            yield
        finally:
            await database.dispose()
            logger.info("application_stopped")

    app = FastAPI(
        title="Enterprise Agentic AI Platform API",
        summary="Secure enterprise knowledge and workflow assistant API",
        description=(
            "Phase 2 backend foundation. Business capabilities are introduced in later phases."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationIdMiddleware)
    install_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
