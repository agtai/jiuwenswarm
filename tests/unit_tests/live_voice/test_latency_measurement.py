from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import jiuwenswarm.server.live_voice.latency_measurement as latency_measurement

from jiuwenswarm.server.live_voice.latency_measurement import (
    L0EvidenceSource,
    L0MeasurementCollector,
    L0MeasurementViolation,
    L0Milestone,
    L0ProcessJsonlSink,
    L0RoundBinding,
    L0RoundClassification,
    L0RoundDeclaration,
    L0RoundTemperature,
    build_l0_measurement_report,
    create_l0_measurement_envelope,
    create_l0_milestone,
    declarations_from_records,
    load_l0_corpus_manifest,
    load_l0_jsonl,
    process_l0_sink,
    validate_l0_corpus_manifest,
)
from jiuwenswarm.server.live_voice.observability import (
    LiveVoiceObservabilityCollector,
)


SOURCE_HEAD = "c31e85ade1a69e934d05bfb9c277568a1238663c"
CORPUS_SHA = "2" * 64
BASE = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def _timestamp(offset_ms: float) -> str:
    return (BASE + timedelta(milliseconds=offset_ms)).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _binding(index: int, *, response_generation: int | None = None) -> L0RoundBinding:
    generation = index if response_generation is None else response_generation
    return L0RoundBinding(
        correlation_id=f"correlation-{index}",
        session_id=f"session-{index}",
        interaction_id=f"interaction-{index}",
        activation_generation=index + 1,
        response_id=f"response-{index}",
        response_generation=generation,
        turn_id=f"turn-{index}",
        round_id=f"round-{index}",
    )


def _record(
    milestone: L0Milestone,
    *,
    binding: L0RoundBinding,
    profile_id: str,
    scenario_id: str,
    sample_index: int,
    temperature: L0RoundTemperature,
    offset_ms: float,
    classification: L0RoundClassification = L0RoundClassification.UNKNOWN,
    evidence_source: L0EvidenceSource = L0EvidenceSource.INJECTED,
    nonce: str | None = None,
):
    completed = {
        L0Milestone.LAST_FRAME_SENT,
        L0Milestone.LAST_FRAME_ACKED,
        L0Milestone.STT_FINAL_AVAILABLE,
        L0Milestone.COMMITTED_SUBMIT_ACCEPTED,
        L0Milestone.FIRST_STABLE_SPEAKABLE_SENTENCE,
        L0Milestone.TOOL_RESULT_SUCCEEDED,
        L0Milestone.CHAT_FINAL,
        L0Milestone.PLAYOUT_COMPLETED,
    }
    return create_l0_milestone(
        milestone=milestone,
        binding=binding,
        profile_id=profile_id,
        scenario_id=scenario_id,
        sample_index=sample_index,
        temperature=temperature,
        classification=classification,
        evidence_source=evidence_source,
        observed_at=_timestamp(offset_ms),
        monotonic_ms=10_000 + offset_ms,
        duration_ms=offset_ms if milestone in completed else None,
        event_nonce=nonce,
    )


def _successful_round(
    index: int,
    *,
    profile_id: str,
    temperature: L0RoundTemperature,
    scenario_id: str = "short-no-tool-zh",
    evidence_source: L0EvidenceSource = L0EvidenceSource.INJECTED,
    task_identity: bool = False,
):
    binding = _binding(index)
    if task_identity:
        binding = replace(
            binding,
            task_id=f"task-{index}",
            attempt_id=f"attempt-{index}",
        )
    variable = index * 10
    points = (
        (L0Milestone.PROVIDER_EOT, 0),
        (L0Milestone.BROWSER_EOT_RECEIPT, 10),
        (L0Milestone.CAPTURE_STOPPED, 50),
        (L0Milestone.LAST_FRAME_SENT, 60),
        (L0Milestone.LAST_FRAME_ACKED, 80),
        (L0Milestone.UPLINK_CLOSED, 90),
        (L0Milestone.STT_FINAL_AVAILABLE, 600 + variable),
        (L0Milestone.COMMITTED_SUBMIT_ACCEPTED, 800 + variable),
        (L0Milestone.AGENT_REQUEST_START, 850 + variable),
        (L0Milestone.FIRST_DELTA, 1_100 + variable * 2),
        (L0Milestone.FIRST_STABLE_SPEAKABLE_SENTENCE, 1_500 + variable * 2),
        (L0Milestone.CHAT_FINAL, 2_200 + variable * 3),
        (L0Milestone.TTS_REQUEST, 2_250 + variable * 3),
        (L0Milestone.PROVIDER_FIRST_AUDIO, 2_450 + variable * 3.5),
        (L0Milestone.DOWNLINK_TICKET, 2_470 + variable * 3.5),
        (L0Milestone.SUCCESSOR_CAPTURE_READY, 2_480 + variable * 3.5),
        (L0Milestone.BROWSER_FIRST_FRAME, 2_500 + variable * 3.5),
        (L0Milestone.WEBAUDIO_FIRST_FRAME_SCHEDULED, 2_510 + variable * 3.5),
        (L0Milestone.WEBAUDIO_ACTUALLY_STARTED, 3_510 + variable * 3.5),
        (L0Milestone.PLAYOUT_COMPLETED, 5_000 + variable * 4),
    )
    records = [
        _record(
            milestone,
            binding=binding,
            profile_id=profile_id,
            scenario_id=scenario_id,
            sample_index=index,
            temperature=temperature,
            offset_ms=offset,
            classification=(
                L0RoundClassification.SUCCESS
                if milestone is L0Milestone.PLAYOUT_COMPLETED
                else L0RoundClassification.UNKNOWN
            ),
            evidence_source=evidence_source,
        )
        for milestone, offset in points
    ]
    return binding, records


