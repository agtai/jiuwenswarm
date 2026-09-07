"""The notify-only watcher a personal connection runs (design §13, matrix S.3).

It is the same machine as ``CloudDocCommentWatcher`` -- the same poll, the same
admission, backoff and freeze, the same trigger detection and the same dedup keys
-- with the far end replaced. Where the service watcher dispatches a turn and posts
into the thread, this one hands the person a notice inside their own swarm and
touches the document not at all. That is a rule, not a default: the surface below
overrides every method that could reach the platform with a write and refuses at
the seam, so no later change to the base class can make a personal watcher speak.

What it notices: a comment or reply that @-mentions the person, or a task assigned
to them, written by **somebody else**. The person's own comments are their own, and
the agent's posts are the person's too under this identity -- both carry the
person's open_id, both are skipped by the same test, and the trigger layer's rule
(2) already refuses anything the identity itself wrote.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import ProviderError
from jiuwenswarm.gateway.clouddoc.comment_watcher import CloudDocCommentWatcher
from jiuwenswarm.gateway.clouddoc.triggers import TriggerClass, find_triggers

logger = logging.getLogger(__name__)

# The state scope a personal watcher keeps its keys under. Shared with the panel,
# which reads a personal row's health from the same key.
PERSONAL_SCOPE = "personal"


class PersonalWatcherMustNotPost(RuntimeError):
    """Raised at the seam if anything tries to make a personal watcher write."""


async def _refuse(*_a: Any, **_k: Any) -> None:
    raise PersonalWatcherMustNotPost("a personal connection's watcher never posts")


class PersonalNoticeWatcher(CloudDocCommentWatcher):
    def __init__(
        self,
        provider: Any,
        store: Any,
        trigger_cfg: Any,
        cfg: Any,
        *,
        notify: Callable[[dict], Awaitable[None]],
        now_fn: Callable[[], float],
        sleep_fn: Callable[[float], Awaitable[None]] | None = None,
        connection_id: str = "",
        title_of: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        super().__init__(
            provider, store, trigger_cfg, cfg,
            dispatch=_refuse, now_fn=now_fn, sleep_fn=sleep_fn, registry=None,
        )
        self._notify = notify
        self._connection_id = connection_id
        self._title_of = title_of

    # ------------------------------------------------------------ the seam

    # Every write path of the base class, closed. The base never calls these on
    # this subclass's tick (``_tick_doc`` below does not reach them), but a later
    # change to the base that did would meet the refusal rather than the platform.
    _safe_reply = _refuse           # type: ignore[assignment]
    _safe_reply_id = _refuse        # type: ignore[assignment]
    _safe_update = _refuse          # type: ignore[assignment]
    _safe_delete = _refuse          # type: ignore[assignment]
    _dedupe_own_notices = _refuse   # type: ignore[assignment]
    _unhighlight_resolved = _refuse  # type: ignore[assignment]
    _settle_turn = _refuse          # type: ignore[assignment]
    _ledger_check = _refuse         # type: ignore[assignment]

    # ------------------------------------------------------------ overrides

    def _gate_open(self) -> bool:
        """Notifying is not unattended action, so the D21 mode does not close it;
        the feature switch still does."""
        try:
            from jiuwenswarm.common.config import get_config

            return bool((get_config().get("clouddoc") or {}).get("enabled", True))
        except Exception:  # noqa: BLE001
            return True

    async def sweep(self) -> list[str]:
        """No placeholders were ever posted, so there is nothing to recover."""
        return []

    async def _admit(self, doc_id: str) -> bool:
        """Read access is enough: the watcher only reads comments, and a person may
        well be a commenter on a document they are summoned in. Nothing here warns
        about sharing posture -- the document is somebody else's to share."""
        if doc_id in self._admitted:
            return True
        try:
            caps = await self._provider.capabilities(doc_id)
        except ProviderError as exc:
            logger.warning("[clouddoc] %s 个人身份准入检查失败（%s），本轮跳过", doc_id, exc.kind)
            return False
        self._caps_cache[doc_id] = caps
        if not caps.can_read:
            await self._store.note_permanent_failure(doc_id, "no_read_access")
            return False
        self._admitted.add(doc_id)
        return True

    async def _tick_doc(self, doc_id: str, summary: dict) -> None:
        comments = await self._provider.list_comments(doc_id)
        if await self._seed_if_new(doc_id, comments):
            summary["seeded"] = summary.get("seeded", 0) + 1
            return
        state = (await self._store.snapshot()).get(self._store._key(doc_id)) or {}
        triggered = set(state.get("triggered_ids") or {})
        for t in find_triggers(comments, self._tcfg, doc_id=doc_id, already_triggered=triggered):
            key = t.key_for(doc_id)
            # The key is written first, as on the service path: a notice delivered
            # twice is a nuisance, and one lost to a crash between the two is what
            # the notice store's idempotent ``add`` (keyed on this) papers over.
            await self._store.mark_triggered(doc_id, [key])
            notice = await self._notice_for(doc_id, t, key)
            try:
                await self._notify(notice)
            except Exception:  # noqa: BLE001 - one undeliverable notice must not end the tick
                logger.exception("[clouddoc] notice delivery failed doc=%s", doc_id)
            summary["notified"] = summary.get("notified", 0) + 1

    async def _notice_for(self, doc_id: str, t: Any, key: str) -> dict:
        c = t.comment
        r = t.reply
        me = (self._tcfg.sa_address or "").strip().lower()
        assigned = bool(c.assignee_address) and c.assignee_address.strip().lower() == me
        title = ""
        if self._title_of is not None:
            try:
                title = await self._title_of(doc_id) or ""
            except Exception:  # noqa: BLE001 - a title is decoration
                title = ""
        url = ""
        try:
            url = str(self._provider.doc_url(doc_id) or "")
        except Exception:  # noqa: BLE001
            url = ""
        return {
            "key": key,
            "doc_id": doc_id,
            "title": title,
            "url": url,
            "connection_id": self._connection_id,
            "comment_id": c.comment_id,
            "reply_id": r.reply_id if r else None,
            "kind": "assigned" if (assigned and t.kind is TriggerClass.ASSIGNED) else "mention",
            "author": (r.author_display_name if r else c.author_display_name) or "",
            "quoted_text": c.quoted_text or "",
            "comment": c.content or "",
            "text": (r.content if r else c.content) or "",
            "created_time": (r.created_time if r else c.created_time) or "",
        }
