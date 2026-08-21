from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice.speech_ports import (
    ProviderRef,
    SynthesisEventKind,
)
from jiuwenswarm.server.live_voice.streaming_speech import StreamingSynthesisEvent


ROOT = Path(__file__).parents[3]
RUNNER_PATH = ROOT / "scripts/live_voice/tts_provider_connection_causal_benchmark.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = _load(RUNNER_PATH, "tts_provider_connection_causal_benchmark")


def test_config_closes_population_source_and_output_boundaries(tmp_path: Path) -> None:
    config = runner.TtsConnectionBenchmarkConfig(
        run_id="tts-connection-pilot",
        mode="pilot",
        output_path=(tmp_path / "report.json").resolve(),
        git_commit="a" * 40,
        source_clean=True,
        source_label="A1",
        model="gpt-4o-mini-tts-2025-12-15",
        voice="marin",
        output_rate_hz=24_000,
    )

    assert config.pair_count == 1
    assert config.expected_attempt_count == 2

    with pytest.raises(ValueError, match="TTS_CONNECTION_BENCHMARK_CONFIG_INVALID"):
        runner.TtsConnectionBenchmarkConfig(
            run_id="tts-connection-run",
            mode="run",
            output_path=Path("relative.json"),
            git_commit="a" * 40,
            source_clean=True,
            source_label="B",
            model="gpt-4o-mini-tts-2025-12-15",
            voice="marin",
            output_rate_hz=24_000,
        )

    with pytest.raises(ValueError, match="TTS_CONNECTION_BENCHMARK_CONFIG_INVALID"):
        runner.TtsConnectionBenchmarkConfig(
            run_id="tts-connection-pilot",
            mode="pilot",
            output_path=(tmp_path / "candidate-pilot.json").resolve(),
            git_commit="a" * 40,
            source_clean=True,
            source_label="B",
            model="gpt-4o-mini-tts-2025-12-15",
            voice="marin",
            output_rate_hz=24_000,
        )


def test_completed_attempt_requires_causal_trace_and_monotonic_offsets() -> None:
    cold = runner.TtsConnectionAttempt(
        pair_index=0,
        position=runner.TtsAttemptPosition.COLD,
        outcome=runner.TtsAttemptOutcome.COMPLETED,
        reason=None,
        connection_reused=False,
        request_started_ms=0.0,
        tcp_connect_started_ms=1.0,
        tcp_connect_completed_ms=2.0,
        tls_started_ms=2.1,
        tls_completed_ms=3.0,
        response_headers_ms=4.0,
        transport_open_ms=4.1,
        first_audio_event_ms=5.0,
        first_pcm_ms=5.2,
        completed_ms=7.0,
        stream_closed_ms=7.1,
    )
    warm = runner.TtsConnectionAttempt(
        pair_index=0,
        position=runner.TtsAttemptPosition.WARM,
        outcome=runner.TtsAttemptOutcome.COMPLETED,
        reason=None,
        connection_reused=True,
        request_started_ms=0.0,
        tcp_connect_started_ms=None,
        tcp_connect_completed_ms=None,
        tls_started_ms=None,
        tls_completed_ms=None,
        response_headers_ms=1.0,
        transport_open_ms=1.1,
        first_audio_event_ms=2.0,
        first_pcm_ms=2.2,
        completed_ms=4.0,
        stream_closed_ms=4.1,
    )

    assert cold.first_pcm_ms == 5.2
    assert warm.connection_reused is True

    control_warm = runner.TtsConnectionAttempt(
        pair_index=0,
        position=runner.TtsAttemptPosition.WARM,
        outcome=runner.TtsAttemptOutcome.COMPLETED,
        reason=None,
        connection_reused=False,
        request_started_ms=0.0,
        tcp_connect_started_ms=0.5,
        tcp_connect_completed_ms=1.0,
        tls_started_ms=1.1,
        tls_completed_ms=1.5,
        response_headers_ms=2.0,
        transport_open_ms=2.1,
        first_audio_event_ms=3.0,
        first_pcm_ms=3.2,
        completed_ms=4.0,
        stream_closed_ms=4.1,
    )
    assert control_warm.connection_reused is False

    with pytest.raises(ValueError, match="TTS_CONNECTION_ATTEMPT_INVALID"):
        runner.TtsConnectionAttempt(
            pair_index=0,
            position=runner.TtsAttemptPosition.COLD,
            outcome=runner.TtsAttemptOutcome.COMPLETED,
            reason=None,
            connection_reused=False,
            request_started_ms=0.0,
            tcp_connect_started_ms=2.0,
            tcp_connect_completed_ms=1.0,
            tls_started_ms=2.1,
            tls_completed_ms=3.0,
            response_headers_ms=4.0,
            transport_open_ms=4.1,
            first_audio_event_ms=5.0,
            first_pcm_ms=5.2,
            completed_ms=7.0,
            stream_closed_ms=7.1,
        )


