# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Deterministic post-final chunking for authoritative Live Voice TTS."""

from __future__ import annotations

import re
from dataclasses import dataclass


_MAX_TAIL_BYTES = 32_768
_MAXIMUM_CHUNKS = 4
_SENTENCE_TERMINALS = frozenset(".?!。？！")
_SENTENCE_TRAILERS = frozenset(".?!。？！…\"'”’」』】）》)]")
_ABBREVIATION = re.compile(
    r"(?:^|\s)(?:mr|mrs|ms|dr|prof|sr|jr|st|vs|etc)\.$",
    re.IGNORECASE,
)
_LIST_MARKER = re.compile(
    r"(?:(?:[-*•]|\d+[.)、])(?:\s|$)|"
    r"(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）))"
)


class AuthoritativeFinalChunkingViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AuthoritativeFinalChunk:
    seq: int
    source_start_utf8: int
    source_end_utf8: int
    content: bytes


def _validate_policy(minimum_tail_bytes: object, maximum_chunks: object) -> None:
    if (
        isinstance(minimum_tail_bytes, bool)
        or not isinstance(minimum_tail_bytes, int)
        or minimum_tail_bytes <= 0
        or minimum_tail_bytes > _MAX_TAIL_BYTES
        or isinstance(maximum_chunks, bool)
        or not isinstance(maximum_chunks, int)
        or maximum_chunks <= 0
        or maximum_chunks > _MAXIMUM_CHUNKS
    ):
        raise AuthoritativeFinalChunkingViolation(
            "INVALID_AUTHORITATIVE_CHUNK_POLICY",
            "authoritative final chunk policy is outside its closed bounds",
        )


def _character_offset_for_utf8(encoded: bytes, byte_offset: object) -> int:
    if (
        isinstance(byte_offset, bool)
        or not isinstance(byte_offset, int)
        or byte_offset < 0
        or byte_offset > len(encoded)
    ):
        raise AuthoritativeFinalChunkingViolation(
            "INVALID_AUTHORITATIVE_PREFIX_SPAN",
            "spoken prefix offset is outside the authoritative final",
        )
    try:
        return len(encoded[:byte_offset].decode("utf-8"))
    except UnicodeDecodeError as error:
        raise AuthoritativeFinalChunkingViolation(
            "INVALID_AUTHORITATIVE_PREFIX_SPAN",
            "spoken prefix offset splits a UTF-8 scalar",
        ) from error


def _period_is_boundary(text: str, index: int) -> bool:
    previous = text[index - 1] if index else ""
    following = text[index + 1] if index + 1 < len(text) else ""
    if previous.isdigit() and following.isdigit():
        return False
    if following and (following.isalnum() or following == "_"):
        return False
    return _ABBREVIATION.search(text[: index + 1]) is None


def _code_fence_mask(text: str) -> tuple[bool, ...]:
    inside = False
    mask = [False] * len(text)
    index = 0
    while index < len(text):
        if text.startswith("```", index):
            mask[index : index + 3] = [inside] * min(3, len(text) - index)
            inside = not inside
            index += 3
            continue
        mask[index] = inside
        index += 1
    return tuple(mask)


def _line_start_boundaries(text: str, start: int, mask: tuple[bool, ...]) -> set[int]:
    boundaries: set[int] = set()
    line_start = start
    while line_start < len(text):
        newline = text.find("\n", line_start)
        next_start = len(text) if newline < 0 else newline + 1
        if next_start >= len(text):
            break
        if not mask[next_start]:
            line_end = text.find("\n", next_start)
            if line_end < 0:
                line_end = len(text)
            line = text[next_start:line_end]
            if not text[line_start:newline if newline >= 0 else len(text)].strip():
                boundaries.add(next_start)
            elif _LIST_MARKER.match(line):
                boundaries.add(next_start)
        line_start = next_start
    return boundaries


