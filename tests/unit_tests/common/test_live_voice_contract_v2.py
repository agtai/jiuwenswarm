# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Shared critical-kernel scenarios for ``live-voice.contract.v2``."""

from __future__ import annotations

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
    CancelScope,
    CapabilityDescriptor,
    CapabilityRegistry,
    CommandEnvelope,
    CommandResultLedger,
    ConnectionEpochRef,
    ContextRef,
    ContractViolation,
    ErrorCode,
    EventApplyStatus,
    EventEnvelope,
    EventSequenceTracker,
    IdentityKind,
    IdentityRecord,
    IdentityRef,
    IdentityRegistry,
    InputCommitState,
    KnownFact,
    Knowledge,
    LifecycleKind,
    MAX_SAFE_INTEGER,
    QueryEnvelope,
    ResponseFence,
    ResponseRef,
    ResultEnvelope,
    ScopeRef,
    SideEffectTarget,
    TerminalOutcome,
    TurnCommit,
    TurnCommitLedger,
    WorkProgressEventV2,
    canonical_json,
    canonical_json_bytes,
    classify_contract,
    default_barge_in_scopes,
    dispatch_cancel,
    dispatch_committed_input,
    parse_v2_envelope,
    validate_transition,
)


FIXTURES = Path(__file__).parents[2] / "fixtures" / "live_voice_contract_v2"


def _load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _registry(fixture: dict[str, object]) -> IdentityRegistry:
    registry = IdentityRegistry()
    scope = ScopeRef.from_dict(fixture["scope"])
    for raw in fixture["identities"]:  # type: ignore[union-attr]
        record = raw  # type: ignore[assignment]
        registry.register(
            IdentityRecord(
                ref=IdentityRef.from_dict(record["ref"]),
                scope=scope,
                parents=tuple(
                    IdentityRef.from_dict(parent) for parent in record["parents"]
                ),
                connection_epoch_ref=(
                    None
                    if record.get("connection_epoch_ref") is None
                    else ConnectionEpochRef.from_dict(record["connection_epoch_ref"])
                ),
            )
        )
    return registry


def _event(
    fixture: dict[str, object],
    *,
    event_id: str,
    seq: int,
    causation_id: str | None = None,
    producer_instance: str = "task-core-1",
    event_type: str = "task.accepted",
    stream_id: str = "task-1",
) -> EventEnvelope:
    raw = copy.deepcopy(fixture["event"])
    raw["event_id"] = event_id
    raw["seq"] = seq
    raw["causation_id"] = causation_id
    raw["producer"]["instance_id"] = producer_instance
    raw["event_type"] = event_type
    raw["stream_ref"]["id"] = stream_id
    raw["payload"] = {"state": event_type.split(".", 1)[1]}
    return EventEnvelope.from_dict(raw)


def test_shared_valid_fixture_round_trips_and_is_immutable() -> None:
    fixture = _load("critical_kernel.valid.json")
    registry = _registry(fixture)

    command = CommandEnvelope.from_dict(fixture["command"], identities=registry)
    query = QueryEnvelope.from_dict(fixture["query"], identities=registry)
    result = ResultEnvelope.from_dict(fixture["result"], owner=command)
    event = EventEnvelope.from_dict(fixture["event"], identities=registry)
    commit = TurnCommit.from_dict(fixture["turn_commit"], identities=registry)
    capability = CapabilityDescriptor.from_dict(fixture["capability"])

    assert parse_v2_envelope(command.to_dict()).to_dict() == command.to_dict()
    assert parse_v2_envelope(query.to_dict()).to_dict() == query.to_dict()
    assert parse_v2_envelope(result.to_dict()).to_dict() == result.to_dict()
    assert parse_v2_envelope(event.to_dict()).to_dict() == event.to_dict()
    assert commit.to_dict() == fixture["turn_commit"]
    assert capability.to_dict() == fixture["capability"]
    assert canonical_json_bytes({"text": "茅"}) == canonical_json(
        {"text": "茅"}
    ).encode("utf-8")

    fixture["command"]["payload"]["name"] = "mutated"
    returned = command.payload
    returned["name"] = "also-mutated"
    assert command.payload["name"] == "check inventory"


def test_shared_canonical_json_cases() -> None:
    fixture = _load("critical_kernel.valid.json")
    for case in fixture["canonical_cases"]:
        assert canonical_json(case["input"]) == case["canonical"]


def test_context_ref_wire_shape_round_trips_and_scope_mismatch_fails_closed() -> None:
    fixture = _load("critical_kernel.valid.json")
    progress_fixture = _load("work_progress.v2.json")
    refs = progress_fixture["context_refs"]
    parsed = [ContextRef.from_dict(item) for item in refs]
    assert [item.to_dict() for item in parsed] == refs
    assert parsed[0].revision.value == "sha256:abc"
    assert parsed[1].revision.value == "snapshot-2"
    assert parsed[2].revision.value is None

    command_raw = copy.deepcopy(fixture["command"])
    command_raw["context_refs"] = copy.deepcopy(refs)
    command = CommandEnvelope.from_dict(command_raw)
    assert command.to_dict() == command_raw
    assert len(command.context_refs) == 3

    query_raw = copy.deepcopy(fixture["query"])
    query_raw["context_refs"] = copy.deepcopy(refs)
    assert QueryEnvelope.from_dict(query_raw).to_dict() == query_raw

    commit_raw = copy.deepcopy(fixture["turn_commit"])
    commit_raw["context_refs"] = copy.deepcopy(refs)
    assert TurnCommit.from_dict(commit_raw).to_dict() == commit_raw

    wrong_scope = copy.deepcopy(command_raw)
    wrong_scope["context_refs"][0]["scope"]["session_id"] = "other-session"
    with pytest.raises(ContractViolation) as mismatch:
        CommandEnvelope.from_dict(wrong_scope)
    assert mismatch.value.reason == "CONTEXT_SCOPE_MISMATCH"
    assert mismatch.value.code is ErrorCode.PERMISSION_DENIED

    secret_field = copy.deepcopy(refs[0])
    secret_field["content"] = "must-not-cross-the-wire"
    with pytest.raises(ContractViolation) as secret:
        ContextRef.from_dict(secret_field)
    assert secret.value.reason == "UNKNOWN_FIELD"


