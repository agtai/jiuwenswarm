# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from jiuwenswarm.server.live_voice import latency_probe_report
from jiuwenswarm.server.live_voice.latency_probe import (
    BATCH_SCHEMA_VERSION,
    MARK_SCHEMA_VERSION,
    LatencyBatch,
    LatencyMark,
    load_latency_run_config,
)
from jiuwenswarm.server.live_voice.latency_probe_report import (
    FIXED_SEGMENTS,
    compare_latency_reports,
    read_latency_batches,
    reduce_latency_run,
    write_latency_report,
)


def run_payload(*, cold_or_warm: str = "warm", source_state: str = "clean") -> dict[str, object]:
    return {
        "schema_version": "live-voice.latency-run.v0",
        "run_id": "run-20260819-a",
        "git_commit": "a" * 40,
        "source_state": source_state,
        "environment_profile": "dev-wsl-browser",
        "browser_family_and_version": "chromium-139",
        "browser_os_class": "windows",
        "gateway_runtime_class": "wsl-python",
        "agent_runtime_class": "linux-python",
        "stt_provider_and_model": "openai-gpt-4o-transcribe",
        "tts_provider_and_model": "openai-gpt-4o-mini-tts",
        "audio_format": "pcm16-24000hz-mono",
        "vad_configuration": "provider-server-vad",
        "playout_configuration": "webaudio-default",
        "allowlisted_feature_flags": {"formal_route": True},
        "cold_or_warm": cold_or_warm,
        "input_case_ids": ["short-greeting-v1", "tool-weather-v1"],
        "profile_ids": [
            "dialogue_no_tool", "dialogue_with_tool", "task_create", "task_status", "task_cancel",
        ],
        "intended_attempts": 5,
        "required_successes": 1,
        "experiment": None,
    }


@pytest.fixture
def run_config(tmp_path):
    path = tmp_path / "run.json"
    path.write_text(json.dumps(run_payload()), encoding="utf-8")
    return load_latency_run_config(path)


def batch_for(
    run, definition, *, clock: str = "clock-1", identity: str = "corr-1", round_index: int = 0,
    terminal_outcome: str = "completed", batch_id: str | None = None,
) -> LatencyBatch:
    profile_id = (
        "dialogue_with_tool" if definition.segment_id == "tool_execution"
        else "task_create" if definition.segment_id in {"task_command", "task_command_to_presentation"}
        else "dialogue_no_tool"
    )
    common = dict(
        schema_version=MARK_SCHEMA_VERSION, run_id=run.run_id, profile_id=profile_id,
        input_case_id="short-greeting-v1", round_index=round_index, source_instance_id="source-1",
        component=definition.component, clock_domain_id=clock, uncertainty_ms=None,
        outcome="observed", reason_code=None, correlation_id=identity, interaction_id="interaction-1",
        activation_id="activation-1", activation_generation=1, turn_id="turn-1",
        response_id="response-1", response_generation=1, task_id=None,
    )
    marks = tuple(
        LatencyMark(mark_index=index, point=point, monotonic_ms=timestamp, **common)
        for index, (point, timestamp) in enumerate(((definition.start_point, 100.0), (definition.end_point, 950.0)))
    )
    phase = {
        "browser": "browser_round", "gateway": "gateway_stt" if definition.start_point.startswith("gateway.stt") or definition.start_point == "gateway.vad_speech_stopped" else "gateway_tts",
        "agent_server": "agent_foreground",
    }[definition.component]
    return LatencyBatch(
        schema_version=BATCH_SCHEMA_VERSION, batch_id=batch_id or f"batch-{definition.segment_id}",
        run_id=run.run_id, profile_id=profile_id, input_case_id="short-greeting-v1",
        round_index=round_index, source_instance_id="source-1", component=definition.component,
        phase=phase, terminal_outcome=terminal_outcome, marks=marks,
    )


