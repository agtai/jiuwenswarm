from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    OpenAIStreamingSpeechConfig,
    OpenAIStreamingSpeechProvider,
)


ROOT = Path(__file__).parents[3]
MANIFEST_PATH = ROOT / "tests/fixtures/live_voice_lvl10_tts_v1/manifest.json"
RUNNER_PATH = ROOT / "scripts/live_voice/lvl10_segmented_tts_screen.py"
ZERO_FORBIDDEN_EFFECTS = {
    "agent_dispatches": 0,
    "tool_dispatches": 0,
    "task_mutations": 0,
    "chat_mutations": 0,
    "history_mutations": 0,
}


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("lvl10_segmented_tts_screen", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# RED contract: Writer A creates this runner. Loading it at collection time is
# intentional: Task 2 must demonstrate that the contract is absent before the
# production-side validation runner exists.
runner = _load_runner()
PopulationRole = runner.PopulationRole
AttemptIdentity = runner.AttemptIdentity
load_fixture_manifest = runner.load_fixture_manifest
run_attempt = runner.run_attempt
derive_ordered_release_stall_ns = runner.derive_ordered_release_stall_ns
reduce_records = runner.reduce_records
main = runner.main


class ScriptedSseStream:
    def __init__(
        self,
        lines: tuple[str, ...],
        *,
        release: asyncio.Event | None = None,
        before_done: asyncio.Event | None = None,
        on_terminal: Callable[[], None],
    ) -> None:
        self._lines = lines
        self._release = release
        self._before_done = before_done
        self._on_terminal = on_terminal
        self._terminal = False
        self.closed = False

    def _finish_once(self) -> None:
        if not self._terminal:
            self._terminal = True
            self._on_terminal()

    async def __aiter__(self):
        try:
            if self._release is not None:
                await self._release.wait()
            for line in self._lines:
                if self._before_done is not None and "speech.audio.done" in line:
                    await self._before_done.wait()
                await asyncio.sleep(0)
                yield line
        finally:
            self._finish_once()

    async def aclose(self) -> None:
        self.closed = True
        if self._release is not None:
            self._release.set()
        if self._before_done is not None:
            self._before_done.set()
        self._finish_once()


class ScriptedSseFactory:
    """Test boundary: captures public Provider payloads, never real network."""

    def __init__(
        self,
        *,
        fail_input_index: int | None = None,
        block_input_index: int | None = None,
        delay_done_input_index: int | None = None,
        sample_count: int = 12_000,
    ) -> None:
        self.inputs: list[str] = []
        self.active = 0
        self.max_active = 0
        self.fail_input_index = fail_input_index
        self.block_input_index = block_input_index
        self.delay_done_input_index = delay_done_input_index
        self.sample_count = sample_count
        self.release = asyncio.Event()
        self.allow_done = asyncio.Event()
        self.streams: list[ScriptedSseStream] = []

    def _deactivate_once(self) -> None:
        assert self.active > 0
        self.active -= 1

    async def __call__(
        self,
        _endpoint: str,
        _headers: dict[str, str],
        payload: dict[str, object],
        _timeout: float,
    ) -> ScriptedSseStream:
        text = payload["input"]
        assert isinstance(text, str)
        index = len(self.inputs)
        self.inputs.append(text)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self.fail_input_index == index:
            self._deactivate_once()
            raise ConnectionError("scripted-provider-failure")
        pcm = (index.to_bytes(2, "little", signed=True)) * self.sample_count
        lines = (
            "data: " + json.dumps({"type": "speech.audio.delta", "audio": base64.b64encode(pcm).decode("ascii")}),
            "",
            'data: {"type":"speech.audio.done","usage":{}}',
            "",
        )
        stream = ScriptedSseStream(
            lines,
            release=self.release if self.block_input_index == index else None,
            before_done=self.allow_done if self.delay_done_input_index == index else None,
            on_terminal=self._deactivate_once,
        )
        self.streams.append(stream)
        return stream


def _config() -> OpenAIStreamingSpeechConfig:
    return OpenAIStreamingSpeechConfig(
        api_key="lvl10-test-key",
        api_base="https://example.invalid/v1",
        stt_model="test-stt",
        tts_model="test-tts",
        tts_voice="test-voice",
        connect_timeout_seconds=1,
    )


def _provider(factory: ScriptedSseFactory) -> OpenAIStreamingSpeechProvider:
    return OpenAIStreamingSpeechProvider(_config(), sse_factory=factory)


def _identity(role: Any, fixture_id: str = "medium", attempt_index: int = 0) -> Any:
    return AttemptIdentity("lvl10-red", role, fixture_id, attempt_index)


def _write_manifest(tmp_path: Path, *, offsets: list[int]) -> Path:
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    document["fixtures"][0]["offsets"] = offsets
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_manifest_preserves_exact_chunks() -> None:
    fixtures = load_fixture_manifest(MANIFEST_PATH)
    assert [item.fixture_id for item in fixtures] == ["short", "medium", "long"]
    assert [len(item.chunks) for item in fixtures] == [1, 3, 4]
    assert all("".join(item.chunks) == item.final_text for item in fixtures)


@pytest.mark.parametrize("offsets", ([1, 31], [0, 0, 31], [0, 30], [0, 31, 32, 33, 34, 35]))
def test_manifest_rejects_invalid_offsets(tmp_path: Path, offsets: list[int]) -> None:
    with pytest.raises(ValueError, match="LVL10_CORPUS_INVALID"):
        load_fixture_manifest(_write_manifest(tmp_path, offsets=offsets))


@pytest.mark.parametrize(
    "field,value",
    (("sha256", "0" * 64), ("unknown_field", "must-reject")),
)
def test_manifest_rejects_bad_hash_and_unknown_fields(
    tmp_path: Path, field: str, value: str
) -> None:
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    document["fixtures"][0][field] = value
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="LVL10_CORPUS_INVALID"):
        load_fixture_manifest(path)


