"""Executable trust-boundary regressions from the P3-6 Tier-3 review."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CONTRACT_VERSION,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
)
from jiuwenswarm.server.live_voice.production_task_intent import (
    AuthenticatedTaskFact,
    BoundedClarificationOwner,
    ClarificationAnswer,
    ProductionConfirmationBinding,
    ProductionFieldExtraction,
    ProductionIntentOrigin,
    ProductionMultiTaskResolver,
    ProductionOriginBinding,
    ProductionTaskIntentProposal,
    ProductionTaskIntentRequest,
    ProductionTaskPolicyOutcome,
    TaskAuthorityRead,
    TrustedConfirmationConsumptionReceipt,
    TrustedProductionOriginReceipt,
)
from jiuwenswarm.server.live_voice.task_core import AttemptState, TaskState
from jiuwenswarm.server.live_voice.voice_task_bridge import VoiceTaskBridge

SCOPE = ScopeRef("subject-a", "project-a", "session-a", Assurance.AUTHENTICATED)
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


def _commit(text: str, commit_id: str = "commit-a") -> TurnCommit:
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
    state: TaskState = TaskState.ACCEPTED,
    outcome: TerminalOutcome | None = None,
    capabilities: frozenset[str] = frozenset({"task.cancel"}),
    dispatch_state: str = "unclaimed",
    decision_event: str | None = None,
    result_digest: str | None = None,
    name: str = "Task A",
    admission_revision: int | None = None,
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
        revision_number=1,
        event_head=1,
        event_head_id=f"event-{task_id}",
        terminal_event_id=f"terminal-{task_id}" if outcome is not None else None,
        attempt_id=f"attempt-{task_id}",
        attempt_state=attempt_state,
        attempt_outcome=outcome,
        capability_profile_digest="a" * 64,
        supported_operations=capabilities,
        result_digest=result_digest,
        decision_required_event_id=decision_event,
        dispatch_state=dispatch_state,
        admission_revision=admission_revision,
    )


class RecordingAuthority:
    def __init__(self, *facts: AuthenticatedTaskFact) -> None:
        self.facts = facts
        self.read_calls: list[str] = []
        self.mutation_calls = 0

    def list_visible_tasks(self, scope: ScopeRef) -> TaskAuthorityRead:
        self.read_calls.append("list")
        return TaskAuthorityRead(scope, "generation-a", self.facts)

    def get_task(self, scope: ScopeRef, task_id: str) -> AuthenticatedTaskFact | None:
        self.read_calls.append("get")
        return next((fact for fact in self.facts if fact.task_id == task_id), None)

    def task_status(
        self, scope: ScopeRef, task_id: str
    ) -> AuthenticatedTaskFact | None:
        self.read_calls.append("status")
        return next((fact for fact in self.facts if fact.task_id == task_id), None)

    def event_head(self, scope: ScopeRef, task_id: str) -> tuple[int, str]:
        self.read_calls.append("events")
        fact = next(fact for fact in self.facts if fact.task_id == task_id)
        return fact.event_head, fact.event_head_id

    def result_digest(self, scope: ScopeRef, task_id: str) -> str | None:
        self.read_calls.append("result")
        return next(
            fact for fact in self.facts if fact.task_id == task_id
        ).result_digest

    def unread_head(self, scope: ScopeRef, task_id: str) -> tuple[int, str] | None:
        self.read_calls.append("unread")
        return None


class RecordingOriginAuthority:
    def __init__(self) -> None:
        self.commits: dict[str, TurnCommit] = {}
        self.calls: list[ProductionOriginBinding] = []

    def accept(self, commit: TurnCommit) -> None:
        self.commits[commit.commit_id] = commit

    def verify_origin(
        self, binding: ProductionOriginBinding
    ) -> TrustedProductionOriginReceipt:
        self.calls.append(binding)
        if binding.origin is ProductionIntentOrigin.STRUCTURED:
            return TrustedProductionOriginReceipt(
                f"origin-{binding.source_id}",
                binding.principal_id,
                binding.fingerprint,
            )
        commit = self.commits.get(binding.commit_id or "")
        if commit is None:
            raise ValueError("unaccepted commit")
        if (
            hashlib.sha256(commit.canonical_bytes()).hexdigest()
            != binding.commit_sha256
        ):
            raise ValueError("changed commit")
        for extraction in binding.extractions:
            content = commit.text[extraction.source_start : extraction.source_end]
            if (
                hashlib.sha256(content.encode()).hexdigest()
                != extraction.content_sha256
            ):
                raise ValueError("changed extraction")
            if extraction.field_name == "operation" and content == "intent":
                raise ValueError("operation span is not classifier-attested")
        return TrustedProductionOriginReceipt(
            f"origin-{commit.commit_id}",
            binding.principal_id,
            binding.fingerprint,
        )


class RecordingConfirmationConsumer:
    def __init__(self) -> None:
        self.calls: list[ProductionConfirmationBinding] = []
        self._consumed: dict[str, str] = {}

    def verify_and_consume(
        self, confirmation_id: str, binding: ProductionConfirmationBinding
    ) -> TrustedConfirmationConsumptionReceipt:
        self.calls.append(binding)
        prior = self._consumed.get(confirmation_id)
        replayed = prior is not None
        if prior is not None and prior != binding.fingerprint:
            raise ValueError("changed confirmation")
        self._consumed[confirmation_id] = binding.fingerprint
        return TrustedConfirmationConsumptionReceipt(
            confirmation_id,
            f"consumption-{len(self.calls)}",
            binding.fingerprint,
            replayed,
        )


class RecordingClarificationOwner(BoundedClarificationOwner):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.issue_calls = 0
        self.consume_calls = 0

    def issue(self, **kwargs: object):
        self.issue_calls += 1
        return super().issue(**kwargs)

    def consume(self, answer: ClarificationAnswer, **kwargs: object) -> str:
        self.consume_calls += 1
        return super().consume(answer, **kwargs)


def _proposal(
    operation: str,
    target: str | None,
    arguments: dict[str, object],
    text: str,
    *,
    operation_span: tuple[int, int] | None = None,
) -> ProductionTaskIntentProposal:
    fields = ["operation"]
    if target is not None:
        fields.append("target")
    fields.extend(f"arguments.{key}" for key in arguments)
    extractions = []
    for field in fields:
        start, end = (0, len(text))
        if field == "operation" and operation_span is not None:
            start, end = operation_span
        extractions.append(ProductionFieldExtraction(field, start, end))
    return ProductionTaskIntentProposal(
        operation,
        target,
        arguments,
        1.0,
        True,
        target_kind=None if target is None else "task_id",
        extractions=tuple(extractions),
    )


def _request(
    proposal: ProductionTaskIntentProposal,
    origin_authority: RecordingOriginAuthority,
    *,
    text: str,
    commit_id: str = "commit-a",
    command_id: str = "command-a",
    confirmation_id: str | None = None,
    clarification_answer: ClarificationAnswer | None = None,
) -> ProductionTaskIntentRequest:
    commit = _commit(text, commit_id)
    origin_authority.accept(commit)
    return ProductionTaskIntentRequest(
        ProductionIntentOrigin.NATURAL_TEXT,
        SCOPE,
        command_id,
        proposal,
        commit,
        clarification_answer=clarification_answer,
        confirmation_id=confirmation_id,
    )


def _resolve(
    request: ProductionTaskIntentRequest,
    authority: RecordingAuthority,
    origin: RecordingOriginAuthority,
    confirmation: RecordingConfirmationConsumer,
    clarifications: RecordingClarificationOwner,
):
    return ProductionMultiTaskResolver(clarifications).resolve(
        request, authority, origin, confirmation
    )


def _assert_no_effects(result, authority: RecordingAuthority) -> None:
    assert result.zero_effects == ZERO_EFFECTS
    assert authority.mutation_calls == 0


def test_confirmation_is_consumed_by_port_once_and_proposal_has_no_fact() -> None:
    authority = RecordingAuthority(_fact())
    origin = RecordingOriginAuthority()
    confirmation = RecordingConfirmationConsumer()
    clarifications = RecordingClarificationOwner(boot_id="boot-a", capacity=8)
    text = "cancel task-a"
    proposal = _proposal("task.cancel", "task-a", {}, text)
    assert not hasattr(proposal, "confirmation")
    request = _request(proposal, origin, text=text, confirmation_id="confirmation-a")

    first = _resolve(request, authority, origin, confirmation, clarifications)
    second = _resolve(request, authority, origin, confirmation, clarifications)

    assert first.confirmation == "confirmed"
    assert first.confirmation_consumption_id == "consumption-1"
    exact_binding = confirmation.calls[0]
    assert exact_binding.principal_id == SCOPE.subject_id
    assert exact_binding.scope == SCOPE
    assert exact_binding.command_id == "command-a"
    assert exact_binding.origin is ProductionIntentOrigin.NATURAL_TEXT
    assert exact_binding.origin_receipt_id == first.origin_receipt_id
    assert exact_binding.origin_binding_fingerprint == first.origin_binding_fingerprint
    assert exact_binding.operation == "task.cancel"
    assert exact_binding.target_task_id == "task-a"
    assert exact_binding.arguments_sha256 == hashlib.sha256(b"{}").hexdigest()
    assert exact_binding.task_set_fingerprint == first.task_set_fingerprint
    assert exact_binding.capability_profile_digest == "a" * 64
    assert second.outcome is ProductionTaskPolicyOutcome.CONFLICT
    assert second.reason == "CONFIRMATION_BINDING_CONFLICT"
    assert len(confirmation.calls) == 2
    assert clarifications.consume_calls == 0
    _assert_no_effects(first, authority)
    _assert_no_effects(second, authority)


def test_bridge_cannot_skip_any_trusted_port() -> None:
    authority = RecordingAuthority(_fact())
    origin = RecordingOriginAuthority()
    text = "status task-a"
    proposal = _proposal("task.status", "task-a", {"query_kind": "status"}, text)
    request = _request(proposal, origin, text=text)

    with pytest.raises(TypeError):
        getattr(VoiceTaskBridge(), "resolve_production")(request, authority)

    assert authority.read_calls == []


def test_forged_clarification_id_fails_closed_without_confirmation_or_effect() -> None:
    fact = _fact()
    authority = RecordingAuthority(fact)
    visible = authority.list_visible_tasks(SCOPE)
    authority.read_calls.clear()
    origin = RecordingOriginAuthority()
    confirmation = RecordingConfirmationConsumer()
    clarifications = RecordingClarificationOwner(boot_id="boot-a", capacity=8)
    text = "status task-a"
    proposal = _proposal("task.status", "task-a", {"query_kind": "status"}, text)
    request = _request(
        proposal,
        origin,
        text=text,
        clarification_answer=ClarificationAnswer(
            "forged-handle", 1, "task-a", visible.fingerprint
        ),
    )

    result = _resolve(request, authority, origin, confirmation, clarifications)

    assert result.outcome is ProductionTaskPolicyOutcome.CONFLICT
    assert result.reason == "CLARIFICATION_BINDING_CONFLICT"
    assert clarifications.consume_calls == 1
    assert confirmation.calls == []
    assert authority.read_calls == ["list"]
    _assert_no_effects(result, authority)


def test_unrelated_intent_span_cannot_authorize_cancel() -> None:
    authority = RecordingAuthority(_fact())
    origin = RecordingOriginAuthority()
    confirmation = RecordingConfirmationConsumer()
    clarifications = RecordingClarificationOwner(boot_id="boot-a", capacity=8)
    text = "intent ... cancel task-a"
    proposal = _proposal("task.cancel", "task-a", {}, text, operation_span=(0, 6))

    result = _resolve(
        _request(proposal, origin, text=text),
        authority,
        origin,
        confirmation,
        clarifications,
    )

    assert result.outcome is ProductionTaskPolicyOutcome.REJECTED
    assert result.reason == "ORIGIN_AUTHORITY_REJECTED"
    assert authority.read_calls == []
    assert confirmation.calls == []
    assert clarifications.issue_calls == clarifications.consume_calls == 0
    _assert_no_effects(result, authority)


def test_foreign_task_authority_scope_never_reaches_target_or_interaction_ports() -> (
    None
):
    foreign_scope = ScopeRef(
        "subject-foreign",
        "project-foreign",
        "session-foreign",
        Assurance.AUTHENTICATED,
    )

    class ForeignAuthority(RecordingAuthority):
        def list_visible_tasks(self, scope: ScopeRef) -> TaskAuthorityRead:
            self.read_calls.append("list")
            return TaskAuthorityRead(foreign_scope, "foreign-generation", self.facts)

    authority = ForeignAuthority(_fact())
    origin = RecordingOriginAuthority()
    confirmation = RecordingConfirmationConsumer()
    clarifications = RecordingClarificationOwner(boot_id="boot-a", capacity=8)
    text = "status task-a"
    proposal = _proposal("task.status", "task-a", {"query_kind": "status"}, text)

    result = _resolve(
        _request(proposal, origin, text=text),
        authority,
        origin,
        confirmation,
        clarifications,
    )

    assert result.outcome is ProductionTaskPolicyOutcome.REJECTED
    assert result.reason == "TASK_AUTHORITY_SCOPE_MISMATCH"
    assert authority.read_calls == ["list"]
    assert confirmation.calls == []
    assert clarifications.issue_calls == clarifications.consume_calls == 0
    _assert_no_effects(result, authority)


def test_canonical_failed_successor_and_opaque_short_id_are_legal() -> None:
    failed = _fact(
        "x",
        state=TaskState.TERMINAL,
        outcome=TerminalOutcome.FAILED,
        capabilities=frozenset({"task.create_successor"}),
        result_digest=None,
        dispatch_state="none",
    )
    authority = RecordingAuthority(failed)
    origin = RecordingOriginAuthority()
    confirmation = RecordingConfirmationConsumer()
    clarifications = RecordingClarificationOwner(boot_id="boot-a", capacity=8)
    text = "successor x"
    proposal = _proposal(
        "task.create_successor",
        "x",
        {"name": "Next", "instruction": "Continue safely"},
        text,
    )

    result = _resolve(
        _request(proposal, origin, text=text),
        authority,
        origin,
        confirmation,
        clarifications,
    )

    assert failed.state is TaskState.TERMINAL
    assert failed.outcome is TerminalOutcome.FAILED
    assert result.outcome is ProductionTaskPolicyOutcome.PROPOSED
    assert result.predecessor_result_digest is None
    assert authority.read_calls == ["list", "get", "status", "result"]
    assert confirmation.calls == []
    assert clarifications.issue_calls == clarifications.consume_calls == 0
    _assert_no_effects(result, authority)


@pytest.mark.parametrize(
    "outcome",
    (
        TerminalOutcome.FAILED,
        TerminalOutcome.CANCELLED,
        TerminalOutcome.INTERRUPTED,
    ),
)
def test_noncompleted_terminal_task_result_is_illegal(
    outcome: TerminalOutcome,
) -> None:
    with pytest.raises(ValueError, match="NONCOMPLETED_RESULT_FORBIDDEN"):
        _fact(
            "x",
            state=TaskState.TERMINAL,
            outcome=outcome,
            result_digest="b" * 64,
            dispatch_state="none",
        )


def test_completed_terminal_requires_canonical_result_digest() -> None:
    with pytest.raises(ValueError, match="COMPLETED_RESULT_REQUIRED"):
        _fact(
            "x",
            state=TaskState.TERMINAL,
            outcome=TerminalOutcome.COMPLETED,
            dispatch_state="none",
        )


@pytest.mark.parametrize(
    ("operation", "arguments", "fact", "reason"),
    [
        (
            "task.list",
            {"query_kind": "list", "limit": -100},
            _fact(),
            "TASK_QUERY_LIMIT_INVALID",
        ),
        (
            "task.reprioritize",
            {"priority": "root"},
            _fact(
                capabilities=frozenset({"task.reprioritize"}),
                admission_revision=1,
            ),
            "TASK_PRIORITY_INVALID",
        ),
    ],
)
def test_invalid_values_reject_before_task_or_interaction_authority(
    operation: str,
    arguments: dict[str, object],
    fact: AuthenticatedTaskFact,
    reason: str,
) -> None:
    authority = RecordingAuthority(fact)
    origin = RecordingOriginAuthority()
    confirmation = RecordingConfirmationConsumer()
    clarifications = RecordingClarificationOwner(boot_id="boot-a", capacity=8)
    text = f"{operation} intent"
    proposal = _proposal(
        operation, None if operation == "task.list" else fact.task_id, arguments, text
    )

    result = _resolve(
        _request(proposal, origin, text=text),
        authority,
        origin,
        confirmation,
        clarifications,
    )

    assert result.outcome is ProductionTaskPolicyOutcome.REJECTED
    assert result.reason == reason
    assert authority.read_calls == []
    assert confirmation.calls == []
    assert clarifications.issue_calls == clarifications.consume_calls == 0
    _assert_no_effects(result, authority)


@pytest.mark.parametrize(
    "fact",
    [
        _fact(
            capabilities=frozenset({"task.reprioritize"}),
            dispatch_state="claimed",
            admission_revision=1,
        ),
        _fact(
            state=TaskState.RUNNING,
            capabilities=frozenset({"task.reprioritize"}),
            admission_revision=1,
        ),
    ],
)
def test_claimed_or_running_reprioritize_is_state_conflict(
    fact: AuthenticatedTaskFact,
) -> None:
    authority = RecordingAuthority(fact)
    origin = RecordingOriginAuthority()
    confirmation = RecordingConfirmationConsumer()
    clarifications = RecordingClarificationOwner(boot_id="boot-a", capacity=8)
    text = "reprioritize task-a high"
    proposal = _proposal("task.reprioritize", fact.task_id, {"priority": "high"}, text)

    result = _resolve(
        _request(proposal, origin, text=text),
        authority,
        origin,
        confirmation,
        clarifications,
    )

    assert result.outcome is ProductionTaskPolicyOutcome.CONFLICT
    assert result.reason == "TASK_REPRIORITIZE_STATE_CONFLICT"
    assert confirmation.calls == []
    assert clarifications.issue_calls == clarifications.consume_calls == 0
    _assert_no_effects(result, authority)


def test_queued_reprioritize_requires_real_admission_capability_and_confirmation() -> (
    None
):
    fact = _fact(
        capabilities=frozenset({"task.reprioritize"}),
        admission_revision=1,
    )
    authority = RecordingAuthority(fact)
    origin = RecordingOriginAuthority()
    confirmation = RecordingConfirmationConsumer()
    clarifications = RecordingClarificationOwner(boot_id="boot-a", capacity=8)
    text = "reprioritize task-a high"
    proposal = _proposal("task.reprioritize", fact.task_id, {"priority": "high"}, text)

    result = _resolve(
        _request(proposal, origin, text=text),
        authority,
        origin,
        confirmation,
        clarifications,
    )

    assert result.outcome is ProductionTaskPolicyOutcome.PROPOSED
    assert result.confirmation == "required"
    assert confirmation.calls == []
    _assert_no_effects(result, authority)


def test_provide_input_requires_exact_decision_state_and_event() -> None:
    authority = RecordingAuthority(_fact(state=TaskState.BLOCKED))
    origin = RecordingOriginAuthority()
    confirmation = RecordingConfirmationConsumer()
    clarifications = RecordingClarificationOwner(boot_id="boot-a", capacity=8)
    text = "answer task-a question-event with B"
    proposal = _proposal(
        "task.provide_input",
        "task-a",
        {"answer": "B", "responds_to_event_id": "question-event"},
        text,
    )

    result = _resolve(
        _request(proposal, origin, text=text),
        authority,
        origin,
        confirmation,
        clarifications,
    )

    assert result.outcome is ProductionTaskPolicyOutcome.CONFLICT
    assert result.reason == "TASK_INPUT_STATE_CONFLICT"
    assert confirmation.calls == []
    assert clarifications.issue_calls == clarifications.consume_calls == 0
    _assert_no_effects(result, authority)


def test_current_hint_allocates_nonempty_bounded_candidates() -> None:
    authority = RecordingAuthority(_fact("x"), _fact("y"))
    origin = RecordingOriginAuthority()
    confirmation = RecordingConfirmationConsumer()
    clarifications = RecordingClarificationOwner(boot_id="boot-a", capacity=8)
    text = "status current task"
    proposal = replace(
        _proposal("task.status", "current", {"query_kind": "status"}, text),
        target_kind="hint",
    )

    result = _resolve(
        _request(proposal, origin, text=text),
        authority,
        origin,
        confirmation,
        clarifications,
    )

    assert result.outcome is ProductionTaskPolicyOutcome.CLARIFICATION
    assert result.candidate_task_ids == ("x", "y")
    assert result.clarification_handle_id is not None
    assert clarifications.issue_calls == 1
    assert confirmation.calls == []
    _assert_no_effects(result, authority)
