"""Real Store/Bridge/Arbiter regressions for independent notification owners."""

import asyncio

import pytest

from jiuwenswarm.server.live_voice.progress_notification_arbiter import ProgressNotificationArbiter
from jiuwenswarm.server.live_voice.task_progress_return import (
    TaskEventAuthorityProgressSource, TaskProgressReturnBridge,
    TaskProgressOriginKind, TaskProgressReturnState,
    DeferredVoiceOwnership,
    task_progress_presentation_allowed,
)
from tests.unit_tests.live_voice.test_task_progress_return import (
    NOW, AFTER_EXPIRY, _authority_task, _advance_authority_task_running, _finish_authority_task,
    _scope, _grant, _binding, _foreground, _busy_foreground,
    _SubscriptionDouble, _PreparedSourceDouble, _event,
)


async def eventually(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(.005)


async def make_owner(path, arbiter, busy, *, deferred_sink=None):
    path.mkdir()
    store, task_id, correlation = _authority_task(path)
    grant = _grant(task_id=task_id)
    source = TaskEventAuthorityProgressSource(
        store=store, authorization=grant, scope=_scope(), task_id=task_id,
        poll_interval=.005, consumer_scope=True, presentation_class="voice", clock=lambda: NOW,
    )
    intents = []

    async def sink(intent):
        intents.append(intent)

    bridge = TaskProgressReturnBridge(
        enabled=True, subscription=source.subscription, prepared_source=source,
        authorization=grant, binding=_binding(TaskProgressOriginKind.VOICE,
            task_id=task_id, correlation_id=correlation),
        generation_is_current=lambda _: True, arbiter=arbiter,
        foreground=lambda: _busy_foreground() if busy[0] else _foreground(),
        voice_sink=sink, text_sink=sink, deferred_voice_sink=deferred_sink, clock=lambda: NOW,
    )
    activation = await bridge.activate()
    assert activation.active and activation.lease
    await eventually(lambda: bridge.snapshot().last_task_event_seq == 0)
    return store, task_id, bridge, activation.lease, intents


@pytest.mark.asyncio
@pytest.mark.parametrize("both_pending", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
async def test_exact_task_drain_does_not_select_another_tasks_quiet_candidate(tmp_path, both_pending, reverse):
    arbiter = ProgressNotificationArbiter()
    busy = [both_pending]
    a = await make_owner(tmp_path / 'a', arbiter, busy)
    busy[0] = True
    b = await make_owner(tmp_path / 'b', arbiter, busy)
    try:
        busy[0] = False
        for owner in ([b, a] if reverse else [a, b]):
            await owner[3].drain_voice()
        for store, task_id, bridge, _, intents in (a, b):
            assert bridge.snapshot().state is TaskProgressReturnState.ACTIVE
            assert all(intent.task_event.task_id == task_id for intent in intents)
            assert store.unread_events_page(task_id, _scope(), presentation_class='voice', limit=500).watermark == -1
        _advance_authority_task_running(a[0], a[1])
        _finish_authority_task(a[0], a[1])
        await eventually(lambda: any(i.task_event.event_type == 'task.terminal' for i in a[4]))
        assert not any(i.task_event.event_type == 'task.terminal' for i in b[4])
        assert b[0].get_task(b[1], _scope()).state.value != 'terminal'
    finally:
        await a[3].close()
        await b[3].close()


@pytest.mark.asyncio
async def test_bridge_keeps_terminal_and_cursor_until_it_can_drain(tmp_path):
    arbiter = ProgressNotificationArbiter()
    busy = [True]
    store, task_id, bridge, lease, intents = await make_owner(tmp_path / 'a', arbiter, busy)
    try:
        _advance_authority_task_running(store, task_id)
        _finish_authority_task(store, task_id)
        await eventually(lambda: bridge.snapshot().last_task_event_seq == store.get_task(task_id, _scope()).event_head)
        # Let terminal cleanup run if it incorrectly releases the pending cursor.
        await asyncio.sleep(.02)
        assert arbiter.snapshot().pending_notifications == 1
        assert bridge.snapshot().worker_pending
        busy[0] = False
        assert await lease.drain_voice() == 1
        assert [i.task_event.event_type for i in intents] == ['task.terminal']
        assert await lease.drain_voice() == 0
        assert store.unread_events_page(task_id, _scope(), presentation_class='voice', limit=500).watermark == -1
    finally:
        await lease.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('owner', [DeferredVoiceOwnership.REGISTRY, DeferredVoiceOwnership.SILENT])
async def test_explicit_handoff_releases_scheduler_but_never_the_unread_watermark(tmp_path, owner):
    transferred = []

    async def handoff(intent):
        transferred.append(intent)
        return owner

    arbiter = ProgressNotificationArbiter()
    store, task_id, bridge, lease, emitted = await make_owner(tmp_path / 'a', arbiter, [True], deferred_sink=handoff)
    try:
        _advance_authority_task_running(store, task_id)
        _finish_authority_task(store, task_id)
        await eventually(lambda: bridge.snapshot().state is TaskProgressReturnState.CLOSED)
        assert transferred[-1].task_event.event_type == 'task.terminal'
        assert bridge.snapshot().pending_voice_intents == 0
        assert arbiter.snapshot().pending_notifications == 0
        assert await lease.drain_voice() == 0
        assert emitted == []
        assert store.unread_events_page(task_id, _scope(), presentation_class='voice', limit=500).watermark == -1
    finally:
        await lease.close()


@pytest.mark.asyncio
async def test_failed_handoff_closes_old_owner_and_fresh_authorized_lease_replays_unread(tmp_path):
    async def reject(_):
        raise RuntimeError('sink unavailable')

    store, task_id, bridge, lease, emitted = await make_owner(tmp_path / 'a', ProgressNotificationArbiter(), [True], deferred_sink=reject)
    await eventually(lambda: bridge.snapshot().state is TaskProgressReturnState.FAILED)
    assert emitted == [] and await lease.drain_voice() == 0
    await lease.close()
    assert store.unread_events_page(task_id, _scope(), presentation_class='voice', limit=500).watermark == -1
    _advance_authority_task_running(store, task_id)
    _finish_authority_task(store, task_id)
    source = TaskEventAuthorityProgressSource(store=store, authorization=_grant(task_id=task_id),
        scope=_scope(), task_id=task_id, consumer_scope=True, presentation_class='voice', clock=lambda: NOW)
    replayed = []

    async def sink(intent):
        replayed.append(intent)

    fresh = TaskProgressReturnBridge(enabled=True, subscription=source.subscription, prepared_source=source,
        authorization=_grant(task_id=task_id), binding=_binding(TaskProgressOriginKind.VOICE, task_id=task_id, generation=8),
        generation_is_current=lambda binding: binding.generation == 8, arbiter=ProgressNotificationArbiter(),
        foreground=_foreground, voice_sink=sink, text_sink=sink, clock=lambda: NOW)
    activated = await fresh.activate()
    try:
        assert activated.active
        await eventually(lambda: fresh.snapshot().state is TaskProgressReturnState.CLOSED)
        assert replayed[-1].task_event.event_type == 'task.terminal'
        assert all(intent.origin.generation == 8 and intent.task_event.task_id == task_id for intent in replayed)
        assert bridge.snapshot().state is TaskProgressReturnState.FAILED
        assert store.unread_events_page(task_id, _scope(), presentation_class='voice', limit=500).watermark == -1
    finally:
        await activated.lease.close()


@pytest.mark.asyncio
async def test_quiet_suffix_cannot_clear_a_retained_attention_event_it_did_not_handoff():
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, [
        _event(0, 'task.accepted', 'accepted'), _event(1, 'task.running', 'running'),
        _event(2, 'task.decision_required', 'decision_required'), _event(3, 'task.running', 'running'),
    ])
    arbiter = ProgressNotificationArbiter()
    busy = [True]
    handoffs, delivered = [], []

    async def handoff(intent):
        owner = DeferredVoiceOwnership.BRIDGE if task_progress_presentation_allowed(intent.task_event, presentation_class='voice') else DeferredVoiceOwnership.SILENT
        handoffs.append((intent.progress_event.event_id, intent.decision.retained_event_id, owner))
        return owner

    async def sink(intent):
        delivered.append(intent.task_event.event_type)

    bridge = TaskProgressReturnBridge(enabled=True, subscription=subscription, prepared_source=prepared,
        authorization=_grant(), binding=_binding(TaskProgressOriginKind.VOICE),
        generation_is_current=lambda _: True, arbiter=arbiter,
        foreground=lambda: _busy_foreground() if busy[0] else _foreground(),
        voice_sink=sink, text_sink=sink, deferred_voice_sink=handoff,
        allow_package_contract_handoff=True, clock=lambda: NOW)
    activation = await bridge.activate()
    try:
        await eventually(lambda: bridge.snapshot().last_task_event_seq == 3)
        assert handoffs[-1] == ('task-progress-return:event-2', 'task-progress-return:event-2', DeferredVoiceOwnership.BRIDGE)
        assert arbiter.snapshot().pending_notifications == bridge.snapshot().pending_voice_intents == 1
        busy[0] = False
        assert await activation.lease.drain_voice() == 1
        assert delivered == ['task.decision_required']
        assert await activation.lease.drain_voice() == 0
    finally:
        await activation.lease.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('fence', ['generation', 'authorization', 'close'])
@pytest.mark.parametrize('owner', [DeferredVoiceOwnership.REGISTRY, DeferredVoiceOwnership.SILENT])
async def test_handoff_rechecks_fences_after_await_with_zero_scheduling_or_durable_ack(tmp_path, monkeypatch, fence, owner):
    entered, release = asyncio.Event(), asyncio.Event()

    async def handoff(_):
        entered.set()
        await release.wait()
        return owner

    arbiter = ProgressNotificationArbiter()
    acknowledgements = []
    original_ack = arbiter.acknowledge

    def ack(*args):
        acknowledgements.append(args)
        return original_ack(*args)

    monkeypatch.setattr(arbiter, 'acknowledge', ack)
    store, task_id, bridge, lease, emitted = await make_owner(tmp_path / 'a', arbiter, [True], deferred_sink=handoff)
    close_task = None
    try:
        await entered.wait()
        if fence == 'generation':
            monkeypatch.setattr(bridge, '_generation_is_current', lambda _: False)
        elif fence == 'authorization':
            monkeypatch.setattr(bridge, '_clock', lambda: AFTER_EXPIRY)
        else:
            close_task = asyncio.create_task(lease.close())
            await asyncio.sleep(0)
        release.set()
        await eventually(lambda: not bridge.snapshot().worker_pending)
        if close_task is not None:
            await close_task
        assert acknowledgements == emitted == []
        assert await lease.drain_voice() == 0
        assert store.unread_events_page(task_id, _scope(), presentation_class='voice', limit=500).watermark == -1
        assert store.get_task(task_id, _scope()).event_head == 0
    finally:
        release.set()
        await lease.close()