@pytest.mark.asyncio
async def test_a1_sends_one_full_authoritative_final_request() -> None:
    fixture = load_fixture_manifest(MANIFEST_PATH)[1]
    factory = ScriptedSseFactory()
    provider = _provider(factory)
    try:
        record = await run_attempt(provider, fixture, PopulationRole.A1, _identity(PopulationRole.A1))
        assert factory.inputs == [fixture.final_text]
        assert record.provider_request_count == 1
        assert record.provider_error_count == 0
        assert record.forbidden_effects == ZERO_FORBIDDEN_EFFECTS
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_short_audio_records_completion_as_reserve_when_250ms_is_unreached() -> None:
    fixture = load_fixture_manifest(MANIFEST_PATH)[0]
    provider = _provider(ScriptedSseFactory(sample_count=100))
    try:
        record = await run_attempt(
            provider, fixture, PopulationRole.A1, _identity(PopulationRole.A1, "short")
        )
        assert record.short_of_reserve is True
        assert record.request_to_reserve_ns == record.request_to_complete_ns
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_b_prefetches_exactly_one_successor_and_releases_in_order() -> None:
    fixture = load_fixture_manifest(MANIFEST_PATH)[1]
    factory = ScriptedSseFactory(delay_done_input_index=0)
    provider = _provider(factory)
    task = asyncio.create_task(
        run_attempt(provider, fixture, PopulationRole.B, _identity(PopulationRole.B))
    )
    try:
        while len(factory.inputs) < 2:
            await asyncio.sleep(0)
        assert factory.max_active == 2
        factory.allow_done.set()
        record = await task
        assert factory.inputs == list(fixture.chunks)
        assert factory.active == 0
        assert record.provider_request_count == len(fixture.chunks)
        assert record.released_chunk_indexes == tuple(range(len(fixture.chunks)))
        assert record.forbidden_effects == ZERO_FORBIDDEN_EFFECTS
    finally:
        factory.allow_done.set()
        await provider.close()


@pytest.mark.asyncio
async def test_b_buffers_successor_that_completes_before_predecessor_done() -> None:
    fixture = load_fixture_manifest(MANIFEST_PATH)[1]
    factory = ScriptedSseFactory(delay_done_input_index=0)
    provider = _provider(factory)
    task = asyncio.create_task(
        run_attempt(provider, fixture, PopulationRole.B, _identity(PopulationRole.B))
    )
    try:
        while len(factory.inputs) < 2:
            await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert factory.max_active == 2
        factory.allow_done.set()
        record = await task
        assert record.released_chunk_indexes == tuple(range(len(fixture.chunks)))
        assert record.successor_pcm_released_before_predecessor_done == 0
    finally:
        factory.allow_done.set()
        await provider.close()


@pytest.mark.asyncio
async def test_b_cancellation_releases_zero_pcm_after_fence() -> None:
    fixture = load_fixture_manifest(MANIFEST_PATH)[1]
    factory = ScriptedSseFactory(block_input_index=1)
    provider = _provider(factory)
    task = asyncio.create_task(run_attempt(provider, fixture, PopulationRole.B, _identity(PopulationRole.B)))
    try:
        while len(factory.inputs) < 2:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Benchmark-only deterministic test seam, not a product API. It must
        # expose fence disposition instead of treating cancellation as success.
        record = await runner.cancel_during_successor(
            provider, fixture, _identity(PopulationRole.B, attempt_index=1)
        )
        assert record.post_fence_sample_count == 0
        assert record.group_completed is False
        assert record.forbidden_effects == ZERO_FORBIDDEN_EFFECTS
    finally:
        factory.release.set()
        await provider.close()


@pytest.mark.asyncio
async def test_b_provider_failure_discards_unreleased_successor() -> None:
    fixture = load_fixture_manifest(MANIFEST_PATH)[1]
    factory = ScriptedSseFactory(fail_input_index=1)
    provider = _provider(factory)
    try:
        record = await run_attempt(provider, fixture, PopulationRole.B, _identity(PopulationRole.B))
        assert record.terminal_outcome == "failed"
        assert record.group_completed is False
        assert record.post_fence_sample_count == 0
        assert record.provider_error_count == 1
        assert record.forbidden_effects == ZERO_FORBIDDEN_EFFECTS
    finally:
        await provider.close()