@pytest.mark.parametrize("definition", FIXED_SEGMENTS, ids=lambda item: item.segment_id)
def test_reducer_calculates_every_fixed_same_clock_segment(run_config, definition) -> None:
    report = reduce_latency_run(run_config, [batch_for(run_config, definition)])

    summary = report.profile(batch_for(run_config, definition).profile_id).segment(definition.segment_id)
    assert summary.successful_samples == 1
    assert summary.minimum_ms == 850.0
    assert summary.p50_ms == 850.0
    assert summary.p95_ms == 850.0
    assert summary.maximum_ms == 850.0
    assert summary.unknown == 0


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "identity", "cross_clock"])
def test_reducer_keeps_ambiguous_pairs_unknown_never_zero(run_config, mutation) -> None:
    definition = next(item for item in FIXED_SEGMENTS if item.segment_id == "response_total")
    batch = batch_for(run_config, definition)
    if mutation == "missing":
        batch = replace(batch, marks=batch.marks[:1])
    elif mutation == "duplicate":
        duplicate = replace(batch.marks[1], mark_index=2, monotonic_ms=951.0)
        batch = replace(batch, marks=(*batch.marks, duplicate))
    elif mutation == "identity":
        batch = replace(batch, marks=(batch.marks[0], replace(batch.marks[1], correlation_id="corr-2")))
    else:
        batch = replace(batch, marks=(batch.marks[0], replace(batch.marks[1], clock_domain_id="clock-2")))

    summary = reduce_latency_run(run_config, [batch]).profile("dialogue_no_tool").segment("response_total")
    assert summary.successful_samples == 0
    assert summary.unknown == 1
    assert summary.p50_ms is None


def test_reducer_deduplicates_identical_batch_receipts(run_config) -> None:
    definition = next(item for item in FIXED_SEGMENTS if item.segment_id == "response_total")
    batch = batch_for(run_config, definition)

    summary = reduce_latency_run(run_config, [batch, batch]).profile("dialogue_no_tool").segment("response_total")

    assert summary.attempts == 1
    assert summary.successful_samples == 1
    assert summary.unknown == 0


def test_reducer_uses_nearest_rank_and_never_pools_cold_warm(run_config, tmp_path) -> None:
    definition = next(item for item in FIXED_SEGMENTS if item.segment_id == "response_total")
    batches = []
    for index, end in enumerate((110.0, 120.0, 130.0, 140.0, 150.0)):
        batch = batch_for(run_config, definition, round_index=index, batch_id=f"batch-{index}")
        batches.append(replace(batch, marks=(batch.marks[0], replace(batch.marks[1], monotonic_ms=end))))
    warm = reduce_latency_run(run_config, batches)
    summary = warm.profile("dialogue_no_tool").segment("response_total")
    assert (summary.minimum_ms, summary.p50_ms, summary.p95_ms, summary.maximum_ms) == (10.0, 30.0, 50.0, 50.0)

    cold_path = tmp_path / "cold.json"
    cold_path.write_text(json.dumps(run_payload(cold_or_warm="cold")), encoding="utf-8")
    cold = reduce_latency_run(load_latency_run_config(cold_path), batches)
    assert warm.cold_or_warm == "warm"
    assert cold.cold_or_warm == "cold"
    assert compare_latency_reports(warm, cold).status == "inconclusive"


def test_read_and_write_reports_are_deterministic_and_sanitized(run_config, tmp_path) -> None:
    definition = next(item for item in FIXED_SEGMENTS if item.segment_id == "response_total")
    run_dir = tmp_path / run_config.run_id
    run_dir.mkdir()
    (run_dir / "run.json").write_text(json.dumps(run_config.to_dict()), encoding="utf-8")
    (run_dir / "browser.jsonl").write_bytes(batch_for(run_config, definition).canonical_bytes() + b"\n")
    report = reduce_latency_run(run_config, read_latency_batches(run_dir))
    write_latency_report(report, run_dir)

    assert json.loads((run_dir / "report.json").read_text(encoding="utf-8")) == report.to_dict()
    assert (run_dir / "report.csv").read_text(encoding="utf-8").splitlines()[0].startswith("profile_id,segment_id")
    markdown = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "## dialogue_no_tool" in markdown
    assert "Waterfall" in markdown


def test_loading_report_for_comparison_never_writes_adjacent_run_manifest(run_config, tmp_path, monkeypatch) -> None:
    definition = next(item for item in FIXED_SEGMENTS if item.segment_id == "response_total")
    report = reduce_latency_run(run_config, [batch_for(run_config, definition)])
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report.to_dict()), encoding="utf-8")
    original_write_text = Path.write_text

    def reject_run_manifest_write(self, *args, **kwargs):
        if self.name == "run.json":
            raise AssertionError("report loading must be read-only")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", reject_run_manifest_write)
    assert latency_probe_report._load_report(path).run.run_id == run_config.run_id


