# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from dataclasses import replace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    InputCommitState,
    ScopeRef,
    TurnCommit,
)
from jiuwenswarm.server.live_voice.voice_task_bridge import (
    BoundedAlphaTaskIntentResolver,
    ResolvedTaskIntent,
    TaskIntent,
    TaskIntentDisposition,
    TaskIntentSourceSpan,
    VoiceTaskBridge,
    VoiceTaskBridgeViolation,
)


SCOPE = ScopeRef("subject", "project", "session", Assurance.AUTHENTICATED)


def committed(text: str, *, commit_id: str = "commit-natural-1") -> TurnCommit:
    return TurnCommit.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "commit_id": commit_id,
            "turn_id": f"turn-{commit_id}",
            "interaction_id": "interaction-natural-1",
            "text": text,
            "hypothesis_provenance": {
                "provider": "test",
                "kind": "committed_text",
            },
            "scope": SCOPE.to_dict(),
            "context_refs": [],
            "committed_at": "2030-01-01T00:00:00Z",
        }
    )


def create_intent(**overrides) -> TaskIntent:
    values = {
        "state": InputCommitState.COMMITTED,
        "operation": "task.create",
        "request_id": "request-1",
        "command_id": "command-1",
        "scope": SCOPE,
        "origin_commit_id": "commit-1",
        "name": "inventory",
        "instruction": "check inventory",
    }
    values.update(overrides)
    return TaskIntent(**values)


def test_committed_create_maps_to_command_without_executing_task() -> None:
    bridge = VoiceTaskBridge()
    command = bridge.map(create_intent(), SCOPE)
    assert command.operation == "task.create"
    assert command.spec.name == "inventory"
    assert command.target_task_id is None
    assert not hasattr(bridge, "task_store")
    assert not hasattr(bridge, "tts")


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"state": InputCommitState.PARTIAL}, "INPUT_NOT_COMMITTED"),
        ({"state": InputCommitState.UNCOMMITTED}, "INPUT_NOT_COMMITTED"),
        ({"ambiguous": True}, "TASK_INTENT_AMBIGUOUS"),
        ({"destructive": True}, "TASK_CONFIRMATION_REQUIRED"),
        ({"origin_commit_id": None}, "COMMITTED_ORIGIN_REQUIRED"),
    ],
)
def test_unsafe_intents_reject_before_command(changes, reason) -> None:
    bridge = VoiceTaskBridge()
    with pytest.raises(VoiceTaskBridgeViolation) as raised:
        bridge.map(create_intent(**changes), SCOPE)
    assert raised.value.reason == reason


def test_cross_scope_and_inexact_cancel_reject() -> None:
    bridge = VoiceTaskBridge()
    foreign = ScopeRef("other", "project", "session", Assurance.AUTHENTICATED)
    with pytest.raises(VoiceTaskBridgeViolation) as raised:
        bridge.map(create_intent(scope=foreign), SCOPE)
    assert raised.value.reason == "TASK_SCOPE_MISMATCH"
    with pytest.raises(VoiceTaskBridgeViolation) as raised:
        bridge.map(
            create_intent(
                operation="task.cancel", name=None, instruction=None, task_id=None
            ),
            SCOPE,
        )
    assert raised.value.reason == "EXACT_TASK_REQUIRED"


def test_confirmed_exact_cancel_maps_without_terminal_claim() -> None:
    command = VoiceTaskBridge().map(
        create_intent(
            operation="task.cancel",
            task_id="task-1",
            name=None,
            instruction=None,
            destructive=True,
            confirmed=True,
        ),
        SCOPE,
    )
    assert command.operation == "task.cancel"
    assert command.target_task_id == "task-1"
    assert command.spec is None


