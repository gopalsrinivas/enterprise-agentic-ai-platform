"""Authenticated user and RBAC administration endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session
from app.api.v1.auth import user_response
from app.api.v1.dependencies import current_user, require_permission
from app.models.identity import Role, User, UserRole
from app.schemas.identity import (
    PermissionResponse,
    RoleAssignmentRequest,
    RoleListResponse,
    RoleResponse,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.identity import IdentityError, audit, find_user, replace_roles

router = APIRouter(tags=["identity"])


@router.get("/users/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(current_user)]) -> UserResponse:
    return user_response(user)


@router.get("/users", response_model=UserListResponse)
async def list_users(
    _actor: Annotated[User, Depends(require_permission("users:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
) -> UserListResponse:
    statement = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.is_deleted.is_(False))
        .order_by(User.id)
        .limit(limit + 1)
    )
    if cursor:
        statement = statement.where(User.id > cursor)
    users = list((await session.scalars(statement)).all())
    return UserListResponse(
        items=[user_response(user) for user in users[:limit]],
        next_cursor=users[limit - 1].id if len(users) > limit else None,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    _actor: Annotated[User, Depends(require_permission("users:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    target = await find_user(session, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    return user_response(target)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    body: UserUpdateRequest,
    actor: Annotated[User, Depends(require_permission("users:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    target = await find_user(session, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    if body.display_name is not None:
        target.display_name = body.display_name.strip()
    if body.status is not None:
        if body.status == "inactive" and any(role.name == "admin" for role in target.roles):
            admin_role = next(role for role in target.roles if role.name == "admin")
            another_admin = await session.scalar(
                select(UserRole.id)
                .join(User, User.id == UserRole.user_id)
                .where(
                    UserRole.role_id == admin_role.id,
                    UserRole.user_id != target.id,
                    User.status == "active",
                    User.is_deleted.is_(False),
                )
                .limit(1)
            )
            if another_admin is None:
                raise HTTPException(409, "The last administrator cannot be deactivated")
        target.status = body.status
    target.updated_by = actor.id
    await audit(
        session,
        "user.updated",
        "success",
        "user",
        actor_id=actor.id,
        resource_id=target.id,
        metadata={"status_changed": str(body.status is not None).lower()},
    )
    await session.commit()
    return user_response(await find_user(session, target.id) or target)


@router.get("/roles", response_model=RoleListResponse)
async def list_roles(
    _actor: Annotated[User, Depends(require_permission("roles:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RoleListResponse:
    roles = (
        await session.scalars(
            select(Role)
            .options(selectinload(Role.permissions))
            .where(Role.is_deleted.is_(False))
            .order_by(Role.name)
        )
    ).all()
    return RoleListResponse(
        items=[
            RoleResponse(
                id=role.id,
                name=role.name,
                description=role.description,
                permissions=[
                    PermissionResponse(name=p.name, description=p.description)
                    for p in sorted(role.permissions, key=lambda item: item.name)
                ],
            )
            for role in roles
        ]
    )


@router.put("/users/{user_id}/roles", response_model=UserResponse)
async def assign_roles(
    user_id: UUID,
    body: RoleAssignmentRequest,
    actor: Annotated[User, Depends(require_permission("roles:assign"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    target = await find_user(session, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    try:
        return user_response(await replace_roles(session, target, body.role_ids, actor))
    except IdentityError as error:
        raise HTTPException(error.status_code, error.message) from error
