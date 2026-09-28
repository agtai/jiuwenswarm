"""Timestamps: ISO-8601 in UTC with milliseconds, which sort as text."""

from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
