# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from threading import Barrier

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ContractViolation,
    ErrorCode,
    EventEnvelope,
    IdentityKind,
    IdentityRef,
    ProducerRef,
    ScopeRef,
    WorkSourceAuthority,
)
from jiuwenswarm.server.live_voice import (
    progress_notification_arbiter as arbiter_module,
)
from jiuwenswarm.server.live_voice.progress_notification_arbiter import (
    ForegroundFact,
    ForegroundSnapshot,
    NoProjectionAdvanceDisposition,
    NotificationDisposition,
    ProgressNotificationArbiter,
    ProgressNotificationArbiterViolation,
    ProgressNotificationBinding,
    SpeechDisposition,
    SpeechPolicy,
)
from jiuwenswarm.server.live_voice.formal_task_models import PersistentTaskEvent


def scope(
    *,
    subject_id: str = "subject-1",
    project_id: str = "project-1",
    session_id: str = "session-1",
    assurance: Assurance = Assurance.AUTHENTICATED,
) -> ScopeRef:
    return ScopeRef(subject_id, project_id, session_id, assurance)


def safe_foreground(
    *, speech_policy: SpeechPolicy = SpeechPolicy.ALLOW_CANDIDATE
) -> ForegroundSnapshot:
    return ForegroundSnapshot(
        interaction=ForegroundFact.SAFE,
        response=ForegroundFact.SAFE,
        presentation=ForegroundFact.SAFE,
        speech_policy=speech_policy,
    )


def busy_foreground() -> ForegroundSnapshot:
    return ForegroundSnapshot(
        interaction=ForegroundFact.SAFE,
        response=ForegroundFact.BUSY,
        presentation=ForegroundFact.SAFE,
        speech_policy=SpeechPolicy.ALLOW_CANDIDATE,
    )


def unknown_foreground() -> ForegroundSnapshot:
    return ForegroundSnapshot(
        interaction=ForegroundFact.SAFE,
        response=ForegroundFact.UNKNOWN,
        presentation=ForegroundFact.SAFE,
        speech_policy=SpeechPolicy.ALLOW_CANDIDATE,
    )


def source_event(
    *,
    work_kind: str = "round",
    work_id: str = "round-1",
    seq: int = 0,
    state: str = "accepted",
    outcome: str | None = None,
    correlation_id: str = "correlation-1",
    current_scope: ScopeRef | None = None,
    event_id: str | None = None,
    producer_component: str | None = None,
    producer_instance: str | None = None,
    causation_id: str | None = None,
) -> EventEnvelope:
    authority = {
        "round": "harness",
        "task": "task_core",
        "attempt": "executor",
    }[work_kind]
    payload: dict[str, object] = {"state": state}
    if state == "terminal":
        payload["outcome"] = outcome
    prior = None if seq == 0 else f"source:{work_kind}:{work_id}:{seq - 1}"
    return EventEnvelope.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "event_id": event_id or f"source:{work_kind}:{work_id}:{seq}",
            "event_type": f"{work_kind}.{state}",
            "producer": {
                "component": producer_component
                or ("task_core" if work_kind == "task" else f"test.{authority}"),
                "instance_id": producer_instance or f"{authority}-1",
                "authority": authority,
            },
            "stream_ref": {"kind": work_kind, "id": work_id},
            "seq": seq,
            "occurred_at": f"2026-08-06T08:00:00.{seq}Z",
            "scope": (current_scope or scope()).to_dict(),
            "correlation_id": correlation_id,
            "causation_id": prior if causation_id is None else causation_id,
            "required_capabilities": [],
            "payload": payload,
            "extensions": {},
        }
    )


def progress_event(
    source: EventEnvelope,
    *,
    work_kind: str | None = None,
    work_id: str | None = None,
    envelope_seq: int | None = None,
    projection_seq: int | None = None,
    event_id: str | None = None,
    state: str | None = None,
    outcome: str | None = None,
    correlation_id: str | None = None,
    current_scope: ScopeRef | None = None,
    source_authority: str | None = None,
    source_kind: str | None = None,
    source_id: str | None = None,
    source_event_id: str | None = None,
    adapter: str | None = "test.adapter",
    urgency: str = "normal",
    speakability: str = "not_speakable",
    summary: object | None = None,
    blocking_question: object | None = None,
    artifact_refs: object | None = None,
    producer_component: str = "test.progress",
    producer_instance: str = "progress-1",
) -> EventEnvelope:
    selected_work_kind = work_kind or source.stream_ref.kind.value
    selected_work_id = work_id or source.stream_ref.id
    selected_state = state or str(source.payload["state"])
    selected_outcome = source.payload.get("outcome") if outcome is None else outcome
    selected_projection_seq = source.seq if projection_seq is None else projection_seq
    selected_envelope_seq = (
        selected_projection_seq if envelope_seq is None else envelope_seq
    )
    payload = {
        "work_ref": {"kind": selected_work_kind, "id": selected_work_id},
        "source": {
            "authority": source_authority or source.producer.authority,
            "event_id": source_event_id or source.event_id,
            "source_work_ref": {
                "kind": source_kind or source.stream_ref.kind.value,
                "id": source_id or source.stream_ref.id,
            },
            "adapter": adapter,
        },
        "seq": selected_projection_seq,
        "state": selected_state,
        "outcome": selected_outcome,
        "summary": summary or {"knowledge": "unknown"},
        "blocking_question": blocking_question or {"knowledge": "unknown"},
        "artifact_refs": artifact_refs or {"knowledge": "unknown"},
        "urgency": urgency,
        "speakability": speakability,
    }
    return EventEnvelope.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "event_id": event_id
            or f"progress:{selected_work_kind}:{selected_work_id}:{selected_projection_seq}",
            "event_type": "work.progress",
            "producer": {
                "component": producer_component,
                "instance_id": producer_instance,
                "authority": "adapter",
            },
            "stream_ref": {
                "kind": selected_work_kind,
                "id": selected_work_id,
            },
            "seq": selected_envelope_seq,
            "occurred_at": source.occurred_at,
            "scope": (current_scope or source.scope).to_dict(),
            "correlation_id": correlation_id or source.correlation_id,
            "causation_id": source_event_id or source.event_id,
            "required_capabilities": [],
            "payload": payload,
            "extensions": {},
        }
    )


def binding(
    source: EventEnvelope,
    progress: EventEnvelope,
    *,
    progress_adapter: str | None = "test.adapter",
) -> ProgressNotificationBinding:
    return ProgressNotificationBinding(
        scope=source.scope,
        work_ref=progress.stream_ref,
        correlation_id=source.correlation_id,
        source_producer=source.producer,
        source_work_ref=source.stream_ref,
        source_authority=WorkSourceAuthority(source.producer.authority),
        progress_producer=progress.producer,
        progress_adapter=progress_adapter,
    )


def offer(
    arbiter: ProgressNotificationArbiter,
    source: EventEnvelope,
    progress: EventEnvelope,
    *,
    foreground: ForegroundSnapshot | None = None,
    expected: ProgressNotificationBinding | None = None,
):
    return arbiter.offer(
        source,
        progress,
        foreground or safe_foreground(),
        expected or binding(source, progress),
    )


def no_projection_advance(
    source: EventEnvelope,
    progress: EventEnvelope,
    *,
    seq: int,
    event_id: str | None = None,
    event_type: str = "attempt.running",
) -> tuple[object, ProgressNotificationBinding]:
    expected = binding(source, progress)
    selected_event_id = event_id or f"task-event:no-projection:{seq}"
    state = {
        "attempt.accepted": "accepted",
        "attempt.running": "running",
        "attempt.terminal": "terminal",
        "task.cancel_requested": "accepted",
    }.get(event_type, "running")
    producer = (
        "task_core.control" if event_type == "task.cancel_requested" else "executor-1"
    )
    source_event_id = (
        None
        if event_type == "task.cancel_requested"
        else f"executor-source:{selected_event_id}"
    )
    persistent = PersistentTaskEvent(
        event_id=selected_event_id,
        task_id=source.stream_ref.id,
        attempt_id="attempt-1",
        scope=source.scope,
        seq=seq,
        event_type=event_type,
        state=state,
        outcome="completed" if state == "terminal" else None,
        producer=producer,
        source_event_id=source_event_id,
        causation_id=source_event_id or f"control:{selected_event_id}",
        correlation_id=source.correlation_id,
        occurred_at="2026-08-06T08:00:00Z",
        details={},
    )
    return (
        arbiter_module._mint_verified_no_projection_advance(persistent, expected),
        expected,
    )


def retry_epoch(
    *,
    work_id: str,
    attempt_id: str,
    retry_of_attempt_id: str,
    attempt_number: int,
    seq: int,
) -> tuple[
    PersistentTaskEvent, EventEnvelope, EventEnvelope, ProgressNotificationBinding
]:
    command_id = f"command-retry-{attempt_number}"
    details = {
        "command_id": command_id,
        "retry_of_attempt_id": retry_of_attempt_id,
        "previous_outcome": "completed",
        "attempt_number": attempt_number,
    }
    persistent = PersistentTaskEvent(
        event_id=f"task-event:{work_id}:retry:{attempt_number}",
        task_id=work_id,
        attempt_id=attempt_id,
        scope=scope(),
        seq=seq,
        event_type="task.retry_accepted",
        state="accepted",
        outcome=None,
        producer="task_core",
        source_event_id=None,
        causation_id=command_id,
        correlation_id="correlation-1",
        occurred_at="2026-08-06T08:00:00Z",
        details=details,
    )
    source = EventEnvelope.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "event_id": persistent.event_id,
            "event_type": persistent.event_type,
            "producer": {
                "component": "task_core",
                "instance_id": "task_core-1",
                "authority": "task_core",
            },
            "stream_ref": {"kind": "task", "id": work_id},
            "seq": seq,
            "occurred_at": persistent.occurred_at,
            "scope": scope().to_dict(),
            "correlation_id": persistent.correlation_id,
            "causation_id": command_id,
            "required_capabilities": [],
            "payload": {"state": "accepted", **details},
            "extensions": {
                "jiuwenswarm.task_progress_return": {
                    "persistent_event_seq": seq,
                    "persistent_event_type": persistent.event_type,
                    "persistent_event_producer": persistent.producer,
                    "persistent_attempt_id": attempt_id,
                    "persistent_source_event_id": None,
                }
            },
        }
    )
    projected = progress_event(source)
    expected = binding(source, projected)
    return persistent, source, projected, expected


