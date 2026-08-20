# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from types import SimpleNamespace

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.agent_latency_probe import (
    AgentForegroundLatencyProbeOperation,
)


class _Recorder:
    def __init__(self) -> None:
        self.marks: list[tuple[str, dict[str, object]]] = []
        self.outcomes: list[str] = []

    def mark(self, point: str, **identity: object) -> bool:
        self.marks.append((point, identity))
        return True

    def finish(self, outcome: str) -> object:
        self.outcomes.append(outcome)
        return object()


class _Writer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.batches: list[object] = []

    def submit(self, batch: object) -> bool:
        if self.fail:
            raise OSError("PRIVATE OUTPUT PATH")
        self.batches.append(batch)
        return True

    def write(self, _batch: object) -> bool:
        raise AssertionError("product path must not call the durable writer")


def _runtime(recorder: _Recorder, writer: _Writer) -> object:
    return SimpleNamespace(
        writer=writer,
        submit=writer.submit,
        create_recorder=lambda **_kwargs: recorder,
    )


def test_agent_probe_binds_response_and_task_identity_then_writes_once() -> None:
    recorder = _Recorder()
    writer = _Writer()
    probe = AgentForegroundLatencyProbeOperation.create(
        _runtime(recorder, writer),
        object(),
        correlation_id="correlation-1",
        interaction_id="interaction-1",
        activation_id="activation-1",
        activation_generation=2,
        turn_id="turn-1",
    )
    assert probe is not None

    assert probe.mark(
        "agent.agent_started",
        response_ref=ResponseRef("interaction-1", "response-1", 3),
    )
    assert probe.mark("agent.task_command_accepted", task_id="task-1")
    probe.finish("completed")
    probe.finish("failed")

    assert recorder.outcomes == ["completed"]
    assert len(writer.batches) == 1
    assert recorder.marks[-1][1] == {
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 2,
        "turn_id": "turn-1",
        "response_id": "response-1",
        "response_generation": 3,
        "task_id": "task-1",
    }


def test_agent_probe_rejects_foreign_response_and_contains_writer_failure() -> None:
    recorder = _Recorder()
    probe = AgentForegroundLatencyProbeOperation.create(
        _runtime(recorder, _Writer(fail=True)),
        object(),
        correlation_id="correlation-1",
        interaction_id="interaction-1",
        activation_id="activation-1",
        activation_generation=2,
        turn_id="turn-1",
    )
    assert probe is not None

    assert not probe.mark(
        "agent.agent_started",
        response_ref=ResponseRef("interaction-foreign", "response-1", 0),
    )
    probe.finish("failed")
    assert recorder.outcomes == ["failed"]


def test_agent_probe_abandon_suppresses_replay_shard() -> None:
    recorder = _Recorder()
    writer = _Writer()
    probe = AgentForegroundLatencyProbeOperation.create(
        _runtime(recorder, writer),
        object(),
        correlation_id="correlation-1",
        interaction_id="interaction-1",
        activation_id="activation-1",
        activation_generation=2,
        turn_id="turn-1",
    )
    assert probe is not None

    probe.abandon()
    assert not probe.mark("agent.agent_started")
    probe.finish("completed")
    assert recorder.outcomes == []
    assert writer.batches == []
