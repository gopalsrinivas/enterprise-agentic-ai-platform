"""Structured request-completion logging tests."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter
from app.main import create_app


@contextmanager
def capture_request_logs() -> Iterator[io.StringIO]:
    """Capture only application-owned request events as JSON."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    request_logger = logging.getLogger("app.request")
    previous_propagate = request_logger.propagate
    request_logger.addHandler(handler)
    request_logger.propagate = False
    try:
        yield stream
    finally:
        request_logger.removeHandler(handler)
        request_logger.propagate = previous_propagate


def parsed_events(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


def test_generated_id_is_in_response_and_single_structured_log(client: TestClient) -> None:
    with capture_request_logs() as stream:
        response = client.get("/health")

    events = parsed_events(stream)
    assert len(events) == 1
    event = events[0]
    response_request_id = response.headers["X-Request-ID"]
    UUID(response_request_id)
    assert event["event"] == "request_completed"
    assert event["message"] == "request_completed"
    assert event["http_method"] == "GET"
    assert event["request_path"] == "/health"
    assert event["status_code"] == 200
    assert event["request_id"] == response_request_id
    assert isinstance(event["duration_ms"], (int, float))
    assert event["duration_ms"] >= 0


def test_valid_supplied_id_is_propagated_to_log(client: TestClient) -> None:
    request_id = str(uuid4())
    with capture_request_logs() as stream:
        response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id
    assert parsed_events(stream)[0]["request_id"] == request_id


def test_malicious_id_is_replaced_in_response_and_log(client: TestClient) -> None:
    malicious_id = "<script>token=not-safe</script>"
    with capture_request_logs() as stream:
        response = client.get("/health", headers={"X-Request-ID": malicious_id})

    effective_id = response.headers["X-Request-ID"]
    UUID(effective_id)
    assert effective_id != malicious_id
    serialized_log = stream.getvalue()
    assert parsed_events(stream)[0]["request_id"] == effective_id
    assert malicious_id not in serialized_log


def test_query_headers_cookies_and_credentials_are_not_logged(client: TestClient) -> None:
    sensitive_value = "verification-sensitive-value"
    with capture_request_logs() as stream:
        response = client.get(
            f"/health?access_token={sensitive_value}",
            headers={
                "Authorization": f"Bearer {sensitive_value}",
                "Cookie": f"session={sensitive_value}",
            },
        )

    event = parsed_events(stream)[0]
    assert response.status_code == 200
    assert event["request_path"] == "/health"
    assert sensitive_value not in stream.getvalue()
    assert "access_token" not in stream.getvalue()
    assert "Authorization" not in stream.getvalue()
    assert "Cookie" not in stream.getvalue()


def test_exception_response_is_safe_and_completion_log_is_structured() -> None:
    app = create_app()
    router = APIRouter()

    @router.get("/_test/logged-error")
    async def logged_error() -> None:
        raise RuntimeError("internal-sensitive-detail")

    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as client:
        with capture_request_logs() as stream:
            response = client.get("/_test/logged-error")

    events = parsed_events(stream)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_server_error"
    assert "internal-sensitive-detail" not in response.text
    assert len(events) == 1
    assert events[0]["status_code"] == 500
    assert events[0]["request_path"] == "/_test/logged-error"


def test_documented_uvicorn_command_disables_default_access_log() -> None:
    content = (Path(__file__).parents[3] / "README.md").read_text(encoding="utf-8")
    assert "uvicorn app.main:app --reload --no-access-log" in content
