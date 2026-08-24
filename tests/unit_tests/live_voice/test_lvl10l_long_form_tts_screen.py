from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    OpenAIStreamingSpeechConfig,
    OpenAIStreamingSpeechProvider,
)


ROOT = Path(__file__).parents[3]
MANIFEST_PATH = ROOT / "tests/fixtures/live_voice_lvl10l_tts_v1/manifest.json"
RUNNER_PATH = ROOT / "scripts/live_voice/lvl10l_long_form_tts_screen.py"


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("lvl10l_long_form_tts_screen", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()
PopulationRole = runner.PopulationRole
load_fixture_manifest = runner.load_fixture_manifest
AttemptIdentity = runner.AttemptIdentity
run_attempt = runner.run_attempt
scheduled_cells = runner.scheduled_cells
interpolate_reference = runner.interpolate_reference
reduce_records = runner.reduce_records
main = runner.main
run_population = runner.run_population


def _mutated_manifest(tmp_path: Path, mutation: str) -> Path:
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixture = document["fixtures"][1]
    if mutation == "hash":
        fixture["sha256"] = "0" * 64
    elif mutation == "overlap":
        fixture["b2_offsets"] = [0, 800, 1422]
    elif mutation == "gap":
        fixture["b4_offsets"] = [0, 356, 900, 1068, 1422]
    elif mutation == "inside_unit":
        fixture["b2_offsets"] = [0, 700, 1422]
    elif mutation == "not_nested":
        document["fixtures"][2]["final_text"] = fixture["final_text"] + "changed"
    elif mutation == "unknown_field":
        fixture["forbidden"] = True
    else:
        raise AssertionError(mutation)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_manifest_is_nested_and_preserves_exact_b2_b4_coverage() -> None:
    fixtures = load_fixture_manifest(MANIFEST_PATH)
    assert [row.fixture_id for row in fixtures] == ["long_600", "long_1200", "long_2400"]
    assert [len(row.chunks_for(PopulationRole.B2)) for row in fixtures] == [2, 2, 2]
    assert [len(row.chunks_for(PopulationRole.B4)) for row in fixtures] == [4, 4, 4]
    assert fixtures[1].final_text.startswith(fixtures[0].final_text)
    assert fixtures[2].final_text.startswith(fixtures[1].final_text)
    assert all("".join(row.chunks_for(PopulationRole.B4)) == row.final_text for row in fixtures)


@pytest.mark.parametrize(
    "mutation", ["hash", "overlap", "gap", "inside_unit", "not_nested", "unknown_field"]
)
def test_manifest_rejects_every_frozen_contract_violation(tmp_path: Path, mutation: str) -> None:
    with pytest.raises(ValueError, match="LVL10L_CORPUS_INVALID"):
        load_fixture_manifest(_mutated_manifest(tmp_path, mutation))


ZERO_FORBIDDEN_EFFECTS = {
    "agent_dispatches": 0,
    "tool_dispatches": 0,
    "task_mutations": 0,
    "chat_mutations": 0,
    "history_mutations": 0,
}


class _Conformance:
    def __init__(self) -> None:
        self.responses: list[Any] = []

    def activate_response(self, response: Any) -> None:
        self.responses.append(response)

    def snapshot(self) -> Any:
        return SimpleNamespace(**ZERO_FORBIDDEN_EFFECTS)


class ScriptedProvider:
    """Deterministic port fake: it never opens a network connection."""

    def __init__(self, *, successor_pcm_first: bool = False, fail_index: int | None = None) -> None:
        self.conformance = _Conformance()
        self.inputs: list[str] = []
        self.requests: list[Any] = []
        self.active = 0
        self.max_active = 0
        self.successor_pcm_first = successor_pcm_first
        self.fail_index = fail_index
        self.events: dict[str, list[Any]] = {}
        self.cancelled: list[str] = []
        self.closed = False

    async def open_synthesis(self, request: Any) -> None:
        index = len(self.inputs)
        self.inputs.append(request.spoken_text)
        self.requests.append(request)
        if self.fail_index == index:
            raise ConnectionError("scripted-open-failure")
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.events[request.ref.stream_id] = [
            SimpleNamespace(kind="chunk", pcm_s16le=b"\x00\x00" * 12_000),
            SimpleNamespace(kind="completed", pcm_s16le=None),
        ]

    async def next_synthesis_event(self, ref: Any, *, timeout_seconds: float) -> Any:
        assert timeout_seconds >= 15
        index = next(item.ref.unit_seq for item in self.requests if item.ref == ref)
        if self.successor_pcm_first and index == 0 and self.events[ref.stream_id][0].kind == "chunk":
            await __import__("asyncio").sleep(0)
        event = self.events[ref.stream_id].pop(0)
        if event.kind == "completed":
            self.active -= 1
        return event

    async def cancel_synthesis(self, ref: Any, *, reason: str) -> None:
        self.cancelled.append(ref.stream_id)
        self.events[ref.stream_id] = [SimpleNamespace(kind="cancelled", pcm_s16le=None)]

    async def close(self) -> None:
        self.closed = True


class MidStreamFailureProvider(ScriptedProvider):
    async def next_synthesis_event(self, ref: Any, *, timeout_seconds: float) -> Any:
        request = next(item for item in self.requests if item.ref == ref)
        if request.ref.unit_seq == 1:
            raise TimeoutError("scripted-idle-timeout")
        return await super().next_synthesis_event(ref, timeout_seconds=timeout_seconds)


class BlockingProvider(ScriptedProvider):
    def __init__(self) -> None:
        super().__init__()
        self.blocked = __import__("asyncio").Event()

    async def next_synthesis_event(self, ref: Any, *, timeout_seconds: float) -> Any:
        await self.blocked.wait()
        return await super().next_synthesis_event(ref, timeout_seconds=timeout_seconds)


class BufferedSuccessorProvider(ScriptedProvider):
    def __init__(self) -> None:
        super().__init__()
        self.predecessor_blocked = __import__("asyncio").Event()

    async def next_synthesis_event(self, ref: Any, *, timeout_seconds: float) -> Any:
        request = next(item for item in self.requests if item.ref == ref)
        if request.ref.unit_seq == 0:
            await self.predecessor_blocked.wait()
        return await super().next_synthesis_event(ref, timeout_seconds=timeout_seconds)


class CancelledProvider(ScriptedProvider):
    async def next_synthesis_event(self, ref: Any, *, timeout_seconds: float) -> Any:
        return SimpleNamespace(kind="cancelled", pcm_s16le=None)


def _identity(role: Any, fixture_id: str, round_index: int = 0) -> Any:
    return AttemptIdentity("unit-run", role, fixture_id, round_index)


async def _scripted_attempt(role: Any, *, successor_pcm_first: bool = False) -> tuple[Any, ScriptedProvider, Any]:
    fixture = load_fixture_manifest(MANIFEST_PATH)[1]
    provider = ScriptedProvider(successor_pcm_first=successor_pcm_first)
    record = await run_attempt(provider, fixture, _identity(role, fixture.fixture_id))
    return record, provider, fixture


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "expected"),
    ((PopulationRole.A1, 1), (PopulationRole.B2, 2), (PopulationRole.B4, 4), (PopulationRole.A2, 1)),
)
async def test_roles_open_exact_requests_and_cover_text(role: Any, expected: int) -> None:
    record, provider, fixture = await _scripted_attempt(role)
    assert record.provider_request_count == expected
    assert "".join(provider.inputs) == fixture.final_text
    assert provider.max_active <= 2
    assert record.released_chunk_indexes == tuple(range(expected))
    assert record.forbidden_effects == ZERO_FORBIDDEN_EFFECTS