@pytest.mark.parametrize(
    ("text", "operation", "task_id", "instruction", "disposition"),
    [
        (
            "create task: inspect the repository",
            "task.create",
            None,
            "inspect the repository",
            TaskIntentDisposition.CLARIFICATION,
        ),
        (
            "创建任务：检查仓库",
            "task.create",
            None,
            "检查仓库",
            TaskIntentDisposition.CLARIFICATION,
        ),
        (
            "task status task-abc_123",
            "task.status",
            "task-abc_123",
            None,
            TaskIntentDisposition.DISPATCHED,
        ),
        (
            "任务状态 task-abc_123",
            "task.status",
            "task-abc_123",
            None,
            TaskIntentDisposition.DISPATCHED,
        ),
        (
            "cancel task task-abc_123",
            "task.cancel",
            "task-abc_123",
            None,
            TaskIntentDisposition.CLARIFICATION,
        ),
        (
            "取消任务 task-abc_123",
            "task.cancel",
            "task-abc_123",
            None,
            TaskIntentDisposition.CLARIFICATION,
        ),
    ],
)
def test_bounded_alpha_corpus_resolves_only_exact_bilingual_forms(
    text: str,
    operation: str,
    task_id: str | None,
    instruction: str | None,
    disposition: TaskIntentDisposition,
) -> None:
    result = VoiceTaskBridge().resolve(committed(text), SCOPE)
    assert result.operation == operation
    assert result.task_id == task_id
    assert result.instruction == instruction
    assert result.disposition is disposition
    assert result.provider == "local.closed_schema"
    assert result.implementation_class == "bounded_deterministic_alpha_v1"
    assert result.source_span is not None
    expected = instruction or task_id
    assert text[result.source_span.start : result.source_span.end] == expected


@pytest.mark.parametrize(
    "text",
    [
        "cancel it",
        "what is its status",
        "please create something useful",
        "取消这个任务",
        "任务怎么样了",
        "创建一个合适的任务",
        "cancel task task-one and task-two",
        "task status",
    ],
)
def test_open_or_ambiguous_task_language_never_guesses_a_command(text: str) -> None:
    result = VoiceTaskBridge().resolve(committed(text), SCOPE)
    assert result.disposition in {
        TaskIntentDisposition.CLARIFICATION,
        TaskIntentDisposition.REJECTED,
    }
    assert result.operation is None
    assert result.task_id is None
    assert result.instruction is None


@pytest.mark.parametrize(
    "text",
    [
        "pause task task-abc_123",
        "resume task task-abc_123",
        "暂停任务 task-abc_123",
        "恢复任务 task-abc_123",
    ],
)
def test_known_full_p3_only_operations_are_definitively_unsupported(
    text: str,
) -> None:
    result = VoiceTaskBridge().resolve(committed(text), SCOPE)

    assert result.disposition is TaskIntentDisposition.REJECTED
    assert result.reason == "UNSUPPORTED_TASK_INTENT"
    assert result.operation is None
    assert result.task_id is None
    assert result.requires_confirmation is False


def test_confirmation_is_a_separate_content_bound_commit() -> None:
    token = "a" * 32
    result = VoiceTaskBridge().resolve(
        committed(f"confirm task request {token}", commit_id="confirm-2"), SCOPE
    )
    assert result.disposition is TaskIntentDisposition.CLARIFICATION
    assert result.operation is None
    assert result.confirmation_token == token
    assert result.source_span is not None


def test_bridge_rejects_resolver_digest_or_span_forgery() -> None:
    class ForgedResolver:
        def resolve(self, _commit: TurnCommit) -> ResolvedTaskIntent:
            return ResolvedTaskIntent(
                disposition=TaskIntentDisposition.DISPATCHED,
                reason="TASK_INTENT_RESOLVED",
                provider="forged",
                implementation_class="test",
                resolution_id="resolution-forged",
                commit_sha256="0" * 64,
                operation="task.status",
                task_id="task-abc",
                source_span=TaskIntentSourceSpan(0, 4),
                target_span=TaskIntentSourceSpan(0, 4),
            )

    with pytest.raises(VoiceTaskBridgeViolation) as raised:
        VoiceTaskBridge(ForgedResolver()).resolve(
            committed("task status task-abc"), SCOPE
        )
    assert raised.value.reason == "TASK_INTENT_COMMIT_MISMATCH"


def test_bridge_recomputes_the_complete_resolution_identity() -> None:
    class ForgedResolver:
        def resolve(self, commit: TurnCommit) -> ResolvedTaskIntent:
            resolved = BoundedAlphaTaskIntentResolver().resolve(commit)
            return replace(resolved, resolution_id="0" * 64)

    with pytest.raises(VoiceTaskBridgeViolation) as raised:
        VoiceTaskBridge(ForgedResolver()).resolve(
            committed("task status task-abc"), SCOPE
        )

    assert raised.value.reason == "TASK_INTENT_RESOLUTION_ID_MISMATCH"
