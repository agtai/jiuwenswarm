"""The permission scene for an unattended cloud-document turn: closed set, no interrupt.

The host's permission rail decides every tool call through a scene hook. On an
unattended turn there is nobody to answer an approval prompt, so a tool outside
the turn's closed set must be *refused* -- a decision the model can act on --
rather than parked behind an interrupt that times out. This module is that
decision; the rail calls ``unattended_scene`` first, before its ``ask_user``
bypass and before its own early returns, and goes on as before when the answer
is ``None``.

**The turn is recognised from the caller's snapshot, not from contextvars.** The
hook runs while a tool is executing, one task removed from the request that
bound the contextvars, so a request-scoped flag reads False there. The adapter
that owns the turn supplies a ``snapshot`` callable. A caller without one (team
members, the code adapter) falls back to the turn readers, which are the
contextvars and therefore never recognise an unattended turn from inside a tool
call; the host may install another fallback.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

TurnSnapshot = Callable[[], "dict[str, Any] | None"]

_fallback: TurnSnapshot | None = None


def set_fallback_snapshot(provider: TurnSnapshot | None) -> None:
    """Install the snapshot used when a caller supplies none. None restores the
    default, which reads the turn readers.
    """
    global _fallback
    _fallback = provider


def _turn_readers_snapshot() -> dict[str, Any] | None:
    from jiuwenswarm.clouddoc.host import turn

    if not turn.is_unattended_turn():
        return None
    return {"mode": turn.turn_mode()}


def resolve_unattended_turn(snapshot: TurnSnapshot | None) -> dict[str, Any] | None:
    """This turn's authorization snapshot, or None outside an unattended turn.

    **Never raises.** A resolver that threw would be caught by the rail, logged as a
    scene-hook failure and then fall through to the tiered engine -- which for a
    write tool means an approval interrupt on a turn with nobody to answer it,
    exactly the silent stall this hook exists to prevent.
    """
    provider = snapshot if snapshot is not None else _fallback
    if provider is None:
        provider = _turn_readers_snapshot
    try:
        turn = provider()
    except Exception:  # noqa: BLE001
        logger.warning("[clouddoc] turn snapshot failed", exc_info=True)
        return None
    return turn if isinstance(turn, dict) and turn else None


def unattended_scene(
    tool_name: str, snapshot: TurnSnapshot | None
) -> tuple[str] | tuple[str, str] | None:
    """The scene verdict for one tool call: ``("approve",)``, ``("reject", why)``, or
    ``None`` when the turn is not an unattended cloud-document turn.

    The allowlist is a **literal family keyed by watch mode**, never set
    subtraction: written as a subtraction it would let removed tools back in. The
    family has a single member (``apply_scoped``, the only level a watch is granted
    at), so any other mode -- missing, stale, retired -- resolves to the empty set
    and every tool is rejected. That is the backstop; the watcher already refuses
    to dispatch such a turn.
    """
    from jiuwenswarm.clouddoc.tools.toolkit import unattended_allowlist_for

    turn = resolve_unattended_turn(snapshot)
    if turn is None:
        return None
    allowed = unattended_allowlist_for(turn.get("mode"))
    if tool_name in allowed:
        return ("approve",)
    return (
        "reject",
        f"[PERMISSION_DENIED] 无人值守的云文档会话只允许 {sorted(allowed)}；{tool_name} 不在其中",
    )