@pytest.mark.asyncio
async def test_first_pcm_credits_chunk_zero_not_early_successor() -> None:
    record, _provider, _fixture = await _scripted_attempt(
        PopulationRole.B2, successor_pcm_first=True
    )
    assert record.request_to_any_chunk_pcm_ns < record.request_to_first_pcm_ns
    assert record.chunk_timelines[0].first_pcm_ns - record.started_ns == record.request_to_first_pcm_ns


@pytest.mark.asyncio
async def test_rotated_fixture_order_never_creates_stale_generation() -> None:
    provider = ScriptedProvider()
    fixtures = load_fixture_manifest(MANIFEST_PATH)
    for fixture in (fixtures[2], fixtures[0], fixtures[1]):
        record = await run_attempt(provider, fixture, _identity(PopulationRole.A1, fixture.fixture_id, 3))
        assert record.group_completed


@pytest.mark.asyncio
async def test_open_failure_fences_whole_group_with_zero_post_fence_samples() -> None:
    fixture = load_fixture_manifest(MANIFEST_PATH)[1]
    provider = ScriptedProvider(fail_index=1)
    record = await run_attempt(provider, fixture, _identity(PopulationRole.B2, fixture.fixture_id))
    assert record.terminal_outcome == "failed"
    assert record.group_completed is False
    assert record.post_fence_sample_count == 0
    assert record.forbidden_effects == ZERO_FORBIDDEN_EFFECTS


