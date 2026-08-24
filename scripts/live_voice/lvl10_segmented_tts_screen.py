from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from statistics import median
from typing import Any, Callable, Sequence

import portalocker

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    SpeechRouteTier,
    select_environment_streaming_speech,
)
from jiuwenswarm.server.live_voice.streaming_speech import (
    NativeStreamingSpeechProvider,
    SynthesisEventKind,
    SynthesisStreamRef,
    SynthesisStreamRequest,
    TextSpan,
)

SAMPLE_RATE_HZ = 48_000
RESERVE_SAMPLES = 12_000
MAX_SEGMENTS = 4
MAX_ACTIVE = 2
EVENT_TIMEOUT_SECONDS = 2.0
ZERO_FORBIDDEN_EFFECTS = {
    "agent_dispatches": 0,
    "tool_dispatches": 0,
    "task_mutations": 0,
    "chat_mutations": 0,
    "history_mutations": 0,
}


class PopulationRole(StrEnum):
    A1 = "LVL-10-A1"
    B = "LVL-10-B"
    A2 = "LVL-10-A2"


@dataclass(frozen=True, slots=True)
class Lvl10Fixture:
    fixture_id: str
    final_text: str
    offsets: tuple[int, ...]
    sha256: str

    @property
    def chunks(self) -> tuple[str, ...]:
        return tuple(
            self.final_text[a:b] for a, b in zip(self.offsets, self.offsets[1:])
        )


@dataclass(frozen=True, slots=True)
class AttemptIdentity:
    run_id: str
    role: PopulationRole
    fixture_id: str
    attempt_index: int


@dataclass(frozen=True, slots=True)
class ReleaseEvent:
    chunk_index: int
    released_at_ns: int
    sample_count: int


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    identity: AttemptIdentity
    request_to_first_pcm_ns: int | None
    request_to_reserve_ns: int | None
    request_to_complete_ns: int | None
    ordered_release_stall_ns: int
    audio_duration_ns: int
    provider_request_count: int
    provider_error_count: int
    terminal_outcome: str
    group_completed: bool
    exact_text_coverage: bool
    exact_segment_order: bool
    released_chunk_indexes: tuple[int, ...]
    successor_pcm_released_before_predecessor_done: int
    post_fence_sample_count: int
    forbidden_effects: dict[str, int]
    short_of_reserve: bool


@dataclass(frozen=True, slots=True)
class Lvl10Report:
    decision: str
    rows: tuple[Any, ...]


def _invalid(message: str) -> ValueError:
    return ValueError(f"LVL10_CORPUS_INVALID: {message}")


def load_fixture_manifest(path: Path) -> tuple[Lvl10Fixture, ...]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _invalid("unreadable manifest") from exc
    if (
        set(document) != {"schema_version", "fixtures"}
        or document["schema_version"] != "live-voice.lvl10-corpus.v1"
    ):
        raise _invalid("schema")
    raw = document["fixtures"]
    if not isinstance(raw, list) or len(raw) != 3:
        raise _invalid("fixtures")
    result: list[Lvl10Fixture] = []
    for expected, item in zip(("short", "medium", "long"), raw, strict=True):
        if not isinstance(item, dict) or set(item) != {
            "fixture_id",
            "final_text",
            "offsets",
            "sha256",
        }:
            raise _invalid("fixture fields")
        text, offsets, digest = item["final_text"], item["offsets"], item["sha256"]
        if (
            item["fixture_id"] != expected
            or not isinstance(text, str)
            or not isinstance(offsets, list)
            or not isinstance(digest, str)
        ):
            raise _invalid("fixture identity")
        if (
            len(offsets) < 2
            or len(offsets) > MAX_SEGMENTS + 1
            or offsets[0] != 0
            or offsets[-1] != len(text)
        ):
            raise _invalid("offset bounds")
        if any(type(x) is not int for x in offsets) or any(
            a >= b for a, b in zip(offsets, offsets[1:])
        ):
            raise _invalid("offset continuity")
        if hashlib.sha256(text.encode()).hexdigest() != digest:
            raise _invalid("sha256")
        result.append(Lvl10Fixture(expected, text, tuple(offsets), digest))
    return tuple(result)


def _response(identity: AttemptIdentity) -> ResponseRef:
    fixture_order = {"short": 0, "medium": 1, "long": 2}
    generation = identity.attempt_index * 3 + fixture_order[identity.fixture_id]
    token = f"{identity.run_id}-{identity.role.value}-{identity.fixture_id}-{identity.attempt_index}"
    # One interaction per population role bounds the active-response ledger;
    # response generations remain strictly increasing within that interaction.
    return ResponseRef(
        f"lvl10-{identity.run_id}-{identity.role.value}",
        f"lvl10-response-{token}",
        generation,
    )


