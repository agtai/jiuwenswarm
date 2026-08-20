# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from scripts.live_voice import p3_wave2_real_evidence_producer as producer
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
INVALID_CALL_SHA = "sha256:" + hashlib.sha256(
    b"live-voice.invalid-tool-call-id"
).hexdigest()
INVALID_TOOL_SHA = "sha256:" + hashlib.sha256(
    b"live-voice.invalid-tool-name"
).hexdigest()


def _make_private_acl(root: Path) -> None:
    if os.name != "nt":
        for path in (root, *root.rglob("*")):
            path.chmod(0o700 if path.is_dir() else 0o600)
        return
    current_sid = producer._windows_acl(root)["user"]
    for path in (root, *root.rglob("*")):
        inheritance = "(OI)(CI)F" if path.is_dir() else "F"
        secured = subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{current_sid}:{inheritance}",
                f"*S-1-5-18:{inheritance}",
                f"*S-1-5-32-544:{inheritance}",
            ],
            check=False,
            capture_output=True,
        )
        assert secured.returncode == 0


def _private_cli_paths(tmp_path: Path, name: str) -> tuple[Path, Path]:
    private_root = tmp_path / name
    (private_root / "config").mkdir(parents=True)
    (private_root / "config" / "config.yaml").write_text("{}", encoding="utf-8")
    (private_root / ".env").write_text("", encoding="utf-8")
    _make_private_acl(private_root)
    return private_root, private_root / "raw-evidence.json"


def _closed_failure_worker_command(
    arguments: list[str],
    remaining: float,
    *,
    reason: object,
) -> list[str]:
    failure = (
        "async def fail(*_args, **_kwargs):\n"
        f"    raise p.ClosedEvidenceFailure({reason!r})\n"
    )
    bootstrap = (
        "import sys; from scripts.live_voice import "
        "p3_wave2_real_evidence_producer as p; "
        f"exec({failure!r}); p._run_production_cli=fail; "
        "raise SystemExit(p._worker_entry(sys.argv[1:5],float(sys.argv[5])))"
    )
    return [sys.executable, "-c", bootstrap, *arguments, f"{remaining:.9f}"]


def _runtime_failure_worker_command(
    arguments: list[str],
    remaining: float,
    *,
    message: str,
) -> list[str]:
    failure = (
        f"async def fail(*_args, **_kwargs):\n    raise RuntimeError({message!r})\n"
    )
    bootstrap = (
        "import sys; from scripts.live_voice import "
        "p3_wave2_real_evidence_producer as p; "
        f"exec({failure!r}); p._run_production_cli=fail; "
        "raise SystemExit(p._worker_entry(sys.argv[1:5],float(sys.argv[5])))"
    )
    return [sys.executable, "-c", bootstrap, *arguments, f"{remaining:.9f}"]


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
    assert output.read_text(encoding="utf-8") == "existing"

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


@pytest.mark.parametrize(
    ("identity_kind", "invalid_sides"),
    [
        ("call_id_digest", (0,)),
        ("call_id_digest", (1,)),
        ("call_id_digest", (0, 1)),
        ("tool_name_digest", (0,)),
        ("tool_name_digest", (1,)),
        ("tool_name_digest", (0, 1)),
    ],
)
def test_invalid_identity_never_earns_physical_tool_credit(
    identity_kind: str,
    invalid_sides: tuple[int, ...],
) -> None:
    observations = [
        _observation(sequence=1, event_kind="tool_call"),
        _observation(
            sequence=2,
            event_kind="tool_result",
            result_status="success",
        ),
    ]
    invalid_digest = (
        INVALID_CALL_SHA
        if identity_kind == "call_id_digest"
        else INVALID_TOOL_SHA
    )
    collector = ObservationCollector(capacity=2)
    for index, observation in enumerate(observations):
        values = asdict(observation)
        if index in invalid_sides:
            values[identity_kind] = invalid_digest
        collector(DirectStreamObservation(**values))

    assert producer._successful_pair(collector, "task-A1", stream_kind="initial") is False


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
    _make_private_acl(private_root)
    output = private_root / "raw-evidence.json"
    calls: list[tuple[list[str], Path, Path, float]] = []

    def fixed_production(
        arguments: list[str],
        private: Path,
        raw_output: Path,
        *,
        deadline: float,
    ):
        calls.append((arguments, private, raw_output, deadline))
        return {
            "ok": True,
            "observation_count": 4,
            "paired_file_tool_count": 2,
            "write_edit_pair_count": 1,
        }

    monkeypatch.setattr(
        "scripts.live_voice.p3_wave2_real_evidence_producer."
        "_supervise_production_worker",
        fixed_production,
    )

    exit_code = main(
        ["--private-root", str(private_root), "--output", str(output)]
    )

    assert exit_code == 0
    assert len(calls) == 1
    arguments, private, raw_output, deadline = calls[0]
    assert arguments == [
        "--private-root",
        str(private_root),
        "--output",
        str(output),
    ]
    assert (private, raw_output) == (private_root, output)
    assert deadline > time.monotonic()
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    assert captured.err == ""
    assert "PRIVATE_" not in captured.out
    assert str(private_root) not in captured.out


