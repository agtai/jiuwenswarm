# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Compatibility Adapter for an already-committed Harness round handle."""

from __future__ import annotations

from collections.abc import AsyncIterator

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode, EventEnvelope
from jiuwenswarm.server.live_voice.agent_bridge import AgentEvent
from jiuwenswarm.server.live_voice.agent_bridge_runtime import AgentRoundRequest
from jiuwenswarm.server.live_voice.jiuwenswarm_round_harness import (
    HarnessRoundHandle,
    HarnessRoundViolation,
)


def _tool_result_succeeded(payload: dict[str, object]) -> bool | None:
    event_type = payload.get("event_type")
    if event_type != "chat.tool_result":
        return None
    success = payload.get("success")
    is_error = payload.get("is_error")
    status = payload.get("status")
    status_value = status.strip().casefold() if isinstance(status, str) else ""
    succeeded = success is True or is_error is False or status_value in {
        "completed",
        "ok",
        "success",
        "succeeded",
    }
    failed = success is False or is_error is True or status_value in {
        "error",
        "failed",
        "failure",
    }
    return succeeded and not failed


class JiuWenSwarmAgentAdapter:
    """Maps Agent chunks while carrying Harness lifecycle events unchanged."""

    adapter_id = "jiuwenswarm.formal_agent"

    def __init__(self, handle: HarnessRoundHandle) -> None:
        if not isinstance(handle, HarnessRoundHandle):
            raise HarnessRoundViolation(
                "INVALID_ROUND_HANDLE",
                "Agent Adapter requires a trusted Harness round handle",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._handle = handle

    async def stream(
        self, request: AgentRoundRequest
    ) -> AsyncIterator[AgentEvent | EventEnvelope]:
        self._validate_request(request)
        agent_seq = 0
        async for item in self._handle.events():
            if isinstance(item, EventEnvelope):
                yield item
                continue
            assert isinstance(item, AgentResponseChunk)
            payload = item.payload if isinstance(item.payload, dict) else {}
            event_type = payload.get("event_type")
            if not isinstance(event_type, str) or not event_type.strip():
                raise HarnessRoundViolation(
                    "INVALID_FORMAL_AGENT_OUTPUT",
                    "Agent chunks require a typed event_type",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            content = payload.get("content")
            error = payload.get("error")
            yield AgentEvent(
                request_id=request.request_id,
                interaction_id=request.commit.interaction_id,
                turn_id=request.commit.turn_id,
                commit_id=request.commit.commit_id,
                seq=agent_seq,
                event_type=event_type,
                source_provenance=request.source_provenance,
                text=content if isinstance(content, str) else None,
                capability="agent.chat",
                error_reason=error if isinstance(error, str) else None,
                tool_result_succeeded=_tool_result_succeeded(payload),
            )
            agent_seq += 1

    def _validate_request(self, request: AgentRoundRequest) -> None:
        reservation = self._handle.reservation
        binding = reservation.binding
        if (
            not isinstance(request, AgentRoundRequest)
            or request.request_id != binding.request_id
            or request.round_id != reservation.round_id
            or request.response_ref != self._handle.response_ref
            or request.correlation_id != binding.correlation_id
            or request.commit.canonical_bytes() != binding.commit.canonical_bytes()
            or request.adapter_id != self.adapter_id
        ):
            raise HarnessRoundViolation(
                "AGENT_ADAPTER_BINDING_MISMATCH",
                "Bridge request does not match the trusted Harness round binding",
                ErrorCode.PERMISSION_DENIED,
            )
