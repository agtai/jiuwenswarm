from __future__ import annotations

from dataclasses import replace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
    CommandEnvelope,
    ErrorCode,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.task_revision import (
    S8_5_TASK_REVISION_PROFILE,
    S8_5_TASK_REVISION_EXTENSION,
    TaskConstraintPatch,
    TaskRevisionAuthority,
    TaskRevisionCommand,
    TaskRevisionConstraints,
    TaskRevisionGrant,
    TaskRevisionOperation,
    TaskRevisionRecord,
    TaskRevisionViolation,
    plan_task_revision,
)


NOW = "2026-08-13T10:00:00Z"


def _scope(*, subject: str = "user-1", project: str = "project-1") -> ScopeRef:
    return ScopeRef(subject, project, "session-1", Assurance.AUTHENTICATED)


def _command(
    operation: TaskRevisionOperation = TaskRevisionOperation.PROVIDE_INPUT,
    *,
    command_id: str = "command-revise-1",
    revision: int = 1,
    attempt_id: str = "attempt-1",
    scope: ScopeRef | None = None,
) -> TaskRevisionCommand:
    return TaskRevisionCommand(
        command_id=command_id,
        operation=operation,
        scope=scope or _scope(),
        task_id="task-1",
        expected_task_revision=revision,
        expected_attempt_id=attempt_id,
        origin_commit_id="turn-commit-1",
        facts=("negative inputs retain their current behavior",)
        if operation is TaskRevisionOperation.PROVIDE_INPUT
        else (),
        constraint_patch=(
            TaskConstraintPatch(
                write_scope=("src/calculator",),
                regression_verifier_required=True,
            )
            if operation is TaskRevisionOperation.UPDATE_CONSTRAINTS
            else None
        ),
    )


def _authority(**changes: object) -> TaskRevisionAuthority:
    values: dict[str, object] = {
        "task_id": "task-1",
        "scope": _scope(),
        "task_revision": 1,
        "attempt_id": "attempt-1",
        "task_state": "running",
        "base_instruction": "Fix the calculator defect.",
        "additive_facts": (),
        "constraints": TaskRevisionConstraints(("src", "tests")),
    }
    values.update(changes)
    return TaskRevisionAuthority(**values)  # type: ignore[arg-type]


def _grant(command: TaskRevisionCommand, **changes: object) -> TaskRevisionGrant:
    values: dict[str, object] = {
        "principal_id": command.scope.subject_id,
        "scope": command.scope,
        "operation": command.operation,
        "command_id": command.command_id,
        "task_id": command.task_id,
        "expected_task_revision": command.expected_task_revision,
        "expected_attempt_id": command.expected_attempt_id,
        "command_fingerprint": command.fingerprint(),
        "confirmation_id": "confirmation-1",
        "confirmed": True,
        "expires_at": "2026-08-13T10:05:00Z",
    }
    values.update(changes)
    return TaskRevisionGrant(**values)  # type: ignore[arg-type]


def _plan(command: TaskRevisionCommand, authority: TaskRevisionAuthority | None = None):
    return plan_task_revision(
        command,
        _grant(command),
        authority or _authority(),
        feature_enabled=True,
        now=NOW,
    )


def _reason(callable_) -> tuple[str, ErrorCode]:
    with pytest.raises(TaskRevisionViolation) as raised:
        callable_()
    return raised.value.reason, raised.value.code


def test_provide_input_creates_next_revision_without_changing_task_identity() -> None:
    command = _command()
    plan = _plan(command)

    assert plan.task_id == "task-1"
    assert plan.predecessor_revision == 1
    assert plan.successor_revision == 2
    assert plan.predecessor_attempt_id == "attempt-1"
    assert plan.additive_facts == command.facts
    assert "negative inputs retain" in plan.effective_instruction
    assert "write_scope: src, tests" in plan.effective_instruction


