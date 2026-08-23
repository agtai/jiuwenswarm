# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Offline, fixed-contract reduction for the Live Voice latency probe.

This module deliberately has no product-side dependencies.  It consumes the
closed Task 1 diagnostic records after a run and preserves uncertainty rather
than deriving timings across clocks or authoritative identities.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Final

from .latency_probe import (
    COMPONENT_OUTPUT_FILES,
    CORE_POINTS_BY_COMPONENT,
    FIXED_SEGMENT_IDS,
    LatencyBatch,
    LatencyMark,
    LatencyProbeViolation,
    LatencyRunConfig,
    PROFILE_IDS,
    RUN_SCHEMA_VERSION_V0,
    RUN_SCHEMA_VERSION_V1,
    _parse_latency_run_config,
    load_latency_run_config,
)


REPORT_SCHEMA_VERSION: Final = "live-voice.latency-report.v0"
COMPARISON_SCHEMA_VERSION: Final = "live-voice.latency-comparison.v0"
ABA_COMPARISON_SCHEMA_VERSION: Final = "live-voice.latency-comparison-a-b-a.v0"
_BROWSER_PROFILES: Final = PROFILE_IDS
_DIALOGUE_PROFILES: Final = ("dialogue_no_tool", "dialogue_with_tool")
_TASK_PROFILES: Final = ("task_create", "task_status", "task_cancel")
POST_CAPTURE_TARGET_SEGMENTS: Final = frozenset(
    {
        "eot_to_stt_final",
        "stt_final_to_submit",
        "submit_to_presentation",
        "presentation_to_tts_request",
        "tts_request_to_first_downlink",
        "first_downlink_to_schedule",
        "schedule_to_start_estimate",
        "playout_to_ack",
        "response_total",
    }
)


@dataclass(frozen=True, slots=True)
class SegmentDefinition:
    segment_id: str
    start_point: str
    end_point: str
    component: str
    phase_tags: tuple[str, ...]
    primary_capability: str
    applicable_profiles: tuple[str, ...]
    measurement_kind: str = "exact"


def _segment(
    segment_id: str,
    start_point: str,
    end_point: str,
    component: str,
    phases: tuple[str, ...],
    capability: str,
    profiles: tuple[str, ...] = _BROWSER_PROFILES,
    measurement_kind: str = "exact",
) -> SegmentDefinition:
    return SegmentDefinition(
        segment_id, start_point, end_point, component, phases, capability,
        profiles, measurement_kind,
    )


