from __future__ import annotations

import argparse
import hashlib
import json
import asyncio
import platform
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from statistics import median
from typing import Any, Callable, Sequence

import portalocker

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.streaming_speech import (
    NativeStreamingSpeechProvider,
    SynthesisStreamRef,
    SynthesisStreamRequest,
    TextSpan,
)
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    SpeechRouteTier,
    select_environment_streaming_speech,
)


class PopulationRole(StrEnum):
    A1 = "LVL-10L-A1"
    B2 = "LVL-10L-B2"
    B4 = "LVL-10L-B4"
    A2 = "LVL-10L-A2"


@dataclass(frozen=True, slots=True)
class Lvl10lFixture:
    fixture_id: str
    final_text: str
    unit_offsets: tuple[int, ...]
    b2_offsets: tuple[int, ...]
    b4_offsets: tuple[int, ...]
    sha256: str

    def chunks_for(self, role: PopulationRole) -> tuple[str, ...]:
        offsets = {
            PopulationRole.A1: (0, len(self.final_text)),
            PopulationRole.A2: (0, len(self.final_text)),
            PopulationRole.B2: self.b2_offsets,
            PopulationRole.B4: self.b4_offsets,
        }[role]
        return tuple(
            self.final_text[start:end] for start, end in zip(offsets, offsets[1:])
        )


@dataclass(frozen=True, slots=True)
class AttemptIdentity:
    run_id: str
    role: PopulationRole
    fixture_id: str
    round_index: int


@dataclass(frozen=True, slots=True)
class ChunkTimeline:
    chunk_index: int
    opened_ns: int
    first_pcm_ns: int | None
    completed_ns: int | None
    released_ns: int | None
    sample_count: int
    terminal_outcome: str
    terminal_reason: str


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    identity: AttemptIdentity
    started_ns: int
    request_to_first_pcm_ns: int | None
    request_to_any_chunk_pcm_ns: int | None
    request_to_reserve_ns: int | None
    request_to_complete_ns: int | None
    audio_duration_ns: int
    provider_request_count: int
    provider_error_count: int
    terminal_outcome: str
    terminal_reason: str
    group_completed: bool
    exact_text_coverage: bool
    released_chunk_indexes: tuple[int, ...]
    chunk_timelines: tuple[ChunkTimeline, ...]
    post_fence_sample_count: int
    forbidden_effects: dict[str, int]


@dataclass(frozen=True, slots=True)
class Lvl10lReport:
    decision: str
    gate_reasons: tuple[str, ...]
    records: tuple[AttemptRecord, ...]
    selected_arm: str | None = None
    smallest_break_even: str | None = None


SAMPLE_RATE_HZ = 48_000
RESERVE_SAMPLES = 12_000
MAX_ACTIVE_REQUESTS = 2
EVENT_TIMEOUT_SECONDS = 15.0
ZERO_FORBIDDEN_EFFECTS = {
    "agent_dispatches": 0,
    "tool_dispatches": 0,
    "task_mutations": 0,
    "chat_mutations": 0,
    "history_mutations": 0,
}


def _invalid(reason: str) -> ValueError:
    return ValueError(f"LVL10L_CORPUS_INVALID:{reason}")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_offsets(
    offsets: object,
    *,
    text_length: int,
    unit_offsets: tuple[int, ...],
    expected_groups: int,
    name: str,
) -> tuple[int, ...]:
    if not isinstance(offsets, list) or len(offsets) != expected_groups + 1:
        raise _invalid(f"{name}_count")
    if any(type(value) is not int for value in offsets):
        raise _invalid(f"{name}_type")
    value = tuple(offsets)
    if value[0] != 0 or value[-1] != text_length:
        raise _invalid(f"{name}_bounds")
    if any(left >= right for left, right in zip(value, value[1:])):
        raise _invalid(f"{name}_coverage")
    if any(boundary not in unit_offsets for boundary in value):
        raise _invalid(f"{name}_unit_boundary")
    return value


