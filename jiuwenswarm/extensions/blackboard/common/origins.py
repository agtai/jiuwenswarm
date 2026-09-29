"""Which web pages may open the host's WebSockets (the same rule as the document service's origins.ts).

Browsers always send ``Origin`` on a WebSocket; members' own jiuwenswarm instances do not. Members'
web apps normally run on their own machine, so loopback origins are allowed; any other page needs
``blackboard.host.allowed_origins`` or ``allow_any_origin``.
"""

from __future__ import annotations

from urllib.parse import urlparse

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def normalize_origin(origin: str) -> str:
    return origin.strip().lower().rstrip("/")


def origin_allowed(origin: str | None, allowed: tuple[str, ...] | list[str], allow_any: bool) -> bool:
    if not origin or allow_any:
        return True
    value = normalize_origin(origin)
    if value in allowed:
        return True
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    return parsed.hostname in _LOOPBACK or parsed.hostname.endswith(".localhost")
