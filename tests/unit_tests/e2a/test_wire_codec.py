# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""E2A WebSocket 线编码 / 解码与 round-trip。"""

from __future__ import annotations

import json
import logging
import traceback
from dataclasses import asdict

import pytest
from openjiuwen.core.session.stream import OutputSchema

from jiuwenswarm.common.e2a.constants import (
    E2A_WIRE_LEGACY_AGENT_CHUNK_KEY,
    E2A_WIRE_LEGACY_AGENT_RESPONSE_KEY,
)
from jiuwenswarm.common.e2a.gateway_normalize import (
    e2a_response_from_agent_chunk,
    e2a_response_from_agent_response,
)
from jiuwenswarm.common.e2a.wire_codec import (
    encode_agent_chunk_for_wire,
    encode_agent_response_for_wire,
    parse_agent_server_wire_chunk,
    parse_agent_server_wire_unary,
)
from jiuwenswarm.common.e2a import wire_codec
from jiuwenswarm.common.schema.agent import AgentResponse, AgentResponseChunk


def test_roundtrip_unary_ok() -> None:
    orig = AgentResponse(
        request_id="r1",
        channel_id="c1",
        ok=True,
        payload={"a": 1},
        metadata={"m": 2},
    )
    wire = encode_agent_response_for_wire(orig, response_id="r1")
    back = parse_agent_server_wire_unary(wire)
    assert back.request_id == orig.request_id
    assert back.channel_id == orig.channel_id
    assert back.ok is True
    assert back.payload == orig.payload
    assert back.metadata == orig.metadata


def test_roundtrip_unary_error() -> None:
    orig = AgentResponse(
        request_id="r2",
        channel_id="c2",
        ok=False,
        payload={"error": "x", "code": 9},
    )
    wire = encode_agent_response_for_wire(orig, response_id="r2")
    back = parse_agent_server_wire_unary(wire)
    assert back.ok is False
    assert back.payload == orig.payload


def test_encode_unary_with_nested_output_schema_is_json_serializable() -> None:
    orig = AgentResponse(
        request_id="approval-answer",
        channel_id="web",
        ok=True,
        payload={
            "result": OutputSchema(
                type="answer",
                index=0,
                payload={"output": "approval accepted", "result_type": "answer"},
            )
        },
    )

    wire = encode_agent_response_for_wire(orig, response_id="approval-answer")

    json.dumps(wire, ensure_ascii=False)
    back = parse_agent_server_wire_unary(wire)
    assert back.payload == {
        "result": {
            "type": "answer",
            "index": 0,
            "payload": {"output": "approval accepted", "result_type": "answer"},
        }
    }


def test_roundtrip_chunk_sentinel_complete() -> None:
    orig = AgentResponseChunk(
        request_id="s1",
        channel_id="c",
        payload={"is_complete": True},
        is_complete=True,
    )
    wire = encode_agent_chunk_for_wire(orig, response_id="s1", sequence=0)
    back = parse_agent_server_wire_chunk(wire)
    assert back.is_complete is True
    assert back.payload == {"is_complete": True}


def test_roundtrip_chunk_chat_delta() -> None:
    orig = AgentResponseChunk(
        request_id="s2",
        channel_id="c",
        payload={
            "event_type": "chat.delta",
            "content": "hi",
            "source_chunk_type": "llm_reasoning",
        },
        is_complete=False,
    )
    wire = encode_agent_chunk_for_wire(orig, response_id="s2", sequence=1)
    back = parse_agent_server_wire_chunk(wire)
    assert back.is_complete is False
    assert back.payload.get("event_type") == "chat.delta"
    assert back.payload.get("content") == "hi"
    assert back.payload.get("source_chunk_type") == "llm_reasoning"


def test_roundtrip_chunk_custom_event() -> None:
    orig = AgentResponseChunk(
        request_id="s3",
        channel_id="c",
        payload={"event_type": "history.message", "message": {"id": 1}},
        is_complete=False,
    )
    wire = encode_agent_chunk_for_wire(orig, response_id="s3", sequence=0)
    back = parse_agent_server_wire_chunk(wire)
    assert back.payload.get("event_type") == "history.message"
    assert back.payload.get("message") == {"id": 1}


