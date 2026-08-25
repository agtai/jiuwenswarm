# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Run a small real-Agent benchmark for first visible delta latency.

The report is deliberately content-free: prompts and Agent output are used only
in memory and are never serialized.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    EventEnvelope,
    ResponseRef,
    ScopeRef,
    TurnCommit,
)
from jiuwenswarm.server.live_voice.agent_latency_probe import (
    AgentForegroundStreamProbeHooks,
)
from jiuwenswarm.server.live_voice.jiuwenswarm_round_harness import (
    HarnessRoundBinding,
    JiuWenSwarmRoundHarness,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextSnapshot,
)


REPORT_SCHEMA_VERSION = "live-voice.agent-first-delta-benchmark.v0"
ZERO_FORBIDDEN_EFFECTS = {
    "agent_tool_calls": 0,
    "task_mutations": 0,
    "history_writes": 0,
    "tts_requests": 0,
    "stt_requests": 0,
    "browser_effects": 0,
}
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, slots=True)
class Workload:
    workload_id: str
    prompt: str


WORKLOADS = (
    Workload("short", "What is the capital of France? Answer with the city name only."),
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
    agent_to_first_delta_ms: float | None
    first_delta_to_final_ms: float | None
    agent_to_final_ms: float | None
    delta_count: int
    terminal_outcome: str
    forbidden_effects: dict[str, int]

    @classmethod
    def completed(
        cls,
        workload_id: str,
        attempt_index: int,
        agent_to_first_delta_ms: float,
        first_delta_to_final_ms: float,
        agent_to_final_ms: float,
        delta_count: int,
    ) -> Attempt:
        return cls(
            workload_id,
            attempt_index,
            "completed",
            "OK",
            agent_to_first_delta_ms,
            first_delta_to_final_ms,
            agent_to_final_ms,
            delta_count,
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
        delta_count: int = 0,
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
            delta_count,
            terminal_outcome,
            dict(ZERO_FORBIDDEN_EFFECTS),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "workload_id": self.workload_id,
            "attempt_index": self.attempt_index,
            "outcome": self.outcome,
            "reason": self.reason,
            "agent_to_first_delta_ms": self.agent_to_first_delta_ms,
            "first_delta_to_final_ms": self.first_delta_to_final_ms,
            "agent_to_final_ms": self.agent_to_final_ms,
            "delta_count": self.delta_count,
            "terminal_outcome": self.terminal_outcome,
            "forbidden_effects": self.forbidden_effects,
        }


def _turn_commit(workload: Workload, attempt_index: int) -> TurnCommit:
    suffix = f"{workload.workload_id}-{attempt_index}-{time.time_ns()}"
    scope = ScopeRef(
        "agent-first-delta-subject",
        "agent-first-delta-project",
        f"agent-first-delta-session-{suffix}",
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


async def measure_attempt(
    facade: object,
    workload: Workload,
    attempt_index: int,
    *,
    monotonic: Callable[[], float] = time.monotonic,
) -> Attempt:
    """Measure one formal no-tools Agent round and retain no content."""

    commit = _turn_commit(workload, attempt_index)
    suffix = commit.turn_id.removeprefix("turn-")
    binding = HarnessRoundBinding(
        request_id=f"request-{suffix}",
        response_id=f"response-{suffix}",
        correlation_id=f"correlation-{suffix}",
        commit=commit,
    )
    harness = JiuWenSwarmRoundHarness(
        instance_id=f"agent-first-delta-{suffix}",
        max_active_rounds=1,
        output_capacity=64,
    )
    started_at: float | None = None
    first_delta_at: float | None = None
    final_at: float | None = None
    delta_count = 0
    terminal_outcome = "unknown"
    stream_failed = False

    def mark_started() -> None:
        nonlocal started_at
        if started_at is None:
            started_at = monotonic()

    def mark_first_visible_delta() -> None:
        nonlocal first_delta_at
        if first_delta_at is None:
            first_delta_at = monotonic()

    try:
        reservation = harness.reserve_round(binding, facade=facade)
        harness.begin_round_commit(reservation)
        handle = harness.commit_round(
            reservation,
            response_ref=ResponseRef(commit.interaction_id, binding.response_id, 0),
            context=FormalContextSnapshot(commit.scope),
            facade=facade,
            channel_id="live_voice_agent_first_delta_benchmark",
            allow_tools=False,
            latency_probe_hooks=AgentForegroundStreamProbeHooks(
                mark_started=mark_started,
                mark_first_visible_delta=mark_first_visible_delta,
            ),
        )
        async with asyncio.timeout(180):
            async for item in handle.events():
                if isinstance(item, AgentResponseChunk):
                    payload = item.payload if isinstance(item.payload, dict) else {}
                    event_type = payload.get("event_type")
                    content = payload.get("content")
                    if event_type == "chat.delta" and isinstance(content, str) and content.strip():
                        delta_count += 1
                    elif event_type == "chat.final" and isinstance(content, str) and content.strip():
                        if final_at is None:
                            final_at = monotonic()
                    elif event_type in {"chat.error", "chat.tool_call", "chat.tool_result"}:
                        stream_failed = True
                elif isinstance(item, EventEnvelope):
                    payload = item.payload
                    if payload.get("state") == "terminal":
                        terminal_outcome = str(payload.get("outcome", "unknown"))
    except BaseException:  # The private exception text must not enter evidence.
        return Attempt.failed(workload.workload_id, attempt_index, "AGENT_STREAM_FAILED")
    finally:
        try:
            await asyncio.wait_for(harness.close(), timeout=10)
        except BaseException:
            pass

    if stream_failed or terminal_outcome != "completed":
        return Attempt.failed(
            workload.workload_id,
            attempt_index,
            "TERMINAL_NOT_COMPLETED",
            delta_count=delta_count,
            terminal_outcome=terminal_outcome,
        )
    if started_at is None or first_delta_at is None:
        return Attempt.failed(
            workload.workload_id,
            attempt_index,
            "NO_VISIBLE_DELTA",
            delta_count=delta_count,
            terminal_outcome=terminal_outcome,
        )
    if final_at is None or not started_at <= first_delta_at <= final_at:
        return Attempt.failed(
            workload.workload_id,
            attempt_index,
            "FINAL_MISSING_OR_INVALID_ORDER",
            delta_count=delta_count,
            terminal_outcome=terminal_outcome,
        )
    return Attempt.completed(
        workload.workload_id,
        attempt_index,
        (first_delta_at - started_at) * 1000.0,
        (final_at - first_delta_at) * 1000.0,
        (final_at - started_at) * 1000.0,
        delta_count,
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
    summaries: dict[str, object] = {}
    for workload_id in sorted({attempt.workload_id for attempt in attempts}):
        completed = [
            attempt
            for attempt in attempts
            if attempt.workload_id == workload_id and attempt.outcome == "completed"
        ]
        summaries[workload_id] = {
            "attempted": sum(a.workload_id == workload_id for a in attempts),
            "completed": len(completed),
            "agent_to_first_delta_ms": {
                "p50": _percentile(
                    (a.agent_to_first_delta_ms for a in completed if a.agent_to_first_delta_ms is not None),
                    0.50,
                ),
                "p95": _percentile(
                    (a.agent_to_first_delta_ms for a in completed if a.agent_to_first_delta_ms is not None),
                    0.95,
                ),
            },
            "first_delta_to_final_ms": {
                "p50": _percentile(
                    (a.first_delta_to_final_ms for a in completed if a.first_delta_to_final_ms is not None),
                    0.50,
                ),
                "p95": _percentile(
                    (a.first_delta_to_final_ms for a in completed if a.first_delta_to_final_ms is not None),
                    0.95,
                ),
            },
            "agent_to_final_ms": {
                "p50": _percentile(
                    (a.agent_to_final_ms for a in completed if a.agent_to_final_ms is not None),
                    0.50,
                ),
                "p95": _percentile(
                    (a.agent_to_final_ms for a in completed if a.agent_to_final_ms is not None),
                    0.95,
                ),
            },
        }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "agent_core_commit": agent_core_commit,
        "measurement_boundary": "agent_started_to_first_visible_chat_delta_to_chat_final",
        "tools_allowed": False,
        "agent_payload_retained": False,
        "status": "PASS" if attempts and all(a.outcome == "completed" for a in attempts) else "FAIL",
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


async def _run(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    if _git(root, "rev-parse", "HEAD") != args.git_commit:
        raise ValueError("git commit does not match the checked-out source")
    if _git(root, "status", "--porcelain"):
        raise ValueError("benchmark requires a clean source tree")
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        raise ValueError("project directory does not exist")

    from jiuwenswarm.server.runtime.agent_manager import AgentManager

    manager = AgentManager()
    attempts: list[Attempt] = []
    try:
        facade = await manager.get_agent(
            channel_id="live_voice_agent_first_delta_benchmark",
            mode="agent",
            project_dir=str(project_dir),
        )
        if facade is None:
            raise RuntimeError("formal Agent facade is unavailable")
        workloads = WORKLOADS[:1] if args.command == "smoke" else WORKLOADS
        count = 1 if args.command == "smoke" else args.attempts
        for workload in workloads:
            for attempt_index in range(count):
                attempt = await measure_attempt(facade, workload, attempt_index)
                attempts.append(attempt)
                print(
                    json.dumps(
                        {
                            "workload_id": workload.workload_id,
                            "attempt_index": attempt_index,
                            "outcome": attempt.outcome,
                            "agent_to_first_delta_ms": attempt.agent_to_first_delta_ms,
                            "agent_to_final_ms": attempt.agent_to_final_ms,
                        }
                    ),
                    flush=True,
                )
                if attempt.outcome != "completed":
                    break
            if attempts[-1].outcome != "completed":
                break
    finally:
        await asyncio.wait_for(manager.cleanup(), timeout=15)

    report = build_report(
        mode=args.command,
        git_commit=args.git_commit,
        agent_core_commit=args.agent_core_commit,
        attempts=tuple(attempts),
    )
    write_report(Path(args.output).resolve(), report)
    return 0 if report["status"] == "PASS" else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("smoke", "run"))
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--git-commit", required=True, type=str.lower)
    parser.add_argument("--agent-core-commit", required=True, type=str.lower)
    parser.add_argument("--attempts", type=int, default=5)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not _COMMIT_RE.fullmatch(args.git_commit) or not _COMMIT_RE.fullmatch(
        args.agent_core_commit
    ):
        raise SystemExit("commit arguments must be full lowercase SHA-1 values")
    if not 1 <= args.attempts <= 20:
        raise SystemExit("--attempts must be between 1 and 20")
    try:
        return asyncio.run(_run(args))
    except BaseException as error:
        print(f"AGENT_FIRST_DELTA_BENCHMARK_FAILED: {type(error).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
