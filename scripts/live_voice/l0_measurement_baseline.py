from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jiuwenswarm.server.live_voice.latency_measurement import (  # noqa: E402
    L0EvidenceSource,
    L0MeasurementCollector,
    L0Milestone,
    L0RoundBinding,
    L0RoundClassification,
    L0RoundDeclaration,
    L0RoundTemperature,
    build_l0_measurement_report,
    canonical_json_bytes,
    create_l0_milestone,
    declarations_from_records,
    load_l0_corpus_manifest,
    load_l0_jsonl,
)
from jiuwenswarm.server.live_voice.observability import (  # noqa: E402
    LiveVoiceObservabilityCollector,
)


DEFAULT_CORPUS = REPO_ROOT / "scripts" / "live_voice" / "l0_fixed_corpus.json"
PROVIDER_REPORT_VERSION = "live-voice.l0-provider-component-report.v3"
INJECTED_ENVIRONMENT_REF = "environment-injected-current-tree"
PROVIDER_ENVIRONMENT_REF = "environment-provider-machine-current"
_LOCAL_NONSOURCE_PREFIXES = (".codex_tmp/",)
_RUN_SOURCE_METADATA_NAME = "browser-session.json"
_BASE_TIME = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
_COMPLETED = frozenset(
    {
        L0Milestone.LAST_FRAME_SENT,
        L0Milestone.LAST_FRAME_ACKED,
        L0Milestone.STT_FINAL_AVAILABLE,
        L0Milestone.COMMITTED_SUBMIT_ACCEPTED,
        L0Milestone.FIRST_STABLE_SPEAKABLE_SENTENCE,
        L0Milestone.TOOL_RESULT_SUCCEEDED,
        L0Milestone.CHAT_FINAL,
        L0Milestone.PLAYOUT_COMPLETED,
    }
)


def _source_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def clean_source_head(requested: str | None = None) -> str:
    head = _source_head()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    source_changes = []
    for raw_line in status.splitlines():
        path = raw_line[3:].replace("\\", "/").strip('"')
        if raw_line.startswith("?? ") and any(
            path == prefix.rstrip("/") or path.startswith(prefix)
            for prefix in _LOCAL_NONSOURCE_PREFIXES
        ):
            continue
        source_changes.append(raw_line)
    if source_changes:
        raise RuntimeError("source-bound L0 evidence requires a clean worktree")
    if requested is not None and requested != head:
        raise RuntimeError("requested source HEAD differs from the clean worktree")
    return head


def _write_json(path: Path, value: object) -> None:
    encoded = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="ascii")
    temporary.replace(path)


def _timestamp(offset_ms: float) -> str:
    return (_BASE_TIME + timedelta(milliseconds=offset_ms)).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _binding(
    profile_index: int,
    sample_index: int,
    *,
    task_identity: bool = False,
) -> L0RoundBinding:
    prefix = f"l0-{profile_index}-{sample_index}"
    return L0RoundBinding(
        correlation_id=f"correlation-{prefix}",
        session_id=f"session-{prefix}",
        interaction_id=f"interaction-{prefix}",
        activation_generation=sample_index + 1,
        response_id=f"response-{prefix}",
        response_generation=sample_index,
        turn_id=f"turn-{prefix}",
        round_id=f"round-{prefix}",
        task_id=f"task-{prefix}" if task_identity else None,
        attempt_id=f"attempt-{prefix}" if task_identity else None,
    )


