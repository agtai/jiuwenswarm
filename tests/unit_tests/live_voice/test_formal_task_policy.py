# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
    CommandEnvelope,
    ContractViolation,
    InputCommitState,
    QueryEnvelope,
    ScopeRef,
    OriginRef,
    TerminalOutcome,
    TurnCommit,
    TurnCommitLedger,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    FormalTaskViolation,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
    TaskRetryPrecondition,
    TaskRetryProductRequestFingerprint,
)
from jiuwenswarm.server.live_voice.voice_task_policy import (
    FormalTaskPolicyAdapter,
    FormalTaskPolicyInput,
)

NOW = "2026-08-05T12:00:00Z"
EXPIRY = "2026-08-05T13:00:00Z"


def _scope() -> ScopeRef:
    return ScopeRef("user-1", "project-1", "session-1", Assurance.AUTHENTICATED)


def _context(project: Path) -> ResolvedTaskContext:
    return ResolvedTaskContext(
        source="gateway.project_registry",
        stable_id="project-1",
        uri=project.resolve().as_uri(),
        revision_kind="version",
        revision_value="a77516a0",
        scope=_scope(),
        permissions=("task.execute", "project.write"),
        expires_at=EXPIRY,
        redaction_policy_id="live_voice.project.v1",
    )


def _grant(
    operation: str, *, command_id: str | None, target: str | None
) -> TaskAuthorizationGrant:
    return TaskAuthorizationGrant(
        principal_id="user-1",
        scope=_scope(),
        operation=operation,
        command_id=command_id,
        target_task_id=target,
        allowed_capabilities=frozenset({operation}),
        confirmation_id="confirm-1" if command_id is not None else None,
        confirmed=command_id is not None,
        expires_at=EXPIRY,
    )


def _create(project: Path) -> FormalTaskPolicyInput:
    return FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="voice",
        operation="task.create",
        request_id="request-1",
        command_id="command-1",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-1",
        authorization=_grant("task.create", command_id="command-1", target=None),
        interaction_id="interaction-1",
        turn_id="turn-1",
        commit_id="commit-1",
        name="Implement formal task",
        instruction="Create the bounded project change.",
        context=_context(project),
        destructive=True,
        confirmed=True,
        confirmation_id="confirm-1",
    )


def _voice_policy() -> FormalTaskPolicyAdapter:
    commits = TurnCommitLedger()
    commits.accept(
        TurnCommit.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "commit_id": "commit-1",
                "turn_id": "turn-1",
                "interaction_id": "interaction-1",
                "text": "Create the bounded project change.",
                "hypothesis_provenance": {"provider": "test"},
                "scope": _scope().to_dict(),
                "context_refs": [],
                "committed_at": NOW,
            }
        )
    )
    return FormalTaskPolicyAdapter(commits)


def test_turn_commit_ledger_is_bounded_and_exact_release_recovers_capacity() -> None:
    ledger = TurnCommitLedger(capacity=1)
    first = TurnCommit.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "commit_id": "commit-capacity-1",
            "turn_id": "turn-capacity-1",
            "interaction_id": "interaction-1",
            "text": "first",
            "hypothesis_provenance": {"provider": "test"},
            "scope": _scope().to_dict(),
            "context_refs": [],
            "committed_at": NOW,
        }
    )
    second = TurnCommit.from_dict(
        {
            **first.to_dict(),
            "commit_id": "commit-capacity-2",
            "turn_id": "turn-capacity-2",
            "text": "second",
        }
    )

    assert ledger.accept(first)
    with pytest.raises(ContractViolation) as raised:
        ledger.accept(second)
    assert raised.value.reason == "TURN_COMMIT_LEDGER_FULL"
    assert ledger.release_origin(
        OriginRef("committed_turn", first.turn_id, first.commit_id), first.scope
    )
    assert ledger.accept(second)


