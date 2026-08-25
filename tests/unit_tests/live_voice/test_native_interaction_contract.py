# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ErrorCode,
    ResponseRef,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NATIVE_INTERACTION_CONTRACT_VERSION,
    NativeAudioObservation,
    NativeContractLedger,
    NativeDelegateProposal,
    NativeInteractionBinding,
    NativeInteractionContractViolation,
    NativePresentationCursor,
    NativeTurnCommit,
)


_SCOPE = ScopeRef("subject", "project", "session", Assurance.AUTHENTICATED)


def _binding_payload() -> dict[str, object]:
    return {
        "scope": _SCOPE.to_dict(),
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 7,
        "correlation_id": "correlation-1",
    }


def _commit_payload(*, audit_transcript: str | None = "hello") -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_version": NATIVE_INTERACTION_CONTRACT_VERSION,
        "commit_id": "native-commit-1",
        "binding": _binding_payload(),
        "turn_id": "turn-1",
        "provider_session_id": "provider-session-1",
        "provider_item_id": "provider-item-1",
        "provider_event_id": "provider-event-1",
        "causation_id": "provider-event-0",
        "input_audio_start_ms": 120,
        "input_audio_end_ms": 760,
        "committed_audio_ms": 640,
        "audit_transcript": audit_transcript,
        "audit_transcript_event_id": (
            None if audit_transcript is None else "provider-transcript-event-1"
        ),
    }
    return payload


def _delegate_payload() -> dict[str, object]:
    return {
        "contract_version": NATIVE_INTERACTION_CONTRACT_VERSION,
        "binding": _binding_payload(),
        "turn_id": "turn-1",
        "response_generation": 9,
        "provider_event_id": "provider-event-9",
        "provider_call_id": "provider-call-1",
        "provider_item_id": "provider-item-9",
        "request_text": "Create a background task",
    }


def _audio_observation_payload() -> dict[str, object]:
    return {
        "provider_event_id": "provider-audio-event-1",
        "provider_response_id": "provider-response-1",
        "provider_item_id": "provider-assistant-item-1",
        "content_index": 0,
        "sequence": 3,
        "sample_count": 480,
        "content_sha256": "a" * 64,
        "response": {
            "interaction_id": "interaction-1",
            "response_id": "native-response-1",
            "response_generation": 7,
        },
    }


def test_native_audio_observation_is_closed_metadata_only() -> None:
    observation = NativeAudioObservation.from_dict(_audio_observation_payload())

    assert observation.to_dict() == _audio_observation_payload()
    assert observation.sample_count == 480
    assert observation.content_sha256 == "a" * 64
    assert not any(
        name in observation.to_dict() for name in ("pcm16", "audio", "bytes", "base64")
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("sample_count", 0, "NATIVE_AUDIO_SAMPLE_COUNT_INVALID"),
        ("sample_count", 48_001, "NATIVE_AUDIO_SAMPLE_COUNT_INVALID"),
        ("content_sha256", "A" * 64, "NATIVE_AUDIO_DIGEST_INVALID"),
        ("content_sha256", "a" * 63, "NATIVE_AUDIO_DIGEST_INVALID"),
    ],
)
def test_native_audio_observation_rejects_noncanonical_metadata(
    field: str, value: object, reason: str
) -> None:
    payload = _audio_observation_payload()
    payload[field] = value

    with pytest.raises(NativeInteractionContractViolation) as raised:
        NativeAudioObservation.from_dict(payload)

    assert raised.value.reason == reason


def test_native_turn_commit_allows_audio_authority_without_transcript() -> None:
    commit = NativeTurnCommit.from_dict(_commit_payload(audit_transcript=None))

    assert commit.contract_version == NATIVE_INTERACTION_CONTRACT_VERSION
    assert commit.audit_transcript is None
    assert commit.audit_transcript_event_id is None
    assert commit.committed_audio_ms == 640
    assert commit.to_dict() == _commit_payload(audit_transcript=None)


def test_native_binding_round_trips_exact_canonical_scope() -> None:
    binding = NativeInteractionBinding.from_dict(_binding_payload())

    assert binding.scope == _SCOPE
    assert binding.to_dict() == _binding_payload()


def test_native_delegate_round_trips_and_function_call_parser_is_closed() -> None:
    expected = NativeDelegateProposal.from_dict(_delegate_payload())
    parsed = NativeDelegateProposal.from_function_call(
        binding=expected.binding,
        turn_id=expected.turn_id,
        response_generation=expected.response_generation,
        provider_event_id=expected.provider_event_id,
        provider_call_id=expected.provider_call_id,
        provider_item_id=expected.provider_item_id,
        arguments='{"request_text":"Create a background task"}',
    )

    assert parsed == expected
    assert parsed.to_dict() == _delegate_payload()


