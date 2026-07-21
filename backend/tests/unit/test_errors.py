"""Safe error envelope tests."""

from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient

from app.main import create_app


def _client_with_error_routes() -> TestClient:
    app = create_app()
    router = APIRouter()

    @router.get("/_test/http-error")
    async def http_error() -> None:
        raise HTTPException(status_code=409, detail="Safe conflict")

    @router.get("/_test/unhandled-error")
    async def unhandled_error() -> None:
        raise RuntimeError("sensitive internal detail")

    @router.get("/_test/validated")
    async def validated(value: int) -> int:
        return value

    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_http_exception_uses_error_envelope() -> None:
    with _client_with_error_routes() as client:
        response = client.get("/_test/http-error")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "http_error"
    assert response.json()["error"]["message"] == "Safe conflict"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_unhandled_exception_does_not_leak_details() -> None:
    with _client_with_error_routes() as client:
        response = client.get("/_test/unhandled-error")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_server_error"
    assert "sensitive internal detail" not in response.text


def test_validation_exception_uses_approved_error_envelope() -> None:
    with _client_with_error_routes() as client:
        response = client.get("/_test/validated", params={"value": "not-an-integer"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