def test_roundtrip_chunk_chat_error() -> None:
    orig = AgentResponseChunk(
        request_id="s4",
        channel_id="c",
        payload={"event_type": "chat.error", "error": "boom"},
        is_complete=True,
    )
    wire = encode_agent_chunk_for_wire(orig, response_id="s4", sequence=2)
    back = parse_agent_server_wire_chunk(wire)
    assert back.is_complete is True
    assert back.payload.get("event_type") == "chat.error"
    assert back.payload.get("error") == "boom"


def test_deprecated_legacy_unary_dict() -> None:
    d = {
        "request_id": "old",
        "channel_id": "ch",
        "ok": True,
        "payload": {"x": 1},
    }
    back = parse_agent_server_wire_unary(d)
    assert back.request_id == "old"
    assert back.payload == {"x": 1}


def test_deprecated_legacy_chunk_dict() -> None:
    d = {
        "request_id": "oldc",
        "channel_id": "ch",
        "payload": {"content": "z"},
        "is_complete": False,
    }
    back = parse_agent_server_wire_chunk(d)
    assert back.request_id == "oldc"
    assert back.payload == {"content": "z"}


def test_parse_unary_prefers_metadata_legacy_blob() -> None:
    legacy = asdict(
        AgentResponse(
            request_id="blob",
            channel_id="c",
            ok=True,
            payload={"recovered": True},
        )
    )
    e2a = e2a_response_from_agent_response(
        AgentResponse(
            request_id="blob",
            channel_id="c",
            ok=False,
            payload={"error": "wire"},
        ),
        response_id="blob",
    )
    meta = dict(e2a.metadata or {})
    meta[E2A_WIRE_LEGACY_AGENT_RESPONSE_KEY] = legacy
    e2a.metadata = meta
    wire = e2a.to_dict()
    back = parse_agent_server_wire_unary(wire)
    assert back.ok is True
    assert back.payload == {"recovered": True}


def test_inverse_raises_for_chunk_shape_on_unary_parser() -> None:
    chunk_wire = encode_agent_chunk_for_wire(
        AgentResponseChunk(
            request_id="u",
            channel_id="c",
            payload={"content": "x"},
            is_complete=False,
        ),
        response_id="u",
        sequence=0,
    )
    with pytest.raises(ValueError):
        parse_agent_server_wire_unary(chunk_wire)


def _private_decode_failure_wire(form: str, stage: str) -> dict:
    if stage == "unrecognized":
        return {
            "sentinel-decode-private-key": "sentinel-decode-private-value",
        }

    if form == "unary":
        if stage == "inverse":
            return encode_agent_chunk_for_wire(
                AgentResponseChunk(
                    request_id="sentinel-decode-inverse-unary-request",
                    channel_id="sentinel-decode-inverse-unary-channel",
                    payload={"content": "sentinel-decode-inverse-unary-payload"},
                    is_complete=False,
                ),
                response_id="sentinel-decode-inverse-unary-response",
                sequence=987654321,
            )
        wire = encode_agent_response_for_wire(
            AgentResponse(
                request_id="sentinel-decode-from-dict-unary-request",
                channel_id="sentinel-decode-from-dict-unary-channel",
                ok=True,
                payload={"content": "sentinel-decode-from-dict-unary-payload"},
            ),
            response_id="sentinel-decode-from-dict-unary-response",
        )
    else:
        if stage == "inverse":
            wire = encode_agent_chunk_for_wire(
                AgentResponseChunk(
                    request_id="sentinel-decode-inverse-chunk-request",
                    channel_id="sentinel-decode-inverse-chunk-channel",
                    payload={"content": "sentinel-decode-inverse-chunk-payload"},
                    is_complete=False,
                ),
                response_id="sentinel-decode-inverse-chunk-response",
                sequence=987654321,
            )
            wire["response_kind"] = "sentinel-decode-inverse-chunk-kind"
            wire["status"] = "sentinel-decode-inverse-chunk-status"
            return wire
        wire = encode_agent_chunk_for_wire(
            AgentResponseChunk(
                request_id="sentinel-decode-from-dict-chunk-request",
                channel_id="sentinel-decode-from-dict-chunk-channel",
                payload={"content": "sentinel-decode-from-dict-chunk-payload"},
                is_complete=False,
            ),
            response_id="sentinel-decode-from-dict-chunk-response",
            sequence=987654321,
        )
    wire["identity_origin"] = "sentinel-decode-private-identity-origin"
    return wire


