from __future__ import annotations

import asyncio
import json
import time

from jiuwenswarm.common.schema.message import Message, ReqMethod
from jiuwenswarm.gateway.app_gateway import _inject_live_voice_gateway_voice_claim
from jiuwenswarm.server.live_voice.batch_speech import (
    BatchSpeechProvider,
    FormalBatchSpeechService,
    ProviderRecognitionRequest,
    ProviderSynthesisRequest,
    create_environment_batch_speech_provider,
)
from jiuwenswarm.server.live_voice.critical_token_safety import CriticalTokenPolicy


PROBE_TEXT = "请介绍巴黎五个地方，每一项都简要回答。"
RESULT_PREFIX = "FORMAL_WEB_RUNTIME_PROBE_RESULT "


async def run_probe(provider: BatchSpeechProvider) -> dict[str, object]:
    capability = provider.capability()
    if not (
        capability.available
        and capability.recognition_batch
        and capability.synthesis_batch
    ):
        raise RuntimeError("formal batch Speech Provider is unavailable")

    synthesized = await provider.synthesize(
        ProviderSynthesisRequest(
            "formal-web-runtime-tts",
            PROBE_TEXT,
            "zh-CN",
            None,
            24_000,
        )
    )
    recognized = await provider.recognize(
        ProviderRecognitionRequest(
            "formal-web-runtime-stt",
            synthesized.audio_wav,
            "zh-CN",
        )
    )
    critical_tokens = CriticalTokenPolicy().scan(recognized.text)
    if not critical_tokens:
        raise RuntimeError("real Speech round trip lost the critical-token fixture")

    service = FormalBatchSpeechService(provider)
    receipt = await service.issue_streaming_voice_commit_receipt(
        operation_id="formal-web-runtime-stt",
        capture_id="formal-web-runtime-capture",
        capture_generation=1,
        session_id="formal-web-runtime-session",
        correlation_id="formal-web-runtime-correlation",
        interaction_id="formal-web-runtime-interaction",
        text=recognized.text,
    )
    message = Message(
        id="formal-web-runtime-submit",
        type="req",
        channel_id="web",
        session_id="formal-web-runtime-session",
        params={
            "session_id": "formal-web-runtime-session",
            "correlation_id": "formal-web-runtime-correlation",
            "interaction_id": "formal-web-runtime-interaction",
            "turn_id": "formal-web-runtime-turn",
            "commit_id": "formal-web-runtime-commit",
            "text": recognized.text,
            "voice_commit_receipt": receipt,
        },
        timestamp=time.time(),
        ok=True,
        req_method=ReqMethod.LIVE_VOICE_COMPOSITION_UNIFIED_SUBMIT,
    )
    await _inject_live_voice_gateway_voice_claim(message, service)
    claim = message.params.get("gateway_voice_claim")
    if not isinstance(claim, dict):
        raise RuntimeError("Gateway did not produce a formal speech claim")
    if claim.get("kind") != "formal_speech_recognition":
        raise RuntimeError("Gateway speech claim is not formal")
    if claim.get("critical_policy") != "eligible":
        raise RuntimeError(
            "formal Speech receipt incorrectly required a special policy"
        )
    if "voice_commit_receipt" in message.params:
        raise RuntimeError("Gateway forwarded a private speech receipt")

    forged = Message(
        id="formal-web-runtime-forged",
        type="req",
        channel_id="web",
        session_id="formal-web-runtime-session",
        params={
            "session_id": "formal-web-runtime-session",
            "correlation_id": "formal-web-runtime-correlation",
            "interaction_id": "formal-web-runtime-interaction",
            "turn_id": "formal-web-runtime-forged-turn",
            "commit_id": "formal-web-runtime-forged-commit",
            "text": recognized.text,
            "gateway_voice_claim": {"kind": "client-forged"},
        },
        timestamp=time.time(),
        ok=True,
        req_method=ReqMethod.LIVE_VOICE_COMPOSITION_UNIFIED_SUBMIT,
    )
    await _inject_live_voice_gateway_voice_claim(forged, service)
    if "gateway_voice_claim" in forged.params:
        raise RuntimeError("Gateway retained a client-forged speech claim")

    mismatch_receipt = await service.issue_streaming_voice_commit_receipt(
        operation_id="formal-web-runtime-mismatch-stt",
        capture_id="formal-web-runtime-mismatch-capture",
        capture_generation=2,
        session_id="formal-web-runtime-session",
        correlation_id="formal-web-runtime-correlation",
        interaction_id="formal-web-runtime-interaction",
        text=recognized.text,
    )
    mismatch_rejected = False
    try:
        await service.claim_voice_commit_receipt(
            receipt=mismatch_receipt,
            session_id="formal-web-runtime-session",
            correlation_id="formal-web-runtime-correlation",
            interaction_id="formal-web-runtime-interaction",
            turn_id="formal-web-runtime-mismatch-turn",
            commit_id="formal-web-runtime-mismatch-commit",
            text=f"{recognized.text}x",
            critical_confirmation=None,
        )
    except ValueError:
        mismatch_rejected = True
    if not mismatch_rejected:
        raise RuntimeError("speech receipt accepted changed recognized text")

    return {
        "provider_round_trip": "passed",
        "recognized_character_count": len(recognized.text),
        "critical_token_count": len(critical_tokens),
        "gateway_claim_policy": "eligible",
        "identity_mismatch": "rejected",
        "forged_claim": "rejected",
        "business_effects": 0,
        "audio_retained": False,
        "transcript_retained": False,
    }


async def _main() -> int:
    try:
        result = await run_probe(create_environment_batch_speech_provider())
    except Exception:
        # Provider and transcript details are machine-private. The controlled
        # launcher reports only this stable failure and keeps the service out of
        # the ready state.
        return 1
    print(RESULT_PREFIX + json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
