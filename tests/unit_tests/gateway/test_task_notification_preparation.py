"""P7 exact preparation lifecycle and production Registry/Speech/media seam."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import json
import time

import pytest

from jiuwenswarm.gateway.live_voice.task_notification_preparation import (
    CONTRACT_VERSION, MAX_FRAMES, PreparationIdentity, PreparationViolation,
    TaskNotificationPreparationOwner,
)
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAudioFrame, MediaDetachReason, MediaTransportViolation,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import DedicatedMediaSocketLeafResult
from jiuwenswarm.gateway.live_voice.dedicated_media_registration import (
    DedicatedMediaProductRegistry, MEDIA_ROUTE_PATH, handle_registered_media_socket,
)
from jiuwenswarm.gateway.live_voice.streaming_synthesis_route import StreamingSynthesisRouteOwner
from jiuwenswarm.server.live_voice.openai_streaming_speech import SpeechRouteTier, StreamingSpeechSelection
from tests.unit_tests.gateway.test_product_streaming_synthesis import _Provider, _Batch
from tests.unit_tests.gateway.test_dedicated_media_registration import (
    ORIGIN, _activate, _params, _media_ticket, _FakeNativeRuntimeClient,
    _native_activation, _FakeNativeEngine, _task_synthesis_request, _AutoAckDownlinkSocket,
)
from jiuwenswarm.server.live_voice.batch_speech import SpeechRpcContext
from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ResponseRef


def identity(**updates):
    return replace(PreparationIdentity("session", "connection", "subject", "correlation", "interaction",
        "activation", 1, '["task","attempt","event"]', "response", 1, "unit", "a" * 64, "en-US", 48_000), **updates)


class Source:
    provider_id = "test"
    provider_implementation_class = "formal"
    provider_fallback_from = None
    model = "test-tts"
    voice = "test"

    def __init__(self, frames=2, rate=48_000):
        self.frames, self.rate = frames, rate
        self.completed = False
        self.closed = 0

    async def __aiter__(self):
        for seq in range(self.frames):
            yield MediaAudioFrame(seq, seq * (self.rate // 50), (0.25,) * (self.rate // 50))
        self.completed = True

    async def aclose(self):
        self.closed += 1


async def eventually(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_pcm_stays_unpresented_until_one_claim_and_exact_contiguous_consumption():
    owner = TaskNotificationPreparationOwner()
    source = Source(100)
    calls = []
    async def produce():
        calls.append("tts")
        return source
    slot = owner.start(identity(), "prepare-1", produce, lambda: True)
    assert owner.start(identity(), "prepare-1", produce, lambda: True) is slot
    await slot.wait_ready()
    await eventually(lambda: slot._produced)
    assert calls == ["tts"] and slot.emitted_frames == 0 and not slot.completed
    assert slot.produced_frames == 100 and slot.produced_bytes == 100 * 960 * 4
    slot.claim()
    with pytest.raises(PreparationViolation, match="ALREADY_CLAIMED"):
        slot.claim()
    slot.attach()
    frames = [frame async for frame in slot]
    assert [frame.seq for frame in frames] == list(range(100))
    assert frames[-1].sample_cursor == 99 * 960 and frames[0].samples[0] == 0.25
    assert slot.completed and owner.retained_count == 1 and not slot.settled
    slot.mark_rendered()
    assert owner.retained_count == 0 and slot.settled
    with pytest.raises(PreparationViolation, match="RETIRED"):
        owner.start(identity(), "prepare-1", produce, lambda: True)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["overflow", "empty", "invalid_pcm", "expiry", "source_changed", "cancel"])
async def test_preparation_faults_drop_pcm_without_claim_or_consumption(fault):
    valid = True
    owner = TaskNotificationPreparationOwner(retention_seconds=0.02 if fault == "expiry" else 30)
    source = Source(0 if fault == "empty" else MAX_FRAMES + 1 if fault == "overflow" else 3,
        rate=24_000 if fault == "invalid_pcm" else 48_000)
    async def produce(): return source
    slot = owner.start(identity(), "prepare-1", produce, lambda: valid)
    await eventually(lambda: slot.producer.done())
    if fault == "cancel":
        assert owner.cancel(identity(), "prepare-1")
        assert not owner.cancel(identity(), "prepare-1")
    elif fault == "source_changed":
        valid = False
        owner.reconcile()
    elif fault == "expiry":
        await eventually(lambda: slot.reason is not None)
    with pytest.raises(PreparationViolation):
        slot.claim()
    await eventually(lambda: owner.retained_count == 0)
    assert not slot.claimed and not slot.completed and slot.emitted_frames == 0
    assert not slot._frames and owner.retained_count == 0 and source.closed == 1
    assert slot.produced_frames <= MAX_FRAMES


@pytest.mark.asyncio
async def test_cancelled_hostile_open_retains_capacity_and_cannot_revive_or_cancel_other_owner():
    owner = TaskNotificationPreparationOwner()
    entered, release = asyncio.Event(), asyncio.Event()
    source = Source()
    async def produce():
        entered.set()
        try: await release.wait()
        except asyncio.CancelledError: await release.wait()
        return source
    slot = owner.start(identity(), "prepare-1", produce, lambda: True)
    await entered.wait()
    with pytest.raises(PreparationViolation, match="OWNER_MISMATCH"):
        owner.cancel(identity(subject_id="foreign"), "prepare-1")
    assert slot.reason is None
    owner.cancel(identity(), "prepare-1")
    with pytest.raises(PreparationViolation, match="BUSY"):
        owner.start(identity(response_id="new"), "prepare-2", produce, lambda: True)
    assert owner.retained_count == 1
    release.set()
    await eventually(lambda: owner.retained_count == 0)
    assert slot.produced_frames == slot.emitted_frames == 0 and source.closed == 1


@pytest.mark.asyncio
async def test_hard_production_deadline_wakes_caller_even_when_open_ignores_cancellation():
    owner = TaskNotificationPreparationOwner(production_seconds=0.01)
    release = asyncio.Event()
    source = Source()
    async def produce():
        while not release.is_set():
            try: await release.wait()
            except asyncio.CancelledError: pass
        return source
    slot = owner.start(identity(), "prepare-1", produce, lambda: True)
    with pytest.raises(PreparationViolation, match="TIMEOUT"):
        await asyncio.wait_for(slot.wait_ready(), 0.5)
    assert slot.produced_frames == slot.emitted_frames == 0 and owner.retained_count == 1
    release.set()
    await eventually(lambda: owner.retained_count == 0)
    assert source.closed == 1


@pytest.mark.asyncio
async def test_global_capacity_counts_all_opening_and_cancelled_cleanup_owners():
    owner = TaskNotificationPreparationOwner()
    release = asyncio.Event()
    async def produce():
        await release.wait()
        return Source()
    slots = [owner.start(identity(activation_id=f"activation-{index}"), "prepare-1", produce, lambda: True) for index in range(8)]
    with pytest.raises(PreparationViolation, match="CAPACITY"):
        owner.start(identity(activation_id="ninth"), "prepare-1", produce, lambda: True)
    assert owner.retained_count == 8
    for slot in slots: slot.fence("TASK_PREPARATION_CANCELLED")
    await eventually(lambda: owner.retained_count == 0)


@pytest.fixture(autouse=True)
def allowed_origin(monkeypatch):
    monkeypatch.setenv("JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS", "voice.example.test")


async def registry_fixture(*, outcome="completed", state="terminal", monotonic=time.monotonic):
    provider = _Provider()
    registry = DedicatedMediaProductRegistry(enabled=True, monotonic=monotonic,
        native_runtime_client=_FakeNativeRuntimeClient(_native_activation()),
        native_engine_factory=lambda _binding: _FakeNativeEngine())
    activated = _activate(registry, params=_params(sample_rate_hz=24_000),
        request_origin=ORIGIN, connection_id="connection-1")
    parent = registry.consume_ticket(_media_ticket(activated), request_origin=ORIGIN)
    await registry.begin_native_interaction(parent)
    async def selector(): return StreamingSpeechSelection(SpeechRouteTier.STREAMING, provider, None)
    owner = StreamingSynthesisRouteOwner(selector)
    registry.configure_streaming_synthesis(owner)
    text = "Task result is ready."
    response = {"interaction_id": "interaction-1", "response_id": "task-response", "response_generation": 3}
    source = {"scope": {"subject_id": "user-1", "project_id": "project-1", "session_id": "session-1", "assurance": "authenticated"},
        "stream_ref": {"kind": "task", "id": "task-1"}, "event_id": "event-1",
        "payload": {"state": state, "outcome": outcome},
        "extensions": {"jiuwenswarm.task_progress_return": {"persistent_attempt_id": "attempt-1"}}}
    notification = {"status": "notification", "kind": "agent.output", "session_id": "session-1",
        "correlation_id": "correlation-1", "activation_id": "activation-1", "activation_generation": 1,
        "response": response, "agent_event": {"event_type": "chat.final", "text": text, "source_provenance": "server.task_notification"},
        "presentation_unit": {"surface": "audio", "unit_id": "unit-1"}, "source_event": source}
    registry.observe_agent_response({"ok": True, "result": notification}, routed_session_id="session-1",
        user_id="user-1", connection_id="connection-1")
    event_key = json.dumps(["user-1", "project-1", "session-1", "authenticated", "task-1", "attempt-1", "event-1"], separators=(",", ":"))
    params = {"contract_version": CONTRACT_VERSION, "preparation_id": "prepare-task-1", "session_id": "session-1",
        "subject_id": parent.subject_id, "correlation_id": "correlation-1", "interaction_id": "interaction-1",
        "activation_id": "activation-1", "activation_generation": 1, "event_key": event_key,
        "response": response, "unit_id": "unit-1", "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "locale": "zh-CN", "sample_rate_hz": 24_000, "text": text}
    return registry, owner, provider, parent, params, notification


def arguments(params):
    return {"params": params, "routed_session_id": "session-1", "connection_id": "connection-1", "request_origin": ORIGIN}


async def cleanup(registry, owner, parent):
    registry.revoke(params={"session_id": "session-1", "subject_id": parent.subject_id,
        "correlation_id": "correlation-1", "interaction_id": "interaction-1",
        "activation_id": "activation-1", "activation_generation": 1},
        routed_session_id="session-1", connection_id="connection-1")
    await registry.close_native_interaction(parent)
    await owner.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("retry", [False, True])
async def test_real_registry_synthesis_media_seam_prepares_without_ticket_then_claims_once_and_requires_real_receipt(retry, monkeypatch):
    registry, owner, provider, parent, params, _ = await registry_fixture()
    release_cleanup = asyncio.Event()
    if retry:
        from jiuwenswarm.gateway.live_voice.product_streaming_synthesis import ProductStreamingSynthesisSource
        original_close = ProductStreamingSynthesisSource.aclose
        async def held_close(source):
            await original_close(source)
            try:
                await release_cleanup.wait()
            except asyncio.CancelledError:
                await release_cleanup.wait()
        monkeypatch.setattr(ProductStreamingSynthesisSource, "aclose", held_close)
    try:
        before_records = set(registry._records)
        ready, duplicate = await asyncio.gather(registry.prepare_task_notification(**arguments(params)),
            registry.prepare_task_notification(**arguments(params)))
        assert ready == duplicate
        assert ready["status"] == "ready" and ready["presented"] is False
        assert await registry.prepare_task_notification(**arguments(params)) == ready
        assert set(registry._records) == before_records and not registry._pending_tickets
        assert len(provider.requests) == 1 and not parent.playout_receipts and not parent.downlink_results
        control = {key: value for key, value in params.items() if key != "text"}
        claimed = await registry.claim_task_notification(**arguments(control))
        assert claimed["presented"] is False and claimed["audio"]["ticket_ttl_ms"] == 30_000
        with pytest.raises(PreparationViolation, match="ALREADY_CLAIMED"):
            await registry.claim_task_notification(**arguments(control))
        assert len(registry._pending_tickets) == 1
        downlink = registry._records[registry._pending_tickets[claimed["audio"]["media_ticket"]]]
        source = downlink.downlink_stream_source
        if retry:
            old_control, old_ticket = control, claimed["audio"]["media_ticket"]
            assert registry.cancel_task_notification(**arguments(control))["status"] == "cancelled"
            assert old_ticket not in registry._pending_tickets and downlink.record_id not in registry._records
            assert source.emitted_frames == 0 and not source.attached and not parent.playout_receipts
            params = {**params, "preparation_id": "prepare-task-retry"}
            replacement = asyncio.create_task(registry.prepare_task_notification(**arguments(params)))
            await asyncio.sleep(.01)
            assert not replacement.done() and len(provider.requests) == 1
            assert registry._task_preparations.retained_count == 1
            release_cleanup.set()
            assert (await asyncio.wait_for(replacement, 1))["status"] == "ready"
            assert len(provider.requests) == 2
            with pytest.raises(PreparationViolation):
                await registry.claim_task_notification(**arguments(old_control))
            control = {key: value for key, value in params.items() if key != "text"}
            claimed = await registry.claim_task_notification(**arguments(control))
            downlink = registry._records[registry._pending_tickets[claimed["audio"]["media_ticket"]]]
            source = downlink.downlink_stream_source
        assert not parent.playout_receipts
        registry.accept_frame(parent, MediaAudioFrame(0, 0, (0.0,) * 480))
        socket = _AutoAckDownlinkSocket(claimed["audio"])
        assert await handle_registered_media_socket(registry, socket, MEDIA_ROUTE_PATH)
        assert sum(isinstance(message, bytes) for message in socket.sent) == 1
        assert socket.close_calls == 1 and downlink.ticket_consumed and source.completed
        assert source.reason is None and source.state == "awaiting_receipt" and not source.settled
        assert registry._task_preparations.retained_count == 1
        assert downlink.downlink_stream_source is source
        assert not parent.playout_receipts
        receipt = registry.acknowledge_playout(params={"session_id": "session-1", "subject_id": parent.subject_id,
            "correlation_id": "correlation-1", "interaction_id": "interaction-1", "response_id": "task-response",
            "response_generation": 3, "unit_id": "unit-1", "capture_frames_acked": 1, "rendered_chunks": 1,
            "rendered_through_seq": 0, "playout_queue_capacity": 256, "playout_peak_depth": 1,
            "capture_control_ack": "capture_flush_acked", "playout_state": "render_completed"},
            routed_session_id="session-1", connection_id="connection-1", user_id="user-1", request_origin=ORIGIN)
        assert receipt["status"] == "media_playout_acknowledged"
        assert len(parent.playout_receipts) == 1 and not parent.route_completed
        assert registry._task_preparations.retained_count == 0 and source.settled
        assert registry.cancel_task_notification(**arguments(control))["status"] == "cancelled"
        assert len(parent.playout_receipts) == 1
    finally:
        release_cleanup.set()
        await cleanup(registry, owner, parent)


@pytest.mark.asyncio
async def test_cancel_before_retry_producer_keeps_actual_consumed_authority_and_fences_attached_retry():
    registry, owner, provider, parent, params, _ = await registry_fixture()
    try:
        await registry.prepare_task_notification(**arguments(params))
        control = {key: value for key, value in params.items() if key != "text"}
        registry.cancel_task_notification(**arguments(control))
        await eventually(lambda: registry._task_preparations.retained_count == 0)
        next_params = {**params, "preparation_id": "cancel-before-producer"}
        preparing = asyncio.create_task(registry.prepare_task_notification(**arguments(next_params)))
        await asyncio.sleep(0)
        registry.cancel_task_notification(**arguments({key: value for key, value in next_params.items() if key != "text"}))
        with pytest.raises(PreparationViolation):
            await preparing
        await eventually(lambda: registry._task_preparations.retained_count == 0)
        assert len(provider.requests) == 1 and not parent.playout_receipts
        final_params = {**params, "preparation_id": "retry-after-early-cancel"}
        await registry.prepare_task_notification(**arguments(final_params))
        control = {key: value for key, value in final_params.items() if key != "text"}
        claimed = await registry.claim_task_notification(**arguments(control))
        child = registry._records[registry._pending_tickets[claimed["audio"]["media_ticket"]]]
        child.downlink_stream_source.attach()
        registry.cancel_task_notification(**arguments(control))
        await eventually(lambda: registry._task_preparations.retained_count == 0)
        with pytest.raises(PreparationViolation):
            await registry.prepare_task_notification(**arguments({**params, "preparation_id": "forbidden-after-attach"}))
        assert len(provider.requests) == 2 and not parent.playout_receipts
        assert not registry._pending_tickets and not parent.route_completed
    finally:
        await cleanup(registry, owner, parent)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["send_error", "receive_cancel"])
async def test_actual_prepared_socket_abort_cleans_exact_unfinished_child_without_parent_effects(fault):
    registry, owner, provider, parent, params, _ = await registry_fixture()

    class FailedSocket(_AutoAckDownlinkSocket):
        async def send(self, message):
            if fault == "send_error" and isinstance(message, bytes):
                raise OSError("test socket send failure")
            await super().send(message)

        async def recv(self):
            if fault == "receive_cancel" and self._authenticated:
                raise asyncio.CancelledError
            return await super().recv()

    try:
        await registry.prepare_task_notification(**arguments(params))
        control = {key: value for key, value in params.items() if key != "text"}
        claimed = await registry.claim_task_notification(**arguments(control))
        child = registry._records[registry._pending_tickets[claimed["audio"]["media_ticket"]]]
        source = child.downlink_stream_source
        socket = FailedSocket(claimed["audio"])
        if fault == "receive_cancel":
            with pytest.raises(asyncio.CancelledError):
                await handle_registered_media_socket(registry, socket, MEDIA_ROUTE_PATH)
        else:
            assert await handle_registered_media_socket(registry, socket, MEDIA_ROUTE_PATH)
        await eventually(lambda: registry._task_preparations.retained_count == 0)
        assert source.reason is not None and not source.completed and not source.settled
        assert child.record_id not in registry._records and not registry._pending_tickets
        assert not parent.playout_receipts and not parent.downlink_results and not parent.route_completed
        registry.accept_frame(parent, MediaAudioFrame(0, 0, (0.0,) * 480))
        assert parent.accepted_frames == 1 and len(provider.requests) == 1
    finally:
        await cleanup(registry, owner, parent)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["wrong_event", "wrong_text", "wrong_activation", "wrong_subject", "cancelled", "running", "busy",
    "wrong_connection", "wrong_origin", "extra", "version", "response_extra", "null_digest"])
async def test_rejected_registry_preparation_has_zero_provider_ticket_receipt_or_protected_owner_effects(fault):
    registry, owner, provider, parent, params, _ = await registry_fixture(
        outcome="cancelled" if fault == "cancelled" else "completed", state="running" if fault == "running" else "terminal")
    try:
        if fault == "wrong_event": params["event_key"] += "changed"
        if fault == "wrong_text": params["text"] += "changed"
        if fault == "wrong_activation": params["activation_generation"] += 1
        if fault == "wrong_subject": params["subject_id"] = "foreign"
        if fault == "busy": registry._tts_opening[("session-1", "connection-1", "interaction-1")] = {object()}
        if fault == "extra": params["extra"] = True
        if fault == "version": params["contract_version"] = "unrecognized"
        if fault == "response_extra": params["response"]["extra"] = True
        if fault == "null_digest": params["text_sha256"] = None
        request_arguments = arguments(params)
        if fault == "wrong_connection": request_arguments["connection_id"] = "another-connection"
        if fault == "wrong_origin": request_arguments["request_origin"] = "https://foreign.example.test"
        before = set(registry._records)
        with pytest.raises(PreparationViolation):
            await registry.prepare_task_notification(**request_arguments)
        assert not provider.requests and not provider.cancelled
        assert not registry._pending_tickets and set(registry._records) == before
        assert not parent.playout_receipts and not parent.downlink_results and not parent.route_completed
        assert registry._task_preparations.retained_count == 0
    finally:
        await cleanup(registry, owner, parent)


@pytest.mark.asyncio
async def test_prepared_source_blocks_normal_tts_without_superseding_and_cancel_preserves_native_input():
    registry, owner, provider, parent, params, _ = await registry_fixture()
    try:
        await registry.prepare_task_notification(**arguments(params))
        request = _task_synthesis_request(subject_id=parent.subject_id,
            response=ResponseRef("interaction-1", "task-response", 3), sample_rate_hz=24_000, text=params["text"])
        result = await registry.try_streaming_synthesis("speech.synthesize.batch", request,
            SpeechRpcContext(parent.subject_id, "session-1", Assurance.AUTHENTICATED), "session-1", batch_service=_Batch())
        assert result["error"]["reason"] == "TASK_PREPARATION_BUSY"
        assert len(provider.requests) == 1
        control = {key: value for key, value in params.items() if key != "text"}
        assert registry.cancel_task_notification(**arguments(control))["status"] == "cancelled"
        assert registry.cancel_task_notification(**arguments(control))["status"] == "cancelled"
        with pytest.raises(PreparationViolation):
            await registry.claim_task_notification(**arguments(control))
        assert not registry._pending_tickets and not parent.playout_receipts and not parent.route_completed
        registry.accept_frame(parent, MediaAudioFrame(0, 0, (0.0,) * 480))
        assert parent.accepted_frames == 1
    finally:
        await cleanup(registry, owner, parent)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["text", "event", "activation_close", "native_close"])
async def test_authoritative_change_fences_old_preparation_without_ticket_or_ack(change):
    registry, owner, provider, parent, params, notification = await registry_fixture()
    try:
        await registry.prepare_task_notification(**arguments(params))
        slot = next(iter(registry._task_preparations._slots.values()))
        if change in {"text", "event"}:
            if change == "text": notification["agent_event"]["text"] = "Changed authoritative text."
            else: notification["source_event"]["event_id"] = "event-replaced"
            registry.observe_agent_response({"ok": True, "result": notification}, routed_session_id="session-1",
                user_id="user-1", connection_id="connection-1")
        elif change == "activation_close":
            registry._revoke_media_for_product_activation(registry._product_activations[("session-1", "connection-1", "interaction-1")])
        else:
            await registry.close_native_interaction(parent)
        with pytest.raises(PreparationViolation): slot.claim()
        assert not slot._frames and not registry._pending_tickets and not parent.playout_receipts
        assert slot.emitted_frames == 0 and len(provider.requests) == 1
    finally:
        await cleanup(registry, owner, parent)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["cancel", "text", "native_close"])
async def test_claimed_child_is_invalidated_without_granting_ack_or_closing_unchanged_parent(change):
    registry, owner, provider, parent, params, notification = await registry_fixture()
    try:
        await registry.prepare_task_notification(**arguments(params))
        control = {key: value for key, value in params.items() if key != "text"}
        claimed = await registry.claim_task_notification(**arguments(control))
        assert len(registry._pending_tickets) == 1
        if change == "cancel":
            registry.cancel_task_notification(**arguments(control))
        elif change == "text":
            notification["agent_event"]["text"] = "Replacement authoritative text."
            registry.observe_agent_response({"ok": True, "result": notification}, routed_session_id="session-1",
                user_id="user-1", connection_id="connection-1")
        else:
            await registry.close_native_interaction(parent)
        assert not registry._pending_tickets
        assert registry.consume_ticket(claimed["audio"]["media_ticket"], request_origin=ORIGIN) is None
        assert not parent.playout_receipts and not parent.downlink_results
        if change != "native_close":
            assert not parent.route_completed
            registry.accept_frame(parent, MediaAudioFrame(0, 0, (0.0,) * 480))
            assert parent.accepted_frames == 1
        assert len(provider.requests) == 1
    finally:
        await cleanup(registry, owner, parent)


@pytest.mark.asyncio
@pytest.mark.parametrize("at_attach", [False, True])
async def test_fresh_claim_ticket_expires_only_its_child_and_cannot_be_replayed(at_attach, monkeypatch):
    clock = [time.monotonic()]
    registry, owner, provider, parent, params, _ = await registry_fixture(monotonic=lambda: clock[0])
    try:
        await registry.prepare_task_notification(**arguments(params))
        clock[0] += 29
        control = {key: value for key, value in params.items() if key != "text"}
        claimed = await registry.claim_task_notification(**arguments(control))
        child = next(record for record in registry._records.values() if record is not parent)
        assert child.ticket_expires_at == clock[0] + 30
        revoked_before = dict(registry._revoked)
        if at_attach:
            source_type = type(child.downlink_stream_source)
            attach = source_type.attach
            def expired_attach(source):
                clock[0] += 31
                return attach(source)
            monkeypatch.setattr(source_type, "attach", expired_attach)
        else:
            clock[0] += 31
        assert registry.consume_ticket(claimed["audio"]["media_ticket"], request_origin=ORIGIN) is None
        assert registry._revoked == revoked_before
        assert set(registry._records) == {parent.record_id} and not parent.route_completed
        registry.accept_frame(parent, MediaAudioFrame(0, 0, (0.0,) * 480))
        assert parent.accepted_frames == 1 and not parent.playout_receipts and not parent.downlink_results
        assert len(provider.requests) == 1
    finally:
        await cleanup(registry, owner, parent)


@pytest.mark.asyncio
async def test_real_normal_tts_opening_atomically_excludes_preparation_without_superseding(monkeypatch):
    registry, owner, provider, parent, params, _ = await registry_fixture()
    entered, release = asyncio.Event(), asyncio.Event()
    original_open = provider.open_synthesis

    async def held_open(request):
        entered.set()
        await release.wait()
        await original_open(request)

    monkeypatch.setattr(provider, "open_synthesis", held_open)
    normal = None
    try:
        request = _task_synthesis_request(subject_id=parent.subject_id,
            response=ResponseRef("interaction-1", "task-response", 3), sample_rate_hz=24_000, text=params["text"])
        normal = asyncio.create_task(registry.try_streaming_synthesis("speech.synthesize.batch", request,
            SpeechRpcContext(parent.subject_id, "session-1", Assurance.AUTHENTICATED), "session-1", batch_service=_Batch()))
        await entered.wait()
        with pytest.raises(PreparationViolation, match="BUSY"):
            await registry.prepare_task_notification(**arguments(params))
        assert not provider.cancelled and registry._task_preparations.retained_count == 0
        assert not registry._pending_tickets and not parent.playout_receipts and not parent.route_completed
        release.set()
        result = await normal
        assert result["ok"] is True and len(provider.requests) == 1
        assert len(registry._pending_tickets) == 1
    finally:
        release.set()
        if normal is not None:
            await normal
        await cleanup(registry, owner, parent)


@pytest.mark.asyncio
@pytest.mark.parametrize("transport_complete", [False, True])
@pytest.mark.parametrize("change", ["cancel", "text", "render_timeout", "transport_failed"])
async def test_eof_keeps_cancel_ownership_until_real_render_receipt(transport_complete, change):
    clock = [time.monotonic()]
    registry, owner, provider, parent, params, notification = await registry_fixture(monotonic=lambda: clock[0])
    try:
        await registry.prepare_task_notification(**arguments(params))
        control = {key: value for key, value in params.items() if key != "text"}
        claimed = await registry.claim_task_notification(**arguments(control))
        child = registry.consume_ticket(claimed["audio"]["media_ticket"], request_origin=ORIGIN)
        source = child.downlink_stream_source
        registry.mark_downlink_started(child)
        registry.accept_frame(parent, MediaAudioFrame(0, 0, (0.0,) * 480))
        frames = [frame async for frame in source]
        assert len(frames) == 1 and source.completed and not source.settled
        assert registry._task_preparations.retained_count == 1 and not parent.playout_receipts
        result = DedicatedMediaSocketLeafResult(activated=True, socket_touched=True, attach_sent=True,
            accepted_frames=0, close_result=None, reason_id=MediaDetachReason.LOCAL_CLOSE,
            sent_frames=1, acknowledged_through_seq=0, configured_max_pending_frames=8,
            configured_max_pending_bytes=131_072, peak_pending_frames=1, peak_pending_bytes=1920)
        if transport_complete:
            assert registry.complete_downlink(child, result)
            assert child.downlink_stream_source is source and registry._task_preparations.retained_count == 1
        await source.aclose()
        assert source.reason is None and registry._task_preparations.retained_count == 1
        if change == "cancel":
            registry.cancel_task_notification(**arguments(control))
        elif change == "text":
            notification["agent_event"]["text"] = "Changed authoritative result after EOF."
            registry.observe_agent_response({"ok": True, "result": notification}, routed_session_id="session-1",
                user_id="user-1", connection_id="connection-1")
        elif change == "render_timeout":
            clock[0] += 31
        else:
            assert not registry.complete_downlink(child, replace(result, sent_frames=0, acknowledged_through_seq=None))
        assert not registry.complete_downlink(child, result), "Late completion cannot restore cancelled child evidence"
        with pytest.raises(MediaTransportViolation, match="completed downlink"):
            registry.acknowledge_playout(params={"session_id": "session-1", "subject_id": parent.subject_id,
                "correlation_id": "correlation-1", "interaction_id": "interaction-1", "response_id": "task-response",
                "response_generation": 3, "unit_id": "unit-1", "capture_frames_acked": 1, "rendered_chunks": 1,
                "rendered_through_seq": 0, "playout_queue_capacity": 256, "playout_peak_depth": 1,
                "capture_control_ack": "capture_flush_acked", "playout_state": "render_completed"},
                routed_session_id="session-1", connection_id="connection-1", user_id="user-1", request_origin=ORIGIN)
        assert not parent.playout_receipts and not parent.downlink_results and not parent.route_completed
        assert child.record_id not in registry._records and not source.settled
        assert len(provider.requests) == 1
    finally:
        await cleanup(registry, owner, parent)
