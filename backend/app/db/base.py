"""Declarative base and shared Phase 3 persistence conventions."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base."""


class UuidPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)


class MutableAuditMixin(UuidPrimaryKeyMixin):
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    @declared_attr
    def created_by(cls) -> Mapped[UUID | None]:
        return mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)

    @declared_attr
    def updated_by(cls) -> Mapped[UUID | None]:
        return mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
