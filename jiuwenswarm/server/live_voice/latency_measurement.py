# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Content-free L0 latency measurement over production observability facts.

The product protocol and ``live-voice.observability.v1`` schema intentionally
remain unchanged.  This module wraps a validated :class:`LiveVoiceObservation`
with run-only identity/classification fields that the shared schema does not
carry (Session and activation generation).  The wrapper is a local evidence
format, never a lifecycle, mutation, presentation, or telemetry authority.

No audio, transcript, credential, URL, device identity, project content, or
arbitrary attribute map is accepted.  Missing milestones stay absent and are
reported as ``None``/unknown; they are never synthesized as zero.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from collections import Counter, OrderedDict, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import Lock
from types import MappingProxyType
from typing import Final

from jiuwenswarm.server.live_voice.observability import (
    LIVE_VOICE_CONTRACT_VERSION,
    OBSERVABILITY_SCHEMA_VERSION,
    LiveVoiceObservation,
    contains_private_observability_content,
    create_observation,
)


L0_MEASUREMENT_ENVELOPE_VERSION: Final = "live-voice.l0-measurement-envelope.v1"
L0_MEASUREMENT_REPORT_VERSION: Final = "live-voice.l0-measurement-report.v1"
L0_CORPUS_MANIFEST_VERSION: Final = "live-voice.l0-corpus.v1"
L0_MEASUREMENT_DIRECTORY_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_L0_MEASUREMENT_DIR"
)
L0_MEASUREMENT_PROFILE_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_L0_MEASUREMENT_PROFILE"
)
L0_MEASUREMENT_SCENARIO_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_L0_MEASUREMENT_SCENARIO"
)
L0_MEASUREMENT_SAMPLE_ENV: Final = "JIUWENSWARM_LIVE_VOICE_L0_MEASUREMENT_SAMPLE"
L0_MEASUREMENT_TEMPERATURE_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_L0_MEASUREMENT_TEMPERATURE"
)
L0_MEASUREMENT_EVIDENCE_SOURCE_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_L0_MEASUREMENT_EVIDENCE_SOURCE"
)
L0_MEASUREMENT_RUN_LABELS_FILE_ENV: Final = (
    "JIUWENSWARM_LIVE_VOICE_L0_MEASUREMENT_RUN_LABELS_FILE"
)
L0_RUN_LABELS_VERSION: Final = "live-voice.l0-run-labels.v1"
L0_MAX_FILE_BYTES: Final = 16 * 1024 * 1024
L0_MAX_RECORDS: Final = 100_000
L0_MAX_ROUNDS: Final = 10_000
L0_MAX_SAFE_INTEGER: Final = 9_007_199_254_740_991

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_PROFILE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_TIMESTAMP = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?Z$"
)