@pytest.mark.asyncio
async def test_mid_stream_failure_fences_successor_without_false_completion() -> None:
    fixture = load_fixture_manifest(MANIFEST_PATH)[1]
    provider = MidStreamFailureProvider()
    record = await run_attempt(provider, fixture, _identity(PopulationRole.B2, fixture.fixture_id))
    assert record.terminal_outcome == "failed"
    assert record.group_completed is False
    assert record.post_fence_sample_count == 0
    assert record.forbidden_effects == ZERO_FORBIDDEN_EFFECTS


@pytest.mark.asyncio
async def test_caller_cancellation_fences_every_live_chunk() -> None:
    fixture = load_fixture_manifest(MANIFEST_PATH)[1]
    provider = BlockingProvider()
    task = __import__("asyncio").create_task(
        run_attempt(provider, fixture, _identity(PopulationRole.B2, fixture.fixture_id))
    )
    while len(provider.inputs) < 2:
        await __import__("asyncio").sleep(0)
    task.cancel()
    record = await task
    assert record.terminal_outcome == "cancelled"
    assert record.group_completed is False
    assert record.post_fence_sample_count == 0
    assert record.forbidden_effects == ZERO_FORBIDDEN_EFFECTS


@pytest.mark.asyncio
async def test_provider_cancelled_event_fences_buffered_successor_with_reason_code() -> None:
    fixture = load_fixture_manifest(MANIFEST_PATH)[1]
    record = await run_attempt(CancelledProvider(), fixture, _identity(PopulationRole.B2, fixture.fixture_id))
    assert record.terminal_outcome == "failed"
    assert record.terminal_reason == "group_fenced"
    assert record.chunk_timelines[0].terminal_reason.startswith("group_fenced:")


def _roles_for(cells: tuple[tuple[Any, str], ...], fixture_id: str) -> list[Any]:
    return [role for role, fixture in cells if fixture == fixture_id]


def _fixture_order(cells: tuple[tuple[Any, str], ...]) -> list[str]:
    return list(dict.fromkeys(fixture for _role, fixture in cells))


def test_schedule_rotates_fixtures_and_alternates_candidates() -> None:
    assert _roles_for(scheduled_cells(0), "long_600") == [
        PopulationRole.A1,
        PopulationRole.B2,
        PopulationRole.B4,
        PopulationRole.A2,
    ]
    assert _roles_for(scheduled_cells(1), "long_1200") == [
        PopulationRole.A1,
        PopulationRole.B4,
        PopulationRole.B2,
        PopulationRole.A2,
    ]
    assert _fixture_order(scheduled_cells(2)) == ["long_2400", "long_600", "long_1200"]