FIXED_SEGMENTS: Final[tuple[SegmentDefinition, ...]] = (
    _segment("eot_to_stt_final", "browser.eot_received", "browser.stt_final_received", "browser", ("P1", "P2"), "speech_recognition"),
    _segment("stt_final_to_submit", "browser.stt_final_received", "browser.commit_submit_started", "browser", ("P1", "P2", "P3"), "integrated_web"),
    _segment("submit_to_presentation", "browser.commit_submit_started", "browser.presentation_received", "browser", ("P2", "P3"), "cross_component_seam"),
    _segment("presentation_to_tts_request", "browser.presentation_received", "browser.tts_request_started", "browser", ("P1", "P2", "P3"), "integrated_web"),
    _segment("tts_request_to_first_downlink", "browser.tts_request_started", "browser.downlink_first_frame_received", "browser", ("P1", "P2", "P3"), "cross_component_seam"),
    _segment("first_downlink_to_schedule", "browser.downlink_first_frame_received", "browser.playout_first_frame_scheduled", "browser", ("P1",), "audio_io"),
    _segment("schedule_to_start_estimate", "browser.playout_first_frame_scheduled", "browser.playout_first_frame_started_estimate", "browser", ("P1",), "audio_io", measurement_kind="estimate"),
    _segment("estimated_start_to_playout_complete", "browser.playout_first_frame_started_estimate", "browser.playout_completed", "browser", ("P1",), "audio_io"),
    _segment("playout_to_ack", "browser.playout_completed", "browser.playout_ack_received", "browser", ("P1", "P2", "P3"), "cross_component_seam"),
    _segment("ack_to_next_capture", "browser.playout_ack_received", "browser.next_turn_capture_activated", "browser", ("P1", "P2"), "conversation_runtime"),
    _segment("response_total", "browser.eot_received", "browser.playout_first_frame_started_estimate", "browser", ("P1", "P2", "P3"), "integrated_web", measurement_kind="estimate"),
    _segment("round_total", "browser.eot_received", "browser.next_turn_capture_activated", "browser", ("P1", "P2", "P3"), "integrated_web"),
    _segment("capture_device_startup", "browser.capture_start_requested", "browser.capture_device_started", "browser", ("P1",), "audio_io"),
    _segment("capture_first_frame_readiness", "browser.capture_start_requested", "browser.capture_first_ack_received", "browser", ("P1", "P2"), "realtime_media"),
    _segment("eot_to_capture_stopped", "browser.eot_received", "browser.capture_stopped", "browser", ("P1",), "audio_io"),
    _segment("eot_to_uplink_closed", "browser.eot_received", "browser.uplink_closed", "browser", ("P1", "P2"), "realtime_media"),
    _segment("successor_capture_readiness", "browser.successor_capture_requested", "browser.successor_capture_ready", "browser", ("P1", "P2"), "realtime_media"),
    _segment("downlink_attach", "browser.downlink_attach_started", "browser.downlink_attached", "browser", ("P1", "P2"), "realtime_media"),
    _segment("stt_transport_open", "gateway.stt_request_started", "gateway.stt_provider_transport_open", "gateway", ("P1", "P2"), "speech_recognition"),
    _segment("stt_session_configuration", "gateway.stt_provider_transport_open", "gateway.stt_session_ready", "gateway", ("P1", "P2"), "speech_recognition"),
    _segment("provider_eot_to_control_send", "gateway.vad_speech_stopped", "gateway.eot_control_sent", "gateway", ("P1", "P2"), "interaction_intelligence"),
    _segment("provider_eot_to_stt_final", "gateway.vad_speech_stopped", "gateway.stt_final_available", "gateway", ("P1", "P2"), "speech_recognition"),
    _segment("commit_admission", "agent.commit_submit_received", "agent.commit_accepted", "agent_server", ("P2", "P3"), "conversation_runtime"),
    _segment("semantic_routing", "agent.commit_accepted", "agent.route_resolved", "agent_server", ("P2", "P3"), "interaction_intelligence"),
    _segment("route_to_agent_start", "agent.route_resolved", "agent.agent_started", "agent_server", ("P2",), "agent_bridge", _DIALOGUE_PROFILES),
    _segment("agent_to_first_delta", "agent.agent_started", "agent.agent_first_delta", "agent_server", ("P2",), "agent_bridge", _DIALOGUE_PROFILES),
    _segment("agent_to_final", "agent.agent_started", "agent.agent_final", "agent_server", ("P2",), "agent_bridge", _DIALOGUE_PROFILES),
    _segment("tool_execution", "agent.tool_execution_started", "agent.tool_execution_completed", "agent_server", ("P2",), "agent_bridge", ("dialogue_with_tool",)),
    _segment("agent_final_to_presentation", "agent.agent_final", "agent.presentation_produced", "agent_server", ("P2",), "conversation_runtime", _DIALOGUE_PROFILES),
    _segment("task_command", "agent.route_resolved", "agent.task_command_accepted", "agent_server", ("P3",), "voice_task_bridge", _TASK_PROFILES),
    _segment("task_command_to_presentation", "agent.task_command_accepted", "agent.presentation_produced", "agent_server", ("P2", "P3"), "cross_component_seam", _TASK_PROFILES),
    _segment("presentation_dispatch", "agent.presentation_produced", "agent.presentation_dispatched", "agent_server", ("P2", "P3"), "conversation_runtime"),
    _segment("tts_transport_open", "gateway.tts_request_received", "gateway.tts_provider_transport_open", "gateway", ("P1", "P2", "P3"), "speech_synthesis"),
    _segment("tts_open_to_first_audio", "gateway.tts_provider_transport_open", "gateway.tts_provider_first_audio", "gateway", ("P1", "P2", "P3"), "speech_synthesis"),
    _segment("tts_time_to_first_audio", "gateway.tts_request_received", "gateway.tts_provider_first_audio", "gateway", ("P1", "P2", "P3"), "speech_synthesis"),
    _segment("tts_first_audio_to_ticket", "gateway.tts_provider_first_audio", "gateway.downlink_ticket_ready", "gateway", ("P1", "P2", "P3"), "realtime_media"),
    _segment("tts_first_audio_to_first_send", "gateway.tts_provider_first_audio", "gateway.downlink_first_frame_sent", "gateway", ("P1", "P2", "P3"), "realtime_media"),
)
assert frozenset(definition.segment_id for definition in FIXED_SEGMENTS) == FIXED_SEGMENT_IDS


@dataclass(frozen=True, slots=True)
class SegmentSummary:
    segment: SegmentDefinition
    attempts: int
    successful_samples: int
    unknown: int
    failed: int
    cancelled: int
    fallback: int
    underrun: int
    rebuffer: int
    minimum_ms: float | None
    p50_ms: float | None
    p95_ms: float | None
    maximum_ms: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment.segment_id, "start_point": self.segment.start_point,
            "end_point": self.segment.end_point, "component": self.segment.component,
            "measurement_kind": self.segment.measurement_kind,
            "phase_tags": list(self.segment.phase_tags), "primary_capability": self.segment.primary_capability,
            "applicable_profiles": list(self.segment.applicable_profiles), "attempts": self.attempts,
            "successful_samples": self.successful_samples, "unknown": self.unknown, "failed": self.failed,
            "cancelled": self.cancelled, "fallback": self.fallback, "underrun": self.underrun,
            "rebuffer": self.rebuffer, "minimum_ms": self.minimum_ms, "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms, "maximum_ms": self.maximum_ms,
        }


@dataclass(frozen=True, slots=True)
class ProfileLatencyReport:
    profile_id: str
    segments: tuple[SegmentSummary, ...]

    def segment(self, segment_id: str) -> SegmentSummary:
        for summary in self.segments:
            if summary.segment.segment_id == segment_id:
                return summary
        raise KeyError(segment_id)

    def to_dict(self) -> dict[str, object]:
        return {"profile_id": self.profile_id, "segments": [item.to_dict() for item in self.segments]}


@dataclass(frozen=True, slots=True)
class LatencyRunReport:
    schema_version: str
    run: LatencyRunConfig
    profiles: tuple[ProfileLatencyReport, ...]

    @property
    def cold_or_warm(self) -> str:
        return self.run.cold_or_warm

    def profile(self, profile_id: str) -> ProfileLatencyReport:
        for profile in self.profiles:
            if profile.profile_id == profile_id:
                return profile
        raise KeyError(profile_id)

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "run": self.run.to_dict(), "profiles": [item.to_dict() for item in self.profiles]}


