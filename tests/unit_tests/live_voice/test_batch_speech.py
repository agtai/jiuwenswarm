# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import io
import json
import sys
import wave
from array import array
from collections.abc import Callable
from dataclasses import replace

import httpx
import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ResponseRef,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.batch_speech import (
    CANCEL_OPERATION,
    FORMAL_BATCH_SPEECH_FLAG,
    MAX_SYNTHESIS_AUDIO_BYTES,
    RECOGNIZE_OPERATION,
    SPEECH_API_BASE_ENV,
    SPEECH_API_KEY_ENV,
    SPEECH_PROVIDER_ENV,
    SPEECH_STT_MODEL_ENV,
    SPEECH_TTS_MODEL_ENV,
    SPEECH_TTS_VOICE_ENV,
    SYNTHESIZE_OPERATION,
    BatchSpeechError,
    BatchSpeechProvider,
    FormalBatchSpeechService,
    OpenAICompatibleBatchSpeechProvider,
    OpenAICompatibleSpeechConfig,
    ProviderCapability,
    ProviderRecognitionRequest,
    ProviderRecognitionResult,
    ProviderSynthesisRequest,
    ProviderSynthesisResult,
    SpeechAuthorizationBinding,
    SpeechAuthorizationResolver,
    SpeechRpcContext,
    UnavailableBatchSpeechProvider,
    create_environment_batch_speech_provider,
    inspect_pcm16_mono_wav,
)


def _wav(sample_rate: int = 16_000, frames: int = 320) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * frames)
    return output.getvalue()


def _pcm16_samples(samples: list[int]) -> bytes:
    pcm = array("h", samples)
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()


def _read_wav_samples(audio: bytes) -> tuple[int, int, int, list[int]]:
    with wave.open(io.BytesIO(audio), "rb") as wav:
        sample_rate = wav.getframerate()
        channel_count = wav.getnchannels()
        sample_width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    return sample_rate, channel_count, sample_width, samples.tolist()


def _openai_provider_returning(audio: bytes) -> OpenAICompatibleBatchSpeechProvider:
    return OpenAICompatibleBatchSpeechProvider(
        OpenAICompatibleSpeechConfig(
            "https://speech.example.test/v1",
            "server-secret",
            None,
            "tts-model",
            "voice-model",
        ),
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=audio, request=request)
            )
        ),
    )


class ControlledProvider(BatchSpeechProvider):
    def __init__(self, *, delay: bool = False) -> None:
        self.recognize_calls = 0
        self.synthesize_calls = 0
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.release = asyncio.Event()
        self.delay = delay

    def capability(self) -> ProviderCapability:
        return ProviderCapability("controlled-speech", True, True, True)

    async def recognize(
        self, request: ProviderRecognitionRequest
    ) -> ProviderRecognitionResult:
        self.recognize_calls += 1
        self.started.set()
        try:
            if self.delay:
                await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        assert request.audio_wav.startswith(b"RIFF")
        return ProviderRecognitionResult("hello formal speech", "en", "stt-test")

    async def synthesize(
        self, request: ProviderSynthesisRequest
    ) -> ProviderSynthesisResult:
        self.synthesize_calls += 1
        self.started.set()
        try:
            if self.delay:
                await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return ProviderSynthesisResult(
            _wav(request.required_sample_rate_hz),
            "tts-test",
            request.voice or "voice-test",
        )


class CriticalTextProvider(ControlledProvider):
    async def recognize(
        self, request: ProviderRecognitionRequest
    ) -> ProviderRecognitionResult:
        self.recognize_calls += 1
        assert request.audio_wav.startswith(b"RIFF")
        return ProviderRecognitionResult("delete 3 files", "en", "stt-critical-test")


class CancellationDefiantProvider(ControlledProvider):
    def __init__(self, *, swallow_continuously: bool) -> None:
        super().__init__()
        self.swallow_continuously = swallow_continuously
        self.cancel_count = 0
        self.returned = asyncio.Event()

    async def recognize(
        self, request: ProviderRecognitionRequest
    ) -> ProviderRecognitionResult:
        self.recognize_calls += 1
        self.started.set()
        while not self.release.is_set():
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancel_count += 1
                self.cancelled.set()
                if not self.swallow_continuously:
                    await self.release.wait()
        assert request.audio_wav.startswith(b"RIFF")
        self.returned.set()
        return ProviderRecognitionResult("late text", "en", "stt-defiant")

    async def synthesize(
        self, request: ProviderSynthesisRequest
    ) -> ProviderSynthesisResult:
        self.synthesize_calls += 1
        self.started.set()
        while not self.release.is_set():
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancel_count += 1
                self.cancelled.set()
                if not self.swallow_continuously:
                    await self.release.wait()
        self.returned.set()
        return ProviderSynthesisResult(
            _wav(request.required_sample_rate_hz),
            "tts-defiant",
            request.voice or "voice-defiant",
        )


class CancelToSuccessProvider(ControlledProvider):
    """Adversarial Provider that turns the cancellation signal into success."""

    def __init__(self) -> None:
        super().__init__()
        self.returned = asyncio.Event()

    async def recognize(
        self, request: ProviderRecognitionRequest
    ) -> ProviderRecognitionResult:
        self.recognize_calls += 1
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
        assert request.audio_wav.startswith(b"RIFF")
        self.returned.set()
        return ProviderRecognitionResult("cancel became success", "en", "stt-defiant")


class DeadlineMonopolizingProvider(ControlledProvider):
    """Returns after the absolute deadline before its timer callback can run."""

    def __init__(self) -> None:
        super().__init__()
        self.returned = asyncio.Event()

    async def recognize(
        self, request: ProviderRecognitionRequest
    ) -> ProviderRecognitionResult:
        self.recognize_calls += 1
        self.started.set()
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        await asyncio.sleep(0.02)
        while loop.time() - started_at < 0.13:
            pass
        assert request.audio_wav.startswith(b"RIFF")
        self.returned.set()
        return ProviderRecognitionResult("overdue success", "en", "stt-overdue")


