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
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ResponseRef,
    ScopeRef,
    TurnCommit,
)
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
)
from jiuwenswarm.server.live_voice.speech_ports import SynthesisEventKind
from jiuwenswarm.server.live_voice.stable_sentence_policy import (
    FinalReconciliationDisposition,
    StableSentenceStreamState,
    candidate_content,
    commit_candidate,
    observe_agent_event,
    reconcile_final,
)
from jiuwenswarm.server.live_voice.streaming_speech import (
    SynthesisStreamRef,
    SynthesisStreamRequest,
    TextSpan,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalAgentExecution,
    FormalContextSnapshot,
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
class ProviderCase:
    case_id: str
    prompt: str = field(repr=False)
    minimum_sentence_count: int
    allow_tools: bool


@dataclass(frozen=True, slots=True)
class TimedAgentEvent:
    observed_ms: float
    event: AgentEvent


@dataclass(frozen=True, slots=True)
class BenchmarkTtsTiming:
    request_started_ms: float
    transport_open_ms: float
    first_provider_audio_ms: float
    first_pcm_ms: float
    completed_ms: float
    cleanup_complete: bool

    def __post_init__(self) -> None:
        ordered = (
            self.request_started_ms,
            self.transport_open_ms,
            self.first_provider_audio_ms,
            self.first_pcm_ms,
            self.completed_ms,
        )
        if (
            any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                for value in ordered
            )
            or list(ordered) != sorted(ordered)
            or self.cleanup_complete is not True
        ):
            raise ValueError("STABLE_SENTENCE_TTS_TIMING_INVALID")


class StreamingBenchmarkTtsClient:
    def __init__(self, provider: object, *, monotonic=time.monotonic) -> None:
        if (
            provider is None
            or not callable(getattr(provider, "open_synthesis", None))
            or not callable(getattr(provider, "next_synthesis_event", None))
            or not callable(getattr(provider, "close", None))
            or not callable(monotonic)
        ):
            raise ValueError("STABLE_SENTENCE_TTS_CLIENT_INVALID")
        self._provider = provider
        self._monotonic = monotonic

    async def measure_first_pcm(
        self,
        *,
        response_ref: ResponseRef,
        unit_id: str,
        text_utf8: bytes,
    ) -> BenchmarkTtsTiming:
        if (
            not isinstance(response_ref, ResponseRef)
            or not isinstance(unit_id, str)
            or not unit_id
            or not isinstance(text_utf8, bytes)
            or not text_utf8
        ):
            raise ValueError("STABLE_SENTENCE_TTS_INPUT_INVALID")
        try:
            text = text_utf8.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("STABLE_SENTENCE_TTS_INPUT_INVALID") from error
        request = SynthesisStreamRequest(
            ref=SynthesisStreamRef(
                f"stable-screen-stream-{response_ref.response_generation}",
                response_ref.response_generation,
                response_ref,
                unit_id,
                0,
            ),
            display_text=text,
            spoken_text=text,
            display_span=TextSpan(0, len(text)),
            sample_rate_hz=24_000,
            event_timeout_seconds=20.0,
        )
        started_at = self._monotonic()
        transport_open_at: float | None = None
        first_audio_at: float | None = None
        completed_at: float | None = None

        def on_transport_open() -> None:
            nonlocal transport_open_at
            observed = self._monotonic()
            if transport_open_at is not None or observed < started_at:
                raise ValueError("STABLE_SENTENCE_TTS_PROTOCOL_INVALID")
            transport_open_at = observed

        try:
            conformance = getattr(self._provider, "conformance", None)
            activate = getattr(conformance, "activate_response", None)
            if not callable(activate):
                raise ValueError("STABLE_SENTENCE_TTS_PROTOCOL_INVALID")
            activate(response_ref)
            await asyncio.wait_for(
                self._provider.open_synthesis(
                    request, on_transport_open=on_transport_open
                ),
                timeout=30.0,
            )
            expected_seq = 0
            started = False
            while completed_at is None:
                event = await asyncio.wait_for(
                    self._provider.next_synthesis_event(
                        request.ref, timeout_seconds=20.0
                    ),
                    timeout=30.0,
                )
                if event.ref != request.ref or event.seq != expected_seq:
                    raise ValueError("STABLE_SENTENCE_TTS_PROTOCOL_INVALID")
                expected_seq += 1
                if event.kind is SynthesisEventKind.STARTED:
                    if started or first_audio_at is not None:
                        raise ValueError("STABLE_SENTENCE_TTS_PROTOCOL_INVALID")
                    started = True
                elif event.kind is SynthesisEventKind.CHUNK:
                    if (
                        not started
                        or event.pcm_s16le is None
                        or event.sample_count <= 0
                    ):
                        raise ValueError("STABLE_SENTENCE_TTS_PROTOCOL_INVALID")
                    if first_audio_at is None:
                        first_audio_at = self._monotonic()
                elif event.kind is SynthesisEventKind.COMPLETED:
                    if not started or first_audio_at is None:
                        raise ValueError("STABLE_SENTENCE_TTS_PROTOCOL_INVALID")
                    completed_at = self._monotonic()
                else:
                    raise ValueError("STABLE_SENTENCE_TTS_PROTOCOL_INVALID")
        finally:
            await asyncio.wait_for(self._provider.close(), timeout=5.0)
        clean = bool(
            getattr(getattr(self._provider, "cleanup_snapshot", None), "clean", False)
        )
        if (
            transport_open_at is None
            or first_audio_at is None
            or completed_at is None
            or not clean
        ):
            raise ValueError("STABLE_SENTENCE_TTS_CLEANUP_INVALID")

        def offset(value: float) -> float:
            return max(0.0, (value - started_at) * 1000.0)

        return BenchmarkTtsTiming(
            0.0,
            offset(transport_open_at),
            offset(first_audio_at),
            offset(first_audio_at),
            offset(completed_at),
            True,
        )