def task_attempt_source_variant(
    source: EventEnvelope,
    *,
    event_id: str,
    event_type: str,
    seq: int,
    state: str,
    outcome: str | None = None,
) -> EventEnvelope:
    document = source.to_dict()
    document.update(
        {
            "event_id": event_id,
            "event_type": event_type,
            "seq": seq,
            "causation_id": source.event_id,
            "payload": {
                "state": state,
                **({"outcome": outcome} if outcome is not None else {}),
            },
        }
    )
    extension = document["extensions"]["jiuwenswarm.task_progress_return"]
    extension["persistent_event_seq"] = seq
    extension["persistent_event_type"] = event_type
    return EventEnvelope.from_dict(document)


def test_constructor_rejects_noncanonical_flags_and_capacities() -> None:
    with pytest.raises(ProgressNotificationArbiterViolation) as invalid_flag:
        ProgressNotificationArbiter(enabled=1)  # type: ignore[arg-type]
    assert invalid_flag.value.reason == "INVALID_FEATURE_FLAG"
    for keyword in ("pending_capacity", "stream_capacity", "events_per_stream"):
        with pytest.raises(ProgressNotificationArbiterViolation) as invalid_capacity:
            ProgressNotificationArbiter(**{keyword: 0})
        assert invalid_capacity.value.reason == "INVALID_ARBITER_CAPACITY"


def test_no_projection_capability_is_internal_and_cannot_be_directly_minted() -> None:
    arbiter = ProgressNotificationArbiter()
    accepted = source_event(work_kind="task", work_id="task-private-capability")
    projected = progress_event(accepted)
    advance, expected = no_projection_advance(accepted, projected, seq=1)

    assert not hasattr(arbiter, "advance_without_projection")
    assert "VerifiedNoProjectionAdvance" not in arbiter_module.__all__
    with pytest.raises(TypeError):
        arbiter_module._VerifiedNoProjectionAdvance(  # type: ignore[call-arg]
            advance.source_event,
            expected,
        )
    with pytest.raises(ProgressNotificationArbiterViolation) as forged:
        arbiter_module._VerifiedNoProjectionAdvance(
            advance.source_event,
            expected,
            consumer_scope=False,
            _token=object(),
        )
    assert forged.value.reason == "INVALID_NO_PROJECTION_CAPABILITY"
    assert advance.source_event.event_id not in repr(advance)


def test_feature_off_returns_before_inspecting_inputs_and_has_zero_state() -> None:
    class Explosive:
        def __getattribute__(self, name: str):
            raise AssertionError(f"feature-off inspected {name}")

    arbiter = ProgressNotificationArbiter(enabled=False)
    decision = arbiter.offer(Explosive(), Explosive(), Explosive(), Explosive())
    assert decision.disposition is NotificationDisposition.FEATURE_DISABLED
    advance = arbiter._advance_without_projection(Explosive())
    assert advance.disposition is NoProjectionAdvanceDisposition.FEATURE_DISABLED
    assert decision.progress is None
    assert arbiter.drain(Explosive(), Explosive()) == ()
    assert arbiter.acknowledge(Explosive(), Explosive(), Explosive()) is False
    assert arbiter.snapshot().tracked_work_streams == 0
    assert arbiter.snapshot().pending_notifications == 0
    assert arbiter.snapshot().rejected_events == 0


def test_retry_epoch_retires_pending_and_rejects_old_attempt_before_identity() -> None:
    arbiter = ProgressNotificationArbiter()
    work_id = "task-retry-epoch"
    accepted_a = source_event(work_kind="task", work_id=work_id)
    projected_a = progress_event(accepted_a)
    deferred_a = offer(
        arbiter,
        accepted_a,
        projected_a,
        foreground=busy_foreground(),
    )
    assert deferred_a.disposition is NotificationDisposition.DEFERRED
    assert arbiter.snapshot().pending_notifications == 1

    boundary_b, source_b, projected_b, binding_b = retry_epoch(
        work_id=work_id,
        attempt_id="attempt-b",
        retry_of_attempt_id="attempt-a",
        attempt_number=2,
        seq=5,
    )
    baseline_b = arbiter_module._mint_verified_attempt_epoch_baseline(
        boundary_b, binding_b
    )
    arbiter._begin_attempt_epoch(baseline_b)

    retired = arbiter.snapshot()
    assert retired.pending_notifications == 0
    assert retired.superseded_notifications == 1
    assert not arbiter.acknowledge(scope(), accepted_a.stream_ref, projected_a.event_id)
    accepted_b = offer(arbiter, source_b, projected_b, expected=binding_b)
    assert accepted_b.disposition is NotificationDisposition.DISPLAY_NOW
    assert arbiter.snapshot().pending_notifications == 1

    old_source_dict = source_b.to_dict()
    old_source_dict.update(
        {
            "event_id": "task-event:old-attempt:late",
            "event_type": "task.running",
            "seq": 6,
            "causation_id": source_b.event_id,
            "payload": {"state": "running"},
        }
    )
    old_source_dict["extensions"]["jiuwenswarm.task_progress_return"][
        "persistent_attempt_id"
    ] = "attempt-a"
    old_source = EventEnvelope.from_dict(old_source_dict)
    old_progress = progress_event(old_source)
    before_offer = arbiter.snapshot()

    stale_offer = offer(
        arbiter,
        old_source,
        old_progress,
        expected=binding(old_source, old_progress),
    )

    assert stale_offer.disposition is NotificationDisposition.REJECTED
    assert stale_offer.reason == "STALE_ATTEMPT"
    assert stale_offer.code is ErrorCode.STALE
    after_offer = arbiter.snapshot()
    assert after_offer.retained_source_events == before_offer.retained_source_events
    assert after_offer.retained_progress_events == before_offer.retained_progress_events
    assert after_offer.pending_notifications == before_offer.pending_notifications
    assert after_offer.accepted_events == before_offer.accepted_events

    stale_attempt_event = PersistentTaskEvent(
        event_id="task-event:old-attempt:no-projection",
        task_id=work_id,
        attempt_id="attempt-a",
        scope=scope(),
        seq=6,
        event_type="attempt.running",
        state="running",
        outcome=None,
        producer="executor-1",
        source_event_id="executor-source:old-attempt:6",
        causation_id="executor-source:old-attempt:6",
        correlation_id="correlation-1",
        occurred_at="2026-08-06T08:00:00Z",
        details={},
    )
    stale_advance = arbiter_module._mint_verified_no_projection_advance(
        stale_attempt_event, binding_b
    )
    before_advance = arbiter.snapshot()

    stale_no_projection = arbiter._advance_without_projection(stale_advance)

    assert stale_no_projection.disposition is NoProjectionAdvanceDisposition.REJECTED
    assert stale_no_projection.reason == "STALE_ATTEMPT"
    assert stale_no_projection.code is ErrorCode.STALE
    after_advance = arbiter.snapshot()
    assert after_advance.retained_source_events == before_advance.retained_source_events
    assert after_advance.no_projection_advances == before_advance.no_projection_advances
    assert after_advance.pending_notifications == before_advance.pending_notifications


def test_retry_epoch_capability_is_private_and_cannot_regress() -> None:
    arbiter = ProgressNotificationArbiter()
    boundary_b, _source_b, _projected_b, binding_b = retry_epoch(
        work_id="task-retry-epoch-private",
        attempt_id="attempt-b",
        retry_of_attempt_id="attempt-a",
        attempt_number=2,
        seq=5,
    )
    with pytest.raises(TypeError):
        arbiter_module._VerifiedAttemptEpochBaseline(  # type: ignore[call-arg]
            boundary_b,
            binding_b,
        )
    with pytest.raises(ProgressNotificationArbiterViolation) as forged:
        arbiter_module._VerifiedAttemptEpochBaseline(
            boundary_b,
            binding_b,
            consumer_scope=False,
            _token=object(),
        )
    assert forged.value.reason == "INVALID_ATTEMPT_EPOCH_CAPABILITY"

    invalid_boundary = replace(
        boundary_b,
        details={
            **dict(boundary_b.details),
            "retry_of_attempt_id": boundary_b.attempt_id,
        },
    )
    before_invalid = arbiter.snapshot()
    with pytest.raises(ProgressNotificationArbiterViolation) as invalid_lineage:
        arbiter._begin_attempt_epoch(
            arbiter_module._mint_verified_attempt_epoch_baseline(
                invalid_boundary, binding_b
            )
        )
    assert invalid_lineage.value.reason == "INVALID_ATTEMPT_EPOCH_BASELINE"
    assert arbiter.snapshot() == before_invalid

    baseline_b = arbiter_module._mint_verified_attempt_epoch_baseline(
        boundary_b, binding_b
    )
    arbiter._begin_attempt_epoch(baseline_b)
    boundary_c, _source_c, _projected_c, binding_c = retry_epoch(
        work_id="task-retry-epoch-private",
        attempt_id="attempt-c",
        retry_of_attempt_id="attempt-b",
        attempt_number=3,
        seq=9,
    )
    arbiter._begin_attempt_epoch(
        arbiter_module._mint_verified_attempt_epoch_baseline(boundary_c, binding_c)
    )

    with pytest.raises(ProgressNotificationArbiterViolation) as stale:
        arbiter._begin_attempt_epoch(baseline_b)
    assert stale.value.reason == "STALE_ATTEMPT_EPOCH"


