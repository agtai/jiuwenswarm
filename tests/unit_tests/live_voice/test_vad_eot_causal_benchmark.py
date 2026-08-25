from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import struct
import subprocess
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


def _complete_pilot_attempts(manifest):
    attempts = []
    for configuration_id, threshold in runner.CONFIGURATION_SEQUENCE:
        for case in manifest.cases:
            attempts.append(
                runner.VadAttemptResult.completed(
                    configuration_id, threshold, case.case_id, 0,
                    final_voiced_frame_to_eot_ms=float(threshold),
                    eot_to_final_ms=100.0,
                    final_voiced_frame_to_final_ms=float(threshold + 100),
                    provider_reported_speech_end_ms=None,
                    pacing_p50_ms=0.0, pacing_p95_ms=0.0, pacing_max_ms=0.0,
                )
            )
    return attempts


def _semantic_formal_attempts(
    manifest,
    *,
    candidate_id: str = "B_AUTO",
    candidate_eot_ms: float = 300.0,
    candidate_finalization_ms: float = 100.0,
    a2_eot_ms: float = 1200.0,
    failed_reason=None,
):
    attempts = []
    sequence = ("A1_1200", candidate_id, "A2_1200")
    for configuration_id in sequence:
        configuration = runner.parse_configuration(configuration_id)
        for case in manifest.cases:
            for attempt_index in range(5):
                labels = {
                    "turn_detection_mode": configuration.mode.value,
                    "semantic_eagerness": (
                        configuration.semantic_eagerness.value
                        if configuration.semantic_eagerness is not None
                        else None
                    ),
                }
                if configuration_id == candidate_id and failed_reason is not None:
                    attempts.append(
                        runner.VadAttemptResult.failed(
                            configuration_id,
                            None,
                            case.case_id,
                            attempt_index,
                            failed_reason,
                            speech_started_count=1,
                            speech_stopped_count=1,
                            committed_count=1,
                            final_count=0,
                            exact_identity=True,
                            transcript_complete=False,
                            cleanup_complete=True,
                            pacing_valid=True,
                            **labels,
                        )
                    )
                    continue
                if configuration_id == candidate_id:
                    eot_ms = candidate_eot_ms
                    finalization_ms = candidate_finalization_ms
                elif configuration_id == "A2_1200":
                    eot_ms = a2_eot_ms
                    finalization_ms = 100.0
                else:
                    eot_ms = 1200.0
                    finalization_ms = 100.0
                attempts.append(
                    runner.VadAttemptResult.completed(
                        configuration_id,
                        configuration.silence_duration_ms,
                        case.case_id,
                        attempt_index,
                        final_voiced_frame_to_eot_ms=eot_ms,
                        eot_to_final_ms=finalization_ms,
                        final_voiced_frame_to_final_ms=eot_ms + finalization_ms,
                        provider_reported_speech_end_ms=1000.0,
                        pacing_p50_ms=0.0,
                        pacing_p95_ms=0.0,
                        pacing_max_ms=0.0,
                        **labels,
                    )
                )
    return tuple(attempts)


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


class SemanticFakeProvider(FakeProvider):
    def __init__(
        self,
        case,
        *,
        disposition=RecognitionCommitDisposition.SEMANTIC_VAD_OBSERVED,
    ) -> None:
        super().__init__(case, 300)
        self.disposition = disposition

    async def open_recognition(self, request, *, timeout_seconds: float) -> None:
        assert timeout_seconds > 0
        assert request.turn_detection.mode is runner.RecognitionTurnDetectionMode.SEMANTIC_VAD
        assert request.turn_detection.semantic_vad is not None
        assert request.turn_detection.semantic_vad.eagerness is runner.SemanticVadEagerness.AUTO
        self.ref = request.ref

    async def commit_recognition(self, ref):
        assert ref == self.ref
        return self.disposition


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


class FaultEventProvider(FakeProvider):
    def __init__(self, case, threshold_ms: int, fault: str) -> None:
        super().__init__(case, threshold_ms)
        self.fault = fault
        self.rewritten = False

    async def send_recognition_audio(self, frame) -> None:
        await super().send_recognition_audio(frame)
        if self.emitted and not self.rewritten:
            self.rewritten = True
            events = []
            while not self.events.empty():
                events.append(self.events.get_nowait())
            if self.fault == "wrong_ref":
                events[0] = replace(
                    events[0], ref=replace(self.ref, session_generation=2)
                )
            elif self.fault == "wrong_item":
                events[1] = replace(events[1], provider_item_id="other-item")
            elif self.fault == "duplicate_start":
                events.insert(1, replace(events[0], seq=1))
                events = [replace(event, seq=index) for index, event in enumerate(events)]
            for event in events:
                await self.events.put(event)