def _reduction_record(
    role: Any,
    fixture_id: str,
    round_index: int,
    *,
    started_ms: int,
    complete_ms: int,
    first_pcm_ms: int = 100,
    reserve_ms: int = 250,
    sample_count: int = 48_000,
    requests: int | None = None,
) -> Any:
    expected = {PopulationRole.A1: 1, PopulationRole.B2: 2, PopulationRole.B4: 4, PopulationRole.A2: 1}[role]
    return SimpleNamespace(
        identity=_identity(role, fixture_id, round_index),
        started_ns=started_ms * 1_000_000,
        request_to_complete_ns=complete_ms * 1_000_000,
        request_to_first_pcm_ns=first_pcm_ms * 1_000_000,
        request_to_reserve_ns=reserve_ms * 1_000_000,
        audio_duration_ns=sample_count * 1_000_000_000 // 48_000,
        provider_request_count=expected if requests is None else requests,
        provider_error_count=0,
        terminal_outcome="completed",
        group_completed=True,
        exact_text_coverage=True,
        released_chunk_indexes=tuple(range(expected)),
        post_fence_sample_count=0,
        forbidden_effects=ZERO_FORBIDDEN_EFFECTS,
        whole_chunk_availability_gap_ns=999_000_000,
    )


def _formal_population() -> list[Any]:
    records: list[Any] = []
    for round_index in range(10):
        for fixture_id in ("long_600", "long_1200", "long_2400"):
            records.extend(
                (
                    _reduction_record(PopulationRole.A1, fixture_id, round_index, started_ms=0, complete_ms=2_000),
                    _reduction_record(PopulationRole.B2, fixture_id, round_index, started_ms=25, complete_ms=1_000),
                    _reduction_record(PopulationRole.B4, fixture_id, round_index, started_ms=50, complete_ms=1_550),
                    _reduction_record(PopulationRole.A2, fixture_id, round_index, started_ms=100, complete_ms=2_000),
                )
            )
    return records


def test_reference_is_interpolated_at_candidate_start() -> None:
    candidate = _reduction_record(PopulationRole.B2, "long_2400", 0, started_ms=25, complete_ms=0)
    a1 = _reduction_record(PopulationRole.A1, "long_2400", 0, started_ms=0, complete_ms=1_000)
    a2 = _reduction_record(PopulationRole.A2, "long_2400", 0, started_ms=100, complete_ms=2_000)
    assert interpolate_reference(candidate, a1, a2, "request_to_complete_ns") == 1_250_000_000


def test_reducer_declares_b2_material_and_keeps_whole_chunk_diagnostic_non_gating() -> None:
    report = reduce_records(_formal_population(), expected_rounds=10)
    assert report.decision == "B2_MATERIAL"
    assert any("whole_chunk_availability" in reason for reason in report.gate_reasons)


def test_reducer_rejects_wrong_request_count_and_marks_missing_control_inconclusive() -> None:
    rejected = _formal_population()
    rejected[1].provider_request_count = 3
    assert reduce_records(rejected, expected_rounds=10).decision == "REJECTED"
    incomplete = _formal_population()[1:]
    assert reduce_records(incomplete, expected_rounds=10).decision == "INCONCLUSIVE"


def test_cli_rejects_non_pilot_non_formal_round_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="LVL10L_ROUNDS_INVALID"):
        main(
            [
                "run", "--manifest", str(MANIFEST_PATH), "--output-root", str(tmp_path / "run"),
                "--run-id", "unit-run", "--source-commit", "a" * 40,
                "--source-state", "clean", "--agent-core-commit", "b" * 40, "--environment-profile", "test", "--rounds", "2",
            ]
        )


