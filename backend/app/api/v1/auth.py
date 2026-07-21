"""Phase 3 authentication endpoints."""

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_app_settings, get_session
from app.api.v1.dependencies import current_user
from app.core.config import Settings
from app.models.identity import User
from app.schemas.identity import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.identity import (
    IdentityError,
    effective_permissions,
    login,
    logout,
    register_user,
    role_names,
    rotate_refresh,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _raise(error: IdentityError) -> NoReturn:
    raise HTTPException(error.status_code, error.message) from error


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        created_at=user.created_at,
        updated_at=user.updated_at,
        roles=role_names(user),
        permissions=effective_permissions(user),
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> UserResponse:
    if not settings.registration_enabled or settings.app_env == "production":
        raise HTTPException(404, "Resource not found")
    try:
        return user_response(
            await register_user(
                session,
                str(body.email),
                body.display_name,
                body.password.get_secret_value(),
            )
        )
    except IdentityError as error:
        _raise(error)


@router.post("/login", response_model=TokenResponse)
async def authenticate(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> TokenResponse:
    try:
        return await login(session, str(body.email), body.password.get_secret_value(), settings)
    except IdentityError as error:
        _raise(error)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> TokenResponse:
    try:
        return await rotate_refresh(session, body.refresh_token.get_secret_value(), settings)
    except IdentityError as error:
        _raise(error)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(
    body: LogoutRequest,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> Response:
    await logout(session, body.refresh_token.get_secret_value(), user, settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
