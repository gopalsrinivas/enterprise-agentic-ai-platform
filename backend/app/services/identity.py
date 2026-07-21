"""Transactional Phase 3 identity, token, RBAC, and audit use cases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.logging import correlation_id_context
from app.models.domain import AuditLog
from app.models.identity import Permission, RefreshSession, Role, RolePermission, User, UserRole
from app.schemas.identity import TokenResponse
from app.security.passwords import hash_password, verify_password
from app.security.rbac import PERMISSIONS, ROLE_PERMISSIONS
from app.security.tokens import create_access_token, create_refresh_token, hash_refresh_token


class IdentityError(Exception):
    def __init__(self, code: str, status_code: int, message: str) -> None:
        self.code, self.status_code, self.message = code, status_code, message


def normalize_email(email: str) -> str:
    return email.strip().casefold()


async def audit(
    session: AsyncSession,
    action: str,
    outcome: str,
    resource_type: str,
    *,
    actor_id: UUID | None = None,
    resource_id: UUID | None = None,
    metadata: dict[str, str] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=correlation_id_context.get(),
            metadata_=metadata or {},
        )
    )


def role_names(user: User) -> list[str]:
    return sorted(role.name for role in user.roles)


def effective_permissions(user: User) -> list[str]:
    return sorted({permission.name for role in user.roles for permission in role.permissions})


async def find_user(session: AsyncSession, user_id: UUID) -> User | None:
    return cast(
        User | None,
        await session.scalar(
            select(User)
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .execution_options(populate_existing=True)
            .where(User.id == user_id, User.is_deleted.is_(False))
        ),
    )


async def register_user(
    session: AsyncSession, email: str, display_name: str, password: str
) -> User:
    normalized = normalize_email(email)
    if await session.scalar(
        select(User.id).where(User.email == normalized, User.is_deleted.is_(False))
    ):
        raise IdentityError("registration_failed", 409, "Registration could not be completed")
    user = User(
        email=normalized, display_name=display_name.strip(), password_hash=hash_password(password)
    )
    session.add(user)
    await session.flush()
    await audit(session, "auth.register", "success", "user", actor_id=user.id, resource_id=user.id)
    await session.commit()
    return await find_user(session, user.id) or user


async def issue_token_pair(
    session: AsyncSession, user: User, settings: Settings, family_id: UUID | None = None
) -> TokenResponse:
    raw_refresh = create_refresh_token()
    refresh = RefreshSession(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh, settings),
        family_id=family_id or uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
    )
    session.add(refresh)
    await session.flush()
    return TokenResponse(
        access_token=create_access_token(user.id, settings),
        refresh_token=raw_refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


async def login(
    session: AsyncSession, email: str, password: str, settings: Settings
) -> TokenResponse:
    user = await session.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.email == normalize_email(email), User.is_deleted.is_(False))
    )
    if (
        user is None
        or user.status != "active"
        or not verify_password(user.password_hash if user else None, password)
    ):
        await audit(session, "auth.login", "failure", "user")
        await session.commit()
        raise IdentityError("invalid_credentials", 401, "Invalid email or password")
    user.last_login_at = datetime.now(UTC)
    pair = await issue_token_pair(session, user, settings)
    await audit(session, "auth.login", "success", "user", actor_id=user.id, resource_id=user.id)
    await session.commit()
    return pair


async def rotate_refresh(
    session: AsyncSession, raw_token: str, settings: Settings
) -> TokenResponse:
    token_hash = hash_refresh_token(raw_token, settings)
    current = await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == token_hash).with_for_update()
    )
    now = datetime.now(UTC)
    if current is None:
        raise IdentityError("invalid_refresh_token", 401, "Invalid or expired refresh token")
    if current.revoked_at is not None:
        current.reuse_detected = True
        await session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.family_id == current.family_id, RefreshSession.revoked_at.is_(None)
            )
            .values(revoked_at=now)
        )
        await audit(
            session,
            "auth.refresh_reuse",
            "blocked",
            "refresh_session",
            actor_id=current.user_id,
            resource_id=current.id,
        )
        await session.commit()
        raise IdentityError("invalid_refresh_token", 401, "Invalid or expired refresh token")
    expires_at = current.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        current.revoked_at = now
        await session.commit()
        raise IdentityError("invalid_refresh_token", 401, "Invalid or expired refresh token")
    user = await find_user(session, current.user_id)
    if user is None or user.status != "active":
        current.revoked_at = now
        await session.commit()
        raise IdentityError("invalid_refresh_token", 401, "Invalid or expired refresh token")
    current.revoked_at = now
    pair = await issue_token_pair(session, user, settings, current.family_id)
    replacement = await session.scalar(
        select(RefreshSession).where(
            RefreshSession.token_hash == hash_refresh_token(pair.refresh_token, settings)
        )
    )
    current.replaced_by_id = replacement.id if replacement else None
    await audit(
        session,
        "auth.refresh",
        "success",
        "refresh_session",
        actor_id=user.id,
        resource_id=current.id,
    )
    await session.commit()
    return pair


async def logout(session: AsyncSession, raw_token: str, user: User, settings: Settings) -> None:
    current = await session.scalar(
        select(RefreshSession)
        .where(
            RefreshSession.token_hash == hash_refresh_token(raw_token, settings),
            RefreshSession.user_id == user.id,
        )
        .with_for_update()
    )
    if current is not None:
        await session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.family_id == current.family_id, RefreshSession.revoked_at.is_(None)
            )
            .values(revoked_at=datetime.now(UTC))
        )
    await audit(session, "auth.logout", "success", "user", actor_id=user.id, resource_id=user.id)
    await session.commit()


async def seed_roles_and_permissions(session: AsyncSession) -> None:
    permissions: dict[str, Permission] = {}
    for name, description in PERMISSIONS.items():
        permission = await session.scalar(select(Permission).where(Permission.name == name))
        if permission is None:
            permission = Permission(name=name, description=description)
            session.add(permission)
            await session.flush()
        permissions[name] = permission
    for role_name, permission_names in ROLE_PERMISSIONS.items():
        role = await session.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(name=role_name, description=f"Built-in {role_name.replace('_', ' ')} role")
            session.add(role)
            await session.flush()
        existing = set(
            (
                await session.scalars(
                    select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
                )
            ).all()
        )
        for permission_name in permission_names:
            permission = permissions[permission_name]
            if permission.id not in existing:
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    await session.commit()


async def replace_roles(
    session: AsyncSession, target: User, role_ids: list[UUID], actor: User
) -> User:
    roles = (
        list(
            (
                await session.scalars(
                    select(Role).where(Role.id.in_(role_ids), Role.is_deleted.is_(False))
                )
            ).all()
        )
        if role_ids
        else []
    )
    if len(roles) != len(role_ids):
        raise IdentityError("invalid_role_assignment", 400, "One or more roles do not exist")
    current_admin = any(role.name == "admin" for role in target.roles)
    new_admin = any(role.name == "admin" for role in roles)
    if current_admin and not new_admin:
        admin_role = await session.scalar(select(Role).where(Role.name == "admin"))
        if (
            admin_role
            and (
                await session.scalar(
                    select(UserRole)
                    .where(UserRole.role_id == admin_role.id, UserRole.user_id != target.id)
                    .limit(1)
                )
            )
            is None
        ):
            raise IdentityError(
                "last_admin_protected", 409, "The last administrator role cannot be removed"
            )
    await session.execute(delete(UserRole).where(UserRole.user_id == target.id))
    session.add_all(
        UserRole(user_id=target.id, role_id=role.id, assigned_by=actor.id) for role in roles
    )
    await audit(
        session,
        "user.roles_replaced",
        "success",
        "user",
        actor_id=actor.id,
        resource_id=target.id,
        metadata={"role_count": str(len(roles))},
    )
    await session.commit()
    return await find_user(session, target.id) or target
