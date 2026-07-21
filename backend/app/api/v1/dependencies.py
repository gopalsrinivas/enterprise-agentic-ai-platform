"""Authentication and deny-by-default Phase 3 authorization dependencies."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_app_settings, get_session
from app.core.config import Settings
from app.models.identity import User
from app.security.tokens import InvalidTokenError, decode_access_token
from app.services.identity import effective_permissions, find_user

bearer = HTTPBearer(auto_error=False)


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError as exc:
        raise HTTPException(
            401, "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"}
        ) from exc
    user = await find_user(session, claims.user_id)
    if user is None or user.status != "active":
        raise HTTPException(
            401, "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"}
        )
    return user


def require_permission(permission: str) -> Callable[..., Awaitable[User]]:
    async def dependency(user: Annotated[User, Depends(current_user)]) -> User:
        if permission not in effective_permissions(user):
            raise HTTPException(403, "Permission denied")
        return user

    return dependency
