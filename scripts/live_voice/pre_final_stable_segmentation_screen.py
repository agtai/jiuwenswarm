# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Validation-only pre-final stable-prefix measurement core.

This module never grants speech or PresentationUnit authority. It records a
candidate time, then waits for ``chat.final`` to prove the candidate was an
exact immutable prefix before retaining any attractive latency.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import math
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Iterable

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CommandEnvelope,
    EventEnvelope,
    ResponseRef,
    ScopeRef,
    TurnCommit,
)
from jiuwenswarm.server.live_voice.agent_bridge import AgentEvent
from jiuwenswarm.server.live_voice.agent_latency_probe import (
    AgentForegroundStreamProbeHooks,
)
from jiuwenswarm.server.live_voice.jiuwenswarm_round_harness import (
    HarnessRoundBinding,
    JiuWenSwarmRoundHarness,
)
from jiuwenswarm.server.live_voice.stable_sentence_policy import (
    FinalReconciliationDisposition,
    StableSentenceStreamState,
    commit_candidate,
    observe_agent_event,
    reconcile_final,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextSnapshot,
)


ZERO_FORBIDDEN_EFFECTS = {
    "agent_tool_calls": 0,
    "task_mutations": 0,
    "history_writes": 0,
    "tts_requests": 0,
    "stt_requests": 0,
    "browser_effects": 0,
    "product_downlinks": 0,
    "audio_playouts": 0,
}
REPORT_SCHEMA_VERSION = "live-voice.pre-final-stable-segmentation-screen.v0"
MATERIALITY_THRESHOLD_MS = 500.0
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, slots=True)
class Workload:
    workload_id: str
    prompt: str


WORKLOADS = (
    Workload("medium", "Explain the complete water cycle in nature in 5 points."),
    Workload(
        "long",
        "Please introduce Hangzhou in 8 detailed points, with at least two "
        "sentences for each point, then give a summary.",
    ),
)


@dataclass(frozen=True, slots=True)
class Attempt:
    workload_id: str
    attempt_index: int
    outcome: str
    reason: str
    agent_to_candidate_ms: float | None
    candidate_to_final_ms: float | None
    agent_to_final_ms: float | None
    reconciliation_disposition: str | None
    terminal_outcome: str
    forbidden_effects: dict[str, int]

    @classmethod
    def completed(
        cls,
        workload_id: str,
        attempt_index: int,
        agent_to_candidate_ms: float,
        candidate_to_final_ms: float,
        agent_to_final_ms: float,
    ) -> Attempt:
        return cls(
            workload_id,
            attempt_index,
            "completed",
            "OK",
            agent_to_candidate_ms,
            candidate_to_final_ms,
            agent_to_final_ms,
            FinalReconciliationDisposition.EXACT_PREFIX.value,
            "completed",
            dict(ZERO_FORBIDDEN_EFFECTS),
        )

    @classmethod
    def failed(
        cls,
        workload_id: str,
        attempt_index: int,
        reason: str,
        *,
        disposition: str | None = None,
        terminal_outcome: str = "failed",
    ) -> Attempt:
        return cls(
            workload_id,
            attempt_index,
            "failed",
            reason,
            None,
            None,
            None,
            disposition,
            terminal_outcome,
            dict(ZERO_FORBIDDEN_EFFECTS),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "workload_id": self.workload_id,
            "attempt_index": self.attempt_index,
            "outcome": self.outcome,
            "reason": self.reason,
            "agent_to_candidate_ms": self.agent_to_candidate_ms,
            "candidate_to_final_ms": self.candidate_to_final_ms,
            "agent_to_final_ms": self.agent_to_final_ms,
            "reconciliation_disposition": self.reconciliation_disposition,
            "terminal_outcome": self.terminal_outcome,
            "forbidden_effects": self.forbidden_effects,
        }


def _turn_commit(workload: Workload, attempt_index: int) -> TurnCommit:
    suffix = f"{workload.workload_id}-{attempt_index}-{time.time_ns()}"
    scope = ScopeRef(
        "pre-final-segmentation-subject",
        "pre-final-segmentation-project",
        f"pre-final-segmentation-session-{suffix}",
        Assurance.REQUEST_ASSERTED,
    )
    return TurnCommit.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "commit_id": f"commit-{suffix}",
            "turn_id": f"turn-{suffix}",
            "interaction_id": f"interaction-{suffix}",
            "text": workload.prompt,
            "hypothesis_provenance": {"provider": "controlled-benchmark"},
            "scope": scope.to_dict(),
            "context_refs": [],
            "committed_at": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
        }
    )


