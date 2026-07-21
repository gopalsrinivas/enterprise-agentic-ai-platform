"""Public Phase 3 identity contracts; persistence secrets are deliberately absent."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    password: SecretStr = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: SecretStr = Field(min_length=32, max_length=512)


class LogoutRequest(RefreshRequest):
    pass


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a credential
    expires_in: int


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: EmailStr
    display_name: str
    status: str
    created_at: datetime
    updated_at: datetime
    roles: list[str] = []
    permissions: list[str] = []


class UserListResponse(BaseModel):
    items: list[UserResponse]
    next_cursor: UUID | None = None


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in {"active", "inactive"}:
            raise ValueError("status must be active or inactive")
        return value


class PermissionResponse(BaseModel):
    name: str
    description: str


class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: str
    permissions: list[PermissionResponse]


class RoleListResponse(BaseModel):
    items: list[RoleResponse]


class RoleAssignmentRequest(BaseModel):
    role_ids: list[UUID] = Field(max_length=20)

    @field_validator("role_ids")
    @classmethod
    def unique_roles(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("role_ids must be unique")
        return value
