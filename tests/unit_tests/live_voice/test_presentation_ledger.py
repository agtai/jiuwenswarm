# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.presentation_ledger import (
    HistorySurfacePolicy,
    PresentationAck,
    PresentationLedger,
    PresentationLedgerViolation,
    PresentationSurface,
    PresentationUnit,
)


def response() -> ResponseRef:
    return ResponseRef("native-interaction-1", "native-response-1", 1)


def audio_unit(sequence: int) -> PresentationUnit:
    return PresentationUnit(
        ref=response(),
        surface=PresentationSurface.AUDIO,
        unit_id=f"native-audio-{sequence}",
        seq=sequence,
        source_start_utf8=sequence * 4,
        source_end_utf8=(sequence + 1) * 4,
        content_ref=f"sha256:audio-{sequence}",
    )


def audio_ack(sequence: int) -> PresentationAck:
    return PresentationAck(
        ref=response(),
        surface=PresentationSurface.AUDIO,
        unit_id=f"native-audio-{sequence}",
        contiguous_cursor=sequence,
        presented_at=f"2026-08-25T10:00:0{sequence + 1}Z",
    )


def test_native_audio_completes_only_after_sealed_contiguous_ack() -> None:
    ledger = PresentationLedger()
    ledger.begin_response(response(), HistorySurfacePolicy.NATIVE_AUDIO)
    for sequence in range(2):
        unit = audio_unit(sequence)
        assert ledger.produce(unit) is True
        assert ledger.enqueue(response(), unit.surface, unit.unit_id)[0] is True

    assert (
        ledger.seal_surface(response(), PresentationSurface.AUDIO, unit_count=2) is True
    )
    assert ledger.presentation_complete(response(), PresentationSurface.AUDIO) is False
    assert ledger.acknowledge(audio_ack(0))[0] is True
    assert ledger.presentation_complete(response(), PresentationSurface.AUDIO) is False
    assert ledger.acknowledge(audio_ack(1))[0] is True
    assert ledger.presentation_complete(response(), PresentationSurface.AUDIO) is True
    assert (
        ledger.seal_surface(response(), PresentationSurface.AUDIO, unit_count=2)
        is False
    )


def test_native_audio_seal_is_immutable_and_rejects_future_output() -> None:
    ledger = PresentationLedger()
    ledger.begin_response(response(), HistorySurfacePolicy.NATIVE_AUDIO)
    unit = audio_unit(0)
    ledger.produce(unit)
    ledger.enqueue(response(), unit.surface, unit.unit_id)
    ledger.seal_surface(response(), PresentationSurface.AUDIO, unit_count=1)
    before = ledger.snapshot()

    with pytest.raises(PresentationLedgerViolation) as changed:
        ledger.seal_surface(response(), PresentationSurface.AUDIO, unit_count=2)
    assert changed.value.reason == "PRESENTATION_SEAL_CONFLICT"
    with pytest.raises(PresentationLedgerViolation) as future:
        ledger.produce(audio_unit(1))
    assert future.value.reason == "PRESENTATION_SURFACE_SEALED"

    assert ledger.snapshot() == before


def test_existing_history_policies_remain_distinct_from_native_audio() -> None:
    assert HistorySurfacePolicy.NATIVE_AUDIO not in {
        HistorySurfacePolicy.TEXT,
        HistorySurfacePolicy.AUDIO,
        HistorySurfacePolicy.UNION,
    }
