"""Errors that cross process and network boundaries as ``{code, message, details}``."""

from __future__ import annotations

from typing import Any

UNAUTHORIZED = "unauthorized"
NOT_MEMBER = "not_member"
FORBIDDEN = "forbidden"
NOT_FOUND = "not_found"
INVALID = "invalid"
CONFLICT = "conflict"
EXPIRED = "expired"
DISABLED = "disabled"
UNAVAILABLE = "unavailable"
# Another mandate holds the document.
BUSY = "busy"
# Milestone 7: an IM account nobody connected, and too many calls in a minute.
NOT_LINKED = "not_linked"
RATE_LIMITED = "rate_limited"
INTERNAL = "internal"


class BlackboardError(Exception):
    """An error with a stable code that callers and agents can act on."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}

    @classmethod
    def from_dict(cls, data: Any) -> "BlackboardError":
        if not isinstance(data, dict):
            return cls(INTERNAL, str(data))
        details = data.get("details")
        return cls(
            str(data.get("code") or INTERNAL),
            str(data.get("message") or "request failed"),
            details if isinstance(details, dict) else {},
        )


def invalid(message: str, **details: Any) -> BlackboardError:
    return BlackboardError(INVALID, message, details)


def not_found(message: str, **details: Any) -> BlackboardError:
    return BlackboardError(NOT_FOUND, message, details)
