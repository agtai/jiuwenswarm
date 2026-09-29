"""Runs comment and chat tasks on this member's own agent (milestone 5).

The host offers a turn with a ``blackboard.mandate.run`` event. The dispatcher picks the session
(the one the person chose, else the workspace's default session, created the first time), attaches
it to the workspace so the agent has Blackboard's tools, claims the turn, sends the prompt to the
AgentServer on the ``__blackboard__`` channel, and reports how the turn ended. A
``blackboard.mandate.stop`` event interrupts a running turn. Turns offered while this jiuwenswarm
was away are picked up when its link to the host is back.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from jiuwenswarm.extensions.blackboard.client.prompt import build_turn_prompt
from jiuwenswarm.extensions.blackboard.common import protocol as p
from jiuwenswarm.extensions.blackboard.common.errors import BlackboardError

if TYPE_CHECKING:
    from jiuwenswarm.extensions.blackboard.client.runtime import ClientRuntime

logger = logging.getLogger(__name__)

CHANNEL = "__blackboard__"
# The host marks a turn Unknown after 600 s without a report; give up a little before.
TURN_TIMEOUT_S = 540.0
SESSION_CREATE_TIMEOUT_S = 60.0
REPORT_ATTEMPTS = 3


@dataclass
class _Turn:
    task: asyncio.Task
    session_id: str | None = None
    request_id: str | None = None


def answer_text(payload: Any) -> str:
    """The agent's final answer from a unary AgentServer response."""
    if not isinstance(payload, dict):
        return ""
    content = payload.get("content")
    if isinstance(content, dict):
        output = content.get("output")
        return output if isinstance(output, str) else ("" if output is None else str(output))
    if isinstance(content, str):
        return content
    text = payload.get("text") or payload.get("answer")
    return text if isinstance(text, str) else ""


