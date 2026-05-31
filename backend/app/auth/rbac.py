"""Phase 10C — RBAC: Roles and their permissions.

Roles: Owner > Admin > Manager > Engineer > Finance > Viewer
"""

from __future__ import annotations

# All available permissions
PERMISSIONS = {
    "can_view_dashboard",
    "can_manage_users",
    "can_manage_providers",
    "can_manage_gateway",
    "can_manage_billing",
    "can_view_financials",
    "can_view_aws",
    "can_manage_aws",
    "can_manage_workloads",
    "can_view_analytics",
    "can_use_gateway",
    "can_transfer_ownership",
    "can_delete_organization",
    "can_view_audit_logs",
    "can_manage_teams",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "Owner": PERMISSIONS.copy(),  # Full control — everything

    "Admin": {
        "can_view_dashboard",
        "can_manage_users",
        "can_manage_providers",
        "can_manage_gateway",
        "can_view_financials",
        "can_view_aws",
        "can_manage_aws",
        "can_manage_workloads",
        "can_view_analytics",
        "can_use_gateway",
        "can_view_audit_logs",
        "can_manage_teams",
    },

    "Manager": {
        "can_view_dashboard",
        "can_view_analytics",
        "can_manage_workloads",
        "can_use_gateway",
        "can_view_aws",
    },

    "Engineer": {
        "can_view_dashboard",
        "can_use_gateway",
        "can_view_analytics",
    },

    "Finance": {
        "can_view_dashboard",
        "can_view_financials",
        "can_view_analytics",
    },

    "Viewer": {
        "can_view_dashboard",
    },
}


def has_permission(role: str, permission: str) -> bool:
    """Return True if the given role has the requested permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())


def get_permissions(role: str) -> set[str]:
    """Return the full permission set for a role."""
    return ROLE_PERMISSIONS.get(role, set()).copy()
