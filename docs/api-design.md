# API Design

## 1. Conventions

- JSON REST endpoints are rooted at `/api/v1`; operational probes remain unversioned.
- Request and response bodies use versioned Pydantic schemas and OpenAPI-generated JSON Schema.
- IDs are UUIDs. Times are UTC RFC 3339 strings. Collection endpoints use cursor pagination with bounded `limit`.
- Protected endpoints require `Authorization: Bearer <access-token>` and service-level RBAC/resource checks.
- Mutation endpoints accept an `Idempotency-Key` where retries could duplicate work.
- Responses include `X-Request-ID`; clients may supply a valid request ID, otherwise the API creates one.
- Secrets, password hashes, raw tokens, internal prompts, provider errors, and unrestricted model traces are never response fields.

Success bodies use resource-specific schemas. Errors use:

```json
{
  "error": {
    "code": "stable_machine_code",
    "message": "Safe human-readable message",
    "request_id": "uuid",
    "details": []
  }
}
```

Expected status codes include `400` invalid semantics, `401` unauthenticated, `403` unauthorized, `404` absent/inaccessible resource, `409` invalid state or idempotency conflict, `413` oversized upload, `415` unsupported media, `422` schema failure, `429` throttled, and safe `5xx` dependency/server failures.

## 2. Endpoint inventory

### Operations

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/health` | Public/internal policy | Process liveness only |
| GET | `/ready` | Internal policy | Required dependency readiness, with sanitized detail |

### Authentication and identity

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/register` | Development/config-gated | Register a test/development user |
| POST | `/api/v1/auth/login` | Public, throttled | Issue access and refresh tokens |
| POST | `/api/v1/auth/refresh` | Valid refresh token | Rotate refresh token and issue access token |
| POST | `/api/v1/auth/logout` | Authenticated | Revoke the refresh session/token family |
| GET | `/api/v1/users/me` | Authenticated | Current user profile and effective roles/permissions |
| GET | `/api/v1/users` | `users:read` | Paginated user administration |
| GET | `/api/v1/users/{user_id}` | `users:read` | User detail |
| PATCH | `/api/v1/users/{user_id}` | `users:write` | Update allowed profile/status fields |
| GET | `/api/v1/roles` | `roles:read` | List roles and permissions |
| PUT | `/api/v1/users/{user_id}/roles` | `roles:assign` | Replace role assignments with an audit event |

### Documents and retrieval

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/v1/documents` | `documents:write` | Multipart upload; return document and processing status |
| GET | `/api/v1/documents` | `documents:read` | List only authorized documents |
| GET | `/api/v1/documents/{document_id}` | Resource access | Metadata and processing status |
| DELETE | `/api/v1/documents/{document_id}` | Owner or `documents:delete` | Soft-delete document and remove it from retrieval |
| POST | `/api/v1/documents/{document_id}/reprocess` | `documents:write` | Retry eligible failed processing idempotently |
| GET | `/api/v1/documents/{document_id}/chunks` | Resource access/admin policy | Paginated chunk metadata; text exposure is policy controlled |
| POST | `/api/v1/search` | `knowledge:search` | Authorized semantic search returning citation candidates |

### Conversations and orchestration

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/v1/conversations` | `chat:use` | Create a conversation |
| GET | `/api/v1/conversations` | `chat:use` | List caller-owned/authorized conversations |
| GET | `/api/v1/conversations/{conversation_id}` | Resource access | Conversation metadata |
| GET | `/api/v1/conversations/{conversation_id}/messages` | Resource access | Paginated message history and citations |
| POST | `/api/v1/conversations/{conversation_id}/messages` | Resource access | Submit a turn and return a completed typed response |
| POST | `/api/v1/conversations/{conversation_id}/messages:stream` | Resource access | Submit a turn and stream typed server-sent events |
| GET | `/api/v1/agent-executions/{execution_id}` | Owner or `executions:read` | Sanitized route, status, timings, usage, and child executions |
| POST | `/api/v1/agent-executions/{execution_id}/cancel` | Owner or `executions:cancel` | Best-effort cancellation of an eligible execution |

### Approvals and tools

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/approvals` | `approvals:review` | Filtered approval inbox |
| GET | `/api/v1/approvals/{approval_id}` | Requester or reviewer | Immutable preview, status, expiry, and sanitized context |
| POST | `/api/v1/approvals/{approval_id}/approve` | `approvals:approve` | Atomically approve an eligible request |
| POST | `/api/v1/approvals/{approval_id}/reject` | `approvals:approve` | Atomically reject with an optional reason |
| POST | `/api/v1/approvals/{approval_id}/execute` | Authorized executor/service | Execute an approved action once after revalidation |
| GET | `/api/v1/tool-executions/{execution_id}` | Related user or `executions:read` | Sanitized tool execution status/result |

Tool proposal creation is normally internal to the workflow agent and message endpoint, preventing callers from bypassing orchestration policy. A future direct proposal endpoint must enforce the identical service policy.

### Audit and evaluation

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/audit-logs` | `audit:read` | Cursor-paginated, filterable audit events; no mutation endpoint |
| GET | `/api/v1/evaluations/runs` | `evaluations:read` | Evaluation run summaries |
| POST | `/api/v1/evaluations/runs` | `evaluations:execute` | Start an offline evaluation run |
| GET | `/api/v1/evaluations/runs/{run_id}` | `evaluations:read` | Metrics, status, and report reference |

## 3. Chat response contract

A completed response contains `message_id`, `conversation_id`, `agent_execution_id`, selected `agent`, `answer`, typed `citations`, optional sanitized `tool_proposal`, `approval_status`, `safety_decision`, usage metadata permitted by policy, and timestamps. A citation contains document ID, filename, page/section, chunk ID, and relevance score; the server verifies it references retrieved authorized context.

Streaming uses `text/event-stream`. Events are ordered and typed: `execution.started`, `agent.selected`, `response.delta`, `citation`, `tool.proposed`, `approval.required`, `safety.decision`, `response.completed`, and `error`. Each event includes an event ID and execution ID. Only `response.completed` represents the durable final response; clients reconnect with `Last-Event-ID` when supported.

## 4. Approval state contract

```text
pending -> approved -> executing -> executed
   |          |             `----> failed (retry policy controlled)
   |          `------------------> expired (if not executing)
   +----> rejected
   `----> expired
```

Transitions use a transaction and a version/check value. Approval does not mean execution: the execute step rechecks expiry, actor permissions, tool availability, argument digest, and idempotency. Terminal decisions cannot be overwritten.

## 5. API security and compatibility

- OpenAPI documents authentication and permission requirements without embedding secrets or internal policies.
- File endpoints enforce extension, detected MIME type, size, and resource authorization before parsing or downloading.
- Rate limits differ for login, upload, chat/model, search, approval, and evaluation workloads.
- Breaking contract changes require a new API/schema version; additive fields remain optional to older clients.
- Contract tests validate OpenAPI, structured model/tool schemas, error envelopes, authorization failures, and SSE event parsing.