def _error_text(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("error", "message", "content"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "the agent could not run the task"


class MandateDispatcher:
    def __init__(self, runtime: "ClientRuntime", agent_client: Any) -> None:
        self._runtime = runtime
        self._client = agent_client
        self._turns: dict[str, _Turn] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}

    # ---- events from the host ----

    def offer(self, host_id: str, payload: dict[str, Any]) -> None:
        mandate_id = payload.get("mandate_id")
        workspace_id = payload.get("workspace_id")
        if not isinstance(mandate_id, str) or not isinstance(workspace_id, str) or mandate_id in self._turns:
            return
        task = asyncio.get_running_loop().create_task(
            self._run(host_id, mandate_id, workspace_id, payload.get("session_id"), str(payload.get("workspace_title") or "")),
            name=f"blackboard.turn.{mandate_id}",
        )
        self._turns[mandate_id] = _Turn(task)
        task.add_done_callback(lambda _: self._turns.pop(mandate_id, None))

    def stop(self, host_id: str, payload: dict[str, Any]) -> None:
        """The mandate was cancelled on the host: interrupt its turn; nothing is reported."""
        del host_id
        turn = self._turns.get(str(payload.get("mandate_id")))
        if turn is not None:
            turn.task.cancel()

    async def resume(self, host_id: str) -> None:
        """Pick up the turns the host offered while this jiuwenswarm was away."""
        try:
            pending = await self._runtime.call(host_id, p.MANDATE_PENDING, {})
        except BlackboardError as exc:
            logger.warning("blackboard: asking %s for waiting tasks failed: %s", host_id, exc.message)
            return
        for run in pending.get("runs", []):
            self.offer(host_id, run)

    async def close(self) -> None:
        turns = list(self._turns.values())
        for turn in turns:
            turn.task.cancel()
        await asyncio.gather(*(t.task for t in turns), return_exceptions=True)

    # ---- one turn ----

    async def _run(self, host_id: str, mandate_id: str, workspace_id: str, session_id: Any, title: str) -> None:
        turn = self._turns[mandate_id]
        try:
            session = session_id if isinstance(session_id, str) and session_id else await self._default_session(host_id, workspace_id, title)
            await self._runtime.attach_session(session, host_id, workspace_id)
            claim = await self._runtime.call(host_id, p.MANDATE_CLAIM, {"mandate_id": mandate_id, "session_id": session})
        except BlackboardError as exc:
            # Someone else's jiuwenswarm claimed it, it ended meanwhile, or the host refused.
            logger.info("blackboard: task %s not started: %s", mandate_id, exc.message)
            return
        except Exception:  # noqa: BLE001 - a session that cannot be made fails the claim; the host times it out
            logger.exception("blackboard: preparing task %s failed", mandate_id)
            return

        turn_id = claim["turn_id"]
        material = claim.get("prompt") or {}
        request_id = f"bb-{turn_id}"
        turn.session_id, turn.request_id = session, request_id
        prompt = build_turn_prompt(material)
        envelope = self._envelope(
            request_id=request_id,
            session_id=session,
            method="CHAT_SEND",
            params={
                "query": prompt,
                "content": prompt,
                "mode": "agent",
                "work_mode": "work",
                "supports_user_interaction": False,
            },
            metadata={
                "blackboard": {
                    "host": host_id,
                    "workspace_id": workspace_id,
                    "workspace_title": (material.get("workspace") or {}).get("title", title),
                    "mandate_id": mandate_id,
                    "origin": material.get("origin", ""),
                }
            },
        )
        status, text, reason = "done", "", None
        try:
            response = await self._client.send_request(envelope, timeout=TURN_TIMEOUT_S)
            payload = response.payload
            if response.ok:
                text = answer_text(payload)
            else:
                status, reason = "failed", _error_text(payload)
        except asyncio.CancelledError:
            await asyncio.shield(self._interrupt(session, request_id))
            raise
        except Exception as exc:  # noqa: BLE001 - every ending is reported to the host
            if type(exc).__name__ == "AgentServerUnaryTimeout":
                await self._interrupt(session, request_id)
                status, reason = "unknown", "timeout"
            else:
                logger.exception("blackboard: task %s failed in the agent", mandate_id)
                status, reason = "failed", str(exc) or type(exc).__name__
        await self._report(host_id, {"mandate_id": mandate_id, "turn_id": turn_id, "status": status, "text": text, "reason": reason})

    async def _report(self, host_id: str, params: dict[str, Any]) -> None:
        for attempt in range(REPORT_ATTEMPTS):
            try:
                await self._runtime.call(host_id, p.MANDATE_REPORT, params)
                return
            except BlackboardError as exc:
                if exc.code not in ("unavailable", "internal"):
                    logger.warning("blackboard: the host refused the report of %s: %s", params["mandate_id"], exc.message)
                    return
                await asyncio.sleep(2 * (attempt + 1))
        logger.warning("blackboard: could not report task %s; the host will mark it Unknown", params["mandate_id"])

    async def _default_session(self, host_id: str, workspace_id: str, title: str) -> str:
        """The workspace's session on this jiuwenswarm, created the first time a task needs it."""
        key = f"{host_id}/{workspace_id}"
        lock = self._session_locks.setdefault(key, asyncio.Lock())
        async with lock:
            existing = self._runtime.sessions.default_for(host_id, workspace_id)
            if existing:
                return existing
            envelope = self._envelope(
                request_id=f"bb-session-{uuid.uuid4().hex}",
                session_id=None,
                method="SESSION_CREATE",
                params={
                    "create_token": f"blackboard:{uuid.uuid4().hex}",
                    "mode": "agent",
                    "is_swarm": False,
                    "work_mode": "work",
                    "title": (title or "Blackboard")[:100],
                },
            )
            response = await self._client.send_request(envelope, timeout=SESSION_CREATE_TIMEOUT_S)
            payload = response.payload if isinstance(response.payload, dict) else {}
            session_id = str(payload.get("session_id") or payload.get("sessionId") or "").strip()
            if not response.ok or not session_id:
                raise RuntimeError(_error_text(payload))
            await self._runtime.sessions.set_default(host_id, workspace_id, session_id)
            return session_id

    async def _interrupt(self, session_id: str, request_id: str) -> None:
        envelope = self._envelope(
            request_id=f"{request_id}-cancel",
            session_id=session_id,
            method="CHAT_CANCEL",
            params={"intent": "cancel", "mode": "agent", "work_mode": "work", "session_id": session_id},
        )
        try:
            await self._client.send_request(envelope, timeout=30)
        except Exception:  # noqa: BLE001 - best effort; the host already knows how the task ended
            logger.warning("blackboard: interrupting %s failed", request_id, exc_info=True)

    @staticmethod
    def _envelope(*, request_id: str, session_id: str | None, method: str, params: dict[str, Any], metadata: dict[str, Any] | None = None) -> Any:
        """An E2A request; `method` names a ReqMethod member."""
        from jiuwenswarm.common.e2a.gateway_normalize import e2a_from_agent_fields
        from jiuwenswarm.common.schema.message import ReqMethod

        return e2a_from_agent_fields(
            request_id=request_id,
            channel_id=CHANNEL,
            session_id=session_id,
            req_method=ReqMethod[method],
            params=params,
            is_stream=False,
            timestamp=time.time(),
            metadata=metadata,
        )