def _policy_event(
    *,
    commit: TurnCommit,
    request_id: str,
    seq: int,
    text: str,
) -> AgentEvent:
    return AgentEvent(
        request_id=request_id,
        interaction_id=commit.interaction_id,
        turn_id=commit.turn_id,
        commit_id=commit.commit_id,
        seq=seq,
        event_type="chat.delta",
        source_provenance="formal-agent-stream",
        text=text,
        capability="agent.chat",
    )


def _cancel_command(
    *,
    binding: HarnessRoundBinding,
    round_id: str,
) -> CommandEnvelope:
    return CommandEnvelope.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "request_id": binding.request_id,
            "command_id": f"cancel-{binding.request_id}",
            "command_type": "round.cancel",
            "issued_at": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "scope": binding.commit.scope.to_dict(),
            "correlation_id": binding.correlation_id,
            "causation_id": None,
            "origin": {
                "kind": "committed_turn",
                "turn_id": binding.commit.turn_id,
                "commit_id": binding.commit.commit_id,
            },
            "target_ref": {"kind": "round", "id": round_id},
            "context_refs": [],
            "required_capabilities": ["round.cancel"],
            "payload": {},
            "extensions": {},
        }
    )


async def _cancel_and_wait_terminal(handle: object, binding: HarnessRoundBinding) -> str:
    cancel = getattr(handle, "cancel", None)
    round_id = getattr(handle, "round_id", None)
    if not callable(cancel) or not isinstance(round_id, str):
        raise RuntimeError("round handle cannot be cancelled")
    result = cancel(_cancel_command(binding=binding, round_id=round_id))
    if getattr(result, "accepted", False) is not True:
        raise RuntimeError("round cancellation was not accepted")

    async def wait_terminal() -> object:
        while getattr(handle, "terminal_event", None) is None:
            await asyncio.sleep(0)
        return handle.terminal_event

    terminal = await asyncio.wait_for(wait_terminal(), timeout=10)
    payload = terminal.payload
    return str(payload.get("outcome", "unknown"))


async def measure_attempt(
    facade: object,
    workload: Workload,
    attempt_index: int,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    timeout_seconds: float = 180.0,
) -> Attempt:
    """Measure one formal Agent round and retain timings only after reconciliation."""

    commit = _turn_commit(workload, attempt_index)
    suffix = commit.turn_id.removeprefix("turn-")
    binding = HarnessRoundBinding(
        request_id=f"request-{suffix}",
        response_id=f"response-{suffix}",
        correlation_id=f"correlation-{suffix}",
        commit=commit,
    )
    response_ref = ResponseRef(commit.interaction_id, binding.response_id, 0)
    harness = JiuWenSwarmRoundHarness(
        instance_id=f"pre-final-segmentation-{suffix}",
        max_active_rounds=1,
        output_capacity=64,
    )
    state = StableSentenceStreamState.create(response_ref)
    started_at: float | None = None
    candidate_at: float | None = None
    final_at: float | None = None
    disposition: str | None = None
    terminal_outcome = "unknown"
    failure_reason: str | None = None
    final_seen = False
    policy_seq = 0
    cleanup_failed = False
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
            channel_id="live_voice_pre_final_segmentation_screen",
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
                    elif (
                        event_type == "chat.delta"
                        and isinstance(content, str)
                        and content
                    ):
                        observation = observe_agent_event(
                            state,
                            _policy_event(
                                commit=commit,
                                request_id=binding.request_id,
                                seq=policy_seq,
                                text=content,
                            ),
                        )
                        policy_seq += 1
                        state = observation.state
                        if candidate_at is None and observation.candidate is not None:
                            candidate_at = monotonic()
                            state = commit_candidate(
                                state, observation.candidate.candidate_id
                            ).state
                    elif event_type == "chat.final":
                        if final_seen or not isinstance(content, str) or not content.strip():
                            failure_reason = "INVALID_OR_DUPLICATE_FINAL"
                        else:
                            final_seen = True
                            final_at = monotonic()
                            reconciliation = reconcile_final(state, content)
                            disposition = reconciliation.disposition.value
                            if (
                                reconciliation.disposition
                                is not FinalReconciliationDisposition.EXACT_PREFIX
                                or reconciliation.correction_required
                            ):
                                failure_reason = "PREFIX_RECONCILIATION_FAILED"
                elif isinstance(item, EventEnvelope):
                    payload = item.payload
                    if payload.get("state") == "terminal":
                        terminal_outcome = str(payload.get("outcome", "unknown"))
    except TimeoutError:
        failure_reason = failure_reason or "AGENT_STREAM_TIMED_OUT"
        if handle is not None and handle.terminal_event is None:
            try:
                terminal_outcome = await _cancel_and_wait_terminal(handle, binding)
            except Exception:
                failure_reason = "ROUND_CANCEL_FAILED"
    except asyncio.CancelledError:
        if handle is not None and handle.terminal_event is None:
            try:
                await _cancel_and_wait_terminal(handle, binding)
            except Exception:
                pass
        raise
    except (KeyboardInterrupt, SystemExit):
        if handle is not None and handle.terminal_event is None:
            try:
                await _cancel_and_wait_terminal(handle, binding)
            except Exception:
                pass
        raise
    except Exception:
        failure_reason = failure_reason or "AGENT_STREAM_FAILED"
        if handle is not None and handle.terminal_event is None:
            try:
                terminal_outcome = await _cancel_and_wait_terminal(handle, binding)
            except Exception:
                failure_reason = "ROUND_CANCEL_FAILED"
    finally:
        try:
            await asyncio.wait_for(harness.close(), timeout=10)
        except BaseException:
            cleanup_failed = True

    if cleanup_failed:
        failure_reason = "HARNESS_CLEANUP_FAILED"
    if terminal_outcome != "completed":
        failure_reason = failure_reason or "TERMINAL_NOT_COMPLETED"
    if candidate_at is None:
        failure_reason = failure_reason or "NO_STABLE_CANDIDATE"
    if not final_seen or final_at is None:
        failure_reason = failure_reason or "FINAL_MISSING"
    if started_at is None:
        failure_reason = failure_reason or "AGENT_START_MISSING"
    if (
        failure_reason is None
        and started_at is not None
        and candidate_at is not None
        and final_at is not None
        and not started_at <= candidate_at <= final_at
    ):
        failure_reason = "INVALID_TIMING_ORDER"

    if failure_reason is not None:
        return Attempt.failed(
            workload.workload_id,
            attempt_index,
            failure_reason,
            disposition=disposition,
            terminal_outcome=terminal_outcome,
        )
    assert started_at is not None and candidate_at is not None and final_at is not None
    return Attempt.completed(
        workload.workload_id,
        attempt_index,
        (candidate_at - started_at) * 1000.0,
        (final_at - candidate_at) * 1000.0,
        (final_at - started_at) * 1000.0,
    )


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[rank], 3)


