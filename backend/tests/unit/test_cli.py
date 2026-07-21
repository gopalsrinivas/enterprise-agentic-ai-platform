"""Credential-safe administrative CLI input tests."""

from unittest.mock import patch

import pytest

from app.cli import _bootstrap_admin


@pytest.mark.asyncio
async def test_admin_bootstrap_rejects_invalid_email_before_database_access() -> None:
    with (
        patch.dict(
            "os.environ",
            {"ADMIN_EMAIL": "admin@example.invalid", "ADMIN_PASSWORD": "long safe password"},
            clear=False,
        ),
        pytest.raises(SystemExit, match="valid email"),
    ):
        await _bootstrap_admin()
