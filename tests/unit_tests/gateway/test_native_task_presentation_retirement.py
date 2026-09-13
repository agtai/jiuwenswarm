"""P2 promotion / P7 Task handoff retirement at the trusted Gateway seam."""
from copy import deepcopy
import json

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.gateway.live_voice.task_notification_preparation import PreparationViolation
from tests.unit_tests.gateway.test_task_notification_preparation import (
    arguments, cleanup, eventually, registry_fixture,
)


@pytest.fixture(autouse=True)
def allowed_origin(monkeypatch):
    monkeypatch.setenv("JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS", "voice.example.test")


def failure_receipt(registry, params):
    activation = registry._product_activations[("session-1", "connection-1", "interaction-1")]
    return json.loads(json.dumps({"ok": True, "product_composition": activation.product_composition,
        "result": {"status": "presentation_failed_fallback_text",
            **{key: params[key] for key in ("session_id", "correlation_id", "interaction_id",
                "activation_id", "activation_generation", "unit_id")},
            "response_id": params["response"]["response_id"],
            "response_generation": params["response"]["response_generation"],
            "surface": "audio", "failure_reason": "task_audio_playout_failed",
            "fallback": "text", "replayed": False}}))


def observe(registry, receipt, **overrides):
    routing = dict(routed_session_id="session-1", connection_id="connection-1",
        user_id="user-1", request_method="live_voice.composition.p2.presentation.failed")
    registry.observe_agent_response(receipt, **(routing | overrides))


def session(registry, parent):
    return registry._native_sessions[registry._native_session_keys_by_record[parent.record_id]]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["unprepared", "prepared", "claimed", "cancelled"])
async def test_canonical_failure_releases_only_exact_handoff_and_fences_replay(stage):
    registry, owner, provider, parent, params, notification = await registry_fixture()
    try:
        native = session(registry, parent)
        control = {key: value for key, value in params.items() if key != "text"}
        assert registry._native_task_presentation_busy(native)
        if stage != "unprepared":
            await registry.prepare_task_notification(**arguments(params))
        if stage == "claimed":
            await registry.claim_task_notification(**arguments(control))
            assert registry._pending_tickets
        if stage == "cancelled":
            registry.cancel_task_notification(**arguments(control))
            assert registry._native_task_presentation_busy(native)
        count = len(provider.requests)
        receipt = failure_receipt(registry, params)
        observe(registry, receipt)
        await eventually(lambda: registry._task_preparations.retained_count == 0)
        assert not registry._native_task_presentation_busy(native)
        assert not registry._pending_tickets and list(registry._records) == [parent.record_id]
        assert not parent.playout_receipts and not parent.downlink_results
        assert not parent.route_completed and not native.closed
        for changed in (False, True):
            replay = deepcopy(notification)
            if changed:
                replay["agent_event"]["text"] = "Different old text cannot revive a failed response."
            registry.observe_agent_response({"ok": True, "result": replay},
                routed_session_id="session-1", connection_id="connection-1")
            assert not registry._native_task_presentation_busy(native)
        receipt["result"]["replayed"] = True
        observe(registry, receipt)
        with pytest.raises(PreparationViolation):
            await registry.prepare_task_notification(**arguments(params))
        with pytest.raises(PreparationViolation):
            await registry.claim_task_notification(**arguments(control))
        assert len(provider.requests) == count and not parent.playout_receipts
        if stage != "unprepared":
            assert registry.cancel_task_notification(**arguments(control))["status"] == "cancelled"
    finally:
        await cleanup(registry, owner, parent)


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["method", "route", "connection", "manifest", "ok", "extra",
    "generation_bool", "generation", "activation", "correlation", "interaction", "response",
    "response_generation", "unit", "surface", "fallback", "reason", "replayed"])
