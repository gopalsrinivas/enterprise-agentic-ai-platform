"""Phase 3 password and token security tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.security.passwords import hash_password, verify_password
from app.security.tokens import InvalidTokenError, create_access_token, decode_access_token


def test_argon2id_hash_round_trip_and_redaction() -> None:
    password = "correct horse battery staple"
    digest = hash_password(password)
    assert digest.startswith("$argon2id$")
    assert password not in digest
    assert verify_password(digest, password)
    assert not verify_password(digest, "incorrect password")


def test_unknown_user_password_check_is_generic() -> None:
    assert verify_password(None, "unknown password") is False


def test_access_token_round_trip(settings: Settings) -> None:
    user_id = uuid4()
    token = create_access_token(user_id, settings)
    assert decode_access_token(token, settings).user_id == user_id


def test_expired_access_token_is_rejected(settings: Settings) -> None:
    token = create_access_token(uuid4(), settings, now=datetime.now(UTC) - timedelta(hours=2))
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, settings)


def test_invalid_access_token_is_rejected(settings: Settings) -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-token", settings)


def test_settings_reject_placeholder_secret_in_production() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(_env_file=None, app_env="production")


def test_settings_reject_production_registration() -> None:
    with pytest.raises(ValueError, match="Registration"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret="x" * 32,
            registration_enabled=True,
        )
