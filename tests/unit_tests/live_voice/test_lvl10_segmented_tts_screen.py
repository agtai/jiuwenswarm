from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import sys
from dataclasses import replace
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
    def __init__(self, lines: tuple[str, ...], *, release: asyncio.Event | None = None) -> None:
        self._lines = lines
        self._release = release
        self.closed = False

    async def __aiter__(self):
        if self._release is not None:
            await self._release.wait()
        for line in self._lines:
            await asyncio.sleep(0)
            yield line

    async def aclose(self) -> None:
        self.closed = True
        if self._release is not None:
            self._release.set()


class ScriptedSseFactory:
    """Test boundary: captures public Provider payloads, never real network."""

    def __init__(self, *, fail_input_index: int | None = None, block_input_index: int | None = None) -> None:
        self.inputs: list[str] = []
        self.active = 0
        self.max_active = 0
        self.fail_input_index = fail_input_index
        self.block_input_index = block_input_index
        self.release = asyncio.Event()
        self.streams: list[ScriptedSseStream] = []

    async def __call__(self, _endpoint: str, _headers: dict[str, str], payload: dict[str, object], _timeout: float) -> ScriptedSseStream:
        text = payload["input"]
        assert isinstance(text, str)
        index = len(self.inputs)
        self.inputs.append(text)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self.fail_input_index == index:
            raise ConnectionError("scripted-provider-failure")
        pcm = (index.to_bytes(2, "little", signed=True)) * 12_000
        lines = (
            "data: " + json.dumps({"type": "speech.audio.delta", "audio": base64.b64encode(pcm).decode("ascii")}),
            "",
            'data: {"type":"speech.audio.done","usage":{}}',
            "",
        )
        stream = ScriptedSseStream(
            lines,
            release=self.release if self.block_input_index == index else None,
        )
        self.streams.append(stream)
        return stream


def _config() -> OpenAIStreamingSpeechConfig:
    return OpenAIStreamingSpeechConfig(
        api_key="lvl10-test-key",
        api_base="https://example.invalid/v1",
        transcription_model="test-stt",
        speech_model="test-tts",
        speech_voice="test-voice",
        connect_timeout_seconds=1,
        event_timeout_seconds=1,
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
async def test_b_sends_one_request_per_manifest_chunk_and_releases_in_order() -> None:
    fixture = load_fixture_manifest(MANIFEST_PATH)[1]
    factory = ScriptedSseFactory()
    provider = _provider(factory)
    try:
        record = await run_attempt(provider, fixture, PopulationRole.B, _identity(PopulationRole.B))
        assert factory.inputs == list(fixture.chunks)
        assert factory.max_active <= 2
        assert record.provider_request_count == len(fixture.chunks)
        assert record.released_chunk_indexes == tuple(range(len(fixture.chunks)))
        assert record.forbidden_effects == ZERO_FORBIDDEN_EFFECTS
    finally:
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
        # The runner must expose fence disposition through its deterministic
        # cancellation helper instead of treating task cancellation as success.
        record = await runner.cancel_during_successor(provider, fixture, _identity(PopulationRole.B, attempt_index=1))
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


def _record(role: Any, fixture_id: str, *, reserve_ms: float, first_pcm_ms: float, complete_ms: float, requests: int, stall_ms: float = 0, outcome: str = "completed") -> Any:
    return SimpleNamespace(
        identity=_identity(role, fixture_id),
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


def test_reducer_requires_100ms_and_ten_percent_medium_long_reserve_win() -> None:
    records: list[Any] = []
    for role, reserve in ((PopulationRole.A1, 1_200), (PopulationRole.B, 1_050), (PopulationRole.A2, 1_210)):
        for fixture_id in ("short", "medium", "long"):
            for attempt in range(5):
                records.append(replace(_record(role, fixture_id, reserve_ms=reserve, first_pcm_ms=700, complete_ms=1_500, requests=1 if fixture_id == "short" else (3 if role is PopulationRole.B else 1)), identity=_identity(role, fixture_id, attempt)))
    report = reduce_records(records)
    assert report.decision == "PASS"


def test_reducer_rejects_completion_regression_and_request_bound_violation() -> None:
    records = [_record(PopulationRole.B, "medium", reserve_ms=800, first_pcm_ms=500, complete_ms=2_000, requests=5)]
    report = reduce_records(records)
    assert report.decision in {"REJECTED", "INCONCLUSIVE"}


def test_main_refuses_existing_output_and_never_serializes_secret(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError):
        main(["validate-corpus", "--manifest", str(MANIFEST_PATH), "--output-root", str(output), "--api-key", "lvl10-secret"])
    assert "lvl10-secret" not in capsys.readouterr().out
