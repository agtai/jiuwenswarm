# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from dataclasses import replace
import json
import threading
import time

import pytest

from jiuwenswarm.server.live_voice.latency_probe import (
    CORE_POINTS_BY_COMPONENT,
    LatencyBatch,
    LatencyProbeBatchWriter,
    LatencyProbeContext,
    LatencyProbeRecorder,
    LatencyProbeRuntime,
    LatencyProbeViolation,
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
        "input_case_ids": [
            "short-greeting-v1",
            "tool-weather-v1",
            "task-create-v1",
            "task-status-v1",
            "task-cancel-v1",
        ],
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
    assert run_config.input_case_ids == (
        "short-greeting-v1",
        "tool-weather-v1",
        "task-create-v1",
        "task-status-v1",
        "task-cancel-v1",
    )
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


def test_run_config_requires_one_ordered_input_case_per_fixed_profile(tmp_path) -> None:
    value = valid_run_json()
    value["input_case_ids"] = ["short-greeting-v1", "tool-weather-v1"]
    path = tmp_path / "mismatched-profile-cases.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(LatencyProbeViolation):
        load_latency_run_config(path)


def test_run_config_bounds_intended_attempts_to_256(tmp_path) -> None:
    accepted = valid_run_json()
    accepted["intended_attempts"] = 256
    accepted_path = tmp_path / "accepted-run.json"
    accepted_path.write_text(json.dumps(accepted), encoding="utf-8")

    assert load_latency_run_config(accepted_path).intended_attempts == 256

    rejected = valid_run_json()
    rejected["intended_attempts"] = 257
    rejected_path = tmp_path / "rejected-run.json"
    rejected_path.write_text(json.dumps(rejected), encoding="utf-8")

    with pytest.raises(ValueError):
        load_latency_run_config(rejected_path)


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
    assert try_parse_latency_probe_context(
        {**context.to_dict(), "input_case_id": "tool-weather-v1"}, run_config
    ) is None
    assert try_parse_latency_probe_context(
        {**context.to_dict(), "round_index": run_config.intended_attempts},
        run_config,
    ) is None
    assert try_parse_latency_probe_context(
        {**context.to_dict(), "round_index": 2**53},
        run_config,
    ) is None
    assert try_parse_latency_probe_context(context.to_dict(), object()) is None


def test_batch_rejects_out_of_policy_rounds_and_non_json_safe_generations(
    run_config,
) -> None:
    batch = browser_batch_for(run_config).to_dict()
    batch["round_index"] = run_config.intended_attempts
    batch["marks"][0]["round_index"] = run_config.intended_attempts
    with pytest.raises(LatencyProbeViolation):
        LatencyBatch.from_dict(batch, run_config)

    unsafe_generation = browser_batch_for(run_config).to_dict()
    unsafe_generation["marks"][0]["activation_generation"] = 2**53
    with pytest.raises(LatencyProbeViolation):
        LatencyBatch.from_dict(unsafe_generation, run_config)


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
    writer = LatencyProbeBatchWriter(tmp_path, run_config, "gateway")

    first = writer.write(batch)
    retry = writer.write(batch)
    conflict = writer.write(batch.with_batch_id("conflicting-batch"))

    output = tmp_path / run_config.run_id / "gateway.jsonl"
    assert first.status == "written"
    assert retry.status == "idempotent"
    assert conflict.status == "rejected"
    assert conflict.reason_code == "BATCH_CONFLICT"
    assert output.read_bytes().count(b"\n") == 1
    assert output.read_bytes().splitlines()[0] == batch.canonical_bytes()


def test_writer_rejects_conflicting_bytes_for_one_batch_id(tmp_path, run_config) -> None:
    first = recorder_for(run_config).finish("completed")
    second_recorder = recorder_for(run_config)
    assert second_recorder.mark(
        "gateway.stt_request_started", correlation_id="corr", interaction_id="ix"
    ) is True
    second = second_recorder.finish("completed")
    assert first is not None and second is not None
    writer = LatencyProbeBatchWriter(tmp_path, run_config, "gateway")

    assert writer.write(first).status == "written"
    assert writer.write(second.with_batch_id(first.batch_id)).reason_code == "BATCH_CONFLICT"


def test_writer_reconstructs_idempotency_and_conflict_receipts_after_restart(
    tmp_path, run_config
) -> None:
    first = recorder_for(run_config).finish("completed")
    second_recorder = recorder_for(run_config)
    assert second_recorder.mark(
        "gateway.stt_request_started", correlation_id="corr", interaction_id="ix"
    ) is True
    conflict = second_recorder.finish("completed")
    assert first is not None and conflict is not None
    assert LatencyProbeBatchWriter(tmp_path, run_config, "gateway").write(first).status == "written"

    restarted_writer = LatencyProbeBatchWriter(tmp_path, run_config, "gateway")
    assert restarted_writer.write(first).status == "idempotent"
    conflict_result = restarted_writer.write(conflict.with_batch_id(first.batch_id))
    assert conflict_result.status == "rejected"
    assert conflict_result.reason_code == "BATCH_CONFLICT"

    output = tmp_path / run_config.run_id / "gateway.jsonl"
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1


def test_writer_rejects_a_second_batch_for_a_durable_semantic_slot(
    tmp_path, run_config
) -> None:
    first = recorder_for(run_config).finish("completed")
    assert first is not None
    conflicting = first.with_batch_id("different-batch-for-same-slot")

    assert (
        LatencyProbeBatchWriter(tmp_path, run_config, "gateway").write(first).status
        == "written"
    )
    restarted = LatencyProbeBatchWriter(tmp_path, run_config, "gateway")
    result = restarted.write(conflicting)

    assert result.status == "rejected"
    assert result.reason_code == "BATCH_CONFLICT"
    output = tmp_path / run_config.run_id / "gateway.jsonl"
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1


def test_writer_finds_evicted_receipts_on_disk(tmp_path, run_config, monkeypatch) -> None:
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.latency_probe.MAX_WRITER_RECEIPTS",
        1,
    )
    writer = LatencyProbeBatchWriter(tmp_path, run_config, "gateway")
    first = recorder_for(run_config).finish("completed")
    assert first is not None
    second = replace(first, batch_id="gateway-batch-2", round_index=1)

    assert writer.write(first).status == "written"
    assert writer.write(second).status == "written"
    assert writer.write(first).status == "idempotent"

    output = tmp_path / run_config.run_id / "gateway.jsonl"
    assert len(output.read_text(encoding="utf-8").splitlines()) == 2


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
    writer = LatencyProbeBatchWriter(tmp_path, run_config, "agent_server")

    assert writer.write(batch).status == "written"
    assert (tmp_path / run_config.run_id / "agent.jsonl").is_file()