class ErrorSignalingProvider(ControlledProvider):
    def __init__(self) -> None:
        super().__init__()
        self.failed = asyncio.Event()

    async def recognize(
        self, request: ProviderRecognitionRequest
    ) -> ProviderRecognitionResult:
        del request
        self.recognize_calls += 1
        self.started.set()
        self.failed.set()
        raise RuntimeError("adversarial Provider failure")


class ExactAuthorizationResolver(SpeechAuthorizationResolver):
    def __init__(
        self,
        transform: Callable[
            [SpeechAuthorizationBinding], SpeechAuthorizationBinding | None
        ]
        | None = None,
    ) -> None:
        self.calls: list[SpeechAuthorizationBinding] = []
        self._transform = transform

    def authorize(
        self, binding: SpeechAuthorizationBinding
    ) -> SpeechAuthorizationBinding | None:
        self.calls.append(binding)
        if self._transform is None:
            return binding
        return self._transform(binding)


def _service(
    provider: BatchSpeechProvider,
    *,
    resolver: SpeechAuthorizationResolver | None = None,
    max_completed_operations: int = 128,
    max_identity_tombstones: int = 512,
) -> FormalBatchSpeechService:
    return FormalBatchSpeechService(
        provider,
        authorization_resolver=resolver or ExactAuthorizationResolver(),
        max_completed_operations=max_completed_operations,
        max_identity_tombstones=max_identity_tombstones,
    )


CONTEXT = SpeechRpcContext("alice", "session-1", Assurance.AUTHENTICATED)
SCOPE = {
    "subject_id": "alice",
    "project_id": None,
    "session_id": "session-1",
    "assurance": "authenticated",
}


def _recognize_request(
    *,
    request_id: str = "request-r0",
    operation_id: str = "operation-r0",
    capture_id: str = "capture-1",
    generation: int = 1,
    locale: str = "en-US",
    timeout_ms: int = 1000,
) -> dict[str, object]:
    return {
        "contract_version": "live-voice.contract.v2",
        "request_id": request_id,
        "operation_id": operation_id,
        "operation": RECOGNIZE_OPERATION,
        "correlation_id": "correlation-1",
        "session_id": "session-1",
        "scope": dict(SCOPE),
        "timeout_ms": timeout_ms,
        "capture": {
            "capture_id": capture_id,
            "capture_generation": generation,
            "track_id": "track-1",
            "final": True,
        },
        "audio": {
            "format": "wav_pcm16_mono",
            "sample_rate_hz": 16_000,
            "channel_count": 1,
            "data_base64": base64.b64encode(_wav()).decode("ascii"),
        },
        "locale": locale,
    }


def _synthesize_request(
    *,
    request_id: str = "request-s0",
    operation_id: str = "operation-s0",
    generation: int = 0,
    timeout_ms: int = 1000,
) -> dict[str, object]:
    return {
        "contract_version": "live-voice.contract.v2",
        "request_id": request_id,
        "operation_id": operation_id,
        "operation": SYNTHESIZE_OPERATION,
        "correlation_id": "correlation-1",
        "session_id": "session-1",
        "scope": dict(SCOPE),
        "timeout_ms": timeout_ms,
        "response": {
            "interaction_id": "interaction-1",
            "response_id": f"response-{generation}",
            "response_generation": generation,
        },
        "unit_id": "unit-1",
        "render_plan": {
            "display_text": "Hello formal speech",
            "spoken_text": "Hello formal speech",
            "transforms": [],
        },
        "authoritative_agent_text": True,
        "locale": "en-US",
        "voice": None,
        "required_sample_rate_hz": 16_000,
    }


def _cancel_request(target: str) -> dict[str, object]:
    return {
        "contract_version": "live-voice.contract.v2",
        "request_id": "request-cancel",
        "operation_id": "operation-cancel",
        "operation": CANCEL_OPERATION,
        "correlation_id": "correlation-1",
        "session_id": "session-1",
        "scope": dict(SCOPE),
        "target_operation_id": target,
    }


@pytest.mark.asyncio
async def test_formal_recognition_and_synthesis_return_exact_provenance() -> None:
    provider = ControlledProvider()
    resolver = ExactAuthorizationResolver()
    service = _service(provider, resolver=resolver)

    recognized = await service.recognize(_recognize_request(), CONTEXT)
    synthesized = await service.synthesize(_synthesize_request(), CONTEXT)

    assert recognized["ok"] is True
    recognition_result = recognized["result"]
    assert recognition_result["event"]["kind"] == "final"
    assert recognition_result["event"]["generation"] == 1
    assert recognition_result["event"]["commits_turn"] is False
    assert recognition_result["provider"] == {
        "provider_id": "controlled-speech",
        "implementation_class": "formal",
        "model": "stt-test",
        "fallback_from": None,
    }
    assert synthesized["ok"] is True
    synthesis_result = synthesized["result"]
    assert synthesis_result["presented"] is False
    assert synthesis_result["audio"]["format"] == "wav_pcm16_mono"
    assert synthesis_result["provider"]["implementation_class"] == "formal"
    completed_cancel = await service.cancel(_cancel_request("operation-r0"), CONTEXT)
    assert completed_cancel["result"]["provider_completion_known"] is True
    assert [binding.operation for binding in resolver.calls] == [
        RECOGNIZE_OPERATION,
        SYNTHESIZE_OPERATION,
    ]
    assert resolver.calls[1].response == ResponseRef("interaction-1", "response-0", 0)
    assert resolver.calls[1].unit_id == "unit-1"
    assert len(resolver.calls[1].content_sha256) == 64
    assert provider.recognize_calls == 1
    assert provider.synthesize_calls == 1