def _register(
    collector: L0MeasurementCollector,
    *,
    binding: L0RoundBinding,
    profile_id: str,
    scenario_id: str,
    sample_index: int,
    temperature: L0RoundTemperature,
    evidence_source: L0EvidenceSource = L0EvidenceSource.INJECTED,
) -> None:
    assert collector.register_round(
        L0RoundDeclaration(
            binding=binding,
            profile_id=profile_id,
            scenario_id=scenario_id,
            sample_index=sample_index,
            temperature=temperature,
            evidence_source=evidence_source,
        )
    )


def test_fixed_corpus_is_closed_complete_and_digest_stable() -> None:
    path = Path("scripts/live_voice/l0_fixed_corpus.json")
    manifest, digest = load_l0_corpus_manifest(path)

    assert len(manifest["profiles"]) == 7
    assert len(manifest["cases"]) == 13
    assert digest == "888fdcba848037c1feba6c8c31a15641d721507b57e0985ba2d14446e7d4b563"
    assert {
        case["category"] for case in manifest["cases"]
    } >= {
        "short_no_tool",
        "long_answer",
        "real_tool",
        "task_create",
        "task_status",
        "task_cancel",
        "chinese_breath_pause",
        "barge_in",
        "silence",
        "mid_pause_truncation",
        "provider_slow",
        "provider_failure",
        "degraded_network",
    }
    assert all(profile["minimum_successful_rounds"] >= 20 for profile in manifest["profiles"])


def test_corpus_rejects_extensions_missing_categories_and_small_formal_sample() -> None:
    manifest = json.loads(Path("scripts/live_voice/l0_fixed_corpus.json").read_text(encoding="utf-8"))
    manifest["credential"] = "forbidden"
    with pytest.raises(L0MeasurementViolation, match="closed shape"):
        validate_l0_corpus_manifest(manifest)

    manifest = json.loads(Path("scripts/live_voice/l0_fixed_corpus.json").read_text(encoding="utf-8"))
    manifest["cases"] = [case for case in manifest["cases"] if case["category"] != "barge_in"]
    with pytest.raises(L0MeasurementViolation, match="missing required categories"):
        validate_l0_corpus_manifest(manifest)

    manifest = json.loads(Path("scripts/live_voice/l0_fixed_corpus.json").read_text(encoding="utf-8"))
    manifest["profiles"][0]["minimum_successful_rounds"] = 19
    with pytest.raises(L0MeasurementViolation, match="at least 20"):
        validate_l0_corpus_manifest(manifest)


def test_twenty_cold_and_warm_successes_use_production_collector_and_nearest_rank() -> None:
    l0 = L0MeasurementCollector()
    production = LiveVoiceObservabilityCollector()
    for temperature, profile_id in (
        (L0RoundTemperature.COLD, "injected-nominal-cold"),
        (L0RoundTemperature.WARM, "injected-nominal-warm"),
    ):
        for index in range(20):
            binding, records = _successful_round(
                index,
                profile_id=profile_id,
                temperature=temperature,
            )
            _register(
                l0,
                binding=binding,
                profile_id=profile_id,
                scenario_id="short-no-tool-zh",
                sample_index=index,
                temperature=temperature,
            )
            for record in records:
                assert production.emit_observation(record.observation)
                assert l0.consume(record)

    report = build_l0_measurement_report(
        l0,
        source_head=SOURCE_HEAD,
        environment_ref="environment-injected-local",
        corpus_sha256=CORPUS_SHA,
    )

    assert production.stats().accepted_observations == 800
    assert len(report["profiles"]) == 2
    for profile in report["profiles"]:
        assert profile["round_count"] == 20
        assert profile["success_count"] == 20
        assert profile["success_eligible_count"] == 20
        assert profile["failure_count"] == 0
        assert profile["fallback_count"] == 0
        audible = profile["percentiles"]["speech_end_to_webaudio_started_ms"]
        assert audible["sample_count"] == 20
        assert audible["p50_ms"] == 3_825.0
        assert audible["p95_ms"] == 4_140.0


