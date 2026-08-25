# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Gateway-only client for the three closed Native Runtime E2A methods."""

from __future__ import annotations

import asyncio
import copy
import hmac
import unicodedata
from dataclasses import dataclass
from typing import Any

from jiuwenswarm.common.e2a.gateway_normalize import e2a_from_agent_fields
from jiuwenswarm.common.schema.agent import AgentResponse
from jiuwenswarm.common.schema.live_voice_contract_v2 import MAX_SAFE_INTEGER, ResponseRef
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.live_voice.native_interaction_carrier import (
    NativeInteractionProposal,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    MAX_NATIVE_TRANSCRIPT_UTF8_BYTES,
    NATIVE_INTERACTION_CONTRACT_VERSION,
    NativeInteractionBinding,
    NativePresentationCursor,
)
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    MAX_NATIVE_DELEGATE_RESULT_UTF8_BYTES,
    NativeEngineEvent,
)
from jiuwenswarm.server.live_voice.presentation_ledger import PresentationAck
from jiuwenswarm.server.live_voice.voice_task_bridge import (
    UnifiedCommittedInputRoute,
)


NATIVE_GATEWAY_DESCRIPTOR_KEY = "_native_gateway"
NATIVE_BROWSER_DESCRIPTOR_KEY = "native_interaction"
NATIVE_GATEWAY_CHANNEL = "live_voice_native_gateway"
NATIVE_INTERNAL_REQ_METHODS = frozenset(
    {
        ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_PROPOSE.value,
        ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_PRESENTATION_ACK.value,
        ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_CLOSE.value,
    }
)
_MAX_REQUEST_SECONDS = 30.0
_MAX_REQUEST_ID_CHARS = 256
_MAX_REQUEST_ID_BYTES = 1_024


class NativeRuntimeClientError(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class GatewayNativeRuntimeClientSnapshot:
    activation_count: int
    completed_requests: int


@dataclass(frozen=True, slots=True, repr=False)
class GatewayNativeActivation:
    """Process-private handle for one exact Browser-owned Native activation."""

    binding: NativeInteractionBinding
    capability: str
    connection_id: str


def _capability(value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise NativeRuntimeClientError(
            "NATIVE_RUNTIME_CAPABILITY_INVALID",
            "Native Runtime capability is not canonical",
        )
    return value


def _request_identity(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_REQUEST_ID_CHARS
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in value
        )
    ):
        raise NativeRuntimeClientError(
            "NATIVE_RUNTIME_REQUEST_ID_INVALID", "request_id is not canonical"
        )
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        encoded = b"x" * (_MAX_REQUEST_ID_BYTES + 1)
    if len(encoded) > _MAX_REQUEST_ID_BYTES:
        raise NativeRuntimeClientError(
            "NATIVE_RUNTIME_REQUEST_ID_INVALID", "request_id is not canonical"
        )
    return value


def _closed_result(
    result: dict[str, object], keys: frozenset[str]
) -> dict[str, object]:
    if set(result) != keys:
        raise NativeRuntimeClientError(
            "NATIVE_RUNTIME_RESPONSE_INVALID",
            "AgentServer Native result fields are not closed",
        )
    return result


def _canonical_result_identity(value: object) -> bool:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_REQUEST_ID_CHARS
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in value
        )
    ):
        return False
    try:
        return len(value.encode("utf-8")) <= _MAX_REQUEST_ID_BYTES
    except UnicodeEncodeError:
        return False


def _canonical_response_ref(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "interaction_id",
        "response_id",
        "response_generation",
    }:
        return False
    generation = value.get("response_generation")
    return (
        _canonical_result_identity(value.get("interaction_id"))
        and _canonical_result_identity(value.get("response_id"))
        and type(generation) is int
        and 0 < generation <= MAX_SAFE_INTEGER
    )