async def test_wrong_failure_receipt_has_zero_retirement_or_playback_effects(defect):
    registry, owner, provider, parent, params, _ = await registry_fixture()
    try:
        await registry.prepare_task_notification(**arguments(params))
        receipt = failure_receipt(registry, params)
        routing = {}
        if defect in {"method", "route", "connection"}:
            routing[{"method": "request_method", "route": "routed_session_id",
                "connection": "connection_id"}[defect]] = "wrong"
        elif defect == "manifest": receipt.pop("product_composition")
        elif defect == "ok": receipt["ok"] = False
        else:
            key, value = {"extra": ("extra", True), "generation_bool": ("activation_generation", True),
                "generation": ("activation_generation", 2), "activation": ("activation_id", "other"),
                "correlation": ("correlation_id", "other"), "interaction": ("interaction_id", "other"),
                "response": ("response_id", "other"), "response_generation": ("response_generation", 4),
                "unit": ("unit_id", "other"), "surface": ("surface", "text"), "fallback": ("fallback", "audio"),
                "reason": ("failure_reason", "unknown"), "replayed": ("replayed", 1)}[defect]
            receipt["result"][key] = value
        observe(registry, receipt, **routing)
        assert registry._product_activations[("session-1", "connection-1", "interaction-1")].notification_fence.task_presentation_retired_generation == -1
        assert registry._native_task_presentation_busy(session(registry, parent))
        assert registry._task_preparations.retained_count == 1 and len(provider.requests) == 1
        assert not registry._pending_tickets and not parent.playout_receipts
        assert not parent.route_completed and not session(registry, parent).closed
    finally:
        await cleanup(registry, owner, parent)


@pytest.mark.asyncio
async def test_retirement_preserves_other_unit_and_accepted_render_fact():
    registry, owner, _provider, parent, params, notification = await registry_fixture()
    try:
        other = deepcopy(notification)
        other["presentation_unit"]["unit_id"] = "other-unit"
        registry.observe_agent_response({"ok": True, "result": other},
            routed_session_id="session-1", connection_id="connection-1")
        ref = ResponseRef(**params["response"])
        accepted = object()
        parent.playout_receipts[(ref, "unit-1")] = accepted
        observe(registry, failure_receipt(registry, params))
        assert parent.playout_receipts[(ref, "unit-1")] is accepted
        assert (ref, "other-unit") in parent.synthesis_content_sha256
        assert registry._native_task_presentation_busy(session(registry, parent))
        assert not parent.route_completed and not registry._pending_tickets
    finally:
        await cleanup(registry, owner, parent)


@pytest.mark.asyncio
async def test_failure_frontier_survives_expiry_and_long_session_without_revoking_another_source():
    registry, owner, provider, parent, params, notification = await registry_fixture()
    try:
        await registry.prepare_task_notification(**arguments(params))
        activation_key = ("session-1", "connection-1", "interaction-1")
        activation = registry._product_activations[activation_key]
        speech_authority = activation.streaming_response_authorities[0]
        slot = next(iter(registry._task_preparations._slots.values()))
        original_transfer = next(iter(activation.synthesis_content_sha256.values()))
        for generation in range(4, 505):
            current = deepcopy(notification)
            current["response"].update(response_id=f"failed-{generation}", response_generation=generation)
            registry.observe_agent_response({"ok": True, "result": current},
                routed_session_id="session-1", connection_id="connection-1")
            current_params = params | {"response": current["response"]}
            # Alternate a present transfer and an already expired/evicted one.
            if generation % 2 == 0:
                authority = registry._product_activations[activation_key]
                for (ref, _unit, _locale, _rate), transfer in authority.synthesis_content_sha256.items():
                    if ref.response_generation == generation:
                        transfer.expires_at = -1
            observe(registry, failure_receipt(registry, current_params))
            assert slot.is_current() and slot.reason is None
            assert registry._product_activations[activation_key].streaming_response_authorities[0] is speech_authority
            assert len(registry._product_activations[activation_key].synthesis_content_sha256) <= 16
        activation = registry._product_activations[activation_key]
        assert activation.notification_fence.task_presentation_retired_generation == 504
        assert original_transfer in activation.synthesis_content_sha256.values()
        assert not original_transfer.presentation_retired
        assert len(provider.requests) == 1 and not parent.playout_receipts
        # Exact old active A survives B failures, including its notification replay.
        registry.observe_agent_response({"ok": True, "result": notification},
            routed_session_id="session-1", connection_id="connection-1")
        assert slot.is_current()
        observe(registry, failure_receipt(registry, params))
        await eventually(lambda: registry._task_preparations.retained_count == 0)
        assert not registry._native_task_presentation_busy(session(registry, parent))
        # Replaying an evicted failed notification may not restore its busy grant.
        registry.observe_agent_response({"ok": True, "result": current},
            routed_session_id="session-1", connection_id="connection-1")
        assert not registry._native_task_presentation_busy(session(registry, parent))
        successor = deepcopy(current)
        successor["response"].update(response_id="valid-next", response_generation=505)
        registry.observe_agent_response({"ok": True, "result": successor},
            routed_session_id="session-1", connection_id="connection-1")
        assert registry._native_task_presentation_busy(session(registry, parent))
        assert not parent.route_completed and not parent.playout_receipts
    finally:
        await cleanup(registry, owner, parent)