def test_noncompleted_attempt_cannot_claim_latency_or_reuse() -> None:
    failed = runner.TtsConnectionAttempt.failed(
        pair_index=2,
        position=runner.TtsAttemptPosition.WARM,
        outcome=runner.TtsAttemptOutcome.FAILED,
        reason="PROVIDER_FAILED",
    )

    assert failed.connection_reused is None
    assert failed.first_pcm_ms is None

    with pytest.raises(ValueError, match="TTS_CONNECTION_ATTEMPT_INVALID"):
        runner.TtsConnectionAttempt(
            pair_index=2,
            position=runner.TtsAttemptPosition.WARM,
            outcome=runner.TtsAttemptOutcome.FAILED,
            reason="PROVIDER_FAILED",
            connection_reused=None,
            request_started_ms=0.0,
            tcp_connect_started_ms=None,
            tcp_connect_completed_ms=None,
            tls_started_ms=None,
            tls_completed_ms=None,
            response_headers_ms=None,
            transport_open_ms=None,
            first_audio_event_ms=None,
            first_pcm_ms=2.0,
            completed_ms=None,
            stream_closed_ms=None,
        )


class ManualClock:
    def __init__(self) -> None:
        self.value = 100.0

    def now(self) -> float:
        return self.value

    def advance_ms(self, value: float) -> float:
        self.value += value / 1000
        return self.value


class FakeConformance:
    def __init__(self) -> None:
        self.responses = []

    def activate_response(self, ref) -> None:
        self.responses.append(ref)