@dataclass(frozen=True, slots=True)
class SegmentComparison:
    profile_id: str
    segment_id: str
    baseline_p50_ms: float | None
    candidate_p50_ms: float | None
    baseline_p95_ms: float | None
    candidate_p95_ms: float | None
    p50_delta_ms: float | None
    p95_delta_ms: float | None
    p50_relative_delta: float | None
    p95_relative_delta: float | None
    baseline_attempts: int
    candidate_attempts: int
    baseline_successful_samples: int
    candidate_successful_samples: int
    count_changes: tuple[tuple[str, int], ...]
    rate_changes: tuple[tuple[str, float], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id, "segment_id": self.segment_id,
            "baseline_p50_ms": self.baseline_p50_ms, "candidate_p50_ms": self.candidate_p50_ms,
            "baseline_p95_ms": self.baseline_p95_ms, "candidate_p95_ms": self.candidate_p95_ms,
            "p50_delta_ms": self.p50_delta_ms, "p95_delta_ms": self.p95_delta_ms,
            "p50_relative_delta": self.p50_relative_delta,
            "p95_relative_delta": self.p95_relative_delta,
            "baseline_attempts": self.baseline_attempts, "candidate_attempts": self.candidate_attempts,
            "baseline_successful_samples": self.baseline_successful_samples,
            "candidate_successful_samples": self.candidate_successful_samples,
            "count_changes": dict(self.count_changes),
            "rate_changes": dict(self.rate_changes),
        }


@dataclass(frozen=True, slots=True)
class LatencyComparison:
    schema_version: str
    status: str
    reason: str | None
    baseline_run_id: str
    candidate_run_id: str
    segments: tuple[SegmentComparison, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version, "status": self.status, "reason": self.reason,
            "baseline_run_id": self.baseline_run_id, "candidate_run_id": self.candidate_run_id,
            "segments": [item.to_dict() for item in self.segments],
        }


@dataclass(frozen=True, slots=True)
class LatencyABAComparison:
    schema_version: str
    status: str
    reason: str | None
    baseline_before_run_id: str
    candidate_run_id: str
    baseline_after_run_id: str
    before_to_candidate: LatencyComparison
    after_to_candidate: LatencyComparison
    baseline_drift: tuple[SegmentComparison, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason": self.reason,
            "baseline_before_run_id": self.baseline_before_run_id,
            "candidate_run_id": self.candidate_run_id,
            "baseline_after_run_id": self.baseline_after_run_id,
            "before_to_candidate": self.before_to_candidate.to_dict(),
            "after_to_candidate": self.after_to_candidate.to_dict(),
            "baseline_drift": [item.to_dict() for item in self.baseline_drift],
        }


def _same_identity(start: LatencyMark, end: LatencyMark) -> bool:
    """Require stable producer bindings while allowing later identity enrichment."""
    required = (
        "run_id", "profile_id", "input_case_id", "round_index", "component",
        "clock_domain_id", "source_instance_id", "correlation_id", "interaction_id",
    )
    optional = (
        "activation_id", "activation_generation", "turn_id", "response_id",
        "response_generation", "task_id",
    )
    return all(getattr(start, field) == getattr(end, field) for field in required) and all(
        getattr(start, field) is None
        or getattr(end, field) == getattr(start, field)
        for field in optional
    )


def _round_identity_compatible(batches: tuple[LatencyBatch, ...]) -> bool:
    if not batches or len({batch.input_case_id for batch in batches}) != 1:
        return False
    marks = tuple(
        mark
        for batch in batches
        for mark in batch.marks
        if mark.point != "probe.capacity"
    )
    if not marks:
        return False
    if len({mark.correlation_id for mark in marks}) != 1 or len(
        {mark.interaction_id for mark in marks}
    ) != 1:
        return False
    identity_fields = (
        "activation_id",
        "activation_generation",
        "turn_id",
        "response_id",
        "response_generation",
        "task_id",
    )
    for field in identity_fields:
        values = {
            getattr(mark, field)
            for mark in marks
            if getattr(mark, field) is not None
        }
        if len(values) > 1:
            return False
    for component in {batch.component for batch in batches}:
        if len(
            {
                batch.source_instance_id
                for batch in batches
                if batch.component == component
            }
        ) != 1:
            return False
    required_by_phase = {
        "browser_round": ("activation_id", "activation_generation"),
        "gateway_stt": ("activation_id", "activation_generation"),
        "gateway_tts": ("response_id", "response_generation"),
        "agent_foreground": (
            "activation_id",
            "activation_generation",
            "turn_id",
        ),
    }
    browser_response_required_points = {
        "browser.presentation_received",
        "browser.tts_request_started",
        "browser.downlink_first_frame_received",
        "browser.playout_first_frame_scheduled",
        "browser.playout_first_frame_started_estimate",
        "browser.playout_completed",
        "browser.playout_ack_received",
        "browser.next_turn_capture_activated",
        "browser.successor_capture_requested",
        "browser.successor_capture_ready",
        "browser.downlink_attach_started",
        "browser.downlink_attached",
        "browser.playout_underrun",
        "browser.playout_rebuffer",
    }
    response_required_points = browser_response_required_points | {
        "agent.agent_started",
        "agent.agent_first_delta",
        "agent.tool_execution_started",
        "agent.tool_execution_completed",
        "agent.agent_final",
        "agent.presentation_produced",
        "agent.presentation_dispatched",
    }
    task_required_points = browser_response_required_points | {
        "agent.task_command_accepted",
        "agent.presentation_produced",
        "agent.presentation_dispatched",
    }
    for batch in batches:
        retained: dict[str, object] = {}
        ordinary = tuple(
            mark for mark in batch.marks if mark.point != "probe.capacity"
        )
        if not ordinary:
            return False
        for mark in ordinary:
            if any(
                getattr(mark, field) is None
                for field in required_by_phase[batch.phase]
            ):
                return False
            if mark.point in response_required_points and (
                mark.response_id is None or mark.response_generation is None
            ):
                return False
            if (
                batch.profile_id in {"task_create", "task_status", "task_cancel"}
                and mark.point in task_required_points
                and mark.task_id is None
            ):
                return False
            for field in identity_fields:
                value = getattr(mark, field)
                prior = retained.get(field)
                if prior is not None and value != prior:
                    return False
                if value is not None:
                    retained[field] = value
    return True