class L0MeasurementViolation(ValueError):
    """Fail-closed local measurement contract violation."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class L0Milestone(StrEnum):
    PROVIDER_EOT = "provider_eot"
    BROWSER_EOT_RECEIPT = "browser_eot_receipt"
    CAPTURE_STOPPED = "capture_stopped"
    LAST_FRAME_SENT = "last_frame_sent"
    LAST_FRAME_ACKED = "last_frame_acked"
    UPLINK_CLOSED = "uplink_closed"
    STT_FINAL_AVAILABLE = "stt_final_available"
    COMMITTED_SUBMIT_ACCEPTED = "committed_submit_accepted"
    AGENT_REQUEST_START = "agent_request_start"
    FIRST_DELTA = "first_delta"
    FIRST_STABLE_SPEAKABLE_SENTENCE = "first_stable_speakable_sentence"
    CHAT_FINAL = "chat_final"
    TTS_REQUEST = "tts_request"
    PROVIDER_FIRST_AUDIO = "provider_first_audio"
    DOWNLINK_TICKET = "downlink_ticket"
    SUCCESSOR_CAPTURE_READY = "successor_capture_ready"
    BROWSER_FIRST_FRAME = "browser_first_frame"
    WEBAUDIO_FIRST_FRAME_SCHEDULED = "webaudio_first_frame_scheduled"
    WEBAUDIO_ACTUALLY_STARTED = "webaudio_actually_started"
    PLAYOUT_COMPLETED = "playout_completed"
    UNDERRUN = "underrun"
    REBUFFER = "rebuffer"
    FRAME_LOSS = "frame_loss"
    FALSE_EOT = "false_eot"
    MISSED_EOT = "missed_eot"
    FAILURE = "failure"
    BARGE_IN = "barge_in"
    FENCE_CANCEL_COMPLETION = "fence_cancel_completion"
    FALLBACK = "fallback"
    DISCARDED_WORK = "discarded_work"


class L0RoundTemperature(StrEnum):
    COLD = "cold"
    WARM = "warm"
    UNKNOWN = "unknown"


class L0RoundClassification(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    FALLBACK = "fallback"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class L0EvidenceSource(StrEnum):
    INJECTED = "injected"
    PRERECORDED = "prerecorded"
    DIGITAL_LOOPBACK = "digital_loopback"
    REAL_PROVIDER = "real_provider"
    PHYSICAL = "physical"


@dataclass(frozen=True, slots=True)
class _MarkerRule:
    event_name: str
    segment_name: str
    source_component: str
    state: str | None = None
    outcome: str | None = None
    reason_code: str | None = None
    error_code: str | None = None
    cancel_scope: str | None = None
    route_class: str = "formal"


def _rule(
    event_name: str,
    segment_name: str,
    source_component: str,
    *,
    state: str | None = None,
    outcome: str | None = None,
    reason_code: str | None = None,
    error_code: str | None = None,
    cancel_scope: str | None = None,
    route_class: str = "formal",
) -> _MarkerRule:
    return _MarkerRule(
        event_name,
        segment_name,
        source_component,
        state,
        outcome,
        reason_code,
        error_code,
        cancel_scope,
        route_class,
    )


_MARKER_RULES: Final[Mapping[L0Milestone, _MarkerRule]] = MappingProxyType(
    {
        L0Milestone.PROVIDER_EOT: _rule(
            "speech.capture_state",
            "speech.capture",
            "measurement.provider.eot",
            state="stopping",
        ),
        L0Milestone.BROWSER_EOT_RECEIPT: _rule(
            "speech.capture_state",
            "speech.capture",
            "measurement.browser.eot_receipt",
            state="stopping",
        ),
        L0Milestone.CAPTURE_STOPPED: _rule(
            "speech.capture_state",
            "speech.capture",
            "measurement.browser.capture_stopped",
            state="stopped",
        ),
        L0Milestone.LAST_FRAME_SENT: _rule(
            "segment.completed",
            "speech.capture",
            "measurement.browser.last_frame_sent",
            state="terminal",
            outcome="completed",
        ),
        L0Milestone.LAST_FRAME_ACKED: _rule(
            "segment.completed",
            "speech.capture",
            "measurement.gateway.last_frame_acked",
            state="terminal",
            outcome="completed",
        ),
        L0Milestone.UPLINK_CLOSED: _rule(
            "speech.capture_state",
            "speech.capture",
            "measurement.gateway.uplink_closed",
            state="stopped",
        ),
        L0Milestone.STT_FINAL_AVAILABLE: _rule(
            "segment.completed",
            "speech.recognition",
            "measurement.gateway.stt_final_available",
            state="terminal",
            outcome="completed",
        ),
        L0Milestone.COMMITTED_SUBMIT_ACCEPTED: _rule(
            "segment.completed",
            "runtime.turn",
            "measurement.runtime.committed_submit_accepted",
            state="terminal",
            outcome="completed",
        ),
        L0Milestone.AGENT_REQUEST_START: _rule(
            "segment.started",
            "agent.dispatch",
            "measurement.agent.request_start",
        ),
        L0Milestone.FIRST_DELTA: _rule(
            "segment.started",
            "agent.progress",
            "measurement.agent.first_delta",
        ),
        L0Milestone.FIRST_STABLE_SPEAKABLE_SENTENCE: _rule(
            "segment.completed",
            "agent.progress",
            "measurement.agent.first_stable_sentence",
            state="terminal",
            outcome="completed",
        ),
        L0Milestone.CHAT_FINAL: _rule(
            "segment.completed",
            "runtime.response",
            "measurement.agent.chat_final",
            state="terminal",
            outcome="completed",
        ),
        L0Milestone.TTS_REQUEST: _rule(
            "segment.started",
            "speech.synthesis",
            "measurement.gateway.tts_request",
        ),
        L0Milestone.PROVIDER_FIRST_AUDIO: _rule(
            "segment.started",
            "speech.playout",
            "measurement.provider.first_audio",
        ),
        L0Milestone.DOWNLINK_TICKET: _rule(
            "route.selected",
            "speech.playout",
            "measurement.gateway.downlink_ticket",
        ),
        L0Milestone.SUCCESSOR_CAPTURE_READY: _rule(
            "segment.started",
            "speech.capture",
            "measurement.browser.successor_capture_ready",
        ),
        L0Milestone.BROWSER_FIRST_FRAME: _rule(
            "segment.started",
            "speech.playout",
            "measurement.browser.first_frame",
        ),
        L0Milestone.WEBAUDIO_FIRST_FRAME_SCHEDULED: _rule(
            "speech.playout_state",
            "speech.playout",
            "measurement.browser.webaudio_scheduled",
            state="ready",
        ),
        L0Milestone.WEBAUDIO_ACTUALLY_STARTED: _rule(
            "speech.playout_state",
            "speech.playout",
            "measurement.browser.webaudio_started",
            state="playing",
        ),
        L0Milestone.PLAYOUT_COMPLETED: _rule(
            "segment.completed",
            "speech.playout",
            "measurement.browser.playout_completed",
            state="terminal",
            outcome="completed",
        ),
        L0Milestone.UNDERRUN: _rule(
            "degradation.activated",
            "system.degradation",
            "measurement.browser.underrun",
            reason_code="DEGRADED",
        ),
        L0Milestone.REBUFFER: _rule(
            "degradation.activated",
            "system.degradation",
            "measurement.browser.rebuffer",
            reason_code="DEGRADED",
        ),
        L0Milestone.FRAME_LOSS: _rule(
            "failure.observed",
            "speech.playout",
            "measurement.browser.frame_loss",
            reason_code="PROTOCOL_REJECTED",
            error_code="PROTOCOL_VIOLATION",
        ),
        L0Milestone.FALSE_EOT: _rule(
            "failure.observed",
            "speech.recognition",
            "measurement.provider.false_eot",
            reason_code="PROVIDER_FAILURE",
            error_code="PROTOCOL_VIOLATION",
        ),
        L0Milestone.MISSED_EOT: _rule(
            "failure.observed",
            "speech.recognition",
            "measurement.provider.missed_eot",
            reason_code="PROVIDER_FAILURE",
            error_code="TIMEOUT",
        ),
        L0Milestone.FAILURE: _rule(
            "failure.observed",
            "agent.dispatch",
            "measurement.agent.failure",
            reason_code="AGENT_FAILURE",
            error_code="INTERNAL",
        ),
        L0Milestone.BARGE_IN: _rule(
            "cancel.requested",
            "speech.playout",
            "measurement.browser.barge_in",
            reason_code="CANCEL_REQUESTED",
            cancel_scope="playback.stop",
        ),
        L0Milestone.FENCE_CANCEL_COMPLETION: _rule(
            "cancel.terminal",
            "speech.playout",
            "measurement.browser.fence_cancel_completion",
            outcome="cancelled",
            reason_code="CANCEL_TERMINAL",
            cancel_scope="playback.stop",
        ),
        L0Milestone.FALLBACK: _rule(
            "route.selected",
            "route.fallback",
            "measurement.runtime.fallback",
            reason_code="ROUTE_FALLBACK",
            route_class="fallback",
        ),
        L0Milestone.DISCARDED_WORK: _rule(
            "fence.stale_dropped",
            "runtime.presentation",
            "measurement.runtime.discarded_work",
            reason_code="STALE_GENERATION",
            error_code="STALE",
        ),
    }
)

_SOURCE_TO_MILESTONE: Final[Mapping[str, L0Milestone]] = MappingProxyType(
    {rule.source_component: milestone for milestone, rule in _MARKER_RULES.items()}
)

_QUALITY_MILESTONES: Final = frozenset(
    {
        L0Milestone.UNDERRUN,
        L0Milestone.REBUFFER,
        L0Milestone.FRAME_LOSS,
        L0Milestone.FALSE_EOT,
        L0Milestone.MISSED_EOT,
        L0Milestone.BARGE_IN,
        L0Milestone.FENCE_CANCEL_COMPLETION,
        L0Milestone.FALLBACK,
        L0Milestone.DISCARDED_WORK,
    }
)

_COMMON_SUCCESS_REQUIRED: Final = frozenset(
    {
        L0Milestone.PROVIDER_EOT,
        L0Milestone.BROWSER_EOT_RECEIPT,
        L0Milestone.CAPTURE_STOPPED,
        L0Milestone.LAST_FRAME_SENT,
        L0Milestone.LAST_FRAME_ACKED,
        L0Milestone.UPLINK_CLOSED,
        L0Milestone.STT_FINAL_AVAILABLE,
        L0Milestone.COMMITTED_SUBMIT_ACCEPTED,
        L0Milestone.TTS_REQUEST,
        L0Milestone.PROVIDER_FIRST_AUDIO,
        L0Milestone.DOWNLINK_TICKET,
        L0Milestone.SUCCESSOR_CAPTURE_READY,
        L0Milestone.BROWSER_FIRST_FRAME,
        L0Milestone.WEBAUDIO_FIRST_FRAME_SCHEDULED,
        L0Milestone.WEBAUDIO_ACTUALLY_STARTED,
        L0Milestone.PLAYOUT_COMPLETED,
    }
)
_AGENT_SUCCESS_REQUIRED: Final = frozenset(
    {L0Milestone.AGENT_REQUEST_START, L0Milestone.CHAT_FINAL}
)
_SUCCESS_ROUTES: Final = frozenset({"dialogue", "tool", "task", "none"})

_SPAN_DEFINITIONS: Final[Mapping[str, tuple[L0Milestone, L0Milestone]]] = (
    MappingProxyType(
        {
            "speech_end_to_stt_final_ms": (
                L0Milestone.PROVIDER_EOT,
                L0Milestone.STT_FINAL_AVAILABLE,
            ),
            "speech_end_to_committed_submit_ms": (
                L0Milestone.PROVIDER_EOT,
                L0Milestone.COMMITTED_SUBMIT_ACCEPTED,
            ),
            "agent_request_to_first_delta_ms": (
                L0Milestone.AGENT_REQUEST_START,
                L0Milestone.FIRST_DELTA,
            ),
            "agent_request_to_first_stable_sentence_ms": (
                L0Milestone.AGENT_REQUEST_START,
                L0Milestone.FIRST_STABLE_SPEAKABLE_SENTENCE,
            ),
            "agent_request_to_chat_final_ms": (
                L0Milestone.AGENT_REQUEST_START,
                L0Milestone.CHAT_FINAL,
            ),
            "tts_request_to_provider_first_audio_ms": (
                L0Milestone.TTS_REQUEST,
                L0Milestone.PROVIDER_FIRST_AUDIO,
            ),
            "speech_end_to_webaudio_started_ms": (
                L0Milestone.PROVIDER_EOT,
                L0Milestone.WEBAUDIO_ACTUALLY_STARTED,
            ),
            "complete_round_ms": (
                L0Milestone.PROVIDER_EOT,
                L0Milestone.PLAYOUT_COMPLETED,
            ),
            "stop_to_silence_ms": (
                L0Milestone.BARGE_IN,
                L0Milestone.FENCE_CANCEL_COMPLETION,
            ),
        }
    )
)


def _violation(reason: str, message: str) -> L0MeasurementViolation:
    return L0MeasurementViolation(reason, message)


def _safe_identity(value: object, field_name: str) -> str:
    if type(value) is not str or not _SAFE_TOKEN.fullmatch(value):
        raise _violation("INVALID_IDENTITY", f"{field_name} is not a safe identity")
    if contains_private_observability_content(value):
        raise _violation("PRIVATE_CONTENT", f"{field_name} contains private content")
    return value


def _optional_identity(value: object, field_name: str) -> str | None:
    return None if value is None else _safe_identity(value, field_name)


def _safe_profile_token(value: object, field_name: str) -> str:
    if type(value) is not str or not _PROFILE_TOKEN.fullmatch(value):
        raise _violation("INVALID_PROFILE", f"{field_name} is not canonical")
    if contains_private_observability_content(value):
        raise _violation("PRIVATE_CONTENT", f"{field_name} contains private content")
    return value


def _safe_uint(value: object, field_name: str, *, positive: bool = False) -> int:
    if (
        type(value) is not int
        or value < int(positive)
        or value > L0_MAX_SAFE_INTEGER
    ):
        raise _violation("INVALID_INTEGER", f"{field_name} is outside the safe range")
    return value


def _safe_number(value: object, field_name: str) -> float:
    if type(value) not in {int, float}:
        raise _violation("INVALID_NUMBER", f"{field_name} must be numeric")
    exact = float(value)
    if not math.isfinite(exact) or exact < 0:
        raise _violation("INVALID_NUMBER", f"{field_name} must be finite and nonnegative")
    return exact


def _utc_timestamp(value: object, field_name: str) -> str:
    if type(value) is not str or not _TIMESTAMP.fullmatch(value):
        raise _violation("INVALID_TIMESTAMP", f"{field_name} must be UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise _violation("INVALID_TIMESTAMP", f"{field_name} is invalid") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise _violation("INVALID_TIMESTAMP", f"{field_name} must be UTC")
    return value


def _timestamp_ms(value: str) -> float:
    return datetime.fromisoformat(value[:-1] + "+00:00").timestamp() * 1000.0


def _closed_mapping(
    value: object,
    *,
    field_name: str,
    allowed: frozenset[str],
    required: frozenset[str],
) -> dict[str, object]:
    if type(value) is not dict:
        raise _violation("INVALID_SHAPE", f"{field_name} must be a plain mapping")
    raw = dict(value)
    if not required.issubset(raw) or set(raw) - allowed:
        raise _violation("INVALID_SHAPE", f"{field_name} has an invalid closed shape")
    return raw


@dataclass(frozen=True, slots=True)
class L0RoundBinding:
    correlation_id: str
    session_id: str
    interaction_id: str
    activation_generation: int
    response_id: str | None = None
    response_generation: int | None = None
    turn_id: str | None = None
    round_id: str | None = None
    task_id: str | None = None
    attempt_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("correlation_id", "session_id", "interaction_id"):
            _safe_identity(getattr(self, field_name), field_name)
        _safe_uint(
            self.activation_generation,
            "activation_generation",
            positive=True,
        )
        for field_name in (
            "response_id",
            "turn_id",
            "round_id",
            "task_id",
            "attempt_id",
        ):
            _optional_identity(getattr(self, field_name), field_name)
        if (self.response_id is None) != (self.response_generation is None):
            raise _violation(
                "INCOMPLETE_RESPONSE_IDENTITY",
                "response identity and generation must be present together",
            )
        if self.response_generation is not None:
            _safe_uint(self.response_generation, "response_generation")
        if self.attempt_id is not None and self.task_id is None:
            raise _violation(
                "INCOMPLETE_TASK_IDENTITY",
                "attempt identity requires Task identity",
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "correlation_id": self.correlation_id,
            "session_id": self.session_id,
            "interaction_id": self.interaction_id,
            "activation_generation": self.activation_generation,
            "response_id": self.response_id,
            "response_generation": self.response_generation,
            "turn_id": self.turn_id,
            "round_id": self.round_id,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
        }

    def trace_binding(self) -> dict[str, object]:
        return {
            "correlation_id": self.correlation_id,
            "interaction_id": self.interaction_id,
            "turn_id": self.turn_id,
            "response_id": self.response_id,
            "response_generation": self.response_generation,
            "round_id": self.round_id,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
        }


_BINDING_KEYS = frozenset(L0RoundBinding.__dataclass_fields__)


def create_l0_round_binding(value: L0RoundBinding | object) -> L0RoundBinding:
    if isinstance(value, L0RoundBinding):
        return L0RoundBinding(**value.to_dict())  # type: ignore[arg-type]
    data = _closed_mapping(
        value,
        field_name="binding",
        allowed=_BINDING_KEYS,
        required=frozenset(
            {
                "correlation_id",
                "session_id",
                "interaction_id",
                "activation_generation",
            }
        ),
    )
    return L0RoundBinding(**data)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class L0MeasurementEnvelope:
    schema_version: str
    milestone: L0Milestone
    binding: L0RoundBinding
    observation: LiveVoiceObservation
    profile_id: str
    scenario_id: str
    sample_index: int
    temperature: L0RoundTemperature
    classification: L0RoundClassification
    evidence_source: L0EvidenceSource

    def __post_init__(self) -> None:
        if self.schema_version != L0_MEASUREMENT_ENVELOPE_VERSION:
            raise _violation("SCHEMA_MISMATCH", "measurement envelope version is invalid")
        if type(self.milestone) is not L0Milestone:
            raise _violation("INVALID_MILESTONE", "milestone is invalid")
        if type(self.binding) is not L0RoundBinding:
            raise _violation("INVALID_BINDING", "round binding is invalid")
        if type(self.observation) is not LiveVoiceObservation:
            raise _violation("INVALID_OBSERVATION", "production observation is required")
        _safe_profile_token(self.profile_id, "profile_id")
        _safe_profile_token(self.scenario_id, "scenario_id")
        _safe_uint(self.sample_index, "sample_index")
        if type(self.temperature) is not L0RoundTemperature:
            raise _violation("INVALID_TEMPERATURE", "temperature is invalid")
        if type(self.classification) is not L0RoundClassification:
            raise _violation("INVALID_CLASSIFICATION", "classification is invalid")
        if type(self.evidence_source) is not L0EvidenceSource:
            raise _violation("INVALID_EVIDENCE_SOURCE", "evidence source is invalid")
        rule = _MARKER_RULES[self.milestone]
        if (
            self.observation.source_component != rule.source_component
            or self.observation.event_name != rule.event_name
            or self.observation.segment_name != rule.segment_name
            or self.observation.binding.correlation_id != self.binding.correlation_id
            or self.observation.binding.interaction_id != self.binding.interaction_id
            or self.observation.binding.response_id != self.binding.response_id
            or self.observation.binding.response_generation
            != self.binding.response_generation
            or self.observation.binding.round_id != self.binding.round_id
            or self.observation.binding.task_id != self.binding.task_id
            or self.observation.binding.attempt_id != self.binding.attempt_id
        ):
            raise _violation(
                "OBSERVATION_BINDING_MISMATCH",
                "measurement wrapper does not match its production observation",
            )
        if contains_private_observability_content(self.to_dict()):
            raise _violation("PRIVATE_CONTENT", "measurement contains private content")

    @property
    def round_key(self) -> tuple[str, str, int]:
        return (self.profile_id, self.scenario_id, self.sample_index)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "milestone": self.milestone.value,
            "binding": self.binding.to_dict(),
            "observation": self.observation.to_dict(),
            "profile_id": self.profile_id,
            "scenario_id": self.scenario_id,
            "sample_index": self.sample_index,
            "temperature": self.temperature.value,
            "classification": self.classification.value,
            "evidence_source": self.evidence_source.value,
        }


_ENVELOPE_KEYS = frozenset(L0MeasurementEnvelope.__dataclass_fields__)


def create_l0_measurement_envelope(
    value: L0MeasurementEnvelope | object,
) -> L0MeasurementEnvelope:
    if isinstance(value, L0MeasurementEnvelope):
        value = value.to_dict()
    data = _closed_mapping(
        value,
        field_name="measurement_envelope",
        allowed=_ENVELOPE_KEYS,
        required=_ENVELOPE_KEYS,
    )
    try:
        data["milestone"] = L0Milestone(data["milestone"])
        data["binding"] = create_l0_round_binding(data["binding"])
        data["observation"] = create_observation(data["observation"])
        data["temperature"] = L0RoundTemperature(data["temperature"])
        data["classification"] = L0RoundClassification(data["classification"])
        data["evidence_source"] = L0EvidenceSource(data["evidence_source"])
    except (TypeError, ValueError) as error:
        if isinstance(error, L0MeasurementViolation):
            raise
        raise _violation("INVALID_ENUM", "measurement enum value is invalid") from error
    return L0MeasurementEnvelope(**data)  # type: ignore[arg-type]


def _default_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def create_l0_milestone(
    *,
    milestone: L0Milestone,
    binding: L0RoundBinding,
    profile_id: str,
    scenario_id: str,
    sample_index: int,
    temperature: L0RoundTemperature,
    classification: L0RoundClassification = L0RoundClassification.UNKNOWN,
    evidence_source: L0EvidenceSource,
    observed_at: str | None = None,
    monotonic_ms: float | None = None,
    duration_ms: float | None = None,
    event_nonce: str | None = None,
) -> L0MeasurementEnvelope:
    """Create one run envelope through the production observation validator."""

    if type(milestone) is not L0Milestone:
        raise _violation("INVALID_MILESTONE", "milestone must use the closed vocabulary")
    exact_binding = create_l0_round_binding(binding)
    timestamp = _utc_timestamp(observed_at or _default_timestamp(), "observed_at")
    monotonic = _safe_number(
        time.monotonic() * 1000.0 if monotonic_ms is None else monotonic_ms,
        "monotonic_ms",
    )
    rule = _MARKER_RULES[milestone]
    route = {
        "implementation_class": rule.route_class,
        "owner_module": rule.source_component,
        "capability_provider": "jiuwenswarm-runtime",
        "contract_version": (
            LIVE_VOICE_CONTRACT_VERSION if rule.route_class == "formal" else None
        ),
        "reason_code": rule.reason_code if rule.route_class != "formal" else None,
    }
    canonical_identity = {
        "milestone": milestone.value,
        "binding": exact_binding.to_dict(),
        "profile_id": profile_id,
        "scenario_id": scenario_id,
        "sample_index": sample_index,
        "observed_at": timestamp,
        "nonce": event_nonce,
    }
    event_id = "l0-" + hashlib.sha256(
        json.dumps(
            canonical_identity,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    payload: dict[str, object] = {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "event_id": event_id,
        "event_name": rule.event_name,
        "segment_name": rule.segment_name,
        "observed_at": timestamp,
        "monotonic_ms": monotonic,
        "binding": exact_binding.trace_binding(),
        "route": route,
        "source_component": rule.source_component,
        "state": rule.state,
        "outcome": rule.outcome,
        "reason_code": rule.reason_code,
        "error_code": rule.error_code,
        "cancel_scope": rule.cancel_scope,
    }
    if rule.event_name == "segment.completed":
        if duration_ms is None:
            raise _violation(
                "UNKNOWN_DURATION",
                "a completed production segment requires a measured duration",
            )
        payload["duration_ms"] = _safe_number(duration_ms, "duration_ms")
    observation = create_observation(payload)
    return L0MeasurementEnvelope(
        schema_version=L0_MEASUREMENT_ENVELOPE_VERSION,
        milestone=milestone,
        binding=exact_binding,
        observation=observation,
        profile_id=_safe_profile_token(profile_id, "profile_id"),
        scenario_id=_safe_profile_token(scenario_id, "scenario_id"),
        sample_index=_safe_uint(sample_index, "sample_index"),
        temperature=temperature,
        classification=classification,
        evidence_source=evidence_source,
    )


@dataclass(frozen=True, slots=True)
class L0RoundDeclaration:
    binding: L0RoundBinding
    profile_id: str
    scenario_id: str
    sample_index: int
    temperature: L0RoundTemperature
    evidence_source: L0EvidenceSource

    def __post_init__(self) -> None:
        if type(self.binding) is not L0RoundBinding:
            raise _violation("INVALID_BINDING", "round declaration binding is invalid")
        _safe_profile_token(self.profile_id, "profile_id")
        _safe_profile_token(self.scenario_id, "scenario_id")
        _safe_uint(self.sample_index, "sample_index")
        if type(self.temperature) is not L0RoundTemperature:
            raise _violation("INVALID_TEMPERATURE", "temperature is invalid")
        if type(self.evidence_source) is not L0EvidenceSource:
            raise _violation("INVALID_EVIDENCE_SOURCE", "evidence source is invalid")

    @property
    def round_key(self) -> tuple[str, str, int]:
        return (self.profile_id, self.scenario_id, self.sample_index)


def _binding_is_compatible(
    expected: L0RoundBinding,
    observed: L0RoundBinding,
) -> bool:
    if (
        expected.correlation_id != observed.correlation_id
        or expected.session_id != observed.session_id
        or expected.interaction_id != observed.interaction_id
        or expected.activation_generation != observed.activation_generation
    ):
        return False
    for field_name in (
        "response_id",
        "response_generation",
        "turn_id",
        "round_id",
        "task_id",
        "attempt_id",
    ):
        expected_value = getattr(expected, field_name)
        observed_value = getattr(observed, field_name)
        if (
            expected_value is not None
            and observed_value is not None
            and expected_value != observed_value
        ):
            return False
    return True


def _merge_binding(left: L0RoundBinding, right: L0RoundBinding) -> L0RoundBinding:
    if not _binding_is_compatible(left, right):
        raise _violation(
            "ROUND_DECLARATION_CONFLICT",
            "input sample key contains mixed identity scope",
        )
    values = left.to_dict()
    for field_name, value in right.to_dict().items():
        if values[field_name] is None and value is not None:
            values[field_name] = value
    return create_l0_round_binding(values)


def _binding_matches_declaration(
    expected: L0RoundBinding,
    observed: L0RoundBinding,
) -> bool:
    if not _binding_is_compatible(expected, observed):
        return False
    # Task and attempt are separate mutation authority. A non-Task round cannot
    # be widened into one merely because a later record reused its sample key.
    return all(
        getattr(expected, field_name) == getattr(observed, field_name)
        for field_name in ("task_id", "attempt_id")
    )


@dataclass(frozen=True, slots=True)
class L0CollectorStats:
    declared_rounds: int
    accepted_records: int
    idempotent_records: int
    isolated_records: int
    conflicting_records: int
    capacity_rejections: int


class L0MeasurementCollector:
    """Exact run registry and isolation gate for local measurement envelopes."""

    def __init__(self, *, max_rounds: int = L0_MAX_ROUNDS, max_records: int = L0_MAX_RECORDS) -> None:
        _safe_uint(max_rounds, "max_rounds", positive=True)
        _safe_uint(max_records, "max_records", positive=True)
        self._max_rounds = max_rounds
        self._max_records = max_records
        self._declarations: dict[tuple[str, str, int], L0RoundDeclaration] = {}
        self._records: list[L0MeasurementEnvelope] = []
        self._record_by_id: dict[str, L0MeasurementEnvelope] = {}
        self._accepted = 0
        self._idempotent = 0
        self._isolated = 0
        self._conflicting = 0
        self._capacity_rejections = 0
        self._lock = Lock()

    def register_round(self, declaration: L0RoundDeclaration) -> bool:
        if type(declaration) is not L0RoundDeclaration:
            raise _violation("INVALID_DECLARATION", "round declaration is invalid")
        key = declaration.round_key
        with self._lock:
            prior = self._declarations.get(key)
            if prior is not None:
                if prior == declaration:
                    return False
                raise _violation(
                    "ROUND_DECLARATION_CONFLICT",
                    "one sample key cannot change its exact identity",
                )
            if len(self._declarations) >= self._max_rounds:
                self._capacity_rejections += 1
                return False
            self._declarations[key] = declaration
        return True

    def consume(self, value: L0MeasurementEnvelope | object) -> bool:
        try:
            envelope = create_l0_measurement_envelope(value)
        except Exception:
            with self._lock:
                self._isolated += 1
            return False
        with self._lock:
            declaration = self._declarations.get(envelope.round_key)
            if (
                declaration is None
                or not _binding_matches_declaration(
                    declaration.binding,
                    envelope.binding,
                )
                or declaration.temperature is not envelope.temperature
                or declaration.evidence_source is not envelope.evidence_source
            ):
                self._isolated += 1
                return False
            # Early Provider/browser facts legitimately precede response, turn,
            # and round allocation.  Pin the declaration to the first later
            # exact identity so a second response can never reuse the sample
            # key through ``None`` compatibility.
            merged_binding = _merge_binding(declaration.binding, envelope.binding)
            if merged_binding != declaration.binding:
                declaration = L0RoundDeclaration(
                    binding=merged_binding,
                    profile_id=declaration.profile_id,
                    scenario_id=declaration.scenario_id,
                    sample_index=declaration.sample_index,
                    temperature=declaration.temperature,
                    evidence_source=declaration.evidence_source,
                )
                self._declarations[envelope.round_key] = declaration
            event_id = envelope.observation.event_id
            prior = self._record_by_id.get(event_id)
            if prior is not None:
                if prior == envelope:
                    self._idempotent += 1
                    return True
                self._conflicting += 1
                return False
            if len(self._records) >= self._max_records:
                self._capacity_rejections += 1
                return False
            self._record_by_id[event_id] = envelope
            self._records.append(envelope)
            self._accepted += 1
        return True

    def records(self) -> tuple[L0MeasurementEnvelope, ...]:
        with self._lock:
            return tuple(self._records)

    def declarations(self) -> tuple[L0RoundDeclaration, ...]:
        with self._lock:
            return tuple(self._declarations.values())

    def stats(self) -> L0CollectorStats:
        with self._lock:
            return L0CollectorStats(
                declared_rounds=len(self._declarations),
                accepted_records=self._accepted,
                idempotent_records=self._idempotent,
                isolated_records=self._isolated,
                conflicting_records=self._conflicting,
                capacity_rejections=self._capacity_rejections,
            )


def _nearest_rank(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return round(ordered[index], 3)


def _classification_for(records: Sequence[L0MeasurementEnvelope]) -> L0RoundClassification:
    classifications = {
        record.classification
        for record in records
        if record.classification is not L0RoundClassification.UNKNOWN
    }
    if len(classifications) > 1:
        return L0RoundClassification.FAILURE
    if classifications:
        return next(iter(classifications))
    milestones = {record.milestone for record in records}
    if L0Milestone.FALLBACK in milestones:
        return L0RoundClassification.FALLBACK
    if L0Milestone.FAILURE in milestones:
        return L0RoundClassification.FAILURE
    if L0Milestone.FENCE_CANCEL_COMPLETION in milestones:
        return L0RoundClassification.CANCELLED
    return L0RoundClassification.UNKNOWN


def _round_summary(
    declaration: L0RoundDeclaration,
    records: Sequence[L0MeasurementEnvelope],
    *,
    expected_route: str,
) -> dict[str, object]:
    ordered = sorted(
        records,
        key=lambda item: (
            _timestamp_ms(item.observation.observed_at),
            item.observation.event_id,
        ),
    )
    milestone_times: dict[L0Milestone, float] = {}
    duplicate_milestones: set[str] = set()
    quality = Counter[str]()
    for record in ordered:
        milestone = record.milestone
        if milestone in _QUALITY_MILESTONES:
            quality[milestone.value] += 1
        if milestone in milestone_times:
            if milestone not in _QUALITY_MILESTONES:
                duplicate_milestones.add(milestone.value)
            continue
        milestone_times[milestone] = _timestamp_ms(record.observation.observed_at)
    classification = _classification_for(ordered)
    required = _COMMON_SUCCESS_REQUIRED
    if expected_route != "task":
        required = required | _AGENT_SUCCESS_REQUIRED
    missing = sorted(item.value for item in required - milestone_times.keys())
    success_eligible = (
        classification is L0RoundClassification.SUCCESS
        and not missing
        and not duplicate_milestones
    )
    spans: dict[str, float | None] = {}
    invalid_order: list[str] = []
    for span_name, (start, end) in _SPAN_DEFINITIONS.items():
        start_value = milestone_times.get(start)
        end_value = milestone_times.get(end)
        if start_value is None or end_value is None:
            spans[span_name] = None
            continue
        elapsed = end_value - start_value
        if elapsed < 0:
            spans[span_name] = None
            invalid_order.append(span_name)
            continue
        spans[span_name] = round(elapsed, 3)
    if invalid_order:
        success_eligible = False
    return {
        "profile_id": declaration.profile_id,
        "scenario_id": declaration.scenario_id,
        "sample_index": declaration.sample_index,
        "temperature": declaration.temperature.value,
        "evidence_source": declaration.evidence_source.value,
        "expected_route": expected_route,
        "classification": classification.value,
        "success_eligible": success_eligible,
        "milestone_count": len(milestone_times),
        "missing_required_milestones": missing,
        "duplicate_milestones": sorted(duplicate_milestones),
        "invalid_order_spans": invalid_order,
        "spans_ms": spans,
        "quality_counts": dict(sorted(quality.items())),
    }


def build_l0_measurement_report(
    collector: L0MeasurementCollector,
    *,
    source_head: str,
    environment_ref: str,
    corpus_sha256: str,
    scenario_routes: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Aggregate exact accepted samples; non-success never enters percentiles."""

    if type(collector) is not L0MeasurementCollector:
        raise _violation("INVALID_COLLECTOR", "measurement collector is invalid")
    if type(source_head) is not str or not re.fullmatch(r"[0-9a-f]{40}", source_head):
        raise _violation("INVALID_SOURCE", "source_head must be an exact Git SHA")
    environment = _safe_profile_token(environment_ref, "environment_ref")
    if type(corpus_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", corpus_sha256):
        raise _violation("INVALID_CORPUS", "corpus_sha256 is invalid")
    routes: dict[str, str] = {}
    if scenario_routes is not None:
        if not isinstance(scenario_routes, Mapping):
            raise _violation("INVALID_CORPUS", "scenario routes are invalid")
        for scenario_id, route in scenario_routes.items():
            checked_scenario = _safe_profile_token(scenario_id, "scenario_id")
            if type(route) is not str or route not in _SUCCESS_ROUTES:
                raise _violation("INVALID_CORPUS", "scenario route is invalid")
            routes[checked_scenario] = route
    by_round: dict[tuple[str, str, int], list[L0MeasurementEnvelope]] = defaultdict(list)
    for record in collector.records():
        by_round[record.round_key].append(record)
    declarations = collector.declarations()
    if routes:
        missing_routes = sorted(
            {item.scenario_id for item in declarations} - routes.keys()
        )
        if missing_routes:
            raise _violation("INVALID_CORPUS", "scenario route is missing")
    summaries = [
        _round_summary(
            declaration,
            by_round.get(declaration.round_key, ()),
            expected_route=(
                routes.get(declaration.scenario_id, "dialogue")
                if not routes
                else routes[declaration.scenario_id]
            ),
        )
        for declaration in sorted(
            declarations,
            key=lambda item: item.round_key,
        )
    ]
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for summary in summaries:
        grouped[(str(summary["profile_id"]), str(summary["temperature"]))].append(summary)
    profile_groups: list[dict[str, object]] = []
    for (profile_id, temperature), rounds in sorted(grouped.items()):
        classifications = Counter(str(item["classification"]) for item in rounds)
        eligible = [item for item in rounds if item["success_eligible"] is True]
        percentiles: dict[str, dict[str, object]] = {}
        for span_name in _SPAN_DEFINITIONS:
            values = [
                float(item["spans_ms"][span_name])  # type: ignore[index]
                for item in eligible
                if item["spans_ms"][span_name] is not None  # type: ignore[index]
            ]
            percentiles[span_name] = {
                "sample_count": len(values),
                "p50_ms": _nearest_rank(values, 0.50),
                "p95_ms": _nearest_rank(values, 0.95),
            }
        quality = Counter[str]()
        for item in rounds:
            quality.update(item["quality_counts"])  # type: ignore[arg-type]
        profile_groups.append(
            {
                "profile_id": profile_id,
                "temperature": temperature,
                "round_count": len(rounds),
                "success_count": classifications[L0RoundClassification.SUCCESS.value],
                "success_eligible_count": len(eligible),
                "failure_count": classifications[L0RoundClassification.FAILURE.value],
                "fallback_count": classifications[L0RoundClassification.FALLBACK.value],
                "cancelled_count": classifications[L0RoundClassification.CANCELLED.value],
                "unknown_count": classifications[L0RoundClassification.UNKNOWN.value],
                "quality_counts": dict(sorted(quality.items())),
                "percentiles": percentiles,
            }
        )
    stats = collector.stats()
    report = {
        "schema_version": L0_MEASUREMENT_REPORT_VERSION,
        "source_head": source_head,
        "environment_ref": environment,
        "corpus_sha256": corpus_sha256,
        "collector": {
            "declared_rounds": stats.declared_rounds,
            "accepted_records": stats.accepted_records,
            "idempotent_records": stats.idempotent_records,
            "isolated_records": stats.isolated_records,
            "conflicting_records": stats.conflicting_records,
            "capacity_rejections": stats.capacity_rejections,
        },
        "profiles": profile_groups,
        "rounds": summaries,
        "non_claims": [
            "injected/prerecorded/digital-loopback evidence is not physical microphone/speaker evidence",
            "WebAudio scheduling or source-stop confirmation is not proof of physical audibility or silence",
            "missing milestones and unavailable stable-sentence facts remain unknown",
            "failed/fallback/cancelled/identity-isolated rounds are excluded from success percentiles",
        ],
    }
    if contains_private_observability_content(report):
        raise _violation("PRIVATE_CONTENT", "measurement report contains private content")
    return report


def canonical_json_bytes(value: object) -> bytes:
    if contains_private_observability_content(value):
        raise _violation("PRIVATE_CONTENT", "canonical measurement contains private content")
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def corpus_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def validate_l0_corpus_manifest(value: object) -> dict[str, object]:
    """Validate the committed fixed-corpus manifest without accepting extensions."""

    data = _closed_mapping(
        value,
        field_name="corpus_manifest",
        allowed=frozenset(
            {
                "schema_version",
                "corpus_id",
                "description",
                "profiles",
                "cases",
                "non_claims",
            }
        ),
        required=frozenset(
            {
                "schema_version",
                "corpus_id",
                "description",
                "profiles",
                "cases",
                "non_claims",
            }
        ),
    )
    if data["schema_version"] != L0_CORPUS_MANIFEST_VERSION:
        raise _violation("SCHEMA_MISMATCH", "corpus manifest version is invalid")
    _safe_profile_token(data["corpus_id"], "corpus_id")
    if type(data["description"]) is not str or not data["description"]:
        raise _violation("INVALID_CORPUS", "corpus description is required")
    profiles = data["profiles"]
    cases = data["cases"]
    non_claims = data["non_claims"]
    if type(profiles) is not list or not profiles:
        raise _violation("INVALID_CORPUS", "corpus profiles are required")
    if type(cases) is not list or not cases:
        raise _violation("INVALID_CORPUS", "corpus cases are required")
    if type(non_claims) is not list or not all(
        type(item) is str and item for item in non_claims
    ):
        raise _violation("INVALID_CORPUS", "corpus non-claims are required")
    profile_ids: set[str] = set()
    profile_sources: set[L0EvidenceSource] = set()
    for raw in profiles:
        profile = _closed_mapping(
            raw,
            field_name="corpus_profile",
            allowed=frozenset(
                {
                    "profile_id",
                    "evidence_source",
                    "network_profile_ref",
                    "minimum_successful_rounds",
                    "temperature_policy",
                    "physical_required",
                }
            ),
            required=frozenset(
                {
                    "profile_id",
                    "evidence_source",
                    "network_profile_ref",
                    "minimum_successful_rounds",
                    "temperature_policy",
                    "physical_required",
                }
            ),
        )
        profile_id = _safe_profile_token(profile["profile_id"], "profile_id")
        if profile_id in profile_ids:
            raise _violation("DUPLICATE_PROFILE", "corpus profile is duplicated")
        profile_ids.add(profile_id)
        try:
            profile_sources.add(L0EvidenceSource(profile["evidence_source"]))
            L0RoundTemperature(profile["temperature_policy"])
        except (TypeError, ValueError) as error:
            raise _violation("INVALID_PROFILE", "corpus profile enum is invalid") from error
        _safe_profile_token(profile["network_profile_ref"], "network_profile_ref")
        minimum = _safe_uint(
            profile["minimum_successful_rounds"],
            "minimum_successful_rounds",
            positive=True,
        )
        if minimum < 20:
            raise _violation("INVALID_PROFILE", "formal profiles require at least 20 successes")
        if type(profile["physical_required"]) is not bool:
            raise _violation("INVALID_PROFILE", "physical_required must be boolean")
    case_ids: set[str] = set()
    categories: set[str] = set()
    required_categories = {
        "short_no_tool",
        "long_answer",
        "real_tool",
        "task_create",
        "task_status",
        "task_cancel",
        "chinese_breath_pause",
        "barge_in",
        "silence",
        "mid_pause_truncation",
        "provider_slow",
        "provider_failure",
        "degraded_network",
    }
    for raw in cases:
        case = _closed_mapping(
            raw,
            field_name="corpus_case",
            allowed=frozenset(
                {
                    "case_id",
                    "category",
                    "locale",
                    "input_mode",
                    "fixture_ref",
                    "stimulus_text",
                    "action_sequence",
                    "expected_route",
                    "expected_classification",
                    "requires_physical_audio",
                    "requires_registered_disposable_project",
                }
            ),
            required=frozenset(
                {
                    "case_id",
                    "category",
                    "locale",
                    "input_mode",
                    "fixture_ref",
                    "stimulus_text",
                    "action_sequence",
                    "expected_route",
                    "expected_classification",
                    "requires_physical_audio",
                    "requires_registered_disposable_project",
                }
            ),
        )
        case_id = _safe_profile_token(case["case_id"], "case_id")
        category = _safe_profile_token(case["category"], "category")
        if case_id in case_ids:
            raise _violation("DUPLICATE_CASE", "corpus case is duplicated")
        case_ids.add(case_id)
        categories.add(category)
        if case["locale"] not in {"zh-CN", "en-US", "none"}:
            raise _violation("INVALID_CASE", "case locale is invalid")
        if case["input_mode"] not in {
            "prerecorded",
            "injected",
            "physical_voice",
            "control",
        }:
            raise _violation("INVALID_CASE", "case input mode is invalid")
        _safe_profile_token(case["fixture_ref"], "fixture_ref")
        stimulus_text = case["stimulus_text"]
        if (
            type(stimulus_text) is not str
            or len(stimulus_text.encode("utf-8")) > 1_024
            or contains_private_observability_content(stimulus_text)
        ):
            raise _violation("INVALID_CASE", "case stimulus text is invalid")
        action_sequence = case["action_sequence"]
        if type(action_sequence) is not list or not all(
            type(item) is str and _PROFILE_TOKEN.fullmatch(item)
            for item in action_sequence
        ):
            raise _violation("INVALID_CASE", "case action sequence is invalid")
        if case["expected_route"] not in {"dialogue", "tool", "task", "none"}:
            raise _violation("INVALID_CASE", "case route is invalid")
        try:
            L0RoundClassification(case["expected_classification"])
        except (TypeError, ValueError) as error:
            raise _violation("INVALID_CASE", "case classification is invalid") from error
        if type(case["requires_physical_audio"]) is not bool or type(
            case["requires_registered_disposable_project"]
        ) is not bool:
            raise _violation("INVALID_CASE", "case requirement flags are invalid")
    if not required_categories.issubset(categories):
        raise _violation("INCOMPLETE_CORPUS", "corpus is missing required categories")
    if contains_private_observability_content(data):
        raise _violation("PRIVATE_CONTENT", "corpus manifest contains private content")
    return data


def load_l0_corpus_manifest(path: Path) -> tuple[dict[str, object], str]:
    if not isinstance(path, Path) or not path.is_file():
        raise _violation("CORPUS_NOT_FOUND", "corpus manifest is unavailable")
    if path.stat().st_size > L0_MAX_FILE_BYTES:
        raise _violation("CORPUS_TOO_LARGE", "corpus manifest is too large")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _violation("INVALID_CORPUS", "corpus manifest cannot be read") from error
    checked = validate_l0_corpus_manifest(raw)
    return checked, corpus_sha256(checked)


def load_l0_jsonl(paths: Sequence[Path]) -> tuple[L0MeasurementEnvelope, ...]:
    records: list[L0MeasurementEnvelope] = []
    for path in paths:
        if not isinstance(path, Path) or not path.is_file():
            raise _violation("INPUT_NOT_FOUND", "measurement input is unavailable")
        if path.stat().st_size > L0_MAX_FILE_BYTES:
            raise _violation("INPUT_TOO_LARGE", "measurement input is too large")
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    if len(records) >= L0_MAX_RECORDS:
                        raise _violation("INPUT_TOO_LARGE", "too many measurement records")
                    try:
                        records.append(
                            create_l0_measurement_envelope(json.loads(line))
                        )
                    except (json.JSONDecodeError, ValueError) as error:
                        raise _violation(
                            "INVALID_INPUT",
                            f"measurement input line {line_number} is invalid",
                        ) from error
        except OSError as error:
            raise _violation("INPUT_UNAVAILABLE", "measurement input cannot be read") from error
    return tuple(records)


class L0ProcessJsonlSink:
    """Opt-in, content-free, one-write-per-record process-local JSONL sink."""

    def __init__(self, directory: Path, *, component: str) -> None:
        if not isinstance(directory, Path):
            raise _violation("INVALID_DIRECTORY", "measurement directory is invalid")
        component_token = _safe_profile_token(component, "component")
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.is_dir():
            raise _violation("INVALID_DIRECTORY", "measurement directory is unavailable")
        self._path = directory / f"l0-{component_token}-{os.getpid()}.jsonl"
        self._lock = Lock()

    @property
    def path(self) -> Path:
        return self._path

    def emit(self, envelope: L0MeasurementEnvelope) -> bool:
        checked = create_l0_measurement_envelope(envelope)
        encoded = canonical_json_bytes(checked.to_dict()) + b"\n"
        if len(encoded) > 16_384:
            return False
        try:
            with self._lock:
                descriptor = os.open(
                    self._path,
                    os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0),
                    0o600,
                )
                try:
                    written = os.write(descriptor, encoded)
                finally:
                    os.close(descriptor)
            return written == len(encoded)
        except OSError:
            return False