def test_delegate_rejects_unknown_arguments_before_any_ledger_effect() -> None:
    ledger = NativeContractLedger(capacity=4)

    with pytest.raises(NativeInteractionContractViolation) as raised:
        NativeDelegateProposal.from_function_call(
            binding=NativeInteractionBinding.from_dict(_binding_payload()),
            turn_id="turn-1",
            response_generation=9,
            provider_event_id="provider-event-9",
            provider_call_id="provider-call-1",
            provider_item_id="provider-item-9",
            arguments='{"request_text":"create a task","tool":"shell"}',
        )

    assert raised.value.reason == "NATIVE_DELEGATE_ARGUMENTS_NOT_CLOSED"
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT
    assert ledger.accepted_count == 0


def test_delegate_rejects_duplicate_json_keys() -> None:
    with pytest.raises(NativeInteractionContractViolation) as raised:
        NativeDelegateProposal.from_function_call(
            binding=NativeInteractionBinding.from_dict(_binding_payload()),
            turn_id="turn-1",
            response_generation=9,
            provider_event_id="provider-event-9",
            provider_call_id="provider-call-1",
            provider_item_id="provider-item-9",
            arguments='{"request_text":"first","request_text":"second"}',
        )

    assert raised.value.reason == "NATIVE_DELEGATE_ARGUMENTS_INVALID"


def test_commit_and_delegate_exact_replay_are_idempotent() -> None:
    ledger = NativeContractLedger(capacity=4)
    commit = NativeTurnCommit.from_dict(_commit_payload())
    delegate = NativeDelegateProposal.from_dict(_delegate_payload())

    assert ledger.accept_commit(commit) == (True, commit)
    assert ledger.accept_commit(commit) == (False, commit)
    assert ledger.accept_delegate(delegate) == (True, delegate)
    assert ledger.accept_delegate(delegate) == (False, delegate)
    assert ledger.accepted_count == 2


@pytest.mark.parametrize(
    "changed",
    [
        replace(
            NativeTurnCommit.from_dict(_commit_payload()),
            provider_event_id="provider-event-changed",
        ),
        replace(
            NativeTurnCommit.from_dict(_commit_payload()),
            turn_id="turn-changed",
        ),
        replace(
            NativeTurnCommit.from_dict(_commit_payload()),
            binding=replace(
                NativeInteractionBinding.from_dict(_binding_payload()),
                interaction_id="interaction-changed",
            ),
        ),
    ],
)
def test_native_turn_commit_rejects_changed_replay_binding(
    changed: NativeTurnCommit,
) -> None:
    ledger = NativeContractLedger(capacity=4)
    accepted = NativeTurnCommit.from_dict(_commit_payload())
    ledger.accept_commit(accepted)

    with pytest.raises(NativeInteractionContractViolation) as raised:
        ledger.accept_commit(changed)

    assert raised.value.reason == "NATIVE_COMMIT_ID_CONFLICT"
    assert ledger.accepted_count == 1


def test_delegate_call_id_cannot_change_request_or_generation() -> None:
    ledger = NativeContractLedger(capacity=4)
    accepted = NativeDelegateProposal.from_dict(_delegate_payload())
    ledger.accept_delegate(accepted)

    with pytest.raises(NativeInteractionContractViolation) as raised:
        ledger.accept_delegate(
            replace(
                accepted,
                request_text="changed",
                response_generation=10,
            )
        )

    assert raised.value.reason == "NATIVE_DELEGATE_CALL_ID_CONFLICT"
    assert ledger.accepted_count == 1


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        (
            "contract_version",
            "live-voice.native-interaction.v2",
            "NATIVE_CONTRACT_VERSION_UNSUPPORTED",
        ),
        ("commit_id", " commit", "NATIVE_IDENTITY_INVALID"),
        ("turn_id", "turn\n1", "NATIVE_IDENTITY_INVALID"),
        ("input_audio_start_ms", -1, "NATIVE_CURSOR_INVALID"),
        ("input_audio_end_ms", 119, "NATIVE_AUDIO_TIMING_INVALID"),
        ("committed_audio_ms", 639, "NATIVE_AUDIO_TIMING_INVALID"),
        ("audit_transcript_event_id", None, "NATIVE_TRANSCRIPT_PROVENANCE_INVALID"),
    ],
)
def test_native_commit_invalid_values_fail_closed(
    field: str, value: object, reason: str
) -> None:
    payload = _commit_payload()
    payload[field] = value

    with pytest.raises(NativeInteractionContractViolation) as raised:
        NativeTurnCommit.from_dict(payload)

    assert raised.value.reason == reason


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("commit_id", "commit\u2028id", "NATIVE_IDENTITY_INVALID"),
        ("audit_transcript", "hello\u0001world", "NATIVE_TRANSCRIPT_INVALID"),
    ],
)
def test_native_commit_rejects_embedded_control_and_line_separator(
    field: str, value: str, reason: str
) -> None:
    payload = _commit_payload()
    payload[field] = value

    with pytest.raises(NativeInteractionContractViolation) as raised:
        NativeTurnCommit.from_dict(payload)

    assert raised.value.reason == reason


