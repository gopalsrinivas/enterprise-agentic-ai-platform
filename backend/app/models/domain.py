"""Phase 3 persistence schema; later phases add domain behavior."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MutableAuditMixin, UuidPrimaryKeyMixin


class Document(MutableAuditMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("byte_size >= 0", name="ck_documents_byte_size_nonnegative"),
        CheckConstraint(
            "status IN ('uploaded','processing','ready','failed')", name="ck_documents_status"
        ),
        Index("ix_documents_owner_status_updated", "owner_id", "status", "updated_at"),
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    filename: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    media_type: Mapped[str] = mapped_column(String(255))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    failure_code: Mapped[str | None] = mapped_column(String(100))
    classification: Mapped[str] = mapped_column(String(50), default="internal")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class DocumentChunk(MutableAuditMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_document_chunks_document_ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_document_chunks_ordinal_nonnegative"),
        CheckConstraint(
            "token_count IS NULL OR token_count >= 0", name="ck_chunks_tokens_nonnegative"
        ),
        Index("ix_document_chunks_document", "document_id"),
    )
    document_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="RESTRICT"))
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(255))
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(1536))
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class Conversation(MutableAuditMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')", name="ck_conversations_status"),
        Index("ix_conversations_owner_updated", "owner_id", "updated_at"),
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class Message(MutableAuditMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_messages_conversation_sequence"),
        CheckConstraint("sequence >= 0", name="ck_messages_sequence_nonnegative"),
        CheckConstraint("role IN ('user','assistant','system','tool')", name="ck_messages_role"),
        CheckConstraint("status IN ('pending','completed','failed')", name="ck_messages_status"),
    )
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="RESTRICT")
    )
    author_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    sequence: Mapped[int] = mapped_column(Integer)
    safety_decision: Mapped[str | None] = mapped_column(String(32))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class MessageCitation(UuidPrimaryKeyMixin, Base):
    __tablename__ = "message_citations"
    __table_args__ = (
        UniqueConstraint("message_id", "rank", name="uq_message_citations_message_rank"),
        CheckConstraint("rank >= 0", name="ck_message_citations_rank_nonnegative"),
    )
    message_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("messages.id", ondelete="RESTRICT"))
    chunk_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("document_chunks.id", ondelete="RESTRICT")
    )
    rank: Mapped[int] = mapped_column(Integer)
    relevance_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    quoted_text: Mapped[str | None] = mapped_column(Text)


class AgentExecution(UuidPrimaryKeyMixin, Base):
    __tablename__ = "agent_executions"
    __table_args__ = (
        CheckConstraint(
            "input_token_count IS NULL OR input_token_count >= 0", name="ck_agent_input_tokens"
        ),
        CheckConstraint(
            "output_token_count IS NULL OR output_token_count >= 0", name="ck_agent_output_tokens"
        ),
        CheckConstraint(
            "estimated_cost IS NULL OR estimated_cost >= 0", name="ck_agent_cost_nonnegative"
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0", name="ck_agent_latency_nonnegative"
        ),
        CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_agent_executions_status",
        ),
        Index(
            "ix_agent_executions_conversation_status_started",
            "conversation_id",
            "status",
            "started_at",
        ),
        Index("ix_agent_executions_trace", "trace_id"),
    )
    conversation_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="RESTRICT")
    )
    message_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="RESTRICT")
    )
    parent_execution_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_executions.id", ondelete="RESTRICT")
    )
    agent_type: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    input_token_count: Mapped[int | None] = mapped_column(Integer)
    output_token_count: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    trace_id: Mapped[str | None] = mapped_column(String(64))


class ApprovalRequest(UuidPrimaryKeyMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','expired','executing','executed','failed')",
            name="ck_approval_requests_status",
        ),
        CheckConstraint("version >= 1", name="ck_approval_requests_version"),
        Index("ix_approval_requests_status_expiry", "status", "expires_at"),
    )
    agent_execution_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("agent_executions.id", ondelete="RESTRICT")
    )
    requested_by: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    tool_name: Mapped[str] = mapped_column(String(255))
    argument_preview: Mapped[dict[str, Any]] = mapped_column(JSON)
    argument_digest: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1)


class ToolExecution(UuidPrimaryKeyMixin, Base):
    __tablename__ = "tool_executions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_tool_executions_idempotency_key"),
        UniqueConstraint("approval_request_id", name="uq_tool_executions_approval"),
        CheckConstraint(
            "status IN ('pending','running','completed','failed')",
            name="ck_tool_executions_status",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0", name="ck_tool_latency_nonnegative"
        ),
    )
    agent_execution_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("agent_executions.id", ondelete="RESTRICT")
    )
    approval_request_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_requests.id", ondelete="RESTRICT")
    )
    tool_name: Mapped[str] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    safe_input: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    safe_output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))


class AuditLog(UuidPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_occurred", "occurred_at"),
        Index("ix_audit_logs_actor", "actor_id"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_request", "request_id"),
        Index("ix_audit_logs_action", "action"),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[UUID | None] = mapped_column(Uuid)
    outcome: Mapped[str] = mapped_column(String(32))
    request_id: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    source_ip_hash: Mapped[str | None] = mapped_column(String(128))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class EvaluationRun(UuidPrimaryKeyMixin, Base):
    __tablename__ = "evaluation_runs"
    dataset_version: Mapped[str] = mapped_column(String(100))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aggregate_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    report_uri: Mapped[str | None] = mapped_column(String(1024))


class EvaluationResult(UuidPrimaryKeyMixin, Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id", "metric_name", name="uq_evaluation_result_metric"),
    )
    run_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("evaluation_runs.id", ondelete="RESTRICT")
    )
    case_id: Mapped[str] = mapped_column(String(255))
    execution_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_executions.id", ondelete="RESTRICT")
    )
    metric_name: Mapped[str] = mapped_column(String(100))
    score: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    passed: Mapped[bool] = mapped_column(Boolean)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)
