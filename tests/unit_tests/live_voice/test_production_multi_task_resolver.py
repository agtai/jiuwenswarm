# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Thread

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ScopeRef,
    TurnCommit,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.production_task_intent import (
    AuthenticatedTaskFact,
    BoundedClarificationOwner,
    ClarificationAnswer,
    ProductionConfirmationFact,
    ProductionIntentOrigin,
    ProductionInteractionBinding,
    ProductionTaskIntentProposal,
    ProductionTaskIntentRequest,
    ProductionTaskPolicyOutcome,
    ProductionTaskResolution,
    TaskAuthorityRead,
)
from jiuwenswarm.server.live_voice.voice_task_bridge import VoiceTaskBridge

CORPUS_DIR = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "live_voice_p3_6_intent_corpus_v1"
)
SCOPE = ScopeRef("subject-a", "project-a", "session-a", Assurance.AUTHENTICATED)


def _commit(text: str, *, commit_id: str = "commit-1") -> TurnCommit:
    return TurnCommit.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "interaction_id": "interaction-1",
            "turn_id": f"turn-{commit_id}",
            "commit_id": commit_id,
            "scope": SCOPE.to_dict(),
            "text": text,
            "hypothesis_provenance": {"provider": "test", "kind": "committed_text"},
            "context_refs": [],
            "committed_at": "2026-08-20T00:00:00Z",
        }
    )


class RecordingAuthority:
    def __init__(self, facts: tuple[AuthenticatedTaskFact, ...]) -> None:
        self.facts = facts
        self.calls: list[tuple[str, str | None]] = []

    def list_visible_tasks(self, scope: ScopeRef) -> TaskAuthorityRead:
        self.calls.append(("list", None))
        assert scope == SCOPE
        return TaskAuthorityRead(scope, "generation-1", self.facts)

    def get_task(self, scope: ScopeRef, task_id: str) -> AuthenticatedTaskFact | None:
        self.calls.append(("get", task_id))
        assert scope == SCOPE
        return next((fact for fact in self.facts if fact.task_id == task_id), None)

    def task_status(
        self, scope: ScopeRef, task_id: str
    ) -> AuthenticatedTaskFact | None:
        self.calls.append(("status", task_id))
        return self.get_task(scope, task_id)

    def event_head(self, scope: ScopeRef, task_id: str) -> tuple[int, str]:
        self.calls.append(("events", task_id))
        fact = self.get_task(scope, task_id)
        assert fact is not None
        return fact.event_head, fact.event_head_id

    def result_digest(self, scope: ScopeRef, task_id: str) -> str | None:
        self.calls.append(("result", task_id))
        fact = self.get_task(scope, task_id)
        assert fact is not None
        return fact.result_digest

    def unread_head(self, scope: ScopeRef, task_id: str) -> tuple[int, str] | None:
        self.calls.append(("unread", task_id))
        fact = self.get_task(scope, task_id)
        assert fact is not None
        return (fact.event_head, fact.event_head_id)


def _fact(
    task_id: str,
    ref: str,
    name: str,
    *,
    state: str = "running",
    generation: int = 1,
    capabilities: frozenset[str] = frozenset({"task.adjust", "task.cancel"}),
    result_digest: str | None = None,
) -> AuthenticatedTaskFact:
    terminal = state in {"completed", "failed", "cancelled", "interrupted", "unknown"}
    return AuthenticatedTaskFact(
        task_id=task_id,
        stable_reference=ref,
        name=name,
        state=state,
        terminal=terminal,
        task_generation=generation,
        event_head=7,
        event_head_id=f"event-{task_id}",
        attempt_id=f"attempt-{task_id}",
        attempt_state=("terminal" if terminal else state),
        capability_profile_digest="a" * 64,
        supported_operations=capabilities,
        result_digest=result_digest,
        decision_required_event_id=(
            "evt_fixture_decision_001" if state == "decision_required" else None
        ),
        dispatch_unclaimed=state == "accepted",
    )