_PROCESS_SINKS: dict[str, L0ProcessJsonlSink | None] = {}
_PROCESS_SINKS_LOCK = Lock()


def process_l0_sink(component: str) -> L0ProcessJsonlSink | None:
    """Return the opt-in sink without reading any business or credential state."""

    component_token = _safe_profile_token(component, "component")
    with _PROCESS_SINKS_LOCK:
        if component_token in _PROCESS_SINKS:
            return _PROCESS_SINKS[component_token]
        raw = os.getenv(L0_MEASUREMENT_DIRECTORY_ENV)
        if not isinstance(raw, str) or not raw.strip():
            _PROCESS_SINKS[component_token] = None
            return None
        try:
            sink = L0ProcessJsonlSink(Path(raw).resolve(), component=component_token)
        except Exception:
            sink = None
        _PROCESS_SINKS[component_token] = sink
        return sink


def runtime_l0_run_labels() -> (
    tuple[str, str, int, L0RoundTemperature, L0EvidenceSource] | None
):
    """Read only non-secret, controlled-run labels from the process environment."""

    run_labels_path = os.getenv(L0_MEASUREMENT_RUN_LABELS_FILE_ENV)
    if isinstance(run_labels_path, str) and run_labels_path.strip():
        try:
            path = Path(run_labels_path).resolve()
            if path.stat().st_size > 4_096:
                return None
            raw_labels = json.loads(path.read_text(encoding="utf-8"))
            if type(raw_labels) is not dict or set(raw_labels) != {
                "schema_version",
                "profile_id",
                "scenario_id",
                "sample_index",
                "temperature",
                "evidence_source",
            }:
                return None
            if raw_labels["schema_version"] != L0_RUN_LABELS_VERSION:
                return None
            return (
                _safe_profile_token(raw_labels["profile_id"], "profile_id"),
                _safe_profile_token(raw_labels["scenario_id"], "scenario_id"),
                _safe_uint(raw_labels["sample_index"], "sample_index"),
                L0RoundTemperature(raw_labels["temperature"]),
                L0EvidenceSource(raw_labels["evidence_source"]),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    raw_profile = os.getenv(L0_MEASUREMENT_PROFILE_ENV)
    raw_scenario = os.getenv(L0_MEASUREMENT_SCENARIO_ENV)
    raw_sample = os.getenv(L0_MEASUREMENT_SAMPLE_ENV)
    raw_temperature = os.getenv(L0_MEASUREMENT_TEMPERATURE_ENV)
    raw_evidence_source = os.getenv(L0_MEASUREMENT_EVIDENCE_SOURCE_ENV)
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            raw_profile,
            raw_scenario,
            raw_sample,
            raw_temperature,
            raw_evidence_source,
        )
    ):
        return None
    try:
        return (
            _safe_profile_token(raw_profile, "profile_id"),
            _safe_profile_token(raw_scenario, "scenario_id"),
            _safe_uint(int(raw_sample), "sample_index"),
            L0RoundTemperature(raw_temperature),
            L0EvidenceSource(raw_evidence_source),
        )
    except (TypeError, ValueError):
        return None


