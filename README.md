# Enterprise Multi-Agent Knowledge and Workflow Assistant

A production-oriented reference platform for secure enterprise knowledge retrieval and approval-gated workflows. It combines a FastAPI API, PostgreSQL/pgvector, LangGraph specialist agents, an extensible LLM gateway, MCP-compatible tools, and a Next.js interface.

> Status: Phase 1 architecture and planning only. No application business logic has been implemented.

## Intended capabilities

- JWT authentication and role-based access control (RBAC)
- Secure document ingestion and citation-backed RAG
- A LangGraph supervisor coordinating RAG, SQL, workflow, and safety agents
- OpenAI and Anthropic provider adapters with validated structured outputs
- MCP-compatible tools with human approval for sensitive actions
- Layered prompt-injection, data-exfiltration, SQL, and hallucination controls
- Audit logging, evaluation, metrics, and distributed tracing
- Local Docker Compose and production-style Kubernetes/GCP/Terraform deployment

## Architecture at a glance

```text
Browser -> Next.js -> FastAPI /api/v1 -> authentication/RBAC
                                      -> LangGraph supervisor
                                         |-> safety agent
                                         |-> RAG agent -> pgvector/documents
                                         |-> SQL agent -> read-only data access
                                         `-> workflow agent -> approval -> MCP tools
                                      -> LLM gateway -> OpenAI / Anthropic
                                      -> PostgreSQL (application + audit state)
                                      -> logs, metrics, traces, evaluations
```

The backend is the security boundary. The browser never receives provider keys, database credentials, system prompts, or unrestricted tool access. See [the architecture](docs/architecture.md), [API design](docs/api-design.md), and [database design](docs/database-design.md).

## Planned repository layout

```text
backend/          FastAPI application, migrations, and tests
frontend/         Next.js App Router application and tests
docs/             Architecture, API, database, and phase specifications
infra/            Docker, Kubernetes, Terraform, and observability config
.github/          CI/CD workflows and repository automation
```

## Delivery plan

Development is intentionally split into the phase specifications under `docs/`: backend foundation; identity and schema; document ingestion/RAG; LLM gateway; LangGraph agents; MCP and approvals; safety; evaluation and observability; frontend; containers; deployment; and final audit.

## Local development

Phase 1 has no runtime dependencies or startup command. Phase 2 will introduce the backend environment, `.env.example`, migrations, linting, typing, and tests. Phase 10 adds the frontend, and Phase 11 provides the documented one-command local environment.

Never commit `.env` files, credentials, private keys, generated uploads, or production data. The root `.gitignore` provides baseline protection, but secrets must also be managed using local environment variables and a cloud secret manager.

## Documentation acceptance

Phase 1 is complete when the architecture and trust boundaries, repository structures, entity relationships, agent responsibilities, API surface, security controls, implementation phases, assumptions, risks, and acceptance criteria are documented without implementation code.
