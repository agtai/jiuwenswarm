# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Gateway-local RPC surface for formal SR-B/SS-B batch speech."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance
from jiuwenswarm.server.live_voice.batch_speech import (
    FormalBatchSpeechService,
    RECOGNIZE_OPERATION,
    SpeechRpcContext,
    SYNTHESIZE_OPERATION,
    create_environment_batch_speech_provider,
)


CAPABILITIES_METHOD = "live_voice.speech.capabilities"
RECOGNIZE_BATCH_METHOD = "live_voice.speech.recognize_batch"
SYNTHESIZE_BATCH_METHOD = "live_voice.speech.synthesize_batch"
CANCEL_METHOD = "live_voice.speech.cancel"
logger = logging.getLogger(__name__)


def register_speech_rpc_handlers(
    channel: Any,
    *,
    service: FormalBatchSpeechService | None = None,
    context_factory: Callable[[Any, object, str, str | None], SpeechRpcContext]
    | None = None,
    evidence_observer: Any | None = None,
    evidence_binding_factory: Callable[[object, str], dict[str, object] | None]
    | None = None,
    result_transform: Callable[
        [str, object, SpeechRpcContext, dict[str, object], str], dict[str, object]
    ]
    | None = None,
) -> FormalBatchSpeechService:
    """Register the package-local methods without composing a Web product route."""

    speech_service = service or FormalBatchSpeechService(
        create_environment_batch_speech_provider()
    )

    async def capabilities_handler(
        ws: Any,
        req_id: str,
        params: object,
        session_id: str,
        user_id: str | None = None,
    ) -> None:
        del params, session_id, user_id
        await channel.send_response(
            ws, req_id, ok=True, payload=speech_service.capability_payload()
        )

    def operation_handler(
        operation_name: str,
        operation: Callable[[object, SpeechRpcContext], Awaitable[dict[str, object]]],
    ) -> Callable[..., Awaitable[None]]:
        async def handler(
            ws: Any,
            req_id: str,
            params: object,
            session_id: str,
            user_id: str | None = None,
        ) -> None:
            if context_factory is None:
                subject_id = str(user_id).strip() if user_id is not None else ""
                context = SpeechRpcContext(
                    subject_id=subject_id or None,
                    session_id=str(session_id),
                    assurance=Assurance.REQUEST_ASSERTED,
                )
            else:
                context = context_factory(ws, params, str(session_id), user_id)
                if not isinstance(context, SpeechRpcContext):
                    raise TypeError("speech context factory returned no typed context")
            result = await operation(params, context)
            if result_transform is not None:
                try:
                    transformed_result = result_transform(
                        operation_name,
                        params,
                        context,
                        result,
                        str(session_id),
                    )
                    if not isinstance(transformed_result, dict):
                        raise TypeError("speech result transform returned no mapping")
                    result = transformed_result
                except Exception as exc:  # noqa: BLE001 -- fail product media closed
                    reason = str(getattr(exc, "reason_id", "MEDIA_DOWNLINK_UNAVAILABLE"))
                    correlation_id = (
                        params.get("correlation_id")
                        if isinstance(params, dict)
                        and isinstance(params.get("correlation_id"), str)
                        else None
                    )
                    result = {
                        **result,
                        "ok": False,
                        "result": None,
                        "error": {
                            "code": "CAPABILITY_UNAVAILABLE",
                            "reason": reason,
                            "message": "formal media downlink is unavailable",
                            "retriable": False,
                            "correlation_id": correlation_id,
                            "details": {},
                        },
                    }
            if evidence_observer is not None and evidence_binding_factory is not None:
                evidence_binding = evidence_binding_factory(params, str(session_id))
                if evidence_binding is not None:
                    error = result.get("error")
                    error_code = (
                        error.get("code")
                        if isinstance(error, dict)
                        and isinstance(error.get("code"), str)
                        else None
                    )
                    try:
                        await evidence_observer.observe_route(
                            session_id=str(session_id),
                            correlation_id=str(evidence_binding["correlation_id"]),
                            request_id=req_id,
                            operation=operation_name,
                            result_ok=result.get("ok") is True,
                            interaction_id=evidence_binding.get("interaction_id"),
                            response_id=evidence_binding.get("response_id"),
                            response_generation=(
                                evidence_binding["response_generation"]
                                if type(evidence_binding.get("response_generation"))
                                is int
                                else None
                            ),
                            error_code=error_code,
                        )
                    except Exception as exc:  # noqa: BLE001 -- diagnostic only
                        logger.warning(
                            "W2 Speech evidence observation rejected: %s", exc
                        )
            # Contract failures stay in the v2 result envelope. Transport success
            # only means the Gateway processed this package-local request.
            await channel.send_response(ws, req_id, ok=True, payload=result)

        return handler

    channel.register_method(CAPABILITIES_METHOD, capabilities_handler)
    channel.register_method(
        RECOGNIZE_BATCH_METHOD,
        operation_handler(RECOGNIZE_OPERATION, speech_service.recognize),
    )
    channel.register_method(
        SYNTHESIZE_BATCH_METHOD,
        operation_handler(SYNTHESIZE_OPERATION, speech_service.synthesize),
    )
    channel.register_method(
        CANCEL_METHOD,
        operation_handler("speech.batch.cancel", speech_service.cancel),
    )
    return speech_service