def emit_runtime_l0_milestone(
    *,
    component: str,
    milestone: L0Milestone,
    binding: L0RoundBinding,
    classification: L0RoundClassification = L0RoundClassification.UNKNOWN,
    evidence_source: L0EvidenceSource | None = None,
    duration_ms: float | None = None,
    event_nonce: str | None = None,
) -> bool:
    """Best-effort production hook; diagnostics can never alter business truth."""

    try:
        labels = runtime_l0_run_labels()
        sink = process_l0_sink(component)
        if labels is None or sink is None:
            return False
        (
            profile_id,
            scenario_id,
            sample_index,
            temperature,
            run_evidence_source,
        ) = labels
        return sink.emit(
            create_l0_milestone(
                milestone=milestone,
                binding=binding,
                profile_id=profile_id,
                scenario_id=scenario_id,
                sample_index=sample_index,
                temperature=temperature,
                classification=classification,
                evidence_source=evidence_source or run_evidence_source,
                duration_ms=duration_ms,
                event_nonce=event_nonce,
            )
        )
    except Exception:
        return False


_RUNTIME_L0_BINDING_CAPACITY: Final = 1_024
_RUNTIME_L0_BINDINGS: OrderedDict[
    tuple[str, str, str, int], L0RoundBinding
] = OrderedDict()
_RUNTIME_L0_BLOCKED: set[tuple[str, str, str, int]] = set()
_RUNTIME_L0_BINDINGS_LOCK = Lock()


