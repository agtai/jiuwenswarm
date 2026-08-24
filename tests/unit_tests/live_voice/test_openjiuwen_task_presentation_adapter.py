# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CommandEnvelope,
    ResponseRef,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.agent_conversation_runtime import (
    PresentationAckResult,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    PersistentTaskEvent,
    TaskAuthorizationGrant,
    TaskUnreadPage,
)
from jiuwenswarm.server.live_voice.openjiuwen_task_facade import (
    OpenJiuwenTaskCursor,
    OpenJiuwenTaskEvent,
    OpenJiuwenTaskFacade,
    OpenJiuwenTaskUnreadPage,
    derive_openjiuwen_scope_binding,
)
from jiuwenswarm.server.live_voice.openjiuwen_task_presentation_adapter import (
    OpenJiuwenTaskPresentationAdapterError,
    OpenJiuwenTaskPresentationCursorAdapter,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    PresentationAck,
    PresentationSurface,
    TaskPresentationConsumptionOwner,
    TaskPresentationRuntimeReceipt,
    TaskPresentationViolation,
    TextPresentationAdoptionAck,
)
from jiuwenswarm.server.live_voice.product_authority import (
    AuthorityResourceBinding,
    ResolvedProductAuthority,
)

SCOPE = ScopeRef("principal-1", "project-1", "session-1", Assurance.AUTHENTICATED)
OTHER_SCOPE = ScopeRef("principal-2", "project-2", "session-2", Assurance.AUTHENTICATED)
TASK = "task-1"
ATTEMPT = "attempt-1"
RESPONSE = ResponseRef("interaction-1", "response-1", 1)
NOW = "2030-01-01T00:00:00Z"
EXPIRY = "2035-01-01T00:00:00Z"
PAYLOAD = "{}"
PAYLOAD_DIGEST = hashlib.sha256(PAYLOAD.encode()).hexdigest()


class _RuntimeAuthority:
    def __init__(self) -> None:
        self.active = True

    def __call__(
        self,
        response: ResponseRef,
        reservation_id: str | None,
        phase: str,
    ) -> TaskPresentationRuntimeReceipt:
        expected = "runtime-reservation-1"
        if phase == "reserve":
            if not self.active or reservation_id is not None:
                raise TaskPresentationViolation("STALE_RUNTIME", "stale")
            return TaskPresentationRuntimeReceipt(response, expected, phase, True)
        if phase == "close":
            if reservation_id != expected or self.active:
                raise TaskPresentationViolation("STALE_RUNTIME", "stale")
            return TaskPresentationRuntimeReceipt(response, expected, phase, False)
        if reservation_id != expected or not self.active:
            raise TaskPresentationViolation("STALE_RUNTIME", "stale")
        return TaskPresentationRuntimeReceipt(response, expected, phase, True)

    def close(self) -> None:
        self.active = False


class _Handle:
    def __init__(self, scope: ScopeRef = SCOPE) -> None:
        self.binding = derive_openjiuwen_scope_binding(scope)
        self.executor_authority = False
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.cursors: dict[str, SimpleNamespace] = {}
        self.receipts: dict[str, SimpleNamespace] = {}

    async def get(self, *_args, **_kwargs):
        return None

    async def list(self, *_args, **_kwargs):
        return ()

    async def read_events(self, *_args, **_kwargs):
        return SimpleNamespace(head_sequence=0, events=())

    async def read_unread(self, *_args, **_kwargs):
        return None

    def _cursor(self, channel: str) -> SimpleNamespace:
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

    async def advance_cursor(self, *args, **facts):
        self.calls.append(("advance_cursor", args, facts))
        advance_id = args[3]
        prior = self.receipts.get(advance_id)
        if prior is not None:
            return SimpleNamespace(
                ok=True,
                reason="",
                advance_id=advance_id,
                replayed=True,
                advanced=prior.advanced,
                cursor=prior.cursor,
            )
        channel = args[2]
        cursor = self._cursor(channel)
        if (
            cursor.sequence != facts["expected_cursor_sequence"]
            or cursor.version != facts["expected_cursor_version"]
        ):
            return SimpleNamespace(
                ok=False,
                reason="stale",
                advance_id=None,
                replayed=False,
                advanced=False,
                cursor=None,
            )
        cursor = SimpleNamespace(
            team_name=self.binding.team_name,
            stream_id=TASK,
            consumer_id=self.binding.consumer_id,
            channel=channel,
            sequence=facts["acknowledged_sequence"],
            version=cursor.version + 1,
            event_id=facts["acknowledged_event_id"],
            event_payload_digest=facts["acknowledged_event_payload_digest"],
            updated_at=2,
        )
        self.cursors[channel] = cursor
        result = SimpleNamespace(
            ok=True,
            reason="",
            advance_id=advance_id,
            replayed=False,
            advanced=True,
            cursor=cursor,
        )
        self.receipts[advance_id] = result
        return result


