# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.interaction_engine import InteractionAction
from jiuwenswarm.server.live_voice.native_interaction_carrier import (
    NativeCarrierViolation,
    NativeInteractionProposal,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NATIVE_INTERACTION_CONTRACT_VERSION,
    NativeInteractionBinding,
    NativeTurnCommit,
)
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
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


def test_native_proposal_rejects_unknown_fields_and_raw_audio() -> None:
    payload = NativeInteractionProposal.from_engine_event(BINDING, event()).to_dict()
    payload["unknown"] = True
    with pytest.raises(NativeCarrierViolation) as unknown:
        NativeInteractionProposal.from_dict(payload)
    assert unknown.value.reason == "NATIVE_PROPOSAL_FIELDS_NOT_CLOSED"

    audio_event = NativeEngineEvent(audio=object())  # type: ignore[arg-type]
    with pytest.raises(NativeCarrierViolation) as audio:
        NativeInteractionProposal.from_engine_event(BINDING, audio_event)
    assert audio.value.reason == "NATIVE_RAW_AUDIO_FORBIDDEN"


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