def register_runtime_l0_binding(binding: L0RoundBinding) -> bool:
    """Retain one opt-in exact response binding for later Agent callbacks."""

    try:
        checked = create_l0_round_binding(binding)
        if (
            checked.response_id is None
            or checked.response_generation is None
            or runtime_l0_run_labels() is None
            or process_l0_sink("agent") is None
        ):
            return False
        key = (
            checked.correlation_id,
            checked.interaction_id,
            checked.response_id,
            checked.response_generation,
        )
        with _RUNTIME_L0_BINDINGS_LOCK:
            if key in _RUNTIME_L0_BLOCKED:
                return False
            prior = _RUNTIME_L0_BINDINGS.get(key)
            if prior is not None:
                if not _binding_is_compatible(prior, checked):
                    _RUNTIME_L0_BINDINGS.pop(key, None)
                    if len(_RUNTIME_L0_BLOCKED) < _RUNTIME_L0_BINDING_CAPACITY:
                        _RUNTIME_L0_BLOCKED.add(key)
                    return False
                _RUNTIME_L0_BINDINGS[key] = _merge_binding(prior, checked)
                return True
            if len(_RUNTIME_L0_BINDINGS) >= _RUNTIME_L0_BINDING_CAPACITY:
                return False
            _RUNTIME_L0_BINDINGS[key] = checked
        return True
    except Exception:
        return False


