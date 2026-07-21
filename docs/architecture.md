# System Architecture

## 1. Purpose and scope

The Enterprise Multi-Agent Knowledge and Workflow Assistant provides authenticated users with grounded enterprise answers and controlled business workflows. The architecture treats model output, uploaded content, retrieved text, and tool responses as untrusted. FastAPI remains the authorization and policy-enforcement boundary; agents propose decisions but never bypass deterministic controls.

This document is the Phase 1 architecture decision record. It describes target state, not implemented behavior.

## 2. Assumptions

- The first deployment is a single enterprise tenant, while records carry ownership and access metadata so tenant isolation can be added later.
- PostgreSQL is the system of record and pgvector is sufficient for the initial retrieval scale.
- External LLM calls are permitted only for data approved by deployment policy; sensitive deployments may disable a provider.
- The business database queried by the SQL agent is logically separate from the application database and is accessed through read-only credentials.
- Ticket, email, and notification integrations start as deterministic local fakes and later use MCP servers.
- A human approver has an explicit permission and cannot approve an expired, rejected, or already executed action.
- Background document processing may begin in-process for development, but production uses a durable worker/queue abstraction.

## 3. Context and trust boundaries

```text
[Untrusted browser]
       |
   TLS + JWT
       v
[Next.js UI] ---- same authenticated API contract ----> [FastAPI]
                                                        | auth/RBAC
                                                        | validation/rate limits
                                                        | safety policy
                           +----------------------------+------------------+
                           |                            |                  |
                    [LangGraph]                 [PostgreSQL]       [Observability]
                   supervisor + agents          app/audit/vector    redacted telemetry
                           |
                    [LLM gateway]
                      /          \
              [OpenAI API]  [Anthropic API]
                           |
                    [Tool registry]
                           |
                 approval state machine
                           |
               [MCP/external systems]
```

Trust boundaries exist at browser/API, API/provider, upload/parser, retrieved-content/model, agent/tool, application/business database, and service/telemetry interfaces. Every crossing requires schema validation, authorization, bounded timeouts, safe errors, and redaction.

## 4. Logical components

| Component | Responsibility |
|---|---|
| Next.js frontend | Authentication UX, chat streaming, document management, approvals, execution details, evaluation and admin views |
| FastAPI API | Versioned transport, validation, JWT verification, RBAC, orchestration entry points, safe error mapping |
| Application services | Transaction boundaries and use cases independent of HTTP and model vendors |
| LangGraph supervisor | Classifies a request, selects the minimum necessary specialist, persists/checkpoints workflow state, returns a typed result |
| LLM gateway | Provider-neutral completion, streaming, structured output, tool calling, fallback, retry, circuit breaking, usage/cost metadata |
| Retrieval pipeline | Validates and parses uploads, chunks content, creates embeddings, stores vectors, applies access filters, returns citations |
| Tool registry | Typed MCP-compatible tool metadata, permission and approval policy, timeout/retry/audit behavior |
| Approval service | Durable propose/approve/reject/expire/execute-once state machine |
| PostgreSQL/pgvector | Identity, documents, conversations, execution state, approvals, audits, embeddings, evaluations |
| Observability | Correlated structured logs, OpenTelemetry traces, Prometheus metrics, evaluation reports with sensitive-data minimization |

## 5. Primary request flows

### Grounded chat

1. FastAPI authenticates the user, validates input, applies rate limits, and creates request/execution records.
2. Safety pre-check returns `allow`, `block`, or `require_review` using deterministic critical rules.
3. The supervisor selects the RAG, SQL, or workflow specialist and records its routing decision.
4. Retrieval and SQL operations enforce user authorization at query time. Retrieved text is labeled untrusted.
5. The gateway obtains a typed model response. The backend validates structure and citations and performs an output safety check.
6. The API streams safe events and stores the final message, citations, model usage, latency, and audit metadata.

### Sensitive workflow

1. The workflow agent may propose, but not execute, an action.
2. The tool registry validates arguments, caller permission, tool policy, and whether approval is required.
3. The service stores an immutable preview and argument digest in a pending approval with an expiry.
4. An authorized human approves or rejects it. Self-approval can be prohibited by policy.
5. Execution revalidates status, expiry, permission, and digest, obtains an idempotency key, and runs at most once.
6. Tool result and audit records are persisted; secrets and sensitive payloads are redacted.

### Document ingestion

