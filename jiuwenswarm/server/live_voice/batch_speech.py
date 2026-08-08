# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Formal batch speech service and dependency-injected Provider Adapter.

The module deliberately owns only SR-B/SS-B batch work.  It does not commit a
turn, dispatch Agent/Tool/Task work, write history, or claim audio was played.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import re
import secrets
import sys
import time
import wave
from array import array
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol
from urllib.parse import urlparse

import httpx

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
    Availability,
    CapabilityDescriptor,
    ContractError,
    ErrorCode,
    ResponseRef,
    ScopeRef,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.speech_ports import (
    ProviderRef,
    RecognitionAlternative,
    RecognitionEventKind,
    RecognitionHypothesis,
    RecognitionPort,
    RenderTransform,
    SpeechCapability,
    SpeechMode,
    SpeechPortViolation,
    SynthesisPort,
    SynthesisRequest,
)
from jiuwenswarm.server.live_voice.critical_token_safety import CriticalTokenPolicy


FORMAL_BATCH_SPEECH_FLAG = "LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED"
SPEECH_PROVIDER_ENV = "LIVE_VOICE_SPEECH_PROVIDER"
SPEECH_API_BASE_ENV = "LIVE_VOICE_SPEECH_API_BASE"
SPEECH_API_KEY_ENV = "LIVE_VOICE_SPEECH_API_KEY"
SPEECH_STT_MODEL_ENV = "LIVE_VOICE_SPEECH_STT_MODEL"
SPEECH_TTS_MODEL_ENV = "LIVE_VOICE_SPEECH_TTS_MODEL"
SPEECH_TTS_VOICE_ENV = "LIVE_VOICE_SPEECH_TTS_VOICE"

RECOGNIZE_OPERATION = "speech.recognize.batch"
SYNTHESIZE_OPERATION = "speech.synthesize.batch"
CANCEL_OPERATION = "speech.batch.cancel"
CAPABILITIES_OPERATION = "speech.capabilities.get"

MAX_BATCH_AUDIO_BYTES = 4 * 1024 * 1024
MAX_SYNTHESIS_AUDIO_BYTES = 8 * 1024 * 1024
MAX_RECOGNITION_TEXT_CHARS = 16_000
MAX_SYNTHESIS_TEXT_CHARS = 4_000
MAX_BATCH_TIMEOUT_MS = 30_000
MIN_BATCH_TIMEOUT_MS = 100
DEFAULT_BATCH_TIMEOUT_MS = 15_000
MAX_COMPLETED_OPERATIONS = 128
MAX_IDENTITY_TOMBSTONES = 512
MIN_CLOSE_TIMEOUT_MS = 10
MAX_CLOSE_TIMEOUT_MS = 5_000
DEFAULT_CLOSE_TIMEOUT_MS = 1_000
MAX_VOICE_COMMIT_RECEIPTS = 512
VOICE_COMMIT_RECEIPT_TTL_SECONDS = 300.0

_PCM16_SAMPLE_WIDTH_BYTES = 2
_PCM_WAV_HEADER_BYTES = 44

_LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
_PROVIDER_ID = "openai-compatible-batch-speech"
_IMPLEMENTATION_CLASS = "formal"


def _contract_error(
    code: ErrorCode,
    reason: str,
    message: str,
    *,
    retriable: bool = False,
    correlation_id: str | None = None,
    details: dict[str, object] | None = None,
) -> ContractError:
    return ContractError.from_dict(
        {
            "code": code.value,
            "reason": reason,
            "message": message,
            "retriable": retriable,
            "correlation_id": correlation_id,
            "details": details or {},
        }
    )


class BatchSpeechError(Exception):
    def __init__(self, error: ContractError) -> None:
        super().__init__(error.message)
        self.error = error


def _fail(
    code: ErrorCode,
    reason: str,
    message: str,
    *,
    retriable: bool = False,
    correlation_id: str | None = None,
    details: dict[str, object] | None = None,
) -> BatchSpeechError:
    return BatchSpeechError(
        _contract_error(
            code,
            reason,
            message,
            retriable=retriable,
            correlation_id=correlation_id,
            details=details,
        )
    )


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "INVALID_REQUIRED_TEXT",
            f"{field} must be a non-empty string",
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "INVALID_UNICODE_SCALAR",
            f"{field} contains invalid Unicode",
        ) from exc
    return value


def _required_dict(value: object, field: str) -> dict[str, object]:
    if type(value) is not dict:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "INVALID_OBJECT",
            f"{field} must be an object",
        )
    return dict(value)


def _exact_keys(
    value: dict[str, object],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    field: str,
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unknown = sorted(actual - required - optional)
    if missing:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "MISSING_REQUIRED_FIELD",
            f"{field} is missing required fields",
            details={"fields": missing},
        )
    if unknown:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "UNKNOWN_FIELD",
            f"{field} contains unknown fields",
            details={"fields": unknown},
        )


def _non_negative_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "INVALID_NON_NEGATIVE_INTEGER",
            f"{field} must be a non-negative integer",
        )
    return value


def _positive_int(value: object, field: str) -> int:
    parsed = _non_negative_int(value, field)
    if parsed == 0:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "INVALID_POSITIVE_INTEGER",
            f"{field} must be positive",
        )
    return parsed


def _timeout_ms(value: object) -> int:
    timeout = _positive_int(value, "timeout_ms")
    if not MIN_BATCH_TIMEOUT_MS <= timeout <= MAX_BATCH_TIMEOUT_MS:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "INVALID_SPEECH_TIMEOUT",
            f"timeout_ms must be between {MIN_BATCH_TIMEOUT_MS} and {MAX_BATCH_TIMEOUT_MS}",
        )
    return timeout


def _locale(value: object) -> str:
    locale = _required_text(value, "locale")
    if _LOCALE_RE.fullmatch(locale) is None:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "INVALID_SPEECH_LOCALE",
            "locale must be a BCP-47-like language tag",
        )
    return locale


def _decode_base64(value: object, *, field: str, max_bytes: int) -> bytes:
    encoded = _required_text(value, field)
    max_encoded_chars = 4 * ((max_bytes + 2) // 3)
    if len(encoded) > max_encoded_chars:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "AUDIO_LIMIT_EXCEEDED",
            "batch speech audio exceeds the package limit",
            details={"max_bytes": max_bytes},
        )
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "INVALID_AUDIO_BASE64",
            f"{field} must contain canonical base64 audio",
        ) from exc
    if not decoded:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "EMPTY_AUDIO",
            "batch speech audio must be non-empty",
        )
    if len(decoded) > max_bytes:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "AUDIO_LIMIT_EXCEEDED",
            "batch speech audio exceeds the package limit",
            details={"max_bytes": max_bytes},
        )
    return decoded


@dataclass(frozen=True, slots=True)
class PcmWavInfo:
    sample_rate_hz: int
    channel_count: int
    sample_width_bytes: int
    frame_count: int

    @property
    def duration_ms(self) -> int:
        return round(self.frame_count * 1000 / self.sample_rate_hz)


def inspect_pcm16_mono_wav(
    audio: bytes,
    *,
    expected_sample_rate_hz: int | None = None,
    invalid_code: ErrorCode = ErrorCode.INVALID_ARGUMENT,
    invalid_reason: str = "INVALID_PCM_WAV",
    unsupported_reason: str = "UNSUPPORTED_BATCH_AUDIO_FORMAT",
) -> PcmWavInfo:
    if (
        len(audio) < 12
        or audio[:4] != b"RIFF"
        or audio[8:12] != b"WAVE"
        or int.from_bytes(audio[4:8], "little") + 8 != len(audio)
    ):
        raise _fail(
            invalid_code,
            invalid_reason,
            "audio must be one complete RIFF/WAVE payload",
        )
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            info = PcmWavInfo(
                sample_rate_hz=wav.getframerate(),
                channel_count=wav.getnchannels(),
                sample_width_bytes=wav.getsampwidth(),
                frame_count=wav.getnframes(),
            )
            compression = wav.getcomptype()
            decoded_frame_bytes = wav.readframes(info.frame_count)
    except (wave.Error, EOFError) as exc:
        raise _fail(
            invalid_code,
            invalid_reason,
            "audio must be a complete PCM WAV file",
        ) from exc
    if (
        compression != "NONE"
        or info.sample_width_bytes != 2
        or info.channel_count != 1
        or info.sample_rate_hz <= 0
        or info.frame_count <= 0
        or len(decoded_frame_bytes)
        != info.frame_count * info.channel_count * info.sample_width_bytes
    ):
        raise _fail(
            invalid_code,
            unsupported_reason,
            "batch speech requires non-empty mono signed-16-bit PCM WAV audio",
        )
    if (
        expected_sample_rate_hz is not None
        and info.sample_rate_hz != expected_sample_rate_hz
    ):
        raise _fail(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "SPEECH_SAMPLE_RATE_MISMATCH",
            "Provider audio sample rate does not match the AIO-B playout rate",
            details={
                "expected_sample_rate_hz": expected_sample_rate_hz,
                "actual_sample_rate_hz": info.sample_rate_hz,
            },
        )
    return info