def test_committed_voice_create_maps_to_formal_v2_without_claiming_authority(
    tmp_path: Path,
) -> None:
    invocation = _voice_policy().map(_create(tmp_path))

    assert isinstance(invocation.envelope, CommandEnvelope)
    assert invocation.envelope.command_type == "task.create"
    assert invocation.envelope.origin.to_dict() == {
        "kind": "committed_turn",
        "turn_id": "turn-1",
        "commit_id": "commit-1",
    }
    assert invocation.envelope.payload["executor_id"] == (
        "jiuwenswarm_code_agent.project_code"
    )
    assert invocation.authorization.principal_id == "user-1"
    assert invocation.context == _context(tmp_path)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"state": InputCommitState.PARTIAL}, "INPUT_NOT_COMMITTED"),
        ({"ambiguous": True}, "TASK_INTENT_AMBIGUOUS"),
        ({"authorization": None}, "FORMAL_TASK_AUTHORIZATION_REQUIRED"),
        ({"confirmed": False}, "TASK_CONFIRMATION_REQUIRED"),
        ({"confirmation_id": "other"}, "TASK_CONFIRMATION_MISMATCH"),
        ({"context": None}, "FORMAL_TASK_CONTEXT_REQUIRED"),
    ],
)
def test_voice_create_rejects_unsafe_policy_inputs_before_core(
    tmp_path: Path,
    change: dict[str, object],
    reason: str,
) -> None:
    with pytest.raises(FormalTaskViolation) as raised:
        _voice_policy().map(replace(_create(tmp_path), **change))

    assert raised.value.reason == reason


def test_voice_create_cannot_borrow_commit_for_different_instruction(
    tmp_path: Path,
) -> None:
    with pytest.raises(FormalTaskViolation) as raised:
        _voice_policy().map(
            replace(_create(tmp_path), instruction="A different project change.")
        )

    assert raised.value.reason == "VOICE_TASK_INSTRUCTION_MISMATCH"


def test_natural_cancel_requires_the_exact_task_id_source_span() -> None:
    commit = TurnCommit.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "commit_id": "commit-cancel",
            "turn_id": "turn-cancel",
            "interaction_id": "interaction-cancel",
            "text": "cancel task task-1",
            "hypothesis_provenance": {"provider": "test"},
            "scope": _scope().to_dict(),
            "context_refs": [],
            "committed_at": NOW,
        }
    )
    commits = TurnCommitLedger()
    assert commits.accept(commit)
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="text",
        operation="task.cancel",
        request_id="request-cancel",
        command_id="command-cancel",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-cancel",
        authorization=_grant(
            "task.cancel", command_id="command-cancel", target="task-2"
        ),
        interaction_id=commit.interaction_id,
        turn_id=commit.turn_id,
        commit_id=commit.commit_id,
        origin_commit_sha256=hashlib.sha256(commit.canonical_bytes()).hexdigest(),
        source_start=12,
        source_end=18,
        task_id="task-2",
        destructive=True,
        confirmed=True,
        confirmation_id="confirm-1",
    )

    with pytest.raises(FormalTaskViolation) as raised:
        FormalTaskPolicyAdapter(commits).map(intent)

    assert raised.value.reason == "TASK_INTENT_SOURCE_SPAN_MISMATCH"


def test_status_is_a_read_only_query_with_exact_task_and_no_context() -> None:
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="structured",
        operation="task.status",
        request_id="request-status",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-status",
        authorization=_grant("task.status", command_id=None, target="task-1"),
        task_id="task-1",
    )

    invocation = FormalTaskPolicyAdapter().map(intent)

    assert isinstance(invocation.envelope, QueryEnvelope)
    assert invocation.envelope.query_type == "task.status"
    assert invocation.envelope.target_ref.id == "task-1"
    assert invocation.context is None


def test_request_derived_scope_cannot_be_promoted_to_formal_authorization() -> None:
    request_scope = ScopeRef(
        "web-channel",
        "project-1",
        "session-1",
        Assurance.REQUEST_ASSERTED,
    )
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="structured",
        operation="task.status",
        request_id="request-status",
        issued_at=NOW,
        scope=request_scope,
        correlation_id="correlation-status",
        authorization=None,
        task_id="task-1",
    )

    with pytest.raises(FormalTaskViolation) as raised:
        FormalTaskPolicyAdapter().map(intent)

    assert raised.value.reason == "FORMAL_TASK_AUTHORIZATION_REQUIRED"


def test_voice_intent_cannot_claim_commit_without_commit_authority(
    tmp_path: Path,
) -> None:
    with pytest.raises(FormalTaskViolation) as raised:
        FormalTaskPolicyAdapter().map(_create(tmp_path))

    assert raised.value.reason == "COMMIT_AUTHORITY_REQUIRED"


def test_unreviewed_task_attribute_is_rejected_before_core(tmp_path: Path) -> None:
    with pytest.raises(FormalTaskViolation) as raised:
        replace(_create(tmp_path), attributes={"execution_root": str(tmp_path)})

    assert raised.value.reason == "UNSUPPORTED_FORMAL_TASK_ATTRIBUTE"


