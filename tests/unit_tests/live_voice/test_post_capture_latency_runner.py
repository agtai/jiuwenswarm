from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
import time
from types import SimpleNamespace
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

from jiuwenswarm.server.live_voice.latency_probe import (
    BATCH_SCHEMA_VERSION,
    MARK_SCHEMA_VERSION,
    LatencyBatch,
    LatencyMark,
    load_latency_run_config,
)


def _load_runner(name: str):
    module_path = Path(__file__).parents[3] / "scripts" / "live_voice" / "post_capture_latency_runner.py"
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_wav(
    path: Path,
    *,
    channels: int = 1,
    sample_width: int = 2,
    sample_rate: int = 48_000,
    frame_count: int = 8,
) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(sample_width)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * channels * frame_count)


def _write_manifest(path: Path, wav_path: Path, *, digest: str, sample_rate: int = 48_000) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "live-voice.fixed-audio-fixture.v0",
                "fixture_profile_id": "en-v1-fixed-wav",
                "cases": [
                    {
                        "profile_id": "dialogue_no_tool",
                        "input_case_id": "dialogue-paris-en-v1",
                        "wav_path": wav_path.name,
                        "sha256": digest,
                        "sample_rate_hz": sample_rate,
                        "expected_transcript_sha256": "c" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_run(
    path: Path,
    *,
    intended_attempts: int = 1,
    profile_id: str = "dialogue_no_tool",
    input_case_id: str = "dialogue-paris-en-v1",
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "live-voice.latency-run.v1",
                "run_id": "run-a",
                "git_commit": "a" * 40,
                "source_state": "clean",
                "environment_profile": "windows-wsl2",
                "browser_family_and_version": "chrome-151",
                "browser_os_class": "windows-11",
                "gateway_runtime_class": "wsl2-python-3.11",
                "agent_runtime_class": "wsl2-python-3.11",
                "stt_provider_and_model": "openai-gpt-4o-mini-transcribe",
                "tts_provider_and_model": "openai-gpt-4o-mini-tts-marin",
                "audio_format": "pcm16-48000-mono",
                "vad_configuration": "server-vad-1200ms",
                "playout_configuration": "webaudio-lead-1000ms",
                "allowlisted_feature_flags": {
                    "formal_integrated_web": True,
                    "formal_integrated_p1": True,
                    "latency_probe": True,
                    "post_capture_benchmark": True,
                },
                "cold_or_warm": "warm",
                "input_case_ids": [input_case_id],
                "profile_ids": [profile_id],
                "intended_attempts": intended_attempts,
                "required_successes": 1,
                "experiment": None,
                "optimization_track": "post_capture_pipeline",
                "benchmark_lane": "controlled_browser_fixture",
                "fixture_profile_id": "en-v1-fixed-wav",
            }
        ),
        encoding="utf-8",
    )


