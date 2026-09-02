from __future__ import annotations

import pytest

from jiuwenswarm.server.live_voice.authoritative_final_chunking import (
    AuthoritativeFinalChunkingViolation,
    chunk_authoritative_final_tail,
)


def _chunk(final_text: str, prefix: str = "Prefix. "):
    assert final_text.startswith(prefix)
    return chunk_authoritative_final_tail(
        final_text,
        spoken_prefix_end_utf8=len(prefix.encode("utf-8")),
    )


def _assert_exact(final_text: str, prefix: str, chunks: tuple[object, ...]) -> None:
    encoded = final_text.encode("utf-8")
    prefix_end = len(prefix.encode("utf-8"))
    assert b"".join(chunk.content for chunk in chunks) == encoded[prefix_end:]
    assert chunks[0].source_start_utf8 == prefix_end
    assert chunks[-1].source_end_utf8 == len(encoded)
    assert [chunk.seq for chunk in chunks] == list(range(1, len(chunks) + 1))
    for left, right in zip(chunks, chunks[1:], strict=False):
        assert left.source_end_utf8 == right.source_start_utf8


def test_threshold_requires_six_hundred_tail_bytes_and_two_safe_units() -> None:
    prefix = "Prefix. "
    below_tail = f"{'A' * 297}. {'B' * 299}."
    eligible_tail = f"{'A' * 298}. {'B' * 299}."
    assert len(below_tail.encode()) == 599
    assert len(eligible_tail.encode()) == 600

    below = _chunk(prefix + below_tail, prefix)
    eligible = _chunk(prefix + eligible_tail, prefix)

    assert len(below) == 1
    assert len(eligible) == 2
    _assert_exact(prefix + below_tail, prefix, below)
    _assert_exact(prefix + eligible_tail, prefix, eligible)


def test_five_safe_units_are_coalesced_into_at_most_four_balanced_chunks() -> None:
    prefix = "Prefix. "
    units = tuple(f"Point {index}: {'x' * 145}. " for index in range(1, 6))
    final_text = prefix + "".join(units)

    chunks = _chunk(final_text, prefix)

    assert 2 <= len(chunks) <= 4
    _assert_exact(final_text, prefix, chunks)
    assert all(chunk.content for chunk in chunks)
    assert max(len(chunk.content) for chunk in chunks) <= 2 * min(
        len(chunk.content) for chunk in chunks
    )


def test_chinese_sentence_and_list_boundaries_preserve_exact_utf8() -> None:
    prefix = "这是前缀。"
    sections = (
        f"一、蒸发{'水' * 55}。\n",
        f"二、凝结{'云' * 55}！\n",
        f"（三）降水{'雨' * 55}？\n",
        f"4、汇集{'河' * 55}。",
    )
    final_text = prefix + "".join(sections)
    assert len("".join(sections).encode("utf-8")) >= 600

    chunks = _chunk(final_text, prefix)

    assert 2 <= len(chunks) <= 4
    _assert_exact(final_text, prefix, chunks)
    decoded = tuple(chunk.content.decode("utf-8") for chunk in chunks)
    assert all(text.endswith(("。", "！\n", "？\n", "。\n")) for text in decoded)


def test_mixed_decimal_abbreviation_and_generic_chinese_separators_are_not_split() -> None:
    prefix = "Prefix. "
    first = "Dr. Lee measured 3.14 liters，then checked A、B、C before publishing. "
    second = "第二阶段使用同一结果；不会在普通分隔符处分段。 "
    tail = (first + second) * 6
    final_text = prefix + tail

    chunks = _chunk(final_text, prefix)

    _assert_exact(final_text, prefix, chunks)
    decoded = tuple(chunk.content.decode("utf-8") for chunk in chunks)
    assert all(not text.endswith(("Dr. ", "3.", "，", "；", "、")) for text in decoded)


def test_code_fence_punctuation_never_becomes_an_internal_boundary() -> None:
    prefix = "Prefix. "
    code = "```python\n" + ("value = 3.14  # not a sentence.\n" * 20) + "```\n"
    final_text = prefix + code + "The explanation ends here. Another safe sentence."

    chunks = _chunk(final_text, prefix)

    _assert_exact(final_text, prefix, chunks)
    for chunk in chunks[:-1]:
        assert chunk.content.decode("utf-8").count("```") % 2 == 0


def test_long_tail_without_safe_boundary_remains_one_monolithic_chunk() -> None:
    prefix = "Prefix. "
    final_text = prefix + ("continuous" * 100)

    chunks = _chunk(final_text, prefix)

    assert len(chunks) == 1
    _assert_exact(final_text, prefix, chunks)


def test_empty_tail_returns_no_chunks() -> None:
    prefix = "Prefix."
    assert _chunk(prefix, prefix) == ()


def test_prefix_offset_that_splits_utf8_scalar_fails_before_output() -> None:
    final_text = "前缀。后续内容。"
    with pytest.raises(AuthoritativeFinalChunkingViolation) as error:
        chunk_authoritative_final_tail(
            final_text,
            spoken_prefix_end_utf8=1,
        )
    assert error.value.reason == "INVALID_AUTHORITATIVE_PREFIX_SPAN"


@pytest.mark.parametrize(
    ("minimum_tail_bytes", "maximum_chunks"),
    ((0, 4), (600, 0), (600, 5), (True, 4)),
)
def test_invalid_policy_bounds_fail_closed(
    minimum_tail_bytes: int,
    maximum_chunks: int,
) -> None:
    with pytest.raises(AuthoritativeFinalChunkingViolation) as error:
        chunk_authoritative_final_tail(
            "Prefix. Tail.",
            spoken_prefix_end_utf8=len(b"Prefix. "),
            minimum_tail_bytes=minimum_tail_bytes,
            maximum_chunks=maximum_chunks,
        )
    assert error.value.reason == "INVALID_AUTHORITATIVE_CHUNK_POLICY"
