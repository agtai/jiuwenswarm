# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Scope-bound formal presentation adapter for the shared AgentRuntime.

This object borrows the host runtime and its configured facade. It owns no
scheduler, Agent, history store, or runtime lifecycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import ScopeRef
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.runtime.service import AgentRuntime, RuntimeStateError
from jiuwenswarm.runtime.session import RuntimeSessionState
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalAgentExecution,
    FormalLiveVoiceViolation,
)


class RuntimeFormalAgentFacade:
    """A host-created capability for one authenticated public session scope."""

    def __init__(
        self, *, runtime: AgentRuntime | None, agent: Any, scope: ScopeRef,
        agent_channel_id: str, mode: str, project_dir: str,
        sub_mode: str | None = None,
    ) -> None:
        self._runtime = runtime
        self._agent = agent
        self._scope = scope
        self._agent_channel_id = agent_channel_id
        self._mode = mode
        self._project_dir = project_dir
        self._sub_mode = sub_mode
        snapshot = (
            runtime.session_coordinator.snapshot_session(scope.session_id)
            if isinstance(runtime, AgentRuntime) and scope.session_id else None
        )
        # Activation binds an existing generation. An unbound capability never
        # adopts a future Session merely because its public ID is reused.
        self._generation = snapshot.generation if snapshot is not None else None
        self._tool_sessions: dict[str, FormalAgentExecution] = {}
        self._gated_sessions: set[str] = set()

    def supports_formal_live_voice(self) -> bool:
        probe = getattr(self._agent, "supports_formal_live_voice", None)
        return callable(probe) and bool(probe())

    def supports_speculative_dialogue(self) -> bool:
        probe = getattr(self._agent, "supports_speculative_dialogue", None)
        return (
            self.supports_formal_live_voice()
            and (not callable(probe) or bool(probe()))
            and all(callable(getattr(self._agent, name, None)) for name in (
                "pause_formal_tools", "resume_formal_tools", "abort_formal_tools",
            ))
        )

    def _require_binding(self) -> AgentRuntime:
        runtime = self._runtime
        if not isinstance(runtime, AgentRuntime) or runtime.closed:
            raise RuntimeStateError("FORMAL_SHARED_RUNTIME_UNAVAILABLE")
        if not self._scope.session_id:
            raise RuntimeStateError("FORMAL_PUBLIC_SESSION_REQUIRED")
        retained = runtime.agent_manager.get_agent_nowait(
            channel_id=self._agent_channel_id, mode=self._mode,
            project_dir=self._project_dir, sub_mode=self._sub_mode,
        )
        if retained is not self._agent:
            raise RuntimeStateError("FORMAL_AGENT_BINDING_CHANGED")
        snapshot = runtime.session_coordinator.snapshot_session(self._scope.session_id)
        if snapshot is None or self._generation is None:
            raise RuntimeStateError("FORMAL_SESSION_NOT_BOUND")
        if snapshot.state in {RuntimeSessionState.CLOSED, RuntimeSessionState.QUIESCING}:
            raise RuntimeStateError("FORMAL_SESSION_CLOSED")
        if snapshot.generation != self._generation:
            raise RuntimeStateError("FORMAL_SESSION_GENERATION_CHANGED")
        return runtime

    def _validate_execution(self, execution: FormalAgentExecution) -> None:
        if not isinstance(execution, FormalAgentExecution):
            raise TypeError("formal execution requires a trusted host input")
        execution.context.validate_for(execution.commit)
        if execution.commit.scope != self._scope:
            raise FormalLiveVoiceViolation(
                "FORMAL_CONTEXT_SCOPE_MISMATCH", "formal facade belongs to another scope",
            )
        if execution.internal_session_id == self._scope.session_id:
            raise FormalLiveVoiceViolation(
                "FORMAL_EXECUTION_NOT_ISOLATED", "formal execution requires an isolated SDK session",
            )
        self._require_binding()

    def prepare_formal_execution(self, execution: FormalAgentExecution) -> None:
        """Bind a trusted execution before a speculative caller pauses tools."""
        self._validate_execution(execution)
        existing = self._tool_sessions.get(execution.internal_session_id)
        if existing is not None and existing != execution:
            raise RuntimeStateError("FORMAL_TOOL_SESSION_BINDING_CONFLICT")
        self._tool_sessions[execution.internal_session_id] = execution

    def _require_tool_session(self, session_id: str) -> None:
        if not isinstance(session_id, str) or session_id not in self._tool_sessions:
            raise RuntimeStateError("FORMAL_TOOL_SESSION_NOT_OWNED")

    def _release_tool_session(self, session_id: str) -> None:
        self._tool_sessions.pop(session_id, None)
        self._gated_sessions.discard(session_id)

    def release_formal_execution(self, session_id: str) -> None:
        """Forget a settled speculative lease; performs no SDK operation."""
        self._release_tool_session(session_id)

    def pause_formal_tools(self, session_id: str) -> None:
        self._require_tool_session(session_id)
        self._require_binding()
        self._agent.pause_formal_tools(session_id)
        self._gated_sessions.add(session_id)

    def resume_formal_tools(self, session_id: str) -> None:
        self._require_tool_session(session_id)
        self._require_binding()
        self._agent.resume_formal_tools(session_id)

    def abort_formal_tools(self, session_id: str) -> None:
        self._require_tool_session(session_id)
        # Exact retained cleanup remains possible after Runtime closes; an
        # arbitrary SDK session never gains this cleanup authority.
        self._agent.abort_formal_tools(session_id)
        self._release_tool_session(session_id)

    async def process_formal_live_voice_stream(
        self, execution: FormalAgentExecution,
    ) -> AsyncIterator[AgentResponseChunk]:
        def validate() -> None:
            self._validate_execution(execution)
            if self._tool_sessions.get(execution.internal_session_id) != execution:
                raise RuntimeStateError("FORMAL_TOOL_SESSION_NOT_OWNED")

        self.prepare_formal_execution(execution)
        validate()
        runtime = self._require_binding()
        request = AgentRequest(
            request_id=execution.request_id, channel_id=execution.channel_id,
            session_id=self._scope.session_id, req_method=ReqMethod.CHAT_SEND,
            params={}, is_stream=True, enable_memory=False,
        )

        async def produce() -> AsyncIterator[AgentResponseChunk]:
            validate()
            stream = self._agent.process_formal_live_voice_stream(execution)
            try:
                async for chunk in stream:
                    # Project only this producer's exact request. Labels remain
                    # provenance, never authority to select another producer.
                    if (chunk.request_id != execution.request_id
                            or chunk.channel_id != execution.channel_id):
                        raise RuntimeStateError("FORMAL_OUTPUT_SCOPE_MISMATCH")
                    payload = chunk.payload if isinstance(chunk.payload, dict) else {}
                    expected = {
                        "source_session_id": execution.internal_session_id,
                        "source_request_id": execution.request_id,
                        "source_origin_request_id": execution.request_id,
                    }
                    if any(key in payload and payload[key] != value
                           for key, value in expected.items()):
                        raise RuntimeStateError("FORMAL_OUTPUT_SOURCE_MISMATCH")
                    yield chunk
            finally:
                await stream.aclose()

        stream = runtime.stream_owned(request, producer=produce, validate=validate)
        try:
            async for event in stream:
                if not event.ok:
                    raise RuntimeStateError(str((event.payload or {}).get("error") or "FORMAL_EXECUTION_FAILED"))
                yield AgentResponseChunk(
                    request_id=event.request_id, channel_id=event.channel_id,
                    payload=event.payload, is_complete=event.is_complete,
                    agent_ref=event.agent_ref, metadata=event.metadata or {},
                )
        finally:
            try:
                await stream.aclose()
            finally:
                if execution.internal_session_id not in self._gated_sessions:
                    self._release_tool_session(execution.internal_session_id)