def test_writer_contains_injected_write_failures(tmp_path, run_config, monkeypatch) -> None:
    batch = recorder_for(run_config).finish("completed")
    assert batch is not None
    writer = LatencyProbeBatchWriter(tmp_path, run_config, "gateway")

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
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.latency_probe.load_latency_run_config",
        lambda path: (_ for _ in ()).throw(AssertionError("must not load while off")),
    )

    assert create_latency_probe_runtime_from_environment("gateway") is None
    assert output_root.exists() is False


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("run_id", "../../protected"),
        ("run_id", "/tmp/other"),
        ("environment_profile", "https://private.example/path"),
        ("audio_format", "C:\\Users\\private\\audio"),
        ("run_id", "PRIVATE_TRANSCRIPT_SENTINEL"),
    ],
)
def test_run_config_rejects_unsafe_paths_urls_and_private_descriptors(
    tmp_path, field, unsafe_value
) -> None:
    value = valid_run_json()
    value[field] = unsafe_value
    path = tmp_path / "run.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(LatencyProbeViolation) as error:
        load_latency_run_config(path)

    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert unsafe_value not in str(error.value)


def test_closed_config_parses_every_field_and_nested_experiment_contract(run_config) -> None:
    assert run_config.schema_version == "live-voice.latency-run.v0"
    assert run_config.run_id == "run-20260819-a"
    assert run_config.git_commit == "a" * 40
    assert run_config.source_state == "clean"
    assert run_config.allowlisted_feature_flags == (("formal_route", True),)
    assert run_config.cold_or_warm == "warm"
    assert run_config.intended_attempts == 5
    assert run_config.required_successes == 5
    assert {
        "environment_profile": run_config.environment_profile,
        "browser_family_and_version": run_config.browser_family_and_version,
        "browser_os_class": run_config.browser_os_class,
        "gateway_runtime_class": run_config.gateway_runtime_class,
        "agent_runtime_class": run_config.agent_runtime_class,
        "stt_provider_and_model": run_config.stt_provider_and_model,
        "tts_provider_and_model": run_config.tts_provider_and_model,
        "audio_format": run_config.audio_format,
        "vad_configuration": run_config.vad_configuration,
        "playout_configuration": run_config.playout_configuration,
    } == {
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
    }
    assert run_config.experiment is not None
    assert run_config.experiment.experiment_id == "buffer-tuning"
    assert run_config.experiment.target_segment == "response_total"
    assert run_config.experiment.target_statistic == "p50_ms"
    assert run_config.experiment.minimum_improvement_ms == 10.0
    assert run_config.experiment.response_total_minimum_improvement_ms == 5.0
    assert run_config.experiment.guardrails[0].to_dict() == {
        "metric": "failure_rate",
        "segment_id": None,
        "maximum_regression": 0.0,
    }
    expected_core_points = {
        "browser": {
            "browser.eot_received", "browser.stt_final_received", "browser.commit_submit_started",
            "browser.presentation_received", "browser.tts_request_started",
            "browser.downlink_first_frame_received", "browser.playout_first_frame_scheduled",
            "browser.playout_first_frame_started_estimate", "browser.playout_completed",
            "browser.playout_ack_received", "browser.next_turn_capture_activated",
            "browser.capture_start_requested", "browser.capture_device_started",
            "browser.media_socket_attached", "browser.capture_first_frame_sent",
            "browser.capture_first_ack_received", "browser.capture_stop_requested",
            "browser.capture_stopped", "browser.uplink_last_frame_sent",
            "browser.uplink_last_ack_received", "browser.uplink_closed",
            "browser.successor_capture_requested", "browser.successor_capture_ready",
            "browser.downlink_attach_started", "browser.downlink_attached",
            "browser.playout_underrun", "browser.playout_rebuffer",
        },
        "gateway": {
            "gateway.stt_request_started", "gateway.stt_provider_transport_open",
            "gateway.stt_session_ready", "gateway.vad_speech_stopped",
            "gateway.eot_control_sent", "gateway.stt_final_available",
            "gateway.stt_fallback_selected",
            "gateway.tts_request_received", "gateway.tts_provider_transport_open",
            "gateway.tts_provider_first_audio", "gateway.downlink_ticket_ready",
            "gateway.downlink_first_frame_sent",
        },
        "agent_server": {
            "agent.commit_submit_received", "agent.commit_accepted", "agent.route_resolved",
            "agent.agent_started", "agent.agent_first_delta", "agent.tool_execution_started",
            "agent.tool_execution_completed", "agent.agent_final", "agent.task_command_accepted",
            "agent.presentation_produced", "agent.presentation_dispatched",
        },
    }
    assert {component: set(points) for component, points in CORE_POINTS_BY_COMPONENT.items()} == expected_core_points
    for component, points in expected_core_points.items():
        for point in points:
            assert run_config.allows_point(point, component) is True


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.__setitem__("git_commit", "A" * 40),
        lambda value: value.__setitem__("allowlisted_feature_flags", {"route": "true"}),
        lambda value: value["experiment"].update(private="PRIVATE"),
        lambda value: value["experiment"]["guardrails"][0].update(private="PRIVATE"),
        lambda value: value["experiment"]["guardrails"][0].__setitem__("maximum_regression", float("inf")),
        lambda value: value["experiment"]["declared_experiment_points"][0].update(text="PRIVATE"),
        lambda value: value["experiment"]["declared_experiment_points"][0].__setitem__("component", "other"),
    ],
)
def test_run_config_rejects_nested_private_and_invalid_values(tmp_path, mutate) -> None:
    value = valid_run_json()
    mutate(value)
    path = tmp_path / "run.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(LatencyProbeViolation):
        load_latency_run_config(path)