def test_cli_writes_immutable_sanitized_artifacts_without_real_provider_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    providers: list[ScriptedProvider] = []

    async def select_fake_provider(*, batch_available: bool) -> Any:
        assert batch_available is False
        provider = ScriptedProvider()
        providers.append(provider)
        return SimpleNamespace(tier=runner.SpeechRouteTier.STREAMING, provider=provider)

    monkeypatch.setattr(runner, "select_environment_streaming_speech", select_fake_provider)
    output = tmp_path / "immutable-run"
    assert main(
        [
            "run", "--manifest", str(MANIFEST_PATH), "--output-root", str(output),
            "--run-id", "unit-run", "--source-commit", "a" * 40,
            "--source-state", "clean", "--agent-core-commit", "b" * 40, "--environment-profile", "test", "--rounds", "1",
        ]
    ) == 0
    assert len(providers) == 4
    assert all(len(provider.conformance.responses) == 3 for provider in providers)
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["expected_requests"] == report["observed_requests"] == 24
    assert report["artifact_hashes"]["manifest_sha256"]
    assert (output / "manifest.json").read_bytes() == MANIFEST_PATH.read_bytes()
    serialized = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.iterdir()
        if path.name != "manifest.json"
    )
    assert "A careful explanation helps" not in serialized
    assert "api_key" not in serialized


def test_exact_run_command_records_safe_complete_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def select_fake_provider(*, batch_available: bool) -> Any:
        return SimpleNamespace(tier=runner.SpeechRouteTier.STREAMING, provider=ScriptedProvider())

    monkeypatch.setattr(runner, "select_environment_streaming_speech", select_fake_provider)
    output = tmp_path / "exact-command"
    assert main([
        "run", "--manifest", str(MANIFEST_PATH), "--output-root", str(output),
        "--run-id", "unit-run", "--source-commit", "a" * 40, "--source-state", "clean",
        "--agent-core-commit", "b" * 40, "--environment-profile", "deterministic-test", "--rounds", "1",
    ]) == 0
    run = json.loads((output / "run.json").read_text(encoding="utf-8"))
    assert run["source_state"] == "clean"
    assert run["utc_started_at"].endswith("Z")
    assert run["role_schedule"] == [[role.value, fixture] for role, fixture in scheduled_cells(0)]
    assert run["frozen_gates"]["sample_rate_hz"] == 48_000
    assert "api_key" not in json.dumps(run)


