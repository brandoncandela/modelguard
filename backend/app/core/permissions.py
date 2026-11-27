"""Role-based access control. Ownership and independence rules are enforced in the services."""
from __future__ import annotations

from typing import Dict, FrozenSet

ALL = "*"

ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    "admin": frozenset({
        "inventory:read", "inventory:create", "inventory:edit", "inventory:archive",
        "monitoring:read", "monitoring:run", "monitoring:configure", "monitoring:simulate", "breach:acknowledge",
        "validation:read", "validation:schedule", "validation:approve",
        "finding:read", "finding:respond", "finding:accept_risk", "finding:extend",
        "ai:read", "ai:edit", "ai:assess", "ai:eval_run", "ai:template_edit", "ai:bias_test",
        "regulatory:read", "regulatory:edit", "regulatory:test",
        "report:read", "report:generate", "audit:read", "user:read", "user:admin",
    }),
    "model_owner": frozenset({
        "inventory:read", "inventory:create", "inventory:edit",
        "monitoring:read", "monitoring:run", "monitoring:configure", "breach:acknowledge",
        "validation:read",
        "finding:read", "finding:respond",
        "ai:read", "ai:edit", "ai:assess",
        "regulatory:read",
        "report:read", "report:generate", "user:read",
    }),
    "validator": frozenset({
        "inventory:read",
        "monitoring:read", "monitoring:run", "breach:acknowledge",
        "validation:read", "validation:perform",
        "finding:read", "finding:create", "finding:close",
        "ai:read", "ai:eval_run", "ai:bias_test",
        "regulatory:read", "regulatory:test",
        "report:read", "report:generate", "audit:read", "user:read",
    }),
    "compliance_reviewer": frozenset({
        "inventory:read",
        "monitoring:read",
        "validation:read", "validation:schedule", "validation:approve",
        "finding:read", "finding:accept_risk", "finding:extend",
        "ai:read", "ai:review", "ai:template_edit",
        "regulatory:read", "regulatory:edit", "regulatory:test",
        "report:read", "report:generate", "audit:read", "user:read",
    }),
}

ROLE_LABELS = {
    "admin": "Administrator",
    "model_owner": "Model Owner",
    "validator": "Validator",
    "compliance_reviewer": "Compliance Reviewer",
}


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def permissions_for(role: str):
    return sorted(ROLE_PERMISSIONS.get(role, frozenset()))