def _request(
    proposal: ProductionTaskIntentProposal,
    *,
    origin: ProductionIntentOrigin = ProductionIntentOrigin.NATURAL_TEXT,
    commit_id: str = "commit-1",
) -> ProductionTaskIntentRequest:
    if (
        origin is not ProductionIntentOrigin.STRUCTURED
        and proposal.operation is not None
        and proposal.source_start is None
    ):
        proposal = replace(proposal, source_start=0, source_end=6)
    return ProductionTaskIntentRequest(
        origin=origin,
        scope=SCOPE,
        proposal=proposal,
        commit=(
            None
            if origin is ProductionIntentOrigin.STRUCTURED
            else _commit("intent", commit_id=commit_id)
        ),
    )


def _matches_expected(
    result: ProductionTaskResolution, expected: dict[str, object]
) -> bool:
    return result.canonical_policy_tuple() == (
        expected["classification"],
        expected["canonical_operation"],
        expected["target_task_id"],
        canonical_json_bytes(expected["arguments"]),
        expected["confirmation"],
        expected["policy_outcome"],
    )


def _from_corpus_case(
    case: dict[str, object],
) -> tuple[RecordingAuthority, ProductionTaskIntentRequest]:
    raw_facts = case["task_facts"]
    assert isinstance(raw_facts, list)
    facts: list[AuthenticatedTaskFact] = []
    for raw in raw_facts:
        assert isinstance(raw, dict)
        state = str(raw["state"])
        terminal = bool(raw["terminal"])
        raw_attempt_state = str(raw["current_attempt_state"])
        attempt_state = (
            "terminal"
            if terminal
            else "running"
            if raw_attempt_state in {"blocked", "decision_required"}
            else raw_attempt_state
        )
        capabilities = {"task.cancel"}
        if state == "running":
            capabilities.add("task.adjust")
        if state == "accepted" and raw["dispatch_outbox_state"] == "unclaimed":
            capabilities.add("task.update")
        result_digest = "b" * 64 if terminal and state != "unknown" else None
        facts.append(
            AuthenticatedTaskFact(
                task_id=str(raw["task_id"]),
                stable_reference=str(raw["user_reference"]),
                name=str(raw["name"]),
                state=state,
                terminal=terminal,
                task_generation=int(raw["snapshot_version"]),
                event_head=int(raw["snapshot_version"]),
                event_head_id=f"event-head-{raw['task_id']}",
                attempt_id=f"attempt-{raw['task_id']}",
                attempt_state=attempt_state,
                capability_profile_digest="a" * 64,
                supported_operations=frozenset(capabilities),
                result_digest=result_digest,
                decision_required_event_id=(
                    str(raw["decision_required_event_id"])
                    if raw["decision_required_event_id"] is not None
                    else None
                ),
                dispatch_unclaimed=raw["dispatch_outbox_state"] == "unclaimed",
            )
        )
    authority = RecordingAuthority(tuple(facts))
    expected = case["expected"]
    partitions = case["partitions"]
    assert isinstance(expected, dict) and isinstance(partitions, dict)
    classification = expected["classification"]
    operation = expected["canonical_operation"]
    target_partition = partitions["target"]
    target_id = expected["target_task_id"]

    if classification == "dialogue":
        proposal = ProductionTaskIntentProposal.dialogue(reason="ORDINARY_DIALOGUE")
    elif operation is None:
        safety = set(partitions["safety"])
        if "partial_interim" in safety:
            proposal = ProductionTaskIntentProposal(None, None, {}, 1.0, False)
        elif "low_confidence" in safety:
            proposal = ProductionTaskIntentProposal(None, None, {}, 0.1, True)
        else:
            proposal = ProductionTaskIntentProposal(
                None, None, {}, 1.0, True, reason="REJECTED_UNSAFE_TASK_TEXT"
            )
    else:
        target: str | None
        matching = next((fact for fact in facts if fact.task_id == target_id), None)
        if target_partition in {"collection"}:
            target = None
        elif target_partition == "explicit_task_id":
            target = str(target_id) if target_id else "tsk_fixture_foreign_001"
        elif target_partition in {
            "stable_user_reference",
            "stale_target",
            "terminal_predecessor",
            "two_visible_tasks",
        }:
            target = matching.stable_reference if matching else "REF-Z9"
        elif target_partition == "unique_authorized_name":
            target = matching.name if matching else "Missing name"
        elif target_partition == "duplicate_name":
            target = facts[0].name
        elif target_partition == "multiple_candidates":
            target = "report"
        elif target_partition == "zero_candidate":
            target = "REF-Z9"
        elif target_partition == "current_recent_hint_only":
            target = "current"
        elif target_partition == "foreign_scope_project":
            target = "tsk_fixture_foreign_001"
        else:
            target = None
        observed = None
        snapshot = case.get("target_snapshot")
        if isinstance(snapshot, dict):
            observed = int(snapshot["observed_snapshot_version"])
        proposal = ProductionTaskIntentProposal(
            operation=str(operation),
            target=target,
            arguments=expected["arguments"],
            confidence=float(case["confidence"]),
            committed=bool(case["committed"]),
            target_kind=(
                "task_id"
                if target_partition in {"explicit_task_id", "foreign_scope_project"}
                else "stable_reference"
                if target_partition
                in {
                    "stable_user_reference",
                    "stale_target",
                    "terminal_predecessor",
                    "two_visible_tasks",
                    "zero_candidate",
                }
                else "name"
                if target_partition
                in {"unique_authorized_name", "duplicate_name", "multiple_candidates"}
                else "hint"
                if target_partition == "current_recent_hint_only"
                else None
            ),
            source_start=(None if case["origin"] == "structured" else 0),
            source_end=(
                None if case["origin"] == "structured" else len(str(case["input_text"]))
            ),
            observed_task_generation=observed,
        )
        context = case.get("interaction_context")
        if isinstance(context, dict):
            current = authority.list_visible_tasks(SCOPE)
            binding = ProductionInteractionBinding(
                kind=str(context["kind"]),
                binding_id=str(context["context_id"]),
                operation=str(context["bound_operation"]),
                target_task_id=(
                    str(context["bound_target_task_id"])
                    if context["bound_target_task_id"] is not None
                    else None
                ),
                arguments=context["bound_arguments"],
                candidate_task_ids=tuple(context["bound_candidate_task_ids"]),
                task_set_fingerprint=(
                    "d" * 64
                    if "changed_task_set" in set(partitions["safety"])
                    else current.fingerprint
                ),
            )
            proposal = replace(proposal, interaction_binding=binding)
            authority.calls.clear()

    origin = ProductionIntentOrigin(str(case["origin"]))
    commit = (
        None
        if origin is ProductionIntentOrigin.STRUCTURED
        else _commit(str(case["input_text"]), commit_id=str(case["case_id"]))
    )
    return authority, ProductionTaskIntentRequest(
        origin=origin,
        scope=SCOPE,
        proposal=proposal,
        commit=commit,
        source_id=str(case["case_id"]),
    )