class _CommitThenFailHandle(_Handle):
    def __init__(self) -> None:
        super().__init__()
        self.fail_once = True

    async def advance_cursor(self, *args, **facts):
        result = await super().advance_cursor(*args, **facts)
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("response lost after commit")
        return result


class _BlockingHandle(_Handle):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def advance_cursor(self, *args, **facts):
        self.started.set()
        await self.release.wait()
        return await super().advance_cursor(*args, **facts)


class _CommitThenBlockHandle(_Handle):
    def __init__(self) -> None:
        super().__init__()
        self.committed = asyncio.Event()
        self.release = asyncio.Event()

    async def advance_cursor(self, *args, **facts):
        result = await super().advance_cursor(*args, **facts)
        self.committed.set()
        await self.release.wait()
        return result


def _facade(handle: _Handle | None = None) -> tuple[OpenJiuwenTaskFacade, _Handle]:
    handle = handle or _Handle()
    return (
        OpenJiuwenTaskFacade(
            handle,
            SCOPE,
            clock=lambda: datetime(2030, 1, 1, tzinfo=UTC),
        ),
        handle,
    )


def _authority(
    *, scope: ScopeRef = SCOPE, expires_at: str = EXPIRY
) -> ResolvedProductAuthority:
    return ResolvedProductAuthority(
        principal_id=scope.subject_id,
        session_id=scope.session_id,
        project_id=scope.project_id,
        scope=scope,
        operation="task.ack_events",
        capabilities=frozenset({"task.ack_events"}),
        expires_at=expires_at,
        assurance=Assurance.AUTHENTICATED,
        source="server.auth.session",
        correlation_id="correlation-ack",
        resource=AuthorityResourceBinding(
            "task",
            TASK,
            hashlib.sha256(TASK.encode()).hexdigest(),
        ),
        confirmation=None,
    )


def _legacy_page(channel: str, *, head_seq: int = 0) -> TaskUnreadPage:
    event = PersistentTaskEvent(
        event_id="event-1",
        task_id=TASK,
        attempt_id=ATTEMPT,
        scope=SCOPE,
        seq=0,
        event_type="task.running",
        state="running",
        outcome=None,
        producer="task_core",
        source_event_id="executor-event-1",
        causation_id="command-1",
        correlation_id="correlation-1",
        occurred_at="2029-12-31T23:59:59Z",
        details={},
    )
    return TaskUnreadPage(
        task_id=TASK,
        presentation_class=channel,
        watermark=-1,
        acked_event_id=None,
        head_seq=head_seq,
        events=(event,),
        next_after_seq=0 if head_seq > 0 else None,
        has_more=head_seq > 0,
    )


