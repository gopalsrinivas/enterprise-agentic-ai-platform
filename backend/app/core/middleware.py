"""Request correlation middleware."""

from __future__ import annotations

from uuid import UUID, uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import correlation_id_context

REQUEST_ID_HEADER = "X-Request-ID"


def _valid_request_id(value: str | None) -> str:
    if value is not None:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())


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

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            correlation_id_context.reset(token)
