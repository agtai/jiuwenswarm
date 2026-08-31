# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ResponseRef,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.interaction_engine import InteractionAction
from jiuwenswarm.server.live_voice.native_interaction_carrier import (
    NativeCarrierViolation,
    NativeInteractionProposal,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NATIVE_INTERACTION_CONTRACT_VERSION,
    NativeInputTranscript,
    NativeInteractionBinding,
    NativeTurnCommit,
)
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    NativeAudioOutput,
    NativeEngineEvent,
)


SCOPE = ScopeRef(
    "subject-native", "project-native", "session-native", Assurance.AUTHENTICATED
)
BINDING = NativeInteractionBinding(
    scope=SCOPE,
    interaction_id="interaction-native",
    activation_id="activation-native",
    activation_generation=1,
    correlation_id="correlation-native",
)


def event() -> NativeEngineEvent:
    commit = NativeTurnCommit(
        contract_version=NATIVE_INTERACTION_CONTRACT_VERSION,
        commit_id="commit-native-1",
        binding=BINDING,
        turn_id="turn-native-1",
        provider_session_id="provider-session-1",
        provider_item_id="provider-item-1",
        provider_event_id="provider-commit-1",
        causation_id="provider-speech-1",
        input_audio_start_ms=0,
        input_audio_end_ms=20,
        committed_audio_ms=20,
    )
    return NativeEngineEvent(
        action=InteractionAction(
            action_id="action-native-1",
            operation="TURN_COMMIT",
            interaction_id=BINDING.interaction_id,
            scope=SCOPE,
            payload=(("turn_id", commit.turn_id),),
        ),
        turn_commit=commit,
    )


def test_native_proposal_round_trips_one_closed_engine_event() -> None:
    proposal = NativeInteractionProposal.from_engine_event(BINDING, event())

    assert NativeInteractionProposal.from_dict(proposal.to_dict()) == proposal
    assert proposal.binding == BINDING
    assert proposal.action is not None
    assert proposal.turn_commit is not None
    assert proposal.delegate is None
    assert proposal.provider_done is None


def test_native_proposal_round_trips_closed_input_transcript_without_audit_authority() -> (
    None
):
    transcript = NativeInputTranscript(
        binding=BINDING,
        turn_id="turn-native-1",
        commit_id="commit-native-1",
        provider_session_id="provider-session-1",
        provider_item_id="provider-item-1",
        provider_event_id="provider-transcript-1",
        transcript="介绍你自己。",
    )

    proposal = NativeInteractionProposal.from_engine_event(
        BINDING, NativeEngineEvent(input_transcript=transcript)
    )
    payload = proposal.to_dict()

    assert NativeInteractionProposal.from_dict(payload) == proposal
    assert proposal.input_transcript == transcript
    assert payload["input_transcript"] == transcript.to_dict()
    assert "audit_transcript" not in json.dumps(payload, sort_keys=True)


def test_native_proposal_rejects_unknown_fields() -> None:
    payload = NativeInteractionProposal.from_engine_event(BINDING, event()).to_dict()
    payload["unknown"] = True
    with pytest.raises(NativeCarrierViolation) as unknown:
        NativeInteractionProposal.from_dict(payload)
    assert unknown.value.reason == "NATIVE_PROPOSAL_FIELDS_NOT_CLOSED"


def test_native_proposal_carries_only_audio_metadata_and_never_pcm() -> None:
    pcm16 = b"\x12\x34" * 480
    response = ResponseRef(BINDING.interaction_id, "native-response-1", 1)
    engine_event = NativeEngineEvent(
        audio=NativeAudioOutput(
            provider_event_id="provider-audio-event-1",
            provider_response_id="provider-response-1",
            provider_item_id="provider-assistant-item-1",
            content_index=0,
            sequence=0,
            pcm16=pcm16,
            response=response,
            provider_sample_count=137,
        )
    )

    proposal = NativeInteractionProposal.from_engine_event(BINDING, engine_event)
    payload = proposal.to_dict()
    encoded = json.dumps(payload, sort_keys=True)

    assert NativeInteractionProposal.from_dict(payload) == proposal
    assert proposal.audio_observation is not None
    assert proposal.audio_observation.sample_count == 137
    assert (
        proposal.audio_observation.content_sha256 == hashlib.sha256(pcm16).hexdigest()
    )
    assert set(payload["audio_observation"]) == {
        "provider_event_id",
        "provider_response_id",
        "provider_item_id",
        "content_index",
        "sequence",
        "sample_count",
        "content_sha256",
        "response",
    }
    assert "pcm16" not in encoded
    assert "EjQ=" not in encoded
    assert pcm16.hex() not in encoded


@pytest.mark.parametrize("sample_count", [0, 481, True])
def test_native_proposal_rejects_provider_samples_outside_emitted_frame(
    sample_count: int,
) -> None:
    response = ResponseRef(BINDING.interaction_id, "native-response-1", 1)
    engine_event = NativeEngineEvent(
        audio=NativeAudioOutput(
            provider_event_id="provider-audio-event-1",
            provider_response_id="provider-response-1",
            provider_item_id="provider-assistant-item-1",
            content_index=0,
            sequence=0,
            pcm16=b"\x12\x34" * 480,
            response=response,
            provider_sample_count=sample_count,
        )
    )

    with pytest.raises(NativeCarrierViolation) as raised:
        NativeInteractionProposal.from_engine_event(BINDING, engine_event)
    assert raised.value.reason == "NATIVE_AUDIO_OBSERVATION_INVALID"


def test_native_proposal_rejects_cross_binding_action_before_runtime() -> None:
    foreign = NativeInteractionBinding(
        scope=SCOPE,
        interaction_id="interaction-foreign",
        activation_id="activation-native",
        activation_generation=1,
        correlation_id="correlation-native",
    )
    with pytest.raises(NativeCarrierViolation) as mismatch:
        NativeInteractionProposal.from_engine_event(foreign, event())
    assert mismatch.value.reason == "NATIVE_PROPOSAL_BINDING_MISMATCH"