def test_work_progress_v2_round_trip_preserves_known_unknown_and_sequence_domains() -> (
    None
):
    fixture = _load("work_progress.v2.json")
    tracker = EventSequenceTracker()
    sources = [EventEnvelope.from_dict(item) for item in fixture["source_events"]]
    progress_events = [
        EventEnvelope.from_dict(item) for item in fixture["progress_events"]
    ]

    accepted = WorkProgressEventV2.from_dict(
        progress_events[0].payload,
        scope=progress_events[0].scope,
    )
    running = WorkProgressEventV2.from_dict(
        progress_events[1].payload,
        scope=progress_events[1].scope,
    )
    terminal = WorkProgressEventV2.from_dict(
        progress_events[2].payload,
        scope=progress_events[2].scope,
    )
    assert accepted.to_dict() == fixture["progress_events"][0]["payload"]
    assert accepted.artifact_refs.knowledge is Knowledge.UNKNOWN
    assert running.artifact_refs.knowledge is Knowledge.UNKNOWN
    assert terminal.outcome is TerminalOutcome.COMPLETED
    assert progress_events[1].seq == 0 and running.seq == 1

    known_empty = copy.deepcopy(progress_events[0].payload)
    known_empty["artifact_refs"] = {"knowledge": "known", "value": []}
    parsed_known_empty = WorkProgressEventV2.from_dict(known_empty)
    assert parsed_known_empty.artifact_refs.knowledge is Knowledge.KNOWN
    assert parsed_known_empty.artifact_refs.value == ()

    maximum = copy.deepcopy(progress_events[0].payload)
    maximum["seq"] = MAX_SAFE_INTEGER
    assert WorkProgressEventV2.from_dict(maximum).seq == MAX_SAFE_INTEGER

    for source in sources:
        assert tracker.accept(source).status is EventApplyStatus.APPLIED

    future_raw = copy.deepcopy(fixture["progress_events"][2])
    future_raw["producer"]["instance_id"] = "bridge-3"
    future_raw["seq"] = 0
    future = EventEnvelope.from_dict(future_raw)
    future_result = tracker.accept(future)
    assert future_result.status is EventApplyStatus.QUARANTINED_PROJECTION
    assert future_result.error is not None
    assert future_result.error.reason == "PROGRESS_SEQUENCE_GAP"

    first = tracker.accept(progress_events[0])
    assert first.status is EventApplyStatus.APPLIED
    second = tracker.accept(progress_events[1])
    assert second.status is EventApplyStatus.APPLIED
    assert second.applied_event_ids == ("progress-1", "progress-2")

    duplicate_source = copy.deepcopy(fixture["progress_events"][0])
    duplicate_source["event_id"] = "progress-overlap"
    duplicate_source["producer"]["instance_id"] = "bridge-overlap"
    duplicate_source["seq"] = 0
    duplicate_source["payload"]["seq"] = 3
    duplicate = tracker.accept(EventEnvelope.from_dict(duplicate_source))
    assert duplicate.status is EventApplyStatus.REJECTED_PROJECTION
    assert duplicate.error is not None
    assert duplicate.error.reason == "PROGRESS_SOURCE_ALREADY_PROJECTED"

    order_tracker = EventSequenceTracker()
    for source in sources:
        assert order_tracker.accept(source).status is EventApplyStatus.APPLIED
    reversed_progress = copy.deepcopy(fixture["progress_events"][2])
    reversed_progress["event_id"] = "progress-terminal-first"
    reversed_progress["producer"]["instance_id"] = "bridge-terminal-first"
    reversed_progress["seq"] = 0
    reversed_progress["payload"]["seq"] = 0
    reversed_result = order_tracker.accept(EventEnvelope.from_dict(reversed_progress))
    assert reversed_result.status is EventApplyStatus.REJECTED_PROJECTION
    assert reversed_result.error is not None
    assert reversed_result.error.reason == "PROGRESS_SOURCE_ORDER_MISMATCH"

    fabricated_detail = copy.deepcopy(fixture["progress_events"][0])
    fabricated_detail["event_id"] = "progress-fabricated-detail"
    fabricated_detail["producer"]["instance_id"] = "bridge-fabricated-detail"
    fabricated_detail["seq"] = 0
    fabricated_detail["payload"]["summary"] = {
        "knowledge": "known",
        "value": "guessed",
    }
    detail_result = order_tracker.accept(EventEnvelope.from_dict(fabricated_detail))
    assert detail_result.status is EventApplyStatus.REJECTED_PROJECTION
    assert detail_result.error is not None
    assert detail_result.error.reason == "PROGRESS_DETAIL_UNPROVEN"

    with pytest.raises(ContractViolation) as invalid_knowledge:
        KnownFact("unknown")  # type: ignore[arg-type]
    assert invalid_knowledge.value.reason == "INVALID_ENUM"


def test_work_progress_v2_rejects_false_authority_outcome_and_source_mapping() -> None:
    fixture = _load("work_progress.v2.json")
    raw = copy.deepcopy(fixture["progress_events"][0])
    raw["payload"]["source"]["authority"] = "executor"
    with pytest.raises(ContractViolation) as authority:
        EventEnvelope.from_dict(raw)
    assert authority.value.reason == "PROGRESS_SOURCE_AUTHORITY_MISMATCH"

    raw = copy.deepcopy(fixture["progress_events"][0])
    raw["payload"]["outcome"] = "completed"
    with pytest.raises(ContractViolation) as outcome:
        EventEnvelope.from_dict(raw)
    assert outcome.value.reason == "NON_TERMINAL_OUTCOME_FORBIDDEN"

    tracker = EventSequenceTracker()
    source = EventEnvelope.from_dict(fixture["source_events"][0])
    assert tracker.accept(source).status is EventApplyStatus.APPLIED
    false_progress = copy.deepcopy(fixture["progress_events"][0])
    false_progress["payload"]["state"] = "running"
    rejected = tracker.accept(EventEnvelope.from_dict(false_progress))
    assert rejected.status is EventApplyStatus.REJECTED_CAUSATION
    assert rejected.error is not None
    assert rejected.error.reason == "PROGRESS_SOURCE_MISMATCH"

    attempt_progress = copy.deepcopy(fixture["progress_events"][0])
    attempt_progress["event_id"] = "attempt-progress-0"
    attempt_progress["stream_ref"] = {"kind": "task", "id": "task-1"}
    attempt_progress["causation_id"] = "attempt-source-0"
    attempt_progress["payload"]["work_ref"] = {"kind": "task", "id": "task-1"}
    attempt_progress["payload"]["source"] = {
        "authority": "executor",
        "event_id": "attempt-source-0",
        "source_work_ref": {"kind": "attempt", "id": "attempt-1"},
        "adapter": "jiuwenswarm.executor",
    }
    with pytest.raises(ContractViolation) as unbound:
        EventEnvelope.from_dict(attempt_progress)
    assert unbound.value.reason == "PROGRESS_ATTEMPT_PARENT_UNVERIFIED"

    identities = IdentityRegistry()
    exact_scope = ScopeRef.from_dict(fixture["scope"])
    identities.register(
        IdentityRecord(IdentityRef(IdentityKind.TASK, "task-1"), exact_scope, ())
    )
    identities.register(
        IdentityRecord(
            IdentityRef(IdentityKind.ATTEMPT, "attempt-1"),
            exact_scope,
            (IdentityRef(IdentityKind.TASK, "task-1"),),
        )
    )
    parsed_attempt_progress = EventEnvelope.from_dict(
        attempt_progress, identities=identities
    )
    assert parsed_attempt_progress.stream_ref.id == "task-1"
    attempt_source = copy.deepcopy(fixture["source_events"][0])
    attempt_source["event_id"] = "attempt-source-0"
    attempt_source["event_type"] = "attempt.accepted"
    attempt_source["producer"] = {
        "component": "task.executor",
        "instance_id": "executor-1",
        "authority": "executor",
    }
    attempt_source["stream_ref"] = {"kind": "attempt", "id": "attempt-1"}
    attempt_tracker = EventSequenceTracker(identities)
    assert (
        attempt_tracker.accept(
            EventEnvelope.from_dict(attempt_source, identities=identities)
        ).status
        is EventApplyStatus.APPLIED
    )
    assert (
        attempt_tracker.accept(parsed_attempt_progress).status
        is EventApplyStatus.APPLIED
    )


