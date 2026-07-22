"""Owner-authorized document lifecycle and pgvector retrieval endpoints."""

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_app_settings, get_session
from app.api.v1.dependencies import current_user, require_permission
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.domain import Document, DocumentChunk
from app.models.identity import User
from app.schemas.documents import (
    ChunkListResponse,
    ChunkResponse,
    CitationCandidate,
    DocumentListResponse,
    DocumentResponse,
    SearchRequest,
    SearchResponse,
)
from app.services.documents import (
    DocumentError,
    chunk_parts,
    extract,
    load,
    remove,
    store,
    validate_upload,
)
from app.services.embeddings import FakeEmbeddingProvider, OpenAIEmbeddingProvider
from app.services.identity import audit, effective_permissions

router = APIRouter(tags=["documents"])
logger = get_logger(__name__)


def response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        media_type=document.media_type,
        byte_size=document.byte_size,
        status=document.status,
        failure_code=document.failure_code,
        classification=document.classification,
        metadata=document.metadata_,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def provider(settings: Settings) -> FakeEmbeddingProvider | OpenAIEmbeddingProvider:
    if settings.embedding_provider == "openai":
        assert settings.openai_api_key is not None
        return OpenAIEmbeddingProvider(
            settings.openai_api_key.get_secret_value(),
            settings.embedding_model,
            settings.embedding_dimensions,
        )
    return FakeEmbeddingProvider(settings.embedding_dimensions)


async def owned(session: AsyncSession, user: User, document_id: UUID) -> Document:
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id, Document.owner_id == user.id, Document.is_deleted.is_(False)
        )
    )
    if document is None:
        raise HTTPException(404, "Document not found")
    return document


async def process(
    document: Document, content: bytes, settings: Settings, session: AsyncSession
) -> None:
    document.status = "processing"
    await session.flush()
    try:
        parts = extract(content, Path(document.filename).suffix.casefold(), settings)
        chunks = chunk_parts(
            parts, settings.document_chunk_chars, settings.document_chunk_overlap_chars
        )
        embedding_provider = provider(settings)
        vectors = await embedding_provider.embed([item.text for item in chunks])
        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        for ordinal, (item, vector) in enumerate(zip(chunks, vectors, strict=True)):
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    ordinal=ordinal,
                    text=item.text,
                    page_number=item.page_number,
                    section=item.section,
                    token_count=len(item.text.split()),
                    embedding=vector,
                    embedding_model=embedding_provider.model,
                    metadata_={"content_is_untrusted": True},
                    created_by=document.owner_id,
                    updated_by=document.owner_id,
                )
            )
        document.status, document.failure_code = "ready", None
    except Exception:
        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        document.status, document.failure_code = "failed", "processing_failed"


