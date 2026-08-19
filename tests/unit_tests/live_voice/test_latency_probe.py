# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json

import pytest

from jiuwenswarm.server.live_voice.latency_probe import (
    LatencyBatch,
    LatencyProbeBatchWriter,
    LatencyProbeRecorder,
    create_latency_probe_runtime_from_environment,
    load_latency_run_config,
    try_parse_latency_probe_context,
)


def valid_run_json() -> dict[str, object]:
    return {
        "schema_version": "live-voice.latency-run.v0",
        "run_id": "run-20260819-a",
        "git_commit": "a" * 40,
        "source_state": "clean",
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
        "cold_or_warm": "warm",
        "input_case_ids": ["short-greeting-v1", "tool-weather-v1"],
        "profile_ids": [
            "dialogue_no_tool",
            "dialogue_with_tool",
            "task_create",
            "task_status",
            "task_cancel",
        ],
        "intended_attempts": 5,
        "required_successes": 5,
        "experiment": {
            "experiment_id": "buffer-tuning",
            "target_segment": "response_total",
            "target_statistic": "p50_ms",
            "minimum_improvement_ms": 10.0,
            "response_total_minimum_improvement_ms": 5.0,
            "guardrails": [
                {
                    "metric": "failure_rate",
                    "segment_id": None,
                    "maximum_regression": 0.0,
                }
            ],
            "declared_experiment_points": [
                {
                    "point": "experiment.buffer-tuning.ready",
                    "component": "browser",
                    "paired_segment_id": "buffer_ready",
                    "start_point": "browser.eot_received",
                    "end_point": "experiment.buffer-tuning.ready",
                },
                *[
                    {
                        "point": f"experiment.buffer-tuning.gateway-{index}",
                        "component": "gateway",
                        "paired_segment_id": None,
                        "start_point": None,
                        "end_point": None,
                    }
                    for index in range(63)
                ],
            ],
        },
    }


@pytest.fixture
def run_config(tmp_path):
    path = tmp_path / "run.json"
    path.write_text(json.dumps(valid_run_json()), encoding="utf-8")
    return load_latency_run_config(path)


def test_load_run_config_accepts_the_five_fixed_profiles_and_declared_points(run_config) -> None:
    assert run_config.profile_ids == (
        "dialogue_no_tool",
        "dialogue_with_tool",
        "task_create",
        "task_status",
        "task_cancel",
    )
    assert run_config.input_case_ids == ("short-greeting-v1", "tool-weather-v1")
    assert run_config.allows_point("browser.eot_received", "browser") is True
    assert run_config.allows_point("gateway.stt_request_started", "gateway") is True
    assert (
        run_config.allows_point("experiment.buffer-tuning.ready", "browser") is True
    )


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda value: value.update(unexpected="PRIVATE"), "unknown key"),
        (lambda value: value.__setitem__("run_id", "x" * 257), "overlong string"),
        (lambda value: value.__setitem__("intended_attempts", 1.5), "invalid number"),
        (lambda value: value.__setitem__("profile_ids", ["dialogue_no_tool"]), "profiles"),
        (lambda value: value.__setitem__("input_case_ids", []), "input cases"),
    ],
)
def test_load_run_config_rejects_closed_invalid_inputs(tmp_path, mutate, reason) -> None:
    value = valid_run_json()
    mutate(value)
    path = tmp_path / "run.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError):
        load_latency_run_config(path)


def test_context_is_closed_and_bound_to_run(run_config) -> None:
    context = try_parse_latency_probe_context(
        {
            "schema_version": "live-voice.latency-context.v0",
            "run_id": run_config.run_id,
            "profile_id": "dialogue_no_tool",
            "input_case_id": "short-greeting-v1",
            "round_index": 0,
        },
        run_config,
    )

    assert context is not None
    assert context.round_index == 0
    assert try_parse_latency_probe_context({**context.to_dict(), "text": "PRIVATE"}, run_config) is None
    assert try_parse_latency_probe_context(
        {**context.to_dict(), "run_id": "other-run"}, run_config
    ) is None
    assert try_parse_latency_probe_context(
        {**context.to_dict(), "profile_id": "undeclared"}, run_config
    ) is None
    assert try_parse_latency_probe_context(
        {**context.to_dict(), "input_case_id": "undeclared-case"}, run_config
    ) is None


def context_for(run_config):
    context = try_parse_latency_probe_context(
        {
            "schema_version": "live-voice.latency-context.v0",
            "run_id": run_config.run_id,
            "profile_id": "dialogue_no_tool",
            "input_case_id": "short-greeting-v1",
            "round_index": 0,
        },
        run_config,
    )
    assert context is not None
    return context


def recorder_for(run_config, *, clock=lambda: 10.0):
    return LatencyProbeRecorder(
        context=context_for(run_config),
        component="gateway",
        phase="gateway_stt",
        source_instance_id_factory=lambda: "source-1",
        clock_domain_id="gateway-process-1",
        monotonic_ms=clock,
        run_config=run_config,
    )