def test_actual_voice_task_bridge_path_rereads_authenticated_core_facts() -> None:
    authority = RecordingAuthority(
        (_fact("task-a", "REF-A", "Build report", state="running"),)
    )
    proposal = ProductionTaskIntentProposal(
        operation="task.status",
        target="REF-A",
        arguments={"query_kind": "status"},
        confidence=0.99,
        committed=True,
        source_start=0,
        source_end=6,
    )

    result = VoiceTaskBridge().resolve_production(_request(proposal), authority)

    assert result == ProductionTaskResolution.task_intent(
        operation="task.status",
        target_task_id="task-a",
        arguments={"query_kind": "status"},
        confirmation="not_required",
        outcome=ProductionTaskPolicyOutcome.PROPOSED,
        task_set_fingerprint=result.task_set_fingerprint,
        authority_fingerprint=result.authority_fingerprint,
        reason="TASK_QUERY_POLICY_ACCEPTED",
    )
    assert [call[0] for call in authority.calls] == ["list", "get", "status", "get"]


@pytest.mark.parametrize("origin", tuple(ProductionIntentOrigin))
def test_natural_voice_and_structured_share_one_closed_policy(
    origin: ProductionIntentOrigin,
) -> None:
    authority = RecordingAuthority((_fact("task-a", "REF-A", "Build report"),))
    proposal = ProductionTaskIntentProposal(
        operation="task.cancel",
        target="task-a",
        arguments={},
        confidence=1.0,
        committed=True,
        source_start=0,
        source_end=6,
    )

    result = VoiceTaskBridge().resolve_production(
        _request(proposal, origin=origin), authority
    )

    assert result.operation == "task.cancel"
    assert result.target_task_id == "task-a"
    assert result.confirmation == "required"
    assert result.outcome is ProductionTaskPolicyOutcome.PROPOSED