@router.post("/documents", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(require_permission("documents:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    classification: Annotated[str, Form(max_length=50)] = "internal",
) -> DocumentResponse:
    content = await file.read(settings.document_max_bytes + 1)
    try:
        filename = validate_upload(file.filename or "", file.content_type or "", content, settings)
        key, checksum = store(content, settings.document_storage_path)
        document = Document(
            owner_id=user.id,
            filename=filename,
            storage_key=key,
            media_type=file.content_type or "",
            byte_size=len(content),
            checksum=checksum,
            status="uploaded",
            classification=classification,
            metadata_={"content_is_untrusted": True, "malware_scan": "not_configured"},
            created_by=user.id,
            updated_by=user.id,
        )
        session.add(document)
        await session.flush()
        await process(document, content, settings, session)
        await audit(
            session,
            "document.uploaded",
            "success",
            "document",
            actor_id=user.id,
            resource_id=document.id,
            metadata={"status": document.status},
        )
        await session.commit()
        await session.refresh(document)
        return response(document)
    except DocumentError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except Exception as exc:
        await session.rollback()
        if "key" in locals():
            remove(settings.document_storage_path, key)
        logger.error("document_upload_failed", extra={"exception_type": type(exc).__name__})
        raise HTTPException(422, "Document processing failed") from exc


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    user: Annotated[User, Depends(require_permission("documents:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentListResponse:
    rows = (
        await session.scalars(
            select(Document)
            .where(Document.owner_id == user.id, Document.is_deleted.is_(False))
            .order_by(Document.updated_at.desc())
        )
    ).all()
    return DocumentListResponse(items=[response(item) for item in rows])


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    user: Annotated[User, Depends(require_permission("documents:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentResponse:
    return response(await owned(session, user, document_id))


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    document = await session.scalar(
        select(Document).where(Document.id == document_id, Document.is_deleted.is_(False))
    )
    if document is None or (
        document.owner_id != user.id and "documents:delete" not in effective_permissions(user)
    ):
        raise HTTPException(404, "Document not found")
    document.is_deleted = True
    document.updated_by = user.id
    await session.execute(
        update(DocumentChunk)
        .where(DocumentChunk.document_id == document.id, DocumentChunk.is_deleted.is_(False))
        .values(is_deleted=True, updated_by=user.id)
    )
    await audit(
        session,
        "document.deleted",
        "success",
        "document",
        actor_id=user.id,
        resource_id=document.id,
    )
    await session.commit()


@router.post("/documents/{document_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document(
    document_id: UUID,
    user: Annotated[User, Depends(require_permission("documents:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> DocumentResponse:
    document = await owned(session, user, document_id)
    if document.status == "ready":
        return response(document)
    if document.status in {"uploaded", "processing"}:
        raise HTTPException(409, "Document is already being processed")
    try:
        await process(
            document, load(settings.document_storage_path, document.storage_key), settings, session
        )
        await audit(
            session,
            "document.reprocessed",
            "success",
            "document",
            actor_id=user.id,
            resource_id=document.id,
            metadata={"status": document.status},
        )
        await session.commit()
        await session.refresh(document)
        return response(document)
    except Exception as exc:
        await session.commit()
        raise HTTPException(422, "Document processing failed") from exc


@router.get("/documents/{document_id}/chunks", response_model=ChunkListResponse)
async def list_chunks(
    document_id: UUID,
    user: Annotated[User, Depends(require_permission("documents:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChunkListResponse:
    document = await owned(session, user, document_id)
    rows = (
        await session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id, DocumentChunk.is_deleted.is_(False))
            .order_by(DocumentChunk.ordinal)
        )
    ).all()
    return ChunkListResponse(
        items=[
            ChunkResponse(
                id=x.id,
                ordinal=x.ordinal,
                text=x.text,
                page_number=x.page_number,
                section=x.section,
                token_count=x.token_count,
            )
            for x in rows
        ]
    )


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    body: SearchRequest,
    user: Annotated[User, Depends(require_permission("knowledge:search"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> SearchResponse:
    vector = (await provider(settings).embed([body.query]))[0]
    distance = DocumentChunk.embedding.cosine_distance(vector)
    statement = (
        select(DocumentChunk, Document, distance.label("distance"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.owner_id == user.id,
            Document.is_deleted.is_(False),
            Document.status == "ready",
            DocumentChunk.is_deleted.is_(False),
            DocumentChunk.embedding.is_not(None),
        )
    )
    if body.classification:
        statement = statement.where(Document.classification == body.classification)
    if body.document_ids:
        statement = statement.where(Document.id.in_(body.document_ids))
    rows = (await session.execute(statement.order_by(distance).limit(body.limit))).all()
    return SearchResponse(
        items=[
            CitationCandidate(
                document_id=doc.id,
                filename=doc.filename,
                page_number=chunk.page_number,
                section=chunk.section,
                chunk_id=chunk.id,
                text=chunk.text,
                relevance_score=max(0.0, 1.0 - float(dist)),
            )
            for chunk, doc, dist in rows
        ]
    )