@pytest.mark.asyncio
async def test_voice_commit_receipt_is_exact_replayable_and_cannot_rebind() -> None:
    service = _service(ControlledProvider())
    recognized = await service.recognize(_recognize_request(), CONTEXT)
    receipt = recognized["result"]["voice_commit_receipt"]
    binding = {
        "receipt": receipt,
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "turn_id": "turn-1",
        "commit_id": "commit-1",
        "text": "hello formal speech",
        "critical_confirmation": None,
    }

    first = await service.claim_voice_commit_receipt(**binding)
    replay = await service.claim_voice_commit_receipt(**binding)

    assert replay == first
    assert first["kind"] == "formal_speech_recognition"
    assert first["critical_policy"] == "eligible"
    assert first["speech_operation_id"] == "operation-r0"
    with pytest.raises(ValueError, match="already bound"):
        await service.claim_voice_commit_receipt(
            **{**binding, "commit_id": "commit-other"}
        )
    with pytest.raises(ValueError, match="does not match recognition"):
        await service.claim_voice_commit_receipt(
            **{**binding, "text": "changed recognized text"}
        )


@pytest.mark.asyncio
async def test_critical_voice_receipt_requires_confirmation_and_expires() -> None:
    now = [10.0]
    service = FormalBatchSpeechService(
        CriticalTextProvider(),
        authorization_resolver=ExactAuthorizationResolver(),
        monotonic=lambda: now[0],
    )
    recognized = await service.recognize(_recognize_request(), CONTEXT)
    receipt = recognized["result"]["voice_commit_receipt"]
    binding = {
        "receipt": receipt,
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "turn_id": "turn-critical",
        "commit_id": "commit-critical",
        "text": "delete 3 files",
    }

    with pytest.raises(ValueError, match="explicit confirmation"):
        await service.claim_voice_commit_receipt(**binding, critical_confirmation=None)
    claim = await service.claim_voice_commit_receipt(
        **binding, critical_confirmation=True
    )
    assert claim["critical_policy"] == "confirmed"

    second = await service.recognize(
        _recognize_request(
            request_id="request-r-expiry",
            operation_id="operation-r-expiry",
            capture_id="capture-expiry",
            generation=2,
        ),
        CONTEXT,
    )
    now[0] += 301
    with pytest.raises(ValueError, match="unknown or expired"):
        await service.claim_voice_commit_receipt(
            **{**binding, "receipt": second["result"]["voice_commit_receipt"]},
            critical_confirmation=True,
        )


@pytest.mark.asyncio
async def test_scope_and_authority_fail_closed_without_provider_side_effects() -> None:
    provider = ControlledProvider()
    service = _service(provider)
    wrong_scope = _recognize_request()
    wrong_scope["scope"] = dict(SCOPE, subject_id="mallory")
    not_authoritative = _synthesize_request()
    not_authoritative["authoritative_agent_text"] = False

    scope_result = await service.recognize(wrong_scope, CONTEXT)
    authority_result = await service.synthesize(not_authoritative, CONTEXT)

    assert scope_result["error"]["code"] == "PERMISSION_DENIED"
    assert authority_result["error"]["reason"] == "AUTHORITATIVE_AGENT_TEXT_REQUIRED"
    assert provider.recognize_calls == 0
    assert provider.synthesize_calls == 0


@pytest.mark.asyncio
async def test_request_asserted_identity_never_authorizes_provider_cost_or_audio() -> (
    None
):
    provider = ControlledProvider()
    resolver = ExactAuthorizationResolver()
    service = _service(provider, resolver=resolver)
    request = _recognize_request()
    request["scope"] = dict(SCOPE, assurance="request_asserted")
    asserted_context = SpeechRpcContext(
        "alice", "session-1", Assurance.REQUEST_ASSERTED
    )

    result = await service.recognize(request, asserted_context)

    assert result["error"]["code"] == "UNAUTHENTICATED"
    assert result["error"]["reason"] == "SPEECH_AUTHENTICATED_IDENTITY_REQUIRED"
    assert resolver.calls == []
    assert provider.recognize_calls == 0


@pytest.mark.asyncio
async def test_authenticated_identity_without_server_authorization_is_unavailable() -> (
    None
):
    provider = ControlledProvider()
    service = FormalBatchSpeechService(provider)

    result = await service.recognize(_recognize_request(), CONTEXT)
    capability = service.capability_payload()

    assert result["error"]["reason"] == "SPEECH_AUTHORIZATION_UNAVAILABLE"
    assert provider.recognize_calls == 0
    assert capability["capability"]["availability"] == "unavailable"
    assert capability["provider"]["provider_configured"] is True
    assert capability["provider"]["authorization_available"] is False


@pytest.mark.asyncio
async def test_forged_authoritative_text_flag_cannot_replace_server_decision() -> None:
    provider = ControlledProvider()
    resolver = ExactAuthorizationResolver(lambda binding: None)
    service = _service(provider, resolver=resolver)

    result = await service.synthesize(_synthesize_request(), CONTEXT)

    assert result["error"]["reason"] == "SPEECH_OPERATION_NOT_AUTHORIZED"
    assert len(resolver.calls) == 1
    assert provider.synthesize_calls == 0