class FakeSynthesisProvider:
    def __init__(
        self,
        observer: Callable[[object, str, float], None],
        clock: ManualClock,
        *,
        reuse_warm: bool,
    ) -> None:
        self.observer = observer
        self.clock = clock
        self.reuse_warm = reuse_warm
        self.conformance = FakeConformance()
        self.cleanup_snapshot = SimpleNamespace(clean=True)
        self.requests = []
        self.events: asyncio.Queue[StreamingSynthesisEvent] = asyncio.Queue()
        self.close_count = 0

    async def open_synthesis(self, request, *, on_transport_open=None) -> None:
        self.requests.append(request)
        warm_reuse = request.ref.stream_generation == 1 and self.reuse_warm
        if not warm_reuse:
            for name in (
                "connect_tcp.started",
                "connect_tcp.complete",
                "start_tls.started",
                "start_tls.complete",
            ):
                self.observer(request.ref, name, self.clock.advance_ms(1))
        self.observer(
            request.ref, "send_request_headers.started", self.clock.advance_ms(1)
        )
        self.observer(
            request.ref,
            "receive_response_headers.complete",
            self.clock.advance_ms(1),
        )
        self.clock.advance_ms(1)
        assert on_transport_open is not None
        on_transport_open()
        await self.events.put(
            StreamingSynthesisEvent(
                request.ref,
                ProviderRef("openai-streaming-speech", "formal"),
                0,
                0,
                SynthesisEventKind.STARTED,
                request.sample_rate_hz,
            )
        )
        self.observer(
            request.ref, "first_audio_event", self.clock.advance_ms(1)
        )
        await self.events.put(
            StreamingSynthesisEvent(
                request.ref,
                ProviderRef("openai-streaming-speech", "formal"),
                1,
                0,
                SynthesisEventKind.CHUNK,
                request.sample_rate_hz,
                sample_count=2,
                pcm_s16le=b"\x00\x00\x00\x00",
            )
        )
        self.clock.advance_ms(1)
        await self.events.put(
            StreamingSynthesisEvent(
                request.ref,
                ProviderRef("openai-streaming-speech", "formal"),
                2,
                2,
                SynthesisEventKind.COMPLETED,
                request.sample_rate_hz,
            )
        )

    async def next_synthesis_event(self, _ref, *, timeout_seconds: float):
        assert timeout_seconds > 0
        return await self.events.get()

    async def close(self) -> None:
        self.close_count += 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_label", "reuse_warm", "expected_reuse"),
    (("A1", False, False), ("B", True, True)),
)
async def test_pair_runner_uses_one_provider_and_classifies_exact_trace(
    tmp_path: Path,
    source_label: str,
    reuse_warm: bool,
    expected_reuse: bool,
) -> None:
    config = runner.TtsConnectionBenchmarkConfig(
        run_id="tts-connection-run",
        mode="run",
        output_path=(tmp_path / "report.json").resolve(),
        git_commit="a" * 40,
        source_clean=True,
        source_label=source_label,
        model="gpt-4o-mini-tts-2025-12-15",
        voice="marin",
        output_rate_hz=24_000,
    )
    clock = ManualClock()
    providers: list[FakeSynthesisProvider] = []

    def provider_factory(observer):
        provider = FakeSynthesisProvider(
            observer, clock, reuse_warm=reuse_warm
        )
        providers.append(provider)
        return provider

    attempts, cleanup_complete = await runner.run_provider_pair(
        config,
        pair_index=0,
        provider_factory=provider_factory,
        monotonic=clock.now,
    )

    assert cleanup_complete is True
    assert len(providers) == 1
    assert providers[0].close_count == 1
    assert [request.ref.stream_generation for request in providers[0].requests] == [
        0,
        1,
    ]
    assert [attempt.position for attempt in attempts] == [
        runner.TtsAttemptPosition.COLD,
        runner.TtsAttemptPosition.WARM,
    ]
    assert [attempt.connection_reused for attempt in attempts] == [
        False,
        expected_reuse,
    ]
    assert all(
        attempt.outcome is runner.TtsAttemptOutcome.COMPLETED
        for attempt in attempts
    )
    assert attempts[0].request_started_ms == 0.0
    assert attempts[0].response_headers_ms < attempts[0].first_pcm_ms


def _completed_attempt(
    pair_index: int,
    position,
    *,
    reused: bool,
    first_pcm_ms: float,
):
    connection_offset = float(pair_index + 1)
    if reused:
        tcp_started = tcp_completed = tls_started = tls_completed = None
        headers = 2.0
    else:
        tcp_started = connection_offset
        tcp_completed = connection_offset + 1.0
        tls_started = connection_offset + 1.1
        tls_completed = connection_offset + 2.0
        headers = connection_offset + 3.0
    return runner.TtsConnectionAttempt(
        pair_index,
        position,
        runner.TtsAttemptOutcome.COMPLETED,
        None,
        reused,
        0.0,
        tcp_started,
        tcp_completed,
        tls_started,
        tls_completed,
        headers,
        headers + 0.1,
        first_pcm_ms - 0.2,
        first_pcm_ms,
        first_pcm_ms + 1.0,
        first_pcm_ms + 1.0,
    )


def test_report_round_trip_is_private_closed_and_failure_atomic(
    tmp_path: Path,
) -> None:
    output = (tmp_path / "report.json").resolve()
    config = runner.TtsConnectionBenchmarkConfig(
        run_id="tts-connection-run",
        mode="run",
        output_path=output,
        git_commit="a" * 40,
        source_clean=True,
        source_label="B",
        model="gpt-4o-mini-tts-2025-12-15",
        voice="marin",
        output_rate_hz=24_000,
    )
    attempts = tuple(
        attempt
        for pair_index in range(3)
        for attempt in (
            _completed_attempt(
                pair_index,
                runner.TtsAttemptPosition.COLD,
                reused=False,
                first_pcm_ms=120.0 + pair_index,
            ),
            _completed_attempt(
                pair_index,
                runner.TtsAttemptPosition.WARM,
                reused=True,
                first_pcm_ms=50.0 + pair_index,
            ),
        )
    )
    report = runner.build_report(
        config,
        provider_id="openai-streaming-speech",
        provider_class="OpenAIStreamingSpeechProvider",
        python_version="3.11.15",
        httpx_version="0.28.1",
        httpcore_version="1.0.9",
        attempts=attempts,
        cleanup_complete=(True, True, True),
    )

    runner.write_private_report(output, report)

    assert runner.parse_report(output) == report
    assert os.stat(output).st_mode & 0o777 == 0o600
    payload = json.loads(output.read_text())
    assert payload["schema_version"] == runner.REPORT_SCHEMA_VERSION
    assert payload["summaries"][1]["first_pcm_ms_p50"] == 51.0
    assert set(payload["forbidden_effects"].values()) == {0}
    assert "text" not in payload
    with pytest.raises(FileExistsError):
        runner.write_private_report(output, report)

    tampered = tmp_path / "tampered.json"
    payload["private_extra"] = "sentinel"
    tampered.write_text(json.dumps(payload))
    tampered.chmod(0o600)
    with pytest.raises(ValueError, match="TTS_CONNECTION_REPORT_INVALID"):
        runner.parse_report(tampered)