def test_task_success_does_not_fabricate_agent_milestones_but_dialogue_requires_them() -> None:
    binding, records = _successful_round(
        0,
        profile_id="injected-nominal-warm",
        temperature=L0RoundTemperature.WARM,
        scenario_id="task-create-zh",
        task_identity=True,
    )
    records = [
        record
        for record in records
        if record.milestone
        not in {
            L0Milestone.AGENT_REQUEST_START,
            L0Milestone.FIRST_DELTA,
            L0Milestone.FIRST_STABLE_SPEAKABLE_SENTENCE,
            L0Milestone.CHAT_FINAL,
        }
    ]
    collector = L0MeasurementCollector()
    _register(
        collector,
        binding=binding,
        profile_id="injected-nominal-warm",
        scenario_id="task-create-zh",
        sample_index=0,
        temperature=L0RoundTemperature.WARM,
    )
    assert all(collector.consume(record) for record in records)

    task_report = build_l0_measurement_report(
        collector,
        source_head=SOURCE_HEAD,
        environment_ref="environment-injected-local",
        corpus_sha256=CORPUS_SHA,
        scenario_routes={"task-create-zh": "task"},
    )
    assert task_report["rounds"][0]["success_eligible"] is True
    assert task_report["rounds"][0]["expected_route"] == "task"
    assert task_report["rounds"][0]["missing_required_bindings"] == []
    assert task_report["rounds"][0]["spans_ms"]["agent_request_to_chat_final_ms"] is None

    dialogue_report = build_l0_measurement_report(
        collector,
        source_head=SOURCE_HEAD,
        environment_ref="environment-injected-local",
        corpus_sha256=CORPUS_SHA,
        scenario_routes={"task-create-zh": "dialogue"},
    )
    assert dialogue_report["rounds"][0]["success_eligible"] is False
    assert {
        "agent_request_start",
        "chat_final",
    } <= set(dialogue_report["rounds"][0]["missing_required_milestones"])


def test_tool_success_requires_authoritative_call_and_success_result_boundaries() -> None:
    binding, records = _successful_round(
        0,
        profile_id="injected-nominal-warm",
        temperature=L0RoundTemperature.WARM,
        scenario_id="real-tool-file-read-zh",
    )
    collector = L0MeasurementCollector()
    _register(
        collector,
        binding=binding,
        profile_id="injected-nominal-warm",
        scenario_id="real-tool-file-read-zh",
        sample_index=0,
        temperature=L0RoundTemperature.WARM,
    )
    assert all(collector.consume(record) for record in records)
    missing_report = build_l0_measurement_report(
        collector,
        source_head=SOURCE_HEAD,
        environment_ref="environment-injected-local",
        corpus_sha256=CORPUS_SHA,
        scenario_routes={"real-tool-file-read-zh": "tool"},
    )
    assert missing_report["rounds"][0]["success_eligible"] is False
    assert missing_report["rounds"][0]["missing_required_milestones"] == [
        "tool_call_observed",
        "tool_result_succeeded",
    ]

    for milestone, offset in (
        (L0Milestone.TOOL_CALL_OBSERVED, 1_300),
        (L0Milestone.TOOL_RESULT_SUCCEEDED, 1_600),
    ):
        assert collector.consume(
            _record(
                milestone,
                binding=binding,
                profile_id="injected-nominal-warm",
                scenario_id="real-tool-file-read-zh",
                sample_index=0,
                temperature=L0RoundTemperature.WARM,
                offset_ms=offset,
            )
        )
    complete_report = build_l0_measurement_report(
        collector,
        source_head=SOURCE_HEAD,
        environment_ref="environment-injected-local",
        corpus_sha256=CORPUS_SHA,
        scenario_routes={"real-tool-file-read-zh": "tool"},
    )
    assert complete_report["rounds"][0]["success_eligible"] is True


def test_no_tool_scenario_rejects_observed_tool_activity() -> None:
    binding, records = _successful_round(
        0,
        profile_id="injected-nominal-warm",
        temperature=L0RoundTemperature.WARM,
        scenario_id="short-no-tool-zh",
    )
    collector = L0MeasurementCollector()
    _register(
        collector,
        binding=binding,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=0,
        temperature=L0RoundTemperature.WARM,
    )
    assert all(collector.consume(record) for record in records)
    for milestone, offset in (
        (L0Milestone.TOOL_CALL_OBSERVED, 1_300),
        (L0Milestone.TOOL_RESULT_SUCCEEDED, 1_600),
    ):
        assert collector.consume(
            _record(
                milestone,
                binding=binding,
                profile_id="injected-nominal-warm",
                scenario_id="short-no-tool-zh",
                sample_index=0,
                temperature=L0RoundTemperature.WARM,
                offset_ms=offset,
            )
        )

    report = build_l0_measurement_report(
        collector,
        source_head=SOURCE_HEAD,
        environment_ref="environment-injected-local",
        corpus_sha256=CORPUS_SHA,
        scenario_routes={"short-no-tool-zh": "dialogue"},
        no_tool_scenarios=frozenset({"short-no-tool-zh"}),
    )
    round_report = report["rounds"][0]
    assert round_report["success_eligible"] is False
    assert round_report["unexpected_milestones"] == [
        "tool_call_observed",
        "tool_result_succeeded",
    ]


