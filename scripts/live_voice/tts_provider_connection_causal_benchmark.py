#!/usr/bin/env python3
"""No-Browser causal benchmark for streaming-TTS Provider connections."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, TypeVar

import httpcore
import httpx

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.batch_speech import (
    SPEECH_API_BASE_ENV,
    SPEECH_API_KEY_ENV,
    SPEECH_PROVIDER_ENV,
    SPEECH_TTS_MODEL_ENV,
    SPEECH_TTS_VOICE_ENV,
)
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    OpenAIStreamingSpeechConfig,
    OpenAIStreamingSpeechProvider,
    SynthesisTransportEventName,
    SynthesisTransportObserver,
)
from jiuwenswarm.server.live_voice.speech_ports import SynthesisEventKind
from jiuwenswarm.server.live_voice.streaming_speech import (
    StreamingSpeechConformance,
    StreamingSynthesisEvent,
    SynthesisStreamRef,
    SynthesisStreamRequest,
    TextSpan,
)


REPORT_SCHEMA_VERSION = "live-voice.tts-provider-connection-causal-report.v0"
_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
EVENT_TIMEOUT_SECONDS = 20.0
OPERATION_TIMEOUT_SECONDS = 30.0
CLOSE_TIMEOUT_SECONDS = 5.0
PROCESS_WATCHDOG_SECONDS = 240.0
_FIXED_TEXT = "Please read this short sentence clearly."
MAX_REPORT_BYTES = 1_048_576
FORBIDDEN_EFFECTS = {
    "agent_submissions": 0,
    "tool_executions": 0,
    "task_mutations": 0,
    "history_writes": 0,
    "browser_effects": 0,
    "stt_requests": 0,
    "vad_requests": 0,
    "fallbacks": 0,
    "retries": 0,
    "report_overwrites": 0,
    "text_persisted": 0,
    "pcm_persisted": 0,
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_WORKER_FLAG = "--benchmark-worker"
_WORKER_TOKEN_ENV = "JIUWENSWARM_TTS_BENCHMARK_WORKER_TOKEN"
_BoundedValue = TypeVar("_BoundedValue")
_RETAINED_BOUNDED_TASKS: set[asyncio.Future[object]] = set()


@dataclass(frozen=True, slots=True)
class _ProcessWatchdogResult:
    returncode: int | None
    stdout: str
    timed_out: bool


def _run_process_with_watchdog(
    command: tuple[str, ...],
    *,
    environ: Mapping[str, str],
    timeout_seconds: float,
) -> _ProcessWatchdogResult:
    if (
        not command
        or not all(type(part) is str and part for part in command)
        or not isinstance(environ, Mapping)
        or isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("TTS_CONNECTION_BENCHMARK_PROCESS_INVALID")
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=dict(environ),
            timeout=float(timeout_seconds),
        )
    except subprocess.TimeoutExpired:
        return _ProcessWatchdogResult(None, "", True)
    return _ProcessWatchdogResult(
        completed.returncode,
        completed.stdout if completed.returncode == 0 else "",
        False,
    )


def _release_bounded_task(task: asyncio.Future[object]) -> None:
    _RETAINED_BOUNDED_TASKS.discard(task)
    if task.cancelled():
        return
    try:
        task.exception()
    except BaseException:
        return


async def _hard_bounded(
    awaitable: Awaitable[_BoundedValue], *, timeout_seconds: float
) -> _BoundedValue:
    task = asyncio.ensure_future(awaitable)
    try:
        done, _pending = await asyncio.wait((task,), timeout=timeout_seconds)
    except BaseException:
        task.cancel()
        _RETAINED_BOUNDED_TASKS.add(task)
        task.add_done_callback(_release_bounded_task)
        raise
    if task not in done:
        task.cancel()
        _RETAINED_BOUNDED_TASKS.add(task)
        task.add_done_callback(_release_bounded_task)
        raise TimeoutError from None
    return task.result()


def _has_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


@dataclass(frozen=True, slots=True)
class TtsConnectionBenchmarkConfig:
    run_id: str
    mode: str
    output_path: Path
    git_commit: str
    source_clean: bool
    source_label: str
    model: str
    voice: str
    output_rate_hz: int

    def __post_init__(self) -> None:
        if (
            type(self.run_id) is not str
            or not _RUN_ID.fullmatch(self.run_id)
            or self.mode not in {"pilot", "run"}
            or not isinstance(self.output_path, Path)
            or not self.output_path.is_absolute()
            or _has_control(str(self.output_path))
            or self.output_path.exists()
            or type(self.git_commit) is not str
            or not _GIT_SHA.fullmatch(self.git_commit)
            or self.source_clean is not True
            or type(self.source_label) is not str
            or self.source_label not in {"A1", "B", "A2"}
            or (self.mode == "pilot" and self.source_label != "A1")
            or type(self.model) is not str
            or not _SAFE_LABEL.fullmatch(self.model)
            or type(self.voice) is not str
            or not _SAFE_LABEL.fullmatch(self.voice)
            or self.output_rate_hz != 24_000
        ):
            raise ValueError("TTS_CONNECTION_BENCHMARK_CONFIG_INVALID")

    @property
    def pair_count(self) -> int:
        return 1 if self.mode == "pilot" else 3

    @property
    def expected_attempt_count(self) -> int:
        return self.pair_count * 2


class TtsAttemptOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class TtsAttemptPosition(StrEnum):
    COLD = "cold"
    WARM = "warm"


@dataclass(frozen=True, slots=True)
class TtsConnectionAttempt:
    pair_index: int
    position: TtsAttemptPosition
    outcome: TtsAttemptOutcome
    reason: str | None
    connection_reused: bool | None
    request_started_ms: float
    tcp_connect_started_ms: float | None
    tcp_connect_completed_ms: float | None
    tls_started_ms: float | None
    tls_completed_ms: float | None
    response_headers_ms: float | None
    transport_open_ms: float | None
    first_audio_event_ms: float | None
    first_pcm_ms: float | None
    completed_ms: float | None
    stream_closed_ms: float | None

    def __post_init__(self) -> None:
        metrics = (
            self.request_started_ms,
            self.tcp_connect_started_ms,
            self.tcp_connect_completed_ms,
            self.tls_started_ms,
            self.tls_completed_ms,
            self.response_headers_ms,
            self.transport_open_ms,
            self.first_audio_event_ms,
            self.first_pcm_ms,
            self.completed_ms,
            self.stream_closed_ms,
        )
        completed = self.outcome is TtsAttemptOutcome.COMPLETED
        required = (
            self.response_headers_ms,
            self.transport_open_ms,
            self.first_audio_event_ms,
            self.first_pcm_ms,
            self.completed_ms,
            self.stream_closed_ms,
        )
        if (
            type(self.pair_index) is not int
            or not 0 <= self.pair_index < 3
            or not isinstance(self.position, TtsAttemptPosition)
            or not isinstance(self.outcome, TtsAttemptOutcome)
            or self.request_started_ms != 0.0
            or any(
                value is not None
                and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                )
                for value in metrics
            )
            or (self.tcp_connect_started_ms is None)
            != (self.tcp_connect_completed_ms is None)
            or (self.tls_started_ms is None) != (self.tls_completed_ms is None)
        ):
            raise ValueError("TTS_CONNECTION_ATTEMPT_INVALID")
        if not completed:
            if (
                type(self.reason) is not str
                or not _SAFE_LABEL.fullmatch(self.reason)
                or self.connection_reused is not None
                or any(value is not None for value in metrics[1:])
            ):
                raise ValueError("TTS_CONNECTION_ATTEMPT_INVALID")
            return
        if self.reason is not None or any(value is None for value in required):
            raise ValueError("TTS_CONNECTION_ATTEMPT_INVALID")
        fresh_connection = (
            self.tcp_connect_started_ms is not None and self.tls_started_ms is not None
        )
        reused_connection = (
            self.tcp_connect_started_ms is None and self.tls_started_ms is None
        )
        if (
            self.connection_reused is not reused_connection
            or not (fresh_connection or reused_connection)
            or (self.position is TtsAttemptPosition.COLD and reused_connection)
        ):
            raise ValueError("TTS_CONNECTION_ATTEMPT_INVALID")
        ordered = [value for value in metrics if value is not None]
        if ordered != sorted(ordered):
            raise ValueError("TTS_CONNECTION_ATTEMPT_INVALID")

    @classmethod
    def failed(
        cls,
        *,
        pair_index: int,
        position: TtsAttemptPosition,
        outcome: TtsAttemptOutcome,
        reason: str,
    ) -> TtsConnectionAttempt:
        if outcome is TtsAttemptOutcome.COMPLETED:
            raise ValueError("TTS_CONNECTION_ATTEMPT_INVALID")
        return cls(
            pair_index,
            position,
            outcome,
            reason,
            None,
            0.0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )


class TtsBenchmarkProvider(Protocol):
    conformance: StreamingSpeechConformance
    cleanup_snapshot: object

    async def open_synthesis(
        self,
        request: SynthesisStreamRequest,
        *,
        on_transport_open: Callable[[], None] | None = None,
    ) -> None: ...

    async def next_synthesis_event(
        self, ref: SynthesisStreamRef, *, timeout_seconds: float
    ) -> StreamingSynthesisEvent: ...

    async def close(self) -> None: ...


ProviderFactory = Callable[[SynthesisTransportObserver], TtsBenchmarkProvider]


@dataclass(slots=True)
class _AttemptTrace:
    ref: SynthesisStreamRef
    started_at: float
    events: dict[str, float]
    invalid: bool = False

    def observe(
        self,
        ref: SynthesisStreamRef,
        name: SynthesisTransportEventName,
        observed_at: float,
    ) -> None:
        if (
            ref != self.ref
            or name in self.events
            or isinstance(observed_at, bool)
            or not isinstance(observed_at, (int, float))
            or not math.isfinite(observed_at)
            or observed_at < self.started_at
        ):
            self.invalid = True
            return
        self.events[name] = float(observed_at)

    def offset(self, name: str) -> float | None:
        observed = self.events.get(name)
        if observed is None:
            return None
        return max(0.0, (observed - self.started_at) * 1000)


def _synthesis_request(pair_index: int, generation: int) -> SynthesisStreamRequest:
    response = ResponseRef(
        f"tts-benchmark-interaction-{pair_index}",
        f"tts-benchmark-response-{pair_index}-{generation}",
        generation,
    )
    return SynthesisStreamRequest(
        ref=SynthesisStreamRef(
            f"tts-benchmark-stream-{pair_index}",
            generation,
            response,
            f"tts-benchmark-unit-{pair_index}-{generation}",
            0,
        ),
        display_text=_FIXED_TEXT,
        spoken_text=_FIXED_TEXT,
        display_span=TextSpan(0, len(_FIXED_TEXT)),
        sample_rate_hz=24_000,
        event_timeout_seconds=EVENT_TIMEOUT_SECONDS,
    )


def _completed_attempt(
    *,
    pair_index: int,
    position: TtsAttemptPosition,
    trace: _AttemptTrace,
    first_pcm_at: float | None,
    completed_at: float,
) -> TtsConnectionAttempt:
    required_trace = {
        "send_request_headers.started",
        "receive_response_headers.complete",
        "first_audio_event",
    }
    has_tcp = {
        "connect_tcp.started",
        "connect_tcp.complete",
    }.issubset(trace.events)
    has_tls = {"start_tls.started", "start_tls.complete"}.issubset(trace.events)
    no_tcp = not {
        "connect_tcp.started",
        "connect_tcp.complete",
    }.intersection(trace.events)
    no_tls = not {"start_tls.started", "start_tls.complete"}.intersection(
        trace.events
    )
    if (
        trace.invalid
        or not required_trace.issubset(trace.events)
        or first_pcm_at is None
        or "transport_open" not in trace.events
        or not ((has_tcp and has_tls) or (no_tcp and no_tls))
        or (position is TtsAttemptPosition.COLD and no_tcp)
    ):
        return TtsConnectionAttempt.failed(
            pair_index=pair_index,
            position=position,
            outcome=TtsAttemptOutcome.INVALID,
            reason="TRACE_REUSE_UNPROVEN",
        )
    connection_reused = no_tcp and no_tls
    completed_offset = max(0.0, (completed_at - trace.started_at) * 1000)
    return TtsConnectionAttempt(
        pair_index,
        position,
        TtsAttemptOutcome.COMPLETED,
        None,
        connection_reused,
        0.0,
        trace.offset("connect_tcp.started"),
        trace.offset("connect_tcp.complete"),
        trace.offset("start_tls.started"),
        trace.offset("start_tls.complete"),
        trace.offset("receive_response_headers.complete"),
        trace.offset("transport_open"),
        trace.offset("first_audio_event"),
        max(0.0, (first_pcm_at - trace.started_at) * 1000),
        completed_offset,
        completed_offset,
    )


async def _run_provider_attempt(
    provider: TtsBenchmarkProvider,
    *,
    pair_index: int,
    position: TtsAttemptPosition,
    generation: int,
    trace: _AttemptTrace,
    monotonic: Callable[[], float],
) -> TtsConnectionAttempt:
    request = _synthesis_request(pair_index, generation)
    if request.ref != trace.ref:
        raise ValueError("TTS_CONNECTION_BENCHMARK_INFRASTRUCTURE_INVALID")
    first_pcm_at: float | None = None
    started = False
    completed = False

    def on_transport_open() -> None:
        observed_at = monotonic()
        if "transport_open" in trace.events or observed_at < trace.started_at:
            trace.invalid = True
            return
        trace.events["transport_open"] = observed_at

    try:
        provider.conformance.activate_response(request.ref.response)
        await _hard_bounded(
            provider.open_synthesis(
                request, on_transport_open=on_transport_open
            ),
            timeout_seconds=OPERATION_TIMEOUT_SECONDS,
        )
        expected_seq = 0
        while not completed:
            event = await _hard_bounded(
                provider.next_synthesis_event(
                    request.ref, timeout_seconds=EVENT_TIMEOUT_SECONDS
                ),
                timeout_seconds=OPERATION_TIMEOUT_SECONDS,
            )
            if event.ref != request.ref or event.seq != expected_seq:
                raise ValueError("PROVIDER_PROTOCOL")
            expected_seq += 1
            if event.kind is SynthesisEventKind.STARTED:
                if started or first_pcm_at is not None:
                    raise ValueError("PROVIDER_PROTOCOL")
                started = True
            elif event.kind is SynthesisEventKind.CHUNK:
                if not started or event.pcm_s16le is None or event.sample_count <= 0:
                    raise ValueError("PROVIDER_PROTOCOL")
                if first_pcm_at is None:
                    first_pcm_at = monotonic()
            elif event.kind is SynthesisEventKind.COMPLETED:
                if not started or first_pcm_at is None:
                    raise ValueError("PROVIDER_PROTOCOL")
                completed = True
            else:
                raise ValueError("PROVIDER_PROTOCOL")
        return _completed_attempt(
            pair_index=pair_index,
            position=position,
            trace=trace,
            first_pcm_at=first_pcm_at,
            completed_at=monotonic(),
        )
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except asyncio.CancelledError:
        raise
    except (TimeoutError, asyncio.TimeoutError):
        return TtsConnectionAttempt.failed(
            pair_index=pair_index,
            position=position,
            outcome=TtsAttemptOutcome.UNKNOWN,
            reason="TIMEOUT",
        )
    except Exception:
        return TtsConnectionAttempt.failed(
            pair_index=pair_index,
            position=position,
            outcome=TtsAttemptOutcome.FAILED,
            reason="PROVIDER_FAILED",
        )
    finally:
        request = None  # type: ignore[assignment]


async def run_provider_pair(
    config: TtsConnectionBenchmarkConfig,
    *,
    pair_index: int,
    provider_factory: ProviderFactory,
    monotonic: Callable[[], float] = time.monotonic,
) -> tuple[tuple[TtsConnectionAttempt, ...], bool]:
    if (
        not isinstance(config, TtsConnectionBenchmarkConfig)
        or type(pair_index) is not int
        or not 0 <= pair_index < config.pair_count
        or not callable(provider_factory)
        or not callable(monotonic)
    ):
        raise ValueError("TTS_CONNECTION_BENCHMARK_INFRASTRUCTURE_INVALID")
    traces: dict[SynthesisStreamRef, _AttemptTrace] = {}

    def observer(
        ref: SynthesisStreamRef,
        name: SynthesisTransportEventName,
        observed_at: float,
    ) -> None:
        trace = traces.get(ref)
        if trace is not None:
            trace.observe(ref, name, observed_at)

    provider = provider_factory(observer)
    attempts: list[TtsConnectionAttempt] = []
    cleanup_complete = False
    try:
        for generation, position in enumerate(
            (TtsAttemptPosition.COLD, TtsAttemptPosition.WARM)
        ):
            request = _synthesis_request(pair_index, generation)
            trace = _AttemptTrace(request.ref, monotonic(), {})
            traces[request.ref] = trace
            attempt = await _run_provider_attempt(
                provider,
                pair_index=pair_index,
                position=position,
                generation=generation,
                trace=trace,
                monotonic=monotonic,
            )
            attempts.append(attempt)
            if attempt.outcome is not TtsAttemptOutcome.COMPLETED:
                if position is TtsAttemptPosition.COLD:
                    attempts.append(
                        TtsConnectionAttempt.failed(
                            pair_index=pair_index,
                            position=TtsAttemptPosition.WARM,
                            outcome=TtsAttemptOutcome.UNKNOWN,
                            reason="PAIR_ABORTED",
                        )
                    )
                break
    finally:
        try:
            await _hard_bounded(
                provider.close(), timeout_seconds=CLOSE_TIMEOUT_SECONDS
            )
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except asyncio.CancelledError:
            raise
        except Exception:
            cleanup_complete = False
        else:
            cleanup_complete = bool(
                getattr(provider.cleanup_snapshot, "clean", False)
            )
    return tuple(attempts), cleanup_complete


@dataclass(frozen=True, slots=True)
class TtsPositionSummary:
    position: TtsAttemptPosition
    attempts: int
    completed: int
    failed: int
    invalid: int
    unknown: int
    response_headers_ms_p50: float | None
    response_headers_ms_p95: float | None
    transport_open_ms_p50: float | None
    transport_open_ms_p95: float | None
    first_audio_event_ms_p50: float | None
    first_audio_event_ms_p95: float | None
    first_pcm_ms_p50: float | None
    first_pcm_ms_p95: float | None
    completed_ms_p50: float | None
    completed_ms_p95: float | None
    stream_closed_ms_p50: float | None
    stream_closed_ms_p95: float | None


@dataclass(frozen=True, slots=True)
class TtsConnectionCausalReport:
    schema_version: str
    run_id: str
    mode: str
    git_commit: str
    source_clean: bool
    source_label: str
    provider_id: str
    provider_class: str
    model: str
    voice: str
    output_rate_hz: int
    python_version: str
    httpx_version: str
    httpcore_version: str
    decision: str
    attempts: tuple[TtsConnectionAttempt, ...]
    summaries: tuple[TtsPositionSummary, ...]
    cleanup_counts: Mapping[str, int]
    forbidden_effects: Mapping[str, int]


def _nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _metric_summary(
    rows: list[TtsConnectionAttempt], name: str
) -> tuple[float | None, float | None]:
    values = [
        float(value)
        for row in rows
        if row.outcome is TtsAttemptOutcome.COMPLETED
        and (value := getattr(row, name)) is not None
    ]
    return (
        statistics.median(values) if values else None,
        _nearest_rank(values, 0.95),
    )


def _summaries(
    attempts: tuple[TtsConnectionAttempt, ...],
) -> tuple[TtsPositionSummary, ...]:
    summaries = []
    for position in (TtsAttemptPosition.COLD, TtsAttemptPosition.WARM):
        rows = [row for row in attempts if row.position is position]
        values: list[float | None] = []
        for name in (
            "response_headers_ms",
            "transport_open_ms",
            "first_audio_event_ms",
            "first_pcm_ms",
            "completed_ms",
            "stream_closed_ms",
        ):
            values.extend(_metric_summary(rows, name))
        summaries.append(
            TtsPositionSummary(
                position,
                len(rows),
                sum(row.outcome is TtsAttemptOutcome.COMPLETED for row in rows),
                sum(row.outcome is TtsAttemptOutcome.FAILED for row in rows),
                sum(row.outcome is TtsAttemptOutcome.INVALID for row in rows),
                sum(row.outcome is TtsAttemptOutcome.UNKNOWN for row in rows),
                *values,
            )
        )
    return tuple(summaries)


def _safe_report_label(value: str) -> bool:
    return type(value) is str and bool(_SAFE_LABEL.fullmatch(value))


def _expected_decision(
    *,
    mode: str,
    source_label: str,
    attempts: tuple[TtsConnectionAttempt, ...],
    cleanup_completed: int,
    expected_pairs: int,
) -> str:
    if (
        len(attempts) != expected_pairs * 2
        or any(row.outcome is not TtsAttemptOutcome.COMPLETED for row in attempts)
        or cleanup_completed != expected_pairs
    ):
        return "INCONCLUSIVE"
    if source_label == "B":
        expected_reuse = {
            TtsAttemptPosition.COLD: False,
            TtsAttemptPosition.WARM: True,
        }
        if any(
            row.connection_reused is not expected_reuse[row.position]
            for row in attempts
        ):
            return "INCONCLUSIVE"
    elif any(row.connection_reused is not False for row in attempts):
        return "INCONCLUSIVE"
    if mode == "pilot":
        return "PILOT_VALID"
    return "CANDIDATE_VALID" if source_label == "B" else "CONTROL_VALID"


def _validate_report(report: TtsConnectionCausalReport) -> None:
    attempt_slots = {(row.pair_index, row.position) for row in report.attempts}
    expected_pairs = 1 if report.mode == "pilot" else 3
    expected_slots = {
        (pair_index, position)
        for pair_index in range(expected_pairs)
        for position in (TtsAttemptPosition.COLD, TtsAttemptPosition.WARM)
    }
    cleanup = dict(report.cleanup_counts)
    if (
        report.schema_version != REPORT_SCHEMA_VERSION
        or not _RUN_ID.fullmatch(report.run_id)
        or report.mode not in {"pilot", "run"}
        or not _GIT_SHA.fullmatch(report.git_commit)
        or report.source_clean is not True
        or report.source_label not in {"A1", "B", "A2"}
        or not all(
            _safe_report_label(value)
            for value in (
                report.provider_id,
                report.provider_class,
                report.model,
                report.voice,
                report.python_version,
                report.httpx_version,
                report.httpcore_version,
            )
        )
        or report.output_rate_hz != 24_000
        or report.decision
        not in {"PILOT_VALID", "CONTROL_VALID", "CANDIDATE_VALID", "INCONCLUSIVE"}
        or report.decision
        != _expected_decision(
            mode=report.mode,
            source_label=report.source_label,
            attempts=report.attempts,
            cleanup_completed=cleanup.get("completed", -1),
            expected_pairs=expected_pairs,
        )
        or attempt_slots != expected_slots
        or len(report.attempts) != len(expected_slots)
        or report.summaries != _summaries(report.attempts)
        or set(cleanup) != {"pairs", "completed", "incomplete"}
        or cleanup.get("pairs") != expected_pairs
        or type(cleanup.get("completed")) is not int
        or type(cleanup.get("incomplete")) is not int
        or cleanup["completed"] < 0
        or cleanup["incomplete"] < 0
        or cleanup["completed"] + cleanup["incomplete"] != expected_pairs
        or dict(report.forbidden_effects) != FORBIDDEN_EFFECTS
    ):
        raise ValueError("TTS_CONNECTION_REPORT_INVALID")


def build_report(
    config: TtsConnectionBenchmarkConfig,
    *,
    provider_id: str,
    provider_class: str,
    python_version: str,
    httpx_version: str,
    httpcore_version: str,
    attempts: tuple[TtsConnectionAttempt, ...],
    cleanup_complete: tuple[bool, ...],
) -> TtsConnectionCausalReport:
    if (
        not isinstance(config, TtsConnectionBenchmarkConfig)
        or len(cleanup_complete) != config.pair_count
        or any(type(value) is not bool for value in cleanup_complete)
    ):
        raise ValueError("TTS_CONNECTION_REPORT_INVALID")
    decision = _expected_decision(
        mode=config.mode,
        source_label=config.source_label,
        attempts=attempts,
        cleanup_completed=sum(cleanup_complete),
        expected_pairs=config.pair_count,
    )
    report = TtsConnectionCausalReport(
        REPORT_SCHEMA_VERSION,
        config.run_id,
        config.mode,
        config.git_commit,
        True,
        config.source_label,
        provider_id,
        provider_class,
        config.model,
        config.voice,
        config.output_rate_hz,
        python_version,
        httpx_version,
        httpcore_version,
        decision,
        attempts,
        _summaries(attempts),
        {
            "pairs": config.pair_count,
            "completed": sum(cleanup_complete),
            "incomplete": len(cleanup_complete) - sum(cleanup_complete),
        },
        dict(FORBIDDEN_EFFECTS),
    )
    _validate_report(report)
    return report


def _jsonable(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _closed_keys(value: object, keys: set[str]) -> Mapping[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("TTS_CONNECTION_REPORT_INVALID")
    return value


_ATTEMPT_KEYS = set(TtsConnectionAttempt.__dataclass_fields__)
_SUMMARY_KEYS = set(TtsPositionSummary.__dataclass_fields__)
_REPORT_KEYS = set(TtsConnectionCausalReport.__dataclass_fields__)


def _parse_attempt(value: object) -> TtsConnectionAttempt:
    row = _closed_keys(value, _ATTEMPT_KEYS)
    try:
        return TtsConnectionAttempt(
            row["pair_index"],
            TtsAttemptPosition(row["position"]),
            TtsAttemptOutcome(row["outcome"]),
            row["reason"],
            row["connection_reused"],
            row["request_started_ms"],
            row["tcp_connect_started_ms"],
            row["tcp_connect_completed_ms"],
            row["tls_started_ms"],
            row["tls_completed_ms"],
            row["response_headers_ms"],
            row["transport_open_ms"],
            row["first_audio_event_ms"],
            row["first_pcm_ms"],
            row["completed_ms"],
            row["stream_closed_ms"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("TTS_CONNECTION_REPORT_INVALID") from exc


def _parse_summary(value: object) -> TtsPositionSummary:
    row = _closed_keys(value, _SUMMARY_KEYS)
    try:
        return TtsPositionSummary(
            TtsAttemptPosition(row["position"]),
            row["attempts"],
            row["completed"],
            row["failed"],
            row["invalid"],
            row["unknown"],
            row["response_headers_ms_p50"],
            row["response_headers_ms_p95"],
            row["transport_open_ms_p50"],
            row["transport_open_ms_p95"],
            row["first_audio_event_ms_p50"],
            row["first_audio_event_ms_p95"],
            row["first_pcm_ms_p50"],
            row["first_pcm_ms_p95"],
            row["completed_ms_p50"],
            row["completed_ms_p95"],
            row["stream_closed_ms_p50"],
            row["stream_closed_ms_p95"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("TTS_CONNECTION_REPORT_INVALID") from exc


def _parse_report_payload(value: object) -> TtsConnectionCausalReport:
    row = _closed_keys(value, _REPORT_KEYS)
    try:
        attempts_value = row["attempts"]
        summaries_value = row["summaries"]
        if type(attempts_value) is not list or type(summaries_value) is not list:
            raise ValueError("TTS_CONNECTION_REPORT_INVALID")
        report = TtsConnectionCausalReport(
            row["schema_version"],
            row["run_id"],
            row["mode"],
            row["git_commit"],
            row["source_clean"],
            row["source_label"],
            row["provider_id"],
            row["provider_class"],
            row["model"],
            row["voice"],
            row["output_rate_hz"],
            row["python_version"],
            row["httpx_version"],
            row["httpcore_version"],
            row["decision"],
            tuple(_parse_attempt(item) for item in attempts_value),
            tuple(_parse_summary(item) for item in summaries_value),
            _closed_keys(
                row["cleanup_counts"], {"pairs", "completed", "incomplete"}
            ),
            _closed_keys(row["forbidden_effects"], set(FORBIDDEN_EFFECTS)),
        )
        _validate_report(report)
        return report
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("TTS_CONNECTION_REPORT_INVALID") from exc


def parse_report(path: Path) -> TtsConnectionCausalReport:
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or not path.is_file()
        or path.stat().st_size > MAX_REPORT_BYTES
        or path.stat().st_mode & 0o077
    ):
        raise ValueError("TTS_CONNECTION_REPORT_INVALID")
    try:
        return _parse_report_payload(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("TTS_CONNECTION_REPORT_INVALID") from exc


def write_private_report(path: Path, report: TtsConnectionCausalReport) -> None:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("TTS_CONNECTION_REPORT_INVALID")
    _validate_report(report)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = (
        json.dumps(_jsonable(report), separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(payload) > MAX_REPORT_BYTES:
        raise ValueError("TTS_CONNECTION_REPORT_INVALID")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        parsed = parse_report(temporary)
        if parsed != report:
            raise ValueError("TTS_CONNECTION_REPORT_INVALID")
        os.link(temporary, path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


async def run_benchmark(
    config: TtsConnectionBenchmarkConfig,
    *,
    provider_factory: ProviderFactory,
    monotonic: Callable[[], float] = time.monotonic,
) -> TtsConnectionCausalReport:
    attempts: list[TtsConnectionAttempt] = []
    cleanup_complete: list[bool] = []
    for pair_index in range(config.pair_count):
        pair_attempts, pair_cleanup = await run_provider_pair(
            config,
            pair_index=pair_index,
            provider_factory=provider_factory,
            monotonic=monotonic,
        )
        attempts.extend(pair_attempts)
        cleanup_complete.append(pair_cleanup)
        stop = not pair_cleanup or any(
            attempt.outcome is not TtsAttemptOutcome.COMPLETED
            for attempt in pair_attempts
        )
        if stop:
            for unrun_pair_index in range(pair_index + 1, config.pair_count):
                attempts.extend(
                    TtsConnectionAttempt.failed(
                        pair_index=unrun_pair_index,
                        position=position,
                        outcome=TtsAttemptOutcome.UNKNOWN,
                        reason="PAIR_ABORTED",
                    )
                    for position in (
                        TtsAttemptPosition.COLD,
                        TtsAttemptPosition.WARM,
                    )
                )
                cleanup_complete.append(False)
            break
    return build_report(
        config,
        provider_id="openai-streaming-speech",
        provider_class="OpenAIStreamingSpeechProvider",
        python_version=sys.version.split()[0],
        httpx_version=httpx.__version__,
        httpcore_version=httpcore.__version__,
        attempts=tuple(attempts),
        cleanup_complete=tuple(cleanup_complete),
    )


def _source_state() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
    ).stdout
    return commit, not bool(dirty)


def parse_args(
    argv: tuple[str, ...] | list[str] | None,
    *,
    environ: Mapping[str, str],
    source_commit: str,
    source_clean: bool,
) -> TtsConnectionBenchmarkConfig:
    class ClosedParser(argparse.ArgumentParser):
        def error(self, _message: str) -> None:
            raise ValueError("TTS_CONNECTION_BENCHMARK_CONFIG_INVALID")

    parser = ClosedParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("mode", choices=("pilot", "run"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--source-label", required=True, choices=("A1", "B", "A2"))
    values = parser.parse_args(argv)
    model = str(environ.get(SPEECH_TTS_MODEL_ENV) or "").strip()
    voice = str(environ.get(SPEECH_TTS_VOICE_ENV) or "").strip()
    if values.git_commit != source_commit or not model or not voice:
        raise ValueError("TTS_CONNECTION_BENCHMARK_CONFIG_INVALID")
    return TtsConnectionBenchmarkConfig(
        values.run_id,
        values.mode,
        values.output,
        values.git_commit,
        source_clean,
        values.source_label,
        model,
        voice,
        24_000,
    )


def _real_provider_factory(
    environ: Mapping[str, str],
    *,
    monotonic: Callable[[], float],
) -> ProviderFactory:
    provider_name = str(environ.get(SPEECH_PROVIDER_ENV) or "").strip().lower()
    api_base = str(environ.get(SPEECH_API_BASE_ENV) or "").strip()
    api_key = str(environ.get(SPEECH_API_KEY_ENV) or "").strip()
    model = str(environ.get(SPEECH_TTS_MODEL_ENV) or "").strip()
    voice = str(environ.get(SPEECH_TTS_VOICE_ENV) or "").strip()
    if provider_name != "openai" or not all((api_base, api_key, model, voice)):
        raise ValueError("PROVIDER_UNAVAILABLE")

    def factory(observer: SynthesisTransportObserver) -> TtsBenchmarkProvider:
        config = OpenAIStreamingSpeechConfig(
            api_base=api_base,
            api_key=api_key,
            tts_model=model,
            tts_voice=voice,
        )
        return OpenAIStreamingSpeechProvider(
            config,
            synthesis_transport_observer=observer,
            monotonic=monotonic,
        )

    return factory


async def _main(
    argv: tuple[str, ...] | list[str] | None,
    *,
    environ: Mapping[str, str],
    provider_factory: ProviderFactory | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    source_state_factory: Callable[[], tuple[str, bool]] = _source_state,
) -> int:
    source_commit, source_clean = source_state_factory()
    config = parse_args(
        argv,
        environ=environ,
        source_commit=source_commit,
        source_clean=source_clean,
    )
    selected_factory = provider_factory or _real_provider_factory(
        environ, monotonic=monotonic
    )
    report = await run_benchmark(
        config, provider_factory=selected_factory, monotonic=monotonic
    )
    final_commit, final_clean = source_state_factory()
    if final_commit != config.git_commit or final_clean is not True:
        raise ValueError("TTS_CONNECTION_BENCHMARK_INFRASTRUCTURE_INVALID")
    write_private_report(config.output_path, report)
    print(
        json.dumps(
            {"run_id": config.run_id, "decision": report.decision},
            separators=(",", ":"),
        )
    )
    return 0


def _worker_main(argv: tuple[str, ...] | list[str]) -> int:
    try:
        return asyncio.run(_main(argv, environ=os.environ))
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        print("TTS_CONNECTION_BENCHMARK_FAILED", file=sys.stderr)
        return 1


def _validated_worker_stdout(value: str) -> str | None:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    if (
        type(payload) is not dict
        or set(payload) != {"run_id", "decision"}
        or type(payload["run_id"]) is not str
        or not _RUN_ID.fullmatch(payload["run_id"])
        or payload["decision"]
        not in {"PILOT_VALID", "CONTROL_VALID", "CANDIDATE_VALID"}
    ):
        return None
    return json.dumps(payload, separators=(",", ":"))


def main(argv: tuple[str, ...] | list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == _WORKER_FLAG:
        expected_token = os.environ.pop(_WORKER_TOKEN_ENV, "")
        supplied_token = arguments[1] if len(arguments) > 1 else ""
        if (
            not expected_token
            or supplied_token != expected_token
            or not re.fullmatch(r"[0-9a-f]{32}", supplied_token)
        ):
            print("TTS_CONNECTION_BENCHMARK_FAILED", file=sys.stderr)
            return 1
        return _worker_main(arguments[2:])
    worker_token = uuid.uuid4().hex
    worker_environ = dict(os.environ)
    worker_environ[_WORKER_TOKEN_ENV] = worker_token
    command = (
        sys.executable,
        str(Path(__file__).resolve()),
        _WORKER_FLAG,
        worker_token,
        *arguments,
    )
    try:
        result = _run_process_with_watchdog(
            command,
            environ=worker_environ,
            timeout_seconds=PROCESS_WATCHDOG_SECONDS,
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        print("TTS_CONNECTION_BENCHMARK_FAILED", file=sys.stderr)
        return 1
    safe_stdout = None if result.timed_out else _validated_worker_stdout(result.stdout)
    if result.returncode != 0 or safe_stdout is None:
        print("TTS_CONNECTION_BENCHMARK_FAILED", file=sys.stderr)
        return 1
    print(safe_stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
