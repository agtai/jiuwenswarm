# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Closed, best-effort records for the development-only Live Voice latency probe.

This module is a diagnostic data plane.  It never owns or changes product
authority, and all inputs are explicitly validated before they are retained.
"""

from __future__ import annotations

import json
import math
import os
import re
import secrets
import hashlib
import unicodedata
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from queue import Full, Queue
from threading import Condition, Lock, Thread
import time
from typing import Final


RUN_SCHEMA_VERSION_V0: Final = "live-voice.latency-run.v0"
RUN_SCHEMA_VERSION_V1: Final = "live-voice.latency-run.v1"
# Keep the historical public name stable for v0 callers. New producers select
# v1 explicitly in their closed manifest.
RUN_SCHEMA_VERSION: Final = RUN_SCHEMA_VERSION_V0
CONTEXT_SCHEMA_VERSION: Final = "live-voice.latency-context.v0"
MARK_SCHEMA_VERSION: Final = "live-voice.latency-probe.v0"
BATCH_SCHEMA_VERSION: Final = "live-voice.latency-batch.v0"
MAX_STRING_UTF8_BYTES: Final = 256
MAX_JSON_SAFE_INTEGER: Final = (1 << 53) - 1
MAX_MARKS_PER_BATCH: Final = 64
MAX_ORDINARY_MARKS: Final = MAX_MARKS_PER_BATCH - 1
MAX_WRITER_RECEIPTS: Final = 256
MAX_PENDING_EXPORT_BATCHES: Final = 256
MAX_RUN_COLLECTION_ITEMS: Final = 64
MAX_INTENDED_ATTEMPTS: Final = 256
LATENCY_PROBE_ENABLED_ENV: Final = "JIUWENSWARM_LIVE_VOICE_LATENCY_PROBE_ENABLED"
LATENCY_PROBE_RUN_CONFIG_ENV: Final = "JIUWENSWARM_LIVE_VOICE_LATENCY_PROBE_RUN_CONFIG"
LATENCY_PROBE_OUTPUT_ROOT_ENV: Final = "JIUWENSWARM_LIVE_VOICE_LATENCY_PROBE_OUTPUT_ROOT"

PROFILE_IDS: Final = (
    "dialogue_no_tool",
    "dialogue_with_tool",
    "task_create",
    "task_status",
    "task_cancel",
)
OPTIMIZATION_TRACKS: Final = (
    "capture_endpointing",
    "post_capture_pipeline",
)
BENCHMARK_LANES: Final = (
    "controlled_browser_fixture",
    "controlled_browser",
    "physical_journey",
)
_POST_CAPTURE_FIXTURE_PROFILES: Final = (
    "dialogue_no_tool",
    "dialogue_with_tool",
)
COMPONENTS: Final = ("browser", "gateway", "agent_server")
COMPONENT_OUTPUT_FILES: Final[Mapping[str, str]] = {
    "browser": "browser.jsonl",
    "gateway": "gateway.jsonl",
    "agent_server": "agent.jsonl",
}
WRITER_MODES: Final = ("single_component", "gateway_with_browser")
PHASES: Final = ("browser_round", "gateway_stt", "gateway_tts", "agent_foreground")
MARK_OUTCOMES: Final = (
    "observed",
    "completed",
    "failed",
    "cancelled",
    "fallback",
    "unknown",
)
TERMINAL_OUTCOMES: Final = ("completed", "failed", "cancelled", "unknown")
REASON_CODES: Final = (
    "FEATURE_OFF",
    "CAPACITY",
    "EXPORT_FAILED",
    "BATCH_CONFLICT",
    "MISSING_MARK",
    "DUPLICATE_MARK",
    "SEQUENCE_GAP",
    "IDENTITY_MISMATCH",
    "CROSS_CLOCK",
    "FAILED",
    "CANCELLED",
    "FALLBACK",
    "UNDERRUN",
    "REBUFFER",
    "TIMEOUT",
    "INCOMPATIBLE_RUN",
    "INSUFFICIENT_SAMPLES",
)

CORE_POINTS_BY_COMPONENT: Final[Mapping[str, tuple[str, ...]]] = {
    "browser": (
        "browser.eot_received",
        "browser.stt_final_received",
        "browser.commit_submit_started",
        "browser.presentation_received",
        "browser.tts_request_started",
        "browser.downlink_first_frame_received",
        "browser.playout_first_frame_scheduled",
        "browser.playout_first_frame_started_estimate",
        "browser.playout_completed",
        "browser.playout_ack_received",
        "browser.next_turn_capture_activated",
        "browser.capture_start_requested",
        "browser.capture_device_started",
        "browser.media_socket_attached",
        "browser.capture_first_frame_sent",
        "browser.capture_first_ack_received",
        "browser.capture_stop_requested",
        "browser.capture_stopped",
        "browser.uplink_last_frame_sent",
        "browser.uplink_last_ack_received",
        "browser.uplink_closed",
        "browser.successor_capture_requested",
        "browser.successor_capture_ready",
        "browser.downlink_attach_started",
        "browser.downlink_attached",
        "browser.playout_underrun",
        "browser.playout_rebuffer",
    ),
    "gateway": (
        "gateway.stt_request_started",
        "gateway.stt_provider_transport_open",
        "gateway.stt_session_ready",
        "gateway.vad_speech_stopped",
        "gateway.eot_control_sent",
        "gateway.stt_final_available",
        "gateway.stt_fallback_selected",
        "gateway.tts_request_received",
        "gateway.tts_provider_transport_open",
        "gateway.tts_provider_first_audio",
        "gateway.downlink_ticket_ready",
        "gateway.downlink_first_frame_sent",
    ),
    "agent_server": (
        "agent.commit_submit_received",
        "agent.commit_accepted",
        "agent.route_resolved",
        "agent.agent_started",
        "agent.agent_first_delta",
        "agent.tool_execution_started",
        "agent.tool_execution_completed",
        "agent.agent_final",
        "agent.task_command_accepted",
        "agent.presentation_produced",
        "agent.presentation_dispatched",
    ),
}
FIXED_SEGMENT_IDS: Final = frozenset(
    {
        "eot_to_stt_final", "stt_final_to_submit", "submit_to_presentation",
        "presentation_to_tts_request", "tts_request_to_first_downlink",
        "first_downlink_to_schedule", "schedule_to_start_estimate",
        "estimated_start_to_playout_complete", "playout_to_ack",
        "ack_to_next_capture", "response_total", "round_total",
        "capture_device_startup", "capture_first_frame_readiness",
        "eot_to_capture_stopped", "eot_to_uplink_closed",
        "successor_capture_readiness", "downlink_attach", "stt_transport_open",
        "stt_session_configuration", "provider_eot_to_control_send",
        "provider_eot_to_stt_final", "commit_admission", "semantic_routing",
        "route_to_agent_start", "agent_to_first_delta", "agent_to_final",
        "tool_execution", "agent_final_to_presentation", "task_command",
        "task_command_to_presentation", "presentation_dispatch",
        "tts_transport_open", "tts_open_to_first_audio", "tts_time_to_first_audio",
        "tts_first_audio_to_ticket", "tts_first_audio_to_first_send",
    }
)

_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_PUBLIC_TOKEN = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,255}$")
_SENSITIVE_DESCRIPTOR = re.compile(
    r"(?:private|secret|credential|password|transcript|prompt|authorization|bearer|api[_-]?key)",
    re.IGNORECASE,
)
_CONFIG_V0_KEYS = frozenset(
    {
        "schema_version", "run_id", "git_commit", "source_state",
        "environment_profile", "browser_family_and_version", "browser_os_class",
        "gateway_runtime_class", "agent_runtime_class", "stt_provider_and_model",
        "tts_provider_and_model", "audio_format", "vad_configuration",
        "playout_configuration", "allowlisted_feature_flags", "cold_or_warm",
        "input_case_ids", "profile_ids", "intended_attempts", "required_successes",
        "experiment",
    }
)
_CONFIG_V1_KEYS = _CONFIG_V0_KEYS | frozenset(
    {"optimization_track", "benchmark_lane", "fixture_profile_id"}
)
_MARK_KEYS = frozenset(
    {
        "schema_version", "run_id", "profile_id", "input_case_id", "round_index",
        "source_instance_id", "mark_index", "component", "clock_domain_id", "point",
        "monotonic_ms", "uncertainty_ms", "outcome", "reason_code", "correlation_id",
        "interaction_id", "activation_id", "activation_generation", "turn_id",
        "response_id", "response_generation", "task_id",
    }
)
_BATCH_KEYS = frozenset(
    {
        "schema_version", "batch_id", "run_id", "profile_id", "input_case_id",
        "round_index", "source_instance_id", "component", "phase", "terminal_outcome",
        "marks",
    }
)
_WRITE_LOCK = Lock()


class LatencyProbeViolation(ValueError):
    """A stable validation result that intentionally contains no user input."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _require_exact_keys(value: object, keys: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise LatencyProbeViolation("INVALID_STRUCTURE")
    return value


