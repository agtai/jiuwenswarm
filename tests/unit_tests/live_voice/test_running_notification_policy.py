# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Running status stays observable without becoming an unsolicited presentation."""

import asyncio
import hashlib

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.runtime.formal_tasks.formal_task_models import (
    ExecutorObservation, ExecutorResolution, FormalAttemptState,
    TaskResultArtifact, TerminalOutcome,
)
from jiuwenswarm.server.live_voice.product_composition_registry import (
    AgentServerProductCompositionRegistry, ProductCompositionSettings, _VoiceTaskOrigin,
)
from tests.unit_tests.live_voice.test_product_composition_registry import (
    ACK_NOW, NOW, SCOPE, _AgentManager, _P3Composition, _p2_params,
    _presentation_progress_ack_params, _progress_params, _running_presentation_store,
)


@pytest.mark.asyncio
@pytest.mark.parametrize('origin_kind', ['text', 'voice'])
@pytest.mark.parametrize('offline', [False, True])
@pytest.mark.parametrize('outcome', [
    TerminalOutcome.COMPLETED, TerminalOutcome.FAILED,
    TerminalOutcome.CANCELLED, TerminalOutcome.INTERRUPTED,
])
async def test_running_silent_then_terminal_presented_and_acknowledged(
    tmp_path, monkeypatch, origin_kind, offline, outcome,
):
    monkeypatch.setattr(
        'jiuwenswarm.server.live_voice.product_composition_registry.utc_now',
        lambda: ACK_NOW,
    )
    project, store, task_id, _ = _running_presentation_store(tmp_path)
    task_before = store.get_task(task_id, SCOPE)
    pushed = []
    registries = []

    async def activate():
        async def push(message):
            pushed.append(message)
            return True

        manager = _AgentManager()
        registry = AgentServerProductCompositionRegistry(
            settings=ProductCompositionSettings(p2_enabled=True, p3_text_enabled=True),
            p3_composition=_P3Composition(project, presentation_store=store),
            agent_manager=manager, push_text_event=push,
        )
        registries.append(registry)
        assert (await registry.handle_p2_activate(
            params=_p2_params(), request_id='activate',
            session_id=SCOPE.session_id, channel_id='web',
        )).ok
        if outcome is TerminalOutcome.CANCELLED and origin_kind == 'voice' and not offline:
            # Exercise the busy-foreground defer sink as well as offline replay.
            runtime = registry._p2_routes[(SCOPE.session_id, 'interaction-1')].activation_lease._runtime
            original_safe = type(runtime).task_notification_foreground_safe
            monkeypatch.setattr(
                type(runtime), 'task_notification_foreground_safe',
                lambda current: False if current is runtime else original_safe(current),
            )
        registry._voice_task_origins[task_id] = _VoiceTaskOrigin(
            session_id=SCOPE.session_id, interaction_id='interaction-1',
            activation_id='activation-1', activation_generation=1,
            correlation_id='correlation-p2',
            response_ref=ResponseRef('interaction-1', 'response-origin', 0),
        )
        assert (await registry.handle_p3_progress_activate(
            params=_progress_params(
                task_id=task_id, correlation_id='correlation-p2',
                origin_id='interaction-1', origin_kind=origin_kind,
                generation_id='running-silence',
            ), request_id='subscribe', session_id=SCOPE.session_id, channel_id='web',
        )).ok
        return registry, next(iter(registry._progress_routes.values())), manager

    async def settle(retained, seq):
        for _ in range(300):
            if retained.progress_lease.snapshot().pending_voice_intents:
                await retained.progress_lease.drain_voice()
            if retained.progress_lease.snapshot().last_task_event_seq == seq:
                return
            await asyncio.sleep(0.01)
        pytest.fail(str(retained.progress_lease.snapshot()))

    try:
        registry, retained, manager = await activate()
        await settle(retained, 3)
        if retained.progress_lease.snapshot().pending_voice_intents:
            await retained.progress_lease.drain_voice()
        assert pushed == []
        assert registry._task_presentation_deliveries == {}
        assert retained.pending_presentations == {}
        assert manager.agent.calls == 0
        assert store.get_task(task_id, SCOPE) == task_before
        for presentation_class in ('text', 'voice'):
            assert store.unread_events_page(
                task_id, SCOPE, presentation_class=presentation_class, limit=500,
            ).watermark == -1

        if offline:
            await registry.stop()
        artifact = TaskResultArtifact('result.md', hashlib.sha256(b'finished').hexdigest())
        (project / 'result.md').write_bytes(b'finished')
        attempt = store.get_attempt(task_before.attempt_id)
        store.apply_observations((ExecutorObservation(
            resolution=ExecutorResolution.KNOWN, executor_id=attempt.executor_id,
            executor_ref=attempt.executor_ref, task_id=task_id, attempt_id=attempt.attempt_id,
            source_event_id=f'{attempt.executor_ref}:2', source_seq=2,
            attempt_state=FormalAttemptState.TERMINAL, attempt_outcome=outcome,
            occurred_at=NOW, raw_status=outcome.value,
            result_text='finished' if outcome is TerminalOutcome.COMPLETED else None,
            result_artifacts=(artifact,) if outcome is TerminalOutcome.COMPLETED else (),
        ),))
        if offline:
            registry, retained, manager = await activate()
        await settle(retained, 5)
        if outcome is TerminalOutcome.CANCELLED and origin_kind == 'voice':
            assert pushed == []
            assert registry._task_presentation_deliveries == {}
            assert retained.pending_presentations == {}
            assert registry._pending_terminal_notifications == {}
            assert registry._terminal_notification_responses == {}
            assert retained.orphaned_terminal is None
            assert manager.agent.calls == 0
            assert store.get_task(task_id, SCOPE).outcome is TerminalOutcome.CANCELLED
            for presentation_class in ('text', 'voice'):
                assert store.unread_events_page(
                    task_id, SCOPE, presentation_class=presentation_class, limit=500,
                ).watermark == -1
            return
        for _ in range(300):
            if retained.progress_lease.snapshot().pending_voice_intents:
                await retained.progress_lease.drain_voice()
            if registry._task_presentation_deliveries:
                break
            await asyncio.sleep(0.01)
        mapped = tuple(registry._task_presentation_deliveries.values())
        assert len(mapped) == 1
        delivery = mapped[0][1]
        assert delivery.event_seq == 5
        assert delivery.presentation_class == origin_kind
        if outcome is TerminalOutcome.CANCELLED:
            assert registry._pending_terminal_notifications == {}
            assert registry._terminal_notification_responses == {}
            assert not any(item.presentation_class == 'voice' for _, item in mapped)
        assert store.unread_events_page(
            task_id, SCOPE, presentation_class=origin_kind, limit=500,
        ).watermark == -1

        if origin_kind == 'text':
            for _ in range(300):
                if any(message.get('payload', {}).get('event_type') == 'live_voice.task.progress' for message in pushed):
                    break
                await asyncio.sleep(0.01)
            progress = [message['payload'] for message in pushed
                        if message.get('payload', {}).get('event_type') == 'live_voice.task.progress']
            assert len(progress) == 1
            assert progress[0]['source_event']['event_type'] == 'task.terminal'
            ack = await registry.handle_p3_progress_ack(
                params=_presentation_progress_ack_params(progress[0]),
                request_id='terminal-text-ack', session_id=SCOPE.session_id, channel_id='web',
            )
        else:
            notification = None
            for seq in range(1, 9):
                polled = await registry.handle_p2_notification_next(
                    params=_p2_params(notification_sequence=seq),
                    request_id=f'notice-{seq}', session_id=SCOPE.session_id,
                )
                assert polled.ok
                candidate = polled.payload['result']
                if candidate.get('response', {}).get('response_id') == delivery.response_ref.response_id:
                    notification = candidate
                    break
            assert notification is not None
            unit = notification['presentation_unit']
            assert unit['surface'] == 'audio'
            ack = await registry.handle_p2_presentation_ack(
                params=_p2_params(
                    response_id=delivery.response_ref.response_id,
                    response_generation=delivery.response_ref.response_generation,
                    surface='audio', unit_id=unit['unit_id'],
                    contiguous_cursor=unit['seq'], presented_at=ACK_NOW,
                ), request_id='terminal-audio-ack', session_id=SCOPE.session_id,
            )
        assert ack.ok
        assert store.unread_events_page(
            task_id, SCOPE, presentation_class=origin_kind, limit=500,
        ).watermark == 5
        other_class = 'voice' if origin_kind == 'text' else 'text'
        assert store.unread_events_page(
            task_id, SCOPE, presentation_class=other_class, limit=500,
        ).watermark == -1
        assert manager.agent.calls == 0
        assert store.get_task(task_id, SCOPE).outcome is outcome
        assert [event.event_type for event in store.events(task_id, SCOPE)] == [
            'task.accepted', 'attempt.accepted', 'attempt.running', 'task.running',
            'attempt.terminal', 'task.terminal',
        ]
    finally:
        for registry in registries:
            await registry.stop()