def test_registered_scenario_database_is_accepted_by_product_store_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jiuwenswarm.common import utils as common_utils
    from jiuwenswarm.server.live_voice.p3_authenticated_composition import (
        _resolve_database_path,
    )
    from jiuwenswarm.server.runtime.session import project_store, session_metadata

    private_root = tmp_path / "private-database-root"
    private_root.mkdir()
    _make_private_acl(private_root)
    projects: list[SimpleNamespace] = []

    def initialize_project(path: Path, *, title: str) -> None:
        assert title in {"Wave 2 Project A", "Wave 2 Project B"}
        path.mkdir()

    def create_project(name: str, path: str, *, work_mode: str):
        assert work_mode == "code"
        project = SimpleNamespace(project_id=f"project-{len(projects)}", name=name)
        projects.append(project)
        assert Path(path).parent == private_root / "projects"
        return project, False

    monkeypatch.setattr(producer, "_initialize_private_project", initialize_project)
    monkeypatch.setattr(project_store, "create_or_restore_project", create_project)
    monkeypatch.setattr(session_metadata, "init_session_metadata", lambda **_kw: None)
    monkeypatch.setattr(common_utils, "_workspace_base_dir", None)
    monkeypatch.setenv("JIUWENSWARM_DATA_DIR", str(private_root))

    scenario = producer._register_private_scenario(private_root)
    producer._configure_product_environment(scenario)
    resolved = _resolve_database_path(
        os.environ["JIUWENSWARM_LIVE_VOICE_P3_DATABASE"]
    )
    expected = (
        private_root / "live_voice" / "p3alpha" / "p3-wave2.sqlite3"
    ).resolve()

    assert scenario.database == expected
    assert resolved == expected
    assert not expected.exists()
    assert expected.parent.is_dir()
    assert not producer._is_reparse_or_symlink(private_root / "live_voice")
    assert not producer._is_reparse_or_symlink(expected.parent)
    assert expected.parent.resolve() == (
        private_root.resolve() / "live_voice" / "p3alpha"
    )
    assert len(projects) == 2


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
@pytest.mark.parametrize("junction_level", ["live_voice", "p3alpha"])
def test_registration_rejects_existing_windows_store_junction_before_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    junction_level: str,
) -> None:
    from jiuwenswarm.server.runtime.session import project_store, session_metadata

    private_root, _output = _private_cli_paths(
        tmp_path, f"store-junction-{junction_level}"
    )
    outside = tmp_path / f"store-outside-{junction_level}"
    outside.mkdir()
    live_voice = private_root / "live_voice"
    if junction_level == "live_voice":
        junction = live_voice
        outside_database = outside / "p3alpha" / "p3-wave2.sqlite3"
    else:
        live_voice.mkdir()
        junction = live_voice / "p3alpha"
        outside_database = outside / "p3-wave2.sqlite3"
    created = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "New-Item -ItemType Junction -Path $env:JUNCTION_PATH "
            "-Target $env:JUNCTION_TARGET | Out-Null",
        ],
        check=False,
        capture_output=True,
        env={
            **os.environ,
            "JUNCTION_PATH": str(junction),
            "JUNCTION_TARGET": str(outside),
        },
    )
    assert created.returncode == 0
    project_calls: list[str] = []
    monkeypatch.setattr(
        producer,
        "_initialize_private_project",
        lambda *_args, **_kwargs: project_calls.append("initialize"),
    )
    monkeypatch.setattr(
        project_store,
        "create_or_restore_project",
        lambda *_args, **_kwargs: project_calls.append("register"),
    )
    monkeypatch.setattr(
        session_metadata,
        "init_session_metadata",
        lambda **_kwargs: project_calls.append("session"),
    )

    with pytest.raises(ClosedEvidenceFailure) as raised:
        producer._register_private_scenario(private_root)

    assert raised.value.reason == "PRIVATE_PATH_REPARSE_POINT"
    assert project_calls == []
    assert not outside_database.exists()


@pytest.mark.parametrize(
    "reason",
    [
        "REAL_CONCURRENT_INITIAL_TIMEOUT",
        "REAL_A2_BUSY_TIMEOUT",
        "REAL_A1_CANCEL_A2_DEQUEUE_TIMEOUT",
        "REAL_A2_INITIAL_TOOL_TIMEOUT",
        "REAL_A2_ADJUST_TIMEOUT",
        "REAL_B1_CANCEL_TIMEOUT",
    ],
)
@pytest.mark.skipif(os.name != "nt", reason="real producer is Windows-only")
def test_supervisor_preserves_allowlisted_worker_stage_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
    reason: str,
) -> None:
    private_root, output = _private_cli_paths(tmp_path, "closed-stage-reason")
    monkeypatch.setattr(
        producer,
        "_worker_command",
        lambda arguments, remaining: _closed_failure_worker_command(
            arguments,
            remaining,
            reason=reason,
        ),
    )

    assert main(["--private-root", str(private_root), "--output", str(output)]) == 2

    assert not output.exists()
    assert capsys.readouterr() == (
        f'{{"ok":false,"reason":"{reason}"}}\n',
        "",
    )


