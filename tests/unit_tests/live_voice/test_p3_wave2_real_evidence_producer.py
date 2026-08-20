# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectStreamObservation,
)
from scripts.live_voice.p3_wave2_real_evidence_producer import (
    ClosedEvidenceFailure,
    ObservationCollector,
    ScenarioSummary,
    build_evidence_document,
    emit_sanitized_result,
    main,
    sanitized_aggregate_line,
    write_private_evidence,
)
from scripts.live_voice.p3_wave2_real_evidence_validator import (
    validate_evidence_bytes,
)


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64


def _observation(
    *,
    sequence: int,
    event_kind: str,
    file_tool_kind: str = "write",
    result_status: str = "not_applicable",
    call_id_digest: str = SHA_B,
    task_label: str = "A1",
    stream_kind: str = "initial",
) -> DirectStreamObservation:
    return DirectStreamObservation(
        task_ref=f"task-{task_label}",
        attempt_ref=f"attempt-{task_label}",
        run_ref=f"run-{task_label}-{stream_kind}",
        sequence=sequence,
        stream_kind=stream_kind,
        event_kind=event_kind,
        file_tool_kind=file_tool_kind,
        tool_name_digest=SHA_A,
        call_id_digest=call_id_digest,
        result_status=result_status,
        observed_at="2026-08-20T10:00:00Z",
    )


def _complete_collector() -> ObservationCollector:
    collector = ObservationCollector(capacity=8)
    for task_label, stream_kind in (
        ("A1", "initial"),
        ("A2", "initial"),
        ("A2", "adjustment"),
        ("B1", "initial"),
    ):
        collector(
            _observation(
                sequence=1,
                event_kind="tool_call",
                task_label=task_label,
                stream_kind=stream_kind,
            )
        )
        collector(
            _observation(
                sequence=2,
                event_kind="tool_result",
                result_status="success",
                task_label=task_label,
                stream_kind=stream_kind,
            )
        )
    return collector


def _summary(output: Path) -> ScenarioSummary:
    return ScenarioSummary(
        run_id="wave2-run-1",
        source_sha256=SHA_C,
        private_output_basename=output.name,
        data_dir_basename="wave2-private-data",
        database_basename="p3-wave2.sqlite3",
        project_basenames=("project-a", "project-b"),
        task_refs=("task-A1", "task-A2", "task-B1"),
        attempt_refs=("attempt-A1", "attempt-A2", "attempt-B1"),
        profile_sha256=SHA_A,
        requirements_sha256=SHA_B,
        production_factory_used=True,
        production_registration_used=True,
        profile_persisted=True,
        requirements_persisted=True,
        two_projects_concurrent=True,
        a2_busy_queued=True,
        a2_zero_pre_release_effect=True,
        same_attempt_dequeued=True,
        adjustment_applied=True,
        cancel_a1_exact=True,
        cancel_b1_exact=True,
        reopen_matched=True,
        cleanup_complete=True,
        source_untouched=True,
        real_agent_observed=True,
        real_tool_observed=True,
    )


def test_collector_builds_valid_closed_evidence_and_private_writer_is_quiet(
    tmp_path: Path,
) -> None:
    private_dir = tmp_path / "PRIVATE_PATH_SENTINEL"
    private_dir.mkdir()
    output = private_dir / "raw-evidence.json"
    collector = _complete_collector()

    document = build_evidence_document(_summary(output), collector)
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    aggregate = validate_evidence_bytes(encoded)
    write_private_evidence(output, document)
    line = sanitized_aggregate_line(aggregate)

    assert output.read_bytes() == encoded
    assert aggregate == {
        "ok": True,
        "observation_count": 8,
        "paired_file_tool_count": 4,
        "write_edit_pair_count": 4,
    }
    assert line.endswith("\n")
    assert line.count("\n") == 1
    assert "PRIVATE_PATH_SENTINEL" not in line
    assert str(output) not in line
    assert len(encoded) <= 64 * 1024


@pytest.mark.parametrize(
    ("observations", "capacity", "reason"),
    [
        (
            (
                _observation(sequence=1, event_kind="tool_call"),
                _observation(
                    sequence=2,
                    event_kind="tool_result",
                    result_status="success",
                ),
            ),
            1,
            "EVIDENCE_DROPPED_OBSERVATION",
        ),
        (
            (_observation(sequence=2, event_kind="tool_call"),),
            8,
            "EVIDENCE_SEQUENCE_GAP",
        ),
        (
            (
                _observation(
                    sequence=1,
                    event_kind="tool_call",
                    file_tool_kind="unknown",
                ),
            ),
            8,
            "EVIDENCE_UNKNOWN_OBSERVATION",
        ),
        (
            (_observation(sequence=1, event_kind="tool_call"),),
            8,
            "EVIDENCE_TOOL_PAIRING_INVALID",
        ),
    ],
)
def test_collector_fails_closed_for_loss_gap_unknown_and_unpaired(
    tmp_path: Path,
    observations: tuple[DirectStreamObservation, ...],
    capacity: int,
    reason: str,
) -> None:
    output = tmp_path / "raw.json"
    collector = ObservationCollector(capacity=capacity)
    for observation in observations:
        collector(observation)

    with pytest.raises(ClosedEvidenceFailure) as raised:
        build_evidence_document(_summary(output), collector)

    assert raised.value.reason == reason
    assert raised.value.args == (reason,)