def test_work_progress_mixed_authority_streams_do_not_invent_global_order() -> None:
    fixture = _load("work_progress.v2.json")
    exact_scope = ScopeRef.from_dict(fixture["scope"])
    identities = IdentityRegistry()
    task_ref = IdentityRef(IdentityKind.TASK, "task-mixed")
    identities.register(IdentityRecord(task_ref, exact_scope, ()))
    for attempt_id in ("attempt-mixed-1", "attempt-mixed-2"):
        identities.register(
            IdentityRecord(
                IdentityRef(IdentityKind.ATTEMPT, attempt_id),
                exact_scope,
                (task_ref,),
            )
        )

    def source_event(
        *, event_id: str, kind: str, ref_id: str, authority: str, instance: str
    ) -> EventEnvelope:
        raw = copy.deepcopy(fixture["source_events"][0])
        raw["event_id"] = event_id
        raw["event_type"] = f"{kind}.accepted"
        raw["producer"] = {
            "component": f"{kind}.runtime",
            "instance_id": instance,
            "authority": authority,
        }
        raw["stream_ref"] = {"kind": kind, "id": ref_id}
        return EventEnvelope.from_dict(raw, identities=identities)

    task_source = source_event(
        event_id="task-mixed-source",
        kind="task",
        ref_id=task_ref.id,
        authority="task_core",
        instance="task-core-1",
    )
    attempt_one = source_event(
        event_id="attempt-mixed-source-1",
        kind="attempt",
        ref_id="attempt-mixed-1",
        authority="executor",
        instance="executor-1",
    )
    attempt_two = source_event(
        event_id="attempt-mixed-source-2",
        kind="attempt",
        ref_id="attempt-mixed-2",
        authority="executor",
        instance="executor-2",
    )
    tracker = EventSequenceTracker(identities)
    for source in (task_source, attempt_one, attempt_two):
        assert tracker.accept(source).status is EventApplyStatus.APPLIED

    def projection(source: EventEnvelope, seq: int) -> EventEnvelope:
        raw = copy.deepcopy(fixture["progress_events"][0])
        raw["event_id"] = f"mixed-progress-{seq}"
        raw["producer"]["instance_id"] = f"mixed-bridge-{seq}"
        raw["stream_ref"] = task_ref.to_dict()
        raw["seq"] = 0
        raw["causation_id"] = source.event_id
        raw["payload"]["work_ref"] = task_ref.to_dict()
        raw["payload"]["source"] = {
            "authority": source.producer.authority,
            "event_id": source.event_id,
            "source_work_ref": source.stream_ref.to_dict(),
            "adapter": "mixed.authority.adapter",
        }
        raw["payload"]["seq"] = seq
        return EventEnvelope.from_dict(raw, identities=identities)

    for seq, source in enumerate((attempt_two, task_source, attempt_one)):
        assert (
            tracker.accept(projection(source, seq)).status is EventApplyStatus.APPLIED
        )


def test_work_progress_source_order_survives_producer_replacement() -> None:
    fixture = _load("work_progress.v2.json")

    def source(
        *, event_id: str, instance: str, event_type: str, cause: str | None
    ) -> EventEnvelope:
        raw = copy.deepcopy(fixture["source_events"][0])
        raw["event_id"] = event_id
        raw["producer"]["instance_id"] = instance
        raw["event_type"] = event_type
        raw["seq"] = 0
        raw["causation_id"] = cause
        raw["payload"] = {"state": event_type.split(".", 1)[1]}
        return EventEnvelope.from_dict(raw)

    accepted = source(
        event_id="round-replaced-accepted",
        instance="harness-before-restart",
        event_type="round.accepted",
        cause=None,
    )
    running = source(
        event_id="round-replaced-running",
        instance="harness-after-restart",
        event_type="round.running",
        cause=accepted.event_id,
    )
    tracker = EventSequenceTracker()
    assert tracker.accept(accepted).status is EventApplyStatus.APPLIED
    assert tracker.accept(running).status is EventApplyStatus.APPLIED

    def projection(
        source: EventEnvelope, *, event_id: str, instance: str, progress_seq: int
    ) -> EventEnvelope:
        raw = copy.deepcopy(fixture["progress_events"][0])
        raw["event_id"] = event_id
        raw["producer"]["instance_id"] = instance
        raw["seq"] = 0
        raw["causation_id"] = source.event_id
        raw["payload"]["source"] = {
            "authority": source.producer.authority,
            "event_id": source.event_id,
            "source_work_ref": source.stream_ref.to_dict(),
            "adapter": "restarted.task-core.adapter",
        }
        raw["payload"]["state"] = source.payload["state"]
        raw["payload"]["seq"] = progress_seq
        return EventEnvelope.from_dict(raw)

    reversed_running = projection(
        running,
        event_id="task-replaced-progress-running-early",
        instance="bridge-running-early",
        progress_seq=0,
    )
    reversed_result = tracker.accept(reversed_running)
    assert reversed_result.status is EventApplyStatus.REJECTED_PROJECTION
    assert reversed_result.error is not None
    assert reversed_result.error.reason == "PROGRESS_SOURCE_ORDER_MISMATCH"

    assert (
        tracker.accept(
            projection(
                accepted,
                event_id="task-replaced-progress-accepted",
                instance="bridge-accepted",
                progress_seq=0,
            )
        ).status
        is EventApplyStatus.APPLIED
    )
    assert (
        tracker.accept(
            projection(
                running,
                event_id="task-replaced-progress-running",
                instance="bridge-running",
                progress_seq=1,
            )
        ).status
        is EventApplyStatus.APPLIED
    )


