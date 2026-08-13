from __future__ import annotations

from dataclasses import replace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
    ErrorCode,
    ScopeRef,
    TurnCommit,
    TurnCommitLedger,
)
from jiuwenswarm.server.live_voice.task_revision import (
    TaskRevisionGrant,
    TaskRevisionOperation,
    TaskRevisionTargetSnapshot,
)
from jiuwenswarm.server.live_voice.task_revision_bridge import (
    BoundedTaskRevisionVoiceBridge,
    TaskRevisionBridgeViolation,
    TaskRevisionIntentDisposition,
    TaskRevisionPolicyAdapter,
)


NOW = "2026-08-13T10:00:00Z"


class _Targets:
    def __init__(self, target: TaskRevisionTargetSnapshot) -> None:
        self.target = target
        self.reads = 0

    def read_target(self, task_id: str, scope: ScopeRef) -> TaskRevisionTargetSnapshot:
        self.reads += 1
        return self.target


def _scope(*, project: str = "project-1") -> ScopeRef:
    return ScopeRef("user-1", project, "session-1", Assurance.AUTHENTICATED)


def _commit(text: str, *, scope: ScopeRef | None = None) -> TurnCommit:
    return TurnCommit.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "commit_id": "commit-revision-1",
            "turn_id": "turn-revision-1",
            "interaction_id": "interaction-1",
            "text": text,
            "committed_at": NOW,
            "scope": (scope or _scope()).to_dict(),
            "context_refs": [],
            "hypothesis_provenance": {"provider": "fixture"},
        }
    )


def _target(**changes: object) -> TaskRevisionTargetSnapshot:
    values: dict[str, object] = {
        "task_id": "task-1",
        "scope": _scope(),
        "task_revision": 1,
        "attempt_id": "attempt-1",
        "attempt_number": 1,
        "task_state": "running",
    }
    values.update(changes)
    return TaskRevisionTargetSnapshot(**values)  # type: ignore[arg-type]


def _authorities(
    commit: TurnCommit, *, target: TaskRevisionTargetSnapshot | None = None
) -> tuple[TurnCommitLedger, _Targets]:
    ledger = TurnCommitLedger()
    ledger.accept(commit)
    return ledger, _Targets(target or _target())


def _resolve(text: str):
    commit = _commit(text)
    ledger, targets = _authorities(commit)
    return BoundedTaskRevisionVoiceBridge(
        enabled=True, commits=ledger, targets=targets
    ).resolve(
        commit,
        authorized_scope=_scope(),
        task_id="task-1",
    )


def test_feature_off_returns_before_inspecting_untrusted_inputs() -> None:
    bridge = BoundedTaskRevisionVoiceBridge(enabled=False)

    with pytest.raises(TaskRevisionBridgeViolation) as rejected:
        bridge.resolve(object(), authorized_scope=_scope(), task_id=object())  # type: ignore[arg-type]

    assert rejected.value.reason == "TASK_REVISION_FEATURE_DISABLED"
    assert rejected.value.code is ErrorCode.UNSUPPORTED


@pytest.mark.parametrize(
    ("text", "operation"),
    [
        ("provide task input: keep negative inputs unchanged", "task.provide_input"),
        ("补充任务输入：负数输入行为保持不变", "task.provide_input"),
        ("limit task write scope to: src/calculator, tests", "task.update_constraints"),
        ("限制任务写入范围：src/calculator，tests", "task.update_constraints"),
        ("require task regression verification", "task.update_constraints"),
        ("要求任务回归验证", "task.update_constraints"),
    ],
)
def test_exact_bilingual_forms_require_confirmation(text: str, operation: str) -> None:
    draft = _resolve(text)

    assert draft.disposition is TaskRevisionIntentDisposition.CONFIRMATION_REQUIRED
    assert draft.operation is TaskRevisionOperation(operation)
    assert draft.target.task_id == "task-1"
    assert draft.source_span is not None
    assert text[draft.source_span.start : draft.source_span.end].strip()


def test_bridge_never_derives_target_identity_from_speech() -> None:
    draft = _resolve("provide task input: task-other must keep negative inputs")

    assert draft.target.task_id == "task-1"
    assert draft.target.attempt_id == "attempt-1"
    assert draft.facts == ("task-other must keep negative inputs",)


@pytest.mark.parametrize(
    ("text", "disposition", "reason"),
    [
        (
            "task change while it runs",
            TaskRevisionIntentDisposition.CLARIFICATION_REQUIRED,
            "TASK_REVISION_EXACT_FORM_REQUIRED",
        ),
        (
            "pause task revision",
            TaskRevisionIntentDisposition.REJECTED,
            "TASK_REVISION_OPERATION_FORBIDDEN",
        ),
        (
            "provide task input: git push the result",
            TaskRevisionIntentDisposition.REJECTED,
            "TASK_REVISION_OPERATION_FORBIDDEN",
        ),
        (
            "what is the weather",
            TaskRevisionIntentDisposition.REJECTED,
            "UNSUPPORTED_TASK_REVISION_INTENT",
        ),
    ],
)
def test_ambiguous_generic_and_forbidden_forms_never_prepare(
    text: str,
    disposition: TaskRevisionIntentDisposition,
    reason: str,
) -> None:
    draft = _resolve(text)

    assert draft.disposition is disposition
    assert draft.reason == reason
    assert draft.operation is None