def test_constraint_update_can_only_narrow_and_require_regression_verifier() -> None:
    command = _command(TaskRevisionOperation.UPDATE_CONSTRAINTS)
    plan = _plan(command)

    assert plan.constraints.write_scope == ("src/calculator",)
    assert plan.constraints.regression_verifier_required is True
    assert plan.additive_facts == ()


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({}, "INVALID_TASK_REVISION_CONSTRAINT_PATCH"),
        ({"dependency_policy": "upgrade"}, "TASK_REVISION_CONSTRAINT_NOT_ALLOWLISTED"),
        ({"public_api_policy": "change"}, "TASK_REVISION_CONSTRAINT_NOT_ALLOWLISTED"),
        (
            {"configuration_policy": "change"},
            "TASK_REVISION_CONSTRAINT_NOT_ALLOWLISTED",
        ),
        ({"write_scope": ["../outside"]}, "INVALID_TASK_REVISION_WRITE_SCOPE"),
        ({"write_scope": ["C:/outside"]}, "INVALID_TASK_REVISION_WRITE_SCOPE"),
        ({"write_scope": ["src\\outside"]}, "INVALID_TASK_REVISION_WRITE_SCOPE"),
        (
            {"regression_verifier_required": "yes"},
            "INVALID_TASK_REVISION_CONSTRAINT_PATCH",
        ),
    ],
)
def test_constraint_patch_rejects_unknown_unsafe_or_malformed_fields(
    payload: object, reason: str
) -> None:
    assert _reason(lambda: TaskConstraintPatch.from_dict(payload))[0] == reason


def test_constraint_update_rejects_scope_expansion() -> None:
    command = replace(
        _command(TaskRevisionOperation.UPDATE_CONSTRAINTS),
        constraint_patch=TaskConstraintPatch(write_scope=("docs",)),
    )
    assert _reason(lambda: _plan(command)) == (
        "TASK_REVISION_CONSTRAINT_RELAXATION_FORBIDDEN",
        ErrorCode.PERMISSION_DENIED,
    )


def test_constraint_update_rejects_disabling_required_verifier() -> None:
    command = replace(
        _command(TaskRevisionOperation.UPDATE_CONSTRAINTS),
        constraint_patch=TaskConstraintPatch(regression_verifier_required=False),
    )
    authority = _authority(
        constraints=TaskRevisionConstraints(
            ("src", "tests"), regression_verifier_required=True
        )
    )
    assert _reason(lambda: _plan(command, authority))[0] == (
        "TASK_REVISION_CONSTRAINT_RELAXATION_FORBIDDEN"
    )


def test_constraint_update_rejects_noop() -> None:
    command = replace(
        _command(TaskRevisionOperation.UPDATE_CONSTRAINTS),
        constraint_patch=TaskConstraintPatch(write_scope=("src", "tests")),
    )
    assert _reason(lambda: _plan(command))[0] == "TASK_REVISION_CONSTRAINT_NOOP"


@pytest.mark.parametrize(
    ("change", "reason", "code"),
    [
        (
            {"feature_enabled": False},
            "TASK_REVISION_FEATURE_DISABLED",
            ErrorCode.UNSUPPORTED,
        ),
        (
            {"authority": _authority(task_state="terminal")},
            "TASK_REVISION_TERMINAL",
            ErrorCode.CONFLICT,
        ),
        (
            {"authority": _authority(task_state="accepted")},
            "TASK_REVISION_NOT_RUNNING",
            ErrorCode.CONFLICT,
        ),
        (
            {"authority": _authority(pending_command_id="other")},
            "TASK_REVISION_ALREADY_PENDING",
            ErrorCode.CONFLICT,
        ),
        (
            {"authority": _authority(task_revision=2)},
            "TASK_REVISION_PRECONDITION_STALE",
            ErrorCode.STALE,
        ),
        (
            {"authority": _authority(attempt_id="attempt-2")},
            "TASK_REVISION_PRECONDITION_STALE",
            ErrorCode.STALE,
        ),
    ],
)
def test_admission_fails_closed_for_feature_state_pending_and_stale(
    change: dict[str, object], reason: str, code: ErrorCode
) -> None:
    command = _command()
    assert _reason(
        lambda: plan_task_revision(
            command,
            _grant(command),
            change.get("authority", _authority()),  # type: ignore[arg-type]
            feature_enabled=bool(change.get("feature_enabled", True)),
            now=NOW,
        )
    ) == (reason, code)


@pytest.mark.parametrize(
    "grant_change",
    [
        {"confirmed": False},
        {"principal_id": "other"},
        {"task_id": "task-other"},
        {"expected_task_revision": 2},
        {"expected_attempt_id": "attempt-other"},
        {"confirmation_id": "confirmation-other", "command_id": "other"},
        {"command_fingerprint": b"different"},
        {"expires_at": "2026-08-13T09:59:59Z"},
    ],
)
def test_confirmation_must_bind_every_mutation_fact(
    grant_change: dict[str, object],
) -> None:
    command = _command()
    assert (
        _reason(
            lambda: plan_task_revision(
                command,
                _grant(command, **grant_change),
                _authority(),
                feature_enabled=True,
                now=NOW,
            )
        )[1]
        == ErrorCode.PERMISSION_DENIED
    )


