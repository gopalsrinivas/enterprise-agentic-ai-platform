"""Explicit, credential-safe Phase 3 bootstrap commands."""

from __future__ import annotations

import argparse
import asyncio
import os

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import DatabaseManager
from app.models.identity import Role, User, UserRole
from app.security.passwords import hash_password
from app.services.identity import normalize_email, seed_roles_and_permissions


async def _seed_rbac() -> None:
    database = DatabaseManager.from_settings(get_settings())
    try:
        async for session in database.session():
            await seed_roles_and_permissions(session)
    finally:
        await database.dispose()


async def _bootstrap_admin() -> None:
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    display_name = os.environ.get("ADMIN_DISPLAY_NAME", "Administrator")
    if not email or not password:
        raise SystemExit("ADMIN_EMAIL and ADMIN_PASSWORD are required")
    try:
        email = str(TypeAdapter(EmailStr).validate_python(email))
    except ValidationError as exc:
        raise SystemExit("ADMIN_EMAIL must be a valid email address") from exc
    if len(password) < 12:
        raise SystemExit("ADMIN_PASSWORD must contain at least 12 characters")
    database = DatabaseManager.from_settings(get_settings())
    try:
        async for session in database.session():
            await seed_roles_and_permissions(session)
            normalized = normalize_email(email)
            user = await session.scalar(select(User).where(User.email == normalized))
            if user is None:
                user = User(
                    email=normalized,
                    display_name=display_name.strip(),
                    password_hash=hash_password(password),
                )
                session.add(user)
                await session.flush()
            admin = await session.scalar(select(Role).where(Role.name == "admin"))
            if admin is None:
                raise RuntimeError("RBAC seed did not create the admin role")
            assignment = await session.scalar(
                select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == admin.id)
            )
            if assignment is None:
                session.add(UserRole(user_id=user.id, role_id=admin.id, assigned_by=user.id))
            await session.commit()
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 administrative bootstrap")
    parser.add_argument("command", choices=("seed-rbac", "bootstrap-admin"))
    command = parser.parse_args().command
    asyncio.run(_seed_rbac() if command == "seed-rbac" else _bootstrap_admin())


if __name__ == "__main__":
    main()
