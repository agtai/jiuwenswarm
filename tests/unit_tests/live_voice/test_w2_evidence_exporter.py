# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice.observability import (
    LIVE_VOICE_CONTRACT_VERSION,
    OBSERVABILITY_SCHEMA_VERSION,
    create_metric,
    create_observation,
)
from jiuwenswarm.server.live_voice.w2_evidence_exporter import (
    MAX_W2_EVIDENCE_RECORDS,
    DisabledW2EvidenceExporter,
    W2EvidenceCapacityError,
    W2EvidenceExporterError,
    W2EvidenceRecordError,
    W2EvidenceSealedError,
    W2JsonlEvidenceExporter,
    create_w2_evidence_exporter,
    verify_w2_candidate_checkout,
)
from jiuwenswarm.server.live_voice.observability_exporter import (
    LiveVoiceObservabilityExporterBuffer,
)


def _route() -> dict[str, object]:
    return {
        "implementation_class": "formal",
        "owner_module": "runtime.conversation",
        "capability_provider": "jiuwenswarm-runtime",
        "contract_version": LIVE_VOICE_CONTRACT_VERSION,
        "reason_code": None,
    }


def _observation(event_id: str):
    return create_observation(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "event_id": event_id,
            "event_name": "segment.started",
            "segment_name": "runtime.turn",
            "observed_at": "2026-08-07T16:00:00Z",
            "monotonic_ms": 100.0,
            "binding": {
                "correlation_id": "correlation-w2",
                "interaction_id": "interaction-w2",
                "turn_id": "turn-w2",
            },
            "route": _route(),
            "source_component": "w2.evidence.test",
        }
    )


def _metric(measurement_id: str):
    return create_metric(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "measurement_id": measurement_id,
            "metric_name": "live_voice.queue_depth",
            "metric_kind": "gauge",
            "unit": "items",
            "value": 0,
            "observed_at": "2026-08-07T16:00:01Z",
            "binding": {"correlation_id": "correlation-w2"},
            "route": _route(),
            "segment_name": "runtime.queue",
            "implementation_class": "formal",
        }
    )


def _exporter(path: Path, **kwargs: object):
    return create_w2_evidence_exporter(
        enabled=True,
        path=path,
        candidate_sha="a" * 40,
        environment_id="environment-w2",
        session_id="session-w2",
        mode_id="integrated-formal",
        evidence_set_id="evidence-set-w2",
        artifact_id="artifact-agentserver-1",
        artifact_sequence=1,
        producer_id="agentserver",
        process_epoch="agentserver-epoch-1",
        **kwargs,
    )


class _ExplodingPath:
    def __str__(self) -> str:
        raise AssertionError("disabled factory inspected the path")


def test_disabled_factory_has_zero_path_or_filesystem_effect() -> None:
    exporter = create_w2_evidence_exporter(enabled=False, path=_ExplodingPath())

    assert type(exporter) is DisabledW2EvidenceExporter
    assert exporter.exporter is None
    assert exporter.snapshot().accepted_records == 0


@pytest.mark.asyncio
async def test_exact_public_records_append_canonical_sequenced_jsonl(
    tmp_path: Path,
) -> None:
    path = tmp_path / "w2-evidence.jsonl"
    exporter = _exporter(path)

    assert type(exporter) is W2JsonlEvidenceExporter
    await exporter(_observation("event-1"))
    await exporter(_metric("measurement-1"))
    await exporter.seal()

    records = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert [record["record_kind"] for record in records] == [
        "header",
        "observation",
        "metric",
        "footer",
    ]
    assert [record["sequence"] for record in records[1:-1]] == [0, 1]
    assert all(record["evidence_schema"] == "live-voice.w2-jsonl-evidence.v2" for record in records)
    assert records[0]["evidence_set_id"] == "evidence-set-w2"
    assert records[0]["artifact_id"] == "artifact-agentserver-1"
    assert records[0]["artifact_sequence"] == 1
    assert records[0]["producer_id"] == "agentserver"
    assert records[0]["process_epoch"] == "agentserver-epoch-1"
    assert all(
        record["candidate"]
        == {
            "candidate_sha": "a" * 40,
            "environment_id": "environment-w2",
            "session_id": "session-w2",
            "mode_id": "integrated-formal",
        }
        for record in records[1:-1]
    )
    assert records[1]["record"] == _observation("event-1").to_dict()
    assert records[2]["record"] == _metric("measurement-1").to_dict()
    assert records[3]["record_count"] == 2
    assert records[3]["last_sequence"] == 1
    assert records[3]["closed"] is True
    snapshot = exporter.snapshot()
    assert snapshot.accepted_records == 2
    assert snapshot.accepted_observations == 1
    assert snapshot.accepted_metrics == 1
    assert snapshot.business_result_changed is False