def _bounded_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise LatencyProbeViolation("INVALID_STRING")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        encoded = None
    if (
        encoded is None
        or len(encoded) > MAX_STRING_UTF8_BYTES
        or _PUBLIC_TOKEN.fullmatch(value) is None
        or value in (".", "..")
        or _SENSITIVE_DESCRIPTOR.search(value) is not None
    ):
        raise LatencyProbeViolation("INVALID_STRING")
    return value


def _bounded_descriptor(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise LatencyProbeViolation("INVALID_STRING")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        encoded = None
    if (
        encoded is None
        or len(encoded) > MAX_STRING_UTF8_BYTES
        or any(character in value for character in ("/", "\\", ":"))
        or any(unicodedata.category(character) == "Cc" for character in value)
        or _SENSITIVE_DESCRIPTOR.search(value) is not None
    ):
        raise LatencyProbeViolation("INVALID_STRING")
    return value


def _non_negative_integer(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > MAX_JSON_SAFE_INTEGER
    ):
        raise LatencyProbeViolation("INVALID_INTEGER")
    return value


def _positive_integer(value: object) -> int:
    value = _non_negative_integer(value)
    if value == 0:
        raise LatencyProbeViolation("INVALID_INTEGER")
    return value


def _finite_non_negative(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LatencyProbeViolation("INVALID_NUMBER")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        number = None
    if number is None:
        raise LatencyProbeViolation("INVALID_NUMBER")
    if not math.isfinite(number) or number < 0:
        raise LatencyProbeViolation("INVALID_NUMBER")
    return number


def _unique_bounded_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > MAX_RUN_COLLECTION_ITEMS:
        raise LatencyProbeViolation("INVALID_ARRAY")
    values = tuple(_bounded_string(item) for item in value)
    if len(set(values)) != len(values):
        raise LatencyProbeViolation("DUPLICATE_VALUE")
    return values


@dataclass(frozen=True, slots=True)
class LatencyExperimentPoint:
    point: str
    component: str
    paired_segment_id: str | None
    start_point: str | None
    end_point: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "point": self.point,
            "component": self.component,
            "paired_segment_id": self.paired_segment_id,
            "start_point": self.start_point,
            "end_point": self.end_point,
        }


@dataclass(frozen=True, slots=True)
class LatencyGuardrail:
    metric: str
    segment_id: str | None
    maximum_regression: float

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "segment_id": self.segment_id,
            "maximum_regression": self.maximum_regression,
        }


@dataclass(frozen=True, slots=True)
class LatencyExperiment:
    experiment_id: str
    target_segment: str
    target_statistic: str
    minimum_improvement_ms: float
    response_total_minimum_improvement_ms: float
    guardrails: tuple[LatencyGuardrail, ...]
    declared_experiment_points: tuple[LatencyExperimentPoint, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "target_segment": self.target_segment,
            "target_statistic": self.target_statistic,
            "minimum_improvement_ms": self.minimum_improvement_ms,
            "response_total_minimum_improvement_ms": self.response_total_minimum_improvement_ms,
            "guardrails": [guardrail.to_dict() for guardrail in self.guardrails],
            "declared_experiment_points": [
                point.to_dict() for point in self.declared_experiment_points
            ],
        }


