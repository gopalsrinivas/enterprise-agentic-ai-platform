"""Stable Phase 3 role and permission registry."""

PERMISSIONS: dict[str, str] = {
    "users:read": "Read user profiles",
    "users:write": "Update user profiles",
    "roles:read": "Read roles and permissions",
    "roles:assign": "Assign user roles",
    "documents:read": "Read authorized documents",
    "documents:write": "Create documents",
    "documents:delete": "Delete authorized documents",
    "knowledge:search": "Search knowledge",
    "chat:use": "Use conversations",
    "executions:read": "Read executions",
    "executions:cancel": "Cancel executions",
    "approvals:review": "Review approvals",
    "approvals:approve": "Decide approvals",
    "audit:read": "Read security audits",
    "evaluations:read": "Read evaluations",
    "evaluations:execute": "Run evaluations",
}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset(PERMISSIONS),
    "ai_engineer": frozenset(
        {
            "documents:read",
            "documents:write",
            "knowledge:search",
            "chat:use",
            "executions:read",
            "evaluations:read",
            "evaluations:execute",
        }
    ),
    "business_user": frozenset({"documents:read", "knowledge:search", "chat:use"}),
    "auditor": frozenset(
        {"users:read", "roles:read", "audit:read", "executions:read", "evaluations:read"}
    ),
}