@pytest.mark.parametrize(
    "scenario",
    _load("critical_kernel.invalid.json")["cases"],
    ids=lambda item: item["id"],
)
def test_shared_invalid_fixture_rejects_with_zero_effects(
    scenario: dict[str, object],
) -> None:
    fixture = _load("critical_kernel.valid.json")
    progress_fixture = _load("work_progress.v2.json")
    effects = 0

    def effect() -> None:
        nonlocal effects
        effects += 1

    with pytest.raises(ContractViolation) as raised:
        match scenario["change"]:
            case "context_refs_malformed":
                raw = copy.deepcopy(fixture["command"])
                raw["context_refs"] = [{"kind": "turn", "id": "turn-1"}]
                CommandEnvelope.from_dict(raw)
            case "wrong_scope_type":
                raw = copy.deepcopy(fixture["command"])
                raw["scope"] = []
                CommandEnvelope.from_dict(raw)
            case "wrong_authority":
                raw = copy.deepcopy(fixture["event"])
                raw["producer"]["authority"] = "adapter"
                EventEnvelope.from_dict(raw)
            case "success_with_error":
                raw = copy.deepcopy(fixture["result"])
                raw["error"] = {
                    "code": "INTERNAL",
                    "reason": "IMPOSSIBLE_SUCCESS",
                    "message": "success cannot also carry an error",
                    "retriable": False,
                    "correlation_id": None,
                    "details": {},
                }
                ResultEnvelope.from_dict(raw)
            case "unsafe_integer":
                raw = copy.deepcopy(fixture["command"])
                raw["payload"]["number"] = 9_007_199_254_740_992
                CommandEnvelope.from_dict(raw)
            case "unpaired_surrogate":
                raw = copy.deepcopy(fixture["command"])
                raw["payload"]["text"] = "\ud800"
                CommandEnvelope.from_dict(raw)
            case "accepted_to_terminal":
                validate_transition(
                    LifecycleKind.ATTEMPT,
                    "accepted",
                    "terminal",
                    outcome=TerminalOutcome.FAILED,
                )
            case "generation_only_match":
                fence = ResponseFence()
                fence.begin(ResponseRef("interaction-1", "response-1", 0))
                fence.apply_if_current(
                    ResponseRef("interaction-1", "wrong-response", 0), effect
                )
            case "context_uri_bom":
                raw = copy.deepcopy(progress_fixture["context_refs"][0])
                raw["uri"] = "urn:test:\ufeff"
                ContextRef.from_dict(raw)
            case "context_stable_id_bom_only":
                raw = copy.deepcopy(progress_fixture["context_refs"][0])
                raw["stable_id"] = "\ufeff"
                ContextRef.from_dict(raw)
            case unknown:
                raise AssertionError(f"unknown invalid scenario {unknown}")

    assert raised.value.reason == scenario["reason"]
    assert effects == 0
    assert scenario["zero_effect"] is True


@pytest.mark.parametrize(
    "state", [InputCommitState.PARTIAL, InputCommitState.UNCOMMITTED]
)
@pytest.mark.parametrize("target", list(SideEffectTarget))
def test_uncommitted_input_has_zero_mutating_effects(
    state: InputCommitState, target: SideEffectTarget
) -> None:
    calls = 0

    def effect() -> None:
        nonlocal calls
        calls += 1

    with pytest.raises(ContractViolation, match="cannot invoke"):
        dispatch_committed_input(state, target, effect)
    assert calls == 0

    dispatch_committed_input(InputCommitState.COMMITTED, target, effect)
    assert calls == 1


def test_turn_commit_is_typed_parent_bound_immutable_and_once_only() -> None:
    fixture = _load("critical_kernel.valid.json")
    registry = _registry(fixture)
    ledger = TurnCommitLedger()
    commit = TurnCommit.from_dict(fixture["turn_commit"], identities=registry)

    assert ledger.accept(commit) is True
    assert ledger.accept(commit) is False
    assert (
        CommandEnvelope.from_dict(
            fixture["command"], identities=registry, commits=ledger
        ).origin.commit_id
        == commit.commit_id
    )
    wrong_origin = copy.deepcopy(fixture["command"])
    wrong_origin["origin"]["commit_id"] = "commit-not-accepted"
    with pytest.raises(ContractViolation) as unaccepted_origin:
        CommandEnvelope.from_dict(wrong_origin, identities=registry, commits=ledger)
    assert unaccepted_origin.value.reason == "TURN_COMMIT_NOT_ACCEPTED"

    dispatch_ledger = TurnCommitLedger()
    effects = 0

    def effect(_commit: TurnCommit) -> str:
        nonlocal effects
        effects += 1
        return "sent"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _index: dispatch_ledger.dispatch(
                    commit, SideEffectTarget.AGENT, effect
                ),
                range(2),
            )
        )
    assert effects == 1
    assert sorted(applied for applied, _result in results) == [False, True]

    changed = copy.deepcopy(fixture["turn_commit"])
    changed["text"] = "different"
    with pytest.raises(ContractViolation) as raised:
        ledger.accept(TurnCommit.from_dict(changed, identities=registry))
    assert raised.value.reason == "TURN_COMMIT_CONFLICT"

    wrong_parent = copy.deepcopy(fixture["turn_commit"])
    wrong_parent["interaction_id"] = "interaction-other"
    with pytest.raises(ContractViolation):
        TurnCommit.from_dict(wrong_parent, identities=registry)


