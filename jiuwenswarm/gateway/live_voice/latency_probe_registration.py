# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Local-only Browser latency-batch registration for the Web Gateway."""

from __future__ import annotations

import asyncio
import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Final

from jiuwenswarm.server.live_voice.latency_probe import (
    LatencyBatch,
    LatencyProbeRuntime,
    LatencyProbeViolation,
    LatencyProbeWriteResult,
)


LATENCY_PROBE_BATCH_METHOD: Final = "live_voice.latency_probe.batch"
_MAX_SESSION_STATES: Final = 256


@dataclass(slots=True)
class _AcceptedSession:
    run_id: str
    profile_id: str
    input_case_id: str
    next_round: int = 0
    accepted_rounds: OrderedDict[int, str] = field(default_factory=OrderedDict)


def _closed_result(
    status: str,
    batch_id: str = "",
    reason_code: str | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "batch_id": batch_id,
        "reason_code": reason_code,
    }


def _valid_dispatcher_session(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        return len(value.encode("utf-8")) <= 256
    except UnicodeEncodeError:
        return False


def register_latency_probe_rpc_handler(
    channel: object,
    runtime: LatencyProbeRuntime | None,
) -> None:
    """Register the diagnostic RPC only for one valid Gateway runtime."""

    if (
        not isinstance(runtime, LatencyProbeRuntime)
        or runtime.component != "gateway"
        or not callable(getattr(channel, "register_method", None))
        or not callable(getattr(channel, "send_response", None))
    ):
        return

    sessions: OrderedDict[str, _AcceptedSession] = OrderedDict()
    dispatch_lock = asyncio.Lock()

    async def _handle_batch(
        ws: Any,
        req_id: str,
        params: object,
        dispatcher_session_id: str,
    ) -> None:
        async with dispatch_lock:
            result = _closed_result("rejected", reason_code="INVALID_STRUCTURE")
            batch: LatencyBatch | None = None
            pending_acceptance: tuple[LatencyBatch, str] | None = None
            authorized_session_id = ""
            try:
                if not isinstance(params, dict) or set(params) != {"session_id", "batch"}:
                    raise LatencyProbeViolation("INVALID_STRUCTURE")
                claimed_session_id = params["session_id"]
                resolve_registered_session = getattr(
                    channel,
                    "_registered_session_for_websocket",
                    None,
                )
                if callable(resolve_registered_session):
                    authorized_session_id = resolve_registered_session(
                        ws,
                        claimed_session_id,
                    )
                if (
                    not _valid_dispatcher_session(authorized_session_id)
                    or authorized_session_id != dispatcher_session_id
                    or claimed_session_id != authorized_session_id
                ):
                    raise LatencyProbeViolation("IDENTITY_MISMATCH")
                batch = LatencyBatch.from_dict(params["batch"], runtime.run_config)
                if batch.component != "browser" or batch.phase != "browser_round":
                    raise LatencyProbeViolation("INCOMPATIBLE_RUN")
                if batch.round_index >= runtime.run_config.intended_attempts:
                    raise LatencyProbeViolation("SEQUENCE_GAP")

                digest = hashlib.sha256(batch.canonical_bytes()).hexdigest()
                session = sessions.get(authorized_session_id)
                identical_retry = False
                if session is None:
                    if batch.round_index != 0:
                        raise LatencyProbeViolation("SEQUENCE_GAP")
                else:
                    if (
                        batch.run_id != session.run_id
                        or batch.profile_id != session.profile_id
                        or batch.input_case_id != session.input_case_id
                    ):
                        raise LatencyProbeViolation("IDENTITY_MISMATCH")
                    prior_digest = session.accepted_rounds.get(batch.round_index)
                    if prior_digest is not None:
                        if prior_digest != digest:
                            raise LatencyProbeViolation("BATCH_CONFLICT")
                        identical_retry = True
                    elif batch.round_index < session.next_round:
                        raise LatencyProbeViolation("BATCH_CONFLICT")
                    elif batch.round_index > session.next_round:
                        raise LatencyProbeViolation("SEQUENCE_GAP")

                if identical_retry:
                    result = _closed_result("idempotent", batch.batch_id)
                else:
                    write_result = runtime.writer.write(batch)
                    if not isinstance(write_result, LatencyProbeWriteResult):
                        result = _closed_result("failed", batch.batch_id, "EXPORT_FAILED")
                    else:
                        result = _closed_result(
                            write_result.status,
                            write_result.batch_id,
                            write_result.reason_code,
                        )
                        if write_result.status in {"written", "idempotent"}:
                            pending_acceptance = (batch, digest)
            except LatencyProbeViolation as exc:
                result = _closed_result(
                    "rejected",
                    "" if batch is None else batch.batch_id,
                    exc.reason_code,
                )
            except Exception:
                result = _closed_result(
                    "failed",
                    "" if batch is None else batch.batch_id,
                    "EXPORT_FAILED",
                )

            try:
                enqueue_receipt = await channel.send_response(
                    ws,
                    req_id,
                    ok=True,
                    payload=result,
                )
            except Exception:
                return
            if enqueue_receipt is not True:
                return

            if pending_acceptance is not None:
                accepted_batch, accepted_digest = pending_acceptance
                session = sessions.get(authorized_session_id)
                if session is None:
                    session = _AcceptedSession(
                        accepted_batch.run_id,
                        accepted_batch.profile_id,
                        accepted_batch.input_case_id,
                    )
                    sessions[authorized_session_id] = session
                    while len(sessions) > _MAX_SESSION_STATES:
                        sessions.popitem(last=False)
                else:
                    sessions.move_to_end(authorized_session_id)
                if accepted_batch.round_index == session.next_round:
                    session.accepted_rounds[accepted_batch.round_index] = accepted_digest
                    session.next_round += 1

    channel.register_method(LATENCY_PROBE_BATCH_METHOD, _handle_batch)
