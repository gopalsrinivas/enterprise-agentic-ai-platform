# Enterprise Multi-Agent Knowledge and Workflow Assistant

A production-oriented reference platform for secure enterprise knowledge retrieval and approval-gated workflows. It combines a FastAPI API, PostgreSQL/pgvector, LangGraph specialist agents, an extensible LLM gateway, MCP-compatible tools, and a Next.js interface.

> Status: Phase 3 core schema, authentication, and RBAC are implemented for review. Document processing and all AI/workflow capabilities remain planned for later phases.

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

## Backend development

Prerequisites are Python 3.12 and, for live readiness/migrations, PostgreSQL 16+. The unit suite does not require PostgreSQL.

```powershell
$python312 = "<path-to-python-3.12-executable>"
& $python312 -m venv "backend\.venv"
& "backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "backend\.venv\Scripts\python.exe" -m pip install -e "backend[dev]"
Copy-Item "backend\.env.example" "backend\.env"
```

Replace the database placeholder in the local untracked `backend/.env`. Run commands from `backend/` so settings load that file:

```powershell
& ".venv\Scripts\python.exe" -m alembic upgrade head
& ".venv\Scripts\python.exe" -m app.cli seed-rbac
& ".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --no-access-log
```

Development registration is disabled by default and can be enabled only with
`REGISTRATION_ENABLED=true` outside production. Create the first administrator explicitly after
the migration and RBAC seed by supplying `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and optionally
`ADMIN_DISPLAY_NAME` through the local process environment, then run:

```powershell
& ".venv\Scripts\python.exe" -m app.cli bootstrap-admin
```

The bootstrap is idempotent, never embeds or prints credentials, and never replaces an existing
administrator's password. Access JWTs are short-lived; opaque refresh tokens are stored only as
keyed hashes and rotate on every refresh. Reuse revokes the entire token family.

The API documentation is at `http://127.0.0.1:8000/docs`. `GET /health` reports process liveness. `GET /ready` verifies PostgreSQL and returns `503` with sanitized detail when it is unavailable. Phase 3 exposes only the approved `/api/v1/auth/*`, `/api/v1/users*`, and `/api/v1/roles` identity endpoints. The application emits one JSON `request_completed` event per request; Uvicorn's duplicate plain-text access log is disabled by the startup command.

Quality checks from `backend/`:

```powershell
& ".venv\Scripts\python.exe" -m ruff format --check .
& ".venv\Scripts\python.exe" -m ruff check .
& ".venv\Scripts\python.exe" -m mypy app tests
& ".venv\Scripts\python.exe" -m pytest
& ".venv\Scripts\python.exe" -m alembic check
```

Phase 10 adds the frontend, and Phase 11 provides the complete containerized local environment.

Never commit `.env` files, credentials, private keys, generated uploads, or production data. The root `.gitignore` provides baseline protection, but secrets must also be managed using local environment variables and a cloud secret manager.

## Documentation acceptance

Phase 1 is complete when the architecture and trust boundaries, repository structures, entity relationships, agent responsibilities, API surface, security controls, implementation phases, assumptions, risks, and acceptance criteria are documented without implementation code.