def _emit_round(
    collector: L0MeasurementCollector,
    production_collector: LiveVoiceObservabilityCollector,
    *,
    profile_index: int,
    profile_id: str,
    scenario_id: str,
    sample_index: int,
    temperature: L0RoundTemperature,
    classification: L0RoundClassification,
    offsets: Sequence[tuple[L0Milestone, float]],
    quality: Sequence[tuple[L0Milestone, float]] = (),
    task_identity: bool = False,
) -> None:
    binding = _binding(
        profile_index,
        sample_index,
        task_identity=task_identity,
    )
    declaration = L0RoundDeclaration(
        binding=binding,
        profile_id=profile_id,
        scenario_id=scenario_id,
        sample_index=sample_index,
        temperature=temperature,
        evidence_source=L0EvidenceSource.INJECTED,
    )
    if not collector.register_round(declaration):
        raise RuntimeError("injected round declaration was not unique")
    final_index = len(offsets) - 1
    for index, (milestone, offset_ms) in enumerate((*offsets, *quality)):
        envelope = create_l0_milestone(
            milestone=milestone,
            binding=binding,
            profile_id=profile_id,
            scenario_id=scenario_id,
            sample_index=sample_index,
            temperature=temperature,
            classification=(
                classification
                if index == final_index
                else L0RoundClassification.UNKNOWN
            ),
            evidence_source=L0EvidenceSource.INJECTED,
            observed_at=_timestamp(
                profile_index * 10_000_000 + sample_index * 100_000 + offset_ms
            ),
            monotonic_ms=sample_index * 100_000 + offset_ms,
            duration_ms=offset_ms if milestone in _COMPLETED else None,
            event_nonce=f"{profile_index}-{sample_index}-{index}",
        )
        if not production_collector.emit_observation(envelope.observation):
            raise RuntimeError("production observability collector rejected an L0 marker")
        if not collector.consume(envelope):
            raise RuntimeError("L0 collector rejected an injected production marker")


def _success_offsets(*, sample_index: int, cold: bool, degraded: bool) -> tuple[tuple[L0Milestone, float], ...]:
    cold_penalty = 700 if cold else 0
    network_penalty = 420 if degraded else 0
    spread = (sample_index % 7) * 37
    agent_start = 820 + cold_penalty + network_penalty + spread
    return (
        (L0Milestone.PROVIDER_EOT, 0),
        (L0Milestone.BROWSER_EOT_RECEIPT, 8 + network_penalty * 0.05),
        (L0Milestone.CAPTURE_STOPPED, 44),
        (L0Milestone.LAST_FRAME_SENT, 58),
        (L0Milestone.LAST_FRAME_ACKED, 78 + network_penalty * 0.20),
        (L0Milestone.UPLINK_CLOSED, 90 + network_penalty * 0.25),
        (
            L0Milestone.STT_FINAL_AVAILABLE,
            560 + cold_penalty * 0.35 + network_penalty + spread,
        ),
        (
            L0Milestone.COMMITTED_SUBMIT_ACCEPTED,
            760 + cold_penalty * 0.35 + network_penalty + spread,
        ),
        (L0Milestone.AGENT_REQUEST_START, agent_start),
        (L0Milestone.FIRST_DELTA, agent_start + 260 + spread),
        (
            L0Milestone.FIRST_STABLE_SPEAKABLE_SENTENCE,
            agent_start + 610 + spread * 1.3,
        ),
        (L0Milestone.CHAT_FINAL, agent_start + 1_350 + spread * 2),
        (L0Milestone.TTS_REQUEST, agent_start + 1_410 + spread * 2),
        (
            L0Milestone.PROVIDER_FIRST_AUDIO,
            agent_start + 1_650 + cold_penalty * 0.25 + spread * 2.2,
        ),
        (
            L0Milestone.DOWNLINK_TICKET,
            agent_start + 1_675 + cold_penalty * 0.25 + spread * 2.2,
        ),
        (
            L0Milestone.SUCCESSOR_CAPTURE_READY,
            agent_start + 1_680 + cold_penalty * 0.25 + spread * 2.2,
        ),
        (
            L0Milestone.BROWSER_FIRST_FRAME,
            agent_start + 1_705 + cold_penalty * 0.25 + network_penalty + spread * 2.2,
        ),
        (
            L0Milestone.WEBAUDIO_FIRST_FRAME_SCHEDULED,
            agent_start + 1_715 + cold_penalty * 0.25 + network_penalty + spread * 2.2,
        ),
        (
            L0Milestone.WEBAUDIO_ACTUALLY_STARTED,
            agent_start + 2_715 + cold_penalty * 0.25 + network_penalty + spread * 2.2,
        ),
        (
            L0Milestone.PLAYOUT_COMPLETED,
            agent_start + 4_100 + cold_penalty * 0.25 + network_penalty + spread * 2.5,
        ),
    )


