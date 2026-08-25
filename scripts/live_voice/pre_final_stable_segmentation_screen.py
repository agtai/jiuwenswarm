# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Validation-only pre-final stable-prefix measurement core.

This module never grants speech or PresentationUnit authority. It records a
candidate time, then waits for ``chat.final`` to prove the candidate was an
exact immutable prefix before retaining any attractive latency.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

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


@dataclass(frozen=True, slots=True)
class Workload:
    workload_id: str
    prompt: str


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
    except BaseException:
        failure_reason = failure_reason or "AGENT_STREAM_FAILED_OR_TIMED_OUT"
        if handle is not None and handle.terminal_event is None:
            try:
                handle.cancel(
                    _cancel_command(binding=binding, round_id=handle.round_id)
                )
            except BaseException:
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
