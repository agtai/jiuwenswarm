# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Closed JSON-line fixture for the EOT/STT settlement causal benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Mapping

from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAudioFrame,
    MediaDetachReason,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_registration import (
    DedicatedMediaProductRegistry,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
    DedicatedMediaSocketLeafResult,
)
from jiuwenswarm.gateway.live_voice.streaming_speech_route import (
    StreamingRecognitionRouteOwner,
)
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    SpeechRouteTier,
    StreamingSpeechSelection,
)
from jiuwenswarm.server.live_voice.speech_ports import (
    ProviderRef,
    RecognitionAlternative,
    RecognitionEventKind,
    RecognitionHypothesis,
    SpeechMode,
)
from jiuwenswarm.server.live_voice.streaming_speech import (
    CapabilityProvenance,
    ProviderTransport,
    RecognitionCommitDisposition,
    RecognitionProviderSupport,
    StreamingProviderCapability,
    StreamingRecognitionEvent,
    SynthesisProviderSupport,
)


_ALLOWED_DELAYS_MS = frozenset({50, 500})
_MAX_LINE_BYTES = 4096
_REQUEST_ORIGIN = "https://voice.example.test"
_SESSION_ID = "session-1"
_CONNECTION_ID = "connection-1"
_USER_ID = "user-1"
_INTERACTION_ID = "interaction-1"
_CORRELATION_ID = "correlation-1"
_ACTIVATION_ID = "activation-1"
_CAPTURE_ID = "capture-1"
_TRACK_ID = "track-1"
_FINAL_TEXT = "benchmark recognition"
_RECEIPT = "eot-stt-benchmark-receipt-12345678901234567890"
_PROVIDER_REF = ProviderRef("eot-stt-benchmark-provider", "formal")
_REJECTED = {
    "status": "rejected",
    "reason_id": "EOT_STT_FIXTURE_REQUEST_REJECTED",
}


def _capability() -> StreamingProviderCapability:
    return StreamingProviderCapability(
        provider=_PROVIDER_REF,
        recognition=RecognitionProviderSupport(
            modes=frozenset({SpeechMode.STREAM}),
            transport=ProviderTransport.NATIVE_STREAM,
            ordered_events=CapabilityProvenance.PROVIDER_NATIVE,
            exact_audio_cursor=CapabilityProvenance.ADAPTER_DERIVED,
            provider_cancel_ack=CapabilityProvenance.UNAVAILABLE,
            native_partials=CapabilityProvenance.PROVIDER_NATIVE,
            server_vad=CapabilityProvenance.UNAVAILABLE,
        ),
        synthesis=SynthesisProviderSupport(
            modes=frozenset({SpeechMode.STREAM}),
            transport=ProviderTransport.NATIVE_STREAM,
            ordered_events=CapabilityProvenance.PROVIDER_NATIVE,
            exact_audio_cursor=CapabilityProvenance.ADAPTER_DERIVED,
        ),
    )


class _BenchmarkProvider:
    """Minimal deterministic Provider Port adapter; it owns no product policy."""

    capability = _capability()
    fallback_tier = SpeechRouteTier.BATCH

    def __init__(self) -> None:
        self._ref = None
        self._final_ready = asyncio.Event()
        self._committed = asyncio.Event()
        self._sample_count = 0
        self._closed = False

    async def open_recognition(self, request, *, timeout_seconds: float) -> None:
        del timeout_seconds
        self._ref = request.ref

    async def send_recognition_audio(self, frame) -> None:
        self._sample_count += frame.sample_count

    async def commit_recognition(self, ref) -> RecognitionCommitDisposition:
        if self._closed or ref != self._ref:
            raise RuntimeError("benchmark Provider authority is unavailable")
        self._committed.set()
        return RecognitionCommitDisposition.CLIENT_COMMIT_SENT

    async def next_recognition_event(self, ref, *, timeout_seconds: float):
        del timeout_seconds
        if self._closed or ref != self._ref:
            raise RuntimeError("benchmark Provider authority is unavailable")
        await self._final_ready.wait()
        await self._committed.wait()
        return StreamingRecognitionEvent(
            ref=ref,
            provider=_PROVIDER_REF,
            seq=0,
            audio_cursor=self._sample_count,
            kind=RecognitionEventKind.FINAL,
            hypothesis=RecognitionHypothesis(
                (RecognitionAlternative(_FINAL_TEXT, _FINAL_TEXT, None),)
            ),
        )

    async def release_final(self) -> None:
        ref = self._ref
        if self._closed or ref is None or self._final_ready.is_set():
            raise RuntimeError("benchmark Provider final is unavailable")
        self._final_ready.set()

    async def cancel_recognition(self, ref, *, reason: str = "caller_cancel") -> None:
        del ref, reason

    async def close(self) -> None:
        self._closed = True