1. Validate filename, extension, detected MIME type, size, and access policy; malware scanning is a production gate.
2. Store the source outside the public web root and create a `Document` in `uploaded` state.
3. A bounded parser extracts and normalizes text; safety inspection treats content as hostile data.
4. Split text into traceable chunks, generate embeddings through an adapter, and store chunks/vectors transactionally.
5. Mark the document `ready`, or record a sanitized error and `failed` status. Search excludes non-ready and unauthorized documents.

## 6. Agent boundaries and responsibilities

| Agent | Responsibilities | Prohibited behavior |
|---|---|---|
| Supervisor | Intent classification, specialist routing, workflow state, response assembly | Direct database/tool access; bypassing safety or RBAC |
| RAG | Authorized retrieval, grounded synthesis, citation emission, insufficient-evidence response | Claims unsupported by retrieved context; access-filter changes |
| SQL | Produce and run bounded read-only queries through the SQL service; return typed tabular data | DML/DDL, arbitrary schemas/functions, application DB access |
| Workflow | Convert intent into validated action proposals and approval requests | Executing approval-required actions itself |
| Safety | Inspect prompts, documents, context, outputs, and tool traffic; return typed policy decisions | Being the sole control for authorization or critical deterministic rules |

All agent inputs and outputs use versioned Pydantic schemas. The graph state contains identifiers and minimal working context rather than secrets or unrestricted raw records.

## 7. Planned folder structures

```text
backend/
  alembic/                  database migrations
  app/
    api/v1/                 versioned routers and dependencies
    agents/                 graph, supervisor, specialist nodes, state
    core/                   configuration, logging, errors, telemetry
    db/                     async session, base, migration helpers
    evaluations/            datasets, metrics, runner, reports
    llm/                    provider interface and adapters
    models/                 SQLAlchemy persistence models
    repositories/           data access and authorization-aware queries
    schemas/                Pydantic request/response/event contracts
    security/               JWT, passwords, RBAC, guardrails, redaction
    services/               application use cases and transactions
    tools/                  registry, policies, MCP clients, local fakes
    main.py                  application factory/entry point
  tests/
    unit/
    integration/
    contract/
  pyproject.toml

frontend/
  app/                       App Router pages/layouts
    (auth)/
    chat/
    documents/
    approvals/
    executions/
    evaluations/
    admin/
  components/                accessible reusable UI
  lib/                       API client, auth, validation, utilities
  hooks/                     client-side behaviors
  types/                     generated/shared API-facing types
  tests/                     unit and integration tests
  e2e/                       browser journeys
  package.json

infra/
  docker/
  kubernetes/
  terraform/environments/
  observability/
```

Dependencies point inward: API and agents call services; services call repositories/providers/tools through interfaces. Persistence models do not become public response schemas.

## 8. Major architectural decisions

| ID | Decision | Rationale and consequence |
|---|---|---|
| ADR-001 | Modular monolith first | Keeps transactions and local development manageable; boundaries permit later extraction |
| ADR-002 | FastAPI is the policy boundary | Model and frontend decisions are never trusted for authorization |
| ADR-003 | PostgreSQL plus pgvector | One transactional platform for metadata and initial vector search; revisit at measured scale |
| ADR-004 | LangGraph with persisted typed state | Makes routing, approval interruption, resumption, and execution traces explicit |
| ADR-005 | Provider-neutral LLM gateway | Supports OpenAI, Anthropic, deterministic tests, fallback, and centralized telemetry |
| ADR-006 | Human approval is a durable state machine | Enables expiry, concurrency control, auditability, and exactly-once tool invocation |
| ADR-007 | Structured contracts everywhere | Pydantic/JSON Schema validation constrains agent, provider, API, and tool boundaries |
| ADR-008 | Defense in depth for AI safety | Deterministic gates protect critical boundaries; model classifiers are supplementary |
| ADR-009 | Soft deletion and immutable security events | Supports recovery and audit investigations; audit records are append-only |
| ADR-010 | Async API with durable workers for heavy work | Avoids blocking requests and supports retries; requires queue/worker selection before production |

## 9. Security controls