def test_showcase_allows_only_one_revision() -> None:
    command = _command(revision=2)
    assert _reason(lambda: _plan(command, _authority(task_revision=2))) == (
        "TASK_REVISION_LIMIT_EXCEEDED",
        ErrorCode.CONFLICT,
    )


def test_wrong_task_scope_rejects_without_a_plan() -> None:
    command = _command(scope=_scope(project="project-other"))
    assert _reason(
        lambda: plan_task_revision(
            command,
            _grant(command),
            _authority(),
            feature_enabled=True,
            now=NOW,
        )
    ) == ("TASK_REVISION_SCOPE_MISMATCH", ErrorCode.PERMISSION_DENIED)


def test_duplicate_fact_cannot_rewrite_existing_revision() -> None:
    command = _command()
    authority = _authority(additive_facts=command.facts)
    assert _reason(lambda: _plan(command, authority))[0] == (
        "TASK_REVISION_FACT_CONFLICT"
    )


def test_command_round_trip_and_fingerprint_are_canonical() -> None:
    command = _command(TaskRevisionOperation.UPDATE_CONSTRAINTS)
    restored = TaskRevisionCommand.from_dict(command.to_dict())

    assert restored == command
    assert restored.fingerprint() == command.fingerprint()
    assert restored.to_dict()["profile"] == S8_5_TASK_REVISION_PROFILE


def test_acg_v2_envelope_narrows_to_exact_revision_command() -> None:
    envelope = CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": "request-revise-1",
            "command_id": "command-revise-1",
            "command_type": "task.provide_input",
            "issued_at": NOW,
            "scope": _scope().to_dict(),
            "correlation_id": "correlation-1",
            "causation_id": "turn-commit-1",
            "origin": {
                "kind": "committed_turn",
                "turn_id": "turn-1",
                "commit_id": "turn-commit-1",
            },
            "target_ref": {"kind": "task", "id": "task-1"},
            "context_refs": [],
            "required_capabilities": ["task.provide_input"],
            "payload": {
                "expected_task_revision": 1,
                "expected_attempt_id": "attempt-1",
                "facts": ["negative inputs retain their current behavior"],
            },
            "extensions": {
                S8_5_TASK_REVISION_EXTENSION: {"profile": S8_5_TASK_REVISION_PROFILE}
            },
        }
    )

    assert TaskRevisionCommand.from_envelope(envelope) == _command()


def test_command_parser_rejects_generic_update_and_unknown_fields() -> None:
    payload = _command().to_dict()
    payload["operation"] = "task.update"
    assert _reason(lambda: TaskRevisionCommand.from_dict(payload)) == (
        "UNSUPPORTED_TASK_REVISION_OPERATION",
        ErrorCode.UNSUPPORTED,
    )

    payload = _command().to_dict()
    payload["generic_steer"] = True
    assert _reason(lambda: TaskRevisionCommand.from_dict(payload))[0] == (
        "INVALID_TASK_REVISION_COMMAND"
    )


def test_fact_limits_and_unicode_are_fail_closed() -> None:
    assert _reason(lambda: replace(_command(), facts=("x" * 2_001,)))[0] == (
        "TASK_REVISION_FIELD_TOO_LARGE"
    )
    assert _reason(lambda: replace(_command(), facts=("same", "same")))[0] == (
        "INVALID_TASK_REVISION_FACTS"
    )
    assert _reason(lambda: replace(_command(), facts=("bad\ud800",)))[0] == (
        "INVALID_TASK_REVISION_UNICODE"
    )


@pytest.mark.parametrize(
    ("revision", "predecessor"),
    [(1, 0), (2, None), (3, 2)],
)
def test_revision_record_rejects_non_profile_lineage(
    revision: int, predecessor: int | None
) -> None:
    with pytest.raises(TaskRevisionViolation) as rejected:
        TaskRevisionRecord(
            task_id="task-1",
            task_revision=revision,
            predecessor_revision=predecessor,
            attempt_id="attempt-1",
            base_instruction="Fix the calculator defect.",
            additive_facts=(),
            constraints=TaskRevisionConstraints(("src", "tests")),
            origin_commit_id="commit-1",
            created_by_command_id="command-1",
        )

    assert rejected.value.reason == "INVALID_TASK_REVISION_LINEAGE"
