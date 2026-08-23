from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.live_voice import l0_measurement_baseline
from scripts.live_voice.l0_measurement_baseline import (
    aggregate_jsonl,
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


def _record() -> dict[str, object]:
    return create_l0_milestone(
        milestone=L0Milestone.PROVIDER_EOT,
        binding=L0RoundBinding(
            correlation_id="correlation-1",
            session_id="session-1",
            interaction_id="interaction-1",
            activation_generation=1,
        ),
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=0,
        temperature=L0RoundTemperature.WARM,
        evidence_source=L0EvidenceSource.PHYSICAL,
        observed_at="2026-08-23T00:00:00.000Z",
        monotonic_ms=100.0,
    ).to_dict()


def _write_record(tmp_path: Path, record: dict[str, object]) -> Path:
    path = tmp_path / "records.jsonl"
    path.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def test_aggregate_accepts_only_profile_scenario_and_source_from_fixed_corpus(
    tmp_path: Path,
) -> None:
    report = aggregate_jsonl(
        inputs=(_write_record(tmp_path, _record()),),
        corpus_path=CORPUS,
        source_head=SOURCE_HEAD,
        environment_ref="environment-physical-test",
    )
    assert report["rounds"][0]["expected_route"] == "dialogue"

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
                environment_ref="environment-physical-test",
            )


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
