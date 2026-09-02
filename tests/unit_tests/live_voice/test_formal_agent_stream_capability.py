# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ScopeRef,
    TurnCommit,
)
from jiuwenswarm.server.live_voice.jiuwenswarm_agent_adapter import (
    _text_stream_capability,
)
from jiuwenswarm.server.live_voice.jiuwenswarm_round_harness import (
    HarnessRoundViolation,
    JiuWenSwarmRoundHarness,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FORMAL_APPEND_ONLY_DELTA_CAPABILITY,
    FormalAgentExecution,
    FormalContextSnapshot,
)
from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm


class AppendOnlyLowerAdapter:
    _is_code_agent = False
    _is_session_scoped_adapter = False

    def formal_live_voice_text_capabilities(self) -> tuple[str, ...]:
        return (FORMAL_APPEND_ONLY_DELTA_CAPABILITY,)

    async def process_formal_live_voice_stream_impl(
        self, request, _inputs
    ) -> AsyncIterator[AgentResponseChunk]:
        for event_type, content in (
            ("chat.delta", "First sentence. "),
            ("chat.delta", "More follows"),
            ("chat.final", "First sentence. More follows."),
        ):
            yield AgentResponseChunk(
                request_id=request.request_id,
                channel_id=request.channel_id,
                payload={"event_type": event_type, "content": content},
                is_complete=event_type == "chat.final",
            )


def execution() -> FormalAgentExecution:
    scope = ScopeRef("subject-1", "project-1", "session-1", Assurance.AUTHENTICATED)
    commit = TurnCommit.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "commit_id": "commit-1",
            "turn_id": "turn-1",
            "interaction_id": "interaction-1",
            "text": "Tell me about Paris.",
            "hypothesis_provenance": {"provider": "test.sr"},
            "scope": scope.to_dict(),
            "context_refs": [],
            "committed_at": "2026-08-26T08:00:00Z",
        }
    )
    return FormalAgentExecution(
        request_id="request-1",
        channel_id="web",
        internal_session_id="lv-formal-capability-1",
        commit=commit,
        context=FormalContextSnapshot(scope),
        allow_tools=False,
    )


@pytest.mark.asyncio
async def test_real_facade_stamps_exact_append_only_capability() -> None:
    facade = JiuWenSwarm()
    facade._adapter = AppendOnlyLowerAdapter()  # type: ignore[assignment]
    facade._build_inputs = lambda request: (  # type: ignore[method-assign]
        {
            "conversation_id": request.session_id,
            "enable_memory": False,
            "skip_a2ui": True,
        },
        "off",
        object(),
    )

    assert facade.formal_live_voice_text_capabilities() == (
        FORMAL_APPEND_ONLY_DELTA_CAPABILITY,
    )
    chunks = [
        chunk
        async for chunk in facade.process_formal_live_voice_stream(execution())
    ]

    assert [chunk.payload["text_stream_capability"] for chunk in chunks] == [
        FORMAL_APPEND_ONLY_DELTA_CAPABILITY,
        FORMAL_APPEND_ONLY_DELTA_CAPABILITY,
        FORMAL_APPEND_ONLY_DELTA_CAPABILITY,
    ]


def test_missing_capability_falls_back_but_unknown_capability_fails_closed() -> None:
    assert _text_stream_capability({"event_type": "chat.delta"}) == "agent.chat"
    assert _text_stream_capability(
        {
            "event_type": "chat.delta",
            "text_stream_capability": FORMAL_APPEND_ONLY_DELTA_CAPABILITY,
        }
    ) == FORMAL_APPEND_ONLY_DELTA_CAPABILITY

    with pytest.raises(HarnessRoundViolation) as invalid:
        _text_stream_capability(
            {
                "event_type": "chat.delta",
                "text_stream_capability": "agent.chat.mutable_delta.v1",
            }
        )
    assert invalid.value.reason == "INVALID_FORMAL_AGENT_OUTPUT"


def test_harness_rejects_forged_or_unknown_text_capabilities() -> None:
    current = execution()
    forged = AgentResponseChunk(
        request_id=current.request_id,
        channel_id=current.channel_id,
        payload={
            "event_type": "chat.delta",
            "content": "unsafe",
            "text_stream_capability": FORMAL_APPEND_ONLY_DELTA_CAPABILITY,
        },
        is_complete=False,
    )

    with pytest.raises(HarnessRoundViolation) as undeclared:
        JiuWenSwarmRoundHarness._validate_chunk(forged, current, ())
    assert undeclared.value.reason == "INVALID_FORMAL_AGENT_OUTPUT"

    class UnknownFacade:
        def formal_live_voice_text_capabilities(self) -> tuple[str, ...]:
            return ("agent.chat.mutable_delta.v1",)

    with pytest.raises(HarnessRoundViolation) as unknown:
        JiuWenSwarmRoundHarness._formal_text_capabilities(UnknownFacade())
    assert unknown.value.reason == "INVALID_FORMAL_AGENT_OUTPUT"