def test_task_declaration_accepts_generic_transport_facts_but_requires_exact_task_identity() -> None:
    task_binding = replace(
        _binding(8),
        task_id="task-8",
        attempt_id="attempt-8",
    )
    generic_binding = replace(task_binding, task_id=None, attempt_id=None)
    records = (
        _record(
            L0Milestone.PROVIDER_EOT,
            binding=generic_binding,
            profile_id="injected-nominal-warm",
            scenario_id="task-status-zh",
            sample_index=8,
            temperature=L0RoundTemperature.WARM,
            offset_ms=0,
        ),
        _record(
            L0Milestone.COMMITTED_SUBMIT_ACCEPTED,
            binding=task_binding,
            profile_id="injected-nominal-warm",
            scenario_id="task-status-zh",
            sample_index=8,
            temperature=L0RoundTemperature.WARM,
            offset_ms=10,
        ),
    )
    declarations = declarations_from_records(records)
    assert declarations[0].binding.task_id == "task-8"
    assert declarations[0].binding.attempt_id == "attempt-8"
    collector = L0MeasurementCollector()
    assert collector.register_round(declarations[0])
    assert all(collector.consume(record) for record in records)

    no_task_binding, no_task_records = _successful_round(
        9,
        profile_id="injected-nominal-warm",
        temperature=L0RoundTemperature.WARM,
        scenario_id="task-status-zh",
    )
    no_task = L0MeasurementCollector()
    _register(
        no_task,
        binding=no_task_binding,
        profile_id="injected-nominal-warm",
        scenario_id="task-status-zh",
        sample_index=9,
        temperature=L0RoundTemperature.WARM,
    )
    assert all(no_task.consume(record) for record in no_task_records)
    report = build_l0_measurement_report(
        no_task,
        source_head=SOURCE_HEAD,
        environment_ref="environment-injected-local",
        corpus_sha256=CORPUS_SHA,
        scenario_routes={"task-status-zh": "task"},
    )
    assert report["rounds"][0]["success_eligible"] is False
    assert report["rounds"][0]["missing_required_bindings"] == [
        "task_id",
        "attempt_id",
    ]


def test_missing_is_unknown_not_zero_and_stable_sentence_can_remain_unknown() -> None:
    binding, records = _successful_round(
        1,
        profile_id="injected-nominal-warm",
        temperature=L0RoundTemperature.WARM,
    )
    records = [
        record
        for record in records
        if record.milestone
        not in {
            L0Milestone.STT_FINAL_AVAILABLE,
            L0Milestone.FIRST_STABLE_SPEAKABLE_SENTENCE,
        }
    ]
    l0 = L0MeasurementCollector()
    _register(
        l0,
        binding=binding,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=1,
        temperature=L0RoundTemperature.WARM,
    )
    assert all(l0.consume(record) for record in records)

    report = build_l0_measurement_report(
        l0,
        source_head=SOURCE_HEAD,
        environment_ref="environment-injected-local",
        corpus_sha256=CORPUS_SHA,
    )

    round_report = report["rounds"][0]
    assert round_report["success_eligible"] is False
    assert "stt_final_available" in round_report["missing_required_milestones"]
    assert round_report["spans_ms"]["speech_end_to_stt_final_ms"] is None
    assert round_report["spans_ms"]["agent_request_to_first_stable_sentence_ms"] is None
    percentile = report["profiles"][0]["percentiles"]["speech_end_to_stt_final_ms"]
    assert percentile == {"sample_count": 0, "p50_ms": None, "p95_ms": None}


@pytest.mark.parametrize(
    ("mutation", "expected_isolated"),
    [
        ("session", True),
        ("activation", True),
        ("response", True),
        ("future_sample", True),
        ("task", True),
    ],
)
def test_wrong_scope_generation_response_task_and_future_observation_are_isolated(
    mutation: str, expected_isolated: bool
) -> None:
    del expected_isolated
    binding = _binding(4)
    l0 = L0MeasurementCollector()
    _register(
        l0,
        binding=binding,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=4,
        temperature=L0RoundTemperature.WARM,
    )
    mutated = binding
    sample_index = 4
    if mutation == "session":
        mutated = replace(binding, session_id="session-foreign")
    elif mutation == "activation":
        mutated = replace(binding, activation_generation=999)
    elif mutation == "response":
        mutated = replace(binding, response_generation=999)
    elif mutation == "future_sample":
        sample_index = 5
    elif mutation == "task":
        mutated = replace(binding, task_id="task-foreign", attempt_id="attempt-foreign")
    record = _record(
        L0Milestone.PROVIDER_EOT,
        binding=mutated,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=sample_index,
        temperature=L0RoundTemperature.WARM,
        offset_ms=0,
    )

    assert l0.consume(record) is False
    assert l0.records() == ()
    assert l0.stats().isolated_records == 1


def test_duplicate_is_idempotent_conflict_and_second_milestone_are_not_aggregated() -> None:
    binding = _binding(3)
    l0 = L0MeasurementCollector()
    _register(
        l0,
        binding=binding,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=3,
        temperature=L0RoundTemperature.WARM,
    )
    first = _record(
        L0Milestone.PROVIDER_EOT,
        binding=binding,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=3,
        temperature=L0RoundTemperature.WARM,
        offset_ms=0,
    )
    assert l0.consume(first)
    assert l0.consume(first)
    conflicting_payload = first.to_dict()
    conflicting_payload["observation"]["observed_at"] = _timestamp(1)
    assert l0.consume(conflicting_payload) is False
    second = _record(
        L0Milestone.PROVIDER_EOT,
        binding=binding,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=3,
        temperature=L0RoundTemperature.WARM,
        offset_ms=2,
        nonce="second",
    )
    assert l0.consume(second)

    report = build_l0_measurement_report(
        l0,
        source_head=SOURCE_HEAD,
        environment_ref="environment-injected-local",
        corpus_sha256=CORPUS_SHA,
    )
    assert l0.stats().idempotent_records == 1
    assert l0.stats().conflicting_records == 1
    assert report["rounds"][0]["duplicate_milestones"] == ["provider_eot"]
    assert report["rounds"][0]["success_eligible"] is False