def _activation_params() -> dict[str, object]:
    return {
        "session_id": _SESSION_ID,
        "interaction_id": _INTERACTION_ID,
        "correlation_id": _CORRELATION_ID,
        "activation_id": _ACTIVATION_ID,
        "activation_generation": 1,
        "capture_id": _CAPTURE_ID,
        "capture_generation": 1,
        "track_id": _TRACK_ID,
        "sample_rate_hz": 16_000,
        "locale": "en-US",
    }


def _trust_activation(registry: DedicatedMediaProductRegistry) -> None:
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "active",
                "session_id": _SESSION_ID,
                "correlation_id": _CORRELATION_ID,
                "interaction_id": _INTERACTION_ID,
                "activation_id": _ACTIVATION_ID,
                "activation_generation": 1,
            },
            "product_composition": {
                "contract_version": "live-voice.product-composition.gate0.v1",
                "enabled": True,
                "routes": [
                    {
                        "segment": "p2.agent_interaction",
                        "truth": "formal",
                        "reason_id": "FORMAL_ROUTE_OBSERVED",
                        "evidence_ids": [
                            "TRUSTED_AUTHORITY_RESOLVED",
                            "FORMAL_ACTIVATION_LEASE_OPEN",
                            "RUNTIME_PATH_OBSERVED",
                            "P2_NOTIFICATION_BACKPRESSURE_CLOSED",
                        ],
                        "formal_runtime_observed": True,
                    }
                ],
            },
        },
        routed_session_id=_SESSION_ID,
        user_id=_USER_ID,
        connection_id=_CONNECTION_ID,
        request_method="live_voice.composition.p2.activate",
    )