class FormalAgentStreamClient:
    def __init__(self, facade: object, *, monotonic=time.monotonic) -> None:
        stream = getattr(facade, "process_formal_live_voice_stream", None)
        if not callable(stream) or not callable(monotonic):
            raise ValueError("STABLE_SENTENCE_AGENT_CLIENT_INVALID")
        self._facade = facade
        self._monotonic = monotonic

    async def stream(self, case: ProviderCase) -> AsyncIterator[TimedAgentEvent]:
        if not isinstance(case, ProviderCase) or case.allow_tools is not False:
            raise ValueError("STABLE_SENTENCE_PROVIDER_CASE_INVALID")
        scope = ScopeRef(
            "stable-screen-subject",
            "stable-screen-project",
            "stable-screen-session",
            Assurance.REQUEST_ASSERTED,
        )
        commit = TurnCommit.from_dict(
            {
                "contract_version": "live-voice.contract.v2",
                "commit_id": f"stable-screen-commit-{case.case_id}",
                "turn_id": f"stable-screen-turn-{case.case_id}",
                "interaction_id": f"stable-screen-interaction-{case.case_id}",
                "text": case.prompt,
                "hypothesis_provenance": {"provider": "stable-screen-public"},
                "scope": scope.to_dict(),
                "context_refs": [],
                "committed_at": "2026-08-21T00:00:00Z",
            }
        )
        execution = FormalAgentExecution(
            request_id="provider-request",
            channel_id="live_voice_latency_screen",
            internal_session_id=f"lv-formal-stable-screen-{case.case_id}",
            commit=commit,
            context=FormalContextSnapshot(scope),
            allow_tools=False,
        )
        started = self._monotonic()
        expected_seq = 0
        final_seen = False
        stream = self._facade.process_formal_live_voice_stream(execution)
        async for chunk in stream:
            if (
                not isinstance(chunk, AgentResponseChunk)
                or chunk.request_id != execution.request_id
                or chunk.channel_id != execution.channel_id
                or not isinstance(chunk.payload, dict)
            ):
                raise ValueError("STABLE_SENTENCE_AGENT_EVENT_INVALID")
            event_type = chunk.payload.get("event_type")
            content = chunk.payload.get("content")
            if event_type in {"chat.tool_call", "chat.tool_result"}:
                raise ValueError("STABLE_SENTENCE_TOOL_EVENT_FORBIDDEN")
            if event_type not in {"chat.delta", "chat.reasoning", "chat.final"}:
                raise ValueError("STABLE_SENTENCE_AGENT_EVENT_INVALID")
            if not isinstance(content, str) or not content:
                raise ValueError("STABLE_SENTENCE_AGENT_EVENT_INVALID")
            if final_seen:
                raise ValueError("STABLE_SENTENCE_AGENT_EVENT_AFTER_FINAL")
            if event_type == "chat.final":
                final_seen = True
            observed = self._monotonic()
            if observed < started:
                raise ValueError("STABLE_SENTENCE_AGENT_CLOCK_INVALID")
            yield TimedAgentEvent(
                (observed - started) * 1000.0,
                AgentEvent(
                    request_id=execution.request_id,
                    interaction_id=commit.interaction_id,
                    turn_id=commit.turn_id,
                    commit_id=commit.commit_id,
                    seq=expected_seq,
                    event_type=event_type,
                    source_provenance="stable-screen-real-agent",
                    text=content,
                    capability="agent.chat",
                ),
            )
            expected_seq += 1
        if not final_seen:
            raise ValueError("STABLE_SENTENCE_AGENT_FINAL_MISSING")


