from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.live_voice import l0_measurement_baseline
from scripts.live_voice.l0_measurement_baseline import (
    _provider_configuration_sha256,
    aggregate_jsonl,
    build_provider_component_baseline,
    clean_source_head,
)
from jiuwenswarm.server.live_voice.latency_measurement import (
    L0EvidenceSource,
    L0Milestone,
    L0RoundBinding,
    L0RoundTemperature,
    create_l0_milestone,
)


SOURCE_HEAD = "c31e85ade1a69e934d05bfb9c277568a1238663c"
CORPUS = Path("scripts/live_voice/l0_fixed_corpus.json")
ENVIRONMENT_REF = "environment-physical-test"
CONFIGURATION_SHA256 = "b" * 64


def test_direct_cli_imports_the_current_repository_implementation() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/live_voice/l0_measurement_baseline.py",
            "validate-corpus",
            "--print-digest",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "888fdcba848037c1feba6c8c31a15641d721507b57e0985ba2d14446e7d4b563"
    )


def _record(sample_index: int = 0) -> dict[str, object]:
    return create_l0_milestone(
        milestone=L0Milestone.PROVIDER_EOT,
        binding=L0RoundBinding(
            correlation_id=f"correlation-{sample_index + 1}",
            session_id="session-1",
            interaction_id=f"interaction-{sample_index + 1}",
            activation_generation=1,
        ),
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=sample_index,
        temperature=L0RoundTemperature.WARM,
        evidence_source=L0EvidenceSource.PHYSICAL,
        observed_at="2026-08-23T00:00:00.000Z",
        monotonic_ms=100.0,
    ).to_dict()


def _write_record(tmp_path: Path, record: dict[str, object]) -> Path:
    _write_source_metadata(tmp_path)
    path = tmp_path / "records.jsonl"
    path.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def _write_records(tmp_path: Path, records: list[dict[str, object]]) -> Path:
    _write_source_metadata(tmp_path)
    path = tmp_path / "records.jsonl"
    path.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def _write_source_metadata(
    tmp_path: Path,
    *,
    source_head: str = SOURCE_HEAD,
    environment_ref: str = ENVIRONMENT_REF,
    configuration_sha256: str = CONFIGURATION_SHA256,
) -> None:
    (tmp_path / "browser-session.json").write_text(
        json.dumps(
            {
                "schema_version": "live-voice.l0-browser-session.v6",
                "source_head": source_head,
                "evidence_directory": str(tmp_path.resolve()),
                "environment_ref": environment_ref,
                "configuration_sha256": configuration_sha256,
                "physical_evidence": "pending-user-run",
            }
        ),
        encoding="utf-8",
    )


def test_aggregate_accepts_only_profile_scenario_and_source_from_fixed_corpus(
    tmp_path: Path,
) -> None:
    report = aggregate_jsonl(
        inputs=(_write_record(tmp_path, _record()),),
        corpus_path=CORPUS,
        source_head=SOURCE_HEAD,
        environment_ref=ENVIRONMENT_REF,
        accepted_round_keys=frozenset(
            {("physical-formal-web-warm", "short-no-tool-zh", 0)}
        ),
    )
    assert report["rounds"][0]["expected_route"] == "dialogue"

    _write_source_metadata(tmp_path, source_head="0" * 40)
    with pytest.raises(RuntimeError, match="differs from the requested"):
        aggregate_jsonl(
            inputs=(tmp_path / "records.jsonl",),
            corpus_path=CORPUS,
            source_head=SOURCE_HEAD,
            environment_ref=ENVIRONMENT_REF,
            accepted_round_keys=frozenset(
                {("physical-formal-web-warm", "short-no-tool-zh", 0)}
            ),
        )
    _write_source_metadata(tmp_path)

    for field_name, value, message in (
        ("profile_id", "foreign-profile", "outside the fixed corpus"),
        ("scenario_id", "foreign-scenario", "outside the fixed corpus"),
        ("evidence_source", "digital_loopback", "conflict with the corpus"),
    ):
        record = _record()
        record[field_name] = value
        with pytest.raises(RuntimeError, match=message):
            aggregate_jsonl(
                inputs=(_write_record(tmp_path, record),),
                corpus_path=CORPUS,
                source_head=SOURCE_HEAD,
                environment_ref=ENVIRONMENT_REF,
                accepted_round_keys=frozenset(
                    {("physical-formal-web-warm", "short-no-tool-zh", 0)}
                ),
            )


