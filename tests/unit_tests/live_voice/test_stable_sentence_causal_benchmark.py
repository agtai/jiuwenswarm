from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.latency_probe import load_latency_run_config
from jiuwenswarm.server.live_voice.speech_ports import ProviderRef, SynthesisEventKind
from jiuwenswarm.server.live_voice.streaming_speech import StreamingSynthesisEvent


ROOT = Path(__file__).parents[3]
RUNNER_PATH = ROOT / "scripts/live_voice/stable_sentence_causal_benchmark.py"
POLICY_FIXTURE = ROOT / "tests/fixtures/live_voice/stable_sentence_policy_v1.json"
PROVIDER_FIXTURE = (
    ROOT / "tests/fixtures/live_voice/stable_sentence_provider_cases.json"
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = _load(RUNNER_PATH, "stable_sentence_causal_benchmark")


def run_payload(*, intended_attempts: int = 7) -> dict[str, object]:
    return {
        "schema_version": "live-voice.latency-run.v1",
        "run_id": "stable-sentence-controlled",
        "git_commit": "a" * 40,
        "source_state": "clean",
        "environment_profile": "controlled-python",
        "browser_family_and_version": "not-exercised",
        "browser_os_class": "not-exercised",
        "gateway_runtime_class": "controlled-tts",
        "agent_runtime_class": "controlled-agent-events",
        "stt_provider_and_model": "not-exercised",
        "tts_provider_and_model": "controlled-delay",
        "audio_format": "pcm16-24000hz-mono",
        "vad_configuration": "not-exercised",
        "playout_configuration": "not-exercised",
        "allowlisted_feature_flags": {
            "latency_probe": True,
            "stable_sentence_tts": False,
        },
        "cold_or_warm": "warm",
        "input_case_ids": ["stable-sentence-controlled-v1"],
        "profile_ids": ["dialogue_no_tool"],
        "intended_attempts": intended_attempts,
        "required_successes": 1,
        "experiment": {
            "experiment_id": "stable-sentence-screen",
            "target_segment": "agent_to_final",
            "target_statistic": "p50_ms",
            "minimum_improvement_ms": 400.0,
            "response_total_minimum_improvement_ms": 400.0,
            "guardrails": [
                {
                    "metric": "failure_rate",
                    "segment_id": None,
                    "maximum_regression": 0.0,
                }
            ],
            "declared_experiment_points": [
                {
                    "point": "agent.sentence_candidate_detected",
                    "component": "agent_server",
                    "paired_segment_id": "candidate_to_final",
                    "start_point": "agent.sentence_candidate_detected",
                    "end_point": "agent.agent_final",
                },
                {
                    "point": "agent.sentence_presentation_committed",
                    "component": "agent_server",
                    "paired_segment_id": "candidate_to_commit",
                    "start_point": "agent.sentence_candidate_detected",
                    "end_point": "agent.sentence_presentation_committed",
                },
            ],
        },
        "optimization_track": "agent_tts_overlap",
        "benchmark_lane": "no_browser_causal",
        "fixture_profile_id": "stable-sentence-policy-v1",
    }


@pytest.fixture
def run_json(tmp_path: Path) -> Path:
    path = tmp_path / "run.json"
    path.write_text(json.dumps(run_payload()), encoding="utf-8")
    return path


class FixedTts:
    def __init__(self, delay_ms: float = 800.0) -> None:
        self.delay_ms = delay_ms
        self.calls: list[bytes] = []

    async def first_pcm_delay_ms(self, text_utf8: bytes) -> float:
        self.calls.append(text_utf8)
        return self.delay_ms


def test_config_closes_source_population_and_output(
    run_json: Path, tmp_path: Path
) -> None:
    config = runner.StableSentenceBenchmarkConfig(
        run_json=run_json.resolve(),
        output_path=(tmp_path / "result.json").resolve(),
        mode="controlled",
        population="SCREEN",
        git_commit="a" * 40,
        source_clean=True,
    )
    assert config.run.run_id == "stable-sentence-controlled"

    with pytest.raises(ValueError, match="STABLE_SENTENCE_CONFIG_INVALID"):
        runner.StableSentenceBenchmarkConfig(
            run_json=run_json.resolve(),
            output_path=Path("relative.json"),
            mode="controlled",
            population="SCREEN",
            git_commit="a" * 40,
            source_clean=True,
        )


@pytest.mark.asyncio
async def test_controlled_attempt_measures_candidate_headroom_without_product_effect(
    run_json: Path, tmp_path: Path
) -> None:
    config = runner.StableSentenceBenchmarkConfig(
        run_json=run_json.resolve(),
        output_path=(tmp_path / "result.json").resolve(),
        mode="controlled",
        population="SCREEN",
        git_commit="a" * 40,
        source_clean=True,
    )
    case = runner.load_controlled_cases(POLICY_FIXTURE)[0]
    tts = FixedTts()

    result = await runner.run_controlled_attempt(config, case, attempt_index=0, tts=tts)

    assert result.attempt.outcome == "completed"
    assert result.attempt.candidate_count == 1
    assert result.attempt.candidate_to_final_ms == 750.0
    assert result.attempt.projected_gain_ms == 750.0
    assert result.attempt.baseline_first_pcm_ms == 1750.0
    assert result.attempt.candidate_first_pcm_ms == 1000.0
    assert result.attempt.forbidden_effects == runner.ZERO_FORBIDDEN_EFFECTS
    assert result.batch.component == "agent_server"
    assert tts.calls == [b"Paris is the capital of France. "]


@pytest.mark.asyncio
async def test_controlled_attempt_uses_observed_tts_delay_not_a_report_constant(
    run_json: Path, tmp_path: Path
) -> None:
    config = runner.StableSentenceBenchmarkConfig(
        run_json=run_json.resolve(),
        output_path=(tmp_path / "result.json").resolve(),
        mode="controlled",
        population="SCREEN",
        git_commit="a" * 40,
        source_clean=True,
    )

    result = await runner.run_controlled_attempt(
        config,
        runner.load_controlled_cases(POLICY_FIXTURE)[0],
        attempt_index=0,
        tts=FixedTts(500.0),
    )

    assert result.attempt.candidate_first_pcm_ms == 700.0
    assert result.attempt.baseline_first_pcm_ms == 1450.0
    assert result.attempt.projected_gain_ms == 750.0


@pytest.mark.asyncio
async def test_mismatch_has_no_latency_credit_and_never_serializes_content(
    run_json: Path, tmp_path: Path
) -> None:
    config = runner.StableSentenceBenchmarkConfig(
        run_json=run_json.resolve(),
        output_path=(tmp_path / "result.json").resolve(),
        mode="controlled",
        population="SCREEN",
        git_commit="a" * 40,
        source_clean=True,
    )
    mismatch = next(
        case
        for case in runner.load_controlled_cases(POLICY_FIXTURE)
        if case.case_id == "prefix-mismatch"
    )

    result = await runner.run_controlled_attempt(
        config, mismatch, attempt_index=0, tts=FixedTts()
    )

    assert result.attempt.outcome == "integrity_failure"
    assert result.attempt.prefix_mismatch_count == 1
    assert result.attempt.candidate_to_final_ms is None
    assert result.attempt.projected_gain_ms is None
    serialized = json.dumps(result.attempt.to_dict(), sort_keys=True)
    assert "Paris" not in serialized
    assert "prompt" not in serialized
    assert "text" not in serialized


def completed_attempt(
    case_id: str, *, headroom: float, gain: float, baseline: float = 1500.0
):
    return runner.StableSentenceAttempt.completed(
        population="SCREEN",
        case_id=case_id,
        attempt_index=0,
        first_delta_ms=100.0,
        candidate_detected_ms=200.0,
        final_ms=200.0 + headroom,
        baseline_first_pcm_ms=baseline,
        candidate_first_pcm_ms=baseline - gain,
        candidate_count=1,
        discard_count=0,
        prefix_match_count=1,
        prefix_mismatch_count=0,
        correction_count=0,
    )


def test_materiality_gate_requires_absolute_relative_and_multiple_trace_classes() -> (
    None
):
    passing = (
        completed_attempt("english", headroom=700.0, gain=600.0),
        completed_attempt("chinese", headroom=800.0, gain=650.0),
    )
    too_small = (
        completed_attempt("english", headroom=300.0, gain=200.0),
        completed_attempt("chinese", headroom=350.0, gain=250.0),
    )

    assert runner.reduce_materiality_gate(passing).decision == "PASS"
    stopped = runner.reduce_materiality_gate(too_small)
    assert stopped.decision == "STOP"
    assert "HEADROOM_BELOW_GATE" in stopped.reasons


def test_atomic_result_writer_is_private_exclusive_and_content_free(
    run_json: Path, tmp_path: Path
) -> None:
    output_path = (tmp_path / "result.json").resolve()
    assert output_path.is_absolute()
    assert not output_path.exists()
    config = runner.StableSentenceBenchmarkConfig(
        run_json=run_json.resolve(),
        output_path=output_path,
        mode="controlled",
        population="SCREEN",
        git_commit="a" * 40,
        source_clean=True,
    )
    assert not config.output_path.exists()
    report = runner.StableSentenceCausalResult(
        schema_version=runner.REPORT_SCHEMA_VERSION,
        run_id=config.run.run_id,
        git_commit=config.git_commit,
        mode=config.mode,
        population=config.population,
        attempts=(completed_attempt("english", headroom=700.0, gain=600.0),),
        gate=runner.reduce_materiality_gate(
            (
                completed_attempt("english", headroom=700.0, gain=600.0),
                completed_attempt("chinese", headroom=800.0, gain=650.0),
            )
        ),
        forbidden_effects=runner.ZERO_FORBIDDEN_EFFECTS,
    )
    assert not config.output_path.exists()

    runner.write_result(report, config.output_path)

    assert config.output_path.stat().st_mode & 0o777 == 0o600
    payload = config.output_path.read_text(encoding="utf-8")
    assert "Paris" not in payload
    assert "api_key" not in payload
    with pytest.raises(FileExistsError):
        runner.write_result(report, config.output_path)


def test_run_config_is_the_existing_v1_contract(run_json: Path) -> None:
    run = load_latency_run_config(run_json)
    assert run.schema_version == "live-voice.latency-run.v1"
    assert run.optimization_track == "agent_tts_overlap"
    assert run.benchmark_lane == "no_browser_causal"
    assert run.experiment is not None


@pytest.mark.asyncio
async def test_controlled_corpus_reuses_standard_batches_and_report(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "stable-sentence-controlled"
    run_dir.mkdir()
    run_path = run_dir / "run.json"
    run_path.write_text(json.dumps(run_payload()), encoding="utf-8")
    config = runner.StableSentenceBenchmarkConfig(
        run_json=run_path.resolve(),
        output_path=(run_dir / "result.json").resolve(),
        mode="controlled",
        population="SCREEN",
        git_commit="a" * 40,
        source_clean=True,
    )

    report = await runner.run_controlled_corpus(config, POLICY_FIXTURE)

    assert len(report.attempts) == 7
    assert report.forbidden_effects == runner.ZERO_FORBIDDEN_EFFECTS
    assert (run_dir / "agent.jsonl").is_file()
    assert (run_dir / "report.json").is_file()
    assert (run_dir / "report.csv").is_file()
    assert (run_dir / "report.md").is_file()
    assert config.output_path.is_file()


class FakeFormalFacade:
    def __init__(self, chunks: list[AgentResponseChunk]) -> None:
        self.chunks = chunks
        self.executions = []

    async def process_formal_live_voice_stream(self, execution):
        self.executions.append(execution)
        for chunk in self.chunks:
            yield chunk


class SequenceClock:
    def __init__(self, *values: float) -> None:
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


def agent_chunk(seq: int, event_type: str, content: str) -> AgentResponseChunk:
    return AgentResponseChunk(
        request_id="provider-request",
        channel_id="live_voice_latency_screen",
        payload={"event_type": event_type, "content": content},
        is_complete=event_type == "chat.final",
    )


def test_provider_cases_are_public_bounded_and_tool_disabled() -> None:
    cases = runner.load_provider_cases(PROVIDER_FIXTURE)

    assert len(cases) == 3
    assert all(case.allow_tools is False for case in cases)
    assert all(case.minimum_sentence_count >= 2 for case in cases)


@pytest.mark.asyncio
async def test_formal_agent_stream_client_forces_no_tools_and_maps_exact_events() -> (
    None
):
    facade = FakeFormalFacade(
        [
            agent_chunk(0, "chat.delta", "First sentence. "),
            agent_chunk(1, "chat.delta", "Second sentence starts"),
            agent_chunk(2, "chat.final", "First sentence. Second sentence starts."),
        ]
    )
    client = runner.FormalAgentStreamClient(
        facade,
        monotonic=SequenceClock(10.0, 10.1, 10.2, 10.9),
    )

    events = [
        item
        async for item in client.stream(runner.load_provider_cases(PROVIDER_FIXTURE)[0])
    ]

    assert [item.event.event_type for item in events] == [
        "chat.delta",
        "chat.delta",
        "chat.final",
    ]
    assert [item.observed_ms for item in events] == pytest.approx([100.0, 200.0, 900.0])
    assert facade.executions[0].allow_tools is False
    assert facade.executions[0].context.entries == ()
    assert facade.executions[0].commit.text == (
        "In two concise sentences, explain why streaming can reduce voice-agent latency."
    )


@pytest.mark.asyncio
async def test_formal_agent_stream_client_rejects_tool_event_without_tts_or_mutation() -> (
    None
):
    facade = FakeFormalFacade([agent_chunk(0, "chat.tool_call", "forbidden")])
    client = runner.FormalAgentStreamClient(
        facade,
        monotonic=SequenceClock(10.0, 10.1),
    )

    with pytest.raises(ValueError, match="STABLE_SENTENCE_TOOL_EVENT_FORBIDDEN"):
        _ = [
            item
            async for item in client.stream(
                runner.load_provider_cases(PROVIDER_FIXTURE)[0]
            )
        ]

    assert facade.executions[0].allow_tools is False


class FakeConformance:
    def __init__(self) -> None:
        self.responses = []

    def activate_response(self, response) -> None:
        self.responses.append(response)


class FakeStreamingTtsProvider:
    def __init__(self, *, gap_seq: bool = False) -> None:
        self.conformance = FakeConformance()
        self.gap_seq = gap_seq
        self.request = None
        self.events = []
        self.close_calls = 0
        self.cleanup_snapshot = type("Cleanup", (), {"clean": True})()

    async def open_synthesis(self, request, *, on_transport_open=None) -> None:
        self.request = request
        if on_transport_open is not None:
            on_transport_open()
        provider = ProviderRef("fake-tts", "fake", None)
        self.events = [
            StreamingSynthesisEvent(
                request.ref, provider, 0, 0, SynthesisEventKind.STARTED, 24_000
            ),
            StreamingSynthesisEvent(
                request.ref,
                provider,
                2 if self.gap_seq else 1,
                0,
                SynthesisEventKind.CHUNK,
                24_000,
                sample_count=2,
                pcm_s16le=b"\x00\x00\x00\x00",
                display_span=request.display_span,
                spoken_span=request.display_span,
            ),
            StreamingSynthesisEvent(
                request.ref,
                provider,
                3 if self.gap_seq else 2,
                2,
                SynthesisEventKind.COMPLETED,
                24_000,
            ),
        ]

    async def next_synthesis_event(self, ref, *, timeout_seconds):
        assert self.request is not None and ref == self.request.ref
        assert timeout_seconds == 20.0
        return self.events.pop(0)

    async def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_benchmark_tts_client_measures_real_events_and_closes_provider() -> None:
    provider = FakeStreamingTtsProvider()
    client = runner.StreamingBenchmarkTtsClient(
        provider,
        monotonic=SequenceClock(10.0, 10.1, 10.2, 10.5),
    )

    timing = await client.measure_first_pcm(
        response_ref=ResponseRef("interaction-1", "response-1", 0),
        unit_id="unit-1",
        text_utf8=b"First sentence.",
    )

    assert timing.request_started_ms == 0.0
    assert timing.transport_open_ms == pytest.approx(100.0)
    assert timing.first_provider_audio_ms == pytest.approx(200.0)
    assert timing.first_pcm_ms == pytest.approx(200.0)
    assert timing.completed_ms == pytest.approx(500.0)
    assert timing.cleanup_complete is True
    assert provider.conformance.responses == [
        ResponseRef("interaction-1", "response-1", 0)
    ]
    assert provider.close_calls == 1


@pytest.mark.asyncio
async def test_benchmark_tts_client_rejects_sequence_gap_and_still_closes() -> None:
    provider = FakeStreamingTtsProvider(gap_seq=True)
    client = runner.StreamingBenchmarkTtsClient(
        provider,
        monotonic=SequenceClock(10.0, 10.1),
    )

    with pytest.raises(ValueError, match="STABLE_SENTENCE_TTS_PROTOCOL_INVALID"):
        await client.measure_first_pcm(
            response_ref=ResponseRef("interaction-1", "response-1", 0),
            unit_id="unit-1",
            text_utf8=b"First sentence.",
        )

    assert provider.close_calls == 1


def test_benchmark_tts_timing_rejects_nonmonotonic_provider_events() -> None:
    with pytest.raises(ValueError, match="STABLE_SENTENCE_TTS_TIMING_INVALID"):
        runner.BenchmarkTtsTiming(
            request_started_ms=0.0,
            transport_open_ms=300.0,
            first_provider_audio_ms=200.0,
            first_pcm_ms=200.0,
            completed_ms=500.0,
            cleanup_complete=True,
        )


class FixedBenchmarkTts:
    def __init__(self, first_pcm_ms: float = 500.0) -> None:
        self.first_pcm_ms = first_pcm_ms
        self.calls = []

    async def measure_first_pcm(self, *, response_ref, unit_id, text_utf8):
        self.calls.append((response_ref, unit_id, text_utf8))
        return runner.BenchmarkTtsTiming(
            0.0,
            100.0,
            self.first_pcm_ms,
            self.first_pcm_ms,
            self.first_pcm_ms + 200.0,
            True,
        )


@pytest.mark.asyncio
async def test_provider_attempt_overlaps_tts_with_agent_and_measures_same_clock_edges() -> (
    None
):
    case = runner.load_provider_cases(PROVIDER_FIXTURE)[0]
    facade = FakeFormalFacade(
        [
            agent_chunk(0, "chat.delta", "First sentence. "),
            agent_chunk(1, "chat.delta", "Second sentence starts"),
            agent_chunk(2, "chat.final", "First sentence. Second sentence starts."),
        ]
    )
    agent = runner.FormalAgentStreamClient(
        facade,
        monotonic=SequenceClock(10.0, 10.1, 10.2, 10.9),
    )
    tts = FixedBenchmarkTts()

    attempt = await runner.run_provider_attempt(
        population="SCREEN",
        case=case,
        attempt_index=0,
        agent=agent,
        tts=tts,
    )

    assert attempt.outcome == "completed"
    assert attempt.first_delta_ms == pytest.approx(100.0)
    assert attempt.candidate_detected_ms == pytest.approx(200.0)
    assert attempt.final_ms == pytest.approx(900.0)
    assert attempt.candidate_to_final_ms == pytest.approx(700.0)
    assert attempt.candidate_first_pcm_ms == pytest.approx(700.0)
    assert attempt.baseline_first_pcm_ms == pytest.approx(1400.0)
    assert attempt.projected_gain_ms == pytest.approx(700.0)
    assert tts.calls[0][2] == b"First sentence. "


@pytest.mark.asyncio
async def test_provider_attempt_mismatch_discards_latency_credit() -> None:
    case = runner.load_provider_cases(PROVIDER_FIXTURE)[0]
    facade = FakeFormalFacade(
        [
            agent_chunk(0, "chat.delta", "First sentence. "),
            agent_chunk(1, "chat.delta", "Second sentence starts"),
            agent_chunk(2, "chat.final", "A rewritten final response."),
        ]
    )
    agent = runner.FormalAgentStreamClient(
        facade,
        monotonic=SequenceClock(10.0, 10.1, 10.2, 10.9),
    )

    attempt = await runner.run_provider_attempt(
        population="SCREEN",
        case=case,
        attempt_index=0,
        agent=agent,
        tts=FixedBenchmarkTts(),
    )

    assert attempt.outcome == "integrity_failure"
    assert attempt.reason == "PREFIX_MISMATCH"
    assert attempt.prefix_mismatch_count == 1
    assert attempt.candidate_to_final_ms is None
    assert attempt.projected_gain_ms is None


@pytest.mark.asyncio
async def test_provider_attempt_drains_stream_and_rejects_second_final() -> None:
    case = runner.load_provider_cases(PROVIDER_FIXTURE)[0]
    facade = FakeFormalFacade(
        [
            agent_chunk(0, "chat.delta", "First sentence. "),
            agent_chunk(1, "chat.delta", "Second sentence starts"),
            agent_chunk(2, "chat.final", "First sentence. Second sentence starts."),
            agent_chunk(3, "chat.final", "Conflicting final."),
        ]
    )
    agent = runner.FormalAgentStreamClient(
        facade,
        monotonic=SequenceClock(10.0, 10.1, 10.2, 10.9, 11.0),
    )

    with pytest.raises(ValueError, match="STABLE_SENTENCE_AGENT_EVENT_AFTER_FINAL"):
        await runner.run_provider_attempt(
            population="SCREEN",
            case=case,
            attempt_index=0,
            agent=agent,
            tts=FixedBenchmarkTts(),
        )


@pytest.mark.asyncio
async def test_provider_corpus_writes_standard_probe_and_private_result(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "stable-sentence-provider"
    run_dir.mkdir()
    payload = run_payload(intended_attempts=3)
    payload["run_id"] = "stable-sentence-provider"
    payload["fixture_profile_id"] = "stable-sentence-provider-v1"
    payload["input_case_ids"] = ["stable-sentence-provider-v1"]
    run_path = run_dir / "run.json"
    run_path.write_text(json.dumps(payload), encoding="utf-8")
    config = runner.StableSentenceBenchmarkConfig(
        run_json=run_path.resolve(),
        output_path=(run_dir / "result.json").resolve(),
        mode="provider-pilot",
        population="SCREEN",
        git_commit="a" * 40,
        source_clean=True,
    )
    facade = FakeFormalFacade(
        [
            agent_chunk(0, "chat.delta", "First sentence. "),
            agent_chunk(1, "chat.delta", "Second sentence starts"),
            agent_chunk(
                2,
                "chat.final",
                "First sentence. Second sentence starts. Third sentence.",
            ),
        ]
    )
    clock_values = [value for _ in range(3) for value in (10.0, 10.1, 10.2, 10.9)]
    agent = runner.FormalAgentStreamClient(
        facade,
        monotonic=SequenceClock(*clock_values),
    )

    report = await runner.run_provider_corpus(
        config,
        PROVIDER_FIXTURE,
        agent=agent,
        tts_factory=lambda: FixedBenchmarkTts(),
    )

    assert len(report.attempts) == 3
    assert all(attempt.outcome == "completed" for attempt in report.attempts)
    assert report.gate.decision == "PASS"
    assert (run_dir / "agent.jsonl").is_file()
    assert (run_dir / "report.json").is_file()
    assert config.output_path.is_file()


class FakeAgentManager:
    def __init__(self, facade) -> None:
        self.facade = facade
        self.get_calls = []
        self.cleanup_calls = 0

    async def get_agent(self, **kwargs):
        self.get_calls.append(kwargs)
        return self.facade

    async def cleanup(self) -> None:
        self.cleanup_calls += 1


@pytest.mark.asyncio
async def test_managed_real_agent_client_binds_disposable_project_and_cleans_up(
    tmp_path: Path,
) -> None:
    facade = FakeFormalFacade([agent_chunk(0, "chat.final", "Final response.")])
    manager = FakeAgentManager(facade)

    async with runner.managed_formal_agent_client(
        tmp_path.resolve(), manager_factory=lambda: manager
    ) as client:
        assert isinstance(client, runner.FormalAgentStreamClient)

    assert manager.get_calls == [
        {
            "channel_id": "live_voice_latency_screen",
            "mode": "agent",
            "project_dir": str(tmp_path.resolve()),
        }
    ]
    assert manager.cleanup_calls == 1


def test_real_tts_factory_rejects_missing_provider_configuration() -> None:
    with pytest.raises(ValueError, match="PROVIDER_UNAVAILABLE"):
        runner.create_real_tts_client({}, monotonic=lambda: 1.0)


def test_prepare_provider_run_writes_existing_private_v1_manifest(
    tmp_path: Path,
) -> None:
    output = (tmp_path / "provider-pilot" / "result.json").resolve()
    environ = {
        runner.SPEECH_PROVIDER_ENV: "openai",
        runner.SPEECH_API_BASE_ENV: "https://api.openai.com/v1",
        runner.SPEECH_API_KEY_ENV: "private-key-not-serialized",
        runner.SPEECH_TTS_MODEL_ENV: "gpt-4o-mini-tts",
        runner.SPEECH_TTS_VOICE_ENV: "alloy",
    }

    run_path = runner.prepare_provider_run(
        output,
        PROVIDER_FIXTURE,
        mode="provider-pilot",
        population="SCREEN",
        source_commit="a" * 40,
        source_clean=True,
        environ=environ,
    )

    run = load_latency_run_config(run_path)
    assert run.schema_version == "live-voice.latency-run.v1"
    assert run.intended_attempts == 3
    assert run.tts_provider_and_model == "openai-gpt-4o-mini-tts-alloy"
    assert run.optimization_track == "agent_tts_overlap"
    assert run.benchmark_lane == "no_browser_causal"
    assert run_path.stat().st_mode & 0o777 == 0o600
    assert "private-key-not-serialized" not in run_path.read_text(encoding="utf-8")


def test_cli_parser_closes_provider_run_arguments(tmp_path: Path) -> None:
    args = runner._parser().parse_args(
        [
            "provider-run",
            "--mode",
            "provider-pilot",
            "--population",
            "SCREEN",
            "--project-dir",
            str(tmp_path.resolve()),
            "--cases",
            str(PROVIDER_FIXTURE),
            "--output",
            str((tmp_path / "result.json").resolve()),
        ]
    )

    assert args.command == "provider-run"
    assert args.mode == "provider-pilot"
    assert args.population == "SCREEN"
    assert args.project_dir == tmp_path.resolve()
