"""Establish the empty Phase 2 migration baseline.

Revision ID: 20260721_0001
Revises:
Create Date: 2026-07-21
"""

from collections.abc import Sequence

revision: str = "20260721_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reserve a migration baseline; domain tables begin in Phase 3."""


def downgrade() -> None:
    """Remove the empty migration baseline."""
