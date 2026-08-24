# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.openjiuwen_task_facade import (
    OpenJiuwenTaskFacade,
    OpenJiuwenTaskFacadeError,
    derive_openjiuwen_scope_binding,
)
from jiuwenswarm.server.live_voice.product_authority import (
    AuthorityResourceBinding,
    ResolvedProductAuthority,
)

SCOPE = ScopeRef("principal-1", "project-1", "session-1", Assurance.AUTHENTICATED)
OTHER_SCOPE = ScopeRef("principal-2", "project-2", "session-2", Assurance.AUTHENTICATED)
TASK = "task-1"
NOW = datetime(2030, 1, 1, tzinfo=UTC)
EXPIRY = "2035-01-01T00:00:00Z"
PAST = "2025-01-01T00:00:00Z"
DIGEST = hashlib.sha256(b"{}").hexdigest()


def _resource(task_id: str) -> AuthorityResourceBinding:
    return AuthorityResourceBinding(
        "task",
        task_id,
        hashlib.sha256(task_id.encode("utf-8")).hexdigest(),
    )


def _authority(
    operation: str,
    *,
    task_id: str | None = TASK,
    scope: ScopeRef = SCOPE,
    expires_at: str = EXPIRY,
) -> ResolvedProductAuthority:
    return ResolvedProductAuthority(
        principal_id=scope.subject_id,
        session_id=scope.session_id,
        project_id=scope.project_id,
        scope=scope,
        operation=operation,
        capabilities=frozenset({operation}),
        expires_at=expires_at,
        assurance=Assurance.AUTHENTICATED,
        source="server.auth.session",
        correlation_id="correlation-1",
        resource=None if task_id is None else _resource(task_id),
        confirmation=None,
    )


def _event(*, binding, sequence: int = 1):
    payload = "{}"
    return SimpleNamespace(
        team_name=binding.team_name,
        stream_id=TASK,
        sequence=sequence,
        event_id=f"event-{sequence}",
        event_type=SimpleNamespace(value="task.created"),
        schema_version=1,
        producer="task.create",
        causation_id=TASK,
        correlation_id=TASK,
        payload_json=payload,
        payload_digest=hashlib.sha256(payload.encode()).hexdigest(),
        occurred_at=sequence,
        execution_id=None,
        execution_version=None,
    )


def _task(*, binding, status: str = "pending", head: int = 1):
    return SimpleNamespace(
        team_name=binding.team_name,
        task_id=TASK,
        title="title",
        content="content",
        status=status,
        assignee=binding.member_name,
        current_execution_id=None,
        execution_version=0,
        event_head=head,
        updated_at=1,
    )


def _snapshot(*, binding):
    return SimpleNamespace(
        task=_task(binding=binding),
        execution=None,
        executor_authority=False,
    )


def _completed_snapshot(*, binding):
    task = _task(binding=binding, status="completed")
    task.current_execution_id = "execution-1"
    task.execution_version = 2
    result = SimpleNamespace(
        result_id="result-1",
        digest=hashlib.sha256(b"result").hexdigest(),
        locator="opaque/result-1",
    )
    execution = SimpleNamespace(
        team_name=binding.team_name,
        task_id=TASK,
        execution_id="execution-1",
        profile_digest=hashlib.sha256(b"profile").hexdigest(),
        generation=1,
        owner_id=None,
        owner_epoch=None,
        disposition="completed",
        execution_version=2,
        checkpoint_head=1,
        outcome="completed",
        result_ref=result,
    )
    return SimpleNamespace(
        task=task,
        execution=execution,
        executor_authority=False,
    )