@pytest.mark.parametrize(
    ("form", "stage", "parser"),
    (
        ("unary", "from_dict", parse_agent_server_wire_unary),
        ("unary", "inverse", parse_agent_server_wire_unary),
        ("unary", "unrecognized", parse_agent_server_wire_unary),
        ("chunk", "from_dict", parse_agent_server_wire_chunk),
        ("chunk", "inverse", parse_agent_server_wire_chunk),
        ("chunk", "unrecognized", parse_agent_server_wire_chunk),
    ),
)
def test_decode_failures_are_static_value_errors_without_private_cause(
    form, stage, parser
) -> None:
    wire = _private_decode_failure_wire(form, stage)

    with pytest.raises(ValueError) as raised:
        parser(wire)

    assert type(raised.value) is ValueError
    assert str(raised.value) == "invalid AgentServer wire response"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    formatted = "".join(traceback.format_exception(raised.value))
    private_sentinels = (
        "sentinel-decode-private-key",
        "sentinel-decode-private-value",
        "sentinel-decode-private-identity-origin",
        "sentinel-decode-from-dict-unary",
        "sentinel-decode-from-dict-chunk",
        "sentinel-decode-inverse-unary",
        "sentinel-decode-inverse-chunk",
        "987654321",
    )
    assert not [sentinel for sentinel in private_sentinels if sentinel in formatted]