@pytest.mark.parametrize("predicate_kind", ["sync", "async"])
@pytest.mark.asyncio
async def test_wait_stage_maps_predicate_exception_without_polling(
    monkeypatch: pytest.MonkeyPatch,
    predicate_kind: str,
) -> None:
    predicate_calls = 0
    sleep_calls = 0

    def failing_predicate() -> bool:
        nonlocal predicate_calls
        predicate_calls += 1
        raise RuntimeError("RAW_PREDICATE_EXCEPTION_SENTINEL")

    async def failing_async_predicate() -> bool:
        nonlocal predicate_calls
        predicate_calls += 1
        raise RuntimeError("RAW_ASYNC_PREDICATE_EXCEPTION_SENTINEL")

    async def forbidden_sleep(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        raise AssertionError("predicate failure must not poll")

    monkeypatch.setattr(producer.asyncio, "sleep", forbidden_sleep)

    with pytest.raises(ClosedEvidenceFailure) as raised:
        await producer._wait_stage(
            (
                failing_predicate
                if predicate_kind == "sync"
                else failing_async_predicate
            ),
            deadline=time.monotonic() + 60,
            reason="REAL_CONCURRENT_INITIAL_TIMEOUT",
        )

    assert raised.value.reason == "REAL_STAGE_OBSERVATION_FAILED"
    assert predicate_calls == 1
    assert sleep_calls == 0


@pytest.mark.asyncio
async def test_wait_stage_preserves_closed_failure_and_polls_normal_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = iter((False, True))
    sleep_calls = 0

    async def no_delay(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1

    monkeypatch.setattr(producer.asyncio, "sleep", no_delay)
    await producer._wait_stage(
        lambda: next(results),
        deadline=time.monotonic() + 60,
        reason="REAL_CONCURRENT_INITIAL_TIMEOUT",
    )
    assert sleep_calls == 1

    with pytest.raises(ClosedEvidenceFailure) as raised:
        await producer._wait_stage(
            lambda: (_ for _ in ()).throw(
                ClosedEvidenceFailure("REAL_MUTATION_REJECTED")
            ),
            deadline=time.monotonic() + 60,
            reason="REAL_CONCURRENT_INITIAL_TIMEOUT",
        )
    assert raised.value.reason == "REAL_MUTATION_REJECTED"


@pytest.mark.parametrize(
    "invalid_reason",
    [
        pytest.param(None, id="none"),
        pytest.param([], id="non-hashable"),
        pytest.param("", id="empty"),
        pytest.param("RAW_NUL_REASON_SENTINEL\0", id="nul"),
        pytest.param("R" * 4096, id="oversized"),
    ],
)
def test_worker_entry_rejects_invalid_closed_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_reason: object,
) -> None:
    private_root = tmp_path / "invalid-closed-reason"
    output = private_root / "raw-evidence.json"

    async def fail_with_invalid_reason(*_args, **_kwargs) -> None:
        raise ClosedEvidenceFailure(invalid_reason)  # type: ignore[arg-type]

    monkeypatch.setattr(
        producer,
        "_cli_paths",
        lambda _arguments: (private_root, output),
    )
    monkeypatch.setattr(producer, "_producer_platform_name", lambda: "nt")
    monkeypatch.setattr(producer, "_run_production_cli", fail_with_invalid_reason)

    assert producer._worker_entry(["ignored"], 1.0) == 2


@pytest.mark.parametrize("failure_kind", ["closed", "exception", "crash"])
@pytest.mark.skipif(os.name != "nt", reason="real producer is Windows-only")
def test_supervisor_maps_unknown_worker_failure_to_one_closed_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
    failure_kind: str,
) -> None:
    private_root, output = _private_cli_paths(
        tmp_path,
        f"unknown-worker-{failure_kind}",
    )
    sentinel = f"RAW_{failure_kind.upper()}_FAILURE_SENTINEL"

    def command(arguments: list[str], remaining: float) -> list[str]:
        if failure_kind == "closed":
            return _closed_failure_worker_command(
                arguments,
                remaining,
                reason=sentinel,
            )
        if failure_kind == "exception":
            return _runtime_failure_worker_command(
                arguments,
                remaining,
                message=sentinel,
            )
        return [sys.executable, "-c", "import os; os._exit(17)"]

    monkeypatch.setattr(producer, "_worker_command", command)

    assert main(["--private-root", str(private_root), "--output", str(output)]) == 2

    captured = capsys.readouterr()
    assert captured == (
        '{"ok":false,"reason":"REAL_PRODUCER_FAILED"}\n',
        "",
    )
    assert sentinel not in captured.out
    assert not output.exists()