def test_rejected_config_does_not_retain_read_error_causes(tmp_path) -> None:
    path = tmp_path / "private.json"
    path.write_bytes(b"\xff")

    with pytest.raises(LatencyProbeViolation) as error:
        load_latency_run_config(path)

    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def browser_batch_for(run_config) -> LatencyBatch:
    recorder = LatencyProbeRecorder(
        context=context_for(run_config),
        component="browser",
        phase="browser_round",
        run_config=run_config,
        source_instance_id_factory=lambda: "browser-source-1",
        batch_id_factory=lambda: "browser-batch-1",
        clock_domain_id="browser-page-1",
        monotonic_ms=lambda: 10.0,
    )
    assert recorder.mark(
        "browser.eot_received", correlation_id="corr", interaction_id="ix"
    ) is True
    batch = recorder.finish("completed")
    assert batch is not None
    return batch


def test_batch_round_trip_is_closed_and_rejects_duplicate_or_misplaced_capacity(run_config) -> None:
    batch = browser_batch_for(run_config)
    assert LatencyBatch.from_dict(batch.to_dict(), run_config).to_dict() == batch.to_dict()

    duplicate = batch.to_dict()
    duplicate["marks"] = [*duplicate["marks"], {**duplicate["marks"][0], "mark_index": 1}]
    with pytest.raises(LatencyProbeViolation):
        LatencyBatch.from_dict(duplicate, run_config)

    misplaced_capacity = batch.to_dict()
    misplaced_capacity["marks"] = [
        *misplaced_capacity["marks"],
        {
            **misplaced_capacity["marks"][0],
            "mark_index": 1,
            "point": "probe.capacity",
            "outcome": "unknown",
            "reason_code": "CAPACITY",
        },
    ]
    with pytest.raises(LatencyProbeViolation):
        LatencyBatch.from_dict(misplaced_capacity, run_config)