@pytest.mark.asyncio
async def test_invalid_record_is_rejected_before_creating_the_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "w2-evidence.jsonl"
    exporter = _exporter(path)

    with pytest.raises(W2EvidenceRecordError):
        await exporter({"transcript": "private"})  # type: ignore[arg-type]

    assert not path.exists()
    assert exporter.snapshot().rejected_invalid == 1


@pytest.mark.asyncio
async def test_capacity_is_non_evicting_and_does_not_append_rejected_record(
    tmp_path: Path,
) -> None:
    path = tmp_path / "w2-evidence.jsonl"
    exporter = _exporter(path, max_records=1)
    await exporter(_observation("event-1"))

    with pytest.raises(W2EvidenceCapacityError):
        await exporter(_observation("event-2"))

    assert len(path.read_text("utf-8").splitlines()) == 2
    snapshot = exporter.snapshot()
    assert snapshot.accepted_records == 1
    assert snapshot.rejected_capacity == 1


@pytest.mark.asyncio
async def test_concurrent_appends_are_serialized_with_contiguous_sequences(
    tmp_path: Path,
) -> None:
    path = tmp_path / "w2-evidence.jsonl"
    exporter = _exporter(path)

    await asyncio.gather(
        *(exporter(_observation(f"event-{index}")) for index in range(20))
    )

    records = [json.loads(line) for line in path.read_text("utf-8").splitlines()][1:]
    assert [record["sequence"] for record in records] == list(range(20))
    assert len({record["record"]["event_id"] for record in records}) == 20
    assert exporter.snapshot().accepted_records == 20


def test_enabled_factory_requires_an_existing_parent_and_regular_file_path(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="absolute"):
        _exporter(Path("relative.jsonl"))
    with pytest.raises(ValueError, match="parent"):
        _exporter(tmp_path / "missing" / "evidence.jsonl")
    with pytest.raises(ValueError, match="regular file"):
        _exporter(tmp_path)
    existing = tmp_path / "existing.jsonl"
    existing.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="must be new"):
        _exporter(existing)


def test_enabled_factory_rejects_unbounded_capacity_before_filesystem_effect(
    tmp_path: Path,
) -> None:
    path = tmp_path / "never-created.jsonl"

    with pytest.raises(ValueError, match="between 1"):
        _exporter(path, max_records=MAX_W2_EVIDENCE_RECORDS + 1)

    assert not path.exists()


def test_candidate_checkout_requires_exact_head_and_clean_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status = ""

    def fake_run(command: list[str], **_kwargs: object) -> object:
        output = "a" * 40 + "\n" if command[-2:] == ["rev-parse", "HEAD"] else status
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.w2_evidence_exporter.subprocess.run",
        fake_run,
    )
    assert verify_w2_candidate_checkout(
        repository_path=tmp_path.resolve(), candidate_sha="a" * 40
    ) == "a" * 40

    with pytest.raises(W2EvidenceExporterError, match="does not match"):
        verify_w2_candidate_checkout(
            repository_path=tmp_path.resolve(), candidate_sha="b" * 40
        )
    status = " M dirty.py\n"
    with pytest.raises(W2EvidenceExporterError, match="must be clean"):
        verify_w2_candidate_checkout(
            repository_path=tmp_path.resolve(), candidate_sha="a" * 40
        )


def test_candidate_checkout_rejects_clean_decoy_for_loaded_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded_root = Path(__file__).resolve().parents[3]

    def fake_run(command: list[str], **_kwargs: object) -> object:
        if command[-2:] == ["rev-parse", "--show-toplevel"]:
            return SimpleNamespace(stdout=str(loaded_root) + "\n")
        return SimpleNamespace(stdout="a" * 40 + "\n")

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.w2_evidence_exporter.subprocess.run",
        fake_run,
    )
    with pytest.raises(W2EvidenceExporterError, match="loaded source tree"):
        verify_w2_candidate_checkout(
            repository_path=tmp_path.resolve(),
            candidate_sha="a" * 40,
            bind_loaded_source=True,
        )


