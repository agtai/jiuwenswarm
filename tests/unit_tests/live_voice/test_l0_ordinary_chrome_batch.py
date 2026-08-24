from __future__ import annotations

import json
import http.client
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jiuwenswarm.server.live_voice.latency_measurement import (
    L0EvidenceSource,
    L0Milestone,
    L0RoundBinding,
    L0RoundClassification,
    L0RoundTemperature,
    create_l0_milestone,
)
from scripts.live_voice.l0_ordinary_chrome_batch import (
    BATCH_ATTEMPT_VERSION,
    BATCH_COMPLETION_VERSION,
    OrdinaryChromeBatchState,
    _Handler,
    _Server,
    build_d095_report,
)


CORPUS = Path("scripts/live_voice/l0_fixed_corpus.json")
SOURCE_HEAD = "a" * 40
CONFIGURATION_SHA256 = "b" * 64
ENVIRONMENT_REF = "ordinary-chrome-test"
EPOCH = "c" * 32
_BASE = datetime(2026, 8, 24, tzinfo=UTC)
_COMPLETED = {
    L0Milestone.LAST_FRAME_SENT,
    L0Milestone.LAST_FRAME_ACKED,
    L0Milestone.STT_FINAL_AVAILABLE,
    L0Milestone.COMMITTED_SUBMIT_ACCEPTED,
    L0Milestone.CHAT_FINAL,
    L0Milestone.PLAYOUT_COMPLETED,
}


def _state(tmp_path: Path, *, temperature: str = "warm") -> OrdinaryChromeBatchState:
    return OrdinaryChromeBatchState(
        evidence_directory=tmp_path,
        run_labels_file=tmp_path / "run-labels.json",
        corpus_path=CORPUS,
        source_head=SOURCE_HEAD,
        environment_ref=ENVIRONMENT_REF,
        configuration_sha256=CONFIGURATION_SHA256,
        browser_origin="http://localhost:5173",
        nonce="d" * 32,
        temperature=temperature,
        epoch_id=EPOCH,
        target=20,
        audio_wav={"short": b"short", "long": b"long", "barge": b"barge"},
    )


def _binding() -> L0RoundBinding:
    return L0RoundBinding(
        correlation_id="correlation-ordinary-0",
        session_id="session-ordinary-0",
        interaction_id="interaction-ordinary-0",
        activation_generation=1,
        response_id="response-ordinary-0",
        response_generation=0,
        turn_id="turn-ordinary-0",
        round_id="round-ordinary-0",
    )


def _record(
    milestone: L0Milestone,
    *,
    offset: int,
    classification: L0RoundClassification = L0RoundClassification.UNKNOWN,
) -> dict[str, object]:
    return create_l0_milestone(
        milestone=milestone,
        binding=_binding(),
        profile_id="ordinary-chrome-prerecorded-warm",
        scenario_id="short-no-tool-zh",
        sample_index=0,
        temperature=L0RoundTemperature.WARM,
        evidence_source=L0EvidenceSource.PRERECORDED,
        classification=classification,
        observed_at=(_BASE + timedelta(milliseconds=offset))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        monotonic_ms=float(offset),
        duration_ms=float(offset) if milestone in _COMPLETED else None,
        event_nonce=f"ordinary-{offset}",
    ).to_dict()