def test_writer_validates_direct_batches_and_rolls_back_partial_records(
    tmp_path, run_config, monkeypatch
) -> None:
    batch = browser_batch_for(run_config)
    malformed = replace(batch, marks=(batch.marks[0], replace(batch.marks[0], mark_index=1)))
    writer = LatencyProbeBatchWriter(tmp_path, run_config, "browser")
    assert writer.write(malformed).reason_code == "DUPLICATE_MARK"
    assert not (tmp_path / run_config.run_id / "browser.jsonl").exists()

    class PartialFile:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self._handle.close()

        def tell(self):
            return self._handle.tell()

        def write(self, data):
            return self._handle.write(data[:3])

        def truncate(self, offset):
            return self._handle.truncate(offset)

    real_open = __import__("pathlib").Path.open

    def partial_open(path, *args, **kwargs):
        return PartialFile(real_open(path, *args, **kwargs))

    monkeypatch.setattr("pathlib.Path.open", partial_open)
    result = writer.write(batch)
    assert result.reason_code == "EXPORT_FAILED"
    assert not (tmp_path / run_config.run_id / "browser.jsonl").exists()


def test_runtime_and_writer_contain_invalid_context_and_callback_failures(
    tmp_path, run_config, monkeypatch
) -> None:
    writer = LatencyProbeBatchWriter(tmp_path, run_config, "gateway")
    runtime = LatencyProbeRuntime(run_config, "gateway", writer)
    invalid_context = LatencyProbeContext(
        "wrong-schema", run_config.run_id, "dialogue_no_tool", "short-greeting-v1", -1
    )
    assert runtime.create_recorder(
        context=invalid_context,
        phase="gateway_stt",
        clock_domain_id="gateway-process-1",
        monotonic_ms=lambda: 10.0,
    ) is None
    recorder = recorder_for(run_config, clock=lambda: 10**100000)
    assert recorder.mark(
        "gateway.stt_request_started", correlation_id="corr", interaction_id="ix"
    ) is False

    batch = recorder_for(run_config).finish("completed")
    assert batch is not None
    monkeypatch.setattr(LatencyBatch, "canonical_bytes", lambda self: (_ for _ in ()).throw(RuntimeError("PRIVATE")))
    assert writer.write(batch).reason_code == "EXPORT_FAILED"

    monkeypatch.undo()
    monkeypatch.setattr("pathlib.Path.exists", lambda self: (_ for _ in ()).throw(OSError("PRIVATE")))
    assert writer.write(batch).reason_code == "EXPORT_FAILED"