def _round_divide_signed(numerator: int, denominator: int) -> int:
    """Round one signed integer ratio to nearest, with ties away from zero."""

    if numerator >= 0:
        return (numerator + denominator // 2) // denominator
    return -((-numerator + denominator // 2) // denominator)


def _resample_pcm16_mono_wav(
    audio: bytes,
    *,
    target_sample_rate_hz: int,
) -> bytes:
    """Convert a validated mono PCM16 WAV to one exact target sample rate.

    Linear interpolation uses integer arithmetic so output bytes are stable
    across platforms.  The complete source is validated before conversion,
    output capacity is checked before allocation, and the generated WAV is
    validated again before it can cross the Provider Adapter boundary.
    """

    source_info = inspect_pcm16_mono_wav(
        audio,
        invalid_code=ErrorCode.PROTOCOL_VIOLATION,
        invalid_reason="SPEECH_PROVIDER_INVALID_WAV",
        unsupported_reason="SPEECH_PROVIDER_UNSUPPORTED_AUDIO_FORMAT",
    )
    if source_info.sample_rate_hz == target_sample_rate_hz:
        return audio
    if target_sample_rate_hz <= 0 or target_sample_rate_hz > 0xFFFFFFFF:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "INVALID_REQUIRED_SAMPLE_RATE",
            "required playout sample rate is outside the PCM WAV range",
        )

    target_frame_count = max(
        1,
        (
            source_info.frame_count * target_sample_rate_hz
            + source_info.sample_rate_hz // 2
        )
        // source_info.sample_rate_hz,
    )
    max_target_frames = (
        MAX_SYNTHESIS_AUDIO_BYTES - _PCM_WAV_HEADER_BYTES
    ) // _PCM16_SAMPLE_WIDTH_BYTES
    if target_frame_count > max_target_frames:
        raise _fail(
            ErrorCode.PROTOCOL_VIOLATION,
            "SPEECH_PROVIDER_RESPONSE_LIMIT",
            "resampled speech Provider output exceeds the package limit",
        )

    with wave.open(io.BytesIO(audio), "rb") as source_wav:
        source_bytes = source_wav.readframes(source_info.frame_count)
    source_samples = array("h")
    source_samples.frombytes(source_bytes)
    if sys.byteorder != "little":
        source_samples.byteswap()
    if len(source_samples) != source_info.frame_count:
        raise _fail(
            ErrorCode.PROTOCOL_VIOLATION,
            "SPEECH_PROVIDER_INVALID_WAV",
            "speech Provider WAV frame count changed during decoding",
        )

    target_samples = array("h", [0]) * target_frame_count
    source_rate = source_info.sample_rate_hz
    target_rate = target_sample_rate_hz
    last_source_index = len(source_samples) - 1
    for target_index in range(target_frame_count):
        source_position, remainder = divmod(target_index * source_rate, target_rate)
        if source_position >= last_source_index:
            sample = source_samples[last_source_index]
        else:
            left = source_samples[source_position]
            right = source_samples[source_position + 1]
            sample = _round_divide_signed(
                left * (target_rate - remainder) + right * remainder,
                target_rate,
            )
        target_samples[target_index] = max(-32768, min(32767, sample))

    output_samples = array("h", target_samples)
    if sys.byteorder != "little":
        output_samples.byteswap()
    output = io.BytesIO()
    with wave.open(output, "wb") as target_wav:
        target_wav.setnchannels(1)
        target_wav.setsampwidth(_PCM16_SAMPLE_WIDTH_BYTES)
        target_wav.setframerate(target_rate)
        target_wav.writeframes(output_samples.tobytes())
    resampled = output.getvalue()
    if len(resampled) > MAX_SYNTHESIS_AUDIO_BYTES:
        raise _fail(
            ErrorCode.PROTOCOL_VIOLATION,
            "SPEECH_PROVIDER_RESPONSE_LIMIT",
            "resampled speech Provider output exceeds the package limit",
        )
    inspect_pcm16_mono_wav(
        resampled,
        expected_sample_rate_hz=target_rate,
        invalid_code=ErrorCode.PROTOCOL_VIOLATION,
        invalid_reason="SPEECH_PROVIDER_INVALID_WAV",
        unsupported_reason="SPEECH_PROVIDER_UNSUPPORTED_AUDIO_FORMAT",
    )
    return resampled


@dataclass(frozen=True, slots=True)
class SpeechRpcContext:
    subject_id: str | None
    session_id: str
    assurance: Assurance = Assurance.REQUEST_ASSERTED


def _scope(value: object, context: SpeechRpcContext) -> ScopeRef:
    try:
        scope = ScopeRef.from_dict(value)
    except Exception as exc:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "INVALID_SPEECH_SCOPE",
            "scope must match the live-voice v2 ScopeRef contract",
        ) from exc
    if context.subject_id is None:
        raise _fail(
            ErrorCode.UNAUTHENTICATED,
            "SPEECH_SUBJECT_REQUIRED",
            "the Gateway connection must supply a subject identity",
        )
    if scope.subject_id != context.subject_id or scope.session_id != context.session_id:
        raise _fail(
            ErrorCode.PERMISSION_DENIED,
            "SPEECH_SCOPE_MISMATCH",
            "speech scope does not match the Gateway connection",
        )
    if scope.project_id is not None:
        raise _fail(
            ErrorCode.PERMISSION_DENIED,
            "SPEECH_PROJECT_SCOPE_UNRESOLVED",
            "batch speech does not resolve project scope in this package",
        )
    if scope.assurance is not context.assurance:
        raise _fail(
            ErrorCode.PERMISSION_DENIED,
            "SPEECH_ASSURANCE_MISMATCH",
            "speech assurance must be resolved by the Gateway",
        )
    return scope


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    provider_id: str
    recognition_batch: bool
    synthesis_batch: bool
    available: bool
    output_format: str = "wav_pcm16_mono"
    supports_transport_cancel: bool = True


@dataclass(frozen=True, slots=True)
class ProviderRecognitionRequest:
    operation_id: str
    audio_wav: bytes
    locale: str


@dataclass(frozen=True, slots=True)
class ProviderRecognitionResult:
    text: str
    observed_locale: str | None
    model: str


@dataclass(frozen=True, slots=True)
class ProviderSynthesisRequest:
    operation_id: str
    spoken_text: str
    locale: str
    voice: str | None
    required_sample_rate_hz: int


@dataclass(frozen=True, slots=True)
class ProviderSynthesisResult:
    audio_wav: bytes
    model: str
    voice: str


class BatchSpeechProvider(Protocol):
    def capability(self) -> ProviderCapability: ...

    async def recognize(
        self, request: ProviderRecognitionRequest
    ) -> ProviderRecognitionResult: ...

    async def synthesize(
        self, request: ProviderSynthesisRequest
    ) -> ProviderSynthesisResult: ...


class UnavailableBatchSpeechProvider:
    def __init__(self, provider_id: str = _PROVIDER_ID) -> None:
        self._capability = ProviderCapability(provider_id, False, False, False)

    def capability(self) -> ProviderCapability:
        return self._capability

    async def recognize(
        self, request: ProviderRecognitionRequest
    ) -> ProviderRecognitionResult:
        del request
        raise _fail(
            ErrorCode.UNAVAILABLE,
            "SPEECH_PROVIDER_UNAVAILABLE",
            "formal batch speech Provider is unavailable",
            retriable=True,
        )

    async def synthesize(
        self, request: ProviderSynthesisRequest
    ) -> ProviderSynthesisResult:
        del request
        raise _fail(
            ErrorCode.UNAVAILABLE,
            "SPEECH_PROVIDER_UNAVAILABLE",
            "formal batch speech Provider is unavailable",
            retriable=True,
        )


@dataclass(frozen=True, slots=True)
class OpenAICompatibleSpeechConfig:
    api_base: str
    api_key: str = field(repr=False)
    stt_model: str | None
    tts_model: str | None
    tts_voice: str | None


class OpenAICompatibleBatchSpeechProvider:
    """Small HTTP Adapter for OpenAI-compatible batch Audio endpoints.

    The secret and endpoint remain private fields.  All exceptions are mapped to
    stable safe errors before they cross the Gateway boundary.
    """

    def __init__(
        self,
        config: OpenAICompatibleSpeechConfig,
        *,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self._config = config
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(follow_redirects=False, timeout=None)
        )
        self._capability = ProviderCapability(
            provider_id=_PROVIDER_ID,
            recognition_batch=config.stt_model is not None,
            synthesis_batch=config.tts_model is not None,
            available=True,
        )

    def capability(self) -> ProviderCapability:
        return self._capability

    async def recognize(
        self, request: ProviderRecognitionRequest
    ) -> ProviderRecognitionResult:
        model = self._config.stt_model
        if model is None:
            raise _fail(
                ErrorCode.UNSUPPORTED,
                "SPEECH_RECOGNITION_UNSUPPORTED",
                "configured Provider does not support batch recognition",
            )
        language = request.locale.split("-", 1)[0].lower()
        data = {"model": model, "response_format": "json"}
        if len(language) in {2, 3}:
            data["language"] = language
        response = await self._post(
            "/audio/transcriptions",
            data=data,
            files={"file": ("capture.wav", request.audio_wav, "audio/wav")},
            max_response_bytes=256 * 1024,
        )
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise _fail(
                ErrorCode.PROTOCOL_VIOLATION,
                "SPEECH_PROVIDER_INVALID_JSON",
                "speech Provider returned an invalid recognition response",
            ) from exc
        if type(payload) is not dict:
            raise _fail(
                ErrorCode.PROTOCOL_VIOLATION,
                "SPEECH_PROVIDER_INVALID_RESULT",
                "speech Provider returned an invalid recognition result",
            )
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise _fail(
                ErrorCode.PROTOCOL_VIOLATION,
                "SPEECH_PROVIDER_EMPTY_TRANSCRIPT",
                "speech Provider returned an empty recognition result",
            )
        if len(text) > MAX_RECOGNITION_TEXT_CHARS:
            raise _fail(
                ErrorCode.PROTOCOL_VIOLATION,
                "SPEECH_PROVIDER_TRANSCRIPT_LIMIT",
                "speech Provider recognition result exceeds the package limit",
            )
        observed_locale = payload.get("language")
        if not isinstance(observed_locale, str) or not observed_locale.strip():
            observed_locale = None
        return ProviderRecognitionResult(text, observed_locale, model)

    async def synthesize(
        self, request: ProviderSynthesisRequest
    ) -> ProviderSynthesisResult:
        model = self._config.tts_model
        voice = request.voice or self._config.tts_voice
        if model is None or voice is None:
            raise _fail(
                ErrorCode.UNSUPPORTED,
                "SPEECH_SYNTHESIS_UNSUPPORTED",
                "configured Provider does not support batch synthesis",
            )
        response = await self._post(
            "/audio/speech",
            json_payload={
                "model": model,
                "voice": voice,
                "input": request.spoken_text,
                "response_format": "wav",
            },
            max_response_bytes=MAX_SYNTHESIS_AUDIO_BYTES,
        )
        audio = bytes(response.content)
        if not audio or len(audio) > MAX_SYNTHESIS_AUDIO_BYTES:
            raise _fail(
                ErrorCode.PROTOCOL_VIOLATION,
                "SPEECH_PROVIDER_AUDIO_LIMIT",
                "speech Provider returned empty or oversized audio",
            )
        audio = _resample_pcm16_mono_wav(
            audio,
            target_sample_rate_hz=request.required_sample_rate_hz,
        )
        return ProviderSynthesisResult(audio, model, voice)

    async def _post(
        self,
        path: str,
        *,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        json_payload: dict[str, str] | None = None,
        max_response_bytes: int,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._config.api_key}"}
        try:
            async with self._client_factory() as client:
                async with client.stream(
                    "POST",
                    f"{self._config.api_base}{path}",
                    headers=headers,
                    data=data,
                    files=files,
                    json=json_payload,
                ) as streamed:
                    status_code = streamed.status_code
                    self._raise_provider_status(status_code)
                    response_headers = streamed.headers
                    response_request = streamed.request
                    chunks: list[bytes] = []
                    response_size = 0
                    async for chunk in streamed.aiter_bytes():
                        response_size += len(chunk)
                        if response_size > max_response_bytes:
                            raise _fail(
                                ErrorCode.PROTOCOL_VIOLATION,
                                "SPEECH_PROVIDER_RESPONSE_LIMIT",
                                "speech Provider response exceeds the package limit",
                            )
                        chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise _fail(
                ErrorCode.TIMEOUT,
                "SPEECH_PROVIDER_TIMEOUT",
                "speech Provider timed out",
                retriable=True,
            ) from exc
        except BatchSpeechError:
            raise
        except httpx.RequestError as exc:
            raise _fail(
                ErrorCode.UNAVAILABLE,
                "SPEECH_PROVIDER_UNAVAILABLE",
                "speech Provider is unavailable",
                retriable=True,
            ) from exc
        response = httpx.Response(
            status_code,
            headers=response_headers,
            content=b"".join(chunks),
            request=response_request,
        )
        return response

    @staticmethod
    def _raise_provider_status(status_code: int) -> None:
        if status_code in {401, 403}:
            raise _fail(
                ErrorCode.UNAVAILABLE,
                "SPEECH_PROVIDER_CREDENTIAL_REJECTED",
                "speech Provider rejected Gateway credentials",
            )
        if status_code == 429 or status_code >= 500:
            raise _fail(
                ErrorCode.UNAVAILABLE,
                "SPEECH_PROVIDER_UNAVAILABLE",
                "speech Provider is temporarily unavailable",
                retriable=True,
            )
        if status_code >= 400:
            raise _fail(
                ErrorCode.INVALID_ARGUMENT,
                "SPEECH_PROVIDER_REQUEST_REJECTED",
                "speech Provider rejected the batch request",
            )


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _validate_api_base(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("speech API base must be an absolute HTTP(S) origin/path")
    loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if parsed.scheme != "https" and not loopback:
        raise ValueError("speech API credentials require HTTPS outside loopback")
    return value.rstrip("/")


def create_environment_batch_speech_provider(
    environ: dict[str, str] | None = None,
) -> BatchSpeechProvider:
    env = os.environ if environ is None else environ
    if not _enabled(env.get(FORMAL_BATCH_SPEECH_FLAG)):
        return UnavailableBatchSpeechProvider()
    provider = str(env.get(SPEECH_PROVIDER_ENV) or "").strip().lower()
    if provider != "openai-compatible":
        return UnavailableBatchSpeechProvider()
    api_base = str(env.get(SPEECH_API_BASE_ENV) or "").strip()
    api_key = str(env.get(SPEECH_API_KEY_ENV) or "").strip()
    stt_model = str(env.get(SPEECH_STT_MODEL_ENV) or "").strip() or None
    tts_model = str(env.get(SPEECH_TTS_MODEL_ENV) or "").strip() or None
    tts_voice = str(env.get(SPEECH_TTS_VOICE_ENV) or "").strip() or None
    if not api_base or not api_key or (stt_model is None and tts_model is None):
        return UnavailableBatchSpeechProvider()
    try:
        normalized_base = _validate_api_base(api_base)
    except ValueError:
        return UnavailableBatchSpeechProvider()
    return OpenAICompatibleBatchSpeechProvider(
        OpenAICompatibleSpeechConfig(
            normalized_base, api_key, stt_model, tts_model, tts_voice
        )
    )


@dataclass(frozen=True, slots=True)
class RecognitionBatchRequest:
    request_id: str
    operation_id: str
    correlation_id: str
    scope: ScopeRef
    capture_id: str
    capture_generation: int
    track_id: str
    locale: str
    audio_wav: bytes
    sample_rate_hz: int
    timeout_ms: int


@dataclass(frozen=True, slots=True)
class SynthesisBatchRequest:
    request_id: str
    operation_id: str
    correlation_id: str
    scope: ScopeRef
    response: ResponseRef
    unit_id: str
    display_text: str
    spoken_text: str
    transforms: tuple[RenderTransform, ...]
    locale: str
    voice: str | None
    required_sample_rate_hz: int
    timeout_ms: int


@dataclass(frozen=True, slots=True)
class SpeechAuthorizationBinding:
    """Exact validated request candidate; only a server-owned resolver can grant it."""

    subject_id: str
    scope: ScopeRef
    operation: str
    operation_id: str
    correlation_id: str
    capture_id: str | None
    capture_generation: int | None
    track_id: str | None
    response: ResponseRef | None
    unit_id: str | None
    content_sha256: str


class SpeechAuthorizationResolver(Protocol):
    def authorize(
        self, binding: SpeechAuthorizationBinding
    ) -> SpeechAuthorizationBinding | None: ...


@dataclass(slots=True)
class _OperationEntry:
    fingerprint: bytes
    scope: ScopeRef
    correlation_id: str
    kind: str
    task: asyncio.Task[dict[str, object]]
    provider_completion_known: bool = False
    worker_task: asyncio.Task[dict[str, object]] | None = None
    worker_terminal: bool = False
    deadline_at: float | None = None
    deadline_handle: asyncio.TimerHandle | None = None
    fence_code: ErrorCode | None = None
    fence_reason: str | None = None
    fence_event: asyncio.Event = field(default_factory=asyncio.Event)


def _parse_common(
    payload: object,
    context: SpeechRpcContext,
    *,
    operation: str,
    extra_keys: set[str],
) -> tuple[dict[str, object], str, str, str, ScopeRef, int]:
    data = _required_dict(payload, "speech_request")
    _exact_keys(
        data,
        required={
            "contract_version",
            "request_id",
            "operation_id",
            "operation",
            "correlation_id",
            "scope",
            "session_id",
            "timeout_ms",
            *extra_keys,
        },
        field="speech_request",
    )
    if data["contract_version"] != CONTRACT_VERSION:
        raise _fail(
            ErrorCode.UNSUPPORTED,
            "UNSUPPORTED_CONTRACT_VERSION",
            f"expected {CONTRACT_VERSION}",
        )
    if data["operation"] != operation:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "SPEECH_OPERATION_MISMATCH",
            "speech operation does not match the Gateway method",
        )
    request_id = _required_text(data["request_id"], "request_id")
    operation_id = _required_text(data["operation_id"], "operation_id")
    correlation_id = _required_text(data["correlation_id"], "correlation_id")
    scope = _scope(data["scope"], context)
    session_id = _required_text(data["session_id"], "session_id")
    if session_id != context.session_id:
        raise _fail(
            ErrorCode.PERMISSION_DENIED,
            "SPEECH_SESSION_MISMATCH",
            "speech session_id does not match the Gateway route",
        )
    timeout = _timeout_ms(data["timeout_ms"])
    return data, request_id, operation_id, correlation_id, scope, timeout


def parse_recognition_batch_request(
    payload: object, context: SpeechRpcContext
) -> RecognitionBatchRequest:
    data, request_id, operation_id, correlation_id, scope, timeout = _parse_common(
        payload,
        context,
        operation=RECOGNIZE_OPERATION,
        extra_keys={"capture", "audio", "locale"},
    )
    capture = _required_dict(data["capture"], "capture")
    _exact_keys(
        capture,
        required={"capture_id", "capture_generation", "track_id", "final"},
        field="capture",
    )
    if capture["final"] is not True:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "FINAL_CAPTURE_REQUIRED",
            "batch recognition accepts only a finalized capture",
        )
    audio = _required_dict(data["audio"], "audio")
    _exact_keys(
        audio,
        required={"format", "sample_rate_hz", "channel_count", "data_base64"},
        field="audio",
    )
    if audio["format"] != "wav_pcm16_mono" or audio["channel_count"] != 1:
        raise _fail(
            ErrorCode.UNSUPPORTED,
            "UNSUPPORTED_BATCH_AUDIO_FORMAT",
            "batch recognition requires mono PCM16 WAV",
        )
    sample_rate = _positive_int(audio["sample_rate_hz"], "audio.sample_rate_hz")
    audio_wav = _decode_base64(
        audio["data_base64"], field="audio.data_base64", max_bytes=MAX_BATCH_AUDIO_BYTES
    )
    inspect_pcm16_mono_wav(audio_wav, expected_sample_rate_hz=sample_rate)
    return RecognitionBatchRequest(
        request_id=request_id,
        operation_id=operation_id,
        correlation_id=correlation_id,
        scope=scope,
        capture_id=_required_text(capture["capture_id"], "capture.capture_id"),
        capture_generation=_non_negative_int(
            capture["capture_generation"], "capture.capture_generation"
        ),
        track_id=_required_text(capture["track_id"], "capture.track_id"),
        locale=_locale(data["locale"]),
        audio_wav=audio_wav,
        sample_rate_hz=sample_rate,
        timeout_ms=timeout,
    )


