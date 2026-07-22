"""PostgreSQL/pgvector integration coverage for authorized Phase 4 retrieval."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import DatabaseManager
from app.models.domain import Document, DocumentChunk
from app.models.identity import User
from app.services.embeddings import FakeEmbeddingProvider


@pytest.mark.integration
async def test_vector_persistence_similarity_and_pre_rank_authorization() -> None:
    manager = DatabaseManager.from_settings(get_settings())
    connection = await manager.engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        owner = User(
            email=f"owner-{uuid4()}@example.invalid",
            display_name="Owner",
            password_hash="not-a-real-credential",
            status="active",
        )
        other = User(
            email=f"other-{uuid4()}@example.invalid",
            display_name="Other",
            password_hash="not-a-real-credential",
            status="active",
        )
        session.add_all([owner, other])
        await session.flush()
        documents = [
            Document(
                owner_id=owner.id,
                filename="authorized.txt",
                storage_key=f"test/{uuid4().hex}",
                media_type="text/plain",
                byte_size=5,
                checksum="a" * 64,
                status="ready",
                classification="internal",
            ),
            Document(
                owner_id=other.id,
                filename="unauthorized.txt",
                storage_key=f"test/{uuid4().hex}",
                media_type="text/plain",
                byte_size=5,
                checksum="b" * 64,
                status="ready",
                classification="internal",
            ),
            Document(
                owner_id=owner.id,
                filename="failed.txt",
                storage_key=f"test/{uuid4().hex}",
                media_type="text/plain",
                byte_size=5,
                checksum="c" * 64,
                status="failed",
                classification="internal",
            ),
        ]
        session.add_all(documents)
        await session.flush()
        provider = FakeEmbeddingProvider()
        vectors = await provider.embed(["alpha knowledge", "alpha knowledge", "alpha knowledge"])
        for document, vector in zip(documents, vectors, strict=True):
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    ordinal=0,
                    text="alpha knowledge",
                    page_number=1,
                    section="Test",
                    token_count=2,
                    embedding=vector,
                    embedding_model=provider.model,
                )
            )
        await session.flush()

        query_vector = (await provider.embed(["alpha knowledge"]))[0]
        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        rows = (
            await session.execute(
                select(DocumentChunk, Document, distance.label("distance"))
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(
                    Document.owner_id == owner.id,
                    Document.status == "ready",
                    Document.classification == "internal",
                    Document.is_deleted.is_(False),
                    DocumentChunk.is_deleted.is_(False),
                )
                .order_by(distance)
                .limit(1)
            )
        ).all()
        assert len(rows) == 1
        chunk, document, measured_distance = rows[0]
        assert document.filename == "authorized.txt"
        assert chunk.page_number == 1
        assert chunk.section == "Test"
        assert float(measured_distance) == pytest.approx(0.0, abs=1e-6)
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await manager.dispose()