def test_blocking_private_preflight_is_bounded_by_worker_supervisor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    private_root, output = _private_cli_paths(tmp_path, "blocking-preflight")
    real_cli_paths = producer._cli_paths

    def blocking_parent_preflight(arguments: list[str]) -> tuple[Path, Path]:
        time.sleep(0.25)
        return real_cli_paths(arguments)

    def blocking_worker_command(arguments: list[str], remaining: float) -> list[str]:
        bootstrap = (
            "import sys,time; from scripts.live_voice import "
            "p3_wave2_real_evidence_producer as p; real=p._cli_paths; "
            "p._cli_paths=lambda argv:(time.sleep(0.25),real(argv))[1]; "
            "raise SystemExit(p._worker_entry(sys.argv[1:5],float(sys.argv[5])))"
        )
        return [sys.executable, "-c", bootstrap, *arguments, f"{remaining:.9f}"]

    monkeypatch.setattr(producer, "_IN_PROCESS_LIMIT_SECONDS", 0.05)
    monkeypatch.setattr(producer, "_cli_paths", blocking_parent_preflight)
    monkeypatch.setattr(producer, "_worker_command", blocking_worker_command)

    started = time.monotonic()
    exit_code = main(
        ["--private-root", str(private_root), "--output", str(output)]
    )
    elapsed = time.monotonic() - started

    assert exit_code == 2
    assert elapsed < 0.20
    assert not output.exists()
    assert capsys.readouterr() == (
        '{"ok":false,"reason":"REAL_SCENARIO_DEADLINE_EXCEEDED"}\n',
        "",
    )


@pytest.mark.parametrize("existing_kind", ["regular", "symlink", "junction"])
def test_worker_preflight_rejects_existing_output_without_deleting_caller_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
    existing_kind: str,
) -> None:
    private_root, output = _private_cli_paths(
        tmp_path,
        f"existing-{existing_kind}",
    )
    sentinel = b"CALLER_EXISTING_OUTPUT_SENTINEL"
    target = tmp_path / f"{existing_kind}-target"
    emulated_symlink = False
    if existing_kind == "regular":
        output.write_bytes(sentinel)
    elif existing_kind == "symlink":
        target.write_bytes(sentinel)
        try:
            output.symlink_to(target)
        except OSError:
            output.write_bytes(sentinel)
            original = producer._is_reparse_or_symlink
            monkeypatch.setattr(
                producer,
                "_is_reparse_or_symlink",
                lambda path: path == output or original(path),
            )
            emulated_symlink = True
    else:
        target.mkdir()
        (target / "sentinel.bin").write_bytes(sentinel)
        created = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "New-Item -ItemType Junction -Path $env:JUNCTION_PATH "
                "-Target $env:JUNCTION_TARGET | Out-Null",
            ],
            check=False,
            capture_output=True,
            env={
                **os.environ,
                "JUNCTION_PATH": str(output),
                "JUNCTION_TARGET": str(target),
            },
        )
        assert created.returncode == 0
    assert main(["--private-root", str(private_root), "--output", str(output)]) == 2
    if existing_kind == "regular" or emulated_symlink:
        assert output.read_bytes() == sentinel
    elif existing_kind == "symlink":
        assert output.is_symlink()
        assert target.read_bytes() == sentinel
    else:
        assert (target / "sentinel.bin").read_bytes() == sentinel
    assert capsys.readouterr() == (
        '{"ok":false,"reason":"REAL_PRODUCER_FAILED"}\n',
        "",
    )


def test_worker_preflight_rejects_broad_acl_without_creating_output(
    tmp_path: Path,
    capsys,
) -> None:
    private_root = tmp_path / "worker-broad-acl"
    (private_root / "config").mkdir(parents=True)
    config = private_root / "config" / "config.yaml"
    dotenv = private_root / ".env"
    config.write_text("{}", encoding="utf-8")
    dotenv.write_text("PRIVATE_ENV_SENTINEL", encoding="utf-8")
    if os.name == "nt":
        granted = subprocess.run(
            [
                "icacls",
                str(private_root),
                "/grant",
                "*S-1-5-32-545:(OI)(CI)R",
                "/T",
                "/C",
            ],
            check=False,
            capture_output=True,
        )
        assert granted.returncode == 0
    else:
        private_root.chmod(0o755)
    output = private_root / "raw-evidence.json"

    assert main(["--private-root", str(private_root), "--output", str(output)]) == 2

    assert not output.exists()
    assert config.read_text(encoding="utf-8") == "{}"
    assert dotenv.read_text(encoding="utf-8") == "PRIVATE_ENV_SENTINEL"
    assert capsys.readouterr() == (
        '{"ok":false,"reason":"REAL_PRODUCER_FAILED"}\n',
        "",
    )