- TLS externally; secure headers and restricted CORS; CSRF protections if browser cookies are introduced.
- Short-lived access JWTs, rotated/revocable refresh tokens, Argon2id password hashing, generic authentication errors, and login throttling.
- Deny-by-default RBAC at endpoint, service, document-query, agent, and tool boundaries; database least privilege.
- UUID identifiers, ownership/access filters, soft deletion, and prevention of insecure direct object references.
- Strict Pydantic input limits; parameterized SQL; read-only SQL credentials, AST allowlist, row/time limits, and blocked DDL/DML.
- Upload size/type/signature checks, sanitized names, isolated storage/parsing, decompression limits, and malware scanning.
- Direct/indirect prompt-injection detection, explicit untrusted-context delimiters, tool allowlists, output/citation validation, and evidence thresholds.
- Secrets supplied at runtime through a secret manager; never logs, source control, images, prompts, error bodies, or client bundles.
- Approval expiry, optimistic concurrency, immutable previews/digests, idempotency keys, separation of duties where configured, and post-approval revalidation.
- Append-only audit events with actor, action, resource, outcome, correlation ID, and sanitized metadata; protected retention and access.
- Dependency, secret, and container scanning; pinned builds/SBOMs; non-root containers; network policies and minimal cloud IAM.
- Logs/traces exclude full sensitive prompts by default and use field-level redaction and configurable retention.

## 10. Reliability and observability

- Timeouts, bounded exponential retries with jitter, circuit breakers, idempotency, connection pooling, and graceful degradation.
- `/health` reports process liveness; `/ready` checks required dependencies without exposing details.
- Correlation/request, conversation, agent execution, tool execution, and trace identifiers propagate across calls.
- Metrics cover traffic, errors, latency, tokens, estimated cost, retrieval, citations, safety, approvals, and tools.
- Backups, restore exercises, migration rollback/roll-forward plans, and recovery objectives must be defined before production.

## 11. Implementation phases

1. Architecture and contracts (this phase).
2. FastAPI foundation, configuration, async database, Alembic, logging, health, quality tooling.
3. Core schema, authentication, token lifecycle, and RBAC.
4. Secure ingestion, pgvector retrieval, document authorization, and citations.
5. Multi-provider LLM gateway and validated structured outputs.
6. LangGraph supervisor and RAG, SQL, workflow, and safety agents.
7. MCP-compatible tools and durable human approvals.
8. Layered AI guardrails and citation/hallucination controls.
9. Evaluation datasets/runner plus logs, traces, and metrics.
10. Accessible Next.js frontend.
11. Containerized local end-to-end environment.
12. CI/CD, Kubernetes, GCP, and Terraform.
13. Final security/quality audit, runbooks, and interview-ready documentation.

Each phase begins only after the preceding phase's diff, acceptance criteria, tests, lint, and types are verified.

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Prompt injection causes unsafe disclosure/action | Treat context as data, deterministic gates, minimal tool permissions, approval, output validation |
| Hallucinated or mismatched citations | Evidence-only RAG prompt, chunk ID validation, relevance threshold, insufficient-evidence response, evaluation |
| Cross-user data leakage | Authorization-aware repository queries and tests; never filter only after retrieval |
| Duplicate approved actions | Transactional state transition, row locking/versioning, idempotency key, result persistence |
| Provider outage/cost growth | Timeouts, circuit breaker, fallback policy, quotas, token/cost telemetry |
| Malicious or oversized documents | Layered validation, isolation, scanner, parser limits, asynchronous processing |
| Generated SQL harms systems | Separate read-only DB identity, AST allowlist, parameterization, statement timeout and row limit |
| Audit/log data leaks | Data classification, redaction, restricted access, retention controls, no raw prompts by default |
| Long-running ingestion blocks API | Durable worker abstraction and status polling; no production in-process work |
| Schema/provider coupling slows change | Adapter interfaces, migrations, contract tests, versioned schemas |

## 13. Phase 1 acceptance criteria

- Architecture, components, trust boundaries, and critical flows are documented.
- Backend and frontend target structures and dependency direction are defined.
- Database entities, cardinalities, lifecycle rules, indexes, and sensitive-data guidance are documented separately.
- Every required agent has a bounded responsibility and explicit prohibition.
- The versioned API endpoint inventory, common conventions, streaming contract, errors, and authorization are defined.
- Security controls cover identity, RBAC, uploads, RAG, SQL, agents, tools, approvals, secrets, telemetry, infrastructure, and supply chain.
- All implementation phases are sequenced without Phase 1 business logic.
- Major decisions, assumptions, risks, and mitigations are explicit.
- README explains purpose, status, structure, documentation, and secret-handling expectations.