def test_config_is_closed_and_freezes_sequence(tmp_path: Path) -> None:
    pilot = _config(tmp_path / "pilot")
    formal = _config(tmp_path / "formal", mode="run")
    assert pilot.configuration_sequence == (("A1", 1200), ("E1", 900), ("E2", 800), ("A2", 1200))
    assert pilot.attempts_per_case == 1
    assert formal.attempts_per_case == 5
    with pytest.raises(ValueError, match="VAD_BENCHMARK_CONFIG_INVALID"):
        replace(pilot, source_clean=False)
    with pytest.raises(ValueError, match="VAD_BENCHMARK_CONFIG_INVALID"):
        replace(pilot, output_path=Path("/tmp/private\npath"))


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
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
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
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
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
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
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
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
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
async def test_early_eot_with_invalid_pacing_is_infrastructure_invalid(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    case = manifest.cases[-1]
    clock = ManualClock()
    provider = EarlyEotThenProtocolProvider(case, 1200)

    async def slow_sleep(delay: float) -> None:
        clock.value += max(0.0, delay) + 0.100
        await asyncio.sleep(0)

    async def factory(_turn_detection):
        return provider

    result = await runner.run_vad_attempt(
        config, case, 0, configuration_id="A1", silence_duration_ms=1200,
        provider_factory=factory, monotonic=clock.now, sleep=slow_sleep,
    )
    assert result.outcome is runner.VadAttemptOutcome.INVALID
    assert result.reason is runner.VadAttemptReason.PACING_INVALID


@pytest.mark.asyncio
async def test_blocked_provider_send_returns_bounded_timeout(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    case = manifest.cases[0]
    provider = FakeProvider(case, 1200)

    async def blocked_send(_frame) -> None:
        await asyncio.Event().wait()

    provider.send_recognition_audio = blocked_send

    async def factory(_turn_detection):
        return provider

    result = await asyncio.wait_for(
        runner.run_vad_attempt(
            config, case, 0, configuration_id="A1", silence_duration_ms=1200,
            provider_factory=factory, operation_timeout_seconds=0.01,
            close_timeout_seconds=0.01,
        ),
        timeout=0.2,
    )
    assert result.outcome is runner.VadAttemptOutcome.UNKNOWN
    assert result.reason is runner.VadAttemptReason.TIMEOUT
    assert provider.closed is True


@pytest.mark.asyncio
async def test_cancellation_hostile_send_does_not_defeat_deadline(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    case = manifest.cases[0]
    provider = FakeProvider(case, 1200)

    async def hostile_send(_frame) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(0.08)

    provider.send_recognition_audio = hostile_send

    async def factory(_turn_detection):
        return provider

    started_at = asyncio.get_running_loop().time()
    result = await runner.run_vad_attempt(
        config, case, 0, configuration_id="A1", silence_duration_ms=1200,
        provider_factory=factory, operation_timeout_seconds=0.01,
        close_timeout_seconds=0.01,
    )
    elapsed = asyncio.get_running_loop().time() - started_at
    assert elapsed < 0.05
    assert result.outcome is runner.VadAttemptOutcome.UNKNOWN
    assert result.reason is runner.VadAttemptReason.CLEANUP_INCOMPLETE
    await asyncio.sleep(0.09)


@pytest.mark.asyncio
async def test_caller_cancellation_closes_exact_provider(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    case = manifest.cases[0]
    provider = FakeProvider(case, 1200)
    entered = asyncio.Event()

    async def blocked_send(_frame) -> None:
        entered.set()
        await asyncio.Event().wait()

    provider.send_recognition_audio = blocked_send

    async def factory(_turn_detection):
        return provider

    task = asyncio.create_task(
        runner.run_vad_attempt(
            config, case, 0, configuration_id="A1", silence_duration_ms=1200,
            provider_factory=factory,
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.closed is True


@pytest.mark.parametrize("fault", ("wrong_ref", "wrong_item", "duplicate_start"))
@pytest.mark.asyncio
async def test_wrong_or_duplicate_turn_identity_never_completes(
    tmp_path: Path, fault: str
) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    case = manifest.cases[0]
    clock = ManualClock()

    async def factory(_turn_detection):
        return FaultEventProvider(case, 1200, fault)

    result = await runner.run_vad_attempt(
        config, case, 0, configuration_id="A1", silence_duration_ms=1200,
        provider_factory=factory, monotonic=clock.now, sleep=clock.sleep,
    )
    assert result.outcome is not runner.VadAttemptOutcome.COMPLETED
    assert result.final_voiced_frame_to_eot_ms is None


@pytest.mark.asyncio
async def test_nonserver_commit_disposition_is_failed_without_latency(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    case = manifest.cases[0]
    clock = ManualClock()
    provider = FakeProvider(case, 1200)

    async def client_commit(_ref):
        return RecognitionCommitDisposition.CLIENT_COMMIT_SENT

    provider.commit_recognition = client_commit

    async def factory(_turn_detection):
        return provider

    result = await runner.run_vad_attempt(
        config, case, 0, configuration_id="A1", silence_duration_ms=1200,
        provider_factory=factory, monotonic=clock.now, sleep=clock.sleep,
    )
    assert result.outcome is runner.VadAttemptOutcome.FAILED
    assert result.reason is runner.VadAttemptReason.PROVIDER_PROTOCOL
    assert result.final_voiced_frame_to_eot_ms is None


@pytest.mark.asyncio
async def test_incomplete_cleanup_is_unknown_and_aborts_screening(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    case = manifest.cases[0]
    clock = ManualClock()
    provider = FakeProvider(case, 1200)
    provider.cleanup_snapshot = TransportCleanupSnapshot(1, 0, ("recognition",))

    async def factory(_turn_detection):
        return provider

    result = await runner.run_vad_attempt(
        config, case, 0, configuration_id="A1", silence_duration_ms=1200,
        provider_factory=factory, monotonic=clock.now, sleep=clock.sleep,
    )
    assert result.outcome is runner.VadAttemptOutcome.UNKNOWN
    assert result.reason is runner.VadAttemptReason.CLEANUP_INCOMPLETE


@pytest.mark.asyncio
async def test_screening_aborts_after_first_invalid_attempt(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    calls = 0

    async def invalid_attempt(_config, case, attempt_index, **kwargs):
        nonlocal calls
        calls += 1
        return runner.VadAttemptResult.failed(
            kwargs["configuration_id"], kwargs["silence_duration_ms"],
            case.case_id, attempt_index, runner.VadAttemptReason.PACING_INVALID,
            outcome=runner.VadAttemptOutcome.INVALID,
        )

    with pytest.raises(ValueError, match="INFRASTRUCTURE_INVALID"):
        await runner.run_screening(
            config, manifest, provider_factory=lambda _: None,
            attempt_runner=invalid_attempt,
        )
    assert calls == 1


@pytest.mark.asyncio
async def test_attempt_revalidates_manifest_and_wav_before_provider(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    case = manifest.cases[0]
    payload = bytearray(case.wav_path.read_bytes())
    payload[100] ^= 1
    case.wav_path.write_bytes(payload)
    case.wav_path.chmod(0o600)
    calls = 0

    async def factory(_turn_detection):
        nonlocal calls
        calls += 1
        return FakeProvider(case, 1200)

    result = await runner.run_vad_attempt(
        config, case, 0, configuration_id="A1", silence_duration_ms=1200,
        provider_factory=factory,
    )
    assert result.outcome is runner.VadAttemptOutcome.UNKNOWN
    assert calls == 0


@pytest.mark.asyncio
async def test_attempt_sends_preallocation_hash_bound_audio_snapshot(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    case = manifest.cases[0]
    original = case.wav_path.read_bytes()
    mutated = bytearray(original)
    mutated[44] ^= 0x7F
    provider = FakeProvider(case, 1200)
    original_close = provider.close

    async def restoring_close() -> None:
        case.wav_path.write_bytes(original)
        case.wav_path.chmod(0o600)
        await original_close()

    provider.close = restoring_close

    async def factory(_turn_detection):
        case.wav_path.write_bytes(mutated)
        case.wav_path.chmod(0o600)
        return provider

    result = await runner.run_vad_attempt(
        config, case, 0, configuration_id="A1", silence_duration_ms=1200,
        provider_factory=factory,
    )
    assert result.outcome is runner.VadAttemptOutcome.COMPLETED
    first_sample = struct.unpack("<f", provider.frames[0].pcm_f32le[:4])[0]
    assert first_sample == pytest.approx(1200 / 32768.0)


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


@pytest.mark.asyncio
async def test_real_factory_requires_explicit_model_before_selector(monkeypatch) -> None:
    calls = 0

    async def selector(**_kwargs):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(runner, "select_environment_streaming_speech", selector)
    with pytest.raises(ValueError, match="PROVIDER_UNAVAILABLE"):
        await runner.create_real_streaming_provider(
            {
                "LIVE_VOICE_SPEECH_PROVIDER": "openai",
                "LIVE_VOICE_SPEECH_API_BASE": "https://api.openai.com/v1",
                "LIVE_VOICE_SPEECH_API_KEY": "private-provider-sentinel",
            }
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_real_factory_rejects_nonstreaming_selection(monkeypatch) -> None:
    async def selector(**_kwargs):
        return SimpleNamespace(tier=runner.SpeechRouteTier.TEXT, provider=None)

    monkeypatch.setattr(runner, "select_environment_streaming_speech", selector)
    with pytest.raises(ValueError, match="PROVIDER_UNAVAILABLE"):
        await runner.create_real_streaming_provider(
            {
                "LIVE_VOICE_SPEECH_PROVIDER": "openai",
                "LIVE_VOICE_SPEECH_API_BASE": "https://api.openai.com/v1",
                "LIVE_VOICE_SPEECH_API_KEY": "private-provider-sentinel",
                "LIVE_VOICE_SPEECH_STT_MODEL": "gpt-4o-mini-transcribe-2025-12-15",
            }
        )


def test_parse_semantic_configuration_is_closed_and_builds_exact_detection() -> None:
    auto = runner.parse_configuration("B_AUTO")
    high = runner.parse_configuration("B_HIGH")
    assert auto.silence_duration_ms is None and auto.semantic_eagerness.value == "auto"
    assert high.silence_duration_ms is None and high.semantic_eagerness.value == "high"
    assert runner.turn_detection_for(auto).semantic_vad.eagerness.value == "auto"
    assert runner.turn_detection_for(runner.parse_configuration("A1_1200")).server_vad.silence_duration_ms == 1200
    assert runner.parse_configuration("A1").silence_duration_ms == 1200
    assert runner.parse_configuration("E1").silence_duration_ms == 900
    assert runner.parse_configuration("E2").silence_duration_ms == 800
    assert runner.turn_detection_for(runner.parse_configuration("E1")).server_vad.silence_duration_ms == 900
    with pytest.raises(ValueError):
        runner.VadConfiguration("bad", runner.RecognitionTurnDetectionMode.SEMANTIC_VAD, 1200, runner.SemanticVadEagerness.AUTO)


def test_semantic_experiments_are_separate_three_arm_blocks_and_report_mode_fields(tmp_path: Path) -> None:
    common = dict(run_id="semantic-auto", mode="pilot", manifest_path=tmp_path / "manifest.json", output_path=tmp_path / "report.json", git_commit="a" * 40, source_clean=True)
    auto = runner.VadBenchmarkConfig(**common, experiment="semantic-auto")
    high = runner.VadBenchmarkConfig(**{**common, "run_id": "semantic-high", "output_path": tmp_path / "high.json"}, experiment="semantic-high")
    assert auto.configuration_sequence == (("A1_1200", 1200), ("B_AUTO", None), ("A2_1200", 1200))
    assert high.configuration_sequence == (("A1_1200", 1200), ("B_HIGH", None), ("A2_1200", 1200))
    assert runner.REPORT_SCHEMA_VERSION.endswith("v1")


def test_semantic_attempt_fields_are_closed_and_failed_timings_are_null() -> None:
    completed = runner.VadAttemptResult.completed("B_AUTO", None, "case-a", 0, final_voiced_frame_to_eot_ms=1.0, eot_to_final_ms=1.0, final_voiced_frame_to_final_ms=2.0, turn_detection_mode="semantic_vad", semantic_eagerness="auto")
    assert completed.turn_detection_mode == "semantic_vad"
    assert completed.silence_duration_ms is None
    assert completed.semantic_eagerness == "auto"
    failed = runner.VadAttemptResult.failed("B_HIGH", None, "case-a", 0, runner.VadAttemptReason.TIMEOUT, turn_detection_mode="semantic_vad", semantic_eagerness="high")
    assert failed.final_voiced_frame_to_eot_ms is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("disposition", "expected_outcome"),
    (
        (
            RecognitionCommitDisposition.SEMANTIC_VAD_OBSERVED,
            runner.VadAttemptOutcome.COMPLETED,
        ),
        (
            RecognitionCommitDisposition.SERVER_VAD_OBSERVED,
            runner.VadAttemptOutcome.FAILED,
        ),
    ),
)
async def test_semantic_attempt_uses_native_detection_and_mode_specific_commit_truth(
    tmp_path: Path,
    disposition,
    expected_outcome,
) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    case = manifest.cases[0]
    provider = SemanticFakeProvider(case, disposition=disposition)
    clock = ManualClock()

    async def factory(turn_detection):
        assert turn_detection.mode is runner.RecognitionTurnDetectionMode.SEMANTIC_VAD
        return provider

    result = await runner.run_vad_attempt(
        config,
        case,
        0,
        configuration_id="B_AUTO",
        silence_duration_ms=None,
        provider_factory=factory,
        monotonic=clock.now,
        sleep=clock.sleep,
    )

    assert result.outcome is expected_outcome
    assert result.turn_detection_mode == "semantic_vad"
    assert result.semantic_eagerness == "auto"
    assert result.silence_duration_ms is None
    if expected_outcome is runner.VadAttemptOutcome.COMPLETED:
        assert result.reason is runner.VadAttemptReason.OK
        assert result.final_voiced_frame_to_eot_ms is not None
    else:
        assert result.reason is runner.VadAttemptReason.PROVIDER_PROTOCOL
        assert result.final_voiced_frame_to_eot_ms is None
        assert result.eot_to_final_ms is None
        assert result.final_voiced_frame_to_final_ms is None


def test_semantic_summaries_preserve_mode_eagerness_and_explicit_arm_order() -> None:
    metrics = {
        "final_voiced_frame_to_eot_ms": 300.0,
        "eot_to_final_ms": 100.0,
        "final_voiced_frame_to_final_ms": 400.0,
        "provider_reported_speech_end_ms": 1000.0,
        "pacing_p50_ms": 0.0,
        "pacing_p95_ms": 0.0,
        "pacing_max_ms": 0.0,
    }
    attempts = (
        runner.VadAttemptResult.completed(
            "A2_1200", 1200, "case-a", 0, **metrics
        ),
        runner.VadAttemptResult.completed(
            "B_AUTO",
            None,
            "case-a",
            0,
            turn_detection_mode="semantic_vad",
            semantic_eagerness="auto",
            **metrics,
        ),
        runner.VadAttemptResult.completed(
            "A1_1200", 1200, "case-a", 0, **metrics
        ),
    )

    summaries = runner._safe_summary(attempts)

    assert [summary.configuration_id for summary in summaries] == [
        "A1_1200",
        "B_AUTO",
        "A2_1200",
    ]
    semantic = summaries[1]
    assert semantic.turn_detection_mode == "semantic_vad"
    assert semantic.silence_duration_ms is None
    assert semantic.semantic_eagerness == "auto"
    assert semantic.eot_to_final_ms_p50 == 100.0
    assert semantic.eot_to_final_ms_p95 == 100.0
    assert semantic.total_ms_p50 == 400.0
    assert semantic.total_ms_p95 == 400.0


@pytest.mark.asyncio
async def test_semantic_screening_uses_exact_three_arm_population_and_report_labels(
    tmp_path: Path,
) -> None:
    base = _config(tmp_path)
    config = replace(
        base,
        run_id="semantic-auto-pilot",
        experiment="semantic-auto",
    )
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    calls = []

    async def attempt_runner(_config, case, attempt_index, **kwargs):
        configuration = runner.parse_configuration(kwargs["configuration_id"])
        calls.append((configuration.configuration_id, case.case_id, attempt_index))
        duration = 300.0 if configuration.silence_duration_ms is None else float(
            configuration.silence_duration_ms
        )
        return runner.VadAttemptResult.completed(
            configuration.configuration_id,
            configuration.silence_duration_ms,
            case.case_id,
            attempt_index,
            final_voiced_frame_to_eot_ms=duration,
            eot_to_final_ms=100.0,
            final_voiced_frame_to_final_ms=duration + 100.0,
            provider_reported_speech_end_ms=1000.0,
            pacing_p50_ms=0.0,
            pacing_p95_ms=0.0,
            pacing_max_ms=0.0,
            turn_detection_mode=configuration.mode.value,
            semantic_eagerness=(
                configuration.semantic_eagerness.value
                if configuration.semantic_eagerness is not None
                else None
            ),
        )

    async def unused_provider_factory(_turn_detection):
        raise AssertionError("attempt runner must own the fake provider boundary")

    report = await runner.run_screening(
        config,
        manifest,
        provider_factory=unused_provider_factory,
        attempt_runner=attempt_runner,
    )

    assert len(calls) == 12
    assert [item[0] for item in calls[::4]] == [
        "A1_1200",
        "B_AUTO",
        "A2_1200",
    ]
    assert report.experiment == "semantic-auto"
    assert len(report.attempts) == 12
    assert {summary.turn_detection_mode for summary in report.summaries} == {
        "server_vad",
        "semantic_vad",
    }


@pytest.mark.parametrize("experiment", ("semantic-auto", "semantic-high"))
def test_cli_accepts_only_closed_semantic_experiment_selector(
    tmp_path: Path,
    experiment: str,
) -> None:
    manifest_path, _ = _corpus(tmp_path)
    config = runner.parse_args(
        [
            "pilot",
            "--experiment",
            experiment,
            "--manifest",
            str(manifest_path),
            "--output",
            str(tmp_path / f"{experiment}.json"),
            "--run-id",
            experiment,
            "--git-commit",
            "a" * 40,
        ],
        source_commit="a" * 40,
        source_clean=True,
    )

    assert config.experiment == experiment
    with pytest.raises(ValueError, match="VAD_BENCHMARK_CONFIG_INVALID"):
        runner.parse_args(
            [
                "pilot",
                "--experiment",
                "semantic-auto-high",
                "--manifest",
                str(manifest_path),
                "--output",
                str(tmp_path / "invalid.json"),
                "--run-id",
                "invalid-experiment",
                "--git-commit",
                "a" * 40,
            ],
            source_commit="a" * 40,
            source_clean=True,
        )


@pytest.mark.parametrize(
    ("experiment", "candidate_id", "expected"),
    (
        ("semantic-auto", "B_AUTO", "SEMANTIC_VAD_AUTO_ELIGIBLE"),
        ("semantic-high", "B_HIGH", "SEMANTIC_VAD_HIGH_ELIGIBLE"),
    ),
)
def test_semantic_formal_decision_requires_integrity_and_per_case_total_gain(
    tmp_path: Path,
    experiment: str,
    candidate_id: str,
    expected: str,
) -> None:
    base = _config(tmp_path, mode="run")
    config = replace(base, experiment=experiment)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)

    assert runner._decision(
        config,
        _semantic_formal_attempts(manifest, candidate_id=candidate_id),
    ) == expected
    assert runner._decision(
        config,
        _semantic_formal_attempts(
            manifest,
            candidate_id=candidate_id,
            candidate_eot_ms=1300.0,
        ),
    ) == "SEMANTIC_VAD_NO_MATERIAL_GAIN"
    assert runner._decision(
        config,
        _semantic_formal_attempts(
            manifest,
            candidate_id=candidate_id,
            failed_reason=runner.VadAttemptReason.EARLY_EOT,
        ),
    ) == "SEMANTIC_VAD_INTEGRITY_REJECTED"
    assert runner._decision(
        config,
        _semantic_formal_attempts(
            manifest,
            candidate_id=candidate_id,
            failed_reason=runner.VadAttemptReason.PROVIDER_PROTOCOL,
        ),
    ) == "SEMANTIC_VAD_PROVIDER_INCOMPATIBLE"
    assert runner._decision(
        config,
        _semantic_formal_attempts(
            manifest,
            candidate_id=candidate_id,
            a2_eot_ms=1500.0,
        ),
    ) == "SEMANTIC_VAD_EVIDENCE_INCOMPLETE"


@pytest.mark.asyncio
async def test_injected_semantic_main_writes_exact_three_arm_private_report(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _corpus(tmp_path)
    output = tmp_path / "semantic-auto-report.json"
    clock = ManualClock()
    allocation_index = 0

    async def provider_factory(turn_detection):
        nonlocal allocation_index
        case = manifest.cases[allocation_index % len(manifest.cases)]
        allocation_index += 1
        if turn_detection.mode is runner.RecognitionTurnDetectionMode.SEMANTIC_VAD:
            return SemanticFakeProvider(case)
        assert turn_detection.server_vad is not None
        return FakeProvider(case, turn_detection.server_vad.silence_duration_ms)

    exit_code = await runner._main(
        [
            "pilot",
            "--experiment",
            "semantic-auto",
            "--manifest",
            str(manifest_path),
            "--output",
            str(output),
            "--run-id",
            "semantic-auto-injected",
            "--git-commit",
            "a" * 40,
        ],
        environ={"LIVE_VOICE_SPEECH_STT_MODEL": "gpt-4o-mini-transcribe"},
        source_commit="a" * 40,
        source_clean=True,
        provider_factory=provider_factory,
        monotonic=clock.now,
        sleep=clock.sleep,
        source_state_factory=lambda: ("a" * 40, True),
    )

    assert exit_code == 0
    assert output.stat().st_mode & 0o777 == 0o600
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == "live-voice.vad-eot-causal-report.v1"
    assert report["experiment"] == "semantic-auto"
    assert report["decision"] == "READY_FOR_SCREENING"
    assert len(report["attempts"]) == 12
    assert [
        summary["configuration_id"] for summary in report["summaries"][::4]
    ] == ["A1_1200", "B_AUTO", "A2_1200"]
    serialized = output.read_text(encoding="utf-8")
    assert "private-item" not in serialized
    assert "first clause" not in serialized


def test_report_is_private_closed_and_excludes_failed_samples(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    attempts = _complete_pilot_attempts(manifest)
    failed_index = next(
        index
        for index, attempt in enumerate(attempts)
        if attempt.configuration_id == "E1" and attempt.case_id == "internal-pause-1000"
    )
    attempts[failed_index] = runner.VadAttemptResult.failed(
        "E1", 900, "internal-pause-1000", 0,
        runner.VadAttemptReason.EARLY_EOT,
        speech_started_count=1, speech_stopped_count=1,
        committed_count=1, exact_identity=True,
        cleanup_complete=True, pacing_valid=True,
    )
    report = runner.build_report(
        config,
        corpus_id="vad-en-v1",
        corpus_manifest_sha256="b" * 64,
        provider_id="openai",
        provider_class="OpenAIStreamingSpeechProvider",
        stt_model="gpt-4o-mini-transcribe",
        attempts=tuple(attempts),
        decision="READY_FOR_SCREENING",
    )
    runner.write_vad_benchmark_report(config.output_path, report)
    loaded = json.loads(config.output_path.read_text())
    assert config.output_path.stat().st_mode & 0o077 == 0
    failed_summary = next(
        summary for summary in loaded["summaries"]
        if summary["configuration_id"] == "E1"
        and summary["case_id"] == "internal-pause-1000"
    )
    assert failed_summary["completed"] == 0
    assert failed_summary["failed"] == 1
    assert failed_summary["eot_ms_p50"] is None
    assert "private-item" not in config.output_path.read_text()
    with pytest.raises(FileExistsError):
        runner.write_vad_benchmark_report(config.output_path, report)


def test_report_reparse_is_deep_and_failure_atomic(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    report = runner.build_report(
        config,
        corpus_id="vad-en-v1",
        corpus_manifest_sha256="b" * 64,
        provider_id="openai",
        provider_class="OpenAIStreamingSpeechProvider",
        stt_model="gpt-4o-mini-transcribe-2025-12-15",
        attempts=tuple(_complete_pilot_attempts(manifest)),
        decision="READY_FOR_SCREENING",
    )
    real_loads = runner.json.loads

    def tampered_loads(payload):
        loaded = real_loads(payload)
        loaded["decision"] = "FIXED_THRESHOLD_REJECTED"
        return loaded

    monkeypatch.setattr(runner.json, "loads", tampered_loads)
    with pytest.raises(ValueError, match="VAD_BENCHMARK_REPORT_INVALID"):
        runner.write_vad_benchmark_report(config.output_path, report)
    assert not config.output_path.exists()


def test_report_rejects_semantically_impossible_population_before_write(tmp_path: Path) -> None:
    config = _config(tmp_path)
    report = runner.build_report(
        config,
        corpus_id="vad-en-v1",
        corpus_manifest_sha256="b" * 64,
        provider_id="openai",
        provider_class="OpenAIStreamingSpeechProvider",
        stt_model="gpt-4o-mini-transcribe-2025-12-15",
        attempts=(),
        decision="INCONCLUSIVE",
    )
    with pytest.raises(ValueError, match="VAD_BENCHMARK_REPORT_INVALID"):
        runner.write_vad_benchmark_report(config.output_path, report)
    assert not config.output_path.exists()


@pytest.mark.asyncio
async def test_screening_order_is_exact(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
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


def test_formal_decision_rejects_lower_threshold_integrity_failures(tmp_path: Path) -> None:
    config = _config(tmp_path, mode="run")
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    attempts = []
    for configuration_id, threshold in runner.CONFIGURATION_SEQUENCE:
        for case in manifest.cases:
            for attempt_index in range(5):
                if configuration_id in {"E1", "E2"} and case.pause_ms == 1000:
                    attempts.append(
                        runner.VadAttemptResult.failed(
                            configuration_id, threshold, case.case_id, attempt_index,
                            runner.VadAttemptReason.EARLY_EOT,
                        )
                    )
                else:
                    attempts.append(
                        runner.VadAttemptResult.completed(
                            configuration_id, threshold, case.case_id, attempt_index,
                            final_voiced_frame_to_eot_ms=float(threshold),
                            eot_to_final_ms=100.0,
                            final_voiced_frame_to_final_ms=float(threshold + 100),
                            provider_reported_speech_end_ms=None,
                            pacing_p50_ms=0.0, pacing_p95_ms=0.0, pacing_max_ms=0.0,
                        )
                    )
    assert runner._decision(config, tuple(attempts)) == "FIXED_THRESHOLD_REJECTED"


@pytest.mark.asyncio
async def test_screening_rejects_corpus_mutated_before_report(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = support.load_vad_corpus_manifest(config.manifest_path)
    calls = 0

    async def attempt(_config, case, attempt_index, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 16:
            payload = bytearray(case.wav_path.read_bytes())
            payload[100] ^= 1
            case.wav_path.write_bytes(payload)
            case.wav_path.chmod(0o600)
        return runner.VadAttemptResult.completed(
            kwargs["configuration_id"], kwargs["silence_duration_ms"],
            case.case_id, attempt_index,
            final_voiced_frame_to_eot_ms=float(kwargs["silence_duration_ms"]),
            eot_to_final_ms=10.0,
            final_voiced_frame_to_final_ms=float(kwargs["silence_duration_ms"] + 10),
            provider_reported_speech_end_ms=None,
            pacing_p50_ms=0.0, pacing_p95_ms=0.0, pacing_max_ms=0.0,
        )

    with pytest.raises(ValueError, match="MANIFEST_INVALID"):
        await runner.run_screening(
            config, manifest, provider_factory=lambda _: None,
            attempt_runner=attempt,
        )


@pytest.mark.asyncio
async def test_injected_main_writes_exact_model_and_rechecks_source(
    tmp_path: Path, capsys
) -> None:
    manifest_path, manifest = _corpus(tmp_path)
    output = tmp_path / "main-report.json"
    clock = ManualClock()
    provider_calls = 0

    async def factory(turn_detection):
        nonlocal provider_calls
        case = manifest.cases[provider_calls % len(manifest.cases)]
        provider_calls += 1
        return FakeProvider(
            case, turn_detection.server_vad.silence_duration_ms
        )

    source_checks = 0

    def source_state():
        nonlocal source_checks
        source_checks += 1
        return "a" * 40, True

    exit_code = await runner._main(
        [
            "pilot", "--manifest", str(manifest_path),
            "--output", str(output), "--run-id", "vad-main-test",
            "--git-commit", "a" * 40,
        ],
        environ={
            "LIVE_VOICE_SPEECH_STT_MODEL":
                "gpt-4o-mini-transcribe-2025-12-15"
        },
        provider_factory=factory,
        monotonic=clock.now,
        sleep=clock.sleep,
        source_state_factory=source_state,
    )
    assert exit_code == 0
    assert source_checks == 2
    assert provider_calls == 16
    loaded = json.loads(output.read_text())
    assert loaded["stt_model"] == "gpt-4o-mini-transcribe-2025-12-15"
    assert capsys.readouterr().out == (
        '{"run_id":"vad-main-test","decision":"READY_FOR_SCREENING"}\n'
    )


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


def test_cli_unknown_secret_argument_is_never_echoed(tmp_path: Path) -> None:
    sentinel = "PRIVATE_CLI_SENTINEL"
    completed = subprocess.run(
        [sys.executable, str(RUNNER_PATH), "pilot", "--api-key", sentinel],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode != 0
    assert completed.stdout == ""
    assert completed.stderr == "VAD_EOT_BENCHMARK_FAILED\n"
    assert sentinel not in completed.stderr