def test_verified_no_projection_advances_all_sequences_without_delivery_state() -> None:
    arbiter = ProgressNotificationArbiter()
    accepted = source_event(work_kind="task", work_id="task-no-projection")
    accepted_progress = progress_event(accepted)
    first = offer(arbiter, accepted, accepted_progress)
    assert first.disposition is NotificationDisposition.DISPLAY_NOW
    assert arbiter.acknowledge(first.scope, first.work_ref, first.event_id)

    for seq, event_type in (
        (1, "attempt.accepted"),
        (2, "attempt.running"),
        (3, "task.cancel_requested"),
        (4, "attempt.terminal"),
    ):
        advance, _ = no_projection_advance(
            accepted,
            accepted_progress,
            seq=seq,
            event_type=event_type,
        )
        result = arbiter._advance_without_projection(advance)
        assert result.disposition is NoProjectionAdvanceDisposition.ADVANCED
        assert result.source_seq == seq
        assert arbiter.drain(scope(), safe_foreground()) == ()
        assert not arbiter.acknowledge(
            scope(), accepted.stream_ref, advance.source_event.event_id
        )

    running = source_event(
        work_kind="task",
        work_id="task-no-projection",
        seq=5,
        state="running",
    )
    projected = progress_event(running)
    delivered = offer(arbiter, running, projected)
    assert delivered.disposition is NotificationDisposition.DISPLAY_NOW
    snapshot = arbiter.snapshot()
    assert snapshot.accepted_events == 2
    assert snapshot.no_projection_advances == 4
    assert snapshot.pending_notifications == 1
    assert snapshot.terminal_work_streams == 0


def test_no_projection_duplicate_is_idempotent_and_cannot_be_reprojected() -> None:
    arbiter = ProgressNotificationArbiter()
    accepted = source_event(work_kind="task", work_id="task-duplicate")
    projected = progress_event(accepted)
    assert offer(arbiter, accepted, projected).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    advance, expected = no_projection_advance(accepted, projected, seq=1)
    first = arbiter._advance_without_projection(advance)
    before = arbiter.snapshot()
    duplicate = arbiter._advance_without_projection(advance)
    after = arbiter.snapshot()
    assert first.disposition is NoProjectionAdvanceDisposition.ADVANCED
    assert duplicate.disposition is NoProjectionAdvanceDisposition.DUPLICATE
    assert after.no_projection_advances == before.no_projection_advances
    assert after.no_projection_duplicates == before.no_projection_duplicates + 1
    assert after.pending_notifications == before.pending_notifications

    changed_record = arbiter_module._mint_verified_no_projection_advance(
        replace(advance.source_event, details={"tampered": True}),
        expected,
    )
    record_conflict = arbiter._advance_without_projection(changed_record)
    assert record_conflict.disposition is NoProjectionAdvanceDisposition.REJECTED
    assert record_conflict.reason == "SOURCE_EVENT_ID_CONFLICT"
    assert arbiter.snapshot().no_projection_advances == 1

    forged_source = source_event(
        work_kind="task",
        work_id="task-duplicate",
        seq=1,
        state="running",
        event_id=advance.source_event.event_id,
    )
    forged_projection = progress_event(forged_source)
    conflict = offer(arbiter, forged_source, forged_projection)
    assert conflict.disposition is NotificationDisposition.REJECTED
    assert conflict.reason == "SOURCE_EVENT_PROJECTION_CLASS_CONFLICT"
    assert arbiter.snapshot().accepted_events == 1


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("partial", "INVALID_NO_PROJECTION_ADVANCE"),
        ("unknown", "INVALID_NO_PROJECTION_SOURCE_EVENT"),
        ("projectable", "INVALID_NO_PROJECTION_SOURCE_EVENT"),
        ("scope", "NO_PROJECTION_BINDING_MISMATCH"),
        ("correlation", "NO_PROJECTION_BINDING_MISMATCH"),
        ("task", "NO_PROJECTION_BINDING_MISMATCH"),
        ("source_component", "INVALID_NO_PROJECTION_ADVANCE"),
        ("producer", "INVALID_NO_PROJECTION_SOURCE_EVENT"),
        ("lifecycle", "INVALID_NO_PROJECTION_SOURCE_EVENT"),
        ("source_evidence", "INVALID_NO_PROJECTION_SOURCE_EVENT"),
    ],
)
def test_invalid_no_projection_evidence_has_zero_partial_sequence_effect(
    mutation: str,
    reason: str,
) -> None:
    arbiter = ProgressNotificationArbiter()
    accepted = source_event(work_kind="task", work_id="task-invalid-advance")
    projected = progress_event(accepted)
    assert offer(arbiter, accepted, projected).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    advance, expected = no_projection_advance(accepted, projected, seq=1)
    event = advance.source_event
    if mutation == "partial":
        advance = arbiter_module._mint_verified_no_projection_advance(  # type: ignore[arg-type]
            {"event_id": event.event_id},
            expected,
        )
    elif mutation == "unknown":
        advance = arbiter_module._mint_verified_no_projection_advance(
            replace(event, event_type="task.unknown"),
            expected,
        )
    elif mutation == "projectable":
        advance = arbiter_module._mint_verified_no_projection_advance(
            replace(event, event_type="task.running"),
            expected,
        )
    elif mutation == "scope":
        advance = arbiter_module._mint_verified_no_projection_advance(
            replace(event, scope=scope(session_id="foreign")),
            expected,
        )
    elif mutation == "correlation":
        advance = arbiter_module._mint_verified_no_projection_advance(
            replace(event, correlation_id="foreign"),
            expected,
        )
    elif mutation == "task":
        advance = arbiter_module._mint_verified_no_projection_advance(
            replace(event, task_id="foreign"),
            expected,
        )
    elif mutation == "source_component":
        expected = replace(
            expected,
            source_producer=ProducerRef(
                component="task_core.delivery",
                instance_id=expected.source_producer.instance_id,
                authority="task_core",
            ),
        )
        advance = arbiter_module._mint_verified_no_projection_advance(
            event,
            expected,
        )
    elif mutation == "producer":
        advance = arbiter_module._mint_verified_no_projection_advance(
            replace(event, producer="task_core.control"),
            expected,
        )
    elif mutation == "lifecycle":
        advance = arbiter_module._mint_verified_no_projection_advance(
            replace(event, state="accepted"),
            expected,
        )
    else:
        advance = arbiter_module._mint_verified_no_projection_advance(
            replace(event, source_event_id=None),
            expected,
        )
    before = arbiter.snapshot()
    result = arbiter._advance_without_projection(advance)
    after = arbiter.snapshot()
    assert result.disposition is NoProjectionAdvanceDisposition.REJECTED
    assert result.reason == reason
    assert after.tracked_source_streams == before.tracked_source_streams
    assert after.tracked_progress_streams == before.tracked_progress_streams
    assert after.tracked_work_streams == before.tracked_work_streams
    assert after.retained_source_events == before.retained_source_events
    assert after.retained_progress_events == before.retained_progress_events
    assert after.pending_notifications == before.pending_notifications
    assert after.accepted_events == before.accepted_events
    assert after.no_projection_advances == before.no_projection_advances


def test_no_projection_exact_type_checks_precede_untrusted_field_methods() -> None:
    class Explosive:
        def __getattribute__(self, name: str):
            raise AssertionError(f"untrusted field method accessed: {name}")

    arbiter = ProgressNotificationArbiter()
    accepted = source_event(work_kind="task", work_id="task-exact-types")
    projected = progress_event(accepted)
    assert offer(arbiter, accepted, projected).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    advance, expected = no_projection_advance(accepted, projected, seq=1)
    before = arbiter.snapshot()

    invalid_event = arbiter_module._mint_verified_no_projection_advance(  # type: ignore[arg-type]
        Explosive(),
        expected,
    )
    event_result = arbiter._advance_without_projection(invalid_event)
    invalid_binding = replace(expected, scope=Explosive())  # type: ignore[arg-type]
    invalid_binding_advance = arbiter_module._mint_verified_no_projection_advance(
        advance.source_event,
        invalid_binding,
    )
    binding_result = arbiter._advance_without_projection(invalid_binding_advance)

    assert event_result.reason == "INVALID_NO_PROJECTION_ADVANCE"
    assert binding_result.reason == "INVALID_PROGRESS_BINDING"
    after = arbiter.snapshot()
    assert after.no_projection_advances == before.no_projection_advances
    assert after.retained_source_events == before.retained_source_events
    assert after.pending_notifications == before.pending_notifications


def test_no_projection_gap_conflict_capacity_and_race_are_atomic() -> None:
    arbiter = ProgressNotificationArbiter(events_per_stream=2)
    accepted = source_event(work_kind="task", work_id="task-atomic-advance")
    projected = progress_event(accepted)
    assert offer(arbiter, accepted, projected).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    gap, _ = no_projection_advance(accepted, projected, seq=2)
    gap_result = arbiter._advance_without_projection(gap)
    assert gap_result.reason == "SOURCE_SEQUENCE_GAP"
    assert arbiter.snapshot().no_projection_advances == 0

    candidates = [
        no_projection_advance(
            accepted,
            projected,
            seq=1,
            event_id=f"task-event:race:{index}",
        )[0]
        for index in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                arbiter._advance_without_projection,
                candidates,
            )
        )
    assert (
        sum(
            item.disposition is NoProjectionAdvanceDisposition.ADVANCED
            for item in results
        )
        == 1
    )
    assert (
        sum(
            item.disposition is NoProjectionAdvanceDisposition.REJECTED
            for item in results
        )
        == 1
    )
    before_capacity = arbiter.snapshot()
    capacity, _ = no_projection_advance(accepted, projected, seq=2)
    full = arbiter._advance_without_projection(capacity)
    after_capacity = arbiter.snapshot()
    assert full.disposition is NoProjectionAdvanceDisposition.BACKPRESSURE
    assert full.reason == "SOURCE_EVENT_CAPACITY_EXHAUSTED"
    assert (
        after_capacity.no_projection_advances == before_capacity.no_projection_advances
    )
    assert (
        after_capacity.retained_source_events == before_capacity.retained_source_events
    )