def report_with_response_total(run_config, *, duration: float):
    definition = next(item for item in FIXED_SEGMENTS if item.segment_id == "response_total")
    batch = batch_for(run_config, definition)
    return reduce_latency_run(run_config, [replace(batch, marks=(batch.marks[0], replace(batch.marks[1], monotonic_ms=100.0 + duration)))])


def experiment_config(tmp_path, *, target: str = "response_total"):
    payload = run_payload()
    payload["experiment"] = {
        "experiment_id": "latency-tune", "target_segment": target, "target_statistic": "p50_ms",
        "minimum_improvement_ms": 10.0, "response_total_minimum_improvement_ms": 10.0,
        "guardrails": [{"metric": "failure_rate", "segment_id": None, "maximum_regression": 0.0}],
        "declared_experiment_points": [],
    }
    path = tmp_path / f"{target}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_latency_run_config(path)


def report_with_complete_summaries(run_config, *, response: float, target: float | None = None, shifted: float | None = None):
    report = report_with_response_total(run_config, duration=response)
    profiles = []
    for profile in report.profiles:
        summaries = []
        for summary in profile.segments:
            value = response
            if summary.segment.segment_id == "eot_to_stt_final" and target is not None:
                value = target
            if summary.segment.segment_id == "stt_final_to_submit" and shifted is not None:
                value = shifted
            summaries.append(replace(summary, attempts=1, successful_samples=1, unknown=0, minimum_ms=value, p50_ms=value, p95_ms=value, maximum_ms=value))
        profiles.append(replace(profile, segments=tuple(summaries)))
    return replace(report, profiles=tuple(profiles))


@pytest.mark.parametrize(
    ("baseline", "candidate", "target", "expected"),
    [
        (100.0, 80.0, "response_total", "improved"),
        (100.0, 110.0, "response_total", "regressed"),
        (100.0, 95.0, "eot_to_stt_final", "shifted"),
    ],
)
def test_compare_classifies_improved_shifted_and_regressed(tmp_path, baseline, candidate, target, expected) -> None:
    base_path = tmp_path / "baseline.json"
    base_path.write_text(json.dumps(run_payload()), encoding="utf-8")
    base = report_with_complete_summaries(load_latency_run_config(base_path), response=baseline, target=baseline)
    current = report_with_complete_summaries(
        experiment_config(tmp_path, target=target), response=candidate,
        target=candidate if target != "response_total" else None,
        shifted=120.0 if expected == "shifted" else None,
    )

    assert compare_latency_reports(base, current).status == expected


def test_compare_is_inconclusive_for_insufficient_samples(run_config, tmp_path) -> None:
    baseline = report_with_response_total(run_config, duration=100.0)
    candidate = report_with_response_total(experiment_config(tmp_path), duration=80.0)
    assert compare_latency_reports(baseline, candidate).status == "inconclusive"


def test_compare_classifies_incompatible_and_dirty_baselines(run_config, tmp_path) -> None:
    baseline = report_with_response_total(run_config, duration=100.0)
    candidate = report_with_response_total(run_config, duration=80.0)
    assert compare_latency_reports(baseline, candidate).status == "inconclusive"

    dirty_path = tmp_path / "dirty.json"
    dirty_path.write_text(json.dumps(run_payload(source_state="product_code_dirty")), encoding="utf-8")
    dirty = report_with_response_total(load_latency_run_config(dirty_path), duration=100.0)
    assert compare_latency_reports(dirty, candidate).status == "inconclusive"


def test_cli_validate_report_and_compare_smoke(run_config, tmp_path) -> None:
    definition = next(item for item in FIXED_SEGMENTS if item.segment_id == "response_total")
    run_dir = tmp_path / run_config.run_id
    run_dir.mkdir()
    run_json = run_dir / "run.json"
    run_json.write_text(json.dumps(run_config.to_dict()), encoding="utf-8")
    (run_dir / "browser.jsonl").write_bytes(batch_for(run_config, definition).canonical_bytes() + b"\n")
    command = [sys.executable, "-m", "jiuwenswarm.server.live_voice.latency_probe_report"]
    assert subprocess.run([*command, "validate-run", "--run-json", str(run_json)], check=False).returncode == 0
    assert subprocess.run([*command, "report", "--run-dir", str(run_dir)], check=False).returncode == 0
    assert subprocess.run([*command, "compare", "--baseline", str(run_dir / "report.json"), "--candidate", str(run_dir / "report.json")], check=False).returncode == 0