class _Handle:
    def __init__(self, scope: ScopeRef = SCOPE) -> None:
        self.binding = derive_openjiuwen_scope_binding(scope)
        self.executor_authority = False
        self.calls: list[tuple[str, tuple, dict]] = []
        self.snapshot = _snapshot(binding=self.binding)
        self.event = _event(binding=self.binding)
        self.cursors: dict[str, SimpleNamespace] = {}
        self.advances: dict[str, SimpleNamespace] = {}
        self.failure: Exception | None = None
        self.get_override: object | None = None
        self.events_override: object | None = None

    def _record(self, name: str, *args, **kwargs) -> None:
        self.calls.append((name, args, kwargs))
        if self.failure is not None:
            raise self.failure

    async def get(self, task_id: str):
        self._record("get", task_id)
        return self.snapshot if self.get_override is None else self.get_override

    async def list(self, *, limit: int = 100):
        self._record("list", limit=limit)
        return (self.snapshot,)

    async def read_events(
        self, task_id: str, *, after_sequence: int = 0, limit: int = 100
    ):
        self._record("read_events", task_id, after_sequence=after_sequence, limit=limit)
        if self.events_override is not None:
            return self.events_override
        events = (self.event,) if after_sequence == 0 else ()
        return SimpleNamespace(head_sequence=1, events=events)

    def _cursor(self, channel: str):
        return self.cursors.setdefault(
            channel,
            SimpleNamespace(
                team_name=self.binding.team_name,
                stream_id=TASK,
                consumer_id=self.binding.consumer_id,
                channel=channel,
                sequence=0,
                version=0,
                event_id=None,
                event_payload_digest=None,
                updated_at=None,
            ),
        )

    async def read_unread(
        self,
        task_id: str,
        consumer_id: str,
        channel: str,
        *,
        limit: int = 100,
    ):
        self._record("read_unread", task_id, consumer_id, channel, limit=limit)
        cursor = self._cursor(channel)
        events = (self.event,) if cursor.sequence == 0 else ()
        return SimpleNamespace(
            cursor=cursor,
            head_sequence=1,
            events=events,
            next_after_sequence=None,
            has_more=False,
        )

    async def advance_cursor(
        self,
        task_id: str,
        consumer_id: str,
        channel: str,
        advance_id: str,
        **facts,
    ):
        self._record(
            "advance_cursor",
            task_id,
            consumer_id,
            channel,
            advance_id,
            **facts,
        )
        replay = self.advances.get(advance_id)
        if replay is not None:
            return SimpleNamespace(
                **{**replay.__dict__, "replayed": True, "advanced": replay.advanced}
            )
        cursor = self._cursor(channel)
        acknowledged = facts["acknowledged_sequence"]
        if cursor.sequence >= acknowledged:
            advanced = False
        elif (
            cursor.sequence == facts["expected_cursor_sequence"]
            and cursor.version == facts["expected_cursor_version"]
        ):
            cursor = SimpleNamespace(
                team_name=self.binding.team_name,
                stream_id=TASK,
                consumer_id=consumer_id,
                channel=channel,
                sequence=acknowledged,
                version=cursor.version + 1,
                event_id=facts["acknowledged_event_id"],
                event_payload_digest=facts["acknowledged_event_payload_digest"],
                updated_at=2,
            )
            self.cursors[channel] = cursor
            advanced = True
        else:
            return SimpleNamespace(
                ok=False,
                reason="stale cursor",
                advance_id=None,
                replayed=False,
                advanced=False,
                cursor=None,
            )
        result = SimpleNamespace(
            ok=True,
            reason="",
            advance_id=advance_id,
            replayed=False,
            advanced=advanced,
            cursor=cursor,
        )
        self.advances[advance_id] = result
        return result


def _facade(handle: _Handle | None = None) -> tuple[OpenJiuwenTaskFacade, _Handle]:
    handle = handle or _Handle()
    return OpenJiuwenTaskFacade(handle, SCOPE, clock=lambda: NOW), handle


def _assert_reason(exc, reason: str) -> None:
    assert isinstance(exc.value, OpenJiuwenTaskFacadeError)
    assert exc.value.reason == reason
    assert str(exc.value) == "OpenJiuwen Task facade is unavailable"