def _write_complete_round(
    run_dir: Path,
    round_index: int,
    *,
    append: bool,
    profile_id: str = "dialogue_no_tool",
    input_case_id: str = "dialogue-paris-en-v1",
    include_tool_marks: bool = False,
) -> None:
    def mark(component: str, point: str, index: int, timestamp: float) -> LatencyMark:
        return LatencyMark(
            schema_version=MARK_SCHEMA_VERSION,
            run_id="run-a",
            profile_id=profile_id,
            input_case_id=input_case_id,
            round_index=round_index,
            source_instance_id=f"{component}-source",
            mark_index=index,
            component=component,
            clock_domain_id=f"{component}-clock",
            point=point,
            monotonic_ms=timestamp,
            uncertainty_ms=1.0 if point == "browser.playout_first_frame_started_estimate" else None,
            outcome="observed",
            reason_code=None,
            correlation_id=f"correlation-{round_index}",
            interaction_id=f"interaction-{round_index}",
            activation_id=f"activation-{round_index}",
            activation_generation=round_index + 1,
            turn_id=f"turn-{round_index}",
            response_id=f"response-{round_index}",
            response_generation=round_index + 1,
            task_id=None,
        )

    common = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "run_id": "run-a",
        "profile_id": profile_id,
        "input_case_id": input_case_id,
        "round_index": round_index,
        "terminal_outcome": "completed",
    }
    batches = (
        LatencyBatch(
            batch_id=f"browser-{round_index}", source_instance_id="browser-source",
            component="browser", phase="browser_round",
            marks=tuple(
                mark("browser", point, index, timestamp)
                for index, (point, timestamp) in enumerate(
                    (
                        ("browser.eot_received", 100.0),
                        ("browser.stt_final_received", 200.0),
                        ("browser.commit_submit_started", 210.0),
                        ("browser.presentation_received", 600.0),
                        ("browser.tts_request_started", 610.0),
                        ("browser.downlink_first_frame_received", 760.0),
                        ("browser.playout_first_frame_scheduled", 770.0),
                        ("browser.playout_first_frame_started_estimate", 800.0),
                        ("browser.playout_completed", 880.0),
                        ("browser.playout_ack_received", 900.0),
                    )
                )
            ),
            **common,
        ),
        LatencyBatch(
            batch_id=f"stt-{round_index}", source_instance_id="gateway-source",
            component="gateway", phase="gateway_stt",
            marks=tuple(
                mark("gateway", point, index, timestamp)
                for index, (point, timestamp) in enumerate(
                    (
                        ("gateway.stt_request_started", 110.0),
                        ("gateway.stt_provider_transport_open", 120.0),
                        ("gateway.stt_session_ready", 130.0),
                        ("gateway.vad_speech_stopped", 170.0),
                        ("gateway.eot_control_sent", 180.0),
                        ("gateway.stt_final_available", 190.0),
                    )
                )
            ),
            **common,
        ),
        LatencyBatch(
            batch_id=f"tts-{round_index}", source_instance_id="gateway-source",
            component="gateway", phase="gateway_tts",
            marks=tuple(
                mark("gateway", point, index, timestamp)
                for index, (point, timestamp) in enumerate(
                    (
                        ("gateway.tts_request_received", 700.0),
                        ("gateway.tts_provider_transport_open", 710.0),
                        ("gateway.tts_provider_first_audio", 730.0),
                        ("gateway.downlink_ticket_ready", 740.0),
                        ("gateway.downlink_first_frame_sent", 750.0),
                    )
                )
            ),
            **common,
        ),
        LatencyBatch(
            batch_id=f"agent-{round_index}", source_instance_id="agent_server-source",
            component="agent_server", phase="agent_foreground",
            marks=tuple(
                mark("agent_server", point, index, timestamp)
                for index, (point, timestamp) in enumerate(
                    (
                        ("agent.commit_submit_received", 300.0),
                        ("agent.commit_accepted", 310.0),
                        ("agent.route_resolved", 320.0),
                        ("agent.agent_started", 330.0),
                        *(
                            (
                                ("agent.tool_execution_started", 400.0),
                                ("agent.tool_execution_completed", 450.0),
                            )
                            if include_tool_marks
                            else ()
                        ),
                        ("agent.agent_final", 500.0),
                        ("agent.presentation_produced", 510.0),
                        ("agent.presentation_dispatched", 520.0),
                    )
                )
            ),
            **common,
        ),
    )
    mode = "ab" if append else "wb"
    with (run_dir / "browser.jsonl").open(mode) as handle:
        handle.write(batches[0].canonical_bytes() + b"\n")
    with (run_dir / "gateway.jsonl").open(mode) as handle:
        handle.write(batches[1].canonical_bytes() + b"\n" + batches[2].canonical_bytes() + b"\n")
    with (run_dir / "agent.jsonl").open(mode) as handle:
        handle.write(batches[3].canonical_bytes() + b"\n")


def test_fixture_manifest_rejects_a_wav_whose_content_does_not_match_the_declared_hash(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_hash")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav)
    manifest = tmp_path / "fixture.json"
    _write_manifest(manifest, wav, digest="a" * 64)

    try:
        runner.load_fixture_manifest(manifest, "en-v1-fixed-wav")
    except ValueError as error:
        assert str(error) == "FIXTURE_HASH_MISMATCH"
    else:
        raise AssertionError("altered fixture bytes must fail closed")


def test_fixture_manifest_loads_only_a_closed_semantic_transcript_digest(
    tmp_path: Path,
) -> None:
    runner = _load_runner("post_capture_latency_runner_semantic_manifest")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav)
    manifest = tmp_path / "fixture.json"
    _write_manifest(
        manifest,
        wav,
        digest=hashlib.sha256(wav.read_bytes()).hexdigest(),
    )

    cases = runner.load_fixture_manifest(manifest, "en-v1-fixed-wav")

    assert cases[0].expected_transcript_sha256 == "c" * 64