def _experiment_segments(run: LatencyRunConfig) -> tuple[SegmentDefinition, ...]:
    if run.experiment is None:
        return ()
    components = {point: component for component, points in CORE_POINTS_BY_COMPONENT.items() for point in points}
    components.update({point.point: point.component for point in run.experiment.declared_experiment_points})
    result: list[SegmentDefinition] = []
    seen: set[str] = set()
    for point in run.experiment.declared_experiment_points:
        values = (point.paired_segment_id, point.start_point, point.end_point)
        if values == (None, None, None):
            continue
        if any(value is None for value in values):
            raise LatencyProbeViolation("INVALID_EXPERIMENT_POINT")
        segment_id, start_point, end_point = values
        assert segment_id is not None and start_point is not None and end_point is not None
        if (
            segment_id in FIXED_SEGMENT_IDS or segment_id in seen
            or components.get(start_point) != point.component
            or components.get(end_point) != point.component
        ):
            raise LatencyProbeViolation("INVALID_EXPERIMENT_POINT")
        seen.add(segment_id)
        result.append(SegmentDefinition(
            segment_id, start_point, end_point, point.component, ("experiment",),
            "experiment", PROFILE_IDS,
        ))
    return tuple(result)


def _segment_definitions(run: LatencyRunConfig) -> tuple[SegmentDefinition, ...]:
    return (*FIXED_SEGMENTS, *_experiment_segments(run))