def test_private_writer_rejects_relative_existing_and_oversized_output(
    tmp_path: Path,
) -> None:
    collector = _complete_collector()
    output = tmp_path / "raw.json"
    document = build_evidence_document(_summary(output), collector)

    with pytest.raises(ClosedEvidenceFailure) as relative:
        write_private_evidence(Path("relative.json"), document)
    assert relative.value.reason == "PRIVATE_OUTPUT_NOT_ABSOLUTE"

    output.write_text("existing", encoding="utf-8")
    with pytest.raises(ClosedEvidenceFailure) as existing:
        write_private_evidence(output, document)
    assert existing.value.reason == "PRIVATE_OUTPUT_EXISTS"

    oversized = dict(document)
    oversized["observations"] = document["observations"] * 512
    with pytest.raises(ClosedEvidenceFailure) as too_large:
        write_private_evidence(tmp_path / "oversized.json", oversized)
    assert too_large.value.reason == "EVIDENCE_TOO_LARGE"


def test_collector_merges_adapter_health_and_fails_closed(tmp_path: Path) -> None:
    collector = _complete_collector()
    collector.record_observer_failures(2)

    with pytest.raises(ClosedEvidenceFailure) as raised:
        build_evidence_document(_summary(tmp_path / "raw.json"), collector)

    assert raised.value.reason == "EVIDENCE_OBSERVER_FAILURE"


def test_emit_sanitized_result_writes_exactly_one_closed_line(capsys) -> None:
    emit_sanitized_result(
        {
            "ok": True,
            "observation_count": 2,
            "paired_file_tool_count": 1,
            "write_edit_pair_count": 1,
        }
    )
    assert capsys.readouterr() == (
        '{"observation_count":2,"ok":true,"paired_file_tool_count":1,'
        '"write_edit_pair_count":1}\n',
        "",
    )

    emit_sanitized_result(None, ClosedEvidenceFailure("REAL_SCENARIO_FAILED"))
    assert capsys.readouterr() == (
        '{"ok":false,"reason":"REAL_SCENARIO_FAILED"}\n',
        "",
    )


def test_cli_uses_fixed_private_production_path_and_accepts_no_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    private_root = tmp_path / "private-root"
    (private_root / "config").mkdir(parents=True)
    (private_root / "config" / "config.yaml").write_text(
        "PRIVATE_CONFIG_SENTINEL", encoding="utf-8"
    )
    (private_root / ".env").write_text("PRIVATE_ENV_SENTINEL", encoding="utf-8")
    output = private_root / "raw-evidence.json"
    calls: list[tuple[Path, Path]] = []

    async def fixed_production(private: Path, raw_output: Path):
        calls.append((private, raw_output))
        return {
            "ok": True,
            "observation_count": 4,
            "paired_file_tool_count": 2,
            "write_edit_pair_count": 1,
        }

    monkeypatch.setattr(
        "scripts.live_voice.p3_wave2_real_evidence_producer._run_production_cli",
        fixed_production,
    )

    exit_code = main(
        ["--private-root", str(private_root), "--output", str(output)]
    )

    assert exit_code == 0
    assert calls == [(private_root.resolve(), output.resolve())]
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    assert captured.err == ""
    assert "PRIVATE_" not in captured.out
    assert str(private_root) not in captured.out


def test_fresh_import_does_not_import_jiuwenswarm_and_invalid_cli_is_closed(
    tmp_path: Path,
) -> None:
    script = Path("scripts/live_voice/p3_wave2_real_evidence_producer.py").resolve()
    imported = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import scripts.live_voice."
                "p3_wave2_real_evidence_producer; "
                "print(any(name == 'jiuwenswarm' or "
                "name.startswith('jiuwenswarm.') for name in sys.modules))"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert imported.returncode == 0
    assert imported.stdout == "False\n"
    assert imported.stderr == ""

    private_root = tmp_path / "private-bootstrap"
    (private_root / "config").mkdir(parents=True)
    (private_root / "config" / "config.yaml").write_text("{}", encoding="utf-8")
    (private_root / ".env").write_text(
        "JIUWENSWARM_DATA_DIR=C:/PRIVATE_HOSTILE_ROOT\n"
        "JIUWENSWARM_HOME=C:/PRIVATE_HOSTILE_HOME\n",
        encoding="utf-8",
    )
    bootstrap = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os, pathlib; from scripts.live_voice import "
                "p3_wave2_real_evidence_producer as p; "
                f"root=pathlib.Path({str(private_root.resolve())!r}); "
                "p._load_private_configuration(root); "
                "print(os.environ['JIUWENSWARM_DATA_DIR'] == str(root) and "
                "os.environ['JIUWENSWARM_HOME'] == str(root) and "
                "os.environ['JIUWENSWARM_CONFIG_DIR'] == str(root / 'config'))"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bootstrap.returncode == 0
    assert bootstrap.stdout == "True\n"
    assert bootstrap.stderr == ""

    invalid = subprocess.run(
        [
            sys.executable,
            str(script),
            "--private-root",
            "PRIVATE_RELATIVE_ROOT_SENTINEL",
            "--output",
            "PRIVATE_RELATIVE_OUTPUT_SENTINEL",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid.returncode == 2
    assert invalid.stdout == '{"ok":false,"reason":"PRIVATE_ROOT_NOT_ABSOLUTE"}\n'
    assert invalid.stderr == ""
    assert "SENTINEL" not in invalid.stdout