def test_fixture_manifest_rejects_audio_that_is_not_pcm16_mono_at_the_declared_rate(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_wav")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav, channels=2)
    manifest = tmp_path / "fixture.json"
    _write_manifest(manifest, wav, digest=hashlib.sha256(wav.read_bytes()).hexdigest())

    try:
        runner.load_fixture_manifest(manifest, "en-v1-fixed-wav")
    except ValueError as error:
        assert str(error) == "FIXTURE_WAV_INVALID"
    else:
        raise AssertionError("non-mono fixture must fail closed")


def test_fixture_manifest_requires_exact_non_boolean_48khz_rate(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_rate")
    for index, rate in enumerate((True, 44_100)):
        wav = tmp_path / f"fixture-{index}.wav"
        _write_wav(wav, sample_rate=48_000 if rate is True else rate)
        manifest = tmp_path / f"fixture-{index}.json"
        _write_manifest(
            manifest,
            wav,
            digest=hashlib.sha256(wav.read_bytes()).hexdigest(),
            sample_rate=rate,
        )
        try:
            runner.load_fixture_manifest(manifest, "en-v1-fixed-wav")
        except ValueError as error:
            assert str(error) == "FIXTURE_WAV_INVALID"
        else:
            raise AssertionError("fixture sample rate must be the exact 48 kHz integer")


def test_fixture_manifest_rejects_wav_larger_than_four_mib(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_size")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav, frame_count=2 * 1024 * 1024 + 1)
    manifest = tmp_path / "fixture.json"
    _write_manifest(manifest, wav, digest=hashlib.sha256(wav.read_bytes()).hexdigest())

    try:
        runner.load_fixture_manifest(manifest, "en-v1-fixed-wav")
    except ValueError as error:
        assert str(error) == "FIXTURE_WAV_TOO_LARGE"
    else:
        raise AssertionError("oversized fixture must fail closed")


def test_fixture_manifest_loader_rejects_paths_outside_its_manifest_root(tmp_path: Path) -> None:
    module_path = Path(__file__).parents[3] / "scripts" / "live_voice" / "post_capture_latency_runner.py"
    spec = importlib.util.spec_from_file_location("post_capture_latency_runner", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    manifest = tmp_path / "fixture.json"
    manifest.write_text('{"schema_version":"live-voice.fixed-audio-fixture.v0","fixture_profile_id":"en-v1-fixed-wav","cases":[{"profile_id":"dialogue_no_tool","input_case_id":"dialogue-paris-en-v1","wav_path":"../private.wav","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","sample_rate_hz":48000,"expected_transcript_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}]}', encoding="utf-8")

    try:
        module.load_fixture_manifest(manifest, "en-v1-fixed-wav")
    except ValueError as error:
        assert str(error) == "FIXTURE_PATH_INVALID"
    else:
        raise AssertionError("path traversal must fail closed")


def test_loopback_fixture_server_rejects_foreign_origin_and_never_serves_unknown_case(tmp_path: Path) -> None:
    module_path = Path(__file__).parents[3] / "scripts" / "live_voice" / "post_capture_latency_runner.py"
    spec = importlib.util.spec_from_file_location("post_capture_latency_runner_server", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    wav = tmp_path / "fixture.wav"
    wav.write_bytes(b"RIFFfixture")
    case = module.FixtureCase("dialogue_no_tool", "dialogue-paris-en-v1", wav, "a" * 64, 48000)
    server = module.create_loopback_fixture_server("http://localhost:5173", (case,))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/fixture/dialogue-paris-en-v1.wav"
        request = urllib.request.Request(url, headers={"Origin": "http://foreign.test"})
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("foreign origin must fail")
    finally:
        server.shutdown()
        server.server_close()


def test_loopback_fixture_server_rechecks_hash_before_serving_bytes(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_fixture_toctou")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav)
    manifest = tmp_path / "fixture.json"
    _write_manifest(manifest, wav, digest=hashlib.sha256(wav.read_bytes()).hexdigest())
    cases = runner.load_fixture_manifest(manifest, "en-v1-fixed-wav")
    server = runner.create_loopback_fixture_server("http://localhost:5173", cases)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    wav.write_bytes(b"RIFF altered private bytes")
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/fixture/dialogue-paris-en-v1.wav",
        headers={"Origin": "http://localhost:5173"},
    )
    try:
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            assert error.code == 409
        else:
            raise AssertionError("changed fixture must not be served")
    finally:
        server.shutdown()
        server.server_close()


def test_loopback_fixture_server_claims_one_attempt_before_serving_audio(
    tmp_path: Path,
) -> None:
    runner = _load_runner("post_capture_latency_runner_fixture_claim")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav)
    digest = hashlib.sha256(wav.read_bytes()).hexdigest()
    case = runner.FixtureCase(
        "dialogue_no_tool",
        "dialogue-paris-en-v1",
        wav,
        digest,
        48_000,
    )
    identity = runner.AttemptIdentity(
        "run-20260820-a",
        "dialogue_no_tool",
        "dialogue-paris-en-v1",
        0,
    )
    server = runner.create_loopback_fixture_server(
        "http://localhost:5173",
        (case,),
        identity,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/fixture/dialogue-paris-en-v1.wav",
        headers={"Origin": "http://localhost:5173"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            assert response.status == 200
            assert (
                response.headers["X-Live-Voice-Transcript-Sha256"]
                == case.expected_transcript_sha256
            )
            assert (
                response.headers["Access-Control-Expose-Headers"]
                == "X-Live-Voice-Transcript-Sha256"
            )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            assert error.code == 409
        else:
            raise AssertionError("a second tab must lose before receiving fixture bytes")
    finally:
        server.shutdown()
        server.server_close()


def test_loopback_server_rejects_non_loopback_web_origin_before_binding(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_origin")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav)
    case = runner.FixtureCase("dialogue_no_tool", "dialogue-paris-en-v1", wav, "a" * 64, 48_000)

    try:
        runner.create_loopback_fixture_server("https://private.example", (case,))
    except ValueError as error:
        assert str(error) == "WEB_ORIGIN_INVALID"
    else:
        raise AssertionError("foreign Web origin must fail before server allocation")


def test_loopback_result_endpoint_accepts_one_exact_content_free_attempt(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_result")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav)
    case = runner.FixtureCase(
        "dialogue_no_tool",
        "dialogue-paris-en-v1",
        wav,
        hashlib.sha256(wav.read_bytes()).hexdigest(),
        48_000,
    )
    identity = runner.AttemptIdentity(
        "run-20260820-a",
        "dialogue_no_tool",
        "dialogue-paris-en-v1",
        0,
    )
    server = runner.create_loopback_fixture_server("http://localhost:5173", (case,), identity)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    body = json.dumps(
        {
            "schema_version": "live-voice.post-capture-result.v0",
            "run_id": "run-20260820-a",
            "profile_id": "dialogue_no_tool",
            "input_case_id": "dialogue-paris-en-v1",
            "round_index": 0,
            "outcome": "completed",
        }
    ).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/result",
        data=body,
        headers={"Origin": "http://localhost:5173", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        fixture = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/fixture/dialogue-paris-en-v1.wav",
            headers={"Origin": "http://localhost:5173"},
        )
        with urllib.request.urlopen(fixture) as response:
            assert response.status == 200
        with urllib.request.urlopen(request) as response:
            assert response.status == 204
        assert server.received_result == runner.AttemptResult(identity, "completed")
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            assert error.code == 409
        else:
            raise AssertionError("duplicate result must fail closed")
    finally:
        server.shutdown()
        server.server_close()


def test_loopback_result_endpoint_accepts_only_the_browser_json_cors_preflight(
    tmp_path: Path,
) -> None:
    runner = _load_runner("post_capture_latency_runner_preflight")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav)
    case = runner.FixtureCase(
        "dialogue_no_tool",
        "dialogue-paris-en-v1",
        wav,
        "a" * 64,
        48_000,
    )
    server = runner.create_loopback_fixture_server(
        "http://localhost:5173",
        (case,),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/result",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
        method="OPTIONS",
    )
    try:
        with urllib.request.urlopen(request) as response:
            assert response.status == 204
            assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
            assert response.headers["Access-Control-Allow-Methods"] == "POST"
            assert response.headers["Access-Control-Allow-Headers"] == "Content-Type"

        invalid = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/result",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization, content-type",
            },
            method="OPTIONS",
        )
        try:
            urllib.request.urlopen(invalid)
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("preflight with an extra header must fail closed")
    finally:
        server.shutdown()
        server.server_close()


def test_loopback_result_endpoint_rejects_boolean_round_identity(
    tmp_path: Path,
) -> None:
    runner = _load_runner("post_capture_latency_runner_boolean_round")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav)
    case = runner.FixtureCase(
        "dialogue_no_tool",
        "dialogue-paris-en-v1",
        wav,
        hashlib.sha256(wav.read_bytes()).hexdigest(),
        48_000,
    )
    identity = runner.AttemptIdentity(
        "run-20260820-a",
        "dialogue_no_tool",
        "dialogue-paris-en-v1",
        1,
    )
    server = runner.create_loopback_fixture_server(
        "http://localhost:5173",
        (case,),
        identity,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fixture = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/fixture/dialogue-paris-en-v1.wav",
        headers={"Origin": "http://localhost:5173"},
    )
    body = json.dumps(
        {
            "schema_version": "live-voice.post-capture-result.v0",
            "run_id": identity.run_id,
            "profile_id": identity.profile_id,
            "input_case_id": identity.input_case_id,
            "round_index": True,
            "outcome": "completed",
        }
    ).encode()
    result = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/result",
        data=body,
        headers={
            "Origin": "http://localhost:5173",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(fixture) as response:
            assert response.status == 200
        try:
            urllib.request.urlopen(result)
        except urllib.error.HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("JSON boolean cannot impersonate round one")
        assert server.received_result is None
    finally:
        server.shutdown()
        server.server_close()


def test_browser_command_is_a_closed_argv_with_exactly_one_url_placeholder() -> None:
    runner = _load_runner("post_capture_latency_runner_browser")
    url = "http://localhost:5173/project/web_benchmark_session?run=public"

    assert runner.parse_browser_command_json(
        '["chromium","--user-data-dir=/tmp/benchmark-profile","{url}"]',
        url,
    ) == (
        "chromium",
        "--user-data-dir=/tmp/benchmark-profile",
        url,
    )
    assert runner.parse_browser_command_json("[]", url) is None
    for invalid in (
        '"chromium {url}"',
        '["chromium"]',
        '["chromium","{url}","{url}"]',
        '["chromium",7,"{url}"]',
    ):
        try:
            runner.parse_browser_command_json(invalid, url)
        except ValueError as error:
            assert str(error) == "BROWSER_COMMAND_INVALID"
        else:
            raise AssertionError("unsafe Browser command must fail closed")


def test_benchmark_url_targets_the_real_saved_chat_route_with_closed_query() -> None:
    runner = _load_runner("post_capture_latency_runner_url")
    identity = runner.AttemptIdentity(
        "run-20260820-a",
        "dialogue_no_tool",
        "dialogue-paris-en-v1",
        3,
    )

    url = runner.build_benchmark_url(
        "http://localhost:5173",
        "web_benchmark_session",
        identity,
        41731,
        1_000,
    )

    parsed = urllib.parse.urlsplit(url)
    assert parsed.scheme == "http"
    assert parsed.netloc == "localhost:5173"
    assert parsed.path == "/chat/web_benchmark_session"
    assert urllib.parse.parse_qs(parsed.query) == {
        "live_voice_post_capture_benchmark": ["1"],
        "run_id": ["run-20260820-a"],
        "profile_id": ["dialogue_no_tool"],
        "input_case_id": ["dialogue-paris-en-v1"],
        "round_index": ["3"],
        "session_id": ["web_benchmark_session"],
        "fixture_url": ["http://127.0.0.1:41731/fixture/dialogue-paris-en-v1.wav"],
        "result_url": ["http://127.0.0.1:41731/result"],
        "start_delay_ms": ["1000"],
    }


def test_attempt_supervisor_uses_no_shell_and_terminates_only_its_owned_browser(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_supervisor")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav)
    case = runner.FixtureCase("dialogue_no_tool", "dialogue-paris-en-v1", wav, "a" * 64, 48_000)
    identity = runner.AttemptIdentity("run-a", "dialogue_no_tool", "dialogue-paris-en-v1", 0)
    server = runner.create_loopback_fixture_server("http://localhost:5173", (case,), identity)
    calls = []

    class FakeProcess:
        def __init__(self) -> None:
            self.terminated = 0

        def poll(self):
            return None

        def terminate(self) -> None:
            self.terminated += 1

        def wait(self, timeout: float):
            calls.append(("wait", timeout))
            return 0

    process = FakeProcess()

    def popen(argv, *, shell):
        calls.append(("popen", tuple(argv), shell))
        assert server.claim_fixture(case)
        assert server.accept_result(runner.AttemptResult(identity, "completed"))
        return process

    result = runner.supervise_browser_attempt(
        server,
        ("chromium", "http://localhost:5173/chat/web"),
        timeout_seconds=2,
        popen_factory=popen,
    )

    assert result == runner.AttemptResult(identity, "completed")
    assert calls[0] == ("popen", ("chromium", "http://localhost:5173/chat/web"), False)
    assert process.terminated == 1


def test_completed_http_result_without_formal_shards_receives_no_attempt_credit(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_artifacts")
    run_dir = tmp_path / "run-a"
    run_dir.mkdir()
    _write_run(run_dir / "run.json")
    identity = runner.AttemptIdentity("run-a", "dialogue_no_tool", "dialogue-paris-en-v1", 0)

    try:
        runner.validate_attempt_artifacts(run_dir, identity)
    except ValueError as error:
        assert str(error) == "ARTIFACTS_INCOMPLETE"
    else:
        raise AssertionError("HTTP result alone must never grant attempt credit")


def test_empty_formal_shards_receive_no_attempt_credit(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_empty_artifacts")
    run_dir = tmp_path / "run-a"
    run_dir.mkdir()
    _write_run(run_dir / "run.json")
    common = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "run_id": "run-a",
        "profile_id": "dialogue_no_tool",
        "input_case_id": "dialogue-paris-en-v1",
        "round_index": 0,
        "terminal_outcome": "completed",
        "marks": (),
    }
    batches = (
        LatencyBatch(batch_id="browser", source_instance_id="browser-source", component="browser", phase="browser_round", **common),
        LatencyBatch(batch_id="stt", source_instance_id="gateway-source", component="gateway", phase="gateway_stt", **common),
        LatencyBatch(batch_id="tts", source_instance_id="gateway-source", component="gateway", phase="gateway_tts", **common),
        LatencyBatch(batch_id="agent", source_instance_id="agent-source", component="agent_server", phase="agent_foreground", **common),
    )
    (run_dir / "browser.jsonl").write_bytes(batches[0].canonical_bytes() + b"\n")
    (run_dir / "gateway.jsonl").write_bytes(batches[1].canonical_bytes() + b"\n" + batches[2].canonical_bytes() + b"\n")
    (run_dir / "agent.jsonl").write_bytes(batches[3].canonical_bytes() + b"\n")
    identity = runner.AttemptIdentity("run-a", "dialogue_no_tool", "dialogue-paris-en-v1", 0)

    try:
        runner.validate_attempt_artifacts(run_dir, identity)
    except ValueError as error:
        assert str(error) == "ARTIFACTS_FAILED"
    else:
        raise AssertionError("empty diagnostic shards must fail closed")


def test_completed_initial_only_shards_do_not_receive_attempt_credit(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_complete_artifacts")
    run_dir = tmp_path / "run-a"
    run_dir.mkdir()
    _write_run(run_dir / "run.json")

    def mark(component: str, point: str, index: int, timestamp: float) -> LatencyMark:
        return LatencyMark(
            schema_version=MARK_SCHEMA_VERSION,
            run_id="run-a",
            profile_id="dialogue_no_tool",
            input_case_id="dialogue-paris-en-v1",
            round_index=0,
            source_instance_id=f"{component}-source",
            mark_index=index,
            component=component,
            clock_domain_id=f"{component}-clock",
            point=point,
            monotonic_ms=timestamp,
            uncertainty_ms=1.0 if point == "browser.playout_first_frame_started_estimate" else None,
            outcome="observed",
            reason_code=None,
            correlation_id="correlation-1",
            interaction_id="interaction-1",
            activation_id="activation-1",
            activation_generation=1,
            turn_id="turn-1",
            response_id="response-1",
            response_generation=1,
            task_id=None,
        )

    common = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "run_id": "run-a",
        "profile_id": "dialogue_no_tool",
        "input_case_id": "dialogue-paris-en-v1",
        "round_index": 0,
        "terminal_outcome": "completed",
    }
    browser = LatencyBatch(
        batch_id="browser",
        source_instance_id="browser-source",
        component="browser",
        phase="browser_round",
        marks=(
            mark("browser", "browser.eot_received", 0, 100.0),
            mark("browser", "browser.playout_first_frame_started_estimate", 1, 900.0),
        ),
        **common,
    )
    stt = LatencyBatch(
        batch_id="stt",
        source_instance_id="gateway-source",
        component="gateway",
        phase="gateway_stt",
        marks=(mark("gateway", "gateway.stt_request_started", 0, 110.0),),
        **common,
    )
    tts = LatencyBatch(
        batch_id="tts",
        source_instance_id="gateway-source",
        component="gateway",
        phase="gateway_tts",
        marks=(mark("gateway", "gateway.tts_request_received", 0, 700.0),),
        **common,
    )
    agent = LatencyBatch(
        batch_id="agent",
        source_instance_id="agent_server-source",
        component="agent_server",
        phase="agent_foreground",
        marks=(mark("agent_server", "agent.commit_submit_received", 0, 300.0),),
        **common,
    )
    (run_dir / "browser.jsonl").write_bytes(browser.canonical_bytes() + b"\n")
    (run_dir / "gateway.jsonl").write_bytes(stt.canonical_bytes() + b"\n" + tts.canonical_bytes() + b"\n")
    (run_dir / "agent.jsonl").write_bytes(agent.canonical_bytes() + b"\n")
    identity = runner.AttemptIdentity("run-a", "dialogue_no_tool", "dialogue-paris-en-v1", 0)

    try:
        runner.validate_attempt_artifacts(run_dir, identity)
    except ValueError as error:
        assert str(error) == "ARTIFACTS_FAILED"
    else:
        raise AssertionError("initial-only shards cannot prove the authoritative journey")


def test_later_completed_round_keeps_credit_when_report_contains_prior_success(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_repeated_artifacts")
    run_dir = tmp_path / "run-a"
    run_dir.mkdir()
    _write_run(run_dir / "run.json", intended_attempts=2)
    _write_complete_round(run_dir, 0, append=False)
    _write_complete_round(run_dir, 1, append=True)
    identity = runner.AttemptIdentity("run-a", "dialogue_no_tool", "dialogue-paris-en-v1", 1)

    runner.validate_attempt_artifacts(run_dir, identity)

    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    response_total = next(
        segment
        for segment in report["profiles"][0]["segments"]
        if segment["segment_id"] == "response_total"
    )
    assert response_total["successful_samples"] == 2


def test_tool_profile_requires_authoritative_tool_marks_before_attempt_credit(
    tmp_path: Path,
) -> None:
    runner = _load_runner("post_capture_latency_runner_tool_artifacts")
    run_dir = tmp_path / "run-tool"
    run_dir.mkdir()
    _write_run(
        run_dir / "run.json",
        profile_id="dialogue_with_tool",
        input_case_id="tool-git-status-en-v1",
    )
    identity = runner.AttemptIdentity(
        "run-a",
        "dialogue_with_tool",
        "tool-git-status-en-v1",
        0,
    )
    _write_complete_round(
        run_dir,
        0,
        append=False,
        profile_id="dialogue_with_tool",
        input_case_id="tool-git-status-en-v1",
        include_tool_marks=False,
    )
    try:
        runner.validate_attempt_artifacts(run_dir, identity)
    except ValueError as error:
        assert str(error) == "ARTIFACTS_FAILED"
    else:
        raise AssertionError("a tool profile without real Tool marks must fail closed")

    _write_complete_round(
        run_dir,
        0,
        append=False,
        profile_id="dialogue_with_tool",
        input_case_id="tool-git-status-en-v1",
        include_tool_marks=True,
    )
    runner.validate_attempt_artifacts(run_dir, identity)


def test_artifact_settlement_waits_for_a_delayed_partial_append_and_times_out_closed(
    tmp_path: Path,
) -> None:
    runner = _load_runner("post_capture_latency_runner_settlement")
    run_dir = tmp_path / "run-a"
    run_dir.mkdir()
    _write_run(run_dir / "run.json")
    staged = tmp_path / "staged"
    staged.mkdir()
    _write_complete_round(staged, 0, append=False)
    browser_bytes = (staged / "browser.jsonl").read_bytes()
    split = len(browser_bytes) // 2
    (run_dir / "browser.jsonl").write_bytes(browser_bytes[:split])
    identity = runner.AttemptIdentity(
        "run-a",
        "dialogue_no_tool",
        "dialogue-paris-en-v1",
        0,
    )

    def settle() -> None:
        time.sleep(0.05)
        with (run_dir / "browser.jsonl").open("ab") as handle:
            handle.write(browser_bytes[split:])
        (run_dir / "gateway.jsonl").write_bytes(
            (staged / "gateway.jsonl").read_bytes()
        )
        (run_dir / "agent.jsonl").write_bytes(
            (staged / "agent.jsonl").read_bytes()
        )

    writer = threading.Thread(target=settle)
    writer.start()
    runner.wait_for_attempt_artifacts(
        run_dir,
        identity,
        timeout_seconds=1.0,
        poll_interval_seconds=0.01,
    )
    writer.join(timeout=1)
    assert (run_dir / "report.json").is_file()

    empty = tmp_path / "empty"
    empty.mkdir()
    _write_run(empty / "run.json")
    try:
        runner.wait_for_attempt_artifacts(
            empty,
            identity,
            timeout_seconds=0.02,
            poll_interval_seconds=0.005,
        )
    except ValueError as error:
        assert str(error) == "ARTIFACTS_SETTLEMENT_TIMEOUT"
    else:
        raise AssertionError("missing exporter shards must time out closed")


def test_prepare_run_cli_writes_one_closed_v1_manifest_and_refuses_overwrite(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_prepare")
    output = tmp_path / "run-a" / "run.json"
    argv = [
        "prepare-run",
        "--output", str(output),
        "--git-commit", "a" * 40,
        "--source-state", "clean",
        "--fixture-profile-id", "en-v1-fixed-wav",
        "--profile-id", "dialogue_no_tool",
        "--input-case-id", "dialogue-paris-en-v1",
        "--environment-profile", "windows-chrome-wsl2",
        "--browser-profile", "chrome-151",
        "--browser-os-class", "windows-11",
        "--gateway-profile", "wsl2-python-3.11",
        "--agent-profile", "wsl2-python-3.11",
        "--stt-profile", "openai-gpt-4o-mini-transcribe",
        "--tts-profile", "openai-gpt-4o-mini-tts-marin",
        "--audio-profile", "pcm16-48000-mono",
        "--vad-profile", "server-vad-1200ms",
        "--playout-profile", "webaudio-lead-1000ms",
        "--cold-or-warm", "warm",
        "--intended-attempts", "1",
        "--required-successes", "1",
    ]

    assert runner.main(argv) == 0
    run = load_latency_run_config(output)
    assert run.run_id == "run-a"
    assert run.optimization_track == "post_capture_pipeline"
    assert run.benchmark_lane == "controlled_browser_fixture"
    assert run.browser_os_class == "windows-11"
    assert runner.main(argv) == 2

    experiment = tmp_path / "experiment.json"
    experiment.write_text(
        json.dumps(
            {
                "experiment_id": "tts-first-audio-v1",
                "target_segment": "tts_request_to_first_downlink",
                "target_statistic": "p95_ms",
                "minimum_improvement_ms": 25.0,
                "response_total_minimum_improvement_ms": 0.0,
                "guardrails": [
                    {
                        "metric": "fallback_rate",
                        "segment_id": None,
                        "maximum_regression": 0.0,
                    }
                ],
                "declared_experiment_points": [],
            }
        ),
        encoding="utf-8",
    )
    candidate_output = tmp_path / "candidate" / "run.json"
    candidate_argv = argv.copy()
    candidate_argv[candidate_argv.index("--output") + 1] = str(candidate_output)
    candidate_argv.extend(("--experiment-json", str(experiment)))

    assert runner.main(candidate_argv) == 0
    candidate = load_latency_run_config(candidate_output)
    assert candidate.experiment is not None
    assert candidate.experiment.target_segment == "tts_request_to_first_downlink"


def test_run_cli_rejects_round_outside_the_manifest_before_browser_effects(tmp_path: Path) -> None:
    runner = _load_runner("post_capture_latency_runner_run_invalid")
    run_dir = tmp_path / "run-a"
    run_dir.mkdir()
    _write_run(run_dir / "run.json")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav)
    manifest = tmp_path / "fixture.json"
    _write_manifest(manifest, wav, digest=hashlib.sha256(wav.read_bytes()).hexdigest())

    assert runner.main(
        [
            "run",
            "--run-json", str(run_dir / "run.json"),
            "--fixture-manifest", str(manifest),
            "--profile-id", "dialogue_no_tool",
            "--round-index", "1",
            "--session-id", "web_benchmark_session",
            "--web-origin", "http://localhost:5173",
            "--browser-command-json", "[]",
            "--timeout-seconds", "1",
        ]
    ) == 2


def test_run_cli_supervises_preexisting_browser_then_applies_the_real_artifact_gate(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    runner = _load_runner("post_capture_latency_runner_run")
    run_dir = tmp_path / "run-a"
    run_dir.mkdir()
    _write_run(run_dir / "run.json")
    wav = tmp_path / "fixture.wav"
    _write_wav(wav)
    manifest = tmp_path / "fixture.json"
    _write_manifest(manifest, wav, digest=hashlib.sha256(wav.read_bytes()).hexdigest())
    calls = []

    def supervise(server, browser_argv, *, timeout_seconds):
        calls.append(("supervise", server.expected_result, browser_argv, timeout_seconds))
        return runner.AttemptResult(server.expected_result, "completed")

    def artifacts(run_path, identity):
        calls.append(("artifacts", run_path, identity))

    monkeypatch.setattr(runner, "supervise_browser_attempt", supervise)
    monkeypatch.setattr(runner, "validate_attempt_artifacts", artifacts)

    assert runner.main(
        [
            "run",
            "--run-json", str(run_dir / "run.json"),
            "--fixture-manifest", str(manifest),
            "--profile-id", "dialogue_no_tool",
            "--round-index", "0",
            "--session-id", "web_benchmark_session",
            "--web-origin", "http://localhost:5173",
            "--browser-command-json", "[]",
            "--timeout-seconds", "2",
        ]
    ) == 0
    assert calls == [
        (
            "supervise",
            runner.AttemptIdentity("run-a", "dialogue_no_tool", "dialogue-paris-en-v1", 0),
            None,
            2.0,
        ),
        (
            "artifacts",
            run_dir,
            runner.AttemptIdentity("run-a", "dialogue_no_tool", "dialogue-paris-en-v1", 0),
        ),
    ]
    assert capsys.readouterr().out.startswith("http://localhost:5173/chat/web_benchmark_session?")


def test_runner_comparison_invokes_closed_module_argv_and_writes_only_explicit_output(
    tmp_path: Path,
) -> None:
    runner = _load_runner("post_capture_latency_runner_compare")
    inputs = tuple(tmp_path / name for name in ("a1.json", "b.json", "a2.json"))
    for path in inputs:
        path.write_text("{}", encoding="utf-8")
    output = tmp_path / "comparison.json"
    calls = []
    payload = {
        "schema_version": "live-voice.latency-comparison-a-b-a.v0",
        "status": "improved",
        "reason": None,
        "baseline_before_run_id": "a1",
        "candidate_run_id": "b",
        "baseline_after_run_id": "a2",
        "before_to_candidate": {},
        "after_to_candidate": {},
        "baseline_drift": [],
    }

    def run(argv, *, shell, check, capture_output, text):
        calls.append((tuple(argv), shell, check, capture_output, text))
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload))

    runner.write_a_b_a_comparison(inputs[0], inputs[1], inputs[2], output, run_command=run)

    assert calls[0][0][:4] == (
        sys.executable,
        "-m",
        "jiuwenswarm.server.live_voice.latency_probe_report",
        "compare-a-b-a",
    )
    assert calls[0][1:] == (False, False, True, True)
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    try:
        runner.write_a_b_a_comparison(inputs[0], inputs[1], inputs[2], output, run_command=run)
    except ValueError as error:
        assert str(error) == "COMPARISON_OUTPUT_EXISTS"
    else:
        raise AssertionError("comparison output must never be overwritten")
    assert len(calls) == 1


def test_runner_compare_subcommand_has_zero_service_or_browser_effects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = _load_runner("post_capture_latency_runner_compare_cli")
    paths = tuple(tmp_path / name for name in ("a1.json", "b.json", "a2.json"))
    for path in paths:
        path.write_text("{}", encoding="utf-8")
    output = tmp_path / "comparison.json"
    calls = []

    def compare(a1, candidate, a2, target):
        calls.append((a1, candidate, a2, target))

    monkeypatch.setattr(runner, "write_a_b_a_comparison", compare)

    assert runner.main(
        [
            "compare",
            "--baseline-before", str(paths[0]),
            "--candidate", str(paths[1]),
            "--baseline-after", str(paths[2]),
            "--output", str(output),
        ]
    ) == 0
    assert calls == [(paths[0], paths[1], paths[2], output)]
