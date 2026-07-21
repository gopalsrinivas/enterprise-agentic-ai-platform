"""Phase 3 schema inventory and public-contract redaction tests."""

import app.models  # noqa: F401
from app.db.base import Base
from app.schemas.identity import UserResponse


def test_all_approved_phase_three_tables_are_declared() -> None:
    assert set(Base.metadata.tables) == {
        "users",
        "roles",
        "permissions",
        "user_roles",
        "role_permissions",
        "refresh_sessions",
        "documents",
        "document_chunks",
        "conversations",
        "messages",
        "message_citations",
        "agent_executions",
        "tool_executions",
        "approval_requests",
        "audit_logs",
        "evaluation_runs",
        "evaluation_results",
    }


def test_public_user_schema_has_no_secret_fields() -> None:
    fields = set(UserResponse.model_fields)
    assert not fields.intersection({"password", "password_hash", "token_hash", "refresh_token"})
