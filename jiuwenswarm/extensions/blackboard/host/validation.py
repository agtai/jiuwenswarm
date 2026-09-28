"""Checks on values people type: names, titles, display names."""

from __future__ import annotations

import re
from typing import Any

from jiuwenswarm.extensions.blackboard.common.errors import invalid

WORKSPACE_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")


def text(value: Any, field: str, *, max_len: int, min_len: int = 1) -> str:
    if not isinstance(value, str):
        raise invalid(f"{field} is required", field=field)
    cleaned = " ".join(value.split())
    if not min_len <= len(cleaned) <= max_len:
        raise invalid(f"{field} must be {min_len} to {max_len} characters", field=field)
    return cleaned


def workspace_name(value: Any) -> str:
    """The slug used in ``@bb:name``: 3-40 of a-z, 0-9 and '-', not starting or ending with '-'."""
    if not isinstance(value, str) or not WORKSPACE_NAME.match(value) or "--" in value:
        raise invalid(
            "the handle must be 3 to 40 lower-case letters, digits or '-', not starting or ending with '-'",
            field="name",
        )
    return value


def display_name(value: Any) -> str:
    return text(value, "display_name", max_len=60)


def title(value: Any) -> str:
    return text(value, "title", max_len=120)


def required_str(params: dict[str, Any], field: str) -> str:
    value = params.get(field)
    if not isinstance(value, str) or not value.strip():
        raise invalid(f"{field} is required", field=field)
    return value.strip()


def int_in_range(value: Any, field: str, *, low: int, high: int, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise invalid(f"{field} must be a number", field=field)
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise invalid(f"{field} must be a number", field=field) from exc
    if not low <= number <= high:
        raise invalid(f"{field} must be between {low} and {high}", field=field)
    return number