def test_no_projection_cannot_create_or_extend_work_lifecycle() -> None:
    arbiter = ProgressNotificationArbiter()
    accepted = source_event(work_kind="task", work_id="task-lifecycle-fence")
    accepted_progress = progress_event(accepted)
    initial, _ = no_projection_advance(
        accepted,
        accepted_progress,
        seq=0,
        event_type="attempt.accepted",
    )
    missing = arbiter._advance_without_projection(initial)
    assert missing.disposition is NoProjectionAdvanceDisposition.REJECTED
    assert missing.reason == "WORK_ACCEPTED_REQUIRED"
    assert arbiter.snapshot().tracked_work_streams == 0

    assert offer(arbiter, accepted, accepted_progress).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    terminal = source_event(
        work_kind="task",
        work_id="task-lifecycle-fence",
        seq=1,
        state="terminal",
        outcome="completed",
    )
    terminal_progress = progress_event(terminal)
    assert offer(arbiter, terminal, terminal_progress).state.value == "terminal"
    after_terminal, _ = no_projection_advance(
        terminal,
        terminal_progress,
        seq=2,
        event_type="attempt.terminal",
    )
    rejected = arbiter._advance_without_projection(after_terminal)
    assert rejected.disposition is NoProjectionAdvanceDisposition.REJECTED
    assert rejected.reason == "WORK_EVENT_AFTER_TERMINAL"
    assert arbiter.snapshot().no_projection_advances == 0


def test_idle_round_progress_displays_and_only_hint_can_be_speech_candidate() -> None:
    arbiter = ProgressNotificationArbiter()
    accepted = source_event()
    silent = progress_event(accepted, speakability="not_speakable")
    first = offer(arbiter, accepted, silent)
    assert first.disposition is NotificationDisposition.DISPLAY_NOW
    assert first.speech is SpeechDisposition.NOT_A_CANDIDATE

    running = source_event(seq=1, state="running")
    eligible = progress_event(running, speakability="eligible")
    second = offer(arbiter, running, eligible)
    assert second.disposition is NotificationDisposition.DISPLAY_NOW
    assert second.speech is SpeechDisposition.SPEAK_WHEN_SAFE_CANDIDATE
    assert arbiter.snapshot().pending_notifications == 1
    assert arbiter.acknowledge(second.scope, second.work_ref, second.event_id) is True
    assert arbiter.snapshot().pending_notifications == 0

    attention = source_event(seq=2, state="blocked")
    requested = progress_event(attention, speakability="attention_requested")
    display_only = offer(
        arbiter,
        attention,
        requested,
        foreground=safe_foreground(speech_policy=SpeechPolicy.DISPLAY_ONLY),
    )
    assert display_only.disposition is NotificationDisposition.DISPLAY_NOW
    assert display_only.speech is SpeechDisposition.NOT_A_CANDIDATE


def test_round_and_task_streams_are_independent_and_keep_terminal_truth() -> None:
    arbiter = ProgressNotificationArbiter()
    round_accepted = source_event(work_id="round-a")
    task_accepted = source_event(work_kind="task", work_id="task-a")
    for source in (round_accepted, task_accepted):
        decision = offer(arbiter, source, progress_event(source))
        assert decision.projection_seq == 0
        assert decision.state.value == "accepted"

    round_terminal = source_event(
        work_id="round-a", seq=1, state="terminal", outcome="completed"
    )
    task_terminal = source_event(
        work_kind="task",
        work_id="task-a",
        seq=1,
        state="terminal",
        outcome="failed",
    )
    round_result = offer(arbiter, round_terminal, progress_event(round_terminal))
    task_result = offer(arbiter, task_terminal, progress_event(task_terminal))
    assert round_result.outcome.value == "completed"
    assert task_result.outcome.value == "failed"
    snapshot = arbiter.snapshot()
    assert snapshot.tracked_work_streams == 2
    assert snapshot.terminal_work_streams == 2


def test_drain_and_ack_are_exact_scope_bound_with_same_work_identity() -> None:
    scope_a = scope(session_id="session-a")
    scope_b = scope(session_id="session-b")
    source_a = source_event(
        work_id="shared-round-id",
        current_scope=scope_a,
        event_id="source:scope-a",
        producer_instance="harness-a",
    )
    progress_a = progress_event(
        source_a,
        event_id="progress:scope-a",
        producer_instance="progress-a",
    )
    source_b = source_event(
        work_id="shared-round-id",
        current_scope=scope_b,
        event_id="source:scope-b",
        producer_instance="harness-b",
    )
    progress_b = progress_event(
        source_b,
        event_id="progress:scope-b",
        producer_instance="progress-b",
    )
    arbiter = ProgressNotificationArbiter()
    assert offer(arbiter, source_a, progress_a).scope == scope_a
    assert offer(arbiter, source_b, progress_b).scope == scope_b
    diagnostic = arbiter.snapshot()
    assert diagnostic.pending_notifications == 2
    assert not hasattr(diagnostic, "pending_work_refs")
    assert "shared-round-id" not in repr(diagnostic)

    drained_a = arbiter.drain(scope_a, safe_foreground())
    assert tuple(item.event_id for item in drained_a) == (progress_a.event_id,)
    assert all(item.scope == scope_a for item in drained_a)
    assert (
        arbiter.acknowledge(scope_a, progress_b.stream_ref, progress_b.event_id)
        is False
    )
    assert arbiter.snapshot().pending_notifications == 2

    request_asserted = scope(
        session_id="session-b", assurance=Assurance.REQUEST_ASSERTED
    )
    unauthenticated = arbiter.drain(request_asserted, safe_foreground())
    assert unauthenticated[0].reason == "UNAUTHENTICATED_CONSUMER_SCOPE"
    assert (
        arbiter.acknowledge(
            request_asserted, progress_b.stream_ref, progress_b.event_id
        )
        is False
    )
    malformed_scope = ScopeRef("", "project-1", "session-b", Assurance.AUTHENTICATED)
    malformed = arbiter.drain(malformed_scope, safe_foreground())
    assert malformed[0].reason == "INVALID_CONSUMER_SCOPE"
    assert (
        arbiter.acknowledge(malformed_scope, progress_b.stream_ref, progress_b.event_id)
        is False
    )
    assert arbiter.snapshot().pending_notifications == 2

    assert (
        arbiter.acknowledge(scope_a, progress_a.stream_ref, progress_a.event_id) is True
    )
    drained_b = arbiter.drain(scope_b, safe_foreground())
    assert tuple(item.event_id for item in drained_b) == (progress_b.event_id,)
    assert arbiter.acknowledge(scope_b, progress_b.stream_ref, progress_b.event_id)
    assert arbiter.snapshot().pending_notifications == 0


def test_busy_and_unknown_foreground_defer_until_all_facts_are_safe() -> None:
    arbiter = ProgressNotificationArbiter()
    accepted = source_event()
    projected = progress_event(
        accepted,
        speakability="eligible",
        urgency="attention",
        summary={"knowledge": "known", "value": "still working"},
        blocking_question={"knowledge": "known", "value": "continue?"},
        artifact_refs={"knowledge": "known", "value": []},
    )
    busy = offer(arbiter, accepted, projected, foreground=busy_foreground())
    assert busy.disposition is NotificationDisposition.DEFERRED
    assert busy.speech is SpeechDisposition.NOT_A_CANDIDATE
    assert busy.progress is not None
    assert busy.progress.to_dict() == projected.payload
    assert arbiter.drain(scope(), unknown_foreground()) == ()
    drained = arbiter.drain(scope(), safe_foreground())
    assert len(drained) == 1
    assert drained[0].disposition is NotificationDisposition.DISPLAY_NOW
    assert drained[0].speech is SpeechDisposition.SPEAK_WHEN_SAFE_CANDIDATE
    assert drained[0].progress is busy.progress
    assert drained[0].progress.to_dict() == projected.payload
    assert (
        arbiter.acknowledge(drained[0].scope, drained[0].work_ref, drained[0].event_id)
        is True
    )


def test_deferred_coalescing_protects_decision_and_terminal_notifications() -> None:
    arbiter = ProgressNotificationArbiter()
    states = ("accepted", "running", "decision_required", "running", "terminal")
    results = []
    for seq, state in enumerate(states):
        source = source_event(
            seq=seq,
            state=state,
            outcome="completed" if state == "terminal" else None,
        )
        results.append(
            offer(
                arbiter,
                source,
                progress_event(
                    source,
                    summary={
                        "knowledge": "known",
                        "value": (
                            "approval required"
                            if state == "decision_required"
                            else f"state:{state}"
                        ),
                    },
                    blocking_question=(
                        {"knowledge": "known", "value": "approve?"}
                        if state == "decision_required"
                        else {"knowledge": "unknown"}
                    ),
                ),
                foreground=busy_foreground(),
            )
        )
    assert results[3].reason == "protected_pending_notification_retained"
    assert results[3].retained_event_id == results[2].event_id
    assert results[3].event_id == results[2].event_id
    assert results[3].progress is results[2].progress
    assert results[3].progress.state.value == "decision_required"
    assert results[3].progress.summary.value == "approval required"
    assert arbiter.snapshot().pending_notifications == 1
    drained = arbiter.drain(scope(), safe_foreground())
    assert len(drained) == 1
    assert drained[0].state.value == "terminal"
    assert drained[0].outcome.value == "completed"
    assert (
        arbiter.acknowledge(results[2].scope, results[2].work_ref, results[2].event_id)
        is False
    )
    assert (
        arbiter.acknowledge(drained[0].scope, drained[0].work_ref, drained[0].event_id)
        is True
    )


def test_exact_duplicate_is_idempotent_and_conflicting_ids_fail_closed() -> None:
    arbiter = ProgressNotificationArbiter()
    source = source_event()
    projected = progress_event(source)
    first = offer(arbiter, source, projected)
    before = arbiter.snapshot()
    duplicate = offer(arbiter, source, projected)
    assert duplicate.disposition is NotificationDisposition.DUPLICATE
    assert duplicate.progress is first.progress
    after = arbiter.snapshot()
    assert after.accepted_events == before.accepted_events
    assert after.pending_notifications == before.pending_notifications
    assert after.duplicate_events == before.duplicate_events + 1

    changed_progress = progress_event(
        source, event_id=projected.event_id, urgency="urgent"
    )
    conflict = offer(arbiter, source, changed_progress)
    assert conflict.disposition is NotificationDisposition.REJECTED
    assert conflict.progress is None
    assert conflict.reason == "PROGRESS_EVENT_ID_CONFLICT"
    assert arbiter.snapshot().accepted_events == 1
    assert arbiter.snapshot().pending_notifications == 1
    assert first.event_id == projected.event_id