@pytest.mark.unit
def test_scope_mapping_is_deterministic_isolated_and_handle_must_match() -> None:
    first = derive_openjiuwen_scope_binding(SCOPE)
    assert first == derive_openjiuwen_scope_binding(SCOPE)
    other = derive_openjiuwen_scope_binding(OTHER_SCOPE)
    assert first.session_id != other.session_id
    assert first.team_name != other.team_name
    assert first.member_name != other.member_name
    assert first.consumer_id != other.consumer_id
    assert max(map(len, (first.session_id, first.team_name, first.member_name))) < 256

    product_boundary = ScopeRef(
        "用" * 256,
        SCOPE.project_id,
        SCOPE.session_id,
        Assurance.AUTHENTICATED,
    )
    assert derive_openjiuwen_scope_binding(product_boundary).team_name
    with pytest.raises(OpenJiuwenTaskFacadeError) as oversized_product_id:
        derive_openjiuwen_scope_binding(
            replace(product_boundary, subject_id="用" * 257)
        )
    _assert_reason(oversized_product_id, "INVALID_SCOPE_SUBJECT_ID")

    with pytest.raises(OpenJiuwenTaskFacadeError) as mismatch:
        OpenJiuwenTaskFacade(_Handle(OTHER_SCOPE), SCOPE, clock=lambda: NOW)
    _assert_reason(mismatch, "AGENTCORE_BINDING_MISMATCH")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authorized_get_list_events_and_result_preserve_raw_truth() -> None:
    facade, handle = _facade()
    snapshot = await facade.get(_authority("task.get"), TASK)
    assert snapshot is not None
    assert snapshot.task.task_id == TASK
    assert snapshot.task.status == "pending"
    assert snapshot.execution is None
    assert not snapshot.executor_authority

    listed = await facade.list(_authority("task.list", task_id=None), limit=1)
    assert listed == (snapshot,)
    assert handle.calls[-1] == ("list", (), {"limit": 1})

    page = await facade.read_events(_authority("task.events"), TASK)
    assert page.head_sequence == 1
    assert page.events[0].payload_json == "{}"
    assert page.events[0].payload_digest == DIGEST

    handle.snapshot = _completed_snapshot(binding=handle.binding)
    result = await facade.read_result(_authority("task.result"), TASK)
    assert result is not None
    assert result.task_status == "completed"
    assert result.outcome == "completed"
    assert result.result_ref is not None
    assert result.result_ref.result_id == "result-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_blocked_and_unknown_canonical_states_remain_raw_facts() -> None:
    facade, handle = _facade()
    blocked = _snapshot(binding=handle.binding)
    blocked.task.status = "blocked"
    handle.snapshot = blocked
    blocked_result = await facade.get(_authority("task.get"), TASK)
    assert blocked_result is not None and blocked_result.task.status == "blocked"
    assert blocked_result.execution is None

    unknown = _completed_snapshot(binding=handle.binding)
    unknown.task.status = "unknown"
    unknown.execution.disposition = "unknown"
    unknown.execution.outcome = "unknown"
    unknown.execution.result_ref = None
    handle.snapshot = unknown
    result = await facade.read_result(_authority("task.result"), TASK)
    assert result is not None and result.task_status == "unknown"
    assert result.outcome == "unknown" and result.result_ref is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_fails_closed_before_agentcore_until_patch_is_confirmed() -> None:
    facade, handle = _facade()
    authority = _authority("task.update")
    with pytest.raises(OpenJiuwenTaskFacadeError) as unsupported:
        await facade.apply_update(
            authority,
            TASK,
            "command-1",
            expected_execution_version=0,
            expected_event_head=1,
            title="updated",
        )
    _assert_reason(unsupported, "UNSUPPORTED_AGENTCORE_OPERATION")
    assert handle.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_text_and_voice_cursors_are_independent_and_ack_replays() -> None:
    facade, handle = _facade()
    unread = _authority("task.unread_events")
    text = await facade.read_unread(unread, TASK, "text")
    voice = await facade.read_unread(unread, TASK, "voice")
    assert text is not None and voice is not None
    assert text.cursor.sequence == voice.cursor.sequence == 0
    assert text.cursor.consumer_id == facade.binding.consumer_id
    event = text.events[0]

    ack = _authority("task.ack_events")
    advanced = await facade.advance_after_presentation_ack(
        ack,
        TASK,
        "text",
        "advance-1",
        expected_cursor_sequence=0,
        expected_cursor_version=0,
        expected_head_sequence=1,
        acknowledged_sequence=event.sequence,
        acknowledged_event_id=event.event_id,
        acknowledged_event_payload_digest=event.payload_digest,
    )
    assert advanced.ok and advanced.advanced and not advanced.replayed
    replay = await facade.advance_after_presentation_ack(
        ack,
        TASK,
        "text",
        "advance-1",
        expected_cursor_sequence=0,
        expected_cursor_version=0,
        expected_head_sequence=1,
        acknowledged_sequence=event.sequence,
        acknowledged_event_id=event.event_id,
        acknowledged_event_payload_digest=event.payload_digest,
    )
    assert replay.ok and replay.replayed and replay.cursor == advanced.cursor
    assert handle.cursors["text"].sequence == 1
    assert handle.cursors["voice"].sequence == 0


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authority", "reason"),
    (
        (_authority("task.events"), "PRODUCT_OPERATION_MISMATCH"),
        (
            replace(
                _authority("task.get"),
                capabilities=frozenset({"task.get", "task.events"}),
            ),
            "PRODUCT_CAPABILITY_MISMATCH",
        ),
        (_authority("task.get", expires_at=PAST), "PRODUCT_AUTHORITY_EXPIRED"),
        (
            replace(_authority("task.get"), resource=_resource("task-2")),
            "TASK_RESOURCE_MISMATCH",
        ),
    ),
)
async def test_authority_rejections_happen_before_agentcore(
    authority: ResolvedProductAuthority,
    reason: str,
) -> None:
    facade, handle = _facade()
    with pytest.raises(OpenJiuwenTaskFacadeError) as rejected:
        await facade.get(authority, TASK)
    _assert_reason(rejected, reason)
    assert handle.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scope_mismatch_calls_nothing() -> None:
    facade, handle = _facade()
    foreign = _authority("task.get", scope=OTHER_SCOPE)
    with pytest.raises(OpenJiuwenTaskFacadeError) as scope_error:
        await facade.get(foreign, TASK)
    _assert_reason(scope_error, "PRODUCT_SCOPE_MISMATCH")

    assert handle.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unicode_and_agentcore_character_bounds_are_exact() -> None:
    facade, handle = _facade()
    unicode_task_id = "任" * 255
    handle.snapshot.task.task_id = unicode_task_id
    projected = await facade.get(
        _authority("task.get", task_id=unicode_task_id),
        unicode_task_id,
    )
    assert projected is not None and projected.task.task_id == unicode_task_id

    facade, handle = _facade()
    too_long_task_id = "x" * 256
    with pytest.raises(OpenJiuwenTaskFacadeError) as long_id:
        await facade.get(
            _authority("task.get", task_id=too_long_task_id),
            too_long_task_id,
        )
    _assert_reason(long_id, "INVALID_TASK_ID")
    assert handle.calls == []

    facade, handle = _facade()
    bounded = _completed_snapshot(binding=handle.binding)
    bounded.task.title = "界" * 65_535
    bounded.execution.result_ref.locator = "路" * 2048
    handle.snapshot = bounded
    result = await facade.read_result(_authority("task.result"), TASK)
    assert result is not None
    assert result.result_ref is not None
    assert result.result_ref.locator == "路" * 2048

    bounded.task.title += "界"
    with pytest.raises(OpenJiuwenTaskFacadeError) as long_title:
        await facade.get(_authority("task.get"), TASK)
    _assert_reason(long_title, "INVALID_TASK_TITLE")

    bounded.task.title = "title"
    bounded.execution.result_ref.locator += "路"
    with pytest.raises(OpenJiuwenTaskFacadeError) as long_locator:
        await facade.read_result(_authority("task.result"), TASK)
    _assert_reason(long_locator, "INVALID_RESULT_LOCATOR")

    facade, handle = _facade()
    fitting_payload = json.dumps(
        {"value": "界" * 5000},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    handle.event.payload_json = fitting_payload
    handle.event.payload_digest = hashlib.sha256(fitting_payload.encode()).hexdigest()
    page = await facade.read_events(_authority("task.events"), TASK)
    assert page.events[0].payload_json == fitting_payload

    oversized_payload = json.dumps(
        {"value": "界" * 5500},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    handle.event.payload_json = oversized_payload
    handle.event.payload_digest = hashlib.sha256(oversized_payload.encode()).hexdigest()
    with pytest.raises(OpenJiuwenTaskFacadeError) as oversized_event:
        await facade.read_events(_authority("task.events"), TASK)
    _assert_reason(oversized_event, "INVALID_EVENT_PAYLOAD_JSON")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_malformed_downstream_facts_never_report_success() -> None:
    facade, handle = _facade()
    wrong = _snapshot(binding=handle.binding)
    wrong.task.task_id = "task-2"
    handle.get_override = wrong
    with pytest.raises(OpenJiuwenTaskFacadeError) as wrong_task:
        await facade.get(_authority("task.get"), TASK)
    _assert_reason(wrong_task, "AGENTCORE_TASK_BINDING_MISMATCH")

    corrupt = _event(binding=handle.binding)
    corrupt.payload_digest = "0" * 64
    handle.events_override = SimpleNamespace(head_sequence=1, events=(corrupt,))
    with pytest.raises(OpenJiuwenTaskFacadeError) as corrupt_event:
        await facade.read_events(_authority("task.events"), TASK)
    _assert_reason(corrupt_event, "EVENT_PAYLOAD_DIGEST_MISMATCH")

    for nonfinite in ('{"value":NaN}', '{"value":Infinity}'):
        corrupt = _event(binding=handle.binding)
        corrupt.payload_json = nonfinite
        corrupt.payload_digest = hashlib.sha256(nonfinite.encode()).hexdigest()
        handle.events_override = SimpleNamespace(head_sequence=1, events=(corrupt,))
        with pytest.raises(OpenJiuwenTaskFacadeError) as noncanonical_number:
            await facade.read_events(_authority("task.events"), TASK)
        _assert_reason(noncanonical_number, "INVALID_EVENT_PAYLOAD_JSON")

    handle.events_override = SimpleNamespace(
        head_sequence=2,
        events=(_event(binding=handle.binding),),
    )
    with pytest.raises(OpenJiuwenTaskFacadeError) as truncated:
        await facade.read_events(_authority("task.events"), TASK)
    _assert_reason(truncated, "INCOMPLETE_EVENT_PAGE")

    async def truncated_unread(
        _task_id: str,
        _consumer_id: str,
        _channel: str,
        *,
        limit: int,
    ):
        assert limit == 100
        return SimpleNamespace(
            cursor=handle._cursor("text"),
            head_sequence=2,
            events=(_event(binding=handle.binding),),
            next_after_sequence=1,
            has_more=True,
        )

    handle.read_unread = truncated_unread
    with pytest.raises(OpenJiuwenTaskFacadeError) as truncated_cursor:
        await facade.read_unread(_authority("task.unread_events"), TASK, "text")
    _assert_reason(truncated_cursor, "INCOMPLETE_UNREAD_PAGE")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_downstream_exception_is_redacted_and_cancellation_propagates() -> None:
    facade, handle = _facade()
    handle.failure = RuntimeError("database password leaked")
    with pytest.raises(OpenJiuwenTaskFacadeError) as failed:
        await facade.get(_authority("task.get"), TASK)
    _assert_reason(failed, "AGENTCORE_AUTHORITY_FAILURE")
    assert "password" not in str(failed.value)

    started = asyncio.Event()

    async def blocked(_task_id: str):
        started.set()
        await asyncio.Event().wait()

    handle.failure = None
    handle.get = blocked
    pending = asyncio.create_task(facade.get(_authority("task.get"), TASK))
    await started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bounds_unsupported_and_handle_drift_fail_closed() -> None:
    facade, handle = _facade()
    for invalid in (True, 0, 101):
        with pytest.raises(OpenJiuwenTaskFacadeError):
            await facade.list(_authority("task.list", task_id=None), limit=invalid)
    assert handle.calls == []

    with pytest.raises(OpenJiuwenTaskFacadeError) as invalid_ack:
        await facade.advance_after_presentation_ack(
            _authority("task.ack_events"),
            TASK,
            "text",
            "invalid-advance",
            expected_cursor_sequence=0,
            expected_cursor_version=1,
            expected_head_sequence=1,
            acknowledged_sequence=1,
            acknowledged_event_id="event-1",
            acknowledged_event_payload_digest=DIGEST,
        )
    _assert_reason(invalid_ack, "INVALID_CURSOR_ADVANCE_REQUEST")
    assert handle.calls == []

    for operation in (
        "task.create",
        "task.update",
        "task.cancel",
        "task.retry",
        "task.adjust",
        "task.reprioritize",
        "task.create_successor",
    ):
        with pytest.raises(OpenJiuwenTaskFacadeError) as unsupported:
            facade.reject_unsupported(operation)
        _assert_reason(unsupported, "UNSUPPORTED_AGENTCORE_OPERATION")
    assert handle.calls == []

    handle.binding = derive_openjiuwen_scope_binding(OTHER_SCOPE)
    with pytest.raises(OpenJiuwenTaskFacadeError) as drift:
        await facade.get(_authority("task.get"), TASK)
    _assert_reason(drift, "AGENTCORE_BINDING_MISMATCH")
    assert handle.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrent_reads_share_no_mutable_facade_authority() -> None:
    facade, handle = _facade()
    authority = _authority("task.get")
    first, second = await asyncio.gather(
        facade.get(authority, TASK),
        facade.get(authority, TASK),
    )
    assert first == second
    assert len(handle.calls) == 2
    assert not facade.executor_authority


@pytest.mark.unit
def test_module_has_no_legacy_store_or_agentcore_internal_import() -> None:
    source = inspect.getsource(
        __import__(
            "jiuwenswarm.server.live_voice.openjiuwen_task_facade",
            fromlist=["*"],
        )
    )
    assert "task_store" not in source
    assert "persistent_task_core" not in source
    assert "openjiuwen.agent_teams.tools" not in source