def _agentcore_page(channel: str) -> OpenJiuwenTaskUnreadPage:
    binding = derive_openjiuwen_scope_binding(SCOPE)
    event = OpenJiuwenTaskEvent(
        task_id=TASK,
        sequence=1,
        event_id="event-1",
        event_type="task.execution_admitted",
        schema_version=1,
        producer="task.execution",
        causation_id=ATTEMPT,
        correlation_id=TASK,
        payload_json=PAYLOAD,
        payload_digest=PAYLOAD_DIGEST,
        occurred_at=1,
        execution_id=ATTEMPT,
        execution_version=1,
    )
    return OpenJiuwenTaskUnreadPage(
        cursor=OpenJiuwenTaskCursor(
            task_id=TASK,
            consumer_id=binding.consumer_id,
            channel=channel,
            sequence=0,
            version=0,
            event_id=None,
            event_payload_digest=None,
            updated_at=None,
        ),
        head_sequence=1,
        events=(event,),
        next_after_sequence=None,
        has_more=False,
    )


def _owner(channel: str, *, head_seq: int = 0):
    runtime = _RuntimeAuthority()
    owner = TaskPresentationConsumptionOwner(runtime)
    delivery = owner.reserve_next(
        _legacy_page(channel, head_seq=head_seq),
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id=f"delivery-{channel}",
        unit_id=f"unit-{channel}",
    )
    return owner, delivery, runtime


def _command(delivery, *, command_id: str = "advance-1"):
    command = CommandEnvelope.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "request_id": f"request-{command_id}",
            "command_id": command_id,
            "command_type": "task.ack_events",
            "issued_at": NOW,
            "scope": SCOPE.to_dict(),
            "correlation_id": "correlation-ack",
            "causation_id": delivery.event_id,
            "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
            "target_ref": {"kind": "task", "id": TASK},
            "context_refs": [],
            "required_capabilities": ["task.ack_events"],
            "payload": {
                "presentation_class": delivery.presentation_class,
                "acked_through_seq": delivery.event_seq,
                "acked_event_id": delivery.event_id,
                "expected_event_head": delivery.expected_event_head,
            },
            "extensions": {},
        }
    )
    grant = TaskAuthorizationGrant(
        principal_id=SCOPE.subject_id,
        scope=SCOPE,
        operation="task.ack_events",
        command_id=command.command_id,
        target_task_id=TASK,
        allowed_capabilities=frozenset({"task.ack_events"}),
        confirmation_id=None,
        confirmed=False,
        expires_at=EXPIRY,
        policy_bypass="server_task_presentation_v1",
    )
    return command, grant