def resolve_runtime_l0_binding(
    *,
    correlation_id: str,
    interaction_id: str,
    response_id: str,
    response_generation: int,
) -> L0RoundBinding | None:
    """Resolve only the exact registered response; no correlation-only fallback."""

    try:
        key = (
            _safe_identity(correlation_id, "correlation_id"),
            _safe_identity(interaction_id, "interaction_id"),
            _safe_identity(response_id, "response_id"),
            _safe_uint(response_generation, "response_generation"),
        )
    except Exception:
        return None
    with _RUNTIME_L0_BINDINGS_LOCK:
        return _RUNTIME_L0_BINDINGS.get(key)


def declarations_from_records(
    records: Iterable[L0MeasurementEnvelope],
) -> tuple[L0RoundDeclaration, ...]:
    """Build exact declarations while rejecting sample-key identity conflicts."""

    declarations: dict[tuple[str, str, int], L0RoundDeclaration] = {}
    for record in records:
        checked = create_l0_measurement_envelope(record)
        declaration = L0RoundDeclaration(
            binding=checked.binding,
            profile_id=checked.profile_id,
            scenario_id=checked.scenario_id,
            sample_index=checked.sample_index,
            temperature=checked.temperature,
            evidence_source=checked.evidence_source,
        )
        prior = declarations.get(declaration.round_key)
        if prior is not None:
            if (
                prior.temperature is not declaration.temperature
                or prior.evidence_source is not declaration.evidence_source
            ):
                raise _violation(
                    "ROUND_DECLARATION_CONFLICT",
                    "input sample key contains mixed classification scope",
                )
            declaration = L0RoundDeclaration(
                binding=_merge_binding(prior.binding, declaration.binding),
                profile_id=declaration.profile_id,
                scenario_id=declaration.scenario_id,
                sample_index=declaration.sample_index,
                temperature=declaration.temperature,
                evidence_source=declaration.evidence_source,
            )
        declarations[declaration.round_key] = declaration
    return tuple(declarations[key] for key in sorted(declarations))