def _route_success_offsets(
    *,
    sample_index: int,
    cold: bool,
    degraded: bool,
    expected_route: object,
) -> tuple[tuple[L0Milestone, float], ...]:
    offsets = _success_offsets(
        sample_index=sample_index,
        cold=cold,
        degraded=degraded,
    )
    if expected_route != "tool":
        return offsets
    agent_start = next(
        value for milestone, value in offsets
        if milestone is L0Milestone.AGENT_REQUEST_START
    )
    tool_points = (
        (L0Milestone.TOOL_CALL_OBSERVED, agent_start + 420),
        (L0Milestone.TOOL_RESULT_SUCCEEDED, agent_start + 780),
    )
    return tuple(sorted((*offsets, *tool_points), key=lambda item: item[1]))


def build_injected_baseline(
    *,
    corpus_path: Path,
    successful_rounds: int,
    source_head: str,
) -> dict[str, object]:
    if successful_rounds < 20:
        raise ValueError("injected formal profiles require at least 20 successful rounds")
    manifest, digest = load_l0_corpus_manifest(corpus_path)
    cases = {
        str(case["case_id"]): case
        for case in manifest["cases"]
    }
    successful_cases = [
        case_id
        for case_id, case in cases.items()
        if case["expected_classification"] == "success"
    ]
    profiles = [
        profile
        for profile in manifest["profiles"]
        if str(profile["profile_id"]).startswith("injected-")
    ]
    collector = L0MeasurementCollector()
    production_collector = LiveVoiceObservabilityCollector(max_observations=20_000)
    for profile_index, profile in enumerate(profiles):
        profile_id = str(profile["profile_id"])
        temperature = L0RoundTemperature(str(profile["temperature_policy"]))
        degraded = profile_id == "injected-degraded-warm"
        for sample_index in range(successful_rounds):
            scenario_id = successful_cases[sample_index % len(successful_cases)]
            quality = (
                (
                    (L0Milestone.UNDERRUN, 3_900 + sample_index),
                    (L0Milestone.REBUFFER, 3_950 + sample_index),
                )
                if degraded and sample_index in {0, 10}
                else ()
            )
            _emit_round(
                collector,
                production_collector,
                profile_index=profile_index,
                profile_id=profile_id,
                scenario_id=scenario_id,
                sample_index=sample_index,
                temperature=temperature,
                classification=L0RoundClassification.SUCCESS,
                offsets=_route_success_offsets(
                    sample_index=sample_index,
                    cold=temperature is L0RoundTemperature.COLD,
                    degraded=degraded,
                    expected_route=cases[scenario_id]["expected_route"],
                ),
                quality=quality,
                task_identity=cases[scenario_id]["expected_route"] == "task",
            )
        _emit_round(
            collector,
            production_collector,
            profile_index=profile_index,
            profile_id=profile_id,
            scenario_id="silence-no-valid-speech",
            sample_index=successful_rounds,
            temperature=temperature,
            classification=L0RoundClassification.FAILURE,
            offsets=((L0Milestone.MISSED_EOT, 1_500),),
        )
        _emit_round(
            collector,
            production_collector,
            profile_index=profile_index,
            profile_id=profile_id,
            scenario_id="provider-failure-zh",
            sample_index=successful_rounds + 1,
            temperature=temperature,
            classification=L0RoundClassification.FALLBACK,
            offsets=((L0Milestone.FALLBACK, 900),),
        )
        _emit_round(
            collector,
            production_collector,
            profile_index=profile_index,
            profile_id=profile_id,
            scenario_id="playout-barge-in-zh",
            sample_index=successful_rounds + 2,
            temperature=temperature,
            classification=L0RoundClassification.CANCELLED,
            offsets=(
                (L0Milestone.BARGE_IN, 3_000),
                (L0Milestone.FENCE_CANCEL_COMPLETION, 3_080),
            ),
        )
    report = build_l0_measurement_report(
        collector,
        source_head=source_head,
        environment_ref=INJECTED_ENVIRONMENT_REF,
        corpus_sha256=digest,
        scenario_routes={
            case_id: str(case["expected_route"])
            for case_id, case in cases.items()
        },
        no_tool_scenarios=frozenset(
            case_id
            for case_id, case in cases.items()
            if case["category"] == "short_no_tool"
        ),
    )
    stats = production_collector.stats()
    report["production_collector"] = {
        "accepted_observations": stats.accepted_observations,
        "duplicate_observations": stats.duplicate_observations,
        "rejected_observations": stats.rejected_observations,
        "sink_failures": stats.sink_failures,
    }
    report["corpus_case_coverage"] = sorted(
        {str(round_report["scenario_id"]) for round_report in report["rounds"]}
    )
    return report