def test_concurrent_exact_duplicates_have_one_delivery_candidate() -> None:
    worker_count = 12
    gate = Barrier(worker_count)
    arbiter = ProgressNotificationArbiter()
    source = source_event(event_id="source:concurrent-duplicate")
    projected = progress_event(
        source,
        event_id="progress:concurrent-duplicate",
        speakability="eligible",
    )

    def invoke_offer():
        gate.wait(timeout=5)
        return offer(arbiter, source, projected)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(invoke_offer) for _ in range(worker_count)]
        decisions = [future.result(timeout=10) for future in futures]

    assert (
        sum(
            item.disposition is NotificationDisposition.DISPLAY_NOW
            for item in decisions
        )
        == 1
    )
    assert (
        sum(item.disposition is NotificationDisposition.DUPLICATE for item in decisions)
        == worker_count - 1
    )
    assert (
        sum(
            item.speech is SpeechDisposition.SPEAK_WHEN_SAFE_CANDIDATE
            for item in decisions
        )
        == 1
    )
    snapshot = arbiter.snapshot()
    assert snapshot.accepted_events == 1
    assert snapshot.duplicate_events == worker_count - 1
    assert snapshot.pending_notifications == 1
    assert snapshot.retained_source_events == 1
    assert snapshot.retained_progress_events == 1


def test_concurrent_same_sequence_conflict_has_one_accepted_event() -> None:
    gate = Barrier(2)
    arbiter = ProgressNotificationArbiter()
    source_a = source_event(event_id="source:concurrent-a")
    source_b = source_event(event_id="source:concurrent-b")
    progress_a = progress_event(
        source_a,
        event_id="progress:concurrent-a",
        speakability="eligible",
    )
    progress_b = progress_event(
        source_b,
        event_id="progress:concurrent-b",
        speakability="eligible",
    )

    def invoke_offer(source: EventEnvelope, projected: EventEnvelope):
        gate.wait(timeout=5)
        return offer(arbiter, source, projected)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(invoke_offer, source_a, progress_a)
        future_b = executor.submit(invoke_offer, source_b, progress_b)
        decisions = [future_a.result(timeout=10), future_b.result(timeout=10)]

    assert (
        sum(
            item.disposition is NotificationDisposition.DISPLAY_NOW
            for item in decisions
        )
        == 1
    )
    assert (
        sum(item.disposition is NotificationDisposition.REJECTED for item in decisions)
        == 1
    )
    rejected = next(
        item
        for item in decisions
        if item.disposition is NotificationDisposition.REJECTED
    )
    assert rejected.reason == "SOURCE_SEQUENCE_CONFLICT"
    assert rejected.speech is SpeechDisposition.NOT_A_CANDIDATE
    assert (
        sum(
            item.speech is SpeechDisposition.SPEAK_WHEN_SAFE_CANDIDATE
            for item in decisions
        )
        == 1
    )
    snapshot = arbiter.snapshot()
    assert snapshot.accepted_events == 1
    assert snapshot.rejected_events == 1
    assert snapshot.pending_notifications == 1
    assert snapshot.retained_source_events == 2
    assert snapshot.retained_progress_events == 2


def test_concurrent_duplicate_drain_ack_and_snapshot_are_linearizable() -> None:
    gate = Barrier(4)
    arbiter = ProgressNotificationArbiter()
    source = source_event(event_id="source:concurrent-consumer")
    projected = progress_event(
        source,
        event_id="progress:concurrent-consumer",
        speakability="eligible",
    )
    first = offer(arbiter, source, projected)
    assert first.disposition is NotificationDisposition.DISPLAY_NOW

    def retry_offer():
        gate.wait(timeout=5)
        return offer(arbiter, source, projected)

    def drain_pending():
        gate.wait(timeout=5)
        return arbiter.drain(scope(), safe_foreground())

    def acknowledge_pending():
        gate.wait(timeout=5)
        return arbiter.acknowledge(
            projected.scope, projected.stream_ref, projected.event_id
        )

    def observe_snapshot():
        gate.wait(timeout=5)
        return arbiter.snapshot()

    with ThreadPoolExecutor(max_workers=4) as executor:
        retry_future = executor.submit(retry_offer)
        drain_future = executor.submit(drain_pending)
        ack_future = executor.submit(acknowledge_pending)
        snapshot_future = executor.submit(observe_snapshot)
        duplicate = retry_future.result(timeout=10)
        drained = drain_future.result(timeout=10)
        acknowledged = ack_future.result(timeout=10)
        concurrent_snapshot = snapshot_future.result(timeout=10)

    assert duplicate.disposition is NotificationDisposition.DUPLICATE
    assert duplicate.speech is SpeechDisposition.NOT_A_CANDIDATE
    assert acknowledged is True
    assert len(drained) in {0, 1}
    if drained:
        assert drained[0].event_id == projected.event_id
        assert drained[0].disposition is NotificationDisposition.DISPLAY_NOW
        assert drained[0].speech is SpeechDisposition.SPEAK_WHEN_SAFE_CANDIDATE
    assert concurrent_snapshot.accepted_events == 1
    assert concurrent_snapshot.duplicate_events in {0, 1}
    assert concurrent_snapshot.pending_notifications in {0, 1}
    final = arbiter.snapshot()
    assert final.accepted_events == 1
    assert final.duplicate_events == 1
    assert final.pending_notifications == 0


def test_source_event_conflict_and_reprojection_are_rejected() -> None:
    arbiter = ProgressNotificationArbiter()
    source = source_event()
    projected = progress_event(source)
    assert offer(arbiter, source, projected).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )

    changed_source = source_event(
        event_id=source.event_id,
        producer_component="test.changed_harness",
    )
    changed_projection = progress_event(changed_source, event_id=projected.event_id)
    source_conflict = offer(
        arbiter,
        changed_source,
        changed_projection,
        expected=binding(changed_source, changed_projection),
    )
    assert source_conflict.reason == "SOURCE_EVENT_ID_CONFLICT"

    reprojection = progress_event(source, event_id="progress:reprojected")
    projected_twice = offer(arbiter, source, reprojection)
    assert projected_twice.reason == "SOURCE_EVENT_REPROJECTED"
    assert arbiter.snapshot().accepted_events == 1


@pytest.mark.parametrize(
    ("source_seq", "envelope_seq", "projection_seq", "reason"),
    [
        (1, 0, 0, "SOURCE_SEQUENCE_GAP"),
        (0, 1, 0, "PROGRESS_ENVELOPE_SEQUENCE_GAP"),
        (0, 0, 1, "WORK_PROJECTION_SEQUENCE_GAP"),
    ],
)
def test_sequence_gaps_never_reorder_or_advance_state(
    source_seq: int,
    envelope_seq: int,
    projection_seq: int,
    reason: str,
) -> None:
    arbiter = ProgressNotificationArbiter()
    source = source_event(seq=source_seq)
    projected = progress_event(
        source,
        envelope_seq=envelope_seq,
        projection_seq=projection_seq,
    )
    result = offer(arbiter, source, projected)
    assert result.disposition is NotificationDisposition.REJECTED
    assert result.reason == reason
    snapshot = arbiter.snapshot()
    assert snapshot.accepted_events == 0
    assert snapshot.tracked_work_streams == 0
    assert snapshot.pending_notifications == 0


def test_gap_observation_freezes_bytes_and_pairing_before_exact_retry() -> None:
    arbiter = ProgressNotificationArbiter()
    gap_source = source_event(
        seq=1,
        state="running",
        event_id="source:mutable-gap",
    )
    gap_progress = progress_event(
        gap_source,
        event_id="progress:mutable-gap",
        urgency="normal",
        speakability="eligible",
    )

    first = offer(arbiter, gap_source, gap_progress)
    exact_retry = offer(arbiter, gap_source, gap_progress)
    assert first.reason == exact_retry.reason == "SOURCE_SEQUENCE_GAP"
    assert first.progress is exact_retry.progress is None
    assert first.speech is exact_retry.speech is SpeechDisposition.NOT_A_CANDIDATE

    mutated_source = source_event(
        seq=1,
        state="decision_required",
        event_id=gap_source.event_id,
    )
    mutated_progress = progress_event(
        mutated_source,
        event_id=gap_progress.event_id,
        urgency="urgent",
        speakability="attention_requested",
    )
    mutated = offer(arbiter, mutated_source, mutated_progress)
    assert mutated.reason == "SOURCE_EVENT_ID_CONFLICT"
    assert mutated.disposition is NotificationDisposition.REJECTED
    assert mutated.progress is None
    assert mutated.speech is SpeechDisposition.NOT_A_CANDIDATE

    reprojected = progress_event(
        gap_source,
        event_id="progress:gap-reprojected",
    )
    pairing_conflict = offer(arbiter, gap_source, reprojected)
    assert pairing_conflict.reason == "SOURCE_EVENT_REPROJECTED"
    assert pairing_conflict.disposition is NotificationDisposition.REJECTED
    assert pairing_conflict.speech is SpeechDisposition.NOT_A_CANDIDATE

    predecessor = source_event()
    assert offer(arbiter, predecessor, progress_event(predecessor)).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    accepted_retry = offer(arbiter, gap_source, gap_progress)
    assert accepted_retry.disposition is NotificationDisposition.DISPLAY_NOW
    assert accepted_retry.speech is SpeechDisposition.SPEAK_WHEN_SAFE_CANDIDATE
    snapshot = arbiter.snapshot()
    assert snapshot.accepted_events == 2
    assert snapshot.rejected_events == 4
    assert snapshot.pending_notifications == 1


