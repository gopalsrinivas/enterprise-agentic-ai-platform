"""Request correlation middleware."""

from __future__ import annotations

from time import perf_counter
from uuid import UUID, uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import correlation_id_context, get_logger

REQUEST_ID_HEADER = "X-Request-ID"
MAX_LOGGED_PATH_LENGTH = 2048
logger = get_logger("app.request")


def _valid_request_id(value: str | None) -> str:
    if value is not None:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())


def _sanitized_request_path(scope: Scope) -> str:
    """Return only a bounded printable path, never a query string."""
    path = str(scope.get("path", "/"))
    printable_path = "".join(character if character.isprintable() else "?" for character in path)
    return printable_path[:MAX_LOGGED_PATH_LENGTH]


class CorrelationIdMiddleware:
    """Propagate a validated UUID request identifier."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = _valid_request_id(headers.get(b"x-request-id", b"").decode() or None)
        token = correlation_id_context.set(request_id)
        started_at = perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = MutableHeaders(scope=message)
                response_headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "request_completed",
                extra={
                    "event": "request_completed",
                    "http_method": scope.get("method", "UNKNOWN"),
                    "request_path": _sanitized_request_path(scope),
                    "status_code": status_code,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            correlation_id_context.reset(token)