def _nearest_rank(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(quantile * len(ordered)) - 1)], 3)


_PROVIDER_CONFIGURATION_FIELDS = (
    "LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED",
    "LIVE_VOICE_SPEECH_PROVIDER",
    "LIVE_VOICE_SPEECH_API_BASE",
    "LIVE_VOICE_SPEECH_STT_MODEL",
    "LIVE_VOICE_SPEECH_TTS_MODEL",
    "LIVE_VOICE_SPEECH_TTS_VOICE",
)


def _provider_configuration_sha256(
    environment: Mapping[str, str] | None = None,
) -> str:
    """Fingerprint effective non-secret Provider/model selection inputs."""

    source = os.environ if environment is None else environment
    normalized = {
        name: str(source.get(name) or "").strip()
        for name in _PROVIDER_CONFIGURATION_FIELDS
    }
    normalized["LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED"] = normalized[
        "LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED"
    ].lower()
    normalized["LIVE_VOICE_SPEECH_PROVIDER"] = normalized[
        "LIVE_VOICE_SPEECH_PROVIDER"
    ].lower()
    normalized["LIVE_VOICE_SPEECH_API_BASE"] = normalized[
        "LIVE_VOICE_SPEECH_API_BASE"
    ].rstrip("/")
    serialized = json.dumps(
        normalized,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


async def build_provider_component_baseline(
    *,
    corpus_path: Path,
    successful_rounds: int,
    max_attempts: int,
    source_head: str,
) -> tuple[dict[str, object], bool]:
    if successful_rounds < 20:
        raise ValueError("provider profiles require at least 20 successful rounds")
    if max_attempts < successful_rounds:
        raise ValueError("provider max attempts cannot be below the success target")
    from jiuwenswarm.server.live_voice.batch_speech import (
        ProviderRecognitionRequest,
        ProviderSynthesisRequest,
        create_environment_batch_speech_provider,
    )

    manifest, digest = load_l0_corpus_manifest(corpus_path)
    configuration_sha256 = _provider_configuration_sha256()
    fixed_case = next(
        case for case in manifest["cases"] if case["case_id"] == "short-no-tool-zh"
    )
    stimulus = str(fixed_case["stimulus_text"])
    stimulus_digest = hashlib.sha256(stimulus.encode("utf-8")).hexdigest()
    successes: list[dict[str, float]] = []
    failures = 0
    attempts = 0
    while len(successes) < successful_rounds and attempts < max_attempts:
        attempt = attempts
        attempts += 1
        provider = create_environment_batch_speech_provider()
        try:
            capability = provider.capability()
            if not (
                capability.available
                and capability.recognition_batch
                and capability.synthesis_batch
            ):
                raise RuntimeError("configured batch provider is unavailable")
            started = time.monotonic()
            synthesized = await provider.synthesize(
                ProviderSynthesisRequest(
                    f"l0-provider-tts-unknown-{attempt}",
                    stimulus,
                    "zh-CN",
                    None,
                    24_000,
                )
            )
            synthesized_at = time.monotonic()
            recognized = await provider.recognize(
                ProviderRecognitionRequest(
                    f"l0-provider-stt-unknown-{attempt}",
                    synthesized.audio_wav,
                    "zh-CN",
                )
            )
            completed_at = time.monotonic()
            if not isinstance(recognized.text, str) or not recognized.text.strip():
                raise RuntimeError("configured provider returned no final recognition")
            successes.append(
                {
                    "batch_synthesis_complete_ms": (synthesized_at - started)
                    * 1000.0,
                    "speech_end_to_stt_final_ms": (
                        completed_at - synthesized_at
                    )
                    * 1000.0,
                    "digital_loopback_round_ms": (completed_at - started)
                    * 1000.0,
                }
            )
            del recognized, synthesized
        except Exception:
            failures += 1
    complete = len(successes) >= successful_rounds
    percentiles = {}
    for metric_name in (
        "batch_synthesis_complete_ms",
        "speech_end_to_stt_final_ms",
        "digital_loopback_round_ms",
    ):
        values = [sample[metric_name] for sample in successes]
        percentiles[metric_name] = {
            "sample_count": len(values),
            "p50_ms": _nearest_rank(values, 0.50),
            "p95_ms": _nearest_rank(values, 0.95),
        }
    groups = [
        {
            "profile_id": "real-provider-digital-loopback-unknown",
            "temperature": L0RoundTemperature.UNKNOWN.value,
            "provider_lifecycle": "uncontrolled",
            "success_target": successful_rounds,
            "attempt_count": attempts,
            "success_count": len(successes),
            "failure_count": failures,
            "fallback_count": 0,
            "complete": complete,
            "percentiles": percentiles,
        }
    ]
    report = {
        "schema_version": PROVIDER_REPORT_VERSION,
        "source_head": source_head,
        "environment_ref": PROVIDER_ENVIRONMENT_REF,
        "corpus_sha256": digest,
        "stimulus_sha256": stimulus_digest,
        "configuration_sha256": configuration_sha256,
        "configuration_fields": list(_PROVIDER_CONFIGURATION_FIELDS),
        "profiles": groups,
        "audio_retained": False,
        "recognized_text_retained": False,
        "non_claims": [
            "batch synthesis completion is not streaming Provider first audio",
            "digital loopback is not a physical microphone or speaker path",
            "this component probe is not complete browser Gateway Agent Runtime latency",
            "the Provider and model lifecycle is uncontrolled, so these samples are not cold or warm evidence",
        ],
    }
    canonical_json_bytes(report)
    return report, complete


def _source_head_from_input_metadata(inputs: Sequence[Path]) -> str:
    if not inputs:
        raise RuntimeError("aggregation requires at least one input")
    source_heads: set[str] = set()
    for directory in {path.resolve().parent for path in inputs}:
        metadata_path = directory / _RUN_SOURCE_METADATA_NAME
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "each input directory requires source-bound browser-session metadata"
            ) from error
        if type(metadata) is not dict:
            raise RuntimeError("input source metadata is invalid")
        source_head = metadata.get("source_head")
        evidence_directory = metadata.get("evidence_directory")
        if (
            type(source_head) is not str
            or not re.fullmatch(r"[0-9a-f]{40}", source_head)
            or type(evidence_directory) is not str
            or Path(evidence_directory).resolve() != directory
        ):
            raise RuntimeError("input source metadata is invalid")
        source_heads.add(source_head)
    if len(source_heads) != 1:
        raise RuntimeError("input runs do not share one exact source HEAD")
    return next(iter(source_heads))


