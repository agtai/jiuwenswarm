# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Project explicit SDK envelope labels; never interpret them as authority."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any


SOURCE_FIELDS = frozenset({
    "source_binding_id", "source_origin_request_id", "source_session_id",
    "source_request_id", "source_task_id", "source_run_kind",
    "source_goal_id", "source_goal_revision",
})


def normalize_sdk_stream_envelope(chunk: Any) -> Any:
    """Give serialized type/payload envelopes the same parser path as objects."""
    if isinstance(chunk, dict) and isinstance(chunk.get("type"), str) and "payload" in chunk:
        return SimpleNamespace(type=chunk["type"], payload=chunk["payload"])
    return chunk


def extract_stream_source(chunk: Any) -> dict[str, Any]:
    """Read only the explicit outer payload, or controller payload.metadata."""
    chunk = normalize_sdk_stream_envelope(chunk)
    if not isinstance(getattr(chunk, "type", None), str) or not hasattr(chunk, "payload"):
        return {}
    payload = chunk.payload
    if chunk.type == "controller_output":
        payload = payload.get("metadata") if isinstance(payload, dict) else getattr(payload, "metadata", None)
    if not isinstance(payload, dict):
        return {}
    source = {}
    for key in SOURCE_FIELDS:
        if key not in payload:
            continue
        value = payload[key]
        if value is None:
            valid = True
        elif key == "source_goal_revision":
            valid = type(value) is int and value > 0
        else:
            valid = type(value) is str
        if valid:
            source[key] = value
    return source


def agent_interaction_payload(chunk: Any) -> Any:
    """Unwrap only the SDK Session source view's one interaction wrapper."""
    chunk = normalize_sdk_stream_envelope(chunk)
    if getattr(chunk, "type", None) != "__interaction__":
        return None
    payload = getattr(chunk, "payload", None)
    if isinstance(payload, dict) and "id" not in payload and any(key in payload for key in SOURCE_FIELDS):
        # Session._tag_stream_payload wraps a typed InteractionOutput as value;
        # dict InteractionOutput is tagged directly. Serialization keeps both.
        wrapped = payload.get("value")
        if ((isinstance(wrapped, dict) and "id" in wrapped and "value" in wrapped)
                or (hasattr(wrapped, "id") and hasattr(wrapped, "value"))):
            return wrapped
    return payload


def extract_agent_interrupt(chunk: Any) -> dict[str, str] | None:
    """Read the exact SDK interaction carrier, never nested tool/model output."""
    payload = agent_interaction_payload(chunk)
    input_id = payload.get("id") if isinstance(payload, dict) else getattr(payload, "id", None)
    value = payload.get("value") if isinstance(payload, dict) else getattr(payload, "value", None)
    token = value.get("pending_token") if isinstance(value, dict) else getattr(value, "pending_token", None)
    if any(type(item) is not str or not item or item.strip() != item or "\x00" in item
           or len(item) > 1024 for item in (input_id, token)):
        return None
    return {"input_id": input_id, "pending_token": token}


def agent_interrupt_display_id(source, token, input_id):
    """Fence old UI callbacks even when providers reuse their tool-call IDs."""
    fields = [source["source_binding_id"], source["source_task_id"], token, input_id]
    encoded = json.dumps(fields, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return "agent-input." + hashlib.sha256(encoded).hexdigest()


def project_stream_source(chunk: Any, parsed: dict[str, Any] | None) -> dict[str, Any] | None:
    """Replace parsed top-level source labels using only the original envelope.

    In particular, expanding a nested tool update cannot promote its self-reported
    labels. Missing labels stay missing, and null is retained without inference.
    Binding lookup and authorization remain the execution service's responsibility.
    """
    if parsed is None:
        return None
    clean = {key: value for key, value in parsed.items()
             if key != "pending_token" and not (isinstance(key, str) and key.startswith("source_"))}
    source = extract_stream_source(chunk)
    interrupt = extract_agent_interrupt(chunk)
    if (interrupt is not None and clean.get("event_type") == "chat.ask_user_question"
            and clean.get("request_id") == interrupt["input_id"]):
        clean["pending_token"] = interrupt["pending_token"]
        if all(isinstance(source.get(key), str) and source[key]
               for key in ("source_binding_id", "source_task_id")):
            clean["input_id"] = interrupt["input_id"]
            clean["request_id"] = agent_interrupt_display_id(source, interrupt["pending_token"], interrupt["input_id"])
    return {**clean, **source}
