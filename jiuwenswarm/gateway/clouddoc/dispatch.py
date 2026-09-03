"""Hand one cloud-document turn to the agentserver.

The split with the watcher is **policy there, transport here**. Prompts,
conventions injection and fencing are all worked out on the watcher side; this
module only manages the session, sends the turn, and handles timeout and cancel.

There are two timeouts and **this side must be the shorter one**: the transport
caps a request at 600s, so this side takes 540s (600 x 0.9). Matching 600 races
the transport and the exception type that surfaces is not predictable. Going
longer is worse: the wait_for here would never fire, nobody would send
CHAT_CANCEL, and the turn on the agentserver side would run on unbounded.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import CLOUDDOC_CHANNEL_ID
from jiuwenswarm.common.e2a.gateway_normalize import e2a_from_agent_fields
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.gateway.clouddoc.comment_watcher import WatcherConfig
from jiuwenswarm.gateway.clouddoc.cursor_store import CloudDocStore

logger = logging.getLogger(__name__)

# Rotate a document's session after this many turns. Without rotation the context
# grows without bound, until every turn replays hundreds of historical comments.
DEFAULT_SESSION_MAX_TURNS = 50


class CloudDocDispatcher:
    def __init__(
        self,
        agent_client,
        store: CloudDocStore,
        cfg: WatcherConfig,
        *,
        now_fn: Callable[[], float],
        session_max_turns: int = DEFAULT_SESSION_MAX_TURNS,
        cancel_fn: Callable | None = None,
        work_mode: str = "",
    ) -> None:
        self._agent_client = agent_client
        self._store = store
        self._cfg = cfg
        self._now_fn = now_fn
        self._session_max_turns = int(session_max_turns)
        self._cancel_fn = cancel_fn
        self._work_mode = work_mode

    async def _session_for(self, doc_id: str) -> str:
        """The session id for this document, rotating it when due.

        The id carries a monotonic counter rather than a timestamp: ``now_fn`` is an
        injectable fake clock in tests, and two rotations inside one millisecond
        would otherwise collide on the same id.
        """
        sess = await self._store.get_session(doc_id)
        if sess and int(sess.get("turn_count", 0)) < self._session_max_turns:
            return str(sess["session_id"])
        generation = int((sess or {}).get("generation", 0)) + 1
        session_id = f"clouddoc_{doc_id[:12]}_{generation}"
        await self._store.set_session(doc_id, session_id)
        return session_id

    @staticmethod
    def _configured_model_name() -> str:
        """Read clouddoc.model_name live, so a change from the panel reaches the
        next turn without a restart -- the same reason the watcher reads mode live."""
        try:
            from jiuwenswarm.common.config import get_config

            section = get_config().get("clouddoc") or {}
            return str(section.get("model_name") or "").strip()
        except Exception:  # noqa: BLE001 - an unreadable config must not stop dispatch
            return ""

    async def __call__(self, doc_id: str, comment_id: str, payload: dict) -> str:
        session_id = await self._session_for(doc_id)
        prompt = str(payload.get("prompt") or "")
        request_id = f"clouddoc-{comment_id}-{int(self._now_fn())}"

        params = {
            "content": prompt,
            "query": prompt,
            "supports_user_interaction": False,
        }
        if self._work_mode:
            params["work_mode"] = self._work_mode
        model_name = self._configured_model_name()
        if model_name:
            params["model_name"] = model_name

        envelope = e2a_from_agent_fields(
            request_id=request_id,
            channel_id=CLOUDDOC_CHANNEL_ID,
            session_id=session_id,
            req_method=ReqMethod.CHAT_SEND,
            params=params,
            is_stream=False,
            timestamp=self._now_fn(),
            # The authorization scope passes through untouched; the watcher has already
            # guaranteed it holds nothing but doc_id.
            metadata={"clouddoc": dict(payload.get("clouddoc") or {})},
        )

        # The watcher owns the inflight record, because it holds the placeholder reply
        # id and crash recovery runs off exactly that id. A second record written here
        # would have no placeholder, and sweep() would read it as a crash before dispatch.
        try:
            resp = await asyncio.wait_for(
                self._agent_client.send_request(envelope),
                timeout=self._cfg.clamped_turn_timeout(),
            )
        except asyncio.TimeoutError:
            logger.warning("[clouddoc] turn timed out doc=%s comment=%s", doc_id, comment_id)
            await self._cancel(session_id, request_id)
            return ""
        except Exception:  # noqa: BLE001 - one failed turn must not end the watcher loop
            logger.exception("[clouddoc] dispatch failed doc=%s comment=%s", doc_id, comment_id)
            return ""
        finally:
            await self._store.bump_turn_count(doc_id)

        return _text_of(resp, request_id=request_id)

    async def _cancel(self, session_id: str, request_id: str) -> None:
        """A timeout must cancel explicitly.

        Without the cancel, the turn on the agentserver side keeps running and
        **still holds the propose_edit tool**, while this side has already given up
        and the next tick dispatches again -- two proposals from one comment.
        """
        if self._cancel_fn is None:
            return
        try:
            await self._cancel_fn(session_id=session_id, request_id=request_id)
        except Exception:  # noqa: BLE001
            logger.exception("[clouddoc] cancel failed session=%s", session_id)


def _text_of(resp, *, request_id: str = "") -> str:
    """The turn's reply text; **any failure returns an empty string** and the watcher
    writes generic wording instead.

    ``error`` is deliberately absent from the extraction keys. It used to be there,
    and the result was that internal exceptions from the agent runtime were pasted
    verbatim into a user's document -- one real case read ``cannot access local
    variable 'close_agent_run_span'``. Errors are sanitised on the way out: generic
    wording for the reader, detail only in the log.

    A falsy ``ok`` also yields nothing. Even when a failed turn carries back partial
    text, that text went through no further processing and must not pose as a reply.
    """
    payload = getattr(resp, "payload", None)
    if not isinstance(payload, dict):
        return ""
    if getattr(resp, "ok", True) is False or payload.get("error"):
        logger.warning(
            "[clouddoc] turn failed request_id=%s detail=%s",
            request_id, str(payload.get("error") or payload)[:400],
        )
        return ""
    for key in ("content", "text", "result"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    # A turn that succeeded and said nothing. The reader gets generic wording either
    # way, so without this line the log holds no trace of the turn at all -- and the
    # cause is never in the turn itself but upstream (an interrupt with nobody to
    # answer it, a round that ended on a tool call), which is exactly what makes it
    # worth a line saying which request to go looking for.
    logger.warning(
        "[clouddoc] turn returned no text request_id=%s payload_keys=%s",
        request_id, sorted(payload),
    )
    return ""
