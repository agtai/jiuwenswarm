# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""AgentServer ↔ Gateway WebSocket：E2AResponse 线编码 / 解码与 legacy 兜底。"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from enum import Enum
from typing import Any

from jiuwenswarm.common.e2a.constants import (
    E2A_RESPONSE_KIND_E2A_ERROR,
    E2A_RESPONSE_STATUS_FAILED,
    E2A_WIRE_LEGACY_AGENT_CHUNK_KEY,
    E2A_WIRE_LEGACY_AGENT_RESPONSE_KEY,
)
from jiuwenswarm.common.e2a.gateway_normalize import (
    e2a_response_from_agent_chunk,
    e2a_response_from_agent_response,
    e2a_response_to_agent_chunk,
    e2a_response_to_agent_response,
)
from jiuwenswarm.common.e2a.constants import E2A_SOURCE_PROTOCOL_E2A
from jiuwenswarm.common.e2a.models import (
    E2A_PROTOCOL_VERSION,
    E2AProvenance,
    E2AResponse,
    IdentityOrigin,
    utc_now_iso,
)
from jiuwenswarm.common.schema.agent import AgentResponse, AgentResponseChunk

logger = logging.getLogger(__name__)
_SAFE_EXCEPTION_CLASSES: tuple[tuple[type[BaseException], str], ...] = (
    (json.JSONDecodeError, "JSONDecodeError"),
    (ConnectionError, "ConnectionError"),
    (TimeoutError, "TimeoutError"),
    (OSError, "OSError"),
    (RuntimeError, "RuntimeError"),
    (TypeError, "TypeError"),
    (ValueError, "ValueError"),
)
_WIRE_DECODE_ERROR_MESSAGE = "invalid AgentServer wire response"
_WIRE_ENCODE_FAILURE_DETAILS = {
    "code": "E2A.WIRE_ENCODE_ERROR",
    "category": "wire_encode",
}


def _safe_exception_class(exc: BaseException) -> str:
    """Classify an error without logging its dynamic name, message or traceback."""
    for cls, category in _SAFE_EXCEPTION_CLASSES:
        if isinstance(exc, cls):
            return category
    return "Exception"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return _json_safe(value.model_dump(mode="json"))
        except Exception:
            return _json_safe(value.model_dump())
    if hasattr(value, "dict"):
        return _json_safe(value.dict())
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


def _exact_legacy_scalar(value: Any) -> Any:
    """Keep exact JSON scalars and replace subclasses/objects without hooks."""
    if value is None or type(value) in (str, int, float, bool):
        return value
    return ""


def _exact_legacy_text(value: Any, *, none_as_empty: bool) -> str:
    """Match legacy builtin-to-text behavior without calling subclass hooks."""
    value_type = type(value)
    if value_type is str:
        return value
    if value is None:
        return "" if none_as_empty else "None"
    if value_type is bool:
        return "True" if value else "False"
    if value_type in (int, float):
        return str(value)
    return ""


def _exact_legacy_channel_text(value: Any) -> str:
    """Preserve legacy ``str(value or '')`` semantics for exact builtins."""
    value_type = type(value)
    if value is None:
        return ""
    if value_type is str:
        return value
    if value_type is bool:
        return "True" if value else ""
    if value_type in (int, float):
        return str(value) if value else ""
    return ""


def _agent_response_legacy_snapshot(resp: AgentResponse) -> dict[str, Any]:
    """Project known response fields without dataclass deepcopy hooks."""
    if type(resp) is not AgentResponse:
        return {
            "request_id": "",
            "channel_id": "",
            "ok": False,
            "payload": None,
            "metadata": None,
            "agent_ref": None,
        }
    fields = object.__getattribute__(resp, "__dict__")
    if type(fields) is not dict:
        return {
            "request_id": "",
            "channel_id": "",
            "ok": False,
            "payload": None,
            "metadata": None,
            "agent_ref": None,
        }
    return {
        "request_id": _exact_legacy_scalar(fields.get("request_id")),
        "channel_id": _exact_legacy_scalar(fields.get("channel_id")),
        "ok": fields.get("ok") if type(fields.get("ok")) is bool else False,
        "payload": _json_safe(fields.get("payload")),
        "metadata": _json_safe(fields.get("metadata")),
        "agent_ref": _json_safe(fields.get("agent_ref")),
    }


