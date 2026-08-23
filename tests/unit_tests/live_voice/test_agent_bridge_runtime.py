# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ErrorCode,
    EventEnvelope,
    ResponseRef,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    WorkProgressEventV2,
)
from jiuwenswarm.server.live_voice.agent_bridge import AgentEvent
from jiuwenswarm.server.live_voice import agent_bridge_runtime
from jiuwenswarm.server.live_voice.agent_bridge_runtime import (
    AgentBridgeCompletionStatus,
    AgentBridgeDelivery,
    AgentBridgeRuntime,
    AgentBridgeRuntimeViolation,
    AgentEventDelivery,
    AgentRoundAdapter,
    AgentRoundRequest,
    WorkProgressDelivery,
    project_round_work_progress,
)
from jiuwenswarm.server.live_voice.latency_measurement import (
    L0Milestone,
    L0RoundBinding,
)


def scope(*, session_id: str = "session-1") -> ScopeRef:
    return ScopeRef("subject-1", "project-1", session_id, Assurance.AUTHENTICATED)


def commit(
    *,
    interaction_id: str = "interaction-1",
    turn_id: str = "turn-1",
    commit_id: str = "commit-1",
    text: str = "hello",
    session_id: str = "session-1",
) -> TurnCommit:
    return TurnCommit.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "commit_id": commit_id,
            "turn_id": turn_id,
            "interaction_id": interaction_id,
            "text": text,
            "hypothesis_provenance": {"provider": "fake.sr"},
            "scope": scope(session_id=session_id).to_dict(),
            "context_refs": [],
            "committed_at": "2026-08-05T08:00:00Z",
        }
    )


def response_ref(
    *, interaction_id: str = "interaction-1", response_id: str = "response-1"
) -> ResponseRef:
    return ResponseRef(interaction_id, response_id, 0)


def round_event(
    request: AgentRoundRequest,
    *,
    seq: int,
    state: str,
    outcome: str | None = None,
    event_id: str | None = None,
    scope_override: ScopeRef | None = None,
) -> EventEnvelope:
    payload: dict[str, object] = {"state": state}
    if state == "terminal":
        payload["outcome"] = outcome
    return EventEnvelope.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "event_id": event_id or f"{request.round_id}-source-{seq}",
            "event_type": f"round.{state}",
            "producer": {
                "component": "agent.runtime",
                "instance_id": f"harness-{request.round_id}",
                "authority": "harness",
            },
            "stream_ref": {"kind": "round", "id": request.round_id},
            "seq": seq,
            "occurred_at": f"2026-08-05T08:00:0{seq}Z",
            "scope": (scope_override or request.commit.scope).to_dict(),
            "correlation_id": request.correlation_id,
            "causation_id": (
                None if seq == 0 else f"{request.round_id}-source-{seq - 1}"
            ),
            "required_capabilities": [],
            "payload": payload,
            "extensions": {},
        }
    )


def agent_event(request: AgentRoundRequest, *, seq: int = 0) -> AgentEvent:
    return AgentEvent(
        request.request_id,
        request.commit.interaction_id,
        request.commit.turn_id,
        request.commit.commit_id,
        seq,
        "agent.output",
        request.source_provenance,
        text="ok",
        capability="agent.chat",
    )


class ScriptedAdapter:
    def __init__(
        self,
        factory: Callable[
            [AgentRoundRequest], tuple[AgentEvent | EventEnvelope | Exception, ...]
        ],
        *,
        release: asyncio.Event | None = None,
    ) -> None:
        self.factory = factory
        self.release = release
        self.started = asyncio.Event()
        self.calls = 0
        self.cancel_calls = 0

    async def stream(self, request: AgentRoundRequest):
        self.calls += 1
        self.started.set()
        if self.release is not None:
            await self.release.wait()
        for item in self.factory(request):
            await asyncio.sleep(0)
            if isinstance(item, Exception):
                raise item
            yield item


class TerminalThenStallAdapter:
    def __init__(self) -> None:
        self.calls = 0
        self.cancel_calls = 0
        self.pulled_after_terminal = asyncio.Event()
        self.closed = asyncio.Event()

    async def stream(self, request: AgentRoundRequest):
        self.calls += 1
        try:
            yield round_event(request, seq=0, state="accepted")
            yield round_event(request, seq=1, state="terminal", outcome="completed")
            self.pulled_after_terminal.set()
            await asyncio.Event().wait()
        finally:
            self.closed.set()