def test_runtime_reuses_one_process_source_identity_for_every_recorder(
    tmp_path, run_config
) -> None:
    runtime = LatencyProbeRuntime(
        run_config,
        "gateway",
        LatencyProbeBatchWriter(tmp_path, run_config, "gateway"),
        source_instance_id="gateway-process-source",
    )
    first = runtime.create_recorder(
        context=context_for(run_config),
        phase="gateway_stt",
        clock_domain_id="gateway-process-1",
        monotonic_ms=lambda: 10.0,
    )
    second = runtime.create_recorder(
        context=context_for(run_config),
        phase="gateway_tts",
        clock_domain_id="gateway-process-1",
        monotonic_ms=lambda: 20.0,
    )
    assert first is not None and second is not None

    assert first.finish("completed").source_instance_id == "gateway-process-source"
    assert second.finish("completed").source_instance_id == "gateway-process-source"


def test_runtime_exports_finished_batches_off_path_and_supports_bounded_drain(
    run_config,
) -> None:
    class BlockingWriter:
        def __init__(self) -> None:
            self.entered = threading.Event()
            self.release = threading.Event()
            self.batches: list[LatencyBatch] = []

        def write(self, batch: LatencyBatch) -> object:
            self.entered.set()
            assert self.release.wait(2.0)
            self.batches.append(batch)
            return object()

    writer = BlockingWriter()
    runtime = LatencyProbeRuntime(run_config, "gateway", writer)  # type: ignore[arg-type]
    batch = recorder_for(run_config).finish("completed")
    assert batch is not None

    started = time.monotonic()
    assert runtime.submit(batch) is True
    elapsed = time.monotonic() - started

    assert elapsed < 0.1
    assert writer.entered.wait(1.0)
    assert runtime.drain(0.01) is False
    writer.release.set()
    assert runtime.drain(1.0) is True
    assert writer.batches == [batch]
    assert runtime.close(1.0) is True


def test_runtime_rolls_back_submission_when_export_thread_cannot_start(
    run_config, monkeypatch
) -> None:
    writer = type("Writer", (), {"write": lambda _self, _batch: object()})()
    runtime = LatencyProbeRuntime(run_config, "gateway", writer)  # type: ignore[arg-type]
    batch = recorder_for(run_config).finish("completed")
    assert batch is not None
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.latency_probe.Thread.start",
        lambda _self: (_ for _ in ()).throw(RuntimeError("THREAD_START_FAILED")),
    )

    assert runtime.submit(batch) is False
    assert runtime.drain(0.01) is True
    assert runtime.close(0.01) is True

def test_full_batch_requires_the_reserved_capacity_mark_in_slot_63(tmp_path, run_config) -> None:
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
    capacity_batch = recorder.finish("unknown")
    assert capacity_batch is not None
    ordinary_full_batch = replace(
        capacity_batch,
        marks=(
            *capacity_batch.marks[:63],
            replace(
                capacity_batch.marks[63],
                point="gateway.stt_request_started",
                outcome="observed",
                reason_code=None,
            ),
        ),
    )

    with pytest.raises(LatencyProbeViolation):
        LatencyBatch.from_dict(ordinary_full_batch.to_dict(), run_config)
    writer = LatencyProbeBatchWriter(tmp_path, run_config, "gateway")
    assert writer.write(ordinary_full_batch).reason_code == "INVALID_BATCH"
    assert not (tmp_path / run_config.run_id / "gateway.jsonl").exists()


def test_forged_run_config_is_rejected_at_recorder_runtime_and_writer_boundaries(
    tmp_path, run_config
) -> None:
    forged = replace(run_config, schema_version="wrong-schema")
    context = context_for(run_config)

    with pytest.raises(LatencyProbeViolation):
        LatencyProbeRecorder(
            context=context,
            component="gateway",
            phase="gateway_stt",
            run_config=forged,
            clock_domain_id="gateway-process-1",
            monotonic_ms=lambda: 10.0,
        )
    runtime = LatencyProbeRuntime(forged, "gateway", object())
    assert runtime.create_recorder(
        context=context,
        phase="gateway_stt",
        clock_domain_id="gateway-process-1",
        monotonic_ms=lambda: 10.0,
    ) is None
    with pytest.raises(LatencyProbeViolation):
        LatencyProbeBatchWriter(tmp_path, forged, "gateway")