@pytest.mark.asyncio
async def test_cancellation_before_commit_has_zero_late_write_and_keeps_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ordered-cancel.jsonl"
    exporter = _exporter(path)
    entered_fsync = Event()
    release_fsync = Event()
    call_lock = Lock()
    calls = 0
    real_fsync = __import__("os").fsync

    def blocking_first_fsync(fd: int) -> None:
        nonlocal calls
        with call_lock:
            calls += 1
            call_number = calls
        if call_number == 1:
            entered_fsync.set()
            assert release_fsync.wait(2)
        real_fsync(fd)

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.w2_evidence_exporter.os.fsync",
        blocking_first_fsync,
    )
    first = asyncio.create_task(exporter(_observation("event-first")))
    assert await asyncio.to_thread(entered_fsync.wait, 1)
    cancelled = asyncio.create_task(exporter(_observation("event-cancelled")))
    await asyncio.sleep(0.01)
    cancelled.cancel()
    await asyncio.sleep(0.01)
    release_fsync.set()

    await first
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    records = [json.loads(line) for line in path.read_text("utf-8").splitlines()][1:]
    assert [record["sequence"] for record in records] == [0]
    assert records[0]["record"]["event_id"] == "event-first"
    assert exporter.snapshot().accepted_records == 1


@pytest.mark.asyncio
async def test_cancellation_after_commit_starts_settles_as_durable_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "retained-commit.jsonl"
    exporter = _exporter(path)
    entered_fsync = Event()
    release_fsync = Event()
    real_fsync = __import__("os").fsync

    def blocking_fsync(fd: int) -> None:
        entered_fsync.set()
        assert release_fsync.wait(2)
        real_fsync(fd)

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.w2_evidence_exporter.os.fsync",
        blocking_fsync,
    )
    attempt = asyncio.create_task(exporter(_observation("event-committing")))
    assert await asyncio.to_thread(entered_fsync.wait, 1)
    attempt.cancel()
    await asyncio.sleep(0.01)
    assert not attempt.done()
    release_fsync.set()

    assert await attempt is None
    assert exporter.snapshot().accepted_records == 1
    assert len(path.read_text("utf-8").splitlines()) == 2


@pytest.mark.asyncio
async def test_sealed_artifact_rejects_every_late_append(tmp_path: Path) -> None:
    path = tmp_path / "sealed.jsonl"
    exporter = _exporter(path)
    await exporter(_observation("event-before-seal"))
    await exporter.seal()
    sealed = path.read_bytes()

    with pytest.raises(W2EvidenceSealedError):
        await exporter(_observation("event-after-seal"))

    assert path.read_bytes() == sealed
    assert exporter.snapshot().sealed is True


@pytest.mark.asyncio
async def test_buffer_timeout_waits_for_commit_truth_and_close_has_no_late_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "buffer-settled.jsonl"
    exporter = _exporter(path)
    entered_fsync = Event()
    release_fsync = Event()
    real_fsync = __import__("os").fsync

    def blocking_fsync(fd: int) -> None:
        entered_fsync.set()
        assert release_fsync.wait(2)
        real_fsync(fd)

    monkeypatch.setattr(
        "jiuwenswarm.server.live_voice.w2_evidence_exporter.os.fsync",
        blocking_fsync,
    )
    buffer = LiveVoiceObservabilityExporterBuffer(
        exporter,
        capacity=1,
        export_timeout_seconds=0.01,
        close_timeout_seconds=1,
    )
    await buffer.start()
    buffer.emit_observation(_observation("event-buffer-commit"))
    assert await asyncio.to_thread(entered_fsync.wait, 1)
    await asyncio.sleep(0.03)
    settling = buffer.snapshot()
    assert settling.stats.delivered_records == 0
    assert settling.stats.failed_records == 0
    assert settling.stats.timed_out_records == 0
    release_fsync.set()

    closed = await buffer.close()
    assert closed.closed
    assert closed.stats.delivered_records == 1
    assert closed.stats.failed_records == 0
    assert closed.stats.timed_out_records == 0
    settled_text = path.read_text("utf-8")
    settled_snapshot = exporter.snapshot()
    await asyncio.sleep(0.03)
    assert path.read_text("utf-8") == settled_text
    assert exporter.snapshot() == settled_snapshot