def test_warm_batch_requires_one_unmeasured_warmup_and_accepts_real_correlation(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    with pytest.raises(RuntimeError, match="warm-up"):
        state.next_job()

    state.accept_warmup(
        {
            "schema_version": BATCH_COMPLETION_VERSION,
            "automated_browser_complete": True,
            "browser_record_count": 0,
            "browser_dropped_record_count": 0,
        }
    )
    job = state.next_job()
    assert job["metric"] == "first_audio"
    assert job["labels"] == {
        "schema_version": "live-voice.l0-run-labels.v1",
        "profile_id": "ordinary-chrome-prerecorded-warm",
        "scenario_id": "short-no-tool-zh",
        "sample_index": 0,
        "temperature": "warm",
        "evidence_source": "prerecorded",
    }

    backend = [
        _record(L0Milestone.PROVIDER_EOT, offset=0),
        _record(L0Milestone.LAST_FRAME_ACKED, offset=30),
        _record(L0Milestone.UPLINK_CLOSED, offset=40),
        _record(L0Milestone.STT_FINAL_AVAILABLE, offset=400),
        _record(L0Milestone.COMMITTED_SUBMIT_ACCEPTED, offset=500),
        _record(L0Milestone.AGENT_REQUEST_START, offset=510),
        _record(L0Milestone.CHAT_FINAL, offset=1000),
        _record(L0Milestone.TTS_REQUEST, offset=1010),
        _record(L0Milestone.PROVIDER_FIRST_AUDIO, offset=1200),
        _record(L0Milestone.DOWNLINK_TICKET, offset=1210),
    ]
    (tmp_path / "l0-runtime-1.jsonl").write_text(
        "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in backend),
        encoding="utf-8",
    )
    browser = [
        _record(L0Milestone.BROWSER_EOT_RECEIPT, offset=10),
        _record(L0Milestone.CAPTURE_STOPPED, offset=20),
        _record(L0Milestone.LAST_FRAME_SENT, offset=25),
        _record(L0Milestone.SUCCESSOR_CAPTURE_READY, offset=1220),
        _record(L0Milestone.BROWSER_FIRST_FRAME, offset=1230),
        _record(L0Milestone.WEBAUDIO_FIRST_FRAME_SCHEDULED, offset=1240),
        _record(L0Milestone.WEBAUDIO_ACTUALLY_STARTED, offset=2240),
        _record(
            L0Milestone.PLAYOUT_COMPLETED,
            offset=3000,
            classification=L0RoundClassification.SUCCESS,
        ),
    ]
    result = state.complete(
        {
            "schema_version": BATCH_COMPLETION_VERSION,
            "job_id": job["job_id"],
            "automated_browser_complete": True,
            "browser_dropped_record_count": 0,
            "records": browser,
            "failure_reason": "none",
        }
    )

    assert result["eligible"] is True
    report = json.loads((tmp_path / "d095-report.json").read_text(encoding="utf-8"))
    warm = next(item for item in report["profiles"] if item["temperature"] == "warm")
    assert warm["first_audio"]["eligible_count"] == 1
    assert warm["first_audio"]["p50_ms"] == 2240.0
    assert report["physical_evidence"] == "not-claimed"
    serialized = json.dumps(report)
    assert "stimulus_text" not in serialized
    assert "operator_confirmation" not in serialized


def test_cold_epoch_consumes_exactly_one_attempt_even_when_incomplete(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path, temperature="cold")
    job = state.next_job()
    result = state.complete(
        {
            "schema_version": BATCH_COMPLETION_VERSION,
            "job_id": job["job_id"],
            "automated_browser_complete": False,
            "browser_dropped_record_count": 0,
            "records": [],
            "failure_reason": "browser_timeout",
        }
    )
    assert result["eligible"] is False
    assert state.shutdown_requested is True
    with pytest.raises(RuntimeError, match="already consumed"):
        state.next_job()
    labels = json.loads((tmp_path / "run-labels.json").read_text(encoding="utf-8"))
    assert labels == {
        "schema_version": "live-voice.l0-run-labels.v1",
        "measurement": "disabled",
    }


def test_wrong_job_labels_reject_before_any_evidence_or_label_mutation(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    state.accept_warmup(
        {
            "schema_version": BATCH_COMPLETION_VERSION,
            "automated_browser_complete": True,
            "browser_record_count": 0,
            "browser_dropped_record_count": 0,
        }
    )
    job = state.next_job()
    wrong = _record(L0Milestone.BROWSER_EOT_RECEIPT, offset=10)
    wrong["scenario_id"] = "playout-barge-in-zh"

    with pytest.raises(ValueError, match="escaped the exact job labels"):
        state.complete(
            {
                "schema_version": BATCH_COMPLETION_VERSION,
                "job_id": job["job_id"],
                "automated_browser_complete": False,
                "browser_dropped_record_count": 0,
                "records": [wrong],
                "failure_reason": "browser_incomplete",
            }
        )

    assert not (tmp_path / "browser.jsonl").exists()
    assert not (tmp_path / "batch-attempts.ndjson").exists()
    assert json.loads((tmp_path / "run-labels.json").read_text(encoding="utf-8")) == job[
        "labels"
    ]
    assert state.next_job() == job


def test_aggregate_rejection_has_zero_durable_completion_writes(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    state.accept_warmup(
        {
            "schema_version": BATCH_COMPLETION_VERSION,
            "automated_browser_complete": True,
            "browser_record_count": 0,
            "browser_dropped_record_count": 0,
        }
    )
    job = state.next_job()
    first = _record(L0Milestone.PROVIDER_EOT, offset=0)
    conflicting = _record(L0Milestone.STT_FINAL_AVAILABLE, offset=400)
    conflicting["binding"]["response_id"] = "response-ordinary-conflict"
    conflicting["binding"]["response_generation"] = 1
    conflicting["observation"]["binding"]["response_id"] = (
        "response-ordinary-conflict"
    )
    conflicting["observation"]["binding"]["response_generation"] = 1
    (tmp_path / "l0-runtime-1.jsonl").write_text(
        "".join(
            json.dumps(item, separators=(",", ":")) + "\n"
            for item in (first, conflicting)
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mixed identity scope"):
        state.complete(
            {
                "schema_version": BATCH_COMPLETION_VERSION,
                "job_id": job["job_id"],
                "automated_browser_complete": False,
                "browser_dropped_record_count": 0,
                "records": [_record(L0Milestone.BROWSER_EOT_RECEIPT, offset=10)],
                "failure_reason": "browser_incomplete",
            }
        )

    assert not (tmp_path / "browser.jsonl").exists()
    assert not (tmp_path / "batch-attempts.ndjson").exists()
    assert not (tmp_path / "d095-report.json").exists()
    assert json.loads((tmp_path / "run-labels.json").read_text(encoding="utf-8")) == {
        "schema_version": "live-voice.l0-run-labels.v1",
        "measurement": "disabled",
    }
    assert not list(tmp_path.glob("live-voice-l0-browser-*.jsonl"))
    assert state.next_job() == job


def test_concurrent_next_requests_linearize_to_one_exact_job(tmp_path: Path) -> None:
    state = _state(tmp_path, temperature="cold")
    barrier = threading.Barrier(8)
    jobs: list[dict[str, object]] = []

    def request_job() -> None:
        barrier.wait()
        jobs.append(state.next_job())

    threads = [threading.Thread(target=request_job) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert len(jobs) == 8
    assert len({str(job["job_id"]) for job in jobs}) == 1
    assert len({int(job["labels"]["sample_index"]) for job in jobs}) == 1


def _attempt(temperature: str, metric: str, index: int) -> dict[str, object]:
    return {
        "schema_version": BATCH_ATTEMPT_VERSION,
        "epoch_id": f"{index + (0 if temperature == 'cold' else 80):032x}",
        "temperature": temperature,
        "metric": metric,
        "profile_id": f"ordinary-chrome-prerecorded-{temperature}",
        "scenario_id": (
            "short-no-tool-zh" if metric == "first_audio" else "playout-barge-in-zh"
        ),
        "sample_index": index,
        "browser_record_count": 10,
        "browser_dropped_record_count": 0,
        "automated_browser_complete": True,
        "classification": "success" if metric == "first_audio" else "cancelled",
        "eligible": True,
        "reason": "eligible",
    }


def test_final_report_requires_both_metrics_and_unique_cold_launcher_epochs() -> None:
    attempts = [
        _attempt(temperature, metric, index + (0 if metric == "first_audio" else 20))
        for temperature in ("cold", "warm")
        for metric in ("first_audio", "barge_in")
        for index in range(20)
    ]
    aggregate = {
        "profiles": [
            {
                "profile_id": f"ordinary-chrome-prerecorded-{temperature}",
                "percentiles": {
                    "speech_end_to_webaudio_started_ms": {
                        "sample_count": 20,
                        "p50_ms": 2500 if temperature == "cold" else 2000,
                        "p95_ms": 3500 if temperature == "cold" else 3000,
                    },
                    "stop_to_silence_ms": {
                        "sample_count": 20,
                        "p50_ms": 70 if temperature == "cold" else 60,
                        "p95_ms": 90 if temperature == "cold" else 80,
                    },
                },
            }
            for temperature in ("cold", "warm")
        ]
    }
    report = build_d095_report(
        aggregate=aggregate,
        attempts=attempts,
        source_head=SOURCE_HEAD,
        environment_ref=ENVIRONMENT_REF,
        configuration_sha256=CONFIGURATION_SHA256,
        corpus_sha256="e" * 64,
        target=20,
    )
    assert report["complete"] is True
    assert report["cold_minus_warm_ms"] == {
        "speech_end_to_webaudio_started_p50": 500.0,
        "speech_end_to_webaudio_started_p95": 500.0,
        "stop_to_silence_p50": 10.0,
        "stop_to_silence_p95": 10.0,
    }

    duplicate = [dict(item) for item in attempts]
    duplicate[1]["epoch_id"] = duplicate[0]["epoch_id"]
    failed = build_d095_report(
        aggregate=aggregate,
        attempts=duplicate,
        source_head=SOURCE_HEAD,
        environment_ref=ENVIRONMENT_REF,
        configuration_sha256=CONFIGURATION_SHA256,
        corpus_sha256="e" * 64,
        target=20,
    )
    assert failed["complete"] is False
    cold = next(item for item in failed["profiles"] if item["temperature"] == "cold")
    assert cold["cold_launcher_epochs_unique"] is False


def test_loopback_http_requires_exact_origin_and_nonce(tmp_path: Path) -> None:
    state = _state(tmp_path, temperature="cold")
    server = _Server(("127.0.0.1", 0), _Handler)
    server.state = state
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request("GET", "/v1/session", headers={"Origin": "http://localhost:5173"})
        assert connection.getresponse().status == 403
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "GET",
            "/v1/session",
            headers={
                "Origin": "http://localhost:5173",
                "X-L0-Batch-Nonce": "d" * 32,
            },
        )
        response = connection.getresponse()
        assert response.status == 200
        payload = json.loads(response.read())
        assert payload["browser_mode"] == "ordinary-installed-chrome"
        assert "nonce" not in payload
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "GET",
            "/v1/audio/short",
            headers={
                "Origin": "http://localhost:5173",
                "X-L0-Batch-Nonce": "d" * 32,
            },
        )
        response = connection.getresponse()
        assert response.status == 200
        assert response.read() == b"short"
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_launcher_routes_ordinary_chrome_without_managed_isolated_profile() -> None:
    launcher = Path("scripts/live_voice/start_hands_free_demo.ps1").read_text(
        encoding="utf-8-sig"
    )
    supervisor = Path(
        "scripts/live_voice/run_l0_ordinary_chrome_series.ps1"
    ).read_text(encoding="utf-8-sig")
    assert supervisor.isascii(), "Windows PowerShell 5.1 requires BOM-less scripts here to be ASCII"
    assert "[switch]$L0OrdinaryChromeBatch" in launcher
    assert "if (-not $NoBrowser -and $L0OrdinaryChromeBatch)" in launcher
    assert "Start-IsolatedChrome" in launcher
    ordinary_block = launcher.split(
        "if (-not $NoBrowser -and $L0OrdinaryChromeBatch)", 1
    )[1].split("} elseif (-not $NoBrowser)", 1)[0]
    assert "Start-IsolatedChrome" not in ordinary_block
    assert "--new-tab" in ordinary_block
    assert "--user-data-dir" not in ordinary_block
    assert "-WindowStyle Hidden" in launcher
    assert "-L0ReuseValidatedBuild" in supervisor
    assert "-NoBrowser" in supervisor
    assert "Wait-Epoch" in supervisor


def test_launcher_waits_for_live_voice_route_registration_after_ports_open() -> None:
    launcher = Path("scripts/live_voice/start_hands_free_demo.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "function Wait-LiveVoiceDeploymentLog" in launcher
    deployment_probe = launcher.split(
        "function Wait-LiveVoiceDeploymentLog", 1
    )[1].split("$l0BatchProcess = $null", 1)[0]
    assert "Start-Sleep -Milliseconds 250" in deployment_probe
    assert "[DateTime]::UtcNow -lt $Deadline" in deployment_probe
    assert "LiveVoice(P3|Product).*failed closed" in deployment_probe
    assert (
        "$logText = Wait-LiveVoiceDeploymentLog -Path $logPath -Deadline $deadline"
        in launcher
    )