def test_reordered_timeline_fails_success_filter_and_does_not_create_negative_latency() -> None:
    binding, records = _successful_round(
        2,
        profile_id="injected-nominal-warm",
        temperature=L0RoundTemperature.WARM,
    )
    records = [
        (
            _record(
                record.milestone,
                binding=binding,
                profile_id=record.profile_id,
                scenario_id=record.scenario_id,
                sample_index=record.sample_index,
                temperature=record.temperature,
                offset_ms=1_000,
                classification=record.classification,
            )
            if record.milestone is L0Milestone.PROVIDER_EOT
            else record
        )
        for record in records
    ]
    l0 = L0MeasurementCollector()
    _register(
        l0,
        binding=binding,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=2,
        temperature=L0RoundTemperature.WARM,
    )
    assert all(l0.consume(record) for record in records)
    report = build_l0_measurement_report(
        l0,
        source_head=SOURCE_HEAD,
        environment_ref="environment-injected-local",
        corpus_sha256=CORPUS_SHA,
    )
    round_report = report["rounds"][0]
    assert round_report["spans_ms"]["speech_end_to_stt_final_ms"] is None
    assert "speech_end_to_stt_final_ms" in round_report["invalid_order_spans"]
    assert round_report["success_eligible"] is False
def test_failure_fallback_cancel_and_quality_counts_never_enter_success_percentiles() -> None:
    l0 = L0MeasurementCollector()
    success_binding, success_records = _successful_round(
        0,
        profile_id="injected-nominal-warm",
        temperature=L0RoundTemperature.WARM,
    )
    _register(
        l0,
        binding=success_binding,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=0,
        temperature=L0RoundTemperature.WARM,
    )
    assert all(l0.consume(item) for item in success_records)

    for index, (classification, marker) in enumerate(
        (
            (L0RoundClassification.FAILURE, L0Milestone.FALSE_EOT),
            (L0RoundClassification.FALLBACK, L0Milestone.FALLBACK),
            (L0RoundClassification.CANCELLED, L0Milestone.FENCE_CANCEL_COMPLETION),
        ),
        start=1,
    ):
        binding = _binding(index)
        _register(
            l0,
            binding=binding,
            profile_id="injected-nominal-warm",
            scenario_id="short-no-tool-zh",
            sample_index=index,
            temperature=L0RoundTemperature.WARM,
        )
        assert l0.consume(
            _record(
                marker,
                binding=binding,
                profile_id="injected-nominal-warm",
                scenario_id="short-no-tool-zh",
                sample_index=index,
                temperature=L0RoundTemperature.WARM,
                offset_ms=100,
                classification=classification,
            )
        )
    assert l0.consume(
        _record(
            L0Milestone.UNDERRUN,
            binding=success_binding,
            profile_id="injected-nominal-warm",
            scenario_id="short-no-tool-zh",
            sample_index=0,
            temperature=L0RoundTemperature.WARM,
            offset_ms=4_000,
        )
    )

    report = build_l0_measurement_report(
        l0,
        source_head=SOURCE_HEAD,
        environment_ref="environment-injected-local",
        corpus_sha256=CORPUS_SHA,
    )
    profile = report["profiles"][0]
    assert profile["round_count"] == 4
    assert profile["success_count"] == 1
    assert profile["failure_count"] == 1
    assert profile["fallback_count"] == 1
    assert profile["cancelled_count"] == 1
    assert profile["success_eligible_count"] == 1
    assert profile["quality_counts"] == {
        "false_eot": 1,
        "fallback": 1,
        "fence_cancel_completion": 1,
        "underrun": 1,
    }
    assert profile["quality_coverage"]["underrun"] == "event_observed"
    assert profile["quality_coverage"]["rebuffer"] == "unknown"
    assert profile["percentiles"]["speech_end_to_webaudio_started_ms"]["sample_count"] == 1
    assert profile["percentiles"]["stop_to_silence_ms"]["sample_count"] == 0


def test_browser_failure_is_content_free_and_classified_as_failure() -> None:
    collector = L0MeasurementCollector()
    binding = _binding(0)
    _register(
        collector,
        binding=binding,
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=0,
        temperature=L0RoundTemperature.WARM,
        evidence_source=L0EvidenceSource.PHYSICAL,
    )
    assert collector.consume(
        _record(
            L0Milestone.BROWSER_FAILURE,
            binding=binding,
            profile_id="physical-formal-web-warm",
            scenario_id="short-no-tool-zh",
            sample_index=0,
            temperature=L0RoundTemperature.WARM,
            offset_ms=100,
            classification=L0RoundClassification.FAILURE,
            evidence_source=L0EvidenceSource.PHYSICAL,
        )
    )
    report = build_l0_measurement_report(
        collector,
        source_head=SOURCE_HEAD,
        environment_ref="environment-physical-local",
        corpus_sha256=CORPUS_SHA,
        no_tool_scenarios=frozenset({"short-no-tool-zh"}),
    )
    assert report["profiles"][0]["failure_count"] == 1
    round_report = report["rounds"][0]
    assert round_report["classification"] == "failure"
    assert round_report["success_eligible"] is False
    assert "private" not in json.dumps(report)