@pytest.mark.parametrize(
    "target",
    [
        _target(task_state="accepted"),
        _target(task_revision=2, attempt_number=2, attempt_id="attempt-2"),
        _target(pending_command_id="other-command"),
    ],
)
def test_ineligible_store_target_rejects_before_payload_resolution(
    target: TaskRevisionTargetSnapshot,
) -> None:
    commit = _commit("provide task input: fact")
    ledger, targets = _authorities(commit, target=target)
    with pytest.raises(TaskRevisionBridgeViolation) as rejected:
        BoundedTaskRevisionVoiceBridge(
            enabled=True, commits=ledger, targets=targets
        ).resolve(
            commit,
            authorized_scope=_scope(),
            task_id="task-1",
        )

    assert rejected.value.reason == "TASK_REVISION_TARGET_INELIGIBLE"


def test_wrong_scope_rejects_without_a_draft() -> None:
    commit = _commit("provide task input: fact", scope=_scope(project="other"))
    ledger, targets = _authorities(commit)
    with pytest.raises(TaskRevisionBridgeViolation) as rejected:
        BoundedTaskRevisionVoiceBridge(
            enabled=True, commits=ledger, targets=targets
        ).resolve(
            commit,
            authorized_scope=_scope(),
            task_id="task-1",
        )

    assert rejected.value.reason == "TASK_REVISION_SCOPE_MISMATCH"


def test_policy_prepares_acg_command_and_requires_exact_confirmation() -> None:
    commit = _commit("provide task input: keep negative inputs unchanged")
    ledger, targets = _authorities(commit)
    bridge = BoundedTaskRevisionVoiceBridge(
        enabled=True, commits=ledger, targets=targets
    )
    draft = bridge.resolve(commit, authorized_scope=_scope(), task_id="task-1")
    policy = TaskRevisionPolicyAdapter(commits=ledger, targets=targets)
    prepared = policy.prepare(
        draft,
        request_id="request-1",
        command_id="command-1",
        issued_at=NOW,
        correlation_id="correlation-1",
    )
    grant = TaskRevisionGrant(
        principal_id="user-1",
        scope=_scope(),
        operation=prepared.command.operation,
        command_id=prepared.command.command_id,
        task_id=prepared.command.task_id,
        expected_task_revision=prepared.command.expected_task_revision,
        expected_attempt_id=prepared.command.expected_attempt_id,
        command_fingerprint=prepared.command.fingerprint(),
        confirmation_id="confirmation-1",
        confirmed=True,
        expires_at="2026-08-13T10:05:00Z",
    )

    assert prepared.envelope.command_type == "task.provide_input"
    assert prepared.envelope.origin.commit_id == draft.commit_id
    assert "task-1" in prepared.confirmation_prompt
    assert "keep negative inputs unchanged" in prepared.confirmation_prompt
    assert prepared.command_fingerprint_sha256 in prepared.confirmation_prompt
    assert policy.authorize(prepared, grant, now=NOW) == prepared.command

    with pytest.raises(TaskRevisionBridgeViolation) as rejected:
        policy.authorize(
            prepared,
            replace(grant, command_fingerprint=b"different"),
            now=NOW,
        )
    assert rejected.value.code is ErrorCode.PERMISSION_DENIED


def test_bridge_requires_accepted_commit_and_store_derived_target() -> None:
    commit = _commit("provide task input: fact")
    targets = _Targets(_target())
    with pytest.raises(TaskRevisionBridgeViolation) as unaccepted:
        BoundedTaskRevisionVoiceBridge(
            enabled=True,
            commits=TurnCommitLedger(),
            targets=targets,
        ).resolve(commit, authorized_scope=_scope(), task_id="task-1")
    assert unaccepted.value.reason == "TURN_COMMIT_NOT_ACCEPTED"
    assert targets.reads == 0

    ledger = TurnCommitLedger()
    ledger.accept(commit)
    mismatched = _Targets(_target(task_id="task-other"))
    with pytest.raises(TaskRevisionBridgeViolation) as target_error:
        BoundedTaskRevisionVoiceBridge(
            enabled=True,
            commits=ledger,
            targets=mismatched,
        ).resolve(commit, authorized_scope=_scope(), task_id="task-1")
    assert target_error.value.reason == "TASK_REVISION_TARGET_AUTHORITY_MISMATCH"


def test_policy_revalidates_commit_and_store_target_before_prepare() -> None:
    commit = _commit("provide task input: fact")
    ledger, targets = _authorities(commit)
    draft = BoundedTaskRevisionVoiceBridge(
        enabled=True, commits=ledger, targets=targets
    ).resolve(commit, authorized_scope=_scope(), task_id="task-1")
    targets.target = _target(pending_command_id="other-command")

    with pytest.raises(TaskRevisionBridgeViolation) as stale:
        TaskRevisionPolicyAdapter(commits=ledger, targets=targets).prepare(
            draft,
            request_id="request-1",
            command_id="command-1",
            issued_at=NOW,
            correlation_id="correlation-1",
        )

    assert stale.value.reason == "TASK_REVISION_TARGET_INELIGIBLE"
