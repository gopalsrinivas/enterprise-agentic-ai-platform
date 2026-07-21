"""Database-independent Phase 3 identity service tests using SQLite."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.models.domain import AuditLog
from app.models.identity import Permission, RefreshSession, Role, UserRole
from app.services.identity import (
    IdentityError,
    find_user,
    login,
    logout,
    register_user,
    replace_roles,
    rotate_refresh,
    seed_roles_and_permissions,
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as database_session:
        yield database_session
    await engine.dispose()


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        jwt_secret="test-only-secret-that-is-at-least-32-chars",
    )


@pytest.mark.asyncio
async def test_rbac_seed_is_idempotent(session: AsyncSession) -> None:
    await seed_roles_and_permissions(session)
    await seed_roles_and_permissions(session)
    assert await session.scalar(select(func.count()).select_from(Role)) == 4
    assert await session.scalar(select(func.count()).select_from(Permission)) == 16


@pytest.mark.asyncio
async def test_registration_normalizes_email_and_audits(session: AsyncSession) -> None:
    user = await register_user(session, " Person@Example.COM ", "Person", "a secure password")
    assert user.email == "person@example.com"
    assert user.password_hash != "a secure password"
    assert await session.scalar(select(func.count()).select_from(AuditLog)) == 1


@pytest.mark.asyncio
async def test_duplicate_registration_is_generic(session: AsyncSession) -> None:
    await register_user(session, "person@example.com", "Person", "a secure password")
    with pytest.raises(IdentityError, match="Registration could not be completed"):
        await register_user(session, "PERSON@example.com", "Other", "another secure password")


@pytest.mark.asyncio
async def test_login_refresh_rotation_and_reuse_detection(
    session: AsyncSession, auth_settings: Settings
) -> None:
    await register_user(session, "person@example.com", "Person", "a secure password")
    pair = await login(session, "person@example.com", "a secure password", auth_settings)
    rotated = await rotate_refresh(session, pair.refresh_token, auth_settings)
    assert rotated.refresh_token != pair.refresh_token
    with pytest.raises(IdentityError):
        await rotate_refresh(session, pair.refresh_token, auth_settings)
    sessions = list((await session.scalars(select(RefreshSession))).all())
    assert all(item.revoked_at is not None for item in sessions)
    assert any(item.reuse_detected for item in sessions)


@pytest.mark.asyncio
async def test_wrong_and_unknown_login_are_generic(
    session: AsyncSession, auth_settings: Settings
) -> None:
    await register_user(session, "person@example.com", "Person", "a secure password")
    for email in ("person@example.com", "unknown@example.com"):
        with pytest.raises(IdentityError, match="Invalid email or password"):
            await login(session, email, "wrong", auth_settings)


@pytest.mark.asyncio
async def test_inactive_and_deleted_users_cannot_login(
    session: AsyncSession, auth_settings: Settings
) -> None:
    user = await register_user(session, "person@example.com", "Person", "a secure password")
    user.status = "inactive"
    await session.commit()
    with pytest.raises(IdentityError):
        await login(session, user.email, "a secure password", auth_settings)
    user.status = "active"
    user.is_deleted = True
    await session.commit()
    with pytest.raises(IdentityError):
        await login(session, user.email, "a secure password", auth_settings)


@pytest.mark.asyncio
async def test_expired_refresh_token_is_rejected(
    session: AsyncSession, auth_settings: Settings
) -> None:
    await register_user(session, "person@example.com", "Person", "a secure password")
    pair = await login(session, "person@example.com", "a secure password", auth_settings)
    refresh_session = await session.scalar(select(RefreshSession))
    assert refresh_session is not None
    refresh_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()
    with pytest.raises(IdentityError, match="Invalid or expired"):
        await rotate_refresh(session, pair.refresh_token, auth_settings)


@pytest.mark.asyncio
async def test_logout_revokes_refresh_family(
    session: AsyncSession, auth_settings: Settings
) -> None:
    user = await register_user(session, "person@example.com", "Person", "a secure password")
    pair = await login(session, user.email, "a secure password", auth_settings)
    await logout(session, pair.refresh_token, user, auth_settings)
    with pytest.raises(IdentityError):
        await rotate_refresh(session, pair.refresh_token, auth_settings)


@pytest.mark.asyncio
async def test_invalid_role_assignment_and_last_admin_are_protected(
    session: AsyncSession,
) -> None:
    await seed_roles_and_permissions(session)
    admin = await register_user(session, "admin@example.com", "Admin", "a secure password")
    admin_role = await session.scalar(select(Role).where(Role.name == "admin"))
    assert admin_role is not None
    session.add(UserRole(user_id=admin.id, role_id=admin_role.id, assigned_by=admin.id))
    await session.commit()
    refreshed_admin = await find_user(session, admin.id)
    assert refreshed_admin is not None
    with pytest.raises(IdentityError, match="do not exist"):
        await replace_roles(session, refreshed_admin, [uuid4()], refreshed_admin)
    with pytest.raises(IdentityError, match="last administrator"):
        await replace_roles(session, refreshed_admin, [], refreshed_admin)
