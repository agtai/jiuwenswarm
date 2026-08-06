# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Gateway-local RPC surface for formal SR-B/SS-B batch speech."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance
from jiuwenswarm.server.live_voice.batch_speech import (
    FormalBatchSpeechService,
    SpeechRpcContext,
    create_environment_batch_speech_provider,
)


CAPABILITIES_METHOD = "live_voice.speech.capabilities"
RECOGNIZE_BATCH_METHOD = "live_voice.speech.recognize_batch"
SYNTHESIZE_BATCH_METHOD = "live_voice.speech.synthesize_batch"
CANCEL_METHOD = "live_voice.speech.cancel"


def register_speech_rpc_handlers(
    channel: Any,
    *,
    service: FormalBatchSpeechService | None = None,
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
        operation: Callable[[object, SpeechRpcContext], Awaitable[dict[str, object]]],
    ) -> Callable[..., Awaitable[None]]:
        async def handler(
            ws: Any,
            req_id: str,
            params: object,
            session_id: str,
            user_id: str | None = None,
        ) -> None:
            subject_id = str(user_id).strip() if user_id is not None else ""
            context = SpeechRpcContext(
                subject_id=subject_id or None,
                session_id=str(session_id),
                assurance=Assurance.REQUEST_ASSERTED,
            )
            result = await operation(params, context)
            # Contract failures stay in the v2 result envelope. Transport success
            # only means the Gateway processed this package-local request.
            await channel.send_response(ws, req_id, ok=True, payload=result)

        return handler

    channel.register_method(CAPABILITIES_METHOD, capabilities_handler)
    channel.register_method(
        RECOGNIZE_BATCH_METHOD, operation_handler(speech_service.recognize)
    )
    channel.register_method(
        SYNTHESIZE_BATCH_METHOD, operation_handler(speech_service.synthesize)
    )
    channel.register_method(CANCEL_METHOD, operation_handler(speech_service.cancel))
    return speech_service
