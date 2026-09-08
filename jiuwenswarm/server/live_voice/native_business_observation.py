"""Closed private Native observation and Provider receipt representations."""

from __future__ import annotations

import json
from collections.abc import Mapping

NATIVE_BUSINESS_OBSERVATION_VERSION = "live-voice.native-business-observation.v1"
NATIVE_PROVIDER_RECEIPT_VERSION = "live-voice.native-provider-receipt.v1"
MAX_OBSERVATION_WAIT_MS = 1000


def is_task_acceptance_receipt(value: object) -> bool:
    """Recognize only the real create receipt; this grants no business authority."""
    if (not isinstance(value, Mapping)
            or value.get("contract_version") != "live-voice.native-business.v1"
            or value.get("operation") not in {"task.create", "task.create_successor"}
            or value.get("status") != "dispatched"):
        return False
    task_id, receipt = value.get("task_id"), value.get("receipt")
    return (type(task_id) is str and bool(task_id) and len(task_id) <= 256
            and isinstance(receipt, Mapping) and receipt.get("task_id") == task_id
            and receipt.get("state") == "accepted")


def is_nonterminal_work_start_receipt(value: object) -> bool:
    """Recognize an actual started analysis, without implying Task acceptance."""
    if (not isinstance(value, Mapping)
            or value.get("contract_version") != "live-voice.native-business.v1"
            or value.get("operation") != "work.start"
            or "status" in value or "reason" in value):
        return False
    work = value.get("work")
    if not isinstance(work, Mapping):
        return False
    work_id = work.get("work_id")
    return (type(work_id) is str and bool(work_id) and len(work_id) <= 256
            and type(work.get("revision")) is int and 1 <= work["revision"] <= 9_007_199_254_740_991
            and type(work.get("sequence")) is int and 1 <= work["sequence"] <= 9_007_199_254_740_991
            and type(work.get("state")) is str and work["state"] in {"accepted", "running"}
            and work.get("execution_settled") is False
            and work.get("reason") is None and "result_text" not in work)


def observation_cursor(value):
    if value is None:
        return None
    if (type(value) is not dict or set(value) != {"epoch", "sequence", "read_sequence"}
            or type(value["epoch"]) is not str or len(value["epoch"]) != 32
            or any(c not in "0123456789abcdef" for c in value["epoch"])
            or any(type(value[k]) is not int or not 0 <= value[k] <= 9_007_199_254_740_991
                   for k in ("sequence", "read_sequence"))):
        raise ValueError("invalid Native observation cursor")
    return dict(value)


def canonical_native_receipt(value: Mapping[str, object]) -> str:
    """Normalize first completion to the exact ordering retained by the journal."""
    return json.dumps(dict(value), ensure_ascii=True, allow_nan=False,
                      separators=(",", ":"), sort_keys=True)


def project_native_receipt(output: str) -> str:
    """Remove only context; the Engine supplies a complete snapshot per response.

    The caller has already validated the original canonical receipt and retains
    it for digest/replay. Unknown/ambiguous JSON stays byte-for-byte unchanged.
    """
    def closed_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate receipt key")
            result[key] = value
        return result
    try:
        value = json.loads(output, object_pairs_hook=closed_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if (type(value) is not dict or value.get("contract_version") != "live-voice.native-business.v1"
                or type(value.get("operation")) is not str):
            return output
        context = value.get("context")
        if (type(context) is not dict
                or set(context) != {"context_id", "history", "tasks", "works", "model"}
                or type(context["context_id"]) is not str or len(context["context_id"]) != 64
                or any(c not in "0123456789abcdef" for c in context["context_id"])
                or "provider_receipt_version" in value or "context_reference" in value):
            return output
        del value["context"]
        value["provider_receipt_version"] = NATIVE_PROVIDER_RECEIPT_VERSION
        value["context_reference"] = {"context_id": context["context_id"],
            "usage": "historical_receipt_context; current_context_supplied_before_response"}
        projected = json.dumps(value, ensure_ascii=False, allow_nan=False,
                               separators=(",", ":"), sort_keys=True)
        return projected if len(projected.encode("utf-8")) < len(output.encode("utf-8")) else output
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        return output