def test_identity_scope_kind_parent_and_closed_object_boundaries() -> None:
    fixture = _load("critical_kernel.valid.json")
    registry = _registry(fixture)

    with pytest.raises(ContractViolation) as invalid_record:
        IdentityRegistry().register(
            IdentityRecord(
                ref=IdentityRef(IdentityKind.INTERACTION, ""),
                scope=ScopeRef("", None, None, Assurance.AUTHENTICATED),
            )
        )
    assert invalid_record.value.reason == "INVALID_REQUIRED_TEXT"

    empty_id = copy.deepcopy(fixture["command"])
    empty_id["request_id"] = "  "
    with pytest.raises(ContractViolation) as empty:
        CommandEnvelope.from_dict(empty_id)
    assert empty.value.reason == "INVALID_REQUIRED_TEXT"

    wrong_kind = copy.deepcopy(fixture["query"])
    wrong_kind["target_ref"] = {"kind": "response", "id": "response-1"}
    with pytest.raises(ContractViolation) as kind:
        QueryEnvelope.from_dict(wrong_kind)
    assert kind.value.reason == "IDENTITY_KIND_MISMATCH"

    unknown_field = copy.deepcopy(fixture["command"])
    unknown_field["unexpected"] = True
    with pytest.raises(ContractViolation) as unknown:
        CommandEnvelope.from_dict(unknown_field)
    assert unknown.value.reason == "UNKNOWN_FIELD"

    unknown_enum = copy.deepcopy(fixture["command"])
    unknown_enum["scope"]["assurance"] = "trusted"
    with pytest.raises(ContractViolation) as invalid_enum:
        CommandEnvelope.from_dict(unknown_enum)
    assert invalid_enum.value.reason == "INVALID_ENUM"

    scope = ScopeRef.from_dict(fixture["scope"])
    interaction_2 = IdentityRef(IdentityKind.INTERACTION, "interaction-2")
    registry.register(IdentityRecord(interaction_2, scope))
    with pytest.raises(ContractViolation) as cross_parent:
        registry.register(
            IdentityRecord(
                IdentityRef(IdentityKind.RESPONSE, "response-cross-parent"),
                scope,
                (
                    interaction_2,
                    IdentityRef(IdentityKind.TURN, "turn-1"),
                ),
            )
        )
    assert cross_parent.value.reason == "IDENTITY_PARENT_MISMATCH"

    different_scope = ScopeRef(
        subject_id=scope.subject_id,
        project_id="project-other",
        session_id=scope.session_id,
        assurance=scope.assurance,
    )
    with pytest.raises(ContractViolation) as cross_scope:
        registry.register(
            IdentityRecord(
                IdentityRef(IdentityKind.TURN, "turn-cross-scope"),
                different_scope,
                (IdentityRef(IdentityKind.INTERACTION, "interaction-1"),),
            )
        )
    assert cross_scope.value.reason == "IDENTITY_SCOPE_MISMATCH"


def test_connection_epoch_binding_and_round_parent_rules() -> None:
    fixture = _load("critical_kernel.valid.json")
    registry = _registry(fixture)
    scope = ScopeRef.from_dict(fixture["scope"])
    binding = ConnectionEpochRef("connection-1", 7)

    connection = registry.require(IdentityRef(IdentityKind.CONNECTION, "connection-1"))
    media = registry.require(IdentityRef(IdentityKind.MEDIA_SESSION, "media-session-1"))
    assert connection.connection_epoch_ref == binding
    assert media.connection_epoch_ref == binding
    with pytest.raises(AttributeError):
        connection.connection_epoch_ref.connection_epoch = 8  # type: ignore[union-attr,misc]

    with pytest.raises(ContractViolation) as missing_connection_binding:
        IdentityRegistry().register(
            IdentityRecord(IdentityRef(IdentityKind.CONNECTION, "connection-2"), scope)
        )
    assert (
        missing_connection_binding.value.reason == "CONNECTION_EPOCH_BINDING_REQUIRED"
    )

    with pytest.raises(ContractViolation) as mismatched_connection_binding:
        IdentityRegistry().register(
            IdentityRecord(
                IdentityRef(IdentityKind.CONNECTION, "connection-2"),
                scope,
                connection_epoch_ref=ConnectionEpochRef("connection-other", 0),
            )
        )
    assert (
        mismatched_connection_binding.value.reason
        == "CONNECTION_EPOCH_BINDING_MISMATCH"
    )

    with pytest.raises(ContractViolation) as missing_media_binding:
        registry.register(
            IdentityRecord(
                IdentityRef(IdentityKind.MEDIA_SESSION, "media-session-2"),
                scope,
                (IdentityRef(IdentityKind.INTERACTION, "interaction-1"),),
            )
        )
    assert missing_media_binding.value.reason == "CONNECTION_EPOCH_BINDING_REQUIRED"

    with pytest.raises(ContractViolation) as unknown_connection:
        registry.register(
            IdentityRecord(
                IdentityRef(IdentityKind.MEDIA_SESSION, "media-session-2"),
                scope,
                (IdentityRef(IdentityKind.INTERACTION, "interaction-1"),),
                ConnectionEpochRef("connection-unknown", 7),
            )
        )
    assert unknown_connection.value.reason == "IDENTITY_CONNECTION_NOT_FOUND"

    with pytest.raises(ContractViolation) as stale_epoch:
        registry.register(
            IdentityRecord(
                IdentityRef(IdentityKind.MEDIA_SESSION, "media-session-2"),
                scope,
                (IdentityRef(IdentityKind.INTERACTION, "interaction-1"),),
                ConnectionEpochRef("connection-1", 6),
            )
        )
    assert stale_epoch.value.reason == "CONNECTION_EPOCH_BINDING_MISMATCH"

    with pytest.raises(ContractViolation) as forbidden_binding:
        registry.register(
            IdentityRecord(
                IdentityRef(IdentityKind.ROUND, "round-2"),
                scope,
                connection_epoch_ref=binding,
            )
        )
    assert forbidden_binding.value.reason == "CONNECTION_EPOCH_BINDING_FORBIDDEN"

    with pytest.raises(ContractViolation) as round_parent:
        registry.register(
            IdentityRecord(
                IdentityRef(IdentityKind.ROUND, "round-2"),
                scope,
                (IdentityRef(IdentityKind.TURN, "turn-1"),),
            )
        )
    assert round_parent.value.reason == "IDENTITY_PARENT_MISMATCH"

    cross_scope_registry = IdentityRegistry()
    cross_scope_registry.register(
        IdentityRecord(IdentityRef(IdentityKind.INTERACTION, "interaction-a"), scope)
    )
    other_scope = ScopeRef(
        scope.subject_id, "project-other", scope.session_id, scope.assurance
    )
    cross_scope_registry.register(
        IdentityRecord(
            IdentityRef(IdentityKind.CONNECTION, "connection-cross"),
            other_scope,
            connection_epoch_ref=ConnectionEpochRef("connection-cross", 1),
        )
    )
    with pytest.raises(ContractViolation) as cross_scope:
        cross_scope_registry.register(
            IdentityRecord(
                IdentityRef(IdentityKind.MEDIA_SESSION, "media-cross"),
                scope,
                (IdentityRef(IdentityKind.INTERACTION, "interaction-a"),),
                ConnectionEpochRef("connection-cross", 1),
            )
        )
    assert cross_scope.value.reason == "IDENTITY_SCOPE_MISMATCH"


