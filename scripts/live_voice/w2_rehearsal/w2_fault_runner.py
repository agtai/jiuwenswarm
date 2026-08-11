"""Real-Gateway companion runner for the nine W2 product-plane faults.

This module never constructs server authority, writes evidence, or inspects the
task database.  Product probes travel through the public Gateway WebSocket
envelope.  P1 capture clones additionally use the production dedicated-media
WebSocket.  Stock-browser ownership is observed through Chrome DevTools network
events; CDP is not used to inject requests or mutate page state.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import copy
import io
import json
import urllib.parse
import urllib.request
import wave
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol, Sequence

from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAck,
    MediaAttach,
    MediaAudioFrame,
    MediaAuthorityBinding,
    MediaDetach,
    MediaDetachReason,
    MediaTransportViolation,
    deserialize_media_control,
    encode_audio_frame,
    serialize_media_control,
)
from jiuwenswarm.server.live_voice.batch_speech import MIN_BATCH_TIMEOUT_MS

P1_OPERATION = "speech.recognize.batch"
P1_METHOD = "live_voice.speech.recognize_batch"
P2_ACTIVATE_METHOD = "live_voice.composition.p2.activate"
P2_CLOSE_METHOD = "live_voice.composition.p2.close"
P2_METHOD = "live_voice.composition.p2.presentation.ack"
P3_ACK_METHOD = "live_voice.composition.p3.progress.ack"
P3_CONFIRM_METHOD = "live_voice.composition.p3.confirmation.issue"
P3_MUTATE_METHOD = "live_voice.composition.p3.mutate"
P3_STATUS_METHOD = "live_voice.task.status"
P3_EVENTS_METHOD = "live_voice.task.events"
P3_PROGRESS_CLOSE_METHOD = "live_voice.composition.p3.progress.close"
MEDIA_ACTIVATE_METHOD = "live_voice.media.activate"
MEDIA_CLOSE_METHOD = "live_voice.media.close"
MEDIA_SUBPROTOCOL = "live-voice.media.v1"
MEDIA_CONTRACT_VERSION = "live-voice.media.v1"
MAX_SAFE_INTEGER = (1 << 53) - 1
_CDP_READ_ONLY_COMMANDS = frozenset({"Network.enable", "Network.disable"})
_STOCK_OBSERVED_REQUEST_METHODS = frozenset(
    {
        P1_METHOD,
        P2_ACTIVATE_METHOD,
        P2_CLOSE_METHOD,
        P2_METHOD,
        P3_ACK_METHOD,
        P3_MUTATE_METHOD,
        P3_PROGRESS_CLOSE_METHOD,
        MEDIA_ACTIVATE_METHOD,
        MEDIA_CLOSE_METHOD,
    }
)
_STOCK_OBSERVED_EVENT_TYPES = frozenset({"live_voice.task.progress"})


class FaultRunnerError(RuntimeError):
    """A fault probe failed closed before it could claim a valid result."""


class FaultIdentity(Protocol):
    pair: int
    plane: Any
    fault_class: Any
    operation: str
    request_id: str
    source_record_id: str


class GatewayRpc(Protocol):
    async def request(
        self, method: str, params: Mapping[str, Any], *, request_id: str
    ) -> Mapping[str, Any]: ...


class SpeechLease(Protocol):
    params: Mapping[str, Any]

    async def close(self) -> None: ...


class SpeechLeaseFactory(Protocol):
    async def create(self, label: str) -> SpeechLease: ...


class P3Oracle(Protocol):
    async def snapshot(self, task_id: str) -> Mapping[str, Any]: ...

    async def wait_stock_retry(self, task_id: str) -> Mapping[str, Any]: ...

    async def wait_stock_progress_ack(
        self,
        *,
        after_delivery_id: str,
        expected_session_id: str,
        expected_task_id: str,
    ) -> Mapping[str, Any]: ...


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _required_text(value: Any, field: str, *, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        raise FaultRunnerError(f"{field} is invalid")
    return value


def _normalized_ws_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme not in {"ws", "wss"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise FaultRunnerError(
            "Gateway endpoint must be an explicit loopback WebSocket"
        )
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return f"{parsed.scheme}://{host}:{port}{parsed.path or '/'}"


def _normalized_stock_ws_url(value: str) -> str:
    """Match the stock socket without retaining its public connection options."""

    parsed = urllib.parse.urlsplit(value)
    if not parsed.query:
        return _normalized_ws_url(value)
    try:
        query = urllib.parse.parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=4,
        )
    except ValueError as exc:
        raise FaultRunnerError("stock WebSocket query is invalid") from exc
    allowed = {"provider", "api_base", "model", "project_dir"}
    keys = [key for key, _value in query]
    if not query or len(keys) != len(set(keys)) or any(key not in allowed for key in keys):
        raise FaultRunnerError("stock WebSocket query is outside the safe allowlist")
    for key, option in query:
        maximum = 2048 if key in {"api_base", "project_dir"} else 256
        if (
            not option
            or option != option.strip()
            or len(option) > maximum
            or any(ord(character) < 32 or ord(character) == 127 for character in option)
        ):
            raise FaultRunnerError(f"stock WebSocket {key} option is invalid")
    query_free = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, "", parsed.fragment)
    )
    return _normalized_ws_url(query_free)


def _normalized_http_origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise FaultRunnerError("stock Web origin must be explicit loopback HTTP")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return f"{parsed.scheme}://{host}:{port}"


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FaultRunnerError(f"{field} is unavailable")
    return value


def _copy_params(value: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(value))


def _walk_keys(value: Any) -> Sequence[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            found.append(str(key).casefold())
            found.extend(_walk_keys(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            found.extend(_walk_keys(child))
    return found


def _reject_credentials(params: Mapping[str, Any]) -> None:
    forbidden = {
        "auth_token",
        "api_key",
        "authorization",
        "bearer",
        "private_key",
        "private_key_path",
    }
    keys = _walk_keys(params)
    if any(key in forbidden for key in keys):
        raise FaultRunnerError("credential material is forbidden in companion requests")


def _validate_fault(
    identity: FaultIdentity,
    *,
    pair: int,
    plane: str,
    fault_class: str,
    operation: str,
) -> None:
    if (
        identity.pair != pair
        or _enum_value(identity.plane) != plane
        or _enum_value(identity.fault_class) != fault_class
        or identity.operation != operation
    ):
        raise FaultRunnerError("public fault-plan identity does not match the probe")
    _required_text(identity.request_id, "fault request_id")
    _required_text(identity.source_record_id, "fault source_record_id")


def _response_payload(value: Mapping[str, Any], request_id: str) -> Mapping[str, Any]:
    outer = _mapping(value, "Gateway response")
    if outer.get("type") != "res" or outer.get("id") != request_id:
        raise FaultRunnerError("Gateway response does not bind the exact request")
    if type(outer.get("ok")) is not bool:
        raise FaultRunnerError("Gateway response has no closed transport outcome")
    payload = _mapping(outer.get("payload"), "product response payload")
    if payload.get("request_id") != request_id:
        raise FaultRunnerError("product response request_id mismatch")
    if type(payload.get("ok")) is not bool:
        raise FaultRunnerError("product response has no closed outcome")
    # Gateway preserves AgentServer business failures as an exact product
    # payload while also setting the outer Web response to ok=false.  That is a
    # valid observed product error, not a transport rejection.  A failed outer
    # response remains inadmissible unless it carries the exact closed product
    # failure bound above.
    if outer.get("ok") is False and payload.get("ok") is not False:
        raise FaultRunnerError("Gateway transport rejected the product request")
    return payload


def _require_error(
    value: Mapping[str, Any],
    request_id: str,
    *,
    codes: set[str],
    reasons: set[str] | None = None,
    retriable: bool,
) -> Mapping[str, Any]:
    payload = _response_payload(value, request_id)
    error = _mapping(payload.get("error"), "product error")
    code = _required_text(error.get("code"), "product error code")
    reason = _required_text(error.get("reason"), "product error reason")
    reported_retriable = error.get("retriable")
    if reported_retriable is None:
        reported_retriable = code in {"TIMEOUT", "UNAVAILABLE"}
    if (
        payload.get("ok") is not False
        or payload.get("result") is not None
        or code not in codes
        or reported_retriable is not retriable
    ):
        raise FaultRunnerError(
            "product fault returned the wrong nested business code "
            f"(code={code!r}, reason={reason!r}, retriable={reported_retriable!r})"
        )
    if reasons is not None and reason not in reasons:
        raise FaultRunnerError(
            "product fault returned the wrong nested business reason"
        )
    return payload


def _require_success(
    value: Mapping[str, Any], request_id: str, *, status: str | None = None
) -> Mapping[str, Any]:
    payload = _response_payload(value, request_id)
    result = _mapping(payload.get("result"), "product success result")
    if payload.get("ok") is not True or payload.get("error") is not None:
        raise FaultRunnerError("product recovery did not succeed")
    if status is not None and result.get("status") != status:
        raise FaultRunnerError("product recovery returned the wrong status")
    return result


def _require_p1_success(result: Mapping[str, Any], params: Mapping[str, Any]) -> None:
    expected_capture = _mapping(params.get("capture"), "P1 request capture")
    capture = _mapping(result.get("capture"), "P1 recovery capture")
    if result.get("operation") != P1_OPERATION or dict(capture) != dict(
        expected_capture
    ):
        raise FaultRunnerError("P1 recovery did not bind the exact capture")
    event = _mapping(result.get("event"), "P1 recovery event")
    if (
        event.get("session_id") != expected_capture.get("capture_id")
        or event.get("generation") != expected_capture.get("capture_generation")
        or event.get("kind") != "final"
    ):
        raise FaultRunnerError("P1 recovery did not return an exact final event")
    hypothesis = _mapping(event.get("hypothesis"), "P1 recovery hypothesis")
    alternatives = hypothesis.get("alternatives")
    if not isinstance(alternatives, list) or not alternatives:
        raise FaultRunnerError("P1 recovery has no authoritative transcript")
    selected = _mapping(alternatives[0], "P1 selected transcript")
    _required_text(selected.get("display_text"), "P1 transcript", maximum=100_000)
    provider = _mapping(result.get("provider"), "P1 recovery provider")
    if provider.get("implementation_class") != "formal":
        raise FaultRunnerError("P1 recovery did not use the formal provider adapter")
    _required_text(provider.get("provider_id"), "P1 provider_id")
    _required_text(provider.get("model"), "P1 provider model")
    _required_text(result.get("voice_commit_receipt"), "P1 voice commit receipt")


def _require_exact_replay(first: Mapping[str, Any], replay: Mapping[str, Any]) -> None:
    if dict(first) != dict(replay):
        raise FaultRunnerError("fault response was not an exact retained replay")


def _control_id(identity: FaultIdentity, suffix: str) -> str:
    source = _required_text(identity.source_record_id, "fault source_record_id")
    return _required_text(f"{source}-{suffix}", "control request_id")


class W2FaultRunner:
    """Runs negative probes while leaving positive ownership with stock Web."""

    def __init__(self, rpc: GatewayRpc) -> None:
        self._rpc = rpc

    async def send_raw_for_test(
        self, method: str, params: Mapping[str, Any], *, request_id: str
    ) -> Mapping[str, Any]:
        return await self._request(method, params, request_id=request_id)

    async def _request(
        self, method: str, params: Mapping[str, Any], *, request_id: str
    ) -> Mapping[str, Any]:
        _required_text(method, "Gateway method")
        _required_text(request_id, "Gateway request_id")
        _reject_credentials(params)
        return await self._rpc.request(
            method, _copy_params(params), request_id=request_id
        )

    async def _fault_replay(
        self,
        *,
        method: str,
        params: Mapping[str, Any],
        request_id: str,
        codes: set[str],
        reasons: set[str] | None = None,
        retriable: bool = False,
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        first = await self._request(method, params, request_id=request_id)
        first_payload = _require_error(
            first,
            request_id,
            codes=codes,
            reasons=reasons,
            retriable=retriable,
        )
        replay = await self._request(method, params, request_id=request_id)
        replay_payload = _require_error(
            replay,
            request_id,
            codes=codes,
            reasons=reasons,
            retriable=retriable,
        )
        _require_exact_replay(first_payload, replay_payload)
        return first_payload, replay_payload

    async def probe_p1_retriable(
        self, identity: FaultIdentity, media: SpeechLeaseFactory
    ) -> None:
        _validate_fault(
            identity,
            pair=1,
            plane="p1.speech_media",
            fault_class="retriable",
            operation=P1_OPERATION,
        )
        failed_lease = await media.create(_control_id(identity, "fault-capture"))
        try:
            params = _copy_params(failed_lease.params)
            params["request_id"] = identity.request_id
            params["operation_id"] = identity.source_record_id
            await self._fault_replay(
                method=P1_METHOD,
                params=params,
                request_id=identity.request_id,
                codes={"UNAVAILABLE"},
                reasons={"SPEECH_W2_RETRIABLE_FAULT_INJECTED"},
                retriable=True,
            )
        finally:
            await failed_lease.close()

        recovery_id = _control_id(identity, "recovery")
        recovery_lease = await media.create(_control_id(identity, "recovery-capture"))
        try:
            recovery = _copy_params(recovery_lease.params)
            recovery["request_id"] = recovery_id
            recovery["operation_id"] = _control_id(identity, "recovery-operation")
            result = await self._request(P1_METHOD, recovery, request_id=recovery_id)
            recovered = _require_success(result, recovery_id)
            _require_p1_success(recovered, recovery)
        finally:
            await recovery_lease.close()

    async def probe_p1_non_retriable(
        self, identity: FaultIdentity, media: SpeechLeaseFactory
    ) -> None:
        _validate_fault(
            identity,
            pair=2,
            plane="p1.speech_media",
            fault_class="non_retriable",
            operation=P1_OPERATION,
        )
        lease = await media.create(_control_id(identity, "fault-capture"))
        try:
            invalid = _copy_params(lease.params)
            invalid["request_id"] = identity.request_id
            invalid["operation_id"] = identity.source_record_id
            invalid["timeout_ms"] = 0
            await self._fault_replay(
                method=P1_METHOD,
                params=invalid,
                request_id=identity.request_id,
                codes={"INVALID_ARGUMENT"},
                reasons={"INVALID_SPEECH_TIMEOUT"},
            )
            recovery_id = _control_id(identity, "recovery")
            recovery = _copy_params(invalid)
            recovery["request_id"] = recovery_id
            recovery["timeout_ms"] = 1_000
            result = await self._request(P1_METHOD, recovery, request_id=recovery_id)
            recovered = _require_success(result, recovery_id)
            _require_p1_success(recovered, recovery)
        finally:
            await lease.close()

    async def probe_p1_zero_effect(
        self, identity: FaultIdentity, media: SpeechLeaseFactory
    ) -> None:
        _validate_fault(
            identity,
            pair=3,
            plane="p1.speech_media",
            fault_class="zero_effect",
            operation=P1_OPERATION,
        )
        lease = await media.create(_control_id(identity, "reserved-capture"))
        try:
            reserve_id = _control_id(identity, "reserve")
            reserved = _copy_params(lease.params)
            reserved["request_id"] = reserve_id
            reserved["operation_id"] = _control_id(identity, "reserve-operation")
            reserved["timeout_ms"] = MIN_BATCH_TIMEOUT_MS
            reserve_response = await self._request(
                P1_METHOD,
                reserved,
                request_id=reserve_id,
            )
            _require_error(
                reserve_response,
                reserve_id,
                codes={"TIMEOUT"},
                reasons={"SPEECH_PROVIDER_TIMEOUT"},
                retriable=True,
            )
            stale = _copy_params(lease.params)
            stale["request_id"] = identity.request_id
            stale["operation_id"] = identity.source_record_id
            first, replay = await self._fault_replay(
                method=P1_METHOD,
                params=stale,
                request_id=identity.request_id,
                codes={"STALE"},
                reasons={"STALE_RECOGNITION_SESSION"},
            )
            _require_exact_replay(first, replay)
        finally:
            await lease.close()

        recovery_id = _control_id(identity, "recovery")
        recovery_lease = await media.create(_control_id(identity, "fresh-capture"))
        try:
            recovery = _copy_params(recovery_lease.params)
            recovery["request_id"] = recovery_id
            recovery["operation_id"] = _control_id(identity, "recovery-operation")
            result = await self._request(P1_METHOD, recovery, request_id=recovery_id)
            recovered = _require_success(result, recovery_id)
            _require_p1_success(recovered, recovery)
        finally:
            await recovery_lease.close()

    async def probe_p2_retriable(
        self, identity: FaultIdentity, canonical_ack: Mapping[str, Any]
    ) -> None:
        _validate_fault(
            identity,
            pair=1,
            plane="p2.conversation",
            fault_class="retriable",
            operation=P2_METHOD,
        )
        first = await self._request(
            P2_METHOD, canonical_ack, request_id=identity.request_id
        )
        _require_error(
            first,
            identity.request_id,
            codes={"UNAVAILABLE"},
            reasons={"PRODUCT_W2_RETRIABLE_FAULT_INJECTED"},
            retriable=True,
        )
        recovery = await self._request(
            P2_METHOD, canonical_ack, request_id=identity.request_id
        )
        _require_success(
            recovery, identity.request_id, status="presentation_acknowledged"
        )

    async def probe_p2_non_retriable(
        self, identity: FaultIdentity, canonical_ack: Mapping[str, Any]
    ) -> None:
        _validate_fault(
            identity,
            pair=2,
            plane="p2.conversation",
            fault_class="non_retriable",
            operation=P2_METHOD,
        )
        invalid = _copy_params(canonical_ack)
        invalid["contiguous_cursor"] = MAX_SAFE_INTEGER
        await self._fault_replay(
            method=P2_METHOD,
            params=invalid,
            request_id=identity.request_id,
            codes={"PROTOCOL_VIOLATION"},
            reasons={"ACK_BEYOND_PRODUCED_CURSOR"},
        )
        recovery_id = _control_id(identity, "recovery")
        recovery = await self._request(P2_METHOD, canonical_ack, request_id=recovery_id)
        _require_success(recovery, recovery_id, status="presentation_acknowledged")

    async def probe_p2_zero_effect(
        self, identity: FaultIdentity, canonical_ack: Mapping[str, Any]
    ) -> None:
        _validate_fault(
            identity,
            pair=3,
            plane="p2.conversation",
            fault_class="zero_effect",
            operation=P2_METHOD,
        )
        await self._fault_replay(
            method=P2_METHOD,
            params=canonical_ack,
            request_id=identity.request_id,
            codes={"STALE"},
            reasons={"PRODUCT_W2_STALE_FAULT_INJECTED"},
        )
        recovery_id = _control_id(identity, "recovery")
        recovery = await self._request(P2_METHOD, canonical_ack, request_id=recovery_id)
        _require_success(recovery, recovery_id, status="presentation_acknowledged")

    async def probe_p3_retriable(
        self,
        identity: FaultIdentity,
        canonical_ack: Mapping[str, Any],
        oracle: P3Oracle,
    ) -> None:
        _validate_fault(
            identity,
            pair=1,
            plane="p3.task",
            fault_class="retriable",
            operation=P3_ACK_METHOD,
        )
        canonical_delivery = _required_text(
            canonical_ack.get("delivery_id"), "canonical progress delivery_id"
        )
        canonical_session = _required_text(
            canonical_ack.get("session_id"), "canonical progress session_id"
        )
        canonical_task = _required_text(
            canonical_ack.get("task_id"), "canonical progress task_id"
        )
        negative = _copy_params(canonical_ack)
        negative["delivery_id"] = identity.source_record_id
        await self._fault_replay(
            method=P3_ACK_METHOD,
            params=negative,
            request_id=identity.request_id,
            codes={"UNAVAILABLE"},
            reasons={"TASK_PROGRESS_DELIVERY_UNAVAILABLE"},
            retriable=True,
        )
        recovered = _mapping(
            await oracle.wait_stock_progress_ack(
                after_delivery_id=canonical_delivery,
                expected_session_id=canonical_session,
                expected_task_id=canonical_task,
            ),
            "stock progress ACK",
        )
        if (
            recovered.get("source") != "stock_ui"
            or recovered.get("status") != "acknowledged"
            or recovered.get("session_id") != canonical_session
            or recovered.get("task_id") != canonical_task
            or not _is_text(recovered.get("attempt_id"))
            or not _is_text(recovered.get("source_event_id"))
            or not _is_text(recovered.get("progress_event_id"))
            or recovered.get("delivery_id")
            in {canonical_delivery, identity.source_record_id}
        ):
            raise FaultRunnerError(
                "stock UI did not own the canonical positive progress ACK"
            )

    async def _issue_retry_confirmation(
        self,
        identity: FaultIdentity,
        *,
        task_id: str,
        session_id: str,
        correlation_id: str,
    ) -> tuple[dict[str, Any], str]:
        issue_id = _control_id(identity, "confirmation")
        mutation = {
            "operation": "task.retry",
            "session_id": _required_text(session_id, "session_id"),
            "command_id": _control_id(identity, "command"),
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "correlation_id": _required_text(correlation_id, "correlation_id"),
            "task_id": _required_text(task_id, "task_id"),
        }
        response = await self._request(P3_CONFIRM_METHOD, mutation, request_id=issue_id)
        receipt = _require_success(response, issue_id, status="confirmation_issued")
        confirmation_id = _required_text(
            receipt.get("confirmation_id"), "confirmation_id"
        )
        return mutation, confirmation_id

    @staticmethod
    def _require_terminal(snapshot: Mapping[str, Any], task_id: str) -> None:
        if snapshot.get("task_id") != task_id or snapshot.get("state") != "terminal":
            raise FaultRunnerError(
                "P3 retry confirmation requires authoritative terminal A"
            )

    @staticmethod
    def _require_nonterminal_b(snapshot: Mapping[str, Any], task_id: str) -> None:
        if (
            snapshot.get("task_id") != task_id
            or snapshot.get("state")
            not in {"accepted", "running", "blocked", "decision_required"}
            or snapshot.get("attempt_number") != 2
        ):
            raise FaultRunnerError(
                "stock UI winner did not establish authoritative nonterminal B"
            )

    @staticmethod
    def _require_no_successor(
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        *,
        rejected_command_id: str,
    ) -> None:
        for field in ("task_id", "attempt_id", "attempt_number", "retry_count"):
            if before.get(field) != after.get(field):
                raise FaultRunnerError(
                    "rejected P3 mutation created or adopted a successor"
                )
        before_history = before.get("event_facts")
        after_history = after.get("event_facts")
        if not isinstance(before_history, tuple) or not isinstance(
            after_history, tuple
        ):
            raise FaultRunnerError("P3 event-history oracle is unavailable")
        if after_history[: len(before_history)] != before_history:
            raise FaultRunnerError("rejected P3 mutation rewrote authoritative history")
        allowed_progress = {
            "task.running",
            "task.blocked",
            "task.decision_required",
            "task.terminal",
        }
        for fact in after_history[len(before_history) :]:
            if (
                not isinstance(fact, tuple)
                or len(fact) != 5
                or fact[2] != before.get("attempt_id")
                or fact[3] not in allowed_progress
                or fact[4] == rejected_command_id
            ):
                raise FaultRunnerError(
                    "rejected P3 mutation appended command side effects"
                )

    async def probe_p3_non_retriable(
        self,
        identity: FaultIdentity,
        task_id: str,
        session_id: str,
        correlation_id: str,
        oracle: P3Oracle,
    ) -> None:
        _validate_fault(
            identity,
            pair=2,
            plane="p3.task",
            fault_class="non_retriable",
            operation=P3_MUTATE_METHOD,
        )
        terminal = _mapping(await oracle.snapshot(task_id), "P3 terminal snapshot")
        self._require_terminal(terminal, task_id)
        mutation, confirmation_id = await self._issue_retry_confirmation(
            identity,
            task_id=task_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        winner = _mapping(await oracle.wait_stock_retry(task_id), "stock retry B")
        if winner.get("operation") != "task.retry" or winner.get("task_id") != task_id:
            raise FaultRunnerError(
                "stock UI did not submit the independent winner retry"
            )
        before = _mapping(await oracle.snapshot(task_id), "P3 nonterminal snapshot")
        self._require_nonterminal_b(before, task_id)
        params = {**mutation, "confirmation_id": confirmation_id}
        await self._fault_replay(
            method=P3_MUTATE_METHOD,
            params=params,
            request_id=identity.request_id,
            codes={"CONFLICT"},
            reasons={"TASK_RETRY_REQUIRES_TERMINAL"},
        )
        after = _mapping(await oracle.snapshot(task_id), "P3 post-rejection snapshot")
        self._require_no_successor(
            before,
            after,
            rejected_command_id=_required_text(
                mutation.get("command_id"), "rejected P3 command_id"
            ),
        )

    async def probe_p3_zero_effect(
        self,
        identity: FaultIdentity,
        task_id: str,
        session_id: str,
        correlation_id: str,
        oracle: P3Oracle,
    ) -> None:
        _validate_fault(
            identity,
            pair=3,
            plane="p3.task",
            fault_class="zero_effect",
            operation=P3_MUTATE_METHOD,
        )
        before = _mapping(await oracle.snapshot(task_id), "P3 terminal snapshot")
        self._require_terminal(before, task_id)
        mutation, confirmation_id = await self._issue_retry_confirmation(
            identity,
            task_id=task_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        params = {**mutation, "confirmation_id": confirmation_id}
        await self._fault_replay(
            method=P3_MUTATE_METHOD,
            params=params,
            request_id=identity.request_id,
            codes={"STALE"},
            reasons={"PRODUCT_W2_STALE_FAULT_INJECTED"},
        )
        after = _mapping(await oracle.snapshot(task_id), "P3 post-STALE snapshot")
        if dict(before) != dict(after):
            raise FaultRunnerError("P3 STALE probe changed authoritative terminal A")
        winner = _mapping(await oracle.wait_stock_retry(task_id), "stock retry B")
        if winner.get("operation") != "task.retry" or winner.get("task_id") != task_id:
            raise FaultRunnerError("stock UI did not submit fresh retry B after STALE")
        successor = _mapping(await oracle.snapshot(task_id), "P3 successor snapshot")
        if (
            successor.get("task_id") != task_id
            or successor.get("attempt_number") != 2
            or successor.get("attempt_id") == before.get("attempt_id")
        ):
            raise FaultRunnerError("fresh stock UI retry did not establish successor B")


class GatewayWebSocketClient:
    """Bounded request/response client for the production Gateway Web route."""

    def __init__(
        self,
        endpoint: str,
        *,
        origin: str,
        request_timeout: float = 15.0,
    ) -> None:
        normalized = _normalized_ws_url(endpoint)
        parsed = urllib.parse.urlsplit(normalized)
        if parsed.path not in {"/ws", "/ws/gateway"}:
            raise FaultRunnerError("Gateway endpoint path is not the product Web route")
        self.endpoint = normalized
        self.origin = _normalized_http_origin(origin)
        self.request_timeout = request_timeout
        self._socket: Any = None
        self._receiver: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[Mapping[str, Any]]] = {}
        self._events: asyncio.Queue[Mapping[str, Any]] = asyncio.Queue(maxsize=256)

    async def __aenter__(self) -> "GatewayWebSocketClient":
        from websockets.asyncio.client import connect

        self._socket = await connect(
            self.endpoint,
            origin=self.origin,
            max_size=16 * 1024 * 1024,
            open_timeout=self.request_timeout,
            close_timeout=5,
        )
        self._receiver = asyncio.create_task(self._receive_loop())
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        receiver, self._receiver = self._receiver, None
        socket, self._socket = self._socket, None
        if socket is not None:
            await socket.close(code=1000, reason="W2 fault companion complete")
        if receiver is not None:
            try:
                await asyncio.wait_for(receiver, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                receiver.cancel()
        error = FaultRunnerError("Gateway companion closed")
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    async def _receive_loop(self) -> None:
        assert self._socket is not None
        try:
            async for raw in self._socket:
                if not isinstance(raw, str):
                    raise FaultRunnerError("Gateway Web route returned a binary frame")
                value = json.loads(raw)
                message = _mapping(value, "Gateway Web message")
                if message.get("type") == "res":
                    request_id = _required_text(
                        message.get("id"), "Gateway response id"
                    )
                    pending = self._pending.get(request_id)
                    if pending is None or pending.done():
                        raise FaultRunnerError(
                            "Gateway returned an unknown response id"
                        )
                    pending.set_result(dict(message))
                elif message.get("type") == "event":
                    if self._events.full():
                        raise FaultRunnerError("Gateway event buffer is full")
                    self._events.put_nowait(dict(message))
                else:
                    raise FaultRunnerError("Gateway returned an unknown Web envelope")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            error = FaultRunnerError("Gateway companion receive loop failed")
            error.__cause__ = exc
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)

    async def request(
        self, method: str, params: Mapping[str, Any], *, request_id: str
    ) -> Mapping[str, Any]:
        _reject_credentials(params)
        if self._socket is None:
            raise FaultRunnerError("Gateway companion is not connected")
        if request_id in self._pending:
            raise FaultRunnerError("duplicate in-flight Gateway request_id")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Mapping[str, Any]] = loop.create_future()
        self._pending[request_id] = future
        envelope = {
            "type": "req",
            "id": request_id,
            "method": method,
            "params": dict(params),
        }
        try:
            await self._socket.send(json.dumps(envelope, separators=(",", ":")))
            return await asyncio.wait_for(future, timeout=self.request_timeout)
        finally:
            self._pending.pop(request_id, None)

    async def wait_event(
        self, event_name: str, *, timeout: float | None = None
    ) -> Mapping[str, Any]:
        duration = self.request_timeout if timeout is None else timeout
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("Gateway event deadline elapsed")
            event = await asyncio.wait_for(self._events.get(), timeout=remaining)
            if event.get("event") == event_name:
                return event


@dataclass(frozen=True)
class ObservedWebMessage:
    direction: str
    socket_id: str
    socket_url: str
    message: Mapping[str, Any]


class ChromeNetworkObserver:
    """Read-only CDP observer for stock-Web ownership and exact wire receipts."""

    def __init__(
        self,
        debugger_url: str,
        *,
        stock_websocket_url: str,
        page_origin: str,
        timeout: float = 30.0,
    ) -> None:
        parsed = urllib.parse.urlsplit(debugger_url)
        if parsed.scheme != "http" or parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise FaultRunnerError("CDP debugger endpoint must be loopback HTTP")
        self.debugger_url = debugger_url.rstrip("/")
        self.stock_websocket_url = _normalized_ws_url(stock_websocket_url)
        self.page_origin = _normalized_http_origin(page_origin)
        self.timeout = timeout
        self._socket: Any = None
        self._receiver: asyncio.Task[None] | None = None
        self._command_seq = 0
        self._command_waiters: dict[int, asyncio.Future[Mapping[str, Any]]] = {}
        self._web_sockets: dict[str, str] = {}
        self._stock_socket_marker_emitted = False
        self._observed_requests: set[tuple[str, str]] = set()
        self._messages: asyncio.Queue[ObservedWebMessage] = asyncio.Queue(maxsize=512)
        self._backlog: deque[ObservedWebMessage] = deque()

    async def __aenter__(self) -> "ChromeNetworkObserver":
        target = await asyncio.to_thread(self._discover_target)
        from websockets.asyncio.client import connect

        self._socket = await connect(
            _required_text(
                target.get("webSocketDebuggerUrl"), "CDP target WebSocket", maximum=2048
            ),
            max_size=16 * 1024 * 1024,
            open_timeout=self.timeout,
            close_timeout=5,
        )
        self._receiver = asyncio.create_task(self._receive_loop())
        await self._command("Network.enable", {})
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    def _discover_target(self) -> Mapping[str, Any]:
        with urllib.request.urlopen(
            f"{self.debugger_url}/json/list", timeout=self.timeout
        ) as response:
            targets = json.load(response)
        if not isinstance(targets, list):
            raise FaultRunnerError("CDP target list is invalid")
        pages = [
            item
            for item in targets
            if isinstance(item, Mapping) and item.get("type") == "page"
        ]
        if len(pages) != 1:
            raise FaultRunnerError("isolated Chrome must expose exactly one page")
        page_url = _required_text(pages[0].get("url"), "CDP page URL", maximum=2048)
        parsed_page = urllib.parse.urlsplit(page_url)
        page_origin = urllib.parse.urlunsplit(
            (parsed_page.scheme, parsed_page.netloc, "", "", "")
        )
        if _normalized_http_origin(page_origin) != self.page_origin:
            raise FaultRunnerError(
                "isolated Chrome page origin is not the stock Web origin"
            )
        return pages[0]

    async def _command(
        self, method: str, params: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if method not in _CDP_READ_ONLY_COMMANDS:
            raise FaultRunnerError("CDP command is outside the read-only allowlist")
        if self._socket is None:
            raise FaultRunnerError("CDP observer is not connected")
        self._command_seq += 1
        command_id = self._command_seq
        future = asyncio.get_running_loop().create_future()
        self._command_waiters[command_id] = future
        try:
            await self._socket.send(
                json.dumps({"id": command_id, "method": method, "params": dict(params)})
            )
            response = await asyncio.wait_for(future, timeout=self.timeout)
            if "error" in response:
                raise FaultRunnerError("CDP read-only network command failed")
            return response
        finally:
            self._command_waiters.pop(command_id, None)

    async def _receive_loop(self) -> None:
        assert self._socket is not None
        async for raw in self._socket:
            if not isinstance(raw, str):
                raise FaultRunnerError("CDP returned a binary command frame")
            value = json.loads(raw)
            message = _mapping(value, "CDP message")
            command_id = message.get("id")
            if type(command_id) is int:
                future = self._command_waiters.get(command_id)
                if future is not None and not future.done():
                    future.set_result(dict(message))
                continue
            method = message.get("method")
            params = _mapping(message.get("params"), "CDP event params")
            if method == "Network.webSocketCreated":
                request_id = str(params.get("requestId", ""))
                url = str(params.get("url", ""))
                if request_id and url:
                    try:
                        normalized = _normalized_stock_ws_url(url)
                    except FaultRunnerError:
                        continue
                    if normalized == self.stock_websocket_url:
                        self._web_sockets[request_id] = normalized
                        if not self._stock_socket_marker_emitted:
                            print(
                                "W2_FAULT_RUNNER_STOCK_SOCKET_OBSERVED "
                                f"url={normalized}",
                                flush=True,
                            )
                            self._stock_socket_marker_emitted = True
                continue
            if method not in {
                "Network.webSocketFrameSent",
                "Network.webSocketFrameReceived",
            }:
                continue
            socket_id = str(params.get("requestId", ""))
            socket_url = self._web_sockets.get(socket_id)
            if socket_url != self.stock_websocket_url:
                continue
            response = _mapping(params.get("response"), "CDP WebSocket frame")
            if response.get("opcode") != 1:
                continue
            try:
                envelope = json.loads(str(response.get("payloadData", "")))
            except json.JSONDecodeError:
                continue
            if not isinstance(envelope, Mapping):
                continue
            direction = "sent" if method.endswith("Sent") else "received"
            envelope_type = envelope.get("type")
            if direction == "sent":
                request_id = envelope.get("id")
                request_method = envelope.get("method")
                if (
                    envelope_type != "req"
                    or type(request_id) is not str
                    or not request_id
                    or request_method not in _STOCK_OBSERVED_REQUEST_METHODS
                ):
                    continue
                request_key = (socket_id, request_id)
                if len(self._observed_requests) >= 512:
                    raise FaultRunnerError("CDP observed request ledger is full")
                self._observed_requests.add(request_key)
            elif envelope_type == "res":
                request_id = envelope.get("id")
                request_key = (socket_id, request_id)
                if (
                    type(request_id) is not str
                    or request_key not in self._observed_requests
                ):
                    continue
                self._observed_requests.discard(request_key)
            elif (
                envelope_type != "event"
                or envelope.get("event") not in _STOCK_OBSERVED_EVENT_TYPES
            ):
                continue
            observed = ObservedWebMessage(
                direction,
                socket_id,
                socket_url,
                dict(envelope),
            )
            if self._messages.full():
                raise FaultRunnerError("CDP product message buffer is full")
            self._messages.put_nowait(observed)

    async def close(self) -> None:
        if self._socket is not None:
            try:
                await self._command("Network.disable", {})
            except FaultRunnerError:
                pass
            socket, self._socket = self._socket, None
            await socket.close(code=1000, reason="W2 read-only observer complete")
        if self._receiver is not None:
            receiver, self._receiver = self._receiver, None
            try:
                await asyncio.wait_for(receiver, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                receiver.cancel()

    async def wait_message(
        self,
        predicate: Callable[[ObservedWebMessage], bool],
        *,
        timeout: float | None = None,
    ) -> ObservedWebMessage:
        for item in tuple(self._backlog):
            if predicate(item):
                self._backlog.remove(item)
                return item
        duration = self.timeout if timeout is None else timeout
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("stock Web observation deadline elapsed")
            item = await asyncio.wait_for(self._messages.get(), timeout=remaining)
            if predicate(item):
                return item
            self._backlog.append(item)
            if len(self._backlog) > 512:
                raise FaultRunnerError("CDP unmatched message buffer is full")

    async def wait_request(
        self, method: str, *, timeout: float | None = None
    ) -> ObservedWebMessage:
        return await self.wait_message(
            lambda item: (
                item.direction == "sent"
                and item.socket_url == self.stock_websocket_url
                and item.message.get("type") == "req"
                and item.message.get("method") == method
            ),
            timeout=timeout,
        )

    async def wait_response(
        self,
        request_id: str,
        *,
        socket_id: str,
        timeout: float | None = None,
    ) -> ObservedWebMessage:
        return await self.wait_message(
            lambda item: (
                item.direction == "received"
                and item.socket_id == socket_id
                and item.socket_url == self.stock_websocket_url
                and item.message.get("type") == "res"
                and item.message.get("id") == request_id
            ),
            timeout=timeout,
        )

    async def wait_exchange(
        self,
        method: str,
        *,
        predicate: Callable[[Mapping[str, Any]], bool] | None = None,
        timeout: float | None = None,
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        duration = self.timeout if timeout is None else timeout
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("stock Web exchange deadline elapsed")
            request = await self.wait_request(method, timeout=remaining)
            params = _mapping(request.message.get("params"), "stock Web request params")
            if predicate is not None and not predicate(params):
                continue
            request_id = _required_text(
                request.message.get("id"), "stock Web request_id"
            )
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("stock Web exchange deadline elapsed")
            response = await self.wait_response(
                request_id,
                socket_id=request.socket_id,
                timeout=remaining,
            )
            return dict(request.message), dict(response.message)


@dataclass(frozen=True)
class StockSpeechTemplate:
    p2_activation_params: Mapping[str, Any]
    media_activation_params: Mapping[str, Any]
    speech_params: Mapping[str, Any]

    def __post_init__(self) -> None:
        p2 = _mapping(self.p2_activation_params, "stock P2 activation")
        _reject_credentials(p2)
        activation = _mapping(self.media_activation_params, "stock media activation")
        speech = _mapping(self.speech_params, "stock Speech request")
        _reject_credentials(activation)
        _reject_credentials(speech)
        if (
            activation.get("session_id") != p2.get("session_id")
            or activation.get("interaction_id") != p2.get("interaction_id")
            or activation.get("correlation_id") != p2.get("correlation_id")
            or activation.get("activation_id") != p2.get("activation_id")
            or activation.get("activation_generation")
            != p2.get("activation_generation")
            or speech.get("operation") != P1_OPERATION
            or speech.get("session_id") != activation.get("session_id")
            or speech.get("correlation_id") != activation.get("correlation_id")
        ):
            raise FaultRunnerError("stock Speech/media template binding mismatch")
        audio = _mapping(speech.get("audio"), "stock Speech audio")
        _required_text(
            audio.get("data_base64"),
            "memory-only Speech audio",
            maximum=8 * 1024 * 1024,
        )


class GatewaySpeechLease:
    def __init__(
        self,
        *,
        rpc: GatewayRpc,
        params: Mapping[str, Any],
        close_params: Mapping[str, Any],
        close_request_id: str,
    ) -> None:
        self._rpc = rpc
        self.params = dict(params)
        self._close_params = dict(close_params)
        self._close_request_id = close_request_id
        self._closed = False

    async def close(self) -> None:
        if self._closed:
            return
        response = await self._rpc.request(
            MEDIA_CLOSE_METHOD,
            self._close_params,
            request_id=self._close_request_id,
        )
        outer = _mapping(response, "media close response")
        if (
            outer.get("type") != "res"
            or outer.get("id") != self._close_request_id
            or outer.get("ok") is not True
        ):
            raise FaultRunnerError("companion media route did not close gracefully")
        payload = _mapping(outer.get("payload"), "media close payload")
        if (
            payload.get("status") != "closed"
            or set(payload) != {"status", "reason_id", *self._close_params}
            or any(
                payload.get(key) != value for key, value in self._close_params.items()
            )
        ):
            raise FaultRunnerError("companion media authority did not close")
        self._closed = True


class GatewayDedicatedSpeechFactory:
    """Creates fresh authoritative P1 captures without persisting raw audio."""

    def __init__(
        self,
        rpc: GatewayRpc,
        template: StockSpeechTemplate,
        *,
        gateway_endpoint: str,
        origin: str,
        timeout: float = 15.0,
    ) -> None:
        self.rpc = rpc
        self.template = template
        self.gateway_endpoint = _normalized_ws_url(gateway_endpoint)
        self.origin = _normalized_http_origin(origin)
        self.timeout = timeout
        self._p2_binding: dict[str, Any] | None = None
        self._p2_close_params: dict[str, Any] | None = None
        self._p2_close_request_id: str | None = None

    async def activate(self, label: str) -> None:
        if self._p2_binding is not None:
            raise FaultRunnerError("companion P2 route is already active")
        source = _copy_params(self.template.p2_activation_params)
        source.update(
            {
                "interaction_id": _required_text(
                    f"{label}-interaction", "companion P2 interaction_id"
                ),
                "activation_id": _required_text(
                    f"{label}-activation", "companion P2 activation_id"
                ),
                "activation_generation": 1,
            }
        )
        request_id = _required_text(
            f"{label}-p2-activate", "companion P2 activate request_id"
        )
        binding = {
            key: source[key]
            for key in (
                "session_id",
                "correlation_id",
                "interaction_id",
                "activation_id",
                "activation_generation",
            )
        }
        self._p2_binding = binding
        self._p2_close_params = source
        self._p2_close_request_id = _required_text(
            f"{label}-p2-close", "companion P2 close request_id"
        )
        result = _require_success(
            await self.rpc.request(P2_ACTIVATE_METHOD, source, request_id=request_id),
            request_id,
            status="active",
        )
        if any(result.get(key) != value for key, value in binding.items()):
            raise FaultRunnerError("companion P2 activation response binding mismatch")

    async def close(self) -> None:
        binding = self._p2_binding
        close_params = self._p2_close_params
        request_id = self._p2_close_request_id
        if binding is None or close_params is None or request_id is None:
            return
        result = _require_success(
            await self.rpc.request(
                P2_CLOSE_METHOD, close_params, request_id=request_id
            ),
            request_id,
            status="closed",
        )
        if any(result.get(key) != value for key, value in binding.items()):
            raise FaultRunnerError("companion P2 close response binding mismatch")
        self._p2_binding = None
        self._p2_close_params = None
        self._p2_close_request_id = None

    async def create(self, label: str) -> GatewaySpeechLease:
        p2 = self._p2_binding
        if p2 is None:
            raise FaultRunnerError("companion P2 authority is not active")
        capture_id = _required_text(f"{label}-capture", "capture_id")
        track_id = _required_text(f"{label}-track", "track_id")
        activation = _copy_params(self.template.media_activation_params)
        activation.update(
            {
                **p2,
                "capture_id": capture_id,
                "capture_generation": 1,
                "track_id": track_id,
            }
        )
        activation_id = _required_text(
            f"{label}-media-activate", "media activation request_id"
        )
        response = await self.rpc.request(
            MEDIA_ACTIVATE_METHOD, activation, request_id=activation_id
        )
        outer = _mapping(response, "media activation response")
        if (
            outer.get("type") != "res"
            or outer.get("id") != activation_id
            or outer.get("ok") is not True
        ):
            raise FaultRunnerError("companion media activation failed")
        payload = _mapping(outer.get("payload"), "media activation payload")
        if (
            payload.get("status") != "active"
            or payload.get("subprotocol") != MEDIA_SUBPROTOCOL
        ):
            raise FaultRunnerError("companion media route is unavailable")
        subject_id = _required_text(payload.get("subject_id"), "media subject_id")
        close_params = {
            "session_id": activation["session_id"],
            "subject_id": subject_id,
            "correlation_id": activation["correlation_id"],
            "interaction_id": activation["interaction_id"],
            "activation_id": activation["activation_id"],
            "activation_generation": activation["activation_generation"],
        }
        lease = GatewaySpeechLease(
            rpc=self.rpc,
            params={},
            close_params=close_params,
            close_request_id=_required_text(
                f"{label}-media-close", "media close request_id"
            ),
        )
        try:
            if set(payload) != {
                "status",
                "reason_id",
                "subject_id",
                "endpoint_path",
                "subprotocol",
                "ticket_ttl_ms",
                "binding",
                "privacy",
            }:
                raise FaultRunnerError("companion media activation shape is not closed")
            privacy = _mapping(payload.get("privacy"), "media privacy boundary")
            if dict(privacy) != {
                "raw_audio_persisted": False,
                "raw_audio_logged": False,
                "memory_only": True,
            }:
                raise FaultRunnerError(
                    "companion media privacy boundary is unavailable"
                )
            binding = _typed_media_binding(payload.get("binding"))
            if (
                binding.session_id != activation["session_id"]
                or binding.interaction_id != activation["interaction_id"]
                or binding.correlation_id != activation["correlation_id"]
                or binding.track_id != track_id
                or binding.generation.id != capture_id
                or binding.generation.value != 1
                or binding.frame_format.sample_rate_hz != activation["sample_rate_hz"]
            ):
                raise FaultRunnerError("companion media authority binding mismatch")
            endpoint_path = _required_text(
                payload.get("endpoint_path"), "media endpoint", maximum=2048
            )
            await self._upload(endpoint_path, binding, self.template.speech_params)
            speech = _copy_params(self.template.speech_params)
            audio = _mapping(speech.get("audio"), "stock Speech audio")
            speech.update(
                {
                    "session_id": activation["session_id"],
                    "correlation_id": activation["correlation_id"],
                    "scope": {
                        "subject_id": subject_id,
                        "project_id": None,
                        "session_id": activation["session_id"],
                        "assurance": "authenticated",
                    },
                    "capture": {
                        "capture_id": capture_id,
                        "capture_generation": 1,
                        "track_id": track_id,
                        "final": True,
                    },
                    "audio": dict(audio),
                }
            )
            lease.params = speech
            return lease
        except BaseException:
            await lease.close()
            raise

    def _media_url(self, endpoint_path: str) -> str:
        base = urllib.parse.urlsplit(self.gateway_endpoint)
        return urllib.parse.urlunsplit(
            (base.scheme, base.netloc, endpoint_path, "", "")
        )

    async def _upload(
        self,
        endpoint_path: str,
        binding: MediaAuthorityBinding,
        speech: Mapping[str, Any],
    ) -> None:
        from websockets.asyncio.client import connect

        audio = _mapping(speech.get("audio"), "stock Speech audio")
        frames = _wav_frames(
            _required_text(
                audio.get("data_base64"),
                "memory-only Speech audio",
                maximum=8 * 1024 * 1024,
            ),
            binding,
        )
        async with connect(
            self._media_url(endpoint_path),
            origin=self.origin,
            subprotocols=[MEDIA_SUBPROTOCOL],
            max_size=2 * 1024 * 1024,
            open_timeout=self.timeout,
            close_timeout=5,
        ) as socket:
            if socket.subprotocol != MEDIA_SUBPROTOCOL:
                raise FaultRunnerError("dedicated media subprotocol was not negotiated")
            await self._transfer(socket, binding, frames)

    async def _transfer(
        self,
        socket: Any,
        binding: MediaAuthorityBinding,
        frames: Sequence[bytes],
    ) -> None:
        try:
            attach_raw = await asyncio.wait_for(socket.recv(), timeout=self.timeout)
            attach = deserialize_media_control(attach_raw)
        except (MediaTransportViolation, TypeError) as exc:
            raise FaultRunnerError("dedicated media attach is malformed") from exc
        if not isinstance(attach, MediaAttach) or attach.binding != binding:
            raise FaultRunnerError("dedicated media attach binding mismatch")
        for seq, frame in enumerate(frames):
            await socket.send(frame)
            try:
                ack_raw = await asyncio.wait_for(socket.recv(), timeout=self.timeout)
                ack = deserialize_media_control(ack_raw)
            except (MediaTransportViolation, TypeError) as exc:
                raise FaultRunnerError(
                    "dedicated media frame ACK is malformed"
                ) from exc
            if (
                not isinstance(ack, MediaAck)
                or ack.lease_id != binding.lease_id
                or ack.generation != binding.generation.value
                or ack.through_seq != seq
            ):
                raise FaultRunnerError("dedicated media frame ACK mismatch")
        expected_completion = MediaDetach(
            lease_id=binding.lease_id,
            generation=binding.generation.value,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
            through_seq=len(frames) - 1,
        )
        await socket.send(serialize_media_control(expected_completion))
        try:
            completion_raw = await asyncio.wait_for(
                socket.recv(), timeout=self.timeout
            )
            completion = deserialize_media_control(completion_raw)
        except asyncio.TimeoutError as exc:
            raise FaultRunnerError(
                "dedicated media completion receipt was not observed"
            ) from exc
        except (MediaTransportViolation, TypeError) as exc:
            raise FaultRunnerError(
                "dedicated media completion receipt is malformed"
            ) from exc
        except Exception as exc:
            raise FaultRunnerError(
                "dedicated media completion receipt was not observed"
            ) from exc
        if completion != expected_completion:
            raise FaultRunnerError("dedicated media completion receipt mismatch")
        wait_closed = getattr(socket, "wait_closed", None)
        if not callable(wait_closed):
            raise FaultRunnerError(
                "dedicated media detach completion is unavailable"
            )
        try:
            await asyncio.wait_for(wait_closed(), timeout=self.timeout)
        except asyncio.TimeoutError as exc:
            raise FaultRunnerError(
                "dedicated media detach completion was not observed"
            ) from exc


def _typed_media_binding(value: Any) -> MediaAuthorityBinding:
    try:
        control = deserialize_media_control(
            json.dumps(
                {
                    "type": "media.attach",
                    "contract_version": MEDIA_CONTRACT_VERSION,
                    "binding": _mapping(value, "media authority binding"),
                },
                separators=(",", ":"),
            )
        )
    except (MediaTransportViolation, TypeError) as exc:
        raise FaultRunnerError("media authority binding is malformed") from exc
    if not isinstance(control, MediaAttach):
        raise FaultRunnerError("media authority binding is unavailable")
    return control.binding


def _wav_frames(data_base64: str, binding: MediaAuthorityBinding) -> tuple[bytes, ...]:
    try:
        wav_bytes = base64.b64decode(data_base64, validate=True)
        with wave.open(io.BytesIO(wav_bytes), "rb") as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2:
                raise FaultRunnerError("stock Speech WAV is not PCM16 mono")
            pcm = source.readframes(source.getnframes())
            sample_rate = source.getframerate()
    except (ValueError, wave.Error) as exc:
        raise FaultRunnerError("stock Speech WAV is invalid") from exc
    frame_format = binding.frame_format
    samples_per_frame = frame_format.samples_per_channel
    if sample_rate != frame_format.sample_rate_hz:
        raise FaultRunnerError("stock Speech WAV does not match media frame authority")
    samples = tuple(
        int.from_bytes(pcm[index : index + 2], "little", signed=True)
        for index in range(0, len(pcm), 2)
    )
    if not samples or len(samples) % samples_per_frame:
        raise FaultRunnerError("stock Speech WAV does not contain exact 20 ms frames")
    frames: list[bytes] = []
    for seq, offset in enumerate(range(0, len(samples), samples_per_frame)):
        block = samples[offset : offset + samples_per_frame]
        floats = tuple(sample / 32768.0 for sample in block)
        frames.append(
            encode_audio_frame(
                binding,
                MediaAudioFrame(seq=seq, sample_cursor=offset, samples=floats),
            )
        )
    return tuple(frames)


def _stock_product_success(
    response: Mapping[str, Any], *, status: str | None = None
) -> Mapping[str, Any] | None:
    if response.get("type") != "res" or response.get("ok") is not True:
        return None
    payload = response.get("payload")
    if not isinstance(payload, Mapping) or payload.get("ok") is not True:
        return None
    result = payload.get("result")
    if not isinstance(result, Mapping):
        return None
    if status is not None and result.get("status") != status:
        return None
    return result


def _direct_stock_success(response: Mapping[str, Any], *, status: str) -> bool:
    return (
        response.get("type") == "res"
        and response.get("ok") is True
        and isinstance(response.get("payload"), Mapping)
        and response["payload"].get("status") == status
    )


class ChromeP3Oracle:
    """P3 truth from real task queries plus stock-Web wire ownership."""

    def __init__(
        self,
        rpc: GatewayRpc,
        observer: ChromeNetworkObserver,
        *,
        session_id: str,
        request_prefix: str,
        timeout: float = 30.0,
    ) -> None:
        self.rpc = rpc
        self.observer = observer
        self.session_id = _required_text(session_id, "P3 oracle session_id")
        self.request_prefix = _required_text(request_prefix, "P3 oracle request prefix")
        self.timeout = timeout
        self._sequence = 0

    def _next_id(self, suffix: str) -> str:
        self._sequence += 1
        return _required_text(
            f"{self.request_prefix}-{suffix}-{self._sequence}",
            "P3 oracle request_id",
        )

    async def snapshot(self, task_id: str) -> Mapping[str, Any]:
        exact_task_id = _required_text(task_id, "P3 snapshot task_id")
        status_id = self._next_id("status")
        status_response = await self.rpc.request(
            P3_STATUS_METHOD,
            {"session_id": self.session_id, "task_id": exact_task_id},
            request_id=status_id,
        )
        status_result = _require_success(status_response, status_id)
        task = _mapping(status_result.get("task"), "P3 status task")
        attempt = _mapping(status_result.get("attempt"), "P3 status attempt")
        if (
            task.get("task_id") != exact_task_id
            or attempt.get("task_id") != exact_task_id
        ):
            raise FaultRunnerError("P3 status returned a foreign task")
        events_id = self._next_id("events")
        events_response = await self.rpc.request(
            P3_EVENTS_METHOD,
            {"session_id": self.session_id, "task_id": exact_task_id, "after_seq": -1},
            request_id=events_id,
        )
        events_result = _require_success(events_response, events_id)
        events = events_result.get("events")
        if (
            not isinstance(events, list)
            or events_result.get("task_id") != exact_task_id
        ):
            raise FaultRunnerError("P3 events returned a foreign task")
        event_head = events_result.get("head_seq")
        if type(event_head) is not int or event_head < 0:
            raise FaultRunnerError("P3 event head is invalid")
        retry_count = 0
        event_facts: list[tuple[int, str, str, str, str]] = []
        for value in events:
            event = _mapping(value, "P3 task event")
            if event.get("task_id") != exact_task_id:
                raise FaultRunnerError("P3 event history contains a foreign task")
            seq = event.get("seq")
            if type(seq) is not int or seq < 0:
                raise FaultRunnerError("P3 event history contains an invalid sequence")
            event_type = _required_text(event.get("event_type"), "P3 event type")
            event_facts.append(
                (
                    seq,
                    _required_text(event.get("event_id"), "P3 event_id"),
                    _required_text(event.get("attempt_id"), "P3 event attempt_id"),
                    event_type,
                    _required_text(event.get("causation_id"), "P3 event causation_id"),
                )
            )
            if event_type == "task.retry_accepted":
                retry_count += 1
        if tuple(fact[0] for fact in event_facts) != tuple(
            sorted({fact[0] for fact in event_facts})
        ) or (event_facts and event_facts[-1][0] != event_head):
            raise FaultRunnerError("P3 event history is not a canonical prefix")
        attempt_number = attempt.get("attempt_number")
        if type(attempt_number) is not int or attempt_number not in {1, 2, 3}:
            raise FaultRunnerError("P3 attempt number is invalid")
        return {
            "task_id": exact_task_id,
            "attempt_id": _required_text(attempt.get("attempt_id"), "P3 attempt_id"),
            "attempt_number": attempt_number,
            "state": _required_text(task.get("state"), "P3 state"),
            "outcome": task.get("outcome"),
            "event_head": event_head,
            "retry_count": retry_count,
            "event_facts": tuple(event_facts),
        }

    async def wait_terminal(self, task_id: str) -> Mapping[str, Any]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout
        delay = 0.1
        while loop.time() < deadline:
            snapshot = await self.snapshot(task_id)
            if snapshot.get("state") == "terminal":
                return snapshot
            await asyncio.sleep(delay)
            delay = min(delay * 2, 1.0)
        raise FaultRunnerError(
            "P3 task did not reach terminal authority before timeout"
        )

    async def wait_stock_retry(self, task_id: str) -> Mapping[str, Any]:
        request, response = await self.observer.wait_exchange(
            P3_MUTATE_METHOD,
            predicate=lambda params: (
                params.get("operation") == "task.retry"
                and params.get("task_id") == task_id
            ),
        )
        request_id = _required_text(request.get("id"), "stock retry request_id")
        result = _stock_product_success(response, status="mutation_processed")
        if result is None or result.get("operation") != "task.retry":
            raise FaultRunnerError(
                "stock UI retry did not receive an authoritative success"
            )
        formal = _mapping(result.get("formal_task_result"), "stock retry formal result")
        if formal.get("task_id") != task_id:
            raise FaultRunnerError("stock UI retry returned a foreign task")
        return {
            "operation": "task.retry",
            "task_id": task_id,
            "request_id": request_id,
            "attempt_id": formal.get("attempt_id"),
        }

    async def wait_stock_progress_ack(
        self,
        *,
        after_delivery_id: str,
        expected_session_id: str,
        expected_task_id: str,
    ) -> Mapping[str, Any]:
        expected_session = _required_text(
            expected_session_id, "stock progress expected session_id"
        )
        expected_task = _required_text(
            expected_task_id, "stock progress expected task_id"
        )
        if expected_session != self.session_id:
            raise FaultRunnerError("stock progress expected a foreign oracle session")
        event = await self.observer.wait_message(
            lambda item: (
                item.direction == "received"
                and item.message.get("type") == "event"
                and item.message.get("event") == "live_voice.task.progress"
                and isinstance(item.message.get("payload"), Mapping)
                and item.message["payload"].get("session_id") == expected_session
                and item.message["payload"].get("task_id") == expected_task
                and item.message["payload"].get("delivery_id") != after_delivery_id
            )
        )
        payload = _mapping(event.message.get("payload"), "stock progress event")
        delivery_id = _required_text(
            payload.get("delivery_id"), "stock progress delivery_id"
        )
        source_event = _mapping(
            payload.get("source_event"), "stock progress source event"
        )
        progress_event = _mapping(
            payload.get("progress_event"), "stock progress projection event"
        )
        source_event_id = _required_text(
            source_event.get("event_id"), "stock progress source_event_id"
        )
        progress_event_id = _required_text(
            progress_event.get("event_id"), "stock progress progress_event_id"
        )
        seq = source_event.get("seq")
        if type(seq) is not int or seq < 0 or progress_event.get("seq") != seq:
            raise FaultRunnerError("stock progress event sequence mismatch")
        extensions = _mapping(
            source_event.get("extensions"), "stock progress extensions"
        )
        progress_return = _mapping(
            extensions.get("jiuwenswarm.task_progress_return"),
            "stock progress return extension",
        )
        attempt_id = _required_text(
            progress_return.get("persistent_attempt_id"),
            "stock progress attempt_id",
        )
        persistent_source = progress_return.get("persistent_source_event_id")
        if progress_return.get("persistent_event_seq") != seq or (
            persistent_source is not None and not _is_text(persistent_source)
        ):
            raise FaultRunnerError("stock progress persistent lineage mismatch")
        expected_ack = {
            "session_id": expected_session,
            "task_id": expected_task,
            "correlation_id": _required_text(
                payload.get("correlation_id"), "stock progress correlation_id"
            ),
            "origin_id": _required_text(
                payload.get("origin_id"), "stock progress origin_id"
            ),
            "generation_id": _required_text(
                payload.get("generation_id"), "stock progress generation_id"
            ),
            "generation": payload.get("generation"),
            "delivery_id": delivery_id,
            "source_event_id": source_event_id,
            "progress_event_id": progress_event_id,
            "seq": seq,
            "evidence_id": _required_text(
                payload.get("evidence_id"), "stock progress evidence_id"
            ),
        }
        if (
            type(expected_ack["generation"]) is not int
            or expected_ack["generation"] <= 0
        ):
            raise FaultRunnerError("stock progress generation is invalid")
        request, response = await self.observer.wait_exchange(
            P3_ACK_METHOD,
            predicate=lambda params: dict(params) == expected_ack,
        )
        result = _stock_product_success(response, status="acknowledged")
        if (
            result is None
            or result.get("attempt_id") != attempt_id
            or any(result.get(key) != value for key, value in expected_ack.items())
            or result.get("acknowledgement") != "web_ui_text_consumed"
            or not isinstance(result.get("replayed"), bool)
        ):
            raise FaultRunnerError("stock UI progress ACK binding mismatch")
        return {
            "delivery_id": delivery_id,
            "attempt_id": attempt_id,
            "session_id": expected_session,
            "task_id": expected_task,
            "source_event_id": source_event_id,
            "progress_event_id": progress_event_id,
            "status": "acknowledged",
            "source": "stock_ui",
            "request_id": request.get("id"),
        }


class ProductFaultPairRunner:
    """Sequences one pair's three faults around real stock-Web checkpoints."""

    def __init__(
        self,
        *,
        pair: int,
        plan: Any,
        rpc: GatewayRpc,
        observer: ChromeNetworkObserver,
        gateway_endpoint: str,
        origin: str,
        timeout: float = 30.0,
    ) -> None:
        if pair not in {1, 2, 3}:
            raise FaultRunnerError("fault pair must be 1, 2 or 3")
        self.pair = pair
        self.plan = plan
        self.rpc = rpc
        self.observer = observer
        self.gateway_endpoint = gateway_endpoint
        self.origin = origin
        self.timeout = timeout
        self.runner = W2FaultRunner(rpc)

    def _identity(self, plane: str) -> Any:
        fault_class = {1: "retriable", 2: "non_retriable", 3: "zero_effect"}[self.pair]
        require = getattr(self.plan, "require", None)
        if not callable(require):
            raise FaultRunnerError("public W2 fault plan has no closed lookup")
        return require(plane, fault_class)

    async def _stock_speech_template(self) -> StockSpeechTemplate:
        while True:
            speech_request, speech_response = await self.observer.wait_exchange(P1_METHOD)
            if _stock_product_success(speech_response) is None:
                continue
            speech = _mapping(speech_request.get("params"), "stock Speech params")
            capture = _mapping(speech.get("capture"), "stock Speech capture")
            activation_request, activation_response = await self.observer.wait_exchange(
                MEDIA_ACTIVATE_METHOD,
                predicate=lambda params: (
                    params.get("session_id") == speech.get("session_id")
                    and params.get("correlation_id") == speech.get("correlation_id")
                    and params.get("capture_id") == capture.get("capture_id")
                    and params.get("capture_generation")
                    == capture.get("capture_generation")
                    and params.get("track_id") == capture.get("track_id")
                ),
            )
            if not _direct_stock_success(activation_response, status="active"):
                continue
            activation = _mapping(
                activation_request.get("params"), "stock media activation params"
            )
            p2_request, p2_response = await self.observer.wait_exchange(
                P2_ACTIVATE_METHOD,
                predicate=lambda params: (
                    params.get("session_id") == activation.get("session_id")
                    and params.get("correlation_id")
                    == activation.get("correlation_id")
                    and params.get("interaction_id")
                    == activation.get("interaction_id")
                    and params.get("activation_id")
                    == activation.get("activation_id")
                    and params.get("activation_generation")
                    == activation.get("activation_generation")
                ),
            )
            p2_result = _stock_product_success(p2_response, status="active")
            if p2_result is None or p2_result.get("replayed") is not False:
                continue
            p2 = _mapping(p2_request.get("params"), "stock P2 activation params")
            close_request, close_response = await self.observer.wait_exchange(
                MEDIA_CLOSE_METHOD,
                predicate=lambda params: (
                    params.get("session_id") == activation.get("session_id")
                    and params.get("correlation_id") == activation.get("correlation_id")
                    and params.get("interaction_id")
                    == activation.get("interaction_id")
                    and params.get("activation_id")
                    == activation.get("activation_id")
                    and params.get("activation_generation")
                    == activation.get("activation_generation")
                ),
            )
            del close_request
            if not _direct_stock_success(close_response, status="closed"):
                raise FaultRunnerError("stock UI media route did not close gracefully")
            return StockSpeechTemplate(
                p2_activation_params=dict(p2),
                media_activation_params=dict(activation),
                speech_params=dict(speech),
            )

    async def _canonical_p2_ack(self) -> Mapping[str, Any]:
        while True:
            request, response = await self.observer.wait_exchange(P2_METHOD)
            if (
                _stock_product_success(response, status="presentation_acknowledged")
                is not None
            ):
                return dict(_mapping(request.get("params"), "stock P2 ACK params"))

    async def _canonical_p3_ack(self) -> Mapping[str, Any]:
        while True:
            request, response = await self.observer.wait_exchange(P3_ACK_METHOD)
            if _stock_product_success(response, status="acknowledged") is not None:
                return dict(_mapping(request.get("params"), "stock P3 ACK params"))

    async def _terminal_task(
        self, identity: FaultIdentity
    ) -> tuple[str, str, str, ChromeP3Oracle]:
        while True:
            create_request, create_response = await self.observer.wait_exchange(
                P3_MUTATE_METHOD,
                predicate=lambda params: params.get("operation") == "task.create",
            )
            create_result = _stock_product_success(
                create_response, status="mutation_processed"
            )
            if create_result is None:
                continue
            formal = _mapping(
                create_result.get("formal_task_result"), "stock task.create result"
            )
            task_id = _required_text(formal.get("task_id"), "stock task_id")
            params = _mapping(create_request.get("params"), "stock task.create params")
            session_id = _required_text(params.get("session_id"), "stock P3 session_id")
            correlation_id = _required_text(
                params.get("correlation_id"), "stock P3 correlation_id"
            )
            oracle = ChromeP3Oracle(
                self.rpc,
                self.observer,
                session_id=session_id,
                request_prefix=_control_id(identity, "oracle"),
                timeout=self.timeout,
            )
            _cancel_request, cancel_response = await self.observer.wait_exchange(
                P3_MUTATE_METHOD,
                predicate=lambda candidate: (
                    candidate.get("operation") == "task.cancel"
                    and candidate.get("task_id") == task_id
                ),
            )
            cancel_result = _stock_product_success(
                cancel_response, status="mutation_processed"
            )
            if cancel_result is None or cancel_result.get("operation") != "task.cancel":
                raise FaultRunnerError(
                    "stock UI cancel did not receive authoritative success"
                )
            cancel_formal = _mapping(
                cancel_result.get("formal_task_result"), "stock task.cancel result"
            )
            if cancel_formal.get("task_id") != task_id:
                raise FaultRunnerError("stock UI cancel returned a foreign task")
            terminal = await oracle.wait_terminal(task_id)
            if terminal.get("outcome") != "cancelled":
                raise FaultRunnerError("stock UI A did not reach terminal cancelled")
            return task_id, session_id, correlation_id, oracle

    async def run(self) -> None:
        p1_identity = self._identity("p1.speech_media")
        p2_identity = self._identity("p2.conversation")
        p3_identity = self._identity("p3.task")
        speech_template = await self._stock_speech_template()
        media = GatewayDedicatedSpeechFactory(
            self.rpc,
            speech_template,
            gateway_endpoint=self.gateway_endpoint,
            origin=self.origin,
            timeout=self.timeout,
        )
        try:
            await media.activate(_control_id(p1_identity, "companion"))
            if self.pair == 1:
                await self.runner.probe_p1_retriable(p1_identity, media)
            elif self.pair == 2:
                await self.runner.probe_p1_non_retriable(p1_identity, media)
            else:
                await self.runner.probe_p1_zero_effect(p1_identity, media)

            canonical_p2 = await self._canonical_p2_ack()
            if self.pair == 1:
                await self.runner.probe_p2_retriable(p2_identity, canonical_p2)
            elif self.pair == 2:
                await self.runner.probe_p2_non_retriable(p2_identity, canonical_p2)
            else:
                await self.runner.probe_p2_zero_effect(p2_identity, canonical_p2)

            if self.pair == 1:
                canonical_p3 = await self._canonical_p3_ack()
                oracle = ChromeP3Oracle(
                    self.rpc,
                    self.observer,
                    session_id=_required_text(
                        canonical_p3.get("session_id"), "P3 ACK session_id"
                    ),
                    request_prefix=_control_id(p3_identity, "oracle"),
                    timeout=self.timeout,
                )
                await self.runner.probe_p3_retriable(p3_identity, canonical_p3, oracle)
            else:
                task_id, session_id, correlation_id, oracle = await self._terminal_task(
                    p3_identity
                )
                if self.pair == 2:
                    await self.runner.probe_p3_non_retriable(
                        p3_identity,
                        task_id,
                        session_id,
                        correlation_id,
                        oracle,
                    )
                else:
                    await self.runner.probe_p3_zero_effect(
                        p3_identity,
                        task_id,
                        session_id,
                        correlation_id,
                        oracle,
                    )
        finally:
            await media.close()

    async def wait_stock_route_closure(self) -> None:
        p2_request, p2_response = await self.observer.wait_exchange(
            "live_voice.composition.p2.close"
        )
        p2_status = _stock_product_success(p2_response, status="closed")
        if p2_status is None:
            raise FaultRunnerError("stock P2 route did not close gracefully")
        del p2_request
        p3_request, p3_response = await self.observer.wait_exchange(
            P3_PROGRESS_CLOSE_METHOD
        )
        p3_status = _stock_product_success(p3_response, status="closed")
        if p3_status is None:
            raise FaultRunnerError("stock P3 progress route did not close gracefully")
        del p3_request