def test_descriptors_allow_human_readable_sanitized_text_but_not_paths_or_secrets(tmp_path) -> None:
    value = valid_run_json()
    value["environment_profile"] = "Windows 11"
    path = tmp_path / "run.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    assert load_latency_run_config(path).environment_profile == "Windows 11"


@pytest.mark.parametrize("control", ("\x00", "\x1f", "\x7f", "\x80", "\x9f"))
def test_descriptors_reject_all_unicode_control_characters(tmp_path, control) -> None:
    value = valid_run_json()
    value["environment_profile"] = f"Windows 11{control}"
    path = tmp_path / "run.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(LatencyProbeViolation):
        load_latency_run_config(path)


def test_gateway_writer_can_persist_only_its_allowed_browser_and_gateway_producers(
    tmp_path, run_config
) -> None:
    writer = LatencyProbeBatchWriter(
        tmp_path,
        run_config,
        "gateway",
        mode="gateway_with_browser",
    )
    runtime = LatencyProbeRuntime(run_config, "gateway", writer)
    browser = browser_batch_for(run_config).with_batch_id("shared-cross-component-id")
    gateway = recorder_for(run_config).finish("completed")
    agent = LatencyProbeRecorder(
        context=context_for(run_config),
        component="agent_server",
        phase="agent_foreground",
        run_config=run_config,
        source_instance_id_factory=lambda: "agent-source-2",
        clock_domain_id="agent-process-2",
        monotonic_ms=lambda: 10.0,
    ).finish("completed")
    assert gateway is not None and agent is not None
    gateway = gateway.with_batch_id("shared-cross-component-id")

    assert runtime.writer.write(browser).status == "written"
    assert runtime.writer.write(gateway).status == "written"
    assert runtime.writer.write(agent).reason_code == "INCOMPATIBLE_RUN"
    assert (tmp_path / run_config.run_id / "browser.jsonl").is_file()
    assert (tmp_path / run_config.run_id / "gateway.jsonl").is_file()
    assert not (tmp_path / run_config.run_id / "agent.jsonl").exists()


@pytest.mark.parametrize(
    "mode", ("gateway_with_agent_server", "gateway_with_browser_and_agent_server")
)
def test_gateway_writer_rejects_arbitrary_multiproducer_modes(
    tmp_path, run_config, mode
) -> None:
    with pytest.raises(LatencyProbeViolation):
        LatencyProbeBatchWriter(tmp_path, run_config, "gateway", mode=mode)


def test_recorder_accepts_leading_hyphen_url_safe_generated_ids(run_config) -> None:
    recorder = LatencyProbeRecorder(
        context=context_for(run_config),
        component="gateway",
        phase="gateway_stt",
        run_config=run_config,
        source_instance_id_factory=lambda: "-source-generated-id",
        batch_id_factory=lambda: "-batch-generated-id",
        clock_domain_id="gateway-process-1",
        monotonic_ms=lambda: 10.0,
    )

    batch = recorder.finish("completed")
    assert batch is not None
    assert batch.source_instance_id == "-source-generated-id"
    assert batch.batch_id == "-batch-generated-id"


@pytest.mark.parametrize(
    ("source_instance_id", "batch_id"),
    [
        ("../../protected", "batch-id"),
        ("source-id", "https://private.example/batch"),
        ("PRIVATE_TRANSCRIPT", "batch-id"),
        ("", "batch-id"),
        ("source-id", "x" * 257),
    ],
)
def test_recorder_rejects_unsafe_or_unbounded_generated_ids(
    run_config, source_instance_id, batch_id
) -> None:
    with pytest.raises(LatencyProbeViolation):
        LatencyProbeRecorder(
            context=context_for(run_config),
            component="gateway",
            phase="gateway_stt",
            run_config=run_config,
            source_instance_id_factory=lambda: source_instance_id,
            batch_id_factory=lambda: batch_id,
            clock_domain_id="gateway-process-1",
            monotonic_ms=lambda: 10.0,
        )
