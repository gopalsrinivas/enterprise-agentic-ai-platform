"""Short-lived JWT access tokens and opaque one-way-hashed refresh tokens."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from app.core.config import Settings


class InvalidTokenError(Exception):
    """Raised for any invalid, expired, or wrong-purpose token."""


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID


def create_access_token(user_id: UUID, settings: Settings, *, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "jti": str(uuid4()),
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.access_token_ttl_minutes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
        if payload.get("type") != "access":
            raise InvalidTokenError
        return AccessClaims(user_id=UUID(payload["sub"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError from exc


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str, settings: Settings) -> str:
    return hmac.new(
        settings.jwt_secret.get_secret_value().encode(), token.encode(), hashlib.sha256
    ).hexdigest()