def test_worker_failure_retains_its_unowned_output_for_cleanup_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    private_root, output = _private_cli_paths(tmp_path, "worker-failure")
    sentinel = b"WORKER_FAILURE_OUTPUT_SENTINEL"
    monkeypatch.setattr(
        producer,
        "_worker_command",
        lambda arguments, _remaining: [
            sys.executable,
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes("
            f"{sentinel!r}); raise SystemExit(2)",
            arguments[3],
        ],
    )

    assert main(["--private-root", str(private_root), "--output", str(output)]) == 2
    assert output.read_bytes() == sentinel
    assert capsys.readouterr() == (
        '{"ok":false,"reason":"REAL_PRODUCER_FAILED"}\n',
        "",
    )


def test_cli_global_deadline_kills_tree_and_retains_cleanup_pending_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    private_root = tmp_path / "deadline-private"
    (private_root / "config").mkdir(parents=True)
    (private_root / "config" / "config.yaml").write_text("{}", encoding="utf-8")
    (private_root / ".env").write_text("", encoding="utf-8")
    _make_private_acl(private_root)
    output = private_root / "raw-evidence.json"
    escaped = private_root / "escaped-descendant.txt"
    taskkill_calls: list[object] = []
    real_run = producer.subprocess.run

    def forbid_taskkill(arguments, *args, **kwargs):
        if arguments and str(arguments[0]).casefold() == "taskkill":
            taskkill_calls.append(arguments)
            raise AssertionError("PID-based taskkill is forbidden")
        return real_run(arguments, *args, **kwargs)

    monkeypatch.setattr(producer.subprocess, "run", forbid_taskkill)
    monkeypatch.setattr(producer, "_IN_PROCESS_LIMIT_SECONDS", 0.2)
    monkeypatch.setattr(
        producer,
        "_worker_command",
        lambda arguments, _remaining: [
            sys.executable,
            "-c",
            "import os,pathlib,subprocess,sys,time; "
            "subprocess.Popen([sys.executable,'-c',"
            "'import pathlib,sys,time; time.sleep(0.8); '"
            "+'pathlib.Path(sys.argv[1]).write_text(\"escaped\")',sys.argv[2]]); "
            "pathlib.Path(sys.argv[1]).write_bytes(b'TIMEOUT_OUTPUT_SENTINEL'); "
            "os.write(1,b'PRIVATE_CHILD_SENTINEL'); time.sleep(5)",
            arguments[3],
            str(escaped),
        ],
        raising=False,
    )

    started = time.monotonic()
    exit_code = main(
        ["--private-root", str(private_root), "--output", str(output)]
    )
    elapsed = time.monotonic() - started

    assert exit_code == 2
    assert elapsed < 2
    assert output.read_bytes() == b"TIMEOUT_OUTPUT_SENTINEL"
    time.sleep(1)
    assert not escaped.exists()
    assert taskkill_calls == []
    assert capsys.readouterr() == (
        '{"ok":false,"reason":"REAL_SCENARIO_DEADLINE_EXCEEDED"}\n',
        "",
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object ownership")
@pytest.mark.parametrize("leader_state", ["exited", "concurrent-exit"])
def test_windows_timeout_uses_stable_job_handle_after_leader_exit_and_pid_reuse(
    monkeypatch: pytest.MonkeyPatch,
    leader_state: str,
) -> None:
    class ReusedPidProcess:
        def __init__(self) -> None:
            self.polls = [0] if leader_state == "exited" else [None, 0]
            self.waited = False

        @property
        def pid(self):
            raise AssertionError("reused PID must never be consulted")

        def poll(self):
            return self.polls.pop(0) if self.polls else 0

        def wait(self, *, timeout: float):
            assert timeout >= 0
            self.waited = True
            return 0

        def kill(self):
            raise AssertionError("stable Job handle must own termination")

    process = ReusedPidProcess()
    job = object()
    terminated: list[object] = []
    monkeypatch.setattr(
        producer,
        "_terminate_windows_job",
        lambda owner: terminated.append(owner),
        raising=False,
    )

    producer._terminate_owned_worker(
        process,
        windows_job=job,
        deadline=time.monotonic() + 1,
    )

    assert terminated == [job]
    assert process.waited is True


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object ownership")
def test_windows_job_assignment_failure_fails_closed_and_kills_by_process_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_root, output = _private_cli_paths(tmp_path, "job-assignment-failure")

    class OwnedProcessHandle:
        def __init__(self) -> None:
            self.killed = False
            self.waited = False

        def kill(self):
            self.killed = True

        def wait(self, *, timeout: float):
            assert timeout >= 0
            self.waited = True
            return 1

    process = OwnedProcessHandle()
    monkeypatch.setattr(producer.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(
        producer,
        "_create_windows_kill_job",
        lambda _process: (_ for _ in ()).throw(
            ClosedEvidenceFailure("REAL_PROCESS_TREE_ISOLATION_UNAVAILABLE")
        ),
        raising=False,
    )

    with pytest.raises(ClosedEvidenceFailure) as raised:
        producer._supervise_production_worker(
            ["--private-root", str(private_root), "--output", str(output)],
            private_root,
            output,
            deadline=time.monotonic() + 1,
        )

    assert raised.value.reason == "REAL_PROCESS_TREE_ISOLATION_UNAVAILABLE"
    assert process.killed is True
    assert process.waited is True


def test_normal_worker_close_kills_owned_descendant_without_taskkill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_root, output = _private_cli_paths(tmp_path, "normal-owned-tree")
    escaped = private_root / "normal-escaped-descendant.txt"
    taskkill_calls: list[object] = []
    real_run = producer.subprocess.run

    def forbid_taskkill(arguments, *args, **kwargs):
        if arguments and str(arguments[0]).casefold() == "taskkill":
            taskkill_calls.append(arguments)
            raise AssertionError("PID-based taskkill is forbidden")
        return real_run(arguments, *args, **kwargs)

    monkeypatch.setattr(producer.subprocess, "run", forbid_taskkill)
    monkeypatch.setattr(
        producer,
        "_worker_command",
        lambda _arguments, _remaining: [
            sys.executable,
            "-c",
            "import subprocess,sys; subprocess.Popen([sys.executable,'-c',"
            "'import pathlib,sys,time; time.sleep(0.8); '"
            "+'pathlib.Path(sys.argv[1]).write_text(\"escaped\")',sys.argv[1]])",
            str(escaped),
        ],
    )
    monkeypatch.setattr(
        producer,
        "_validate_worker_output",
        lambda _root, _output: {
            "ok": True,
            "observation_count": 4,
            "paired_file_tool_count": 2,
            "write_edit_pair_count": 1,
        },
    )

    aggregate = producer._supervise_production_worker(
        ["--private-root", str(private_root), "--output", str(output)],
        private_root,
        output,
        deadline=time.monotonic() + 5,
    )

    assert aggregate["ok"] is True
    time.sleep(1)
    assert not escaped.exists()
    assert taskkill_calls == []


def test_simulated_posix_cli_fails_closed_before_spawn_with_zero_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    private_root, output = _private_cli_paths(tmp_path, "simulated-posix")
    config = private_root / "config" / "config.yaml"
    dotenv = private_root / ".env"
    config_before = config.read_bytes()
    dotenv_before = dotenv.read_bytes()
    spawn_calls: list[object] = []

    def forbidden_spawn(*args, **_kwargs):
        spawn_calls.append(args)
        raise AssertionError("POSIX producer must fail before spawn")

    monkeypatch.setattr(
        producer,
        "_producer_platform_name",
        lambda: "posix",
        raising=False,
    )
    monkeypatch.setattr(producer.subprocess, "Popen", forbidden_spawn)

    exit_code = main(
        ["--private-root", str(private_root), "--output", str(output)]
    )

    assert exit_code == 2
    assert spawn_calls == []
    assert not output.exists()
    assert config.read_bytes() == config_before
    assert dotenv.read_bytes() == dotenv_before
    assert capsys.readouterr() == (
        '{"ok":false,"reason":"REAL_PROCESS_TREE_ISOLATION_UNAVAILABLE"}\n',
        "",
    )


@pytest.mark.skipif(os.name == "nt", reason="real POSIX fail-closed boundary")
def test_real_posix_cli_fails_closed_before_spawn_with_zero_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    private_root, output = _private_cli_paths(tmp_path, "real-posix")
    marker = private_root / "caller-marker.bin"
    marker.write_bytes(b"CALLER_POSIX_SENTINEL")
    marker.chmod(0o600)
    spawn_calls: list[object] = []

    def forbidden_spawn(*args, **_kwargs):
        spawn_calls.append(args)
        raise AssertionError("POSIX producer must fail before spawn")

    monkeypatch.setattr(producer.subprocess, "Popen", forbidden_spawn)

    exit_code = main(
        ["--private-root", str(private_root), "--output", str(output)]
    )

    assert exit_code == 2
    assert spawn_calls == []
    assert not output.exists()
    assert marker.read_bytes() == b"CALLER_POSIX_SENTINEL"
    assert capsys.readouterr() == (
        '{"ok":false,"reason":"REAL_PROCESS_TREE_ISOLATION_UNAVAILABLE"}\n',
        "",
    )


def test_invalid_worker_evidence_is_retained_for_cleanup_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    private_root, output = _private_cli_paths(tmp_path, "invalid-evidence")
    sentinel = b"PRIVATE_INVALID_EVIDENCE_SENTINEL"
    monkeypatch.setattr(
        producer,
        "_worker_command",
        lambda arguments, _remaining: [
            sys.executable,
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes("
            f"{sentinel!r})",
            arguments[3],
        ],
    )

    assert main(["--private-root", str(private_root), "--output", str(output)]) == 2
    assert output.read_bytes() == sentinel
    assert capsys.readouterr() == (
        '{"ok":false,"reason":"EVIDENCE_JSON_INVALID"}\n',
        "",
    )


def test_competing_output_created_after_parent_preflight_is_never_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    private_root, output = _private_cli_paths(tmp_path, "competing-output")
    sentinel = b"CALLER_RACE_OUTPUT_SENTINEL"
    real_popen = subprocess.Popen

    def racing_popen(_command, **kwargs):
        output.write_bytes(sentinel)
        return real_popen(
            [sys.executable, "-c", "raise SystemExit(2)"],
            **kwargs,
        )

    monkeypatch.setattr(producer.subprocess, "Popen", racing_popen)

    assert main(["--private-root", str(private_root), "--output", str(output)]) == 2
    assert output.read_bytes() == sentinel
    assert capsys.readouterr() == (
        '{"ok":false,"reason":"REAL_PRODUCER_FAILED"}\n',
        "",
    )


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


@pytest.mark.parametrize(
    "occupied_field",
    [
        "journal_record_present",
        "worker_present",
        "applying_present",
        "checkpoint_present",
        "retained_cleanup_present",
        "worktree_present",
        "attempt_agent_owner_present",
        "attempt_agent_pin_present",
        "attempt_agent_lease_present",
    ],
)
def test_direct_authority_snapshot_fails_closed_for_every_a2_prelease_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    occupied_field: str,
) -> None:
    project = tmp_path / "project-a"
    project.mkdir()
    subprocess.run(
        ["git", "-C", str(project), "init", "--initial-branch=main"],
        check=True,
        capture_output=True,
    )

    class Journal:
        record = None

        def get(self, _attempt_id: str):
            return self.record

    journal = Journal()
    executor = SimpleNamespace(
        _journal=journal,
        _running={},
        _applying=set(),
        _adjustment_checkpoints={},
        _retained_worktree_cleanups={},
    )
    manager = SimpleNamespace(
        agents={},
        _agent_create_params={},
        _agent_pins={},
        _agent_borrowers={},
    )
    parent = tmp_path / "attempt-parent"
    worktree = parent / "checkout"
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.project_code_executor."
        "_attempt_worktree_paths",
        lambda _root, _attempt: (parent, worktree),
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.project_code_executor."
        "_worktree_registered",
        lambda _root, _worktree: False,
    )

    clear = producer._direct_authority_snapshot(
        executor=executor,
        agent_manager=manager,
        project_root=project,
        attempt_ref="attempt-A2",
    )
    assert clear.all_clear is True
    assert set(asdict(clear).values()) == {False}

    agent = SimpleNamespace(_jiuwenswarm_agent_project_dir=str(worktree))
    if occupied_field == "journal_record_present":
        journal.record = object()
    elif occupied_field == "worker_present":
        executor._running["attempt-A2"] = object()
    elif occupied_field == "applying_present":
        executor._applying.add("attempt-A2")
    elif occupied_field == "checkpoint_present":
        executor._adjustment_checkpoints["attempt-A2"] = object()
    elif occupied_field == "retained_cleanup_present":
        executor._retained_worktree_cleanups["attempt-A2"] = object()
    elif occupied_field == "worktree_present":
        parent.mkdir()
    elif occupied_field == "attempt_agent_lease_present":
        manager._agent_create_params = {
            "live_voice_formal_task": {
                "agent-A2": {"config": {"project_dir": str(worktree)}}
            }
        }
    else:
        manager.agents = {"live_voice_formal_task": {"agent-A2": agent}}
        if occupied_field == "attempt_agent_pin_present":
            manager._agent_pins[id(agent)] = 1
    occupied = producer._direct_authority_snapshot(
        executor=executor,
        agent_manager=manager,
        project_root=project,
        attempt_ref="attempt-A2",
    )
    assert occupied.all_clear is False
    assert getattr(occupied, occupied_field) is True


@pytest.mark.parametrize(
    "broad_sid",
    ["S-1-1-0", "S-1-5-11", "S-1-5-32-545"],
)
def test_private_preflight_rejects_a_real_broad_windows_acl(
    tmp_path: Path,
    broad_sid: str,
) -> None:
    private_root = tmp_path / "broad-private-root"
    (private_root / "config").mkdir(parents=True)
    (private_root / "config" / "config.yaml").write_text("{}", encoding="utf-8")
    (private_root / ".env").write_text("", encoding="utf-8")
    if os.name == "nt":
        granted = subprocess.run(
            [
                "icacls",
                str(private_root),
                "/grant",
                f"*{broad_sid}:(OI)(CI)R",
                "/T",
                "/C",
            ],
            check=False,
            capture_output=True,
        )
        assert granted.returncode == 0
    else:
        private_root.chmod(0o755)

    with pytest.raises(ClosedEvidenceFailure) as raised:
        producer._validated_private_paths(
            private_root.resolve(),
            (private_root / "raw-evidence.json").resolve(),
        )

    assert raised.value.reason == "PRIVATE_ACL_NOT_PRIVATE"


def test_private_preflight_accepts_only_current_user_system_and_admins(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private-allowlist"
    (private_root / "config").mkdir(parents=True)
    (private_root / "config" / "config.yaml").write_text("{}", encoding="utf-8")
    (private_root / ".env").write_text("", encoding="utf-8")
    _make_private_acl(private_root)
    output = private_root / "raw-evidence.json"

    assert producer._validated_private_paths(private_root, output) == (
        private_root.resolve(),
        output.resolve(),
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
@pytest.mark.parametrize("junction_kind", ["root", "config", "output"])
def test_private_preflight_rejects_real_windows_junctions(
    tmp_path: Path,
    junction_kind: str,
) -> None:
    target = tmp_path / f"{junction_kind}-target"
    target.mkdir()
    private_root = tmp_path / f"{junction_kind}-private"
    if junction_kind == "root":
        (target / "config").mkdir()
        (target / "config" / "config.yaml").write_text("{}", encoding="utf-8")
        (target / ".env").write_text("", encoding="utf-8")
        junction = private_root
    else:
        private_root.mkdir()
        (private_root / ".env").write_text("", encoding="utf-8")
        if junction_kind == "config":
            (target / "config.yaml").write_text("{}", encoding="utf-8")
            junction = private_root / "config"
        else:
            (private_root / "config").mkdir()
            (private_root / "config" / "config.yaml").write_text(
                "{}", encoding="utf-8"
            )
            junction = private_root / "raw-evidence.json"
    created = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "New-Item -ItemType Junction -Path $env:JUNCTION_PATH "
            "-Target $env:JUNCTION_TARGET | Out-Null",
        ],
        check=False,
        capture_output=True,
        env={
            **os.environ,
            "JUNCTION_PATH": str(junction),
            "JUNCTION_TARGET": str(target),
        },
    )
    assert created.returncode == 0

    with pytest.raises(ClosedEvidenceFailure) as raised:
        producer._validated_private_paths(
            private_root.absolute(),
            (private_root / "raw-evidence.json").absolute(),
        )

    assert raised.value.reason == "PRIVATE_PATH_REPARSE_POINT"


@pytest.mark.parametrize("linked_basename", ["config.yaml", ".env"])
def test_private_preflight_rejects_real_configuration_symlinks(
    tmp_path: Path,
    linked_basename: str,
) -> None:
    private_root = tmp_path / f"{linked_basename}-private"
    (private_root / "config").mkdir(parents=True)
    config = private_root / "config" / "config.yaml"
    dotenv = private_root / ".env"
    linked = dotenv if linked_basename == ".env" else config
    normal = config if linked is dotenv else dotenv
    normal.write_text("{}", encoding="utf-8")
    target = tmp_path / f"{linked_basename}-target"
    target.write_text("{}", encoding="utf-8")
    try:
        linked.symlink_to(target)
    except OSError:
        pytest.skip("file symlinks unavailable on this host")

    with pytest.raises(ClosedEvidenceFailure) as raised:
        producer._validated_private_paths(
            private_root.absolute(),
            (private_root / "raw-evidence.json").absolute(),
        )

    assert raised.value.reason == "PRIVATE_PATH_REPARSE_POINT"


def test_fd_silence_blocks_os_write_and_child_output_then_restores_fds(
    capfd,
) -> None:
    with producer._silence_process_fds():
        os.write(1, b"PRIVATE_FD_STDOUT_SENTINEL\n")
        os.write(2, b"PRIVATE_FD_STDERR_SENTINEL\n")
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os; os.write(1,b'PRIVATE_CHILD_OUT_SENTINEL\\n'); "
                "os.write(2,b'PRIVATE_CHILD_ERR_SENTINEL\\n')",
            ],
            check=False,
        )
        assert child.returncode == 0
    print("RESTORED_STDOUT")
    print("RESTORED_STDERR", file=sys.stderr)

    captured = capfd.readouterr()
    assert captured.out == "RESTORED_STDOUT\n"
    assert captured.err == "RESTORED_STDERR\n"