def _agent_chunk_legacy_snapshot(chunk: AgentResponseChunk) -> dict[str, Any]:
    """Project known chunk fields without dataclass deepcopy hooks."""
    if type(chunk) is not AgentResponseChunk:
        return {
            "request_id": "",
            "channel_id": "",
            "payload": None,
            "is_complete": False,
            "agent_ref": None,
            "metadata": {},
        }
    fields = object.__getattribute__(chunk, "__dict__")
    if type(fields) is not dict:
        return {
            "request_id": "",
            "channel_id": "",
            "payload": None,
            "is_complete": False,
            "agent_ref": None,
            "metadata": {},
        }
    return {
        "request_id": _exact_legacy_scalar(fields.get("request_id")),
        "channel_id": _exact_legacy_scalar(fields.get("channel_id")),
        "payload": _json_safe(fields.get("payload")),
        "is_complete": (
            fields.get("is_complete")
            if type(fields.get("is_complete")) is bool
            else False
        ),
        "agent_ref": _json_safe(fields.get("agent_ref")),
        "metadata": _json_safe(fields.get("metadata")),
    }


def _sanitize_fallback_legacy_scalars(
    legacy: dict[str, Any],
    *,
    chunk: bool,
) -> dict[str, Any]:
    """Ensure every fallback scalar later inspected is an exact builtin."""
    if type(legacy) is not dict:
        return {
            "request_id": "",
            "channel_id": "",
            **({"is_complete": False} if chunk else {"ok": False}),
        }
    safe = dict(legacy)
    safe["request_id"] = _exact_legacy_scalar(legacy.get("request_id", ""))
    safe["channel_id"] = _exact_legacy_scalar(legacy.get("channel_id", ""))
    if chunk:
        complete = legacy.get("is_complete", False)
        safe["is_complete"] = complete if type(complete) is bool else False
    else:
        ok = legacy.get("ok", False)
        safe["ok"] = ok if type(ok) is bool else False
    return safe


def _raw_dict_to_agent_response(data: dict[str, Any]) -> AgentResponse:
    return AgentResponse(
        request_id=str(data["request_id"]),
        channel_id=str(data.get("channel_id", "")),
        ok=bool(data.get("ok", True)),
        payload=data.get("payload"),
        metadata=data.get("metadata"),
    )


def _raw_dict_to_agent_chunk(data: dict[str, Any]) -> AgentResponseChunk:
    return AgentResponseChunk(
        request_id=str(data["request_id"]),
        channel_id=str(data.get("channel_id", "")),
        payload=data.get("payload"),
        is_complete=bool(data.get("is_complete", False)),
    )


def is_e2a_response_wire_dict(data: dict[str, Any]) -> bool:
    """判别 JSON 对象是否为 E2A 响应线格式（与 ``E2AEnvelope`` 区分：须含非空 ``response_kind``）。"""
    if not isinstance(data, dict) or data.get("type") == "event":
        return False
    if data.get("protocol_version") != E2A_PROTOCOL_VERSION:
        return False
    rk = data.get("response_kind")
    return isinstance(rk, str) and bool(rk.strip())


def _deprecated_unary_shape(data: dict[str, Any]) -> bool:
    return (
        isinstance(data, dict)
        and "request_id" in data
        and "channel_id" in data
        and "ok" in data
        and not is_e2a_response_wire_dict(data)
    )


def _deprecated_chunk_shape(data: dict[str, Any]) -> bool:
    return (
        isinstance(data, dict)
        and "request_id" in data
        and "channel_id" in data
        and "is_complete" in data
        and "payload" in data
        and "ok" not in data
        and not is_e2a_response_wire_dict(data)
    )