def _wrong_scope_binding(
    binding: SpeechAuthorizationBinding,
) -> SpeechAuthorizationBinding:
    return replace(
        binding,
        scope=ScopeRef.from_dict(
            {
                "subject_id": "mallory",
                "project_id": None,
                "session_id": "session-1",
                "assurance": "authenticated",
            }
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate_grant",
    [
        _wrong_scope_binding,
        lambda binding: replace(binding, correlation_id="wrong-correlation"),
        lambda binding: replace(
            binding,
            response=ResponseRef("interaction-1", "wrong-response", 0),
        ),
        lambda binding: replace(binding, unit_id="wrong-unit"),
        lambda binding: replace(binding, content_sha256="0" * 64),
    ],
    ids=["scope", "correlation", "response", "unit", "render-text-digest"],
)
async def test_synthesis_requires_exact_server_owned_binding(
    mutate_grant: Callable[[SpeechAuthorizationBinding], SpeechAuthorizationBinding],
) -> None:
    provider = ControlledProvider()
    resolver = ExactAuthorizationResolver(mutate_grant)
    service = _service(provider, resolver=resolver)

    result = await service.synthesize(_synthesize_request(), CONTEXT)

    assert result["error"]["reason"] == "SPEECH_OPERATION_NOT_AUTHORIZED"
    assert provider.synthesize_calls == 0


@pytest.mark.asyncio
async def test_unavailable_flag_off_is_stable_and_does_not_fake_success() -> None:
    provider = create_environment_batch_speech_provider({})
    assert isinstance(provider, UnavailableBatchSpeechProvider)
    service = _service(provider)

    result = await service.recognize(_recognize_request(), CONTEXT)
    capability = service.capability_payload()

    assert result["error"]["reason"] == "SPEECH_PROVIDER_UNAVAILABLE"
    assert capability["capability"]["availability"] == "unavailable"
    assert capability["fallback"]["recognition"] == "browser-speech-recognition"
    assert capability["fallback"]["automatic"] is False


@pytest.mark.asyncio
async def test_idempotent_replay_and_stale_or_conflicting_input_never_reinvoke_provider() -> (
    None
):
    provider = ControlledProvider()
    service = _service(provider)

    first = await service.recognize(_recognize_request(), CONTEXT)
    replay = await service.recognize(
        _recognize_request(request_id="request-replay"), CONTEXT
    )
    conflict = await service.recognize(
        _recognize_request(operation_id="operation-r0", locale="fr-FR"), CONTEXT
    )
    stale = await service.recognize(
        _recognize_request(operation_id="operation-r1"), CONTEXT
    )
    reused_capture = await service.recognize(
        _recognize_request(operation_id="operation-r2", generation=2), CONTEXT
    )

    assert first["ok"] is True
    assert replay["ok"] is True
    assert replay["request_id"] == "request-replay"
    assert conflict["error"]["reason"] == "SPEECH_OPERATION_ID_CONFLICT"
    assert stale["error"]["code"] == "STALE"
    assert reused_capture["error"]["reason"] == "CAPTURE_ID_REUSED"
    assert provider.recognize_calls == 1


@pytest.mark.asyncio
async def test_equal_media_ids_are_isolated_by_exact_subject_scope() -> None:
    provider = ControlledProvider()
    service = _service(provider)
    bob_context = SpeechRpcContext("bob", "session-1", Assurance.AUTHENTICATED)
    bob_recognition = _recognize_request(request_id="request-bob-r")
    bob_recognition["scope"] = dict(SCOPE, subject_id="bob")
    bob_synthesis = _synthesize_request(request_id="request-bob-s")
    bob_synthesis["scope"] = dict(SCOPE, subject_id="bob")

    alice_recognition = await service.recognize(_recognize_request(), CONTEXT)
    bob_recognition_result = await service.recognize(bob_recognition, bob_context)
    alice_synthesis = await service.synthesize(_synthesize_request(), CONTEXT)
    bob_synthesis_result = await service.synthesize(bob_synthesis, bob_context)

    assert alice_recognition["ok"] is True
    assert bob_recognition_result["ok"] is True
    assert alice_synthesis["ok"] is True
    assert bob_synthesis_result["ok"] is True
    assert provider.recognize_calls == 2
    assert provider.synthesize_calls == 2


@pytest.mark.asyncio
async def test_truncated_wav_and_wrong_cancel_correlation_have_zero_forbidden_effects() -> (
    None
):
    provider = ControlledProvider(delay=True)
    service = _service(provider)
    truncated = _recognize_request(operation_id="operation-truncated")
    truncated_audio = _wav()[:-2]
    truncated["audio"]["data_base64"] = base64.b64encode(truncated_audio).decode(
        "ascii"
    )
    overlong = _recognize_request(operation_id="operation-overlong")
    overlong["capture"]["capture_id"] = "capture-overlong"
    overlong["audio"]["data_base64"] = base64.b64encode(_wav() + b"\x00").decode(
        "ascii"
    )

    invalid_audio = await service.recognize(truncated, CONTEXT)
    overlong_audio = await service.recognize(overlong, CONTEXT)
    pending = asyncio.create_task(service.synthesize(_synthesize_request(), CONTEXT))
    await provider.started.wait()
    wrong_cancel = _cancel_request("operation-s0")
    wrong_cancel["correlation_id"] = "other-correlation"
    rejected_cancel = await service.cancel(wrong_cancel, CONTEXT)
    provider.release.set()
    completed = await pending

    assert invalid_audio["error"]["reason"] == "INVALID_PCM_WAV"
    assert overlong_audio["error"]["reason"] == "INVALID_PCM_WAV"
    assert rejected_cancel["error"]["reason"] == "SPEECH_CORRELATION_MISMATCH"
    assert completed["ok"] is True
    assert provider.recognize_calls == 0
    assert provider.synthesize_calls == 1


@pytest.mark.asyncio
async def test_newer_server_capture_generation_fences_old_provider_completion() -> None:
    provider = ControlledProvider(delay=True)
    service = _service(provider)
    old = asyncio.create_task(service.recognize(_recognize_request(), CONTEXT))
    await provider.started.wait()
    new = asyncio.create_task(
        service.recognize(
            _recognize_request(
                request_id="request-r1",
                operation_id="operation-r1",
                capture_id="capture-2",
                generation=3,
            ),
            CONTEXT,
        )
    )
    while provider.recognize_calls < 2:
        await asyncio.sleep(0)
    provider.release.set()

    old_result, new_result = await asyncio.gather(old, new)

    assert old_result["error"]["reason"] == "STALE_RECOGNITION_SESSION"
    assert new_result["ok"] is True
    assert provider.recognize_calls == 2


@pytest.mark.asyncio
async def test_recreated_aio_adapter_can_restart_token_with_unique_capture_id() -> None:
    provider = ControlledProvider()
    service = _service(provider)

    before_recreate = await service.recognize(_recognize_request(), CONTEXT)
    after_recreate = await service.recognize(
        _recognize_request(
            request_id="request-r1",
            operation_id="operation-r1",
            capture_id="capture-after-recreate",
            generation=1,
        ),
        CONTEXT,
    )

    assert before_recreate["ok"] is True
    assert after_recreate["ok"] is True
    assert after_recreate["result"]["event"]["generation"] == 1
    assert provider.recognize_calls == 2


@pytest.mark.asyncio
async def test_timeout_cancels_provider_and_returns_terminal_error() -> None:
    provider = ControlledProvider(delay=True)
    service = _service(provider)

    result = await service.recognize(_recognize_request(timeout_ms=100), CONTEXT)

    assert result["error"]["code"] == "TIMEOUT"
    assert provider.cancelled.is_set()
    assert provider.recognize_calls == 1
    after_timeout = await service.cancel(_cancel_request("operation-r0"), CONTEXT)
    assert after_timeout["result"] == {
        "accepted": False,
        "target_operation_id": "operation-r0",
        "already_terminal": True,
        "provider_completion_known": False,
    }


@pytest.mark.asyncio
async def test_hard_timeout_fences_provider_that_swallows_cancel_once() -> None:
    provider = CancellationDefiantProvider(swallow_continuously=False)
    service = _service(provider)
    loop = asyncio.get_running_loop()
    started_at = loop.time()

    result = await asyncio.wait_for(
        service.recognize(_recognize_request(timeout_ms=100), CONTEXT),
        timeout=0.3,
    )
    elapsed = loop.time() - started_at

    assert elapsed < 0.25
    assert result["ok"] is False
    assert result["result"] is None
    assert result["error"]["code"] == "TIMEOUT"
    assert provider.cancel_count == 1
    replay = await service.recognize(
        _recognize_request(request_id="request-replay", timeout_ms=100), CONTEXT
    )
    assert replay["error"]["code"] == "TIMEOUT"

    provider.release.set()
    await asyncio.wait_for(provider.returned.wait(), timeout=0.2)
    close_report = await service.close(timeout_ms=200)
    assert close_report["provider_straggler_count"] == 0
    after_late_completion = await service.cancel(
        _cancel_request("operation-r0"), CONTEXT
    )
    assert after_late_completion["result"] == {
        "accepted": False,
        "target_operation_id": "operation-r0",
        "already_terminal": True,
        "provider_completion_known": True,
    }


@pytest.mark.asyncio
async def test_provider_cannot_turn_deadline_cancellation_into_success() -> None:
    provider = CancelToSuccessProvider()
    service = _service(provider)

    terminal = await asyncio.wait_for(
        service.recognize(_recognize_request(timeout_ms=100), CONTEXT),
        timeout=0.3,
    )
    await asyncio.wait_for(provider.returned.wait(), timeout=0.2)
    replay = await service.recognize(
        _recognize_request(request_id="request-replay", timeout_ms=100),
        CONTEXT,
    )

    assert provider.cancelled.is_set()
    assert terminal["ok"] is False
    assert terminal["error"]["code"] == "TIMEOUT"
    assert terminal["result"] is None
    assert replay["ok"] is False
    assert replay["error"]["code"] == "TIMEOUT"
    assert replay["result"] is None
    assert provider.recognize_calls == 1


@pytest.mark.asyncio
async def test_provider_completion_after_absolute_deadline_is_timeout_before_timer_dispatch() -> (
    None
):
    provider = DeadlineMonopolizingProvider()
    service = _service(provider)

    terminal = await asyncio.wait_for(
        service.recognize(_recognize_request(timeout_ms=100), CONTEXT),
        timeout=0.3,
    )

    assert provider.returned.is_set()
    assert terminal["ok"] is False
    assert terminal["error"]["code"] == "TIMEOUT"
    assert terminal["result"] is None
    replay = await service.recognize(
        _recognize_request(request_id="request-replay", timeout_ms=100),
        CONTEXT,
    )
    assert replay["error"]["code"] == "TIMEOUT"
    assert replay["result"] is None
    assert provider.recognize_calls == 1


@pytest.mark.asyncio
async def test_continuous_cancel_swallow_is_retained_bounded_and_close_reports_it() -> (
    None
):
    provider = CancellationDefiantProvider(swallow_continuously=True)
    service = _service(provider, max_completed_operations=1)
    loop = asyncio.get_running_loop()
    started_at = loop.time()

    first = await asyncio.wait_for(
        service.recognize(_recognize_request(timeout_ms=100), CONTEXT),
        timeout=0.3,
    )
    elapsed = loop.time() - started_at
    second = await service.recognize(
        _recognize_request(
            request_id="request-r1",
            operation_id="operation-r1",
            capture_id="capture-2",
            generation=2,
        ),
        CONTEXT,
    )

    assert first["error"]["code"] == "TIMEOUT"
    assert elapsed < 0.25
    assert second["error"]["reason"] == "SPEECH_OPERATION_CAPACITY"
    assert provider.recognize_calls == 1
    assert len(service._operations) == 1

    close_caller = asyncio.create_task(service.close(timeout_ms=50))
    await asyncio.sleep(0)
    close_caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_caller
    await asyncio.sleep(0.06)
    assert service._close_task is not None and service._close_task.done()
    close_started_at = loop.time()
    report = await service.close(timeout_ms=50)
    close_elapsed = loop.time() - close_started_at
    assert report["provider_straggler_count"] == 1
    assert report["provider_straggler_operation_ids"] == ["operation-r0"]
    assert report["clean"] is False
    assert close_elapsed < 0.15

    provider.release.set()
    await asyncio.wait_for(provider.returned.wait(), timeout=0.2)
    drained = await service.close(timeout_ms=200)
    assert drained["provider_straggler_count"] == 0
    assert drained["clean"] is True
    capability = service.capability_payload()
    assert capability["capability"]["availability"] == "unavailable"
    assert capability["provider"]["service_closed"] is True
    after_close = await service.recognize(
        _recognize_request(
            request_id="request-after-close",
            operation_id="operation-after-close",
            capture_id="capture-after-close",
            generation=3,
        ),
        CONTEXT,
    )
    assert after_close["error"]["reason"] == "SPEECH_SERVICE_CLOSED"
    assert provider.recognize_calls == 1


@pytest.mark.asyncio
async def test_late_synthesis_cannot_resurrect_audio_or_speech_events() -> None:
    provider = CancellationDefiantProvider(swallow_continuously=False)
    service = _service(provider)

    terminal = await asyncio.wait_for(
        service.synthesize(_synthesize_request(timeout_ms=100), CONTEXT),
        timeout=0.3,
    )

    assert terminal["ok"] is False
    assert terminal["error"]["code"] == "TIMEOUT"
    assert terminal["result"] is None

    provider.release.set()
    await asyncio.wait_for(provider.returned.wait(), timeout=0.2)
    replay = await service.synthesize(
        _synthesize_request(request_id="request-replay", timeout_ms=100),
        CONTEXT,
    )
    assert replay["ok"] is False
    assert replay["error"]["code"] == "TIMEOUT"
    assert replay["result"] is None
    assert "audio" not in replay
    assert "events" not in replay

    close_report = await service.close(timeout_ms=200)
    assert close_report["provider_completion_known_count"] == 1
    assert close_report["provider_straggler_count"] == 0
    assert close_report["clean"] is True


@pytest.mark.asyncio
async def test_explicit_cancel_fences_late_provider_result() -> None:
    provider = ControlledProvider(delay=True)
    service = _service(provider)
    pending = asyncio.create_task(service.synthesize(_synthesize_request(), CONTEXT))
    await provider.started.wait()

    cancelled = await service.cancel(_cancel_request("operation-s0"), CONTEXT)
    terminal = await pending
    provider.release.set()

    assert cancelled["result"] == {
        "accepted": True,
        "target_operation_id": "operation-s0",
        "already_terminal": False,
        "provider_completion_known": False,
    }
    assert terminal["error"]["code"] == "CANCELLED"
    assert provider.cancelled.is_set()
    duplicate = await service.cancel(_cancel_request("operation-s0"), CONTEXT)
    assert duplicate["result"] == {
        "accepted": False,
        "target_operation_id": "operation-s0",
        "already_terminal": True,
        "provider_completion_known": False,
    }


@pytest.mark.asyncio
async def test_exact_cancel_cannot_override_provider_success_terminal() -> None:
    provider = CancellationDefiantProvider(swallow_continuously=True)
    service = _service(provider)
    pending = asyncio.create_task(
        service.recognize(_recognize_request(timeout_ms=1000), CONTEXT)
    )
    await provider.started.wait()
    provider.release.set()
    await provider.returned.wait()

    cancelled = await service.cancel(_cancel_request("operation-r0"), CONTEXT)
    terminal = await pending

    assert cancelled["result"] == {
        "accepted": False,
        "target_operation_id": "operation-r0",
        "already_terminal": True,
        "provider_completion_known": True,
    }
    assert terminal["ok"] is True
    assert terminal["result"]["event"]["kind"] == "final"
    assert provider.cancel_count == 0


@pytest.mark.asyncio
async def test_exact_cancel_cannot_override_provider_error_terminal() -> None:
    provider = ErrorSignalingProvider()
    service = _service(provider)
    pending = asyncio.create_task(
        service.recognize(_recognize_request(timeout_ms=1000), CONTEXT)
    )
    await provider.failed.wait()

    cancelled = await service.cancel(_cancel_request("operation-r0"), CONTEXT)
    terminal = await pending

    assert cancelled["result"] == {
        "accepted": False,
        "target_operation_id": "operation-r0",
        "already_terminal": True,
        "provider_completion_known": False,
    }
    assert terminal["ok"] is False
    assert terminal["error"]["code"] == "INTERNAL"
    assert terminal["error"]["reason"] == "SPEECH_ADAPTER_INTERNAL"
    assert provider.recognize_calls == 1


@pytest.mark.asyncio
async def test_exact_cancel_returns_while_non_cooperative_provider_is_retained() -> (
    None
):
    provider = CancellationDefiantProvider(swallow_continuously=True)
    service = _service(provider)
    pending = asyncio.create_task(
        service.recognize(_recognize_request(timeout_ms=1000), CONTEXT)
    )
    await provider.started.wait()

    cancelled = await service.cancel(_cancel_request("operation-r0"), CONTEXT)
    terminal = await asyncio.wait_for(pending, timeout=0.2)
    close_report = await service.close(timeout_ms=50)

    assert cancelled["result"]["accepted"] is True
    assert cancelled["result"]["provider_completion_known"] is False
    assert terminal["error"]["code"] == "CANCELLED"
    assert terminal["result"] is None
    assert close_report["provider_straggler_count"] == 1

    provider.release.set()
    await asyncio.wait_for(provider.returned.wait(), timeout=0.2)
    drained = await service.close(timeout_ms=200)
    assert drained["clean"] is True


@pytest.mark.asyncio
async def test_identity_and_operation_state_stays_within_declared_windows() -> None:
    provider = ControlledProvider()
    service = _service(provider, max_completed_operations=2, max_identity_tombstones=3)

    for index in range(6):
        subject = f"user-{index}"
        context = SpeechRpcContext(subject, "session-1", Assurance.AUTHENTICATED)
        recognition = _recognize_request(
            request_id=f"request-r{index}",
            operation_id=f"operation-r{index}",
            capture_id=f"capture-{index}",
            generation=index + 1,
        )
        recognition["scope"] = dict(SCOPE, subject_id=subject)
        synthesis = _synthesize_request(
            request_id=f"request-s{index}",
            operation_id=f"operation-s{index}",
        )
        synthesis["scope"] = dict(SCOPE, subject_id=subject)
        synthesis["response"] = {
            "interaction_id": f"interaction-{index}",
            "response_id": f"response-{index}",
            "response_generation": 0,
        }

        assert (await service.recognize(recognition, context))["ok"] is True
        assert (await service.synthesize(synthesis, context))["ok"] is True

    assert len(service._operations) <= 2
    assert len(service._seen_captures) <= 3
    assert len(service._current_capture) <= 3
    assert len(service._seen_response_ids) <= 3
    assert len(service._last_response_generation) <= 3
    limits = service.capability_payload()["capability"]["declared_limits"]
    assert limits["operation_replay_window"] == 2
    assert limits["identity_tombstone_window"] == 3
    assert limits["resampling"] == "server_linear_pcm16_mono"


@pytest.mark.asyncio
async def test_openai_compatible_adapter_uses_server_credentials_and_batch_endpoints() -> (
    None
):
    seen: list[tuple[str, str | None, object | None]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        payload = (
            json.loads(request.content)
            if request.url.path.endswith("/audio/speech")
            else None
        )
        seen.append((request.url.path, request.headers.get("authorization"), payload))
        if request.url.path.endswith("/audio/transcriptions"):
            return httpx.Response(200, json={"text": "provider text", "language": "en"})
        return httpx.Response(200, content=_pcm16_samples([0, 1, -1]))

    config = OpenAICompatibleSpeechConfig(
        "https://speech.example.test/v1",
        "server-secret",
        "stt-model",
        "tts-model",
        "voice-model",
    )
    provider = OpenAICompatibleBatchSpeechProvider(
        config,
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(responder)
        ),
    )

    transcript = await provider.recognize(
        ProviderRecognitionRequest("r", _wav(), "en-US")
    )
    audio = await provider.synthesize(
        ProviderSynthesisRequest("s", "hello", "en-US", None, 16_000)
    )

    assert transcript.text == "provider text"
    assert audio.audio_wav.startswith(b"RIFF")
    assert seen[0][0:2] == (
        "/v1/audio/transcriptions",
        "Bearer server-secret",
    )
    assert seen[1] == (
        "/v1/audio/speech",
        "Bearer server-secret",
        {
            "model": "tts-model",
            "voice": "voice-model",
            "input": "hello",
            "response_format": "pcm",
        },
    )
    assert "server-secret" not in repr(config)
    assert "server-secret" not in repr(provider.capability())


@pytest.mark.asyncio
async def test_openai_compatible_adapter_wraps_and_resamples_24khz_pcm_to_48khz() -> (
    None
):
    provider = _openai_provider_returning(_pcm16_samples([0, 1_000, 2_000, 3_000]))

    result = await provider.synthesize(
        ProviderSynthesisRequest("s", "hello", "en-US", None, 48_000)
    )

    rate, channels, width, samples = _read_wav_samples(result.audio_wav)
    assert (rate, channels, width) == (48_000, 1, 2)
    assert samples == [0, 500, 1_000, 1_500, 2_000, 2_500, 3_000, 3_000]
    assert len(result.audio_wav) <= MAX_SYNTHESIS_AUDIO_BYTES
    inspected = inspect_pcm16_mono_wav(
        result.audio_wav,
        expected_sample_rate_hz=48_000,
    )
    assert inspected.frame_count == 8


@pytest.mark.asyncio
async def test_openai_compatible_adapter_resamples_24khz_pcm_to_16khz() -> None:
    provider = _openai_provider_returning(_pcm16_samples([0, 1_000, 2_000, 3_000]))

    result = await provider.synthesize(
        ProviderSynthesisRequest("s", "hello", "en-US", None, 16_000)
    )

    rate, channels, width, samples = _read_wav_samples(result.audio_wav)
    assert (rate, channels, width) == (16_000, 1, 2)
    assert samples == [0, 1_500, 3_000]


@pytest.mark.asyncio
async def test_openai_compatible_adapter_resamples_one_pcm16_sample() -> None:
    provider = _openai_provider_returning(_pcm16_samples([-12_345]))

    result = await provider.synthesize(
        ProviderSynthesisRequest("s", "hello", "en-US", None, 48_000)
    )

    rate, channels, width, samples = _read_wav_samples(result.audio_wav)
    assert (rate, channels, width) == (48_000, 1, 2)
    assert samples == [-12_345, -12_345]


@pytest.mark.asyncio
async def test_openai_compatible_adapter_wraps_same_rate_pcm_as_canonical_wav() -> None:
    source = _pcm16_samples([-32_768, -1, 0, 1, 32_767])
    provider = _openai_provider_returning(source)

    result = await provider.synthesize(
        ProviderSynthesisRequest("s", "hello", "en-US", None, 24_000)
    )

    expected_header = (
        b"RIFF"
        + (36 + len(source)).to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (24_000).to_bytes(4, "little")
        + (48_000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + len(source).to_bytes(4, "little")
    )
    assert result.audio_wav == expected_header + source
    inspected = inspect_pcm16_mono_wav(
        result.audio_wav,
        expected_sample_rate_hz=24_000,
    )
    assert inspected.frame_count == 5


@pytest.mark.asyncio
async def test_openai_compatible_adapter_resamples_odd_and_minimal_frame_input() -> (
    None
):
    provider = _openai_provider_returning(_pcm16_samples([-3, 0, 7]))

    result = await provider.synthesize(
        ProviderSynthesisRequest("s", "hello", "en-US", None, 48_000)
    )

    rate, channels, width, samples = _read_wav_samples(result.audio_wav)
    assert (rate, channels, width) == (48_000, 1, 2)
    assert len(samples) == 6
    assert samples


@pytest.mark.asyncio
async def test_openai_compatible_adapter_rejects_resampled_output_over_limit() -> None:
    scale = 48_000 // 24_000
    max_output_frames = (MAX_SYNTHESIS_AUDIO_BYTES - 44) // 2
    source_frames = max_output_frames // scale + 1
    source = b"\x00\x00" * source_frames
    assert len(source) <= MAX_SYNTHESIS_AUDIO_BYTES - 44
    provider = _openai_provider_returning(source)

    with pytest.raises(BatchSpeechError) as oversized:
        await provider.synthesize(
            ProviderSynthesisRequest("s", "hello", "en-US", None, 48_000)
        )

    assert oversized.value.error.reason == "SPEECH_PROVIDER_RESPONSE_LIMIT"


@pytest.mark.asyncio
async def test_openai_compatible_adapter_accepts_exact_raw_pcm_limit_at_24khz() -> None:
    source = b"\x00" * (MAX_SYNTHESIS_AUDIO_BYTES - 44)
    provider = _openai_provider_returning(source)

    result = await provider.synthesize(
        ProviderSynthesisRequest("s", "hello", "en-US", None, 24_000)
    )

    assert len(result.audio_wav) == MAX_SYNTHESIS_AUDIO_BYTES
    inspected = inspect_pcm16_mono_wav(
        result.audio_wav,
        expected_sample_rate_hz=24_000,
    )
    assert inspected.frame_count == len(source) // 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "reason"),
    [
        pytest.param(b"", "SPEECH_PROVIDER_INVALID_PCM", id="empty-pcm"),
        pytest.param(b"\x00", "SPEECH_PROVIDER_INVALID_PCM", id="odd-pcm-byte"),
        pytest.param(
            b"\x00" * (MAX_SYNTHESIS_AUDIO_BYTES - 44 + 1),
            "SPEECH_PROVIDER_RESPONSE_LIMIT",
            id="oversized-pcm",
        ),
    ],
)
async def test_openai_compatible_adapter_rejects_invalid_provider_pcm(
    source: bytes,
    reason: str,
) -> None:
    provider = _openai_provider_returning(source)

    with pytest.raises(BatchSpeechError) as invalid:
        await provider.synthesize(
            ProviderSynthesisRequest("s", "hello", "en-US", None, 48_000)
        )

    assert invalid.value.error.reason == reason


@pytest.mark.asyncio
async def test_provider_response_limit_and_credentials_fail_with_safe_errors() -> None:
    status = 200

    def responder(request: httpx.Request) -> httpx.Response:
        if status == 401:
            return httpx.Response(401, content=b"server-secret must not escape")
        return httpx.Response(200, content=b"x" * (256 * 1024 + 1))

    provider = OpenAICompatibleBatchSpeechProvider(
        OpenAICompatibleSpeechConfig(
            "https://speech.example.test/v1",
            "server-secret",
            "stt-model",
            None,
            None,
        ),
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(responder)
        ),
    )

    with pytest.raises(BatchSpeechError) as oversized:
        await provider.recognize(ProviderRecognitionRequest("r", _wav(), "en-US"))
    assert oversized.value.error.reason == "SPEECH_PROVIDER_RESPONSE_LIMIT"
    assert "server-secret" not in str(oversized.value)

    status = 401
    with pytest.raises(BatchSpeechError) as rejected:
        await provider.recognize(ProviderRecognitionRequest("r2", _wav(), "en-US"))
    assert rejected.value.error.reason == "SPEECH_PROVIDER_CREDENTIAL_REJECTED"
    assert "server-secret" not in str(rejected.value)


def test_environment_configuration_requires_secure_complete_gateway_secret_boundary() -> (
    None
):
    base = {
        FORMAL_BATCH_SPEECH_FLAG: "true",
        SPEECH_PROVIDER_ENV: "openai-compatible",
        SPEECH_API_BASE_ENV: "http://speech.example.test/v1",
        SPEECH_API_KEY_ENV: "server-secret",
        SPEECH_STT_MODEL_ENV: "stt-model",
        SPEECH_TTS_MODEL_ENV: "tts-model",
        SPEECH_TTS_VOICE_ENV: "voice-model",
    }
    insecure = create_environment_batch_speech_provider(base)
    secure = create_environment_batch_speech_provider(
        {**base, SPEECH_API_BASE_ENV: "https://speech.example.test/v1"}
    )

    assert isinstance(insecure, UnavailableBatchSpeechProvider)
    assert isinstance(secure, OpenAICompatibleBatchSpeechProvider)
    capability_json = json.dumps(_service(secure).capability_payload())
    assert "server-secret" not in capability_json
    assert "speech.example.test" not in capability_json
