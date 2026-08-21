#!/usr/bin/env python3
"""No-Browser causal benchmark for the existing OpenAI server-VAD path."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import statistics
import struct
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from vad_eot_benchmark_support import (
    VadCorpusCase,
    VadCorpusManifest,
    load_vad_corpus_manifest,
    normalize_transcript,
    read_pcm16_mono_wav,
)

from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    OpenAIStreamingSpeechProvider,
    SpeechRouteTier,
    TransportCleanupSnapshot,
    select_environment_streaming_speech,
)
from jiuwenswarm.server.live_voice.speech_ports import RecognitionEventKind
from jiuwenswarm.server.live_voice.streaming_speech import (
    CaptureRef,
    RecognitionAudioFrame,
    RecognitionCommitDisposition,
    RecognitionStreamRef,
    RecognitionStreamRequest,
    RecognitionTurnBoundaryEvent,
    RecognitionTurnBoundaryKind,
    RecognitionTurnDetection,
    RecognitionTurnDetectionMode,
    ServerVadConfig,
    StreamingRecognitionEvent,
)


REPORT_SCHEMA_VERSION = "live-voice.vad-eot-causal-report.v0"
CONFIGURATION_SEQUENCE = (("A1", 1200), ("E1", 900), ("E2", 800), ("A2", 1200))
FRAME_SAMPLES = 960
FRAME_SECONDS = 0.020
EVENT_TIMEOUT_SECONDS = 20.0
_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class VadAttemptOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    INVALID = "invalid"


class VadAttemptReason(StrEnum):
    OK = "OK"
    EARLY_EOT = "EARLY_EOT"
    TURN_COUNT_MISMATCH = "TURN_COUNT_MISMATCH"
    TRANSCRIPT_INCOMPLETE = "TRANSCRIPT_INCOMPLETE"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    PACING_INVALID = "PACING_INVALID"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_PROTOCOL = "PROVIDER_PROTOCOL"
    TIMEOUT = "TIMEOUT"
    CLEANUP_INCOMPLETE = "CLEANUP_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class VadBenchmarkConfig:
    run_id: str
    mode: str
    manifest_path: Path = field(repr=False)
    output_path: Path = field(repr=False)
    git_commit: str
    source_clean: bool

    def __post_init__(self) -> None:
        if (
            type(self.run_id) is not str
            or not _RUN_ID.fullmatch(self.run_id)
            or self.mode not in {"pilot", "run"}
            or not isinstance(self.manifest_path, Path)
            or not self.manifest_path.is_absolute()
            or not isinstance(self.output_path, Path)
            or not self.output_path.is_absolute()
            or self.output_path.exists()
            or type(self.git_commit) is not str
            or not _GIT_SHA.fullmatch(self.git_commit)
            or self.source_clean is not True
        ):
            raise ValueError("VAD_BENCHMARK_CONFIG_INVALID")

    @property
    def configuration_sequence(self) -> tuple[tuple[str, int], ...]:
        return CONFIGURATION_SEQUENCE

    @property
    def attempts_per_case(self) -> int:
        return 1 if self.mode == "pilot" else 5


@dataclass(frozen=True, slots=True)
class VadAttemptResult:
    configuration_id: str
    silence_duration_ms: int
    case_id: str
    attempt_index: int
    outcome: VadAttemptOutcome
    reason: VadAttemptReason
    speech_started_count: int
    speech_stopped_count: int
    committed_count: int
    final_count: int
    exact_identity: bool
    transcript_complete: bool
    cleanup_complete: bool
    pacing_valid: bool
    final_voiced_frame_to_eot_ms: float | None
    eot_to_final_ms: float | None
    final_voiced_frame_to_final_ms: float | None
    provider_reported_speech_end_ms: float | None
    pacing_p50_ms: float | None
    pacing_p95_ms: float | None
    pacing_max_ms: float | None

    def __post_init__(self) -> None:
        metrics = (
            self.final_voiced_frame_to_eot_ms,
            self.eot_to_final_ms,
            self.final_voiced_frame_to_final_ms,
            self.provider_reported_speech_end_ms,
            self.pacing_p50_ms,
            self.pacing_p95_ms,
            self.pacing_max_ms,
        )
        counts = (
            self.speech_started_count,
            self.speech_stopped_count,
            self.committed_count,
            self.final_count,
        )
        completed = self.outcome is VadAttemptOutcome.COMPLETED
        if (
            self.configuration_id not in {"A1", "E1", "E2", "A2"}
            or type(self.silence_duration_ms) is not int
            or self.silence_duration_ms not in {800, 900, 1200}
            or type(self.case_id) is not str
            or not _RUN_ID.fullmatch(self.case_id)
            or type(self.attempt_index) is not int
            or not 0 <= self.attempt_index < 5
            or not isinstance(self.outcome, VadAttemptOutcome)
            or not isinstance(self.reason, VadAttemptReason)
            or any(type(value) is not int or value < 0 for value in counts)
            or any(value is not None and (not math.isfinite(value) or value < 0) for value in metrics)
            or (completed and self.reason is not VadAttemptReason.OK)
            or (not completed and self.reason is VadAttemptReason.OK)
            or (
                completed
                and (
                    counts != (1, 1, 1, 1)
                    or not all(
                        (
                            self.exact_identity,
                            self.transcript_complete,
                            self.cleanup_complete,
                            self.pacing_valid,
                        )
                    )
                    or any(value is None for value in metrics[:3])
                )
            )
            or (not completed and any(value is not None for value in metrics))
        ):
            raise ValueError("VAD_ATTEMPT_RESULT_INVALID")

    @classmethod
    def completed(
        cls,
        configuration_id: str,
        silence_duration_ms: int,
        case_id: str,
        attempt_index: int,
        **metrics: float | None,
    ) -> "VadAttemptResult":
        return cls(
            configuration_id,
            silence_duration_ms,
            case_id,
            attempt_index,
            VadAttemptOutcome.COMPLETED,
            VadAttemptReason.OK,
            1,
            1,
            1,
            1,
            True,
            True,
            True,
            True,
            metrics["final_voiced_frame_to_eot_ms"],
            metrics["eot_to_final_ms"],
            metrics["final_voiced_frame_to_final_ms"],
            metrics.get("provider_reported_speech_end_ms"),
            metrics.get("pacing_p50_ms"),
            metrics.get("pacing_p95_ms"),
            metrics.get("pacing_max_ms"),
        )

    @classmethod
    def failed(
        cls,
        configuration_id: str,
        silence_duration_ms: int,
        case_id: str,
        attempt_index: int,
        reason: VadAttemptReason,
        *,
        outcome: VadAttemptOutcome = VadAttemptOutcome.FAILED,
        speech_started_count: int = 0,
        speech_stopped_count: int = 0,
        committed_count: int = 0,
        final_count: int = 0,
        exact_identity: bool = False,
        transcript_complete: bool = False,
        cleanup_complete: bool = False,
        pacing_valid: bool = False,
    ) -> "VadAttemptResult":
        return cls(
            configuration_id,
            silence_duration_ms,
            case_id,
            attempt_index,
            outcome,
            reason,
            speech_started_count,
            speech_stopped_count,
            committed_count,
            final_count,
            exact_identity,
            transcript_complete,
            cleanup_complete,
            pacing_valid,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )


@dataclass(frozen=True, slots=True)
class VadConfigurationSummary:
    configuration_id: str
    silence_duration_ms: int
    case_id: str
    attempts: int
    completed: int
    failed: int
    unknown: int
    invalid: int
    eot_ms_p50: float | None
    eot_ms_p95: float | None


@dataclass(frozen=True, slots=True)
class VadBenchmarkReport:
    schema_version: str
    run_id: str
    mode: str
    git_commit: str
    source_clean: bool
    corpus_id: str
    corpus_manifest_sha256: str
    provider_id: str
    provider_class: str
    stt_model: str
    decision: str
    attempts: tuple[VadAttemptResult, ...]
    summaries: tuple[VadConfigurationSummary, ...]
    forbidden_effects: Mapping[str, int]


FORBIDDEN_EFFECTS = {
    "agent_submissions": 0,
    "tool_executions": 0,
    "task_mutations": 0,
    "p2_effects": 0,
    "tts_downlinks": 0,
    "history_writes": 0,
    "browser_effects": 0,
}


class VadRecognitionProvider(Protocol):
    cleanup_snapshot: TransportCleanupSnapshot

    async def open_recognition(self, request: RecognitionStreamRequest, *, timeout_seconds: float) -> None: ...
    async def send_recognition_audio(self, frame: RecognitionAudioFrame) -> None: ...
    async def commit_recognition(self, ref: RecognitionStreamRef) -> RecognitionCommitDisposition: ...
    async def next_recognition_event(self, ref: RecognitionStreamRef, *, timeout_seconds: float): ...
    async def cancel_recognition(self, ref: RecognitionStreamRef, *, reason: str = "caller_cancel") -> None: ...
    async def close(self) -> None: ...


ProviderFactory = Callable[[RecognitionTurnDetection], Awaitable[VadRecognitionProvider]]


def _nearest_rank(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _safe_summary(attempts: Sequence[VadAttemptResult]) -> tuple[VadConfigurationSummary, ...]:
    grouped: dict[tuple[str, int, str], list[VadAttemptResult]] = defaultdict(list)
    for attempt in attempts:
        grouped[(attempt.configuration_id, attempt.silence_duration_ms, attempt.case_id)].append(attempt)
    summaries = []
    for key in sorted(grouped, key=lambda value: ("A1E1E2A2".index(value[0]), value[2])):
        rows = grouped[key]
        values = [
            row.final_voiced_frame_to_eot_ms
            for row in rows
            if row.outcome is VadAttemptOutcome.COMPLETED
            and row.final_voiced_frame_to_eot_ms is not None
        ]
        summaries.append(
            VadConfigurationSummary(
                *key,
                len(rows),
                sum(row.outcome is VadAttemptOutcome.COMPLETED for row in rows),
                sum(row.outcome is VadAttemptOutcome.FAILED for row in rows),
                sum(row.outcome is VadAttemptOutcome.UNKNOWN for row in rows),
                sum(row.outcome is VadAttemptOutcome.INVALID for row in rows),
                statistics.median(values) if values else None,
                _nearest_rank(values, 0.95),
            )
        )
    return tuple(summaries)


def build_report(
    config: VadBenchmarkConfig,
    *,
    corpus_id: str,
    corpus_manifest_sha256: str,
    provider_id: str,
    provider_class: str,
    stt_model: str,
    attempts: tuple[VadAttemptResult, ...],
    decision: str,
) -> VadBenchmarkReport:
    if (
        not _RUN_ID.fullmatch(corpus_id)
        or not re.fullmatch(r"[0-9a-f]{64}", corpus_manifest_sha256)
        or not all(_SAFE_LABEL.fullmatch(value) for value in (provider_id, provider_class, stt_model))
        or decision not in {"READY_FOR_SCREENING", "LOWER_THRESHOLD_ELIGIBLE", "FIXED_THRESHOLD_REJECTED", "INCONCLUSIVE"}
    ):
        raise ValueError("VAD_BENCHMARK_REPORT_INVALID")
    return VadBenchmarkReport(
        REPORT_SCHEMA_VERSION,
        config.run_id,
        config.mode,
        config.git_commit,
        True,
        corpus_id,
        corpus_manifest_sha256,
        provider_id,
        provider_class,
        stt_model,
        decision,
        attempts,
        _safe_summary(attempts),
        dict(FORBIDDEN_EFFECTS),
    )


def _jsonable(value):
    if isinstance(value, StrEnum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def write_vad_benchmark_report(path: Path, report: VadBenchmarkReport) -> None:
    if not isinstance(path, Path) or not path.is_absolute() or not isinstance(report, VadBenchmarkReport):
        raise ValueError("VAD_BENCHMARK_REPORT_INVALID")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = json.dumps(_jsonable(report), separators=(",", ":"), sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(payload)
    path.chmod(0o600)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if type(loaded) is not dict or set(loaded) != set(report.__dataclass_fields__):
        path.unlink(missing_ok=True)
        raise ValueError("VAD_BENCHMARK_REPORT_INVALID")


async def run_vad_attempt(
    config: VadBenchmarkConfig,
    case: VadCorpusCase,
    attempt_index: int,
    *,
    configuration_id: str,
    silence_duration_ms: int,
    provider_factory: ProviderFactory,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> VadAttemptResult:
    del config
    provider: VadRecognitionProvider | None = None
    started = stopped = committed = final = 0
    exact_identity = transcript_complete = False
    pacing_valid = False
    lateness: list[float] = []
    eot_at = final_at = None
    provider_end_ms: float | None = None
    early_eot = False
    ref = RecognitionStreamRef(
        f"vad-{uuid.uuid4().hex}",
        1,
        CaptureRef(f"capture-{uuid.uuid4().hex}", 1, 48_000),
    )
    turn_detection = RecognitionTurnDetection(
        RecognitionTurnDetectionMode.SERVER_VAD,
        ServerVadConfig(
            threshold=0.5,
            prefix_padding_ms=300,
            silence_duration_ms=silence_duration_ms,
            create_response=False,
            interrupt_response=False,
        ),
    )
    sent_cursor = 0
    item_id: str | None = None
    eot_seen = asyncio.Event()
    commit_checked = asyncio.Event()
    final_text = ""
    disposition: RecognitionCommitDisposition | None = None
    try:
        provider = await provider_factory(turn_detection)
        await provider.open_recognition(
            RecognitionStreamRequest(ref, turn_detection),
            timeout_seconds=10.0,
        )
        decoded = read_pcm16_mono_wav(case.wav_path)
        epoch = monotonic()
        final_voice_at = epoch + case.final_voiced_frame / 48_000.0

        async def sender() -> None:
            nonlocal sent_cursor, disposition
            for seq, offset in enumerate(range(0, len(decoded.samples), FRAME_SAMPLES)):
                if eot_seen.is_set():
                    break
                deadline = epoch + seq * FRAME_SECONDS
                await sleep(max(0.0, deadline - monotonic()))
                lateness.append(max(0.0, (monotonic() - deadline) * 1000.0))
                samples = decoded.samples[offset : offset + FRAME_SAMPLES]
                floats = tuple(sample / 32768.0 for sample in samples)
                await provider.send_recognition_audio(
                    RecognitionAudioFrame(
                        ref,
                        seq,
                        offset,
                        len(samples),
                        struct.pack(f"<{len(floats)}f", *floats),
                    )
                )
                sent_cursor = offset + len(samples)
                await asyncio.sleep(0)
            disposition = await provider.commit_recognition(ref)
            commit_checked.set()

        async def collector() -> None:
            nonlocal started, stopped, committed, final, exact_identity
            nonlocal transcript_complete, eot_at, final_at, provider_end_ms
            nonlocal item_id, early_eot, final_text
            while final == 0:
                event = await provider.next_recognition_event(
                    ref, timeout_seconds=EVENT_TIMEOUT_SECONDS
                )
                if event.ref != ref:
                    exact_identity = False
                    raise ValueError("identity")
                if isinstance(event, RecognitionTurnBoundaryEvent):
                    if event.kind is RecognitionTurnBoundaryKind.SPEECH_STARTED:
                        started += 1
                        item_id = event.provider_item_id if item_id is None else item_id
                        exact_identity = event.provider_item_id == item_id
                    elif event.kind is RecognitionTurnBoundaryKind.SPEECH_STOPPED:
                        stopped += 1
                        exact_identity = exact_identity and event.provider_item_id == item_id
                        eot_at = monotonic()
                        provider_end_ms = (
                            float(event.provider_end_ms)
                            if event.provider_end_ms is not None
                            else None
                        )
                        early_eot = sent_cursor < case.final_voiced_frame
                        if provider_end_ms is not None:
                            early_eot = early_eot or provider_end_ms < case.final_voiced_frame / 48.0
                        eot_seen.set()
                        await commit_checked.wait()
                    elif event.kind is RecognitionTurnBoundaryKind.COMMITTED:
                        committed += 1
                        exact_identity = exact_identity and event.provider_item_id == item_id
                elif isinstance(event, StreamingRecognitionEvent):
                    if event.kind is RecognitionEventKind.FINAL:
                        final += 1
                        final_at = monotonic()
                        if event.hypothesis is None:
                            raise ValueError("final")
                        final_text = event.hypothesis.selected.display_text
                        normalized = normalize_transcript(final_text)
                        transcript_complete = (
                            normalized == case.expected_normalized_transcript
                            and all(token in normalized.split() for token in case.required_post_pause_tokens)
                        )

        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(sender())
            tasks.create_task(collector())
        p50 = statistics.median(lateness) if lateness else 0.0
        p95 = _nearest_rank(lateness, 0.95) or 0.0
        maximum = max(lateness, default=0.0)
        pacing_valid = p95 <= 20.0 and maximum <= 50.0
        del final_text
        await provider.close()
        clean = provider.cleanup_snapshot.clean
        if not clean:
            reason = VadAttemptReason.CLEANUP_INCOMPLETE
        elif not pacing_valid:
            reason = VadAttemptReason.PACING_INVALID
        elif early_eot:
            reason = VadAttemptReason.EARLY_EOT
        elif (started, stopped, committed, final) != (1, 1, 1, 1):
            reason = VadAttemptReason.TURN_COUNT_MISMATCH
        elif not exact_identity:
            reason = VadAttemptReason.IDENTITY_MISMATCH
        elif not transcript_complete:
            reason = VadAttemptReason.TRANSCRIPT_INCOMPLETE
        elif disposition not in {
            RecognitionCommitDisposition.SERVER_VAD_PENDING,
            RecognitionCommitDisposition.SERVER_VAD_OBSERVED,
        }:
            reason = VadAttemptReason.PROVIDER_PROTOCOL
        else:
            assert eot_at is not None and final_at is not None
            return VadAttemptResult.completed(
                configuration_id,
                silence_duration_ms,
                case.case_id,
                attempt_index,
                final_voiced_frame_to_eot_ms=(eot_at - final_voice_at) * 1000.0,
                eot_to_final_ms=(final_at - eot_at) * 1000.0,
                final_voiced_frame_to_final_ms=(final_at - final_voice_at) * 1000.0,
                provider_reported_speech_end_ms=provider_end_ms,
                pacing_p50_ms=p50,
                pacing_p95_ms=p95,
                pacing_max_ms=maximum,
            )
        return VadAttemptResult.failed(
            configuration_id,
            silence_duration_ms,
            case.case_id,
            attempt_index,
            reason,
            outcome=(VadAttemptOutcome.INVALID if reason is VadAttemptReason.PACING_INVALID else VadAttemptOutcome.FAILED),
            speech_started_count=started,
            speech_stopped_count=stopped,
            committed_count=committed,
            final_count=final,
            exact_identity=exact_identity,
            transcript_complete=transcript_complete,
            cleanup_complete=clean,
            pacing_valid=pacing_valid,
        )
    except asyncio.TimeoutError:
        reason = VadAttemptReason.TIMEOUT
        outcome = VadAttemptOutcome.UNKNOWN
    except asyncio.CancelledError:
        raise
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        reason = VadAttemptReason.PROVIDER_PROTOCOL
        outcome = VadAttemptOutcome.UNKNOWN
    finally:
        commit_checked.set()
        if provider is not None and not getattr(provider, "closed", False):
            try:
                await provider.close()
            except Exception:
                pass
    cleanup = bool(provider is not None and provider.cleanup_snapshot.clean)
    return VadAttemptResult.failed(
        configuration_id,
        silence_duration_ms,
        case.case_id,
        attempt_index,
        reason,
        outcome=outcome,
        speech_started_count=started,
        speech_stopped_count=stopped,
        committed_count=committed,
        final_count=final,
        exact_identity=exact_identity,
        transcript_complete=transcript_complete,
        cleanup_complete=cleanup,
        pacing_valid=pacing_valid,
    )


async def create_real_streaming_provider(environ: Mapping[str, str]) -> OpenAIStreamingSpeechProvider:
    allowed = {
        key: str(environ.get(key) or "")
        for key in (
            "LIVE_VOICE_SPEECH_PROVIDER",
            "LIVE_VOICE_SPEECH_API_BASE",
            "LIVE_VOICE_SPEECH_API_KEY",
            "LIVE_VOICE_SPEECH_STT_MODEL",
        )
    }
    allowed["LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED"] = "1"
    selected = await select_environment_streaming_speech(
        environ=allowed,
        batch_available=False,
    )
    if selected.tier is not SpeechRouteTier.STREAMING or not isinstance(
        selected.provider, OpenAIStreamingSpeechProvider
    ):
        raise ValueError("PROVIDER_UNAVAILABLE")
    return selected.provider


def _decision(config: VadBenchmarkConfig, attempts: tuple[VadAttemptResult, ...]) -> str:
    if config.mode == "pilot":
        return "READY_FOR_SCREENING"
    summaries = {(row.configuration_id, row.case_id): row for row in _safe_summary(attempts)}
    cases = sorted({row.case_id for row in attempts})
    for case_id in cases:
        a1, a2 = summaries[("A1", case_id)], summaries[("A2", case_id)]
        if a1.completed != a2.completed or a1.eot_ms_p50 is None or a2.eot_ms_p50 is None:
            return "INCONCLUSIVE"
        if abs(a1.eot_ms_p50 - a2.eot_ms_p50) > max(a1.eot_ms_p50, a2.eot_ms_p50) * 0.10:
            return "INCONCLUSIVE"

    eligible = []
    for candidate in ("E1", "E2"):
        valid = True
        for case_id in cases:
            row = summaries[(candidate, case_id)]
            controls = (summaries[("A1", case_id)], summaries[("A2", case_id)])
            valid = valid and row.completed == 5 and row.attempts == 5
            valid = valid and all(
                row.eot_ms_p50 is not None
                and control.eot_ms_p50 is not None
                and row.eot_ms_p50 < control.eot_ms_p50
                and row.eot_ms_p95 is not None
                and control.eot_ms_p95 is not None
                and row.eot_ms_p95 < control.eot_ms_p95
                for control in controls
            )
        if valid:
            eligible.append(candidate)
    if not eligible:
        return "FIXED_THRESHOLD_REJECTED"
    if eligible == ["E2"]:
        return "LOWER_THRESHOLD_ELIGIBLE"
    if "E1" in eligible and "E2" in eligible:
        e2_wins = all(
            summaries[("E1", case)].eot_ms_p50 - summaries[("E2", case)].eot_ms_p50 >= 80.0
            and summaries[("E2", case)].eot_ms_p95 <= summaries[("E1", case)].eot_ms_p95
            for case in cases
        )
        del e2_wins  # threshold selection belongs in sanitized evidence, not the decision token.
    return "LOWER_THRESHOLD_ELIGIBLE"


async def run_screening(
    config: VadBenchmarkConfig,
    manifest: VadCorpusManifest,
    *,
    provider_factory: ProviderFactory,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    attempt_runner=run_vad_attempt,
    provider_id: str = "openai",
    provider_class: str = "OpenAIStreamingSpeechProvider",
    stt_model: str = "gpt-4o-mini-transcribe",
) -> VadBenchmarkReport:
    attempts = []
    for configuration_id, threshold in CONFIGURATION_SEQUENCE:
        for case in manifest.cases:
            for attempt_index in range(config.attempts_per_case):
                result = await attempt_runner(
                    config,
                    case,
                    attempt_index,
                    configuration_id=configuration_id,
                    silence_duration_ms=threshold,
                    provider_factory=provider_factory,
                    monotonic=monotonic,
                    sleep=sleep,
                )
                attempts.append(result)
                if result.outcome in {VadAttemptOutcome.UNKNOWN, VadAttemptOutcome.INVALID}:
                    raise ValueError("VAD_EOT_BENCHMARK_INFRASTRUCTURE_INVALID")
    frozen = tuple(attempts)
    digest = hashlib.sha256(config.manifest_path.read_bytes()).hexdigest()
    return build_report(
        config,
        corpus_id=manifest.corpus_id,
        corpus_manifest_sha256=digest,
        provider_id=provider_id,
        provider_class=provider_class,
        stt_model=stt_model,
        attempts=frozen,
        decision=_decision(config, frozen),
    )


def _source_state() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, not bool(dirty)


def parse_args(
    argv: Sequence[str] | None,
    *,
    source_commit: str | None = None,
    source_clean: bool | None = None,
) -> VadBenchmarkConfig:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("mode", choices=("pilot", "run"))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    values = parser.parse_args(argv)
    if source_commit is None or source_clean is None:
        source_commit, source_clean = _source_state()
    if values.git_commit != source_commit:
        raise ValueError("VAD_BENCHMARK_CONFIG_INVALID")
    return VadBenchmarkConfig(
        values.run_id,
        values.mode,
        values.manifest,
        values.output,
        values.git_commit,
        source_clean,
    )


async def _main(
    argv: Sequence[str] | None,
    *,
    environ: Mapping[str, str],
    source_commit: str | None = None,
    source_clean: bool | None = None,
) -> int:
    config = parse_args(
        argv, source_commit=source_commit, source_clean=source_clean
    )
    manifest = load_vad_corpus_manifest(config.manifest_path)

    async def factory(_turn_detection):
        return await create_real_streaming_provider(environ)

    report = await run_screening(
        config,
        manifest,
        provider_factory=factory,
        stt_model=str(environ.get("LIVE_VOICE_SPEECH_STT_MODEL") or "gpt-4o-mini-transcribe"),
    )
    write_vad_benchmark_report(config.output_path, report)
    print(json.dumps({"run_id": config.run_id, "decision": report.decision}, separators=(",", ":")))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(_main(argv, environ=os.environ))
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        print("VAD_EOT_BENCHMARK_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