def _nearest_rank(samples: Sequence[float], percentile: int) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    index = max(0, (len(ordered) * percentile + 99) // 100 - 1)
    return ordered[index]


def _summary(
    definition: SegmentDefinition,
    groups: Iterable[
        tuple[tuple[LatencyBatch, ...], tuple[LatencyMark, ...], bool]
    ],
) -> SegmentSummary:
    attempts = successful = unknown = failed = cancelled = fallback = underrun = rebuffer = 0
    samples: list[float] = []
    for batches, marks, identity_compatible in groups:
        attempts += 1
        points = [mark for mark in marks if mark.component == definition.component]
        failed_here = any(batch.terminal_outcome == "failed" or mark.outcome == "failed" for batch in batches for mark in batch.marks)
        cancelled_here = any(batch.terminal_outcome == "cancelled" or mark.outcome == "cancelled" for batch in batches for mark in batch.marks)
        fallback_here = any(mark.outcome == "fallback" for batch in batches for mark in batch.marks)
        underrun += int(any(mark.point == "browser.playout_underrun" for mark in points))
        rebuffer += int(any(mark.point == "browser.playout_rebuffer" for mark in points))
        failed += int(failed_here)
        cancelled += int(cancelled_here)
        fallback += int(fallback_here)
        starts = [mark for mark in points if mark.point == definition.start_point]
        ends = [mark for mark in points if mark.point == definition.end_point]
        unknown_here = any(
            batch.terminal_outcome == "unknown" or mark.outcome == "unknown"
            for batch in batches for mark in batch.marks
        )
        if (
            not identity_compatible
            or failed_here
            or cancelled_here
            or fallback_here
            or unknown_here
            or len(starts) != 1
            or len(ends) != 1
        ):
            unknown += 1
            continue
        start, end = starts[0], ends[0]
        if not _same_identity(start, end) or end.monotonic_ms < start.monotonic_ms:
            unknown += 1
            continue
        samples.append(end.monotonic_ms - start.monotonic_ms)
        successful += 1
    ordered = sorted(samples)
    return SegmentSummary(
        definition, attempts, successful, unknown, failed, cancelled, fallback, underrun, rebuffer,
        ordered[0] if ordered else None, _nearest_rank(ordered, 50), _nearest_rank(ordered, 95), ordered[-1] if ordered else None,
    )


def _validated_batches(run: LatencyRunConfig, batches: Iterable[LatencyBatch]) -> tuple[LatencyBatch, ...]:
    seen: dict[tuple[str, str], bytes] = {}
    seen_slots: dict[
        tuple[str, str, str, str, int], tuple[tuple[str, str], bytes]
    ] = {}
    valid: list[LatencyBatch] = []
    for batch in batches:
        if not isinstance(batch, LatencyBatch):
            raise LatencyProbeViolation("INCOMPATIBLE_RUN")
        try:
            batch = LatencyBatch.from_dict(batch.to_dict(), run)
            encoded = batch.canonical_bytes()
        except Exception:
            raise LatencyProbeViolation("INVALID_BATCH") from None
        receipt_key = (batch.component, batch.batch_id)
        previous = seen.get(receipt_key)
        if previous is not None and previous != encoded:
            raise LatencyProbeViolation("BATCH_CONFLICT")
        if previous is not None:
            continue
        slot = (
            batch.component,
            batch.phase,
            batch.profile_id,
            batch.input_case_id,
            batch.round_index,
        )
        previous_slot = seen_slots.get(slot)
        if previous_slot is not None and previous_slot != (receipt_key, encoded):
            raise LatencyProbeViolation("BATCH_CONFLICT")
        seen[receipt_key] = encoded
        seen_slots[slot] = (receipt_key, encoded)
        valid.append(batch)
    return tuple(valid)


def reduce_latency_run(run: LatencyRunConfig, batches: Iterable[LatencyBatch]) -> LatencyRunReport:
    """Reduce one homogeneous run without treating absent evidence as zero."""
    if not isinstance(run, LatencyRunConfig) or run.schema_version not in {
        RUN_SCHEMA_VERSION_V0,
        RUN_SCHEMA_VERSION_V1,
    }:
        raise LatencyProbeViolation("INCOMPATIBLE_RUN")
    checked = _validated_batches(run, batches)
    grouped: dict[tuple[str, str, int], list[LatencyBatch]] = defaultdict(list)
    for batch in checked:
        if batch.profile_id not in run.profile_ids or batch.input_case_id not in run.input_case_ids:
            raise LatencyProbeViolation("INCOMPATIBLE_RUN")
        grouped[(batch.profile_id, batch.input_case_id, batch.round_index)].append(batch)
    profiles: list[ProfileLatencyReport] = []
    for profile_id in run.profile_ids:
        profile_groups = []
        for round_index in range(run.intended_attempts):
            items = tuple(
                batch
                for (current_profile, _, current_round), batches_for_key in sorted(
                    grouped.items()
                )
                if current_profile == profile_id and current_round == round_index
                for batch in batches_for_key
            )
            profile_groups.append(
                (
                    items,
                    tuple(mark for batch in items for mark in batch.marks),
                    _round_identity_compatible(items),
                )
            )
        summaries = tuple(
            _summary(definition, profile_groups)
            for definition in _segment_definitions(run) if profile_id in definition.applicable_profiles
        )
        profiles.append(ProfileLatencyReport(profile_id, summaries))
    return LatencyRunReport(REPORT_SCHEMA_VERSION, run, tuple(profiles))


def read_latency_batches(run_dir: Path) -> tuple[LatencyBatch, ...]:
    """Read the closed JSONL files of one run directory in deterministic order."""
    run = load_latency_run_config(Path(run_dir) / "run.json")
    result: list[LatencyBatch] = []
    for component in ("browser", "gateway", "agent_server"):
        path = Path(run_dir) / COMPONENT_OUTPUT_FILES[component]
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                if line:
                    result.append(LatencyBatch.from_dict(json.loads(line), run))
        except (OSError, UnicodeError, json.JSONDecodeError, LatencyProbeViolation):
            raise LatencyProbeViolation("INVALID_BATCH") from None
    return tuple(result)


def _csv_rows(report: LatencyRunReport) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for profile in report.profiles:
        for summary in profile.segments:
            row = {"profile_id": profile.profile_id, **summary.to_dict()}
            row["phase_tags"] = ";".join(summary.segment.phase_tags)
            row["applicable_profiles"] = ";".join(summary.segment.applicable_profiles)
            rows.append(row)
    return rows


def write_latency_report(report: LatencyRunReport, output_dir: Path) -> None:
    """Write stable JSON, CSV and a compact human inspection report."""
    if not isinstance(report, LatencyRunReport):
        raise LatencyProbeViolation("INVALID_REPORT")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    rows = _csv_rows(report)
    fieldnames = list(rows[0]) if rows else ["profile_id", "segment_id"]
    with (output / "report.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    chunks = ["# Live Voice latency report", ""]
    for profile in report.profiles:
        chunks.extend([f"## {profile.profile_id}", "", "| Segment | Measurement | Samples | p50 ms | p95 ms | Unknown |", "|---|---|---:|---:|---:|---:|"])
        for summary in profile.segments:
            chunks.append(f"| {summary.segment.segment_id} | {summary.segment.measurement_kind} | {summary.successful_samples} | {summary.p50_ms if summary.p50_ms is not None else 'unknown'} | {summary.p95_ms if summary.p95_ms is not None else 'unknown'} | {summary.unknown} |")
        chunks.extend(["", "### Waterfall", ""])
        for summary in profile.segments:
            value = "unknown" if summary.p50_ms is None else f"{summary.p50_ms:.3f} ms"
            chunks.append(
                f"{summary.segment.segment_id} [{summary.segment.measurement_kind}]: {value}"
            )
        chunks.append("")
    (output / "report.md").write_text("\n".join(chunks), encoding="utf-8")


def _rate(summary: SegmentSummary, field: str) -> float:
    return 0.0 if summary.attempts == 0 else getattr(summary, field) / summary.attempts


_COUNT_FIELDS: Final = (
    "attempts", "successful_samples", "unknown", "failed", "cancelled", "fallback",
    "underrun", "rebuffer",
)
_RATE_FIELDS: Final = ("failed", "fallback", "underrun", "rebuffer", "cancelled")


def _relative_delta(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None or baseline == 0:
        return None
    return (candidate - baseline) / baseline


def _compatible(left: LatencyRunConfig, right: LatencyRunConfig) -> bool:
    fields = (
        "schema_version", "environment_profile", "browser_family_and_version", "browser_os_class",
        "gateway_runtime_class", "agent_runtime_class", "stt_provider_and_model", "tts_provider_and_model",
        "audio_format", "vad_configuration", "playout_configuration", "allowlisted_feature_flags",
        "cold_or_warm", "input_case_ids", "profile_ids", "intended_attempts", "required_successes",
        "optimization_track", "benchmark_lane", "fixture_profile_id",
    )
    return all(getattr(left, field) == getattr(right, field) for field in fields)


def _catalog(run: LatencyRunConfig) -> tuple[tuple[object, ...], ...]:
    """Return every fixed and declared experiment definition for comparison."""
    return tuple(
        (
            definition.segment_id, definition.start_point, definition.end_point,
            definition.component, definition.phase_tags, definition.primary_capability,
            definition.applicable_profiles,
        )
        for definition in _segment_definitions(run)
    )


def _comparison_rows(baseline: LatencyRunReport, candidate: LatencyRunReport) -> tuple[SegmentComparison, ...]:
    rows: list[SegmentComparison] = []
    for profile in baseline.profiles:
        candidate_profile = candidate.profile(profile.profile_id)
        for base in profile.segments:
            current = candidate_profile.segment(base.segment.segment_id)
            rates = tuple((field, _rate(current, field) - _rate(base, field)) for field in _RATE_FIELDS)
            counts = tuple((field, getattr(current, field) - getattr(base, field)) for field in _COUNT_FIELDS)
            rows.append(SegmentComparison(
                profile.profile_id, base.segment.segment_id, base.p50_ms, current.p50_ms, base.p95_ms, current.p95_ms,
                None if base.p50_ms is None or current.p50_ms is None else current.p50_ms - base.p50_ms,
                None if base.p95_ms is None or current.p95_ms is None else current.p95_ms - base.p95_ms,
                _relative_delta(base.p50_ms, current.p50_ms), _relative_delta(base.p95_ms, current.p95_ms),
                base.attempts, current.attempts, base.successful_samples, current.successful_samples, counts, rates,
            ))
    return tuple(rows)


def _inconclusive(baseline: LatencyRunReport, candidate: LatencyRunReport, rows: tuple[SegmentComparison, ...], reason: str) -> LatencyComparison:
    return LatencyComparison(COMPARISON_SCHEMA_VERSION, "inconclusive", reason, baseline.run.run_id, candidate.run.run_id, rows)


def _statistic_delta(item: SegmentComparison, statistic: str) -> float | None:
    return item.p50_delta_ms if statistic == "p50_ms" else item.p95_delta_ms


def _statistic_relative_delta(item: SegmentComparison, statistic: str) -> float | None:
    return item.p50_relative_delta if statistic == "p50_ms" else item.p95_relative_delta


def compare_latency_reports(baseline: LatencyRunReport, candidate: LatencyRunReport) -> LatencyComparison:
    if not isinstance(baseline, LatencyRunReport) or not isinstance(candidate, LatencyRunReport):
        raise LatencyProbeViolation("INVALID_REPORT")
    empty_rows: tuple[SegmentComparison, ...] = ()
    if (
        baseline.run.source_state == "product_code_dirty"
        or candidate.run.source_state == "product_code_dirty"
        or (
            candidate.run.optimization_track == "post_capture_pipeline"
            and (
                baseline.run.source_state != "clean"
                or candidate.run.source_state != "clean"
            )
        )
    ):
        return _inconclusive(baseline, candidate, empty_rows, "DIRTY_SOURCE")
    if candidate.run.experiment is None:
        return _inconclusive(baseline, candidate, empty_rows, "NO_EXPERIMENT")
    if not _compatible(baseline.run, candidate.run):
        return _inconclusive(baseline, candidate, empty_rows, "INCOMPATIBLE_RUN")
    experiment = candidate.run.experiment
    if (
        candidate.run.optimization_track == "post_capture_pipeline"
        and experiment.target_segment not in POST_CAPTURE_TARGET_SEGMENTS
    ):
        return _inconclusive(
            baseline, candidate, empty_rows, "INVALID_TARGET_SEGMENT"
        )
    if _catalog(baseline.run) != _catalog(candidate.run):
        return _inconclusive(baseline, candidate, empty_rows, "INCOMPATIBLE_RUN")
    rows = _comparison_rows(baseline, candidate)
    statistic = experiment.target_statistic
    if any(
        item.baseline_successful_samples < baseline.run.required_successes
        or item.candidate_successful_samples < candidate.run.required_successes
        or _statistic_delta(item, statistic) is None
        for item in rows
    ):
        return _inconclusive(baseline, candidate, rows, "INSUFFICIENT_SAMPLES")
    target = tuple(item for item in rows if item.segment_id == experiment.target_segment)
    total = tuple(item for item in rows if item.segment_id == "response_total")
    if not target or not total or any(_statistic_delta(item, statistic) is None for item in (*target, *total)):
        return _inconclusive(baseline, candidate, rows, "UNKNOWN_SEGMENT")
    if any(
        _statistic_relative_delta(item, statistic) is None
        for item in (*target, *total)
    ):
        return _inconclusive(baseline, candidate, rows, "ZERO_BASELINE")
    target_gain = min(-_statistic_delta(item, statistic) for item in target if _statistic_delta(item, statistic) is not None)
    total_gain = min(-_statistic_delta(item, statistic) for item in total if _statistic_delta(item, statistic) is not None)
    guardrail_failed = False
    for guardrail in experiment.guardrails:
        for item in rows:
            if guardrail.segment_id is not None and item.segment_id != guardrail.segment_id:
                continue
            if guardrail.metric == "p50_ms":
                change = item.p50_delta_ms
            elif guardrail.metric == "p95_ms":
                change = item.p95_delta_ms
            else:
                name = {"failure_rate": "failed", "fallback_rate": "fallback", "underrun_rate": "underrun", "rebuffer_rate": "rebuffer", "cancellation_rate": "cancelled"}[guardrail.metric]
                change = dict(item.rate_changes)[name]
            guardrail_failed = guardrail_failed or change is None or change > guardrail.maximum_regression
    if total_gain < 0 or guardrail_failed:
        status = "regressed"
    elif target_gain >= experiment.minimum_improvement_ms and total_gain >= experiment.response_total_minimum_improvement_ms:
        status = "improved"
    elif target_gain > 0 and any(item.segment_id != "response_total" and item.segment_id in {definition.segment_id for definition in FIXED_SEGMENTS if definition.component == "browser"} and (_statistic_delta(item, statistic) or 0) > 0 for item in rows):
        status = "shifted"
    else:
        status = "inconclusive"
    return LatencyComparison(COMPARISON_SCHEMA_VERSION, status, None, baseline.run.run_id, candidate.run.run_id, rows)


def compare_latency_reports_a_b_a(
    baseline_before: LatencyRunReport,
    candidate: LatencyRunReport,
    baseline_after: LatencyRunReport,
) -> LatencyABAComparison:
    before = compare_latency_reports(baseline_before, candidate)
    after = compare_latency_reports(baseline_after, candidate)
    source_reason: str | None = None
    if baseline_before.run.git_commit != baseline_after.run.git_commit:
        source_reason = "BASELINE_SOURCE_MISMATCH"
    elif candidate.run.git_commit == baseline_before.run.git_commit:
        source_reason = "CANDIDATE_SOURCE_NOT_DISTINCT"
    if source_reason is not None:
        return LatencyABAComparison(
            ABA_COMPARISON_SCHEMA_VERSION,
            "inconclusive",
            source_reason,
            baseline_before.run.run_id,
            candidate.run.run_id,
            baseline_after.run.run_id,
            before,
            after,
            (),
        )
    drift = (
        _comparison_rows(baseline_before, baseline_after)
        if _compatible(baseline_before.run, baseline_after.run)
        and _catalog(baseline_before.run) == _catalog(baseline_after.run)
        else ()
    )
    status = "inconclusive"
    reason: str | None = None
    if before.status == "regressed" or after.status == "regressed":
        status = "regressed"
        reason = "PAIRWISE_REGRESSION"
    elif before.status != "improved" or after.status != "improved":
        reason = before.reason or after.reason or "PAIRWISE_INCONCLUSIVE"
    elif candidate.run.experiment is None or not drift:
        reason = "INCOMPATIBLE_RUN"
    else:
        statistic = candidate.run.experiment.target_statistic
        relevant_segments = {
            candidate.run.experiment.target_segment,
            "response_total",
        }
        before_rows = tuple(
            row for row in before.segments if row.segment_id in relevant_segments
        )
        after_rows = tuple(
            row for row in after.segments if row.segment_id in relevant_segments
        )
        drift_rows = tuple(
            row for row in drift if row.segment_id in relevant_segments
        )
        before_gains = tuple(
            -value
            for row in before_rows
            if (value := _statistic_delta(row, statistic)) is not None
        )
        after_gains = tuple(
            -value
            for row in after_rows
            if (value := _statistic_delta(row, statistic)) is not None
        )
        drift_values = tuple(
            abs(value)
            for row in drift_rows
            if (value := _statistic_delta(row, statistic)) is not None
        )
        expected_count = len(relevant_segments) * len(candidate.run.profile_ids)
        denominator_drift = any(
            row.baseline_attempts != row.candidate_attempts
            or any(value != 0 for _, value in row.count_changes)
            or any(value != 0 for _, value in row.rate_changes)
            for row in drift_rows
        )
        if denominator_drift:
            reason = "BASELINE_DRIFT"
        elif (
            len(before_gains) != expected_count
            or len(after_gains) != expected_count
            or len(drift_values) != expected_count
        ):
            reason = "BASELINE_DRIFT_UNKNOWN"
        elif max(drift_values) >= min(*before_gains, *after_gains):
            reason = "BASELINE_DRIFT"
        else:
            status = "improved"
    return LatencyABAComparison(
        ABA_COMPARISON_SCHEMA_VERSION,
        status,
        reason,
        baseline_before.run.run_id,
        candidate.run.run_id,
        baseline_after.run.run_id,
        before,
        after,
        drift,
    )


_REPORT_KEYS: Final = frozenset({"schema_version", "run", "profiles"})
_PROFILE_REPORT_KEYS: Final = frozenset({"profile_id", "segments"})
_SEGMENT_REPORT_KEYS: Final = frozenset({
    "segment_id", "start_point", "end_point", "component", "measurement_kind", "phase_tags",
    "primary_capability", "applicable_profiles", "attempts", "successful_samples",
    "unknown", "failed", "cancelled", "fallback", "underrun", "rebuffer",
    "minimum_ms", "p50_ms", "p95_ms", "maximum_ms",
})
_SUMMARY_COUNT_FIELDS: Final = (
    "attempts", "successful_samples", "unknown", "failed", "cancelled", "fallback",
    "underrun", "rebuffer",
)
_SUMMARY_VALUE_FIELDS: Final = ("minimum_ms", "p50_ms", "p95_ms", "maximum_ms")


def _exact_mapping(value: object, keys: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError
    return value


def _report_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError
    return value


def _report_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError
    return number


def _parse_summary(
    value: object,
    definition: SegmentDefinition,
    intended_attempts: int,
) -> SegmentSummary:
    raw = _exact_mapping(value, _SEGMENT_REPORT_KEYS)
    expected = {
        "segment_id": definition.segment_id, "start_point": definition.start_point,
        "end_point": definition.end_point, "component": definition.component,
        "measurement_kind": definition.measurement_kind,
        "phase_tags": list(definition.phase_tags), "primary_capability": definition.primary_capability,
        "applicable_profiles": list(definition.applicable_profiles),
    }
    if any(raw[key] != expected_value for key, expected_value in expected.items()):
        raise ValueError
    counts = tuple(_report_count(raw[field]) for field in _SUMMARY_COUNT_FIELDS)
    attempts, successful, unknown, failed, cancelled, fallback, underrun, rebuffer = counts
    if (
        attempts != intended_attempts
        or any(value > attempts for value in counts[1:])
        or successful + unknown != attempts
    ):
        raise ValueError
    values = tuple(raw[field] for field in _SUMMARY_VALUE_FIELDS)
    if successful == 0:
        if any(value is not None for value in values):
            raise ValueError
        parsed_values: tuple[float | None, ...] = (None, None, None, None)
    else:
        if any(value is None for value in values):
            raise ValueError
        parsed_values = tuple(_report_number(value) for value in values)
        minimum, p50, p95, maximum = parsed_values
        assert minimum is not None and p50 is not None and p95 is not None and maximum is not None
        if not minimum <= p50 <= p95 <= maximum:
            raise ValueError
    return SegmentSummary(definition, attempts, successful, unknown, failed, cancelled, fallback, underrun, rebuffer, *parsed_values)


def _load_report(path: Path) -> LatencyRunReport:
    try:
        raw = _exact_mapping(json.loads(Path(path).read_text(encoding="utf-8")), _REPORT_KEYS)
        if raw["schema_version"] != REPORT_SCHEMA_VERSION or not isinstance(raw["profiles"], list):
            raise ValueError
        run = _parse_latency_run_config(raw["run"])
        definitions = _segment_definitions(run)
        expected_by_profile = {
            profile_id: tuple(item for item in definitions if profile_id in item.applicable_profiles)
            for profile_id in run.profile_ids
        }
        if len(raw["profiles"]) != len(run.profile_ids):
            raise ValueError
        profiles: list[ProfileLatencyReport] = []
        seen_profiles: set[str] = set()
        for profile_raw in raw["profiles"]:
            profile = _exact_mapping(profile_raw, _PROFILE_REPORT_KEYS)
            profile_id = profile["profile_id"]
            if not isinstance(profile_id, str) or profile_id in seen_profiles or profile_id not in expected_by_profile:
                raise ValueError
            seen_profiles.add(profile_id)
            segments_raw = profile["segments"]
            expected_segments = expected_by_profile[profile_id]
            if not isinstance(segments_raw, list) or len(segments_raw) != len(expected_segments):
                raise ValueError
            summaries = tuple(
                _parse_summary(item, definition, run.intended_attempts)
                for item, definition in zip(
                    segments_raw,
                    expected_segments,
                    strict=True,
                )
            )
            profiles.append(ProfileLatencyReport(profile_id, summaries))
        if tuple(item.profile_id for item in profiles) != run.profile_ids:
            raise ValueError
        return LatencyRunReport(REPORT_SCHEMA_VERSION, run, tuple(profiles))
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, OverflowError, LatencyProbeViolation):
        raise LatencyProbeViolation("INVALID_REPORT") from None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="latency_probe_report")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-run")
    validate.add_argument("--run-json", type=Path, required=True)
    report = commands.add_parser("report")
    report.add_argument("--run-dir", type=Path, required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    aba = commands.add_parser("compare-a-b-a")
    aba.add_argument("--baseline-before", type=Path, required=True)
    aba.add_argument("--candidate", type=Path, required=True)
    aba.add_argument("--baseline-after", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-run":
            load_latency_run_config(args.run_json)
            return 0
        if args.command == "report":
            run = load_latency_run_config(args.run_dir / "run.json")
            result = reduce_latency_run(run, read_latency_batches(args.run_dir))
            write_latency_report(result, args.run_dir)
            return 0
        if args.command == "compare-a-b-a":
            result = compare_latency_reports_a_b_a(
                _load_report(args.baseline_before),
                _load_report(args.candidate),
                _load_report(args.baseline_after),
            )
        else:
            result = compare_latency_reports(
                _load_report(args.baseline), _load_report(args.candidate)
            )
        print(json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":")))
        # An inconclusive comparison is a valid, truthful report outcome; only
        # malformed input or I/O failure makes the command itself fail.
        return 0
    except (OSError, LatencyProbeViolation):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