class EotSttRegistryFixture:
    """Exact real-registry authority fixture with five closed operations."""

    def __init__(self, *, local_settlement_ms: int, provider_final_ms: int) -> None:
        if (
            isinstance(local_settlement_ms, bool)
            or not isinstance(local_settlement_ms, int)
            or local_settlement_ms not in _ALLOWED_DELAYS_MS
            or isinstance(provider_final_ms, bool)
            or not isinstance(provider_final_ms, int)
            or provider_final_ms not in _ALLOWED_DELAYS_MS
        ):
            raise ValueError("EOT_STT_FIXTURE_ARGUMENT_INVALID")
        self.local_settlement_ms = local_settlement_ms
        self.provider_final_ms = provider_final_ms
        self.session_id = _SESSION_ID
        self.connection_id = _CONNECTION_ID
        self.request_origin = _REQUEST_ORIGIN
        self.registry = DedicatedMediaProductRegistry(enabled=True)
        self._provider = _BenchmarkProvider()
        self._owner = StreamingRecognitionRouteOwner(
            lambda: asyncio.sleep(
                0,
                result=StreamingSpeechSelection(
                    SpeechRouteTier.STREAMING,
                    self._provider,
                    None,
                ),
            )
        )
        self.registry.configure_streaming_recognition(
            self._owner,
            receipt_issuer=self._issue_receipt,
        )
        self._record = None
        self._exact_result_params: dict[str, object] | None = None
        self._opened = False
        self._route_settled = False
        self._provider_final = False
        self._result_returned = False
        self._close_requested = False
        self._closed = False
        self._cleanup_abort_complete = False
        self._cleanup_owner_complete = False
        self._cleanup_observability_complete = False
        self._cleanup_diagnostics_complete = False
        self._cleanup_media_complete = False

    @property
    def exact_result_params(self) -> Mapping[str, object]:
        if self._exact_result_params is None:
            raise RuntimeError("benchmark fixture is not open")
        return self._exact_result_params

    async def _issue_receipt(self, **binding: object) -> str:
        if binding.get("text") != _FINAL_TEXT:
            raise RuntimeError("benchmark receipt binding is invalid")
        return _RECEIPT

    async def _open(self) -> dict[str, object]:
        if self._opened or self._close_requested:
            raise RuntimeError("benchmark fixture state is invalid")
        os.environ["JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS"] = "voice.example.test"
        await self.registry.prepare_streaming_provider()
        _trust_activation(self.registry)
        activation_params = _activation_params()
        activation = self.registry.activate(
            params=activation_params,
            request_origin=self.request_origin,
            connection_id=self.connection_id,
            user_id=_USER_ID,
        )
        if (
            activation.get("status") != "active"
            or activation.get("streaming_recognition") is not True
        ):
            raise RuntimeError("benchmark fixture activation is unavailable")
        record = self.registry.consume_ticket(
            str(activation["media_ticket"]),
            request_origin=self.request_origin,
        )
        if record is None:
            raise RuntimeError("benchmark fixture record is unavailable")
        await self.registry.begin_streaming_recognition(record)
        frame = MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.0,) * 320)
        self.registry.accept_frame(record, frame)
        self.registry.accept_streaming_frame(record, frame)
        self._record = record
        self._exact_result_params = {
            "session_id": self.session_id,
            "subject_id": activation["subject_id"],
            "correlation_id": activation_params["correlation_id"],
            "interaction_id": activation_params["interaction_id"],
            "capture_id": activation_params["capture_id"],
            "capture_generation": activation_params["capture_generation"],
            "track_id": activation_params["track_id"],
        }
        self._opened = True
        return {"status": "opened"}

    async def _settle_route(self) -> dict[str, object]:
        if (
            not self._opened
            or self._route_settled
            or self._close_requested
            or self._record is None
        ):
            raise RuntimeError("benchmark fixture state is invalid")
        await asyncio.sleep(self.local_settlement_ms / 1000)
        self.registry.complete_route(
            self._record,
            DedicatedMediaSocketLeafResult(
                activated=True,
                socket_touched=True,
                attach_sent=True,
                accepted_frames=1,
                close_result=None,
                reason_id=MediaDetachReason.LOCAL_CLOSE,
            ),
        )
        self._route_settled = True
        return {"status": "route_settled", "elapsed_ms": self.local_settlement_ms}

    async def _release_provider_final(self) -> dict[str, object]:
        if not self._opened or self._provider_final or self._close_requested:
            raise RuntimeError("benchmark fixture state is invalid")
        await asyncio.sleep(self.provider_final_ms / 1000)
        await self._provider.release_final()
        self._provider_final = True
        return {"status": "provider_final", "elapsed_ms": self.provider_final_ms}

    def is_exact(self, payload: Mapping[str, object]) -> bool:
        capture = payload.get("capture")
        provider = payload.get("provider")
        return bool(
            payload.get("status") == "completed"
            and payload.get("operation") == "speech.recognize.stream"
            and payload.get("final_text") == _FINAL_TEXT
            and payload.get("raw_text") == _FINAL_TEXT
            and payload.get("commits_turn") is False
            and payload.get("voice_commit_receipt") == _RECEIPT
            and payload.get("degradation") is None
            and isinstance(capture, dict)
            and capture
            == {
                "capture_id": _CAPTURE_ID,
                "capture_generation": 1,
                "track_id": _TRACK_ID,
                "final": True,
            }
            and isinstance(provider, dict)
            and provider
            == {
                "provider_id": _PROVIDER_REF.provider_id,
                "implementation_class": _PROVIDER_REF.implementation_class,
                "fallback_from": _PROVIDER_REF.fallback_from,
            }
        )

    async def _streaming_result(self) -> dict[str, object]:
        if (
            not self._opened
            or not self._route_settled
            or not self._provider_final
            or self._result_returned
            or self._close_requested
            or self._record is None
        ):
            raise RuntimeError("benchmark fixture state is invalid")
        await self.registry.finish_streaming_recognition(self._record)
        payload = await self.registry.streaming_recognition_result(
            params=self.exact_result_params,
            routed_session_id=self.session_id,
            connection_id=self.connection_id,
            request_origin=self.request_origin,
        )
        exact = self.is_exact(payload)
        if not exact:
            raise RuntimeError("benchmark registry result is inexact")
        self._result_returned = True
        return {
            "status": payload["status"],
            "exact_result": exact,
            "business_result": payload,
        }

    async def _close(self) -> dict[str, object]:
        if self._closed:
            return {"status": "closed", "cleanup_complete": True}
        self._close_requested = True
        if not self._cleanup_abort_complete:
            if self._record is None or self._result_returned:
                self._cleanup_abort_complete = True
            else:
                try:
                    await self.registry.abort_streaming_recognition(self._record)
                except (Exception, asyncio.CancelledError):
                    pass
                else:
                    self._cleanup_abort_complete = True
        if not self._cleanup_owner_complete:
            try:
                await self._owner.close()
            except (Exception, asyncio.CancelledError):
                pass
            else:
                self._cleanup_owner_complete = True
        if not self._cleanup_observability_complete:
            try:
                self.registry.close_streaming_observability()
            except Exception:
                pass
            else:
                self._cleanup_observability_complete = True
        if not self._cleanup_diagnostics_complete:
            try:
                self._cleanup_diagnostics_complete = (
                    self.registry.close_streaming_diagnostics() is True
                )
            except Exception:
                pass
        if not self._cleanup_media_complete:
            try:
                self._cleanup_media_complete = (
                    await self.registry.close_media_leaf_cleanup()
                ) is True
            except (Exception, asyncio.CancelledError):
                pass
        cleanup_complete = all(
            (
                self._cleanup_abort_complete,
                self._cleanup_owner_complete,
                self._cleanup_observability_complete,
                self._cleanup_diagnostics_complete,
                self._cleanup_media_complete,
            )
        )
        self._closed = cleanup_complete
        return {
            "status": "closed",
            "cleanup_complete": cleanup_complete,
        }

    async def handle(self, request: object) -> dict[str, object]:
        try:
            if not isinstance(request, dict) or set(request) != {"operation"}:
                raise RuntimeError("benchmark fixture request is invalid")
            operation = request.get("operation")
            if operation == "open":
                return await self._open()
            if operation == "provider_final":
                return await self._release_provider_final()
            if operation == "route_settled":
                return await self._settle_route()
            if operation == "streaming_result":
                return await self._streaming_result()
            if operation == "close":
                return await self._close()
        except (Exception, asyncio.CancelledError):
            return dict(_REJECTED)
        return dict(_REJECTED)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--local-settlement-ms", type=int, required=True)
    parser.add_argument("--provider-final-ms", type=int, required=True)
    args = parser.parse_args(argv)
    if (
        args.local_settlement_ms not in _ALLOWED_DELAYS_MS
        or args.provider_final_ms not in _ALLOWED_DELAYS_MS
    ):
        parser.error("EOT_STT_FIXTURE_ARGUMENT_INVALID")
    return args