@pytest.mark.parametrize(
    ("milestone", "expected_classification"),
    (
        (L0Milestone.BROWSER_FAILURE, "failure"),
        (L0Milestone.FRAME_LOSS, "failure"),
        (L0Milestone.FALSE_EOT, "failure"),
        (L0Milestone.MISSED_EOT, "failure"),
        (L0Milestone.FALLBACK, "fallback"),
        (L0Milestone.FENCE_CANCEL_COMPLETION, "cancelled"),
    ),
)
def test_unknown_failure_fallback_or_cancel_marker_overrides_terminal_success(
    milestone: L0Milestone,
    expected_classification: str,
) -> None:
    collector = L0MeasurementCollector()
    binding, records = _successful_round(
        0,
        profile_id="physical-formal-web-warm",
        temperature=L0RoundTemperature.WARM,
        evidence_source=L0EvidenceSource.PHYSICAL,
    )
    _register(
        collector,
        binding=binding,
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=0,
        temperature=L0RoundTemperature.WARM,
        evidence_source=L0EvidenceSource.PHYSICAL,
    )
    assert all(collector.consume(record) for record in records)
    assert collector.consume(
        _record(
            milestone,
            binding=binding,
            profile_id="physical-formal-web-warm",
            scenario_id="short-no-tool-zh",
            sample_index=0,
            temperature=L0RoundTemperature.WARM,
            offset_ms=9_000,
            evidence_source=L0EvidenceSource.PHYSICAL,
        )
    )

    report = build_l0_measurement_report(
        collector,
        source_head=SOURCE_HEAD,
        environment_ref="environment-physical-local",
        corpus_sha256=CORPUS_SHA,
    )
    assert report["rounds"][0]["classification"] == expected_classification
    assert report["rounds"][0]["success_eligible"] is False
    assert report["profiles"][0][f"{expected_classification}_count"] == 1
    assert report["profiles"][0]["success_eligible_count"] == 0


def test_recovered_fallback_stays_fallback_and_cancel_span_uses_cancelled_round() -> None:
    collector = L0MeasurementCollector()
    fallback_binding, fallback_records = _successful_round(
        0,
        profile_id="injected-nominal-warm",
        temperature=L0RoundTemperature.WARM,
    )
    _register(
        collector,
        binding=fallback_binding,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=0,
        temperature=L0RoundTemperature.WARM,
    )
    assert all(collector.consume(record) for record in fallback_records)
    assert collector.consume(
        _record(
            L0Milestone.FALLBACK,
            binding=fallback_binding,
            profile_id="injected-nominal-warm",
            scenario_id="short-no-tool-zh",
            sample_index=0,
            temperature=L0RoundTemperature.WARM,
            offset_ms=700,
            classification=L0RoundClassification.FALLBACK,
        )
    )

    cancel_binding = _binding(1)
    _register(
        collector,
        binding=cancel_binding,
        profile_id="injected-nominal-warm",
        scenario_id="playout-barge-in-zh",
        sample_index=1,
        temperature=L0RoundTemperature.WARM,
    )
    for milestone, offset, classification in (
        (L0Milestone.BARGE_IN, 3_000, L0RoundClassification.UNKNOWN),
        (
            L0Milestone.FENCE_CANCEL_COMPLETION,
            3_080,
            L0RoundClassification.CANCELLED,
        ),
    ):
        assert collector.consume(
            _record(
                milestone,
                binding=cancel_binding,
                profile_id="injected-nominal-warm",
                scenario_id="playout-barge-in-zh",
                sample_index=1,
                temperature=L0RoundTemperature.WARM,
                offset_ms=offset,
                classification=classification,
            )
        )
    report = build_l0_measurement_report(
        collector,
        source_head=SOURCE_HEAD,
        environment_ref="environment-injected-local",
        corpus_sha256=CORPUS_SHA,
    )
    profile = report["profiles"][0]
    assert profile["fallback_count"] == 1
    assert profile["success_count"] == 0
    assert profile["cancelled_count"] == 1
    assert profile["percentiles"]["stop_to_silence_ms"] == {
        "sample_count": 1,
        "p50_ms": 80.0,
        "p95_ms": 80.0,
    }


def test_private_content_unknown_fields_and_unmeasured_completed_duration_fail_closed() -> None:
    with pytest.raises(L0MeasurementViolation, match="safe identity"):
        L0RoundBinding(
            correlation_id="correlation-1",
            session_id="session api_key value",
            interaction_id="interaction-1",
            activation_generation=1,
        )

    binding = _binding(1)
    with pytest.raises(L0MeasurementViolation, match="measured duration"):
        create_l0_milestone(
            milestone=L0Milestone.CHAT_FINAL,
            binding=binding,
            profile_id="injected-nominal-warm",
            scenario_id="short-no-tool-zh",
            sample_index=1,
            temperature=L0RoundTemperature.WARM,
            evidence_source=L0EvidenceSource.INJECTED,
        )

    record = _record(
        L0Milestone.PROVIDER_EOT,
        binding=binding,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=1,
        temperature=L0RoundTemperature.WARM,
        offset_ms=0,
    ).to_dict()
    record["raw_audio"] = "forbidden"
    with pytest.raises(L0MeasurementViolation, match="closed shape"):
        create_l0_measurement_envelope(record)