def test_command_idempotency_replays_one_execution_under_concurrency() -> None:
    fixture = _load("critical_kernel.valid.json")
    command = CommandEnvelope.from_dict(fixture["command"])
    replay_raw = copy.deepcopy(fixture["command"])
    replay_raw["request_id"] = "request-replay"
    replay = CommandEnvelope.from_dict(replay_raw)
    ledger = CommandResultLedger()
    started = threading.Event()
    release = threading.Event()
    calls = 0

    def handler(owner: CommandEnvelope) -> ResultEnvelope:
        nonlocal calls
        calls += 1
        started.set()
        assert release.wait(timeout=5)
        return ResultEnvelope.success(
            owner=owner,
            result={"accepted": True},
            observed_at="2026-08-04T08:00:02Z",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            ledger.execute,
            command,
            observed_at="2026-08-04T08:00:02Z",
            handler=handler,
        )
        assert started.wait(timeout=5)
        second = pool.submit(
            ledger.execute,
            replay,
            observed_at="2026-08-04T08:00:02Z",
            handler=handler,
        )
        release.set()
        first_result = first.result(timeout=5)
        replay_result = second.result(timeout=5)

    assert calls == 1
    assert first_result.request_id == command.request_id
    assert replay_result.request_id == replay.request_id
    assert replay_result.command_id == command.command_id


def test_command_id_conflict_never_reexecutes_and_failure_is_cached() -> None:
    fixture = _load("critical_kernel.valid.json")
    command = CommandEnvelope.from_dict(fixture["command"])
    ledger = CommandResultLedger()
    calls = 0

    def broken(_owner: CommandEnvelope) -> ResultEnvelope:
        nonlocal calls
        calls += 1
        raise RuntimeError("private detail must not escape")

    first = ledger.execute(command, observed_at="2026-08-04T08:00:02Z", handler=broken)
    replay = ledger.execute(command, observed_at="2026-08-04T08:00:03Z", handler=broken)
    assert calls == 1
    assert first.error is not None and first.error.reason == "COMMAND_HANDLER_FAILED"
    assert replay.error == first.error

    changed = copy.deepcopy(fixture["command"])
    changed["payload"]["priority"] = 2
    conflict = ledger.execute(
        CommandEnvelope.from_dict(changed),
        observed_at="2026-08-04T08:00:04Z",
        handler=broken,
    )
    assert calls == 1
    assert conflict.error is not None
    assert conflict.error.code is ErrorCode.CONFLICT
    assert conflict.error.reason == "IDEMPOTENCY_CONFLICT"


def test_response_fence_requires_exact_tuple_and_new_response_identity() -> None:
    fence = ResponseFence()
    first = ResponseRef("interaction-1", "response-1", 0)
    replacement = ResponseRef("interaction-1", "response-2", 1)
    effects: list[str] = []

    fence.begin(first)
    fence.apply_if_current(first, lambda: effects.append("first"))
    fence.begin(replacement)
    with pytest.raises(ContractViolation) as stale:
        fence.apply_if_current(first, lambda: effects.append("stale"))
    assert stale.value.code is ErrorCode.STALE

    generation_only = ResponseRef("interaction-1", "wrong-response", 1)
    with pytest.raises(ContractViolation):
        fence.apply_if_current(generation_only, lambda: effects.append("wrong"))
    fence.cancel(replacement)
    with pytest.raises(ContractViolation):
        fence.apply_if_current(replacement, lambda: effects.append("cancelled"))
    with pytest.raises(ContractViolation):
        fence.begin(ResponseRef("interaction-1", "response-1", 2))
    assert effects == ["first"]


def test_cancel_scopes_route_to_exactly_one_handler() -> None:
    fixture = _load("critical_kernel.valid.json")
    calls: list[tuple[CancelScope, str, object | None]] = []
    handlers = {
        scope: (
            lambda command, scope=scope: calls.append(
                (
                    scope,
                    command.target_ref.id,
                    command.payload.get("response_generation"),
                )
            )
        )
        for scope in CancelScope
    }
    expected_kinds = {
        CancelScope.PLAYBACK_STOP: "response",
        CancelScope.RESPONSE_CANCEL: "response",
        CancelScope.ROUND_CANCEL: "round",
        CancelScope.TASK_CANCEL: "task",
    }
    for scope, kind in expected_kinds.items():
        raw = copy.deepcopy(fixture["command"])
        raw["command_type"] = scope.value
        raw["target_ref"] = {"kind": kind, "id": f"{kind}-1"}
        raw["payload"] = (
            {"interaction_id": "interaction-1", "response_generation": 0}
            if kind == "response"
            else {}
        )
        dispatch_cancel(CommandEnvelope.from_dict(raw), handlers)
    assert calls == [
        (scope, f"{kind}-1", 0 if kind == "response" else None)
        for scope, kind in expected_kinds.items()
    ]
    assert default_barge_in_scopes() == (CancelScope.PLAYBACK_STOP,)
    assert default_barge_in_scopes(cancel_response=True) == (
        CancelScope.PLAYBACK_STOP,
        CancelScope.RESPONSE_CANCEL,
    )
    for invalid in fixture["invalid_cancel_values"]:
        raw = copy.deepcopy(fixture["command"])
        raw["command_type"] = invalid
        with pytest.raises(ContractViolation):
            CommandEnvelope.from_dict(raw)

    wrong_owner = copy.deepcopy(fixture["command"])
    wrong_owner.update(
        {
            "command_type": "response.cancel",
            "target_ref": {"kind": "response", "id": "response-1"},
            "payload": {
                "interaction_id": "interaction-other",
                "response_generation": 0,
            },
        }
    )
    with pytest.raises(ContractViolation):
        CommandEnvelope.from_dict(wrong_owner, identities=_registry(fixture))


def test_lifecycle_rules_reject_attempt_shortcut_and_require_outcome() -> None:
    fixture = _load("critical_kernel.valid.json")
    for kind, current, target in fixture["lifecycle_allowed"]:
        validate_transition(
            kind,
            current,
            target,
            outcome=(TerminalOutcome.COMPLETED if target == "terminal" else None),
        )
    for kind, current, target in fixture["lifecycle_forbidden"]:
        with pytest.raises(ContractViolation):
            validate_transition(
                kind,
                current,
                target,
                outcome=(TerminalOutcome.FAILED if target == "terminal" else None),
            )
    validate_transition(LifecycleKind.ATTEMPT, "accepted", "running")
    validate_transition(
        LifecycleKind.ATTEMPT,
        "running",
        "terminal",
        outcome=TerminalOutcome.COMPLETED,
    )
    with pytest.raises(ContractViolation):
        validate_transition(
            LifecycleKind.ATTEMPT,
            "accepted",
            "terminal",
            outcome=TerminalOutcome.FAILED,
        )
    with pytest.raises(ContractViolation):
        validate_transition(LifecycleKind.RESPONSE, "generating", "terminal")
    with pytest.raises(ContractViolation):
        validate_transition(
            LifecycleKind.RESPONSE,
            "accepted",
            "generating",
            outcome=TerminalOutcome.COMPLETED,
        )