def test_lifecycle_reject_freezes_identity_but_exact_retry_rechecks_policy() -> None:
    arbiter = ProgressNotificationArbiter()
    accepted = source_event()
    assert offer(arbiter, accepted, progress_event(accepted)).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    repeated_source = source_event(
        seq=1,
        state="accepted",
        event_id="source:mutable-lifecycle",
    )
    repeated_progress = progress_event(
        repeated_source,
        event_id="progress:mutable-lifecycle",
    )
    first = offer(arbiter, repeated_source, repeated_progress)
    exact_retry = offer(arbiter, repeated_source, repeated_progress)
    assert first.reason == exact_retry.reason == "WORK_ACCEPTED_REPEATED"

    mutated_progress = progress_event(
        repeated_source,
        event_id=repeated_progress.event_id,
        urgency="urgent",
        speakability="attention_requested",
    )
    mutated = offer(arbiter, repeated_source, mutated_progress)
    assert mutated.reason == "PROGRESS_EVENT_ID_CONFLICT"
    assert mutated.disposition is NotificationDisposition.REJECTED
    assert mutated.progress is None
    assert mutated.speech is SpeechDisposition.NOT_A_CANDIDATE
    snapshot = arbiter.snapshot()
    assert snapshot.accepted_events == 1
    assert snapshot.rejected_events == 3
    assert snapshot.pending_notifications == 1


def test_old_sequence_conflict_fails_closed() -> None:
    arbiter = ProgressNotificationArbiter()
    accepted = source_event()
    assert offer(arbiter, accepted, progress_event(accepted)).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )

    reused = source_event(seq=0, event_id="source:changed-id")
    reused_projection = progress_event(reused, event_id="progress:changed-id")
    old = offer(arbiter, reused, reused_projection)
    assert old.reason == "SOURCE_SEQUENCE_CONFLICT"
    assert arbiter.snapshot().accepted_events == 1


def test_task_core_source_causation_is_not_a_sequence_predecessor() -> None:
    arbiter = ProgressNotificationArbiter()
    accepted = source_event(
        work_kind="task",
        work_id="task-causation",
        seq=0,
        causation_id="command:create-task",
    )
    first = offer(arbiter, accepted, progress_event(accepted))
    assert first.disposition is NotificationDisposition.DISPLAY_NOW
    running = source_event(
        work_kind="task",
        work_id="task-causation",
        seq=1,
        state="running",
        causation_id="executor:attempt-started",
    )
    second = offer(arbiter, running, progress_event(running))
    assert second.disposition is NotificationDisposition.DISPLAY_NOW
    assert second.progress.source.event_id == running.event_id
    assert arbiter.snapshot().accepted_events == 2


def test_progress_envelope_causation_must_still_match_exact_source() -> None:
    source = source_event(causation_id="command:external-parent")
    projected = progress_event(source)
    forged = replace(projected, causation_id="source:foreign")
    arbiter = ProgressNotificationArbiter()
    result = offer(
        arbiter,
        source,
        forged,
        expected=binding(source, projected),
    )
    assert result.disposition is NotificationDisposition.REJECTED
    assert result.reason == "PROGRESS_SOURCE_MISMATCH"
    assert arbiter.snapshot().accepted_events == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "scope",
        "correlation",
        "source_producer",
        "progress_producer",
        "source_ref",
        "adapter",
    ],
)
def test_wrong_scope_correlation_or_provenance_is_rejected_without_projection(
    mutation: str,
) -> None:
    arbiter = ProgressNotificationArbiter()
    source = source_event()
    projected = progress_event(source)
    expected = binding(source, projected)
    if mutation == "scope":
        expected = replace(expected, scope=scope(session_id="foreign"))
    elif mutation == "correlation":
        expected = replace(expected, correlation_id="foreign")
    elif mutation == "source_producer":
        expected = replace(
            expected,
            source_producer=ProducerRef("test.harness", "foreign", "harness"),
        )
    elif mutation == "progress_producer":
        expected = replace(
            expected,
            progress_producer=ProducerRef("test.progress", "foreign", "adapter"),
        )
    elif mutation == "source_ref":
        expected = replace(
            expected, source_work_ref=IdentityRef(IdentityKind.ROUND, "foreign")
        )
    else:
        expected = replace(expected, progress_adapter="foreign.adapter")
    result = offer(arbiter, source, projected, expected=expected)
    assert result.disposition is NotificationDisposition.REJECTED
    snapshot = arbiter.snapshot()
    assert snapshot.accepted_events == 0
    assert snapshot.pending_notifications == 0


def test_request_asserted_scope_and_unknown_foreground_never_authorize_speech() -> None:
    request_scope = scope(assurance=Assurance.REQUEST_ASSERTED)
    source = source_event(current_scope=request_scope)
    projected = progress_event(source, speakability="attention_requested")
    arbiter = ProgressNotificationArbiter()
    unauthenticated = offer(arbiter, source, projected)
    assert unauthenticated.disposition is NotificationDisposition.REJECTED
    assert unauthenticated.reason == "UNAUTHENTICATED_PROGRESS_SCOPE"
    assert arbiter.snapshot().pending_notifications == 0

    authenticated = source_event()
    eligible = progress_event(authenticated, speakability="attention_requested")
    unknown = offer(arbiter, authenticated, eligible, foreground=unknown_foreground())
    assert unknown.disposition is NotificationDisposition.DEFERRED
    assert unknown.speech is SpeechDisposition.NOT_A_CANDIDATE


def test_source_state_outcome_and_terminal_irreversibility_fail_closed() -> None:
    arbiter = ProgressNotificationArbiter()
    accepted = source_event()
    assert offer(arbiter, accepted, progress_event(accepted)).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    terminal = source_event(seq=1, state="terminal", outcome="completed")
    terminal_projection = progress_event(terminal)
    assert offer(arbiter, terminal, terminal_projection).state.value == "terminal"

    after_terminal = source_event(seq=2, state="running")
    rejected = offer(arbiter, after_terminal, progress_event(after_terminal))
    assert rejected.reason == "WORK_EVENT_AFTER_TERMINAL"
    assert arbiter.snapshot().accepted_events == 2

    missing_source = source_event(
        work_id="round-missing", state="terminal", outcome="completed"
    )
    invalid_wire = progress_event(missing_source).to_dict()
    invalid_wire["payload"]["outcome"] = None
    with pytest.raises(ContractViolation) as missing_outcome:
        EventEnvelope.from_dict(invalid_wire)
    assert missing_outcome.value.reason == "TERMINAL_OUTCOME_REQUIRED"


def test_source_state_mismatch_rejects_without_inference() -> None:
    source = source_event()
    projected = progress_event(source, state="running")
    arbiter = ProgressNotificationArbiter()
    result = offer(arbiter, source, projected)
    assert result.reason == "PROGRESS_SOURCE_STATE_MISMATCH"
    assert arbiter.snapshot().tracked_work_streams == 0


def test_non_v2_envelope_instance_is_rejected_before_sequence_state() -> None:
    source = source_event()
    projected = progress_event(source)
    forged = replace(projected, contract_version="live-voice.contract.v1")
    arbiter = ProgressNotificationArbiter()
    result = offer(
        arbiter,
        source,
        forged,
        expected=binding(source, projected),
    )
    assert result.disposition is NotificationDisposition.REJECTED
    assert result.reason == "UNSUPPORTED_CONTRACT_VERSION"
    assert arbiter.snapshot().tracked_work_streams == 0


def test_pending_capacity_is_explicit_and_retry_does_not_skip_sequence() -> None:
    arbiter = ProgressNotificationArbiter(pending_capacity=1)
    first_source = source_event(work_id="round-1")
    first_progress = progress_event(first_source)
    assert offer(arbiter, first_source, first_progress).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )

    second_source = source_event(work_id="round-2")
    second_progress = progress_event(second_source)
    full = offer(arbiter, second_source, second_progress)
    assert full.disposition is NotificationDisposition.BACKPRESSURE
    assert full.progress is None
    assert full.reason == "PENDING_NOTIFICATION_CAPACITY_EXHAUSTED"
    snapshot = arbiter.snapshot()
    assert snapshot.tracked_work_streams == 1
    assert snapshot.accepted_events == 1
    assert snapshot.backpressure_events == 1

    exact_while_full = offer(arbiter, second_source, second_progress)
    assert exact_while_full.disposition is NotificationDisposition.BACKPRESSURE
    assert exact_while_full.reason == "PENDING_NOTIFICATION_CAPACITY_EXHAUSTED"
    mutated_second = progress_event(
        second_source,
        event_id=second_progress.event_id,
        urgency="urgent",
        speakability="attention_requested",
    )
    mutated_retry = offer(arbiter, second_source, mutated_second)
    assert mutated_retry.reason == "PROGRESS_EVENT_ID_CONFLICT"
    assert mutated_retry.disposition is NotificationDisposition.REJECTED
    assert mutated_retry.progress is None
    assert mutated_retry.speech is SpeechDisposition.NOT_A_CANDIDATE

    assert arbiter.acknowledge(
        first_progress.scope,
        first_progress.stream_ref,
        first_progress.event_id,
    )
    retried = offer(arbiter, second_source, second_progress)
    assert retried.disposition is NotificationDisposition.DISPLAY_NOW
    assert retried.projection_seq == 0
    final = arbiter.snapshot()
    assert final.tracked_work_streams == 2
    assert final.accepted_events == 2
    assert final.backpressure_events == 2
    assert final.rejected_events == 1
    assert final.pending_notifications == 1