async def _read_bounded_line() -> tuple[bytes, bool]:
    line = await asyncio.to_thread(
        sys.stdin.buffer.readline,
        _MAX_LINE_BYTES + 1,
    )
    if line == b"":
        return line, False
    oversized = len(line) > _MAX_LINE_BYTES or not line.endswith(b"\n")
    while line != b"" and not line.endswith(b"\n"):
        line = await asyncio.to_thread(
            sys.stdin.buffer.readline,
            _MAX_LINE_BYTES + 1,
        )
    return (b"" if oversized else line), oversized


async def _serve(fixture: EotSttRegistryFixture) -> int:
    try:
        while True:
            line, oversized = await _read_bounded_line()
            if line == b"" and not oversized:
                break
            if oversized:
                response = dict(_REJECTED)
            else:
                try:
                    request = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    request = None
                response = await fixture.handle(request)
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
            if (
                response.get("status") == "closed"
                and response.get("cleanup_complete") is True
            ):
                return 0
        cleanup = await fixture._close()
        return 0 if cleanup.get("cleanup_complete") is True else 1
    except BaseException:
        await fixture._close()
        return 1


def main(argv: list[str] | None = None) -> int:
    logging.disable(logging.CRITICAL)
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    fixture = EotSttRegistryFixture(
        local_settlement_ms=args.local_settlement_ms,
        provider_final_ms=args.provider_final_ms,
    )
    return asyncio.run(_serve(fixture))


if __name__ == "__main__":
    raise SystemExit(main())