@asynccontextmanager
async def managed_formal_agent_client(project_dir: Path, *, manager_factory=None):
    if (
        not isinstance(project_dir, Path)
        or not project_dir.is_absolute()
        or not project_dir.is_dir()
    ):
        raise ValueError("STABLE_SENTENCE_PROJECT_INVALID")
    if manager_factory is None:
        from jiuwenswarm.server.runtime.agent_manager import AgentManager

        manager_factory = AgentManager
    if not callable(manager_factory):
        raise ValueError("STABLE_SENTENCE_AGENT_MANAGER_INVALID")
    manager = manager_factory()
    cleanup = getattr(manager, "cleanup", None)
    if not callable(cleanup):
        raise ValueError("STABLE_SENTENCE_AGENT_MANAGER_INVALID")
    try:
        facade = await manager.get_agent(
            channel_id="live_voice_latency_screen",
            mode="agent",
            project_dir=str(project_dir),
        )
        yield FormalAgentStreamClient(facade)
    finally:
        await asyncio.wait_for(cleanup(), timeout=10.0)


def create_real_tts_client(
    environ: Mapping[str, str], *, monotonic=time.monotonic
) -> StreamingBenchmarkTtsClient:
    provider_name = str(environ.get(SPEECH_PROVIDER_ENV) or "").strip().lower()
    api_base = str(environ.get(SPEECH_API_BASE_ENV) or "").strip()
    api_key = str(environ.get(SPEECH_API_KEY_ENV) or "").strip()
    model = str(environ.get(SPEECH_TTS_MODEL_ENV) or "").strip()
    voice = str(environ.get(SPEECH_TTS_VOICE_ENV) or "").strip()
    if provider_name != "openai" or not all((api_base, api_key, model, voice)):
        raise ValueError("PROVIDER_UNAVAILABLE")
    provider = OpenAIStreamingSpeechProvider(
        OpenAIStreamingSpeechConfig(
            api_base=api_base,
            api_key=api_key,
            tts_model=model,
            tts_voice=voice,
        ),
        monotonic=monotonic,
    )
    return StreamingBenchmarkTtsClient(provider, monotonic=monotonic)


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
            or self.outcome
            not in {
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
    if (
        not isinstance(path, Path)
        or not path.is_file()
        or path.stat().st_size > MAX_REPORT_BYTES
    ):
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
            or disposition
            not in {item.value for item in FinalReconciliationDisposition}
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


def load_provider_cases(path: Path) -> tuple[ProviderCase, ...]:
    if (
        not isinstance(path, Path)
        or not path.is_file()
        or path.stat().st_size > MAX_REPORT_BYTES
    ):
        raise ValueError("STABLE_SENTENCE_PROVIDER_CASE_INVALID")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("STABLE_SENTENCE_PROVIDER_CASE_INVALID") from error
    if not isinstance(raw, list) or not 2 <= len(raw) <= 16:
        raise ValueError("STABLE_SENTENCE_PROVIDER_CASE_INVALID")
    cases: list[ProviderCase] = []
    for item in raw:
        record = _require_exact_mapping(
            item,
            frozenset({"case_id", "prompt", "minimum_sentence_count", "allow_tools"}),
        )
        case_id = record["case_id"]
        prompt = record["prompt"]
        minimum = record["minimum_sentence_count"]
        if (
            not isinstance(case_id, str)
            or not _SAFE_ID.fullmatch(case_id)
            or not isinstance(prompt, str)
            or not prompt.strip()
            or len(prompt.encode("utf-8")) > 1_024
            or not isinstance(minimum, int)
            or isinstance(minimum, bool)
            or not 2 <= minimum <= 8
            or record["allow_tools"] is not False
        ):
            raise ValueError("STABLE_SENTENCE_PROVIDER_CASE_INVALID")
        cases.append(ProviderCase(case_id, prompt, minimum, False))
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("STABLE_SENTENCE_PROVIDER_CASE_INVALID")
    return tuple(cases)


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
    response = ResponseRef("stable-screen-interaction", "stable-screen-response", 0)
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
                CONTROLLED_FIRST_DELTA_MS + seq * CONTROLLED_FRAGMENT_INTERVAL_MS
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
        reconciled.disposition is FinalReconciliationDisposition.REWRITE_AFTER_COMMIT
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


async def run_provider_attempt(
    *,
    population: str,
    case: ProviderCase,
    attempt_index: int,
    agent: FormalAgentStreamClient,
    tts: object,
) -> StableSentenceAttempt:
    if (
        population not in {"SCREEN", "A1", "B", "A2"}
        or not isinstance(case, ProviderCase)
        or not isinstance(attempt_index, int)
        or attempt_index < 0
        or not isinstance(agent, FormalAgentStreamClient)
        or not callable(getattr(tts, "measure_first_pcm", None))
    ):
        raise ValueError("STABLE_SENTENCE_PROVIDER_ATTEMPT_INVALID")
    response = ResponseRef(
        f"stable-screen-interaction-{case.case_id}",
        f"stable-screen-response-{case.case_id}",
        attempt_index,
    )
    state = StableSentenceStreamState.create(response)
    first_delta_ms: float | None = None
    candidate_detected_ms: float | None = None
    final_ms: float | None = None
    final_text: str | None = None
    candidate_count = discard_count = 0
    tts_task: asyncio.Task[BenchmarkTtsTiming] | None = None
    try:
        async for timed in agent.stream(case):
            event = timed.event
            if event.event_type == "chat.final":
                final_ms = timed.observed_ms
                final_text = event.text
                continue
            if event.event_type == "chat.delta" and first_delta_ms is None:
                first_delta_ms = timed.observed_ms
            observation = observe_agent_event(state, event)
            state = observation.state
            discard_count += len(observation.discarded_candidate_ids)
            if observation.candidate is not None and tts_task is None:
                candidate = observation.candidate
                content = candidate_content(state, candidate)
                candidate_detected_ms = timed.observed_ms
                candidate_count = 1
                state = commit_candidate(state, candidate.candidate_id).state
                tts_task = asyncio.create_task(
                    tts.measure_first_pcm(
                        response_ref=response,
                        unit_id=candidate.candidate_id,
                        text_utf8=content,
                    ),
                    name=f"stable-sentence-screen-tts:{case.case_id}",
                )
        if final_ms is None or not isinstance(final_text, str):
            raise ValueError("STABLE_SENTENCE_AGENT_FINAL_MISSING")
        if first_delta_ms is None or candidate_detected_ms is None or tts_task is None:
            if tts_task is not None:
                await tts_task
            return StableSentenceAttempt.noncompleted(
                population=population,
                case_id=case.case_id,
                attempt_index=attempt_index,
                outcome="integrity_failure",
                reason="NO_STABLE_CANDIDATE",
                first_delta_ms=first_delta_ms,
                candidate_detected_ms=candidate_detected_ms,
                final_ms=final_ms,
                candidate_count=candidate_count,
                discard_count=discard_count,
                prefix_match_count=0,
                prefix_mismatch_count=0,
                correction_count=0,
            )
        timing = await tts_task
        reconciled = reconcile_final(state, final_text)
        mismatch = int(
            reconciled.disposition
            is FinalReconciliationDisposition.REWRITE_AFTER_COMMIT
        )
        if mismatch:
            return StableSentenceAttempt.noncompleted(
                population=population,
                case_id=case.case_id,
                attempt_index=attempt_index,
                outcome="integrity_failure",
                reason="PREFIX_MISMATCH",
                first_delta_ms=first_delta_ms,
                candidate_detected_ms=candidate_detected_ms,
                final_ms=final_ms,
                candidate_count=candidate_count,
                discard_count=discard_count,
                prefix_match_count=0,
                prefix_mismatch_count=1,
                correction_count=1,
            )
        if reconciled.disposition is not FinalReconciliationDisposition.EXACT_PREFIX:
            return StableSentenceAttempt.noncompleted(
                population=population,
                case_id=case.case_id,
                attempt_index=attempt_index,
                outcome="integrity_failure",
                reason="FINAL_RECONCILIATION_INVALID",
                first_delta_ms=first_delta_ms,
                candidate_detected_ms=candidate_detected_ms,
                final_ms=final_ms,
                candidate_count=candidate_count,
                discard_count=discard_count,
                prefix_match_count=0,
                prefix_mismatch_count=0,
                correction_count=0,
            )
        return StableSentenceAttempt.completed(
            population=population,
            case_id=case.case_id,
            attempt_index=attempt_index,
            first_delta_ms=first_delta_ms,
            candidate_detected_ms=candidate_detected_ms,
            final_ms=final_ms,
            baseline_first_pcm_ms=final_ms + timing.first_pcm_ms,
            candidate_first_pcm_ms=candidate_detected_ms + timing.first_pcm_ms,
            candidate_count=candidate_count,
            discard_count=discard_count,
            prefix_match_count=1,
            prefix_mismatch_count=0,
            correction_count=0,
        )
    except BaseException:
        if tts_task is not None and not tts_task.done():
            tts_task.cancel()
            await asyncio.gather(tts_task, return_exceptions=True)
        raise


def _provider_batch(
    config: StableSentenceBenchmarkConfig,
    attempt: StableSentenceAttempt,
    *,
    round_index: int,
) -> LatencyBatch:
    clock = _ManualClock()
    context = LatencyProbeContext(
        CONTEXT_SCHEMA_VERSION,
        config.run.run_id,
        "dialogue_no_tool",
        config.run.input_case_for_profile("dialogue_no_tool") or "",
        round_index,
    )
    recorder = LatencyProbeRecorder(
        context=context,
        component="agent_server",
        phase="agent_foreground",
        run_config=config.run,
        source_instance_id_factory=lambda: "stable-provider-agent-source",
        batch_id_factory=lambda: f"stable-provider-batch-{round_index}",
        clock_domain_id="stable-provider-agent-clock",
        monotonic_ms=clock.now,
    )

    def mark(point: str, timestamp: float) -> None:
        clock.value = timestamp
        accepted = recorder.mark(
            point,
            correlation_id="stable-provider-correlation",
            interaction_id=f"stable-screen-interaction-{attempt.case_id}",
            activation_id="stable-provider-activation",
            activation_generation=1,
            turn_id=f"stable-screen-turn-{attempt.case_id}",
            response_id=f"stable-screen-response-{attempt.case_id}",
            response_generation=round_index,
        )
        if not accepted:
            raise ValueError("STABLE_SENTENCE_PROBE_MARK_REJECTED")

    mark("agent.agent_started", 0.0)
    if attempt.first_delta_ms is not None:
        mark("agent.agent_first_delta", attempt.first_delta_ms)
    if attempt.candidate_detected_ms is not None:
        mark("agent.sentence_candidate_detected", attempt.candidate_detected_ms)
    if attempt.final_ms is not None:
        mark("agent.agent_final", attempt.final_ms)
    batch = recorder.finish("completed" if attempt.outcome == "completed" else "failed")
    if batch is None:
        raise ValueError("STABLE_SENTENCE_PROBE_FINISH_FAILED")
    return batch


async def run_provider_corpus(
    config: StableSentenceBenchmarkConfig,
    cases_path: Path,
    *,
    agent: FormalAgentStreamClient,
    tts_factory,
) -> StableSentenceCausalResult:
    if config.mode not in {"provider-pilot", "run"} or not callable(tts_factory):
        raise ValueError("STABLE_SENTENCE_PROVIDER_CONFIG_INVALID")
    cases = load_provider_cases(cases_path)
    attempts_per_case = 1 if config.mode == "provider-pilot" else 5
    expected_attempts = len(cases) * attempts_per_case
    if config.run.intended_attempts != expected_attempts:
        raise ValueError("STABLE_SENTENCE_ATTEMPT_POLICY_MISMATCH")
    writer = LatencyProbeBatchWriter(
        config.run_json.parent.parent, config.run, "agent_server"
    )
    attempts: list[StableSentenceAttempt] = []
    batches: list[LatencyBatch] = []
    round_index = 0
    for case in cases:
        for _case_attempt in range(attempts_per_case):
            try:
                tts = tts_factory()
                attempt = await run_provider_attempt(
                    population=config.population,
                    case=case,
                    attempt_index=round_index,
                    agent=agent,
                    tts=tts,
                )
            except (KeyboardInterrupt, SystemExit, GeneratorExit):
                raise
            except asyncio.CancelledError:
                raise
            except Exception:
                attempt = StableSentenceAttempt.noncompleted(
                    population=config.population,
                    case_id=case.case_id,
                    attempt_index=round_index,
                    outcome="failed",
                    reason="AGENT_OR_TTS_FAILED",
                    first_delta_ms=None,
                    candidate_detected_ms=None,
                    final_ms=None,
                    candidate_count=0,
                    discard_count=0,
                    prefix_match_count=0,
                    prefix_mismatch_count=0,
                    correction_count=0,
                )
            batch = _provider_batch(config, attempt, round_index=round_index)
            receipt = writer.write(batch)
            if receipt.status not in {"written", "replayed"}:
                raise ValueError("STABLE_SENTENCE_BATCH_WRITE_FAILED")
            attempts.append(attempt)
            batches.append(batch)
            round_index += 1
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
    encoded = (
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    )
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


def prepare_provider_run(
    output_path: Path,
    cases_path: Path,
    *,
    mode: str,
    population: str,
    source_commit: str,
    source_clean: bool,
    environ: Mapping[str, str],
) -> Path:
    cases = load_provider_cases(cases_path)
    provider = str(environ.get(SPEECH_PROVIDER_ENV) or "").strip().lower()
    api_base = str(environ.get(SPEECH_API_BASE_ENV) or "").strip()
    api_key = str(environ.get(SPEECH_API_KEY_ENV) or "").strip()
    model = str(environ.get(SPEECH_TTS_MODEL_ENV) or "").strip()
    voice = str(environ.get(SPEECH_TTS_VOICE_ENV) or "").strip()
    if (
        not isinstance(output_path, Path)
        or not output_path.is_absolute()
        or output_path.exists()
        or mode not in {"provider-pilot", "run"}
        or population not in {"SCREEN", "A1", "B", "A2"}
        or (mode == "provider-pilot" and population != "SCREEN")
        or not _GIT_SHA.fullmatch(source_commit)
        or not source_clean
        or provider != "openai"
        or not all((api_base, api_key, model, voice))
        or not all(
            re.fullmatch(r"[A-Za-z0-9._-]{1,128}", item) for item in (model, voice)
        )
    ):
        raise ValueError("STABLE_SENTENCE_PROVIDER_CONFIG_INVALID")
    attempts_per_case = 1 if mode == "provider-pilot" else 5
    intended_attempts = len(cases) * attempts_per_case
    run_path = output_path.parent / "run.json"
    payload = {
        "schema_version": "live-voice.latency-run.v1",
        "run_id": output_path.parent.name,
        "git_commit": source_commit,
        "source_state": "clean",
        "environment_profile": "real-agent-real-tts-no-chrome",
        "browser_family_and_version": "not-exercised",
        "browser_os_class": "not-exercised",
        "gateway_runtime_class": "direct-provider-client",
        "agent_runtime_class": "formal-agent-no-tools",
        "stt_provider_and_model": "not-exercised",
        "tts_provider_and_model": f"openai-{model}-{voice}",
        "audio_format": "pcm16-24000hz-mono",
        "vad_configuration": "not-exercised",
        "playout_configuration": "not-exercised",
        "allowlisted_feature_flags": {
            "latency_probe": True,
            "stable_sentence_tts": population == "B",
        },
        "cold_or_warm": "warm",
        "input_case_ids": ["stable-sentence-provider-v1"],
        "profile_ids": ["dialogue_no_tool"],
        "intended_attempts": intended_attempts,
        "required_successes": len(cases),
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
        "fixture_profile_id": "stable-sentence-provider-v1",
    }
    run = _parse_latency_run_config(payload)
    _write_private_json(run.to_dict(), run_path)
    return run_path


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
    provider = commands.add_parser("provider-run")
    provider.add_argument("--mode", choices=("provider-pilot", "run"), required=True)
    provider.add_argument(
        "--population", choices=("SCREEN", "A1", "B", "A2"), required=True
    )
    provider.add_argument("--project-dir", type=Path, required=True)
    provider.add_argument("--cases", type=Path, required=True)
    provider.add_argument("--output", type=Path, required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--screen", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    return parser


def _require_disposable_project(path: Path) -> Path:
    resolved = path.resolve()
    if (
        not path.is_absolute()
        or not resolved.is_dir()
        or resolved == REPOSITORY_ROOT
        or REPOSITORY_ROOT in resolved.parents
    ):
        raise ValueError("STABLE_SENTENCE_PROJECT_INVALID")
    inside = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=resolved,
        check=False,
        capture_output=True,
        text=True,
    )
    remotes = subprocess.run(
        ["git", "remote"],
        cwd=resolved,
        check=False,
        capture_output=True,
        text=True,
    )
    if (
        inside.returncode != 0
        or inside.stdout.strip() != "true"
        or remotes.returncode != 0
        or remotes.stdout.strip()
    ):
        raise ValueError("STABLE_SENTENCE_PROJECT_INVALID")
    return resolved


async def _run_real_provider_command(
    args: argparse.Namespace,
    *,
    source_commit: str,
    source_clean: bool,
) -> None:
    project = _require_disposable_project(args.project_dir)
    output = args.output.resolve()
    cases = args.cases.resolve()
    run_path = prepare_provider_run(
        output,
        cases,
        mode=args.mode,
        population=args.population,
        source_commit=source_commit,
        source_clean=source_clean,
        environ=os.environ,
    )
    config = StableSentenceBenchmarkConfig(
        run_path,
        output,
        args.mode,
        args.population,
        source_commit,
        source_clean,
    )
    async with managed_formal_agent_client(project) as agent:
        await run_provider_corpus(
            config,
            cases,
            agent=agent,
            tts_factory=lambda: create_real_tts_client(os.environ),
        )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        source_commit, source_clean = _source_state()
        if args.command == "prepare":
            _prepare(
                args.output, source_commit=source_commit, source_clean=source_clean
            )
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
        if args.command == "provider-run":
            asyncio.run(
                _run_real_provider_command(
                    args,
                    source_commit=source_commit,
                    source_clean=source_clean,
                )
            )
            final_commit, final_clean = _source_state()
            if final_commit != source_commit or final_clean is not True:
                raise ValueError("STABLE_SENTENCE_SOURCE_CHANGED")
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
