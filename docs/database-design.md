# Database Design

## 1. Storage strategy

PostgreSQL 16+ is the authoritative application store; pgvector stores chunk embeddings. SQLAlchemy 2.x async mappings and Alembic manage schema evolution. Application and migration identities are separate. The SQL agent never queries this database directly and uses a separate read-only business-data connection.

UUID primary keys and UTC timezone-aware timestamps are used throughout. Core mutable tables include `created_at`, `updated_at`, `created_by`, `updated_by`, and `is_deleted`; bootstrap/system writes may use nullable actor fields tied to a documented system identity. Security and execution history is append-oriented and not silently overwritten.

## 2. Relationship overview

```text
User --< UserRole >-- Role
User --< RefreshSession
User --< Document --< DocumentChunk
User --< Conversation --< Message
Conversation --< AgentExecution --< ToolExecution
AgentExecution --< ApprovalRequest --0..1 ToolExecution
Message --< MessageCitation >-- DocumentChunk
User/requests/resources --< AuditLog
EvaluationRun --< EvaluationResult
```

`created_by`/`updated_by` audit foreign keys are omitted from the diagram for clarity.

## 3. Core entities

### Identity and authorization

| Entity | Important fields | Rules/indexes |
|---|---|---|
| `User` | email, display_name, password_hash, status, last_login_at | Case-normalized unique email among active records; hash never selected into API schemas |
| `Role` | name, description, permissions JSON/association | Unique stable name; permissions validated against an application registry |
| `UserRole` | user_id, role_id, assigned_by, assigned_at | Unique active `(user_id, role_id)`; audited assignment/revocation |
| `RefreshSession` | user_id, token_hash, family_id, expires_at, revoked_at, replaced_by_id | Store only one-way token hashes; indexes on user/family/expiry support rotation and revocation |

### Knowledge and chat

| Entity | Important fields | Rules/indexes |
|---|---|---|
| `Document` | owner_id, filename, storage_key, media_type, byte_size, checksum, status, failure_code, classification, metadata | Status enum `uploaded/processing/ready/failed`; indexes on owner/status; storage key is not a public URL |
| `DocumentChunk` | document_id, ordinal, text, page_number, section, token_count, embedding, embedding_model, metadata | Unique `(document_id, ordinal)`; vector index selected after workload measurement; chunks inherit document access |
| `Conversation` | owner_id, title, status, metadata | Index owner/update time; authorization required for every access |
| `Message` | conversation_id, author_user_id, role, content, status, sequence, safety_decision, metadata | Unique `(conversation_id, sequence)`; sensitive content retention is configurable |
| `MessageCitation` | message_id, chunk_id, rank, relevance_score, quoted_text | Unique message/rank; chunk must be among authorized retrieval results used for the answer |

Document sharing beyond owner/admin access should use an explicit `DocumentAccessGrant(document_id, principal_type, principal_id, permission)` table rather than embedding ad hoc ACL arrays. It is introduced when sharing behavior is implemented.

### Agent, tool, approval, and audit

| Entity | Important fields | Rules/indexes |
|---|---|---|
| `AgentExecution` | conversation_id, message_id, parent_execution_id, agent_type, provider, model, status, input/output token counts, estimated_cost, latency_ms, started_at, completed_at, error_code, trace_id | Hierarchical execution tree; safe metadata only; indexes on conversation/status/start time/trace |
| `ApprovalRequest` | agent_execution_id, requested_by, tool_name, argument_preview, argument_digest, status, expires_at, decided_by, decided_at, decision_reason, version | Status check constraint; optimistic version; one active logical request/idempotency key; immutable preview/digest |
| `ToolExecution` | agent_execution_id, approval_request_id, tool_name, idempotency_key, status, started_at, completed_at, latency_ms, safe_input, safe_output, error_code | Unique idempotency key; at most one execution per approval; never store credentials |
| `AuditLog` | occurred_at, actor_id, action, resource_type, resource_id, outcome, request_id, trace_id, source_ip_hash, metadata | Append-only application permissions; indexes on time, actor, resource, request, action; partition by time if needed |

### Evaluation

| Entity | Important fields | Rules/indexes |
|---|---|---|
| `EvaluationRun` | dataset_version, configuration, status, started_at, completed_at, aggregate_metrics, report_uri | Configuration excludes credentials; immutable dataset/config snapshot |
| `EvaluationResult` | run_id, case_id, execution_id, metric_name, score, passed, evidence | Unique `(run_id, case_id, metric_name)`; evidence is sanitized and retention-controlled |

## 4. Common columns and lifecycle rules

Mutable domain tables use:

- `id UUID PRIMARY KEY`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`
- `created_by UUID NULL REFERENCES users(id)`
- `updated_by UUID NULL REFERENCES users(id)`
- `is_deleted BOOLEAN NOT NULL DEFAULT FALSE`

Soft deletion is performed in services, cascades logically to dependent retrieval/read queries, and is included in audit logs. Partial unique indexes should exclude deleted rows when a value may be reused. Physical purge is a privileged retention job, not an API delete side effect. `AuditLog` is append-only and uses an explicit retention marker rather than ordinary soft-deletion semantics.

Foreign-key behavior is conservative: `RESTRICT` for audit/identity history and explicit service-managed lifecycle for documents, conversations, and executions. Database cascades are used only where deletion cannot erase evidence unexpectedly.

## 5. Integrity and concurrency

- Enums/check constraints restrict document, message, execution, approval, and tool states.
- Money/cost uses fixed precision; token counts, sizes, ranks, scores, and timeouts have non-negative checks.
- Approval decisions lock the row or compare `version`; execution claims the approved request atomically.
- The persisted idempotency key and unique constraint prevent duplicated sensitive actions.
- Message sequence allocation and finalization occur transactionally.
- Embedding dimension is tied to the configured embedding model and changed only through a migration/re-index plan.
- Application queries default to `is_deleted = false`; repositories make inclusion of deleted records explicit.

## 6. Data protection

- Passwords use Argon2id hashes; refresh tokens and API-token-like values are stored as keyed/one-way hashes.
- Provider keys, database passwords, MCP credentials, raw access/refresh tokens, and encryption keys are never database fields in these entities.
- Sensitive document/message/tool fields require classification, access controls, encryption at rest, minimal retention, and redaction in logs and evaluation evidence.
- Model prompts and responses are not duplicated into `AgentExecution` by default; reference authorized messages and store bounded safe metadata.
- Backups are encrypted and access logged. Production restoration and deletion/retention procedures require testing.
- All data access routes through authorization-aware repositories. RAG applies access predicates before vector ranking, not after returning candidates.

## 7. Migration and performance approach

- Alembic revisions are reviewed, deterministic, and validated on empty and representative databases.
- Destructive changes use expand/migrate/contract deployment steps and explicit rollback/forward-recovery plans.
- Initial B-tree indexes cover foreign keys and common `(owner_id, status, updated_at)` or time-based filters.
- Choose HNSW or IVFFlat and tuning parameters only after corpus/latency measurements; always combine vector search with authorization and metadata filters.
- Large audit/execution tables may be time-partitioned. Retention jobs operate in bounded batches.
- Query plans, pool saturation, lock waits, table growth, and vector recall/latency are monitored before adding complexity.

## 8. Open design items before production

- Final tenant-isolation model and whether row-level security is required.
- Durable job queue and document object-storage provider.
- Exact document-sharing principals and permissions.
- Embedding model/dimension and vector-index choice from measured corpus size.
- Region-specific retention, legal hold, PII, and data-residency rules.
- Audit immutability mechanism (restricted table, export/WORM store, or both) and recovery objectives.