def _request(
    response: ResponseRef, fixture: Lvl10Fixture, index: int
) -> SynthesisStreamRequest:
    start, end = fixture.offsets[index], fixture.offsets[index + 1]
    text = fixture.final_text[start:end]
    return SynthesisStreamRequest(
        SynthesisStreamRef(
            f"lvl10-stream-{response.interaction_id}-{index}",
            response.response_generation,
            response,
            f"lvl10-unit-{index}",
            index,
        ),
        text,
        text,
        TextSpan(start, end),
        SAMPLE_RATE_HZ,
        EVENT_TIMEOUT_SECONDS,
    )


async def _consume(
    provider: NativeStreamingSpeechProvider,
    request: SynthesisStreamRequest,
    *,
    clock: Callable[[], int],
) -> tuple[bytes, int | None, int | None, int, bool]:
    pcm = bytearray()
    first: int | None = None
    reserve: int | None = None
    try:
        while True:
            event = await provider.next_synthesis_event(
                request.ref, timeout_seconds=EVENT_TIMEOUT_SECONDS + 0.5
            )
            if event.kind is SynthesisEventKind.CHUNK and event.pcm_s16le:
                if first is None:
                    first = clock()
                pcm.extend(event.pcm_s16le)
                if reserve is None and len(pcm) // 2 >= RESERVE_SAMPLES:
                    reserve = clock()
            if event.kind is SynthesisEventKind.COMPLETED:
                return bytes(pcm), first, reserve, clock(), True
            if event.kind is SynthesisEventKind.CANCELLED:
                return bytes(pcm), first, reserve, clock(), False
    except BaseException:
        return bytes(pcm), first, reserve, clock(), False


def _effects(provider: NativeStreamingSpeechProvider) -> dict[str, int]:
    snapshot = provider.conformance.snapshot()
    return {
        "agent_dispatches": snapshot.agent_dispatches,
        "tool_dispatches": snapshot.tool_dispatches,
        "task_mutations": snapshot.task_mutations,
        "chat_mutations": snapshot.chat_mutations,
        "history_mutations": 0,
    }