def parse_agent_server_wire_unary(data: dict[str, Any]) -> AgentResponse:
    """将一条非流式 WebSocket JSON 解析为 ``AgentResponse``。"""
    if is_e2a_response_wire_dict(data):
        e2a: E2AResponse | None
        try:
            e2a = E2AResponse.from_dict(dict(data))
        except Exception as e:
            logger.error(
                "[E2A][wire][in][FAIL] stage=from_dict form=unary exception_class=%s",
                _safe_exception_class(e),
            )
            e2a = None
        if e2a is None:
            raise ValueError(_WIRE_DECODE_ERROR_MESSAGE) from None
        meta = dict(e2a.metadata or {})
        legacy = meta.get(E2A_WIRE_LEGACY_AGENT_RESPONSE_KEY)
        if legacy is not None and isinstance(legacy, dict):
            logger.warning(
                "[E2A][wire][in][fallback] form=unary legacy_present=true legacy_field_count=%s",
                len(legacy),
            )
            return _raw_dict_to_agent_response(legacy)
        out: AgentResponse | None
        try:
            out = e2a_response_to_agent_response(e2a)
            logger.debug(
                "[E2A][wire][in] form=unary legacy_present=false",
            )
        except Exception as e:
            logger.error(
                "[E2A][wire][in][FAIL] stage=inverse form=unary exception_class=%s",
                _safe_exception_class(e),
            )
            legacy_inv = meta.get(E2A_WIRE_LEGACY_AGENT_RESPONSE_KEY)
            if isinstance(legacy_inv, dict):
                logger.warning(
                    "[E2A][wire][in][fallback] stage=inverse form=unary legacy_present=true",
                )
                return _raw_dict_to_agent_response(legacy_inv)
            out = None
        if out is None:
            raise ValueError(_WIRE_DECODE_ERROR_MESSAGE) from None
        return out

    if _deprecated_unary_shape(data):
        logger.warning(
            "[E2A][wire][in][deprecated_legacy_shape] form=unary field_count=%s",
            len(data),
        )
        return _raw_dict_to_agent_response(data)

    logger.error(
        "[E2A][wire][in][FAIL] stage=shape form=unary exception_class=ValueError"
    )
    raise ValueError(_WIRE_DECODE_ERROR_MESSAGE) from None


def parse_agent_server_wire_chunk(data: dict[str, Any]) -> AgentResponseChunk:
    """将一条流式 WebSocket JSON 解析为 ``AgentResponseChunk``。"""
    if is_e2a_response_wire_dict(data):
        e2a: E2AResponse | None
        try:
            e2a = E2AResponse.from_dict(dict(data))
        except Exception as e:
            logger.error(
                "[E2A][wire][in][FAIL] stage=from_dict form=chunk exception_class=%s",
                _safe_exception_class(e),
            )
            e2a = None
        if e2a is None:
            raise ValueError(_WIRE_DECODE_ERROR_MESSAGE) from None
        meta = dict(e2a.metadata or {})
        legacy = meta.get(E2A_WIRE_LEGACY_AGENT_CHUNK_KEY)
        if legacy is not None and isinstance(legacy, dict):
            logger.warning(
                "[E2A][wire][in][fallback] form=chunk legacy_present=true legacy_field_count=%s",
                len(legacy),
            )
            return _raw_dict_to_agent_chunk(legacy)
        out: AgentResponseChunk | None
        try:
            out = e2a_response_to_agent_chunk(e2a)
            logger.debug(
                "[E2A][wire][in] form=chunk is_final=%s legacy_present=false",
                e2a.is_final,
            )
        except Exception as e:
            logger.error(
                "[E2A][wire][in][FAIL] stage=inverse form=chunk exception_class=%s",
                _safe_exception_class(e),
            )
            legacy_inv = meta.get(E2A_WIRE_LEGACY_AGENT_CHUNK_KEY)
            if isinstance(legacy_inv, dict):
                logger.warning(
                    "[E2A][wire][in][fallback] stage=inverse form=chunk legacy_present=true",
                )
                return _raw_dict_to_agent_chunk(legacy_inv)
            out = None
        if out is None:
            raise ValueError(_WIRE_DECODE_ERROR_MESSAGE) from None
        return out

    if _deprecated_chunk_shape(data):
        logger.warning(
            "[E2A][wire][in][deprecated_legacy_shape] form=chunk field_count=%s",
            len(data),
        )
        return _raw_dict_to_agent_chunk(data)

    logger.error(
        "[E2A][wire][in][FAIL] stage=shape form=chunk exception_class=ValueError"
    )
    raise ValueError(_WIRE_DECODE_ERROR_MESSAGE) from None