def test_ordered_release_stall_counts_only_starvation_after_playback_eligibility() -> None:
    events = (
        runner.ReleaseEvent(chunk_index=0, released_at_ns=0, sample_count=12_000),
        runner.ReleaseEvent(chunk_index=1, released_at_ns=300_000_000, sample_count=12_000),
    )
    assert derive_ordered_release_stall_ns(events) == 50_000_000


def _record(
    role: Any,
    fixture_id: str,
    *,
    reserve_ms: float,
    first_pcm_ms: float,
    complete_ms: float,
    requests: int,
    stall_ms: float = 0,
    outcome: str = "completed",
    attempt_index: int = 0,
) -> Any:
    return SimpleNamespace(
        identity=_identity(role, fixture_id, attempt_index),
        request_to_reserve_ns=int(reserve_ms * 1_000_000),
        request_to_first_pcm_ns=int(first_pcm_ms * 1_000_000),
        request_to_complete_ns=int(complete_ms * 1_000_000),
        ordered_release_stall_ns=int(stall_ms * 1_000_000),
        provider_request_count=requests,
        provider_error_count=0,
        terminal_outcome=outcome,
        group_completed=outcome == "completed",
        exact_text_coverage=True,
        exact_segment_order=True,
        post_fence_sample_count=0,
        forbidden_effects=ZERO_FORBIDDEN_EFFECTS,
    )


def _valid_population() -> list[Any]:
    records: list[Any] = []
    for role, reference_reserve, reference_first_pcm in (
        (PopulationRole.A1, 1_200, 700),
        (PopulationRole.B, 0, 0),
        (PopulationRole.A2, 1_210, 710),
    ):
        for fixture_id in ("short", "medium", "long"):
            if role is PopulationRole.B:
                # Medium/long: 150 ms and at least 10% better than both refs.
                # Short is a one-request parity control, not a gain claim.
                reserve = 1_200 if fixture_id == "short" else 1_050
                first_pcm = 700 if fixture_id == "short" else 650
                requests = {"short": 1, "medium": 3, "long": 4}[fixture_id]
            else:
                reserve = reference_reserve
                first_pcm = reference_first_pcm
                requests = 1
            for attempt in range(5):
                records.append(
                    _record(
                        role,
                        fixture_id,
                        reserve_ms=reserve,
                        first_pcm_ms=first_pcm,
                        complete_ms=1_500,
                        requests=requests,
                        attempt_index=attempt,
                    )
                )
    return records


def test_reducer_requires_100ms_and_ten_percent_medium_long_reserve_win() -> None:
    report = reduce_records(_valid_population())
    assert report.decision == "PASS"


def test_reducer_rejects_only_absolute_reserve_gate_miss() -> None:
    records = _valid_population()
    for record in records:
        if record.identity.role is PopulationRole.B and record.identity.fixture_id == "medium":
            record.request_to_reserve_ns = 1_151_000_000  # 49 ms vs A1, <100 ms.
    assert reduce_records(records).decision == "NO_MATERIAL_GAIN"


def test_reducer_rejects_only_relative_reserve_gate_miss() -> None:
    records = _valid_population()
    for record in records:
        if record.identity.role is PopulationRole.B and record.identity.fixture_id == "long":
            record.request_to_reserve_ns = 1_100_000_000  # 100 ms, but <10% vs A1.
    assert reduce_records(records).decision == "NO_MATERIAL_GAIN"


def test_reducer_rejects_completion_regression_and_request_bound_violation() -> None:
    records = _valid_population()
    for record in records:
        if record.identity.role is PopulationRole.B and record.identity.fixture_id == "medium":
            record.request_to_complete_ns = 1_700_000_000  # >10% slower than 1,500 ms.
        if record.identity.role is PopulationRole.B and record.identity.fixture_id == "long":
            record.provider_request_count = 5
    assert reduce_records(records).decision == "REJECTED"


def test_reducer_marks_a1_a2_drift_inconclusive() -> None:
    records = _valid_population()
    for record in records:
        if record.identity.role is PopulationRole.A2:
            record.request_to_reserve_ns = 1_500_000_000  # >250 ms and >20% drift.
    assert reduce_records(records).decision == "INCONCLUSIVE"


def test_main_refuses_existing_output_without_a_credential_cli_contract(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError):
        main(
            [
                "run",
                "--manifest",
                str(MANIFEST_PATH),
                "--output-root",
                str(output),
                "--run-id",
                "lvl10-existing",
                "--source-commit",
                "a" * 40,
                "--source-state",
                "clean",
                "--agent-core-commit",
                "b" * 40,
                "--environment-profile",
                "deterministic-test",
                "--attempts",
                "1",
            ]
        )


def test_injected_provider_config_hides_secret_from_serialization() -> None:
    assert "lvl10-test-key" not in repr(_config())