def build_report(
    *,
    mode: str,
    git_commit: str,
    agent_core_commit: str,
    attempts: tuple[Attempt, ...],
) -> dict[str, object]:
    workloads = WORKLOADS[:1] if mode == "smoke" else WORKLOADS
    attempts_per_workload = 1 if mode == "smoke" else 5
    expected_count = len(workloads) * attempts_per_workload
    summaries: dict[str, object] = {}
    for workload in workloads:
        selected = [attempt for attempt in attempts if attempt.workload_id == workload.workload_id]
        completed = [attempt for attempt in selected if attempt.outcome == "completed"]
        candidate_to_final = [
            attempt.candidate_to_final_ms
            for attempt in completed
            if attempt.candidate_to_final_ms is not None
        ]
        candidate_p50 = _percentile(candidate_to_final, 0.50)
        summaries[workload.workload_id] = {
            "attempted": len(selected),
            "completed": len(completed),
            "agent_to_candidate_ms": {
                "p50": _percentile(
                    (
                        attempt.agent_to_candidate_ms
                        for attempt in completed
                        if attempt.agent_to_candidate_ms is not None
                    ),
                    0.50,
                ),
                "p95_nearest_rank": _percentile(
                    (
                        attempt.agent_to_candidate_ms
                        for attempt in completed
                        if attempt.agent_to_candidate_ms is not None
                    ),
                    0.95,
                ),
            },
            "candidate_to_final_ms": {
                "p50": candidate_p50,
                "p95_nearest_rank": _percentile(candidate_to_final, 0.95),
            },
            "agent_to_final_ms": {
                "p50": _percentile(
                    (
                        attempt.agent_to_final_ms
                        for attempt in completed
                        if attempt.agent_to_final_ms is not None
                    ),
                    0.50,
                ),
                "p95_nearest_rank": _percentile(
                    (
                        attempt.agent_to_final_ms
                        for attempt in completed
                        if attempt.agent_to_final_ms is not None
                    ),
                    0.95,
                ),
            },
            "materiality_threshold_ms": MATERIALITY_THRESHOLD_MS,
            "materiality_pass": (
                len(completed) == attempts_per_workload
                and candidate_p50 is not None
                and candidate_p50 >= MATERIALITY_THRESHOLD_MS
            ),
        }
    expected_slots = tuple(
        (workload.workload_id, attempt_index)
        for workload in workloads
        for attempt_index in range(attempts_per_workload)
    )
    actual_slots = tuple(
        (attempt.workload_id, attempt.attempt_index) for attempt in attempts
    )
    integrity_pass = (
        actual_slots == expected_slots
        and len(attempts) == expected_count
        and all(attempt.outcome == "completed" for attempt in attempts)
        and all(
            attempt.reconciliation_disposition
            == FinalReconciliationDisposition.EXACT_PREFIX.value
            for attempt in attempts
        )
    )
    materiality_pass = integrity_pass and all(
        bool(summary["materiality_pass"]) for summary in summaries.values()
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "agent_core_commit": agent_core_commit,
        "measurement_boundary": "agent_started_to_exact_prefix_candidate_to_chat_final",
        "candidate_authority": "retrospective_validation_only",
        "tools_allowed": False,
        "agent_payload_retained": False,
        "p95_method": "nearest_rank_small_population",
        "intended_attempts": expected_count,
        "status": "PASS" if integrity_pass else "FAIL",
        "decision": (
            "READY_FOR_TTS_SCREEN"
            if materiality_pass
            else "MATERIALITY_STOP"
            if integrity_pass
            else "INTEGRITY_FAILED"
        ),
        "attempts": [attempt.to_dict() for attempt in attempts],
        "summaries": summaries,
        "forbidden_effects": dict(ZERO_FORBIDDEN_EFFECTS),
    }