def test_wire_codec_logs_are_content_free_across_all_public_paths(
    caplog, monkeypatch
) -> None:
    target_logger = logging.getLogger("jiuwenswarm.common.e2a.wire_codec")
    target_logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG, logger=target_logger.name)
    huge_sequence = 9876543210123456789

    normal_unary = AgentResponse(
        request_id="sentinel-wire-normal-unary-request-id",
        channel_id="sentinel-wire-normal-unary-channel-id",
        ok=True,
        payload={"Final-Text": "sentinel-wire-normal-unary-payload"},
    )
    normal_chunk = AgentResponseChunk(
        request_id="sentinel-wire-normal-chunk-request-id",
        channel_id="sentinel-wire-normal-chunk-channel-id",
        payload={"RAW AUDIO": "sentinel-wire-normal-chunk-payload"},
        is_complete=True,
    )

    try:
        unary_wire = encode_agent_response_for_wire(
            normal_unary,
            response_id="sentinel-wire-normal-unary-response-id",
            sequence=huge_sequence,
        )
        unary_back = parse_agent_server_wire_unary(unary_wire)
        chunk_wire = encode_agent_chunk_for_wire(
            normal_chunk,
            response_id="sentinel-wire-normal-chunk-response-id",
            sequence=huge_sequence,
        )
        chunk_back = parse_agent_server_wire_chunk(chunk_wire)

        fallback_unary_legacy = {
            "request_id": "sentinel-wire-fallback-unary-legacy-id",
            "channel_id": "sentinel-wire-fallback-unary-channel-id",
            "ok": True,
            "payload": {"private": "sentinel-wire-fallback-unary-payload"},
        }
        fallback_unary = e2a_response_from_agent_response(
            normal_unary,
            response_id="sentinel-wire-fallback-unary-response-id",
        )
        fallback_unary.request_id = "sentinel-wire-fallback-unary-request-id"
        fallback_unary.response_id = "sentinel-wire-fallback-unary-response-id"
        fallback_unary.metadata = {
            E2A_WIRE_LEGACY_AGENT_RESPONSE_KEY: fallback_unary_legacy
        }
        assert (
            parse_agent_server_wire_unary(fallback_unary.to_dict()).payload
            == fallback_unary_legacy["payload"]
        )

        fallback_chunk_legacy = {
            "request_id": "sentinel-wire-fallback-chunk-legacy-id",
            "channel_id": "sentinel-wire-fallback-chunk-channel-id",
            "payload": {"private": "sentinel-wire-fallback-chunk-payload"},
            "is_complete": True,
        }
        fallback_chunk = e2a_response_from_agent_chunk(
            normal_chunk,
            response_id="sentinel-wire-fallback-chunk-response-id",
            sequence=huge_sequence,
        )
        fallback_chunk.request_id = "sentinel-wire-fallback-chunk-request-id"
        fallback_chunk.response_id = "sentinel-wire-fallback-chunk-response-id"
        fallback_chunk.metadata = {
            E2A_WIRE_LEGACY_AGENT_CHUNK_KEY: fallback_chunk_legacy
        }
        assert (
            parse_agent_server_wire_chunk(fallback_chunk.to_dict()).payload
            == fallback_chunk_legacy["payload"]
        )

        deprecated_unary = {
            "request_id": "sentinel-wire-deprecated-unary-id",
            "channel_id": "sentinel-wire-deprecated-unary-channel",
            "ok": True,
            "payload": {"private": "sentinel-wire-deprecated-unary-payload"},
            "sentinel-wire-deprecated-unary-key": True,
        }
        deprecated_chunk = {
            "request_id": "sentinel-wire-deprecated-chunk-id",
            "channel_id": "sentinel-wire-deprecated-chunk-channel",
            "payload": {"private": "sentinel-wire-deprecated-chunk-payload"},
            "is_complete": True,
            "sentinel-wire-deprecated-chunk-key": True,
        }
        parse_agent_server_wire_unary(deprecated_unary)
        parse_agent_server_wire_chunk(deprecated_chunk)

        inverse_unary = e2a_response_from_agent_response(
            normal_unary,
            response_id="sentinel-wire-inverse-unary-response-id",
        )
        inverse_unary.request_id = "sentinel-wire-inverse-unary-request-id"
        inverse_unary.response_kind = "sentinel-wire-inverse-unary-kind"
        inverse_unary.status = "sentinel-wire-inverse-unary-status"
        with pytest.raises(ValueError):
            parse_agent_server_wire_unary(inverse_unary.to_dict())

        inverse_chunk = e2a_response_from_agent_chunk(
            normal_chunk,
            response_id="sentinel-wire-inverse-chunk-response-id",
            sequence=huge_sequence,
        )
        inverse_chunk.request_id = "sentinel-wire-inverse-chunk-request-id"
        inverse_chunk.response_kind = "sentinel-wire-inverse-chunk-kind"
        inverse_chunk.status = "sentinel-wire-inverse-chunk-status"
        with pytest.raises(ValueError):
            parse_agent_server_wire_chunk(inverse_chunk.to_dict())

        invalid_origin_wire = dict(unary_wire)
        invalid_origin_wire["identity_origin"] = "sentinel-wire-invalid-origin"
        with pytest.raises(ValueError):
            parse_agent_server_wire_unary(invalid_origin_wire)

        private_failure = type("SentinelWireExceptionClass", (RuntimeError,), {})

        def fail_unary_conversion(*args, **kwargs):
            raise private_failure("sentinel-wire-unary-exception-message")

        def fail_chunk_conversion(*args, **kwargs):
            raise private_failure("sentinel-wire-chunk-exception-message")

        monkeypatch.setattr(
            wire_codec,
            "e2a_response_from_agent_response",
            fail_unary_conversion,
        )
        encode_agent_response_for_wire(
            normal_unary,
            response_id="sentinel-wire-error-unary-response-id",
            sequence=huge_sequence,
        )
        monkeypatch.setattr(
            wire_codec,
            "e2a_response_from_agent_chunk",
            fail_chunk_conversion,
        )
        encode_agent_chunk_for_wire(
            normal_chunk,
            response_id="sentinel-wire-error-chunk-response-id",
            sequence=huge_sequence,
        )
    finally:
        target_logger.removeHandler(caplog.handler)

    assert unary_back.payload == normal_unary.payload
    assert chunk_back.payload == normal_chunk.payload
    assert normal_unary.payload == {"Final-Text": "sentinel-wire-normal-unary-payload"}
    assert normal_chunk.payload == {"RAW AUDIO": "sentinel-wire-normal-chunk-payload"}

    records = [record for record in caplog.records if record.name == target_logger.name]
    log_material = "\n".join(
        f"{record.getMessage()} args={record.args!r}" for record in records
    )
    private_sentinels = (
        "sentinel-wire-normal-unary-request-id",
        "sentinel-wire-normal-unary-channel-id",
        "sentinel-wire-normal-unary-payload",
        "sentinel-wire-normal-unary-response-id",
        "sentinel-wire-normal-chunk-request-id",
        "sentinel-wire-normal-chunk-channel-id",
        "sentinel-wire-normal-chunk-payload",
        "sentinel-wire-normal-chunk-response-id",
        "sentinel-wire-fallback-unary-legacy-id",
        "sentinel-wire-fallback-unary-channel-id",
        "sentinel-wire-fallback-unary-payload",
        "sentinel-wire-fallback-unary-request-id",
        "sentinel-wire-fallback-unary-response-id",
        "sentinel-wire-fallback-chunk-legacy-id",
        "sentinel-wire-fallback-chunk-channel-id",
        "sentinel-wire-fallback-chunk-payload",
        "sentinel-wire-fallback-chunk-request-id",
        "sentinel-wire-fallback-chunk-response-id",
        "sentinel-wire-deprecated-unary-id",
        "sentinel-wire-deprecated-unary-channel",
        "sentinel-wire-deprecated-unary-payload",
        "sentinel-wire-deprecated-unary-key",
        "sentinel-wire-deprecated-chunk-id",
        "sentinel-wire-deprecated-chunk-channel",
        "sentinel-wire-deprecated-chunk-payload",
        "sentinel-wire-deprecated-chunk-key",
        "sentinel-wire-inverse-unary-request-id",
        "sentinel-wire-inverse-unary-response-id",
        "sentinel-wire-inverse-unary-kind",
        "sentinel-wire-inverse-unary-status",
        "sentinel-wire-inverse-chunk-request-id",
        "sentinel-wire-inverse-chunk-response-id",
        "sentinel-wire-inverse-chunk-kind",
        "sentinel-wire-inverse-chunk-status",
        "sentinel-wire-invalid-origin",
        "SentinelWireExceptionClass",
        "sentinel-wire-unary-exception-message",
        "sentinel-wire-chunk-exception-message",
        "sentinel-wire-error-unary-response-id",
        "sentinel-wire-error-chunk-response-id",
        str(huge_sequence),
        E2A_WIRE_LEGACY_AGENT_RESPONSE_KEY,
        E2A_WIRE_LEGACY_AGENT_CHUNK_KEY,
    )
    assert records
    assert not [sentinel for sentinel in private_sentinels if sentinel in log_material]
    assert "response_kind=" not in log_material
    assert "status=" not in log_material
    assert "keys=" not in log_material
    assert not [record for record in records if record.exc_info is not None]