@pytest.mark.asyncio
async def test_main_runs_three_independent_pairs_and_writes_closed_report(
    tmp_path: Path,
) -> None:
    output = (tmp_path / "formal.json").resolve()
    clock = ManualClock()
    providers: list[FakeSynthesisProvider] = []

    def provider_factory(observer):
        provider = FakeSynthesisProvider(observer, clock, reuse_warm=False)
        providers.append(provider)
        return provider

    def source_state() -> tuple[str, bool]:
        return "a" * 40, True

    result = await runner._main(
        (
            "run",
            "--output",
            str(output),
            "--run-id",
            "tts-connection-formal",
            "--git-commit",
            "a" * 40,
            "--source-label",
            "A1",
        ),
        environ={
            "LIVE_VOICE_SPEECH_TTS_MODEL": "gpt-4o-mini-tts-2025-12-15",
            "LIVE_VOICE_SPEECH_TTS_VOICE": "marin",
        },
        provider_factory=provider_factory,
        monotonic=clock.now,
        source_state_factory=source_state,
    )

    report = runner.parse_report(output)
    assert result == 0
    assert len(providers) == 3
    assert all(provider.close_count == 1 for provider in providers)
    assert len(report.attempts) == 6
    assert report.decision == "CONTROL_VALID"
    assert report.cleanup_counts == {"pairs": 3, "completed": 3, "incomplete": 0}


def test_cli_errors_are_stable_and_do_not_echo_unknown_private_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    private = "private-cli-sentinel"

    result = runner.main(("pilot", "--api-key", private))

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err.strip() == "TTS_CONNECTION_BENCHMARK_FAILED"
    assert private not in captured.out + captured.err


def test_process_watchdog_terminates_cancellation_hostile_asyncio_worker() -> None:
    hostile = """
import asyncio

async def hostile():
    while True:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            continue

async def run():
    await asyncio.wait_for(hostile(), timeout=0.01)

asyncio.run(run())
"""
    started = time.monotonic()

    result = runner._run_process_with_watchdog(
        (sys.executable, "-c", hostile),
        environ=os.environ,
        timeout_seconds=0.1,
    )

    assert result.timed_out is True
    assert result.returncode is None
    assert result.stdout == ""
    assert time.monotonic() - started < 2.0


class DuplicateTraceProvider(FakeSynthesisProvider):
    async def open_synthesis(self, request, *, on_transport_open=None) -> None:
        await super().open_synthesis(
            request, on_transport_open=on_transport_open
        )
        self.observer(
            request.ref,
            "receive_response_headers.complete",
            self.clock.advance_ms(1),
        )


@pytest.mark.asyncio
async def test_duplicate_trace_is_invalid_and_never_retried(tmp_path: Path) -> None:
    config = runner.TtsConnectionBenchmarkConfig(
        "tts-connection-run",
        "run",
        (tmp_path / "report.json").resolve(),
        "a" * 40,
        True,
        "A1",
        "gpt-4o-mini-tts-2025-12-15",
        "marin",
        24_000,
    )
    clock = ManualClock()
    providers = []

    def provider_factory(observer):
        provider = DuplicateTraceProvider(observer, clock, reuse_warm=False)
        providers.append(provider)
        return provider

    attempts, cleanup_complete = await runner.run_provider_pair(
        config,
        pair_index=0,
        provider_factory=provider_factory,
        monotonic=clock.now,
    )

    assert cleanup_complete is True
    assert len(providers) == 1
    assert len(providers[0].requests) == 1
    assert [attempt.outcome for attempt in attempts] == [
        runner.TtsAttemptOutcome.INVALID,
        runner.TtsAttemptOutcome.UNKNOWN,
    ]
    assert [attempt.reason for attempt in attempts] == [
        "TRACE_REUSE_UNPROVEN",
        "PAIR_ABORTED",
    ]