def test_jsonl_sink_roundtrip_is_content_free_and_declarations_reject_mixed_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    binding = _binding(7)
    record = _record(
        L0Milestone.PROVIDER_EOT,
        binding=binding,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=7,
        temperature=L0RoundTemperature.WARM,
        offset_ms=0,
    )
    fsync_calls: list[int] = []
    real_fsync = latency_measurement.os.fsync

    def fsync(descriptor: int) -> None:
        fsync_calls.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(latency_measurement.os, "fsync", fsync)
    sink = L0ProcessJsonlSink(tmp_path, component="gateway")
    assert sink.emit(record)
    assert len(fsync_calls) == 1
    loaded = load_l0_jsonl((sink.path,))
    assert loaded == (record,)
    assert declarations_from_records(loaded)[0].binding == binding
    assert "stimulus_text" not in sink.path.read_text(encoding="utf-8")

    foreign = _record(
        L0Milestone.BROWSER_EOT_RECEIPT,
        binding=replace(binding, session_id="session-foreign"),
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=7,
        temperature=L0RoundTemperature.WARM,
        offset_ms=1,
    )
    with pytest.raises(L0MeasurementViolation, match="mixed identity"):
        declarations_from_records((record, foreign))


def test_early_partial_identity_merges_with_later_exact_response_without_rebinding() -> None:
    full = _binding(8)
    early = replace(
        full,
        response_id=None,
        response_generation=None,
        turn_id=None,
        round_id=None,
    )
    provider = _record(
        L0Milestone.PROVIDER_EOT,
        binding=early,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=8,
        temperature=L0RoundTemperature.WARM,
        offset_ms=0,
    )
    final = _record(
        L0Milestone.CHAT_FINAL,
        binding=full,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=8,
        temperature=L0RoundTemperature.WARM,
        offset_ms=1_000,
    )

    declaration = declarations_from_records((provider, final))[0]
    assert declaration.binding == full
    collector = L0MeasurementCollector()
    assert collector.register_round(declaration)
    assert collector.consume(provider)
    assert collector.consume(final)

    wrong = _record(
        L0Milestone.FIRST_DELTA,
        binding=replace(full, response_generation=999),
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=8,
        temperature=L0RoundTemperature.WARM,
        offset_ms=500,
    )
    assert collector.consume(wrong) is False
    assert collector.stats().isolated_records == 1


def test_task_identity_requires_complete_task_attempt_pair() -> None:
    full = replace(_binding(9), task_id="task-9", attempt_id="attempt-9")

    with pytest.raises(L0MeasurementViolation, match="present together"):
        replace(full, attempt_id=None)
    with pytest.raises(L0MeasurementViolation, match="present together"):
        replace(full, task_id=None)

    declaration = L0RoundDeclaration(
        binding=full,
        profile_id="injected-nominal-warm",
        scenario_id="task-query-en",
        sample_index=9,
        temperature=L0RoundTemperature.WARM,
        evidence_source=L0EvidenceSource.INJECTED,
    )
    generic = replace(full, task_id=None, attempt_id=None)
    collector = L0MeasurementCollector()
    assert collector.register_round(declaration)
    assert collector.consume(
        _record(
            L0Milestone.PROVIDER_EOT,
            binding=generic,
            profile_id="injected-nominal-warm",
            scenario_id="task-query-en",
            sample_index=9,
            temperature=L0RoundTemperature.WARM,
            offset_ms=0,
        )
    )


def test_collector_pins_first_exact_response_after_partial_declaration() -> None:
    full = _binding(9)
    early = replace(
        full,
        response_id=None,
        response_generation=None,
        turn_id=None,
        round_id=None,
    )
    collector = L0MeasurementCollector()
    _register(
        collector,
        binding=early,
        profile_id="injected-nominal-warm",
        scenario_id="short-no-tool-zh",
        sample_index=9,
        temperature=L0RoundTemperature.WARM,
    )
    assert collector.consume(
        _record(
            L0Milestone.PROVIDER_EOT,
            binding=early,
            profile_id="injected-nominal-warm",
            scenario_id="short-no-tool-zh",
            sample_index=9,
            temperature=L0RoundTemperature.WARM,
            offset_ms=0,
        )
    )
    assert collector.consume(
        _record(
            L0Milestone.FIRST_DELTA,
            binding=full,
            profile_id="injected-nominal-warm",
            scenario_id="short-no-tool-zh",
            sample_index=9,
            temperature=L0RoundTemperature.WARM,
            offset_ms=100,
        )
    )
    assert collector.declarations()[0].binding == full
    assert collector.consume(
        _record(
            L0Milestone.CHAT_FINAL,
            binding=replace(
                full,
                response_id="response-foreign",
                response_generation=1_000,
            ),
            profile_id="injected-nominal-warm",
            scenario_id="short-no-tool-zh",
            sample_index=9,
            temperature=L0RoundTemperature.WARM,
            offset_ms=200,
        )
    ) is False
    assert collector.stats().isolated_records == 1


def test_feature_off_process_sink_creates_no_directory_or_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "must-not-exist"
    monkeypatch.delenv("JIUWENSWARM_LIVE_VOICE_L0_MEASUREMENT_DIR", raising=False)
    # Use a unique component so the process cache cannot contain a prior test value.
    assert process_l0_sink("feature-off-test") is None
    assert not target.exists()