def _parse_response(value: object) -> ResponseRef:
    data = _required_dict(value, "response")
    _exact_keys(
        data,
        required={"interaction_id", "response_id", "response_generation"},
        field="response",
    )
    return ResponseRef(
        _required_text(data["interaction_id"], "response.interaction_id"),
        _required_text(data["response_id"], "response.response_id"),
        _non_negative_int(data["response_generation"], "response.response_generation"),
    )


def _parse_transforms(value: object, display_text: str) -> tuple[RenderTransform, ...]:
    if type(value) is not list:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "INVALID_RENDER_TRANSFORMS",
            "render_plan.transforms must be an array",
        )
    result: list[RenderTransform] = []
    for index, raw in enumerate(value):
        item = _required_dict(raw, f"render_plan.transforms[{index}]")
        _exact_keys(
            item,
            required={"transform", "source_start", "source_end", "rendered_text"},
            field=f"render_plan.transforms[{index}]",
        )
        transform = RenderTransform(
            _required_text(item["transform"], "transform"),
            _non_negative_int(item["source_start"], "source_start"),
            _non_negative_int(item["source_end"], "source_end"),
            _required_text(item["rendered_text"], "rendered_text"),
        )
        if transform.source_end < transform.source_start or transform.source_end > len(
            display_text
        ):
            raise _fail(
                ErrorCode.INVALID_ARGUMENT,
                "INVALID_RENDER_SPAN",
                "render transform span is invalid",
            )
        result.append(transform)
    return tuple(result)