class ControlledCloseIterator:
    def __init__(
        self,
        request: AgentRoundRequest,
        *,
        close_release: asyncio.Event | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.request = request
        self.close_release = close_release
        self.close_error = close_error
        self.index = 0
        self.close_started = asyncio.Event()
        self.close_cancelled = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index == 0:
            self.index += 1
            return round_event(self.request, seq=0, state="accepted")
        if self.index == 1:
            self.index += 1
            return round_event(
                self.request, seq=1, state="terminal", outcome="completed"
            )
        await asyncio.Event().wait()
        raise StopAsyncIteration

    async def aclose(self) -> None:
        self.close_started.set()
        if self.close_error is not None:
            raise self.close_error
        if self.close_release is None:
            return
        try:
            await self.close_release.wait()
        except asyncio.CancelledError:
            self.close_cancelled.set()
            await self.close_release.wait()


class ControlledCloseAdapter:
    def __init__(
        self,
        *,
        close_release: asyncio.Event | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.close_release = close_release
        self.close_error = close_error
        self.iterator: ControlledCloseIterator | None = None

    def stream(self, request: AgentRoundRequest):
        self.iterator = ControlledCloseIterator(
            request,
            close_release=self.close_release,
            close_error=self.close_error,
        )
        return self.iterator


@pytest.mark.parametrize(
    "timeout",
    [True, 0, -1, float("inf"), float("nan"), "1"],
)
def test_adapter_close_timeout_must_be_a_positive_finite_number(
    timeout: object,
) -> None:
    with pytest.raises(AgentBridgeRuntimeViolation) as invalid:
        AgentBridgeRuntime(
            instance_id="bridge-invalid-timeout",
            adapter_close_timeout_seconds=timeout,  # type: ignore[arg-type]
        )
    assert invalid.value.reason == "INVALID_RUNTIME_CAPACITY"


def test_bridge_instance_rejects_unpaired_surrogate_at_construction() -> None:
    with pytest.raises(AgentBridgeRuntimeViolation) as invalid:
        AgentBridgeRuntime(instance_id="bridge-\ud800")
    assert invalid.value.reason == "INVALID_BRIDGE_INSTANCE"


@pytest.mark.asyncio
async def test_request_id_surrogate_rejects_before_adapter_or_ledger_effect() -> None:
    adapter = ScriptedAdapter(lambda _request: ())
    runtime = AgentBridgeRuntime(instance_id="bridge-valid")
    await runtime.start()
    with pytest.raises(AgentBridgeRuntimeViolation) as invalid:
        submit(runtime, adapter, request_id="request-\ud800")
    assert invalid.value.reason == "INVALID_AGENT_ROUND_REQUEST"
    assert invalid.value.code is ErrorCode.INVALID_ARGUMENT
    assert adapter.calls == 0
    assert runtime.snapshot().retained_requests == 0
    assert runtime.snapshot().queued_outputs == 0
    await runtime.close()


def submit(
    runtime: AgentBridgeRuntime,
    adapter: AgentRoundAdapter,
    *,
    request_id: str = "request-1",
    round_id: str = "round-1",
    current_commit: TurnCommit | None = None,
    current_response: ResponseRef | None = None,
):
    bound_commit = current_commit or commit()
    return runtime.submit(
        request_id=request_id,
        round_id=round_id,
        response_ref=current_response
        or response_ref(
            interaction_id=bound_commit.interaction_id,
            response_id=f"response-{round_id}",
        ),
        correlation_id=f"correlation-{round_id}",
        commit=bound_commit,
        adapter_id="jiuwenswarm.harness",
        adapter=adapter,
    )


@pytest.mark.asyncio
async def test_slow_adapter_never_blocks_submit_and_preserves_two_sequence_domains() -> (
    None
):
    release = asyncio.Event()

    def script(request: AgentRoundRequest):
        return (
            agent_event(request),
            round_event(request, seq=0, state="accepted"),
            round_event(request, seq=1, state="running"),
            round_event(request, seq=2, state="blocked"),
            round_event(request, seq=3, state="decision_required"),
            round_event(request, seq=4, state="terminal", outcome="completed"),
        )

    adapter = ScriptedAdapter(script, release=release)
    runtime = AgentBridgeRuntime(instance_id="bridge-1", output_capacity=8)
    assert await runtime.start() is True
    submission = submit(runtime, adapter)
    assert adapter.calls == 0
    assert submission.completion.done() is False
    await asyncio.wait_for(adapter.started.wait(), timeout=1)
    assert submission.completion.done() is False

    release.set()
    deliveries = [
        await asyncio.wait_for(runtime.next_delivery(), timeout=1) for _ in range(6)
    ]
    completion = await asyncio.wait_for(submission.completion, timeout=1)
    assert isinstance(deliveries[0], AgentEventDelivery)
    progress = [item for item in deliveries if isinstance(item, WorkProgressDelivery)]
    assert [item.source_event.seq for item in progress] == [0, 1, 2, 3, 4]
    assert [item.progress_event.seq for item in progress] == [0, 1, 2, 3, 4]
    assert [
        WorkProgressEventV2.from_dict(item.progress_event.payload).seq
        for item in progress
    ] == [0, 1, 2, 3, 4]
    assert [
        WorkProgressEventV2.from_dict(item.progress_event.payload).state.value
        for item in progress
    ] == ["accepted", "running", "blocked", "decision_required", "terminal"]
    assert all(
        WorkProgressEventV2.from_dict(
            item.progress_event.payload
        ).summary.knowledge.value
        == "unknown"
        for item in progress
    )
    assert completion.status is AgentBridgeCompletionStatus.TERMINAL_OBSERVED
    assert completion.terminal_outcome is TerminalOutcome.COMPLETED
    assert adapter.cancel_calls == 0
    await runtime.close()


@pytest.mark.asyncio
async def test_production_agent_bridge_emits_only_exact_bound_l0_milestones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound = L0RoundBinding(
        correlation_id="correlation-round-1",
        session_id="session-1",
        interaction_id="interaction-1",
        activation_generation=2,
        response_id="response-round-1",
        response_generation=0,
        turn_id="turn-1",
        round_id="round-1",
    )
    resolved: list[dict[str, object]] = []
    emitted: list[dict[str, object]] = []

    def resolve(**kwargs: object) -> L0RoundBinding:
        resolved.append(kwargs)
        return bound

    def emit(**kwargs: object) -> bool:
        emitted.append(kwargs)
        return True

    monkeypatch.setattr(agent_bridge_runtime, "resolve_runtime_l0_binding", resolve)
    monkeypatch.setattr(agent_bridge_runtime, "emit_runtime_l0_milestone", emit)

    def script(request: AgentRoundRequest):
        common = (
            request.request_id,
            request.commit.interaction_id,
            request.commit.turn_id,
            request.commit.commit_id,
        )
        return (
            AgentEvent(
                *common,
                0,
                "chat.delta",
                request.source_provenance,
                text="private delta",
            ),
            AgentEvent(
                *common,
                1,
                "chat.final",
                request.source_provenance,
                text="private final",
            ),
        )

    adapter = ScriptedAdapter(script)
    runtime = AgentBridgeRuntime(instance_id="bridge-l0-production", output_capacity=4)
    await runtime.start()
    submission = submit(runtime, adapter)
    deliveries = [
        await asyncio.wait_for(runtime.next_delivery(), timeout=1) for _ in range(2)
    ]
    completion = await asyncio.wait_for(submission.completion, timeout=1)
    assert all(isinstance(item, AgentEventDelivery) for item in deliveries)
    assert completion.status is AgentBridgeCompletionStatus.STREAM_ENDED_WITHOUT_TERMINAL
    assert resolved == [
        {
            "correlation_id": "correlation-round-1",
            "interaction_id": "interaction-1",
            "response_id": "response-round-1",
            "response_generation": 0,
        }
    ]
    assert [item["milestone"] for item in emitted] == [
        L0Milestone.AGENT_REQUEST_START,
        L0Milestone.FIRST_DELTA,
        L0Milestone.FIRST_STABLE_SPEAKABLE_SENTENCE,
        L0Milestone.CHAT_FINAL,
    ]
    assert all(item["binding"] == bound for item in emitted)
    assert "classification" not in emitted[-1]
    assert "private delta" not in repr(emitted)
    assert "private final" not in repr(emitted)
    await runtime.close()


@pytest.mark.asyncio
async def test_dispatch_backpressure_replay_conflict_and_ledger_are_bounded() -> None:
    release = asyncio.Event()
    first = ScriptedAdapter(lambda _request: (), release=release)
    second = ScriptedAdapter(lambda _request: ())
    rejected = ScriptedAdapter(lambda _request: ())
    runtime = AgentBridgeRuntime(
        instance_id="bridge-1",
        dispatch_capacity=1,
        max_concurrency=1,
        max_requests=3,
    )
    await runtime.start()
    one = submit(runtime, first, request_id="request-1", round_id="round-1")
    await asyncio.wait_for(first.started.wait(), timeout=1)
    two = submit(runtime, second, request_id="request-2", round_id="round-2")
    assert submit(runtime, second, request_id="request-2", round_id="round-2") is two

    with pytest.raises(AgentBridgeRuntimeViolation) as full:
        submit(runtime, rejected, request_id="request-3", round_id="round-3")
    assert full.value.reason == "DISPATCH_QUEUE_FULL"
    assert rejected.calls == 0

    changed = commit(text="changed")
    with pytest.raises(AgentBridgeRuntimeViolation) as conflict:
        submit(
            runtime,
            second,
            request_id="request-2",
            round_id="round-2",
            current_commit=changed,
            current_response=response_ref(response_id="response-round-2"),
        )
    assert conflict.value.reason == "REQUEST_ID_CONFLICT"
    assert second.calls == 0

    release.set()
    assert (
        await asyncio.wait_for(one.completion, timeout=1)
    ).status is AgentBridgeCompletionStatus.STREAM_ENDED_WITHOUT_TERMINAL
    assert (
        await asyncio.wait_for(two.completion, timeout=1)
    ).status is AgentBridgeCompletionStatus.STREAM_ENDED_WITHOUT_TERMINAL
    assert second.calls == 1
    await runtime.close()


@pytest.mark.asyncio
async def test_completion_timeout_does_not_cancel_the_shared_request_result() -> None:
    release = asyncio.Event()
    adapter = ScriptedAdapter(lambda _request: (), release=release)
    runtime = AgentBridgeRuntime(instance_id="bridge-completion-timeout")
    await runtime.start()
    submission = submit(runtime, adapter)
    await asyncio.wait_for(adapter.started.wait(), timeout=1)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(submission.completion, timeout=0.01)
    assert submission.completion.done() is False
    assert submit(runtime, adapter) is submission

    release.set()
    completion = await asyncio.wait_for(submission.completion, timeout=1)
    assert (
        completion.status is AgentBridgeCompletionStatus.STREAM_ENDED_WITHOUT_TERMINAL
    )
    await runtime.close()


@pytest.mark.asyncio
async def test_request_ledger_rejects_new_work_without_unsafe_eviction() -> None:
    first = ScriptedAdapter(lambda _request: ())
    rejected = ScriptedAdapter(lambda _request: ())
    runtime = AgentBridgeRuntime(instance_id="bridge-1", max_requests=1)
    await runtime.start()
    one = submit(runtime, first)
    await asyncio.wait_for(one.completion, timeout=1)
    with pytest.raises(AgentBridgeRuntimeViolation) as full:
        submit(runtime, rejected, request_id="request-2", round_id="round-2")
    assert full.value.reason == "REQUEST_LEDGER_FULL"
    assert rejected.calls == 0
    assert submit(runtime, first) is one
    await runtime.close()


@pytest.mark.asyncio
async def test_scoped_round_identity_cannot_be_rebound_to_another_request() -> None:
    release = asyncio.Event()
    first = ScriptedAdapter(lambda _request: (), release=release)
    rejected = ScriptedAdapter(lambda _request: ())
    runtime = AgentBridgeRuntime(instance_id="bridge-1")
    await runtime.start()
    one = submit(runtime, first, request_id="request-1", round_id="round-1")
    await asyncio.wait_for(first.started.wait(), timeout=1)
    with pytest.raises(AgentBridgeRuntimeViolation) as conflict:
        submit(runtime, rejected, request_id="request-2", round_id="round-1")
    assert conflict.value.reason == "ROUND_ID_CONFLICT"
    assert rejected.calls == 0
    release.set()
    await asyncio.wait_for(one.completion, timeout=1)
    await runtime.close()


@pytest.mark.asyncio
async def test_output_backpressure_blocks_only_worker_and_never_drops_terminal() -> (
    None
):
    adapter = ScriptedAdapter(
        lambda request: (
            round_event(request, seq=0, state="accepted"),
            round_event(request, seq=1, state="running"),
            round_event(request, seq=2, state="terminal", outcome="failed"),
        )
    )
    runtime = AgentBridgeRuntime(instance_id="bridge-1", output_capacity=1)
    await runtime.start()
    submission = submit(runtime, adapter)
    await asyncio.wait_for(adapter.started.wait(), timeout=1)
    await asyncio.sleep(0)
    assert runtime.snapshot().queued_outputs == 1
    assert submission.completion.done() is False
    close_task = asyncio.create_task(runtime.close())
    await asyncio.sleep(0)
    assert close_task.done() is False

    deliveries = [
        await asyncio.wait_for(runtime.next_delivery(), timeout=1) for _ in range(3)
    ]
    completion = await asyncio.wait_for(submission.completion, timeout=1)
    assert [
        WorkProgressEventV2.from_dict(item.progress_event.payload).state.value
        for item in deliveries
        if isinstance(item, WorkProgressDelivery)
    ] == ["accepted", "running", "terminal"]
    assert completion.terminal_outcome is TerminalOutcome.FAILED
    await asyncio.wait_for(close_task, timeout=1)
    assert runtime.snapshot().closed is True


@pytest.mark.asyncio
async def test_authoritative_terminal_completes_without_waiting_for_stream_end() -> (
    None
):
    adapter = TerminalThenStallAdapter()
    runtime = AgentBridgeRuntime(instance_id="bridge-terminal", output_capacity=2)
    await runtime.start()
    submission = submit(runtime, adapter)
    deliveries = [
        await asyncio.wait_for(runtime.next_delivery(), timeout=1) for _ in range(2)
    ]
    completion = await asyncio.wait_for(submission.completion, timeout=1)
    assert all(isinstance(item, WorkProgressDelivery) for item in deliveries)
    assert completion.status is AgentBridgeCompletionStatus.TERMINAL_OBSERVED
    assert completion.terminal_outcome is TerminalOutcome.COMPLETED
    await asyncio.sleep(0)
    assert adapter.pulled_after_terminal.is_set() is False
    await asyncio.wait_for(adapter.closed.wait(), timeout=1)
    assert adapter.cancel_calls == 0
    await asyncio.wait_for(runtime.close(), timeout=1)


@pytest.mark.asyncio
async def test_terminal_completion_and_runtime_close_do_not_wait_for_stalled_aclose() -> (
    None
):
    release = asyncio.Event()
    adapter = ControlledCloseAdapter(close_release=release)
    runtime = AgentBridgeRuntime(
        instance_id="bridge-stalled-close",
        output_capacity=2,
        adapter_close_timeout_seconds=0.01,
    )
    await runtime.start()
    submission = submit(runtime, adapter)
    deliveries = [
        await asyncio.wait_for(runtime.next_delivery(), timeout=1) for _ in range(2)
    ]
    assert all(isinstance(item, WorkProgressDelivery) for item in deliveries)
    completion = await asyncio.wait_for(submission.completion, timeout=0.1)
    assert completion.status is AgentBridgeCompletionStatus.TERMINAL_OBSERVED
    assert adapter.iterator is not None
    await asyncio.wait_for(adapter.iterator.close_started.wait(), timeout=0.1)
    await asyncio.wait_for(runtime.close(), timeout=0.1)
    assert runtime.snapshot().closed is True
    assert adapter.iterator.close_cancelled.is_set()
    release.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_terminal_completion_is_not_rewritten_when_aclose_raises() -> None:
    adapter = ControlledCloseAdapter(close_error=RuntimeError("cleanup failed"))
    runtime = AgentBridgeRuntime(instance_id="bridge-raising-close", output_capacity=2)
    await runtime.start()
    submission = submit(runtime, adapter)
    for _ in range(2):
        assert isinstance(
            await asyncio.wait_for(runtime.next_delivery(), timeout=1),
            WorkProgressDelivery,
        )
    completion = await asyncio.wait_for(submission.completion, timeout=0.1)
    assert completion.status is AgentBridgeCompletionStatus.TERMINAL_OBSERVED
    assert completion.terminal_outcome is TerminalOutcome.COMPLETED
    await asyncio.wait_for(runtime.close(), timeout=0.1)
    assert runtime.snapshot().closed is True


def test_progress_event_identity_cannot_collide_on_opaque_delimiters() -> None:
    first_commit = commit()
    first_request = AgentRoundRequest(
        request_id="c",
        round_id="round-1",
        response_ref=response_ref(response_id="response-round-1"),
        correlation_id="correlation-round-1",
        commit=first_commit,
        adapter_id="jiuwenswarm.harness",
    )
    second_commit = commit(
        interaction_id="interaction-2",
        turn_id="turn-2",
        commit_id="commit-2",
        session_id="session-2",
    )
    second_request = AgentRoundRequest(
        request_id="b:c",
        round_id="round-2",
        response_ref=response_ref(
            interaction_id="interaction-2", response_id="response-round-2"
        ),
        correlation_id="correlation-round-2",
        commit=second_commit,
        adapter_id="jiuwenswarm.harness",
    )
    first = project_round_work_progress(
        round_event(first_request, seq=0, state="accepted"),
        first_request,
        bridge_instance_id="a:b",
        envelope_seq=0,
        projection_seq=0,
    )
    second = project_round_work_progress(
        round_event(second_request, seq=0, state="accepted"),
        second_request,
        bridge_instance_id="a",
        envelope_seq=0,
        projection_seq=0,
    )
    assert first.event_id != second.event_id
    assert first.event_id.startswith("agent.bridge:613a62:63:")
    assert second.event_id.startswith("agent.bridge:61:623a63:")
    with pytest.raises(AgentBridgeRuntimeViolation) as invalid_instance:
        project_round_work_progress(
            round_event(first_request, seq=0, state="accepted"),
            first_request,
            bridge_instance_id="bridge-\ud800",
            envelope_seq=0,
            projection_seq=0,
        )
    assert invalid_instance.value.reason == "INVALID_BRIDGE_INSTANCE"


@pytest.mark.asyncio
async def test_source_gap_reorders_deduplicates_and_projects_once() -> None:
    def script(request: AgentRoundRequest):
        accepted = round_event(request, seq=0, state="accepted")
        running = round_event(request, seq=1, state="running")
        terminal = round_event(request, seq=2, state="terminal", outcome="completed")
        return running, accepted, accepted, terminal

    adapter = ScriptedAdapter(script)
    runtime = AgentBridgeRuntime(instance_id="bridge-1")
    await runtime.start()
    submission = submit(runtime, adapter)
    progress = [
        await asyncio.wait_for(runtime.next_delivery(), timeout=1) for _ in range(3)
    ]
    completion = await asyncio.wait_for(submission.completion, timeout=1)
    assert [item.source_event.seq for item in progress] == [0, 1, 2]
    assert completion.source_event_count == 4
    assert completion.progress_event_count == 3
    await runtime.close()


@pytest.mark.asyncio
async def test_wrong_source_and_adapter_failure_do_not_fabricate_terminal() -> None:
    wrong = ScriptedAdapter(
        lambda request: (
            round_event(
                request,
                seq=0,
                state="accepted",
                scope_override=scope(session_id="other-session"),
            ),
        )
    )
    runtime = AgentBridgeRuntime(instance_id="bridge-1")
    await runtime.start()
    invalid = submit(runtime, wrong)
    with pytest.raises(AgentBridgeRuntimeViolation) as mismatch:
        await asyncio.wait_for(invalid.completion, timeout=1)
    assert mismatch.value.reason == "INVALID_ROUND_SOURCE"
    assert runtime.snapshot().queued_outputs == 0
    await runtime.close()

    broken = ScriptedAdapter(lambda _request: (RuntimeError("adapter down"),))
    second_runtime = AgentBridgeRuntime(instance_id="bridge-2")
    await second_runtime.start()
    failed = submit(second_runtime, broken)
    with pytest.raises(RuntimeError, match="adapter down"):
        await asyncio.wait_for(failed.completion, timeout=1)
    assert second_runtime.snapshot().queued_outputs == 0
    await second_runtime.close()


@pytest.mark.asyncio
async def test_invalid_agent_sequence_and_conflicting_source_fail_closed() -> None:
    wrong_agent = ScriptedAdapter(lambda request: (agent_event(request, seq=1),))
    runtime = AgentBridgeRuntime(instance_id="bridge-1")
    await runtime.start()
    submission = submit(runtime, wrong_agent)
    with pytest.raises(AgentBridgeRuntimeViolation) as invalid_agent:
        await asyncio.wait_for(submission.completion, timeout=1)
    assert invalid_agent.value.reason == "INVALID_AGENT_EVENT_PROVENANCE"
    assert runtime.snapshot().queued_outputs == 0
    await runtime.close()

    def conflicting_script(request: AgentRoundRequest):
        accepted = round_event(request, seq=0, state="accepted")
        conflict = EventEnvelope.from_dict(
            {
                **accepted.to_dict(),
                "payload": {"state": "accepted"},
                "occurred_at": "2026-08-05T08:00:09Z",
            }
        )
        return accepted, conflict

    conflicting = ScriptedAdapter(conflicting_script)
    second_runtime = AgentBridgeRuntime(instance_id="bridge-2")
    await second_runtime.start()
    failed = submit(second_runtime, conflicting)
    first_delivery = await asyncio.wait_for(second_runtime.next_delivery(), timeout=1)
    assert isinstance(first_delivery, WorkProgressDelivery)
    with pytest.raises(AgentBridgeRuntimeViolation) as source_conflict:
        await asyncio.wait_for(failed.completion, timeout=1)
    assert source_conflict.value.reason == "EVENT_ID_CONFLICT"
    assert second_runtime.snapshot().queued_outputs == 0
    await second_runtime.close()


@pytest.mark.asyncio
async def test_source_event_limit_fails_request_without_fabricating_terminal() -> None:
    def repeated_source(request: AgentRoundRequest):
        accepted = round_event(request, seq=0, state="accepted")
        return accepted, accepted

    adapter = ScriptedAdapter(repeated_source)
    runtime = AgentBridgeRuntime(
        instance_id="bridge-source-limit",
        max_source_events_per_request=1,
    )
    await runtime.start()
    submission = submit(runtime, adapter)
    assert isinstance(
        await asyncio.wait_for(runtime.next_delivery(), timeout=1),
        WorkProgressDelivery,
    )
    with pytest.raises(AgentBridgeRuntimeViolation) as limited:
        await asyncio.wait_for(submission.completion, timeout=1)
    assert limited.value.reason == "SOURCE_EVENT_LIMIT_EXCEEDED"
    assert runtime.snapshot().queued_outputs == 0
    await runtime.close()


@pytest.mark.asyncio
async def test_feature_off_and_not_started_have_zero_adapter_effects() -> None:
    adapter = ScriptedAdapter(lambda _request: ())
    disabled = AgentBridgeRuntime(instance_id="bridge-off", enabled=False)
    assert await disabled.start() is False
    with pytest.raises(AgentBridgeRuntimeViolation) as off:
        submit(disabled, adapter)
    assert off.value.reason == "FEATURE_DISABLED"
    assert disabled.snapshot().started is False
    assert disabled.snapshot().retained_requests == 0
    assert adapter.calls == 0
    with pytest.raises(AgentBridgeRuntimeViolation) as disabled_delivery:
        await disabled.next_delivery()
    assert disabled_delivery.value.reason == "FEATURE_DISABLED"
    await disabled.close()

    idle = AgentBridgeRuntime(instance_id="bridge-idle")
    with pytest.raises(AgentBridgeRuntimeViolation) as not_started:
        submit(idle, adapter)
    assert not_started.value.reason == "BRIDGE_RUNTIME_NOT_STARTED"
    assert adapter.calls == 0
    with pytest.raises(AgentBridgeRuntimeViolation) as no_delivery_owner:
        await idle.next_delivery()
    assert no_delivery_owner.value.reason == "BRIDGE_RUNTIME_NOT_STARTED"

    owned = AgentBridgeRuntime(instance_id="bridge-owned")
    await owned.start()

    def wrong_loop_delivery_reason() -> str:
        async def consume() -> str:
            try:
                await owned.next_delivery()
            except AgentBridgeRuntimeViolation as error:
                return error.reason
            raise AssertionError("cross-loop delivery unexpectedly succeeded")

        return asyncio.run(consume())

    assert (
        await asyncio.to_thread(wrong_loop_delivery_reason)
        == "BRIDGE_EVENT_LOOP_MISMATCH"
    )
    assert owned.snapshot().queued_outputs == 0
    await owned.close()

    closed = AgentBridgeRuntime(instance_id="bridge-closed")
    await closed.start()
    await closed.close()
    with pytest.raises(AgentBridgeRuntimeViolation) as after_close:
        submit(closed, adapter)
    assert after_close.value.reason == "BRIDGE_RUNTIME_CLOSED"
    assert adapter.calls == 0
    with pytest.raises(AgentBridgeRuntimeViolation) as closed_delivery:
        await closed.next_delivery()
    assert closed_delivery.value.reason == "BRIDGE_RUNTIME_CLOSED"


@pytest.mark.asyncio
async def test_pending_delivery_waiters_wake_when_idle_runtime_closes() -> None:
    runtime = AgentBridgeRuntime(instance_id="bridge-delivery-close-race")
    await runtime.start()
    waiters = [asyncio.create_task(runtime.next_delivery()) for _ in range(2)]
    await asyncio.sleep(0)
    assert all(not waiter.done() for waiter in waiters)
    await asyncio.wait_for(runtime.close(), timeout=0.1)
    for waiter in waiters:
        with pytest.raises(AgentBridgeRuntimeViolation) as closed:
            await asyncio.wait_for(waiter, timeout=0.1)
        assert closed.value.reason == "BRIDGE_RUNTIME_CLOSED"


@pytest.mark.asyncio
async def test_cancelled_delivery_waiter_cannot_consume_the_arriving_output() -> None:
    waiter: asyncio.Task[AgentBridgeDelivery]

    class CancelAfterFirstYieldAdapter:
        def stream(
            self, request: AgentRoundRequest
        ) -> AsyncIterator[AgentEvent | EventEnvelope]:
            async def generate() -> AsyncIterator[AgentEvent | EventEnvelope]:
                yield round_event(request, seq=0, state="accepted")
                waiter.cancel()

            return generate()

    runtime = AgentBridgeRuntime(instance_id="bridge-delivery-cancel")
    await runtime.start()
    waiter = asyncio.create_task(runtime.next_delivery())
    submission = submit(runtime, CancelAfterFirstYieldAdapter())

    with pytest.raises(asyncio.CancelledError):
        await waiter
    delivery = await asyncio.wait_for(runtime.next_delivery(), timeout=1)
    assert isinstance(delivery, WorkProgressDelivery)
    assert (
        WorkProgressEventV2.from_dict(delivery.progress_event.payload).state.value
        == "accepted"
    )
    completion = await asyncio.wait_for(submission.completion, timeout=1)
    assert (
        completion.status is AgentBridgeCompletionStatus.STREAM_ENDED_WITHOUT_TERMINAL
    )
    await runtime.close()


@pytest.mark.asyncio
async def test_concurrent_rounds_keep_scope_and_identity_isolated_while_close_drains() -> (
    None
):
    release = asyncio.Event()

    def terminal_script(request: AgentRoundRequest):
        return (
            round_event(request, seq=0, state="accepted"),
            round_event(request, seq=1, state="terminal", outcome="completed"),
        )

    first = ScriptedAdapter(terminal_script, release=release)
    second = ScriptedAdapter(terminal_script, release=release)
    runtime = AgentBridgeRuntime(instance_id="bridge-1", max_concurrency=2)
    await runtime.start()
    one_commit = commit()
    two_commit = commit(
        interaction_id="interaction-2",
        turn_id="turn-2",
        commit_id="commit-2",
        session_id="session-2",
    )
    one = submit(
        runtime,
        first,
        request_id="request-1",
        round_id="round-1",
        current_commit=one_commit,
    )
    two = submit(
        runtime,
        second,
        request_id="request-2",
        round_id="round-2",
        current_commit=two_commit,
    )
    await asyncio.wait_for(first.started.wait(), timeout=1)
    await asyncio.wait_for(second.started.wait(), timeout=1)
    close_task = asyncio.create_task(runtime.close())
    await asyncio.sleep(0)
    assert close_task.done() is False
    release.set()

    deliveries = [
        await asyncio.wait_for(runtime.next_delivery(), timeout=1) for _ in range(4)
    ]
    await asyncio.wait_for(close_task, timeout=1)
    assert (await one.completion).terminal_outcome is TerminalOutcome.COMPLETED
    assert (await two.completion).terminal_outcome is TerminalOutcome.COMPLETED
    assert {
        (item.request.request_id, item.source_event.scope.session_id)
        for item in deliveries
        if isinstance(item, WorkProgressDelivery)
    } == {
        ("request-1", "session-1"),
        ("request-2", "session-2"),
    }
    assert first.cancel_calls == second.cancel_calls == 0
    assert runtime.snapshot().closed is True