def test_event_gap_reorders_duplicate_and_conflicting_sequence_fail_closed() -> None:
    fixture = _load("critical_kernel.valid.json")
    tracker = EventSequenceTracker()
    later = _event(fixture, event_id="event-1", seq=1, event_type="task.running")
    first = _event(fixture, event_id="event-0", seq=0)

    gap = tracker.accept(later)
    assert gap.status is EventApplyStatus.QUARANTINED_GAP
    assert gap.error is not None
    applied = tracker.accept(first)
    assert applied.applied_event_ids == ("event-0", "event-1")
    duplicate = tracker.accept(later)
    assert duplicate.status is EventApplyStatus.DUPLICATE_APPLIED

    poisoned = EventSequenceTracker()
    assert poisoned.accept(later).status is EventApplyStatus.QUARANTINED_GAP
    conflict = _event(
        fixture, event_id="event-conflict", seq=1, event_type="task.running"
    )
    rejected_conflict = poisoned.accept(conflict)
    assert rejected_conflict.status is EventApplyStatus.REJECTED_CONFLICT
    assert rejected_conflict.error is not None
    assert rejected_conflict.error.code is ErrorCode.PROTOCOL_VIOLATION
    assert poisoned.accept(first).applied_event_ids == ("event-0",)
    duplicate_gap = poisoned.accept(later)
    assert duplicate_gap.status is EventApplyStatus.DUPLICATE_QUARANTINED
    assert duplicate_gap.error is not None

    id_conflict_tracker = EventSequenceTracker()
    assert id_conflict_tracker.accept(later).status is EventApplyStatus.QUARANTINED_GAP
    same_id_changed = _event(
        fixture,
        event_id="event-1",
        seq=2,
        event_type="task.running",
    )
    same_id_result = id_conflict_tracker.accept(same_id_changed)
    assert same_id_result.status is EventApplyStatus.REJECTED_CONFLICT
    assert id_conflict_tracker.accept(first).applied_event_ids == ("event-0",)
    poisoned_original = id_conflict_tracker.accept(later)
    assert poisoned_original.status is EventApplyStatus.DUPLICATE_QUARANTINED
    assert poisoned_original.error is not None
    assert poisoned_original.error.reason == "EVENT_ID_CONFLICT"


def test_event_cause_must_be_applied_but_later_root_is_allowed() -> None:
    fixture = _load("critical_kernel.valid.json")
    tracker = EventSequenceTracker()
    child = _event(
        fixture,
        event_id="event-child",
        seq=0,
        causation_id="event-root",
        producer_instance="task-core-child",
        event_type="task.running",
    )
    root = _event(
        fixture,
        event_id="event-root",
        seq=0,
        producer_instance="task-core-root",
    )
    assert tracker.accept(child).status is EventApplyStatus.QUARANTINED_CAUSATION
    assert tracker.accept(root).applied_event_ids == ("event-root", "event-child")
    later_root = _event(
        fixture,
        event_id="event-later-root",
        seq=0,
        producer_instance="task-core-later",
        stream_id="task-2",
    )
    assert tracker.accept(later_root).status is EventApplyStatus.APPLIED

    externally_caused = _event(
        fixture,
        event_id="event-command-caused",
        seq=0,
        causation_id="command-accepted-1",
        producer_instance="task-core-command-caused",
        stream_id="task-3",
    )
    command_tracker = EventSequenceTracker()
    assert (
        command_tracker.accept(externally_caused).status
        is EventApplyStatus.QUARANTINED_CAUSATION
    )
    command_raw = copy.deepcopy(fixture["command"])
    command_raw["command_id"] = "command-accepted-1"
    command = CommandEnvelope.from_dict(command_raw)
    assert command_tracker.register_applied_cause(command) == ("event-command-caused",)
    assert (
        command_tracker.accept(externally_caused).status
        is EventApplyStatus.DUPLICATE_APPLIED
    )


@pytest.mark.parametrize(
    ("changed_field", "reason"),
    [
        ("scope", "CAUSATION_SCOPE_MISMATCH"),
        ("correlation_id", "CAUSATION_CORRELATION_MISMATCH"),
    ],
)
def test_event_cause_must_share_scope_and_correlation(
    changed_field: str, reason: str
) -> None:
    fixture = _load("critical_kernel.valid.json")
    tracker = EventSequenceTracker()
    source = _event(fixture, event_id="cause-source", seq=0)
    assert tracker.accept(source).status is EventApplyStatus.APPLIED

    child_raw = copy.deepcopy(fixture["event"])
    child_raw.update(
        {
            "event_id": f"cause-child-{changed_field}",
            "event_type": "task.running",
            "producer": {
                "component": "task_core",
                "instance_id": f"cause-child-{changed_field}",
                "authority": "task_core",
            },
            "seq": 0,
            "causation_id": "cause-source",
            "payload": {"state": "running"},
        }
    )
    if changed_field == "scope":
        child_raw["scope"]["subject_id"] = "other-subject"
    else:
        child_raw["correlation_id"] = "other-correlation"
    result = tracker.accept(EventEnvelope.from_dict(child_raw))
    assert result.status is EventApplyStatus.REJECTED_CAUSATION
    assert result.error is not None
    assert result.error.reason == reason


