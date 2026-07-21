"""Operational endpoint and OpenAPI tests."""

from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_database


class StubDatabase:
    def __init__(self, ready: bool) -> None:
        self.ready = ready

    async def is_ready(self) -> bool:
        return self.ready


def test_health_is_liveness_only(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    UUID(response.headers["X-Request-ID"])


def test_ready_when_database_is_available(client: TestClient) -> None:
    app: FastAPI = client.app  # type: ignore[assignment]
    app.dependency_overrides[get_database] = lambda: StubDatabase(ready=True)
    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_fails_safely_when_database_is_unavailable(client: TestClient) -> None:
    app: FastAPI = client.app  # type: ignore[assignment]
    app.dependency_overrides[get_database] = lambda: StubDatabase(ready=False)
    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert "database" not in response.text.lower()


def test_valid_request_id_is_propagated(client: TestClient) -> None:
    request_id = str(uuid4())
    response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "not-a-uuid"})

    generated = response.headers["X-Request-ID"]
    UUID(generated)
    assert generated != "not-a-uuid"


def test_openapi_exposes_only_phase_two_operations(client: TestClient) -> None:
    document = client.get("/openapi.json").json()

    assert document["info"]["title"] == "Enterprise Agentic AI Platform API"
    assert set(document["paths"]) == {"/health", "/ready"}