# ---------------------------------------------------------------------------
# SDD-0010 — wire truncation keeps budget / token_count / child meta
# ---------------------------------------------------------------------------


def test_snapshot_keep_keys_include_budget() -> None:
    from jiuwenswarm.server.wire_truncate import (
        _WORKFLOW_SNAPSHOT_KEEP_KEYS,
        _WORKFLOW_LIST_SUMMARY_KEEP_KEYS,
    )

    assert "budget" in _WORKFLOW_SNAPSHOT_KEEP_KEYS
    assert "budget" in _WORKFLOW_LIST_SUMMARY_KEEP_KEYS


def test_collapse_agent_keeps_token_count() -> None:
    from jiuwenswarm.server.wire_truncate import _workflow_agent_for_collapse

    agent = {
        "id": "k1",
        "name": "analyst",
        "status": "completed",
        "kind": "agent",
        "token_count": 12700,
        "outcome": "ok",
    }
    out = _workflow_agent_for_collapse(agent)
    assert out.get("token_count") == 12700


def test_collapse_phase_keeps_child_meta() -> None:
    from jiuwenswarm.server.wire_truncate import (
        _collapse_oversized_workflow_snapshot_item,
    )

    item = {
        "id": "wf_1",
        "name": "onboarding",
        "status": "running",
        "agent_count": 1,
        "completed_agent_count": 0,
        "started_at": "2026-08-01T10:00:00+08:00",
        "token_count": 12700,
        "budget": {
            "total": 5,
            "spent": 5,
            "remaining": 0,
            "scope": "leader",
            "exhausted": True,
        },
        "phases": [
            {
                "id": "p1",
                "name": "▸ intro #0",
                "status": "running",
                "agent_count": 1,
                "completed_agent_count": 0,
                "phase_type": "child",
                "nested_phase": "▸ intro #0",
                "parent_phase": "review",
                "agents": [],
            }
        ],
    }
    out = _collapse_oversized_workflow_snapshot_item(item)
    assert out["budget"]["exhausted"] is True
    assert out["token_count"] == 12700
    ph = out["phases"][0]
    assert ph.get("phase_type") == "child"
    assert ph.get("nested_phase") == "▸ intro #0"
    assert ph.get("parent_phase") == "review"
