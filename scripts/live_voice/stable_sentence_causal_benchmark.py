#!/usr/bin/env python3
"""No-Chrome causal benchmark for stable-sentence Agent-to-TTS overlap."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import statistics
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.agent_bridge import AgentEvent
from jiuwenswarm.server.live_voice.latency_probe import (
    CONTEXT_SCHEMA_VERSION,
    LatencyBatch,
    LatencyProbeBatchWriter,
    LatencyProbeContext,
    LatencyProbeRecorder,
    LatencyRunConfig,
    _parse_latency_run_config,
    load_latency_run_config,
)
from jiuwenswarm.server.live_voice.latency_probe_report import (
    reduce_latency_run,
    write_latency_report,
)
from jiuwenswarm.server.live_voice.stable_sentence_policy import (
    FinalReconciliationDisposition,
    StableSentenceStreamState,
    candidate_content,
    commit_candidate,
    observe_agent_event,
    reconcile_final,
)


REPORT_SCHEMA_VERSION = "live-voice.stable-sentence-causal-result.v0"
MATERIALITY_SCHEMA_VERSION = "live-voice.stable-sentence-materiality.v0"
MAX_REPORT_BYTES = 1_048_576
CONTROLLED_FIRST_DELTA_MS = 100.0
CONTROLLED_FRAGMENT_INTERVAL_MS = 100.0
CONTROLLED_CANDIDATE_TO_FINAL_MS = 750.0
CONTROLLED_TTS_FIRST_PCM_MS = 800.0
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ZERO_FORBIDDEN_EFFECTS = (
    ("agent_submissions", 0),
    ("audio_playouts", 0),
    ("browser_effects", 0),
    ("history_writes", 0),
    ("product_downlinks", 0),
    ("task_mutations", 0),
    ("tool_executions", 0),
)


class ControlledTtsPort(Protocol):
    async def first_pcm_delay_ms(self, text_utf8: bytes) -> float: ...


@dataclass(frozen=True, slots=True)
class ControlledCase:
    case_id: str
    fragments: tuple[str, ...] = field(repr=False)
    expected_candidate: str | None = field(repr=False)
    final: str = field(repr=False)
    expected_disposition: str


@dataclass(frozen=True, slots=True)
class StableSentenceBenchmarkConfig:
    run_json: Path = field(repr=False)
    output_path: Path = field(repr=False)
    mode: Literal["controlled", "provider-pilot", "run"]
    population: Literal["SCREEN", "A1", "B", "A2"]
    git_commit: str
    source_clean: bool
    run: LatencyRunConfig = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            run = load_latency_run_config(self.run_json)
        except Exception as error:
            raise ValueError("STABLE_SENTENCE_CONFIG_INVALID") from error
        if (
            not self.run_json.is_absolute()
            or not self.run_json.is_file()
            or not self.output_path.is_absolute()
            or self.output_path.exists()
            or self.mode not in {"controlled", "provider-pilot", "run"}
            or self.population not in {"SCREEN", "A1", "B", "A2"}
            or (self.mode == "controlled" and self.population != "SCREEN")
            or not _GIT_SHA.fullmatch(self.git_commit)
            or self.git_commit != run.git_commit
            or self.source_clean is not True
            or run.source_state != "clean"
            or run.optimization_track != "agent_tts_overlap"
            or run.benchmark_lane != "no_browser_causal"
        ):
            raise ValueError("STABLE_SENTENCE_CONFIG_INVALID")
        object.__setattr__(self, "run", run)


@dataclass(frozen=True, slots=True)
class StableSentenceAttempt:
    population: str
    case_id: str
    attempt_index: int
    outcome: str
    reason: str | None
    first_delta_ms: float | None
    candidate_detected_ms: float | None
    final_ms: float | None
    baseline_first_pcm_ms: float | None
    candidate_first_pcm_ms: float | None
    candidate_to_final_ms: float | None
    projected_gain_ms: float | None
    candidate_count: int
    discard_count: int
    prefix_match_count: int
    prefix_mismatch_count: int
    correction_count: int
    forbidden_effects: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        metrics = (
            self.first_delta_ms,
            self.candidate_detected_ms,
            self.final_ms,
            self.baseline_first_pcm_ms,
            self.candidate_first_pcm_ms,
            self.candidate_to_final_ms,
            self.projected_gain_ms,
        )
        counts = (
            self.candidate_count,
            self.discard_count,
            self.prefix_match_count,
            self.prefix_mismatch_count,
            self.correction_count,
        )
        if (
            self.population not in {"SCREEN", "A1", "B", "A2"}
            or not _SAFE_ID.fullmatch(self.case_id)
            or not isinstance(self.attempt_index, int)
            or self.attempt_index < 0
            or self.outcome not in {
                "completed",
                "integrity_failure",
                "failed",
                "unknown",
            }
            or (self.outcome == "completed") != (self.reason is None)
            or any(not isinstance(value, int) or value < 0 for value in counts)
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
            or self.forbidden_effects != ZERO_FORBIDDEN_EFFECTS
            or (
                self.outcome != "completed"
                and any(
                    value is not None
                    for value in (
                        self.candidate_to_final_ms,
                        self.projected_gain_ms,
                        self.baseline_first_pcm_ms,
                        self.candidate_first_pcm_ms,
                    )
                )
            )
        ):
            raise ValueError("STABLE_SENTENCE_ATTEMPT_INVALID")

    @classmethod
    def completed(
        cls,
        *,
        population: str,
        case_id: str,
        attempt_index: int,
        first_delta_ms: float,
        candidate_detected_ms: float,
        final_ms: float,
        baseline_first_pcm_ms: float,
        candidate_first_pcm_ms: float,
        candidate_count: int,
        discard_count: int,
        prefix_match_count: int,
        prefix_mismatch_count: int,
        correction_count: int,
    ) -> StableSentenceAttempt:
        return cls(
            population=population,
            case_id=case_id,
            attempt_index=attempt_index,
            outcome="completed",
            reason=None,
            first_delta_ms=first_delta_ms,
            candidate_detected_ms=candidate_detected_ms,
            final_ms=final_ms,
            baseline_first_pcm_ms=baseline_first_pcm_ms,
            candidate_first_pcm_ms=candidate_first_pcm_ms,
            candidate_to_final_ms=final_ms - candidate_detected_ms,
            projected_gain_ms=baseline_first_pcm_ms - candidate_first_pcm_ms,
            candidate_count=candidate_count,
            discard_count=discard_count,
            prefix_match_count=prefix_match_count,
            prefix_mismatch_count=prefix_mismatch_count,
            correction_count=correction_count,
            forbidden_effects=ZERO_FORBIDDEN_EFFECTS,
        )

    @classmethod
    def noncompleted(
        cls,
        *,
        population: str,
        case_id: str,
        attempt_index: int,
        outcome: str,
        reason: str,
        first_delta_ms: float | None,
        candidate_detected_ms: float | None,
        final_ms: float | None,
        candidate_count: int,
        discard_count: int,
        prefix_match_count: int,
        prefix_mismatch_count: int,
        correction_count: int,
    ) -> StableSentenceAttempt:
        return cls(
            population,
            case_id,
            attempt_index,
            outcome,
            reason,
            first_delta_ms,
            candidate_detected_ms,
            final_ms,
            None,
            None,
            None,
            None,
            candidate_count,
            discard_count,
            prefix_match_count,
            prefix_mismatch_count,
            correction_count,
            ZERO_FORBIDDEN_EFFECTS,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ControlledAttemptResult:
    attempt: StableSentenceAttempt
    batch: LatencyBatch


@dataclass(frozen=True, slots=True)
class MaterialityGate:
    schema_version: str
    decision: str
    reasons: tuple[str, ...]
    successful_samples: int
    trace_classes: int
    candidate_to_final_p50_ms: float | None
    projected_gain_p50_ms: float | None
    projected_gain_percent_p50: float | None
    prefix_mismatch_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StableSentenceCausalResult:
    schema_version: str
    run_id: str
    git_commit: str
    mode: str
    population: str
    attempts: tuple[StableSentenceAttempt, ...]
    gate: MaterialityGate
    forbidden_effects: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "git_commit": self.git_commit,
            "mode": self.mode,
            "population": self.population,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "gate": self.gate.to_dict(),
            "forbidden_effects": dict(self.forbidden_effects),
        }


class _FixedControlledTts:
    async def first_pcm_delay_ms(self, text_utf8: bytes) -> float:
        if not text_utf8:
            raise ValueError("STABLE_SENTENCE_TTS_INPUT_INVALID")
        return CONTROLLED_TTS_FIRST_PCM_MS


class _ManualClock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value


def _require_exact_mapping(value: object, keys: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError("STABLE_SENTENCE_FIXTURE_INVALID")
    return value


def load_controlled_cases(path: Path) -> tuple[ControlledCase, ...]:
    if not isinstance(path, Path) or not path.is_file() or path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("STABLE_SENTENCE_FIXTURE_INVALID")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("STABLE_SENTENCE_FIXTURE_INVALID") from error
    if not isinstance(raw, list) or not 2 <= len(raw) <= 64:
        raise ValueError("STABLE_SENTENCE_FIXTURE_INVALID")
    result: list[ControlledCase] = []
    for item in raw:
        record = _require_exact_mapping(
            item,
            frozenset(
                {
                    "case_id",
                    "fragments",
                    "expected_candidate",
                    "final",
                    "expected_disposition",
                }
            ),
        )
        case_id = record["case_id"]
        fragments = record["fragments"]
        candidate = record["expected_candidate"]
        final = record["final"]
        disposition = record["expected_disposition"]
        if (
            not isinstance(case_id, str)
            or not _SAFE_ID.fullmatch(case_id)
            or not isinstance(fragments, list)
            or not fragments
            or not all(isinstance(fragment, str) and fragment for fragment in fragments)
            or (candidate is not None and not isinstance(candidate, str))
            or not isinstance(final, str)
            or not final
            or disposition not in {item.value for item in FinalReconciliationDisposition}
        ):
            raise ValueError("STABLE_SENTENCE_FIXTURE_INVALID")
        result.append(
            ControlledCase(
                case_id,
                tuple(fragments),
                candidate,
                final,
                disposition,
            )
        )
    if len({case.case_id for case in result}) != len(result):
        raise ValueError("STABLE_SENTENCE_FIXTURE_INVALID")
    return tuple(result)


def _agent_event(seq: int, text: str) -> AgentEvent:
    return AgentEvent(
        request_id="stable-screen-request",
        interaction_id="stable-screen-interaction",
        turn_id="stable-screen-turn",
        commit_id="stable-screen-commit",
        seq=seq,
        event_type="chat.delta",
        source_provenance="stable-screen-controlled",
        text=text,
        capability="agent.chat",
    )


def _mark(
    recorder: LatencyProbeRecorder,
    clock: _ManualClock,
    point: str,
    timestamp: float,
) -> None:
    clock.value = timestamp
    accepted = recorder.mark(
        point,
        correlation_id="stable-screen-correlation",
        interaction_id="stable-screen-interaction",
        activation_id="stable-screen-activation",
        activation_generation=1,
        turn_id="stable-screen-turn",
        response_id="stable-screen-response",
        response_generation=0,
    )
    if not accepted:
        raise ValueError("STABLE_SENTENCE_PROBE_MARK_REJECTED")


async def run_controlled_attempt(
    config: StableSentenceBenchmarkConfig,
    case: ControlledCase,
    *,
    attempt_index: int,
    tts: ControlledTtsPort,
) -> ControlledAttemptResult:
    if (
        config.mode != "controlled"
        or config.population != "SCREEN"
        or not isinstance(case, ControlledCase)
        or not isinstance(attempt_index, int)
        or not 0 <= attempt_index < config.run.intended_attempts
    ):
        raise ValueError("STABLE_SENTENCE_ATTEMPT_CONFIG_INVALID")
    response = ResponseRef(
        "stable-screen-interaction", "stable-screen-response", 0
    )
    state = StableSentenceStreamState.create(response)
    first_delta_ms = CONTROLLED_FIRST_DELTA_MS
    candidate_detected_ms: float | None = None
    observed_tts_delay_ms: float | None = None
    candidate_count = discard_count = 0
    for seq, fragment in enumerate(case.fragments):
        observation = observe_agent_event(state, _agent_event(seq, fragment))
        state = observation.state
        discard_count += len(observation.discarded_candidate_ids)
        if observation.candidate is not None and candidate_detected_ms is None:
            candidate_detected_ms = (
                CONTROLLED_FIRST_DELTA_MS
                + seq * CONTROLLED_FRAGMENT_INTERVAL_MS
            )
            candidate_count = 1
            content = candidate_content(state, observation.candidate)
            tts_delay_ms = await tts.first_pcm_delay_ms(content)
            if (
                isinstance(tts_delay_ms, bool)
                or not isinstance(tts_delay_ms, (int, float))
                or not math.isfinite(tts_delay_ms)
                or tts_delay_ms <= 0
            ):
                raise ValueError("STABLE_SENTENCE_TTS_TIMING_INVALID")
            observed_tts_delay_ms = float(tts_delay_ms)
            state = commit_candidate(state, observation.candidate.candidate_id).state
    final_ms = (
        (candidate_detected_ms + CONTROLLED_CANDIDATE_TO_FINAL_MS)
        if candidate_detected_ms is not None
        else CONTROLLED_FIRST_DELTA_MS
        + len(case.fragments) * CONTROLLED_FRAGMENT_INTERVAL_MS
        + CONTROLLED_CANDIDATE_TO_FINAL_MS
    )
    reconciled = reconcile_final(state, case.final)
    expected = case.expected_disposition
    integrity_ok = reconciled.disposition.value == expected
    prefix_mismatch_count = int(
        reconciled.disposition
        is FinalReconciliationDisposition.REWRITE_AFTER_COMMIT
    )
    prefix_match_count = int(
        reconciled.disposition is FinalReconciliationDisposition.EXACT_PREFIX
        and candidate_detected_ms is not None
    )
    clock = _ManualClock()
    context = LatencyProbeContext(
        CONTEXT_SCHEMA_VERSION,
        config.run.run_id,
        "dialogue_no_tool",
        config.run.input_case_for_profile("dialogue_no_tool") or "",
        attempt_index,
    )
    recorder = LatencyProbeRecorder(
        context=context,
        component="agent_server",
        phase="agent_foreground",
        run_config=config.run,
        source_instance_id_factory=lambda: "stable-screen-agent-source",
        batch_id_factory=lambda: f"stable-screen-batch-{attempt_index}",
        clock_domain_id="stable-screen-controlled-clock",
        monotonic_ms=clock.now,
    )
    _mark(recorder, clock, "agent.agent_started", 0.0)
    _mark(recorder, clock, "agent.agent_first_delta", first_delta_ms)
    if candidate_detected_ms is not None:
        _mark(
            recorder,
            clock,
            "agent.sentence_candidate_detected",
            candidate_detected_ms,
        )
    _mark(recorder, clock, "agent.agent_final", final_ms)
    completed = (
        integrity_ok
        and prefix_mismatch_count == 0
        and candidate_detected_ms is not None
    )
    batch = recorder.finish("completed" if completed else "failed")
    if batch is None:
        raise ValueError("STABLE_SENTENCE_PROBE_FINISH_FAILED")
    if completed:
        if observed_tts_delay_ms is None:
            raise ValueError("STABLE_SENTENCE_TTS_TIMING_INVALID")
        tts_delay = observed_tts_delay_ms
        candidate_first_pcm = candidate_detected_ms + tts_delay
        baseline_first_pcm = final_ms + tts_delay
        attempt = StableSentenceAttempt.completed(
            population=config.population,
            case_id=case.case_id,
            attempt_index=attempt_index,
            first_delta_ms=first_delta_ms,
            candidate_detected_ms=candidate_detected_ms,
            final_ms=final_ms,
            baseline_first_pcm_ms=baseline_first_pcm,
            candidate_first_pcm_ms=candidate_first_pcm,
            candidate_count=candidate_count,
            discard_count=discard_count,
            prefix_match_count=prefix_match_count,
            prefix_mismatch_count=0,
            correction_count=0,
        )
    else:
        attempt = StableSentenceAttempt.noncompleted(
            population=config.population,
            case_id=case.case_id,
            attempt_index=attempt_index,
            outcome="integrity_failure",
            reason=(
                "PREFIX_MISMATCH"
                if prefix_mismatch_count
                else "FIXTURE_DISPOSITION_MISMATCH"
                if not integrity_ok
                else "NO_STABLE_CANDIDATE"
            ),
            first_delta_ms=first_delta_ms,
            candidate_detected_ms=candidate_detected_ms,
            final_ms=final_ms,
            candidate_count=candidate_count,
            discard_count=discard_count,
            prefix_match_count=prefix_match_count,
            prefix_mismatch_count=prefix_mismatch_count,
            correction_count=int(reconciled.correction_required),
        )
    return ControlledAttemptResult(attempt, batch)


def _p50(values: Sequence[float]) -> float | None:
    return None if not values else float(statistics.median(values))


def reduce_materiality_gate(
    attempts: Sequence[StableSentenceAttempt],
) -> MaterialityGate:
    completed = tuple(attempt for attempt in attempts if attempt.outcome == "completed")
    headrooms = tuple(
        attempt.candidate_to_final_ms
        for attempt in completed
        if attempt.candidate_to_final_ms is not None
    )
    gains = tuple(
        attempt.projected_gain_ms
        for attempt in completed
        if attempt.projected_gain_ms is not None
    )
    relative = tuple(
        100.0 * attempt.projected_gain_ms / attempt.baseline_first_pcm_ms
        for attempt in completed
        if attempt.projected_gain_ms is not None
        and attempt.baseline_first_pcm_ms is not None
        and attempt.baseline_first_pcm_ms > 0
    )
    headroom_p50 = _p50(headrooms)
    gain_p50 = _p50(gains)
    relative_p50 = _p50(relative)
    trace_classes = len({attempt.case_id for attempt in completed})
    mismatches = sum(attempt.prefix_mismatch_count for attempt in attempts)
    reasons: list[str] = []
    if headroom_p50 is None or headroom_p50 < 500.0:
        reasons.append("HEADROOM_BELOW_GATE")
    if gain_p50 is None or gain_p50 < 400.0:
        reasons.append("ABSOLUTE_GAIN_BELOW_GATE")
    if relative_p50 is None or relative_p50 < 10.0:
        reasons.append("RELATIVE_GAIN_BELOW_GATE")
    if trace_classes < 2:
        reasons.append("TRACE_CLASS_COVERAGE_BELOW_GATE")
    if mismatches:
        reasons.append("PREFIX_MISMATCH")
    if any(attempt.forbidden_effects != ZERO_FORBIDDEN_EFFECTS for attempt in attempts):
        reasons.append("FORBIDDEN_EFFECT")
    return MaterialityGate(
        MATERIALITY_SCHEMA_VERSION,
        "PASS" if not reasons else "STOP",
        tuple(reasons),
        len(completed),
        trace_classes,
        headroom_p50,
        gain_p50,
        relative_p50,
        mismatches,
    )


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    ) + b"\n"
    if len(encoded) > MAX_REPORT_BYTES:
        raise ValueError("STABLE_SENTENCE_REPORT_TOO_LARGE")
    return encoded


def _write_private_json(value: Mapping[str, object], path: Path) -> None:
    if not path.is_absolute():
        raise ValueError("STABLE_SENTENCE_OUTPUT_INVALID")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = _canonical_bytes(value)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


def write_result(report: StableSentenceCausalResult, path: Path) -> None:
    if (
        not isinstance(report, StableSentenceCausalResult)
        or report.schema_version != REPORT_SCHEMA_VERSION
        or report.forbidden_effects != ZERO_FORBIDDEN_EFFECTS
    ):
        raise ValueError("STABLE_SENTENCE_REPORT_INVALID")
    _write_private_json(report.to_dict(), path)


async def run_controlled_corpus(
    config: StableSentenceBenchmarkConfig, fixture_path: Path
) -> StableSentenceCausalResult:
    cases = load_controlled_cases(fixture_path)
    if config.run.intended_attempts != len(cases):
        raise ValueError("STABLE_SENTENCE_ATTEMPT_POLICY_MISMATCH")
    writer = LatencyProbeBatchWriter(
        config.run_json.parent.parent, config.run, "agent_server"
    )
    attempts: list[StableSentenceAttempt] = []
    batches: list[LatencyBatch] = []
    for attempt_index, case in enumerate(cases):
        result = await run_controlled_attempt(
            config,
            case,
            attempt_index=attempt_index,
            tts=_FixedControlledTts(),
        )
        receipt = writer.write(result.batch)
        if receipt.status not in {"written", "replayed"}:
            raise ValueError("STABLE_SENTENCE_BATCH_WRITE_FAILED")
        attempts.append(result.attempt)
        batches.append(result.batch)
    latency_report = reduce_latency_run(config.run, batches)
    write_latency_report(latency_report, config.run_json.parent)
    report = StableSentenceCausalResult(
        REPORT_SCHEMA_VERSION,
        config.run.run_id,
        config.git_commit,
        config.mode,
        config.population,
        tuple(attempts),
        reduce_materiality_gate(attempts),
        ZERO_FORBIDDEN_EFFECTS,
    )
    write_result(report, config.output_path)
    return report


def _source_state() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, not bool(dirty)


def _prepare(output: Path, *, source_commit: str, source_clean: bool) -> None:
    if (
        not output.is_absolute()
        or output.name != "run.json"
        or output.exists()
        or not _GIT_SHA.fullmatch(source_commit)
        or not source_clean
    ):
        raise ValueError("STABLE_SENTENCE_CONFIG_INVALID")
    payload = {
        "schema_version": "live-voice.latency-run.v1",
        "run_id": output.parent.name,
        "git_commit": source_commit,
        "source_state": "clean",
        "environment_profile": "controlled-python",
        "browser_family_and_version": "not-exercised",
        "browser_os_class": "not-exercised",
        "gateway_runtime_class": "controlled-tts",
        "agent_runtime_class": "controlled-agent-events",
        "stt_provider_and_model": "not-exercised",
        "tts_provider_and_model": "controlled-delay",
        "audio_format": "pcm16-24000hz-mono",
        "vad_configuration": "not-exercised",
        "playout_configuration": "not-exercised",
        "allowlisted_feature_flags": {
            "latency_probe": True,
            "stable_sentence_tts": False,
        },
        "cold_or_warm": "warm",
        "input_case_ids": ["stable-sentence-controlled-v1"],
        "profile_ids": ["dialogue_no_tool"],
        "intended_attempts": 7,
        "required_successes": 1,
        "experiment": {
            "experiment_id": "stable-sentence-screen",
            "target_segment": "agent_to_final",
            "target_statistic": "p50_ms",
            "minimum_improvement_ms": 400.0,
            "response_total_minimum_improvement_ms": 400.0,
            "guardrails": [
                {
                    "metric": "failure_rate",
                    "segment_id": None,
                    "maximum_regression": 0.0,
                }
            ],
            "declared_experiment_points": [
                {
                    "point": "agent.sentence_candidate_detected",
                    "component": "agent_server",
                    "paired_segment_id": "candidate_to_final",
                    "start_point": "agent.sentence_candidate_detected",
                    "end_point": "agent.agent_final",
                }
            ],
        },
        "optimization_track": "agent_tts_overlap",
        "benchmark_lane": "no_browser_causal",
        "fixture_profile_id": "stable-sentence-policy-v1",
    }
    run = _parse_latency_run_config(payload)
    _write_private_json(run.to_dict(), output)


def _load_result(path: Path) -> StableSentenceCausalResult:
    if not path.is_file() or path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("STABLE_SENTENCE_REPORT_INVALID")
    raw = json.loads(path.read_text(encoding="utf-8"))
    attempts = tuple(
        StableSentenceAttempt(
            **{
                **item,
                "forbidden_effects": tuple(
                    (key, value) for key, value in item["forbidden_effects"]
                ),
            }
        )
        for item in raw["attempts"]
    )
    gate = MaterialityGate(**raw["gate"])
    return StableSentenceCausalResult(
        raw["schema_version"],
        raw["run_id"],
        raw["git_commit"],
        raw["mode"],
        raw["population"],
        attempts,
        gate,
        tuple(raw["forbidden_effects"].items()),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stable_sentence_causal_benchmark")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--mode", choices=("controlled",), required=True)
    prepare.add_argument("--population", choices=("SCREEN",), required=True)
    prepare.add_argument("--output", type=Path, required=True)
    controlled = commands.add_parser("controlled-run")
    controlled.add_argument("--run-json", type=Path, required=True)
    controlled.add_argument("--fixture", type=Path, required=True)
    controlled.add_argument("--output", type=Path, required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--screen", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        source_commit, source_clean = _source_state()
        if args.command == "prepare":
            _prepare(args.output, source_commit=source_commit, source_clean=source_clean)
            return 0
        if args.command == "controlled-run":
            config = StableSentenceBenchmarkConfig(
                args.run_json.resolve(),
                args.output.resolve(),
                "controlled",
                "SCREEN",
                source_commit,
                source_clean,
            )
            asyncio.run(run_controlled_corpus(config, args.fixture.resolve()))
            return 0
        if args.command == "compare":
            report = _load_result(args.screen.resolve())
            _write_private_json(report.gate.to_dict(), args.output.resolve())
            return 0
        return 2
    except (OSError, ValueError, json.JSONDecodeError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