def test_voice_adjust_maps_exact_current_task_and_committed_span() -> None:
    text = "Move dinner to 19:00."
    current_commit = TurnCommit.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "commit_id": "commit-adjust-1",
            "turn_id": "turn-adjust-1",
            "interaction_id": "interaction-adjust-1",
            "text": text,
            "hypothesis_provenance": {"provider": "test"},
            "scope": _scope().to_dict(),
            "context_refs": [],
            "committed_at": NOW,
        }
    )
    commits = TurnCommitLedger()
    assert commits.accept(current_commit)
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="voice",
        operation="task.adjust",
        request_id="request-adjust-1",
        command_id="command-adjust-1",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-adjust-1",
        authorization=_grant(
            "task.adjust", command_id="command-adjust-1", target="task-1"
        ),
        interaction_id=current_commit.interaction_id,
        turn_id=current_commit.turn_id,
        commit_id=current_commit.commit_id,
        origin_commit_sha256=hashlib.sha256(
            current_commit.canonical_bytes()
        ).hexdigest(),
        source_start=0,
        source_end=len(text),
        task_id="task-1",
        instruction=text,
        destructive=True,
        confirmed=True,
        confirmation_id="confirm-1",
        current_task_binding=True,
    )

    invocation = FormalTaskPolicyAdapter(commits).map(intent)
    envelope = invocation.envelope
    assert isinstance(envelope, CommandEnvelope)
    assert envelope.command_type == "task.adjust"
    assert envelope.target_ref.id == "task-1"
    assert envelope.payload == {"adjustment": text}
    assert envelope.extensions == {}
    assert invocation.context is None

    for changes, reason in (
        ({"task_id": "task-2"}, "FORMAL_TASK_AUTHORIZATION_DENIED"),
        ({"source_end": len(text) - 1}, "TASK_INTENT_SOURCE_SPAN_MISMATCH"),
        ({"instruction": "different"}, "TASK_INTENT_SOURCE_SPAN_MISMATCH"),
        ({"context": _context(Path.cwd())}, "INVALID_TASK_ADJUST_INTENT"),
    ):
        with pytest.raises(FormalTaskViolation) as rejected:
            FormalTaskPolicyAdapter(commits).map(replace(intent, **changes))
        assert rejected.value.reason == reason


# --- D-069 bounded task.retry mapping ---------------------------------------


def _retry_precondition(
    *,
    previous_attempt_id: str = "attempt-1",
    outcome: TerminalOutcome = TerminalOutcome.CANCELLED,
    attempt_number: int = 2,
) -> TaskRetryPrecondition:
    return TaskRetryPrecondition(
        previous_attempt_id=previous_attempt_id,
        previous_outcome=outcome,
        attempt_number=attempt_number,
    )


def _retry_fingerprint(digest: str = "b" * 64) -> TaskRetryProductRequestFingerprint:
    return TaskRetryProductRequestFingerprint(digest)


def _retry(project: Path, **overrides: object) -> FormalTaskPolicyInput:
    base: dict[str, object] = {
        "state": InputCommitState.COMMITTED,
        "source": "structured",
        "operation": "task.retry",
        "request_id": "request-retry",
        "command_id": "command-retry",
        "issued_at": NOW,
        "scope": _scope(),
        "correlation_id": "correlation-1",
        "authorization": _grant(
            "task.retry", command_id="command-retry", target="task-1"
        ),
        "task_id": "task-1",
        "context": _context(project),
        "destructive": True,
        "confirmed": True,
        "confirmation_id": "confirm-1",
        "retry_precondition": _retry_precondition(),
        "retry_product_request": _retry_fingerprint(),
    }
    base.update(overrides)
    return FormalTaskPolicyInput(**base)  # type: ignore[arg-type]


def test_retry_maps_server_derived_lineage_into_one_exact_command(
    tmp_path: Path,
) -> None:
    invocation = FormalTaskPolicyAdapter().map(_retry(tmp_path))
    envelope = invocation.envelope

    assert isinstance(envelope, CommandEnvelope)
    assert envelope.command_type == "task.retry"
    assert envelope.target_ref.kind.value == "task"
    assert envelope.target_ref.id == "task-1"
    assert tuple(envelope.required_capabilities) == ("task.retry",)
    assert envelope.origin == OriginRef("structured", None, None)
    # The payload is exactly the Store-derived predecessor lineage.
    assert envelope.payload == {
        "previous_attempt_id": "attempt-1",
        "previous_outcome": "cancelled",
        "attempt_number": 2,
    }
    # The product-owned request fingerprint travels as the only extension.
    assert envelope.extensions == {
        "jiuwenswarm.task_retry_product_request": {"sha256": "b" * 64}
    }
    assert invocation.context is not None
    assert invocation.authorization.operation == "task.retry"


