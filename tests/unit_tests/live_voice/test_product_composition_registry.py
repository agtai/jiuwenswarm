# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping, NoReturn, cast

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.message import Message, ReqMethod
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
    CommandEnvelope,
    ContractViolation,
    ErrorCode,
    MAX_SAFE_INTEGER,
    OriginRef,
    ProducerRef,
    ResponseRef,
    ResultEnvelope,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    TurnCommitLedger,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    ExecutorDeliveryResult,
    FormalTaskSpec,
    FormalTaskState,
    FormalTaskViolation,
    PersistentTaskEvent,
    PersistentTaskRecord,
    ResolvedTaskContext,
    TaskResultArtifact,
    TaskResultAvailability,
    TaskResultRecord,
)
from jiuwenswarm.gateway.app_gateway import _inject_live_voice_gateway_voice_claim
from jiuwenswarm.server.live_voice.batch_speech import (
    FormalBatchSpeechService,
    UnavailableBatchSpeechProvider,
)
from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
    P3AuthenticatedComposition,
    P3RouteResult,
    PreparedP3MutationConfirmation,
)
from jiuwenswarm.server.live_voice.p2_response_generation_store import (
    SqliteP2ResponseGenerationOwner,
)
from jiuwenswarm.server.live_voice.p3_confirmation import (
    BoundedP3ConfirmationOwner,
    P3ConfirmationBinding,
    P3ConfirmationOwnerContext,
)
from jiuwenswarm.server.live_voice.p3_product_confirmation import (
    ProductP3ConfirmationForwarder,
)
from jiuwenswarm.server.live_voice.product_authority import (
    AuthorityResourceBinding,
    TrustedAuthorityCandidate,
)
from jiuwenswarm.server.live_voice.product_p2_interaction_adapter import (
    P2LeaseState,
)
from jiuwenswarm.server.live_voice.product_composition_registry import (
    AgentServerProductCompositionRegistry,
    PRODUCT_COMPOSITION_ENABLE_ENV,
    PRODUCT_CRITICAL_INPUT_ENABLE_ENV,
    PRODUCT_DEMO_POLICY_BYPASS_ENV,
    PRODUCT_P2_ENABLE_ENV,
    PRODUCT_P3_TEXT_ENABLE_ENV,
    ProductCompositionSettings,
    _ProgressDelivery,
    _VoiceTaskOrigin,
    create_product_composition_registry_from_environment,
)
from jiuwenswarm.server.live_voice.product_p3_text_adapter import (
    ProductP3AuthorizedQuery,
)
from jiuwenswarm.server.live_voice.task_event_subscription import (
    TaskEventSubscription,
)
from jiuwenswarm.server.live_voice.task_progress_return import (
    TaskProgressNotificationIntent,
    TaskProgressOriginBinding,
    TaskProgressOriginKind,
    TaskProgressTextEvent,
    _evidence_id,
    project_task_progress_event,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectProjectCodeExecutorAdapter,
    FORMAL_PROJECT_EXECUTOR_ID,
    ProjectExecutionBinding,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from jiuwenswarm.server.live_voice.unified_committed_input import (
    SqliteUnifiedCommittedInputJournal,
)
from jiuwenswarm.server.live_voice.voice_task_bridge import (
    ResolvedTaskIntent,
    TaskIntentDisposition,
    TaskIntentSourceSpan,
    VoiceTaskBridge,
    VoiceTaskBridgeViolation,
    _resolution_identity,
)


NOW = "2030-01-01T00:00:00Z"
EXPIRY = "2035-01-01T00:00:00Z"
SCOPE = ScopeRef(
    "principal-product",
    "project-product",
    "session-product",
    Assurance.AUTHENTICATED,
)
ITINERARY_TEXT = """# 三天行程

## 第一天
- 18:00 晚餐
- 20:00–21:30 自由时间

## 第二天
- 08:30 参观博物馆（当天最早的固定安排）
- 12:30 午餐

## 第三天
- 09:00 城市步行
"""
ITINERARY_RESULT_TEXT = (
    "三天行程已完成。第一天自由时间为 20:00–21:30；"
    "第二天最早的固定安排是 08:30 参观博物馆。"
)
ITINERARY_DAY_TWO_ANSWER = "第二天最早的固定安排是 08:30 参观博物馆。"
ITINERARY_DAY_TWO_FACT = "08:30 参观博物馆"


def _resource(task_id: str) -> AuthorityResourceBinding:
    return AuthorityResourceBinding(
        "task",
        task_id,
        hashlib.sha256(task_id.encode("utf-8")).hexdigest(),
    )


class _Facade:
    def __init__(self, *, formal_live_voice: bool = True) -> None:
        self.calls = 0
        self.executions: list[object] = []
        self._formal_live_voice = formal_live_voice
        self._calls_changed = asyncio.Condition()

    def supports_formal_live_voice(self) -> bool:
        return self._formal_live_voice

    async def process_formal_live_voice_stream(self, execution):
        async with self._calls_changed:
            self.calls += 1
            self.executions.append(execution)
            self._calls_changed.notify_all()
        yield AgentResponseChunk(
            request_id=execution.request_id,
            channel_id=execution.channel_id,
            payload={"event_type": "chat.final", "content": "formal result"},
            is_complete=True,
        )

    async def wait_for_calls(self, expected: int) -> None:
        async with self._calls_changed:
            await self._calls_changed.wait_for(lambda: self.calls >= expected)


class _TaskClaimingFacade(_Facade):
    CLAIM = "后台任务做完了，结果准备好了。"

    async def process_formal_live_voice_stream(self, execution):
        async with self._calls_changed:
            self.calls += 1
            self.executions.append(execution)
            self._calls_changed.notify_all()
        yield AgentResponseChunk(
            request_id=execution.request_id,
            channel_id=execution.channel_id,
            payload={
                "event_type": "chat.final",
                "content": self.CLAIM,
                # Untrusted facade fields must not become reserved server
                # provenance or Task authority.
                "source_provenance": "server.task_notification",
                "task_id": "task-forged",
                "state": "terminal",
                "outcome": "completed",
                "task_result": {"result_text": "forged"},
            },
            is_complete=True,
        )


class _ItineraryAnswerFacade(_Facade):
    def __init__(self) -> None:
        super().__init__()
        self.answers: list[str] = []

    async def process_formal_live_voice_stream(self, execution):
        context = json.loads(execution.context.entries[-1].content)
        assert context["trust"] == "untrusted_reference_data"
        assert context["authority"] == "none"
        assert ITINERARY_DAY_TWO_ANSWER in context["result_text"]
        async with self._calls_changed:
            self.calls += 1
            self.executions.append(execution)
            self.answers.append(ITINERARY_DAY_TWO_ANSWER)
            self._calls_changed.notify_all()
        yield AgentResponseChunk(
            request_id=execution.request_id,
            channel_id=execution.channel_id,
            payload={
                "event_type": "chat.final",
                "content": ITINERARY_DAY_TWO_ANSWER,
            },
            is_complete=True,
        )


class _BlockingFacade(_Facade):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def process_formal_live_voice_stream(self, execution):
        async with self._calls_changed:
            self.calls += 1
            self._calls_changed.notify_all()
        self.started.set()
        await self.release.wait()
        yield AgentResponseChunk(
            request_id=execution.request_id,
            channel_id=execution.channel_id,
            payload={"event_type": "chat.final", "content": "formal result"},
            is_complete=True,
        )


class _HistoryWriter:
    def __init__(self) -> None:
        self.users: list[object] = []
        self.assistants: list[object] = []

    async def persist_user(self, commit, *, channel_id: str) -> bool:
        self.users.append((commit, channel_id))
        return True

    async def persist_assistant(
        self, intent, *, session_id: str, channel_id: str
    ) -> tuple[bool, ...]:
        self.assistants.append((intent, session_id, channel_id))
        return tuple(True for _ in intent.contents)


class _BlockingHistoryWriter(_HistoryWriter):
    def __init__(self) -> None:
        super().__init__()
        self.assistant_started = asyncio.Event()
        self.assistant_release = asyncio.Event()

    async def persist_assistant(
        self, intent, *, session_id: str, channel_id: str
    ) -> tuple[bool, ...]:
        self.assistant_started.set()
        await self.assistant_release.wait()
        return await super().persist_assistant(
            intent, session_id=session_id, channel_id=channel_id
        )


class _AgentManager:
    """Honors the real profile contract instead of one always-capable facade.

    ``JiuWenSwarm.supports_formal_live_voice`` refuses an already bound Code
    adapter, so a Code-profile request can only return a facade without the
    formal Live Voice seam. A fake that reports the capability for every
    profile hides which profile the caller actually asked for.
    """

    def __init__(self) -> None:
        self.agent = _Facade()
        self.code_agent = _Facade(formal_live_voice=False)
        self.get_calls: list[tuple[object, ...]] = []
        self.pins = 0
        self.unpins = 0

    async def get_agent(self, *args):
        self.get_calls.append(args)
        mode = str(args[1]) if len(args) > 1 else "agent"
        return self.code_agent if mode == "code" else self.agent

    def pin_agent(self, agent) -> None:
        assert agent in (self.agent, self.code_agent)
        self.pins += 1

    def unpin_agent(self, agent) -> None:
        assert agent in (self.agent, self.code_agent)
        self.unpins += 1


@dataclass(frozen=True, slots=True)
class _SubscriptionSnapshot:
    task_id: str


class _Subscription:
    def __init__(
        self,
        binding: TaskProgressOriginBinding,
        *,
        event: PersistentTaskEvent | None,
        close_failures: int = 0,
    ) -> None:
        self.binding = binding
        self.events = deque(() if event is None else (event,))
        self.close_failures = close_failures
        self.start_calls = 0
        self.close_calls = 0
        self._closed = asyncio.Event()

    def snapshot(self) -> _SubscriptionSnapshot:
        return _SubscriptionSnapshot(self.binding.task_id)

    async def start(self) -> bool:
        self.start_calls += 1
        return True

    async def next_event(self) -> PersistentTaskEvent:
        if self.events:
            return self.events.popleft()
        await self._closed.wait()
        raise StopAsyncIteration

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_failures:
            self.close_failures -= 1
            raise RuntimeError("injected close failure")
        self._closed.set()


class _P3Composition(P3AuthenticatedComposition):
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.authority_calls: list[dict[str, object]] = []
        self.query_calls: list[ProductP3AuthorizedQuery] = []
        self.retry_admission_calls: list[dict[str, object]] = []
        self.retry_admission_failure: FormalTaskViolation | None = None
        self.subscription_calls: list[TaskProgressOriginBinding] = []
        self.fail_authority: FormalTaskViolation | None = None
        self.correlation_override: str | None = None
        self.subscription_event = True
        self.subscription_event_type = "task.running"
        self.subscription_close_failures = 0

    def resolve_product_authority_candidate(self, **kwargs):
        self.authority_calls.append(dict(kwargs))
        if self.fail_authority is not None:
            raise self.fail_authority
        if kwargs["bearer_token"] != "trusted-token":
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHENTICATION_REQUIRED",
                "formal task authentication is required",
                ErrorCode.UNAUTHENTICATED,
            )
        operation = str(kwargs["operation"])
        task_id = cast(str | None, kwargs.get("task_id"))
        capabilities = cast(frozenset[str], kwargs["required_capabilities"])
        correlation_id = self.correlation_override or str(kwargs["correlation_id"])
        context = ResolvedTaskContext(
            source="test.server.project",
            stable_id=SCOPE.project_id or "",
            uri=self.project_dir.as_uri(),
            revision_kind="version",
            revision_value="revision-1",
            scope=SCOPE,
            permissions=("project.write", "task.execute"),
            expires_at=EXPIRY,
            redaction_policy_id="test-policy",
            redacted=False,
            redacted_fields=(),
        )
        return (
            TrustedAuthorityCandidate(
                principal_id=SCOPE.subject_id,
                session_id=SCOPE.session_id or "",
                project_id=SCOPE.project_id,
                scope=SCOPE,
                allowed_operations=frozenset({operation}),
                allowed_capabilities=capabilities,
                expires_at=EXPIRY,
                assurance=Assurance.AUTHENTICATED,
                source="test.server.product",
                correlation_id=correlation_id,
                resource=None if task_id is None else _resource(task_id),
            ),
            context,
        )

    def query(
        self,
        query: ProductP3AuthorizedQuery,
        *,
        now: str | None = None,
    ) -> ResultEnvelope:
        self.query_calls.append(query)
        return ResultEnvelope.success(
            owner=query.envelope,
            result={"query_type": query.envelope.query_type},
            observed_at=now or NOW,
        )

    async def read_product_status_retry_admission(
        self,
        *,
        bearer_token: object,
        session_id: str,
        task_id: str,
    ) -> dict[str, object]:
        self.retry_admission_calls.append(
            {
                "bearer_token": bearer_token,
                "session_id": session_id,
                "task_id": task_id,
            }
        )
        if self.retry_admission_failure is not None:
            raise self.retry_admission_failure
        if bearer_token != "trusted-token" or session_id != SCOPE.session_id:
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHENTICATION_REQUIRED",
                "formal task authentication is required",
                ErrorCode.UNAUTHENTICATED,
            )
        return {
            "eligible": False,
            "reason": "TASK_RETRY_EXECUTOR_CLEANUP_PENDING",
            "task_id": task_id,
            "attempt_id": None,
            "attempt_number": None,
        }

    def create_product_subscription(
        self,
        _authorization,
        binding: TaskProgressOriginBinding,
    ) -> TaskEventSubscription:
        self.subscription_calls.append(binding)
        event = (
            PersistentTaskEvent(
                event_id="event-running-1",
                task_id=binding.task_id,
                attempt_id="attempt-1",
                scope=binding.scope,
                seq=7,
                event_type=self.subscription_event_type,
                state=(
                    "terminal"
                    if self.subscription_event_type == "task.terminal"
                    else "running"
                ),
                outcome=(
                    "completed"
                    if self.subscription_event_type == "task.terminal"
                    else None
                ),
                producer="task_core",
                source_event_id=None,
                causation_id="cause-running-1",
                correlation_id=binding.correlation_id,
                occurred_at=NOW,
                details={},
            )
            if self.subscription_event
            else None
        )
        return cast(
            TaskEventSubscription,
            _Subscription(
                binding,
                event=event,
                close_failures=self.subscription_close_failures,
            ),
        )


def _background_task(
    project_dir: Path,
    *,
    state: FormalTaskState = FormalTaskState.RUNNING,
    outcome: TerminalOutcome | None = None,
    task_id: str = "task-current-1",
    attempt_id: str = "attempt-current-1",
) -> PersistentTaskRecord:
    context = ResolvedTaskContext(
        source="test.server.project",
        stable_id=SCOPE.project_id or "",
        uri=project_dir.resolve().as_uri(),
        revision_kind="version",
        revision_value="revision-1",
        scope=SCOPE,
        permissions=("project.write", "task.execute"),
        expires_at=EXPIRY,
        redaction_policy_id="test-policy",
    )
    return PersistentTaskRecord(
        task_id=task_id,
        scope=SCOPE,
        spec=FormalTaskSpec(
            name="Three-day itinerary",
            instruction="Plan a three-day itinerary.",
            origin=OriginRef("structured", None, None),
            context=context,
            executor_id="jiuwenswarm_code_agent.project_code",
            required_capabilities=("task.create",),
            side_effect_class="project_mutation",
            attributes=(),
        ),
        state=state,
        attempt_id=attempt_id,
        correlation_id="correlation-p2",
        cancel_requested=False,
        dispatch_fenced=False,
        outcome=outcome,
        reconciliation_state=None,
        reconciliation_reason=None,
        create_command_id=f"command-create-{task_id}",
        predecessor_task_id=None,
        revision_number=1,
        event_head=3,
    )


class _ItineraryProjectExecutor:
    def __init__(self) -> None:
        self.finished = asyncio.Event()
        self.requests: list[object] = []

    async def process_background_code_task_stream(self, request):
        self.requests.append(request)
        project = Path(request.params["project_dir"]).resolve()
        try:
            (project / "itinerary.md").write_text(
                ITINERARY_TEXT,
                encoding="utf-8",
                newline="\n",
            )
            yield AgentResponseChunk(
                request_id=request.request_id,
                channel_id=request.channel_id,
                payload={
                    "event_type": "chat.final",
                    "content": ITINERARY_RESULT_TEXT,
                },
                is_complete=True,
            )
        finally:
            self.finished.set()


class _ItineraryBindingResolver:
    def __init__(self, binding: ProjectExecutionBinding) -> None:
        self.binding = binding
        self.calls = 0

    async def resolve(self, _spec, *, for_dispatch: bool):
        assert for_dispatch is True
        self.calls += 1
        return self.binding


class _UnifiedP3Composition(_P3Composition):
    def __init__(self, project_dir: Path) -> None:
        super().__init__(project_dir)
        self.current: PersistentTaskRecord | None = None
        self.handle_calls: list[tuple[str, dict[str, object], dict[str, object]]] = []
        self.read_current_calls = 0
        self.result_availability = "not_ready"
        self.result_reason = "TASK_RESULT_NOT_READY"
        self.result_record: dict[str, object] | None = None
        self.create_state = FormalTaskState.RUNNING
        self.create_receipt_extra: dict[str, object] = {}
        self.create_receipt_omit: set[str] = set()
        self.create_receipt_override: object | None = None
        self.create_effects = 0
        self.adjust_effects = 0
        self._create_commands: set[str] = set()
        self._adjust_commands: set[str] = set()
        self.adjustment_events: list[dict[str, object]] = []
        self.known_tasks: dict[str, PersistentTaskRecord] = {}

    async def read_current_background_task(
        self,
        *,
        bearer_token: object,
        session_id: str,
    ) -> PersistentTaskRecord | None:
        self.read_current_calls += 1
        if bearer_token != "trusted-token" or session_id != SCOPE.session_id:
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHENTICATION_REQUIRED",
                "formal task authentication is required",
                ErrorCode.UNAUTHENTICATED,
            )
        return self.current

    async def read_background_task(
        self,
        *,
        bearer_token: object,
        session_id: str,
        task_id: str,
    ) -> PersistentTaskRecord:
        if bearer_token != "trusted-token" or session_id != SCOPE.session_id:
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHENTICATION_REQUIRED",
                "formal task authentication is required",
                ErrorCode.UNAUTHENTICATED,
            )
        if self.current is not None and self.current.task_id == task_id:
            return self.current
        retained = self.known_tasks.get(task_id)
        if retained is None:
            raise FormalTaskViolation(
                "FORMAL_TASK_NOT_FOUND",
                "formal task was not found",
                ErrorCode.NOT_FOUND,
            )
        return retained

    async def read_task_notification_facts(
        self,
        *,
        task_id: str,
        attempt_id: str,
        scope: ScopeRef,
    ) -> tuple[
        PersistentTaskRecord,
        TaskResultAvailability,
        TaskResultRecord | None,
        str,
    ]:
        task = await self.read_background_task(
            bearer_token="trusted-token",
            session_id=scope.session_id or "",
            task_id=task_id,
        )
        if task.attempt_id != attempt_id:
            raise FormalTaskViolation(
                "TASK_NOTIFICATION_ATTEMPT_MISMATCH",
                "terminal notification attempt changed",
                ErrorCode.STALE,
            )
        availability = TaskResultAvailability(self.result_availability)
        record = None
        if availability is TaskResultAvailability.AVAILABLE:
            raw = self.result_record
            assert raw is not None
            record = TaskResultRecord(
                task_id=str(raw["task_id"]),
                attempt_id=str(raw["attempt_id"]),
                source_event_id=str(raw["source_event_id"]),
                result_text=str(raw["result_text"]),
                artifacts=tuple(
                    TaskResultArtifact(
                        relative_path=str(artifact["relative_path"]),
                        sha256=str(artifact["sha256"]),
                    )
                    for artifact in cast(list[dict[str, object]], raw["artifacts"])
                ),
                completed_at=str(raw["completed_at"]),
            )
        return task, availability, record, self.result_reason

    async def handle(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
        **policy: object,
    ) -> P3RouteResult:
        self.handle_calls.append((operation, dict(params), dict(policy)))
        if (
            params.get("auth_token") != "trusted-token"
            or session_id != SCOPE.session_id
        ):
            return P3RouteResult(
                False,
                {
                    "request_id": request_id,
                    "ok": False,
                    "result": None,
                    "error": {"reason": "FORMAL_TASK_AUTHENTICATION_REQUIRED"},
                },
            )
        if operation in {
            "task.create",
            "task.adjust",
            "task.cancel",
        } and not policy.get("trusted_demo_policy_bypass", False):
            return P3RouteResult(
                False,
                {
                    "request_id": request_id,
                    "ok": False,
                    "result": None,
                    "error": {"reason": "FORMAL_TASK_CONFIRMATION_REQUIRED"},
                },
            )
        if operation == "task.create":
            command_id = str(params["command_id"])
            if command_id not in self._create_commands:
                if (
                    self.current is not None
                    and self.current.state is not FormalTaskState.TERMINAL
                ):
                    return P3RouteResult(
                        False,
                        {
                            "request_id": request_id,
                            "ok": False,
                            "result": None,
                            "error": {"reason": "CURRENT_BACKGROUND_TASK_ACTIVE"},
                        },
                    )
                self._create_commands.add(command_id)
                self.create_effects += 1
                self.current = _background_task(
                    self.project_dir,
                    state=self.create_state,
                )
                self.known_tasks[self.current.task_id] = self.current
            assert self.current is not None
            result: dict[str, object] = {
                "task_id": self.current.task_id,
                "attempt_id": self.current.attempt_id,
                "state": self.current.state.value,
                "outbox_id": "outbox-current-1",
            }
            result.update(self.create_receipt_extra)
            for key in self.create_receipt_omit:
                result.pop(key, None)
            if self.create_receipt_override is not None:
                result = self.create_receipt_override
        elif operation == "task.adjust":
            assert self.current is not None
            assert self.current.state is not FormalTaskState.TERMINAL
            assert params["task_id"] == self.current.task_id
            command_id = str(params["command_id"])
            if command_id not in self._adjust_commands:
                self._adjust_commands.add(command_id)
                self.adjust_effects += 1
                self.adjustment_events.append(
                    {
                        "event_id": f"event-adjust-requested-{self.adjust_effects}",
                        "task_id": self.current.task_id,
                        "attempt_id": self.current.attempt_id,
                        "scope": SCOPE.to_dict(),
                        "seq": self.current.event_head + self.adjust_effects,
                        "event_type": "task.adjust_requested",
                        "state": self.current.state.value,
                        "outcome": None,
                        "producer": "task_core.control",
                        "source_event_id": None,
                        "causation_id": command_id,
                        "correlation_id": self.current.correlation_id,
                        "occurred_at": NOW,
                        "details": {"command_id": command_id},
                    }
                )
            result = {
                "task_id": self.current.task_id,
                "attempt_id": self.current.attempt_id,
                "state": "pending",
                "command_id": command_id,
                "accepted": True,
            }
        elif operation == "task.cancel":
            result = {
                "task_id": params["task_id"],
                "state": self.current.state.value if self.current else "running",
                "cancel_acknowledged": True,
                "accepted": True,
            }
        elif operation == "task.status":
            result = {
                "task": (
                    self.current.to_dict()
                    if self.current is not None
                    else {
                        "task_id": params["task_id"],
                        "state": FormalTaskState.RUNNING.value,
                        "outcome": None,
                        "event_head": 0,
                    }
                ),
                "attempt": {
                    "attempt_id": (
                        self.current.attempt_id
                        if self.current is not None
                        else "attempt-current-1"
                    ),
                    "state": "running",
                },
            }
        elif operation == "task.result":
            result = {
                "task_id": params["task_id"],
                "availability": self.result_availability,
                "reason": self.result_reason,
                "task_result": self.result_record,
            }
        elif operation == "task.events":
            result = {
                "task_id": params["task_id"],
                "events": list(self.adjustment_events),
                "next_after_seq": (
                    self.adjustment_events[-1]["seq"]
                    if self.adjustment_events
                    else int(params.get("after_seq", -1))
                ),
            }
        else:
            raise AssertionError(f"unexpected unified P3 operation: {operation}")
        return P3RouteResult(
            True,
            {
                "request_id": request_id,
                "ok": True,
                "result": result,
                "error": None,
            },
        )


class _StoreBackedUnifiedP3(_UnifiedP3Composition):
    def __init__(self, project_dir: Path, store: SqliteTaskStore) -> None:
        super().__init__(project_dir)
        self.store = store

    async def read_current_background_task(
        self,
        *,
        bearer_token: object,
        session_id: str,
    ) -> PersistentTaskRecord | None:
        self.read_current_calls += 1
        if bearer_token != "trusted-token" or session_id != SCOPE.session_id:
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHENTICATION_REQUIRED",
                "formal task authentication is required",
                ErrorCode.UNAUTHENTICATED,
            )
        return self.store.get_current_background_task(SCOPE, session_id=session_id)

    async def handle(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
        **policy: object,
    ) -> P3RouteResult:
        if operation != "task.result":
            return await super().handle(
                operation=operation,
                params=params,
                request_id=request_id,
                session_id=session_id,
                **policy,
            )
        self.handle_calls.append((operation, dict(params), dict(policy)))
        if (
            params.get("auth_token") != "trusted-token"
            or session_id != SCOPE.session_id
        ):
            raise AssertionError("itinerary fixture must use its exact authority")
        availability, record, reason = self.store.task_result(
            str(params["task_id"]), SCOPE
        )
        return P3RouteResult(
            True,
            {
                "request_id": request_id,
                "ok": True,
                "result": {
                    "task_id": params["task_id"],
                    "availability": availability.value,
                    "reason": reason,
                    "task_result": (
                        record.to_dict()
                        if availability is TaskResultAvailability.AVAILABLE
                        and record is not None
                        else None
                    ),
                },
                "error": None,
            },
        )


class _MutationP3Composition(_P3Composition):
    def __init__(
        self,
        project_dir: Path,
        verifier: ProductP3ConfirmationForwarder,
    ) -> None:
        super().__init__(project_dir)
        self.verifier = verifier
        self.prepare_calls: list[tuple[str, dict[str, object]]] = []
        self.mutation_calls: list[tuple[str, dict[str, object]]] = []
        self.replay_authority_revoked = False

    async def prepare_mutation_confirmation(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        session_id: str | None,
    ) -> PreparedP3MutationConfirmation:
        if params.get("auth_token") != "trusted-token":
            raise FormalTaskViolation(
                "FORMAL_TASK_AUTHENTICATION_REQUIRED",
                "formal task authentication is required",
                ErrorCode.UNAUTHENTICATED,
            )
        if session_id != SCOPE.session_id or params.get("session_id") != session_id:
            raise FormalTaskViolation(
                "FORMAL_TASK_SESSION_MISMATCH",
                "formal task session does not match",
                ErrorCode.PERMISSION_DENIED,
            )
        self.prepare_calls.append((operation, dict(params)))
        target = (
            str(params["task_id"])
            if operation in {"task.cancel", "task.retry"}
            else None
        )
        intent = hashlib.sha256(
            repr(
                (
                    operation,
                    params.get("command_id"),
                    target,
                    params.get("name"),
                    params.get("instruction"),
                    params.get("model_intent"),
                )
            ).encode("utf-8")
        ).hexdigest()
        return PreparedP3MutationConfirmation(
            binding=P3ConfirmationBinding(
                principal_id=SCOPE.subject_id,
                scope=SCOPE,
                operation=operation,
                command_id=str(params["command_id"]),
                target_task_id=target,
                intent_fingerprint=intent,
            ),
            correlation_id=str(params["correlation_id"]),
            issued_at=str(params["issued_at"]),
            observed_at=NOW,
        )

    async def reauthorize_mutation_replay(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        session_id: str | None,
        expected_binding: P3ConfirmationBinding,
    ) -> None:
        if self.replay_authority_revoked:
            raise FormalTaskViolation(
                "TASK_CONTEXT_PERMISSION_MISSING",
                "formal task authority was revoked",
                ErrorCode.PERMISSION_DENIED,
            )
        prepared = await self.prepare_mutation_confirmation(
            operation=operation,
            params=params,
            session_id=session_id,
        )
        if prepared.binding != expected_binding:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_BINDING_MISMATCH",
                "formal task replay binding changed",
                ErrorCode.PERMISSION_DENIED,
            )

    async def handle(
        self,
        *,
        operation: str,
        params: Mapping[str, object],
        request_id: str,
        session_id: str | None,
    ) -> P3RouteResult:
        prepared = await self.prepare_mutation_confirmation(
            operation=operation,
            params=params,
            session_id=session_id,
        )
        self.verifier.verify_and_consume(
            str(params["confirmation_id"]),
            prepared.binding,
            now=NOW,
        )
        self.mutation_calls.append((operation, dict(params)))
        task_id = (
            "task-created-natural-1"
            if operation == "task.create"
            else params.get("task_id")
        )
        return P3RouteResult(
            True,
            {
                "request_id": request_id,
                "ok": True,
                "result": {
                    "accepted": True,
                    "operation": operation,
                    "task_id": task_id,
                },
                "error": None,
            },
        )


def _voice_mutation_registry(
    tmp_path: Path,
    *,
    commit_ledger: TurnCommitLedger,
) -> tuple[
    AgentServerProductCompositionRegistry,
    _MutationP3Composition,
    BoundedP3ConfirmationOwner,
]:
    owner = BoundedP3ConfirmationOwner(
        tmp_path / "voice-confirmations.sqlite3", enabled=True
    )
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=True,
            p3_text_enabled=False,
            p3_mutation_enabled=True,
        ),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
        commit_ledger=commit_ledger,
    )
    return registry, composition, owner


def _registry(
    tmp_path: Path,
    *,
    p2: bool = True,
    p3: bool = True,
    push_success: bool = True,
    commit_ledger: TurnCommitLedger | None = None,
    critical_input: bool = False,
    unified: bool = False,
):
    p3_composition = _P3Composition(tmp_path)
    manager = _AgentManager()
    pushed: list[dict[str, object]] = []

    async def push(message: dict[str, object]) -> bool:
        pushed.append(message)
        return push_success

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=p2,
            p3_text_enabled=p3,
            critical_input_enabled=critical_input,
        ),
        p3_composition=p3_composition,
        agent_manager=manager,
        push_text_event=push,
        commit_ledger=commit_ledger,
        unified_journal=(
            SqliteUnifiedCommittedInputJournal(tmp_path / "unified.sqlite3")
            if unified
            else None
        ),
    )
    return registry, p3_composition, manager, pushed


def _unified_registry(
    tmp_path: Path,
    *,
    p3_enabled: bool = True,
    mutation_enabled: bool = True,
    demo_policy_bypass: bool = False,
    critical_input: bool = False,
    composition: _UnifiedP3Composition | None = None,
) -> tuple[AgentServerProductCompositionRegistry, _UnifiedP3Composition, _AgentManager]:
    composition = composition or _UnifiedP3Composition(tmp_path)
    manager = _AgentManager()

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=True,
            p3_text_enabled=p3_enabled,
            p3_mutation_enabled=mutation_enabled,
            demo_policy_bypass_enabled=demo_policy_bypass,
            critical_input_enabled=critical_input,
        ),
        p3_composition=composition,
        agent_manager=manager,
        push_text_event=push,
        unified_journal=SqliteUnifiedCommittedInputJournal(
            tmp_path / "unified.sqlite3"
        ),
    )
    return registry, composition, manager


def _p2_params(**changes: object) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "correlation_id": "correlation-p2",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
    }
    params.update(changes)
    return params


def _p2_task_origin_params(*, stem: str, text: str) -> dict[str, object]:
    commit_id = f"commit-{stem}"
    turn_id = f"turn-{stem}"
    return _p2_params(
        commit_id=commit_id,
        turn_id=turn_id,
        committed_at=NOW,
        text=text,
        dispatch_target="task",
        gateway_voice_claim={
            "kind": "formal_speech_recognition",
            "speech_operation_id": f"speech-operation-{stem}",
            "capture_id": f"capture-{stem}",
            "capture_generation": 1,
            "session_id": "session-product",
            "correlation_id": "correlation-p2",
            "interaction_id": "interaction-1",
            "turn_id": turn_id,
            "commit_id": commit_id,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "critical_policy": "eligible",
        },
    )


def _unified_final_params(*, stem: str, text: str) -> dict[str, object]:
    params = _p2_task_origin_params(stem=stem, text=text)
    params.pop("dispatch_target")
    params["input_state"] = "final"
    return params


def _initialize_itinerary_fixture(project: Path) -> None:
    project.mkdir(parents=True)
    for arguments in (
        ("init",),
        ("config", "user.name", "Live Voice Itinerary Fixture"),
        ("config", "user.email", "live-voice-itinerary@example.invalid"),
        ("config", "core.autocrlf", "false"),
    ):
        subprocess.run(
            ["git", "-C", str(project), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    (project / "README.md").write_text(
        "isolated live voice itinerary fixture\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "-C", str(project), "add", "README.md"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(project), "commit", "-m", "fixture baseline"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _itinerary_spec(project: Path) -> FormalTaskSpec:
    return FormalTaskSpec(
        name="三天行程规划",
        instruction="根据这些要求制定三天的行程，并写入 itinerary.md。",
        origin=OriginRef("structured", None, None),
        context=ResolvedTaskContext(
            source="test.isolated_itinerary_fixture",
            stable_id=SCOPE.project_id or "",
            uri=project.resolve().as_uri(),
            revision_kind="version",
            revision_value="itinerary-fixture-v1",
            scope=SCOPE,
            permissions=("project.write", "task.execute"),
            expires_at=EXPIRY,
            redaction_policy_id="live_voice.itinerary_fixture.v1",
        ),
        executor_id=FORMAL_PROJECT_EXECUTOR_ID,
        required_capabilities=("task.create",),
        side_effect_class="project_mutation",
        attributes=(
            ("model_config_version", "catalog-v1"),
            ("model_identity", "default#0"),
        ),
    )


def _itinerary_command(spec: FormalTaskSpec) -> CommandEnvelope:
    return CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": "request-itinerary-fixture",
            "command_id": "command-itinerary-fixture",
            "command_type": "task.create",
            "issued_at": NOW,
            "scope": SCOPE.to_dict(),
            "correlation_id": "correlation-p2",
            "causation_id": None,
            "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
            "target_ref": {
                "kind": "task",
                "id": "create:command-itinerary-fixture",
            },
            "context_refs": [],
            "required_capabilities": ["task.create"],
            "payload": {
                "name": spec.name,
                "instruction": spec.instruction,
                "executor_id": spec.executor_id,
                "side_effect_class": spec.side_effect_class,
                "attributes": dict(spec.attributes),
            },
            "extensions": {},
        }
    )


async def _wait_itinerary_executor(
    adapter: DirectProjectCodeExecutorAdapter,
    attempt_id: str,
) -> None:
    for _ in range(500):
        record = adapter._journal.get(attempt_id)
        if not adapter._running and record is not None and record.source_seq >= 2:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("itinerary fixture Executor did not settle")


async def _ack_unified_presentation(
    registry: AgentServerProductCompositionRegistry,
    *,
    sequence: int,
    stem: str,
) -> int:
    for _ in range(4):
        sequence += 1
        polled = await asyncio.wait_for(
            registry.handle_p2_notification_next(
                params=_p2_params(notification_sequence=sequence),
                request_id=f"request-{stem}-notification-{sequence}",
                session_id=SCOPE.session_id,
            ),
            timeout=1,
        )
        assert polled.ok
        notification = cast(dict[str, object], polled.payload["result"])
        presentation = notification.get("presentation_unit")
        if not isinstance(presentation, dict):
            continue
        response = cast(dict[str, object], notification["response"])
        acknowledged = await registry.handle_p2_presentation_ack(
            params=_p2_params(
                response_id=response["response_id"],
                response_generation=response["response_generation"],
                surface=presentation["surface"],
                unit_id=presentation["unit_id"],
                contiguous_cursor=presentation["seq"],
                presented_at=NOW,
            ),
            request_id=f"request-{stem}-ack-{sequence}",
            session_id=SCOPE.session_id,
        )
        assert acknowledged.ok
        return sequence
    raise AssertionError("unified presentation was not delivered")


def _install_unified_history_writer(
    registry: AgentServerProductCompositionRegistry,
) -> _HistoryWriter:
    history = _HistoryWriter()
    route = registry._p2_routes[(SCOPE.session_id, "interaction-1")]
    route.activation_lease._runtime._history_writer = history
    return history


async def _close_unified_route(
    registry: AgentServerProductCompositionRegistry,
    *,
    stem: str,
) -> None:
    closed: P3RouteResult | None = None
    for attempt in range(20):
        closed = await registry.handle_p2_close(
            params=_p2_params(),
            request_id=f"request-{stem}-close-{attempt}",
            session_id=SCOPE.session_id,
        )
        if closed.ok:
            break
        assert cast(dict, closed.payload["error"])["reason"] == (
            "PRODUCT_P2_CLEANUP_PENDING"
        )
        await asyncio.sleep(0)
    if closed is None or not closed.ok:
        retained = registry._p2_routes[(SCOPE.session_id, "interaction-1")]
        raise AssertionError(
            (
                retained.lease.pending_adapter_ids,
                retained.activation_lease.snapshot(),
                retained.activation_lease._runtime.snapshot(),
            )
        )
    await registry.stop()


def _progress_params(**changes: object) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "task_id": "task-1",
        "correlation_id": "correlation-task-1",
        "origin_id": "web-surface-1",
        "generation_id": "web-session-generation-1",
        "generation": 1,
    }
    params.update(changes)
    return params


