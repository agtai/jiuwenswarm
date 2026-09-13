# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Process-local execution gate for formal Live Voice sessions.

A speculative dialogue candidate must never execute a tool before the
semantic decision, but its formal session adapter (and the stream-event
rail that pauses tool calls) only comes into existence when its stream
starts. The gate therefore records the intent per formal session id:
``request_pause`` before the stream starts, ``release`` or ``abort`` when
the decision settles. The session adapter consults ``should_pause`` right
after it opens the tool capture, before the first model call, and applies
the pause on its own rail; a release or abort that arrives while the
session adapter already exists is applied to the rail directly by the
facade. Entries are bounded and removed on release or abort.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

_MAX_ENTRIES = 256
_PAUSED = "paused"
_RELEASED = "released"

_lock = threading.Lock()
_entries: "OrderedDict[str, str]" = OrderedDict()


def _require_session(session_id: str) -> str:
    if not isinstance(session_id, str) or not session_id.startswith("lv-formal-"):
        raise RuntimeError("FORMAL_TOOL_GATE_SESSION_INVALID")
    return session_id


def request_pause(session_id: str) -> None:
    """Ask that every tool call of ``session_id`` waits until it is released."""

    key = _require_session(session_id)
    with _lock:
        _entries.pop(key, None)
        _entries[key] = _PAUSED
        while len(_entries) > _MAX_ENTRIES:
            _entries.popitem(last=False)


def should_pause(session_id: str) -> bool:
    """Whether a session adapter must pause its tools when its stream starts."""

    with _lock:
        return _entries.get(session_id) == _PAUSED


def release(session_id: str) -> bool:
    """Let the session execute tools; returns whether a pause was pending."""

    key = _require_session(session_id)
    with _lock:
        return _entries.pop(key, None) == _PAUSED


def abort(session_id: str) -> bool:
    """Forget the session's pause; its tools are aborted by the caller."""

    key = _require_session(session_id)
    with _lock:
        return _entries.pop(key, None) is not None


def snapshot() -> dict[str, int]:
    with _lock:
        return {"pending": sum(1 for state in _entries.values() if state == _PAUSED)}


__all__ = ["abort", "release", "request_pause", "should_pause", "snapshot"]
