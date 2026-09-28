"""Workspace roles and their order."""

from __future__ import annotations

from jiuwenswarm.extensions.blackboard.common.errors import invalid

ROLES = ("viewer", "commenter", "editor", "owner")
ROLE_ORDER = {role: index for index, role in enumerate(ROLES)}
# Owner is never granted by an invite; an owner promotes a member with set_role.
INVITE_ROLES = ("editor", "commenter", "viewer")


def role_at_least(role: str, minimum: str) -> bool:
    return ROLE_ORDER.get(role, -1) >= ROLE_ORDER[minimum]


def validate_role(role: object, allowed: tuple[str, ...] = ROLES) -> str:
    if not isinstance(role, str) or role not in allowed:
        raise invalid(f"role must be one of: {', '.join(allowed)}", field="role")
    return role