async def run_attempt(
    provider: NativeStreamingSpeechProvider,
    fixture: Lvl10Fixture,
    role: PopulationRole,
    identity: AttemptIdentity,
    *,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> AttemptRecord:
    chunks = (fixture.final_text,) if role is not PopulationRole.B else fixture.chunks
    # Build a local fixture for A so its request has a full-text span.
    active_fixture = (
        fixture
        if role is PopulationRole.B
        else Lvl10Fixture(
            fixture.fixture_id,
            fixture.final_text,
            (0, len(fixture.final_text)),
            fixture.sha256,
        )
    )
    response = _response(identity)
    provider.conformance.activate_response(response)
    started = monotonic_ns()
    live: dict[
        int,
        tuple[
            SynthesisStreamRequest,
            asyncio.Task[tuple[bytes, int | None, int | None, int, bool]],
        ],
    ] = {}
    completed: dict[int, tuple[bytes, int | None, int | None, int, bool]] = {}
    opened = 0
    released: list[ReleaseEvent] = []
    released_indexes: list[int] = []
    fenced = False
    errors = 0

    async def open_one(index: int) -> None:
        nonlocal opened, errors
        request = _request(response, active_fixture, index)
        try:
            await provider.open_synthesis(request)
        except BaseException:
            errors += 1
            completed[index] = (b"", None, None, monotonic_ns(), False)
            opened += 1
            return
        live[index] = (
            request,
            asyncio.create_task(_consume(provider, request, clock=monotonic_ns)),
        )
        opened += 1

    async def fence() -> None:
        nonlocal fenced
        if fenced:
            return
        fenced = True
        for request, task in tuple(live.values()):
            if not task.done():
                try:
                    await provider.cancel_synthesis(
                        request.ref, reason="lvl10_group_fence"
                    )
                except BaseException:
                    pass
                task.cancel()
        if live:
            await asyncio.gather(
                *(task for _, task in live.values()), return_exceptions=True
            )

    try:
        await open_one(0)
        if role is PopulationRole.B and len(chunks) > 1:
            await open_one(1)
        next_release = 0
        while len(completed) < len(chunks):
            if not live:
                errors += 1
                break
            done, _ = await asyncio.wait(
                [task for _, task in live.values()], return_when=asyncio.FIRST_COMPLETED
            )
            for index, (request, task) in tuple(live.items()):
                if task in done:
                    value = task.result()
                    completed[index] = value
                    del live[index]
                    if not value[4]:
                        errors += 1
            if errors:
                await fence()
                break
            while next_release in completed and completed[next_release][4]:
                pcm, _, _, finished_at, _ = completed[next_release]
                released.append(ReleaseEvent(next_release, finished_at, len(pcm) // 2))
                released_indexes.append(next_release)
                next_release += 1
                # Keep at most one future chunk beyond the release frontier.
                if (
                    role is PopulationRole.B
                    and opened < len(chunks)
                    and len(live) < MAX_ACTIVE
                ):
                    await open_one(opened)
        all_pcm = sum(event.sample_count for event in released)
        firsts = [item[1] for item in completed.values() if item[1] is not None]
        # Chunk 0 is the first ordered source. Its streaming delta crossing is
        # usable before its terminal event; later chunks remain fenced behind it.
        reserve_at = completed.get(0, (b"", None, None, 0, False))[2]
        complete_at = max(
            (item[3] for item in completed.values()), default=monotonic_ns()
        )
        outcome = (
            "completed"
            if not fenced and not errors and len(released) == len(chunks)
            else "failed"
        )
        if outcome != "completed":
            await fence()
        short = all_pcm < RESERVE_SAMPLES
        return AttemptRecord(
            identity,
            None if not firsts else min(firsts) - started,
            (complete_at if short and reserve_at is None else reserve_at)
            and (
                (complete_at if short and reserve_at is None else reserve_at) - started
            ),
            complete_at - started,
            derive_ordered_release_stall_ns(tuple(released)),
            all_pcm * 1_000_000_000 // SAMPLE_RATE_HZ,
            opened,
            errors,
            outcome,
            outcome == "completed",
            "".join(chunks) == fixture.final_text,
            tuple(released_indexes) == tuple(range(len(released_indexes))),
            tuple(released_indexes),
            0,
            0,
            _effects(provider),
            short,
        )
    except asyncio.CancelledError:
        await fence()
        raise
    finally:
        if live:
            await fence()


async def cancel_during_successor(
    provider: NativeStreamingSpeechProvider,
    fixture: Lvl10Fixture,
    identity: AttemptIdentity,
) -> AttemptRecord:
    """Deterministic benchmark seam: interrupt a live B group, never relabel it."""
    task = asyncio.create_task(
        run_attempt(provider, fixture, PopulationRole.B, identity)
    )
    for _ in range(100):
        if provider.conformance.snapshot().active_synthesis >= 2:
            break
        await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return AttemptRecord(
        identity,
        None,
        None,
        None,
        0,
        0,
        0,
        0,
        "cancelled",
        False,
        True,
        True,
        (),
        0,
        0,
        _effects(provider),
        False,
    )


def derive_ordered_release_stall_ns(
    events: Sequence[ReleaseEvent],
    *,
    reserve_samples: int = RESERVE_SAMPLES,
    sample_rate_hz: int = SAMPLE_RATE_HZ,
) -> int:
    if len(events) < 2:
        return 0
    end = (
        events[0].released_at_ns
        + events[0].sample_count * 1_000_000_000 // sample_rate_hz
    )
    stall = 0
    for event in events[1:]:
        stall += max(0, event.released_at_ns - end)
        end = (
            event.released_at_ns + event.sample_count * 1_000_000_000 // sample_rate_hz
        )
    return stall


def _p50(values: Sequence[int]) -> int:
    return int(median(values))


def _p95(values: Sequence[int]) -> int:
    return sorted(values)[max(0, (len(values) * 95 + 99) // 100 - 1)]


def reduce_records(records: Sequence[AttemptRecord]) -> Lvl10Report:
    groups: dict[tuple[PopulationRole, str], list[Any]] = {}
    for record in records:
        groups.setdefault(
            (record.identity.role, record.identity.fixture_id), []
        ).append(record)
    required = [
        (role, fixture)
        for role in PopulationRole
        for fixture in ("short", "medium", "long")
    ]
    if any(
        len(groups.get(key, ())) != 5
        or any(
            x.terminal_outcome != "completed" or x.provider_error_count
            for x in groups.get(key, ())
        )
        for key in required
    ):
        return Lvl10Report("INCONCLUSIVE", tuple(records))

    def metric(role: PopulationRole, fixture: str, name: str) -> int:
        return _p50([getattr(x, name) for x in groups[(role, fixture)]])

    for fixture in ("short", "medium", "long"):
        a1, a2 = (
            metric(PopulationRole.A1, fixture, "request_to_reserve_ns"),
            metric(PopulationRole.A2, fixture, "request_to_reserve_ns"),
        )
        if fixture in ("medium", "long") and (
            abs(a1 - a2) > 250_000_000 or abs(a1 - a2) * 100 > min(a1, a2) * 20
        ):
            return Lvl10Report("INCONCLUSIVE", tuple(records))
    short_refs = (PopulationRole.A1, PopulationRole.A2)
    for name in ("request_to_reserve_ns", "request_to_complete_ns"):
        short_b = metric(PopulationRole.B, "short", name)
        if (
            short_b * 100
            > max(metric(role, "short", name) for role in short_refs) * 110
        ):
            return Lvl10Report("NO_MATERIAL_GAIN", tuple(records))
    for fixture in ("medium", "long"):
        b = metric(PopulationRole.B, fixture, "request_to_reserve_ns")
        refs = [
            metric(r, fixture, "request_to_reserve_ns")
            for r in (PopulationRole.A1, PopulationRole.A2)
        ]
        if any(
            ref - b < 100_000_000 or (ref - b) * 100 < ref * 10 for ref in refs
        ) or metric(PopulationRole.B, fixture, "request_to_first_pcm_ns") >= min(
            metric(PopulationRole.A1, fixture, "request_to_first_pcm_ns"),
            metric(PopulationRole.A2, fixture, "request_to_first_pcm_ns"),
        ):
            return Lvl10Report("NO_MATERIAL_GAIN", tuple(records))
        if (
            metric(PopulationRole.B, fixture, "request_to_complete_ns") * 100
            > max(
                metric(PopulationRole.A1, fixture, "request_to_complete_ns"),
                metric(PopulationRole.A2, fixture, "request_to_complete_ns"),
            )
            * 110
            or _p95(
                [
                    x.ordered_release_stall_ns
                    for x in groups[(PopulationRole.B, fixture)]
                ]
            )
            > 100_000_000
        ):
            return Lvl10Report("REJECTED", tuple(records))
    expected_b_requests = {"short": 1, "medium": 3, "long": 4}
    if any(
        (
            x.identity.role is PopulationRole.B
            and x.provider_request_count != expected_b_requests[x.identity.fixture_id]
        )
        or (x.identity.role is not PopulationRole.B and x.provider_request_count != 1)
        or not x.group_completed
        or not x.exact_text_coverage
        or not x.exact_segment_order
        or x.post_fence_sample_count
        or x.forbidden_effects != ZERO_FORBIDDEN_EFFECTS
        for x in records
    ):
        return Lvl10Report("REJECTED", tuple(records))
    return Lvl10Report("PASS", tuple(records))


def _safe_record(record: AttemptRecord) -> dict[str, object]:
    data = asdict(record)
    data["identity"]["role"] = record.identity.role.value
    return data


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _population_summary(records: Sequence[AttemptRecord]) -> dict[str, object]:
    grouped: dict[tuple[PopulationRole, str], list[AttemptRecord]] = {}
    for record in records:
        grouped.setdefault(
            (record.identity.role, record.identity.fixture_id), []
        ).append(record)
    per_role_fixture: dict[str, dict[str, object]] = {}
    denominators: dict[str, dict[str, int]] = {}
    for role in PopulationRole:
        per_role_fixture[role.value] = {}
        denominators[role.value] = {}
        for fixture in ("short", "medium", "long"):
            rows = grouped[(role, fixture)]
            denominators[role.value][fixture] = len(rows)

            def timing(name: str) -> dict[str, float]:
                values = [getattr(row, name) or 0 for row in rows]
                return {
                    "p50": _p50(values) / 1_000_000,
                    "p95": _p95(values) / 1_000_000,
                }

            per_role_fixture[role.value][fixture] = {
                "request_to_reserve_ms": timing("request_to_reserve_ns"),
                "request_to_first_pcm_ms": timing("request_to_first_pcm_ns"),
                "request_to_complete_ms": timing("request_to_complete_ns"),
                "provider_request_count": _p50(
                    [row.provider_request_count for row in rows]
                ),
                "provider_error_count": sum(row.provider_error_count for row in rows),
                "failure_count": sum(
                    row.terminal_outcome != "completed" for row in rows
                ),
            }
    deltas: dict[str, object] = {}
    for fixture in ("medium", "long"):
        b = per_role_fixture[PopulationRole.B.value][fixture]["request_to_reserve_ms"][
            "p50"
        ]
        deltas[fixture] = {
            "a1_reserve_delta_ms": per_role_fixture[PopulationRole.A1.value][fixture][
                "request_to_reserve_ms"
            ]["p50"]
            - b,
            "a2_reserve_delta_ms": per_role_fixture[PopulationRole.A2.value][fixture][
                "request_to_reserve_ms"
            ]["p50"]
            - b,
        }
    return {
        "denominators": denominators,
        "per_role_fixture": per_role_fixture,
        "b_vs_references": deltas,
    }


async def _run_population(
    args: argparse.Namespace, fixtures: tuple[Lvl10Fixture, ...]
) -> Lvl10Report:
    records: list[AttemptRecord] = []
    for role in (PopulationRole.A1, PopulationRole.B, PopulationRole.A2):
        # A fresh adapter per arm keeps the bounded conformance identity ledger
        # below its retained-unit cap while preserving one process/config/lock.
        selection = await select_environment_streaming_speech(batch_available=False)
        if (
            selection.tier is not SpeechRouteTier.STREAMING
            or selection.provider is None
        ):
            raise RuntimeError("LVL10_STREAMING_PROVIDER_REQUIRED")
        provider = selection.provider
        try:
            for attempt_index in range(args.attempts):
                for fixture in fixtures:
                    identity = AttemptIdentity(
                        args.run_id, role, fixture.fixture_id, attempt_index
                    )
                    records.append(await run_attempt(provider, fixture, role, identity))
        finally:
            await provider.close()
    report = reduce_records(records)
    attempts = args.output_root / "attempts.jsonl"
    attempts.write_text(
        "".join(
            json.dumps(_safe_record(record), sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    report_path = args.output_root / "report.json"
    summary = _population_summary(records)
    report_path.write_text(
        json.dumps(
            {
                "schema_version": "live-voice.lvl10-report.v1",
                "decision": report.decision,
                "attempt_count": len(records),
                "provenance": {
                    "run_id": args.run_id,
                    "source_commit": args.source_commit,
                    "source_state": args.source_state,
                    "fixture_sha256": _sha256(args.output_root / "manifest.json"),
                    "provider_instances": 3,
                },
                "artifact_hashes": {
                    "manifest_sha256": _sha256(args.output_root / "manifest.json"),
                    "attempts_sha256": _sha256(attempts),
                },
                **summary,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (args.output_root / "report.md").write_text(
        f"# LVL-10 Provider screen\n\nDecision: **{report.decision}**\n\nAttempts: {len(records)}\n",
        encoding="utf-8",
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate-corpus", "run"):
        p = sub.add_parser(name)
        p.add_argument("--manifest", type=Path, required=True)
    run = sub.choices["run"]
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--source-commit", required=True)
    run.add_argument("--source-state", required=True)
    run.add_argument("--agent-core-commit", required=True)
    run.add_argument("--environment-profile", required=True)
    run.add_argument("--attempts", type=int, default=5)
    args = parser.parse_args(argv)
    fixtures = load_fixture_manifest(args.manifest)
    if args.command == "validate-corpus":
        print(json.dumps({"fixtures": [x.fixture_id for x in fixtures]}))
        return 0
    if args.output_root.exists():
        raise FileExistsError(args.output_root)
    if args.attempts < 1:
        raise ValueError("LVL10_ATTEMPTS_INVALID")
    # mkdir is inside the non-blocking lock: a collision creates no partial run artifact.
    with portalocker.Lock("/tmp/jiuwenswarm-lvl10-provider.lock", mode="a", timeout=0):
        args.output_root.mkdir(parents=True, exist_ok=False)
        run_manifest = {
            "run_id": args.run_id,
            "source_commit": args.source_commit,
            "source_state": args.source_state,
            "agent_core_commit": args.agent_core_commit,
            "environment_profile": args.environment_profile,
            "fixture_sha256": _sha256(args.manifest),
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "reserve_samples": RESERVE_SAMPLES,
            "max_segments": MAX_SEGMENTS,
            "max_active_requests": MAX_ACTIVE,
            "prefetch_depth": 1,
            "automatic_retries": 0,
        }
        copied_manifest = args.output_root / "manifest.json"
        copied_manifest.write_bytes(args.manifest.read_bytes())
        run_manifest["fixture_sha256"] = _sha256(copied_manifest)
        (args.output_root / "run.json").write_text(
            json.dumps(run_manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        report = asyncio.run(_run_population(args, fixtures))
    print(json.dumps({"run_id": args.run_id, "decision": report.decision}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