@pytest.mark.asyncio
async def test_timeout_is_unknown_and_does_not_start_warm_or_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = runner.TtsConnectionBenchmarkConfig(
        "tts-connection-run",
        "run",
        (tmp_path / "report.json").resolve(),
        "a" * 40,
        True,
        "A1",
        "gpt-4o-mini-tts-2025-12-15",
        "marin",
        24_000,
    )
    clock = ManualClock()

    class SlowProvider(FakeSynthesisProvider):
        def __init__(self, observer, clock) -> None:
            super().__init__(observer, clock, reuse_warm=False)
            self.open_count = 0

        async def open_synthesis(self, request, *, on_transport_open=None) -> None:
            self.open_count += 1
            await asyncio.Event().wait()

    providers = []

    def provider_factory(observer):
        provider = SlowProvider(observer, clock)
        providers.append(provider)
        return provider

    monkeypatch.setattr(runner, "OPERATION_TIMEOUT_SECONDS", 0.01)
    attempts, cleanup_complete = await runner.run_provider_pair(
        config,
        pair_index=0,
        provider_factory=provider_factory,
        monotonic=clock.now,
    )

    assert cleanup_complete is True
    assert len(providers) == 1
    assert providers[0].open_count == 1
    assert [attempt.outcome for attempt in attempts] == [
        runner.TtsAttemptOutcome.UNKNOWN,
        runner.TtsAttemptOutcome.UNKNOWN,
    ]
    assert attempts[0].reason == "TIMEOUT"
    assert attempts[1].reason == "PAIR_ABORTED"


@pytest.mark.asyncio
async def test_operation_deadline_wins_when_provider_suppresses_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = runner.TtsConnectionBenchmarkConfig(
        "tts-connection-run",
        "run",
        (tmp_path / "report.json").resolve(),
        "a" * 40,
        True,
        "A1",
        "gpt-4o-mini-tts-2025-12-15",
        "marin",
        24_000,
    )
    clock = ManualClock()

    class SuppressingProvider(FakeSynthesisProvider):
        async def open_synthesis(self, request, *, on_transport_open=None) -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await super().open_synthesis(
                    request, on_transport_open=on_transport_open
                )

    provider = None

    def provider_factory(observer):
        nonlocal provider
        provider = SuppressingProvider(observer, clock, reuse_warm=False)
        return provider

    monkeypatch.setattr(runner, "OPERATION_TIMEOUT_SECONDS", 0.01)
    attempts, cleanup_complete = await runner.run_provider_pair(
        config,
        pair_index=0,
        provider_factory=provider_factory,
        monotonic=clock.now,
    )

    assert cleanup_complete is True
    assert provider is not None
    assert len(provider.requests) == 1
    assert [attempt.outcome for attempt in attempts] == [
        runner.TtsAttemptOutcome.UNKNOWN,
        runner.TtsAttemptOutcome.UNKNOWN,
    ]
    assert attempts[0].reason == "TIMEOUT"


@pytest.mark.asyncio
async def test_dirty_pair_cleanup_stops_before_next_paid_provider(
    tmp_path: Path,
) -> None:
    config = runner.TtsConnectionBenchmarkConfig(
        "tts-connection-run",
        "run",
        (tmp_path / "report.json").resolve(),
        "a" * 40,
        True,
        "A1",
        "gpt-4o-mini-tts-2025-12-15",
        "marin",
        24_000,
    )
    clock = ManualClock()
    providers = []

    class DirtyCleanupProvider(FakeSynthesisProvider):
        async def close(self) -> None:
            await super().close()
            self.cleanup_snapshot = SimpleNamespace(clean=False)

    def provider_factory(observer):
        provider = DirtyCleanupProvider(observer, clock, reuse_warm=False)
        providers.append(provider)
        return provider

    with pytest.raises(
        ValueError, match="TTS_CONNECTION_BENCHMARK_CLEANUP_INCOMPLETE"
    ):
        await runner.run_benchmark(
            config,
            provider_factory=provider_factory,
            monotonic=clock.now,
        )

    assert len(providers) == 1
    assert providers[0].close_count == 1