def _canonical_audio_presentation_unit(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "response",
        "surface",
        "unit_id",
        "seq",
        "source_start_utf8",
        "source_end_utf8",
        "content_ref",
    }:
        return False
    seq = value.get("seq")
    start = value.get("source_start_utf8")
    end = value.get("source_end_utf8")
    content_ref = value.get("content_ref")
    return (
        _canonical_response_ref(value.get("response"))
        and value.get("surface") == "audio"
        and _canonical_result_identity(value.get("unit_id"))
        and type(seq) is int
        and 0 <= seq <= MAX_SAFE_INTEGER
        and type(start) is int
        and 0 <= start <= MAX_SAFE_INTEGER
        and type(end) is int
        and start < end <= MAX_SAFE_INTEGER
        and type(content_ref) is str
        and content_ref.startswith("sha256:")
        and len(content_ref) == 71
        and all(character in "0123456789abcdef" for character in content_ref[7:])
    )


def _canonical_transcript(value: object) -> bool:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in value
        )
    ):
        return False
    try:
        return len(value.encode("utf-8")) <= MAX_NATIVE_TRANSCRIPT_UTF8_BYTES
    except UnicodeEncodeError:
        return False


def _canonical_delegate_result(value: object) -> bool:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in value
        )
    ):
        return False
    try:
        return len(value.encode("utf-8")) <= MAX_NATIVE_DELEGATE_RESULT_UTF8_BYTES
    except UnicodeEncodeError:
        return False


def _validate_method_result(
    method: ReqMethod, result: dict[str, object]
) -> dict[str, object]:
    kind = result.get("kind")
    if method is ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_PROPOSE:
        if kind in {"action", "turn", "done"}:
            _closed_result(result, frozenset({"kind", "status", "accepted"}))
            valid = (
                result.get("status") == "observed"
                and type(result.get("accepted")) is bool
            )
        elif kind == "response":
            _closed_result(
                result,
                frozenset(
                    {
                        "kind",
                        "status",
                        "accepted",
                        "provider_response_id",
                        "response",
                    }
                ),
            )
            response = result.get("response")
            valid = (
                result.get("status") == "observed"
                and result.get("accepted") is True
                and _canonical_result_identity(result.get("provider_response_id"))
                and _canonical_response_ref(response)
            )
        elif kind == "audio":
            _closed_result(
                result,
                frozenset({"kind", "status", "accepted", "presentation_unit"}),
            )
            valid = (
                result.get("status") == "observed"
                and type(result.get("accepted")) is bool
                and _canonical_audio_presentation_unit(result.get("presentation_unit"))
            )
        elif kind == "delegate":
            _closed_result(
                result,
                frozenset(
                    {
                        "kind",
                        "status",
                        "accepted",
                        "provider_call_id",
                        "route",
                        "turn_commit_id",
                        "canonical_text",
                        "response",
                    }
                ),
            )
            valid = (
                result.get("status") == "completed"
                and type(result.get("accepted")) is bool
                and _canonical_result_identity(result.get("provider_call_id"))
                and result.get("route")
                in {route.value for route in UnifiedCommittedInputRoute}
                and _canonical_result_identity(result.get("turn_commit_id"))
                and _canonical_delegate_result(result.get("canonical_text"))
                and _canonical_response_ref(result.get("response"))
            )
        else:
            valid = False
    elif method is ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_PRESENTATION_ACK:
        if kind == "presentation_ack":
            eligible = result.get("history_eligible")
            expected = {"kind", "status", "history_eligible"}
            if eligible is True:
                expected.add("history")
            _closed_result(result, frozenset(expected))
            history = result.get("history")
            transcript = (
                history.get("transcript") if isinstance(history, dict) else None
            )
            presented_at = (
                history.get("presented_at") if isinstance(history, dict) else None
            )
            valid = (
                result.get("status") == "observed"
                and type(eligible) is bool
                and (
                    eligible is False
                    or (
                        isinstance(history, dict)
                        and set(history) == {"response", "transcript", "presented_at"}
                        and _canonical_response_ref(history.get("response"))
                        and _canonical_transcript(transcript)
                        and _canonical_result_identity(presented_at)
                    )
                )
            )
        elif kind == "played_cursor":
            _closed_result(
                result,
                frozenset({"kind", "status", "applied", "cancel_command_id"}),
            )
            command_id = result.get("cancel_command_id")
            valid = (
                result.get("status") == "observed"
                and type(result.get("applied")) is bool
                and (command_id is None or _canonical_result_identity(command_id))
            )
        elif kind == "response_fence":
            _closed_result(
                result,
                frozenset({"kind", "status", "applied", "cancel_command_id"}),
            )
            command_id = result.get("cancel_command_id")
            valid = (
                result.get("status") == "observed"
                and type(result.get("applied")) is bool
                and (command_id is None or _canonical_result_identity(command_id))
            )
        else:
            valid = False
    elif method is ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_CLOSE:
        _closed_result(result, frozenset({"kind", "status", "accepted"}))
        valid = (
            kind == "close"
            and result.get("status") == "closed"
            and result.get("accepted") is True
        )
    else:
        valid = False
    if not valid:
        raise NativeRuntimeClientError(
            "NATIVE_RUNTIME_RESPONSE_INVALID",
            "AgentServer Native result is not canonical for the request method",
        )
    return dict(result)