def _adopt_text(owner, delivery) -> None:
    assert owner.mark_text_adopted(
        TextPresentationAdoptionAck.from_delivery(
            delivery,
            adopted_at="2030-01-01T00:00:01Z",
        )
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_text_dom_ack_advances_exact_cursor_and_replays() -> None:
    facade, handle = _facade()
    adapter = OpenJiuwenTaskPresentationCursorAdapter(facade)
    owner, delivery, _runtime = _owner("text")
    command, grant = _command(delivery)

    with pytest.raises(TaskPresentationViolation) as missing_ack:
        await adapter.consume(
            owner,
            delivery,
            command,
            grant,
            _authority(),
            _agentcore_page("text"),
            observed_at=NOW,
        )
    assert missing_ack.value.reason == "PRESENTATION_ACK_REQUIRED"
    assert handle.calls == []

    _adopt_text(owner, delivery)
    first = await adapter.consume(
        owner,
        delivery,
        command,
        grant,
        _authority(),
        _agentcore_page("text"),
        observed_at=NOW,
    )
    replay = await adapter.consume(
        owner,
        delivery,
        command,
        grant,
        _authority(),
        _agentcore_page("text"),
        observed_at=NOW,
    )

    assert first.ok and replay.ok
    assert first.result is not None and first.result["advanced"] is True
    assert replay.result is not None and replay.result["replayed"] is True
    assert handle.cursors["text"].sequence == 1
    assert len(handle.calls) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_voice_runtime_ack_advances_only_voice_channel() -> None:
    facade, handle = _facade()
    adapter = OpenJiuwenTaskPresentationCursorAdapter(facade)
    owner, delivery, _runtime = _owner("voice")
    ack = PresentationAck(
        ref=RESPONSE,
        surface=PresentationSurface.AUDIO,
        unit_id=delivery.unit_id,
        contiguous_cursor=0,
        presented_at="2030-01-01T00:00:01Z",
    )

    async def runtime_ack(value: PresentationAck) -> PresentationAckResult:
        return PresentationAckResult(value, True, False, 0, False)

    assert await owner.mark_voice_presented(delivery, ack, runtime_ack)
    command, grant = _command(delivery, command_id="advance-voice")
    result = await adapter.consume(
        owner,
        delivery,
        command,
        grant,
        _authority(),
        _agentcore_page("voice"),
        observed_at=NOW,
    )

    assert result.ok
    assert handle.cursors["voice"].sequence == 1
    assert handle._cursor("text").sequence == 0


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda page, _delivery: replace(
                page,
                events=(replace(page.events[0], payload_digest="0" * 64),),
            ),
            "INVALID_AGENTCORE_EVENT_PAYLOAD",
        ),
        (
            lambda page, _delivery: replace(
                page,
                events=(replace(page.events[0], schema_version=True),),
            ),
            "INVALID_AGENTCORE_EVENT",
        ),
        (
            lambda page, _delivery: replace(
                page,
                events=(replace(page.events[0], occurred_at=True),),
            ),
            "INVALID_EVENT_OCCURRED_AT",
        ),
        (
            lambda page, _delivery: replace(
                page,
                events=(
                    replace(
                        page.events[0],
                        payload_json='{"value":NaN}',
                        payload_digest=hashlib.sha256(b'{"value":NaN}').hexdigest(),
                    ),
                ),
            ),
            "INVALID_AGENTCORE_EVENT_PAYLOAD",
        ),
        (
            lambda page, _delivery: replace(
                page,
                events=(replace(page.events[0], event_id="e" * 256),),
            ),
            "INVALID_EVENT_ID",
        ),
        (
            lambda page, _delivery: replace(
                page,
                cursor=replace(page.cursor, channel="voice"),
            ),
            "AGENTCORE_CURSOR_BINDING_MISMATCH",
        ),
        (
            lambda page, _delivery: replace(
                page,
                head_sequence=2,
                has_more=True,
                next_after_sequence=None,
            ),
            "INVALID_AGENTCORE_UNREAD_PAGE",
        ),
        (
            lambda page, _delivery: replace(
                page,
                events=(
                    page.events[0],
                    replace(page.events[0], sequence=2, event_id="event-2"),
                ),
            ),
            "INVALID_AGENTCORE_UNREAD_PAGE",
        ),
        (
            lambda page, _delivery: replace(
                page,
                next_after_sequence=True,
            ),
            "INVALID_NEXT_AFTER_SEQUENCE",
        ),
        (
            lambda page, delivery: replace(
                page,
                events=(
                    replace(
                        page.events[0], execution_id=delivery.attempt_id + "-other"
                    ),
                ),
            ),
            "PRESENTATION_EVENT_BINDING_MISMATCH",
        ),
    ],
)
async def test_malformed_unread_binding_has_zero_cursor_call(mutation, reason) -> None:
    facade, handle = _facade()
    adapter = OpenJiuwenTaskPresentationCursorAdapter(facade)
    owner, delivery, _runtime = _owner("text")
    _adopt_text(owner, delivery)
    command, grant = _command(delivery)

    with pytest.raises(OpenJiuwenTaskPresentationAdapterError) as rejected:
        await adapter.consume(
            owner,
            delivery,
            command,
            grant,
            _authority(),
            mutation(_agentcore_page("text"), delivery),
            observed_at=NOW,
        )
    assert rejected.value.reason == reason
    assert handle.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_foreign_or_expired_authority_has_zero_cursor_call() -> None:
    facade, handle = _facade()
    adapter = OpenJiuwenTaskPresentationCursorAdapter(facade)
    owner, delivery, _runtime = _owner("text")
    _adopt_text(owner, delivery)
    command, grant = _command(delivery)

    for authority, reason in (
        (_authority(scope=OTHER_SCOPE), "PRESENTATION_CURSOR_AUTHORITY_MISMATCH"),
        (
            _authority(expires_at="2029-01-01T00:00:00Z"),
            "PRESENTATION_CURSOR_AUTHORIZATION_MISMATCH",
        ),
    ):
        with pytest.raises(OpenJiuwenTaskPresentationAdapterError) as rejected:
            await adapter.consume(
                owner,
                delivery,
                command,
                grant,
                authority,
                _agentcore_page("text"),
                observed_at=NOW,
            )
        assert rejected.value.reason == reason
    assert handle.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_default_limit_page_with_larger_backlog_remains_consumable() -> None:
    facade, handle = _facade()
    adapter = OpenJiuwenTaskPresentationCursorAdapter(facade)
    owner, delivery, _runtime = _owner("text", head_seq=100)
    _adopt_text(owner, delivery)
    command, grant = _command(delivery, command_id="advance-default-page")
    initial = _agentcore_page("text")
    events = tuple(
        replace(initial.events[0], sequence=sequence, event_id=f"event-{sequence}")
        for sequence in range(1, 101)
    )
    page = replace(
        initial,
        head_sequence=101,
        events=events,
        next_after_sequence=100,
        has_more=True,
    )

    result = await adapter.consume(
        owner,
        delivery,
        command,
        grant,
        _authority(),
        page,
        observed_at=NOW,
    )

    assert result.ok
    assert handle.cursors["text"].sequence == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_commit_before_response_loss_retries_as_agentcore_replay() -> None:
    handle = _CommitThenFailHandle()
    facade, _ = _facade(handle)
    adapter = OpenJiuwenTaskPresentationCursorAdapter(facade)
    owner, delivery, _runtime = _owner("text")
    _adopt_text(owner, delivery)
    command, grant = _command(delivery, command_id="advance-response-loss")
    args = (
        owner,
        delivery,
        command,
        grant,
        _authority(),
        _agentcore_page("text"),
    )

    with pytest.raises(OpenJiuwenTaskPresentationAdapterError) as lost:
        await adapter.consume(*args, observed_at=NOW)
    assert lost.value.reason == "AGENTCORE_CURSOR_ADVANCE_FAILED"
    assert handle.cursors["text"].sequence == 1

    replay = await adapter.consume(*args, observed_at=NOW)
    assert replay.ok and replay.result is not None
    assert replay.result["replayed"] is True
    assert handle.cursors["text"].version == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_caller_cancellation_propagates_without_cursor_advance() -> None:
    handle = _BlockingHandle()
    facade, _ = _facade(handle)
    adapter = OpenJiuwenTaskPresentationCursorAdapter(facade)
    owner, delivery, _runtime = _owner("text")
    _adopt_text(owner, delivery)
    command, grant = _command(delivery, command_id="advance-cancelled")
    task = asyncio.create_task(
        adapter.consume(
            owner,
            delivery,
            command,
            grant,
            _authority(),
            _agentcore_page("text"),
            observed_at=NOW,
        )
    )
    await handle.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert handle.cursors == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_before_async_consume_fences_cursor_call() -> None:
    facade, handle = _facade()
    adapter = OpenJiuwenTaskPresentationCursorAdapter(facade)
    owner, delivery, runtime = _owner("text")
    _adopt_text(owner, delivery)
    command, grant = _command(delivery, command_id="advance-after-close")
    runtime.close()
    assert (
        owner.close_response(
            RESPONSE,
            reservation_id=delivery.runtime_reservation_id,
            reason="response_closed",
        )
        == 1
    )

    with pytest.raises(TaskPresentationViolation) as closed:
        await adapter.consume(
            owner,
            delivery,
            command,
            grant,
            _authority(),
            _agentcore_page("text"),
            observed_at=NOW,
        )
    assert closed.value.reason == "PRESENTATION_DELIVERY_NOT_FOUND"
    assert handle.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_consume_start_wins_over_later_response_close() -> None:
    handle = _BlockingHandle()
    facade, _ = _facade(handle)
    adapter = OpenJiuwenTaskPresentationCursorAdapter(facade)
    owner, delivery, runtime = _owner("text")
    _adopt_text(owner, delivery)
    command, grant = _command(delivery, command_id="advance-before-close")
    task = asyncio.create_task(
        adapter.consume(
            owner,
            delivery,
            command,
            grant,
            _authority(),
            _agentcore_page("text"),
            observed_at=NOW,
        )
    )
    await handle.started.wait()
    runtime.close()
    assert (
        owner.close_response(
            RESPONSE,
            reservation_id=delivery.runtime_reservation_id,
            reason="response_closed",
        )
        == 1
    )
    handle.release.set()
    result = await task
    assert result.ok
    assert handle.cursors["text"].sequence == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_after_commit_is_unknown_then_exact_retry_replays() -> None:
    handle = _CommitThenBlockHandle()
    facade, _ = _facade(handle)
    adapter = OpenJiuwenTaskPresentationCursorAdapter(facade)
    owner, delivery, _runtime = _owner("text")
    _adopt_text(owner, delivery)
    command, grant = _command(delivery, command_id="advance-cancel-after-commit")
    args = (
        owner,
        delivery,
        command,
        grant,
        _authority(),
        _agentcore_page("text"),
    )
    task = asyncio.create_task(adapter.consume(*args, observed_at=NOW))
    await handle.committed.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert handle.cursors["text"].sequence == 1
    assert handle.cursors["text"].version == 1

    handle.release.set()
    replay = await adapter.consume(*args, observed_at=NOW)
    assert replay.ok and replay.result is not None
    assert replay.result["replayed"] is True
    assert handle.cursors["text"].version == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrent_same_command_is_one_advance_plus_replay() -> None:
    facade, handle = _facade()
    adapter = OpenJiuwenTaskPresentationCursorAdapter(facade)
    owner, delivery, _runtime = _owner("text")
    _adopt_text(owner, delivery)
    command, grant = _command(delivery, command_id="advance-concurrent")
    args = (
        owner,
        delivery,
        command,
        grant,
        _authority(),
        _agentcore_page("text"),
    )

    results = await asyncio.gather(
        adapter.consume(*args, observed_at=NOW),
        adapter.consume(*args, observed_at=NOW),
    )
    assert all(result.ok for result in results)
    facts = [result.result for result in results]
    assert sum(item["replayed"] is True for item in facts if item is not None) == 1
    assert handle.cursors["text"].version == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_consumption_does_not_rebind_delivery_to_another_command() -> None:
    handle = _BlockingHandle()
    facade, _ = _facade(handle)
    adapter = OpenJiuwenTaskPresentationCursorAdapter(facade)
    owner, delivery, _runtime = _owner("text")
    _adopt_text(owner, delivery)
    first_command, first_grant = _command(delivery, command_id="advance-first")
    second_command, second_grant = _command(delivery, command_id="advance-second")
    first = asyncio.create_task(
        adapter.consume(
            owner,
            delivery,
            first_command,
            first_grant,
            _authority(),
            _agentcore_page("text"),
            observed_at=NOW,
        )
    )
    await handle.started.wait()

    with pytest.raises(TaskPresentationViolation) as rebound:
        await adapter.consume(
            owner,
            delivery,
            second_command,
            second_grant,
            _authority(),
            _agentcore_page("text"),
            observed_at=NOW,
        )
    assert rebound.value.reason == "CONSUMPTION_COMMAND_REWRITE"
    assert len(handle.calls) == 0

    handle.release.set()
    assert (await first).ok
    assert len(handle.calls) == 1


@pytest.mark.unit
def test_adapter_is_default_off_and_requires_exact_facade() -> None:
    with pytest.raises(ValueError):
        OpenJiuwenTaskPresentationCursorAdapter(object())
