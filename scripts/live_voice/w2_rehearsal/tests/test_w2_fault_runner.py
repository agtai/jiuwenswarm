from __future__ import annotations

import asyncio
import io
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAck,
    MediaAttach,
    serialize_media_control,
)
from scripts.live_voice.w2_rehearsal.w2_fault_runner import (
    ChromeNetworkObserver,
    ChromeP3Oracle,
    GatewayDedicatedSpeechFactory,
    GatewayWebSocketClient,
    ObservedWebMessage,
    StockSpeechTemplate,
    W2FaultRunner,
    _typed_media_binding,
    derive_public_fault_plan,
)


@dataclass(frozen=True)
class _Fault:
    pair: int
    plane: str
    fault_class: str
    operation: str
    request_id: str
    source_record_id: str


class _ScriptedRpc:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    async def request(
        self, method: str, params: dict[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        self.calls.append((method, params, request_id))
        assert self.responses, "unexpected Gateway request"
        return self.responses.pop(0)


class _MediaSocket:
    def __init__(self, received: list[str]) -> None:
        self.received = list(received)
        self.sent: list[str | bytes] = []

    async def recv(self) -> str:
        assert self.received, "unexpected media receive"
        return self.received.pop(0)

    async def send(self, value: str | bytes) -> None:
        self.sent.append(value)


def _media_binding(
    *, interaction_id: str = "interaction-1", capture_id: str = "capture-1", track_id: str = "track-1"
) -> Any:
    return _typed_media_binding(
        {
            "lease_id": "lease-1",
            "authority_evidence_id": "authority-1",
            "connection_id": "connection-1",
            "connection_epoch": 0,
            "session_id": "session-1",
            "media_session_id": "media-session-1",
            "interaction_id": interaction_id,
            "track_id": track_id,
            "correlation_id": "correlation-1",
            "direction": "uplink",
            "generation": {"kind": "capture", "id": capture_id, "value": 1},
            "frame_format": {
                "sample_rate_hz": 8_000,
                "samples_per_channel": 160,
                "encoding": "pcm_f32",
                "byte_order": "little",
                "channel_count": 1,
                "frame_duration_ms": 20,
            },
            "playout": None,
        }
    )


class _SpeechLease:
    def __init__(self, label: str) -> None:
        self.label = label
        self.closed = False
        self.params = {
            "contract_version": "live-voice.contract.v2",
            "request_id": f"{label}-inner",
            "operation_id": f"{label}-operation",
            "operation": "speech.recognize.batch",
            "correlation_id": "correlation-1",
            "session_id": "session-1",
            "scope": {
                "subject_id": "subject-1",
                "project_id": None,
                "session_id": "session-1",
                "assurance": "authenticated",
            },
            "timeout_ms": 1_000,
            "capture": {
                "capture_id": f"{label}-capture",
                "capture_generation": 1,
                "track_id": f"{label}-track",
                "final": True,
            },
            "audio": {
                "format": "wav_pcm16_mono",
                "sample_rate_hz": 48_000,
                "channel_count": 1,
                "data_base64": "memory-only-audio",
            },
            "locale": "en-US",
        }

    async def close(self) -> None:
        self.closed = True


class _SpeechFactory:
    def __init__(self) -> None:
        self.leases: list[_SpeechLease] = []

    async def create(self, label: str) -> _SpeechLease:
        lease = _SpeechLease(label)
        self.leases.append(lease)
        return lease


class _NoSocketSpeechFactory(GatewayDedicatedSpeechFactory):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.upload_bindings: list[Any] = []

    async def _upload(self, endpoint_path: str, binding: Any, speech: Any) -> None:
        del endpoint_path, speech
        self.upload_bindings.append(binding)


def _stock_template() -> StockSpeechTemplate:
    return StockSpeechTemplate(
        p2_activation_params={
            "session_id": "session-1",
            "correlation_id": "correlation-1",
            "interaction_id": "stock-interaction",
            "activation_id": "stock-activation",
            "activation_generation": 7,
            "claimed_user_id": None,
            "claimed_project_id": None,
        },
        media_activation_params={
            "session_id": "session-1",
            "interaction_id": "stock-interaction",
            "correlation_id": "correlation-1",
            "activation_id": "stock-activation",
            "activation_generation": 7,
            "capture_id": "stock-capture",
            "capture_generation": 1,
            "track_id": "stock-track",
            "sample_rate_hz": 8_000,
            "locale": "en-US",
        },
        speech_params={
            "contract_version": "live-voice.contract.v2",
            "request_id": "stock-speech",
            "operation_id": "stock-operation",
            "operation": "speech.recognize.batch",
            "correlation_id": "correlation-1",
            "session_id": "session-1",
            "scope": {
                "subject_id": "stock-subject",
                "project_id": None,
                "session_id": "session-1",
                "assurance": "authenticated",
            },
            "timeout_ms": 1_000,
            "capture": {
                "capture_id": "stock-capture",
                "capture_generation": 1,
                "track_id": "stock-track",
                "final": True,
            },
            "audio": {
                "format": "wav_pcm16_mono",
                "sample_rate_hz": 8_000,
                "channel_count": 1,
                "data_base64": "dGVzdA==",
            },
            "locale": "en-US",
        },
    )


def _fault(pair: int, plane: str, fault_class: str, operation: str) -> _Fault:
    return _Fault(
        pair,
        plane,
        fault_class,
        operation,
        f"w2-fault-{pair}-{plane}-{fault_class}",
        f"w2-request-{pair}-{plane}-{fault_class}",
    )


def _error(request_id: str, code: str, reason: str) -> dict[str, Any]:
    return {
        "type": "res",
        "id": request_id,
        "ok": True,
        "payload": {
            "request_id": request_id,
            "ok": False,
            "result": None,
            "error": {"code": code, "reason": reason, "retriable": code in {"TIMEOUT", "UNAVAILABLE"}},
        },
    }


def _success(request_id: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "res",
        "id": request_id,
        "ok": True,
        "payload": {
            "request_id": request_id,
            "ok": True,
            "result": result or {"status": "accepted"},
            "error": None,
        },
    }


def _direct(request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": "res", "id": request_id, "ok": True, "payload": payload}


def _speech_success(request_id: str, capture_label: str) -> dict[str, Any]:
    capture_id = f"{capture_label}-capture"
    track_id = f"{capture_label}-track"
    return _success(
        request_id,
        {
            "operation": "speech.recognize.batch",
            "capture": {
                "capture_id": capture_id,
                "capture_generation": 1,
                "track_id": track_id,
                "final": True,
            },
            "event": {
                "session_id": capture_id,
                "generation": 1,
                "seq": 1,
                "kind": "final",
                "hypothesis": {
                    "alternatives": [
                        {
                            "raw_text": "formal transcript",
                            "display_text": "formal transcript",
                            "confidence": None,
                        }
                    ],
                    "selected_index": 0,
                },
                "commits_turn": False,
            },
            "locale": {"requested": "en-US", "observed": "en-US"},
            "timing": {"audio_duration_ms": 20, "provider_elapsed_ms": 1},
            "provider": {
                "provider_id": "formal-provider",
                "implementation_class": "formal",
                "model": "stt-model",
                "fallback_from": None,
            },
            "voice_commit_receipt": f"receipt-{capture_id}",
        },
    )


@pytest.mark.asyncio
async def test_p1_retriable_exact_replay_recovers_only_on_fresh_capture() -> None:
    fault = _fault(1, "p1.speech_media", "retriable", "speech.recognize.batch")
    failed = _error(
        fault.request_id,
        "UNAVAILABLE",
        "SPEECH_W2_RETRIABLE_FAULT_INJECTED",
    )
    recovery_id = f"{fault.source_record_id}-recovery"
    rpc = _ScriptedRpc(
        [
            failed,
            failed,
            _speech_success(
                recovery_id, f"{fault.source_record_id}-recovery-capture"
            ),
        ]
    )
    media = _SpeechFactory()

    await W2FaultRunner(rpc).probe_p1_retriable(fault, media)

    assert [call[2] for call in rpc.calls] == [fault.request_id, fault.request_id, recovery_id]
    assert len(media.leases) == 2
    assert media.leases[0].params["capture"] != media.leases[1].params["capture"]
    assert all(lease.closed for lease in media.leases)


@pytest.mark.asyncio
async def test_p1_non_retriable_replays_invalid_timeout_then_uses_untouched_binding() -> None:
    fault = _fault(2, "p1.speech_media", "non_retriable", "speech.recognize.batch")
    failed = _error(fault.request_id, "INVALID_ARGUMENT", "INVALID_SPEECH_TIMEOUT")
    recovery_id = f"{fault.source_record_id}-recovery"
    rpc = _ScriptedRpc(
        [
            failed,
            failed,
            _speech_success(recovery_id, f"{fault.source_record_id}-fault-capture"),
        ]
    )
    media = _SpeechFactory()

    await W2FaultRunner(rpc).probe_p1_non_retriable(fault, media)

    invalid, replay, recovery = rpc.calls
    assert invalid[1]["timeout_ms"] == 0
    assert replay[1] == invalid[1]
    assert recovery[1]["timeout_ms"] > 0
    assert recovery[1]["capture"] == invalid[1]["capture"]
    assert len(media.leases) == 1 and media.leases[0].closed


@pytest.mark.asyncio
async def test_p1_zero_effect_never_allows_same_capture_success_after_stale() -> None:
    fault = _fault(3, "p1.speech_media", "zero_effect", "speech.recognize.batch")
    reserve_id = f"{fault.source_record_id}-reserve"
    stale = _error(fault.request_id, "STALE", "STALE_RECOGNITION_SESSION")
    recovery_id = f"{fault.source_record_id}-recovery"
    rpc = _ScriptedRpc(
        [
            _error(reserve_id, "TIMEOUT", "SPEECH_PROVIDER_TIMEOUT"),
            stale,
            stale,
            _speech_success(recovery_id, f"{fault.source_record_id}-fresh-capture"),
        ]
    )
    media = _SpeechFactory()

    await W2FaultRunner(rpc).probe_p1_zero_effect(fault, media)

    same_capture = [call[1]["capture"] for call in rpc.calls[:3]]
    assert same_capture[0] == same_capture[1] == same_capture[2]
    assert [call[2] for call in rpc.calls[:3]] == [
        reserve_id,
        fault.request_id,
        fault.request_id,
    ]
    assert rpc.calls[0][1]["timeout_ms"] == 1
    assert rpc.calls[3][1]["capture"] != same_capture[0]
    assert len(media.leases) == 2 and all(lease.closed for lease in media.leases)


@pytest.mark.asyncio
async def test_p2_retriable_exact_replay_recovers_after_one_shot_failure() -> None:
    fault = _fault(1, "p2.conversation", "retriable", "live_voice.composition.p2.presentation.ack")
    failed = _error(fault.request_id, "UNAVAILABLE", "PRODUCT_W2_RETRIABLE_FAULT_INJECTED")
    recovered = _success(
        fault.request_id,
        {"status": "presentation_acknowledged", "replayed": False},
    )
    rpc = _ScriptedRpc([failed, recovered])
    canonical = {"session_id": "session-1", "response_id": "response-1", "contiguous_cursor": 12}

    await W2FaultRunner(rpc).probe_p2_retriable(fault, canonical)

    assert [call[1] for call in rpc.calls] == [canonical, canonical]
    assert [call[2] for call in rpc.calls] == [fault.request_id, fault.request_id]


@pytest.mark.asyncio
async def test_p2_non_retriable_uses_schema_valid_beyond_produced_cursor() -> None:
    fault = _fault(2, "p2.conversation", "non_retriable", "live_voice.composition.p2.presentation.ack")
    failed = _error(fault.request_id, "PROTOCOL_VIOLATION", "ACK_BEYOND_PRODUCED_CURSOR")
    recovery_id = f"{fault.source_record_id}-recovery"
    rpc = _ScriptedRpc([failed, failed, _success(recovery_id, {"status": "presentation_acknowledged"})])
    canonical = {"session_id": "session-1", "response_id": "response-1", "contiguous_cursor": 12}

    await W2FaultRunner(rpc).probe_p2_non_retriable(fault, canonical)

    assert rpc.calls[0][1]["contiguous_cursor"] == (1 << 53) - 1
    assert rpc.calls[1][1] == rpc.calls[0][1]
    assert rpc.calls[2][1] == canonical


@pytest.mark.asyncio
async def test_p2_zero_effect_keeps_canonical_ack_binding_and_recovers() -> None:
    fault = _fault(3, "p2.conversation", "zero_effect", "live_voice.composition.p2.presentation.ack")
    failed = _error(
        fault.request_id,
        "STALE",
        "PRODUCT_W2_STALE_FAULT_INJECTED",
    )
    recovery_id = f"{fault.source_record_id}-recovery"
    rpc = _ScriptedRpc([failed, failed, _success(recovery_id, {"status": "presentation_acknowledged"})])
    canonical = {"session_id": "session-1", "response_id": "response-1", "contiguous_cursor": 12}

    await W2FaultRunner(rpc).probe_p2_zero_effect(fault, canonical)

    assert rpc.calls[0][1] == canonical
    assert rpc.calls[1][1] == canonical
    assert rpc.calls[2][1] == canonical


class _P3Oracle:
    def __init__(
        self,
        snapshots: list[dict[str, Any]],
        winner: dict[str, Any] | None = None,
        stock_ack: dict[str, Any] | None = None,
    ) -> None:
        self.snapshots = list(snapshots)
        self.winner = winner
        self.stock_ack = stock_ack
        self.stock_ack_calls = 0

    async def snapshot(self, _task_id: str) -> dict[str, Any]:
        assert self.snapshots
        return self.snapshots.pop(0)

    async def wait_stock_retry(self, _task_id: str) -> dict[str, Any]:
        assert self.winner is not None
        return self.winner

    async def wait_stock_progress_ack(
        self,
        *,
        after_delivery_id: str,
        expected_session_id: str,
        expected_task_id: str,
    ) -> dict[str, Any]:
        self.stock_ack_calls += 1
        return self.stock_ack or {
            "delivery_id": f"{after_delivery_id}-canonical",
            "attempt_id": "attempt-b",
            "session_id": expected_session_id,
            "task_id": expected_task_id,
            "source_event_id": "source-b",
            "progress_event_id": "progress-b",
            "status": "acknowledged",
            "source": "stock_ui",
        }


@pytest.mark.asyncio
async def test_p3_retriable_negative_ack_is_companion_only_and_positive_recovery_is_stock_ui() -> None:
    fault = _fault(1, "p3.task", "retriable", "live_voice.composition.p3.progress.ack")
    failed = _error(fault.request_id, "UNAVAILABLE", "TASK_PROGRESS_DELIVERY_UNAVAILABLE")
    rpc = _ScriptedRpc([failed, failed])
    canonical = {
        "session_id": "session-1",
        "task_id": "task-1",
        "delivery_id": "canonical-delivery",
        "source_event_id": "source-1",
        "progress_event_id": "progress-1",
    }
    oracle = _P3Oracle([])

    await W2FaultRunner(rpc).probe_p3_retriable(fault, canonical, oracle)

    assert rpc.calls[0][1]["delivery_id"] == fault.source_record_id
    assert rpc.calls[1][1] == rpc.calls[0][1]
    assert len(rpc.calls) == 2, "companion must never send the canonical positive ACK"
    assert oracle.stock_ack_calls == 1


@pytest.mark.asyncio
async def test_p3_retriable_rejects_foreign_task_stock_ack_recovery() -> None:
    fault = _fault(1, "p3.task", "retriable", "live_voice.composition.p3.progress.ack")
    failed = _error(fault.request_id, "UNAVAILABLE", "TASK_PROGRESS_DELIVERY_UNAVAILABLE")
    canonical = {
        "session_id": "session-1",
        "task_id": "task-1",
        "delivery_id": "canonical-delivery",
        "source_event_id": "source-1",
        "progress_event_id": "progress-1",
    }
    oracle = _P3Oracle(
        [],
        stock_ack={
            "delivery_id": "foreign-delivery",
            "attempt_id": "attempt-foreign",
            "session_id": "session-1",
            "task_id": "task-foreign",
            "source_event_id": "source-foreign",
            "progress_event_id": "progress-foreign",
            "status": "acknowledged",
            "source": "stock_ui",
        },
    )

    with pytest.raises(Exception, match="canonical positive progress ACK"):
        await W2FaultRunner(_ScriptedRpc([failed, failed])).probe_p3_retriable(
            fault, canonical, oracle
        )


@pytest.mark.asyncio
async def test_p3_non_retriable_presigns_terminal_then_rejects_mutate_against_nonterminal_b() -> None:
    fault = _fault(2, "p3.task", "non_retriable", "live_voice.composition.p3.mutate")
    issue_id = f"{fault.source_record_id}-confirmation"
    failed = _error(fault.request_id, "CONFLICT", "TASK_RETRY_REQUIRES_TERMINAL")
    rpc = _ScriptedRpc(
        [
            _success(issue_id, {"status": "confirmation_issued", "confirmation_id": "confirmation-probe"}),
            failed,
            failed,
        ]
    )
    terminal_a = {
        "task_id": "task-1",
        "attempt_id": "attempt-a",
        "attempt_number": 1,
        "state": "terminal",
        "retry_count": 0,
        "event_facts": ((3, "event-a-terminal", "attempt-a", "task.terminal", "executor-a"),),
    }
    nonterminal_b = {
        "task_id": "task-1",
        "attempt_id": "attempt-b",
        "attempt_number": 2,
        "state": "running",
        "retry_count": 1,
        "event_facts": ((4, "event-b-retry", "attempt-b", "task.retry_accepted", "ui-retry-command"),),
    }
    after = {
        **nonterminal_b,
        "event_facts": nonterminal_b["event_facts"]
        + ((5, "event-b-running", "attempt-b", "task.running", "executor-b"),),
    }
    oracle = _P3Oracle([terminal_a, nonterminal_b, after], winner={"operation": "task.retry", "task_id": "task-1"})

    await W2FaultRunner(rpc).probe_p3_non_retriable(fault, "task-1", "session-1", "correlation-1", oracle)

    assert rpc.calls[0][0] == "live_voice.composition.p3.confirmation.issue"
    assert rpc.calls[1][0] == rpc.calls[2][0] == fault.operation
    assert rpc.calls[1][2] == rpc.calls[2][2] == fault.request_id
    assert rpc.calls[1][1] == rpc.calls[2][1]


@pytest.mark.asyncio
async def test_p3_non_retriable_rejects_command_lineage_side_effect() -> None:
    fault = _fault(2, "p3.task", "non_retriable", "live_voice.composition.p3.mutate")
    issue_id = f"{fault.source_record_id}-confirmation"
    failed = _error(fault.request_id, "CONFLICT", "TASK_RETRY_REQUIRES_TERMINAL")
    rpc = _ScriptedRpc(
        [
            _success(
                issue_id,
                {
                    "status": "confirmation_issued",
                    "confirmation_id": "confirmation-probe",
                },
            ),
            failed,
            failed,
        ]
    )
    terminal_a = {
        "task_id": "task-1",
        "attempt_id": "attempt-a",
        "attempt_number": 1,
        "state": "terminal",
        "retry_count": 0,
        "event_facts": (),
    }
    nonterminal_b = {
        "task_id": "task-1",
        "attempt_id": "attempt-b",
        "attempt_number": 2,
        "state": "running",
        "retry_count": 1,
        "event_facts": (),
    }
    after = {
        **nonterminal_b,
        "event_facts": (
            (
                6,
                "event-side-effect",
                "attempt-b",
                "task.running",
                f"{fault.source_record_id}-command",
            ),
        ),
    }
    oracle = _P3Oracle(
        [terminal_a, nonterminal_b, after],
        winner={"operation": "task.retry", "task_id": "task-1"},
    )

    with pytest.raises(Exception, match="command side effects"):
        await W2FaultRunner(rpc).probe_p3_non_retriable(
            fault, "task-1", "session-1", "correlation-1", oracle
        )


@pytest.mark.asyncio
async def test_p3_zero_effect_uses_exact_planned_id_before_fresh_ui_retry() -> None:
    fault = _fault(3, "p3.task", "zero_effect", "live_voice.composition.p3.mutate")
    issue_id = f"{fault.source_record_id}-confirmation"
    failed = _error(fault.request_id, "STALE", "PRODUCT_W2_STALE_FAULT_INJECTED")
    rpc = _ScriptedRpc(
        [
            _success(issue_id, {"status": "confirmation_issued", "confirmation_id": "confirmation-stale"}),
            failed,
            failed,
        ]
    )
    terminal_a = {
        "task_id": "task-1",
        "attempt_id": "attempt-a",
        "attempt_number": 1,
        "state": "terminal",
        "retry_count": 0,
        "event_head": 3,
        "event_facts": ((3, "event-a-terminal", "attempt-a", "task.terminal", "executor-a"),),
    }
    successor_b = {
        "task_id": "task-1",
        "attempt_id": "attempt-b",
        "attempt_number": 2,
        "state": "running",
        "retry_count": 1,
        "event_head": 5,
        "event_facts": ((5, "event-b-running", "attempt-b", "task.running", "executor-b"),),
    }
    oracle = _P3Oracle([terminal_a, dict(terminal_a), successor_b], winner={"operation": "task.retry", "task_id": "task-1"})

    await W2FaultRunner(rpc).probe_p3_zero_effect(fault, "task-1", "session-1", "correlation-1", oracle)

    assert rpc.calls[1][2] == rpc.calls[2][2] == fault.request_id
    assert rpc.calls[1][1] == rpc.calls[2][1]


@pytest.mark.asyncio
async def test_media_transfer_rejects_tampered_attach_and_ack() -> None:
    binding = _media_binding()
    factory = GatewayDedicatedSpeechFactory(
        _ScriptedRpc([]),
        _stock_template(),
        gateway_endpoint="ws://127.0.0.1:8000/ws",
        origin="http://127.0.0.1:3000",
    )
    attach = json.loads(serialize_media_control(MediaAttach(binding)))
    tampered_attach = {**attach, "unexpected": True}
    with pytest.raises(Exception, match="attach is malformed"):
        await factory._transfer(
            _MediaSocket([json.dumps(tampered_attach)]), binding, [b"frame"]
        )

    ack = json.loads(
        serialize_media_control(MediaAck(binding.lease_id, binding.generation.value, 0))
    )
    tampered_ack = {**ack, "unexpected": True}
    socket = _MediaSocket(
        [serialize_media_control(MediaAttach(binding)), json.dumps(tampered_ack)]
    )
    with pytest.raises(Exception, match="ACK is malformed"):
        await factory._transfer(socket, binding, [b"frame"])
    assert socket.sent == [b"frame"]


@pytest.mark.asyncio
async def test_companion_owns_p2_before_media_and_closes_exact_route() -> None:
    owner_label = "companion-owner"
    capture_label = "companion-capture"
    interaction_id = f"{owner_label}-interaction"
    activation_id = f"{owner_label}-activation"
    p2_binding = {
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": interaction_id,
        "activation_id": activation_id,
        "activation_generation": 1,
    }
    media_binding = _media_binding(
        interaction_id=interaction_id,
        capture_id=f"{capture_label}-capture",
        track_id=f"{capture_label}-track",
    )
    media_binding_json = json.loads(
        serialize_media_control(MediaAttach(media_binding))
    )["binding"]
    p2_activate_id = f"{owner_label}-p2-activate"
    media_activate_id = f"{capture_label}-media-activate"
    speech_id = "companion-speech"
    media_close_id = f"{capture_label}-media-close"
    p2_close_id = f"{owner_label}-p2-close"
    rpc = _ScriptedRpc(
        [
            _success(p2_activate_id, {"status": "active", **p2_binding}),
            _direct(
                media_activate_id,
                {
                    "status": "active",
                    "reason_id": "MEDIA_ROUTE_TICKET_ISSUED",
                    "subject_id": "subject-1",
                    "endpoint_path": "/ws/live-voice/media/ticket-1",
                    "subprotocol": "live-voice.media.v1",
                    "ticket_ttl_ms": 30_000,
                    "binding": media_binding_json,
                    "privacy": {
                        "raw_audio_persisted": False,
                        "raw_audio_logged": False,
                        "memory_only": True,
                    },
                },
            ),
            _success(speech_id),
            _direct(
                media_close_id,
                {
                    "status": "closed",
                    "reason_id": "MEDIA_ROUTE_REVOKED",
                    "session_id": "session-1",
                    "subject_id": "subject-1",
                    "correlation_id": "correlation-1",
                    "interaction_id": interaction_id,
                    "activation_id": activation_id,
                    "activation_generation": 1,
                },
            ),
            _success(p2_close_id, {"status": "closed", **p2_binding}),
        ]
    )
    factory = _NoSocketSpeechFactory(
        rpc,
        _stock_template(),
        gateway_endpoint="ws://127.0.0.1:8000/ws",
        origin="http://127.0.0.1:3000",
    )

    await factory.activate(owner_label)
    lease = await factory.create(capture_label)
    await rpc.request("live_voice.speech.recognize_batch", lease.params, request_id=speech_id)
    await lease.close()
    await factory.close()

    assert [call[0] for call in rpc.calls] == [
        "live_voice.composition.p2.activate",
        "live_voice.media.activate",
        "live_voice.speech.recognize_batch",
        "live_voice.media.close",
        "live_voice.composition.p2.close",
    ]
    own_activate = rpc.calls[0][1]
    media_activate = rpc.calls[1][1]
    assert own_activate["interaction_id"] != "stock-interaction"
    assert own_activate["activation_id"] != "stock-activation"
    assert media_activate["interaction_id"] == own_activate["interaction_id"]
    assert media_activate["activation_id"] == own_activate["activation_id"]
    assert rpc.calls[-1][1] == {
        **p2_binding,
        "claimed_user_id": None,
        "claimed_project_id": None,
    }


@pytest.mark.asyncio
async def test_companion_retains_cleanup_after_ambiguous_activation_result() -> None:
    owner_label = "ambiguous-owner"
    requested = {
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": f"{owner_label}-interaction",
        "activation_id": f"{owner_label}-activation",
        "activation_generation": 1,
    }
    activate_id = f"{owner_label}-p2-activate"
    close_id = f"{owner_label}-p2-close"
    rpc = _ScriptedRpc(
        [
            _success(
                activate_id,
                {"status": "active", **requested, "activation_id": "foreign"},
            ),
            _success(close_id, {"status": "closed", **requested}),
        ]
    )
    factory = _NoSocketSpeechFactory(
        rpc,
        _stock_template(),
        gateway_endpoint="ws://127.0.0.1:8000/ws",
        origin="http://127.0.0.1:3000",
    )

    with pytest.raises(Exception, match="activation response binding mismatch"):
        try:
            await factory.activate(owner_label)
        finally:
            await factory.close()

    assert [call[0] for call in rpc.calls] == [
        "live_voice.composition.p2.activate",
        "live_voice.composition.p2.close",
    ]


@pytest.mark.asyncio
async def test_cdp_exchange_requires_normalized_gateway_and_same_socket() -> None:
    observer = ChromeNetworkObserver(
        "http://127.0.0.1:9222",
        gateway_url="ws://127.0.0.1:8000/ws",
        page_origin="http://127.0.0.1:3000",
    )
    gateway_url = "ws://127.0.0.1:8000/ws"
    request = ObservedWebMessage(
        "sent",
        "gateway-socket",
        gateway_url,
        {
            "type": "req",
            "id": "request-1",
            "method": "live_voice.composition.p2.presentation.ack",
            "params": {"session_id": "session-1"},
        },
    )
    foreign_response = ObservedWebMessage(
        "received",
        "other-socket",
        gateway_url,
        {"type": "res", "id": "request-1", "ok": True},
    )
    exact_response = ObservedWebMessage(
        "received",
        "gateway-socket",
        gateway_url,
        {"type": "res", "id": "request-1", "ok": True},
    )
    observer._backlog.extend([request, foreign_response, exact_response])

    _request, response = await observer.wait_exchange(
        "live_voice.composition.p2.presentation.ack"
    )

    assert response == exact_response.message
    assert foreign_response in observer._backlog
    with pytest.raises(Exception, match="read-only allowlist"):
        await observer._command("Runtime.evaluate", {"expression": "1"})


@pytest.mark.asyncio
async def test_chrome_p3_recovery_skips_foreign_task_and_requires_exact_ack_lineage() -> None:
    observer = ChromeNetworkObserver(
        "http://127.0.0.1:9222",
        gateway_url="ws://127.0.0.1:8000/ws",
        page_origin="http://127.0.0.1:3000",
    )
    gateway_url = "ws://127.0.0.1:8000/ws"

    def progress_payload(task_id: str, suffix: str) -> dict[str, Any]:
        return {
            "event_type": "live_voice.task.progress",
            "session_id": "session-1",
            "task_id": task_id,
            "project_id": "project-1",
            "correlation_id": "correlation-1",
            "origin_id": "origin-1",
            "generation_kind": "web_task_progress_generation",
            "generation_id": "generation-1",
            "generation": 1,
            "delivery_id": f"delivery-{suffix}",
            "source_event": {
                "event_id": f"source-{suffix}",
                "event_type": "task.running",
                "seq": 2,
                "extensions": {
                    "jiuwenswarm.task_progress_return": {
                        "persistent_event_seq": 2,
                        "persistent_attempt_id": f"attempt-{suffix}",
                        "persistent_source_event_id": None,
                    }
                },
            },
            "progress_event": {"event_id": f"progress-{suffix}", "seq": 2},
            "evidence_id": f"evidence-{suffix}",
        }

    foreign_payload = progress_payload("task-foreign", "foreign")
    exact_payload = progress_payload("task-1", "exact")
    expected_ack = {
        "session_id": "session-1",
        "task_id": "task-1",
        "correlation_id": "correlation-1",
        "origin_id": "origin-1",
        "generation_id": "generation-1",
        "generation": 1,
        "delivery_id": "delivery-exact",
        "source_event_id": "source-exact",
        "progress_event_id": "progress-exact",
        "seq": 2,
        "evidence_id": "evidence-exact",
    }
    foreign_event = ObservedWebMessage(
        "received",
        "gateway-socket",
        gateway_url,
        {
            "type": "event",
            "event": "live_voice.task.progress",
            "payload": foreign_payload,
        },
    )
    exact_event = ObservedWebMessage(
        "received",
        "gateway-socket",
        gateway_url,
        {
            "type": "event",
            "event": "live_voice.task.progress",
            "payload": exact_payload,
        },
    )
    ack_request = ObservedWebMessage(
        "sent",
        "gateway-socket",
        gateway_url,
        {
            "type": "req",
            "id": "stock-ack-1",
            "method": "live_voice.composition.p3.progress.ack",
            "params": expected_ack,
        },
    )
    ack_response = ObservedWebMessage(
        "received",
        "gateway-socket",
        gateway_url,
        _success(
            "stock-ack-1",
            {
                **expected_ack,
                "status": "acknowledged",
                "attempt_id": "attempt-exact",
                "acknowledgement": "web_ui_text_consumed",
                "replayed": False,
            },
        ),
    )
    observer._backlog.extend(
        [foreign_event, exact_event, ack_request, ack_response]
    )
    oracle = ChromeP3Oracle(
        _ScriptedRpc([]),
        observer,
        session_id="session-1",
        request_prefix="oracle",
    )

    recovered = await oracle.wait_stock_progress_ack(
        after_delivery_id="delivery-before",
        expected_session_id="session-1",
        expected_task_id="task-1",
    )

    assert recovered == {
        "delivery_id": "delivery-exact",
        "attempt_id": "attempt-exact",
        "session_id": "session-1",
        "task_id": "task-1",
        "source_event_id": "source-exact",
        "progress_event_id": "progress-exact",
        "status": "acknowledged",
        "source": "stock_ui",
        "request_id": "stock-ack-1",
    }
    assert foreign_event in observer._backlog


def test_cdp_target_requires_exact_stock_page_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer = ChromeNetworkObserver(
        "http://127.0.0.1:9222",
        gateway_url="ws://127.0.0.1:8000/ws",
        page_origin="http://127.0.0.1:3000",
    )
    target = [
        {
            "type": "page",
            "url": "http://127.0.0.1:3999/live-voice",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
        }
    ]
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: io.BytesIO(json.dumps(target).encode("utf-8")),
    )

    with pytest.raises(Exception, match="page origin"):
        observer._discover_target()


@pytest.mark.asyncio
async def test_observation_and_gateway_event_waits_have_one_noisy_deadline() -> None:
    observer = ChromeNetworkObserver(
        "http://127.0.0.1:9222",
        gateway_url="ws://127.0.0.1:8000/ws",
        page_origin="http://127.0.0.1:3000",
    )
    for index in range(200):
        observer._messages.put_nowait(
            ObservedWebMessage(
                "sent",
                "gateway-socket",
                "ws://127.0.0.1:8000/ws",
                {"type": "event", "event": f"noise-{index}"},
            )
        )
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            observer.wait_message(lambda _item: False, timeout=0.01), timeout=0.1
        )

    gateway = GatewayWebSocketClient(
        "ws://127.0.0.1:8000/ws",
        origin="http://127.0.0.1:3000",
    )
    for index in range(200):
        gateway._events.put_nowait({"type": "event", "event": f"noise-{index}"})
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            gateway.wait_event("target", timeout=0.01), timeout=0.1
        )


