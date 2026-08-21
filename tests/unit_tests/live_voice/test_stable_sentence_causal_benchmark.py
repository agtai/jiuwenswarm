from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from jiuwenswarm.server.live_voice.latency_probe import load_latency_run_config


ROOT = Path(__file__).parents[3]
RUNNER_PATH = ROOT / "scripts/live_voice/stable_sentence_causal_benchmark.py"
POLICY_FIXTURE = (
    ROOT / "tests/fixtures/live_voice/stable_sentence_policy_v1.json"
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


def test_config_closes_source_population_and_output(run_json: Path, tmp_path: Path) -> None:
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

    result = await runner.run_controlled_attempt(
        config, case, attempt_index=0, tts=tts
    )

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


def test_materiality_gate_requires_absolute_relative_and_multiple_trace_classes() -> None:
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