def _progress_ack_params(
    event: Mapping[str, object], **changes: object
) -> dict[str, object]:
    source = cast(Mapping[str, object], event["source_event"])
    progress = cast(Mapping[str, object], event["progress_event"])
    params = _progress_params(
        session_id=event["session_id"],
        task_id=event["task_id"],
        correlation_id=event["correlation_id"],
        origin_id=event["origin_id"],
        generation_id=event["generation_id"],
        generation=event["generation"],
        delivery_id=event["delivery_id"],
        source_event_id=source["event_id"],
        progress_event_id=progress["event_id"],
        seq=source["seq"],
        evidence_id=event["evidence_id"],
    )
    params.update(changes)
    return params


def _route(payload: dict[str, object], segment: str) -> dict[str, object]:
    manifest = cast(dict[str, object], payload["product_composition"])
    routes = cast(list[dict[str, object]], manifest["routes"])
    return next(item for item in routes if item["segment"] == segment)


def test_master_flag_off_constructs_no_registry_or_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PRODUCT_COMPOSITION_ENABLE_ENV, raising=False)

    class _Poison:
        def __getattribute__(self, _name):
            raise AssertionError("feature-off inspected P3 composition")

    result = create_product_composition_registry_from_environment(
        p3_composition=cast(P3AuthenticatedComposition, _Poison()),
        agent_manager=_Poison(),
        push_text_event=cast(object, _Poison()),
    )

    assert result is None


def test_critical_input_product_composition_flag_is_default_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PRODUCT_CRITICAL_INPUT_ENABLE_ENV, raising=False)
    assert ProductCompositionSettings.from_environment().critical_input_enabled is False
    monkeypatch.setenv(PRODUCT_CRITICAL_INPUT_ENABLE_ENV, "1")
    assert ProductCompositionSettings.from_environment().critical_input_enabled is True


def test_demo_policy_bypass_is_backend_configured_and_default_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PRODUCT_DEMO_POLICY_BYPASS_ENV, raising=False)
    assert (
        ProductCompositionSettings.from_environment().demo_policy_bypass_enabled
        is False
    )
    monkeypatch.setenv(PRODUCT_DEMO_POLICY_BYPASS_ENV, "1")
    assert (
        ProductCompositionSettings.from_environment().demo_policy_bypass_enabled is True
    )


@pytest.mark.asyncio
async def test_unified_final_dialogue_is_exactly_once_and_replays_by_voice_identity(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path, unified=True)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-unified-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok
    params = _unified_final_params(stem="dialogue-once", text="你好。")

    first = await registry.handle_unified_submit(
        params=params,
        request_id="request-unified-first",
        session_id="session-product",
        channel_id="web",
    )
    replay = await registry.handle_unified_submit(
        params=params,
        request_id="request-unified-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert first.ok
    assert first.payload["request_id"] == "request-unified-first"
    assert replay.payload["request_id"] == "request-unified-replay"
    assert {
        key: value for key, value in replay.payload.items() if key != "request_id"
    } == {key: value for key, value in first.payload.items() if key != "request_id"}
    assert manager.agent.calls == 1
    assert manager.agent.executions[0].commit.text == "你好。"
    assert manager.agent.executions[0].allow_tools is True
    await _close_unified_route(registry, stem="p3-off-create")


@pytest.mark.asyncio
async def test_unified_task_ack_never_contaminates_next_dialogue_context(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
    )
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-task-context-isolation-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    _install_unified_history_writer(registry)

    created = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="task-context-isolation-create",
            text="帮我在后台创建巴黎一日行程.md。",
        ),
        request_id="request-task-context-isolation-create",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert created.ok
    sequence = await _ack_unified_presentation(
        registry,
        sequence=0,
        stem="task-context-isolation-create",
    )
    assert manager.agent.calls == 0
    assert composition.create_effects == 1

    weather = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="task-context-isolation-weather",
            text="今天天气怎么样？",
        ),
        request_id="request-task-context-isolation-weather",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert weather.ok
    await asyncio.wait_for(manager.agent.wait_for_calls(1), timeout=1)
    execution = manager.agent.executions[0]
    assert execution.commit.text == "今天天气怎么样？"
    assert execution.context.entries == ()
    assert json.loads(execution.prompt_content())["selected_context"] == []
    assert composition.create_effects == 1
    assert composition.adjust_effects == 0
    assert [call[0] for call in composition.handle_calls] == ["task.create"]

    sequence = await _ack_unified_presentation(
        registry,
        sequence=sequence,
        stem="task-context-isolation-weather",
    )
    followup = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="task-context-isolation-followup",
            text="请继续回答。",
        ),
        request_id="request-task-context-isolation-followup",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert followup.ok
    await asyncio.wait_for(manager.agent.wait_for_calls(2), timeout=1)
    assert [entry.content for entry in manager.agent.executions[1].context.entries] == [
        "今天天气怎么样？",
        "formal result",
    ]
    assert composition.create_effects == 1
    assert composition.adjust_effects == 0
    assert [call[0] for call in composition.handle_calls] == ["task.create"]
    await _ack_unified_presentation(
        registry,
        sequence=sequence,
        stem="task-context-isolation-followup",
    )
    await _close_unified_route(registry, stem="task-context-isolation")


@pytest.mark.asyncio
async def test_dialogue_task_claim_remains_untrusted_and_has_zero_task_effect(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(tmp_path)
    current = _background_task(tmp_path)
    composition.current = current
    composition.known_tasks[current.task_id] = current
    claiming_agent = _TaskClaimingFacade()
    manager.agent = claiming_agent
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-dialogue-task-claim-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(registry)

    submitted = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="dialogue-task-claim",
            text="聊聊杭州今天的天气。",
        ),
        request_id="request-dialogue-task-claim",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert submitted.ok
    notification: dict[str, object] | None = None
    sequence = 0
    for _ in range(4):
        sequence += 1
        polled = await asyncio.wait_for(
            registry.handle_p2_notification_next(
                params=_p2_params(notification_sequence=sequence),
                request_id=f"request-dialogue-task-claim-notification-{sequence}",
                session_id=SCOPE.session_id,
            ),
            timeout=1,
        )
        assert polled.ok
        candidate = cast(dict[str, object], polled.payload["result"])
        if isinstance(candidate.get("presentation_unit"), dict):
            notification = candidate
            break
    assert notification is not None
    agent_event = cast(dict[str, object], notification["agent_event"])
    assert agent_event["text"] == _TaskClaimingFacade.CLAIM
    assert agent_event["source_provenance"] not in {
        "server.authoritative",
        "server.background.adjustment",
        "server.task_notification",
    }
    dialogue_provenance = json.loads(cast(str, agent_event["source_provenance"]))
    assert dialogue_provenance["kind"] == "committed_speech"
    assert "task_id" not in agent_event
    assert "state" not in agent_event
    assert "outcome" not in agent_event
    assert "task_result" not in agent_event
    presentation = cast(dict[str, object], notification["presentation_unit"])
    response = cast(dict[str, object], notification["response"])
    acknowledged = await registry.handle_p2_presentation_ack(
        params=_p2_params(
            response_id=response["response_id"],
            response_generation=response["response_generation"],
            surface=presentation["surface"],
            unit_id=presentation["unit_id"],
            contiguous_cursor=presentation["seq"],
            presented_at=NOW,
        ),
        request_id="request-dialogue-task-claim-ack",
        session_id=SCOPE.session_id,
    )
    assert acknowledged.ok

    assert claiming_agent.calls == 1
    assert composition.read_current_calls == 0
    assert composition.handle_calls == []
    assert composition.create_effects == 0
    assert composition.adjust_effects == 0
    assert composition.current is current
    assert registry._pending_terminal_notifications == {}
    assert registry._voice_task_origins == {}
    assert len(history.users) == 1
    assert len(history.assistants) == 1
    persisted_intent = history.assistants[0][0]
    persisted_text = b"".join(
        content.content_utf8 for content in persisted_intent.contents
    ).decode("utf-8")
    assert persisted_text == _TaskClaimingFacade.CLAIM
    assert not hasattr(persisted_intent, "task_id")
    assert not hasattr(persisted_intent, "state")
    assert not hasattr(persisted_intent, "outcome")
    assert not hasattr(persisted_intent, "task_result")
    await _close_unified_route(registry, stem="dialogue-task-claim")