def encode_agent_response_for_wire(
    resp: AgentResponse,
    *,
    response_id: str,
    sequence: int = 0,
) -> dict[str, Any]:
    """``AgentResponse`` → E2A 线 dict；失败时 ``metadata`` 塞入整包 legacy 并记日志。"""
    try:
        e2a = e2a_response_from_agent_response(
            resp, response_id=response_id, sequence=sequence
        )
        try:
            wire = e2a.to_dict()
        except Exception as te:
            logger.error(
                "[E2A][wire][out][FAIL] stage=to_dict form=unary exception_class=%s legacy_stashed=true",
                _safe_exception_class(te),
            )
            return _fallback_wire_unary_from_legacy(
                _agent_response_legacy_snapshot(resp),
                response_id=response_id,
                sequence=sequence,
            )
        logger.info(
            "[E2A][wire][out] form=unary legacy_stashed=false",
        )
        return _json_safe(wire)
    except Exception as e:
        logger.error(
            "[E2A][wire][out][FAIL] stage=encode form=unary exception_class=%s legacy_stashed=true",
            _safe_exception_class(e),
        )
        return _fallback_wire_unary_from_legacy(
            _agent_response_legacy_snapshot(resp),
            response_id=response_id,
            sequence=sequence,
        )


def encode_agent_chunk_for_wire(
    chunk: AgentResponseChunk,
    *,
    response_id: str,
    sequence: int,
    is_stream: bool = True,
) -> dict[str, Any]:
    """``AgentResponseChunk`` → E2A 线 dict；失败时 ``metadata`` 塞入整包 legacy。"""
    try:
        e2a = e2a_response_from_agent_chunk(
            chunk,
            response_id=response_id,
            sequence=sequence,
            is_stream=is_stream,
        )
        try:
            wire = e2a.to_dict()
        except Exception as te:
            logger.error(
                "[E2A][wire][out][FAIL] stage=to_dict form=chunk exception_class=%s legacy_stashed=true",
                _safe_exception_class(te),
            )
            return _fallback_wire_chunk_from_legacy(
                _agent_chunk_legacy_snapshot(chunk),
                response_id=response_id,
                sequence=sequence,
                is_stream=is_stream,
            )
        logger.debug("[E2A][wire][out] form=chunk legacy_stashed=false")
        return _json_safe(wire)
    except Exception as e:
        logger.error(
            "[E2A][wire][out][FAIL] stage=encode form=chunk exception_class=%s legacy_stashed=true",
            _safe_exception_class(e),
        )
        return _fallback_wire_chunk_from_legacy(
            _agent_chunk_legacy_snapshot(chunk),
            response_id=response_id,
            sequence=sequence,
            is_stream=is_stream,
        )