def test_cli_exception_cannot_leak_fd_or_child_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd,
) -> None:
    private_root, output = _private_cli_paths(tmp_path, "exception-private")

    def leaking_failure(*_args, **_kwargs):
        os.write(1, b"PRIVATE_EXCEPTION_STDOUT_SENTINEL\n")
        os.write(2, b"PRIVATE_EXCEPTION_STDERR_SENTINEL\n")
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import os; os.write(1,b'PRIVATE_EXCEPTION_CHILD_OUT'); "
                "os.write(2,b'PRIVATE_EXCEPTION_CHILD_ERR')",
            ],
            check=False,
        )
        raise RuntimeError("PRIVATE_EXCEPTION_DETAIL")

    monkeypatch.setattr(producer, "_supervise_production_worker", leaking_failure)

    assert main(["--private-root", str(private_root), "--output", str(output)]) == 2
    assert capfd.readouterr() == (
        '{"ok":false,"reason":"REAL_PRODUCER_FAILED"}\n',
        "",
    )


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_source_snapshot_rejects_every_dirty_source_state(
    tmp_path: Path,
    dirty_kind: str,
) -> None:
    source = tmp_path / "source"
    producer._initialize_private_project(source, title="Clean Source")
    before = producer._clean_source_snapshot(source)
    assert len(before.head) == 40
    assert before.status == b""

    if dirty_kind == "tracked":
        (source / "README.md").write_text("dirty\n", encoding="utf-8")
    else:
        (source / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(ClosedEvidenceFailure) as raised:
        producer._clean_source_snapshot(source)

    assert raised.value.reason == "SOURCE_TREE_DIRTY"