def parse_synthesis_batch_request(
    payload: object, context: SpeechRpcContext
) -> SynthesisBatchRequest:
    data, request_id, operation_id, correlation_id, scope, timeout = _parse_common(
        payload,
        context,
        operation=SYNTHESIZE_OPERATION,
        extra_keys={
            "response",
            "unit_id",
            "render_plan",
            "authoritative_agent_text",
            "locale",
            "voice",
            "required_sample_rate_hz",
        },
    )
    if data["authoritative_agent_text"] is not True:
        raise _fail(
            ErrorCode.PERMISSION_DENIED,
            "AUTHORITATIVE_AGENT_TEXT_REQUIRED",
            "synthesis must declare Agent-text intent; server authorization is required",
        )
    plan = _required_dict(data["render_plan"], "render_plan")
    _exact_keys(
        plan,
        required={"display_text", "spoken_text", "transforms"},
        field="render_plan",
    )
    display_text = _required_text(plan["display_text"], "render_plan.display_text")
    spoken_text = _required_text(plan["spoken_text"], "render_plan.spoken_text")
    if len(spoken_text) > MAX_SYNTHESIS_TEXT_CHARS:
        raise _fail(
            ErrorCode.INVALID_ARGUMENT,
            "SYNTHESIS_TEXT_LIMIT_EXCEEDED",
            "synthesis text exceeds the package limit",
            details={"max_chars": MAX_SYNTHESIS_TEXT_CHARS},
        )
    voice_value = data["voice"]
    voice = None if voice_value is None else _required_text(voice_value, "voice")
    return SynthesisBatchRequest(
        request_id=request_id,
        operation_id=operation_id,
        correlation_id=correlation_id,
        scope=scope,
        response=_parse_response(data["response"]),
        unit_id=_required_text(data["unit_id"], "unit_id"),
        display_text=display_text,
        spoken_text=spoken_text,
        transforms=_parse_transforms(plan["transforms"], display_text),
        locale=_locale(data["locale"]),
        voice=voice,
        required_sample_rate_hz=_positive_int(
            data["required_sample_rate_hz"], "required_sample_rate_hz"
        ),
        timeout_ms=timeout,
    )


def _recognition_authorization_binding(
    request: RecognitionBatchRequest,
) -> SpeechAuthorizationBinding:
    content_sha256 = hashlib.sha256(
        canonical_json_bytes(
            {
                "capture_id": request.capture_id,
                "capture_generation": request.capture_generation,
                "track_id": request.track_id,
                "locale": request.locale,
                "sample_rate_hz": request.sample_rate_hz,
                "audio_sha256": hashlib.sha256(request.audio_wav).hexdigest(),
            }
        )
    ).hexdigest()
    return SpeechAuthorizationBinding(
        subject_id=request.scope.subject_id,
        scope=request.scope,
        operation=RECOGNIZE_OPERATION,
        operation_id=request.operation_id,
        correlation_id=request.correlation_id,
        capture_id=request.capture_id,
        capture_generation=request.capture_generation,
        track_id=request.track_id,
        response=None,
        unit_id=None,
        content_sha256=content_sha256,
    )


def _synthesis_authorization_binding(
    request: SynthesisBatchRequest,
) -> SpeechAuthorizationBinding:
    content_sha256 = hashlib.sha256(
        canonical_json_bytes(
            {
                "response": {
                    "interaction_id": request.response.interaction_id,
                    "response_id": request.response.response_id,
                    "response_generation": request.response.response_generation,
                },
                "unit_id": request.unit_id,
                "display_text": request.display_text,
                "spoken_text": request.spoken_text,
                "transforms": [
                    {
                        "transform": item.transform,
                        "source_start": item.source_start,
                        "source_end": item.source_end,
                        "rendered_text": item.rendered_text,
                    }
                    for item in request.transforms
                ],
                "locale": request.locale,
                "voice": request.voice,
                "required_sample_rate_hz": request.required_sample_rate_hz,
            }
        )
    ).hexdigest()
    return SpeechAuthorizationBinding(
        subject_id=request.scope.subject_id,
        scope=request.scope,
        operation=SYNTHESIZE_OPERATION,
        operation_id=request.operation_id,
        correlation_id=request.correlation_id,
        capture_id=None,
        capture_generation=None,
        track_id=None,
        response=request.response,
        unit_id=request.unit_id,
        content_sha256=content_sha256,
    )


