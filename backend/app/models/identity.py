"""Identity, RBAC, and refresh-session models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, MutableAuditMixin, UuidPrimaryKeyMixin


class User(MutableAuditMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_active_email",
            "email",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint("status IN ('active','inactive')", name="ck_users_status"),
    )
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    roles: Mapped[list[Role]] = relationship(
        secondary="user_roles",
        primaryjoin="User.id == UserRole.user_id",
        secondaryjoin="Role.id == UserRole.role_id",
        lazy="selectin",
        viewonly=True,
    )


class Role(MutableAuditMixin, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(500))
    permissions: Mapped[list[Permission]] = relationship(
        secondary="role_permissions", lazy="selectin", viewonly=True
    )


class Permission(UuidPrimaryKeyMixin, Base):
    __tablename__ = "permissions"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(500))


class UserRole(UuidPrimaryKeyMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    role_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("roles.id", ondelete="RESTRICT"))
    assigned_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RolePermission(UuidPrimaryKeyMixin, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
    )
    role_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("roles.id", ondelete="RESTRICT"))
    permission_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("permissions.id", ondelete="RESTRICT")
    )


class RefreshSession(UuidPrimaryKeyMixin, Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (
        Index("ix_refresh_sessions_user", "user_id"),
        Index("ix_refresh_sessions_family", "family_id"),
        Index("ix_refresh_sessions_expiry", "expires_at"),
    )
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    family_id: Mapped[UUID] = mapped_column(Uuid)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("refresh_sessions.id", ondelete="RESTRICT")
    )
    reuse_detected: Mapped[bool] = mapped_column(Boolean, default=False)
