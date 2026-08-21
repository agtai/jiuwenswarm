from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import struct
import sys
import wave
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    TransportCleanupSnapshot,
)
from jiuwenswarm.server.live_voice.speech_ports import (
    ProviderRef,
    RecognitionAlternative,
    RecognitionEventKind,
    RecognitionHypothesis,
)
from jiuwenswarm.server.live_voice.streaming_speech import (
    RecognitionCommitDisposition,
    RecognitionTurnBoundaryEvent,
    RecognitionTurnBoundaryKind,
    StreamingRecognitionEvent,
)


ROOT = Path(__file__).parents[3]
RUNNER_PATH = ROOT / "scripts/live_voice/vad_eot_causal_benchmark.py"
SUPPORT_PATH = ROOT / "scripts/live_voice/vad_eot_benchmark_support.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


support = _load(SUPPORT_PATH, "vad_eot_benchmark_support")
runner = _load(RUNNER_PATH, "vad_eot_causal_benchmark")


def _private(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    path.chmod(0o600)


def _corpus(tmp_path: Path):
    root = tmp_path / "corpus"
    root.mkdir(mode=0o700, parents=True)
    expected = "first clause second clause"
    cases = []
    for case_id, pause_ms in zip(support.CASE_IDS, support.PAUSES_MS, strict=True):
        split = 960
        voiced_end = split + pause_ms * 48 + 960
        samples = (1200,) * split + (0,) * (pause_ms * 48) + (1200,) * 960 + (0,) * 96_000
        wav_path = root / f"{case_id}.wav"
        with wave.open(str(wav_path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(48_000)
            output.writeframes(struct.pack(f"<{len(samples)}h", *samples))
        wav_path.chmod(0o600)
        cases.append(
            {
                "case_id": case_id,
                "pause_ms": pause_ms,
                "wav_path": wav_path.name,
                "sha256": hashlib.sha256(wav_path.read_bytes()).hexdigest(),
                "final_voiced_frame": voiced_end,
                "second_clause_first_frame": split + pause_ms * 48,
            }
        )
    manifest_path = root / "manifest.json"
    manifest = {
        "schema_version": support.CORPUS_SCHEMA_VERSION,
        "corpus_id": "vad-en-v1",
        "source_wav": "source.wav",
        "source_sha256": "a" * 64,
        "split_frame": 960,
        "sample_rate_hz": 48_000,
        "channel_count": 1,
        "sample_width_bytes": 2,
        "final_silence_ms": 2_000,
        "expected_normalized_transcript": expected,
        "required_post_pause_tokens": ["second"],
        "cases": cases,
    }
    _private(manifest_path, (json.dumps(manifest) + "\n").encode())
    return manifest_path, support.load_vad_corpus_manifest(manifest_path)


def _config(tmp_path: Path, *, mode: str = "pilot"):
    manifest_path, _ = _corpus(tmp_path)
    return runner.VadBenchmarkConfig(
        run_id="vad-test-001",
        mode=mode,
        manifest_path=manifest_path,
        output_path=tmp_path / "report.json",
        git_commit="a" * 40,
        source_clean=True,
    )


class ManualClock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value

    async def sleep(self, delay: float) -> None:
        self.value += max(0.0, delay)
        await asyncio.sleep(0)


class FakeProvider:
    def __init__(self, case, threshold_ms: int, *, transcript: str | None = None) -> None:
        self.case = case
        self.threshold_ms = threshold_ms
        self.transcript = transcript or case.expected_normalized_transcript
        self.ref = None
        self.events: asyncio.Queue = asyncio.Queue()
        self.frames = []
        self.emitted = False
        self.closed = False
        self.cleanup_snapshot = TransportCleanupSnapshot(0, 0, ())
        self.provider = ProviderRef("openai", "fake")

    async def open_recognition(self, request, *, timeout_seconds: float) -> None:
        assert timeout_seconds > 0
        assert request.turn_detection.server_vad.silence_duration_ms == self.threshold_ms
        self.ref = request.ref

    async def send_recognition_audio(self, frame) -> None:
        self.frames.append(frame)
        trigger = self.case.final_voiced_frame + self.threshold_ms * 48
        if not self.emitted and frame.sample_cursor + frame.sample_count >= trigger:
            self.emitted = True
            item = "private-item"
            await self.events.put(
                RecognitionTurnBoundaryEvent(
                    self.ref,
                    self.provider,
                    0,
                    RecognitionTurnBoundaryKind.SPEECH_STARTED,
                    item,
                    provider_start_ms=0,
                )
            )
            await self.events.put(
                RecognitionTurnBoundaryEvent(
                    self.ref,
                    self.provider,
                    1,
                    RecognitionTurnBoundaryKind.SPEECH_STOPPED,
                    item,
                    provider_end_ms=self.case.final_voiced_frame // 48 + self.threshold_ms,
                )
            )
            await self.events.put(
                RecognitionTurnBoundaryEvent(
                    self.ref,
                    self.provider,
                    2,
                    RecognitionTurnBoundaryKind.COMMITTED,
                    item,
                )
            )
            hypothesis = RecognitionHypothesis(
                (RecognitionAlternative(self.transcript, self.transcript, None),)
            )
            await self.events.put(
                StreamingRecognitionEvent(
                    self.ref,
                    self.provider,
                    3,
                    frame.sample_cursor + frame.sample_count,
                    RecognitionEventKind.FINAL,
                    hypothesis,
                )
            )

    async def commit_recognition(self, ref):
        assert ref == self.ref
        return RecognitionCommitDisposition.SERVER_VAD_OBSERVED

    async def next_recognition_event(self, ref, *, timeout_seconds: float):
        assert ref == self.ref
        return await asyncio.wait_for(self.events.get(), timeout_seconds)

    async def cancel_recognition(self, ref, *, reason: str = "caller_cancel") -> None:
        assert ref == self.ref

    async def close(self) -> None:
        self.closed = True


class EarlyEotThenProtocolProvider(FakeProvider):
    async def send_recognition_audio(self, frame) -> None:
        self.frames.append(frame)
        if not self.emitted and frame.sample_cursor + frame.sample_count >= self.case.second_clause_first_frame:
            self.emitted = True
            item = "private-item"
            for event in (
                RecognitionTurnBoundaryEvent(
                    self.ref, self.provider, 0,
                    RecognitionTurnBoundaryKind.SPEECH_STARTED, item,
                    provider_start_ms=0,
                ),
                RecognitionTurnBoundaryEvent(
                    self.ref, self.provider, 1,
                    RecognitionTurnBoundaryKind.SPEECH_STOPPED, item,
                    provider_end_ms=self.case.second_clause_first_frame // 48,
                ),
                RecognitionTurnBoundaryEvent(
                    self.ref, self.provider, 2,
                    RecognitionTurnBoundaryKind.COMMITTED, item,
                ),
            ):
                await self.events.put(event)

    async def next_recognition_event(self, ref, *, timeout_seconds: float):
        if self.events.empty() and self.emitted:
            raise RuntimeError("private-provider-sentinel")
        return await super().next_recognition_event(ref, timeout_seconds=timeout_seconds)


def test_config_is_closed_and_freezes_sequence(tmp_path: Path) -> None:
    pilot = _config(tmp_path / "pilot")
    formal = _config(tmp_path / "formal", mode="run")
    assert pilot.configuration_sequence == (("A1", 1200), ("E1", 900), ("E2", 800), ("A2", 1200))
    assert pilot.attempts_per_case == 1
    assert formal.attempts_per_case == 5
    with pytest.raises(ValueError, match="VAD_BENCHMARK_CONFIG_INVALID"):
        replace(pilot, source_clean=False)


def test_result_invariants_reject_attractive_failed_latency(tmp_path: Path) -> None:
    _config(tmp_path)
    with pytest.raises(ValueError, match="VAD_ATTEMPT_RESULT_INVALID"):
        runner.VadAttemptResult(
            "A1", 1200, "no-internal-pause", 0,
            runner.VadAttemptOutcome.FAILED, runner.VadAttemptReason.EARLY_EOT,
            1, 1, 1, 1, True, True, True, True,
            1.0, 1.0, 2.0, 0.0, 0.0, 0.0, 0.0,
        )


@pytest.mark.asyncio
async def test_attempt_paces_contiguous_frames_and_accepts_one_exact_turn(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _, manifest = _corpus(tmp_path / "second")
    case = manifest.cases[0]
    clock = ManualClock()
    providers = []

    async def factory(turn_detection):
        provider = FakeProvider(case, turn_detection.server_vad.silence_duration_ms)
        providers.append(provider)
        return provider

    result = await runner.run_vad_attempt(
        config,
        case,
        0,
        configuration_id="A1",
        silence_duration_ms=1200,
        provider_factory=factory,
        monotonic=clock.now,
        sleep=clock.sleep,
    )
    assert result.outcome is runner.VadAttemptOutcome.COMPLETED
    # The fake publishes at the first complete 20 ms frame after the threshold;
    # cooperative sender/collector scheduling may add one further quantum.
    assert result.final_voiced_frame_to_eot_ms == pytest.approx(1200.0, abs=40.1)
    assert [frame.seq for frame in providers[0].frames] == list(range(len(providers[0].frames)))
    assert providers[0].closed is True


@pytest.mark.asyncio
async def test_incomplete_transcript_is_failed_without_latency_credit(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _, manifest = _corpus(tmp_path / "second")
    case = manifest.cases[0]
    clock = ManualClock()

    async def factory(turn_detection):
        return FakeProvider(case, turn_detection.server_vad.silence_duration_ms, transcript="first clause")

    result = await runner.run_vad_attempt(
        config, case, 0, configuration_id="A1", silence_duration_ms=1200,
        provider_factory=factory, monotonic=clock.now, sleep=clock.sleep,
    )
    assert result.outcome is runner.VadAttemptOutcome.FAILED
    assert result.reason is runner.VadAttemptReason.TRANSCRIPT_INCOMPLETE
    assert result.final_voiced_frame_to_eot_ms is None


@pytest.mark.asyncio
async def test_provider_failure_cancels_collector_and_closes_owner(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _, manifest = _corpus(tmp_path / "second")
    case = manifest.cases[0]
    clock = ManualClock()
    provider = FakeProvider(case, 1200)

    async def fail_send(_frame) -> None:
        raise RuntimeError("private-provider-sentinel")

    provider.send_recognition_audio = fail_send

    async def factory(_turn_detection):
        return provider

    result = await runner.run_vad_attempt(
        config, case, 0, configuration_id="A1", silence_duration_ms=1200,
        provider_factory=factory, monotonic=clock.now, sleep=clock.sleep,
    )
    assert result.outcome is runner.VadAttemptOutcome.UNKNOWN
    assert result.reason is runner.VadAttemptReason.PROVIDER_PROTOCOL
    assert provider.closed is True


@pytest.mark.asyncio
async def test_observed_early_eot_remains_turn_failure_when_tail_protocol_fails(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _, manifest = _corpus(tmp_path / "second")
    case = manifest.cases[-1]
    clock = ManualClock()
    provider = EarlyEotThenProtocolProvider(case, 1200)

    async def factory(_turn_detection):
        return provider

    result = await runner.run_vad_attempt(
        config, case, 0, configuration_id="A1", silence_duration_ms=1200,
        provider_factory=factory, monotonic=clock.now, sleep=clock.sleep,
    )
    assert result.outcome is runner.VadAttemptOutcome.FAILED
    assert result.reason is runner.VadAttemptReason.EARLY_EOT
    assert result.final_voiced_frame_to_eot_ms is None
    assert result.pacing_valid is True
    assert provider.closed is True


@pytest.mark.asyncio
async def test_real_factory_passes_only_existing_speech_configuration(monkeypatch) -> None:
    class MarkerProvider:
        pass

    provider = MarkerProvider()
    seen = None

    async def selector(*, environ, batch_available):
        nonlocal seen
        seen = dict(environ)
        assert batch_available is False
        return SimpleNamespace(
            tier=runner.SpeechRouteTier.STREAMING,
            provider=provider,
        )

    monkeypatch.setattr(runner, "OpenAIStreamingSpeechProvider", MarkerProvider)
    monkeypatch.setattr(runner, "select_environment_streaming_speech", selector)
    selected = await runner.create_real_streaming_provider(
        {
            "LIVE_VOICE_SPEECH_PROVIDER": "openai",
            "LIVE_VOICE_SPEECH_API_BASE": "https://api.openai.com/v1",
            "LIVE_VOICE_SPEECH_API_KEY": "private-provider-sentinel",
            "LIVE_VOICE_SPEECH_STT_MODEL": "gpt-4o-mini-transcribe",
            "UNRELATED_PRIVATE_VALUE": "must-not-copy",
        }
    )
    assert selected is provider
    assert seen is not None
    assert "UNRELATED_PRIVATE_VALUE" not in seen
    assert seen["LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED"] == "1"


def test_report_is_private_closed_and_excludes_failed_samples(tmp_path: Path) -> None:
    config = _config(tmp_path)
    completed = runner.VadAttemptResult.completed(
        "A1", 1200, "no-internal-pause", 0,
        final_voiced_frame_to_eot_ms=1200.0,
        eot_to_final_ms=100.0,
        final_voiced_frame_to_final_ms=1300.0,
        provider_reported_speech_end_ms=1220.0,
        pacing_p50_ms=0.0,
        pacing_p95_ms=0.0,
        pacing_max_ms=0.0,
    )
    failed = runner.VadAttemptResult.failed(
        "A1", 1200, "no-internal-pause", 1,
        runner.VadAttemptReason.EARLY_EOT,
        speech_started_count=1,
        speech_stopped_count=1,
    )
    report = runner.build_report(
        config,
        corpus_id="vad-en-v1",
        corpus_manifest_sha256="b" * 64,
        provider_id="openai",
        provider_class="OpenAIStreamingSpeechProvider",
        stt_model="gpt-4o-mini-transcribe",
        attempts=(completed, failed),
        decision="INCONCLUSIVE",
    )
    runner.write_vad_benchmark_report(config.output_path, report)
    loaded = json.loads(config.output_path.read_text())
    assert config.output_path.stat().st_mode & 0o077 == 0
    assert loaded["summaries"][0]["completed"] == 1
    assert loaded["summaries"][0]["failed"] == 1
    assert loaded["summaries"][0]["eot_ms_p50"] == 1200.0
    assert "private-item" not in config.output_path.read_text()
    with pytest.raises(FileExistsError):
        runner.write_vad_benchmark_report(config.output_path, report)


@pytest.mark.asyncio
async def test_screening_order_is_exact(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _, manifest = _corpus(tmp_path / "second")
    calls = []

    async def attempt(config, case, attempt_index, **kwargs):
        calls.append((kwargs["configuration_id"], kwargs["silence_duration_ms"], case.case_id, attempt_index))
        return runner.VadAttemptResult.completed(
            kwargs["configuration_id"], kwargs["silence_duration_ms"], case.case_id, attempt_index,
            final_voiced_frame_to_eot_ms=float(kwargs["silence_duration_ms"]),
            eot_to_final_ms=10.0,
            final_voiced_frame_to_final_ms=float(kwargs["silence_duration_ms"] + 10),
            provider_reported_speech_end_ms=None,
            pacing_p50_ms=0.0, pacing_p95_ms=0.0, pacing_max_ms=0.0,
        )

    report = await runner.run_screening(
        config, manifest, provider_factory=lambda _: None,
        attempt_runner=attempt,
    )
    assert [(value[0], value[1]) for value in calls[::4]] == [
        ("A1", 1200), ("E1", 900), ("E2", 800), ("A2", 1200)
    ]
    assert report.decision == "READY_FOR_SCREENING"


def test_cli_rejects_dirty_or_existing_output_before_provider(tmp_path: Path) -> None:
    manifest_path, _ = _corpus(tmp_path)
    argv = [
        "pilot", "--manifest", str(manifest_path), "--output", str(tmp_path / "report.json"),
        "--run-id", "vad-test-001", "--git-commit", "a" * 40,
    ]
    config = runner.parse_args(argv, source_commit="a" * 40, source_clean=True)
    assert config.mode == "pilot"
    with pytest.raises(ValueError, match="VAD_BENCHMARK_CONFIG_INVALID"):
        runner.parse_args(argv, source_commit="a" * 40, source_clean=False)
    (tmp_path / "report.json").write_text("occupied")
    with pytest.raises(ValueError, match="VAD_BENCHMARK_CONFIG_INVALID"):
        runner.parse_args(argv, source_commit="a" * 40, source_clean=True)
