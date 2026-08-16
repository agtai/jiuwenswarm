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
    CurrentBackgroundTaskContext,
    ResolvedTaskIntent,
    TaskIntent,
    TaskIntentDisposition,
    TaskIntentSourceSpan,
    UnifiedCommittedInputRoute,
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


CURRENT = CurrentBackgroundTaskContext(
    task_id="task-current-1",
    name="Three-day itinerary",
    state="running",
    terminal=False,
)


@pytest.mark.parametrize(
    ("text", "route"),
    [
        ("你好，介绍一下你自己。", UnifiedCommittedInputRoute.DIALOGUE),
        (
            "后台帮我检查这些资料并整理报告。",
            UnifiedCommittedInputRoute.BACKGROUND_CREATE,
        ),
        (
            "帮我根据这些要求制定三天的行程。",
            UnifiedCommittedInputRoute.BACKGROUND_CREATE,
        ),
        (
            "帮我在后台制定一份三天杭州行程。",
            UnifiedCommittedInputRoute.BACKGROUND_CREATE,
        ),
        (
            "请在后台生成 itinerary.md 行程文件，包含三天杭州安排。",
            UnifiedCommittedInputRoute.BACKGROUND_CREATE,
        ),
        (
            "把第二天下午改成西湖，晚上给我留出自由时间。",
            UnifiedCommittedInputRoute.BACKGROUND_UPDATE,
        ),
        (
            "Please change the current itinerary so day two visits West Lake.",
            UnifiedCommittedInputRoute.BACKGROUND_UPDATE,
        ),
        (
            "刚才的修改加进去了吗？",
            UnifiedCommittedInputRoute.BACKGROUND_STATUS,
        ),
        (
            "第一天晚上给我留出的自由时间是几点？",
            UnifiedCommittedInputRoute.BACKGROUND_QUERY,
        ),
        ("后台现在做到哪了？", UnifiedCommittedInputRoute.BACKGROUND_STATUS),
        (
            "当前后台任务情况如何？",
            UnifiedCommittedInputRoute.BACKGROUND_STATUS,
        ),
        (
            "当前后台任务进展如何？",
            UnifiedCommittedInputRoute.BACKGROUND_STATUS,
        ),
        (
            "停止刚才的行程规划。",
            UnifiedCommittedInputRoute.BACKGROUND_CANCEL,
        ),
    ],
)
def test_unified_semantic_routes_cover_closed_protocol(
    text: str, route: UnifiedCommittedInputRoute
) -> None:
    resolved = VoiceTaskBridge().resolve_unified(committed(text), SCOPE, CURRENT)
    assert resolved.route is route
    assert resolved.provider == "local.closed_schema"
    if route in {
        UnifiedCommittedInputRoute.BACKGROUND_QUERY,
        UnifiedCommittedInputRoute.BACKGROUND_STATUS,
        UnifiedCommittedInputRoute.BACKGROUND_UPDATE,
        UnifiedCommittedInputRoute.BACKGROUND_CANCEL,
    }:
        assert resolved.task_id == CURRENT.task_id
        assert resolved.target_binding == "current_background_task"


@pytest.mark.parametrize(
    ("text", "route"),
    [
        (
            "不用停止后台任务，告诉我第二天最早的固定安排是什么。",
            UnifiedCommittedInputRoute.BACKGROUND_QUERY,
        ),
        ("不要取消，继续做。", UnifiedCommittedInputRoute.DIALOGUE),
        ("别停止后台任务，继续处理。", UnifiedCommittedInputRoute.DIALOGUE),
    ],
)
def test_unified_negated_cancel_has_no_cancel_route(
    text: str, route: UnifiedCommittedInputRoute
) -> None:
    resolved = VoiceTaskBridge().resolve_unified(committed(text), SCOPE, CURRENT)
    assert resolved.route is route
    assert resolved.route is not UnifiedCommittedInputRoute.BACKGROUND_CANCEL


@pytest.mark.parametrize(
    "text",
    [
        "帮我介绍杭州。",
        "杭州有什么特色菜？",
        "可以改一下吗？",
        "不要修改当前后台任务。",
        "Don't change the current background task.",
    ],
)
def test_unified_low_confidence_or_negated_update_has_zero_task_route(
    text: str,
) -> None:
    resolved = VoiceTaskBridge().resolve_unified(committed(text), SCOPE, CURRENT)
    assert resolved.route is UnifiedCommittedInputRoute.DIALOGUE
    assert resolved.task_id is None
    assert resolved.instruction is None


def test_unified_update_binds_exact_current_task_and_instruction_span() -> None:
    text = "把第二天下午改成西湖，晚上给我留出自由时间。"
    resolved = VoiceTaskBridge().resolve_unified(committed(text), SCOPE, CURRENT)
    assert resolved.route is UnifiedCommittedInputRoute.BACKGROUND_UPDATE
    assert resolved.task_id == CURRENT.task_id
    assert resolved.target_binding == "current_background_task"
    assert resolved.source_span is not None
    assert resolved.instruction == text[:-1]
    assert text[resolved.source_span.start : resolved.source_span.end] == text[:-1]


def test_unified_route_identity_is_bound_to_current_task_context() -> None:
    first = VoiceTaskBridge().resolve_unified(
        committed("后台现在做到哪了？"), SCOPE, CURRENT
    )
    second = VoiceTaskBridge().resolve_unified(
        committed("后台现在做到哪了？"),
        SCOPE,
        replace(CURRENT, task_id="task-current-2"),
    )
    assert first.resolution_id != second.resolution_id
    assert first.current_task_sha256 != second.current_task_sha256


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