def test_physical_aggregate_requires_acceptance_and_exact_session_provenance(
    tmp_path: Path,
) -> None:
    path = _write_record(tmp_path, _record())

    with pytest.raises(RuntimeError, match="verified operator acceptance"):
        aggregate_jsonl(
            inputs=(path,),
            corpus_path=CORPUS,
            source_head=SOURCE_HEAD,
            environment_ref=ENVIRONMENT_REF,
        )

    accepted_keys = frozenset(
        {("physical-formal-web-warm", "short-no-tool-zh", 0)}
    )
    report = aggregate_jsonl(
        inputs=(path,),
        corpus_path=CORPUS,
        source_head=SOURCE_HEAD,
        environment_ref=ENVIRONMENT_REF,
        accepted_round_keys=accepted_keys,
    )
    assert report["physical_configuration_sha256"] == CONFIGURATION_SHA256
    assert report["physical_profile_success_targets"] == {
        "physical-formal-web-warm": 20
    }
    assert report["physical_capture_complete"] is False
    assert report["physical_profile_complete"] is False

    with pytest.raises(RuntimeError, match="requested environment"):
        aggregate_jsonl(
            inputs=(path,),
            corpus_path=CORPUS,
            source_head=SOURCE_HEAD,
            environment_ref="environment-other",
            accepted_round_keys=accepted_keys,
        )

    other = tmp_path / "other"
    other.mkdir()
    other_path = _write_record(other, _record(1))
    _write_source_metadata(other, configuration_sha256="c" * 64)
    with pytest.raises(RuntimeError, match="environment and configuration"):
        aggregate_jsonl(
            inputs=(path, other_path),
            corpus_path=CORPUS,
            source_head=SOURCE_HEAD,
            environment_ref=ENVIRONMENT_REF,
            accepted_round_keys=accepted_keys,
        )

    (tmp_path / "browser-session.json").write_text(
        json.dumps(
            {
                "source_head": SOURCE_HEAD,
                "evidence_directory": str(tmp_path.resolve()),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="metadata is invalid"):
        aggregate_jsonl(
            inputs=(path,),
            corpus_path=CORPUS,
            source_head=SOURCE_HEAD,
            environment_ref=ENVIRONMENT_REF,
            accepted_round_keys=accepted_keys,
        )


def test_aggregate_percentiles_and_quality_use_only_operator_accepted_rounds(
    tmp_path: Path,
) -> None:
    accepted = _record()
    rejected = _record(1)
    path = _write_records(tmp_path, [accepted, rejected])

    report = aggregate_jsonl(
        inputs=(path,),
        corpus_path=CORPUS,
        source_head=SOURCE_HEAD,
        environment_ref=ENVIRONMENT_REF,
        accepted_round_keys=frozenset(
            {("physical-formal-web-warm", "short-no-tool-zh", 0)}
        ),
    )

    assert [round_report["sample_index"] for round_report in report["rounds"]] == [0, 1]
    assert [round_report["operator_accepted"] for round_report in report["rounds"]] == [
        True,
        False,
    ]
    assert report["profiles"][0]["success_eligible_count"] == 0


def test_clean_source_identity_rejects_dirty_or_requested_head_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(l0_measurement_baseline, "_source_head", lambda: SOURCE_HEAD)
    monkeypatch.setattr(
        l0_measurement_baseline.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=" M changed.py\n"),
    )
    with pytest.raises(RuntimeError, match="clean worktree"):
        clean_source_head()

    monkeypatch.setattr(
        l0_measurement_baseline.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=""),
    )
    with pytest.raises(RuntimeError, match="differs"):
        clean_source_head("0" * 40)
    assert clean_source_head(SOURCE_HEAD) == SOURCE_HEAD

    monkeypatch.setattr(
        l0_measurement_baseline.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout="?? .codex_tmp/local-artifact/output.bin\n"
        ),
    )
    assert clean_source_head(SOURCE_HEAD) == SOURCE_HEAD


@pytest.mark.asyncio
async def test_provider_component_labels_uncontrolled_lifecycle_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jiuwenswarm.server.live_voice import batch_speech

    created = 0

    class _Provider:
        def capability(self) -> object:
            return SimpleNamespace(
                available=True,
                recognition_batch=True,
                synthesis_batch=True,
            )

        async def synthesize(self, _request: object) -> object:
            return SimpleNamespace(audio_wav=b"content-free-test-wav")

        async def recognize(self, _request: object) -> object:
            return SimpleNamespace(text="recognized")

    def factory() -> _Provider:
        nonlocal created
        created += 1
        return _Provider()

    provider_environment = {
        "LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED": "1",
        "LIVE_VOICE_SPEECH_PROVIDER": "openai-compatible",
        "LIVE_VOICE_SPEECH_API_BASE": "https://speech.example.test/v1",
        "LIVE_VOICE_SPEECH_STT_MODEL": "stt-model-a",
        "LIVE_VOICE_SPEECH_TTS_MODEL": "tts-model-a",
        "LIVE_VOICE_SPEECH_TTS_VOICE": "voice-a",
    }
    for name, value in provider_environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(batch_speech, "create_environment_batch_speech_provider", factory)
    report, complete = await build_provider_component_baseline(
        corpus_path=CORPUS,
        successful_rounds=20,
        max_attempts=20,
        source_head=SOURCE_HEAD,
    )

    assert complete is True
    assert created == 20
    assert len(report["profiles"]) == 1
    assert report["profiles"][0]["profile_id"] == "real-provider-digital-loopback-unknown"
    assert report["profiles"][0]["temperature"] == "unknown"
    assert report["profiles"][0]["provider_lifecycle"] == "uncontrolled"
    assert report["configuration_sha256"] == _provider_configuration_sha256(
        provider_environment
    )
    assert len(report["configuration_sha256"]) == 64
    changed_environment = dict(provider_environment)
    changed_environment["LIVE_VOICE_SPEECH_STT_MODEL"] = "stt-model-b"
    assert _provider_configuration_sha256(
        changed_environment
    ) != report["configuration_sha256"]