def test_artifacts_pin_per_cell_metrics_paired_deltas_and_timeline_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def select_fake_provider(*, batch_available: bool) -> Any:
        return SimpleNamespace(tier=runner.SpeechRouteTier.STREAMING, provider=ScriptedProvider())

    monkeypatch.setattr(runner, "select_environment_streaming_speech", select_fake_provider)
    output = tmp_path / "artifact-shape"
    main([
        "run", "--manifest", str(MANIFEST_PATH), "--output-root", str(output),
        "--run-id", "unit-run", "--source-commit", "a" * 40, "--source-state", "clean",
        "--agent-core-commit", "b" * 40, "--environment-profile", "test", "--rounds", "1",
    ])
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["per_cell"]["LVL-10L-B4"]["long_2400"]["denominator"] == 1
    assert set(report["per_cell"]["LVL-10L-B4"]["long_2400"]["request_to_complete_ns"]) == {"p50", "p90", "p95"}
    assert report["paired_completion"]["LVL-10L-B2"]["long_2400"]["win_count"] in (0, 1)
    attempt = json.loads((output / "attempts.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert "terminal_reason" in attempt
    assert "whole_chunk_availability_gap_ns" in attempt
    assert set(attempt["chunk_timelines"][0]) >= {"opened_ns", "first_pcm_ns", "completed_ns", "released_ns", "terminal_outcome"}
    assert report["artifact_hashes"]["report_canonical_excludes"] == ["artifact_hashes.report_canonical_sha256"]


def test_existing_output_performs_zero_provider_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "already-there"
    output.mkdir()
    calls = 0

    async def select_fake_provider(*, batch_available: bool) -> Any:
        nonlocal calls
        calls += 1
        return SimpleNamespace(tier=runner.SpeechRouteTier.STREAMING, provider=ScriptedProvider())

    monkeypatch.setattr(runner, "select_environment_streaming_speech", select_fake_provider)
    with pytest.raises(FileExistsError):
        main([
            "run", "--manifest", str(MANIFEST_PATH), "--output-root", str(output),
            "--run-id", "unit-run", "--source-commit", "a" * 40, "--source-state", "clean",
            "--agent-core-commit", "b" * 40, "--environment-profile", "test", "--rounds", "1",
        ])
    assert calls == 0


def test_selection_failure_closes_already_created_adapters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = ScriptedProvider()
    calls = 0

    async def select_then_fail(*, batch_available: bool) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(tier=runner.SpeechRouteTier.STREAMING, provider=first)
        return SimpleNamespace(tier="fallback", provider=None)

    monkeypatch.setattr(runner, "select_environment_streaming_speech", select_then_fail)
    with pytest.raises(RuntimeError, match="LVL10L_STREAMING_PROVIDER_REQUIRED"):
        main([
            "run", "--manifest", str(MANIFEST_PATH), "--output-root", str(tmp_path / "selection-failure"),
            "--run-id", "unit-run", "--source-commit", "a" * 40, "--source-state", "clean",
            "--agent-core-commit", "b" * 40, "--environment-profile", "test", "--rounds", "1",
        ])
    assert first.closed is True
    output = tmp_path / "selection-failure"
    assert (output / "attempts.jsonl").read_text(encoding="utf-8") == ""
    terminal = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert terminal["decision"] == "INCONCLUSIVE"
    assert terminal["gate_reasons"] == ["provider_setup_failed"]
    assert "provider_setup_failed" in (output / "report.md").read_text(encoding="utf-8")


def test_shared_lock_collision_creates_no_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "locked-run"
    with runner.portalocker.Lock("/tmp/jiuwenswarm-lvl10-provider.lock", mode="a", timeout=0):
        with pytest.raises(Exception):
            main([
                "run", "--manifest", str(MANIFEST_PATH), "--output-root", str(output),
                "--run-id", "unit-run", "--source-commit", "a" * 40, "--source-state", "clean",
                "--agent-core-commit", "b" * 40, "--environment-profile", "test", "--rounds", "1",
            ])
    assert output.exists() is False


def test_failure_population_retains_denominator_and_writes_artifacts_without_timing_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def select_failing_provider(*, batch_available: bool) -> Any:
        return SimpleNamespace(tier=runner.SpeechRouteTier.STREAMING, provider=ScriptedProvider(fail_index=0))

    monkeypatch.setattr(runner, "select_environment_streaming_speech", select_failing_provider)
    output = tmp_path / "failed-run"
    assert main([
        "run", "--manifest", str(MANIFEST_PATH), "--output-root", str(output),
        "--run-id", "failed-run", "--source-commit", "a" * 40, "--source-state", "clean",
        "--agent-core-commit", "b" * 40, "--environment-profile", "test", "--rounds", "1",
    ]) == 0
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    cell = report["per_cell"][PopulationRole.A1.value]["long_600"]
    assert report["decision"] == "REJECTED"
    assert cell["measured_denominator"] == 0
    assert cell["provider_error_count"] == cell["failure_count"] == 1
    assert cell["request_to_first_pcm_ns"] == {"p50": None, "p90": None, "p95": None}
    assert (output / "attempts.jsonl").read_text(encoding="utf-8")
    assert "integrity_reliability" in (output / "report.md").read_text(encoding="utf-8")
    assert "| LVL-10L-B2 | long_600 | first_pcm_regression | 0 | — | — |" in (
        output / "report.md"
    ).read_text(encoding="utf-8")


def test_report_markdown_contains_required_timing_and_decision_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def select_fake_provider(*, batch_available: bool) -> Any:
        return SimpleNamespace(tier=runner.SpeechRouteTier.STREAMING, provider=ScriptedProvider())

    monkeypatch.setattr(runner, "select_environment_streaming_speech", select_fake_provider)
    output = tmp_path / "markdown-report"
    main([
        "run", "--manifest", str(MANIFEST_PATH), "--output-root", str(output),
        "--run-id", "markdown-run", "--source-commit", "a" * 40, "--source-state", "clean",
        "--agent-core-commit", "b" * 40, "--environment-profile", "test", "--rounds", "1",
    ])
    markdown = (output / "report.md").read_text(encoding="utf-8")
    for heading in (
        "## Per-role/fixture timings",
        "## Paired completion",
        "## Request and failure totals",
        "## Control drift",
        "Measured: Provider/source timings",
        "Derived: paired gains",
        "Browser and product latency are excluded",
    ):
        assert heading in markdown
    assert "LVL-10L-B2 | long_2400" in markdown
    assert "Selected arm:" in markdown
    assert "## Candidate first/reserve/duration decision inputs" in markdown
    assert "| LVL-10L-B2 | long_2400 | first_pcm_regression | 1 |" in markdown
    assert "| LVL-10L-B4 | long_1200 | audio_duration_delta | 1 |" in markdown


def test_artifacts_serialize_candidate_regressions_duration_parity_and_b4_increment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def select_fake_provider(*, batch_available: bool) -> Any:
        return SimpleNamespace(tier=runner.SpeechRouteTier.STREAMING, provider=ScriptedProvider())

    monkeypatch.setattr(runner, "select_environment_streaming_speech", select_fake_provider)
    output = tmp_path / "decision-inputs"
    main([
        "run", "--manifest", str(MANIFEST_PATH), "--output-root", str(output),
        "--run-id", "decision-run", "--source-commit", "a" * 40, "--source-state", "clean",
        "--agent-core-commit", "b" * 40, "--environment-profile", "test", "--rounds", "1",
    ])
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    inputs = report["candidate_decision_inputs"][PopulationRole.B2.value]["long_2400"]
    assert set(inputs) >= {"first_pcm_regression", "reserve_regression", "audio_duration_delta"}
    assert inputs["first_pcm_regression"]["measured_denominator"] == 1
    assert set(inputs["audio_duration_delta"]) >= {"p50_absolute_ns", "p50_percent", "measured_denominator"}
    assert set(report["b4_incremental_vs_b2"]) >= {"p50_gain_delta_ns", "p50_gain_delta_pct", "measured_denominator"}
    assert "B4 vs B2 incremental paired gain" in (output / "report.md").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_fence_terminalizes_buffered_successor_timelines_for_jsonl_without_post_fence_release() -> None:
    fixture = load_fixture_manifest(MANIFEST_PATH)[1]
    provider = BufferedSuccessorProvider()
    task = __import__("asyncio").create_task(
        run_attempt(provider, fixture, _identity(PopulationRole.B2, fixture.fixture_id))
    )
    while len(provider.inputs) < 2:
        await __import__("asyncio").sleep(0)
    while provider.active != 1:
        await __import__("asyncio").sleep(0)
    task.cancel()
    record = await task
    row = json.loads(json.dumps(runner._safe_record(record)))
    assert row["released_chunk_indexes"] == []
    assert all(chunk["terminal_outcome"] != "opened" for chunk in row["chunk_timelines"])
    assert row["chunk_timelines"][0]["terminal_reason"].startswith("group_fenced:")
    assert row["chunk_timelines"][1]["terminal_reason"].startswith("group_fenced:")


def test_non_monotonic_bucket_walk_is_recorded_after_2400_pass_and_1200_fail() -> None:
    records = _formal_population()
    for record in records:
        if record.identity.role is PopulationRole.B2:
            record.request_to_complete_ns = {
                "long_2400": 1_000_000_000,
                "long_1200": 1_900_000_000,
                "long_600": 1_000_000_000,
            }[record.identity.fixture_id]
        if record.identity.role is PopulationRole.B4:
            record.request_to_complete_ns = 2_000_000_000
    report = reduce_records(records, expected_rounds=10)
    assert report.smallest_break_even == "NON_MONOTONIC"
    assert "monotonic_bucket_walk:NON_MONOTONIC" in report.gate_reasons


@pytest.mark.asyncio
async def test_formal_b4_reuses_twelve_stream_identities_with_round_generations() -> None:
    provider = ScriptedProvider()
    fixtures = load_fixture_manifest(MANIFEST_PATH)
    for round_index in range(10):
        for fixture in fixtures:
            record = await run_attempt(
                provider,
                fixture,
                _identity(PopulationRole.B4, fixture.fixture_id, round_index),
            )
            assert record.group_completed
    requests = [request for request in provider.requests if request.ref.response.response_id.startswith("lvl10l-response-unit-run-LVL-10L-B4")]
    assert len(requests) == 120
    assert len({request.ref.stream_id for request in requests}) == 12
    assert {request.ref.stream_generation for request in requests} == set(range(10))


def test_pilot_requires_exact_authorization_predicate_not_formal_materiality() -> None:
    pilot = [record for record in _formal_population() if record.identity.round_index == 0]
    report = reduce_records(pilot, expected_rounds=1)
    assert report.decision == "PILOT_PASS"
    assert report.selected_arm == PopulationRole.B2.value


def test_pilot_fails_when_long_candidate_is_not_faster_than_both_controls() -> None:
    pilot = [record for record in _formal_population() if record.identity.round_index == 0]
    for record in pilot:
        if record.identity.fixture_id == "long_2400" and record.identity.role in (PopulationRole.B2, PopulationRole.B4):
            record.request_to_complete_ns = 2_000_000_000
    assert reduce_records(pilot, expected_rounds=1).decision == "PILOT_FAILED"


def test_monotonic_bucket_walk_and_b4_incremental_preference_are_reported() -> None:
    records = _formal_population()
    for record in records:
        if record.identity.role is PopulationRole.B4:
            record.request_to_complete_ns = 100_000_000
    report = reduce_records(records, expected_rounds=10)
    assert report.decision == "B4_MATERIAL"
    assert report.selected_arm == PopulationRole.B4.value
    assert report.smallest_break_even == "long_600"


class AdapterSse:
    async def __aiter__(self):
        pcm = base64.b64encode(b"\x00\x00" * 100).decode("ascii")
        yield "data: " + json.dumps({"type": "speech.audio.delta", "audio": pcm})
        yield ""
        yield 'data: {"type":"speech.audio.done","usage":{}}'
        yield ""

    async def aclose(self) -> None:
        return None


def test_actual_conformance_capacity_completes_formal_b4_with_twelve_retained_stream_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    providers: list[OpenAIStreamingSpeechProvider] = []

    async def sse_factory(*_args: Any) -> AdapterSse:
        return AdapterSse()

    async def select_actual_adapter(*, batch_available: bool) -> Any:
        assert batch_available is False
        provider = OpenAIStreamingSpeechProvider(
            OpenAIStreamingSpeechConfig(api_base="https://api.openai.com/v1", api_key="test-key"),
            sse_factory=sse_factory,
        )
        providers.append(provider)
        return SimpleNamespace(tier=runner.SpeechRouteTier.STREAMING, provider=provider)

    monkeypatch.setattr(runner, "select_environment_streaming_speech", select_actual_adapter)
    output = tmp_path / "formal-capacity"
    assert main([
        "run", "--manifest", str(MANIFEST_PATH), "--output-root", str(output),
        "--run-id", "capacity-run", "--source-commit", "a" * 40, "--source-state", "clean",
        "--agent-core-commit", "b" * 40, "--environment-profile", "test", "--rounds", "10",
    ]) == 0
    b4 = providers[2].conformance.snapshot()
    assert b4.retained_synthesis == 0
    assert b4.retained_identity_tombstones <= 64
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["observed_requests"] == report["expected_requests"] == 240