@pytest.mark.asyncio
async def test_probe_rejects_p3_bearer_before_gateway_rpc() -> None:
    runner = W2FaultRunner(_ScriptedRpc([]))
    with pytest.raises(Exception, match="credential"):
        await runner.send_raw_for_test(
            "live_voice.composition.p3.mutate",
            {"auth_token": "forbidden"},
            request_id="request-1",
        )


def test_observed_stock_template_rejects_credential_material() -> None:
    stock = _stock_template()
    credentialed = dict(stock.p2_activation_params)
    credentialed["auth_token"] = "must-remain-server-side"
    with pytest.raises(Exception, match="credential"):
        StockSpeechTemplate(
            p2_activation_params=credentialed,
            media_activation_params=stock.media_activation_params,
            speech_params=stock.speech_params,
        )


def test_runner_consumes_exact_public_nine_item_fault_plan() -> None:
    plan = derive_public_fault_plan(
        policy_id="policy-1",
        candidate_sha="a" * 40,
        evidence_set_id="evidence-set-1",
    )

    assert len(plan.items) == 9
    assert {item.pair for item in plan.items} == {1, 2, 3}
    assert all(item.request_id.startswith("w2-fault-") for item in plan.items)


@pytest.mark.asyncio
async def test_p1_runner_contract_matches_real_fault_seam() -> None:
    from jiuwenswarm.server.live_voice.batch_speech import (
        BatchSpeechP1RetriableFaultPlan,
    )
    from tests.unit_tests.live_voice.test_batch_speech import (
        CONTEXT,
        ControlledProvider,
        _recognize_request,
        _service,
    )

    fault = _fault(1, "p1.speech_media", "retriable", "speech.recognize.batch")
    provider = ControlledProvider()
    service = _service(
        provider,
        p1_retriable_fault_plan=BatchSpeechP1RetriableFaultPlan(
            request_id=fault.request_id,
            operation="speech.recognize.batch",
        ),
    )

    class ServiceRpc:
        async def request(
            self, method: str, params: dict[str, Any], *, request_id: str
        ) -> dict[str, Any]:
            assert method == "live_voice.speech.recognize_batch"
            payload = await service.recognize(params, CONTEXT)
            return _direct(request_id, payload)

    class RealSpeechFactory:
        async def create(self, label: str) -> _SpeechLease:
            lease = _SpeechLease(label)
            lease.params = _recognize_request(
                request_id=f"{label}-inner",
                operation_id=f"{label}-operation",
                capture_id=f"{label}-capture",
            )
            return lease

    await W2FaultRunner(ServiceRpc()).probe_p1_retriable(
        fault, RealSpeechFactory()
    )

    assert provider.recognize_calls == 1