@dataclass(frozen=True, slots=True)
class LatencyRunConfig:
    schema_version: str
    run_id: str
    git_commit: str
    source_state: str
    environment_profile: str
    browser_family_and_version: str
    browser_os_class: str
    gateway_runtime_class: str
    agent_runtime_class: str
    stt_provider_and_model: str
    tts_provider_and_model: str
    audio_format: str
    vad_configuration: str
    playout_configuration: str
    allowlisted_feature_flags: tuple[tuple[str, bool], ...]
    cold_or_warm: str
    input_case_ids: tuple[str, ...]
    profile_ids: tuple[str, ...]
    intended_attempts: int
    required_successes: int
    experiment: LatencyExperiment | None
    optimization_track: str = "legacy_full_journey"
    benchmark_lane: str = "legacy_unspecified"
    fixture_profile_id: str = "legacy-unspecified"

    def to_dict(self) -> dict[str, object]:
        result = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "git_commit": self.git_commit,
            "source_state": self.source_state,
            "environment_profile": self.environment_profile,
            "browser_family_and_version": self.browser_family_and_version,
            "browser_os_class": self.browser_os_class,
            "gateway_runtime_class": self.gateway_runtime_class,
            "agent_runtime_class": self.agent_runtime_class,
            "stt_provider_and_model": self.stt_provider_and_model,
            "tts_provider_and_model": self.tts_provider_and_model,
            "audio_format": self.audio_format,
            "vad_configuration": self.vad_configuration,
            "playout_configuration": self.playout_configuration,
            "allowlisted_feature_flags": dict(self.allowlisted_feature_flags),
            "cold_or_warm": self.cold_or_warm,
            "input_case_ids": list(self.input_case_ids),
            "profile_ids": list(self.profile_ids),
            "intended_attempts": self.intended_attempts,
            "required_successes": self.required_successes,
            "experiment": None if self.experiment is None else self.experiment.to_dict(),
        }
        if self.schema_version == RUN_SCHEMA_VERSION_V1:
            result.update(
                optimization_track=self.optimization_track,
                benchmark_lane=self.benchmark_lane,
                fixture_profile_id=self.fixture_profile_id,
            )
        return result

    def allows_point(self, point: str, component: str) -> bool:
        if component not in COMPONENTS or not isinstance(point, str):
            return False
        if point in CORE_POINTS_BY_COMPONENT[component]:
            return True
        return self.experiment is not None and any(
            declared.point == point and declared.component == component
            for declared in self.experiment.declared_experiment_points
        )

    def input_case_for_profile(self, profile_id: str) -> str | None:
        try:
            return self.input_case_ids[self.profile_ids.index(profile_id)]
        except (ValueError, IndexError):
            return None


@dataclass(frozen=True, slots=True)
class LatencyProbeContext:
    schema_version: str
    run_id: str
    profile_id: str
    input_case_id: str
    round_index: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "profile_id": self.profile_id,
            "input_case_id": self.input_case_id,
            "round_index": self.round_index,
        }


def _optional_bounded_string(value: object) -> str | None:
    return None if value is None else _bounded_string(value)


def _optional_non_negative_integer(value: object) -> int | None:
    return None if value is None else _non_negative_integer(value)


@dataclass(frozen=True, slots=True)
class LatencyMark:
    schema_version: str
    run_id: str
    profile_id: str
    input_case_id: str
    round_index: int
    source_instance_id: str
    mark_index: int
    component: str
    clock_domain_id: str
    point: str
    monotonic_ms: float
    uncertainty_ms: float | None
    outcome: str
    reason_code: str | None
    correlation_id: str
    interaction_id: str
    activation_id: str | None
    activation_generation: int | None
    turn_id: str | None
    response_id: str | None
    response_generation: int | None
    task_id: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "profile_id": self.profile_id,
            "input_case_id": self.input_case_id,
            "round_index": self.round_index,
            "source_instance_id": self.source_instance_id,
            "mark_index": self.mark_index,
            "component": self.component,
            "clock_domain_id": self.clock_domain_id,
            "point": self.point,
            "monotonic_ms": self.monotonic_ms,
            "uncertainty_ms": self.uncertainty_ms,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "correlation_id": self.correlation_id,
            "interaction_id": self.interaction_id,
            "activation_id": self.activation_id,
            "activation_generation": self.activation_generation,
            "turn_id": self.turn_id,
            "response_id": self.response_id,
            "response_generation": self.response_generation,
            "task_id": self.task_id,
        }

    @classmethod
    def from_dict(cls, value: object, run: LatencyRunConfig) -> LatencyMark:
        raw = _require_exact_keys(value, _MARK_KEYS)
        if raw["schema_version"] != MARK_SCHEMA_VERSION:
            raise LatencyProbeViolation("INVALID_SCHEMA_VERSION")
        component = raw["component"]
        point = _bounded_string(raw["point"])
        if component not in COMPONENTS or (
            point != "probe.capacity" and not run.allows_point(point, component)
        ):
            raise LatencyProbeViolation("INVALID_POINT")
        if raw["run_id"] != run.run_id:
            raise LatencyProbeViolation("INCOMPATIBLE_RUN")
        profile_id = _bounded_string(raw["profile_id"])
        input_case_id = _bounded_string(raw["input_case_id"])
        round_index = _non_negative_integer(raw["round_index"])
        if (
            profile_id not in run.profile_ids
            or input_case_id != run.input_case_for_profile(profile_id)
            or round_index >= run.intended_attempts
        ):
            raise LatencyProbeViolation("INCOMPATIBLE_RUN")
        if raw["outcome"] not in MARK_OUTCOMES:
            raise LatencyProbeViolation("INVALID_OUTCOME")
        reason_code = raw["reason_code"]
        if reason_code is not None and reason_code not in REASON_CODES:
            raise LatencyProbeViolation("INVALID_REASON_CODE")
        if point == "probe.capacity" and reason_code != "CAPACITY":
            raise LatencyProbeViolation("INVALID_POINT")
        uncertainty = raw["uncertainty_ms"]
        if uncertainty is not None:
            uncertainty = _finite_non_negative(uncertainty)
            if point != "browser.playout_first_frame_started_estimate":
                raise LatencyProbeViolation("INVALID_UNCERTAINTY")
        return cls(
            schema_version=MARK_SCHEMA_VERSION,
            run_id=run.run_id,
            profile_id=profile_id,
            input_case_id=input_case_id,
            round_index=round_index,
            source_instance_id=_bounded_string(raw["source_instance_id"]),
            mark_index=_non_negative_integer(raw["mark_index"]),
            component=component,
            clock_domain_id=_bounded_string(raw["clock_domain_id"]),
            point=point,
            monotonic_ms=_finite_non_negative(raw["monotonic_ms"]),
            uncertainty_ms=uncertainty,
            outcome=raw["outcome"],
            reason_code=reason_code,
            correlation_id=_bounded_string(raw["correlation_id"]),
            interaction_id=_bounded_string(raw["interaction_id"]),
            activation_id=_optional_bounded_string(raw["activation_id"]),
            activation_generation=_optional_non_negative_integer(raw["activation_generation"]),
            turn_id=_optional_bounded_string(raw["turn_id"]),
            response_id=_optional_bounded_string(raw["response_id"]),
            response_generation=_optional_non_negative_integer(raw["response_generation"]),
            task_id=_optional_bounded_string(raw["task_id"]),
        )