class GatewayNativeInteractionRuntimeClient:
    """Holds process-private activation capabilities and sends closed E2A."""

    def __init__(
        self,
        agent_client: Any,
        *,
        native_model: str,
        timeout_seconds: float = 5.0,
    ) -> None:
        if not callable(getattr(agent_client, "send_request", None)):
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_AGENT_UNAVAILABLE",
                "AgentServer client is unavailable",
            )
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 < float(timeout_seconds) <= _MAX_REQUEST_SECONDS
        ):
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_TIMEOUT_INVALID",
                "Native Runtime timeout must be positive and bounded",
            )
        if not _canonical_result_identity(native_model):
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_MODEL_INVALID",
                "Native Realtime model is not canonical",
            )
        self._agent = agent_client
        self._native_model = native_model
        self._timeout_seconds = float(timeout_seconds)
        self._activations: dict[tuple[str, str], GatewayNativeActivation] = {}
        self._completed_requests = 0

    def _decode_activation_response(
        self,
        payload: dict[str, object],
        *,
        routed_session_id: str | None,
        connection_id: str | None,
        request_method: str | None,
    ) -> tuple[dict[str, object], dict[str, object] | None, GatewayNativeActivation | None]:
        sanitized = copy.deepcopy(payload)
        result = sanitized.get("result")
        if not isinstance(result, dict):
            return sanitized, None, None
        descriptor = result.pop(NATIVE_GATEWAY_DESCRIPTOR_KEY, None)
        if descriptor is None:
            return sanitized, result, None
        if (
            request_method != ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value
            or payload.get("ok") is not True
            or result.get("status") != "active"
            or not isinstance(descriptor, dict)
            or set(descriptor) != {"contract_version", "binding", "capability"}
            or descriptor.get("contract_version") != NATIVE_INTERACTION_CONTRACT_VERSION
            or type(connection_id) is not str
            or not connection_id
        ):
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_ACTIVATION_INVALID",
                "Native activation descriptor is not on the exact private seam",
            )
        try:
            binding = NativeInteractionBinding.from_dict(descriptor["binding"])
        except Exception as error:
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_ACTIVATION_INVALID",
                "Native activation binding is invalid",
            ) from error
        visible = (
            result.get("session_id"),
            result.get("correlation_id"),
            result.get("interaction_id"),
            result.get("activation_id"),
            result.get("activation_generation"),
        )
        expected = (
            binding.scope.session_id,
            binding.correlation_id,
            binding.interaction_id,
            binding.activation_id,
            binding.activation_generation,
        )
        if routed_session_id != binding.scope.session_id or visible != expected:
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_ACTIVATION_MISMATCH",
                "Native activation descriptor does not match visible P2 authority",
            )
        capability = _capability(descriptor["capability"])
        return (
            sanitized,
            result,
            GatewayNativeActivation(binding, capability, connection_id),
        )

    def observe_activation_response(
        self,
        payload: dict[str, object],
        *,
        routed_session_id: str | None,
        connection_id: str | None,
        request_method: str | None,
    ) -> dict[str, object]:
        """Consume and remove one private descriptor before Browser delivery."""

        sanitized, result, activation = self._decode_activation_response(
            payload,
            routed_session_id=routed_session_id,
            connection_id=connection_id,
            request_method=request_method,
        )
        if result is None or activation is None:
            return sanitized
        binding = activation.binding
        key = (binding.scope.session_id or "", binding.interaction_id)
        prior = self._activations.get(key)
        if prior is not None and prior != activation:
            prior_generation = prior.binding.activation_generation
            candidate_generation = binding.activation_generation
            if candidate_generation < prior_generation:
                raise NativeRuntimeClientError(
                    "NATIVE_RUNTIME_ACTIVATION_STALE",
                    "Native activation response is older than the retained activation",
                )
            if candidate_generation == prior_generation:
                raise NativeRuntimeClientError(
                    "NATIVE_RUNTIME_ACTIVATION_CONFLICT",
                    "Native activation response conflicts with retained authority",
                )
        self._activations[key] = activation
        result[NATIVE_BROWSER_DESCRIPTOR_KEY] = {
            "contract_version": NATIVE_INTERACTION_CONTRACT_VERSION,
            "engine": "openai-realtime-native",
            "model": self._native_model,
        }
        return sanitized

    async def propose(
        self,
        *,
        binding: NativeInteractionBinding,
        capability: str,
        event: NativeEngineEvent,
        request_id: str,
    ) -> dict[str, object]:
        retained = self._authorize(binding, capability)
        proposal = NativeInteractionProposal.from_engine_event(binding, event)
        return await self._request(
            method=ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_PROPOSE,
            binding=binding,
            capability=retained.capability,
            request_id=request_id,
            extra={"proposal": proposal.to_dict()},
            timeout_seconds=(
                _MAX_REQUEST_SECONDS
                if event.delegate is not None
                else self._timeout_seconds
            ),
        )

    async def presentation_ack(
        self,
        *,
        binding: NativeInteractionBinding,
        capability: str,
        request_id: str,
        ack: PresentationAck | None = None,
        cursor: NativePresentationCursor | None = None,
        fence_response: ResponseRef | None = None,
        action_id: str | None = None,
    ) -> dict[str, object]:
        retained = self._authorize(binding, capability)
        if sum(value is not None for value in (ack, cursor, fence_response)) != 1 or (
            ack is not None and action_id is not None
        ):
            raise NativeRuntimeClientError(
                "NATIVE_PRESENTATION_ACK_INVALID",
                "Native presentation requires one ACK, played cursor, or response fence",
            )
        if (cursor is not None or fence_response is not None) and (
            type(action_id) is not str
            or not action_id
            or action_id != action_id.strip()
        ):
            raise NativeRuntimeClientError(
                "NATIVE_PRESENTATION_ACK_INVALID",
                "played cursor or response fence requires a canonical action identity",
            )
        if fence_response is not None and not isinstance(fence_response, ResponseRef):
            raise NativeRuntimeClientError(
                "NATIVE_PRESENTATION_ACK_INVALID",
                "response fence requires an exact ResponseRef",
            )
        encoded_ack = None
        if ack is not None:
            encoded_ack = {
                "response": {
                    "interaction_id": ack.ref.interaction_id,
                    "response_id": ack.ref.response_id,
                    "response_generation": ack.ref.response_generation,
                },
                "surface": ack.surface.value,
                "unit_id": ack.unit_id,
                "contiguous_cursor": ack.contiguous_cursor,
                "presented_at": ack.presented_at,
            }
        return await self._request(
            method=ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_PRESENTATION_ACK,
            binding=binding,
            capability=retained.capability,
            request_id=request_id,
            extra={
                "ack": encoded_ack,
                "cursor": (
                    cursor.to_dict()
                    if cursor is not None
                    else (
                        None
                        if fence_response is None
                        else {
                            "response": {
                                "interaction_id": fence_response.interaction_id,
                                "response_id": fence_response.response_id,
                                "response_generation": fence_response.response_generation,
                            },
                            "fence_only": True,
                        }
                    )
                ),
                "action_id": action_id,
            },
        )

    async def close(
        self,
        *,
        binding: NativeInteractionBinding,
        capability: str,
        request_id: str,
        disposition: str = "closed",
    ) -> dict[str, object]:
        retained = self._authorize(binding, capability)
        if type(disposition) is not str or disposition not in {
            "closed",
            "activation_aborted",
        }:
            raise NativeRuntimeClientError(
                "NATIVE_CLOSE_DISPOSITION_INVALID",
                "Native close disposition is outside the closed contract",
            )
        result = await self._request(
            method=ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_CLOSE,
            binding=binding,
            capability=retained.capability,
            request_id=request_id,
            extra=(
                {}
                if disposition == "closed"
                else {"disposition": "activation_aborted"}
            ),
        )
        key = (binding.scope.session_id or "", binding.interaction_id)
        if self._activations.get(key) == retained:
            self._activations.pop(key, None)
        return result

    async def abort_activation_response(
        self,
        payload: dict[str, object],
        *,
        routed_session_id: str | None,
        connection_id: str | None,
        request_method: str | None,
        request_id: str,
    ) -> dict[str, object]:
        """Compensate one exact private activation that cannot reach Browser."""

        _sanitized, _result, candidate = self._decode_activation_response(
            payload,
            routed_session_id=routed_session_id,
            connection_id=connection_id,
            request_method=request_method,
        )
        if candidate is None:
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_ACTIVATION_INVALID",
                "Native activation compensation requires an exact private descriptor",
            )
        close_result = await self._request(
            method=ReqMethod.LIVE_VOICE_INTERNAL_NATIVE_CLOSE,
            binding=candidate.binding,
            capability=candidate.capability,
            request_id=request_id,
            extra={"disposition": "activation_aborted"},
        )
        key = (
            candidate.binding.scope.session_id or "",
            candidate.binding.interaction_id,
        )
        if self._activations.get(key) == candidate:
            self._activations.pop(key, None)
        return close_result

    def forget_connection(self, connection_id: str) -> int:
        """Drop process-private capabilities when one Gateway socket closes."""

        if type(connection_id) is not str or not connection_id:
            return 0
        keys = tuple(
            key
            for key, activation in self._activations.items()
            if activation.connection_id == connection_id
        )
        for key in keys:
            self._activations.pop(key, None)
        return len(keys)

    def activation_for(
        self,
        *,
        session_id: str,
        interaction_id: str,
        connection_id: str,
    ) -> GatewayNativeActivation | None:
        """Resolve one exact retained capability without exposing it to Browser."""

        if not all(
            _canonical_result_identity(value)
            for value in (session_id, interaction_id, connection_id)
        ):
            return None
        retained = self._activations.get((session_id, interaction_id))
        if retained is None or retained.connection_id != connection_id:
            return None
        return retained

    def browser_descriptor_for(
        self,
        *,
        session_id: str,
        interaction_id: str,
        connection_id: str,
    ) -> dict[str, str] | None:
        """Project the credential-free descriptor for one exact live activation."""

        if (
            self.activation_for(
                session_id=session_id,
                interaction_id=interaction_id,
                connection_id=connection_id,
            )
            is None
        ):
            return None
        return {
            "contract_version": NATIVE_INTERACTION_CONTRACT_VERSION,
            "engine": "openai-realtime-native",
            "model": self._native_model,
        }

    def snapshot(self) -> GatewayNativeRuntimeClientSnapshot:
        return GatewayNativeRuntimeClientSnapshot(
            activation_count=len(self._activations),
            completed_requests=self._completed_requests,
        )

    def _authorize(
        self, binding: NativeInteractionBinding, capability: str
    ) -> GatewayNativeActivation:
        if not isinstance(binding, NativeInteractionBinding):
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_BINDING_INVALID", "binding is not canonical"
            )
        key = (binding.scope.session_id or "", binding.interaction_id)
        retained = self._activations.get(key)
        if (
            retained is None
            or retained.binding != binding
            or type(capability) is not str
            or not hmac.compare_digest(retained.capability, capability)
        ):
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_CAPABILITY_REJECTED",
                "Native Runtime capability did not match the current activation",
            )
        return retained

    async def _request(
        self,
        *,
        method: ReqMethod,
        binding: NativeInteractionBinding,
        capability: str,
        request_id: str,
        extra: dict[str, object],
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        request_id = _request_identity(request_id)
        params: dict[str, object] = {
            "contract_version": NATIVE_INTERACTION_CONTRACT_VERSION,
            "binding": binding.to_dict(),
            "capability": capability,
            **extra,
        }
        envelope = e2a_from_agent_fields(
            request_id=request_id,
            channel_id=NATIVE_GATEWAY_CHANNEL,
            session_id=binding.scope.session_id,
            req_method=method,
            params=params,
            is_stream=False,
        )
        try:
            response = await asyncio.wait_for(
                self._agent.send_request(envelope),
                timeout=(
                    self._timeout_seconds
                    if timeout_seconds is None
                    else timeout_seconds
                ),
            )
        except TimeoutError:
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_TIMEOUT", "AgentServer Native Runtime timed out"
            ) from None
        except Exception as error:
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_UNAVAILABLE", "AgentServer Native Runtime failed"
            ) from error
        result = self._validate_response(response, request_id, method)
        self._completed_requests += 1
        return result

    @staticmethod
    def _validate_response(
        response: object, request_id: str, method: ReqMethod
    ) -> dict[str, object]:
        if (
            not isinstance(response, AgentResponse)
            or response.request_id != request_id
            or response.channel_id != NATIVE_GATEWAY_CHANNEL
            or not isinstance(response.payload, dict)
            or set(response.payload) != {"request_id", "ok", "result", "error"}
            or response.payload.get("request_id") != request_id
        ):
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_RESPONSE_INVALID",
                "AgentServer Native response is not canonical",
            )
        if response.ok is not True or response.payload.get("ok") is not True:
            error = response.payload.get("error")
            reason_value = error.get("reason") if isinstance(error, dict) else None
            reason = (
                reason_value
                if isinstance(reason_value, str)
                else "NATIVE_RUNTIME_REJECTED"
            )
            raise NativeRuntimeClientError(
                reason, "AgentServer rejected Native request"
            )
        result = response.payload.get("result")
        if response.payload.get("error") is not None or not isinstance(result, dict):
            raise NativeRuntimeClientError(
                "NATIVE_RUNTIME_RESPONSE_INVALID",
                "AgentServer Native success result is not canonical",
            )
        return _validate_method_result(method, result)


__all__ = [
    "GatewayNativeActivation",
    "NATIVE_GATEWAY_CHANNEL",
    "NATIVE_GATEWAY_DESCRIPTOR_KEY",
    "NATIVE_BROWSER_DESCRIPTOR_KEY",
    "NATIVE_INTERNAL_REQ_METHODS",
    "GatewayNativeInteractionRuntimeClient",
    "GatewayNativeRuntimeClientSnapshot",
    "NativeRuntimeClientError",
]