@pytest.mark.parametrize("field", ["extra", "missing"])
def test_native_commit_mapping_is_exact_key(field: str) -> None:
    payload = _commit_payload()
    if field == "extra":
        payload["unexpected"] = True
    else:
        payload.pop("provider_item_id")

    with pytest.raises(NativeInteractionContractViolation) as raised:
        NativeTurnCommit.from_dict(payload)

    assert raised.value.reason == "NATIVE_COMMIT_FIELDS_NOT_CLOSED"


def test_native_binding_requires_authenticated_scope() -> None:
    payload = _binding_payload()
    scope = dict(_SCOPE.to_dict())
    scope["assurance"] = "request_asserted"
    payload["scope"] = scope

    with pytest.raises(NativeInteractionContractViolation) as raised:
        NativeInteractionBinding.from_dict(payload)

    assert raised.value.reason == "NATIVE_SCOPE_NOT_AUTHENTICATED"


@pytest.mark.parametrize(
    "request_text",
    ["", " request", "request ", "bad\u0000request", "x" * 16_385],
    ids=["empty", "leading-space", "trailing-space", "control", "oversized"],
)
def test_delegate_request_text_is_nonempty_trimmed_control_free_and_bounded(
    request_text: str,
) -> None:
    payload = _delegate_payload()
    payload["request_text"] = request_text

    with pytest.raises(NativeInteractionContractViolation) as raised:
        NativeDelegateProposal.from_dict(payload)

    assert raised.value.reason == "NATIVE_DELEGATE_REQUEST_INVALID"


def test_invalid_json_function_call_has_zero_ledger_effect() -> None:
    ledger = NativeContractLedger(capacity=1)

    with pytest.raises(NativeInteractionContractViolation) as raised:
        NativeDelegateProposal.from_function_call(
            binding=NativeInteractionBinding.from_dict(_binding_payload()),
            turn_id="turn-1",
            response_generation=9,
            provider_event_id="provider-event-9",
            provider_call_id="provider-call-1",
            provider_item_id="provider-item-9",
            arguments="{",
        )

    assert raised.value.reason == "NATIVE_DELEGATE_ARGUMENTS_INVALID"
    assert ledger.accepted_count == 0


def test_ledger_capacity_fails_before_accepting_another_identity() -> None:
    ledger = NativeContractLedger(capacity=1)
    commit = NativeTurnCommit.from_dict(_commit_payload())
    delegate = NativeDelegateProposal.from_dict(_delegate_payload())
    ledger.accept_commit(commit)

    with pytest.raises(NativeInteractionContractViolation) as raised:
        ledger.accept_delegate(delegate)

    assert raised.value.reason == "NATIVE_CONTRACT_LEDGER_FULL"
    assert ledger.accepted_count == 1


def test_presentation_cursor_round_trips_and_rejects_negative_audio_end() -> None:
    cursor = NativePresentationCursor(
        response=ResponseRef("interaction-1", "response-1", 9),
        provider_item_id="provider-item-1",
        content_index=0,
        audio_end_ms=420,
    )

    assert NativePresentationCursor.from_dict(cursor.to_dict()) == cursor
    invalid = deepcopy(cursor.to_dict())
    invalid["audio_end_ms"] = -1
    with pytest.raises(NativeInteractionContractViolation) as raised:
        NativePresentationCursor.from_dict(invalid)
    assert raised.value.reason == "NATIVE_CURSOR_INVALID"


def test_presentation_cursor_direct_constructor_revalidates_response_ref() -> None:
    with pytest.raises(NativeInteractionContractViolation) as raised:
        NativePresentationCursor(
            response=ResponseRef(
                interaction_id="interaction-1",
                response_id="response-1",
                response_generation=0,
            ),
            provider_item_id="provider-item-1",
            content_index=0,
            audio_end_ms=0,
        )

    assert raised.value.reason == "NATIVE_GENERATION_INVALID"