def test_registered_response_freezes_labels_and_conflicting_rebind_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels_a = (
        "physical-formal-web-warm",
        "short-no-tool-zh",
        30,
        L0RoundTemperature.WARM,
        L0EvidenceSource.PHYSICAL,
    )
    labels_b = (
        "physical-formal-web-warm",
        "long-answer-zh",
        31,
        L0RoundTemperature.WARM,
        L0EvidenceSource.PHYSICAL,
    )
    current_labels = [labels_a]
    emitted = []

    class _Sink:
        def emit(self, record: object) -> bool:
            emitted.append(record)
            return True

    monkeypatch.setattr(
        latency_measurement,
        "runtime_l0_run_labels",
        lambda: current_labels[0],
    )
    monkeypatch.setattr(
        latency_measurement,
        "process_l0_sink",
        lambda _component: _Sink(),
    )
    latency_measurement._RUNTIME_L0_BINDINGS.clear()
    latency_measurement._RUNTIME_L0_BLOCKED.clear()
    binding = _binding(30)
    try:
        assert latency_measurement.register_runtime_l0_binding(binding)
        current_labels[0] = labels_b
        assert latency_measurement.emit_runtime_l0_milestone(
            component="agent",
            milestone=L0Milestone.CHAT_FINAL,
            binding=binding,
            duration_ms=100.0,
        )
        assert len(emitted) == 1
        assert emitted[0].profile_id == labels_a[0]
        assert emitted[0].scenario_id == labels_a[1]
        assert emitted[0].sample_index == labels_a[2]

        assert latency_measurement.register_runtime_l0_binding(binding) is False
        assert (
            latency_measurement.resolve_runtime_l0_binding(
                correlation_id=binding.correlation_id,
                interaction_id=binding.interaction_id,
                response_id=binding.response_id or "",
                response_generation=binding.response_generation or 0,
            )
            is None
        )
    finally:
        latency_measurement._RUNTIME_L0_BINDINGS.clear()
        latency_measurement._RUNTIME_L0_BLOCKED.clear()


def test_conflicting_response_cannot_rebind_after_tombstone_capacity_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels_a = (
        "physical-formal-web-warm",
        "short-no-tool-zh",
        100,
        L0RoundTemperature.WARM,
        L0EvidenceSource.PHYSICAL,
    )
    labels_b = (
        "physical-formal-web-warm",
        "long-answer-zh",
        101,
        L0RoundTemperature.WARM,
        L0EvidenceSource.PHYSICAL,
    )
    current_labels = [labels_a]
    emitted = []

    class _Sink:
        def emit(self, record: object) -> bool:
            emitted.append(record)
            return True

    monkeypatch.setattr(
        latency_measurement,
        "runtime_l0_run_labels",
        lambda: current_labels[0],
    )
    monkeypatch.setattr(
        latency_measurement,
        "process_l0_sink",
        lambda _component: _Sink(),
    )
    latency_measurement._RUNTIME_L0_BINDINGS.clear()
    latency_measurement._RUNTIME_L0_BLOCKED.clear()
    binding = _binding(100)
    conflicting_binding = replace(
        binding,
        session_id="session-conflicting",
        activation_generation=binding.activation_generation + 1,
    )
    try:
        latency_measurement._RUNTIME_L0_BLOCKED.update(
            (
                "filled-correlation",
                f"filled-interaction-{index}",
                f"filled-response-{index}",
                index,
            )
            for index in range(latency_measurement._RUNTIME_L0_BINDING_CAPACITY)
        )
        assert latency_measurement.register_runtime_l0_binding(binding)
        current_labels[0] = labels_b
        assert (
            latency_measurement.register_runtime_l0_binding(conflicting_binding)
            is False
        )
        assert (
            latency_measurement.register_runtime_l0_binding(conflicting_binding)
            is False
        )
        assert (
            latency_measurement.resolve_runtime_l0_binding(
                correlation_id=binding.correlation_id,
                interaction_id=binding.interaction_id,
                response_id=binding.response_id or "",
                response_generation=binding.response_generation or 0,
            )
            is None
        )
        assert not latency_measurement.emit_runtime_l0_milestone(
            component="agent",
            milestone=L0Milestone.CHAT_FINAL,
            binding=binding,
            duration_ms=100.0,
        )
        assert emitted == []
    finally:
        latency_measurement._RUNTIME_L0_BINDINGS.clear()
        latency_measurement._RUNTIME_L0_BLOCKED.clear()


def test_dynamic_run_labels_file_is_closed_content_free_and_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jiuwenswarm.server.live_voice.latency_measurement import (
        L0_MEASUREMENT_RUN_LABELS_FILE_ENV,
        L0_RUN_LABELS_VERSION,
        runtime_l0_run_labels,
    )

    path = tmp_path / "run-labels.json"
    monkeypatch.setenv(L0_MEASUREMENT_RUN_LABELS_FILE_ENV, str(path))
    path.write_text(
        json.dumps(
            {
                "schema_version": L0_RUN_LABELS_VERSION,
                "profile_id": "physical-formal-web-warm",
                "scenario_id": "short-no-tool-zh",
                "sample_index": 8,
                "temperature": "warm",
                "evidence_source": "physical",
            }
        ),
        encoding="utf-8",
    )
    assert runtime_l0_run_labels() == (
        "physical-formal-web-warm",
        "short-no-tool-zh",
        8,
        L0RoundTemperature.WARM,
        L0EvidenceSource.PHYSICAL,
    )

    path.write_text(
        json.dumps(
            {
                "schema_version": L0_RUN_LABELS_VERSION,
                "profile_id": "physical-formal-web-warm",
                "scenario_id": "short-no-tool-zh",
                "sample_index": 8,
                "temperature": "warm",
                "evidence_source": "physical",
                "transcript": "forbidden",
            }
        ),
        encoding="utf-8",
    )
    assert runtime_l0_run_labels() is None