@pytest.mark.parametrize(
    ("proposal", "outcome"),
    (
        (
            ProductionTaskIntentProposal.dialogue(reason="NEGATED_TASK_INTENT"),
            ProductionTaskPolicyOutcome.DIALOGUE,
        ),
        (
            ProductionTaskIntentProposal.dialogue(reason="ORDINARY_DIALOGUE"),
            ProductionTaskPolicyOutcome.DIALOGUE,
        ),
        (
            ProductionTaskIntentProposal(
                operation="task.cancel",
                target="REF-A",
                arguments={},
                confidence=0.2,
                committed=True,
            ),
            ProductionTaskPolicyOutcome.REJECTED,
        ),
        (
            ProductionTaskIntentProposal(
                operation="task.cancel",
                target="REF-A",
                arguments={},
                confidence=1.0,
                committed=False,
            ),
            ProductionTaskPolicyOutcome.REJECTED,
        ),
    ),
)
def test_dialogue_negation_partial_and_low_confidence_have_zero_effects(
    proposal: ProductionTaskIntentProposal,
    outcome: ProductionTaskPolicyOutcome,
) -> None:
    authority = RecordingAuthority((_fact("task-a", "REF-A", "Build report"),))
    result = VoiceTaskBridge().resolve_production(_request(proposal), authority)
    assert result.outcome is outcome
    assert result.zero_effects
    assert authority.calls == []


def test_explicit_id_and_ref_win_but_names_must_be_unique_and_hints_never_select() -> (
    None
):
    facts = (
        _fact("task-a", "REF-A", "Report"),
        _fact("task-b", "REF-B", "Report"),
    )
    authority = RecordingAuthority(facts)
    bridge = VoiceTaskBridge()

    exact = bridge.resolve_production(
        _request(
            ProductionTaskIntentProposal.intent(
                "task.status", "REF-B", {"query_kind": "status"}
            )
        ),
        authority,
    )
    duplicate = bridge.resolve_production(
        _request(
            ProductionTaskIntentProposal.intent(
                "task.status", "Report", {"query_kind": "status"}
            )
        ),
        authority,
    )
    missing = bridge.resolve_production(
        _request(
            ProductionTaskIntentProposal.intent(
                "task.status", "current", {"query_kind": "status"}
            )
        ),
        authority,
    )

    assert exact.target_task_id == "task-b"
    assert duplicate.outcome is ProductionTaskPolicyOutcome.CLARIFICATION
    assert duplicate.candidate_task_ids == ("task-a", "task-b")
    assert missing.outcome is ProductionTaskPolicyOutcome.CLARIFICATION
    assert missing.target_task_id is None


def test_target_reread_and_changed_task_set_fail_closed() -> None:
    fact = _fact("task-a", "REF-A", "Report")

    class DriftingAuthority(RecordingAuthority):
        def get_task(
            self, scope: ScopeRef, task_id: str
        ) -> AuthenticatedTaskFact | None:
            found = super().get_task(scope, task_id)
            return None if found is None else replace(found, task_generation=2)

    result = VoiceTaskBridge().resolve_production(
        _request(ProductionTaskIntentProposal.intent("task.cancel", "REF-A", {})),
        DriftingAuthority((fact,)),
    )
    assert result.outcome is ProductionTaskPolicyOutcome.CONFLICT
    assert result.reason == "TASK_AUTHORITY_CHANGED"
    assert result.zero_effects