def load_fixture_manifest(path: Path) -> tuple[Lvl10lFixture, ...]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _invalid("unreadable") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "fixtures"}:
        raise _invalid("schema_fields")
    if raw["schema_version"] != "live-voice.lvl10l-corpus.v2":
        raise _invalid("schema_version")
    fixtures = raw["fixtures"]
    if not isinstance(fixtures, list) or len(fixtures) != 3:
        raise _invalid("fixture_count")
    expected = (
        ("long_600", 4, (550, 750)),
        ("long_1200", 8, (1100, 1500)),
        ("long_2100", 12, (2000, 2250)),
    )
    result: list[Lvl10lFixture] = []
    required = {
        "fixture_id",
        "final_text",
        "character_count",
        "utf8_byte_count",
        "unit_offsets",
        "unit_sha256",
        "b2_offsets",
        "b4_offsets",
        "sha256",
    }
    for item, (fixture_id, unit_count, accepted_range) in zip(
        fixtures, expected, strict=True
    ):
        if not isinstance(item, dict) or set(item) != required:
            raise _invalid("fixture_fields")
        text = item["final_text"]
        if item["fixture_id"] != fixture_id or not isinstance(text, str):
            raise _invalid("fixture_identity")
        if not accepted_range[0] <= len(text) <= accepted_range[1]:
            raise _invalid("character_count_range")
        if item["character_count"] != len(text) or item["utf8_byte_count"] != len(
            text.encode("utf-8")
        ):
            raise _invalid("declared_counts")
        if not isinstance(item["unit_offsets"], list) or len(item["unit_offsets"]) != unit_count + 1:
            raise _invalid("unit_offsets_count")
        if any(type(value) is not int for value in item["unit_offsets"]):
            raise _invalid("unit_offsets_type")
        unit_offsets = tuple(item["unit_offsets"])
        if (
            unit_offsets[0] != 0
            or unit_offsets[-1] != len(text)
            or any(left >= right for left, right in zip(unit_offsets, unit_offsets[1:]))
        ):
            raise _invalid("unit_offsets_coverage")
        hashes = item["unit_sha256"]
        if not isinstance(hashes, list) or len(hashes) != unit_count:
            raise _invalid("unit_hash_count")
        expected_hashes = [
            _sha256(text[start:end])
            for start, end in zip(unit_offsets, unit_offsets[1:])
        ]
        if hashes != expected_hashes:
            raise _invalid("unit_hash")
        if not isinstance(item["sha256"], str) or item["sha256"] != _sha256(text):
            raise _invalid("sha256")
        b2 = _validate_offsets(
            item["b2_offsets"],
            text_length=len(text),
            unit_offsets=unit_offsets,
            expected_groups=2,
            name="b2",
        )
        b4 = _validate_offsets(
            item["b4_offsets"],
            text_length=len(text),
            unit_offsets=unit_offsets,
            expected_groups=4,
            name="b4",
        )
        if b2 != (0, unit_offsets[unit_count // 2], len(text)):
            raise _invalid("b2_equal_unit_groups")
        if b4 != tuple(
            unit_offsets[index] for index in range(0, unit_count + 1, unit_count // 4)
        ):
            raise _invalid("b4_equal_unit_groups")
        result.append(Lvl10lFixture(fixture_id, text, unit_offsets, b2, b4, item["sha256"]))
    if not (
        result[1].final_text.startswith(result[0].final_text)
        and result[2].final_text.startswith(result[1].final_text)
    ):
        raise _invalid("nested_prefixes")
    return tuple(result)


def _response(identity: AttemptIdentity) -> ResponseRef:
    token = "-".join(
        (identity.run_id, identity.role.value, identity.fixture_id, str(identity.round_index))
    )
    return ResponseRef(
        f"lvl10l-{identity.run_id}-{identity.role.value}-{identity.fixture_id}",
        f"lvl10l-response-{token}",
        identity.round_index,
    )


def _request(
    response: ResponseRef,
    fixture: Lvl10lFixture,
    offsets: tuple[int, ...],
    index: int,
    identity: AttemptIdentity,
) -> SynthesisStreamRequest:
    start, end = offsets[index], offsets[index + 1]
    stable_stream = "-".join((identity.run_id, identity.role.value, identity.fixture_id, str(index)))
    unit_token = "-".join(
        (identity.role.value, identity.fixture_id, str(identity.round_index), str(index))
    )
    return SynthesisStreamRequest(
        SynthesisStreamRef(
            f"lvl10l-stream-{stable_stream}",
            identity.round_index,
            response,
            f"lvl10l-unit-{unit_token}",
            index,
        ),
        fixture.final_text[start:end],
        fixture.final_text[start:end],
        TextSpan(start, end),
        SAMPLE_RATE_HZ,
        EVENT_TIMEOUT_SECONDS,
    )


def _kind(event: Any) -> str:
    value = getattr(event.kind, "value", event.kind)
    return str(value).lower()


def _effects(provider: NativeStreamingSpeechProvider) -> dict[str, int]:
    snapshot = provider.conformance.snapshot()
    return {
        key: int(getattr(snapshot, key, 0)) for key in ZERO_FORBIDDEN_EFFECTS
    }


async def _consume_chunk(
    provider: NativeStreamingSpeechProvider,
    request: SynthesisStreamRequest,
    *,
    clock: Callable[[], int],
) -> tuple[int | None, int | None, int, int, str, str]:
    first_pcm_ns: int | None = None
    reserve_ns: int | None = None
    sample_count = 0
    try:
        while True:
            event = await provider.next_synthesis_event(
                request.ref, timeout_seconds=EVENT_TIMEOUT_SECONDS + 0.5
            )
            kind = _kind(event)
            if kind == "chunk" and getattr(event, "pcm_s16le", None):
                if first_pcm_ns is None:
                    first_pcm_ns = clock()
                sample_count += len(event.pcm_s16le) // 2
                if reserve_ns is None and sample_count >= RESERVE_SAMPLES:
                    reserve_ns = clock()
            if kind == "completed":
                return first_pcm_ns, reserve_ns, clock(), sample_count, "completed", "provider_completed"
            if kind == "cancelled":
                return first_pcm_ns, reserve_ns, clock(), sample_count, "cancelled", "provider_cancelled"
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return first_pcm_ns, reserve_ns, clock(), sample_count, "failed", f"provider_exception:{type(exc).__name__}"


async def run_attempt(
    provider: NativeStreamingSpeechProvider,
    fixture: Lvl10lFixture,
    identity: AttemptIdentity,
    *,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> AttemptRecord:
    offsets = {
        PopulationRole.A1: (0, len(fixture.final_text)),
        PopulationRole.B2: fixture.b2_offsets,
        PopulationRole.B4: fixture.b4_offsets,
        PopulationRole.A2: (0, len(fixture.final_text)),
    }[identity.role]
    expected_chunks = len(offsets) - 1
    response = _response(identity)
    provider.conformance.activate_response(response)
    started_ns = monotonic_ns()
    live: dict[int, tuple[SynthesisStreamRequest, asyncio.Task[Any]]] = {}
    completed: dict[int, tuple[int | None, int | None, int, int, str, str]] = {}
    timeline: dict[int, ChunkTimeline] = {}
    released: list[int] = []
    opened = 0
    errors = 0
    fenced = False
    cancellation = False

    async def open_chunk(index: int) -> None:
        nonlocal opened, errors
        request = _request(response, fixture, offsets, index, identity)
        opened_at = monotonic_ns()
        opened += 1
        try:
            await provider.open_synthesis(request)
        except Exception:
            errors += 1
            completed[index] = (None, None, monotonic_ns(), 0, "failed", "provider_open_exception")
            timeline[index] = ChunkTimeline(index, opened_at, None, monotonic_ns(), None, 0, "failed", "provider_open_exception")
            return
        live[index] = (
            request,
            asyncio.create_task(_consume_chunk(provider, request, clock=monotonic_ns)),
        )
        timeline[index] = ChunkTimeline(index, opened_at, None, None, None, 0, "opened", "pending")

    async def fence_group(reason: str) -> None:
        nonlocal fenced
        if fenced:
            return
        fenced = True
        current = tuple(live.items())
        for index, (_request, task) in current:
            if task.done() and not task.cancelled():
                try:
                    result = task.result()
                except Exception:
                    continue
                prior = timeline[index]
                timeline[index] = ChunkTimeline(
                    index, prior.opened_ns, result[0], result[2], None, result[3], result[4], result[5]
                )
        for _index, (request, task) in current:
            if not task.done():
                try:
                    await provider.cancel_synthesis(request.ref, reason=reason)
                except Exception:
                    pass
                task.cancel()
        if current:
            await asyncio.gather(*(task for _, (_, task) in current), return_exceptions=True)
        for index, (_request, task) in current:
            if task.cancelled() or not task.done():
                continue
            try:
                result = task.result()
            except Exception:
                continue
            prior = timeline[index]
            timeline[index] = ChunkTimeline(
                index, prior.opened_ns, result[0], result[2], None, result[3], result[4], result[5]
            )
        for index, prior in tuple(timeline.items()):
            if prior.released_ns is None:
                timeline[index] = ChunkTimeline(
                    prior.chunk_index,
                    prior.opened_ns,
                    prior.first_pcm_ns,
                    prior.completed_ns,
                    None,
                    prior.sample_count,
                    "fenced",
                    f"group_fenced:{reason}",
                )
        live.clear()

    try:
        await open_chunk(0)
        if expected_chunks > 1:
            await open_chunk(1)
        next_release = 0
        while len(completed) < expected_chunks:
            if errors:
                await fence_group("lvl10l_group_fence")
                break
            if not live:
                errors += 1
                await fence_group("lvl10l_group_no_live_stream")
                break
            done, _ = await asyncio.wait(
                [task for _, task in live.values()], return_when=asyncio.FIRST_COMPLETED
            )
            for index, (_request_item, task) in tuple(live.items()):
                if task not in done:
                    continue
                result = task.result()
                completed[index] = result
                del live[index]
                prior = timeline[index]
                timeline[index] = ChunkTimeline(
                    index, prior.opened_ns, result[0], result[2], None, result[3], result[4], result[5]
                )
                if result[4] != "completed":
                    errors += 1
            if errors:
                await fence_group("lvl10l_group_fence")
                break
            while next_release in completed and completed[next_release][4] == "completed":
                prior = timeline[next_release]
                timeline[next_release] = ChunkTimeline(
                    prior.chunk_index,
                    prior.opened_ns,
                    prior.first_pcm_ns,
                    prior.completed_ns,
                    monotonic_ns(),
                    prior.sample_count,
                    prior.terminal_outcome,
                    prior.terminal_reason,
                )
                released.append(next_release)
                next_release += 1
                if opened < expected_chunks and len(live) < MAX_ACTIVE_REQUESTS:
                    await open_chunk(opened)
        if len(released) != expected_chunks or errors:
            await fence_group("lvl10l_group_incomplete")
        records = tuple(timeline[index] for index in range(opened))
        chunk_zero = timeline.get(0)
        first_values = [row.first_pcm_ns for row in records if row.first_pcm_ns is not None]
        reserve_at = chunk_zero.completed_ns if chunk_zero and chunk_zero.sample_count < RESERVE_SAMPLES else (chunk_zero and completed.get(0, (None, None))[1])
        completed_at = max((row.completed_ns or started_ns for row in records), default=started_ns)
        outcome = "completed" if not fenced and not errors and len(released) == expected_chunks else "failed"
        return AttemptRecord(
            identity,
            started_ns,
            None if chunk_zero is None or chunk_zero.first_pcm_ns is None else chunk_zero.first_pcm_ns - started_ns,
            None if not first_values else min(first_values) - started_ns,
            None if reserve_at is None else reserve_at - started_ns,
            None if outcome != "completed" else completed_at - started_ns,
            sum(row.sample_count for row in records if row.released_ns is not None) * 1_000_000_000 // SAMPLE_RATE_HZ,
            opened,
            errors,
            "cancelled" if cancellation else outcome,
            "provider_completed" if outcome == "completed" else "group_fenced",
            outcome == "completed",
            "".join(fixture.final_text[start:end] for start, end in zip(offsets, offsets[1:])) == fixture.final_text,
            tuple(released),
            records,
            0,
            _effects(provider),
        )
    except asyncio.CancelledError:
        cancellation = True
        await fence_group("lvl10l_caller_cancel")
        records = tuple(timeline[index] for index in range(opened))
        return AttemptRecord(
            identity, started_ns, None, None, None, None, 0, opened, errors,
            "cancelled", "caller_cancelled", False, True, tuple(released), records, 0, _effects(provider)
        )
    finally:
        if live:
            await fence_group("lvl10l_finally_fence")


FIXTURE_IDS = ("long_600", "long_1200", "long_2100")


def scheduled_cells(round_index: int) -> tuple[tuple[PopulationRole, str], ...]:
    if type(round_index) is not int or round_index < 0:
        raise ValueError("LVL10L_ROUND_INVALID")
    fixtures = FIXTURE_IDS[round_index % 3 :] + FIXTURE_IDS[: round_index % 3]
    candidates = (PopulationRole.B2, PopulationRole.B4) if round_index % 2 == 0 else (PopulationRole.B4, PopulationRole.B2)
    return tuple(
        (role, fixture)
        for fixture in fixtures
        for role in (PopulationRole.A1, *candidates, PopulationRole.A2)
    )


def interpolate_reference(
    candidate: AttemptRecord,
    a1: AttemptRecord,
    a2: AttemptRecord,
    metric: str,
) -> float:
    start, before, after = candidate.started_ns, a1.started_ns, a2.started_ns
    if after <= before or not before <= start <= after:
        raise ValueError("LVL10L_INTERPOLATION_INVALID")
    before_value = getattr(a1, metric)
    after_value = getattr(a2, metric)
    if before_value is None or after_value is None:
        raise ValueError("LVL10L_INTERPOLATION_METRIC_INVALID")
    return before_value + (after_value - before_value) * (start - before) / (after - before)


def _p50(records: Sequence[Any], metric: str) -> float:
    return float(median(getattr(record, metric) for record in records))


def _expected_requests(role: PopulationRole) -> int:
    return {PopulationRole.A1: 1, PopulationRole.B2: 2, PopulationRole.B4: 4, PopulationRole.A2: 1}[role]


def _complete_integrity(record: Any) -> bool:
    return (
        record.terminal_outcome == "completed"
        and record.group_completed
        and record.provider_error_count == 0
        and record.provider_request_count == _expected_requests(record.identity.role)
        and record.exact_text_coverage
        and record.released_chunk_indexes == tuple(range(_expected_requests(record.identity.role)))
        and record.post_fence_sample_count == 0
        and record.forbidden_effects == ZERO_FORBIDDEN_EFFECTS
    )


def _candidate_gate(
    candidate: PopulationRole,
    fixture_id: str,
    groups: dict[tuple[PopulationRole, str], list[Any]],
) -> tuple[bool, list[float]]:
    candidate_rows = groups[(candidate, fixture_id)]
    a1_rows = {row.identity.round_index: row for row in groups[(PopulationRole.A1, fixture_id)]}
    a2_rows = {row.identity.round_index: row for row in groups[(PopulationRole.A2, fixture_id)]}
    gains: list[float] = []
    paired_first: list[float] = []
    paired_reserve: list[float] = []
    paired_duration: list[float] = []
    for row in candidate_rows:
        a1, a2 = a1_rows[row.identity.round_index], a2_rows[row.identity.round_index]
        gains.append(interpolate_reference(row, a1, a2, "request_to_complete_ns") - row.request_to_complete_ns)
        paired_first.append(interpolate_reference(row, a1, a2, "request_to_first_pcm_ns"))
        paired_reserve.append(interpolate_reference(row, a1, a2, "request_to_reserve_ns"))
        paired_duration.append(interpolate_reference(row, a1, a2, "audio_duration_ns"))
    gain_p50 = float(median(gains))
    reference_p50 = float(median(
        interpolate_reference(row, a1_rows[row.identity.round_index], a2_rows[row.identity.round_index], "request_to_complete_ns")
        for row in candidate_rows
    ))
    candidate_complete = _p50(candidate_rows, "request_to_complete_ns")
    control_complete = (
        _p50(groups[(PopulationRole.A1, fixture_id)], "request_to_complete_ns"),
        _p50(groups[(PopulationRole.A2, fixture_id)], "request_to_complete_ns"),
    )
    first_regression = _p50(candidate_rows, "request_to_first_pcm_ns") - float(median(paired_first))
    reserve_regression = _p50(candidate_rows, "request_to_reserve_ns") - float(median(paired_reserve))
    duration = _p50(candidate_rows, "audio_duration_ns")
    paired_duration_p50 = float(median(paired_duration))
    return (
        gain_p50 >= 750_000_000
        and gain_p50 * 100 >= reference_p50 * 15
        and candidate_complete < min(control_complete)
        and sum(gain > 0 for gain in gains) >= 4
        and first_regression <= 200_000_000
        and first_regression * 100 <= float(median(paired_first)) * 10
        and reserve_regression <= 200_000_000
        and reserve_regression * 100 <= float(median(paired_reserve)) * 10
        and abs(duration - paired_duration_p50) * 100 <= paired_duration_p50 * 10,
        gains,
    )


def _smallest_monotonic_break_even(
    candidate: PopulationRole,
    groups: dict[tuple[PopulationRole, str], list[Any]],
) -> str:
    passed_2100, _ = _candidate_gate(candidate, "long_2100", groups)
    assert passed_2100
    passed_1200, _ = _candidate_gate(candidate, "long_1200", groups)
    passed_600, _ = _candidate_gate(candidate, "long_600", groups)
    if passed_600 and not passed_1200:
        return "NON_MONOTONIC"
    if passed_600:
        return "long_600"
    if passed_1200:
        return "long_1200"
    return "long_2100"


def _pilot_result(
    groups: dict[tuple[PopulationRole, str], list[Any]], records: Sequence[AttemptRecord]
) -> Lvl10lReport:
    for fixture in ("long_1200", "long_2100"):
        controls = [
            groups[(PopulationRole.A1, fixture)][0].request_to_complete_ns,
            groups[(PopulationRole.A2, fixture)][0].request_to_complete_ns,
        ]
        if not any(
            groups[(candidate, fixture)][0].request_to_complete_ns < min(controls)
            for candidate in (PopulationRole.B2, PopulationRole.B4)
        ):
            return Lvl10lReport("PILOT_FAILED", (f"pilot_faster_than_controls:{fixture}",), tuple(records))
    for fixture in ("long_1200", "long_2100"):
        a1, a2 = groups[(PopulationRole.A1, fixture)][0], groups[(PopulationRole.A2, fixture)][0]
        for candidate in (PopulationRole.B2, PopulationRole.B4):
            row = groups[(candidate, fixture)][0]
            for metric in ("request_to_first_pcm_ns", "request_to_reserve_ns"):
                paired = interpolate_reference(row, a1, a2, metric)
                regression = getattr(row, metric) - paired
                if regression > 1_000_000_000 and regression * 100 > paired * 50:
                    return Lvl10lReport("PILOT_FAILED", (f"pilot_regression:{fixture}:{metric}",), tuple(records))
    b2_2100 = groups[(PopulationRole.B2, "long_2100")][0].request_to_complete_ns
    b4_2100 = groups[(PopulationRole.B4, "long_2100")][0].request_to_complete_ns
    selected = PopulationRole.B2 if b2_2100 <= b4_2100 else PopulationRole.B4
    return Lvl10lReport(
        "PILOT_PASS",
        ("pilot_denominators_pass", "pilot_integrity_pass", "pilot_authorization_pass"),
        tuple(records),
        selected.value,
        None,
    )


def reduce_records(
    records: Sequence[AttemptRecord], *, expected_rounds: int, provenance_complete: bool = True
) -> Lvl10lReport:
    reasons: list[str] = []
    if expected_rounds not in (1, 5):
        return Lvl10lReport("INCONCLUSIVE", ("invalid_expected_rounds",), tuple(records))
    groups: dict[tuple[PopulationRole, str], list[Any]] = {}
    for record in records:
        groups.setdefault((record.identity.role, record.identity.fixture_id), []).append(record)
    expected_cells = [(role, fixture) for fixture in FIXTURE_IDS for role in PopulationRole]
    if any(len(groups.get(cell, ())) != expected_rounds for cell in expected_cells):
        return Lvl10lReport("INCONCLUSIVE", ("provenance_denominators",), tuple(records))
    if not provenance_complete:
        return Lvl10lReport("INCONCLUSIVE", ("provenance_incomplete",), tuple(records))
    if any(not _complete_integrity(record) for record in records):
        return Lvl10lReport("REJECTED", ("integrity_reliability",), tuple(records))
    if expected_rounds == 1:
        return _pilot_result(groups, records)
    for fixture in FIXTURE_IDS:
        a1, a2 = groups[(PopulationRole.A1, fixture)], groups[(PopulationRole.A2, fixture)]
        for metric, absolute_ns, relative_pct in (
            ("request_to_complete_ns", 1_500_000_000, 10),
            ("request_to_first_pcm_ns", 250_000_000, 20),
            ("request_to_reserve_ns", 250_000_000, 20),
        ):
            one, two = _p50(a1, metric), _p50(a2, metric)
            if abs(one - two) > absolute_ns or abs(one - two) * 100 > min(one, two) * relative_pct:
                return Lvl10lReport("INCONCLUSIVE", (f"control_drift:{fixture}:{metric}",), tuple(records))
        close_brackets = sum(
            abs(a1_row.request_to_complete_ns - a2_row.request_to_complete_ns) * 100
            <= min(a1_row.request_to_complete_ns, a2_row.request_to_complete_ns) * 20
            for a1_row, a2_row in zip(a1, a2)
        )
        if expected_rounds == 5 and close_brackets < 4:
            return Lvl10lReport("INCONCLUSIVE", (f"control_brackets:{fixture}",), tuple(records))
    b2_2100, b2_gains = _candidate_gate(PopulationRole.B2, "long_2100", groups)
    b4_2100, b4_gains = _candidate_gate(PopulationRole.B4, "long_2100", groups)
    if not b2_2100 and not b4_2100:
        return Lvl10lReport("NO_MATERIAL_GAIN", ("long_2100_materiality", "whole_chunk_availability_diagnostic_only"), tuple(records))
    if b2_2100 and b4_2100:
        b2_gain, b4_gain = float(median(b2_gains)), float(median(b4_gains))
        if b4_gain - b2_gain >= 750_000_000 and (b4_gain - b2_gain) * 100 >= b2_gain * 10:
            decision = "B4_MATERIAL"
        else:
            decision = "B2_AND_B4_MATERIAL_PREFER_B2"
    elif b2_2100:
        decision = "B2_MATERIAL"
    else:
        decision = "B4_MATERIAL"
    selected = PopulationRole.B4 if decision == "B4_MATERIAL" else PopulationRole.B2
    break_even = _smallest_monotonic_break_even(selected, groups)
    reasons.extend(("provenance_denominators_pass", "integrity_reliability_pass", "control_drift_pass", "long_2100_materiality_pass", f"monotonic_bucket_walk:{break_even}", "whole_chunk_availability_diagnostic_only"))
    return Lvl10lReport(decision, tuple(reasons), tuple(records), selected.value, break_even)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_record(record: AttemptRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["identity"]["role"] = record.identity.role.value
    completed = [
        row["completed_ns"]
        for row in payload["chunk_timelines"]
        if row["completed_ns"] is not None
    ]
    payload["whole_chunk_availability_gap_ns"] = (
        None if len(completed) < 2 else max(completed) - min(completed)
    )
    return payload


def _nearest_rank(values: Sequence[int | float], percentile: int) -> float:
    ordered = sorted(values)
    return float(ordered[(len(ordered) * percentile + 99) // 100 - 1])


def _percentile_provenance(rounds: int) -> dict[str, str]:
    return {
        "p50": "median",
        "p90_p95": f"nearest-rank descriptive (n={rounds})",
        "decision_role": "non-gating",
    }


def _timing_summary(rows: Sequence[Any], metric: str) -> dict[str, float | None]:
    values = [getattr(row, metric) for row in rows if getattr(row, metric) is not None]
    if not values:
        return {"p50": None, "p90": None, "p95": None}
    return {
        "p50": float(median(values)),
        "p90": _nearest_rank(values, 90),
        "p95": _nearest_rank(values, 95),
    }


def _numeric_p50(rows: Sequence[Any], metric: str) -> float | None:
    values = [getattr(row, metric) for row in rows if getattr(row, metric) is not None]
    return None if not values else float(median(values))


def _artifact_metrics(records: Sequence[AttemptRecord]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    groups: dict[tuple[PopulationRole, str], list[Any]] = {}
    for record in records:
        groups.setdefault((record.identity.role, record.identity.fixture_id), []).append(record)
    per_cell: dict[str, Any] = {}
    paired: dict[str, Any] = {}
    control_drift: dict[str, Any] = {}
    candidate_inputs: dict[str, Any] = {}
    incremental: dict[str, Any] = {}
    for role in PopulationRole:
        per_cell[role.value] = {}
        for fixture in FIXTURE_IDS:
            rows = groups.get((role, fixture), [])
            per_cell[role.value][fixture] = {
                "denominator": len(rows),
                "measured_denominator": sum(row.request_to_complete_ns is not None for row in rows),
                "observed_request_count": sum(row.provider_request_count for row in rows),
                "provider_error_count": sum(row.provider_error_count for row in rows),
                "failure_count": sum(row.terminal_outcome != "completed" for row in rows),
                "request_to_first_pcm_ns": _timing_summary(rows, "request_to_first_pcm_ns"),
                "request_to_reserve_ns": _timing_summary(rows, "request_to_reserve_ns"),
                "request_to_complete_ns": _timing_summary(rows, "request_to_complete_ns"),
                "audio_duration_ns": _timing_summary(rows, "audio_duration_ns"),
            }
    for fixture in FIXTURE_IDS:
        a1 = {row.identity.round_index: row for row in groups[(PopulationRole.A1, fixture)]}
        a2 = {row.identity.round_index: row for row in groups[(PopulationRole.A2, fixture)]}
        control_drift[fixture] = {}
        for metric in ("request_to_first_pcm_ns", "request_to_reserve_ns", "request_to_complete_ns"):
            one, two = _numeric_p50(list(a1.values()), metric), _numeric_p50(list(a2.values()), metric)
            absolute = None if one is None or two is None else abs(one - two)
            control_drift[fixture][metric] = {
                "absolute_ns": absolute,
                "percent": None if absolute is None or min(one, two) == 0 else absolute * 100 / min(one, two),
            }
        for role in (PopulationRole.B2, PopulationRole.B4):
            paired.setdefault(role.value, {})[fixture] = {}
            rows = groups[(role, fixture)]
            comparable = [
                row for row in rows
                if row.request_to_complete_ns is not None
                and a1[row.identity.round_index].request_to_complete_ns is not None
                and a2[row.identity.round_index].request_to_complete_ns is not None
            ]
            references = [interpolate_reference(row, a1[row.identity.round_index], a2[row.identity.round_index], "request_to_complete_ns") for row in comparable]
            gains = [reference - row.request_to_complete_ns for row, reference in zip(comparable, references)]
            paired[role.value][fixture] = {
                "measured_denominator": len(gains),
                "p50_gain_ns": None if not gains else float(median(gains)),
                "p50_gain_pct": None if not gains else float(median(gain * 100 / reference for gain, reference in zip(gains, references))),
                "win_count": sum(gain > 0 for gain in gains),
            }
            candidate_inputs.setdefault(role.value, {})[fixture] = {}
            for label, metric in (
                ("first_pcm_regression", "request_to_first_pcm_ns"),
                ("reserve_regression", "request_to_reserve_ns"),
                ("audio_duration_delta", "audio_duration_ns"),
            ):
                comparable_metric = [
                    row for row in rows
                    if getattr(row, metric) is not None
                    and getattr(a1[row.identity.round_index], metric) is not None
                    and getattr(a2[row.identity.round_index], metric) is not None
                ]
                references_metric = [
                    interpolate_reference(row, a1[row.identity.round_index], a2[row.identity.round_index], metric)
                    for row in comparable_metric
                ]
                deltas = [getattr(row, metric) - reference for row, reference in zip(comparable_metric, references_metric)]
                percentages = [
                    delta * 100 / reference
                    for delta, reference in zip(deltas, references_metric)
                    if reference != 0
                ]
                candidate_inputs[role.value][fixture][label] = {
                    "measured_denominator": len(deltas),
                    "p50_absolute_ns": None if not deltas else float(median(deltas)),
                    "p50_percent": None if not percentages else float(median(percentages)),
                }
        b2 = paired[PopulationRole.B2.value][fixture]
        b4 = paired[PopulationRole.B4.value][fixture]
        if b2["p50_gain_ns"] is None or b4["p50_gain_ns"] is None:
            incremental[fixture] = {"measured_denominator": 0, "p50_gain_delta_ns": None, "p50_gain_delta_pct": None}
        else:
            delta = b4["p50_gain_ns"] - b2["p50_gain_ns"]
            incremental[fixture] = {
                "measured_denominator": min(b2["measured_denominator"], b4["measured_denominator"]),
                "p50_gain_delta_ns": delta,
                "p50_gain_delta_pct": None if b2["p50_gain_ns"] == 0 else delta * 100 / b2["p50_gain_ns"],
            }
    return per_cell, paired, control_drift, candidate_inputs, incremental


def _ms(summary: dict[str, float | None]) -> str:
    return "/".join("—" if value is None else f"{value / 1_000_000:.3f}" for value in summary.values())


def _incremental_line(fixture: str, row: dict[str, Any]) -> str:
    gain = "—" if row["p50_gain_delta_ns"] is None else f"{row['p50_gain_delta_ns'] / 1_000_000:.3f}"
    percent = "—" if row["p50_gain_delta_pct"] is None else f"{row['p50_gain_delta_pct']:.3f}"
    return f"| {fixture} | {row['measured_denominator']} | {gain} | {percent} |"


def _candidate_input_line(candidate: str, fixture: str, metric: str, row: dict[str, Any]) -> str:
    absolute = "—" if row["p50_absolute_ns"] is None else f"{row['p50_absolute_ns'] / 1_000_000:.3f}"
    percent = "—" if row["p50_percent"] is None else f"{row['p50_percent']:.3f}"
    return f"| {candidate} | {fixture} | {metric} | {row['measured_denominator']} | {absolute} | {percent} |"


def _markdown_report(
    report: Lvl10lReport,
    per_cell: dict[str, Any],
    paired: dict[str, Any],
    control_drift: dict[str, Any],
    candidate_inputs: dict[str, Any],
    incremental: dict[str, Any],
    records: Sequence[AttemptRecord],
    observed_requests: int,
    expected_requests: int,
    rounds: int,
) -> str:
    timing_rows = [
        "| Role | Fixture | n / measured | First p50/p90/p95 ms | Reserve p50/p90/p95 ms | Complete p50/p90/p95 ms | Duration p50/p90/p95 ms |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    totals = ["| Role | Fixture | Requests | Provider errors | Failures |", "| --- | --- | ---: | ---: | ---: |"]
    for role in PopulationRole:
        for fixture in FIXTURE_IDS:
            cell = per_cell[role.value][fixture]
            timing_rows.append(
                f"| {role.value} | {fixture} | {cell['denominator']} / {cell['measured_denominator']} | "
                f"{_ms(cell['request_to_first_pcm_ns'])} | {_ms(cell['request_to_reserve_ns'])} | "
                f"{_ms(cell['request_to_complete_ns'])} | {_ms(cell['audio_duration_ns'])} |"
            )
            totals.append(
                f"| {role.value} | {fixture} | {cell['observed_request_count']} | "
                f"{cell['provider_error_count']} | {cell['failure_count']} |"
            )
    paired_rows = ["| Candidate | Fixture | Measured | p50 completion gain ms | p50 gain % | Wins |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    for role in (PopulationRole.B2, PopulationRole.B4):
        for fixture in FIXTURE_IDS:
            row = paired[role.value][fixture]
            gain = "—" if row["p50_gain_ns"] is None else f"{row['p50_gain_ns'] / 1_000_000:.3f}"
            percent = "—" if row["p50_gain_pct"] is None else f"{row['p50_gain_pct']:.3f}"
            paired_rows.append(f"| {role.value} | {fixture} | {row['measured_denominator']} | {gain} | {percent} | {row['win_count']} |")
    drift_rows = ["| Fixture | First abs ms / % | Reserve abs ms / % | Complete abs ms / % |", "| --- | --- | --- | --- |"]
    for fixture in FIXTURE_IDS:
        rendered = []
        for metric in ("request_to_first_pcm_ns", "request_to_reserve_ns", "request_to_complete_ns"):
            value = control_drift[fixture][metric]
            absolute = "—" if value["absolute_ns"] is None else f"{value['absolute_ns'] / 1_000_000:.3f}"
            percent = "—" if value["percent"] is None else f"{value['percent']:.3f}"
            rendered.append(f"{absolute} / {percent}")
        drift_rows.append(f"| {fixture} | {' | '.join(rendered)} |")
    decision_rows = [
        "| Candidate | Fixture | Metric | Measured | p50 absolute ms | p50 percent |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for role in (PopulationRole.B2, PopulationRole.B4):
        for fixture in FIXTURE_IDS:
            for metric in ("first_pcm_regression", "reserve_regression", "audio_duration_delta"):
                decision_rows.append(_candidate_input_line(role.value, fixture, metric, candidate_inputs[role.value][fixture][metric]))
    return "\n".join((
        "# LVL-10L long-form TTS screen",
        "",
        f"Decision: **{report.decision}**. Selected arm: **{report.selected_arm or 'none'}**. Smallest break-even: **{report.smallest_break_even or 'none'}**.",
        f"Attempts: {len(records)}; requests: {observed_requests}/{expected_requests}.",
        f"Gate reasons: {', '.join(report.gate_reasons)}.",
        f"Percentiles: p50=median; p90/p95 descriptive nearest-rank (n={rounds}), non-gating.",
        "",
        "## Per-role/fixture timings",
        "",
        *timing_rows,
        "",
        "## Paired completion",
        "",
        *paired_rows,
        "",
        "## Request and failure totals",
        "",
        *totals,
        "",
        "## Control drift",
        "",
        *drift_rows,
        "",
        "## Candidate first/reserve/duration decision inputs",
        "",
        *decision_rows,
        "",
        "## B4 vs B2 incremental paired gain",
        "",
        "| Fixture | Measured | p50 gain delta ms | p50 gain delta % |",
        "| --- | ---: | ---: | ---: |",
        *(_incremental_line(fixture, row) for fixture, row in incremental.items()),
        "",
        "Measured: Provider/source timings and terminal counts. Derived: paired gains, duration and whole-chunk availability diagnostics.",
        "Browser and product latency are excluded. Whole-chunk availability is diagnostic only and does not decide materiality.",
        "",
    ))


def _write_artifacts(
    output_root: Path,
    args: argparse.Namespace,
    report: Lvl10lReport,
    records: Sequence[AttemptRecord],
) -> None:
    attempts = output_root / "attempts.jsonl"
    attempts.write_text(
        "".join(json.dumps(_safe_record(record), sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    expected_requests = args.rounds * len(FIXTURE_IDS) * sum(
        _expected_requests(role) for role in PopulationRole
    )
    observed_requests = sum(record.provider_request_count for record in records)
    per_cell, paired_completion, control_drift, candidate_inputs, incremental = _artifact_metrics(records)
    report_payload = {
        "schema_version": "live-voice.lvl10l-report.v1",
        "decision": report.decision,
        "gate_reasons": list(report.gate_reasons),
        "attempt_count": len(records),
        "expected_requests": expected_requests,
        "observed_requests": observed_requests,
        "request_totals_by_role": {
            role.value: sum(
                record.provider_request_count
                for record in records
                if record.identity.role is role
            )
            for role in PopulationRole
        },
        "selected_arm": report.selected_arm,
        "smallest_break_even": report.smallest_break_even,
        "per_cell": per_cell,
        "paired_completion": paired_completion,
        "control_drift": control_drift,
        "candidate_decision_inputs": candidate_inputs,
        "b4_incremental_vs_b2": incremental["long_2100"],
        "whole_chunk_availability": "diagnostic_only_non_gating",
        "percentile_provenance": _percentile_provenance(args.rounds),
        "artifact_hashes": {
            "run_sha256": _file_sha256(output_root / "run.json"),
            "manifest_sha256": _file_sha256(output_root / "manifest.json"),
            "attempts_sha256": _file_sha256(attempts),
            "report_canonical_excludes": ["artifact_hashes.report_canonical_sha256"],
        },
    }
    canonical = json.dumps(report_payload, sort_keys=True, separators=(",", ":")).encode()
    report_payload["artifact_hashes"]["report_canonical_sha256"] = hashlib.sha256(canonical).hexdigest()
    (output_root / "report.json").write_text(
        json.dumps(report_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (output_root / "report.md").write_text(
        _markdown_report(report, per_cell, paired_completion, control_drift, candidate_inputs, incremental, records, observed_requests, expected_requests, args.rounds),
        encoding="utf-8",
    )


def _write_setup_failure_artifacts(output_root: Path, args: argparse.Namespace) -> None:
    attempts = output_root / "attempts.jsonl"
    attempts.write_text("", encoding="utf-8")
    payload = {
        "schema_version": "live-voice.lvl10l-report.v1",
        "decision": "INCONCLUSIVE",
        "gate_reasons": ["provider_setup_failed"],
        "attempt_count": 0,
        "expected_requests": args.rounds * len(FIXTURE_IDS) * sum(_expected_requests(role) for role in PopulationRole),
        "observed_requests": 0,
        "request_totals_by_role": {role.value: 0 for role in PopulationRole},
        "selected_arm": None,
        "smallest_break_even": None,
        "setup_failure": "provider_setup_failed",
        "percentile_provenance": _percentile_provenance(args.rounds),
        "artifact_hashes": {
            "run_sha256": _file_sha256(output_root / "run.json"),
            "manifest_sha256": _file_sha256(output_root / "manifest.json"),
            "attempts_sha256": _file_sha256(attempts),
            "report_canonical_excludes": ["artifact_hashes.report_canonical_sha256"],
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["artifact_hashes"]["report_canonical_sha256"] = hashlib.sha256(canonical).hexdigest()
    (output_root / "report.json").write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (output_root / "report.md").write_text(
        "# LVL-10L long-form TTS screen\n\nDecision: **INCONCLUSIVE**.\n\nGate reasons: provider_setup_failed.\n",
        encoding="utf-8",
    )


async def run_population(
    args: argparse.Namespace, fixtures: tuple[Lvl10lFixture, ...]
) -> Lvl10lReport:
    providers: dict[PopulationRole, NativeStreamingSpeechProvider] = {}
    records: list[AttemptRecord] = []
    identities: dict[PopulationRole, int] = {role: 0 for role in PopulationRole}
    setup_complete = False
    try:
        for role in PopulationRole:
            selection = await select_environment_streaming_speech(batch_available=False)
            if selection.tier is not SpeechRouteTier.STREAMING or selection.provider is None:
                raise RuntimeError("LVL10L_STREAMING_PROVIDER_REQUIRED")
            providers[role] = selection.provider
        run_path = args.output_root / "run.json"
        run_document = json.loads(run_path.read_text(encoding="utf-8"))
        run_document["provider_route"] = {
            "adapter_classes": sorted(
                {f"{type(provider).__module__}.{type(provider).__qualname__}" for provider in providers.values()}
            ),
            "synthesis_models": sorted({str(provider.synthesis_model) for provider in providers.values() if getattr(provider, "synthesis_model", None)}),
            "synthesis_voices": sorted({str(provider.synthesis_voice) for provider in providers.values() if getattr(provider, "synthesis_voice", None)}),
            "audio_format": "pcm_s16le",
            "sample_rate_hz": SAMPLE_RATE_HZ,
        }
        run_path.write_text(json.dumps(run_document, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        setup_complete = True
        by_id = {fixture.fixture_id: fixture for fixture in fixtures}
        for round_index in range(args.rounds):
            for role, fixture_id in scheduled_cells(round_index):
                records.append(
                    await run_attempt(
                        providers[role],
                        by_id[fixture_id],
                        AttemptIdentity(args.run_id, role, fixture_id, round_index),
                    )
                )
                identities[role] += 1
        expected_identities = 15 if args.rounds == 5 else 3
        if any(count != expected_identities for count in identities.values()):
            raise RuntimeError("LVL10L_RESPONSE_IDENTITY_BUDGET_INVALID")
        report = reduce_records(records, expected_rounds=args.rounds)
        _write_artifacts(args.output_root, args, report, records)
        return report
    except Exception:
        if not setup_complete:
            _write_setup_failure_artifacts(args.output_root, args)
        raise
    finally:
        await asyncio.gather(*(provider.close() for provider in providers.values()), return_exceptions=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    validate = subcommands.add_parser("validate-corpus")
    validate.add_argument("--manifest", type=Path, required=True)
    run = subcommands.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--source-commit", required=True)
    run.add_argument("--source-state", required=True)
    run.add_argument("--agent-core-commit", required=True)
    run.add_argument("--environment-profile", required=True)
    run.add_argument("--rounds", type=int, required=True)
    args = parser.parse_args(argv)
    fixtures = load_fixture_manifest(args.manifest)
    if args.command == "validate-corpus":
        print(json.dumps({"fixtures": [fixture.fixture_id for fixture in fixtures]}))
        return 0
    if args.rounds not in (1, 5):
        raise ValueError("LVL10L_ROUNDS_INVALID")
    if any(not getattr(args, field).strip() for field in ("run_id", "source_commit", "source_state", "agent_core_commit", "environment_profile")):
        raise ValueError("LVL10L_PROVENANCE_INVALID")
    if args.output_root.exists():
        raise FileExistsError(args.output_root)
    with portalocker.Lock("/tmp/jiuwenswarm-lvl10-provider.lock", mode="a", timeout=0):
        args.output_root.mkdir(parents=True, exist_ok=False)
        copied_manifest = args.output_root / "manifest.json"
        copied_manifest.write_bytes(args.manifest.read_bytes())
        run_payload = {
            "schema_version": "live-voice.lvl10l-run.v1",
            "run_id": args.run_id,
            "source_commit": args.source_commit,
            "source_state": args.source_state,
            "agent_core_commit": args.agent_core_commit,
            "environment_profile": args.environment_profile,
            "utc_started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "runtime": {
                "python_implementation": platform.python_implementation(),
                "python_version": platform.python_version(),
            },
            "corpus_sha256": _file_sha256(copied_manifest),
            "rounds": args.rounds,
            "expected_requests": args.rounds * len(FIXTURE_IDS) * 8,
            "request_budget": "24" if args.rounds == 1 else "120",
            "max_active_requests": MAX_ACTIVE_REQUESTS,
            "automatic_retries": 0,
            "provider_lock": "/tmp/jiuwenswarm-lvl10-provider.lock",
            "clock": "time.monotonic_ns",
            "percentile_provenance": _percentile_provenance(args.rounds),
            "role_schedule": [
                [role.value, fixture]
                for round_index in range(args.rounds)
                for role, fixture in scheduled_cells(round_index)
            ],
            "frozen_gates": {
                "sample_rate_hz": SAMPLE_RATE_HZ,
                "reserve_samples": RESERVE_SAMPLES,
                "max_active_requests": MAX_ACTIVE_REQUESTS,
                "event_timeout_seconds": EVENT_TIMEOUT_SECONDS,
                "automatic_retries": 0,
            },
        }
        (args.output_root / "run.json").write_text(
            json.dumps(run_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        report = asyncio.run(run_population(args, fixtures))
    print(json.dumps({"run_id": args.run_id, "decision": report.decision}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
