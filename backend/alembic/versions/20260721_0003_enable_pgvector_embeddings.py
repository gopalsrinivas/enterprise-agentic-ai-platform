"""enable pgvector embeddings

Revision ID: 20260721_0003
Revises: 20260721_0002
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260721_0003"
down_revision: str | None = "20260721_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.alter_column(
        "document_chunks",
        "embedding",
        type_=sa.Text(),
        postgresql_using="embedding::text",
    )
    op.execute(
        "ALTER TABLE document_chunks ALTER COLUMN embedding "
        "TYPE vector(1536) USING embedding::vector(1536)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE document_chunks ALTER COLUMN embedding "
        "TYPE json USING embedding::text::json"
    )
    op.execute("DROP EXTENSION IF EXISTS vector")
