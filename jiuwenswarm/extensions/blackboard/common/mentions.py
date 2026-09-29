"""Mentions in comments and chat messages.

A message gives the agent a task only when both the text and the composer agree: the body contains
``@jiuwen`` as a word, and the structured mentions the composer sent include the agent. Text pasted
from elsewhere, or a mention the composer did not produce, never starts a mandate.
"""

from __future__ import annotations

import re
from typing import Any

from jiuwenswarm.extensions.blackboard.common.errors import invalid

AGENT_HANDLE = "jiuwen"
MAX_MENTIONS = 20

_AGENT = re.compile(r"(^|[^\w@])@jiuwen\b", re.IGNORECASE)


def parse(value: Any) -> list[dict[str, str]]:
    """``[{kind: 'agent'} | {kind: 'user', id}]`` from the composer; anything else is refused."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_MENTIONS:
        raise invalid(f"mentions is a list of at most {MAX_MENTIONS}", field="mentions")
    out: list[dict[str, str]] = []
    for item in value:
        kind = item.get("kind") if isinstance(item, dict) else None
        if kind == "agent":
            entry = {"kind": "agent"}
        elif kind == "user" and isinstance(item.get("id"), str) and item["id"].strip():
            entry = {"kind": "user", "id": item["id"].strip()}
        else:
            raise invalid("a mention is {kind: 'agent'} or {kind: 'user', id}", field="mentions")
        if entry not in out:
            out.append(entry)
    return out


def names_agent(body: str, mentions: list[dict[str, str]]) -> bool:
    return bool(_AGENT.search(body)) and any(m["kind"] == "agent" for m in mentions)


def without_agent(body: str) -> str:
    """The request itself: the body with the agent's mention taken out."""
    stripped = _AGENT.sub(lambda m: m.group(1), body)
    return " ".join(stripped.split())