def aggregate_jsonl(
    *,
    inputs: Sequence[Path],
    corpus_path: Path,
    source_head: str,
    environment_ref: str,
    accepted_round_keys: frozenset[tuple[str, str, int]] | None = None,
) -> dict[str, object]:
    input_source_head = _source_head_from_input_metadata(inputs)
    if input_source_head != source_head:
        raise RuntimeError("input run source HEAD differs from the requested source")
    manifest, digest = load_l0_corpus_manifest(corpus_path)
    profiles = {
        str(profile["profile_id"]): profile for profile in manifest["profiles"]
    }
    cases = {str(case["case_id"]): case for case in manifest["cases"]}
    all_records = load_l0_jsonl(inputs)
    all_declarations = declarations_from_records(all_records)
    for declaration in all_declarations:
        profile = profiles.get(declaration.profile_id)
        case = cases.get(declaration.scenario_id)
        if profile is None or case is None:
            raise RuntimeError("input record labels are outside the fixed corpus")
        if (
            declaration.evidence_source.value != profile["evidence_source"]
            or declaration.temperature.value != profile["temperature_policy"]
        ):
            raise RuntimeError("input record profile labels conflict with the corpus")
    collector = L0MeasurementCollector()
    declarations = declarations_from_records(all_records)
    for declaration in declarations:
        if not collector.register_round(declaration):
            raise RuntimeError("input declaration was unexpectedly duplicated")
    for record in all_records:
        if not collector.consume(record):
            raise RuntimeError("input record failed exact run isolation")
    return build_l0_measurement_report(
        collector,
        source_head=source_head,
        environment_ref=environment_ref,
        corpus_sha256=digest,
        scenario_routes={
            case_id: str(case["expected_route"])
            for case_id, case in cases.items()
        },
        no_tool_scenarios=frozenset(
            case_id
            for case_id, case in cases.items()
            if case["category"] == "short_no_tool"
        ),
        accepted_round_keys=accepted_round_keys,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run or aggregate sanitized Live Voice L0 measurement evidence."
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--source-head", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-corpus")
    validate.add_argument("--print-digest", action="store_true")

    injected = subparsers.add_parser("injected-baseline")
    injected.add_argument("--successful-rounds", type=int, default=20)
    injected.add_argument("--output", type=Path, required=True)

    provider = subparsers.add_parser("provider-baseline")
    provider.add_argument("--successful-rounds", type=int, default=20)
    provider.add_argument("--max-attempts", type=int, default=25)
    provider.add_argument("--output", type=Path, required=True)

    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("--input", type=Path, action="append", required=True)
    aggregate.add_argument("--environment-ref", required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate-corpus":
        _manifest, digest = load_l0_corpus_manifest(args.corpus)
        if args.print_digest:
            print(digest)
        return 0
    source_head = clean_source_head(args.source_head)
    if args.command == "injected-baseline":
        report = build_injected_baseline(
            corpus_path=args.corpus,
            successful_rounds=args.successful_rounds,
            source_head=source_head,
        )
        _write_json(args.output, report)
        return 0
    if args.command == "provider-baseline":
        report, complete = asyncio.run(
            build_provider_component_baseline(
                corpus_path=args.corpus,
                successful_rounds=args.successful_rounds,
                max_attempts=args.max_attempts,
                source_head=source_head,
            )
        )
        _write_json(args.output, report)
        return 0 if complete else 2
    if args.command == "aggregate":
        report = aggregate_jsonl(
            inputs=args.input,
            corpus_path=args.corpus,
            source_head=source_head,
            environment_ref=args.environment_ref,
        )
        _write_json(args.output, report)
        return 0
    raise RuntimeError("unsupported L0 command")


if __name__ == "__main__":
    raise SystemExit(main())
