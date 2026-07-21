"""Document ingestion and retrieval API contracts."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    media_type: str
    byte_size: int
    status: Literal["uploaded", "processing", "ready", "failed"]
    failure_code: str | None
    classification: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]


class ChunkResponse(BaseModel):
    id: UUID
    ordinal: int
    text: str
    page_number: int | None
    section: str | None
    token_count: int | None


class ChunkListResponse(BaseModel):
    items: list[ChunkResponse]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=10, ge=1, le=50)
    classification: str | None = Field(default=None, min_length=1, max_length=50)
    document_ids: list[UUID] | None = Field(default=None, max_length=100)


class CitationCandidate(BaseModel):
    document_id: UUID
    filename: str
    page_number: int | None
    section: str | None
    chunk_id: UUID
    text: str
    relevance_score: float


class SearchResponse(BaseModel):
    items: list[CitationCandidate]