def test_event_tracker_enforces_lifecycle_and_adapter_authority_chain() -> None:
    fixture = _load("critical_kernel.valid.json")
    terminal_first_raw = copy.deepcopy(fixture["event"])
    terminal_first_raw["event_id"] = "event-terminal-first"
    terminal_first_raw["event_type"] = "task.terminal"
    terminal_first_raw["payload"] = {"state": "terminal", "outcome": "failed"}
    terminal_first = EventEnvelope.from_dict(terminal_first_raw)
    tracker = EventSequenceTracker()
    rejected = tracker.accept(terminal_first)
    assert rejected.status is EventApplyStatus.REJECTED_LIFECYCLE
    assert rejected.error is not None
    assert rejected.error.reason == "INVALID_INITIAL_LIFECYCLE_STATE"

    attempt_accepted_raw = copy.deepcopy(fixture["event"])
    attempt_accepted_raw.update(
        {
            "event_id": "attempt-event-0",
            "event_type": "attempt.accepted",
            "producer": {
                "component": "executor",
                "instance_id": "executor-1",
                "authority": "executor",
            },
            "stream_ref": {"kind": "attempt", "id": "attempt-1"},
            "payload": {"state": "accepted"},
        }
    )
    attempt_terminal_raw = copy.deepcopy(attempt_accepted_raw)
    attempt_terminal_raw.update(
        {
            "event_id": "attempt-event-1",
            "event_type": "attempt.terminal",
            "seq": 1,
            "payload": {"state": "terminal", "outcome": "failed"},
        }
    )
    attempt_tracker = EventSequenceTracker()
    assert (
        attempt_tracker.accept(EventEnvelope.from_dict(attempt_accepted_raw)).status
        is EventApplyStatus.APPLIED
    )
    attempt_rejected = attempt_tracker.accept(
        EventEnvelope.from_dict(attempt_terminal_raw)
    )
    assert attempt_rejected.status is EventApplyStatus.REJECTED_LIFECYCLE
    assert attempt_rejected.error is not None
    assert attempt_rejected.error.code is ErrorCode.PROTOCOL_VIOLATION

    task_tracker = EventSequenceTracker()
    accepted = _event(fixture, event_id="task-restart-0", seq=0)
    terminal_raw = copy.deepcopy(fixture["event"])
    terminal_raw.update(
        {
            "event_id": "task-restart-1",
            "event_type": "task.terminal",
            "seq": 1,
            "payload": {"state": "terminal", "outcome": "completed"},
        }
    )
    restarted = _event(
        fixture,
        event_id="task-restart-2",
        seq=0,
        producer_instance="task-core-restarted",
    )
    assert task_tracker.accept(accepted).status is EventApplyStatus.APPLIED
    assert (
        task_tracker.accept(EventEnvelope.from_dict(terminal_raw)).status
        is EventApplyStatus.APPLIED
    )
    restarted_result = task_tracker.accept(restarted)
    assert restarted_result.status is EventApplyStatus.REJECTED_LIFECYCLE
    assert restarted_result.error is not None
    assert restarted_result.error.reason == "INVALID_LIFECYCLE_TRANSITION"

    source = _event(fixture, event_id="source-event", seq=0)
    adapter_raw = copy.deepcopy(fixture["event"])
    adapter_raw.update(
        {
            "event_id": "adapter-event-1",
            "event_type": "adapter.observed",
            "producer": {
                "component": "task.adapter",
                "instance_id": "adapter-1",
                "authority": "adapter",
            },
            "stream_ref": {"kind": "event", "id": "adapter-stream-1"},
            "causation_id": "source-event",
            "payload": {"source_event_type": "task.accepted"},
        }
    )
    authority_tracker = EventSequenceTracker()
    assert authority_tracker.accept(source).status is EventApplyStatus.APPLIED
    adapter = EventEnvelope.from_dict(adapter_raw)
    assert authority_tracker.accept(adapter).status is EventApplyStatus.APPLIED

    chained_raw = copy.deepcopy(adapter_raw)
    chained_raw.update(
        {
            "event_id": "adapter-event-2",
            "producer": {
                "component": "task.adapter",
                "instance_id": "adapter-2",
                "authority": "adapter",
            },
            "stream_ref": {"kind": "event", "id": "adapter-stream-2"},
            "causation_id": "adapter-event-1",
            "payload": {"source_event_type": "adapter.observed"},
        }
    )
    chained = authority_tracker.accept(EventEnvelope.from_dict(chained_raw))
    assert chained.status is EventApplyStatus.REJECTED_CAUSATION
    assert chained.error is not None
    assert chained.error.reason == "ADAPTER_SOURCE_NOT_AUTHORITATIVE"


def test_event_authority_capability_and_v1_separation() -> None:
    fixture = _load("critical_kernel.valid.json")
    wrong = copy.deepcopy(fixture["event"])
    wrong["producer"]["authority"] = "adapter"
    with pytest.raises(ContractViolation) as authority:
        EventEnvelope.from_dict(wrong)
    assert authority.value.code is ErrorCode.PERMISSION_DENIED

    registry = CapabilityRegistry()
    descriptor = CapabilityDescriptor.from_dict(fixture["capability"])
    registry.register(descriptor)
    registry.require("speech.sr", "recognize.batch")
    with pytest.raises(ContractViolation) as unsupported:
        registry.require("speech.sr", "synthesize.batch")
    assert unsupported.value.code is ErrorCode.UNSUPPORTED

    unavailable = copy.deepcopy(fixture["capability"])
    unavailable["component"] = "speech.unavailable"
    unavailable["availability"] = "unavailable"
    registry.register(CapabilityDescriptor.from_dict(unavailable))
    with pytest.raises(ContractViolation) as down:
        registry.require("speech.unavailable", "recognize.batch")
    assert down.value.code is ErrorCode.UNAVAILABLE

    failure_raw = {
        "contract_version": CONTRACT_VERSION,
        "request_id": "request-2",
        "command_id": None,
        "ok": False,
        "result": None,
        "error": {
            "code": "UNAVAILABLE",
            "reason": "PROVIDER_DOWN",
            "message": "provider is unavailable",
            "retriable": True,
            "correlation_id": "correlation-1",
            "details": {},
        },
        "observed_at": "2026-08-04T08:00:05Z",
        "extensions": {},
    }
    assert ResultEnvelope.from_dict(failure_raw).to_dict() == failure_raw

    observed_codes = []
    for code in fixture["distinct_error_codes"]:
        raw = copy.deepcopy(failure_raw)
        raw["error"]["code"] = code
        raw["error"]["reason"] = f"TEST_{code}"
        observed_codes.append(
            ResultEnvelope.from_dict(raw).error.code.value  # type: ignore[union-attr]
        )
    assert observed_codes == fixture["distinct_error_codes"]

    wrong_mode = copy.deepcopy(fixture["capability"])
    wrong_mode["batch_modes"] = ["stream"]
    with pytest.raises(ContractViolation):
        CapabilityDescriptor.from_dict(wrong_mode)

    legacy = _load("compatibility.v1.json")
    assert classify_contract(legacy) == "v1"
    with pytest.raises(ContractViolation):
        parse_v2_envelope(legacy)
    assert CONTRACT_VERSION == "live-voice.contract.v2"


def test_strict_json_rejects_non_json_cycles_surrogates_and_unsafe_integers() -> None:
    fixture = _load("critical_kernel.valid.json")

    class DictSubclass(dict):
        pass

    with pytest.raises(ContractViolation):
        CommandEnvelope.from_dict(DictSubclass(fixture["command"]))

    cycle = copy.deepcopy(fixture["command"])
    cycle["payload"]["cycle"] = cycle["payload"]
    with pytest.raises(ContractViolation) as cyclic:
        CommandEnvelope.from_dict(cycle)
    assert cyclic.value.reason == "CYCLIC_JSON"

    surrogate = copy.deepcopy(fixture["command"])
    surrogate["payload"]["text"] = "\ud800"
    with pytest.raises(ContractViolation) as invalid_unicode:
        CommandEnvelope.from_dict(surrogate)
    assert invalid_unicode.value.reason == "INVALID_UNICODE_SCALAR"

    unsafe = copy.deepcopy(fixture["command"])
    unsafe["payload"]["number"] = 9_007_199_254_740_992
    with pytest.raises(ContractViolation) as invalid_integer:
        CommandEnvelope.from_dict(unsafe)
    assert invalid_integer.value.reason == "INVALID_SAFE_INTEGER"