__all__ = [
    "L0_CORPUS_MANIFEST_VERSION",
    "L0_MEASUREMENT_DIRECTORY_ENV",
    "L0_MEASUREMENT_EVIDENCE_SOURCE_ENV",
    "L0_MEASUREMENT_ENVELOPE_VERSION",
    "L0_MEASUREMENT_RUN_LABELS_FILE_ENV",
    "L0_MEASUREMENT_REPORT_VERSION",
    "L0_RUN_LABELS_VERSION",
    "L0CollectorStats",
    "L0EvidenceSource",
    "L0MeasurementCollector",
    "L0MeasurementEnvelope",
    "L0MeasurementViolation",
    "L0Milestone",
    "L0ProcessJsonlSink",
    "L0RoundBinding",
    "L0RoundClassification",
    "L0RoundDeclaration",
    "L0RoundTemperature",
    "build_l0_measurement_report",
    "canonical_json_bytes",
    "corpus_sha256",
    "create_l0_measurement_envelope",
    "create_l0_milestone",
    "create_l0_round_binding",
    "declarations_from_records",
    "emit_runtime_l0_milestone",
    "load_l0_corpus_manifest",
    "load_l0_jsonl",
    "process_l0_sink",
    "register_runtime_l0_binding",
    "resolve_runtime_l0_binding",
    "runtime_l0_run_labels",
    "validate_l0_corpus_manifest",
]
