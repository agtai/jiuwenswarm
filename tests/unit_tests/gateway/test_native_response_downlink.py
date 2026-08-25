# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAudioFrame,
    MediaTransportViolation,
)
from jiuwenswarm.gateway.live_voice.native_response_downlink import (
    NativeDownlinkPresentationUnit,
    NativeResponseDownlinkSource,
)


def _unit(response: ResponseRef, sequence: int, pcm16: bytes) -> NativeDownlinkPresentationUnit:
    return NativeDownlinkPresentationUnit(
        response=response,
        unit_id=f"native-unit-{sequence}",
        unit_seq=sequence,
        provider_item_id="provider-item-1",
        content_index=0,
        source_start_sample=sequence * 480,
        source_end_sample=(sequence + 1) * 480,
        content_sha256=hashlib.sha256(pcm16).hexdigest(),
    )


@pytest.mark.asyncio
async def test_three_second_native_response_is_one_bounded_contiguous_source() -> None:
    response = ResponseRef("interaction-1", "response-1", 1)
    source = NativeResponseDownlinkSource(
        response=response,
        sample_rate_hz=48_000,
        capacity=8,
        max_frames=150,
    )
    observed: list[MediaAudioFrame] = []

    async def produce() -> None:
        for sequence in range(150):
            pcm16 = sequence.to_bytes(2, "little") * 480
            await source.append(
                MediaAudioFrame(
                    seq=sequence,
                    sample_cursor=sequence * 960,
                    samples=(sequence / 150.0,) * 960,
                ),
                _unit(response, sequence, pcm16),
                pcm16=pcm16,
            )
        await source.seal(response)

    async def consume() -> None:
        async for frame in source:
            observed.append(frame)

    await asyncio.gather(produce(), consume())

    assert [frame.seq for frame in observed] == list(range(150))
    assert [frame.sample_cursor for frame in observed] == [
        sequence * 960 for sequence in range(150)
    ]
    assert source.appended_frames == 150
    assert source.emitted_frames == 150
    assert source.completed is True
    assert source.buffered_frames == 0
    assert 0 < source.peak_buffered_frames <= 8
    assert source.unit_for_media_sequence(149) == _unit(
        response, 149, (149).to_bytes(2, "little") * 480
    )
    expected_digest = hashlib.sha256(
        b"".join(sequence.to_bytes(2, "little") * 480 for sequence in range(150))
    ).hexdigest()
    assert source.content_sha256 == expected_digest


@pytest.mark.asyncio
async def test_native_source_close_unblocks_producer_and_changed_scope_is_zero_effect() -> None:
    response = ResponseRef("interaction-1", "response-1", 1)
    source = NativeResponseDownlinkSource(
        response=response,
        sample_rate_hz=24_000,
        capacity=1,
        max_frames=4,
    )
    pcm16 = b"\x01\x00" * 480
    await source.append(
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.0,) * 480),
        _unit(response, 0, pcm16),
        pcm16=pcm16,
    )
    blocked = asyncio.create_task(
        source.append(
            MediaAudioFrame(seq=1, sample_cursor=480, samples=(0.0,) * 480),
            _unit(response, 1, pcm16),
            pcm16=pcm16,
        )
    )
    await asyncio.sleep(0)
    assert blocked.done() is False

    await source.aclose()

    with pytest.raises(MediaTransportViolation, match="closed"):
        await blocked
    assert source.appended_frames == 1
    assert source.emitted_frames == 0
    assert source.buffered_frames == 0
    before = source.content_sha256
    with pytest.raises(MediaTransportViolation, match="response"):
        await source.seal(ResponseRef("foreign-interaction", "response-1", 1))
    assert source.content_sha256 == before