@pytest.mark.asyncio
async def test_p2_zero_runner_contract_matches_real_stale_seam(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jiuwenswarm.server.live_voice.product_composition_registry import (
        ProductP2StaleFaultPlan,
    )
    from tests.unit_tests.live_voice.test_product_composition_registry import (
        NOW,
        _p2_params,
        _registry,
    )

    fault = _fault(
        3,
        "p2.conversation",
        "zero_effect",
        "live_voice.composition.p2.presentation.ack",
    )
    registry, _p3, _manager, _pushed = _registry(
        tmp_path,
        p2_stale_fault_plan=ProductP2StaleFaultPlan(
            request_id=fault.request_id,
            operation=fault.operation,
        ),
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.product_composition_registry._server_agent_mode",
        lambda _session_id: ("code", "normal"),
    )
    activated = await registry.handle_p2_activate(
        params=_p2_params(),
        request_id="runner-production-activate",
        session_id="session-product",
        channel_id="web",
    )
    assert activated.ok is True
    route = registry._p2_routes[("session-product", "interaction-1")]
    acknowledgements: list[object] = []

    async def acknowledge(*args: object) -> object:
        acknowledgements.append(args)
        return SimpleNamespace(
            accepted=True,
            replayed=False,
            history_records_written=0,
            history_pending=False,
        )

    monkeypatch.setattr(route.activation_lease, "acknowledge_presentation", acknowledge)
    server_canonical = _p2_params(
        response_id="response-runner-stale",
        response_generation=1,
        surface="text",
        unit_id="unit-runner-stale",
        contiguous_cursor=1,
        presented_at=NOW,
    )
    canonical = dict(server_canonical)
    canonical.pop("auth_token")

    class RegistryRpc:
        async def request(
            self, method: str, params: dict[str, Any], *, request_id: str
        ) -> dict[str, Any]:
            assert method == "live_voice.composition.p2.presentation.ack"
            result = await registry.handle_p2_presentation_ack(
                params={**params, "auth_token": server_canonical["auth_token"]},
                request_id=request_id,
                session_id="session-product",
            )
            return _direct(request_id, dict(result.payload))

    try:
        await W2FaultRunner(RegistryRpc()).probe_p2_zero_effect(fault, canonical)
        assert len(acknowledgements) == 1
        assert registry._p2_stale_fault_consumed is True
    finally:
        await registry.close_active_routes()


def test_runner_has_no_direct_authority_or_persistence_imports() -> None:
    from pathlib import Path

    source = Path(W2FaultRunner.__module__.replace(".", "/") + ".py")
    if not source.exists():
        source = Path("scripts/live_voice/w2_rehearsal/w2_fault_runner.py")
    text = source.read_text(encoding="utf-8")
    forbidden = (
        "product_composition_registry",
        "persistent_task_core",
        "task_core",
        "task_store",
        "w2_demo_gate",
        "product_w2_observability",
        "sqlite3",
        "jsonlines",
        "localStorage",
        "struct.pack",
        "hashlib",
        "Runtime.evaluate",
        "DOM.",
        "Input.",
    )
    assert all(item not in text for item in forbidden)
    assert "encode_audio_frame" in text
    assert "deserialize_media_control" in text
    assert "W2_FAULT_RUNNER_PAIR_PASS" not in text
    assert "W2_FAULT_RUNNER_PRODUCT_FAULTS_PASS" in text
    assert text.count("W2_FAULT_RUNNER_PRODUCT_FAULTS_PASS") == 1
