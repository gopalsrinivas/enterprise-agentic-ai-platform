"""Safe, consistent API exception mapping."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import correlation_id_context, get_logger

logger = get_logger(__name__)


def _error_body(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": correlation_id_context.get(),
            "details": details or [],
        }
    }


def install_exception_handlers(app: FastAPI) -> None:
    """Register handlers without leaking exception or infrastructure detail."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_error_body("validation_error", "Request validation failed", details),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request could not be completed"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body("http_error", message),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_request_error",
            extra={"exception_type": type(exc).__name__},
        )
        return JSONResponse(
            status_code=500,
            content=_error_body("internal_server_error", "An unexpected error occurred"),
        )