def _result_envelope(
    request_id: str,
    operation_id: str,
    *,
    result: dict[str, object] | None = None,
    error: ContractError | None = None,
) -> dict[str, object]:
    ok = error is None
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "operation_id": operation_id,
        "ok": ok,
        "result": result if ok else None,
        "error": None if ok else error.to_dict(),
    }


def _provider_payload(
    provider_id: str,
    *,
    model: str,
    fallback_from: str | None = None,
) -> dict[str, object]:
    return {
        "provider_id": provider_id,
        "implementation_class": _IMPLEMENTATION_CLASS,
        "model": model,
        "fallback_from": fallback_from,
    }


@dataclass(slots=True)
class _VoiceCommitReceipt:
    operation_id: str
    capture_id: str
    capture_generation: int
    session_id: str
    correlation_id: str
    text: str
    expires_at: float
    claimed_binding: tuple[str, str, str, str, str, str] | None = None


class FormalBatchSpeechService:
    def __init__(
        self,
        provider: BatchSpeechProvider,
        *,
        authorization_resolver: SpeechAuthorizationResolver | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        max_completed_operations: int = MAX_COMPLETED_OPERATIONS,
        max_identity_tombstones: int = MAX_IDENTITY_TOMBSTONES,
    ) -> None:
        self._provider = provider
        self._provider_capability = provider.capability()
        self._authorization_resolver = authorization_resolver
        self._formal_available = (
            self._provider_capability.available
            and self._authorization_resolver is not None
        )
        provider_ref = ProviderRef(
            self._provider_capability.provider_id,
            _IMPLEMENTATION_CLASS if self._formal_available else "unsupported",
        )
        self._speech_capability = SpeechCapability(
            provider_ref,
            frozenset({SpeechMode.BATCH})
            if self._provider_capability.recognition_batch
            else frozenset(),
            frozenset({SpeechMode.BATCH})
            if self._provider_capability.synthesis_batch
            else frozenset(),
            self._formal_available,
        )
        self._monotonic = monotonic
        self._max_completed = max(1, max_completed_operations)
        self._max_identity_tombstones = max(1, max_identity_tombstones)
        self._lock = asyncio.Lock()
        self._closed = False
        self._close_task: asyncio.Task[dict[str, object]] | None = None
        self._operations: OrderedDict[tuple[ScopeRef, str], _OperationEntry] = (
            OrderedDict()
        )
        self._seen_captures: OrderedDict[tuple[ScopeRef, str], int] = OrderedDict()
        self._current_capture: OrderedDict[ScopeRef, tuple[str, int]] = OrderedDict()
        self._seen_response_ids: OrderedDict[tuple[ScopeRef, str], None] = OrderedDict()
        self._last_response_generation: OrderedDict[tuple[ScopeRef, str], int] = (
            OrderedDict()
        )
        self._voice_commit_receipts: OrderedDict[str, _VoiceCommitReceipt] = (
            OrderedDict()
        )

    async def claim_voice_commit_receipt(
        self,
        *,
        receipt: object,
        session_id: object,
        correlation_id: object,
        interaction_id: object,
        turn_id: object,
        commit_id: object,
        text: object,
        critical_confirmation: object,
    ) -> dict[str, object]:
        """Bind one formal STT result to one exact downstream TurnCommit.

        The browser holds only an opaque, short-lived capability.  Gateway
        redeems it immediately before E2A forwarding and replaces it with this
        closed server claim.  Exact request replay is allowed; rebinding a
        receipt to another turn, commit, interaction, or text fails closed.
        """

        token = str(receipt) if isinstance(receipt, str) else ""
        values = {
            "session_id": session_id,
            "correlation_id": correlation_id,
            "interaction_id": interaction_id,
            "turn_id": turn_id,
            "commit_id": commit_id,
            "text": text,
        }
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token) or any(
            type(value) is not str or not value or value != value.strip()
            for value in values.values()
        ):
            raise ValueError("voice commit receipt binding is invalid")
        now = self._monotonic()
        critical_tokens = CriticalTokenPolicy().scan(str(text))
        if critical_tokens and critical_confirmation is not True:
            raise ValueError("critical speech tokens require explicit confirmation")
        async with self._lock:
            self._prune_voice_commit_receipts_locked(now)
            retained = self._voice_commit_receipts.get(token)
            if retained is None or retained.expires_at <= now:
                raise ValueError("voice commit receipt is unknown or expired")
            binding = (
                str(session_id),
                str(correlation_id),
                str(interaction_id),
                str(turn_id),
                str(commit_id),
                str(text),
            )
            if (
                retained.session_id != binding[0]
                or retained.correlation_id != binding[1]
                or retained.text != binding[5]
            ):
                raise ValueError("voice commit receipt does not match recognition")
            if retained.claimed_binding is None:
                retained.claimed_binding = binding
            elif retained.claimed_binding != binding:
                raise ValueError("voice commit receipt was already bound")
            self._voice_commit_receipts.move_to_end(token)
            return {
                "kind": "formal_speech_recognition",
                "speech_operation_id": retained.operation_id,
                "capture_id": retained.capture_id,
                "capture_generation": retained.capture_generation,
                "session_id": retained.session_id,
                "correlation_id": retained.correlation_id,
                "interaction_id": binding[2],
                "turn_id": binding[3],
                "commit_id": binding[4],
                "text_sha256": hashlib.sha256(binding[5].encode("utf-8")).hexdigest(),
                "critical_policy": "confirmed" if critical_tokens else "eligible",
            }

    async def _issue_voice_commit_receipt(
        self, request: RecognitionBatchRequest, text: str
    ) -> str:
        now = self._monotonic()
        async with self._lock:
            self._prune_voice_commit_receipts_locked(now)
            if len(self._voice_commit_receipts) >= MAX_VOICE_COMMIT_RECEIPTS:
                raise _fail(
                    ErrorCode.UNAVAILABLE,
                    "VOICE_COMMIT_RECEIPT_CAPACITY_EXHAUSTED",
                    "formal voice commit receipt capacity is exhausted",
                    retriable=True,
                )
            token = secrets.token_urlsafe(32)
            self._voice_commit_receipts[token] = _VoiceCommitReceipt(
                operation_id=request.operation_id,
                capture_id=request.capture_id,
                capture_generation=request.capture_generation,
                session_id=request.scope.session_id or "",
                correlation_id=request.correlation_id,
                text=text,
                expires_at=now + VOICE_COMMIT_RECEIPT_TTL_SECONDS,
            )
            return token

    def _prune_voice_commit_receipts_locked(self, now: float) -> None:
        for token, retained in tuple(self._voice_commit_receipts.items()):
            if retained.expires_at <= now:
                self._voice_commit_receipts.pop(token, None)

    def capability_payload(self) -> dict[str, object]:
        formal_available = self._formal_available and not self._closed
        operations: list[str] = [CAPABILITIES_OPERATION]
        if formal_available and self._provider_capability.recognition_batch:
            operations.append(RECOGNIZE_OPERATION)
        if formal_available and self._provider_capability.synthesis_batch:
            operations.append(SYNTHESIZE_OPERATION)
        operations.append(CANCEL_OPERATION)
        descriptor = CapabilityDescriptor.from_dict(
            {
                "component": "speech.batch.gateway",
                "contract_major": "v2",
                "supported_operations": operations,
                "supported_event_types": [],
                "batch_modes": ["batch"],
                "stream_modes": [],
                "supports_cancel_ack": True,
                "supports_replay": False,
                "declared_limits": {
                    "max_input_audio_bytes": MAX_BATCH_AUDIO_BYTES,
                    "max_output_audio_bytes": MAX_SYNTHESIS_AUDIO_BYTES,
                    "max_recognition_text_chars": MAX_RECOGNITION_TEXT_CHARS,
                    "max_text_chars": MAX_SYNTHESIS_TEXT_CHARS,
                    "max_timeout_ms": MAX_BATCH_TIMEOUT_MS,
                    "recognition_input": "wav_pcm16_mono",
                    "synthesis_output": "wav_pcm16_mono",
                    "resampling": "server_linear_pcm16_mono",
                    "credential_boundary": "gateway_only",
                    "max_operation_capacity": self._max_completed,
                    "operation_replay_window": self._max_completed,
                    "identity_tombstone_window": self._max_identity_tombstones,
                    "close_timeout_max_ms": MAX_CLOSE_TIMEOUT_MS,
                    "authorization": "authenticated_server_owned_exact_binding",
                },
                "fallback_identity": "browser-speech-compatibility",
                "availability": (
                    Availability.AVAILABLE.value
                    if formal_available
                    else Availability.UNAVAILABLE.value
                ),
            }
        )
        return {
            "contract_version": CONTRACT_VERSION,
            "capability": descriptor.to_dict(),
            "provider": {
                "provider_id": self._provider_capability.provider_id,
                "implementation_class": (
                    _IMPLEMENTATION_CLASS if formal_available else "unsupported"
                ),
                "available": formal_available,
                "provider_configured": self._provider_capability.available,
                "authorization_available": self._authorization_resolver is not None,
                "service_closed": self._closed,
            },
            "fallback": {
                "recognition": "browser-speech-recognition",
                "synthesis": "browser-speech-synthesis",
                "automatic": False,
            },
        }

    async def recognize(
        self, payload: object, context: SpeechRpcContext
    ) -> dict[str, object]:
        request_id = "unknown"
        operation_id = "unknown"
        try:
            request = parse_recognition_batch_request(payload, context)
            request_id = request.request_id
            operation_id = request.operation_id
            self._authorize(
                _recognition_authorization_binding(request), context.assurance
            )
            fingerprint = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "kind": RECOGNIZE_OPERATION,
                        "operation_id": request.operation_id,
                        "correlation_id": request.correlation_id,
                        "scope": request.scope.to_dict(),
                        "capture_id": request.capture_id,
                        "capture_generation": request.capture_generation,
                        "track_id": request.track_id,
                        "locale": request.locale,
                        "sample_rate_hz": request.sample_rate_hz,
                        "audio_sha256": hashlib.sha256(request.audio_wav).hexdigest(),
                        "timeout_ms": request.timeout_ms,
                    }
                )
            ).digest()
            return await self._execute(
                request.operation_id,
                request.request_id,
                request.scope,
                request.correlation_id,
                RECOGNIZE_OPERATION,
                fingerprint,
                request.timeout_ms,
                lambda: self._recognize_once(request),
                reserve=lambda: self._reserve_capture(request),
            )
        except BatchSpeechError as exc:
            return _result_envelope(request_id, operation_id, error=exc.error)
        except Exception:
            return _result_envelope(
                request_id,
                operation_id,
                error=_contract_error(
                    ErrorCode.INTERNAL,
                    "SPEECH_ADAPTER_INTERNAL",
                    "formal batch speech failed internally",
                ),
            )

    async def synthesize(
        self, payload: object, context: SpeechRpcContext
    ) -> dict[str, object]:
        request_id = "unknown"
        operation_id = "unknown"
        try:
            request = parse_synthesis_batch_request(payload, context)
            request_id = request.request_id
            operation_id = request.operation_id
            self._authorize(
                _synthesis_authorization_binding(request), context.assurance
            )
            fingerprint = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "kind": SYNTHESIZE_OPERATION,
                        "operation_id": request.operation_id,
                        "correlation_id": request.correlation_id,
                        "scope": request.scope.to_dict(),
                        "response": {
                            "interaction_id": request.response.interaction_id,
                            "response_id": request.response.response_id,
                            "response_generation": request.response.response_generation,
                        },
                        "unit_id": request.unit_id,
                        "display_text": request.display_text,
                        "spoken_text": request.spoken_text,
                        "transforms": [
                            {
                                "transform": item.transform,
                                "source_start": item.source_start,
                                "source_end": item.source_end,
                                "rendered_text": item.rendered_text,
                            }
                            for item in request.transforms
                        ],
                        "locale": request.locale,
                        "voice": request.voice,
                        "required_sample_rate_hz": request.required_sample_rate_hz,
                        "timeout_ms": request.timeout_ms,
                    }
                )
            ).digest()
            return await self._execute(
                request.operation_id,
                request.request_id,
                request.scope,
                request.correlation_id,
                SYNTHESIZE_OPERATION,
                fingerprint,
                request.timeout_ms,
                lambda: self._synthesize_once(request),
                reserve=lambda: self._reserve_response(request),
            )
        except BatchSpeechError as exc:
            return _result_envelope(request_id, operation_id, error=exc.error)
        except Exception:
            return _result_envelope(
                request_id,
                operation_id,
                error=_contract_error(
                    ErrorCode.INTERNAL,
                    "SPEECH_ADAPTER_INTERNAL",
                    "formal batch speech failed internally",
                ),
            )

    async def cancel(
        self, payload: object, context: SpeechRpcContext
    ) -> dict[str, object]:
        request_id = "unknown"
        operation_id = "unknown"
        try:
            data = _required_dict(payload, "cancel_request")
            _exact_keys(
                data,
                required={
                    "contract_version",
                    "request_id",
                    "operation_id",
                    "operation",
                    "correlation_id",
                    "scope",
                    "session_id",
                    "target_operation_id",
                },
                field="cancel_request",
            )
            if data["contract_version"] != CONTRACT_VERSION:
                raise _fail(
                    ErrorCode.UNSUPPORTED,
                    "UNSUPPORTED_CONTRACT_VERSION",
                    f"expected {CONTRACT_VERSION}",
                )
            if data["operation"] != CANCEL_OPERATION:
                raise _fail(
                    ErrorCode.INVALID_ARGUMENT,
                    "SPEECH_OPERATION_MISMATCH",
                    "speech cancel operation does not match the Gateway method",
                )
            request_id = _required_text(data["request_id"], "request_id")
            operation_id = _required_text(data["operation_id"], "operation_id")
            correlation_id = _required_text(data["correlation_id"], "correlation_id")
            scope = _scope(data["scope"], context)
            self._require_authenticated(context.assurance)
            session_id = _required_text(data["session_id"], "session_id")
            if session_id != context.session_id:
                raise _fail(
                    ErrorCode.PERMISSION_DENIED,
                    "SPEECH_SESSION_MISMATCH",
                    "speech session_id does not match the Gateway route",
                )
            target = _required_text(data["target_operation_id"], "target_operation_id")
            async with self._lock:
                operation_key = (scope, target)
                entry = self._operations.get(operation_key)
                if entry is None:
                    raise _fail(
                        ErrorCode.NOT_FOUND,
                        "SPEECH_OPERATION_NOT_FOUND",
                        "target speech operation was not found",
                    )
                if entry.scope != scope:
                    raise _fail(
                        ErrorCode.PERMISSION_DENIED,
                        "SPEECH_SCOPE_MISMATCH",
                        "speech cancel scope does not match the target operation",
                    )
                if entry.correlation_id != correlation_id:
                    raise _fail(
                        ErrorCode.PERMISSION_DENIED,
                        "SPEECH_CORRELATION_MISMATCH",
                        "speech cancel correlation does not match the target operation",
                    )
                if (
                    entry.task.done()
                    or entry.worker_terminal
                    or entry.fence_code is not None
                ):
                    result = {
                        "accepted": False,
                        "target_operation_id": target,
                        "already_terminal": True,
                        "provider_completion_known": entry.provider_completion_known,
                    }
                else:
                    self._fence_entry(
                        entry,
                        ErrorCode.CANCELLED,
                        "SPEECH_OPERATION_CANCELLED",
                    )
                    result = {
                        "accepted": True,
                        "target_operation_id": target,
                        "already_terminal": False,
                        "provider_completion_known": entry.provider_completion_known,
                    }
            return _result_envelope(request_id, operation_id, result=result)
        except BatchSpeechError as exc:
            return _result_envelope(request_id, operation_id, error=exc.error)

    @staticmethod
    def _require_authenticated(assurance: Assurance) -> None:
        if assurance is not Assurance.AUTHENTICATED:
            raise _fail(
                ErrorCode.UNAUTHENTICATED,
                "SPEECH_AUTHENTICATED_IDENTITY_REQUIRED",
                "formal Provider speech requires an authenticated server identity",
            )

    def _authorize(
        self, binding: SpeechAuthorizationBinding, assurance: Assurance
    ) -> None:
        self._require_authenticated(assurance)
        resolver = self._authorization_resolver
        if resolver is None:
            raise _fail(
                ErrorCode.UNAVAILABLE,
                "SPEECH_AUTHORIZATION_UNAVAILABLE",
                "formal Provider speech authorization is unavailable",
            )
        try:
            grant = resolver.authorize(binding)
        except Exception as exc:
            raise _fail(
                ErrorCode.UNAVAILABLE,
                "SPEECH_AUTHORIZATION_UNAVAILABLE",
                "formal Provider speech authorization is unavailable",
            ) from exc
        if grant != binding:
            raise _fail(
                ErrorCode.PERMISSION_DENIED,
                "SPEECH_OPERATION_NOT_AUTHORIZED",
                "formal Provider speech was not authorized",
            )

    async def close(
        self, timeout_ms: int = DEFAULT_CLOSE_TIMEOUT_MS
    ) -> dict[str, object]:
        if type(timeout_ms) is not int or not (
            MIN_CLOSE_TIMEOUT_MS <= timeout_ms <= MAX_CLOSE_TIMEOUT_MS
        ):
            raise ValueError(
                f"close timeout_ms must be between {MIN_CLOSE_TIMEOUT_MS} "
                f"and {MAX_CLOSE_TIMEOUT_MS}"
            )
        async with self._lock:
            if self._close_task is None or self._close_task.done():
                self._close_task = asyncio.create_task(
                    self._close_once(timeout_ms),
                    name="live-voice-formal-speech-close",
                )
            close_task = self._close_task
        return await asyncio.shield(close_task)

    async def _close_once(self, timeout_ms: int) -> dict[str, object]:
        async with self._lock:
            self._closed = True
            operation_items = list(self._operations.items())
            for _, entry in operation_items:
                if not entry.task.done():
                    self._fence_entry(
                        entry,
                        ErrorCode.CANCELLED,
                        "SPEECH_SERVICE_CLOSED",
                    )
                worker = entry.worker_task
                if worker is not None and not worker.done():
                    worker.cancel()
            tracked = {
                task
                for _, entry in operation_items
                for task in (entry.task, entry.worker_task)
                if task is not None and not task.done()
            }
        if tracked:
            await asyncio.wait(tracked, timeout=timeout_ms / 1000)
        provider_stragglers = [
            (operation_key, entry)
            for operation_key, entry in operation_items
            if entry.worker_task is not None and not entry.worker_task.done()
        ]
        operation_stragglers = [
            (operation_key, entry)
            for operation_key, entry in operation_items
            if not entry.task.done()
        ]
        return {
            "closed": True,
            "timeout_ms": timeout_ms,
            "tracked_operation_count": len(operation_items),
            "provider_completion_known_count": sum(
                1 for _, entry in operation_items if entry.provider_completion_known
            ),
            "provider_straggler_count": len(provider_stragglers),
            "provider_straggler_operation_ids": sorted(
                operation_key[1] for operation_key, _ in provider_stragglers
            ),
            "operation_straggler_count": len(operation_stragglers),
            "operation_straggler_operation_ids": sorted(
                operation_key[1] for operation_key, _ in operation_stragglers
            ),
            "clean": not provider_stragglers and not operation_stragglers,
        }

    async def _execute(
        self,
        operation_id: str,
        request_id: str,
        scope: ScopeRef,
        correlation_id: str,
        kind: str,
        fingerprint: bytes,
        timeout_ms: int,
        runner: Callable[[], Awaitable[dict[str, object]]],
        *,
        reserve: Callable[[], None],
    ) -> dict[str, object]:
        operation_key = (scope, operation_id)
        async with self._lock:
            existing = self._operations.get(operation_key)
            if existing is not None:
                if (
                    existing.fingerprint != fingerprint
                    or existing.scope != scope
                    or existing.correlation_id != correlation_id
                    or existing.kind != kind
                ):
                    raise _fail(
                        ErrorCode.CONFLICT,
                        "SPEECH_OPERATION_ID_CONFLICT",
                        "operation_id was reused with different speech input",
                    )
                task = existing.task
                self._operations.move_to_end(operation_key)
            else:
                if self._closed:
                    raise _fail(
                        ErrorCode.UNAVAILABLE,
                        "SPEECH_SERVICE_CLOSED",
                        "formal batch speech service is closed",
                    )
                self._evict_completed_locked()
                reserve()
                task = asyncio.create_task(
                    self._run_operation(
                        operation_id,
                        request_id,
                        scope,
                        timeout_ms,
                        runner,
                    ),
                    name=f"live-voice-{kind}-{operation_id}",
                )
                self._operations[operation_key] = _OperationEntry(
                    fingerprint=fingerprint,
                    scope=scope,
                    correlation_id=correlation_id,
                    kind=kind,
                    task=task,
                )
        result = await asyncio.shield(task)
        replay = dict(result)
        replay["request_id"] = request_id
        return replay

    async def _run_operation(
        self,
        operation_id: str,
        request_id: str,
        scope: ScopeRef,
        timeout_ms: int,
        runner: Callable[[], Awaitable[dict[str, object]]],
    ) -> dict[str, object]:
        entry = self._operations[(scope, operation_id)]
        if entry.fence_code is not None:
            return _result_envelope(
                request_id, operation_id, error=self._fence_error(entry)
            )
        loop = asyncio.get_running_loop()
        entry.deadline_at = loop.time() + (timeout_ms / 1000)
        worker = asyncio.create_task(
            self._invoke_worker(entry, runner),
            name=f"live-voice-provider-work-{operation_id}",
        )
        entry.worker_task = worker
        entry.deadline_handle = loop.call_at(
            entry.deadline_at,
            self._fence_entry,
            entry,
            ErrorCode.TIMEOUT,
            "SPEECH_PROVIDER_TIMEOUT",
        )
        worker.add_done_callback(self._consume_background_task)
        fence_waiter = asyncio.create_task(entry.fence_event.wait())
        try:
            done, _ = await asyncio.wait(
                {worker, fence_waiter},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if entry.fence_code is not None:
                return _result_envelope(
                    request_id, operation_id, error=self._fence_error(entry)
                )
            if worker not in done:
                raise RuntimeError("speech operation woke without a terminal state")
            result = worker.result()
            self._ensure_not_fenced(scope, operation_id)
            return _result_envelope(request_id, operation_id, result=result)
        except asyncio.CancelledError:
            if entry.fence_code is None:
                self._fence_entry(
                    entry,
                    ErrorCode.CANCELLED,
                    "SPEECH_OPERATION_CANCELLED",
                )
            return _result_envelope(
                request_id, operation_id, error=self._fence_error(entry)
            )
        except BatchSpeechError as exc:
            return _result_envelope(request_id, operation_id, error=exc.error)
        except SpeechPortViolation as exc:
            code = (
                ErrorCode.STALE
                if "STALE" in exc.reason
                else ErrorCode.UNSUPPORTED
                if "UNSUPPORTED" in exc.reason
                else ErrorCode.UNAVAILABLE
                if "UNAVAILABLE" in exc.reason
                else ErrorCode.INVALID_ARGUMENT
            )
            return _result_envelope(
                request_id,
                operation_id,
                error=_contract_error(code, exc.reason, str(exc)),
            )
        except Exception:
            return _result_envelope(
                request_id,
                operation_id,
                error=_contract_error(
                    ErrorCode.INTERNAL,
                    "SPEECH_ADAPTER_INTERNAL",
                    "formal batch speech failed internally",
                ),
            )
        finally:
            deadline_handle = entry.deadline_handle
            if deadline_handle is not None:
                deadline_handle.cancel()
            if not fence_waiter.done():
                fence_waiter.cancel()

    async def _invoke_worker(
        self,
        entry: _OperationEntry,
        runner: Callable[[], Awaitable[dict[str, object]]],
    ) -> dict[str, object]:
        try:
            result = await runner()
        except asyncio.CancelledError:
            self._record_worker_terminal(entry, cancelled=True)
            raise
        except BaseException:
            self._record_worker_terminal(entry, cancelled=False)
            raise
        self._record_worker_terminal(entry, cancelled=False)
        return result

    def _record_worker_terminal(
        self, entry: _OperationEntry, *, cancelled: bool
    ) -> None:
        if entry.fence_code is not None or entry.worker_terminal:
            return
        deadline_at = entry.deadline_at
        if deadline_at is not None and asyncio.get_running_loop().time() >= deadline_at:
            self._fence_entry(
                entry,
                ErrorCode.TIMEOUT,
                "SPEECH_PROVIDER_TIMEOUT",
                cancel_worker=False,
            )
            return
        if cancelled:
            self._fence_entry(
                entry,
                ErrorCode.CANCELLED,
                "SPEECH_OPERATION_CANCELLED",
                cancel_worker=False,
            )
            return
        entry.worker_terminal = True
        deadline_handle = entry.deadline_handle
        if deadline_handle is not None:
            deadline_handle.cancel()

    @staticmethod
    def _consume_background_task(task: asyncio.Task[object]) -> None:
        try:
            task.exception()
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _fence_error(entry: _OperationEntry) -> ContractError:
        if entry.fence_code is ErrorCode.TIMEOUT:
            return _contract_error(
                ErrorCode.TIMEOUT,
                entry.fence_reason or "SPEECH_PROVIDER_TIMEOUT",
                "formal batch speech timed out",
                retriable=True,
            )
        return _contract_error(
            ErrorCode.CANCELLED,
            entry.fence_reason or "SPEECH_OPERATION_CANCELLED",
            "formal batch speech was cancelled",
        )

    @staticmethod
    def _fence_entry(
        entry: _OperationEntry,
        code: ErrorCode,
        reason: str,
        *,
        cancel_worker: bool = True,
    ) -> bool:
        if entry.fence_code is not None or entry.worker_terminal:
            return False
        entry.fence_code = code
        entry.fence_reason = reason
        deadline_handle = entry.deadline_handle
        if deadline_handle is not None:
            deadline_handle.cancel()
        entry.fence_event.set()
        worker = entry.worker_task
        if cancel_worker and worker is not None and not worker.done():
            worker.cancel()
        return True

    def _ensure_not_fenced(self, scope: ScopeRef, operation_id: str) -> None:
        entry = self._operations.get((scope, operation_id))
        if entry is not None and entry.fence_code is not None:
            raise BatchSpeechError(self._fence_error(entry))

    def _mark_provider_completion_known(
        self, scope: ScopeRef, operation_id: str
    ) -> None:
        entry = self._operations.get((scope, operation_id))
        if entry is not None:
            entry.provider_completion_known = True

    def _bounded_identity_put(
        self, mapping: OrderedDict, key: object, value: object
    ) -> None:
        mapping[key] = value
        mapping.move_to_end(key)
        while len(mapping) > self._max_identity_tombstones:
            mapping.popitem(last=False)

    def _reserve_capture(self, request: RecognitionBatchRequest) -> None:
        capture_key = (request.scope, request.capture_id)
        seen_generation = self._seen_captures.get(capture_key)
        if seen_generation is not None:
            if seen_generation != request.capture_generation:
                raise _fail(
                    ErrorCode.CONFLICT,
                    "CAPTURE_ID_REUSED",
                    "capture_id cannot be reused with another AIO capture generation",
                )
            raise _fail(
                ErrorCode.STALE,
                "STALE_RECOGNITION_SESSION",
                "capture generation is duplicated",
            )
        self._bounded_identity_put(
            self._seen_captures, capture_key, request.capture_generation
        )
        self._bounded_identity_put(
            self._current_capture,
            request.scope,
            (request.capture_id, request.capture_generation),
        )

    def _reserve_response(self, request: SynthesisBatchRequest) -> None:
        response = request.response
        response_id_key = (request.scope, response.response_id)
        interaction_key = (request.scope, response.interaction_id)
        if response_id_key in self._seen_response_ids:
            raise _fail(
                ErrorCode.CONFLICT,
                "RESPONSE_ID_REUSED",
                "response_id cannot be reused for synthesis",
            )
        last = self._last_response_generation.get(interaction_key, -1)
        if response.response_generation <= last:
            raise _fail(
                ErrorCode.STALE,
                "STALE_SYNTHESIS_RESPONSE",
                "response generation is stale",
            )
        self._bounded_identity_put(self._seen_response_ids, response_id_key, None)
        self._bounded_identity_put(
            self._last_response_generation,
            interaction_key,
            response.response_generation,
        )

    def _ensure_capture_current(self, request: RecognitionBatchRequest) -> None:
        current = self._current_capture.get(request.scope)
        if current != (request.capture_id, request.capture_generation):
            raise _fail(
                ErrorCode.STALE,
                "STALE_RECOGNITION_SESSION",
                "a newer capture generation fenced this recognition result",
            )

    def _ensure_response_current(self, request: SynthesisBatchRequest) -> None:
        current = self._last_response_generation.get(
            (request.scope, request.response.interaction_id)
        )
        if current != request.response.response_generation:
            raise _fail(
                ErrorCode.STALE,
                "STALE_SYNTHESIS_RESPONSE",
                "a newer response generation fenced this synthesis result",
            )

    def _evict_completed_locked(self) -> None:
        while len(self._operations) >= self._max_completed:
            completed_key = next(
                (
                    key
                    for key, entry in self._operations.items()
                    if entry.task.done()
                    and (entry.worker_task is None or entry.worker_task.done())
                ),
                None,
            )
            if completed_key is None:
                raise _fail(
                    ErrorCode.UNAVAILABLE,
                    "SPEECH_OPERATION_CAPACITY",
                    "formal batch speech operation capacity is exhausted",
                    retriable=True,
                )
            self._operations.pop(completed_key)

    async def _recognize_once(
        self, request: RecognitionBatchRequest
    ) -> dict[str, object]:
        if not self._provider_capability.available:
            raise _fail(
                ErrorCode.UNAVAILABLE,
                "SPEECH_PROVIDER_UNAVAILABLE",
                "formal batch speech Provider is unavailable",
                retriable=True,
            )
        if not self._provider_capability.recognition_batch:
            raise _fail(
                ErrorCode.UNSUPPORTED,
                "SPEECH_RECOGNITION_UNSUPPORTED",
                "formal batch recognition is unsupported",
            )
        recognition = RecognitionPort(self._speech_capability)
        session = recognition.start(request.capture_id, SpeechMode.BATCH)
        started = self._monotonic()
        try:
            provider_result = await self._provider.recognize(
                ProviderRecognitionRequest(
                    request.operation_id, request.audio_wav, request.locale
                )
            )
            self._mark_provider_completion_known(request.scope, request.operation_id)
            self._ensure_not_fenced(request.scope, request.operation_id)
            self._ensure_capture_current(request)
        except BaseException:
            try:
                recognition.emit(
                    session.session_id,
                    session.generation,
                    RecognitionEventKind.CANCELLED,
                )
            except SpeechPortViolation:
                pass
            raise
        hypothesis = RecognitionHypothesis(
            (
                RecognitionAlternative(
                    provider_result.text,
                    provider_result.text,
                    None,
                ),
            )
        )
        event = recognition.emit(
            session.session_id,
            session.generation,
            RecognitionEventKind.FINAL,
            hypothesis,
        )
        wav_info = inspect_pcm16_mono_wav(request.audio_wav)
        voice_commit_receipt = await self._issue_voice_commit_receipt(
            request, provider_result.text
        )
        return {
            "operation": RECOGNIZE_OPERATION,
            "capture": {
                "capture_id": request.capture_id,
                "capture_generation": request.capture_generation,
                "track_id": request.track_id,
                "final": True,
            },
            "event": {
                "session_id": request.capture_id,
                "generation": request.capture_generation,
                "seq": event.seq,
                "kind": event.kind.value,
                "hypothesis": {
                    "alternatives": [
                        {
                            "raw_text": provider_result.text,
                            "display_text": provider_result.text,
                            "confidence": None,
                        }
                    ],
                    "selected_index": 0,
                },
                "commits_turn": False,
            },
            "locale": {
                "requested": request.locale,
                "observed": provider_result.observed_locale,
            },
            "timing": {
                "audio_duration_ms": wav_info.duration_ms,
                "provider_elapsed_ms": max(
                    0, round((self._monotonic() - started) * 1000)
                ),
            },
            "provider": _provider_payload(
                event.provider.provider_id, model=provider_result.model
            ),
            "voice_commit_receipt": voice_commit_receipt,
        }

    async def _synthesize_once(
        self, request: SynthesisBatchRequest
    ) -> dict[str, object]:
        if not self._provider_capability.available:
            raise _fail(
                ErrorCode.UNAVAILABLE,
                "SPEECH_PROVIDER_UNAVAILABLE",
                "formal batch speech Provider is unavailable",
                retriable=True,
            )
        if not self._provider_capability.synthesis_batch:
            raise _fail(
                ErrorCode.UNSUPPORTED,
                "SPEECH_SYNTHESIS_UNSUPPORTED",
                "formal batch synthesis is unsupported",
            )
        synthesis = SynthesisPort(self._speech_capability)
        plan = synthesis.create_render_plan(
            request.display_text, request.spoken_text, request.transforms
        )
        synthesis.activate_response(request.response)
        started_event = synthesis.start(
            SynthesisRequest(
                request.operation_id,
                request.response,
                request.unit_id,
                0,
                len(request.display_text),
                plan,
                SpeechMode.BATCH,
            )
        )
        try:
            provider_result = await self._provider.synthesize(
                ProviderSynthesisRequest(
                    request.operation_id,
                    request.spoken_text,
                    request.locale,
                    request.voice,
                    request.required_sample_rate_hz,
                )
            )
            self._mark_provider_completion_known(request.scope, request.operation_id)
            self._ensure_not_fenced(request.scope, request.operation_id)
            self._ensure_response_current(request)
            wav_info = inspect_pcm16_mono_wav(
                provider_result.audio_wav,
                expected_sample_rate_hz=request.required_sample_rate_hz,
            )
            chunk_event = synthesis.emit_chunk(
                request.operation_id, provider_result.audio_wav
            )
            completed_event = synthesis.complete(request.operation_id)
        except BaseException:
            try:
                synthesis.cancel(request.operation_id)
            except SpeechPortViolation:
                pass
            raise
        return {
            "operation": SYNTHESIZE_OPERATION,
            "response": {
                "interaction_id": request.response.interaction_id,
                "response_id": request.response.response_id,
                "response_generation": request.response.response_generation,
            },
            "unit_id": request.unit_id,
            "render_plan": {
                "display_sha256": plan.display_sha256,
                "spoken_text_sha256": hashlib.sha256(
                    plan.spoken_text.encode("utf-8")
                ).hexdigest(),
            },
            "events": {
                "started_seq": started_event.seq,
                "chunk_seq": chunk_event.seq,
                "completed_seq": completed_event.seq,
            },
            "audio": {
                "format": "wav_pcm16_mono",
                "sample_rate_hz": wav_info.sample_rate_hz,
                "channel_count": wav_info.channel_count,
                "duration_ms": wav_info.duration_ms,
                "data_base64": base64.b64encode(provider_result.audio_wav).decode(
                    "ascii"
                ),
            },
            "provider": _provider_payload(
                chunk_event.provider.provider_id,
                model=provider_result.model,
            )
            | {"voice": provider_result.voice},
            "presented": False,
        }