def test_foreign_authority_and_malformed_argument_bounds_fail_closed() -> None:
    foreign_scope = ScopeRef(
        "subject-a", "project-foreign", "session-a", Assurance.AUTHENTICATED
    )

    class ForeignAuthority(RecordingAuthority):
        def list_visible_tasks(self, scope: ScopeRef) -> TaskAuthorityRead:
            self.calls.append(("list", None))
            return TaskAuthorityRead(foreign_scope, "foreign-generation", self.facts)

    authority = ForeignAuthority((_fact("task-a", "REF-A", "Report"),))
    result = VoiceTaskBridge().resolve_production(
        _request(
            ProductionTaskIntentProposal.intent(
                "task.status", "REF-A", {"query_kind": "status"}
            )
        ),
        authority,
    )
    assert result.outcome is ProductionTaskPolicyOutcome.REJECTED
    assert result.reason == "TASK_AUTHORITY_SCOPE_MISMATCH"
    assert result.zero_effects
    assert authority.calls == [("list", None)]

    with pytest.raises(ValueError, match="INVALID_TASK_INTENT_ARGUMENT_VALUE"):
        ProductionTaskIntentProposal.intent(
            "task.update", "REF-A", {"instruction": {"nested": "forbidden"}}
        )
    with pytest.raises(ValueError, match="INVALID_TASK_INTENT_ARGUMENT"):
        ProductionTaskIntentProposal.intent(
            "task.update", "REF-A", {"instruction": "x" * 4_097}
        )


def test_unsupported_controls_and_terminal_conflicts_never_invent_primitives() -> None:
    running = RecordingAuthority(
        (_fact("task-a", "REF-A", "Report", capabilities=frozenset()),)
    )
    terminal = RecordingAuthority(
        (_fact("task-a", "REF-A", "Report", state="completed", result_digest="b" * 64),)
    )
    bridge = VoiceTaskBridge()

    arguments_by_operation: dict[str, dict[str, object]] = {
        "task.provide_input": {
            "answer": "bounded answer",
            "responds_to_event_id": "event-decision",
        },
        "task.pause": {},
        "task.resume": {},
        "task.reprioritize": {"priority": "high"},
    }
    for operation, arguments in arguments_by_operation.items():
        result = bridge.resolve_production(
            _request(
                ProductionTaskIntentProposal.intent(operation, "REF-A", arguments)
            ),
            running,
        )
        assert result.outcome is ProductionTaskPolicyOutcome.UNSUPPORTED
        assert result.zero_effects

    terminal_result = bridge.resolve_production(
        _request(ProductionTaskIntentProposal.intent("task.pause", "REF-A", {})),
        terminal,
    )
    assert terminal_result.outcome is ProductionTaskPolicyOutcome.CONFLICT


def test_successor_requires_exact_core_result_digest_and_rejects_unknown() -> None:
    completed = RecordingAuthority(
        (_fact("task-a", "REF-A", "Report", state="completed", result_digest="b" * 64),)
    )
    unknown = RecordingAuthority((_fact("task-a", "REF-A", "Report", state="unknown"),))
    proposal = ProductionTaskIntentProposal.intent(
        "task.create_successor",
        "REF-A",
        {"name": "Revision", "instruction": "Revise report."},
    )
    bridge = VoiceTaskBridge()

    accepted = bridge.resolve_production(_request(proposal), completed)
    refused = bridge.resolve_production(_request(proposal), unknown)

    assert accepted.outcome is ProductionTaskPolicyOutcome.PROPOSED
    assert accepted.predecessor_result_digest == "b" * 64
    assert refused.outcome is ProductionTaskPolicyOutcome.CONFLICT