def test_terminal_ack_releases_stream_capacity_and_keeps_replay_fence() -> None:
    """A9: terminal+ACK releases heavy stream state, not replay authority."""

    arbiter = ProgressNotificationArbiter(
        pending_capacity=1, stream_capacity=1, events_per_stream=2
    )
    first_source = source_event(work_id="round-terminal-1")
    first_progress = progress_event(first_source)
    assert offer(arbiter, first_source, first_progress).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    assert arbiter.acknowledge(
        first_progress.scope, first_progress.stream_ref, first_progress.event_id
    )
    after_nonterminal_ack = arbiter.snapshot()
    assert after_nonterminal_ack.tracked_work_streams == 1
    assert after_nonterminal_ack.tracked_source_streams == 1
    assert after_nonterminal_ack.tracked_progress_streams == 1

    terminal_source = source_event(
        work_id="round-terminal-1", seq=1, state="terminal", outcome="completed"
    )
    terminal_progress = progress_event(terminal_source)
    assert offer(arbiter, terminal_source, terminal_progress).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    assert arbiter.acknowledge(
        terminal_progress.scope,
        terminal_progress.stream_ref,
        terminal_progress.event_id,
    )

    released = arbiter.snapshot()
    assert released.tracked_work_streams == 0
    assert released.tracked_source_streams == 0
    assert released.tracked_progress_streams == 0
    assert released.retained_source_events == 0
    assert released.retained_progress_events == 0
    assert released.pending_notifications == 0
    assert released.terminal_work_streams == 0
    assert arbiter._decisions == {}

    replay = offer(arbiter, first_source, first_progress)
    assert replay.disposition is NotificationDisposition.REJECTED
    assert replay.progress is None
    after_replay = arbiter.snapshot()
    assert after_replay.tracked_work_streams == 0
    assert after_replay.tracked_source_streams == 0
    assert after_replay.tracked_progress_streams == 0
    assert after_replay.retained_source_events == 0
    assert after_replay.retained_progress_events == 0
    assert after_replay.pending_notifications == 0
    assert after_replay.accepted_events == released.accepted_events
    assert arbiter._decisions == {}

    second_source = source_event(work_id="round-terminal-2")
    second_progress = progress_event(second_source)
    second = offer(arbiter, second_source, second_progress)
    assert second.disposition is NotificationDisposition.DISPLAY_NOW
    assert arbiter.snapshot().tracked_work_streams == 1
    assert arbiter.snapshot().pending_notifications == 1


def test_terminal_ack_retires_current_attempt_but_newer_epoch_can_reopen() -> None:
    """A9 review: fresh IDs cannot revive the retired current Attempt."""

    arbiter = ProgressNotificationArbiter()
    work_id = "task-terminal-epoch"
    boundary_b, source_b, progress_b, binding_b = retry_epoch(
        work_id=work_id,
        attempt_id="attempt-b",
        retry_of_attempt_id="attempt-a",
        attempt_number=2,
        seq=5,
    )
    baseline_b = arbiter_module._mint_verified_attempt_epoch_baseline(
        boundary_b, binding_b
    )
    arbiter._begin_attempt_epoch(baseline_b)
    assert offer(arbiter, source_b, progress_b, expected=binding_b).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    assert arbiter.acknowledge(
        progress_b.scope, progress_b.stream_ref, progress_b.event_id
    )

    terminal_b = task_attempt_source_variant(
        source_b,
        event_id="task-event:terminal-epoch:b:terminal",
        event_type="task.terminal",
        seq=6,
        state="terminal",
        outcome="completed",
    )
    terminal_progress_b = progress_event(terminal_b)
    terminal_binding_b = binding(terminal_b, terminal_progress_b)
    assert offer(
        arbiter,
        terminal_b,
        terminal_progress_b,
        expected=terminal_binding_b,
    ).disposition is NotificationDisposition.DISPLAY_NOW
    assert arbiter.acknowledge(
        terminal_progress_b.scope,
        terminal_progress_b.stream_ref,
        terminal_progress_b.event_id,
    )
    released = arbiter.snapshot()
    assert released.tracked_work_streams == 0
    assert released.retained_source_events == 0
    assert released.pending_notifications == 0

    fresh_old_source = task_attempt_source_variant(
        source_b,
        event_id="task-event:terminal-epoch:b:fresh",
        event_type="task.accepted",
        seq=0,
        state="accepted",
    )
    fresh_old_progress = progress_event(
        fresh_old_source,
        event_id="progress:terminal-epoch:b:fresh",
    )
    stale = offer(
        arbiter,
        fresh_old_source,
        fresh_old_progress,
        expected=binding(fresh_old_source, fresh_old_progress),
    )
    assert stale.disposition is NotificationDisposition.REJECTED
    after_stale = arbiter.snapshot()
    assert after_stale.tracked_work_streams == released.tracked_work_streams
    assert after_stale.retained_source_events == released.retained_source_events
    assert after_stale.retained_progress_events == released.retained_progress_events
    assert after_stale.pending_notifications == released.pending_notifications
    assert after_stale.accepted_events == released.accepted_events
    with pytest.raises(ProgressNotificationArbiterViolation) as repeated_epoch:
        arbiter._begin_attempt_epoch(baseline_b)
    assert repeated_epoch.value.reason == "STALE_ATTEMPT_EPOCH"

    boundary_c, source_c, progress_c, binding_c = retry_epoch(
        work_id=work_id,
        attempt_id="attempt-c",
        retry_of_attempt_id="attempt-b",
        attempt_number=3,
        seq=9,
    )
    arbiter._begin_attempt_epoch(
        arbiter_module._mint_verified_attempt_epoch_baseline(boundary_c, binding_c)
    )
    assert offer(arbiter, source_c, progress_c, expected=binding_c).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )

    def retained_effect_state() -> tuple[object, ...]:
        current = arbiter.snapshot()
        return (
            current.tracked_work_streams,
            current.tracked_source_streams,
            current.tracked_progress_streams,
            current.retained_source_events,
            current.retained_progress_events,
            current.pending_notifications,
            current.accepted_events,
            current.coalesced_events,
            current.duplicate_events,
            current.backpressure_events,
            current.no_projection_advances,
            dict(arbiter._decisions),
        )

    active_baseline = retained_effect_state()
    old_source_id = task_attempt_source_variant(
        source_c,
        event_id=source_b.event_id,
        event_type="task.running",
        seq=10,
        state="running",
    )
    fresh_progress_id = progress_event(
        old_source_id,
        event_id="progress:terminal-epoch:c:fresh-for-old-source",
    )
    source_replay = offer(
        arbiter,
        old_source_id,
        fresh_progress_id,
        expected=binding(old_source_id, fresh_progress_id),
    )
    assert source_replay.disposition is NotificationDisposition.REJECTED
    assert retained_effect_state() == active_baseline

    fresh_source_id = task_attempt_source_variant(
        source_c,
        event_id="task-event:terminal-epoch:c:fresh-for-old-progress",
        event_type="task.running",
        seq=10,
        state="running",
    )
    old_progress_id = progress_event(
        fresh_source_id,
        event_id=progress_b.event_id,
    )
    progress_replay = offer(
        arbiter,
        fresh_source_id,
        old_progress_id,
        expected=binding(fresh_source_id, old_progress_id),
    )
    assert progress_replay.disposition is NotificationDisposition.REJECTED
    assert retained_effect_state() == active_baseline


def test_retired_attempt_epochs_share_capacity_and_keep_old_history_fenced() -> None:
    """A9 review: retired Attempt ownership is bounded without plain LRU."""

    arbiter = ProgressNotificationArbiter(
        pending_capacity=1,
        stream_capacity=1,
        events_per_stream=2,
    )
    first_baseline = None
    first_source: EventEnvelope | None = None
    first_progress: EventEnvelope | None = None
    latest_work_id = ""
    latest_attempt_id = ""
    for index in range(12):
        latest_work_id = f"task-retired-epoch-{index}"
        latest_attempt_id = f"attempt-{index}-b"
        boundary, source, progress, expected = retry_epoch(
            work_id=latest_work_id,
            attempt_id=latest_attempt_id,
            retry_of_attempt_id=f"attempt-{index}-a",
            attempt_number=2,
            seq=5,
        )
        baseline = arbiter_module._mint_verified_attempt_epoch_baseline(
            boundary, expected
        )
        if first_baseline is None:
            first_baseline = baseline
            first_source = source
            first_progress = progress
        arbiter._begin_attempt_epoch(baseline)
        assert offer(arbiter, source, progress, expected=expected).disposition is (
            NotificationDisposition.DISPLAY_NOW
        )
        assert arbiter.acknowledge(
            progress.scope, progress.stream_ref, progress.event_id
        )
        terminal = task_attempt_source_variant(
            source,
            event_id=f"task-event:{latest_work_id}:terminal",
            event_type="task.terminal",
            seq=6,
            state="terminal",
            outcome="completed",
        )
        terminal_progress = progress_event(terminal)
        assert offer(
            arbiter,
            terminal,
            terminal_progress,
            expected=binding(terminal, terminal_progress),
        ).disposition is NotificationDisposition.DISPLAY_NOW
        assert arbiter.acknowledge(
            terminal_progress.scope,
            terminal_progress.stream_ref,
            terminal_progress.event_id,
        )
        assert arbiter.snapshot().tracked_work_streams == 0

    assert arbiter._attempt_epochs == {}
    assert len(arbiter._retired_attempt_epochs) <= arbiter._observation_capacity
    assert len(arbiter._retired_identities) <= arbiter._retired_identity_capacity
    assert len(arbiter._retired_identity_set) <= arbiter._retired_identity_capacity
    assert first_source is not None
    assert first_progress is not None
    first_source_digest = arbiter._retired_event_digest(
        "source", first_source.event_id
    )
    assert first_source_digest not in arbiter._retired_identities
    assert first_source_digest not in arbiter._retired_identity_set
    assert arbiter._retired_identity_known(first_source_digest)
    before_replay = arbiter.snapshot()
    replay = offer(arbiter, first_source, first_progress)
    assert replay.disposition is NotificationDisposition.REJECTED
    after_replay = arbiter.snapshot()
    assert after_replay.tracked_work_streams == before_replay.tracked_work_streams
    assert after_replay.retained_source_events == before_replay.retained_source_events
    assert after_replay.retained_progress_events == (
        before_replay.retained_progress_events
    )
    assert after_replay.pending_notifications == before_replay.pending_notifications
    assert after_replay.accepted_events == before_replay.accepted_events
    assert first_baseline is not None
    with pytest.raises(ProgressNotificationArbiterViolation) as fenced_history:
        arbiter._begin_attempt_epoch(first_baseline)
    assert fenced_history.value.reason == "STALE_ATTEMPT_EPOCH"

    boundary_c, source_c, progress_c, binding_c = retry_epoch(
        work_id=latest_work_id,
        attempt_id=f"{latest_attempt_id}-next",
        retry_of_attempt_id=latest_attempt_id,
        attempt_number=3,
        seq=9,
    )
    arbiter._begin_attempt_epoch(
        arbiter_module._mint_verified_attempt_epoch_baseline(boundary_c, binding_c)
    )
    assert offer(arbiter, source_c, progress_c, expected=binding_c).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )


def test_stream_and_event_ledger_exhaustion_are_observable_without_eviction() -> None:
    stream_limited = ProgressNotificationArbiter(pending_capacity=2, stream_capacity=1)
    first = source_event(work_id="round-1")
    assert offer(stream_limited, first, progress_event(first)).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    second = source_event(work_id="round-2")
    stream_full = offer(stream_limited, second, progress_event(second))
    assert stream_full.disposition is NotificationDisposition.BACKPRESSURE
    assert stream_full.reason == "SOURCE_STREAM_CAPACITY_EXHAUSTED"

    event_limited = ProgressNotificationArbiter(events_per_stream=1)
    accepted = source_event()
    assert offer(event_limited, accepted, progress_event(accepted)).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )
    running = source_event(seq=1, state="running")
    event_full = offer(event_limited, running, progress_event(running))
    assert event_full.disposition is NotificationDisposition.BACKPRESSURE
    assert event_full.reason == "SOURCE_EVENT_CAPACITY_EXHAUSTED"
    assert event_limited.snapshot().accepted_events == 1


def test_observation_capacity_bounds_new_ids_and_exact_retry() -> None:
    arbiter = ProgressNotificationArbiter(
        pending_capacity=1,
        stream_capacity=1,
        events_per_stream=2,
    )
    gap_source = source_event(
        seq=1,
        state="running",
        event_id="source:observation-gap",
    )
    gap_progress = progress_event(
        gap_source,
        event_id="progress:observation-gap",
        speakability="eligible",
    )
    gap = offer(arbiter, gap_source, gap_progress)
    assert gap.reason == "SOURCE_SEQUENCE_GAP"

    predecessor = source_event()
    predecessor_progress = progress_event(predecessor)
    assert offer(arbiter, predecessor, predecessor_progress).disposition is (
        NotificationDisposition.DISPLAY_NOW
    )

    lifecycle_source = source_event(
        seq=1,
        state="accepted",
        event_id="source:observation-lifecycle",
    )
    lifecycle_progress = progress_event(
        lifecycle_source,
        event_id="progress:observation-lifecycle",
    )
    lifecycle = offer(arbiter, lifecycle_source, lifecycle_progress)
    assert lifecycle.reason == "WORK_ACCEPTED_REPEATED"

    at_limit = arbiter.snapshot()
    assert at_limit.retained_source_events == 3
    assert at_limit.retained_progress_events == 3
    assert at_limit.tracked_source_streams == 1
    assert at_limit.tracked_progress_streams == 1
    assert at_limit.tracked_work_streams == 1
    assert at_limit.accepted_events == 1
    assert at_limit.pending_notifications == 1

    overflow_source = source_event(
        seq=1,
        state="running",
        event_id="source:observation-overflow",
    )
    overflow_progress = progress_event(
        overflow_source,
        event_id="progress:observation-overflow",
        speakability="attention_requested",
    )
    overflow = offer(arbiter, overflow_source, overflow_progress)
    assert overflow.disposition is NotificationDisposition.BACKPRESSURE
    assert overflow.reason == "SOURCE_OBSERVATION_CAPACITY_EXHAUSTED"
    assert overflow.progress is None
    assert overflow.speech is SpeechDisposition.NOT_A_CANDIDATE
    after_overflow = arbiter.snapshot()
    assert after_overflow.retained_source_events == 3
    assert after_overflow.retained_progress_events == 3
    assert after_overflow.accepted_events == 1
    assert after_overflow.pending_notifications == 1

    overflow_repeat = offer(arbiter, overflow_source, overflow_progress)
    assert overflow_repeat.reason == "SOURCE_OBSERVATION_CAPACITY_EXHAUSTED"
    assert overflow_repeat.disposition is NotificationDisposition.BACKPRESSURE
    assert overflow_repeat.speech is SpeechDisposition.NOT_A_CANDIDATE
    mutated_unobserved = progress_event(
        overflow_source,
        event_id=overflow_progress.event_id,
        urgency="urgent",
    )
    unobserved_mutated_retry = offer(arbiter, overflow_source, mutated_unobserved)
    assert unobserved_mutated_retry.reason == "SOURCE_OBSERVATION_CAPACITY_EXHAUSTED"
    assert unobserved_mutated_retry.disposition is (
        NotificationDisposition.BACKPRESSURE
    )
    assert unobserved_mutated_retry.speech is SpeechDisposition.NOT_A_CANDIDATE
    before_recovery = arbiter.snapshot()
    assert before_recovery.retained_source_events == 3
    assert before_recovery.retained_progress_events == 3
    assert before_recovery.accepted_events == 1
    assert before_recovery.pending_notifications == 1

    lifecycle_exact = offer(arbiter, lifecycle_source, lifecycle_progress)
    assert lifecycle_exact.reason == "WORK_ACCEPTED_REPEATED"
    mutated_lifecycle = progress_event(
        lifecycle_source,
        event_id=lifecycle_progress.event_id,
        urgency="urgent",
    )
    lifecycle_conflict = offer(arbiter, lifecycle_source, mutated_lifecycle)
    assert lifecycle_conflict.reason == "PROGRESS_EVENT_ID_CONFLICT"
    assert lifecycle_conflict.speech is SpeechDisposition.NOT_A_CANDIDATE

    recovered_gap = offer(arbiter, gap_source, gap_progress)
    assert recovered_gap.disposition is NotificationDisposition.DISPLAY_NOW
    assert recovered_gap.projection_seq == 1
    assert recovered_gap.speech is SpeechDisposition.SPEAK_WHEN_SAFE_CANDIDATE

    overflow_exact = offer(arbiter, overflow_source, overflow_progress)
    assert overflow_exact.reason == "SOURCE_OBSERVATION_CAPACITY_EXHAUSTED"
    assert overflow_exact.disposition is NotificationDisposition.BACKPRESSURE
    assert overflow_exact.speech is SpeechDisposition.NOT_A_CANDIDATE
    mutated_overflow = progress_event(
        overflow_source,
        event_id=overflow_progress.event_id,
        urgency="urgent",
    )
    overflow_mutated_retry = offer(arbiter, overflow_source, mutated_overflow)
    assert overflow_mutated_retry.reason == "SOURCE_OBSERVATION_CAPACITY_EXHAUSTED"
    assert overflow_mutated_retry.disposition is NotificationDisposition.BACKPRESSURE
    assert overflow_mutated_retry.speech is SpeechDisposition.NOT_A_CANDIDATE

    final = arbiter.snapshot()
    assert final.retained_source_events == 3
    assert final.retained_progress_events == 3
    assert final.accepted_events == 2
    assert final.pending_notifications == 1
    assert final.coalesced_events == 1
    assert final.duplicate_events == 0
    assert final.rejected_events == 4
    assert final.backpressure_events == 5


def test_consumer_failure_keeps_exact_candidate_until_successful_ack() -> None:
    arbiter = ProgressNotificationArbiter()
    source = source_event()
    projected = progress_event(source, speakability="eligible")
    offered = offer(arbiter, source, projected)
    assert offered.disposition is NotificationDisposition.DISPLAY_NOW

    def failing_consumer(_decision) -> None:
        raise RuntimeError("observer unavailable")

    with pytest.raises(RuntimeError):
        failing_consumer(offered)
    assert arbiter.snapshot().pending_notifications == 1
    retry = arbiter.drain(scope(), safe_foreground())
    assert len(retry) == 1
    assert retry[0].event_id == offered.event_id
    assert retry[0].progress is offered.progress
    assert (
        arbiter.acknowledge(retry[0].scope, retry[0].work_ref, retry[0].event_id)
        is True
    )
    assert arbiter.snapshot().pending_notifications == 0


def test_decisions_are_immutable_and_have_no_authority_effect_surface() -> None:
    arbiter = ProgressNotificationArbiter()
    source = source_event()
    decision = offer(arbiter, source, progress_event(source))
    assert decision.progress is not None
    with pytest.raises(FrozenInstanceError):
        decision.reason = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        decision.progress.state = "running"  # type: ignore[misc]
    assert not hasattr(decision, "speak")
    assert not hasattr(decision, "cancel")
    assert not hasattr(decision, "mutate")


def test_invalid_drain_and_ack_inputs_fail_closed_without_consuming_pending() -> None:
    arbiter = ProgressNotificationArbiter()
    source = source_event()
    projected = progress_event(source)
    offer(arbiter, source, projected)
    invalid_snapshot = ForegroundSnapshot(  # type: ignore[arg-type]
        interaction="safe",
        response=ForegroundFact.SAFE,
        presentation=ForegroundFact.SAFE,
    )
    invalid = arbiter.drain(scope(), invalid_snapshot)
    assert invalid[0].disposition is NotificationDisposition.REJECTED
    assert invalid[0].reason == "INVALID_FOREGROUND_SNAPSHOT"
    invalid_limit = arbiter.drain(scope(), safe_foreground(), max_items=0)
    assert invalid_limit[0].reason == "INVALID_DRAIN_LIMIT"
    invalid_work = arbiter.drain(scope(), safe_foreground(), work_ref=object())
    assert invalid_work[0].reason == "INVALID_PROGRESS_BINDING"
    assert arbiter.drain(
        scope(),
        safe_foreground(),
        work_ref=IdentityRef(IdentityKind.ROUND, "foreign-round"),
    ) == ()
    assert (
        arbiter.acknowledge(projected.scope, projected.stream_ref, "foreign-event")
        is False
    )
    assert arbiter.snapshot().pending_notifications == 1