def test_report_parser_rejects_a_decision_that_disagrees_with_attempt_truth(
    tmp_path: Path,
) -> None:
    output = (tmp_path / "report.json").resolve()
    config = runner.TtsConnectionBenchmarkConfig(
        "tts-connection-pilot",
        "pilot",
        output,
        "a" * 40,
        True,
        "A1",
        "gpt-4o-mini-tts-2025-12-15",
        "marin",
        24_000,
    )
    attempts = (
        _completed_attempt(
            0,
            runner.TtsAttemptPosition.COLD,
            reused=False,
            first_pcm_ms=100.0,
        ),
        _completed_attempt(
            0,
            runner.TtsAttemptPosition.WARM,
            reused=False,
            first_pcm_ms=90.0,
        ),
    )
    report = runner.build_report(
        config,
        provider_id="openai-streaming-speech",
        provider_class="OpenAIStreamingSpeechProvider",
        python_version="3.11.15",
        httpx_version="0.28.1",
        httpcore_version="1.0.9",
        attempts=attempts,
        cleanup_complete=(True,),
    )
    runner.write_private_report(output, report)
    payload = json.loads(output.read_text())
    payload["decision"] = "INCONCLUSIVE"
    output.write_text(json.dumps(payload))
    output.chmod(0o600)

    with pytest.raises(ValueError, match="TTS_CONNECTION_REPORT_INVALID"):
        runner.parse_report(output)


def test_control_report_is_inconclusive_if_a_warm_request_reuses_connection(
    tmp_path: Path,
) -> None:
    config = runner.TtsConnectionBenchmarkConfig(
        "tts-connection-pilot",
        "pilot",
        (tmp_path / "report.json").resolve(),
        "a" * 40,
        True,
        "A1",
        "gpt-4o-mini-tts-2025-12-15",
        "marin",
        24_000,
    )
    report = runner.build_report(
        config,
        provider_id="openai-streaming-speech",
        provider_class="OpenAIStreamingSpeechProvider",
        python_version="3.11.15",
        httpx_version="0.28.1",
        httpcore_version="1.0.9",
        attempts=(
            _completed_attempt(
                0,
                runner.TtsAttemptPosition.COLD,
                reused=False,
                first_pcm_ms=100.0,
            ),
            _completed_attempt(
                0,
                runner.TtsAttemptPosition.WARM,
                reused=True,
                first_pcm_ms=50.0,
            ),
        ),
        cleanup_complete=(True,),
    )

    assert report.decision == "INCONCLUSIVE"


def test_report_install_failure_leaves_no_final_or_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = (tmp_path / "report.json").resolve()
    config = runner.TtsConnectionBenchmarkConfig(
        "tts-connection-pilot",
        "pilot",
        output,
        "a" * 40,
        True,
        "A1",
        "gpt-4o-mini-tts-2025-12-15",
        "marin",
        24_000,
    )
    report = runner.build_report(
        config,
        provider_id="openai-streaming-speech",
        provider_class="OpenAIStreamingSpeechProvider",
        python_version="3.11.15",
        httpx_version="0.28.1",
        httpcore_version="1.0.9",
        attempts=(
            _completed_attempt(
                0,
                runner.TtsAttemptPosition.COLD,
                reused=False,
                first_pcm_ms=100.0,
            ),
            _completed_attempt(
                0,
                runner.TtsAttemptPosition.WARM,
                reused=False,
                first_pcm_ms=90.0,
            ),
        ),
        cleanup_complete=(True,),
    )

    def fail_install(_source, _destination) -> None:
        raise OSError("private-install-sentinel")

    monkeypatch.setattr(runner.os, "link", fail_install)
    with pytest.raises(OSError, match="private-install-sentinel"):
        runner.write_private_report(output, report)

    assert output.exists() is False
    assert list(tmp_path.iterdir()) == []
