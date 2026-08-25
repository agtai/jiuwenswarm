# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Real-Agent/real-TTS no-Browser A1/B/A2 first-PCM screen."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Iterable

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import EventEnvelope, ResponseRef
from jiuwenswarm.server.live_voice.agent_latency_probe import (
    AgentForegroundStreamProbeHooks,
)
from jiuwenswarm.server.live_voice.batch_speech import (
    SPEECH_API_BASE_ENV,
    SPEECH_API_KEY_ENV,
    SPEECH_PROVIDER_ENV,
    SPEECH_STT_MODEL_ENV,
    SPEECH_TTS_MODEL_ENV,
    SPEECH_TTS_VOICE_ENV,
)
from jiuwenswarm.server.live_voice.jiuwenswarm_round_harness import (
    HarnessRoundBinding,
    JiuWenSwarmRoundHarness,
)
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    DEFAULT_STT_MODEL,
    OpenAIStreamingSpeechConfig,
    OpenAIStreamingSpeechProvider,
)
from jiuwenswarm.server.live_voice.speech_ports import SynthesisEventKind
from jiuwenswarm.server.live_voice.stable_sentence_policy import (
    FinalReconciliationDisposition,
    StableSentenceStreamState,
    StableSentenceViolation,
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
    FormalContextSnapshot,
)
if __package__:
    from scripts.live_voice import pre_final_stable_segmentation_screen as prefix_screen
else:
    import pre_final_stable_segmentation_screen as prefix_screen


REPORT_SCHEMA_VERSION = "live-voice.pre-final-stable-agent-tts-screen.v0"
ARMS = ("A1", "B", "A2")
MINIMUM_GAIN_MS = 400.0
MINIMUM_RELATIVE_GAIN_PERCENT = 10.0
MAX_CONTROL_DRIFT_MS = 400.0
MAX_CONTROL_DRIFT_PERCENT = 20.0
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
Workload = prefix_screen.Workload
WORKLOADS = prefix_screen.WORKLOADS
ZERO_FORBIDDEN_EFFECTS = dict(prefix_screen.ZERO_FORBIDDEN_EFFECTS)


@dataclass(frozen=True, slots=True)
class TtsTiming:
    dispatch_to_request_ms: float
    request_to_first_pcm_ms: float


@dataclass(frozen=True, slots=True)
class Attempt:
    arm: str
    workload_id: str
    attempt_index: int
    outcome: str
    reason: str
    agent_to_candidate_ms: float | None
    candidate_to_final_ms: float | None
    agent_to_final_ms: float | None
    tts_dispatch_to_request_ms: float | None
    tts_request_to_first_pcm_ms: float | None
    agent_to_first_pcm_ms: float | None
    prefix_exact: bool
    terminal_outcome: str
    authorized_agent_calls: int
    authorized_tts_calls: int
    forbidden_effects: dict[str, int]

    @classmethod
    def completed(
        cls,
        *,
        arm: str,
        workload_id: str,
        attempt_index: int,
        agent_to_candidate_ms: float,
        candidate_to_final_ms: float,
        agent_to_final_ms: float,
        tts_dispatch_to_request_ms: float,
        tts_request_to_first_pcm_ms: float,
        agent_to_first_pcm_ms: float,
    ) -> Attempt:
        return cls(
            arm,
            workload_id,
            attempt_index,
            "completed",
            "OK",
            agent_to_candidate_ms,
            candidate_to_final_ms,
            agent_to_final_ms,
            tts_dispatch_to_request_ms,
            tts_request_to_first_pcm_ms,
            agent_to_first_pcm_ms,
            True,
            "completed",
            1,
            1,
            dict(ZERO_FORBIDDEN_EFFECTS),
        )

    @classmethod
    def failed(
        cls,
        *,
        arm: str,
        workload_id: str,
        attempt_index: int,
        reason: str,
        terminal_outcome: str = "failed",
        agent_calls: int = 1,
        tts_calls: int = 0,
    ) -> Attempt:
        return cls(
            arm,
            workload_id,
            attempt_index,
            "failed",
            reason,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            terminal_outcome,
            agent_calls,
            tts_calls,
            dict(ZERO_FORBIDDEN_EFFECTS),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "arm": self.arm,
            "workload_id": self.workload_id,
            "attempt_index": self.attempt_index,
            "outcome": self.outcome,
            "reason": self.reason,
            "agent_to_candidate_ms": self.agent_to_candidate_ms,
            "candidate_to_final_ms": self.candidate_to_final_ms,
            "agent_to_final_ms": self.agent_to_final_ms,
            "tts_dispatch_to_request_ms": self.tts_dispatch_to_request_ms,
            "tts_request_to_first_pcm_ms": self.tts_request_to_first_pcm_ms,
            "agent_to_first_pcm_ms": self.agent_to_first_pcm_ms,
            "prefix_exact": self.prefix_exact,
            "terminal_outcome": self.terminal_outcome,
            "authorized_agent_calls": self.authorized_agent_calls,
            "authorized_tts_calls": self.authorized_tts_calls,
            "forbidden_effects": self.forbidden_effects,
        }