def test_recorder_assigns_contiguous_marks_rejects_duplicates_and_finishes_once(run_config) -> None:
    recorder = recorder_for(run_config)

    assert recorder.mark(
        "gateway.stt_request_started", correlation_id="corr", interaction_id="ix"
    ) is True
    assert recorder.mark(
        "gateway.stt_request_started", correlation_id="corr", interaction_id="ix"
    ) is False
    batch = recorder.finish("completed")

    assert [mark.mark_index for mark in batch.marks] == [0]
    assert recorder.finish("completed") is None
    assert recorder.mark(
        "gateway.stt_session_ready", correlation_id="corr", interaction_id="ix"
    ) is False


def test_recorder_rejects_undeclared_experiment_marks_and_closed_batch_fields(run_config) -> None:
    recorder = recorder_for(run_config)
    assert recorder.mark(
        "experiment.buffer-tuning.not-declared", correlation_id="corr", interaction_id="ix"
    ) is False
    batch = recorder.finish("unknown")
    assert batch is not None

    with pytest.raises(ValueError):
        LatencyBatch.from_dict({**batch.to_dict(), "text": "PRIVATE"}, run_config)


def test_recorder_reserves_its_final_slot_for_one_capacity_observation(run_config) -> None:
    recorder = recorder_for(run_config)

    for index in range(63):
        assert recorder.mark(
            f"experiment.buffer-tuning.gateway-{index}",
            correlation_id="corr",
            interaction_id="ix",
        ) is True
    assert recorder.mark(
        "gateway.stt_request_started", correlation_id="corr", interaction_id="ix"
    ) is False

    batch = recorder.finish("unknown")
    assert batch is not None
    assert len(batch.marks) == 64
    assert batch.marks[-1].mark_index == 63
    assert batch.marks[-1].reason_code == "CAPACITY"


def test_writer_appends_one_canonical_line_and_handles_retries(tmp_path, run_config) -> None:
    batch = recorder_for(run_config).finish("completed")
    assert batch is not None
    writer = LatencyProbeBatchWriter(tmp_path, run_config.run_id, "gateway")

    first = writer.write(batch)
    retry = writer.write(batch)
    conflict = writer.write(batch.with_batch_id("conflicting-batch"))

    output = tmp_path / run_config.run_id / "gateway.jsonl"
    assert first.status == "written"
    assert retry.status == "idempotent"
    assert conflict.status == "written"
    assert output.read_bytes().count(b"\n") == 2
    assert output.read_bytes().splitlines()[0] == batch.canonical_bytes()


def test_writer_rejects_conflicting_bytes_for_one_batch_id(tmp_path, run_config) -> None:
    first = recorder_for(run_config).finish("completed")
    second_recorder = recorder_for(run_config)
    assert second_recorder.mark(
        "gateway.stt_request_started", correlation_id="corr", interaction_id="ix"
    ) is True
    second = second_recorder.finish("completed")
    assert first is not None and second is not None
    writer = LatencyProbeBatchWriter(tmp_path, run_config.run_id, "gateway")

    assert writer.write(first).status == "written"
    assert writer.write(second.with_batch_id(first.batch_id)).reason_code == "BATCH_CONFLICT"


def test_writer_maps_agent_server_batches_to_the_closed_agent_filename(tmp_path, run_config) -> None:
    batch = LatencyProbeRecorder(
        context=context_for(run_config),
        component="agent_server",
        phase="agent_foreground",
        run_config=run_config,
        source_instance_id_factory=lambda: "agent-source-1",
        clock_domain_id="agent-process-1",
        monotonic_ms=lambda: 10.0,
    ).finish("completed")
    assert batch is not None
    writer = LatencyProbeBatchWriter(tmp_path, run_config.run_id, "agent_server")

    assert writer.write(batch).status == "written"
    assert (tmp_path / run_config.run_id / "agent.jsonl").is_file()


def test_writer_contains_injected_write_failures(tmp_path, run_config, monkeypatch) -> None:
    batch = recorder_for(run_config).finish("completed")
    assert batch is not None
    writer = LatencyProbeBatchWriter(tmp_path, run_config.run_id, "gateway")

    def fail_write(*args, **kwargs):
        raise OSError("PRIVATE write failure")

    monkeypatch.setattr("pathlib.Path.open", fail_write)
    result = writer.write(batch)

    assert result.status == "failed"
    assert result.reason_code == "EXPORT_FAILED"
    assert "PRIVATE" not in repr(result)


def test_factory_feature_off_creates_no_runtime_or_files(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "run.json"
    config_path.write_text(json.dumps(valid_run_json()), encoding="utf-8")
    output_root = tmp_path / "output"
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_LATENCY_PROBE_ENABLED", "0")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_LATENCY_PROBE_RUN_CONFIG", str(config_path))
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_LATENCY_PROBE_OUTPUT_ROOT", str(output_root))

    assert create_latency_probe_runtime_from_environment("gateway") is None
    assert output_root.exists() is False