def write_report(output: Path, report: dict[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _installed_agent_core_commit() -> str:
    try:
        distribution = importlib.metadata.distribution("openjiuwen")
        direct_url_text = distribution.read_text("direct_url.json")
        direct_url = json.loads(direct_url_text or "{}")
        commit_id = direct_url.get("vcs_info", {}).get("commit_id")
    except (importlib.metadata.PackageNotFoundError, json.JSONDecodeError):
        commit_id = None
    if not isinstance(commit_id, str) or not _COMMIT_RE.fullmatch(commit_id):
        raise ValueError("installed Agent-Core commit provenance is unavailable")
    return commit_id


def validate_source(
    root: Path,
    git_commit: str,
    agent_core_commit: str,
    output: Path,
) -> None:
    if output.exists():
        raise FileExistsError("benchmark output already exists")
    if _git(root, "rev-parse", "HEAD") != git_commit:
        raise ValueError("git commit does not match the checked-out source")
    if _git(root, "status", "--porcelain"):
        raise ValueError("benchmark requires a clean source tree")
    if _installed_agent_core_commit() != agent_core_commit:
        raise ValueError("Agent-Core commit does not match the installed dependency")


async def collect_attempts(
    facade: object,
    workloads: tuple[Workload, ...],
    attempts_per_workload: int,
    *,
    measure: Callable[[object, Workload, int], Awaitable[Attempt]] = measure_attempt,
) -> tuple[Attempt, ...]:
    attempts: list[Attempt] = []
    for workload in workloads:
        for attempt_index in range(attempts_per_workload):
            attempts.append(await measure(facade, workload, attempt_index))
    return tuple(attempts)


async def _run(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    output = Path(args.output).resolve()
    validate_source(root, args.git_commit, args.agent_core_commit, output)
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        raise ValueError("project directory does not exist")

    from jiuwenswarm.server.runtime.agent_manager import AgentManager

    manager = AgentManager()
    attempts: tuple[Attempt, ...] = ()
    try:
        facade = await manager.get_agent(
            channel_id="live_voice_pre_final_segmentation_screen",
            mode="agent",
            project_dir=str(project_dir),
        )
        if facade is None:
            raise RuntimeError("formal Agent facade is unavailable")
        workloads = WORKLOADS[:1] if args.command == "smoke" else WORKLOADS
        count = 1 if args.command == "smoke" else 5
        attempts = await collect_attempts(facade, workloads, count)
        for attempt in attempts:
            print(
                json.dumps(
                    {
                        "workload_id": attempt.workload_id,
                        "attempt_index": attempt.attempt_index,
                        "outcome": attempt.outcome,
                        "agent_to_candidate_ms": attempt.agent_to_candidate_ms,
                        "candidate_to_final_ms": attempt.candidate_to_final_ms,
                        "agent_to_final_ms": attempt.agent_to_final_ms,
                    }
                ),
                flush=True,
            )
    finally:
        await asyncio.wait_for(manager.cleanup(), timeout=15)

    report = build_report(
        mode=args.command,
        git_commit=args.git_commit,
        agent_core_commit=args.agent_core_commit,
        attempts=attempts,
    )
    write_report(output, report)
    return 0 if report["status"] == "PASS" else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("smoke", "run"))
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
        print(f"PRE_FINAL_STABLE_SEGMENTATION_FAILED: {type(error).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