@dataclass(frozen=True, slots=True)
class LatencyBatch:
    schema_version: str
    batch_id: str
    run_id: str
    profile_id: str
    input_case_id: str
    round_index: int
    source_instance_id: str
    component: str
    phase: str
    terminal_outcome: str
    marks: tuple[LatencyMark, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "profile_id": self.profile_id,
            "input_case_id": self.input_case_id,
            "round_index": self.round_index,
            "source_instance_id": self.source_instance_id,
            "component": self.component,
            "phase": self.phase,
            "terminal_outcome": self.terminal_outcome,
            "marks": [mark.to_dict() for mark in self.marks],
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

    def with_batch_id(self, batch_id: str) -> LatencyBatch:
        return replace(self, batch_id=_bounded_string(batch_id))

    @classmethod
    def from_dict(cls, value: object, run: LatencyRunConfig) -> LatencyBatch:
        run = _revalidate_run_config(run)
        if run is None:
            raise LatencyProbeViolation("INCOMPATIBLE_RUN")
        raw = _require_exact_keys(value, _BATCH_KEYS)
        if raw["schema_version"] != BATCH_SCHEMA_VERSION or raw["run_id"] != run.run_id:
            raise LatencyProbeViolation("INCOMPATIBLE_RUN")
        component = raw["component"]
        phase = raw["phase"]
        if component not in COMPONENTS or phase not in PHASES:
            raise LatencyProbeViolation("INVALID_BATCH")
        if (
            (component == "browser" and phase != "browser_round")
            or (component == "agent_server" and phase != "agent_foreground")
            or (component == "gateway" and phase not in ("gateway_stt", "gateway_tts"))
        ):
            raise LatencyProbeViolation("INVALID_BATCH")
        if raw["terminal_outcome"] not in TERMINAL_OUTCOMES:
            raise LatencyProbeViolation("INVALID_OUTCOME")
        marks_raw = raw["marks"]
        if not isinstance(marks_raw, list) or len(marks_raw) > MAX_MARKS_PER_BATCH:
            raise LatencyProbeViolation("INVALID_BATCH")
        marks = tuple(LatencyMark.from_dict(item, run) for item in marks_raw)
        profile_id = _bounded_string(raw["profile_id"])
        input_case_id = _bounded_string(raw["input_case_id"])
        round_index = _non_negative_integer(raw["round_index"])
        source_instance_id = _bounded_string(raw["source_instance_id"])
        if (
            profile_id not in run.profile_ids
            or input_case_id != run.input_case_for_profile(profile_id)
            or round_index >= run.intended_attempts
        ):
            raise LatencyProbeViolation("INCOMPATIBLE_RUN")
        points: set[str] = set()
        capacity_count = 0
        for index, mark in enumerate(marks):
            if (
                mark.mark_index != index
                or mark.run_id != run.run_id
                or mark.profile_id != profile_id
                or mark.input_case_id != input_case_id
                or mark.round_index != round_index
                or mark.source_instance_id != source_instance_id
                or mark.component != component
            ):
                raise LatencyProbeViolation("INVALID_BATCH")
            if mark.point in points:
                raise LatencyProbeViolation("DUPLICATE_MARK")
            points.add(mark.point)
            if mark.point == "probe.capacity":
                capacity_count += 1
                if (
                    capacity_count != 1
                    or mark.mark_index != MAX_ORDINARY_MARKS
                    or len(marks) != MAX_MARKS_PER_BATCH
                ):
                    raise LatencyProbeViolation("INVALID_BATCH")
        if len(marks) == MAX_MARKS_PER_BATCH and capacity_count != 1:
            raise LatencyProbeViolation("INVALID_BATCH")
        return cls(
            schema_version=BATCH_SCHEMA_VERSION,
            batch_id=_bounded_string(raw["batch_id"]),
            run_id=run.run_id,
            profile_id=profile_id,
            input_case_id=input_case_id,
            round_index=round_index,
            source_instance_id=source_instance_id,
            component=component,
            phase=phase,
            terminal_outcome=raw["terminal_outcome"],
            marks=marks,
        )


def _parse_experiment(value: object) -> LatencyExperiment | None:
    if value is None:
        return None
    raw = _require_exact_keys(
        value,
        frozenset(
            {
                "experiment_id", "target_segment", "target_statistic",
                "minimum_improvement_ms", "response_total_minimum_improvement_ms",
                "guardrails", "declared_experiment_points",
            }
        ),
    )
    experiment_id = _bounded_string(raw["experiment_id"])
    target_segment = _bounded_string(raw["target_segment"])
    if target_segment not in FIXED_SEGMENT_IDS:
        raise LatencyProbeViolation("INVALID_SEGMENT")
    if raw["target_statistic"] not in ("p50_ms", "p95_ms"):
        raise LatencyProbeViolation("INVALID_STATISTIC")
    guards_raw = raw["guardrails"]
    if not isinstance(guards_raw, list) or len(guards_raw) > MAX_RUN_COLLECTION_ITEMS:
        raise LatencyProbeViolation("INVALID_ARRAY")
    guards: list[LatencyGuardrail] = []
    for item in guards_raw:
        guard = _require_exact_keys(
            item, frozenset({"metric", "segment_id", "maximum_regression"})
        )
        if guard["metric"] not in (
            "p50_ms", "p95_ms", "failure_rate", "fallback_rate", "underrun_rate",
            "rebuffer_rate", "cancellation_rate",
        ):
            raise LatencyProbeViolation("INVALID_GUARDRAIL")
        segment_id = guard["segment_id"]
        if segment_id is not None:
            segment_id = _bounded_string(segment_id)
            if segment_id not in FIXED_SEGMENT_IDS:
                raise LatencyProbeViolation("INVALID_SEGMENT")
        guards.append(
            LatencyGuardrail(
                metric=guard["metric"],
                segment_id=segment_id,
                maximum_regression=_finite_non_negative(guard["maximum_regression"]),
            )
        )
    points_raw = raw["declared_experiment_points"]
    if not isinstance(points_raw, list) or len(points_raw) > MAX_RUN_COLLECTION_ITEMS:
        raise LatencyProbeViolation("INVALID_ARRAY")
    points: list[LatencyExperimentPoint] = []
    prefix = f"experiment.{experiment_id}."
    for item in points_raw:
        point = _require_exact_keys(
            item,
            frozenset({"point", "component", "paired_segment_id", "start_point", "end_point"}),
        )
        name = _bounded_string(point["point"])
        if not name.startswith(prefix) or point["component"] not in COMPONENTS:
            raise LatencyProbeViolation("INVALID_EXPERIMENT_POINT")
        optional = []
        for key in ("paired_segment_id", "start_point", "end_point"):
            item_value = point[key]
            optional.append(None if item_value is None else _bounded_string(item_value))
        points.append(
            LatencyExperimentPoint(name, point["component"], *optional)
        )
    if len({point.point for point in points}) != len(points):
        raise LatencyProbeViolation("DUPLICATE_VALUE")
    return LatencyExperiment(
        experiment_id=experiment_id,
        target_segment=target_segment,
        target_statistic=raw["target_statistic"],
        minimum_improvement_ms=_finite_non_negative(raw["minimum_improvement_ms"]),
        response_total_minimum_improvement_ms=_finite_non_negative(
            raw["response_total_minimum_improvement_ms"]
        ),
        guardrails=tuple(guards),
        declared_experiment_points=tuple(points),
    )


def _parse_latency_run_config(raw: object) -> LatencyRunConfig:
    if not isinstance(raw, Mapping):
        raise LatencyProbeViolation("INVALID_STRUCTURE")
    schema_version = raw.get("schema_version")
    if schema_version == RUN_SCHEMA_VERSION_V0:
        value = _require_exact_keys(raw, _CONFIG_V0_KEYS)
        optimization_track = "legacy_full_journey"
        benchmark_lane = "legacy_unspecified"
        fixture_profile_id = "legacy-unspecified"
    elif schema_version == RUN_SCHEMA_VERSION_V1:
        value = _require_exact_keys(raw, _CONFIG_V1_KEYS)
        optimization_track = value["optimization_track"]
        benchmark_lane = value["benchmark_lane"]
        fixture_profile_id = value["fixture_profile_id"]
        if optimization_track not in OPTIMIZATION_TRACKS:
            raise LatencyProbeViolation("INVALID_OPTIMIZATION_TRACK")
        if benchmark_lane not in BENCHMARK_LANES:
            raise LatencyProbeViolation("INVALID_BENCHMARK_LANE")
        fixture_profile_id = _bounded_string(fixture_profile_id)
    else:
        raise LatencyProbeViolation("INVALID_SCHEMA_VERSION")
    run_id = _bounded_string(value["run_id"])
    git_commit = value["git_commit"]
    if not isinstance(git_commit, str) or _GIT_COMMIT.fullmatch(git_commit) is None:
        raise LatencyProbeViolation("INVALID_GIT_COMMIT")
    if value["source_state"] not in ("clean", "docs_only_dirty", "product_code_dirty"):
        raise LatencyProbeViolation("INVALID_SOURCE_STATE")
    if value["cold_or_warm"] not in ("cold", "warm"):
        raise LatencyProbeViolation("INVALID_COLD_OR_WARM")
    profile_ids = _unique_bounded_strings(value["profile_ids"])
    expected_subset = tuple(profile for profile in PROFILE_IDS if profile in profile_ids)
    if (
        (schema_version == RUN_SCHEMA_VERSION_V0 and profile_ids != PROFILE_IDS)
        or (schema_version == RUN_SCHEMA_VERSION_V1 and profile_ids != expected_subset)
    ):
        raise LatencyProbeViolation("INVALID_PROFILES")
    if (
        schema_version == RUN_SCHEMA_VERSION_V1
        and optimization_track == "post_capture_pipeline"
        and benchmark_lane == "controlled_browser_fixture"
        and any(profile not in _POST_CAPTURE_FIXTURE_PROFILES for profile in profile_ids)
    ):
        raise LatencyProbeViolation("INVALID_PROFILES")
    flags = value["allowlisted_feature_flags"]
    if not isinstance(flags, Mapping) or len(flags) > MAX_RUN_COLLECTION_ITEMS:
        raise LatencyProbeViolation("INVALID_FLAGS")
    parsed_flags: list[tuple[str, bool]] = []
    for key, flag in flags.items():
        parsed_flags.append((_bounded_string(key), flag))
        if not isinstance(flag, bool):
            raise LatencyProbeViolation("INVALID_FLAGS")
    intended_attempts = _positive_integer(value["intended_attempts"])
    required_successes = _positive_integer(value["required_successes"])
    if (
        intended_attempts > MAX_INTENDED_ATTEMPTS
        or required_successes > intended_attempts
    ):
        raise LatencyProbeViolation("INVALID_ATTEMPT_POLICY")
    fields = (
        "environment_profile", "browser_family_and_version", "browser_os_class",
        "gateway_runtime_class", "agent_runtime_class", "stt_provider_and_model",
        "tts_provider_and_model", "audio_format", "vad_configuration",
        "playout_configuration",
    )
    parsed = {field: _bounded_descriptor(value[field]) for field in fields}
    input_case_ids = _unique_bounded_strings(value["input_case_ids"])
    if len(input_case_ids) != len(profile_ids):
        raise LatencyProbeViolation("INVALID_ATTEMPT_POLICY")
    return LatencyRunConfig(
        schema_version=schema_version,
        run_id=run_id,
        git_commit=git_commit,
        source_state=value["source_state"],
        allowlisted_feature_flags=tuple(sorted(parsed_flags)),
        cold_or_warm=value["cold_or_warm"],
        input_case_ids=input_case_ids,
        profile_ids=profile_ids,
        intended_attempts=intended_attempts,
        required_successes=required_successes,
        experiment=_parse_experiment(value["experiment"]),
        optimization_track=optimization_track,
        benchmark_lane=benchmark_lane,
        fixture_profile_id=fixture_profile_id,
        **parsed,
    )


def _revalidate_run_config(value: object) -> LatencyRunConfig | None:
    if not isinstance(value, LatencyRunConfig):
        return None
    try:
        normalized = _parse_latency_run_config(value.to_dict())
    except Exception:
        return None
    return normalized if normalized == value else None


def load_latency_run_config(path: Path) -> LatencyRunConfig:
    """Load a closed run manifest; rejected content is never included in errors."""
    failed_to_load = False
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raw = None
        failed_to_load = True
    if failed_to_load:
        raise LatencyProbeViolation("INVALID_RUN_CONFIG")
    return _parse_latency_run_config(raw)


def try_parse_latency_probe_context(
    value: object, run: LatencyRunConfig
) -> LatencyProbeContext | None:
    """Return only a compatible closed context; malformed diagnostics are ignored."""
    try:
        run = _revalidate_run_config(run)
        if run is None:
            return None
        raw = _require_exact_keys(
            value,
            frozenset({"schema_version", "run_id", "profile_id", "input_case_id", "round_index"}),
        )
        if raw["schema_version"] != CONTEXT_SCHEMA_VERSION:
            return None
        run_id = _bounded_string(raw["run_id"])
        profile_id = _bounded_string(raw["profile_id"])
        input_case_id = _bounded_string(raw["input_case_id"])
        round_index = _non_negative_integer(raw["round_index"])
        if (
            run_id != run.run_id
            or profile_id not in run.profile_ids
            or input_case_id != run.input_case_for_profile(profile_id)
            or round_index >= run.intended_attempts
        ):
            return None
        return LatencyProbeContext(
            CONTEXT_SCHEMA_VERSION, run_id, profile_id, input_case_id, round_index
        )
    except Exception:
        return None


@dataclass(frozen=True, slots=True)
class LatencyProbeWriteResult:
    status: str
    batch_id: str
    reason_code: str | None


class LatencyProbeRecorder:
    """Collect one bounded component-local batch without writing on mark paths."""

    def __init__(
        self,
        *,
        context: LatencyProbeContext,
        component: str,
        phase: str,
        run_config: LatencyRunConfig,
        source_instance_id_factory: Callable[[], str] = lambda: secrets.token_urlsafe(18),
        batch_id_factory: Callable[[], str] = lambda: secrets.token_urlsafe(18),
        clock_domain_id: str,
        monotonic_ms: Callable[[], float],
    ) -> None:
        if component not in COMPONENTS or phase not in PHASES:
            raise LatencyProbeViolation("INVALID_BATCH")
        if (
            (component == "browser" and phase != "browser_round")
            or (component == "agent_server" and phase != "agent_foreground")
            or (component == "gateway" and phase not in ("gateway_stt", "gateway_tts"))
        ):
            raise LatencyProbeViolation("INVALID_BATCH")
        run_config = _revalidate_run_config(run_config)
        if run_config is None or not isinstance(context, LatencyProbeContext):
            raise LatencyProbeViolation("INCOMPATIBLE_RUN")
        validated_context = try_parse_latency_probe_context(context.to_dict(), run_config)
        if validated_context is None:
            raise LatencyProbeViolation("INCOMPATIBLE_RUN")
        self._context = validated_context
        self._run_config = run_config
        self._component = component
        self._phase = phase
        self._source_instance_id = _bounded_string(source_instance_id_factory())
        self._batch_id = _bounded_string(batch_id_factory())
        self._clock_domain_id = _bounded_string(clock_domain_id)
        self._monotonic_ms = monotonic_ms
        self._marks: list[LatencyMark] = []
        self._points: set[str] = set()
        self._finished = False
        self._capacity_recorded = False

    def mark(
        self,
        point: str,
        *,
        correlation_id: str,
        interaction_id: str,
        activation_id: str | None = None,
        activation_generation: int | None = None,
        turn_id: str | None = None,
        response_id: str | None = None,
        response_generation: int | None = None,
        task_id: str | None = None,
        uncertainty_ms: float | None = None,
        outcome: str = "observed",
        reason_code: str | None = None,
    ) -> bool:
        """Record a validated mark, returning false for a probe-only rejection."""
        if self._finished or self._capacity_recorded:
            return False
        if len(self._marks) >= MAX_ORDINARY_MARKS:
            self._record_capacity(correlation_id, interaction_id)
            return False
        try:
            if not isinstance(point, str) or point in self._points:
                return False
            if not self._run_config.allows_point(point, self._component):
                return False
            if outcome not in MARK_OUTCOMES or (reason_code is not None and reason_code not in REASON_CODES):
                return False
            mark = LatencyMark(
                schema_version=MARK_SCHEMA_VERSION,
                run_id=self._context.run_id,
                profile_id=self._context.profile_id,
                input_case_id=self._context.input_case_id,
                round_index=self._context.round_index,
                source_instance_id=self._source_instance_id,
                mark_index=len(self._marks),
                component=self._component,
                clock_domain_id=self._clock_domain_id,
                point=_bounded_string(point),
                monotonic_ms=_finite_non_negative(self._monotonic_ms()),
                uncertainty_ms=(
                    None if uncertainty_ms is None else _finite_non_negative(uncertainty_ms)
                ),
                outcome=outcome,
                reason_code=reason_code,
                correlation_id=_bounded_string(correlation_id),
                interaction_id=_bounded_string(interaction_id),
                activation_id=_optional_bounded_string(activation_id),
                activation_generation=_optional_non_negative_integer(activation_generation),
                turn_id=_optional_bounded_string(turn_id),
                response_id=_optional_bounded_string(response_id),
                response_generation=_optional_non_negative_integer(response_generation),
                task_id=_optional_bounded_string(task_id),
            )
            if mark.uncertainty_ms is not None and point != "browser.playout_first_frame_started_estimate":
                return False
        except Exception:
            return False
        self._marks.append(mark)
        self._points.add(point)
        return True

    def _record_capacity(self, correlation_id: str, interaction_id: str) -> None:
        if self._capacity_recorded or len(self._marks) >= MAX_MARKS_PER_BATCH:
            return
        try:
            mark = LatencyMark(
                schema_version=MARK_SCHEMA_VERSION,
                run_id=self._context.run_id,
                profile_id=self._context.profile_id,
                input_case_id=self._context.input_case_id,
                round_index=self._context.round_index,
                source_instance_id=self._source_instance_id,
                mark_index=len(self._marks),
                component=self._component,
                clock_domain_id=self._clock_domain_id,
                point="probe.capacity",
                monotonic_ms=_finite_non_negative(self._monotonic_ms()),
                uncertainty_ms=None,
                outcome="unknown",
                reason_code="CAPACITY",
                correlation_id=_bounded_string(correlation_id),
                interaction_id=_bounded_string(interaction_id),
                activation_id=None,
                activation_generation=None,
                turn_id=None,
                response_id=None,
                response_generation=None,
                task_id=None,
            )
        except Exception:
            self._capacity_recorded = True
            return
        self._marks.append(mark)
        self._capacity_recorded = True

    def finish(self, terminal_outcome: str) -> LatencyBatch | None:
        if self._finished or terminal_outcome not in TERMINAL_OUTCOMES:
            return None
        self._finished = True
        return LatencyBatch(
            schema_version=BATCH_SCHEMA_VERSION,
            batch_id=self._batch_id,
            run_id=self._context.run_id,
            profile_id=self._context.profile_id,
            input_case_id=self._context.input_case_id,
            round_index=self._context.round_index,
            source_instance_id=self._source_instance_id,
            component=self._component,
            phase=self._phase,
            terminal_outcome=terminal_outcome,
            marks=tuple(self._marks),
        )


class LatencyProbeBatchWriter:
    """Append canonical batches with bounded cache and durable deduplication."""

    def __init__(
        self,
        output_root: Path,
        run_config: LatencyRunConfig,
        component: str,
        *,
        mode: str = "single_component",
    ) -> None:
        run_config = _revalidate_run_config(run_config)
        if (
            run_config is None
            or component not in COMPONENTS
            or mode not in WRITER_MODES
        ):
            raise LatencyProbeViolation("INVALID_COMPONENT")
        if mode == "single_component":
            allowed = (component,)
        elif mode == "gateway_with_browser" and component == "gateway":
            allowed = ("browser", "gateway")
        else:
            raise LatencyProbeViolation("INVALID_COMPONENT")
        self._run_config = run_config
        self._run_id = _bounded_string(run_config.run_id)
        self._component = component
        self._allowed_components = frozenset(allowed)
        self._run_dir = Path(output_root) / self._run_id
        self._receipts: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._slot_receipts: OrderedDict[
            tuple[str, str, str, int], tuple[str, str]
        ] = OrderedDict()
        self._run_dir.mkdir(parents=True, exist_ok=True)

    def _remember_receipt(
        self,
        component: str,
        batch_id: str,
        digest: str,
    ) -> None:
        key = (component, batch_id)
        self._receipts[key] = digest
        self._receipts.move_to_end(key)
        while len(self._receipts) > MAX_WRITER_RECEIPTS:
            self._receipts.popitem(last=False)

    @staticmethod
    def _semantic_slot(batch: LatencyBatch) -> tuple[str, str, str, int]:
        return (
            batch.phase,
            batch.profile_id,
            batch.input_case_id,
            batch.round_index,
        )

    def _remember_slot_receipt(
        self,
        slot: tuple[str, str, str, int],
        batch_id: str,
        digest: str,
    ) -> None:
        self._slot_receipts[slot] = (batch_id, digest)
        self._slot_receipts.move_to_end(slot)
        while len(self._slot_receipts) > MAX_WRITER_RECEIPTS:
            self._slot_receipts.popitem(last=False)

    def _read_durable_receipts(
        self,
        path: Path,
        batch: LatencyBatch,
    ) -> tuple[str | None, tuple[str, str] | None]:
        if not path.exists():
            return None, None
        found_batch: str | None = None
        found_slot: tuple[str, str] | None = None
        requested_slot = self._semantic_slot(batch)
        with path.open("rb") as handle:
            for line in handle:
                if not line.endswith(b"\n"):
                    raise LatencyProbeViolation("INVALID_BATCH")
                parsed = LatencyBatch.from_dict(
                    json.loads(line),
                    self._run_config,
                )
                if parsed.component not in self._allowed_components:
                    raise LatencyProbeViolation("INCOMPATIBLE_RUN")
                digest = hashlib.sha256(parsed.canonical_bytes()).hexdigest()
                if parsed.batch_id == batch.batch_id:
                    if found_batch is not None and found_batch != digest:
                        raise LatencyProbeViolation("BATCH_CONFLICT")
                    found_batch = digest
                if self._semantic_slot(parsed) == requested_slot:
                    receipt = (parsed.batch_id, digest)
                    if found_slot is not None and found_slot != receipt:
                        raise LatencyProbeViolation("BATCH_CONFLICT")
                    found_slot = receipt
        return found_batch, found_slot

    def write(self, batch: LatencyBatch) -> LatencyProbeWriteResult:
        if not isinstance(batch, LatencyBatch):
            return LatencyProbeWriteResult("rejected", "", "INCOMPATIBLE_RUN")
        try:
            validated = LatencyBatch.from_dict(batch.to_dict(), self._run_config)
        except LatencyProbeViolation as exc:
            return LatencyProbeWriteResult("rejected", "", exc.reason_code)
        except Exception:
            return LatencyProbeWriteResult("failed", "", "EXPORT_FAILED")
        if (
            validated.run_id != self._run_id
            or validated.component not in self._allowed_components
        ):
            return LatencyProbeWriteResult(
                "rejected", validated.batch_id, "INCOMPATIBLE_RUN"
            )
        try:
            data = validated.canonical_bytes()
            digest = hashlib.sha256(data).hexdigest()
        except Exception:
            return LatencyProbeWriteResult("failed", validated.batch_id, "EXPORT_FAILED")
        with _WRITE_LOCK:
            receipt_key = (validated.component, validated.batch_id)
            existing = self._receipts.get(receipt_key)
            slot = self._semantic_slot(validated)
            existing_slot = self._slot_receipts.get(slot)
            path = self._run_dir / COMPONENT_OUTPUT_FILES[validated.component]
            if existing is None or existing_slot is None:
                try:
                    durable_batch, durable_slot = self._read_durable_receipts(
                        path,
                        validated,
                    )
                except Exception:
                    return LatencyProbeWriteResult(
                        "failed", validated.batch_id, "EXPORT_FAILED"
                    )
                if existing is None:
                    existing = durable_batch
                if existing_slot is None:
                    existing_slot = durable_slot
            if existing is not None or existing_slot is not None:
                if existing is not None:
                    self._remember_receipt(
                        validated.component,
                        validated.batch_id,
                        existing,
                    )
                if existing_slot is not None:
                    self._remember_slot_receipt(slot, *existing_slot)
                if (
                    existing == digest
                    and existing_slot == (validated.batch_id, digest)
                ):
                    return LatencyProbeWriteResult(
                        "idempotent", validated.batch_id, None
                    )
                return LatencyProbeWriteResult(
                    "rejected", validated.batch_id, "BATCH_CONFLICT"
                )
            offset: int | None = None
            created_output = False
            try:
                created_output = not path.exists()
                with path.open("ab") as handle:
                    offset = handle.tell()
                    payload = data + b"\n"
                    if handle.write(payload) != len(payload):
                        handle.truncate(offset)
                        if created_output:
                            path.unlink(missing_ok=True)
                        return LatencyProbeWriteResult(
                            "failed", validated.batch_id, "EXPORT_FAILED"
                        )
            except Exception:
                if offset is not None:
                    try:
                        with path.open("r+b") as rollback:
                            rollback.truncate(offset)
                    except Exception:
                        pass
                if created_output:
                    try:
                        path.unlink(missing_ok=True)
                    except Exception:
                        pass
                return LatencyProbeWriteResult("failed", validated.batch_id, "EXPORT_FAILED")
            self._remember_receipt(
                validated.component,
                validated.batch_id,
                digest,
            )
            self._remember_slot_receipt(slot, validated.batch_id, digest)
        return LatencyProbeWriteResult("written", validated.batch_id, None)


class LatencyProbeBatchExporter:
    """Move serialization and durable writes off measured product paths."""

    def __init__(self, writer: object) -> None:
        self._writer = writer
        self._queue: Queue[LatencyBatch | object] = Queue(
            maxsize=MAX_PENDING_EXPORT_BATCHES
        )
        self._stop = object()
        self._condition = Condition()
        self._pending = 0
        self._closed = False
        self._thread: Thread | None = None

    def submit(self, batch: LatencyBatch) -> bool:
        if (
            not isinstance(batch, LatencyBatch)
            or not callable(getattr(self._writer, "write", None))
        ):
            return False
        with self._condition:
            if self._closed:
                return False
            try:
                self._queue.put_nowait(batch)
            except Full:
                return False
            self._pending += 1
            if self._thread is None:
                thread = Thread(
                    target=self._run,
                    name="live-voice-latency-export",
                    daemon=True,
                )
                self._thread = thread
                try:
                    thread.start()
                except BaseException:
                    self._thread = None
                    self._queue.get_nowait()
                    self._queue.task_done()
                    self._pending -= 1
                    self._condition.notify_all()
                    return False
            return True

    def _run(self) -> None:
        while True:
            batch = self._queue.get()
            if batch is self._stop:
                return
            try:
                self._writer.write(batch)
            except BaseException:
                # This diagnostic worker owns no product or process authority.
                pass
            finally:
                with self._condition:
                    self._pending -= 1
                    self._condition.notify_all()

    def drain(self, timeout: float) -> bool:
        try:
            deadline = time.monotonic() + _finite_non_negative(timeout)
        except Exception:
            return False
        with self._condition:
            while self._pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def close(self, timeout: float) -> bool:
        try:
            deadline = time.monotonic() + _finite_non_negative(timeout)
        except Exception:
            return False
        with self._condition:
            self._closed = True
        if not self.drain(max(0.0, deadline - time.monotonic())):
            return False
        with self._condition:
            thread = self._thread
            if thread is None:
                return True
            try:
                self._queue.put_nowait(self._stop)
            except Full:
                return False
        thread.join(max(0.0, deadline - time.monotonic()))
        return not thread.is_alive()


@dataclass(frozen=True, slots=True)
class LatencyProbeRuntime:
    run_config: LatencyRunConfig
    component: str
    writer: LatencyProbeBatchWriter
    source_instance_id: str = field(
        default_factory=lambda: secrets.token_urlsafe(18)
    )
    _exporter: LatencyProbeBatchExporter = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_instance_id",
            _bounded_string(self.source_instance_id),
        )
        object.__setattr__(self, "_exporter", LatencyProbeBatchExporter(self.writer))

    def submit(self, batch: LatencyBatch) -> bool:
        return self._exporter.submit(batch)

    def drain(self, timeout: float) -> bool:
        return self._exporter.drain(timeout)

    def close(self, timeout: float) -> bool:
        return self._exporter.close(timeout)

    def create_recorder(
        self,
        *,
        context: LatencyProbeContext,
        phase: str,
        clock_domain_id: str,
        monotonic_ms: Callable[[], float],
        batch_id_factory: Callable[[], str] = lambda: secrets.token_urlsafe(18),
    ) -> LatencyProbeRecorder | None:
        try:
            run_config = _revalidate_run_config(self.run_config)
            if run_config is None:
                return None
            if not isinstance(context, LatencyProbeContext):
                return None
            validated_context = try_parse_latency_probe_context(
                context.to_dict(), run_config
            )
            if validated_context is None:
                return None
            return LatencyProbeRecorder(
                context=validated_context,
                component=self.component,
                phase=phase,
                run_config=run_config,
                source_instance_id_factory=lambda: self.source_instance_id,
                batch_id_factory=batch_id_factory,
                clock_domain_id=clock_domain_id,
                monotonic_ms=monotonic_ms,
            )
        except Exception:
            return None


def create_latency_probe_runtime_from_environment(
    component: str,
) -> LatencyProbeRuntime | None:
    """Create the enabled-only runtime; diagnostics never block product startup."""
    if os.environ.get(LATENCY_PROBE_ENABLED_ENV) not in ("1", "true", "TRUE"):
        return None
    config_path = os.environ.get(LATENCY_PROBE_RUN_CONFIG_ENV)
    output_root = os.environ.get(LATENCY_PROBE_OUTPUT_ROOT_ENV)
    if not config_path or not output_root or component not in COMPONENTS:
        return None
    try:
        run_config = load_latency_run_config(Path(config_path))
        writer = LatencyProbeBatchWriter(
            Path(output_root),
            run_config,
            component,
            mode="gateway_with_browser" if component == "gateway" else "single_component",
        )
        return LatencyProbeRuntime(run_config, component, writer)
    except Exception:
        return None