class StreamingTtsClient:
    def __init__(self, provider: object, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._provider = provider
        self._monotonic = monotonic

    async def measure_first_pcm(
        self,
        *,
        response_ref: ResponseRef,
        unit_id: str,
        text_utf8: bytes,
        dispatched_at: float,
    ) -> TtsTiming:
        text = text_utf8.decode("utf-8")
        request = SynthesisStreamRequest(
            ref=SynthesisStreamRef(
                f"stable-ab-stream-{response_ref.response_id}",
                response_ref.response_generation,
                response_ref,
                unit_id,
                0,
            ),
            display_text=text,
            spoken_text=text,
            display_span=TextSpan(0, len(text)),
            sample_rate_hz=24_000,
            event_timeout_seconds=30.0,
        )
        started_at = self._monotonic()
        if started_at < dispatched_at:
            raise ValueError("TTS_REQUEST_STARTED_BEFORE_DISPATCH")
        first_pcm_at: float | None = None
        expected_seq = 0
        started = False
        completed = False
        try:
            activate = getattr(getattr(self._provider, "conformance", None), "activate_response", None)
            if not callable(activate):
                raise ValueError("TTS_CONFORMANCE_UNAVAILABLE")
            activate(response_ref)
            await asyncio.wait_for(self._provider.open_synthesis(request), timeout=30)
            while not completed:
                event = await asyncio.wait_for(
                    self._provider.next_synthesis_event(
                        request.ref, timeout_seconds=30.0
                    ),
                    timeout=35,
                )
                if event.ref != request.ref or event.seq != expected_seq:
                    raise ValueError("TTS_EVENT_SEQUENCE_INVALID")
                expected_seq += 1
                if event.kind is SynthesisEventKind.STARTED:
                    if started:
                        raise ValueError("TTS_DUPLICATE_STARTED")
                    started = True
                elif event.kind is SynthesisEventKind.CHUNK:
                    if not started or event.sample_count <= 0 or not event.pcm_s16le:
                        raise ValueError("TTS_CHUNK_INVALID")
                    if first_pcm_at is None:
                        first_pcm_at = self._monotonic()
                elif event.kind is SynthesisEventKind.COMPLETED:
                    if not started or first_pcm_at is None:
                        raise ValueError("TTS_COMPLETED_BEFORE_PCM")
                    completed = True
                else:
                    raise ValueError("TTS_TERMINAL_INVALID")
        finally:
            await asyncio.wait_for(self._provider.close(), timeout=10)
        cleanup = getattr(self._provider, "cleanup_snapshot", None)
        if first_pcm_at is None or getattr(cleanup, "clean", False) is not True:
            raise ValueError("TTS_CLEANUP_INCOMPLETE")
        return TtsTiming(
            (started_at - dispatched_at) * 1000.0,
            (first_pcm_at - started_at) * 1000.0,
        )


def create_real_tts_client(environ: dict[str, str]) -> StreamingTtsClient:
    provider = str(environ.get(SPEECH_PROVIDER_ENV) or "").strip().lower()
    api_base = str(environ.get(SPEECH_API_BASE_ENV) or "").strip()
    api_key = str(environ.get(SPEECH_API_KEY_ENV) or "").strip()
    stt_model = str(environ.get(SPEECH_STT_MODEL_ENV) or "").strip() or DEFAULT_STT_MODEL
    tts_model = str(environ.get(SPEECH_TTS_MODEL_ENV) or "").strip()
    voice = str(environ.get(SPEECH_TTS_VOICE_ENV) or "").strip()
    if provider != "openai" or not all((api_base, api_key, tts_model, voice)):
        raise ValueError("REAL_TTS_CONFIGURATION_UNAVAILABLE")
    config = OpenAIStreamingSpeechConfig(
        api_base=api_base,
        api_key=api_key,
        stt_model=stt_model,
        tts_model=tts_model,
        tts_voice=voice,
    )
    return StreamingTtsClient(OpenAIStreamingSpeechProvider(config))


async def measure_attempt(
    facade: object,
    workload: Workload,
    arm: str,
    attempt_index: int,
    *,
    tts: object,
    monotonic: Callable[[], float] = time.monotonic,
    timeout_seconds: float = 240.0,
) -> Attempt:
    if arm not in ARMS:
        raise ValueError("INVALID_ABA_ARM")
    commit = prefix_screen._turn_commit(workload, attempt_index)
    suffix = f"{arm.lower()}-{commit.turn_id.removeprefix('turn-')}"
    binding = HarnessRoundBinding(
        request_id=f"request-{suffix}",
        response_id=f"response-{suffix}",
        correlation_id=f"correlation-{suffix}",
        commit=commit,
    )
    response_ref = ResponseRef(commit.interaction_id, binding.response_id, 0)
    harness = JiuWenSwarmRoundHarness(
        instance_id=f"stable-agent-tts-{suffix}",
        max_active_rounds=1,
        output_capacity=64,
    )
    state = StableSentenceStreamState.create(response_ref)
    started_at: float | None = None
    candidate_at: float | None = None
    final_at: float | None = None
    terminal_outcome = "unknown"
    failure_reason: str | None = None
    policy_seq = 0
    final_seen = False
    tts_task: asyncio.Task[TtsTiming] | None = None
    tts_timing: TtsTiming | None = None
    tts_calls = 0
    handle = None

    def mark_started() -> None:
        nonlocal started_at
        if started_at is None:
            started_at = monotonic()

    try:
        reservation = harness.reserve_round(binding, facade=facade)
        harness.begin_round_commit(reservation)
        handle = harness.commit_round(
            reservation,
            response_ref=response_ref,
            context=FormalContextSnapshot(commit.scope),
            facade=facade,
            channel_id="live_voice_pre_final_stable_agent_tts_screen",
            allow_tools=False,
            latency_probe_hooks=AgentForegroundStreamProbeHooks(
                mark_started=mark_started,
                mark_first_visible_delta=lambda: None,
            ),
        )
        async with asyncio.timeout(timeout_seconds):
            async for item in handle.events():
                if isinstance(item, AgentResponseChunk):
                    payload = item.payload if isinstance(item.payload, dict) else {}
                    event_type = payload.get("event_type")
                    content = payload.get("content")
                    if event_type in {"chat.tool_call", "chat.tool_result"}:
                        failure_reason = "FORBIDDEN_TOOL_EVENT"
                    elif event_type == "chat.error":
                        failure_reason = "AGENT_REPORTED_ERROR"
                    elif event_type == "chat.delta" and isinstance(content, str) and content:
                        if candidate_at is not None:
                            continue
                        observation = observe_agent_event(
                            state,
                            prefix_screen._policy_event(
                                commit=commit,
                                request_id=binding.request_id,
                                seq=policy_seq,
                                text=content,
                            ),
                        )
                        policy_seq += 1
                        state = observation.state
                        if observation.candidate is not None:
                            candidate_at = monotonic()
                            candidate = observation.candidate
                            candidate_bytes = candidate_content(state, candidate)
                            state = commit_candidate(state, candidate.candidate_id).state
                            if arm == "B":
                                tts_calls = 1
                                tts_task = asyncio.create_task(
                                    tts.measure_first_pcm(
                                        response_ref=response_ref,
                                        unit_id=candidate.candidate_id,
                                        text_utf8=candidate_bytes,
                                        dispatched_at=candidate_at,
                                    )
                                )
                    elif event_type == "chat.final":
                        if final_seen or not isinstance(content, str) or not content.strip():
                            failure_reason = "INVALID_OR_DUPLICATE_FINAL"
                        else:
                            final_seen = True
                            final_at = monotonic()
                            reconciliation = reconcile_final(state, content)
                            if (
                                reconciliation.disposition
                                is not FinalReconciliationDisposition.EXACT_PREFIX
                                or reconciliation.correction_required
                            ):
                                failure_reason = "PREFIX_RECONCILIATION_FAILED"
                            if arm in {"A1", "A2"}:
                                tts_calls = 1
                                tts_task = asyncio.create_task(
                                    tts.measure_first_pcm(
                                        response_ref=response_ref,
                                        unit_id=f"final-{arm.lower()}-{attempt_index}",
                                        text_utf8=content.encode("utf-8"),
                                        dispatched_at=final_at,
                                    )
                                )
                elif isinstance(item, EventEnvelope):
                    payload = item.payload
                    if payload.get("state") == "terminal":
                        terminal_outcome = str(payload.get("outcome", "unknown"))
            if tts_task is None:
                failure_reason = failure_reason or "TTS_REQUEST_MISSING"
                tts_timing = None
            else:
                tts_timing = await asyncio.wait_for(tts_task, timeout=120)
    except TimeoutError:
        failure_reason = failure_reason or "AGENT_OR_TTS_TIMED_OUT"
        tts_timing = None
        if handle is not None and handle.terminal_event is None:
            try:
                terminal_outcome = await prefix_screen._cancel_and_wait_terminal(
                    handle, binding
                )
            except Exception:
                failure_reason = "ROUND_CANCEL_FAILED"
    except asyncio.CancelledError:
        if tts_task is not None and not tts_task.done():
            tts_task.cancel()
            await asyncio.gather(tts_task, return_exceptions=True)
        if handle is not None and handle.terminal_event is None:
            try:
                await prefix_screen._cancel_and_wait_terminal(handle, binding)
            except Exception:
                pass
        raise
    except StableSentenceViolation as error:
        failure_reason = error.reason
        tts_timing = None
        if handle is not None and handle.terminal_event is None:
            try:
                terminal_outcome = await prefix_screen._cancel_and_wait_terminal(
                    handle, binding
                )
            except Exception:
                failure_reason = "ROUND_CANCEL_FAILED"
    except (KeyboardInterrupt, SystemExit):
        if handle is not None and handle.terminal_event is None:
            try:
                await prefix_screen._cancel_and_wait_terminal(handle, binding)
            except Exception:
                pass
        raise
    except Exception:
        failure_reason = failure_reason or "AGENT_OR_TTS_FAILED"
        tts_timing = None
        if handle is not None and handle.terminal_event is None:
            try:
                terminal_outcome = await prefix_screen._cancel_and_wait_terminal(
                    handle, binding
                )
            except Exception:
                failure_reason = "ROUND_CANCEL_FAILED"
    finally:
        if tts_task is not None and not tts_task.done():
            tts_task.cancel()
            await asyncio.gather(tts_task, return_exceptions=True)
        try:
            await asyncio.wait_for(harness.close(), timeout=10)
        except Exception:
            failure_reason = "HARNESS_CLEANUP_FAILED"

    if terminal_outcome != "completed":
        failure_reason = failure_reason or "TERMINAL_NOT_COMPLETED"
    if started_at is None or candidate_at is None or final_at is None:
        failure_reason = failure_reason or "AGENT_TIMING_INCOMPLETE"
    if (
        tts_timing is None
        or not math.isfinite(tts_timing.dispatch_to_request_ms)
        or tts_timing.dispatch_to_request_ms < 0
        or not math.isfinite(tts_timing.request_to_first_pcm_ms)
        or tts_timing.request_to_first_pcm_ms < 0
    ):
        failure_reason = failure_reason or "TTS_TIMING_INVALID"
    if (
        failure_reason is None
        and started_at is not None
        and candidate_at is not None
        and final_at is not None
        and not started_at <= candidate_at <= final_at
    ):
        failure_reason = "AGENT_TIMING_ORDER_INVALID"
    if failure_reason is not None:
        return Attempt.failed(
            arm=arm,
            workload_id=workload.workload_id,
            attempt_index=attempt_index,
            reason=failure_reason,
            terminal_outcome=terminal_outcome,
            tts_calls=tts_calls,
        )
    assert started_at is not None and candidate_at is not None and final_at is not None
    assert tts_timing is not None
    candidate_offset_ms = (candidate_at - started_at) * 1000.0
    final_offset_ms = (final_at - started_at) * 1000.0
    trigger_offset_ms = candidate_offset_ms if arm == "B" else final_offset_ms
    return Attempt.completed(
        arm=arm,
        workload_id=workload.workload_id,
        attempt_index=attempt_index,
        agent_to_candidate_ms=candidate_offset_ms,
        candidate_to_final_ms=(final_at - candidate_at) * 1000.0,
        agent_to_final_ms=final_offset_ms,
        tts_dispatch_to_request_ms=tts_timing.dispatch_to_request_ms,
        tts_request_to_first_pcm_ms=tts_timing.request_to_first_pcm_ms,
        agent_to_first_pcm_ms=(
            trigger_offset_ms
            + tts_timing.dispatch_to_request_ms
            + tts_timing.request_to_first_pcm_ms
        ),
    )


def _p50(values: Iterable[float]) -> float | None:
    return prefix_screen._percentile(values, 0.50)


def _p95(values: Iterable[float]) -> float | None:
    return prefix_screen._percentile(values, 0.95)


def build_report(
    *,
    mode: str,
    git_commit: str,
    agent_core_commit: str,
    attempts: tuple[Attempt, ...],
) -> dict[str, object]:
    count = 1 if mode == "pilot" else 5
    expected_slots = tuple(
        (arm, workload.workload_id, index)
        for arm in ARMS
        for workload in WORKLOADS
        for index in range(count)
    )
    actual_slots = tuple(
        (attempt.arm, attempt.workload_id, attempt.attempt_index)
        for attempt in attempts
    )
    integrity_pass = (
        actual_slots == expected_slots
        and all(attempt.outcome == "completed" and attempt.prefix_exact for attempt in attempts)
        and all(attempt.authorized_agent_calls == 1 and attempt.authorized_tts_calls == 1 for attempt in attempts)
    )
    summaries: dict[str, object] = {}
    candidate_pass = integrity_pass
    for workload in WORKLOADS:
        arm_values: dict[str, dict[str, object]] = {}
        for arm in ARMS:
            selected = [
                attempt
                for attempt in attempts
                if attempt.workload_id == workload.workload_id
                and attempt.arm == arm
                and attempt.outcome == "completed"
                and attempt.agent_to_first_pcm_ms is not None
            ]
            first_pcm = [attempt.agent_to_first_pcm_ms for attempt in selected if attempt.agent_to_first_pcm_ms is not None]
            arm_values[arm] = {
                "completed": len(selected),
                "agent_to_candidate_p50_ms": _p50(
                    attempt.agent_to_candidate_ms
                    for attempt in selected
                    if attempt.agent_to_candidate_ms is not None
                ),
                "agent_to_candidate_p95_nearest_rank_ms": _p95(
                    attempt.agent_to_candidate_ms
                    for attempt in selected
                    if attempt.agent_to_candidate_ms is not None
                ),
                "candidate_to_final_p50_ms": _p50(
                    attempt.candidate_to_final_ms
                    for attempt in selected
                    if attempt.candidate_to_final_ms is not None
                ),
                "candidate_to_final_p95_nearest_rank_ms": _p95(
                    attempt.candidate_to_final_ms
                    for attempt in selected
                    if attempt.candidate_to_final_ms is not None
                ),
                "agent_to_final_p50_ms": _p50(
                    attempt.agent_to_final_ms
                    for attempt in selected
                    if attempt.agent_to_final_ms is not None
                ),
                "agent_to_final_p95_nearest_rank_ms": _p95(
                    attempt.agent_to_final_ms
                    for attempt in selected
                    if attempt.agent_to_final_ms is not None
                ),
                "tts_dispatch_to_request_p50_ms": _p50(
                    attempt.tts_dispatch_to_request_ms
                    for attempt in selected
                    if attempt.tts_dispatch_to_request_ms is not None
                ),
                "agent_to_first_pcm_p50_ms": _p50(first_pcm),
                "agent_to_first_pcm_p95_nearest_rank_ms": _p95(first_pcm),
                "tts_request_to_first_pcm_p50_ms": _p50(
                    attempt.tts_request_to_first_pcm_ms
                    for attempt in selected
                    if attempt.tts_request_to_first_pcm_ms is not None
                ),
            }
        a1 = arm_values["A1"]["agent_to_first_pcm_p50_ms"]
        b = arm_values["B"]["agent_to_first_pcm_p50_ms"]
        a2 = arm_values["A2"]["agent_to_first_pcm_p50_ms"]
        if all(isinstance(value, float) for value in (a1, b, a2)):
            assert isinstance(a1, float) and isinstance(b, float) and isinstance(a2, float)
            interpolated = (a1 + a2) / 2.0
            gain = interpolated - b
            relative = 100.0 * gain / interpolated if interpolated > 0 else None
            drift = abs(a1 - a2)
            drift_percent = 100.0 * drift / min(a1, a2) if min(a1, a2) > 0 else None
        else:
            interpolated = gain = relative = drift = drift_percent = None
        workload_pass = bool(
            integrity_pass
            and gain is not None
            and relative is not None
            and drift is not None
            and drift_percent is not None
            and gain >= MINIMUM_GAIN_MS
            and relative >= MINIMUM_RELATIVE_GAIN_PERCENT
            and drift <= MAX_CONTROL_DRIFT_MS
            and drift_percent <= MAX_CONTROL_DRIFT_PERCENT
        )
        candidate_pass = candidate_pass and workload_pass
        summaries[workload.workload_id] = {
            "arms": arm_values,
            "interpolated_control_p50_ms": interpolated,
            "gain_vs_interpolated_control_ms": gain,
            "relative_gain_percent": relative,
            "a1_a2_drift_ms": drift,
            "a1_a2_drift_percent": drift_percent,
            "candidate_pass": workload_pass,
        }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "agent_core_commit": agent_core_commit,
        "measurement_boundary": "agent_started_to_tts_first_pcm",
        "arm_contract": {"A1": "chat_final", "B": "exact_prefix_candidate", "A2": "chat_final"},
        "status": "PASS" if integrity_pass else "FAIL",
        "decision": (
            "CANDIDATE_ACCEPTED"
            if candidate_pass and mode == "run"
            else "PILOT_PASS"
            if candidate_pass
            else "CANDIDATE_REJECTED"
            if integrity_pass
            else "INTEGRITY_FAILED"
        ),
        "p95_method": "nearest_rank_small_population",
        "minimum_gain_ms": MINIMUM_GAIN_MS,
        "minimum_relative_gain_percent": MINIMUM_RELATIVE_GAIN_PERCENT,
        "maximum_control_drift_ms": MAX_CONTROL_DRIFT_MS,
        "maximum_control_drift_percent": MAX_CONTROL_DRIFT_PERCENT,
        "attempts": [attempt.to_dict() for attempt in attempts],
        "summaries": summaries,
        "authorized_agent_calls": sum(attempt.authorized_agent_calls for attempt in attempts),
        "authorized_tts_calls": sum(attempt.authorized_tts_calls for attempt in attempts),
        "forbidden_effects": dict(ZERO_FORBIDDEN_EFFECTS),
        "browser_exercised": False,
        "product_wiring_exercised": False,
        "payload_retained": False,
    }