def derive_public_fault_plan(
    *, policy_id: str, candidate_sha: str, evidence_set_id: str
) -> Any:
    """Load the sole public derivation authority; never reproduce its hash."""

    from jiuwenswarm.server.live_voice.w2_fault_plan import (
        W2_FAULT_DERIVATION_VERSION,
        derive_w2_product_fault_plan,
    )

    plan = derive_w2_product_fault_plan(
        policy_id=policy_id,
        candidate_sha=candidate_sha,
        evidence_set_id=evidence_set_id,
        derivation_version=W2_FAULT_DERIVATION_VERSION,
    )
    if getattr(plan, "derivation_version", None) != W2_FAULT_DERIVATION_VERSION:
        raise FaultRunnerError(
            "public W2 fault plan returned the wrong derivation version"
        )
    return plan


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Observe stock Web and run the nine W2 product fault probes through Gateway"
    )
    parser.add_argument("--policy-id", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--evidence-set-id", required=True)
    parser.add_argument("--pair", required=True, type=int, choices=(1, 2, 3))
    parser.add_argument("--gateway-url", required=True)
    parser.add_argument("--stock-websocket-url", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--cdp-url", required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser


async def _run_cli(args: argparse.Namespace) -> None:
    plan = derive_public_fault_plan(
        policy_id=args.policy_id,
        candidate_sha=args.candidate_sha,
        evidence_set_id=args.evidence_set_id,
    )
    identities = tuple(getattr(plan, "items", ()))
    selected = tuple(
        item for item in identities if getattr(item, "pair", None) == args.pair
    )
    if len(selected) != 3:
        raise FaultRunnerError(
            "public W2 fault plan did not provide exactly three pair faults"
        )
    if args.timeout <= 0 or args.timeout > 900:
        raise FaultRunnerError("runner timeout must be in (0, 900] seconds")
    async with ChromeNetworkObserver(
        args.cdp_url,
        stock_websocket_url=args.stock_websocket_url,
        page_origin=args.origin,
        timeout=args.timeout,
    ) as observer:
        async with GatewayWebSocketClient(
            args.gateway_url,
            origin=args.origin,
            request_timeout=args.timeout,
        ) as rpc:
            pair_runner = ProductFaultPairRunner(
                pair=args.pair,
                plan=plan,
                rpc=rpc,
                observer=observer,
                gateway_endpoint=args.gateway_url,
                origin=args.origin,
                timeout=args.timeout,
            )
            async with asyncio.timeout(args.timeout):
                await pair_runner.run()
                await pair_runner.wait_stock_route_closure()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    asyncio.run(_run_cli(args))
    print(
        f"W2_FAULT_RUNNER_PRODUCT_FAULTS_PASS pair={args.pair} faults=3 routes=closed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