def test_clarification_owner_is_bounded_single_use_cas_and_restart_invalidates_handles() -> (
    None
):
    now = datetime(2026, 8, 20, tzinfo=UTC)
    owner = BoundedClarificationOwner(
        capacity=2, ttl=timedelta(minutes=2), boot_id="boot-a"
    )
    issued = owner.issue(
        scope=SCOPE,
        source_commit_id="commit-1",
        operation="task.cancel",
        ambiguous_fields=("target",),
        candidate_task_ids=("task-a", "task-b"),
        task_set_fingerprint="c" * 64,
        now=now,
    )
    answer = ClarificationAnswer(
        handle_id=issued.handle_id,
        generation=issued.generation,
        scope=SCOPE,
        commit_id="answer-1",
        selected_task_id="task-a",
        task_set_fingerprint="c" * 64,
    )

    results: list[object] = []
    barrier = Barrier(2)

    def consume() -> None:
        barrier.wait()
        results.append(owner.consume(answer, now=now + timedelta(seconds=1)))

    threads = [Thread(target=consume), Thread(target=consume)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results[0] == results[1]
    changed = replace(answer, commit_id="answer-2", selected_task_id="task-b")
    with pytest.raises(ValueError, match="CLARIFICATION_ALREADY_CONSUMED"):
        owner.consume(changed, now=now + timedelta(seconds=2))

    owner.restart("boot-b")
    with pytest.raises(ValueError, match="CLARIFICATION_HANDLE_INVALID_AFTER_RESTART"):
        owner.consume(answer, now=now + timedelta(seconds=3))


def test_clarification_capacity_and_expiry_are_safe_bounded_failures() -> None:
    now = datetime(2026, 8, 20, tzinfo=UTC)
    owner = BoundedClarificationOwner(
        capacity=1, ttl=timedelta(seconds=1), boot_id="boot-a"
    )
    issued = owner.issue(
        scope=SCOPE,
        source_commit_id="commit-1",
        operation="task.cancel",
        ambiguous_fields=("target",),
        candidate_task_ids=("task-a",),
        task_set_fingerprint="c" * 64,
        now=now,
    )
    with pytest.raises(ValueError, match="CLARIFICATION_CAPACITY_EXCEEDED"):
        owner.issue(
            scope=SCOPE,
            source_commit_id="commit-2",
            operation="task.cancel",
            ambiguous_fields=("target",),
            candidate_task_ids=("task-b",),
            task_set_fingerprint="d" * 64,
            now=now,
        )
    with pytest.raises(ValueError, match="CLARIFICATION_HANDLE_EXPIRED"):
        owner.consume(
            ClarificationAnswer(
                handle_id=issued.handle_id,
                generation=issued.generation,
                scope=SCOPE,
                commit_id="answer-1",
                selected_task_id="task-a",
                task_set_fingerprint="c" * 64,
            ),
            now=now + timedelta(seconds=1),
        )


def test_confirmation_must_bind_operation_target_arguments_and_task_set() -> None:
    authority = RecordingAuthority((_fact("task-a", "REF-A", "Report"),))
    base = ProductionTaskIntentProposal.intent("task.cancel", "REF-A", {})
    proposed = VoiceTaskBridge().resolve_production(_request(base), authority)
    assert proposed.task_set_fingerprint is not None
    confirmation = ProductionConfirmationFact(
        confirmation_id="confirmation-1",
        operation="task.cancel",
        target_task_id="task-a",
        arguments_sha256=hashlib.sha256(canonical_json_bytes({})).hexdigest(),
        task_set_fingerprint=proposed.task_set_fingerprint,
    )

    exact = VoiceTaskBridge().resolve_production(
        _request(replace(base, confirmation=confirmation)), authority
    )
    changed = VoiceTaskBridge().resolve_production(
        _request(
            replace(
                ProductionTaskIntentProposal.intent("task.pause", "REF-A", {}),
                confirmation=confirmation,
            )
        ),
        authority,
    )
    consumed = VoiceTaskBridge().resolve_production(
        _request(replace(base, confirmation=replace(confirmation, consumed=True))),
        authority,
    )

    assert exact.confirmation == "confirmed"
    assert exact.outcome is ProductionTaskPolicyOutcome.PROPOSED
    assert changed.outcome is ProductionTaskPolicyOutcome.CONFLICT
    assert consumed.outcome is ProductionTaskPolicyOutcome.CONFLICT
    assert changed.zero_effects


def test_all_68_corpus_cases_and_14_parity_groups_use_production_bridge_policy() -> (
    None
):
    cases = [
        json.loads(line)
        for line in (CORPUS_DIR / "cases.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(cases) == 68
    assert len({case["parity_group"] for case in cases if case["parity_group"]}) == 14

    actual: dict[str, ProductionTaskResolution] = {}
    for case in cases:
        authority, request = _from_corpus_case(case)
        actual[case["case_id"]] = VoiceTaskBridge().resolve_production(
            request, authority
        )
        assert _matches_expected(actual[case["case_id"]], case["expected"]), case[
            "case_id"
        ]
        assert actual[case["case_id"]].zero_effects == tuple(
            case["expected"]["zero_effects"]
        )

    for group in {case["parity_group"] for case in cases if case["parity_group"]}:
        group_results = [
            actual[case["case_id"]].canonical_policy_tuple()
            for case in cases
            if case["parity_group"] == group
        ]
        assert len(set(group_results)) == 1, group
