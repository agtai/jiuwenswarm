# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""Bounded WebSocket wire sending for AgentServer responses."""

from __future__ import annotations

import json
import logging
from typing import Any

from jiuwenswarm.common.e2a.constants import E2A_WIRE_SERVER_PUSH_KEY
from jiuwenswarm.common.e2a.wire_codec import (
    encode_agent_chunk_for_wire,
    encode_agent_response_for_wire,
)
from jiuwenswarm.common.schema.agent import AgentResponse, AgentResponseChunk
from jiuwenswarm.common.ws_limits import AGENT_WS_SEND_BUDGET_BYTES

logger = logging.getLogger(__name__)

_ROUTING_KEYS = (
    "session_id",
    "task_id",
    "context_id",
    "correlation_id",
)
_MAX_ROUTING_INTEGER_BITS = 4_096


def _safe_routing_text(value: Any) -> str:
    """Project a routing scalar without invoking subclass hooks."""
    value_type = type(value)
    if value_type is str:
        return value
    if value is None:
        return ""
    if value_type is bool:
        return "True" if value else ""
    if value_type is int:
        if int.bit_length(value) > _MAX_ROUTING_INTEGER_BITS:
            return ""
        return str(value) if value else ""
    if value_type is float:
        return str(value) if value else ""
    return ""


def _safe_routing_scalar(value: Any) -> Any:
    value_type = type(value)
    if value is None or value_type is str or value_type is bool or value_type is float:
        return value
    if value_type is int and int.bit_length(value) <= _MAX_ROUTING_INTEGER_BITS:
        return value
    return None


def _oversized_payload(actual_bytes: int) -> dict[str, Any]:
    return {
        "error": "AgentServer response exceeds WebSocket send budget",
        "code": "response_too_large",
        "actual_bytes": actual_bytes,
        "max_bytes": AGENT_WS_SEND_BUDGET_BYTES,
    }


def _build_oversized_fallback(
    wire: dict[str, Any], actual_bytes: int
) -> dict[str, Any]:
    request_id = _safe_routing_text(wire.get("request_id"))
    response_id = _safe_routing_text(wire.get("response_id"))
    if not response_id:
        response_id = request_id
    channel_id = _safe_routing_text(wire.get("channel"))
    raw_sequence = wire.get("sequence")
    sequence = (
        raw_sequence
        if type(raw_sequence) is int
        and int.bit_length(raw_sequence) <= _MAX_ROUTING_INTEGER_BITS
        else 0
    )
    raw_agent_ref = wire.get("agent_ref")
    agent_ref = raw_agent_ref if type(raw_agent_ref) is dict else None
    payload = _oversized_payload(actual_bytes)

    if wire.get("is_stream") is True:
        payload["event_type"] = "chat.error"
        fallback = encode_agent_chunk_for_wire(
            AgentResponseChunk(
                request_id=request_id,
                channel_id=channel_id,
                payload=payload,
                is_complete=True,
                agent_ref=agent_ref,
            ),
            response_id=response_id,
            sequence=sequence,
        )
    elif type(wire.get("type")) is str and wire.get("type") == "event":
        fallback = {
            "type": "event",
            "event": "response.error",
            "payload": payload,
        }
    else:
        fallback = encode_agent_response_for_wire(
            AgentResponse(
                request_id=request_id,
                channel_id=channel_id,
                ok=False,
                payload=payload,
                agent_ref=agent_ref,
            ),
            response_id=response_id,
            sequence=sequence,
        )

    for key in _ROUTING_KEYS:
        if wire.get(key) is not None:
            fallback[key] = _safe_routing_scalar(wire[key])

    source_metadata = wire.get("metadata")
    if (
        type(source_metadata) is dict
        and source_metadata.get(E2A_WIRE_SERVER_PUSH_KEY) is True
    ):
        metadata = dict(fallback.get("metadata") or {})
        metadata[E2A_WIRE_SERVER_PUSH_KEY] = True
        fallback["metadata"] = metadata

    return fallback


async def send_wire_payload(ws: Any, wire: dict[str, Any]) -> bool:
    """Send one bounded wire payload, replacing oversized data with an error."""
    serialized = json.dumps(wire, ensure_ascii=False)
    actual_bytes = len(serialized.encode("utf-8"))
    if actual_bytes <= AGENT_WS_SEND_BUDGET_BYTES:
        await ws.send(serialized)
        return True

    field_count = dict.__len__(wire) if type(wire) is dict else 0
    logger.error(
        "AgentServer WebSocket send failed: stage=oversized "
        "category=wire_budget fallback=true actual_bytes=%d max_bytes=%d "
        "field_count=%d",
        actual_bytes,
        AGENT_WS_SEND_BUDGET_BYTES,
        field_count,
    )
    fallback = _build_oversized_fallback(wire, actual_bytes)
    fallback_json = json.dumps(fallback, ensure_ascii=False)
    fallback_bytes = len(fallback_json.encode("utf-8"))
    if fallback_bytes > AGENT_WS_SEND_BUDGET_BYTES:
        raise RuntimeError(
            "oversized fallback exceeds WebSocket send budget: "
            f"actual_bytes={fallback_bytes} "
            f"max_bytes={AGENT_WS_SEND_BUDGET_BYTES}"
        )
    await ws.send(fallback_json)
    return False
