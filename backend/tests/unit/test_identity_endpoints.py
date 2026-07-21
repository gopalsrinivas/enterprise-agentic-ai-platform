"""Phase 3 authentication and deny-by-default endpoint tests."""

from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies import get_app_settings, get_session
from app.core.config import Settings
from app.db.base import Base
from app.main import create_app


@pytest_asyncio.fixture
async def identity_client() -> AsyncIterator[AsyncClient]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        jwt_secret="endpoint-test-secret-with-at-least-32-characters",
        registration_enabled=True,
    )
    app = create_app(settings)

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_app_settings] = lambda: settings
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


async def register(identity_client: AsyncClient) -> dict[str, object]:
    response = await identity_client.post(
        "/api/v1/auth/register",
        json={
            "email": "person@example.com",
            "display_name": "Person",
            "password": "a secure development password",
        },
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


async def login(identity_client: AsyncClient) -> dict[str, str]:
    response = await identity_client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "a secure development password"},
    )
    assert response.status_code == 200
    return cast(dict[str, str], response.json())


@pytest.mark.asyncio
async def test_development_registration_and_duplicate_redaction(
    identity_client: AsyncClient,
) -> None:
    body = await register(identity_client)
    assert body["email"] == "person@example.com"
    assert "password" not in body
    duplicate = await identity_client.post(
        "/api/v1/auth/register",
        json={
            "email": "PERSON@example.com",
            "display_name": "Other",
            "password": "another secure password",
        },
    )
    assert duplicate.status_code == 409
    assert "hash" not in duplicate.text


@pytest.mark.asyncio
async def test_registration_disabled_is_safe() -> None:
    settings = Settings(_env_file=None, app_env="test", registration_enabled=False)
    app = create_app(settings)
    app.state.settings = settings

    async def unused_session() -> AsyncIterator[AsyncSession]:
        yield AsyncSession()

    app.dependency_overrides[get_session] = unused_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "a@example.com",
                "display_name": "A",
                "password": "long enough password",
            },
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_login_current_user_and_missing_auth(identity_client: AsyncClient) -> None:
    await register(identity_client)
    tokens = await login(identity_client)
    me = await identity_client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["permissions"] == []
    assert (await identity_client.get("/api/v1/users/me")).status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_and_permission_denial(identity_client: AsyncClient) -> None:
    await register(identity_client)
    tokens = await login(identity_client)
    assert (
        await identity_client.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer invalid.token.value"}
        )
    ).status_code == 401
    assert (
        await identity_client.get(
            "/api/v1/users", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_refresh_rotation_reuse_and_logout(identity_client: AsyncClient) -> None:
    await register(identity_client)
    first = await login(identity_client)
    rotation = await identity_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert rotation.status_code == 200
    assert rotation.json()["refresh_token"] != first["refresh_token"]
    reuse = await identity_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert reuse.status_code == 401
    logout = await identity_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": rotation.json()["refresh_token"]},
        headers={"Authorization": f"Bearer {rotation.json()['access_token']}"},
    )
    assert logout.status_code == 204
