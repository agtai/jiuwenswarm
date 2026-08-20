"""Focused production-path and resolver-policy-only P3-6 corpus evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CONTRACT_VERSION,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.production_task_intent import (
    AuthenticatedTaskFact,
    BoundedClarificationOwner,
    ClarificationAnswer,
    ProductionConfirmationBinding,
    ProductionFieldExtraction,
    ProductionIntentOrigin,
    ProductionOriginBinding,
    ProductionTaskIntentProposal,
    ProductionTaskIntentRequest,
    ProductionTaskPolicyOutcome,
    ProductionTaskResolution,
    TaskAuthorityRead,
    TrustedConfirmationConsumptionReceipt,
    TrustedProductionOriginReceipt,
)
from jiuwenswarm.server.live_voice.task_core import AttemptState, TaskState
from jiuwenswarm.server.live_voice.voice_task_bridge import VoiceTaskBridge

SCOPE = ScopeRef("subject-a", "project-a", "session-a", Assurance.AUTHENTICATED)
CORPUS_DIR = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "live_voice_p3_6_intent_corpus_v1"
)
CORPUS_EVIDENCE_SCOPE = (
    "resolver-policy-only; expected-derived proposals are not classifier evidence"
)
# The preparation oracle predates D-088's claimed/running reprioritize conflict
# and the Tier-3 requirement to validate operation arguments before target
# clarification. Keep those disagreements visible instead of silently treating
# expected-derived proposals as a production classifier or changing the corpus.
CORPUS_POLICY_CORRECTIONS = {
    "p012-reprioritize-natural_text": "TASK_REPRIORITIZE_STATE_CONFLICT",
    "p012-reprioritize-structured": "TASK_REPRIORITIZE_STATE_CONFLICT",
    "p012-reprioritize-voice": "TASK_REPRIORITIZE_STATE_CONFLICT",
    "s012-zero-candidate": "TASK_INTENT_ARGUMENT_SCHEMA_MISMATCH",
    "s013-multiple-candidates": "TASK_INTENT_ARGUMENT_SCHEMA_MISMATCH",
}
ZERO_EFFECTS = (
    "agent_calls",
    "tool_calls",
    "task_writes",
    "attempt_writes",
    "command_writes",
    "event_writes",
    "result_writes",
    "executor_calls",
    "scheduler_calls",
    "file_writes",
    "network_calls",
    "audio_tts_calls",
    "history_writes",
    "presentation_writes",
    "other_scope_writes",
)


def _commit(text: str, *, commit_id: str = "commit-a") -> TurnCommit:
    return TurnCommit.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "commit_id": commit_id,
            "turn_id": f"turn-{commit_id}",
            "interaction_id": "interaction-a",
            "text": text,
            "hypothesis_provenance": {},
            "scope": SCOPE.to_dict(),
            "context_refs": [],
            "committed_at": "2026-08-20T10:00:00Z",
        }
    )


def _fact(
    task_id: str = "task-a",
    *,
    name: str = "Task A",
    state: TaskState = TaskState.ACCEPTED,
    outcome: TerminalOutcome | None = None,
    revision: int = 1,
    capabilities: frozenset[str] = frozenset({"task.cancel"}),
    result_digest: str | None = None,
    decision_event: str | None = None,
    dispatch_state: str = "unclaimed",
    admission_revision: int | None = None,
    successor_task_id: str | None = None,
) -> AuthenticatedTaskFact:
    attempt_state = {
        TaskState.ACCEPTED: AttemptState.ACCEPTED,
        TaskState.RUNNING: AttemptState.RUNNING,
        TaskState.BLOCKED: AttemptState.RUNNING,
        TaskState.DECISION_REQUIRED: AttemptState.RUNNING,
        TaskState.TERMINAL: AttemptState.TERMINAL,
    }[state]
    return AuthenticatedTaskFact(
        task_id=task_id,
        stable_reference=f"ref-{task_id}",
        name=name,
        state=state,
        outcome=outcome,
        revision_number=revision,
        event_head=revision,
        event_head_id=f"event-{task_id}-{revision}",
        terminal_event_id=(
            f"terminal-{task_id}-{revision}" if outcome is not None else None
        ),
        attempt_id=f"attempt-{task_id}",
        attempt_state=attempt_state,
        attempt_outcome=outcome,
        capability_profile_digest="a" * 64,
        supported_operations=capabilities,
        result_digest=result_digest,
        decision_required_event_id=decision_event,
        dispatch_state=dispatch_state,
        admission_revision=admission_revision,
        successor_task_id=successor_task_id,
    )


class RecordingAuthority:
    def __init__(self, facts: tuple[AuthenticatedTaskFact, ...]) -> None:
        self.facts = facts
        self.calls: list[str] = []
        self.changed_get: AuthenticatedTaskFact | None = None
        self.changed_status: AuthenticatedTaskFact | None = None

    def list_visible_tasks(self, scope: ScopeRef) -> TaskAuthorityRead:
        self.calls.append("list")
        return TaskAuthorityRead(scope, "generation-a", self.facts)

    def get_task(self, scope: ScopeRef, task_id: str) -> AuthenticatedTaskFact | None:
        self.calls.append("get")
        return self.changed_get or next(
            (fact for fact in self.facts if fact.task_id == task_id), None
        )

    def task_status(
        self, scope: ScopeRef, task_id: str
    ) -> AuthenticatedTaskFact | None:
        self.calls.append("status")
        return self.changed_status or next(
            (fact for fact in self.facts if fact.task_id == task_id), None
        )

    def event_head(self, scope: ScopeRef, task_id: str) -> tuple[int, str]:
        self.calls.append("events")
        fact = next(fact for fact in self.facts if fact.task_id == task_id)
        return fact.event_head, fact.event_head_id

    def result_digest(self, scope: ScopeRef, task_id: str) -> str | None:
        self.calls.append("result")
        return next(
            fact for fact in self.facts if fact.task_id == task_id
        ).result_digest

    def unread_head(self, scope: ScopeRef, task_id: str) -> tuple[int, str] | None:
        self.calls.append("unread")
        return None


class AcceptedOriginAuthority:
    def __init__(self) -> None:
        self.commits: dict[str, TurnCommit] = {}
        self.calls: list[ProductionOriginBinding] = []

    def accept(self, commit: TurnCommit) -> None:
        self.commits[commit.commit_id] = commit

    def verify_origin(
        self, binding: ProductionOriginBinding
    ) -> TrustedProductionOriginReceipt:
        self.calls.append(binding)
        if binding.origin is not ProductionIntentOrigin.STRUCTURED:
            commit = self.commits.get(binding.commit_id or "")
            if commit is None:
                raise ValueError("unaccepted origin")
            if (
                hashlib.sha256(commit.canonical_bytes()).hexdigest()
                != binding.commit_sha256
            ):
                raise ValueError("changed origin")
            for extraction in binding.extractions:
                content = commit.text[extraction.source_start : extraction.source_end]
                if (
                    hashlib.sha256(content.encode()).hexdigest()
                    != extraction.content_sha256
                ):
                    raise ValueError("changed extraction")
        return TrustedProductionOriginReceipt(
            f"origin-{binding.source_id}",
            binding.principal_id,
            binding.fingerprint,
        )


class ExactConfirmationConsumer:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject
        self.calls: list[ProductionConfirmationBinding] = []
        self.consumed: set[str] = set()

    def verify_and_consume(
        self, confirmation_id: str, binding: ProductionConfirmationBinding
    ) -> TrustedConfirmationConsumptionReceipt:
        self.calls.append(binding)
        if self.reject:
            raise ValueError("confirmation binding mismatch")
        replayed = confirmation_id in self.consumed
        self.consumed.add(confirmation_id)
        return TrustedConfirmationConsumptionReceipt(
            confirmation_id,
            f"consumption-{len(self.calls)}",
            binding.fingerprint,
            replayed,
        )


def _extractions(
    proposal: ProductionTaskIntentProposal, text: str
) -> tuple[ProductionFieldExtraction, ...]:
    fields = ["dialogue"] if proposal.operation is None else ["operation"]
    if proposal.operation is not None and proposal.target is not None:
        fields.append("target")
    if proposal.operation is not None:
        fields.extend(f"arguments.{key}" for key in proposal.arguments)
    return tuple(ProductionFieldExtraction(field, 0, len(text)) for field in fields)


def _request(
    proposal: ProductionTaskIntentProposal,
    origin_authority: AcceptedOriginAuthority,
    *,
    origin: ProductionIntentOrigin = ProductionIntentOrigin.NATURAL_TEXT,
    text: str = "task intent",
    commit_id: str = "commit-a",
    command_id: str = "command-a",
    clarification_answer: ClarificationAnswer | None = None,
    confirmation_id: str | None = None,
) -> ProductionTaskIntentRequest:
    if origin is ProductionIntentOrigin.STRUCTURED:
        return ProductionTaskIntentRequest(
            origin,
            SCOPE,
            command_id,
            proposal,
            source_id=commit_id,
            clarification_answer=clarification_answer,
            confirmation_id=confirmation_id,
        )
    if proposal.committed:
        proposal = replace(proposal, extractions=_extractions(proposal, text))
    commit = _commit(text, commit_id=commit_id)
    origin_authority.accept(commit)
    return ProductionTaskIntentRequest(
        origin,
        SCOPE,
        command_id,
        proposal,
        commit,
        source_id=commit_id,
        clarification_answer=clarification_answer,
        confirmation_id=confirmation_id,
    )


def _resolve(
    request: ProductionTaskIntentRequest,
    authority: RecordingAuthority,
    origin_authority: AcceptedOriginAuthority,
    confirmation: ExactConfirmationConsumer | None = None,
    clarifications: BoundedClarificationOwner | None = None,
) -> ProductionTaskResolution:
    return VoiceTaskBridge().resolve_production(
        request,
        authority,
        origin_authority,
        confirmation or ExactConfirmationConsumer(),
        clarifications or BoundedClarificationOwner(boot_id="boot-a", capacity=64),
    )


def test_actual_voice_task_bridge_path_rereads_authenticated_core_facts() -> None:
    fact = _fact()
    authority = RecordingAuthority((fact,))
    origin = AcceptedOriginAuthority()
    request = _request(
        ProductionTaskIntentProposal(
            "task.status",
            fact.task_id,
            {"query_kind": "status"},
            1.0,
            True,
            target_kind="task_id",
        ),
        origin,
        text="status task-a",
    )

    result = _resolve(request, authority, origin)

    assert result.outcome is ProductionTaskPolicyOutcome.PROPOSED
    assert authority.calls == ["list", "get", "status"]
    assert result.origin_receipt_id == "origin-commit-a"
    assert result.origin_binding_fingerprint == origin.calls[0].fingerprint
    assert result.origin_binding == origin.calls[0]
    assert result.origin_binding.commit_id == "commit-a"
    commit = request.commit
    assert commit is not None
    assert (
        result.origin_binding.commit_sha256
        == hashlib.sha256(commit.canonical_bytes()).hexdigest()
    )
    assert {item.field_name for item in result.origin_binding.extractions} == {
        "operation",
        "target",
        "arguments.query_kind",
    }
    assert all(
        item.content_sha256 != item.value_sha256
        for item in result.origin_binding.extractions
    )
    assert result.zero_effects == ZERO_EFFECTS


@pytest.mark.parametrize("origin_kind", list(ProductionIntentOrigin))
def test_natural_voice_and_structured_share_closed_policy(
    origin_kind: ProductionIntentOrigin,
) -> None:
    fact = _fact()
    authority = RecordingAuthority((fact,))
    origin = AcceptedOriginAuthority()
    proposal = ProductionTaskIntentProposal(
        "task.status",
        fact.stable_reference,
        {"query_kind": "status"},
        1.0,
        True,
        target_kind="stable_reference",
    )

    result = _resolve(
        _request(proposal, origin, origin=origin_kind, text="status ref-task-a"),
        authority,
        origin,
    )

    assert result.canonical_policy_tuple() == (
        "task_intent",
        "task.status",
        "task-a",
        canonical_json_bytes({"query_kind": "status"}),
        "not_required",
        "proposed",
    )


def test_partial_input_has_no_authority_or_interaction_calls() -> None:
    authority = RecordingAuthority((_fact(),))
    origin = AcceptedOriginAuthority()
    confirmation = ExactConfirmationConsumer()
    clarifications = BoundedClarificationOwner(boot_id="boot-a", capacity=8)
    proposal = ProductionTaskIntentProposal(None, None, {}, 1.0, False)
    request = _request(proposal, origin, text="partial")

    result = _resolve(request, authority, origin, confirmation, clarifications)

    assert result.outcome is ProductionTaskPolicyOutcome.REJECTED
    assert authority.calls == origin.calls == confirmation.calls == []
    assert result.zero_effects == ZERO_EFFECTS


def test_structured_ambiguity_uses_same_bounded_clarification_owner() -> None:
    authority = RecordingAuthority((_fact("x"), _fact("y")))
    origin = AcceptedOriginAuthority()
    owner = BoundedClarificationOwner(boot_id="boot-a", capacity=8)
    proposal = ProductionTaskIntentProposal(
        "task.status",
        "current",
        {"query_kind": "status"},
        1.0,
        True,
        target_kind="hint",
    )

    result = _resolve(
        _request(
            proposal,
            origin,
            origin=ProductionIntentOrigin.STRUCTURED,
            commit_id="structured-a",
        ),
        authority,
        origin,
        clarifications=owner,
    )

    assert result.outcome is ProductionTaskPolicyOutcome.CLARIFICATION
    assert result.candidate_task_ids == ("x", "y")
    assert result.clarification_handle_id is not None


def test_target_reread_and_observed_revision_fail_closed() -> None:
    fact = _fact(revision=2)
    authority = RecordingAuthority((fact,))
    origin = AcceptedOriginAuthority()
    proposal = ProductionTaskIntentProposal(
        "task.status",
        fact.task_id,
        {"query_kind": "status"},
        1.0,
        True,
        target_kind="task_id",
        observed_task_revision=1,
    )

    stale = _resolve(
        _request(proposal, origin, text="status task-a"), authority, origin
    )
    authority.changed_get = _fact(revision=3)
    changed = _resolve(
        _request(
            replace(proposal, observed_task_revision=2),
            origin,
            text="status task-a",
            commit_id="commit-b",
            command_id="command-b",
        ),
        authority,
        origin,
    )

    assert stale.reason == "TASK_SNAPSHOT_STALE"
    assert changed.reason == "TASK_AUTHORITY_CHANGED"
    assert stale.zero_effects == changed.zero_effects == ZERO_EFFECTS


def test_clarification_is_new_commit_single_use_and_restart_invalidates() -> None:
    authority = RecordingAuthority((_fact("x"), _fact("y")))
    origin = AcceptedOriginAuthority()
    owner = BoundedClarificationOwner(
        boot_id="boot-a", capacity=4, per_subject_capacity=2
    )
    proposal = ProductionTaskIntentProposal(
        "task.status",
        "current",
        {"query_kind": "status"},
        1.0,
        True,
        target_kind="hint",
    )
    issued = _resolve(
        _request(proposal, origin, text="status current"),
        authority,
        origin,
        clarifications=owner,
    )
    assert issued.clarification_handle_id is not None
    assert issued.clarification_generation is not None
    answer = ClarificationAnswer(
        issued.clarification_handle_id,
        issued.clarification_generation,
        "x",
        issued.task_set_fingerprint or "",
    )
    answer_proposal = replace(proposal, target="x", target_kind="task_id")
    request = _request(
        answer_proposal,
        origin,
        text="choose x",
        commit_id="commit-b",
        command_id="command-b",
        clarification_answer=answer,
    )

    consumed = _resolve(request, authority, origin, clarifications=owner)
    replay = _resolve(request, authority, origin, clarifications=owner)
    owner.restart("boot-b")
    after_restart = _resolve(request, authority, origin, clarifications=owner)

    assert consumed.target_task_id == "x"
    assert origin.calls[-1].clarification_answer_sha256 == answer.fingerprint
    assert replay.reason == "CLARIFICATION_BINDING_CONFLICT"
    assert after_restart.reason == "CLARIFICATION_BINDING_CONFLICT"


def test_clarification_is_per_subject_bounded_and_never_evicts() -> None:
    authority = RecordingAuthority((_fact("x"), _fact("y")))
    origin = AcceptedOriginAuthority()
    owner = BoundedClarificationOwner(
        boot_id="boot-a", capacity=3, per_subject_capacity=1
    )
    proposal = ProductionTaskIntentProposal(
        "task.status",
        "current",
        {"query_kind": "status"},
        1.0,
        True,
        target_kind="hint",
    )
    first = _resolve(
        _request(proposal, origin, text="status", commit_id="commit-a"),
        authority,
        origin,
        clarifications=owner,
    )
    overflow = _resolve(
        _request(
            proposal,
            origin,
            text="status again",
            commit_id="commit-b",
            command_id="command-b",
        ),
        authority,
        origin,
        clarifications=owner,
    )

    assert first.outcome is ProductionTaskPolicyOutcome.CLARIFICATION
    assert overflow.reason == "CLARIFICATION_UNAVAILABLE"


def test_clarification_changed_authorized_task_set_conflicts_without_consuming() -> (
    None
):
    original_facts = (_fact("x"), _fact("y"))
    authority = RecordingAuthority(original_facts)
    origin = AcceptedOriginAuthority()
    owner = BoundedClarificationOwner(boot_id="boot-a", capacity=4)
    proposal = ProductionTaskIntentProposal(
        "task.status",
        "current",
        {"query_kind": "status"},
        1.0,
        True,
        target_kind="hint",
    )
    issued = _resolve(
        _request(proposal, origin, text="status current"),
        authority,
        origin,
        clarifications=owner,
    )
    assert issued.clarification_handle_id is not None
    assert issued.clarification_generation is not None
    assert issued.task_set_fingerprint is not None
    answer = ClarificationAnswer(
        issued.clarification_handle_id,
        issued.clarification_generation,
        "x",
        issued.task_set_fingerprint,
    )
    answer_proposal = replace(proposal, target="x", target_kind="task_id")
    request = _request(
        answer_proposal,
        origin,
        text="choose x",
        commit_id="commit-b",
        command_id="command-b",
        clarification_answer=answer,
    )
    authority.facts = (*original_facts, _fact("z"))

    changed = _resolve(request, authority, origin, clarifications=owner)
    authority.facts = original_facts
    recovered = _resolve(request, authority, origin, clarifications=owner)

    assert changed.reason == "CLARIFICATION_BINDING_CONFLICT"
    assert changed.zero_effects == ZERO_EFFECTS
    assert recovered.target_task_id == "x"


def test_clarification_owner_expiry_is_fail_closed() -> None:
    owner = BoundedClarificationOwner(
        boot_id="boot-a", capacity=2, ttl=timedelta(seconds=1)
    )
    source = ProductionOriginBinding(
        SCOPE.subject_id,
        SCOPE,
        ProductionIntentOrigin.STRUCTURED,
        "structured-source",
        None,
        None,
        (),
    )
    source_receipt = TrustedProductionOriginReceipt(
        "source-receipt", SCOPE.subject_id, source.fingerprint
    )
    now = datetime(2026, 8, 20, 10, tzinfo=UTC)
    handle = owner.issue(
        origin_binding=source,
        origin_receipt=source_receipt,
        operation="task.status",
        arguments={"query_kind": "status"},
        ambiguous_fields=("target",),
        candidate_task_ids=("x",),
        task_set_fingerprint="d" * 64,
        now=now,
    )
    answer_origin = ProductionOriginBinding(
        SCOPE.subject_id,
        SCOPE,
        ProductionIntentOrigin.NATURAL_TEXT,
        "answer-source",
        "answer-commit",
        "e" * 64,
        (),
    )
    answer_receipt = TrustedProductionOriginReceipt(
        "answer-receipt", SCOPE.subject_id, answer_origin.fingerprint
    )

    with pytest.raises(ValueError, match="CLARIFICATION_HANDLE_EXPIRED"):
        owner.consume(
            ClarificationAnswer(handle.handle_id, handle.generation, "x", "d" * 64),
            answer_origin=answer_origin,
            answer_receipt=answer_receipt,
            operation="task.status",
            arguments={"query_kind": "status"},
            task_set_fingerprint="d" * 64,
            now=now + timedelta(seconds=2),
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


def _corpus_fact(raw: dict[str, object]) -> AuthenticatedTaskFact:
    raw_state = str(raw["state"])
    terminal = bool(raw["terminal"])
    outcome = TerminalOutcome(raw_state) if terminal else None
    state = (
        TaskState.TERMINAL
        if terminal
        else TaskState.DECISION_REQUIRED
        if bool(raw["decision_required_event_current"])
        else TaskState(raw_state)
    )
    capabilities = {"task.cancel"}
    if state is TaskState.RUNNING:
        capabilities.add("task.adjust")
    if state is TaskState.ACCEPTED and raw["dispatch_outbox_state"] == "unclaimed":
        capabilities.add("task.update")
    result_digest = "b" * 64 if outcome is TerminalOutcome.COMPLETED else None
    return _fact(
        str(raw["task_id"]),
        name=str(raw["name"]),
        state=state,
        outcome=outcome,
        revision=int(raw["snapshot_version"]),
        capabilities=frozenset(capabilities),
        result_digest=result_digest,
        decision_event=(
            str(raw["decision_required_event_id"])
            if raw["decision_required_event_id"] is not None
            else None
        ),
        dispatch_state=str(raw["dispatch_outbox_state"]),
    )


def _from_corpus_case(
    case: dict[str, object],
) -> tuple[
    RecordingAuthority,
    AcceptedOriginAuthority,
    ExactConfirmationConsumer,
    BoundedClarificationOwner,
    ProductionTaskIntentRequest,
]:
    raw_facts = case["task_facts"]
    assert isinstance(raw_facts, list)
    facts = tuple(_corpus_fact(raw) for raw in raw_facts if isinstance(raw, dict))
    authority = RecordingAuthority(facts)
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
        matching = next((fact for fact in facts if fact.task_id == target_id), None)
        if target_partition == "collection":
            target = None
        elif target_partition == "explicit_task_id":
            target = str(target_id) if target_id else "foreign"
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
            target = "foreign"
        else:
            target = None
        target_kind = (
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
        )
        snapshot = case.get("target_snapshot")
        proposal = ProductionTaskIntentProposal(
            str(operation),
            target,
            expected["arguments"],
            float(case["confidence"]),
            bool(case["committed"]),
            target_kind=target_kind,
            observed_task_revision=(
                int(snapshot["observed_snapshot_version"])
                if isinstance(snapshot, dict)
                else None
            ),
        )

    origin_authority = AcceptedOriginAuthority()
    origin_kind = ProductionIntentOrigin(str(case["origin"]))
    clarification_answer = None
    confirmation_id = None
    context = case.get("interaction_context")
    confirmation = ExactConfirmationConsumer()
    if isinstance(context, dict) and context["kind"] == "clarification":
        current = authority.list_visible_tasks(SCOPE)
        authority.calls.clear()
        clarification_answer = ClarificationAnswer(
            str(context["context_id"]),
            1,
            str(context["bound_candidate_task_ids"][0]),
            "d" * 64
            if "changed_task_set" in set(partitions["safety"])
            else current.fingerprint,
        )
    elif isinstance(context, dict) and context["kind"] == "confirmation":
        confirmation_id = str(context["context_id"])
        confirmation = ExactConfirmationConsumer(reject=True)
    request = _request(
        proposal,
        origin_authority,
        origin=origin_kind,
        text=str(case["input_text"]),
        commit_id=str(case["case_id"]),
        command_id=f"command-{case['case_id']}",
        clarification_answer=clarification_answer,
        confirmation_id=confirmation_id,
    )
    return (
        authority,
        origin_authority,
        confirmation,
        BoundedClarificationOwner(boot_id="corpus-boot", capacity=128),
        request,
    )


def test_all_68_cases_and_14_groups_are_resolver_policy_only_evidence() -> None:
    """Evaluate supplied proposals, never claim production classifier accuracy."""

    assert CORPUS_EVIDENCE_SCOPE.startswith("resolver-policy-only")
    cases = [
        json.loads(line)
        for line in (CORPUS_DIR / "cases.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(cases) == 68
    assert len({case["parity_group"] for case in cases if case["parity_group"]}) == 14

    actual: dict[str, ProductionTaskResolution] = {}
    observed_corrections: set[str] = set()
    for case in cases:
        authority, origin, confirmation, clarifications, request = _from_corpus_case(
            case
        )
        result = _resolve(request, authority, origin, confirmation, clarifications)
        actual[case["case_id"]] = result
        if not _matches_expected(result, case["expected"]):
            observed_corrections.add(case["case_id"])
            assert result.reason == CORPUS_POLICY_CORRECTIONS[case["case_id"]]
            assert result.outcome in {
                ProductionTaskPolicyOutcome.REJECTED,
                ProductionTaskPolicyOutcome.CONFLICT,
            }
        assert result.zero_effects == tuple(case["expected"]["zero_effects"])

    groups = {case["parity_group"] for case in cases if case["parity_group"]}
    assert observed_corrections == set(CORPUS_POLICY_CORRECTIONS)
    for group in groups:
        members = [case for case in cases if case["parity_group"] == group]
        assert (
            len({actual[case["case_id"]].canonical_policy_tuple() for case in members})
            == 1
        )