def test_retry_requires_confirmation_context_lineage_and_fingerprint(
    tmp_path: Path,
) -> None:
    adapter = FormalTaskPolicyAdapter()

    for overrides, expected in (
        ({"confirmed": False}, "TASK_CONFIRMATION_REQUIRED"),
        ({"confirmation_id": None}, "TASK_CONFIRMATION_REQUIRED"),
        ({"destructive": False}, "TASK_CONFIRMATION_REQUIRED"),
        ({"task_id": None}, "EXACT_TASK_REQUIRED"),
        ({"context": None}, "FORMAL_TASK_CONTEXT_REQUIRED"),
        ({"retry_precondition": None}, "TASK_RETRY_PRECONDITION_REQUIRED"),
        (
            {"retry_product_request": None},
            "TASK_RETRY_PRODUCT_REQUEST_FINGERPRINT_REQUIRED",
        ),
    ):
        with pytest.raises(FormalTaskViolation) as raised:
            adapter.map(_retry(tmp_path, **overrides))
        assert raised.value.reason == expected, overrides


def test_retry_rejects_create_only_content_and_a_voice_committed_origin(
    tmp_path: Path,
) -> None:
    adapter = FormalTaskPolicyAdapter()

    for overrides, expected in (
        ({"name": "renamed"}, "INVALID_TASK_RETRY_INTENT"),
        ({"instruction": "replaced"}, "INVALID_TASK_RETRY_INTENT"),
        (
            {"attributes": {"model_identity": "m", "model_config_version": "v"}},
            "INVALID_TASK_RETRY_INTENT",
        ),
        ({"after_seq": 0}, "INVALID_TASK_RETRY_INTENT"),
    ):
        with pytest.raises(FormalTaskViolation) as raised:
            adapter.map(_retry(tmp_path, **overrides))
        assert raised.value.reason == expected, overrides

    # A retry never borrows a committed voice turn: the bounded W2 contract is
    # structured-only, so a voice claim fails closed rather than being ignored.
    with pytest.raises(FormalTaskViolation) as voice:
        adapter.map(
            _retry(
                tmp_path,
                source="voice",
                interaction_id="interaction-1",
                turn_id="turn-1",
                commit_id="commit-1",
            )
        )
    assert voice.value.reason == "COMMIT_AUTHORITY_REQUIRED"

    with pytest.raises(FormalTaskViolation) as voice_with_ledger:
        _voice_policy().map(
            _retry(
                tmp_path,
                source="voice",
                interaction_id="interaction-1",
                turn_id="turn-1",
                commit_id="commit-1",
            )
        )
    assert voice_with_ledger.value.reason == "INVALID_TASK_RETRY_INTENT"


def test_only_retry_may_carry_server_derived_retry_lineage(tmp_path: Path) -> None:
    adapter = FormalTaskPolicyAdapter()

    with pytest.raises(FormalTaskViolation) as created:
        _voice_policy().map(
            replace(_create(tmp_path), retry_precondition=_retry_precondition())
        )
    assert created.value.reason == "INVALID_TASK_RETRY_INTENT"

    query = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="structured",
        operation="task.get",
        request_id="request-get",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-1",
        authorization=_grant("task.get", command_id=None, target="task-1"),
        task_id="task-1",
        retry_product_request=_retry_fingerprint(),
    )
    with pytest.raises(FormalTaskViolation) as queried:
        adapter.map(query)
    assert queried.value.reason == "INVALID_TASK_RETRY_INTENT"


def test_retry_precondition_rejects_ineligible_outcome_and_attempt_number() -> None:
    for outcome in (
        TerminalOutcome.FAILED,
        TerminalOutcome.INTERRUPTED,
        TerminalOutcome.UNKNOWN,
    ):
        with pytest.raises(FormalTaskViolation) as raised:
            _retry_precondition(outcome=outcome)
        assert raised.value.reason == "TASK_RETRY_OUTCOME_NOT_ELIGIBLE"

    for attempt_number in (0, 1, 4):
        with pytest.raises(FormalTaskViolation) as raised:
            _retry_precondition(attempt_number=attempt_number)
        assert raised.value.reason == "TASK_RETRY_ATTEMPT_NUMBER_INVALID"


def test_product_request_fingerprint_must_be_canonical_sha256() -> None:
    for invalid in ("", "b" * 63, "B" * 64, "g" * 64):
        with pytest.raises(FormalTaskViolation) as raised:
            TaskRetryProductRequestFingerprint(invalid)
        assert raised.value.reason == ("TASK_RETRY_PRODUCT_REQUEST_FINGERPRINT_INVALID")