def _fallback_wire_unary_from_legacy(
    legacy: dict[str, Any],
    *,
    response_id: str,
    sequence: int,
) -> dict[str, Any]:
    legacy = _sanitize_fallback_legacy_scalars(legacy, chunk=False)
    ts = utc_now_iso()
    prov = E2AProvenance(
        source_protocol=E2A_SOURCE_PROTOCOL_E2A,
        converter="jiuwenswarm.common.e2a.wire_codec:_fallback_wire_unary_from_legacy",
        converted_at=ts,
        details=dict(_WIRE_ENCODE_FAILURE_DETAILS),
    )
    e2a = E2AResponse(
        protocol_version=E2A_PROTOCOL_VERSION,
        response_id=_exact_legacy_scalar(response_id),
        request_id=_exact_legacy_text(
            legacy.get("request_id", ""), none_as_empty=False
        ),
        sequence=sequence if type(sequence) is int else 0,
        is_final=True,
        status=E2A_RESPONSE_STATUS_FAILED,
        response_kind=E2A_RESPONSE_KIND_E2A_ERROR,
        timestamp=ts,
        provenance=prov,
        body={
            "code": "E2A.WIRE_ENCODE_ERROR",
            "message": "Failed to encode AgentResponse as E2A; see metadata legacy blob",
            "details": dict(_WIRE_ENCODE_FAILURE_DETAILS),
        },
        channel=_exact_legacy_channel_text(legacy.get("channel_id")) or None,
        metadata={E2A_WIRE_LEGACY_AGENT_RESPONSE_KEY: legacy},
        identity_origin=IdentityOrigin.AGENT,
        is_stream=False,
    )
    return e2a.to_dict()


def _fallback_wire_chunk_from_legacy(
    legacy: dict[str, Any],
    *,
    response_id: str,
    sequence: int,
    is_stream: bool,
) -> dict[str, Any]:
    legacy = _sanitize_fallback_legacy_scalars(legacy, chunk=True)
    ts = utc_now_iso()
    prov = E2AProvenance(
        source_protocol=E2A_SOURCE_PROTOCOL_E2A,
        converter="jiuwenswarm.common.e2a.wire_codec:_fallback_wire_chunk_from_legacy",
        converted_at=ts,
        details=dict(_WIRE_ENCODE_FAILURE_DETAILS),
    )
    e2a = E2AResponse(
        protocol_version=E2A_PROTOCOL_VERSION,
        response_id=_exact_legacy_scalar(response_id),
        request_id=_exact_legacy_text(
            legacy.get("request_id", ""), none_as_empty=False
        ),
        sequence=sequence if type(sequence) is int else 0,
        is_final=legacy.get("is_complete", False),
        status=E2A_RESPONSE_STATUS_FAILED,
        response_kind=E2A_RESPONSE_KIND_E2A_ERROR,
        timestamp=ts,
        provenance=prov,
        body={
            "code": "E2A.WIRE_ENCODE_ERROR",
            "message": "Failed to encode AgentResponseChunk as E2A; see metadata legacy blob",
            "details": dict(_WIRE_ENCODE_FAILURE_DETAILS),
        },
        channel=_exact_legacy_channel_text(legacy.get("channel_id")) or None,
        metadata={E2A_WIRE_LEGACY_AGENT_CHUNK_KEY: legacy},
        identity_origin=IdentityOrigin.AGENT,
        is_stream=is_stream if type(is_stream) is bool else True,
    )
    return e2a.to_dict()


def encode_json_parse_error_wire(
    *,
    request_id: str,
    channel_id: str,
    message: str,
    response_id: str = "",
) -> dict[str, Any]:
    """入站 JSON 无法解析时发送的单帧 E2A 形错误（无 legacy blob）。"""
    ts = utc_now_iso()
    rid_out = response_id or (request_id or "invalid-json")
    e2a = E2AResponse(
        protocol_version=E2A_PROTOCOL_VERSION,
        response_id=rid_out,
        request_id=request_id or None,
        sequence=0,
        is_final=True,
        status=E2A_RESPONSE_STATUS_FAILED,
        response_kind=E2A_RESPONSE_KIND_E2A_ERROR,
        timestamp=ts,
        provenance=E2AProvenance(
            source_protocol=E2A_SOURCE_PROTOCOL_E2A,
            converter="jiuwenswarm.common.e2a.wire_codec:encode_json_parse_error_wire",
            converted_at=ts,
            details={"kind": "json_parse_error"},
        ),
        body={
            "code": "E2A.INVALID_JSON",
            "message": message,
            "details": {},
        },
        channel=channel_id or None,
        identity_origin=IdentityOrigin.AGENT,
        is_stream=False,
    )
    return e2a.to_dict()
