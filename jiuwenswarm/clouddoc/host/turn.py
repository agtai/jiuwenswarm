"""Which turn this is: the cross-process authorization payload of an unattended turn.

The watcher dispatches every unattended turn on the cloud-document channel with
the document, the comment and the watch level in the request metadata. The
agentserver binds that request to contextvars for the length of the request's
setup; the readers here are the agentserver's only way of asking "is this turn
unattended, and for which document".

Two rules shape every reader:

* **The discriminator is the channel id, never whether metadata exists.** With
  metadata missing you could not tell this was an unattended turn at all, and
  "missing means refuse" would be unreachable by construction.
* **Unbound reads as None, not as the contextvar's default.** The channel
  contextvar defaults to ``"web"``, which would make "nothing was bound this
  turn" and "genuinely on the web channel" indistinguishable by value, so the
  bound flag is consulted first. Likewise the metadata reader never falls back
  to the previous turn's snapshot, which would have a tool authorizing an
  operation on document B while holding document A's id.

The contextvars belong to the agent adapter; they are read lazily so that this
module imports without it, and a deployment can install another source.
"""

from __future__ import annotations

from typing import Any, Callable

RequestContext = Callable[[], "tuple[bool, str | None, dict[str, Any] | None]"]

_request_context: RequestContext | None = None


def set_request_context(provider: RequestContext | None) -> None:
    """Install the source of ``(bound, channel_id, metadata)`` for the current request.
    Without one, the agent adapter's contextvars are read.
    """
    global _request_context
    _request_context = provider


def _context() -> tuple[bool, str | None, dict[str, Any] | None]:
    if _request_context is not None:
        return _request_context()
    from jiuwenswarm.server.runtime.agent_adapter.interface_deep import (
        _CRON_TOOL_BOUND,
        _CRON_TOOL_CHANNEL_ID,
        _CRON_TOOL_METADATA,
    )

    return bool(_CRON_TOOL_BOUND.get()), _CRON_TOOL_CHANNEL_ID.get(), _CRON_TOOL_METADATA.get()


def request_channel_id() -> str | None:
    """This request's channel id, or None when nothing is bound."""
    bound, channel_id, _ = _context()
    return channel_id if bound else None


def request_metadata() -> dict[str, Any] | None:
    """This request's metadata, or None when nothing is bound."""
    bound, _, metadata = _context()
    return metadata if bound else None


def is_unattended_turn() -> bool:
    """Whether this turn runs inside an unattended cloud-document session."""
    from jiuwenswarm.clouddoc.providers.base import CLOUDDOC_CHANNEL_ID

    return request_channel_id() == CLOUDDOC_CHANNEL_ID


def _payload() -> dict[str, Any]:
    payload = (request_metadata() or {}).get("clouddoc")
    return payload if isinstance(payload, dict) else {}


def turn_doc_id() -> str | None:
    """The document in this turn's authorization scope. None outside an unattended
    turn, where the chat path imposes no constraint; the empty string inside one
    whose payload is missing, since an absent authorization field means no
    authorization.
    """
    if not is_unattended_turn():
        return None
    doc_id = _payload().get("doc_id")
    return doc_id if isinstance(doc_id, str) and doc_id else ""


def turn_comment_id() -> str | None:
    """The comment this turn was summoned under: replies are allowed only there.
    Same None / empty-string contract as ``turn_doc_id``.
    """
    if not is_unattended_turn():
        return None
    comment_id = _payload().get("comment_id")
    return comment_id if isinstance(comment_id, str) and comment_id else ""


def turn_mode() -> str | None:
    """The watch level in this turn's authorization scope. None outside an unattended
    turn; inside one, a missing or non-string value is None too, and the closed-set
    resolver treats that as the strictest level -- the fail direction of an absent
    authorization field is always refusal, never width.
    """
    if not is_unattended_turn():
        return None
    mode = _payload().get("mode")
    return mode if isinstance(mode, str) and mode else None


def turn_progress() -> dict[str, str]:
    """The placeholder reply this turn may narrate its steps into.

    Read from ``clouddoc_progress``, a sibling of the authorization payload rather
    than a field inside it: the dictionary the authorization check reads holds only
    what grants something, and a display-only id gates nothing. Absent, empty or
    malformed means the turn narrates nothing; a progress note is decoration on top
    of the work, and losing it must never cost the work.
    """
    if not is_unattended_turn():
        return {}
    payload = (request_metadata() or {}).get("clouddoc_progress")
    if isinstance(payload, dict):
        rid = payload.get("reply_id")
        if isinstance(rid, str) and rid:
            return {"reply_id": rid, "lang": str(payload.get("lang") or "")}
    return {}