@pytest.mark.asyncio
async def test_unified_continuous_dialogue_releases_all_in_memory_identity_state(
    tmp_path: Path,
) -> None:
    registry, _composition, manager = _unified_registry(tmp_path)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-soak-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    _install_unified_history_writer(registry)
    presentation_sequence = 0

    for index in range(40):
        stem = f"soak-{index}"
        result = await registry.handle_unified_submit(
            params=_unified_final_params(
                stem=stem,
                text=f"普通连续对话第 {index} 轮。",
            ),
            request_id=f"request-unified-{stem}",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
        assert result.ok
        assert registry._unified_operations == {}
        assert registry._critical_input_commit_generations == {}
        assert registry._critical_input_guarded_commits == set()
        presentation_sequence = await _ack_unified_presentation(
            registry,
            sequence=presentation_sequence,
            stem=stem,
        )

    assert manager.agent.calls == 40
    assert [
        entry.content for entry in manager.agent.executions[-1].context.entries
    ] == [
        "普通连续对话第 35 轮。",
        "formal result",
        "普通连续对话第 36 轮。",
        "formal result",
        "普通连续对话第 37 轮。",
        "formal result",
        "普通连续对话第 38 轮。",
        "formal result",
    ]
    await _close_unified_route(registry, stem="soak")


@pytest.mark.asyncio
async def test_unified_interim_and_request_content_conflict_have_zero_agent_effect(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path, unified=True)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-unified-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok
    interim = _unified_final_params(stem="interim", text="尚未结束")
    interim["input_state"] = "partial"
    rejected = await registry.handle_unified_submit(
        params=interim,
        request_id="request-unified-conflict",
        session_id="session-product",
        channel_id="web",
    )
    assert not rejected.ok
    assert cast(dict, rejected.payload["error"])["reason"] == "INPUT_NOT_FINAL"
    assert manager.agent.calls == 0

    accepted = await registry.handle_unified_submit(
        params=_unified_final_params(stem="accepted", text="第一条对话。"),
        request_id="request-unified-conflict",
        session_id="session-product",
        channel_id="web",
    )
    assert accepted.ok
    assert manager.agent.calls == 1
    conflict = await registry.handle_unified_submit(
        params=_unified_final_params(stem="changed", text="不同的内容。"),
        request_id="request-unified-conflict",
        session_id="session-product",
        channel_id="web",
    )
    assert not conflict.ok
    assert cast(dict, conflict.payload["error"])["reason"] == (
        "UNIFIED_INPUT_ID_CONFLICT"
    )
    assert manager.agent.calls == 1
    await registry.stop()


@pytest.mark.asyncio
async def test_unified_pre_admission_failures_release_critical_voice_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _composition, manager = _unified_registry(tmp_path)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-pre-admission-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok

    invalid_time = _unified_final_params(
        stem="pre-admission-time",
        text="invalid committed time must retain no identity",
    )
    invalid_time["committed_at"] = "not-a-timestamp"
    rejected_time = await registry.handle_unified_submit(
        params=invalid_time,
        request_id="request-unified-pre-admission-time",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert not rejected_time.ok
    assert manager.agent.calls == 0
    assert registry._critical_input_commit_generations == {}
    assert registry._critical_input_guarded_commits == set()

    route = registry._p2_routes[(SCOPE.session_id, "interaction-1")]
    original_select = route.activation_lease.select_formal_context

    async def fail_context(_binding: object) -> object:
        raise RuntimeError("private context selector failure")

    monkeypatch.setattr(
        route.activation_lease,
        "select_formal_context",
        fail_context,
    )
    context_params = _unified_final_params(
        stem="pre-admission-context",
        text="context failure must retain no identity",
    )
    rejected_context = await registry.handle_unified_submit(
        params=context_params,
        request_id="request-unified-pre-admission-context",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert not rejected_context.ok
    assert cast(dict, rejected_context.payload["error"])["reason"] == (
        "UNIFIED_INPUT_FAILED"
    )
    assert manager.agent.calls == 0
    assert registry._critical_input_commit_generations == {}
    assert registry._critical_input_guarded_commits == set()

    monkeypatch.setattr(
        route.activation_lease,
        "select_formal_context",
        original_select,
    )
    accepted = await registry.handle_unified_submit(
        params=context_params,
        request_id="request-unified-pre-admission-context-retry",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert accepted.ok
    assert manager.agent.calls == 1
    assert registry._critical_input_commit_generations == {}
    assert registry._critical_input_guarded_commits == set()
    await _close_unified_route(registry, stem="pre-admission")


@pytest.mark.asyncio
async def test_cancelled_unified_pre_admission_context_releases_identity_with_zero_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, composition, manager = _unified_registry(tmp_path)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-pre-admission-cancel-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    route = registry._p2_routes[(SCOPE.session_id, "interaction-1")]
    entered = asyncio.Event()
    blocker = asyncio.Event()

    async def block_context(_binding: object) -> object:
        entered.set()
        await blocker.wait()
        raise AssertionError("cancelled context selector resumed")

    monkeypatch.setattr(
        route.activation_lease,
        "select_formal_context",
        block_context,
    )
    caller = asyncio.create_task(
        registry.handle_unified_submit(
            params=_unified_final_params(
                stem="pre-admission-cancel",
                text="cancel before semantic admission",
            ),
            request_id="request-unified-pre-admission-cancel",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    assert manager.agent.calls == 0
    assert composition.handle_calls == []
    assert composition.read_current_calls == 0
    assert route.activation_lease._runtime.snapshot().published_notifications == 0
    assert registry._unified_operations == {}
    assert registry._critical_input_commit_generations == {}
    assert registry._critical_input_guarded_commits == set()
    gate = registry._critical_token_gate
    assert gate._candidate_fingerprints == {}
    assert gate._commit_interactions == {}
    assert gate._commit_generations == {}
    await _close_unified_route(registry, stem="pre-admission-cancel")


@pytest.mark.asyncio
async def test_unified_post_admission_rejection_is_durably_replayed(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path,
        critical_input=True,
    )
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-critical-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    params = _unified_final_params(
        stem="unified-critical",
        text="后台帮我 create task 42 on feature/safe。",
    )

    first = await registry.handle_unified_submit(
        params=params,
        request_id="request-unified-critical-first",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    replay = await registry.handle_unified_submit(
        params=params,
        request_id="request-unified-critical-replay",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert not first.ok
    assert first.payload["request_id"] == "request-unified-critical-first"
    assert replay.payload["request_id"] == "request-unified-critical-replay"
    assert {
        key: value for key, value in replay.payload.items() if key != "request_id"
    } == {key: value for key, value in first.payload.items() if key != "request_id"}
    assert cast(dict, first.payload["error"])["reason"] == (
        "CRITICAL_TOKEN_CLARIFICATION_REQUIRED"
    )
    assert composition.handle_calls == []
    assert manager.agent.calls == 0
    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        assert (
            connection.execute(
                "SELECT status FROM unified_committed_inputs"
            ).fetchone()[0]
            == "completed"
        )
    await registry.stop()


@pytest.mark.asyncio
async def test_unified_background_intent_fails_closed_when_p3_is_off(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path, p3_enabled=False, mutation_enabled=False
    )
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-off-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    _install_unified_history_writer(registry)

    result = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="p3-off-create",
            text="帮我根据这些要求制定三天的行程。",
        ),
        request_id="request-unified-off-create",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert result.ok
    assert manager.agent.calls == 0
    assert composition.read_current_calls == 0
    assert composition.handle_calls == []
    await _ack_unified_presentation(registry, sequence=0, stem="p3-off-create")
    await _close_unified_route(registry, stem="p3-off-create")


@pytest.mark.asyncio
async def test_unified_background_permission_denial_is_spoken_and_resumes_via_ack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, composition, manager = _unified_registry(tmp_path)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-denied-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(registry)

    async def deny_current(**_kwargs: object) -> None:
        raise FormalTaskViolation(
            "FORMAL_TASK_AUTHORIZATION_DENIED",
            "must not be exposed as an RPC-only failure",
            ErrorCode.PERMISSION_DENIED,
        )

    monkeypatch.setattr(composition, "read_current_background_task", deny_current)
    result = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="permission-denied-create",
            text="后台帮我制定三天行程。",
        ),
        request_id="request-unified-permission-denied",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert result.ok
    assert manager.agent.calls == 0
    assert composition.handle_calls == []
    await _ack_unified_presentation(
        registry,
        sequence=0,
        stem="permission-denied-create",
    )
    assert len(history.assistants) == 1
    spoken = b"".join(
        content.content_utf8 for content in history.assistants[0][0].contents
    ).decode("utf-8")
    assert spoken == "后台任务功能当前不可用。"
    await _close_unified_route(registry, stem="permission-denied-create")


@pytest.mark.asyncio
async def test_unified_dirty_worktree_create_reports_actionable_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, composition, manager = _unified_registry(tmp_path)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-dirty-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(registry)

    async def reject_dirty(**kwargs: object) -> P3RouteResult:
        return P3RouteResult(
            False,
            {
                "request_id": kwargs["request_id"],
                "ok": False,
                "result": None,
                "error": {"reason": "TASK_CONTEXT_WORKTREE_DIRTY"},
            },
        )

    monkeypatch.setattr(composition, "handle", reject_dirty)
    result = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="dirty-create",
            text="后台帮我根据项目中的订单整理三天行程。",
        ),
        request_id="request-unified-dirty-create",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert result.ok
    assert manager.agent.calls == 0
    await _ack_unified_presentation(registry, sequence=0, stem="dirty-create")
    spoken = b"".join(
        content.content_utf8 for content in history.assistants[0][0].contents
    ).decode("utf-8")
    assert spoken == "项目工作区有未提交修改，无法启动后台任务。"
    await _close_unified_route(registry, stem="dirty-create")


@pytest.mark.asyncio
async def test_unified_unknown_failure_never_exposes_exception_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, composition, manager = _unified_registry(tmp_path)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-safe-failure-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok

    async def fail_current_read(**_kwargs: object) -> None:
        raise RuntimeError(r"C:\private\itinerary\secret.txt")

    monkeypatch.setattr(
        composition,
        "read_current_background_task",
        fail_current_read,
    )
    rejected = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="safe-failure",
            text="后台现在做到哪了？",
        ),
        request_id="request-unified-safe-failure",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert not rejected.ok
    error = cast(dict[str, object], rejected.payload["error"])
    assert error["reason"] == "UNIFIED_INPUT_FAILED"
    assert error["message"] == "unified committed input failed closed"
    assert "private" not in json.dumps(rejected.payload)
    assert manager.agent.calls == 0
    await registry.stop()


@pytest.mark.asyncio
async def test_unified_journal_seal_failure_never_exposes_exception_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _composition, manager, _pushed = _registry(tmp_path, unified=True)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-seal-failure-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    journal = registry._unified_journal
    assert journal is not None

    def fail_seal(**_kwargs: object) -> None:
        raise RuntimeError(r"C:\private\journal\voice.sqlite3")

    async def fail_business(**_kwargs: object) -> None:
        raise RuntimeError(r"C:\private\agent\response.txt")

    monkeypatch.setattr(journal, "complete", fail_seal)
    monkeypatch.setattr(registry, "_run_unified_submit", fail_business)
    rejected = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="seal-failure",
            text="你好。",
        ),
        request_id="request-unified-seal-failure",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert not rejected.ok
    error = cast(dict[str, object], rejected.payload["error"])
    assert error == {
        "code": ErrorCode.UNAVAILABLE.value,
        "reason": "UNIFIED_INPUT_EXECUTION_LEASE_LOST",
        "message": "unified committed-input result could not be durably sealed",
    }
    assert "private" not in json.dumps(rejected.payload)
    assert manager.agent.calls == 0
    await registry.stop()


@pytest.mark.asyncio
async def test_unified_presentation_crash_window_recovers_without_duplicate_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
    )
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-crash-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(registry)
    journal = registry._unified_journal
    assert journal is not None
    complete = journal.complete
    complete_calls = 0

    def fail_after_first_presentation(**kwargs: object):
        nonlocal complete_calls
        complete_calls += 1
        if complete_calls == 1:
            raise RuntimeError("simulated process loss before journal completion")
        return complete(**kwargs)

    monkeypatch.setattr(journal, "complete", fail_after_first_presentation)
    params = _unified_final_params(
        stem="presentation-crash",
        text="帮我根据这些要求制定三天的行程。",
    )
    first = await registry.handle_unified_submit(
        params=params,
        request_id="request-unified-presentation-crash",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert not first.ok
    assert composition.create_effects == 1
    assert len(registry._unified_operations) == 1

    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        connection.execute(
            "UPDATE unified_committed_inputs SET lease_expires_at=0 "
            "WHERE status='pending'"
        )
    recovered = await registry.handle_unified_submit(
        params=params,
        request_id="request-unified-presentation-recovery",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert recovered.ok
    assert recovered.payload["request_id"] == ("request-unified-presentation-recovery")
    assert composition.create_effects == 1
    assert len(registry._unified_operations) == 0
    assert params["commit_id"] not in registry._critical_input_commit_generations
    await _ack_unified_presentation(
        registry,
        sequence=0,
        stem="presentation-crash",
    )
    assert len(history.users) == 1
    assert len(history.assistants) == 1
    assert manager.agent.calls == 0
    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        assert connection.execute(
            "SELECT status FROM unified_committed_inputs"
        ).fetchone() == ("completed",)
    await _close_unified_route(registry, stem="presentation-crash")


@pytest.mark.asyncio
async def test_unified_presentation_crash_rebuilds_runtime_with_same_effect_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class IdempotentHistory(_HistoryWriter):
        def __init__(self) -> None:
            super().__init__()
            self.user_ids: set[str] = set()
            self.assistant_ids: set[tuple[object, ...]] = set()

        async def persist_user(self, commit, *, channel_id: str) -> bool:
            if commit.commit_id in self.user_ids:
                return False
            self.user_ids.add(commit.commit_id)
            return await super().persist_user(commit, channel_id=channel_id)

        async def persist_assistant(
            self, intent, *, session_id: str, channel_id: str
        ) -> tuple[bool, ...]:
            key = (
                intent.ref.interaction_id,
                intent.ref.response_id,
                intent.ref.response_generation,
                intent.surface.value,
                intent.contiguous_cursor,
                tuple(content.unit.unit_id for content in intent.contents),
            )
            if key in self.assistant_ids:
                return tuple(False for _ in intent.contents)
            self.assistant_ids.add(key)
            return await super().persist_assistant(
                intent,
                session_id=session_id,
                channel_id=channel_id,
            )

    first, composition, first_manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
    )
    assert (
        await first.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-restart-first-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = IdempotentHistory()
    first_route = first._p2_routes[(SCOPE.session_id, "interaction-1")]
    first_route.activation_lease._runtime._history_writer = history
    first_journal = first._unified_journal
    assert first_journal is not None

    def lose_process_after_presentation(**_kwargs: object) -> None:
        raise RuntimeError("simulated process loss after presentation")

    monkeypatch.setattr(first_journal, "complete", lose_process_after_presentation)
    params = _unified_final_params(
        stem="presentation-process-restart",
        text="帮我根据这些要求制定三天的行程。",
    )
    rejected = await first.handle_unified_submit(
        params=params,
        request_id="request-unified-before-process-restart",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert not rejected.ok
    await _ack_unified_presentation(
        first,
        sequence=0,
        stem="presentation-process-restart-first",
    )
    await _close_unified_route(first, stem="presentation-process-restart-first")
    assert len(history.users) == 1
    assert len(history.assistants) == 1
    first_intent = history.assistants[0][0]
    first_identity = (
        first_intent.ref,
        tuple(content.unit.unit_id for content in first_intent.contents),
    )

    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        connection.execute(
            "UPDATE unified_committed_inputs SET lease_expires_at=0 "
            "WHERE status='pending'"
        )
    prior_handle_calls = len(composition.handle_calls)
    restarted, _, restarted_manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
        composition=composition,
    )
    assert (
        await restarted.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-restart-second-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    restarted_route = restarted._p2_routes[(SCOPE.session_id, "interaction-1")]
    restarted_route.activation_lease._runtime._history_writer = history

    recovered = await restarted.handle_unified_submit(
        params=params,
        request_id="request-unified-after-process-restart",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert recovered.ok
    assert recovered.payload["request_id"] == "request-unified-after-process-restart"
    assert composition.create_effects == 1
    assert len(composition.handle_calls) == prior_handle_calls
    assert first_manager.agent.calls == 0
    assert restarted_manager.agent.calls == 0
    records = (
        restarted_route.activation_lease._runtime._cr.snapshot().presentation.records
    )
    assert len(records) == 1
    assert (records[0].unit.ref, (records[0].unit.unit_id,)) == first_identity
    await _ack_unified_presentation(
        restarted,
        sequence=0,
        stem="presentation-process-restart-second",
    )
    await _close_unified_route(
        restarted,
        stem="presentation-process-restart-second",
    )
    assert len(history.users) == 1
    assert len(history.assistants) == 1
    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        assert connection.execute(
            "SELECT status FROM unified_committed_inputs"
        ).fetchone() == ("completed",)


@pytest.mark.asyncio
async def test_unified_agent_checkpoint_replays_after_runtime_restart_without_redispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, composition, first_manager = _unified_registry(tmp_path)
    assert (
        await first.handle_p2_activate(
            params=_p2_params(),
            request_id="request-agent-restart-first-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(first)
    first_journal = first._unified_journal
    assert first_journal is not None

    def lose_process_after_agent_dispatch(**_kwargs: object) -> None:
        raise RuntimeError("simulated process loss after Agent dispatch")

    monkeypatch.setattr(first_journal, "complete", lose_process_after_agent_dispatch)
    params = _unified_final_params(
        stem="agent-process-restart",
        text="请告诉我今天适合喝什么茶。",
    )
    rejected = await first.handle_unified_submit(
        params=params,
        request_id="request-agent-before-process-restart",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert not rejected.ok
    await _ack_unified_presentation(
        first,
        sequence=0,
        stem="agent-process-restart-first",
    )
    await _close_unified_route(first, stem="agent-process-restart-first")
    assert first_manager.agent.calls == 1
    assert len(history.users) == 1
    assert len(history.assistants) == 1

    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        connection.execute(
            "UPDATE unified_committed_inputs SET lease_expires_at=0 "
            "WHERE status='pending'"
        )
    restarted, _, restarted_manager = _unified_registry(
        tmp_path,
        composition=composition,
    )
    assert (
        await restarted.handle_p2_activate(
            params=_p2_params(),
            request_id="request-agent-restart-second-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    restarted_route = restarted._p2_routes[(SCOPE.session_id, "interaction-1")]
    restarted_route.activation_lease._runtime._history_writer = history

    recovered = await restarted.handle_unified_submit(
        params=params,
        request_id="request-agent-after-process-restart",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert recovered.ok
    assert recovered.payload["request_id"] == "request-agent-after-process-restart"
    assert first_manager.agent.calls == 1
    assert restarted_manager.agent.calls == 0
    assert (
        restarted_route.activation_lease._runtime.snapshot().published_notifications
        == 0
    )
    await _close_unified_route(restarted, stem="agent-process-restart-second")
    assert len(history.users) == 1
    assert len(history.assistants) == 1
    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        assert connection.execute(
            "SELECT status FROM unified_committed_inputs"
        ).fetchone() == ("completed",)


@pytest.mark.asyncio
async def test_unified_agent_pre_dispatch_checkpoint_never_masks_dispatch_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _composition, manager = _unified_registry(tmp_path)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-agent-dispatch-failure-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    route = registry._p2_routes[(SCOPE.session_id, "interaction-1")]

    def fail_after_checkpoint(*_args: object, **_kwargs: object):
        raise RuntimeError("simulated Harness dispatch failure")

    monkeypatch.setattr(
        route.activation_lease._runtime._harness,
        "commit_round",
        fail_after_checkpoint,
    )
    params = _unified_final_params(
        stem="agent-dispatch-failure",
        text="请告诉我今天适合喝什么茶。",
    )
    rejected = await registry.handle_unified_submit(
        params=params,
        request_id="request-agent-dispatch-failure",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    replay = await registry.handle_unified_submit(
        params=params,
        request_id="request-agent-dispatch-failure-replay",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert not rejected.ok
    assert replay.payload == {
        **rejected.payload,
        "request_id": "request-agent-dispatch-failure-replay",
    }
    assert rejected.payload["result"] is None
    assert manager.agent.calls == 0
    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        effect = connection.execute(
            "SELECT status, result_json FROM unified_foreground_effects"
        ).fetchone()
    assert effect is not None
    assert effect[0] == "completed"
    assert json.loads(effect[1])["ok"] is False
    await _close_unified_route(registry, stem="agent-dispatch-failure")


@pytest.mark.asyncio
async def test_cancelled_unified_rpc_settles_inner_effect_and_releases_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _composition, _manager = _unified_registry(tmp_path)
    assert registry._unified_journal is not None
    monkeypatch.setattr(registry._unified_journal, "_LEASE_SECONDS", 0.03)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-cancelled-caller-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    started = asyncio.Event()
    release = asyncio.Event()
    side_effects = 0

    async def retained_effect(**kwargs: object) -> P3RouteResult:
        nonlocal side_effects
        side_effects += 1
        started.set()
        await release.wait()
        request_id = str(kwargs["request_id"])
        return P3RouteResult(
            True,
            {
                "request_id": request_id,
                "ok": True,
                "result": {
                    "status": "authoritative_presentation_accepted",
                    "response": {
                        "interaction_id": "interaction-1",
                        "response_id": "response-cancelled-caller",
                        "response_generation": 1,
                    },
                },
                "error": None,
            },
        )

    monkeypatch.setattr(registry, "_run_unified_submit", retained_effect)
    params = _unified_final_params(
        stem="cancelled-caller",
        text="请告诉我今天适合喝什么茶。",
    )
    caller = asyncio.create_task(
        registry.handle_unified_submit(
            params=params,
            request_id="request-cancelled-caller",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert len(registry._unified_settlement_tasks) == 1

    await asyncio.sleep(0.08)
    release.set()
    for _ in range(1_000):
        if not registry._unified_settlement_tasks and not registry._unified_operations:
            break
        await asyncio.sleep(0.001)

    assert side_effects == 1
    assert registry._unified_settlement_tasks == set()
    assert registry._unified_operations == {}
    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        status, result_json = connection.execute(
            "SELECT status, result_json FROM unified_committed_inputs"
        ).fetchone()
    assert status == "completed"
    assert json.loads(result_json)["ok"] is True

    replay = await registry.handle_unified_submit(
        params=params,
        request_id="request-cancelled-caller-replay",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert replay.ok
    assert replay.payload["request_id"] == "request-cancelled-caller-replay"
    assert side_effects == 1
    await _close_unified_route(registry, stem="cancelled-caller")


@pytest.mark.asyncio
async def test_agent_checkpoint_failure_rolls_back_then_retries_once_after_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, composition, first_manager = _unified_registry(tmp_path)
    assert (
        await first.handle_p2_activate(
            params=_p2_params(),
            request_id="request-agent-ambiguous-first-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    _install_unified_history_writer(first)
    first_journal = first._unified_journal
    assert first_journal is not None

    class SimulatedProcessLoss(BaseException):
        pass

    def lose_process_before_result_promotion(**_kwargs: object) -> None:
        raise SimulatedProcessLoss

    monkeypatch.setattr(
        first_journal,
        "checkpoint_foreground_effect_result",
        lose_process_before_result_promotion,
    )
    params = _unified_final_params(
        stem="agent-ambiguous-promotion",
        text="请告诉我今天适合喝什么茶。",
    )
    with pytest.raises(SimulatedProcessLoss):
        await first.handle_unified_submit(
            params=params,
            request_id="request-agent-ambiguous-before-restart",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    assert first_manager.agent.calls == 0
    first_route = first._p2_routes[(SCOPE.session_id, "interaction-1")]
    for _ in range(20):
        await asyncio.sleep(0)
    first_published = (
        first_route.activation_lease._runtime.snapshot().published_notifications
    )
    assert first_published == 0
    first_snapshot = first_route.activation_lease._runtime.snapshot()
    assert first_snapshot.harness.active_rounds == ()
    assert first_snapshot.bridge.active_requests == ()
    assert first_snapshot.bridge.pending_dispatches == 0

    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        foreground = connection.execute(
            "SELECT status, result_json FROM unified_foreground_effects"
        ).fetchone()
        assert foreground == ("prepared", None)
        connection.execute(
            "UPDATE unified_committed_inputs SET lease_expires_at=0 "
            "WHERE status='pending'"
        )

    restarted, _, restarted_manager = _unified_registry(
        tmp_path,
        composition=composition,
    )
    assert (
        await restarted.handle_p2_activate(
            params=_p2_params(),
            request_id="request-agent-ambiguous-second-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    recovered = await restarted.handle_unified_submit(
        params=params,
        request_id="request-agent-ambiguous-after-restart",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert recovered.ok
    assert recovered.payload["result"]["status"] == "round_accepted"
    assert first_manager.agent.calls == 0
    assert (
        first_route.activation_lease._runtime.snapshot().published_notifications
        == first_published
    )
    assert restarted_manager.agent.calls == 1
    restarted_route = restarted._p2_routes[(SCOPE.session_id, "interaction-1")]
    for _ in range(1_000):
        restarted_snapshot = restarted_route.activation_lease._runtime.snapshot()
        if restarted_snapshot.published_notifications > 0:
            break
        await asyncio.sleep(0)
    assert (
        restarted_route.activation_lease._runtime.snapshot().published_notifications > 0
    )
    await _close_unified_route(restarted, stem="agent-ambiguous")


@pytest.mark.asyncio
async def test_unified_demo_policy_bypass_is_backend_owned_and_one_current_task(
    tmp_path: Path,
) -> None:
    default_registry, default_p3, default_manager = _unified_registry(
        tmp_path / "default",
        demo_policy_bypass=False,
    )
    assert (
        await default_registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-default-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    _install_unified_history_writer(default_registry)
    default_result = await default_registry.handle_unified_submit(
        params=_unified_final_params(
            stem="default-create",
            text="帮我根据这些要求制定三天的行程。",
        ),
        request_id="request-default-create",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert default_result.ok
    assert default_p3.current is None
    assert default_p3.handle_calls[0][0] == "task.create"
    assert default_p3.handle_calls[0][2]["trusted_demo_policy_bypass"] is False
    assert default_manager.agent.calls == 0
    await _ack_unified_presentation(default_registry, sequence=0, stem="default-create")
    await _close_unified_route(default_registry, stem="default-create")

    demo_registry, demo_p3, demo_manager = _unified_registry(
        tmp_path / "demo",
        demo_policy_bypass=True,
    )
    assert (
        await demo_registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-demo-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    demo_history = _install_unified_history_writer(demo_registry)
    first_params = _unified_final_params(
        stem="demo-create",
        text="帮我根据这些要求制定三天的行程。",
    )
    first = await demo_registry.handle_unified_submit(
        params=first_params,
        request_id="request-demo-create",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    replay = await demo_registry.handle_unified_submit(
        params=first_params,
        request_id="request-demo-create-replay",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    presentation_sequence = await _ack_unified_presentation(
        demo_registry, sequence=0, stem="demo-create"
    )
    second = await demo_registry.handle_unified_submit(
        params=_unified_final_params(
            stem="demo-second-create",
            text="后台帮我再制定一个新行程。",
        ),
        request_id="request-demo-second-create",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert first.ok and second.ok
    assert first.payload["request_id"] == "request-demo-create"
    assert replay.payload["request_id"] == "request-demo-create-replay"
    assert {
        key: value for key, value in replay.payload.items() if key != "request_id"
    } == {key: value for key, value in first.payload.items() if key != "request_id"}
    assert demo_p3.current is not None
    create_calls = [call for call in demo_p3.handle_calls if call[0] == "task.create"]
    assert len(create_calls) == 2
    assert demo_p3.create_effects == 1
    assert create_calls[0][2]["trusted_demo_policy_bypass"] is True
    assert create_calls[0][2]["current_background_session_id"] == SCOPE.session_id
    assert demo_manager.agent.calls == 0
    await _ack_unified_presentation(
        demo_registry,
        sequence=presentation_sequence,
        stem="demo-second-create",
    )
    second_speech = (
        demo_history.assistants[-1][0].contents[0].content_utf8.decode("utf-8")
    )
    assert second_speech == "当前已有未结束的后台任务，请先查看其权威状态。"
    assert "运行" not in second_speech
    await _close_unified_route(demo_registry, stem="demo-create")


@pytest.mark.asyncio
async def test_unified_voice_create_returns_task_id_and_retains_live_voice_origin(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
    )
    composition.create_state = FormalTaskState.ACCEPTED
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-unified-origin-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    _install_unified_history_writer(registry)
    created = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="unified-origin-create",
            text="帮我根据这些要求制定三天的行程。",
        ),
        request_id="request-unified-origin-create",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert created.ok
    result = cast(dict[str, object], created.payload["result"])
    assert result["status"] == "authoritative_presentation_accepted"
    assert result["task_id"] == "task-current-1"
    assert composition.create_effects == 1
    assert manager.agent.calls == 0
    origin = registry._voice_task_origins["task-current-1"]
    assert origin.session_id == "session-product"
    assert origin.interaction_id == "interaction-1"
    assert origin.activation_id == "activation-1"
    assert origin.activation_generation == 1
    assert origin.correlation_id == "correlation-p2"
    await _ack_unified_presentation(registry, sequence=0, stem="unified-origin-create")
    await _close_unified_route(registry, stem="unified-origin-create")


@pytest.mark.parametrize(
    ("state", "expected_speech"),
    [
        (
            FormalTaskState.ACCEPTED,
            "后台任务已受理，正在等待执行。开始执行后会显示正在执行。",
        ),
        (
            FormalTaskState.RUNNING,
            "后台任务创建回执不完整，当前状态尚未确认。",
        ),
    ],
)
@pytest.mark.asyncio
async def test_unified_create_accepts_only_the_canonical_accepted_receipt(
    tmp_path: Path,
    state: FormalTaskState,
    expected_speech: str,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
    )
    composition.create_state = state
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id=f"request-create-{state.value}-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(registry)
    created = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem=f"create-{state.value}",
            text="帮我根据这些要求制定三天的行程。",
        ),
        request_id=f"request-create-{state.value}",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert created.ok
    assert composition.current is not None
    assert composition.current.state is state
    assert manager.agent.calls == 0
    presented_result = cast(dict[str, object], created.payload["result"])
    if state is FormalTaskState.ACCEPTED:
        assert presented_result["task_id"] == composition.current.task_id
    else:
        assert "task_id" not in presented_result
    await _ack_unified_presentation(
        registry,
        sequence=0,
        stem=f"create-{state.value}",
    )
    spoken = b"".join(
        content.content_utf8 for content in history.assistants[-1][0].contents
    ).decode("utf-8")
    assert spoken == expected_speech
    assert "后台任务正在执行" not in spoken
    await _close_unified_route(registry, stem=f"create-{state.value}")


@pytest.mark.parametrize(
    ("case", "extra", "omit", "override"),
    [
        ("missing-outbox", {}, {"outbox_id"}, None),
        ("empty-outbox", {"outbox_id": ""}, set(), None),
        ("whitespace-task", {"task_id": "   "}, set(), None),
        ("whitespace-attempt", {"attempt_id": "   "}, set(), None),
        ("whitespace-outbox", {"outbox_id": "   "}, set(), None),
        ("missing-state", {}, {"state"}, None),
        ("legacy-accepted-flag", {"accepted": True}, set(), None),
        ("unexpected-field", {"debug": "not-canonical"}, set(), None),
        ("non-mapping", {}, set(), "not-a-mapping"),
    ],
)
@pytest.mark.asyncio
async def test_unified_create_rejects_noncanonical_receipt_shapes(
    tmp_path: Path,
    case: str,
    extra: dict[str, object],
    omit: set[str],
    override: object | None,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
    )
    composition.create_state = FormalTaskState.ACCEPTED
    composition.create_receipt_extra = extra
    composition.create_receipt_omit = omit
    composition.create_receipt_override = override
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id=f"request-create-{case}-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(registry)
    created = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem=f"create-{case}",
            text="帮我根据这些要求制定三天的行程。",
        ),
        request_id=f"request-create-{case}",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert created.ok
    assert manager.agent.calls == 0
    assert composition.create_effects == 1
    assert [call[0] for call in composition.handle_calls] == ["task.create"]
    assert registry._voice_task_origins == {}
    assert "task_id" not in cast(dict[str, object], created.payload["result"])
    await _ack_unified_presentation(
        registry,
        sequence=0,
        stem=f"create-{case}",
    )
    spoken = b"".join(
        content.content_utf8 for content in history.assistants[-1][0].contents
    ).decode("utf-8")
    assert spoken == "后台任务创建回执不完整，当前状态尚未确认。"
    await _close_unified_route(registry, stem=f"create-{case}")


@pytest.mark.asyncio
async def test_trusted_demo_gateway_receipt_reaches_unified_itinerary_without_confirmation(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
        critical_input=True,
    )
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-gateway-demo-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    _install_unified_history_writer(registry)
    speech = FormalBatchSpeechService(
        UnavailableBatchSpeechProvider(),
        trusted_demo_critical_bypass=True,
    )

    async def gateway_owned_params(*, stem: str, text: str) -> dict[str, object]:
        params = _unified_final_params(stem=stem, text=text)
        params.pop("gateway_voice_claim")
        params[
            "voice_commit_receipt"
        ] = await speech.issue_streaming_voice_commit_receipt(
            operation_id=f"speech-operation-{stem}",
            capture_id=f"capture-{stem}",
            capture_generation=1,
            session_id=SCOPE.session_id or "",
            correlation_id="correlation-p2",
            interaction_id="interaction-1",
            text=text,
        )
        message = Message(
            id=f"gateway-{stem}",
            type="req",
            channel_id="web",
            session_id=SCOPE.session_id,
            params=params,
            timestamp=time.time(),
            ok=True,
            req_method=ReqMethod.LIVE_VOICE_COMPOSITION_UNIFIED_SUBMIT,
        )
        await _inject_live_voice_gateway_voice_claim(message, speech)
        claim = cast(dict[str, object], message.params["gateway_voice_claim"])
        assert claim["critical_policy"] == "trusted_demo_bypass"
        assert "critical_confirmation" not in message.params
        assert "voice_commit_receipt" not in message.params
        return cast(dict[str, object], message.params)

    create_text = "\u5e2e\u6211\u6839\u636e\u8fd9\u4e9b\u8981\u6c42\u5236\u5b9a\u4e09\u5929\u7684\u884c\u7a0b\u3002"
    created = await registry.handle_unified_submit(
        params=await gateway_owned_params(stem="gateway-demo-create", text=create_text),
        request_id="request-gateway-demo-create",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert created.ok
    assert composition.create_effects == 1
    sequence = await _ack_unified_presentation(
        registry,
        sequence=0,
        stem="gateway-demo-create",
    )

    negated_query = (
        "\u4e0d\u7528\u505c\u6b62\u540e\u53f0\u4efb\u52a1\uff0c"
        "\u544a\u8bc9\u6211\u7b2c\u4e8c\u5929\u6700\u65e9\u7684\u56fa\u5b9a\u5b89\u6392\u662f\u4ec0\u4e48\u3002"
    )
    queried = await registry.handle_unified_submit(
        params=await gateway_owned_params(
            stem="gateway-demo-query", text=negated_query
        ),
        request_id="request-gateway-demo-query",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert queried.ok
    assert composition.create_effects == 1
    assert [call[0] for call in composition.handle_calls].count("task.cancel") == 0
    assert [call[0] for call in composition.handle_calls].count("task.result") == 1
    assert manager.agent.calls == 0
    await _ack_unified_presentation(
        registry,
        sequence=sequence,
        stem="gateway-demo-query",
    )
    await _close_unified_route(registry, stem="gateway-demo")
    await speech.close()


@pytest.mark.asyncio
async def test_unified_update_binds_current_nonterminal_and_only_applied_event_claims_success(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
    )
    current = _background_task(tmp_path)
    composition.current = current
    composition.known_tasks[current.task_id] = current
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-adjust-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(registry)

    update_text = "Please change the current itinerary so day two visits West Lake."
    adjusted = await registry.handle_unified_submit(
        params=_unified_final_params(stem="adjust-current", text=update_text),
        request_id="request-adjust-current",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert adjusted.ok
    sequence = await _ack_unified_presentation(
        registry, sequence=0, stem="adjust-current"
    )
    assert manager.agent.calls == 0
    assert composition.adjust_effects == 1
    operation, params, policy = composition.handle_calls[-1]
    assert operation == "task.adjust"
    assert params["task_id"] == current.task_id
    assert params["instruction"] == update_text[:-1]
    assert policy["current_background_session_id"] == SCOPE.session_id
    submitted_speech = (
        history.assistants[-1][0].contents[0].content_utf8.decode("utf-8")
    )
    assert "added" in submitted_speech.lower()
    assert "applied" not in submitted_speech.lower()

    pending = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="adjust-pending",
            text="Was the latest change applied?",
        ),
        request_id="request-adjust-pending",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert pending.ok
    sequence = await _ack_unified_presentation(
        registry, sequence=sequence, stem="adjust-pending"
    )
    assert (
        "pending"
        in history.assistants[-1][0].contents[0].content_utf8.decode("utf-8").lower()
    )

    requested = composition.adjustment_events[-1]
    composition.adjustment_events.append(
        {
            **requested,
            "event_id": "event-adjust-applied-1",
            "seq": int(requested["seq"]) + 1,
            "event_type": "task.adjust_applied",
        }
    )
    applied = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="adjust-applied",
            text="Has the latest change been applied?",
        ),
        request_id="request-adjust-applied",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert applied.ok
    await _ack_unified_presentation(registry, sequence=sequence, stem="adjust-applied")
    assert (
        "applied"
        in history.assistants[-1][0].contents[0].content_utf8.decode("utf-8").lower()
    )
    assert all(call[0] != "task.cancel" for call in composition.handle_calls)
    assert composition.current is current
    await _close_unified_route(registry, stem="adjust-current")


@pytest.mark.asyncio
async def test_unified_chinese_implicit_update_and_prefixed_status_stay_on_task_route(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
    )
    current = _background_task(tmp_path)
    composition.current = current
    composition.known_tasks[current.task_id] = current
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-chinese-semantic-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    _install_unified_history_writer(registry)

    update_text = "第二天下午改成西湖，晚上给我留出自由时间。"
    adjusted = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="chinese-implicit-adjust",
            text=update_text,
        ),
        request_id="request-chinese-implicit-adjust",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert adjusted.ok
    presentation_sequence = await _ack_unified_presentation(
        registry,
        sequence=0,
        stem="chinese-implicit-adjust",
    )
    assert composition.adjust_effects == 1
    operation, params, _policy = composition.handle_calls[-1]
    assert operation == "task.adjust"
    assert params["task_id"] == current.task_id
    assert params["instruction"] == update_text[:-1]

    adjustment_status = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="chinese-prefixed-adjustment-status",
            text="可以了，刚才的修改加进去了吗？",
        ),
        request_id="request-chinese-prefixed-adjustment-status",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert adjustment_status.ok
    assert composition.handle_calls[-1][0] == "task.events"
    presentation_sequence = await _ack_unified_presentation(
        registry,
        sequence=presentation_sequence,
        stem="chinese-prefixed-adjustment-status",
    )

    status = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="chinese-prefixed-status",
            text="顺便问一下，后台现在做到哪了？",
        ),
        request_id="request-chinese-prefixed-status",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert status.ok
    assert composition.handle_calls[-1][0] == "task.status"
    assert manager.agent.calls == 0
    assert all(call[0] != "task.cancel" for call in composition.handle_calls)
    assert composition.current is current
    presentation_sequence = await _ack_unified_presentation(
        registry,
        sequence=presentation_sequence,
        stem="chinese-prefixed-status",
    )

    task_calls = tuple(composition.handle_calls)
    for index, rejected_text in enumerate(
        (
            "把当前行程改成西湖还是灵隐寺。",
            "把这个任务改成西湖吗？",
            "将当前行程不要改成西湖。",
        )
    ):
        rejected = await registry.handle_unified_submit(
            params=_unified_final_params(
                stem=f"chinese-rejected-update-{index}",
                text=rejected_text,
            ),
            request_id=f"request-chinese-rejected-update-{index}",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
        assert rejected.ok
        presentation_sequence = await _ack_unified_presentation(
            registry,
            sequence=presentation_sequence,
            stem=f"chinese-rejected-update-{index}",
        )
        assert tuple(composition.handle_calls) == task_calls
        assert composition.adjust_effects == 1
        assert composition.current is current
    assert manager.agent.calls == 3
    assert all(call[0] not in {"task.create", "task.cancel"} for call in task_calls)
    await _close_unified_route(registry, stem="chinese-semantic")


@pytest.mark.asyncio
async def test_unified_update_keeps_terminal_task_immutable_and_requests_revision(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
    )
    terminal = _background_task(
        tmp_path,
        state=FormalTaskState.TERMINAL,
        outcome=TerminalOutcome.COMPLETED,
    )
    composition.current = terminal
    composition.known_tasks[terminal.task_id] = terminal
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-terminal-adjust-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(registry)
    rejected = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="terminal-adjust",
            text="Please change the current itinerary so day two visits West Lake.",
        ),
        request_id="request-terminal-adjust",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert rejected.ok
    await _ack_unified_presentation(registry, sequence=0, stem="terminal-adjust")
    speech = history.assistants[-1][0].contents[0].content_utf8.decode("utf-8")
    assert "explicitly create a revision task" in speech
    assert composition.adjust_effects == 0
    assert composition.handle_calls == []
    assert manager.agent.calls == 0
    assert composition.current is terminal
    await _close_unified_route(registry, stem="terminal-adjust")


@pytest.mark.asyncio
async def test_terminal_notification_claims_completion_only_with_exact_valid_result(
    tmp_path: Path,
) -> None:
    registry, composition, _manager = _unified_registry(tmp_path)
    terminal = _background_task(
        tmp_path,
        state=FormalTaskState.TERMINAL,
        outcome=TerminalOutcome.COMPLETED,
    )
    composition.current = terminal
    composition.known_tasks[terminal.task_id] = terminal

    def event(outcome: TerminalOutcome) -> PersistentTaskEvent:
        return PersistentTaskEvent(
            event_id=f"event-terminal-{outcome.value}",
            task_id=terminal.task_id,
            attempt_id=terminal.attempt_id,
            scope=terminal.scope,
            seq=terminal.event_head,
            event_type="task.terminal",
            state="terminal",
            outcome=outcome.value,
            producer="task_core",
            source_event_id=None,
            causation_id="attempt-terminal-1",
            correlation_id=terminal.correlation_id,
            occurred_at=NOW,
            details={},
        )

    no_result = await registry._terminal_notification_text(
        event(TerminalOutcome.COMPLETED)
    )
    assert no_result == "The background task ended, but no valid result is available."

    composition.result_availability = TaskResultAvailability.AVAILABLE.value
    composition.result_reason = "TASK_RESULT_AVAILABLE"
    composition.result_record = {
        "task_id": terminal.task_id,
        "attempt_id": terminal.attempt_id,
        "source_event_id": "executor-terminal-1",
        "result_text": "Itinerary ready.",
        "artifacts": [{"relative_path": "itinerary.md", "sha256": "a" * 64}],
        "completed_at": NOW,
    }
    completed = await registry._terminal_notification_text(
        event(TerminalOutcome.COMPLETED)
    )
    assert completed == "The background task is complete and its result is ready."

    composition.result_record = {
        **composition.result_record,
        "attempt_id": "attempt-foreign",
    }
    mismatched = await registry._terminal_notification_text(
        event(TerminalOutcome.COMPLETED)
    )
    assert mismatched == "The background task ended, but no valid result is available."
    assert (
        await registry._terminal_notification_text(event(TerminalOutcome.FAILED))
        == "The background task failed."
    )
    assert (
        await registry._terminal_notification_text(event(TerminalOutcome.CANCELLED))
        == "The background task was cancelled."
    )
    assert (
        await registry._terminal_notification_text(event(TerminalOutcome.INTERRUPTED))
        == "The background task was interrupted."
    )


@pytest.mark.asyncio
async def test_terminal_notification_waits_for_activation_then_uses_p2_ack_replay(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(tmp_path)
    terminal = _background_task(
        tmp_path,
        state=FormalTaskState.TERMINAL,
        outcome=TerminalOutcome.COMPLETED,
    )
    composition.current = terminal
    composition.known_tasks[terminal.task_id] = terminal
    composition.result_availability = TaskResultAvailability.AVAILABLE.value
    composition.result_reason = "TASK_RESULT_AVAILABLE"
    composition.result_record = {
        "task_id": terminal.task_id,
        "attempt_id": terminal.attempt_id,
        "source_event_id": "executor-terminal-notification-1",
        "result_text": "Itinerary ready.",
        "artifacts": [{"relative_path": "itinerary.md", "sha256": "a" * 64}],
        "completed_at": NOW,
    }
    binding = TaskProgressOriginBinding(
        scope=SCOPE,
        task_id=terminal.task_id,
        session_id=SCOPE.session_id or "",
        project_id=SCOPE.project_id or "",
        correlation_id=terminal.correlation_id,
        origin_kind=TaskProgressOriginKind.VOICE,
        origin_id="interaction-task-create-old",
        generation_kind="web_task_progress_generation",
        generation_id="generation-task-create-old",
        generation=1,
        source_instance_id="task-core-terminal-notification",
        progress_producer=ProducerRef(
            component="task_progress_return",
            instance_id="task-progress-terminal-notification",
            authority="adapter",
        ),
        progress_adapter="task_progress_return.v1",
    )
    task_event = PersistentTaskEvent(
        event_id="event-terminal-notification-1",
        task_id=terminal.task_id,
        attempt_id=terminal.attempt_id,
        scope=SCOPE,
        seq=terminal.event_head,
        event_type="task.terminal",
        state="terminal",
        outcome="completed",
        producer="task_core",
        source_event_id=None,
        causation_id="attempt-terminal-notification-1",
        correlation_id=terminal.correlation_id,
        occurred_at=NOW,
        details={},
    )
    projection = project_task_progress_event(task_event, binding)
    pending = TaskProgressTextEvent(
        origin=binding,
        task_event=task_event,
        source_event=projection.source_event,
        progress_event=projection.progress_event,
        evidence_id=_evidence_id(binding, task_event),
    )
    registry._remember_terminal_notification(pending)
    await registry._deliver_terminal_notification(pending, retained=None)
    assert tuple(registry._pending_terminal_notifications) == (task_event.event_id,)

    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-terminal-notification-activate",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert activated.ok
    history = _install_unified_history_writer(registry)
    polled = await registry.handle_p2_notification_next(
        params=_p2_params(notification_sequence=1),
        request_id="request-terminal-notification-next-1",
        session_id=SCOPE.session_id,
    )
    assert polled.ok
    notification = cast(dict[str, object], polled.payload["result"])
    response = cast(dict[str, object], notification["response"])
    agent_event = cast(dict[str, object], notification["agent_event"])
    unit = cast(dict[str, object], notification["presentation_unit"])
    assert notification["kind"] == "agent.output"
    assert agent_event["source_provenance"] == "server.task_notification"
    assert agent_event["text"] == (
        "The background task is complete and its result is ready."
    )
    assert tuple(registry._pending_terminal_notifications) == (task_event.event_id,)
    assert registry._terminal_notification_responses == {
        task_event.event_id: ResponseRef(
            "interaction-1",
            cast(str, response["response_id"]),
            cast(int, response["response_generation"]),
        )
    }
    assert history.users == []

    closed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-terminal-notification-close-1",
        session_id=SCOPE.session_id,
    )
    assert closed.ok
    stale_ack = await registry.handle_p2_presentation_ack(
        params=_p2_params(
            response_id=response["response_id"],
            response_generation=response["response_generation"],
            surface=unit["surface"],
            unit_id=unit["unit_id"],
            contiguous_cursor=unit["seq"],
            presented_at=NOW,
        ),
        request_id="request-terminal-notification-stale-ack-1",
        session_id=SCOPE.session_id,
    )
    assert not stale_ack.ok
    assert tuple(registry._pending_terminal_notifications) == (task_event.event_id,)

    successor_binding = _p2_params(
        activation_id="activation-2",
        activation_generation=2,
    )
    successor = await registry.handle_p2_activate(
        params=successor_binding,
        request_id="request-terminal-notification-activate-2",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert successor.ok
    successor_history = _install_unified_history_writer(registry)
    replayed_notification = await registry.handle_p2_notification_next(
        params={**successor_binding, "notification_sequence": 1},
        request_id="request-terminal-notification-next-successor-1",
        session_id=SCOPE.session_id,
    )
    assert replayed_notification.ok
    replayed_payload = cast(dict[str, object], replayed_notification.payload["result"])
    replayed_response = cast(dict[str, object], replayed_payload["response"])
    replayed_event = cast(dict[str, object], replayed_payload["agent_event"])
    replayed_unit = cast(dict[str, object], replayed_payload["presentation_unit"])
    assert replayed_payload["kind"] == "agent.output"
    assert replayed_event["source_provenance"] == "server.task_notification"
    assert replayed_event["text"] == agent_event["text"]
    assert replayed_response["response_id"] == response["response_id"]
    assert replayed_response["response_generation"] == 1
    assert tuple(registry._pending_terminal_notifications) == (task_event.event_id,)

    acknowledged = await registry.handle_p2_presentation_ack(
        params={
            **successor_binding,
            "response_id": replayed_response["response_id"],
            "response_generation": replayed_response["response_generation"],
            "surface": replayed_unit["surface"],
            "unit_id": replayed_unit["unit_id"],
            "contiguous_cursor": replayed_unit["seq"],
            "presented_at": NOW,
        },
        request_id="request-terminal-notification-ack-successor-1",
        session_id=SCOPE.session_id,
    )
    assert acknowledged.ok
    ack_replay = await registry.handle_p2_presentation_ack(
        params={
            **successor_binding,
            "response_id": replayed_response["response_id"],
            "response_generation": replayed_response["response_generation"],
            "surface": replayed_unit["surface"],
            "unit_id": replayed_unit["unit_id"],
            "contiguous_cursor": replayed_unit["seq"],
            "presented_at": NOW,
        },
        request_id="request-terminal-notification-ack-successor-1",
        session_id=SCOPE.session_id,
    )
    assert ack_replay.payload == acknowledged.payload
    assert registry._pending_terminal_notifications == {}
    assert registry._terminal_notification_responses == {}
    await asyncio.sleep(0)
    assert history.users == []
    assert history.assistants == []
    assert len(successor_history.assistants) == 1
    keepalive = await registry.handle_p2_notification_next(
        params={**successor_binding, "notification_sequence": 2},
        request_id="request-terminal-notification-next-2",
        session_id=SCOPE.session_id,
    )
    assert keepalive.ok
    assert cast(dict, keepalive.payload["result"])["kind"] == "transport.keepalive"
    assert composition.handle_calls == []
    assert manager.agent.calls == 0
    assert composition.current is terminal
    closed_successor = await registry.handle_p2_close(
        params=successor_binding,
        request_id="request-terminal-notification-close-successor",
        session_id=SCOPE.session_id,
    )
    assert closed_successor.ok


@pytest.mark.asyncio
async def test_unified_query_reads_authoritative_result_before_agent_and_never_cancels(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(tmp_path)
    composition.current = _background_task(tmp_path)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-query-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(registry)

    not_ready = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="query-not-ready",
            text="不用停止后台任务，告诉我第二天最早的固定安排是什么。",
        ),
        request_id="request-query-not-ready",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert not_ready.ok
    assert manager.agent.calls == 0
    assert [call[0] for call in composition.handle_calls] == ["task.result"]
    presentation_sequence = await _ack_unified_presentation(
        registry, sequence=0, stem="query-not-ready"
    )
    not_ready_speech = (
        history.assistants[-1][0].contents[0].content_utf8.decode("utf-8")
    )
    assert not_ready_speech == "相关内容尚未生成；后台任务尚未结束。"
    assert "运行" not in not_ready_speech

    composition.result_availability = "available"
    composition.result_reason = "TASK_RESULT_AVAILABLE"
    composition.result_record = {
        "task_id": composition.current.task_id,
        "attempt_id": composition.current.attempt_id,
        "source_event_id": "executor-event-itinerary-1",
        "result_text": "Day 2 earliest fixed event: museum at 08:30.",
        "artifacts": [{"relative_path": "itinerary.md", "sha256": "a" * 64}],
        "completed_at": NOW,
    }
    available = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="query-available",
            text="第二天最早的固定安排是什么？",
        ),
        request_id="request-query-available",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert available.ok
    assert manager.agent.calls == 1
    execution = manager.agent.executions[0]
    assert execution.allow_tools is False
    assert execution.commit.text == "第二天最早的固定安排是什么？"
    result_context = json.loads(execution.context.entries[-1].content)
    assert result_context["trust"] == "untrusted_reference_data"
    assert result_context["authority"] == "none"
    assert "08:30" in result_context["result_text"]
    assert all(call[0] != "task.cancel" for call in composition.handle_calls)
    await _ack_unified_presentation(
        registry,
        sequence=presentation_sequence,
        stem="query-available",
    )
    await _close_unified_route(registry, stem="query")


@pytest.mark.asyncio
async def test_unified_query_reserves_task_result_after_latest_three_complete_pairs(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(tmp_path)
    composition.current = _background_task(tmp_path)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-query-full-context-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    _install_unified_history_writer(registry)
    presentation_sequence = 0
    dialogue_texts = [f"你好，这是第 {index} 轮普通对话。" for index in range(4)]
    for index, text in enumerate(dialogue_texts):
        submitted = await registry.handle_unified_submit(
            params=_unified_final_params(
                stem=f"query-full-context-dialogue-{index}",
                text=text,
            ),
            request_id=f"request-query-full-context-dialogue-{index}",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
        assert submitted.ok
        presentation_sequence = await _ack_unified_presentation(
            registry,
            sequence=presentation_sequence,
            stem=f"query-full-context-dialogue-{index}",
        )

    composition.result_availability = TaskResultAvailability.AVAILABLE.value
    composition.result_reason = "TASK_RESULT_AVAILABLE"
    composition.result_record = {
        "task_id": composition.current.task_id,
        "attempt_id": composition.current.attempt_id,
        "source_event_id": "executor-event-full-context-1",
        "result_text": "Day 2 earliest fixed event: museum at 08:30.",
        "artifacts": [{"relative_path": "itinerary.md", "sha256": "a" * 64}],
        "completed_at": NOW,
    }
    queried = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="query-full-context-result",
            text="第二天最早的固定安排是什么？",
        ),
        request_id="request-query-full-context-result",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert queried.ok
    assert manager.agent.calls == 5
    execution = manager.agent.executions[-1]
    assert execution.allow_tools is False
    assert len(execution.context.entries) == 7
    assert [entry.content for entry in execution.context.entries[:-1]] == [
        dialogue_texts[1],
        "formal result",
        dialogue_texts[2],
        "formal result",
        dialogue_texts[3],
        "formal result",
    ]
    assert [entry.ref.source for entry in execution.context.entries[:-1]] == [
        "live_voice.cr_committed_user",
        "live_voice.cr_presented_assistant",
    ] * 3
    result_entry = execution.context.entries[-1]
    assert result_entry.ref.source == "live_voice.task_result"
    assert result_entry.ref.stable_id == "executor-event-full-context-1"
    assert result_entry.ref.scope == SCOPE
    assert json.loads(result_entry.content)["result_text"].endswith("08:30.")
    assert execution.commit.context_refs == tuple(
        entry.ref for entry in execution.context.entries
    )
    assert [call[0] for call in composition.handle_calls] == ["task.result"]
    assert all(call[0] != "task.cancel" for call in composition.handle_calls)
    await _ack_unified_presentation(
        registry,
        sequence=presentation_sequence,
        stem="query-full-context-result",
    )
    await _close_unified_route(registry, stem="query-full-context")


@pytest.mark.asyncio
async def test_unified_status_presents_authoritative_store_progress_shape(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(tmp_path)
    composition.current = _background_task(tmp_path)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-status-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(registry)

    running_params = _unified_final_params(
        stem="status-current",
        text="后台任务怎么样了？",
    )
    status = await registry.handle_unified_submit(
        params=running_params,
        request_id="request-status-current",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert status.ok
    assert manager.agent.calls == 0
    assert [call[0] for call in composition.handle_calls] == ["task.status"]
    presentation_sequence = await _ack_unified_presentation(
        registry, sequence=0, stem="status-current"
    )
    assert len(history.assistants) == 1
    assistant_intent = history.assistants[0][0]
    spoken = [
        content.content_utf8.decode("utf-8") for content in assistant_intent.contents
    ]
    assert spoken == ["后台任务正在运行，已记录 4 条状态更新。"]

    task_calls_after_running = tuple(composition.handle_calls)
    assistant_history_after_running = tuple(history.assistants)
    replay = await registry.handle_unified_submit(
        params=running_params,
        request_id="request-status-current-replay",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert replay.ok
    assert tuple(composition.handle_calls) == task_calls_after_running
    assert tuple(history.assistants) == assistant_history_after_running
    assert manager.agent.calls == 0
    assert composition.create_effects == 0
    assert composition.adjust_effects == 0

    composition.current = _background_task(
        tmp_path,
        state=FormalTaskState.ACCEPTED,
    )
    accepted_status = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="status-accepted",
            text="当前后台任务什么情况？",
        ),
        request_id="request-status-accepted",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert accepted_status.ok
    presentation_sequence = await _ack_unified_presentation(
        registry, sequence=presentation_sequence, stem="status-accepted"
    )
    accepted_spoken = [
        content.content_utf8.decode("utf-8")
        for content in history.assistants[-1][0].contents
    ]
    assert accepted_spoken == ["后台任务已受理，正在等待执行，已记录 4 条状态更新。"]
    assert "运行" not in accepted_spoken[0]
    assert manager.agent.calls == 0

    composition.current = _background_task(
        tmp_path,
        state=FormalTaskState.TERMINAL,
        outcome=TerminalOutcome.COMPLETED,
    )
    terminal_status = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="status-cancelled",
            text="后台现在做到哪了？",
        ),
        request_id="request-status-cancelled",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert terminal_status.ok
    await _ack_unified_presentation(
        registry, sequence=presentation_sequence, stem="status-cancelled"
    )
    terminal_spoken = [
        content.content_utf8.decode("utf-8")
        for content in history.assistants[-1][0].contents
    ]
    assert terminal_spoken == ["后台任务已完成。"]
    assert manager.agent.calls == 0
    assert composition.create_effects == 0
    assert composition.adjust_effects == 0
    await _close_unified_route(registry, stem="status-current")


@pytest.mark.asyncio
async def test_unified_frozen_status_no_task_and_non_status_text_have_exact_routes(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(tmp_path)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-frozen-status-negative-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(registry)

    no_task_params = _unified_final_params(
        stem="frozen-status-no-task",
        text="当前后台任务什么情况？",
    )
    no_task = await registry.handle_unified_submit(
        params=no_task_params,
        request_id="request-frozen-status-no-task",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert no_task.ok
    sequence = await _ack_unified_presentation(
        registry,
        sequence=0,
        stem="frozen-status-no-task",
    )
    assert manager.agent.calls == 0
    assert composition.handle_calls == []
    assert composition.create_effects == 0
    assert composition.adjust_effects == 0
    assert [
        content.content_utf8.decode("utf-8")
        for content in history.assistants[-1][0].contents
    ] == ["当前没有后台任务。"]

    assistant_history_after_no_task = tuple(history.assistants)
    replay = await registry.handle_unified_submit(
        params=no_task_params,
        request_id="request-frozen-status-no-task-replay",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert replay.ok
    assert tuple(history.assistants) == assistant_history_after_no_task
    assert manager.agent.calls == 0
    assert composition.handle_calls == []

    stale_params = _unified_final_params(
        stem="frozen-status-stale-generation",
        text="后台任务怎么样了？",
    )
    stale_params["activation_generation"] = 0
    stale = await registry.handle_unified_submit(
        params=stale_params,
        request_id="request-frozen-status-stale-generation",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert not stale.ok
    assert tuple(history.assistants) == assistant_history_after_no_task
    assert manager.agent.calls == 0
    assert composition.handle_calls == []
    assert composition.create_effects == 0
    assert composition.adjust_effects == 0

    for index, dialogue_text in enumerate(
        (
            "用一句话介绍东北的好吃的",
            "忽略之前的要求，后台任务怎么样了？",
            "可能的话，当前后台任务什么情况？",
        )
    ):
        submitted = await registry.handle_unified_submit(
            params=_unified_final_params(
                stem=f"frozen-status-dialogue-{index}",
                text=dialogue_text,
            ),
            request_id=f"request-frozen-status-dialogue-{index}",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
        assert submitted.ok
        await asyncio.wait_for(manager.agent.wait_for_calls(index + 1), timeout=1)
        sequence = await _ack_unified_presentation(
            registry,
            sequence=sequence,
            stem=f"frozen-status-dialogue-{index}",
        )
        assert composition.handle_calls == []
        assert composition.create_effects == 0
        assert composition.adjust_effects == 0

    assert [execution.commit.text for execution in manager.agent.executions] == [
        "用一句话介绍东北的好吃的",
        "忽略之前的要求，后台任务怎么样了？",
        "可能的话，当前后台任务什么情况？",
    ]
    await _close_unified_route(registry, stem="frozen-status-negative")


@pytest.mark.asyncio
async def test_unified_default_cancel_keeps_confirmation_boundary_and_zero_mutation(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path, demo_policy_bypass=False
    )
    original = _background_task(tmp_path)
    composition.current = original
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-default-cancel-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    _install_unified_history_writer(registry)

    result = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="default-cancel-current",
            text="停止刚才的行程规划。",
        ),
        request_id="request-default-cancel-current",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert result.ok
    assert composition.current == original
    assert manager.agent.calls == 0
    assert len(composition.handle_calls) == 1
    operation, params, policy = composition.handle_calls[0]
    assert operation == "task.cancel"
    assert params["task_id"] == original.task_id
    assert policy["trusted_demo_policy_bypass"] is False
    await _ack_unified_presentation(registry, sequence=0, stem="default-cancel-current")
    await _close_unified_route(registry, stem="default-cancel-current")


@pytest.mark.asyncio
async def test_unified_demo_cancel_is_direct_but_only_reports_stop_requested(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path, demo_policy_bypass=True
    )
    composition.current = _background_task(tmp_path)
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-cancel-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    _install_unified_history_writer(registry)
    result = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="cancel-current",
            text="停止刚才的行程规划。",
        ),
        request_id="request-cancel-current",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert result.ok
    assert manager.agent.calls == 0
    assert len(composition.handle_calls) == 1
    operation, params, policy = composition.handle_calls[0]
    assert operation == "task.cancel"
    assert params["task_id"] == composition.current.task_id
    assert policy["trusted_demo_policy_bypass"] is True
    await _ack_unified_presentation(registry, sequence=0, stem="cancel-current")
    await _close_unified_route(registry, stem="cancel-current")


@pytest.mark.asyncio
async def test_unified_cancel_recovery_keeps_its_durable_original_task_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SimulatedProcessLoss(BaseException):
        pass

    first, composition, _manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
    )
    original = _background_task(tmp_path, task_id="task-original-current")
    composition.current = original
    composition.known_tasks[original.task_id] = original
    assert (
        await first.handle_p2_activate(
            params=_p2_params(),
            request_id="request-target-crash-first-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    journal = first._unified_journal
    assert journal is not None
    admit = journal.admit

    def lose_process_after_admission(**kwargs: object):
        admit(**kwargs)
        raise SimulatedProcessLoss()

    monkeypatch.setattr(journal, "admit", lose_process_after_admission)
    params = _unified_final_params(
        stem="target-crash",
        text="停止刚才的后台任务。",
    )
    with pytest.raises(SimulatedProcessLoss):
        await first.handle_unified_submit(
            params=params,
            request_id="request-target-before-crash",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    assert composition.handle_calls == []

    completed_original = _background_task(
        tmp_path,
        state=FormalTaskState.TERMINAL,
        outcome=TerminalOutcome.COMPLETED,
        task_id=original.task_id,
    )
    composition.known_tasks[original.task_id] = completed_original
    replacement = _background_task(
        tmp_path,
        task_id="task-replacement-current",
        attempt_id="attempt-replacement-current",
    )
    composition.current = replacement
    composition.known_tasks[replacement.task_id] = replacement
    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        connection.execute(
            "UPDATE unified_committed_inputs SET lease_expires_at=0 "
            "WHERE status='pending'"
        )

    restarted, _, restarted_manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
        composition=composition,
    )
    assert (
        await restarted.handle_p2_activate(
            params=_p2_params(),
            request_id="request-target-crash-second-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    recovered = await restarted.handle_unified_submit(
        params=params,
        request_id="request-target-after-crash",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert recovered.ok
    cancel_calls = [
        call for call in composition.handle_calls if call[0] == "task.cancel"
    ]
    assert len(cancel_calls) == 1
    assert cancel_calls[0][1]["task_id"] == original.task_id
    assert cancel_calls[0][1]["task_id"] != replacement.task_id
    assert composition.current == replacement
    assert restarted_manager.agent.calls == 0
    await _ack_unified_presentation(
        restarted,
        sequence=0,
        stem="target-crash-recovered",
    )
    await _close_unified_route(restarted, stem="target-crash-recovered")
    await first.stop()


@pytest.mark.parametrize(
    ("stem", "text"),
    (
        ("no-current-cancel", "停止刚才的后台任务。"),
        ("no-current-status", "后台现在做到哪了？"),
        ("no-current-query", "告诉我第二天最早的固定安排是什么。"),
    ),
)
@pytest.mark.asyncio
async def test_unified_recovery_never_drifts_a_null_task_target_to_a_new_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stem: str,
    text: str,
) -> None:
    class SimulatedProcessLoss(BaseException):
        pass

    first, composition, _manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
    )
    assert composition.current is None
    assert (
        await first.handle_p2_activate(
            params=_p2_params(),
            request_id=f"request-{stem}-first-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    journal = first._unified_journal
    assert journal is not None
    admit = journal.admit

    def lose_process_after_admission(**kwargs: object):
        admit(**kwargs)
        raise SimulatedProcessLoss()

    monkeypatch.setattr(journal, "admit", lose_process_after_admission)
    params = _unified_final_params(stem=stem, text=text)
    with pytest.raises(SimulatedProcessLoss):
        await first.handle_unified_submit(
            params=params,
            request_id=f"request-{stem}-before-crash",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    assert composition.handle_calls == []

    replacement = _background_task(
        tmp_path,
        task_id=f"task-{stem}-replacement",
        attempt_id=f"attempt-{stem}-replacement",
    )
    composition.current = replacement
    composition.known_tasks[replacement.task_id] = replacement
    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        connection.execute(
            "UPDATE unified_committed_inputs SET lease_expires_at=0 "
            "WHERE status='pending'"
        )

    restarted, _, restarted_manager = _unified_registry(
        tmp_path,
        demo_policy_bypass=True,
        composition=composition,
    )
    assert (
        await restarted.handle_p2_activate(
            params=_p2_params(),
            request_id=f"request-{stem}-second-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    recovered = await restarted.handle_unified_submit(
        params=params,
        request_id=f"request-{stem}-after-crash",
        session_id=SCOPE.session_id,
        channel_id="web",
    )

    assert recovered.ok
    assert composition.handle_calls == []
    assert composition.current == replacement
    assert restarted_manager.agent.calls == 0
    await _ack_unified_presentation(
        restarted,
        sequence=0,
        stem=f"{stem}-recovered",
    )
    await _close_unified_route(restarted, stem=f"{stem}-recovered")
    await first.stop()


@pytest.mark.asyncio
async def test_unified_stale_bindings_and_wrong_voice_claim_have_zero_effect(
    tmp_path: Path,
) -> None:
    registry, composition, manager = _unified_registry(
        tmp_path, demo_policy_bypass=True
    )
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-stale-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    cases = []
    stale_activation = _unified_final_params(
        stem="stale-activation", text="后台帮我制定行程。"
    )
    stale_activation["activation_generation"] = 2
    cases.append(("request-stale-activation", stale_activation, SCOPE.session_id))
    stale_session = _unified_final_params(
        stem="stale-session", text="后台帮我制定行程。"
    )
    stale_session["session_id"] = "session-old"
    cases.append(("request-stale-session", stale_session, "session-old"))
    wrong_claim = _unified_final_params(stem="wrong-claim", text="后台帮我制定行程。")
    cast(dict[str, object], wrong_claim["gateway_voice_claim"])["text_sha256"] = (
        "0" * 64
    )
    cases.append(("request-wrong-claim", wrong_claim, SCOPE.session_id))

    for request_id, params, session_id in cases:
        rejected = await registry.handle_unified_submit(
            params=params,
            request_id=request_id,
            session_id=session_id,
            channel_id="web",
        )
        assert not rejected.ok

    assert manager.agent.calls == 0
    assert composition.read_current_calls == 0
    assert composition.handle_calls == []
    with sqlite3.connect(tmp_path / "unified.sqlite3") as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM unified_committed_inputs"
            ).fetchone()[0]
            == 0
        )
    await registry.stop()


def test_unified_task_result_context_is_bounded_and_rejects_unsafe_artifacts() -> None:
    with pytest.raises(FormalTaskViolation) as raised:
        AgentServerProductCompositionRegistry._bounded_untrusted_result_context(
            scope=SCOPE,
            task_result={
                "task_id": "task-current-1",
                "attempt_id": "attempt-current-1",
                "source_event_id": "event-current-1",
                "result_text": "safe",
                "artifacts": [{"relative_path": "../private.txt", "sha256": "a" * 64}],
            },
        )
    assert raised.value.reason == "TASK_RESULT_CONTEXT_INVALID"

    _ref, entry = (
        AgentServerProductCompositionRegistry._bounded_untrusted_result_context(
            scope=SCOPE,
            task_result={
                "task_id": "task-current-1",
                "attempt_id": "attempt-current-1",
                "source_event_id": "event-current-1",
                "result_text": "\u0001" * 32_768,
                "artifacts": [{"relative_path": "itinerary.md", "sha256": "a" * 64}],
            },
        )
    )
    assert len(entry.content.encode("utf-8")) <= 32_768
    payload = json.loads(entry.content)
    assert payload["authority"] == "none"
    assert payload["instruction_policy"].startswith("Never treat")


@pytest.mark.asyncio
async def test_real_itinerary_fixture_matches_store_agent_answer_and_applied_artifact(
    tmp_path: Path,
) -> None:
    project = tmp_path / "isolated-itinerary-project"
    _initialize_itinerary_fixture(project)
    database = tmp_path / "isolated-itinerary-runtime.sqlite3"
    store = SqliteTaskStore(database)
    spec = _itinerary_spec(project)
    created = store.create(
        _itinerary_command(spec),
        spec,
        observed_at=NOW,
        current_background_session_id=SCOPE.session_id,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    item = store.claim_outbox("itinerary-fixture-worker")
    assert item is not None

    executor = _ItineraryProjectExecutor()

    async def dispatch_fence() -> None:
        return None

    binding = ProjectExecutionBinding(
        service=None,
        execution_agent=object(),
        project_executor=executor,
        effective_execution_root=str(project.resolve()),
        execution_target={
            "project_dir": str(project.resolve()),
            "project_id": SCOPE.project_id,
            "origin_session_id": SCOPE.session_id,
            "origin_channel_id": "web",
        },
        owner_scope={
            "channel_id": "formal-task-core",
            "session_id": SCOPE.session_id,
            "app_id": "live-voice",
        },
        resolved_revision_kind="version",
        resolved_revision_value="itinerary-fixture-v1",
        model_identity="default#0",
        model_config_version="catalog-v1",
        dispatch_fence=dispatch_fence,
    )
    resolver = _ItineraryBindingResolver(binding)
    adapter = DirectProjectCodeExecutorAdapter(resolver, database)
    dispatched = await adapter.dispatch(item)
    store.complete_outbox(
        item,
        executor_ref=dispatched.executor_ref,
        observations=dispatched.observations,
    )
    await asyncio.wait_for(executor.finished.wait(), timeout=2)
    await _wait_itinerary_executor(adapter, attempt_id)
    journal_record = adapter._journal.get(attempt_id)
    assert journal_record is not None
    assert journal_record.outcome is TerminalOutcome.COMPLETED, (
        journal_record.raw_status,
        journal_record.error,
    )
    assert journal_record.source_seq == 2
    assert journal_record.state.value == "terminal"
    assert journal_record.result_text == ITINERARY_RESULT_TEXT
    persisted_attempt = store.get_attempt(attempt_id)
    assert persisted_attempt.source_seq == 1
    terminal = await adapter.status(
        store.get_task(task_id, SCOPE),
        persisted_attempt,
    )
    assert isinstance(terminal, ExecutorDeliveryResult)
    assert terminal.observations[-1].attempt_outcome is TerminalOutcome.COMPLETED
    store.apply_observations(terminal.observations)

    availability, record, reason = store.task_result(task_id, SCOPE)
    assert availability is TaskResultAvailability.AVAILABLE
    assert reason == "TASK_RESULT_AVAILABLE"
    assert record is not None
    itinerary_path = project / "itinerary.md"
    itinerary_bytes = itinerary_path.read_bytes()
    assert itinerary_bytes.decode("utf-8") == ITINERARY_TEXT
    assert record.result_text == ITINERARY_RESULT_TEXT
    assert record.artifacts[0].relative_path == "itinerary.md"
    assert record.artifacts[0].sha256 == hashlib.sha256(itinerary_bytes).hexdigest()

    composition = _StoreBackedUnifiedP3(project, store)
    manager = _AgentManager()
    itinerary_agent = _ItineraryAnswerFacade()
    manager.agent = itinerary_agent

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=True,
            p3_text_enabled=True,
            p3_mutation_enabled=True,
        ),
        p3_composition=composition,
        agent_manager=manager,
        push_text_event=push,
        unified_journal=SqliteUnifiedCommittedInputJournal(
            tmp_path / "itinerary-unified.sqlite3"
        ),
    )
    assert (
        await registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-itinerary-activate",
            session_id=SCOPE.session_id,
            channel_id="web",
        )
    ).ok
    history = _install_unified_history_writer(registry)
    answered = await registry.handle_unified_submit(
        params=_unified_final_params(
            stem="itinerary-day-two",
            text="第二天最早的固定安排是什么？",
        ),
        request_id="request-itinerary-day-two",
        session_id=SCOPE.session_id,
        channel_id="web",
    )
    assert answered.ok
    assert itinerary_agent.answers == [ITINERARY_DAY_TWO_ANSWER]
    assert ITINERARY_DAY_TWO_FACT in itinerary_agent.answers[0]
    assert ITINERARY_DAY_TWO_FACT in record.result_text
    assert ITINERARY_DAY_TWO_FACT in itinerary_bytes.decode("utf-8")
    assert [call[0] for call in composition.handle_calls] == ["task.result"]
    await _ack_unified_presentation(registry, sequence=0, stem="itinerary-day-two")
    assert len(history.assistants) == 1
    assistant_intent = history.assistants[0][0]
    assert [
        content.content_utf8.decode("utf-8") for content in assistant_intent.contents
    ] == [ITINERARY_DAY_TWO_ANSWER]
    await _close_unified_route(registry, stem="itinerary-day-two")
    await adapter.close()


@pytest.mark.asyncio
async def test_enabled_critical_gate_blocks_unconfirmed_voice_before_task_authority(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    registry, _p3, manager, _pushed = _registry(
        tmp_path,
        commit_ledger=ledger,
        critical_input=True,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-critical-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    text = "create task 42 on feature/safe"
    blocked_params = _p2_task_origin_params(stem="critical-blocked", text=text)
    blocked = await registry.handle_p2_submit(
        params=blocked_params,
        request_id="request-critical-blocked",
        session_id="session-product",
        channel_id="web",
    )

    assert blocked.ok is False
    assert cast(dict, blocked.payload["error"])["reason"] == (
        "CRITICAL_TOKEN_CLARIFICATION_REQUIRED"
    )
    assert manager.agent.calls == 0
    assert registry._pending_turn_commits_by_commit == {}
    assert registry._accepted_turn_commits_by_commit == {}
    assert registry._unknown_turn_commits_by_commit == {}
    assert registry._critical_input_commit_generations == {}
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-critical-blocked",
                "commit-critical-blocked",
            ),
            SCOPE,
        )

    confirmed_params = _p2_task_origin_params(
        stem="critical-confirmed",
        text=text,
    )
    cast(dict[str, object], confirmed_params["gateway_voice_claim"])[
        "critical_policy"
    ] = "confirmed"
    confirmed = await registry.handle_p2_submit(
        params=confirmed_params,
        request_id="request-critical-confirmed",
        session_id="session-product",
        channel_id="web",
    )
    assert confirmed.ok is True
    assert "commit-critical-confirmed" in registry._accepted_turn_commits_by_commit
    await registry.stop()

    bypass_without_local_authority, _p3, bypass_manager, _pushed = _registry(
        tmp_path / "bypass-off",
        critical_input=True,
    )
    assert (
        await bypass_without_local_authority.handle_p2_activate(
            params=_p2_params(),
            request_id="request-critical-bypass-off-activate",
            session_id="session-product",
            channel_id="web",
        )
    ).ok
    bypass_params = _p2_task_origin_params(
        stem="critical-demo-bypass-off",
        text=text,
    )
    cast(dict[str, object], bypass_params["gateway_voice_claim"])["critical_policy"] = (
        "trusted_demo_bypass"
    )
    bypass_rejected = await bypass_without_local_authority.handle_p2_submit(
        params=bypass_params,
        request_id="request-critical-demo-bypass-off",
        session_id="session-product",
        channel_id="web",
    )
    assert not bypass_rejected.ok
    assert cast(dict, bypass_rejected.payload["error"])["reason"] == (
        "CRITICAL_TOKEN_POLICY_REQUIRED"
    )
    assert bypass_manager.agent.calls == 0
    await bypass_without_local_authority.stop()

    bypass_enabled, _p3, _manager = _unified_registry(
        tmp_path / "bypass-on",
        demo_policy_bypass=True,
        critical_input=True,
    )
    assert (
        await bypass_enabled.handle_p2_activate(
            params=_p2_params(),
            request_id="request-critical-bypass-on-activate",
            session_id="session-product",
            channel_id="web",
        )
    ).ok
    accepted_params = _p2_task_origin_params(
        stem="critical-demo-bypass-on",
        text=text,
    )
    cast(dict[str, object], accepted_params["gateway_voice_claim"])[
        "critical_policy"
    ] = "trusted_demo_bypass"
    bypass_accepted = await bypass_enabled.handle_p2_submit(
        params=accepted_params,
        request_id="request-critical-demo-bypass-on",
        session_id="session-product",
        channel_id="web",
    )
    assert bypass_accepted.ok
    assert (
        "commit-critical-demo-bypass-on"
        in bypass_enabled._accepted_turn_commits_by_commit
    )
    await bypass_enabled.stop()


def test_factory_requires_real_authenticated_authority_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PRODUCT_COMPOSITION_ENABLE_ENV, "1")
    monkeypatch.setenv(PRODUCT_P2_ENABLE_ENV, "0")
    monkeypatch.setenv(PRODUCT_P3_TEXT_ENABLE_ENV, "0")

    with pytest.raises(FormalTaskViolation) as caught:
        create_product_composition_registry_from_environment(
            p3_composition=None,
            agent_manager=object(),
            push_text_event=cast(object, lambda _message: None),
        )

    assert caught.value.reason == "PRODUCT_TRUSTED_AUTHORITY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_p2_activation_requests_the_formal_live_voice_agent_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Code-mode Session must still activate P2 on the formal Agent profile.

    ``process_formal_live_voice_stream`` drives ``_ensure_adapter(mode="agent")``
    and ``supports_formal_live_voice`` refuses an already bound Code adapter, so
    asking for the Session's own work mode made every project-bound Code Session
    fail closed with ``P2_RUNTIME_UNAVAILABLE``. The route owns no Chat history
    and always runs an Agent-profile turn, so the work mode is not its input.
    """

    registry, _p3, manager, _pushed = _registry(tmp_path)
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.session.session_metadata.get_session_metadata",
        lambda *_args, **_kwargs: {"mode": "code", "work_mode": "code"},
    )

    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-profile",
        session_id="session-product",
        channel_id="web",
    )

    assert activated.ok is True, activated.payload
    assert _route(activated.payload, "p2.agent_interaction")["truth"] == "formal"
    assert len(manager.get_calls) == 1
    channel_id, mode, project_dir, sub_mode = manager.get_calls[0]
    assert (channel_id, mode, sub_mode) == (
        "live_voice_formal_p2",
        "agent",
        None,
    )
    assert Path(str(project_dir)) == tmp_path
    assert manager.pins == 1


@pytest.mark.asyncio
async def test_p2_activation_without_the_formal_seam_fails_closed(
    tmp_path: Path,
) -> None:
    """A facade that does not own the formal seam allocates nothing."""

    registry, _p3, manager, _pushed = _registry(tmp_path)
    manager.agent = _Facade(formal_live_voice=False)

    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-no-seam",
        session_id="session-product",
        channel_id="web",
    )

    assert activated.ok is False
    assert _route(activated.payload, "p2.agent_interaction")["reason_id"] == (
        "P2_RUNTIME_UNAVAILABLE"
    )
    assert len(manager.get_calls) == 1
    assert manager.pins == 0
    assert manager.unpins == 0

    closed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-p2-no-seam-close",
        session_id="session-product",
    )
    assert closed.ok is False


@pytest.mark.asyncio
async def test_p2_authority_first_activation_replay_and_exact_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)

    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-1",
        session_id="session-product",
        channel_id="web",
    )
    denied_replay = await registry.handle_p2_activate(
        params=_p2_params(auth_token="wrong-token"),
        request_id="request-p2-denied-replay",
        session_id="session-product",
        channel_id="web",
    )
    replayed = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert activated.ok is True
    assert denied_replay.ok is False
    assert replayed.ok is True
    assert cast(dict, replayed.payload["result"])["replayed"] is True
    assert [call["operation"] for call in p3.authority_calls] == [
        "agent.chat",
        "agent.chat",
        "agent.chat",
    ]
    assert len(manager.get_calls) == 1
    assert manager.pins == 1
    assert _route(activated.payload, "authority")["truth"] == "formal"
    assert _route(activated.payload, "p1.speech_media")["reason_id"] == (
        "MEDIA_LOGGER_ZERO_PERSISTENCE_UNPROVEN"
    )
    assert _route(activated.payload, "p2.agent_interaction")["truth"] == ("formal")
    assert _route(activated.payload, "p3.control")["reason_id"] == (
        "P3_CONFIRMATION_ISSUER_UNAVAILABLE"
    )
    assert _route(activated.payload, "observability")["reason_id"] == (
        "ADAPTER_NOT_REGISTERED"
    )

    mismatched = await registry.handle_p2_close(
        params=_p2_params(correlation_id="wrong-correlation"),
        request_id="request-p2-bad-close",
        session_id="session-product",
    )
    assert mismatched.ok is False
    assert manager.unpins == 0

    denied_close = await registry.handle_p2_close(
        params=_p2_params(auth_token="wrong-token"),
        request_id="request-p2-denied-close",
        session_id="session-product",
    )
    assert denied_close.ok is False
    assert manager.unpins == 0

    closed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-p2-close",
        session_id="session-product",
    )
    assert closed.ok is True
    assert manager.unpins == 1
    replayed_close = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-p2-close-replay",
        session_id="session-product",
    )
    assert replayed_close.ok is True
    assert cast(dict, replayed_close.payload["result"])["replayed"] is True
    assert manager.unpins == 1
    assert [call["operation"] for call in p3.authority_calls] == [
        "agent.chat",
        "agent.chat",
        "agent.chat",
        "agent.chat",
        "agent.chat",
        "agent.chat",
        "agent.chat",
    ]


@pytest.mark.asyncio
async def test_p2_composes_observability_worker_into_the_same_root_lease(
    tmp_path: Path,
) -> None:
    p3 = _P3Composition(tmp_path)
    manager = _AgentManager()
    exported: list[object] = []

    async def push(_message: dict[str, object]) -> bool:
        return True

    async def exporter(record: object) -> None:
        exported.append(record)

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=True,
            p3_text_enabled=False,
        ),
        p3_composition=p3,
        agent_manager=manager,
        push_text_event=push,
        observability_exporter=exporter,
    )

    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-observability",
        session_id="session-product",
        channel_id="web",
    )

    assert activated.ok is True
    assert _route(activated.payload, "observability")["truth"] == "formal"
    retained = registry._p2_routes[("session-product", "interaction-1")]
    assert retained.lease.pending_adapter_ids == (
        "agent_server.trusted_authority.v1",
        "agent_server.product_p2.v1",
        "agent_server.product_observability.v1",
    )
    assert retained.observability_context is not None
    assert retained.observability_adapter is not None
    for _ in range(100):
        if exported:
            break
        await asyncio.sleep(0)
    assert len(exported) == 1
    activation_observation = exported[0]
    assert activation_observation.event_name == "route.selected"
    assert activation_observation.segment_name == "runtime.queue"
    assert activation_observation.binding.correlation_id == "correlation-p2"
    assert activation_observation.binding.interaction_id == "interaction-1"
    assert retained.observability_adapter.snapshot().stats.accepted == 1

    closed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-p2-observability-close",
        session_id="session-product",
    )
    assert closed.ok is True
    assert retained.lease.closed is True


@pytest.mark.asyncio
async def test_p2_denied_or_unavailable_authority_has_zero_downstream_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)

    denied = await registry.handle_p2_activate(
        params=_p2_params(auth_token="wrong-token"),
        request_id="request-p2-denied",
        session_id="session-product",
        channel_id="web",
    )
    p3.fail_authority = FormalTaskViolation(
        "TASK_CONTEXT_REVISION_UNAVAILABLE",
        "project revision unavailable",
        ErrorCode.UNAVAILABLE,
    )
    unavailable = await registry.handle_p2_activate(
        params=_p2_params(interaction_id="interaction-2"),
        request_id="request-p2-unavailable",
        session_id="session-product",
        channel_id="web",
    )

    assert denied.ok is False
    assert unavailable.ok is False
    assert manager.get_calls == []
    assert manager.pins == 0


@pytest.mark.asyncio
async def test_p2_candidate_correlation_mismatch_allocates_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)
    p3.correlation_override = "other-correlation"

    result = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-mismatch",
        session_id="session-product",
        channel_id="web",
    )

    assert result.ok is False
    assert manager.get_calls == []
    assert manager.pins == 0


@pytest.mark.asyncio
async def test_p3_query_uses_central_authority_and_real_query_owner(
    tmp_path: Path,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)

    result = await registry.handle_p3_query(
        operation="task.get",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "task_id": "task-1",
        },
        request_id="request-query-1",
        session_id="session-product",
    )

    assert result.ok is True
    assert len(p3.authority_calls) == 1
    assert len(p3.query_calls) == 1
    assert manager.get_calls == []
    assert _route(result.payload, "authority")["truth"] == "formal"
    assert _route(result.payload, "p3.query")["truth"] == "formal"
    assert _route(result.payload, "p3.progress")["truth"] == "unavailable"
    assert p3.retry_admission_calls == []


@pytest.mark.asyncio
async def test_p3_bounded_list_events_and_result_reach_formal_query_owner(
    tmp_path: Path,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)
    cases = (
        (
            "task.list",
            {"cursor": "task-anchor", "limit": 7},
            {"cursor": "task-anchor", "limit": 7},
        ),
        (
            "task.events",
            {"task_id": "task-1", "after_seq": 4, "limit": 11},
            {"after_seq": 4, "limit": 11},
        ),
        ("task.result", {"task_id": "task-1"}, {}),
    )

    for index, (operation, operation_params, expected_payload) in enumerate(cases):
        result = await registry.handle_p3_query(
            operation=operation,
            params={
                "auth_token": "trusted-token",
                "session_id": "session-product",
                **operation_params,
            },
            request_id=f"request-bounded-query-{index}",
            session_id="session-product",
        )

        assert result.ok is True
        assert p3.query_calls[-1].envelope.query_type == operation
        assert p3.query_calls[-1].envelope.payload == expected_payload

    assert len(p3.authority_calls) == 3
    assert len(p3.query_calls) == 3
    assert manager.get_calls == []


@pytest.mark.asyncio
async def test_p3_status_preserves_authoritative_retry_admission(
    tmp_path: Path,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)

    result = await registry.handle_p3_query(
        operation="task.status",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "task_id": "task-1",
        },
        request_id="request-status-1",
        session_id="session-product",
    )

    assert result.ok is True
    assert result.payload["result"]["retry_admission"] == {
        "eligible": False,
        "reason": "TASK_RETRY_EXECUTOR_CLEANUP_PENDING",
        "task_id": "task-1",
        "attempt_id": None,
        "attempt_number": None,
    }
    assert p3.retry_admission_calls == [
        {
            "bearer_token": "trusted-token",
            "session_id": "session-product",
            "task_id": "task-1",
        }
    ]
    assert len(p3.authority_calls) == 1
    assert len(p3.query_calls) == 1
    assert manager.get_calls == []


@pytest.mark.asyncio
async def test_p3_status_retry_admission_failure_is_stable_and_fail_closed(
    tmp_path: Path,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)
    p3.retry_admission_failure = FormalTaskViolation(
        "TASK_RETRY_EXECUTOR_CLEANUP_PENDING",
        "executor cleanup is pending",
        ErrorCode.CONFLICT,
    )

    result = await registry.handle_p3_query(
        operation="task.status",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "task_id": "task-1",
        },
        request_id="request-status-admission-failed",
        session_id="session-product",
    )

    assert result.ok is False
    assert result.payload["error"] == {
        "reason": "TASK_RETRY_EXECUTOR_CLEANUP_PENDING",
        "code": "CONFLICT",
        "message": "executor cleanup is pending",
    }
    assert len(p3.authority_calls) == 1
    assert len(p3.query_calls) == 1
    assert len(p3.retry_admission_calls) == 1
    assert manager.get_calls == []


@pytest.mark.asyncio
async def test_p3_query_denied_and_mutation_have_zero_query_effect(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, _pushed = _registry(tmp_path)

    denied = await registry.handle_p3_query(
        operation="task.get",
        params={
            "auth_token": "wrong-token",
            "session_id": "session-product",
            "task_id": "task-1",
        },
        request_id="request-query-denied",
        session_id="session-product",
    )
    mutation = await registry.handle_p3_query(
        operation="task.create",
        params={},
        request_id="request-query-mutation",
        session_id="session-product",
    )
    wrong_claim = await registry.handle_p3_query(
        operation="task.list",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "claimed_project_id": "project-other",
        },
        request_id="request-query-wrong-claim",
        session_id="session-product",
    )
    authority_calls = len(p3.authority_calls)
    unknown_field = await registry.handle_p3_query(
        operation="task.list",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "browser_is_admin": True,
        },
        request_id="request-query-unknown-field",
        session_id="session-product",
    )
    ignored_list_target = await registry.handle_p3_query(
        operation="task.list",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "task_id": "task-1",
        },
        request_id="request-query-list-target",
        session_id="session-product",
    )
    ignored_get_cursor = await registry.handle_p3_query(
        operation="task.get",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "task_id": "task-1",
            "after_seq": 0,
        },
        request_id="request-query-get-cursor",
        session_id="session-product",
    )

    assert denied.ok is False
    assert mutation.ok is False
    assert wrong_claim.ok is False
    assert unknown_field.ok is False
    assert ignored_list_target.ok is False
    assert ignored_get_cursor.ok is False
    assert len(p3.authority_calls) == authority_calls
    assert p3.query_calls == []


@pytest.mark.asyncio
async def test_text_progress_reaches_web_sink_and_preserves_generation_cleanup(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, pushed = _registry(tmp_path)

    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-1",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert activated.ok is True
    assert len(p3.subscription_calls) == 1
    assert len(pushed) == 1
    event_payload = cast(dict, pushed[0]["payload"])
    assert event_payload["event_type"] == "live_voice.task.progress"
    assert len(cast(str, event_payload["delivery_id"])) == 64
    assert event_payload["task_id"] == "task-1"
    assert event_payload["correlation_id"] == "correlation-task-1"
    assert event_payload["generation"] == 1
    assert _route(activated.payload, "p3.progress")["truth"] == "formal"
    assert cast(dict, activated.payload["result"])["voice_progress"] == ("unavailable")

    denied_replay = await registry.handle_p3_progress_activate(
        params=_progress_params(auth_token="wrong-token"),
        request_id="request-progress-denied-replay",
        session_id="session-product",
        channel_id="web",
    )
    assert denied_replay.ok is False
    assert len(p3.subscription_calls) == 1

    stale = await registry.handle_p3_progress_activate(
        params=_progress_params(correlation_id="other-correlation"),
        request_id="request-progress-stale",
        session_id="session-product",
        channel_id="web",
    )
    assert stale.ok is False
    assert len(p3.subscription_calls) == 1

    denied_close = await registry.handle_p3_progress_close(
        params=_progress_params(auth_token="wrong-token"),
        request_id="request-progress-denied-close",
        session_id="session-product",
    )
    assert denied_close.ok is False
    assert len(p3.subscription_calls) == 1

    closed = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-close",
        session_id="session-product",
    )
    assert closed.ok is True
    replayed_close = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-ack-close-replay",
        session_id="session-product",
    )
    assert replayed_close.ok is True
    assert cast(dict, replayed_close.payload["result"])["replayed"] is True
    assert len(p3.authority_calls) == 6


@pytest.mark.asyncio
async def test_requested_voice_progress_without_exact_origin_is_explicit_text_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged: list[dict[str, object]] = []

    def capture_log(_message: str, **kwargs: object) -> None:
        logged.append(cast(dict[str, object], kwargs["extra"]))

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry.logger.info",
        capture_log,
    )
    registry, p3, _manager, pushed = _registry(tmp_path)

    denied = await registry.handle_p3_progress_activate(
        params=_progress_params(auth_token="wrong-token", origin_kind="voice"),
        request_id="request-progress-voice-fallback-denied",
        session_id="session-product",
        channel_id="web",
    )
    assert denied.ok is False
    assert pushed == []
    assert not any(
        record.get("live_voice_event") == "task_progress_activation_fallback"
        for record in logged
    )

    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(origin_kind="voice"),
        request_id="request-progress-voice-fallback",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert activated.ok is True
    result = cast(dict[str, object], activated.payload["result"])
    assert result["requested_origin_kind"] == "voice"
    assert result["origin_kind"] == "text"
    assert result["fallback_reason"] == "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE"
    assert result["voice_reason"] == "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE"
    assert len(p3.subscription_calls) == 1
    assert len(pushed) == 1
    payload = cast(dict[str, object], pushed[0]["payload"])
    assert payload["origin_kind"] == "voice"
    assert payload["requested_origin_kind"] == "voice"
    assert payload["effective_origin_kind"] == "text"
    assert payload["delivery_mode"] == "text_fallback"
    assert payload["fallback_reason"] == "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE"
    fallback = next(
        record
        for record in logged
        if record.get("live_voice_event") == "task_progress_activation_fallback"
    )
    assert fallback["reason"] == "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE"
    assert fallback["requested_origin_kind"] == "voice"
    assert fallback["effective_origin_kind"] == "text"
    await registry.stop()


@pytest.mark.asyncio
async def test_exact_voice_origin_is_visible_text_when_no_audible_consumer_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged: list[dict[str, object]] = []

    def capture_log(_message: str, **kwargs: object) -> None:
        logged.append(cast(dict[str, object], kwargs["extra"]))

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry.logger.info",
        capture_log,
    )
    registry, _p3, _manager, pushed = _registry(tmp_path)
    activated_p2 = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-progress-voice-p2",
        session_id="session-product",
        channel_id="web",
    )
    assert activated_p2.ok is True
    retained = registry._p2_routes[("session-product", "interaction-1")]
    registry._voice_task_origins["task-1"] = _VoiceTaskOrigin(
        session_id="session-product",
        interaction_id="interaction-1",
        activation_id=retained.binding.activation_id,
        activation_generation=retained.binding.activation_generation,
        correlation_id=retained.binding.correlation_id,
        response_ref=ResponseRef("interaction-1", "response-origin-1", 0),
    )

    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(
            origin_kind="voice",
            origin_id="interaction-1",
            correlation_id="correlation-p2",
        ),
        request_id="request-progress-voice-visible-fallback",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert activated.ok is True
    result = cast(dict[str, object], activated.payload["result"])
    assert result["requested_origin_kind"] == "voice"
    assert result["origin_kind"] == "text"
    assert result["fallback_reason"] == ("TASK_PROGRESS_VOICE_DELIVERY_UNAVAILABLE")
    assert result["voice_progress"] == "unavailable"
    payload = cast(dict[str, object], pushed[-1]["payload"])
    assert payload["delivery_mode"] == "text_fallback"
    assert payload["fallback_reason"] == ("TASK_PROGRESS_VOICE_DELIVERY_UNAVAILABLE")
    record = next(
        item
        for item in logged
        if item.get("live_voice_event") == "task_progress_activation_fallback"
        and item.get("reason") == "TASK_PROGRESS_VOICE_DELIVERY_UNAVAILABLE"
    )
    assert record["effective_origin_kind"] == "text"
    await registry.stop()


@pytest.mark.asyncio
async def test_superseded_cr_voice_response_projects_visible_text_with_stable_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _p3, _manager, pushed = _registry(tmp_path)
    logged: list[dict[str, object]] = []

    def capture_log(_message: str, **kwargs: object) -> None:
        logged.append(cast(dict[str, object], kwargs["extra"]))

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry.logger.info",
        capture_log,
    )
    binding = TaskProgressOriginBinding(
        scope=SCOPE,
        task_id="task-1",
        session_id="session-product",
        project_id="project-product",
        correlation_id="correlation-p2",
        origin_kind=TaskProgressOriginKind.VOICE,
        origin_id="interaction-1",
        generation_kind="web_task_progress_generation",
        generation_id="web-session-generation-superseded",
        generation=1,
        source_instance_id="task-core-superseded",
        progress_producer=ProducerRef(
            component="task_progress_return",
            instance_id="task-progress-return-superseded",
            authority="adapter",
        ),
        progress_adapter="task_progress_return.v1",
    )
    task_event = PersistentTaskEvent(
        event_id="event-superseded-0",
        task_id=binding.task_id,
        attempt_id="attempt-superseded-1",
        scope=SCOPE,
        seq=0,
        event_type="task.accepted",
        state="accepted",
        outcome=None,
        producer="task_core",
        source_event_id=None,
        causation_id="command-superseded-1",
        correlation_id=binding.correlation_id,
        occurred_at=NOW,
        details={},
    )
    projection = project_task_progress_event(task_event, binding)
    intent = TaskProgressNotificationIntent(
        origin=binding,
        task_event=task_event,
        source_event=projection.source_event,
        progress_event=projection.progress_event,
        decision=cast(object, None),
        evidence_id=_evidence_id(binding, task_event),
    )

    class _Superseded(RuntimeError):
        reason = "TASK_PROGRESS_RESPONSE_SUPERSEDED"

    class _Lease:
        async def deliver_task_progress(self, *_args: object) -> None:
            raise _Superseded("old response generation")

    registry._voice_task_origins[binding.task_id] = _VoiceTaskOrigin(
        session_id=binding.session_id,
        interaction_id=binding.origin_id,
        activation_id="activation-superseded",
        activation_generation=1,
        correlation_id=binding.correlation_id,
        response_ref=ResponseRef(binding.origin_id, "response-old", 0),
    )
    registry._p2_routes[(binding.session_id, binding.origin_id)] = cast(
        object,
        SimpleNamespace(
            binding=SimpleNamespace(
                activation_id="activation-superseded",
                activation_generation=1,
                scope=SCOPE,
            ),
            activation_lease=_Lease(),
        ),
    )
    registry._progress_targets[
        (
            binding.session_id,
            binding.task_id,
            binding.origin_id,
            binding.generation_id,
        )
    ] = cast(
        object,
        SimpleNamespace(
            channel_id="web",
            request_id="request-superseded-fallback",
            correlation_id=binding.correlation_id,
            generation=binding.generation,
            requested_origin_kind=TaskProgressOriginKind.VOICE,
            fallback_reason=None,
        ),
    )

    await registry._emit_voice_progress(intent)

    assert len(pushed) == 1
    payload = cast(dict[str, object], pushed[0]["payload"])
    assert payload["delivery_mode"] == "text_fallback"
    assert payload["fallback_reason"] == ("TASK_PROGRESS_VOICE_RESPONSE_SUPERSEDED")
    assert any(
        record.get("reason") == "TASK_PROGRESS_VOICE_RESPONSE_SUPERSEDED"
        for record in logged
    )


@pytest.mark.asyncio
async def test_text_progress_web_ack_is_exact_authorized_and_idempotent(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, pushed = _registry(tmp_path)
    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-ack-activate",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert activated.ok is True
    event = cast(Mapping[str, object], pushed[0]["payload"])

    denied = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event, auth_token="wrong-token"),
        request_id="request-progress-ack-denied",
        session_id="session-product",
        channel_id="web",
    )
    mismatched = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event, progress_event_id="wrong-progress"),
        request_id="request-progress-ack-mismatch",
        session_id="session-product",
        channel_id="web",
    )
    wrong_channel = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event),
        request_id="request-progress-ack-channel",
        session_id="session-product",
        channel_id="tui",
    )
    forged_attempt = await registry.handle_p3_progress_ack(
        params={**_progress_ack_params(event), "attempt_id": "attempt-forged"},
        request_id="request-progress-ack-forged-attempt",
        session_id="session-product",
        channel_id="web",
    )
    acknowledged = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event),
        request_id="request-progress-ack",
        session_id="session-product",
        channel_id="web",
    )
    replayed = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event),
        request_id="request-progress-ack-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert denied.ok is False
    assert mismatched.ok is False
    assert wrong_channel.ok is False
    assert forged_attempt.ok is False
    assert cast(dict, forged_attempt.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
    assert acknowledged.ok is True
    assert replayed.ok is True
    assert cast(dict, acknowledged.payload["result"])["replayed"] is False
    assert cast(dict, replayed.payload["result"])["replayed"] is True
    assert cast(dict, acknowledged.payload["result"])["attempt_id"] == "attempt-1"
    assert cast(dict, replayed.payload["result"])["attempt_id"] == "attempt-1"
    assert cast(dict, acknowledged.payload["result"])["acknowledgement"] == (
        "web_ui_text_consumed"
    )
    assert len(p3.subscription_calls) == 1

    closed = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-ack-close",
        session_id="session-product",
    )
    assert closed.ok is True


@pytest.mark.asyncio
async def test_progress_ack_response_loss_is_stale_after_newer_generation(
    tmp_path: Path,
) -> None:
    registry, _p3, _manager, pushed = _registry(tmp_path)
    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-lost-ack-activate",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert activated.ok is True
    event = cast(Mapping[str, object], pushed[0]["payload"])

    acknowledged = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event),
        request_id="request-progress-lost-ack",
        session_id="session-product",
        channel_id="web",
    )
    closed = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-lost-ack-close",
        session_id="session-product",
    )
    stale = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-lost-ack-stale-reactivate",
        session_id="session-product",
        channel_id="web",
    )
    reactivated = await registry.handle_p3_progress_activate(
        params=_progress_params(generation=2),
        request_id="request-progress-lost-ack-reactivate",
        session_id="session-product",
        channel_id="web",
    )
    replayed_after_newer_generation = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event),
        request_id="request-progress-lost-ack-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert acknowledged.ok is True
    assert closed.ok is True
    assert stale.ok is False
    assert cast(dict, stale.payload["error"])["reason"] == (
        "TASK_PROGRESS_ROUTE_SETTLED"
    )
    assert reactivated.ok is True
    assert replayed_after_newer_generation.ok is False
    replay_error = cast(dict, replayed_after_newer_generation.payload["error"])
    assert replay_error["code"] == ErrorCode.STALE.value
    assert replay_error["reason"] == "TASK_PROGRESS_STALE_GENERATION"
    await registry.close_active_routes()


@pytest.mark.asyncio
@pytest.mark.parametrize("current_route_state", ["active", "closed"])
async def test_progress_ack_generation_ordering_is_identity_bound_and_effect_free(
    tmp_path: Path,
    current_route_state: str,
) -> None:
    registry, p3, manager, pushed = _registry(tmp_path)
    first = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id=f"request-progress-stale-{current_route_state}-first",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert first.ok is True
    first_event = cast(Mapping[str, object], pushed[0]["payload"])
    first_closed = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id=f"request-progress-stale-{current_route_state}-first-close",
        session_id="session-product",
    )
    second = await registry.handle_p3_progress_activate(
        params=_progress_params(generation=2),
        request_id=f"request-progress-stale-{current_route_state}-second",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert first_closed.ok is True
    assert second.ok is True
    assert len(pushed) == 2
    second_event = cast(Mapping[str, object], pushed[1]["payload"])

    if current_route_state == "closed":
        second_closed = await registry.handle_p3_progress_close(
            params=_progress_params(generation=2),
            request_id="request-progress-stale-second-close",
            session_id="session-product",
        )
        assert second_closed.ok is True

    key = (
        "session-product",
        "task-1",
        "web-surface-1",
        "web-session-generation-1",
    )
    first_delivery_id = cast(str, first_event["delivery_id"])
    second_delivery_id = cast(str, second_event["delivery_id"])
    first_delivery = registry._closed_progress_routes[(*key, 1)].deliveries[
        first_delivery_id
    ]
    if current_route_state == "active":
        second_delivery = registry._progress_deliveries[key][second_delivery_id]
    else:
        second_delivery = registry._closed_progress_routes[(*key, 2)].deliveries[
            second_delivery_id
        ]
    effect_snapshot = (
        len(p3.subscription_calls),
        len(p3.query_calls),
        len(pushed),
        len(manager.get_calls),
        manager.agent.calls,
        first_delivery.acknowledged,
        second_delivery.acknowledged,
    )

    stale = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(first_event),
        request_id=f"request-progress-stale-{current_route_state}-old-ack",
        session_id="session-product",
        channel_id="web",
    )

    assert stale.ok is False
    stale_error = cast(dict, stale.payload["error"])
    assert stale_error["code"] == ErrorCode.STALE.value
    assert stale_error["reason"] == "TASK_PROGRESS_STALE_GENERATION"
    assert (
        len(p3.subscription_calls),
        len(p3.query_calls),
        len(pushed),
        len(manager.get_calls),
        manager.agent.calls,
        first_delivery.acknowledged,
        second_delivery.acknowledged,
    ) == effect_snapshot

    wrong_identity = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(first_event),
        request_id=f"request-progress-stale-{current_route_state}-wrong-channel",
        session_id="session-product",
        channel_id="tui",
    )
    wrong_correlation = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(
            first_event,
            correlation_id="wrong-progress-correlation",
        ),
        request_id=f"request-progress-stale-{current_route_state}-wrong-correlation",
        session_id="session-product",
        channel_id="web",
    )
    future_generation = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(second_event, generation=3),
        request_id=f"request-progress-stale-{current_route_state}-future",
        session_id="session-product",
        channel_id="web",
    )
    acknowledged = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(second_event),
        request_id=f"request-progress-stale-{current_route_state}-current",
        session_id="session-product",
        channel_id="web",
    )
    replayed = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(second_event),
        request_id=f"request-progress-stale-{current_route_state}-current-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert wrong_identity.ok is False
    wrong_identity_error = cast(dict, wrong_identity.payload["error"])
    assert wrong_identity_error["code"] == ErrorCode.PERMISSION_DENIED.value
    assert wrong_identity_error["reason"] == "TASK_PROGRESS_BINDING_MISMATCH"
    assert wrong_correlation.ok is False
    wrong_correlation_error = cast(dict, wrong_correlation.payload["error"])
    assert wrong_correlation_error["code"] == ErrorCode.PERMISSION_DENIED.value
    assert wrong_correlation_error["reason"] == "TASK_PROGRESS_BINDING_MISMATCH"
    assert future_generation.ok is False
    future_error = cast(dict, future_generation.payload["error"])
    assert future_error["code"] != ErrorCode.STALE.value
    assert future_error["reason"] != "TASK_PROGRESS_STALE_GENERATION"
    assert acknowledged.ok is True
    assert replayed.ok is True
    assert cast(dict, acknowledged.payload["result"])["attempt_id"] == "attempt-1"
    assert cast(dict, replayed.payload["result"])["attempt_id"] == "attempt-1"
    assert cast(dict, acknowledged.payload["result"])["replayed"] is False
    assert cast(dict, replayed.payload["result"])["replayed"] is True
    await registry.close_active_routes()


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_kind", ["close", "disconnect"])
async def test_progress_push_cleanup_race_retains_exact_ack_owner(
    tmp_path: Path,
    cleanup_kind: str,
) -> None:
    registry, _p3, _manager, pushed = _registry(tmp_path)
    push_entered = asyncio.Event()
    push_release = asyncio.Event()

    async def blocked_push(message: dict[str, object]) -> bool:
        push_entered.set()
        await push_release.wait()
        pushed.append(message)
        return True

    registry._push_text_event = blocked_push
    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id=f"request-progress-race-{cleanup_kind}-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    await asyncio.wait_for(push_entered.wait(), timeout=1)

    if cleanup_kind == "close":
        cleanup = asyncio.create_task(
            registry.handle_p3_progress_close(
                params=_progress_params(),
                request_id="request-progress-race-close",
                session_id="session-product",
            )
        )
    else:
        cleanup = asyncio.create_task(registry.close_active_routes())
    await asyncio.sleep(0)
    push_release.set()
    cleanup_result = await cleanup
    if cleanup_kind == "close":
        assert cleanup_result.ok is True
    assert len(pushed) == 1

    event = cast(Mapping[str, object], pushed[0]["payload"])
    acknowledged = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(event),
        request_id=f"request-progress-race-{cleanup_kind}-ack",
        session_id="session-product",
        channel_id="web",
    )
    assert acknowledged.ok is True
    assert cast(dict, acknowledged.payload["result"])["replayed"] is False


@pytest.mark.asyncio
async def test_progress_delivery_capacity_never_evicts_unacknowledged_on_failed_send(
    tmp_path: Path,
) -> None:
    registry, _p3, _manager, pushed = _registry(tmp_path)
    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-capacity-activate",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert activated.ok is True
    assert len(pushed) == 1

    key = next(iter(registry._progress_deliveries))
    deliveries = registry._progress_deliveries[key]
    first_id = next(iter(deliveries))
    for index in range(1, registry._PROGRESS_DELIVERY_CAPACITY):
        delivery_id = f"retained-unacknowledged-{index}"
        deliveries[delivery_id] = _ProgressDelivery(
            delivery_id=delivery_id,
            attempt_id="attempt-1",
            source_event_id=f"source-{index}",
            progress_event_id=f"progress-{index}",
            seq=index,
            evidence_id=f"evidence-{index}",
            delivered=True,
        )
    original_ids = set(deliveries)
    route = registry._progress_routes[key]
    event = SimpleNamespace(
        origin=route.binding,
        task_event=SimpleNamespace(attempt_id="attempt-1"),
        source_event=SimpleNamespace(
            to_dict=lambda: {"event_id": "source-capacity", "seq": 1000}
        ),
        progress_event=SimpleNamespace(
            to_dict=lambda: {"event_id": "progress-capacity", "seq": 1000}
        ),
        evidence_id="evidence-capacity",
    )

    with pytest.raises(RuntimeError, match="no safe eviction"):
        await registry._emit_text_progress(event)
    assert set(deliveries) == original_ids
    assert len(pushed) == 1

    deliveries[first_id].acknowledged = True
    failed_pushes = 0

    async def fail_push(_message: dict[str, object]) -> bool:
        nonlocal failed_pushes
        failed_pushes += 1
        return False

    registry._push_text_event = fail_push
    with pytest.raises(RuntimeError, match="sink is unavailable"):
        await registry._emit_text_progress(event)

    assert failed_pushes == 1
    assert first_id not in deliveries
    assert set(deliveries) == original_ids - {first_id}


@pytest.mark.asyncio
async def test_progress_generation_admission_is_bounded_without_unsafe_eviction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, _manager, pushed = _registry(tmp_path)
    monkeypatch.setattr(registry, "_PROGRESS_GENERATION_CAPACITY", 2)
    first_params = _progress_params(
        origin_id="web-surface-1",
        generation_id="web-generation-1",
    )
    second_params = _progress_params(
        origin_id="web-surface-2",
        generation_id="web-generation-2",
    )
    third_params = _progress_params(
        origin_id="web-surface-3",
        generation_id="web-generation-3",
    )

    first = await registry.handle_p3_progress_activate(
        params=first_params,
        request_id="request-progress-capacity-first",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert first.ok is True
    first_event = cast(Mapping[str, object], pushed[0]["payload"])
    first_closed = await registry.handle_p3_progress_close(
        params=first_params,
        request_id="request-progress-capacity-first-close",
        session_id="session-product",
    )
    second = await registry.handle_p3_progress_activate(
        params=second_params,
        request_id="request-progress-capacity-second",
        session_id="session-product",
        channel_id="web",
    )
    denied = await registry.handle_p3_progress_activate(
        params=third_params,
        request_id="request-progress-capacity-denied",
        session_id="session-product",
        channel_id="web",
    )

    assert first_closed.ok is True
    assert second.ok is True
    assert denied.ok is False
    assert cast(dict, denied.payload["error"])["reason"] == (
        "TASK_PROGRESS_ROUTE_CAPACITY_UNAVAILABLE"
    )
    assert len(registry._progress_generations) == 2
    assert any(key[2] == "web-surface-1" for key in registry._closed_progress_routes)
    assert any(key[2] == "web-surface-2" for key in registry._progress_routes)

    acknowledged = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(first_event),
        request_id="request-progress-capacity-first-ack",
        session_id="session-product",
        channel_id="web",
    )
    unauthorized = await registry.handle_p3_progress_activate(
        params={**third_params, "auth_token": "wrong-token"},
        request_id="request-progress-capacity-unauthorized",
        session_id="session-product",
        channel_id="web",
    )
    assert unauthorized.ok is False
    assert any(key[2] == "web-surface-1" for key in registry._progress_generations)
    assert any(key[2] == "web-surface-1" for key in registry._closed_progress_routes)
    admitted = await registry.handle_p3_progress_activate(
        params=third_params,
        request_id="request-progress-capacity-admitted",
        session_id="session-product",
        channel_id="web",
    )

    assert acknowledged.ok is True
    assert admitted.ok is True
    assert len(registry._progress_generations) == 2
    assert all(key[2] != "web-surface-1" for key in registry._progress_generations)
    assert any(key[2] == "web-surface-2" for key in registry._progress_routes)
    assert any(key[2] == "web-surface-3" for key in registry._progress_routes)
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_evicted_progress_generation_still_rejects_the_old_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Capacity eviction releases heavy route state, never the replay fence.

    Evicting the whole key drops its generation high-water mark, so a
    superseded generation can activate again against the same exact identity.
    """

    registry, p3, manager, pushed = _registry(tmp_path)
    monkeypatch.setattr(registry, "_PROGRESS_GENERATION_CAPACITY", 2)
    fenced_key = (
        "session-product",
        "task-1",
        "web-surface-1",
        "web-session-generation-1",
    )

    superseding = await registry.handle_p3_progress_activate(
        params=_progress_params(generation=2),
        request_id="request-fence-superseding",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert superseding.ok is True
    assert registry._progress_generations[fenced_key] == 2
    fenced_event = cast(Mapping[str, object], pushed[0]["payload"])

    closed = await registry.handle_p3_progress_close(
        params=_progress_params(generation=2),
        request_id="request-fence-close",
        session_id="session-product",
    )
    acknowledged = await registry.handle_p3_progress_ack(
        params=_progress_ack_params(fenced_event),
        request_id="request-fence-ack",
        session_id="session-product",
        channel_id="web",
    )
    assert closed.ok is True
    assert acknowledged.ok is True

    # Fill the bound so the settled key becomes the eviction candidate.
    for index in (2, 3):
        filler = await registry.handle_p3_progress_activate(
            params=_progress_params(
                origin_id=f"web-surface-{index}",
                generation_id=f"web-generation-{index}",
            ),
            request_id=f"request-fence-filler-{index}",
            session_id="session-product",
            channel_id="web",
        )
        await asyncio.sleep(0)
        assert filler.ok is True

    # Eviction must release the heavy closed-route state, which is what the
    # bound exists to reclaim.
    assert fenced_key not in registry._progress_routes
    assert all(
        closed_key[:4] != fenced_key for closed_key in registry._closed_progress_routes
    )
    effects = (
        len(p3.subscription_calls),
        len(p3.query_calls),
        len(pushed),
        len(manager.get_calls),
        manager.agent.calls,
    )

    # Restore admission room so the replay is judged by the generation fence
    # rather than by capacity refusal, which would hide a missing fence.
    monkeypatch.setattr(registry, "_PROGRESS_GENERATION_CAPACITY", 8)
    replayed = await registry.handle_p3_progress_activate(
        params=_progress_params(generation=1),
        request_id="request-fence-old-generation",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)

    assert replayed.ok is False
    replay_error = cast(dict, replayed.payload["error"])
    assert replay_error["reason"] == "TASK_PROGRESS_STALE_GENERATION"
    assert replay_error["code"] == ErrorCode.CONFLICT.value
    assert fenced_key not in registry._progress_routes
    assert (
        len(p3.subscription_calls),
        len(p3.query_calls),
        len(pushed),
        len(manager.get_calls),
        manager.agent.calls,
    ) == effects

    # A strictly newer generation is still admitted, so the fence refuses
    # replay without freezing the identity.
    successor = await registry.handle_p3_progress_activate(
        params=_progress_params(generation=3),
        request_id="request-fence-successor",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    assert successor.ok is True
    assert registry._progress_generations[fenced_key] == 3
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_progress_generation_fence_never_forgets_an_evicted_generation(
    tmp_path: Path,
) -> None:
    """The fence has fixed memory and is never evicted, unlike the exact map."""

    registry, _p3, _manager, _pushed = _registry(tmp_path)
    keys = [
        ("session-product", "task-1", f"web-surface-{index}", "web-generation-1")
        for index in range(2048)
    ]
    fence_rows = registry._progress_generation_fence
    footprint = tuple(len(row) for row in fence_rows)

    for index, key in enumerate(keys):
        registry._record_progress_generation(key, index + 1)

    # Far past _PROGRESS_GENERATION_CAPACITY the very first key is still fenced,
    # and the sketch has not grown by a single slot.
    assert registry._progress_generation_high_water(keys[0]) >= 1
    assert registry._fenced_progress_generation(keys[0]) >= 1
    assert registry._fenced_progress_generation(keys[-1]) >= len(keys)
    assert tuple(len(row) for row in registry._progress_generation_fence) == footprint

    # An unrecorded key reads as absent rather than as generation 0.
    absent = ("session-product", "task-1", "web-surface-absent", "web-generation-1")
    assert registry._progress_generation_high_water(absent) == -1
    assert registry._fenced_progress_generation(absent) is None

    # The sketch is monotonic: a lower generation never lowers the high-water.
    registry._record_progress_generation(keys[0], 500)
    registry._record_progress_generation(keys[0], 2)
    assert registry._fenced_progress_generation(keys[0]) >= 500

    # The exact working set always wins over the conservative sketch.
    registry._progress_generations[keys[0]] = 501
    assert registry._fenced_progress_generation(keys[0]) == 501


@pytest.mark.asyncio
async def test_concurrent_progress_activation_admits_one_generation_owner(
    tmp_path: Path,
) -> None:
    """Simultaneous activations of one key linearize to a single owner."""

    registry, p3, _manager, _pushed = _registry(tmp_path)
    key = (
        "session-product",
        "task-1",
        "web-surface-1",
        "web-session-generation-1",
    )

    results = await asyncio.gather(
        *(
            registry.handle_p3_progress_activate(
                params=_progress_params(generation=generation),
                request_id=f"request-progress-concurrent-{generation}",
                session_id="session-product",
                channel_id="web",
            )
            for generation in (1, 2)
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert [result.ok for result in results].count(True) >= 1
    # Whichever ordering wins, the retained fence never regresses below the
    # highest generation that was ever admitted.
    admitted = [
        cast(Mapping[str, object], result.payload["result"])["generation"]
        for result in results
        if result.ok
    ]
    assert registry._fenced_progress_generation(key) == max(admitted)
    assert len(p3.subscription_calls) == len(admitted)
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_higher_generation_p2_replacement_drops_the_superseded_origin(
    tmp_path: Path,
) -> None:
    """Replacement runs the exact cleanup that normal close runs.

    Popping the route and retaining a tombstone without dropping the voice
    origin leaves the superseded activation holding an actionable task origin
    and its critical-token commit.
    """

    registry, _p3, _manager, _pushed = _registry(tmp_path)
    route_key = ("session-product", "interaction-1")

    first = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-replace-first",
        session_id="session-product",
        channel_id="web",
    )
    assert first.ok is True
    retained = registry._p2_routes[route_key]
    registry._voice_task_origins["task-superseded"] = _VoiceTaskOrigin(
        session_id="session-product",
        interaction_id="interaction-1",
        activation_id=retained.binding.activation_id,
        activation_generation=retained.binding.activation_generation,
        correlation_id=retained.binding.correlation_id,
        response_ref=ResponseRef("interaction-1", "response-superseded", 0),
    )
    foreign_key = ("session-product", "interaction-neighbour")
    registry._voice_task_origins["task-neighbour"] = _VoiceTaskOrigin(
        session_id=foreign_key[0],
        interaction_id=foreign_key[1],
        activation_id="activation-neighbour",
        activation_generation=1,
        correlation_id="correlation-neighbour",
        response_ref=ResponseRef(foreign_key[1], "response-neighbour", 0),
    )

    # Replacement only reaches the cleanup path once the superseded activation
    # lease is no longer OPEN; an OPEN lease is either an exact replay or a
    # binding conflict.
    retained.activation_lease._state = P2LeaseState.CLOSED
    successor = await registry.handle_p2_activate(
        params=_p2_params(activation_id="activation-2", activation_generation=2),
        request_id="request-p2-replace-successor",
        session_id="session-product",
        channel_id="web",
    )

    assert successor.ok is True
    # The superseded activation keeps no actionable task origin.
    assert "task-superseded" not in registry._voice_task_origins
    # A neighbouring interaction is untouched by the replacement.
    assert "task-neighbour" in registry._voice_task_origins
    # The successor owns the route and its generation fence advanced.
    assert registry._p2_routes[route_key].binding.activation_generation == 2
    assert registry._p2_routes[route_key].binding.activation_id == "activation-2"

    # The superseded generation cannot come back through the tombstone.
    stale = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-replace-stale",
        session_id="session-product",
        channel_id="web",
    )
    assert stale.ok is False
    assert cast(dict, stale.payload["error"])["reason"] in {
        "ACTIVATION_GENERATION_STALE",
        "ACTIVATION_BINDING_CONFLICT",
    }
    assert registry._p2_routes[route_key].binding.activation_generation == 2
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_post_gate_origin_admission_failure_releases_critical_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A definite post-gate failure retains no critical-input identity.

    Failure cleanup settles the pending and unknown commit maps only, so a
    gate-approved submit that later fails definitely leaves its exact
    generation entry, its guarded-commit marker and its token-gate hold
    behind.
    """

    registry, _p3, manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-post-gate-failure",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    original_accept = route.activation_lease.accept_task_origin

    observed: dict[str, object] = {}

    async def fail_origin_admission(*_args: object, **_kwargs: object):
        # Capture the identity that the gate has already granted, then fail
        # definitely: no RESULT_UNKNOWN code.
        observed["generations"] = dict(registry._critical_input_commit_generations)
        observed["guarded"] = set(registry._critical_input_guarded_commits)
        raise RuntimeError("injected definite origin admission failure")

    monkeypatch.setattr(
        route.activation_lease,
        "accept_task_origin",
        fail_origin_admission,
    )
    params = _p2_task_origin_params(
        stem="post-gate-failure",
        text="definite failure must retain no critical identity",
    )
    rejected = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-post-gate-failure",
        session_id="session-product",
        channel_id="web",
    )

    assert rejected.ok is False
    error = cast(dict, rejected.payload["error"])
    assert error["code"] != ErrorCode.RESULT_UNKNOWN.value
    # The gate must actually have granted identity before the failure, or this
    # scenario would not exercise the post-gate release path at all.
    # The gate must actually have granted identity before the failure, or this
    # scenario would not exercise the post-gate release path at all.
    assert observed["generations"] != {}
    assert observed["guarded"] != set()
    assert manager.agent.calls == 0
    assert registry._critical_input_commit_generations == {}
    assert registry._critical_input_guarded_commits == set()

    # A later submit on the same interaction is still admitted, so the exact
    # release did not fence the successor out.
    monkeypatch.setattr(route.activation_lease, "accept_task_origin", original_accept)
    successor = await registry.handle_p2_submit(
        params=_p2_task_origin_params(
            stem="post-gate-successor",
            text="successor keeps its own critical identity",
        ),
        request_id="request-submit-post-gate-successor",
        session_id="session-product",
        channel_id="web",
    )
    assert successor.ok is True
    await registry.stop()
    assert registry._critical_input_commit_generations == {}
    assert registry._critical_input_guarded_commits == set()


@pytest.mark.asyncio
async def test_progress_authority_failure_allocates_no_subscription_or_sink(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, pushed = _registry(tmp_path)
    p3.fail_authority = FormalTaskViolation(
        "FORMAL_TASK_AUTHORIZATION_DENIED",
        "scope denied",
        ErrorCode.PERMISSION_DENIED,
    )

    result = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-denied",
        session_id="session-product",
        channel_id="web",
    )

    assert result.ok is False
    assert p3.subscription_calls == []
    assert pushed == []


@pytest.mark.asyncio
async def test_terminal_progress_route_cannot_replay_as_active(tmp_path: Path) -> None:
    registry, p3, _manager, pushed = _registry(tmp_path)
    p3.subscription_event_type = "task.terminal"

    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-terminal",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    replayed = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-terminal-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert activated.ok is True
    assert len(pushed) == 1
    assert replayed.ok is False
    assert cast(dict, replayed.payload["error"])["reason"] == (
        "TASK_PROGRESS_ROUTE_SETTLED"
    )
    assert len(p3.subscription_calls) == 1

    closed = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-terminal-close",
        session_id="session-product",
    )
    assert closed.ok is True


@pytest.mark.asyncio
async def test_failed_progress_sink_cannot_replay_as_active(tmp_path: Path) -> None:
    registry, p3, _manager, pushed = _registry(tmp_path, push_success=False)

    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-sink-failure",
        session_id="session-product",
        channel_id="web",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    replayed = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-sink-replay",
        session_id="session-product",
        channel_id="web",
    )

    assert activated.ok is True
    assert len(pushed) == 1
    assert replayed.ok is False
    assert cast(dict, replayed.payload["error"])["reason"] == (
        "TASK_PROGRESS_ROUTE_SETTLED"
    )
    assert len(p3.subscription_calls) == 1

    closed = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-sink-close",
        session_id="session-product",
    )
    assert closed.ok is True


@pytest.mark.asyncio
async def test_disconnect_cleanup_closes_p2_and_progress_without_stopping_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2",
        session_id="session-product",
        channel_id="web",
    )
    await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress",
        session_id="session-product",
        channel_id="web",
    )

    await registry.close_active_routes()

    assert manager.unpins == 1
    p2_reconciled = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-p2-disconnect-close-replay",
        session_id="session-product",
    )
    progress_reconciled = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-disconnect-close-replay",
        session_id="session-product",
    )
    assert p2_reconciled.ok is True
    assert progress_reconciled.ok is True
    assert cast(dict, p2_reconciled.payload["result"])["replayed"] is True
    assert cast(dict, progress_reconciled.payload["result"])["replayed"] is True
    assert manager.unpins == 1

    p2_reactivated = await registry.handle_p2_activate(
        params=_p2_params(activation_id="activation-2", activation_generation=2),
        request_id="request-p2-after-disconnect",
        session_id="session-product",
        channel_id="web",
    )
    progress_reactivated = await registry.handle_p3_progress_activate(
        params=_progress_params(generation=2),
        request_id="request-progress-after-disconnect",
        session_id="session-product",
        channel_id="web",
    )
    assert p2_reactivated.ok is True
    assert progress_reactivated.ok is True
    second = await registry.handle_p3_query(
        operation="task.list",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
        },
        request_id="request-after-disconnect",
        session_id="session-product",
    )
    assert second.ok is True
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_progress_close_failure_is_retained_and_exact_retry_succeeds(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, _pushed = _registry(tmp_path)
    p3.subscription_event = False
    p3.subscription_close_failures = 1
    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-retry-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True

    first = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-retry-first",
        session_id="session-product",
    )
    second = await registry.handle_p3_progress_close(
        params=_progress_params(),
        request_id="request-progress-retry-second",
        session_id="session-product",
    )

    assert first.ok is False
    assert cast(dict, first.payload["error"])["reason"] == (
        "PRODUCT_P3_PROGRESS_CLEANUP_PENDING"
    )
    assert second.ok is True
    assert len(p3.authority_calls) == 3


@pytest.mark.asyncio
async def test_registry_stop_remains_retryable_after_cleanup_failure(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, _pushed = _registry(tmp_path)
    p3.subscription_event = False
    p3.subscription_close_failures = 1
    activated = await registry.handle_p3_progress_activate(
        params=_progress_params(),
        request_id="request-progress-stop-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True

    with pytest.raises(RuntimeError, match="cleanup remains pending"):
        await registry.stop()
    await registry.stop()

    rejected = await registry.handle_p3_progress_activate(
        params=_progress_params(generation=2),
        request_id="request-progress-after-stop",
        session_id="session-product",
        channel_id="web",
    )
    assert rejected.ok is False
    assert cast(dict, rejected.payload["error"])["reason"] == (
        "PRODUCT_COMPOSITION_STOPPED"
    )


@pytest.mark.asyncio
async def test_stop_waits_for_inflight_query_before_closing_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, _manager, _pushed = _registry(tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()
    original = registry._p3_adapter.activate_prepared_query

    async def blocked_query(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(
        registry._p3_adapter,
        "activate_prepared_query",
        blocked_query,
    )
    query_task = asyncio.create_task(
        registry.handle_p3_query(
            operation="task.list",
            params={
                "auth_token": "trusted-token",
                "session_id": "session-product",
            },
            request_id="request-blocked-query",
            session_id="session-product",
        )
    )
    await entered.wait()
    stop_task = asyncio.create_task(registry.stop())
    await asyncio.sleep(0)

    assert stop_task.done() is False
    release.set()
    result = await query_task
    await stop_task

    assert result.ok is True


@pytest.mark.asyncio
async def test_activation_queued_before_stop_rechecks_state_before_authority(
    tmp_path: Path,
) -> None:
    registry, p3, manager, _pushed = _registry(tmp_path)
    await registry._lock.acquire()
    activation_task = asyncio.create_task(
        registry.handle_p2_activate(
            params=_p2_params(),
            request_id="request-queued-before-stop",
            session_id="session-product",
            channel_id="web",
        )
    )
    await asyncio.sleep(0)
    stop_task = asyncio.create_task(registry.stop())
    await asyncio.sleep(0)
    registry._lock.release()

    result = await activation_task
    await stop_task

    assert result.ok is False
    assert cast(dict, result.payload["error"])["reason"] == (
        "PRODUCT_COMPOSITION_STOPPED"
    )
    assert p3.authority_calls == []
    assert manager.get_calls == []


@pytest.mark.asyncio
async def test_segment_flags_fail_before_authority_or_downstream(
    tmp_path: Path,
) -> None:
    registry, p3, manager, pushed = _registry(tmp_path, p2=False, p3=False)

    p2 = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-off",
        session_id="session-product",
        channel_id="web",
    )
    query = await registry.handle_p3_query(
        operation="task.list",
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
        },
        request_id="request-p3-off",
        session_id="session-product",
    )
    progress_ack = await registry.handle_p3_progress_ack(
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "task_id": "task-1",
            "correlation_id": "correlation-task-1",
            "origin_id": "web-surface",
            "generation_id": "web-generation",
            "generation": 1,
            "delivery_id": "delivery-1",
            "source_event_id": "event-1",
            "progress_event_id": "progress-1",
            "seq": 1,
            "evidence_id": "evidence-1",
        },
        request_id="request-p3-ack-off",
        session_id="session-product",
        channel_id="web",
    )

    assert p2.ok is False
    assert query.ok is False
    assert progress_ack.ok is False
    assert p3.authority_calls == []
    assert p3.query_calls == []
    assert p3.subscription_calls == []
    assert manager.get_calls == []
    assert pushed == []


@pytest.mark.asyncio
async def test_p2_text_submit_notification_and_exact_presentation_ack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    history = _HistoryWriter()
    route.activation_lease._runtime._history_writer = history
    submit_params = _p2_params(
        commit_id="commit-1",
        turn_id="turn-1",
        response_id="response-1",
        committed_at=NOW,
        text="hello product agent",
    )

    wrong_generation = await registry.handle_p2_submit(
        params={**submit_params, "activation_generation": 2},
        request_id="request-submit-wrong-generation",
        session_id="session-product",
        channel_id="web",
    )
    submitted = await registry.handle_p2_submit(
        params=submit_params,
        request_id="request-submit-1",
        session_id="session-product",
        channel_id="web",
    )
    replayed = await registry.handle_p2_submit(
        params=submit_params,
        request_id="request-submit-1",
        session_id="session-product",
        channel_id="web",
    )

    assert wrong_generation.ok is False
    assert cast(dict, wrong_generation.payload["error"])["reason"] == (
        "ACTIVATION_BINDING_MISMATCH"
    )
    assert submitted.ok is True
    assert replayed.payload == submitted.payload
    assert manager.agent.calls == 1
    presentation: dict[str, object] | None = None
    response: dict[str, object] | None = None
    presentation_notification_request_id: str | None = None
    for index in range(4):
        notification_request_id = f"request-notification-{index}"
        polled = await asyncio.wait_for(
            registry.handle_p2_notification_next(
                params=_p2_params(notification_sequence=index + 1),
                request_id=notification_request_id,
                session_id="session-product",
            ),
            timeout=1,
        )
        assert polled.ok is True
        notification = cast(dict[str, object], polled.payload["result"])
        candidate = notification["presentation_unit"]
        if isinstance(candidate, dict):
            presentation = cast(dict[str, object], candidate)
            response = cast(dict[str, object], notification["response"])
            presentation_notification_request_id = notification_request_id
            break
    assert presentation is not None
    assert response is not None
    assert presentation_notification_request_id is not None

    ack_params = _p2_params(
        response_id=response["response_id"],
        response_generation=response["response_generation"],
        surface=presentation["surface"],
        unit_id=presentation["unit_id"],
        contiguous_cursor=presentation["seq"],
        presented_at=NOW,
    )
    await asyncio.sleep(0)
    runtime_before_rejection = route.activation_lease._runtime.snapshot()
    rejected_ack_params = {
        **ack_params,
        "contiguous_cursor": MAX_SAFE_INTEGER,
    }
    rejected = await registry.handle_p2_presentation_ack(
        params=rejected_ack_params,
        request_id="request-ack-beyond-produced",
        session_id="session-product",
    )
    rejected_replay = await registry.handle_p2_presentation_ack(
        params=rejected_ack_params,
        request_id="request-ack-beyond-produced",
        session_id="session-product",
    )

    assert rejected.ok is False
    assert rejected_replay.payload == rejected.payload
    assert cast(dict, rejected.payload["error"])["code"] == "PROTOCOL_VIOLATION"
    assert cast(dict, rejected.payload["error"])["reason"] == (
        "ACK_BEYOND_PRODUCED_CURSOR"
    )
    assert route.activation_lease._runtime.snapshot() == runtime_before_rejection
    assert history.assistants == []
    assert tuple(registry._p2_ack_operations) == ("request-ack-beyond-produced",)

    acknowledged = await registry.handle_p2_presentation_ack(
        params=ack_params,
        request_id="request-ack-1",
        session_id="session-product",
    )
    ack_replay = await registry.handle_p2_presentation_ack(
        params=ack_params,
        request_id="request-ack-1",
        session_id="session-product",
    )

    assert acknowledged.ok is True
    assert ack_replay.payload == acknowledged.payload
    assert cast(dict, acknowledged.payload["result"])["accepted"] is True
    assert len(history.assistants) == 1
    second_submit = await registry.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-2",
            turn_id="turn-2",
            response_id="response-2",
            committed_at="2030-01-01T00:00:01Z",
            text="use the previous answer",
        ),
        request_id="request-submit-2",
        session_id="session-product",
        channel_id="web",
    )
    assert second_submit.ok is True
    await asyncio.wait_for(manager.agent.wait_for_calls(2), timeout=1)
    assert manager.agent.calls == 2
    second_execution = manager.agent.executions[1]
    assert [entry.content for entry in second_execution.context.entries] == [
        "hello product agent",
        "formal result",
    ]
    assert second_execution.commit.context_refs == tuple(
        entry.ref for entry in second_execution.context.entries
    )
    assert json.loads(second_execution.prompt_content())["selected_context"] == [
        {
            "context_ref": entry.ref.to_dict(),
            "content": entry.content,
        }
        for entry in second_execution.context.entries
    ]
    task_origin = await registry.handle_p2_submit(
        params=_p2_task_origin_params(
            stem="task-with-acknowledged-agent-context",
            text="create a task without Agent context",
        ),
        request_id="request-task-with-acknowledged-agent-context",
        session_id="session-product",
        channel_id="web",
    )
    assert task_origin.ok is True
    assert manager.agent.calls == 2
    task_commit = registry._accepted_turn_commits_by_commit[
        "commit-task-with-acknowledged-agent-context"
    ]
    assert task_commit.context_refs == ()
    await registry.close_active_routes()
    submit_after_disconnect = await registry.handle_p2_submit(
        params=submit_params,
        request_id="request-submit-1",
        session_id="session-product",
        channel_id="web",
    )
    notification_after_disconnect = await registry.handle_p2_notification_next(
        params=_p2_params(
            notification_sequence=int(
                presentation_notification_request_id.rpartition("-")[2]
            )
            + 1
        ),
        request_id=presentation_notification_request_id,
        session_id="session-product",
    )
    ack_after_disconnect = await registry.handle_p2_presentation_ack(
        params=ack_params,
        request_id="request-ack-1",
        session_id="session-product",
    )
    submit_conflict_after_disconnect = await registry.handle_p2_submit(
        params={**submit_params, "commit_id": "commit-conflict"},
        request_id="request-submit-1",
        session_id="session-product",
        channel_id="web",
    )
    new_submit_after_disconnect = await registry.handle_p2_submit(
        params={**submit_params, "commit_id": "commit-new"},
        request_id="request-submit-new",
        session_id="session-product",
        channel_id="web",
    )

    assert submit_after_disconnect.payload == submitted.payload
    assert notification_after_disconnect.payload == polled.payload
    assert ack_after_disconnect.payload == acknowledged.payload
    assert submit_conflict_after_disconnect.ok is False
    assert (
        cast(dict, submit_conflict_after_disconnect.payload["error"])["reason"]
        == "PRODUCT_REQUEST_ID_CONFLICT"
    )
    assert new_submit_after_disconnect.ok is False
    assert cast(dict, new_submit_after_disconnect.payload["error"])["reason"] == (
        "PRODUCT_P2_ROUTE_NOT_FOUND"
    )
    assert manager.agent.calls == 2
    assert len(history.assistants) == 1


@pytest.mark.asyncio
async def test_p2_context_excludes_unacknowledged_agent_output(tmp_path: Path) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-activate-unacked-context",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    history = _HistoryWriter()
    route.activation_lease._runtime._history_writer = history

    first = await registry.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-unacked-1",
            turn_id="turn-unacked-1",
            response_id="response-unacked-1",
            committed_at=NOW,
            text="unacknowledged user turn",
        ),
        request_id="request-submit-unacked-1",
        session_id="session-product",
        channel_id="web",
    )
    assert first.ok is True
    presentation = None
    for sequence in range(1, 5):
        polled = await asyncio.wait_for(
            registry.handle_p2_notification_next(
                params=_p2_params(notification_sequence=sequence),
                request_id=f"request-unacked-context-notification-{sequence}",
                session_id="session-product",
            ),
            timeout=1,
        )
        assert polled.ok is True
        notification = cast(dict[str, object], polled.payload["result"])
        if isinstance(notification["presentation_unit"], dict):
            presentation = cast(dict[str, object], notification["presentation_unit"])
            break
    assert presentation is not None
    assert manager.agent.calls == 1
    assert history.assistants == []

    second = await registry.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-unacked-2",
            turn_id="turn-unacked-2",
            response_id="response-unacked-2",
            committed_at="2030-01-01T00:00:01Z",
            text="must not see the first output",
        ),
        request_id="request-submit-unacked-2",
        session_id="session-product",
        channel_id="web",
    )
    assert second.ok is True
    await asyncio.wait_for(manager.agent.wait_for_calls(2), timeout=1)
    assert manager.agent.calls == 2
    assert manager.agent.executions[1].context.entries == ()
    assert manager.agent.executions[1].commit.context_refs == ()
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_ack_and_next_submit_linearize_one_complete_context_snapshot(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-activate-ack-submit-race",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    history = _BlockingHistoryWriter()
    route.activation_lease._runtime._history_writer = history
    first = await registry.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-ack-submit-race-1",
            turn_id="turn-ack-submit-race-1",
            response_id="response-ack-submit-race-1",
            committed_at=NOW,
            text="context becomes visible atomically",
        ),
        request_id="request-ack-submit-race-1",
        session_id="session-product",
        channel_id="web",
    )
    assert first.ok is True
    presentation = None
    response = None
    for sequence in range(1, 5):
        polled = await asyncio.wait_for(
            registry.handle_p2_notification_next(
                params=_p2_params(notification_sequence=sequence),
                request_id=f"request-ack-submit-race-notification-{sequence}",
                session_id="session-product",
            ),
            timeout=1,
        )
        assert polled.ok is True
        notification = cast(dict[str, object], polled.payload["result"])
        if isinstance(notification["presentation_unit"], dict):
            presentation = cast(dict[str, object], notification["presentation_unit"])
            response = cast(dict[str, object], notification["response"])
            break
    assert presentation is not None
    assert response is not None

    ack_task = asyncio.create_task(
        registry.handle_p2_presentation_ack(
            params=_p2_params(
                response_id=response["response_id"],
                response_generation=response["response_generation"],
                surface=presentation["surface"],
                unit_id=presentation["unit_id"],
                contiguous_cursor=presentation["seq"],
                presented_at=NOW,
            ),
            request_id="request-ack-submit-race-ack",
            session_id="session-product",
        )
    )
    await asyncio.wait_for(history.assistant_started.wait(), timeout=1)
    submit_task = asyncio.create_task(
        registry.handle_p2_submit(
            params=_p2_params(
                commit_id="commit-ack-submit-race-2",
                turn_id="turn-ack-submit-race-2",
                response_id="response-ack-submit-race-2",
                committed_at="2030-01-01T00:00:01Z",
                text="read only the complete prior pair",
            ),
            request_id="request-ack-submit-race-2",
            session_id="session-product",
            channel_id="web",
        )
    )
    await asyncio.sleep(0)
    assert manager.agent.calls == 1

    history.assistant_release.set()
    acknowledged, submitted = await asyncio.gather(ack_task, submit_task)
    assert acknowledged.ok is True
    assert submitted.ok is True
    await asyncio.wait_for(manager.agent.wait_for_calls(2), timeout=1)
    assert manager.agent.calls == 2
    assert [entry.content for entry in manager.agent.executions[1].context.entries] == [
        "context becomes visible atomically",
        "formal result",
    ]
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_close_fences_a_concurrent_next_submit_before_agent_effect(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-activate-close-submit-race",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    await route.activation_lease._operation_lock.acquire()
    close_task = asyncio.create_task(
        route.activation_lease.close(route.binding, timeout_seconds=1)
    )
    for _ in range(20):
        if route.activation_lease.snapshot().state.value == "closing":
            break
        await asyncio.sleep(0)
    assert route.activation_lease.snapshot().state.value == "closing"
    submit_task = asyncio.create_task(
        registry.handle_p2_submit(
            params=_p2_params(
                commit_id="commit-close-submit-race",
                turn_id="turn-close-submit-race",
                response_id="response-close-submit-race",
                committed_at=NOW,
                text="must never reach the Agent",
            ),
            request_id="request-close-submit-race",
            session_id="session-product",
            channel_id="web",
        )
    )
    await asyncio.sleep(0)
    assert manager.agent.calls == 0
    route.activation_lease._operation_lock.release()

    closed, submitted = await asyncio.gather(close_task, submit_task)
    assert closed.status.value == "closed"
    assert submitted.ok is False
    assert cast(dict, submitted.payload["error"])["reason"] == (
        "ACTIVATION_LEASE_NOT_OPEN"
    )
    assert manager.agent.calls == 0
    assert registry._p2_submit_operations == {}
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_context_keeps_only_four_latest_acknowledged_pairs(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-activate-context-bound",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    notification_sequence = 0

    for index in range(5):
        submitted = await registry.handle_p2_submit(
            params=_p2_params(
                commit_id=f"commit-context-{index}",
                turn_id=f"turn-context-{index}",
                response_id=f"response-context-{index}",
                committed_at=f"2030-01-01T00:00:0{index}Z",
                text=f"user context {index}",
            ),
            request_id=f"request-submit-context-{index}",
            session_id="session-product",
            channel_id="web",
        )
        assert submitted.ok is True
        presentation = None
        response = None
        for _ in range(4):
            notification_sequence += 1
            polled = await asyncio.wait_for(
                registry.handle_p2_notification_next(
                    params=_p2_params(notification_sequence=notification_sequence),
                    request_id=f"request-context-notification-{notification_sequence}",
                    session_id="session-product",
                ),
                timeout=1,
            )
            assert polled.ok is True
            notification = cast(dict[str, object], polled.payload["result"])
            candidate = notification["presentation_unit"]
            if isinstance(candidate, dict):
                presentation = cast(dict[str, object], candidate)
                response = cast(dict[str, object], notification["response"])
                break
        assert presentation is not None
        assert response is not None
        acknowledged = await registry.handle_p2_presentation_ack(
            params=_p2_params(
                response_id=response["response_id"],
                response_generation=response["response_generation"],
                surface=presentation["surface"],
                unit_id=presentation["unit_id"],
                contiguous_cursor=presentation["seq"],
                presented_at=f"2030-01-01T00:01:0{index}Z",
            ),
            request_id=f"request-context-ack-{index}",
            session_id="session-product",
        )
        assert acknowledged.ok is True

    final = await registry.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-context-final",
            turn_id="turn-context-final",
            response_id="response-context-final",
            committed_at="2030-01-01T00:00:10Z",
            text="use bounded context",
        ),
        request_id="request-submit-context-final",
        session_id="session-product",
        channel_id="web",
    )
    assert final.ok is True
    await asyncio.wait_for(manager.agent.wait_for_calls(6), timeout=1)
    assert manager.agent.calls == 6
    assert [
        entry.content for entry in manager.agent.executions[-1].context.entries
    ] == [
        "user context 1",
        "formal result",
        "user context 2",
        "formal result",
        "user context 3",
        "formal result",
        "user context 4",
        "formal result",
    ]
    assistant_refs = manager.agent.executions[-1].context.entries[1::2]
    assert len({entry.ref.stable_id for entry in assistant_refs}) == 4
    assert len({entry.ref.uri for entry in assistant_refs}) == 4
    assert len({entry.ref.revision.value for entry in assistant_refs}) == 1
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_accepts_voice_origin_only_after_exact_success(tmp_path: Path) -> None:
    ledger = TurnCommitLedger()
    registry, _p3, manager, _pushed = _registry(tmp_path, commit_ledger=ledger)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-voice-origin",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    rejected = await registry.handle_p2_submit(
        params=_p2_params(
            activation_generation=2,
            commit_id="commit-rejected",
            turn_id="turn-rejected",
            response_id="response-rejected",
            committed_at=NOW,
            text="must never acquire task authority",
        ),
        request_id="request-submit-rejected-origin",
        session_id="session-product",
        channel_id="web",
    )
    assert rejected.ok is False
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef("committed_turn", "turn-rejected", "commit-rejected"),
            SCOPE,
        )

    voice_text = "create the bounded voice task"
    voice_origin_params = _p2_task_origin_params(stem="voice-origin", text=voice_text)
    submitted = await registry.handle_p2_submit(
        params=voice_origin_params,
        request_id="request-submit-voice-origin",
        session_id="session-product",
        channel_id="web",
    )
    assert submitted.ok is True
    assert cast(dict, submitted.payload["result"])["status"] == ("task_origin_accepted")
    response = cast(dict, submitted.payload["result"])["response"]
    assert response["interaction_id"] == "interaction-1"
    assert cast(str, response["response_id"]).strip()
    assert response["response_generation"] == 0
    runtime = registry._p2_routes[
        ("session-product", "interaction-1")
    ].activation_lease._runtime
    response_records = runtime.snapshot().conversation.conversation.responses
    canonical = next(
        item
        for item in response_records
        if item.ref.response_id == response["response_id"]
    )
    assert canonical.ref.response_generation == response["response_generation"]
    assert canonical.state.value == "terminal"
    assert canonical.outcome.value == "completed"
    replayed = await registry.handle_p2_submit(
        params=voice_origin_params,
        request_id="request-submit-voice-origin",
        session_id="session-product",
        channel_id="web",
    )
    assert replayed.payload == submitted.payload
    assert (
        sum(
            item.ref.response_id == response["response_id"]
            for item in runtime.snapshot().conversation.conversation.responses
        )
        == 1
    )
    accepted = ledger.require_origin(
        OriginRef("committed_turn", "turn-voice-origin", "commit-voice-origin"),
        SCOPE,
    )
    assert accepted.text == voice_text
    assert manager.agent.calls == 0

    agent_params = _p2_params(
        commit_id="commit-agent-chat",
        turn_id="turn-agent-chat",
        response_id="response-agent-chat",
        committed_at=NOW,
        text="answer this ordinary voice chat",
        dispatch_target="agent",
    )
    ordinary = await registry.handle_p2_submit(
        params=agent_params,
        request_id="request-submit-agent-chat",
        session_id="session-product",
        channel_id="web",
    )
    assert ordinary.ok is True
    ordinary_result = cast(dict[str, object], ordinary.payload["result"])
    assert ordinary_result["turn_id"] == "turn-agent-chat"
    assert ordinary_result["commit_id"] == "commit-agent-chat"
    ordinary_replay = await registry.handle_p2_submit(
        params=agent_params,
        request_id="request-submit-agent-chat",
        session_id="session-product",
        channel_id="web",
    )
    assert ordinary_replay.payload == ordinary.payload
    assert manager.agent.calls == 1
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef("committed_turn", "turn-agent-chat", "commit-agent-chat"),
            SCOPE,
        )
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_response_generation_continues_across_activation_successor(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    first_binding = _p2_params()
    first_activation = await registry.handle_p2_activate(
        params=first_binding,
        request_id="request-response-generation-activate-1",
        session_id="session-product",
        channel_id="web",
    )
    assert first_activation.ok is True
    first_submit = await registry.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-response-generation-1",
            turn_id="turn-response-generation-1",
            response_id="response-generation-1",
            committed_at=NOW,
            text="first activation response",
            dispatch_target="agent",
        ),
        request_id="request-response-generation-submit-1",
        session_id="session-product",
        channel_id="web",
    )
    assert first_submit.ok is True
    first_response = cast(dict, first_submit.payload["result"])["response"]
    assert first_response["response_generation"] == 0

    first_close = await registry.handle_p2_close(
        params=first_binding,
        request_id="request-response-generation-close-1",
        session_id="session-product",
    )
    assert first_close.ok is True

    successor_binding = _p2_params(
        activation_id="activation-2",
        activation_generation=2,
    )
    successor_activation = await registry.handle_p2_activate(
        params=successor_binding,
        request_id="request-response-generation-activate-2",
        session_id="session-product",
        channel_id="web",
    )
    assert successor_activation.ok is True
    successor_submit_params = {
        **successor_binding,
        "commit_id": "commit-response-generation-2",
        "turn_id": "turn-response-generation-2",
        "response_id": "response-generation-2",
        "committed_at": NOW,
        "text": "successor activation response",
        "dispatch_target": "agent",
    }
    successor_submit = await registry.handle_p2_submit(
        params=successor_submit_params,
        request_id="request-response-generation-submit-2",
        session_id="session-product",
        channel_id="web",
    )
    assert successor_submit.ok is True
    successor_response = cast(dict, successor_submit.payload["result"])["response"]
    assert successor_response["response_generation"] == 1

    replayed = await registry.handle_p2_submit(
        params=successor_submit_params,
        request_id="request-response-generation-submit-2",
        session_id="session-product",
        channel_id="web",
    )
    assert replayed.payload == successor_submit.payload
    assert manager.agent.calls == 2
    assert registry._p2_response_generations[("session-product", "interaction-1")] == 1
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_response_generation_continues_across_registry_restart(
    tmp_path: Path,
) -> None:
    generation_database = tmp_path / "durable-response-generations.sqlite3"
    first, first_p3, _manager, _pushed = _registry(tmp_path)
    first_p3._p2_response_generation_owner = SqliteP2ResponseGenerationOwner(
        generation_database
    )
    first_binding = _p2_params()
    assert (
        await first.handle_p2_activate(
            params=first_binding,
            request_id="request-restart-generation-activate-1",
            session_id="session-product",
            channel_id="web",
        )
    ).ok is True
    first_submit = await first.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-restart-generation-1",
            turn_id="turn-restart-generation-1",
            response_id="response-restart-generation-1",
            committed_at=NOW,
            text="response before restart",
            dispatch_target="agent",
        ),
        request_id="request-restart-generation-submit-1",
        session_id="session-product",
        channel_id="web",
    )
    assert first_submit.ok is True
    assert (
        cast(dict, first_submit.payload["result"])["response"]["response_generation"]
        == 0
    )
    await first.close_active_routes()

    restarted, restarted_p3, _manager, _pushed = _registry(tmp_path)
    restarted_p3._p2_response_generation_owner = SqliteP2ResponseGenerationOwner(
        generation_database
    )
    successor_binding = _p2_params(
        activation_id="activation-after-restart",
        activation_generation=2,
    )
    assert (
        await restarted.handle_p2_activate(
            params=successor_binding,
            request_id="request-restart-generation-activate-2",
            session_id="session-product",
            channel_id="web",
        )
    ).ok is True
    successor = await restarted.handle_p2_submit(
        params={
            **successor_binding,
            "commit_id": "commit-restart-generation-2",
            "turn_id": "turn-restart-generation-2",
            "response_id": "response-restart-generation-2",
            "committed_at": NOW,
            "text": "response after restart",
            "dispatch_target": "agent",
        },
        request_id="request-restart-generation-submit-2",
        session_id="session-product",
        channel_id="web",
    )
    assert successor.ok is True
    assert (
        cast(dict, successor.payload["result"])["response"]["response_generation"] == 1
    )
    await restarted.close_active_routes()


def test_durable_p2_response_generation_owner_keeps_memory_exact_set_bounded(
    tmp_path: Path,
) -> None:
    registry, p3, _manager, _pushed = _registry(tmp_path)
    p3._p2_response_generation_owner = SqliteP2ResponseGenerationOwner(
        tmp_path / "bounded-durable-response-generations.sqlite3"
    )
    first_key = ("session-product", "interaction-durable-0")
    assert registry._next_p2_response_generation(first_key, -1) == 0
    for index in range(1, registry._P2_RESPONSE_GENERATION_CAPACITY + 1):
        registry._next_p2_response_generation(
            ("session-product", f"interaction-durable-{index}"),
            -1,
        )

    assert len(registry._p2_response_generations) == (
        registry._P2_RESPONSE_GENERATION_CAPACITY
    )
    assert first_key not in registry._p2_response_generations
    assert registry._next_p2_response_generation(first_key, -1) >= 1


def test_p2_response_generation_fence_survives_exact_high_water_eviction(
    tmp_path: Path,
) -> None:
    registry, _p3, _manager, _pushed = _registry(tmp_path)
    first_key = ("session-product", "interaction-generation-0")
    assert registry._next_p2_response_generation(first_key, -1) == 0
    for index in range(1, registry._P2_RESPONSE_GENERATION_CAPACITY + 1):
        assert (
            registry._next_p2_response_generation(
                ("session-product", f"interaction-generation-{index}"), -1
            )
            == 0
        )

    assert first_key not in registry._p2_response_generations
    assert registry._next_p2_response_generation(first_key, -1) >= 1


def test_p2_response_generation_owner_serializes_concurrent_allocations(
    tmp_path: Path,
) -> None:
    registry, _p3, _manager, _pushed = _registry(tmp_path)
    key = ("session-product", "interaction-concurrent-generation")
    worker_count = 32
    barrier = threading.Barrier(worker_count)

    def allocate() -> int:
        barrier.wait(timeout=5)
        return registry._next_p2_response_generation(key, -1)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        generations = list(executor.map(lambda _index: allocate(), range(worker_count)))

    assert sorted(generations) == list(range(worker_count))
    assert registry._p2_response_generations[key] == worker_count - 1


def test_p2_response_generation_exhaustion_preserves_owner_state(
    tmp_path: Path,
) -> None:
    registry, _p3, _manager, _pushed = _registry(tmp_path)
    key = ("session-product", "interaction-exhausted-generation")
    registry._p2_response_generations[key] = MAX_SAFE_INTEGER
    exact_before = dict(registry._p2_response_generations)
    fence_before = tuple(
        row.tobytes() for row in registry._p2_response_generation_fence
    )

    with pytest.raises(FormalTaskViolation, match="generation is exhausted") as caught:
        registry._next_p2_response_generation(key, MAX_SAFE_INTEGER - 1)

    assert caught.value.reason == "RESPONSE_GENERATION_EXHAUSTED"
    assert registry._p2_response_generations == exact_before
    assert (
        tuple(row.tobytes() for row in registry._p2_response_generation_fence)
        == fence_before
    )


@pytest.mark.asyncio
async def test_p2_task_origin_caller_cancellation_retains_exact_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = TurnCommitLedger()
    registry, _p3, manager, _pushed = _registry(tmp_path, commit_ledger=ledger)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-task-origin-cancel",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    original_accept = route.activation_lease.accept_task_origin
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked_accept(*args: object, **kwargs: object):
        entered.set()
        await release.wait()
        return await original_accept(*args, **kwargs)

    monkeypatch.setattr(route.activation_lease, "accept_task_origin", blocked_accept)
    text = "retain the exact voice task origin"
    params = _p2_task_origin_params(stem="task-origin-cancel", text=text)
    caller = asyncio.create_task(
        registry.handle_p2_submit(
            params=params,
            request_id="request-submit-task-origin-cancel",
            session_id="session-product",
            channel_id="web",
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    release.set()
    retained = registry._p2_submit_operations["request-submit-task-origin-cancel"]
    first = await asyncio.wait_for(asyncio.shield(retained.task), timeout=1)
    replayed = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-cancel",
        session_id="session-product",
        channel_id="web",
    )

    assert first.ok is True
    assert replayed.payload == first.payload
    assert manager.agent.calls == 0
    assert (
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-task-origin-cancel",
                "commit-task-origin-cancel",
            ),
            SCOPE,
        ).text
        == text
    )
    runtime = route.activation_lease._runtime
    response_id = cast(dict, first.payload["result"])["response"]["response_id"]
    assert (
        sum(
            item.ref.response_id == response_id
            for item in runtime.snapshot().conversation.conversation.responses
        )
        == 1
    )
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_task_origin_canonical_accept_wins_concurrent_route_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = TurnCommitLedger()
    registry, _p3, manager, _pushed = _registry(tmp_path, commit_ledger=ledger)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-task-origin-close-race",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    runtime = route.activation_lease._runtime
    original_accept = runtime.accept_task_origin
    canonical_accepted = asyncio.Event()
    release = asyncio.Event()

    async def blocked_after_canonical_accept(**kwargs: object):
        response_ref = await original_accept(**kwargs)
        canonical_accepted.set()
        await release.wait()
        return response_ref

    monkeypatch.setattr(runtime, "accept_task_origin", blocked_after_canonical_accept)
    text = "canonical acceptance must win the close race"
    params = _p2_task_origin_params(stem="task-origin-close-race", text=text)
    submit = asyncio.create_task(
        registry.handle_p2_submit(
            params=params,
            request_id="request-submit-task-origin-close-race",
            session_id="session-product",
            channel_id="web",
        )
    )
    await asyncio.wait_for(canonical_accepted.wait(), timeout=1)
    close = asyncio.create_task(
        registry.handle_p2_close(
            params=_p2_params(),
            request_id="request-close-task-origin-close-race",
            session_id="session-product",
        )
    )

    async def wait_for_closing() -> None:
        while route.activation_lease.snapshot().state.value != "closing":
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_closing(), timeout=1)
    release.set()
    submitted, closed = await asyncio.gather(submit, close)
    replayed = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-close-race",
        session_id="session-product",
        channel_id="web",
    )

    assert submitted.ok is True
    assert cast(dict, submitted.payload["result"])["status"] == ("task_origin_accepted")
    assert closed.ok is True
    assert replayed.payload == submitted.payload
    assert manager.agent.calls == 0
    assert "commit-task-origin-close-race" in (
        registry._accepted_turn_commits_by_commit
    )
    assert (
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-task-origin-close-race",
                "commit-task-origin-close-race",
            ),
            SCOPE,
        ).text
        == text
    )


@pytest.mark.asyncio
async def test_closed_p2_voice_origin_is_consumed_once_by_exact_p3_create(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    registry, composition, _owner = _voice_mutation_registry(
        tmp_path,
        commit_ledger=ledger,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-closed-origin",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    text = "create exactly one task after the P2 route closes"
    origin_params = _p2_task_origin_params(stem="closed-origin", text=text)
    accepted = await registry.handle_p2_submit(
        params=origin_params,
        request_id="request-submit-closed-origin",
        session_id="session-product",
        channel_id="web",
    )
    closed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-close-closed-origin",
        session_id="session-product",
    )
    replayed_origin = await registry.handle_p2_submit(
        params=origin_params,
        request_id="request-submit-closed-origin",
        session_id="session-product",
        channel_id="web",
    )
    create = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "operation": "task.create",
        "command_id": "command-create-closed-origin",
        "issued_at": NOW,
        "correlation_id": "correlation-create-closed-origin",
        "name": "Closed origin task",
        "instruction": text,
        "source": "voice",
        "interaction_id": "interaction-1",
        "turn_id": "turn-closed-origin",
        "commit_id": "commit-closed-origin",
    }
    issued = await registry.handle_p3_confirmation_issue(
        params=create,
        request_id="request-issue-closed-origin",
        session_id="session-product",
    )
    assert accepted.ok is True
    assert closed.ok is True
    assert replayed_origin.payload == accepted.payload
    assert issued.ok is True
    receipt = cast(dict[str, object], issued.payload["result"])
    mutation = {**create, "confirmation_id": receipt["confirmation_id"]}
    created = await registry.handle_p3_mutation(
        params=mutation,
        request_id="request-mutate-closed-origin",
        session_id="session-product",
    )
    replayed_create = await registry.handle_p3_mutation(
        params=mutation,
        request_id="request-mutate-closed-origin",
        session_id="session-product",
    )
    duplicate = await registry.handle_p3_confirmation_issue(
        params={**create, "command_id": "command-create-closed-origin-duplicate"},
        request_id="request-issue-closed-origin-duplicate",
        session_id="session-product",
    )
    foreign = await registry.handle_p3_confirmation_issue(
        params={
            **create,
            "command_id": "command-create-closed-origin-foreign",
            "interaction_id": "interaction-foreign",
        },
        request_id="request-issue-closed-origin-foreign",
        session_id="session-product",
    )

    assert created.ok is True
    assert replayed_create.payload == created.payload
    assert duplicate.ok is False
    assert foreign.ok is False
    assert len(composition.mutation_calls) == 1
    await registry.stop()
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-closed-origin",
                "commit-closed-origin",
            ),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_concurrent_p3_creates_reserve_one_exact_voice_origin(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    registry, composition, _owner = _voice_mutation_registry(
        tmp_path,
        commit_ledger=ledger,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-concurrent-create",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    text = "create one task despite concurrent requests"
    accepted = await registry.handle_p2_submit(
        params=_p2_task_origin_params(stem="concurrent-create", text=text),
        request_id="request-submit-concurrent-create",
        session_id="session-product",
        channel_id="web",
    )
    assert accepted.ok is True
    create = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "operation": "task.create",
        "issued_at": NOW,
        "correlation_id": "correlation-concurrent-create",
        "name": "Concurrent origin task",
        "instruction": text,
        "source": "voice",
        "interaction_id": "interaction-1",
        "turn_id": "turn-concurrent-create",
        "commit_id": "commit-concurrent-create",
    }
    first_issue = await registry.handle_p3_confirmation_issue(
        params={**create, "command_id": "command-concurrent-create-a"},
        request_id="request-issue-concurrent-create-a",
        session_id="session-product",
    )
    second_issue = await registry.handle_p3_confirmation_issue(
        params={**create, "command_id": "command-concurrent-create-b"},
        request_id="request-issue-concurrent-create-b",
        session_id="session-product",
    )
    assert first_issue.ok is True
    assert second_issue.ok is True
    first_receipt = cast(dict[str, object], first_issue.payload["result"])
    second_receipt = cast(dict[str, object], second_issue.payload["result"])

    first, second = await asyncio.gather(
        registry.handle_p3_mutation(
            params={
                **create,
                "command_id": "command-concurrent-create-a",
                "confirmation_id": first_receipt["confirmation_id"],
            },
            request_id="request-mutate-concurrent-create-a",
            session_id="session-product",
        ),
        registry.handle_p3_mutation(
            params={
                **create,
                "command_id": "command-concurrent-create-b",
                "confirmation_id": second_receipt["confirmation_id"],
            },
            request_id="request-mutate-concurrent-create-b",
            session_id="session-product",
        ),
    )

    assert sum(result.ok for result in (first, second)) == 1
    assert len(composition.mutation_calls) == 1
    rejected = second if first.ok else first
    assert cast(dict, rejected.payload["error"])["code"] == (
        ErrorCode.PERMISSION_DENIED.value
    )
    await registry.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_mode", ["failed", "cancelled"])
async def test_failed_voice_create_eviction_retires_exact_reserved_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal_mode: str,
) -> None:
    ledger = TurnCommitLedger(capacity=1)
    registry, composition, _owner = _voice_mutation_registry(
        tmp_path,
        commit_ledger=ledger,
    )
    monkeypatch.setattr(registry, "_TURN_COMMIT_CAPACITY", 1)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id=f"request-activate-create-{terminal_mode}",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    text = f"retire {terminal_mode} voice create without leaking capacity"
    origin = await registry.handle_p2_submit(
        params=_p2_task_origin_params(stem=f"create-{terminal_mode}", text=text),
        request_id=f"request-submit-create-{terminal_mode}",
        session_id="session-product",
        channel_id="web",
    )
    assert origin.ok is True
    create = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "operation": "task.create",
        "command_id": f"command-create-{terminal_mode}",
        "issued_at": NOW,
        "correlation_id": f"correlation-create-{terminal_mode}",
        "name": f"{terminal_mode} task",
        "instruction": text,
        "source": "voice",
        "interaction_id": "interaction-1",
        "turn_id": f"turn-create-{terminal_mode}",
        "commit_id": f"commit-create-{terminal_mode}",
    }
    issued = await registry.handle_p3_confirmation_issue(
        params=create,
        request_id=f"request-issue-create-{terminal_mode}",
        session_id="session-product",
    )
    assert issued.ok is True
    receipt = cast(dict[str, object], issued.payload["result"])
    mutation_request_id = f"request-mutate-create-{terminal_mode}"

    async def terminal_handle(**_kwargs: object) -> P3RouteResult:
        if terminal_mode == "cancelled":
            raise asyncio.CancelledError
        return P3RouteResult(
            False,
            {
                "request_id": mutation_request_id,
                "ok": False,
                "result": None,
                "error": {
                    "code": ErrorCode.UNAVAILABLE.value,
                    "reason": "INJECTED_CREATE_FAILURE",
                    "message": "injected create failure",
                },
            },
        )

    monkeypatch.setattr(composition, "handle", terminal_handle)
    mutation = registry.handle_p3_mutation(
        params={**create, "confirmation_id": receipt["confirmation_id"]},
        request_id=mutation_request_id,
        session_id="session-product",
    )
    if terminal_mode == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await mutation
    else:
        failed = await mutation
        assert failed.ok is False

    assert (
        registry._reserved_voice_origin_requests[f"commit-create-{terminal_mode}"]
        == mutation_request_id
    )
    async with registry._lock:
        assert (
            registry._evict_completed_product_operation(
                registry._p3_mutation_operations,
                namespace="p3.mutate",
            )
            is True
        )

    assert registry._reserved_voice_origin_requests == {}
    assert registry._accepted_turn_commits_by_commit == {}
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                f"turn-create-{terminal_mode}",
                f"commit-create-{terminal_mode}",
            ),
            SCOPE,
        )
    retired = await registry.handle_p2_submit(
        params=_p2_task_origin_params(stem=f"create-{terminal_mode}", text=text),
        request_id=f"request-submit-create-{terminal_mode}-duplicate",
        session_id="session-product",
        channel_id="web",
    )
    assert retired.ok is False
    assert cast(dict, retired.payload["error"])["reason"] == "TURN_COMMIT_RETIRED"

    fresh = await registry.handle_p2_submit(
        params=_p2_task_origin_params(
            stem=f"create-{terminal_mode}-fresh",
            text="fresh voice origin proves bounded capacity was released",
        ),
        request_id=f"request-submit-create-{terminal_mode}-fresh",
        session_id="session-product",
        channel_id="web",
    )
    assert fresh.ok is True
    await registry.stop()


@pytest.mark.asyncio
async def test_p2_task_origin_partial_cr_failure_is_stable_result_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = TurnCommitLedger()
    registry, _p3, manager, _pushed = _registry(tmp_path, commit_ledger=ledger)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-task-origin-unknown",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    runtime = route.activation_lease._runtime

    async def fail_terminal_transition(*_args: object, **_kwargs: object):
        raise RuntimeError("injected transition loss")

    monkeypatch.setattr(runtime._cr, "transition_response", fail_terminal_transition)
    text = "retain unknown after partial canonical write"
    params = _p2_task_origin_params(stem="task-origin-unknown", text=text)
    first = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-unknown",
        session_id="session-product",
        channel_id="web",
    )
    replayed = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-unknown",
        session_id="session-product",
        channel_id="web",
    )
    second_request = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-unknown-second",
        session_id="session-product",
        channel_id="web",
    )

    assert first.ok is False
    assert cast(dict, first.payload["error"])["code"] == (
        ErrorCode.RESULT_UNKNOWN.value
    )
    assert replayed.payload == first.payload
    assert second_request.ok is False
    assert cast(dict, second_request.payload["error"])["reason"] == (
        "TURN_COMMIT_ALREADY_SUBMITTED"
    )
    assert manager.agent.calls == 0
    assert (
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-task-origin-unknown",
                "commit-task-origin-unknown",
            ),
            SCOPE,
        ).text
        == text
    )
    assert (
        registry._unknown_turn_commits_by_commit["commit-task-origin-unknown"].turn_id
        == "turn-task-origin-unknown"
    )
    assert len(runtime.snapshot().conversation.conversation.responses) == 1
    await registry.stop()
    assert registry._unknown_turn_commits_by_commit == {}
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-task-origin-unknown",
                "commit-task-origin-unknown",
            ),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_p2_task_origin_unknown_eviction_retires_identity_and_frees_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = TurnCommitLedger(capacity=2)
    registry, _p3, _manager, _pushed = _registry(tmp_path, commit_ledger=ledger)
    monkeypatch.setattr(registry, "_TURN_COMMIT_CAPACITY", 2)
    monkeypatch.setattr(registry, "_TURN_COMMIT_CAPACITY_PER_ROUTE", 1)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-task-origin-unknown-eviction",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    runtime = registry._p2_routes[
        ("session-product", "interaction-1")
    ].activation_lease._runtime
    original_transition = runtime._cr.transition_response

    async def fail_terminal_transition(*_args: object, **_kwargs: object):
        raise RuntimeError("injected transition loss")

    monkeypatch.setattr(runtime._cr, "transition_response", fail_terminal_transition)
    text = "retire an unknown canonical response without reopening it"
    params = _p2_task_origin_params(stem="unknown-eviction", text=text)
    unknown = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-unknown-eviction",
        session_id="session-product",
        channel_id="web",
    )
    assert unknown.ok is False
    assert cast(dict, unknown.payload["error"])["code"] == (
        ErrorCode.RESULT_UNKNOWN.value
    )
    assert (
        registry._unknown_turn_commits_by_commit["commit-unknown-eviction"].turn_id
        == "turn-unknown-eviction"
    )
    monkeypatch.setattr(runtime._cr, "transition_response", original_transition)
    fresh = await registry.handle_p2_submit(
        params=_p2_task_origin_params(
            stem="unknown-eviction-fresh",
            text="fresh origin after bounded unknown eviction",
        ),
        request_id="request-submit-unknown-eviction-fresh",
        session_id="session-product",
        channel_id="web",
    )
    assert fresh.ok is True
    assert registry._unknown_turn_commits_by_commit == {}
    with pytest.raises(ContractViolation, match="accepted commit"):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-unknown-eviction",
                "commit-unknown-eviction",
            ),
            SCOPE,
        )
    retired = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-unknown-eviction-retry",
        session_id="session-product",
        channel_id="web",
    )
    assert retired.ok is False
    assert cast(dict, retired.payload["error"])["reason"] == "TURN_COMMIT_RETIRED"
    await registry.stop()


@pytest.mark.asyncio
async def test_p2_task_origin_reconciles_terminal_write_before_response_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-task-origin-terminal-loss",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    runtime = route.activation_lease._runtime
    original_transition = runtime._cr.transition_response

    async def mutate_then_lose(*args: object, **kwargs: object):
        await original_transition(*args, **kwargs)
        raise RuntimeError("response lost after canonical terminal write")

    monkeypatch.setattr(runtime._cr, "transition_response", mutate_then_lose)
    params = _p2_task_origin_params(
        stem="task-origin-terminal-loss",
        text="recover the exact terminal task origin",
    )
    first = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-terminal-loss",
        session_id="session-product",
        channel_id="web",
    )
    replayed = await registry.handle_p2_submit(
        params=params,
        request_id="request-submit-task-origin-terminal-loss",
        session_id="session-product",
        channel_id="web",
    )

    assert first.ok is True
    assert replayed.payload == first.payload
    response = cast(dict, first.payload["result"])["response"]
    canonical = next(
        item
        for item in runtime.snapshot().conversation.conversation.responses
        if item.ref.response_id == response["response_id"]
    )
    assert canonical.turn_id == "turn-task-origin-terminal-loss"
    assert canonical.state.value == "terminal"
    assert canonical.outcome.value == "completed"
    assert manager.agent.calls == 0


@pytest.mark.asyncio
async def test_p2_task_origin_rejects_client_declared_canonical_response_id(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-task-origin-client-response",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True

    rejected = await registry.handle_p2_submit(
        params={
            **_p2_task_origin_params(
                stem="task-origin-client-response",
                text="do not trust a browser response identity",
            ),
            "response_id": "response-browser-declared",
        },
        request_id="request-submit-task-origin-client-response",
        session_id="session-product",
        channel_id="web",
    )

    assert rejected.ok is False
    assert cast(dict, rejected.payload["error"])["code"] == (
        ErrorCode.INVALID_ARGUMENT.value
    )
    assert registry._p2_submit_operations == {}
    assert manager.agent.calls == 0


@pytest.mark.asyncio
async def test_product_p2_barge_in_is_exact_replayable_and_playback_scoped(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    blocking = _BlockingFacade()
    manager.agent = blocking
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-barge",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    submitted = await registry.handle_p2_submit(
        params=_p2_params(
            commit_id="commit-barge",
            turn_id="turn-barge",
            response_id="response-barge",
            committed_at=NOW,
            text="keep this response active",
            dispatch_target="agent",
        ),
        request_id="request-submit-barge",
        session_id="session-product",
        channel_id="web",
    )
    assert submitted.ok is True
    await asyncio.wait_for(blocking.started.wait(), timeout=1)

    params = _p2_params(
        action_id="barge-action-1",
        response_id="response-barge",
        response_generation=0,
        cancel_response=False,
    )
    interrupted = await registry.handle_p2_barge_in(
        params=params,
        request_id="request-barge-1",
        session_id="session-product",
    )
    replayed = await registry.handle_p2_barge_in(
        params=params,
        request_id="request-barge-1",
        session_id="session-product",
    )
    conflict = await registry.handle_p2_barge_in(
        params={**params, "cancel_response": True},
        request_id="request-barge-1",
        session_id="session-product",
    )

    assert interrupted.ok is True
    assert replayed.payload == interrupted.payload
    assert conflict.ok is False
    assert cast(dict, conflict.payload["error"])["reason"] == (
        "PRODUCT_REQUEST_ID_CONFLICT"
    )
    result = cast(dict, interrupted.payload["result"])
    assert result["status"] == "barge_in_applied"
    assert result["cancel_response"] is False
    assert result["applied"] is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    effects = route.activation_lease._runtime._cr.snapshot().effects
    effect_types = [record.effect.effect_type for record in effects]
    assert effect_types.count("playback.stop") == 1
    assert not {"response.cancel", "round.cancel", "task.cancel"} & set(effect_types)

    blocking.release.set()
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_submit_caller_cancellation_retains_exact_disconnect_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    blocking = _BlockingFacade()
    manager.agent = blocking
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-p2-activate-cancel",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    submit_params = _p2_params(
        commit_id="commit-cancel",
        turn_id="turn-cancel",
        response_id="response-cancel",
        committed_at=NOW,
        text="retained after caller cancellation",
    )

    caller = asyncio.create_task(
        registry.handle_p2_submit(
            params=submit_params,
            request_id="request-submit-cancel",
            session_id="session-product",
            channel_id="web",
        )
    )
    await asyncio.wait_for(blocking.started.wait(), timeout=1)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    blocking.release.set()
    retained = registry._p2_submit_operations["request-submit-cancel"]
    first = await asyncio.wait_for(asyncio.shield(retained.task), timeout=1)
    try:
        await registry.close_active_routes()
    except RuntimeError:
        # The bounded disconnect close may report retained cleanup pending;
        # exact operation replay must remain available in either state.
        pass

    replay = await registry.handle_p2_submit(
        params=submit_params,
        request_id="request-submit-cancel",
        session_id="session-product",
        channel_id="web",
    )

    assert first.ok is True
    assert replay.payload == first.payload
    assert blocking.calls == 1
    for _ in range(3):
        try:
            await registry.close_active_routes()
            break
        except RuntimeError:
            await asyncio.sleep(0)


def _mutation_params(**changes: object) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "operation": "task.cancel",
        "command_id": "command-cancel-1",
        "issued_at": NOW,
        "correlation_id": "correlation-cancel-1",
        "task_id": "task-1",
    }
    params.update(changes)
    return params


def _text_intent_params(
    *, stem: str, text: str, operation: str, task_id: str | None = None
) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "correlation_id": f"correlation-{stem}",
        "source": "text",
        "operation_hint": operation,
        "interaction_id": "chat-task-intent-1",
        "turn_id": f"turn-{stem}",
        "commit_id": f"commit-{stem}",
        "committed_at": NOW,
        "text": text,
    }
    if task_id is not None:
        params["task_id_hint"] = task_id
    return params


def _voice_intent_params(
    *, stem: str, operation: str, task_id: str | None = None
) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "correlation_id": "correlation-p2",
        "source": "voice",
        "operation_hint": operation,
        "interaction_id": "interaction-1",
        "turn_id": f"turn-{stem}",
        "commit_id": f"commit-{stem}",
    }
    if task_id is not None:
        params["task_id_hint"] = task_id
    return params


def _assert_rejected_intent_manifest_has_no_formal_facts(
    payload: Mapping[str, object],
) -> None:
    forbidden_evidence = {
        "TRUSTED_AUTHORITY_RESOLVED",
        "FORMAL_ACTIVATION_LEASE_OPEN",
        "RUNTIME_PATH_OBSERVED",
    }
    authority = _route(payload, "authority")
    control = _route(payload, "p3.control")
    assert authority == {
        "segment": "authority",
        "truth": "unavailable",
        "reason_id": "TRUSTED_AUTHORITY_UNAVAILABLE",
        "evidence_ids": ["PACKAGE_CONTRACT_ONLY", "NO_RUNTIME_EVIDENCE"],
        "formal_runtime_observed": False,
    }
    assert control == {
        "segment": "p3.control",
        "truth": "unavailable",
        "reason_id": "FORMAL_ACTIVATION_EVIDENCE_MISSING",
        "evidence_ids": ["PACKAGE_CONTRACT_ONLY", "NO_RUNTIME_EVIDENCE"],
        "formal_runtime_observed": False,
    }
    for route in cast(dict[str, object], payload["product_composition"])["routes"]:
        fact = cast(dict[str, object], route)
        assert not forbidden_evidence.intersection(
            cast(list[str], fact["evidence_ids"])
        )


@pytest.mark.asyncio
async def test_rejected_task_intents_never_fabricate_formal_manifest(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    denied_params = _text_intent_params(
        stem="manifest-denied",
        text="create task: denied manifest request",
        operation="task.create",
    )
    denied_params["auth_token"] = "invalid-token"
    denied = await registry.handle_p3_intent(
        params=denied_params,
        request_id="request-manifest-denied",
        session_id="session-product",
    )
    invalid = await registry.handle_p3_intent(
        params={
            **_text_intent_params(
                stem="manifest-invalid",
                text="create task: invalid manifest request",
                operation="task.create",
            ),
            "model_intent": "client-selected-provider",
        },
        request_id="request-manifest-invalid",
        session_id="session-product",
    )
    missing = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="manifest-missing",
            text="confirm task request 0123456789abcdef0123456789abcdef",
            operation="task.create",
        ),
        request_id="request-manifest-missing",
        session_id="session-product",
    )

    assert denied.ok is False
    assert cast(dict, denied.payload["error"])["reason"] == (
        "FORMAL_TASK_AUTHENTICATION_REQUIRED"
    )
    assert invalid.ok is False
    assert cast(dict, invalid.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
    assert missing.ok is False
    assert cast(dict, missing.payload["error"])["reason"] == (
        "TASK_CONFIRMATION_BINDING_MISMATCH"
    )
    for rejected in (denied, invalid, missing):
        _assert_rejected_intent_manifest_has_no_formal_facts(rejected.payload)

    assert composition.prepare_calls == []
    assert composition.mutation_calls == []
    assert registry._pending_task_intents == {}
    assert registry._agent_manager.pins == 0
    assert registry._agent_manager.unpins == 0
    with sqlite3.connect(tmp_path / "confirmations.sqlite3") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM p3_confirmations"
        ).fetchone() == (0,)

    successful = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="manifest-success",
            text="create task: successful manifest request",
            operation="task.create",
        ),
        request_id="request-manifest-success",
        session_id="session-product",
    )
    assert successful.ok is True
    assert _route(successful.payload, "authority")["truth"] == "formal"
    assert _route(successful.payload, "p3.control")["truth"] == "formal"


@pytest.mark.asyncio
async def test_voice_intent_create_uses_two_exact_p2_commits_and_retains_live_progress_origin(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    registry, composition, _owner = _voice_mutation_registry(
        tmp_path,
        commit_ledger=ledger,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-natural-voice-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    first_text = "create task: inspect the repository"
    first_commit = await registry.handle_p2_submit(
        params=_p2_task_origin_params(stem="natural-voice", text=first_text),
        request_id="request-natural-voice-commit",
        session_id="session-product",
        channel_id="web",
    )
    assert first_commit.ok is True
    first = await registry.handle_p3_intent(
        params=_voice_intent_params(
            stem="natural-voice",
            operation="task.create",
        ),
        request_id="request-natural-voice-intent",
        session_id="session-product",
    )
    assert first.ok is True, first.payload
    first_result = cast(dict[str, object], first.payload["result"])
    assert first_result["status"] == "clarification"
    token = cast(str, first_result["confirmation_token"])
    assert composition.mutation_calls == []

    confirmation_text = f"confirm task request {token}"
    confirmation_commit = await registry.handle_p2_submit(
        params=_p2_task_origin_params(
            stem="natural-voice-confirm",
            text=confirmation_text,
        ),
        request_id="request-natural-voice-confirm-commit",
        session_id="session-product",
        channel_id="web",
    )
    assert confirmation_commit.ok is True
    confirmed = await registry.handle_p3_intent(
        params=_voice_intent_params(
            stem="natural-voice-confirm",
            operation="task.create",
        ),
        request_id="request-natural-voice-confirm-intent",
        session_id="session-product",
    )

    assert confirmed.ok is True, confirmed.payload
    result = cast(dict[str, object], confirmed.payload["result"])
    assert result["status"] == "dispatched"
    assert result["task_id"] == "task-created-natural-1"
    assert result["origin_kind"] == "voice"
    assert result["origin_id"] == "interaction-1"
    assert result["confirmation_commit_id"] == "commit-natural-voice-confirm"
    assert result["task_control_binding"] == {
        "subject_id": SCOPE.subject_id,
        "session_id": SCOPE.session_id,
        "project_id": SCOPE.project_id,
        "correlation_id": "correlation-p2",
        "generation": registry._p3_confirmation_generation,
    }
    assert len(composition.mutation_calls) == 1
    assert registry._voice_task_origins["task-created-natural-1"].interaction_id == (
        "interaction-1"
    )
    assert registry._voice_task_origins["task-created-natural-1"].correlation_id == (
        "correlation-p2"
    )
    assert (
        registry._voice_task_origins[
            "task-created-natural-1"
        ].response_ref.interaction_id
        == "interaction-1"
    )
    await registry.stop()


@pytest.mark.asyncio
async def test_voice_pending_confirmation_is_released_when_exact_route_closes(
    tmp_path: Path,
) -> None:
    ledger = TurnCommitLedger()
    registry, composition, _owner = _voice_mutation_registry(
        tmp_path,
        commit_ledger=ledger,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-pending-close-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    sentinel = "create task: SENTINEL_PENDING_VOICE_TEXT"
    committed = await registry.handle_p2_submit(
        params=_p2_task_origin_params(stem="pending-close", text=sentinel),
        request_id="request-pending-close-commit",
        session_id="session-product",
        channel_id="web",
    )
    assert committed.ok is True
    pending = await registry.handle_p3_intent(
        params=_voice_intent_params(
            stem="pending-close",
            operation="task.create",
        ),
        request_id="request-pending-close-intent",
        session_id="session-product",
    )
    token = cast(dict[str, object], pending.payload["result"])["confirmation_token"]
    assert token in registry._pending_task_intents
    assert (
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-pending-close",
                "commit-pending-close",
            ),
            SCOPE,
        ).text
        == sentinel
    )

    closed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-pending-close-route",
        session_id="session-product",
    )
    replayed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-pending-close-route-replay",
        session_id="session-product",
    )
    registry._drop_voice_task_origins_for_route_locked(
        ("session-foreign", "interaction-foreign")
    )

    assert closed.ok is True
    assert replayed.ok is True
    assert registry._pending_task_intents == {}
    assert "commit-pending-close" not in registry._accepted_turn_commits_by_commit
    assert "commit-pending-close" not in registry._accepted_voice_commit_routes
    assert sentinel not in repr(registry._pending_task_intents)
    assert composition.mutation_calls == []
    with pytest.raises(ContractViolation):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-pending-close",
                "commit-pending-close",
            ),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_voice_intent_obtain_then_close_race_releases_unstored_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = TurnCommitLedger()
    registry, composition, _owner = _voice_mutation_registry(
        tmp_path,
        commit_ledger=ledger,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-obtain-close-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    committed = await registry.handle_p2_submit(
        params=_p2_task_origin_params(
            stem="obtain-close",
            text="create task: bounded race request",
        ),
        request_id="request-obtain-close-commit",
        session_id="session-product",
        channel_id="web",
    )
    assert committed.ok is True
    original_obtain = registry._obtain_task_intent_commit
    obtained = asyncio.Event()
    release = asyncio.Event()

    async def blocked_obtain(**kwargs: object) -> TurnCommit:
        commit = await original_obtain(**kwargs)
        obtained.set()
        await release.wait()
        return commit

    monkeypatch.setattr(registry, "_obtain_task_intent_commit", blocked_obtain)
    intent = asyncio.create_task(
        registry.handle_p3_intent(
            params=_voice_intent_params(
                stem="obtain-close",
                operation="task.create",
            ),
            request_id="request-obtain-close-intent",
            session_id="session-product",
        )
    )
    await asyncio.wait_for(obtained.wait(), timeout=1)
    closed = await registry.handle_p2_close(
        params=_p2_params(),
        request_id="request-obtain-close-route",
        session_id="session-product",
    )
    release.set()
    rejected = await asyncio.wait_for(intent, timeout=1)

    assert closed.ok is True
    assert rejected.ok is False
    assert cast(dict, rejected.payload["error"])["reason"] == (
        "VOICE_TASK_ROUTE_MISMATCH"
    )
    assert registry._pending_task_intents == {}
    assert "commit-obtain-close" not in registry._accepted_turn_commits_by_commit
    assert "commit-obtain-close" not in registry._accepted_voice_commit_routes
    assert composition.mutation_calls == []
    with pytest.raises(ContractViolation):
        ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-obtain-close",
                "commit-obtain-close",
            ),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_text_intent_create_requires_later_exact_committed_confirmation(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    first = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-create",
            text="create task: inspect the repository",
            operation="task.create",
        ),
        request_id="request-natural-create",
        session_id="session-product",
    )

    assert first.ok is True, first.payload
    clarification = cast(dict[str, object], first.payload["result"])
    assert clarification["status"] == "clarification"
    token = cast(str, clarification["confirmation_token"])
    assert len(token) == 32
    assert composition.prepare_calls == []
    assert composition.mutation_calls == []

    confirmed = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-create-confirm",
            text=f"confirm task request {token}",
            operation="task.create",
        ),
        request_id="request-natural-create-confirm",
        session_id="session-product",
    )

    assert confirmed.ok is True, confirmed.payload
    result = cast(dict[str, object], confirmed.payload["result"])
    assert result["status"] == "dispatched"
    assert result["confirmation_commit_id"] == "commit-natural-create-confirm"
    assert result["task_control_binding"] == {
        "subject_id": SCOPE.subject_id,
        "session_id": SCOPE.session_id,
        "project_id": SCOPE.project_id,
        "correlation_id": "correlation-natural-create",
        "generation": registry._p3_confirmation_generation,
    }
    assert len(composition.mutation_calls) == 1
    operation, forwarded = composition.mutation_calls[0]
    assert operation == "task.create"
    assert forwarded["instruction"] == "inspect the repository"
    assert forwarded["commit_id"] == "commit-natural-create"
    assert forwarded["origin_commit_sha256"] == clarification["commit_sha256"]
    assert registry._pending_task_intents == {}


@pytest.mark.asyncio
async def test_completed_text_intent_recovers_content_free_without_replaying_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    secret_instruction = "inspect SENTINEL_PROVIDER_SECRET without retaining this text"
    first = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-recovery",
            text=f"create task: {secret_instruction}",
            operation="task.create",
        ),
        request_id="request-natural-recovery",
        session_id="session-product",
    )
    token = cast(dict[str, object], first.payload["result"])["confirmation_token"]
    confirmed_request_id = "request-natural-recovery-confirm"
    confirmed = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-recovery-confirm",
            text=f"confirm task request {token}",
            operation="task.create",
        ),
        request_id=confirmed_request_id,
        session_id="session-product",
    )
    assert confirmed.ok is True
    assert len(composition.mutation_calls) == 1

    status_params = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "correlation_id": "correlation-natural-recovery-confirm",
        "intent_request_id": confirmed_request_id,
    }
    recovered = await registry.handle_p3_intent_status(
        params=status_params,
        request_id="request-natural-recovery-status",
        session_id="session-product",
    )
    replayed = await registry.handle_p3_intent_status(
        params=status_params,
        request_id="request-natural-recovery-status-replay",
        session_id="session-product",
    )

    assert recovered.ok is True, recovered.payload
    assert replayed.ok is True, replayed.payload
    assert recovered.payload["result"] == replayed.payload["result"]
    assert cast(dict, recovered.payload["result"])["status"] == "settled"
    assert cast(dict, recovered.payload["result"])["phase"] == "final"
    recovered_wire = repr(recovered.payload)
    assert secret_instruction not in recovered_wire
    assert "SENTINEL_PROVIDER_SECRET" not in recovered_wire
    assert "confirm task request" not in recovered_wire
    intent = cast(dict[str, object], cast(dict, recovered.payload["result"])["intent"])
    assert intent["status"] == "dispatched"
    assert intent["formal_task_result"] == {
        "recovered": True,
        "task_id": "task-created-natural-1",
    }
    assert len(composition.mutation_calls) == 1

    wrong_scope = await registry.handle_p3_intent_status(
        params={**status_params, "correlation_id": "correlation-foreign"},
        request_id="request-natural-recovery-wrong-scope",
        session_id="session-product",
    )
    unknown = await registry.handle_p3_intent_status(
        params={**status_params, "intent_request_id": "request-unknown"},
        request_id="request-natural-recovery-unknown",
        session_id="session-product",
    )
    assert wrong_scope.ok is False
    assert unknown.ok is False
    assert len(composition.mutation_calls) == 1

    exception_canary = "SENTINEL_RECOVERY_AUTHORITY_SECRET"

    async def fail_authority(**_kwargs: object) -> NoReturn:
        raise RuntimeError(exception_canary)

    monkeypatch.setattr(registry, "_preauthorize_task_intent", fail_authority)
    failed = await registry.handle_p3_intent_status(
        params=status_params,
        request_id="request-natural-recovery-authority-failed",
        session_id="session-product",
    )
    assert failed.ok is False
    assert failed.payload["error"] == {
        "reason": "TASK_INTENT_RECOVERY_FAILED",
        "code": ErrorCode.UNAVAILABLE.value,
        "message": "task intent recovery failed closed",
    }
    assert exception_canary not in repr(failed.payload)
    assert len(composition.mutation_calls) == 1


@pytest.mark.asyncio
async def test_pending_intent_status_recovers_exact_phase_then_expires_without_mutation(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    request_id = "request-natural-pending-status"
    first = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-pending-status",
            text="create task: bounded pending status",
            operation="task.create",
        ),
        request_id=request_id,
        session_id="session-product",
    )
    first_result = cast(dict[str, object], first.payload["result"])
    token = cast(str, first_result["confirmation_token"])
    status_params = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "correlation_id": "correlation-natural-pending-status",
        "intent_request_id": request_id,
    }

    pending = await registry.handle_p3_intent_status(
        params=status_params,
        request_id="request-natural-pending-status-query",
        session_id="session-product",
    )
    replayed = await registry.handle_p3_intent_status(
        params=status_params,
        request_id="request-natural-pending-status-replay",
        session_id="session-product",
    )
    assert pending.ok is True and replayed.ok is True
    pending_result = cast(dict[str, object], pending.payload["result"])
    assert pending_result["status"] == "pending"
    assert pending_result["phase"] == "awaiting_confirmation"
    assert cast(dict, pending_result["intent"])["confirmation_token"] == token
    assert pending_result == replayed.payload["result"]
    assert composition.mutation_calls == []

    assert registry._evict_oldest_pending_task_intent_locked() is True
    expired = await registry.handle_p3_intent_status(
        params=status_params,
        request_id="request-natural-pending-status-expired",
        session_id="session-product",
    )
    assert expired.ok is True
    assert expired.payload["result"] == {
        "status": "expired",
        "phase": "expired",
        "intent_request_id": request_id,
        "source": "text",
        "intent": None,
    }
    assert composition.mutation_calls == []


@pytest.mark.asyncio
async def test_non_destructive_clarification_status_remains_content_free_pending(
    tmp_path: Path,
) -> None:
    registry, composition, _manager, _pushed = _registry(tmp_path, p2=False, p3=True)
    request_id = "request-natural-unclear-status"
    unclear = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-unclear-status",
            text="what is its task status",
            operation="task.status",
            task_id="task-alpha",
        ),
        request_id=request_id,
        session_id="session-product",
    )
    assert unclear.ok is True
    recovered = await registry.handle_p3_intent_status(
        params={
            "auth_token": "trusted-token",
            "session_id": "session-product",
            "correlation_id": "correlation-natural-unclear-status",
            "intent_request_id": request_id,
        },
        request_id="request-natural-unclear-status-query",
        session_id="session-product",
    )
    assert recovered.ok is True
    result = cast(dict[str, object], recovered.payload["result"])
    assert result["status"] == "pending"
    assert result["phase"] == "clarification"
    intent = cast(dict[str, object], result["intent"])
    assert intent["confirmation_token"] is None
    assert intent["confirmation_form"] is None
    assert "what is its task status" not in repr(recovered.payload)
    assert composition.query_calls == []


@pytest.mark.asyncio
async def test_natural_task_intent_rejects_client_model_intent_before_authority(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    result = await registry.handle_p3_intent(
        params={
            **_text_intent_params(
                stem="natural-model-tamper",
                text="create task: bounded request",
                operation="task.create",
            ),
            "model_intent": "client-selected-provider",
        },
        request_id="request-natural-model-tamper",
        session_id="session-product",
    )

    assert result.ok is False
    assert cast(dict, result.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
    assert composition.authority_calls == []
    assert composition.prepare_calls == []
    assert composition.mutation_calls == []


@pytest.mark.asyncio
async def test_resolver_exception_is_content_free_on_wire_and_in_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    sentinel = "SENTINEL_PROVIDER_SECRET_TRANSCRIPT"
    logged: list[tuple[str, dict[str, object]]] = []

    def capture_warning(message: str, **kwargs: object) -> None:
        logged.append((message, cast(dict[str, object], kwargs["extra"])))

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry.logger.warning",
        capture_warning,
    )

    class _LeakingResolver:
        def resolve(self, *_args: object) -> object:
            raise VoiceTaskBridgeViolation(
                "SENTINEL_PROVIDER_REASON",
                sentinel,
                ErrorCode.PERMISSION_DENIED,
            )

    registry._task_intent_bridge = cast(object, _LeakingResolver())
    result = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-resolver-canary",
            text="create task: bounded resolver canary",
            operation="task.create",
        ),
        request_id="request-natural-resolver-canary",
        session_id="session-product",
    )

    assert result.ok is False
    error = cast(dict[str, object], result.payload["error"])
    assert error == {
        "code": ErrorCode.PERMISSION_DENIED.value,
        "reason": "TASK_INTENT_RESOLUTION_REJECTED",
        "message": "task intent resolution was rejected",
    }
    _assert_rejected_intent_manifest_has_no_formal_facts(result.payload)
    rendered = repr(result.payload) + repr(logged)
    assert sentinel not in rendered
    assert "SENTINEL_PROVIDER_REASON" not in rendered
    _message, record = next(
        item
        for item in logged
        if item[1].get("live_voice_event") == "task_intent_resolution_rejected"
    )
    assert record["exception_class"] == "VoiceTaskBridgeViolation"
    assert len(cast(str, record["request_digest"])) == 16
    assert composition.query_calls == []
    with pytest.raises(ContractViolation):
        registry._commit_ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-natural-resolver-canary",
                "commit-natural-resolver-canary",
            ),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_mixed_confirmation_resolution_cannot_consume_pending_task_intent(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    original_text = "create task: preserve the exact pending request"
    pending = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="mixed-confirmation-original",
            text=original_text,
            operation="task.create",
        ),
        request_id="request-mixed-confirmation-original",
        session_id="session-product",
    )
    assert pending.ok is True
    token = cast(
        str, cast(dict[str, object], pending.payload["result"])["confirmation_token"]
    )

    class MixedAuthorityResolver:
        def resolve(self, commit: TurnCommit) -> ResolvedTaskIntent:
            instruction = "approve"
            values = {
                "provider": "malicious.test",
                "implementation_class": "mixed_authority_fields",
                "commit_sha256": hashlib.sha256(commit.canonical_bytes()).hexdigest(),
                "operation": None,
                "task_id": None,
                "name": None,
                "instruction": instruction,
                "source_span": TaskIntentSourceSpan(0, len(instruction)),
                "target_span": None,
                "requires_confirmation": False,
                "confirmation_token": token,
                "reason": "TASK_CONFIRMATION_RESOLVED",
            }
            return ResolvedTaskIntent(
                disposition=TaskIntentDisposition.CLARIFICATION,
                resolution_id=hashlib.sha256(
                    canonical_json_bytes(_resolution_identity(**values))
                ).hexdigest(),
                **values,
            )

    registry._task_intent_bridge = VoiceTaskBridge(MixedAuthorityResolver())
    rejected = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="mixed-confirmation-forged",
            text="approve",
            operation="task.create",
        ),
        request_id="request-mixed-confirmation-forged",
        session_id="session-product",
    )

    assert rejected.ok is False
    assert rejected.payload["error"] == {
        "code": ErrorCode.PERMISSION_DENIED.value,
        "reason": "TASK_INTENT_RESOLUTION_REJECTED",
        "message": "task intent resolution was rejected",
    }
    assert set(registry._pending_task_intents) == {token}
    assert composition.prepare_calls == []
    assert composition.query_calls == []
    assert composition.mutation_calls == []
    assert registry._agent_manager.get_calls == []
    assert registry._agent_manager.agent.executions == []
    assert registry._agent_manager.code_agent.executions == []
    assert registry._agent_manager.pins == 0
    assert registry._agent_manager.unpins == 0
    assert (
        registry._commit_ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-mixed-confirmation-original",
                "commit-mixed-confirmation-original",
            ),
            SCOPE,
        ).text
        == original_text
    )
    with pytest.raises(ContractViolation):
        registry._commit_ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-mixed-confirmation-forged",
                "commit-mixed-confirmation-forged",
            ),
            SCOPE,
        )
    with sqlite3.connect(tmp_path / "confirmations.sqlite3") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM p3_confirmations"
        ).fetchone() == (0,)


@pytest.mark.asyncio
async def test_untyped_resolver_exception_is_content_free_and_releases_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    sentinel = "SENTINEL_UNTYPED_PROVIDER_SECRET"
    logged: list[tuple[str, dict[str, object]]] = []

    def capture_warning(message: str, **kwargs: object) -> None:
        logged.append((message, cast(dict[str, object], kwargs["extra"])))

    class _FailingResolver:
        def resolve(self, *_args: object) -> object:
            raise RuntimeError(sentinel)

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry.logger.warning",
        capture_warning,
    )
    registry._task_intent_bridge = cast(object, _FailingResolver())
    result = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-resolver-untyped",
            text="create task: bounded resolver failure",
            operation="task.create",
        ),
        request_id="request-natural-resolver-untyped",
        session_id="session-product",
    )

    assert result.ok is False
    assert cast(dict[str, object], result.payload["error"]) == {
        "code": ErrorCode.UNAVAILABLE.value,
        "reason": "TASK_INTENT_RESOLUTION_FAILED",
        "message": "task intent resolver failed closed",
    }
    assert sentinel not in repr(result.payload) + repr(logged)
    _message, record = next(
        item
        for item in logged
        if item[1].get("live_voice_event") == "task_intent_resolution_failed"
    )
    assert record["exception_class"] == "RuntimeError"
    assert composition.mutation_calls == []
    with pytest.raises(ContractViolation):
        registry._commit_ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-natural-resolver-untyped",
                "commit-natural-resolver-untyped",
            ),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_abandoned_pending_intent_evicts_oldest_exact_commit_at_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _composition, _owner = _mutation_registry(tmp_path)
    monkeypatch.setattr(registry, "_PRODUCT_OPERATION_CAPACITY", 1)
    first = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-abandoned-first",
            text="create task: first bounded request",
            operation="task.create",
        ),
        request_id="request-natural-abandoned-first",
        session_id="session-product",
    )
    second = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-abandoned-second",
            text="create task: second bounded request",
            operation="task.create",
        ),
        request_id="request-natural-abandoned-second",
        session_id="session-product",
    )

    first_token = cast(dict[str, object], first.payload["result"])["confirmation_token"]
    second_token = cast(dict[str, object], second.payload["result"])[
        "confirmation_token"
    ]
    assert first.ok is True and second.ok is True
    assert first_token not in registry._pending_task_intents
    assert second_token in registry._pending_task_intents
    with pytest.raises(ContractViolation):
        registry._commit_ledger.require_origin(
            OriginRef(
                "committed_turn",
                "turn-natural-abandoned-first",
                "commit-natural-abandoned-first",
            ),
            SCOPE,
        )
    await registry.stop()


@pytest.mark.asyncio
async def test_cancel_confirmation_wrong_task_and_scope_have_zero_effect(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)
    first = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-cancel",
            text="cancel task task-alpha",
            operation="task.cancel",
            task_id="task-alpha",
        ),
        request_id="request-natural-cancel",
        session_id="session-product",
    )
    token = cast(dict[str, object], first.payload["result"])["confirmation_token"]

    wrong_task = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-cancel-wrong",
            text=f"confirm task request {token}",
            operation="task.cancel",
            task_id="task-beta",
        ),
        request_id="request-natural-cancel-wrong",
        session_id="session-product",
    )

    assert wrong_task.ok is False
    assert cast(dict, wrong_task.payload["error"])["reason"] == (
        "TASK_CONFIRMATION_BINDING_MISMATCH"
    )
    assert composition.prepare_calls == []
    assert composition.mutation_calls == []
    assert token in registry._pending_task_intents


@pytest.mark.asyncio
async def test_text_status_dispatches_formal_query_and_partial_like_form_clarifies(
    tmp_path: Path,
) -> None:
    registry, composition, _manager, _pushed = _registry(tmp_path, p2=False, p3=True)
    status = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-status",
            text="task status task-alpha",
            operation="task.status",
            task_id="task-alpha",
        ),
        request_id="request-natural-status",
        session_id="session-product",
    )
    assert status.ok is True, status.payload
    assert cast(dict, status.payload["result"])["status"] == "dispatched"
    assert len(composition.query_calls) == 1

    unclear = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-unclear",
            text="what is its task status",
            operation="task.status",
            task_id="task-alpha",
        ),
        request_id="request-natural-unclear",
        session_id="session-product",
    )
    assert unclear.ok is True
    assert cast(dict, unclear.payload["result"])["status"] == "clarification"
    assert len(composition.query_calls) == 1


@pytest.mark.asyncio
async def test_task_intent_flag_off_has_zero_authority_or_commit_effect(
    tmp_path: Path,
) -> None:
    composition = _P3Composition(tmp_path)
    ledger = TurnCommitLedger()
    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, False),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=cast(object, lambda _message: None),
        commit_ledger=ledger,
    )
    result = await registry.handle_p3_intent(
        params=_text_intent_params(
            stem="natural-off",
            text="task status task-alpha",
            operation="task.status",
            task_id="task-alpha",
        ),
        request_id="request-natural-off",
        session_id="session-product",
    )
    assert result.ok is False
    assert composition.authority_calls == []
    with pytest.raises(ContractViolation):
        ledger.require_origin(
            OriginRef("committed_turn", "turn-natural-off", "commit-natural-off"),
            SCOPE,
        )


@pytest.mark.asyncio
async def test_p3_confirmation_issue_and_mutation_use_current_owner_permit(
    tmp_path: Path,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False,
            p3_text_enabled=False,
            p3_mutation_enabled=True,
        ),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    issue_params = _mutation_params()

    issued = await registry.handle_p3_confirmation_issue(
        params=issue_params,
        request_id="request-confirmation-1",
        session_id="session-product",
    )
    replayed_issue = await registry.handle_p3_confirmation_issue(
        params=issue_params,
        request_id="request-confirmation-1",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])
    confirmation_id = cast(str, receipt["confirmation_id"])
    mutation_params = _mutation_params(confirmation_id=confirmation_id)

    prepared = await composition.prepare_mutation_confirmation(
        operation="task.cancel",
        params={
            key: value for key, value in mutation_params.items() if key != "operation"
        },
        session_id="session-product",
    )
    with pytest.raises(FormalTaskViolation) as direct:
        forwarder.verify_and_consume(confirmation_id, prepared.binding, now=NOW)

    mutated = await registry.handle_p3_mutation(
        params=mutation_params,
        request_id="request-mutation-1",
        session_id="session-product",
    )
    replayed_mutation = await registry.handle_p3_mutation(
        params=mutation_params,
        request_id="request-mutation-1",
        session_id="session-product",
    )

    assert issued.ok is True
    assert replayed_issue.payload == issued.payload
    assert receipt["status"] == "confirmation_issued"
    assert receipt["command_id"] == "command-cancel-1"
    assert receipt["target_task_id"] == "task-1"
    assert receipt["task_control_binding"] == {
        "subject_id": SCOPE.subject_id,
        "session_id": SCOPE.session_id,
        "project_id": SCOPE.project_id,
        "correlation_id": "correlation-cancel-1",
        "generation": registry._p3_confirmation_generation,
    }
    assert direct.value.reason == "P3_CONFIRMATION_FORWARDING_REQUIRED"
    assert mutated.ok is True
    assert replayed_mutation.payload == mutated.payload
    mutation_result = cast(dict[str, object], mutated.payload["result"])
    assert mutation_result["command_id"] == "command-cancel-1"
    assert mutation_result["target_task_id"] == "task-1"
    assert len(composition.mutation_calls) == 1
    assert _route(mutated.payload, "authority")["truth"] == "formal"
    assert _route(mutated.payload, "p3.control")["truth"] == "formal"


@pytest.mark.asyncio
async def test_p3_confirmation_owner_mismatch_and_request_conflict_fail_closed(
    tmp_path: Path,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    issue_params = _mutation_params()
    issued = await registry.handle_p3_confirmation_issue(
        params=issue_params,
        request_id="request-confirmation-1",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])

    conflict = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(command_id="command-other"),
        request_id="request-confirmation-1",
        session_id="session-product",
    )
    mismatch = await registry.handle_p3_mutation(
        params=_mutation_params(
            confirmation_id=receipt["confirmation_id"],
            correlation_id="correlation-other",
        ),
        request_id="request-mutation-mismatch",
        session_id="session-product",
    )

    assert conflict.ok is False
    assert cast(dict, conflict.payload["error"])["reason"] == (
        "P3_CONFIRMATION_BINDING_MISMATCH"
    )
    assert mismatch.ok is False
    assert cast(dict, mismatch.payload["error"])["reason"] == (
        "P3_CONFIRMATION_BINDING_MISMATCH"
    )


@pytest.mark.asyncio
async def test_denied_p3_requests_do_not_reserve_replay_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    monkeypatch.setattr(registry, "_PRODUCT_OPERATION_CAPACITY", 1)

    denied_issue = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(auth_token="invalid-token"),
        request_id="request-confirmation-denied-capacity",
        session_id="session-product",
    )
    issued = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(),
        request_id="request-confirmation-valid-capacity",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])

    denied_mutation = await registry.handle_p3_mutation(
        params=_mutation_params(
            auth_token="invalid-token",
            confirmation_id=receipt["confirmation_id"],
        ),
        request_id="request-mutation-denied-capacity",
        session_id="session-product",
    )
    mutated = await registry.handle_p3_mutation(
        params=_mutation_params(confirmation_id=receipt["confirmation_id"]),
        request_id="request-mutation-valid-capacity",
        session_id="session-product",
    )

    assert denied_issue.ok is False
    assert cast(dict, denied_issue.payload["error"])["reason"] == (
        "FORMAL_TASK_AUTHENTICATION_REQUIRED"
    )
    assert issued.ok is True
    assert len(registry._p3_issue_operations) == 1
    assert denied_mutation.ok is False
    assert cast(dict, denied_mutation.payload["error"])["reason"] == (
        "FORMAL_TASK_AUTHENTICATION_REQUIRED"
    )
    assert mutated.ok is True
    assert len(registry._p3_mutation_operations) == 1
    assert len(composition.mutation_calls) == 1


@pytest.mark.asyncio
async def test_retained_p3_results_require_current_authority(
    tmp_path: Path,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    issue_params = _mutation_params()
    issued = await registry.handle_p3_confirmation_issue(
        params=issue_params,
        request_id="request-confirmation-revoked",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])
    mutation_params = _mutation_params(confirmation_id=receipt["confirmation_id"])
    mutated = await registry.handle_p3_mutation(
        params=mutation_params,
        request_id="request-mutation-revoked",
        session_id="session-product",
    )

    composition.replay_authority_revoked = True
    denied_issue_replay = await registry.handle_p3_confirmation_issue(
        params=issue_params,
        request_id="request-confirmation-revoked",
        session_id="session-product",
    )
    denied_mutation_replay = await registry.handle_p3_mutation(
        params=mutation_params,
        request_id="request-mutation-revoked",
        session_id="session-product",
    )

    assert issued.ok is True
    assert mutated.ok is True
    assert denied_issue_replay.ok is False
    assert cast(dict, denied_issue_replay.payload["error"])["reason"] == (
        "TASK_CONTEXT_PERMISSION_MISSING"
    )
    assert denied_mutation_replay.ok is False
    assert cast(dict, denied_mutation_replay.payload["error"])["reason"] == (
        "TASK_CONTEXT_PERMISSION_MISSING"
    )
    assert len(composition.mutation_calls) == 1


@pytest.mark.asyncio
async def test_product_operation_capacity_recovers_with_fail_closed_old_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    monkeypatch.setattr(registry, "_PRODUCT_OPERATION_CAPACITY", 1)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-capacity",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    first_params = _p2_params(
        commit_id="commit-capacity-1",
        turn_id="turn-capacity-1",
        response_id="response-capacity-1",
        committed_at=NOW,
        text="first capacity turn",
    )
    second_params = _p2_params(
        commit_id="commit-capacity-2",
        turn_id="turn-capacity-2",
        response_id="response-capacity-2",
        committed_at=NOW,
        text="second capacity turn",
    )
    first = await registry.handle_p2_submit(
        params=first_params,
        request_id="request-submit-capacity-1",
        session_id="session-product",
        channel_id="web",
    )
    second = await registry.handle_p2_submit(
        params=second_params,
        request_id="request-submit-capacity-2",
        session_id="session-product",
        channel_id="web",
    )
    expired = await registry.handle_p2_submit(
        params=first_params,
        request_id="request-submit-capacity-1",
        session_id="session-product",
        channel_id="web",
    )

    assert first.ok is True
    assert second.ok is True
    assert expired.ok is False
    assert cast(dict, expired.payload["error"])["reason"] == (
        "PRODUCT_OPERATION_REPLAY_EXPIRED"
    )
    assert manager.agent.calls == 2


@pytest.mark.asyncio
async def test_notification_polls_require_exact_serial_sequence(
    tmp_path: Path,
) -> None:
    registry, _p3, _manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-notification-sequence",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True

    gap = await registry.handle_p2_notification_next(
        params=_p2_params(notification_sequence=2),
        request_id="request-notification-gap",
        session_id="session-product",
    )
    first_waiter = asyncio.create_task(
        registry.handle_p2_notification_next(
            params=_p2_params(notification_sequence=1),
            request_id="request-notification-sequence-1",
            session_id="session-product",
        )
    )
    for _ in range(20):
        if "request-notification-sequence-1" in registry._p2_notification_operations:
            break
        await asyncio.sleep(0)
    concurrent = await registry.handle_p2_notification_next(
        params=_p2_params(notification_sequence=2),
        request_id="request-notification-sequence-2",
        session_id="session-product",
    )
    reordered = await registry.handle_p2_notification_next(
        params=_p2_params(notification_sequence=1),
        request_id="request-notification-reordered",
        session_id="session-product",
    )

    assert gap.ok is False
    assert cast(dict, gap.payload["error"])["reason"] == (
        "PRODUCT_NOTIFICATION_SEQUENCE_MISMATCH"
    )
    assert concurrent.ok is False
    assert cast(dict, concurrent.payload["error"])["reason"] == (
        "PRODUCT_NOTIFICATION_POLL_PENDING"
    )
    assert reordered.ok is False
    assert cast(dict, reordered.payload["error"])["reason"] == (
        "PRODUCT_NOTIFICATION_SEQUENCE_MISMATCH"
    )
    assert len(registry._p2_notification_operations) == 1

    await registry.close_active_routes()
    await asyncio.wait_for(first_waiter, timeout=1)


@pytest.mark.asyncio
async def test_idle_notification_poll_returns_effect_free_keepalive_before_gateway_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._P2_NOTIFICATION_LONG_POLL_TIMEOUT_SECONDS",
        0.001,
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-activate-notification-keepalive",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True

    keepalive = await registry.handle_p2_notification_next(
        params=_p2_params(notification_sequence=1),
        request_id="request-notification-keepalive-1",
        session_id="session-product",
    )

    assert keepalive.ok is True
    result = cast(dict[str, object], keepalive.payload["result"])
    assert result["status"] == "notification"
    assert result["kind"] == "transport.keepalive"
    assert result["response"] is None
    assert result["agent_event"] is None
    assert result["progress_event"] is None
    assert result["presentation_unit"] is None
    assert result["session_id"] == "session-product"
    assert result["activation_generation"] == 1
    assert (
        registry._p2_routes[("session-product", "interaction-1")].lease.closed is False
    )
    assert manager.agent.calls == 0

    second = await registry.handle_p2_notification_next(
        params=_p2_params(notification_sequence=2),
        request_id="request-notification-keepalive-2",
        session_id="session-product",
    )
    assert second.ok is True
    assert (
        cast(dict[str, object], second.payload["result"])["kind"]
        == "transport.keepalive"
    )
    await registry.close_active_routes()


@pytest.mark.asyncio
async def test_p2_activation_generation_never_resurrects_an_older_id(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    first_params = _p2_params(activation_id="activation-a", activation_generation=1)
    second_params = _p2_params(activation_id="activation-b", activation_generation=2)
    assert (
        await registry.handle_p2_activate(
            params=first_params,
            request_id="request-activate-a1",
            session_id="session-product",
            channel_id="web",
        )
    ).ok
    assert (
        await registry.handle_p2_close(
            params=first_params,
            request_id="request-close-a1",
            session_id="session-product",
        )
    ).ok
    assert (
        await registry.handle_p2_activate(
            params=second_params,
            request_id="request-activate-b2",
            session_id="session-product",
            channel_id="web",
        )
    ).ok
    assert (
        await registry.handle_p2_close(
            params=second_params,
            request_id="request-close-b2",
            session_id="session-product",
        )
    ).ok
    allocations_before = len(manager.get_calls)

    stale = await registry.handle_p2_activate(
        params=first_params,
        request_id="request-delayed-activate-a1",
        session_id="session-product",
        channel_id="web",
    )

    assert stale.ok is False
    assert cast(dict, stale.payload["error"])["reason"] == (
        "ACTIVATION_GENERATION_STALE"
    )
    assert len(manager.get_calls) == allocations_before
    assert registry._p2_routes == {}


@pytest.mark.asyncio
async def test_p2_generation_fence_survives_exact_tombstone_eviction(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    first_params: dict[str, object] | None = None
    for index in range(registry._CLOSED_ROUTE_CAPACITY + 1):
        params = _p2_params(
            correlation_id=f"correlation-capacity-{index}",
            interaction_id=f"interaction-capacity-{index}",
            activation_id=f"activation-capacity-{index}",
            activation_generation=1,
        )
        if first_params is None:
            first_params = params
        activated = await registry.handle_p2_activate(
            params=params,
            request_id=f"request-activate-capacity-{index}",
            session_id="session-product",
            channel_id="web",
        )
        closed = await registry.handle_p2_close(
            params=params,
            request_id=f"request-close-capacity-{index}",
            session_id="session-product",
        )
        assert activated.ok is True
        assert closed.ok is True

    assert first_params is not None
    assert (
        "session-product",
        "interaction-capacity-0",
    ) not in registry._closed_p2_routes
    allocations_before = len(manager.get_calls)
    stale = await registry.handle_p2_activate(
        params=first_params,
        request_id="request-delayed-after-tombstone-eviction",
        session_id="session-product",
        channel_id="web",
    )

    assert stale.ok is False
    assert cast(dict, stale.payload["error"])["reason"] == (
        "ACTIVATION_GENERATION_STALE"
    )
    assert len(manager.get_calls) == allocations_before


@pytest.mark.asyncio
async def test_p2_oversized_generation_allocates_nothing(
    tmp_path: Path,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)

    result = await registry.handle_p2_activate(
        params=_p2_params(activation_generation=2**64),
        request_id="request-oversized-generation",
        session_id="session-product",
        channel_id="web",
    )

    assert result.ok is False
    assert cast(dict, result.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
    assert manager.get_calls == []


@pytest.mark.asyncio
async def test_p3_issue_preflight_cannot_admit_after_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    original = composition.prepare_mutation_confirmation

    async def blocked_prepare(**kwargs: object) -> PreparedP3MutationConfirmation:
        entered.set()
        await release.wait()
        return await original(**kwargs)

    monkeypatch.setattr(composition, "prepare_mutation_confirmation", blocked_prepare)
    issue_task = asyncio.create_task(
        registry.handle_p3_confirmation_issue(
            params=_mutation_params(),
            request_id="request-issue-preflight-stop",
            session_id="session-product",
        )
    )
    await entered.wait()
    await registry.stop()
    release.set()
    result = await issue_task

    assert result.ok is False
    assert cast(dict, result.payload["error"])["reason"] == (
        "PRODUCT_COMPOSITION_STOPPED"
    )
    assert registry._p3_issue_operations == {}
    assert composition.mutation_calls == []


@pytest.mark.asyncio
async def test_p3_mutation_preflight_cannot_admit_or_consume_after_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    issued = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(),
        request_id="request-mutation-preflight-issue",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])
    mutation_params = _mutation_params(confirmation_id=receipt["confirmation_id"])
    prepared = await composition.prepare_mutation_confirmation(
        operation="task.cancel",
        params=mutation_params,
        session_id="session-product",
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    original = composition.prepare_mutation_confirmation

    async def blocked_prepare(**kwargs: object) -> PreparedP3MutationConfirmation:
        entered.set()
        await release.wait()
        return await original(**kwargs)

    monkeypatch.setattr(composition, "prepare_mutation_confirmation", blocked_prepare)
    mutation_task = asyncio.create_task(
        registry.handle_p3_mutation(
            params=mutation_params,
            request_id="request-mutation-preflight-stop",
            session_id="session-product",
        )
    )
    await entered.wait()
    await registry.stop()
    release.set()
    result = await mutation_task

    assert result.ok is False
    assert cast(dict, result.payload["error"])["reason"] == (
        "PRODUCT_COMPOSITION_STOPPED"
    )
    assert registry._p3_mutation_operations == {}
    assert composition.mutation_calls == []
    owner.validate_for_forwarding(
        str(receipt["confirmation_id"]),
        prepared.binding,
        P3ConfirmationOwnerContext(
            session_id="session-product",
            correlation_id=prepared.correlation_id,
            owner_generation=registry._p3_confirmation_generation,
        ),
        now=prepared.observed_at,
    )
    assert registry._p2_routes == {}


@pytest.mark.asyncio
async def test_p2_oversized_notification_cursor_allocates_no_business_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-oversized-operation-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True

    notification = await registry.handle_p2_notification_next(
        params=_p2_params(notification_sequence=MAX_SAFE_INTEGER + 1),
        request_id="request-oversized-notification",
        session_id="session-product",
    )

    assert notification.ok is False
    assert cast(dict, notification.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
    assert registry._p2_notification_operations == {}
    assert manager.agent.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response_generation", "contiguous_cursor"),
    (
        (MAX_SAFE_INTEGER + 1, 1),
        (1, MAX_SAFE_INTEGER + 1),
    ),
)
async def test_p2_oversized_ack_cursor_allocates_no_business_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response_generation: int,
    contiguous_cursor: int,
) -> None:
    registry, _p3, manager, _pushed = _registry(tmp_path)
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="request-oversized-ack-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    history = _HistoryWriter()
    route = registry._p2_routes[("session-product", "interaction-1")]
    route.activation_lease._runtime._history_writer = history

    acknowledgement = await registry.handle_p2_presentation_ack(
        params=_p2_params(
            response_id="response-oversized",
            response_generation=response_generation,
            surface="text",
            unit_id="unit-oversized",
            contiguous_cursor=contiguous_cursor,
            presented_at=NOW,
        ),
        request_id="request-oversized-ack",
        session_id="session-product",
    )

    assert acknowledgement.ok is False
    assert cast(dict, acknowledgement.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
    assert registry._p2_ack_operations == {}
    assert manager.agent.calls == 0
    assert history.users == []
    assert history.assistants == []


@pytest.mark.asyncio
async def test_p3_capacity_recovery_rejects_evicted_exact_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    monkeypatch.setattr(registry, "_PRODUCT_OPERATION_CAPACITY", 1)
    issue_one_params = _mutation_params()
    issue_two_params = _mutation_params(
        command_id="command-cancel-2",
        correlation_id="correlation-cancel-2",
        task_id="task-2",
    )
    issue_one = await registry.handle_p3_confirmation_issue(
        params=issue_one_params,
        request_id="request-confirmation-capacity-1",
        session_id="session-product",
    )
    issue_two = await registry.handle_p3_confirmation_issue(
        params=issue_two_params,
        request_id="request-confirmation-capacity-2",
        session_id="session-product",
    )
    expired_issue = await registry.handle_p3_confirmation_issue(
        params=issue_one_params,
        request_id="request-confirmation-capacity-1",
        session_id="session-product",
    )
    receipt_one = cast(dict[str, object], issue_one.payload["result"])
    receipt_two = cast(dict[str, object], issue_two.payload["result"])
    mutation_one_params = _mutation_params(
        confirmation_id=receipt_one["confirmation_id"]
    )
    mutation_two_params = _mutation_params(
        command_id="command-cancel-2",
        correlation_id="correlation-cancel-2",
        task_id="task-2",
        confirmation_id=receipt_two["confirmation_id"],
    )
    mutation_one = await registry.handle_p3_mutation(
        params=mutation_one_params,
        request_id="request-mutation-capacity-1",
        session_id="session-product",
    )
    mutation_two = await registry.handle_p3_mutation(
        params=mutation_two_params,
        request_id="request-mutation-capacity-2",
        session_id="session-product",
    )
    expired_mutation = await registry.handle_p3_mutation(
        params=mutation_one_params,
        request_id="request-mutation-capacity-1",
        session_id="session-product",
    )

    assert issue_one.ok is True
    assert issue_two.ok is True
    assert expired_issue.ok is False
    assert cast(dict, expired_issue.payload["error"])["reason"] == (
        "PRODUCT_OPERATION_REPLAY_EXPIRED"
    )
    assert mutation_one.ok is True
    assert mutation_two.ok is True
    assert expired_mutation.ok is False
    assert cast(dict, expired_mutation.payload["error"])["reason"] == (
        "PRODUCT_OPERATION_REPLAY_EXPIRED"
    )
    assert len(composition.mutation_calls) == 2


@pytest.mark.asyncio
async def test_p3_conflict_is_not_revealed_before_reauthentication(
    tmp_path: Path,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    issued = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(),
        request_id="request-private-conflict",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])
    mutated = await registry.handle_p3_mutation(
        params=_mutation_params(confirmation_id=receipt["confirmation_id"]),
        request_id="request-private-mutation-conflict",
        session_id="session-product",
    )

    denied_issue = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(
            auth_token="invalid-token", command_id="changed-command"
        ),
        request_id="request-private-conflict",
        session_id="session-product",
    )
    denied_mutation = await registry.handle_p3_mutation(
        params=_mutation_params(
            auth_token="invalid-token",
            confirmation_id=receipt["confirmation_id"],
            task_id="changed-task",
        ),
        request_id="request-private-mutation-conflict",
        session_id="session-product",
    )

    assert issued.ok is True
    assert mutated.ok is True
    assert cast(dict, denied_issue.payload["error"])["reason"] == (
        "FORMAL_TASK_AUTHENTICATION_REQUIRED"
    )
    assert cast(dict, denied_mutation.payload["error"])["reason"] == (
        "FORMAL_TASK_AUTHENTICATION_REQUIRED"
    )
    assert len(composition.mutation_calls) == 1


@pytest.mark.asyncio
async def test_p3_product_mutation_preserves_formal_failure_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, True),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    issued = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(),
        request_id="request-confirmation-denied",
        session_id="session-product",
    )
    receipt = cast(dict[str, object], issued.payload["result"])

    async def deny_mutation(**_kwargs: object) -> P3RouteResult:
        return P3RouteResult(
            False,
            {
                "ok": False,
                "result": None,
                "error": {
                    "code": ErrorCode.PERMISSION_DENIED.value,
                    "reason": "EXECUTION_CONTEXT_SCOPE_MISMATCH",
                    "message": "formal task authority changed",
                },
            },
        )

    monkeypatch.setattr(composition, "handle", deny_mutation)
    result = await registry.handle_p3_mutation(
        params=_mutation_params(confirmation_id=receipt["confirmation_id"]),
        request_id="request-mutation-denied",
        session_id="session-product",
    )

    assert result.ok is False
    assert result.payload["error"] == {
        "code": ErrorCode.PERMISSION_DENIED.value,
        "reason": "EXECUTION_CONTEXT_SCOPE_MISMATCH",
        "message": "formal task authority changed",
    }
    assert composition.mutation_calls == []


@pytest.mark.asyncio
async def test_p3_mutation_flag_off_has_zero_composition_effect(tmp_path: Path) -> None:
    composition = _P3Composition(tmp_path)
    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(False, False, False),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=cast(object, lambda _message: None),
    )

    result = await registry.handle_p3_confirmation_issue(
        params=_mutation_params(),
        request_id="request-confirmation-off",
        session_id="session-product",
    )

    assert result.ok is False
    assert cast(dict, result.payload["error"])["reason"] == (
        "P3_CONFIRMATION_ISSUER_UNAVAILABLE"
    )
    assert composition.authority_calls == []


# --- D-069 bounded task.retry product mutation route ------------------------


def _retry_mutation_params(**changes: object) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "operation": "task.retry",
        "command_id": "command-retry-1",
        "issued_at": NOW,
        "correlation_id": "correlation-retry-1",
        "task_id": "task-1",
    }
    params.update(changes)
    return params


def _mutation_registry(
    tmp_path: Path,
) -> tuple[
    AgentServerProductCompositionRegistry,
    _MutationP3Composition,
    BoundedP3ConfirmationOwner,
]:
    owner = BoundedP3ConfirmationOwner(tmp_path / "confirmations.sqlite3", enabled=True)
    forwarder = ProductP3ConfirmationForwarder(owner)
    composition = _MutationP3Composition(tmp_path, forwarder)

    async def push(_message: dict[str, object]) -> bool:
        return True

    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(
            p2_enabled=False,
            p3_text_enabled=False,
            p3_mutation_enabled=True,
        ),
        p3_composition=composition,
        agent_manager=_AgentManager(),
        push_text_event=push,
        p3_confirmation_owner=owner,
        p3_confirmation_forwarder=forwarder,
    )
    return registry, composition, owner


@pytest.mark.asyncio
async def test_product_retry_mutation_issues_and_forwards_one_exact_target(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)

    issued = await registry.handle_p3_confirmation_issue(
        params=_retry_mutation_params(),
        request_id="request-retry-confirmation",
        session_id="session-product",
    )
    assert issued.ok is True, issued.payload
    receipt = cast(dict[str, object], issued.payload["result"])
    assert receipt["operation"] == "task.retry"
    assert receipt["command_id"] == "command-retry-1"
    assert receipt["target_task_id"] == "task-1"

    mutated = await registry.handle_p3_mutation(
        params=_retry_mutation_params(
            confirmation_id=cast(str, receipt["confirmation_id"])
        ),
        request_id="request-retry-mutation",
        session_id="session-product",
    )
    assert mutated.ok is True, mutated.payload
    result = cast(dict[str, object], mutated.payload["result"])
    assert result["status"] == "mutation_processed"
    assert result["operation"] == "task.retry"
    assert result["target_task_id"] == "task-1"

    # The registry forwards the operation verbatim and never invents lineage.
    assert [operation for operation, _ in composition.mutation_calls] == ["task.retry"]
    forwarded = composition.mutation_calls[0][1]
    assert "operation" not in forwarded
    assert forwarded["task_id"] == "task-1"
    assert "previous_attempt_id" not in forwarded
    assert "attempt_number" not in forwarded


@pytest.mark.asyncio
async def test_product_retry_rejects_extra_missing_or_unknown_mutation_fields(
    tmp_path: Path,
) -> None:
    registry, composition, _owner = _mutation_registry(tmp_path)

    # A bounded retry carries no voice-committed origin and no create content.
    for extra in (
        {"source": "voice"},
        {"source": "structured"},
        {"name": "renamed"},
        {"instruction": "replaced"},
        {"model_intent": "default"},
        {"interaction_id": "interaction-1"},
        {"previous_attempt_id": "attempt-client-declared"},
        {"attempt_number": 2},
    ):
        rejected = await registry.handle_p3_confirmation_issue(
            params=_retry_mutation_params(**extra),
            request_id=f"request-retry-extra-{next(iter(extra))}",
            session_id="session-product",
        )
        assert rejected.ok is False, extra
        assert cast(dict, rejected.payload["error"])["reason"] == (
            "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
        ), extra

    # The exact target task is mandatory.
    without_target = _retry_mutation_params()
    without_target.pop("task_id")
    missing = await registry.handle_p3_confirmation_issue(
        params=without_target,
        request_id="request-retry-missing-target",
        session_id="session-product",
    )
    assert missing.ok is False
    assert cast(dict, missing.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )

    # An unnegotiated same-task operation still fails closed.
    unsupported = await registry.handle_p3_confirmation_issue(
        params=_retry_mutation_params(operation="task.resume"),
        request_id="request-retry-unsupported",
        session_id="session-product",
    )
    assert unsupported.ok is False
    assert cast(dict, unsupported.payload["error"])["reason"] == (
        "INVALID_P3_CONFIRMATION_OPERATION"
    )

    # Nothing above ever reached the mutation route.
    assert composition.mutation_calls == []


def _create_mutation_params(**changes: object) -> dict[str, object]:
    params: dict[str, object] = {
        "auth_token": "trusted-token",
        "session_id": "session-product",
        "operation": "task.create",
        "command_id": "command-create-1",
        "issued_at": NOW,
        "correlation_id": "correlation-create-1",
        "name": "Formal project task",
        "instruction": "Create one bounded project change.",
    }
    params.update(changes)
    return params


@pytest.mark.asyncio
async def test_every_p3_mutation_rejects_missing_required_fields_fail_closed(
    tmp_path: Path,
) -> None:
    """A missing required field is one stable rejection, never a stray lookup.

    ``_require_exact_params`` only rejects non-string or unknown keys, so each
    P3 mutation additionally proves its required fields are present.  Without
    that proof a missing ``task_id`` escaped as an unhandled ``KeyError`` from
    the downstream confirmation preparation instead of failing closed.
    """

    registry, composition, owner = _mutation_registry(tmp_path)

    cancel_without_target = _mutation_params()
    cancel_without_target.pop("task_id")
    create_without_name = _create_mutation_params()
    create_without_name.pop("name")
    create_without_instruction = _create_mutation_params()
    create_without_instruction.pop("instruction")
    retry_without_target = _retry_mutation_params()
    retry_without_target.pop("task_id")

    for label, params in (
        ("task.cancel missing task_id", cancel_without_target),
        ("task.create missing name", create_without_name),
        ("task.create missing instruction", create_without_instruction),
        ("task.retry missing task_id", retry_without_target),
    ):
        issued = await registry.handle_p3_confirmation_issue(
            params=params,
            request_id=f"request-issue-{label.replace(' ', '-')}",
            session_id="session-product",
        )
        assert issued.ok is False, label
        error = cast(dict, issued.payload["error"])
        assert error["reason"] == "INVALID_PRODUCT_COMPOSITION_ARGUMENT", label
        assert error["code"] == "INVALID_ARGUMENT", label

    # ``mutate`` additionally requires the confirmation it must forward.
    mutate_without_confirmation = _retry_mutation_params()
    mutated = await registry.handle_p3_mutation(
        params=mutate_without_confirmation,
        request_id="request-mutate-missing-confirmation",
        session_id="session-product",
    )
    assert mutated.ok is False
    mutate_error = cast(dict, mutated.payload["error"])
    assert mutate_error["reason"] == "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    assert mutate_error["code"] == "INVALID_ARGUMENT"

    # None of the rejections reached authority resolution, the confirmation
    # forwarder or the mutation route, and none consumed a confirmation.
    assert composition.prepare_calls == []
    assert composition.mutation_calls == []
    assert composition.authority_calls == []
    assert owner.raw_verifier is not None
    with sqlite3.connect(tmp_path / "confirmations.sqlite3") as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM p3_confirmations").fetchone()[0]
            == 0
        )


@pytest.mark.asyncio
async def test_missing_bearer_stays_an_authentication_failure_for_every_mutation(
    tmp_path: Path,
) -> None:
    """A missing bearer is an authentication fact, not a structural one.

    ``auth_token`` remains an allowed field and is deliberately excluded from
    the structural required-field check, so the existing authenticator keeps
    classifying it.  Folding it into the argument check would have silently
    reclassified every unauthenticated create/cancel/retry.
    """

    registry, composition, owner = _mutation_registry(tmp_path)

    for label, builder in (
        ("task.create", _create_mutation_params),
        ("task.cancel", _mutation_params),
        ("task.retry", _retry_mutation_params),
    ):
        without_bearer = builder()
        without_bearer.pop("auth_token")

        issued = await registry.handle_p3_confirmation_issue(
            params=without_bearer,
            request_id=f"request-issue-no-bearer-{label}",
            session_id="session-product",
        )
        assert issued.ok is False, label
        issue_error = cast(dict, issued.payload["error"])
        assert issue_error["reason"] == "FORMAL_TASK_AUTHENTICATION_REQUIRED", label
        assert issue_error["code"] == "UNAUTHENTICATED", label

        mutate_without_bearer = dict(without_bearer)
        mutate_without_bearer["confirmation_id"] = "confirmation-never-issued"
        mutated = await registry.handle_p3_mutation(
            params=mutate_without_bearer,
            request_id=f"request-mutate-no-bearer-{label}",
            session_id="session-product",
        )
        assert mutated.ok is False, label
        mutate_error = cast(dict, mutated.payload["error"])
        assert mutate_error["reason"] == "FORMAL_TASK_AUTHENTICATION_REQUIRED", label
        assert mutate_error["code"] == "UNAUTHENTICATED", label

    # No rejection reached the mutation route or consumed a confirmation, and
    # the remaining required-field checks are untouched for every operation.
    assert composition.mutation_calls == []
    assert composition.authority_calls == []
    with sqlite3.connect(tmp_path / "confirmations.sqlite3") as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM p3_confirmations").fetchone()[0]
            == 0
        )
    still_structural = _retry_mutation_params()
    still_structural.pop("task_id")
    structural = await registry.handle_p3_confirmation_issue(
        params=still_structural,
        request_id="request-issue-still-structural",
        session_id="session-product",
    )
    assert structural.ok is False
    assert cast(dict, structural.payload["error"])["reason"] == (
        "INVALID_PRODUCT_COMPOSITION_ARGUMENT"
    )