def _safe_character_boundaries(text: str, start: int) -> tuple[int, ...]:
    mask = _code_fence_mask(text)
    boundaries = _line_start_boundaries(text, start, mask)
    for index in range(start, len(text)):
        character = text[index]
        if mask[index] or character not in _SENTENCE_TERMINALS:
            continue
        if character == "." and not _period_is_boundary(text, index):
            continue
        boundary = index + 1
        while boundary < len(text) and text[boundary] in _SENTENCE_TRAILERS:
            boundary += 1
        while boundary < len(text) and text[boundary].isspace():
            boundary += 1
        if boundary < len(text):
            boundaries.add(boundary)
    return tuple(sorted(boundary for boundary in boundaries if start < boundary < len(text)))


def _utf8_offset(text: str, character_offset: int) -> int:
    return len(text[:character_offset].encode("utf-8"))


def _balanced_groups(lengths: tuple[int, ...], maximum_chunks: int) -> tuple[tuple[int, int], ...]:
    count = len(lengths)
    group_count = min(count, maximum_chunks)
    if group_count <= 1:
        return ((0, count),)
    cumulative = [0]
    for length in lengths:
        cumulative.append(cumulative[-1] + length)
    groups: list[tuple[int, int]] = []
    start = 0
    for group_index in range(group_count - 1):
        remaining_groups = group_count - group_index
        minimum_end = start + 1
        maximum_end = count - (remaining_groups - 1)
        remaining_bytes = cumulative[count] - cumulative[start]
        target = cumulative[start] + remaining_bytes / remaining_groups
        end = min(
            range(minimum_end, maximum_end + 1),
            key=lambda candidate: (abs(cumulative[candidate] - target), candidate),
        )
        groups.append((start, end))
        start = end
    groups.append((start, count))
    return tuple(groups)


def chunk_authoritative_final_tail(
    final_text: str,
    *,
    spoken_prefix_end_utf8: int,
    minimum_tail_bytes: int = 600,
    maximum_chunks: int = 4,
) -> tuple[AuthoritativeFinalChunk, ...]:
    """Return exact, bounded AUDIO chunks for an already-authoritative tail."""

    _validate_policy(minimum_tail_bytes, maximum_chunks)
    if not isinstance(final_text, str):
        raise AuthoritativeFinalChunkingViolation(
            "INVALID_AUTHORITATIVE_FINAL",
            "authoritative final must be text",
        )
    try:
        encoded = final_text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise AuthoritativeFinalChunkingViolation(
            "INVALID_AUTHORITATIVE_FINAL",
            "authoritative final must contain Unicode scalars",
        ) from error
    if len(encoded) > _MAX_TAIL_BYTES:
        raise AuthoritativeFinalChunkingViolation(
            "INVALID_AUTHORITATIVE_FINAL",
            "authoritative final exceeds its closed byte bound",
        )
    start_character = _character_offset_for_utf8(encoded, spoken_prefix_end_utf8)
    if spoken_prefix_end_utf8 == len(encoded):
        return ()
    tail = encoded[spoken_prefix_end_utf8:]
    safe_characters = _safe_character_boundaries(final_text, start_character)
    safe_bytes = tuple(_utf8_offset(final_text, boundary) for boundary in safe_characters)
    unit_ends = (*safe_bytes, len(encoded))
    unit_starts = (spoken_prefix_end_utf8, *safe_bytes)
    units = tuple(
        (start, end, encoded[start:end])
        for start, end in zip(unit_starts, unit_ends, strict=True)
        if end > start
    )
    if len(tail) < minimum_tail_bytes or len(units) < 2:
        units = ((spoken_prefix_end_utf8, len(encoded), tail),)
    groups = _balanced_groups(tuple(len(unit[2]) for unit in units), maximum_chunks)
    chunks: list[AuthoritativeFinalChunk] = []
    for seq, (group_start, group_end) in enumerate(groups, start=1):
        start = units[group_start][0]
        end = units[group_end - 1][1]
        chunks.append(
            AuthoritativeFinalChunk(
                seq=seq,
                source_start_utf8=start,
                source_end_utf8=end,
                content=encoded[start:end],
            )
        )
    return tuple(chunks)
