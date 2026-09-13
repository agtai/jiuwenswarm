# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import threading

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ScopeRef,
    TurnCommit,
)
from jiuwenswarm.server.live_voice.agent_bridge import (
    AgentBridgePort,
    AgentBridgeViolation,
    AgentEvent,
)


def commit() -> TurnCommit:
    scope = ScopeRef("subject", "project", "session", Assurance.AUTHENTICATED)
    return TurnCommit.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "commit_id": "commit-1",
            "turn_id": "turn-1",
            "interaction_id": "interaction-1",
            "text": "hello",
            "hypothesis_provenance": {"provider": "fake"},
            "scope": scope.to_dict(),
            "context_refs": [],
            "committed_at": "2026-08-04T08:00:00Z",
        }
    )


def test_submit_returns_before_slow_handler_and_preserves_provenance() -> None:
    release = threading.Event()
    entered = threading.Event()
    port = AgentBridgePort(max_workers=1)

    def handler(request):
        entered.set()
        release.wait(timeout=2)
        return (
            AgentEvent(
                request.request_id,
                request.interaction_id,
                request.turn_id,
                request.commit_id,
                0,
                "agent.output",
                request.source_provenance,
                text="ok",
                capability="agent.chat",
            ),
        )

    accepted, future = port.submit("request-1", commit(), handler)
    assert accepted is True
    assert entered.wait(timeout=1)
    assert future.done() is False
    release.set()
    event = future.result(timeout=1)[0]
    assert (event.interaction_id, event.turn_id, event.commit_id) == (
        "interaction-1",
        "turn-1",
        "commit-1",
    )
    assert event.source_provenance == '{"provider":"fake"}'
    assert not hasattr(event, "task_command")
    port.close()


def test_duplicate_request_reuses_future_and_conflict_rejects() -> None:
    port = AgentBridgePort(max_workers=1)

    def handler(request):
        return ()

    _, first = port.submit("request-1", commit(), handler)
    accepted, replay = port.submit("request-1", commit(), handler)
    assert accepted is False
    assert replay is first
    changed = TurnCommit.from_dict({**commit().to_dict(), "text": "changed"})
    with pytest.raises(AgentBridgeViolation) as raised:
        port.submit("request-1", changed, handler)
    assert raised.value.reason == "REQUEST_ID_CONFLICT"
    port.close()


def test_invalid_handler_event_fails_closed() -> None:
    port = AgentBridgePort(max_workers=1)

    def handler(request):
        return (
            AgentEvent(
                "wrong",
                request.interaction_id,
                request.turn_id,
                request.commit_id,
                0,
                "agent.output",
                request.source_provenance,
            ),
        )

    _, future = port.submit("request-1", commit(), handler)
    with pytest.raises(AgentBridgeViolation) as raised:
        future.result(timeout=1)
    assert raised.value.reason == "INVALID_AGENT_EVENT_PROVENANCE"
    port.close()