async def collect_attempts(
    facade: object,
    *,
    mode: str,
    tts_factory: Callable[[], object],
    measure: Callable[..., Awaitable[Attempt]] = measure_attempt,
) -> tuple[Attempt, ...]:
    count = 1 if mode == "pilot" else 5
    attempts: list[Attempt] = []
    for arm in ARMS:
        for workload in WORKLOADS:
            for index in range(count):
                try:
                    attempt = await measure(
                        facade,
                        workload,
                        arm,
                        index,
                        tts=tts_factory(),
                    )
                except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
                    raise
                except Exception:
                    attempt = Attempt.failed(
                        arm=arm,
                        workload_id=workload.workload_id,
                        attempt_index=index,
                        reason="ATTEMPT_UNHANDLED_FAILURE",
                    )
                attempts.append(attempt)
    return tuple(attempts)


async def _run(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    output = Path(args.output).resolve()
    prefix_screen.validate_source(
        root, args.git_commit, args.agent_core_commit, output
    )
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        raise ValueError("project directory does not exist")
    create_real_tts_client(dict(os.environ))

    from jiuwenswarm.server.runtime.agent_manager import AgentManager

    manager = AgentManager()
    try:
        facade = await manager.get_agent(
            channel_id="live_voice_pre_final_stable_agent_tts_screen",
            mode="agent",
            project_dir=str(project_dir),
        )
        if facade is None:
            raise RuntimeError("formal Agent facade is unavailable")
        attempts = await collect_attempts(
            facade,
            mode=args.command,
            tts_factory=lambda: create_real_tts_client(dict(os.environ)),
        )
    finally:
        await asyncio.wait_for(manager.cleanup(), timeout=15)
    for attempt in attempts:
        print(
            json.dumps(
                {
                    "arm": attempt.arm,
                    "workload_id": attempt.workload_id,
                    "attempt_index": attempt.attempt_index,
                    "outcome": attempt.outcome,
                    "agent_to_first_pcm_ms": attempt.agent_to_first_pcm_ms,
                }
            ),
            flush=True,
        )
    report = build_report(
        mode=args.command,
        git_commit=args.git_commit,
        agent_core_commit=args.agent_core_commit,
        attempts=attempts,
    )
    prefix_screen.write_report(output, report)
    return 0 if report["status"] == "PASS" else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("pilot", "run"))
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--git-commit", required=True, type=str.lower)
    parser.add_argument("--agent-core-commit", required=True, type=str.lower)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not _COMMIT_RE.fullmatch(args.git_commit) or not _COMMIT_RE.fullmatch(
        args.agent_core_commit
    ):
        raise SystemExit("commit arguments must be full lowercase SHA-1 values")
    try:
        return asyncio.run(_run(args))
    except Exception as error:
        print(f"PRE_FINAL_STABLE_AGENT_TTS_FAILED: {type(error).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
